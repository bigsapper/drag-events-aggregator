# Drag Events Aggregator

Crawls drag racing track websites and aggregator sources for event flyers, extracts structured event data using Claude AI vision, and stores deduplicated results in a local JSON database.

## How It Works

1. **Crawl** — scrapes track websites and aggregator sources for event flyer images and text listings
2. **Extract** — sends flyer images to Claude vision (Sonnet) or text listings to Claude (Haiku) to extract structured event data
3. **Dedup** — uses perceptual hashing to detect duplicate images and track+date matching to merge repeat flyers for the same event
4. **Store** — writes results to `dist/events.json`

## Prerequisites

- Python 3.10+
- An [Anthropic API key](https://console.anthropic.com/)

## Setup

```bash
git clone https://github.com/bigsapper/drag-events-aggregator.git
cd drag-events-aggregator
bash setup.sh
```

`setup.sh` is a one-time convenience script for Debian/Ubuntu-style environments. It:

- installs `python3-pip` and `python3-venv` with `apt-get`
- creates the project virtual environment at `.venv/`
- installs both `requirements.txt` and `requirements-dev.txt`

Because it uses `sudo apt-get`, you may be prompted for your password. If you are not on a Debian/Ubuntu-based system, create `.venv/` manually and install the requirements yourself instead.

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

## Operations

Operational commands and processing workflows live in [docs/OPERATIONS.md](docs/OPERATIONS.md).

## Output

Results are written to `dist/events.json` — the primary data output of this project, intended for consumption by websites, APIs, and other external services.

The full field reference and JSON Schema contract are documented in [docs/SCHEMA.md](docs/SCHEMA.md).

## Project Structure

```
drag-events-aggregator/
├── dist/
│   ├── archive/           # Timestamped backups created by make archive-events / make fresh-start
│   ├── events.json         # Primary output — drag racing event database
│   └── events.schema.json  # JSON Schema contract for events.json
├── docs/
│   ├── OPERATIONS.md      # Crawl process, manual processing, reset, and development runbook
│   ├── SCHEMA.md          # Human-readable events.json field reference
│   └── TODO.md            # Project backlog and productionization notes
├── runtime/
│   ├── state/
│   │   └── crawl_state.json    # Crawl state (seen URLs, known listings)
│   └── tracing/
│       ├── crawl_errors.log        # Persistent crawl error log for fetch, extraction, and run failures
│       ├── crawl_metrics.jsonl     # One JSON record per crawl run with timings and counts
│       └── crawl_metrics_summary.json # Rolling summary derived from crawl_metrics.jsonl
├── src/
│   └── drag_events/
│       ├── config/
│       │   ├── track_aliases.json # Track alias normalization data
│       │   ├── tracks.json        # Track website definitions
│       │   └── sources.json       # Aggregator source definitions
│       ├── crawl.py            # Web crawler for tracks and aggregator sources
│       ├── extract.py          # Claude vision extraction for flyer images
│       ├── extract_text.py     # Claude text extraction for text-based listings
│       ├── dedup.py            # Perceptual hash and event-level deduplication
│       ├── process.py          # Orchestrates extraction + dedup for flyer files
│       └── schema.py           # Shared Claude tool JSON schema
├── requirements.txt        # Python dependencies
├── requirements-dev.txt    # Dev/test dependencies
├── setup.sh                # One-time setup script for Debian/Ubuntu-style environments
└── .env.example            # Environment variable template
```
