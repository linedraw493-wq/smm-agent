#!/usr/bin/env python3
"""words.json → subs.ass — вербатим-карты по 2–4 слова в стиле M4ksi.

    python subs_ass.py work/words.json -o work/subs.ass [--cuts work/cuts.json]

Стиль — плашка (BorderStyle=3), не обводка: на пёстром фоне обводка плывёт.
Шапка стиля берётся из presets/subs-m4ksi.ass, чтобы стиль жил в одном месте.

cuts.json — карта катов и ускорений. Если ролик резался, тайминги слов надо
пересчитать в выходную шкалу. **CUTS — единственный источник правды:** тот же
файл читает сборка. Разойдутся — субтитры уедут, и ошибка будет тихой.

Формат cuts.json:
    {"cuts": [{"src_in": 1.2, "src_out": 5.4, "speed": 1.0}, ...]}
"""
import argparse, json, os, sys
import config


def load_cuts(path):
    if not path:
        return None
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)["cuts"]


def out_t(t, cuts):
    """Время исходника → время выхода. Слово вне окон катов → None (вырезано)."""
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


def cards(words, lo, hi):
    """Режем поток слов на карты 2–4 слова. Граница — по паузе, потом по счёту."""
    out, buf = [], []
    for i, w in enumerate(words):
        buf.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        gap = (nxt["s"] - w["e"]) if nxt else 99.0
        if len(buf) >= hi or (len(buf) >= lo and gap > 0.28) or nxt is None:
            out.append(buf)
            buf = []
    if buf:
        out.append(buf)
    return out


def ts(t):
    t = max(0.0, t)
    h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("words")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--cuts", default=None)
    ap.add_argument("--style", default=config.SUBS_STYLE_FILE)
    a = ap.parse_args()

    with open(a.words, encoding="utf-8-sig") as f:
        words = json.load(f)["words"]
    if not words:
        sys.exit("в words.json нет слов")
    cuts = load_cuts(a.cuts)
    out = a.out or os.path.join(os.path.dirname(a.words) or ".", "subs.ass")

    with open(a.style, encoding="utf-8-sig") as f:
        header = f.read().rstrip() + "\n"

    lo, hi = config.SUBS_WORDS_PER_CARD
    lines, dropped = [], 0
    for card in cards(words, lo, hi):
        s = out_t(card[0]["s"], cuts)
        e = out_t(card[-1]["e"], cuts)
        if s is None or e is None or e <= s:
            dropped += 1
            continue
        text = " ".join(w["w"] for w in card).replace("\n", " ").strip()
        # 8 полей до текста: Layer,Start,End,Style,Name,MarginL,MarginR,Effect
        lines.append(f"Dialogue: 0,{ts(s)},{ts(e)},M4KSI,,0,0,,{text}")

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8-sig") as f:
        f.write(header + "\n".join(lines) + "\n")
    msg = f"{out}: {len(lines)} карт"
    if dropped:
        msg += f", {dropped} выпало на катах"
    print(msg)


if __name__ == "__main__":
    main()
