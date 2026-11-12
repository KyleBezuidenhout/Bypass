# Capacity at 10,000 forms/day — 2026-11-12

> Figures generated from `gsa_wrap.sizing.capacity_10k(10000, 60)`. Re-run the
> command in the [README](README.md) to refresh.

## The one thing to get straight first

**10,000 forms *submitted* per day is a SENDING number.** Parsing does not submit.
Conflating the two is the single easiest way to size this wrong.

Once the lead list is supplied, 10k submits/day maps to roughly:

| Quantity | Value |
|---|---|
| Forms submitted / day | 10,000 |
| Sites that must be parsed / day (at 60% find-rate) | ~16,700 |
| Sending threads | 55 |
| Clean sending IPs needed | ~55 |
| Captcha solves / day (assumed 20% of submits hit one) | ~2,000 |
| Captcha cost | ~$1.28/day (~$38/month) |

## Parsing: accounts needed

Two **independent** constraints, and they must not be blended:

- **Daily allowance** — 1,000 URLs/day **per account**. At 16,700 URLs/day this binds
  at **17 accounts**. This is the number for *recurring daily* volume.
- **Speed** — 150 URLs/min **per account**. Speed alone would clear 16,700 URLs with
  **2 accounts in ~56 minutes**.

So:

| Scenario | Accounts | Why |
|---|---|---|
| **Recurring daily** 10k submits | **~17** | The daily allowance binds. 17 × 1,000 = 17,000 URLs/day. |
| **One-off list** | **~2** | A one-off can spread across days, so only speed binds. |

> **Trap to avoid:** two accounts can *push* ~18,000 URLs/hour, but they still only
> *own* 2,000 URLs/day. High throughput does not equal high daily allowance.

At 17 accounts the day's parse clears in ~6.5 minutes of actual fetching.

Note the found-rate assumption matters linearly here. At a 30% find-rate the parse
volume for 10k submits doubles to ~33,000 URLs/day, and the allowance answer doubles
to ~34 accounts.

## Sending: the actual cost centre

| Tier | Pool entries | Distinct IPs/day |
|---|---|---|
| Dedicated DC / ISP | 55 | 20 |
| Shared DC | 55 | 8 |
| Rotating residential | 55 | 1 |

Sending is where money goes, and residential grade on the sending stage is the
non-negotiable part. See the panel's IP-grade section for per-IP pricing.

## What is NOT covered here

- **Found-rate on the real list is unmeasured.** 60% is a labelled assumption.
- **Duplicate/root-domain handling** — `only root domains=0` on hand-curated leads is
  a live duplicate-submission risk and is tracked separately.
- **Bounce/retry volume** adding to effective sends.

## Revisit trigger

If measured found-rate lands below ~40%, re-run with the real number before buying
proxies, because parse accounts scale inversely with it.
