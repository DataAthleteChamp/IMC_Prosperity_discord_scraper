<!-- markdownlint-disable MD033 MD041 -->
<div align="center">

# prosperity-scraper

**Open-source Discord server scraper for the [IMC Prosperity](https://prosperity.imc.com/) trading competition.**
Export every readable channel to JSONL for offline search and AI preprocessing.

[![CI](https://github.com/DataAthleteChamp/IMC_Prosperity_discord_scraper/actions/workflows/ci.yml/badge.svg)](https://github.com/DataAthleteChamp/IMC_Prosperity_discord_scraper/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Code style: ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

</div>

---

> ⚠️ **Terms-of-Service warning.** Using this tool with a **user token** (the
> `--auth user` backend) violates [Discord's Terms of Service](https://discord.com/terms)
> and may result in permanent termination of your Discord account. The authors
> assume no responsibility for actions Discord takes against accounts that use
> this software. **Prefer the official bot path** (`--auth bot`) whenever possible
> — see [`docs/bot-invite.md`](./docs/bot-invite.md) for how to ask a server
> admin to invite a read-only bot.

---

## Table of contents

- [Why this exists](#why-this-exists)
- [Features](#features)
- [How it works](#how-it-works)
- [Quickstart](#quickstart)
- [CLI reference](#cli-reference)
- [Output layout](#output-layout)
- [Alternatives & prior art](#alternatives--prior-art)
- [Roadmap](#roadmap)
- [Safety & privacy](#safety--privacy)
- [Contributing](#contributing)
- [License](#license)

## Why this exists

The [IMC Prosperity](https://prosperity.imc.com/) trading competition runs a
community Discord server with thousands of messages spanning strategy
discussions, algo bugs, and round-specific intel. Most of this knowledge is
ephemeral — there's no built-in search across years of history, and you can't
feed raw Discord into an LLM easily.

`prosperity-scraper` is a small, well-documented tool to export what you can
see in the UI into a clean JSONL archive. From there you can grep it,
tokenise it, embed it, or pipe it into whatever AI preprocessing pipeline you
prefer.

## Features

| | |
|---|---|
| 🔐 **Two auth backends** | `--auth bot` (ToS-clean, needs admin invite) or `--auth user` (ToS-risk, no admin needed). |
| 🧵 **Full server traversal** | Text channels, announcement channels, forum channels, and both active and archived public/private threads. |
| ⏱️ **Time-range filtering** | `--since` / `--until` ISO-8601; converts to Discord snowflake bounds. |
| 💾 **JSONL output** | One file per channel, ready for LLM pipelines. Raw Discord payload preserved per record. |
| 🔁 **Resumable** | Per-channel snowflake watermarks in `_cursors.json`; Ctrl-C safe. |
| 🐢 **Stealth pacing** | 5 req/s token bucket + randomised jitter + proper `Retry-After` / 429 handling. |
| 🧹 **Preprocessing hook** | `preprocess` subcommand resolves mentions and strips markdown into a `content_clean` field. |
| ✅ **Tested** | 24 unit tests, synthetic fixtures only — CI never hits real Discord. |

## How it works

```
┌──────────────────────────────────────────────────────────┐
│                   prosperity-scraper CLI                 │
│                                                          │
│   --auth {bot|user}  --since/--until  --channels ...     │
│         │                                                │
│         ▼                                                │
│   AuthBackend ──► BotAuth  ("Bot <token>")               │
│                └─ UserAuth (raw token, ToS-risk)         │
│         │                                                │
│         ▼                                                │
│   DiscordClient (httpx async, rate-limited)              │
│         │                                                │
│         ▼                                                │
│   discover_channels  → text / announce / forum + threads │
│         │                                                │
│         ▼                                                │
│   paginator  → snowflake-cursor, newest→oldest           │
│         │                                                │
│         ▼                                                │
│   normalize  → pydantic Message (+ raw preserved)        │
│         │                                                │
│         ▼                                                │
│   JsonlWriter  + CursorStore (resumable)                 │
└──────────────────────────────────────────────────────────┘
```

Detailed write-up in [`docs/architecture.md`](./docs/architecture.md).

## Quickstart

### 1. Install

```bash
git clone https://github.com/DataAthleteChamp/IMC_Prosperity_discord_scraper.git
cd IMC_Prosperity_discord_scraper
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,user]"           # or .[dev,bot] for the bot-token path
```

### 2. Configure

```bash
cp .env.example .env
# fill in:
#   DISCORD_USER_TOKEN=<see docs/faq.md for how to extract>
#   DISCORD_GUILD_ID=<right-click server → Copy Server ID, with Developer Mode on>
```

### 3. Discover channels (dry run — no data downloaded)

```bash
prosperity-scraper scrape --auth user --dry-run
```

### 4. Backfill

```bash
# everything
prosperity-scraper scrape --auth user

# last 24 hours
prosperity-scraper scrape --auth user --since "$(date -u -v-24H +%Y-%m-%dT%H:%M:%SZ)"

# one specific channel, a specific window
prosperity-scraper scrape --auth user \
    --channels 1476867343068958781 \
    --since 2025-01-01T00:00:00Z --until 2025-04-30T00:00:00Z
```

### 5. Preprocess for LLM input (optional)

```bash
prosperity-scraper preprocess ./data/1476867343068958781.jsonl \
                              ./data/1476867343068958781.clean.jsonl
```

## CLI reference

```console
$ prosperity-scraper scrape --help
Usage: prosperity-scraper scrape [OPTIONS]

  Backfill messages from the configured guild.

Options:
  --auth [bot|user]        Auth backend: 'bot' (ToS-clean) or 'user' (ToS-risk).  [required]
  --guild-id TEXT          Override DISCORD_GUILD_ID from env.
  --since TEXT             Lower bound (ISO-8601, inclusive).
  --until TEXT             Upper bound (ISO-8601, inclusive).
  --channels TEXT          Comma-separated channel/thread IDs to include.
  --exclude-channels TEXT  Comma-separated channel/thread IDs to skip.
  --output-dir PATH
  --rate-limit FLOAT       Average requests per second (default: 5).
  --dry-run                Discover only, do not fetch messages.
  -v, --verbose
  --help                   Show this message and exit.
```

## Output layout

```
data/
├── _channels.json          # discovered channels (ids, names, types)
├── _cursors.json           # resumable per-channel watermarks
└── <channel_id>.jsonl      # one file per channel, one message per line
```

An annotated sample record lives in
[`examples/sample_output.jsonl`](./examples/sample_output.jsonl) (synthetic).
Full schema: [`docs/architecture.md`](./docs/architecture.md#message-jsonl-record).

## Alternatives & prior art

| Tool | Language | Notes |
|---|---|---|
| [Tyrrrz/DiscordChatExporter](https://github.com/Tyrrrz/DiscordChatExporter) | C# | The best-known exporter. GUI + CLI. Produces HTML/JSON/CSV/TXT. Larger surface; not Python-native. |
| [dolfies/discord.py-self](https://github.com/dolfies/discord.py-self) | Python | User-account SDK — this project could be rewritten on top of it but chooses to hit REST directly for transparency. |
| [aiko-chan-ai/discord.js-selfbot-v13](https://github.com/aiko-chan-ai/discord.js-selfbot-v13) | Node.js | Node equivalent of discord.py-self. |
| [mautrix/discord](https://github.com/mautrix/discord) | Go | Matrix bridge; reference for traffic-shape work. |

See [`docs/architecture.md`](./docs/architecture.md) for why this project
chose a direct-REST approach over the alternatives above.

## Roadmap

- [ ] SQLite backend as an alternative to JSONL (with per-message upserts).
- [ ] `--auth browser` — Playwright-based fallback that drives real Discord web.
- [ ] Attachment download (opt-in, `--download-attachments`).
- [ ] Live-tailing mode via the Gateway WebSocket.
- [ ] `--anonymize` flag for publishing derived datasets responsibly.
- [ ] Richer preprocessing: per-user rolling context windows for LLM fine-tuning.

Have a concrete use case? Open an issue.

## Safety & privacy

- Treat your user token as **equivalent to your Discord password**.
- `.env` is in `.gitignore`; pre-commit runs
  [`gitleaks`](https://github.com/gitleaks/gitleaks) to block accidental
  commits.
- Scraped messages contain other users' personal data. **Do not redistribute
  scraped data.** If you publish derived work, anonymise author IDs and
  usernames first.
- This repository ships the tool, never datasets. Tests use synthetic
  fixtures.
- Security disclosures: see [`SECURITY.md`](./SECURITY.md).

## Contributing

See [`CONTRIBUTING.md`](./CONTRIBUTING.md) and our
[Code of Conduct](./CODE_OF_CONDUCT.md). Pull requests for documentation,
tests, and new features are all welcome — but features whose only purpose
is to evade Discord detection are out of scope and will be closed.

## License

[MIT](./LICENSE) © 2026 Jakub Piotrowski and contributors.
