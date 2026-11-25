"""Build standalone Windows portable PaperHarness.exe via PyInstaller."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRONTEND_DIST = ROOT / "frontend" / "dist"
_SKILL_CANDIDATES = [
    ROOT / "skills" / "academic-polish",
    ROOT.parent / "academic-polish-plugin" / "skills" / "academic-polish",
]
SKILL_DIR = next((p for p in _SKILL_CANDIDATES if (p / "SKILL.md").exists()), _SKILL_CANDIDATES[0])
RELEASE_DIR = ROOT / "release"
BUILD_WORK = ROOT / "build_pyi"


def main() -> None:
    assert (FRONTEND_DIST / "index.html").exists(), "Run `npm run build` in frontend/ first!"
    assert (SKILL_DIR / "SKILL.md").exists(), f"Missing skill dir: {SKILL_DIR}"

    # Clean previous build dirs
    for d in (RELEASE_DIR, BUILD_WORK):
        if d.exists():
            shutil.rmtree(d)

    # Copy skill cleanly without __pycache__ into staging inside build_pyi
    staged_skill = BUILD_WORK / "skills_clean" / "academic-polish"
    shutil.copytree(SKILL_DIR, staged_skill, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--name",
        "PaperHarness",
        "--distpath",
        str(RELEASE_DIR),
        "--workpath",
        str(BUILD_WORK / "work"),
        "--specpath",
        str(BUILD_WORK),
        # Native desktop window + WebView2 + .NET bridge
        "--collect-all",
        "webview",
        "--collect-all",
        "pythonnet",
        "--collect-all",
        "clr_loader",
        # Document, PPTX, PDF & plotting data templates / native binaries
        "--collect-data",
        "docx",
        "--collect-data",
        "pptx",
        "--collect-data",
        "matplotlib",
        "--collect-all",
        "pymupdf",
        "--collect-submodules",
        "backend",
        # Uvicorn & FastAPI dynamic imports
        "--hidden-import",
        "uvicorn.logging",
        "--hidden-import",
        "uvicorn.loops.auto",
        "--hidden-import",
        "uvicorn.loops.asyncio",
        "--hidden-import",
        "uvicorn.protocols.http.auto",
        "--hidden-import",
        "uvicorn.protocols.http.h11_impl",
        "--hidden-import",
        "uvicorn.protocols.websockets.auto",
        "--hidden-import",
        "uvicorn.lifespan.on",
        "--hidden-import",
        "multipart",
        "--hidden-import",
        "python_multipart",
        "--hidden-import",
        "matplotlib.backends.backend_agg",
        "--hidden-import",
        "matplotlib.backends.backend_svg",
        "--hidden-import",
        "matplotlib.backends.backend_pdf",
        # Exclude heavy unused conda packages to keep portable release slim
        "--exclude-module",
        "tkinter",
        "--exclude-module",
        "PyQt5",
        "--exclude-module",
        "PyQt6",
        "--exclude-module",
        "PySide6",
        "--exclude-module",
        "IPython",
        "--exclude-module",
        "jupyter",
        "--exclude-module",
        "notebook",
        "--exclude-module",
        "pytest",
        "--exclude-module",
        "torch",
        "--exclude-module",
        "torchvision",
        "--exclude-module",
        "scipy",
        "--exclude-module",
        "pandas",
        "--exclude-module",
        "sklearn",
        "--exclude-module",
        "cv2",
        # Bundled static SPA & 3,000-paper academic skill corpus
        "--add-data",
        f"{FRONTEND_DIST};frontend/dist",
        "--add-data",
        f"{staged_skill};skills/academic-polish",
        str(ROOT / "launch_desktop.py"),
    ]

    print("[Build] Launching PyInstaller...")
    subprocess.run(cmd, check=True)

    app_out = RELEASE_DIR / "PaperHarness"
    # Drop a crisp usage note right next to PaperHarness.exe
    (app_out / "使用说明.txt").write_text(
        "PaperHarness · 学术论文写作与科研绘图工作台（免安装便携版）\n"
        "============================================================\n\n"
        "1. 直接双击 PaperHarness.exe 即可打开独立桌面窗口（无需安装 Python 或任何环境）。\n"
        "2. 打开后点击右上角「配置 API」，填入任意大模型 API Key 并点击「用 Key 拉取模型」即可使用。\n"
        "3. 你的 API Key 与自建语料包仅保存在本文件夹内的 local_data/ 目录中；\n"
        "   如需继续转发给其他同学，请先删除 local_data/ 目录以免泄露自己的密钥。\n"
        "4. 若个别旧版 Windows 未安装 Edge WebView2，程序会自动改用系统默认浏览器打开，功能完全一致。\n",
        encoding="utf-8",
    )

    shutil.rmtree(BUILD_WORK, ignore_errors=True)
    print(f"[Build] Done! Executable ready at: {app_out / 'PaperHarness.exe'}")


if __name__ == "__main__":
    main()
