#!/usr/bin/env python3
"""Единственный источник констант конвейера Али.

Числа взяты из ../alya-vault/craft/. Если число здесь расходится с craft —
**правит craft**, а этот файл догоняет. Не наоборот: ремесло живёт текстом,
код его исполняет.

Стиль — НЕ эти константы. Стиль живёт в рендерере (plate.py). Здесь только
палитра и геометрия, которые рендерер читает.
"""
import os
import shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
ASSETS = os.path.join(REPO, "assets")
FONTS = os.path.join(ASSETS, "fonts")
PRESETS = os.path.join(REPO, "presets")
MODELS = os.path.join(ROOT, "models")

# ─── ffmpeg ───────────────────────────────────────────────────────────────
# winget кладёт бинарь в Links; берём из PATH, иначе ищем в стандартном месте.
def _find(name):
    p = shutil.which(name)
    if p:
        return p
    guess = os.path.expandvars(
        r"%LOCALAPPDATA%\Microsoft\WinGet\Packages"
        r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
    )
    if os.path.isdir(guess):
        for d, _, files in os.walk(guess):
            if name + ".exe" in files:
                return os.path.join(d, name + ".exe")
    return name

FFMPEG = _find("ffmpeg")
FFPROBE = _find("ffprobe")

# ─── кадр ─────────────────────────────────────────────────────────────────
FRAME_W, FRAME_H, FPS = 1080, 1920, 30

# ─── цвета — из палитры, НЕ зашиты ───────────────────────────────────────
# Окончательный дизайн не выбран (владелец 2026-08-23): живут две палитры —
# ink-lime (владельца) и blue-white (Нурса). Код обязан работать с любой.
# Переключение: переменная окружения ALYA_PALETTE или флаг --palette.
# Смотреть все: python palette.py
import palette as _pal

PALETTE = _pal.load()
BG = _pal.rgba(PALETTE["bg"])
PLATE = _pal.rgba(PALETTE["plate"], PALETTE["plate_opacity"])
WHITE = _pal.rgba(PALETTE["text"])
SOFT = _pal.rgba(PALETTE["text_soft"])
HEADING = _pal.rgba(PALETTE["heading"])
ACCENT = _pal.rgba(PALETTE["accent"])
HAIRLINE = _pal.rgba(PALETTE["hairline"])
# на статичной обложке акцент может отличаться (у синей палитры — отличается,
# потому что h264 4:2:0 бледнит синий, а jpg нет)
ACCENT_STILL = _pal.rgba(PALETTE.get("accent_still", PALETTE["accent"]))

# ─── типографика ──────────────────────────────────────────────────────────
KICKER_LETTERSPACING = 0.22   # em, Inter-SemiBold, PIL рисует по-символьно
CROWN_HEURISTIC = 0.55        # макушка = верх лба − 0.55 × высота лица
MARGIN = 54                   # px от низа плашки до макушки

INTER_RG = os.path.join(FONTS, "Inter-Regular.ttf")
INTER_SB = os.path.join(FONTS, "Inter-SemiBold.ttf")
INTER_XB = os.path.join(FONTS, "Inter-ExtraBold.ttf")
PF_SB = os.path.join(FONTS, "PlayfairDisplay-SemiBold.ttf")
PF_IT = os.path.join(FONTS, "PlayfairDisplay-SemiBoldItalic.ttf")

# ─── тонмап HLG/HDR → SDR. ПОРЯДОК: тонмап ПЕРВЫМ, плашки после ───────────
TONEMAP = (
    "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
    "tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p"
)
TONEMAP_COVER = (
    "zscale=t=linear:npl=250,format=gbrpf32le,zscale=p=bt709,"
    "tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p"
)

# ─── звук: жёсткие гейты (craft/audio) ────────────────────────────────────
LUFS_TARGET = -16
TRUE_PEAK = -1
LRA = 11
VOICE_CHAIN = "highpass=100,arnndn=m={rnnoise}:mix=0.85,afftdn=nr=7"
VOICE_CHAIN_NORNN = "highpass=100,afftdn=nr=7"   # если модели RNNoise нет
LR_RMS_TOLERANCE_DB = 0.5     # L и R должны совпасть — «no one-ear»

# ─── экспорт (craft/video-station) ────────────────────────────────────────
CRF = 22
MAXRATE = "7M"
BUFSIZE = "14M"
X264_PRESET = "slow"

# ─── гейт контраста ───────────────────────────────────────────────────────
CONTRAST_FLOOR = 6.6   # WCAG на ярчайшем кадре окна

# ─── субтитры ─────────────────────────────────────────────────────────────
SUBS_WORDS_PER_CARD = (2, 4)     # карта 2–4 слова, вербатим
SUBS_BOTTOM_SAFE = 0.15          # ≥15% высоты кадра снизу свободно
SUBS_STYLE_FILE = os.path.join(PRESETS, "subs-m4ksi.ass")

# ─── распознавание ────────────────────────────────────────────────────────
WHISPER_MODEL = "large-v3"
WHISPER_LANG = "ru"
