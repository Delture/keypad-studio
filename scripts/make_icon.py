"""Generate the Keypad Studio app icon (warm charcoal + terracotta)."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 1024
BG = (30, 29, 28, 255)        # #1E1D1C
KEY = (245, 244, 239, 255)    # #F5F4EF
ACCENT = (217, 119, 87, 255)  # #D97757


def render() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((0, 0, SIZE - 1, SIZE - 1), radius=232, fill=BG)
    draw.rounded_rectangle((7, 7, SIZE - 8, SIZE - 8), radius=226, outline=(255, 255, 255, 22), width=5)

    key_w, key_h = 238, 240
    gap_x, gap_y = 56, 54
    cols, rows = 3, 2
    total_w = cols * key_w + (cols - 1) * gap_x
    total_h = rows * key_h + (rows - 1) * gap_y
    x0 = (SIZE - total_w) // 2
    y0 = (SIZE - total_h) // 2

    for row in range(rows):
        for col in range(cols):
            x = x0 + col * (key_w + gap_x)
            y = y0 + row * (key_h + gap_y)
            fill = ACCENT if (row, col) == (1, 2) else KEY
            draw.rounded_rectangle((x, y, x + key_w, y + key_h), radius=50, fill=fill)
            draw.rounded_rectangle((x + 18, y + 18, x + key_w - 18, y + key_h - 18), radius=34, fill=None,
                                   outline=(0, 0, 0, 18), width=3)
    return img


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    assets = root / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    img = render()
    img.resize((512, 512), Image.Resampling.LANCZOS).save(assets / "icon.png")
    img.save(
        assets / "icon.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(assets / "icon.png")
    print(assets / "icon.ico")


if __name__ == "__main__":
    main()
