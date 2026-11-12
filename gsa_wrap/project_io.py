"""
Reader / writer for GSA Website Contact project files (`*.prj`).

Why this exists
---------------
`config.ini` is only half the story. The things that actually decide *what gets
done* live in the project file (.prj), not the global config:

    [misc]                      <- scraping + proxy + filter behaviour
        proxies for se/parse/sending
        se/parse/sending proxy type
        skip root domains, collect social, max pages, ...
    [keywords]                  <- 0=1:robotics outbound
    [se]                        <- 2500 search engines, flag=1 means enabled
    [ident url]/[ident anchor]/[ident]  <- field-matching language lists
    [scheduler]                 <- per-project timers + import/export

The project file is written by GSA in plain ANSI text with CRLF, exactly like
config.ini, so we reuse the same byte-faithful parse/render approach. The big
indexed sections ([se], [ident], [ident url]) are the bulk of the file and are
left untouched unless the caller asks to change them.

Evidence
--------
All keys below were read from the live `robotics outbound.prj` and cross-checked
against strings in the unpacked binary (WebContact_unpacked.exe), which contains
the literal tokens "se proxy type", "parse proxy type", "sending proxy type",
"ImportSend", "import file", "import min", "import del on", "collect social",
"keyword add". Nothing here is invented.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import config_io
from .config_io import ConfigError, Entry, ParsedConfig, _render

PROJECTS_SUBPATH = Path("GSA_WebsiteContact") / "projects"

# ---------------------------------------------------------------------------
# Proxy types. The binary ships the literal labels "None" / "HTTP" / "Socks4"
# / "Socks5" and the dialog reports the setting as `... proxy type`. The live
# file stores 3 for "no proxy" on all three roles. So:
#   * 3 is PROVEN (it is what a freshly licensed install writes as "off").
#   * the other three are INFERRED from the four shipped labels and from the
#     binary's `Socks4)` / `Socks5)` strings next to "Please choose the proxy
#     type." They must be re-verified by toggling the Proxy dialog by hand once.
# ---------------------------------------------------------------------------
PROXY_TYPES: dict[int, str] = {0: "none", 1: "http", 2: "socks4", 3: "socks5"}
PROXY_TYPE_IDS: dict[str, int] = {v: k for k, v in PROXY_TYPES.items()}
PROXY_TYPE_PROVEN = {3}

# Boolean/int project settings we are willing to touch. Everything else in
# [misc] is preserved as-is.
PROXY_ROLE_KEYS = ("proxies for se", "proxies for parse", "proxies for sending")
PROXY_TYPE_KEYS = ("se proxy type", "parse proxy type", "sending proxy type")
BOOL_KEYS = (
    "only root domains", "remember keyword history", "repeat search",
    "skip root domains", "collect social", "skip sublink parsing",
    "accept duplicate domains", "filter language on", "filter country on",
    "filter url on", "filter content on", "retry failed", "parse css",
    "skip external contact forms", "filter comment forms", "keyword mod on",
)
INT_KEYS = ("start page", "max pages", "delay before submit",
            "delay before submit rnd", "unknown form field fill type")
SCHED_BOOL_KEYS = ("scraper on", "sender on", "send limit on", "import on",
                   "import del on", "export failed on", "export checked on",
                   "export sent on", "export filtered on", "start other prj on")
SCHED_STR_KEYS = ("import file", "export failed file", "export checked file",
                  "export sent file", "export filtered file", "start other prj")
SCHED_INT_KEYS = ("send limit", "import min", "send limit type", "export format",
                  "start other prj flags")

KNOWN_KEYS: dict[str, set[str]] = {
    "misc": set(PROXY_ROLE_KEYS) | set(PROXY_TYPE_KEYS) | set(BOOL_KEYS) | set(INT_KEYS),
    "scheduler": set(SCHED_BOOL_KEYS) | set(SCHED_STR_KEYS) | set(SCHED_INT_KEYS),
}


def projects_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA is not set; pass an explicit project path")
    return Path(appdata) / PROJECTS_SUBPATH


def list_projects() -> list[dict]:
    d = projects_dir()
    if not d.exists():
        return []
    out = []
    for p in sorted(d.glob("*.prj")):
        st = p.stat()
        out.append({
            "name": p.stem,
            "path": str(p),
            "size": st.st_size,
            "modified": st.st_mtime,
        })
    return out


def _path(arg: Path | str) -> Path:
    """Accept an absolute path, a bare project name, or a relative path."""
    p = Path(arg)
    if p.is_absolute() and p.exists():
        return p
    if p.exists() and p.suffix.lower() == ".prj":
        return p.resolve()
    cand = projects_dir() / f"{Path(arg).stem}.prj"
    if cand.exists():
        return cand
    raise ConfigError(f"project not found: {arg!r} (looked for {cand})")


def load(path: Path | str) -> ParsedConfig:
    return config_io.parse_text(_path(path).read_bytes())


def _indexed(cfg: ParsedConfig, section: str) -> dict[int, tuple[int, str]]:
    """{index: (line_no, name)} for a `N=flag:name` style section."""
    out: dict[int, tuple[int, str]] = {}
    sec = cfg.find_section(section)
    for e in cfg.entries:
        if e.section != section:
            continue
        try:
            idx = int(e.key)
        except ValueError:
            continue
        name = e.value.split(":", 1)[1] if ":" in e.value else e.value
        out[idx] = (e.line_no, name)
    return out


def read_summary(path: Path | str) -> dict:
    """Everything our UI needs to show about a project, without the bulk."""
    p = _path(path)
    cfg = config_io.parse_text(p.read_bytes())
    misc = {e.key: e.value for e in cfg.entries if e.section == "misc"}
    sched = {e.key: e.value for e in cfg.entries if e.section == "scheduler"}

    kws = []
    for e in cfg.entries:
        if e.section == "keywords" and ":" in e.value:
            flag, _, name = e.value.partition(":")
            kws.append({"name": name, "enabled": flag.strip() == "1"})

    se_total = len(_indexed(cfg, "se"))
    se_on = [n for (_, n) in _indexed_vals(cfg, "se") if n]

    return {
        "name": p.stem,
        "path": str(p),
        "proxies": {k: misc.get(k, "0") == "1" for k in PROXY_ROLE_KEYS},
        "proxy_types": {k: int(misc.get(k, "3") or 3) for k in PROXY_TYPE_KEYS},
        "proxy_type_names": {k: PROXY_TYPES.get(int(misc.get(k, "3") or 3), "?")
                             for k in PROXY_TYPE_KEYS},
        "proxy_type_options": PROXY_TYPES,
        "keywords": kws,
        "search_engines_total": se_total,
        "search_engines_enabled": len(se_on),
        "search_engines_enabled_sample": se_on[:40],
        "misc": misc,
        "scheduler": sched,
    }


def _indexed_vals(cfg: ParsedConfig, section: str) -> list[tuple[int, str]]:
    out = []
    for e in cfg.entries:
        if e.section != section:
            continue
        try:
            int(e.key)
        except ValueError:
            continue
        if e.value.startswith("1:"):
            out.append((int(e.key), e.value.split(":", 1)[1]))
    return out


# ---------------------------------------------------------------------------
# write
# ---------------------------------------------------------------------------
@dataclass
class ProjectChange:
    section: str
    key: str
    old: str | None
    new: str
    added: bool = False

    def __str__(self) -> str:
        return f"[{self.section}] {self.key}: {self.old!r} -> {self.new!r}"


def apply_settings(updates: dict[str, object], path: Path | str, *, backup: bool = True,
                   verify: bool = True) -> dict:
    """
    Apply a flat {section::key: value} map to a .prj.

    Keys are coerced by simple, explicit rules (no schema object here because the
    .prj is a different namespace from config.ini):
        * PROXY_ROLE_KEYS / BOOL_KEYS  -> "1"/"0"
        * PROXY_TYPE_KEYS              -> int, must be a known proxy type id
        * INT_KEYS / SCHED_INT_KEYS    -> int
        * str keys                     -> verbatim
    Unknown sections/keys are appended, never guessed at.
    """
    p = _path(path)
    cfg = config_io.parse_text(p.read_bytes())
    changes = plan_settings(cfg, updates)
    if not changes:
        return {"changed": [], "verified": True, "bounced": [], "backup_path": None,
                "added": [], "updated": []}

    backup_path = None
    if backup:
        backup_path = p.with_suffix(p.suffix + ".bak")
        shutil.copy2(p, backup_path)

    for ch in changes:
        e = cfg.find(ch.section, ch.key)
        if e is not None:
            line = cfg.lines[e.line_no]
            prefix = line.split("=", 1)[0]
            tail = "\r" if line.endswith("\r") else ""
            cfg.lines[e.line_no] = f"{prefix}={ch.new}{tail}"
            e.value = ch.new
        else:
            config_io._append_key(cfg, ch.section, ch.key, ch.new)

    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_bytes(_render(cfg))
    os.replace(tmp, p)

    bounced: list[str] = []
    if verify:
        after = config_io.parse_text(p.read_bytes())
        for ch in changes:
            e = after.find(ch.section, ch.key)
            if e is None or e.value != ch.new:
                bounced.append(f"[{ch.section}] {ch.key}")

    return {
        "changed": [str(c) for c in changes],
        "added": [f"[{c.section}] {c.key}" for c in changes if c.added],
        "updated": [f"[{c.section}] {c.key}" for c in changes if not c.added],
        "verified": not bounced,
        "bounced": bounced,
        "backup_path": str(backup_path) if backup_path else None,
    }


def coerce_project_value(section: str, key: str, value: object) -> str:
    if key in PROXY_TYPE_KEYS:
        iv = int(value)
        if iv not in PROXY_TYPES:
            raise ConfigError(f"{key}: unknown proxy type id {iv} (use 0..3)")
        return str(iv)
    if key in PROXY_ROLE_KEYS or key in BOOL_KEYS or key in SCHED_BOOL_KEYS:
        if isinstance(value, bool):
            return "1" if value else "0"
        return "1" if str(value).strip().lower() in {"1", "true", "yes", "on"} else "0"
    if key in INT_KEYS or key in SCHED_INT_KEYS:
        return str(int(value))
    return str(value)


def plan_settings(cfg: ParsedConfig, updates: dict[str, object]) -> list[ProjectChange]:
    changes: list[ProjectChange] = []
    for ref, value in updates.items():
        if "::" not in ref:
            raise ConfigError(f"bad ref {ref!r}, expected 'section::key'")
        section, key = ref.split("::", 1)
        new = coerce_project_value(section, key, value)
        existing = cfg.find(section, key)
        if existing is None:
            changes.append(ProjectChange(section=section, key=key, old=None, new=new, added=True))
        elif existing.value != new:
            changes.append(ProjectChange(section=section, key=key, old=existing.value, new=new))
    return changes


def set_keywords(cfg: ParsedConfig, keywords: list[str], *, enable: bool = True) -> list[ProjectChange]:
    """
    Replace the [keywords] block with the given list, all enabled (flag 1).
    Existing identical entries are kept with their current flag to stay
    idempotent.
    """
    existing = {e.value.split(":", 1)[1]: e for e in cfg.entries
                if e.section == "keywords" and ":" in e.value}
    changes: list[ProjectChange] = []
    want = [k.strip() for k in keywords if k.strip()]

    # remove keys that are no longer wanted
    for name, e in existing.items():
        if name not in want:
            changes.append(ProjectChange("keywords", name, e.value, "", added=False))

    # add/reflag
    for name in want:
        if name in existing:
            old = existing[name].value
            if old != f"1:{name}":
                changes.append(ProjectChange("keywords", name, old, f"1:{name}"))
        else:
            changes.append(ProjectChange("keywords", name, None, f"1:{name}", added=True))
    return changes
