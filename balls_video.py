"""Render a video of one ball per sandbox provider, each crossing its row in the provider's median `1 + 1` time.

    uv run balls_video.py

Times are the medians in results/, slowed down by SLOWDOWN. Needs ffmpeg, and writes sandbox_balls.mp4.
The layout copies Benjamin Dicken's "1 Billion nested loop iterations" video. The icons in logos/ are each
provider's site icon.
"""

import json
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# results file, icon in logos/, ball colour
STYLES = {
    'logfire_turbo': ('pydantic.dev', (230, 32, 225)),
    'logfire': ('pydantic.dev', (240, 150, 200)),
    'modal': ('modal.com', (98, 190, 90)),
    'e2b': ('e2b.dev', (245, 170, 60)),
    'cloudflare_sandbox': ('cloudflare.com', (243, 100, 30)),
    'daytona': ('daytona.io', (110, 180, 235)),
    'vercel': ('vercel.com', (20, 20, 20)),
    'boat': ('boat.dev', (40, 60, 170)),
}
ROOT = Path(__file__).parent


def providers() -> list[tuple[str, int, str, tuple[int, int, int]]]:
    """Name, median ms for `1 + 1`, icon and colour of each provider in results/, fastest first."""
    found = []
    for key, (icon, colour) in STYLES.items():
        result = json.loads((ROOT / 'results' / f'{key}.json').read_text())
        found.append((result['provider'], result['cases']['1 + 1']['median'], icon, colour))
    return sorted(found, key=lambda p: p[1])


PROVIDERS = providers()
W, H, FPS, SECONDS = 1200, 1080, 60, 40
SLOWDOWN = 15
DARK = (62, 62, 62)
PANEL = (236, 236, 236)
FRAME = (50, 180, 1150, 1050)
BORDER = 12
ROW_H = (FRAME[3] - FRAME[1] - 2 * BORDER - 16) // len(PROVIDERS)
ROW_TOP = FRAME[1] + BORDER + 8
ICON = 60
LABEL_X0, LABEL_X1 = 140, 590
RADIUS = ROW_H // 2 - 4
# the ball's centre goes between these
TRACK_X0, TRACK_X1 = LABEL_X1 + 6 + RADIUS, FRAME[2] - BORDER - 6 - RADIUS

label_font = ImageFont.truetype('/System/Library/Fonts/Menlo.ttc', 25)
small = ImageFont.truetype('/System/Library/Fonts/Menlo.ttc', 22)
title_font = ImageFont.truetype('/System/Library/Fonts/Menlo.ttc', 50, index=1)


def background() -> Image.Image:
    img = Image.new('RGB', (W, H), 'white')
    d = ImageDraw.Draw(img)
    d.text((W // 2, 70), 'Sandboxes running code', font=title_font, fill='black', anchor='mm')
    d.text(
        (W // 2, 132),
        f'median time for a new session, shown {SLOWDOWN}x slower',
        font=small,
        fill=(110, 110, 110),
        anchor='mm',
    )
    d.rectangle(FRAME, fill=PANEL, outline=DARK, width=BORDER)
    for i, (name, ms, icon, _) in enumerate(PROVIDERS):
        y0 = ROW_TOP + i * ROW_H
        y = y0 + ROW_H // 2
        logo = Image.open(ROOT / 'logos' / f'{icon}.png').convert('RGBA').resize((ICON, ICON), Image.LANCZOS)
        img.paste(logo, (FRAME[0] + BORDER + 10, y - ICON // 2), logo)
        d.rectangle((LABEL_X0, y0 + 4, LABEL_X1, y0 + ROW_H - 4), fill=DARK)
        d.text(((LABEL_X0 + LABEL_X1) // 2, y), f'{name} ({ms}ms)', font=label_font, fill='white', anchor='mm')
    return img


def ball(colour: tuple[int, int, int]) -> Image.Image:
    """A circle with a thin dark edge, drawn large and scaled down to smooth it."""
    big = 8 * RADIUS
    img = Image.new('RGBA', (big, big), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((0, 0, big - 1, big - 1), fill=colour, outline=(40, 40, 40), width=6)
    return img.resize((2 * RADIUS, 2 * RADIUS), Image.LANCZOS)


def position(t_ms: float, ms: float) -> int:
    """Pixels along the track at a time, going there and back at a constant speed."""
    phase = (t_ms / ms) % 2
    return round((phase if phase < 1 else 2 - phase) * (TRACK_X1 - TRACK_X0))


def main() -> None:
    base = background()
    balls = [ball(colour) for *_, colour in PROVIDERS]
    ffmpeg = subprocess.Popen(
        ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}']
        + ['-r', str(FPS), '-i', '-', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '17', 'sandbox_balls.mp4'],
        stdin=subprocess.PIPE,
    )
    assert ffmpeg.stdin
    for f in range(FPS * SECONDS):
        img = base.copy()
        t_ms = f * 1000 / FPS / SLOWDOWN
        for i, (_, ms, *_) in enumerate(PROVIDERS):
            y = ROW_TOP + i * ROW_H + ROW_H // 2
            img.paste(balls[i], (TRACK_X0 - RADIUS + position(t_ms, ms), y - RADIUS), balls[i])
        ffmpeg.stdin.write(np.asarray(img).tobytes())
    ffmpeg.stdin.close()
    ffmpeg.wait()


if __name__ == '__main__':
    main()
