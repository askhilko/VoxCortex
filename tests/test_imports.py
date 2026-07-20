from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize(
    "module",
    [
        "fastapi",
        "uvicorn",
        "yaml",
        "pyperclip",
        "pyautogui",
        "zeroconf",
        "pystray",
        "PIL",
        "faster_whisper",
        "huggingface_hub",
        "ctranslate2",
        "av",
        "tokenizers",
        "esptool",
        "serial",
        "m5_dictation.app",
        "m5_dictation.tray",
        "m5_dictation.firmware_updater",
    ],
)
def test_runtime_dependency_imports(module: str) -> None:
    importlib.import_module(module)
