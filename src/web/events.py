from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from uuid import UUID

logger = logging.getLogger(__name__)

_MAX_REPLAY = 200
_DB_FLUSH_INTERVAL = 5.0


@dataclass(frozen=True)
class ProgressEvent:
    event_type: str
    message: str
    phase: str | None = None
    current: int | None = None
    total: int | None = None
    wait_seconds: int | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


class EventHub:
    """In-memory pub/sub keyed by content-item UUID.

    Publishers call ``publish()``; WebSocket handlers subscribe via
    ``subscribe()`` / ``unsubscribe()`` and read from the returned queue.
    A bounded replay buffer per item lets late-joining clients catch up.
    """

    def __init__(self) -> None:
        self._subscribers: dict[UUID, set[asyncio.Queue[ProgressEvent]]] = {}
        self._replay: dict[UUID, deque[ProgressEvent]] = {}
        self._latest_snapshot: dict[UUID, dict] = {}
        self._dirty: set[UUID] = set()
        self._flush_task: asyncio.Task | None = None  # type: ignore[type-arg]

    def subscribe(self, item_id: UUID) -> asyncio.Queue[ProgressEvent]:
        q: asyncio.Queue[ProgressEvent] = asyncio.Queue(maxsize=512)
        self._subscribers.setdefault(item_id, set()).add(q)
        return q

    def unsubscribe(self, item_id: UUID, q: asyncio.Queue[ProgressEvent]) -> None:
        subs = self._subscribers.get(item_id)
        if subs:
            subs.discard(q)
            if not subs:
                del self._subscribers[item_id]

    def get_replay(self, item_id: UUID) -> list[ProgressEvent]:
        buf = self._replay.get(item_id)
        return list(buf) if buf else []

    def publish(self, item_id: UUID, event: ProgressEvent) -> None:
        self._replay.setdefault(item_id, deque(maxlen=_MAX_REPLAY)).append(event)

        if event.event_type in ("progress", "phase", "wait", "done", "error"):
            snap = self._latest_snapshot.get(item_id, {})
            if event.phase:
                snap["phase"] = event.phase
            if event.current is not None:
                snap["current"] = event.current
            if event.total is not None:
                snap["total"] = event.total
            if event.wait_seconds is not None:
                snap["wait_seconds"] = event.wait_seconds
            snap["last_message"] = event.message
            snap["last_event"] = event.event_type
            snap["updated_at"] = event.timestamp
            self._latest_snapshot[item_id] = snap
            self._dirty.add(item_id)

        for q in list(self._subscribers.get(item_id, ())):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.debug("Dropping event for slow subscriber on item %s", item_id)

    def get_snapshot(self, item_id: UUID) -> dict | None:
        return self._latest_snapshot.get(item_id)

    def clear(self, item_id: UUID) -> None:
        self._replay.pop(item_id, None)
        self._subscribers.pop(item_id, None)
        self._latest_snapshot.pop(item_id, None)
        self._dirty.discard(item_id)

    async def start_db_flusher(self) -> None:
        """Periodically write dirty snapshots to the DB for HTMX fallback."""
        while True:
            await asyncio.sleep(_DB_FLUSH_INTERVAL)
            if not self._dirty:
                continue
            dirty = list(self._dirty)
            self._dirty.clear()
            for item_id in dirty:
                snap = self._latest_snapshot.get(item_id)
                if snap is None:
                    continue
                try:
                    from web import db
                    await db.update_progress_data(item_id, snap)
                except Exception:
                    logger.debug("Failed to flush progress for %s", item_id, exc_info=True)

    def ensure_flusher_running(self) -> None:
        if self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.create_task(self.start_db_flusher())


hub = EventHub()
