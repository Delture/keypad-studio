"""Configuration persistence."""
from __future__ import annotations

import copy
import json
import os
import shutil
import threading
import uuid
from pathlib import Path
from typing import Any

from .constants import DEFAULT_TRIGGER_MAP, KEY_COUNT, VERSION


def _action(action_id: str, name: str, action_type: str, icon: str, params: dict[str, Any]) -> dict:
    return {
        "id": action_id,
        "name": name,
        "type": action_type,
        "icon": icon,
        "params": params,
    }


def default_state() -> dict[str, Any]:
    actions = [
        _action("act_copy", "复制", "key", "copy", {"keys": ["Ctrl", "C"], "mode": "press"}),
        _action("act_paste", "粘贴", "key", "paste", {"keys": ["Ctrl", "V"], "mode": "press"}),
        _action("act_undo", "撤销", "key", "undo", {"keys": ["Ctrl", "Z"], "mode": "press"}),
        _action("act_desktop", "显示桌面", "system", "monitor", {"action": "show_desktop"}),
        _action("act_browser", "打开浏览器", "open", "globe", {"target": "https://www.bing.com", "args": "", "cwd": "", "runAsAdmin": False}),
        _action("act_play", "播放 / 暂停", "media", "play", {"action": "play_pause"}),
        _action("act_cs2_volume", "CS2 音量", "app_volume", "volume", {"process": "cs2.exe", "mode": "toggle"}),
        _action("act_network_toggle", "网络切换", "network_toggle", "network", {}),
    ]
    default_bindings = [
        "act_cs2_volume",
        "act_paste",
        "act_undo",
        "act_desktop",
        "act_browser",
        "act_network_toggle",
    ]
    keys = {}
    for slot in range(1, KEY_COUNT + 1):
        keys[str(slot)] = {"action": default_bindings[slot - 1], "double": None}
    return {
        "version": 1,
        "settings": {
            "theme": "dark",
            "language": "zh",
            "autostart": False,
            "minimizeToTray": True,
            "startMinimized": False,
            "doublePressMs": 320,
            "syncBindingsOnStart": True,
            "deviceInitialized": False,
            "activeProfile": "profile_default",
            "activeLayer": 0,
            "autoProfileSwitch": True,
            "revertToDefault": True,
            "autoCheckUpdate": True,
        },
        "triggerMap": {str(k): v for k, v in DEFAULT_TRIGGER_MAP.items()},
        "actions": actions,
        "profiles": [
            {
                "id": "profile_default",
                "name": "默认配置",
                "color": "#8B5CF6",
                "match": [],
                "layers": [
                    {"name": "主层", "keys": keys},
                    {"name": "第二层", "keys": {str(i): {"action": None, "double": None} for i in range(1, KEY_COUNT + 1)}},
                ],
            }
        ],
    }


def data_dir() -> Path:
    root = Path(__file__).resolve().parent.parent
    if (root / "portable.txt").exists():
        path = root / "data"
    else:
        base = Path(os.environ.get("APPDATA", str(Path.home())))
        path = base / "KeypadStudio"
    path.mkdir(parents=True, exist_ok=True)
    return path


class ConfigStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (data_dir() / "config.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._state: dict[str, Any] = default_state()

    def load(self) -> dict[str, Any]:
        with self._lock:
            if not self.path.exists():
                self._state = default_state()
                self.save(self._state)
                return copy.deepcopy(self._state)
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                self._state = self.normalize(raw)
            except Exception:
                try:
                    backup = self.path.with_suffix(".corrupt.json")
                    shutil.copy2(self.path, backup)
                except Exception:
                    pass
                self._state = default_state()
                self.save(self._state)
            return copy.deepcopy(self._state)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._state)

    def save(self, state: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            normalized = self.normalize(state)
            self._state = normalized
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
            if self.path.exists():
                try:
                    shutil.copy2(self.path, self.path.with_suffix(".bak.json"))
                except Exception:
                    pass
            os.replace(tmp, self.path)
            return copy.deepcopy(normalized)

    # ------------------------------------------------------------------

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        base = default_state()
        if not isinstance(raw, dict):
            return base
        state = copy.deepcopy(raw)
        state.setdefault("version", 1)

        settings = base["settings"]
        settings.update(state.get("settings") or {})
        state["settings"] = settings

        actions = state.get("actions")
        if not isinstance(actions, list) or not actions:
            actions = base["actions"]
        clean_actions: list[dict] = []
        seen_ids: set[str] = set()
        for item in actions:
            if not isinstance(item, dict):
                continue
            item = copy.deepcopy(item)
            item.setdefault("id", "act_" + uuid.uuid4().hex[:10])
            if item["id"] in seen_ids:
                item["id"] = "act_" + uuid.uuid4().hex[:10]
            seen_ids.add(item["id"])
            item.setdefault("name", "未命名动作")
            item.setdefault("type", "none")
            item.setdefault("icon", "bolt")
            item.setdefault("params", {})
            if not isinstance(item["params"], dict):
                item["params"] = {}
            clean_actions.append(item)
        state["actions"] = clean_actions
        action_ids = {a["id"] for a in clean_actions}

        profiles = state.get("profiles")
        if not isinstance(profiles, list) or not profiles:
            profiles = base["profiles"]
        clean_profiles: list[dict] = []
        for profile in profiles:
            if not isinstance(profile, dict):
                continue
            profile = copy.deepcopy(profile)
            profile.setdefault("id", "profile_" + uuid.uuid4().hex[:8])
            profile.setdefault("name", "配置")
            profile.setdefault("color", "#8B5CF6")
            profile.setdefault("match", [])
            if not isinstance(profile["match"], list):
                profile["match"] = []
            layers = profile.get("layers")
            if not isinstance(layers, list) or not layers:
                layers = [{"name": "主层", "keys": {}}]
            clean_layers = []
            for index, layer in enumerate(layers):
                if not isinstance(layer, dict):
                    layer = {}
                layer = copy.deepcopy(layer)
                layer.setdefault("name", "主层" if index == 0 else f"第 {index + 1} 层")
                keys = layer.get("keys")
                if not isinstance(keys, dict):
                    keys = {}
                for slot in range(1, KEY_COUNT + 1):
                    binding = keys.get(str(slot))
                    if not isinstance(binding, dict):
                        binding = {"action": None, "double": None}
                    if binding.get("action") not in action_ids:
                        binding["action"] = None
                    if binding.get("double") not in action_ids:
                        binding["double"] = None
                    keys[str(slot)] = binding
                layer["keys"] = keys
                clean_layers.append(layer)
            profile["layers"] = clean_layers
            clean_profiles.append(profile)
        state["profiles"] = clean_profiles
        profile_ids = {p["id"] for p in clean_profiles}

        if state["settings"].get("activeProfile") not in profile_ids:
            state["settings"]["activeProfile"] = clean_profiles[0]["id"]
        active_profile = next(p for p in clean_profiles if p["id"] == state["settings"]["activeProfile"])
        layer_count = len(active_profile["layers"])
        layer = int(state["settings"].get("activeLayer", 0) or 0)
        state["settings"]["activeLayer"] = max(0, min(layer, layer_count - 1))

        trigger_map = state.get("triggerMap")
        if not isinstance(trigger_map, dict):
            trigger_map = {str(k): v for k, v in DEFAULT_TRIGGER_MAP.items()}
        clean_map = {}
        for key, value in trigger_map.items():
            try:
                clean_map[str(int(key))] = int(value)
            except Exception:
                continue
        if not clean_map:
            clean_map = {str(k): v for k, v in DEFAULT_TRIGGER_MAP.items()}
        state["triggerMap"] = clean_map
        return state
