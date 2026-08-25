# -*- coding: utf-8 -*-
"""Макет экрана или страницы: заготовка HTML с нашей дизайн-системой.

Зачем: у нас есть кадр и пост, но нет экрана. Клиент просит «покажите, как
это будет выглядеть» — и показать нечего. Этот модуль отдаёт живую страницу
с готовыми размерами, цветами, состояниями кнопок и мобильной сеткой:
дальше её наполняют текстом, а не рисуют заново.

    py -3.12 tools/maket.py landing -o work/maket.html --title "ИИ-агент"
    py -3.12 tools/maket.py screen  -o work/app.html --title "Заявки"
    py -3.12 tools/maket.py tokens  -o work/tokens.html

Виды:
    landing — продающая страница: экран-обещание, что умеет, ступени, призыв
    screen  — экран приложения: список, карточка, действия
    tokens  — витрина системы: цвета, шрифты, отступы, состояния

Правило: макет — не картинка. Он открывается в браузере, тянется по ширине
и показывает то же, что увидит человек с телефона.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import palette as pal  # noqa: E402

# Сетка 8: все отступы кратны восьми. Это не вкус — так размеры совпадают
# на любом экране без подгонки.
BASE = """
:root {
  --bg: %(bg)s; --panel: %(panel)s; --text: %(text)s; --soft: %(soft)s;
  --accent: %(accent)s; --line: %(line)s; --head: %(head)s;
  --s1: 8px; --s2: 16px; --s3: 24px; --s4: 32px; --s5: 48px; --s6: 64px;
  --r1: 10px; --r2: 16px; --r3: 24px;
  --f-h1: clamp(30px, 6vw, 54px);
  --f-h2: clamp(22px, 4vw, 32px);
  --f-body: clamp(15px, 2.6vw, 18px);
  --f-small: 13px;
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  background: var(--bg); color: var(--text);
  font: var(--f-body)/1.6 'Segoe UI', system-ui, -apple-system, sans-serif;
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 1080px; margin: 0 auto; padding: 0 var(--s3); }
h1, h2, h3 { color: var(--head); margin: 0 0 var(--s2); line-height: 1.15; }
h1 { font-size: var(--f-h1); letter-spacing: -0.02em; }
h2 { font-size: var(--f-h2); letter-spacing: -0.01em; }
p { margin: 0 0 var(--s2); }
.soft { color: var(--soft); }
.kicker {
  font-size: var(--f-small); letter-spacing: .22em; text-transform: uppercase;
  color: var(--accent); margin-bottom: var(--s2);
}
.btn {
  display: inline-flex; align-items: center; gap: var(--s1);
  background: var(--accent); color: #08111c; border: 0;
  padding: 14px 26px; border-radius: var(--r1);
  font: 600 var(--f-body)/1 inherit; cursor: pointer;
  transition: transform .12s ease, filter .12s ease;
  min-height: 48px;             /* палец: меньше 48px промахивается */
}
.btn:hover { filter: brightness(1.08); }
.btn:active { transform: translateY(1px); }
.btn:focus-visible { outline: 3px solid var(--accent); outline-offset: 3px; }
.btn.ghost { background: transparent; color: var(--head);
             border: 1px solid var(--line); }
.card {
  background: var(--panel); border: 1px solid var(--line);
  border-radius: var(--r2); padding: var(--s3);
}
.grid { display: grid; gap: var(--s3); }
@media (min-width: 720px) { .grid.c2 { grid-template-columns: 1fr 1fr; }
                            .grid.c3 { grid-template-columns: repeat(3, 1fr); } }
section { padding: var(--s6) 0; }
.line { height: 1px; background: var(--line); border: 0; margin: 0; }
.tag { display: inline-block; font-size: var(--f-small); color: var(--accent);
       border: 1px solid var(--accent); border-radius: 999px;
       padding: 4px 12px; }
"""

LANDING = """
<header class="wrap" style="padding-top:var(--s5)">
  <div class="kicker">%(kicker)s</div>
  <h1>%(title)s</h1>
  <p class="soft" style="max-width:56ch">Одно предложение о том, что человек
     получит. Не про нас — про его дело.</p>
  <p style="margin-top:var(--s3)">
    <button class="btn">Обсудить задачу</button>
    <button class="btn ghost">Как это работает</button>
  </p>
</header>
<hr class="line">
<section class="wrap">
  <h2>Что он умеет</h2>
  <div class="grid c3">
    <div class="card"><div class="tag">отвечает</div>
      <p>На частые вопросы клиентов, круглосуточно, в мессенджере.</p></div>
    <div class="card"><div class="tag">записывает</div>
      <p>Заявку кладёт туда, где её увидят, и напоминает.</p></div>
    <div class="card"><div class="tag">передаёт</div>
      <p>Чего не знает — отдаёт человеку. Не выдумывает.</p></div>
  </div>
</section>
<section class="wrap">
  <h2>Как идём</h2>
  <div class="grid c3">
    <div class="card"><h3>1. Разговор</h3><p class="soft">15–20 минут.
      Разбираем задачу. Бесплатно.</p></div>
    <div class="card"><h3>2. Запуск</h3><p class="soft">Собираем и показываем
      работающего агента.</p></div>
    <div class="card"><h3>3. Дальше</h3><p class="soft">Ведём и улучшаем
      по месяцам.</p></div>
  </div>
</section>
<section class="wrap">
  <div class="card" style="text-align:center">
    <h2>Посмотрим на вашу задачу?</h2>
    <p class="soft">Один разговор — и станет понятно, нужен ли вам агент вообще.</p>
    <button class="btn">Написать нам</button>
  </div>
</section>
<footer class="wrap soft" style="padding:var(--s5) var(--s3);font-size:var(--f-small)">
  M4KSI · макет, не готовая страница
</footer>
"""

SCREEN = """
<header class="wrap" style="padding:var(--s3) var(--s3) 0;display:flex;
        justify-content:space-between;align-items:center">
  <strong>%(title)s</strong>
  <button class="btn" style="padding:10px 18px">Новая</button>
</header>
<section class="wrap" style="padding-top:var(--s3)">
  <div class="grid" style="gap:var(--s2)">
    <div class="card" style="display:flex;justify-content:space-between;gap:var(--s2)">
      <div><strong>Айгуль</strong><br><span class="soft">пробное занятие · сегодня 14:00</span></div>
      <span class="tag">новая</span>
    </div>
    <div class="card" style="display:flex;justify-content:space-between;gap:var(--s2)">
      <div><strong>Тимур</strong><br><span class="soft">перезвонить · вчера</span></div>
      <span class="tag" style="color:var(--soft);border-color:var(--line)">в работе</span>
    </div>
    <div class="card" style="display:flex;justify-content:space-between;gap:var(--s2)">
      <div><strong>Салтанат</strong><br><span class="soft">записана · 20 авг</span></div>
      <span class="tag" style="color:var(--soft);border-color:var(--line)">закрыта</span>
    </div>
  </div>
</section>
<section class="wrap">
  <div class="card">
    <div class="kicker">карточка</div>
    <h2>Айгуль</h2>
    <p class="soft">+7 ··· ·· ··  ·  из формы на сайте  ·  группа: начинающие</p>
    <p><button class="btn">Записать на пробное</button>
       <button class="btn ghost">Позвонить</button></p>
  </div>
</section>
"""

TOKENS = """
<section class="wrap">
  <div class="kicker">дизайн-система</div>
  <h1>%(title)s</h1>
  <h2>Цвета</h2>
  <div class="grid c3">
    <div class="card"><div style="height:64px;border-radius:var(--r1);
         background:var(--accent)"></div><p class="soft">accent — действие,
         акцент, ссылка</p></div>
    <div class="card"><div style="height:64px;border-radius:var(--r1);
         background:var(--panel);border:1px solid var(--line)"></div>
         <p class="soft">panel — карточки и панели</p></div>
    <div class="card"><div style="height:64px;border-radius:var(--r1);
         background:var(--bg);border:1px solid var(--line)"></div>
         <p class="soft">bg — фон страницы</p></div>
  </div>
  <h2>Текст</h2>
  <h1 style="margin:0">Заголовок первого уровня</h1>
  <h2 style="margin:var(--s2) 0">Заголовок второго уровня</h2>
  <p>Обычный текст. Длина строки держится в 60–75 знаках — дальше глаз
     теряет начало следующей строки.</p>
  <p class="soft">Приглушённый текст: подписи, второстепенное.</p>
  <h2>Кнопки и состояния</h2>
  <p><button class="btn">Основное действие</button>
     <button class="btn ghost">Второстепенное</button>
     <button class="btn" disabled style="opacity:.45;cursor:not-allowed">Недоступно</button></p>
  <p class="soft">Высота кнопки — не меньше 48 px: палец промахивается по
     меньшему. Фокус обведён видимой рамкой — иначе с клавиатуры не понять,
     где находишься.</p>
  <h2>Отступы</h2>
  <div class="grid c3">
    <div class="card"><p>8 / 16 / 24</p><p class="soft">внутри карточки</p></div>
    <div class="card"><p>32 / 48</p><p class="soft">между блоками</p></div>
    <div class="card"><p>64</p><p class="soft">между секциями</p></div>
  </div>
</section>
"""

BODIES = {"landing": LANDING, "screen": SCREEN, "tokens": TOKENS}


def build(kind, out, title, kicker):
    p = pal.load()
    css = BASE % {
        "bg": p["bg"], "panel": p.get("plate", p["bg"]), "text": p["text"],
        "soft": p["text_soft"], "accent": p["accent"], "line": p["hairline"],
        "head": p["heading"],
    }
    body = BODIES[kind] % {"title": title, "kicker": kicker}
    doc = ("<!doctype html>\n<html lang=\"ru\"><head><meta charset=\"utf-8\">\n"
           "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
           "<title>%s</title>\n<style>%s</style></head>\n<body>%s</body></html>\n"
           % (title, css, body))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(doc)
    print("макет: %s  (%s, палитра «%s»)" % (out, kind, p["name"]))
    print("  открыть в браузере и сузить окно до 375 px — так его увидит телефон")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kind", choices=list(BODIES))
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--title", default="Создадим вам ИИ-агента")
    ap.add_argument("--kicker", default="M4KSI")
    a = ap.parse_args()
    build(a.kind, a.out, a.title, a.kicker)
    return 0


if __name__ == "__main__":
    sys.exit(main())
