from __future__ import annotations

import json
import re
import sys
from pathlib import Path

Import("env")


PROJECT_DIR = Path(env.subst("$PROJECT_DIR"))
sys.path.insert(0, str(PROJECT_DIR / "scripts"))
from build_metadata import resolve_build_id

metadata = json.loads((PROJECT_DIR / "version.json").read_text(encoding="utf-8"))
version = str(metadata["version"])
board = str(metadata["board"])
protocol = int(metadata["protocol"])

if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", version):
    raise ValueError(f"Invalid firmware version: {version}")
if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", board):
    raise ValueError(f"Invalid firmware board id: {board}")
if protocol < 1:
    raise ValueError("Firmware protocol version must be positive")

build = resolve_build_id(PROJECT_DIR.parent)


def quoted(value: str) -> str:
    return f'\\"{value}\\"'


env.Append(
    CPPDEFINES=[
        ("M5_FIRMWARE_VERSION", quoted(version)),
        ("M5_FIRMWARE_BUILD", quoted(build)),
        ("M5_FIRMWARE_BOARD", quoted(board)),
        ("M5_PROTOCOL_VERSION", protocol),
    ]
)
