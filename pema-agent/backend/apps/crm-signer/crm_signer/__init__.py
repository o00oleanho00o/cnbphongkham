"""``crm-signer``: the only holder of the key that signs the agent's calls to the CRM
(docs/PLAN-crm-plugin.md 3.9).

It imports nothing of the CRM (``pema``) or of the agent (``agent_app``, ``agentcore``): the two meet only
over HTTP.
"""
