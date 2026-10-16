--
-- PostgreSQL database dump
--

\restrict Jlf3w99WzUbX5tcWfGY2dASvLYt3fLQfjmqgHAzWP2qVvPkrV6BzAev8F2Oztch

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
-- Name: ctx; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA ctx;


--
-- Name: the_clinic_id(); Type: FUNCTION; Schema: ctx; Owner: -
--

CREATE FUNCTION ctx.the_clinic_id() RETURNS uuid
    LANGUAGE plpgsql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'clinic', 'pg_temp'
    AS $$
        DECLARE
            v_id uuid;
        BEGIN
            SELECT id INTO v_id FROM clinic.clinic;
            IF v_id IS NULL THEN
                RAISE EXCEPTION 'no clinic installed: run clinic.ensure_clinic first';
            END IF;
            RETURN v_id;
        END $$;


--
-- Name: SCHEMA ctx; Type: ACL; Schema: -; Owner: -
--

GRANT USAGE ON SCHEMA ctx TO be_app;
GRANT USAGE ON SCHEMA ctx TO agent_worker;


--
-- Name: FUNCTION the_clinic_id(); Type: ACL; Schema: ctx; Owner: -
--

REVOKE ALL ON FUNCTION ctx.the_clinic_id() FROM PUBLIC;
GRANT ALL ON FUNCTION ctx.the_clinic_id() TO be_app;
GRANT ALL ON FUNCTION ctx.the_clinic_id() TO agent_worker;


--
-- PostgreSQL database dump complete
--

\unrestrict Jlf3w99WzUbX5tcWfGY2dASvLYt3fLQfjmqgHAzWP2qVvPkrV6BzAev8F2Oztch

