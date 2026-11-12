"""
Zero-dependency dev server for editing the panel UI from any machine.

Why this exists: the backend must run on the Windows PC (it shells out to the
GSA binary and writes the .prj/ini), so on a Mac you cannot run `uvicorn`. But
the UI is a single HTML file with no build step — you only need a static server
with live reload. This is that, in ~80 lines and stdlib only.

Usage (on the Windows PC, in the repo root):
    python dev-server.py                # http://localhost:5500, reloads on save
    python dev-server.py --port 5501    # if 5500 is taken

Then open http://localhost:5500, edit `ui/index.html` in your editor, and the
page reloads itself on save.

Two modes, picked per request via the `X-Panel-Mode` header:

  * `mock`    -> serves ui/*.html and answers the handful of GET endpoints the
                 UI needs on load with canned JSON. No import of gsa_wrap, so it
                 runs anywhere (including a Mac with no deps installed).
  * `backend` -> reverse-proxies everything to a running panel (default
                 http://127.0.0.1:8000), so real settings and real actions work.

The injected reload script polls a `__rev` counter that ticks when a watched
file changes; when it moves, the page does `location.reload()`.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UI = ROOT / "ui"
WATCH = [UI / "index.html", UI / "login.html"]

_rev = 0
_lock = threading.Lock()


def _snapshot() -> dict[str, float]:
    stamps: dict[str, float] = {}
    for p in WATCH:
        try:
            stamps[str(p)] = p.stat().st_mtime
        except OSError:
            stamps[str(p)] = 0.0
    return stamps


def _watcher(interval: float = 0.6) -> None:
    global _rev
    last = _snapshot()
    while True:
        time.sleep(interval)
        now = _snapshot()
        if now != last:
            last = now
            with _lock:
                _rev += 1


RELOAD_SNIPPET = """
<script>
(function(){
  let seen = null;
  async function poll(){
    try {
      const r = await fetch("/__rev", {cache:"no-store"});
      const n = (await r.json()).rev;
      if (seen === null) seen = n;
      else if (n !== seen) { location.reload(); return; }
    } catch(e) {}
    setTimeout(poll, 900);
  }
  poll();
})();
</script>
"""

# Canned GET responses so the UI is fully browsable with the backend offline.
MOCK: dict[str, object] = {
    "/health": {"ok": True, "config_exists": True, "app_running": False,
                "app_exe": "C:/GSA/website_contact.exe", "note": "mock mode"},
    "/auth/status": {"auth": "off"},
    "/glossary": {"terms": []},
    "/schema": {"count": 0, "groups": [], "sections": [], "fields": []},
    "/settings": {"values": {}},
    "/settings/defaults": {"defaults": {}, "missing": []},
    "/projects": {"projects": []},
}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    backend = "http://127.0.0.1:8000"
    root: Path = ROOT

    # ---------------------------------------------------------------- helpers
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj: object, code: int = 200) -> None:
        self._send(code, json.dumps(obj).encode(), "application/json")

    def _mode(self) -> str:
        return (self.headers.get("x-panel-mode") or "mock").lower()

    # ---------------------------------------------------------------- routing
    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]

        if path == "/__rev":
            with _lock:
                return self._json({"rev": _rev})

        if path in ("/", "/index.html", "/login"):
            return self._page("login.html" if path == "/login" else "index.html")

        if path == "/logout":
            # dev has no session; bounce straight back to the panel
            self.send_response(302)
            self.send_header("Location", "/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        if self._mode() == "backend":
            return self._proxy()

        if path in MOCK:
            return self._json(MOCK[path])
        # unknown API path in mock mode: empty object beats a 404 the UI logs
        return self._json({"note": "mock: not implemented", "path": path})

    def do_POST(self) -> None:
        if self._mode() == "backend":
            return self._proxy()
        length = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            parsed = json.loads(raw or b"{}")
        except ValueError:
            parsed = {}
        return self._json({"ok": True, "echo": parsed, "note": "mock: not applied"})

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", self.headers.get("origin", "*"))
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ---------------------------------------------------------------- pieces
    def _page(self, name: str) -> None:
        f = self.root / "ui" / name
        if not f.exists():
            return self._send(404, b"missing " + name.encode(), "text/plain")
        html = f.read_text(encoding="utf-8")
        if "</body>" in html:
            html = html.replace("</body>", RELOAD_SNIPPET + "</body>", 1)
        else:
            html += RELOAD_SNIPPET
        return self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")

    def _proxy(self) -> None:
        length = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(length) if length else None
        req = urllib.request.Request(
            self.backend + self.path,
            data=body,
            method=self.command,
            headers={k: v for k, v in self.headers.items()
                     if k.lower() in ("content-type", "authorization", "cookie", "accept")},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                payload = r.read()
                ctype = r.headers.get("content-type", "application/json")
                self.send_response(r.status)
        except urllib.error.HTTPError as e:
            payload = e.read()
            ctype = e.headers.get("content-type", "application/json")
            self.send_response(e.code)
        except Exception as e:  # backend down
            return self._json({"error": f"backend unreachable: {e}"}, 502)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, fmt: str, *args) -> None:
        if "__rev" in (args[0] if args else ""):
            return
        print(f"  dev {self.command} {self.path} -> {args[1] if len(args) > 1 else ''}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Panel dev server with live reload.")
    ap.add_argument("--port", type=int, default=5500)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--backend", default="http://127.0.0.1:8000",
                    help="panel to proxy to when X-Panel-Mode: backend")
    args = ap.parse_args()

    Handler.backend = args.backend.rstrip("/")
    threading.Thread(target=_watcher, daemon=True).start()

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print("")
    print(f"  dev server   http://{args.host}:{args.port}")
    print(f"  mode         mock (X-Panel-Mode: backend proxies to {Handler.backend})")
    print(f"  watching     {', '.join(p.name for p in WATCH)}  — save to reload")
    print("")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  bye")


if __name__ == "__main__":
    main()
