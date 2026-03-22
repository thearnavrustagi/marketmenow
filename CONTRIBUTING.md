# Contributing to MarketMeNow

Thanks for your interest in contributing! This guide covers everything you need to get started.

## Development Setup

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- Node.js 18+ (only for Instagram Reels — Remotion video composition)
- Git

### Clone and Install

```bash
git clone https://github.com/Wayground/marketmenow.git
cd marketmenow
uv sync --all-extras
uv run pre-commit install --hook-type pre-push
```

This installs all dependencies including optional ones (LangChain, etc.) and sets up a pre-push Git hook that runs the test suite and linter before every push.

### Verify Installation

```bash
mmn version
mmn platforms
```

## Project Structure

```
src/
├── marketmenow/             # Core framework (platform-agnostic)
│   ├── core/                # Orchestrator, Pipeline, Scheduler
│   ├── models/              # Pydantic data models (content, campaign, result)
│   ├── ports/               # Protocol interfaces for adapters
│   ├── integrations/        # LangChain and other framework integrations
│   ├── cli.py               # Top-level CLI entry point
│   ├── normaliser.py        # Content normalisation layer
│   ├── registry.py          # Adapter registry and PlatformBundle
│   └── exceptions.py        # Framework exception hierarchy
└── adapters/                # Platform-specific implementations
    ├── instagram/           # Instagram adapter (Reels, Carousels)
    └── twitter/             # Twitter/X adapter (Replies, Threads)
```

## Architecture Rules

These rules are enforced to keep the codebase modular and maintainable:

### Strict Boundary: Core vs. Adapters

- **`src/marketmenow/`** (core, models, ports, normaliser, registry) is **platform-agnostic**. It must **never** import any platform SDK, adapter module, or contain any platform-specific branching.
- **`src/adapters/`** contains all platform-specific code. Adapters depend on core, never the other way around.

### Structural Subtyping

Adapter interfaces are defined as `typing.Protocol` with `@runtime_checkable` in `src/marketmenow/ports/`. Never subclass an ABC — use structural subtyping. If your adapter class has the right methods and signatures, it satisfies the protocol automatically.

### Immutable Data Flow

All data models are Pydantic `BaseModel` with `frozen=True`. Never mutate a model instance — use `model_copy(update={...})` to create a modified copy.

## Code Style

| Rule | Details |
|---|---|
| Python version | >= 3.12 |
| Future annotations | `from __future__ import annotations` in every file |
| Data models | Pydantic `BaseModel` with `frozen=True` |
| Adapter interfaces | `typing.Protocol` with `@runtime_checkable` |
| Type annotations | Full annotations everywhere; never use `Any` |
| Async | Adapter methods are `async def` |
| Imports | Absolute imports; no circular dependencies |

## Adding a New Platform

This is the most common type of contribution. The hexagonal architecture makes it clean:

### 1. Create the Adapter Package

```
src/adapters/yourplatform/
├── __init__.py          # create_yourplatform_bundle() factory
├── adapter.py           # PlatformAdapter implementation
├── renderer.py          # ContentRenderer implementation
├── uploader.py          # Uploader implementation
├── settings.py          # pydantic-settings for env vars
└── cli.py               # Typer sub-commands (optional)
```

### 2. Implement the Protocols

Your adapter must satisfy these protocols from `src/marketmenow/ports/`:

**`PlatformAdapter`** — the core platform interface:

```python
from __future__ import annotations

from marketmenow.models.content import ContentModality
from marketmenow.models.result import PublishResult, SendResult
from marketmenow.normaliser import NormalisedContent


class YourPlatformAdapter:
    @property
    def platform_name(self) -> str:
        return "yourplatform"

    def supported_modalities(self) -> frozenset[ContentModality]:
        return frozenset({ContentModality.THREAD, ContentModality.CAROUSEL})

    async def authenticate(self, credentials: dict[str, str]) -> None:
        ...

    async def publish(self, content: NormalisedContent) -> PublishResult:
        ...

    async def send_dm(self, content: NormalisedContent) -> SendResult:
        ...
```

**`ContentRenderer`** — transform normalised content for your platform:

```python
class YourPlatformRenderer:
    @property
    def platform_name(self) -> str:
        return "yourplatform"

    async def render(self, content: NormalisedContent) -> NormalisedContent:
        # Enforce character limits, resize media, add platform metadata
        return content.model_copy(update={...})
```

**`Uploader`** — upload media assets:

```python
from marketmenow.models.content import MediaAsset
from marketmenow.models.result import MediaRef


class YourPlatformUploader:
    @property
    def platform_name(self) -> str:
        return "yourplatform"

    async def upload(self, asset: MediaAsset) -> MediaRef:
        ...

    async def upload_batch(self, assets: list[MediaAsset]) -> list[MediaRef]:
        return [await self.upload(a) for a in assets]
```

### 3. Create the Bundle Factory

In `src/adapters/yourplatform/__init__.py`:

```python
from __future__ import annotations

from marketmenow.registry import PlatformBundle

from .adapter import YourPlatformAdapter
from .renderer import YourPlatformRenderer
from .settings import YourPlatformSettings
from .uploader import YourPlatformUploader


def create_yourplatform_bundle(
    settings: YourPlatformSettings | None = None,
) -> PlatformBundle:
    if settings is None:
        settings = YourPlatformSettings()

    return PlatformBundle(
        adapter=YourPlatformAdapter(...),
        renderer=YourPlatformRenderer(),
        uploader=YourPlatformUploader(...),
    )
```

### 4. Wire Up the CLI (Optional)

Create a Typer app in `cli.py` and add it to the main CLI in `src/marketmenow/cli.py`:

```python
from adapters.yourplatform.cli import app as yourplatform_app

app.add_typer(
    yourplatform_app,
    name="yourplatform",
    help="YourPlatform commands.",
    rich_help_panel="Platforms",
)
```

### 5. No Core Changes Needed

If you followed the steps above, the core pipeline, orchestrator, and scheduler will automatically work with your new platform through the registry.

## Adding a New Content Modality

1. Add a variant to `ContentModality` in `src/marketmenow/models/content.py`.
2. Create a frozen Pydantic model inheriting `BaseContent`.
3. Add a `case` arm in `ContentNormaliser.normalise()` in `src/marketmenow/normaliser.py`.
4. Existing adapters gain support by updating their `supported_modalities()` return value.

## Pre-Push Checks

A pre-push Git hook runs automatically before every `git push`. It executes three checks:

1. **Test suite** — `uv run --extra dev pytest --tb=short -q`
2. **Ruff lint** — `uv run ruff check src/ tests/`
3. **Ruff format** — `uv run ruff format --check src/ tests/`

If any check fails, the push is blocked. Fix the issue and push again. This keeps `main` clean without slowing down local commits.

The hook is installed by `setup.sh` or manually via:

```bash
uv run pre-commit install --hook-type pre-push
```

To run the checks without pushing:

```bash
uv run pre-commit run --hook-stage pre-push --all-files
```

## Pull Request Process

1. **Fork the repo** and create a feature branch from `main`.
2. **Make your changes** following the code style and architecture rules above.
3. **Test your changes** — run the CLI commands locally to verify.
4. **Write a clear PR description** explaining what changed and why.
5. **Keep PRs focused** — one feature or fix per PR.

### Commit Messages

Use clear, descriptive commit messages:

```
feat: add LinkedIn adapter with thread and carousel support
fix: handle empty caption in carousel normalisation
docs: add LinkedIn setup instructions to README
refactor: extract common TTS interface from reel orchestrator
```

Prefixes: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.

## Questions?

Open an issue or start a discussion on GitHub. We're happy to help you get started.
