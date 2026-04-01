PYTHON = .venv/bin/python
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
	@printf "  make process PATHS=\"...\"      Process one or more flyer paths manually\n"
	@printf "  make crawl-metrics           Show historical crawl timing summary\n"
	@printf "  make archive-events          Archive dist/events.json with a timestamp\n"
	@printf "  make fresh-start             Archive events, clear flyers, reset crawl state, empty dist/events.json\n"

test:
	$(PYTHON) -m pytest

coverage:
	$(PYTHON) -m pytest --cov-report=html && open htmlcov/index.html

crawl:
	$(PYTHON) crawl.py

crawl-tracks:
	$(PYTHON) crawl.py --tracks

crawl-sources:
	$(PYTHON) crawl.py --sources

crawl-track:
	@if [ -z "$(NAME)" ]; then echo 'Usage: make crawl-track NAME="Texas Motorplex"'; exit 1; fi
	$(PYTHON) crawl.py --track "$(NAME)"

crawl-source:
	@if [ -z "$(NAME)" ]; then echo 'Usage: make crawl-source NAME="Bracketraces.com"'; exit 1; fi
	$(PYTHON) crawl.py --source "$(NAME)"

process:
	@if [ -z "$(PATHS)" ]; then echo 'Usage: make process PATHS="path/to/flyer.jpg [more paths...]"'; exit 1; fi
	$(PYTHON) process.py $(PATHS)

crawl-metrics:
	$(PYTHON) crawl.py --metrics

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
	@mkdir -p flyers dist
	@rm -f .crawl_state.json
	@find flyers -type f -delete
	@printf "[]\n" > dist/events.json
	@echo "Reset complete: cleared flyers/, removed .crawl_state.json, and reinitialized dist/events.json"

.PHONY: help test coverage crawl crawl-tracks crawl-sources crawl-track crawl-source process crawl-metrics archive-events fresh-start
