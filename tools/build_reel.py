#!/usr/bin/env python3
"""Сборка вертикального ролика 1080×1920 (craft/video-station).

    python build_reel.py work/clip.mp4 -o out/reel.mp4 \
        [--audio work/voice.wav] [--subs work/subs.ass] [--hdr] [--fade 0.4]

Жёсткий порядок фильтров, менять нельзя:
    тонмап → кроп/скейл в вертикаль → плашки → субтитры → фейд → экспорт

Почему порядок жёсткий: плашка кладётся на уже-SDR кадр. Тонмапить после
композа нельзя — графитовый navy уходит в мутно-серый. Это код-гейт №3.

Экспорт: crf 22 + потолок 7M — дефолт под живой/пёстрый фон. Без потолка
листва раздувает файл вдвое ни за что.
"""
import argparse, os, subprocess, sys
import config


def esc(p):
    """Путь внутрь фильтра ffmpeg: слэши вперёд, двоеточие диска экранировано."""
    bs = chr(92)
    return p.replace(bs, "/").replace(":", bs + ":").replace("'", bs + "'")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("video")
    ap.add_argument("-o", "--out", default="reel.mp4")
    ap.add_argument("--audio", default=None)
    ap.add_argument("--subs", default=None)
    ap.add_argument("--overlay", default=None, help="PNG плашек на весь кадр")
    ap.add_argument("--hdr", action="store_true", help="исходник HLG/HDR с телефона")
    ap.add_argument("--fade", type=float, default=0.0, help="фейд в конце, с")
    ap.add_argument("--crf", type=int, default=config.CRF)
    a = ap.parse_args()

    if not os.path.exists(a.video):
        sys.exit(f"нет файла: {a.video}")

    vf = []
    if a.hdr:
        vf.append(config.TONEMAP)          # ГЕЙТ: тонмап первым
    vf.append(
        f"scale={config.FRAME_W}:{config.FRAME_H}:force_original_aspect_ratio=increase,"
        f"crop={config.FRAME_W}:{config.FRAME_H},fps={config.FPS}"
    )

    cmd = [config.FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", a.video]
    if a.audio:
        cmd += ["-i", a.audio]
    if a.overlay:
        cmd += ["-i", a.overlay]

    filt = "[0:v]" + ",".join(vf) + "[base]"
    last = "base"
    if a.overlay:
        idx = 2 if a.audio else 1
        filt += f";[{last}][{idx}:v]overlay=0:0[ov]"
        last = "ov"
    if a.subs:
        # fontsdir — libass берёт шрифты из assets/fonts/, ставить в систему не надо
        filt += (f";[{last}]ass='{esc(os.path.abspath(a.subs))}'"
                 f":fontsdir='{esc(config.FONTS)}'[sub]")
        last = "sub"
    if a.fade > 0:
        dur = probe_duration(a.video)
        st = max(0.0, dur - a.fade)
        filt += f";[{last}]fade=t=out:st={st:.3f}:d={a.fade}[fin]"
        last = "fin"

    cmd += ["-filter_complex", filt, "-map", f"[{last}]"]
    cmd += ["-map", "1:a" if a.audio else "0:a?"]
    cmd += [
        "-c:v", "libx264", "-preset", config.X264_PRESET, "-crf", str(a.crf),
        "-maxrate", config.MAXRATE, "-bufsize", config.BUFSIZE,
        "-pix_fmt", "yuv420p", "-r", str(config.FPS),
        "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-ar", "48000",
        "-movflags", "+faststart", a.out,
    ]
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    subprocess.run(cmd, check=True)
    print(f"{a.out}: собран. Дальше обязательно qa.py — гейты не пропускать.")


def probe_duration(path):
    r = subprocess.run(
        [config.FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


if __name__ == "__main__":
    main()
