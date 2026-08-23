#!/usr/bin/env python3
"""Проверка обложки в сетке: читается ли она размером с ноготь.

    python grid_test.py <картинка> [-o out.png]

Площадка режет превью примерно до 3:4 и показывает мелким. Обложка, которая
не читается здесь, не существует — сколько бы красиво она ни выглядела в
полный размер. Это первый вопрос к обложке, остальные после него.
"""
import argparse, os
from PIL import Image


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--width", type=int, default=160, help="ширина в сетке, px")
    a = ap.parse_args()

    im = Image.open(a.src).convert("RGB")
    # центральный кроп 3:4 — так режет сетка
    tw = min(im.width, int(im.height * 3 / 4))
    th = int(tw * 4 / 3)
    box = ((im.width - tw) // 2, (im.height - th) // 2)
    crop = im.crop((box[0], box[1], box[0] + tw, box[1] + th))
    small = crop.resize((a.width, int(a.width * 4 / 3)), Image.LANCZOS)

    out = a.out or os.path.splitext(a.src)[0] + "-grid.png"
    # рядом кладём увеличенное без сглаживания — видно, что реально различимо
    both = Image.new("RGB", (small.width + small.width * 3 + 20, small.height * 3), "white")
    both.paste(small, (0, 0))
    both.paste(small.resize((small.width * 3, small.height * 3), Image.NEAREST),
               (small.width + 20, 0))
    both.save(out)
    print(f"{out}: слева — как в сетке ({a.width}px), справа — то же, увеличено.")
    print("Заголовок не читается слева → обложку переделывать, а не уговаривать себя.")


if __name__ == "__main__":
    main()
