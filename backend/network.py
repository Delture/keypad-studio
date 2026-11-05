"""Tailscale + Clash Party network profile switching."""
from __future__ import annotations

import ctypes
import json
import os
import re
import shutil
import subprocess
import time
import winreg
from pathlib import Path
from typing import Callable, Tuple

import psutil

from . import winutil

CLASH_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "mihomo-party"
CLASH_CONFIG = CLASH_DIR / "config.yaml"
MIHOMO_CONFIG = CLASH_DIR / "mihomo.yaml"
PROXY_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
CREATE_NO_WINDOW = 0x08000000
POWERSHELL = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _tailscale_exe() -> str | None:
    candidates = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tailscale" / "tailscale.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Tailscale" / "tailscale.exe",
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return shutil.which("tailscale")


def _run(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=CREATE_NO_WINDOW,
    )


def tailscale_state() -> str:
    exe = _tailscale_exe()
    if not exe:
        return "NotFound"
    try:
        result = _run([exe, "status", "--json"], timeout=8)
        if result.returncode != 0:
            return "Error"
        data = json.loads(result.stdout or "{}")
        return str(data.get("BackendState", "Unknown"))
    except Exception:
        return "Error"


def tailscale_connected() -> bool:
    return tailscale_state() == "Running"


def set_tailscale(connected: bool, wait_seconds: float = 25.0) -> Tuple[bool, str]:
    exe = _tailscale_exe()
    if not exe:
        return False, "未找到 Tailscale"
    target = "Running" if connected else "Stopped"
    if tailscale_state() == target:
        return True, ""
    try:
        result = _run([exe, "up" if connected else "down"], timeout=35 if connected else 15)
    except subprocess.TimeoutExpired:
        return False, "Tailscale 命令超时"
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if tailscale_state() == target:
            return True, ""
        time.sleep(0.4)
    detail = (result.stderr or result.stdout or "").strip()
    return False, f"Tailscale 状态未切换{f'：{detail}' if detail else ''}"


def system_proxy_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, PROXY_REG_PATH) as key:
            value, _ = winreg.QueryValueEx(key, "ProxyEnable")
            return int(value) == 1
    except Exception:
        return False


def _read_shortcut(key: str) -> str:
    try:
        text = CLASH_CONFIG.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    match = re.search(rf"(?m)^\s*{re.escape(key)}\s*:\s*(.*?)\s*$", text)
    if not match:
        return ""
    return match.group(1).strip().strip('"').strip("'")


def clash_shortcuts() -> dict[str, str]:
    return {
        "tun": _read_shortcut("triggerTunShortcut"),
        "proxy": _read_shortcut("triggerSysProxyShortcut"),
    }


def _accelerator_to_keys(accelerator: str) -> list[str]:
    tokens = [part.strip() for part in (accelerator or "").split("+") if part.strip()]
    if not tokens:
        return []
    keys: list[str] = []
    special = {
        "space": "Space", "tab": "Tab", "enter": "Enter", "return": "Enter",
        "escape": "Esc", "esc": "Esc", "backspace": "Backspace", "delete": "Delete",
        "insert": "Insert", "home": "Home", "end": "End", "pageup": "PageUp",
        "pagedown": "PageDown", "up": "Up", "down": "Down", "left": "Left",
        "right": "Right", "printscreen": "PrintScreen", "capslock": "CapsLock",
        "numlock": "NumLock", "scrolllock": "ScrollLock", "plus": "Equals",
        "numadd": "NumpadAdd", "numsub": "NumpadSubtract",
        "nummult": "NumpadMultiply", "numdiv": "NumpadDivide", "numdec": "NumpadDecimal",
    }
    for token in tokens:
        low = token.lower()
        if low in {"ctrl", "control", "commandorcontrol", "cmdorctrl"}:
            keys.append("Ctrl")
        elif low == "shift":
            keys.append("Shift")
        elif low in {"alt", "option"}:
            keys.append("Alt")
        elif low in {"super", "meta", "command", "cmd"}:
            keys.append("Win")
        else:
            if low in special:
                keys.append(special[low])
            else:
                try:
                    keys.append(winutil.normalize_key(token))
                except ValueError:
                    return []
    if not any(key not in {"Ctrl", "Shift", "Alt", "Win"} for key in keys):
        return []
    return keys


def _send_shortcut(accelerator: str) -> Tuple[bool, str]:
    keys = _accelerator_to_keys(accelerator)
    if not keys:
        return False, "快捷键格式无法识别"
    try:
        winutil.send_combo(keys)
        return True, ""
    except Exception as exc:
        return False, f"发送快捷键失败：{exc}"


def _tun_adapter_up() -> bool:
    if not POWERSHELL.exists():
        ps = "powershell.exe"
    else:
        ps = str(POWERSHELL)
    script = (
        "$n = Get-NetAdapter -IncludeHidden | Where-Object { $_.Name -eq 'Mihomo' -or "
        "$_.InterfaceDescription -match 'Mihomo' }; "
        "if ($n -and ($n.Status -eq 'Up')) { 'UP' } else { 'DOWN' }"
    )
    try:
        result = _run([ps, "-NoProfile", "-NonInteractive", "-Command", script], timeout=10)
        return "UP" in (result.stdout or "")
    except Exception:
        return False


def _wait_for(predicate: Callable[[], bool], timeout: float, interval: float = 0.4) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if predicate():
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


def _clash_running() -> bool:
    try:
        for proc in psutil.process_iter(["name"]):
            if (proc.info.get("name") or "").lower() == "clash party.exe":
                return True
    except Exception:
        pass
    return False


def network_status() -> dict:
    ts = tailscale_state()
    proxy = system_proxy_enabled()
    tun = _tun_adapter_up()
    return {
        "tailscale": ts,
        "tailscaleConnected": ts == "Running",
        "systemProxy": proxy,
        "tun": tun,
        "isStateA": ts == "Running" and proxy and not tun,
        "admin": is_admin(),
        "clashRunning": _clash_running(),
        "shortcuts": clash_shortcuts(),
    }


def toggle_network_profile() -> Tuple[bool, str]:
    if not _clash_running():
        return False, "Clash Party 未运行"
    shortcuts = clash_shortcuts()
    if not shortcuts["tun"] or not shortcuts["proxy"]:
        return False, "Clash Party 未配置 TUN/系统代理快捷键，请重启 Clash Party 让快捷键生效"

    status = network_status()
    state_a = bool(status["isStateA"])

    def apply_tun(target: bool) -> Tuple[bool, str]:
        if _tun_adapter_up() == target:
            return True, ""
        ok, message = _send_shortcut(shortcuts["tun"])
        if not ok:
            return False, message
        if not _wait_for(lambda: _tun_adapter_up() == target, 12):
            return False, "TUN 模式切换超时，请检查 Clash Party 快捷键与管理员权限"
        return True, ""

    def apply_proxy(target: bool) -> Tuple[bool, str]:
        if system_proxy_enabled() == target:
            return True, ""
        ok, message = _send_shortcut(shortcuts["proxy"])
        if not ok:
            return False, message
        if not _wait_for(lambda: system_proxy_enabled() == target, 6):
            return False, "系统代理切换超时，请检查 Clash Party 快捷键"
        return True, ""

    if state_a:
        ok, message = apply_tun(True)
        if not ok:
            return False, message
        ok, message = apply_proxy(False)
        if not ok:
            return False, message
        ok, message = set_tailscale(False)
        if not ok:
            return False, message
        return True, "已切换：Tailscale 已断开 + Clash Party TUN 模式"

    ok, message = set_tailscale(True)
    if not ok:
        return False, message
    ok, message = apply_proxy(True)
    if not ok:
        return False, message
    ok, message = apply_tun(False)
    if not ok:
        return False, message
    return True, "已恢复：Tailscale 已连接 + Clash Party 普通代理"
