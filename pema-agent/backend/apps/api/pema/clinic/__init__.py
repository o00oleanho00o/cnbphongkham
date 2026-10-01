"""Clinic CRM. domain/ actions/ rbac/ audit/ crm_rules/ and models/ (ORM of clinic.*). Owners: B1 (all
but crm_rules), B2 (crm_rules). domain and actions never import channels, api, agent or workers; the
agent side reaches this package only through pema.clinic.actions.
"""
