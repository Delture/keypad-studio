"""Per-application volume control via the Windows audio session API."""
from __future__ import annotations

from typing import Tuple


def set_app_volume(process_name: str, mode: str = "toggle") -> Tuple[bool, str]:
    """Change one application's volume in the Windows Volume Mixer.

    mode:
      toggle — if muted/0%, restore 100%; otherwise mute
      mute   — mute
      full   — set to 100% and unmute
    """
    try:
        import comtypes
        from pycaw.pycaw import AudioUtilities
    except Exception:
        return False, "缺少 pycaw 组件，请重新安装应用"

    try:
        comtypes.CoInitialize()
    except Exception:
        pass

    display = (process_name or "cs2.exe").strip() or "cs2.exe"
    normalized = display.lower()
    base = normalized[:-4] if normalized.endswith(".exe") else normalized

    try:
        sessions = []
        for session in AudioUtilities.GetAllSessions():
            try:
                process = session.Process
                if not process:
                    continue
                name = process.name().lower()
                if name == normalized or name == base or name == base + ".exe":
                    sessions.append(session.SimpleAudioVolume)
            except Exception:
                continue

        if not sessions:
            return False, f"未找到 {display} 的音频会话"

        muted = all(
            bool(volume.GetMute()) or float(volume.GetMasterVolume()) <= 0.001
            for volume in sessions
        )

        mode = (mode or "toggle").lower()
        if mode == "mute":
            target_mute = True
            target_volume = None
        elif mode == "full":
            target_mute = False
            target_volume = 1.0
        else:
            if muted:
                target_mute = False
                target_volume = 1.0
            else:
                target_mute = True
                target_volume = None

        for volume in sessions:
            if target_volume is not None:
                volume.SetMasterVolume(float(target_volume), None)
            volume.SetMute(bool(target_mute), None)

        if target_mute:
            return True, f"{display} 已静音"
        return True, f"{display} 音量已设为 100%"
    except Exception as exc:
        return False, f"设置 {display} 音量失败：{exc}"
