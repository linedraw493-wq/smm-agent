#!/usr/bin/env python3
"""Склейка нескольких источников в один клип для сборки.

    python join_clips.py raw/01.mp4 raw/02.mp4 ... -o work/clip.mp4 --hdr

Зачем. `build_reel.py` берёт РОВНО ОДИН входной файл: он режет внутри него по
карте катов, но склеивать разные источники не умеет и не должен. Когда владелец
приносит семь отдельных видео, между ними и сборкой нужен этот шаг.

Что делает с каждым куском, в этом порядке:
    тонмап (если HDR) → приведение к одной частоте кадров → вертикаль 1080x1920
и только потом склеивает. Порядок тот же, что в сборке, и по той же причине
(craft/video-station): тонмапить после склейки — значит тонмапить уже
испорченное, а приводить fps после — получить рассинхрон звука.

ЧЕГО ЭТОТ МОДУЛЬ НЕ ДЕЛАЕТ. Не грейдит, не кладёт плашки, не вешает субтитры.
Он выдаёт промежуточный клип, дальше работает `build_reel.py`. Промежуток
пишется с crf 16 — это заведомо избыточно, чтобы второй проход не наследовал
артефакты первого.

РАЗНАЯ ЧАСТОТА КАДРОВ — не мелочь. Айфон снимает то 60, то 30. Склеить их без
приведения — тихий брак: картинка идёт, а звук уезжает, и гейт длительности
поймает это уже после сборки.
"""
import argparse
import os
import subprocess
import sys

import build_reel
import config
import shot_match
import shot_stats


def parse_spec(spec):
    """path · path@in:out · path@in:out:speed — кусок с подрезкой и скоростью.

    Подрезка делается ЗДЕСЬ, а не после склейки, и это принципиально: гнать
    через тонмап и масштаб две минуты, чтобы потом выкинуть полторы, —
    впустую сожжённый прогон. Плюс карта катов по склеенному файлу требует
    пересчёта таймингов при любой правке, а тут правится одно число.

    СКОРОСТЬ: 0.5 — вдвое медленнее, 2.0 — вдвое быстрее.

    Почему замедление тут честное, а не «резиновое». Материал снят на 60
    кадров, а лента принимает 30. На 0.5x каждый снятый кадр показывается
    ровно один раз — это НАСТОЯЩЕЕ замедление, без придуманных промежуточных
    кадров и без рывков. Ниже 0.5x с 60 fps начнётся дёрганье: кадров уже не
    хватает, и fps=30 будет их дублировать.

    Клип, снятый на 30 кадров, замедлять нельзя вовсе — модуль об этом
    предупредит: там каждый второй кадр окажется копией предыдущего.
    """
    if "@" not in spec:
        return spec, None, None, 1.0
    path, _, rng = spec.rpartition("@")
    parts = rng.split(":")
    try:
        if len(parts) == 2:
            return path, float(parts[0]), float(parts[1]), 1.0
        if len(parts) == 3:
            sp = float(parts[2])
            if sp <= 0:
                sys.exit("скорость должна быть больше нуля: " + spec)
            return path, float(parts[0]), float(parts[1]), sp
    except ValueError:
        pass
    sys.exit("не разобрала кусок: %s (жду path@начало:конец[:скорость])" % spec)


def src_fps(info):
    """r_frame_rate вида '60000/1001' -> 59.94"""
    try:
        a, b = info["fps"].split("/")
        return float(a) / float(b)
    except (ValueError, ZeroDivisionError):
        return 0.0


def probe(path):
    import json
    r = subprocess.run(
        [config.FFPROBE, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate,color_transfer",
         "-show_entries", "format=duration", "-of", "json", path],
        capture_output=True, text=True, check=True)
    d = json.loads(r.stdout)
    st = (d.get("streams") or [{}])[0]
    return {
        "w": int(st.get("width", 0)),
        "h": int(st.get("height", 0)),
        "fps": st.get("r_frame_rate", "0/1"),
        "trc": st.get("color_transfer", ""),
        "dur": float(d.get("format", {}).get("duration", 0) or 0),
    }


def has_audio(path):
    r = subprocess.run(
        [config.FFPROBE, "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=index", "-of", "csv=p=0", path],
        capture_output=True, text=True)
    return bool(r.stdout.strip())


def main():
    ap = argparse.ArgumentParser(description="Склеить источники в один клип")
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--hdr", action="store_true",
                    help="источники HDR/HLG — тонмапить каждый перед склейкой")
    ap.add_argument("--fit", default="auto",
                    choices=["auto", "crop", "top", "bottom", "blur", "solid"])
    ap.add_argument("--crf", type=int, default=16, help="качество промежутка")
    ap.add_argument("--mute", action="store_true",
                    help="выбросить звук совсем (владелец просит немой ряд)")
    ap.add_argument("--match", action="store_true",
                    help="выровнять куски друг под друга ДО общего вида: "
                         "телефон ставит баланс белого заново на каждую съёмку")
    ap.add_argument("--match-strength", type=float, default=shot_match.STRENGTH,
                    help="насколько тянуть к среднему, 0..1 (по умолчанию 0.75)")
    ap.add_argument("--xfade", type=float, default=0.0,
                    help="плавный переход между кусками, с (0 — встык)")
    a = ap.parse_args()

    specs = [parse_spec(x) for x in a.inputs]
    for p, _, _, _ in specs:
        if not os.path.exists(p):
            sys.exit("нет файла: " + p)

    if a.mute:
        with_audio = False
        print("звук выброшен целиком (--mute)")
    else:
        # звук берём только если он есть у ВСЕХ: concat с разным набором
        # дорожек молча роняет его у части кусков — искать потом замучаешься
        auds = [has_audio(p) for p, _, _, _ in specs]
        with_audio = all(auds)
        if any(auds) and not with_audio:
            print("! звук есть не у всех кусков — собираю без звука, "
                  "иначе concat потеряет его молча")

    # выравнивание считается ДО построения графа: нужно знать все куски,
    # чтобы найти среднее, к которому их тянуть
    fixes = [None] * len(specs)
    if a.match:
        print("замер кусков для выравнивания ...")
        measured = []
        for p, t_in, t_out, _ in specs:
            seg = (t_in, t_out) if t_in is not None else None
            st = shot_stats.stats_of(p, a.hdr, 5, seg)
            if st is None:
                sys.exit("не удалось замерить " + p)
            measured.append(st)
        tgt = shot_match.targets(measured)
        print("  цель: яркость %.3f · насыщ %.3f · средние каналов "
              "R%.3f G%.3f B%.3f"
              % (tgt["яркость"], tgt["насыщ"], tgt["mR"], tgt["mG"], tgt["mB"]))
        for i, (st, (p, _, _, _)) in enumerate(zip(measured, specs)):
            chain, report, notes = shot_match.correction(st, tgt, a.match_strength)
            fixes[i] = chain
            print("  %s: %s" % (os.path.basename(p), report))
            for nt in notes:
                print("    ! " + nt)
        print("")

    parts, labels, total, takes = [], [], 0.0, []
    for i, (p, t_in, t_out, speed) in enumerate(specs):
        info = probe(p)
        raw_take = info["dur"] if t_in is None else (t_out - t_in)
        take = raw_take / speed          # на экране кусок идёт СТОЛЬКО
        if t_in is not None and t_out > info["dur"]:
            sys.exit("%s: просят до %.2f с, а клип длится %.2f"
                     % (os.path.basename(p), t_out, info["dur"]))
        # замедление ниже, чем позволяет частота съёмки, даёт дубли кадров
        fps_in = src_fps(info)
        if speed < 1.0 and fps_in * speed < config.FPS - 0.5:
            print("  ! %s снят на %.0f кадров: на %.2fx получится %.0f "
                  "против нужных %d — пойдут дубли и рывки"
                  % (os.path.basename(p), fps_in, speed, fps_in * speed, config.FPS))
        total += take
        takes.append(take)
        # w/h тут — как в контейнере; реальную геометрию (с поворотом)
        # знает build_reel.probe_size, её и печатаем
        dw, dh = build_reel.probe_size(p)
        sp_note = "" if speed == 1.0 else ("  %.2fx" % speed)
        print("%2d. %s  %dx%d%s  %s fps  %s  берём %.2f -> %.2f с%s"
              % (i + 1, os.path.basename(p), dw, dh,
                 " (повёрнут)" if (dw, dh) != (info["w"], info["h"]) else "",
                 info["fps"], info["trc"] or "sdr", raw_take, take, sp_note))

        chain = ""
        if t_in is not None:
            chain += "trim=start=%.3f:end=%.3f,setpts=PTS-STARTPTS," % (t_in, t_out)
        if speed != 1.0:
            # PTS/speed: speed<1 растягивает время (замедление), >1 сжимает.
            # Ставится ДО fps=30 — так нормализация частоты видит уже
            # растянутый поток и раскладывает кадры равномерно.
            chain += "setpts=PTS/%.6f," % speed
        if a.hdr:
            chain += config.TONEMAP + ","
        if fixes[i]:
            # покусковая правка стоит ПОСЛЕ тонмапа (мерили тонмапленное)
            # и ДО масштабирования — на полном кадре меньше видно полосы
            chain += fixes[i] + ","
        chain += "fps=%d," % config.FPS
        chain += build_reel.fit_chain(p, a.fit)
        chain += ",setsar=1"
        parts.append("[%d:v]%s[v%d]" % (i, chain, i))
        labels.append("[v%d]" % i)
        if with_audio:
            atrim = ("atrim=start=%.3f:end=%.3f," % (t_in, t_out)) if t_in is not None else ""
            if speed != 1.0:
                # atempo держит высоту тона; вне 0.5..2.0 его надо каскадом,
                # а до этого случая доживём — пока честно откажемся
                if not (0.5 <= speed <= 2.0):
                    sys.exit("скорость %.2f со звуком не вытяну одним atempo "
                             "(нужен каскад). Либо --mute, либо 0.5..2.0" % speed)
                atrim += "atempo=%.6f," % speed
            parts.append("[%d:a]%saresample=48000,aformat=sample_fmts=fltp:"
                         "channel_layouts=stereo,asetpts=PTS-STARTPTS[a%d]"
                         % (i, atrim, i))
            labels.append("[a%d]" % i)

    n = len(specs)
    if a.xfade > 0:
        if with_audio:
            sys.exit("xfade со звуком пока не сведён — гоняй с --mute")
        # xfade цепочкой по парам. Смещение каждого следующего перехода —
        # сумма длин до него МИНУС уже съеденное предыдущими переходами:
        # каждый переход укорачивает ролик ровно на свою длительность.
        vlabels = [l for l in labels if l.startswith("[v")]
        durs = takes[:]
        for d in durs:
            if d <= a.xfade:
                sys.exit("кусок короче перехода (%.2f <= %.2f): "
                         "либо длиннее кусок, либо короче переход" % (d, a.xfade))
        cur = vlabels[0]
        acc = durs[0]
        for k in range(1, n):
            out = "[x%d]" % k if k < n - 1 else "[outv]"
            off = acc - a.xfade
            parts.append("%s%sxfade=transition=fade:duration=%.3f:offset=%.3f%s"
                         % (cur, vlabels[k], a.xfade, off, out))
            # после xfade длина склеенного = смещение + длина второго куска
            acc = off + durs[k]
            cur = out
        total = total - a.xfade * (n - 1)
        print("переходы: %d штук по %.2f с, ролик короче на %.2f с"
              % (n - 1, a.xfade, a.xfade * (n - 1)))
    elif with_audio:
        parts.append("".join(labels) + "concat=n=%d:v=1:a=1[outv][outa]" % n)
    else:
        parts.append("".join(labels) + "concat=n=%d:v=1:a=0[outv]" % n)

    cmd = [config.FFMPEG, "-y", "-hide_banner", "-loglevel", "error"]
    for p, _, _, _ in specs:
        cmd += ["-i", p]
    cmd += ["-filter_complex", ";".join(parts), "-map", "[outv]"]
    if with_audio:
        cmd += ["-map", "[outa]", "-c:a", "aac", "-b:a", "256k",
                "-ac", "2", "-ar", "48000"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", str(a.crf),
            "-pix_fmt", "yuv420p", "-r", str(config.FPS),
            "-movflags", "+faststart", a.out]

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    print("\nсклейка %d кусков, ожидаемая длина %.2f с ..." % (n, total))
    subprocess.run(cmd, check=True)

    got = probe(a.out)["dur"]
    print("%s: %.2f с (ожидали %.2f, расхождение %.2f с)"
          % (a.out, got, total, abs(got - total)))
    # тот же гейт, что и после сборки: рассинхрон concat — тихий брак
    if abs(got - total) > 0.5:
        sys.exit("ГЕЙТ ДЛИТЕЛЬНОСТИ НЕ ПРОЙДЕН: склейка разъехалась. "
                 "Не подрезать вручную — разбираться, какой кусок виноват.")
    print("гейт длительности пройден.")


if __name__ == "__main__":
    main()
