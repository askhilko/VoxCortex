from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from .app import RecognitionEvent

LOG = logging.getLogger(__name__)


class RecognitionHistoryStore:
    def __init__(self, path: Path, max_items: int = 250) -> None:
        self.path = path
        self.max_items = max_items
        self._items = self.load()

    @property
    def items(self) -> list[RecognitionEvent]:
        return list(self._items)

    def load(self) -> list[RecognitionEvent]:
        if not self.path.exists():
            return []
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
            raw_items = document.get("items", []) if isinstance(document, dict) else []
            events = [self._parse(item) for item in raw_items if isinstance(item, dict)]
            return events[-self.max_items :]
        except Exception:
            LOG.exception("Не удалось прочитать историю распознавания: %s", self.path)
            return []

    def append(self, event: RecognitionEvent) -> None:
        self._items.append(event)
        self._items = self._items[-self.max_items :]
        self._save()

    def clear(self) -> None:
        """Forget all recognition events and remove their persisted copy."""
        self._items.clear()
        self.path.unlink(missing_ok=True)
        self.path.with_name(f".{self.path.name}.tmp").unlink(missing_ok=True)

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        document = {
            "version": 1,
            "items": [self._serialize(event) for event in self._items],
        }
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        temporary.write_text(
            json.dumps(document, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)

    @staticmethod
    def _serialize(event: RecognitionEvent) -> dict[str, Any]:
        return {
            "created_at": event.created_at.isoformat(),
            "text": event.text,
            "device_id": event.device_id,
            "sequence": event.sequence,
            "action": event.action,
        }

    @staticmethod
    def _parse(item: dict[str, Any]) -> RecognitionEvent:
        return RecognitionEvent(
            created_at=datetime.fromisoformat(str(item["created_at"])),
            text=str(item["text"]),
            device_id=str(item.get("device_id", "unknown")),
            sequence=int(item.get("sequence", 0)),
            action=str(item.get("action", "copy")),
        )
