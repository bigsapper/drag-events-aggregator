PYTHON = .venv/bin/python

test:
	$(PYTHON) -m pytest

coverage:
	$(PYTHON) -m pytest --cov-report=html && open htmlcov/index.html

.PHONY: test coverage
