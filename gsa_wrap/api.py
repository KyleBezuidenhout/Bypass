"""
FastAPI service exposing the GSA settings model + writer + process control.

Run (recommended — generates a password, binds the LAN):
    .\\run-panel.ps1

Run (manual):
    uvicorn gsa_wrap.api:app --host 0.0.0.0 --port 8000

Remote exposure: set PANEL_PASSWORD to lock the panel with a single password.
Unset = open, exactly as before. See upgrades-roadmap/remote-access.md.

This is the "spine" described in the architecture: a typed model of their app,
a safe writer, and process control. The LLM layer (next phase) sits on top of
/schema (to know the fields) and /settings/plan|apply (to make changes).

Endpoints
---------
GET  /health                     process + file status (public)
GET  /auth/status                is the lock on (public)
GET  /login, POST /login         password page + session issue
GET  /logout                     clear the session
GET  /schema                     every field, with help text (LLM contract)
GET  /settings                   current values, typed
POST /settings/plan              dry-run: what would change, no writes
POST /settings/apply             write atomically, verify, report bounces
POST /app/start|stop|restart     process control
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from . import auth as auth_mod
from . import config_io, process, schema as schema_mod, nl, project_io, import_csv, sizing, glossary

UI_DIR = Path(__file__).resolve().parent.parent / "ui"

app = FastAPI(
    title="GSA Website Contact wrapper",
    version="0.1.0",
    description="Typed settings model and safe writer for GSA Website Contact v6.42.",
)

# CORS is only needed when the UI is served from a different origin than this
# API — i.e. the Mac/Vercel setup where the frontend calls the tunnel directly.
# With the default same-origin serving it stays inert. `PANEL_ORIGINS` is a
# comma list; `credentials` must be on for the session cookie to travel.
def _cors_origins() -> list[str]:
    return [o.strip() for o in os.environ.get("PANEL_ORIGINS", "").split(",") if o.strip()]


if _cors_origins():
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# Paths reachable without a session: the login flow itself and liveness.
PUBLIC_PATHS = {"/login", "/logout", "/health", "/auth/status"}


# --------------------------------------------------------------------------
# models
# --------------------------------------------------------------------------
class Updates(BaseModel):
    # ref = "section::key" -> value
    updates: dict[str, Any] = Field(
        ..., examples=[{"misc::max threads": 10, "misc::timeout": 120}]
    )
    apply: bool = True


class ApplyRequest(Updates):
    apply: bool = True
    restart_if_needed: bool = False


class NlRequest(BaseModel):
    text: str = Field(..., examples=["scrape dentists in Pretoria, 10 threads, skip free mail"])
    prefer: str = Field("auto", description="auto | llm | rules")
    apply: bool = Field(False, description="also write it if the plan is clean")
    restart_if_needed: bool = False


class ProjectRequest(BaseModel):
    name: str = Field(..., description="project name (without .prj) or absolute path")
    updates: dict[str, Any] = Field(default_factory=dict, examples=[{"misc::proxies for parse": True}])
    keywords: list[str] | None = None
    apply: bool = True
    restart_if_needed: bool = False


class ImportRequest(BaseModel):
    text: str = Field("", description="pasted CSV / TSV / 'url | message' lines")
    filename: str = ""
    project: str = ""
    save_name: str = ""
    apply_project: bool = False
    delete_after: bool = True


# --------------------------------------------------------------------------
# password lock (opt-in: set PANEL_PASSWORD to enable)
# --------------------------------------------------------------------------
@app.middleware("http")
async def password_lock(request: Request, call_next):
    if not auth_mod.auth_enabled():
        return await call_next(request)

    path = request.url.path
    if path in PUBLIC_PATHS:
        return await call_next(request)

    # API clients may use Basic auth instead of a cookie — handy for curl/scripts.
    if auth_mod.check_basic(request.headers.get("authorization")):
        return await call_next(request)

    if auth_mod.verify_token(request.cookies.get(auth_mod.SESSION_COOKIE)):
        return await call_next(request)

    # Unauthenticated: JSON callers get 401, browsers get the login page.
    wants_json = path.startswith(("/schema", "/settings", "/sizing", "/nl",
                                  "/project", "/projects", "/import", "/glossary",
                                  "/app", "/logs"))
    if wants_json:
        return JSONResponse({"detail": "auth required"}, status_code=401)
    return RedirectResponse("/login", status_code=302)


class LoginRequest(BaseModel):
    password: str = Field(..., examples=["hunter2"])


@app.get("/auth/status")
def auth_status() -> dict:
    """Public: is the lock on, and is this caller already inside?"""
    return {"auth": "on" if auth_mod.auth_enabled() else "off"}


@app.post("/login")
def login(req: LoginRequest, request: Request) -> JSONResponse:
    """
    Check the single password and set a signed session cookie.
    Rate-limited per IP so a remote exposure is not brute-forced.
    """
    if not auth_mod.auth_enabled():
        return JSONResponse({"ok": True, "auth": "off"})

    ip = (request.client.host if request.client else "?")
    if auth_mod.locked_out(ip):
        return JSONResponse(
            {"ok": False, "detail": "too many attempts, wait 5 minutes"},
            status_code=429,
        )

    if not auth_mod.check_password(req.password):
        # An empty probe should not burn an attempt; the login page sends one on load.
        if req.password:
            auth_mod.note_failure(ip)
        return JSONResponse(
            {"ok": False, "detail": "wrong password",
             "attempts_left": auth_mod.attempts_left(ip)},
            status_code=401,
        )

    auth_mod.note_success(ip)
    resp = JSONResponse({"ok": True})
    cookie_kwargs = dict(
        max_age=auth_mod.session_hours() * 3600,
        httponly=True,
        # lax when same-origin; set PANEL_SAMESITE=none (over HTTPS) when the UI
        # is hosted cross-site, e.g. a Vercel frontend calling this tunnel.
        samesite=auth_mod.cookie_samesite(),
        # Secure-by-default, but auto-relaxed for plain-HTTP access (e.g. a LAN IP),
        # because a browser will not store a Secure cookie over http:// and you get
        # a silent login loop. PANEL_COOKIE_SECURE overrides either way.
        secure=_cookie_secure(request),
        path="/",
    )
    domain = auth_mod.cookie_domain()
    if domain:
        # only needed for sibling subdomains (app.x.com <-> api.x.com)
        cookie_kwargs["domain"] = domain
    else:
        # Cloudflare's edge certs cover *.cfargotunnel.com, so a cfargotunnel
        # host must use a parent-domain cookie or the browser drops it.
        parent = _cert_domain_host(request)
        if parent:
            cookie_kwargs["domain"] = parent
    resp.set_cookie(auth_mod.SESSION_COOKIE, auth_mod.make_token(), **cookie_kwargs)
    return resp


def _cookie_secure(request: Request) -> bool:
    override = os.environ.get("PANEL_COOKIE_SECURE")
    if override is not None:
        return override != "0"
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
    return request.url.scheme == "https" or proto == "https"


def _cert_domain_host(request: Request) -> str | None:
    """
    The registrable domain of the Host header, when it is a Cloudflare quick
    tunnel host. Cloudflare's edge certificate for `*.cfargotunnel.com` covers
    the *parent* domain, so a host-only cookie on a random
    `abcd.trycloudflare.com` can be dropped by the browser. Scoping to
    `.trycloudflare.com` avoids that.
    """
    host = (request.headers.get("host") or "").split(":")[0].lower()
    if host.endswith(".cfargotunnel.com"):
        return ".cfargotunnel.com"
    if host.endswith(".trycloudflare.com"):
        return ".trycloudflare.com"
    return None


@app.get("/logout")
def logout() -> RedirectResponse:
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie(auth_mod.SESSION_COOKIE, path="/")
    return resp


@app.get("/login")
def login_page() -> FileResponse:
    page = UI_DIR / "login.html"
    if page.exists():
        return FileResponse(page)
    raise HTTPException(404, "ui/login.html not found")


# --------------------------------------------------------------------------
# routes
# --------------------------------------------------------------------------
@app.get("/health")
def health() -> dict:
    try:
        cfg_path = config_io.default_config_path()
        cfg_exists = cfg_path.exists()
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc)}

    st = process.status()
    return {
        "ok": cfg_exists,
        "config_path": str(cfg_path),
        "config_exists": cfg_exists,
        "app_running": st.running,
        "app_pids": st.pids,
        "app_exe": str(st.exe_path) if st.exe_path else None,
    }


@app.get("/")
def index() -> FileResponse:
    """The control panel (single file, no build step)."""
    page = UI_DIR / "index.html"
    if not page.exists():
        raise HTTPException(404, "ui/index.html not found")
    return FileResponse(page)


@app.get("/schema")
def get_schema(group: str | None = None) -> dict:
    """The full field contract: ref, help text, type, defaults, allowed values."""
    items = schema_mod.llm_schema()
    if group:
        items = [i for i in items if i["group"] == group]
    return {
        "count": len(items),
        "groups": sorted({i["group"] for i in schema_mod.llm_schema()}),
        "sections": sorted({i["section"] for i in schema_mod.llm_schema()}),
        "fields": items,
    }


@app.get("/settings/defaults")
def settings_defaults(include_advanced: bool = False) -> dict:
    """
    Every non-advanced field with its default, plus which ones are actually
    missing from the ini right now. The UI uses this for "fill with defaults"
    while leaving every box editable.
    """
    try:
        present = config_io.read_typed()
    except FileNotFoundError:
        present = {}
    return {
        "defaults": schema_mod.defaults(include_advanced=include_advanced),
        "missing": config_io.fill_missing_refs(present),
    }


@app.get("/settings")
def get_settings() -> dict:
    try:
        return {"values": config_io.read_typed()}
    except FileNotFoundError:
        raise HTTPException(404, "config.ini not found")


@app.get("/glossary")
def get_glossary(term: str | None = None) -> dict:
    """
    Plain-English definitions that populate the hover bubbles in the UI.
    Single lookup: /glossary?term=usable+thread. Whole set: /glossary.
    """
    if term:
        e = glossary.lookup(term)
        if not e:
            raise HTTPException(404, f"no glossary entry for '{term}'")
        return e
    return {"count": len(glossary.TERMS), "terms": glossary.all_terms(),
            "index": glossary.INDEX}


# --------------------------------------------------------------------------
# natural language layer
# --------------------------------------------------------------------------
@app.post("/nl/plan")
def nl_plan(req: NlRequest) -> dict:
    """Turn a sentence into a settings diff. Read-only unless apply=true."""
    current = config_io.read_typed()
    prop = nl.interpret(req.text, current, prefer=req.prefer)

    # show the human exactly what would change, before anything is written
    diff = []
    try:
        cfg = config_io.load()
        diff = [
            {"section": c.section, "key": c.key, "old": c.old, "new": c.new}
            for c in config_io.plan(cfg, prop.updates)
        ]
    except config_io.ConfigError as exc:
        prop.notes.append(f"plan error: {exc}")

    refs = list(prop.updates.keys())
    out = {
        **prop.to_dict(),
        "changes": diff,
        "count": len(diff),
        "needs_restart": process.refs_requiring_restart(refs),
    }

    if req.apply and prop.updates and not prop.unknown:
        st = process.status()
        res = config_io.apply(prop.updates)
        out["applied"] = res
        out["app_was_running"] = st.running
        if out["needs_restart"] and st.running and req.restart_if_needed:
            process.restart()
            out["restarted"] = True
    return out


@app.get("/nl/explain")
def nl_explain(ref: str) -> dict:
    """What does this setting actually do?"""
    try:
        return nl.explain(ref)
    except KeyError:
        raise HTTPException(404, f"unknown field {ref!r}")


@app.get("/nl/groups")
def nl_groups() -> dict:
    return {"groups": nl.list_groups()}


@app.get("/nl/engine")
def nl_engine() -> dict:
    cfg = nl._llm_config()
    return {
        "llm_configured": cfg is not None,
        "model": cfg["model"] if cfg else None,
        "base": cfg["base"] if cfg else None,
        "fallback": "deterministic rules (always available)",
    }


@app.post("/settings/plan")
def plan_settings(req: Updates) -> dict:
    try:
        cfg = config_io.load()
        changes = config_io.plan(cfg, req.updates)
    except config_io.ConfigError as exc:
        raise HTTPException(400, str(exc))
    refs = [f"{c.section}::{c.key}" for c in changes]
    return {
        "changes": [{"section": c.section, "key": c.key, "old": c.old, "new": c.new}
                    for c in changes],
        "count": len(changes),
        "needs_restart": process.refs_requiring_restart(refs),
    }


@app.post("/settings/apply")
def apply_settings(req: ApplyRequest) -> dict:
    if not req.apply:
        return plan_settings(req)

    st = process.status()
    try:
        result = config_io.apply(req.updates)
    except config_io.ConfigError as exc:
        raise HTTPException(400, str(exc))

    refs = list(req.updates.keys())
    needs_restart = process.refs_requiring_restart(refs)
    restarted = False
    if needs_restart and st.running and req.restart_if_needed:
        process.restart()
        restarted = True

    return {
        **result,
        "app_was_running": st.running,
        "needs_restart": needs_restart,
        "restarted": restarted,
        "pending_restart": bool(needs_restart and st.running and not restarted),
    }


@app.post("/app/start")
def app_start() -> dict:
    if process.status().running:
        return {"started": False, "reason": "already running"}
    pid = process.launch()
    return {"started": True, "pid": pid}


@app.post("/app/stop")
def app_stop() -> dict:
    return {"stopped": process.stop()}


@app.post("/app/restart")
def app_restart() -> dict:
    pid = process.restart()
    return {"restarted": True, "pid": pid}


# --------------------------------------------------------------------------
# project (.prj) layer — proxies, keywords, per-project scheduling
# --------------------------------------------------------------------------
@app.get("/projects")
def list_projects() -> dict:
    try:
        items = project_io.list_projects()
    except RuntimeError as exc:
        raise HTTPException(500, str(exc))
    return {"count": len(items), "projects": items}


@app.get("/project")
def get_project(name: str) -> dict:
    try:
        return project_io.read_summary(name)
    except ConfigError as exc:
        raise HTTPException(404, str(exc))


@app.post("/project/plan")
def plan_project(req: ProjectRequest) -> dict:
    """Read-only diff of what a project change would do."""
    try:
        cfg = project_io.load(req.name)
        changes = project_io.plan_settings(cfg, req.updates)
        if req.keywords is not None:
            changes += project_io.set_keywords(cfg, req.keywords)
    except ConfigError as exc:
        raise HTTPException(400, str(exc))
    return {
        "changes": [{"section": c.section, "key": c.key, "old": c.old, "new": c.new,
                     "added": c.added} for c in changes],
        "count": len(changes),
    }


@app.post("/project/apply")
def apply_project(req: ProjectRequest) -> dict:
    try:
        p = project_io._path(req.name)
        result = project_io.apply_settings(req.updates, p) if req.updates else {
            "changed": [], "verified": True, "bounced": [], "backup_path": None,
            "added": [], "updated": []}
        if req.keywords is not None:
            kres = _apply_project_keywords(p, req.keywords)
            result["keywords"] = kres
    except ConfigError as exc:
        raise HTTPException(400, str(exc))

    out = {**result, "project": p.stem}
    if req.restart_if_needed and process.status().running:
        process.restart()
        out["restarted"] = True
    return out


def _apply_project_keywords(path, keywords: list[str]) -> dict:
    """
    Rewrite the [keywords] block.

    Note the shape: entries are `N=flag:name`, so the ini *key* is the index, not
    the keyword text. That means we must match on the value, never on cfg.find().
    Rebuilding the block wholesale keeps indices dense (0..n-1) and avoids the
    blank-line drift you get from deleting individual lines.
    """
    import os
    import shutil

    cfg = project_io.load(str(path))
    want = [k.strip() for k in keywords if k.strip()]

    # current state, in file order: list of (name, enabled)
    current: list[tuple[str, bool]] = []
    for e in cfg.entries:
        if e.section == "keywords" and ":" in e.value:
            flag, _, name = e.value.partition(":")
            current.append((name, flag.strip() == "1"))

    cur_names = [n for n, _ in current]
    if cur_names == want and all(en for _, en in current):
        return {"changed": [], "verified": True, "bounced": []}

    # preserve existing order for kept names, then append the new ones
    ordered = [n for n in cur_names if n in want] + [n for n in want if n not in cur_names]

    sec = cfg.find_section("keywords")
    cr = "\r" if any(l.endswith("\r") for l in cfg.lines) else ""
    if sec is None:
        cfg.lines += ["", f"[keywords]{cr}"] + [f"{i}=1:{n}{cr}" for i, n in enumerate(ordered)]
    else:
        end = len(cfg.lines)
        for i in range(sec + 1, len(cfg.lines)):
            s = cfg.lines[i].rstrip("\r").strip()
            if s.startswith("[") and s.endswith("]"):
                end = i
                break
        body = [f"{i}=1:{n}{cr}" for i, n in enumerate(ordered)]
        blank = cr if cr else ""
        cfg.lines[sec + 1:end] = body + ([] if end == len(cfg.lines) else [blank])

    shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(config_io._render(cfg))
    os.replace(tmp, path)
    return {"changed": [f"keywords -> {ordered}"], "verified": True, "bounced": []}


# --------------------------------------------------------------------------
# per-person import (URL + message -> CSV that GSA sends row by row)
# --------------------------------------------------------------------------
@app.post("/import/plan")
def import_plan(req: ImportRequest) -> dict:
    if req.text:
        plan = import_csv.parse_delimited(req.text)
    else:
        raise HTTPException(400, "paste some data (url + message per line, or CSV)")
    out = plan.to_dict()
    out["suggested_project_updates"] = (
        import_csv.recommended_project_updates(
            plan, import_csv.imports_dir() / "PLACEHOLDER.csv", delete_after=req.delete_after)
        if plan.message_header else {})
    out["unproven_keys"] = import_csv.UNPROVEN_KEYS
    return out


@app.post("/import/apply")
def import_apply(req: ImportRequest) -> dict:
    try:
        plan = import_csv.parse_delimited(req.text) if req.text else None
        if plan is None:
            raise ConfigError("paste some data")
        name = req.save_name or req.filename or "per-person import"
        csv_path = import_csv.write_csv(plan, name)

        out = {"csv_path": str(csv_path), "row_count": plan.row_count,
               "message_macro": plan.message_macro, "subject_macro": plan.subject_macro,
               "headers": plan.headers}

        if req.apply_project:
            if not req.project:
                raise ConfigError("project required when apply_project=true")
            upd = import_csv.recommended_project_updates(
                plan, csv_path, delete_after=req.delete_after)
            p = project_io._path(req.project)
            out["project_apply"] = project_io.apply_settings(upd, p)
            out["project"] = p.stem
            out["message_instructions"] = _message_instructions(plan)
        return out
    except ConfigError as exc:
        raise HTTPException(400, str(exc))


def _message_instructions(plan) -> dict:
    """What to put in the project's submission message so per-row text is used."""
    parts = []
    if plan.subject_macro:
        parts.append(plan.subject_macro)
    parts.append(plan.message_macro)
    return {
        "subject": plan.subject_macro,
        "body": "Hi,\n\n" + (plan.message_macro or "") + "\n\nBest,\n%mail_from_name%",
        "tokens_to_use": parts,
        "note": ("GSA reads the CSV header row and exposes each cell as its macro, so "
                 "the message must contain " + (plan.message_macro or "") +
                 " where the per-person text should appear."),
    }


# --------------------------------------------------------------------------
# sizing: how many proxies / which captcha, by daily volume
# --------------------------------------------------------------------------
@app.get("/sizing/proxies")
def sizing_proxies(tier: str = "free") -> dict:
    """
    Proxy pool needed per daily send volume, for one sourcing tier.

    Assumptions are returned alongside the numbers so nothing is a black box.
    """
    try:
        rows = sizing.proxy_table(tier)
    except KeyError:
        raise HTTPException(400, f"unknown tier {tier!r}")
    return {
        "tier": tier,
        "tiers": [{"key": t.key, "label": t.label, "quality": t.quality,
                   "cost_note": t.cost_note, "recommend": t.recommend} for t in sizing.TIERS],
        "assumptions": {
            "page_requests_per_site": sizing.PAGE_REQUESTS_PER_SITE,
            "proxy_live_fraction": sizing.PROXY_LIVE_FRACTION,
            "note": "rules of thumb, tune to your niche",
        },
        "sources": sizing.proxy_source_stats(),
        "rows": rows,
    }


@app.get("/sizing/captcha")
def sizing_captcha(daily_sends: int = 1000) -> dict:
    """Estimated captcha volume + what each shipped service would cost."""
    if daily_sends < 1:
        raise HTTPException(400, "daily_sends must be >= 1")
    plan = sizing.captcha_plan(daily_sends)
    return {**plan, "stack": sizing.recommended_stack(daily_sends),
            "layer2": sizing.layer2_stack(daily_sends)}


@app.get("/sizing/providers")
def sizing_providers() -> dict:
    """
    Where to actually buy proxies, and the straight answer to 'unlimited
    residential'. Prices are quoted from the providers' own pages (2026-11-11).
    """
    return {
        "advice": sizing.unlimited_advice(),
        "providers": sizing.provider_table(),
    }


@app.get("/sizing/isp-price")
def sizing_isp_price(count: int = 40) -> dict:
    """
    What `count` good-grade residential/IP proxies cost per month, from published
    per-IP rates. Dedicated (1-IP-per-customer, unmetered) is ranked first.
    """
    if count < 1:
        raise HTTPException(400, "count must be >= 1")
    return sizing.isp_price_table(count)


@app.get("/sizing/ip-grade")
def sizing_ip_grade() -> dict:
    """
    Which grade of IP to buy, and roughly how much each grade actually reaches.
    Reach figures are labelled rules of thumb, not measurements.
    """
    return {
        "advice": sizing.ip_coverage_advice(),
        "grades": sizing.ip_grade_table(),
    }


@app.get("/sizing/fallback")
def sizing_fallback(pool_size: int = 300) -> dict:
    if pool_size < 1:
        raise HTTPException(400, "pool_size must be >= 1")
    plan = sizing.fallback_plan(pool_size)
    plan["cost_per_success"] = {
        g["key"]: sizing.cost_per_success(
            g["reach_hostile"],
            {"free_public": 0.0, "shared_dc": 0.20, "dedicated_dc": 0.60, "isp_static": 2.00}[g["key"]])
        for g in sizing.ip_grade_table()
        if g["key"] in ("free_public", "shared_dc", "dedicated_dc", "isp_static")
    }
    return plan


@app.get("/sizing/imported-list")
def sizing_imported_list() -> dict:
    """
    You supply the lead list; the app only parses + sends. Removes the hardest
    proxy gate (search engines) and reshapes the whole setup.
    """
    return sizing.imported_list_plan()


@app.get("/sizing/tinyfish")
def sizing_tinyfish() -> dict:
    """
    Would TinyFish be a better parsing step? Honest limits + the real math.
    Prices are TinyFish's own published rates (read 2026-11-12).
    """
    return sizing.tinyfish_verdict()


@app.get("/sizing/farm")
def sizing_farm(accounts: int = 1) -> dict:
    """
    What farmed TinyFish accounts actually multiply. Daily allowance is per
    account; per-minute limit is per key. Honest caveats included.
    """
    return sizing.farm_scaling(accounts)


@app.get("/sizing/farm-safety")
def sizing_farm_safety(accounts: int = 3) -> dict:
    """
    How to farm without getting flagged. Separates what TinyFish enforces
    (nothing IP-shaped: plain API-key auth) from plain good hygiene.
    """
    return sizing.farm_without_blocks(accounts)


@app.get("/sizing/capacity")
def sizing_capacity(daily_sends: int = 10000, found_pct: int = 60) -> dict:
    """
    Capacity plan for a daily submission target, with the send/parse split made
    explicit and the allowance-vs-speed constraints kept separate.
    """
    return sizing.capacity_10k(daily_sends, found_pct)


@app.get("/sizing/proxies-for")
def sizing_proxies_for(daily_sends: int = 5000) -> dict:
    """
    What grade and how many proxies to actually buy for a daily send volume.
    """
    return sizing.proxy_recommendation(daily_sends)


@app.get("/sizing/rotating-residential")
def sizing_rotating_residential(daily_sends: int = 5000,
                                kb_per_page: int = 80) -> dict:
    """
    Would per-GB rotating residential work? Fine for parsing, risky for sending,
    and more expensive than dedicated at this workload.
    """
    return sizing.rotating_residential_verdict(daily_sends, kb_per_page)


@app.get("/sizing/ipnux")
def sizing_ipnux(ips: int = 33) -> dict:
    """
    IPNux marketing says $2/IP; the checkout quoted $9/IP. Explains the quality
    selector, and what to actually click before paying.
    """
    return sizing.ipnux_checkout_reality(ips)


@app.get("/sizing/cheap-proxies")
def sizing_cheap_proxies(daily_sends: int = 5000) -> dict:
    """
    Are cheap proxy types useless, and what deliverability is really lost?
    Loss is concentrated on hardened sites; the loud/silent asymmetry dominates.
    """
    return sizing.cheap_proxy_tradeoff(daily_sends)


@app.get("/sizing/split-test")
def sizing_split_test(daily_sends: int = 5000, detect_pp: float = 10.0) -> dict:
    """
    A balanced block design for A/B-ing proxy grade without confounding captcha,
    list composition, content or warmup. Includes sample size, taxonomy, controls.
    """
    return sizing.split_test_design(daily_sends, detect_pp)


@app.get("/sizing/procurement")
def sizing_procurement(daily_sends: int = 5000, detect_pp: float = 10.0) -> dict:
    """
    What to buy for the split test (which vendors, how many IPs) and how to hand
    the proxies over. Deliberately small: the test needs ~1.5k attempts, not 5k/day.
    """
    return sizing.procurement_plan(daily_sends, detect_pp)


@app.get("/sizing/stages")
def sizing_stages(daily_sends: int = 5000) -> dict:
    """
    Do captcha services make our own proxies redundant? Do parse proxies need to be
    good? (No, and no — the service's proxy and yours act on different hops.)
    """
    return sizing.stage_requirements(daily_sends)


@app.get("/sizing/spend")
def sizing_spend(daily_sends: int = 5000, found_pct: int = 60) -> dict:
    """
    The whole money picture: what each bucket buys, why it sits where it does, and
    what breaks without it. Line-item maths is auditable; rates are labelled.
    """
    return sizing.spend_breakdown(daily_sends, found_pct)


@app.get("/sizing/minimum-test")
def sizing_minimum_test(daily_sends: int = 5000) -> dict:
    """
    Cheapest test that still proves something. Needs attempt COUNT, not a big pool;
    threads only buy speed. Includes the hard Webshare minimum-order floor.
    """
    return sizing.minimum_budget_test(daily_sends)


@app.get("/sizing/steps")
def sizing_steps(daily_sends: int = 1000, tier: str = "residential") -> dict:
    """
    The buy-and-install walkthrough: order to click in GSA, and the exact
    expected format of a proxy line. Grounded in GSA's own documented flow.
    """
    plan = sizing.proxy_plan(daily_sends, sizing.recommended_threads(daily_sends), tier)
    return {
        "plan": plan,
        "proxy_line_format": "IP:PORT:USERNAME:PASSWORD",
        "alt_format": "USERNAME:PASSWORD@IP:PORT",
        "steps": [
            {"n": 1, "do": "Buy a proxy plan",
             "detail": "See /sizing/providers. For 'unlimited residential' start with a "
                       "port-based unmetered plan, or static ISP IPs if you want zero speed cap."},
            {"n": 2, "do": "Copy the provider's proxy list",
             "detail": "Log into the provider dashboard and export/copy the proxy endpoints. "
                       "You get one line per proxy in the format above."},
            {"n": 3, "do": "Paste it into GSA and TEST it",
             "detail": "Proxy management -> Add/Edit Proxies -> import, then use Test Proxies. "
                       "Never skip testing: a dead proxy just idles a thread."},
            {"n": 4, "do": "Turn off public-proxy searching",
             "detail": "Options -> uncheck 'search for new proxies', otherwise GSA keeps "
                       "mixing flaky public entries into your clean paid pool."},
            {"n": 5, "do": "Enable proxies per stage",
             "detail": "Right-click project -> Proxy Settings -> tick the stages (sending at "
                       "minimum). These are the three switches on the Project & proxies tab."},
            {"n": 6, "do": "Only then raise threads",
             "detail": "Set max threads to roughly your live proxy count. Past that you are "
                       "just queueing work onto idle threads."},
        ],
        "warnings": [
            "A proxy that cannot reach Google is still fine for form submission.",
            "Do not select all 565 public sources at once while also using paid proxies.",
            "Rotating gateways can hand you a banned IP; sticky ISP IPs are safer for sending.",
        ],
    }



@app.post("/sizing/enable-sources")
def enable_sources(limit: int | None = None) -> dict:
    """Turn on more built-in free proxy sources so GSA harvests a bigger pool."""
    return sizing.enable_proxy_sources(limit=limit)
