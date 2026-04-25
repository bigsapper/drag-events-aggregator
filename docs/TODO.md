# TODO — Productionization

This project currently assumes a manual, on-demand operating model.

## Crawl Architecture

- [ ] Add concurrency to the crawl source loop — all operations are I/O-bound (HTTP, Claude API), so `asyncio` or `concurrent.futures.ThreadPoolExecutor` across sources could significantly reduce wall time for large source lists
- [ ] Make Playwright an optional install extra — remove it from the base requirements, document the TMCCC/browser dependency, and raise a clear runtime error when TMCCC crawling is requested without Playwright installed
- [ ] Add dynamic strategy registration/loading so new aggregator strategies can be added without editing `src/drag_events/crawl/cli.py`

## Extraction And Validation

- [ ] Replace the custom JSON Schema validator in `event_validation/` with the `jsonschema` PyPI package — the current implementation is a Draft 7 subset that may miss edge cases and carries ongoing maintenance cost
- [ ] Detect actual image MIME type from file contents before sending images to Claude instead of trusting the file extension
- [ ] Downscale or recompress oversized images before Claude submission so images over the 5 MB limit do not fail extraction

## Intake And Filtering

- [ ] Replace the Google Drive embedded-folder-view HTML parser in `flyer_sync/` with the Drive API v3 (service account or OAuth) — the current approach scrapes `.flip-entry` HTML that Google can change without notice
- [ ] Document the manual flyer intake operating process, including where upstream flyers are sourced, how they enter the configured Google Drive folder, and what checks an operator should perform before running sync/process
- [ ] Tighten generic image-crawl filtering so logos, sponsor graphics, maps, and other non-flyer assets are less likely to enter the extraction queue
- [ ] Tighten text-listing filtering so site chrome, navigation labels, and editorial/news content are not treated as event listings
- [ ] Review and improve event matching/merge logic to reduce false merges between loosely related records
- [ ] Investigate and fix the text-listing failure seen during production crawl: `'str' object has no attribute 'get'`

## Data Quality

- [ ] Define and enforce a minimum confidence threshold — exclude or flag events below it
- [ ] Decide the retention contract for `dist/events.json` — live upcoming-events feed, historical archive, or hybrid
- [ ] Implement stale event cleanup once the retention contract is decided — use `dates.end` when present, otherwise `dates.start`, and preserve removed events in an archive-oriented output if history must be retained

## Operations And Automation

- [ ] Thread source identity through retry telemetry in `core/retry_utils.py` — retry counters are currently global per-run, making it impossible to identify which source is consistently causing retries in `runtime/tracing/crawl_metrics.jsonl`
- [ ] Add failure alerting for crawl errors and Claude API failures
- [ ] Add GitHub Actions workflow to run the test suite automatically on every push and pull request
- [ ] Add a workflow step that validates `dist/events.json` against `dist/events.schema.json` before merge
- [ ] Add a scheduled GitHub Actions workflow to run the crawl automatically (e.g. nightly)
- [ ] Add a workflow step that commits and pushes updated `dist/events.json` back to the repo after a successful scheduled crawl
- [ ] Persist `runtime/state/crawl_state.json` in a location that survives across CI runner environments (e.g. commit it, or store in a remote cache)
