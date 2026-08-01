# FAQ

## I'm not an admin of the server I want to archive. Can I still use this?

Yes — that's what the `--auth user` backend is for. It authenticates with
your own Discord user token. Be aware this violates Discord's Terms of
Service and carries account-ban risk. The tool ships with safety defaults
(5 req/s, random jitter, `Retry-After` handling) that put it in the
lowest-risk bracket of automation, but you accept the risk by using it.

See the "Safety & privacy" section of `README.md` for the full risk analysis.

## Will I get my Discord account banned?

Honest answer: nobody outside Discord knows their exact enforcement
heuristics. Empirically:

- Read-only, low-volume use of a user token (exactly what this tool does)
  is the lowest-risk category. Tools like DiscordChatExporter have
  operated this way for years.
- Bans, when they happen, usually correlate with: high request rates,
  parallel sessions from different IPs, newly-created "burner" accounts
  used for scraping + reporting others, or explicit rule-breaking
  patterns (mass-DMing, raid assistance, etc.).

If you are concerned, create a dedicated throwaway Discord account, join
the server with it, and use *its* token.

## Why JSONL and not SQLite?

SQLite is arguably the architecturally better choice (upserts, queries,
single-file portability). JSONL was picked as the default because:

- Simpler for LLM pipelines — most tools eat JSONL directly.
- Diff-able, `grep`-able, human-inspectable.
- No "what library do I need to read it" friction for collaborators.

A future version may add SQLite as an option (see roadmap in README).

## Can I scrape several servers at once?

Yes — that's the main workflow. Add one `[[targets]]` block per server to
`scraper.toml`, each with its own `guild_id`, `channels`, and `output_dir`,
then run `discord-channel-scraper scrape --all`. Targets are processed
sequentially so a single account never issues parallel bursts.

All targets share the account token from `.env` by default. To use a
different account for one server, put its token in another env var and point
the target at it with `token_env = "DISCORD_USER_TOKEN_ALT"`.

## How do I pick which channels to scrape?

List them under `channels` by **name or ID** — `channels = ["general",
"round-5"]` works, and so does a raw snowflake. `exclude_channels` uses the
same syntax and wins over `channels`. Naming a text or forum channel also
selects the threads underneath it. Omit `channels` entirely to take every
channel your account can read.

Run `discord-channel-scraper scrape --target NAME --dry-run` to print the
full channel list for a server without downloading any messages.

## Can two targets write to the same folder?

No. Each target needs its own `output_dir` because `_cursors.json` and
`_channels.json` are per-directory; sharing one would corrupt both servers'
resume state. The config loader rejects it at startup.

## How do I get my user token?

See the README quickstart. In short: Discord web client → DevTools →
Network → any `/api` request → copy the `Authorization` header. Treat
that string as equivalent to your Discord password.

## How do I get my bot token (if I convinced an admin)?

See `docs/bot-invite.md` for the full flow.

## Can I publish the scraped data?

**Please don't.** Messages contain other users' personal data and may be
covered by privacy laws (GDPR, CCPA) in your jurisdiction. This project
ships the *tool*, never datasets. If you want to publish derived work
(e.g. for research), anonymise author IDs/usernames first.

## What about `mod-logs` / channels I can't read?

If your account doesn't have permission to read a channel, Discord will
return HTTP 403 to the scraper. The channel is logged under `skipped`
in the run summary and the rest of the scrape continues. There's no
way to scrape a channel you can't see in the UI — the token inherits
your exact permissions.

## How long does a full backfill take?

At the default 5 req/s × 100 messages/request = 500 messages/second.
For a channel with 50,000 messages that's ~100 seconds, plus jitter.
For a mid-sized community server (~10 channels), expect anywhere from a
few minutes to an hour depending on message density. With `scrape --all`,
targets run one after another, so total time is the sum across servers.

## Is it resumable?

Yes. Cursors are flushed to `_cursors.json` after every page. Ctrl-C
at any time; re-run with the same command; it picks up where it left
off. If a channel's `backfill_done` is `true`, subsequent runs only
fetch messages newer than the recorded `newest_seen`.

## I see lots of `403` logs for `threads/archived/private`. Is that bad?

No. User tokens cannot list private archived threads unless you have
the "Manage Threads" permission (which almost no regular member has).
The scraper swallows that 403 as expected. Public archived threads
are fetched normally.
