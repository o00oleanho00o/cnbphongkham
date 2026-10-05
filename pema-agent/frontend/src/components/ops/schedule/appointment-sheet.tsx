"use client";

// Book or open an appointment (old modal "Đặt lịch hẹn" / "Chi tiết lịch hẹn" of operations-ui.js, `edit`). The
// fields are the ones the BE stores (patient, doctor, room, start, duration, note); the service comes with a
// later step. Every rule (hours, break, double booking, who may do what) is the BE's: its sentence is shown
// as it is. "Tìm giờ trống" asks the BE for the first free start instead of guessing here.
import { useMemo, useState, type FormEvent } from "react";
import Link from "next/link";

import { Notice } from "@/components/ops/ops-ui";
import { Sheet } from "@/components/ops/sheet";
import { useToast } from "@/components/ops/toast";
import type { Schemas } from "@/lib/api";
import { ApiError, errorMessage, http, unwrap } from "@/lib/api/client";
import { APPOINTMENT_STATUS_LABEL } from "@/lib/ops/labels";
import type { PatientIndex } from "@/lib/ops/use-patient-names";
import { fetchFreeSlot, runTransition } from "@/lib/ops/schedule-api";
import {
  ACTION_DONE,
  ACTION_LABEL,
  STATUS_TONE,
  allowedActions,
  clockOf,
  dayOf,
  isEditable,
  toStartsAt,
  type ScheduleAction,
  type ScheduleItem,
} from "@/lib/ops/schedule-view";
import { useSession } from "@/lib/session/session-context";
import { Badge } from "@/ui/badge";
import { Button } from "@/ui/button";
import { Field, FIELD_CONTROL_CLASS } from "@/ui/field";

type Doctor = Schemas["ScheduleDoctor"];
type Room = Schemas["RoomOut"];

export type SheetTarget =
  | {
      kind: "create";
      day: string;
      doctorId: string | null;
      /** An empty slot of the room grid names the room and the start it was clicked at. */
      roomId?: string | null;
      clock?: string;
    }
  | { kind: "edit"; item: ScheduleItem };

const DURATIONS = [15, 30, 45, 60, 90, 120];

/** The form starts from the visit being opened, or from the day (and doctor) the board was showing. */
function initialValues(target: SheetTarget) {
  if (target.kind === "edit") {
    const { item } = target;
    return {
      doctorId: item.doctor_id ?? "",
      roomId: item.room_id ?? "",
      day: dayOf(item.starts_at),
      clock: clockOf(item.starts_at),
      duration: String(item.duration_min),
      note: item.note ?? "",
    };
  }
  return {
    doctorId: target.doctorId ?? "",
    roomId: target.roomId ?? "",
    day: target.day,
    clock: target.clock ?? "09:00",
    duration: "30",
    note: "",
  };
}

function staleSentence(err: unknown): string {
  if (err instanceof ApiError && err.code === "version_conflict") {
    return "Lịch này vừa được người khác thay đổi. Đóng hộp thoại để tải lại.";
  }
  return errorMessage(err);
}

export function AppointmentSheet({
  target,
  doctors,
  rooms = [],
  patients,
  onClose,
  onSaved,
}: {
  target: SheetTarget;
  doctors: readonly Doctor[];
  /** Rooms of the clinic; without any the room field is not shown. */
  rooms?: readonly Room[];
  patients: PatientIndex;
  onClose: () => void;
  /** Called after the BE accepted a change; the page reloads the board. */
  onSaved: () => void;
}) {
  const { user, can } = useSession();
  const toast = useToast();
  const editing = target.kind === "edit" ? target.item : null;
  const mayWrite = can("appointment.write");
  const locked = editing !== null && (!isEditable(editing.status) || !mayWrite);
  // A doctor books only for themselves (the BE checks it again).
  const ownDoctorOnly = user.role === "doctor";

  const initial = useMemo(() => initialValues(target), [target]);
  const [patientId, setPatientId] = useState(editing?.patient_id ?? "");
  // A doctor books only for themselves: the form starts on their own name, not on "no doctor".
  const [doctorId, setDoctorId] = useState(
    ownDoctorOnly && initial.doctorId === "" ? user.id : initial.doctorId,
  );
  const [roomId, setRoomId] = useState(initial.roomId);
  const [day, setDay] = useState(initial.day);
  const [clock, setClock] = useState(initial.clock);
  const [duration, setDuration] = useState(initial.duration);
  const [note, setNote] = useState(initial.note);
  const [cancelReason, setCancelReason] = useState("");
  const [error, setError] = useState("");
  const [hint, setHint] = useState("");
  const [busy, setBusy] = useState(false);

  const patientOptions = useMemo(
    () => [...patients.values()].toSorted((a, b) => a.full_name.localeCompare(b.full_name, "vi")),
    [patients],
  );
  const doctorChoices = ownDoctorOnly ? doctors.filter((d) => d.id === user.id) : doctors;
  // A paused room is still shown when the visit already holds it, so the form never silently drops it.
  const roomChoices = rooms.filter((r) => r.active || r.id === initial.roomId);

  async function findSlot() {
    setError("");
    setHint("");
    if (patientId === "" || day === "") {
      setError("Chọn bệnh nhân và ngày trước khi tìm giờ trống.");
      return;
    }
    setBusy(true);
    try {
      const slot = await fetchFreeSlot({
        patientId,
        doctorId: doctorId === "" ? null : doctorId,
        day,
        durationMin: Number(duration),
      });
      if (slot === null) {
        setError("Không có giờ trống cho lựa chọn này. Hãy đổi ngày hoặc bác sĩ.");
        return;
      }
      setClock(clockOf(slot));
      setHint("Đã chọn giờ trống. Bấm xác nhận để lưu.");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    setError("");
    if (editing === null && patientId === "") {
      setError("Hãy chọn bệnh nhân.");
      return;
    }
    if (day === "" || clock === "") {
      setError("Hãy nhập ngày và giờ hẹn.");
      return;
    }
    setBusy(true);
    try {
      const startsAt = toStartsAt(day, clock);
      if (editing === null) {
        await unwrap(
          http.POST("/api/v1/appointments", {
            body: {
              patient_id: patientId,
              doctor_id: doctorId === "" ? null : doctorId,
              room_id: roomId === "" ? null : roomId,
              starts_at: startsAt,
              duration_min: Number(duration),
              note: note.trim() === "" ? null : note.trim(),
            },
          }),
        );
        toast.push("success", "Đã đặt lịch hẹn.");
      } else {
        await unwrap(
          http.PATCH("/api/v1/appointments/{appointment_id}", {
            params: { path: { appointment_id: editing.id } },
            body: {
              version: editing.version,
              ...(doctorId !== (editing.doctor_id ?? "")
                ? { doctor_id: doctorId === "" ? null : doctorId }
                : {}),
              ...(roomId !== (editing.room_id ?? "")
                ? { room_id: roomId === "" ? null : roomId }
                : {}),
              ...(startsAt !== editing.starts_at ? { starts_at: startsAt } : {}),
              ...(Number(duration) !== editing.duration_min
                ? { duration_min: Number(duration) }
                : {}),
              ...(note.trim() !== (editing.note ?? "") ? { note: note.trim() } : {}),
            },
          }),
        );
        toast.push("success", "Đã lưu thay đổi lịch hẹn.");
      }
      onSaved();
    } catch (err) {
      setError(staleSentence(err));
    } finally {
      setBusy(false);
    }
  }

  async function move(action: ScheduleAction) {
    if (editing === null) return;
    if (action === "cancel" && cancelReason.trim() === "") {
      setError("Cần lý do hủy cho lịch đang hoạt động.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await runTransition(action, editing, action === "cancel" ? cancelReason.trim() : null);
      toast.push("success", ACTION_DONE[action]);
      onSaved();
    } catch (err) {
      setError(staleSentence(err));
    } finally {
      setBusy(false);
    }
  }

  const actions = editing === null ? [] : allowedActions(editing.status, can);
  const otherActions = actions.filter((a) => a !== "cancel");
  const patientName = editing ? (editing.patient_name ?? editing.patient_code) : "";

  return (
    <Sheet
      title={editing === null ? "Đặt lịch hẹn" : "Chi tiết lịch hẹn"}
      subtitle={editing === null ? undefined : patientName}
      onClose={onClose}
      footer={
        locked ? (
          <Button variant="secondary" onClick={onClose}>
            Đóng
          </Button>
        ) : (
          <>
            <Button variant="secondary" onClick={onClose} disabled={busy}>
              Hủy bỏ
            </Button>
            <Button type="submit" form="appointment-form" disabled={busy}>
              {busy ? "Đang lưu..." : editing === null ? "Xác nhận đặt lịch" : "Lưu thay đổi"}
            </Button>
          </>
        )
      }
    >
      {editing !== null && (
        <div className="mb-4 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={STATUS_TONE[editing.status]}>
              {APPOINTMENT_STATUS_LABEL[editing.status]}
            </Badge>
            {can("patient.read_360") && (
              <Link
                href={`/patients/${editing.patient_id}`}
                className="text-small font-medium text-link hover:underline"
              >
                Patient 360 →
              </Link>
            )}
          </div>
          {otherActions.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {otherActions.map((action) => (
                <Button
                  key={action}
                  variant="secondary"
                  disabled={busy}
                  onClick={() => void move(action)}
                >
                  {ACTION_LABEL[action]}
                </Button>
              ))}
            </div>
          )}
          {editing.cancel_reason !== null && editing.cancel_reason !== undefined && (
            <Notice tone="warn">Lý do hủy: {editing.cancel_reason}</Notice>
          )}
          {!isEditable(editing.status) && (
            <Notice>Lịch đã bắt đầu, hoàn tất, hủy hoặc vắng; hãy tạo lịch mới để đổi.</Notice>
          )}
        </div>
      )}

      <form id="appointment-form" onSubmit={(e) => void save(e)}>
        {editing === null && (
          <Field label="Bệnh nhân" required>
            {(control) => (
              <select
                {...control}
                className={FIELD_CONTROL_CLASS}
                value={patientId}
                onChange={(e) => setPatientId(e.target.value)}
              >
                <option value="">Chọn bệnh nhân…</option>
                {patientOptions.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.full_name} · {p.code}
                  </option>
                ))}
              </select>
            )}
          </Field>
        )}
        <div className="grid grid-cols-1 gap-x-3 sm:grid-cols-2">
          <Field label="Bác sĩ">
            {(control) => (
              <select
                {...control}
                className={FIELD_CONTROL_CLASS}
                value={doctorId}
                disabled={locked}
                onChange={(e) => setDoctorId(e.target.value)}
              >
                {!ownDoctorOnly && <option value="">Chưa gán bác sĩ</option>}
                {doctorChoices.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </select>
            )}
          </Field>
          {roomChoices.length > 0 && (
            <Field label="Phòng">
              {(control) => (
                <select
                  {...control}
                  className={FIELD_CONTROL_CLASS}
                  value={roomId}
                  disabled={locked}
                  onChange={(e) => setRoomId(e.target.value)}
                >
                  <option value="">Chưa xếp phòng</option>
                  {roomChoices.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name}
                      {r.active ? "" : " (tạm ngưng)"}
                    </option>
                  ))}
                </select>
              )}
            </Field>
          )}
          <Field label="Thời lượng">
            {(control) => (
              <select
                {...control}
                className={FIELD_CONTROL_CLASS}
                value={duration}
                disabled={locked}
                onChange={(e) => setDuration(e.target.value)}
              >
                {DURATIONS.map((m) => (
                  <option key={m} value={m}>
                    {m} phút
                  </option>
                ))}
              </select>
            )}
          </Field>
          <Field label="Ngày" required>
            {(control) => (
              <input
                {...control}
                type="date"
                className={FIELD_CONTROL_CLASS}
                value={day}
                disabled={locked}
                onChange={(e) => setDay(e.target.value)}
              />
            )}
          </Field>
          <Field label="Giờ" required hint={hint === "" ? undefined : hint}>
            {(control) => (
              <input
                {...control}
                type="time"
                step={300}
                className={FIELD_CONTROL_CLASS}
                value={clock}
                disabled={locked}
                onChange={(e) => setClock(e.target.value)}
              />
            )}
          </Field>
        </div>
        <Field label="Ghi chú">
          {(control) => (
            <input
              {...control}
              type="text"
              maxLength={1000}
              className={FIELD_CONTROL_CLASS}
              value={note}
              disabled={locked}
              onChange={(e) => setNote(e.target.value)}
            />
          )}
        </Field>
        {!locked && (
          <div className="mb-3.5">
            <Button variant="secondary" disabled={busy} onClick={() => void findSlot()}>
              Tìm giờ trống
            </Button>
          </div>
        )}
      </form>

      {editing !== null && actions.includes("cancel") && (
        <section aria-label="Hủy lịch hẹn" className="mt-2 border-t border-line pt-4">
          <Field label="Lý do hủy">
            {(control) => (
              <input
                {...control}
                type="text"
                maxLength={500}
                className={FIELD_CONTROL_CLASS}
                value={cancelReason}
                onChange={(e) => setCancelReason(e.target.value)}
              />
            )}
          </Field>
          <Button variant="danger" disabled={busy} onClick={() => void move("cancel")}>
            {ACTION_LABEL.cancel}
          </Button>
        </section>
      )}

      {error !== "" && (
        <div className="mt-3">
          <Notice tone="error">{error}</Notice>
        </div>
      )}
    </Sheet>
  );
}
