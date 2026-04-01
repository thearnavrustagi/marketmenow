# MarketMeNow — Agent Guide

MarketMeNow is a cross-platform marketing automation framework (Python 3.12+, async, ports-and-adapters architecture). It generates and publishes content across Instagram, Twitter/X, Reddit, LinkedIn, YouTube, TikTok, Facebook, and Email via a CLI (`mmn`) and a FastAPI web dashboard.

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
| `src/marketmenow/core/prompt_builder.py`   | `PromptBuilder` — composable prompt assembly (persona + function + ICL) |
| `src/marketmenow/core/embedding_store.py`  | `EmbeddingStore` — Gemini text-embedding-004 wrapper |
| `src/marketmenow/core/diversity_selector.py` | `select_diverse_examples()` — farthest-point ICL diversity sampling |
| `src/marketmenow/core/capsule.py`      | `ContentCapsule`, `CapsuleManager` — content capsule packaging, cross-posting, publication tracking |
| `src/marketmenow/steps/package_capsule.py` | `PackageCapsuleStep` — packages generated content into capsules |
| `src/marketmenow/steps/post_from_capsule.py` | `PostFromCapsuleStep` — posts capsule to any platform by ID |
| `src/marketmenow/normaliser.py`         | `NormalisedContent` + `ContentNormaliser`  |
| `src/marketmenow/cli.py`               | Main CLI entry point (+ hidden adapter CLI aliases for web frontend) |
| `campaigns/*.yaml`                     | YAML campaign config files (e.g. reddit-launch) |
| `src/web/app.py`                        | FastAPI app                                |
| `src/web/cli_runner.py`                | Subprocess runner + progress parsing       |
| `tests/conftest.py`                     | Mock adapters and content factories        |
| `pyproject.toml`                        | All deps, scripts, ruff, pytest config     |
| `.env.example`                          | Required environment variables             |

## Prompt System (Design Standard)

**All content generation prompts MUST use `PromptBuilder`** (`src/marketmenow/core/prompt_builder.py`).
Deterministic tool prompts (autograde, rubric generation, sentiment scoring, guideline generation, worksheet generation/fill) may use direct YAML loading.

### How PromptBuilder Works

PromptBuilder assembles prompts from three composable building blocks:

1. **Persona** (`persona.yaml`) -- who the account is: voice, tone, brand identity
2. **Function** (`functions/{name}.yaml`) -- what the LLM is doing: task instructions, output format
3. **ICL** (`icl_block.yaml`) -- in-context learning examples of high-performing outputs

System prompt = persona system + "\n\n" + function system.
User prompt = function user template (with `{{ icl_block }}` injected when ICL examples provided).

### Prompt Categories

| Category | PromptBuilder? | Persona | Brand | Examples |
|----------|---------------|---------|-------|----------|
| **Content generation** | Yes, required | Required | Required | Comment/reply/thread/post generation, script generation, carousel |
| **Outreach** | Yes, required | None | None | Prospect scoring, message generation (uses CustomerProfile via template_vars) |
| **Platform metadata** | Yes, required | Optional | Required | YouTube metadata, email paraphrase |
| **Deterministic tools** | No, hardcoded | N/A | N/A | Autograde, rubric gen, sentiment scoring, guideline gen, worksheet gen/fill |

### Adding a New Content Generation Prompt

1. Create `prompts/{platform}/functions/{function_name}.yaml` with `system:` and `user:` keys (Jinja2)
2. If persona-driven: ensure `prompts/{platform}/persona.yaml` exists (or project override in `projects/{slug}/prompts/{platform}/persona.yaml`)
3. In code:
   ```python
   from marketmenow.core.prompt_builder import PromptBuilder
   builder = PromptBuilder()
   built = builder.build(
       platform="yourplatform",
       function="your_function",
       persona=persona_config,
       brand=brand_config,
       icl_examples=examples,  # optional
       template_vars={"post_text": "...", "key": "value"},
       project_slug=project_slug,
   )
   # built.system -> system instruction for LLM
   # built.user -> user message for LLM
   ```

### Resolution Order

PromptBuilder checks these paths (first match wins):
1. `projects/{slug}/prompts/{platform}/{file}` -- project + platform specific
2. `projects/{slug}/prompts/{file}` -- project generic
3. `prompts/{platform}/{file}` -- global fallback

### Template Variables

All templates receive these variables via Jinja2:
- `{{ brand.name }}`, `{{ brand.url }}`, `{{ brand.tagline }}`, `{{ brand.features }}` -- from BrandConfig
- `{{ persona.name }}`, `{{ persona.voice }}`, `{{ persona.tone }}`, `{{ persona.description }}` -- from PersonaConfig (with platform overrides applied)
- `{{ icl_block }}` -- rendered ICL examples (in user template only)
- Any caller-supplied `template_vars` (e.g. `{{ post_text }}`, `{{ subreddit }}`)

### Anti-Patterns (DO NOT)

- Create new `load_prompt()` helper functions for content generation -- use `PromptBuilder`
- Use Python `.format()` in YAML templates -- use Jinja2 `{{ }}`
- Hardcode brand names/URLs in prompt files -- use `{{ brand.name }}`, `{{ brand.url }}`
- Construct content prompts via string concatenation or f-strings
- Pass raw prompt strings to `generate_content` without going through PromptBuilder
- Embed persona instructions inside function YAML -- keep persona in `persona.yaml`

## Style

Python >= 3.12. `from __future__ import annotations` in every file. Full type annotations, no `Any`. Async-first adapters. Tests use pytest + pytest-asyncio (`asyncio_mode = "auto"`), never call external APIs.
