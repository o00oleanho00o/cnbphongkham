"""Every recorded scenario under ``tests/replays/<name>/`` replays through the real agent, without an API key,
to the transcript in its ``expected.txt``. Re-record a scenario after a change that alters what the model is
asked (``agent chat --record``), then ``agent replay ... --update``."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from agent_app.cli import main
from agent_app.profile import load_profile
from agent_app.replay import mask, replay

APP_DIR = Path(__file__).resolve().parents[1]
DEV_PROFILE = APP_DIR / "agents" / "dev"
SCENARIOS = sorted(p for p in (APP_DIR / "tests" / "replays").iterdir() if (p / "cassette.jsonl").is_file())


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[p.name for p in SCENARIOS])
async def test_a_recorded_scenario_replays_to_its_expected_transcript(scenario: Path) -> None:
    outcome = await replay(scenario / "cassette.jsonl", load_profile(DEV_PROFILE))

    assert outcome.transcript == (scenario / "expected.txt").read_text(encoding="utf-8")


def test_there_are_scenarios() -> None:
    assert {p.name for p in SCENARIOS} >= {"echo-two-turns", "calculate-after-rate-limit"}


def test_times_dates_ids_and_weekdays_are_masked() -> None:
    text = "2026-10-09T17:05:00+07:00 (Friday, Asia/Ho_Chi_Minh) at 9:30, id 0f8c1e2a-1b2c-4d5e-8f90-123456789abc"

    assert mask(text) == "<datetime> (<weekday>, Asia/Ho_Chi_Minh) at <time>, id <id>"


def test_the_replay_command_compares_and_shows_a_diff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    cassette = APP_DIR / "tests" / "replays" / "echo-two-turns" / "cassette.jsonl"
    expected = APP_DIR / "tests" / "replays" / "echo-two-turns" / "expected.txt"
    wrong = tmp_path / "wrong.txt"
    wrong.write_text("== turn 1 ==\n", encoding="utf-8")
    args = ["replay", str(cassette), "--profile", str(DEV_PROFILE)]

    assert main([*args, "--expect", str(expected)]) == 0
    assert "matches" in capsys.readouterr().out
    assert main([*args, "--expect", str(wrong)]) == 1
    assert "+user: hello there" in capsys.readouterr().out
    assert main([*args, "--expect", str(tmp_path / "new.txt"), "--update"]) == 0
    assert (tmp_path / "new.txt").read_text(encoding="utf-8") == expected.read_text(encoding="utf-8")


def test_a_drifted_cassette_fails_the_replay_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    source = APP_DIR / "tests" / "replays" / "echo-two-turns" / "cassette.jsonl"
    drifted = tmp_path / "cassette.jsonl"
    drifted.write_text(
        source.read_text(encoding="utf-8").replace('"hello there"}', '"hi"}', 1), encoding="utf-8"
    )

    assert main(["replay", str(drifted), "--profile", str(DEV_PROFILE)]) == 1
    assert "replay failed: call 1: user was 'hello there' when recorded, now 'hi'" in capsys.readouterr().out
