.PHONY: help install dev upgrade test lint format ci clean

UV := uv
PYTHON := $(UV) run python

help:
	@echo "Targets:"
	@echo "  install   Create venv and install dependencies"
	@echo "  dev       Run the full pipeline"
	@echo "  upgrade   Upgrade locked dependencies"
	@echo "  clean     Remove Python build artifacts and caches"
	@echo "  test      Run unit tests"
	@echo "  lint      Type-check with basedpyright"
	@echo "  format    Format Python sources with ruff"
	@echo "  ci        Run format, lint, then test"

install:
	$(UV) venv --allow-existing
	$(UV) lock
	$(UV) sync --group dev

dev:
	$(PYTHON) -m networthcsv

upgrade:
	$(UV) sync --upgrade --group dev

test:
	$(PYTHON) -m unittest discover -s tests

lint:
	$(UV) run basedpyright

format:
	$(UV) run ruff format src tests

ci: format lint test

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
