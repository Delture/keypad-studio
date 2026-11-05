"""HID device manager for the 6-key MyKey / ByAmos keypad."""
from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Callable

import hid

from .constants import DEFAULT_TRIGGER_MAP, KEY_COUNT, MODEL_NAMES, PRODUCT_ID, VENDOR_ID

PACKET_SIZE = 64
REPORT_SIZE = 65


class DeviceManager:
    def __init__(
        self,
        on_trigger: Callable[[int], None] | None = None,
        on_status: Callable[[dict], None] | None = None,
    ) -> None:
        self.on_trigger = on_trigger or (lambda trigger_id: None)
        self.on_status = on_status or (lambda status: None)
        self.dev: hid.device | None = None
        self.path: bytes | None = None
        self.connected = False
        self.model_code = 0
        self.model = ""
        self.firmware = ""
        self.last_error = ""
        self.initialized = False
        self.trigger_map = dict(DEFAULT_TRIGGER_MAP)
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="KeypadHID", daemon=True)
        self._raw_log: list[dict] = []
        self._log_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        if not self._thread.is_alive():
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            self._close_locked()

    def _close_locked(self) -> None:
        if self.dev is not None:
            try:
                self.dev.close()
            except Exception:
                pass
        self.dev = None
        self.connected = False
        self.path = None

    def status(self) -> dict:
        return {
            "connected": self.connected,
            "model": self.model,
            "modelCode": self.model_code,
            "firmware": self.firmware,
            "path": (self.path.decode("utf-8", "replace") if isinstance(self.path, bytes) else self.path) or "",
            "initialized": self.initialized,
            "error": self.last_error,
        }

    def _emit_status(self) -> None:
        try:
            self.on_status(self.status())
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _find_path(self) -> bytes | None:
        try:
            devices = hid.enumerate(VENDOR_ID, PRODUCT_ID)
        except Exception as exc:
            self.last_error = str(exc)
            return None
        for entry in devices:
            path = entry.get("path")
            if path and b"MI_00" in path:
                return path
        return None

    def _connect(self) -> bool:
        path = self._find_path()
        if not path:
            self.last_error = "未找到设备"
            return False
        dev = hid.device()
        try:
            dev.open_path(path)
        except Exception as exc:
            self.last_error = f"打开设备失败：{exc}"
            try:
                dev.close()
            except Exception:
                pass
            return False
        with self._lock:
            self.dev = dev
            self.path = path
            self.connected = True
            self.last_error = ""
        try:
            self._read_device_info()
        except Exception as exc:
            self.last_error = f"读取设备信息失败：{exc}"
            with self._lock:
                self._close_locked()
            return False
        self._emit_status()
        return True

    def _read_device_info(self) -> None:
        payload = b"GetDeviceInfo" + b"\x00" * (PACKET_SIZE - len("GetDeviceInfo"))
        response = self._transact(payload, timeout_ms=800, expect_prefix=None)
        if not response:
            raise RuntimeError("设备没有回应")
        code = response[0]
        self.model_code = code
        self.model = MODEL_NAMES.get(code, f"未知型号 (0x{code:02X})")
        if len(response) >= 3:
            self.firmware = f"{response[2]}.{response[1]:03d}"
        self._log("IN", response)

    # ------------------------------------------------------------------
    # Low level I/O
    # ------------------------------------------------------------------

    def _log(self, direction: str, data: bytes | list[int]) -> None:
        raw = bytes(data)
        entry = {
            "ts": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "dir": direction,
            "hex": raw.hex(" ").upper(),
        }
        with self._log_lock:
            self._raw_log.append(entry)
            if len(self._raw_log) > 400:
                del self._raw_log[: len(self._raw_log) - 400]

    def raw_log(self) -> list[dict]:
        with self._log_lock:
            return list(self._raw_log)

    def _write_locked(self, payload: bytes) -> None:
        if not self.dev:
            raise RuntimeError("设备未连接")
        payload = bytes(payload)[:PACKET_SIZE]
        payload = payload + b"\x00" * (PACKET_SIZE - len(payload))
        report = b"\x00" + payload
        written = self.dev.write(report)
        self._log("OUT", report)
        if written is not None and int(written) < 0:
            raise OSError("HID 写入失败")

    def _read_locked(self, timeout_ms: int = 200) -> bytes | None:
        if not self.dev:
            raise RuntimeError("设备未连接")
        data = self.dev.read(PACKET_SIZE, timeout_ms)
        if data:
            raw = bytes(data)
            self._log("IN", raw)
            return raw
        return None

    def _transact(self, payload: bytes, timeout_ms: int = 500, expect_prefix: bytes | None = None):
        """Write a report and wait for the device's echo / response.

        The device echoes configuration packets, so an echo is used as the ACK.
        Any trigger packets received while waiting are dispatched normally.
        """
        with self._lock:
            self._write_locked(payload)
            deadline = time.monotonic() + timeout_ms / 1000
            while time.monotonic() < deadline:
                data = self._read_locked(max(40, int((deadline - time.monotonic()) * 1000) or 40))
                if not data:
                    continue
                if expect_prefix is not None:
                    if data.startswith(expect_prefix):
                        return data
                    continue
                return data
        return None

    # ------------------------------------------------------------------
    # Public operations
    # ------------------------------------------------------------------

    def reconnect(self) -> bool:
        with self._lock:
            self._close_locked()
        self._emit_status()
        ok = self._connect()
        if ok:
            self.initialized = False
        self._emit_status()
        return ok

    def initialize_keys(self, sync: bool = True) -> bool:
        """Bind all six firmware keys to software triggers.

        The firmware key id is kept as the trigger id; the physical order is
        handled by trigger_map.
        """
        if not self.connected:
            if not self._connect():
                return False
        try:
            for key_id in range(1, KEY_COUNT + 1):
                self.write_key_binding(key_id, 3, key_id, wait_ack=True)
            self.initialized = True
            self._emit_status()
            return True
        except Exception as exc:
            self.last_error = f"初始化按键失败：{exc}"
            self._emit_status()
            return False

    def write_key_binding(
        self,
        firmware_key: int,
        action_type: int,
        action_id: int,
        value: bytes | list[int] | None = None,
        wait_ack: bool = True,
    ) -> bool:
        sw = [firmware_key & 0xFF, action_type & 0xFF, action_id & 0xFF] + list(value or [])
        info = [1, len(sw) % 256, len(sw) // 256, 0, 0] + [0] * 22 + sw
        data = bytes(info)
        chunks = [data[i * 62 : (i + 1) * 62] for i in range((len(data) + 61) // 62)]
        for index, chunk in enumerate(chunks):
            prefix = b"\x0b\x01" if index == len(chunks) - 1 else b"\x0b\x00"
            packet = prefix + chunk
            if wait_ack:
                with self._lock:
                    self._write_locked(packet)
                    deadline = time.monotonic() + 1.0
                    while time.monotonic() < deadline:
                        response = self._read_locked(120)
                        if not response:
                            continue
                        # trigger packets may arrive while writing
                        self._handle_packet(response, raw_only=False)
                        if response.startswith(b"\x0b\x01" + chunk[:3]):
                            break
            else:
                with self._lock:
                    self._write_locked(packet)
                time.sleep(0.05)
        return True

    def send_raw(self, payload: bytes) -> bool:
        try:
            with self._lock:
                self._write_locked(payload)
            return True
        except Exception as exc:
            self.last_error = str(exc)
            return False

    def read_test(self, timeout_ms: int = 500) -> bytes | None:
        try:
            with self._lock:
                return self._read_locked(timeout_ms)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Read loop
    # ------------------------------------------------------------------

    def _handle_packet(self, data: bytes, raw_only: bool = False) -> None:
        if len(data) >= 5 and data[0:3] == b"\x0b\x01\x03":
            # software key event: 0B 01 03 <type> <id>
            action_type = data[3]
            trigger_id = data[4]
            if action_type in (3, 4):
                try:
                    self.on_trigger(trigger_id)
                except Exception:
                    pass

    def _run(self) -> None:
        while not self._stop.is_set():
            if not self.connected:
                self.last_error = ""
                if not self._connect():
                    self._emit_status()
                    time.sleep(1.2)
                    continue
            try:
                with self._lock:
                    data = self._read_locked(200)
                if data:
                    self._handle_packet(data)
            except Exception as exc:
                self.last_error = f"设备断开：{exc}"
                with self._lock:
                    self._close_locked()
                self._emit_status()
                time.sleep(0.8)
