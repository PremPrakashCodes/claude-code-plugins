.PHONY: test lint format format-check check clean

PLUGIN_DIR := plugins/status-line
PYTHON ?= python3

test:
	cd $(PLUGIN_DIR) && $(PYTHON) -m unittest discover -s tests

lint:
	cd $(PLUGIN_DIR) && ruff check .

format:
	cd $(PLUGIN_DIR) && ruff format .

format-check:
	cd $(PLUGIN_DIR) && ruff format --check .

check: test lint format-check

clean:
	find . -type d \( -name __pycache__ -o -name .ruff_cache -o -name .mypy_cache -o -name .pytest_cache \) -prune -exec rm -rf {} +
