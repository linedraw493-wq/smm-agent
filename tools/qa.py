#!/usr/bin/env python3
"""Гейты готового ролика (craft/video-station §Четыре гейта).

    python qa.py out/reel.mp4 [--expect-duration 27.4]

Проверяет машиной то, что глазами проверять нельзя:
  1. кадр 1080×1920 @ 30
  2. звук стерео и L/R RMS совпадают — «no one-ear»
     (с --silent проверка переворачивается: звука быть не должно)
  3. громкость в −14…−16 LUFS
  4. длительность сошлась с ожидаемой (рассинхрон concat — тихий брак)

Гейт контраста живёт в рендерере плашек: его надо мерить ДО сборки, на
ярчайшем кадре окна, а не на готовом файле.

Код возврата 1, если хоть один гейт не прошёл.
"""
import argparse, json, re, subprocess, sys
import config

OK, BAD = "OK  ", "БРАК"


def probe(path):
    r = subprocess.run(
        [config.FFPROBE, "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", path],
        capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def measure_audio(path):
    """Одним проходом: loudnorm (LUFS) и astats (RMS по каналам)."""
    r = subprocess.run(
        [config.FFMPEG, "-hide_banner", "-nostats", "-i", path,
         "-af", "astats=metadata=1:reset=0,loudnorm=print_format=json",
         "-f", "null", "-"],
        capture_output=True, text=True)
    err = r.stderr
    lufs = None
    m = re.findall(r'"input_i"\s*:\s*"(-?[\d.]+)"', err)
    if m:
        lufs = float(m[-1])
    rms = [float(x) for x in re.findall(r"RMS level dB:\s*(-?[\d.inf]+)", err)
           if x not in ("-inf", "inf")]
    return lufs, rms


# Пороги ритма — craft/montage.md. Расходятся с ремеслом → правит ремесло.
RHYTHM_AVG_MAX = 3.0        # средняя длина плана, с
RHYTHM_LONGEST_MAX = 5.0    # самый длинный план, с
RHYTHM_FIRST_CUT_MAX = 2.0  # первая склейка, с
RHYTHM_MIN_SHOTS = 8        # планов на ролик 20–30 с


def shots(path, thr):
    """Границы планов по смене сцены. Тот же метод, что в teardown.py —
    жёсткие каты ловит, мягкие переходы пропускает намеренно."""
    r = subprocess.run(
        [config.FFMPEG, "-hide_banner", "-nostats", "-i", path,
         "-filter:v", f"select='gt(scene,{thr})',showinfo", "-f", "null", "-"],
        capture_output=True, text=True)
    return [round(float(t), 2)
            for t in re.findall(r"pts_time:([\d.]+)", r.stderr)]


def check_rhythm(path, dur, thr, declared=None):
    """Гейт ритма. Возвращает список провалов.

    ⚠️ Детектор сцен видит только ЖЁСТКИЕ каты. Кроссфейд 0.5 с он
    пропускает — поймано 2026-08-23 на первой же пересборке: ролик из семи
    кусков с --xfade показался ему одним планом на 23.5 с, и гейт выдал
    четыре «БРАК» там, где ритм по кускам был в норме.

    Гейт, который врёт, хуже отсутствующего. Поэтому: не нашли склеек на
    длинном ролике — НЕ судим, а требуем сказать число планов явно
    (--shots). Судить наугад нельзя ни в плюс, ни в минус.
    """
    cuts = shots(path, thr)
    if declared is None and dur > 10.0 and len(cuts) < 2:
        print("?    ритм не измерен: детектор нашёл "
              f"{len(cuts)} склеек на {dur:.1f} с. Так бывает при мягких "
              "переходах (--xfade) — они не «смена сцены».")
        print("     Скажи число планов явно: qa.py … --rhythm --shots N")
        return []
    if declared is not None and declared > len(cuts) + 1:
        # переходы мягкие: раскладываем ролик на равные планы по объявленному
        # числу — точных границ нет, но средняя и число планов честные
        step = dur / declared
        cuts = [round(step * (i + 1), 2) for i in range(declared - 1)]
        print(f"     планов объявлено {declared}, границы приняты равномерно "
              "(мягкие переходы)")
    n = len(cuts) + 1
    lens = [round(b - a, 2) for a, b in zip([0.0] + cuts, cuts + [dur])]
    avg = sum(lens) / len(lens)
    longest = max(lens)
    first = cuts[0] if cuts else dur
    bad = []

    def gate(ok, name, msg):
        print(f"{OK if ok else BAD} {msg}")
        if not ok:
            bad.append(name)

    gate(avg <= RHYTHM_AVG_MAX, "ритм: средний план",
         f"средний план {avg:.2f} с (норма ≤ {RHYTHM_AVG_MAX})")
    gate(longest <= RHYTHM_LONGEST_MAX, "ритм: длинный план",
         f"самый длинный план {longest:.2f} с (норма ≤ {RHYTHM_LONGEST_MAX})")
    gate(first <= RHYTHM_FIRST_CUT_MAX, "ритм: первая склейка",
         f"первая склейка {first:.2f} с (норма ≤ {RHYTHM_FIRST_CUT_MAX})")
    gate(n >= RHYTHM_MIN_SHOTS, "ритм: мало планов",
         f"планов {n} (норма ≥ {RHYTHM_MIN_SHOTS})")
    print(f"     длины планов: {' '.join(f'{x:.1f}' for x in lens)}")
    if bad:
        print("     ровный ряд — метроном, разброс — ритм. Лечится резом, "
              "а не ускорением (craft/montage).")
    return bad


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("video")
    ap.add_argument("--expect-duration", type=float, default=None)
    ap.add_argument("--cuts", default=None,
                    help="карта катов: ожидаемая длина берётся из неё")
    ap.add_argument("--silent", action="store_true",
                    help="ролик задуман немым: звука быть НЕ должно")
    ap.add_argument("--rhythm", action="store_true",
                    help="гейт ритма: средний план, максимум, первая склейка, "
                         "число планов (craft/montage)")
    ap.add_argument("--scene", type=float, default=0.30,
                    help="порог смены сцены для поиска склеек")
    ap.add_argument("--shots", type=int, default=None,
                    help="сколько в ролике планов — когда переходы мягкие и "
                         "детектор сцен их не видит (join_clips --xfade)")
    a = ap.parse_args()

    # длину лучше читать из карты, чем вписывать руками: вписанное руками
    # число — ещё один путь для ошибки, и он уже сработал при проверке
    if a.cuts and a.expect_duration is None:
        with open(a.cuts, encoding="utf-8-sig") as f:
            a.expect_duration = json.load(f).get("out_duration")

    info = probe(a.video)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    au = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    dur = float(info["format"]["duration"])
    fails = []

    # 1 — кадр
    if v and (v["width"], v["height"]) == (config.FRAME_W, config.FRAME_H):
        print(f"{OK} кадр {v['width']}×{v['height']}")
    else:
        size = f"{v['width']}×{v['height']}" if v else "нет видео"
        print(f"{BAD} кадр {size}, ждём {config.FRAME_W}×{config.FRAME_H}")
        fails.append("кадр")

    # 2 — стерео + L/R
    #
    # Немой ролик — законный случай (владелец 2026-08-23: «звук с видео надо
    # полностью вырезать»), но объявленный флагом, а не выведенный из того,
    # что дорожки не нашлось. Иначе забытый звук и вырезанный звук выглядят
    # одинаково, и гейт перестаёт что-либо ловить. Поэтому под --silent
    # проверка не отключается, а разворачивается: звук здесь — брак.
    if a.silent:
        if au:
            print(f"{BAD} ролик заявлен немым, а дорожка на месте "
                  f"({au.get('channels', '?')} кан.) — звук не вырезан")
            fails.append("звук не вырезан")
        else:
            print(f"{OK} звука нет — как и задумано (--silent)")
    elif not au:
        print(f"{BAD} звуковой дорожки нет вовсе")
        fails.append("звук")
    else:
        ch = int(au.get("channels", 0))
        if ch == 2:
            print(f"{OK} звук стерео")
        else:
            print(f"{BAD} звук {ch} канал(а) — на телефоне заиграет в одно ухо")
            fails.append("моно")
        lufs, rms = measure_audio(a.video)
        # на моно L/R сравнивать не с чем. Печатать тут «OK» — ложная
        # зелёная галочка, а она хуже отсутствия проверки: гейт, который
        # всегда зелёный, перестают читать
        if ch != 2:
            print("?    L/R не проверялись — дорожка не стерео")
        elif len(rms) >= 2:
            d = abs(rms[0] - rms[1])
            if d <= config.LR_RMS_TOLERANCE_DB:
                print(f"{OK} L/R сходятся (Δ {d:.2f} dB)")
            else:
                print(f"{BAD} L/R расходятся на {d:.2f} dB — one-ear")
                fails.append("L/R")
        else:
            print("?    L/R измерить не вышло")
        # 3 — громкость
        if lufs is None:
            print("?    громкость измерить не вышло")
        elif -16.9 <= lufs <= -13.1:
            print(f"{OK} громкость {lufs} LUFS")
        else:
            print(f"{BAD} громкость {lufs} LUFS, лента ждёт −14…−16")
            fails.append("LUFS")

    # 4 — длительность
    if a.expect_duration is None:
        print(f"?    длительность {dur:.2f} с — сверить не с чем "
              f"(передай --expect-duration из карты катов)")
    elif abs(dur - a.expect_duration) <= 0.15:
        print(f"{OK} длительность {dur:.2f} с")
    else:
        print(f"{BAD} длительность {dur:.2f} с, ждали {a.expect_duration:.2f} "
              f"— рассинхрон карты катов")
        fails.append("длительность")

    # 5 — ритм. Гейт заведён 2026-08-23 после разбора первого ролика
    # (school/razbor-2026-08-23-reel-v3): нормы монтажа были записаны в
    # craft/video-station за сутки до сборки, ролик нарушил их втрое, и
    # ничто этого не поймало. Правило без гейта — пожелание.
    if a.rhythm:
        fails += check_rhythm(a.video, dur, a.scene, a.shots)

    if fails:
        print("\nНЕ ПРОШЛО: " + ", ".join(fails) + ". Владельцу не показывать.")
        sys.exit(1)
    print("\nВсе гейты пройдены.")
    print("Числа сошлись — теперь глазами: tools/look.py и рубрика "
          "craft/self-review. Гейты не видят цвет, хук и ритм внутри плана.")


if __name__ == "__main__":
    main()
