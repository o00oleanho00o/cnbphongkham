# AI roadmap — trợ lý có kiểm soát

| Feature | Demo now | Pilot next | Guardrail |
|---|---:|---:|---|
| Pre-visit brief | Yes | Yes | Cite timeline events; doctor approve/edit. |
| Clinical note draft | Yes | Yes | Draft only; no auto-sign; audit prompt/source. |
| Timeline summary | Yes | Yes | Date-bounded, event-linked, show uncertainty. |
| Follow-up/missing-data detection | Yes | Yes | Rule-first; staff triage; no silent close. |
| Ask Pema | Yes (dataset) | Soon | Role-filtered retrieval, evidence rows, no diagnosis. |
| Before/after assistance | Simulate alignment | Validate | Suggest matching views only; no efficacy/diagnosis claim. |
| Autonomous diagnosis/treatment | No | No | Requires separate clinical validation/regulatory path. |

AI UI must say `Bản nháp — bác sĩ duyệt`, include generatedAt/model/version, source event links, and correction feedback. Log accepted/rejected output for evaluation.

## Evaluation before real-patient pilot

Use 30–50 consented/appropriately de-identified episodes with clinician-authored reference summaries after local privacy review. For each AI brief measure omitted critical events, invented facts, date/session errors and editing time. A clinician should label severity and reject unsafe output; acceptance rates alone are insufficient.

For rule-based follow-up detection, test overdue dates, no-show, already-resolved items, aftercare missing, duplicate patient photos and timezone boundaries. For Ask Pema, display record IDs, denominator and date filter; unsupported questions must say the demo cannot answer, not invent a number.

Go/no-go proposal: no unresolved critical omission/hallucination in the bounded validation set, visible source links, audit of approval/correction, and measured time saved. This is a product validation gate, not proof of clinical efficacy. Image analysis and autonomous diagnosis remain outside this gate and outside V1.
