from __future__ import annotations

import asyncio
import json
import logging
import socket
import threading
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import uvicorn
from zeroconf import ServiceInfo, Zeroconf

from .app import DeviceStatusCallback, RecognitionCallback, create_app, device_settings_message
from .config import Settings
from .inserter import TextInserter
from .transcriber import WhisperTranscriber


class JsonFormatter(logging.Formatter):
    """Write one valid UTF-8 JSON object per log line."""

    def format(self, record: logging.LogRecord) -> str:
        item: dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created).astimezone().isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for name in ("event", "device_id", "sequence", "action"):
            if hasattr(record, name):
                item[name] = getattr(record, name)
        if record.exc_info:
            item["exception"] = self.formatException(record.exc_info)
        return json.dumps(item, ensure_ascii=False)


def configure_logging(log_dir: Path, diagnostic: bool, *, console: bool = True) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "server.log"
    formatter = JsonFormatter()
    file_handler = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(formatter)
    handlers: list[logging.Handler] = [file_handler]
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        handlers.append(console_handler)
    logging.basicConfig(
        level=logging.DEBUG if diagnostic else logging.INFO,
        handlers=handlers,
        force=True,
    )
    return log_path


class ServerRuntime:
    """Shared server lifecycle for console and Windows tray launchers."""

    def __init__(
        self,
        settings: Settings,
        on_recognition: RecognitionCallback | None = None,
        on_device_status: DeviceStatusCallback | None = None,
    ) -> None:
        self.settings = settings
        self.app = create_app(
            settings,
            on_recognition=on_recognition,
            on_device_status=on_device_status,
        )
        self.server = uvicorn.Server(
            uvicorn.Config(
                self.app,
                host=settings.host,
                port=settings.port,
                log_config=None,
            )
        )
        self.thread: threading.Thread | None = None
        self.failure: BaseException | None = None
        self._zeroconf: Zeroconf | None = None
        self._services: list[ServiceInfo] = []

    def apply_settings(self, settings: Settings) -> WhisperTranscriber | None:
        """Apply GUI-editable settings without restarting the server or losing UI state."""
        previous = self.settings
        self.settings = settings
        runtime = self.app.state.runtime
        runtime.settings = settings
        runtime.inserter = TextInserter(settings)

        transcriber: WhisperTranscriber | None = None
        model_runtime_changed = (
            settings.speech.model != previous.speech.model
            or settings.speech.models_dir != previous.speech.models_dir
        )
        if model_runtime_changed:
            transcriber = WhisperTranscriber(settings.speech)
            runtime.transcriber = transcriber
        elif isinstance(runtime.transcriber, WhisperTranscriber):
            runtime.transcriber.settings = settings.speech
            if not runtime.transcriber.is_loaded:
                transcriber = runtime.transcriber

        for device_id, connection in list(runtime.connections.items()):
            item = runtime.devices.get(device_id, {})
            if "settings_v1" not in item.get("capabilities", []):
                continue
            _websocket, loop, sender = connection
            runtime.settings_revision += 1
            revision = runtime.settings_revision
            item["settings_revision"] = revision
            future = asyncio.run_coroutine_threadsafe(
                sender(device_settings_message(settings, revision)),
                loop,
            )
            future.add_done_callback(self._log_settings_push_failure)
        return transcriber

    @staticmethod
    def _log_settings_push_failure(future: Any) -> None:
        try:
            future.result()
        except Exception:
            logging.getLogger(__name__).debug(
                "Не удалось отправить настройки отключившемуся устройству",
                exc_info=True,
            )

    @property
    def running(self) -> bool:
        return bool(self.server.started and self.thread and self.thread.is_alive())

    def _register_mdns(self) -> None:
        logger = logging.getLogger(__name__)
        try:
            address = socket.gethostbyname(socket.gethostname())
            if address.startswith("127."):
                return
            self._zeroconf = Zeroconf()
            service_specs = (
                ("_voxcortex._tcp.local.", "VoxCortex._voxcortex._tcp.local.", "voxcortex.local."),
                # Keep the former hostname working for devices configured before the rename.
                ("_m5-dictation._tcp.local.", "VoxCortex Legacy._m5-dictation._tcp.local.", "ai-dictation.local."),
            )
            for service_type, name, server in service_specs:
                service = ServiceInfo(
                    service_type,
                    name,
                    addresses=[socket.inet_aton(address)],
                    port=self.settings.port,
                    properties={"protocol": "1"},
                    server=server,
                )
                self._zeroconf.register_service(service)
                self._services.append(service)
            logger.info("mDNS voxcortex.local (legacy: ai-dictation.local) -> %s", address)
        except Exception:
            logger.exception("Не удалось зарегистрировать mDNS; сервер продолжит работу по IP-адресу")
            self._close_mdns()

    def _close_mdns(self) -> None:
        if self._zeroconf is None:
            return
        try:
            for service in reversed(self._services):
                self._zeroconf.unregister_service(service)
        finally:
            self._zeroconf.close()
            self._zeroconf = None
            self._services.clear()

    def run(self) -> None:
        self._register_mdns()
        try:
            self.server.run()
        finally:
            self._close_mdns()

    def _thread_target(self) -> None:
        try:
            self.run()
        except BaseException as exc:
            self.failure = exc
            logging.getLogger(__name__).exception("Сервер аварийно остановлен")

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.failure = None
        self.thread = threading.Thread(target=self._thread_target, name="voxcortex-server", daemon=True)
        self.thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        self.server.should_exit = True
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout)
