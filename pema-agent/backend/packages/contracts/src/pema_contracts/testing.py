"""Constants shared by the tests of the clinic application. Import in tests only."""

from __future__ import annotations

from uuid import UUID

FAKE_CLINIC_ID = UUID("00000000-0000-4000-8000-000000000001")
"""A fixed clinic id for tests that do not touch a database."""
