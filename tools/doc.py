# -*- coding: utf-8 -*-
"""Документ из markdown: медиакит, бриф, отчёт, презентация к разговору.

Зачем: у нас всё умеет становиться роликом и постом, но ничего — документом.
А клиенту, партнёру и площадке нужен именно документ: его пересылают,
печатают и читают без нас.

Собирает одностраничный HTML в фирменном стиле: цвета из палитры, шрифты
из наборов (`fonts.py`, набор «документ» — засечки в заголовке). Открывается
в браузере, печатается в PDF через «Печать → Сохранить как PDF».

    py -3.12 tools/doc.py work/mediakit.md -o out/mediakit.html \\
        [--title "Медиакит M4ksi"] [--kind mediakit|brief|report]

Готовый .docx или .pdf нужен файлом — это делают навыки работы с
документами, а не мы: markdown отдаём им.
"""
import argparse
import html
import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402
import palette as pal  # noqa: E402
import fonts as F  # noqa: E402

KINDS = {
    "mediakit": "Медиакит",
    "brief": "Бриф",
    "report": "Отчёт",
    "offer": "Предложение",
    "plan": "План",
}


def md_to_html(src):
    """Маленький разбор markdown: заголовки, списки, таблицы, жирный, код.

    Полноценный markdown нам не нужен — документ пишется нами и по форме.
    Чего нет, того в форме и не должно быть.
    """
    out, in_ul, in_table = [], False, False
    for raw in src.split("\n"):
        line = raw.rstrip()
        if not line.strip():
            if in_ul:
                out.append("</ul>")
                in_ul = False
            if in_table:
                out.append("</table>")
                in_table = False
            continue

        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):
                continue
            if not in_table:
                out.append('<table>')
                in_table = True
                out.append("<tr>" + "".join("<th>%s</th>" % inline(c) for c in cells) + "</tr>")
            else:
                out.append("<tr>" + "".join("<td>%s</td>" % inline(c) for c in cells) + "</tr>")
            continue
        if in_table:
            out.append("</table>")
            in_table = False

        m = re.match(r"^(#{1,3})\s+(.*)", line)
        if m:
            if in_ul:
                out.append("</ul>")
                in_ul = False
            lvl = len(m.group(1))
            out.append("<h%d>%s</h%d>" % (lvl, inline(m.group(2)), lvl))
            continue

        if line.lstrip().startswith(("- ", "* ")):
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append("<li>%s</li>" % inline(line.lstrip()[2:]))
            continue

        if in_ul:
            out.append("</ul>")
            in_ul = False
        # абзац склеиваем: в markdown перевод строки внутри абзаца — это
        # ширина колонки, а не новый абзац. Поймано на прогоне 2026-08-25.
        if out and out[-1].startswith("<p>") and not out[-1].endswith("</p></p>"):
            out[-1] = out[-1][:-4] + " " + inline(line) + "</p>"
        else:
            out.append("<p>%s</p>" % inline(line))

    if in_ul:
        out.append("</ul>")
    if in_table:
        out.append("</table>")
    return "\n".join(out)


def inline(s):
    s = html.escape(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    s = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', s)
    return s


def font_stack(role):
    """Имя шрифта для CSS: берём из набора «документ», запасной — системный."""
    name = F.PAIRS["документ"][role]
    path = F.find(name)
    fam = os.path.splitext(os.path.basename(path))[0] if path else name
    fallback = "Georgia, serif" if role in ("заголовок", "акцент") else \
        "'Segoe UI', system-ui, sans-serif"
    return "'%s', %s" % (fam, fallback)


TPL = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<title>{title}</title>
<style>
  :root {{
    --bg: {bg}; --text: {text}; --soft: {soft};
    --accent: {accent}; --line: {line}; --head: {head};
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 56px 64px 72px;
    background: var(--bg); color: var(--text);
    font: 16px/1.65 {body_font};
    max-width: 900px; margin-inline: auto;
  }}
  header {{ border-bottom: 2px solid var(--accent); padding-bottom: 18px; margin-bottom: 34px; }}
  .kind {{ font: 600 12px/1 {body_font}; letter-spacing: .22em;
           text-transform: uppercase; color: var(--accent); }}
  h1 {{ font: 600 40px/1.15 {head_font}; margin: 10px 0 6px; color: var(--head); }}
  h2 {{ font: 600 26px/1.25 {head_font}; margin: 34px 0 10px; color: var(--head); }}
  h3 {{ font: 600 19px/1.3 {body_font}; margin: 24px 0 8px; color: var(--head); }}
  p {{ margin: 0 0 12px; }}
  ul {{ margin: 0 0 14px; padding-left: 22px; }}
  li {{ margin: 0 0 6px; }}
  strong {{ color: var(--head); }}
  code {{ font: 14px/1.4 Consolas, monospace; background: rgba(0,0,0,.06);
          padding: 1px 5px; border-radius: 4px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 12px 0 20px; }}
  th, td {{ text-align: left; padding: 9px 12px; border-bottom: 1px solid var(--line); }}
  th {{ font: 600 13px/1.3 {body_font}; text-transform: uppercase;
        letter-spacing: .08em; color: var(--soft); }}
  footer {{ margin-top: 46px; padding-top: 16px; border-top: 1px solid var(--line);
            color: var(--soft); font-size: 13px; display: flex;
            justify-content: space-between; }}
  @media print {{
    body {{ padding: 0; max-width: none; }}
    header {{ break-after: avoid; }}
    h2, h3 {{ break-after: avoid; }}
    table, ul {{ break-inside: avoid; }}
  }}
</style></head>
<body>
<header>
  <div class="kind">{kind}</div>
  <h1>{title}</h1>
</header>
{body}
<footer><span>M4KSI</span><span>{today}</span></footer>
</body></html>
"""


def build(src_path, out_path, title=None, kind="mediakit"):
    with open(src_path, encoding="utf-8") as f:
        src = f.read()

    # заголовок берём из первой строки «# …», если не задан
    if not title:
        m = re.search(r"^#\s+(.+)$", src, re.M)
        title = m.group(1).strip() if m else os.path.basename(src_path)
        src = re.sub(r"^#\s+.+$", "", src, count=1, flags=re.M)

    p = pal.load()
    doc = TPL.format(
        title=html.escape(title),
        kind=KINDS.get(kind, kind).upper(),
        body=md_to_html(src),
        bg="#ffffff",
        text="#1a1f26",
        soft="#5b6672",
        head="#131a22",   # заголовок на бумаге: тёмный, не палитра кадра
        accent=p["accent"],
        line="#dfe4ea",
        head_font=font_stack("заголовок"),
        body_font=font_stack("текст"),
        today=date.today().isoformat(),
    )
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(doc)
    print("документ: %s  (%s, %.1f КБ)"
          % (out_path, KINDS.get(kind, kind), os.path.getsize(out_path) / 1024))
    print("  PDF: открыть в браузере → Печать → Сохранить как PDF")
    return out_path


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="markdown-файл")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--title", default=None)
    ap.add_argument("--kind", default="mediakit", choices=list(KINDS))
    a = ap.parse_args()
    build(a.source, a.out, a.title, a.kind)
    return 0


if __name__ == "__main__":
    sys.exit(main())
