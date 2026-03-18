---
description: Testing conventions for MarketMeNow test suite
globs: tests/**/*.py
alwaysApply: false
---

# Testing Conventions

## Framework

- pytest + pytest-asyncio with `asyncio_mode = "auto"`.
- Async tests are plain `async def test_...` -- no decorator needed.
- `from __future__ import annotations` in every test file.

## Patterns

- Use `pytest.raises(ExceptionType)` for expected exceptions, never try/except.
- Use `tmp_path` fixture for any file-system tests (YAML, CSV, templates).
- Assert on specific fields, not full model equality, to avoid brittle
  UUID/datetime comparisons.
- No mocking of Pydantic validation -- test it directly with
  `pytest.raises(ValidationError)`.

## Mocks and Fixtures

- Mock adapters implement Protocol interfaces via structural subtyping.
  Never subclass or inherit from the Protocol.
- Content model factories live in `conftest.py` (e.g. `make_text_post()`,
  `make_video()`). Prefer these over inline construction in tests.
- A pre-built `AdapterRegistry` fixture is available in `conftest.py`.

## Naming

- Files: `test_{module}.py` matching the source module under test.
- Functions: `test_{module}_{behavior}` (e.g. `test_normaliser_video_with_thumbnail`).

## No External I/O

- Tests must never call external APIs, send emails, or launch browsers.
- All network and I/O dependencies are replaced with in-memory mocks.
