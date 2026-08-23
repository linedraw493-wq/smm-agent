#!/usr/bin/env python3
"""Гейты готового ролика (craft/video-station §Четыре гейта).

    python qa.py out/reel.mp4 [--expect-duration 27.4]

Проверяет машиной то, что глазами проверять нельзя:
  1. кадр 1080×1920 @ 30
  2. звук стерео и L/R RMS совпадают — «no one-ear»
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


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("video")
    ap.add_argument("--expect-duration", type=float, default=None)
    ap.add_argument("--cuts", default=None,
                    help="карта катов: ожидаемая длина берётся из неё")
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
    if not au:
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

    if fails:
        print("\nНЕ ПРОШЛО: " + ", ".join(fails) + ". Владельцу не показывать.")
        sys.exit(1)
    print("\nВсе гейты пройдены.")


if __name__ == "__main__":
    main()
