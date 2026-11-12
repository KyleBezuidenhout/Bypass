"""
Tiny CLI so you can drive this without the API.

  python -m gsa_wrap.cli health
  python -m gsa_wrap.cli schema [--group performance]
  python -m gsa_wrap.cli settings
  python -m gsa_wrap.cli plan "misc::max threads=25" "misc::use real captcha ip=true"
  python -m gsa_wrap.cli apply "misc::max threads=25"
  python -m gsa_wrap.cli start|stop|restart
"""

from __future__ import annotations

import argparse
import json
import sys

from . import config_io, process, schema as schema_mod


def _parse_kv(pairs: list[str]) -> dict[str, object]:
    out: dict[str, object] = {}
    for p in pairs:
        if "=" not in p:
            raise SystemExit(f"bad pair {p!r}, expected section::key=value")
        ref, _, val = p.partition("=")
        low = val.strip().lower()
        if low in {"true", "yes", "on"}:
            out[ref] = True
        elif low in {"false", "no", "off"}:
            out[ref] = False
        elif val.strip().lstrip("-").isdigit():
            out[ref] = int(val)
        else:
            out[ref] = val
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="gsa_wrap")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health")
    sp = sub.add_parser("schema")
    sp.add_argument("--group")
    sub.add_parser("settings")
    pp = sub.add_parser("plan"); pp.add_argument("pairs", nargs="+")
    aa = sub.add_parser("apply"); aa.add_argument("pairs", nargs="+")
    aa.add_argument("--restart-if-needed", action="store_true")
    for c in ("start", "stop", "restart"):
        sub.add_parser(c)

    args = ap.parse_args(argv)

    if args.cmd == "health":
        st = process.status()
        print(json.dumps({
            "config_path": str(config_io.default_config_path()),
            "app_running": st.running, "app_pids": st.pids,
            "app_exe": str(st.exe_path) if st.exe_path else None,
        }, indent=2))
    elif args.cmd == "schema":
        items = schema_mod.llm_schema()
        if args.group:
            items = [i for i in items if i["group"] == args.group]
        for i in items:
            print(f"{i['ref']:<40} {i['type']:<5} default={i['default']!r}")
            print(f"    {i['help']}")
    elif args.cmd == "settings":
        print(json.dumps(config_io.read_typed(), indent=2))
    elif args.cmd == "plan":
        changes = config_io.plan(config_io.load(), _parse_kv(args.pairs))
        for c in changes:
            print(c)
        print(f"{len(changes)} change(s)")
    elif args.cmd == "apply":
        st = process.status()
        res = config_io.apply(_parse_kv(args.pairs))
        refs = list(_parse_kv(args.pairs))
        need = process.refs_requiring_restart(refs)
        if need and st.running and args.restart_if_needed:
            process.restart(); res["restarted"] = True
        res["needs_restart"] = need
        print(json.dumps(res, indent=2))
    elif args.cmd == "start":
        print(process.launch())
    elif args.cmd == "stop":
        print(process.stop())
    elif args.cmd == "restart":
        print(process.restart())
    return 0


if __name__ == "__main__":
    sys.exit(main())
