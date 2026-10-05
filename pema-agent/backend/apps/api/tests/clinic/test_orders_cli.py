# new tests (package U, step U5)
"""``pema catalog import <json>``: loads the real product catalog once, idempotently, with its provenance.
Needs ``PEMA_TEST_DATABASE_URL`` (skipped otherwise)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from pema import cli
from pema.api.clinic_testing import BE_PASSWORD
from pema.config.env import get_settings
from pema.core.testing import ensure_test_clinic, truncate_installation_data

pytestmark = pytest.mark.db

CATALOG_JSON = Path(__file__).resolve().parents[6] / "prototype" / "shared" / "product-catalog.json"
EXCEL_SHA256 = "3047d9e3bb50f813c39a15b9848e01697a59f6984d3ac676bdbd28186c387de5"


@pytest.mark.skipif(not CATALOG_JSON.exists(), reason="prototype catalog not in this checkout")
def test_the_cli_imports_the_real_catalog_and_a_second_run_changes_nothing(
    pg_url: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    engine = create_engine(pg_url)
    try:
        with engine.begin() as conn:
            ensure_test_clinic(conn)
            truncate_installation_data(conn)
        be_app_url = make_url(pg_url).set(username="be_app", password=BE_PASSWORD)
        monkeypatch.setenv("PEMA_DATABASE_URL", be_app_url.render_as_string(hide_password=False))
        get_settings.cache_clear()
        argv = ["catalog", "import", str(CATALOG_JSON), "--source-sha256", EXCEL_SHA256]

        assert cli.main(argv) == 0
        first = json.loads(capsys.readouterr().out)
        assert (first["total"], first["created"], first["unchanged_run"]) == (115, 115, False)

        assert cli.main(argv) == 0
        second = json.loads(capsys.readouterr().out)
        assert (second["created"], second["updated"], second["unchanged_run"]) == (0, 0, True)
        assert second["sha256"] == first["sha256"]

        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM clinic.product")).scalar_one() == 115
            row = conn.execute(
                text(
                    "SELECT source_name, source_sha256, total_rows, prescription_rows FROM clinic.catalog_import"
                )
            ).one()
            assert tuple(row) == ("product-catalog.json", EXCEL_SHA256, 115, 30)
            assert (
                conn.execute(text("SELECT price_vnd FROM clinic.product WHERE code = 'H002'")).scalar_one()
                == 5500
            )
    finally:
        engine.dispose()
        get_settings.cache_clear()


def test_the_cli_refuses_a_broken_file_and_a_bad_hash(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text(
        json.dumps([{"code": "H1", "name": "x", "price": 1.5, "outputType": "PRESCRIPTION"}]), "utf-8"
    )
    assert cli.main(["catalog", "import", str(broken)]) == 1
    assert "Giá không hợp lệ: H1." in capsys.readouterr().err
    assert cli.main(["catalog", "import", str(tmp_path / "missing.json")]) == 1
    good = tmp_path / "good.json"
    good.write_text(
        json.dumps([{"code": "H1", "name": "x", "price": 1, "outputType": "PRESCRIPTION"}]), "utf-8"
    )
    assert cli.main(["catalog", "import", str(good), "--source-sha256", "abc"]) == 2
