from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence


SUPPORTED_USB_IDS = {(0x1A86, 0x55D4)}  # WCH CH9102 used by M5StickC Plus2.
# Retained so the renamed desktop app can update firmware released before VoxCortex.
INFO_PREFIX = "M5AI_INFO "


class FirmwareUpdateError(RuntimeError):
    pass


@dataclass(frozen=True)
class FirmwareImage:
    offset: int
    filename: str
    sha256: str


@dataclass(frozen=True)
class FirmwareManifest:
    directory: Path
    version: str
    build: str
    board: str
    protocol: int
    baud: int
    update_images: tuple[FirmwareImage, ...]
    factory_images: tuple[FirmwareImage, ...]

    @classmethod
    def load(cls, path: str | Path) -> "FirmwareManifest":
        manifest_path = Path(path).resolve()
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FirmwareUpdateError(f"Не удалось прочитать манифест: {manifest_path}") from exc
        if raw.get("schema") != 1:
            raise FirmwareUpdateError("Неподдерживаемая версия манифеста прошивки")

        def images(name: str) -> tuple[FirmwareImage, ...]:
            result = []
            for item in raw.get(name, {}).get("images", []):
                try:
                    offset = int(str(item["offset"]), 0)
                    filename = str(item["file"])
                    digest = str(item["sha256"]).lower()
                except (KeyError, TypeError, ValueError) as exc:
                    raise FirmwareUpdateError(f"Некорректная секция {name} в манифесте") from exc
                if Path(filename).name != filename or not re.fullmatch(r"[0-9a-f]{64}", digest):
                    raise FirmwareUpdateError(f"Некорректный файл в секции {name}")
                result.append(FirmwareImage(offset, filename, digest))
            if not result:
                raise FirmwareUpdateError(f"В манифесте отсутствует секция {name}")
            return tuple(result)

        try:
            version = str(raw["version"])
            build = str(raw["build"])
            board = str(raw["board"])
            protocol = int(raw["protocol"])
            baud = int(raw.get("baud", 921600))
        except (KeyError, TypeError, ValueError) as exc:
            raise FirmwareUpdateError("В манифесте отсутствуют обязательные поля") from exc
        parse_version(version)
        if not board or not build or protocol < 1 or baud <= 0:
            raise FirmwareUpdateError("Некорректные метаданные прошивки")
        return cls(
            manifest_path.parent,
            version,
            build,
            board,
            protocol,
            baud,
            images("update"),
            images("factory"),
        )

    def verify(self, *, factory: bool = False) -> tuple[FirmwareImage, ...]:
        images = self.factory_images if factory else self.update_images
        for image in images:
            path = self.directory / image.filename
            if not path.is_file():
                raise FirmwareUpdateError(f"Файл прошивки не найден: {path}")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != image.sha256:
                raise FirmwareUpdateError(f"Контрольная сумма не совпала: {image.filename}")
        return images


@dataclass(frozen=True)
class SerialDevice:
    port: str
    description: str
    serial_number: str = ""
    vid: int | None = None
    pid: int | None = None


@dataclass(frozen=True)
class DeviceInfo:
    board: str
    version: str
    build: str
    protocol: int
    device_id: str


def parse_version(value: str) -> tuple[int, int, int, str]:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:[-+]([0-9A-Za-z.-]+))?", value)
    if not match:
        raise FirmwareUpdateError(f"Некорректная версия прошивки: {value}")
    major, minor, patch = (int(match.group(index)) for index in range(1, 4))
    return major, minor, patch, match.group(4) or ""


def compare_versions(left: str, right: str) -> int:
    left_parts = parse_version(left)
    right_parts = parse_version(right)
    numeric = (left_parts[:3] > right_parts[:3]) - (left_parts[:3] < right_parts[:3])
    if numeric:
        return numeric
    left_suffix, right_suffix = left_parts[3], right_parts[3]
    if left_suffix == right_suffix:
        return 0
    if not left_suffix:
        return 1
    if not right_suffix:
        return -1
    return (left_suffix > right_suffix) - (left_suffix < right_suffix)


def discover_devices() -> list[SerialDevice]:
    try:
        from serial.tools import list_ports
    except ImportError as exc:
        raise FirmwareUpdateError("Не установлен pyserial") from exc
    devices = []
    for item in list_ports.comports():
        if (item.vid, item.pid) not in SUPPORTED_USB_IDS:
            continue
        devices.append(
            SerialDevice(
                port=str(item.device),
                description=str(item.description or "CH9102"),
                serial_number=str(item.serial_number or ""),
                vid=item.vid,
                pid=item.pid,
            )
        )
    return sorted(devices, key=lambda item: item.port.casefold())


def select_device(
    devices: Sequence[SerialDevice],
    requested_port: str | None,
    input_fn: Callable[[str], str] = input,
) -> SerialDevice:
    if requested_port:
        for device in devices:
            if device.port.casefold() == requested_port.casefold():
                return device
        # An explicit port remains usable for older USB bridges, but it is never
        # selected automatically because flashing an unrelated ESP32 is unsafe.
        return SerialDevice(requested_port, "порт указан вручную")
    if not devices:
        raise FirmwareUpdateError(
            "M5StickC Plus2 с USB-контроллером CH9102 не найден. "
            "Проверьте кабель и драйвер либо укажите --port COMx."
        )
    if len(devices) == 1:
        return devices[0]
    print("Найдено несколько подходящих устройств:")
    for index, device in enumerate(devices, 1):
        serial = f", USB {device.serial_number}" if device.serial_number else ""
        print(f"  {index}. {device.port} — {device.description}{serial}")
    answer = input_fn("Выберите номер устройства: ").strip()
    try:
        return devices[int(answer) - 1]
    except (ValueError, IndexError) as exc:
        raise FirmwareUpdateError("Некорректный номер устройства") from exc


def parse_device_info(line: str) -> DeviceInfo | None:
    marker = line.find(INFO_PREFIX)
    if marker < 0:
        return None
    try:
        raw = json.loads(line[marker + len(INFO_PREFIX) :].strip())
        return DeviceInfo(
            board=str(raw["board"]),
            version=str(raw["version"]),
            build=str(raw.get("build", "")),
            protocol=int(raw["protocol"]),
            device_id=str(raw.get("device_id", "")),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def query_device(port: str, timeout: float = 5.0) -> DeviceInfo | None:
    try:
        import serial
    except ImportError as exc:
        raise FirmwareUpdateError("Не установлен pyserial") from exc
    deadline = time.monotonic() + timeout
    try:
        with serial.Serial(port, 115200, timeout=0.25, write_timeout=1) as connection:
            connection.dtr = False
            connection.rts = False
            connection.reset_input_buffer()
            next_request = 0.0
            while time.monotonic() < deadline:
                now = time.monotonic()
                if now >= next_request:
                    connection.write(b"\nM5AI INFO\n")
                    connection.flush()
                    next_request = now + 1.0
                line = connection.readline().decode("utf-8", errors="ignore")
                info = parse_device_info(line)
                if info is not None:
                    return info
    except (OSError, serial.SerialException) as exc:
        raise FirmwareUpdateError(f"Не удалось открыть {port}: {exc}") from exc
    return None


def ensure_update_allowed(
    manifest: FirmwareManifest,
    current: DeviceInfo | None,
    *,
    force: bool,
) -> bool:
    if current is None:
        return True
    if current.board != manifest.board:
        raise FirmwareUpdateError(
            f"Подключена плата {current.board}, а пакет предназначен для {manifest.board}"
        )
    relation = compare_versions(current.version, manifest.version)
    if relation > 0 and not force:
        raise FirmwareUpdateError(
            f"На устройстве установлена более новая версия {current.version}; "
            "для понижения используйте --force"
        )
    if relation == 0 and current.build == manifest.build and not force:
        return False
    return True


def run_esptool(arguments: list[str]) -> None:
    try:
        import esptool
    except ImportError as exc:
        raise FirmwareUpdateError("Не установлен esptool") from exc
    try:
        esptool.main(arguments)
    except SystemExit as exc:
        if exc.code not in (0, None):
            raise FirmwareUpdateError(f"esptool завершился с кодом {exc.code}") from exc


def flash(
    manifest: FirmwareManifest,
    port: str,
    images: Sequence[FirmwareImage],
    *,
    factory: bool,
) -> None:
    common = ["--chip", "esp32", "--port", port, "--baud", str(manifest.baud)]
    if factory:
        run_esptool([*common, "erase-flash"])
    write = [*common, "write-flash"]
    for image in images:
        write.extend([hex(image.offset), str(manifest.directory / image.filename)])
    run_esptool(write)


def default_manifest_path() -> Path:
    base = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path.cwd()
    candidates = [base / "manifest.json", base / "firmware" / "manifest.json"]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[-1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="USB-обновление M5StickC Plus2")
    parser.add_argument("--manifest", type=Path, default=default_manifest_path())
    parser.add_argument("--port", help="COM-порт; по умолчанию CH9102 определяется автоматически")
    parser.add_argument("--factory", action="store_true", help="стереть настройки и прошить все разделы")
    parser.add_argument("--force", action="store_true", help="разрешить повторную прошивку или понижение")
    parser.add_argument("--yes", action="store_true", help="не запрашивать подтверждение")
    parser.add_argument("--list", action="store_true", help="только показать найденные устройства")
    parser.add_argument("--no-pause", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        devices = discover_devices()
        if args.list:
            if not devices:
                print("Подходящие USB-устройства не найдены")
            for device in devices:
                serial = f" · USB {device.serial_number}" if device.serial_number else ""
                print(f"{device.port} · {device.description}{serial}")
            return 0
        manifest = FirmwareManifest.load(args.manifest)
        images = manifest.verify(factory=args.factory)
        device = select_device(devices, args.port)
        print(f"Порт: {device.port} · {device.description}")
        current = query_device(device.port)
        if current is None:
            print("Текущую версию прочитать не удалось (возможно, установлена старая прошивка).")
        else:
            print(f"Устройство: {current.device_id or current.board}")
            print(f"Текущая прошивка: {current.version} ({current.build or 'без номера сборки'})")
        print(f"Прошивка из пакета: {manifest.version} ({manifest.build})")
        if not ensure_update_allowed(manifest, current, force=args.force):
            print("Прошивка уже актуальна.")
            return 0
        if not args.yes:
            warning = "Все настройки устройства будут удалены. " if args.factory else ""
            answer = input(f"{warning}Продолжить прошивку через {device.port}? [y/N] ")
            if answer.strip().casefold() not in {"y", "yes", "д", "да"}:
                print("Отменено.")
                return 0
        flash(manifest, device.port, images, factory=args.factory)
        print("Запись завершена. Проверяю запущенную прошивку…")
        time.sleep(2)
        updated = query_device(device.port, timeout=12.0)
        if updated is None:
            raise FirmwareUpdateError(
                "Прошивка записана, но устройство не подтвердило версию после перезагрузки"
            )
        if updated.board != manifest.board or updated.version != manifest.version:
            raise FirmwareUpdateError(
                f"После перезагрузки устройство сообщило версию {updated.version}"
            )
        print(f"Готово: {updated.device_id or updated.board}, FW {updated.version}.")
        return 0
    except FirmwareUpdateError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
