#!/usr/bin/env python3
"""Build a self-contained animated SVG of the site's "halo" name: black letters with light
spilling out from behind them, mapped through the Ember palette with thin-film iridescence.

Everything is SVG filters + SMIL, so it animates inside an <img> (GitHub README) with no JS.
usage: build_halo.py FONT.woff OUT.svg
"""
import math, sys
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

FONT, OUT = sys.argv[1], sys.argv[2]
LINES = ["JOSHUA", "MARKLE"]
W, H = 1200, 560
CAP = 150            # cap height in px
TRACK = -0.02        # em, as on the site
LEAD = 1.32          # line pitch in cap heights

# ---------- glyphs to paths ----------
f = TTFont(FONT)
upm = f["head"].unitsPerEm
cmap, gs, hmtx = f.getBestCmap(), f.getGlyphSet(), f["hmtx"]
capH = getattr(f["OS/2"], "sCapHeight", 0) or upm * 0.7
s = CAP / capH
kern = {}
if "kern" in f:
    for t in f["kern"].kernTables: kern.update(t.kernTable)

def line_path(text, y):
    names = [cmap[ord(c)] for c in text]
    adv = [hmtx[n][0] for n in names]
    width = sum(adv) + sum(kern.get((a, b), 0) for a, b in zip(names, names[1:])) + TRACK * upm * (len(names) - 1)
    x = (W / s - width) / 2
    pen = SVGPathPen(gs, ntos=lambda v: f"{v:.1f}".rstrip("0").rstrip("."))
    for i, n in enumerate(names):
        gs[n].draw(TransformPen(pen, (s, 0, 0, -s, x * s, y)))
        x += adv[i] + TRACK * upm + (kern.get((n, names[i + 1]), 0) if i + 1 < len(names) else 0)
    return pen.getCommands()

top = (H - CAP * (1 + LEAD * (len(LINES) - 1))) / 2
d = " ".join(line_path(t, top + CAP + i * CAP * LEAD) for i, t in enumerate(LINES))

# ---------- palette (Ember), oklab-interpolated like src/palettes.js ----------
STOPS = [(0, '#000000'), (0.16, '#0d0424'), (0.34, '#3f13b0'), (0.5, '#7a2cff'), (0.63, '#b63db0'), (0.73, '#ff2a1a'), (0.86, '#ff8d1f'), (1, '#ffe6a3')]
hexf = lambda h: [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
lin = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
gam = lambda c: c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
def oklab(rgb):
    r, g, b = map(lin, rgb)
    l, m, q = (math.copysign(abs(v) ** (1 / 3), v) for v in (0.4122214708*r+0.5363325363*g+0.0514459929*b, 0.2119034982*r+0.6806995451*g+0.1073969566*b, 0.0883024619*r+0.2817188376*g+0.6299787005*b))
    return [0.2104542553*l+0.793617785*m-0.0040720468*q, 1.9779984951*l-2.428592205*m+0.4505937099*q, 0.0259040371*l+0.7827717662*m-0.808675766*q]
def from_oklab(L, a, b):
    l, m, q = (L+0.3963377774*a+0.2158037573*b)**3, (L-0.1055613458*a-0.0638541728*b)**3, (L-0.0894841775*a-1.291485548*b)**3
    return [gam(min(1, max(0, c))) for c in (4.0767416621*l-3.3077115913*m+0.2309699292*q, -1.2684380046*l+2.6097574011*m-0.3413193965*q, -0.0041960863*l-0.7034186147*m+1.707614701*q)]
LAB = [(p, oklab(hexf(h))) for p, h in STOPS]
def lut(t):
    t = min(.999, max(.001, t))
    k = next(i for i in range(len(LAB) - 1) if t <= LAB[i + 1][0])
    (p0, c0), (p1, c1) = LAB[k], LAB[k + 1]
    u = (t - p0) / (p1 - p0)
    return from_oklab(*[a + (b - a) * u for a, b in zip(c0, c1)])

smooth = lambda a, b, x: (lambda t: t * t * (3 - 2 * t))(min(1, max(0, (x - a) / (b - a))))
IRID = 0.35
def pal(v, film):
    c = lut(v)
    fl = [.5 - .5 * math.cos(12.566 * 1.33 * film * (.55 + .9 * v) / lam) for lam in (640, 540, 450)]
    k = IRID * smooth(.04, .3, v)
    return [min(1, ci * (1 + (fi * 1.75 - 1) * k)) for ci, fi in zip(c, fl)]

N = 48
def tables(film):
    rows = [pal(i / (N - 1), film) for i in range(N)]
    return [" ".join(f"{r[ch]:.3f}" for r in rows) for ch in range(3)]

# film thickness drifts, so the iridescent bands turn through their colours
FILMS = [420, 455, 490, 520, 490, 455, 420, 395, 420]
FILM_DUR = "14s"
ch_anims = []
for ch, tag in enumerate("RGB"):
    vals = ";".join(tables(fm)[ch] for fm in FILMS)
    ch_anims.append(f'<feFunc{tag} type="table" tableValues="{tables(FILMS[0])[ch]}"><animate attributeName="tableValues" dur="{FILM_DUR}" repeatCount="indefinite" values="{vals}"/></feFunc{tag}>')

# ---------- noise that loops: a stitched tile, repeated, then slid by exactly one tile ----------
def noise(name, tw, th, fx, fy, seed, dur, dx, dy):
    return f'''
    <feTurbulence type="fractalNoise" baseFrequency="{fx} {fy}" numOctaves="2" seed="{seed}" stitchTiles="stitch" x="0" y="0" width="{tw}" height="{th}" result="{name}t"/>
    <feTile in="{name}t" x="{-M}" y="{-M}" width="{W+2*M}" height="{H+2*M}" result="{name}r"/>
    <feOffset in="{name}r" result="{name}">
      <animate attributeName="dx" from="0" to="{dx*tw}" dur="{dur}" repeatCount="indefinite"/>
      <animate attributeName="dy" from="0" to="{dy*th}" dur="{dur}" repeatCount="indefinite"/>
    </feOffset>'''

M = 640
# tiles sized so baseFrequency * tile is a whole number (needed for stitching to be exact)
n1 = noise("n1", 600, 560, 5/600, 4/560, 7, "26s", 1, -1)
n2 = noise("n2", 400, 280, 7/400, 5/280, 19, "17s", -1, 1)

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
  <title>Joshua Markle</title>
  <defs>
    <filter id="halo" filterUnits="userSpaceOnUse" x="{-M}" y="{-M}" width="{W+2*M}" height="{H+2*M}" color-interpolation-filters="sRGB">
      <!-- heat: two layers of boiling noise, pushed hard so the light pools in patches -->{n1}{n2}
      <feComposite in="n1" in2="n2" operator="arithmetic" k2="0.74" k3="0.26" result="nn"/>
      <feColorMatrix in="nn" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  2.6 0 0 0 -1.15" result="heat"/>

      <!-- distance from the letters, four ways -->
      <feGaussianBlur in="SourceAlpha" stdDeviation="1.6" result="b0"/>
      <feGaussianBlur in="SourceAlpha" stdDeviation="6" result="b1"/>
      <feGaussianBlur in="SourceAlpha" stdDeviation="16" result="b2"/>
      <feGaussianBlur in="SourceAlpha" stdDeviation="46" result="b3"/>

      <!-- body of the glow: a violet rim everywhere, widening and heating where the noise runs hot -->
      <feComposite in="b2" in2="heat" operator="arithmetic" k1="1.45" result="hb2"/>
      <feComposite in="b3" in2="heat" operator="arithmetic" k1="1.6" result="hb3"/>
      <feComposite in="b1" in2="hb2" operator="arithmetic" k2="0.8" k3="1" result="g1"/>
      <feComposite in="g1" in2="hb3" operator="arithmetic" k2="1" k3="1" result="body"/>
      <feComposite in="body" in2="SourceAlpha" operator="out" result="outer"/>

      <!-- the hairline round every letter: b0*(1-b0) peaks right on the edge -->
      <feComposite in="b0" in2="b0" operator="arithmetic" k1="-2" k2="1" k3="1" result="edge"/>
      <feComposite in="outer" in2="edge" operator="arithmetic" k2="1" k3="1" result="v"/>

      <!-- heat to colour: alpha becomes grey, grey goes through the palette and the film -->
      <feColorMatrix in="v" type="matrix" values="0 0 0 1 0  0 0 0 1 0  0 0 0 1 0  0 0 0 0 1" result="grey"/>
      <feComponentTransfer in="grey">
        {ch_anims[0]}
        {ch_anims[1]}
        {ch_anims[2]}
      </feComponentTransfer>
    </filter>
    <path id="name" d="{d}"/>
  </defs>
  <rect width="{W}" height="{H}" fill="#000"/>
  <use href="#name" fill="#fff" filter="url(#halo)"/>
</svg>
'''
open(OUT, "w").write(svg)
print(OUT, len(svg), "bytes")
