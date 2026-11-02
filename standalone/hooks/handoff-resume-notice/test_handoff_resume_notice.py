"""Tests for handoff-resume-notice.py. Run from this folder: python -m pytest test_handoff_resume_notice.py"""
import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import handoff_pointer as hp  # noqa: E402

spec = importlib.util.spec_from_file_location("hrn", HERE / "handoff-resume-notice.py")
hrn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hrn)

NOW = datetime.now(timezone.utc)
WRITER = "0dfa82e1-35b1-43ee-9ad2-bc249c96d1c3"
OWN = "9b6e8918-58b4-4ccb-b9cf-67ea72659329"
OTHER = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
NAME = "auto-resume-handoff"


@pytest.fixture(autouse=True)
def stores(tmp_path, monkeypatch):
    monkeypatch.setenv("HANDOFF_POINTER_DIR", str(tmp_path / "ptrs"))


def primer(tmp_path, body="# Handoff: resume the thing\n", name="2026-10-31-x.md", repo="r1"):
    d = tmp_path / repo / ".claude" / "handoffs"
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(body, encoding="utf-8")
    return str(p)


def transcript(tmp_path, title=NAME):
    t = tmp_path / "t.jsonl"
    t.write_text(json.dumps({"type": "custom-title", "customTitle": title}) + "\n", encoding="utf-8")
    return str(t)


def point(tmp_path, p, ref="faa98d", sid=WRITER, now=NOW, title=NAME):
    return hp.write(sid, transcript(tmp_path, title), p, ref, now=now)


def payload(**kw):
    base = {"hook_event_name": "SessionStart", "source": "clear", "session_id": OWN, "session_title": NAME}
    base.update(kw)
    return base


def test_one_match_offers_the_primer(tmp_path):
    p = primer(tmp_path)
    point(tmp_path, p)
    out = hrn.build_output(payload())
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert p in ctx and "[ref] must be faa98d" in ctx and "resume the thing" in ctx and "ListAgents" in ctx
    assert "go-ahead is the confirmation" in ctx
    assert "2026-10-31-x.md" in out["systemMessage"]


@pytest.mark.parametrize("source", ["startup", "resume", "compact", "fork", None])
def test_other_sources_are_silent(tmp_path, source):
    point(tmp_path, primer(tmp_path))
    assert hrn.build_output(payload(source=source)) is None


@pytest.mark.parametrize("title", [None, "", "   ", 7])
def test_no_usable_title_is_silent(tmp_path, title):
    point(tmp_path, primer(tmp_path))
    assert hrn.build_output(payload(session_title=title)) is None


def test_different_name_is_silent(tmp_path):
    point(tmp_path, primer(tmp_path))
    assert hrn.build_output(payload(session_title="something-else")) is None


def test_two_pointers_same_name_fall_back(tmp_path):
    point(tmp_path, primer(tmp_path, name="a.md"))
    point(tmp_path, primer(tmp_path, name="b.md"), sid=OTHER, ref="ce63ea")
    assert hrn.build_output(payload()) is None


def test_primer_consumed_or_archived_is_silent(tmp_path):
    p = primer(tmp_path)
    point(tmp_path, p)
    arch = Path(p).parent / "archive"
    arch.mkdir()
    Path(p).rename(arch / Path(p).name)
    assert hrn.build_output(payload()) is None


def test_pointer_older_than_two_hours_is_silent(tmp_path):
    point(tmp_path, primer(tmp_path), now=NOW - timedelta(hours=2, minutes=5))
    assert hrn.build_output(payload()) is None


def test_malformed_pointer_file_is_ignored(tmp_path):
    p = primer(tmp_path)
    point(tmp_path, p)
    (tmp_path / "ptrs" / "junk.json").write_text("{nope", encoding="utf-8")
    assert hrn.build_output(payload()) is not None


def test_long_heading_is_capped_and_control_characters_removed(tmp_path):
    p = primer(tmp_path, body="# " + "A" * 300 + "\x1b[31m red\n")
    point(tmp_path, p)
    ctx = hrn.build_output(payload())["hookSpecificOutput"]["additionalContext"]
    assert "A" * 110 in ctx and "A" * 111 not in ctx and "\x1b" not in ctx


def test_missing_primer_file_never_raises(tmp_path):
    assert hrn._heading(str(tmp_path / "nope.md")) == ""


def run_hook(stdin, tmp_path):
    env = {**os.environ, "HANDOFF_POINTER_DIR": str(tmp_path / "ptrs")}
    return subprocess.run([sys.executable, str(HERE / "handoff-resume-notice.py")], input=stdin, text=True, capture_output=True, env=env, timeout=30)


def test_process_prints_json_on_match_and_nothing_otherwise(tmp_path):
    point(tmp_path, primer(tmp_path))
    r = run_hook(json.dumps(payload()), tmp_path)
    assert r.returncode == 0 and "additionalContext" in json.loads(r.stdout)["hookSpecificOutput"]
    r = run_hook(json.dumps(payload(source="startup")), tmp_path)
    assert r.returncode == 0 and r.stdout.strip() == ""


def test_process_matches_a_non_ascii_title_sent_as_utf8_bytes(tmp_path):
    # the hook's stdin is decoded as UTF-8, not the locale code page (cp1252 on Windows)
    point(tmp_path, primer(tmp_path), title="café-work")
    env = {**os.environ, "HANDOFF_POINTER_DIR": str(tmp_path / "ptrs")}
    env.pop("PYTHONUTF8", None)
    data = json.dumps(payload(session_title="café-work"), ensure_ascii=False).encode("utf-8")
    r = subprocess.run([sys.executable, str(HERE / "handoff-resume-notice.py")], input=data, capture_output=True, env=env, timeout=30)
    assert r.returncode == 0 and "additionalContext" in json.loads(r.stdout.decode("utf-8"))["hookSpecificOutput"]


@pytest.mark.parametrize("stdin", ["", "not json", "[]", "null", "{}"])
def test_process_never_fails_on_bad_input(tmp_path, stdin):
    r = run_hook(stdin, tmp_path)
    assert r.returncode == 0 and r.stdout.strip() == ""
