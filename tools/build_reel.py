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
    # ⚠️ ОТМЕНЁН 2026-08-23. Оставлен только для пересборки старых выпусков.
    #
    # Профиль нарушал сразу два собственных правила ремесла, записанных в
    # craft/video-station: eq=contrast=1.06 ПОВЕРХ curves (контраст тянется
    # дважды, оба конца уходят в стену — механизм пересветов) и unsharp
    # поверх ужатия 2160→1080 (каёмки по контурам — «странная резкость»).
    # Правило было записано, дефолтный код его не исполнял.
    #
    # Дефолт переведён на `alive`: слово владельца, третья правка подряд —
    # «вместо насыщенности цветов ты вытягиваешь контраст, яркость».
    # Тон не трогается вообще, поднимается только цвет.
    "rich": "vibrance=intensity=0.50",
    # для записи экрана: резкость выше, насыщенность почти не трогаем —
    # интерфейсы и так насыщенные, а текст должен быть острым
    "screen": ("eq=saturation=1.04:contrast=1.08,"
               "unsharp=luma_msize_x=3:luma_msize_y=3:luma_amount=1.1"
               ":chroma_amount=0"),
    # «киношный». Слово владельца 2026-08-23: «ярко вытягивает контраст,
    # тени и насыщает цвета в более природные, но яркие», НЕ сплошной фильтр.
    #
    # Профиль подобран НЕ на глаз, а стендом `grade_lab.py` по доле выбитых
    # и задавленных пикселей. Предыдущая версия (кривая + eq=contrast сверху)
    # выжигала 6.8% кадра в белое и давила 20% в чёрное — владелец забраковал.
    # Здесь: выбито 0.01%, пик 0.09%, чёрного 0.00%, насыщенность 0.321
    # против 0.169 у исходника.
    #
    # Три решения и почему именно они:
    # 1. Контраст — ТОЛЬКО кривой, никакого eq=contrast сверху. Именно эта
    #    пара и выжгла прошлую версию: кривая тянет, а eq тянет ещё раз.
    #    Плечо 0.88->0.925 (наклон к белому 0.62) ужимает подход к 255
    #    вместо того, чтобы втыкаться в него.
    # 2. ПОДНЯТЫЙ ЧЁРНЫЙ 0->0.012. Приём плёнки: низ садится чуть выше нуля.
    #    Замер: доля пикселей в абсолютном чёрном падает с 1.07% (исходник)
    #    до 0.00%. Тени глубокие, но с деталью — ровно то, чего владельцу
    #    не хватало.
    # 3. vibrance вместо eq=saturation. Vibrance тянет бледное сильнее
    #    насыщенного: зелень оживает, кожа не уходит в загар и каналы не
    #    клипуют поодиночке. eq=saturation дёргает всё поровну и выбивает
    #    то, что и так было ярким.
    #
    # Резкости здесь НЕТ намеренно. unsharp поверх двукратного ужатия рисует
    # каёмки — это и была «странная резкость». Детали берёт lanczos в
    # fit_chain, на самом масштабировании.
    # «живой» — то, что владелец просил с самого начала и чего я дважды
    # не сделала. Слово владельца 2026-08-23, третья правка подряд:
    # «вместо насыщенности цветов ты вытягиваешь контраст, яркость —
    # ты ошиблась в формулировке и настройке».
    #
    # Он прав буквально. Профиль cinematic поднимал кривой 0.62->0.665 и
    # 0.88->0.925 — это подъём ЯРКОСТИ. Насыщенность при этом ушла на 0.321
    # при том, что естественный уровень на его же фотографии — 0.222.
    # Натуральность убита ровно этим: тон тянули, цвет перекрутили.
    #
    # Здесь ТОН НЕ ТРОГАЕТСЯ ВООБЩЕ. Ни кривой, ни contrast, ни gamma,
    # ни brightness. Только цвет, и только до естественного уровня.
    #
    # Работает это лишь в паре с покусковым выравниванием (--match в
    # join_clips): без него профиль ляжет на куски, которые сами по себе
    # разной светлоты и белизны, и «разный цветокор» останется.
    # Величина подобрана стендом, не на глаз. Замер на выровненном материале:
    #   как есть      яркость 0.416, насыщ 0.160
    #   vibrance 0.40 яркость 0.417, насыщ 0.214
    #   vibrance 0.50 яркость 0.417, насыщ 0.226   <- взято
    #   vibrance 0.65 яркость 0.417, насыщ 0.244
    #   отвергнутый v3 яркость 0.433, насыщ 0.304
    # Ориентир — фотография владельца того же дня: насыщенность 0.222.
    # Яркость во всех вариантах с чистым цветом стоит на 0.417 и не
    # шевелится; у отвергнутого профиля она уехала на 0.433. Это и есть
    # разница между «насытить цвет» и «поднять яркость».
    "alive": "vibrance=intensity=0.50",

    "cinematic": ("colorbalance=bs=0.028:rh=0.014:bh=-0.010,"
                  "curves=all='0/0.012 0.10/0.095 0.30/0.30 0.62/0.665 "
                  "0.88/0.925 1/1',"
                  "vibrance=intensity=0.85"),
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
    """Размер кадра КАК ЕГО ВИДНО, с учётом поворота в метаданных.

    Телефон пишет вертикальное видео горизонтальным кадром плюс матрица
    поворота: ffprobe покажет 3840x2160, а декодер выдаст 2160x3840.
    Взять сырые width/height — значит принять вертикальный материал за
    горизонтальный и включить кадрирование там, где кадрировать нечего.
    Поймано 2026-08-23 на семи клипах с айфона: fit=auto ушёл в blur и
    подставил размытые поля вокруг и без того вертикального кадра.
    """
    r = subprocess.run(
        [config.FFPROBE, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height:stream_side_data=rotation",
         "-of", "json", path],
        capture_output=True, text=True, check=True)
    st = (json.loads(r.stdout).get("streams") or [{}])[0]
    w, h = int(st.get("width", 0)), int(st.get("height", 0))

    rot = 0
    for sd in st.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(float(sd["rotation"]))
            break
    if rot == 0:                      # старые файлы держат поворот в тегах
        try:
            rot = int(float(st.get("tags", {}).get("rotate", 0)))
        except (TypeError, ValueError):
            rot = 0

    if abs(rot) % 180 == 90:
        w, h = h, w
    return w, h


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

    # flags=lanczos, а не дефолтный бикубик. Ужатие 2160->1080 двукратное:
    # бикубик отдаёт мягкий кадр, который потом «спасают» нерезкой маской —
    # и получают каёмки по контурам. Владелец назвал это «странная резкость»
    # 2026-08-23. Lanczos берёт детали на самом ужатии, и unsharp не нужен.
    cover = ("scale=%d:%d:force_original_aspect_ratio=increase:flags=lanczos" % (W, H))
    contain = ("scale=%d:%d:force_original_aspect_ratio=decrease:flags=lanczos" % (W, H))

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
    ap.add_argument("--hdr", action="store_true", help="исходник HLG/PQ с телефона")
    ap.add_argument("--npl", type=int, default=None,
                    help="порог тонмапа: НЕ константа, а параметр материала. "
                         "Подбирается свипом на самом светлом кадре "
                         "(craft/color.md), дефолт %d" % config.NPL_DEFAULT)
    ap.add_argument("--fade", type=float, default=0.0, help="фейд в конце, с")
    ap.add_argument("--crf", type=int, default=None, help="перебить crf профиля")
    ap.add_argument("--fit", choices=["auto", "crop", "top", "bottom", "blur", "solid"],
                    default="auto", help="как горизонтальный кадр становится вертикальным")
    ap.add_argument("--cuts", default=None, help="карта катов work/cuts.json")
    ap.add_argument("--look", choices=sorted(LOOK), default="alive",
                    help="обработка картинки. Дефолт alive: поднимает ЦВЕТ и "
                         "не трогает тон (слово владельца 2026-08-23). "
                         "rich отменён, оставлен для пересборки старых выпусков")
    ap.add_argument("--grade", default=None,
                    help="готовая цепочка фильтров вместо профиля --look; "
                         "её считает grade_match.py по референс-фотографии. "
                         "Задана — --look игнорируется (два грейда подряд "
                         "накладываются и дают перекрут)")
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
        filt += config.tonemap(a.npl) + ","    # ГЕЙТ: тонмап первым
        print(f"тонмап: npl={a.npl or config.NPL_DEFAULT}, desat=2")
    filt += f"fps={config.FPS}[pre];[pre]" + fit_chain(a.video, a.fit)
    # грейд ПОСЛЕ кадрирования и ДО плашек: шарпить готовую плашку нельзя —
    # у неё появится каёмка, и текст станет грязным
    grade = a.grade if a.grade else LOOK[a.look]
    if a.grade:
        print("грейд: цепочка из замера (--look %s не применяется)" % a.look)
    if grade:
        filt += "," + grade
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
    look_name = "замер по референсу" if a.grade else a.look
    print(f"{a.out}: собран (картинка {look_name}, качество {a.quality} crf {crf}).")
    print("Дальше обязательно qa.py — гейты не пропускать.")


def probe_duration(path):
    r = subprocess.run(
        [config.FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


if __name__ == "__main__":
    main()
