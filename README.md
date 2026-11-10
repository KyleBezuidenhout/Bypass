# captcha-bypass

All-in-one, open-source CAPTCHA bypass for web scraping and automation.

Two layers, one clean interface:

1. **Stealth + click (free, required)** — [SeleniumBase](https://github.com/seleniumbase/SeleniumBase) CDP mode.
   Avoids most challenges and clicks checkboxes / sliders. Handles Cloudflare Turnstile and
   simple widgets with zero cost.
2. **Vision solving (optional, paid)** — plug in any solver API (2Captcha, Anti-Captcha, CapSolver).
   Only needed for image-grid / audio / hard challenges. You pay **per solve**, and only when a
   CAPTCHA actually appears — a clean page costs $0.

Runs headless on a Linux server. No proxies required to start.

---

## Install

```bash
pip install -r requirements.txt
# optional (only if using the paid layer):
cp .env.example .env    # then paste your API key(s)
```

## Quick start

```python
from captcha_bypass import Bypass

with Bypass() as b:
    b.goto("https://example.com/protected")
    html = b.page_source()
    print(len(html))
```

`Bypass()` auto-detects CAPTCHAs, routes them to the best available solver, injects the token,
and falls back to stealth-only clicking if no paid key is set.

## The paid layer (optional)

Set any of these env vars — the library picks the cheapest capable solver automatically:

| Provider | Env var | Typical price / 1000 solves | Notes |
|---|---|---|---|
| Anti-Captcha | `ANTICAPTCHA_KEY` | $0.50–2 | human workers, very accurate |
| CapSolver | `CAPSOLVER_KEY` | $0.80–1.20 | ML, fast, cheapest paid |
| 2Captcha | `TWOCAPTCHA_KEY` | $1.00–2.99 | human workers, broadest coverage |
| hCaptcha-Challenger | (self-host) | free | hCaptcha only, ML |

Reality check: without the paid layer you still pass **most** sites. You only lose the image-grid
and audio fraction (which drops to ~0 on those specific sites). See `docs/why-paid.md`.

## Layout

```
captcha_bypass/
  __init__.py
  config.py            # env / key handling
  browser.py           # SeleniumBase CDP stealth launcher
  detect.py            # find CAPTCHAs + sitekeys on a page
  bypass.py            # orchestrator: detect -> solve -> inject
  solvers/
    base.py            # BaseSolver + registry
    anticaptcha.py
    capsolver.py
    twocaptcha.py
examples/
  scrape.py
  solve_turnstile.py
```

## License

MIT. SeleniumBase is MIT. The paid solver APIs have their own terms.

## Credits

Stealth engine: [SeleniumBase](https://github.com/seleniumbase/SeleniumBase) by Michael Mintz.
