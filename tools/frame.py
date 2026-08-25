# -*- coding: utf-8 -*-
"""Композиция кадра: сплит верх/низ, подложка с тенью, указатель, подсветка.

Зачем: разбор 23 чужих роликов дал один и тот же приём — **экран сверху,
говорящая голова снизу**. У нас вместо лица стояла размытая копия того же
кадра (`--fit blur`): та же площадь, но пустая. Плюс скриншот во весь кадр
мылится, а без указателя читается вдвое дольше.

Что умеет:
    split   — собрать кадр из двух источников: верх и низ
    shot    — скриншот на подложке со скруглением и тенью
    point   — стрелка и подсветка нужного места на картинке
    divider — линия-разделитель на стыке панелей

Запуск (статика):
    py -3.12 tools/frame.py split --top work/screen.png --bottom work/face.png \\
        -o work/split.png [--ratio 0.55] [--divider]
    py -3.12 tools/frame.py shot --image raw/dash.png -o work/shot.png
    py -3.12 tools/frame.py point --image work/shot.png --at 620,880 \\
        --text "сюда" -o work/pointed.png

Запуск (видео) — печатает готовую команду ffmpeg, не выполняет её:
    py -3.12 tools/frame.py split --video-top work/screen.mp4 \\
        --video-bottom work/face.mp4 --cmd
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402

from PIL import Image, ImageDraw, ImageFilter  # noqa: E402

W, H = 1080, 1920
RADIUS = 28          # скругление подложки под скриншот
SHADOW_BLUR = 26
SHADOW_OFFSET = 14
PAD = 48             # поля вокруг скриншота на подложке


def load(path, box):
    """Вписать картинку в прямоугольник по короткой стороне и обрезать лишнее."""
    im = Image.open(path).convert("RGB")
    bw, bh = box
    k = max(bw / im.width, bh / im.height)
    im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))),
                   Image.LANCZOS)
    left = (im.width - bw) // 2
    top = (im.height - bh) // 2
    return im.crop((left, top, left + bw, top + bh))


def split(top_path, bottom_path, out, ratio=0.55, divider=False):
    """Верх — экран, низ — лицо. Ratio: какую долю кадра занимает верх."""
    th = int(H * ratio)
    bh = H - th
    canvas = Image.new("RGB", (W, H), (0, 0, 0))
    canvas.paste(load(top_path, (W, th)), (0, 0))
    canvas.paste(load(bottom_path, (W, bh)), (0, th))
    if divider:
        d = ImageDraw.Draw(canvas)
        color = tuple(config.ACCENT[:3])
        d.rectangle([0, th - 3, W, th + 2], fill=color)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    canvas.save(out)
    print("сплит: %s  верх %d px (%.0f%%), низ %d px%s"
          % (out, th, ratio * 100, bh, ", разделитель есть" if divider else ""))
    return out


def shot(image, out, bg=None, radius=RADIUS):
    """Скриншот на подложке: скругление, тень, поля. Не во весь кадр — читается."""
    src = Image.open(image).convert("RGB")
    inner_w = W - PAD * 2
    k = inner_w / src.width
    inner_h = max(1, int(src.height * k))
    src = src.resize((inner_w, inner_h), Image.LANCZOS)

    # скругление
    mask = Image.new("L", (inner_w, inner_h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, inner_w, inner_h],
                                           radius=radius, fill=255)

    canvas = Image.new("RGB", (W, max(H, inner_h + PAD * 4)),
                       bg or tuple(config.BG[:3]))
    y = (canvas.height - inner_h) // 2

    # тень — размытый чёрный прямоугольник под картинкой
    sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle(
        [PAD, y + SHADOW_OFFSET, PAD + inner_w, y + inner_h + SHADOW_OFFSET],
        radius=radius, fill=(0, 0, 0, 150))
    sh = sh.filter(ImageFilter.GaussianBlur(SHADOW_BLUR))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), sh).convert("RGB")

    canvas.paste(src, (PAD, y), mask)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    canvas.save(out)
    print("скриншот на подложке: %s  (%dx%d, поля %d, скругление %d)"
          % (out, canvas.width, canvas.height, PAD, radius))
    return out


def point(image, at, out, text=None, box=None, dim=90):
    """Стрелка к месту на картинке + подсветка области. Без указателя кадр читается дольше."""
    im = Image.open(image).convert("RGB")
    d = ImageDraw.Draw(im, "RGBA")
    x, y = at
    color = tuple(config.ACCENT[:3])

    if box:
        bx, by, bw, bh = box
        # затемняем всё, кроме нужного места
        dark = Image.new("RGBA", im.size, (0, 0, 0, dim))
        hole = Image.new("L", im.size, 255)
        ImageDraw.Draw(hole).rounded_rectangle([bx, by, bx + bw, by + bh],
                                               radius=12, fill=0)
        dark.putalpha(hole)
        im = Image.alpha_composite(im.convert("RGBA"), dark).convert("RGB")
        d = ImageDraw.Draw(im, "RGBA")
        d.rounded_rectangle([bx, by, bx + bw, by + bh], radius=12,
                            outline=color + (255,), width=5)

    # стрелка: линия под 45° из верхнего левого угла к точке
    tail = (x - 170, y - 170)
    d.line([tail, (x, y)], fill=color + (255,), width=9)
    d.polygon([(x, y), (x - 34, y - 12), (x - 12, y - 34)], fill=color + (255,))
    d.ellipse([x - 16, y - 16, x + 16, y + 16], outline=color + (255,), width=6)

    if text:
        from PIL import ImageFont
        try:
            f = ImageFont.truetype(config.INTER_XB, 44)
        except Exception:
            f = ImageFont.load_default()
        tw = d.textbbox((0, 0), text, font=f)[2]
        tx, ty = tail[0] - tw - 20, tail[1] - 30
        d.rounded_rectangle([tx - 18, ty - 12, tx + tw + 18, ty + 60],
                            radius=10, fill=color + (255,))
        d.text((tx, ty), text, font=f, fill=(0, 0, 0, 255))

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    im.save(out)
    print("указатель: %s  точка (%d,%d)%s" % (out, x, y, ", подсветка есть" if box else ""))
    return out


def ffmpeg_split(top, bottom, ratio, out, divider):
    """Готовая команда для видео-сплита. Печатаем, а не выполняем: сборкой ведает build_reel."""
    th = int(H * ratio)
    bh = H - th
    line = ""
    if divider:
        c = "0x%02X%02X%02X" % tuple(config.ACCENT[:3])
        line = (",drawbox=x=0:y=%d:w=%d:h=5:color=%s@1:t=fill" % (th - 2, W, c))
    cmd = (
        '"{ff}" -i "{top}" -i "{bot}" -filter_complex '
        '"[0:v]scale={W}:{th}:force_original_aspect_ratio=increase,'
        'crop={W}:{th}[t];'
        '[1:v]scale={W}:{bh}:force_original_aspect_ratio=increase,'
        'crop={W}:{bh}[b];'
        '[t][b]vstack=inputs=2{line}[v]" '
        '-map "[v]" -map 1:a? -c:v libx264 -crf {crf} -pix_fmt yuv420p "{out}"'
    ).format(ff=config.FFMPEG, top=top, bot=bottom, W=W, th=th, bh=bh,
             line=line, crf=config.CRF, out=out)
    print(cmd)
    return cmd


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["split", "shot", "point", "divider"])
    ap.add_argument("--top"), ap.add_argument("--bottom")
    ap.add_argument("--video-top"), ap.add_argument("--video-bottom")
    ap.add_argument("--image")
    ap.add_argument("--at", help="точка указателя: x,y")
    ap.add_argument("--box", help="подсветить область: x,y,w,h")
    ap.add_argument("--text")
    ap.add_argument("--ratio", type=float, default=0.55,
                    help="доля кадра под верхнюю панель (по умолчанию 0.55)")
    ap.add_argument("--divider", action="store_true", help="линия на стыке панелей")
    ap.add_argument("--dim", type=int, default=90,
                    help="насколько затемнить вокруг подсветки, 0-255")
    ap.add_argument("--cmd", action="store_true", help="напечатать команду ffmpeg для видео")
    ap.add_argument("-o", "--out", default="work/frame.png")
    a = ap.parse_args()

    if a.mode == "split":
        if a.cmd or a.video_top:
            if not (a.video_top and a.video_bottom):
                sys.exit("для видео нужны --video-top и --video-bottom")
            return ffmpeg_split(a.video_top, a.video_bottom, a.ratio,
                                a.out.replace(".png", ".mp4"), a.divider) and 0
        if not (a.top and a.bottom):
            sys.exit("нужны --top и --bottom (картинки) или --video-top/--video-bottom")
        split(a.top, a.bottom, a.out, a.ratio, a.divider)
    elif a.mode == "shot":
        if not a.image:
            sys.exit("нужен --image")
        shot(a.image, a.out)
    elif a.mode == "point":
        if not (a.image and a.at):
            sys.exit("нужны --image и --at x,y")
        at = tuple(int(v) for v in a.at.split(","))
        box = tuple(int(v) for v in a.box.split(",")) if a.box else None
        point(a.image, at, a.out, a.text, box, a.dim)
    return 0


if __name__ == "__main__":
    sys.exit(main())
