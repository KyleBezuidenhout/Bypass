# Remote access — letting clients reach this PC safely

## What is already built

The panel now has a **single-password lock**:

- Set `PANEL_PASSWORD` to switch it on. Unset and it behaves exactly as before (open).
- One shared password, no user accounts — matches the brief.
- Signed `HttpOnly` session cookie, `SameSite=Lax`. No server-side session store.
- `Authorization: Basic` also accepted, for `curl` and scripts.
- Per-IP brute-force limiting: 10 wrong tries in 5 minutes → 429.
- Rotating the password invalidates all existing sessions automatically.

Easiest launch (generates and stores the password, binds the LAN):

```powershell
.\run-panel.ps1
```

Then from another machine on the network: `http://<lan-ip>:8000`.

---

## The one thing the password does NOT give you: encryption

The lock stops people **in**. It does not stop the wire being read. Over plain
`http://` the password and the session cookie travel in the clear. On a home LAN
that is tolerable; over the internet it is not.

So pick one of these. Ranked by fit for your situation:

### Option 1 — Cloudflare Tunnel (recommended)

Outbound-only connection, so **no port-forwarding and no opening the firewall**.
Your PC dials out to Cloudflare; clients reach a hostname; TLS is terminated for
you with a real certificate.

- Good fit because the whole stack already runs on Cloudflare (R2), and it survives
  CGNAT / changing IPs / restarts.
- Put `Cloudflare Access` in front as well and you get SSO or a one-time-PIN by email
  *on top of* the panel password — two locks, and the second one costs nothing.
- Everything arrives with `X-Forwarded-Proto: https`, which the panel already reads,
  so the cookie is set `Secure` automatically.

Shape: `cloudflared tunnel --url http://localhost:8000` for a quick try, or a named
tunnel with a DNS record on your domain for the real thing.

### Option 2 — Vercel in front of the tunnel (or a direct proxy)

Because the frontend is on Vercel, you can keep one client-facing address and proxy
through to the tunnel. Two sub-choices:

- **Vercel rewrite → tunnel hostname.** Simplest. Clientele hit your existing domain.
  Watch the request-body and timeout limits for the streaming endpoints.
- **Vercel as a thin proxy function.** More control, more moving parts, adds latency
  and a second place to get auth wrong.

Rule: pick ONE edge for auth and TLS, not both. Two overlapping locks is where the
confusing bugs live.

### Option 3 — Tailscale

Private mesh VPN. Clients install Tailscale and reach the machine directly. Strongest
privacy (nothing is public at all), but it asks each client to install software.
Good if "clients" is really "me and a few colleagues".

### Option 4 — Port forward + TLS

Open one port on your router and forward it. Needs a static IP or DDNS, and manual
certificates (`caddy` can automate them). The most moving parts and the most exposed.

---

## Recommendation

**Cloudflare Tunnel + Access, with the panel password left ON as the second lock.**

- No ports opened, no static IP needed.
- Real TLS on a hostname you control.
- Access can be scoped later (email allow-list) without touching code.
- If the tunnel dies, the panel is simply unreachable — not exposed.

Keep the password ON even with Access. It is the difference between "only invited
people" and "only invited people who also know the secret".

---

## Exposure checklist

- [ ] `PANEL_PASSWORD` set (the panel never runs open on a public interface).
- [ ] Reached over `https://` — confirm the cookie has the `Secure` flag in devtools.
- [ ] `X-Forwarded-Proto` header reaches the app (so cookies are marked Secure).
- [ ] If using Access/a proxy: the real client IP is forwarded, or rate-limiting
      lumps everyone under the proxy's IP.
- [ ] `PANEL_SESSION_HOURS` set to taste (default 14 days; lower it if the panel is
      more sensitive than convenient).
- [ ] `PANEL_SECRET` set explicitly if you want sessions to survive a password change.
- [ ] The panel controls a **local process** — anyone inside can start/stop the app.
      That is the real blast radius, not reading settings.

## Known limits (honest)

- Single shared password: no per-client attribution, no individual revocation.
  Rotating the password logs everyone out at once.
- No CSRF token. `SameSite=Lax` covers ordinary POSTs; a determined cross-site
  form post is not blocked.
- Rate limiting is per-process and in memory, so it resets on restart.
- Sessions cannot be revoked early other than by rotating the password or the secret.
