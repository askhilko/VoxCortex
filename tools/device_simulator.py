#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import math
import struct
import tempfile
import wave
from pathlib import Path
from typing import Iterator


LEGACY_FIELDS = {
    "copy": ("clipboard", "insert"),
    "paste": ("chatgpt", "insert"),
    "paste_enter": ("terminal", "enter"),
    "paste_ctrl_enter": ("vscode", "ctrl_enter"),
}


def generate_test_wav(path: Path, duration: float = 1.0, frequency: float = 440.0) -> Path:
    """Generate a license-free tone WAV for transport/integration testing."""
    sample_rate = 16000
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        for index in range(int(sample_rate * duration)):
            envelope = min(1.0, index / 800, (sample_rate * duration - index) / 800)
            sample = int(6000 * envelope * math.sin(2 * math.pi * frequency * index / sample_rate))
            output.writeframesraw(struct.pack("<h", sample))
    return path


def pcm_chunks(path: Path, chunk_bytes: int) -> Iterator[bytes]:
    with wave.open(str(path), "rb") as source:
        if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, 16000):
            raise ValueError("WAV must be mono, PCM 16-bit, 16000 Hz")
        while chunk := source.readframes(chunk_bytes // 2):
            yield chunk


async def simulate(args: argparse.Namespace) -> int:
    try:
        import websockets
    except ImportError as exc:
        raise SystemExit("Install simulator dependencies: pip install -e 'pc_server[test]'") from exc

    uri = f"ws://{args.host}:{args.port}/ws"
    wav_path: Path
    temporary: tempfile.TemporaryDirectory[str] | None = None
    if args.wav:
        wav_path = Path(args.wav)
    else:
        temporary = tempfile.TemporaryDirectory(prefix="m5-simulator-")
        wav_path = generate_test_wav(Path(temporary.name) / "test-tone.wav", args.duration)

    try:
        async with websockets.connect(uri, max_size=1_000_000) as socket:
            print("<", await socket.recv())
            profile, mode = LEGACY_FIELDS[args.action]
            await socket.send(json.dumps({
                "type": "hello",
                "protocol_version": 1,
                "device_id": args.device_id,
                "device_name": "Python simulator",
            }))
            print("<", await socket.recv())
            await socket.send(json.dumps({
                "type": "recording_start",
                "protocol_version": 1,
                "device_id": args.device_id,
                "sample_rate": 16000,
                "channels": 1,
                "sample_format": "pcm_s16le",
                "sequence": args.sequence,
                "action": args.action,
                "profile": profile,
                "mode": mode,
            }))
            print("<", await socket.recv())
            for chunk in pcm_chunks(wav_path, args.chunk_bytes):
                await socket.send(chunk)
                if args.realtime:
                    await asyncio.sleep(len(chunk) / 32000)
            await socket.send(json.dumps({
                "type": "recording_end",
                "protocol_version": 1,
                "sequence": args.sequence,
                "cancelled": args.cancel,
            }))
            while True:
                raw = await asyncio.wait_for(socket.recv(), timeout=args.timeout)
                print("<", raw)
                message = json.loads(raw)
                if message.get("state") in {"sent", "cancelled", "error"}:
                    return 0 if message.get("state") != "error" else 1
    finally:
        if temporary:
            temporary.cleanup()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Simulate M5StickC Plus2 audio protocol")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--device-id", default="m5stick-simulator")
    parser.add_argument("--sequence", type=int, default=1)
    parser.add_argument("--wav", help="16 kHz mono PCM16 WAV; generated tone is used if omitted")
    parser.add_argument("--duration", type=float, default=1.0)
    parser.add_argument("--chunk-bytes", type=int, default=1024)
    parser.add_argument(
        "--action",
        choices=["copy", "paste", "paste_enter", "paste_ctrl_enter"],
        default="copy",
    )
    parser.add_argument("--cancel", action="store_true")
    parser.add_argument("--realtime", action="store_true")
    parser.add_argument("--timeout", type=float, default=120.0)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.chunk_bytes <= 0 or args.chunk_bytes % 2:
        raise SystemExit("--chunk-bytes must be a positive even number")
    raise SystemExit(asyncio.run(simulate(args)))


if __name__ == "__main__":
    main()
