#!/usr/bin/env python3
"""Чистка и мастеринг голоса → стерео, −16 LUFS (craft/audio).

    python audio_clean.py <вход> -o work/voice.wav [--rnnoise models/bd.rnnn]

Цепочка: highpass=100 → arnndn mix=0.85 → afftdn nr=7 → loudnorm последней.
Границы найдены прогонами: mix=1.0 — «водянистый» голос, nr=10 — звон,
−14 LUFS + LRA 9 — поднимает артефакты.

Модели RNNoise (.rnnn) в поставке ffmpeg нет — без неё шаг arnndn
пропускается, и об этом печатается предупреждение. Это честнее, чем тихо
собрать по другой цепочке.

Экспорт **всегда стерео**: моно на телефоне играет в одно ухо — это был
живой баг. Проверка L/R — в qa.py.
"""
import argparse, os, subprocess, sys
import config


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src")
    ap.add_argument("-o", "--out", default="voice.wav")
    ap.add_argument("--rnnoise", default=None, help="путь к модели .rnnn")
    ap.add_argument("--lufs", type=float, default=config.LUFS_TARGET)
    a = ap.parse_args()

    if not os.path.exists(a.src):
        sys.exit(f"нет файла: {a.src}")

    if a.rnnoise and os.path.exists(a.rnnoise):
        model = a.rnnoise.replace(chr(92), "/").replace(":", chr(92) + ":")
        chain = config.VOICE_CHAIN.format(rnnoise=model)
    else:
        chain = config.VOICE_CHAIN_NORNN
        print("! модели RNNoise нет — arnndn пропущен, чистка слабее",
              file=sys.stderr)

    # моно-голос разводится в оба канала ДО нормализации; loudnorm последней
    chain += (
        f",pan=stereo|c0=c0|c1=c0"
        f",loudnorm=I={a.lufs}:TP={config.TRUE_PEAK}:LRA={config.LRA}"
    )

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    cmd = [config.FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
           "-i", a.src, "-af", chain, "-ac", "2", "-ar", "48000", a.out]
    subprocess.run(cmd, check=True)
    print(f"{a.out}: стерео 48 кГц, цель {a.lufs} LUFS")


if __name__ == "__main__":
    main()
