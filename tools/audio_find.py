#!/usr/bin/env python3
"""Поиск мусора в записи голоса: посторонние сигналы и вдохи.

    python audio_find.py <аудио> --words work/words.json [--json work/events.json]

Зачем отдельный инструмент. Владелец слышит «уведомление на фоне» и «вдохи»,
но секунду назвать не может. Искать глазами по спектрограмме — час работы и
половина находок: короткий тихий сигнал на общей картинке просто не виден,
автояркость его съедает.

Машина ищет по двум разным признакам, и признаки эти противоположные.

  ПОСТОРОННИЙ СИГНАЛ (уведомление, писк, будильник) — это **стоячая
  частота**. Голос тоже даёт узкие линии — гармоники, — но они всё время
  плывут вместе с интонацией. Сигнал телефона стоит намертво: за четверть
  секунды частота гуляет на единицы герц. Поэтому ловим не «узкую линию», а
  «узкую линию, которая не дрожит», и только там, где голоса нет.

  ВДОХ — наоборот, широкий шум без всякой частоты. Живёт в паузе между
  словами, звенит в 1.5-6 кГц, звонких колебаний связок в нём нет.
  Отличаем от шипящих «с» и «ш» тем, что ищем ТОЛЬКО вне слов: шипящая
  внутри слова — часть речи, её не трогают.

Паузы берутся из расшифровки (`words.json`). Без неё инструмент ищет паузы
сам по энергии — грубее, но работает.

⚠️ Инструмент НЕ решает, что убирать. Он показывает, где смотреть. Речь без
единого вдоха звучит мёртво (craft/sound-design) — давят заметные, а не все.
"""
import argparse
import io
import json
import os
import subprocess
import sys

import numpy as np

import config

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

SR = 48000
NFFT = 8192      # 5.9 Гц по частоте — чтобы отличить стоячий тон от плывущего
HOP = 256        # 5.3 мс по времени — чтобы поймать короткий вдох
BG_WIDTH = 400   # Гц, окно скользящей медианы: «фон» на этой частоте


def decode(path):
    """Файл -> моно float32 48 кГц. Сырьё не трогаем, только читаем."""
    p = subprocess.run(
        [config.FFMPEG, "-v", "error", "-i", path,
         "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"], capture_output=True)
    if p.returncode != 0:
        sys.exit("ffmpeg не прочитал %s: %s" % (path, p.stderr[-400:]))
    return np.frombuffer(p.stdout, dtype="<i2").astype(np.float32) / 32768.0


def stft(x):
    win = np.hanning(NFFT).astype(np.float32)
    n = 1 + (len(x) - NFFT) // HOP
    fr = np.lib.stride_tricks.as_strided(
        x, shape=(n, NFFT), strides=(x.strides[0] * HOP, x.strides[0])).copy()
    fr *= win
    mag = np.abs(np.fft.rfft(fr, axis=1)) + 1e-12
    return mag, np.fft.rfftfreq(NFFT, 1.0 / SR)


def band(mag, freqs, lo, hi):
    s = (freqs >= lo) & (freqs < hi)
    return 20 * np.log10(np.sqrt((mag[:, s] ** 2).mean(axis=1)) + 1e-12)


def excess(mag, freqs, lo, hi):
    """Спектр минус свой же скользящий фон: видно только то, что торчит."""
    a, b = np.searchsorted(freqs, lo), np.searchsorted(freqs, hi)
    sub = 20 * np.log10(mag[:, a:b])
    w = int(BG_WIDTH / (freqs[1] - freqs[0])) // 2 * 2 + 1
    pad = np.pad(sub, ((0, 0), (w // 2, w // 2)), mode="edge")
    bg = np.median(np.lib.stride_tricks.sliding_window_view(pad, w, axis=1), axis=2)
    return sub - bg, freqs[a:b]


def runs(mask, min_len):
    out, i, n = [], 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            if j - i >= min_len:
                out.append((i, j))
            i = j
        else:
            i += 1
    return out


def word_gaps(words, dur, edge=0.04, min_gap=0.10):
    """Промежутки между словами. Внутри слова не ищем — там речь."""
    g, prev = [], 0.0
    for w in sorted(words, key=lambda w: w["s"]):
        if w["s"] - prev > min_gap:
            g.append((prev + edge, w["s"] - edge))
        prev = max(prev, w["e"])
    if dur - prev > min_gap:
        g.append((prev + edge, dur))
    return g


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("--words", default=None)
    ap.add_argument("--tone-min", type=float, default=0.10,
                    help="сколько тон должен держаться, с (по умолч. 0.10)")
    ap.add_argument("--tone-jitter", type=float, default=15.0,
                    help="сколько тону позволено дрожать, Гц (по умолч. 15)")
    ap.add_argument("--breath-over", type=float, default=8.0,
                    help="насколько вдох громче фона паузы, dB (по умолч. 8)")
    ap.add_argument("--json", default=None)
    a = ap.parse_args()

    if not os.path.exists(a.src):
        sys.exit("нет файла: " + a.src)

    x = decode(a.src)
    dur = len(x) / SR
    mag, freqs = stft(x)
    t = np.arange(mag.shape[0]) * HOP / SR + NFFT / (2.0 * SR)
    hop_s = HOP / SR

    full = band(mag, freqs, 60, 20000)
    hiss = band(mag, freqs, 1500, 6000)
    floor = float(np.percentile(full, 5))
    speech = float(np.percentile(full, 85))

    print("файл: %s" % a.src)
    print("длительность %.2f с · фон %.1f dB · речь %.1f dB · запас %.1f dB"
          % (dur, floor, speech, speech - floor))

    if a.words and os.path.exists(a.words):
        gaps = word_gaps(json.load(open(a.words, encoding="utf-8"))["words"], dur)
        how = "по расшифровке"
    else:
        quiet = full < (floor + speech) / 2
        gaps = [(i * hop_s, j * hop_s) for i, j in runs(quiet, int(0.10 / hop_s))]
        how = "по энергии"
    print("паузы (%s): %d штук, суммарно %.2f с"
          % (how, len(gaps), sum(b - c for c, b in gaps)))

    in_gap = np.zeros(len(t), bool)
    for g0, g1 in gaps:
        in_gap |= (t >= g0) & (t < g1)

    ex, fs = excess(mag, freqs, 400, 9000)
    events = []

    # ── стоячая частота в паузе = посторонний сигнал ──────────────────────
    min_fr = int(a.tone_min / hop_s)
    strong = ex > 12
    cand = in_gap & strong.any(axis=1)
    for i, j in runs(cand, min_fr):
        prof = ex[i:j]
        pf = fs[prof.argmax(axis=1)]
        # частот может быть две сразу («ди-дон»): разбираем каждую отдельно,
        # но одну и ту же не считаем дважды — уже разобранное вычёркиваем.
        left = np.ones(len(pf), bool)
        while left.sum() >= min_fr:
            f0 = float(np.median(pf[left]))
            sel = left & (np.abs(pf - f0) < 60)
            if not sel.any():   # медиана легла между двумя тонами — берём ближний
                near = np.where(left)[0][np.abs(pf[left] - f0).argmin()]
                sel = left & (np.abs(pf - pf[near]) < 60)
            left = left & ~sel
            if sel.sum() < min_fr:
                continue
            got = pf[sel]
            if got.std() > a.tone_jitter:
                continue          # частота дрожит — это голос, не сигнал
            k = np.searchsorted(fs, got.mean())
            lvl = 20 * np.log10(mag[i:j, np.searchsorted(freqs, got.mean())].max())
            events.append({
                "тип": "сигнал",
                "с": round(float(t[i]), 3), "по": round(float(t[j - 1]), 3),
                "длит": round(float(t[j - 1] - t[i]), 3),
                "частота": int(round(float(got.mean()))),
                "дрожь": round(float(got.std()), 1),
                "над_фоном": round(float(prof[sel][:, max(k - 3, 0):k + 3].max()), 1),
                "уровень": round(float(lvl), 1),
            })

    # ── широкий шум в паузе без стоячей частоты = вдох ────────────────────
    gap_floor = float(np.percentile(hiss[in_gap], 20)) if in_gap.any() else floor
    br = in_gap & (hiss > gap_floor + a.breath_over) & (ex.max(axis=1) < 18)
    for i, j in runs(br, int(0.06 / hop_s)):
        events.append({
            "тип": "вдох",
            "с": round(float(t[i]), 3), "по": round(float(t[j - 1]), 3),
            "длит": round(float(t[j - 1] - t[i]), 3),
            "над_фоном": round(float(hiss[i:j].max() - gap_floor), 1),
            "уровень": round(float(full[i:j].max()), 1),
            "тише_речи": round(float(speech - full[i:j].max()), 1),
        })

    events.sort(key=lambda e: e["с"])
    print()
    if not events:
        print("ничего не нашла — ни стоячих частот, ни вдохов выше порога")
    for e in events:
        if e["тип"] == "сигнал":
            print("%6.2f-%6.2f  СИГНАЛ  %5d Гц  дрожь ±%.1f Гц  над фоном %4.1f dB"
                  % (e["с"], e["по"], e["частота"], e["дрожь"], e["над_фоном"]))
        else:
            print("%6.2f-%6.2f  вдох    %.2f с  над фоном паузы %4.1f dB  "
                  "тише речи на %4.1f dB"
                  % (e["с"], e["по"], e["длит"], e["над_фоном"], e["тише_речи"]))

    print("\nитого: сигналов %d · вдохов %d"
          % (sum(1 for e in events if e["тип"] == "сигнал"),
             sum(1 for e in events if e["тип"] == "вдох")))

    if a.json:
        os.makedirs(os.path.dirname(os.path.abspath(a.json)), exist_ok=True)
        json.dump({"src": os.path.abspath(a.src), "duration": round(dur, 3),
                   "floor": round(floor, 1), "speech": round(speech, 1),
                   "events": events}, open(a.json, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print("%s: %d событий" % (a.json, len(events)))


if __name__ == "__main__":
    main()
