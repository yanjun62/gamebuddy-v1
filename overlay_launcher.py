"""Launch the GameBuddy overlay with a reliable Tk runtime on Windows."""

from __future__ import annotations

import os
import runpy
import subprocess
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent


def relaunch_in_project_venv() -> bool:
    """Use the project runtime on Windows so optional voice packages stay available."""
    if sys.platform != "win32":
        return False
    scripts_dir = PROJECT_DIR / ".venv" / "Scripts"
    executable_name = "pythonw.exe" if Path(sys.executable).name.casefold() == "pythonw.exe" else "python.exe"
    candidate = scripts_dir / executable_name
    site_packages = PROJECT_DIR / ".venv" / "Lib" / "site-packages"
    voice_ready = (site_packages / "sounddevice.py").is_file() and (site_packages / "faster_whisper").is_dir()
    try:
        already_using_candidate = Path(sys.executable).resolve() == candidate.resolve()
    except OSError:
        already_using_candidate = False
    if already_using_candidate or not candidate.is_file() or not voice_ready:
        return False
    command = [str(candidate), str(Path(__file__).resolve()), *sys.argv[1:]]
    try:
        if "--check" in sys.argv:
            raise SystemExit(subprocess.run(command, cwd=PROJECT_DIR, check=False).returncode)
        subprocess.Popen(command, cwd=PROJECT_DIR)
        return True
    except OSError as exc:
        print(f"项目语音运行时无法启动，将继续使用当前 Python：{exc}", file=sys.stderr)
        return False


def configure_tk() -> tuple[Path, Path] | None:
    """Point tkinter at Tcl/Tk bundled with the Python base runtime."""
    roots = [Path(sys.base_prefix), Path(sys.prefix), Path(sys.executable).resolve().parent]
    for root in dict.fromkeys(roots):
        tcl_root = root / "tcl"
        tcl_library = tcl_root / "tcl8.6"
        tk_library = tcl_root / "tk8.6"
        if tcl_library.is_dir() and tk_library.is_dir():
            os.environ["TCL_LIBRARY"] = str(tcl_library)
            os.environ["TK_LIBRARY"] = str(tk_library)
            return tcl_library, tk_library
    return None


def system_tk_version() -> str | None:
    """Check the interpreter-provided Tk runtime without requiring a visible window."""
    try:
        import tkinter as tk

        interpreter = tk.Tcl()
        return str(interpreter.eval("info patchlevel"))
    except Exception:
        return None


def launch_macos_overlay(*, check_only: bool = False) -> int:
    source = PROJECT_DIR / "macos" / "GameBuddyMac.swift"
    info_plist = PROJECT_DIR / "macos" / "Info.plist"
    build_dir = PROJECT_DIR / ".gamebuddy-build"
    app_dir = build_dir / "GameBuddy.app"
    contents_dir = app_dir / "Contents"
    binary = contents_dir / "MacOS" / "GameBuddy"
    built_plist = contents_dir / "Info.plist"
    swiftc = Path("/usr/bin/xcrun")
    if not source.exists() or not info_plist.exists() or not swiftc.exists():
        print("缺少 macOS 原生气泡源码、Info.plist 或 Swift 工具链", file=sys.stderr)
        return 1
    if check_only:
        print(f"macOS 原生 AppKit 前端：{source}")
        print("Swift 工具链与 App Bundle 配置可用")
        return 0
    binary.parent.mkdir(parents=True, exist_ok=True)
    needs_build = not binary.exists() or binary.stat().st_mtime_ns < source.stat().st_mtime_ns
    if needs_build:
        command = [
            str(swiftc), "swiftc", "-swift-version", "5", "-parse-as-library",
            str(source), "-o", str(binary),
        ]
        try:
            subprocess.run(command, cwd=PROJECT_DIR, check=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            print(f"macOS 原生气泡编译失败: {exc}", file=sys.stderr)
            return 1
    try:
        built_plist.write_bytes(info_plist.read_bytes())
    except OSError as exc:
        print(f"macOS App Bundle 配置失败: {exc}", file=sys.stderr)
        return 1
    os.execv("/usr/bin/open", ["open", "-n", str(app_dir), "--args", str(PROJECT_DIR)])
    return 0


def main() -> int:
    if relaunch_in_project_venv():
        return 0
    if sys.platform == "darwin":
        return launch_macos_overlay(check_only="--check" in sys.argv)

    configured = configure_tk()
    if "--check" in sys.argv:
        if configured:
            print(f"TCL_LIBRARY={configured[0]}")
            print(f"TK_LIBRARY={configured[1]}")
            return 0
        version = system_tk_version()
        if version:
            print(f"使用解释器自带 Tkinter / Tcl {version}")
            return 0
        print("未找到可用的 Tcl/Tk 运行库", file=sys.stderr)
        return 1

    os.chdir(PROJECT_DIR)
    sys.path.insert(0, str(PROJECT_DIR))
    runpy.run_path(str(PROJECT_DIR / "danmaku_overlay.py"), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
