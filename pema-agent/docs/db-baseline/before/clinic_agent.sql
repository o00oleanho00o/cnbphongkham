--
-- PostgreSQL database dump
--

\restrict aUfUrXjbVbGvxVwCnDETCZ0Oga9N7S3nAAynMiMEFJhKbV1hbxfiSby9scyYwsi

-- Dumped from database version 17.11 (Debian 17.11-1.pgdg12+2)
-- Dumped by pg_dump version 17.11 (Debian 17.11-1.pgdg12+2)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: clinic_agent; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA clinic_agent;


--
-- Name: create_review_item(text, text, text, text, uuid, text, jsonb, jsonb, text, text[], text, text); Type: FUNCTION; Schema: clinic_agent; Owner: -
--

CREATE FUNCTION clinic_agent.create_review_item(p_job_id text, p_kind text, p_origin text, p_patient_code text, p_conversation_id uuid, p_draft_text text, p_payload jsonb, p_sources jsonb, p_risk_level text, p_red_flags text[], p_model text, p_prompt_version text) RETURNS uuid
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'clinic', 'ctx', 'pg_temp'
    AS $$
        DECLARE
            v_clinic uuid := ctx.the_clinic_id();
            v_patient uuid;
            v_id uuid;
            v_doctor boolean := (p_risk_level = 'red_flag' OR p_kind = 'triage_alert');
        BEGIN
            IF v_clinic IS NULL THEN RAISE EXCEPTION 'no clinic context'; END IF;
            IF p_job_id IS NULL OR p_job_id = '' THEN RAISE EXCEPTION 'job_id is the idempotency key'; END IF;
            SELECT id INTO v_id FROM clinic.review_item WHERE clinic_id = v_clinic AND job_id = p_job_id;
            IF FOUND THEN RETURN v_id; END IF;
            IF p_patient_code IS NOT NULL THEN
                SELECT id INTO v_patient FROM clinic.patient WHERE clinic_id = v_clinic AND code = p_patient_code;
            END IF;
            INSERT INTO clinic.review_item (clinic_id, kind, origin, conversation_id, patient_id, job_id, draft_text,
                    payload, sources, risk_level, red_flags, requires_doctor, model, prompt_version)
            VALUES (v_clinic, p_kind, p_origin, p_conversation_id, v_patient, p_job_id, p_draft_text,
                    p_payload, COALESCE(p_sources, '[]'::jsonb), p_risk_level, COALESCE(p_red_flags, '{}'), v_doctor,
                    p_model, p_prompt_version)
            RETURNING id INTO v_id;
            IF p_conversation_id IS NOT NULL THEN
                UPDATE clinic.conversation
                   SET status = CASE WHEN v_doctor THEN 'handoff' ELSE 'pending_review' END
                 WHERE clinic_id = v_clinic AND id = p_conversation_id AND status <> 'closed';
            END IF;
            INSERT INTO clinic.audit_log (clinic_id, actor_type, action, entity_type, entity_id, details)
            VALUES (v_clinic, 'agent', 'review_item.create', 'review_item', v_id::text,
                    jsonb_build_object('kind', p_kind, 'origin', p_origin, 'risk_level', p_risk_level,
                                       'has_draft', p_draft_text IS NOT NULL));
            RETURN v_id;
        END $$;


--
-- Name: link_attempts_exceeded(uuid, text, text); Type: FUNCTION; Schema: clinic_agent; Owner: -
--

CREATE FUNCTION clinic_agent.link_attempts_exceeded(p_clinic uuid, p_channel text, p_uid text) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'clinic', 'pg_temp'
    AS $$
            SELECT count(*) >= 5
              FROM clinic.identity_link_attempt a
             WHERE a.clinic_id = p_clinic AND a.channel = p_channel AND a.external_user_id = p_uid
               AND NOT a.succeeded AND a.attempted_at > now() - interval '1 hour'
        $$;


--
-- Name: link_identity_by_phone_hash(text, text, text); Type: FUNCTION; Schema: clinic_agent; Owner: -
--

CREATE FUNCTION clinic_agent.link_identity_by_phone_hash(p_channel text, p_external_user_id text, p_phone_hash text) RETURNS TABLE(outcome text, patient_id uuid, patient_code text, identity_id uuid)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'clinic', 'clinic_agent', 'ctx', 'pg_temp'
    AS $_$
        #variable_conflict use_column
        DECLARE
            v_clinic uuid := ctx.the_clinic_id();
            v_identity clinic.channel_identity%ROWTYPE;
            v_ids uuid[];
            v_codes text[];
            v_n integer;
        BEGIN
            IF v_clinic IS NULL THEN RAISE EXCEPTION 'no clinic context'; END IF;
            IF p_phone_hash IS NULL OR p_phone_hash !~ '^[0-9a-f]{64}$' THEN
                RAISE EXCEPTION 'invalid phone hash';
            END IF;
            IF clinic_agent.link_attempts_exceeded(v_clinic, p_channel, p_external_user_id) THEN
                RETURN QUERY SELECT 'rate_limited'::text, NULL::uuid, NULL::text, NULL::uuid;
                RETURN;
            END IF;

            INSERT INTO clinic.channel_identity (clinic_id, channel, external_user_id, last_inbound_at)
            VALUES (v_clinic, p_channel, p_external_user_id, now())
            ON CONFLICT (clinic_id, channel, external_user_id) DO UPDATE SET last_inbound_at = now()
            RETURNING * INTO v_identity;

            IF v_identity.verification_status = 'verified' THEN
                RETURN QUERY SELECT 'already_verified'::text, v_identity.patient_id,
                    (SELECT pt.code FROM clinic.patient pt
                      WHERE pt.clinic_id = v_clinic AND pt.id = v_identity.patient_id),
                    v_identity.id;
                RETURN;
            END IF;
            IF v_identity.verification_status = 'rejected' THEN
                RETURN QUERY SELECT 'rejected_by_staff'::text, NULL::uuid, NULL::text, v_identity.id;
                RETURN;
            END IF;

            SELECT array_agg(pt.id), array_agg(pt.code) INTO v_ids, v_codes
              FROM clinic.patient pt
             WHERE pt.clinic_id = v_clinic AND pt.phone IS NOT NULL
               AND encode(sha256(convert_to(clinic_agent.norm_phone(pt.phone), 'UTF8')), 'hex') = p_phone_hash;
            v_n := coalesce(array_length(v_ids, 1), 0);

            IF v_n <> 1 THEN
                INSERT INTO clinic.identity_link_attempt (clinic_id, channel, external_user_id, method, succeeded)
                VALUES (v_clinic, p_channel, p_external_user_id, 'phone', false);
                RETURN QUERY SELECT (CASE WHEN v_n = 0 THEN 'no_match' ELSE 'ambiguous' END)::text,
                    NULL::uuid, NULL::text, v_identity.id;
                RETURN;
            END IF;

            UPDATE clinic.channel_identity i
               SET patient_id = v_ids[1], verification_status = 'pending'
             WHERE i.clinic_id = v_clinic AND i.id = v_identity.id;
            INSERT INTO clinic.identity_link_attempt (clinic_id, channel, external_user_id, method, succeeded)
            VALUES (v_clinic, p_channel, p_external_user_id, 'phone', true);
            INSERT INTO clinic.audit_log (clinic_id, actor_type, action, entity_type, entity_id, details)
            VALUES (v_clinic, 'agent', 'identity.link_candidate', 'channel_identity', v_identity.id::text,
                    jsonb_build_object('method', 'phone', 'channel', p_channel));
            RETURN QUERY SELECT 'candidate_created'::text, v_ids[1], v_codes[1], v_identity.id;
        END $_$;


--
-- Name: norm_phone(text); Type: FUNCTION; Schema: clinic_agent; Owner: -
--

CREATE FUNCTION clinic_agent.norm_phone(p text) RETURNS text
    LANGUAGE sql IMMUTABLE
    AS $$
            SELECT CASE
                WHEN d LIKE '0084%' THEN '0' || substr(d, 5)
                WHEN d LIKE '84%' AND length(d) IN (11, 12) THEN
                    CASE WHEN substr(d, 3, 1) = '0' THEN substr(d, 3) ELSE '0' || substr(d, 3) END
                ELSE d
            END
            FROM (SELECT regexp_replace(coalesce(p, ''), '[^0-9]', '', 'g') AS d) s
        $$;


--
-- Name: record_inbound_message(text, text, text, text, text, text, timestamp with time zone, text); Type: FUNCTION; Schema: clinic_agent; Owner: -
--

CREATE FUNCTION clinic_agent.record_inbound_message(p_channel text, p_update_id text, p_thread_id text, p_external_user_id text, p_display_name text, p_text text, p_sent_at timestamp with time zone, p_actor_type text) RETURNS TABLE(o_conversation_id uuid, o_message_id uuid, o_patient_id uuid, o_duplicate boolean)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'clinic', 'ctx', 'pg_temp'
    AS $$
        BEGIN
            RETURN QUERY SELECT * FROM clinic_agent.record_inbound_message(
                p_channel, p_update_id, p_thread_id, p_external_user_id, p_display_name, p_text, p_sent_at,
                p_actor_type, NULL::text);
        END $$;


--
-- Name: record_inbound_message(text, text, text, text, text, text, timestamp with time zone, text, text); Type: FUNCTION; Schema: clinic_agent; Owner: -
--

CREATE FUNCTION clinic_agent.record_inbound_message(p_channel text, p_update_id text, p_thread_id text, p_external_user_id text, p_display_name text, p_text text, p_sent_at timestamp with time zone, p_actor_type text, p_account_id text) RETURNS TABLE(o_conversation_id uuid, o_message_id uuid, o_patient_id uuid, o_duplicate boolean)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'clinic', 'agent', 'ctx', 'pg_temp'
    AS $$
        DECLARE
            v_clinic uuid := ctx.the_clinic_id();
            v_identity uuid;
            v_patient uuid;
            v_conv uuid;
            v_msg uuid;
            v_conv_patient uuid;
            v_account text;
            v_purpose text;
        BEGIN
            IF v_clinic IS NULL THEN RAISE EXCEPTION 'no clinic context'; END IF;
            IF p_actor_type NOT IN ('agent', 'system') THEN RAISE EXCEPTION 'bad actor type'; END IF;
            IF p_update_id IS NULL OR p_update_id = '' THEN
                RAISE EXCEPTION 'update_id is the idempotency key';
            END IF;

            -- the identity that received the message: an unknown id is stored as NULL (never lose a message
            -- over a configuration gap), an internal notifier is refused
            IF p_account_id IS NOT NULL AND p_account_id <> '' THEN
                SELECT a.id, a.purpose INTO v_account, v_purpose FROM agent.accounts a
                 WHERE a.clinic_id = v_clinic AND a.id = p_account_id;
                IF v_purpose = 'internal' THEN
                    RAISE EXCEPTION 'an internal account cannot be the identity of a conversation'
                        USING ERRCODE = '23514';
                END IF;
            END IF;

            INSERT INTO clinic.channel_identity AS i
                   (clinic_id, channel, external_user_id, display_name, last_inbound_at)
            VALUES (v_clinic, p_channel, p_external_user_id, NULLIF(p_display_name, ''), now())
            ON CONFLICT (clinic_id, channel, external_user_id) DO UPDATE
               SET last_inbound_at = now(),
                   display_name = COALESCE(NULLIF(EXCLUDED.display_name, ''), i.display_name)
            RETURNING i.id, CASE WHEN i.verification_status = 'verified' THEN i.patient_id END
              INTO v_identity, v_patient;

            INSERT INTO clinic.conversation AS c
                   (clinic_id, channel, external_ref, patient_id, identity_id, account_id,
                    last_message_at, last_inbound_at)
            VALUES (v_clinic, p_channel, p_thread_id, v_patient, v_identity, v_account,
                    COALESCE(p_sent_at, now()), COALESCE(p_sent_at, now()))
            ON CONFLICT (clinic_id, channel, external_ref) DO UPDATE
               SET identity_id = COALESCE(c.identity_id, EXCLUDED.identity_id),
                   patient_id = COALESCE(c.patient_id, EXCLUDED.patient_id),
                   account_id = COALESCE(c.account_id, EXCLUDED.account_id)
            RETURNING c.id, c.patient_id INTO v_conv, v_conv_patient;

            INSERT INTO clinic.message (clinic_id, conversation_id, channel, direction, sender_type, body,
                                        status, update_id, sent_at)
            VALUES (v_clinic, v_conv, p_channel, 'inbound', 'patient', p_text, 'received', p_update_id,
                    p_sent_at)
            ON CONFLICT (clinic_id, channel, update_id) WHERE update_id IS NOT NULL DO NOTHING
            RETURNING id INTO v_msg;

            IF v_msg IS NULL THEN
                SELECT m.id INTO v_msg FROM clinic.message m
                 WHERE m.clinic_id = v_clinic AND m.channel = p_channel AND m.update_id = p_update_id;
                RETURN QUERY SELECT v_conv, v_msg, v_conv_patient, true;
                RETURN;
            END IF;

            UPDATE clinic.conversation c
               SET unread_count = c.unread_count + 1,
                   last_message_at = GREATEST(COALESCE(c.last_message_at, COALESCE(p_sent_at, now())),
                                              COALESCE(p_sent_at, now())),
                   last_inbound_at = GREATEST(COALESCE(c.last_inbound_at, COALESCE(p_sent_at, now())),
                                              COALESCE(p_sent_at, now())),
                   status = CASE WHEN c.status = 'closed' THEN 'open' ELSE c.status END,
                   version = c.version + 1
             WHERE c.clinic_id = v_clinic AND c.id = v_conv;

            INSERT INTO clinic.audit_log (clinic_id, actor_type, action, entity_type, entity_id, details)
            VALUES (v_clinic, p_actor_type, 'message.record_inbound', 'message', v_msg::text,
                    jsonb_build_object('conversation_id', v_conv, 'channel', p_channel));
            RETURN QUERY SELECT v_conv, v_msg, v_conv_patient, false;
        END $$;


--
-- Name: record_outbound_message(uuid, text, text, boolean, uuid, text, text); Type: FUNCTION; Schema: clinic_agent; Owner: -
--

CREATE FUNCTION clinic_agent.record_outbound_message(p_conversation_id uuid, p_text text, p_status text, p_proactive boolean, p_review_item_id uuid, p_error_code text, p_actor_type text) RETURNS TABLE(o_conversation_id uuid, o_message_id uuid)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'clinic', 'ctx', 'pg_temp'
    AS $$
        DECLARE
            v_clinic uuid := ctx.the_clinic_id();
            v_channel text;
            v_msg uuid;
        BEGIN
            IF v_clinic IS NULL THEN RAISE EXCEPTION 'no clinic context'; END IF;
            IF p_actor_type NOT IN ('agent', 'system') THEN RAISE EXCEPTION 'bad actor type'; END IF;
            SELECT c.channel INTO v_channel FROM clinic.conversation c
             WHERE c.clinic_id = v_clinic AND c.id = p_conversation_id;
            IF NOT FOUND THEN RAISE EXCEPTION 'conversation not found'; END IF;

            -- A message created when staff approved the review item is only updated (sent/failed), so
            -- the Inbox never holds the same reply twice.
            IF p_review_item_id IS NOT NULL THEN
                UPDATE clinic.message m
                   SET status = p_status,
                       error_code = p_error_code,
                       sent_at = CASE WHEN p_status = 'sent' THEN now() ELSE m.sent_at END
                 WHERE m.clinic_id = v_clinic AND m.review_item_id = p_review_item_id
                   AND m.conversation_id = p_conversation_id AND m.status = 'queued'
                RETURNING m.id INTO v_msg;
            END IF;

            IF v_msg IS NULL THEN
                INSERT INTO clinic.message (clinic_id, conversation_id, channel, direction, sender_type, body,
                                            status, proactive, review_item_id, error_code, sent_at)
                VALUES (v_clinic, p_conversation_id, v_channel, 'outbound',
                        CASE WHEN p_review_item_id IS NOT NULL THEN 'staff' ELSE 'system' END,
                        p_text, p_status, COALESCE(p_proactive, false), p_review_item_id, p_error_code,
                        CASE WHEN p_status = 'sent' THEN now() END)
                RETURNING id INTO v_msg;
                UPDATE clinic.conversation c
                   SET last_message_at = now(), version = c.version + 1
                 WHERE c.clinic_id = v_clinic AND c.id = p_conversation_id;
            END IF;

            INSERT INTO clinic.audit_log (clinic_id, actor_type, action, entity_type, entity_id, details)
            VALUES (v_clinic, p_actor_type, 'message.record_outbound', 'message', v_msg::text,
                    jsonb_build_object('conversation_id', p_conversation_id, 'status', p_status,
                                       'proactive', COALESCE(p_proactive, false)));
            RETURN QUERY SELECT p_conversation_id, v_msg;
        END $$;


--
-- Name: record_retention_run(text, jsonb); Type: FUNCTION; Schema: clinic_agent; Owner: -
--

CREATE FUNCTION clinic_agent.record_retention_run(p_scope text, p_counts jsonb) RETURNS bigint
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'clinic', 'ctx', 'pg_temp'
    AS $_$
        DECLARE
            v_clinic uuid := ctx.the_clinic_id();
            v_id bigint;
        BEGIN
            IF v_clinic IS NULL THEN RAISE EXCEPTION 'no clinic context'; END IF;
            IF p_scope NOT IN ('agent', 'clinic') THEN RAISE EXCEPTION 'bad retention scope'; END IF;
            IF p_counts IS NULL OR jsonb_typeof(p_counts) <> 'object' THEN
                RAISE EXCEPTION 'counts must be a JSON object';
            END IF;
            IF (SELECT count(*) FROM jsonb_object_keys(p_counts)) > 40 THEN
                RAISE EXCEPTION 'too many counters';
            END IF;
            -- Counters only: short snake_case keys, non-negative integers. No free text can get in.
            IF EXISTS (SELECT 1 FROM jsonb_each(p_counts) e
                        WHERE e.key !~ '^[a-z][a-z_]{0,39}$'
                           OR jsonb_typeof(e.value) <> 'number'
                           OR e.value::text !~ '^[0-9]{1,12}$') THEN
                RAISE EXCEPTION 'counts must map snake_case names to non-negative integers';
            END IF;
            INSERT INTO clinic.audit_log (clinic_id, actor_type, action, entity_type, entity_id, details)
            VALUES (v_clinic, 'system', 'retention.run', 'retention', p_scope,
                    jsonb_build_object('scope', p_scope, 'deleted', p_counts))
            RETURNING id INTO v_id;
            RETURN v_id;
        END $_$;


--
-- Name: redeem_identity_code(text, text, text); Type: FUNCTION; Schema: clinic_agent; Owner: -
--

CREATE FUNCTION clinic_agent.redeem_identity_code(p_channel text, p_external_user_id text, p_code_hash text) RETURNS TABLE(outcome text, patient_id uuid, patient_code text, identity_id uuid)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'clinic', 'clinic_agent', 'ctx', 'pg_temp'
    AS $_$
        #variable_conflict use_column
        DECLARE
            v_clinic uuid := ctx.the_clinic_id();
            v_identity clinic.channel_identity%ROWTYPE;
            v_code clinic.identity_link_code%ROWTYPE;
            v_patient_code text;
        BEGIN
            IF v_clinic IS NULL THEN RAISE EXCEPTION 'no clinic context'; END IF;
            IF p_code_hash IS NULL OR p_code_hash !~ '^[0-9a-f]{64}$' THEN
                RAISE EXCEPTION 'invalid code hash';
            END IF;
            IF clinic_agent.link_attempts_exceeded(v_clinic, p_channel, p_external_user_id) THEN
                RETURN QUERY SELECT 'rate_limited'::text, NULL::uuid, NULL::text, NULL::uuid;
                RETURN;
            END IF;

            SELECT * INTO v_code FROM clinic.identity_link_code c
             WHERE c.clinic_id = v_clinic AND c.code_hash = p_code_hash FOR UPDATE;
            IF NOT FOUND OR v_code.used_at IS NOT NULL THEN
                INSERT INTO clinic.identity_link_attempt (clinic_id, channel, external_user_id, method, succeeded)
                VALUES (v_clinic, p_channel, p_external_user_id, 'code', false);
                RETURN QUERY SELECT 'invalid_code'::text, NULL::uuid, NULL::text, NULL::uuid;
                RETURN;
            END IF;
            IF v_code.expires_at < now() THEN
                INSERT INTO clinic.identity_link_attempt (clinic_id, channel, external_user_id, method, succeeded)
                VALUES (v_clinic, p_channel, p_external_user_id, 'code', false);
                RETURN QUERY SELECT 'expired_code'::text, NULL::uuid, NULL::text, NULL::uuid;
                RETURN;
            END IF;

            INSERT INTO clinic.channel_identity (clinic_id, channel, external_user_id, last_inbound_at)
            VALUES (v_clinic, p_channel, p_external_user_id, now())
            ON CONFLICT (clinic_id, channel, external_user_id) DO UPDATE SET last_inbound_at = now()
            RETURNING * INTO v_identity;

            IF v_identity.verification_status = 'verified' AND v_identity.patient_id <> v_code.patient_id THEN
                INSERT INTO clinic.identity_link_attempt (clinic_id, channel, external_user_id, method, succeeded)
                VALUES (v_clinic, p_channel, p_external_user_id, 'code', false);
                RETURN QUERY SELECT 'conflict'::text, NULL::uuid, NULL::text, v_identity.id;
                RETURN;
            END IF;

            UPDATE clinic.channel_identity i
               SET patient_id = v_code.patient_id, verification_status = 'verified',
                   verified_at = now(), verified_by = v_code.issued_by
             WHERE i.clinic_id = v_clinic AND i.id = v_identity.id;
            UPDATE clinic.identity_link_code c
               SET used_at = now(), used_identity_id = v_identity.id
             WHERE c.clinic_id = v_clinic AND c.id = v_code.id;
            INSERT INTO clinic.identity_link_attempt (clinic_id, channel, external_user_id, method, succeeded)
            VALUES (v_clinic, p_channel, p_external_user_id, 'code', true);
            INSERT INTO clinic.audit_log (clinic_id, actor_type, action, entity_type, entity_id, details)
            VALUES (v_clinic, 'agent', 'identity.verified_by_code', 'channel_identity', v_identity.id::text,
                    jsonb_build_object('channel', p_channel, 'issued_by', v_code.issued_by));
            SELECT pt.code INTO v_patient_code FROM clinic.patient pt
             WHERE pt.clinic_id = v_clinic AND pt.id = v_code.patient_id;
            RETURN QUERY SELECT 'verified'::text, v_code.patient_id, v_patient_code, v_identity.id;
        END $_$;


--
-- Name: resolve_identity(text, text); Type: FUNCTION; Schema: clinic_agent; Owner: -
--

CREATE FUNCTION clinic_agent.resolve_identity(p_channel text, p_external_user_id text) RETURNS TABLE(status text, patient_id uuid, patient_code text, verified_at timestamp with time zone)
    LANGUAGE plpgsql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'clinic', 'ctx', 'pg_temp'
    AS $$
        DECLARE v_clinic uuid := ctx.the_clinic_id();
        BEGIN
            IF v_clinic IS NULL THEN RAISE EXCEPTION 'no clinic context'; END IF;
            RETURN QUERY
            SELECT i.verification_status, i.patient_id, p.code, i.verified_at
              FROM clinic.channel_identity i
              LEFT JOIN clinic.patient p ON p.clinic_id = i.clinic_id AND p.id = i.patient_id
             WHERE i.clinic_id = v_clinic AND i.channel = p_channel AND i.external_user_id = p_external_user_id;
            IF NOT FOUND THEN
                RETURN QUERY SELECT 'unlinked'::text, NULL::uuid, NULL::text, NULL::timestamptz;
            END IF;
        END $$;


--
-- Name: retention_purge_link_attempts(timestamp with time zone, integer, boolean); Type: FUNCTION; Schema: clinic_agent; Owner: -
--

CREATE FUNCTION clinic_agent.retention_purge_link_attempts(p_cutoff timestamp with time zone, p_limit integer, p_dry_run boolean) RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'clinic', 'ctx', 'pg_temp'
    AS $$
        DECLARE
            v_clinic uuid := ctx.the_clinic_id();
            v_n integer;
        BEGIN
            IF v_clinic IS NULL THEN RAISE EXCEPTION 'no clinic context'; END IF;
            -- The failure limiter of the link functions looks one hour back: never delete inside it.
            IF p_cutoff IS NULL OR p_cutoff > now() - interval '1 hour' THEN
                RAISE EXCEPTION 'cutoff must be older than one hour';
            END IF;
            IF p_dry_run THEN
                SELECT count(*)::integer INTO v_n FROM clinic.identity_link_attempt a
                 WHERE a.clinic_id = v_clinic AND a.attempted_at < p_cutoff;
                RETURN v_n;
            END IF;
            IF p_limit IS NULL OR p_limit < 1 OR p_limit > 10000 THEN
                RAISE EXCEPTION 'limit must be between 1 and 10000';
            END IF;
            WITH doomed AS (
                SELECT a.id FROM clinic.identity_link_attempt a
                 WHERE a.clinic_id = v_clinic AND a.attempted_at < p_cutoff
                 ORDER BY a.id LIMIT p_limit FOR UPDATE SKIP LOCKED)
            DELETE FROM clinic.identity_link_attempt t USING doomed WHERE t.id = doomed.id;
            GET DIAGNOSTICS v_n = ROW_COUNT;
            RETURN v_n;
        END $$;


--
-- Name: touch_identity(text, text, text); Type: FUNCTION; Schema: clinic_agent; Owner: -
--

CREATE FUNCTION clinic_agent.touch_identity(p_channel text, p_external_user_id text, p_display_name text) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'clinic', 'ctx', 'pg_temp'
    AS $$
        DECLARE v_clinic uuid := ctx.the_clinic_id();
        BEGIN
            IF v_clinic IS NULL THEN RAISE EXCEPTION 'no clinic context'; END IF;
            INSERT INTO clinic.channel_identity (clinic_id, channel, external_user_id, display_name, last_inbound_at)
            VALUES (v_clinic, p_channel, p_external_user_id, NULLIF(p_display_name, ''), now())
            ON CONFLICT (clinic_id, channel, external_user_id) DO UPDATE
               SET last_inbound_at = now(),
                   display_name = COALESCE(NULLIF(EXCLUDED.display_name, ''), clinic.channel_identity.display_name);
        END $$;


--
-- Name: channel_policy; Type: VIEW; Schema: clinic_agent; Owner: -
--

CREATE VIEW clinic_agent.channel_policy WITH (security_barrier='true') AS
 SELECT clinic_id,
    channel,
    enabled,
    kill_switch_on,
    daily_cap,
    send_window_start,
    send_window_end,
    min_gap_seconds,
    max_gap_seconds,
    requires_friend
   FROM clinic.channel_setting s
  WHERE (clinic_id = ctx.the_clinic_id());


--
-- Name: consent_current; Type: VIEW; Schema: clinic_agent; Owner: -
--

CREATE VIEW clinic_agent.consent_current WITH (security_barrier='true') AS
 SELECT DISTINCT ON (patient_id, kind) clinic_id,
    patient_id,
    kind,
    granted
   FROM clinic.consent c
  WHERE (clinic_id = ctx.the_clinic_id())
  ORDER BY patient_id, kind, created_at DESC;


--
-- Name: identity_verified; Type: VIEW; Schema: clinic_agent; Owner: -
--

CREATE VIEW clinic_agent.identity_verified WITH (security_barrier='true') AS
 SELECT clinic_id,
    channel,
    external_user_id,
    patient_id,
    verified_at
   FROM clinic.channel_identity i
  WHERE ((clinic_id = ctx.the_clinic_id()) AND (verification_status = 'verified'::text));


--
-- Name: message_template_approved; Type: VIEW; Schema: clinic_agent; Owner: -
--

CREATE VIEW clinic_agent.message_template_approved WITH (security_barrier='true') AS
 SELECT clinic_id,
    template_key,
    title,
    body,
    marketing
   FROM clinic.message_template m
  WHERE ((clinic_id = ctx.the_clinic_id()) AND active AND (approved_at IS NOT NULL));


--
-- Name: on_call_contact; Type: VIEW; Schema: clinic_agent; Owner: -
--

CREATE VIEW clinic_agent.on_call_contact WITH (security_barrier='true') AS
 SELECT id,
    clinic_id,
    zalo_number,
    owner,
    valid_from,
    valid_to,
    active,
    is_fixture
   FROM clinic.on_call_contacts c
  WHERE (clinic_id = ctx.the_clinic_id());


--
-- Name: patient_appointment; Type: VIEW; Schema: clinic_agent; Owner: -
--

CREATE VIEW clinic_agent.patient_appointment WITH (security_barrier='true') AS
 SELECT id,
    clinic_id,
    patient_id,
    doctor_id,
    starts_at,
    duration_min,
    status
   FROM clinic.appointment a
  WHERE (clinic_id = ctx.the_clinic_id());


--
-- Name: patient_care_plan; Type: VIEW; Schema: clinic_agent; Owner: -
--

CREATE VIEW clinic_agent.patient_care_plan WITH (security_barrier='true') AS
 SELECT id,
    clinic_id,
    patient_id,
    service_code,
    total_sessions,
    completed_sessions,
    status
   FROM clinic.treatment_plan pl
  WHERE (clinic_id = ctx.the_clinic_id());


--
-- Name: patient_last_session; Type: VIEW; Schema: clinic_agent; Owner: -
--

CREATE VIEW clinic_agent.patient_last_session WITH (security_barrier='true') AS
 SELECT DISTINCT ON (patient_id) clinic_id,
    patient_id,
    protocol_id,
    performed_at
   FROM clinic.treatment_session s
  WHERE ((clinic_id = ctx.the_clinic_id()) AND (status = 'completed'::text))
  ORDER BY patient_id, performed_at DESC;


--
-- Name: patient_open_task; Type: VIEW; Schema: clinic_agent; Owner: -
--

CREATE VIEW clinic_agent.patient_open_task WITH (security_barrier='true') AS
 SELECT id,
    clinic_id,
    patient_id,
    rule_key,
    priority,
    status,
    due_at
   FROM clinic.crm_task t
  WHERE ((clinic_id = ctx.the_clinic_id()) AND (status = ANY (ARRAY['open'::text, 'rescheduled'::text])));


--
-- Name: patient_ownership; Type: VIEW; Schema: clinic_agent; Owner: -
--

CREATE VIEW clinic_agent.patient_ownership WITH (security_barrier='true') AS
 SELECT id,
    clinic_id,
    patient_id,
    cs_owner,
    doctor
   FROM clinic.patient_ownership o
  WHERE (clinic_id = ctx.the_clinic_id());


--
-- Name: patient_ref; Type: VIEW; Schema: clinic_agent; Owner: -
--

CREATE VIEW clinic_agent.patient_ref WITH (security_barrier='true') AS
 SELECT id,
    clinic_id,
    code,
    full_name,
    gender,
    doctor_id,
    marketing_opt_out,
    expected_visit_source,
    reactivated_at,
    last_contact_at
   FROM clinic.patient p
  WHERE (clinic_id = ctx.the_clinic_id());


--
-- Name: review_item_summary; Type: VIEW; Schema: clinic_agent; Owner: -
--

CREATE VIEW clinic_agent.review_item_summary WITH (security_barrier='true') AS
 SELECT r.id,
    r.clinic_id,
    r.kind,
    r.origin,
    r.status,
    r.conversation_id,
    r.patient_id,
    p.code AS patient_code,
    r.job_id,
    r.draft_text,
    r.payload,
    r.sources,
    r.risk_level,
    r.red_flags,
    r.requires_doctor,
    r.model,
    r.prompt_version,
    r.created_at,
    r.decided_at,
    r.version
   FROM (clinic.review_item r
     LEFT JOIN clinic.patient p ON (((p.clinic_id = r.clinic_id) AND (p.id = r.patient_id))))
  WHERE (r.clinic_id = ctx.the_clinic_id());


--
-- Name: staff_profile; Type: VIEW; Schema: clinic_agent; Owner: -
--

CREATE VIEW clinic_agent.staff_profile WITH (security_barrier='true') AS
 SELECT id,
    clinic_id,
    user_id,
    role,
    skills,
    shift,
    capacity,
    languages
   FROM clinic.staff_profiles s
  WHERE (clinic_id = ctx.the_clinic_id());


--
-- Name: SCHEMA clinic_agent; Type: ACL; Schema: -; Owner: -
--

GRANT USAGE ON SCHEMA clinic_agent TO agent_worker;
GRANT USAGE ON SCHEMA clinic_agent TO be_app;


--
-- Name: FUNCTION create_review_item(p_job_id text, p_kind text, p_origin text, p_patient_code text, p_conversation_id uuid, p_draft_text text, p_payload jsonb, p_sources jsonb, p_risk_level text, p_red_flags text[], p_model text, p_prompt_version text); Type: ACL; Schema: clinic_agent; Owner: -
--

REVOKE ALL ON FUNCTION clinic_agent.create_review_item(p_job_id text, p_kind text, p_origin text, p_patient_code text, p_conversation_id uuid, p_draft_text text, p_payload jsonb, p_sources jsonb, p_risk_level text, p_red_flags text[], p_model text, p_prompt_version text) FROM PUBLIC;
GRANT ALL ON FUNCTION clinic_agent.create_review_item(p_job_id text, p_kind text, p_origin text, p_patient_code text, p_conversation_id uuid, p_draft_text text, p_payload jsonb, p_sources jsonb, p_risk_level text, p_red_flags text[], p_model text, p_prompt_version text) TO agent_worker;
GRANT ALL ON FUNCTION clinic_agent.create_review_item(p_job_id text, p_kind text, p_origin text, p_patient_code text, p_conversation_id uuid, p_draft_text text, p_payload jsonb, p_sources jsonb, p_risk_level text, p_red_flags text[], p_model text, p_prompt_version text) TO be_app;


--
-- Name: FUNCTION link_attempts_exceeded(p_clinic uuid, p_channel text, p_uid text); Type: ACL; Schema: clinic_agent; Owner: -
--

REVOKE ALL ON FUNCTION clinic_agent.link_attempts_exceeded(p_clinic uuid, p_channel text, p_uid text) FROM PUBLIC;


--
-- Name: FUNCTION link_identity_by_phone_hash(p_channel text, p_external_user_id text, p_phone_hash text); Type: ACL; Schema: clinic_agent; Owner: -
--

REVOKE ALL ON FUNCTION clinic_agent.link_identity_by_phone_hash(p_channel text, p_external_user_id text, p_phone_hash text) FROM PUBLIC;
GRANT ALL ON FUNCTION clinic_agent.link_identity_by_phone_hash(p_channel text, p_external_user_id text, p_phone_hash text) TO agent_worker;


--
-- Name: FUNCTION norm_phone(p text); Type: ACL; Schema: clinic_agent; Owner: -
--

REVOKE ALL ON FUNCTION clinic_agent.norm_phone(p text) FROM PUBLIC;


--
-- Name: FUNCTION record_inbound_message(p_channel text, p_update_id text, p_thread_id text, p_external_user_id text, p_display_name text, p_text text, p_sent_at timestamp with time zone, p_actor_type text); Type: ACL; Schema: clinic_agent; Owner: -
--

REVOKE ALL ON FUNCTION clinic_agent.record_inbound_message(p_channel text, p_update_id text, p_thread_id text, p_external_user_id text, p_display_name text, p_text text, p_sent_at timestamp with time zone, p_actor_type text) FROM PUBLIC;
GRANT ALL ON FUNCTION clinic_agent.record_inbound_message(p_channel text, p_update_id text, p_thread_id text, p_external_user_id text, p_display_name text, p_text text, p_sent_at timestamp with time zone, p_actor_type text) TO agent_worker;
GRANT ALL ON FUNCTION clinic_agent.record_inbound_message(p_channel text, p_update_id text, p_thread_id text, p_external_user_id text, p_display_name text, p_text text, p_sent_at timestamp with time zone, p_actor_type text) TO be_app;


--
-- Name: FUNCTION record_inbound_message(p_channel text, p_update_id text, p_thread_id text, p_external_user_id text, p_display_name text, p_text text, p_sent_at timestamp with time zone, p_actor_type text, p_account_id text); Type: ACL; Schema: clinic_agent; Owner: -
--

REVOKE ALL ON FUNCTION clinic_agent.record_inbound_message(p_channel text, p_update_id text, p_thread_id text, p_external_user_id text, p_display_name text, p_text text, p_sent_at timestamp with time zone, p_actor_type text, p_account_id text) FROM PUBLIC;
GRANT ALL ON FUNCTION clinic_agent.record_inbound_message(p_channel text, p_update_id text, p_thread_id text, p_external_user_id text, p_display_name text, p_text text, p_sent_at timestamp with time zone, p_actor_type text, p_account_id text) TO agent_worker;
GRANT ALL ON FUNCTION clinic_agent.record_inbound_message(p_channel text, p_update_id text, p_thread_id text, p_external_user_id text, p_display_name text, p_text text, p_sent_at timestamp with time zone, p_actor_type text, p_account_id text) TO be_app;


--
-- Name: FUNCTION record_outbound_message(p_conversation_id uuid, p_text text, p_status text, p_proactive boolean, p_review_item_id uuid, p_error_code text, p_actor_type text); Type: ACL; Schema: clinic_agent; Owner: -
--

REVOKE ALL ON FUNCTION clinic_agent.record_outbound_message(p_conversation_id uuid, p_text text, p_status text, p_proactive boolean, p_review_item_id uuid, p_error_code text, p_actor_type text) FROM PUBLIC;
GRANT ALL ON FUNCTION clinic_agent.record_outbound_message(p_conversation_id uuid, p_text text, p_status text, p_proactive boolean, p_review_item_id uuid, p_error_code text, p_actor_type text) TO agent_worker;
GRANT ALL ON FUNCTION clinic_agent.record_outbound_message(p_conversation_id uuid, p_text text, p_status text, p_proactive boolean, p_review_item_id uuid, p_error_code text, p_actor_type text) TO be_app;


--
-- Name: FUNCTION record_retention_run(p_scope text, p_counts jsonb); Type: ACL; Schema: clinic_agent; Owner: -
--

REVOKE ALL ON FUNCTION clinic_agent.record_retention_run(p_scope text, p_counts jsonb) FROM PUBLIC;
GRANT ALL ON FUNCTION clinic_agent.record_retention_run(p_scope text, p_counts jsonb) TO agent_worker;
GRANT ALL ON FUNCTION clinic_agent.record_retention_run(p_scope text, p_counts jsonb) TO be_app;


--
-- Name: FUNCTION redeem_identity_code(p_channel text, p_external_user_id text, p_code_hash text); Type: ACL; Schema: clinic_agent; Owner: -
--

REVOKE ALL ON FUNCTION clinic_agent.redeem_identity_code(p_channel text, p_external_user_id text, p_code_hash text) FROM PUBLIC;
GRANT ALL ON FUNCTION clinic_agent.redeem_identity_code(p_channel text, p_external_user_id text, p_code_hash text) TO agent_worker;


--
-- Name: FUNCTION resolve_identity(p_channel text, p_external_user_id text); Type: ACL; Schema: clinic_agent; Owner: -
--

REVOKE ALL ON FUNCTION clinic_agent.resolve_identity(p_channel text, p_external_user_id text) FROM PUBLIC;
GRANT ALL ON FUNCTION clinic_agent.resolve_identity(p_channel text, p_external_user_id text) TO agent_worker;
GRANT ALL ON FUNCTION clinic_agent.resolve_identity(p_channel text, p_external_user_id text) TO be_app;


--
-- Name: FUNCTION retention_purge_link_attempts(p_cutoff timestamp with time zone, p_limit integer, p_dry_run boolean); Type: ACL; Schema: clinic_agent; Owner: -
--

REVOKE ALL ON FUNCTION clinic_agent.retention_purge_link_attempts(p_cutoff timestamp with time zone, p_limit integer, p_dry_run boolean) FROM PUBLIC;
GRANT ALL ON FUNCTION clinic_agent.retention_purge_link_attempts(p_cutoff timestamp with time zone, p_limit integer, p_dry_run boolean) TO be_app;


--
-- Name: FUNCTION touch_identity(p_channel text, p_external_user_id text, p_display_name text); Type: ACL; Schema: clinic_agent; Owner: -
--

REVOKE ALL ON FUNCTION clinic_agent.touch_identity(p_channel text, p_external_user_id text, p_display_name text) FROM PUBLIC;
GRANT ALL ON FUNCTION clinic_agent.touch_identity(p_channel text, p_external_user_id text, p_display_name text) TO agent_worker;
GRANT ALL ON FUNCTION clinic_agent.touch_identity(p_channel text, p_external_user_id text, p_display_name text) TO be_app;


--
-- Name: TABLE channel_policy; Type: ACL; Schema: clinic_agent; Owner: -
--

GRANT SELECT ON TABLE clinic_agent.channel_policy TO agent_worker;
GRANT SELECT ON TABLE clinic_agent.channel_policy TO be_app;


--
-- Name: TABLE consent_current; Type: ACL; Schema: clinic_agent; Owner: -
--

GRANT SELECT ON TABLE clinic_agent.consent_current TO agent_worker;
GRANT SELECT ON TABLE clinic_agent.consent_current TO be_app;


--
-- Name: TABLE identity_verified; Type: ACL; Schema: clinic_agent; Owner: -
--

GRANT SELECT ON TABLE clinic_agent.identity_verified TO agent_worker;
GRANT SELECT ON TABLE clinic_agent.identity_verified TO be_app;


--
-- Name: TABLE message_template_approved; Type: ACL; Schema: clinic_agent; Owner: -
--

GRANT SELECT ON TABLE clinic_agent.message_template_approved TO agent_worker;
GRANT SELECT ON TABLE clinic_agent.message_template_approved TO be_app;


--
-- Name: TABLE on_call_contact; Type: ACL; Schema: clinic_agent; Owner: -
--

GRANT SELECT ON TABLE clinic_agent.on_call_contact TO agent_worker;


--
-- Name: TABLE patient_appointment; Type: ACL; Schema: clinic_agent; Owner: -
--

GRANT SELECT ON TABLE clinic_agent.patient_appointment TO agent_worker;
GRANT SELECT ON TABLE clinic_agent.patient_appointment TO be_app;


--
-- Name: TABLE patient_care_plan; Type: ACL; Schema: clinic_agent; Owner: -
--

GRANT SELECT ON TABLE clinic_agent.patient_care_plan TO agent_worker;
GRANT SELECT ON TABLE clinic_agent.patient_care_plan TO be_app;


--
-- Name: TABLE patient_last_session; Type: ACL; Schema: clinic_agent; Owner: -
--

GRANT SELECT ON TABLE clinic_agent.patient_last_session TO agent_worker;
GRANT SELECT ON TABLE clinic_agent.patient_last_session TO be_app;


--
-- Name: TABLE patient_open_task; Type: ACL; Schema: clinic_agent; Owner: -
--

GRANT SELECT ON TABLE clinic_agent.patient_open_task TO agent_worker;
GRANT SELECT ON TABLE clinic_agent.patient_open_task TO be_app;


--
-- Name: TABLE patient_ownership; Type: ACL; Schema: clinic_agent; Owner: -
--

GRANT SELECT ON TABLE clinic_agent.patient_ownership TO agent_worker;


--
-- Name: TABLE patient_ref; Type: ACL; Schema: clinic_agent; Owner: -
--

GRANT SELECT ON TABLE clinic_agent.patient_ref TO agent_worker;
GRANT SELECT ON TABLE clinic_agent.patient_ref TO be_app;


--
-- Name: TABLE review_item_summary; Type: ACL; Schema: clinic_agent; Owner: -
--

GRANT SELECT ON TABLE clinic_agent.review_item_summary TO agent_worker;
GRANT SELECT ON TABLE clinic_agent.review_item_summary TO be_app;


--
-- Name: TABLE staff_profile; Type: ACL; Schema: clinic_agent; Owner: -
--

GRANT SELECT ON TABLE clinic_agent.staff_profile TO agent_worker;


--
-- PostgreSQL database dump complete
--

\unrestrict aUfUrXjbVbGvxVwCnDETCZ0Oga9N7S3nAAynMiMEFJhKbV1hbxfiSby9scyYwsi

