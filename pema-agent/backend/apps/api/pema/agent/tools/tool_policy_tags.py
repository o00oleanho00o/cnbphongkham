# ported from: (no zalo-agent source) PLAN-AI01 section 5, tool row of the policy table
"""Policy metadata of the built-in tools, as DATA, so package P (and the Tools page) can filter by meaning
without a hand-written list of keys in a second place.

Nothing here removes a tool. ``PolicyProfile.disabled_tool_keys`` of the ``patient_channel`` profile is
``MEDIA_AND_WEB_TOOL_KEYS`` (contract); the registry applies it, and ``PolicyHooks.filter_tool_keys`` may
narrow further. The tags answer WHY a tool is in that set and what else a future profile may want to
switch off:

* ``media``: sends or reads files, images or video (``send_file``, documents, images, video, ``read_image``);
* ``web``: reaches the open internet (``web_search``, ``web_fetch``, and the video sources);
* ``third_party``: sends content to a third party outside the clinic's infrastructure (image generation
  provider, Jina Reader fallback, search providers, video sources);
* ``sends_to_chat``: writes into the conversation by itself (not through the reply of the turn);
* ``reads_patient_media``: looks at a photo the other side sent (``read_image``): in ``patient_channel`` a
  patient's photo is only FLAGGED in the Inbox for a person, never analysed (PLAN-AI01 section 5);
* ``writes_memory``: stores something durable about the person (``save_memory``);
* ``schedules``: creates proactive work (``schedule_task``);
* ``clinic_safe``: allowed in ``patient_channel`` (text-only, no third party).
"""

from __future__ import annotations

from pema_contracts.policy import MEDIA_AND_WEB_TOOL_KEYS

TOOL_POLICY_TAGS: dict[str, frozenset[str]] = {
    "add_reaction": frozenset({"sends_to_chat", "clinic_safe"}),
    "send_file": frozenset({"media", "sends_to_chat"}),
    "create_word_document": frozenset({"media", "sends_to_chat"}),
    "create_excel_file": frozenset({"media", "sends_to_chat"}),
    "create_image": frozenset({"media", "third_party", "sends_to_chat"}),
    "tai_video": frozenset({"media", "web", "third_party", "sends_to_chat"}),
    "tag_member": frozenset({"sends_to_chat", "clinic_safe"}),
    "save_memory": frozenset({"writes_memory", "clinic_safe"}),
    "schedule_task": frozenset({"schedules", "clinic_safe"}),
    "get_datetime": frozenset({"clinic_safe"}),
    "web_search": frozenset({"web", "third_party"}),
    "web_fetch": frozenset({"web", "third_party"}),
    "read_image": frozenset({"media", "reads_patient_media", "third_party"}),
    "get_group_info": frozenset({"clinic_safe"}),
    "kb_search": frozenset({"clinic_safe"}),
}

_MEDIA_OR_WEB = frozenset({"media", "web"})


def tool_keys_with_tag(tag: str) -> frozenset[str]:
    return frozenset(key for key, tags in TOOL_POLICY_TAGS.items() if tag in tags)


def tool_keys_blocked_in_patient_channel() -> frozenset[str]:
    """Keys carrying ``media`` or ``web``: must equal ``MEDIA_AND_WEB_TOOL_KEYS`` of the contract (tested)."""
    return frozenset(key for key, tags in TOOL_POLICY_TAGS.items() if tags & _MEDIA_OR_WEB)


def policy_tags_of(key: str) -> frozenset[str]:
    """Tags of a tool key; a tool without an entry (an MCP tool) has none, so no profile treats it as safe."""
    return TOOL_POLICY_TAGS.get(key, frozenset())


__all__ = [
    "MEDIA_AND_WEB_TOOL_KEYS",
    "TOOL_POLICY_TAGS",
    "policy_tags_of",
    "tool_keys_blocked_in_patient_channel",
    "tool_keys_with_tag",
]
