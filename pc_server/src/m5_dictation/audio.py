from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path

from .protocol import RecordingStart


class AudioSessionError(RuntimeError):
    pass


@dataclass
class AudioSession:
    start: RecordingStart
    path: Path
    maximum_bytes: int
    _wave: wave.Wave_write
    bytes_received: int = 0
    closed: bool = False

    @classmethod
    def create(cls, start: RecordingStart, directory: Path, max_seconds: float) -> "AudioSession":
        directory.mkdir(parents=True, exist_ok=True)
        safe_device = "".join(c for c in start.device_id if c.isalnum() or c in "-_")
        path = directory / f"{safe_device}-{start.sequence}.wav"
        writer = wave.open(str(path), "wb")
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(start.sample_rate)
        return cls(start, path, int(start.sample_rate * 2 * max_seconds), writer)

    @property
    def duration_seconds(self) -> float:
        return self.bytes_received / (self.start.sample_rate * 2)

    def append(self, chunk: bytes) -> None:
        if self.closed:
            raise AudioSessionError("session is closed")
        if len(chunk) % 2:
            raise AudioSessionError("PCM chunk length must be even")
        if self.bytes_received + len(chunk) > self.maximum_bytes:
            raise AudioSessionError("maximum recording duration exceeded")
        self._wave.writeframesraw(chunk)
        self.bytes_received += len(chunk)

    def close(self) -> Path:
        if not self.closed:
            self._wave.close()
            self.closed = True
        return self.path

    def discard(self) -> None:
        self.close()
        self.path.unlink(missing_ok=True)

