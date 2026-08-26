#!/usr/bin/env python3
"""Диагностика голоса ДО обработки — что чинить, а что не трогать.

    python audio_report.py <файл> [--spectrum work/spec.png]

Эквализировать вслепую нельзя: одна и та же цепочка на хорошей записи даёт
звонкий голос, а на убитой — только громче подчёркивает брак. Сначала замер.

Что меряет:
  * энергию по шести полосам — где мути много, где воздуха нет;
  * ПОТОЛОК полосы — выше какой частоты сигнала практически нет;
  * громкость (LUFS), разброс (LRA), пик, шумовую полку;
  * моно или стерео и совпадают ли каналы.

Главный диагноз, который он ставит: **потолок около 10 кГц** означает, что
запись прошла через мессенджер. Это не лечится ничем — голосовой кодек
срезал полосу, выше неё пусто. Такую запись надо перезаписать, а не
обрабатывать.
"""
import argparse
import re
import subprocess
import sys

import config

# (имя, низ, верх, что означает избыток, что означает недостаток)
BANDS = [
    ("низ 80-200",       80,   200, "гул и бубнёж",      "голос тонкий"),
    ("муть 200-500",     200,  500, "закрытый, в бочке", "голос пустой"),
    ("тело 500-2k",      500,  2000, "носовой",          "голос без опоры"),
    ("разбор 2k-5k",     2000, 5000, "резкий",           "слова смазаны"),
    ("присутств 5k-9k",  5000, 9000, "шипит",            "голос далеко"),
    ("воздух 9k-16k",    9000, 16000, "стеклянный",      "голос глухой"),
]


def run(args):
    return subprocess.run(args, capture_output=True, text=True).stderr


def band_db(path, lo, hi):
    err = run([config.FFMPEG, "-hide_banner", "-nostats", "-i", path,
               "-af", "highpass=f=%d,lowpass=f=%d,volumedetect" % (lo, hi),
               "-f", "null", "-"])
    m = re.search(r"mean_volume:\s*(-?[\d.]+)", err)
    return float(m.group(1)) if m else None


def overall(path):
    err = run([config.FFMPEG, "-hide_banner", "-nostats", "-i", path,
               "-af", "astats=metadata=1:reset=0,loudnorm=print_format=json",
               "-f", "null", "-"])
    def j(key):
        m = re.findall(r'"%s"\s*:\s*"(-?[\d.]+)"' % key, err)
        return float(m[-1]) if m else None
    peaks = [float(x) for x in re.findall(r"Peak level dB:\s*(-?[\d.]+)", err)]
    rms = [float(x) for x in re.findall(r"RMS level dB:\s*(-?[\d.]+)", err)]
    floor = [float(x) for x in re.findall(r"Noise floor dB:\s*(-?[\d.]+)", err)]
    return j("input_i"), j("input_lra"), peaks, rms, floor


def channels(path):
    # только по именам полей: ffprobe печатает их в своём порядке, и
    # позиционное чтение молча меняет каналы местами с частотой
    r = subprocess.run(
        [config.FFPROBE, "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=channels,sample_rate",
         "-of", "json", path],
        capture_output=True, text=True)
    import json as _json
    st = (_json.loads(r.stdout).get("streams") or [{}])[0]
    return int(st.get("channels", 0)), int(st.get("sample_rate", 0))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src")
    ap.add_argument("--spectrum", default=None, help="сохранить картинку спектра")
    a = ap.parse_args()

    ch, sr = channels(a.src)
    print("канал(ов) %d, частота дискретизации %d Гц"
          % (ch, sr) + ("   ! моно — на телефоне заиграет в одно ухо" if ch == 1 else ""))

    lufs, lra, peaks, rms, floor = overall(a.src)
    print("громкость  %s LUFS   разброс LRA %s" % (lufs, lra))
    if peaks:
        print("пик        %.1f dB" % max(peaks))
    if floor:
        print("шумовая полка %.1f dB" % max(floor))
        if rms and max(rms) - max(floor) < 30:
            print("           ! шум близко к голосу — чистка будет слышна, "
                  "лучше перезаписать")
    if len(rms) >= 2 and abs(rms[0] - rms[1]) > 0.5:
        print("           ! L и R расходятся на %.2f dB" % abs(rms[0] - rms[1]))

    print("\nполосы (среднее, dB):")
    vals = {}
    for name, lo, hi, much, few in BANDS:
        db = band_db(a.src, lo, hi)
        vals[name] = db
        print("  %-18s %s" % (name, "%.1f" % db if db is not None else "—"))

    body = vals.get("тело 500-2k")
    if body is not None:
        print("\nчитаем относительно тела голоса (%.1f dB):" % body)
        for name, lo, hi, much, few in BANDS:
            db = vals.get(name)
            if db is None or name.startswith("тело"):
                continue
            d = db - body
            verdict = ""
            if name.startswith("муть") and d > -4:
                verdict = "  <- многовато: " + much + ", снять 2-3 dB на 450 Гц"
            if name.startswith("воздух") and d < -26:
                verdict = "  <- мало: " + few + ", поднять 9 кГц на 3-4 dB"
            if name.startswith("присутств") and d < -20:
                verdict = "  <- мало: " + few + ", поднять 4.2 кГц на 3 dB"
            print("  %-18s %+6.1f dB%s" % (name, d, verdict))

    # Отдельный замер узкой мутной полосы. Штатные полосы широкие: 200-500
    # мешает в одну кучу нижнюю опору голоса и настоящую муть, и вырез на
    # 3-4 dB почти не двигает её среднее — замер 2026-08-25 показал сдвиг
    # 3.4 -> 3.0 при реально снятых 2.6 dB. Владелец слышит именно 300-650
    # («убери мутность»), поэтому меряем ровно эту полосу против тела 650-2k.
    mud = band_db(a.src, 300, 650)
    tone = band_db(a.src, 650, 2000)
    if mud is not None and tone is not None:
        d = mud - tone
        print("\nмутность 300-650 Гц против тела 650-2к: %+.1f dB" % d)
        if d > 3:
            print("    <- перевешивает тело: голос закрытый. Вырез --mud 3-4 dB")
        elif d < -1:
            print("    <- вырезано слишком: голос станет пустым, ослабить --mud")
        else:
            print("    <- в норме: муть не перевешивает тело голоса")

    air = vals.get("воздух 9k-16k")
    pres = vals.get("присутств 5k-9k")
    if air is not None and pres is not None and pres - air > 22:
        print("\n!!! ПОТОЛОК около 10 кГц: выше почти пусто.")
        print("    Это подпись голосового кодека — запись шла через мессенджер.")
        print("    Полосу не вернуть ничем. Перезаписать «Диктофоном» в Lossless,")
        print("    передать кабелем или AirDrop. Мессенджер жмёт и при записи,")
        print("    и при передаче.")

    if a.spectrum:
        subprocess.run([config.FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                        "-i", a.src, "-lavfi",
                        "showspectrumpic=s=1200x600:legend=1", a.spectrum],
                       check=False)
        print("\nспектр: %s  (чёрный потолок на картинке = срезанная полоса)"
              % a.spectrum)


if __name__ == "__main__":
    main()

# Оговорка про полосы: они широкие, а эквалайзер узкий. Вырез 2.5 dB с
# добротностью ~1.2 на 450 Гц почти не сдвинет среднее по полосе 200-500 —
# и это не значит, что он не сработал. Полосы показывают ОБЩИЙ перекос
# тембра, а не действие отдельного фильтра. Судить о вырезе — ухом и по
# спектру (--spectrum), а не по этой таблице.
