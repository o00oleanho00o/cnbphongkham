-- No query reads the marks sent per person any more: the daily cap is the case engine's (docs/PLAN-case-loop.md 6).
DROP INDEX IF EXISTS crm_reminder_sent_person;
