#!/usr/bin/env python3
"""Стенд для профиля картинки: несколько вариантов — и цифры по каждому.

    python grade_lab.py work/clip.mp4 --n 14

Зачем. Профиль, подобранный на глаз по одному красивому кадру, врёт: на
пасмурном небе он выбивает белое, на тёмном салоне давит чёрное, и видно это
уже владельцу. Стенд гоняет варианты по одному материалу и считает то, что
глазом не считается — долю выбитых и задавленных пикселей.

Кадры НЕ кодируются: фильтр применяется на извлечении, замер идёт по PNG.
Так прогон варианта занимает секунды, а не минуты, и можно перебрать десяток.

Правило приёмки (2026-08-23, после брака reel-v2 с 6.19% выбитого):
    выбито  < 0.5 %   среднее по кадрам
    пик     < 2.0 %   на худшем кадре
    чёрное  < 3.0 %
Вариант, не проходящий по этим трём, владельцу не показывается.
"""
import argparse
import os
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

import config

LIMIT_MEAN, LIMIT_PEAK, LIMIT_DARK = 0.5, 2.0, 3.0


def measure(path, chain, n):
    vf = ("%s," % chain) if chain else ""
    vf += "scale=540:-2"
    dur = _duration(path)
    rate = max(n / dur, 0.05) if dur > 0 else 1.0
    hi, lo, p995, sat, lum = [], [], [], [], []
    with tempfile.TemporaryDirectory() as td:
        cmd = [config.FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
               "-i", path, "-vf", "fps=%.4f,%s" % (rate, vf),
               "-frames:v", str(n), os.path.join(td, "f%03d.png")]
        subprocess.run(cmd, check=True)
        names = sorted(os.listdir(td))
        if not names:
            sys.exit("не удалось вынуть кадры")
        for name in names:
            a = np.asarray(Image.open(os.path.join(td, name)).convert("RGB"),
                           dtype=np.float32)
            luma = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
            t = luma.size
            hi.append(100.0 * (luma >= 254).sum() / t)
            lum.append(float(luma.mean()) / 255.0)
            lo.append(100.0 * (luma <= 2).sum() / t)
            p995.append(float(np.percentile(luma, 99.5)))
            mx, mn = a.max(axis=2), a.min(axis=2)
            sat.append(float(np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0).mean()))
    return {
        "выбито": float(np.mean(hi)), "пик": float(np.max(hi)),
        "чёрное": float(np.mean(lo)), "p99.5": float(np.mean(p995)),
        "насыщ": float(np.mean(sat)),
        "яркость": float(np.mean(lum)),
    }


def _duration(path):
    r = subprocess.run(
        [config.FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


# Кандидаты. Каждый — ответ на конкретную претензию владельца 2026-08-23:
# «куча пересветов», «странная резкость», «цвета природные, но яркие».
CANDIDATES = [
    # Тон НЕ трогаем ни в одном варианте — владелец 2026-08-23: «вместо
    # насыщенности цветов ты вытягиваешь контраст, яркость». Перебираем
    # ровно одну величину: насколько поднять цвет.
    #
    # Ориентир естественности — его же фотография того дня: насыщенность
    # 0.222. Уходить выше значит терять натуральность, ниже — оставить
    # картинку вялой, как в первом заходе.
    ("0. как есть", ""),
    ("1. vibrance 0.20", "vibrance=intensity=0.20"),
    ("2. vibrance 0.30", "vibrance=intensity=0.30"),
    ("3. vibrance 0.40", "vibrance=intensity=0.40"),
    ("4. vibrance 0.50", "vibrance=intensity=0.50"),
    ("5. vibrance 0.65", "vibrance=intensity=0.65"),
    ("6. eq sat 1.15 (для сравнения)", "eq=saturation=1.15"),
    ("7. отвергнутый v3", "colorbalance=bs=0.028:rh=0.014:bh=-0.010,"
     "curves=all='0/0.012 0.10/0.095 0.30/0.30 0.62/0.665 0.88/0.925 1/1',"
     "vibrance=intensity=0.85"),
]


def main():
    ap = argparse.ArgumentParser(description="Стенд профиля картинки")
    ap.add_argument("video")
    ap.add_argument("--n", type=int, default=14)
    a = ap.parse_args()

    print("%-30s %8s %8s %8s %9s %8s  %s" %
          ("вариант", "выбито%", "пик%", "чёрное%", "яркость", "насыщ", "приёмка"))
    for name, chain in CANDIDATES:
        r = measure(a.video, chain, a.n)
        ok = (r["выбито"] < LIMIT_MEAN and r["пик"] < LIMIT_PEAK
              and r["чёрное"] < LIMIT_DARK)
        print("%-30s %8.2f %8.2f %8.2f %9.3f %8.3f  %s" %
              (name, r["выбито"], r["пик"], r["чёрное"], r["яркость"],
               r["насыщ"], "прошёл" if ok else "НЕ ПРОШЁЛ"))


if __name__ == "__main__":
    main()
