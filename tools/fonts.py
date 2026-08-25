# -*- coding: utf-8 -*-
"""Реестр шрифтов: что доступно, что умеет кириллицу, какие пары брать.

Зачем: в `assets/fonts/` лежит пять файлов, а на машине их триста с лишним.
Половина из них не знает кириллицы — в кадре это вылезает пустыми
квадратами, и увидишь ты это только на готовом рендере.

Запуск:
    py -3.12 tools/fonts.py                 # что доступно и что умеет кириллицу
    py -3.12 tools/fonts.py --pairs         # готовые пары под задачи
    py -3.12 tools/fonts.py --check <файл>  # проверить один шрифт
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402

try:
    from PIL import ImageFont
except ImportError:
    ImageFont = None

WIN_FONTS = r"C:\Windows\Fonts"

# буквы, без которых кириллический текст в кадре сломается
PROBE = "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюя"

# наборы под задачи: чем крупный заголовок, чем текст, чем цифры и код
PAIRS = {
    "дом": {
        "что": "наш обычный ролик и обложка",
        "заголовок": "Inter-ExtraBold",
        "текст": "Inter-Regular",
        "акцент": "PlayfairDisplay-SemiBoldItalic",
        "почему": "гротеск держит крупный кегль, курсив с засечками даёт «дорого» в одном слове",
    },
    "экран": {
        "что": "кадры с кодом, терминалом, таблицами",
        "заголовок": "Inter-SemiBold",
        "текст": "consola",
        "акцент": "Inter-ExtraBold",
        "почему": "моноширинный читается как «настоящий экран» и не пляшет по ширине",
    },
    "документ": {
        "что": "предложение клиенту, медиакит, отчёт",
        "заголовок": "georgia",
        "текст": "segoeui",
        "акцент": "georgiai",
        "почему": "засечки в заголовке читаются как документ, а не как сторис",
    },
    "плакат": {
        "что": "обложка с одним словом, титул",
        "заголовок": "impact",
        "текст": "Inter-SemiBold",
        "акцент": "Inter-ExtraBold",
        "почему": "узкий тяжёлый гротеск даёт максимум буквы на ширину кадра",
    },
}


def has_cyrillic(path):
    """Умеет ли шрифт кириллицу — проверяем по таблице символов, а не по имени."""
    if ImageFont is None:
        return None
    try:
        f = ImageFont.truetype(path, 24)
    except Exception:
        return None
    try:
        # у шрифта без кириллицы ширина строки схлопывается в ноль или в .notdef
        w = f.getbbox(PROBE)[2]
        w_lat = f.getbbox("ABVGDEabvgde")[2]
        return w > 0 and w > w_lat * 2
    except Exception:
        return None


def own_fonts():
    d = config.FONTS
    if not os.path.isdir(d):
        return []
    return [os.path.join(d, f) for f in sorted(os.listdir(d))
            if f.lower().endswith((".ttf", ".otf"))]


def system_fonts():
    if not os.path.isdir(WIN_FONTS):
        return []
    return [os.path.join(WIN_FONTS, f) for f in sorted(os.listdir(WIN_FONTS))
            if f.lower().endswith((".ttf", ".otf"))]


def find(name):
    """Найти шрифт по имени: сперва свои, потом системные."""
    name = name.lower().replace(" ", "").replace("-", "")
    for p in own_fonts() + system_fonts():
        base = os.path.splitext(os.path.basename(p))[0]
        if base.lower().replace(" ", "").replace("-", "") == name:
            return p
    for p in own_fonts() + system_fonts():
        base = os.path.splitext(os.path.basename(p))[0]
        if name in base.lower().replace(" ", "").replace("-", ""):
            return p
    return None


def report():
    own = own_fonts()
    print("=== свои шрифты (%d) — едут вместе с проектом ===" % len(own))
    for p in own:
        cyr = has_cyrillic(p)
        print("  %-42s кириллица: %s" % (os.path.basename(p),
                                         "да" if cyr else "НЕТ" if cyr is False else "?"))

    sysf = system_fonts()
    good = []
    for p in sysf:
        if has_cyrillic(p):
            good.append(p)
    print("\n=== системные (%d всего, с кириллицей %d) ===" % (len(sysf), len(good)))
    print("Их можно брать в кадр, но в проект они не едут: на другой машине\n"
          "их может не быть. Для выпуска — копировать нужный в assets/fonts/.")
    show = [os.path.basename(p) for p in good]
    for i in range(0, min(len(show), 40), 4):
        print("  " + "  ".join("%-24s" % s for s in show[i:i + 4]))
    if len(show) > 40:
        print("  … ещё %d" % (len(show) - 40))


def pairs():
    print("=== наборы под задачи ===\n")
    for key, p in PAIRS.items():
        print("**%s** — %s" % (key, p["что"]))
        for role in ("заголовок", "текст", "акцент"):
            path = find(p[role])
            mark = "ok " if path else "НЕТ"
            print("   %-10s %-32s %s" % (role, p[role], mark))
        print("   почему: %s\n" % p["почему"])


def main():
    if "--pairs" in sys.argv:
        return pairs()
    if "--check" in sys.argv:
        i = sys.argv.index("--check")
        path = sys.argv[i + 1]
        if not os.path.isfile(path):
            path = find(path) or path
        print("%s: кириллица %s" % (path, has_cyrillic(path)))
        return 0
    return report()


if __name__ == "__main__":
    sys.exit(main() or 0)
