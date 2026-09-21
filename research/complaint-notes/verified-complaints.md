# Verified public complaints and workflow pain evidence (20/09/2026)

## Method and evidence standard

This is a bounded public-web pass. I recorded direct URLs and exact claims where pages were reachable. “Verified” here means the statement is visible on the cited public page; it does **not** mean the researcher independently confirmed the operational frequency or clinical impact. Vendor marketing claims are labelled as such. No login, patient data, or private clinic system was accessed.

## Vietnam: operational pain described publicly

### YouMed / Doctor Workspace article (secondary industry source)

Source: [Phần mềm quản lý phòng khám trong Doctor Workspace](https://youmed.vn/tin-tuc/phan-mem-quan-ly-phong-kham/) (published 16/05/2023; page states updated 18/12/2025).

The article explicitly lists recurring management difficulties:

- **Reception and waiting:** “Tiếp nhận bệnh là một trong những bước chiếm nhiều thời gian của bác sĩ”; for larger clinics, a poorly designed intake process can increase waiting and dissatisfaction.
- **Paper/manual records:** It says most clinics manage records/medical records manually; finding a patient's file takes time and manual storage can lose information or create errors.
- **Excel limitations:** It says some clinics use Microsoft Excel for records, but Excel is not purpose-built for management and lacks strong information-security features.
- **Reporting burden:** Revenue/expense reporting and data analysis can be complex and time-consuming for doctors and staff.
- **Post-visit communication gap:** Doctors often interact with patients only during in-person visits; questions after the visit may wait until the next appointment, reducing continuity.
- **Inventory risk:** Manual stock and expiry tracking can cause over/under-stocking and expiry mistakes.
- **Security concern:** Weak/manual systems can expose medical history and staff personal data, lose important records, and damage patient trust.

These are statements made by YouMed in a product-education/marketing context, so they should be treated as industry pain signals, not an independent prevalence study. They strongly support validating Pema's reception queue, longitudinal timeline, follow-up inbox, inventory boundaries and audit/privacy requirements.

The same article describes Doctor Workspace's advertised countermeasures: cloud records, electronic prescriptions, reports, machine-result connections, booking, patient messaging/video, stock controls and security claims (ISO 27001:2013, HIPAA, VNISA membership and periodic pentesting). This is useful competitor positioning; it is not independent verification of certification or implementation.

## Global review/complaint sources attempted but not verified

The following independent review endpoints were attempted with a normal public HTTP request and were blocked with HTTP 403 in this environment:

- [Capterra — Aesthetic Record reviews](https://www.capterra.com/p/140513/Aesthetic-Record/reviews/) — 403.
- [Software Advice — Pabau reviews](https://www.softwareadvice.com/medical/pabau-profile/reviews/) — 403.
- [Software Advice — Aesthetic Record reviews](https://www.softwareadvice.com/medical/aesthetic-record-profile/reviews/) — 403.
- [GetApp — Pabau reviews](https://www.getapp.com/healthcare-pharmaceuticals-software/a/pabau/reviews/) — 403.
- [G2 — Pabau reviews](https://www.g2.com/products/pabau/reviews) — 403.
- [Trustpilot — Pabau](https://www.trustpilot.com/review/pabau.com) — 403.
- [Trustpilot — Aesthetic Record](https://www.trustpilot.com/review/aestheticrecord.com) — 403.
- Reddit search/API for Pabau, Aesthetic Record, Nextech and PatientNow — HTTP 403 (“Blocked”).

No complaint claim is attributed to these inaccessible pages. The direct public Apple RSS evidence below is a separate accessible source and supports only the specific user-reported issues quoted there.

## Independent App Store review evidence (public RSS)

Apple's public RSS feed was reachable without login. These are user-reported experiences, not an independent technical audit; they are included as complaint signals and should be triangulated in demos/interviews. Feed links expose the app-level review collection and stable review IDs.

### Nextech app (App Store ID 496924413; feed: [Apple RSS](https://itunes.apple.com/us/rss/customerreviews/id=496924413/sortBy=mostRecent/json))

- Review **14075222490**, 1 star, version 3.0.9, updated **2026-05-17**: “Can’t send any prescriptions anymore because you can’t scroll once the acknowledgment comes up.” This is a concrete mobile interaction failure alleged by one reviewer.
- Review **10537027781**, 1 star, version 2.7.8, updated **2023-10-31**: “The photo uploaded is terrible… not robust photo management”; reviewer says camera uploads error, photos sometimes do not save, and they could not see patient photos for a month. This is directly relevant to clinical photography, but remains a single user report.
- Review **9348809887**, 3 stars, version 2.6.1, updated **2022-12-01**: reviewer values remote prescriptions and schedule access but says they cannot schedule appointments from the app. This indicates a mobile workflow gap reported by a user.
- Review **3206441653**, 5 stars, version 1.69, updated **2018-09-19**: positive counter-evidence—reviewer calls the app “invaluable” but says multi-provider schedule visualization was unwieldy. A separate 5-star review **773781974**, version 0.79, dated **2013-03-21**, says iPad photo capture, chart review and in-room notes made seeing patients “easy and fast.” These prevent a one-sided “Nextech is bad” conclusion, although both are historical versions.

The app-level iTunes search result returned average rating **2.72/5 from 83 ratings** for this App Store ID at the time of capture. Ratings are not clinic-wide product quality and may reflect an app subset/version.

### PocketEMA / ModMed app (App Store ID 460369272; feed: [Apple RSS](https://itunes.apple.com/us/rss/customerreviews/id=460369272/sortBy=mostRecent/json))

- Review **14012881430**, 2 stars, version 7.13.3, updated **2026-04-30**: “Underpowered compared to website and main app”; reviewer says the mobile website is difficult to use and leaves no way to view additional data on a phone.
- Review **13568987595**, 1 star, version 7.12.0, updated **2025-12-29**: reviewer says updates have removed functions and the app crashes when adding photos to a chart.
- Review **10593350295**, 3 stars, version 7.3.1, updated **2023-11-16**: reviewer says tasks are essential to their practice but unavailable, and attachments support is limited to photos.
- Review **1862531481**, 4 stars, version 5.6.0, updated **2017-10-20**: positive counter-evidence—reviewer uses the app for intramail, patient lookup and schedule, but still requests task viewing/responding for patient messages/refills.

The app-level iTunes search result returned average rating **2.20/5 from 60 ratings** for this App Store ID at capture time. This is an app signal, not evidence about every ModMed module or customer.

### Design implications for Pema (hypotheses, not vendor verdicts)

Across these independent user reports, recurring themes are: missing mobile actions (appointments/tasks), photo capture/save reliability, interruptions from updates/crashes, and poor multi-provider schedule views. Pema should therefore test: (1) photo upload retry + visible save status; (2) task ownership for patient updates; (3) mobile-first minimum actions rather than a shrunken desktop; (4) graceful offline/error states; and (5) clinic-wide Today view with provider/resource filters.

## What is not verified

- No independent VTTech complaint/review was located or validated in this pass. The login host is not a public review surface.
- No rate, frequency, error metric or patient outcome should be inferred from the YouMed article.
- No claim here establishes that VTTech, YouMed, Pabau, Aesthetic Record, Nextech or PatientNow fails a particular workflow at Pema.

## Interview prompts derived from the evidence

Ask each role to show the last real case rather than give a feature wish-list:

1. Where do receptionists record arrivals, waiting, missing forms/photos/consent and payment today?
2. When a returning patient asks “what did we do last time?”, how many screens, systems or Zalo messages must staff search?
3. Which data is still copied to Excel/paper and why?
4. How are overdue follow-ups detected and assigned? Who owns an unanswered patient photo?
5. How are treatment photos standardized, consented and compared over multiple sessions?
6. What report is assembled manually every week or month?
7. What patient question arrives after the visit, and where is the answer recorded?
