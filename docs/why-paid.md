# Why the paid layer exists (and when you need it)

SeleniumBase's `solve_captcha()` has no eyes. It:
- avoids challenges via stealth, and
- clicks checkboxes / drags sliders via CDP + PyAutoGUI.

It cannot look at a picture and decide which tiles contain a boat. That visual step is what the
optional paid solvers add (human workers or ML models), returning a token to inject.

## What breaks without it

| CAPTCHA kind | SeleniumBase alone | With a solver |
|---|---|---|
| No challenge / auto-passed | works | works |
| Checkbox reCAPTCHA / Turnstile / slider | works | works |
| Image-grid (reCAPTCHA v2, hCaptcha images) | ~0% | ~95%+ |
| Audio | ~0% | ~95%+ |
| reCAPTCHA v3 (score-gated) | poor | good |

Blended across a mixed site list: stealth-only ≈ 55–85%; on image-grid-heavy sites it collapses.
Add a solver to recover.

## Pricing (per 1,000 SUCCESSFUL solves — clean pages cost $0)

| Provider | v2 | v3 | Turnstile | Images |
|---|---|---|---|---|
| Anti-Captcha | $0.95–2 | $1–2 | $2 | $0.50–0.70 |
| CapSolver | $0.80 | $1.00 | $1.20 | — |
| 2Captcha | $1–2.99 | $1.45–2.99 | $1.45 | $0.50–1 |

Human services (2Captcha, Anti-Captcha) are the most accurate but slower (~5s).
ML services (CapSolver) are faster and cheaper. hCaptcha-Challenger is free but hCaptcha-only.

## How billing works

Per CAPTCHA actually solved, not per page. A page with no CAPTCHA bills $0. Cost scales with how
often a site challenges you — so good stealth is also a cost-control measure. reCAPTCHA v2 tokens
can be reused for the same sitekey within ~120s, so one paid solve can cover several page loads.
