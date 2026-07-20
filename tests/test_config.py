from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import yaml

from voxcortex.config import load_settings, prepare_user_config, save_settings


def test_migrates_former_product_data_directory(tmp_path: Path, monkeypatch) -> None:
    local_app_data = tmp_path / "LocalAppData"
    legacy = local_app_data / "M5AIDictationRemote"
    legacy.mkdir(parents=True)
    (legacy / "config.yaml").write_text(
        yaml.safe_dump({"speech": {"model": "tiny", "models_dir": "models"}}),
        encoding="utf-8",
    )
    (legacy / "history.json").write_text('{"version": 1, "items": []}', encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.delenv("VOXCORTEX_DATA_DIR", raising=False)
    monkeypatch.delenv("M5_DICTATION_DATA_DIR", raising=False)

    config_path = prepare_user_config()

    assert config_path == local_app_data / "VoxCortex" / "config.yaml"
    assert (local_app_data / "VoxCortex" / "history.json").is_file()


def test_migrates_legacy_runtime_data_once(tmp_path: Path, monkeypatch) -> None:
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    models = legacy / "models"
    models.mkdir()
    (legacy / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "temp_dir": "tmp",
                "log_dir": "logs",
                "speech": {"model": "tiny", "models_dir": "models"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    history = {"version": 1, "items": [{"text": "Секретная тестовая фраза"}]}
    (legacy / "history.json").write_text(json.dumps(history), encoding="utf-8")
    (legacy / "logs").mkdir()
    (legacy / "logs" / "server.log").write_text("test log", encoding="utf-8")
    (legacy / "tmp").mkdir()
    (legacy / "tmp" / "recording.wav").write_bytes(b"test wav")

    data_dir = tmp_path / "local-app-data"
    monkeypatch.setenv("VOXCORTEX_DATA_DIR", str(data_dir))
    config_path = prepare_user_config(legacy_paths=[legacy / "config.yaml"])
    settings = load_settings(config_path)

    assert config_path == data_dir / "config.yaml"
    assert settings.temp_dir == data_dir / "tmp"
    assert settings.log_dir == data_dir / "logs"
    assert settings.speech.models_dir == models
    assert (data_dir / "history.json").is_file()
    assert (data_dir / "logs" / "server.log").is_file()
    assert (data_dir / "tmp" / "recording.wav").is_file()
    assert (data_dir / ".legacy-migration-complete").is_file()

    (data_dir / "history.json").write_text("new history", encoding="utf-8")
    prepare_user_config(legacy_paths=[legacy / "config.yaml"])
    assert (data_dir / "history.json").read_text(encoding="utf-8") == "new history"


def test_loads_and_atomically_saves_configuration(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    config_path = data_dir / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "host": "127.0.0.1",
                "port": 8765,
                "temp_dir": "tmp",
                "log_dir": "logs",
                "speech": {"model": "tiny", "models_dir": "models"},
                "custom_section": {"preserved": True},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    settings = load_settings(config_path)
    external_models = tmp_path / "models-on-another-drive"
    changed = replace(
        settings,
        port=9876,
        speech=replace(settings.speech, model="small", models_dir=external_models),
    )
    save_settings(config_path, changed)
    reloaded = load_settings(config_path)
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert reloaded.port == 9876
    assert reloaded.speech.model == "small"
    assert reloaded.speech.models_dir == external_models
    assert raw["custom_section"] == {"preserved": True}
    assert not config_path.with_name(".config.yaml.tmp").exists()
