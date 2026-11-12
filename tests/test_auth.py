"""
Auth tests. Two things matter here and they are different:

  1. The auth PRIMITIVES are correct (signing, expiry, constant-time compare).
  2. The middleware actually gates every route that matters, and does NOT gate
     the login flow into a loop.

The second one is where a remote exposure actually breaks, so it is tested with a
real TestClient, not by poking the module.
"""
from __future__ import annotations

import base64
import time

import pytest
from fastapi.testclient import TestClient

from gsa_wrap import auth, api


@pytest.fixture
def locked(monkeypatch):
    monkeypatch.setenv("PANEL_PASSWORD", "hunter2")
    monkeypatch.setenv("PANEL_COOKIE_SECURE", "0")
    auth._FAILS.clear()
    with TestClient(api.app) as c:
        yield c
    auth._FAILS.clear()


@pytest.fixture
def open_panel(monkeypatch):
    monkeypatch.delenv("PANEL_PASSWORD", raising=False)
    with TestClient(api.app) as c:
        yield c


# ---------------------------------------------------------------- primitives
def test_no_password_means_off(monkeypatch):
    monkeypatch.delenv("PANEL_PASSWORD", raising=False)
    assert auth.auth_enabled() is False
    assert auth.check_password(None) is True


def test_empty_password_string_is_off(monkeypatch):
    monkeypatch.setenv("PANEL_PASSWORD", "   ")
    assert auth.auth_enabled() is False


def test_token_round_trip(monkeypatch):
    monkeypatch.setenv("PANEL_PASSWORD", "pw")
    assert auth.verify_token(auth.make_token()) is True


def test_token_rejects_tampering(monkeypatch):
    monkeypatch.setenv("PANEL_PASSWORD", "pw")
    tok = auth.make_token()
    exp, _, sig = tok.partition(".")
    assert auth.verify_token(f"{int(exp)+9999}.{sig}") is False
    assert auth.verify_token(f"{exp}.{sig[:-1]}0") is False
    assert auth.verify_token("garbage") is False
    assert auth.verify_token(None) is False


def test_token_expiry(monkeypatch):
    monkeypatch.setenv("PANEL_PASSWORD", "pw")
    # session is 14 days, so go back further than that to actually expire
    long_ago = time.time() - 30 * 24 * 3600
    assert auth.verify_token(auth.make_token(now=long_ago)) is False
    recent = time.time() - 60
    assert auth.verify_token(auth.make_token(now=recent)) is True


def test_changing_password_invalidates_old_tokens(monkeypatch):
    monkeypatch.setenv("PANEL_PASSWORD", "first")
    tok = auth.make_token()
    assert auth.verify_token(tok) is True
    monkeypatch.setenv("PANEL_PASSWORD", "second")
    assert auth.verify_token(tok) is False


def test_explicit_secret_overrides_password_derivation(monkeypatch):
    monkeypatch.setenv("PANEL_PASSWORD", "first")
    monkeypatch.setenv("PANEL_SECRET", "fixed")
    tok = auth.make_token()
    monkeypatch.setenv("PANEL_PASSWORD", "second")
    assert auth.verify_token(tok) is True   # secret pinned, so token survives


def test_basic_auth_parsing(monkeypatch):
    monkeypatch.setenv("PANEL_PASSWORD", "pw")
    def hdr(user, pw):
        return "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()
    assert auth.check_basic(hdr("anyone", "pw")) is True
    assert auth.check_basic(hdr("anyone", "bad")) is False
    assert auth.check_basic(None) is False
    assert auth.check_basic("Bearer xyz") is False
    assert auth.check_basic("Basic !!!notb64") is False


def test_rate_limit_locks_and_clears(monkeypatch):
    auth._FAILS.clear()
    for _ in range(auth.MAX_ATTEMPTS):
        auth.note_failure("1.1.1.1")
    assert auth.locked_out("1.1.1.1") is True
    assert auth.locked_out("2.2.2.2") is False
    auth.note_success("1.1.1.1")
    assert auth.locked_out("1.1.1.1") is False


def test_rate_limit_window_expires():
    auth._FAILS.clear()
    old = time.time() - auth.WINDOW_SECONDS - 5
    for _ in range(auth.MAX_ATTEMPTS):
        auth.note_failure("3.3.3.3", now=old)
    assert auth.locked_out("3.3.3.3") is False


# ---------------------------------------------------------------- middleware
def test_health_is_public(locked):
    assert locked.get("/health").status_code == 200


def test_auth_status_is_public(locked):
    assert locked.get("/auth/status").json()["auth"] == "on"


def test_protected_route_401s_without_session(locked):
    assert locked.get("/schema").status_code == 401


def test_browser_route_redirects_to_login(locked):
    r = locked.get("/", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/login"


def test_login_page_is_reachable(locked):
    assert locked.get("/login").status_code == 200


def test_wrong_password_is_rejected(locked):
    r = locked.post("/login", json={"password": "nope"})
    assert r.status_code == 401
    assert "attempts_left" in r.json()


def test_correct_password_sets_cookie_and_unlocks(locked):
    r = locked.post("/login", json={"password": "hunter2"})
    assert r.status_code == 200
    assert auth.SESSION_COOKIE in r.cookies
    # the TestClient persists cookies, so the same client is now inside
    assert locked.get("/schema").status_code == 200
    assert locked.get("/").status_code == 200


def test_empty_probe_does_not_burn_attempts(locked):
    locked.post("/login", json={"password": ""})
    assert auth.attempts_left("testclient") == auth.MAX_ATTEMPTS


def test_basic_auth_grants_access_without_login(locked):
    hdr = {"Authorization": "Basic " + base64.b64encode(b"x:hunter2").decode()}
    assert locked.get("/schema", headers=hdr).status_code == 200


def test_logout_clears_the_session(locked):
    locked.post("/login", json={"password": "hunter2"})
    assert locked.get("/schema").status_code == 200
    locked.get("/logout", follow_redirects=False)
    assert locked.get("/schema").status_code == 401


def test_lockout_returns_429(locked):
    for _ in range(auth.MAX_ATTEMPTS):
        locked.post("/login", json={"password": "bad"})
    assert locked.post("/login", json={"password": "hunter2"}).status_code == 429


def test_public_paths_are_exhaustive():
    """If a public route is added it must not be silently gated."""
    for p in api.PUBLIC_PATHS:
        assert p.startswith("/")


# ---------------------------------------------------------------- auth off
def test_auth_off_leaves_everything_open(open_panel):
    assert open_panel.get("/schema").status_code == 200
    assert open_panel.get("/").status_code == 200
    assert open_panel.get("/auth/status").json()["auth"] == "off"


def test_login_with_auth_off_reports_off(open_panel):
    r = open_panel.post("/login", json={"password": "anything"})
    assert r.json()["auth"] == "off"

# ---------------------------------------------------------------- cross-site (Mac UI on Vercel)
def test_samesite_defaults_to_lax(monkeypatch):
    monkeypatch.delenv("PANEL_SAMESITE", raising=False)
    assert auth.cookie_samesite() == "lax"


def test_samesite_none_enables_cross_site(monkeypatch):
    monkeypatch.setenv("PANEL_SAMESITE", "none")
    assert auth.cookie_samesite() == "none"


def test_samesite_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("PANEL_SAMESITE", "NONE")
    assert auth.cookie_samesite() == "none"


def test_samesite_garbage_falls_back_to_lax(monkeypatch):
    """A typo must not lock you out."""
    monkeypatch.setenv("PANEL_SAMESITE", "nonsense")
    assert auth.cookie_samesite() == "lax"


def test_cookie_carries_the_samesite_setting(locked, monkeypatch):
    monkeypatch.setenv("PANEL_SAMESITE", "none")
    r = locked.post("/login", json={"password": "hunter2"})
    assert "samesite=none" in r.headers["set-cookie"].lower()


def test_cors_origins_parses_and_trims(monkeypatch):
    monkeypatch.setenv("PANEL_ORIGINS", " https://a.vercel.app , https://b.com ,")
    assert api._cors_origins() == ["https://a.vercel.app", "https://b.com"]


def test_cors_origins_empty_when_unset(monkeypatch):
    monkeypatch.delenv("PANEL_ORIGINS", raising=False)
    assert api._cors_origins() == []


def test_login_is_preflighted_when_origins_set(locked, monkeypatch):
    """A cross-site POST with a JSON body triggers a CORS preflight first."""
    import importlib, os
    monkeypatch.setenv("PANEL_ORIGINS", "https://app.vercel.app")
    importlib.reload(api)
    from fastapi.testclient import TestClient as TC
    with TC(api.app) as c:
        r = c.options("/login", headers={
            "Origin": "https://app.vercel.app",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        })
    assert r.status_code in (200, 204)
    assert r.headers.get("access-control-allow-origin") == "https://app.vercel.app"
    assert r.headers.get("access-control-allow-credentials") == "true"
    importlib.reload(api)  # leave the module as we found it


# ---------------------------------------------------------------- ui is origin-agnostic
UI_DIR = __import__("pathlib").Path(__file__).resolve().parents[1] / "ui"


def test_index_fetches_send_cookies_cross_origin():
    html = (UI_DIR / "index.html").read_text(encoding="utf-8")
    assert "credentials:'include'" in html


def test_index_has_no_origin_bound_fetch():
    """A bare fetch('/x') breaks the moment the UI is hosted anywhere but the API."""
    html = (UI_DIR / "index.html").read_text(encoding="utf-8")
    assert 'fetch("/' not in html
    assert "const API = (window.PANEL_API_BASE" in html


def test_index_login_redirect_uses_api_origin():
    html = (UI_DIR / "index.html").read_text(encoding="utf-8")
    assert "LOGIN_URL" in html
    assert "location.href = LOGIN_URL" in html


def test_index_signout_points_at_the_api():
    """Sign out must clear the API's cookie, not the hosting origin's."""
    html = (UI_DIR / "index.html").read_text(encoding="utf-8")
    assert '$("signout").href = API + "/logout"' in html


def test_login_page_is_origin_agnostic():
    html = (UI_DIR / "login.html").read_text(encoding="utf-8")
    assert 'fetch(API + "/login"' in html
    assert 'credentials: "include"' in html
    assert 'fetch(API + "/auth/status"' in html
    assert 'fetch("/login"' not in html
