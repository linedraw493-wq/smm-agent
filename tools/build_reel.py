#!/usr/bin/env python3
"""Сборка вертикального ролика 1080×1920 (craft/video-station).

    python build_reel.py work/clip.mp4 -o out/reel.mp4 \
        [--audio work/voice.wav] [--subs work/subs.ass] [--hdr] [--fade 0.4]

Жёсткий порядок фильтров, менять нельзя:
    тонмап → кроп/скейл в вертикаль → плашки → субтитры → фейд → экспорт

Почему порядок жёсткий: плашка кладётся на уже-SDR кадр. Тонмапить после
композа нельзя — графитовый navy уходит в мутно-серый. Это код-гейт №3.

Экспорт: crf 22 + потолок 7M — дефолт под живой/пёстрый фон. Без потолка
листва раздувает файл вдвое ни за что.
"""
import argparse, json, os, subprocess, sys
import config


def esc(p):
    """Путь внутрь фильтра ffmpeg: слэши вперёд, двоеточие диска экранировано."""
    bs = chr(92)
    return p.replace(bs, "/").replace(":", bs + ":").replace("'", bs + "'")


# Профили экспорта. Слово владельца 2026-08-23: «картинка должна быть очень
# качественной, насыщенные цвета, детализация, тени, фокусировка».
#
# Канон цеха держал crf 22 с потолком 7M — он экономил битрейт на пёстрой
# листве. Под требование качества дефолт поднят: площадка всё равно пережмёт,
# но чем чище исходник, тем лучше её кодировщик отработает. Плата — размер
# файла, и она принята сознательно.
QUALITY = {
    "high":  {"crf": 19, "maxrate": "12M", "bufsize": "24M"},   # дефолт
    "max":   {"crf": 16, "maxrate": "20M", "bufsize": "40M"},   # графика, экран
    "feed":  {"crf": 22, "maxrate": "7M",  "bufsize": "14M"},   # канон, экономный
}

# Обработка картинки. Цель — насыщенность, детализация, тени, резкость,
# но без «мыла наоборот»: перешарп на лице виден сразу и выглядит дёшево.
LOOK = {
    # ничего. Для уже отгрейженного материала и для кожи крупным планом
    "natural": None,
    # дефолт: аккуратный подъём насыщенности и контраста, тени чуть глубже,
    # мягкая резкость по яркости (по цвету не трогаем — полезут артефакты)
    "rich": ("eq=saturation=1.14:contrast=1.06:gamma=0.98,"
             "curves=all='0/0 0.22/0.18 0.75/0.79 1/1',"
             "unsharp=luma_msize_x=5:luma_msize_y=5:luma_amount=0.7"
             ":chroma_amount=0"),
    # для записи экрана: резкость выше, насыщенность почти не трогаем —
    # интерфейсы и так насыщенные, а текст должен быть острым
    "screen": ("eq=saturation=1.04:contrast=1.08,"
               "unsharp=luma_msize_x=3:luma_msize_y=3:luma_amount=1.1"
               ":chroma_amount=0"),
}


def load_cuts(path):
    with open(path, encoding="utf-8-sig") as f:
        d = json.load(f)
    return d["cuts"], d.get("out_duration")


# select с суммой between() короче и быстрее, но парсер выражений ffmpeg
# ломается на длинной строке: 193 куска (5224 символа) он уже не разбирает —
# поймано 2026-08-23 на сорокаминутном материале. Поэтому выше порога
# собираем trim+concat: длиннее граф, зато без предела.
SELECT_MAX_CUTS = 40


def select_expr(cuts):
    return "+".join("between(t,%.3f,%.3f)" % (float(c["src_in"]), float(c["src_out"]))
                    for c in cuts)


def trim_graph(cuts, with_audio):
    """trim+concat: по звену на кусок. Работает на любом числе кусков."""
    parts, labels = [], []
    for i, c in enumerate(cuts):
        s, e = float(c["src_in"]), float(c["src_out"])
        parts.append("[0:v]trim=start=%.3f:end=%.3f,setpts=PTS-STARTPTS[v%d]" % (s, e, i))
        labels.append("[v%d]" % i)
        if with_audio:
            parts.append("[0:a]atrim=start=%.3f:end=%.3f,asetpts=PTS-STARTPTS[a%d]"
                         % (s, e, i))
            labels.append("[a%d]" % i)
    n = len(cuts)
    if with_audio:
        parts.append("".join(labels) + "concat=n=%d:v=1:a=1[cv][ca]" % n)
    else:
        parts.append("".join(labels) + "concat=n=%d:v=1:a=0[cv]" % n)
    return ";".join(parts)


def probe_size(path):
    r = subprocess.run(
        [config.FFPROBE, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", path],
        capture_output=True, text=True, check=True)
    st = (json.loads(r.stdout).get("streams") or [{}])[0]
    return int(st.get("width", 0)), int(st.get("height", 0))


def fit_chain(path, mode):
    """Как горизонтальный кадр становится вертикальным 1080x1920.

    Центральный кроп 16:9 выбрасывает ДВЕ ТРЕТИ ширины. Для говорящей головы
    это терпимо, для записи экрана — уничтожение: пропадают края интерфейса,
    ради которых ролик и снимался. Проверено 2026-08-23 на тестовой записи:
    от кадра 1920x1080 уцелела середина, оба края с текстом срезало.

    Поэтому режим выбирается по исходнику, а не берётся один на всё.
    """
    W, H = config.FRAME_W, config.FRAME_H
    sw, sh = probe_size(path)
    src_ar = (sw / sh) if sh else 0.5625

    if mode == "auto":
        # сколько ширины съест кроп; больше трети — не режем, вписываем
        keep = (W / H) / src_ar if src_ar else 1.0
        mode = "crop" if keep >= 0.66 else "blur"
        print("--fit auto -> %s (исходник %dx%d, кроп сохранил бы %d%% ширины)"
              % (mode, sw, sh, round(keep * 100)))

    cover = ("scale=%d:%d:force_original_aspect_ratio=increase" % (W, H))
    contain = ("scale=%d:%d:force_original_aspect_ratio=decrease" % (W, H))

    if mode == "crop":
        return cover + ",crop=%d:%d" % (W, H)
    if mode == "top":
        return cover + ",crop=%d:%d:(iw-%d)/2:0" % (W, H, W)
    if mode == "bottom":
        return cover + ",crop=%d:%d:(iw-%d)/2:ih-%d" % (W, H, W, H)
    if mode == "solid":
        bg = "0x%02x%02x%02x" % config.BG[:3]
        return (contain + ",pad=%d:%d:(ow-iw)/2:(oh-ih)/2:%s" % (W, H, bg))
    # blur: кадр целиком, за ним размытая растянутая копия — она заполняет
    # поля, не отвлекая. Стандарт для записи экрана в вертикальной ленте.
    return ("split=2[bg][fg];"
            "[bg]" + cover + ",crop=%d:%d,gblur=sigma=28,eq=brightness=-0.12[bgb];"
            "[fg]" % (W, H) + contain + "[fgs];"
            "[bgb][fgs]overlay=(W-w)/2:(H-h)/2")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("video")
    ap.add_argument("-o", "--out", default="reel.mp4")
    ap.add_argument("--audio", default=None)
    ap.add_argument("--subs", default=None)
    ap.add_argument("--overlay", default=None, help="PNG плашек на весь кадр")
    ap.add_argument("--hdr", action="store_true", help="исходник HLG/HDR с телефона")
    ap.add_argument("--fade", type=float, default=0.0, help="фейд в конце, с")
    ap.add_argument("--crf", type=int, default=None, help="перебить crf профиля")
    ap.add_argument("--fit", choices=["auto", "crop", "top", "bottom", "blur", "solid"],
                    default="auto", help="как горизонтальный кадр становится вертикальным")
    ap.add_argument("--cuts", default=None, help="карта катов work/cuts.json")
    ap.add_argument("--look", choices=sorted(LOOK), default="rich",
                    help="обработка картинки: насыщенность, тени, резкость")
    ap.add_argument("--quality", choices=sorted(QUALITY), default="high",
                    help="профиль экспорта")
    a = ap.parse_args()

    if not os.path.exists(a.video):
        sys.exit(f"нет файла: {a.video}")

    cmd = [config.FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", a.video]
    if a.audio:
        cmd += ["-i", a.audio]
    if a.overlay:
        cmd += ["-i", a.overlay]

    # граф собирается по звеньям с явными метками: режим blur ветвится
    # (split), и склейкой через запятую его не собрать
    filt = ""
    src_v, cut_audio = "[0:v]", None
    if a.cuts:
        cuts, expected = load_cuts(a.cuts)
        cut_a = not a.audio          # свой голос уже порезан, исходный — нет
        print(f"карта катов: {len(cuts)} кусков, ожидаемая длина {expected} с")
        if len(cuts) <= SELECT_MAX_CUTS:
            filt = "[0:v]select='%s',setpts=N/FRAME_RATE/TB[cv]" % select_expr(cuts)
            if cut_a:
                filt += ";[0:a]aselect='%s',asetpts=N/SR/TB[ca]" % select_expr(cuts)
        else:
            print(f"  кусков больше {SELECT_MAX_CUTS} — собираю trim+concat "
                  f"(выражение select столько не переваривает)")
            filt = trim_graph(cuts, cut_a)
        src_v = "[cv]"
        cut_audio = "[ca]" if cut_a else None
        filt += ";"

    filt += src_v
    if a.hdr:
        filt += config.TONEMAP + ","    # ГЕЙТ: тонмап первым
    filt += f"fps={config.FPS}[pre];[pre]" + fit_chain(a.video, a.fit)
    # грейд ПОСЛЕ кадрирования и ДО плашек: шарпить готовую плашку нельзя —
    # у неё появится каёмка, и текст станет грязным
    if LOOK[a.look]:
        filt += "," + LOOK[a.look]
    filt += "[base]"
    last = "base"
    if a.overlay:
        idx = 2 if a.audio else 1
        filt += f";[{last}][{idx}:v]overlay=0:0[ov]"
        last = "ov"
    if a.subs:
        # fontsdir — libass берёт шрифты из assets/fonts/, ставить в систему не надо
        filt += (f";[{last}]ass='{esc(os.path.abspath(a.subs))}'"
                 f":fontsdir='{esc(config.FONTS)}'[sub]")
        last = "sub"
    if a.fade > 0:
        dur = probe_duration(a.video)
        st = max(0.0, dur - a.fade)
        filt += f";[{last}]fade=t=out:st={st:.3f}:d={a.fade}[fin]"
        last = "fin"

    # звук режется той же картой, что и картинка — иначе разъедется.
    # Если голос пришёл отдельным файлом, он уже обработан и порезан: берём как есть.
    amap = cut_audio if cut_audio else ("1:a" if a.audio else "0:a?")
    cmd += ["-filter_complex", filt, "-map", f"[{last}]", "-map", amap]
    q = QUALITY[a.quality]
    crf = a.crf if a.crf is not None else q["crf"]
    cmd += [
        "-c:v", "libx264", "-preset", config.X264_PRESET, "-crf", str(crf),
        "-maxrate", q["maxrate"], "-bufsize", q["bufsize"],
        "-pix_fmt", "yuv420p", "-r", str(config.FPS),
        "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-ar", "48000",
        "-movflags", "+faststart", a.out,
    ]
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    subprocess.run(cmd, check=True)
    print(f"{a.out}: собран (картинка {a.look}, качество {a.quality} crf {crf}).")
    print("Дальше обязательно qa.py — гейты не пропускать.")


def probe_duration(path):
    r = subprocess.run(
        [config.FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


if __name__ == "__main__":
    main()
