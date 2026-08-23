#!/usr/bin/env python3
"""Сделать библиотеку SFX своими руками — вуши, райзеры, импакты, клики.

    python sfx_make.py            # собрать весь набор в assets/sfx/
    python sfx_make.py --list     # что будет сделано, без записи

Почему синтез, а не скачивание. Канон цеха назвал SFX-слой приоритетом №1 и
главным разрывом с профессиональными рилсами — и не внедрил его ни разу.
Скачивание упирается в аккаунты и ключи API, а Аля не заводит аккаунтов и не
тратит денег.

Между тем **вуш, райзер, импакт и клик — это ровно то, что делается
синтезом**, и делается так же, как их делают в студии: шум с движущимся
фильтром и огибающей, скользящий тон, короткий транзиент. Своё звучит не
хуже покупного в этой категории и **не несёт вообще никаких прав** — ни
страйка, ни атрибуции, ни срока лицензии.

Чего синтезом НЕ сделать и за чем идти в библиотеку: живые предметные звуки
(шаги, клавиатура, дверь, кофе), атмосферы места, музыкальные хиты. Их
докладываем скачиванием, когда владелец скажет.

Уровни: пик −6 dBFS. Дальше сведение по craft/sound-design: SFX на −12…−8 dB
относительно голоса, три-пять штук на ролик, не больше.
"""
import argparse, os, struct, wave
import numpy as np
import config

SR = 48000
PEAK = 10 ** (-6 / 20)          # −6 dBFS, запас под сведение
OUT = os.path.join(config.REPO, "assets", "sfx")


# ─── кирпичи ──────────────────────────────────────────────────────────────

def t(dur):
    return np.linspace(0, dur, int(SR * dur), endpoint=False)


def noise(dur, seed=0):
    return np.random.default_rng(seed).standard_normal(len(t(dur)))


def env(dur, attack, release, curve=2.0):
    """Огибающая: атака — release. Кривая делает спад естественным."""
    n = int(SR * dur)
    a, r = max(1, int(SR * attack)), max(1, int(SR * release))
    s = max(0, n - a - r)
    return np.concatenate([
        np.linspace(0, 1, a) ** (1 / curve),
        np.ones(s),
        np.linspace(1, 0, r) ** curve,
    ])[:n]


def sweep_filter(x, f0, f1, q=0.9):
    """Полосовой фильтр с движущейся частотой — сердце вуша.

    Считается по одному отсчёту резонансным фильтром состояния (SVF): он
    устойчив при быстром движении частоты, в отличие от пересчёта биквада.
    """
    n = len(x)
    f = np.geomspace(f0, f1, n)
    g = np.tan(np.pi * f / SR)
    k = 1.0 / q
    out = np.empty(n)
    ic1 = ic2 = 0.0
    for i in range(n):
        a1 = 1.0 / (1.0 + g[i] * (g[i] + k))
        a2 = g[i] * a1
        v3 = x[i] - ic2
        v1 = a1 * ic1 + a2 * v3
        v2 = ic2 + g[i] * v1
        ic1 = 2 * v1 - ic1
        ic2 = 2 * v2 - ic2
        out[i] = v1                      # полосовой выход
    return out


def stereo(x, width=0.0):
    """Моно в стерео. width — задержка правого канала в мс, даёт ширину.

    На голосе ширину не делаем никогда (развалится в моно), а на эффекте
    можно: он не несёт смысла, и если сложится — не страшно."""
    if width <= 0:
        return np.stack([x, x], axis=1)
    d = int(SR * width / 1000)
    r = np.concatenate([np.zeros(d), x])[:len(x)]
    return np.stack([x, r], axis=1)


def norm(x):
    m = np.max(np.abs(x))
    return x * (PEAK / m) if m > 0 else x


def save(name, data):
    data = norm(data)
    if data.ndim == 1:
        data = stereo(data)
    pcm = (np.clip(data, -1, 1) * 32767).astype("<i2")
    path = os.path.join(OUT, name + ".wav")
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return path, len(data) / SR


# ─── сами звуки ───────────────────────────────────────────────────────────

def whoosh(dur=0.45, up=True, seed=1, width=8):
    """Вуш: шум, летящий по спектру. Вверх — вход, вниз — уход.

    ⚠️ Кладётся ЧЕРЕЗ рез, а не в точку реза: пик совпадает с кадром
    склейки, хвост уходит в новый план (craft/sound-design)."""
    x = noise(dur, seed)
    f0, f1 = (300, 6000) if up else (6000, 300)
    x = sweep_filter(x, f0, f1)
    x *= env(dur, 0.06 * dur, 0.55 * dur, 2.2)
    return stereo(x, width)


def riser(dur=1.5, seed=2):
    """Райзер: готовит зрителя к пику. Начинается ЗА секунду-две до кадра-пика
    и обрывается В ТОТ ЖЕ кадр, не после."""
    x = noise(dur, seed)
    x = sweep_filter(x, 200, 9000, q=1.4)
    tone = 0.35 * np.sin(2 * np.pi * np.cumsum(np.geomspace(120, 900, len(t(dur)))) / SR)
    x = x + tone
    x *= np.linspace(0, 1, len(x)) ** 2.2      # ровный набор без хвоста
    return stereo(x, 12)


def impact(dur=0.35, seed=3):
    """Импакт: точка под число или результат. Транзиент плюс низ."""
    tt = t(dur)
    low = np.sin(2 * np.pi * np.cumsum(np.geomspace(150, 45, len(tt))) / SR)
    low *= env(dur, 0.001, 0.9 * dur, 3.0)
    crack = noise(dur, seed) * env(dur, 0.0005, 0.06, 4.0)
    return stereo(low * 0.9 + crack * 0.35, 4)


def subdrop(dur=0.7):
    """Саб-дроп: уход вниз под смену блока. Тише, чем кажется нужным."""
    tt = t(dur)
    x = np.sin(2 * np.pi * np.cumsum(np.geomspace(90, 28, len(tt))) / SR)
    return stereo(x * env(dur, 0.005, 0.8 * dur, 2.5))


def click(dur=0.035, f=2400):
    """Клик: появление текста, плашки, галочки."""
    x = np.sin(2 * np.pi * f * t(dur)) * env(dur, 0.0005, dur * 0.9, 3.5)
    # шум держим тихим: на замере при 0.25 центр спектра уезжал к 10 кГц —
    # это уже не клик, а шипящий тик, и тон под ним не слышен
    x += noise(dur, 7) * env(dur, 0.0003, 0.004, 4.0) * 0.10
    return stereo(x)


def pop(dur=0.09):
    """Поп: мягче клика, под появление карточки."""
    tt = t(dur)
    x = np.sin(2 * np.pi * np.cumsum(np.geomspace(900, 260, len(tt))) / SR)
    return stereo(x * env(dur, 0.002, 0.08, 2.6))


def ui_ok(dur=0.22):
    """Две ноты вверх: подтверждение в интерфейсе, «сработало»."""
    half = dur / 2
    a = np.sin(2 * np.pi * 880 * t(half)) * env(half, 0.003, half * 0.8)
    b = np.sin(2 * np.pi * 1320 * t(half)) * env(half, 0.003, half * 0.8)
    return stereo(np.concatenate([a, b]) * 0.8)


def swell(dur=1.0, seed=5):
    """Свелл: мягкий вдох перед фразой. Не райзер — тише и без тона."""
    x = noise(dur, seed)
    x = sweep_filter(x, 800, 5000, q=0.7)
    return stereo(x * (np.linspace(0, 1, len(x)) ** 1.6), 16)


SET = {
    "whoosh-up":     (lambda: whoosh(0.45, True, 1),  "вуш вверх — вход в новый блок"),
    "whoosh-down":   (lambda: whoosh(0.45, False, 4), "вуш вниз — уход, закрытие"),
    "whoosh-short":  (lambda: whoosh(0.22, True, 9),  "короткий вуш — быстрый рез"),
    "riser-1_5":     (lambda: riser(1.5),             "райзер 1.5 с — подход к пику"),
    "riser-2_0":     (lambda: riser(2.0, 6),          "райзер 2.0 с — длинный подход"),
    "impact":        (lambda: impact(),               "импакт — под число, под результат"),
    "subdrop":       (lambda: subdrop(),              "саб-дроп — смена блока"),
    "click":         (lambda: click(),                "клик — появление текста"),
    "click-soft":    (lambda: click(0.05, 1600),      "мягкий клик — вторичный текст"),
    "pop":           (lambda: pop(),                  "поп — появление карточки"),
    "ui-ok":         (lambda: ui_ok(),                "две ноты вверх — «сработало»"),
    "swell":         (lambda: swell(),                "свелл — вдох перед фразой"),
}

REGISTRY = """# SFX — реестр

**Файла нет в этой таблице — он не идёт в работу.** То же правило, что у
музыки: страйк прилетает за файл, а не за небрежность.

## Откуда это взялось

Весь стартовый набор **синтезирован нами** — `tools/sfx_make.py`. Вуш,
райзер, импакт и клик делаются так же, как в студии: шум с движущимся
полосовым фильтром и огибающей, скользящий тон, короткий транзиент.

**Права наши, лицензия не нужна, атрибуция не нужна, страйк невозможен.**
Пересобрать набор можно в любой момент одной командой — файлы в git не едут,
код едет.

## Как пользоваться — коротко

- **Три-пять акцентов на ролик, не больше.** Перебор SFX хуже, чем их
  отсутствие: чаще — это уже шум и подпись бесплатного редактора.
- **Вуш кладётся ЧЕРЕЗ рез**, а не в точку реза: пик на кадре склейки, хвост
  в новом плане. Так склейка прячется, а не подчёркивается.
- **Райзер обрывается в кадр пика**, не после него.
- Уровень: **−12…−8 dB относительно голоса**. Файлы нормализованы к −6 dBFS,
  запас под сведение уже есть.

Подробности — `alya-vault/craft/sound-design.md`.

## Чего здесь нет и почему

Синтезом не делаются живые предметные звуки (шаги, клавиатура, дверь,
стакан), атмосферы места и музыкальные хиты. За ними — в CC0-библиотеки
(Pixabay, Mixkit, ZapSplat, VideoEditingSFX), по слову владельца. Скачал —
**записал строку сюда в тот же момент**, иначе следующая сессия не будет
знать, можно ли брать файл.

## Реестр

| Файл | Что это | Длина | Права |
|---|---|---|---|
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    if a.list:
        for k, (_, why) in SET.items():
            print(f"{k:14s} — {why}")
        return

    os.makedirs(OUT, exist_ok=True)
    rows = []
    for name, (make, why) in SET.items():
        path, dur = save(name, make())
        rows.append(f"| `{name}.wav` | {why} | {dur:.2f} с | наши |")
        print(f"{name:14s} {dur:5.2f} с")

    with open(os.path.join(OUT, "licenses.md"), "w", encoding="utf-8") as f:
        f.write(REGISTRY + "\n".join(rows) + "\n")
    print(f"\n{len(rows)} звуков в assets/sfx/, реестр записан.")
    print("Слой SFX больше не пустой — это был приоритет №1 канона цеха.")


if __name__ == "__main__":
    main()
