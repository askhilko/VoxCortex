from __future__ import annotations

from dataclasses import dataclass
from typing import Any

PROTOCOL_VERSION = 1
ACTIONS = {"copy", "paste", "paste_enter", "paste_ctrl_enter"}
STATES = {
    "connected",
    "ready",
    "recording",
    "receiving",
    "transcribing",
    "inserting",
    "sent",
    "cancelled",
    "error",
}


class ProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class RecordingStart:
    device_id: str
    sequence: int
    sample_rate: int
    profile: str
    mode: str
    action: str | None = None


def parse_start(message: dict[str, Any]) -> RecordingStart:
    if message.get("type") != "recording_start":
        raise ProtocolError("expected recording_start")
    if int(message.get("protocol_version", -1)) != PROTOCOL_VERSION:
        raise ProtocolError("unsupported protocol_version")
    if message.get("channels") != 1 or message.get("sample_format") != "pcm_s16le":
        raise ProtocolError("only mono pcm_s16le is supported")
    sample_rate = int(message.get("sample_rate", 0))
    if sample_rate != 16000:
        raise ProtocolError("sample_rate must be 16000")
    sequence = int(message.get("sequence", -1))
    if sequence < 0:
        raise ProtocolError("sequence must be non-negative")
    device_id = str(message.get("device_id", "")).strip()
    if not device_id or len(device_id) > 64:
        raise ProtocolError("invalid device_id")
    mode = str(message.get("mode", "insert"))
    if mode not in {"insert", "enter", "ctrl_enter"}:
        raise ProtocolError("invalid mode")
    raw_action = message.get("action")
    action = None if raw_action is None else str(raw_action)
    if action is not None and action not in ACTIONS:
        raise ProtocolError("invalid action")
    return RecordingStart(
        device_id=device_id,
        sequence=sequence,
        sample_rate=sample_rate,
        profile=str(message.get("profile", "chatgpt")),
        mode=mode,
        action=action,
    )


def status(state: str, message: str, **extra: Any) -> dict[str, Any]:
    if state not in STATES:
        raise ProtocolError(f"unknown state: {state}")
    return {
        "type": "status",
        "protocol_version": PROTOCOL_VERSION,
        "state": state,
        "message": message,
        **extra,
    }
