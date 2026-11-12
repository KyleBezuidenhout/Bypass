"""
Build GSA-compatible import files for *per-person* outreach.

The question this answers
-------------------------
"Can I upload a personalized message per person along with their website, and
have it go fill out that site's form?"

Yes — GSA supports it natively, and the feature is old and documented. From the
shipped `change.log`:

    1.52 - new: ability to import CSV files with URLs and other data that can be
           used in the message itself (reference to it with %csv-header-cell-name%
           in message)
    1.96 - new: import of previously exported data is now also importing
           everything else than just the URL
    1.93 - new: project mode "Import + Send + Delete" which will import URLs from
           files, submit the message, delete the list and load next URLs from file
    2.03 - new: option to import URLs from a file every set minutes

So the mechanics are:

  1. A CSV whose header row names columns (e.g. `URL`, `Message`, `Subject`).
  2. A project whose submission message contains the macro `%csv-Message%`
     (and `%csv-Subject%`).
  3. Project mode / scheduler import pointing at that CSV.

Then, per row, the message becomes *that row's* text — one unique message per
website, submitted through the site's own contact form.

This module builds (1), writes it somewhere safe, and reports the exact
message-body + import settings the project needs for (2) and (3).

Column naming note
------------------
The macro is literally `%csv-` + the header cell text + `%`, so the header text
must match the macro exactly. We keep headers alphanumeric and record the exact
macro strings so the UI can insert them without the user guessing.
"""

from __future__ import annotations

import csv
import io
import os
from dataclasses import dataclass, field
from pathlib import Path

from .config_io import ConfigError

URL_HEADERS = {"url", "website", "site", "link", "domain"}
MESSAGE_HEADERS = {"message", "msg", "body", "text", "personal message", "email"}
SUBJECT_HEADERS = {"subject", "title", "headline"}

CHANGELOG_EVIDENCE = [
    "1.52 - import CSV files with URLs + other data, reference via %csv-header-cell-name% in message",
    "1.96 - importing previously exported data now imports everything, not just the URL",
    "1.93 - project mode 'Import + Send + Delete' imports URLs from a file, submits, deletes, next file",
    "2.03 - option to import URLs from a file every set minutes",
]


def imports_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA is not set")
    return Path(appdata) / "GSA_WebsiteContact" / "imports"


@dataclass
class ImportPlan:
    headers: list[str] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)
    url_header: str | None = None
    message_header: str | None = None
    subject_header: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def message_macro(self) -> str | None:
        return f"%csv-{self.message_header}%" if self.message_header else None

    @property
    def subject_macro(self) -> str | None:
        return f"%csv-{self.subject_header}%" if self.subject_header else None

    def to_dict(self) -> dict:
        return {
            "headers": self.headers,
            "row_count": len(self.rows),
            "preview": self.rows[:5],
            "url_header": self.url_header,
            "message_header": self.message_header,
            "subject_header": self.subject_header,
            "message_macro": self.message_macro,
            "subject_macro": self.subject_macro,
            "notes": self.notes,
            "evidence": CHANGELOG_EVIDENCE,
        }


def _norm(h: str) -> str:
    return h.strip().strip('"').lower()


def _classify(headers: list[str]) -> tuple[str | None, str | None, str | None, list[str]]:
    url = msg = subj = None
    notes: list[str] = []
    for h in headers:
        n = _norm(h)
        if url is None and n in URL_HEADERS:
            url = h
        elif msg is None and n in MESSAGE_HEADERS:
            msg = h
        elif subj is None and n in SUBJECT_HEADERS:
            subj = h
    if url is None:
        # first column is the URL by convention; GSA also assumes this
        url = headers[0] if headers else None
        if url:
            notes.append(f"no obvious URL column; assuming the first column {url!r} holds the URL")
    if msg is None:
        notes.append("no message column found — the project's own message will be used for every row")
    return url, msg, subj, notes


def from_rows(headers: list[str], rows: list[dict]) -> ImportPlan:
    headers = [h.strip() for h in headers if h.strip()]
    if not headers:
        raise ConfigError("no columns found")
    url, msg, subj, notes = _classify(headers)
    clean = [{h: (r.get(h) or "").strip() for h in headers} for r in rows]
    clean = [r for r in clean if r.get(url or headers[0], "").strip()]
    if not clean:
        raise ConfigError("no rows with a URL/website value")
    return ImportPlan(headers=headers, rows=clean, url_header=url,
                      message_header=msg, subject_header=subj, notes=notes)


def parse_delimited(text: str, *, delimiter: str | None = None) -> ImportPlan:
    """
    Parse pasted data. Handles, in order of preference:
      * a real CSV with a header row (comma or semicolon)
      * tab-separated (what you get pasting out of Excel / Sheets)
      * `url | message` lines
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    if not text.strip():
        raise ConfigError("nothing pasted")

    lines = [l for l in text.split("\n") if l.strip()]
    if delimiter is None:
        first = lines[0]
        if first.count("\t") >= 1:
            delimiter = "\t"
        elif first.count("|") >= 1 and first.count(",") < first.count("|"):
            delimiter = "|"
        elif first.count(";") > first.count(","):
            delimiter = ";"
        else:
            delimiter = ","

    # pipe / no-header form: every line is "url<delim>message"
    if delimiter == "|":
        rows = []
        for l in lines:
            parts = l.split("|", 1)
            rows.append({"URL": parts[0].strip(), "Message": parts[1].strip() if len(parts) > 1 else ""})
        return from_rows(["URL", "Message"], rows)

    reader = csv.reader(io.StringIO("\n".join(lines)), delimiter=delimiter)
    table = [r for r in reader if any(c.strip() for c in r)]
    if not table:
        raise ConfigError("could not read any columns")

    header_cells = [c.strip() for c in table[0]]
    # A header row is one whose cells are short and not URL-ish.
    looks_header = not any(_looks_url(c) for c in header_cells)
    if looks_header:
        headers, body = header_cells, table[1:]
    else:
        # No header row. A bare 2-column paste is almost always URL + message,
        # so name it that way rather than making the user add a header.
        if len(header_cells) == 2:
            headers = ["URL", "Message"]
        else:
            headers = ["URL"] + [f"Column{n}" for n in range(2, len(header_cells) + 1)]
        body = table

    rows = []
    for r in body:
        rows.append({headers[i]: (r[i] if i < len(r) else "") for i in range(len(headers))})
    return from_rows(headers, rows)


def parse_file(data: bytes, *, filename: str = "") -> ImportPlan:
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return parse_delimited(data.decode(enc))
        except UnicodeDecodeError:
            continue
    raise ConfigError("could not decode the file as text")


def _looks_url(s: str) -> bool:
    s = s.strip()
    return s.startswith(("http://", "https://", "www.")) or ("." in s and " " not in s and "/" not in s[:1])


def to_gsa_csv(plan: ImportPlan) -> str:
    """
    Serialise the plan as RFC4180 CSV with the URL column first.

    GSA reads the header row and exposes each cell as %csv-<header>%, so the
    header text is load-bearing and preserved verbatim.
    """
    order = [plan.url_header] + [h for h in plan.headers
                                 if h not in (plan.url_header,)]
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    w.writerow(order)
    for r in plan.rows:
        w.writerow([r.get(h, "") for h in order])
    return buf.getvalue()


def write_csv(plan: ImportPlan, name: str, *, directory: Path | None = None) -> Path:
    d = directory or imports_dir()
    d.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in name).strip() or "import"
    p = d / f"{safe}.csv"
    p.write_bytes(to_gsa_csv(plan).encode("utf-8-sig"))
    return p


def recommended_project_updates(plan: ImportPlan, csv_path: Path,
                                *, mode: str = "import_send",
                                delete_after: bool = True) -> dict:
    """
    The project settings that make the import actually send the per-person text.

    Keys come from the live .prj plus the binary's literal tokens
    ("ImportSend", "import file", "import min", "import del on").

      * import on / import file -> point the project at our CSV
      * import del on           -> remove each URL after it is handled
      * message subject/body    -> set to the %csv-...% macros

    NOTE: `message subject` / `message body` are *inferred* key names for the
    submission text. They are reported under `unproven_keys` so the UI can warn.
    """
    if not plan.message_header:
        raise ConfigError("no message column; nothing per-person to send")

    upd: dict[str, object] = {
        "scheduler::import on": True,
        "scheduler::import file": str(csv_path),
        "scheduler::import del on": delete_after,
    }
    return upd


UNPROVEN_KEYS = ["project message body (submission text)",
                 "proxy type ids other than 3",
                 "scheduler::import min cadence semantics"]
