PYTHON = .venv/bin/python
PYTHONPATH_RUN = PYTHONPATH=src
MAKEFLAGS += --no-builtin-rules
.DEFAULT_GOAL := help

help:
	@printf "Available targets:\n"
	@printf "  make                         Show this help\n"
	@printf "  make test                    Run the pytest suite\n"
	@printf "  make run                     Single additive full workflow: sync-flyers + crawl + process\n"
	@printf "  make metrics                 Show historical crawl timing summary\n"
	@printf "  make reset                   Archive events, clear flyers, reset runtime state, empty dist/events.json\n"

test:
	$(PYTHON) -m pytest

run:
	$(PYTHONPATH_RUN) $(PYTHON) -m drag_events.flyer_sync
	$(PYTHONPATH_RUN) $(PYTHON) -m drag_events.crawl
	@if find flyers -maxdepth 1 -type f | grep -q .; then \
		$(PYTHONPATH_RUN) $(PYTHON) -m drag_events.process flyers; \
	else \
		echo "No staged flyer images to process."; \
	fi

metrics:
	$(PYTHONPATH_RUN) $(PYTHON) -m drag_events.crawl --metrics

reset:
	@mkdir -p dist/archive
	@if [ -f dist/events.json ]; then \
		ts=$$(date +"%Y%m%d-%H%M%S"); \
		cp dist/events.json "dist/archive/events-$${ts}.json"; \
		echo "Archived dist/events.json -> dist/archive/events-$${ts}.json"; \
	else \
		echo "No dist/events.json found to archive"; \
	fi
	@mkdir -p flyers dist runtime runtime/state runtime/tracing
	@printf '{\n  "seen_urls": [],\n  "racingjunk_events": [],\n  "myracepass_events": [],\n  "tmccc_events": []\n}\n' > runtime/state/crawl_state.json
	@printf '{\n  "downloaded_drive_file_ids": []\n}\n' > runtime/state/flyer_sync_state.json
	@find flyers -type f -delete
	@printf "[]\n" > dist/events.json
	@echo "Reset complete: cleared flyers/, reinitialized runtime/state/*.json, and reinitialized dist/events.json"

.PHONY: help test run metrics reset
