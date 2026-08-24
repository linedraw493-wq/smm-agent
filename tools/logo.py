"""
Логотип m4ksi — один рендерер, чтобы значок и wordmark не расходились.

Палитра blue-white (Нурс), тёплый белый вместо чистого — решение
2026-08-24 (см. alya-vault/craft/design-system.md, вопрос цвета).
Шрифт Inter ExtraBold, по-символьно, иначе разрядки не будет (та же
причина, что и в tools/plate.py).

Usage:
    python tools/logo.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONT_PATH = ROOT / "assets" / "fonts" / "Inter-ExtraBold.ttf"
OUT_DIR = ROOT / "assets" / "logo"

BG = "#0a1929"
TEXT = "#f7f1e9"      # тёплый кремовый, не чистый белый — решение по цвету 2026-08-24
ACCENT = "#74a6ff"    # accent_still — статичный ассет, не видео

WORD = "m4ksi"
ACCENT_CHAR = "4"

SCALE = 4  # рендерим в 4x и уменьшаем — сглаживание без внешних либ


def load_font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_PATH), size)


def char_colors(word: str) -> list[str]:
    return [ACCENT if c == ACCENT_CHAR else TEXT for c in word]


def _char_ink(draw: ImageDraw.ImageDraw, ch: str, font: ImageFont.FreeTypeFont):
    """bbox символа при отрисовке из (0, 0) с anchor='ls' — левый/правый/верх/низ чернил."""
    return draw.textbbox((0, 0), ch, font=font, anchor="ls")


def layout_word(draw: ImageDraw.ImageDraw, word: str, font: ImageFont.FreeTypeFont, gap: float):
    """
    Оптическая раскладка: расстояние между КРАЯМИ ЧЕРНИЛ соседних символов
    постоянно (gap), а не расстояние между опорными точками курсора.
    Раньше был равный advance-трекинг — он давал разный видимый зазор
    там, где у соседних глифов разная боковая кромка (m|4 против 4|k):
    подтверждено замером на первой версии, зазор m-4 был шире остальных
    почти вдвое на глаз. Правит этот вариант.
    """
    positions = []
    cursor_ink_right = None
    x = 0.0
    tops, bottoms = [], []
    for ch in word:
        left, top, right, bottom = _char_ink(draw, ch, font)
        tops.append(top)
        bottoms.append(bottom)
        if cursor_ink_right is None:
            x = -left
        else:
            x = cursor_ink_right - left + gap
        positions.append((ch, x))
        cursor_ink_right = x + right
    return positions, cursor_ink_right, min(tops), max(bottoms)


def draw_word(draw: ImageDraw.ImageDraw, x0: float, y: float, word: str,
               font: ImageFont.FreeTypeFont, gap: float) -> None:
    colors = char_colors(word)
    positions, _, _, _ = layout_word(draw, word, font, gap)
    for (ch, cx), col in zip(positions, colors):
        draw.text((x0 + cx, y), ch, font=font, fill=col, anchor="ls")


def _measure(draw, font, gap):
    _, ww, cap_top, baseline_bottom = layout_word(draw, WORD, font, gap)
    text_h = baseline_bottom - cap_top
    return ww, cap_top, text_h


def render_fixed(canvas_w: int, canvas_h: int, font_ratio: float, gap_ratio: float,
                  out_path: Path) -> None:
    """Слово внутри заданного холста — для аватара, где холст диктует круг."""
    w, h = canvas_w * SCALE, canvas_h * SCALE
    img = Image.new("RGB", (w, h), BG)
    draw = ImageDraw.Draw(img)

    font = load_font(int(h * font_ratio))
    gap = gap_ratio * font.size
    ww, cap_top, text_h = _measure(draw, font, gap)

    x0 = (w - ww) / 2
    baseline_y = (h - text_h) / 2 - cap_top
    draw_word(draw, x0, baseline_y, WORD, font, gap)

    _save(img, canvas_w, canvas_h, out_path)
    print(f"{out_path.name}: {canvas_w}x{canvas_h}, слово {ww / SCALE:.0f}px из {canvas_w}px")


def render_hug(canvas_h: int, font_ratio: float, gap_ratio: float, margin_ratio: float,
               out_path: Path) -> None:
    """Холст облегает слово — для wordmark-файла без лишнего пустого поля."""
    h = canvas_h * SCALE
    font = load_font(int(h * font_ratio))
    gap = gap_ratio * font.size

    probe = Image.new("RGB", (10, 10), BG)
    pdraw = ImageDraw.Draw(probe)
    ww, cap_top, text_h = _measure(pdraw, font, gap)

    margin = int(h * margin_ratio)
    w = int(ww + 2 * margin)

    img = Image.new("RGB", (w, h), BG)
    draw = ImageDraw.Draw(img)
    x0 = margin
    baseline_y = (h - text_h) / 2 - cap_top
    draw_word(draw, x0, baseline_y, WORD, font, gap)

    canvas_w = round(w / SCALE)
    _save(img, canvas_w, canvas_h, out_path)
    print(f"{out_path.name}: {canvas_w}x{canvas_h} (облегает слово)")


def _save(img: Image.Image, canvas_w: int, canvas_h: int, out_path: Path) -> None:
    img = img.resize((canvas_w, canvas_h), Image.LANCZOS)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    img.save(out_path.with_suffix(".png"))
    img.save(out_path.with_suffix(".pdf"))


if __name__ == "__main__":
    # квадрат под аватар IG/Threads: крупнее прежнего — на 32-40px в ленте
    # прежний размер (font_ratio 0.16) размывался в кашу, замерено 2026-08-24
    render_fixed(1080, 1080, font_ratio=0.20, gap_ratio=0.07, out_path=OUT_DIR / "m4ksi-icon-square")

    # горизонтальный wordmark: холст облегает слово, под сайт/шапку/подпись
    render_hug(640, font_ratio=0.42, gap_ratio=0.07, margin_ratio=0.28,
               out_path=OUT_DIR / "m4ksi-wordmark-horizontal")
