#!/usr/bin/env python3
"""Карта катов из длинного материала — хоть из часов.

    python cuts.py work/src.mp4 -o work/cuts.json
        [--min-speech 0.35] [--pad 0.12] [--gap 0.45] [--noise -34]
        [--max-out 30] [--words work/words.json]

Механический слой отбора: выкидывает то, где думать не о чем — тишину,
дед-эйр, слишком длинные паузы. Обычно снимает половину хронометража и
не требует ни головы, ни распознавания.

ПОЧЕМУ НЕ ЧЕРЕЗ РАСПОЗНАВАНИЕ. Распознать час речи моделью large-v3 на
процессоре — это час с лишним счёта. Поиск тишины идёт в десятки раз
быстрее реального времени и на часах работает спокойно. Поэтому порядок
такой: сначала дёшево отрезать тишину, и только по оставшимся кускам,
если надо, гонять распознавание.

Выход — `cuts.json`, ЕДИНСТВЕННЫЙ источник правды по времени: его читают и
сборка, и субтитры. Разойдутся — субтитры уедут, и ошибка будет тихой.

Смысловой отбор (что из речи оставить) этот модуль НЕ делает: он про
механику. Смысл — за Алей, по операции vybrat-katy.
"""
import argparse
import json
import os
import re
import subprocess
import sys

import config


def duration(path):
    r = subprocess.run(
        [config.FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def silences(path, noise_db, min_sil):
    """Окна тишины через silencedetect. Идёт много быстрее реального времени,
    поэтому не боится часов."""
    r = subprocess.run(
        [config.FFMPEG, "-hide_banner", "-nostats", "-i", path,
         "-af", "silencedetect=noise=%ddB:d=%s" % (noise_db, min_sil),
         "-f", "null", "-"],
        capture_output=True, text=True)
    starts = [float(x) for x in re.findall(r"silence_start:\s*(-?[\d.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end:\s*([\d.]+)", r.stderr)]
    out = []
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else None
        out.append((max(0.0, s), e))
    return out


def speech_regions(dur, sils, pad, min_speech):
    """Инверсия тишины = речь. С запасом по краям: рез впритык съедает
    первую букву — особенно перед /с/-подобными согласными."""
    regions, cur = [], 0.0
    for s, e in sils:
        if s > cur:
            regions.append((cur, s))
        cur = e if e is not None else dur
    if cur < dur:
        regions.append((cur, dur))
    out = []
    for s, e in regions:
        s = max(0.0, s - pad)
        e = min(dur, e + pad)
        if e - s >= min_speech:
            if out and s - out[-1][1] < 0.05:      # склеиваем почти сомкнутые
                out[-1] = (out[-1][0], e)
            else:
                out.append((s, e))
    return out


def merge_close(regions, gap):
    """Паузу короче gap не режем: дробить речь на слова — не монтаж, а
    заикание. Пауза внутри фразы должна остаться."""
    if not regions:
        return []
    out = [list(regions[0])]
    for s, e in regions[1:]:
        if s - out[-1][1] <= gap:
            out[-1][1] = e
        else:
            out.append([s, e])
    return [tuple(x) for x in out]


def hhmmss(t):
    return "%d:%02d:%05.2f" % (int(t // 3600), int(t % 3600 // 60), t % 60)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--noise", type=int, default=-34, help="порог тишины, dB")
    ap.add_argument("--min-sil", type=float, default=0.35, help="мин. длина тишины, с")
    ap.add_argument("--min-speech", type=float, default=0.35, help="мин. кусок речи, с")
    ap.add_argument("--pad", type=float, default=0.12, help="запас по краям куска, с")
    ap.add_argument("--gap", type=float, default=0.45, help="паузу короче — не режем")
    ap.add_argument("--max-out", type=float, default=None,
                    help="предупредить, если итог длиннее (с)")
    ap.add_argument("--speed", type=float, default=1.0)
    a = ap.parse_args()

    if not os.path.exists(a.src):
        sys.exit("нет файла: " + a.src)

    dur = duration(a.src)
    print("исходник %s (%.1f с)" % (hhmmss(dur), dur))
    if dur > 1800:
        print("  длинный материал — поиск тишины идёт быстро, распознавание нет.")
        print("  Распознавать только выбранные куски, а не всё целиком.")

    sils = silences(a.src, a.noise, a.min_sil)
    regions = merge_close(speech_regions(dur, sils, a.pad, a.min_speech), a.gap)
    if not regions:
        sys.exit("речь не найдена. Порог --noise слишком строгий, либо в файле тишина.")

    kept = sum(e - s for s, e in regions)
    print("речь: %s из %s (%.0f%%), кусков %d"
          % (hhmmss(kept), hhmmss(dur), 100 * kept / dur, len(regions)))
    print("выброшено тишины: %s" % hhmmss(dur - kept))

    out = a.out or os.path.join(os.path.dirname(a.src) or ".", "cuts.json")
    data = {
        "source": os.path.abspath(a.src),
        "source_duration": round(dur, 3),
        "out_duration": round(kept / (a.speed or 1.0), 3),
        "made_by": "cuts.py (механический слой: тишина и дед-эйр)",
        "note": "Смысловой отбор не делался. Куски идут подряд, как в исходнике.",
        "cuts": [{"src_in": round(s, 3), "src_out": round(e, 3), "speed": a.speed}
                 for s, e in regions],
    }
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    print("%s: %d кусков, на выходе %s" % (out, len(regions), hhmmss(data["out_duration"])))
    if a.max_out and data["out_duration"] > a.max_out:
        print("  ! длиннее %.0f с — это ещё не ролик, а материал без тишины."
              % a.max_out)
        print("  Дальше смысловой отбор: выбрать крючок, потом под него остальное.")
    print("  Эту же карту обязан прочитать subs_ass.py --cuts, иначе субтитры уедут.")


if __name__ == "__main__":
    main()
