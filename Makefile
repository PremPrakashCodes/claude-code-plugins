.PHONY: test lint format format-check check clean

# Every plugin with a pyproject.toml. Narrow to one with `make test PLUGINS=plugins/status-line`.
PLUGINS ?= $(patsubst %/pyproject.toml,%,$(wildcard plugins/*/pyproject.toml))
PYTHON ?= python3

test:
	@set -e; for dir in $(PLUGINS); do \
		echo "==> $$dir: tests"; \
		(cd $$dir && $(PYTHON) -m unittest discover -s tests); \
	done

lint:
	@set -e; for dir in $(PLUGINS); do \
		echo "==> $$dir: ruff check"; \
		(cd $$dir && ruff check .); \
	done

format:
	@set -e; for dir in $(PLUGINS); do \
		echo "==> $$dir: ruff format"; \
		(cd $$dir && ruff format .); \
	done

format-check:
	@set -e; for dir in $(PLUGINS); do \
		echo "==> $$dir: ruff format --check"; \
		(cd $$dir && ruff format --check .); \
	done

check: test lint format-check

clean:
	find . -type d \( -name __pycache__ -o -name .ruff_cache -o -name .mypy_cache -o -name .pytest_cache \) -prune -exec rm -rf {} +
