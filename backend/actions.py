"""Action execution engine."""
from __future__ import annotations

import queue
import random
import threading
import time
import traceback
from typing import Any, Callable

from . import winutil
from .constants import MEDIA_ACTIONS
from .network import toggle_network_profile
from .volume import set_app_volume


class ActionEngine:
    def __init__(
        self,
        on_toast: Callable[[str, str], None] | None = None,
        on_layer: Callable[[str, int | None], None] | None = None,
        on_profile: Callable[[str, str | None], None] | None = None,
    ) -> None:
        self.on_toast = on_toast or (lambda message, kind="info": None)
        self.on_layer = on_layer or (lambda mode, index=None: None)
        self.on_profile = on_profile or (lambda mode, profile_id=None: None)
        self._queue: queue.Queue[tuple[dict[str, Any], bool]] = queue.Queue()
        self._thread = threading.Thread(target=self._worker, name="ActionEngine", daemon=True)
        self._running = True
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        try:
            self._queue.put_nowait(({"type": "none"}, False))
        except Exception:
            pass

    def submit(self, action: dict[str, Any] | None, test: bool = False) -> None:
        if not action:
            return
        self._queue.put((action, test))

    def _worker(self) -> None:
        while self._running:
            action, test = self._queue.get()
            if not self._running:
                break
            try:
                self.execute_now(action, test=test)
            except Exception as exc:
                traceback.print_exc()
                name = action.get("name") or "动作"
                self.on_toast(f"{name} 执行失败：{exc}", "error")

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute_now(self, action: dict[str, Any], test: bool = False) -> None:
        action = action or {}
        action_type = action.get("type") or "none"
        params = action.get("params") or {}
        name = action.get("name") or "动作"

        if action_type == "none":
            return
        if action_type == "key":
            self._do_key(params)
        elif action_type == "text":
            self._do_text(params)
        elif action_type == "open":
            winutil.open_target(
                params.get("target", ""),
                args=params.get("args", ""),
                cwd=params.get("cwd", ""),
                run_as_admin=bool(params.get("runAsAdmin")),
            )
        elif action_type == "command":
            winutil.run_command(
                params.get("command", ""),
                shell=params.get("shell", "powershell"),
                hidden=params.get("hidden", True),
                cwd=params.get("cwd", ""),
            )
        elif action_type == "media":
            key = MEDIA_ACTIONS.get(params.get("action", ""))
            if key:
                winutil.send_key(key)
        elif action_type == "app_volume":
            self._do_app_volume(params)
        elif action_type == "network_toggle":
            ok, message = toggle_network_profile()
            self.on_toast(message, "success" if ok else "warning")
        elif action_type == "mouse":
            self._do_mouse(params)
        elif action_type == "system":
            result = winutil.system_action(params.get("action", ""))
            if result:
                self.on_toast(f"已保存截图：{result}", "success")
        elif action_type == "clipboard":
            self._do_clipboard(params)
        elif action_type == "window":
            winutil.window_control(params.get("action", ""))
        elif action_type == "layer":
            self.on_layer(params.get("mode", "set"), params.get("index"))
        elif action_type == "profile":
            self.on_profile(params.get("mode", "set"), params.get("profileId"))
        elif action_type == "delay":
            time.sleep(max(0, int(params.get("ms", 100))) / 1000)
        elif action_type == "macro":
            self._do_macro(params)
        else:
            raise ValueError(f"未知动作类型：{action_type}")

        if test:
            self.on_toast(f"已测试：{name}", "success")

    def _do_key(self, params: dict[str, Any]) -> None:
        keys = params.get("keys") or []
        if isinstance(keys, str):
            keys = winutil.parse_combo_text(keys)
        mode = params.get("mode", "press")
        hold = int(params.get("hold", 0) or 0)
        if mode == "down":
            for key in keys:
                winutil.send_key(key, down=True, up=False)
        elif mode == "up":
            for key in reversed(keys):
                winutil.send_key(key, down=False, up=True)
        else:
            winutil.send_combo(keys, hold_ms=hold)

    def _do_text(self, params: dict[str, Any]) -> None:
        text = params.get("text", "")
        mode = params.get("mode", "type")
        if mode == "paste":
            winutil.paste_text(text)
        else:
            winutil.send_text(text, int(params.get("interval", 0) or 0))

    def _do_app_volume(self, params: dict[str, Any]) -> None:
        ok, message = set_app_volume(
            params.get("process", "cs2.exe"),
            params.get("mode", "toggle"),
        )
        self.on_toast(message, "success" if ok else "warning")

    def _do_mouse(self, params: dict[str, Any]) -> None:
        action = params.get("action", "left")
        if action in {"left", "right", "middle"}:
            winutil.mouse_click(action, int(params.get("count", 1) or 1))
        elif action == "double":
            winutil.mouse_click("left", 2)
        elif action == "wheel_up":
            winutil.mouse_wheel(int(params.get("delta", 120) or 120))
        elif action == "wheel_down":
            winutil.mouse_wheel(-abs(int(params.get("delta", 120) or 120)))
        elif action == "move_rel":
            winutil.mouse_move_rel(int(params.get("dx", 0) or 0), int(params.get("dy", 0) or 0))
        elif action == "move_abs":
            winutil.mouse_move_abs(float(params.get("x", 0) or 0), float(params.get("y", 0) or 0))

    def _do_clipboard(self, params: dict[str, Any]) -> None:
        action = params.get("action", "paste")
        if action == "set":
            winutil.set_clipboard_text(params.get("text", ""))
        elif action == "clear":
            winutil.set_clipboard_text("")
        elif action == "copy":
            winutil.send_combo(["Ctrl", "C"])
        elif action == "paste":
            winutil.send_combo(["Ctrl", "V"])
        elif action == "cut":
            winutil.send_combo(["Ctrl", "X"])
        elif action == "select_all":
            winutil.send_combo(["Ctrl", "A"])
        elif action == "undo":
            winutil.send_combo(["Ctrl", "Z"])

    def _do_macro(self, params: dict[str, Any]) -> None:
        steps = params.get("steps") or []
        repeat = max(1, min(999, int(params.get("repeat", 1) or 1)))
        interval = max(0, int(params.get("interval", 0) or 0))
        for i in range(repeat):
            for step in steps:
                self._do_step(step)
            if i < repeat - 1 and interval:
                time.sleep(interval / 1000)

    def _do_step(self, step: dict[str, Any]) -> None:
        step_type = step.get("type", "delay")
        if step_type == "key":
            self._do_key(step)
        elif step_type == "text":
            self._do_text(step)
        elif step_type == "delay":
            if "min" in step or "max" in step:
                lo = int(step.get("min", 0) or 0)
                hi = max(lo, int(step.get("max", lo) or lo))
                ms = random.randint(lo, hi)
            else:
                ms = int(step.get("ms", 100) or 0)
            time.sleep(max(0, ms) / 1000)
        elif step_type == "mouse":
            self._do_mouse(step)
        elif step_type == "media":
            key = MEDIA_ACTIONS.get(step.get("action", ""))
            if key:
                winutil.send_key(key)
        elif step_type == "app_volume":
            self._do_app_volume(step)
        elif step_type == "system":
            winutil.system_action(step.get("action", ""))
        elif step_type == "clipboard":
            self._do_clipboard(step)
        elif step_type == "window":
            winutil.window_control(step.get("action", ""))
        elif step_type == "open":
            winutil.open_target(
                step.get("target", ""),
                args=step.get("args", ""),
                cwd=step.get("cwd", ""),
                run_as_admin=bool(step.get("runAsAdmin")),
            )
        elif step_type == "command":
            winutil.run_command(
                step.get("command", ""),
                shell=step.get("shell", "powershell"),
                hidden=step.get("hidden", True),
                cwd=step.get("cwd", ""),
            )
        elif step_type == "delay_random":
            lo = int(step.get("min", 0) or 0)
            hi = max(lo, int(step.get("max", lo) or lo))
            time.sleep(random.randint(lo, hi) / 1000)
        else:
            raise ValueError(f"未知宏步骤：{step_type}")
