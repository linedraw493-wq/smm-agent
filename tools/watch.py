#!/usr/bin/env python3
"""Смотреть чужие ролики самой — весь путь одной командой.

    python watch.py --channel https://www.youtube.com/@nateherk/shorts -n 3
    python watch.py --url <ссылка> [--name 2026-08-23-avtor-chto]
    python watch.py --roll-up            # свести все просмотры в корпус

Аля не может «посмотреть видео» так, как человек. Но она может **воспринять**
его тремя каналами сразу, и вместе они дают больше, чем просмотр:

  глазами  — контактный лист кадров (look.py): ритм, цвет, композиция
  ушами    — транскрипт первых секунд (whisper): крючок дословно
  числами  — замер (teardown.py): склейки, LUFS, средний план

Этот модуль делает всю механику и оставляет ровно одно, чего машина не может:
**посмотреть на контактный лист и сказать словами, что там за приём.**
Дальше — операция razobrat-rolik.

Скачанное лежит в assets/ref/ — вне git, study-only. Забираем приём, не ролик.
"""
import argparse, glob, json, os, re, subprocess, sys, datetime
import config

REPO = config.REPO
REF = os.path.join(REPO, "assets", "ref")
CARDS = os.path.join(REPO, "alya-vault", "trends", "teardowns")
CORPUS = os.path.join(REPO, "alya-vault", "school", "corpus")
PY = sys.executable
TOOLS = os.path.dirname(os.path.abspath(__file__))

# Сколько секунд расшифровывать. Нас интересует крючок, а не весь текст:
# полный транскрипт чужого ролика нам не нужен и хранить его незачем.
HOOK_SECONDS = 10

# Крючок расшифровываем МАЛЕНЬКОЙ моделью, не рабочей large-v3.
# Здесь нужна суть первой фразы чужого ролика, а не вербатим для субтитров:
# small на CPU делает это в разы быстрее, а на десяти секундах чистой речи
# ошибается редко. В своих субтитрах модель остаётся большой — там цена
# ошибки другая.
HOOK_MODEL = "small"


def ytdlp(*args):
    # ffmpeg стоит в winget-папке и в PATH его нет — yt-dlp сам его не найдёт
    # и молча откажется склеивать видео со звуком. Показываем путь явно.
    return subprocess.run(
        [PY, "-m", "yt_dlp", "--ffmpeg-location", os.path.dirname(config.FFMPEG),
         *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace")


def slug(s, n=40):
    s = re.sub(r"[^\w\s-]", "", s, flags=re.U).strip().lower()
    s = re.sub(r"[\s_]+", "-", s)
    return s[:n].strip("-") or "bez-imeni"


def discover(channel, count):
    """Свежие ролики канала — без браузера и без входа."""
    r = ytdlp("--flat-playlist", "--playlist-end", str(count),
              # разделитель — табуляция: в именах каналов сплошь и рядом «|»
              # в плоском списке channel часто пуст — падаем на поле плейлиста
              "--print",
              "%(id)s	%(uploader,channel,playlist_uploader,playlist_title,playlist)s	%(title)s",
              channel)
    if r.returncode != 0:
        print(r.stderr.strip()[-400:], file=sys.stderr)
        return []
    out = []
    for line in r.stdout.splitlines():
        parts = line.split("	", 2)
        if len(parts) == 3:
            out.append({"id": parts[0], "author": parts[1], "title": parts[2]})
    return out


def fetch(url, folder):
    os.makedirs(folder, exist_ok=True)
    dst = os.path.join(folder, "src.mp4")
    if os.path.exists(dst):
        print("  уже скачан")
        return dst
    r = ytdlp("-f", "bv*+ba/b", "--merge-output-format", "mp4",
              "-o", os.path.join(folder, "src.%(ext)s"), url)
    if r.returncode != 0 or not os.path.exists(dst):
        print("  НЕ СКАЧАЛОСЬ: " + r.stderr.strip().splitlines()[-1][:200]
              if r.stderr.strip() else "  НЕ СКАЧАЛОСЬ")
        return None
    return dst


def run(mod, *args):
    r = subprocess.run([PY, os.path.join(TOOLS, mod), *args],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return r.stdout


def numbers(path):
    """Замер teardown.py, разобранный в словарь — чтобы сводить в корпус."""
    txt = run("teardown.py", path)
    d = {"raw": txt}
    pat = {
        "duration": r"длительность\s+([\d.]+)",
        "cuts": r"склеек\s+(\d+)",
        "avg_shot": r"средний план\s+([\d.]+)",
        "first_cut": r"первая склейка\s+([\d.]+)",
    }
    for k, p in pat.items():
        m = re.search(p, txt)
        if m:
            d[k] = float(m.group(1))
    m = re.search(r"звук\s+(\S+),\s*(-?[\d.]+) LUFS, LRA (-?[\d.]+)", txt)
    if m:
        d["channels"], d["lufs"], d["lra"] = m.group(1), float(m.group(2)), float(m.group(3))
    m = re.search(r"кадр\s+(\d+)×(\d+) @ (\d+)", txt)
    if m:
        d["w"], d["h"], d["fps"] = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return d


def hook_text(path, folder, lang):
    """Первые секунды словами. Крючок — это то, что сказано в них дословно."""
    cut = os.path.join(folder, "hook.wav")
    subprocess.run([config.FFMPEG, "-v", "error", "-y", "-t", str(HOOK_SECONDS),
                    "-i", path, "-vn", "-ac", "1", "-ar", "16000", cut],
                   check=False)
    if not os.path.exists(cut):
        return ""
    out = run("transcribe.py", cut, "-o", os.path.join(folder, "hook.json"),
              "--lang", lang, "--model", HOOK_MODEL)
    try:
        with open(os.path.join(folder, "hook.json"), encoding="utf-8") as f:
            return json.load(f).get("text", "").strip()
    except Exception:
        return ""


CARD = """---
тип: разбор
род: ролик
источник: {url}
автор: {author}
дата: {date}
статус: числа сняты, приём не назван
---
# {title}

**Смотреть:** `{sheet}` — контактный лист. Открыть и глядеть, а не читать
описание. Файл ролика — `{src}`, вне git, study-only.

## Числа — сняты машиной

```
{raw}```

## Крючок дословно — первые {hook_sec} секунд

> {hook}

## Что видно глазами — ЗАПОЛНИТЬ, смотря на лист

Пока эти строки пустые, разбора нет: числа без приёма ничему не учат.

- **Первый кадр:** что в нём, есть ли субъект, что обещает.
- **Ритм:** где разгон, где пауза, есть ли пик.
- **Крупности:** меняются или всё одним планом.
- **Раскладка экрана:** полный кадр, сплит, где текст, где лицо.
- **Субтитры:** размер карт, стиль, подсветка слова.
- **Финал:** кадр или затухание; замыкает ли начало.

## Мост к нам — без него разбор бесполезен

- **Воспроизводимо ли** нашим конвейером:
- **Что забираем** (приём, не кадр):
- **Чего не забираем вслепую** и почему:
"""


def one(url, author, title, lang, date):
    name = f"{date}-{slug(author, 20)}-{slug(title, 30)}"
    folder = os.path.join(REF, name)
    print(f"\n▸ {author} — {title}")

    # Карточка, в которую уже писали глазами, не перезаписывается никогда.
    # Ловушка поймана 2026-08-23: `--channel -n 6` берёт СВЕЖИЕ ролики, а
    # свежие почти всегда те же, что в прошлый раз. Один повторный прогон
    # стирал бы разбор — самое дорогое, что здесь есть, и единственное, что
    # машина не восстановит. Числа снимаются заново за минуту, приём — нет.
    card = os.path.join(CARDS, name + ".md")
    if os.path.exists(card):
        with open(card, encoding="utf-8") as f:
            if "Разобрано глазами" in f.read():
                print(f"  разобрана глазами — не трогаю: "
                      f"{os.path.relpath(card, REPO)}")
                return None

    src = fetch(url, folder)
    if not src:
        return None

    num = numbers(src)
    sheet = os.path.join(folder, "look.jpg")
    run("look.py", src, "-n", "16", "--cols", "4", "--tile", "260", "-o", sheet)
    hook = hook_text(src, folder, lang) or "(речи в первых секундах нет — "\
                                           "крючок визуальный)"

    os.makedirs(CARDS, exist_ok=True)
    with open(card, "w", encoding="utf-8") as f:
        f.write(CARD.format(url=url, author=author, title=title, date=date,
                            sheet=os.path.relpath(sheet, REPO).replace("\\", "/"),
                            src=os.path.relpath(src, REPO).replace("\\", "/"),
                            raw=num.get("raw", ""), hook=hook,
                            hook_sec=HOOK_SECONDS))
    with open(os.path.join(folder, "numbers.json"), "w", encoding="utf-8") as f:
        json.dump({k: v for k, v in num.items() if k != "raw"}, f,
                  ensure_ascii=False, indent=1)

    print(f"  карточка: {os.path.relpath(card, REPO)}")
    print(f"  СМОТРЕТЬ:  {os.path.relpath(sheet, REPO)}")
    return num


def roll_up():
    """Свести все просмотры в коридор чисел. Это и есть корпус."""
    rows = []
    for p in sorted(glob.glob(os.path.join(REF, "*", "numbers.json"))):
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
            d["name"] = os.path.basename(os.path.dirname(p))
            rows.append(d)
        except Exception:
            pass
    if len(rows) < 3:
        print(f"просмотров {len(rows)} — мало. По одному-двум замерам норму от "
              "случайности не отличить, коридор не считаю.")
        return

    def col(k):
        return [r[k] for r in rows if isinstance(r.get(k), (int, float))]

    def line(label, k, fmt="{:.2f}"):
        v = col(k)
        if not v:
            return f"| {label} | — | — | — |"
        v.sort()
        return (f"| {label} | {fmt.format(v[0])} | "
                f"{fmt.format(sum(v) / len(v))} | {fmt.format(v[-1])} |")

    date = datetime.date.today().isoformat()
    os.makedirs(CORPUS, exist_ok=True)
    out = os.path.join(CORPUS, f"{date}-koridor.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"""---
type: reference
status: active
updated: {date}
tags: [corpus, benchmarks, measured]
---

# Коридор чисел — {len(rows)} просмотренных роликов

Снято `tools/watch.py --roll-up` {date}. **Это не мнение о том, как надо, —
это то, как делают** те, кого мы смотрим. Наше число вне коридора не значит
«плохо», но значит «объясни, почему у нас иначе».

| Мерка | минимум | среднее | максимум |
|---|---|---|---|
{line('длительность, с', 'duration')}
{line('склеек', 'cuts', '{:.0f}')}
{line('средний план, с', 'avg_shot')}
{line('первая склейка, с', 'first_cut')}
{line('громкость, LUFS', 'lufs')}
{line('LRA', 'lra')}

## Три оговорки — без них таблица врёт

1. **Ноль склеек не значит «нет монтажа».** Детектор сцен видит смену всего
   кадра. При раскладке «сплит верх/низ» с неподвижной нижней половиной он
   не видит ничего, хотя верх меняется каждые две секунды. Такие ролики
   выпадают из колонки «средний план», а не портят её.
2. **LUFS сняты с файла, скачанного с площадки.** Площадка отдаёт свой
   поток, и это не обязательно то, что автор загружал. Абсолютную громкость
   по этой таблице не выставляем — держим −14 по спекам.
   **LRA сжатием площадки не меняется, ему верим.**
3. **Длительность разъезжается**, потому что «Shorts» — это всё до трёх
   минут. Смотреть надо на нижнюю половину коридора, а не на среднее.

## Что просмотрено

""")
        for r in rows:
            f.write(f"- `{r['name']}` — {r.get('duration', '?')} с, "
                    f"средний план {r.get('avg_shot', '?')} с, "
                    f"{r.get('lufs', '?')} LUFS\n")
    print(f"{os.path.relpath(out, REPO)} — коридор по {len(rows)} роликам.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--channel", help="канал или плейлист: берём свежие")
    ap.add_argument("--url", help="один конкретный ролик")
    ap.add_argument("--name", help="имя папки для --url")
    ap.add_argument("-n", "--count", type=int, default=3)
    ap.add_argument("--lang", default="en", help="язык речи в роликах")
    ap.add_argument("--roll-up", action="store_true",
                    help="свести все просмотры в коридор чисел")
    a = ap.parse_args()

    date = datetime.date.today().isoformat()
    if a.roll_up:
        return roll_up()

    if a.url:
        one(a.url, (a.name or "ref").split("-")[0], a.name or "ролик",
            a.lang, date)
    elif a.channel:
        items = discover(a.channel, a.count)
        if not items:
            sys.exit("канал не отдал список. Instagram профили yt-dlp не "
                     "поддерживает — туда нужна ссылка на конкретный ролик.")
        for it in items:
            one(f"https://www.youtube.com/watch?v={it['id']}",
                it["author"], it["title"], a.lang, date)
    else:
        sys.exit("нужен --channel, --url или --roll-up")

    print("\nЧисла сняты, крючок расшифрован, листы готовы.")
    print("Осталось то, чего машина не умеет: ОТКРЫТЬ лист и назвать приём.")
    print("Дальше — alya-vault/operations/razobrat-rolik.md")


if __name__ == "__main__":
    main()
