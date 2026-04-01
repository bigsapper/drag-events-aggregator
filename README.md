# Drag Events Aggregator

Crawls drag racing track websites and aggregator sources for event flyers, extracts structured event data using Claude AI vision, and stores deduplicated results in a local JSON database.

## How It Works

1. **Crawl** — scrapes track websites and aggregator sources for event flyer images and text listings
2. **Extract** — sends flyer images to Claude vision (Sonnet) or text listings to Claude (Haiku) to extract structured event data
3. **Dedup** — uses perceptual hashing to detect duplicate images and track+date matching to merge repeat flyers for the same event
4. **Store** — writes results to `events.json`

## Prerequisites

- Python 3.10+
- An [Anthropic API key](https://console.anthropic.com/)

## Setup

```bash
git clone https://github.com/bigsapper/drag-events-aggregator.git
cd drag-events-aggregator
bash setup.sh
```

Then copy `.env.example` to `.env` and add your Anthropic API key:

```bash
cp .env.example .env
```

Activate the virtual environment before running any commands:

```bash
source .venv/bin/activate
```

You can list the available project shortcuts with:

```bash
make
```

## Configuration Files

| File | Purpose |
|---|---|
| `src/config/tracks.json` | Individual track websites to crawl (generic image scraper) |
| `src/config/sources.json` | Aggregator sites with custom scraping strategies (RacingJunk, Bracketraces, RSS, etc.) |

## Usage

### Crawl + Extract (main workflow)

```bash
# Crawl all tracks and all aggregator sources
make crawl

# Show historical runtime summary from recorded crawl metrics
make crawl-metrics

# Crawl all tracks and all aggregator sources
python src/crawl.py

# Crawl track websites only
make crawl-tracks

# Crawl track websites only
python src/crawl.py --tracks

# Crawl aggregator sources only
make crawl-sources

# Crawl aggregator sources only
python src/crawl.py --sources

# Crawl a specific track by name
make crawl-track NAME="Texas Motorplex"

# Crawl a specific track by name
python src/crawl.py --track "Texas Motorplex"

# Crawl a specific aggregator source by name
make crawl-source NAME="Bracketraces.com"

# Crawl a specific aggregator source by name
python src/crawl.py --source "Bracketraces.com"
```

Crawling automatically triggers extraction and deduplication for any newly downloaded flyers.
Each crawl run also records timing and count metrics to `runtime/tracing/crawl_metrics.jsonl` and refreshes a summary snapshot in `runtime/tracing/crawl_metrics_summary.json`.
Recoverable and fatal crawl errors from live runs are appended to `runtime/tracing/crawl_errors.log`.

### Process Flyers Manually

```bash
# Process one or more flyer paths manually
make process PATHS="path/to/flyer.jpg"

# Process a single flyer image
python src/process.py path/to/flyer.jpg

# Process all images in a directory
python src/process.py path/to/flyers/

# Process multiple specific files
python src/process.py flyer1.jpg flyer2.png
```

### Archive + Reset For A Fresh Start

```bash
# Archive the current dist/events.json without resetting anything else
make archive-events

# Archive dist/events.json, clear flyers/, remove crawl state, and reinitialize dist/events.json
make fresh-start
```

`make fresh-start` creates timestamped backups in `dist/archive/` using the pattern `events-YYYYMMDD-HHMMSS.json`.

## Output

Results are written to `dist/events.json` — the primary data output of this project, intended for consumption by websites, APIs, and other external services.

The full field reference and JSON Schema contract are documented in [SCHEMA.md](SCHEMA.md).

## Project Structure

```
drag-events-aggregator/
├── dist/
│   ├── archive/           # Timestamped backups created by make archive-events / make fresh-start
│   ├── events.json         # Primary output — drag racing event database
│   └── events.schema.json  # JSON Schema contract for events.json
├── runtime/
│   ├── state/
│   │   └── crawl_state.json    # Crawl state (seen URLs, known listings)
│   └── tracing/
│       ├── crawl_errors.log        # Persistent crawl error log for fetch, extraction, and run failures
│       ├── crawl_metrics.jsonl     # One JSON record per crawl run with timings and counts
│       └── crawl_metrics_summary.json # Rolling summary derived from crawl_metrics.jsonl
├── src/
│   ├── config/
│   │   ├── track_aliases.json # Track alias normalization data
│   │   ├── tracks.json        # Track website definitions
│   │   └── sources.json       # Aggregator source definitions
│   ├── crawl.py            # Web crawler for tracks and aggregator sources
│   ├── extract.py          # Claude vision extraction for flyer images
│   ├── extract_text.py     # Claude text extraction for text-based listings
│   ├── dedup.py            # Perceptual hash and event-level deduplication
│   ├── process.py          # Orchestrates extraction + dedup for flyer files
│   └── schema.py           # Shared Claude tool JSON schema
├── SCHEMA.md               # Human-readable events.json field reference
├── requirements.txt        # Python dependencies
├── requirements-dev.txt    # Dev/test dependencies
├── setup.sh                # One-time setup script (Linux/macOS)
└── .env.example            # Environment variable template
```

## Development Setup

```bash
pip install -r requirements-dev.txt
```

Run the full test suite:

```bash
pytest
```

Tests use mocked Claude API calls and temporary file system paths — no API key is needed to run them. Coverage is reported automatically; the suite targets >90% across all source files.

## Test Flyers

`tests/test-flyers/` contains sample flyers for local validation and unit testing. Files in this directory are never deleted after processing.

## Runtime Files (not checked in)

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
