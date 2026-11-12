# Proxy pools for the split test

Drop the proxies you buy here. One file per arm. The wrapper reads these, keeps the
arms separate, and wires each into its own project.

## Format

One proxy per line. Always accepted:

```
host:port
```

For private / authenticated proxies (which yours will be), use this exact form —
it is GSA's own documented paste format:

```
login:password@host:port
```

Example line:

```
user123:pass456@gate.example.com:8080
```

Notes:
- Lines starting with `#` are ignored, so you can leave comments.
- Blank lines are ignored.
- Both arms MUST be the same country, or geography becomes a second variable.

## Files

| File | Arm | What it is |
|---|---|---|
| `arm-a-cheap.txt` | A | Shared datacenter (the cheap side) |
| `arm-b-clean.txt` | B | Dedicated static ISP (the clean side) |
| `arm-b-prime-aa.txt` | B' | More dedicated ISP, same grade as B — the A/A noise floor |

## What happens next

Save the files and tell me. I will:
1. Parse and de-dupe each arm.
2. Clone the working project twice and diff it so the ONLY difference is the proxy source.
3. Set proxy type and enable "use proxies for sending" on both arms.
4. Turn on `retry failed` and `export failed on`.
5. Match threads, timeout, captcha, message and spin seed across arms.
6. Stratify the URL list and coin-flip rows into `/import/a.csv` and `/import/b.csv`.

Then you press Start.
