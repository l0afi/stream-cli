#!/usr/bin/env python3
"""stream-cli: Search and stream movies/shows from configurable providers."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "stream-cli" / "config.json"

DEFAULT_CONFIG = {
    "player": "mpv",
    "providers": [
        {
            "name": "example-static",
            "type": "static",
            "path": "~/.config/stream-cli/example_provider.json",
        }
    ],
}

DEFAULT_PROVIDER_DATA = {
    "catalog": [
        {"id": "demo-movie", "title": "Demo Movie", "year": 2024, "type": "movie"},
        {"id": "demo-show-s01e01", "title": "Demo Show S01E01", "year": 2024, "type": "show"},
    ],
    "streams": {
        "demo-movie": [
            {
                "name": "Demo 1080p",
                "url": "https://example.com/demo-movie-1080p.m3u8",
            }
        ],
        "demo-show-s01e01": [
            {
                "name": "Demo Episode",
                "url": "https://example.com/demo-show-s01e01.m3u8",
            }
        ],
    },
}


class StreamCliError(Exception):
    """Raised for expected stream-cli errors."""


def _expand(path: str) -> Path:
    return Path(os.path.expanduser(path)).resolve()


def init_config(config_path: Path) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if not config_path.exists():
        config_path.write_text(json.dumps(DEFAULT_CONFIG, indent=2) + "\n", encoding="utf-8")

    example_path = _expand(DEFAULT_CONFIG["providers"][0]["path"])
    example_path.parent.mkdir(parents=True, exist_ok=True)
    if not example_path.exists():
        example_path.write_text(json.dumps(DEFAULT_PROVIDER_DATA, indent=2) + "\n", encoding="utf-8")


def load_config(config_path: Path) -> Dict[str, Any]:
    if not config_path.exists():
        raise StreamCliError(
            f"Config not found: {config_path}. Run `stream-cli init` to create a starter config."
        )

    with config_path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)

    if "providers" not in config or not isinstance(config["providers"], list):
        raise StreamCliError("Config must contain a providers array.")

    if "player" not in config:
        config["player"] = "mpv"

    return config


def _run_provider_command(command: str, *args: str) -> Any:
    try:
        parts = shlex.split(command)
    except ValueError as exc:
        raise StreamCliError(f"Invalid provider command: {exc}") from exc

    result = subprocess.run(
        [*parts, *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise StreamCliError(
            f"Provider command failed ({result.returncode}): {' '.join(parts)}\n{result.stderr.strip()}"
        )

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise StreamCliError(f"Provider command returned invalid JSON: {exc}") from exc


def _load_static_provider(provider: Dict[str, Any]) -> Dict[str, Any]:
    provider_path = provider.get("path")
    if not provider_path:
        raise StreamCliError(f"Static provider '{provider.get('name', '<unnamed>')}' missing path")

    path = _expand(provider_path)
    if not path.exists():
        raise StreamCliError(f"Static provider data file not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def search_provider(provider: Dict[str, Any], query: str) -> List[Dict[str, Any]]:
    provider_name = provider.get("name", "unnamed")
    provider_type = provider.get("type")

    if provider_type == "command":
        results = _run_provider_command(provider["command"], "search", query)
        if not isinstance(results, list):
            raise StreamCliError(f"Provider '{provider_name}' search result must be a JSON array")
        return [{**item, "provider": provider_name} for item in results]

    if provider_type == "static":
        data = _load_static_provider(provider)
        catalog = data.get("catalog", [])
        filtered = []
        for item in catalog:
            title = str(item.get("title", ""))
            if query.lower() in title.lower():
                filtered.append({**item, "provider": provider_name})
        return filtered

    raise StreamCliError(f"Unsupported provider type '{provider_type}' in provider '{provider_name}'")


def streams_for(provider: Dict[str, Any], item_id: str) -> List[Dict[str, Any]]:
    provider_type = provider.get("type")

    if provider_type == "command":
        streams = _run_provider_command(provider["command"], "stream", item_id)
        if not isinstance(streams, list):
            raise StreamCliError("Provider stream result must be a JSON array")
        return streams

    if provider_type == "static":
        data = _load_static_provider(provider)
        return list(data.get("streams", {}).get(item_id, []))

    raise StreamCliError(f"Unsupported provider type '{provider_type}'")


def collect_results(config: Dict[str, Any], query: str, provider_name: Optional[str]) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for provider in config["providers"]:
        if provider_name and provider.get("name") != provider_name:
            continue
        results.extend(search_provider(provider, query))
    return results


def choose_interactive(options: List[str], label: str) -> int:
    if not options:
        raise StreamCliError(f"No {label} available.")

    for idx, option in enumerate(options, start=1):
        print(f"[{idx}] {option}")

    raw = input(f"Choose {label} [1-{len(options)}]: ").strip()
    if not raw.isdigit():
        raise StreamCliError(f"Invalid {label} selection: {raw}")
    chosen = int(raw)
    if chosen < 1 or chosen > len(options):
        raise StreamCliError(f"{label.capitalize()} selection out of range")
    return chosen - 1


def find_provider(config: Dict[str, Any], provider_name: str) -> Dict[str, Any]:
    for provider in config["providers"]:
        if provider.get("name") == provider_name:
            return provider
    raise StreamCliError(f"Unknown provider '{provider_name}'")


def play_stream(player: str, stream: Dict[str, Any], dry_run: bool = False) -> None:
    url = stream.get("url")
    if not url:
        raise StreamCliError("Selected stream does not include a URL")

    command = [player]
    headers = stream.get("headers") or {}
    if headers:
        header_str = ",".join(f"{k}: {v}" for k, v in headers.items())
        command.append(f"--http-header-fields={header_str}")

    command.append(url)

    if dry_run:
        print(" ".join(shlex.quote(part) for part in command))
        return

    process = subprocess.run(command, check=False)
    if process.returncode != 0:
        raise StreamCliError(f"Player exited with non-zero status: {process.returncode}")


def cmd_init(args: argparse.Namespace) -> int:
    path = _expand(args.config)
    init_config(path)
    print(f"Initialized config: {path}")
    return 0


def cmd_providers(args: argparse.Namespace) -> int:
    config = load_config(_expand(args.config))
    for provider in config["providers"]:
        print(f"- {provider.get('name')} ({provider.get('type')})")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    config = load_config(_expand(args.config))
    results = collect_results(config, args.query, args.provider)

    if args.json:
        print(json.dumps(results, indent=2))
        return 0

    if not results:
        print("No matching titles found.")
        return 0

    for idx, item in enumerate(results, start=1):
        title = item.get("title", "Unknown")
        year = item.get("year", "?")
        media_type = item.get("type", "unknown")
        provider = item.get("provider", "unknown")
        print(f"[{idx}] {title} ({year}) [{media_type}] via {provider}")

    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    config = load_config(_expand(args.config))
    results = collect_results(config, args.query, args.provider)
    if not results:
        raise StreamCliError("No matching titles found.")

    if args.index is not None:
        result_index = args.index - 1
        if result_index < 0 or result_index >= len(results):
            raise StreamCliError("Title index out of range")
    else:
        readable = [f"{r.get('title', 'Unknown')} ({r.get('year', '?')}) via {r.get('provider', 'unknown')}" for r in results]
        result_index = choose_interactive(readable, "title")

    selected = results[result_index]
    provider = find_provider(config, selected["provider"])
    item_id = selected.get("id")
    if not item_id:
        raise StreamCliError("Selected title does not contain provider item id")

    streams = streams_for(provider, item_id)
    if not streams:
        raise StreamCliError("No streams available for the selected title")

    if args.stream_index is not None:
        stream_index = args.stream_index - 1
        if stream_index < 0 or stream_index >= len(streams):
            raise StreamCliError("Stream index out of range")
    else:
        readable_streams = [s.get("name", s.get("url", "unnamed")) for s in streams]
        stream_index = choose_interactive(readable_streams, "stream")

    chosen_stream = streams[stream_index]
    play_stream(config["player"], chosen_stream, dry_run=args.dry_run)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stream-cli",
        description="Search, stream, and play movies/shows from configurable providers.",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to config JSON (default: ~/.config/stream-cli/config.json)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create a starter config and demo provider file")
    init_parser.set_defaults(func=cmd_init)

    providers_parser = subparsers.add_parser("providers", help="List configured providers")
    providers_parser.set_defaults(func=cmd_providers)

    search_parser = subparsers.add_parser("search", help="Search movies/shows across providers")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--provider", help="Use only one configured provider")
    search_parser.add_argument("--json", action="store_true", help="Return raw JSON results")
    search_parser.set_defaults(func=cmd_search)

    watch_parser = subparsers.add_parser("watch", help="Search and play selected movie/show")
    watch_parser.add_argument("query", help="Search query")
    watch_parser.add_argument("--provider", help="Use only one configured provider")
    watch_parser.add_argument("--index", type=int, help="1-based title index from search results")
    watch_parser.add_argument("--stream-index", type=int, help="1-based stream index")
    watch_parser.add_argument("--dry-run", action="store_true", help="Print player command instead of running it")
    watch_parser.set_defaults(func=cmd_watch)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return args.func(args)
    except StreamCliError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
