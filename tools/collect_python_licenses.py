from __future__ import annotations

import argparse
import re
import shutil
from email.message import Message
from importlib import metadata
from pathlib import Path, PurePosixPath

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


ROOT_REQUIREMENTS = (
    "fastapi",
    "uvicorn[standard]",
    "PyYAML",
    "pyperclip",
    "zeroconf",
    "pystray",
    "Pillow",
    "faster-whisper",
    "huggingface-hub",
    "esptool",
    "pyserial",
    # The bootloader is present in executables produced by PyInstaller.
    "pyinstaller",
)
LICENSE_WORDS = ("license", "copying", "notice", "copyright")


def _installed_distributions() -> dict[str, metadata.Distribution]:
    result: dict[str, metadata.Distribution] = {}
    for distribution in metadata.distributions():
        name = distribution.metadata.get("Name")
        if name:
            result.setdefault(canonicalize_name(name), distribution)
    return result


def _marker_applies(requirement: Requirement, extras: set[str]) -> bool:
    if requirement.marker is None:
        return True
    environment = default_environment()
    return any(
        requirement.marker.evaluate({**environment, "extra": extra})
        for extra in extras | {""}
    )


def dependency_closure(requirements: tuple[str, ...]) -> list[metadata.Distribution]:
    installed = _installed_distributions()
    requested_extras: dict[str, set[str]] = {}
    queue = [Requirement(item) for item in requirements]

    while queue:
        requirement = queue.pop()
        name = canonicalize_name(requirement.name)
        extras = set(requirement.extras) | {""}
        previous = requested_extras.setdefault(name, set())
        if extras.issubset(previous):
            continue
        previous.update(extras)
        distribution = installed.get(name)
        if distribution is None:
            raise RuntimeError(f"Required distribution is not installed: {requirement.name}")
        active_extras = requested_extras[name]
        for raw_dependency in distribution.requires or ():
            dependency = Requirement(raw_dependency)
            if _marker_applies(dependency, active_extras):
                queue.append(dependency)

    return [installed[name] for name in sorted(requested_extras)]


def _license_expression(message: Message) -> str:
    return (
        message.get("License-Expression")
        or message.get("License")
        or "Not declared in package metadata"
    ).strip()


def _project_urls(message: Message) -> list[str]:
    urls = []
    for value in message.get_all("Project-URL") or ():
        urls.append(value)
    home_page = message.get("Home-page")
    if home_page:
        urls.append(f"Home-page, {home_page}")
    return sorted(set(urls))


def _safe_relative_path(value: str) -> Path:
    parts = [part for part in PurePosixPath(value).parts if part not in (".", "..")]
    return Path(*parts)


def collect(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    rows = ["Package\tVersion\tLicense"]

    for distribution in dependency_closure(ROOT_REQUIREMENTS):
        message = distribution.metadata
        name = message.get("Name") or "unknown"
        version = distribution.version
        license_expression = _license_expression(message)
        folder_name = re.sub(r"[^A-Za-z0-9._-]+", "-", f"{name}-{version}")
        package_dir = output / folder_name
        package_dir.mkdir(parents=True, exist_ok=True)

        details = [
            f"Package: {name}",
            f"Version: {version}",
            f"License metadata: {license_expression}",
        ]
        urls = _project_urls(message)
        if urls:
            details.append("Project URLs:")
            details.extend(f"- {url}" for url in urls)
        (package_dir / "PACKAGE.txt").write_text("\n".join(details) + "\n", encoding="utf-8")

        copied: set[Path] = set()
        for entry in distribution.files or ():
            if not any(word in entry.name.casefold() for word in LICENSE_WORDS):
                continue
            source = Path(distribution.locate_file(entry))
            if not source.is_file():
                continue
            relative = _safe_relative_path(str(entry).replace("\\", "/"))
            destination = package_dir / relative
            if destination in copied:
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied.add(destination)

        single_line_license = re.sub(r"\s+", " ", license_expression)
        rows.append(f"{name}\t{version}\t{single_line_license}")

    (output / "INDEX.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect license metadata and texts for the Windows release dependency closure"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    collect(args.output.resolve())
    print(f"Third-party Python licenses: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
