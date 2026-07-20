from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path


def source_fingerprint(firmware_dir: Path) -> str:
    digest = hashlib.sha256()
    roots = [firmware_dir / "include", firmware_dir / "scripts", firmware_dir / "src"]
    files = [firmware_dir / "platformio.ini", firmware_dir / "version.json"]
    for root in roots:
        files.extend(
            path
            for path in root.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
        )
    for path in sorted(files, key=lambda item: item.as_posix()):
        digest.update(path.relative_to(firmware_dir).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:8]


def resolve_build_id(repository_root: Path) -> str:
    configured = (
        os.environ.get("VOXCORTEX_FIRMWARE_BUILD")
        or os.environ.get("M5_FIRMWARE_BUILD", "")
    ).strip()
    if configured:
        return configured
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=repository_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain", "--", "firmware"],
            cwd=repository_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if status:
            commit += f"-dirty.{source_fingerprint(repository_root / 'firmware')}"
        return commit
    except (OSError, subprocess.SubprocessError):
        return f"local.{source_fingerprint(repository_root / 'firmware')}"
