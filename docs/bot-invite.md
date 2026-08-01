# Pitch template: asking an admin to invite a read-only bot

The Terms-of-Service–clean path for this scraper is a **Bot account** invited
to the Discord server by an admin. If you can persuade whoever runs the
server to invite your bot, you get:

- Zero personal-account risk.
- Official, stable API surface.
- Real-time event stream if you ever want to tail live.

## Steps

1. Create an application at <https://discord.com/developers/applications>.
2. Under **Bot**, enable **Message Content Intent** (privileged — self-serve
   in servers with <100 members).
3. Under **OAuth2 → URL Generator**, select scopes `bot` and
   `applications.commands`, and permissions **View Channel** and
   **Read Message History** only (no send, no moderate, no manage).
4. Copy the generated invite URL and the bot token.
5. Save the token to `.env` as `DISCORD_BOT_TOKEN`, and set `auth = "bot"`
   on the relevant target in `scraper.toml`.

## Email/DM template

> Hi team,
>
> I'm a member of this server building an open-source, **read-only** archive
> tool so community members can search and analyse past discussions
> (strategy threads, announcements, etc.) offline. Source is public:
> `https://github.com/DataAthleteChamp/discord-channel-scraper`.
>
> I'd like to request that you invite a read-only bot I've built to the
> server. Its permissions are limited to **View Channel** + **Read Message
> History** — it cannot post, moderate, or DM anyone. Data stays local to
> whoever runs the tool; nothing from the server will be republished.
>
> Invite link: `<paste your OAuth2 URL here>`
>
> Happy to answer any questions or adjust the permissions set.
>
> Thanks!

## If they decline

Fall back to the user-token backend (`auth = "user"`). Read the ToS warning
in the README first.
