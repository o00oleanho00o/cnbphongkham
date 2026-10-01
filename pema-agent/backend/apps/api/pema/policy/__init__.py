"""Policy profiles for the Pema agent (package P). Implements ``pema_contracts.policy.PolicyHooks``.

``staff_assistant`` keeps the zalo-agent behaviour; ``patient_channel`` is the clinic-safety profile of
PLAN-AI01 section 5. Modules:

* ``hooks``           ``ClinicPolicyHooks``: the eight hooks, driven by the flags of the profile
* ``profiles``        resolve the profile of an account + agent, build ``PolicyContext``
* ``redflags``        red-flag detector (bleeding, fever, pus, dyspnoea; with/without diacritics)
* ``pii``             PII mask and the narrow, name-only restore
* ``identity``        zalo_uid <-> patient link: phone hash, reception code, rate limit
* ``identity_admin``  staff side (confirm, reject, issue a code, set an account profile); ``be_app``
* ``gateway``         the ``clinic_agent`` views/functions the hooks read (``agent_worker``)
* ``review``          builders of the review items the policy and its callers open
* ``turn_guard``      the normative order of a turn around the model, as a reference function
* ``testing``         in-memory doubles (tests and evals only)
"""
