from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from voxcortex.app import RecognitionEvent
from voxcortex.history_store import RecognitionHistoryStore


def _event(number: int) -> RecognitionEvent:
    return RecognitionEvent(
        created_at=datetime(2026, 1, 1) + timedelta(seconds=number),
        text=f"Фраза {number}",
        device_id="test-device",
        sequence=number,
        action="copy",
    )


def test_history_is_bounded_persisted_and_cleared(tmp_path: Path) -> None:
    history_path = tmp_path / "history.json"
    store = RecognitionHistoryStore(history_path, max_items=2)

    store.append(_event(1))
    store.append(_event(2))
    store.append(_event(3))

    assert [item.text for item in store.items] == ["Фраза 2", "Фраза 3"]
    reloaded = RecognitionHistoryStore(history_path, max_items=2)
    assert [item.sequence for item in reloaded.items] == [2, 3]

    reloaded.clear()
    assert reloaded.items == []
    assert not history_path.exists()
    assert RecognitionHistoryStore(history_path).items == []
