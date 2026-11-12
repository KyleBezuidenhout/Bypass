"""
Natural-language layer: turn "scrape dentists in Pretoria, 10 threads, skip
free mail" into concrete settings updates, and explain what any field does.

Two engines, in order of preference:
  1. LLM (any OpenAI-compatible endpoint: OpenAI, Ollama, OpenRouter, vLLM).
     The schema IS the contract — the model can only pick fields that exist.
  2. Deterministic rule fallback, so the service still works with no API key
     and no network. Honest about being a fallback.

Neither engine ever writes. They return a plan that a human approves, then the
existing /settings/apply does the actual (verified, atomic) write.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from .schema import SettingField, all_fields, get as get_field, llm_schema


# --------------------------------------------------------------------------
# result types
# --------------------------------------------------------------------------
@dataclass
class Proposal:
    updates: dict[str, Any] = field(default_factory=dict)
    explanation: str = ""
    notes: list[str] = field(default_factory=list)
    engine: str = "rules"
    unknown: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "updates": self.updates,
            "explanation": self.explanation,
            "notes": self.notes,
            "engine": self.engine,
            "unknown": self.unknown,
        }


# --------------------------------------------------------------------------
# prompt construction — the schema is the contract
# --------------------------------------------------------------------------
SYSTEM = (
    "You configure GSA Website Contact, a cold-outreach desktop app. "
    "You are given a JSON schema of settings. Map the user's plain-English "
    "request to setting changes.\n"
    "RULES:\n"
    "1. Only use refs that exist in the schema. Never invent a ref.\n"
    "2. Respect type (int/bool/str) and allowed/min/max. An int field takes a number.\n"
    "3. If the user implies a setting but you are unsure of the exact ref, "
    "pick the closest and say so in notes.\n"
    "4. Do not change settings the user did not mention.\n"
    "5. Reply with ONLY JSON: {\"updates\": {\"<ref>\": <value>}, "
    "\"explanation\": \"<one sentence>\", \"notes\": [\"...\"], \"unknown\": [\"...\"]}"
)


def _compact_schema() -> list[dict]:
    out = []
    for f in sorted(all_fields(), key=lambda x: (x.section, x.key)):
        row = {"ref": f"{f.section}::{f.key}", "type": f.type.value, "help": f.help}
        if f.allowed:
            row["allowed"] = f.allowed
        if f.min_value is not None or f.max_value is not None:
            row["range"] = [f.min_value, f.max_value]
        if f.default is not None and f.default != "":
            row["default"] = f.default
        out.append(row)
    # proven/structural fields first, then the noisy columns grid last
    out.sort(key=lambda r: ("columns" in r["ref"], r["ref"]))
    return out


def build_messages(user_text: str, current: dict | None = None) -> list[dict]:
    payload = {"schema": _compact_schema()}
    if current:
        payload["current_values"] = current
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": json.dumps(payload) + "\n\nREQUEST: " + user_text},
    ]


# --------------------------------------------------------------------------
# engine 1: LLM (OpenAI-compatible)
# --------------------------------------------------------------------------
def _llm_config() -> dict | None:
    key = os.environ.get("GSA_LLM_KEY") or os.environ.get("OPENAI_API_KEY")
    base = os.environ.get("GSA_LLM_BASE") or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"
    model = os.environ.get("GSA_LLM_MODEL") or "gpt-4o-mini"
    if not key and "localhost" not in base and "127.0.0.1" not in base:
        return None
    return {"key": key, "base": base.rstrip("/"), "model": model}


def _call_llm(messages: list[dict], cfg: dict) -> str:
    body = json.dumps({
        "model": cfg["model"],
        "messages": messages,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }).encode()
    req = urllib.request.Request(
        f"{cfg['base']}/chat/completions", data=body,
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {cfg['key']}"} if cfg["key"] else {})},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    return data["choices"][0]["message"]["content"]


# --------------------------------------------------------------------------
# engine 2: deterministic rules
# --------------------------------------------------------------------------
# alias -> ref. Grounded in the field help text + common phrasing.
ALIASES: dict[str, str] = {
    "thread": "misc::max threads",
    "threads": "misc::max threads",
    "concurrent": "misc::max threads",
    "parallel": "misc::max threads",
    "timeout": "misc::timeout",
    "wait": "misc::timeout",
    "search engine threads": "misc::max threads se",
    "se threads": "misc::max threads se",
    "blacklist": "misc::blacklist on",
    "dupecheck": "misc::global send dupecheck",
    "dupe check": "misc::global send dupecheck",
    "duplicates": "misc::global send dupecheck",
    "autoscroll": "misc::autoscroll",
    "preview": "misc::message preview",
    "stop on no proxy": "misc::stop project on no proxy",
    "real captcha ip": "misc::use real captcha ip",
    "captcha ip": "misc::use real captcha ip",
    "random order": "misc::captcha services in random order",
    "scaling": "misc::scaling mode",
    "scrape": "scheduler::scrape sites",
    "check sites": "scheduler::check sites",
    "send sites": "scheduler::send sites",
    "max projects": "scheduler::max projects",
    "max runtime": "scheduler::max runtime",
    "use runtime": "scheduler::use runtime",
    "email notification": "notify::email notification on",
    "notify": "notify::email notification on",
    "smtp": "notify::smtp server",
    "every min": "notify::every min",
}

NEG = re.compile(r"\b(no|not|off|disable|disabled|without|dont|don't|never|skip)\b", re.I)

# Number fields we accept a bare number for.
NUMERIC = {
    "misc::max threads", "misc::max threads se", "misc::timeout",
    "scheduler::max projects", "scheduler::max runtime", "notify::every min",
}


def _clauses(text: str) -> list[str]:
    """Split into per-setting clauses so negation binds locally, not globally."""
    parts = re.split(r"[,;]|\band\b|\bthen\b|\balso\b", text.lower())
    return [p.strip() for p in parts if p.strip()]


def _label_to_numeric_ref(label: str) -> str | None:
    label = " ".join(label.split())
    for alias, ref in ALIASES.items():
        if ref in NUMERIC and re.search(rf"\b{re.escape(alias)}\b", label):
            return ref
    return None


def _rules(text: str) -> Proposal:
    p = Proposal(engine="rules")
    used: set[str] = set()

    for clause in _clauses(text):
        # a) "<number> <label>"  e.g. "10 threads"
        m = re.search(r"\b(\d+)\s+([a-z][a-z ]{2,24})", clause)
        ref = _label_to_numeric_ref(m.group(2)) if m else None
        if ref:
            p.updates[ref] = int(m.group(1)); used.add(ref)
            continue

        # b) "<label> (to|=|:)? <number>"  e.g. "threads to 25", "timeout=300"
        m = re.search(r"([a-z][a-z ]{2,24}?)\s*(?:to|=|:)?\s*(\d+)\b", clause)
        if m:
            ref = _label_to_numeric_ref(m.group(1))
            if ref:
                p.updates[ref] = int(m.group(2)); used.add(ref)
                continue

        # c) boolean toggle, negation bound to THIS clause only
        for alias, ref in ALIASES.items():
            if ref in used or ref in NUMERIC:
                continue
            if re.search(rf"\b{re.escape(alias)}\b", clause):
                try:
                    ft = get_field(*ref.split("::")).type.value
                except KeyError:
                    continue
                if ft == "bool":
                    p.updates[ref] = not bool(NEG.search(clause))
                    used.add(ref)
                    break

    if p.updates:
        p.explanation = f"Mapped {len(p.updates)} setting(s) to your wording."
    else:
        p.explanation = "No confident match — try naming settings directly."
    return p


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------
def interpret(text: str, current: dict | None = None, *, prefer: str = "auto") -> Proposal:
    """Natural language -> proposed settings updates. Never writes."""
    if prefer in ("auto", "llm"):
        cfg = _llm_config()
        if cfg:
            try:
                raw = _call_llm(build_messages(text, current), cfg)
                data = json.loads(raw)
                return _validate(data, engine="llm")
            except Exception as exc:  # fall through to rules
                p = _rules(text)
                p.notes.append(f"LLM failed ({exc.__class__.__name__}); used rules.")
                return p
    return _rules(text)


def _validate(data: dict, engine: str) -> Proposal:
    """Drop/repair anything the model hallucinated."""
    p = Proposal(engine=engine)
    p.explanation = str(data.get("explanation", ""))[:500]
    p.notes = [str(n)[:300] for n in data.get("notes", [])][:8]
    p.unknown = [str(u)[:200] for u in data.get("unknown", [])][:8]

    for ref, val in (data.get("updates") or {}).items():
        if "::" not in ref:
            p.unknown.append(f"{ref} (bad ref)")
            continue
        section, key = ref.split("::", 1)
        try:
            f = get_field(section, key)
        except KeyError:
            p.unknown.append(f"{ref} (not in schema)")
            continue
        try:
            f.coerce(val)          # validates type/range/allowed before we keep it
            p.updates[ref] = val
        except (ValueError, TypeError) as exc:
            p.notes.append(f"{ref}: {exc}")
    return p


def explain(ref: str) -> dict:
    """Plain-English explanation of one field — what it does and when to change it."""
    section, key = ref.split("::", 1)
    f: SettingField = get_field(section, key)
    out = {
        "ref": ref, "key": f.key, "section": f.section, "type": f.type.value,
        "help": f.help, "default": f.default, "allowed": f.allowed,
        "range": [f.min_value, f.max_value] if (f.min_value is not None or f.max_value is not None) else None,
        "group": f.ui_group, "confidence": f.confidence.value,
    }
    if f.type.value == "int" and f.min_value is not None:
        out["guidance"] = (
            f"Takes a whole number between {f.min_value} and {f.max_value}. "
            f"Default is {f.default}. Lower = lighter/faster, higher = more aggressive."
        )
    elif f.type.value == "bool":
        out["guidance"] = "A simple on/off switch."
    else:
        out["guidance"] = "Free text."
    return out


def list_groups() -> dict[str, list[str]]:
    g: dict[str, list[str]] = {}
    for f in all_fields():
        g.setdefault(f.ui_group, []).append(f"{f.section}::{f.key}")
    return {k: sorted(v) for k, v in sorted(g.items())}
