.PHONY: help install dev upgrade check ci clean

UV := uv
PYTHON := $(UV) run python

help:
	@echo "Targets:"
	@echo "  install   Create venv and install dependencies"
	@echo "  dev       Run the full pipeline (optional: IDENTIFIER=account_number)"
	@echo "  upgrade   Upgrade locked dependencies"
	@echo "  clean     Remove Python build artifacts and caches"
	@echo "  check     Autofix format and lint, then verify (lint, typecheck, tests)"
	@echo "  ci        Check-only: format, lint, typecheck, then test"

install:
	$(UV) venv --allow-existing
	$(UV) lock
	$(UV) sync --group dev

dev:
	$(PYTHON) -m networthcsv $(if $(IDENTIFIER),--identifier $(IDENTIFIER),)

upgrade:
	$(UV) sync --upgrade --group dev

check:
	$(UV) run ruff format src tests
	$(UV) run ruff check --fix src tests
	$(UV) run ruff check src tests
	$(UV) run basedpyright
	$(PYTHON) -m tests

ci:
	$(UV) run ruff format --check src tests
	$(UV) run ruff check src tests
	$(UV) run basedpyright
	$(PYTHON) -m tests

clean:
	/usr/bin/rm -rf build dist .ruff_cache
	if command -v fd >/dev/null 2>&1; then \
		fd -H -I -t d __pycache__ -E .venv -x rm -rf; \
		fd -H -I -t d -g '*.egg-info' -E .venv -x rm -rf; \
		fd -H -I -t f -g '*.pyc' -E .venv -x rm -f; \
	else \
		find . -not -path './.venv' -not -path './.venv/*' -type d -name '__pycache__' -exec rm -rf {} +; \
		find . -not -path './.venv' -not -path './.venv/*' -type d -name '*.egg-info' -exec rm -rf {} +; \
		find . -not -path './.venv' -not -path './.venv/*' -type f -name '*.pyc' -exec rm -f {} +; \
	fi
