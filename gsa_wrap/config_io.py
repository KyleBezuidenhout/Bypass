"""
Reader / writer / verifier for GSA Website Contact's `config.ini`.

Design rules (mirroring the project's credit-safety mindset):
  * Read the file as bytes; preserve CRLF and original key order.
  * Write is atomic: temp file + os.replace, so a crash never leaves a
    half-written config.
  * Never touch keys/sections we don't understand.
  * Every mutation is diffable before it is applied.
  * Write -> re-read -> verify, and surface anything that silently bounced.

Format facts, taken from the live file (not assumed):
  * Encoding is plain ASCII, line endings are CRLF.
  * Keys contain spaces and are written verbatim (e.g. "max threads").
  * Values are unquoted, unescaped, single-line.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .schema import SCHEMA, SettingField, get as get_field

APPDATA_SUBPATH = Path("GSA_WebsiteContact") / "config.ini"

def default_config_path() -> Path:
    """%APPDATA%\\GSA_WebsiteContact\\config.ini on Windows."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA is not set; pass an explicit config path")
    return Path(appdata) / APPDATA_SUBPATH


@dataclass
class Entry:
    section: str
    key: str
    value: str
    line_no: int


@dataclass
class ParsedConfig:
    entries: list[Entry] = field(default_factory=list)
    # raw lines, so we can rewrite preserving everything including unknowns
    lines: list[str] = field(default_factory=list)
    newline: str = "\r\n"

    def find(self, section: str, key: str) -> Entry | None:
        for e in self.entries:
            if e.section == section and e.key == key:
                return e
        return None

    def section_names(self) -> list[str]:
        seen: list[str] = []
        for e in self.entries:
            if e.section not in seen:
                seen.append(e.section)
        return seen

    def find_section(self, section: str) -> int | None:
        """Line number of the '[section]' header, or None."""
        for i, line in enumerate(self.lines):
            s = line.rstrip("\r").strip()
            if s.startswith("[") and s.endswith("]") and s[1:-1] == section:
                return i
        return None


def parse_text(raw: bytes, *, newline: str = "\n") -> ParsedConfig:
    """
    Parse config bytes into a ParsedConfig.

    Split on '\n' ONLY and keep any '\r' at end-of-line. This survives mixed
    line endings (which really happen: our own scripts and the app's own
    rewrites can each introduce a different convention), and latin-1 maps
    bytes<->chars 1:1 so we round-trip non-ASCII city names without failing.
    """
    text = raw.decode("latin-1")
    lines = text.split(newline)
    cfg = ParsedConfig(lines=lines, newline=newline)

    section = ""
    for i, line in enumerate(lines):
        s = line.rstrip("\r").strip()
        if not s or s.startswith(";"):
            continue
        if s.startswith("[") and s.endswith("]"):
            section = s[1:-1]
            continue
        if "=" in s:
            k, _, v = s.partition("=")
            cfg.entries.append(Entry(section=section, key=k, value=v, line_no=i))
    return cfg


def load(path: Path | None = None) -> ParsedConfig:
    p = Path(path) if path else default_config_path()
    return parse_text(p.read_bytes())


class ConfigError(Exception):
    pass


def fill_missing_refs(values: dict[str, dict[str, object]]) -> dict[str, object]:
    """
    Given read_typed() output, return {ref: default} for every schema field that
    has NO line in the file yet. Used by the UI's "fill with defaults" so the
    user sees a complete, editable form even on a fresh install.
    """
    out: dict[str, object] = {}
    for ref, f in SCHEMA.items():
        sec, key = ref.split("::", 1)
        if key not in values.get(sec, {}):
            out[ref] = f.default
    return out


def read_values(path: Path | None = None) -> dict[str, dict[str, str]]:
    """{section: {key: raw_value}}."""
    cfg = load(path)
    out: dict[str, dict[str, str]] = {}
    for e in cfg.entries:
        out.setdefault(e.section, {})[e.key] = e.value
    return out


def read_typed(path: Path | None = None) -> dict[str, dict[str, object]]:
    """Same as read_values but coerced through the schema where we know the key."""
    cfg = load(path)
    out: dict[str, dict[str, object]] = {}
    for e in cfg.entries:
        ref = f"{e.section}::{e.key}"
        try:
            f = get_field(e.section, e.key)
            val: object = f.parse(e.value)
        except KeyError:
            val = e.value
        out.setdefault(e.section, {})[e.key] = val
    return out


def _render(cfg: ParsedConfig) -> bytes:
    # lines already carry their own trailing "\r" where the source had CRLF,
    # so a plain join preserves whatever mix the file actually used.
    return cfg.newline.join(cfg.lines).encode("latin-1")


@dataclass
class Change:
    section: str
    key: str
    old: str | None
    new: str
    added: bool = False

    def __str__(self) -> str:
        arrow = "(new)" if self.added else f"{self.old!r}"
        return f"[{self.section}] {self.key}: {arrow} -> {self.new!r}"


def plan(cfg: ParsedConfig, updates: dict[str, object]) -> list[Change]:
    """
    Turn a {ref: value} mapping (ref = "section::key") into a list of Changes
    WITHOUT mutating anything. This is what we show a human before applying.

    A ref whose key is absent from the file is reported as an `added` change;
    append() then creates it, keeping the ini line-ordered like GSA does.
    """
    changes: list[Change] = []
    for ref, value in updates.items():
        if "::" not in ref:
            raise ConfigError(f"bad ref {ref!r}, expected 'section::key'")
        section, key = ref.split("::", 1)
        try:
            f: SettingField = get_field(section, key)
        except KeyError:
            raise ConfigError(f"unknown setting {ref!r} (not in schema)")
        new = f.coerce(value)
        existing = cfg.find(section, key)
        if existing is None:
            changes.append(Change(section=section, key=key, old=None, new=new, added=True))
        elif existing.value != new:
            changes.append(Change(section=section, key=key, old=existing.value, new=new))
    return changes


def _apply_in_memory(cfg: ParsedConfig, changes: list[Change]) -> None:
    for ch in changes:
        e = cfg.find(ch.section, ch.key)
        if e is not None:
            line = cfg.lines[e.line_no]
            prefix = line.split("=", 1)[0]
            # keep any trailing "\r" so mixed/CRLF files stay byte-faithful
            tail = "\r" if line.endswith("\r") else ""
            cfg.lines[e.line_no] = f"{prefix}={ch.new}{tail}"
            e.value = ch.new
        else:
            _append_key(cfg, ch.section, ch.key, ch.new)


def _append_key(cfg: ParsedConfig, section: str, key: str, value: str) -> None:
    """
    Insert "key=value" at the end of `section`, or create the section at EOF if
    it does not exist. Matches GSA's own ordering (new keys append to their
    section) so the file stays diff-friendly for the app.
    """
    cr = "\r" if cfg.newline == "\n" and any(l.endswith("\r") for l in cfg.lines) else ""
    # find section bounds
    sec_start = None
    for i, line in enumerate(cfg.lines):
        s = line.rstrip("\r").strip()
        if s.startswith("[") and s.endswith("]"):
            if sec_start is not None:
                break  # reached the next section
            if s[1:-1] == section:
                sec_start = i
    new_line = f"{key}={value}{cr}"
    if sec_start is None:
        cfg.lines.append("" if cfg.lines and cfg.lines[-1].strip() else "")
        cfg.lines.append(f"[{section}]{cr}")
        cfg.lines.append(new_line)
        idx = len(cfg.lines) - 1
    else:
        insert_at = len(cfg.lines)
        for i in range(sec_start + 1, len(cfg.lines)):
            s = cfg.lines[i].rstrip("\r").strip()
            if s.startswith("[") and s.endswith("]"):
                insert_at = i
                break
        # walk back over blank lines so we land inside the section body
        while insert_at - 1 > sec_start and not cfg.lines[insert_at - 1].rstrip("\r").strip():
            insert_at -= 1
        cfg.lines.insert(insert_at, new_line)
        idx = insert_at
    # shift line numbers of every entry after the insertion point
    for entry in cfg.entries:
        if entry.line_no >= idx:
            entry.line_no += 1
    cfg.entries.append(Entry(section=section, key=key, value=value, line_no=idx))


def apply(
    updates: dict[str, object],
    path: Path | None = None,
    *,
    backup: bool = True,
    verify: bool = True,
) -> dict:
    """
    Write `updates` ({ref: value}) to the ini atomically, then re-read and
    confirm. Returns {changed, verified, bounced, backup_path}.

    Idempotent: applying the same updates twice yields zero changes the 2nd time.
    """
    p = Path(path) if path else default_config_path()

    # 1. plan against a fresh read
    cfg = load(p)
    changes = plan(cfg, updates)
    if not changes:
        return {"changed": [], "verified": True, "bounced": [], "backup_path": None,
                "added": [], "updated": []}

    # 2. backup (once), then write atomically
    backup_path = None
    if backup:
        backup_path = p.with_suffix(p.suffix + ".bak")
        shutil.copy2(p, backup_path)

    _apply_in_memory(cfg, changes)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_bytes(_render(cfg))
    os.replace(tmp, p)

    # 3. verify by re-reading from disk
    bounced: list[str] = []
    if verify:
        after = load(p)
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
