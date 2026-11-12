# Sending 5,000 forms/day — where things go and what to buy

Two questions answered here: **where the files and mappings live**, and **what
proxies to buy**. Both grounded in the live install, not in documentation.

---

## 1. Where you upload websites + personalisation

Everything happens from the project, not a separate screen. The live project is
`%APPDATA%\GSA_WebsiteContact\projects\robotics outbound.prj`.

### Step 1 — build the CSV

Drop it in the imports folder, which already exists:

```
%APPDATA%\GSA_WebsiteContact\imports\
```

You already have `robotics week 1.csv` there with a `URL,Message,Subject` header.

### Step 2 — the header row IS the mapping

**This is the part people miss.** There is no separate mapping table to fill in.
The CSV header row *is* the field mapping: a column named `Message` becomes the
macro `%csv-Message%`, and it is matched by name, verbatim.

So the mapping is done by naming your columns, then calling those names from the
project's message text.

| If your column header is | The macro you get | Use it in |
|---|---|---|
| `URL` | `%csv-URL%` | the target column (auto) |
| `Message` | `%csv-Message%` | the project message body |
| `Subject` | `%csv-Subject%` | the project message subject |

Notes that matter:

- Header text must match the macro **exactly** — keep headers alphanumeric.
- Your live message body is already a macro template: `{Hello|Hi|Dear|To the} %domain% {Owner|Webmaster|Admin|Administrator}`.
  Add the per-person line by including `%csv-Message%` in that same body.
- `{a|b|c}` picks one at random. So mixing a static body with `%csv-Message%`
  gives a per-person opener inside a rotating wrapper.

### Step 3 — point the project at the file

Already wired in your `.prj`, under `[scheduler]`:

| Key | Your current value | Meaning |
|---|---|---|
| `import on` | `1` | import mode is ON |
| `import file` | `...\imports\robotics week 1.csv` | which file |
| `import del on` | `1` | delete each row after handling it |
| `import min` | `30` | re-check the file every 30 minutes |

> Caveat: `import min` cadence semantics are **unproven** from the artefacts we
> have. Treat 30 as "how often it looks for new rows", and verify by watching a
> short run rather than trusting it.

---

## 2. Sending windows and schedules (already configured)

These live in `.prj` under `[scheduler]`. Your current settings:

| Key | Value | Read |
|---|---|---|
| `sender on` | `0` | **schedule is OFF** — nothing sends until this is 1 |
| `sender workday` | `1` | weekdays on |
| `sender weekend` | `0` | weekends off |
| `sender start` | `08:30` | window opens |
| `sender stop` | `16:30` | window closes |
| `send limit on` | `0` | rate cap **OFF** |
| `send limit` | `100` | would send 100 per interval |
| `send limit type` | `1` | interval unit |
| `scraper on` | `0` | true, since you import rather than scrape |

**Three live problems for a 5,000/day goal:**

1. **`sender on=0`** — the schedule exists but is switched off. Nothing is sending.
2. **`send limit on=0` with a target of 5,000/day** — an 8-hour window means ~10
   sends/minute sustained. With no cap, GSA front-loads and can finish early, then
   sit idle. Turn the cap on so the day is paced.
3. **`scraper on=0`** is correct for you, but `proxies for se` is still on and
   burning capacity for engines you never call.

**A sane 5,000/day window:** keep `08:30–16:30` on weekdays, turn `send limit on=1`,
and set `send limit` so the arithmetic lands under 5,000/day for the window length.
Also decide `sender weekend` deliberately — currently it will stop on Saturday.

---

## 3. Proxies for 5,000 sends/day

Generated from `gsa_wrap.sizing.proxy_recommendation(5000)`.

| Quantity | Value |
|---|---|
| Recommended threads | 30 |
| IPs required (1 per thread) | 30 |
| **IPs to actually buy (10% spare)** | **33** |
| Grade | Dedicated static ISP / dedicated residential |
| Not | rotating residential, not shared datacenter |

### Buy this

| Rank | Vendor | $/IP | ~Monthly at 33 |
|---|---|---|---|
| 1 | IPNux | $2.00 | ~$66 |
| 2 | PinnedIP | $2.03 | ~$67 |
| 3 | Rayobyte | $5.00 | ~$165 |

Cheapest genuinely unmetered dedicated tier. **Unmetered matters** — sends are many
tiny requests, not a bulk crawl, so per-GB billing is the wrong meter.

### Do not buy this

| Option | Verdict | Why |
|---|---|---|
| Webshare shared ($0.30/IP) | Wrong for sending | Shared reputation, 250 GB/IP |
| Rotating residential (per GB) | See below | Sticky-identity risk, and dearer at scale |
| Datacenter/cloud ($0.30–1/IP) | The classic mistake | Form endpoints recognise DC ranges, captcha rates jump |

### The reality check

Honest spend: **~$66–165/month on 33 dedicated IPs**. That is the price of looking
like 30 real people. Captcha at this volume is ~$19/month — noise next to the proxies.

**Buy to match threads, not more.** Spare IPs idle. 33 = 30 threads + 10% so one
flagged IP does not stall the run.

---

## 4. Would a $1.56/GB rotating residential plan work instead?

Short answer: **for parsing yes, for sending no** — and it costs more at this volume.

### The sending problem

Submitting a form is several requests in a row: load the page, fetch the captcha,
POST the form. Many sites tie the session cookie and any captcha to the exit IP. If
the IP rotates between the GET and the POST, the site can drop the submission.

**"Automatic IP rotation" is literally the opposite of what sending needs.** The
screenshot's own selling point is the failure mode here.

And GSA cannot fix it: there is **no sticky-session setting anywhere in `config.ini`**.
The only proxy-session-ish keys are `stop project on no proxy` and `use real captcha ip`.
So the vendor must do the pinning.

### The workaround (unproven)

Do not hand GSA one rotating gateway URL. Give it the vendor's **sticky session
endpoint list** — one port per session — so GSA assigns one per thread and holds it
for that site's submission. Stickiness then comes from the list shape, not a setting.
Verify by watching one submission and confirming the exit IP does not move.

### Cost, which is where it really loses

| Measure | Value |
|---|---|
| Traffic at 5,000 sends/day | ~61 GB/month |
| Rotating residential, realistic rate | **$153–336/month** |
| Dedicated static ISP instead | **$66/month for 33 IPs** |

The $1.56/GB headline is a very-high-volume rate; ~61 GB/month will not be on it.
Form submission is high-page-weight and low-request-count, so **per-GB billing
punishes exactly this workload**, while dedicated is per-IP and unmetered.

### Verdict

| Use for | Buy |
|---|---|
| Sending | Dedicated static ISP |
| Parsing | Rotating residential is legitimate, or cheap datacenter |

Buy the rotating plan only as the parsing tier, or as a cheap test before committing
to 33 dedicated IPs.

---

## 5. The IPNux checkout trap — read before you pay

The dashboard showed **$9.00/IP** while IPNux's own pricing page advertises
**"from $2.00"**. That is a 4.5x gap, and if you had clicked through you would have
paid ~$297/month instead of ~$66–165.

### Why the gap exists

The page has a **quality selector** that the marketing headline hides:

| Tier | From $/IP | What it claims |
|---|---|---|
| Regular | $5.00 | Improved screening, for small/start-up businesses |
| **Premium** | **$9.00** | Best performance for top-targeted domains ← **pre-selected** |
| Dedicated | $14.00 | "Crafted for power users" |

The checkout had **Premium** selected. That is the trap — not a dishonest page, just a
default that is not the one you want.

### What to actually do

1. **Select Regular explicitly.** It is still dedicated, residential, and unlimited
   bandwidth. Premium buys "better performance on top-targeted domains" — a
   nice-to-have, not a requirement for submitting a form.
2. **Read the checkout TOTAL**, not the per-IP figure, and ignore any VAT line.
3. **Confirm the word DEDICATED.** Their API also exposes a "Shared (ISP)" type at a
   different rate, and shared is not what sending wants.
4. **Longer period is cheaper** — their docs say 10% off at 60 days, 15% off at 90 days.
5. **Order ~33 IPs** to match threads. The discount table starts at 10–500, so a
   smaller order gains no scale benefit.

### What that is worth

| Option | 33 IPs / month |
|---|---|
| IPNux Premium (as quoted) | ~$297 |
| IPNux Regular | ~$165 |
| PinnedIP | ~$67 |

Downgrading the tier saves ~$132/month; switching vendor on top saves ~$230/month.

> **Honesty note:** neither the marketing page nor the dashboard could be loaded
> programmatically (403), so these are read-from-screen figures. Verify at checkout.

---

## 6. Are cheaper proxy types useless? What deliverability is actually lost

**Short answer: not useless, and the loss is concentrated, not uniform.** Cheap
proxies behave *identically* to good ones on unprotected sites and only fail on
hardened ones. Nothing about the loss is spread evenly, so "cheap" is not a
blanket downgrade — it is a downgrade of a fraction of your list.

Live numbers: `GET /sizing/cheap-proxies?daily_sends=5000`
(code: `sizing.cheap_proxy_tradeoff`). **The loss percentages below are reasoned,
not measured.**

### The asymmetry that decides everything

- **A parse failure is loud.** The page will not load, GSA books a status, you see
  it and retry. Nothing is lost unseen.
- **A send failure is often silent.** reCAPTCHA v3 returns a *score* and the
  target form decides; a low-score submit can be accepted, soft-rejected, or
  dropped with no error at all.

Consequence: **spend on the sending stage first.** Parsing runs fine on junk.

### Where the loss actually lands (5,000 sends/day model)

| Site class | Share | Loss on cheap | Why |
|---|---|---|---|
| No protection | 55% | **0%** | Nothing inspects the IP. Datacenter loads and submits fine. |
| Light protection | 30% | **8%** | Akismet / basic Cloudflare: mostly content scoring, small IP effect. |
| Hardened | 15% | **35%** | reCAPTCHA v3 / bot mode: these *do* score the IP. |

- Blended: **~7.7%** from the datacenter penalty alone.
- Add **~4%** if the pool is *also* shared (inherited reputation, rate limits).

### Two axes — do not collapse them

1. **Shared vs dedicated** — whose reputation is on the IP.
2. **Datacenter vs residential** — what kind of network the IP lives on.

The cheapest options are **both** shared **and** datacenter: worst corner on both
axes, which is why they feel so bad. Fixing one axis (e.g. *dedicated*
datacenter) removes half the penalty for very little money.

### Options, with the loss attached (33 IPs, 5k/day)

| Option | $/mo | Loss vs dedicated ISP |
|---|---|---|
| Free public lists | $0 | ~24% |
| Shared datacenter | ~$9.90 | ~12% |
| Dedicated datacenter | ~$33.00 | ~7.7% |
| Dedicated static ISP | ~$66.99 | 0% |

### Breakeven

Upgrading from shared DC to dedicated ISP costs **~$57/month** and recovers
**~17,550 sends/month**. That pays for itself if a recovered contact is worth
more than **~$0.003**. At any normal lead value the maths is not close — the limit
is cashflow tolerance, not economics.

### Fix this before buying anything

Send failures are currently **being lost**: live config has `retry failed=0` and
`export failed on=0`, so a rejected submit is invisible. Turn on failed-send
export + retry **first**. You cannot size a proxy upgrade you cannot measure.

### The smart compromise — split by stage

- **Send pool (~33 IPs):** must be clean. This is the reputation-sensitive stage.
- **Parse pool:** whatever is cheap — shared DC or free lists, sized separately.

Running both on dedicated ISP wastes the good IPs on page loads nobody scores.

**Cheapest non-stupid setup:** sending only on *dedicated datacenter* (~$1/IP),
parsing on shared DC / free. Keeps the hard fraction landing without paying the
full ISP premium.

### How to replace these guesses with your own number

Use the stratified protocol in §7 (this supersedes the rough "500 vs 500" sketch).
Compare the *Successfully Sent* rate, not replies.

> The earlier "dedicated ISP for sending" rule still stands as the safe floor. If
> the price bites, **dedicated datacenter is a legitimate step down** — losing
> part of one axis, not both.

---

## 7. Split-testing proxy grade without fooling yourself

You **cannot hold captcha constant** — a captcha failing *is* the outcome. So you
balance the captcha mix across arms and **attribute** each failure instead.

Live design + sample sizes: `GET /sizing/split-test?daily_sends=5000&detect_pp=10`
(code: `sizing.split_test_design`).

### Design: randomised block (stratified)

- **Unit:** the URL. One site = one row = one arm.
- **Stratify** by protection class (none / light / hardened), then **coin-flip
  within each stratum.** Classify protection *before* assignment.
- Two plain lists differ in composition more than the proxies differ — that is why
  stratification matters.
- Optional paired variant (same URL both arms) needs `skip dupecheck` or the second
  arm is blocked as a duplicate.

### Metric

- **Primary:** `confirmed_send_rate` — reached a real confirmation marker, not just
  HTTP 200.
- **Not the metric:** "did not error". Silent drops look identical to success.

### Attribute the failures

Log a code per attempt: `success_confirmed`, `blocked_waf`, `captcha_unsolved`,
`captcha_solved_then_rejected`, `silent_drop`, `field_not_found`, `timeout`,
`proxy_dead`.

- If the delta is `silent_drop` + `captcha_solved_then_rejected` → that is the IP effect.
- If `proxy_dead` dominates → you measured pool hygiene, not grade.
- `timeout` must **not** count as a reject.

### Sample size (α 0.05, power 0.8)

| Stratum | Share | n per arm |
|---|---|---|
| No protection | 55% | 116 |
| Light protection | 30% | 222 |
| Hardened | 15% | 31 |

- **Minimum total:** 738 attempts. **With A/A floor + canary + dropout: 1,476.**
- **At 5,000/day that is ~1 day.**
- Trap: the hardened effect is *large*, so n=31 looks decisive — but one bad IP can
  produce it by chance.

### Hold identical

Message template **and spin seed**, sender domain, captcha solver + settings, `use
real captcha ip`, timeout (generous — fast DC IPs flatter the cheap arm), retry
policy, thread split, many/all field values, proxy geography.

Only the proxy grade varies. Clone the project and **diff** it to prove that.

### Kill these confounds

List composition, IP warmup, captcha type, solver settings, content, sender
reputation, concurrency, time of day, timeout-as-reject, dupecheck (when pairing),
IP/ASN clustering (30 sends from 1 IP ≠ 30 samples — analyse per-IP).

### Controls

- **Positive canary:** ~50 easy sites that must pass on *both* arms — validates the harness.
- **A/A noise floor:** dedicated vs dedicated. If |B − B'| is 5%, an A/B gap of 5% is noise.
- **Pre-register** metric, n and threshold before starting.

### Decision rule

- **Adopt cheap** only if the pooled loss CI is inside tolerance AND no stratum collapses.
- **Keep dedicated** if the loss is concentrated on hardened sites even when pooled looks small.
- **Cannot call it** if |A − B| sits inside the noise floor — buy more sample.

---

## 8. What to buy for the test, and how to hand it over

Live plan: `GET /sizing/procurement?daily_sends=5000&detect_pp=10`
(code: `sizing.procurement_plan`).

**Key point: do NOT buy the full 33-IP sending pool for this.** The test asks
*which grade*, not *how much capacity*. It needs ~1,476 attempts ⇒ ~13 threads ⇒ a
few spare-padded IPs per arm.

### Arms

| Arm | What | Vendor | Why this vendor |
|---|---|---|---|
| A | Shared datacenter | **Webshare** | Cheapest real option; GSA pulls it itself via API token. |
| B | Dedicated static ISP | **PinnedIP** | Cheapest dedicated ISP (~$2.03/IP), 1-IP minimum, no per-GB meter. |
| B' | More dedicated ISP (A/A) | PinnedIP | Same grade as B → measures the noise floor. |

**Estimated test cost: ~$26/month** (7 + 7 + 5 IPs). Pocket change vs a $90 order.

This is also why the IPNux $9/IP was painful — a 5-IP test there would have forced a
$45–90 order. PinnedIP's ~$2.03 with no minimum makes the test cheap.

### Proven vendor facts (from the app itself)

- GSA has a **built-in WebShare importer**: Settings path `proxy.webshare.io/api/...`,
  `Authorization: Token`, auto-refresh frequency. So arm A needs no manual list.
- GSA has a **built-in Blazing / Rayobyte importer** (`rayobyte.com/proxy/dashboard/api/...`).
- Manual import accepts **`login:password@host:port`** and `host:port` — this is the
  app's own on-screen hint, quoted from the proxy dialog.

### Handover

Drop files in **`proxy-pools/`** in the workspace:

- `proxy-pools/arm-a-cheap.txt`
- `proxy-pools/arm-b-clean.txt`
- `proxy-pools/arm-b-prime-aa.txt`

Format: one proxy per line, `login:password@host:port`. `#` and blank lines ignored.
**Both arms must be the same country.**

Templates with headers are already committed there.

### Then it is automated

Parse + de-dupe → clone project per arm and **diff to prove only the proxy source
differs** → set proxy type + enable sending-proxy → turn on `retry failed` +
`export failed on` → match threads/timeout/captcha/message/spin-seed → stratify and
coin-flip the URL list into `/import/a.csv` and `/import/b.csv`.

### Buying caveats

- Minimum order sizes bite more than price at this scale (budget plans start ~20 IPs).
- Check the **total at checkout**, not the headline rate (the IPNux trap).
- Same country both arms. Buy both at once. Warm both equally.
- Keep the ISP IPs even if cheap wins — the warmed ones are your sending floor.

---

## 9. Do captchas replace our proxies? Do parse proxies need to be good?

**No to both — for the same reason.** A captcha service's proxy and your proxy act on
**different hops**.

Live: `GET /sizing/stages` (code: `sizing.stage_requirements`).

### Three hops happen per submission. The service covers one.

1. **Yours:** you load the form page from the target, through your proxy.
2. **Theirs:** the service fetches a captcha token using **its own IPs**.
3. **Yours:** you POST the form. Their proxy is gone by now.

A per-solve plan is billed per solve and its proxy only exists for that one request —
so you cannot browse a site through it. "Run everything through there" is impossible.

### Why the solver does not fix your problem

A solved token is bound to an IP, and the **target** decides whether to trust it.
reCAPTCHA v3 returns a *score*. A low-trust IP can get a successful solve and still be
rejected or silently dropped. **Captcha services get you past the puzzle; they do not
upgrade your IP reputation.**

### Proven from the app

The setting **`use real captcha ip`** exists (misc), live value `0`, with the app's own
help text: *"Solve captchas from your real IP instead of through a proxy. More reliable
solves, but exposes your address to the captcha provider."* It decides which IP the
solve is bound to — which is why your send proxies must be sticky. Hold it constant
across test arms.

### Parse proxies: cheap is genuinely fine

- No captcha occurs at parse time.
- Nothing scores the IP.
- Failures are **loud and retryable**.
- Keep it on the `proxies for parse` role so it does not burn the clean pool's budget.

**Caveat:** very hostile targets can block datacenter ASNs from *parsing* too, lowering
find-rates. That affects discoverability, not deliverability.

### The hybrid

| Layer | Grade | Cost shape |
|---|---|---|
| Parse pool | cheap | ~$0.30/IP |
| Send pool | clean (static ISP) | ~$2.03/IP — the real line item |
| Captcha | the layer-2 subscription | per solve (already budgeted) |

Two of the three are not the expensive axis. Everything is still needed at full scale:
the clean send pool stays ~1 IP per concurrent thread.

---

## 10. The whole money picture — where every dollar goes and why

Live: `GET /sizing/spend` (code: `sizing.spend_breakdown`). Line maths is auditable;
labelled rates are listed in the response's `assumption_ledger`.

| # | Bucket | $/mo (5k/day) | Buys | Scale |
|---|---|---|---|---|
| 1 | Split test | ~$26 (one-off) | An ANSWER: is cheap good enough to send? | fixed |
| 2 | **Sending proxies** | **~$66** | Your exit identity on the graded stage | threads |
| 3 | Parse proxies | ~$10 | Loading pages to find forms | page volume |
| 4 | Captcha solves | ~$15 | Passing puzzles on gated sites | **solves**, not sends |
| 5 | Already owned | $0 | GSA licence + tooling | fixed |

**Recurring ~$91/mo · first month ~$117 · $0.0008 per send.**

### How to read it

- **Bucket 2 drives everything.** Buckets 3 and 4 are noise next to it — but omitting
  4 loses leads outright.
- **Bucket 1 exists only to move bucket 2** up or down a grade with evidence.
- Only buckets 2–3 scale with threads; bucket 4 scales with **solves**; the test is fixed.
- Every bucket states its trade-off and its confidence level.

### Marginal value per dollar

| Bucket | Marginal value |
|---|---|
| Sending IPs | high — recovers real, silent losses |
| Captcha solves | high/cheap — unlocks gated sites |
| Parse IPs | low/cheap — volume only |
| Test | **highest per dollar** — it decides bucket 2 |

Cheapest sane ≈ $58/mo (send on dedicated DC once the test proves it). Premium ≈ $115/mo
(send on ISP, parse on dedicated DC).

---

## 11. Minimum budget for a proof-of-concept test

Live: `GET /sizing/minimum-test` (code: `sizing.minimum_budget_test`).

**The reframe:** you do NOT need a "sizable pool". You need a sizable **attempt
count**. Pool size only buys IP diversity and speed.

| Knob | What it controls |
|---|---|
| Attempt count | **correctness** — this is what makes a result significant |
| IP count | budget — only diversity and speed |

Lower threads → same proof, but slower. Raise the detection threshold → fewer
attempts. **Neither requires more IPs.** Buying a big pool for a short test is the
classic overpay — renting 20 IPs to run a 4-hour job.

### Tiers

| Tier | $/mo | Attempts | IPs/arm | Runtime | Proves |
|---|---|---|---|---|---|
| Rock bottom | ~$10 | 272 | 2 | ~28 min | only a ~20pp difference |
| Minimum that means something | ~$18 | 440 | 3 | ~37 min | ~15pp, with A/A |
| **Matches the predicted ~8pp gap** | **~$22** | 1,320 | 4 | ~69 min | the real effect ← pick this |

**Hard floor:** Webshare's ~20-IP order minimum makes the cheap arm ~$6 regardless.
You will use 2–4 of them; the *minimum* is the floor, not the per-IP rate.

### Not in this budget

Leads list ($0, you upload your own) · captcha (~$0–5 at ~90 solves) · GSA licence
(owned) · any parse pool (the test measures **sending** only).

### How to cut further

Drop the A/A arm (~$6) · fewer threads (slower, same proof) · raise the threshold ·
stop the moment significance is reached — a full day is a ceiling, not a target.

> Pacing (~25s/attempt) is a labelled guess; the `~` runtime figures follow from it.

---

## Assumptions and known gaps

- Threads come from a rule-of-thumb helper, **not a measurement**.
- 1:1 IP-per-thread is a floor; real need depends on observed ban rate.
- `import min` cadence and the `send limit type` unit meaning are **unproven**.
- The project message-body key name (`message body`) is inferred, not confirmed.
