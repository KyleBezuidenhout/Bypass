"""
Typed schema for GSA Website Contact settings.

This is the load-bearing artifact: it is simultaneously
  1. what the LLM fills in from a natural-language prompt,
  2. what our UI renders, and
  3. where the human-readable `help` text lives.

Every field here is grounded in evidence from the shipped binary
(`WebContact_unpacked.exe`, config key table at file offset ~0x324b00)
and the live `config.ini` in %APPDATA%. Do not add a field without evidence.

EVIDENCE NOTE
-------------
The [misc] key table in the binary lists exactly:
    hide disclaimer, timeout, max threads, max threads se, autoscroll,
    blacklist on, global send dupecheck, message preview,
    stop project on no proxy, use real captcha ip,
    captcha services in random order, scaling mode
plus the [columns prj], [columns url], [notify] and [scheduler] sections.
Widget *labels* (the human-facing wording) are a separate namespace the binary
does not embed verbatim; those are marked `label_confidence` so we never
confuse a proven key with a plausible label.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Iterable

from pydantic import BaseModel, Field


class FieldType(str, Enum):
    INT = "int"
    BOOL = "bool"          # stored as 0/1 in the ini
    STR = "str"


class Confidence(str, Enum):
    """How sure are we this field is real and correctly described?"""
    PROVEN = "proven"        # key + section literally present in the binary
    INFERRED = "inferred"    # key present, semantics inferred from name/context


class SettingField(BaseModel):
    """One leaf setting."""

    key: str                                  # exact ini key, spaces included
    section: str                              # exact ini section
    type: FieldType
    default: Any
    help: str
    allowed: list[Any] | None = None
    min_value: int | None = None
    max_value: int | None = None
    confidence: Confidence = Confidence.PROVEN
    # Some settings only take effect after the app restarts. Proven for the
    # registration flow ("Please restart the program now."); assumed for settings
    # read only at startup.
    requires_restart: bool = False
    # Ui hint for the future front-end.
    ui_group: str = "general"
    # Short unit suffix shown next to the input ("sec", "min", "px", "").
    unit: str = ""
    # Advanced/formatting fields the user rarely needs to touch. The UI still
    # renders them, but "fill with defaults" leaves them alone so we never
    # surprise someone by stomping their window size or grid columns.
    advanced: bool = False
    # True when a value is required for the app to work at all (e.g. threads).
    essential: bool = False

    @property
    def editable(self) -> bool:
        """Everything in the schema is editable; kept as an explicit flag so the
        contract does not change if we later add read-only mirrors."""
        return True

    def coerce(self, value: Any) -> str:
        """Coerce a python value to the exact string the ini expects."""
        if self.type is FieldType.BOOL:
            if isinstance(value, bool):
                out = "1" if value else "0"
            else:
                out = "1" if str(value).strip().lower() in {"1", "true", "yes", "on"} else "0"
        elif self.type is FieldType.INT:
            iv = int(value)
            if self.min_value is not None and iv < self.min_value:
                raise ValueError(f"{self.key}: {iv} < min {self.min_value}")
            if self.max_value is not None and iv > self.max_value:
                raise ValueError(f"{self.key}: {iv} > max {self.max_value}")
            out = str(iv)
        else:
            out = str(value)

        if self.allowed is not None and out not in {str(a) for a in self.allowed}:
            raise ValueError(f"{self.key}: {out!r} not in {self.allowed}")
        return out

    def parse(self, raw: str) -> Any:
        """Parse a raw ini string back to a python value."""
        if self.type is FieldType.BOOL:
            return raw.strip() in {"1", "true", "yes", "on"}
        if self.type is FieldType.INT:
            try:
                return int(raw.strip())
            except ValueError:
                return self.default
        return raw


# --------------------------------------------------------------------------
# The schema. Grouped by section, mirroring the binary's key table exactly.
# --------------------------------------------------------------------------

S = SettingField

SCHEMA: dict[str, SettingField] = {f"{f.section}::{f.key}": f for f in [
    # ---- [misc] : proven keys ------------------------------------------
    S(key="hide disclaimer", section="misc", type=FieldType.BOOL, default=False,
      help="Skip the 'Disclaimer' notice shown every launch. Turn on once you've read it.",
      ui_group="interface"),
    S(key="timeout", section="misc", type=FieldType.INT, default=120, min_value=5, max_value=3600,
      help="Seconds to wait for a single site before giving up and marking it failed. "
           "Low = faster but more false failures; high = slower but survives slow hosts.",
      ui_group="performance", unit="sec", essential=True),
    S(key="max threads", section="misc", type=FieldType.INT, default=10, min_value=1, max_value=200,
      help="How many websites are visited at the same time. Proxies let you raise this; "
           "no proxies means keep it modest or you get IP-banned.",
      ui_group="performance", essential=True),
    S(key="max threads se", section="misc", type=FieldType.INT, default=10, min_value=1, max_value=200,
      help="Parallelism specifically for search-engine queries (used to find sites). "
           "Kept separate from site threads because SEs rate-limit harder.",
      ui_group="performance", essential=True),
    S(key="autoscroll", section="misc", type=FieldType.BOOL, default=True,
      help="Auto-scroll the results grid as work progresses.",
      ui_group="interface"),
    S(key="blacklist on", section="misc", type=FieldType.BOOL, default=False,
      help="Enable the domain blacklist so matching sites are skipped entirely.",
      ui_group="filtering"),    S(key="global send dupecheck", section="misc", type=FieldType.BOOL, default=False,
      help="Before submitting, check globally whether this site was already contacted.",
      ui_group="filtering"),
    S(key="message preview", section="misc", type=FieldType.BOOL, default=True,
      help="Show a preview of the outgoing message before it is sent.",
      ui_group="interface"),
    S(key="stop project on no proxy", section="misc", type=FieldType.BOOL, default=True,
      help="Halt the project if all proxies die, rather than continuing from your own IP.",
      ui_group="proxies"),
    S(key="use real captcha ip", section="misc", type=FieldType.BOOL, default=False,
      help="Solve captchas from your real IP instead of through a proxy. "
           "More reliable solves, but exposes your address to the captcha provider.",
      ui_group="captcha"),
    S(key="captcha services in random order", section="misc", type=FieldType.BOOL, default=False,
      help="Rotate between configured captcha services instead of always using the first.",
      ui_group="captcha"),
    S(key="scaling mode", section="misc", type=FieldType.INT, default=0, allowed=[0, 1, 2],
      help="Windows DPI scaling behaviour for the interface (0=off). "
           "Label wording inferred; values are what the ini stores.",
      confidence=Confidence.INFERRED, ui_group="interface"),

    # ---- [scheduler] : proven keys -------------------------------------
    S(key="scrape sites", section="scheduler", type=FieldType.BOOL, default=True,
      help="Scheduled run should perform the 'scrape/find sites' stage.",
      ui_group="scheduler"),
    S(key="check sites", section="scheduler", type=FieldType.BOOL, default=True,
      help="Scheduled run should perform the 'check sites' stage.",
      ui_group="scheduler"),
    S(key="send sites", section="scheduler", type=FieldType.BOOL, default=False,
      help="Scheduled run should actually send outreach messages.",
      ui_group="scheduler"),
    S(key="max projects", section="scheduler", type=FieldType.INT, default=5, min_value=1, max_value=100,
      help="Upper bound on projects run in one scheduled batch.",
      ui_group="scheduler"),
    S(key="max runtime", section="scheduler", type=FieldType.INT, default=30, min_value=1, max_value=1440,
      help="Minutes the scheduler may run before stopping.",
      ui_group="scheduler", unit="min"),
    S(key="use runtime", section="scheduler", type=FieldType.BOOL, default=True,
      help="Enforce the max runtime limit above.",
      ui_group="scheduler"),

    # ---- [misc] extras present in live ini but outside the small key table
    S(key="f1.width", section="misc", type=FieldType.INT, default=837,
      help="Remembered main-window width in pixels.",
      confidence=Confidence.INFERRED, ui_group="interface", unit="px", advanced=True),
    S(key="f1.height", section="misc", type=FieldType.INT, default=468,
      help="Remembered main-window height in pixels.",
      confidence=Confidence.INFERRED, ui_group="interface", unit="px", advanced=True),
    S(key="stats time", section="misc", type=FieldType.INT, default=0,
      help="Reserved/statistics timer setting (0 = default).",
      confidence=Confidence.INFERRED, ui_group="misc", advanced=True),
    S(key="search engine wait time", section="misc", type=FieldType.INT, default=0,
      help="Extra seconds between search-engine queries.",
      confidence=Confidence.INFERRED, ui_group="performance", unit="sec"),
    S(key="se wait time", section="misc", type=FieldType.INT, default=0,
      help="Extra seconds between site visits when reached via a search engine.",
      confidence=Confidence.INFERRED, ui_group="performance", unit="sec"),
    S(key="always perform filter on import", section="misc", type=FieldType.INT, default=-1,
      allowed=[-1, 0, 1],
      help="Whether imported URLs are always passed through the filter (-1 = ask).",
      confidence=Confidence.INFERRED, ui_group="filtering"),
]}

# Sections whose keys are index-suffixed (width 0..9 / visible 0..9).
# Present in the live ini and matched in the binary as 'width ' / 'visible '.
for i in range(10):
    SCHEMA[f"columns prj::width {i}"] = S(
        key=f"width {i}", section="columns prj", type=FieldType.INT, default=50,
        help=f"Column {i} width in the projects grid.", confidence=Confidence.INFERRED,
        ui_group="columns")
    SCHEMA[f"columns prj::visible {i}"] = S(
        key=f"visible {i}", section="columns prj", type=FieldType.BOOL, default=True,
        help=f"Show column {i} in the projects grid.", confidence=Confidence.INFERRED,
        ui_group="columns")
for i in range(6):
    SCHEMA[f"columns url::width {i}"] = S(
        key=f"width {i}", section="columns url", type=FieldType.INT, default=80,
        help=f"Column {i} width in the URLs grid.", confidence=Confidence.INFERRED,
        ui_group="columns")
    SCHEMA[f"columns url::visible {i}"] = S(
        key=f"visible {i}", section="columns url", type=FieldType.BOOL, default=True,
        help=f"Show column {i} in the URLs grid.", confidence=Confidence.INFERRED,
        ui_group="columns")

# ---- [notify] : proven keys ------------------------------------------
for f in [
    S(key="email notification on", section="notify", type=FieldType.BOOL, default=False,
      help="Email you a status report while a project runs.", ui_group="notifications"),
    S(key="email from", section="notify", type=FieldType.STR, default="",
      help="From address for notification email.", ui_group="notifications"),
    S(key="email login", section="notify", type=FieldType.STR, default="",
      help="SMTP username.", ui_group="notifications"),
    S(key="email pw", section="notify", type=FieldType.STR, default="",
      help="SMTP password.", ui_group="notifications"),
    S(key="smtp server", section="notify", type=FieldType.STR, default="",
      help="SMTP host for notifications.", ui_group="notifications"),
    S(key="smtp port", section="notify", type=FieldType.INT, default=113, min_value=1, max_value=65535,
      help="SMTP port.", ui_group="notifications"),
    S(key="ssl", section="notify", type=FieldType.BOOL, default=False,
      help="Use SSL for the notification mail connection.", ui_group="notifications"),
    S(key="subject", section="notify", type=FieldType.STR,
      default="GSA Website Contact - Status Update",
      help="Subject line for notification email.", ui_group="notifications"),
    S(key="email to", section="notify", type=FieldType.STR, default="",
      help="Recipient of notification email.", ui_group="notifications"),
    S(key="every min", section="notify", type=FieldType.INT, default=60, min_value=1, max_value=1440,
      help="How often (minutes) to send the notification.", ui_group="notifications", unit="min"),
]:
    SCHEMA[f"{f.section}::{f.key}"] = f


def by_section() -> dict[str, list[SettingField]]:
    out: dict[str, list[SettingField]] = {}
    for f in SCHEMA.values():
        out.setdefault(f.section, []).append(f)
    return {k: sorted(v, key=lambda x: x.key) for k, v in out.items()}


def get(section: str, key: str) -> SettingField:
    return SCHEMA[f"{section}::{key}"]


def all_fields() -> Iterable[SettingField]:
    return SCHEMA.values()


class SchemaMeta(BaseModel):
    """A flat, LLM-friendly view of one field (no python types)."""

    ref: str
    key: str
    section: str
    type: str
    default: Any
    help: str
    allowed: list[Any] | None
    group: str
    confidence: str
    unit: str = ""
    advanced: bool = False
    essential: bool = False

    @classmethod
    def of(cls, f: SettingField) -> "SchemaMeta":
        return cls(ref=f"{f.section}::{f.key}", key=f.key, section=f.section,
                   type=f.type.value, default=f.default, help=f.help,
                   allowed=f.allowed, group=f.ui_group, confidence=f.confidence.value,
                   unit=f.unit, advanced=f.advanced, essential=f.essential)


def llm_schema() -> list[dict]:
    """The schema as plain dicts — this is the LLM's tool/response contract."""
    return [SchemaMeta.of(f).model_dump() for f in sorted(all_fields(), key=lambda x: (x.section, x.key))]


def defaults(*, include_advanced: bool = False) -> dict[str, Any]:
    """
    {ref: default} for every non-advanced field.

    This is what the UI uses to fill a value into every box the user has not
    touched, so nothing is ever blank/unknown and everything stays editable.
    """
    out: dict[str, Any] = {}
    for f in all_fields():
        if f.advanced and not include_advanced:
            continue
        out[f"{f.section}::{f.key}"] = f.default
    return out
