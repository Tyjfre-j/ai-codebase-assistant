.PHONY: dev test lint lint-fix typecheck clean

dev:
	uvicorn app.main:app --reload --reload-dir app

test:
	pytest tests/ -v -s

lint:
	ruff check app/

lint-fix:
	ruff check app/ --fix

typecheck:
	mypy app/

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null; \
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null; \
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null; \
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null