from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def package(build_dir: Path, output_dir: Path, root: Path) -> Path:
    sys.path.insert(0, str(root / "firmware" / "scripts"))
    from build_metadata import resolve_build_id

    metadata = json.loads((root / "firmware" / "version.json").read_text(encoding="utf-8"))
    idedata = json.loads((build_dir / "idedata.json").read_text(encoding="utf-8"))
    sources = {
        int(item["offset"], 0): Path(item["path"])
        for item in idedata["extra"]["flash_images"]
    }
    application_offset = int(idedata["extra"]["application_offset"], 0)
    sources[application_offset] = build_dir / "firmware.bin"
    filenames = {
        0x1000: "bootloader.bin",
        0x8000: "partitions.bin",
        0xE000: "boot_app0.bin",
        application_offset: "firmware.bin",
    }
    missing = [hex(offset) for offset in filenames if offset not in sources or not sources[offset].is_file()]
    if missing:
        raise RuntimeError(f"Missing firmware images at offsets: {', '.join(missing)}")

    output_dir.mkdir(parents=True, exist_ok=True)
    images = []
    for offset, filename in filenames.items():
        destination = output_dir / filename
        shutil.copy2(sources[offset], destination)
        images.append(
            {
                "offset": hex(offset),
                "file": filename,
                "sha256": sha256(destination),
                "size": destination.stat().st_size,
            }
        )

    build = resolve_build_id(root)
    manifest = {
        "schema": 1,
        "version": str(metadata["version"]),
        "build": build,
        "board": str(metadata["board"]),
        "protocol": int(metadata["protocol"]),
        "usb": {"vid": "0x1a86", "pid": "0x55d4"},
        "baud": 921600,
        "update": {
            "preserves_settings": True,
            "images": [item for item in images if int(item["offset"], 0) == application_offset],
        },
        "factory": {
            "preserves_settings": False,
            "images": images,
        },
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    checksum_lines = [
        f"{item['sha256']}  {item['file']}"
        for item in images
    ]
    checksum_lines.append(f"{sha256(manifest_path)}  manifest.json")
    (output_dir / "SHA256SUMS.txt").write_text(
        "\n".join(checksum_lines) + "\n",
        encoding="ascii",
    )
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    manifest = package(args.build_dir.resolve(), args.output_dir.resolve(), args.root.resolve())
    print(f"Firmware package: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
