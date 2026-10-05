# stream-cli

Search, stream, and play movies/shows from Linux terminal providers (including debrid-compatible sources) using `mpv`.

## What this does

`stream-cli` is a terminal-first launcher inspired by `ani-cli`, but for movies and shows.

- Search for titles from one or more configured providers
- Pull stream URLs from provider backends (debrid services or any source you control)
- Play selected streams directly in `mpv`

## Requirements

- Linux
- Python 3.9+
- `mpv` installed and available on `PATH`

## Quick start

From the repository root:

```bash
python3 stream_cli.py init
python3 stream_cli.py providers
python3 stream_cli.py search demo
python3 stream_cli.py watch demo --index 1 --stream-index 1 --dry-run
```

The `init` command creates:

- `~/.config/stream-cli/config.json`
- `~/.config/stream-cli/example_provider.json`

## Usage

```text
stream-cli [--config PATH] <command> [...]

Commands:
  init        Create starter config and demo provider file
  providers   List configured providers
  search      Search movies/shows across providers
  watch       Search, select, and play a stream
```

Examples:

```bash
# Search across all providers
python3 stream_cli.py search "the matrix"

# Search only one provider
python3 stream_cli.py search "the matrix" --provider realdebrid

# Print JSON search results
python3 stream_cli.py search "the matrix" --json

# Play by explicit indexes (non-interactive)
python3 stream_cli.py watch "the matrix" --index 1 --stream-index 1

# Preview the mpv command without launching it
python3 stream_cli.py watch "the matrix" --index 1 --stream-index 1 --dry-run
```

## Configuration

Default config path: `~/.config/stream-cli/config.json`

```json
{
  "player": "mpv",
  "providers": [
    {
      "name": "realdebrid",
      "type": "command",
      "command": "python3 /absolute/path/to/rd_provider.py"
    },
    {
      "name": "backup-static",
      "type": "static",
      "path": "~/.config/stream-cli/example_provider.json"
    }
  ]
}
```

### Provider types

#### 1) `command` provider (recommended for debrid)

`stream-cli` executes your command provider twice:

1. `search <query>`
2. `stream <item_id>`

Your provider must print JSON to stdout.

`search` output schema (array):

```json
[
  {
    "id": "unique-item-id",
    "title": "Movie or Episode Name",
    "year": 2025,
    "type": "movie"
  }
]
```

`stream` output schema (array):

```json
[
  {
    "name": "1080p WEB-DL",
    "url": "https://...",
    "headers": {
      "Authorization": "******"
    }
  }
]
```

`headers` is optional and is forwarded to `mpv` via `--http-header-fields`.

This model lets you plug in:

- Real-Debrid / AllDebrid / Premiumize integration scripts
- Self-hosted indexers
- Any custom API source

#### 2) `static` provider

Reads a local JSON file with a small catalog and stream map. Useful for testing and fallback.

## Codebase overview

- `stream_cli.py`: main CLI entrypoint, provider orchestration, playback execution
- `tests/test_stream_cli.py`: focused unit tests for config init, static provider behavior, and provider filtering

## Testing

Run targeted tests:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

## Notes

- This project intentionally leaves provider backend implementation to user-owned scripts so credentials and debrid API logic stay outside this repository.
- Use absolute paths for provider commands/scripts when possible.
