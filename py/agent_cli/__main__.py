"""Subprocess entry point for AgentCLI (debugging / external use).

Usage::

    python -m py.agent_cli base-models list [--limit N]
    python -m py.agent_cli metadata read <path>
    python -m py.agent_cli metadata update <path> --json '{...}'
    python -m py.agent_cli preview download <path> --url <url>
    python -m py.agent_cli cache refresh <path>

NOTE: This is an **optional** convenience wrapper.  The primary consumer of
AgentCLI is the :mod:`AgentService` (in-process).  This entry point exists
for manual debugging and future integration with subprocess-based agent
frameworks.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any, Dict, List


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lmcli", description="LoRA Manager Agent CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    # base-models list
    base_models = sub.add_parser("base-models", aliases=["bm"])
    base_models_cmds = base_models.add_subparsers(dest="subcommand", required=True)
    base_models_list = base_models_cmds.add_parser("list")
    base_models_list.add_argument(
        "--limit", type=int, default=0, help="Max number of models (0 = all)"
    )

    # metadata read
    meta = sub.add_parser("metadata", aliases=["md"])
    meta_cmds = meta.add_subparsers(dest="subcommand", required=True)
    meta_read = meta_cmds.add_parser("read")
    meta_read.add_argument("path", type=str, help="Model file path")

    # metadata update
    meta_update = meta_cmds.add_parser("update")
    meta_update.add_argument("path", type=str, help="Model file path")
    meta_update.add_argument(
        "--json",
        type=str,
        required=True,
        help='JSON object of fields to update, e.g. \'{"base_model": "SDXL 1.0"}\'',
    )

    # preview download
    prev = sub.add_parser("preview", aliases=["pv"])
    prev_cmds = prev.add_subparsers(dest="subcommand", required=True)
    prev_dl = prev_cmds.add_parser("download")
    prev_dl.add_argument("path", type=str, help="Model file path")
    prev_dl.add_argument("--url", type=str, required=True, help="Preview image URL")

    # cache refresh
    cache = sub.add_parser("cache")
    cache_cmds = cache.add_subparsers(dest="subcommand", required=True)
    cache_refresh = cache_cmds.add_parser("refresh")
    cache_refresh.add_argument("path", type=str, help="Model file path")

    return parser


async def _run(args: argparse.Namespace) -> Any:
    from . import (  # lazy import so startup is fast
        list_base_models,
        read_metadata,
        apply_metadata_updates,
        download_preview,
        refresh_cache,
    )

    cmd = args.command
    sub = args.subcommand

    if cmd in ("base-models", "bm") and sub == "list":
        return await list_base_models(limit=args.limit)

    if cmd in ("metadata", "md") and sub == "read":
        return await read_metadata(args.path)

    if cmd in ("metadata", "md") and sub == "update":
        updates: Dict[str, Any] = json.loads(args.json)
        return await apply_metadata_updates(args.path, updates)

    if cmd in ("preview", "pv") and sub == "download":
        return await download_preview(args.path, args.url)

    if cmd == "cache" and sub == "refresh":
        return await refresh_cache(args.path)

    raise ValueError(f"Unknown command: {cmd} {sub}")


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    result = asyncio.run(_run(args))
    # Always print as JSON so callers can parse reliably
    if isinstance(result, list):
        for item in result:
            print(item)
    elif isinstance(result, dict):
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        print(json.dumps(result))


if __name__ == "__main__":
    main()
