PYTHON = .venv/bin/python
PYTHONPATH_RUN = PYTHONPATH=src
MAKEFLAGS += --no-builtin-rules
.DEFAULT_GOAL := help

help:
	@printf "Available targets:\n"
	@printf "  make test                    Run the pytest suite\n"
	@printf "  make coverage                Run tests with HTML coverage output\n"
	@printf "  make crawl                   Crawl all tracks and sources, then extract and dedup\n"
	@printf "  make crawl-tracks            Crawl track websites only\n"
	@printf "  make crawl-sources           Crawl aggregator sources only\n"
	@printf "  make crawl-track NAME=\"...\"   Crawl one track by name\n"
	@printf "  make crawl-source NAME=\"...\"  Crawl one source by name\n"
	@printf "  make sync-flyers             Download staged flyer images from the configured Google Drive folder\n"
	@printf "  make process PATHS=\"...\"      Process one or more flyer paths manually\n"
	@printf "  make crawl-metrics           Show historical crawl timing summary\n"
	@printf "  make archive-events          Archive dist/events.json with a timestamp\n"
	@printf "  make fresh-start             Archive events, clear flyers, reset crawl state, empty dist/events.json\n"

test:
	$(PYTHON) -m pytest

coverage:
	$(PYTHON) -m pytest --cov-report=html
	@if command -v xdg-open >/dev/null 2>&1; then \
		xdg-open htmlcov/index.html; \
	elif command -v open >/dev/null 2>&1; then \
		open htmlcov/index.html; \
	else \
		echo "HTML coverage report generated at htmlcov/index.html"; \
	fi

crawl:
	$(PYTHONPATH_RUN) $(PYTHON) -m drag_events.crawl

crawl-tracks:
	$(PYTHONPATH_RUN) $(PYTHON) -m drag_events.crawl --tracks

crawl-sources:
	$(PYTHONPATH_RUN) $(PYTHON) -m drag_events.crawl --sources

crawl-track:
	@if [ -z "$(NAME)" ]; then echo 'Usage: make crawl-track NAME="Texas Motorplex"'; exit 1; fi
	$(PYTHONPATH_RUN) $(PYTHON) -m drag_events.crawl --track "$(NAME)"

crawl-source:
	@if [ -z "$(NAME)" ]; then echo 'Usage: make crawl-source NAME="Bracketraces.com"'; exit 1; fi
	$(PYTHONPATH_RUN) $(PYTHON) -m drag_events.crawl --source "$(NAME)"

sync-flyers:
	$(PYTHONPATH_RUN) $(PYTHON) -m drag_events.flyer_sync

process:
	@if [ -z "$(PATHS)" ]; then echo 'Usage: make process PATHS="path/to/flyer.jpg [more paths...]"'; exit 1; fi
	$(PYTHONPATH_RUN) $(PYTHON) -m drag_events.process $(PATHS)

crawl-metrics:
	$(PYTHONPATH_RUN) $(PYTHON) -m drag_events.crawl --metrics

archive-events:
	@mkdir -p dist/archive
	@if [ -f dist/events.json ]; then \
		ts=$$(date +"%Y%m%d-%H%M%S"); \
		cp dist/events.json "dist/archive/events-$${ts}.json"; \
		echo "Archived dist/events.json -> dist/archive/events-$${ts}.json"; \
	else \
		echo "No dist/events.json found to archive"; \
	fi

fresh-start: archive-events
	@mkdir -p flyers dist runtime runtime/state runtime/tracing
	@printf '{\n  "seen_urls": [],\n  "racingjunk_events": [],\n  "myracepass_events": [],\n  "tmccc_events": []\n}\n' > runtime/state/crawl_state.json
	@printf '{\n  "downloaded_drive_file_ids": []\n}\n' > runtime/state/flyer_sync_state.json
	@find flyers -type f -delete
	@printf "[]\n" > dist/events.json
	@echo "Reset complete: cleared flyers/, reinitialized runtime/state/*.json, and reinitialized dist/events.json"

.PHONY: help test coverage crawl crawl-tracks crawl-sources crawl-track crawl-source sync-flyers process crawl-metrics archive-events fresh-start
