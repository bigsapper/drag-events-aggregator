# Operations

## Configuration Files

| File | Purpose |
|---|---|
| `src/drag_events/config/tracks.json` | Individual track websites to crawl (generic image scraper) |
| `src/drag_events/config/sources.json` | Aggregator sites with custom scraping strategies (RacingJunk, Bracketraces, RSS, etc.) |
| `src/drag_events/config/track_aliases.json` | Alternate track names mapped to canonical names for deduplication and normalization |

`tracks.json` and `sources.json` entries may include `"enabled": false` to disable a specific site without deleting its configuration. Omitted `enabled` values default to `true`.

`sources.json` entries may also include these optional per-site settings:
- `request_headers`: extra HTTP headers merged into the default crawler headers
- `page_delay_seconds`: override the delay between paginated or sequential source requests
- `max_pages`: override pagination depth for strategies that page through result sets, such as `racingjunk`

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

## Development

```bash
pip install -r requirements-dev.txt
make test
make coverage
pytest
```

Tests use mocked Claude API calls and temporary file system paths, so no API key is needed to run them.

## Test Flyers

`tests/test-flyers/` contains sample flyers for local validation and unit testing. Files in this directory are never deleted after processing.

## Runtime Files

| File/Dir | Purpose |
|---|---|
| `.env` | Your API key |
| `.venv/` | Python virtual environment |
| `flyers/` | Downloaded flyer images (auto-deleted after successful processing) |
| `dist/archive/` | Archived `dist/events.json` snapshots created during reset workflows |
| `runtime/` | Operational state and telemetry for crawls |
| `runtime/state/crawl_state.json` | Crawl state (seen URLs, known listings); checked in and resettable |
| `runtime/tracing/crawl_errors.log` | Persistent crawl error log for troubleshooting failed runs |
| `runtime/tracing/crawl_metrics.jsonl` | Historical crawl run metrics used for runtime estimation |
| `runtime/tracing/crawl_metrics_summary.json` | Latest aggregate timing summary |
| `dist/events.json` | Extracted event database |
