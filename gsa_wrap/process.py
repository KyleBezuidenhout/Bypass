"""
Process control for WebContact.exe: locate it, see if it is running, launch it,
and detect whether a pending change needs a restart to take effect.

Deliberately small and dependency-free (no pywin32). Uses `tasklist`/`taskkill`
on Windows so it runs with a stock CPython.
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

EXE_NAME = "WebContact.exe"
DEFAULT_INSTALL_DIRS = [
    Path(r"C:\GSA_WebsiteContact"),
]

# Settings proven (via the registration flow message "Please restart the program
# now.") or strongly indicated to be read only at startup. Editing these while
# the app is running will not take effect until it restarts.
RESTART_REQUIRED_PREFIXES = (
    "misc::f1.",          # window geometry, applied at layout time
    "misc::scaling mode",  # DPI mode chosen at startup
)


class ProcessError(Exception):
    pass


@dataclass
class ProcStatus:
    running: bool
    pids: list[int]
    exe_path: Path | None


def find_exe(install_dir: Path | None = None) -> Path:
    candidates = [Path(install_dir)] if install_dir else DEFAULT_INSTALL_DIRS
    for d in candidates:
        exe = d / EXE_NAME
        if exe.exists():
            return exe
    raise ProcessError(f"{EXE_NAME} not found in {[str(c) for c in candidates]}")


def _tasklist_pids(image: str) -> list[int]:
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {image}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=20,
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        raise ProcessError(f"tasklist failed: {exc}") from exc

    pids: list[int] = []
    for line in out.splitlines():
        line = line.strip()
        if not line or "No tasks" in line:
            continue
        # CSV: "Image Name","PID","Session Name","Session#","Mem Usage"
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[0].lower() == image.lower():
            try:
                pids.append(int(parts[1]))
            except ValueError:
                pass
    return pids


def status(install_dir: Path | None = None) -> ProcStatus:
    exe: Path | None
    try:
        exe = find_exe(install_dir)
    except ProcessError:
        exe = None
    pids = _tasklist_pids(EXE_NAME)
    return ProcStatus(running=bool(pids), pids=pids, exe_path=exe)


def launch(install_dir: Path | None = None, *, wait_s: float = 12.0) -> int:
    """Start the app and wait until it reports a window, returning its pid."""
    exe = find_exe(install_dir)
    # DETACHED so it survives us; the app manages its own window.
    subprocess.Popen(
        [str(exe)],
        cwd=str(exe.parent),
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        close_fds=True,
    )
    deadline = time.time() + wait_s
    while time.time() < deadline:
        pids = _tasklist_pids(EXE_NAME)
        if pids:
            return pids[0]
        time.sleep(0.5)
    raise ProcessError(f"{EXE_NAME} did not start within {wait_s}s")


def stop(timeout_s: float = 15.0) -> bool:
    """Graceful taskkill, escalating to /F. True if it is gone afterwards."""
    pids = _tasklist_pids(EXE_NAME)
    if not pids:
        return True
    subprocess.run(["taskkill", "/IM", EXE_NAME], capture_output=True, text=True, timeout=20)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if not _tasklist_pids(EXE_NAME):
            return True
        time.sleep(0.5)
    subprocess.run(["taskkill", "/IM", EXE_NAME, "/F"], capture_output=True, text=True, timeout=20)
    time.sleep(1.0)
    return not _tasklist_pids(EXE_NAME)


def restart(install_dir: Path | None = None) -> int:
    stop()
    return launch(install_dir)


def refs_requiring_restart(refs: list[str]) -> list[str]:
    return [r for r in refs if r.startswith(RESTART_REQUIRED_PREFIXES)]


@dataclass
class ApplyOutcome:
    """What the service reports back after a settings write."""

    changed: list[str]
    verified: bool
    bounced: list[str]
    backup_path: str | None
    restart_needed: bool
    app_was_running: bool
