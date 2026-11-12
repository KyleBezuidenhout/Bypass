"""
Recursive window/control enumerator for WebContact.exe.

Why this exists: GSA's Settings dialog has *dozens* of checkboxes that never
appear in config.ini. To put an LLM in front of the app we first need a machine
readable map of every control: its class, its caption, its id, and its state.

Delphi specifics handled here:
  * Inactive TTabSheet pages hide their children -> we must select each tab.
  * Real input controls live inside the active page, not on the form.
  * Some dialogs (TCapForm, TForm6) build children lazily -> we Show them first.

Pure ctypes, no pywin32.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as w
import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

u32 = ctypes.windll.user32

ENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, w.HWND, w.LPARAM)

WM_GETTEXT, WM_GETTEXTLENGTH, WM_COMMAND = 0x000D, 0x000E, 0x0111
BM_GETCHECK, BM_CLICK = 0x00F0, 0x00F5
CB_GETCURSEL, CB_GETCOUNT, CB_GETLBTEXT, CB_GETLBTEXTLEN = 0x0147, 0x0146, 0x0148, 0x0149
TCM_GETCURSEL, TCM_GETITEMCOUNT, TCM_SETCURSEL = 0x130B, 0x1304, 0x130C
SB_GETTEXT = 0x040D

# Control classes we treat as "real" inputs worth mapping.
INPUT_CLASSES = {
    "TCheckBox", "TRadioButton", "TEdit", "TMemo", "TComboBox", "TButton",
    "TSpinEdit", "TListBox", "TListView", "TTreeView", "TTabSheet", "TLabel",
    "TGroupBox", "TPanel", "TComboBoxEx", "TDateTimePicker", "TUpDown",
    "TBitBtn", "TStaticText", "TStringGrid", "TValueListEditor", "TTabControl",
}


class RECT(ctypes.Structure):
    _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]


def _text(h: int) -> str:
    n = u32.GetWindowTextLengthW(h)
    if n <= 0:
        # TLabel/TStaticText sometimes need WM_GETTEXT even with len 0
        buf = ctypes.create_unicode_buffer(1024)
        u32.SendMessageW(h, WM_GETTEXT, 1024, buf)
        return buf.value
    buf = ctypes.create_unicode_buffer(n + 1)
    u32.GetWindowTextW(h, buf, n + 1)
    return buf.value


def _class(h: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    u32.GetClassNameW(h, buf, 256)
    return buf.value


def _rect(h: int) -> tuple[int, int, int, int]:
    r = RECT()
    u32.GetWindowRect(h, ctypes.byref(r))
    return r.l, r.t, r.r - r.l, r.b - r.t


def _pid(h: int) -> int:
    p = w.DWORD()
    u32.GetWindowThreadProcessId(h, ctypes.byref(p))
    return p.value


@dataclass
class Ctrl:
    cid: int
    cls: str
    text: str
    x: int
    y: int
    w: int
    h: int
    visible: bool
    enabled: bool
    checked: bool | None = None
    items: list[str] = field(default_factory=list)

    @property
    def kind(self) -> str:
        m = {
            "TCheckBox": "checkbox", "TRadioButton": "radio", "TEdit": "text",
            "TMemo": "multiline", "TComboBox": "dropdown", "TSpinEdit": "number",
            "TButton": "button", "TBitBtn": "button", "TListBox": "list",
            "TTabSheet": "tabpage", "TLabel": "label", "TStaticText": "label",
            "TGroupBox": "group", "TDateTimePicker": "datetime",
        }
        return m.get(self.cls, "other")


def _tabs_of(parent: int) -> list[tuple[str, int]]:
    """(caption, index) for each tab page of a TPageControl."""
    out = []
    n = u32.SendMessageW(parent, TCM_GETITEMCOUNT, 0, 0)
    for i in range(n):
        buf = ctypes.create_unicode_buffer(128)
        u32.SendMessageW(parent, 0x1305, i, ctypes.byref(buf))  # TCM_GETITEM
        out.append((buf.value.strip(), i))
    return out


def children(parent: int) -> list[int]:
    """All descendants. NOTE: EnumChildWindows is already recursive, so we must
    NOT walk into each child again (that double-counts every control)."""
    acc: list[int] = []

    def cb(h, l):
        acc.append(h)
        return True

    u32.EnumChildWindows(parent, ENUMPROC(cb), 0)
    return acc


def describe(h: int) -> Ctrl:
    l, t, ww, hh = _rect(h)
    c = Ctrl(
        cid=u32.GetDlgCtrlID(h), cls=_class(h), text=_text(h),
        x=l, y=t, w=ww, h=hh,
        visible=bool(u32.IsWindowVisible(h)),
        enabled=bool(u32.IsWindowEnabled(h)),
    )
    if c.cls == "TCheckBox":
        st = u32.SendMessageW(h, BM_GETCHECK, 0, 0)
        c.checked = st == 1
    if c.cls in ("TComboBox", "TListBox"):
        n = u32.SendMessageW(h, CB_GETCOUNT, 0, 0)
        for i in range(min(n, 60)):
            ln = u32.SendMessageW(h, CB_GETLBTEXTLEN, i, 0)
            if ln > 0:
                buf = ctypes.create_unicode_buffer(ln + 1)
                u32.SendMessageW(h, CB_GETLBTEXT, i, ctypes.byref(buf))
                c.items.append(buf.value)
    return c


def dump_form(hwnd: int, *, visible_only: bool = False) -> dict:
    """Full description of one form, including all tab pages."""
    out = {"hwnd": hwnd, "cls": _class(hwnd), "title": _text(hwnd), "controls": []}
    for h in children(hwnd):
        d = describe(h)
        if d.cls not in INPUT_CLASSES:
            continue
        if visible_only and not d.visible:
            continue
        out["controls"].append(asdict(d) | {"kind": d.kind})
    return out


def find_forms(pid: int) -> dict[str, int]:
    """{title: hwnd} for every TForm*/dialog owned by pid."""
    found: dict[str, int] = {}

    def cb(h, l):
        if _pid(h) == pid and u32.GetAncestor(h, 2) == h:  # GA_ROOT == self
            c = _class(h)
            if c.startswith("TForm") or c in {
                "TCapForm", "Tproxyform", "TQueryForm", "TAbout_Form", "TLogForm",
            }:
                found[f"{c}|{_text(h)}"] = h
        return True

    u32.EnumWindows(ENUMPROC(cb), 0)
    return found


def select_tab(tabsheet_hwnd: int) -> None:
    """Activate a tab page by clicking its TTabSheet (Delphi switches on click)."""
    u32.SendMessageW(tabsheet_hwnd, 0x0201, 0, 0)  # WM_LBUTTONDOWN
    u32.SendMessageW(tabsheet_hwnd, 0x0202, 0, 0)  # WM_LBUTTONUP
    time.sleep(0.35)


def map_all(pid: int, out_path: Path | None = None) -> dict:
    forms = find_forms(pid)
    result = {"pid": pid, "forms": {}}
    for name, h in forms.items():
        result["forms"][name] = dump_form(h)
    if out_path:
        out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    import sys
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    if not pid:
        import subprocess
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq WebContact.exe", "/FO", "CSV", "/NH"],
                             capture_output=True, text=True).stdout
        for line in out.splitlines():
            parts = [p.strip('"') for p in line.split('","')]
            if len(parts) >= 2 and parts[0].lower() == "webcontact.exe":
                pid = int(parts[1])
                break
    res = map_all(pid, Path("_work/dialogs.json"))
    for form, d in res["forms"].items():
        print(f"\n### {form}  ({len(d['controls'])} controls)")
        for c in d["controls"]:
            if c["kind"] in ("checkbox", "dropdown", "number", "text", "multiline", "radio"):
                mark = "" if c["checked"] is None else (" [x]" if c["checked"] else " [ ]")
                print(f"  {c['kind']:<9} {c['cls']:<14} id={c['cid']:<7} {c['text']!r}{mark}")
        print(f"  -> written to _work/dialogs.json")
