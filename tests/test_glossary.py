"""Glossary + UI contract tests: every term resolves, and the UI actually links to it."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gsa_wrap import glossary
from gsa_wrap.api import app

UI = Path(__file__).resolve().parents[1] / "ui" / "index.html"


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


# ---------------------------------------------------------------- glossary data
def test_every_entry_is_complete():
    for key, e in glossary.TERMS.items():
        assert e.get("title"), f"{key} missing title"
        assert e.get("short"), f"{key} missing short"
        assert e.get("long"), f"{key} missing long"
        assert isinstance(e.get("aliases", []), list)


def test_aliases_are_unique_and_resolvable():
    seen = {}
    for key, e in glossary.TERMS.items():
        for alias in [key, *e.get("aliases", [])]:
            low = alias.lower()
            assert low not in seen, f"'{alias}' claimed by both {seen.get(low)} and {key}"
            seen[low] = key


def test_no_duplicate_keys_in_source():
    """A repeated dict key silently shadows the earlier entry in Python."""
    import ast
    src = Path(glossary.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "TERMS":
            keys = [k.value for k in node.value.keys if isinstance(k, ast.Constant)]
            dupes = {k for k in keys if keys.count(k) > 1}
            assert not dupes, f"duplicate glossary keys shadow each other: {dupes}"


def test_lookup_direct_and_alias():
    assert glossary.lookup("usable thread")["key"] == "usable thread"
    assert glossary.lookup("USABLE THREAD")["key"] == "usable thread"
    assert glossary.lookup("worker")["key"] == "thread"
    assert glossary.lookup("?proxies")["key"] == "proxy"
    assert glossary.lookup("dupe check")["key"] == "dupecheck"
    assert glossary.lookup("nope") is None


def test_define_returns_compact_form():
    d = glossary.define("thread", "proxy", "missing")
    assert set(d) == {"thread", "proxy"}
    assert "short" in d["thread"] and "tip" in d["proxy"]


# ---------------------------------------------------------------- api
def test_glossary_endpoint_full(client):
    r = client.get("/glossary")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == len(glossary.TERMS)
    assert "usable thread" in body["index"]


def test_glossary_endpoint_single(client):
    r = client.get("/glossary", params={"term": "live thread"})
    assert r.status_code == 200
    assert r.json()["key"] == "usable thread"


def test_glossary_endpoint_404(client):
    assert client.get("/glossary", params={"term": "zzz"}).status_code == 404


def test_sizing_providers_endpoint(client):
    r = client.get("/sizing/providers")
    assert r.status_code == 200
    body = r.json()
    assert body["providers"] and body["advice"]["headline"]


def test_sizing_steps_endpoint(client):
    r = client.get("/sizing/steps", params={"daily_sends": 1000})
    assert r.status_code == 200
    body = r.json()
    assert len(body["steps"]) >= 5
    assert body["proxy_line_format"] == "IP:PORT:USERNAME:PASSWORD"


def test_captcha_endpoint_includes_layer2(client):
    r = client.get("/sizing/captcha", params={"daily_sends": 1000})
    assert r.status_code == 200
    l2 = r.json()["layer2"]
    assert l2["buy"]["layer_2_primary"]["name"] != l2["buy"]["layer_2_backup"]["name"]


def test_ip_grade_endpoint(client):
    r = client.get("/sizing/ip-grade")
    assert r.status_code == 200
    body = r.json()
    assert body["grades"] and body["advice"]["headline"]
    assert any(g["recommend"] for g in body["grades"])


# ---------------------------------------------------------------- ui contract
def test_ui_has_bubble_container_and_hover_wiring():
    html = UI.read_text(encoding="utf-8")
    assert 'id="bubble"' in html
    assert "data-gloss" in html
    assert "/glossary" in html
    assert "mouseover" in html and "mouseout" in html


def test_ui_gloss_terms_all_exist_in_glossary():
    """Any data-gloss the UI hardcodes must resolve server-side or the bubble is empty.

    data-gloss values come in two flavours:
      * literal HTML attributes        -> must resolve as-is
      * JS template expressions like ${esc(e.key)} -> resolved elsewhere (glossary-driven)
    """
    html = UI.read_text(encoding="utf-8")
    used = set(re.findall(r'data-gloss="([^"]+)"', html))
    assert used, "no glossary hooks in the UI"
    literal = {t for t in used if "${" not in t}
    unresolved = sorted(t for t in literal if glossary.lookup(t) is None)
    assert not unresolved, f"UI references undefined glossary terms: {unresolved}"


def test_ui_dot_helper_arguments_are_real_terms():
    """`dot("...")` is how prose gets a hover bubble — every arg must exist."""
    html = UI.read_text(encoding="utf-8")
    args = set(re.findall(r'\bdot\(\s*"([^"$]+)"', html))
    assert args, "no dot() affordances in the UI"
    unresolved = sorted(t for t in args if glossary.lookup(t) is None)
    assert not unresolved, f"dot() references undefined glossary terms: {unresolved}"


def test_every_schema_field_has_bubble_help():
    """Every field the UI renders needs help text, or its bubble is blank."""
    from gsa_wrap import schema as schema_mod
    for f in schema_mod.llm_schema():
        assert f["ref"], "field without a ref"
        assert f["help"], f"{f['ref']} has no help text for its bubble"
        assert f["group"], f"{f['ref']} has no group"


def test_jargon_terms_used_in_field_help_are_defined():
    """If a field's help text says 'dupecheck' or 'spintax', the bubble must explain it."""
    from gsa_wrap import schema as schema_mod
    jargon = ["dupecheck", "spintax", "blacklist", "timeout", "sublink", "macro"]
    missing = [j for j in jargon if glossary.lookup(j) is None]
    assert not missing, f"jargon used in help text is undefined: {missing}"


def test_ui_theme_is_dark_glass():
    html = UI.read_text(encoding="utf-8")
    assert "backdrop-filter" in html
    assert "saturate(200%)" in html
    assert "-apple-system" in html
    assert "#030407" in html  # near-black base
    assert "rgba(255,255,255,.085)" in html  # translucent hairline border
    assert "feTurbulence" in html  # grain overlay prevents banding


def test_ui_glass_uses_apples_layered_greys():
    """Apple dark uses several greys, never one flat black."""
    html = UI.read_text(encoding="utf-8")
    assert "--txt:#ffffff" in html.replace(" ", "")  # professional Apple white
    for shade in ("--glass:", "--glass-2:", "--glass-3:"):
        assert shade in html, f"missing {shade} layer"


def test_ui_has_the_three_buy_steps():
    html = UI.read_text(encoding="utf-8")
    assert "Where to buy" in html
    assert "Install them into GSA" in html
    assert "captcha subscriptions to buy" in html


def test_ip_thread_is_explained():
    """The single most-asked beginner question must have a real answer."""
    e = glossary.lookup("ip thread")
    assert e and "1 IP = 1 thread" in e["title"]
    assert glossary.lookup("one ip per thread")["key"] == "ip thread"
    assert glossary.lookup("idle thread")
    assert glossary.lookup("max threads")


def test_ip_grade_jargon_is_explained():
    for t in ("ip grade", "coverage", "hostile site", "professional grade", "mobile proxy"):
        assert glossary.lookup(t), f"{t} missing from glossary"
    assert glossary.lookup("premium")["key"] == "professional grade"
    assert glossary.lookup("reach")["key"] == "coverage"


def test_fallback_jargon_is_explained():
    for t in ("ip fallback", "retry failed", "deduction", "cost per success", "escalation"):
        assert glossary.lookup(t), f"{t} missing from glossary"
    assert glossary.lookup("tiered proxies")["key"] == "ip fallback"
    assert glossary.lookup("filtering")["key"] == "deduction"


def test_fallback_endpoint(client):
    r = client.get("/sizing/fallback", params={"pool_size": 300})
    assert r.status_code == 200
    body = r.json()
    assert body["is_native"] is False
    assert body["cost_per_success"]["isp_static"] > 0


def test_imported_list_endpoint(client):
    r = client.get("/sizing/imported-list")
    assert r.status_code == 200
    body = r.json()
    assert body["skipped_stage"] == "scraping"
    assert body["hard_warnings"]


def test_imported_list_jargon_is_explained():
    for t in ("imported list", "export failed", "only root domains", "send limit"):
        assert glossary.lookup(t), f"{t} missing from glossary"
    assert glossary.lookup("csv import")["key"] == "imported list"
    assert glossary.lookup("lead list")["key"] == "imported list"


def test_external_parser_is_explained():
    e = glossary.lookup("external parser")
    assert e and "third-party" in e["short"].lower()
    assert glossary.lookup("third party parser")["key"] == "external parser"


def test_tinyfish_endpoint(client):
    r = client.get("/sizing/tinyfish")
    assert r.status_code == 200
    assert r.json()["honesty"]


def test_farm_jargon_is_explained():
    for t in ("free allowance", "round robin", "daily allowance", "key rotation",
              "account farm", "farming", "stagger", "jitter"):
        assert glossary.lookup(t), f"{t} missing from glossary"


def test_farm_safety_endpoint(client):
    r = client.get("/sizing/farm-safety")
    assert r.status_code == 200
    assert r.json()["is_different_ip_required"]["answer"].startswith("No")


def test_farm_endpoint(client):
    r = client.get("/sizing/farm?accounts=2")
    assert r.status_code == 200
    assert r.json()["what_scales"]["daily_urls"]["total"] == 2000
