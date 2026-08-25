#!/usr/bin/env python3
"""Полная обработка голоса: чистка, эквализация, де-эссер, пространство.

    python audio_polish.py <вход> -o work/voice.wav
        [--profile clean|phone|damaged] [--space none|room|hall]
        [--rnnoise models/bd.rnnn] [--lufs -16] [--dry]

Порядок жёсткий и он не случайный:

    хайпасс -> шумодав -> де-мут -> присутствие -> де-харш -> де-эссер
    -> воздух -> компрессор -> ПРОСТРАНСТВО -> стерео -> loudnorm

Почему так:
  * шумодав ДО эквалайзера — иначе поднятое присутствие поднимет и шип;
  * компрессор ПОСЛЕ эквалайзера — он должен ровнять уже готовый тембр;
  * пространство ПОСЛЕ компрессора — иначе компрессор задавит хвост и
    комната будет «дышать»;
  * loudnorm ВСЕГДА последним — любая обработка после него ломает громкость.

Цифры не выдуманы: подобраны замером под тембр референса (alya-vault/craft/audio.md).
Границы, за которые не заходить: шумодав mix=1.0 даёт «водянистый» голос,
nr=10 — металлический звон, -14 LUFS с узким LRA поднимает артефакты.

--dry печатает цепочку и ничего не делает. Полезно, когда надо понять,
что именно сейчас сделается с голосом.
"""
import argparse
import os
import subprocess
import sys

import config

# профиль источника -> чистка. Чем хуже источник, тем осторожнее, а не наоборот:
# на убитой записи агрессивная чистка слышна сильнее самого шума.
DENOISE = {
    "clean":   "afftdn=nr=6",
    "phone":   "afftdn=nr=7",
    "damaged": "anlmdn=s=0.0004,afftdn=nr=8",
}

# эквализация под тембр референса: убрать муть, вернуть присутствие и воздух
EQ = (
    "equalizer=f=450:t=q:w=1.2:g=-2.5,"     # де-мут: «в бочке» -> открыто
    "equalizer=f=4200:t=q:w=1.0:g=3.5,"     # присутствие: слова вперёд
    "equalizer=f=6800:t=q:w=1.4:g=-1.5,"    # де-харш: снять резкость
    "treble=f=9000:g=4"                     # воздух: голос перестаёт быть глухим
)

# де-эссер: динамический, работает только когда шипящая реально пришла.
# Статическим эквалайзером сибилянты не лечат — он глушит их всегда,
# и голос становится шепелявым.
DEESS = ("adynamicequalizer=dfrequency=7000:dqfactor=2:tfrequency=7000:tqfactor=2"
         ":threshold=0.06:ratio=4:range=12:attack=1:release=50:mode=cutabove")

# пространство. Короткое и тихое: голос должен стоять в комнате, а не в зале.
# Проверять обязательно в наушниках И в моно — площадка может сложить каналы.
SPACE = {
    "none": None,
    "room": "aecho=0.9:0.75:23|31:0.055|0.035",
    "hall": "aecho=0.85:0.75:47|71:0.11|0.075",
}


def build(profile, space, rnnoise, lufs, bass=0.0, headroom=0.0, comp=2.6):
    chain = []

    # Запас на входе. Запись с телефона часто приходит с пиками у самого нуля
    # (интерсэмпл-пики выше 0 dBTP — обычное дело у AAC). Фильтры, работающие
    # в зашкале, добавляют грязь, а подъём низа — сильнее всего. Понижение
    # НЕ восстанавливает уже срезанное в записи, оно только не усугубляет.
    if headroom:
        chain.append("volume=%.2fdB" % -abs(headroom))

    chain.append("highpass=f=85")

    if rnnoise and os.path.exists(rnnoise):
        bs = chr(92)
        m = rnnoise.replace(bs, "/").replace(":", bs + ":")
        chain.append("arnndn=m=%s:mix=0.85" % m)
    else:
        chain.append(DENOISE[profile])

    chain.append(EQ)

    # «Больше низа» — узко и с оглядкой. Широкий подъём 80-200 Гц даёт не
    # плотность, а бубнёж: полоса 200-500 («муть») лезет вперёд и голос
    # закрывается. Поэтому грудь поднимается узко около 110 Гц, а муть в
    # 300 Гц одновременно подрезается — тогда низ читается как опора, а не
    # как гул. Мерить до и после — audio_report.py, полоса «низ 80-200»
    # относительно «тело 500-2k».
    if bass:
        chain.append("equalizer=f=110:t=q:w=0.9:g=%.2f" % bass)
        chain.append("equalizer=f=300:t=q:w=1.1:g=%.2f" % (-0.6 * bass))
    chain.append(DEESS)

    # Компрессор — не бесплатный. На записи, которую телефон уже придавил
    # автогромкостью (LRA меньше ~3), ещё один слой сжатия не «усаживает
    # плотнее», а душит: речь теряет остатки динамики и звучит как диктор
    # автоответчика. Замер 2026-08-25 на этом выпуске: LRA записи 2.8, после
    # дефолтного ratio 2.6 стало 1.5 при коридоре референсов 2.0-3.1.
    # Поэтому степень сжатия — параметр, а не константа; 0 выключает совсем.
    if comp > 0:
        chain.append("acompressor=threshold=-20dB:ratio=%.2f:attack=8"
                     ":release=180:makeup=%.2f" % (comp, 1.0 + 0.6 * (comp - 1.0)))

    if SPACE[space]:
        chain.append(SPACE[space])

    # голос остаётся по центру: разводим моно в оба канала, а не расширяем.
    # Расширение стерео на голосе разваливается, когда площадка сложит в моно.
    chain.append("pan=stereo|c0=c0|c1=c0")
    chain.append("alimiter=limit=0.97")
    chain.append("loudnorm=I=%s:TP=%s:LRA=%s" % (lufs, config.TRUE_PEAK, config.LRA))
    return ",".join(chain)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src", nargs="?")
    ap.add_argument("-o", "--out", default="voice.wav")
    ap.add_argument("--profile", choices=sorted(DENOISE), default="phone")
    ap.add_argument("--space", choices=sorted(SPACE), default="room")
    ap.add_argument("--rnnoise", default=None)
    ap.add_argument("--lufs", type=float, default=config.LUFS_TARGET)
    ap.add_argument("--bass", type=float, default=0.0,
                    help="подъём груди голоса на 110 Гц, dB (узко, Q=0.9); "
                         "одновременно подрезает муть 300 Гц на 0.6 от этого "
                         "числа. Выше 3 dB на телефонной записи — бубнёж")
    ap.add_argument("--headroom", type=float, default=0.0,
                    help="понизить вход на N dB перед обработкой: нужно, если "
                         "true peak записи у нуля или выше")
    ap.add_argument("--comp", type=float, default=2.6,
                    help="степень сжатия (ratio). 0 — без компрессора. На "
                         "записи с LRA меньше 3 ставить 1.4-1.8, иначе речь "
                         "душится: замер 2026-08-25 дал LRA 1.5 при 2.6")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    if a.bass > 3.0:
        print("! --bass %.1f dB: выше 3 dB на моно-записи с телефона даёт "
              "бубнёж, а не плотность (craft/audio)" % a.bass, file=sys.stderr)

    chain = build(a.profile, a.space, a.rnnoise, a.lufs, a.bass, a.headroom,
                  a.comp)

    if a.dry:
        print("профиль %s, пространство %s, цель %s LUFS\n" % (a.profile, a.space, a.lufs))
        for step in chain.split(","):
            print("  " + step)
        return
    if not a.src:
        sys.exit("нужен входной файл (или --dry)")
    if not os.path.exists(a.src):
        sys.exit("нет файла: " + a.src)
    if not a.rnnoise:
        print("! модели RNNoise нет — чистка спектральная, слабее", file=sys.stderr)

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    subprocess.run([config.FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                    "-i", a.src, "-af", chain,
                    "-ac", "2", "-ar", "48000", a.out], check=True)
    print("%s: профиль %s, пространство %s, стерео 48 кГц, цель %s LUFS"
          % (a.out, a.profile, a.space, a.lufs))
    print("Проверь в наушниках И в моно: пространство разваливается именно в моно.")


if __name__ == "__main__":
    main()
