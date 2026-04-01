# TODO — Productionization

## CI/CD
- [ ] Add GitHub Actions workflow to run the test suite automatically on every push and pull request
- [ ] Add a workflow step that validates `dist/events.json` against `dist/events.schema.json` before merge
- [ ] Add a scheduled GitHub Actions workflow to run the crawl automatically (e.g. nightly)
- [ ] Add a workflow step that commits and pushes updated `dist/events.json` back to the repo after a successful scheduled crawl

## Data Quality
- [ ] Initialize `dist/events.json` with an empty array so external consumers always find a valid file
- [ ] Define and enforce a minimum confidence threshold — exclude or flag events below it
- [ ] Implement stale event cleanup — archive or remove events whose dates have passed

## Observability
- [ ] Replace `print()` statements with structured logging (`logging` module) with configurable log levels
- [ ] Add log file output for headless/scheduled runs
- [ ] Add failure alerting for crawl errors and Claude API failures

## Resilience
- [ ] Add retry logic for transient HTTP failures during crawling
- [ ] Add retry logic for transient Claude API failures during extraction
- [ ] Persist `.crawl_state.json` in a location that survives across CI runner environments (e.g. commit it, or store in a remote cache)

## Architecture — Crawl Strategy Scalability
Adding aggregator sources with unique page structures currently requires modifying `crawl.py` directly
(new function + `STRATEGY_MAP` entry). This is manageable at the current scale but will become a
maintenance burden as more aggregators are added.

- [ ] Extract each crawl strategy into its own file (e.g. `strategies/racingjunk.py`) loaded dynamically, so adding a new aggregator no longer requires editing `crawl.py`
- [ ] Add per-site configuration support in `sources.json` for rate limits, custom headers, and pagination depth (currently hardcoded constants)
- [ ] Add an `enabled` flag to `tracks.json` and `sources.json` entries so individual sites can be disabled without editing code
- [ ] Add schema validation for `tracks.json` and `sources.json` at startup so malformed entries fail fast with a clear error

## Security
- [ ] Replace `.env` file pattern with proper secrets injection for production (CI secrets, AWS Secrets Manager, or equivalent)
