# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
- `prosperity-scraper preprocess` subcommand that resolves mentions,
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

[Unreleased]: https://github.com/DataAthleteChamp/IMC_Prosperity_discord_scraper/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/DataAthleteChamp/IMC_Prosperity_discord_scraper/releases/tag/v0.1.0
