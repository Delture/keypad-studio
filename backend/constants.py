"""Shared constants for Keypad Studio."""
from __future__ import annotations

APP_NAME = "Keypad Studio"
APP_NAME_CN = "小键盘工作室"
APP_ID = "KeypadStudio"
VERSION = "1.5.0"

VENDOR_ID = 0x5A5A
PRODUCT_ID = 0x2023
KEY_COUNT = 6

# Trigger id -> physical slot (1 = leftmost). Learned from the Single6VerticalAdvanced
# firmware: the wiring reports key ids in reverse order.
DEFAULT_TRIGGER_MAP = {6: 1, 5: 2, 4: 3, 3: 4, 2: 5, 1: 6}

MODEL_NAMES = {
    0x99: "Single6VerticalAdvanced",
    0x98: "Single3Plus5Advanced",
    0x97: "Triplex9Advanced",
    0x96: "Double6Advanced",
    0x95: "Double4Advanced",
    0x94: "Single4Advanced",
    0x93: "Single3Advanced",
    0x91: "Single2Advanced",
    0x90: "Single1Advanced",
    0x8F: "DiyAllKeyboardAdvanced",
    0x3F: "L3_Triplex9Advanced",
    0x3E: "L3_Double8Advanced",
    0x3D: "L3_Double6Advanced",
    0x3C: "L3_Single6VerticalAdvanced",
}

# ---------------------------------------------------------------------------
# Keyboard keys
# ---------------------------------------------------------------------------

# canonical name -> (virtual-key code, extended)
KEYS: dict[str, tuple[int, bool]] = {}

for _i in range(26):
    _ch = chr(ord("A") + _i)
    KEYS[_ch] = (ord(_ch), False)
for _d in range(10):
    KEYS[str(_d)] = (ord(str(_d)), False)
for _i in range(24):
    KEYS[f"F{_i + 1}"] = (0x70 + _i, False)

KEYS.update({
    "Backspace": (0x08, False),
    "Tab": (0x09, False),
    "Enter": (0x0D, False),
    "Shift": (0x10, False),
    "Ctrl": (0x11, False),
    "Alt": (0x12, False),
    "Pause": (0x13, False),
    "CapsLock": (0x14, False),
    "Esc": (0x1B, False),
    "Space": (0x20, False),
    "PageUp": (0x21, True),
    "PageDown": (0x22, True),
    "End": (0x23, True),
    "Home": (0x24, True),
    "Left": (0x25, True),
    "Up": (0x26, True),
    "Right": (0x27, True),
    "Down": (0x28, True),
    "PrintScreen": (0x2C, True),
    "Insert": (0x2D, True),
    "Delete": (0x2E, True),
    "NumLock": (0x90, True),
    "ScrollLock": (0x91, False),
    "LWin": (0x5B, True),
    "RWin": (0x5C, True),
    "Win": (0x5B, True),
    "Apps": (0x5D, True),
    "Sleep": (0x5F, False),
    "Numpad0": (0x60, False),
    "Numpad1": (0x61, False),
    "Numpad2": (0x62, False),
    "Numpad3": (0x63, False),
    "Numpad4": (0x64, False),
    "Numpad5": (0x65, False),
    "Numpad6": (0x66, False),
    "Numpad7": (0x67, False),
    "Numpad8": (0x68, False),
    "Numpad9": (0x69, False),
    "NumpadMultiply": (0x6A, False),
    "NumpadAdd": (0x6B, False),
    "NumpadSubtract": (0x6D, False),
    "NumpadDecimal": (0x6E, False),
    "NumpadDivide": (0x6F, True),
    "LShift": (0xA0, False),
    "RShift": (0xA1, False),
    "LCtrl": (0xA2, False),
    "RCtrl": (0xA3, True),
    "LAlt": (0xA4, False),
    "RAlt": (0xA5, True),
    "BrowserBack": (0xA6, True),
    "BrowserForward": (0xA7, True),
    "BrowserRefresh": (0xA8, True),
    "BrowserStop": (0xA9, True),
    "BrowserSearch": (0xAA, True),
    "BrowserFavorites": (0xAB, True),
    "BrowserHome": (0xAC, True),
    "VolumeMute": (0xAD, True),
    "VolumeDown": (0xAE, True),
    "VolumeUp": (0xAF, True),
    "MediaNextTrack": (0xB0, True),
    "MediaPrevTrack": (0xB1, True),
    "MediaStop": (0xB2, True),
    "MediaPlayPause": (0xB3, True),
    "LaunchMail": (0xB4, True),
    "LaunchMediaSelect": (0xB5, True),
    "LaunchApp1": (0xB6, True),
    "LaunchApp2": (0xB7, True),
    "Semicolon": (0xBA, False),
    "Equals": (0xBB, False),
    "Comma": (0xBC, False),
    "Minus": (0xBD, False),
    "Period": (0xBE, False),
    "Slash": (0xBF, False),
    "Backtick": (0xC0, False),
    "LeftBracket": (0xDB, False),
    "Backslash": (0xDC, False),
    "RightBracket": (0xDD, False),
    "Quote": (0xDE, False),
})

# Aliases accepted in stored configs and user-entered combos.
KEY_ALIASES = {
    "Control": "Ctrl",
    "Escape": "Esc",
    "Return": "Enter",
    "Del": "Delete",
    "Ins": "Insert",
    "PgUp": "PageUp",
    "PgDn": "PageDown",
    "SpaceBar": "Space",
    "Meta": "Win",
    "Super": "Win",
    "Command": "Win",
    "Option": "Alt",
    "LControl": "LCtrl",
    "RControl": "RCtrl",
    "LMenu": "LAlt",
    "RMenu": "RAlt",
    "Multiply": "NumpadMultiply",
    "Add": "NumpadAdd",
    "Subtract": "NumpadSubtract",
    "Decimal": "NumpadDecimal",
    "Divide": "NumpadDivide",
    "PlayPause": "MediaPlayPause",
    "NextTrack": "MediaNextTrack",
    "PrevTrack": "MediaPrevTrack",
    "Mute": "VolumeMute",
    "VolUp": "VolumeUp",
    "VolDown": "VolumeDown",
}

MODIFIER_KEYS = {"Ctrl", "Shift", "Alt", "Win", "LCtrl", "RCtrl", "LShift", "RShift", "LAlt", "RAlt", "LWin", "RWin"}

KEY_DISPLAY = {
    "Ctrl": "Ctrl", "Shift": "Shift", "Alt": "Alt", "Win": "Win",
    "LCtrl": "左 Ctrl", "RCtrl": "右 Ctrl", "LShift": "左 Shift", "RShift": "右 Shift",
    "LAlt": "左 Alt", "RAlt": "右 Alt", "LWin": "左 Win", "RWin": "右 Win",
    "Enter": "Enter", "Esc": "Esc", "Space": "空格", "Tab": "Tab", "Backspace": "退格",
    "Delete": "Delete", "Insert": "Insert", "Home": "Home", "End": "End",
    "PageUp": "Page Up", "PageDown": "Page Down",
    "Up": "↑", "Down": "↓", "Left": "←", "Right": "→",
    "CapsLock": "Caps Lock", "NumLock": "Num Lock", "ScrollLock": "Scroll Lock",
    "PrintScreen": "Print Screen", "Pause": "Pause",
    "VolumeUp": "音量 +", "VolumeDown": "音量 −", "VolumeMute": "静音",
    "MediaPlayPause": "播放 / 暂停", "MediaNextTrack": "下一曲", "MediaPrevTrack": "上一曲",
    "MediaStop": "停止", "BrowserBack": "浏览器后退", "BrowserForward": "浏览器前进",
    "BrowserRefresh": "浏览器刷新", "BrowserHome": "浏览器主页",
    "Semicolon": ";", "Equals": "=", "Comma": ",", "Minus": "-", "Period": ".",
    "Slash": "/", "Backtick": "`", "LeftBracket": "[", "Backslash": "\\",
    "RightBracket": "]", "Quote": "'",
    "NumpadMultiply": "小键盘 *", "NumpadAdd": "小键盘 +", "NumpadSubtract": "小键盘 −",
    "NumpadDecimal": "小键盘 .", "NumpadDivide": "小键盘 /",
}

KEY_GROUPS = [
    {
        "name": "字母与数字",
        "keys": list("ABCDEFGHIJKLMNOPQRSTUVWXYZ") + [str(i) for i in range(10)],
    },
    {
        "name": "功能键",
        "keys": [f"F{i}" for i in range(1, 25)],
    },
    {
        "name": "控制键",
        "keys": ["Enter", "Esc", "Tab", "Space", "Backspace", "Delete", "Insert",
                 "Home", "End", "PageUp", "PageDown", "Up", "Down", "Left", "Right",
                 "CapsLock", "NumLock", "ScrollLock", "PrintScreen", "Pause"],
    },
    {
        "name": "修饰键",
        "keys": ["Ctrl", "Shift", "Alt", "Win", "LCtrl", "RCtrl", "LShift", "RShift",
                 "LAlt", "RAlt", "LWin", "RWin"],
    },
    {
        "name": "符号",
        "keys": ["Semicolon", "Equals", "Comma", "Minus", "Period", "Slash", "Backtick",
                 "LeftBracket", "Backslash", "RightBracket", "Quote"],
    },
    {
        "name": "多媒体",
        "keys": ["VolumeUp", "VolumeDown", "VolumeMute", "MediaPlayPause",
                 "MediaNextTrack", "MediaPrevTrack", "MediaStop", "BrowserBack",
                 "BrowserForward", "BrowserRefresh", "BrowserHome"],
    },
    {
        "name": "小键盘",
        "keys": [f"Numpad{i}" for i in range(10)] + ["NumpadMultiply", "NumpadAdd",
                                                       "NumpadSubtract", "NumpadDecimal", "NumpadDivide"],
    },
]

MEDIA_ACTIONS = {
    "play_pause": "MediaPlayPause",
    "next": "MediaNextTrack",
    "prev": "MediaPrevTrack",
    "stop": "MediaStop",
    "volume_up": "VolumeUp",
    "volume_down": "VolumeDown",
    "mute": "VolumeMute",
    "browser_back": "BrowserBack",
    "browser_forward": "BrowserForward",
    "browser_refresh": "BrowserRefresh",
    "browser_home": "BrowserHome",
}

MEDIA_LABELS = {
    "play_pause": "播放 / 暂停",
    "next": "下一曲",
    "prev": "上一曲",
    "stop": "停止",
    "volume_up": "音量 +",
    "volume_down": "音量 −",
    "mute": "静音",
    "browser_back": "浏览器后退",
    "browser_forward": "浏览器前进",
    "browser_refresh": "浏览器刷新",
    "browser_home": "浏览器主页",
}

ACTION_TYPES = [
    {"id": "key", "name": "键盘按键", "desc": "发送一个按键或组合键", "icon": "keyboard"},
    {"id": "text", "name": "文本输入", "desc": "输入一段文字，支持中文", "icon": "text"},
    {"id": "open", "name": "打开 / 运行", "desc": "打开程序、文件、文件夹或网址", "icon": "folder"},
    {"id": "command", "name": "运行命令", "desc": "执行 PowerShell、CMD 或 bat", "icon": "terminal"},
    {"id": "macro", "name": "宏序列", "desc": "多步骤的键鼠脚本，可循环", "icon": "macro"},
    {"id": "media", "name": "多媒体", "desc": "播放、音量、浏览器控制", "icon": "music"},
    {"id": "app_volume", "name": "应用音量", "desc": "切换单个程序在音量合成器中的音量", "icon": "volume"},
    {"id": "network_toggle", "name": "网络切换", "desc": "Tailscale 与 Clash Party 的组合切换", "icon": "network"},
    {"id": "mouse", "name": "鼠标动作", "desc": "点击、滚轮、移动", "icon": "mouse"},
    {"id": "system", "name": "系统功能", "desc": "锁屏、睡眠、任务管理器等", "icon": "power"},
    {"id": "clipboard", "name": "剪贴板", "desc": "复制、粘贴、写入文本", "icon": "clipboard"},
    {"id": "window", "name": "窗口操作", "desc": "最小化、最大化、关闭、切换", "icon": "window"},
    {"id": "layer", "name": "切换图层", "desc": "在当前配置的不同图层间切换", "icon": "layers"},
    {"id": "profile", "name": "切换配置", "desc": "切换整套按键配置", "icon": "grid"},
    {"id": "delay", "name": "延时", "desc": "等待一段时间", "icon": "clock"},
    {"id": "none", "name": "无动作", "desc": "按下后不做任何事", "icon": "ban"},
]

SYSTEM_ACTIONS = {
    "lock": "锁定电脑",
    "sleep": "睡眠",
    "shutdown": "关机",
    "restart": "重启",
    "taskmgr": "任务管理器",
    "explorer": "文件资源管理器",
    "settings": "Windows 设置",
    "terminal": "终端 / PowerShell",
    "show_desktop": "显示桌面",
    "screenshot": "截屏到图片",
    "empty_recycle": "清空回收站",
    "signout": "注销",
    "volume_up": "音量 +",
    "volume_down": "音量 −",
    "volume_mute": "静音",
}

CLIPBOARD_ACTIONS = {
    "copy": "复制 (Ctrl+C)",
    "paste": "粘贴 (Ctrl+V)",
    "cut": "剪切 (Ctrl+X)",
    "select_all": "全选 (Ctrl+A)",
    "undo": "撤销 (Ctrl+Z)",
    "set": "写入剪贴板",
    "clear": "清空剪贴板",
}

WINDOW_ACTIONS = {
    "minimize": "最小化当前窗口",
    "maximize": "最大化当前窗口",
    "restore": "还原当前窗口",
    "close": "关闭当前窗口",
    "switch": "切换窗口 (Alt+Tab)",
}

MOUSE_ACTIONS = {
    "left": "左键单击",
    "right": "右键单击",
    "middle": "中键单击",
    "double": "左键双击",
    "wheel_up": "滚轮向上",
    "wheel_down": "滚轮向下",
    "move_rel": "相对移动",
    "move_abs": "移动到屏幕坐标",
}
