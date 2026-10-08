"""Shared contracts of the Pema clinic application (docs/CONTRACTS-AI01.md is the index).

Import from the submodules, e.g. ``from pema_contracts.patients import PatientOut``.

Foundations:  common (base model, +07:00 time, Page), roles, errors, actions, installation.
Clinic:       auth, patients, appointments, crm, conversations (Inbox), review (doctor follow-up queue),
              catalog, orders, finance, guide, knowledge, live, ops, admin.
Channels:     channel (channel kinds and message shapes, kept for the future channel integration).
"""

__version__ = "0.1.0"
