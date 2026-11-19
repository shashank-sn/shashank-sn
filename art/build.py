"""Build the animated SVGs used by the profile README.

    pip install fonttools brotli
    python3 art/build.py

Writes assets/<name>.svg for every image. Each SVG carries its own warm
off-white ground, so it reads the same on GitHub's light and dark themes.

Every SVG is self-contained so GitHub renders it through <img>: CSS animation
only, no JS, no external requests. Allo (SIL OFL 1.1, art/fonts/) is subset to
the glyphs each SVG draws and embedded as woff2. The X panel embeds
art/src/banner.jpg and art/src/avatar.jpg.

Every animated element rests in its final state, so a viewer with reduced
motion sees the finished picture.
"""
import base64
import html
import io
import re
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

ART = Path(__file__).resolve().parent
OUT = ART.parent / "assets"
SRC = ART / "src"
FONTS = ART / "fonts"

W = 840  # every image is drawn at README width and scales with width="100%"

# --------------------------------------------------------------------------
# palette: one ground, one ink, one accent
# --------------------------------------------------------------------------
GROUND = "#f5f4ef"  # warm off-white field behind every image
CARD = "#ffffff"  # things that sit on the ground
INK = "#111111"
MUTED = "#8c8a83"
FAINT = "#e3e1d9"  # empty slots, quiet fills
LIME = "#7cf542"  # the accent, always with ink on it
X_BLUE, X_MUTED = "#1d9bf0", "#536471"

FAMILY = "allo"
WEIGHTS = {400: "Allo-Regular.woff2", 500: "Allo-Medium.woff2", 800: "Allo-ExtraBold.woff2"}
FONT = f"'{FAMILY}', -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"

CURSOR = "M0 0 L0 26 L7 19 L12 31 L17 29 L12 17 L22 17 Z"
X_LOGO = ("M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835"
          "L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z")
ELLORA_LOGO = (  # getellora.com/favicon.svg, 24x24
    f'<rect width="24" height="24" rx="5" fill="{INK}"/>'
    f'<g stroke="{CARD}" stroke-width="3.4" stroke-linecap="round">'
    '<line x1="12" y1="3.4" x2="12" y2="20.6"/><line x1="3.4" y1="12" x2="20.6" y2="12"/>'
    '<line x1="5.9" y1="5.9" x2="18.1" y2="18.1"/><line x1="18.1" y1="5.9" x2="5.9" y2="18.1"/></g>'
)
EASE_OUT = "cubic-bezier(.16,1,.3,1)"
SPRING = "cubic-bezier(.34,1.56,.64,1)"

# --------------------------------------------------------------------------
# fonts: measuring and embedding
# --------------------------------------------------------------------------
_fonts = {w: TTFont(FONTS / f) for w, f in WEIGHTS.items()}


def measure(text, size, weight=400, spacing=0.0):
    """advance width of text in px (no kerning, close enough for layout)."""
    font = _fonts[weight]
    cmap, hmtx, upm = font.getBestCmap(), font["hmtx"], font["head"].unitsPerEm
    units = sum(hmtx[cmap.get(ord(c), "space")][0] for c in text)
    return units * size / upm + spacing * len(text)


def glyphs(svg):
    """every character drawn as text: text node contents, not CSS."""
    drawn = re.sub(r"<style>.*?</style>", "", svg, flags=re.S)
    return set(html.unescape("".join(re.findall(r">([^<]+)<", drawn))))


def font_faces(svg):
    """@font-face rules for the Allo weights svg uses, subset to its glyphs."""
    used = {400} | {int(w) for w in re.findall(r'font-weight="(\d+)"', svg)}
    text = "".join(sorted(glyphs(svg))) + " "
    rules = []
    for weight in sorted(used):
        opts = subset.Options()
        opts.flavor = "woff2"
        opts.layout_features = ["kern", "liga", "calt"]
        font = TTFont(FONTS / WEIGHTS[weight])
        sub = subset.Subsetter(opts)
        sub.populate(text=text)
        sub.subset(font)
        buf = io.BytesIO()
        font.flavor = "woff2"
        font.save(buf)
        b64 = base64.b64encode(buf.getvalue()).decode()
        rules.append(f"@font-face{{font-family:'{FAMILY}';font-weight:{weight};"
                     f"src:url(data:font/woff2;base64,{b64}) format('woff2')}}")
    return "".join(rules)


def write(name, h, body, css="", label=""):
    """write <name>.svg: ground, fonts, body, and a reduced-motion switch."""
    css += "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}" viewBox="0 0 {W} {h}" '
        f'role="img" aria-label="{html.escape(label)}" font-family="{FONT}" font-size="16">'
        f"<style>{css}</style>"
        f'<rect width="{W}" height="{h}" rx="24" fill="{GROUND}"/>{body}</svg>'
    )
    head = svg.index(">") + 1
    svg = svg[:head] + f"<style>{font_faces(svg)}</style>" + svg[head:]
    (OUT / f"{name}.svg").write_text(svg + "\n")


def data_uri(path):
    return "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode()


def cursor(element_id="cur"):
    return f'<g id="{element_id}"><path d="{CURSOR}" fill="{INK}" stroke="{CARD}" stroke-width="1.5"/></g>'


def pct(seconds, total):
    return f"{seconds / total * 100:.2f}%"


# --------------------------------------------------------------------------
# shared motion pieces
# --------------------------------------------------------------------------
def odometer(uid, x, y, value, size, weight=800, fill=INK, start=0.4, dur=1.4, total=None, out=None):
    """number whose digits roll up into place, left-aligned at x on baseline y.

    total=None plays once and holds; otherwise the roll repeats every `total`
    seconds, starting at `start`, and the digits fade at `out`.
    """
    lh = size * 1.1
    parts, css, cx = [], [], x
    for i, ch in enumerate(value):
        w = measure(ch, size, weight)
        if not ch.isdigit():
            parts.append(f'<text x="{cx:.1f}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{fill}">{ch}</text>')
            cx += w
            continue
        d = int(ch)
        seq = list(range(10)) + list(range(d + 1))  # one full turn, then land on d
        end = -(len(seq) - 1) * lh
        cid = f"{uid}{i}"
        delay = start + i * 0.12
        parts.append(
            f'<clipPath id="k{cid}"><rect x="{cx - 2:.1f}" y="{y - size * 0.82:.1f}" width="{w + 4:.1f}" height="{size * 0.98:.1f}"/></clipPath>'
            f'<g clip-path="url(#k{cid})"><g id="r{cid}" transform="translate(0 {end:.1f})">'
            + "".join(f'<text x="{cx + w / 2:.1f}" y="{y + k * lh:.1f}" text-anchor="middle" font-size="{size}" '
                      f'font-weight="{weight}" fill="{fill}">{n}</text>' for k, n in enumerate(seq))
            + "</g></g>"
        )
        if total is None:
            css.append(f"@keyframes r{cid}{{from{{transform:translateY(0)}}to{{transform:translateY({end:.1f}px)}}}}"
                       f"#r{cid}{{animation:r{cid} {dur}s {delay:.2f}s both {EASE_OUT}}}")
        else:
            css.append(
                f"@keyframes r{cid}{{0%,{pct(delay, total)}{{transform:translateY(0);animation-timing-function:{EASE_OUT}}}"
                f"{pct(delay + dur, total)},100%{{transform:translateY({end:.1f}px)}}}}"
                f"#r{cid}{{animation:r{cid} {total}s infinite}}"
            )
        cx += w
    return "".join(parts), "".join(css), cx - x


def rise(selector, delay, dist=24, dur=0.9):
    """element slides up into place once (it is already there at rest)."""
    name = re.sub(r"\W", "", selector)
    return (f"@keyframes u{name}{{from{{opacity:0;transform:translateY({dist}px)}}to{{opacity:1;transform:none}}}}"
            f"{selector}{{animation:u{name} {dur}s {delay:.2f}s both {EASE_OUT}}}")


# --------------------------------------------------------------------------
# 1. hero: the name, what got built, and the four numbers
# --------------------------------------------------------------------------
def hero():
    h = 392
    css, body = [], []

    # the name rises out of a mask, word by word
    size, ls, base = 116, -5, 150
    x = 44
    body.append(f'<clipPath id="nm"><rect x="0" y="0" width="{W}" height="{base + 6}"/></clipPath><g clip-path="url(#nm)">')
    for i, word in enumerate(["shashank", "sn"]):
        body.append(f'<text id="w{i}" x="{x:.1f}" y="{base}" font-size="{size}" font-weight="800" letter-spacing="{ls}" fill="{INK}">{word}</text>')
        css.append(f"@keyframes w{i}{{from{{transform:translateY({size}px)}}to{{transform:none}}}}"
                   f"#w{i}{{animation:w{i} 1.1s {0.1 + i * 0.14:.2f}s both {EASE_OUT}}}")
        x += measure(word, size, 800, ls) + 30
    body.append("</g>")

    # "i've built" + a slot that rolls through the builds
    items = ["brands for 150+ companies", "a coffee brand, then sold it", "a newsletter, then sold it",
             "india's first digital wedding invite", "a club that gets india reading", "an ai editor called ellora"]
    psize, lh, line = 30, 46, 238
    prefix = "i've built"
    body.append(f'<text id="pre" x="46" y="{line}" font-size="{psize}" font-weight="500" fill="{MUTED}">{prefix}</text>')
    sx = 46 + measure(prefix, psize, 500) + 12
    top, bottom = line - 38, line + 13
    body.append(
        f'<linearGradient id="fade" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".2" stop-color="#fff" stop-opacity="1"/>'
        '<stop offset=".82" stop-color="#fff" stop-opacity="1"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
        f'<mask id="slot" maskUnits="userSpaceOnUse" x="0" y="{top}" width="{W}" height="{bottom - top}">'
        f'<rect x="0" y="{top}" width="{W}" height="{bottom - top}" fill="url(#fade)"/></mask>'
        f'<g mask="url(#slot)"><g id="roll">'
        + "".join(f'<text x="{sx:.1f}" y="{line + k * lh}" font-size="{psize}" font-weight="800" letter-spacing="-.6" fill="{INK}">{html.escape(t)}</text>'
                  for k, t in enumerate(items + items[:1]))
        + "</g></g>"
    )
    for t in items:
        assert sx + measure(t, psize, 800) < W - 40, f"slot item too wide: {t}"
    step, hold = 2.4, 1.9  # seconds per item, seconds it rests
    total = step * len(items)
    frames = []
    for k in range(len(items)):
        t0 = k * step
        frames.append(f"{pct(t0, total)},{pct(t0 + hold, total)}{{transform:translateY({-k * lh}px);animation-timing-function:{EASE_OUT}}}")
    frames.append(f"100%{{transform:translateY({-len(items) * lh}px)}}")
    css.append(f"@keyframes roll{{{''.join(frames)}}}#roll{{animation:roll {total}s 1.6s infinite}}")
    css.append(rise("#pre", 0.5))

    # the numbers
    stats = [("150+", "companies"), ("100+", "talks"), ("7", "things built"), ("2", "exits")]
    ny, ly = 324, 352
    for i, (num, label) in enumerate(stats):
        cx = 46 + i * 196
        if label == "exits":
            body.append(f'<rect id="hi" x="{cx - 18}" y="{ny - 56}" width="128" height="98" rx="18" fill="{LIME}"/>')
            css.append(f"@keyframes hi{{from{{transform:scaleX(0)}}to{{transform:none}}}}"
                       f"#hi{{transform-box:fill-box;transform-origin:left;animation:hi .7s 1.9s both {EASE_OUT}}}")
        part, c, _ = odometer(f"s{i}", cx, ny, num, 52, start=0.7 + i * 0.15)
        body.append(part)
        css.append(c)
        body.append(f'<text id="l{i}" x="{cx}" y="{ly}" font-size="17" font-weight="500" fill="{INK}">{label}</text>')
        css.append(rise(f"#l{i}", 1.0 + i * 0.15, 10, 0.7))
    write("hero", h, "".join(body), "".join(css),
          "shashank sn. i've built brands for 150+ companies, a coffee brand and a newsletter (both sold), "
          "india's first digital wedding invite, a reading club and an ai editor. 150+ companies, 100+ talks, 7 things built, 2 exits.")


# --------------------------------------------------------------------------
# 2. builds: the things i made, dealt onto the table like cards
# --------------------------------------------------------------------------
def coffee_bag():
    return (f'<path d="M-36 40 L36 40 L40 140 Q40 146 34 146 L-34 146 Q-40 146 -40 140 Z" fill="{INK}"/>'
            f'<rect x="-36" y="30" width="72" height="14" rx="3" fill="{INK}"/>'
            f'<path d="M-36 37 H36" stroke="{GROUND}" stroke-width="2" stroke-dasharray="4 4"/>'
            f'<rect x="-27" y="64" width="54" height="52" rx="4" fill="{CARD}"/>'
            f'<text x="0" y="86" text-anchor="middle" font-size="15" font-weight="800" fill="{INK}">el</text>'
            f'<text x="0" y="104" text-anchor="middle" font-size="15" font-weight="800" fill="{INK}">mejor</text>'
            f'<rect x="-40" y="126" width="80" height="8" fill="{LIME}"/>')


def invite():
    return (f'<rect x="-50" y="78" width="100" height="66" rx="6" fill="{INK}"/>'
            f'<g id="card"><rect x="-38" y="34" width="76" height="80" rx="4" fill="{CARD}" stroke="{INK}" stroke-width="2.5"/>'
            f'<text x="0" y="60" text-anchor="middle" font-size="12" font-weight="500" fill="{MUTED}">save</text>'
            f'<text x="0" y="76" text-anchor="middle" font-size="12" font-weight="500" fill="{MUTED}">the date</text></g>'
            f'<path d="M-50 84 L0 116 L50 84 L50 138 Q50 144 44 144 L-44 144 Q-50 144 -50 138 Z" fill="{INK}"/>'
            f'<path d="M-50 84 L0 116 L50 84" fill="none" stroke="{GROUND}" stroke-width="1.6" stroke-opacity=".35"/>'
            f'<path d="M0 126 c-9 -11 -21 -2 -10 7 l10 9 l10 -9 c11 -9 -1 -18 -10 -7z" fill="{LIME}"/>')


def smiley():
    return (f'<circle cx="5" cy="94" r="44" fill="{INK}"/>'
            f'<circle id="face" cx="0" cy="89" r="44" fill="{LIME}" stroke="{INK}" stroke-width="3.5"/>'
            f'<ellipse cx="-14" cy="78" rx="4.5" ry="7" fill="{INK}"/><ellipse cx="14" cy="78" rx="4.5" ry="7" fill="{INK}"/>'
            f'<path d="M-22 96 Q0 120 22 96" fill="none" stroke="{INK}" stroke-width="4.5" stroke-linecap="round"/>')


def books():
    return (f'<rect x="-48" y="124" width="96" height="20" rx="3" fill="{INK}"/>'
            f'<rect x="-42" y="104" width="86" height="20" rx="3" fill="{CARD}" stroke="{INK}" stroke-width="2.5"/>'
            f'<rect x="-46" y="84" width="88" height="20" rx="3" fill="{LIME}" stroke="{INK}" stroke-width="2.5"/>'
            f'<line x1="-30" y1="114" x2="30" y2="114" stroke="{FAINT}" stroke-width="3" stroke-linecap="round"/>'
            f'<g id="coin"><circle cx="24" cy="56" r="20" fill="{CARD}" stroke="{INK}" stroke-width="2.5"/>'
            f'<text x="24" y="62" text-anchor="middle" font-size="15" font-weight="800" fill="{INK}">2p</text></g>')


def builds():
    h = 300
    cards = [
        ("el mejor coffee", "sold", True, coffee_bag(), -3.5),
        ("happy beginnings", "india's first", False, invite(), 2.5),
        ("the stupidpreneur", "sold", True, smiley(), -2),
        ("two paise club", "reading club", False, books(), 3.5),
    ]
    cw, ch, top = 176, 238, 30
    css, body = [], []
    for i, (name, status, sold, art, tilt) in enumerate(cards):
        cx = 44 + cw / 2 + i * (W - 88 - cw) / 3
        pw = measure(status, 13, 800) + 24
        body.append(
            f'<g transform="translate({cx:.1f} {top})"><g id="c{i}" transform="rotate({tilt})">'
            f'<rect x="{-cw / 2}" y="0" width="{cw}" height="{ch}" rx="18" fill="{CARD}"/>'
            f'<rect x="{-cw / 2 + 10}" y="10" width="{cw - 20}" height="152" rx="12" fill="{GROUND}"/>'
            f"{art}"
            f'<text x="{-cw / 2 + 16}" y="190" font-size="17" font-weight="800" letter-spacing="-.3" fill="{INK}">{name}</text>'
            f'<g id="p{i}"><rect x="{-cw / 2 + 16}" y="202" width="{pw:.0f}" height="24" rx="12" fill="{LIME if sold else FAINT}"/>'
            f'<text x="{-cw / 2 + 28}" y="218.5" font-size="13" font-weight="800" fill="{INK}">{status}</text></g>'
            "</g></g>"
        )
        d = 0.15 + i * 0.13
        css.append(
            f"@keyframes c{i}{{from{{opacity:0;transform:translateY(180px) rotate({tilt * -3}deg)}}"
            f"to{{opacity:1;transform:rotate({tilt}deg)}}}}"
            f"#c{i}{{transform-box:fill-box;transform-origin:50% 100%;animation:c{i} 1.1s {d:.2f}s both {EASE_OUT}}}"
            f"@keyframes p{i}{{from{{opacity:0;transform:scale(.4)}}to{{opacity:1;transform:none}}}}"
            f"#p{i}{{transform-box:fill-box;transform-origin:left center;animation:p{i} .6s {d + 0.8:.2f}s both {SPRING}}}"
        )
    css.append(
        "@keyframes bob{0%,100%{transform:translateY(0)}50%{transform:translateY(-6px)}}"
        "#card{animation:bob 3s 2s infinite ease-in-out}"
        "@keyframes flip{0%,70%,100%{transform:scaleX(1)}80%{transform:scaleX(-1)}90%{transform:scaleX(1)}}"
        "#coin{transform-box:fill-box;transform-origin:center;animation:flip 4s 2.2s infinite}"
        "@keyframes wink{0%,92%,100%{transform:scale(1)}96%{transform:scale(1.06)}}"
        "#face{transform-box:fill-box;transform-origin:center;animation:wink 3.4s 2s infinite}"
    )
    write("builds", h, "".join(body), "".join(css),
          "the things i built: el mejor coffee (sold), happy beginnings (india's first digital wedding invite), "
          "the stupidpreneur (sold), two paise club (reading club)")


# --------------------------------------------------------------------------
# 3. choose: two identical products, and the picks pile up on one side
# --------------------------------------------------------------------------
def jar(cx, top):
    return (f'<rect x="{cx - 28}" y="{top}" width="56" height="14" rx="4" fill="{INK}"/>'
            f'<rect x="{cx - 32}" y="{top + 12}" width="64" height="84" rx="12" fill="{CARD}" stroke="{INK}" stroke-width="3"/>'
            f'<rect x="{cx - 32}" y="{top + 38}" width="64" height="30" fill="{LIME}" stroke="{INK}" stroke-width="3"/>'
            f'<text x="{cx}" y="{top + 58}" text-anchor="middle" font-size="13" font-weight="800" fill="{INK}">good</text>')


def choose():
    h, total = 344, 11
    css, body = [], []
    lines = ["same product.", "people still", "pick one."]
    for i, t in enumerate(lines):
        body.append(f'<text id="t{i}" x="44" y="{122 + i * 50}" font-size="44" font-weight="800" letter-spacing="-1.6" '
                    f'fill="{INK}">{t}</text>')
        css.append(rise(f"#t{i}", 0.15 + i * 0.12, 20))
        assert 44 + measure(t, 44, 800, -1.6) < 400, t
    body.append(f'<text id="t3" x="46" y="{122 + 3 * 50 + 4}" font-size="17" font-weight="500" fill="{MUTED}">'
                "nothing inside the jar explains the pile.</text>")
    css.append(rise("#t3", 0.6, 10))

    sq, gap, cols, rows = 16, 5, 6, 8
    gw = cols * sq + (cols - 1) * gap
    for side, (cx, picks) in enumerate([(500, 3), (700, 34)]):
        body.append(jar(cx, 22))
        gx, gy = cx - gw / 2, 136
        for r in range(rows):
            for c in range(cols):
                body.append(f'<rect x="{gx + c * (sq + gap):.1f}" y="{gy + r * (sq + gap)}" width="{sq}" height="{sq}" rx="4" fill="{FAINT}"/>')
        for k in range(picks):
            r, c = rows - 1 - k // cols, k % cols
            body.append(f'<rect class="q" style="animation-delay:{0.9 + k * (3.8 / 34) * (11 if side == 0 else 1):.2f}s" '
                        f'x="{gx + c * (sq + gap):.1f}" y="{gy + r * (sq + gap)}" width="{sq}" height="{sq}" rx="4" '
                        f'fill="{INK if side == 0 else LIME}"/>')
        body.append(f'<text x="{cx}" y="{gy + rows * (sq + gap) + 20}" text-anchor="middle" font-size="15" font-weight="800" fill="{INK}">'
                    f'{picks} picks</text>')
    css.append(
        f"@keyframes q{{0%{{opacity:0;transform:scale(.3)}}4%{{opacity:1;transform:scale(1.15)}}6%,72%{{opacity:1;transform:none}}"
        f"78%,100%{{opacity:0;transform:scale(.6)}}}}"
        f".q{{transform-box:fill-box;transform-origin:center;animation:q {total}s infinite both}}"
    )
    write("choose", h, "".join(body), "".join(css), "two identical jars. one gets 3 picks, the other gets 34. people still pick one.")


# --------------------------------------------------------------------------
# 4. deck: the committee approves the slide, then a real person reads it
# --------------------------------------------------------------------------
def deck():
    h, total = 340, 11
    css, body = [], []

    def at(t):
        return pct(t, total)

    def pop(element, t0, origin="left center", travel="scale(.6)"):
        css.append(f"@keyframes {element}{{0%,{at(t0)}{{opacity:0;transform:{travel}}}{at(t0 + .45)},94%{{opacity:1;transform:none}}"
                   f"100%{{opacity:0;transform:none}}}}"
                   f"#{element}{{transform-box:fill-box;transform-origin:{origin};animation:{element} {total}s infinite {SPRING}}}")

    t_people = 5.7  # the customer's message lands; "not with people." lights with it
    words = [("works", INK), ("in", INK), ("the", INK), ("deck.", INK), ("not", INK), ("with", INK), ("people.", INK)]
    x, y = 44, 128
    for i, (wd, fill) in enumerate(words):
        if wd == "not":
            x, y = 44, 178
        body.append(f'<text id="v{i}" x="{x:.1f}" y="{y}" font-size="44" font-weight="800" letter-spacing="-1.6" fill="{fill}">{wd}</text>')
        x += measure(wd, 44, 800, -1.6) + 12
        t0 = 0.2 + i * 0.12 if i < 4 else t_people + .3 + (i - 4) * 0.16
        css.append(f"@keyframes v{i}{{0%,{at(t0)}{{opacity:.14}}{at(t0 + .4)},94%{{opacity:1}}100%{{opacity:.14}}}}"
                   f"#v{i}{{animation:v{i} {total}s infinite}}")
    assert x < 400
    # the laptop, with the deck app's title bar
    sx, sy, sw, sh = 420, 34, 380, 236
    body.append(
        f'<rect x="{sx}" y="{sy}" width="{sw}" height="{sh}" rx="16" fill="{INK}"/>'
        f'<rect x="{sx + 12}" y="{sy + 12}" width="{sw - 24}" height="{sh - 20}" rx="6" fill="{CARD}"/>'
        f'<path d="M{sx - 26} {sy + sh} H{sx + sw + 26} L{sx + sw + 14} {sy + sh + 20} Q{sx + sw + 10} {sy + sh + 26} {sx + sw} {sy + sh + 26} '
        f'H{sx} Q{sx - 10} {sy + sh + 26} {sx - 14} {sy + sh + 20} Z" fill="{FAINT}"/>'
        f'<rect x="{sx + sw / 2 - 34}" y="{sy + sh}" width="68" height="6" rx="3" fill="#cfcdc4"/>'
        f'<path d="M{sx + 12} {sy + 44} V{sy + 18} Q{sx + 12} {sy + 12} {sx + 18} {sy + 12} H{sx + sw - 18} '
        f'Q{sx + sw - 12} {sy + 12} {sx + sw - 12} {sy + 18} V{sy + 44} Z" fill="{GROUND}"/>'
    )
    # the filename gets longer with every round of feedback
    names = ["brand_final.pptx", "brand_final_v2.pptx", "brand_final_final.pptx", "brand_v14_approved.pptx"]
    fx, fy, flh = sx + 26, sy + 33, 26
    body.append(
        f'<clipPath id="fn"><rect x="{sx + 12}" y="{sy + 14}" width="{sw - 24}" height="28"/></clipPath>'
        f'<g clip-path="url(#fn)"><g id="fname">'
        + "".join(f'<text x="{fx}" y="{fy + k * flh}" font-size="13" font-weight="500" fill="{INK}">{n}</text>' for k, n in enumerate(names))
        + "</g></g>"
    )
    frames = [f"0%,{at(1.5)}{{transform:translateY(0);animation-timing-function:{EASE_OUT}}}"]
    for k, t in enumerate([1.5, 2.6, 3.7], start=1):
        frames.append(f"{at(t + .5)},{at(t + 1.1 if k < 3 else 10.3)}{{transform:translateY({-k * flh}px);animation-timing-function:{EASE_OUT}}}")
    frames.append(f"100%{{transform:translateY(0)}}")
    css.append(f"@keyframes fname{{{''.join(frames)}}}#fname{{animation:fname {total}s infinite}}")
    chip = "approved 3/3"
    cw = measure(chip, 12, 800) + 22
    body.append(f'<g id="ok"><rect x="{sx + sw - 24 - cw:.1f}" y="{sy + 17}" width="{cw:.1f}" height="22" rx="11" fill="{LIME}"/>'
                f'<text x="{sx + sw - 13 - cw:.1f}" y="{sy + 32.5}" font-size="12" font-weight="800" fill="{INK}">{chip}</text></g>')
    pop("ok", 4.4, "right center")

    # the slide
    ix, iy = sx + 36, sy + 92
    body.append(f'<text id="title" x="{ix}" y="{iy}" font-size="30" font-weight="800" letter-spacing="-1" fill="{INK}">our brand</text>')
    css.append(f"@keyframes title{{0%,{at(2.3)}{{transform:none}}{at(2.75)},94%{{transform:scale(1.22)}}100%{{transform:none}}}}"
               f"#title{{transform-box:fill-box;transform-origin:0 100%;animation:title {total}s infinite {SPRING}}}")
    for k, wd in enumerate(["bold.", "human.", "innovative."]):
        by = iy + 38 + k * 27
        body.append(f'<circle cx="{ix + 4}" cy="{by - 6}" r="4" fill="{INK}"/>'
                    f'<text x="{ix + 18}" y="{by}" font-size="17" font-weight="500" fill="{INK}">{wd}</text>')
        if k == 0:
            body.append(f'<line id="strike" x1="{ix + 16}" y1="{by - 6}" x2="{ix + 20 + measure(wd, 17, 500):.1f}" y2="{by - 6}" '
                        f'stroke="{INK}" stroke-width="2.4" stroke-linecap="round"/>')
            css.append(f"@keyframes strike{{0%,{at(1.3)}{{transform:scaleX(0)}}{at(1.7)},94%{{transform:none}}100%{{transform:scaleX(0)}}}}"
                       f"#strike{{transform-box:fill-box;transform-origin:left;animation:strike {total}s infinite {EASE_OUT}}}")
    body.append(f'<text x="{ix}" y="{sy + sh - 22}" font-size="12" fill="{MUTED}">14 / 62</text>')

    # the committee's comments, pinned down the right edge of the slide
    comments = [("l", "legal", "drop “bold.”"), ("c", "ceo", "make the logo bigger."), ("s", "sales", "love it. ship it.")]
    for k, (initial, role, msg) in enumerate(comments):
        w = measure(role + " " + msg, 12.5, 800) + 40
        x0, y0 = sx + sw - 26 - w, sy + 104 + k * 40
        body.append(
            f'<g id="cm{k}"><rect x="{x0:.1f}" y="{y0}" width="{w:.1f}" height="32" rx="16" fill="{GROUND}"/>'
            f'<circle cx="{x0 + 16:.1f}" cy="{y0 + 16}" r="10" fill="{INK}"/>'
            f'<text x="{x0 + 16:.1f}" y="{y0 + 20}" text-anchor="middle" font-size="11" font-weight="800" fill="{CARD}">{initial}</text>'
            f'<text x="{x0 + 32:.1f}" y="{y0 + 20.5}" font-size="12.5" fill="{INK}"><tspan font-weight="800">{role}</tspan>'
            f'<tspan font-weight="500"> {msg}</tspan></text></g>'
        )
        pop(f"cm{k}", 1.0 + k * 1.1, "right center")

    # then a real person reads it
    who, says = "a real customer", "so what do you actually do?"
    bw = measure(says, 17, 500) + 36
    bx, by = 44, 220
    body.append(
        f'<g id="cust"><rect x="{bx}" y="{by}" width="{bw:.1f}" height="60" rx="20" fill="{INK}"/>'
        f'<path d="M{bx + 16} {by + 52} L{bx + 6} {by + 72} L{bx + 34} {by + 58} Z" fill="{INK}"/>'
        f'<text x="{bx + 18}" y="{by + 23}" font-size="12" font-weight="800" fill="{LIME}">{who}</text>'
        f'<text x="{bx + 18}" y="{by + 45}" font-size="17" font-weight="500" fill="{CARD}">{says}</text></g>'
    )
    pop("cust", t_people, "left bottom", "translateY(18px) scale(.85)")
    write("deck", h, "".join(body), "".join(css),
          "a slide called our brand collects committee comments and ends up brand_v14_approved. "
          "then a real customer asks: so what do you actually do? works in the deck. not with people.")


# --------------------------------------------------------------------------
# 5. ellora: the draft goes in, the ai tells get marked, your voice comes back
# --------------------------------------------------------------------------
def editor():
    h, total, swap = 372, 17, 7.6
    css, body = [], []
    bx, by, bw, bh = 44, 24, W - 88, 220
    tx, size, ys = bx + 32, 25, [by + 54, by + 92, by + 130]
    before = ["we help teams unlock growth with a", "seamless platform. let's delve into", "what sets us apart."]
    after = ["we help teams grow. the tool is", "simple. here's what's different", "about it."]
    tells = [(0, "unlock"), (1, "seamless"), (1, "delve into")]
    scores = [("93", "voice dna"), ("100", "ai editor"), ("100", "narrative")]

    def fade(element, t_in, t_out):
        """visible from t_in to t_out inside the loop; visible at rest."""
        show = "0%" if t_in < 0 else f"0%,{pct(t_in, total)}{{opacity:0}}{pct(t_in + .5, total)}"
        css.append(f"@keyframes {element}{{{show},{pct(t_out, total)}{{opacity:1}}"
                   f"{pct(t_out + .5, total)},100%{{opacity:0}}}}#{element}{{animation:{element} {total}s infinite}}")

    body.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="24" fill="{CARD}"/>')
    # phase a: the draft, with each tell marked, then struck
    marks = []
    for k, (row, word) in enumerate(tells):
        x0 = tx + measure(before[row][:before[row].index(word)], size, 500)
        ww = measure(word, size, 500)
        y = ys[row]
        t_mark, t_strike = 0.9 + k * 0.45, 2.6 + k * 0.35
        marks.append(f'<rect id="m{k}" x="{x0 - 4:.1f}" y="{y - 23}" width="{ww + 8:.1f}" height="31" rx="6" fill="{LIME}"/>')
        marks.append(f'<line id="s{k}" x1="{x0:.1f}" y1="{y - 8}" x2="{x0 + ww:.1f}" y2="{y - 8}" stroke="{INK}" stroke-width="2.4" stroke-linecap="round"/>')
        for el, t0 in ((f"m{k}", t_mark), (f"s{k}", t_strike)):
            css.append(f"@keyframes {el}{{0%,{pct(t0, total)}{{transform:scaleX(0)}}{pct(t0 + .45, total)},100%{{transform:none}}}}"
                       f"#{el}{{transform-box:fill-box;transform-origin:left;animation:{el} {total}s infinite {EASE_OUT}}}")
    body.append('<g id="pa">' + "".join(marks)
                + "".join(f'<text x="{tx}" y="{y}" font-size="{size}" font-weight="500" fill="{INK}">{t}</text>' for t, y in zip(before, ys))
                + "</g>")
    # phase b: the same draft in your voice
    body.append('<g id="pb">' + "".join(f'<text x="{tx}" y="{y}" font-size="{size}" font-weight="500" fill="{INK}">{t}</text>'
                                        for t, y in zip(after, ys)) + "</g>")
    fade("pa", -1, swap)
    fade("pb", swap + .4, total - .7)

    # the toolbar
    ty = by + bh - 40
    pill1 = measure("ellora", 15, 800) + 50
    pill2 = measure("your voice", 15, 500) + 28
    body.append(
        f'<circle cx="{bx + 38}" cy="{ty}" r="17" fill="{GROUND}"/>'
        f'<path d="M{bx + 38} {ty - 7} V{ty + 7} M{bx + 31} {ty} H{bx + 45}" stroke="{INK}" stroke-width="2.2" stroke-linecap="round"/>'
        f'<rect x="{bx + 64}" y="{ty - 17}" width="{pill1:.0f}" height="34" rx="17" fill="{GROUND}"/>'
        f'<g transform="translate({bx + 74} {ty - 10}) scale(.84)">{ELLORA_LOGO}</g>'
        f'<text x="{bx + 102}" y="{ty + 5}" font-size="15" font-weight="800" fill="{INK}">ellora</text>'
        f'<rect x="{bx + 72 + pill1:.0f}" y="{ty - 17}" width="{pill2:.0f}" height="34" rx="17" fill="{GROUND}"/>'
        f'<text x="{bx + 86 + pill1:.0f}" y="{ty + 5}" font-size="15" font-weight="500" fill="{INK}">your voice</text>'
        f'<g id="send"><circle cx="{bx + bw - 38}" cy="{ty}" r="19" fill="{INK}"/>'
        f'<path d="M{bx + bw - 38} {ty + 8} V{ty - 8} M{bx + bw - 45} {ty - 1} L{bx + bw - 38} {ty - 8} L{bx + bw - 31} {ty - 1}" '
        f'fill="none" stroke="{CARD}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></g>'
    )
    css.append(f"@keyframes send{{0%,{pct(swap - .5, total)},{pct(swap, total)},100%{{transform:none}}{pct(swap - .25, total)}{{transform:scale(.82)}}}}"
               f"#send{{transform-box:fill-box;transform-origin:center;animation:send {total}s infinite}}")

    # under the box: the tells (phase a), then this readme's scores (phase b)
    ly = by + bh + 44
    chips, cx = [], bx
    chips.append(f'<text x="{bx + 2}" y="{ly}" font-size="17" font-weight="800" fill="{INK}">3 ai tells</text>')
    cx = bx
    for k, (_, word) in enumerate(tells):
        cw = measure(word, 15, 500) + 46
        chips.append(f'<g id="ch{k}"><rect x="{cx}" y="{ly + 22}" width="{cw:.0f}" height="36" rx="18" fill="{CARD}"/>'
                     f'<circle cx="{cx + 18}" cy="{ly + 40}" r="5" fill="{LIME}" stroke="{INK}" stroke-width="1.5"/>'
                     f'<text x="{cx + 30}" y="{ly + 45}" font-size="15" font-weight="500" fill="{INK}">{word}</text></g>')
        css.append(f"@keyframes ch{k}{{0%,{pct(.9 + k * .45, total)}{{opacity:0;transform:translateY(8px)}}"
                   f"{pct(1.4 + k * .45, total)},100%{{opacity:1;transform:none}}}}#ch{k}{{animation:ch{k} {total}s infinite {EASE_OUT}}}")
        cx += cw + 10
    body.append('<g id="ta">' + "".join(chips) + "</g>")
    fade("ta", -1, swap)

    parts = [f'<text x="{bx + 2}" y="{ly}" font-size="17" font-weight="800" fill="{INK}">this readme scored</text>']
    for k, (num, label) in enumerate(scores):
        x = bx + k * 220
        part, c, nw = odometer(f"e{k}", x, ly + 58, num, 46, start=swap + .9 + k * .18, dur=1.3, total=total)
        parts.append(part)
        css.append(c)
        parts.append(f'<text x="{x + nw + 10:.0f}" y="{ly + 58}" font-size="17" font-weight="500" fill="{MUTED}">{label}</text>')
    body.append('<g id="tb">' + "".join(parts) + "</g>")
    fade("tb", swap + .4, total - .7)
    css.append("@media (prefers-reduced-motion:reduce){#pa,#ta{display:none}}")
    write("ellora", h, "".join(body), "".join(css),
          "ellora marks the ai tells in a draft (unlock, seamless, delve into) and hands it back in your voice. "
          "this readme scored 93 voice dna, 100 ai editor, 100 narrative.")


# --------------------------------------------------------------------------
# 5b. workflows: the method ticks off, and the real install commands type out
# --------------------------------------------------------------------------
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"  # real commands only


def workflows():
    h, total = 340, 12
    css, body = [], []

    def at(t):
        return pct(t, total)

    def shown(element, t0, travel="translateY(8px)", origin="left center"):
        css.append(f"@keyframes {element}{{0%,{at(t0)}{{opacity:0;transform:{travel}}}{at(t0 + .45)},95%{{opacity:1;transform:none}}"
                   f"100%{{opacity:0;transform:none}}}}"
                   f"#{element}{{transform-box:fill-box;transform-origin:{origin};animation:{element} {total}s infinite {EASE_OUT}}}")

    # left: the method, one step at a time
    steps = ["write down the steps.", "gate where it breaks.", "keep the evidence."]
    for k, step in enumerate(steps):
        y = 106 + k * 62
        t0 = 0.8 + k * 1.3
        assert 92 + measure(step, 28, 800, -1) < 380, step
        body.append(
            f'<circle cx="62" cy="{y - 10}" r="17" fill="{FAINT}"/>'
            f'<g id="tk{k}"><circle cx="62" cy="{y - 10}" r="17" fill="{LIME}"/>'
            f'<path d="M54 {y - 10} l5.5 5.5 l10 -11" fill="none" stroke="{INK}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></g>'
            f'<text id="st{k}" x="92" y="{y}" font-size="28" font-weight="800" letter-spacing="-1" fill="{INK}">{step}</text>'
        )
        shown(f"tk{k}", t0, "scale(.3)", "center")
        css.append(f"@keyframes st{k}{{0%,{at(t0)}{{opacity:.2}}{at(t0 + .35)},95%{{opacity:1}}100%{{opacity:.2}}}}"
                   f"#st{k}{{animation:st{k} {total}s infinite}}")
    body.append(f'<text x="46" y="292" font-size="17" font-weight="500" fill="{MUTED}">then it runs the same way twice.</text>')

    # right: claude code installs one
    cx, cy, cw, ch = 400, 24, 396, 292
    body.append(f'<rect x="{cx}" y="{cy}" width="{cw}" height="{ch}" rx="22" fill="{CARD}"/>'
                f'<text x="{cx + 24}" y="{cy + 38}" font-size="14" font-weight="800" fill="{INK}">claude code</text>'
                f'<text x="{cx + cw - 24}" y="{cy + 38}" text-anchor="end" font-size="14" font-weight="500" fill="{MUTED}">shashank-sn/workflows</text>')
    lines = [
        ("/plugin marketplace add shashank-sn/workflows", "added shashank-workflows", 1.0),
        ("/plugin install delivery-loop@shashank-workflows", "installed delivery-loop", 4.0),
    ]
    mono_adv = 0.6 * 12
    for k, (cmd, done, t0) in enumerate(lines):
        y = cy + 84 + k * 76
        width = len(cmd) * mono_adv + 8
        assert cx + 24 + width < cx + cw - 12, cmd
        t_typed = t0 + len(cmd) * 0.045
        body.append(
            f'<g id="ln{k}"><clipPath id="ty{k}"><rect x="{cx + 22}" y="{y - 16}" width="{width:.0f}" height="24"/></clipPath>'
            f'<text x="{cx + 24}" y="{y}" clip-path="url(#ty{k})" font-family="{MONO}" font-size="12" fill="{INK}">{cmd}</text></g>'
            f'<g id="ok{k}"><circle cx="{cx + 32}" cy="{y + 25}" r="8" fill="{LIME}"/>'
            f'<path d="M{cx + 28} {y + 25} l3 3 l5.5 -6" fill="none" stroke="{INK}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<text x="{cx + 48}" y="{y + 30}" font-size="14" font-weight="500" fill="{MUTED}">{done}</text></g>'
        )
        shown(f"ln{k}", t0 - .2, "none")
        css.append(f"@keyframes ty{k}{{0%,{at(t0)}{{width:0}}{at(t_typed)},100%{{width:{width:.0f}px}}}}"
                   f"#ty{k} rect{{animation:ty{k} {total}s infinite linear}}")
        shown(f"ok{k}", t_typed + .4)

    # the shelves the skills sit on
    shelves = ["build", "write", "research", "operate", "presence"]
    x, y = cx + 24, cy + ch - 62
    for k, name in enumerate(shelves):
        w = measure(name, 12.5, 800) + 20
        body.append(f'<g id="sh{k}"><rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="30" rx="15" fill="{GROUND}"/>'
                    f'<text x="{x + 10:.1f}" y="{y + 19.5}" font-size="12.5" font-weight="800" fill="{INK}">{name}</text></g>')
        shown(f"sh{k}", 7.6 + k * .12, "scale(.6)")
        x += w + 5
    assert x - 5 < cx + cw - 20, x
    write("workflows", h, "".join(body), "".join(css),
          "workflows: write down the steps, gate where it breaks, keep the evidence. "
          "install them in claude code with /plugin marketplace add shashank-sn/workflows.")


# --------------------------------------------------------------------------
# 6. x: the profile; the cursor opens a dm and the reader types the problem
# --------------------------------------------------------------------------
def verified(x, y, r=9):
    """x's blue check badge, centred on (x, y)."""
    return (f'<circle cx="{x}" cy="{y}" r="{r}" fill="{X_BLUE}"/>'
            f'<path d="M{x - r * .45} {y} l{r * .32} {r * .32} l{r * .6} {-r * .62}" fill="none" stroke="{CARD}" '
            f'stroke-width="{r * .24:.1f}" stroke-linecap="round" stroke-linejoin="round"/>')


def xpanel():
    """mirrors x.com/istupidpreneur: banner, avatar, bio, link, join date, post count (2026-10-22)."""
    total, h = 18, 380
    px, py, pw, ph = 24, 24, 446, 332
    dx, dy, dw, dh = 486, 24, 330, 332
    banner, avatar = data_uri(SRC / "banner.jpg"), data_uri(SRC / "avatar.jpg")
    bh = pw / 3  # x banners are 3:1
    ax, ay, ar = px + 72, py + bh, 50
    name_w = measure("shashank sn", 22, 800, -.4)

    profile = (
        f'<clipPath id="pc"><rect x="{px}" y="{py}" width="{pw}" height="{ph}" rx="20"/></clipPath>'
        f'<clipPath id="av"><circle cx="{ax}" cy="{ay}" r="{ar}"/></clipPath>'
        f'<g clip-path="url(#pc)"><rect x="{px}" y="{py}" width="{pw}" height="{ph}" fill="{CARD}"/>'
        f'<image href="{banner}" x="{px}" y="{py}" width="{pw}" height="{bh:.1f}" preserveAspectRatio="xMidYMid slice"/></g>'
        f'<circle cx="{ax}" cy="{ay}" r="{ar + 4}" fill="{CARD}"/>'
        f'<image href="{avatar}" x="{ax - ar}" y="{ay - ar}" width="{ar * 2}" height="{ar * 2}" clip-path="url(#av)"/>'
        f'<g id="msgbtn"><circle cx="{px + pw - 132}" cy="{py + bh + 30}" r="18" fill="{GROUND}"/>'
        f'<rect x="{px + pw - 141}" y="{py + bh + 24}" width="18" height="13" rx="2" fill="none" stroke="{INK}" stroke-width="1.7"/>'
        f'<path d="M{px + pw - 141} {py + bh + 25} L{px + pw - 132} {py + bh + 32} L{px + pw - 123} {py + bh + 25}" fill="none" stroke="{INK}" stroke-width="1.7"/></g>'
        f'<rect x="{px + pw - 102}" y="{py + bh + 12}" width="82" height="36" rx="18" fill="{INK}"/>'
        f'<text x="{px + pw - 61}" y="{py + bh + 35}" text-anchor="middle" font-size="15" font-weight="800" fill="{CARD}">follow</text>'
        f'<text x="{px + 24}" y="{py + bh + 86}" font-size="22" font-weight="800" letter-spacing="-.4" fill="{INK}">shashank sn</text>'
        + verified(px + 24 + name_w + 14, py + bh + 79)
        + f'<text x="{px + 24}" y="{py + bh + 108}" font-size="15" fill="{X_MUTED}">@istupidpreneur</text>'
        f'<text x="{px + 24}" y="{py + bh + 140}" font-size="16" font-weight="500" fill="{INK}">idiot savant</text>'
        f'<g fill="none" stroke="{X_MUTED}" stroke-width="1.6" stroke-linecap="round">'
        f'<path d="M{px + 28} {py + bh + 167} l6 -6 M{px + 25} {py + bh + 165} a4 4 0 0 1 0 -5.5 l2 -2 a4 4 0 0 1 5.5 0 M{px + 37} {py + bh + 163} a4 4 0 0 1 0 5.5 l-2 2 a4 4 0 0 1 -5.5 0"/>'
        f'<rect x="{px + 156}" y="{py + bh + 157}" width="14" height="13" rx="2"/><path d="M{px + 156} {py + bh + 161} h14 M{px + 160} {py + bh + 154} v4 M{px + 166} {py + bh + 154} v4"/></g>'
        f'<text x="{px + 44}" y="{py + bh + 169}" font-size="14" fill="{X_BLUE}">getellora.com</text>'
        f'<text x="{px + 176}" y="{py + bh + 169}" font-size="14" fill="{X_MUTED}">joined november 2024</text>'
    )

    css, bubbles = [], []
    for k, (msg, s0, s1) in enumerate([("we built something good.", 18, 30), ("people still pick the other one.", 36, 50)]):
        bw = measure(msg, 15, 500) + 30
        x, y = dx + dw - 18 - bw, dy + 110 + k * 50
        bubbles.append(
            f'<g id="m{k}"><rect x="{x:.0f}" y="{y}" width="{bw:.0f}" height="38" rx="19" fill="{X_BLUE}"/>'
            f'<clipPath id="t{k}"><rect x="{x + 12:.0f}" y="{y}" width="0" height="38"/></clipPath>'
            f'<text x="{x + 15:.0f}" y="{y + 24}" clip-path="url(#t{k})" font-size="15" font-weight="500" fill="{CARD}">{msg}</text></g>'
        )
        css.append(
            f"@keyframes m{k}{{0%,{s0}%{{opacity:0;transform:translateY(8px)}}{s0 + 2}%,92%{{opacity:1;transform:none}}97%,100%{{opacity:0}}}}#m{k}{{animation:m{k} {total}s infinite}}"
            f"@keyframes t{k}{{0%,{s0 + 1}%{{width:0}}{s1}%,100%{{width:{bw - 24:.0f}px}}}}#t{k} rect{{animation:t{k} {total}s infinite linear}}"
        )
    ty = dy + 110 + 2 * 50
    dm = (
        f'<clipPath id="av2"><circle cx="{dx + 34}" cy="{dy + 34}" r="16"/></clipPath>'
        f'<g id="dm"><rect x="{dx}" y="{dy}" width="{dw}" height="{dh}" rx="20" fill="{CARD}"/>'
        f'<image href="{avatar}" x="{dx + 18}" y="{dy + 18}" width="32" height="32" clip-path="url(#av2)"/>'
        f'<text x="{dx + 60}" y="{dy + 40}" font-size="16" font-weight="800" fill="{INK}">shashank sn</text>'
        + verified(dx + 60 + measure("shashank sn", 16, 800) + 12, dy + 35, 7.5)
        + f'<g transform="translate({dx + dw - 40} {dy + 23}) scale(.85)"><path d="{X_LOGO}" fill="{INK}"/></g>'
        f'<text x="{dx + dw / 2}" y="{dy + 86}" text-anchor="middle" font-size="13" fill="{X_MUTED}">@istupidpreneur · 5,705 posts</text>'
        f'<rect x="{dx + 16}" y="{dy + dh - 52}" width="{dw - 32}" height="36" rx="18" fill="{GROUND}"/>'
        f'<text x="{dx + 34}" y="{dy + dh - 29}" font-size="14" fill="{X_MUTED}">start a new message</text>'
        + "".join(bubbles)
        + f'<g id="typing"><rect x="{dx + 18}" y="{ty}" width="66" height="38" rx="19" fill="{GROUND}"/>'
        + "".join(f'<circle class="dot" style="animation-delay:{i * 0.15:.2f}s" cx="{dx + 37 + i * 14}" cy="{ty + 19}" r="4" fill="{X_MUTED}"/>' for i in range(3))
        + "</g></g>"
    )
    click_x, click_y = px + pw - 128, py + bh + 34
    css.append(
        f"@keyframes typing{{0%,54%{{opacity:0}}57%,92%{{opacity:1}}97%,100%{{opacity:0}}}}#typing{{animation:typing {total}s infinite}}"
        "@keyframes dot{0%,60%,100%{transform:translateY(0)}30%{transform:translateY(-5px)}}.dot{animation:dot 1s infinite}"
        f"@keyframes dm{{0%,12%{{opacity:.35}}15%,94%{{opacity:1}}100%{{opacity:.35}}}}#dm{{animation:dm {total}s infinite}}"
        f"@keyframes cur{{0%{{transform:translate(470px,{h}px)}}10%{{transform:translate({click_x:.0f}px,{click_y:.0f}px)}}"
        f"12%{{transform:translate({click_x:.0f}px,{click_y + 3:.0f}px)}}14%,100%{{transform:translate({click_x:.0f}px,{click_y:.0f}px)}}}}"
        f"#cur{{transform:translate({click_x:.0f}px,{click_y:.0f}px);animation:cur {total}s infinite cubic-bezier(.6,0,.3,1)}}"
        f"@keyframes btn{{0%,10%{{opacity:1}}12%{{opacity:.5}}14%,100%{{opacity:1}}}}#msgbtn{{animation:btn {total}s infinite}}"
    )
    write("x", h, profile + dm + cursor(), "".join(css), "send shashank a dm on x: @istupidpreneur")


def main():
    OUT.mkdir(exist_ok=True)
    for build in (hero, builds, choose, deck, editor, workflows, xpanel):
        build()


if __name__ == "__main__":
    main()
