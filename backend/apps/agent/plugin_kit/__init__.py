"""What plugins share with each other, owned by neither the harness nor any plugin (rule H1 in
.claude/rules/agent-harness.md): the contracts of the services one plugin gives another through
``ctx.provide`` / ``ctx.use``. It imports neither
``agent_app`` nor ``plugins``; a plugin never imports another plugin, it imports this."""

from __future__ import annotations

from plugin_kit.services import (
    EMBEDDINGS,
    JUDGE,
    EmbeddingService,
    EmbeddingUnavailableError,
    JudgeService,
    JudgeUnavailableError,
)

__all__ = [
    "EMBEDDINGS",
    "JUDGE",
    "EmbeddingService",
    "EmbeddingUnavailableError",
    "JudgeService",
    "JudgeUnavailableError",
]
