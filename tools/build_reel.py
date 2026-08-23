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
    ap.add_argument("--crf", type=int, default=config.CRF)
    ap.add_argument("--fit", choices=["auto", "crop", "top", "bottom", "blur", "solid"],
                    default="auto", help="как горизонтальный кадр становится вертикальным")
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
    filt = "[0:v]"
    if a.hdr:
        filt += config.TONEMAP + ","    # ГЕЙТ: тонмап первым
    filt += f"fps={config.FPS}[pre];[pre]" + fit_chain(a.video, a.fit) + "[base]"
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

    cmd += ["-filter_complex", filt, "-map", f"[{last}]"]
    cmd += ["-map", "1:a" if a.audio else "0:a?"]
    cmd += [
        "-c:v", "libx264", "-preset", config.X264_PRESET, "-crf", str(a.crf),
        "-maxrate", config.MAXRATE, "-bufsize", config.BUFSIZE,
        "-pix_fmt", "yuv420p", "-r", str(config.FPS),
        "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-ar", "48000",
        "-movflags", "+faststart", a.out,
    ]
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    subprocess.run(cmd, check=True)
    print(f"{a.out}: собран. Дальше обязательно qa.py — гейты не пропускать.")


def probe_duration(path):
    r = subprocess.run(
        [config.FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


if __name__ == "__main__":
    main()
