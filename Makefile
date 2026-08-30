.PHONY: run test lint format typecheck check clean

run:
	uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest tests/ -v --cov=backend --cov-report=term-missing --cov-fail-under=70

# Same paths as .github/workflows/ci.yml — when these drift, `make check` passes locally
# and CI fails on a file the Makefile never looked at.
lint:
	ruff check backend/ tests/ eval/

format:
	ruff format backend/ tests/ eval/

typecheck:
	mypy backend/

# `format` rewrites files; CI runs `ruff format --check`. Both are here so `make check`
# covers every gate CI enforces, in the same order.
check: lint format typecheck test

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
