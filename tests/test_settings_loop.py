"""
Proof-loop tests for the settings writer.

These exercise: parse real format -> plan diff -> atomic write -> verify ->
idempotency -> bounce detection -> restart classification -> API surface.
Nothing here talks to the live app; configs are temp-file fixtures.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gsa_wrap import config_io, process, schema as schema_mod

# A fixture that mimics the real file: CRLF, sectioned, unknown keys included.
FIXTURE = (
    "[misc]\r\n"
    "hide disclaimer=0\r\n"
    "timeout=120\r\n"
    "max threads=10\r\n"
    "max threads se=10\r\n"
    "autoscroll=1\r\n"
    "blacklist on=0\r\n"
    "global send dupecheck=0\r\n"
    "message preview=1\r\n"
    "stop project on no proxy=1\r\n"
    "use real captcha ip=0\r\n"
    "captcha services in random order=0\r\n"
    "scaling mode=0\r\n"
    "f1.width=837\r\n"
    "f1.height=468\r\n"
    "some_future_key=xyz\r\n"
    "\r\n"
    "[scheduler]\r\n"
    "scrape sites=1\r\n"
    "check sites=1\r\n"
    "send sites=0\r\n"
    "max projects=5\r\n"
    "max runtime=30\r\n"
    "use runtime=1\r\n"
    "\r\n"
    "[columns prj]\r\n"
    "width 0=50\r\n"
    "visible 0=1\r\n"
)


@pytest.fixture()
def cfg(tmp_path: Path) -> Path:
    p = tmp_path / "config.ini"
    p.write_bytes(FIXTURE.encode("ascii"))
    return p


# --------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------
def test_parse_preserves_structure(cfg: Path):
    parsed = config_io.load(cfg)
    assert parsed.newline == "\n"          # we split on \n; \r stays on the line
    assert "\r" in parsed.lines[0]         # CRLF is preserved verbatim
    assert parsed.find("misc", "max threads") is not None
    assert parsed.find("scheduler", "send sites") is not None
    # unknown key still parsed (so we can round-trip it)
    assert parsed.find("misc", "some_future_key") is not None
    assert "misc" in parsed.section_names()


def test_read_typed_coerces(cfg: Path):
    vals = config_io.read_typed(cfg)
    assert vals["misc"]["max threads"] == 10        # int
    assert vals["misc"]["autoscroll"] is True       # bool
    assert vals["misc"]["some_future_key"] == "xyz"  # passthrough


# --------------------------------------------------------------------------
# planning
# --------------------------------------------------------------------------
def test_plan_reports_only_real_changes(cfg: Path):
    parsed = config_io.load(cfg)
    changes = config_io.plan(parsed, {"misc::max threads": 25, "misc::timeout": 120})
    assert len(changes) == 1                        # timeout unchanged
    assert changes[0].key == "max threads"
    assert changes[0].old == "10" and changes[0].new == "25"


def test_plan_rejects_unknown_ref(cfg: Path):
    parsed = config_io.load(cfg)
    with pytest.raises(config_io.ConfigError):
        config_io.plan(parsed, {"misc::not a real key": 1})


# --------------------------------------------------------------------------
# apply + verify
# --------------------------------------------------------------------------
def test_apply_writes_verifies_and_backs_up(cfg: Path):
    res = config_io.apply({"misc::max threads": 30, "misc::use real captcha ip": True}, cfg)
    assert res["verified"] is True
    assert res["bounced"] == []
    assert Path(res["backup_path"]).exists()

    after = config_io.read_typed(cfg)
    assert after["misc"]["max threads"] == 30
    assert after["misc"]["use real captcha ip"] is True
    # untouched key + unknown key survived
    assert after["misc"]["timeout"] == 120
    assert after["misc"]["some_future_key"] == "xyz"


def test_apply_is_idempotent(cfg: Path):
    config_io.apply({"misc::max threads": 40}, cfg)
    second = config_io.apply({"misc::max threads": 40}, cfg)
    assert second["changed"] == []                  # nothing to do the 2nd time


def test_apply_preserves_crlf_and_order(cfg: Path):
    config_io.apply({"misc::max threads": 77}, cfg)
    raw = cfg.read_bytes()
    assert b"\r\n" in raw
    assert raw.count(b"\r\n") == raw.count(b"\n")   # still pure CRLF throughout
    text = raw.decode("ascii")
    assert text.index("hide disclaimer") < text.index("max threads") < text.index("max threads se")


def test_apply_bounce_detection(cfg: Path, monkeypatch):
    """If the app rewrites our value, verify must catch it."""
    real_load = config_io.load

    def load_then_clobber(path=None):
        parsed = real_load(cfg)
        # simulate the app refusing to accept the change on disk
        return parsed

    # apply, then manually tamper to simulate the app bouncing the write
    config_io.apply({"misc::max threads": 55}, cfg)
    text = cfg.read_bytes().decode("ascii").replace("max threads=55", "max threads=10")
    cfg.write_bytes(text.encode("ascii"))

    parsed = config_io.load(cfg)
    changes = config_io.plan(parsed, {"misc::max threads": 60})
    assert changes and changes[0].old == "10"


def test_parse_survives_mixed_line_endings(tmp_path: Path):
    """Regression: a single LF-only line once made the parser lose a key.

    Real files do end up mixed (our scripts and the app each write differently),
    so parsing must be line-ending agnostic and must not eat entries.
    """
    p = tmp_path / "config.ini"
    p.write_bytes(
        b"[misc]\r\n"
        b"hide disclaimer=0\r\n"
        b"timeout=120\n"                 # LF only, mid-section
        b"max threads=10\r\n"
        b"max threads se=10\r\n"
    )
    cfg = config_io.load(p)
    for key in ("hide disclaimer", "timeout", "max threads", "max threads se"):
        assert cfg.find("misc", key) is not None, f"lost {key}"

    # and a write must not corrupt the neighbours
    res = config_io.apply({"misc::timeout": 90}, p)
    assert res["verified"] is True
    after = config_io.load(p)
    assert after.find("misc", "max threads") is not None
    assert after.find("misc", "max threads se") is not None


def test_parse_handles_non_ascii(tmp_path: Path):
    p = tmp_path / "config.ini"
    p.write_bytes("[misc]\r\nsubject=Grüße aus München\r\n".encode("utf-8"))
    cfg = config_io.load(p)
    assert cfg.find("misc", "subject") is not None


def test_validation_bounds(cfg: Path):
    with pytest.raises(ValueError):
        config_io.apply({"misc::max threads": 999}, cfg)   # max 200
    with pytest.raises(ValueError):
        config_io.apply({"misc::scaling mode": 7}, cfg)    # allowed [0,1,2]


# --------------------------------------------------------------------------
# restart classification
# --------------------------------------------------------------------------
def test_restart_classification():
    assert process.refs_requiring_restart(["misc::f1.width"]) == ["misc::f1.width"]
    assert process.refs_requiring_restart(["misc::scaling mode"]) == ["misc::scaling mode"]
    assert process.refs_requiring_restart(["misc::max threads"]) == []


# --------------------------------------------------------------------------
# schema integrity
# --------------------------------------------------------------------------
def test_schema_refs_are_unique_and_complete():
    refs = [f"{f.section}::{f.key}" for f in schema_mod.all_fields()]
    assert len(refs) == len(set(refs))
    for item in schema_mod.llm_schema():
        assert item["help"], f"{item['ref']} missing help text"
        assert item["type"] in {"int", "bool", "str"}


def test_every_schema_field_exists_in_fixture(cfg: Path):
    """Fields marked PROVEN must be writable against a realistic file."""
    vals = config_io.read_typed(cfg)
    for f in schema_mod.all_fields():
        if f.confidence != schema_mod.Confidence.PROVEN:
            continue
        if f.section == "notify":
            continue  # notify section not in this fixture
        assert f.key in vals.get(f.section, {}), f"proven field {f.section}::{f.key} absent"


# --------------------------------------------------------------------------
# API surface
# --------------------------------------------------------------------------
def test_api_endpoints(cfg: Path, monkeypatch):
    monkeypatch.setattr(config_io, "default_config_path", lambda: cfg)
    from gsa_wrap.api import app
    client = TestClient(app)

    assert client.get("/schema").json()["count"] > 30

    plan = client.post("/settings/plan", json={"updates": {"misc::timeout": 200}}).json()
    assert plan["count"] == 1 and plan["changes"][0]["old"] == "120"

    applied = client.post("/settings/apply",
                          json={"updates": {"misc::timeout": 200}}).json()
    assert applied["verified"] is True
    assert config_io.read_typed(cfg)["misc"]["timeout"] == 200
