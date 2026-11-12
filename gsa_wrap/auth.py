"""
Single-password lock for the panel, so it can be exposed beyond localhost.

Design decisions (deliberate, and why):

  * ONE password, from the environment (`PANEL_PASSWORD`) — matches the brief.
  * No user database, no sessions stored server-side. A signed cookie carries the
    expiry; the signature is HMAC-SHA256 over that expiry, keyed with a secret.
    So a restart does not log everyone out, and there is no session table to lose.
  * Constant-time comparison everywhere a secret is checked, so a timing attack
    cannot recover the password one byte at a time.
  * The signing secret is derived from the password when `PANEL_SECRET` is unset.
    Changing the password therefore invalidates old cookies automatically, which
    is the behaviour we want.
  * Basic auth is also accepted, so `curl` and the API work without a login dance.
  * Auth is OPT-IN: set no password and behaviour is exactly as before (open),
    which keeps local-only use friction-free.

What this deliberately does NOT do: multi-user accounts, roles, password resets,
or CSRF tokens. For a single shared password behind TLS that is the right scope.
SameSite=Lax on the cookie covers the practical CSRF case for JSON POSTs.

Cross-site note (Mac UI on Vercel → tunnel → this backend): a cross-site fetch
will NOT send a SameSite=Lax cookie, so the login silently fails. Set
`PANEL_SAMESITE=none` (requires HTTPS, i.e. the tunnel) to allow that mode. The
default stays `lax` because same-origin serving is the common case and `none`
without HTTPS breaks the cookie outright.
"""

from __future__ import annotations

import base64
import hmac
import os
import time
from hashlib import sha256

SESSION_COOKIE = "gsa_panel"
DEFAULT_SESSION_HOURS = 336  # 14 days — long enough not to annoy, short enough to expire
_SECRET_SALT = b"gsa-panel-cookie-v1"


def configured_password() -> str | None:
    """The password, from env. Empty/absent means auth is OFF."""
    pw = os.environ.get("PANEL_PASSWORD")
    if pw is None:
        return None
    pw = pw.strip()
    return pw or None


def auth_enabled() -> bool:
    return configured_password() is not None


def _secret() -> bytes:
    """
    Signing key. Prefers an explicit PANEL_SECRET; otherwise derives from the
    password so that rotating the password also invalidates existing cookies.
    """
    explicit = os.environ.get("PANEL_SECRET")
    if explicit:
        return explicit.encode("utf-8")
    pw = configured_password() or ""
    return hmac.new(_SECRET_SALT, pw.encode("utf-8"), sha256).digest()


def session_hours() -> int:
    try:
        return max(1, int(os.environ.get("PANEL_SESSION_HOURS", DEFAULT_SESSION_HOURS)))
    except ValueError:
        return DEFAULT_SESSION_HOURS


def cookie_samesite() -> str:
    """
    SameSite policy for the session cookie.

    `lax` (default) is correct when the UI is served by this same app. When the
    UI is hosted cross-site (e.g. on Vercel) and calls this backend directly, a
    cross-site cookie is required, which means `none` — and `none` only works
    over HTTPS. Invalid values fall back to `lax` rather than raising, so a typo
    in an env var cannot lock you out.
    """
    value = (os.environ.get("PANEL_SAMESITE") or "lax").strip().lower()
    return value if value in ("lax", "strict", "none") else "lax"


def cookie_domain() -> str | None:
    """
    Optional cookie scope, e.g. `.yourdomain.com`.

    Only needed when the UI is on a sibling subdomain (app.example.com talking to
    api.example.com). Sibling subdomains are *same-site*, so the cookie stays
    first-party and `lax` keeps working — no `none`/third-party-cookie gamble.
    Unset means a normal host-only cookie.
    """
    domain = (os.environ.get("PANEL_COOKIE_DOMAIN") or "").strip()
    return domain or None


def check_password(candidate: str | None) -> bool:
    """Constant-time password check. False when auth is off is never used."""
    pw = configured_password()
    if pw is None:
        return True
    if candidate is None:
        return False
    return hmac.compare_digest(candidate, pw)


def make_token(*, now: float | None = None) -> str:
    """`<expiry>.<hex signature>` — nothing secret is stored client-side."""
    now = time.time() if now is None else now
    exp = int(now + session_hours() * 3600)
    payload = str(exp).encode("ascii")
    sig = hmac.new(_secret(), payload, sha256).hexdigest()
    return f"{exp}.{sig}"


def verify_token(token: str | None, *, now: float | None = None) -> bool:
    """True only for a well-formed, correctly-signed, unexpired token."""
    if not token or "." not in token:
        return False
    exp_s, _, sig = token.partition(".")
    try:
        exp = int(exp_s)
    except ValueError:
        return False
    now = time.time() if now is None else now
    if exp <= now:
        return False
    expected = hmac.new(_secret(), exp_s.encode("ascii"), sha256).hexdigest()
    return hmac.compare_digest(sig, expected)


def parse_basic(header: str | None) -> tuple[str, str] | None:
    """Decode an `Authorization: Basic ...` header to (user, password)."""
    if not header:
        return None
    scheme, _, blob = header.partition(" ")
    if scheme.lower() != "basic" or not blob:
        return None
    try:
        decoded = base64.b64decode(blob.strip(), validate=True).decode("utf-8", "replace")
    except Exception:
        return None
    if ":" not in decoded:
        return None
    user, _, pw = decoded.partition(":")
    return user, pw


def check_basic(header: str | None) -> bool:
    parsed = parse_basic(header)
    if parsed is None:
        return False
    # username is ignored: single shared password, so only the password matters
    _, pw = parsed
    return check_password(pw)


# --------------------------------------------------------------------------
# brute-force shaping — in-memory, good enough for a single password
# --------------------------------------------------------------------------
_FAILS: dict[str, list[float]] = {}
WINDOW_SECONDS = 300
MAX_ATTEMPTS = 10


def note_failure(ip: str, *, now: float | None = None) -> None:
    now = time.time() if now is None else now
    hits = [t for t in _FAILS.get(ip, []) if now - t < WINDOW_SECONDS]
    hits.append(now)
    _FAILS[ip] = hits


def note_success(ip: str) -> None:
    _FAILS.pop(ip, None)


def locked_out(ip: str, *, now: float | None = None) -> bool:
    now = time.time() if now is None else now
    hits = [t for t in _FAILS.get(ip, []) if now - t < WINDOW_SECONDS]
    return len(hits) >= MAX_ATTEMPTS


def attempts_left(ip: str) -> int:
    return max(0, MAX_ATTEMPTS - len(_FAILS.get(ip, [])))
