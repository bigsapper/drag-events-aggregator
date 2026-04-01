# TODO — Productionization

This project currently assumes a manual, on-demand operating model.
Items related to CI, scheduled execution, and automated notifications are parked unless that changes later.

## Active Priorities

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

### Observability
- [x] Replace `print()` statements with structured logging (`logging` module) with configurable log levels

## Deferred

### Data Quality
These items are intentionally deferred for now. The current project direction does not require
implementing them immediately, but the design considerations below should be preserved.

- [ ] Define and enforce a minimum confidence threshold — exclude or flag events below it
- [ ] Implement stale event cleanup — archive or remove events whose dates have passed

Notes on stale event cleanup:
- First decide whether `dist/events.json` is intended to be a live upcoming-events feed, a historical archive, or a hybrid.
- If `dist/events.json` is treated as a live feed, stale cleanup is useful so downstream consumers do not have to filter past events themselves.
- If the project should retain history, hard deletion is probably the wrong behavior; status-based retention or archival is safer.
- The recommended direction discussed so far is a hybrid:
  keep `dist/events.json` focused on current/upcoming events while archiving past events instead of deleting them permanently.
- A practical stale rule would use `dates.end` when present, otherwise `dates.start`, with an optional short grace period after the event.
- If this is implemented later, the preferred behavior discussed was:
  automatic cleanup during crawl, removal from `dist/events.json`, and preservation in an archive-oriented output for historical reference.

## Parked

### CI / Automation
- [ ] Add GitHub Actions workflow to run the test suite automatically on every push and pull request
- [ ] Add a workflow step that validates `dist/events.json` against `dist/events.schema.json` before merge
- [ ] Add a scheduled GitHub Actions workflow to run the crawl automatically (e.g. nightly)
- [ ] Add a workflow step that commits and pushes updated `dist/events.json` back to the repo after a successful scheduled crawl

### Automated Operations
- [ ] Add failure alerting for crawl errors and Claude API failures
- [ ] Persist `runtime/state/crawl_state.json` in a location that survives across CI runner environments (e.g. commit it, or store in a remote cache)
