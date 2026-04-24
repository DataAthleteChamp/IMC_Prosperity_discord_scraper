# Architecture

This document explains how the scraper is organised and why each piece
exists.

## 30-second tour

```
┌──────────────────────────────────────────────────────────┐
│                     CLI   (click)                        │
│                                                          │
│   --auth {bot|user}  --since/--until  --channels ...     │
│         │                                                │
│         ▼                                                │
│   Settings.load()  ──►  .env / keyring                   │
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
│   iter_channel_messages(channel_id, since, until)        │
│       → snowflake-cursor pagination, newest→oldest       │
│         │                                                │
│         ▼                                                │
│   normalize_message()  → pydantic Message                │
│         │                                                │
│         ▼                                                │
│   JsonlWriter.append()  + CursorStore.update()           │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

## Modules (in dependency order)

| Module | Responsibility |
|---|---|
| `config.py` | Loads `Settings` from `.env` (token, guild id, output dir, rate limit, user-agent). |
| `auth.py` | `AuthBackend` Protocol with `BotAuth` and `UserAuth` implementations — the only place where the two auth modes differ. |
| `snowflake.py` | Convert `datetime` ↔ Discord snowflake for time-bounded pagination. |
| `client.py` | Thin async Discord REST client on top of `httpx`. Rate limiting, 429/5xx handling, endpoint helpers. |
| `models.py` | Pydantic v2 data classes: `Message`, `Author`, `Attachment`, `Reaction`, `Channel`. Every message also carries the full original payload under `raw`. |
| `normalize.py` | Pure functions that turn raw Discord payloads into the models. |
| `paginate.py` | `iter_channel_messages()` — snowflake-cursor pagination with optional `--since` / `--until` / resume-from-cursor. |
| `discover.py` | `discover_channels()` — enumerates every scrapeable channel, thread, and forum post in a guild. |
| `writer.py` | `JsonlWriter` (per-channel append-only) + `CursorStore` (`_cursors.json`) + `write_channel_index()`. |
| `scrape.py` | `run_backfill()` orchestrator — ties discovery, pagination, normalization, and writing together. |
| `preprocess.py` | Optional LLM-preprocessing pass: resolves mentions, strips markdown, appends `content_clean`. |
| `cli.py` | `click`-based entry point exposing `scrape` and `preprocess` subcommands. |

## Output layout

```
data/
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
- If `backfill_done == true` and `--since` isn't provided: walk **forward**
  from `newest_seen` (future enhancement — currently incremental re-runs just
  start from `newest_seen + 1` via the paginator's `after=` semantics).

Dedup on re-read is on `id` — the writer is append-only, so if you manually
re-run over the same range you can get duplicate lines; `preprocess.py` can
be taught to drop them (future work — see roadmap).

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
