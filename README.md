<!-- markdownlint-disable MD033 MD041 -->
<div align="center">

# discord-channel-scraper

**Open-source Discord scraper for archiving selected channels across multiple servers.**
Point it at any number of servers, pick the channels you care about by name or ID,
and export them to JSONL for offline search and AI preprocessing.

[![CI](https://github.com/DataAthleteChamp/discord-channel-scraper/actions/workflows/ci.yml/badge.svg)](https://github.com/DataAthleteChamp/discord-channel-scraper/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Code style: ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

</div>

---

> ⚠️ **Terms-of-Service warning.** Using this tool with a **user token** (the
> `auth = "user"` backend) violates [Discord's Terms of Service](https://discord.com/terms)
> and may result in permanent termination of your Discord account. The authors
> assume no responsibility for actions Discord takes against accounts that use
> this software. **Prefer the official bot path** (`auth = "bot"`) whenever possible
> — see [`docs/bot-invite.md`](./docs/bot-invite.md) for how to ask a server
> admin to invite a read-only bot.

---

## Table of contents

- [Why this exists](#why-this-exists)
- [Features](#features)
- [How it works](#how-it-works)
- [Quickstart](#quickstart)
- [Configuring targets](#configuring-targets)
- [CLI reference](#cli-reference)
- [Output layout](#output-layout)
- [Alternatives & prior art](#alternatives--prior-art)
- [Roadmap](#roadmap)
- [Safety & privacy](#safety--privacy)
- [Contributing](#contributing)
- [License](#license)

## Why this exists

Community Discord servers — trading competitions, hackathons, open-source
projects, research groups — accumulate thousands of messages of genuinely
useful knowledge. Most of it is ephemeral: there's no search across years of
history, and you can't feed raw Discord into an LLM easily.

`discord-channel-scraper` exports what you can already see in the UI into a
clean JSONL archive. It is built around **targets**: one config file describes
several servers, the channels to take from each, and where each one's output
goes. One command scrapes them all.

## Features

| | |
|---|---|
| 🌐 **Multi-server** | One `scraper.toml`, many servers. `scrape --all` walks each in turn; `--target NAME` runs just one. |
| 📁 **Per-target output paths** | Every target writes to its own directory — absolute or relative, `~` and `$VARS` expanded. |
| 🏷️ **Channels by name or ID** | `channels = ["general", "round-5"]` — no snowflake hunting. Naming a forum/text channel also pulls its threads. |
| 🔐 **Two auth backends** | `bot` (ToS-clean, needs admin invite) or `user` (ToS-risk, no admin needed). One account can serve every target, or each target can use its own via `token_env`. |
| 🧵 **Full server traversal** | Text channels, announcement channels, forum channels, and both active and archived public/private threads. |
| ⏱️ **Time-range filtering** | `--since` / `--until` ISO-8601, globally or per target; converts to Discord snowflake bounds. |
| 💾 **JSONL output** | One file per channel, ready for LLM pipelines. Raw Discord payload preserved per record. |
| 🔁 **Resumable** | Per-channel snowflake watermarks in `_cursors.json`; Ctrl-C safe; one directory per target so servers never clobber each other. |
| 🐢 **Stealth pacing** | 5 req/s token bucket + randomised jitter + proper `Retry-After` / 429 handling. Targets run sequentially, never in parallel bursts. |
| 🧹 **Preprocessing hook** | `preprocess` subcommand resolves mentions and strips markdown into a `content_clean` field. |
| ✅ **Tested** | 83 unit + integration tests against a mocked Discord API — CI never hits the real one. |

## How it works

```
┌──────────────────────────────────────────────────────────┐
│              discord-channel-scraper CLI                 │
│                                                          │
│   scraper.toml ──► [[targets]]  guild + channels + path  │
│         │                                                │
│         ▼                                                │
│   for each target, sequentially:                         │
│         │                                                │
│         ├─ AuthBackend ──► BotAuth  ("Bot <token>")      │
│         │              └── UserAuth (raw token, ToS-risk)│
│         │                                                │
│         ▼                                                │
│   DiscordClient (httpx async, rate-limited)              │
│         │                                                │
│         ▼                                                │
│   discover_channels  → text / announce / forum + threads │
│         │                                                │
│         ▼                                                │
│   select_channels    → allow/deny by name or ID          │
│         │                                                │
│         ▼                                                │
│   paginator  → snowflake-cursor, newest→oldest           │
│         │                                                │
│         ▼                                                │
│   normalize  → pydantic Message (+ raw preserved)        │
│         │                                                │
│         ▼                                                │
│   JsonlWriter + CursorStore  → <target>/output_dir/      │
└──────────────────────────────────────────────────────────┘
```

Detailed write-up in [`docs/architecture.md`](./docs/architecture.md).

## Quickstart

### 1. Install

```bash
git clone https://github.com/DataAthleteChamp/discord-channel-scraper.git
cd discord-channel-scraper
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. Add your token

```bash
cp .env.example .env
# fill in ONE of:
#   DISCORD_USER_TOKEN=<see docs/faq.md for how to extract it>
#   DISCORD_BOT_TOKEN=<see docs/bot-invite.md>
```

Tokens only ever live in `.env` / the environment. The targets config holds no
secrets, so it's safe to share.

### 3. Describe what to scrape

```bash
discord-channel-scraper init      # writes scraper.toml
```

Then edit it — one `[[targets]]` block per server:

```toml
[defaults]
auth = "user"
rate_limit = 5

[[targets]]
name = "comp-2026"
guild_id = "111111111111111111"
output_dir = "/Users/me/archives/comp-2026"
channels = ["announcements", "general", "round-5"]

[[targets]]
name = "research-server"
guild_id = "222222222222222222"
output_dir = "/Users/me/archives/research"
exclude_channels = ["off-topic", "bot-spam"]
```

Don't know the channel names or IDs yet? Leave `channels` out, run a dry run,
and pick from the table it prints.

### 4. Dry run (no messages downloaded)

```bash
discord-channel-scraper targets              # what's configured
discord-channel-scraper scrape --all --dry-run
```

### 5. Backfill

```bash
# every enabled target, each into its own output_dir
discord-channel-scraper scrape --all

# just one server
discord-channel-scraper scrape --target comp-2026

# two servers, last 24 hours only
discord-channel-scraper scrape -t comp-2026 -t research-server \
    --since "$(date -u -v-24H +%Y-%m-%dT%H:%M:%SZ)"
```

Re-run the same command any time — cursors make it resume rather than
re-download.

### 6. Preprocess for LLM input (optional)

```bash
discord-channel-scraper preprocess \
    /Users/me/archives/comp-2026/333333333333333333.jsonl \
    /Users/me/archives/comp-2026/333333333333333333.clean.jsonl
```

## Configuring targets

The config file is TOML. It is looked up in this order:

1. `--config /path/to/file.toml`
2. `$SCRAPER_CONFIG`
3. `./scraper.toml`
4. `~/.config/discord-channel-scraper/config.toml`

`[defaults]` supplies fallbacks for every target; each target may override them.

| Key | Scope | Default | Meaning |
|---|---|---|---|
| `name` | target | *required* | Unique label used by `--target`. |
| `guild_id` | target | *required* | Server ID (Developer Mode → right-click server → Copy Server ID). |
| `output_dir` | both | `./data` | Where this target writes. Relative paths resolve against the config file; `~` and `$VARS` expand. A target without its own value gets `<defaults.output_dir>/<name>`. |
| `channels` | target | *all* | Allow-list of channel names or IDs. Naming a text/forum channel also includes its threads. |
| `exclude_channels` | target | *none* | Deny-list, same syntax. Takes precedence over `channels`. |
| `auth` | both | `"user"` | `"bot"` or `"user"`. |
| `token_env` | both | `DISCORD_USER_TOKEN` / `DISCORD_BOT_TOKEN` | Env var holding this target's token — set it to scrape different servers with different accounts. |
| `rate_limit` | both | `5` | Average requests/second. |
| `since` / `until` | both | *none* | ISO-8601 bounds; CLI flags override. |
| `enabled` | target | `true` | `false` skips the target in `scrape --all`. |

Two targets may not share an `output_dir` — they'd overwrite each other's
`_cursors.json`. The loader rejects that at startup, along with duplicate
names, non-numeric guild IDs, and unknown keys.

`scraper.toml` is gitignored (it contains your server/channel IDs);
[`scraper.example.toml`](./scraper.example.toml) is the shareable template.

## CLI reference

```console
$ discord-channel-scraper --help
Usage: discord-channel-scraper [OPTIONS] COMMAND [ARGS]...

  Scrape Discord channels from one or more servers into JSONL.

Commands:
  init        Write a starter targets config you can edit.
  preprocess  Augment a scraped JSONL with an LLM-friendly content_clean field.
  scrape      Backfill messages from configured targets, or from one ad-hoc server.
  targets     Show the servers configured in the targets file.

$ discord-channel-scraper scrape --help
Options:
  --config PATH            Path to the targets config (default: ./scraper.toml).
  -t, --target TEXT        Target name; repeatable.
  --all                    Scrape every enabled target.
  --auth [bot|user]        Auth backend for ad-hoc runs.
  --guild-id TEXT          Ad-hoc run against one server, ignoring targets.
  --since TEXT             Lower bound (ISO-8601, inclusive).
  --until TEXT             Upper bound (ISO-8601, inclusive).
  --channels TEXT          Comma-separated channel names or IDs to include.
  --exclude-channels TEXT  Comma-separated names or IDs to skip.
  --output-dir PATH
  --rate-limit FLOAT       Average requests per second (default: 5).
  --dry-run                Discover only, do not fetch messages.
  --json                   Print the raw JSON summary.
  -v, --verbose
  -h, --help               Show this message and exit.
```

`dcscrape` is installed as a shorter alias for the same command.

No config file needed for a one-off:

```bash
discord-channel-scraper scrape --auth user --guild-id 111111111111111111 \
    --channels general,announcements --output-dir ./tmp-archive
```

## Output layout

Each target owns a directory:

```
/Users/me/archives/comp-2026/
├── _channels.json          # discovered channels (ids, names, types)
├── _cursors.json           # resumable per-channel watermarks
└── <channel_id>.jsonl      # one file per channel, one message per line

/Users/me/archives/research/
├── _channels.json
├── _cursors.json
└── <channel_id>.jsonl
```

An annotated sample record lives in
[`examples/sample_output.jsonl`](./examples/sample_output.jsonl) (synthetic).
Full schema: [`docs/architecture.md`](./docs/architecture.md#message-jsonl-record).

## Alternatives & prior art

| Tool | Language | Notes |
|---|---|---|
| [Tyrrrz/DiscordChatExporter](https://github.com/Tyrrrz/DiscordChatExporter) | C# | The best-known exporter. GUI + CLI. Produces HTML/JSON/CSV/TXT. Larger surface; not Python-native; no declarative multi-server config. |
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
