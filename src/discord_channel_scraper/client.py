"""Async Discord REST client with rate limiting, retries, and 429 handling.

We talk to the REST API directly via ``httpx`` rather than going through
``discord.py``/``discord.py-self``. Rationale:

- Both auth modes (bot / user) use the same endpoints; only the
  ``Authorization`` header differs.
- Thin, inspectable, few dependencies.
- Easier to reason about rate-limit and error behaviour.

Endpoints used (all documented at https://discord.com/developers/docs):

- ``GET /users/@me/guilds``
- ``GET /guilds/{guild_id}/channels``
- ``GET /channels/{channel_id}``
- ``GET /channels/{channel_id}/messages``        (pagination via ``before``)
- ``GET /channels/{channel_id}/threads/archived/public``
- ``GET /channels/{channel_id}/threads/archived/private``
- ``GET /guilds/{guild_id}/threads/active``
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

import httpx
from aiolimiter import AsyncLimiter

from .auth import AuthBackend

log = logging.getLogger(__name__)

API_BASE = "https://discord.com/api/v10"


class DiscordAPIError(RuntimeError):
    def __init__(self, status: int, message: str, body: Any = None) -> None:
        super().__init__(f"Discord API {status}: {message}")
        self.status = status
        self.body = body


class DiscordClient:
    """Rate-limited async Discord REST client.

    Parameters
    ----------
    auth:
        Auth backend (bot or user).
    rate_limit_rps:
        Average requests per second. Default 5 — well below Discord's 50/s global
        cap, and human-like enough that a user-token scraper blends in.
    user_agent:
        Browser-looking UA string. Only consequential for user-token mode.
    max_retries:
        Retries on 5xx / connection errors per request.
    """

    def __init__(
        self,
        auth: AuthBackend,
        *,
        rate_limit_rps: float = 5.0,
        user_agent: str = "discord-channel-scraper/0.2.0",
        max_retries: int = 5,
        jitter: tuple[float, float] = (0.2, 0.8),
    ) -> None:
        self._auth = auth
        self._limiter = AsyncLimiter(max_rate=max(1, int(rate_limit_rps)), time_period=1)
        self._max_retries = max_retries
        self._jitter = jitter
        headers = {
            "Authorization": auth.header(),
            "User-Agent": user_agent,
            "Accept": "application/json",
        }
        self._http = httpx.AsyncClient(
            base_url=API_BASE,
            headers=headers,
            timeout=httpx.Timeout(30.0, connect=10.0),
            http2=False,
        )

    async def __aenter__(self) -> DiscordClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    # ---- low-level ---------------------------------------------------------

    async def _request(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Perform a GET with rate-limit, 429 backoff, and 5xx retries."""
        attempt = 0
        while True:
            async with self._limiter:
                await asyncio.sleep(random.uniform(*self._jitter))
                try:
                    resp = await self._http.get(path, params=params)
                except httpx.TransportError as e:
                    if attempt >= self._max_retries:
                        raise
                    backoff = min(60.0, 2**attempt)
                    log.warning("transport error (%s); retrying in %.1fs", e, backoff)
                    attempt += 1
                    await asyncio.sleep(backoff)
                    continue

            if resp.status_code == 429:
                retry_after = float(
                    resp.headers.get("Retry-After") or _safe_json(resp).get("retry_after", 1.0)
                )
                log.warning("429 rate-limited; sleeping %.2fs (%s)", retry_after, path)
                await asyncio.sleep(retry_after + 0.25)
                continue

            if 500 <= resp.status_code < 600:
                if attempt >= self._max_retries:
                    raise DiscordAPIError(resp.status_code, resp.text)
                backoff = min(60.0, 2**attempt)
                log.warning("5xx (%s); retrying in %.1fs", resp.status_code, backoff)
                attempt += 1
                await asyncio.sleep(backoff)
                continue

            if resp.status_code == 401:
                raise DiscordAPIError(401, "Unauthorized — token invalid or revoked")
            if resp.status_code == 403:
                raise DiscordAPIError(403, f"Forbidden ({path})", _safe_json(resp))
            if resp.status_code == 404:
                raise DiscordAPIError(404, f"Not found ({path})")
            if resp.status_code >= 400:
                raise DiscordAPIError(resp.status_code, resp.text, _safe_json(resp))

            data: Any = resp.json()
            return data

    # ---- high-level endpoints ---------------------------------------------

    async def list_user_guilds(self) -> list[dict[str, Any]]:
        """List guilds the authenticated account is a member of."""
        data = await self._request("/users/@me/guilds")
        return list(data)

    async def list_guild_channels(self, guild_id: str) -> list[dict[str, Any]]:
        data = await self._request(f"/guilds/{guild_id}/channels")
        return list(data)

    async def get_channel(self, channel_id: str) -> dict[str, Any]:
        data = await self._request(f"/channels/{channel_id}")
        return dict(data)

    async def list_guild_active_threads(self, guild_id: str) -> dict[str, Any]:
        data = await self._request(f"/guilds/{guild_id}/threads/active")
        return dict(data)

    async def list_archived_public_threads(
        self, channel_id: str, *, before: str | None = None, limit: int = 100
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if before:
            params["before"] = before
        data = await self._request(f"/channels/{channel_id}/threads/archived/public", params=params)
        return dict(data)

    async def list_archived_private_threads(
        self, channel_id: str, *, before: str | None = None, limit: int = 100
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if before:
            params["before"] = before
        try:
            data = await self._request(
                f"/channels/{channel_id}/threads/archived/private", params=params
            )
        except DiscordAPIError as e:
            if e.status == 403:
                return {"threads": [], "members": [], "has_more": False}
            raise
        return dict(data)

    async def get_messages(
        self,
        channel_id: str,
        *,
        before: str | None = None,
        after: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit}
        if before:
            params["before"] = before
        if after:
            params["after"] = after
        data = await self._request(f"/channels/{channel_id}/messages", params=params)
        return list(data)


def _safe_json(resp: httpx.Response) -> dict[str, Any]:
    try:
        data = resp.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}
