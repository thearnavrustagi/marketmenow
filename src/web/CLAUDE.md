# Web Dashboard (src/web/)

FastAPI application providing a browser-based UI for content generation, review, and publishing.

## Architecture

The web app does **not** use the Python pipeline directly. Instead, it spawns `mmn` CLI commands as subprocesses via `cli_runner.py` and streams their output to the frontend through WebSocket events.

```
Browser → FastAPI routes → cli_runner.run_cli_streaming() → subprocess (uv run mmn ...)
                                    ↓
                              EventHub → WebSocket /ws/content/{item_id}
```

## Module Map

| Module               | Purpose                                                        |
|----------------------|----------------------------------------------------------------|
| `app.py`             | FastAPI app, lifespan (DB pool + queue worker), WebSocket endpoint, route registration |
| `config.py`          | `Settings` (pydantic-settings): host, port, DB URL, output dir, queue poll interval |
| `db.py`              | asyncpg connection pool, content/queue/rate-limit DB operations |
| `events.py`          | `EventHub` — publish/subscribe for `ProgressEvent`, WebSocket fan-out |
| `queue_worker.py`    | `run_queue_loop()` — polls DB queue, respects per-platform rate limits, calls `run_cli_streaming` |
| `cli_runner.py`      | `run_cli()` / `run_cli_streaming()` — spawns `uv run mmn ...` subprocesses, parses progress from stdout/stderr |
| `deps.py`            | Shared constants (STATIC_DIR, TEMPLATES_DIR, etc.)             |
| `routes/dashboard.py`| Dashboard page                                                 |
| `routes/generate.py` | Content generation forms, `generate_content`, `generate_all` (batch) |
| `routes/outreach.py` | Cold DM outreach page — stats, history, campaign profiles, run workflows |
| `routes/review.py`   | Content review UI (approve/reject per item)                    |
| `routes/queue.py`    | Queue management (view, requeue, cancel)                       |
| `routes/webhooks.py` | Webhook endpoints                                              |

## Key Patterns

### Hidden CLI Groups

The user-facing CLI exposes `mmn run <workflow>`, but the web frontend calls the **original per-platform commands** (`mmn reel create`, `mmn twitter engage`, etc.) as subprocesses. These adapter CLIs are re-mounted in `marketmenow/cli.py` with `hidden=True` — they don't appear in `mmn --help` but remain callable by the web frontend. The `reddit-launch` workflow is the exception: it uses `mmn run reddit-launch` directly.

### CLI Runner

`cli_runner.py` defines `PLATFORM_META` (JSON-serializable params per platform/command) and `BUILDERS` (server-side functions that construct `mmn` CLI argument lists). Each platform/command has a generate builder and a publish builder.

`run_cli_streaming()` reads subprocess stdout/stderr line-by-line, matches against regex patterns (`_PATTERNS`) to extract structured `ProgressEvent`s, and publishes them to the `EventHub`.

### Queue Worker

Background `asyncio.Task` started in the lifespan. Polls the database queue every N seconds. For each platform, checks rate limits (max per hour, max per day, min interval), then processes the next queued job by calling `run_cli_streaming` with the stored `publish_command`.

### Event System

`EventHub` provides pub/sub per content item UUID. WebSocket clients subscribe on connect and receive replayed + live `ProgressEvent`s. Events have types: `phase`, `progress`, `wait`, `log`, `stderr`, `done`, `error`.

### Batch Generation (`generate_all`)

Parallel generation across platforms. YouTube Shorts depend on Instagram Reel (reuses the mp4). Reddit and Email have special flows (discover + generate, CSV-based).

## Database

PostgreSQL via asyncpg. Connection pool initialized in lifespan. Tables: content items, queue jobs, post history, rate limits.

## Static Files

- Templates: `src/web/templates/` (Jinja2 HTML)
- Static assets: `src/web/static/` (CSS, JS)
- Generated output: mounted at `/output` from `settings.output_dir`

## Running

```bash
docker compose up -d      # Start PostgreSQL
uv run mmn-web            # Start dashboard at http://localhost:8000
```

Requires `MMN_WEB_DATABASE_URL` in `.env`.
