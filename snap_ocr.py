"""
OCR 模式 — Windows OCR 提取游戏文字 → description.txt
纯文字OCR，免费零延迟。适合文字RPG。

Usage: python snap_ocr.py          # 截一张OCR
       python snap_ocr.py --auto   # 每60秒自动
       python snap_ocr.py --once   # 截一张退出
"""

import time
import sys
from pathlib import Path
import numpy as np
import json
from screen_capture import capture_region, find_game_window as find_configured_window
from game_knowledge import correct_ocr_text

CONFIG_DIR = Path(__file__).parent
DESC_FILE = CONFIG_DIR / "description.txt"


def capture_screen(region=None):
    if region is None:
        raise RuntimeError("未找到目标游戏窗口；为保护隐私，已跳过截图")
    image = capture_region(region)
    return np.array(image), image


def ocr_text(image_array, reader):
    """用 easyocr 提取中文+英文文字"""
    results = reader.readtext(image_array, detail=0)
    return "\n".join(results) if results else ""


def format_output(raw_text, config=None):
    """把 OCR 原始输出整理成可读格式"""
    corrections = []
    if config:
        raw_text, corrections = correct_ocr_text(raw_text, config)
    lines = raw_text.strip().split("\n")
    # 去重去空白
    seen = set()
    clean = []
    for line in lines:
        line = line.strip()
        if line and line not in seen and len(line) > 1:
            seen.add(line)
            clean.append(line)

    if not clean:
        return "（OCR 未识别到文字）"

    out = "【OCR 提取文字】\n"
    out += "\n".join(clean)
    if corrections:
        out += "\n\n【词库校对】\n"
        out += "\n".join(f"{item['from']} → {item['to']}" for item in corrections[:10])
    out += "\n\n（写完弹幕到 danmaku.txt）"
    return out


def main():
    print("🔍 Snap OCR 启动中...")
    try:
        cfg = json.loads((CONFIG_DIR / "config.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"   ❌ 无法读取 config.json: {exc}")
        return
    title = str(cfg.get("game_window_title", "")).strip()
    if not title:
        print("   ❌ 请先设置 game_window_title；未截图，以免捕获桌面隐私")
        return

    # 加载 easyocr（第一次会下载模型）
    try:
        import easyocr
        print("   加载 OCR 模型（首次较慢）...")
        reader = easyocr.Reader(['ch_sim', 'en'], gpu=False, verbose=False)
        print("   ✅ OCR 就绪\n")
    except Exception as e:
        print(f"   ❌ OCR 加载失败: {e}")
        return

    auto = "--auto" in sys.argv
    region = find_configured_window(title)
    if region is None:
        print("   ❌ 未找到目标游戏窗口；已跳过截图")
        return
    if region:
        print(f"🎯 窗口: {region['width']}x{region['height']}\n")

    if not auto:
        # 单次模式
        print("📸 截图中...")
        arr, raw = capture_screen(region)
        print("🔍 OCR 识别中...")
        text = ocr_text(arr, reader)
        output = format_output(text, cfg)
        DESC_FILE.write_text(output, encoding='utf-8')
        print(f"✅ → {DESC_FILE}")
        print(f"\n{output[:500]}")
        return

    # 自动模式
    INTERVAL = 60
    print(f"🔄 自动模式（每{INTERVAL}秒）→ {DESC_FILE}")
    print("   Ctrl+C 退出\n")

    last_text = ""
    frame = 0

    try:
        while True:
            frame += 1
            region = find_configured_window(title)
            if region is None:
                print("⚠️ 未找到目标游戏窗口；跳过截图")
                time.sleep(INTERVAL)
                continue
            arr, raw = capture_screen(region)
            text = ocr_text(arr, reader)
            output = format_output(text, cfg)

            if text == last_text:
                time.sleep(INTERVAL)
                continue

            last_text = text
            DESC_FILE.write_text(output, encoding='utf-8')
            print(f"📸 #{frame} OCR 完成 ({len(text)} 字)")
            time.sleep(INTERVAL)

    except KeyboardInterrupt:
        print("👋 Snap OCR 已停止")


if __name__ == "__main__":
    main()
