#!/usr/bin/env python3
"""Посмотреть на свою работу глазами — контактный лист кадров.

    python look.py <видео> [-n 12] [-o work/look.jpg] [--safe] [--zones]
    python look.py <видео> --frame 4.2 -o work/f42.png

Числовые гейты (`qa.py`) не ловят «ужасный цветокор» и «странная резкость» —
это видит только глаз. Но глазу нужно **что-то показать**: не 26 секунд
видео, а одну картинку, на которой весь ролик виден разом.

Контактный лист — эта картинка. Кадры берутся равномерно, каждый подписан
секундой, всё складывается в сетку. По ней сразу видно то, что в потоке
проскакивает: скачок яркости на склейке, кадр-провал, повтор ракурса,
пересвет в одном месте, разъехавшийся цвет между клипами.

`--safe` рисует поверх безопасную зону площадок: интерфейс Reels/TikTok/
Shorts закрывает верх, правый столбец и низ кадра. Текст, лицо и призыв,
попавшие под интерфейс, зритель не увидит — а на нашем экране всё выглядело
хорошо.

Работает и по картинке (обложка), и по папке с кадрами.
"""
import argparse, glob, os, subprocess, sys
from PIL import Image, ImageDraw, ImageFont
import config

# ─── безопасная зона вертикали 1080×1920 ─────────────────────────────────
# Замер 2026-08-23 по открытым спекам площадок (craft/platform-specs.md).
# Пересечение зон Reels · TikTok · Shorts ≈ 900×1400 по центру кадра.
SAFE_W, SAFE_H = 900, 1400
UI_TOP = 120          # строка статуса и кнопки площадки
UI_BOTTOM = 250       # подпись, имя автора, звук
UI_RIGHT = 200        # столбец кнопок: лайк, коммент, пересылка


def probe_duration(path):
    r = subprocess.run(
        [config.FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path], capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def grab(path, t, out):
    """Кадр на секунде t. -ss до -i — быстрый seek, для контактного листа
    его точности хватает; пофреймовая точность нужна обложке, не обзору."""
    subprocess.run(
        [config.FFMPEG, "-hide_banner", "-loglevel", "error", "-ss", f"{t:.3f}",
         "-i", path, "-frames:v", "1", "-q:v", "2", "-y", out],
        check=True)


def draw_safe(im, scale):
    """Поверх кадра — что закроет интерфейс площадки."""
    d = ImageDraw.Draw(im, "RGBA")
    w, h = im.size
    sx, sy = (w - SAFE_W * scale) / 2, (h - SAFE_H * scale) / 2
    # опасные полосы — тонкой заливкой, чтобы не спорить с кадром
    d.rectangle([0, 0, w, UI_TOP * scale], fill=(255, 0, 0, 46))
    d.rectangle([0, h - UI_BOTTOM * scale, w, h], fill=(255, 0, 0, 46))
    d.rectangle([w - UI_RIGHT * scale, h * 0.45, w, h], fill=(255, 0, 0, 46))
    # безопасный прямоугольник — контуром
    d.rectangle([sx, sy, sx + SAFE_W * scale, sy + SAFE_H * scale],
                outline=(0, 255, 128, 200), width=max(1, int(2 * scale)))


def font(size):
    for name in ("Inter-SemiBold.ttf", "Inter-Regular.ttf"):
        p = os.path.join(config.FONTS, name)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def label(im, text, size=22):
    d = ImageDraw.Draw(im, "RGBA")
    f = font(size)
    box = d.textbbox((0, 0), text, font=f)
    pad = size // 3
    d.rectangle([0, 0, box[2] + pad * 2, box[3] + pad * 2], fill=(0, 0, 0, 210))
    d.text((pad, pad), text, font=f, fill=(255, 255, 255, 255))


def sheet(frames, cols, tile_w, safe):
    """frames — список (подпись, PIL.Image). Складывает в сетку."""
    ratio = frames[0][1].height / frames[0][1].width
    tile_h = int(tile_w * ratio)
    rows = (len(frames) + cols - 1) // cols
    gap = 8
    out = Image.new("RGB",
                    (cols * tile_w + (cols + 1) * gap,
                     rows * tile_h + (rows + 1) * gap), (24, 24, 24))
    for i, (cap, im) in enumerate(frames):
        t = im.resize((tile_w, tile_h), Image.LANCZOS)
        if safe:
            draw_safe(t, tile_w / 1080)
        label(t, cap, max(14, tile_w // 14))
        x = gap + (i % cols) * (tile_w + gap)
        y = gap + (i // cols) * (tile_h + gap)
        out.paste(t, (x, y))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", help="видео, картинка или папка с картинками")
    ap.add_argument("-n", "--count", type=int, default=12)
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--tile", type=int, default=300, help="ширина плитки, px")
    ap.add_argument("--safe", action="store_true", help="показать зону интерфейса")
    ap.add_argument("--frame", type=float, default=None,
                    help="вынуть один кадр в полный размер и выйти")
    ap.add_argument("--from", dest="t0", type=float, default=0.0)
    ap.add_argument("--to", dest="t1", type=float, default=None)
    a = ap.parse_args()

    work = os.path.join(os.path.dirname(os.path.abspath(a.src)) or ".", "_look_tmp")

    # ── один кадр в полный размер: судить «мыло» и цвет надо здесь ────────
    if a.frame is not None:
        out = a.out or f"frame_{a.frame:.2f}.png".replace(".", "_", 1)
        grab(a.src, a.frame, out)
        if a.safe:
            im = Image.open(out).convert("RGB")
            draw_safe(im, im.width / 1080)
            im.save(out)
        print(f"{out} — кадр {a.frame:.2f} с в полный размер.")
        print("Мыло и цвет судить ТОЛЬКО здесь: превью врёт в обе стороны.")
        return

    frames = []
    if os.path.isdir(a.src):
        for p in sorted(glob.glob(os.path.join(a.src, "*.[jp][pn]g"))):
            frames.append((os.path.basename(p), Image.open(p).convert("RGB")))
    elif a.src.lower().endswith((".jpg", ".jpeg", ".png")):
        frames.append((os.path.basename(a.src), Image.open(a.src).convert("RGB")))
    else:
        dur = probe_duration(a.src)
        t1 = a.t1 if a.t1 is not None else dur
        os.makedirs(work, exist_ok=True)
        # первый кадр берём почти с нуля: хук судится по нему
        step = (t1 - a.t0) / max(1, a.count - 1)
        for i in range(a.count):
            t = min(a.t0 + i * step, max(0.0, t1 - 0.05))
            p = os.path.join(work, f"{i:02d}.jpg")
            grab(a.src, t, p)
            frames.append((f"{t:.1f}s", Image.open(p).convert("RGB")))

    if not frames:
        sys.exit("нечего показывать: кадров не найдено")

    out = a.out or (os.path.splitext(a.src)[0].rstrip("\\/") + "-look.jpg")
    sheet(frames, a.cols, a.tile, a.safe).save(out, quality=92)
    for f in glob.glob(os.path.join(work, "*.jpg")):
        os.remove(f)
    if os.path.isdir(work):
        os.rmdir(work)

    print(f"{out} — {len(frames)} кадров, {a.cols} в ряд.")
    print("Смотреть по операции posmotret-rabotu: сначала ритм и провалы,")
    print("потом цвет между кадрами, потом текст в безопасной зоне (--safe).")


if __name__ == "__main__":
    main()
