from __future__ import annotations

import argparse
import ctypes
import logging
import os
import queue
import sys
import threading
import time
import tkinter as tk
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from tkinter import messagebox

import pystray

from .app import DeviceStatusEvent, RecognitionEvent
from .config import Settings, application_dir, load_settings, prepare_user_config, save_settings
from .history import RecognitionHistoryWindow
from .history_store import RecognitionHistoryStore
from .firmware_window import FirmwareUpdateWindow
from .icons import create_tray_image
from .inserter import TextInserter
from .links import SUPPORT_URL, open_support_page
from .runtime import ServerRuntime, configure_logging
from .settings_window import SettingsWindow, confirm_model_download
from .transcriber import MODEL_OPTIONS, model_is_downloaded
from .windows_input import activate_window, foreground_window, root_window, window_process_id

LOG = logging.getLogger(__name__)


def firmware_manifest_path() -> Path:
    return application_dir() / "firmware" / "manifest.json"


class TrayApplication:
    def __init__(self, settings: Settings, log_path: Path, config_path: Path) -> None:
        self.settings = settings
        self.log_path = log_path
        self.config_path = config_path
        self.events: queue.Queue[RecognitionEvent] = queue.Queue()
        self.device_events: queue.Queue[DeviceStatusEvent] = queue.Queue()
        self.gui_actions: queue.Queue[Callable[[], None]] = queue.Queue()
        self.root = tk.Tk()
        self.tray_ready = False
        self.exiting = False
        self.device_statuses: dict[str, DeviceStatusEvent] = {}
        self.model_loading = False
        self.text_inserter = TextInserter(settings)
        self.last_external_window: int | None = None
        self.history_store = RecognitionHistoryStore(config_path.with_name("history.json"))
        self.history = RecognitionHistoryWindow(
            self.root,
            self.hide_history,
            self.request_exit,
            self.insert_manual_text,
            self.change_action,
            self.open_settings,
            self.open_firmware_update,
            self.clear_history,
            self.open_support,
        )
        self.history.set_action(settings.device.action)
        for event in self.history_store.items:
            self.history.add_event(event)
        self.settings_window = SettingsWindow(
            self.root,
            settings,
            self.apply_settings,
            config_path.parent,
            self._models_changed,
        )
        self.firmware_window = FirmwareUpdateWindow(self.root, firmware_manifest_path())
        self.server = ServerRuntime(
            settings,
            on_recognition=self.events.put,
            on_device_status=self.device_events.put,
        )
        self.icon = pystray.Icon(
            "voxcortex",
            create_tray_image("starting"),
            "VoxCortex — запуск",
            menu=self._create_menu(),
        )
        self._watcher: threading.Thread | None = None

    def _create_menu(self) -> pystray.Menu:
        model_items = [self._create_model_item(model) for model in MODEL_OPTIONS]
        return pystray.Menu(
            pystray.MenuItem(self._device_text, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Сменить модель", pystray.Menu(*model_items)),
            pystray.MenuItem("Распознанные фразы", self.show_history_from_tray, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Поддержать VoxCortex", self.open_support_from_tray),
            pystray.MenuItem("Выход", self.exit_from_tray),
        )

    def _create_model_item(self, model: str) -> pystray.MenuItem:
        def text(_item: pystray.MenuItem) -> str:
            title, size = MODEL_OPTIONS[model]
            marker = (
                "✓ загружена"
                if model_is_downloaded(model, self.settings.speech.models_dir)
                else "○ не загружена"
            )
            return f"{title} · {size} · {marker}"

        def action(_icon: pystray.Icon, _item: pystray.MenuItem) -> None:
            self.gui_actions.put(lambda: self._apply_model_from_tray(model))

        def checked(_item: pystray.MenuItem) -> bool:
            return self.settings.speech.model == model

        return pystray.MenuItem(
            text,
            action,
            checked=checked,
            radio=True,
            enabled=self._model_menu_enabled,
        )

    def _model_menu_enabled(self, _item: pystray.MenuItem) -> bool:
        return not self.model_loading

    def _device_text(self, _item: pystray.MenuItem) -> str:
        connected = [event for event in self.device_statuses.values() if event.connected]
        if not connected:
            return "Устройство не подключено"
        current = max(connected, key=lambda event: event.updated_at)
        extra = len(connected) - 1
        suffix = f" (+{extra})" if extra else ""
        return f"Подключено: {current.device_name}{suffix}"

    def _models_changed(self) -> None:
        self.icon.update_menu()

    def _watch_server(self, runtime: ServerRuntime) -> None:
        for _ in range(100):
            if runtime.running or runtime.failure is not None:
                break
            time.sleep(0.1)
        if runtime.running:
            self.icon.icon = create_tray_image("running")
            self.icon.title = "VoxCortex — готово"
            self.gui_actions.put(lambda: self.history.set_server_ready(runtime.settings.port))
            LOG.info("Tray-приложение готово")
            try:
                self.icon.notify("Сервер запущен. Окно истории можно открыть двойным щелчком.")
            except Exception:
                LOG.debug("Windows-уведомление недоступно", exc_info=True)
        else:
            self.icon.icon = create_tray_image("error")
            self.icon.title = "VoxCortex — ошибка запуска"
            self.gui_actions.put(self.history.set_server_error)
            LOG.error("Сервер не запустился; диагностический журнал: %s", self.log_path)
        self.icon.update_menu()

    def setup(self, icon: pystray.Icon) -> None:
        icon.visible = True
        self.tray_ready = True
        LOG.info("Значок зарегистрирован в области уведомлений; visible=%s", icon.visible)
        self.server.start()
        self._load_model_in_background(self.server.app.state.runtime.transcriber)
        self._watcher = threading.Thread(
            target=self._watch_server,
            args=(self.server,),
            name="tray-watcher",
            daemon=True,
        )
        self._watcher.start()

    def _poll_queues(self) -> None:
        while True:
            try:
                self.gui_actions.get_nowait()()
            except queue.Empty:
                break
        while True:
            try:
                event = self.events.get_nowait()
                self.history.add_event(event)
                try:
                    self.history_store.append(event)
                except Exception:
                    LOG.exception("Не удалось сохранить историю распознавания")
            except queue.Empty:
                break
        while True:
            try:
                event = self.device_events.get_nowait()
                self.device_statuses[event.device_id] = event
                self.history.set_device_status(event)
                self.icon.update_menu()
            except queue.Empty:
                break
        self._remember_external_window()
        if not self.exiting:
            self.root.after(100, self._poll_queues)

    def _remember_external_window(self) -> None:
        current = foreground_window()
        if current is None:
            return
        if window_process_id(current) == os.getpid():
            return
        application_window = root_window(self.root.winfo_id())
        if root_window(current) != application_window:
            self.last_external_window = root_window(current)

    def insert_manual_text(self, text: str, action: str) -> None:
        target = self.last_external_window

        def work() -> None:
            try:
                if not self.settings.insertion_enabled or self.settings.diagnostic:
                    raise RuntimeError("Вставка отключена в настройках приложения")
                if action != "copy":
                    if target is None or not activate_window(target):
                        raise RuntimeError("Не найдено окно для вставки. Сначала переключитесь в нужное окно")
                    time.sleep(0.1)
                self.text_inserter.insert(text, action)
                labels = {
                    "copy": "Текст скопирован",
                    "paste": "Текст вставлен",
                    "paste_enter": "Текст вставлен и отправлен",
                    "paste_ctrl_enter": "Текст вставлен и отправлен",
                }
                self.gui_actions.put(lambda: self.history.set_manual_result(labels[action]))
            except Exception as exc:
                LOG.exception("Не удалось выполнить действие с текстом")
                message = str(exc)
                self.gui_actions.put(lambda: self.history.set_manual_result(message, error=True))

        threading.Thread(target=work, name="manual-text-inserter", daemon=True).start()

    def open_settings(self) -> None:
        self.settings_window.show()

    def open_firmware_update(self) -> None:
        connected = [event for event in self.device_statuses.values() if event.connected]
        current = max(connected, key=lambda event: event.updated_at) if connected else None
        self.firmware_window.show(current)

    def open_support(self) -> None:
        try:
            if open_support_page():
                return
        except Exception:
            LOG.exception("Не удалось открыть страницу поддержки")
        messagebox.showerror(
            "Не удалось открыть страницу",
            f"Откройте страницу поддержки вручную:\n\n{SUPPORT_URL}",
            parent=self.root,
        )

    def clear_history(self) -> None:
        if not self.history_store.items:
            self.history.status.configure(text="История уже пуста", foreground="#425466")
            return
        if not messagebox.askyesno(
            "Очистка истории",
            "Удалить все сохранённые распознанные фразы? Отменить это действие нельзя.",
            parent=self.root,
        ):
            return
        self.history_store.clear()
        self.history.clear_events()
        self.history.status.configure(text="История очищена", foreground="#197447")

    def change_action(self, action: str) -> None:
        if action == self.settings.device.action:
            return
        self.apply_settings(
            replace(self.settings, device=replace(self.settings.device, action=action))
        )

    def _apply_model_from_tray(self, model: str) -> None:
        if self.model_loading:
            return
        current = self.server.app.state.runtime.transcriber
        if model == self.settings.speech.model and getattr(current, "is_loaded", False):
            return
        if not confirm_model_download(self.root, model, self.settings.speech.models_dir):
            return
        settings = self.settings
        if model != settings.speech.model:
            settings = replace(settings, speech=replace(settings.speech, model=model))
        self.apply_settings(settings)

    def apply_settings(self, settings: Settings) -> None:
        save_settings(self.config_path, settings)
        self.settings = settings
        self.text_inserter = TextInserter(settings)
        self.history.set_action(settings.device.action)
        self.settings_window.set_settings(settings)
        self.history.status.configure(text="Настройки сохранены", foreground="#197447")
        transcriber = self.server.apply_settings(settings)
        if transcriber is None:
            self.icon.update_menu()
            return

        self._load_model_in_background(transcriber)

    def _load_model_in_background(self, transcriber) -> None:
        self.model_loading = True
        self.icon.update_menu()

        def report_model_status(state: str, message: str, percent: int | None) -> None:
            def update() -> None:
                if state in {"ready", "error"}:
                    self.model_loading = False
                self.settings_window.set_model_progress(state, message, percent)
                self.history.set_model_progress(
                    state,
                    message,
                    percent,
                    transcriber.settings.model,
                )
                self.icon.update_menu()

            self.gui_actions.put(update)

        def load_model() -> None:
            try:
                transcriber.load(report_model_status)
            except Exception:
                LOG.exception("Не удалось загрузить выбранную модель распознавания")

        threading.Thread(target=load_model, name="model-loader", daemon=True).start()

    def show_history_from_tray(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self.gui_actions.put(self.history.show)

    def open_support_from_tray(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self.gui_actions.put(self.open_support)

    def hide_history(self) -> None:
        if self.tray_ready:
            self.history.hide()
        else:
            self.root.iconify()

    def request_exit(self) -> None:
        self._shutdown()

    def exit_from_tray(self, icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        icon.stop()
        self.gui_actions.put(self._shutdown)

    def _shutdown(self) -> None:
        if self.exiting:
            return
        self.exiting = True
        LOG.info("Tray-приложение завершает работу")
        self.server.stop()
        self.icon.stop()
        self.root.quit()

    def run(self) -> None:
        self.icon.run_detached(setup=self.setup)
        self.root.after(100, self._poll_queues)
        try:
            self.root.mainloop()
        finally:
            self._shutdown()
            self.root.destroy()


def show_error(message: str) -> None:
    if os.name == "nt":
        ctypes.windll.user32.MessageBoxW(None, message, "VoxCortex", 0x10)
    else:
        print(message, file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="VoxCortex Windows AI voice server")
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    try:
        config_path = args.config.resolve() if args.config else prepare_user_config()
        settings = load_settings(config_path)
        log_path = configure_logging(settings.log_dir, settings.diagnostic, console=False)
        LOG.info("Запуск tray-приложения; конфигурация: %s", config_path)
        TrayApplication(settings, log_path, config_path).run()
    except Exception as exc:
        logging.exception("Не удалось запустить tray-приложение")
        show_error(f"Не удалось запустить VoxCortex.\n\n{exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
