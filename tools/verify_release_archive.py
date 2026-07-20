from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile


EXPECTED_ROOT = "VoxCortex"
FORBIDDEN_RUNTIME_ITEMS = {"config.yaml", "history.json", "logs", "models", "tmp"}
REQUIRED_RELEASE_ITEMS = {"VoxCortex.exe", "config.example.yaml", "README.md"}


class ReleaseArchiveError(RuntimeError):
    pass


def validate_release_archive(path: str | Path, expected_root: str = EXPECTED_ROOT) -> None:
    archive_path = Path(path).resolve()
    try:
        with ZipFile(archive_path) as archive:
            names = []
            for entry in archive.infolist():
                normalized = entry.filename.replace("\\", "/")
                parts = PurePosixPath(normalized).parts
                if normalized.startswith("/") or ".." in parts:
                    raise ReleaseArchiveError(f"Unsafe archive entry: {entry.filename}")
                if not parts or parts[0] != expected_root:
                    raise ReleaseArchiveError(f"Entry outside {expected_root}: {entry.filename}")
                names.append(parts)
    except (OSError, BadZipFile) as exc:
        raise ReleaseArchiveError(f"Could not read release archive: {archive_path}") from exc

    forbidden = sorted(
        "/".join(parts)
        for parts in names
        if len(parts) >= 2 and parts[1].casefold() in FORBIDDEN_RUNTIME_ITEMS
    )
    if forbidden:
        raise ReleaseArchiveError(
            "Private runtime data entered the release archive: " + ", ".join(forbidden)
        )

    root_files = {parts[1] for parts in names if len(parts) == 2}
    missing = sorted(REQUIRED_RELEASE_ITEMS - root_files)
    if missing:
        raise ReleaseArchiveError("Required release files are missing: " + ", ".join(missing))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a clean Windows release ZIP")
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    validate_release_archive(args.archive)
    print(f"Release archive verified: {args.archive.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
