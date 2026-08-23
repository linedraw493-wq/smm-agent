#!/usr/bin/env python3
"""Транскрипт со словными таймингами → work/words.json.

    python transcribe.py <аудио-или-видео> [-o work/words.json] [--lang ru]

Модель качается при первом запуске (~1.5 ГБ) в tools/models/ — вне git.

⚠️ Whisper врёт на первых словах: кладёт речь в тишину. Начало ролика резать
по энергии сигнала, а не по этому таймингу (craft/subtitles).
"""
import argparse, json, os, sys
import config


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--lang", default=config.WHISPER_LANG)
    ap.add_argument("--model", default=config.WHISPER_MODEL)
    a = ap.parse_args()

    if not os.path.exists(a.src):
        sys.exit(f"нет файла: {a.src}")
    out = a.out or os.path.join(os.path.dirname(a.src) or ".", "words.json")

    from faster_whisper import WhisperModel
    os.makedirs(config.MODELS, exist_ok=True)
    print(f"модель {a.model} (CPU int8), язык {a.lang}...", file=sys.stderr)
    model = WhisperModel(a.model, device="cpu", compute_type="int8",
                         download_root=config.MODELS)

    segments, info = model.transcribe(a.src, language=a.lang,
                                      word_timestamps=True, vad_filter=True)
    words, text = [], []
    for seg in segments:
        text.append(seg.text.strip())
        for w in (seg.words or []):
            words.append({"w": w.word.strip(), "s": round(w.start, 3),
                          "e": round(w.end, 3), "p": round(w.probability, 3)})

    data = {"src": os.path.abspath(a.src), "lang": info.language,
            "duration": round(info.duration, 3),
            "text": " ".join(text), "words": words}
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"{out}: {len(words)} слов, {data['duration']} с")


if __name__ == "__main__":
    main()
