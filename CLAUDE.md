# MarketMeNow

Cross-platform marketing automation framework. Generates and publishes content across Instagram, Twitter/X, Reddit, LinkedIn, YouTube, TikTok, and Email from a single CLI or web dashboard.

## Project Layout

```
src/marketmenow/          # Platform-agnostic core (models, ports, pipeline, registry, workflows)
src/marketmenow/steps/    # Reusable workflow steps (generate, post, discover, etc.)
src/marketmenow/workflows/# Built-in workflow definitions (instagram-reel, twitter-engage, etc.)
src/adapters/             # Platform-specific adapters (instagram, twitter, linkedin, reddit, email, facebook, youtube, tiktok)
src/web/                  # FastAPI web dashboard
tests/                    # pytest + pytest-asyncio test suite
prompts/                  # YAML prompt templates per platform
campaigns/                # YAML campaign config files (e.g. reddit-launch)
projects/                 # Per-product marketing material directories
pyproject.toml            # Single source of truth for deps, scripts, ruff, pytest config
```

## Commands

```bash
uv sync                              # Install dependencies
uv sync --all-extras                  # Install with optional deps (langchain, dev tools)
uv run --extra dev pytest             # Run tests
uv run ruff check src/ tests/        # Lint
uv run ruff format src/ tests/       # Format
uv run ruff check --fix src/ tests/  # Auto-fix safe lint issues
uv run mmn --help                    # CLI help
uv run mmn workflows                 # List available marketing workflows
uv run mmn run <workflow> [OPTIONS]  # Run a workflow (e.g. instagram-reel, twitter-engage)
uv run mmn project add <slug>      # Create a new project (interactive onboarding)
uv run mmn project list             # List all projects
uv run mmn project use <slug>       # Set active project
uv run mmn project info             # Show project details
uv run mmn auth <platform>           # Authenticate with a platform
uv run mmn heal                      # Run tests and auto-fix failures via Cursor agent
uv run mmn-web                       # Start web dashboard (http://localhost:8000)
docker compose up -d                 # Start PostgreSQL (required for web dashboard)
```

## Architecture

Ports-and-adapters (hexagonal). The core engine is completely platform-agnostic.

**Pipeline flow:** Content → Normalise → Render → Sanitise → Upload → Publish

Key components:
- `ContentPipeline` (`core/pipeline.py`) — executes the five-stage pipeline for one platform
- `Orchestrator` (`core/orchestrator.py`) — runs a Campaign across multiple targets via `asyncio.gather`
- `ContentDistributor` (`core/distributor.py`) — resolves target platforms from a `DistributionMap` then delegates to `Orchestrator`
- `AdapterRegistry` (`registry.py`) — holds `PlatformBundle` instances keyed by platform name
- `ContentNormaliser` (`normaliser.py`) — converts any `BaseContent` variant into `NormalisedContent`
- `build_registry()` (`core/registry_builder.py`) — auto-registers all adapters whose env vars are present
- `PromptBuilder` (`core/prompt_builder.py`) — composable prompt assembly from persona + function + ICL blocks
- `EmbeddingStore` (`core/embedding_store.py`) — Gemini text-embedding-004 wrapper with batch embed and cosine distance
- `select_diverse_examples()` (`core/diversity_selector.py`) — farthest-point sampling for diverse ICL example selection

### Workflows (core/workflow.py, steps/, workflows/)

Higher-level composable marketing workflows. A `Workflow` is a named sequence of `WorkflowStep` instances that share a `WorkflowContext`. Steps are reusable building blocks; workflows compose them into end-to-end marketing flows.

- `WorkflowStep` — `typing.Protocol` with `name`, `description`, `execute(ctx)`
- `WorkflowContext` — mutable state bag carrying `params` (CLI args) and `artifacts` (step outputs)
- `Workflow` — frozen dataclass with `name`, `description`, `steps`, `params` (ParamDef schema)
- `WorkflowRegistry` (`core/workflow_registry.py`) — holds registered workflows, `build_workflow_registry()` auto-discovers all built-in workflows

Built-in workflows: `instagram-reel`, `instagram-carousel`, `twitter-thread`, `twitter-engage`, `twitter-outreach`, `reddit-engage`, `reddit-launch`, `linkedin-post`, `email-outreach`, `youtube-short`, `tiktok-reel`

### Projects (models/project.py, core/project_manager.py, core/onboarding.py)

Per-product packaging of all marketing material. A project directory under `projects/` contains everything needed to market a specific product: brand config, target customer, personas, platform prompts, engagement targets, campaign profiles, reel templates, and generated output.

- `ProjectConfig` — slug, brand, target customer, default persona, env overrides
- `GenerationConfig` — project-scoped batch generation settings (`generation_config.yaml`)
- `BrandConfig` — name, url, tagline, color, logo, features
- `TargetCustomer` — ICP description, pain points, keywords, target platforms
- `PersonaConfig` — voice, tone, example phrases, platform overrides
- `ProjectManager` — CRUD, path resolution with global fallback, active project tracking
- `run_onboarding()` — 10-phase interactive wizard for creating new projects

Path resolution: `ProjectManager.resolve_path()` checks `projects/{slug}/{category}/` first, falls back to global paths. This means workflows, prompt loaders, and template loaders automatically use project-specific content when available.

### Outreach Engine (outreach/)

Modular, platform-agnostic cold outreach system. Discovers people on a platform, scores them against a rubric, generates personalised messages, and sends them.

- `outreach/models.py` — `CustomerProfile`, `UserProfile`, `ScoredProspect`, `OutreachMessage`, `RubricCriterion`, `DiscoveryVectorConfig`
- `outreach/ports.py` — `DiscoveryVector`, `ProfileEnricher`, `MessageSender` protocols
- `outreach/scorer.py` — `ProspectScorer` (Gemini rubric evaluation, platform-agnostic)
- `outreach/message_generator.py` — `OutreachMessageGenerator` (Gemini message generation, platform-agnostic)
- `outreach/history.py` — `OutreachHistory` (JSON-based tracking of contacted handles)

Platform-specific implementations live in adapter packages (e.g. `adapters/twitter/outreach/`). The core engine never imports adapters.

### Prompt System (core/prompt_builder.py, prompts/, projects/)

Composable prompt architecture that separates **persona** (who the account is) from **function** (what it's doing) and **ICL** (in-context learning examples).

- `PromptBuilder` assembles prompts from three building blocks: persona template (project-scoped), function template (global), and optional ICL examples
- Resolution order: `projects/{slug}/prompts/{platform}/{file}` -> `projects/{slug}/prompts/{file}` -> `prompts/{platform}/{file}`
- Epsilon-greedy ICL: per reply, draw `random.random() < epsilon` to decide explore (no examples) vs exploit (diverse high-performing examples via farthest-point embedding sampling)
- Falls back to legacy monolithic prompt files for backward compatibility

### Protocols (ports/)

All defined as `typing.Protocol` with `@runtime_checkable`:

- **`PlatformAdapter`** — `platform_name`, `supported_modalities()`, `authenticate()`, `publish()`, `send_dm()`
- **`ContentRenderer`** — `platform_name`, `render(NormalisedContent) -> NormalisedContent`
- **`Uploader`** — `platform_name`, `upload(MediaAsset) -> MediaRef`, `upload_batch()`
- **`AnalyticsCollector`** — `platform_name`, `collect(PublishResult) -> AnalyticsSnapshot`

### Content Models (models/content.py)

`ContentModality` enum: VIDEO, IMAGE, THREAD, DIRECT_MESSAGE, REPLY, TEXT_POST, DOCUMENT, ARTICLE, POLL

`BaseContent` → `VideoPost`, `ImagePost`, `Thread`, `DirectMessage`, `Reply`, `TextPost`, `Document`, `Article`, `Poll`

### Adapters (src/adapters/)

| Adapter    | Modalities                                    | Key subsystems                                    |
|------------|-----------------------------------------------|---------------------------------------------------|
| instagram  | VIDEO, IMAGE                                  | Reels (TTS + Remotion), Carousels                 |
| twitter    | THREAD, REPLY, DIRECT_MESSAGE                 | Discovery, reply generation, engagement orchestrator, cold outreach (DM) |
| linkedin   | TEXT_POST, IMAGE, VIDEO, DOCUMENT, ARTICLE, POLL | API + browser posting                            |
| reddit     | REPLY, TEXT_POST                              | Two-phase engagement + subreddit post submission  |
| youtube    | VIDEO                                         | Shorts upload via Data API v3                     |
| tiktok     | VIDEO                                         | Content Posting API (Direct Post) + browser posting (cookie login) |
| email      | DIRECT_MESSAGE                                | CSV + Jinja2 templates, Gemini paraphrasing       |
| facebook   | TEXT_POST, IMAGE, VIDEO, DIRECT_MESSAGE        | Browser posting, group engagement (discover + AI comment + post) |

## Architecture Rules

1. **Core is platform-agnostic.** `src/marketmenow/` must never import from `src/adapters/` or any platform SDK. The only exception is `core/registry_builder.py` which does lazy imports inside try/except blocks.
2. **Structural subtyping only.** Adapters implement `typing.Protocol` interfaces — never subclass an ABC.
3. **Immutable data.** All Pydantic models use `frozen=True`. Mutate via `model_copy(update={...})`.
4. **Adapters are independent.** Adapter packages must not import from each other.
5. **`PlatformBundle` registration.** Each adapter exposes a `create_*_bundle(settings)` factory. Registration happens in `core/registry_builder.py` — missing env vars cause graceful skip.
6. **Project-scoped content.** Prompts, targets, templates, and campaigns resolve from the active project directory first, falling back to global paths.

## Python Style

- Python >= 3.12. `from __future__ import annotations` in every file.
- Full type annotations everywhere. Never use `Any`.
- Async-first: adapter methods are `async def`.
- Pydantic `BaseModel` with `frozen=True` for all data models.
- `typing.Protocol` with `@runtime_checkable` for all adapter interfaces.
- Absolute imports, no circular dependencies.

## Testing

- Tests in `tests/`, one `test_*.py` per module.
- Naming: `test_{module}_{behavior}`.
- `conftest.py` provides `MockAdapter`, `MockRenderer`, `MockUploader`, `MockAnalytics`, content factories (`make_video`, `make_image`, `make_thread`, etc.), and a pre-built `AdapterRegistry`.
- pytest-asyncio with `asyncio_mode = "auto"` — async tests are plain `async def`, no decorator.
- **Never call external APIs in tests.** Mock all I/O.
- Use `pytest.raises()` for expected exceptions, `tmp_path` for file-system tests.

## Adding a New Platform

1. Create `src/adapters/yourplatform/` with `adapter.py`, `renderer.py`, `uploader.py`, `settings.py`.
2. Implement `PlatformAdapter`, `ContentRenderer`, `Uploader` protocols.
3. Optionally implement `AnalyticsCollector`.
4. Expose `create_yourplatform_bundle(settings) -> PlatformBundle` in `__init__.py`.
5. Add a `_try_yourplatform()` function in `core/registry_builder.py`.
6. No changes to `core/`, `models/`, or `ports/`.

## Adding a New Workflow

1. Create a step in `src/marketmenow/steps/yourstep.py` implementing `WorkflowStep` protocol (`name`, `description`, `execute(ctx)`).
2. Create `src/marketmenow/workflows/your_workflow.py` composing steps into a `Workflow` with `ParamDef` declarations.
3. Add a `_try_register()` call in `core/workflow_registry.py` `build_workflow_registry()`.
4. No changes to `core/`, `models/`, `ports/`, or `cli.py` needed — workflows auto-register.

## Adding a New Content Modality

1. Add variant to `ContentModality` enum in `models/content.py`.
2. Create frozen Pydantic model inheriting `BaseContent`.
3. Add `case` arm in `ContentNormaliser.normalise()`.
4. Existing adapters update their `supported_modalities()`.

## Web Dashboard (src/web/)

FastAPI app with Jinja2 templates. Runs `mmn` CLI commands as subprocesses via `cli_runner.py`. The queue worker (`queue_worker.py`) drains a per-platform posting queue with rate limiting. Real-time progress via WebSocket (`/ws/content/{item_id}`) and `EventHub`. Dedicated **Outreach** page (`/outreach`) shows cold DM stats, outreach history from `.outreach_history.json`, campaign profiles, and quick-run forms for outreach workflows.

The web frontend calls per-platform CLI commands (`mmn reel create`, `mmn twitter engage`, etc.) as subprocesses. These adapter CLIs are mounted as **hidden groups** in `cli.py` (`hidden=True`) — they don't appear in `mmn --help` but remain callable by the web frontend.

## Environment

- Copy `.env.example` to `.env` and fill in API keys for platforms you use.
- `uv` is the package manager. All deps in `pyproject.toml`.
- Docker Compose provides PostgreSQL for the web dashboard.

## Commit Messages

Use conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.

## Documentation Maintenance

When making structural changes (new adapter, new modality, protocol change, new CLI command, new web route, pipeline change), update the relevant docs **in the same commit**:

- **New/removed adapter** → update this file (Adapters table), `src/adapters/CLAUDE.md`, `AGENTS.md` (if key files change), `README.md` (platform table)
- **New/removed modality** → update this file (Content Models), `src/marketmenow/CLAUDE.md`
- **Protocol signature change** → update this file (Protocols), `src/marketmenow/CLAUDE.md`
- **New CLI command** → update this file (Commands), `README.md`
- **Web architecture change** → update `src/web/CLAUDE.md`, `.cursor/rules/web.mdc`
- **Pipeline/orchestration change** → update `src/marketmenow/CLAUDE.md`, `.cursor/rules/core.mdc`

Keep updates surgical — edit only the affected sections, matching existing tone and format.
