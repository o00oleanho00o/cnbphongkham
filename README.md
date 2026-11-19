# Agent (agentic RAG)

An agent that answers from its own knowledge store, on a web console and on chat platforms (Zalo through a connector),
with a harness of plugins, a case engine for proactive messages and a dashboard. Split from the Pema clinic project
on 2026-11-18 (tag `split-base`); the clinic CRM lives on branch `split/crm`.

Start everything locally (demo values, ports on 127.0.0.1):

    docker compose up --build

Then open http://localhost:3000; the first sign-in creates the agent's admin account. The code is in `pema-agent/`
(see `pema-agent/README.md`), the working rules in `AGENT.md`.
