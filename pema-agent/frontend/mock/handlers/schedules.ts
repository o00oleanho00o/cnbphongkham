// Mock of the scheduled jobs. A job is addressed by its id alone (the clinic is the session's). Times are
// ISO strings; the schedule input is the contract's union by `kind`.
import { accounts } from "./accounts";
import {
  bodyOf,
  fail,
  isoFromNow,
  uid,
  DAY,
  HOUR,
  MIN,
  type Reply,
  type Router,
  type Schemas,
} from "../core";

type S = Schemas;

const BASE = {
  clinic_id: accounts[0]?.clinic_id ?? "",
  delivery_attempts: 0,
  dedupe_key: null,
  patient_id: null,
};

const jobs: S["ScheduledJob"][] = [
  {
    ...BASE,
    id: "job-nhac-tai-kham",
    account_id: "pema-bot",
    thread_id: "u-demo-005",
    thread_type: 0,
    name: "Nhắc tái khám tuần sau",
    kind: "message",
    payload: "nhac-tai-kham",
    schedule_kind: "once",
    run_at: isoFromNow(2 * DAY),
    every_minutes: null,
    cron_expr: null,
    timezone: "Asia/Ho_Chi_Minh",
    enabled: true,
    next_run_at: isoFromNow(2 * DAY),
    last_run_at: null,
    last_status: null,
    last_error: null,
    run_count: 0,
    max_runs: 1,
    created_by: "staff",
    origin: "crm_rule",
    created_at: isoFromNow(-1 * DAY),
    updated_at: isoFromNow(-1 * DAY),
  },
  {
    ...BASE,
    id: "job-tong-ket",
    account_id: "le-tan-ca-nhan",
    thread_id: "u-demo-021",
    thread_type: 0,
    name: "Tóm tắt việc cuối ngày",
    kind: "agent",
    payload: "Tóm tắt các việc chăm sóc còn mở và gợi ý ưu tiên cho ngày mai.",
    schedule_kind: "cron",
    run_at: null,
    every_minutes: null,
    cron_expr: "30 17 * * 1-6",
    timezone: "Asia/Ho_Chi_Minh",
    enabled: true,
    next_run_at: isoFromNow(5 * HOUR),
    last_run_at: isoFromNow(-19 * HOUR),
    last_status: "ok",
    last_error: null,
    run_count: 12,
    max_runs: null,
    created_by: "staff",
    origin: "staff",
    created_at: isoFromNow(-20 * DAY),
    updated_at: isoFromNow(-19 * HOUR),
  },
  {
    ...BASE,
    id: "job-ping-loi",
    account_id: "le-tan-ca-nhan",
    thread_id: "u-demo-022",
    thread_type: 0,
    name: "Nhắc kiểm tra kho vật tư",
    kind: "message",
    payload: "Nhớ kiểm tra kho vật tư vào cuối tuần nhé.",
    schedule_kind: "every",
    run_at: null,
    every_minutes: 10080,
    cron_expr: null,
    timezone: "Asia/Ho_Chi_Minh",
    enabled: true,
    next_run_at: isoFromNow(3 * DAY),
    last_run_at: isoFromNow(-4 * DAY),
    last_status: "error",
    last_error: "Tài khoản chưa đăng nhập (cần quét QR lại).",
    run_count: 3,
    max_runs: null,
    created_by: "agent",
    origin: "agent_tool",
    created_at: isoFromNow(-30 * DAY),
    updated_at: isoFromNow(-4 * DAY),
  },
];

const runs = new Map<string, S["JobRunRecord"][]>([
  [
    "job-tong-ket",
    [
      {
        id: 3,
        job_id: "job-tong-ket",
        status: "ok",
        detail: "Đã gửi bản tóm tắt.",
        delivered_chars: 412,
        started_at: isoFromNow(-19 * HOUR),
        finished_at: isoFromNow(-19 * HOUR + MIN),
        turn_id: 41,
      },
      {
        id: 2,
        job_id: "job-tong-ket",
        status: "skipped",
        detail: "Chạm trần tin chủ động trong ngày.",
        delivered_chars: 0,
        started_at: isoFromNow(-43 * HOUR),
        finished_at: isoFromNow(-43 * HOUR),
        turn_id: null,
      },
      {
        id: 1,
        job_id: "job-tong-ket",
        status: "silent",
        detail: "Không có việc nào, bot im lặng.",
        delivered_chars: 0,
        started_at: isoFromNow(-67 * HOUR),
        finished_at: isoFromNow(-67 * HOUR + MIN),
        turn_id: 37,
      },
    ],
  ],
]);

function jobOr404(id: string | undefined): S["ScheduledJob"] {
  const found = jobs.find((j) => j.id === id);
  if (!found) fail(404, "not_found", "Không tìm thấy lịch hẹn.");
  return found;
}

function nextRun(input: S["ScheduleInput"]): string | null {
  if ("in_minutes" in input) return isoFromNow(input.in_minutes * MIN);
  if (input.kind === "once" && "date" in input) {
    const at = Date.parse(`${input.date}T${input.time}:00+07:00`);
    if (Number.isNaN(at)) fail(422, "invalid_schedule", "Ngày giờ không hợp lệ.");
    if (at <= Date.now()) fail(422, "invalid_schedule", "Thời điểm chạy phải ở tương lai.");
    return isoFromNow(at - Date.now());
  }
  if (input.kind === "every") return isoFromNow(input.minutes * MIN);
  if (input.kind === "cron") {
    if (input.expr.trim().split(/\s+/).length !== 5) {
      fail(422, "invalid_schedule", "Biểu thức cron cần đúng 5 trường.");
    }
    return isoFromNow(HOUR);
  }
  return null;
}

function applySchedule(job: S["ScheduledJob"], input: S["ScheduleInput"]): void {
  job.next_run_at = nextRun(input);
  if (input.kind === "every")
    Object.assign(job, {
      schedule_kind: "every",
      every_minutes: input.minutes,
      cron_expr: null,
      run_at: null,
    });
  else if (input.kind === "cron")
    Object.assign(job, {
      schedule_kind: "cron",
      cron_expr: input.expr,
      every_minutes: null,
      run_at: null,
    });
  else
    Object.assign(job, {
      schedule_kind: "once",
      run_at: job.next_run_at,
      every_minutes: null,
      cron_expr: null,
    });
}

export function register(r: Router): void {
  r.get("/api/v1/admin/schedules", "admin.schedules", (ctx): Reply => {
    const account = ctx.query.get("account_id");
    return { body: jobs.filter((j) => !account || j.account_id === account) };
  });

  r.post("/api/v1/admin/schedules", "admin.schedules", (ctx): Reply => {
    const input = bodyOf<S["ScheduleCreate"]>(ctx);
    const account = accounts.find((a) => a.id === input.account_id);
    if (!account) fail(404, "not_found", "Không tìm thấy tài khoản.");
    const job: S["ScheduledJob"] = {
      ...BASE,
      id: uid("job"),
      account_id: input.account_id,
      thread_id: input.thread_id,
      thread_type: input.thread_type ?? 0,
      name: input.name,
      kind: input.kind,
      payload: input.payload,
      schedule_kind: "once",
      run_at: null,
      every_minutes: null,
      cron_expr: null,
      timezone: input.timezone || "Asia/Ho_Chi_Minh",
      enabled: true,
      next_run_at: null,
      last_run_at: null,
      last_status: null,
      last_error: null,
      run_count: 0,
      max_runs: input.max_runs ?? null,
      created_by: "staff",
      origin: "staff",
      created_at: isoFromNow(0),
      updated_at: isoFromNow(0),
    };
    applySchedule(job, input.schedule);
    jobs.push(job);
    return { status: 201, body: job };
  });

  r.patch("/api/v1/admin/schedules/{job_id}", "admin.schedules", (ctx): Reply => {
    const job = jobOr404(ctx.params.job_id);
    const input = bodyOf<S["ScheduleUpdate"]>(ctx);
    if (input.name) job.name = input.name;
    if (input.payload) job.payload = input.payload;
    if (input.schedule) applySchedule(job, input.schedule);
    if (input.enabled !== undefined && input.enabled !== null) job.enabled = input.enabled;
    job.updated_at = isoFromNow(0);
    return { body: job };
  });

  r.delete("/api/v1/admin/schedules/{job_id}", "admin.schedules", (ctx): Reply => {
    const job = jobOr404(ctx.params.job_id);
    jobs.splice(jobs.indexOf(job), 1);
    runs.delete(job.id);
    return { status: 204 };
  });

  r.post("/api/v1/admin/schedules/{job_id}/run", "admin.schedules", (ctx): Reply => {
    const job = jobOr404(ctx.params.job_id);
    const history = runs.get(job.id) ?? [];
    const run: S["JobRunRecord"] = {
      id: history.length + 100,
      job_id: job.id,
      status: job.last_status === "error" ? "error" : "ok",
      detail:
        job.last_status === "error"
          ? (job.last_error ?? "Lỗi")
          : "Chạy thử xong (không gửi cho khách).",
      delivered_chars: 0,
      started_at: isoFromNow(0),
      finished_at: isoFromNow(0),
      turn_id: job.kind === "agent" ? 99 : null,
    };
    runs.set(job.id, [run, ...history]);
    job.last_run_at = run.started_at;
    job.run_count = (job.run_count ?? 0) + 1;
    return { body: run };
  });

  r.get("/api/v1/admin/schedules/{job_id}/runs", "admin.schedules", (ctx): Reply => ({
    body: runs.get(jobOr404(ctx.params.job_id).id) ?? [],
  }));
}
