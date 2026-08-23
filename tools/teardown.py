#!/usr/bin/env python3
"""Замеры чужого ролика для разбора — числа вместо впечатлений.

    python teardown.py <файл-или-папка> [--scene 0.30]

Даёт то, что глазом не увидишь: длительность, кадр, частоту, громкость и
LRA, список склеек по секундам и среднюю длину плана. Дальше разбор идёт
по alya-vault/operations/razobrat-rolik.md.

Порог сцены 0.30 ловит жёсткие каты. Плавные переходы он пропускает — это
не баг: нам и нужны жёсткие, мягкие в нашем жанре не используются.
"""
import argparse, json, re, subprocess, sys
import config


def probe(path):
    r = subprocess.run(
        [config.FFPROBE, "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", path],
        capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def loudness(path):
    r = subprocess.run(
        [config.FFMPEG, "-hide_banner", "-nostats", "-i", path,
         "-af", "loudnorm=print_format=json", "-f", "null", "-"],
        capture_output=True, text=True)
    def grab(k):
        m = re.findall(r'"%s"\s*:\s*"(-?[\d.]+)"' % k, r.stderr)
        return float(m[-1]) if m else None
    return grab("input_i"), grab("input_lra")


def cuts(path, thr):
    r = subprocess.run(
        [config.FFMPEG, "-hide_banner", "-nostats", "-i", path,
         "-filter:v", f"select='gt(scene,{thr})',showinfo",
         "-f", "null", "-"],
        capture_output=True, text=True)
    return [round(float(t), 2)
            for t in re.findall(r"pts_time:([\d.]+)", r.stderr)]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src")
    ap.add_argument("--scene", type=float, default=0.30)
    a = ap.parse_args()

    info = probe(a.src)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    au = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    dur = float(info["format"]["duration"])

    print(f"длительность   {dur:.2f} с")
    if v:
        num, den = (v.get("r_frame_rate", "0/1").split("/") + ["1"])[:2]
        fps = float(num) / float(den or 1)
        print(f"кадр           {v['width']}×{v['height']} @ {fps:.0f}")
    if au:
        i, lra = loudness(a.src)
        ch = {1: "моно", 2: "стерео"}.get(int(au.get("channels", 0)), au.get("channels"))
        print(f"звук           {ch}, {i} LUFS, LRA {lra}")
        if i is not None and i > -13:
            print("               ! громче нашей нормы −16: плотный вещательный звук")
    c = cuts(a.src, a.scene)
    print(f"склеек         {len(c)}")
    if c:
        planes = [round(b - x, 2) for x, b in zip([0.0] + c, c + [dur])]
        avg = sum(planes) / len(planes)
        print(f"средний план   {avg:.2f} с   (наша норма — смена каждые 1.5–3 с)")
        print(f"первая склейка {c[0]:.2f} с   (наш хук — до 1.5 с)")
        print("склейки, с:    " + ", ".join(str(x) for x in c[:40])
              + (" …" if len(c) > 40 else ""))
    print("\nЧисла сняты. Приём словами — по операции razobrat-rolik.")


if __name__ == "__main__":
    main()
