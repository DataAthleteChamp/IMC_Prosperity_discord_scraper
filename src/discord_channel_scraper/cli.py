"""Command-line entry point.

Examples::

    # write a starter config, then edit it
    discord-channel-scraper init

    # see what's configured
    discord-channel-scraper targets

    # dry-run one target: discover channels, don't fetch messages
    discord-channel-scraper scrape --target server-one --dry-run

    # backfill every enabled target, each into its own output_dir
    discord-channel-scraper scrape --all

    # backfill two named targets over a time window
    discord-channel-scraper scrape -t server-one -t server-two \\
        --since 2025-01-01T00:00:00Z --until 2025-04-30T00:00:00Z

    # ad-hoc run without a config file
    discord-channel-scraper scrape --auth user --guild-id 1234 --channels general

    # preprocess a scraped channel file for LLM input
    discord-channel-scraper preprocess ./data/1234.jsonl ./data/1234.clean.jsonl
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from . import __version__
from .auth import from_mode
from .client import DiscordAPIError, DiscordClient
from .config import Settings, load_env, user_agent_from_env
from .preprocess import preprocess_file
from .scrape import run_backfill, run_targets
from .targets import (
    DEFAULT_CONFIG_NAME,
    EXAMPLE_CONFIG,
    ConfigError,
    ScraperConfig,
    Target,
    find_config,
    load_config,
)

console = Console()


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


def _load_config_or_none(config: Path | None) -> ScraperConfig | None:
    try:
        path = find_config(config)
    except ConfigError as e:
        raise click.UsageError(str(e)) from e
    if path is None:
        return None
    try:
        return load_config(path)
    except ConfigError as e:
        raise click.UsageError(str(e)) from e


def _resolve_targets(
    cfg: ScraperConfig | None, names: tuple[str, ...], all_targets: bool
) -> list[Target]:
    if cfg is None:
        raise click.UsageError(
            f"No config file found. Run 'discord-channel-scraper init' to create "
            f"{DEFAULT_CONFIG_NAME}, or pass --guild-id for a one-off run."
        )
    try:
        selected = cfg.select(list(names) if names else None)
    except ConfigError as e:
        raise click.UsageError(str(e)) from e
    if not selected:
        which = "matched" if names else "enabled"
        raise click.UsageError(f"No {which} targets in {cfg.path}")
    return selected


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="discord-channel-scraper")
def main() -> None:
    """Scrape Discord channels from one or more servers into JSONL."""


@main.command()
@click.option(
    "--config",
    "config_path",
    type=click.Path(path_type=Path),
    default=None,
    help=f"Path to the targets config (default: ./{DEFAULT_CONFIG_NAME}).",
)
@click.option("-t", "--target", "targets", multiple=True, help="Target name; repeatable.")
@click.option("--all", "all_targets", is_flag=True, help="Scrape every enabled target.")
@click.option(
    "--auth",
    type=click.Choice(["bot", "user"]),
    default=None,
    help="Auth backend for ad-hoc runs: 'bot' (ToS-clean) or 'user' (ToS-risk).",
)
@click.option("--guild-id", default=None, help="Ad-hoc run against one server, ignoring targets.")
@click.option("--since", default=None, help="Lower bound (ISO-8601, inclusive).")
@click.option("--until", default=None, help="Upper bound (ISO-8601, inclusive).")
@click.option("--channels", default=None, help="Comma-separated channel names or IDs to include.")
@click.option("--exclude-channels", default=None, help="Comma-separated names or IDs to skip.")
@click.option("--output-dir", type=click.Path(path_type=Path), default=None)
@click.option(
    "--rate-limit", type=float, default=None, help="Average requests per second (default: 5)."
)
@click.option("--dry-run", is_flag=True, help="Discover only, do not fetch messages.")
@click.option("--json", "as_json", is_flag=True, help="Print the raw JSON summary.")
@click.option("-v", "--verbose", is_flag=True)
def scrape(
    config_path: Path | None,
    targets: tuple[str, ...],
    all_targets: bool,
    auth: str | None,
    guild_id: str | None,
    since: str | None,
    until: str | None,
    channels: str | None,
    exclude_channels: str | None,
    output_dir: Path | None,
    rate_limit: float | None,
    dry_run: bool,
    as_json: bool,
    verbose: bool,
) -> None:
    """Backfill messages from configured targets, or from one ad-hoc server."""
    _setup_logging(verbose)

    if guild_id and (targets or all_targets):
        raise click.UsageError(
            "--guild-id is for ad-hoc runs; don't combine it with --target/--all"
        )

    if targets or all_targets:
        # These are per-target settings in the config; honouring them globally
        # would silently widen or redirect a multi-server run.
        conflicting = {
            "--auth": auth,
            "--channels": channels,
            "--exclude-channels": exclude_channels,
            "--output-dir": output_dir,
        }
        used = [flag for flag, value in conflicting.items() if value]
        if used:
            raise click.UsageError(
                f"{', '.join(used)} only applies to ad-hoc --guild-id runs. "
                "Set these per target in the config file instead."
            )

    cfg = None if guild_id else _load_config_or_none(config_path)

    if targets or all_targets:
        selected = _resolve_targets(cfg, targets, all_targets)
        load_env()
        summary = asyncio.run(
            run_targets(
                selected,
                since=_parse_dt(since),
                until=_parse_dt(until),
                rate_limit=rate_limit,
                user_agent=user_agent_from_env(),
                dry_run=dry_run,
            )
        )
        _emit(summary, as_json=as_json, dry_run=dry_run, multi=True)
        failed = sorted(name for name, result in summary.items() if "error" in result)
        if failed:
            raise click.ClickException(f"{len(failed)} target(s) failed: {', '.join(failed)}")
        return

    if cfg is not None and not guild_id:
        # A discoverable config doesn't rule out the DISCORD_GUILD_ID fallback,
        # but with neither that nor a target name there's nothing to scrape.
        load_env()
        if not os.environ.get("DISCORD_GUILD_ID", "").strip():
            available = ", ".join(t.name for t in cfg.targets) or "<none>"
            raise click.UsageError(
                f"Pick what to scrape: --target NAME (one of: {available}), "
                f"--all for every enabled target in {cfg.path}, "
                f"or --guild-id for a one-off server."
            )

    summary = _run_adhoc(
        auth=auth,
        guild_id=guild_id,
        since=since,
        until=until,
        channels=channels,
        exclude_channels=exclude_channels,
        output_dir=output_dir,
        rate_limit=rate_limit,
        dry_run=dry_run,
    )
    _emit(summary, as_json=as_json, dry_run=dry_run)


def _run_adhoc(
    *,
    auth: str | None,
    guild_id: str | None,
    since: str | None,
    until: str | None,
    channels: str | None,
    exclude_channels: str | None,
    output_dir: Path | None,
    rate_limit: float | None,
    dry_run: bool,
) -> dict:
    if not auth:
        raise click.UsageError(
            "--auth is required for ad-hoc runs (use 'bot' or 'user'). "
            "For repeatable multi-server runs, create a config with "
            "'discord-channel-scraper init'."
        )
    try:
        settings = Settings.load(auth)  # type: ignore[arg-type]
    except RuntimeError as e:  # missing token
        raise click.ClickException(str(e)) from e
    gid = guild_id or settings.guild_id
    if not gid:
        raise click.UsageError(
            "No server to scrape. Use --target/--all with a config file, "
            "or pass --guild-id, or set DISCORD_GUILD_ID in .env"
        )
    out = (output_dir or settings.output_dir).expanduser().resolve()
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

    try:
        return asyncio.run(_run())
    except (DiscordAPIError, RuntimeError) as e:
        raise click.ClickException(str(e)) from e


def _emit(summary: dict, *, as_json: bool, dry_run: bool, multi: bool = False) -> None:
    if as_json or not dry_run:
        click.echo(json.dumps(summary, indent=2, default=str))
        return
    runs = summary if multi else {"": summary}
    for name, result in runs.items():
        if "error" in result:
            console.print(f"[red]{name}: {result['error']}[/red]")
            continue
        title = f"{name or 'discovered channels'} — {result['selected']}/{result['discovered']}"
        table = Table(title=title, header_style="bold")
        table.add_column("channel id", no_wrap=True)
        table.add_column("name")
        table.add_column("type", justify="right")
        table.add_column("thread", justify="center")
        for ch in result.get("channels", []):
            table.add_row(
                ch["id"],
                ch.get("name") or "-",
                str(ch["type"]),
                "yes" if ch.get("is_thread") else "",
            )
        console.print(table)
        console.print(f"output_dir: {result.get('output_dir')}")


@main.command(name="targets")
@click.option(
    "--config",
    "config_path",
    type=click.Path(path_type=Path),
    default=None,
    help=f"Path to the targets config (default: ./{DEFAULT_CONFIG_NAME}).",
)
@click.option("--json", "as_json", is_flag=True, help="Print raw JSON instead of a table.")
def list_targets(config_path: Path | None, as_json: bool) -> None:
    """Show the servers configured in the targets file."""
    cfg = _load_config_or_none(config_path)
    if cfg is None:
        raise click.UsageError(
            f"No config file found. Run 'discord-channel-scraper init' to create "
            f"{DEFAULT_CONFIG_NAME}."
        )
    if as_json:
        click.echo(
            json.dumps(
                [
                    {
                        "name": t.name,
                        "guild_id": t.guild_id,
                        "output_dir": str(t.output_dir),
                        "auth": t.auth_mode,
                        "token_env": t.resolved_token_env,
                        "channels": list(t.channels),
                        "exclude_channels": list(t.exclude_channels),
                        "enabled": t.enabled,
                    }
                    for t in cfg.targets
                ],
                indent=2,
                default=str,
            )
        )
        return

    table = Table(title=f"targets in {cfg.path}", header_style="bold")
    table.add_column("name")
    table.add_column("guild id", no_wrap=True)
    table.add_column("auth")
    table.add_column("channels")
    table.add_column("output dir")
    table.add_column("on", justify="center")
    for t in cfg.targets:
        table.add_row(
            t.name,
            t.guild_id,
            t.auth_mode,
            ", ".join(t.channels) if t.channels else "[dim]all[/dim]",
            str(t.output_dir),
            "✓" if t.enabled else "[dim]-[/dim]",
        )
    console.print(table)


@main.command()
@click.option(
    "--path",
    type=click.Path(path_type=Path),
    default=None,
    help=f"Where to write the config (default: ./{DEFAULT_CONFIG_NAME}).",
)
@click.option("--force", is_flag=True, help="Overwrite an existing file.")
def init(path: Path | None, force: bool) -> None:
    """Write a starter targets config you can edit."""
    dest = (path or Path.cwd() / DEFAULT_CONFIG_NAME).expanduser()
    if dest.exists() and not force:
        raise click.UsageError(f"{dest} already exists (use --force to overwrite)")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(EXAMPLE_CONFIG, encoding="utf-8")
    console.print(f"[green]wrote[/green] {dest}")
    console.print("Next: set guild_id / output_dir per target, then run 'scrape --all --dry-run'.")


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
