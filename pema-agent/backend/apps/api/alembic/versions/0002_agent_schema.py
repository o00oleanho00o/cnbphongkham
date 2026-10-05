"""agent schema: the engine tables of the zalo-agent port, now multi-tenant on Postgres.

Mapping from the SQLite tables of zalo-agent (src/conversation/database.ts, knowledge/kb-schema.ts,
mcp/mcp-schema.ts, conversation/friend-schema.ts):

====================  ===========================  ==============================================
zalo-agent            here (schema agent)          notes
====================  ===========================  ==============================================
accounts              accounts                     + policy_profile, encrypted credentials
agents                agents                       + policy_profile
threads               threads                      summary, context_epoch kept
messages              history                      the LLM context store (NOT the Inbox of record)
memories              memories                     asymmetric learned_in_group rule kept
contacts              contacts
image_descriptions    image_descriptions
agent_turns           usage                        token accounting per turn
agent_steps           usage_steps                  trace of every step
scheduled_jobs        jobs                         + dedupe_key, patient_id, origin; delivery_attempts
scheduled_job_runs    job_runs
proactive_send_..     proactive_send_counters      keyed by scope_key (account:thread or patient:account)
kb_sources            kb_document                  + approved_by_clinical_owner
kb_chunks (+fts5)     kb_chunk                     tsvector (diacritics folded) + vector(1024) bge-m3
agent_kb_sources      agent_kb_document            default-deny binding
mcp_servers           mcp_servers                  headers encrypted
agent_mcp_servers     agent_mcp_servers            default-deny binding
friend_requests       friend_requests
runtime_settings      runtime_settings             tuning + LLM overrides (secrets encrypted by the app)
dashboard_sessions    (dropped)                    replaced by the JWT session of the API
(new)                 channel_update_seen          update_id de-duplication for webhooks
====================  ===========================  ==============================================

Security: every table has ``clinic_id`` and the same RLS policy as ``clinic.*``. Both runtime roles
(``be_app`` for the admin API, ``agent_worker`` for turns, scheduler, ingest) get DML on ``agent.*``;
``agent_worker`` gets nothing on ``clinic.*`` (see 0003). Text ids are the original kebab/hex ids, unique
per clinic (primary key ``(clinic_id, id)``).

Revision ID: 0002_agent_schema
Revises: 0001_clinic_schema
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_agent_schema"
down_revision = "0001_clinic_schema"
branch_labels = None
depends_on = None

EMBEDDING_DIMENSIONS = 1024  # bge-m3; keep equal to pema_contracts.knowledge.KB_EMBEDDING_DIMENSIONS

TABLES = (
    "runtime_settings",
    "agents",
    "accounts",
    "threads",
    "history",
    "contacts",
    "memories",
    "image_descriptions",
    "friend_requests",
    "usage",
    "usage_steps",
    "jobs",
    "job_runs",
    "proactive_send_counters",
    "kb_document",
    "kb_chunk",
    "agent_kb_document",
    "mcp_servers",
    "agent_mcp_servers",
    "channel_update_seen",
)


def _sql(statement: str) -> None:
    op.execute(sa.text(statement))


def upgrade() -> None:
    _sql("CREATE EXTENSION IF NOT EXISTS vector")
    _sql("CREATE SCHEMA agent")
    _sql("REVOKE ALL ON SCHEMA agent FROM PUBLIC")

    _sql("""
        CREATE FUNCTION agent.touch_updated_at() RETURNS trigger LANGUAGE plpgsql AS
        $$ BEGIN NEW.updated_at = now(); RETURN NEW; END $$""")

    # ---------------------------------------------------------------- settings, agents, accounts
    _sql("""
        CREATE TABLE agent.runtime_settings (
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            key text NOT NULL,
            value text NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (clinic_id, key)
        )""")
    _sql("""
        CREATE TABLE agent.agents (
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            id text NOT NULL CHECK (id ~ '^[a-z0-9][a-z0-9-]*$'),
            icon text NOT NULL DEFAULT '🤖',
            name text NOT NULL,
            persona text NOT NULL DEFAULT '',
            model_provider text CHECK (model_provider IN ('openai-compatible', 'anthropic', 'google')),
            model_name text,
            max_steps integer CHECK (max_steps >= 1),
            reasoning_effort text CHECK (reasoning_effort IN ('off', 'low', 'medium', 'high', 'xhigh')),
            disabled_tools jsonb NOT NULL DEFAULT '[]'::jsonb,
            context_window integer CHECK (context_window >= 1000),
            is_default boolean NOT NULL DEFAULT false,
            policy_profile text NOT NULL DEFAULT 'patient_channel'
                CHECK (policy_profile IN ('staff_assistant', 'patient_channel')),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (clinic_id, id)
        )""")
    _sql("CREATE UNIQUE INDEX agents_one_default_idx ON agent.agents (clinic_id) WHERE is_default")
    _sql("""
        CREATE TABLE agent.accounts (
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            id text NOT NULL CHECK (id ~ '^[a-z0-9][a-z0-9-]*$'),
            label text NOT NULL,
            channel text NOT NULL DEFAULT 'zalo_personal'
                CHECK (channel IN ('zalo_bot', 'zalo_personal', 'zalo_oa')),
            enabled boolean NOT NULL DEFAULT true,
            agent_id text NOT NULL,
            allowlist_mode text NOT NULL DEFAULT 'all' CHECK (allowlist_mode IN ('all', 'list')),
            allowlist_user_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
            group_require_mention boolean NOT NULL DEFAULT true,
            respond_to_groups boolean NOT NULL DEFAULT true,
            group_passive_listen boolean NOT NULL DEFAULT true,
            auto_react_enabled boolean NOT NULL DEFAULT true,
            auto_react_icon text NOT NULL DEFAULT 'heart',
            typing_indicator_enabled boolean NOT NULL DEFAULT true,
            disabled_tools jsonb NOT NULL DEFAULT '[]'::jsonb,
            auto_accept_friends boolean NOT NULL DEFAULT false,
            auto_accept_friend_delay_minutes integer NOT NULL DEFAULT 1
                CHECK (auto_accept_friend_delay_minutes BETWEEN 0 AND 1440),
            policy_profile text NOT NULL DEFAULT 'patient_channel'
                CHECK (policy_profile IN ('staff_assistant', 'patient_channel')),
            bot_token_enc text NOT NULL DEFAULT '',
            credential_enc text NOT NULL DEFAULT '',
            webhook_secret_enc text NOT NULL DEFAULT '',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (clinic_id, id),
            FOREIGN KEY (clinic_id, agent_id) REFERENCES agent.agents (clinic_id, id)
        )""")

    # ---------------------------------------------------------------- conversation context
    _sql("""
        CREATE TABLE agent.threads (
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            account_id text NOT NULL,
            thread_id text NOT NULL,
            thread_type integer NOT NULL,
            display_name text NOT NULL DEFAULT '',
            bot_enabled boolean NOT NULL DEFAULT true,
            message_count integer NOT NULL DEFAULT 0,
            last_message_at timestamptz,
            last_sender_name text,
            summary text NOT NULL DEFAULT '',
            summary_covers_to_message_id bigint NOT NULL DEFAULT 0,
            context_epoch integer NOT NULL DEFAULT 0,
            PRIMARY KEY (clinic_id, account_id, thread_id),
            FOREIGN KEY (clinic_id, account_id) REFERENCES agent.accounts (clinic_id, id) ON DELETE CASCADE
        )""")
    _sql("CREATE INDEX threads_recent_idx ON agent.threads (clinic_id, last_message_at DESC)")
    _sql("""
        CREATE TABLE agent.history (
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            account_id text NOT NULL,
            thread_id text NOT NULL,
            role text NOT NULL CHECK (role IN ('user', 'assistant')),
            sender_name text,
            sender_id text,
            content text NOT NULL,
            images jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        )""")
    _sql("CREATE INDEX history_thread_idx ON agent.history (clinic_id, account_id, thread_id, id)")
    _sql("""
        CREATE TABLE agent.contacts (
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            account_id text NOT NULL,
            user_id text NOT NULL,
            display_name text NOT NULL DEFAULT '',
            first_seen timestamptz NOT NULL DEFAULT now(),
            last_seen timestamptz NOT NULL DEFAULT now(),
            message_count integer NOT NULL DEFAULT 0,
            PRIMARY KEY (clinic_id, account_id, user_id)
        )""")
    _sql("""
        CREATE TABLE agent.memories (
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            account_id text NOT NULL,
            subject_id text NOT NULL,
            content text NOT NULL,
            learned_in_thread_id text NOT NULL,
            learned_in_group boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now()
        )""")
    _sql("CREATE INDEX memories_subject_idx ON agent.memories (clinic_id, account_id, subject_id, id)")
    _sql("""
        CREATE TABLE agent.image_descriptions (
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            rel_path text NOT NULL,
            description text NOT NULL,
            model text NOT NULL DEFAULT '',
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (clinic_id, rel_path)
        )""")
    _sql("""
        CREATE TABLE agent.friend_requests (
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            account_id text NOT NULL,
            from_uid text NOT NULL,
            message text NOT NULL DEFAULT '',
            sender_name text,
            avatar_url text,
            received_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (clinic_id, account_id, from_uid)
        )""")

    # ---------------------------------------------------------------- usage and trace
    _sql("""
        CREATE TABLE agent.usage (
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            account_id text NOT NULL,
            thread_id text NOT NULL,
            source text NOT NULL DEFAULT 'message' CHECK (source IN ('message', 'schedule')),
            input_tokens integer NOT NULL DEFAULT 0,
            output_tokens integer NOT NULL DEFAULT 0,
            total_tokens integer NOT NULL DEFAULT 0,
            steps integer NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (clinic_id, id)
        )""")
    _sql("CREATE INDEX usage_account_created_idx ON agent.usage (clinic_id, account_id, created_at)")
    _sql("""
        CREATE TABLE agent.usage_steps (
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            turn_id bigint NOT NULL,
            step_number integer NOT NULL,
            attempt integer NOT NULL DEFAULT 1,
            text text NOT NULL DEFAULT '',
            reasoning text NOT NULL DEFAULT '',
            tool_calls jsonb NOT NULL DEFAULT '[]'::jsonb,
            tool_results jsonb NOT NULL DEFAULT '[]'::jsonb,
            tool_errors jsonb NOT NULL DEFAULT '[]'::jsonb,
            finish_reason text NOT NULL DEFAULT '',
            warnings jsonb NOT NULL DEFAULT '[]'::jsonb,
            input_tokens integer NOT NULL DEFAULT 0,
            output_tokens integer NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT now(),
            FOREIGN KEY (clinic_id, turn_id) REFERENCES agent.usage (clinic_id, id) ON DELETE CASCADE
        )""")
    _sql("CREATE INDEX usage_steps_turn_idx ON agent.usage_steps (clinic_id, turn_id, step_number)")
    _sql("CREATE INDEX usage_steps_created_idx ON agent.usage_steps (created_at)")

    # ---------------------------------------------------------------- scheduler
    _sql("""
        CREATE TABLE agent.jobs (
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            id text NOT NULL,
            account_id text NOT NULL,
            thread_id text NOT NULL,
            thread_type integer NOT NULL,
            name text NOT NULL,
            kind text NOT NULL CHECK (kind IN ('message', 'agent')),
            payload text NOT NULL,
            schedule_kind text NOT NULL CHECK (schedule_kind IN ('once', 'every', 'cron')),
            run_at timestamptz,
            every_minutes integer,
            cron_expr text,
            timezone text NOT NULL DEFAULT '',
            enabled boolean NOT NULL DEFAULT true,
            next_run_at timestamptz,
            last_run_at timestamptz,
            last_status text,
            last_error text,
            run_count integer NOT NULL DEFAULT 0,
            max_runs integer,
            delivery_attempts integer NOT NULL DEFAULT 0,
            created_by text NOT NULL DEFAULT '',
            dedupe_key text,
            patient_id uuid,
            origin text NOT NULL DEFAULT 'agent_tool'
                CHECK (origin IN ('agent_tool', 'staff', 'crm_rule', 'system')),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (clinic_id, id),
            CHECK (schedule_kind <> 'once' OR max_runs = 1)
        )""")
    _sql("CREATE INDEX jobs_due_idx ON agent.jobs (clinic_id, enabled, next_run_at)")
    _sql("CREATE INDEX jobs_thread_idx ON agent.jobs (clinic_id, account_id, thread_id)")
    _sql(
        "CREATE UNIQUE INDEX jobs_dedupe_idx ON agent.jobs (clinic_id, dedupe_key) WHERE dedupe_key IS NOT NULL"
    )
    _sql("""
        CREATE TABLE agent.job_runs (
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            job_id text NOT NULL,
            turn_id bigint,
            status text NOT NULL CHECK (status IN ('running', 'ok', 'silent', 'skipped', 'error', 'interrupted')),
            detail text NOT NULL DEFAULT '',
            delivered_chars integer NOT NULL DEFAULT 0,
            started_at timestamptz NOT NULL DEFAULT now(),
            finished_at timestamptz,
            FOREIGN KEY (clinic_id, job_id) REFERENCES agent.jobs (clinic_id, id) ON DELETE CASCADE
        )""")
    _sql("CREATE INDEX job_runs_job_idx ON agent.job_runs (clinic_id, job_id, id DESC)")
    _sql("""
        CREATE TABLE agent.proactive_send_counters (
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            scope_key text NOT NULL,
            day_key text NOT NULL,
            count integer NOT NULL DEFAULT 0 CHECK (count >= 0),
            notice_sent boolean NOT NULL DEFAULT false,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (clinic_id, scope_key, day_key)
        )""")

    # ---------------------------------------------------------------- knowledge base
    _sql("""
        CREATE TABLE agent.kb_document (
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            id text NOT NULL,
            name text NOT NULL,
            kind text NOT NULL CHECK (kind IN ('file', 'text')),
            format text NOT NULL DEFAULT '',
            storage_key text NOT NULL DEFAULT '',
            raw_text text NOT NULL DEFAULT '',
            status text NOT NULL DEFAULT 'cho_xu_ly'
                CHECK (status IN ('cho_xu_ly', 'dang_xu_ly', 'san_sang', 'hong')),
            error text NOT NULL DEFAULT '',
            chunk_count integer NOT NULL DEFAULT 0,
            byte_size integer NOT NULL DEFAULT 0,
            attempts integer NOT NULL DEFAULT 0,
            approved_by_clinical_owner boolean NOT NULL DEFAULT false,
            approved_by uuid,
            approved_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (clinic_id, id)
        )""")
    _sql(f"""
        CREATE TABLE agent.kb_chunk (
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            source_id text NOT NULL,
            ord integer NOT NULL,
            title text NOT NULL DEFAULT '',
            content text NOT NULL,
            folded text NOT NULL,
            tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', folded)) STORED,
            embedding vector({EMBEDDING_DIMENSIONS}),
            FOREIGN KEY (clinic_id, source_id) REFERENCES agent.kb_document (clinic_id, id) ON DELETE CASCADE
        )""")
    _sql("CREATE INDEX kb_chunk_source_idx ON agent.kb_chunk (clinic_id, source_id)")
    _sql("CREATE INDEX kb_chunk_tsv_idx ON agent.kb_chunk USING gin (tsv)")
    _sql("CREATE INDEX kb_chunk_embedding_idx ON agent.kb_chunk USING hnsw (embedding vector_cosine_ops)")
    _sql("""
        CREATE TABLE agent.agent_kb_document (
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            agent_id text NOT NULL,
            source_id text NOT NULL,
            PRIMARY KEY (clinic_id, agent_id, source_id),
            FOREIGN KEY (clinic_id, agent_id) REFERENCES agent.agents (clinic_id, id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, source_id) REFERENCES agent.kb_document (clinic_id, id) ON DELETE CASCADE
        )""")

    # ---------------------------------------------------------------- MCP client
    _sql("""
        CREATE TABLE agent.mcp_servers (
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            id text NOT NULL,
            name text NOT NULL,
            url text NOT NULL,
            headers_enc text NOT NULL DEFAULT '',
            enabled boolean NOT NULL DEFAULT true,
            status text NOT NULL DEFAULT 'cho_ket_noi'
                CHECK (status IN ('cho_ket_noi', 'da_ket_noi', 'loi', 'can_duyet_lai')),
            error text NOT NULL DEFAULT '',
            tools_snapshot jsonb NOT NULL DEFAULT '[]'::jsonb,
            fingerprint text NOT NULL DEFAULT '',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (clinic_id, id)
        )""")
    _sql("""
        CREATE TABLE agent.agent_mcp_servers (
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            agent_id text NOT NULL,
            server_id text NOT NULL,
            PRIMARY KEY (clinic_id, agent_id, server_id),
            FOREIGN KEY (clinic_id, agent_id) REFERENCES agent.agents (clinic_id, id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, server_id) REFERENCES agent.mcp_servers (clinic_id, id) ON DELETE CASCADE
        )""")

    # ---------------------------------------------------------------- webhook de-duplication
    _sql("""
        CREATE TABLE agent.channel_update_seen (
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            account_id text NOT NULL,
            update_id text NOT NULL,
            seen_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (clinic_id, account_id, update_id)
        )""")
    _sql("CREATE INDEX channel_update_seen_age_idx ON agent.channel_update_seen (seen_at)")

    # ---------------------------------------------------------------- updated_at triggers
    for table in ("agents", "accounts", "jobs", "kb_document", "mcp_servers"):
        _sql(
            f"CREATE TRIGGER {table}_touch BEFORE UPDATE ON agent.{table} "
            "FOR EACH ROW EXECUTE FUNCTION agent.touch_updated_at()"
        )

    # ---------------------------------------------------------------- row level security
    for table in TABLES:
        _sql(f"ALTER TABLE agent.{table} ENABLE ROW LEVEL SECURITY")
        _sql(
            f"CREATE POLICY clinic_isolation ON agent.{table} "
            "USING (clinic_id = ctx.current_clinic_id()) "
            "WITH CHECK (clinic_id = ctx.current_clinic_id())"
        )

    # ---------------------------------------------------------------- grants
    _sql("GRANT USAGE ON SCHEMA agent TO be_app, agent_worker")
    _sql("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA agent TO be_app, agent_worker")
    _sql("GRANT USAGE ON ALL SEQUENCES IN SCHEMA agent TO be_app, agent_worker")
    _sql(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA agent GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES "
        "TO be_app, agent_worker"
    )
    _sql("ALTER DEFAULT PRIVILEGES IN SCHEMA agent GRANT USAGE ON SEQUENCES TO be_app, agent_worker")


def downgrade() -> None:
    _sql("DROP SCHEMA IF EXISTS agent CASCADE")
