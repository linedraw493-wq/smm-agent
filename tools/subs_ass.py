#!/usr/bin/env python3
"""words.json -> subs.ass: вербатим-карты в стиле дома, разложенные по кадру.

    python subs_ass.py work/words.json -o work/subs.ass \
        [--cuts work/cuts.json] [--scenes work/clip.mp4] \
        [--palette ink-lime] [--accent "35,два часа"]

Три вещи, которые делает этот модуль:

1. Режет речь на карты по 2-4 слова, вербатим — зритель читает то же, что
   слышит. Граница ставится по паузе, а не по счёту слов.

2. Раскладывает карты по кадрам, а не только по времени (--scenes).
   Карта не должна перепрыгивать склейку: глаз в момент реза уходит на новую
   картинку и теряет строку. Карта, попавшая на склейку, режется по ней.
   Это и есть «понимать, что происходит в видео»: монтаж ведёт текст.

3. Выделяет акцентом ключевое слово (--accent). Числа выделяются сами: в
   нашем ремесле число в кадре — главное, что должно остаться в памяти.

Цвета берутся из палитры, а не зашиты: окончательный дизайн не выбран.
"""
import argparse
import json
import os
import re
import subprocess
import sys

import config
import palette as pal


def load_json(path):
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def out_t(t, cuts):
    """Время исходника -> время выхода по карте катов. Вырезано -> None."""
    if cuts is None:
        return t
    acc = 0.0
    for c in cuts:
        s, e = float(c["src_in"]), float(c["src_out"])
        sp = float(c.get("speed", 1.0)) or 1.0
        if s <= t < e:
            return acc + (t - s) / sp
        acc += (e - s) / sp
    return None


def scene_times(video, thr=0.30):
    """Секунды склеек — тем же способом, что teardown.py меряет чужие."""
    sel = "select='gt(scene," + str(thr) + ")',showinfo"
    r = subprocess.run(
        [config.FFMPEG, "-hide_banner", "-nostats", "-i", video,
         "-filter:v", sel, "-f", "null", "-"],
        capture_output=True, text=True)
    return sorted(round(float(t), 3)
                  for t in re.findall(r"pts_time:([\d.]+)", r.stderr))


def cards(words, lo, hi, gap_s=0.28):
    out, buf = [], []
    for i, w in enumerate(words):
        buf.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        gap = (nxt["s"] - w["e"]) if nxt else 99.0
        if len(buf) >= hi or (len(buf) >= lo and gap > gap_s) or nxt is None:
            out.append(buf)
            buf = []
    if buf:
        out.append(buf)
    return out


def split_on_scenes(items, scenes, min_len=0.35):
    """Карта, перепрыгивающая склейку, режется по ней.

    Глаз в момент реза уходит на новую картинку — строка, начатая до реза и
    дочитываемая после, теряется. Осколок короче min_len не плодим: мигание
    хуже, чем строка внахлёст.
    """
    if not scenes:
        return items
    out = []
    for item in items:
        s, e, text = item[0], item[1], item[2]
        card = item[3] if len(item) > 3 else None
        inner = [c for c in scenes if s + min_len < c < e - min_len]
        if not inner:
            out.append(item)
            continue
        bounds = [s] + inner + [e]
        words = text.split()
        total = e - s
        idx = 0
        made = []
        for a, b in zip(bounds, bounds[1:]):
            take = max(1, int(round(len(words) * (b - a) / total)))
            part = words[idx:idx + take] or words[idx:idx + 1]
            # словные тайминги режем той же долей — иначе караоке уедет
            sub = card[idx:idx + len(part)] if card else None
            idx += len(part)
            if part:
                made.append((a, b, " ".join(part), sub))
        if idx < len(words) and made:
            a, b, t, sub = made[-1]
            tail = card[idx:] if card else None
            made[-1] = (a, b, t + " " + " ".join(words[idx:]),
                        (sub or []) + (tail or []) if card else None)
        out.extend(made)
    return out


NUM = re.compile(r"\d")


def emphasise(text, accent_ass, text_ass, wanted):
    """Красим числа и названные слова. Больше ничего: два акцента в кадре —
    это уже не акцент."""
    words = text.split()
    hit = False
    for i, w in enumerate(words):
        bare = w.strip(".,!?:;«»\"'()").lower()
        if NUM.search(w) or bare in wanted:
            # цвет ASS: &HAABBGGRR + закрывающий &. Раньше здесь стояло
            # accent_ass[:-1] — последняя цифра красного канала срезалась,
            # и цвет уезжал. Поймано 2026-08-25 на прогоне караоке.
            words[i] = "{\\c" + accent_ass + "&}" + w + "{\\c" + text_ass + "&}"
            hit = True
    return " ".join(words), hit



def karaoke(card, accent_ass, text_ass, fill=False):
    r"""Слово подсвечивается ровно тогда, когда его произносят.

    Приём снят с разбора чужих роликов 2026-08-23: у n8n и Riley Brown это
    основной стиль субтитров, и он держит досмотр — глаз идёт за подсветкой.
    Тайминги словные, они уже есть в words.json: `\k` в ASS считает время
    в сотых долях секунды.

    fill=True — под активным словом появляется заливка (у n8n основной приём),
    иначе просто меняется цвет буквы.
    """
    out = []
    for w in card:
        dur = max(1, int(round((w["e"] - w["s"]) * 100)))
        word = w["w"]
        if fill:
            # \kf — заливка «наплывом» слева направо
            out.append("{\\kf%d\\c%s}%s" % (dur, accent_ass + "&", word))
        else:
            out.append("{\\k%d\\c%s}%s{\\c%s}"
                       % (dur, accent_ass + "&", word, text_ass + "&"))
    return " ".join(out)


def ts(t):
    t = max(0.0, t)
    return "%d:%02d:%05.2f" % (int(t // 3600), int(t % 3600 // 60), t % 60)


def build_header(p, font, size, marginv):
    tpl = os.path.join(pal.PRESETS, "subs-style.template.ass")
    with open(tpl, encoding="utf-8-sig") as f:
        s = f.read()
    return (s.replace("{W}", str(config.FRAME_W))
             .replace("{H}", str(config.FRAME_H))
             .replace("{FONT}", font)
             .replace("{SIZE}", str(size))
             .replace("{TEXT}", pal.ass(p["text"]))
             .replace("{PLATE}", pal.ass(p["plate"], p["plate_opacity"]))
             .replace("{MARGINV}", str(marginv)))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("words")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--cuts", default=None, help="карта катов work/cuts.json")
    ap.add_argument("--scenes", default=None, help="видео: разложить карты по кадрам")
    ap.add_argument("--palette", default=None)
    ap.add_argument("--accent", default="", help="слова через запятую")
    ap.add_argument("--font", default="Inter SemiBold")
    ap.add_argument("--size", type=int, default=74)
    ap.add_argument("--karaoke", action="store_true",
                    help="подсвечивать слово по мере произнесения")
    ap.add_argument("--fill", action="store_true",
                    help="заливка под активным словом (с --karaoke)")
    a = ap.parse_args()

    words = load_json(a.words)["words"]
    if not words:
        sys.exit("в words.json нет слов")
    cuts = load_json(a.cuts)["cuts"] if a.cuts else None
    p = pal.load(a.palette)
    wanted = set(w.strip().lower() for w in a.accent.split(",") if w.strip())
    out = a.out or os.path.join(os.path.dirname(a.words) or ".", "subs.ass")

    lo, hi = config.SUBS_WORDS_PER_CARD
    items, dropped = [], 0
    for card in cards(words, lo, hi):
        s, e = out_t(card[0]["s"], cuts), out_t(card[-1]["e"], cuts)
        if s is None or e is None or e <= s:
            dropped += 1
            continue
        text = " ".join(w["w"] for w in card).replace("\n", " ").strip()
        items.append((s, e, text, card))

    scenes = scene_times(a.scenes) if a.scenes else []
    before = len(items)
    items = split_on_scenes(items, scenes)

    marginv = int(config.FRAME_H * config.SUBS_BOTTOM_SAFE) + 12
    lines, accented = [], 0
    for item in items:
        s, e, text = item[0], item[1], item[2]
        card = item[3] if len(item) > 3 else None
        if a.karaoke and card:
            body = karaoke(card, pal.ass(p["accent"]), pal.ass(p["text"]), a.fill)
            hit = False
        else:
            body, hit = emphasise(text, pal.ass(p["accent"]), pal.ass(p["text"]), wanted)
        accented += 1 if hit else 0
        lines.append("Dialogue: 0,%s,%s,M4KSI,,0,0,,%s" % (ts(s), ts(e), body))

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8-sig") as f:
        f.write(build_header(p, a.font, a.size, marginv) + "\n".join(lines) + "\n")

    print("%s: %d карт, палитра «%s» (%s)" % (out, len(lines), p["name"], p["human"]))
    if dropped:
        print("  %d карт выпало на катах" % dropped)
    if scenes:
        print("  склеек в видео %d, карт разрезано по кадрам %d"
              % (len(scenes), len(items) - before))
    if accented:
        print("  акцентом выделено карт: %d" % accented)
    if a.karaoke:
        print("  караоке: слово подсвечивается по произнесению%s"
              % (", с заливкой" if a.fill else ""))


if __name__ == "__main__":
    main()
