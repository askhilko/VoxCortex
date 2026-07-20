from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from . import __version__
from .audio import AudioSession, AudioSessionError
from .config import Settings
from .inserter import TextInserter, legacy_output_action
from .protocol import PROTOCOL_VERSION, ProtocolError, parse_start, status
from .transcriber import WhisperTranscriber

LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class RecognitionEvent:
    created_at: datetime
    text: str
    device_id: str
    sequence: int
    action: str


RecognitionCallback = Callable[[RecognitionEvent], None]


@dataclass(frozen=True)
class DeviceStatusEvent:
    device_id: str
    device_name: str
    connected: bool
    state: str
    message: str
    updated_at: datetime
    battery_percent: int | None = None
    charging: bool | None = None
    rssi: int | None = None
    firmware_version: str = ""
    firmware_build: str = ""
    board: str = ""
    action: str = ""
    max_recording_seconds: int | None = None
    sounds_enabled: bool | None = None


DeviceStatusCallback = Callable[[DeviceStatusEvent], None]


class Runtime:
    def __init__(
        self,
        settings: Settings,
        transcriber: Any | None = None,
        inserter: Any | None = None,
        on_recognition: RecognitionCallback | None = None,
        on_device_status: DeviceStatusCallback | None = None,
    ) -> None:
        self.settings = settings
        self.transcriber = transcriber or WhisperTranscriber(settings.speech)
        self.inserter = inserter or TextInserter(settings)
        self.on_recognition = on_recognition
        self.on_device_status = on_device_status
        self.started_at = time.monotonic()
        self.devices: dict[str, dict[str, Any]] = {}
        self.completed: dict[str, set[int]] = {}
        self.connections: dict[
            str,
            tuple[WebSocket, asyncio.AbstractEventLoop, Callable[[dict[str, Any]], Any]],
        ] = {}
        self.settings_revision = int(time.time())


def device_settings_message(settings: Settings, revision: int) -> dict[str, Any]:
    message: dict[str, Any] = {
        "type": "settings_update",
        "protocol_version": PROTOCOL_VERSION,
        "revision": revision,
        "action": settings.device.action,
        "max_recording_seconds": settings.device.max_recording_seconds,
        "sounds_enabled": settings.device.sounds_enabled,
    }
    return message


def create_app(
    settings: Settings,
    transcriber: Any | None = None,
    inserter: Any | None = None,
    on_recognition: RecognitionCallback | None = None,
    on_device_status: DeviceStatusCallback | None = None,
) -> FastAPI:
    app = FastAPI(title="VoxCortex", version=__version__)
    runtime = Runtime(settings, transcriber, inserter, on_recognition, on_device_status)
    app.state.runtime = runtime

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "protocol_version": PROTOCOL_VERSION}

    @app.get("/status")
    async def server_status() -> dict[str, Any]:
        return {
            "uptime_seconds": round(time.monotonic() - runtime.started_at, 1),
            "devices": list(runtime.devices.values()),
            "diagnostic": runtime.settings.diagnostic,
        }

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        send_lock = asyncio.Lock()

        async def send_json(message: dict[str, Any]) -> None:
            async with send_lock:
                await websocket.send_json(message)

        await send_json(status("connected", "Connected to PC"))
        session: AudioSession | None = None
        processing_queue: asyncio.Queue[tuple[AudioSession, Path]] = asyncio.Queue(maxsize=4)
        processing_worker_task: asyncio.Task[None] | None = None
        pending_sequences: set[int] = set()
        device_id: str | None = None

        def publish_device_status(state_name: str, message: str, *, connected: bool = True) -> None:
            if not device_id or device_id not in runtime.devices:
                return
            item = runtime.devices[device_id]
            item.update(
                connected=connected,
                state=state_name,
                message=message,
                updated_at=time.time(),
            )
            if runtime.on_device_status is None:
                return
            try:
                runtime.on_device_status(
                    DeviceStatusEvent(
                        device_id=device_id,
                        device_name=str(item.get("device_name") or device_id),
                        connected=connected,
                        state=state_name,
                        message=message,
                        updated_at=datetime.now().astimezone(),
                        battery_percent=item.get("battery_percent"),
                        charging=item.get("charging"),
                        rssi=item.get("rssi"),
                        firmware_version=str(item.get("firmware_version", "")),
                        firmware_build=str(item.get("firmware_build", "")),
                        board=str(item.get("board", "")),
                        action=str(item.get("action", "")),
                        max_recording_seconds=item.get("max_recording_seconds"),
                        sounds_enabled=item.get("sounds_enabled"),
                    )
                )
            except Exception:
                LOG.exception("Не удалось обновить состояние устройства в окне приложения")

        async def send_state(state_name: str, message: str, **extra: Any) -> None:
            publish_device_status(state_name, message)
            await send_json(status(state_name, message, **extra))

        async def process_recording(current: AudioSession, wav_path: Path) -> None:
            try:
                await send_state(
                    "transcribing", "Recognizing speech", sequence=current.start.sequence
                )
                text = await asyncio.to_thread(runtime.transcriber.transcribe, wav_path)
                if not text:
                    LOG.info("Речь не распознана для %s", current.start.device_id)
                    await send_state(
                        "ready", "Speech not recognized", sequence=current.start.sequence
                    )
                    return
                active_settings = runtime.settings
                profile = active_settings.profiles.get(
                    current.start.profile, active_settings.profiles["clipboard"]
                )
                requested_action = current.start.action or legacy_output_action(profile, current.start.mode)
                device = runtime.devices.get(current.start.device_id, {})
                action = (
                    active_settings.device.action
                    if "settings_v1" in device.get("capabilities", [])
                    else requested_action
                )
                if requested_action != action:
                    LOG.info(
                        "Режим устройства %s заменён настройкой приложения %s",
                        requested_action,
                        action,
                    )
                event = RecognitionEvent(
                    created_at=datetime.now().astimezone(),
                    text=text,
                    device_id=current.start.device_id,
                    sequence=current.start.sequence,
                    action=action,
                )
                if runtime.on_recognition is not None:
                    try:
                        runtime.on_recognition(event)
                    except Exception:
                        LOG.exception("Не удалось добавить фразу в окно истории")
                LOG.info(
                    "Распознавание завершено; символов=%d",
                    len(text),
                    extra={
                        "event": "recognition",
                        "device_id": event.device_id,
                        "sequence": event.sequence,
                        "action": event.action,
                    },
                )
                await send_state("inserting", "Inserting text", sequence=current.start.sequence)
                await asyncio.to_thread(runtime.inserter.insert, text, action)
                done = runtime.completed.setdefault(current.start.device_id, set())
                done.add(current.start.sequence)
                if len(done) > 256:
                    done.remove(min(done))
                await send_state(
                    "sent", "Done", sequence=current.start.sequence, text_length=len(text)
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                LOG.exception("Recording processing failed for %s", current.start.device_id)
                with contextlib.suppress(RuntimeError):
                    await send_state("error", str(exc), sequence=current.start.sequence)
            finally:
                pending_sequences.discard(current.start.sequence)
                if not runtime.settings.keep_wav:
                    with contextlib.suppress(OSError):
                        wav_path.unlink(missing_ok=True)

        async def processing_worker() -> None:
            while True:
                current, wav_path = await processing_queue.get()
                try:
                    await process_recording(current, wav_path)
                finally:
                    processing_queue.task_done()

        processing_worker_task = asyncio.create_task(processing_worker())

        try:
            while True:
                packet = await websocket.receive()
                if packet.get("type") == "websocket.disconnect":
                    raise WebSocketDisconnect(packet.get("code", 1000))
                if packet.get("bytes") is not None:
                    if session is None:
                        LOG.warning("Ignoring audio received outside recording from %s", device_id or "unknown")
                        continue
                    session.append(packet["bytes"])
                    continue
                raw = packet.get("text")
                if raw is None:
                    continue
                message = json.loads(raw)
                message_type = message.get("type")
                if message_type == "hello":
                    if int(message.get("protocol_version", -1)) != PROTOCOL_VERSION:
                        raise ProtocolError("unsupported protocol_version")
                    device_id = str(message.get("device_id", ""))
                    if not device_id:
                        raise ProtocolError("device_id is required")
                    device_name = str(message.get("device_name", "")).strip() or device_id
                    capabilities = {
                        str(value) for value in message.get("capabilities", []) if isinstance(value, str)
                    }
                    runtime.devices[device_id] = {
                        "device_id": device_id,
                        "device_name": device_name,
                        "connected": True,
                        "state": "ready",
                        "message": "Hold A or double M5",
                        "connected_at": time.time(),
                        "updated_at": time.time(),
                        "capabilities": sorted(capabilities),
                        "firmware_version": str(message.get("firmware_version", "")),
                        "firmware_build": str(message.get("firmware_build", "")),
                        "board": str(message.get("board", "")),
                        "action": str(message.get("action", "")),
                        "max_recording_seconds": message.get("max_recording_seconds"),
                        "sounds_enabled": message.get("sounds_enabled"),
                    }
                    runtime.connections[device_id] = (
                        websocket,
                        asyncio.get_running_loop(),
                        send_json,
                    )
                    publish_device_status("ready", "Hold A or double M5")
                    active_settings = runtime.settings
                    await send_json(
                        status("ready", "Hold A or double M5", profiles=[
                            {"id": key, "title": profile.title}
                            for key, profile in active_settings.profiles.items()
                        ])
                    )
                    if "settings_v1" in capabilities:
                        runtime.settings_revision += 1
                        revision = runtime.settings_revision
                        runtime.devices[device_id]["settings_revision"] = revision
                        await send_json(device_settings_message(active_settings, revision))
                elif message_type == "recording_start":
                    if session is not None:
                        raise ProtocolError("recording already active")
                    start = parse_start(message)
                    if device_id and start.device_id != device_id:
                        raise ProtocolError("device_id changed")
                    done = runtime.completed.setdefault(start.device_id, set())
                    if start.sequence in done or start.sequence in pending_sequences:
                        await send_json(status("error", "Duplicate sequence", sequence=start.sequence))
                        continue
                    if processing_queue.full():
                        await send_state(
                            "error", "Processing queue is full", sequence=start.sequence
                        )
                        continue
                    active_settings = runtime.settings
                    session = AudioSession.create(
                        start,
                        active_settings.temp_dir,
                        active_settings.speech.max_duration_seconds,
                    )
                    pending_sequences.add(start.sequence)
                    await send_state("recording", "Receiving audio", sequence=start.sequence)
                elif message_type == "recording_end":
                    if session is None:
                        raise ProtocolError("no active recording")
                    if int(message.get("sequence", -1)) != session.start.sequence:
                        raise ProtocolError("sequence mismatch")
                    current = session
                    session = None
                    if bool(message.get("cancelled", False)):
                        current.discard()
                        pending_sequences.discard(current.start.sequence)
                        await send_state(
                            "cancelled", "Recording cancelled", sequence=current.start.sequence
                        )
                        continue
                    wav_path = current.close()
                    await send_state(
                        "receiving", "Audio received", sequence=current.start.sequence
                    )
                    if current.duration_seconds < runtime.settings.speech.min_duration_seconds:
                        wav_path.unlink(missing_ok=True)
                        pending_sequences.discard(current.start.sequence)
                        await send_state(
                            "error", "Recording is too short", sequence=current.start.sequence
                        )
                        continue
                    processing_queue.put_nowait((current, wav_path))
                elif message_type == "cancel":
                    if session is not None:
                        pending_sequences.discard(session.start.sequence)
                        session.discard()
                        session = None
                    if processing_worker_task is not None:
                        processing_worker_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await processing_worker_task
                    while not processing_queue.empty():
                        queued, queued_path = processing_queue.get_nowait()
                        pending_sequences.discard(queued.start.sequence)
                        queued_path.unlink(missing_ok=True)
                        processing_queue.task_done()
                    processing_worker_task = asyncio.create_task(processing_worker())
                    await send_state("cancelled", "Operation cancelled")
                elif message_type == "ping":
                    await send_json({"type": "pong", "protocol_version": PROTOCOL_VERSION})
                elif message_type in {"settings_ack", "telemetry"}:
                    if not device_id or device_id not in runtime.devices:
                        raise ProtocolError("hello is required")
                    item = runtime.devices[device_id]
                    if message_type == "settings_ack":
                        revision = int(message.get("revision", -1))
                        if revision != item.get("settings_revision"):
                            raise ProtocolError("settings revision mismatch")
                        if not bool(message.get("applied", False)):
                            raise ProtocolError("device rejected settings")
                    for key in (
                        "device_name",
                        "battery_percent",
                        "charging",
                        "rssi",
                        "firmware_version",
                        "firmware_build",
                        "board",
                        "action",
                        "max_recording_seconds",
                        "sounds_enabled",
                    ):
                        if key in message:
                            item[key] = message[key]
                    publish_device_status(
                        str(item.get("state", "ready")),
                        "Settings synchronized" if message_type == "settings_ack" else str(item.get("message", "")),
                    )
                else:
                    raise ProtocolError(f"unknown message type: {message_type}")
        except WebSocketDisconnect:
            LOG.info("Device disconnected: %s", device_id or "unknown")
        except (ProtocolError, AudioSessionError, json.JSONDecodeError, ValueError) as exc:
            LOG.warning("Protocol error from %s: %s", device_id or "unknown", exc)
            await send_json(status("error", str(exc)))
            await websocket.close(code=1003)
        except Exception as exc:
            LOG.exception("Device session failed")
            try:
                await send_json(status("error", str(exc)))
                await websocket.close(code=1011)
            except RuntimeError:
                pass
        finally:
            if session is not None:
                session.discard()
            if processing_worker_task is not None:
                processing_worker_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await processing_worker_task
            while not processing_queue.empty():
                queued, queued_path = processing_queue.get_nowait()
                queued_path.unlink(missing_ok=True)
                processing_queue.task_done()
            if device_id and runtime.connections.get(device_id, (None, None, None))[0] is websocket:
                runtime.connections.pop(device_id, None)
                if device_id in runtime.devices:
                    publish_device_status("disconnected", "Device disconnected", connected=False)

    return app
