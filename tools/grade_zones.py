#!/usr/bin/env python3
"""Замер картинки ПО ЗОНАМ: тени / средние / света — и тепло в каждой.

    python grade_zones.py out/warm-a.mp4
    python grade_zones.py out/warm-a.mp4 --segments 0:2.4 2.4:4.1 ...
    python grade_zones.py raw/08.jpg --hdr 0
    python grade_zones.py work/clip.mp4 --chain "curves=...,vibrance=..."

Зачем отдельный модуль, когда есть grade_lab и shot_stats.

grade_lab считает одно число на кадр: выбито, чёрное, яркость, насыщенность.
Этого хватало, пока задача была «не выжги небо». Задача 2026-08-24 другая:
**тепло в средних и светах, холод только в тенях**. Одним числом на кадр это
не проверяется вовсе — средняя температура кадра может быть нейтральной и при
холодных светах, и при тёплых тенях, то есть ровно в двух противоположных
случаях, один из которых брак.

Поэтому здесь пиксели раскладываются по яркости на три зоны и каждая мерится
отдельно. «Тепло» = среднее (R − B) в зоне, в единицах 0..255:
    плюс  — зона тёплая (янтарь, кожа, солнце)
    ноль  — нейтральная
    минус — холодная (синева, тень, пасмурное небо)

Пороги зон взяты по luma 0..255: тени < 64, средние 64..180, света > 180.
Границы не круглые случайно: 64 — примерно там, где на нашем материале
кончается торпедо машины, 180 — там, где начинается пасмурное небо.

ВЫБИТО и ЗАДАВЛЕНО считаются по порогам Кота 2026-08-24 (>=250 и <=5), а не
по >=254/<=2 из grade_lab: 254 пропускает света, которые уже склеились, но
формально не в потолке. Оба числа печатаются, чтобы старые прогоны сравнивались.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

import config

SHADOW_TOP, HIGH_BOT = 64.0, 180.0


def _duration(path):
    r = subprocess.run(
        [config.FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _frames(path, n, hdr, npl, chain, seg, out_dir):
    """Вынуть n кадров, применив тонмап и цепочку. Без кодирования — в PNG."""
    pre = []
    if seg:
        a, b = seg
        pre = ["-ss", "%.3f" % a, "-t", "%.3f" % (b - a)]
        dur = b - a
    else:
        dur = _duration(path)

    vf = []
    if hdr:
        vf.append(config.tonemap(npl))
    is_still = path.lower().endswith((".jpg", ".jpeg", ".png"))
    if not is_still:
        rate = max(n / dur, 0.05) if dur > 0 else 1.0
        vf.append("fps=%.5f" % rate)
    if chain:
        vf.append(chain)
    vf.append("scale=540:-2")

    cmd = ([config.FFMPEG, "-y", "-hide_banner", "-loglevel", "error"] + pre
           + ["-i", path, "-vf", ",".join(vf), "-frames:v",
              "1" if is_still else str(n), os.path.join(out_dir, "f%03d.png")])
    subprocess.run(cmd, check=True)
    return sorted(os.listdir(out_dir))


def measure(path, n=12, hdr=False, npl=None, chain="", seg=None):
    rows = []
    with tempfile.TemporaryDirectory() as td:
        names = _frames(path, n, hdr, npl, chain, seg, td)
        if not names:
            return None
        for name in names:
            a = np.asarray(Image.open(os.path.join(td, name)).convert("RGB"),
                           dtype=np.float32)
            r, g, b = a[..., 0], a[..., 1], a[..., 2]
            luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
            mx, mn = a.max(axis=2), a.min(axis=2)
            sat = np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
            warm = r - b

            sh = luma < SHADOW_TOP
            hi = luma > HIGH_BOT
            md = ~sh & ~hi

            def zmean(mask, arr):
                return float(arr[mask].mean()) if mask.any() else float("nan")

            rows.append({
                "яркость": float(luma.mean()),
                "СКО": float(luma.std()),
                "насыщ": float(sat.mean()),
                "выбито250": 100.0 * float((luma >= 250).sum()) / luma.size,
                "чёрное5": 100.0 * float((luma <= 5).sum()) / luma.size,
                "выбито254": 100.0 * float((luma >= 254).sum()) / luma.size,
                "чёрное2": 100.0 * float((luma <= 2).sum()) / luma.size,
                "тепло_тени": zmean(sh, warm),
                "тепло_сред": zmean(md, warm),
                "тепло_света": zmean(hi, warm),
                "насыщ_света": zmean(hi, sat),
                "доля_теней": 100.0 * float(sh.sum()) / luma.size,
                "доля_светов": 100.0 * float(hi.sum()) / luma.size,
                # пурпур в светах — мерка из craft/color, чтобы не терять её
                "пурпур": (float(((r + b) / 2 - g)[luma > 200].mean())
                           if (luma > 200).any() else 0.0),
            })

    keys = rows[0].keys()
    out = {k: float(np.nanmean([x[k] for x in rows])) for k in keys}
    out["выбито250_пик"] = float(np.nanmax([x["выбито250"] for x in rows]))
    out["чёрное5_пик"] = float(np.nanmax([x["чёрное5"] for x in rows]))
    out["кадров"] = len(rows)
    return out


ORDER = ["яркость", "СКО", "насыщ", "выбито250", "выбито250_пик", "чёрное5",
         "чёрное5_пик", "тепло_тени", "тепло_сред", "тепло_света",
         "насыщ_света", "пурпур"]


def show(name, r):
    print("%-22s " % name[:22] + "  ".join(
        "%s %.2f" % (k, r[k]) for k in ORDER))


def main():
    ap = argparse.ArgumentParser(description="Замер по зонам яркости")
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--hdr", action="store_true")
    ap.add_argument("--npl", type=int, default=None)
    ap.add_argument("--chain", default="", help="цепочка фильтров перед замером")
    ap.add_argument("--segments", nargs="*", default=None,
                    help="куски одного файла: 0:2.4 2.4:4.1 ...")
    ap.add_argument("--json", default=None, help="сохранить замер файлом")
    a = ap.parse_args()

    res = {}
    if a.segments:
        p = a.inputs[0]
        for s in a.segments:
            x, y = s.split(":")
            r = measure(p, a.n, a.hdr, a.npl, a.chain, (float(x), float(y)))
            if r:
                res[s] = r
    else:
        for p in a.inputs:
            r = measure(p, a.n, a.hdr, a.npl, a.chain)
            if r:
                res[os.path.basename(p)] = r

    if not res:
        sys.exit("нечего мерить")
    for k, v in res.items():
        show(k, v)

    if len(res) > 1:
        print("-" * 60)
        for key in ("яркость", "СКО", "насыщ", "тепло_сред"):
            vals = [v[key] for v in res.values()]
            print("разброс %-12s %.3f" % (key, max(vals) - min(vals)))

    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
        print("замер сохранён: " + a.json)


if __name__ == "__main__":
    main()
