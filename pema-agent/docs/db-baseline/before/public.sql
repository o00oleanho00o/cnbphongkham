--
-- PostgreSQL database dump
--

\restrict 4caJjauY1PVpmn8OCIETfYweUOhH7XxfHURwipa8FJufkDDOdsZwwInZrdITxzM

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
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA public;


--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA public IS 'standard public schema';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version_agent_rt; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version_agent_rt (
    version_num character varying(32) NOT NULL
);


--
-- Name: alembic_version_pema; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version_pema (
    version_num character varying(32) NOT NULL
);


--
-- Name: alembic_version_agent_rt alembic_version_agent_rt_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version_agent_rt
    ADD CONSTRAINT alembic_version_agent_rt_pkc PRIMARY KEY (version_num);


--
-- Name: alembic_version_pema alembic_version_pema_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version_pema
    ADD CONSTRAINT alembic_version_pema_pkc PRIMARY KEY (version_num);


--
-- PostgreSQL database dump complete
--

\unrestrict 4caJjauY1PVpmn8OCIETfYweUOhH7XxfHURwipa8FJufkDDOdsZwwInZrdITxzM

