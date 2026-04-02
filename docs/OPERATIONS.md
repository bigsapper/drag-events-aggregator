# Operations

## Configuration Files

| File | Purpose |
|---|---|
| `src/drag_events/config/flyer_sources.json` | Google Drive folder used for staged manual flyer intake |
| `src/drag_events/config/tracks.json` | Individual track websites to crawl (generic image scraper) |
| `src/drag_events/config/sources.json` | Aggregator sites with custom scraping strategies (RacingJunk, Bracketraces, RSS, etc.) |
| `src/drag_events/config/track_aliases.json` | Alternate track names mapped to canonical names for deduplication and normalization |

`tracks.json` and `sources.json` entries may include `"enabled": false` to disable a specific site without deleting its configuration. Omitted `enabled` values default to `true`.

`sources.json` entries may also include these optional per-site settings:
- `request_headers`: extra HTTP headers merged into the default crawler headers
- `page_delay_seconds`: override the delay between paginated or sequential source requests
- `max_pages`: override pagination depth for strategies that page through result sets, such as `racingjunk`

## Secrets

The runtime supports these Anthropic API key sources:

- a repo-local `.env` file containing `ANTHROPIC_API_KEY=...`
- `ANTHROPIC_API_KEY`: inject the key directly into the process environment
- `ANTHROPIC_API_KEY_FILE`: point to a file outside the repo whose contents are the key

Examples:

```bash
printf '%s\n' 'ANTHROPIC_API_KEY=your_api_key_here' > .env

export ANTHROPIC_API_KEY="your_api_key_here"
export ANTHROPIC_API_KEY_FILE="/path/to/anthropic_api_key"
```

Resolution order is:
1. `ANTHROPIC_API_KEY`
2. `ANTHROPIC_API_KEY_FILE`
3. repo-local `.env` with `ANTHROPIC_API_KEY=...`

## Crawl + Extract

```bash
# Crawl all tracks and all aggregator sources
make crawl

# Show historical runtime summary from recorded crawl metrics
make crawl-metrics

# Crawl all tracks and all aggregator sources
PYTHONPATH=src python -m drag_events.crawl

# Crawl track websites only
make crawl-tracks

# Crawl track websites only
PYTHONPATH=src python -m drag_events.crawl --tracks

# Crawl aggregator sources only
make crawl-sources

# Crawl aggregator sources only
PYTHONPATH=src python -m drag_events.crawl --sources

# Crawl a specific track by name
make crawl-track NAME="Texas Motorplex"

# Crawl a specific track by name
PYTHONPATH=src python -m drag_events.crawl --track "Texas Motorplex"

# Crawl a specific aggregator source by name
make crawl-source NAME="Bracketraces.com"

# Crawl a specific aggregator source by name
PYTHONPATH=src python -m drag_events.crawl --source "Bracketraces.com"
```

Crawling automatically triggers extraction and deduplication for any newly downloaded flyers.
Each crawl run also records timing and count metrics to `runtime/tracing/crawl_metrics.jsonl` and refreshes a summary snapshot in `runtime/tracing/crawl_metrics_summary.json`.
Retry telemetry for transient HTTP failures and Claude API failures is included in the recorded crawl metrics for each live run.
Recoverable and fatal crawl errors from live runs are appended to `runtime/tracing/crawl_errors.log`.

## Manual Processing

```bash
# Sync staged flyer images from Google Drive into flyers/
make sync-flyers

# Sync staged flyer images, then process the flyers/ staging directory
make sync-flyers
make process PATHS="flyers"

# Process one or more flyer paths manually
make process PATHS="path/to/flyer.jpg"

# Process a single flyer image
PYTHONPATH=src python -m drag_events.process path/to/flyer.jpg

# Process all images in a directory
PYTHONPATH=src python -m drag_events.process path/to/flyers/

# Process multiple specific files
PYTHONPATH=src python -m drag_events.process flyer1.jpg flyer2.png
```

## Reset Workflow

```bash
# Archive the current dist/events.json without resetting anything else
make archive-events

# Archive dist/events.json, clear flyers/, reinitialize crawl state, and reinitialize dist/events.json
make fresh-start
```

`make fresh-start` creates timestamped backups in `dist/archive/` using the pattern `events-YYYYMMDD-HHMMSS.json`.
It also clears `runtime/state/flyer_sync_state.json`, so Google Drive-staged flyers become eligible for download again.

## Development

```bash
pip install -r requirements-dev.txt
make test
make coverage
pytest
```

Tests use mocked Claude API calls and temporary file system paths, so no API key is needed to run them.

Logging uses the Python `logging` module and defaults to `INFO` level output. You can override the verbosity with `DRAG_EVENTS_LOG_LEVEL`, for example:

```bash
DRAG_EVENTS_LOG_LEVEL=DEBUG make crawl
```

Persistent application logging is off by default. To enable it, set `DRAG_EVENTS_LOG_TO_FILE=1`.
The default file path is `runtime/tracing/drag_events.log`, and you can override it with `DRAG_EVENTS_LOG_FILE`.

```bash
DRAG_EVENTS_LOG_TO_FILE=1 make crawl
DRAG_EVENTS_LOG_TO_FILE=1 DRAG_EVENTS_LOG_FILE=runtime/tracing/custom.log make crawl
```

## Test Flyers

`tests/test-flyers/` contains sample flyers for local validation and unit testing. Files in this directory are never deleted after processing.

## Runtime Files

| File/Dir | Purpose |
|---|---|
| `.venv/` | Python virtual environment |
| `flyers/` | Temporary flyer staging area for crawled images and Google Drive-synced manual intake (auto-deleted after successful processing) |
| `dist/archive/` | Archived `dist/events.json` snapshots created during reset workflows |
| `runtime/` | Operational state and telemetry for crawls |
| `runtime/state/crawl_state.json` | Crawl state (seen URLs, known listings); checked in and resettable |
| `runtime/state/flyer_sync_state.json` | Google Drive flyer sync state (already staged file ids); checked in and resettable |
| `runtime/tracing/drag_events.log` | Optional persistent application log when `DRAG_EVENTS_LOG_TO_FILE=1` is enabled |
| `runtime/tracing/crawl_errors.log` | Persistent crawl error log for troubleshooting failed runs |
| `runtime/tracing/crawl_metrics.jsonl` | Historical crawl run metrics used for runtime estimation |
| `runtime/tracing/crawl_metrics_summary.json` | Latest aggregate timing summary |
| `dist/events.json` | Extracted event database |
