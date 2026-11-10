"""Detect CAPTCHA widgets and their sitekeys on the current page.

Runs JS in the page via SeleniumBase's CDP `evaluate`. Returns a list of dicts:
    {"kind": "recaptcha_v2|recaptcha_v3|turnstile|hcaptcha", "sitekey": "...", "cb": "callbackName"}
"""
import json

_DETECT_JS = r"""
(() => {
  const out = [];
  const push = (kind, sitekey, cb) => { if (sitekey) out.push({kind, sitekey, cb: cb || null}); };

  document.querySelectorAll('.g-recaptcha, .g-recaptcha-v2').forEach(el =>
    push('recaptcha_v2', el.getAttribute('data-sitekey'), el.getAttribute('data-callback')));

  document.querySelectorAll('.cf-turnstile').forEach(el =>
    push('turnstile', el.getAttribute('data-sitekey'), el.getAttribute('data-callback')));

  document.querySelectorAll('.h-captcha').forEach(el =>
    push('hcaptcha', el.getAttribute('data-sitekey'), el.getAttribute('data-callback')));

  if (out.length === 0) {
    const fr = document.querySelector('iframe[src*="/recaptcha/"]');
    if (fr) { const m = fr.src.match(/[?&]k=([^&]+)/); if (m) push('recaptcha_v2', decodeURIComponent(m[1]), null); }
    const ft = document.querySelector('iframe[src*="challenges.cloudflare.com"]');
    if (ft) { const m = ft.src.match(/[?&]k=([^&]+)/); if (m) push('turnstile', decodeURIComponent(m[1]), null); }
    const fh = document.querySelector('iframe[src*="hcaptcha.com"]');
    if (fh) { const m = fh.src.match(/[?&]sitekey=([^&]+)/); if (m) push('hcaptcha', decodeURIComponent(m[1]), null); }
  }

  // de-dup by kind+sitekey
  const seen = new Set(); const dedup = [];
  for (const c of out) { const k = c.kind + '|' + c.sitekey; if (!seen.has(k)) { seen.add(k); dedup.push(c); } }
  return JSON.stringify(dedup);
})()
"""

_INJECT_JS = r"""
((kind, token, cb) => {
  const sel = {
    recaptcha_v2: 'textarea[name="g-recaptcha-response"], #g-recaptcha-response',
    recaptcha_v3: 'textarea[name="g-recaptcha-response"], #g-recaptcha-response',
    turnstile: 'input[name="cf-turnstile-response"], textarea[name="cf-turnstile-response"]',
    hcaptcha: 'textarea[name="h-captcha-response"], textarea[name="g-recaptcha-response"]',
  }[kind] || '';

  document.querySelectorAll(sel).forEach(el => {
    el.value = token;
    el.innerHTML = token;
    el.dispatchEvent(new Event('change', {bubbles: true}));
  });

  if (cb && typeof window[cb] === 'function') { try { window[cb](token); return 'callback'; } catch (e) {} }

  // reCAPTCHA: fire the registered widget callback directly
  try {
    if (kind.startsWith('recaptcha') && typeof ___grecaptcha_cfg !== 'undefined') {
      const clients = ___grecaptcha_cfg.clients || {};
      for (const i in clients) for (const j in clients[i]) {
        const p = clients[i][j];
        if (p && typeof p.callback === 'function') { p.callback(token); return 'gre-callback'; }
      }
    }
  } catch (e) {}
  return 'value-set';
})
"""


def detect(sb):
    raw = sb.evaluate(_DETECT_JS)
    try:
        return json.loads(raw) if raw else []
    except Exception:
        return []


def inject(sb, kind, token, cb=None):
    call = "({js})({kind}, {token}, {cb})".format(
        js=_INJECT_JS,
        kind=json.dumps(kind),
        token=json.dumps(token),
        cb=json.dumps(cb),
    )
    return sb.evaluate(call)
