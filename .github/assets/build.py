#!/usr/bin/env python3
"""Build the README's animated SVGs in the style of joshuamarkle.com: black shapes with light
spilling out from behind them, mapped through the Ember palette with thin-film iridescence,
then printed onto VHS (lines, grain, a tracking jolt).

Everything is SVG filters + SMIL, so it animates inside an <img> (GitHub README) with no JS.

  halo.svg          the name
  divider.svg       a bar of the same light, the height of a badge
  bead.svg          the site's drop of glass with the whole gradient in it

usage: build.py [SITE_DIR]   (default ../joshuamarkle, for the font)
"""
import math, os, sys
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "../../../joshuamarkle")
FONT = os.path.join(SITE, "node_modules/@fontsource/special-gothic-expanded-one/files/special-gothic-expanded-one-latin-400-normal.woff")

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
film_rgb = lambda film, x: [.5 - .5 * math.cos(12.566 * 1.33 * film * x / lam) for lam in (640, 540, 450)]
IRID = 0.35
def pal(v, film, lo=0.0, hi=1.0):
    c = lut(lo + (hi - lo) * v)
    fl = film_rgb(film, .55 + .9 * v)
    k = IRID * smooth(.04, .3, v)
    return [min(1, ci * (1 + (fi * 1.75 - 1) * k)) for ci, fi in zip(c, fl)]

# film thickness drifts, so the iridescent bands turn through their colours
FILMS = [420, 455, 490, 520, 490, 455, 420, 395, 420]
def palette_transfer(result, inp="grey", lo=0.0, hi=1.0, n=48, dur="14s"):
    def tables(film):
        rows = [pal(i / (n - 1), film, lo, hi) for i in range(n)]
        return [" ".join(f"{r[ch]:.3f}" for r in rows) for ch in range(3)]
    all_t = [tables(fm) for fm in FILMS]
    fn = "\n        ".join(
        f'<feFunc{tag} type="table" tableValues="{all_t[0][ch]}"><animate attributeName="tableValues" dur="{dur}" repeatCount="indefinite" values="{";".join(t[ch] for t in all_t)}"/></feFunc{tag}>'
        for ch, tag in enumerate("RGB"))
    return f'''<feComponentTransfer in="{inp}" result="{result}">
        {fn}
      </feComponentTransfer>'''

# ---------- noise that loops: a stitched tile, repeated, then slid by exactly one tile ----------
def noise(name, box, tw, th, cx, cy, seed, dur, dx, dy):
    """cx cy: whole number of noise cells across one tile (stitching needs it exact)"""
    x, y, w, h = box
    return f'''
    <feTurbulence type="fractalNoise" baseFrequency="{cx/tw:.6g} {cy/th:.6g}" numOctaves="2" seed="{seed}" stitchTiles="stitch" x="0" y="0" width="{tw}" height="{th}" result="{name}t"/>
    <feTile in="{name}t" x="{x}" y="{y}" width="{w}" height="{h}" result="{name}r"/>
    <feOffset in="{name}r" result="{name}">
      <animate attributeName="dx" from="0" to="{dx*tw}" dur="{dur}" repeatCount="indefinite"/>
      <animate attributeName="dy" from="0" to="{dy*th}" dur="{dur}" repeatCount="indefinite"/>
    </feOffset>'''

def sway(name, fx, fy, seed, dur, dx, dy):
    """noise too big to tile in the margin: it drifts out and back instead of sliding round"""
    return f'''
    <feTurbulence type="fractalNoise" baseFrequency="{fx:.6g} {fy:.6g}" numOctaves="2" seed="{seed}" result="{name}r"/>
    <feOffset in="{name}r" result="{name}">
      <animate attributeName="dx" values="0;{dx:g};0" dur="{dur}" calcMode="spline" keySplines=".45 0 .55 1;.45 0 .55 1" repeatCount="indefinite"/>
      <animate attributeName="dy" values="0;{dy:g};0" dur="{dur}" calcMode="spline" keySplines=".45 0 .55 1;.45 0 .55 1" repeatCount="indefinite"/>
    </feOffset>'''

# grain: one field of fine noise, jumped to a new place a dozen times a second
# kept small: a jump past the filter's edge would leave a strip with no grain, which multiplies to black
JUMPS = [(0, 0), (17, 6), (-9, 13), (25, -7), (-20, -14), (7, 23), (31, 11), (-25, 3)]

def vhs(inp, W, H, M, px=1.0, pitch=4, weave=0.45, grain=0.9, jolt=5, flicker=True):
    """px: canvas units to one pixel as shown, so lines and grain come out the same size everywhere.
    flicker: the grain jumps a dozen times a second; without it the grain holds still"""
    flick = f'''<feOffset in="g0" result="g1">
        <animate attributeName="dx" values="{';'.join(f'{j[0]*px:g}' for j in JUMPS)}" dur="{len(JUMPS)/12:.3f}s" calcMode="discrete" repeatCount="indefinite"/>
        <animate attributeName="dy" values="{';'.join(f'{j[1]*px:g}' for j in JUMPS)}" dur="{len(JUMPS)/12:.3f}s" calcMode="discrete" repeatCount="indefinite"/>
      </feOffset>''' if flicker else '<feOffset in="g0" result="g1"/>'
    P = pitch * px
    out = ""
    if jolt:
        out += f'''
      <!-- tracking: a soft band rolls down the picture and shoves what it passes sideways -->
      <feFlood flood-color="#808080" result="mid"/>
      <feFlood flood-color="#ff8080" x="{-M}" width="{W+2*M}" height="{26*px:g}" y="{-60*px:g}" result="band0">
        <animate attributeName="y" values="{-60*px:g};{-60*px:g};{H+40*px:g}" keyTimes="0;0.62;1" dur="9s" repeatCount="indefinite"/>
      </feFlood>
      <feGaussianBlur in="band0" stdDeviation="0 {9*px:g}" result="band1"/>
      <feMerge result="bandmap"><feMergeNode in="mid"/><feMergeNode in="band1"/></feMerge>
      <feDisplacementMap in="{inp}" in2="bandmap" scale="{jolt*4*px:g}" xChannelSelector="R" yChannelSelector="G" result="tracked"/>'''
        inp = "tracked"
    out += f'''

      <!-- VHS lines: a row every few px, its threads cut at random -->
      <feFlood flood-color="#fff" x="0" y="0" width="{W}" height="{P*0.5:g}" result="ln0"/>
      <feMerge x="0" y="0" width="{W}" height="{P:g}" result="ln1"><feMergeNode in="ln0"/></feMerge>
      <feTile in="ln1" result="lines"/>
      <feTurbulence type="fractalNoise" baseFrequency="{0.09/px:.3f} {1/P:.3f}" numOctaves="1" seed="3" result="cut0"/>
      <feColorMatrix in="cut0" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  1.8 0 0 0 -0.25" result="cut"/>
      <feComposite in="lines" in2="cut" operator="arithmetic" k1="0.55" k2="0.45" result="th"/>
      <feColorMatrix in="th" type="matrix" values="0 0 0 -{weave} 1  0 0 0 -{weave} 1  0 0 0 -{weave} 1  0 0 0 0 1" result="weave"/>
      <feComposite in="{inp}" in2="weave" operator="arithmetic" k1="1" result="woven"/>

      <!-- grain: multiplies the light, so it is gone on true black -->
      <feTurbulence type="fractalNoise" baseFrequency="{0.85/px:.3f}" numOctaves="1" seed="5" result="g0"/>
      {flick}
      <feColorMatrix in="g1" type="matrix" values="0.55 0.15 0.15 0 0  0.15 0.55 0.15 0 0  0.15 0.15 0.55 0 0  0 0 0 0 1" result="g2"/>
      <feComposite in="woven" in2="g2" operator="arithmetic" k1="{grain*2}" k2="{1-grain*0.85:.3f}"/>'''
    return out

# black becomes see-through, so a picture sits on whatever page it is on
CLEAR = '''
      <feColorMatrix type="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  2.6 2.6 2.6 0 0"/>'''

# ---------- the halo: any white shape, black, with the light coming from behind it ----------
def halo_svg(d, W, H, title, s=1.0, warp=30, px=1.0, jolt=5, heat=1.0, transform=None, ns=1, amb=0.0, clear=False):
    """s: size of the light (blurs and noise), relative to the name. heat: how hard it runs.
    ns: size of the heat noise on top of s. amb: glow in the open background. clear: black goes see-through"""
    M = round(640 * s)
    box = (-M, -M, W + 2 * M, H + 2 * M)
    t = lambda v: round(v * s)
    if ns == 1:
        n1 = noise("n1", box, t(600), t(560), 5, 4, 7, "26s", 1, -1)
        n2 = noise("n2", box, t(400), t(280), 7, 5, 19, "17s", -1, 1)
    else:
        D = 0.75 * M
        n1 = sway("n1", 5 / t(600) / ns, 4 / t(560) / ns, 7, "38s", D, -D * .6)
        n2 = sway("n2", 7 / t(400) / ns, 5 / t(280) / ns, 19, "27s", -D * .8, D * .5)
    wn = noise("wn", box, t(600), t(560), 2, 2, 31, "34s", -1, -1) if warp else ""
    src = "src" if warp else "SourceAlpha"
    bend = f'''

      <!-- the shape bends: slow noise pushes every point of it about -->
      <feDisplacementMap in="SourceAlpha" in2="wn" scale="{warp}" xChannelSelector="R" yChannelSelector="G" result="src"/>''' if warp else ""
    b = lambda v: f"{v * s:.3g}"
    ambient = f'''

      <!-- the open dark: the same heat, faint, so the film shows in it too -->
      <feColorMatrix in="nn" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  1.7 0 0 0 -0.6" result="amb0"/>
      <feComposite in="amb0" in2="{src}" operator="out" result="amb1"/>
      <feComposite in="v0" in2="amb1" operator="arithmetic" k2="1" k3="{amb:g}" result="v"/>''' if amb else ""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
  <title>{title}</title>
  <defs>
    <filter id="halo" filterUnits="userSpaceOnUse" x="{-M}" y="{-M}" width="{W+2*M}" height="{H+2*M}" color-interpolation-filters="sRGB">
      <!-- heat: two layers of boiling noise, pushed hard so the light pools in patches -->{n1}{n2}{wn}
      <feComposite in="n1" in2="n2" operator="arithmetic" k2="0.74" k3="0.26" result="nn"/>
      <feColorMatrix in="nn" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  2.6 0 0 0 -1.15" result="heat"/>{bend}

      <!-- distance from the shape, four ways -->
      <feGaussianBlur in="{src}" stdDeviation="{b(1.6) if s >= .5 else 1.2}" result="b0"/>
      <feGaussianBlur in="{src}" stdDeviation="{b(6)}" result="b1"/>
      <feGaussianBlur in="{src}" stdDeviation="{b(16)}" result="b2"/>
      <feGaussianBlur in="{src}" stdDeviation="{b(46)}" result="b3"/>

      <!-- body of the glow: a violet rim everywhere, widening and heating where the noise runs hot -->
      <feComposite in="b2" in2="heat" operator="arithmetic" k1="{1.45*heat:g}" result="hb2"/>
      <feComposite in="b3" in2="heat" operator="arithmetic" k1="{1.6*heat:g}" result="hb3"/>
      <feComposite in="b1" in2="hb2" operator="arithmetic" k2="0.8" k3="1" result="g1"/>
      <feComposite in="g1" in2="hb3" operator="arithmetic" k2="1" k3="1" result="body"/>
      <feComposite in="body" in2="{src}" operator="out" result="outer"/>

      <!-- the hairline round every edge: b0*(1-b0) peaks right on it -->
      <feComposite in="b0" in2="b0" operator="arithmetic" k1="-2" k2="1" k3="1" result="edge"/>
      <feComposite in="outer" in2="edge" operator="arithmetic" k2="1" k3="1" result="{'v0' if amb else 'v'}"/>{ambient}

      <!-- heat to colour: alpha becomes grey, grey goes through the palette and the film -->
      <feColorMatrix in="v" type="matrix" values="0 0 0 1 0  0 0 0 1 0  0 0 0 1 0  0 0 0 0 1" result="grey"/>
      {palette_transfer("col")}{vhs("col", W, H, M, px=px, jolt=jolt)}{CLEAR if clear else ""}
    </filter>
    <path id="shape"{f' transform="{transform}"' if transform else ''} fill-rule="evenodd" d="{d}"/>
  </defs>
{"" if clear else f'  <rect width="{W}" height="{H}" fill="#000"/>\n'}  <use href="#shape" fill="#fff" filter="url(#halo)"/>
</svg>
'''

# ---------- the divider: a squared-off bar of the heat itself, on black ----------
def divider_svg(W=1200, H=40, px=1.45):
    """H 40 at 1200 wide comes out about as tall as a for-the-badge badge in a README"""
    T = 1800
    box = (-T, 0, W + 2 * T, H)
    # streaks: a few cells across, one down, sliding sideways in opposite directions
    n1 = noise("n1", box, T, H, 4, 1, 7, "63s", 1, 0)
    n2 = noise("n2", box, 1200, H, 7, 1, 19, "39s", -1, 0)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
  <defs>
    <filter id="bar" filterUnits="userSpaceOnUse" x="{-T}" y="0" width="{W+2*T}" height="{H}" color-interpolation-filters="sRGB">{n1}{n2}
      <feComposite in="n1" in2="n2" operator="arithmetic" k2="0.62" k3="0.38" result="nn"/>
      <!-- kept low in the palette: black gaps and violet, warming only now and then -->
      <feColorMatrix in="nn" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  2.1 0 0 0 -0.6" result="v"/>
      <feColorMatrix in="v" type="matrix" values="0 0 0 1 0  0 0 0 1 0  0 0 0 1 0  0 0 0 0 1" result="grey"/>
      {palette_transfer("col")}{vhs("col", W, H, T, px=px, jolt=0, flicker=False)}
    </filter>
  </defs>
  <rect width="{W}" height="{H}" fill="#000" filter="url(#bar)"/>
</svg>
'''

# ---------- the bead: a drop of glass with the whole gradient in it ----------
def bead_svg(R=300, px=1.6):
    C, r = R / 2, R * 0.36
    M = round(R * 0.5)
    box = (-M, -M, R + 2 * M, R + 2 * M)
    swirl = noise("sw", box, 300, 300, 4, 4, 11, "23s", 1, 1)
    glow = lut(.52)
    glow = "#" + "".join(f"{round(c*255):02x}" for c in glow)
    ring = film_rgb(420, .62)
    ringc = "#" + "".join(f"{round(c*255):02x}" for c in ring)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {R} {R}" width="{R}" height="{R}">
  <title>A drop of glass with the whole gradient in it</title>
  <defs>
    <!-- across the drop the palette runs end to end; it turns slowly -->
    <linearGradient id="t" x1=".1" y1="0" x2=".45" y2="0" spreadMethod="reflect">
      <stop offset="0" stop-color="#000"/><stop offset="1" stop-color="#fff"/>
      <animateTransform attributeName="gradientTransform" type="rotate" values="0 .5 .5;360 .5 .5" dur="40s" repeatCount="indefinite"/>
    </linearGradient>
    <radialGradient id="shade" cx=".5" cy=".5" r=".5">
      <stop offset=".55" stop-color="#000" stop-opacity="0"/><stop offset=".93" stop-color="#000" stop-opacity=".45"/><stop offset="1" stop-color="#000" stop-opacity=".7"/>
    </radialGradient>
    <radialGradient id="film" cx=".5" cy=".5" r=".5">
      <stop offset=".8" stop-color="{ringc}" stop-opacity="0"/><stop offset=".96" stop-color="{ringc}" stop-opacity=".3"/><stop offset="1" stop-color="#fff" stop-opacity=".25"/>
      <animate attributeName="r" values=".5;.47;.5" dur="7s" repeatCount="indefinite"/>
    </radialGradient>
    <radialGradient id="glow" cx=".5" cy=".5" r=".5">
      <stop offset=".3" stop-color="{glow}" stop-opacity=".2"/><stop offset=".6" stop-color="{glow}" stop-opacity=".04"/><stop offset="1" stop-color="{glow}" stop-opacity="0"/>
    </radialGradient>
    <filter id="marble" filterUnits="userSpaceOnUse" x="{-M}" y="{-M}" width="{R+2*M}" height="{R+2*M}" color-interpolation-filters="sRGB">{swirl}
      <!-- the noise drags the gradient into swirls, then it goes through the palette -->
      <feDisplacementMap in="SourceGraphic" in2="sw" scale="{R*0.42:g}" xChannelSelector="R" yChannelSelector="G" result="grey0"/>
      <!-- pulled apart: the low half sinks to black, the high half runs hot -->
      <feComponentTransfer in="grey0" result="grey"><feFuncR type="linear" slope="1.7" intercept="-0.45"/><feFuncG type="linear" slope="1.7" intercept="-0.45"/><feFuncB type="linear" slope="1.7" intercept="-0.45"/></feComponentTransfer>
      {palette_transfer("col", lo=0.0, hi=0.95)}
    </filter>
    <filter id="soft" x="-1" y="-1" width="3" height="3"><feGaussianBlur stdDeviation="{R*0.02:g}"/></filter>
    <filter id="tape" filterUnits="userSpaceOnUse" x="{-M}" y="{-M}" width="{R+2*M}" height="{R+2*M}" color-interpolation-filters="sRGB">{vhs("SourceGraphic", R, R, M, px=px, jolt=4)}{CLEAR}
    </filter>
    <clipPath id="drop"><circle cx="{C}" cy="{C}" r="{r:g}"/></clipPath>
  </defs>
  <g filter="url(#tape)">
    <g clip-path="url(#drop)">
      <g filter="url(#marble)"><rect x="{C-r*1.4:g}" y="{C-r*1.4:g}" width="{r*2.8:g}" height="{r*2.8:g}" fill="url(#t)"/></g>
      <circle cx="{C}" cy="{C}" r="{r:g}" fill="url(#shade)"/>
      <circle cx="{C}" cy="{C}" r="{r:g}" fill="url(#film)" style="mix-blend-mode:screen"/>
      <ellipse cx="{C-r*.38:g}" cy="{C-r*.45:g}" rx="{r*.32:g}" ry="{r*.17:g}" transform="rotate(-38 {C-r*.38:g} {C-r*.45:g})" fill="#fff" opacity=".45" filter="url(#soft)"/>
    </g>
    <circle cx="{C}" cy="{C}" r="{r-0.6:g}" fill="none" stroke="#fff" stroke-opacity=".22" stroke-width="1"/>
  </g>
</svg>
'''

# ---------- shapes ----------
def name_path(lines, W, H, cap=150, track=-0.02, lead=1.32):
    f = TTFont(FONT)
    upm = f["head"].unitsPerEm
    cmap, gs, hmtx = f.getBestCmap(), f.getGlyphSet(), f["hmtx"]
    capH = getattr(f["OS/2"], "sCapHeight", 0) or upm * 0.7
    s = cap / capH
    kern = {}
    if "kern" in f:
        for t in f["kern"].kernTables: kern.update(t.kernTable)
    def line(text, y):
        names = [cmap[ord(c)] for c in text]
        adv = [hmtx[n][0] for n in names]
        width = sum(adv) + sum(kern.get((a, b), 0) for a, b in zip(names, names[1:])) + track * upm * (len(names) - 1)
        x = (W / s - width) / 2
        pen = SVGPathPen(gs, ntos=lambda v: f"{v:.1f}".rstrip("0").rstrip("."))
        for i, n in enumerate(names):
            gs[n].draw(TransformPen(pen, (s, 0, 0, -s, x * s, y)))
            x += adv[i] + track * upm + (kern.get((n, names[i + 1]), 0) if i + 1 < len(names) else 0)
        return pen.getCommands()
    top = (H - cap * (1 + lead * (len(lines) - 1))) / 2
    return " ".join(line(t, top + cap + i * cap * lead) for i, t in enumerate(lines))

def write(rel, text):
    p = os.path.join(HERE, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w").write(text)
    print(f"{rel:24} {len(text):>7} bytes")

if __name__ == "__main__":
    write("halo.svg", halo_svg(name_path(["JOSHUA", "MARKLE"], 1200, 560), 1200, 560, "Joshua Markle", warp=45, jolt=7.5, ns=3))
    write("divider.svg", divider_svg())
    write("bead.svg", bead_svg())
