#!/usr/bin/env python3
"""Сделать фоновую подложку своими руками — синтезом, без чужих треков.

    python music_make.py --mood calm --dur 32 -o assets/music/calm-day.wav
    python music_make.py --list

Зачем это есть. Музыку в ролик до 2026-08-25 не вшивали вовсе: решение
владельца было брать трек в самой площадке при выкладке. Владелец это
решение отменил для выпуска «день основателя» — попросил тихую фоновую
музыку прямо в файле. Скачивать чужое нельзя (страйк, аккаунты, деньги),
значит подложка делается так же, как SFX: **синтезом**.

Что синтез здесь делает честно: спокойный гармонический пэд без ударных —
это ровно тот случай, когда своё звучит не хуже стокового, потому что
слушателю нужен фон, а не мелодия. Прав на такую подложку нет ни у кого.

Чего синтезом НЕ сделать: живой инструмент, узнаваемую мелодию, трек с
вокалом. За этим — в библиотеку площадки, и это по-прежнему нормальный
путь для роликов, где музыка ведёт.

**Ударных нет намеренно.** Резать под доли всё равно нельзя: монтаж этого
выпуска идёт под речь, а не под музыку. Пэд без ритма не спорит с речью и
не заставляет монтаж попадать в сетку, которой нет.

Уровень: пик −6 dBFS, запас под сведение. Дальше music_bed.py ставит её
на −16 dB под голосом (craft/sound-design §Слой 4).
"""
import argparse
import os
import wave

import numpy as np

import config

SR = 48000
PEAK = 10 ** (-6 / 20)

# Ноты, которые нужны прогрессиям (равномерный строй, A4 = 440)
NOTE = {
    "C2": 65.41, "D2": 73.42, "E2": 82.41, "F2": 87.31, "G2": 98.00, "A2": 110.00,
    "C3": 130.81, "D3": 146.83, "E3": 164.81, "F3": 174.61, "G3": 196.00,
    "A3": 220.00, "B3": 246.94,
    "C4": 261.63, "D4": 293.66, "E4": 329.63, "F4": 349.23, "G4": 392.00,
    "A4": 440.00, "B4": 493.88,
    "C5": 523.25, "D5": 587.33, "E5": 659.25, "G5": 784.00,
}

# Настроения. Аккорд — (бас, [ноты пэда]).
# calm: Am7 - Fmaj7 - Cmaj7 - G6. Тёплая нейтральная петля: не грустная и
# не бодрая, под разговор о работе — то, что нужно фону.
MOODS = {
    "calm": {
        "human": "спокойный день, тёплый и нейтральный",
        "chords": [
            ("A2", ["A3", "C4", "E4", "G4"]),
            ("F2", ["A3", "C4", "F4", "E5"]),
            ("C3", ["C4", "E4", "G4", "B4"]),
            ("G2", ["B3", "D4", "G4", "E5"]),
        ],
        "cutoff": 1800.0,
    },
    "focus": {
        "human": "собранный, чуть строже — под перечисление и процесс",
        "chords": [
            ("D2", ["D4", "F4", "A4", "C5"]),
            ("A2", ["C4", "E4", "A4", "G5"]),
            ("F2", ["C4", "F4", "A4", "C5"]),
            ("G2", ["D4", "G4", "B4", "D5"]),
        ],
        "cutoff": 2200.0,
    },
    "warm": {
        "human": "мягкий и светлый, почти без движения",
        "chords": [
            ("C3", ["E4", "G4", "C5"]),
            ("G2", ["D4", "G4", "B4"]),
            ("A2", ["E4", "A4", "C5"]),
            ("F2", ["C4", "F4", "A4"]),
        ],
        "cutoff": 1500.0,
    },
}


def osc(freq, n, detune=0.0015):
    """Мягкий голос пэда: основа плюс две тихие гармоники, слегка расстроенные.

    Расстройка нужна, чтобы звук не был «пищалкой из девяностых»: две копии,
    разведённые на полторы тысячных, дают медленное биение и ощущение живого
    инструмента. Гармоники падают быстро (0.35 и 0.15) — иначе пэд лезет в
    полосу речи, а он должен под ней лежать.
    """
    t = np.arange(n) / SR
    out = np.zeros(n)
    for mult, amp in ((1.0, 1.0), (2.0, 0.35), (3.0, 0.15)):
        for d in (1.0 - detune, 1.0 + detune):
            phase = 2 * np.pi * freq * mult * d * t
            out += amp * np.sin(phase) / 2.0
    return out


def lowpass(x, cutoff):
    """Однополюсный фильтр: снимает верх, оставляет тепло.

    Одного полюса достаточно — задача не «отрезать», а «убрать стекло».
    Крутой фильтр на пэде слышен как «накрыли подушкой».
    """
    a = np.exp(-2 * np.pi * cutoff / SR)
    out = np.empty_like(x)
    y = 0.0
    for i, v in enumerate(x):
        y = (1 - a) * v + a * y
        out[i] = y
    return out


def env(n, attack, release):
    """Огибающая аккорда: медленный вход, плато, медленный уход."""
    a = min(int(SR * attack), n // 2)
    r = min(int(SR * release), n // 2)
    s = max(0, n - a - r)
    return np.concatenate([
        np.linspace(0, 1, a) ** 1.6,
        np.ones(s),
        np.linspace(1, 0, r) ** 1.4,
    ])[:n]


def build(mood, dur, bars=None):
    spec = MOODS[mood]
    chords = spec["chords"]
    bars = bars or len(chords)
    # аккорды перекрываются: следующий входит, пока предыдущий уходит —
    # иначе на стыке слышна дырка
    overlap = 1.2
    step = dur / bars
    seg = step + overlap

    total = int(SR * (dur + overlap + 0.5))
    mix = np.zeros(total)

    for i in range(bars):
        bass_name, notes = chords[i % len(chords)]
        n = int(SR * seg)
        e = env(n, attack=1.1, release=1.4)

        chord = np.zeros(n)
        for k, name in enumerate(notes):
            # верхние ноты тише нижних: так аккорд звучит как один инструмент,
            # а не как четыре отдельных писка
            amp = 1.0 / (1.0 + 0.55 * k)
            chord += amp * osc(NOTE[name], n)
        chord = lowpass(chord, spec["cutoff"]) * e

        bass = osc(NOTE[bass_name], n, detune=0.0008)
        bass = lowpass(bass, 320.0) * e * 0.85

        start = int(SR * step * i)
        mix[start:start + n] += chord * 0.5 + bass * 0.5

    # «воздух»: очень тихий отфильтрованный шум. Он не слышен отдельно, но
    # без него пэд звучит стерильно — синтетика выдаёт себя именно тишиной
    # между гармониками.
    rng = np.random.default_rng(7)
    air = lowpass(rng.standard_normal(total), 900.0)
    air = air / (np.max(np.abs(air)) or 1.0)
    mix += air * 0.02

    mix = mix[:int(SR * dur)]
    # мягкий вход и выход всего куска
    f = int(SR * 1.5)
    mix[:f] *= np.linspace(0, 1, f) ** 1.5
    mix[-f:] *= np.linspace(1, 0, f) ** 1.5

    peak = np.max(np.abs(mix)) or 1.0
    return mix / peak * PEAK


def write(path, mono):
    """Стерео с лёгким расхождением каналов — фон дышит шире голоса.

    Голос стоит по центру и остаётся там; подложка чуть разведена, чтобы не
    сидеть с ним в одной точке. Разведение крошечное (задержка 12 мс на
    правом), в моно оно складывается без провала — проверять обязательно
    именно в моно (craft/sound-design).
    """
    d = int(SR * 0.012)
    left = mono
    right = np.concatenate([np.zeros(d), mono])[:len(mono)]
    stereo = np.stack([left, right], axis=1)
    data = (np.clip(stereo, -1, 1) * 32767).astype("<i2")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mood", choices=sorted(MOODS), default="calm")
    ap.add_argument("--dur", type=float, default=32.0)
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    if a.list:
        for name in sorted(MOODS):
            print("%-8s %s" % (name, MOODS[name]["human"]))
        return

    out = a.out or os.path.join(config.REPO, "assets", "music",
                                "%s-%ds.wav" % (a.mood, int(a.dur)))
    write(out, build(a.mood, a.dur))
    print("%s: %s, %.1f с, пик −6 dBFS, стерео %d Гц"
          % (out, MOODS[a.mood]["human"], a.dur, SR))
    print("Права: сгенерировано нами, чужого материала нет — страйк невозможен.")
    print("Дальше music_bed.py: подложка ставится на −16 dB под голосом.")


if __name__ == "__main__":
    main()
