from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from m5_dictation.firmware_updater import (
    FirmwareManifest,
    FirmwareUpdateError,
    compare_versions,
)


def _write_manifest(directory: Path, firmware: bytes) -> Path:
    firmware_path = directory / "firmware.bin"
    firmware_path.write_bytes(firmware)
    digest = hashlib.sha256(firmware).hexdigest()
    image = {"offset": "0x10000", "file": "firmware.bin", "sha256": digest}
    manifest = {
        "schema": 1,
        "version": "1.2.3",
        "build": "test-build",
        "board": "m5stack-stickc-plus2",
        "protocol": 1,
        "baud": 921600,
        "update": {"images": [image]},
        "factory": {"images": [image]},
    }
    path = directory / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_manifest_verifies_firmware_sha256(tmp_path: Path) -> None:
    manifest = FirmwareManifest.load(_write_manifest(tmp_path, b"valid firmware"))

    assert manifest.verify()[0].filename == "firmware.bin"
    (tmp_path / "firmware.bin").write_bytes(b"tampered firmware")
    with pytest.raises(FirmwareUpdateError, match="Контрольная сумма"):
        manifest.verify()


def test_manifest_rejects_path_traversal(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, b"firmware")
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["update"]["images"][0]["file"] = "../firmware.bin"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(FirmwareUpdateError, match="Некорректный файл"):
        FirmwareManifest.load(path)


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ("1.2.3", "1.2.3", 0),
        ("1.2.4", "1.2.3", 1),
        ("2.0.0", "10.0.0", -1),
        ("1.2.3-beta", "1.2.3", -1),
        ("1.2.3", "1.2.3-beta", 1),
        ("1.2.3-beta.2", "1.2.3-beta.1", 1),
    ],
)
def test_compares_versions(left: str, right: str, expected: int) -> None:
    assert compare_versions(left, right) == expected


def test_rejects_invalid_version() -> None:
    with pytest.raises(FirmwareUpdateError, match="Некорректная версия"):
        compare_versions("1.2", "1.2.0")
