from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw


COLORS = {
    "starting": "#D79B21",
    "running": "#25A866",
    "stopped": "#68717D",
    "error": "#D64545",
}


def create_tray_image(state: str = "running", size: int = 64) -> Image.Image:
    """Create a crisp microphone icon that remains legible at tray size."""
    scale = size / 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    color = COLORS.get(state, COLORS["stopped"])
    draw.rounded_rectangle((2 * scale, 2 * scale, 62 * scale, 62 * scale), 14 * scale, fill=color)
    white = "#FFFFFF"
    draw.rounded_rectangle((25 * scale, 12 * scale, 39 * scale, 39 * scale), 7 * scale, fill=white)
    draw.arc((18 * scale, 22 * scale, 46 * scale, 50 * scale), 0, 180, fill=white, width=max(2, round(4 * scale)))
    draw.rounded_rectangle((30 * scale, 45 * scale, 34 * scale, 54 * scale), 2 * scale, fill=white)
    draw.rounded_rectangle((23 * scale, 52 * scale, 41 * scale, 57 * scale), 2 * scale, fill=white)
    return image


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the Windows tray/application icon")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    create_tray_image(size=256).save(output, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


if __name__ == "__main__":
    main()
