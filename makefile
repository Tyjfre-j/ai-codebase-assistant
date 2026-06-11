.PHONY: dev test lint typecheck clean

dev:
	uvicorn app.main:app --reload --reload-dir app

test:
	pytest tests/ -v

lint:
	ruff check app/

typecheck:
	mypy app/

clean:
	powershell -Command "Get-ChildItem -Path . -Recurse -Force | Where-Object { $$_.PSIsContainer -and $$_.Name -in '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache' } | Remove-Item -Recurse -Force"