# Core Framework (src/marketmenow/)

This package is **platform-agnostic**. It must never import from `src/adapters/` or any platform SDK. The only exception is `core/registry_builder.py` which uses lazy imports inside try/except.

## Module Map

| Module                    | Purpose                                                      |
|---------------------------|--------------------------------------------------------------|
| `models/content.py`       | `ContentModality` enum, `BaseContent` and all content variants |
| `models/campaign.py`      | `Audience`, `ScheduleRule`, `CampaignTarget`, `Campaign`     |
| `models/result.py`        | `PublishResult`, `SendResult`, `MediaRef`, `AnalyticsSnapshot` |
| `models/distribution.py`  | `DistributionRoute`, `DistributionMap` (modality → platforms) |
| `ports/platform_adapter.py` | `PlatformAdapter` protocol                                 |
| `ports/content_renderer.py` | `ContentRenderer` protocol                                 |
| `ports/uploader.py`       | `Uploader` protocol                                         |
| `ports/analytics.py`      | `AnalyticsCollector` protocol                                |
| `normaliser.py`           | `NormalisedContent` model + `ContentNormaliser` (match/case dispatch) |
| `registry.py`             | `PlatformBundle` dataclass + `AdapterRegistry`               |
| `exceptions.py`           | `MarketMeNowError` hierarchy (`AdapterNotFoundError`, `UnsupportedModalityError`, `AuthenticationError`, `PublishError`, `RenderError`, `UploadError`) |
| `cli.py`                  | Top-level Typer app (`mmn`) — `run`, `workflows`, `auth`, `distribute`, `platforms`, `version`, `heal` + hidden adapter CLI groups for web frontend |
| `core/workflow.py`        | `WorkflowStep` protocol, `WorkflowContext`, `Workflow` runner, `ParamDef` |
| `core/workflow_registry.py`| `WorkflowRegistry` + `build_workflow_registry()` — auto-discovers workflows |
| `steps/*.py`              | Reusable workflow steps (generate_reel, post_to_platform, discover_posts, discover_prospects, enrich_profiles, score_prospects, generate_messages, send_messages, etc.) |
| `workflows/*.py`          | Built-in workflow definitions (instagram_reel, twitter_engage, twitter_outreach, etc.) |
| `outreach/models.py`      | `CustomerProfile`, `UserProfile`, `ScoredProspect`, `OutreachMessage`, rubric models |
| `outreach/ports.py`       | `DiscoveryVector`, `ProfileEnricher`, `MessageSender` protocols |
| `outreach/scorer.py`      | `ProspectScorer` — Gemini rubric evaluation (platform-agnostic) |
| `outreach/message_generator.py` | `OutreachMessageGenerator` — Gemini message generation (platform-agnostic) |
| `outreach/history.py`     | `OutreachHistory` — JSON tracking of contacted handles |
| `core/pipeline.py`        | `ContentPipeline` — normalise → render → upload → publish    |
| `core/orchestrator.py`    | `Orchestrator` + `CampaignResult` — runs campaigns across targets in parallel |
| `core/distributor.py`     | `ContentDistributor` — resolves platforms from `DistributionMap`, delegates to `Orchestrator` |
| `core/registry_builder.py`| `build_registry()` — auto-registers adapters (lazy imports, graceful skip on missing config) |
| `core/text_sanitiser.py`  | `sanitise_text()` — strips em/en-dashes from all text fields (anti-AI-detection) |
| `core/scheduler.py`       | `Scheduler` — in-process scheduled campaign execution        |
| `core/distribute_cli.py`  | Shared async helper for CLI `distribute` command             |
| `integrations/langchain.py`| LangChain tool/chain integration                            |

## Pipeline Flow

```
BaseContent
  → ContentNormaliser.normalise()  →  NormalisedContent
  → bundle.renderer.render()      →  NormalisedContent (platform-adapted)
  → sanitise_text()                →  NormalisedContent (em/en-dashes stripped)
  → bundle.uploader.upload_batch() →  list[MediaRef] (stored in extra._media_refs)
  → bundle.adapter.publish()       →  PublishResult
```

For `DIRECT_MESSAGE` modality, the last step calls `send_dm()` instead of `publish()`.

## Content Model Hierarchy

All models are `BaseModel` with `frozen=True`. `BaseContent` provides `id` (UUID), `modality`, `created_at`, `metadata`.

Variants: `VideoPost`, `ImagePost`, `Thread` (with `ThreadEntry`), `DirectMessage` (with `Recipient`), `Reply`, `TextPost`, `Document`, `Article`, `Poll`.

## Protocol Signatures

```python
class PlatformAdapter(Protocol):
    platform_name: str                                          # property
    def supported_modalities(self) -> frozenset[ContentModality]: ...
    async def authenticate(self, credentials: dict[str, str]) -> None: ...
    async def publish(self, content: NormalisedContent) -> PublishResult: ...
    async def send_dm(self, content: NormalisedContent) -> SendResult: ...

class ContentRenderer(Protocol):
    platform_name: str                                          # property
    async def render(self, content: NormalisedContent) -> NormalisedContent: ...

class Uploader(Protocol):
    platform_name: str                                          # property
    async def upload(self, asset: MediaAsset) -> MediaRef: ...
    async def upload_batch(self, assets: list[MediaAsset]) -> list[MediaRef]: ...

class AnalyticsCollector(Protocol):
    platform_name: str                                          # property
    async def collect(self, result: PublishResult) -> AnalyticsSnapshot: ...
```

## Registry

`PlatformBundle` groups `adapter`, `renderer`, `uploader`, and optional `analytics`. `AdapterRegistry` stores bundles by platform name and provides `register()`, `get()`, `list_platforms()`, `supports(platform, modality)`.

`build_registry()` in `core/registry_builder.py` calls `_try_<platform>()` for each adapter. Each function does a lazy import, constructs settings from env vars, builds the bundle, and registers it. Exceptions (missing config, validation errors) cause that platform to be silently skipped.

## Workflow System

A `Workflow` is a named sequence of `WorkflowStep` instances sharing a `WorkflowContext`. The context carries `params` (user CLI args) and `artifacts` (data produced by steps). Steps implement the `WorkflowStep` protocol: `name`, `description`, `async execute(ctx)`.

Steps live in `steps/` and can import from adapters (they are glue code). Workflows live in `workflows/` and compose steps with `ParamDef` declarations that drive CLI auto-generation. `build_workflow_registry()` auto-discovers all built-in workflows.

## Outreach Engine (outreach/)

Modular, platform-agnostic cold outreach system. The core defines models, protocols, and LLM-powered scoring/generation. Platform-specific discovery, enrichment, and sending live in adapter packages.

**Core (platform-agnostic):**
- `outreach/models.py` — `CustomerProfile` (loaded from YAML), `UserProfile`, `ScoredProspect`, `OutreachMessage`, `RubricCriterion`, `DiscoveryVectorConfig`, `MessagingConfig`
- `outreach/ports.py` — `DiscoveryVector` (finds posts), `ProfileEnricher` (scrapes profiles), `MessageSender` (sends messages) — all `typing.Protocol`
- `outreach/scorer.py` — `ProspectScorer` uses Gemini to evaluate each user against rubric criteria. Returns structured JSON with per-criterion scores and a `dm_angle`.
- `outreach/message_generator.py` — `OutreachMessageGenerator` uses Gemini to craft personalised messages based on the scorer's `dm_angle` and product info.
- `outreach/history.py` — `OutreachHistory` tracks contacted handles in `.outreach_history.json`, keyed by `{platform}:{handle}`.

**YAML-driven config:** Changing the `CustomerProfile` YAML fully reconfigures discovery queries, rubric criteria, tone, message length, and rate limits. Zero code changes.

**Platform adapters** implement the three protocols. Adding a new platform = new discovery vectors + profile enricher + message sender. The scorer and message generator are reused.

## Key Rules

- Never import platform SDKs or adapter code in this package (except `core/registry_builder.py`, `core/workflow_registry.py`, and `steps/`).
- All data models must be `frozen=True`.
- All protocols use `@runtime_checkable` and structural subtyping (no ABC inheritance).
- Use `model_copy(update={...})` to "mutate" frozen models.
- Normaliser uses `match`/`case` on content type — add a new arm when adding a modality.
