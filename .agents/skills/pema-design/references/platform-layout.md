# Platform-specific layout

## Clinic Web

Standard 1920×1020 CSS pixels, 100% zoom (content viewport, not the machine's full screen). Use available horizontal space; do not set max-width 920/1050px for the entire workspace. Split context and content columns, keeping readable text line length instead of stretching every paragraph across the screen.

Calendar: compact header/filters, one-row statistics when there is enough room, resource area sized to available height. Tables/calendars may scroll internally; the document must not overflow horizontally. Patient 360 balances timeline/context; instructions have action/handoff columns; services/doctors may use 4 columns from 1600px as the current layout does. This is a pattern to choose by content, not a rule forcing every screen into a 4-column grid.

Also check 1440×900, 1280×720, 1024×768, 390×844. On small screens, prioritize essential information/actions, compact disclosure/filters, and clear scroll containers. Do not shrink the whole page font or hide business controls to fix overflow.

## Patient Mobile web

App shell follows the viewport; header/navigation and scrollable content do not overlap; leave bottom safe area. Home shows the nearest appointment, next care step, and a few shortcuts; full history lives in "Hành trình" (Journey) / child screens. Use progressive disclosure/load more when needed; do not build the whole timeline/images/orders as one long vertical home page.

Current review breakpoints are 360×800, 375×667, 390×844. Test interactions when the keyboard is open and content is long; browser resize is not a substitute for real device evidence.

## Flutter native template

Material 3, SafeArea, Navigator/Back, date picker, scrollable forms; sheets are for short decisions. Long forms or multi-line reviews need their own screen. Preserve data when validation fails; the keyboard must not cover the CTA/current field. Keep 48 logical pixel touch targets and check text scaling; no fixed heights that clip Vietnamese.

The review shell supports 360×800, 390×844, 430×932, 768×1024. Current widget tests use widths 360/390/430/768 but **all have height 844**, so they do not prove all frames above were tested. Android/iOS physical devices, system safe area, keyboard, gestures, and accessibility need separate evidence when scope requires it.

Tablet may increase columns/width sensibly but must not become a miniature desktop dashboard. Do not force a fixed number of cards if long text/data breaks usability.

## Targeted screenshot review

Check in order: patient/task orientation → content hierarchy → spacing/alignment → text/icon/contrast → length/scroll → state/navigation/CTA. Capture before/after in the same viewport and state when comparing. Every comment must identify the issue, the impact on operation, and the fix; avoid generic comments like “not modern enough”. After fixing, test click/validation too, not only a polished empty screenshot.


CSKH (customer care) native: show only status, search, the "Lọc" button, and the customer list on the main screen. Place D1/D3/D7/revisit/90/180 days/birthday groups in a scrollable sheet; show only the currently selected group chip. Avoid 10 wrapping chips pushing the first customer out of the viewport. Test filtering and status changes, beyond static screenshots.
