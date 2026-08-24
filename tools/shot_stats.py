#!/usr/bin/env python3
"""Разброс между кусками: одинаково ли они выглядят.

    python shot_stats.py raw/*.mp4 --hdr
    python shot_stats.py out/reel.mp4 --segments 0:4.8 4.8:9.3 9.3:14.8

Зачем. Один общий грейд на весь ролик НЕ делает куски похожими. Телефон
ставит баланс белого и экспозицию заново на каждую съёмку: салон машины
уходит в синь, парк в зелень, асфальт в серость. Глобальная кривая двигает
их все одинаково — и разными они остаются ровно настолько, насколько были.

Модуль меряет по каждому куску:
  * ЯРКОСТЬ  — средняя luma 0..1
  * НАСЫЩ    — средняя S (насколько цвета вообще цветные)
  * R/G/B    — отклонение канала от серого; это и есть баланс белого.
               Куски, у которых эти три числа разъезжаются, зритель видит
               как «разный цветокор», даже не зная слова «баланс белого».

РАЗБРОС в конце — максимум минус минимум по каждой мерке. Он и есть ответ
на «фрагменты разные по цветокоррекции»: пока разброс большой, общий профиль
поверх ничего не исправит.
"""
import argparse
import os
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

import config


def _duration(path):
    r = subprocess.run(
        [config.FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def stats_of(path, hdr, n, seg=None, npl=None):
    # npl обязан совпадать с тем, которым кусок будет тонмаплен на сборке:
    # мерить при 400 и рендерить при 250 — значит выравнивать одно, а
    # показывать другое. Пойман 2026-08-24, когда у join_clips появился --npl.
    vf = (config.tonemap(npl) + ",") if hdr else ""
    if seg:
        a, b = seg
        dur = b - a
        pre = ["-ss", "%.3f" % a, "-t", "%.3f" % dur]
    else:
        dur = _duration(path)
        pre = []
    rate = max(n / dur, 0.05) if dur > 0 else 1.0
    vf += "fps=%.4f,scale=480:-2" % rate

    lum, sat, dr, dg, db = [], [], [], [], []
    mr, mg, mb = [], [], []
    with tempfile.TemporaryDirectory() as td:
        cmd = ([config.FFMPEG, "-y", "-hide_banner", "-loglevel", "error"]
               + pre + ["-i", path, "-vf", vf, "-frames:v", str(n),
                        os.path.join(td, "f%03d.png")])
        subprocess.run(cmd, check=True)
        names = sorted(os.listdir(td))
        if not names:
            return None
        for name in names:
            arr = np.asarray(Image.open(os.path.join(td, name)).convert("RGB"),
                             dtype=np.float32) / 255.0
            r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
            luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
            mx, mn = arr.max(axis=2), arr.min(axis=2)
            s = np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
            base = float(luma.mean())
            lum.append(base)
            sat.append(float(s.mean()))
            dr.append(float(r.mean()) - base)
            dg.append(float(g.mean()) - base)
            db.append(float(b.mean()) - base)
            mr.append(float(r.mean()))
            mg.append(float(g.mean()))
            mb.append(float(b.mean()))
    return {
        "яркость": float(np.mean(lum)), "насыщ": float(np.mean(sat)),
        "R": float(np.mean(dr)), "G": float(np.mean(dg)), "B": float(np.mean(db)),
        # абсолютные средние каналов — по ним считается поканальное усиление
        "mR": float(np.mean(mr)), "mG": float(np.mean(mg)), "mB": float(np.mean(mb)),
    }


def main():
    ap = argparse.ArgumentParser(description="Разброс цвета между кусками")
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--hdr", action="store_true")
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--segments", nargs="*", default=None,
                    help="куски одного файла: 0:4.8 4.8:9.3 ...")
    a = ap.parse_args()

    rows = []
    if a.segments:
        path = a.inputs[0]
        for seg in a.segments:
            x, y = seg.split(":")
            r = stats_of(path, a.hdr, a.n, (float(x), float(y)))
            if r:
                rows.append((seg + " с", r))
    else:
        for p in a.inputs:
            r = stats_of(p, a.hdr, a.n)
            if r:
                rows.append((os.path.basename(p), r))

    if not rows:
        sys.exit("нечего мерить")

    print("%-26s %9s %9s %8s %8s %8s" %
          ("кусок", "яркость", "насыщ", "R", "G", "B"))
    for name, r in rows:
        print("%-26s %9.3f %9.3f %+8.3f %+8.3f %+8.3f" %
              (name, r["яркость"], r["насыщ"], r["R"], r["G"], r["B"]))

    print("-" * 72)
    for key in ("яркость", "насыщ", "R", "G", "B"):
        vals = [r[key] for _, r in rows]
        spread = max(vals) - min(vals)
        note = ""
        if key == "яркость" and spread > 0.08:
            note = "  <-- куски разной светлоты, видно на стыке"
        if key in ("R", "G", "B") and spread > 0.030:
            note = "  <-- баланс белого разъехался, это и есть «разный цветокор»"
        print("разброс %-18s %9.3f%s" % (key, spread, note))


if __name__ == "__main__":
    main()
