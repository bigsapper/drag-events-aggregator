# TODO — Productionization

This project currently assumes a manual, on-demand operating model.
Items related to CI, scheduled execution, and automated notifications are parked unless that changes later.

## Architecture — Crawl Strategy Scalability

Aggregator crawl strategies have already been extracted into dedicated modules under
`src/drag_events/crawl/strategies/`. The remaining coupling is registration: adding a new strategy still
requires modifying `src/drag_events/crawl/__init__.py` to import it and add it to `STRATEGY_MAP`.

- [ ] Add dynamic strategy registration/loading so new aggregator strategies can be added without editing `src/drag_events/crawl/__init__.py`
- [ ] Improve the manual flyer intake workflow:
  flyer sourcing still happens outside this project, but staged intake now syncs from the configured Google Drive folder into `flyers/` for local processing. The remaining work is to refine the operator process around that upstream sourcing workflow.

## Production Follow-Up

- [ ] Detect actual image MIME type from file contents before sending images to Claude instead of trusting the file extension
- [ ] Downscale or recompress oversized images before Claude submission so images over the 5 MB limit do not fail extraction
- [ ] Tighten generic image-crawl filtering so logos, sponsor graphics, maps, and other non-flyer assets are less likely to enter the extraction queue
- [ ] Tighten text-listing filtering so site chrome, navigation labels, and editorial/news content are not treated as event listings
- [ ] Review and improve event matching/merge logic to reduce false merges between loosely related records
- [ ] Investigate and fix the text-listing failure seen during production crawl: `'str' object has no attribute 'get'`

## Data Quality

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
