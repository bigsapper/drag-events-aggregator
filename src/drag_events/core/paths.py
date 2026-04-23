from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[3]
SRC_DIR = BASE_DIR / "src" / "drag_events"
CONFIG_DIR = SRC_DIR / "config"
DIST_DIR = BASE_DIR / "dist"
RUNTIME_DIR = BASE_DIR / "runtime"
STATE_DIR = RUNTIME_DIR / "state"
TRACING_DIR = RUNTIME_DIR / "tracing"
FLYERS_DIR = BASE_DIR / "flyers"

TRACKS_FILE = CONFIG_DIR / "tracks.json"
SOURCES_FILE = CONFIG_DIR / "sources.json"
TRACK_ALIASES_FILE = CONFIG_DIR / "track_aliases.json"
TRACK_CATALOG_FILE = CONFIG_DIR / "track_catalog.json"
FLYER_SOURCES_FILE = CONFIG_DIR / "flyer_sources.json"

EVENTS_FILE = DIST_DIR / "events.json"
EVENTS_SCHEMA_FILE = DIST_DIR / "events.schema.json"

CRAWL_STATE_FILE = STATE_DIR / "crawl_state.json"
FLYER_SYNC_STATE_FILE = STATE_DIR / "flyer_sync_state.json"

CRAWL_METRICS_LOG_FILE = TRACING_DIR / "crawl_metrics.jsonl"
CRAWL_METRICS_SUMMARY_FILE = TRACING_DIR / "crawl_metrics_summary.json"
CRAWL_ERROR_LOG_FILE = TRACING_DIR / "crawl_errors.log"
APP_LOG_FILE = TRACING_DIR / "drag_events.log"

PROJECT_ENV_FILE = BASE_DIR / ".env"
