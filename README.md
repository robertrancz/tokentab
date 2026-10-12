# TokenTab

Local TUI dashboard for **API token usage**, **subscription seats**, and a **month-end spend forecast**.

It does **not** MITM Cursor, Claude Desktop, or Copilot. Cookie scraping and editor proxies are out of scope.

## What it counts

| Source | How | Cost |
| --- | --- | --- |
| OpenAI API | Org Usage + Costs APIs | Vendor cost when the Costs API returns it |
| Anthropic API | Admin Usage + Cost APIs | Vendor cost (cents → USD) |
| OpenRouter | `GET /api/v1/key` (and optional management `GET /api/v1/credits`) | Snapshot deltas of cumulative usage |
| aider | `~/.aider/analytics.jsonl` or `.aider.chat.history.md` | Activity by default |
| Cursor Pro, Copilot, ChatGPT Plus, Claude Pro | You type the monthly seat price | Fixed line item |

**Billing vs activity:** OpenAI, Anthropic, and OpenRouter are billing authorities. aider logs are **not** added to billed totals while those APIs are enabled (otherwise you would double-count). Set `aider.counts_as_billing = true` in config only if aider is *not* going through those APIs.

Cursor included-model quota is not visible without unofficial scraping. Enter Cursor as a seat; if you point Cursor at your own API keys, that spend shows up on the vendor APIs.

## Setup (uv)

```powershell
uv venv .venv
uv sync
uv run tokentab --demo
```

Demo mode seeds a local DB and never calls vendor APIs.

### Keys (OS keyring; env vars override)

OpenAI and Anthropic usage endpoints need **admin/usage** keys, not ordinary inference keys.

```powershell
uv run tokentab set-key openai
uv run tokentab set-key anthropic
uv run tokentab set-key openrouter
uv run tokentab set-key openrouter-mgmt
```

Environment overrides:

- `TOKENTAB_OPENAI_ADMIN_KEY` or `OPENAI_ADMIN_KEY`
- `TOKENTAB_ANTHROPIC_ADMIN_KEY` or `ANTHROPIC_ADMIN_KEY`
- `TOKENTAB_OPENROUTER_API_KEY` or `OPENROUTER_API_KEY`
- `TOKENTAB_OPENROUTER_MANAGEMENT_KEY`

Then:

```powershell
uv run tokentab          # TUI
uv run tokentab sync
uv run tokentab report --json
```

Config lives in the platform user config dir (`%APPDATA%\tokentab\tokentab\config.toml` on Windows). The SQLite ledger is in the user data dir. `uv run tokentab config-path` prints both.

### Corporate SSL / self-signed proxy

If sync fails with `CERTIFICATE_VERIFY_FAILED` / `self-signed certificate in certificate chain`, your network is likely intercepting HTTPS. Prefer trusting the corporate CA:

```toml
[ssl]
verify = true
ca_bundle = "C:\\path\\to\\corp-root.pem"
```

Or set `TOKENTAB_CA_BUNDLE` / `SSL_CERT_FILE` to that PEM file.

As a last resort (disables TLS verification for vendor calls):

```toml
[ssl]
verify = false
```

Or `$env:TOKENTAB_SSL_VERIFY = "false"`.

### aider logs

Enable aider's analytics log (`--analytics-log` / `AIDER_ANALYTICS_LOG`). Default path: `~/.aider/analytics.jsonl`. Optional chat-history directories go in config:

```toml
[aider]
counts_as_billing = false
analytics_log = ""
history_dirs = ["D:\\Projects\\some-repo"]
```

## Forecast

No ML. Median daily metered burn over the last N complete days (today excluded), times remaining days in the billing cycle, plus seat commitment. A what-if control prices N tokens/day against the bundled catalog (80% input / 20% output).

Vendor-reported USD wins over catalog estimates when both exist.

## Standalone executable (Windows)

Build a one-file `tokentab.exe` that does not need Python or uv installed:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
```

Output: `dist\tokentab.exe`

```powershell
.\dist\tokentab.exe --demo
.\dist\tokentab.exe
.\dist\tokentab.exe sync
.\dist\tokentab.exe report
```

Config and the SQLite DB still live under your user data dir (`tokentab config-path`), not next to the exe.

## Tests

```powershell
uv run pytest
```

## Non-goals

- MITM / cookie scraping / injecting into Cursor, VS Code, Claude Desktop, Copilot
- Claiming Cursor included-quota tokens
- Google Cloud billing, Ollama, or an OpenAI-compatible local proxy (later, opt-in only)
