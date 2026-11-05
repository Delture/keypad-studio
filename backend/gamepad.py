"""XInput support for the Rainbow 2 SE (and other XInput-compatible pads).

XInput exposes live buttons/sticks/triggers, rumble and a coarse battery
report.  It does not expose vendor settings such as remapping, gyro curves,
macros or firmware information; those need the vendor's private protocol and
are intentionally kept out of this module.
"""
from __future__ import annotations

import ctypes
import os
import threading
import time
from ctypes import wintypes
from typing import Any

GAMEPAD_VID = 0x413D
GAMEPAD_PID = 0x2104

ERROR_DEVICE_NOT_CONNECTED = 1167

BATTERY_TYPE_DISCONNECTED = 0
BATTERY_TYPE_WIRED = 1
BATTERY_TYPE_ALKALINE = 2
BATTERY_TYPE_NIMH = 3
BATTERY_TYPE_LITHIUM = 4

BATTERY_PERCENT = {0: 5, 1: 25, 2: 60, 3: 100}
BATTERY_LEVEL_LABEL = {0: "电量低", 1: "偏低", 2: "中等", 3: "充足"}
BATTERY_TYPE_LABEL = {
    BATTERY_TYPE_DISCONNECTED: "未连接",
    BATTERY_TYPE_WIRED: "有线供电",
    BATTERY_TYPE_ALKALINE: "碱性电池",
    BATTERY_TYPE_NIMH: "镍氢电池",
    BATTERY_TYPE_LITHIUM: "锂电池",
}

BUTTON_FLAGS = {
    "up": 0x0001,
    "down": 0x0002,
    "left": 0x0004,
    "right": 0x0008,
    "start": 0x0010,
    "back": 0x0020,
    "l3": 0x0040,
    "r3": 0x0080,
    "lb": 0x0100,
    "rb": 0x0200,
    "a": 0x1000,
    "b": 0x2000,
    "x": 0x4000,
    "y": 0x8000,
}


class GamepadError(RuntimeError):
    pass


class _XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [
        ("wButtons", wintypes.WORD),
        ("bLeftTrigger", wintypes.BYTE),
        ("bRightTrigger", wintypes.BYTE),
        ("sThumbLX", ctypes.c_short),
        ("sThumbLY", ctypes.c_short),
        ("sThumbRX", ctypes.c_short),
        ("sThumbRY", ctypes.c_short),
    ]


class _XINPUT_STATE(ctypes.Structure):
    _fields_ = [
        ("dwPacketNumber", wintypes.DWORD),
        ("Gamepad", _XINPUT_GAMEPAD),
    ]


class _XINPUT_VIBRATION(ctypes.Structure):
    _fields_ = [
        ("wLeftMotorSpeed", wintypes.WORD),
        ("wRightMotorSpeed", wintypes.WORD),
    ]


class _XINPUT_BATTERY_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BatteryType", wintypes.BYTE),
        ("BatteryLevel", wintypes.BYTE),
    ]


_lib_lock = threading.Lock()
_lib: Any = None
_lib_loaded = False


def _load_xinput() -> Any:
    """Load the first available XInput DLL once, or return None."""
    global _lib, _lib_loaded
    with _lib_lock:
        if _lib_loaded:
            return _lib
        _lib_loaded = True
        if os.name != "nt":
            return None
        for name in ("xinput1_4.dll", "xinput1_3.dll", "xinput9_1_0.dll"):
            try:
                lib = ctypes.WinDLL(name)
            except OSError:
                continue
            try:
                lib.XInputGetState.argtypes = [wintypes.DWORD, ctypes.POINTER(_XINPUT_STATE)]
                lib.XInputGetState.restype = wintypes.DWORD
                lib.XInputSetState.argtypes = [wintypes.DWORD, ctypes.POINTER(_XINPUT_VIBRATION)]
                lib.XInputSetState.restype = wintypes.DWORD
            except AttributeError:
                continue
            try:
                lib.XInputGetBatteryInformation.argtypes = [
                    wintypes.DWORD,
                    wintypes.BYTE,
                    ctypes.POINTER(_XINPUT_BATTERY_INFORMATION),
                ]
                lib.XInputGetBatteryInformation.restype = wintypes.DWORD
            except AttributeError:
                pass
            _lib = lib
            return lib
        return None


class GamepadManager:
    """Poll the first connected XInput pad and drive its rumble motors."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self._link_ts = 0.0
        self._link_cache: dict[str, Any] = {"receiver": False, "product": None}
        self._stop_timer: threading.Timer | None = None

    # ------------------------------------------------------------------
    # Discovery / state
    # ------------------------------------------------------------------

    @staticmethod
    def _find_slot(lib: Any) -> tuple[int | None, Any | None]:
        for slot in range(4):
            state = _XINPUT_STATE()
            if lib.XInputGetState(slot, ctypes.byref(state)) == 0:
                return slot, state
        return None, None

    @staticmethod
    def _read_battery(lib: Any, slot: int) -> tuple[int, int] | None:
        getter = getattr(lib, "XInputGetBatteryInformation", None)
        if getter is None:
            return None
        info = _XINPUT_BATTERY_INFORMATION()
        try:
            if getter(slot, 0, ctypes.byref(info)) != 0:
                return None
        except Exception:
            return None
        return int(info.BatteryType), int(info.BatteryLevel)

    def _link_info(self) -> dict[str, Any]:
        """Check the USB receiver via hidapi, cached for a few seconds.

        XInput reports the 2.4G receiver as ``wired`` because the receiver is
        USB-powered, so the HID manufacturer string is the reliable way to
        tell "receiver" from "data cable".
        """
        now = time.time()
        with self.lock:
            if now - self._link_ts < 8.0:
                return self._link_cache
        receiver = False
        product = None
        try:
            import hid

            for item in hid.enumerate(GAMEPAD_VID, GAMEPAD_PID):
                manufacturer = str(item.get("manufacturer_string") or "")
                prod = str(item.get("product_string") or "")
                if not product and prod:
                    product = prod
                if "2.4G" in manufacturer or "2.4G" in prod:
                    receiver = True
                    break
        except Exception:
            pass
        result = {"receiver": receiver, "product": product}
        with self.lock:
            self._link_ts = now
            self._link_cache = result
        return result

    def state(self) -> dict[str, Any]:
        lib = _load_xinput()
        base: dict[str, Any] = {
            "connected": False,
            "available": lib is not None,
            "model": "BIGBIG WON Rainbow 2 SE",
            "xinput": True,
            "slot": None,
            "packet": None,
            "link": "未连接",
            "wireless": None,
            "receiver": False,
            "battery": None,
            "battery_type": None,
            "battery_level": None,
            "battery_type_label": None,
            "battery_level_label": None,
            "battery_label": None,
            "battery_note": None,
            "charging": None,
            "buttons": {name: False for name in BUTTON_FLAGS},
            "buttons_down": [],
            "triggers": {"left": 0, "right": 0},
            "sticks": {
                "left": {"x": 0, "y": 0},
                "right": {"x": 0, "y": 0},
            },
        }
        if lib is None:
            base["error"] = "当前系统没有可用的 XInput 接口"
            return base

        slot, raw = self._find_slot(lib)
        if slot is None:
            return base

        pad = raw.Gamepad
        buttons = {name: bool(pad.wButtons & flag) for name, flag in BUTTON_FLAGS.items()}
        link_info = self._link_info()
        receiver = bool(link_info.get("receiver"))
        battery_info = self._read_battery(lib, slot)

        link = "2.4G 接收器" if receiver else "有线 (XInput)"
        wireless = bool(receiver)
        battery = None
        battery_type = None
        battery_level = None
        battery_type_label = None
        battery_level_label = None
        battery_label = None
        battery_note = "XInput 未提供电量信息"
        charging = None

        if battery_info is not None:
            battery_type, battery_level = battery_info
            battery_type_label = BATTERY_TYPE_LABEL.get(battery_type, "未知")
            battery_level_label = BATTERY_LEVEL_LABEL.get(battery_level)
            if battery_type == BATTERY_TYPE_WIRED:
                link = "2.4G 接收器" if receiver else "USB 有线"
                wireless = bool(receiver)
                charging = True
                battery_label = "接收器供电" if receiver else "USB 供电"
                battery_note = (
                    "2.4G 接收器由 USB 供电，XInput 不提供手柄电量百分比"
                    if receiver
                    else "通过数据线供电，XInput 不提供电池百分比"
                )
            elif battery_type in (BATTERY_TYPE_ALKALINE, BATTERY_TYPE_NIMH, BATTERY_TYPE_LITHIUM):
                link = "无线"
                wireless = True
                battery = BATTERY_PERCENT.get(battery_level)
                battery_label = battery_level_label
                battery_note = "XInput 电量等级换算，仅供参考"
            else:
                link = "XInput"
                wireless = None
                battery_label = battery_type_label
        else:
            # Battery information is missing on some third-party receivers.
            link = "2.4G 接收器" if receiver else "XInput"
            wireless = bool(receiver)
            battery_label = "接收器供电" if receiver else None
            battery_note = "XInput 未提供电量信息"

        active = [name for name, pressed in buttons.items() if pressed]
        return {
            **base,
            "connected": True,
            "slot": slot,
            "packet": int(raw.dwPacketNumber),
            "link": link,
            "wireless": wireless,
            "receiver": receiver,
            "battery": battery,
            "battery_type": battery_type,
            "battery_level": battery_level,
            "battery_type_label": battery_type_label,
            "battery_level_label": battery_level_label,
            "battery_label": battery_label,
            "battery_note": battery_note,
            "charging": charging,
            "buttons": buttons,
            "buttons_down": active,
            "triggers": {"left": int(pad.bLeftTrigger), "right": int(pad.bRightTrigger)},
            "sticks": {
                "left": {"x": int(pad.sThumbLX), "y": int(pad.sThumbLY)},
                "right": {"x": int(pad.sThumbRX), "y": int(pad.sThumbRY)},
            },
            "product": link_info.get("product"),
        }

    # ------------------------------------------------------------------
    # Rumble
    # ------------------------------------------------------------------

    @staticmethod
    def _clamp(value: Any, low: int = 0, high: int = 100) -> int:
        try:
            number = int(round(float(value)))
        except (TypeError, ValueError) as exc:
            raise GamepadError("震动强度必须是数字") from exc
        return max(low, min(high, number))

    def vibrate(self, left: Any = 60, right: Any = 60, duration_ms: Any = 450) -> dict[str, Any]:
        lib = _load_xinput()
        if lib is None:
            raise GamepadError("当前系统没有可用的 XInput 接口")
        slot, _ = self._find_slot(lib)
        if slot is None:
            raise GamepadError("手柄未连接")
        left_value = self._clamp(left)
        right_value = self._clamp(right)
        try:
            duration = max(0, min(5000, int(duration_ms)))
        except (TypeError, ValueError) as exc:
            raise GamepadError("震动时长必须是数字") from exc
        if duration == 0:
            self._cancel_stop()
            lib.XInputSetState(slot, ctypes.byref(_XINPUT_VIBRATION(0, 0)))
            return {"slot": slot, "left": 0, "right": 0, "duration_ms": 0}
        vibration = _XINPUT_VIBRATION(
            int(left_value * 65535 / 100),
            int(right_value * 65535 / 100),
        )
        if lib.XInputSetState(slot, ctypes.byref(vibration)) != 0:
            raise GamepadError("手柄拒绝了震动指令")
        self._arm_stop(slot, duration)
        return {"slot": slot, "left": left_value, "right": right_value, "duration_ms": duration}

    def stop(self) -> dict[str, Any]:
        lib = _load_xinput()
        if lib is None:
            raise GamepadError("当前系统没有可用的 XInput 接口")
        slot, _ = self._find_slot(lib)
        if slot is None:
            raise GamepadError("手柄未连接")
        self._cancel_stop()
        vibration = _XINPUT_VIBRATION(0, 0)
        lib.XInputSetState(slot, ctypes.byref(vibration))
        return {"slot": slot, "left": 0, "right": 0, "duration_ms": 0}

    def _cancel_stop(self) -> None:
        with self.lock:
            if self._stop_timer is not None:
                self._stop_timer.cancel()
                self._stop_timer = None

    def _arm_stop(self, slot: int, duration_ms: int) -> None:
        self._cancel_stop()
        if duration_ms <= 0:
            return

        def finish() -> None:
            lib = _load_xinput()
            if lib is None:
                return
            try:
                lib.XInputSetState(slot, ctypes.byref(_XINPUT_VIBRATION(0, 0)))
            except Exception:
                pass

        timer = threading.Timer(duration_ms / 1000.0, finish)
        timer.daemon = True
        with self.lock:
            self._stop_timer = timer
        timer.start()
