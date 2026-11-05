"""Peripheral hub: battery for the M75 keyboard, battery / polling rate / DPI
and sensor settings for the G04 Ultra mouse, and XInput state for the
Rainbow 2 SE gamepad.

Protocols were reverse engineered from the vendors' own drivers:

* Xinmeng M75 (2.4G receiver 0C45:FEFE, interface MI_03, usage page 0xFF60):
  33-byte output report (report id 0 + 32 bytes). data[0] = command,
  data[31] = sum(data[0..30]) & 0xFF. Command 0x20 arg 1 answers with a
  32-byte report whose byte 3 is the battery percentage.

* AUSDOM G04 Ultra (receiver 363C:FF9D, usage page 0xFFA0):
  output report id 0x0B, 63-byte payload; responses carry report id 0x0A.
  0x13 = device info, 0x17 = performance config, 0x19 = DPI stages,
  0x18 = write performance config, 0x1A = write DPI stages,
  0x22 = select active DPI stage.

* Rainbow 2 SE gamepad: XInput (xinput1_4.dll / 1_3 / 9_1_0) for live input,
  rumble and coarse battery.  The vendor's private protocol is not used here,
  so remapping, gyro, macros and firmware stay outside this module.
"""
from __future__ import annotations

import threading
import time
from typing import Any

import hid

from .gamepad import GamepadManager

KEYBOARD_VID = 0x0C45
KEYBOARD_PID = 0xFEFE
KEYBOARD_USAGE_PAGE = 0xFF60
KEYBOARD_INTERFACE = 3

MOUSE_VID = 0x363C
MOUSE_PID = 0xFF9D
MOUSE_USAGE_PAGE = 0xFFA0
MOUSE_REPORT_ID = 0x0B
MOUSE_RESPONSE_ID = 0x0A
MOUSE_CONFIG_MODE = 0x1F  # G04 Ultra dongle: lcd=false, ble250=true

MOUSE_DPI_STEP = 50
MOUSE_DPI_MIN = 50
MOUSE_DPI_MAX = 42000
MOUSE_STAGES_MAX = 8

MOUSE_LOD_OPTIONS = [
    {"value": 0, "label": "0.7 / 1 mm（玻璃）"},
    {"value": 1, "label": "1 mm"},
    {"value": 2, "label": "2 mm"},
]
MOUSE_SLEEP_OPTIONS = [
    {"value": 1, "label": "10 秒"},
    {"value": 3, "label": "30 秒"},
    {"value": 6, "label": "1 分钟"},
    {"value": 12, "label": "2 分钟"},
    {"value": 18, "label": "3 分钟"},
    {"value": 30, "label": "5 分钟"},
    {"value": 60, "label": "10 分钟"},
    {"value": 90, "label": "15 分钟"},
]
MOUSE_RIPPLE_OPTIONS = [
    {"value": 0, "label": "自动（默认）"},
    {"value": 1, "label": "开启"},
    {"value": 2, "label": "关闭"},
]
MOUSE_DEBOUNCE_MAX = 15

WIRELESS_RATES = [
    {"label": "8000", "code": 64},
    {"label": "4000", "code": 32},
    {"label": "2000", "code": 16},
    {"label": "1000", "code": 1},
    {"label": "500", "code": 2},
    {"label": "250", "code": 4},
]
WIRED_RATES = WIRELESS_RATES + [{"label": "125", "code": 8}]


class PeripheralError(RuntimeError):
    pass


def _open(path: bytes) -> hid.device:
    dev = hid.device()
    dev.open_path(path)
    return dev


class PeripheralHub:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.gamepad = GamepadManager()

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    @staticmethod
    def keyboard_path() -> bytes | None:
        for item in hid.enumerate(KEYBOARD_VID, KEYBOARD_PID):
            if (
                item.get("usage_page") == KEYBOARD_USAGE_PAGE
                and item.get("interface_number") == KEYBOARD_INTERFACE
            ):
                return item["path"]
        return None

    @staticmethod
    def mouse_path() -> bytes | None:
        for item in hid.enumerate(MOUSE_VID, MOUSE_PID):
            if item.get("usage_page") == MOUSE_USAGE_PAGE:
                return item["path"]
        return None

    # ------------------------------------------------------------------
    # Keyboard
    # ------------------------------------------------------------------

    @staticmethod
    def _keyboard_frame(cmd: int, arg: int = 0) -> bytes:
        data = bytearray(32)
        data[0] = cmd
        data[1] = arg
        data[31] = sum(data[:31]) & 0xFF
        return b"\x00" + bytes(data)

    def keyboard_state(self) -> dict[str, Any]:
        path = self.keyboard_path()
        if not path:
            return {"connected": False, "model": "新盟 M75", "link": "2.4G"}
        dev = _open(path)
        battery = None
        try:
            for _ in range(2):
                dev.write(self._keyboard_frame(0x20, 1))
                deadline = time.time() + 0.9
                while time.time() < deadline:
                    report = dev.read(256, int(max(1, (deadline - time.time()) * 1000)))
                    if not report:
                        continue
                    report = bytes(report)
                    if len(report) >= 33 and report[0] == 0x00:
                        report = report[1:]
                    if len(report) >= 4 and report[0] == 0x20 and report[1] == 0x01:
                        battery = report[3]
                        break
                if battery is not None:
                    break
                time.sleep(0.2)
        finally:
            dev.close()
        if battery is None:
            raise PeripheralError("暂时读不到键盘电量，请先按一下键盘任意键唤醒，再点「重新扫描」")
        return {
            "connected": True,
            "model": "新盟 M75",
            "link": "2.4G",
            "battery": int(battery),
            "charging": None,
        }

    # ------------------------------------------------------------------
    # Mouse helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _mouse_write(dev: hid.device, payload: list[int] | bytes) -> None:
        data = bytes(payload).ljust(63, b"\x00")[:63]
        dev.write(bytes([MOUSE_REPORT_ID]) + data)

    def _mouse_read(self, dev: hid.device, cmd: int, wait: float = 0.7) -> bytes | None:
        """Send a bare read command and return the first matching response payload."""
        self._mouse_write(dev, [cmd, 0, 0])
        deadline = time.time() + wait
        while time.time() < deadline:
            report = dev.read(256, int(max(1, (deadline - time.time()) * 1000)))
            if not report:
                continue
            report = bytes(report)
            payload = report[1:] if report and report[0] == MOUSE_RESPONSE_ID else report
            if payload and payload[0] == cmd:
                return payload
        return None

    @staticmethod
    def _mouse_config(report: bytes) -> list[int]:
        return list(report[3:63])

    @staticmethod
    def _mouse_options() -> dict[str, Any]:
        return {
            "lod": MOUSE_LOD_OPTIONS,
            "sleep": MOUSE_SLEEP_OPTIONS,
            "ripple": MOUSE_RIPPLE_OPTIONS,
            "debounce_max": MOUSE_DEBOUNCE_MAX,
        }

    @classmethod
    def _mouse_config_state(cls, config: list[int]) -> dict[str, Any]:
        return {
            "silent_height": int(config[6]),
            "key_debounce_time": int(config[7]),
            "motion_sync_enable": config[8] == 1,
            "linear_correction_enable": config[10] == 1,
            "ripple_control_option": int(config[11]),
            "sensor_power_saving_enable": config[15] == 0,
            "sleep_time": int(config[25]),
        }

    @staticmethod
    def _decode_stage(config: list[int], index: int) -> dict[str, Any]:
        base = index * 6
        lo_x, lo_y, flags = config[base], config[base + 1], config[base + 2]
        hi_x = (flags >> 6) & 0x03
        hi_y = (flags >> 2) & 0x03
        value = (((hi_x << 8) | lo_x) + 1) * MOUSE_DPI_STEP
        return {
            "index": index,
            "dpi": value,
            "color": f"#{config[base + 3]:02x}{config[base + 4]:02x}{config[base + 5]:02x}",
        }

    @staticmethod
    def _encode_stage(dpi: int) -> tuple[int, int, int]:
        steps = max(1, int(round(dpi / MOUSE_DPI_STEP))) - 1
        low = steps & 0xFF
        high = (steps >> 8) & 0x0F
        flags = (high << 6) | (high << 2)
        return low, low, flags

    def mouse_state(self) -> dict[str, Any]:
        path = self.mouse_path()
        if not path:
            return {
                "connected": False,
                "model": "AUSDOM G04 Ultra",
                "link": "2.4G",
                "rates": WIRELESS_RATES,
                "options": self._mouse_options(),
            }
        dev = _open(path)
        try:
            info = self._mouse_read(dev, 0x13)
            if not info or len(info) < 20:
                raise PeripheralError("鼠标没有返回设备信息")
            perf = self._mouse_read(dev, 0x17)
            if not perf or len(perf) < 34:
                raise PeripheralError("鼠标没有返回性能配置")
            dpi_raw = self._mouse_read(dev, 0x19)
            if not dpi_raw or len(dpi_raw) < 51:
                raise PeripheralError("鼠标没有返回 DPI 配置")
        finally:
            dev.close()

        config = self._mouse_config(perf)
        dpi_config = self._mouse_config(dpi_raw)
        wireless = info[19] == 1
        battery = int(info[17])
        charging = (not wireless) and battery < 100 and info[16] == 1
        stages_total = int(config[2])
        current_stage = int(config[3])
        stages = [self._decode_stage(dpi_config, i) for i in range(min(stages_total, MOUSE_STAGES_MAX))]
        return {
            "connected": True,
            "model": "AUSDOM G04 Ultra",
            "link": "2.4G" if wireless else "有线",
            "wireless": wireless,
            "battery": battery,
            "charging": charging,
            "report_rate_code": int(config[0] if wireless else config[1]),
            "usb_report_rate_code": int(config[1]),
            "rates": WIRELESS_RATES if wireless else WIRED_RATES,
            "stages": stages,
            "current_stage": current_stage,
            "max_stage": stages_total,
            "dpi_min": MOUSE_DPI_MIN,
            "dpi_max": MOUSE_DPI_MAX,
            "dpi_step": MOUSE_DPI_STEP,
            "config": self._mouse_config_state(config),
            "options": self._mouse_options(),
        }

    # ------------------------------------------------------------------
    # Mouse setters
    # ------------------------------------------------------------------

    def set_report_rate(self, code: int) -> None:
        valid = {item["code"] for item in WIRELESS_RATES + WIRED_RATES}
        if code not in valid:
            raise PeripheralError("不支持的回报率")
        path = self.mouse_path()
        if not path:
            raise PeripheralError("未找到鼠标接收器")
        dev = _open(path)
        try:
            perf = self._mouse_read(dev, 0x17)
            if not perf:
                raise PeripheralError("读取鼠标配置失败")
            info = self._mouse_read(dev, 0x13)
            if not info:
                raise PeripheralError("读取鼠标状态失败")
            wireless = info[19] == 1
            config = self._mouse_config(perf)
            config[0 if wireless else 1] = code
            self._mouse_write(dev, [0x18, MOUSE_CONFIG_MODE] + config)
            time.sleep(0.15)
            check = self._mouse_read(dev, 0x17)
        finally:
            dev.close()
        if not check:
            raise PeripheralError("写入回报率后没有收到确认")
        now = self._mouse_config(check)[0 if wireless else 1]
        if now != code:
            raise PeripheralError("回报率写入失败")

    def set_dpi(self, stage: int, dpi: int) -> None:
        if not (0 <= stage < MOUSE_STAGES_MAX):
            raise PeripheralError("DPI 档位超出范围")
        if not (MOUSE_DPI_MIN <= dpi <= MOUSE_DPI_MAX):
            raise PeripheralError(f"DPI 需要在 {MOUSE_DPI_MIN} - {MOUSE_DPI_MAX} 之间")
        dpi = int(round(dpi / MOUSE_DPI_STEP)) * MOUSE_DPI_STEP
        path = self.mouse_path()
        if not path:
            raise PeripheralError("未找到鼠标接收器")
        dev = _open(path)
        try:
            raw = self._mouse_read(dev, 0x19)
            if not raw:
                raise PeripheralError("读取 DPI 配置失败")
            config = self._mouse_config(raw)
            low, low_y, flags = self._encode_stage(dpi)
            base = stage * 6
            config[base] = low
            config[base + 1] = low_y
            config[base + 2] = flags
            self._mouse_write(dev, [0x1A, 48] + config)
            time.sleep(0.15)
            check = self._mouse_read(dev, 0x19)
        finally:
            dev.close()
        if not check:
            raise PeripheralError("写入 DPI 后没有收到确认")
        now = self._decode_stage(self._mouse_config(check), stage)["dpi"]
        if now != dpi:
            raise PeripheralError("DPI 写入失败")

    def set_active_stage(self, stage: int) -> None:
        path = self.mouse_path()
        if not path:
            raise PeripheralError("未找到鼠标接收器")
        dev = _open(path)
        try:
            perf = self._mouse_read(dev, 0x17)
            if not perf:
                raise PeripheralError("读取鼠标配置失败")
            config = self._mouse_config(perf)
            total = int(config[2])
            if not (0 <= stage < total):
                raise PeripheralError("档位不存在")
            self._mouse_write(dev, [0x22, 2, stage, total])
            time.sleep(0.12)
            check = self._mouse_read(dev, 0x17)
        finally:
            dev.close()
        if not check:
            raise PeripheralError("切换档位后没有收到确认")
        now = int(self._mouse_config(check)[3])
        if now != stage:
            raise PeripheralError("切换档位失败")

    @staticmethod
    def _mouse_setting_patch(name: str, value: Any) -> tuple[int, int]:
        """Map one UI setting to (config index, byte value), matching the
        vendor driver's own write layout."""
        if name == "silent_height":
            number = int(value)
            if number not in (0, 1, 2):
                raise PeripheralError("静默高度取值无效")
            return 6, number
        if name == "key_debounce_time":
            number = int(value)
            if not (0 <= number <= MOUSE_DEBOUNCE_MAX):
                raise PeripheralError(f"按键去抖需要在 0 - {MOUSE_DEBOUNCE_MAX} ms 之间")
            return 7, number
        if name == "motion_sync_enable":
            return 8, 1 if value else 0
        if name == "linear_correction_enable":
            return 10, 1 if value else 0
        if name == "ripple_control_option":
            number = int(value)
            if number not in (0, 1, 2):
                raise PeripheralError("波纹控制取值无效")
            return 11, number
        if name == "sensor_power_saving_enable":
            # The vendor driver stores the inverse: 0 means power saving on.
            return 15, 0 if value else 1
        if name == "sleep_time":
            number = int(value)
            if number not in {item["value"] for item in MOUSE_SLEEP_OPTIONS}:
                raise PeripheralError("休眠时间取值无效")
            return 25, number
        raise PeripheralError(f"未知鼠标设置：{name}")

    def set_mouse_setting(self, name: str, value: Any) -> None:
        path = self.mouse_path()
        if not path:
            raise PeripheralError("未找到鼠标接收器")
        dev = _open(path)
        try:
            perf = self._mouse_read(dev, 0x17)
            if not perf or len(perf) < 34:
                raise PeripheralError("读取鼠标配置失败")
            config = self._mouse_config(perf)
            index, byte = self._mouse_setting_patch(name, value)
            config[index] = byte
            self._mouse_write(dev, [0x18, MOUSE_CONFIG_MODE] + config)
            time.sleep(0.15)
            check = self._mouse_read(dev, 0x17)
        finally:
            dev.close()
        if not check or len(check) < 34:
            raise PeripheralError("写入鼠标设置后没有收到确认")
        if self._mouse_config(check)[index] != byte:
            raise PeripheralError("鼠标设置写入失败")

    # ------------------------------------------------------------------
    # Gamepad
    # ------------------------------------------------------------------

    def gamepad_state(self) -> dict[str, Any]:
        with self.lock:
            return self.gamepad.state()

    def gamepad_action(self, action: str, payload: dict[str, Any] | None = None) -> None:
        payload = payload or {}
        if action == "vibrate":
            self.gamepad.vibrate(
                payload.get("left", 60),
                payload.get("right", 60),
                payload.get("duration_ms", 450),
            )
        elif action == "stop":
            self.gamepad.stop()
        else:
            raise PeripheralError(f"未知手柄操作：{action}")

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            result: dict[str, Any] = {}
            readers = (
                ("keyboard", self.keyboard_state, self.keyboard_path),
                ("mouse", self.mouse_state, self.mouse_path),
            )
            for key, reader, finder in readers:
                try:
                    result[key] = reader()
                except Exception as exc:  # keep the other device usable
                    try:
                        present = bool(finder())
                    except Exception:
                        present = False
                    result[key] = {"connected": present, "error": str(exc)}
            try:
                result["gamepad"] = self.gamepad.state()
            except Exception as exc:
                result["gamepad"] = {"connected": False, "error": str(exc)}
            return result
