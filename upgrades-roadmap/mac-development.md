# Editing from the Mac (GitHub + Vercel) while the bot stays on the PC

**Short answer: yes for the UI, no for the backend.** The UI is one HTML file
with no build step, so it can live on GitHub and deploy itself to Vercel on every
push. The backend cannot move to Vercel, because it does things only a machine
sitting next to the GSA install can do.

## Why the backend must stay on the PC

The API "spine" is not a database app. It:

- reads and writes GSA's `config.ini` and `.prj` files on the local disk,
- starts, stops and restarts `website_contact.exe` as a local process,
- reports the process's PIDs and the live values it wrote.

Vercel gives you a serverless function with no disk and no child process, so it
cannot be the thing that drives GSA. The PC keeps running FastAPI; the Mac only
ever talks to it over the network.

## The split

```
  ┌─────────────┐   git push    ┌──────────┐   auto-deploy   ┌──────────────┐
  │  Mac        │ ────────────► │  GitHub  │ ──────────────► │  Vercel      │
  │  edit ui/   │               │  repo    │                 │  serves ui/  │
  └─────────────┘               └──────────┘                 └──────┬───────┘
                                                                    │ https, fetch
                                                                    ▼
                              ┌───────────────────────────────────────────────┐
                              │  Cloudflare Tunnel  (no open ports, real TLS)  │
                              └──────────────────────┬────────────────────────┘
                                                     ▼
                              ┌───────────────────────────────────────────────┐
                              │  Windows PC                                   │
                              │    FastAPI  ──►  config.ini / .prj            │
                              │             ──►  website_contact.exe          │
                              └───────────────────────────────────────────────┘
```

The only new part is the arrow from Vercel to the tunnel. Everything else already
exists.

## Two config the code now supports for that shape

Both are optional; leave them unset and nothing changes.

| Env var | Set it to | Needed when |
|---|---|---|
| `PANEL_ORIGINS` | `https://your-app.vercel.app` | the Vercel origin must be allowed to call the API (CORS), comma list for several |
| `PANEL_SAMESITE` | `none` | the UI is on a **different site** than the API, so a `Lax` cookie would never be sent |
| `PANEL_COOKIE_DOMAIN` | `.yourdomain.com` | UI and API are **sibling subdomains** (see below) |

`none` **requires HTTPS** — it will not work over a plain-HTTP LAN address.

`credentials:'include'` is already set on every fetch in `ui/index.html`, and
`allow_credentials=True` is set on the CORS block, so the session cookie travels.

## Pick a shape, then one edge for auth/TLS

Ranked. The first is the best fit, because it dodges the third-party-cookie
problem entirely.

### 1. Same domain, path-split (recommended)

- UI: `https://panel.yourdomain.com/` from Vercel
- API: `https://panel.yourdomain.com/api/*` proxied by a Vercel rewrite to the tunnel
- UI is served by FastAPI itself, next to the API.

Same origin → `Lax` still works, no `PANEL_ORIGINS`, no `PANEL_SAMESITE`. The UI
calls the API at `/api/...`, so the backend needs one prefix strip. Most robust.

### 2. Subdomain split

- UI: `https://app.yourdomain.com` (Vercel)
- API: `https://api.yourdomain.com` (tunnel)

Sibling subdomains are the *same site*, so the cookie is still first-party and
still `Lax`-able **as long as** you set `PANEL_COOKIE_DOMAIN=.yourdomain.com`. No
`none` gamble.

### 3. Different sites (e.g. `*.vercel.app` → `*.trycloudflare.com`)

The quickest to stand up and the least robust: the two hosts are different sites,
browser third-party-cookie rules apply, and you must set `PANEL_SAMESITE=none`.

## Cloudflare quick tunnel: a cookie gotcha the code handles

A quick tunnel host like `random-name.trycloudflare.com` is five labels deep, but
Cloudflare's edge certificate covers `*.trycloudflare.com` — the parent. A
host-only cookie on the extra label can be silently dropped. When the Host header
is a `*.trycloudflare.com` or `*.cfargotunnel.com` host, the login therefore
scopes the cookie to the parent domain automatically. No config needed; a named
tunnel on your own domain does not hit this.

## Editing the UI from the Mac, without deploying

`dev-server.py` runs on the PC and serves `ui/` with **live reload** — stdlib
only, no deps:

```powershell
python dev-server.py            # http://localhost:5500
```

Edit `ui/index.html` in your editor; the browser reloads on save. Send
`X-Panel-Mode: backend` from the UI to make the dev server reverse-proxy to the
real panel on `:8000` and exercise real settings.

That means the loop on the Mac is: edit → push → Vercel preview → merge, and the
fast local loop is still one command.

## The honest list of what this does NOT solve

- **Backend code still needs the PC to test.** There is no local equivalent of
  "shell out to website_contact.exe". Backend changes ship to the PC, not Vercel.
- **Two deployments means two admin surfaces.** The tunnel is a second thing to
  keep alive; if it drops, the UI loads and its calls fail.
- **Streaming endpoints** (log tails) can buffer badly through a Vercel rewrite.
  Test them before trusting them.
- **`_work/` (the 2.4 GB GSA unpacked payload) is not in git** and never will be.
  It is local to the PC by design.
- A cloud service could not drive GSA even if you paid it to, so "Vercel hosting
  the whole thing" is not a future option — only the UI half.

## Trigger to revisit

Move the backend off the PC only if GSA itself gets a headless/remote mode. Until
then this split is the shape.
