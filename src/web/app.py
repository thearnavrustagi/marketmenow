from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from web import db
from web.config import settings
from web.deps import STATIC_DIR
from web.events import hub
from web.queue_worker import run_queue_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

ws_logger = logging.getLogger("web.ws")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    await db.init_pool()
    worker_task = asyncio.create_task(run_queue_loop())
    hub.ensure_flusher_running()
    yield
    worker_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await worker_task
    await db.close_pool()


app = FastAPI(title="MarketMeNow", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

output_dir = settings.output_dir.resolve()
output_dir.mkdir(parents=True, exist_ok=True)
app.mount("/output", StaticFiles(directory=str(output_dir)), name="output")


# ── WebSocket endpoint ──────────────────────────────────────────────


@app.websocket("/ws/content/{item_id}")
async def content_ws(websocket: WebSocket, item_id: UUID) -> None:
    await websocket.accept()
    q = hub.subscribe(item_id)
    try:
        for evt in hub.get_replay(item_id):
            await websocket.send_text(json.dumps(evt.to_dict()))

        while True:
            event = await q.get()
            try:
                await websocket.send_text(json.dumps(event.to_dict()))
            except Exception:
                break
    except WebSocketDisconnect:
        pass
    except Exception:
        ws_logger.debug("WS closed for item %s", item_id)
    finally:
        hub.unsubscribe(item_id, q)


# ── Routes ──────────────────────────────────────────────────────────

from web.routes.credentials import router as credentials_router  # noqa: E402
from web.routes.dashboard import router as dashboard_router  # noqa: E402
from web.routes.flows import router as flows_router  # noqa: E402
from web.routes.generate import router as generate_router  # noqa: E402
from web.routes.outreach import router as outreach_router  # noqa: E402
from web.routes.project import router as project_router  # noqa: E402
from web.routes.queue import router as queue_router  # noqa: E402
from web.routes.review import router as review_router  # noqa: E402
from web.routes.webhooks import router as webhooks_router  # noqa: E402

app.include_router(dashboard_router)
app.include_router(flows_router)
app.include_router(outreach_router)
app.include_router(credentials_router)
app.include_router(generate_router)
app.include_router(review_router)
app.include_router(queue_router)
app.include_router(webhooks_router)
app.include_router(project_router)


def main() -> None:
    uvicorn.run(
        "web.app:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )


if __name__ == "__main__":
    main()
