"""The tray icon, drawn at runtime so the build ships no image files."""

from __future__ import annotations

from PIL import Image, ImageDraw

_SIZE = 64


def _arrows(draw: ImageDraw.ImageDraw, color, width: int) -> None:
    # ⇄: an arrow to the right above an arrow to the left
    for y, left_to_right in ((22, True), (42, False)):
        start, end = (12, 52) if left_to_right else (52, 12)
        draw.line((start, y, end, y), fill=color, width=width)
        head = 10 if left_to_right else -10
        draw.polygon([(end + head // 5, y), (end - head, y - 9), (end - head, y + 9)], fill=color)


def mac_template(active: bool) -> Image.Image:
    """Black on transparent; macOS recolours a template image for light and dark menu bars."""
    image = Image.new("RGBA", (_SIZE, _SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    alpha = 255 if active else 110
    _arrows(draw, (0, 0, 0, alpha), 6)
    if not active:
        draw.line((10, 54, 54, 10), fill=(0, 0, 0, 255), width=5)
    return image


def windows_icon(active: bool) -> Image.Image:
    """A coloured tile that reads on light and dark taskbars."""
    image = Image.new("RGBA", (_SIZE, _SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    tile = (0, 120, 212, 255) if active else (120, 120, 120, 255)
    draw.rounded_rectangle((2, 2, _SIZE - 3, _SIZE - 3), radius=12, fill=tile)
    _arrows(draw, (255, 255, 255, 255), 6)
    return image
