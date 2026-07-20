from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml


APP_DATA_DIR_NAME = "VoxCortex"
LEGACY_APP_DATA_DIR_NAMES = ("M5AIDictationRemote",)


def application_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd().resolve()


def _user_data_root() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        return Path(base) if base else Path.home() / "AppData" / "Local"
    base = os.environ.get("XDG_DATA_HOME")
    return Path(base).expanduser() if base else Path.home() / ".local" / "share"


def user_data_dir() -> Path:
    override = os.environ.get("VOXCORTEX_DATA_DIR") or os.environ.get("M5_DICTATION_DATA_DIR")
    if override:
        return Path(os.path.expandvars(override)).expanduser().resolve()
    return (_user_data_root() / APP_DATA_DIR_NAME).resolve()


def default_config_path() -> Path:
    return user_data_dir() / "config.yaml"


def _source_config_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def _unique_paths(paths: Iterable[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        resolved = path.resolve()
        key = os.path.normcase(str(resolved))
        if key not in seen:
            seen.add(key)
            result.append(resolved)
    return result


def _resolve_path(base: Path, value: object) -> Path:
    path = Path(os.path.expandvars(str(value))).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _copy_tree_missing(source: Path, target: Path) -> None:
    if not source.is_dir():
        return
    for item in source.rglob("*"):
        relative = item.relative_to(source)
        destination = target / relative
        if item.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, destination)


def _migrate_supporting_data(legacy_config: Path, data_dir: Path) -> None:
    legacy_dir = legacy_config.parent
    legacy_history = legacy_dir / "history.json"
    target_history = data_dir / "history.json"
    if legacy_history.is_file() and not target_history.exists():
        shutil.copy2(legacy_history, target_history)
    _copy_tree_missing(legacy_dir / "logs", data_dir / "logs")
    _copy_tree_missing(legacy_dir / "tmp", data_dir / "tmp")


def _write_migrated_config(legacy_config: Path, target: Path) -> None:
    raw = _mapping(yaml.safe_load(legacy_config.read_text(encoding="utf-8")), "config")
    speech_raw = _mapping(raw.get("speech"), "speech").copy()
    legacy_models = _resolve_path(legacy_config.parent, speech_raw.get("models_dir", "models"))

    raw["temp_dir"] = "tmp"
    raw["log_dir"] = "logs"
    speech_raw["models_dir"] = str(legacy_models) if legacy_models.is_dir() else "models"
    raw["speech"] = speech_raw

    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def prepare_user_config(
    *,
    legacy_paths: Iterable[Path] | None = None,
    template_path: Path | None = None,
) -> Path:
    """Create the per-user config and non-destructively import legacy runtime data."""
    data_dir = user_data_dir()
    config_path = data_dir / "config.yaml"
    migration_marker = data_dir / ".legacy-migration-complete"
    data_dir.mkdir(parents=True, exist_ok=True)

    if legacy_paths is None:
        legacy_paths = (
            *(
                _user_data_root() / name / "config.yaml"
                for name in LEGACY_APP_DATA_DIR_NAMES
            ),
            application_dir() / "config.yaml",
            _source_config_dir() / "config.yaml",
        )
    candidates = [
        path for path in _unique_paths(legacy_paths)
        if path != config_path and path.is_file()
    ]
    legacy_config = candidates[0] if candidates else None

    if not config_path.exists():
        if legacy_config is not None:
            _write_migrated_config(legacy_config, config_path)
        else:
            templates = [template_path] if template_path else [
                application_dir() / "config.example.yaml",
                _source_config_dir() / "config.example.yaml",
            ]
            template = next(
                (path.resolve() for path in templates if path is not None and path.is_file()),
                None,
            )
            if template is None:
                raise FileNotFoundError("config.example.yaml was not found")
            shutil.copy2(template, config_path)

    if legacy_config is not None and not migration_marker.exists():
        _migrate_supporting_data(legacy_config, data_dir)
        migration_marker.touch()
    return config_path


@dataclass(frozen=True)
class Profile:
    title: str
    paste: bool = True
    send_hotkey: str | None = None


@dataclass(frozen=True)
class SpeechSettings:
    model: str = "small"
    models_dir: Path = Path("models")
    language: str = "ru"
    vad: bool = True
    beam_size: int = 5
    min_duration_seconds: float = 0.3
    max_duration_seconds: float = 120.0


@dataclass(frozen=True)
class DeviceSettings:
    action: str = "paste"
    max_recording_seconds: int = 120
    sounds_enabled: bool = True


@dataclass(frozen=True)
class Settings:
    host: str = "0.0.0.0"
    port: int = 8765
    temp_dir: Path = Path("tmp")
    keep_wav: bool = False
    log_dir: Path = Path("logs")
    diagnostic: bool = False
    insertion_enabled: bool = True
    paste_delay_ms: int = 300
    restore_clipboard: bool = False
    speech: SpeechSettings = field(default_factory=SpeechSettings)
    device: DeviceSettings = field(default_factory=DeviceSettings)
    profiles: dict[str, Profile] = field(default_factory=dict)


DEFAULT_PROFILES = {
    "chatgpt": Profile("ChatGPT", True, None),
    "vscode": Profile("VS Code Agent", True, "ctrl+enter"),
    "terminal": Profile("Terminal / Codex", True, "enter"),
    "clipboard": Profile("Clipboard only", False, None),
}


def _mapping(data: Any, name: str) -> dict[str, Any]:
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"{name} must be a mapping")
    return data


def load_settings(path: str | Path) -> Settings:
    config_path = Path(path).resolve()
    raw = _mapping(yaml.safe_load(config_path.read_text(encoding="utf-8")), "config")
    speech_raw = _mapping(raw.get("speech"), "speech")
    device_raw = _mapping(raw.get("device"), "device")
    profiles_raw = _mapping(raw.get("profiles"), "profiles")

    profiles = DEFAULT_PROFILES.copy()
    for key, value in profiles_raw.items():
        item = _mapping(value, f"profiles.{key}")
        profiles[str(key)] = Profile(
            title=str(item.get("title", key)),
            paste=bool(item.get("paste", True)),
            send_hotkey=item.get("send_hotkey"),
        )

    base = config_path.parent
    settings = Settings(
        host=str(raw.get("host", "0.0.0.0")),
        port=int(raw.get("port", 8765)),
        temp_dir=_resolve_path(base, raw.get("temp_dir", "tmp")),
        keep_wav=bool(raw.get("keep_wav", False)),
        log_dir=_resolve_path(base, raw.get("log_dir", "logs")),
        diagnostic=bool(raw.get("diagnostic", False)),
        insertion_enabled=bool(raw.get("insertion_enabled", True)),
        paste_delay_ms=int(raw.get("paste_delay_ms", 300)),
        restore_clipboard=bool(raw.get("restore_clipboard", False)),
        speech=SpeechSettings(
            model=str(speech_raw.get("model", "small")),
            models_dir=_resolve_path(base, speech_raw.get("models_dir", "models")),
            language="ru",
            vad=bool(speech_raw.get("vad", True)),
            beam_size=int(speech_raw.get("beam_size", 5)),
            min_duration_seconds=float(speech_raw.get("min_duration_seconds", 0.3)),
            max_duration_seconds=float(speech_raw.get("max_duration_seconds", 120.0)),
        ),
        device=DeviceSettings(
            action=str(device_raw.get("action", "paste")),
            max_recording_seconds=int(device_raw.get("max_recording_seconds", 120)),
            sounds_enabled=bool(device_raw.get("sounds_enabled", True)),
        ),
        profiles=profiles,
    )
    if not (1 <= settings.port <= 65535):
        raise ValueError("port must be in range 1..65535")
    if settings.speech.min_duration_seconds < 0:
        raise ValueError("min_duration_seconds cannot be negative")
    if settings.speech.max_duration_seconds <= settings.speech.min_duration_seconds:
        raise ValueError("max_duration_seconds must exceed min_duration_seconds")
    if settings.device.action not in {"copy", "paste", "paste_enter", "paste_ctrl_enter"}:
        raise ValueError("device.action is invalid")
    if not (1 <= settings.device.max_recording_seconds <= 600):
        raise ValueError("device.max_recording_seconds must be in range 1..600")
    return settings


def _path_text(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def save_settings(path: str | Path, settings: Settings) -> None:
    """Atomically persist editable settings while retaining unknown config sections."""
    config_path = Path(path).resolve()
    raw = _mapping(yaml.safe_load(config_path.read_text(encoding="utf-8")), "config")
    raw.update(
        host=settings.host,
        port=settings.port,
        temp_dir=_path_text(settings.temp_dir, config_path.parent),
        keep_wav=settings.keep_wav,
        log_dir=_path_text(settings.log_dir, config_path.parent),
        diagnostic=settings.diagnostic,
        insertion_enabled=settings.insertion_enabled,
        paste_delay_ms=settings.paste_delay_ms,
        restore_clipboard=settings.restore_clipboard,
    )
    raw["speech"] = {
        "model": settings.speech.model,
        "models_dir": _path_text(settings.speech.models_dir, config_path.parent),
        "language": "ru",
        "vad": settings.speech.vad,
        "beam_size": settings.speech.beam_size,
        "min_duration_seconds": settings.speech.min_duration_seconds,
        "max_duration_seconds": settings.speech.max_duration_seconds,
    }
    raw["device"] = {
        "action": settings.device.action,
        "max_recording_seconds": settings.device.max_recording_seconds,
        "sounds_enabled": settings.device.sounds_enabled,
    }
    temporary = config_path.with_name(f".{config_path.name}.tmp")
    temporary.write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    temporary.replace(config_path)
