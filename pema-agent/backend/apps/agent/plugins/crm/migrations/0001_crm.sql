-- What the CRM told the agent about the visits of the people it chats with (docs/PLAN-crm-plugin.md 3.4), and the
-- marks of reminders already sent. State, not history: a row holds the latest version the CRM sent, so a late, a
-- repeated or a missed event cannot leave it wrong. Runs in schema agent_rt (agent db migrate-plugins); every row
-- is scoped by tenant and agent.

CREATE TABLE crm_reminder (
    tenant_id text NOT NULL,
    agent text NOT NULL,
    appointment_id uuid NOT NULL,
    channel text NOT NULL,
    external_id text NOT NULL,
    starts_at timestamptz NOT NULL,
    duration_min integer NOT NULL,
    status text NOT NULL,
    version integer NOT NULL,
    -- when the time was last set (booked or moved); a status change alone (confirmed, cancelled) keeps it
    changed_at timestamptz NOT NULL,
    actor_type text NOT NULL,
    last_event_id uuid NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, agent, appointment_id)
);

CREATE INDEX crm_reminder_upcoming ON crm_reminder (tenant_id, agent, starts_at)
    WHERE status IN ('booked', 'confirmed');

-- One row per person of a chat: their consent to reminders (newest wins) and, once known, the chat to write to.
CREATE TABLE crm_person (
    tenant_id text NOT NULL,
    agent text NOT NULL,
    channel text NOT NULL,
    external_id text NOT NULL,
    messages_consent boolean,
    consent_at timestamptz,
    conversation_id text,
    PRIMARY KEY (tenant_id, agent, channel, external_id)
);

-- The unique key that stops a reminder going out twice: written before the message is sent.
CREATE TABLE crm_reminder_sent (
    tenant_id text NOT NULL,
    agent text NOT NULL,
    appointment_id uuid NOT NULL,
    starts_at timestamptz NOT NULL,
    mark text NOT NULL,
    sent_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, agent, appointment_id, starts_at, mark)
);
