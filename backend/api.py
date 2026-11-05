"""JS-facing API and runtime glue."""
from __future__ import annotations

import copy
import os
import threading
import time
import traceback
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

from . import winutil
from .actions import ActionEngine
from .constants import (
    ACTION_TYPES,
    CLIPBOARD_ACTIONS,
    KEY_COUNT,
    KEY_DISPLAY,
    KEY_GROUPS,
    MEDIA_LABELS,
    MOUSE_ACTIONS,
    SYSTEM_ACTIONS,
    VERSION,
    WINDOW_ACTIONS,
)
from .device import DeviceManager
from .peripherals import PeripheralHub
from .storage import ConfigStore, data_dir
from .updater import Updater


class Api:
    def __init__(self) -> None:
        self.store = ConfigStore()
        self.state = self.store.load()
        self.lock = threading.RLock()
        self.events: deque[dict] = deque(maxlen=400)
        self._window = None
        self._tray = None
        self.quitting = False
        self.calibration: dict[str, Any] = {"active": False, "index": 0, "order": []}
        self._pending: dict[int, threading.Timer] = {}
        self._auto_init_started = False
        self._auto_profile: str | None = None
        self._last_auto_poll = 0.0
        self._actions_by_id: dict[str, dict] = {}
        self._refresh_indexes()

        self.engine = ActionEngine(
            on_toast=self.toast,
            on_layer=self._on_layer_action,
            on_profile=self._on_profile_action,
        )
        self.device = DeviceManager(
            on_trigger=self._on_trigger,
            on_status=self._on_device_status,
        )
        self.peripherals = PeripheralHub()
        self.updater = Updater(emit=self._emit, on_quit=self.quit_app)
        self.device.trigger_map = {int(k): int(v) for k, v in self.state.get("triggerMap", {}).items()}

        self._monitor = threading.Thread(target=self._foreground_monitor, name="ForegroundMonitor", daemon=True)
        self._monitor.start()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _refresh_indexes(self) -> None:
        with self.lock:
            self._actions_by_id = {a["id"]: a for a in self.state.get("actions", [])}
            self.settings = self.state.setdefault("settings", {})
            self.trigger_map = {int(k): int(v) for k, v in self.state.get("triggerMap", {}).items()}
            self.device_initialized = bool(self.settings.get("deviceInitialized"))

    def _emit(self, event: dict[str, Any]) -> None:
        event.setdefault("ts", time.time())
        self.events.append(event)

    def toast(self, message: str, kind: str = "info") -> None:
        self._emit({"type": "toast", "message": message, "kind": kind})

    def _save(self) -> dict:
        saved = self.store.save(self.state)
        self.state = saved
        self._refresh_indexes()
        return saved

    def _current_profile(self) -> dict | None:
        pid = self.settings.get("activeProfile")
        for profile in self.state.get("profiles", []):
            if profile.get("id") == pid:
                return profile
        profiles = self.state.get("profiles", [])
        return profiles[0] if profiles else None

    def _current_layer(self) -> int:
        profile = self._current_profile()
        if not profile:
            return 0
        layers = profile.get("layers", [])
        return max(0, min(int(self.settings.get("activeLayer", 0) or 0), max(0, len(layers) - 1)))

    def _binding(self, slot: int) -> dict | None:
        profile = self._current_profile()
        if not profile:
            return None
        layers = profile.get("layers", [])
        if not layers:
            return None
        layer = layers[self._current_layer()]
        return (layer.get("keys") or {}).get(str(slot))

    def _profile_by_id(self, profile_id: str) -> dict | None:
        for profile in self.state.get("profiles", []):
            if profile.get("id") == profile_id:
                return profile
        return None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def attach_window(self, window) -> None:
        self._window = window

    def _on_device_status(self, status: dict) -> None:
        self._emit({"type": "device", "device": status})
        if status.get("connected"):
            if self.settings.get("deviceInitialized") and self.settings.get("syncBindingsOnStart", True):
                if not self._auto_init_started:
                    threading.Thread(target=self._auto_initialize, daemon=True).start()
        else:
            self._auto_init_started = False

    def on_loaded(self) -> None:
        self._emit({"type": "ready", "version": VERSION})
        self.device.start()
        if self.settings.get("autostart"):
            try:
                winutil.set_autostart(True)
            except Exception:
                pass
        self.updater.auto_check(bool(self.settings.get("autoCheckUpdate", True)))

    def on_closing(self) -> bool:
        if self.quitting or not self.settings.get("minimizeToTray", True):
            return True
        try:
            if self._window:
                self._window.hide()
            self.toast("已最小化到托盘，点击托盘图标可重新打开", "info")
        except Exception:
            pass
        return False

    def shutdown(self) -> None:
        self.quitting = True
        for timer in list(self._pending.values()):
            try:
                timer.cancel()
            except Exception:
                pass
        self.device.stop()
        self.engine.stop()
        try:
            if self._tray:
                self._tray.stop()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # State API
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        with self.lock:
            return {
                "config": copy.deepcopy(self.state),
                "device": self.device.status(),
                "runtime": {
                    "version": VERSION,
                    "dataDir": str(data_dir()),
                    "calibration": copy.deepcopy(self.calibration),
                    "autostart": winutil.is_autostart_enabled(),
                    "update": self.updater.state(),
                },
                "meta": {
                    "actionTypes": ACTION_TYPES,
                    "keyGroups": KEY_GROUPS,
                    "keyDisplay": KEY_DISPLAY,
                    "mediaActions": MEDIA_LABELS,
                    "systemActions": SYSTEM_ACTIONS,
                    "clipboardActions": CLIPBOARD_ACTIONS,
                    "windowActions": WINDOW_ACTIONS,
                    "mouseActions": MOUSE_ACTIONS,
                },
            }

    def hub_state(self) -> dict:
        try:
            return {"ok": True, "hub": self.peripherals.snapshot()}
        except Exception as exc:
            traceback.print_exc()
            return {"ok": False, "error": str(exc)}

    def hub_action(self, action: str, payload: dict | None = None) -> dict:
        payload = payload or {}
        try:
            if action == "report_rate":
                self.peripherals.set_report_rate(int(payload.get("code")))
            elif action == "dpi":
                self.peripherals.set_dpi(int(payload.get("stage")), int(payload.get("dpi")))
            elif action == "stage":
                self.peripherals.set_active_stage(int(payload.get("stage")))
            elif action != "refresh":
                return {"ok": False, "error": f"未知操作：{action}"}
            return {"ok": True, "hub": self.peripherals.snapshot()}
        except Exception as exc:
            traceback.print_exc()
            return {"ok": False, "error": str(exc)}

    def update_state(self) -> dict:
        return {"ok": True, "update": self.updater.state()}

    def update_check(self) -> dict:
        return self.updater.check_async()

    def update_download(self) -> dict:
        return self.updater.begin_install()

    def update_apply(self) -> dict:
        return self.updater.apply()

    def open_url(self, url: str) -> dict:
        url = str(url or "").strip()
        if not url.lower().startswith(("https://github.com/", "https://api.github.com/")):
            return {"ok": False, "error": "不支持的链接"}
        try:
            winutil.open_target(url)
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def save_config(self, config: dict) -> dict:
        try:
            with self.lock:
                previous = copy.deepcopy(self.state.get("settings", {}))
                self.state = config
                saved = self._save()
                # apply autostart changes
                if bool(previous.get("autostart")) != bool(saved["settings"].get("autostart")):
                    winutil.set_autostart(bool(saved["settings"].get("autostart")))
                self.device.trigger_map = {int(k): int(v) for k, v in saved.get("triggerMap", {}).items()}
                self._emit({"type": "config", "config": copy.deepcopy(saved)})
                return {"ok": True, "config": copy.deepcopy(saved)}
        except Exception as exc:
            traceback.print_exc()
            return {"ok": False, "error": str(exc)}

    def set_settings(self, patch: dict) -> dict:
        with self.lock:
            settings = self.state.setdefault("settings", {})
            settings.update(patch or {})
            saved = self._save()
            if "autostart" in (patch or {}):
                winutil.set_autostart(bool(settings.get("autostart")))
            self._emit({"type": "config", "config": copy.deepcopy(saved)})
            return {"ok": True, "config": copy.deepcopy(saved)}

    def set_active_profile(self, profile_id: str) -> dict:
        with self.lock:
            if not self._profile_by_id(profile_id):
                return {"ok": False, "error": "配置不存在"}
            self.settings["activeProfile"] = profile_id
            self.settings["activeLayer"] = 0
            self._auto_profile = None
            self._save()
            self._emit_profile_changed()
            return {"ok": True}

    def set_active_layer(self, index: int) -> dict:
        with self.lock:
            profile = self._current_profile()
            if not profile:
                return {"ok": False, "error": "没有配置"}
            layers = profile.get("layers", [])
            index = max(0, min(int(index), max(0, len(layers) - 1)))
            self.settings["activeLayer"] = index
            self._save()
            self._emit_layer_changed()
            return {"ok": True}

    def poll_events(self) -> list[dict]:
        events = []
        while self.events:
            try:
                events.append(self.events.popleft())
            except IndexError:
                break
        return events

    # ------------------------------------------------------------------
    # Device API
    # ------------------------------------------------------------------

    def device_action(self, action: str, payload: dict | None = None) -> dict:
        action = (action or "").lower()
        kwargs = payload or {}
        if action == "reconnect":
            ok = self.device.reconnect()
            if ok and self.settings.get("deviceInitialized") and self.settings.get("syncBindingsOnStart", True):
                threading.Thread(target=self._auto_initialize, daemon=True).start()
            return {"ok": ok, "device": self.device.status()}
        if action == "initialize":
            ok = self.device.initialize_keys()
            if ok:
                self.settings["deviceInitialized"] = True
                self.state["triggerMap"] = {str(k): v for k, v in self.device.trigger_map.items()}
                self._save()
                self.toast("6 个按键已初始化，可以开始使用了", "success")
                self._emit({"type": "device", "device": self.device.status()})
            else:
                self.toast(self.device.last_error or "初始化失败", "error")
            return {"ok": ok, "device": self.device.status()}
        if action == "log":
            return {"ok": True, "log": self.device.raw_log()}
        if action == "send_raw":
            try:
                payload = bytes.fromhex(str(kwargs.get("payload", "")).replace(" ", ""))
                ok = self.device.send_raw(payload)
                return {"ok": ok, "device": self.device.status()}
            except Exception as exc:
                return {"ok": False, "error": str(exc)}
        if action == "read":
            data = self.device.read_test(int(kwargs.get("timeout", 500)))
            return {"ok": bool(data), "hex": data.hex(" ").upper() if data else ""}
        if action == "simulate":
            slot = int(kwargs.get("slot", 1))
            trigger = self._trigger_for_slot(slot)
            if trigger is None:
                return {"ok": False, "error": "找不到按键映射"}
            self._on_trigger(trigger)
            return {"ok": True}
        if action == "start_calibration":
            self.start_calibration()
            return {"ok": True, "calibration": copy.deepcopy(self.calibration)}
        if action == "cancel_calibration":
            self.calibration = {"active": False, "index": 0, "order": []}
            self._emit({"type": "calibration", "calibration": copy.deepcopy(self.calibration)})
            return {"ok": True}
        return {"ok": False, "error": "未知设备操作"}

    def _trigger_for_slot(self, slot: int) -> int | None:
        for trigger, mapped in self.trigger_map.items():
            if int(mapped) == int(slot):
                return int(trigger)
        return None

    def _auto_initialize(self) -> None:
        if self._auto_init_started:
            return
        self._auto_init_started = True
        try:
            if self.device.initialize_keys():
                self.settings["deviceInitialized"] = True
                self.state["triggerMap"] = {str(k): v for k, v in self.device.trigger_map.items()}
                self._save()
                self._emit({"type": "device", "device": self.device.status()})
            else:
                self.toast(self.device.last_error or "自动初始化按键失败", "warning")
        finally:
            time.sleep(0.5)
            self._auto_init_started = False

    def start_calibration(self) -> None:
        self.calibration = {"active": True, "index": 0, "order": []}
        self._emit({"type": "calibration", "calibration": copy.deepcopy(self.calibration)})
        self.toast("请按最左边的键开始校准", "info")

    # ------------------------------------------------------------------
    # Triggers / actions
    # ------------------------------------------------------------------

    def _on_trigger(self, trigger_id: int) -> None:
        try:
            if self.calibration.get("active"):
                self._calibration_trigger(trigger_id)
                return
            slot = self.trigger_map.get(int(trigger_id))
            if slot is None:
                # Fall back to 1..6 when the map is unknown.
                slot = trigger_id if 1 <= trigger_id <= KEY_COUNT else None
            if slot is None or not (1 <= slot <= KEY_COUNT):
                self._emit({"type": "raw_trigger", "trigger": trigger_id})
                return
            binding = self._binding(int(slot))
            if not binding:
                self._emit({"type": "key", "slot": int(slot), "actionName": "未绑定", "actionId": None})
                return
            action_id = binding.get("action")
            double_id = binding.get("double")
            action = self._actions_by_id.get(action_id) if action_id else None
            double_action = self._actions_by_id.get(double_id) if double_id else None

            self._emit({
                "type": "key",
                "slot": int(slot),
                "actionName": (action or {}).get("name") or "未绑定",
                "actionId": action_id,
                "actionType": (action or {}).get("type"),
                "actionIcon": (action or {}).get("icon"),
                "double": bool(double_action),
            })

            if double_action:
                pending = self._pending.pop(int(slot), None)
                if pending is not None:
                    pending.cancel()
                    self._emit({"type": "key", "slot": int(slot), "actionName": double_action.get("name", ""), "actionId": double_id, "doubleFired": True})
                    self.engine.submit(double_action)
                    return
                delay = max(80, min(1500, int(self.settings.get("doublePressMs", 320) or 320))) / 1000
                timer = threading.Timer(delay, self._fire_single, args=(int(slot), action))
                timer.daemon = True
                self._pending[int(slot)] = timer
                timer.start()
            else:
                if action:
                    self.engine.submit(action)
        except Exception:
            traceback.print_exc()

    def _fire_single(self, slot: int, action: dict | None) -> None:
        self._pending.pop(slot, None)
        if action:
            self.engine.submit(action)

    def _calibration_trigger(self, trigger_id: int) -> None:
        order = self.calibration.setdefault("order", [])
        order.append(int(trigger_id))
        self.calibration["index"] = len(order)
        if len(order) >= KEY_COUNT:
            mapping = {str(trigger): index + 1 for index, trigger in enumerate(order[:KEY_COUNT])}
            self.state["triggerMap"] = mapping
            self.trigger_map = {int(k): v for k, v in mapping.items()}
            self.device.trigger_map = dict(self.trigger_map)
            self._save()
            self.calibration["active"] = False
            self.toast("按键顺序校准完成", "success")
        else:
            self.toast(f"已记录键 {len(order)}，请按下一个", "info")
        self._emit({"type": "calibration", "calibration": copy.deepcopy(self.calibration)})

    def test_action(self, action: dict) -> dict:
        try:
            self.engine.submit(action, test=True)
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _on_layer_action(self, mode: str, index: int | None = None) -> None:
        with self.lock:
            profile = self._current_profile()
            if not profile:
                return
            layers = profile.get("layers", [])
            if not layers:
                return
            current = self._current_layer()
            mode = (mode or "set").lower()
            if mode == "set":
                target = int(index or 0)
            elif mode == "toggle":
                target = 0 if current == int(index or 1) else int(index or 1)
            elif mode == "next":
                target = (current + 1) % len(layers)
            elif mode == "prev":
                target = (current - 1) % len(layers)
            else:
                target = current
            target = max(0, min(target, len(layers) - 1))
            self.settings["activeLayer"] = target
            self._save()
            self._emit_layer_changed()
            self.toast(f"已切换到「{layers[target].get('name', '图层')}」", "info")

    def _on_profile_action(self, mode: str, profile_id: str | None = None) -> None:
        with self.lock:
            profiles = self.state.get("profiles", [])
            if not profiles:
                return
            mode = (mode or "set").lower()
            current_id = self.settings.get("activeProfile")
            current_index = next((i for i, p in enumerate(profiles) if p.get("id") == current_id), 0)
            if mode == "set" and profile_id:
                target = self._profile_by_id(profile_id)
            elif mode == "next":
                target = profiles[(current_index + 1) % len(profiles)]
            elif mode == "prev":
                target = profiles[(current_index - 1) % len(profiles)]
            else:
                target = None
            if not target:
                return
            self.settings["activeProfile"] = target["id"]
            self.settings["activeLayer"] = 0
            self._auto_profile = None
            self._save()
            self._emit_profile_changed()
            self.toast(f"已切换到「{target.get('name', '配置')}」", "info")

    def _emit_layer_changed(self) -> None:
        profile = self._current_profile() or {}
        layers = profile.get("layers", [])
        index = self._current_layer()
        self._emit({
            "type": "layer",
            "layer": index,
            "layerName": (layers[index].get("name") if layers else "主层"),
            "profileId": profile.get("id"),
        })

    def _emit_profile_changed(self) -> None:
        profile = self._current_profile() or {}
        self._emit({
            "type": "profile",
            "profileId": profile.get("id"),
            "profileName": profile.get("name", ""),
            "layer": self._current_layer(),
        })

    # ------------------------------------------------------------------
    # Foreground app profile switching
    # ------------------------------------------------------------------

    def _foreground_monitor(self) -> None:
        while True:
            time.sleep(0.8)
            try:
                if not self.settings.get("autoProfileSwitch", True):
                    continue
                if self.calibration.get("active"):
                    continue
                process = winutil.get_foreground_process_name()
                if not process:
                    continue
                # never auto-switch based on our own process
                if process in {"python.exe", "pythonw.exe", getattr(self, "exe_name", "")}:
                    matched = None
                else:
                    matched = None
                    for profile in self.state.get("profiles", []):
                        matches = [str(m).lower().replace(".exe", "") for m in profile.get("match", [])]
                        if process.replace(".exe", "") in matches:
                            matched = profile
                            break
                if matched:
                    if self.settings.get("activeProfile") != matched["id"]:
                        self.settings["activeProfile"] = matched["id"]
                        self.settings["activeLayer"] = 0
                        self._auto_profile = matched["id"]
                        self._save()
                        self._emit_profile_changed()
                        self.toast(f"已自动切换到「{matched.get('name')}」", "info")
                else:
                    if self.settings.get("revertToDefault", True) and self._auto_profile:
                        default = self.state.get("profiles", [{}])[0]
                        if default and self.settings.get("activeProfile") != default.get("id"):
                            self.settings["activeProfile"] = default.get("id")
                            self.settings["activeLayer"] = 0
                            self._save()
                            self._emit_profile_changed()
                        self._auto_profile = None
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Window / OS helpers
    # ------------------------------------------------------------------

    def window_control(self, action: str) -> dict:
        action = (action or "").lower()
        try:
            if not self._window:
                return {"ok": False}
            if action == "minimize":
                self._window.minimize()
            elif action == "maximize":
                self._window.maximize()
            elif action == "restore":
                self._window.restore()
            elif action == "hide":
                self._window.hide()
            elif action == "show":
                self._window.show()
                self._window.restore()
            elif action == "close":
                if self.settings.get("minimizeToTray", True):
                    self._window.hide()
                else:
                    self.quit_app()
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def quit_app(self) -> dict:
        self.quitting = True
        try:
            if self._tray:
                self._tray.stop()
        except Exception:
            pass
        try:
            if self._window:
                self._window.destroy()
        except Exception:
            pass
        return {"ok": True}

    def open_data_dir(self) -> dict:
        try:
            winutil.open_data_folder(str(data_dir()))
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def set_autostart(self, enabled: bool) -> dict:
        try:
            winutil.set_autostart(bool(enabled))
            self.settings["autostart"] = bool(enabled)
            self._save()
            return {"ok": True, "enabled": bool(enabled)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def choose_path(self, kind: str = "file", save: bool = False) -> dict:
        try:
            import webview

            if not self._window:
                return {"ok": False}
            if kind == "folder":
                result = self._window.create_file_dialog(webview.FOLDER_DIALOG)
                path = result[0] if result else ""
            else:
                file_types = ("所有文件 (*.*)",) if kind == "file" else ("程序 (*.exe;*.bat;*.cmd;*.lnk)", "所有文件 (*.*)")
                dialog = webview.SAVE_DIALOG if save else webview.OPEN_DIALOG
                result = self._window.create_file_dialog(dialog, file_types=file_types)
                path = result if isinstance(result, str) else (result[0] if result else "")
            return {"ok": True, "path": path or ""}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def export_config(self) -> dict:
        try:
            import webview

            if not self._window:
                return {"ok": False}
            result = self._window.create_file_dialog(
                webview.SAVE_DIALOG,
                save_filename=f"keypad-studio-{datetime.now().strftime('%Y%m%d')}.json",
                file_types=("JSON (*.json)",),
            )
            path = result if isinstance(result, str) else (result[0] if result else "")
            if not path:
                return {"ok": False, "cancelled": True}
            import json

            Path(path).write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")
            return {"ok": True, "path": path}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def import_config(self) -> dict:
        try:
            import webview

            if not self._window:
                return {"ok": False}
            result = self._window.create_file_dialog(webview.OPEN_DIALOG, file_types=("JSON (*.json)", "所有文件 (*.*)"))
            path = result[0] if result else ""
            if not path:
                return {"ok": False, "cancelled": True}
            import json

            data = json.loads(Path(path).read_text(encoding="utf-8"))
            with self.lock:
                self.state = data
                saved = self._save()
                self.device.trigger_map = {int(k): int(v) for k, v in saved.get("triggerMap", {}).items()}
                self._emit({"type": "config", "config": copy.deepcopy(saved)})
            self.toast("配置已导入", "success")
            return {"ok": True, "config": copy.deepcopy(self.state)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
