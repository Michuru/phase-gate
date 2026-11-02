"""Tests for handoff_pointer.py. Run from this folder: python -m pytest test_handoff_pointer.py"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import handoff_pointer as hp  # noqa: E402

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
SID = "0dfa82e1-35b1-43ee-9ad2-bc249c96d1c3"


@pytest.fixture(autouse=True)
def pdir(tmp_path, monkeypatch):
    monkeypatch.setenv("HANDOFF_POINTER_DIR", str(tmp_path / "ptrs"))
    return tmp_path / "ptrs"


def make_primer(tmp_path, repo="r1", name="2026-10-31-x.md", top=True):
    d = tmp_path / repo / ".claude" / "handoffs"
    if not top:
        d = d / "archive"
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text("# Handoff: x\n", encoding="utf-8")
    return str(p)


def make_transcript(tmp_path, titles=("auto-resume-handoff",), extra=True):
    t = tmp_path / "t.jsonl"
    lines = []
    if extra:
        lines.append(json.dumps({"type": "user", "message": {"content": "hi"}}))
    for title in titles:
        lines.append(json.dumps({"type": "custom-title", "customTitle": title, "sessionId": SID}))
        lines.append(json.dumps({"type": "agent-name", "agentName": title, "sessionId": SID}))
    t.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(t)


def test_custom_title_takes_the_last_record(tmp_path):
    assert hp.custom_title(make_transcript(tmp_path, titles=("first", "second"))) == "second"


def test_custom_title_none_without_a_record_or_file(tmp_path):
    t = tmp_path / "plain.jsonl"
    t.write_text(json.dumps({"type": "agent-name", "agentName": "ghost"}) + "\n", encoding="utf-8")
    assert hp.custom_title(str(t)) is None
    assert hp.custom_title(str(tmp_path / "missing.jsonl")) is None


def test_custom_title_ignores_marker_inside_other_record(tmp_path):
    t = tmp_path / "x.jsonl"
    t.write_text(json.dumps({"type": "user", "message": {"content": 'say "custom-title" aloud'}}) + "\n", encoding="utf-8")
    assert hp.custom_title(str(t)) is None


def test_write_then_find_roundtrip(tmp_path, pdir):
    primer = make_primer(tmp_path)
    e = hp.write(SID, make_transcript(tmp_path), primer, "faa98d", now=NOW)
    assert e["name"] == "auto-resume-handoff" and e["ref"] == "faa98d"
    assert (pdir / f"{SID}.json").is_file()
    assert not list(pdir.glob("*.tmp"))
    hits = hp.find("auto-resume-handoff", now=NOW + timedelta(minutes=5))
    assert len(hits) == 1 and hits[0]["primer"].lower().endswith("2026-10-31-x.md")


def test_write_without_owner_name_raises(tmp_path):
    t = tmp_path / "plain.jsonl"
    t.write_text('{"type":"user"}\n', encoding="utf-8")
    with pytest.raises(hp.NoOwnerName):
        hp.write(SID, str(t), make_primer(tmp_path), "faa98d", now=NOW)


def test_write_rejects_bad_ref_and_bad_id(tmp_path):
    t, p = make_transcript(tmp_path), make_primer(tmp_path)
    for bad in ("", "FAA98D", "faa98", "faa98dd", "zzzzzz"):
        with pytest.raises(ValueError):
            hp.write(SID, t, p, bad, now=NOW)
    with pytest.raises(ValueError):
        hp.write("../evil", t, p, "faa98d", now=NOW)


def test_explicit_name_overrides_transcript(tmp_path):
    e = hp.write(SID, make_transcript(tmp_path), make_primer(tmp_path), "faa98d", name="other", now=NOW)
    assert e["name"] == "other"


def test_second_handoff_by_same_window_overwrites(tmp_path, pdir):
    t = make_transcript(tmp_path)
    hp.write(SID, t, make_primer(tmp_path, name="2026-10-31-a.md"), "faa98d", now=NOW)
    hp.write(SID, t, make_primer(tmp_path, name="2026-10-31-b.md"), "faa98d", now=NOW + timedelta(minutes=10))
    hits = hp.find("auto-resume-handoff", now=NOW + timedelta(minutes=11))
    assert len(hits) == 1 and hits[0]["primer"].endswith("2026-10-31-b.md")


def test_later_handoff_by_same_window_after_clear_supersedes_the_earlier_pointer(tmp_path, pdir):
    # the /clear changed the session id but not the name or the [ref]: one window, two handoffs
    t = make_transcript(tmp_path)
    hp.write(SID, t, make_primer(tmp_path, name="a.md"), "faa98d", now=NOW)
    new_sid = "9b6e8918-58b4-4ccb-b9cf-67ea72659329"
    hp.write(new_sid, t, make_primer(tmp_path, name="b.md"), "faa98d", now=NOW + timedelta(minutes=30))
    assert not (pdir / f"{SID}.json").exists()
    hits = hp.find("auto-resume-handoff", now=NOW + timedelta(minutes=31))
    assert len(hits) == 1 and hits[0]["primer"].endswith("b.md")


def test_supersede_leaves_a_different_window_and_unreadable_files(tmp_path, pdir):
    t = make_transcript(tmp_path)
    hp.write(SID, t, make_primer(tmp_path, name="a.md"), "ce63ea", now=NOW)  # same name, other window
    (pdir / "junk.json").write_text("{nope", encoding="utf-8")
    hp.write("9b6e8918-58b4-4ccb-b9cf-67ea72659329", t, make_primer(tmp_path, name="b.md"), "faa98d", now=NOW)
    assert (pdir / f"{SID}.json").exists() and (pdir / "junk.json").exists()
    assert len(hp.find("auto-resume-handoff", now=NOW)) == 2  # two windows: the hook stays silent


def test_supersede_keeps_same_ref_under_a_different_name(tmp_path, pdir):
    # a ref-only supersede would delete this: the name must match too
    hp.write(SID, make_transcript(tmp_path, titles=("other-name",)), make_primer(tmp_path, name="a.md"), "faa98d", now=NOW)
    hp.write("9b6e8918-58b4-4ccb-b9cf-67ea72659329", make_transcript(tmp_path), make_primer(tmp_path, name="b.md"), "faa98d", now=NOW)
    assert (pdir / f"{SID}.json").exists()


def test_id_and_ref_reject_a_trailing_newline(tmp_path):
    t, p = make_transcript(tmp_path), make_primer(tmp_path)
    with pytest.raises(ValueError):
        hp.write(SID, t, p, "faa98d\n", now=NOW)
    with pytest.raises(ValueError):
        hp.write(SID + "\n", t, p, "faa98d", now=NOW)


def test_non_ascii_name_roundtrips(tmp_path):
    hp.write(SID, make_transcript(tmp_path, titles=("café-work",)), make_primer(tmp_path), "faa98d", now=NOW)
    assert len(hp.find("café-work", now=NOW)) == 1


def test_find_skips_wrong_name(tmp_path):
    hp.write(SID, make_transcript(tmp_path), make_primer(tmp_path), "faa98d", now=NOW)
    assert hp.find("auto-resume", now=NOW) == []
    assert hp.find("AUTO-RESUME-HANDOFF", now=NOW) == []


def test_find_skips_old_pointer(tmp_path):
    hp.write(SID, make_transcript(tmp_path), make_primer(tmp_path), "faa98d", now=NOW)
    assert hp.find("auto-resume-handoff", now=NOW + timedelta(hours=2, minutes=1)) == []
    assert len(hp.find("auto-resume-handoff", now=NOW + timedelta(hours=1, minutes=59))) == 1


def test_find_skips_future_dated_pointer(tmp_path):
    hp.write(SID, make_transcript(tmp_path), make_primer(tmp_path), "faa98d", now=NOW + timedelta(hours=3))
    assert hp.find("auto-resume-handoff", now=NOW) == []


def test_find_skips_primer_gone_or_archived(tmp_path):
    primer = make_primer(tmp_path)
    hp.write(SID, make_transcript(tmp_path), primer, "faa98d", now=NOW)
    Path(primer).unlink()
    assert hp.find("auto-resume-handoff", now=NOW) == []
    archived = make_primer(tmp_path, name="2026-10-31-z.md", top=False)
    hp.write(SID, make_transcript(tmp_path), archived, "faa98d", now=NOW)
    assert hp.find("auto-resume-handoff", now=NOW) == []


def test_find_two_pointers_same_name_returns_both(tmp_path):
    t = make_transcript(tmp_path)
    hp.write(SID, t, make_primer(tmp_path, name="a.md"), "faa98d", now=NOW)
    hp.write("11111111-2222-3333-4444-555555555555", t, make_primer(tmp_path, name="b.md"), "ce63ea", now=NOW)
    assert len(hp.find("auto-resume-handoff", now=NOW)) == 2


def test_find_ignores_malformed_files(tmp_path, pdir):
    hp.write(SID, make_transcript(tmp_path), make_primer(tmp_path), "faa98d", now=NOW)
    (pdir / "bad.json").write_text("{not json", encoding="utf-8")
    (pdir / "list.json").write_text("[1, 2]", encoding="utf-8")
    (pdir / "noref.json").write_text(json.dumps({"name": "auto-resume-handoff", "primer": "x", "written": NOW.isoformat()}), encoding="utf-8")
    assert len(hp.find("auto-resume-handoff", now=NOW)) == 1


def test_find_with_missing_directory_is_empty():
    assert hp.find("anything") == []


def test_write_prunes_week_old_pointers_but_leaves_unreadable_files(tmp_path, pdir):
    t = make_transcript(tmp_path)
    hp.write("old-session", t, make_primer(tmp_path, name="old.md"), "faa98d", now=NOW - timedelta(days=8))
    (pdir / "junk.json").write_text("{not json", encoding="utf-8")
    hp.write(SID, t, make_primer(tmp_path, name="new.md"), "ce63ea", now=NOW)
    assert not (pdir / "old-session.json").exists()
    assert (pdir / "junk.json").exists() and (pdir / f"{SID}.json").exists()


def test_cli_write_find_name_and_exit_codes(tmp_path, capsys):
    t, p = make_transcript(tmp_path), make_primer(tmp_path)
    assert hp.main(["name", "--transcript", t]) == 0
    assert capsys.readouterr().out.strip() == "auto-resume-handoff"
    assert hp.main(["write", "--session-id", SID, "--transcript", t, "--primer", p, "--ref", "faa98d"]) == 0
    assert "WROTE" in capsys.readouterr().out
    assert hp.main(["find", "--name", "auto-resume-handoff"]) == 0
    assert json.loads(capsys.readouterr().out.strip().splitlines()[0])["ref"] == "faa98d"
    assert hp.main(["find", "--name", "nobody"]) == 1
    plain = tmp_path / "plain.jsonl"
    plain.write_text('{"type":"user"}\n', encoding="utf-8")
    assert hp.main(["name", "--transcript", str(plain)]) == 1
    assert hp.main(["write", "--session-id", SID, "--transcript", str(plain), "--primer", p, "--ref", "faa98d"]) == 3
    assert "NO-OWNER-NAME" in capsys.readouterr().out
    assert hp.main(["write", "--session-id", SID, "--transcript", t, "--primer", p, "--ref", "nope"]) == 2
    assert hp.main(["write"]) == 2
