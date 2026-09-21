# PEMA DIGITAL CLINIC — SINGLE ULTRA SECTION MASTER PROMPT

## ROLE

You are the product discovery, domain research, healthcare workflow, UX architecture,
technical architecture, and prototype lead for **Pema Digital Clinic**.

This is ONE single Ultra section. Do not split into separate independent sections.
Work end-to-end in one continuous run.

Your mission is not to maximize code volume.
Your mission is to produce the strongest possible product understanding, research,
architecture, and interactive demo for a real dermatology/aesthetic clinic in Vietnam.

---

# 0. PROJECT CONTEXT

Pema is a real dermatology/aesthetic clinic in Vietnam.

The clinic owner, Dr. Tâm, is a practicing dermatologist and has explicitly proposed:
- both sides cooperate to build the system first,
- validate it inside the real clinic,
- then commercialize it.

The software team has strong software engineering and AI capability.

Pema currently uses / has experience with existing clinic management software.
One relevant vendor is VTTech:
https://annam.vttechsolution.vn/

The important observation is:

> Existing clinic software may look feature-rich and professional, but real clinic staff
> still complain that it lacks important functions and does not truly understand how the
> clinic works.

This is the product opportunity.

We are NOT trying to build another generic clinic ERP.

Long-term thesis:

Pema real clinic
→ deeply understand real workflows
→ Pema Digital Clinic
→ patient-facing mobile experience
→ structured longitudinal clinical dataset
→ useful AI
→ reusable dermatology/aesthetic clinic platform
→ commercialization

The first system should be built for Pema,
but the architecture must avoid hard-coding Pema-specific behavior into the reusable core.

---

# 1. PRODUCT PRINCIPLES

Follow these principles throughout the work.

## 1.1 Clinic-first, not ERP-first

Do not begin from accounting, warehouse, HR, generic CRM, or a generic admin template.

Begin from:
- patient journey,
- medical/clinical workflow,
- treatment journey,
- before/after photography,
- follow-up,
- doctor context,
- clinic staff workflow,
- patient experience.

## 1.2 Understand the real workflow before building

A large feature checklist is not product understanding.

Find:
- where staff leave the software and use Excel/Zalo/paper,
- where data is entered twice,
- what doctors cannot see quickly,
- what owners cannot measure,
- what patients repeatedly ask,
- what breaks across multi-session treatment,
- where photos become disconnected from the clinical timeline.

## 1.3 Patient longitudinal history is the center

The system must make it easy to understand:

What happened to this patient?
Why?
What was done?
How did they respond?
What changed?
What is next?

This should be understandable in seconds.

## 1.4 AI should assist, not pretend to replace doctors

Do NOT make autonomous diagnosis the centerpiece.

Prioritize:
- pre-visit summaries,
- clinical note drafting,
- timeline summarization,
- follow-up detection,
- missing-data detection,
- image progress assistance,
- natural-language clinic analytics.

Clinically relevant AI output must be doctor-reviewed.

## 1.5 Mobile patient experience is a first-class product

Do NOT make the patient app a shrunk-down admin UI.

The patient should feel:

> “Pema remembers my entire treatment journey.”

## 1.6 Build a demo that can be shown to Dr. Tâm

The result must be understandable in a 10-minute live demo.

It should feel like a plausible product,
not a wireframe dump or generic dashboard template.

---

# 2. RESEARCH FIRST

Before designing or coding, conduct deep research.

Use current public information from the web.

Research:
1. dermatology practice management software,
2. dermatology EMR/EHR,
3. aesthetic clinic / medspa software,
4. patient portals and mobile apps,
5. clinical photography and before/after systems,
6. AI medical scribe,
7. AI-assisted dermatology workflows,
8. treatment planning and follow-up,
9. Vietnamese clinic management software,
10. real user complaints and reviews.

Study strong products such as, but do not limit yourself to:
- ModMed
- Nextech
- Aesthetic Record
- PatientNow
- Pabau
- Zenoti
- Canfield / VISIA
- Skin Analytics
- other products you discover
- VTTech / Vietnamese competitors

For every important product, do not stop at marketing pages.

Look for:
- product docs,
- help centers,
- demos,
- YouTube walkthroughs,
- user reviews,
- Reddit/community discussion,
- clinic staff complaints,
- app reviews when useful.

Research specifically:
- what clinicians love,
- what clinicians hate,
- receptionist friction,
- nurse/assistant friction,
- patient friction,
- owner/manager blind spots,
- repeated manual work,
- workflow gaps,
- data fragmentation,
- multi-session treatment problems,
- photo/document management problems,
- generic-system failures in specialist clinics.

Produce a clear answer to:

### A. TOP 10 UNSOLVED OR POORLY SOLVED PROBLEMS

### B. TOP 10 PRODUCT OPPORTUNITIES FOR PEMA

### C. WHAT NOT TO BUILD

### D. WHICH EXISTING SYSTEMS / FEATURES WE SHOULD COPY, INTEGRATE, OR BUY INSTEAD OF REBUILDING

Keep citations/links inside research documents.

---

# 3. UNDERSTAND THE DERMATOLOGY / AESTHETIC DOMAIN

Model a realistic patient journey:

Lead / referral
→ booking
→ reception
→ consultation
→ clinical assessment
→ diagnosis / problem list
→ treatment plan
→ procedure / treatment session
→ medication / home care
→ clinical photography
→ post-treatment follow-up
→ complications / reactions if any
→ progress assessment
→ next session
→ re-examination
→ long-term history

Model both:
- medical dermatology,
- aesthetic dermatology / multi-session treatment.

Think deeply about domain entities and relationships.

At minimum investigate:

Patient
PatientProfile
EpisodeOfCare
Condition
Concern
Assessment
Diagnosis
TreatmentPlan
TreatmentPlanItem
TreatmentSession
Procedure
Device
DeviceSettings
Medication
Prescription
HomeCareInstruction
ClinicalImage
ImageSet
BodyArea
FollowUp
PatientReportedOutcome
Appointment
Visit
Consent
Document
Invoice
Payment
Package
Communication
Task
Staff
Doctor
AuditLog

Do not assume all of these must become database tables.
First understand the domain.

Important design question:

How should the system represent a multi-month treatment journey
so that both a doctor and an AI can understand it later?

Create a domain model and explain the main design decisions.

---

# 4. DISCOVERY QUESTIONS FOR PEMA

Create a practical workshop questionnaire for a future on-site session at Pema.

Organize by role:
- clinic owner,
- doctor,
- receptionist,
- nurse/assistant,
- customer care,
- cashier/accounting,
- patient.

Questions should uncover real workflow, not just ask “what features do you want?”

Examples of the style:

- What is the last thing you do before a patient enters the doctor room?
- Which information do you usually ask another person for?
- What do you still write on paper or send through Zalo?
- What information is often missing when a patient returns?
- Which part of the current software do staff avoid using?
- What takes the most clicks?
- When a patient complains after treatment, how do you reconstruct what happened?
- How do you compare images over time today?
- How do you know which patient should have returned but did not?
- What report does management currently build manually?

Produce:
PEMA_DISCOVERY_WORKSHOP.md

This document should be directly usable in a real clinic workshop.

---

# 5. PRODUCT SCOPE

Design Pema Digital Clinic in layers.

## Layer 1 — Pema Clinic

Focus on the minimum set that can become genuinely better than the current workflow.

Prioritize:

1. Clinic Dashboard
2. Today / Reception
3. Patient 360
4. Consultation
5. Treatment Plan
6. Treatment Session
7. Clinical Photography / Before & After
8. Follow-up Inbox
9. Search
10. Basic billing context only where needed for the workflow

Do NOT prioritize:
- deep accounting,
- generic HR,
- huge warehouse/ERP scope,
- hundreds of reports,
- irrelevant enterprise modules.

## Layer 2 — Pema Patient

Design a mobile-first patient experience.

Main areas:
- Home
- My appointments
- My treatment journey
- Treatment progress
- Before / after
- Aftercare instructions
- Medication / products
- Send photo / update
- Messages
- Documents / invoices
- Profile

Core experience:

Patient receives treatment
→ goes home
→ opens Pema
→ sees aftercare
→ receives follow-up reminder
→ sends a skin photo
→ clinic reviews it
→ doctor / staff responds
→ next appointment is scheduled

The mobile experience should feel premium and extremely easy.

## Layer 3 — Pema AI

Prioritize practical AI:

1. Pre-visit patient brief
2. Clinical note draft / AI scribe
3. Timeline summarization
4. Follow-up detection
5. Missing-data / missing-photo detection
6. Before-after assistance
7. Natural-language clinic analytics (“Ask Pema”)
8. Patient message drafting
9. Treatment journey summarization

Clearly separate:
- demoable now,
- technically feasible soon,
- requires strong clinical validation,
- should not be attempted yet.

---

# 6. HERO PRODUCT EXPERIENCES

Design these very carefully.

## 6.1 PATIENT 360 — HERO SCREEN

This is the most important clinic screen.

A doctor opening a patient should understand within seconds:

- who this patient is,
- key skin concerns,
- major diagnoses / assessments,
- current treatment plan,
- what was done recently,
- how the patient responded,
- latest clinical photos,
- current medications / home care,
- pending follow-up,
- next appointment,
- important alerts.

Use a longitudinal timeline.

Avoid giant forms.

The timeline should connect:
consultation
→ photos
→ procedure
→ medication
→ patient report
→ follow-up
→ progress
→ next action.

## 6.2 BEFORE / AFTER STUDIO

Design a clinically useful photography experience.

Consider:
- consistent body/face region,
- standardized views,
- capture date,
- treatment stage,
- side-by-side,
- slider comparison,
- annotation,
- zoom,
- image sets,
- privacy,
- consent,
- progress over time.

AI may assist with:
- alignment,
- area matching,
- change highlighting,
- measurement suggestions,

but must not falsely claim medical diagnosis.

## 6.3 TODAY / RECEPTION

Reception must immediately understand:
- who is coming,
- who arrived,
- who is waiting,
- which doctor,
- which treatment,
- missing forms / photos / payment / consent,
- what is delayed.

Optimize for operational speed.

## 6.4 FOLLOW-UP INBOX

Create a unified follow-up queue:
- patient sent image,
- patient reported symptoms,
- aftercare check,
- overdue follow-up,
- doctor review needed,
- staff can resolve / escalate.

This can become a major differentiator.

---

# 7. PROTOTYPE REQUIREMENT

Create a polished interactive prototype.

Use a web stack that can run locally with simple commands.
Choose the stack pragmatically.

Recommended:
- React / Next.js / Vite
- responsive UI
- local mock data
- no complex infrastructure required for the demo

Do not spend the run building production backend complexity.

The goal is:
- product learning,
- realistic interaction,
- high-quality demo.

Create TWO connected experiences:

## A. CLINIC WEB

Desktop-first but responsive.

Screens:
- Dashboard
- Today / Reception
- Patient Search
- Patient 360
- Consultation
- Treatment Plan
- Treatment Session
- Before/After Studio
- Follow-up Inbox

## B. PATIENT MOBILE

Mobile-first PWA/web app.

Screens:
- Home
- Appointments
- Treatment Journey
- Progress / Photos
- Aftercare
- Medication
- Send Update
- Messages
- Documents
- Profile

Make the two demos share the same fake patient dataset when possible.

Example demo flow:

Clinic creates/updates treatment
→ patient app immediately reflects it
→ patient submits follow-up photo
→ clinic Follow-up Inbox receives it
→ clinician reviews it
→ Patient 360 timeline updates.

Even if implemented locally with mock state, the interaction should feel coherent.

---

# 8. DEMO DATA

Generate realistic Vietnamese fake data.

At minimum:
- 30 patients
- multiple ages
- acne
- melasma / pigmentation
- post-inflammatory hyperpigmentation
- rosacea-like redness
- scar treatment
- cosmetic laser / peel / injectables where appropriate
- multi-session treatment plans
- appointments
- procedures
- medication / skincare instructions
- follow-ups
- invoices / payments at a light level
- clinical photo placeholders

Never use real patient data.

Create enough variation to test the workflow.

---

# 9. AI DEMO

Implement or simulate the following AI experiences in a believable way.

## 9.1 Pre-Visit Brief

Example:

“Patient returns after 28 days.
Currently on session 3/5 of pigmentation treatment.
After the previous session, redness lasted 2 days.
No severe reaction reported.
Patient submitted one photo 7 days ago.
Next planned step: reassessment before session 4.”

## 9.2 Clinical Note Draft

Provide a UI where the doctor can:
- enter short notes or mock transcript,
- generate a draft,
- review/edit,
- approve.

Do not claim autonomous medical accuracy.

## 9.3 Follow-Up Detection

Examples:
- patients overdue for follow-up,
- patient submitted image but no one reviewed,
- no photo captured at expected milestone,
- treatment session complete but aftercare not sent.

## 9.4 Ask Pema

Example questions:
- “Which pigmentation patients are overdue for follow-up?”
- “How many treatment plans were started this month?”
- “Which patients submitted photos after laser treatment?”
- “Show patients with more than 30 days since last visit.”

Natural-language analytics can be simulated using the demo dataset if necessary.

---

# 10. COMMERCIALIZATION THINKING

The first version is for Pema,
but we want the option to commercialize later.

Analyze:

## What belongs in reusable core?
Examples:
- patient timeline,
- appointments,
- clinical photography,
- treatment plans,
- follow-up,
- messaging,
- patient portal,
- permissions,
- audit.

## What should be configurable?
Examples:
- treatment templates,
- clinic branding,
- workflow states,
- forms,
- consent templates,
- image protocols,
- notification templates,
- service catalog.

## What may be Pema-specific?
Identify these explicitly.

Also analyze:
- SaaS vs per-clinic deployment
- tenant isolation
- data ownership
- Vietnam healthcare/privacy considerations
- backup/audit
- integrations
- Zalo
- SMS
- e-invoice
- payments
- future mobile apps
- AI model strategy

Do not over-engineer, but document architecture choices that avoid a dead end.

---

# 11. COMPETITOR TEARDOWN

Create a compact but useful comparison.

Do NOT simply count features.

Compare systems on:

- clinic workflow depth
- dermatology specialization
- treatment journey
- photography
- patient experience
- follow-up
- doctor context
- operational speed
- customization
- AI assistance
- analytics
- perceived complexity
- common complaints

For VTTech specifically, investigate public information available about:
- clinic workflow,
- patient management,
- dermatology support,
- appointment,
- treatment,
- CRM,
- Zalo / patient interaction,
- mobile / mini app,
- AI or automation.

Answer:

> Why can a system look very complete while clinic staff still feel
> “it lacks features” or “it does not understand the clinic”?

Develop evidence-based hypotheses.

---

# 12. CRITIQUE LOOP

Do not accept the first prototype.

After initial implementation:

1. Run the app.
2. Exercise the main workflows.
3. Capture screenshots of all key screens.
4. Review them critically.
5. Identify:
   - generic admin-template look,
   - wasted space,
   - weak information hierarchy,
   - unnecessary clicks,
   - unclear clinical context,
   - mobile friction,
   - fake or meaningless metrics,
   - broken flows,
   - inconsistent data.
6. Redesign weak screens.
7. Re-run the main flow.
8. Capture final screenshots.

The UI should feel modern and premium,
but usability and domain clarity matter more than visual decoration.

---

# 13. PERSONA SIMULATION

Create and test these personas:

- Clinic owner
- Dermatologist
- Nurse / treatment assistant
- Receptionist
- Customer care
- New patient
- Long-term patient

For each persona:
- define goals,
- define frequent tasks,
- define pain points,
- walk through the prototype,
- record friction,
- recommend changes.

At minimum simulate:
- 5 clinic staff personas,
- 5 patient scenarios,
- 30 fake patients in the dataset.

---

# 14. REQUIRED DELIVERABLES

Create the following structure:

/docs
  00_EXECUTIVE_SUMMARY.md
  01_MARKET_RESEARCH.md
  02_COMPETITOR_GAPS.md
  03_TOP_10_PROBLEMS.md
  04_PRODUCT_OPPORTUNITIES.md
  05_PEMA_DISCOVERY_WORKSHOP.md
  06_CLINIC_WORKFLOW.md
  07_DOMAIN_MODEL.md
  08_PRODUCT_SCOPE_V1.md
  09_PATIENT_APP.md
  10_AI_ROADMAP.md
  11_COMMERCIALIZATION.md
  12_TECH_ARCHITECTURE.md
  13_SECURITY_PRIVACY_NOTES.md
  14_PERSONA_TESTING.md
  15_UX_CRITIQUE.md
  16_DEMO_SCRIPT.md
  17_WHAT_NOT_TO_BUILD.md

/prototype
  /clinic-web
  /patient-mobile

/demo-assets
  screenshots/
  demo-data/
  optional-video-or-gif-notes/

/research
  sources.md
  competitor-notes/
  complaint-notes/

README.md

---

# 15. EXECUTIVE SUMMARY MUST ANSWER THESE QUESTIONS

The final executive summary must answer concisely:

1. Why should we build this at all?
2. Why are existing systems still unsatisfactory to real clinics?
3. What is the strongest product wedge for Pema?
4. What should Pema Digital Clinic v1 include?
5. What should it deliberately exclude?
6. Why is Patient 360 important?
7. Why is the patient app important?
8. Which AI features are practical now?
9. What can become defensible after 1–3 years of real clinic usage?
10. What must we learn from Pema before commercializing?
11. What are the biggest risks?
12. What should we demo to Dr. Tâm first?

---

# 16. 10-MINUTE DEMO SCRIPT

Create a polished 10-minute demonstration.

Suggested flow:

1. Clinic Dashboard
2. Today / Reception
3. Open one patient
4. Understand entire history from Patient 360
5. Open treatment plan
6. Compare before/after photos
7. Record a new treatment session
8. Switch to patient mobile
9. Patient sees treatment + aftercare
10. Patient sends follow-up image
11. Return to clinic Follow-up Inbox
12. AI generates a patient summary
13. Show “Ask Pema”

The script should say:
- what to click,
- what to explain,
- why it matters.

---

# 17. DEFINITION OF DONE

Do not stop at documents.

The section is complete only when:

- research exists,
- competitor gaps are documented,
- clinic workflow is modeled,
- domain model exists,
- discovery workshop exists,
- clinic prototype runs,
- patient mobile prototype runs,
- realistic demo data exists,
- main cross-app flow works,
- screenshots are captured,
- first UI version is critiqued,
- weak screens are improved,
- demo script exists,
- README explains exactly how to run everything.

If some part cannot be completed,
document precisely:
- what failed,
- why,
- what remains,
- how to continue.

---

# 18. IMPORTANT EXECUTION RULES

- Research first.
- Do not blindly copy competitors.
- Do not build a generic ERP.
- Do not optimize for code volume.
- Do not overbuild backend infrastructure.
- Do not use real patient data.
- Use Vietnamese UI for the prototype.
- Technical documentation may be English or Vietnamese, but executive/product docs should be understandable to Vietnamese stakeholders.
- Prefer working software and evidence over speculative architecture.
- Cite external research sources.
- Save screenshots as evidence.
- Keep the prototype easy to run locally.
- If you discover a better product direction during research, update the design rather than following this prompt mechanically.

Most importantly:

> The goal is not to prove that we can code a clinic system.
> The goal is to discover how to build a system that a real dermatology clinic
> actually prefers to use — starting with Pema — and which can later become a product.

Start now.
