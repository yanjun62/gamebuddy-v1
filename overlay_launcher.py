"""Launch the GameBuddy overlay with a reliable Tk runtime on Windows."""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent


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


def main() -> int:
    configured = configure_tk()
    if "--check" in sys.argv:
        if configured:
            print(f"TCL_LIBRARY={configured[0]}")
            print(f"TK_LIBRARY={configured[1]}")
            return 0
        print("未找到可用的 Tcl/Tk 运行库", file=sys.stderr)
        return 1

    os.chdir(PROJECT_DIR)
    sys.path.insert(0, str(PROJECT_DIR))
    runpy.run_path(str(PROJECT_DIR / "danmaku_overlay.py"), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
