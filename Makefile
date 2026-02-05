.PHONY: lint lint-fix format format-check test setup

# Ensure venv exists and has dev deps
setup:
	@if [ ! -d ".venv" ]; then python3.13 -m venv .venv; fi
	@.venv/bin/pip install -q -e ".[dev]"

# Run linter (installs ruff if needed)
lint: setup
	.venv/bin/ruff check src/ tests/

# Run linter with auto-fix
lint-fix: setup
	.venv/bin/ruff check src/ tests/ --fix

# Format code
format: setup
	.venv/bin/ruff format src/ tests/

# Check formatting without changes
format-check: setup
	.venv/bin/ruff format --check src/ tests/

# Run tests
test: setup
	.venv/bin/pytest tests/ -v
