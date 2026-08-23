#!/usr/bin/env python3
"""Общий рендерер: плашки, лоуэр-терды, обложки. ОДИН на все поверхности.

    # обложка из кадра видео
    python plate.py --layout cover --frame work/src.mp4 --at 3.2 \
        --kicker "АВТОМАТИЗАЦИЯ" --text "Менеджер копирует заявки руками" \
        -o out/cover.jpg

    # плашка поверх видео (прозрачный PNG на весь кадр)
    python plate.py --layout plate --text "35 минут -> 2" --y 900 -o work/plate.png

    # нижняя треть
    python plate.py --layout lower --kicker "M4KSI" --text "ИИ-агенты для бизнеса" \
        -o work/lower.png

    # кадр карусели под пост: заголовок на своей подложке, 4:5
    python plate.py --layout card --size 1080x1350 --kicker "КЕЙС" \
        --text "Он не написал текст. Он нарисовал систему." \
        --note "шахматная школа — воронка продаж" -o out/slide-1.jpg

    # кадр карусели со скриншотом внутри
    python plate.py --layout shot --size 1080x1350 --image raw/voronka.png \
        --kicker "ВОРОНКА" --text "Где мы теряем деньги" -o out/slide-2.jpg

Почему один модуль на всё: правило ремесла — стиль живёт в коде рендерера,
а не в описании. Переписывать его «из прозы» под каждую поверхность значит
терять грид-safe, отступы и иерархию. Это повторная грабля канона цеха.

Цвета берутся из палитры (`presets/palette-*.json`), не зашиты: окончательный
дизайн не выбран.
"""
import argparse
import json
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

import config
import palette as pal

GRID_AR = 3 / 4          # сетка площадки режет превью примерно до 3:4
SAFE_BOTTOM = 0.15       # низ занят интерфейсом


# ─── типографика ──────────────────────────────────────────────────────────

def font(path, size):
    if not os.path.exists(path):
        sys.exit("нет шрифта: %s\nПоложи static TTF в assets/fonts/ (см. doctor.ps1)"
                 % path)
    return ImageFont.truetype(path, size)


def text_w(draw, s, f, spacing=0.0):
    """Ширина строки с разрядкой. PIL разрядку не умеет — считаем сами."""
    if spacing <= 0:
        return draw.textlength(s, font=f)
    return sum(draw.textlength(c, font=f) for c in s) + spacing * f.size * (len(s) - 1)


def draw_spaced(draw, xy, s, f, fill, spacing=0.0):
    """Рисуем по символу — иначе разрядки не будет."""
    x, y = xy
    if spacing <= 0:
        draw.text((x, y), s, font=f, fill=fill)
        return
    for c in s:
        draw.text((x, y), c, font=f, fill=fill)
        x += draw.textlength(c, font=f) + spacing * f.size


def wrap(draw, s, f, max_w):
    words, lines, cur = s.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=f) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def fit_size(draw, s, path, max_w, max_h, start, min_size=28):
    """Подбор кегля под коробку. Уменьшать ниже min_size нельзя: в сетке
    такое уже не читается, и обложку надо переписывать, а не мельчить."""
    size = start
    while size > min_size:
        f = font(path, size)
        lines = wrap(draw, s, f, max_w)
        h = len(lines) * size * 1.18
        if h <= max_h and all(draw.textlength(l, font=f) <= max_w for l in lines):
            return f, lines
        size -= 2
    f = font(path, min_size)
    return f, wrap(draw, s, f, max_w)


# ─── контраст ─────────────────────────────────────────────────────────────

def rel_lum(c):
    def ch(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(c[0]) + 0.7152 * ch(c[1]) + 0.0722 * ch(c[2])


def contrast(a, b):
    la, lb = rel_lum(a), rel_lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


# ─── кадр из видео ────────────────────────────────────────────────────────

def grab_frame(video, at, hdr, out_png):
    """Кадр пофреймово: обычный seek плавает на 1-3 кадра, а обложку выбирают
    точно. Тонмап для стоп-кадра — npl=250 (краft/video-station)."""
    vf = (config.TONEMAP_COVER + ",") if hdr else ""
    subprocess.run([config.FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                    "-ss", str(max(0.0, at - 0.5)), "-i", video,
                    "-vf", vf + "select='gte(t,%f)'" % at,
                    "-frames:v", "1", "-fps_mode", "passthrough", out_png],
                   check=True)
    return Image.open(out_png).convert("RGB")


# ─── раскладки ────────────────────────────────────────────────────────────

def layout_cover(p, base, kicker, text, W=None, H=None):
    """Обложка: кикер + герой в грид-безопасной зоне, на плотной панели."""
    W = W or config.FRAME_W
    H = H or config.FRAME_H
    img = base.resize((W, H)).convert("RGBA") if base else \
        Image.new("RGBA", (W, H), pal.rgba(p["bg"]))
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)

    pad = 72
    box_w = W - pad * 2
    # панель — в центральной зоне: сетка режет края, и герой обязан уцелеть
    f_hero, lines = fit_size(d, text, config.PF_SB, box_w - 64, 560, 104)
    line_h = f_hero.size * 1.18
    body_h = len(lines) * line_h
    f_kick = font(config.INTER_SB, 34)
    kick_h = f_kick.size * 2.2 if kicker else 0
    panel_h = int(body_h + kick_h + 96)
    py = int(H * 0.62) - panel_h // 2

    plate_rgba = pal.rgba(p["plate"], p["plate_opacity"])
    d.rectangle([pad, py, W - pad, py + panel_h], fill=plate_rgba)
    d.rectangle([pad, py, W - pad, py + 2], fill=pal.rgba(p["hairline"]))

    y = py + 44
    if kicker:
        draw_spaced(d, (pad + 32, y), kicker.upper(), f_kick,
                    pal.rgba(p["accent"]), config.KICKER_LETTERSPACING)
        y += kick_h
    for ln in lines:
        d.text((pad + 32, y), ln, font=f_hero, fill=pal.rgba(p["heading"]))
        y += line_h
    return Image.alpha_composite(img, lay), plate_rgba, pal.rgba(p["heading"])


def layout_plate(p, kicker, text, y_center, W=None, H=None):
    """Плашка поверх видео: прозрачный PNG на весь кадр."""
    W = W or config.FRAME_W
    H = H or config.FRAME_H
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    f, lines = fit_size(d, text, config.INTER_XB, W - 240, 420, 78)
    line_h = f.size * 1.16
    body_h = len(lines) * line_h
    f_kick = font(config.INTER_SB, 30)
    kick_h = f_kick.size * 2.1 if kicker else 0
    h = int(body_h + kick_h + 64)
    widest = max(d.textlength(l, font=f) for l in lines)
    w = int(min(W - 120, max(widest, text_w(d, kicker.upper(), f_kick,
              config.KICKER_LETTERSPACING) if kicker else 0) + 72))
    x = (W - w) // 2
    y0 = int(y_center - h / 2)

    plate_rgba = pal.rgba(p["plate"], p["plate_opacity"])
    d.rectangle([x, y0, x + w, y0 + h], fill=plate_rgba)
    d.rectangle([x, y0, x + w, y0 + 2], fill=pal.rgba(p["hairline"]))
    y = y0 + 26
    if kicker:
        draw_spaced(d, (x + 36, y), kicker.upper(), f_kick,
                    pal.rgba(p["accent"]), config.KICKER_LETTERSPACING)
        y += kick_h
    for ln in lines:
        d.text((x + 36, y), ln, font=f, fill=pal.rgba(p["text"]))
        y += line_h
    return lay, plate_rgba, pal.rgba(p["text"])


def layout_lower(p, kicker, text, W=None, H=None):
    """Нижняя треть — над зоной интерфейса площадки."""
    H = H or config.FRAME_H
    y = int(H * (1 - SAFE_BOTTOM) - 210)
    return layout_plate(p, kicker, text, y, W, H)


def layout_card(p, kicker, text, note, W=None, H=None):
    """Кадр карусели: заголовок на плотном фоне, без видео под ним.

    Отличается от `cover` тем, что снизу есть место под подпись и марку —
    в карусели кадр читают дольше, чем обложку в ленте, и одной фразы мало.
    """
    W = W or config.FRAME_W
    H = H or config.FRAME_H
    img = Image.new("RGBA", (W, H), pal.rgba(p["bg"]))
    d = ImageDraw.Draw(img)

    pad = int(W * 0.085)
    box_w = W - pad * 2
    f_kick = font(config.INTER_SB, max(26, int(W / 32)))
    f_note = font(config.INTER_RG, max(22, int(W / 40)))
    mark_h = int(f_note.size * 2.4)

    y = pad
    if kicker:
        draw_spaced(d, (pad, y), kicker.upper(), f_kick,
                    pal.rgba(p["accent"]), config.KICKER_LETTERSPACING)
        y += int(f_kick.size * 2.4)

    note_lines = wrap(d, note, f_note, box_w) if note else []
    note_h = int(len(note_lines) * f_note.size * 1.35)
    top, bottom = y, H - pad - mark_h - int(H * 0.02)
    rule_h = int(f_note.size * 1.6) + 4 if note_lines else 0
    room = (bottom - top) - note_h - rule_h
    f_hero, lines = fit_size(d, text, config.PF_SB, box_w, room, int(W / 9))

    # блок ставится чуть выше геометрического центра: снизу марка, и
    # оптический центр кадра выше середины — иначе низ проваливается
    block_h = int(len(lines) * f_hero.size * 1.16) + note_h + rule_h
    y = top + max(0, int((bottom - top - block_h) * 0.38))

    for ln in lines:
        d.text((pad, y), ln, font=f_hero, fill=pal.rgba(p["heading"]))
        y += f_hero.size * 1.16

    if note_lines:
        y += int(f_hero.size * 0.34)
        d.rectangle([pad, y, pad + int(W * 0.12), y + 4],
                    fill=pal.rgba(p["accent"]))
        y += int(f_note.size * 1.6)
        for ln in note_lines:
            d.text((pad, y), ln, font=f_note, fill=pal.rgba(p["text_soft"]))
            y += f_note.size * 1.35

    d.rectangle([pad, H - pad - mark_h, W - pad, H - pad - mark_h + 1],
                fill=pal.rgba(p["hairline"]))
    draw_spaced(d, (pad, H - pad - int(mark_h * 0.5)), "M4KSI", f_note,
                pal.rgba(p["text_soft"]), config.KICKER_LETTERSPACING)
    return img, pal.rgba(p["bg"]), pal.rgba(p["heading"])


def layout_shot(p, shot_path, kicker, text, note, W=None, H=None):
    """Кадр карусели со скриншотом: заголовок сверху, снимок экрана в рамке.

    Скриншот вписывается целиком (не кропается): в нём смысл, а обрезанная
    схема бесполезна. Пустое место по бокам добирается фоном палитры.
    """
    W = W or config.FRAME_W
    H = H or config.FRAME_H
    if not os.path.exists(shot_path):
        sys.exit("нет файла скриншота: %s" % shot_path)
    img = Image.new("RGBA", (W, H), pal.rgba(p["bg"]))
    d = ImageDraw.Draw(img)

    pad = int(W * 0.085)
    box_w = W - pad * 2
    f_kick = font(config.INTER_SB, max(26, int(W / 34)))
    f_head = font(config.INTER_XB, max(30, int(W / 22)))
    f_note = font(config.INTER_RG, max(22, int(W / 42)))

    y = pad
    if kicker:
        draw_spaced(d, (pad, y), kicker.upper(), f_kick,
                    pal.rgba(p["accent"]), config.KICKER_LETTERSPACING)
        y += int(f_kick.size * 2.2)
    head_lines = wrap(d, text, f_head, box_w) if text else []
    for ln in head_lines:
        d.text((pad, y), ln, font=f_head, fill=pal.rgba(p["heading"]))
        y += int(f_head.size * 1.18)
    y += int(pad * 0.5)

    note_lines = wrap(d, note, f_note, box_w) if note else []
    note_h = int(len(note_lines) * f_note.size * 1.35) + (pad if note_lines else 0)
    frame_h = H - y - pad - note_h
    shot = Image.open(shot_path).convert("RGB")
    k = min(box_w / shot.width, frame_h / shot.height)
    sw, sh = int(shot.width * k), int(shot.height * k)
    shot = shot.resize((sw, sh), Image.LANCZOS)
    sx, sy = (W - sw) // 2, y + (frame_h - sh) // 2
    img.paste(shot, (sx, sy))
    d.rectangle([sx - 1, sy - 1, sx + sw, sy + sh],
                outline=pal.rgba(p["hairline"]), width=2)

    if note_lines:
        ny = y + frame_h + int(pad * 0.4)
        for ln in note_lines:
            d.text((pad, ny), ln, font=f_note, fill=pal.rgba(p["text_soft"]))
            ny += f_note.size * 1.35
    return img, pal.rgba(p["bg"]), pal.rgba(p["heading"])


# ─── проверка сетки ───────────────────────────────────────────────────────

def grid_note(img):
    tw = min(img.width, int(img.height * GRID_AR))
    th = int(tw / GRID_AR)
    x, y = (img.width - tw) // 2, (img.height - th) // 2
    return ("сетка режет до %dx%d из центра — всё за этой рамкой в превью "
            "не видно (проверь grid_test.py)" % (tw, th)), (x, y, tw, th)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--layout", choices=["cover", "plate", "lower", "card", "shot"],
                    required=True)
    ap.add_argument("--text", required=True)
    ap.add_argument("--kicker", default=None)
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--frame", default=None, help="видео, из которого взять кадр")
    ap.add_argument("--at", type=float, default=0.0, help="секунда кадра")
    ap.add_argument("--hdr", action="store_true", help="исходник HLG/HDR")
    ap.add_argument("--y", type=int, default=None, help="центр плашки по вертикали")
    ap.add_argument("--palette", default=None)
    ap.add_argument("--size", default=None, metavar="ШxВ",
                    help="холст, по умолчанию 1080x1920; карусель — 1080x1350")
    ap.add_argument("--image", default=None, help="скриншот для раскладки shot")
    ap.add_argument("--note", default=None, help="подпись под заголовком")
    a = ap.parse_args()

    W = H = None
    if a.size:
        try:
            W, H = (int(v) for v in a.size.lower().replace("х", "x").split("x"))
        except ValueError:
            sys.exit("--size пишется как 1080x1350")

    p = pal.load(a.palette)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)

    if a.layout in ("card", "shot"):
        if a.layout == "shot":
            if not a.image:
                sys.exit("раскладке shot нужен --image со скриншотом")
            img, plate_c, text_c = layout_shot(p, a.image, a.kicker, a.text,
                                               a.note, W, H)
        else:
            img, plate_c, text_c = layout_card(p, a.kicker, a.text, a.note, W, H)
        img = img.convert("RGB")
        if a.out.lower().endswith((".jpg", ".jpeg")):
            img.save(a.out, quality=95, subsampling=0)
        else:
            img.save(a.out)
        note, box = grid_note(img)
        print("  " + note)
    elif a.layout == "cover":
        base = None
        if a.frame:
            tmp = os.path.splitext(a.out)[0] + "-frame.png"
            base = grab_frame(a.frame, a.at, a.hdr, tmp)
            os.remove(tmp)
        img, plate_c, text_c = layout_cover(p, base, a.kicker, a.text, W, H)
        img = img.convert("RGB")
        img.save(a.out, quality=94) if a.out.lower().endswith((".jpg", ".jpeg")) \
            else img.save(a.out)
        note, box = grid_note(img)
        print("  " + note)
    else:
        y = a.y if a.y is not None else int((H or config.FRAME_H) * 0.5)
        img, plate_c, text_c = (layout_lower(p, a.kicker, a.text, W, H)
                                if a.layout == "lower"
                                else layout_plate(p, a.kicker, a.text, y, W, H))
        img.save(a.out)

    ratio = contrast(text_c[:3], plate_c[:3])
    verdict = "OK" if ratio >= config.CONTRAST_FLOOR else "БРАК"
    print("%s: раскладка %s, палитра «%s»" % (a.out, a.layout, p["name"]))
    print("%s контраст текст/подложка %.2f при пороге %.1f"
          % (verdict, ratio, config.CONTRAST_FLOOR))
    if ratio < config.CONTRAST_FLOOR:
        print("   Поднять непрозрачность подложки в палитре — не «подобрать под фон».")
        sys.exit(1)


if __name__ == "__main__":
    main()
