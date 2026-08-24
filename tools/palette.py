#!/usr/bin/env python3
"""Палитра — читается из presets/palette-<имя>.json, а не зашита в код.

    python palette.py            — показать все палитры
    python palette.py ink-lime   — показать одну

Палитра выбрана 2026-08-24: `blue-white`. `ink-lime` не удалена — статус
`отклонена`, живёт как история. Выбор всё ещё параметр выпуска
(`--palette` / `ALYA_PALETTE`), а не жёстко зашит в модули — на случай
пересмотра.
"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
PRESETS = os.path.join(os.path.dirname(ROOT), "presets")
DEFAULT = os.environ.get("ALYA_PALETTE", "blue-white")


def names():
    return sorted(os.path.basename(p)[8:-5]
                  for p in glob.glob(os.path.join(PRESETS, "palette-*.json")))


def load(name=None):
    name = name or DEFAULT
    p = os.path.join(PRESETS, f"palette-{name}.json")
    if not os.path.exists(p):
        sys.exit(f"нет палитры «{name}». Есть: {', '.join(names())}")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def rgba(hexstr, opacity=None):
    """#rrggbb или #rrggbbaa → (r, g, b, a) для Pillow."""
    h = hexstr.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    a = int(h[6:8], 16) if len(h) >= 8 else 255
    if opacity is not None:
        a = int(round(255 * opacity))
    return (r, g, b, a)


def ass(hexstr, opacity=None):
    """#rrggbb → &HAABBGGRR. Задом наперёд, и альфа инвертирована:
    в ASS 00 = непрозрачный, FF = прозрачный. Обе ловушки — тихие."""
    r, g, b, a = rgba(hexstr, opacity)
    return "&H%02X%02X%02X%02X" % (255 - a, b, g, r)


def main():
    want = sys.argv[1] if len(sys.argv) > 1 else None
    for n in ([want] if want else names()):
        p = load(n)
        mark = "  ← по умолчанию" if n == DEFAULT else ""
        print(f"\n{p['name']} — {p['human']} ({p['author']}, {p['status']}){mark}")
        print(f"  источник: {p['source']}")
        for k in ("bg", "plate", "text", "heading", "accent"):
            if k in p:
                print(f"  {k:<10} {p[k]:<10} ASS {ass(p[k])}")
        print(f"  плашка в ASS: {ass(p['plate'], p['plate_opacity'])}"
              f"  (непрозрачность {int(p['plate_opacity']*100)}%)")
        if p.get("note"):
            print(f"  {p['note']}")


if __name__ == "__main__":
    main()
