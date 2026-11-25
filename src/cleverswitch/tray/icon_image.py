"""CleverSwitch's icon: a keyboard, a mouse in front of it and the switch arrows between them.

Drawn at runtime with Pillow, so the build ships no image files. The build scripts call
``save_app_icons`` to turn the same drawing into the Windows .ico and the macOS .icns.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

_DESIGN = 256  # coordinates below are on a 256 x 256 canvas
_SUPERSAMPLE = 4
_KEYBOARD = (14, 58, 160, 88)  # x, y, width, height
_MOUSE = (178, 104, 62, 98)
_ARROWS = (166, 146, 30)  # centre x, centre y, half size
_ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


class _Canvas:
    def __init__(self, size: int) -> None:
        self.k = size * _SUPERSAMPLE / _DESIGN
        side = size * _SUPERSAMPLE
        self.image = Image.new("RGBA", (side, side), (0, 0, 0, 0))

    def box(self, x0, y0, x1, y1):
        return [x0 * self.k, y0 * self.k, x1 * self.k, y1 * self.k]

    def draw(self) -> ImageDraw.ImageDraw:
        return ImageDraw.Draw(self.image)

    def shadow(self, box, radius, offset=(4, 6), blur=6, alpha=90, ellipse=False) -> None:
        layer = Image.new("RGBA", self.image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        moved = self.box(box[0] + offset[0], box[1] + offset[1], box[2] + offset[0], box[3] + offset[1])
        if ellipse:
            draw.ellipse(moved, fill=(0, 0, 0, alpha))
        else:
            draw.rounded_rectangle(moved, radius=radius * self.k, fill=(0, 0, 0, alpha))
        self.image.alpha_composite(layer.filter(ImageFilter.GaussianBlur(blur * self.k)))

    def gradient_fill(self, box, top, bottom, radius=None) -> None:
        x0, y0, x1, y1 = (int(v) for v in self.box(*box))
        width, height = max(1, x1 - x0), max(1, y1 - y0)
        fill = Image.new("RGBA", (width, height))
        draw = ImageDraw.Draw(fill)
        for y in range(height):
            t = y / height
            draw.line(
                [(0, y), (width, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)) + (255,)
            )
        mask = Image.new("L", (width, height), 0)
        if radius is None:
            ImageDraw.Draw(mask).ellipse([0, 0, width - 1, height - 1], fill=255)
        else:
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, width - 1, height - 1], radius=radius * self.k, fill=255)
        self.image.paste(fill, (x0, y0), mask)


def _keyboard(c: _Canvas) -> None:
    x, y, w, h = _KEYBOARD
    c.shadow((x, y, x + w, y + h), 10)
    c.gradient_fill((x, y, x + w, y + h), (250, 250, 250), (205, 208, 212), radius=10)
    draw = c.draw()
    draw.rounded_rectangle(
        c.box(x, y, x + w, y + h), radius=10 * c.k, outline=(150, 155, 160), width=max(1, round(2 * c.k))
    )
    cols, rows, pad = 9, 3, 9
    key_w = (w - 2 * pad) / cols
    key_h = (h - 2 * pad - 10) / (rows + 1)
    keys = [(x + pad + col * key_w, y + pad + row * key_h, 1) for row in range(rows) for col in range(cols)]
    keys.append((x + pad + 2 * key_w, y + pad + rows * key_h, 5))  # space bar
    for kx, ky, span in keys:
        draw.rounded_rectangle(
            c.box(kx + 1.5, ky + 1.5, kx + span * key_w - 1.5, ky + key_h - 1.5),
            radius=2.5 * c.k,
            fill=(232, 234, 237),
            outline=(170, 174, 180),
            width=max(1, round(c.k)),
        )


def _mouse(c: _Canvas) -> None:
    x, y, w, h = _MOUSE
    c.shadow((x, y, x + w, y + h), w // 2, offset=(5, 7), blur=7, alpha=110, ellipse=True)
    c.gradient_fill((x, y, x + w, y + h), (255, 255, 255), (190, 194, 200))
    draw = c.draw()
    draw.ellipse(c.box(x, y, x + w, y + h), outline=(140, 145, 150), width=max(1, round(2 * c.k)))
    split = y + h * 0.38
    draw.line(c.box(x + w / 2, y + 3, x + w / 2, split)[:4], fill=(150, 155, 160), width=max(1, round(2 * c.k)))
    draw.line(c.box(x + 5, split, x + w - 5, split)[:4], fill=(175, 180, 185), width=max(1, round(c.k)))
    draw.rounded_rectangle(
        c.box(x + w / 2 - 2.5, y + h * 0.12, x + w / 2 + 2.5, y + h * 0.27), radius=2.5 * c.k, fill=(160, 165, 170)
    )


def _arrow_shapes(c: _Canvas, draw: ImageDraw.ImageDraw, color) -> None:
    cx, cy, s = _ARROWS
    width = max(1, round(max(2, s * 0.16) * c.k))
    for sign, dy in ((1, -s * 0.32), (-1, s * 0.32)):
        y0 = cy + dy
        start, tip = cx - s * 0.8 * sign, cx + s * 0.8 * sign
        draw.line(c.box(start, y0, tip - sign * s * 0.3, y0)[:4], fill=color, width=width)
        draw.polygon(
            [
                (tip * c.k, y0 * c.k),
                ((tip - sign * s * 0.45) * c.k, (y0 - s * 0.3) * c.k),
                ((tip - sign * s * 0.45) * c.k, (y0 + s * 0.3) * c.k),
            ],
            fill=color,
        )


def _arrows(c: _Canvas) -> None:
    # A soft white edge keeps the arrows readable where they cross the keyboard and the mouse.
    layer = Image.new("RGBA", c.image.size, (0, 0, 0, 0))
    _arrow_shapes(c, ImageDraw.Draw(layer), (255, 255, 255, 255))
    spread = max(3, int(5 * c.k) | 1)
    edge = layer.split()[3].filter(ImageFilter.MaxFilter(spread)).filter(ImageFilter.GaussianBlur(1.5 * c.k))
    halo = Image.new("RGBA", c.image.size, (255, 255, 255, 0))
    halo.putalpha(edge.point(lambda v: int(v * 0.9)))
    c.image.alpha_composite(halo)
    _arrow_shapes(c, c.draw(), (80, 86, 94, 255))


def app_icon(size: int = 256) -> Image.Image:
    """The full-colour icon (white/grey, slightly 3D) at ``size`` x ``size`` pixels."""
    c = _Canvas(size)
    _keyboard(c)
    _mouse(c)
    _arrows(c)
    return c.image.resize((size, size), Image.LANCZOS)


def windows_icon(active: bool) -> Image.Image:
    """The tray icon; greyed out and faded while the mouse button switch is off."""
    image = app_icon(64)
    if active:
        return image
    faded = ImageEnhance.Color(image).enhance(0.0)
    faded.putalpha(faded.split()[3].point(lambda v: v * 55 // 100))
    return faded


def mac_template(active: bool) -> Image.Image:
    """The same motif as black outlines on transparent; macOS recolours a template image."""
    c = _Canvas(64)
    draw = c.draw()
    alpha = 255 if active else 110
    ink = (0, 0, 0, alpha)
    line = max(1, round(9 * c.k))
    x, y, w, h = _KEYBOARD
    draw.rounded_rectangle(c.box(x, y, x + w, y + h), radius=14 * c.k, outline=ink, width=line)
    for row in range(2):
        for col in range(5):
            kx, ky = x + 22 + col * 26, y + 20 + row * 22
            draw.rectangle(c.box(kx, ky, kx + 12, ky + 10), fill=ink)
    draw.rectangle(c.box(x + 48, y + 64, x + 112, y + 74), fill=ink)
    mx, my, mw, mh = _MOUSE
    erase = Image.new("L", c.image.size, 0)
    ImageDraw.Draw(erase).ellipse(c.box(mx - 10, my - 10, mx + mw + 10, my + mh + 10), fill=255)
    c.image.paste((0, 0, 0, 0), (0, 0), erase)  # gap between the keyboard and the mouse in front of it
    draw.ellipse(c.box(mx, my, mx + mw, my + mh), outline=ink, width=line)
    draw.line(c.box(mx + mw / 2, my + 6, mx + mw / 2, my + mh * 0.38)[:4], fill=ink, width=line)
    _arrow_shapes(c, draw, ink)
    if not active:
        draw.line(c.box(20, 230, 236, 26)[:4], fill=(0, 0, 0, 255), width=round(14 * c.k))
    return c.image.resize((64, 64), Image.LANCZOS)


def save_app_icons(directory: Path) -> None:
    """Write cleverswitch.ico and cleverswitch.icns for the build scripts."""
    directory.mkdir(parents=True, exist_ok=True)
    big = app_icon(1024)
    big.save(directory / "cleverswitch.ico", sizes=_ICO_SIZES)
    big.save(directory / "cleverswitch.icns")


if __name__ == "__main__":
    save_app_icons(Path(sys.argv[1] if len(sys.argv) > 1 else "build/icons"))
