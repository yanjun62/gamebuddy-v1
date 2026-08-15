#!/usr/bin/env python3
"""把 overlay_themes.py 里的主题解析成 JSON，交给 macOS 的 Swift 前端。

Swift 那边不重写各套配色——配色只有一处定义（overlay_themes.py），
Tk 前端和 AppKit 前端读同一份，改主题不用改两遍。

用法：
    theme_bridge.py list                 列出全部主题
    theme_bridge.py resolve <theme_id>   解析单个主题的全部颜色
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, fields
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from overlay_themes import get_theme, theme_choices
except Exception as exc:  # pragma: no cover - 让 Swift 侧拿到可读的错误
    print(json.dumps({"error": f"无法加载 overlay_themes: {exc}"}, ensure_ascii=False))
    raise SystemExit(1)


def _dump(theme) -> dict:
    data = {}
    for field in fields(theme):
        value = getattr(theme, field.name)
        # gradient 是三元组，转成数组
        data[field.name] = list(value) if isinstance(value, tuple) else value
    return data


def main() -> int:
    argv = sys.argv[1:]
    action = argv[0] if argv else "list"

    if action == "list":
        payload = [
            {"id": t.id, "display_name": t.display_name, "description": t.description, "badge": t.badge}
            for t in theme_choices()
        ]
        print(json.dumps({"themes": payload}, ensure_ascii=False))
        return 0

    if action == "resolve":
        theme_id = argv[1] if len(argv) > 1 else None
        print(json.dumps({"theme": _dump(get_theme(theme_id))}, ensure_ascii=False))
        return 0

    print(json.dumps({"error": f"未知动作 {action}"}, ensure_ascii=False))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
