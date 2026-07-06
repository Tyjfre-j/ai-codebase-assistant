.PHONY: dev test lint lint-fix typecheck clean

dev:
	uv run uvicorn app.main:app --reload --reload-dir app

test:
	uv run pytest tests/ -v -s

lint:
	uv run ruff check app/

lint-fix:
	uv run ruff check app/ --fix

typecheck:
	uv run mypy app/

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null; \
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null; \
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null; \
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null