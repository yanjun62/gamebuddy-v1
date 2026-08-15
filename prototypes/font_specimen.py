"""Render a font-only comparison over the illustrated Mucha background."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
FONT_ROOT = ASSETS / "fonts"
OUTPUT = ASSETS / "mucha-font-specimen-v1.png"

INK = "#3A2A20"
GOLD = "#9E742F"
TEAL = "#315F5A"
ROSE = "#99585E"
PAPER_ALPHA = (247, 237, 211, 232)


def centered(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str,
             font: ImageFont.FreeTypeFont, fill: str) -> None:
    box = draw.textbbox((0, 0), text, font=font)
    width = box[2] - box[0]
    draw.text((xy[0] - width / 2, xy[1]), text, font=font, fill=fill)


def main() -> None:
    image = Image.open(ASSETS / "mucha-frame-v1.png").convert("RGBA")
    draw = ImageDraw.Draw(image)
    wenkai_path = FONT_ROOT / "lxgw-wenkai" / "LXGWWenKai-Regular.ttf"
    wenkai_small = ImageFont.truetype(str(wenkai_path), 25)
    wenkai_body = ImageFont.truetype(str(wenkai_path), 26)
    wenkai_heading = ImageFont.truetype(str(wenkai_path), 27)

    draw.rounded_rectangle((238, 394, 786, 449), radius=24,
                           fill=PAPER_ALPHA, outline=GOLD, width=2)
    centered(draw, (512, 402), "英文花体样张 · 中文统一使用霞鹜文楷",
             wenkai_heading, TEAL)

    samples = [
        ("A · Great Vibes", FONT_ROOT / "great-vibes" / "GreatVibes-Regular.ttf", 458),
        ("B · Parisienne", FONT_ROOT / "parisienne" / "Parisienne-Regular.ttf", 758),
        ("C · Allura", FONT_ROOT / "allura" / "Allura-Regular.ttf", 1058),
    ]

    for label, path, y in samples:
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        odraw.rounded_rectangle((168, y, 856, y + 248), radius=34,
                                fill=PAPER_ALPHA, outline=(158, 116, 47, 235), width=3)
        odraw.line((205, y + 51, 819, y + 51), fill=(204, 170, 98, 210), width=2)
        image.alpha_composite(overlay)
        draw = ImageDraw.Draw(image)

        centered(draw, (512, y + 13), label, wenkai_small, GOLD)
        title_font = ImageFont.truetype(str(path), 92)
        centered(draw, (512, y + 55), "Game Buddy", title_font, INK)
        body_color = ROSE if label.startswith("B") else TEAL
        centered(draw, (512, y + 164), "右边的奖励实在很诱人。", wenkai_body, body_color)
        centered(draw, (512, y + 199), "若今夜求稳，便选择左边吧。", wenkai_body, body_color)

    image.convert("RGB").save(OUTPUT, quality=95)
    print(OUTPUT)


if __name__ == "__main__":
    main()
