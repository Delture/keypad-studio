"""Windows integration helpers: SendInput, clipboard, windows, power, autostart."""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time
import winreg
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .constants import KEY_ALIASES, KEYS, MODIFIER_KEYS, KEY_DISPLAY

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
powrprof = ctypes.WinDLL("powrprof", use_last_error=True)
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

# ---------------------------------------------------------------------------
# SendInput
# ---------------------------------------------------------------------------

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000

ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT

# 64-bit safe signatures (a default c_int restype would truncate handles/pointers).
HANDLE = wintypes.HANDLE
HGLOBAL = ctypes.c_void_p
LPVOID = ctypes.c_void_p
SIZE_T = ctypes.c_size_t

kernel32.GlobalAlloc.argtypes = (wintypes.UINT, SIZE_T)
kernel32.GlobalAlloc.restype = HGLOBAL
kernel32.GlobalLock.argtypes = (HGLOBAL,)
kernel32.GlobalLock.restype = LPVOID
kernel32.GlobalUnlock.argtypes = (HGLOBAL,)
kernel32.GlobalUnlock.restype = wintypes.BOOL
kernel32.GlobalFree.argtypes = (HGLOBAL,)
kernel32.GlobalFree.restype = HGLOBAL
kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
kernel32.OpenProcess.restype = HANDLE
kernel32.CloseHandle.argtypes = (HANDLE,)
kernel32.QueryFullProcessImageNameW.argtypes = (HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.CreateMutexW.argtypes = (LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
kernel32.CreateMutexW.restype = HANDLE
kernel32.GetCurrentProcess.restype = HANDLE
advapi32.OpenProcessToken.argtypes = (HANDLE, wintypes.DWORD, ctypes.POINTER(HANDLE))
advapi32.OpenProcessToken.restype = wintypes.BOOL

user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.OpenClipboard.argtypes = (wintypes.HWND,)
user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.restype = wintypes.BOOL
user32.GetClipboardData.argtypes = (wintypes.UINT,)
user32.GetClipboardData.restype = HANDLE
user32.SetClipboardData.argtypes = (wintypes.UINT, HANDLE)
user32.SetClipboardData.restype = HANDLE
user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
user32.ShowWindow.restype = wintypes.BOOL
user32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.PostMessageW.restype = wintypes.BOOL
advapi32.LookupPrivilegeValueW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR, LPVOID)
advapi32.LookupPrivilegeValueW.restype = wintypes.BOOL
advapi32.AdjustTokenPrivileges.argtypes = (HANDLE, wintypes.BOOL, LPVOID, wintypes.DWORD, LPVOID, LPVOID)
advapi32.AdjustTokenPrivileges.restype = wintypes.BOOL


def _send(*inputs: INPUT) -> int:
    array = (INPUT * len(inputs))(*inputs)
    return user32.SendInput(len(inputs), array, ctypes.sizeof(INPUT))


def _key_input(vk: int, up: bool, extended: bool = False) -> INPUT:
    flags = KEYEVENTF_KEYUP if up else 0
    if extended:
        flags |= KEYEVENTF_EXTENDEDKEY
    item = INPUT(type=INPUT_KEYBOARD)
    item.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=0)
    return item


def _unicode_input(code_unit: int, up: bool) -> INPUT:
    flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0)
    item = INPUT(type=INPUT_KEYBOARD)
    item.ki = KEYBDINPUT(wVk=0, wScan=code_unit, dwFlags=flags, time=0, dwExtraInfo=0)
    return item


def normalize_key(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise ValueError("空按键名")
    if name in KEYS:
        return name
    if name in KEY_ALIASES:
        return KEY_ALIASES[name]
    upper = name.upper()
    if upper in KEYS:
        return upper
    if upper.startswith("F") and upper[1:].isdigit() and f"F{upper[1:]}" in KEYS:
        return f"F{upper[1:]}"
    raise ValueError(f"未知按键: {name}")


def key_label(name: str) -> str:
    try:
        key = normalize_key(name)
    except ValueError:
        return name
    return KEY_DISPLAY.get(key, key)


def send_key(name: str, down: bool = True, up: bool = True, hold_ms: int = 0) -> None:
    key = normalize_key(name)
    vk, extended = KEYS[key]
    if down:
        _send(_key_input(vk, False, extended))
    if hold_ms:
        time.sleep(max(0, hold_ms) / 1000)
    if up:
        _send(_key_input(vk, True, extended))


def send_combo(keys: Iterable[str], hold_ms: int = 0) -> None:
    resolved = [normalize_key(k) for k in keys if str(k).strip()]
    if not resolved:
        return
    modifiers = [k for k in resolved if k in MODIFIER_KEYS]
    normal = [k for k in resolved if k not in MODIFIER_KEYS]
    # de-duplicate while keeping order
    modifiers = list(dict.fromkeys(modifiers))
    normal = list(dict.fromkeys(normal))

    sent_down: list[tuple[int, bool]] = []
    try:
        for key in modifiers + normal:
            vk, ext = KEYS[key]
            _send(_key_input(vk, False, ext))
            sent_down.append((vk, ext))
        if hold_ms:
            time.sleep(max(0, hold_ms) / 1000)
    finally:
        for vk, ext in reversed(sent_down):
            _send(_key_input(vk, True, ext))


def parse_combo_text(text: str) -> list[str]:
    parts = [p.strip() for p in (text or "").replace("＋", "+").split("+")]
    return [p for p in parts if p]


def send_combo_text(text: str) -> None:
    send_combo(parse_combo_text(text))


def send_text(text: str, interval_ms: int = 0) -> None:
    data = (text or "").encode("utf-16-le", "surrogatepass")
    units = [data[i] | (data[i + 1] << 8) for i in range(0, len(data), 2)]
    for unit in units:
        _send(_unicode_input(unit, False), _unicode_input(unit, True))
        if interval_ms:
            time.sleep(max(0, interval_ms) / 1000)


# ---------------------------------------------------------------------------
# Clipboard
# ---------------------------------------------------------------------------

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002


def _open_clipboard(retries: int = 10) -> bool:
    for _ in range(retries):
        if user32.OpenClipboard(None):
            return True
        time.sleep(0.03)
    return False


def get_clipboard_text() -> str:
    if not _open_clipboard():
        return ""
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return ""
        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def set_clipboard_text(text: str) -> bool:
    data = (text or "").encode("utf-16-le", "surrogatepass") + b"\x00\x00"
    if not _open_clipboard():
        return False
    handle = None
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not handle:
            return False
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return False
        try:
            ctypes.memmove(ptr, data, len(data))
        finally:
            kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            return False
        handle = None  # ownership transferred to the clipboard
        return True
    finally:
        if handle:
            kernel32.GlobalFree(handle)
        user32.CloseClipboard()


def paste_text(text: str) -> None:
    previous = get_clipboard_text()
    set_clipboard_text(text)
    time.sleep(0.05)
    send_combo(["Ctrl", "V"])
    time.sleep(0.12)
    try:
        if previous:
            set_clipboard_text(previous)
        else:
            if _open_clipboard():
                try:
                    user32.EmptyClipboard()
                finally:
                    user32.CloseClipboard()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Mouse
# ---------------------------------------------------------------------------

def _mouse_input(dx: int = 0, dy: int = 0, data: int = 0, flags: int = 0) -> INPUT:
    item = INPUT(type=INPUT_MOUSE)
    item.mi = MOUSEINPUT(dx=int(dx), dy=int(dy), mouseData=int(data), dwFlags=int(flags), time=0, dwExtraInfo=0)
    return item


def mouse_click(button: str = "left", count: int = 1) -> None:
    button = (button or "left").lower()
    down, up = {
        "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
        "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
        "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
    }.get(button, (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP))
    for i in range(max(1, int(count))):
        _send(_mouse_input(flags=down), _mouse_input(flags=up))
        if count > 1 and i < count - 1:
            time.sleep(0.03)


def mouse_wheel(delta: int = 120, horizontal: bool = False) -> None:
    flags = MOUSEEVENTF_HWHEEL if horizontal else MOUSEEVENTF_WHEEL
    _send(_mouse_input(data=int(delta), flags=flags))


def mouse_move_rel(dx: int, dy: int) -> None:
    _send(_mouse_input(dx=int(dx), dy=int(dy), flags=MOUSEEVENTF_MOVE))


def get_screen_metrics() -> tuple[int, int, int, int]:
    # virtual screen: x, y, width, height
    x = user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
    y = user32.GetSystemMetrics(77)
    w = user32.GetSystemMetrics(78)
    h = user32.GetSystemMetrics(79)
    if not w or not h:
        w = user32.GetSystemMetrics(0)
        h = user32.GetSystemMetrics(1)
        x = y = 0
    return x, y, w, h


def mouse_move_abs(x: float, y: float) -> None:
    # Accept either absolute screen pixels or normalized 0..65535.
    vx, vy, vw, vh = get_screen_metrics()
    if 0 <= x <= 65535 and 0 <= y <= 65535 and (x > vw or y > vh):
        nx, ny = int(x), int(y)
    else:
        nx = int((float(x) - vx) * 65535 / max(1, vw - 1))
        ny = int((float(y) - vy) * 65535 / max(1, vh - 1))
    flags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
    _send(_mouse_input(dx=nx, dy=ny, flags=flags))


# ---------------------------------------------------------------------------
# Windows / processes
# ---------------------------------------------------------------------------

def get_foreground_window() -> int:
    return int(user32.GetForegroundWindow() or 0)


def get_foreground_process_name() -> str:
    hwnd = get_foreground_window()
    if not hwnd:
        return ""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return ""
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(1024)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return Path(buf.value).name.lower()
        return ""
    finally:
        kernel32.CloseHandle(handle)


def window_control(action: str) -> None:
    hwnd = get_foreground_window()
    SW_MINIMIZE = 6
    SW_MAXIMIZE = 3
    SW_RESTORE = 9
    WM_CLOSE = 0x0010
    if action == "minimize" and hwnd:
        user32.ShowWindow(hwnd, SW_MINIMIZE)
    elif action == "maximize" and hwnd:
        user32.ShowWindow(hwnd, SW_MAXIMIZE)
    elif action == "restore" and hwnd:
        user32.ShowWindow(hwnd, SW_RESTORE)
    elif action == "close" and hwnd:
        user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    elif action == "switch":
        send_combo(["Alt", "Tab"])


# ---------------------------------------------------------------------------
# Shell / process launching
# ---------------------------------------------------------------------------

def shell_open(target: str, args: str = "", cwd: str = "", run_as_admin: bool = False, verb: str = "open") -> None:
    target = (target or "").strip()
    if not target:
        raise ValueError("路径为空")
    if target.startswith("ms-") or target.startswith("shell:"):
        os.startfile(target)  # type: ignore[attr-defined]
        return
    result = shell32.ShellExecuteW(
        None,
        "runas" if run_as_admin else verb,
        target,
        args or None,
        cwd or None,
        1,
    )
    if int(result) <= 32:
        raise OSError(f"ShellExecute 失败，代码 {int(result)}")


def open_target(target: str, args: str = "", cwd: str = "", run_as_admin: bool = False) -> None:
    target = (target or "").strip()
    if not target:
        raise ValueError("目标为空")
    if target.lower().startswith(("http://", "https://", "www.")):
        if target.lower().startswith("www."):
            target = "https://" + target
        os.startfile(target)  # type: ignore[attr-defined]
        return
    # ShellExecute is required whenever arguments or a working directory are set.
    if args or cwd or run_as_admin:
        shell_open(target, args=args, cwd=cwd, run_as_admin=run_as_admin)
        return
    try:
        if os.path.isdir(target) or os.path.isfile(target):
            os.startfile(target)  # type: ignore[attr-defined]
            return
    except OSError:
        pass
    shell_open(target, args=args, cwd=cwd, run_as_admin=run_as_admin)


CREATE_NO_WINDOW = 0x08000000


def run_command(command: str, shell: str = "powershell", hidden: bool = True, cwd: str = "") -> None:
    command = (command or "").strip()
    if not command:
        raise ValueError("命令为空")
    shell = (shell or "powershell").lower()
    flags = CREATE_NO_WINDOW if hidden else 0
    common = dict(
        cwd=cwd or None,
        creationflags=flags,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL if hidden else None,
        stderr=subprocess.DEVNULL if hidden else None,
        close_fds=True,
    )
    if shell in {"cmd", "bat"}:
        # Let cmd.exe parse the command line directly. Passing a quoted argument
        # list through CreateProcess breaks cmd's handling of embedded quotes.
        subprocess.Popen(command, shell=True, **common)
    elif shell == "powershell":
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            **common,
        )
    else:
        subprocess.Popen(command, shell=True, **common)


# ---------------------------------------------------------------------------
# System actions
# ---------------------------------------------------------------------------

def _enable_shutdown_privilege() -> None:
    TOKEN_ADJUST_PRIVILEGES = 0x0020
    TOKEN_QUERY = 0x0008
    SE_PRIVILEGE_ENABLED = 0x0002

    class LUID(ctypes.Structure):
        _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]

    class LUID_AND_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("Luid", LUID), ("Attributes", wintypes.DWORD)]

    class TOKEN_PRIVILEGES(ctypes.Structure):
        _fields_ = [("PrivilegeCount", wintypes.DWORD), ("Privileges", LUID_AND_ATTRIBUTES * 1)]

    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY, ctypes.byref(token)):
        return
    try:
        luid = LUID()
        if not advapi32.LookupPrivilegeValueW(None, "SeShutdownPrivilege", ctypes.byref(luid)):
            return
        tp = TOKEN_PRIVILEGES()
        tp.PrivilegeCount = 1
        tp.Privileges[0].Luid = luid
        tp.Privileges[0].Attributes = SE_PRIVILEGE_ENABLED
        advapi32.AdjustTokenPrivileges(token, False, ctypes.byref(tp), 0, None, None)
    finally:
        kernel32.CloseHandle(token)


def system_action(action: str) -> str:
    action = (action or "").lower()
    if action == "lock":
        user32.LockWorkStation()
        return ""
    if action == "sleep":
        powrprof.SetSuspendState(False, False, False)
        return ""
    if action in {"shutdown", "restart", "signout"}:
        _enable_shutdown_privilege()
        flags = {"shutdown": 0x00000001, "restart": 0x00000002, "signout": 0x00000000}[action]
        user32.ExitWindowsEx(flags, 0)
        return ""
    if action == "taskmgr":
        subprocess.Popen(["taskmgr.exe"])
        return ""
    if action == "explorer":
        subprocess.Popen(["explorer.exe"])
        return ""
    if action == "settings":
        os.startfile("ms-settings:")  # type: ignore[attr-defined]
        return ""
    if action == "terminal":
        try:
            subprocess.Popen(["wt.exe"])
        except OSError:
            subprocess.Popen(["powershell.exe"])
        return ""
    if action == "show_desktop":
        send_combo(["Win", "D"])
        return ""
    if action == "volume_up":
        send_key("VolumeUp")
        return ""
    if action == "volume_down":
        send_key("VolumeDown")
        return ""
    if action == "volume_mute":
        send_key("VolumeMute")
        return ""
    if action == "empty_recycle":
        shell32.SHEmptyRecycleBinW(None, None, 0x00000007)
        return ""
    if action == "screenshot":
        return take_screenshot()
    raise ValueError(f"未知系统动作: {action}")


def take_screenshot() -> str:
    try:
        from PIL import ImageGrab
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("缺少 Pillow，无法截屏") from exc
    folder = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Pictures" / "Keypad Studio"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    img = ImageGrab.grab(all_screens=True)
    img.save(path)
    return str(path)


# ---------------------------------------------------------------------------
# Autostart / single instance
# ---------------------------------------------------------------------------

AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_NAME = "KeypadStudio"


def app_launch_command(minimized: bool = True) -> str:
    if getattr(sys, "frozen", False):
        exe = sys.executable
        return f'"{exe}"' + (" --minimized" if minimized else "")
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    script = Path(__file__).resolve().parent.parent / "app.py"
    exe = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{exe}" "{script}"' + (" --minimized" if minimized else "")


def set_autostart(enabled: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, AUTOSTART_NAME, 0, winreg.REG_SZ, app_launch_command(True))
        else:
            try:
                winreg.DeleteValue(key, AUTOSTART_NAME)
            except FileNotFoundError:
                pass


def is_autostart_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY) as key:
            value, _ = winreg.QueryValueEx(key, AUTOSTART_NAME)
            return bool(value)
    except OSError:
        return False


def create_single_instance_mutex() -> tuple[bool, int]:
    ERROR_ALREADY_EXISTS = 183
    handle = kernel32.CreateMutexW(None, False, "Local\\KeypadStudio_SingleInstance")
    already = ctypes.get_last_error() == ERROR_ALREADY_EXISTS
    return already, int(handle or 0)


def open_data_folder(path: str) -> None:
    os.startfile(path)  # type: ignore[attr-defined]
