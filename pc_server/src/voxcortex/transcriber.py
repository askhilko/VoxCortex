from __future__ import annotations

import logging
import re
import shutil
import threading
from pathlib import Path
from threading import Lock
from collections.abc import Callable
from typing import Any

from .config import SpeechSettings

LOG = logging.getLogger(__name__)

MODEL_OPTIONS = {
    "tiny": ("Tiny — самый быстрый", "около 80 МБ"),
    "base": ("Base — быстро", "около 150 МБ"),
    "small": ("Small — оптимальный баланс", "около 500 МБ"),
    "medium": ("Medium — повышенная точность", "около 1,5 ГБ"),
    "large-v3": ("Large v3 — максимальная точность", "около 3 ГБ"),
    "turbo": ("Turbo — быстро и точно", "около 1,6 ГБ"),
}

MODEL_ALLOW_PATTERNS = [
    "config.json",
    "preprocessor_config.json",
    "model.bin",
    "tokenizer.json",
    "vocabulary.*",
]

KNOWN_HALLUCINATIONS = {
    "продолжение следует",
    "субтитры сделал dimatorzok",
}


def model_is_downloaded(model: str, models_dir: Path) -> bool:
    return model_local_path(model, models_dir) is not None


def model_cache_root(models_dir: Path) -> Path:
    return Path(models_dir).expanduser().resolve()


def _model_repo_id(model: str) -> str:
    from faster_whisper.utils import _MODELS

    repo_id = _MODELS.get(model)
    if repo_id is None:
        raise ValueError(f"Неизвестная модель: {model}")
    return repo_id


def model_cache_path(model: str, models_dir: Path) -> Path:
    repo_id = _model_repo_id(model)
    return model_cache_root(models_dir) / f"models--{repo_id.replace('/', '--')}"


def model_local_path(model: str, models_dir: Path) -> Path | None:
    try:
        from faster_whisper.utils import download_model

        return Path(
            download_model(
                model,
                local_files_only=True,
                cache_dir=str(model_cache_root(models_dir)),
            )
        )
    except Exception:
        return None


def delete_model(model: str, models_dir: Path) -> bool:
    """Delete one application's model cache without touching any other directory."""
    root = model_cache_root(models_dir)
    cache_path = model_cache_path(model, root).resolve()
    if cache_path.parent != root:
        raise ValueError("Некорректный путь модели")
    existed = cache_path.exists() or cache_path.is_symlink()
    if cache_path.is_symlink():
        cache_path.unlink()
    elif cache_path.exists():
        shutil.rmtree(cache_path)

    lock_path = root / ".locks" / cache_path.name
    if lock_path.is_symlink():
        lock_path.unlink()
    elif lock_path.exists():
        shutil.rmtree(lock_path)
    return existed


class _DownloadProgress:
    def __init__(self, callback: Callable[[int, int, int], None], total: int = 0) -> None:
        self.callback = callback
        self.lock = threading.Lock()
        self.current = 0
        self.total = max(0, total)
        self.last_percent = -1

    def advance(self, amount: int) -> None:
        with self.lock:
            self.current = max(0, self.current + amount)
            percent = min(99, int(self.current * 100 / self.total)) if self.total else 0
            if percent <= self.last_percent:
                return
            self.last_percent = percent
            current = self.current
            total = self.total
        self.callback(percent, current, total)

    def complete(self) -> None:
        with self.lock:
            if self.last_percent == 100:
                return
            self.current = max(self.current, self.total)
            self.last_percent = 100
            current = self.current
            total = self.total or self.current
        self.callback(100, current, total)


def _progress_tqdm_class(tracker: _DownloadProgress) -> type:
    class ProgressTqdm:
        _lock = threading.RLock()

        @classmethod
        def get_lock(cls):
            return cls._lock

        @classmethod
        def set_lock(cls, lock) -> None:
            cls._lock = lock

        def __init__(self, iterable=None, *args, **kwargs) -> None:
            self.iterable = iterable
            self.total = kwargs.get("total") or 0
            self.n = kwargs.get("initial") or 0
            self.desc = kwargs.get("desc", "")
            self._is_transfer = self.desc == "Downloading bytes"

        def __iter__(self):
            if self.iterable is None:
                return
            for item in self.iterable:
                yield item
                self.update(1)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback) -> None:
            self.close()

        def update(self, amount=1) -> None:
            self.n += amount or 0
            if self._is_transfer:
                tracker.advance(int(amount or 0))

        def refresh(self, *args, **kwargs) -> None:
            return None

        def close(self) -> None:
            return None

        def set_description(self, description, *args, **kwargs) -> None:
            self.desc = description
            if self._is_transfer and description == "Download complete":
                tracker.complete()

        def set_postfix_str(self, *args, **kwargs) -> None:
            return None

    return ProgressTqdm


def download_model_with_progress(
    model: str,
    models_dir: Path,
    on_progress: Callable[[int, int, int], None],
) -> Path:
    cached = model_local_path(model, models_dir)
    if cached is not None:
        on_progress(100, 1, 1)
        return cached

    from huggingface_hub import snapshot_download
    from faster_whisper.utils import disabled_tqdm

    repo_id = _model_repo_id(model)
    cache_root = model_cache_root(models_dir)
    cache_root.mkdir(parents=True, exist_ok=True)
    download_total = 0
    try:
        plan = snapshot_download(
            repo_id,
            allow_patterns=MODEL_ALLOW_PATTERNS,
            cache_dir=str(cache_root),
            dry_run=True,
            tqdm_class=disabled_tqdm,
        )
        download_total = sum(
            item.file_size for item in plan if getattr(item, "will_download", False)
        )
    except TypeError:
        LOG.warning("Installed huggingface_hub cannot pre-calculate download size")
    tracker = _DownloadProgress(on_progress, download_total)
    path = snapshot_download(
        repo_id,
        allow_patterns=MODEL_ALLOW_PATTERNS,
        cache_dir=str(cache_root),
        tqdm_class=_progress_tqdm_class(tracker),
    )
    tracker.complete()
    return Path(path)


def _format_bytes(value: int) -> str:
    if value >= 1024**3:
        return f"{value / 1024**3:.1f} ГБ"
    if value >= 1024**2:
        return f"{value / 1024**2:.0f} МБ"
    return f"{value / 1024:.0f} КБ"


def normalize_text(text: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def is_known_hallucination(text: str) -> bool:
    canonical = re.sub(r"[\W_]+", " ", text.casefold()).strip()
    return canonical in KNOWN_HALLUCINATIONS


class WhisperTranscriber:
    def __init__(self, settings: SpeechSettings) -> None:
        self.settings = settings
        self._model: Any = None
        self._lock = Lock()
        self._inference_lock = Lock()
        self._status_callback: Callable[[str, str, int | None], None] | None = None

    def _notify(self, state: str, message: str, percent: int | None) -> None:
        if self._status_callback is not None:
            self._status_callback(state, message, percent)

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self, on_status: Callable[[str, str, int | None], None] | None = None) -> None:
        if on_status is not None:
            self._status_callback = on_status
        with self._lock:
            if self._model is not None:
                if on_status is not None:
                    self._notify("ready", "Модель готова", 100)
                return
            LOG.info("Loading faster-whisper model %s", self.settings.model)
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                self._notify("error", "faster-whisper не установлен", None)
                raise RuntimeError(
                    "faster-whisper is not installed; run setup_windows.ps1 with speech support"
                ) from exc
            cache_root = model_cache_root(self.settings.models_dir)
            local_path = model_local_path(self.settings.model, cache_root)
            try:
                if local_path is None:
                    self._notify(
                        "downloading",
                        f"Скачивание в {cache_root}",
                        0,
                    )

                    def progress(percent: int, current: int, total: int) -> None:
                        amounts = ""
                        if total > 0:
                            amounts = f" · {_format_bytes(current)} из {_format_bytes(total)}"
                        self._notify(
                            "downloading",
                            f"Скачивание модели: {percent}%{amounts}\n{cache_root}",
                            percent,
                        )

                    local_path = download_model_with_progress(
                        self.settings.model,
                        cache_root,
                        progress,
                    )
                self._notify(
                    "loading",
                    f"Подготовка модели…\n{local_path}",
                    100,
                )
                self._model = WhisperModel(
                    str(local_path),
                    device="cpu",
                    compute_type="int8",
                )
                LOG.info("Speech model loaded on CPU")
                self._notify(
                    "ready",
                    f"Модель загружена и готова\n{local_path}",
                    100,
                )
            except Exception as exc:
                self._notify("error", f"Ошибка загрузки модели: {exc}", None)
                raise

    def transcribe(self, path: Path) -> str:
        self.load()
        with self._inference_lock:
            return self._transcribe_loaded(path)

    def _transcribe_loaded(self, path: Path) -> str:
        segments, _ = self._model.transcribe(
            str(path),
            language=self.settings.language,
            vad_filter=self.settings.vad,
            beam_size=self.settings.beam_size,
            log_prob_threshold=-0.8,
            no_speech_threshold=0.5,
            condition_on_previous_text=False,
        )
        text = normalize_text("".join(segment.text for segment in segments))
        if is_known_hallucination(text):
            LOG.info("Known Whisper hallucination discarded")
            return ""
        return text
