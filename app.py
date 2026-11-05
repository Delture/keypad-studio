"""Keypad Studio — entry point."""
from __future__ import annotations

import argparse
import ctypes
import json
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

import webview

from backend import winutil
from backend.api import Api
from backend.constants import APP_NAME
from backend.storage import data_dir
from backend.tray import Tray, ensure_icon

_MUTEX_HANDLE = None


def _message(text: str, title: str = APP_NAME) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(None, text, title, 0x00000040)
    except Exception:
        print(text)


def _debug_channel(api: Api, window) -> None:
    """Tiny file-based control channel used only with --debug."""
    folder = Path(tempfile.gettempdir())
    command_path = folder / "keypad-studio-command.json"
    result_path = folder / "keypad-studio-result.json"
    for path in (command_path, result_path):
        try:
            path.unlink()
        except OSError:
            pass
    while True:
        time.sleep(0.25)
        if not command_path.exists():
            continue
        result = None
        try:
            payload = json.loads(command_path.read_text(encoding="utf-8"))
            command_path.unlink()
            if "js" in payload:
                result = window.evaluate_js(payload["js"])
            elif "method" in payload:
                method = getattr(api, payload["method"])
                result = method(*payload.get("args", []), **payload.get("kwargs", {}))
            else:
                result = {"ok": False, "error": "需要 method 或 js"}
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
        try:
            result_path.write_text(json.dumps(result, ensure_ascii=False, default=str), encoding="utf-8")
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--minimized", action="store_true")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    global _MUTEX_HANDLE
    already, handle = winutil.create_single_instance_mutex()
    _MUTEX_HANDLE = handle
    if already:
        _message("Keypad Studio 已经在运行。\n请在任务栏或系统托盘中找到它。")
        return 0

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("KeypadStudio.1.4.1")
    except Exception:
        pass

    try:
        log_path = data_dir() / "app.log"
        log_file = open(log_path, "a", encoding="utf-8", buffering=1)
        sys.stdout = log_file
        sys.stderr = log_file
        print(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} start ---", flush=True)
    except Exception:
        pass

    ensure_icon(Path(__file__).resolve().parent / "assets")

    api = Api()
    url = (Path(__file__).resolve().parent / "web" / "index.html").as_uri()

    window = webview.create_window(
        APP_NAME,
        url=url,
        js_api=api,
        width=1280,
        height=830,
        min_size=(1080, 720),
        background_color="#0B0B10",
        hidden=bool(args.minimized),
        text_select=False,
        easy_drag=True,
    )
    api.attach_window(window)
    window.events.loaded += api.on_loaded
    window.events.closing += api.on_closing

    tray = Tray(api)
    api._tray = tray
    tray.start()

    if args.debug:
        threading.Thread(target=_debug_channel, args=(api, window), daemon=True).start()
        print("debug channel ready", flush=True)

    try:
        webview.start(gui="edgechromium", debug=args.debug, private_mode=False)
    except Exception as exc:
        traceback.print_exc()
        _message(
            "无法启动应用界面。\n\n"
            "请确认系统已安装 Microsoft Edge WebView2 Runtime。\n"
            f"错误：{exc}"
        )
        return 1
    finally:
        api.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
