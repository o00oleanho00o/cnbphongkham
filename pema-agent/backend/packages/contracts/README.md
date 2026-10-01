# pema-contracts

Shared, dependency-light contracts of Pema Agent: pydantic DTOs, `ChannelPort`, the ports between the
12 parallel packages (scheduler, agent turn, policy hooks, tool registry, knowledge, conversation stores,
MCP, agent-facing clinic actions) and the error codes. It must never import `pema`. The index of every
contract and the ownership of every directory is `pema-agent/docs/CONTRACTS-AI01.md`.

`pema_contracts.testing` has the fakes (`FakeChannel`, `InMemoryTurnQueue`, `InMemoryThreadLock`,
`FakeTextGenerator`, `make_inbound`, `fake_agent_profile`, `fake_account_config`) every package uses in
its tests.

Rules for changing it: additive only after package A (new optional fields, new enum members); renames
and removals need a note in CONTRACTS-AI01.md and a coordinated change in every package (package G).
