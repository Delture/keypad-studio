"""Self-update through GitHub Releases.

The packaged app checks ``Delture/keypad-studio`` for a newer release, downloads
``KeypadStudio-win64.zip`` and lets a small batch file replace the installation
after the current process has exited.  Source checkouts never install.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Callable

from .constants import VERSION

REPO = "Delture/keypad-studio"
REPO_URL = f"https://github.com/{REPO}"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
ASSET_NAME = "KeypadStudio-win64.zip"
USER_AGENT = f"KeypadStudio/{VERSION} (+{REPO_URL})"
STAGE_FOLDER = "KeypadStudioUpdate"

CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008


def parse_version(text: str) -> tuple[int, ...]:
    parts: list[int] = []
    for chunk in str(text or "").strip().lstrip("vV").split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts) or (0,)


def _system_proxies() -> dict[str, str]:
    """Proxy map from environment, falling back to the Windows WinINET settings.

    ``urllib`` skips the registry when the environment only defines ``NO_PROXY``,
    which is common with Clash/系统代理; read the registry ourselves so asset
    downloads work there too.
    """
    proxies = {key: value for key, value in urllib.request.getproxies().items() if key in ("http", "https")}
    if proxies:
        return proxies
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
        ) as key:
            enabled = int(winreg.QueryValueEx(key, "ProxyEnable")[0])
            if not enabled:
                return {}
            server = str(winreg.QueryValueEx(key, "ProxyServer")[0]).strip()
    except Exception:
        return {}
    if not server:
        return {}
    if "=" not in server:
        if not server.startswith(("http://", "https://")):
            server = "http://" + server
        return {"http": server, "https": server}
    result: dict[str, str] = {}
    for part in server.split(";"):
        name, _, value = part.partition("=")
        name = name.strip().lower()
        value = value.strip()
        if name in ("http", "https") and value:
            if not value.startswith(("http://", "https://")):
                value = "http://" + value
            result[name] = value
    return result


def _open(request: urllib.request.Request, timeout: float):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler(_system_proxies()))
    return opener.open(request, timeout=timeout)


def _error_message(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 404:
            return "仓库里还没有发布任何版本"
        if exc.code in (403, 429):
            return "GitHub 接口访问太频繁，请稍后再试"
        return f"GitHub 返回错误 {exc.code}"
    if isinstance(exc, urllib.error.URLError):
        return "网络连接失败，请检查网络或代理后重试"
    return str(exc) or exc.__class__.__name__


class Updater:
    def __init__(self, emit: Callable[[dict], None], on_quit: Callable[[], Any]) -> None:
        self._emit_event = emit
        self._on_quit = on_quit
        self.lock = threading.RLock()
        self._checking = False
        self._busy = False
        self._release: dict | None = None
        self._auto_checked = False
        self.status: dict[str, Any] = {
            "phase": "idle",
            "current": VERSION,
            "canInstall": self.install_dir() is not None,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def install_dir() -> Path | None:
        if not getattr(sys, "frozen", False):
            return None
        return Path(sys.executable).resolve().parent

    def state(self) -> dict:
        with self.lock:
            return dict(self.status)

    def _set(self, **patch: Any) -> None:
        with self.lock:
            self.status = {**self.status, **patch}
            snapshot = dict(self.status)
        self._emit_event({"type": "update", "update": snapshot})

    @staticmethod
    def _asset(release: dict) -> dict | None:
        for asset in release.get("assets") or []:
            if asset.get("name") == ASSET_NAME:
                return asset
        return None

    # ------------------------------------------------------------------
    # Check
    # ------------------------------------------------------------------

    def check_async(self, notify: bool = False) -> dict:
        with self.lock:
            if self._checking:
                return {"ok": True, "update": dict(self.status)}
            self._checking = True
            self.status = {**self.status, "phase": "checking", "error": None}
            snapshot = dict(self.status)
        self._emit_event({"type": "update", "update": snapshot})
        threading.Thread(target=self._check_worker, args=(notify,), name="UpdateCheck", daemon=True).start()
        return {"ok": True}

    def _check_worker(self, notify: bool = False) -> None:
        try:
            request = urllib.request.Request(
                API_LATEST,
                headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
            )
            with _open(request, 15) as response:
                release = json.loads(response.read().decode("utf-8"))
            latest = str(release.get("tag_name") or "").lstrip("vV")
            asset = self._asset(release)
            available = parse_version(latest) > parse_version(VERSION)
            with self.lock:
                self._release = release if available else None
                self.status = {
                    "phase": "available" if available else "uptodate",
                    "current": VERSION,
                    "canInstall": self.install_dir() is not None,
                    "latest": latest,
                    "notes": (release.get("body") or "").strip()[:1500],
                    "published": release.get("published_at") or "",
                    "page": release.get("html_url") or REPO_URL,
                    "asset": bool(asset),
                    "size": int((asset or {}).get("size") or 0),
                    "error": None,
                }
                snapshot = dict(self.status)
            self._emit_event({"type": "update", "update": snapshot})
            if notify and available and asset:
                if self.install_dir() is not None:
                    message = f"发现新版本 {latest}，可在「设置 → 软件更新」里安装"
                else:
                    message = f"发现新版本 {latest}，源码运行请到发布页下载"
                self._emit_event({"type": "toast", "message": message, "kind": "info"})
        except Exception as exc:
            self._set(phase="error", error=_error_message(exc))
        finally:
            with self.lock:
                self._checking = False

    def auto_check(self, enabled: bool = True) -> None:
        with self.lock:
            if self._auto_checked:
                return
            self._auto_checked = True
        if enabled:
            self.check_async(notify=True)

    # ------------------------------------------------------------------
    # Download / stage
    # ------------------------------------------------------------------

    def begin_install(self) -> dict:
        if self.install_dir() is None:
            return {"ok": False, "error": "源码运行模式不支持自动更新"}
        with self.lock:
            if self._busy or self._checking:
                return {"ok": False, "error": "正在处理更新，请稍候"}
            release = self._release
            if not release:
                return {"ok": False, "error": "请先检查更新"}
            asset = self._asset(release)
            if not asset:
                return {"ok": False, "error": "新版本已发布，但安装包还在编译中，请稍后再试"}
            self._busy = True
            self.status = {
                **self.status,
                "phase": "downloading",
                "progress": 0,
                "downloaded": 0,
                "error": None,
            }
            snapshot = dict(self.status)
            latest = str(release.get("tag_name") or "").lstrip("vV") or "latest"
        self._emit_event({"type": "update", "update": snapshot})
        threading.Thread(target=self._download_worker, args=(asset, latest), name="UpdateDownload", daemon=True).start()
        return {"ok": True}

    def _download_worker(self, asset: dict, latest: str) -> None:
        stage = Path(tempfile.gettempdir()) / STAGE_FOLDER / latest
        try:
            shutil.rmtree(stage.parent, ignore_errors=True)
            stage.mkdir(parents=True, exist_ok=True)
            archive = stage / ASSET_NAME
            request = urllib.request.Request(
                asset["browser_download_url"],
                headers={"User-Agent": USER_AGENT, "Accept": "application/octet-stream"},
            )
            total = int(asset.get("size") or 0)
            done = 0
            last_emit = 0.0
            with _open(request, 30) as response, open(archive, "wb") as handle:
                declared = int(response.headers.get("Content-Length") or 0)
                total = total or declared
                while True:
                    chunk = response.read(262144)
                    if not chunk:
                        break
                    handle.write(chunk)
                    done += len(chunk)
                    now = time.time()
                    if now - last_emit > 0.25:
                        last_emit = now
                        progress = int(done * 100 / total) if total else 0
                        self._set(progress=min(99, progress), downloaded=done, total=total)

            payload = stage / "payload"
            self._set(phase="extracting", progress=100)
            digest = str(asset.get("digest") or "")
            if digest.lower().startswith("sha256:"):
                actual = hashlib.sha256(archive.read_bytes()).hexdigest()
                if actual != digest.split(":", 1)[1].strip().lower():
                    raise RuntimeError("安装包校验失败，请在发布页重新下载")
            payload.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(archive) as bundle:
                root = payload.resolve()
                for member in bundle.infolist():
                    target = (payload / member.filename).resolve()
                    if target != root and root not in target.parents:
                        raise RuntimeError("安装包里含有非法路径")
                bundle.extractall(payload)

            exe_root = payload
            if not (exe_root / "KeypadStudio.exe").exists():
                nested = payload / "KeypadStudio"
                if (nested / "KeypadStudio.exe").exists():
                    exe_root = nested
                else:
                    raise RuntimeError("安装包内容不完整（缺少 KeypadStudio.exe）")

            self._set(phase="ready", progress=100, payload=str(exe_root), stage=str(stage), latest=latest)
        except Exception as exc:
            self._set(phase="error", error=_error_message(exc))
            shutil.rmtree(stage, ignore_errors=True)
        finally:
            with self.lock:
                self._busy = False

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------

    def apply(self) -> dict:
        target = self.install_dir()
        if target is None:
            return {"ok": False, "error": "源码运行模式不支持自动更新"}
        with self.lock:
            status = dict(self.status)
        if status.get("phase") != "ready":
            return {"ok": False, "error": "更新还没有下载完成"}
        payload = Path(str(status.get("payload") or ""))
        stage = Path(str(status.get("stage") or ""))
        if not payload.exists() or not stage.exists():
            return {"ok": False, "error": "更新文件已丢失，请重新下载"}
        script = stage / "apply-update.bat"
        try:
            _write_batch(script, _batch_script(os.getpid(), target, payload))
            subprocess.Popen(
                ["cmd.exe", "/c", str(script)],
                cwd=str(stage),
                creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
        except Exception as exc:
            return {"ok": False, "error": f"无法启动更新程序：{exc}"}
        self._set(phase="installing")
        threading.Timer(1.2, self._on_quit).start()
        return {"ok": True}


def _write_batch(path: Path, text: str) -> None:
    # cmd.exe reads .bat files with the ANSI/OEM code page on Chinese Windows,
    # so prefer mbcs for paths with non-ASCII characters.
    for encoding in ("mbcs", "utf-8"):
        try:
            path.write_text(text, encoding=encoding, newline="\r\n")
            return
        except (LookupError, UnicodeEncodeError):
            continue
    path.write_text(text, encoding="utf-8", newline="\r\n")


def _batch_script(pid: int, target: Path, payload: Path) -> str:
    def quote(value: Path) -> str:
        return str(value).replace("%", "%%")

    return f"""@echo off
setlocal DisableDelayedExpansion
title Keypad Studio updater
set "WAIT_PID={pid}"
set "TARGET={quote(target)}"
set "PAYLOAD={quote(payload)}"
set /a TRIES=0
:wait
set /a TRIES+=1
if %TRIES% GTR 90 goto install
tasklist /FI "PID eq %WAIT_PID%" 2>nul | find "%WAIT_PID%" >nul
if errorlevel 1 goto install
ping -n 2 127.0.0.1 >nul
goto wait
:install
ping -n 3 127.0.0.1 >nul
robocopy "%PAYLOAD%" "%TARGET%" /E /R:2 /W:1 /NFL /NDL /NJH /NJS /NP >nul
start "" "%TARGET%\\KeypadStudio.exe"
exit /b 0
"""
