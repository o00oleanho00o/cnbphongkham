"""Shared contracts of the Pema CSKH agent (docs/CONTRACTS-AI01.md is the index).

Import from the submodules, e.g. ``from pema_contracts.channel import ChannelPort``.

Foundations:  common (base model, +07:00 time, Page), roles, errors, actions.
Channels:     channel (ChannelPort and optional capabilities, InboundMessage, SendResult).
Engine:       agents (account/agent config), agent_turn (AgentEngine, queue, lock), tools (ToolSpec,
              ToolRegistry), policy (PolicyProfile, PolicyHooks), conversation (stores), knowledge,
              mcp, scheduler (job model, SchedulerPort, ProactiveSendGuard).
Clinic:       auth, patients, appointments, crm, conversations (Inbox), review, clinic_actions
              (the agent-facing surface of the clinic), admin, admin_agent.
"""

__version__ = "0.1.0"
