# MarketMeNow — Agent Guide

MarketMeNow is a cross-platform marketing automation framework (Python 3.12+, async, ports-and-adapters architecture). It generates and publishes content across Instagram, Twitter/X, Reddit, LinkedIn, YouTube, and Email via a CLI (`mmn`) and a FastAPI web dashboard.

## Quick Reference

```bash
uv sync                              # Install deps
uv run --extra dev pytest             # Test
uv run ruff check src/ tests/        # Lint
uv run ruff format src/ tests/       # Format
uv run mmn --help                    # CLI
uv run mmn workflows                 # List marketing workflows
uv run mmn run <workflow> [OPTIONS]  # Run a workflow
uv run mmn project add <slug>      # Create project (onboarding wizard)
uv run mmn project list             # List projects
uv run mmn project use <slug>       # Switch active project
uv run mmn auth <platform>           # Authenticate
uv run mmn-web                       # Web dashboard (localhost:8000)
```

## Architecture Invariants

- **`src/marketmenow/`** is platform-agnostic. It must never import platform SDKs or adapter code (except lazy imports in `core/registry_builder.py`, `core/workflow_registry.py`, and `steps/`).
- **`src/adapters/`** contains all platform-specific logic. Adapter packages are independent and must not import from each other.
- All adapter interfaces are `typing.Protocol` with `@runtime_checkable` — use structural subtyping, never ABC inheritance.
- All data models are Pydantic `BaseModel` with `frozen=True` — mutate via `model_copy(update={...})`.

## Agent Config Locations

| Tool        | Config                                                        |
|-------------|---------------------------------------------------------------|
| Claude Code | `CLAUDE.md` (root) + `src/marketmenow/CLAUDE.md`, `src/adapters/CLAUDE.md`, `src/web/CLAUDE.md` |
| Cursor      | `.cursor/rules/marketmenow.mdc` (always), `.cursor/rules/testing.mdc` (tests), `.cursor/rules/adapters.mdc` (adapters), `.cursor/rules/web.mdc` (web), `.cursor/rules/core.mdc` (core pipeline) |

## Key Files

| File                                    | Purpose                                    |
|-----------------------------------------|--------------------------------------------|
| `src/marketmenow/ports/*.py`            | Protocol definitions (adapter interfaces)  |
| `src/marketmenow/registry.py`           | `PlatformBundle` + `AdapterRegistry`       |
| `src/marketmenow/core/pipeline.py`      | Content pipeline (normalise → render → upload → publish) |
| `src/marketmenow/core/registry_builder.py` | Auto-registers adapters from env vars   |
| `src/marketmenow/core/workflow.py`      | `WorkflowStep` protocol, `WorkflowContext`, `Workflow` runner |
| `src/marketmenow/core/workflow_registry.py` | `WorkflowRegistry` + `build_workflow_registry()` |
| `src/marketmenow/steps/*.py`            | Reusable workflow steps (generate, post, discover, etc.) |
| `src/marketmenow/workflows/*.py`        | Built-in workflow definitions              |
| `src/marketmenow/models/content.py`     | Content modalities and data models         |
| `src/marketmenow/models/project.py`       | `ProjectConfig`, `BrandConfig`, `TargetCustomer`, `PersonaConfig` |
| `src/marketmenow/core/project_manager.py` | `ProjectManager` — CRUD, path resolution, scaffolding |
| `src/marketmenow/core/onboarding.py`      | 10-phase interactive project onboarding wizard |
| `src/marketmenow/core/project_templates.py`| Generate starter prompts, targets, campaigns |
| `projects/`                                | Per-product marketing material directories |
| `src/marketmenow/normaliser.py`         | `NormalisedContent` + `ContentNormaliser`  |
| `src/marketmenow/cli.py`               | Main CLI entry point (+ hidden adapter CLI aliases for web frontend) |
| `campaigns/*.yaml`                     | YAML campaign config files (e.g. reddit-launch) |
| `src/web/app.py`                        | FastAPI app                                |
| `src/web/cli_runner.py`                | Subprocess runner + progress parsing       |
| `tests/conftest.py`                     | Mock adapters and content factories        |
| `pyproject.toml`                        | All deps, scripts, ruff, pytest config     |
| `.env.example`                          | Required environment variables             |

## Style

Python >= 3.12. `from __future__ import annotations` in every file. Full type annotations, no `Any`. Async-first adapters. Tests use pytest + pytest-asyncio (`asyncio_mode = "auto"`), never call external APIs.
