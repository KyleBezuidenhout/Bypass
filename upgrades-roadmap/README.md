# Upgrades roadmap

Decisions and plans for what to change, and in what order. Newest decision on top.

The rule for this folder: **a decision is only recorded here once it is decided.**
Options that are still open stay in `open-questions.md`.

## Rolling decisions log

| # | Date | Decision | Status | Doc |
|---|------|----------|--------|-----|
| 1 | 2026-11-12 | Keep the **local GSA parser** for now. Do **not** route parsing through TinyFish yet. | Decided | [parsing-strategy.md](parsing-strategy.md) |
| 2 | 2026-11-12 | Treat **10k forms/day as a sending target**, not a parsing target. Size proxies and accounts against that. | Decided | [capacity-10k.md](capacity-10k.md) |
| 3 | — | TinyFish account farm: how many accounts, and how to avoid flags | Open | [open-questions.md](open-questions.md) |
| 4 | 2026-11-12 | Where the CSV lives, how the header row maps columns, existing sending windows, and what proxies to buy for 5k/day | Decided | [import-schedule-and-proxies.md](import-schedule-and-proxies.md) |
| 5 | 2026-11-12 | Before buying any sending pool, **run a small stratified split test** to measure the cheap-vs-clean proxy gap for real. ~$26 test, ~1 day. | Decided | [import-schedule-and-proxies.md](import-schedule-and-proxies.md) §6–§8 |
| 6 | 2026-11-12 | Panel gets a **single shared password lock** (env-driven, opt-in). Remote access via **Cloudflare Tunnel + Access**, password kept on as a second lock. | Decided | [remote-access.md](remote-access.md) |
| 7 | 2026-11-12 | Dev from the Mac: **UI on GitHub + Vercel**, **backend stays on the PC**. No build step, so the UI is portable; the backend must stay because it drives GSA locally. | Decided | [mac-development.md](mac-development.md) |

## Why the local parser wins for now

Short version: GSA parses **internally** (`[ident]` model, `parse css`), so there is no
"swap in a better parser" hook. Any external parser has to run as a **pre-step** on
URLs and be re-imported, which is real integration work. The measured win is not yet
big enough to justify that, because the binding constraint at 10k/day is **sending**,
not parsing.

Full reasoning, including the numbers and the exact trigger for revisiting:
[parsing-strategy.md](parsing-strategy.md).

## Regenerating the numbers

The figures in `capacity-10k.md` are generated, not typed. To refresh them:

```powershell
$env:PYTHONPATH="."
python -c "import json; from gsa_wrap import sizing as s; print(json.dumps(s.capacity_10k(10000, 60), indent=2))"
```

Live equivalents are also served by the panel API:

- `GET /sizing/capacity?daily_sends=10000&found_pct=60`
- `GET /sizing/proxies-for?daily_sends=5000`
- `GET /sizing/farm?accounts=17`
- `GET /sizing/farm-safety`
- `GET /sizing/cheap-proxies?daily_sends=5000`
- `GET /sizing/split-test?daily_sends=5000&detect_pp=10`
- `GET /sizing/procurement?daily_sends=5000&detect_pp=10`
