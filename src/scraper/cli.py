"""Command-line entry point.

Examples::

    # dry-run: discover channels, don't fetch messages
    prosperity-scraper scrape --auth user --dry-run

    # full backfill of the configured guild
    prosperity-scraper scrape --auth user

    # time-bounded backfill of two channels
    prosperity-scraper scrape --auth user \\
        --since 2025-01-01T00:00:00Z --until 2025-04-30T00:00:00Z \\
        --channels 1234,5678

    # preprocess a scraped channel file for LLM input
    prosperity-scraper preprocess ./data/1234.jsonl ./data/1234.clean.jsonl
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

import click

from . import __version__
from .auth import from_mode
from .client import DiscordClient
from .config import Settings
from .preprocess import preprocess_file
from .scrape import run_backfill


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    # httpx logs every request at INFO; mute unless verbose.
    if not verbose:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _parse_csv(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [x.strip() for x in value.split(",") if x.strip()]


@click.group()
@click.version_option(__version__, prog_name="prosperity-scraper")
def main() -> None:
    """IMC Prosperity Discord scraper."""


@main.command()
@click.option(
    "--auth",
    type=click.Choice(["bot", "user"]),
    required=True,
    help="Auth backend: 'bot' (ToS-clean) or 'user' (ToS-risk).",
)
@click.option("--guild-id", default=None, help="Override DISCORD_GUILD_ID from env.")
@click.option("--since", default=None, help="Lower bound (ISO-8601, inclusive).")
@click.option("--until", default=None, help="Upper bound (ISO-8601, inclusive).")
@click.option("--channels", default=None, help="Comma-separated channel/thread IDs to include.")
@click.option(
    "--exclude-channels", default=None, help="Comma-separated channel/thread IDs to skip."
)
@click.option("--output-dir", type=click.Path(path_type=Path), default=None)
@click.option(
    "--rate-limit", type=float, default=None, help="Average requests per second (default: 5)."
)
@click.option("--dry-run", is_flag=True, help="Discover only, do not fetch messages.")
@click.option("-v", "--verbose", is_flag=True)
def scrape(
    auth: str,
    guild_id: str | None,
    since: str | None,
    until: str | None,
    channels: str | None,
    exclude_channels: str | None,
    output_dir: Path | None,
    rate_limit: float | None,
    dry_run: bool,
    verbose: bool,
) -> None:
    """Backfill messages from the configured guild."""
    _setup_logging(verbose)
    settings = Settings.load(auth)  # type: ignore[arg-type]
    gid = guild_id or settings.guild_id
    if not gid:
        raise click.UsageError(
            "No guild ID provided. Pass --guild-id or set DISCORD_GUILD_ID in .env"
        )
    out = (output_dir or settings.output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    async def _run() -> dict:
        async with DiscordClient(
            from_mode(auth, settings.token),
            rate_limit_rps=rate_limit or settings.rate_limit_rps,
            user_agent=settings.user_agent,
        ) as client:
            return await run_backfill(
                client,
                gid,
                out,
                since=_parse_dt(since),
                until=_parse_dt(until),
                channels_allow=_parse_csv(channels),
                channels_deny=_parse_csv(exclude_channels),
                dry_run=dry_run,
            )

    summary = asyncio.run(_run())
    click.echo(json.dumps(summary, indent=2, default=str))


@main.command()
@click.argument("input_path", type=click.Path(exists=True, path_type=Path))
@click.argument("output_path", type=click.Path(path_type=Path))
@click.option(
    "--channels-index",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to _channels.json (defaults to sibling of input).",
)
@click.option("-v", "--verbose", is_flag=True)
def preprocess(
    input_path: Path,
    output_path: Path,
    channels_index: Path | None,
    verbose: bool,
) -> None:
    """Augment a scraped JSONL with an LLM-friendly ``content_clean`` field."""
    _setup_logging(verbose)
    idx = channels_index or (input_path.parent / "_channels.json")
    n = preprocess_file(input_path, output_path, idx)
    click.echo(f"wrote {n} records to {output_path}")


if __name__ == "__main__":
    main()
