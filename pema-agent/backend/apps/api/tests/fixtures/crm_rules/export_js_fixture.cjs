/*
 * Runs the ORIGINAL prototype CRM engine (prototype/shared/crm-data.js + crm-automation.js) under node on the
 * synthetic CRM01 fixture with the fixed clock 2026-09-20 and writes what a Python port must reproduce:
 *
 *   crm_rules_js_scenarios.json   per scenario: the engine INPUT (rules, patients, existing tasks) and the
 *                                 expected OUTPUT (all tasks after the run, per-patient profile)
 *
 * Read-only on prototype/. Regenerate with:  node export_js_fixture.cjs
 * The committed JSON is what the pytest suite reads; node is not needed to run the tests.
 * Everything here is synthetic (patients P001..P046 of the prototype). Names, phones and photos are NOT exported.
 */
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm'), crypto = require('node:crypto');

const SHARED = path.resolve(__dirname, '../../../../../../../prototype/shared');

function boot(ensure) {
  let stored = null;
  const listeners = {};
  const ctx = {
    console, crypto, structuredClone,
    Event: class { constructor(type) { this.type = type; } },
    CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } },
    localStorage: { getItem: () => stored, setItem: (k, v) => (stored = v) },
    addEventListener: (k, f) => (listeners[k] ||= []).push(f),
    dispatchEvent: (e) => (listeners[e.type] || []).forEach((f) => f(e)),
  };
  ctx.window = ctx;
  vm.createContext(ctx);
  for (const f of ['data.js', 'operations-data.js', 'crm-data.js', 'crm-automation.js']) {
    vm.runInContext(fs.readFileSync(path.join(SHARED, f), 'utf8'), ctx, { filename: f });
  }
  if (ensure) ctx.PemaCRM.ensure();
  else ctx.PemaCRMData.seed(); // fixture/migration only; the engine has not run yet
  return ctx;
}

const clone = (x) => JSON.parse(JSON.stringify(x));

/** Engine input: only what the rules read. No names, phones, notes, images. */
function snapshot(x) {
  const appts = x.PemaOps.seed().appointments;
  return {
    today: x.PemaCRMData.DAY,
    rules: clone(x.Pema.state.crmAutomationRules).map((r) => ({
      id: r.id, name: r.name, trigger: r.trigger, delayDays: r.delayDays, suggestedAction: r.suggestedAction,
      priority: r.priority, active: r.active, protocol: r.conditions.protocol, marketing: r.conditions.marketing,
    })),
    patients: x.Pema.state.patients.map((p) => ({
      id: p.id, doctor: p.doctor, owner: p.crm.owner, lastVisit: p.lastVisit || null,
      total: p.total, completed: p.completed,
      sessions: p.sessions.map((s) => ({ id: s.id, date: s.date, protocolId: s.protocolId || null })),
      appointments: appts.filter((a) => a.patient === p.id).map((a) => ({
        id: a.id, date: a.date, time: a.time, status: a.status,
        cancelledAt: a.cancelledAt || null, missedAt: a.missedAt || null,
      })),
      birthday: p.crm.birthday || null, marketingOptOut: !!p.crm.marketingOptOut,
      recommendationAt: p.crm.recommendationAt || null,
      expectedVisitSource: p.crm.expectedVisitSource || null,
      expectedVisitReason: p.crm.expectedVisitReason || null,
      lastProtocolSession: p.crm.lastProtocolSession || null,
      reactivatedAt: p.crm.reactivatedAt || null,
      firstPlanId: p.servicePlans?.[0]?.id || null,
    })),
    existingTasks: clone(x.Pema.state.crmTasks).map((t) => ({ id: t.id, ruleId: t.ruleId, status: t.status })),
  };
}

function outcome(x) {
  return {
    tasks: clone(x.Pema.state.crmTasks).map((t) => ({
      id: t.id, patientId: t.patientId, ruleId: t.ruleId, reason: t.reason, priority: t.priority,
      dueAt: t.dueAt, status: t.status, owner: t.owner, suggestedAction: t.suggestedAction,
      sourceEventId: t.sourceEventId, relatedAppointmentId: t.relatedAppointmentId || null,
      relatedPlanId: t.relatedPlanId || null, resolution: t.resolution || null,
    })),
    patients: Object.fromEntries(x.Pema.state.patients.map((p) => [p.id, {
      recommendationAt: p.crm.recommendationAt || null,
      expectedVisitSource: p.crm.expectedVisitSource || null,
      expectedVisitReason: p.crm.expectedVisitReason || null,
      lastProtocolSession: p.crm.lastProtocolSession || null,
      expectedNextVisitAt: p.crm.expectedNextVisitAt || null,
      overdueDays: p.crm.overdueDays, lifecycleStage: p.crm.lifecycleStage, riskLevel: p.crm.riskLevel,
      lastVisitAt: p.crm.lastVisitAt || null,
    }])),
  };
}

const scenarios = [];

function scenario(name, description, build, act) {
  const x = build();
  act(x);
  const input = snapshot(x); // after the mutation, before the run (existing tasks = state of the previous run)
  x.PemaCRM.run();
  scenarios.push({ name, description, input, expected: outcome(x) });
}

const boot0 = () => boot(true);
const patient = (x, id) => x.Pema.patient(id);
const appts = (x) => x.Pema.state.operations.appointments;

// 1. Fresh seed, first run: all ten rules, P025..P032 and the ten mobile cases.
{
  const x = boot(false);
  const input = snapshot(x);
  x.PemaCRM.ensure();
  scenarios.push({ name: 'fresh_seed', description: 'first run on the CRM01 seed (no tasks yet)', input, expected: outcome(x) });
}
scenario('rerun_is_idempotent', 'a second run changes nothing', boot0, () => {});
scenario('optout_supersedes_marketing_keeps_clinical',
  'P030 opts out: dormant180 superseded, abandoned (clinical) stays', boot0, (x) => { patient(x, 'P030').crm.marketingOptOut = true; });
scenario('rule_deactivated_supersedes', 'd1 switched off: its open tasks are superseded', boot0,
  (x) => { x.Pema.state.crmAutomationRules.find((r) => r.id === 'd1').active = false; });
scenario('new_protocol_session_creates_future_d1_d3_d7', 'a Laser CO2 session today creates D+1/3/7 with future due dates', boot0,
  (x) => { patient(x, 'P001').sessions.push({ id: 'new-session', date: '2026-09-20', protocolId: 'laser-co2' }); });
scenario('non_protocol_session_creates_no_d_tasks', 'a session without protocol never creates D+1/3/7', boot0,
  (x) => { patient(x, 'P001').sessions.push({ id: 'plain-session', date: '2026-09-20' }); });
scenario('recall_24h_boundary_before', 'cancellation 15h before the clock: not yet a recall', boot0, (x) => {
  const p = patient(x, 'P036');
  x.Pema.state.operations.appointments = appts(x).filter((a) => a.patient !== p.id);
  appts(x).push({ id: 'recent-cancel', patient: p.id, date: '2026-09-19', time: '17:00', status: 'cancelled', cancelledAt: '2026-09-19T17:00:00+07:00' });
});
scenario('recall_24h_boundary_after', 'cancellation 25h before the clock: recall', boot0, (x) => {
  const p = patient(x, 'P036');
  x.Pema.state.operations.appointments = appts(x).filter((a) => a.patient !== p.id);
  appts(x).push({ id: 'recent-cancel', patient: p.id, date: '2026-09-19', time: '17:00', status: 'cancelled', cancelledAt: '2026-09-19T08:00:00+07:00' });
});
scenario('birthday_past_excluded', 'a birthday that already passed this year is not due', boot0,
  (x) => { patient(x, 'P001').crm.birthday = '1990-09-19'; });
scenario('birthday_on_the_last_day_of_window', 'a birthday exactly 7 days ahead is due', boot0,
  (x) => { patient(x, 'P001').crm.birthday = '1990-09-27'; });
scenario('birthday_after_window_excluded', 'a birthday 8 days ahead is not due', boot0,
  (x) => { patient(x, 'P001').crm.birthday = '1990-09-28'; });
scenario('booking_supersedes_overdue', 'P027 books a future visit: overdue task superseded, expected date becomes the appointment', boot0, (x) => {
  // saveAppointment runs the CRM itself; restore the tasks so the scenario's own run performs the transition.
  const before = clone(x.Pema.state.crmTasks);
  x.PemaOps.saveAppointment({ patient: 'P027', service: 'S0', doctor: 'D0', room: 'R0', date: '2026-09-27', time: '10:00' });
  x.Pema.state.crmTasks = before;
});
scenario('cancelled_booking_does_not_revive_superseded_task', 'the booking is cancelled again: expected date returns to the recommendation but the superseded task stays closed', () => {
  const x = boot0();
  x.PemaOps.saveAppointment({ patient: 'P027', service: 'S0', doctor: 'D0', room: 'R0', date: '2026-09-27', time: '10:00' });
  x.PemaCRM.ensure();
  return x;
}, (x) => {
  const a = appts(x).at(-1);
  x.PemaOps.cancel(a.id, 'Khach chua thu xep duoc');
});
scenario('exactly_180_days_leaves_the_90_day_group', 'a patient at exactly 180 days belongs to dormant180 only', boot0,
  (x) => { patient(x, 'P031').lastVisit = '2026-03-24'; });
scenario('arrival_today_suppresses_due', 'expected visit today but the patient already arrived: no due task', boot0, (x) => {
  patient(x, 'P001').crm.recommendationAt = '2026-09-20';
  x.Pema.state.operations.appointments = appts(x).filter((a) => a.patient !== 'P001');
  appts(x).push({ id: 'today-arrived', patient: 'P001', doctor: 'D0', room: 'R0', service: 'S0', date: '2026-09-20', time: '10:00', duration: 30, buffer: 0, status: 'arrived' });
});
scenario('due_today_without_arrival', 'expected visit today and not arrived: due task', boot0, (x) => {
  x.Pema.state.operations.appointments = appts(x).filter((a) => a.patient !== 'P001');
  patient(x, 'P001').crm.recommendationAt = '2026-09-20';
});
const lonePatient = (x) => {
  x.Pema.state.operations.appointments = appts(x).filter((a) => a.patient !== 'P001');
  return patient(x, 'P001');
};
scenario('protocol_session_45_days_old_still_creates_d_tasks', 'a Laser CO2 session exactly 45 days old is inside the window', boot0,
  (x) => { patient(x, 'P001').sessions = [{ id: 'old-45', date: '2026-08-06', protocolId: 'laser-co2' }]; });
scenario('protocol_session_46_days_old_creates_none', 'a Laser CO2 session 46 days old is outside the window', boot0,
  (x) => { patient(x, 'P001').sessions = [{ id: 'old-46', date: '2026-08-05', protocolId: 'laser-co2' }]; });
scenario('abandoned_at_exactly_45_days_is_not_yet_abandoned', 'age must be MORE than 45 days', boot0,
  (x) => { patient(x, 'P029').lastVisit = '2026-08-06'; });
scenario('abandoned_at_46_days', 'age 46 with sessions left and no booking', boot0,
  (x) => { patient(x, 'P029').lastVisit = '2026-08-05'; });
scenario('dormant_at_89_days_is_not_dormant', '89 days: the 90-day group does not apply yet', boot0,
  (x) => { patient(x, 'P031').lastVisit = '2026-06-23'; });
scenario('dormant_at_exactly_90_days', '90 days: the 90-day group applies', boot0,
  (x) => { patient(x, 'P031').lastVisit = '2026-06-22'; });
scenario('overdue_one_day', 'expected visit yesterday: overdue by one day', boot0,
  (x) => { lonePatient(x).crm.recommendationAt = '2026-09-19'; });
scenario('overdue_zero_days_is_due_not_overdue', 'expected visit today: due, not overdue', boot0,
  (x) => { lonePatient(x).crm.recommendationAt = '2026-09-20'; });
scenario('high_risk_after_seven_days_overdue', 'overdue by 8 days with no booking is high risk, 7 is not', boot0,
  (x) => { lonePatient(x).crm.recommendationAt = '2026-09-12'; });
scenario('reactivated_patient_is_reactivated', 'a check-in after care sets reactivatedAt and the lifecycle stage', boot0,
  (x) => { patient(x, 'P031').crm.reactivatedAt = '2026-09-20T09:00:00+07:00'; });
scenario('doctor_edit_of_recommendation_is_kept', 'the D+30 recommendation is only applied once per session', boot0,
  (x) => { patient(x, 'P025').crm.recommendationAt = '2026-12-01'; });
scenario('manual_task_is_never_superseded', 'a staff task (ruleId manual) survives a rerun', boot0, (x) => {
  x.Pema.state.crmTasks.push({ id: 'CRM:manual:P001:x', patientId: 'P001', ruleId: 'manual', type: 'manual', reason: 'Viec thu cong', priority: 'normal', createdAt: '2026-09-20T08:00:00+07:00', dueAt: '2026-09-20T09:00:00+07:00', status: 'open', owner: 'CSKH Thu', suggestedAction: 'x', sourceEventId: 'x' });
});

// Size: every scenario but the first two is stored as a difference from "rerun_is_idempotent" (the state after
// one run on the seed). The pytest loader (tests/clinic/crm_rules/js_fixture.py) rebuilds the full picture.
const base = scenarios[1];
const basePatients = new Map(base.input.patients.map((p) => [p.id, JSON.stringify(p)]));
const baseTasks = new Map(base.expected.tasks.map((t) => [t.id, JSON.stringify(t)]));
const baseProfile = new Map(Object.entries(base.expected.patients).map(([k, v]) => [k, JSON.stringify(v)]));
const packed = scenarios.map((sc, i) => {
  if (i < 2) return sc;
  return {
    name: sc.name, description: sc.description,
    input: {
      today: sc.input.today, rules: sc.input.rules, existingTasks: sc.input.existingTasks,
      patientsChanged: sc.input.patients.filter((p) => basePatients.get(p.id) !== JSON.stringify(p)),
    },
    expected: {
      tasksChanged: sc.expected.tasks.filter((t) => baseTasks.get(t.id) !== JSON.stringify(t)),
      taskIds: sc.expected.tasks.map((t) => t.id),
      patientsChanged: Object.fromEntries(Object.entries(sc.expected.patients).filter(([k, v]) => baseProfile.get(k) !== JSON.stringify(v))),
    },
  };
});

fs.writeFileSync(path.join(__dirname, 'crm_rules_js_scenarios.json'), JSON.stringify({ clock: '2026-09-20', base: 'rerun_is_idempotent', scenarios: packed }) + String.fromCharCode(10));
console.log(JSON.stringify(scenarios.map((s) => [s.name, s.expected.tasks.length])));
