# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] — 2026-08-01

### Added

- **Multi-server targets.** A `scraper.toml` config file describes any number
  of servers, each with its own guild ID, channel selection, time window, and
  output directory. `scrape --all` runs every enabled target sequentially;
  `--target NAME` (repeatable) runs a subset.
- `init` subcommand that writes a starter config, and `targets` subcommand
  that lists what's configured.
- **Channel selection by name or ID.** `channels` / `exclude_channels` (and
  the matching CLI flags) accept `"general"` as readily as a snowflake, and
  selecting a text/forum channel now also selects the threads beneath it.
  Selectors that match nothing are reported as warnings.
- Per-target `token_env`, so different servers can be scraped with different
  accounts from one config.
- Config discovery via `--config`, `$SCRAPER_CONFIG`, `./scraper.toml`, or
  `~/.config/discord-channel-scraper/config.toml`.
- Rich tables for `targets` and for `--dry-run` output; `--json` restores
  machine-readable output.
- Integration tests that run a full two-server backfill against a mocked
  Discord API, plus CLI-level tests for argument validation. Suite grew from
  24 to 83 tests.

### Changed

- **Renamed** from `imc-prosperity-discord-scraper` to
  `discord-channel-scraper`. The CLI is now `discord-channel-scraper` (alias
  `dcscrape`) and the Python package is `discord_channel_scraper`.
  Documentation is no longer competition-specific.
- Run summaries now include `guild_id`, `output_dir`, and any unmatched
  channel selectors. `scrape --all` returns a summary keyed by target name.
- A target that fails no longer aborts the rest of the run; its error is
  recorded in the summary.
- `--auth` is now only required for ad-hoc `--guild-id` runs; targets carry
  their own auth mode.

### Removed

- Unused `keyring` dependency and the unused `bot` / `user` optional extras
  (the scraper talks to the REST API directly and never imported them).
  Install with `pip install -e ".[dev]"`.

### Fixed

- **Re-running a finished channel no longer re-downloads and duplicates every
  message.** Once `backfill_done` is set, later runs bound the fetch by the
  `newest_seen` watermark (via a new `after` parameter on the paginator), so
  the documented "just re-run it" workflow is now genuinely incremental. An
  explicit `--since` still overrides the watermark.
- `.gitignore` no longer excludes `examples/sample_output.jsonl`, which the
  README links to.
- Two targets can no longer share an output directory and corrupt each
  other's `_cursors.json`. Collisions are compared case-insensitively (macOS
  and Windows filesystems), target names containing path separators are
  rejected, and the `[defaults].output_dir` fallback is resolved so it can't
  be escaped.
- `--auth`, `--channels`, `--exclude-channels` and `--output-dir` are now
  rejected in `--target` / `--all` mode instead of being silently ignored —
  previously `scrape --all --channels general` would quietly scrape *every*
  channel of every server.
- A malformed `rate_limit` in the config raises a readable error instead of an
  uncaught `ValueError`/`TypeError`; non-positive and boolean values are
  rejected.
- API errors during ad-hoc runs print a clean message instead of a traceback.
- `scrape` exits non-zero when any target fails, so cron jobs notice.
- The `DISCORD_GUILD_ID` fallback is reachable again when a config file
  happens to be discoverable.
- `SCRAPER_OUTPUT_DIR` now expands `~`.

## [0.1.0] — 2026-04-24

### Added

- Initial public release.
- Two pluggable auth backends behind one CLI:
  - `--auth bot` — official Discord bot token (ToS-clean; requires an admin
    to invite the bot, see `docs/bot-invite.md`).
  - `--auth user` — user account token (violates Discord ToS; included with a
    prominent warning for research use).
- Direct `httpx`-based async REST client with:
  - Rate limiting via `aiolimiter` (default 5 req/s, configurable).
  - Randomized jitter (0.2–0.8 s) between requests.
  - 429 handling that honours the `Retry-After` header.
  - Exponential backoff on 5xx / connection errors.
- Snowflake-cursor pagination for `GET /channels/{id}/messages`.
- Channel discovery covering text channels, announcement channels, forum
  channels (type 15/16), and active + archived public/private threads.
- JSONL output, one file per channel, with a companion `_channels.json`
  index and resumable `_cursors.json` per-channel watermarks.
- Pydantic v2 message schema that preserves the original Discord payload
  under a `raw` field (schema-drift proof).
- `discord-channel-scraper preprocess` subcommand that resolves mentions,
  strips Discord markdown, and emits a `content_clean` field for LLM
  pipelines.
- `--since` / `--until` (ISO-8601) and `--channels` / `--exclude-channels`
  filters, plus `--dry-run`.
- Test suite (24 tests) with synthetic fixtures; CI runs on Python 3.11
  and 3.12.
- Pre-commit hooks: `gitleaks`, `ruff`, `ruff-format`.
- Documentation: `docs/architecture.md`, `docs/bot-invite.md`, `docs/faq.md`.

### Security

- `gitleaks` in CI + pre-commit to block accidental token commits.
- `.gitignore` excludes `.env`, `data/`, `*.jsonl`, `attachments/`.
- `SECURITY.md` with private disclosure instructions.

[Unreleased]: https://github.com/DataAthleteChamp/discord-channel-scraper/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/DataAthleteChamp/discord-channel-scraper/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/DataAthleteChamp/discord-channel-scraper/releases/tag/v0.1.0
