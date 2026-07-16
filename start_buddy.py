"""
Game Buddy 一键启动 — 同时拉起 截图识图 + 弹幕悬浮窗

Usage:
    python start_buddy.py          # capture_daemon.py（视觉模型识图）
    python start_buddy.py --ocr    # snap_ocr.py --auto（Windows OCR，免费）

关闭方式：右键关闭悬浮窗，截图脚本会一起退出。
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent


def main():
    if "--ocr" in sys.argv[1:]:
        capture_cmd = [sys.executable, str(HERE / "snap_ocr.py"), "--auto"]
        capture_name = "snap_ocr.py (OCR模式)"
    else:
        capture_cmd = [sys.executable, str(HERE / "capture_daemon.py")]
        capture_name = "capture_daemon.py (识图模式)"

    print(f"🎮 Game Buddy 一键启动")
    print(f"   截图端: {capture_name}")
    print(f"   悬浮窗: danmaku_overlay.py")
    print(f"   （右键关闭悬浮窗 = 全部退出）\n")

    daemon = subprocess.Popen(capture_cmd)

    import danmaku_overlay
    try:
        danmaku_overlay.main()  # tkinter 主循环，窗口关闭后返回
    except KeyboardInterrupt:
        pass
    finally:
        if daemon.poll() is None:
            daemon.terminate()
            try:
                daemon.wait(timeout=5)
            except subprocess.TimeoutExpired:
                daemon.kill()
        print("👋 Game Buddy 已全部停止")


if __name__ == "__main__":
    main()
