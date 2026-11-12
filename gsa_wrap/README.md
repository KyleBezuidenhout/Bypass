# GSA Website Contact — local wrapper

A modern control panel over the licensed **GSA Website Contact v6.42** desktop app.
Their app keeps running and stays licensed; this gives it a typed settings model,
a safe writer, and a natural-language front end.

```
ui/index.html          single-file control panel (no build step)
gsa_wrap/schema.py     typed model of every setting + help text  (the contract)
gsa_wrap/config_io.py  atomic, verified read/write of config.ini
gsa_wrap/process.py    launch / stop / restart + restart-needed detection
gsa_wrap/nl.py         natural language -> settings, and field explanations
gsa_wrap/api.py        FastAPI service
gsa_wrap/cli.py        same thing from the terminal
gsa_wrap/ui_enum.py    Win32 control enumerator (for dialog-only settings)
tests/                 29 tests
```

## Run

```bash
pip install -r requirements-gsawrap.txt
python -m uvicorn gsa_wrap.api:app --port 8787
# open http://127.0.0.1:8787
```

Or headless:

```bash
python -m gsa_wrap.cli health
python -m gsa_wrap.cli schema --group performance
python -m gsa_wrap.cli plan  "misc::max threads=25"
python -m gsa_wrap.cli apply "misc::max threads=25"
```

## Why it is safe

- **Atomic writes** — temp file + `os.replace`; a crash never leaves a half file.
- **Backup** — `config.ini.bak` written once per apply.
- **Verified** — every write is re-read from disk; anything that didn't stick is
  reported as `bounced` rather than silently claimed as done.
- **Plan before apply** — `/settings/plan` and `/nl/plan` are read-only; you see
  the exact diff first.
- **Byte-faithful** — line endings (mixed CRLF/LF included), key order and
  unknown future keys are all preserved.
- **No clobbering** — verified that the running app does not rewrite
  `config.ini` while idle, on exit, or on relaunch.

## Natural language (optional LLM)

Works with no key using a deterministic rules engine. To use a real model, set
any OpenAI-compatible endpoint:

```bash
# OpenAI
set GSA_LLM_KEY=sk-...
set GSA_LLM_MODEL=gpt-4o-mini

# local Ollama (no key needed)
set GSA_LLM_BASE=http://localhost:11434/v1
set GSA_LLM_MODEL=llama3.1
```

The schema is handed to the model as the contract, so it can only pick fields
that exist. Anything hallucinated is dropped and reported in `unknown`.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | control panel |
| GET | `/health` | app + config status |
| GET | `/schema` | every field with help text |
| GET | `/settings` | current values |
| POST | `/settings/plan` | dry-run diff |
| POST | `/settings/apply` | write, verify, report bounces |
| POST | `/nl/plan` | sentence → diff (read-only unless `apply: true`) |
| GET | `/nl/explain?ref=...` | what a setting does |
| POST | `/app/start\|stop\|restart` | process control |

## License

The app itself is untouched. Back up `%APPDATA%\GSA_WebsiteContact\projects\qklrr.ups`
and `qklrr.ups.rsa` together — those two are the activation.
