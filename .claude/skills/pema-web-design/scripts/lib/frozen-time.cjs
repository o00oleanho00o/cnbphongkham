// Preload for the MOCK back end of pema-agent/frontend (never for `next dev`): `node --require frozen-time.cjs`.
//
// The mock builds its fictional data relative to the wall clock (`isoFromNow(-2 * MIN)`), so a reference shot of a
// Next.js screen would show "2 phút trước" today and "3 phút trước" in a minute, and the shots could never be compared
// from one day to the next. This file freezes Date.now() and `new Date()` of the mock process at the inventory clock
// (2026-09-20 09:00 +07, the clock web-shots.cjs also gives the browser), so the data and the browser agree and a
// capture is reproducible. Timers keep running. Nothing of the front end or the mock is edited.
//
//   MOCK_PORT=4480 MOCK_LIVE_PERIOD_MS=0 NODE_OPTIONS="--require <abs path>/frozen-time.cjs" pnpm mock
//
// MOCK_LIVE_PERIOD_MS=0 switches the mock's live-event simulator off (it fires a random refresh every 20 s).
// Side effect to know about: the mock's 5-per-minute limit for staff create/reset never rolls over while the clock is
// frozen, so a run that really POSTs there more than 5 times needs a restart. The capture script answers those calls itself.

const FIXED = Date.parse('2026-09-20T09:00:00+07:00');
const RealDate = Date;

class FrozenDate extends RealDate {
  constructor(...args) {
    if (args.length === 0) super(FIXED);
    else super(...args);
  }

  static now() {
    return FIXED;
  }
}

globalThis.Date = FrozenDate;
