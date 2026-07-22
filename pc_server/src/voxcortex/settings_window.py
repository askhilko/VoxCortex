from __future__ import annotations

import os
import tkinter as tk
from collections.abc import Callable
from contextlib import suppress
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .config import DeviceSettings, Settings
from .history import ACTION_LABELS, LABEL_ACTIONS
from .transcriber import (
    MODEL_OPTIONS,
    delete_model,
    model_cache_root,
    model_cache_path,
    model_is_downloaded,
    model_local_path,
)


MODEL_LABELS = {
    model: f"{title} · {size}"
    for model, (title, size) in MODEL_OPTIONS.items()
}
LABEL_MODELS = {label: model for model, label in MODEL_LABELS.items()}


def confirm_model_download(parent: tk.Misc, model: str, models_dir: Path) -> bool:
    if model_is_downloaded(model, models_dir):
        return True
    size = MODEL_OPTIONS[model][1]
    return messagebox.askyesno(
        "Загрузка модели",
        f"Модель {model} ещё не загружена.\n\n"
        f"Потребуется интернет, {size} свободного места и некоторое время. "
        f"Модель будет сохранена в:\n{model_cache_root(models_dir)}\n\n"
        "Начать загрузку?",
        parent=parent,
    )


class ModelDownloadDialog:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.window: tk.Toplevel | None = None
        self.status: ttk.Label | None = None
        self.progress: ttk.Progressbar | None = None
        self.percent: ttk.Label | None = None
        self.close_button: ttk.Button | None = None

    @property
    def active(self) -> bool:
        return self.window is not None and self.window.winfo_exists()

    def update(self, state: str, message: str, percent: int | None) -> None:
        if state == "downloading":
            self._show()
            value = percent if percent is not None else 0
            self.status.configure(text=message)
            self.progress.configure(value=value)
            self.percent.configure(text=f"{value}%")
            return
        if not self.active:
            return
        if state == "loading":
            self.status.configure(text=message)
            self.progress.configure(value=100)
            self.percent.configure(text="100%")
            return
        if state == "error":
            self.status.configure(text=message, foreground="#B42318")
            self.close_button.pack(side="right")
            self.window.protocol("WM_DELETE_WINDOW", self.close)
            return
        if state == "ready":
            self.close()

    def _show(self) -> None:
        if self.active:
            self.window.deiconify()
            self.window.lift()
            return
        window = tk.Toplevel(self.root)
        self.window = window
        window.title("Скачивание модели")
        window.geometry("560x185")
        window.resizable(False, False)
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", lambda: None)

        content = ttk.Frame(window, padding=18)
        content.pack(fill="both", expand=True)
        ttk.Label(content, text="Загрузка модели распознавания", font=("Segoe UI", 12, "bold")).pack(
            anchor="w"
        )
        self.status = ttk.Label(content, foreground="#425466", wraplength=520)
        self.status.pack(fill="x", pady=(9, 10))
        self.progress = ttk.Progressbar(content, mode="determinate", maximum=100)
        self.progress.pack(fill="x")
        self.percent = ttk.Label(content, text="0%", anchor="e")
        self.percent.pack(fill="x", pady=(3, 0))
        self.close_button = ttk.Button(content, text="Закрыть", command=self.close)
        window.grab_set()

    def close(self) -> None:
        if not self.active:
            return
        with suppress(tk.TclError):
            self.window.grab_release()
        self.window.destroy()
        self.window = None


class SettingsWindow:
    def __init__(
        self,
        root: tk.Tk,
        settings: Settings,
        on_save: Callable[[Settings], None],
        config_dir: Path | None = None,
        on_models_changed: Callable[[], None] | None = None,
        on_open_support: Callable[[], None] | None = None,
    ) -> None:
        self.root = root
        self.settings = settings
        self.on_save = on_save
        self.config_dir = (config_dir or settings.speech.models_dir.parent).resolve()
        self.on_models_changed = on_models_changed
        self.on_open_support = on_open_support
        self.window: tk.Toplevel | None = None
        self.download_dialog = ModelDownloadDialog(root)

    def set_settings(self, settings: Settings) -> None:
        self.settings = settings
        if self.window is None or not self.window.winfo_exists():
            return
        self.action.set(ACTION_LABELS[settings.device.action])
        self.max_recording.set(str(settings.device.max_recording_seconds))
        self.sounds.set(settings.device.sounds_enabled)
        self.models_dir.set(str(settings.speech.models_dir))
        self.model.set(self._model_label(settings.speech.model))
        self.vad.set(settings.speech.vad)
        self.insertion_enabled.set(settings.insertion_enabled)
        self.paste_delay.set(str(settings.paste_delay_ms))
        self.restore_clipboard.set(settings.restore_clipboard)
        self._update_model_hint()

    def show(self) -> None:
        if self.window is not None and self.window.winfo_exists():
            self.window.deiconify()
            self.window.lift()
            return

        window = tk.Toplevel(self.root)
        self.window = window
        window.title("VoxCortex — настройки")
        window.geometry("680x680")
        window.minsize(620, 620)
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", window.withdraw)

        content = ttk.Frame(window, padding=14)
        content.pack(fill="both", expand=True)

        device = ttk.LabelFrame(content, text="Режим и устройство", padding=14)
        device.pack(fill="x", pady=(0, 10))
        self.action = tk.StringVar(value=ACTION_LABELS[self.settings.device.action])
        self.max_recording = tk.StringVar(value=str(self.settings.device.max_recording_seconds))
        self.sounds = tk.BooleanVar(value=self.settings.device.sounds_enabled)
        self._combo(device, 0, "Режим вывода", self.action, list(ACTION_LABELS.values()))
        self._entry(device, 1, "Максимальная запись, сек.", self.max_recording)
        ttk.Checkbutton(device, text="Звуковые сигналы на устройстве", variable=self.sounds).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(7, 0)
        )

        recognition = ttk.LabelFrame(content, text="Распознавание", padding=14)
        recognition.pack(fill="x", pady=(0, 10))
        self.models_dir = tk.StringVar(value=str(self.settings.speech.models_dir))
        self.model = tk.StringVar(value=self._model_label(self.settings.speech.model))
        model_values = [self._model_label(model) for model in MODEL_OPTIONS]
        if self.model.get() not in model_values:
            model_values.append(self.model.get())
        self._combo(recognition, 0, "Модель", self.model, model_values)
        self.model_box.bind("<<ComboboxSelected>>", self._update_model_hint)
        ttk.Label(recognition, text="Папка моделей").grid(
            row=1, column=0, sticky="w", pady=6, padx=(0, 12)
        )
        path_controls = ttk.Frame(recognition)
        path_controls.grid(row=1, column=1, sticky="ew", pady=6)
        self.models_dir_entry = ttk.Entry(path_controls, textvariable=self.models_dir)
        self.models_dir_entry.pack(side="left", fill="x", expand=True)
        self.models_dir_entry.bind("<FocusOut>", self._models_path_changed)
        ttk.Button(path_controls, text="Обзор…", command=self._choose_models_dir).pack(
            side="left", padx=(6, 0)
        )
        model_actions = ttk.Frame(recognition)
        model_actions.grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 4))
        ttk.Button(model_actions, text="Открыть папку", command=self._open_models_dir).pack(
            side="left"
        )
        ttk.Button(
            model_actions,
            text="Удалить выбранную модель",
            command=self._delete_selected_model,
        ).pack(side="left", padx=(8, 0))
        self.vad = tk.BooleanVar(value=self.settings.speech.vad)
        ttk.Label(
            recognition,
            text="Язык распознавания зафиксирован: русский.",
            foreground="#425466",
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(7, 2))
        ttk.Checkbutton(recognition, text="Отсекать тишину", variable=self.vad).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(5, 0)
        )
        self.model_status = ttk.Label(recognition, foreground="#637083", wraplength=510)
        self.model_status.grid(row=5, column=0, columnspan=2, sticky="w", pady=(9, 2))

        insertion = ttk.LabelFrame(content, text="Вставка текста", padding=14)
        insertion.pack(fill="x")
        self.insertion_enabled = tk.BooleanVar(value=self.settings.insertion_enabled)
        self.paste_delay = tk.StringVar(value=str(self.settings.paste_delay_ms))
        self.restore_clipboard = tk.BooleanVar(value=self.settings.restore_clipboard)
        ttk.Checkbutton(
            insertion,
            text="Разрешить автоматическую вставку",
            variable=self.insertion_enabled,
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 7))
        self._entry(insertion, 1, "Задержка перед вставкой, мс", self.paste_delay)
        ttk.Checkbutton(
            insertion,
            text="Восстанавливать предыдущий буфер обмена",
            variable=self.restore_clipboard,
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(7, 0))

        footer = ttk.Frame(window, padding=(14, 0, 14, 14))
        footer.pack(fill="x")
        if self.on_open_support is not None:
            ttk.Button(
                footer,
                text="Поддержать проект",
                command=self.on_open_support,
            ).pack(side="left")
        ttk.Button(footer, text="Закрыть", command=window.withdraw).pack(side="right", padx=(8, 0))
        self.save_button = ttk.Button(footer, text="Сохранить и применить", command=self._save)
        self.save_button.pack(side="right")
        self._update_model_hint()

    def _model_label(self, model: str) -> str:
        if model not in MODEL_LABELS:
            return model
        marker = (
            "✓ загружена"
            if model_is_downloaded(model, self._models_directory())
            else "○ не загружена"
        )
        return f"{MODEL_LABELS[model]} · {marker}"

    def _selected_model(self) -> str:
        selected = self.model.get()
        for model, label in MODEL_LABELS.items():
            if selected == label or selected.startswith(f"{label} · "):
                return model
        return LABEL_MODELS.get(selected, selected)

    def _models_directory(self) -> Path:
        raw = os.path.expandvars(self.models_dir.get().strip())
        if not raw:
            raise ValueError("Укажите папку для моделей")
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = self.config_dir / path
        return path.resolve()

    def _refresh_model_choices(self, selected: str | None = None) -> None:
        selected = selected or self._selected_model()
        values = [self._model_label(model) for model in MODEL_OPTIONS]
        self.model_box.configure(values=values)
        self.model.set(self._model_label(selected))

    def _models_path_changed(self, _event: tk.Event | None = None) -> None:
        try:
            selected = self._selected_model()
            self._refresh_model_choices(selected)
            self._update_model_hint()
        except Exception as exc:
            self.model_status.configure(text=str(exc), foreground="#B42318")

    def _choose_models_dir(self) -> None:
        try:
            initial = self._models_directory()
        except ValueError:
            initial = self.config_dir
        selected = filedialog.askdirectory(
            title="Папка для моделей распознавания",
            initialdir=str(initial),
            parent=self.window,
        )
        if selected:
            self.models_dir.set(selected)
            self._models_path_changed()

    def _open_models_dir(self) -> None:
        try:
            models_dir = self._models_directory()
            models_dir.mkdir(parents=True, exist_ok=True)
            os.startfile(str(models_dir))  # type: ignore[attr-defined]
        except Exception as exc:
            messagebox.showerror("Не удалось открыть папку", str(exc), parent=self.window)

    def _delete_selected_model(self) -> None:
        try:
            model = self._selected_model()
            models_dir = self._models_directory()
            cache_path = model_cache_path(model, models_dir)
            active_dir = model_cache_root(self.settings.speech.models_dir)
            if model == self.settings.speech.model and models_dir == active_dir:
                messagebox.showwarning(
                    "Модель используется",
                    "Сначала выберите и примените другую модель, затем удалите эту.",
                    parent=self.window,
                )
                return
            if not cache_path.exists():
                messagebox.showinfo(
                    "Модель не загружена",
                    f"Файлы модели {model} в выбранной папке не найдены.",
                    parent=self.window,
                )
                return
            if not messagebox.askyesno(
                "Удаление модели",
                f"Удалить модель {model} и освободить занятое ею место?\n\n{cache_path}",
                parent=self.window,
            ):
                return
            delete_model(model, models_dir)
            self._refresh_model_choices(model)
            self._update_model_hint()
            if self.on_models_changed is not None:
                self.on_models_changed()
            messagebox.showinfo("Модель удалена", f"Модель {model} удалена.", parent=self.window)
        except Exception as exc:
            messagebox.showerror("Не удалось удалить модель", str(exc), parent=self.window)

    def _update_model_hint(self, _event: tk.Event | None = None) -> None:
        model = self._selected_model()
        models_dir = self._models_directory()
        local_path = model_local_path(model, models_dir)
        if local_path is not None:
            self.model_status.configure(
                text=f"✓ Модель загружена.\nМесто хранения: {local_path}",
                foreground="#637083",
            )
        else:
            size = MODEL_OPTIONS.get(model, ("", "неизвестный объём"))[1]
            self.model_status.configure(
                text=(
                    f"○ Модель не загружена. Понадобится интернет и {size} свободного места.\n"
                    f"Будет сохранена в: {model_cache_root(models_dir)}"
                ),
                foreground="#637083",
            )

    def set_model_progress(self, state: str, message: str, percent: int | None = None) -> None:
        self.download_dialog.update(state, message, percent)
        if self.window is None or not self.window.winfo_exists():
            return
        if state in {"downloading", "loading"}:
            self.save_button.configure(state="disabled")
            self.model_status.configure(
                text="Скачивание модели выполняется в отдельном окне."
                if state == "downloading"
                else "Модель скачана. Подготовка к работе…",
                foreground="#637083",
            )
        else:
            self.save_button.configure(state="normal")
            if state == "ready":
                model = self._selected_model()
                self._refresh_model_choices(model)
                self._update_model_hint()
            elif state == "error":
                self.model_status.configure(text=message, foreground="#B42318")

    @staticmethod
    def _entry(parent: ttk.Frame, row: int, label: str, variable: tk.Variable) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=6, padx=(0, 12))
        ttk.Entry(parent, textvariable=variable, width=31).grid(row=row, column=1, sticky="ew", pady=6)
        parent.columnconfigure(1, weight=1)

    def _combo(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.Variable,
        values: list[str],
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=6, padx=(0, 12))
        box = ttk.Combobox(parent, textvariable=variable, values=values, state="readonly", width=31)
        box.grid(row=row, column=1, sticky="ew", pady=6)
        parent.columnconfigure(1, weight=1)
        if label == "Модель":
            self.model_box = box

    def _save(self) -> None:
        try:
            max_recording = int(self.max_recording.get())
            paste_delay = int(self.paste_delay.get())
            model = self._selected_model()
            models_dir = self._models_directory()
            if not 1 <= max_recording <= 600:
                raise ValueError("Длительность записи должна быть от 1 до 600 секунд")
            if not 0 <= paste_delay <= 5000:
                raise ValueError("Задержка вставки должна быть от 0 до 5000 мс")
            if model not in MODEL_OPTIONS and model != self.settings.speech.model:
                raise ValueError("Выберите модель из списка")
            models_dir.mkdir(parents=True, exist_ok=True)
            if not models_dir.is_dir():
                raise ValueError("Путь моделей не является папкой")
            if not confirm_model_download(self.window, model, models_dir):
                return
            new_speech = replace(
                self.settings.speech,
                model=model,
                models_dir=models_dir,
                language="ru",
                vad=self.vad.get(),
                max_duration_seconds=float(max_recording),
            )
            new_settings = replace(
                self.settings,
                insertion_enabled=self.insertion_enabled.get(),
                paste_delay_ms=paste_delay,
                restore_clipboard=self.restore_clipboard.get(),
                speech=new_speech,
                device=DeviceSettings(
                    action=LABEL_ACTIONS[self.action.get()],
                    max_recording_seconds=max_recording,
                    sounds_enabled=self.sounds.get(),
                ),
            )
            self.on_save(new_settings)
            self.settings = new_settings
            if model == self.settings.speech.model and model_is_downloaded(model, models_dir):
                self.model_status.configure(text="Настройки сохранены. Модель готова.")
        except Exception as exc:
            messagebox.showerror("Некорректные настройки", str(exc), parent=self.window)
