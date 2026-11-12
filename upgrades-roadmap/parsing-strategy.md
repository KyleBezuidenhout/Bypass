# Parsing strategy — decided 2026-11-12

## Decision

**Keep the local GSA parser. Do not route parsing through TinyFish yet.**

Parsing stays inside GSA. TinyFish stays a *candidate pre-step*, not a component.

## Why

1. **GSA parses internally, so there is no swap hook.** The project file drives
   field identification through the `[ident]` model, with `parse css=1`. GSA never
   calls out to a parser. So "use TinyFish for parsing" really means: fetch URLs
   elsewhere, then re-import the results into GSA. That is a pipeline, not a setting.
2. **The binding constraint is sending, not parsing.** At 10,000 submissions/day the
   parse volume is ~16,700 URLs (~6.5 min of farmed fetching) versus ~10,000 form
   submits across 55 concurrent threads. Parsing is the cheap, fast part.
3. **The headroom is free right now anyway.** TinyFish's own free tier is capped but
   cheap to extend; there is no cost pressure forcing the change.

## The honest counter-argument

TinyFish renders JavaScript. A meaningful share of target sites are JS/SPA pages
where a static parse finds no form at all. That is a **quality** gap, not a cost one,
and it is the one real reason to switch. It is currently unmeasured.

## Trigger to revisit

Revisit when **either** is true:

- Measured form-discovery rate on the live target list is materially below ~60%, and
  spot checks show the misses are JS-rendered pages rather than genuinely form-less
  sites; **or**
- Sending is stable and the next bottleneck becomes send-volume per site (i.e. more
  sites found per hour actually matters more than more submits).

## How to test before committing

Fetch ~200 known target sites through TinyFish Fetch free tier, compare contact-form
discovery against what GSA's local parse finds on the same 200. Decide on that number,
not on vendor coverage claims (they cite 93%, self-evaluated).

## Cost side, for when it matters

- TinyFetch: $0 within 150 URLs/min and 1,000 URLs/day. Past that, no published
  per-URL rate — higher limits go via sales.
- TinyAgent (does the whole interaction, not just parse): $0.016/step, 2 concurrent
  runs. Cents per site, so only worth it where a cheap static-IP submit fails.
- Comparison point: TinyAgent at $0.016/step works out ~$16/1,000 pages for
  schema-shaped output, versus ~$0.90/1,000 from at least one competitor. Worth a
  quote before assuming.

## What this decision does NOT change

- Proxies still go on the **sending** stage, at residential grade.
- The imported-lead-list path stays as-is.
- The TinyFish account-farm work is still worth doing for the day parsing is
  outsourced, but it is not on the critical path.
