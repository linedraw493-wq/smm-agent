#!/usr/bin/env python3
"""Подложить музыку под голос — так, чтобы её было слышно, а голос понятно.

    python music_bed.py --voice work/voice.wav --music assets/music/<трек>.mp3 \
        -o work/mix.wav [--under 16] [--duck] [--intro 1.2] [--outro 1.5]

Уровень музыки меряется НЕ абсолютно, а разницей к голосу. У референс-влогов
музыка идёт примерно на 16 dB тише голоса — это живая подложка. На 26 dB и
ниже её просто не слышно, и вшивать её тогда незачем.

--duck включает сайдчейн: музыка приседает, когда говорят, и возвращается в
паузах. На плотной речи разница невелика, на речи с паузами слышна сразу.

ЛИЦЕНЗИЯ ПРОВЕРЯЕТСЯ ДО СВЕДЕНИЯ. Трека нет в assets/music/licenses.md —
модуль останавливается. Обработка чужого трека НЕ делает его свободным:
защищает лицензия, а не эквалайзер.
"""
import argparse
import os
import re
import subprocess
import sys

import config

REGISTRY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "assets", "music", "licenses.md")


def check_license(track):
    """Трек без записанной лицензии в работу не идёт."""
    name = os.path.basename(track)
    if not os.path.exists(REGISTRY):
        sys.exit("нет реестра лицензий %s — без него музыку не подкладываем" % REGISTRY)
    with open(REGISTRY, encoding="utf-8") as f:
        reg = f.read()
    if name not in reg:
        sys.exit("трек «%s» не записан в assets/music/licenses.md.\n"
                 "Внеси строку с лицензией и источником — или возьми другой трек.\n"
                 "Обработка чужого трека не делает его свободным: защищает лицензия."
                 % name)
    for line in reg.splitlines():
        if name in line:
            if "CC-BY" in line.upper():
                print("! CC-BY: в подписи к посту обязательна кредит-строка")
            return line.strip()
    return ""


def dur(path):
    r = subprocess.run([config.FFPROBE, "-v", "error", "-show_entries",
                        "format=duration", "-of", "default=nw=1:nk=1", path],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--voice", required=True)
    ap.add_argument("--music", required=True)
    ap.add_argument("-o", "--out", default="mix.wav")
    ap.add_argument("--under", type=float, default=16.0,
                    help="на сколько dB музыка тише голоса")
    ap.add_argument("--duck", action="store_true", help="сайдчейн-приседание")
    ap.add_argument("--intro", type=float, default=1.0, help="нарастание, с")
    ap.add_argument("--outro", type=float, default=1.5, help="затухание, с")
    a = ap.parse_args()

    for f in (a.voice, a.music):
        if not os.path.exists(f):
            sys.exit("нет файла: " + f)

    lic = check_license(a.music)
    if lic:
        print("лицензия: " + re.sub(r"\s+", " ", lic)[:120])

    vd = dur(a.voice)
    out_fade = max(0.0, vd - a.outro)

    # музыка: обрезать по длине голоса, вырезать полосу речи, приглушить,
    # нарастание и затухание. Вырез на 300-3000 Гц освобождает место голосу —
    # это слышно сильнее, чем просто убавить громкость
    music = ("[1:a]atrim=0:%.3f,asetpts=N/SR/TB,"
             "equalizer=f=800:t=q:w=1.4:g=-3,"
             "equalizer=f=2500:t=q:w=1.2:g=-2,"
             "volume=%.2fdB,"
             "afade=t=in:st=0:d=%.2f,afade=t=out:st=%.3f:d=%.2f[m]"
             % (vd, -a.under, a.intro, out_fade, a.outro))

    if a.duck:
        graph = ("[0:a]asplit=2[v1][vsc];" + music +
                 ";[m][vsc]sidechaincompress=threshold=0.05:ratio=6:attack=15"
                 ":release=350:makeup=1[md];"
                 "[v1][md]amix=inputs=2:duration=first:normalize=0,"
                 "loudnorm=I=%s:TP=%s:LRA=%s[out]"
                 % (config.LUFS_TARGET, config.TRUE_PEAK, config.LRA))
    else:
        graph = (music + ";[0:a][m]amix=inputs=2:duration=first:normalize=0,"
                 "loudnorm=I=%s:TP=%s:LRA=%s[out]"
                 % (config.LUFS_TARGET, config.TRUE_PEAK, config.LRA))

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    subprocess.run([config.FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                    "-i", a.voice, "-stream_loop", "-1", "-i", a.music,
                    "-filter_complex", graph, "-map", "[out]",
                    "-ac", "2", "-ar", "48000", a.out], check=True)
    print("%s: музыка на %.0f dB под голосом%s, %.1f с"
          % (a.out, a.under, ", с приседанием" if a.duck else "", vd))
    print("Проверь: голос разборчив, музыка слышна. Не слышна — она лишняя.")


if __name__ == "__main__":
    main()
