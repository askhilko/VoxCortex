from __future__ import annotations

import contextlib
import io
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from .app import DeviceStatusEvent
from .firmware_updater import (
    DeviceInfo,
    FirmwareManifest,
    FirmwareUpdateError,
    SerialDevice,
    compare_versions,
    discover_devices,
    ensure_update_allowed,
    flash,
    query_device,
)


class _QueueWriter(io.TextIOBase):
    def __init__(self, events: queue.Queue[tuple[str, object]]) -> None:
        self.events = events

    @property
    def encoding(self) -> str:
        return "utf-8"

    def write(self, value: str) -> int:
        if value:
            self.events.put(("log", value))
        return len(value)

    def flush(self) -> None:
        return None

    def isatty(self) -> bool:
        return False


class FirmwareUpdateWindow:
    """USB firmware updater integrated into the desktop application."""

    def __init__(self, root: tk.Tk, manifest_path: Path) -> None:
        self.root = root
        self.manifest_path = manifest_path
        self.window: tk.Toplevel | None = None
        self.manifest: FirmwareManifest | None = None
        self.devices: dict[str, SerialDevice] = {}
        self.current: DeviceInfo | None = None
        self.connected_event: DeviceStatusEvent | None = None
        self.busy = False
        self._events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._poll_scheduled = False

    def show(self, connected_event: DeviceStatusEvent | None = None) -> None:
        self.connected_event = connected_event
        if self.window is not None and self.window.winfo_exists():
            self._show_connected_event()
            self.window.deiconify()
            self.window.lift()
            return
        self._build()
        self._load_manifest()
        self._show_connected_event()
        self.refresh()

    def _build(self) -> None:
        window = tk.Toplevel(self.root)
        self.window = window
        window.title("M5 AI Dictation — прошивка")
        window.geometry("720x590")
        window.minsize(640, 520)
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", window.withdraw)

        content = ttk.Frame(window, padding=16)
        content.pack(fill="both", expand=True)

        ttk.Label(content, text="USB-обновление M5StickC Plus2", font=("Segoe UI", 14, "bold")).pack(
            anchor="w"
        )
        ttk.Label(
            content,
            text="Устройство прошивается только через USB. Обычное обновление сохраняет Wi-Fi и настройки.",
            foreground="#425466",
            wraplength=680,
        ).pack(anchor="w", fill="x", pady=(4, 12))

        versions = ttk.LabelFrame(content, text="Версии", padding=12)
        versions.pack(fill="x", pady=(0, 10))
        self.package_label = ttk.Label(versions, text="В приложении: проверка пакета…")
        self.package_label.pack(anchor="w")
        self.current_label = ttk.Label(versions, text="На устройстве: неизвестно")
        self.current_label.pack(anchor="w", pady=(5, 0))

        connection = ttk.LabelFrame(content, text="USB-устройство", padding=12)
        connection.pack(fill="x", pady=(0, 10))
        row = ttk.Frame(connection)
        row.pack(fill="x")
        ttk.Label(row, text="Порт:").pack(side="left")
        self.port_var = tk.StringVar()
        self.port_box = ttk.Combobox(row, state="readonly", textvariable=self.port_var, width=54)
        self.port_box.pack(side="left", fill="x", expand=True, padx=(8, 8))
        self.port_box.bind("<<ComboboxSelected>>", lambda _event: self._query_selected())
        self.refresh_button = ttk.Button(row, text="Обновить список", command=self.refresh)
        self.refresh_button.pack(side="right")

        self.status_label = ttk.Label(content, text="Подключите устройство USB-кабелем.", foreground="#425466")
        self.status_label.pack(anchor="w", fill="x", pady=(0, 8))
        self.progress = ttk.Progressbar(content, mode="indeterminate")
        self.progress.pack(fill="x", pady=(0, 10))

        log_frame = ttk.LabelFrame(content, text="Журнал", padding=8)
        log_frame.pack(fill="both", expand=True)
        self.log = tk.Text(log_frame, height=12, wrap="word", state="disabled", font=("Consolas", 9))
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=log_scroll.set)
        log_scroll.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)

        actions = ttk.Frame(content)
        actions.pack(fill="x", pady=(12, 0))
        self.factory_button = ttk.Button(
            actions,
            text="Заводская установка…",
            command=lambda: self._request_flash(factory=True),
        )
        self.factory_button.pack(side="left")
        ttk.Button(actions, text="Закрыть", command=window.withdraw).pack(side="right")
        self.update_button = ttk.Button(
            actions,
            text="Обновить прошивку",
            command=lambda: self._request_flash(factory=False),
        )
        self.update_button.pack(side="right", padx=(0, 8))
        self._set_busy(False)

    def _load_manifest(self) -> None:
        try:
            self.manifest = FirmwareManifest.load(self.manifest_path)
            self.manifest.verify()
            self.package_label.configure(
                text=f"В приложении: {self.manifest.version} · сборка {self.manifest.build}"
            )
        except FirmwareUpdateError as exc:
            self.manifest = None
            self.package_label.configure(text="В приложении: пакет прошивки недоступен", foreground="#B42318")
            self._set_status(str(exc), error=True)

    def _show_connected_event(self) -> None:
        event = self.connected_event
        if event is None or not event.connected or not event.firmware_version:
            return
        self.current = DeviceInfo(
            board=event.board,
            version=event.firmware_version,
            build=event.firmware_build,
            protocol=1,
            device_id=event.device_id,
        )
        self._render_current()

    def refresh(self) -> None:
        if self.busy:
            return
        self._set_busy(True)
        self._set_status("Ищу M5StickC Plus2 по USB…")
        self._start_worker(self._discover_worker)

    def _discover_worker(self) -> None:
        try:
            devices = discover_devices()
            self._events.put(("devices", devices))
        except Exception as exc:
            self._events.put(("error", str(exc)))

    def _apply_devices(self, devices: list[SerialDevice]) -> None:
        previous_port = self._selected_port()
        self.devices = {
            self._device_label(device): device
            for device in devices
        }
        labels = list(self.devices)
        self.port_box.configure(values=labels)
        selected = next(
            (label for label, item in self.devices.items() if item.port.casefold() == previous_port.casefold()),
            labels[0] if labels else "",
        )
        self.port_var.set(selected)
        if not labels:
            self.current = None
            self.current_label.configure(text="На устройстве: USB-устройство не найдено")
            self._set_status("M5StickC Plus2 с CH9102 не найден. Проверьте кабель и драйвер.", error=True)
            self._set_busy(False)
            return
        self._set_status(f"Найдено устройств: {len(labels)}. Читаю версию через {self._selected_port()}…")
        self._start_worker(self._query_worker, self._selected_port())

    def _query_selected(self) -> None:
        if self.busy:
            return
        port = self._selected_port()
        if not port:
            return
        self._set_busy(True)
        self._set_status(f"Читаю версию через {port}…")
        self._start_worker(self._query_worker, port)

    def _query_worker(self, port: str) -> None:
        try:
            self._events.put(("current", query_device(port)))
        except Exception as exc:
            self._events.put(("error", str(exc)))

    def _render_current(self) -> None:
        current = self.current
        manifest = self.manifest
        if current is None:
            self.current_label.configure(text="На устройстве: версия не определена")
            self._set_status("Версия не прочитана. Старую или чистую плату всё равно можно прошить.")
            return
        build = f" · сборка {current.build}" if current.build else ""
        identity = f" · {current.device_id}" if current.device_id else ""
        self.current_label.configure(text=f"На устройстве: {current.version}{build}{identity}")
        if manifest is None:
            return
        if current.board and current.board != manifest.board:
            self._set_status(
                f"Пакет предназначен для {manifest.board}, подключена плата {current.board}.",
                error=True,
            )
            return
        relation = compare_versions(current.version, manifest.version)
        if relation > 0:
            self._set_status("На устройстве установлена более новая версия. Понижение заблокировано.", error=True)
        elif relation == 0 and current.build == manifest.build:
            self._set_status("Прошивка устройства актуальна.", success=True)
        elif relation == 0:
            self._set_status("Версия совпадает, но доступна другая сборка.")
        else:
            self._set_status(f"Доступно обновление до {manifest.version}.")

    def _request_flash(self, *, factory: bool) -> None:
        if self.busy or self.manifest is None:
            return
        port = self._selected_port()
        if not port:
            messagebox.showerror("Прошивка", "Сначала подключите устройство и выберите COM-порт.", parent=self.window)
            return
        if factory:
            confirmed = messagebox.askyesno(
                "Заводская установка",
                "Будет полностью очищена flash-память устройства. Wi-Fi и все настройки будут удалены.\n\n"
                f"Продолжить через {port}?",
                parent=self.window,
                icon="warning",
            )
        else:
            confirmed = messagebox.askyesno(
                "Обновление прошивки",
                f"Записать прошивку {self.manifest.version} через {port}?\n\nWi-Fi и настройки сохранятся.",
                parent=self.window,
            )
        if not confirmed:
            return
        self._set_busy(True)
        self._append_log(f"\n--- {'Заводская установка' if factory else 'Обновление'} · {port} ---\n")
        self._set_status("Проверяю устройство и пакет прошивки…")
        self._start_worker(self._flash_worker, port, factory)

    def _flash_worker(self, port: str, factory: bool) -> None:
        manifest = self.manifest
        if manifest is None:
            self._events.put(("error", "Пакет прошивки недоступен"))
            return
        writer = _QueueWriter(self._events)
        try:
            images = manifest.verify(factory=factory)
            current = query_device(port)
            allowed = ensure_update_allowed(manifest, current, force=factory)
            if not factory and not allowed:
                raise FirmwareUpdateError("Прошивка устройства уже актуальна")
            with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                flash(manifest, port, images, factory=factory)
            self._events.put(("status", "Запись завершена. Проверяю устройство после перезагрузки…"))
            time.sleep(2)
            updated = query_device(port, timeout=12.0)
            if updated is None:
                raise FirmwareUpdateError(
                    "Прошивка записана, но устройство не подтвердило версию после перезагрузки"
                )
            if updated.board != manifest.board or updated.version != manifest.version:
                raise FirmwareUpdateError(
                    f"После перезагрузки устройство сообщило версию {updated.version}"
                )
            if updated.build and updated.build != manifest.build:
                raise FirmwareUpdateError(
                    f"После перезагрузки устройство сообщило сборку {updated.build}"
                )
            self._events.put(("flash_done", updated))
        except Exception as exc:
            self._events.put(("error", str(exc)))

    def _start_worker(self, target, *args: object) -> None:
        threading.Thread(target=target, args=args, name="firmware-updater", daemon=True).start()
        if not self._poll_scheduled:
            self._poll_scheduled = True
            self.root.after(80, self._poll_events)

    def _poll_events(self) -> None:
        self._poll_scheduled = False
        while True:
            try:
                kind, value = self._events.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self._append_log(str(value))
            elif kind == "status":
                self._set_status(str(value))
            elif kind == "devices":
                self._apply_devices(value)  # type: ignore[arg-type]
            elif kind == "current":
                self.current = value  # type: ignore[assignment]
                self._render_current()
                self._set_busy(False)
            elif kind == "flash_done":
                self.current = value  # type: ignore[assignment]
                self._render_current()
                self._set_status("Прошивка успешно обновлена и проверена.", success=True)
                self._append_log("\nГотово: устройство запустило новую прошивку.\n")
                self._set_busy(False)
            elif kind == "error":
                self._set_status(str(value), error=True)
                self._append_log(f"\nОшибка: {value}\n")
                self._set_busy(False)
        if (self.busy or not self._events.empty()) and not self._poll_scheduled:
            self._poll_scheduled = True
            self.root.after(80, self._poll_events)

    def _selected_port(self) -> str:
        selected = self.devices.get(self.port_var.get()) if hasattr(self, "port_var") else None
        return selected.port if selected is not None else ""

    @staticmethod
    def _device_label(device: SerialDevice) -> str:
        serial = f" · USB {device.serial_number}" if device.serial_number else ""
        return f"{device.port} · {device.description}{serial}"

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        has_port = bool(self._selected_port())
        board_matches = (
            self.current is None
            or not self.current.board
            or self.manifest is None
            or self.current.board == self.manifest.board
        )
        can_update = not busy and has_port and self.manifest is not None and board_matches
        if can_update and self.current is not None:
            relation = compare_versions(self.current.version, self.manifest.version)
            can_update = relation < 0 or (
                relation == 0 and self.current.build != self.manifest.build
            )
        self.update_button.configure(state="normal" if can_update else "disabled")
        self.factory_button.configure(
            state=(
                "normal"
                if not busy and has_port and self.manifest is not None and board_matches
                else "disabled"
            )
        )
        self.refresh_button.configure(state="disabled" if busy else "normal")
        self.port_box.configure(state="disabled" if busy else "readonly")
        if busy:
            self.progress.start(12)
        else:
            self.progress.stop()

    def _set_status(self, text: str, *, error: bool = False, success: bool = False) -> None:
        color = "#B42318" if error else "#197447" if success else "#425466"
        self.status_label.configure(text=text, foreground=color)

    def _append_log(self, value: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", value.replace("\r", "\n"))
        self.log.see("end")
        self.log.configure(state="disabled")
