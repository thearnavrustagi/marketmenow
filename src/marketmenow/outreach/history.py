from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path(".outreach_history.json")


class OutreachHistory:
    """Tracks which handles have been contacted, keyed by platform:handle."""

    def __init__(self, path: Path = _DEFAULT_PATH) -> None:
        self._path = path
        self._data: dict[str, dict[str, object]] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            self._data = raw.get("contacted", {})
            logger.info("Loaded outreach history: %d contacts", len(self._data))

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({"contacted": self._data}, indent=2),
            encoding="utf-8",
        )

    def is_contacted(self, platform: str, handle: str) -> bool:
        key = f"{platform}:{handle.lower().lstrip('@')}"
        return key in self._data

    def record(
        self,
        platform: str,
        handle: str,
        *,
        message_preview: str = "",
        score: int = 0,
        profile_yaml: str = "",
        success: bool = True,
    ) -> None:
        key = f"{platform}:{handle.lower().lstrip('@')}"
        self._data[key] = {
            "sent_at": datetime.now(UTC).isoformat(),
            "message_preview": message_preview[:100],
            "score": score,
            "profile_yaml": profile_yaml,
            "success": success,
        }
        self._save()

    def contacted_handles(self, platform: str) -> set[str]:
        prefix = f"{platform}:"
        return {k.split(":", 1)[1] for k in self._data if k.startswith(prefix)}

    @property
    def total_contacted(self) -> int:
        return len(self._data)
