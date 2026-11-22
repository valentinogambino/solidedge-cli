set windows-shell := ["powershell.exe", "-NoProfile", "-Command"]

test:
    uv run pytest

lint:
    uv run ruff check .

fmt:
    uv run ruff format .
