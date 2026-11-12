# Open questions

Things still undecided. Move an item to the decisions log in the [README](README.md)
once it is settled.

---

## 1. TinyFish account farm — how many accounts, and how to avoid flags

**Status:** open. Analysis exists in `gsa_wrap/sizing.py` (`farm_scaling`,
`farm_without_blocks`), surfaced in the panel, but no number is committed.

**What is already established:**

- The daily allowance is **per account** (1,000 Fetch URLs/day, resets 00:00 UTC), so
  N accounts genuinely multiply free capacity. This was read from their docs, not
  assumed.
- Auth is a plain `X-API-Key` header, with **no IP binding documented**. So multiple
  accounts from one IP is the expected shape — a different IP is *not* required.
- The separation that matters is the **email address**, not the IP.
- The per-minute limit is documented as per **account**, not per key.

**What is NOT established:**

- How many accounts are actually worth running. Depends entirely on where parsing
  happens, which is [decided](parsing-strategy.md) to stay local *for now*.
- Whether their per-minute limiter behaves strictly per key under a real burst. Docs
  suggest yes; only a burst test settles it.
- Whether "multiple accounts is fine" is tolerated or merely not yet enforced. Their
  start-up programme fine print reserves the right to revoke for "abuse, including
  multiple accounts".

**Decision needed when:** parsing is outsourced, or the local parse rate is measured
low enough to trigger a switch.

**Blocked on:** the Form-discovery measurement in [parsing-strategy.md](parsing-strategy.md).

---

## 2. Which paid proxy provider, and at what tier mix

**Status:** open. Per-IP pricing for four vendors is in the panel; no vendor chosen.
Options and their real deliverability loss are modelled in
`gsa_wrap/sizing.py` (`cheap_proxy_tradeoff`) and written up in
`import-schedule-and-proxies.md` §6.

**Known trade-off:** dedicated static ISP at ~$2/IP/month × 55 IPs is the sending
cost. Shared DC is ~1/4 the price but carries flagged IPs. A two-tier split (cheap DC
for parsing, residential for sending) has been costed but not committed.

**Where it actually stands:** the loss is **not** a blanket downgrade — it lands only
on hardened sites (~15%), and a *dedicated* datacenter step-down keeps ~92% of the
reach for ~half the price. Breakeven vs the safe pool is ~$0.003 per recovered send.

**The measurement to make first:** turn on `retry failed` + `export failed on` so
send failures are visible at all (live config currently drops them silently), then
run the stratified test in `import-schedule-and-proxies.md` §7. **Note:** an earlier
"500 vs 500" figure is underpowered — detecting a 10pp pooled gap needs ~222 per arm
pooled, ~1,476 total once the A/A noise floor and canary are included (~1 day at
5,000/day). Do this before spending, not after.

**Decision needed when:** the sending stage is next in line for work.

**Blocked on:** nothing — this could be decided independently.

---

## 3. Measured form-discovery rate on the real target list

**Status:** open. Currently a 60% assumption labelled as such everywhere.

**Why it matters:** parse volume scales inversely with it, so it drives the account
count in [capacity-10k.md](capacity-10k.md) linearly. It is also the trigger for
revisiting the parsing decision.

**How to settle:** run ~200 real target sites, count how many expose a usable contact
form. Cheap, and it unblocks items 1 and the parsing revisit at the same time.
