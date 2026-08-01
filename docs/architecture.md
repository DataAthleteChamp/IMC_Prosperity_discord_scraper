# Architecture

This document explains how the scraper is organised and why each piece
exists.

## 30-second tour

```
┌──────────────────────────────────────────────────────────┐
│                     CLI   (click)                        │
│                                                          │
│   scraper.toml ──► load_config() ──► [Target, Target...] │
│         │                                                │
│         │  each Target: guild_id, channels, output_dir,  │
│         │               auth, token_env, since/until     │
│         ▼                                                │
│   run_targets()  — sequential, one target at a time      │
│         │                                                │
│         ▼                                                │
│   resolve_token()  ──►  .env / environment               │
│         │                                                │
│         ▼                                                │
│   AuthBackend (Protocol)                                 │
│       ├─ BotAuth     ("Bot <token>")                     │
│       └─ UserAuth    (raw token, ToS-risk)               │
│         │                                                │
│         ▼                                                │
│   DiscordClient  (httpx async, rate-limited)             │
│         │        ├─ aiolimiter 5 req/s + 0.2–0.8 jitter  │
│         │        ├─ 429 → Retry-After                    │
│         │        └─ 5xx → exponential backoff            │
│         ▼                                                │
│   discover_channels(guild_id)                            │
│       → text / announce / forum + active/archived threads│
│         │                                                │
│         ▼                                                │
│   select_channels(allow, deny)                           │
│       → match by ID or name, cascade to child threads    │
│         │                                                │
│         ▼                                                │
│   iter_channel_messages(channel_id, since, until)        │
│       → snowflake-cursor pagination, newest→oldest       │
│         │                                                │
│         ▼                                                │
│   normalize_message()  → pydantic Message                │
│         │                                                │
│         ▼                                                │
│   JsonlWriter.append()  + CursorStore.update()           │
│       → this target's own output_dir                     │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

## Modules (in dependency order)

| Module | Responsibility |
|---|---|
| `targets.py` | Parses `scraper.toml` into `Target` objects (one per server) with stdlib `tomllib`. Validates names, guild IDs, time bounds, and output-directory collisions. Also holds the `EXAMPLE_CONFIG` template used by `init`. |
| `config.py` | Loads secrets and process-wide defaults from `.env` / the environment. `resolve_token()` maps an auth mode (plus optional per-target `token_env`) to a token. |
| `auth.py` | `AuthBackend` Protocol with `BotAuth` and `UserAuth` implementations — the only place where the two auth modes differ. |
| `snowflake.py` | Convert `datetime` ↔ Discord snowflake for time-bounded pagination. |
| `client.py` | Thin async Discord REST client on top of `httpx`. Rate limiting, 429/5xx handling, endpoint helpers. |
| `models.py` | Pydantic v2 data classes: `Message`, `Author`, `Attachment`, `Reaction`, `Channel`. Every message also carries the full original payload under `raw`. |
| `normalize.py` | Pure functions that turn raw Discord payloads into the models. |
| `paginate.py` | `iter_channel_messages()` — snowflake-cursor pagination with optional `--since` / `--until` / resume-from-cursor. |
| `discover.py` | `discover_channels()` — enumerates every scrapeable channel, thread, and forum post in a guild. |
| `selectors.py` | `select_channels()` — applies allow/deny selectors that may be IDs *or* names, cascading a parent match down to its threads. Reports selectors that matched nothing. |
| `writer.py` | `JsonlWriter` (per-channel append-only) + `CursorStore` (`_cursors.json`) + `write_channel_index()`. |
| `scrape.py` | `run_backfill()` for one guild; `run_target()` builds a client for a `Target`; `run_targets()` drives many targets sequentially and isolates failures. |
| `preprocess.py` | Optional LLM-preprocessing pass: resolves mentions, strips markdown, appends `content_clean`. |
| `cli.py` | `click`-based entry point exposing `scrape`, `targets`, `init`, and `preprocess` subcommands. |

## Targets and isolation

A **target** is one server plus the decisions about it: which channels, which
time window, which token, and where the output goes.

- Targets run **sequentially**, never concurrently. A single Discord account
  issuing parallel bursts against several guilds is exactly the traffic shape
  that gets flagged; one-at-a-time keeps the request rate at the configured
  ceiling overall, not per server.
- Each target owns its `output_dir`. `_cursors.json` and `_channels.json` are
  per-directory, so two servers can never corrupt each other's resume state.
  The config loader rejects shared output directories up front.
- A failing target is recorded as `{"error": ...}` in the run summary and the
  remaining targets still run.

## Output layout

```
<target.output_dir>/
├── _channels.json        # discovered channels (ids, names, types)
├── _cursors.json         # per-channel watermarks (resume points)
└── <channel_id>.jsonl    # one file per channel, one message per line
```

### `_cursors.json` schema

```json
{
  "channels": {
    "<channel_id>": {
      "oldest_seen":   "1234567890",
      "newest_seen":   "9876543210",
      "backfill_done": false,
      "updated_at":    "2026-04-24T21:40:00Z"
    }
  }
}
```

### Message JSONL record (fields of interest)

```json
{
  "id": "1234",
  "channel_id": "1111",
  "channel_name": "strategy",
  "guild_id": "guild-1",
  "thread_parent_id": null,
  "author": {"id": "42", "username": "alice", "global_name": "Alice", "is_bot": false},
  "content": "raw markdown",
  "created_at": "2025-04-01T12:00:00Z",
  "edited_at": null,
  "reply_to_id": null,
  "type": 0,
  "attachments": [{"url": "...", "filename": "...", "content_type": "image/png", "size": 1234}],
  "reactions": [{"emoji": "👍", "count": 3}],
  "embeds_raw": [/* preserved */],
  "raw": {/* original Discord payload */},
  "fetched_at": "2026-04-24T21:40:00Z"
}
```

## Resume semantics

Every page is committed to `_cursors.json` immediately after it's written to
JSONL. On restart:

- If `backfill_done == false`: resume going **older** from `oldest_seen`.
- If `backfill_done == true`: fetch only messages newer than `newest_seen`,
  so re-running a completed target is incremental rather than a full
  re-download. Passing an explicit `--since` overrides that watermark.

The writer is append-only and does not deduplicate, so the watermark is what
keeps re-runs clean. If you deliberately re-scrape a range you already have
(e.g. with `--since`), expect duplicate lines.

## Rate-limiting design

- `aiolimiter.AsyncLimiter(5, 1)` — token bucket, 5 requests per second
  average.
- Per-request `asyncio.sleep(random.uniform(0.2, 0.8))` jitter so traffic
  doesn't look metronomic.
- On HTTP 429: sleep for `Retry-After` seconds + 0.25 s slack, then retry.
- On HTTP 5xx / transport errors: exponential backoff capped at 60 s,
  maximum 5 retries.
- On HTTP 403 (missing channel permission): the channel is logged and
  skipped; the overall scrape continues.

## Why direct `httpx` instead of `discord.py-self`?

- Both auth modes (bot vs user) use the same REST endpoints; only the
  `Authorization` header differs. A single client with two backends is
  simpler than maintaining two SDK integrations.
- Fewer dependencies → smaller supply-chain surface for an OSS scraper.
- Rate-limit and error behaviour is transparent and testable — everything
  goes through one `_request()` method.
- If the user-token library is ever updated with a fingerprint feature we
  want (e.g. `X-Super-Properties`), we can add that one header here.
