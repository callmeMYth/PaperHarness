"""PaperHarness Native Frameless Windows Desktop Application (Source & Frozen .exe).

Opens a pure standalone Windows desktop window via WebView2 (no browser tabs, no URL bar,
custom draggable titlebar with minimize/maximize/close via `window.pywebview.api`).
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import traceback
import urllib.request
from pathlib import Path

IS_FROZEN = getattr(sys, "frozen", False)
ROOT = Path(sys.executable).resolve().parent if IS_FROZEN else Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_mpl_dir = ROOT / "local_data" / "mpl_cache"
_mpl_dir.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_mpl_dir))

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")


def _pick_port(preferred: int = 8765) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(("127.0.0.1", preferred)) != 0:
            return preferred
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_ready(url: str, timeout: float = 25.0) -> bool:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with opener.open(f"{url}/api/health", timeout=1) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.15)
    return False


def _alert_error(msg: str) -> None:
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, msg, "PaperHarness", 0x10)
        except Exception:
            pass


class DesktopWindowBridge:
    """JS bridge exposed at `window.pywebview.api` for native frameless window & file dialogs."""

    def __init__(self) -> None:
        self._window = None
        self._maximized = False
        self._last_dir = str(ROOT / "local_data" / "exports")
        Path(self._last_dir).mkdir(parents=True, exist_ok=True)

    def bind(self, win) -> None:
        self._window = win

    def is_desktop(self) -> bool:
        return True

    def get_default_dirs(self) -> dict:
        exp = ROOT / "local_data" / "exports"
        exp.mkdir(parents=True, exist_ok=True)
        return {"app_dir": str(ROOT), "exports_dir": str(exp), "last_dir": self._last_dir}

    def save_file_b64(self, filename: str, data_b64: str) -> dict:
        """Show native Windows Save-As dialog, write bytes, and return the exact saved path."""
        import base64
        import webview

        if not self._window:
            return {"ok": False, "error": "window_not_ready"}
        save_mode = getattr(getattr(webview, "FileDialog", None), "SAVE", getattr(webview, "SAVE_DIALOG", 30))
        res = self._window.create_file_dialog(save_mode, directory=self._last_dir, save_filename=filename)
        if not res:
            return {"ok": False, "cancelled": True}
        target = Path(res[0] if isinstance(res, (list, tuple)) else str(res))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(base64.b64decode(data_b64))
        self._last_dir = str(target.parent)
        return {"ok": True, "path": str(target), "filename": target.name}

    def pick_workspace_folder(self) -> dict:
        """Show native Windows Folder dialog to open an entire LaTeX project workspace."""
        import webview

        if not self._window:
            return {"ok": False, "error": "window_not_ready"}
        folder_mode = getattr(getattr(webview, "FileDialog", None), "FOLDER", getattr(webview, "FOLDER_DIALOG", 20))
        res = self._window.create_file_dialog(folder_mode, directory=self._last_dir)
        if not res:
            return {"ok": False, "cancelled": True}
        folder = Path(res[0] if isinstance(res, (list, tuple)) else str(res))
        self._last_dir = str(folder)
        return {"ok": True, "path": str(folder), "name": folder.name}

    def pick_import_file(self) -> dict:
        """Show native Windows Open-File dialog for manuscripts and return exact full path + bytes."""
        import base64
        import webview

        if not self._window:
            return {"ok": False, "error": "window_not_ready"}
        open_mode = getattr(getattr(webview, "FileDialog", None), "OPEN", getattr(webview, "OPEN_DIALOG", 10))
        ft = ("论文文档 (*.docx;*.tex;*.pdf;*.md;*.txt)", "所有文件 (*.*)")
        res = self._window.create_file_dialog(open_mode, directory=self._last_dir, allow_multiple=False, file_types=ft)
        if not res:
            return {"ok": False, "cancelled": True}
        src = Path(res[0] if isinstance(res, (list, tuple)) else str(res))
        self._last_dir = str(src.parent)
        return {
            "ok": True,
            "path": str(src),
            "filename": src.name,
            "b64": base64.b64encode(src.read_bytes()).decode("ascii"),
        }

    def open_file_location(self, path: str) -> dict:
        """Reveal file or folder in Windows File Explorer."""
        import subprocess

        p = Path(path)
        if os.name == "nt":
            if p.is_file():
                subprocess.Popen(["explorer", "/select,", str(p)])
            elif p.exists():
                subprocess.Popen(["explorer", str(p)])
            else:
                fallback = ROOT / "local_data" / "exports"
                fallback.mkdir(parents=True, exist_ok=True)
                subprocess.Popen(["explorer", str(fallback)])
            return {"ok": True}
        return {"ok": False}

    def minimize(self) -> None:
        if self._window:
            self._window.minimize()

    def toggle_maximize(self) -> bool:
        if not self._window:
            return False
        if self._maximized:
            self._window.restore()
            self._maximized = False
        else:
            self._window.maximize()
            self._maximized = True
        return self._maximized

    def close(self) -> None:
        if self._window:
            self._window.destroy()


def main() -> None:
    try:
        import uvicorn
        from backend.main import app

        server_only = "--server" in sys.argv or "--no-open" in sys.argv
        port = int(os.environ.get("PAPER_HARNESS_PORT", "8765")) if server_only else _pick_port(8765)
        url = f"http://127.0.0.1:{port}"

        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None)
        server = uvicorn.Server(config)

        if server_only:
            server.run()
            return

        threading.Thread(target=server.run, daemon=True).start()
        if not _wait_ready(url):
            raise RuntimeError("PaperHarness 本地引擎启动超时，请检查端口占用后重试。")

        import json
        import webview
        from webview.dom import DOMEventHandler

        bridge = DesktopWindowBridge()
        win = webview.create_window(
            title="PaperHarness",
            url=url,
            js_api=bridge,
            width=1480,
            height=920,
            min_size=(1060, 680),
            resizable=True,
            frameless=True,
            easy_drag=False,
            text_select=True,
            shadow=True,
            background_color="#F6F4EF",
        )
        bridge.bind(win)

        def _attach_native_drop() -> None:
            def _on_drop(e: dict) -> None:
                try:
                    files = (e.get("dataTransfer") or {}).get("files") or []
                    for f in files:
                        fp = f.get("pywebviewFullPath")
                        if fp and Path(fp).is_dir():
                            bridge._last_dir = fp
                            win.evaluate_js(
                                f"window.dispatchEvent(new CustomEvent('ph:native-folder-drop', {{detail: {json.dumps(fp)}}}));"
                            )
                            return
                except Exception:
                    pass

            try:
                win.dom.document.events.drop += DOMEventHandler(_on_drop, False, False)
            except Exception:
                pass

        win.events.loaded += _attach_native_drop
        try:
            webview.start(gui="edgechromium")
        except Exception:
            webview.start()
        server.should_exit = True
    except Exception:
        err = traceback.format_exc()
        log_path = ROOT / "local_data" / "startup_error.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(err, encoding="utf-8")
        if IS_FROZEN:
            _alert_error(
                "PaperHarness 桌面窗口启动失败，请确认 Windows 已安装 Microsoft Edge WebView2 运行时。\n\n"
                f"详细日志：{log_path}"
            )
        raise


if __name__ == "__main__":
    main()
