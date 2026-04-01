# Operations

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

## Crawl + Extract

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

## Manual Processing

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

## Reset Workflow

```bash
# Archive the current dist/events.json without resetting anything else
make archive-events

# Archive dist/events.json, clear flyers/, remove crawl state, and reinitialize dist/events.json
make fresh-start
```

`make fresh-start` creates timestamped backups in `dist/archive/` using the pattern `events-YYYYMMDD-HHMMSS.json`.

## Development

```bash
pip install -r requirements-dev.txt
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
