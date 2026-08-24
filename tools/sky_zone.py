#!/usr/bin/env python3
"""Небо и большие светлые поля: плоское, выбитое или пустое в исходнике.

    python sky_zone.py raw/03.mp4 --at 9.45 --hdr --sweep
    python sky_zone.py out/reel.mp4 --at 12.3
    python sky_zone.py raw/03.mp4 --at 9.45 --hdr --chain "curves=..."

Зачем отдельный модуль, когда есть grade_zones.

`grade_zones` меряет ЗОНУ СВЕТОВ всего кадра — все пиксели ярче 180, где бы
они ни лежали. Для вопроса «тёплые ли света» этого хватает. Для вопроса «что
не так с небом» — нет: в зону светов попадают и блик на капоте, и белая
футболка, и торпедо в контровом, а небо в ней тонет.

Заведено 2026-08-24 по `projects/2026-08-24-test-tyoplyy-kadr`. Кот забраковал
дорожные кадры словами «небо плоское, выбито в белое, грейд его не тронул».
Замер показал, что оба утверждения неверны: доля ≥ 250 была 0.00–1.16 %, а
тепло в небе выросло с +1.07 до +34.31. Плоским небо делало третье — оно было
слишком ЯРКИМ: 226–234 luma, до 67 % выше 240. Новой цепочки грейда это
стоило бы зря. Подробности и лечение — craft/color §Плоское небо.

ЧТО МЕРИТСЯ И ПОЧЕМУ ИМЕННО ЭТО:

  СКО внутри неба и размах p1–p99
      «Плоское» — это НЕ «упёрлось в 255». Это «внутри неба нет разброса»:
      облако от облака не отличается. Долей выбитого такое не ловится вовсе.

  доля ≥ 250 и ОТДЕЛЬНО доля ≥ 240
      250 отвечает «склеились ли света». 240 отвечает «читается ли пятно как
      белое». Второй вопрос и есть тот, что задаёт глаз, и по нему пасмурное
      небо проваливается там, где по первому проходит с нулём.

  то же самое на СЫРОМ HDR, в 16 битах
      Ответ на «потолок исходника». Размах меньше ~25 кодов из 255 значит,
      что структуры в небе нет в самом файле, и вернуть её нельзя ничем.

МАСКА считается ОДИН РАЗ — по кадру без цепочки — и прикладывается ко всем
вариантам. Иначе у каждой цепочки своя маска, это уже разные пиксели, и
разница чисел ничего не значит. Берётся по яркости И положению: верхние
`--top` кадра и luma выше `--thr`. Прямоугольником нельзя — он ловит кроны
деревьев и козырёк, а они не небо.

СЫРОЙ PQ читается rawvideo-дампом, а не через PIL: `.convert("RGB")` роняет
16 бит в 8, и вопрос «есть ли деталь в тонких градациях» отвечает сам себе —
нет, потому что мы её только что выбросили. Числа сырого кадра — в КОДАХ PQ,
а не в нитах: PQ нелинеен, сравнивать их с яркостью после тонмапа нельзя.
Внутри одной строки они сравнимы между собой, и этого хватает: вопрос стоит
«есть ли разброс», а не «сколько нит».
"""
import argparse
import subprocess
import sys

import numpy as np

import config

W_PX = 540
KEYS = ["доля_неба", "ярк", "СКО_неба", "размах_p1_p99", "≥250", "≥240", "тепло"]
SWEEP = (100, 250, 400, 700, 1000)
# Размах в сыром PQ ниже этого — структуры в небе нет в самом файле.
# Число с нашего материала: клип без облаков дал 23, клип с деталью — 36.
FLAT_SOURCE_RANGE = 25.0


def grab(src, t, vf, depth16=False):
    """Кадр как массив float 0..255 — через rawvideo, без потери битности."""
    pix = "rgb48le" if depth16 else "rgb24"
    cmd = [config.FFMPEG, "-y", "-v", "error"]
    if t is not None:
        cmd += ["-ss", "%.3f" % t]
    cmd += ["-i", src, "-vf", vf, "-frames:v", "1",
            "-pix_fmt", pix, "-f", "rawvideo", "-"]
    buf = subprocess.run(cmd, capture_output=True, check=True).stdout
    a = np.frombuffer(buf, dtype=np.uint16 if depth16 else np.uint8)
    a = a.astype(np.float32).reshape(-1, W_PX, 3)
    return a / 65535.0 * 255.0 if depth16 else a


def luma_of(a):
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def sky_mask(luma, top_frac, thr):
    m = np.zeros(luma.shape, bool)
    m[: int(luma.shape[0] * top_frac)] = True
    return m & (luma > thr)


def stat(a, m):
    r, b = a[..., 0], a[..., 2]
    s = luma_of(a)[m]
    return {"доля_неба": 100.0 * float(m.mean()),
            "ярк": float(s.mean()),
            "СКО_неба": float(s.std()),
            "размах_p1_p99": float(np.percentile(s, 99) - np.percentile(s, 1)),
            "≥250": 100.0 * float((s >= 250).mean()),
            "≥240": 100.0 * float((s >= 240).mean()),
            "тепло": float((r - b)[m].mean())}


def line(name, r):
    print("%-28s " % name[:28] + "  ".join("%s %6.2f" % (k, r[k]) for k in KEYS))


def main():
    ap = argparse.ArgumentParser(description="Замер неба по маске")
    ap.add_argument("src")
    ap.add_argument("--at", type=float, default=None, help="секунда кадра")
    ap.add_argument("--hdr", action="store_true", help="исходник HDR — тонмапить")
    ap.add_argument("--npl", type=int, default=400)
    ap.add_argument("--chain", default="", help="цепочка грейда после тонмапа")
    ap.add_argument("--sweep", action="store_true",
                    help="прогнать npl 100·250·400·700·1000")
    ap.add_argument("--top", type=float, default=0.55, help="доля кадра сверху")
    ap.add_argument("--thr", type=float, default=150.0, help="порог luma для неба")
    a = ap.parse_args()

    scale = ",scale=%d:-2" % W_PX
    base_tm = (config.tonemap(a.npl) if a.hdr else "null")

    base = grab(a.src, a.at, base_tm + scale)
    m = sky_mask(luma_of(base), a.top, a.thr)
    if m.sum() < 100:
        sys.exit("маска неба пуста: верхние %.0f %% кадра ярче %.0f не набрали "
                 "и сотни пикселей. Неба на этом плане нет — или порог не тот."
                 % (a.top * 100, a.thr))

    raw = None
    if a.hdr:
        raw = stat(grab(a.src, a.at, "null" + scale, depth16=True), m)
        line("СЫРОЙ PQ 16 бит (коды PQ)", raw)
        for npl in (SWEEP if a.sweep else (a.npl,)):
            line("тонмап npl=%d" % npl,
                 stat(grab(a.src, a.at, config.tonemap(npl) + scale), m))
    else:
        line("как есть", stat(base, m))

    if a.chain:
        line("  + цепочка", stat(grab(a.src, a.at, base_tm + "," + a.chain + scale), m))

    # Диагноз словами — иначе таблицу прочтут как «выбито/не выбито» и
    # починят не то. Ровно эта ошибка и стоила захода 2026-08-24.
    cur = stat(grab(a.src, a.at, base_tm + ("," + a.chain if a.chain else "") + scale), m)
    print("")
    if cur["≥250"] >= 1.0:
        print("ДИАГНОЗ: света склеились (доля ≥250 %.2f %%). Лечится тонмапом, "
              "npl ВНИЗ." % cur["≥250"])
    elif cur["≥240"] >= 10.0:
        print("ДИАГНОЗ: небо не выбито, а СЛИШКОМ ЯРКОЕ (≥250 всего %.2f %%, "
              "но ≥240 уже %.1f %%). Глаз читает это как пересвет при любом "
              "оттенке. Лечится тонмапом, npl ВВЕРХ — не цветом и не гаммой "
              "сведения." % (cur["≥250"], cur["≥240"]))
    else:
        print("ДИАГНОЗ: по яркости небо в норме (≥250 %.2f %%, ≥240 %.1f %%)."
              % (cur["≥250"], cur["≥240"]))
    if raw and raw["размах_p1_p99"] < FLAT_SOURCE_RANGE:
        print("ПОТОЛОК ИСХОДНИКА: размах в сыром PQ %.1f кода из 255 — "
              "структуры в небе нет в самом файле. Оттенить можно, вернуть "
              "деталь нельзя ничем." % raw["размах_p1_p99"])
    elif raw:
        print("Материал не при чём: размах в сыром PQ %.1f кода — деталь в "
              "файле есть." % raw["размах_p1_p99"])


if __name__ == "__main__":
    main()
