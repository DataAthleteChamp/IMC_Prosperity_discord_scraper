# FAQ

## I'm not an admin of the IMC Prosperity server. Can I still use this?

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
IMC Prosperity with it, and use *its* token.

## Why JSONL and not SQLite?

SQLite is arguably the architecturally better choice (upserts, queries,
single-file portability). JSONL was picked as the default because:

- Simpler for LLM pipelines — most tools eat JSONL directly.
- Diff-able, `grep`-able, human-inspectable.
- No "what library do I need to read it" friction for collaborators.

A future version may add SQLite as an option (see roadmap in README).

## Can I use this for other Discord servers?

Yes. The project's name is specific to IMC Prosperity but the code is
not: set `DISCORD_GUILD_ID` to any server your account belongs to.

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
For the IMC Prosperity server as of April 2026 (~9 channels), expect
anywhere from a few minutes to an hour depending on message density.

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
