"""Рендер сцены в mp4: каждый кадр снимается браузером и уходит в ffmpeg.

Кадр детерминированный: страница не крутит анимацию сама, время задаётся
вызовом seek(t). Значит один и тот же кадр всегда выглядит одинаково.

    python render.py                 # весь ролик
    python render.py --shots 1.2 7.4 # только контрольные кадры в work/
"""
import argparse
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
SCENE_FILE = "scene-v2.html"      # правится тут, если сцен станет больше
W, H, FPS, DUR = 1080, 1920, 30, 18.0


def logo_alpha():
    """Марка лежит на своём фоне-плашке; в кадре она нужна без плашки.

    Фон марки — тот же графит #0a1929, что и фон ролика, но за логотипом идёт
    свечение, и прямоугольник плашки становится виден. Поэтому фон вырезается
    в прозрачность один раз, в work/ (в git не едет).
    """
    dst = HERE / "work" / "logo-alpha.png"
    if dst.exists():
        return dst
    from PIL import Image
    src = Image.open(r"C:\Claude\m4ksi\alya\assets\logo\m4ksi-wordmark-horizontal.png").convert("RGB")
    out = Image.new("RGBA", src.size)
    bg = (10, 25, 41)
    sp, dp = src.load(), out.load()
    for y in range(src.size[1]):
        for x in range(src.size[0]):
            r, g, b = sp[x, y]
            d = max(abs(r - bg[0]), abs(g - bg[1]), abs(b - bg[2]))
            dp[x, y] = (r, g, b, min(255, int(d * 255 / 45)))
    dst.parent.mkdir(exist_ok=True)
    out.save(dst)
    return dst


def browser(p, scene):
    b = p.chromium.launch(args=["--allow-file-access-from-files",
                                "--force-color-profile=srgb",
                                "--disable-lcd-text",
                                "--font-render-hinting=none"])
    page = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
    page.goto((HERE / scene).as_uri() + "?manual=1")
    page.evaluate("u => document.getElementById('logo').src = u", logo_alpha().as_uri())
    page.wait_for_timeout(900)          # шрифты и логотип
    return b, page


def shots(times, scene):
    out = HERE / "work"
    out.mkdir(exist_ok=True)
    with sync_playwright() as p:
        b, page = browser(p, scene)
        for t in times:
            page.evaluate("t => window.seek(t)", t)
            page.screenshot(path=str(out / f"kadr-{t:05.2f}.png".replace(".", "_", 1)))
            print("kadr", t)
        b.close()
    print("kadry:", out)


def video(dst: Path, scene: str):
    dst.parent.mkdir(exist_ok=True)
    n = int(DUR * FPS)
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "image2pipe", "-framerate", str(FPS), "-i", "-",
         "-c:v", "libx264", "-preset", "slow", "-crf", "17",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dst)],
        stdin=subprocess.PIPE)
    with sync_playwright() as p:
        b, page = browser(p, scene)
        for i in range(n):
            page.evaluate("t => window.seek(t)", i / FPS)
            ff.stdin.write(page.screenshot(type="png"))
            if i % 30 == 0:
                print(f"  {i/FPS:5.1f} s / {DUR:.0f}", flush=True)
        b.close()
    ff.stdin.close()
    if ff.wait() != 0:
        sys.exit("ffmpeg упал")
    print("gotovo:", dst, f"({dst.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", nargs="*", type=float)
    ap.add_argument("--scene", default=SCENE_FILE)
    ap.add_argument("--out", default=str(HERE / "out" / "m4ksi-agent-obrashcheniya.mp4"))
    a = ap.parse_args()
    if a.shots is not None:
        shots(a.shots or [0.6, 1.8, 3.6, 5.0, 7.0, 9.6, 11.2, 13.4, 15.2, 17.2], a.scene)
    else:
        video(Path(a.out), a.scene)
