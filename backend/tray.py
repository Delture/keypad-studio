"""System tray integration."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


def ensure_icon(assets_dir: Path) -> Path:
    assets_dir.mkdir(parents=True, exist_ok=True)
    png = assets_dir / "icon.png"
    ico = assets_dir / "icon.ico"
    if png.exists() and ico.exists():
        return png

    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # warm charcoal rounded square, terracotta accent key
    draw.rounded_rectangle((3, 3, size - 4, size - 4), radius=58, fill=(30, 29, 28, 255))
    draw.rounded_rectangle((3, 3, size - 4, size - 4), radius=58, outline=(255, 255, 255, 45), width=2)
    # six keys, two rows of three
    key_w, key_h, gap = 60, 61, 14
    total_w = key_w * 3 + gap * 2
    start_x = (size - total_w) // 2
    start_y = (size - (key_h * 2 + gap)) // 2
    for row in range(2):
        for col in range(3):
            x = start_x + col * (key_w + gap)
            y = start_y + row * (key_h + gap)
            fill = (217, 119, 87, 255) if (row, col) == (1, 2) else (245, 244, 239, 255)
            draw.rounded_rectangle((x, y, x + key_w, y + key_h), radius=13, fill=fill)
    img.save(png)
    img.save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return png


class Tray:
    def __init__(self, api) -> None:
        self.api = api
        self.icon = None
        self._image_path = ensure_icon(Path(__file__).resolve().parent.parent / "assets")

    def _show(self, icon=None, item=None) -> None:
        try:
            if self.api._window:
                self.api._window.show()
                self.api._window.restore()
        except Exception:
            pass

    def _initialize(self, icon=None, item=None) -> None:
        try:
            self.api.device_action("initialize")
        except Exception:
            pass

    def _reconnect(self, icon=None, item=None) -> None:
        try:
            self.api.device_action("reconnect")
        except Exception:
            pass

    def _quit(self, icon=None, item=None) -> None:
        try:
            self.api.quit_app()
        except Exception:
            pass

    def start(self) -> None:
        try:
            import pystray

            image = Image.open(self._image_path)
            menu = pystray.Menu(
                pystray.MenuItem("显示主界面", self._show, default=True),
                pystray.MenuItem("初始化 6 个按键", self._initialize),
                pystray.MenuItem("重新连接设备", self._reconnect),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("退出 Keypad Studio", self._quit),
            )
            self.icon = pystray.Icon("KeypadStudio", image, "Keypad Studio", menu)
            self.icon.run_detached()
        except Exception as exc:
            print("tray failed:", exc)

    def stop(self) -> None:
        try:
            if self.icon:
                self.icon.stop()
        except Exception:
            pass
