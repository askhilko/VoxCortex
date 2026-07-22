from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

import pytest

from tools.verify_release_archive import ReleaseArchiveError, validate_release_archive


ROOT = "VoxCortex"
SAFE_FILES = {
    f"{ROOT}/VoxCortex.exe": b"exe",
    f"{ROOT}/config.example.yaml": b"host: 0.0.0.0\n",
    f"{ROOT}/LICENSE.txt": b"MIT",
    f"{ROOT}/README.md": b"guide",
    f"{ROOT}/THIRD_PARTY_NOTICES.md": b"notices",
    f"{ROOT}/THIRD_PARTY_LICENSES/python/example/PACKAGE.txt": b"example",
}


def _archive(path: Path, files: dict[str, bytes]) -> Path:
    with ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return path


def test_accepts_clean_release_archive(tmp_path: Path) -> None:
    archive = _archive(tmp_path / "release.zip", SAFE_FILES)
    validate_release_archive(archive)


@pytest.mark.parametrize(
    "private_name",
    [
        "config.yaml",
        "history.json",
        "logs/server.log",
        "models/model.bin",
        "tmp/recording.wav",
    ],
)
def test_rejects_private_runtime_data(tmp_path: Path, private_name: str) -> None:
    files = {**SAFE_FILES, f"{ROOT}/{private_name}": b"private"}
    archive = _archive(tmp_path / "release.zip", files)

    with pytest.raises(ReleaseArchiveError, match="Private runtime data"):
        validate_release_archive(archive)


def test_rejects_zip_path_traversal(tmp_path: Path) -> None:
    archive = _archive(tmp_path / "release.zip", {**SAFE_FILES, "../secret.txt": b"secret"})
    with pytest.raises(ReleaseArchiveError, match="Unsafe archive entry"):
        validate_release_archive(archive)
