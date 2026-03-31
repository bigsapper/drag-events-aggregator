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
# Clone the repo
git clone https://github.com/bigsapper/drag-events-aggregator.git
cd drag-events-aggregator

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and add your Anthropic API key
```

## Configuration Files

| File | Purpose |
|---|---|
| `tracks.json` | Individual track websites to crawl (generic image scraper) |
| `sources.json` | Aggregator sites with custom scraping strategies (RacingJunk, Bracketraces, RSS, etc.) |

## Usage

### Crawl + Extract (main workflow)

```bash
# Crawl all tracks and all aggregator sources
python crawl.py

# Crawl track websites only
python crawl.py --tracks

# Crawl aggregator sources only
python crawl.py --sources

# Crawl a specific track by name
python crawl.py --track "Texas Motorplex"

# Crawl a specific aggregator source by name
python crawl.py --source "Bracketraces.com"
```

Crawling automatically triggers extraction and deduplication for any newly downloaded flyers.

### Process Flyers Manually

```bash
# Process a single flyer image
python process.py path/to/flyer.jpg

# Process all images in a directory
python process.py path/to/flyers/

# Process multiple specific files
python process.py flyer1.jpg flyer2.png
```

## Output

Results are written to `events.json` — a JSON array of event records with the following structure:

```json
{
  "id": "uuid",
  "title": "Spring Fling",
  "event_type": "bracket",
  "series": "NHRA",
  "track": { "name": "Xtreme Raceway Park", "city": "Ennis", "state": "TX" },
  "dates": { "start": "2025-04-12", "end": "2025-04-13" },
  "times": { "gates_open": "07:00", "registration_opens": "08:00", "race_start": "10:00" },
  "classes": ["Super Pro", "Pro", "Sportsman"],
  "fees": { "entry": "$60/class", "spectator": "$10" },
  "contact": { "phone": "555-1234", "email": null, "website": "https://example.com" },
  "confidence": 0.92,
  "flyers": [{ "file": "flyer-abc123.jpg", "phash": "f3a1...", "processed_at": "2025-03-31T12:00:00Z" }],
  "created_at": "2025-03-31T12:00:00Z",
  "updated_at": "2025-03-31T12:00:00Z"
}
```

## Project Structure

```
drag-events-aggregator/
├── crawl.py          # Web crawler for tracks and aggregator sources
├── extract.py        # Claude vision extraction for flyer images
├── extract_text.py   # Claude text extraction for text-based listings
├── dedup.py          # Perceptual hash and event-level deduplication
├── process.py        # Orchestrates extraction + dedup for flyer files
├── tracks.json       # Track website definitions
├── sources.json      # Aggregator source definitions
├── requirements.txt  # Python dependencies
├── setup.sh          # One-time setup script (Linux/macOS)
└── .env.example      # Environment variable template
```

## Runtime Files (not checked in)

| File/Dir | Purpose |
|---|---|
| `.env` | Your API key |
| `.venv/` | Python virtual environment |
| `flyers/` | Downloaded flyer images |
| `events.json` | Extracted event database |
| `.crawl_state.json` | Crawl state (seen URLs, known listings) |
