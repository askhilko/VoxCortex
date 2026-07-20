from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from PIL import ImageTk

from .app import DeviceStatusEvent, RecognitionEvent
from .icons import create_tray_image


ACTION_LABELS = {
    "copy": "Скопировать",
    "paste": "Вставить",
    "paste_enter": "Вставить и Enter",
    "paste_ctrl_enter": "Вставить и Ctrl+Enter",
}
LABEL_ACTIONS = {label: action for action, label in ACTION_LABELS.items()}
STATE_LABELS = {
    "ready": "Готов к записи",
    "recording": "Идёт запись",
    "receiving": "Запись получена",
    "transcribing": "Распознавание речи",
    "inserting": "Вставка текста",
    "sent": "Готово",
    "cancelled": "Операция отменена",
    "error": "Ошибка устройства",
    "disconnected": "Не подключено",
}
MODEL_NAMES = {
    "tiny": "Tiny",
    "base": "Base",
    "small": "Small",
    "medium": "Medium",
    "large-v3": "Large v3",
    "turbo": "Turbo",
}


def model_status_text(state: str, model: str, percent: int | None = None) -> str:
    name = MODEL_NAMES.get(model, model)
    if state == "ready":
        return f"Активная модель: {name}"
    if state == "downloading":
        progress = f" {percent}%" if percent is not None else ""
        return f"Модель распознавания: {name} · скачивание{progress}"
    if state == "loading":
        return f"Модель распознавания: {name} · подготовка…"
    if state == "error":
        return f"Модель распознавания: {name} · ошибка загрузки"
    return f"Модель распознавания: {name}"


class RecognitionHistoryWindow:
    def __init__(
        self,
        root: tk.Tk,
        on_close: Callable[[], None],
        on_exit: Callable[[], None],
        on_insert: Callable[[str, str], None],
        on_action_changed: Callable[[str], None] | None = None,
        on_open_settings: Callable[[], None] | None = None,
        on_open_firmware: Callable[[], None] | None = None,
        on_clear_history: Callable[[], None] | None = None,
    ) -> None:
        self.root = root
        self.on_close = on_close
        self.on_exit = on_exit
        self.on_insert = on_insert
        self.on_action_changed = on_action_changed
        self.on_open_settings = on_open_settings
        self.on_open_firmware = on_open_firmware
        self.on_clear_history = on_clear_history
        self.rows: list[tk.Frame] = []
        self.empty_label: ttk.Label | None = None
        self.devices: dict[str, DeviceStatusEvent] = {}

        root.title("M5 AI Dictation")
        root.geometry("880x680")
        root.minsize(640, 500)
        root.configure(background="#F3F5F7")
        root.protocol("WM_DELETE_WINDOW", on_close)
        self._icon = ImageTk.PhotoImage(create_tray_image("running", 64))
        root.iconphoto(True, self._icon)

        header = tk.Frame(root, background="#16324F", padx=20, pady=14)
        header.pack(fill="x")
        tk.Label(
            header,
            text="M5 AI Dictation",
            background="#16324F",
            foreground="white",
            font=("Segoe UI Semibold", 17),
        ).pack(side="left")
        if on_open_settings is not None:
            ttk.Button(header, text="Настройки", command=on_open_settings).pack(side="right")

        body = tk.Frame(root, background="#F3F5F7")
        body.pack(fill="both", expand=True, padx=14, pady=14)

        self._build_device_card(body)
        self._build_editor(body)
        self._build_history(body)

        footer = tk.Frame(root, background="#E5E9EE", padx=14, pady=9)
        footer.pack(fill="x")
        self.status = tk.Label(
            footer,
            text="Сервер запускается…",
            background="#E5E9EE",
            foreground="#425466",
            font=("Segoe UI", 9),
        )
        self.status.pack(side="left")
        ttk.Button(footer, text="Свернуть в трей", command=on_close).pack(side="right", padx=(8, 0))
        ttk.Button(footer, text="Выход", command=on_exit).pack(side="right")

    def _build_device_card(self, parent: tk.Widget) -> None:
        card = tk.Frame(parent, background="#FFFFFF", padx=14, pady=12)
        card.pack(fill="x", pady=(0, 10))
        self.device_dot = tk.Label(
            card,
            text="●",
            background="#FFFFFF",
            foreground="#8A94A3",
            font=("Segoe UI", 18),
        )
        self.device_dot.pack(side="left", padx=(0, 10))
        labels = tk.Frame(card, background="#FFFFFF")
        labels.pack(side="left", fill="x", expand=True)
        self.device_title = tk.Label(
            labels,
            text="Устройство не подключено",
            background="#FFFFFF",
            foreground="#172B3A",
            font=("Segoe UI Semibold", 11),
        )
        self.device_title.pack(anchor="w")
        self.device_details = tk.Label(
            labels,
            text="Включите M5StickC Plus2 и проверьте подключение к Wi-Fi",
            background="#FFFFFF",
            foreground="#637083",
            font=("Segoe UI", 9),
        )
        self.device_details.pack(anchor="w", pady=(2, 0))
        self.model_details = tk.Label(
            labels,
            text="Модель распознавания: подготовка…",
            background="#FFFFFF",
            foreground="#637083",
            font=("Segoe UI", 8),
            justify="left",
            anchor="w",
            wraplength=760,
        )
        self.model_details.pack(anchor="w", fill="x", pady=(3, 0))
        if self.on_open_firmware is not None:
            ttk.Button(card, text="Прошивка…", command=self.on_open_firmware).pack(
                side="right", padx=(12, 0)
            )

    def _build_editor(self, parent: tk.Widget) -> None:
        card = tk.Frame(parent, background="#FFFFFF", padx=14, pady=12)
        card.pack(fill="x", pady=(0, 10))
        toolbar = tk.Frame(card, background="#FFFFFF")
        toolbar.pack(fill="x", pady=(0, 8))
        tk.Label(
            toolbar,
            text="Текст",
            background="#FFFFFF",
            foreground="#172B3A",
            font=("Segoe UI Semibold", 11),
        ).pack(side="left")
        self.action_var = tk.StringVar(value=ACTION_LABELS["paste"])
        self.action_box = ttk.Combobox(
            toolbar,
            state="readonly",
            width=23,
            textvariable=self.action_var,
            values=list(ACTION_LABELS.values()),
        )
        self.action_box.pack(side="right")
        self.action_box.bind("<<ComboboxSelected>>", self._update_execute_label)

        self.editor = tk.Text(
            card,
            height=5,
            wrap="word",
            undo=True,
            relief="solid",
            borderwidth=1,
            font=("Segoe UI", 11),
            padx=9,
            pady=7,
        )
        self.editor.pack(fill="x")
        self.editor.bind("<Control-Return>", self._execute_shortcut)

        actions = tk.Frame(card, background="#FFFFFF")
        actions.pack(fill="x", pady=(9, 0))
        tk.Label(
            actions,
            text="Ctrl+Enter — выполнить",
            background="#FFFFFF",
            foreground="#7A8491",
            font=("Segoe UI", 8),
        ).pack(side="left")
        ttk.Button(actions, text="Очистить", command=self.clear_editor).pack(side="right", padx=(8, 0))
        self.execute_button = ttk.Button(actions, text="Вставить", command=self._execute)
        self.execute_button.pack(side="right")

    def _build_history(self, parent: tk.Widget) -> None:
        heading = tk.Frame(parent, background="#F3F5F7")
        heading.pack(fill="x", pady=(2, 7))
        tk.Label(
            heading,
            text="Последние фразы",
            background="#F3F5F7",
            foreground="#172B3A",
            font=("Segoe UI Semibold", 11),
        ).pack(side="left")
        if self.on_clear_history is not None:
            ttk.Button(
                heading,
                text="Очистить историю",
                command=self.on_clear_history,
            ).pack(side="right")
        history = tk.Frame(parent, background="#F3F5F7")
        history.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(history, background="#F3F5F7", highlightthickness=0)
        scrollbar = ttk.Scrollbar(history, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.list_frame = tk.Frame(self.canvas, background="#F3F5F7")
        self.canvas_window = self.canvas.create_window((0, 0), window=self.list_frame, anchor="nw")
        self.list_frame.bind("<Configure>", self._update_scroll_region)
        self.canvas.bind("<Configure>", self._resize_list)
        self.canvas.bind_all("<MouseWheel>", self._mouse_wheel)
        self.empty_label = ttk.Label(
            self.list_frame,
            text="Здесь появятся распознанные фразы",
            foreground="#6B7785",
            font=("Segoe UI", 11),
        )
        self.empty_label.pack(pady=45)

    def _update_scroll_region(self, _event: tk.Event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _resize_list(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self.canvas_window, width=event.width)

    def _mouse_wheel(self, event: tk.Event) -> None:
        self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def _selected_action(self) -> str:
        return LABEL_ACTIONS.get(self.action_var.get(), "paste")

    def set_action(self, action: str) -> None:
        if action in ACTION_LABELS:
            self.action_var.set(ACTION_LABELS[action])
            self._update_execute_label()

    def _update_execute_label(self, _event: tk.Event | None = None) -> None:
        self.execute_button.configure(text=ACTION_LABELS[self._selected_action()])
        if _event is not None and self.on_action_changed is not None:
            self.on_action_changed(self._selected_action())

    def _execute_shortcut(self, _event: tk.Event) -> str:
        self._execute()
        return "break"

    def _execute(self) -> None:
        text = self.editor.get("1.0", "end-1c").strip()
        if not text:
            self.status.configure(text="Введите текст", foreground="#B42318")
            self.editor.focus_set()
            return
        self.execute_button.configure(state="disabled")
        self.status.configure(text="Выполнение…", foreground="#425466")
        self.on_insert(text, self._selected_action())

    def clear_editor(self) -> None:
        self.editor.delete("1.0", "end")
        self.editor.focus_set()

    def load_editor(self, text: str) -> None:
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", text)
        self.editor.focus_set()
        self.status.configure(text="Фраза загружена в редактор", foreground="#197447")

    def set_manual_result(self, message: str, *, error: bool = False) -> None:
        self.execute_button.configure(state="normal")
        self.status.configure(text=message, foreground="#B42318" if error else "#197447")

    def show(self) -> None:
        self.root.deiconify()
        self.root.lift()

    def hide(self) -> None:
        self.root.withdraw()

    def set_server_ready(self, port: int) -> None:
        self.status.configure(text=f"Сервер работает · порт {port}", foreground="#197447")

    def set_server_error(self) -> None:
        self.status.configure(text="Ошибка запуска сервера", foreground="#B42318")

    def set_model_progress(
        self,
        state: str,
        _message: str,
        percent: int | None = None,
        model: str = "",
    ) -> None:
        self.model_details.configure(
            text=model_status_text(state, model, percent),
            foreground="#B42318" if state == "error" else "#637083",
        )

    def set_device_status(self, event: DeviceStatusEvent) -> None:
        self.devices[event.device_id] = event
        connected = [item for item in self.devices.values() if item.connected]
        current = max(connected or self.devices.values(), key=lambda item: item.updated_at)
        if current.connected:
            color = "#B42318" if current.state == "error" else "#197447"
            state = STATE_LABELS.get(current.state, current.message)
            self.device_title.configure(text=f"{current.device_name} — подключено")
            details = [state]
            if current.battery_percent is not None and current.battery_percent >= 0:
                battery = f"батарея {current.battery_percent}%"
                if current.charging:
                    battery += " ⚡"
                details.append(battery)
            if current.rssi is not None:
                details.append(f"Wi-Fi {current.rssi} dBm")
            if current.firmware_version:
                details.append(f"FW {current.firmware_version}")
            details.append(current.device_id)
            self.device_details.configure(text=" · ".join(details))
        else:
            color = "#8A94A3"
            timestamp = current.updated_at.strftime("%H:%M:%S")
            self.device_title.configure(text=f"{current.device_name} — не подключено")
            self.device_details.configure(text=f"Последнее соединение: {timestamp} · {current.device_id}")
        self.device_dot.configure(foreground=color)

    def add_event(self, event: RecognitionEvent) -> None:
        if self.empty_label is not None:
            self.empty_label.destroy()
            self.empty_label = None

        normal = "#FFFFFF"
        hover = "#E8F3FF"
        row = tk.Frame(self.list_frame, background=normal, padx=12, pady=10, cursor="hand2")
        row.pack(fill="x", pady=(0, 7))
        timestamp = tk.Label(
            row,
            text=event.created_at.strftime("%d.%m.%Y\n%H:%M:%S"),
            justify="center",
            width=12,
            background=normal,
            foreground="#637083",
            font=("Segoe UI", 9),
            cursor="hand2",
        )
        timestamp.pack(side="left", anchor="n", padx=(0, 10))
        phrase = tk.Label(
            row,
            text=event.text,
            justify="left",
            anchor="nw",
            wraplength=620,
            background=normal,
            foreground="#172B3A",
            font=("Segoe UI", 11),
            cursor="hand2",
        )
        phrase.pack(side="left", fill="x", expand=True)

        widgets = (row, timestamp, phrase)

        def recolor(color: str) -> None:
            for widget in widgets:
                widget.configure(background=color)

        for widget in widgets:
            widget.bind("<Enter>", lambda _event: recolor(hover))
            widget.bind("<Leave>", lambda _event: recolor(normal))
            widget.bind("<Button-1>", lambda _event, text=event.text: self.load_editor(text))

        self.rows.append(row)
        if len(self.rows) > 250:
            self.rows.pop(0).destroy()
        self.root.update_idletasks()
        self.canvas.yview_moveto(1.0)

    def clear_events(self) -> None:
        for row in self.rows:
            row.destroy()
        self.rows.clear()
        if self.empty_label is None:
            self.empty_label = ttk.Label(
                self.list_frame,
                text="Здесь появятся распознанные фразы",
                foreground="#6B7785",
                font=("Segoe UI", 11),
            )
            self.empty_label.pack(pady=45)
        self.canvas.yview_moveto(0.0)
