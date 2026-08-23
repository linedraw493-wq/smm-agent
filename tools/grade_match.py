#!/usr/bin/env python3
"""Грейд по референс-фотографии — числами, а не на глаз.

    python grade_match.py --ref raw/photo.jpg --src raw/01.mp4 raw/02.mp4 \
        --hdr -o work/grade.json

Что делает. Снимает статистику с фотографии-референса и с кадров исходника,
считает разницу и выдаёт цепочку фильтров ffmpeg, которая двигает исходник
к референсу. Ничего не выдумывает: каждое число — измеренная величина.

ПОЧЕМУ КАДРЫ БЕРУТСЯ ПОСЛЕ ТОНМАПА. Грейд в сборке стоит после тонмапа и
кадрирования (craft/video-station). Мерить сырой HDR и применять результат к
SDR — мерить одно, а править другое. Поэтому при --hdr кадры вынимаются той
же цепочкой config.TONEMAP, что и в сборке.

Что считается:
  * насыщенность — средняя S в HSV;
  * контраст — СКО яркости;
  * гамма — по средней яркости;
  * цветовой сдвиг по трём зонам (тени / средние / света) — colorbalance.

Границы зажаты намеренно: замер на нетипичном кадре не должен выкручивать
картинку в неузнаваемое. Упёрлось в границу — модуль об этом говорит вслух.
"""
import argparse
import json
import math
import os
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

import config

# Потолки. Грейд — сближение, а не перекраска: за этими границами
# «как на фото» превращается в «не узнать исходник».
SAT_RANGE = (0.60, 1.80)
CON_RANGE = (0.70, 1.55)
GAM_RANGE = (0.70, 1.45)
CB_LIMIT = 0.30          # colorbalance по каналу, |сдвиг|
BANDS = ((0.00, 0.35), (0.35, 0.70), (0.70, 1.00))   # тени / средние / света
BAND_NAMES = ("тени", "средние", "света")


def stats(arr):
    """arr — float32 RGB 0..1, HxWx3. Возвращает мерки картинки."""
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    luma = 0.2126 * r + 0.7152 * g + 0.0722 * b

    mx, mn = arr.max(axis=2), arr.min(axis=2)
    sat = np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0.0)

    out = {
        "luma_mean": float(luma.mean()),
        "luma_std": float(luma.std()),
        "sat_mean": float(sat.mean()),
        "bands": [],
    }
    for lo, hi in BANDS:
        m = (luma >= lo) & (luma < hi)
        if m.sum() < 64:                      # зона пустая — не выдумываем сдвиг
            out["bands"].append(None)
            continue
        # отклонение канала от серого внутри зоны: это и есть «оттенок» зоны
        base = float(luma[m].mean())
        out["bands"].append([float(r[m].mean()) - base,
                             float(g[m].mean()) - base,
                             float(b[m].mean()) - base])
    return out


def load_image(path, long_side=720):
    im = Image.open(path).convert("RGB")
    im.thumbnail((long_side, long_side))
    return np.asarray(im, dtype=np.float32) / 255.0


def probe_duration(path):
    r = subprocess.run(
        [config.FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def sample_video(path, hdr, n=6):
    """n кадров из видео, при hdr — уже тонмапленных."""
    vf = (config.TONEMAP + ",") if hdr else ""
    vf += "scale=640:-2"
    frames = []
    with tempfile.TemporaryDirectory() as td:
        pat = os.path.join(td, "f%03d.png")
        # частота подбирается под длину: n кадров равномерно по всему клипу
        dur = probe_duration(path)
        rate = max(n / dur, 0.05) if dur > 0 else 1.0
        cmd = [config.FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
               "-i", path, "-vf", vf + (",fps=%.4f" % rate),
               "-frames:v", str(n), pat]
        subprocess.run(cmd, check=True)
        for name in sorted(os.listdir(td)):
            frames.append(load_image(os.path.join(td, name)))
    if not frames:
        sys.exit("не удалось вынуть кадры из " + path)
    return frames


def merge(list_of_stats):
    """Средние мерки по всем кадрам всех клипов."""
    out = {k: float(np.mean([s[k] for s in list_of_stats]))
           for k in ("luma_mean", "luma_std", "sat_mean")}
    bands = []
    for i in range(len(BANDS)):
        vals = [s["bands"][i] for s in list_of_stats if s["bands"][i] is not None]
        bands.append([float(x) for x in np.mean(vals, axis=0)] if vals else None)
    out["bands"] = bands
    return out


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def build(ref, src):
    """Разница ref−src → параметры фильтров. Возвращает (цепочка, отчёт)."""
    notes = []

    def note_if_clamped(name, raw, lo, hi):
        if raw < lo or raw > hi:
            notes.append("%s: замер дал %.2f, зажато в %.2f..%.2f" % (name, raw, lo, hi))

    raw_sat = ref["sat_mean"] / max(src["sat_mean"], 1e-4)
    note_if_clamped("насыщенность", raw_sat, *SAT_RANGE)
    sat = clamp(raw_sat, *SAT_RANGE)

    raw_con = ref["luma_std"] / max(src["luma_std"], 1e-4)
    note_if_clamped("контраст", raw_con, *CON_RANGE)
    con = clamp(raw_con, *CON_RANGE)

    # gamma: хотим src_mean^(1/g) == ref_mean
    sm = clamp(src["luma_mean"], 1e-3, 0.999)
    rm = clamp(ref["luma_mean"], 1e-3, 0.999)
    raw_gam = math.log(sm) / math.log(rm)
    note_if_clamped("гамма", raw_gam, *GAM_RANGE)
    gam = clamp(raw_gam, *GAM_RANGE)

    cb, report_bands = {}, []
    for i, key in enumerate(("s", "m", "h")):
        rb, sb = ref["bands"][i], src["bands"][i]
        if rb is None or sb is None:
            report_bands.append("%s: зона пуста, сдвиг не считаю" % BAND_NAMES[i])
            for ch in "rgb":
                cb[ch + key] = 0.0
            continue
        deltas = []
        for j, ch in enumerate("rgb"):
            d = clamp(rb[j] - sb[j], -CB_LIMIT, CB_LIMIT)
            cb[ch + key] = round(d, 4)
            deltas.append(d)
        report_bands.append("%s: R%+.3f G%+.3f B%+.3f"
                            % (BAND_NAMES[i], deltas[0], deltas[1], deltas[2]))

    cb_str = ":".join("%s=%s" % (k, v) for k, v in cb.items() if abs(v) >= 0.001)
    chain = []
    if cb_str:
        chain.append("colorbalance=" + cb_str)
    chain.append("eq=saturation=%.3f:contrast=%.3f:gamma=%.3f" % (sat, con, gam))
    # резкость — из канона rich, только по яркости (по цвету полезут каёмки)
    chain.append("unsharp=luma_msize_x=5:luma_msize_y=5:luma_amount=0.7:chroma_amount=0")

    report = {
        "saturation": round(sat, 3), "contrast": round(con, 3), "gamma": round(gam, 3),
        "colorbalance": cb, "bands_human": report_bands, "notes": notes,
        "ref_stats": ref, "src_stats": src,
    }
    return ",".join(chain), report


def main():
    ap = argparse.ArgumentParser(description="Грейд по референс-фотографии")
    ap.add_argument("--ref", required=True, help="фотография-референс")
    ap.add_argument("--src", nargs="+", required=True, help="исходные видео")
    ap.add_argument("--hdr", action="store_true", help="исходник HDR — мерить после тонмапа")
    ap.add_argument("-o", "--out", default=None, help="куда положить grade.json")
    a = ap.parse_args()

    ref = stats(load_image(a.ref))
    src = merge([stats(f) for p in a.src for f in sample_video(p, a.hdr)])
    chain, report = build(ref, src)
    report["chain"] = chain

    print("--- референс ---")
    print("  яркость %.3f · контраст(СКО) %.3f · насыщенность %.3f"
          % (ref["luma_mean"], ref["luma_std"], ref["sat_mean"]))
    print("--- исходник (%s) ---" % ("после тонмапа" if a.hdr else "как есть"))
    print("  яркость %.3f · контраст(СКО) %.3f · насыщенность %.3f"
          % (src["luma_mean"], src["luma_std"], src["sat_mean"]))
    print("--- правка ---")
    print("  насыщенность x%.3f · контраст x%.3f · гамма %.3f"
          % (report["saturation"], report["contrast"], report["gamma"]))
    for line in report["bands_human"]:
        print("  " + line)
    for n in report["notes"]:
        print("  ! " + n)
    print("")
    print(chain)

    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print("\nотчёт: " + a.out)


if __name__ == "__main__":
    main()
