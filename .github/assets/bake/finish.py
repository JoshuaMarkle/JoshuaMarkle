#!/usr/bin/env python3
"""Turn captured frames of the site's halo into a seamless loop with a VHS tracking glitch on it,
then encode it as GIF and animated WebP.

usage: finish.py FRAMES_DIR OUT_DIR [--width 1200] [--loop 300] [--fade 60] [--grain 0.5]

The capture runs LOOP + FADE frames. The last FADE frames are blended into the first FADE, so the
loop's end flows into its start. The site already has grain and woven lines; what it does not have is
the tracking glitch, a band that rolls down and drags the picture sideways, pulling its colours apart.

Grain: capture with the site's own grain off ('{"grain":0}'). Its grain is new every frame, which no
GIF can squeeze (every pixel changes every frame: ~100 MB). Here it is laid back on as one pattern that
holds still, the way the site weighs it (strongest in the mid-tones, none on black), so a pixel only
changes when the light under it does.
"""
import argparse, json, os, subprocess
import numpy as np
from PIL import Image

ap = argparse.ArgumentParser()
ap.add_argument("frames"); ap.add_argument("out")
ap.add_argument("--width", type=int, default=1200)
ap.add_argument("--loop", type=int, default=300)
ap.add_argument("--fade", type=int, default=60)
ap.add_argument("--grain", type=float, default=0.5)
ap.add_argument("--gif-width", type=int, default=960, help="GIF is ~4x the WebP; 960 keeps it under GitHub's 50 MB warning")
ap.add_argument("--quality", type=int, default=70, help="WebP quality")
a = ap.parse_args()
os.makedirs(os.path.join(a.out, "png"), exist_ok=True)
fps = json.load(open(os.path.join(a.frames, "clip.json")))["fps"]
load = lambda i: np.asarray(Image.open(os.path.join(a.frames, f"f{i:04d}.png")).convert("RGB")).astype(np.float32) / 255
smooth = lambda x: x * x * (3 - 2 * x)

# glitches: (start s, length s, strength). A band rolls from top to bottom over the length
GLITCH = [(1.1, 0.55, 1.0), (3.9, 0.9, 0.7), (4.05, 0.25, 1.3)]
rng = np.random.default_rng(4)

def glitch(img, t):
    h, w, _ = img.shape
    out = img.copy()
    y = np.arange(h)
    for t0, L, k in GLITCH:
        u = (t - t0) / L
        if not 0 <= u <= 1: continue
        c = -0.15 * h + u * 1.3 * h                       # centre of the band
        bw = 0.07 * h
        env = np.exp(-((y - c) / bw) ** 2) * k * np.sin(np.pi * u) ** 0.5
        if env.max() < 0.01: continue
        # each row is dragged its own way: a smooth swing, plus a little jitter that changes every frame
        shove = env * (0.022 * w) * (0.6 + 0.4 * np.sin(y * 0.09 + t * 37)) + env * rng.normal(0, 0.004 * w, h)
        split = env * 0.006 * w                           # how far red and blue pull apart
        for ch, extra in ((0, split), (1, 0), (2, -split)):
            sh = np.round(shove + extra).astype(int)
            idx = (np.arange(w)[None, :] - sh[:, None]) % w
            out[:, :, ch] = np.take_along_axis(img[:, :, ch], idx, axis=1)
        # the band itself is lighter and noisier, with a few bright threads through it
        lift = env[:, None, None]
        out = out * (1 + 0.25 * lift) + lift * 0.05 * rng.random((h, w, 1))
        threads = (rng.random(h) < 0.06 * env) * rng.uniform(0.3, 0.8, h)
        out += threads[:, None, None] * np.array([0.9, 0.85, 1.0]) * (rng.random((h, w, 1)) < 0.7)
    return np.clip(out, 0, 1)

N, K = a.loop, a.fade
h0, w0, _ = load(0).shape
H = round(a.width * h0 / w0 / 2) * 2
# one field of grain for the whole loop: a shared part and a little per channel, like the site's
g = np.random.default_rng(9)
G = 0.62 * g.normal(0, 0.5, (H, a.width, 1)) + 0.30 * g.normal(0, 0.5, (H, a.width, 3))

def grain(f):
    l = f @ np.array([0.3, 0.55, 0.15], np.float32)
    amp = a.grain * (0.012 + 0.34 * np.sqrt(np.clip(l, 0, 1)) * (1 - 0.55 * l)) * np.clip(f.max(-1) / 0.03, 0, 1)
    return np.clip(f + amp[..., None] * G, 0, 1)
for i in range(N):
    f = load(i)
    if i < K:                                             # the end of the capture flows into its start
        wgt = smooth(i / K)
        f = (1 - wgt) * load(N + i) + wgt * f
    f = glitch(f, i / fps)
    img = Image.fromarray(np.round(f * 255).astype(np.uint8)).resize((a.width, H), Image.LANCZOS)
    if a.grain: img = Image.fromarray(np.round(grain(np.asarray(img).astype(np.float32) / 255) * 255).astype(np.uint8))
    img.save(os.path.join(a.out, "png", f"o{i:04d}.png"))
    if i % 50 == 0: print(f"frame {i}/{N}", flush=True)

src = os.path.join(a.out, "png", "o%04d.png")
gif = os.path.join(a.out, "halo.gif")
webp = os.path.join(a.out, "halo.webp")
# one palette for the whole loop, from every frame, so colours don't shimmer from frame to frame
subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", str(fps), "-i", src, "-vf",
                # ordered dither: the same colour always dithers the same way, so still parts stay still between frames
                f"scale={a.gif_width}:-2:flags=lanczos,split[a][b];[a]palettegen=max_colors=256:stats_mode=full[p];[b][p]paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle",
                "-loop", "0", gif], check=True)
subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", str(fps), "-i", src, "-c:v", "libwebp_anim",
                "-quality", str(a.quality), "-compression_level", "6", "-loop", "0", webp], check=True)
for p in (gif, webp): print(p, f"{os.path.getsize(p) / 1e6:.1f} MB")
