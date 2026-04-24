"""Auth backends — provide the right `Authorization` header for Discord REST.

Two backends share one interface so the rest of the scraper is auth-agnostic:

- :class:`BotAuth`  — ToS-clean. Requires a bot invited to the server by an admin.
- :class:`UserAuth` — uses a user account token. Violates Discord ToS; ban risk.
"""

from __future__ import annotations

from typing import Protocol


class AuthBackend(Protocol):
    """Produces the value of the HTTP ``Authorization`` header for Discord."""

    mode: str

    def header(self) -> str: ...


class BotAuth:
    mode = "bot"

    def __init__(self, token: str) -> None:
        self._token = token

    def header(self) -> str:
        return f"Bot {self._token}"


class UserAuth:
    mode = "user"

    def __init__(self, token: str) -> None:
        self._token = token

    def header(self) -> str:
        # User tokens are sent as the raw value, no prefix.
        return self._token


def from_mode(mode: str, token: str) -> AuthBackend:
    if mode == "bot":
        return BotAuth(token)
    if mode == "user":
        return UserAuth(token)
    raise ValueError(f"Unknown auth mode: {mode!r}")
