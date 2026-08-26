#!/usr/bin/env python3
"""Убрать из записи лишнее: посторонний звук, вдох, стук, дед-эйр по краям.

    python audio_fix.py <вход> -o work/voice-clean.wav
        [--duck 10.16:10.47:-40] [--duck 17.80:17.96:-12] ...
        [--trim 0.32:26.16 | --auto-trim] [--fade 0.020]

Шаг СТОИТ ПЕРЕД `audio_polish.py`, и порядок этот не случайный:

  * гасить надо ДО эквалайзера и компрессора. Компрессор, увидев громкий
    вдох, приберёт следом за ним и слова — приберёт ровно там, где вдох
    был. Убрали вдох заранее — компрессор про него не знает;
  * резать дед-эйр надо ДО нормализации громкости: тишина в хвосте не
    меняет LUFS, но меняет длину, а длина у нас — гейт;
  * гасить надо мягко. Резкий край даёт щелчок, который слышно лучше, чем
    то, что убирали. Отсюда `--fade`: склоны косинусом, по умолчанию 20 мс.

⚠️ Что этот модуль НЕ делает: он не решает, что убирать. Места ищет
`audio_find.py`, выбирает Аля. Речь без единого вдоха звучит мёртво
(craft/sound-design) — давят заметные, а не все.

⚠️ Гашение — не вырезание. Кусок остаётся на месте, просто тише: длина не
меняется, тайминги слов и карта катов не едут. Вырезать кусок из середины
речи нельзя, не пересчитав всё остальное.
"""
import argparse
import io
import os
import subprocess
import sys

import numpy as np

import config

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

SR = 48000


def decode(path):
    p = subprocess.run(
        [config.FFMPEG, "-v", "error", "-i", path,
         "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"], capture_output=True)
    if p.returncode != 0:
        sys.exit("ffmpeg не прочитал %s: %s" % (path, p.stderr[-400:]))
    return np.frombuffer(p.stdout, dtype="<i2").astype(np.float64) / 32768.0


def write_wav(x, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    pcm = np.clip(x, -1.0, 1.0)
    p = subprocess.run(
        [config.FFMPEG, "-v", "error", "-y", "-f", "f64le", "-ar", str(SR),
         "-ac", "1", "-i", "-", "-c:a", "pcm_s24le", path],
        input=pcm.astype("<f8").tobytes(), capture_output=True)
    if p.returncode != 0:
        sys.exit("ffmpeg не записал %s: %s" % (path, p.stderr[-400:]))


def rms_db(x, a, b):
    q = x[int(a * SR):int(b * SR)]
    return 20 * np.log10(np.sqrt((q ** 2).mean()) + 1e-12) if len(q) else -120.0


def auto_trim(x, air=0.08, win=0.02):
    """Начало и конец речи по ЭНЕРГИИ, а не по расшифровке.

    Whisper врёт на краях: кладёт первое слово в тишину, а стук по телефону
    в конце принимает за конец фразы. Правило ремесла (craft/subtitles):
    край режется по энергии. Порог берётся от самой записи — на 20 dB ниже
    речи, но не ниже, чем на 12 dB над её же тишиной.
    """
    n = int(len(x) / SR / win)
    lv = np.array([rms_db(x, i * win, (i + 1) * win) for i in range(n)])
    speech = np.percentile(lv, 90)
    floor = np.percentile(lv, 5)
    thr = max(speech - 20, floor + 12)
    on = np.where(lv > thr)[0]
    if not len(on):
        return 0.0, len(x) / SR, thr
    return (max(on[0] * win - air, 0.0),
            min((on[-1] + 1) * win + air, len(x) / SR), thr)


def ramp(x, a, b, gain_db, fade):
    """Приглушить кусок с косинусными склонами. Щелчка не будет."""
    i, j = int(a * SR), int(b * SR)
    i, j = max(i, 0), min(j, len(x))
    if j <= i:
        return
    f = min(int(fade * SR), (j - i) // 2)
    g = 10 ** (gain_db / 20.0)
    env = np.full(j - i, g)
    if f > 0:
        s = (1 - np.cos(np.linspace(0, np.pi, f))) / 2      # 0 -> 1
        env[:f] = 1 + (g - 1) * s
        env[-f:] = g + (1 - g) * s
    x[i:j] *= env


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--duck", action="append", default=[],
                    metavar="НАЧАЛО:КОНЕЦ:dB",
                    help="приглушить кусок, можно много раз")
    ap.add_argument("--trim", default=None, metavar="НАЧАЛО:КОНЕЦ",
                    help="обрезать края, секунды")
    ap.add_argument("--auto-trim", action="store_true",
                    help="найти края речи по энергии и обрезать")
    ap.add_argument("--air", type=float, default=0.08,
                    help="сколько воздуха оставить вокруг речи, с")
    ap.add_argument("--fade", type=float, default=0.020,
                    help="склон гашения, с (по умолч. 20 мс)")
    a = ap.parse_args()

    if not os.path.exists(a.src):
        sys.exit("нет файла: " + a.src)

    x = decode(a.src)
    print("вход: %s — %.2f с" % (a.src, len(x) / SR))

    for spec in a.duck:
        try:
            s, e, g = spec.split(":")
            s, e, g = float(s), float(e), float(g)
        except ValueError:
            sys.exit("не разобрала --duck %s (жду начало:конец:дБ)" % spec)
        was = rms_db(x, s, e)
        ramp(x, s, e, g, a.fade)
        now = rms_db(x, s, e)
        print("  гашу %6.2f-%6.2f на %5.1f dB: было %6.1f -> стало %6.1f"
              % (s, e, g, was, now))

    if a.auto_trim and a.trim:
        sys.exit("--trim и --auto-trim вместе не имеют смысла: выбери одно")

    if a.auto_trim:
        s, e, thr = auto_trim(x, a.air)
        print("  края по энергии (порог %.1f dB): речь %.2f-%.2f" % (thr, s, e))
    elif a.trim:
        try:
            s, e = [float(v) for v in a.trim.split(":")]
        except ValueError:
            sys.exit("не разобрала --trim %s (жду начало:конец)" % a.trim)
    else:
        s, e = 0.0, len(x) / SR

    cut = x[int(s * SR):int(e * SR)]
    print("  обрезано: %.2f с -> %.2f с (снято %.2f с)"
          % (len(x) / SR, len(cut) / SR, len(x) / SR - len(cut) / SR))
    print("  СДВИГ ТАЙМИНГОВ: вычесть %.3f с из времён расшифровки" % s)

    write_wav(cut, a.out)
    print("%s: %.2f с" % (a.out, len(cut) / SR))


if __name__ == "__main__":
    main()
