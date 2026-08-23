#!/usr/bin/env python3
"""Сколько картинки выбито в белое и задавлено в чёрное — числами.

    python clip_report.py work/clip.mp4 out/reel.mp4 --n 12

«Пересветы» на глаз — спор. Пересветы в процентах выбитых пикселей — факт.
Модуль вынимает n кадров равномерно по файлу и считает по каждому:

  * ВЫБИТО   — доля пикселей, где яркость >= 254. Там уже нет никакой
               информации: ни фактуры облаков, ни оконного переплёта.
  * НА КРАЮ  — доля, где яркость >= 245. Ещё не белое, но на полшага до него;
               площадка добьёт это своим кодировщиком.
  * ЗАДАВЛЕНО — доля, где яркость <= 2. Чёрное пятно вместо теней.
  * P99.5    — уровень, ниже которого лежит 99.5% пикселей. Если он упёрся
               в 255, значит верх гистограммы слипся в стену.

Порог приемлемого. Выбитое небо в кадре — это не всегда брак: солнце и
пасмурная белизна физически ярче всего остального. Но выше ~1% выбитых
пикселей картинка начинает читаться «пережжённой», а выше 3% это видно
любому зрителю без сравнения.
"""
import argparse
import os
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

import config

CLIP_HI = 254
EDGE_HI = 245
CLIP_LO = 2


def frames(path, n):
    with tempfile.TemporaryDirectory() as td:
        dur = duration(path)
        rate = max(n / dur, 0.05) if dur > 0 else 1.0
        cmd = [config.FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
               "-i", path, "-vf", "fps=%.4f,scale=540:-2" % rate,
               "-frames:v", str(n), os.path.join(td, "f%03d.png")]
        subprocess.run(cmd, check=True)
        for name in sorted(os.listdir(td)):
            yield np.asarray(Image.open(os.path.join(td, name)).convert("RGB"),
                             dtype=np.float32)


def duration(path):
    r = subprocess.run(
        [config.FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def report(path, n):
    hi, edge, lo, p995, mean = [], [], [], [], []
    for arr in frames(path, n):
        luma = 0.2126 * arr[..., 0] + 0.7152 * arr[..., 1] + 0.0722 * arr[..., 2]
        total = luma.size
        hi.append(100.0 * (luma >= CLIP_HI).sum() / total)
        edge.append(100.0 * (luma >= EDGE_HI).sum() / total)
        lo.append(100.0 * (luma <= CLIP_LO).sum() / total)
        p995.append(float(np.percentile(luma, 99.5)))
        mean.append(float(luma.mean()))
    if not hi:
        sys.exit("не удалось вынуть кадры из " + path)
    return {
        "выбито": float(np.mean(hi)), "выбито_макс": float(np.max(hi)),
        "на_краю": float(np.mean(edge)),
        "задавлено": float(np.mean(lo)),
        "p99.5": float(np.mean(p995)),
        "яркость": float(np.mean(mean)),
    }


def main():
    ap = argparse.ArgumentParser(description="Отчёт по пересветам и провалам")
    ap.add_argument("videos", nargs="+")
    ap.add_argument("--n", type=int, default=12, help="сколько кадров смотреть")
    a = ap.parse_args()

    print("%-26s %8s %8s %8s %8s %8s" %
          ("файл", "выбито%", "макс%", "край%", "чёрн%", "p99.5"))
    for v in a.videos:
        if not os.path.exists(v):
            print("%-26s  нет файла" % os.path.basename(v))
            continue
        r = report(v, a.n)
        flag = ""
        if r["выбито"] > 3.0:
            flag = "  <-- видно любому зрителю"
        elif r["выбито"] > 1.0:
            flag = "  <-- читается пережжённым"
        print("%-26s %8.2f %8.2f %8.2f %8.2f %8.1f%s" %
              (os.path.basename(v), r["выбито"], r["выбито_макс"],
               r["на_краю"], r["задавлено"], r["p99.5"], flag))


if __name__ == "__main__":
    main()
