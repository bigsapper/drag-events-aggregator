# TODO — Productionization

This project currently assumes a manual, on-demand operating model.
Items related to CI, scheduled execution, and automated notifications are parked unless that changes later.

## Architecture — Crawl Strategy Scalability

Aggregator crawl strategies have already been extracted into dedicated modules under
`src/drag_events/strategies/`. The remaining coupling is registration: adding a new strategy still
requires modifying `crawl.py` to import it and add it to `STRATEGY_MAP`.

- [ ] Add dynamic strategy registration/loading so new aggregator strategies can be added without editing `crawl.py`
- [ ] Implement a process to automate searching for event flyers and downloading them for subsequent extraction and deduplication

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
