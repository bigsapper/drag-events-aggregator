# TODO — Productionization

This project currently assumes a manual, on-demand operating model.
Items related to CI, scheduled execution, and automated notifications are parked unless that changes later.

## Active Priorities

## Data Quality
- [ ] Define and enforce a minimum confidence threshold — exclude or flag events below it
- [ ] Implement stale event cleanup — archive or remove events whose dates have passed

## Observability
- [ ] Replace `print()` statements with structured logging (`logging` module) with configurable log levels

## Architecture — Crawl Strategy Scalability
Adding aggregator sources with unique page structures currently requires modifying `crawl.py` directly
(new function + `STRATEGY_MAP` entry). This is manageable at the current scale but will become a
maintenance burden as more aggregators are added.

- [ ] Extract each crawl strategy into its own file (e.g. `strategies/racingjunk.py`) loaded dynamically, so adding a new aggregator no longer requires editing `crawl.py`

## Security
- [ ] Replace `.env` file pattern with proper secrets injection for production (CI secrets, AWS Secrets Manager, or equivalent)

## Recently Completed

### Configuration Safety
- [x] Add schema validation for `src/drag_events/config/tracks.json` and `src/drag_events/config/sources.json` at startup so malformed entries fail fast with a clear error
- [x] Add an `enabled` flag to `src/drag_events/config/tracks.json` and `src/drag_events/config/sources.json` entries so individual sites can be disabled without editing code
- [x] Add per-site configuration support in `src/drag_events/config/sources.json` for rate limits, custom headers, and pagination depth (currently hardcoded constants)

### Resilience
- [x] Add retry logic for transient HTTP failures during crawling
- [x] Add retry logic for transient Claude API failures during extraction

## Parked

### CI / Automation
- [ ] Add GitHub Actions workflow to run the test suite automatically on every push and pull request
- [ ] Add a workflow step that validates `dist/events.json` against `dist/events.schema.json` before merge
- [ ] Add a scheduled GitHub Actions workflow to run the crawl automatically (e.g. nightly)
- [ ] Add a workflow step that commits and pushes updated `dist/events.json` back to the repo after a successful scheduled crawl

### Automated Operations
- [ ] Add failure alerting for crawl errors and Claude API failures
- [ ] Persist `runtime/state/crawl_state.json` in a location that survives across CI runner environments (e.g. commit it, or store in a remote cache)
