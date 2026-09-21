/* Node VM regression audit for the shared synthetic data layer.
 * Run: node prototype/data-audit.cjs
 * No browser storage or prototype code is modified.
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const crypto = require('crypto');
const root = path.resolve(__dirname, '..');
const sourceRelative = 'prototype/shared/data.js';
const source = fs.readFileSync(path.join(root, sourceRelative), 'utf8');
const KEY = 'pema-demo-v2';
const results = [];
const clone = value => JSON.parse(JSON.stringify(value));

function run(seed = null, mode = {}) {
  let stored = seed;
  const events = [], listeners = {};
  let writes = 0, reads = 0;
  const storage = {
    getItem() {
      reads++;
      if (mode.readThrows) {
        const error = Error('Storage access unavailable');
        error.name = 'SecurityError';
        throw error;
      }
      return stored;
    },
    setItem(key, value) {
      writes++;
      if (mode.writeThrows) {
        const error = Error('Storage quota exceeded');
        error.name = 'QuotaExceededError';
        throw error;
      }
      stored = value;
    }
  };
  class Event { constructor(type) { this.type = type; } }
  class CustomEvent extends Event {
    constructor(type, options = {}) { super(type); this.detail = options.detail; }
  }
  const window = {
    dispatchEvent(event) {
      events.push({ type: event.type, detail: event.detail });
      (listeners[event.type] || []).forEach(fn => fn(event));
      return true;
    },
    addEventListener(type, fn) { (listeners[type] ??= []).push(fn); }
  };
  const context = { localStorage: storage, window, Event, CustomEvent, console };
  vm.runInNewContext(source, context, { filename: sourceRelative, timeout: 2000 });
  return {
    p: window.Pema, events,
    setStored(value) { stored = value; },
    get stored() { return stored; },
    get writes() { return writes; },
    get reads() { return reads; },
    dispatchStorage() { window.dispatchEvent({ type: 'storage', key: KEY }); }
  };
}
function assert(condition, message) { if (!condition) throw Error(message); }
function check(name, test) {
  try { results.push({ name, status: 'PASS', details: test() ?? {} }); }
  catch (error) { results.push({ name, status: 'FAIL', error: error.message }); }
}

const baseline = clone(run().p.state);
const fingerprint = state => JSON.stringify(state.patients.map(p => [p.id, p.name, p.completed, p.total, p.sessions]));
const baselineFingerprint = fingerprint(baseline);
function restored(seed) {
  const result = run(seed);
  assert(fingerprint(result.p.state) === baselineFingerprint, 'Expected a fresh synthetic state');
  assert(result.p.state.followups.length === 5, 'Expected five synthetic follow-ups');
  assert(result.p.state.audit.length === 0, 'Expected cleared synthetic audit');
  assert(result.p.state.selected === 'P001', 'Expected P001 selection');
  assert(result.p.brief(result.p.patient()).includes('Nguyễn Minh Linh'), 'Seed brief must be readable');
  return {
    patientCount: result.p.state.patients.length,
    followupCount: result.p.state.followups.length,
    persisted: JSON.parse(result.stored).version === 2
  };
}
for (const [name, value] of [
  ['malformed_json', '{oops'],
  ['empty_storage', null],
  ['json_null', 'null'],
  ['json_empty_object', '{}'],
  ['json_empty_array', '[]'],
  ['json_string', '"stale"'],
  ['version_2_empty_patients', JSON.stringify({ version: 2, selected: 'P001', patients: [], followups: [], audit: [] })],
  ['wrong_version', JSON.stringify({ ...baseline, version: 1 })],
  ['patients_wrong_type', JSON.stringify({ ...baseline, patients: {} })],
  ['missing_patient_sessions', JSON.stringify({ ...baseline, patients: baseline.patients.map((p, i) => i ? p : { ...p, sessions: null }) })],
  ['orphan_followup', JSON.stringify({ ...baseline, followups: [{ id: 'F404', patient: 'P404' }] })]
]) check(name, () => restored(value));

check('valid_state_is_preserved', () => {
  const state = clone(baseline);
  state.patients[0].name = 'Tên demo đã chỉnh';
  state.audit.push({ action: 'Test only' });
  const result = run(JSON.stringify(state));
  assert(result.p.patient('P001').name === 'Tên demo đã chỉnh', 'Valid user modification was reset');
  assert(result.p.state.audit.length === 1, 'Valid audit was discarded');
  return { modifiedNamePreserved: true, auditPreserved: true };
});
for (const [name, mode] of [
  ['storage_read_throws', { readThrows: true }],
  ['storage_write_throws', { writeThrows: true }],
  ['storage_read_and_write_throw', { readThrows: true, writeThrows: true }]
]) check(name, () => {
  const result = run(null, mode);
  assert(result.p.state.patients.length === 36, 'Expected synthetic state in memory');
  assert(result.p.brief(result.p.patient()).length > 0, 'Brief should stay usable');
  const returnValue = result.p.save();
  if (mode.writeThrows) {
    assert(returnValue === false, 'save must report failure');
    assert(result.events.some(e => e.type === 'pema-save-error' && typeof e.detail === 'string'), 'Expected visible storage error event');
  } else assert(returnValue === true, 'save should succeed when only reads fail');
  return {
    patientCount: result.p.state.patients.length,
    saveReturn: returnValue,
    errorEvents: result.events.filter(e => e.type === 'pema-save-error').length
  };
});
check('invalid_external_storage_retains_last_good_state', () => {
  const result = run(), before = JSON.stringify(result.p.state);
  result.setStored('{"version":2,"patients":[]}');
  result.dispatchStorage();
  assert(JSON.stringify(result.p.state) === before, 'Invalid storage event replaced last known good state');
  assert(result.events.some(e => e.type === 'pema-external'), 'Expected external refresh notification');
  return { patientCount: result.p.state.patients.length, lastGoodStateRetained: true };
});
check('seeded_sessions_chronological_and_match_completed', () => {
  const state = run().p.state, failures = [];
  for (const patient of state.patients) {
    if (patient.completed !== patient.sessions.length) failures.push({ patient: patient.id, issue: 'completed_count', completed: patient.completed, sessions: patient.sessions.length });
    if (patient.completed > patient.total || patient.completed < 0) failures.push({ patient: patient.id, issue: 'completed_bounds' });
    for (let i = 0; i < patient.sessions.length; i++) {
      const date = patient.sessions[i].date, timestamp = Date.parse(date + 'T00:00:00Z'), last = Date.parse(patient.lastVisit + 'T00:00:00Z');
      if (!Number.isFinite(timestamp) || !Number.isFinite(last) || timestamp > last) failures.push({ patient: patient.id, issue: 'invalid_or_after_last_visit', date, lastVisit: patient.lastVisit });
      if (i && date < patient.sessions[i - 1].date) failures.push({ patient: patient.id, issue: 'unsorted', previous: patient.sessions[i - 1].date, date });
    }
    if (patient.sessions.length && patient.sessions.at(-1).date !== patient.lastVisit) failures.push({ patient: patient.id, issue: 'latest_session_not_last_visit', latest: patient.sessions.at(-1).date, lastVisit: patient.lastVisit });
  }
  assert(!failures.length, JSON.stringify(failures));
  return {
    patientsChecked: state.patients.length,
    sessionsChecked: state.patients.reduce((n, p) => n + p.sessions.length, 0),
    allAscending: true, allAtOrBeforeLastVisit: true,
    latestMatchesLastVisit: true, completedMatchesCount: true
  };
});
check('seeded_ids_and_followup_references_valid', () => {
  const state = run().p.state, ids = state.patients.map(p => p.id), sessionIds = state.patients.flatMap(p => p.sessions.map(s => s.id));
  assert(new Set(ids).size === ids.length, 'Duplicate patient ID');
  assert(new Set(sessionIds).size === sessionIds.length, 'Duplicate session ID');
  assert(state.followups.every(f => ids.includes(f.patient)), 'Orphan follow-up reference');
  return { patientIds: ids.length, sessionIds: sessionIds.length, followups: state.followups.length };
});
check('malformed_nested_patient_missing_concern', () => {
  const state = clone(baseline);
  delete state.patients[0].concern;
  const result = run(JSON.stringify(state));
  assert(typeof result.p.patient('P001').concern === 'string', 'Persisted patient missing concern passed validation and was not restored');
  assert(result.p.brief(result.p.patient()).length > 0, 'Brief must remain readable');
  return { restored: true };
});
check('malformed_nested_session_null_entry', () => {
  const state = clone(baseline);
  state.patients[0].sessions = [null];
  const result = run(JSON.stringify(state));
  assert(result.p.patient('P001').sessions.every(s => s && typeof s.date === 'string'), 'Null session entry passed validation and was not restored');
  return { restored: true };
});
const audit = {
  generatedAt: new Date().toISOString(),
  scope: 'Node VM data.js only; no browser UI, file uploads, or real localStorage mutation',
  source: sourceRelative,
  sourceSha256: crypto.createHash('sha256').update(source).digest('hex'),
  node: process.version,
  summary: { total: results.length, passed: results.filter(r => r.status === 'PASS').length, failed: results.filter(r => r.status === 'FAIL').length },
  results
};
const output = path.join(root, 'demo-assets/test-results/data-audit.json');
fs.mkdirSync(path.dirname(output), { recursive: true });
fs.writeFileSync(output, JSON.stringify(audit, null, 2) + '\n');
console.log(JSON.stringify(audit, null, 2));
if (audit.summary.failed) process.exitCode = 1;

