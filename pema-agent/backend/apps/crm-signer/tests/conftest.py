"""Fixtures: a signer with a fresh key and a fake CRM (helpers in ``crm_signer.testing``)."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from starlette.testclient import TestClient

from crm_signer import keys
from crm_signer.app import create_app
from crm_signer.testing import UPSTREAM, FakeCrm


@pytest.fixture
def key() -> keys.SigningKey:
    return keys.signing_key(Ed25519PrivateKey.generate())


@pytest.fixture
def crm() -> FakeCrm:
    return FakeCrm()


@pytest.fixture
def client(key: keys.SigningKey, crm: FakeCrm) -> Iterator[TestClient]:
    app = create_app(key, UPSTREAM, transport=httpx.MockTransport(crm.handle))
    with TestClient(app) as c:
        yield c
