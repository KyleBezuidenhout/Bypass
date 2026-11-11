# Task prompt — reverse-engineer the GSA Website Contact form-workflow (captcha EXCLUDED)

You have **no prior context**. You have access to the files in this folder
(`/Users/kylebezuidenhout/Desktop/Contact Form/`). Work from the binary only —
**cite string/evidence for every claim. Do not invent behaviour.**

## What the product is
`website_contact.exe` is the installer for **GSA Website Contact v6.42** (by "GSA
Software"). It is a 32-bit Windows Delphi app (Inno Setup 6.4.3). Its job: take a
list of website URLs, **navigate to each site, find the contact form, fill it in,
and submit an outreach message**, then record a per-URL status.

## Goal of THIS task
Produce a **precise, evidence-backed map of the app's form-navigation and
form-filling workflow** — end to end — and a **build-vs-buy gap analysis**.

**CAPTCHA is OUT OF SCOPE for this task** (it is handled by a separate library).
Ignore reCAPTCHA/hCaptcha/Turnstile specifics except as a passing note.

We are assessing whether to (a) just run this Windows app, or (b) rebuild an
equivalent pipeline natively in Python/FastAPI, and later offer it as
infrastructure (API + MCP + optional proxies) to businesses that run cold outbound.

## How to get at the real code
The `.exe` is an **installer**, not the app. Steps that work:

1. `ext/[0]` (and `extracted/[0]`) is the packed app payload. `innoextract` 1.10
   fails on setup data 6.4.3; `7zz` lists but won't decompress it.
2. `[0]` starts with magic bytes `zlb\x1a` = a **raw LZMA2** stream. Decompress it:

```python
import lzma
data = open("ext/[0]", "rb").read()          # note: skip 5-byte zlb header
d = lzma.LZMADecompressor(format=lzma.FORMAT_RAW,
                          filters=[{"id": lzma.FILTER_LZMA2, "dict_size": 1 << 24}])
open("payload.exe", "wb").write(d.decompress(data[5:]))   # -> 49.8 MB PE32
```

3. `strings -a payload.exe | grep -i <term>` is the main mining tool. The app
   embeds a large in-binary **changelog** — that changelog is the richest source
   of "what it can do". Also grep for: `javascript simulation`, `emulation`,
   `ajax`, `contact form`, `comment form`, `sublink`, `redirect`, `selector`,
   `type=text`, `wpforms`, `jotform`, `User-Agent`, status words.

## Key things already established (verify, then build on)
- `payload.exe` imports **winhttp / netapi32 / ws2_32 / comctl32 / MFC42u / openssl**
  and **no browser engine** (no CEF/Chromium/WebKit). Conclusion to test: the app
  is an **HTTP client + a hand-written JavaScript/AJAX simulator**, NOT a headless
  browser. Confirm or refute from imports + changelog strings.
- The changelog shows the app relies on **per-plugin templates** (WordPress,
  JotForm, UABB, NitroForm, wpforms, everest_forms, ASP.NET) to compensate for not
  having a real DOM.

## What to deliver (in this order)
1. **Stage-by-stage workflow map**, e.g.: URL intake → redirect resolution → site
   crawl / sublink discovery → form location → form classification → field mapping
   (which input gets name/email/message/subject) → fill → (captcha: skip) →
   submit → post-submit / success detection → status + result writing.
   For each stage: **mechanism**, **evidence strings**, and **known failure modes**.
2. **Field-mapping heuristics**: how it decides which field is email vs message vs
   name (grep for label/name matching, macros, hidden-field and `display:none`
   handling).
3. **Where it structurally breaks**: SPA/AJAX/bespoke forms, iframes, JS walls —
   and the exact strings that show it *trying and failing* (e.g. a
   "javascript protected" status).
4. **Build-vs-buy gap list**: stage by stage, is a native Python rebuild trivial,
   moderate, or hard? Where would a *real-browser* agent beat the emulator?
5. **Open questions** where evidence is thin — say what's unknown.

## Rules
- **No invention.** Every functional claim must point to a string, an import, or a
  concrete artefact. If unsure, say so.
- Captcha excluded (mention only where it interlocks).
- Assume the reader is a senior engineer; be concise and specific.
- Do not run the app (no Wine needed for this task) — this is static analysis.
