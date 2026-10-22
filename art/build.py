"""Build the animated SVGs used by the profile README.

    python3 art/build.py

Writes assets/<name>.svg (light) and assets/<name>-dark.svg (dark) for every
image. The README picks one with <picture> + prefers-color-scheme, which GitHub
matches to the viewer's GitHub theme.

Every SVG is self-contained so GitHub renders it through <img>: CSS / SMIL
animation only, no JS, no external requests. Google Sans Flex and Google Sans
Code (both OFL) are subset to the glyphs each SVG uses and embedded as woff2.
The X panel embeds art/src/banner.jpg and art/src/avatar.jpg.

Needs network access on the first run to fetch fonts; responses are cached in
art/.font-cache/.
"""
import base64
import hashlib
import html
import random
import re
import urllib.parse
import urllib.request
from pathlib import Path

ART = Path(__file__).resolve().parent
OUT = ART.parent / "assets"
SRC = ART / "src"
FONT_CACHE = ART / ".font-cache"

W = 840  # every image is drawn at README width and scales with width="100%"

# --------------------------------------------------------------------------
# palette: light values are the source; DARK derives the dark-theme file
# --------------------------------------------------------------------------
INK = "#111111"
MUTED = "#8a8a8a"
LINE = "#e6e6e6"
ACCENT = "#ff4d2e"
SURFACE = "#ffffff"  # cards and fills that sit on the page
ON_ACCENT = "#fffffe"  # text on red / blue: white in both themes
ON_INK = "#fffffd"  # text on ink shapes: flips with ink
SHADOW = "#efefef"
BAR = "#eeeeee"  # placeholder text bars
BAR_STRONG = "#d6d6d6"
FLAG_BG = "#fff6f4"
X_MUTED, X_BLUE, X_FIELD, X_BORDER = "#536471", "#1d9bf0", "#eff3f4", "#cfd9de"

# the receipt is a physical object: it stays white, and its printer stays dark,
# in both themes. These values are deliberately absent from DARK.
PAPER, PAPER_EDGE, PAPER_INK, PAPER_MUTED = "#fffdf8", "#e4e1d8", "#121212", "#8b8b8b"
DEVICE, DEVICE_TEXT, DEVICE_SLOT = "#1c1c1c", "#9a9a99", "#050505"

DARK = {
    INK: "#e6edf3", MUTED: "#8b949e", LINE: "#30363d", SURFACE: "#0d1117",
    ON_ACCENT: "#ffffff", ON_INK: "#0d1117", SHADOW: "#010409",
    BAR: "#262c34", BAR_STRONG: "#3d444d", FLAG_BG: "#2a1612",
    X_MUTED: "#8b98a5", X_FIELD: "#21262d", X_BORDER: "#3d444d",
}

MONO = "'Google Sans Code', ui-monospace, Menlo, monospace"
SANS = "'Google Sans Flex', -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
FONTS = {"Google Sans Flex": (400, 700, 800, 900), "Google Sans Code": (400, 700)}
CODE_ADV = 0.6  # Google Sans Code advance width, in em
# Google Fonts only serves woff2 to browser user agents
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"

CURSOR = "M0 0 L0 26 L7 19 L12 31 L17 29 L12 17 L22 17 Z"
X_LOGO = ("M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835"
          "L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z")
ELLORA_LOGO = (  # getellora.com/favicon.svg, 24x24
    f'<rect width="24" height="24" rx="5" fill="{INK}"/>'
    f'<g stroke="{ON_INK}" stroke-width="3.4" stroke-linecap="round">'
    '<line x1="12" y1="3.4" x2="12" y2="20.6"/><line x1="3.4" y1="12" x2="20.6" y2="12"/>'
    '<line x1="5.9" y1="5.9" x2="18.1" y2="18.1"/><line x1="18.1" y1="5.9" x2="5.9" y2="18.1"/></g>'
)


# --------------------------------------------------------------------------
# output: fonts, themes, files
# --------------------------------------------------------------------------
def fetch(url):
    """GET url through an on-disk cache keyed by the full URL."""
    key = FONT_CACHE / hashlib.sha256(url.encode()).hexdigest()
    if not key.exists():
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        key.write_bytes(urllib.request.urlopen(req, timeout=30).read())
    return key.read_bytes()


def glyphs(svg):
    """every character drawn as text: text node contents, not CSS."""
    drawn = re.sub(r"<style>.*?</style>", "", svg, flags=re.S)
    return "".join(sorted(set(html.unescape("".join(re.findall(r">([^<]+)<", drawn))))))


def font_faces(svg):
    """@font-face rules for both families, subset to the glyphs in svg."""
    rules = []
    for family, weights in FONTS.items():
        query = urllib.parse.urlencode({
            "family": f"{family}:wght@{';'.join(map(str, weights))}",
            "text": glyphs(svg),
        })
        css = fetch(f"https://fonts.googleapis.com/css2?{query}").decode()
        # a variable font comes back as the same file for every weight: embed it once
        weights_by_src = {}
        for block in re.findall(r"@font-face\s*{[^}]+}", css):
            weight = int(re.search(r"font-weight:\s*(\d+)", block).group(1))
            src = re.search(r"url\(([^)]+)\)", block).group(1)
            weights_by_src.setdefault(src, []).append(weight)
        for src, ws in weights_by_src.items():
            b64 = base64.b64encode(fetch(src)).decode()
            rules.append(
                f"@font-face{{font-family:'{family}';font-weight:{min(ws)} {max(ws)};"
                f"src:url(data:font/woff2;base64,{b64}) format('woff2')}}"
            )
    return "".join(rules)


def to_dark(svg):
    return re.sub(r"#[0-9a-f]{6}\b", lambda m: DARK.get(m.group(0), m.group(0)), svg)


def write(name, h, body, css="", font=MONO, size=13):
    """write <name>.svg and <name>-dark.svg with a transparent canvas."""
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}" viewBox="0 0 {W} {h}" '
        f'font-family="{font}" font-size="{size}"><style>{css}</style>{body}</svg>'
    )
    fonts = f"<style>{font_faces(svg)}</style>"
    head = svg.index(">") + 1
    light = svg[:head] + fonts + svg[head:]
    (OUT / f"{name}.svg").write_text(light + "\n")
    (OUT / f"{name}-dark.svg").write_text(to_dark(light) + "\n")


def data_uri(path):
    return "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode()


def cursor(element_id="cur"):
    return f'<g id="{element_id}"><path d="{CURSOR}" fill="{INK}" stroke="{SURFACE}" stroke-width="1.5"/></g>'


# --------------------------------------------------------------------------
# header: a thermal printer prints the career, then a stamp lands
# --------------------------------------------------------------------------
RECEIPT_COLS = 42


def receipt_row(left, right):
    dots = RECEIPT_COLS - len(left) - len(right) - 2
    assert dots >= 2, f"receipt row too long: {left!r} / {right!r}"
    return f"{left} {'.' * dots} {right}"


RECEIPT_ROWS = [
    ("SHASHANK SN", "title"),
    ("brand strategist by accident.", "center"),
    ("builder on purpose.", "center"),
    (receipt_row("table: github", "guest: you"), "muted"),
    ("-" * RECEIPT_COLS, "muted"),
    (receipt_row("THE WORK", "QTY"), "bold"),
    (receipt_row("brand strategy, fractional", "still open"), ""),
    (receipt_row("head of brand, guvi hcl", "1 yr"), ""),
    (receipt_row("guinness world record", "1"), ""),
    (receipt_row("talks given", "100+"), ""),
    (receipt_row("companies served", "150+"), ""),
    (receipt_row("years in brand", "7"), ""),
    ("-" * RECEIPT_COLS, "muted"),
    (receipt_row("THE BUILDS", "STATUS"), "bold"),
    (receipt_row("brandeey", "the course"), ""),
    (receipt_row("ellora", "ai editor"), "accent"),
    (receipt_row("sayabout.us", "in the oven"), ""),
    (receipt_row("happy beginnings", "1st in india"), ""),
    (receipt_row("el mejor coffee", "SOLD"), "sold"),
    (receipt_row("the stupidpreneur", "SOLD"), "sold"),
    (receipt_row("two paise club", "₹0.02"), ""),
    ("-" * RECEIPT_COLS, "muted"),
    (receipt_row("SUBTOTAL", "7 built"), "bold"),
    (receipt_row("EXITS", "2"), "bold"),
    (receipt_row("brands that only work in a deck", "0"), "bold"),
    ("-" * RECEIPT_COLS, "muted"),
    ("why do people choose you,", "center"),
    ("and why do they come back?", "center"),
    ("", "barcode"),
    ("", "gap"),
    ("tips accepted on x, @istupidpreneur.", "center"),
    ("thank you. come back.", "center"),
]


def receipt():
    """plays once and stays: the receipt is ~95 words, too long to read inside a loop."""
    lh, rw = 22, 420
    print_s = 7  # paper feed time; the stamp lands just after
    rx = (W - rw) / 2
    tx = rx + 22
    slot = 70  # y of the slot on the printer's front face
    paper_top = slot + 4

    lines, y, stamp_y = [], 46, None
    for content, style in RECEIPT_ROWS:
        if style == "title":
            y += 8
            lines.append(f'<text x="{W / 2}" y="{y}" text-anchor="middle" font-size="22" font-weight="800" letter-spacing="3" fill="{PAPER_INK}">{content}</text>')
            y += lh + 4
        elif style == "barcode":
            rng = random.Random(3)
            bx, bars = rx + 70, []
            while bx < rx + rw - 70:
                w = rng.choice([1.5, 1.5, 2.5, 4])
                bars.append(f'<rect x="{bx:.1f}" y="{y - 10}" width="{w}" height="44" fill="{PAPER_INK}"/>')
                bx += w + rng.choice([1.5, 2.5, 3])
            lines.append("".join(bars))
            y += 48
        elif style == "gap":
            y += 4
        else:
            if style == "sold" and stamp_y is None:
                stamp_y = paper_top + y - 40  # the stamp lands beside the first sold line
            fill = {"muted": PAPER_MUTED, "sold": PAPER_MUTED, "accent": ACCENT}.get(style, PAPER_INK)
            if style == "center":
                lines.append(f'<text x="{W / 2}" y="{y}" text-anchor="middle" fill="{fill}" xml:space="preserve">{content}</text>')
            else:
                weight = ' font-weight="700"' if style == "bold" else ""
                lines.append(f'<text x="{tx}" y="{y}" fill="{fill}"{weight} xml:space="preserve" textLength="{rw - 44}" lengthAdjust="spacing">{content}</text>')
            y += lh

    rh = y + 18
    teeth = 34
    tw = rw / teeth
    torn = " ".join(f"L{rx + rw - (i + 0.5) * tw:.1f} {rh + 8} L{rx + rw - (i + 1) * tw:.1f} {rh}" for i in range(teeth))
    paper = f"M{rx} 0 L{rx + rw} 0 L{rx + rw} {rh} {torn} Z"
    h = paper_top + rh + 40
    sx = rx + rw - 34  # stamp box, hanging over the paper's right edge

    body = (
        # printer: the paper is drawn after it, so it comes out of the front slot
        f'<rect x="{rx - 48}" y="14" width="{rw + 96}" height="82" rx="16" fill="{DEVICE}" stroke="{LINE}" stroke-width="1.5"/>'
        f'<circle id="led" cx="{rx - 22}" cy="36" r="5" fill="{ACCENT}"/>'
        f'<text x="{rx + rw + 22}" y="40" text-anchor="end" fill="{DEVICE_TEXT}" font-size="11" letter-spacing="2">EST. 7 YRS</text>'
        f'<rect x="{rx - 10}" y="{slot - 4}" width="{rw + 20}" height="8" rx="4" fill="{DEVICE_SLOT}"/>'
        '<linearGradient id="lip" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#000000" stop-opacity=".28"/><stop offset="1" stop-color="#000000" stop-opacity="0"/></linearGradient>'
        f'<clipPath id="out"><rect x="0" y="{paper_top}" width="{W}" height="{h - paper_top}"/></clipPath>'
        f'<g clip-path="url(#out)"><g transform="translate(0 {paper_top})"><g id="paper">'
        f'<path d="{paper}" transform="translate(4 6)" fill="{SHADOW}"/>'
        f'<path d="{paper}" fill="{PAPER}" stroke="{PAPER_EDGE}" stroke-width="1.2"/>'
        f'{"".join(lines)}'
        f'</g></g></g>'
        f'<rect x="{rx}" y="{paper_top}" width="{rw}" height="14" fill="url(#lip)"/>'
        '<g id="stamp">'
        f'<rect x="{sx}" y="{stamp_y}" width="196" height="74" rx="8" fill="none" stroke="{ACCENT}" stroke-width="4"/>'
        f'<rect x="{sx + 6}" y="{stamp_y + 6}" width="184" height="62" rx="5" fill="none" stroke="{ACCENT}" stroke-width="1.5"/>'
        f'<text x="{sx + 98}" y="{stamp_y + 36}" text-anchor="middle" font-family="{SANS}" font-size="24" font-weight="900" letter-spacing="2" fill="{ACCENT}">2 EXITS</text>'
        f'<text x="{sx + 98}" y="{stamp_y + 56}" text-anchor="middle" font-family="{SANS}" font-size="11" font-weight="800" letter-spacing="2" fill="{ACCENT}">BUILT · SCALED · SOLD</text>'
        '</g>'
    )
    steps = len(RECEIPT_ROWS) + 6  # the printer feeds in jerks, roughly a line at a time
    blinks = round(print_s / 0.4)  # the led blinks while the printer runs
    css = (
        f"@keyframes pr{{from{{transform:translateY(-{rh + 30}px);animation-timing-function:steps({steps},end)}}"
        "to{transform:translateY(0)}}"
        f"#paper{{animation:pr {print_s}s both}}"
        "@keyframes st{from{opacity:0;transform:rotate(-14deg) scale(2.6)}"
        "60%{opacity:.92;transform:rotate(-14deg) scale(.94)}to{opacity:.88;transform:rotate(-14deg) scale(1)}}"
        f"#stamp{{transform-box:fill-box;transform-origin:center;animation:st .5s {print_s + 0.4}s both}}"
        f"@keyframes led{{from,99%{{fill:{ACCENT}}}to{{fill:{DEVICE_TEXT}}}}}"
        "@keyframes bl{50%{opacity:.2}}"
        f"#led{{animation:led {print_s}s both,bl .4s steps(1) {blinks}}}"
    )
    write("d-receipt", h, body, css, size=14)


# --------------------------------------------------------------------------
# story panels: short loops between the README paragraphs
# --------------------------------------------------------------------------
def shelf():
    """the things i built drop onto a shelf; the sold ones swing a tag."""
    total, h, floor = 8, 230, 168
    items = [
        ("el mejor coffee", True,
         f'<rect x="-26" y="-58" width="52" height="58" rx="8" fill="{INK}"/>'
         f'<path d="M26 -46 a14 14 0 0 1 0 28" fill="none" stroke="{INK}" stroke-width="6"/>'
         f'<rect x="-26" y="-40" width="52" height="14" fill="{ACCENT}"/>'
         f'<path class="steam" d="M-10 -66 q6 -8 0 -16 q-6 -8 0 -16 M8 -66 q6 -8 0 -16 q-6 -8 0 -16" fill="none" stroke="{MUTED}" stroke-width="2.5" stroke-linecap="round"/>'),
        ("happy beginnings", False,
         f'<rect x="-40" y="-54" width="80" height="54" rx="4" fill="{SURFACE}" stroke="{INK}" stroke-width="3"/>'
         f'<path d="M-40 -54 L0 -24 L40 -54" fill="none" stroke="{INK}" stroke-width="3"/>'
         f'<path d="M0 -12 c-8 -10 -18 -2 -9 6 l9 8 l9 -8 c9 -8 -1 -16 -9 -6z" fill="{ACCENT}"/>'),
        ("the stupidpreneur", True,
         f'<rect x="-32" y="-78" width="64" height="78" rx="3" fill="{SURFACE}" stroke="{INK}" stroke-width="3"/>'
         f'<rect x="-24" y="-70" width="48" height="12" fill="{INK}"/>'
         + "".join(f'<rect x="-24" y="{-50 + k * 10}" width="{48 if k % 3 else 34}" height="4" fill="{BAR_STRONG}"/>' for k in range(5))),
        ("two paise club", False,
         f'<rect x="-34" y="-20" width="68" height="20" rx="2" fill="{INK}"/>'
         f'<rect x="-30" y="-40" width="60" height="20" rx="2" fill="{SURFACE}" stroke="{INK}" stroke-width="3"/>'
         f'<rect x="-26" y="-60" width="52" height="20" rx="2" fill="{ACCENT}"/>'
         f'<circle cx="16" cy="-80" r="12" fill="{SURFACE}" stroke="{INK}" stroke-width="3"/>'
         f'<text x="16" y="-75.5" text-anchor="middle" font-size="12" font-weight="800" fill="{INK}">2p</text>'),
    ]
    sold_tag = (
        '<g transform="translate(34 -60)"><g class="swing">'
        f'<line x1="0" y1="0" x2="0" y2="16" stroke="{INK}" stroke-width="1.5"/>'
        f'<rect x="-24" y="16" width="48" height="20" rx="3" fill="{ACCENT}"/>'
        f'<text x="0" y="30.5" text-anchor="middle" font-size="11" font-weight="800" fill="{ON_ACCENT}" letter-spacing="1.5">SOLD</text>'
        '</g></g>'
    )
    css = [
        "@keyframes sw{0%,100%{transform:rotate(9deg)}50%{transform:rotate(-9deg)}}"
        ".swing{transform-box:view-box;transform-origin:0 0;animation:sw 1.6s infinite ease-in-out}"
        "@keyframes steam{to{stroke-dashoffset:-24}}.steam{stroke-dasharray:6 6;animation:steam 1s linear infinite}"
    ]
    body = [f'<line x1="70" y1="{floor}" x2="{W - 70}" y2="{floor}" stroke="{INK}" stroke-width="3" stroke-linecap="round"/>']
    for i, (label, sold, icon) in enumerate(items):
        s = 4 + i * 4  # each item drops a little after the previous one
        css.append(
            f"@keyframes d{i}{{0%,{s}%{{transform:translateY(-200px);opacity:0}}"
            f"{s + 8}%{{transform:translateY(0);opacity:1}}{s + 11}%{{transform:translateY(-14px)}}{s + 14}%,90%{{transform:translateY(0);opacity:1}}"
            f"96%,100%{{transform:translateY(0);opacity:0}}}}#d{i}{{animation:d{i} {total}s infinite cubic-bezier(.5,0,.5,1)}}"
        )
        body.append(
            f'<g transform="translate({150 + i * 180} {floor})"><g id="d{i}">{icon}{sold_tag if sold else ""}</g>'
            f'<text y="34" text-anchor="middle" fill="{MUTED}">{label}</text></g>'
        )
    write("p1-shelf", h, "".join(body), "".join(css))


def product_card(x, element_id):
    return (
        f'<g id="{element_id}"><rect x="{x}" y="30" width="230" height="150" rx="12" fill="{SURFACE}" stroke="{LINE}" stroke-width="2"/>'
        f'<rect x="{x + 20}" y="50" width="44" height="44" rx="10" fill="{INK}"/>'
        f'<rect x="{x + 78}" y="56" width="110" height="10" rx="5" fill="{INK}"/>'
        f'<rect x="{x + 78}" y="76" width="74" height="8" rx="4" fill="{BAR_STRONG}"/>'
        + "".join(f'<rect x="{x + 20}" y="{112 + k * 16}" width="{190 - k * 30}" height="8" rx="4" fill="{BAR}"/>' for k in range(3))
        + "</g>"
    )


def choose():
    """two identical products; people still pick one."""
    total, h = 6, 250
    ax, bx = 170, 440
    body = (
        product_card(ax, "ca") + product_card(bx, "cb")
        + f'<rect class="ring" x="{bx - 6}" y="24" width="242" height="162" rx="16" fill="none" stroke="{ACCENT}" stroke-width="3"/>'
        f'<g class="badge"><rect x="{bx + 150}" y="14" width="92" height="28" rx="14" fill="{ACCENT}"/>'
        f'<text x="{bx + 196}" y="33" text-anchor="middle" font-size="12" font-weight="800" fill="{ON_ACCENT}">✓ chosen</text></g>'
        f'<text x="{ax + 115}" y="210" text-anchor="middle" fill="{MUTED}">same product</text>'
        f'<text x="{bx + 115}" y="210" text-anchor="middle" fill="{MUTED}">same product</text>'
        f'<text x="{W / 2}" y="238" text-anchor="middle" fill="{INK}" font-weight="700">people still pick one.</text>'
        + cursor()
    )
    css = (
        "@keyframes cur{0%{transform:translate(780px,230px)}20%{transform:translate(330px,120px)}"
        "32%{transform:translate(310px,110px)}50%{transform:translate(560px,118px)}55%{transform:translate(560px,122px)}"
        f"58%,88%{{transform:translate(560px,118px)}}100%{{transform:translate(780px,230px)}}}}#cur{{animation:cur {total}s infinite cubic-bezier(.6,0,.3,1)}}"
        f"@keyframes ring{{0%,54%{{opacity:0}}57%,90%{{opacity:1}}96%,100%{{opacity:0}}}}.ring{{animation:ring {total}s infinite}}"
        "@keyframes badge{0%,55%{opacity:0;transform:scale(.3)}60%{opacity:1;transform:scale(1.15)}64%,90%{opacity:1;transform:scale(1)}96%,100%{opacity:0;transform:scale(1)}}"
        f".badge{{transform-box:fill-box;transform-origin:center;animation:badge {total}s infinite}}"
        f"@keyframes fadea{{0%,55%{{opacity:1}}62%,90%{{opacity:.45}}100%{{opacity:1}}}}#ca{{animation:fadea {total}s infinite}}"
    )
    write("p2-choose", h, body, css)


def deck():
    """a brand that only works in a deck gets stamped: proposal."""
    total, h = 6, 270
    sx, sy, sw, sh = 230, 24, 380, 214
    body = (
        f'<rect x="{sx + 8}" y="{sy + 8}" width="{sw}" height="{sh}" rx="10" fill="{SHADOW}"/>'
        f'<rect x="{sx}" y="{sy}" width="{sw}" height="{sh}" rx="10" fill="{SURFACE}" stroke="{INK}" stroke-width="2.5"/>'
        f'<text x="{sx + 28}" y="{sy + 52}" font-family="{SANS}" font-size="30" font-weight="900" letter-spacing="-1" fill="{INK}">our brand</text>'
        f'<rect x="{sx + 28}" y="{sy + 68}" width="60" height="5" fill="{ACCENT}"/>'
        + "".join(f'<circle cx="{sx + 34}" cy="{sy + 100 + k * 24}" r="4" fill="{INK}"/><rect x="{sx + 48}" y="{sy + 96 + k * 24}" width="{150 - k * 26}" height="8" rx="4" fill="{BAR_STRONG}"/>' for k in range(3))
        + "".join(f'<rect class="bar" style="animation-delay:{k * 0.12:.2f}s" x="{sx + 250 + k * 26}" y="{sy + 140 - k * 22}" width="18" height="{30 + k * 22}" fill="{INK if k < 3 else ACCENT}"/>' for k in range(4))
        + f'<text x="{sx + sw - 18}" y="{sy + sh - 14}" text-anchor="end" fill="{MUTED}" font-size="11">slide 14 of 62</text>'
        f'<g class="stamp"><rect x="{sx + 96}" y="{sy + 74}" width="200" height="64" rx="8" fill="{SURFACE}" fill-opacity=".6" stroke="{ACCENT}" stroke-width="4"/>'
        f'<text x="{sx + 196}" y="{sy + 117}" text-anchor="middle" font-family="{SANS}" font-size="30" font-weight="900" letter-spacing="3" fill="{ACCENT}">PROPOSAL</text></g>'
        f'<text x="{W / 2}" y="{h - 8}" text-anchor="middle" fill="{MUTED}">works in the deck. not with people.</text>'
    )
    css = (
        "@keyframes grow{from{transform:scaleY(0)}to{transform:scaleY(1)}}"
        ".bar{transform-box:fill-box;transform-origin:bottom;animation:grow .8s both cubic-bezier(.3,1.4,.5,1)}"
        "@keyframes stamp{0%,40%{opacity:0;transform:rotate(-12deg) scale(2.4)}45%{opacity:1;transform:rotate(-12deg) scale(.92)}"
        "48%,90%{opacity:1;transform:rotate(-12deg) scale(1)}96%,100%{opacity:0;transform:rotate(-12deg) scale(1)}}"
        f".stamp{{transform-box:fill-box;transform-origin:center;animation:stamp {total}s infinite}}"
    )
    write("p3-deck", h, body, css)


def eyebrow(x, y, label):
    return f'<text x="{x}" y="{y}" font-family="{SANS}" font-size="12" font-weight="700" letter-spacing="1.5" fill="{MUTED}">{label}</text>'


def editor():
    """ellora flags the ai tells, hands back the draft, and shows this readme's scores.

    timeline in seconds: the draft and its flags stay until `swap` (strikes are all in
    by ~4 s), then the clean draft and the scores stay until the loop restarts at `total`.
    """
    total, swap, h = 20, 9.0, 350

    def at(seconds):
        return f"{seconds / total * 100:.1f}%"

    cx, cy, cw, ch = 30, 16, 780, 296
    char_w = 15 * CODE_ADV
    tx, ys = cx + 28, [cy + 124, cy + 156, cy + 188]
    side = cx + 520
    before = ["we help teams unlock growth with a", "seamless platform. let's delve into", "what sets us apart."]
    after = ["we help teams grow. the tool is", "simple. here's what's different", "about it."]
    flags = [(0, "unlock"), (1, "seamless"), (1, "delve into")]
    scores = [("voice dna", 93), ("ai editor", 100), ("narrative", 100)]  # this README's ellora review

    def pill(element_id, label, filled):
        fill, stroke, text = (ACCENT, "none", ON_ACCENT) if filled else (SURFACE, ACCENT, ACCENT)
        return (f'<g id="{element_id}"><rect x="{cx + cw - 136}" y="{cy + 13}" width="116" height="28" rx="14" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
                f'<text x="{cx + cw - 78}" y="{cy + 32}" text-anchor="middle" font-family="{SANS}" font-size="13" font-weight="700" fill="{text}">{label}</text></g>')

    css = []
    body = [
        f'<rect x="{cx}" y="{cy}" width="{cw}" height="{ch}" rx="16" fill="{SURFACE}" stroke="{LINE}" stroke-width="2"/>'
        f'<line x1="{cx}" y1="{cy + 52}" x2="{cx + cw}" y2="{cy + 52}" stroke="{LINE}" stroke-width="2"/>'
        f'<line x1="{side - 20}" y1="{cy + 52}" x2="{side - 20}" y2="{cy + ch}" stroke="{LINE}" stroke-width="2"/>'
        f'<g transform="translate({cx + 18} {cy + 13}) scale(1.1)">{ELLORA_LOGO}</g>'
        f'<text x="{cx + 54}" y="{cy + 32}" font-family="{SANS}" font-size="18" font-weight="800" fill="{INK}">ellora</text>'
        f'<text x="{cx + 140}" y="{cy + 31}" font-family="{SANS}" font-size="14" fill="{MUTED}">draft</text>'
        f'<text x="{cx + 192}" y="{cy + 31}" font-family="{SANS}" font-size="14" font-weight="700" fill="{INK}">review</text>'
        f'<rect x="{cx + 192}" y="{cy + 49}" width="46" height="3" fill="{ACCENT}"/>'
        + pill("pa", "3 ai tells", False) + pill("pb", "voice held ✓", True)
        + eyebrow(tx, cy + 86, "YOUR DRAFT")
    ]

    # phase 1: the draft with its ai tells marked, and the flags listed alongside
    marks, flag_rows = [], []
    for k, (line, word) in enumerate(flags):
        i = before[line].index(word)
        x0, x1, y = tx + i * char_w, tx + (i + len(word)) * char_w, ys[line]
        marks.append(
            f'<rect class="hl{k}" x="{x0 - 3:.1f}" y="{y - 16}" width="{x1 - x0 + 6:.1f}" height="22" rx="4" fill="{ACCENT}" fill-opacity=".16"/>'
            f'<line class="sk{k}" x1="{x0:.1f}" y1="{y - 5}" x2="{x1:.1f}" y2="{y - 5}" stroke="{ACCENT}" stroke-width="2.2"/>'
        )
        fy = cy + 112 + k * 46
        flag_rows.append(
            f'<g id="f{k}"><rect x="{side}" y="{fy}" width="222" height="36" rx="8" fill="{FLAG_BG}"/>'
            f'<circle cx="{side + 16}" cy="{fy + 18}" r="4" fill="{ACCENT}"/>'
            f'<text x="{side + 30}" y="{fy + 23}" font-size="14" fill="{INK}">{word}</text>'
            f'<text x="{side + 208}" y="{fy + 23}" text-anchor="end" font-family="{SANS}" font-size="12" fill="{ACCENT}">ai tell</text></g>'
        )
        flagged, struck = 1.0 + k * 0.6, 2.6 + k * 0.6  # seconds
        css.append(
            f"@keyframes hl{k}{{0%,{at(flagged)}{{opacity:0}}{at(flagged + .3)},{at(swap)}{{opacity:1}}{at(swap + .6)},100%{{opacity:0}}}}"
            f".hl{k}{{animation:hl{k} {total}s infinite}}"
            f"@keyframes sk{k}{{0%,{at(struck)}{{opacity:0}}{at(struck + .2)},{at(swap)}{{opacity:1}}{at(swap + .6)},100%{{opacity:0}}}}"
            f".sk{k}{{animation:sk{k} {total}s infinite}}"
            f"@keyframes f{k}{{0%,{at(flagged)}{{opacity:0;transform:translateX(12px)}}{at(flagged + .4)},{at(swap)}{{opacity:1;transform:translateX(0)}}"
            f"{at(swap + .6)},100%{{opacity:0}}}}#f{k}{{animation:f{k} {total}s infinite}}"
        )
    body.append(
        '<g id="va">' + "".join(marks)
        + "".join(f'<text x="{tx}" y="{y}" font-size="15" fill="{INK}" xml:space="preserve">{t}</text>' for t, y in zip(before, ys))
        + "</g>"
        + f'<g id="sa">{eyebrow(side, cy + 86, "FLAGS")}{"".join(flag_rows)}</g>'
    )

    # phase 2: the clean draft and the scores
    body.append(
        '<g id="vb">' + "".join(f'<text x="{tx}" y="{y}" font-size="15" fill="{INK}">{t}</text>' for t, y in zip(after, ys)) + "</g>"
        + f'<g id="sb">{eyebrow(side, cy + 86, "THIS README")}'
        + "".join(
            f'<text x="{side}" y="{cy + 122 + k * 50}" font-family="{SANS}" font-size="14" font-weight="700" fill="{INK}">{label}</text>'
            f'<text x="{side + 222}" y="{cy + 122 + k * 50}" text-anchor="end" font-family="{SANS}" font-size="14" font-weight="800" fill="{ACCENT}">{score}</text>'
            f'<rect x="{side}" y="{cy + 132 + k * 50}" width="222" height="8" rx="4" fill="{BAR}"/>'
            f'<rect class="m" style="animation-delay:{k * 0.15:.2f}s" x="{side}" y="{cy + 132 + k * 50}" width="{222 * score / 100:.0f}" height="8" rx="4" fill="{INK if k else ACCENT}"/>'
            for k, (label, score) in enumerate(scores))
        + "</g>"
    )
    body.append(
        f'<rect x="{tx}" y="{cy + 222}" width="150" height="8" rx="4" fill="{BAR}"/><rect x="{tx + 162}" y="{cy + 222}" width="220" height="8" rx="4" fill="{BAR}"/>'
        f'<rect x="{tx}" y="{cy + 242}" width="290" height="8" rx="4" fill="{BAR}"/>'
        f'<text x="{W / 2}" y="{h - 10}" text-anchor="middle" font-family="{SANS}" font-size="14" fill="{MUTED}">'
        "inside chatgpt, claude and the apps your team already writes in</text>"
    )
    shown = swap + 1.6  # clean draft fully in
    css.append(
        f"@keyframes va{{0%,{at(swap)}{{opacity:1}}{at(swap + .8)},100%{{opacity:0}}}}#va,#sa,#pa{{animation:va {total}s infinite}}"
        f"@keyframes vb{{0%,{at(swap + .8)}{{opacity:0}}{at(shown)},{at(total - .8)}{{opacity:1}}100%{{opacity:0}}}}#vb,#sb,#pb{{animation:vb {total}s infinite}}"
        f"@keyframes m{{0%,{at(shown)}{{transform:scaleX(0)}}{at(shown + 2)},100%{{transform:scaleX(1)}}}}"
        f".m{{transform-box:fill-box;transform-origin:left;animation:m {total}s infinite cubic-bezier(.3,0,.2,1)}}"
    )
    write("p4-ellora", h, "".join(body), "".join(css))


def verified(x, y, r=9):
    """x's blue check badge, centred on (x, y)."""
    return (f'<circle cx="{x}" cy="{y}" r="{r}" fill="{X_BLUE}"/>'
            f'<path d="M{x - r * .45} {y} l{r * .32} {r * .32} l{r * .6} {-r * .62}" fill="none" stroke="{ON_ACCENT}" '
            f'stroke-width="{r * .24:.1f}" stroke-linecap="round" stroke-linejoin="round"/>')


def xpanel():
    """the x profile; the cursor opens a dm and the reader types the problem.

    mirrors x.com/istupidpreneur: banner, avatar, bio, link, join date, post count (2026-10-22).
    the loop is long enough to hold both messages for ~7 s after they are typed.
    """
    total, h = 18, 374
    px, py, pw, ph = 40, 20, 430, 334
    dx, dy, dw, dh = 500, 20, 300, 334
    banner, avatar = data_uri(SRC / "banner.jpg"), data_uri(SRC / "avatar.jpg")
    bh = pw / 3  # x banners are 3:1
    ax, ay, ar = px + 70, py + bh, 50
    name_w = 131  # measured: "shashank sn" at 21px / 800 in Google Sans Flex
    dm_name_w = 94  # measured: "shashank sn" at 15px / 800

    profile = (
        f'<clipPath id="pc"><rect x="{px}" y="{py}" width="{pw}" height="{ph}" rx="16"/></clipPath>'
        f'<clipPath id="av"><circle cx="{ax}" cy="{ay}" r="{ar}"/></clipPath>'
        f'<g clip-path="url(#pc)"><rect x="{px}" y="{py}" width="{pw}" height="{ph}" fill="{SURFACE}"/>'
        f'<image href="{banner}" x="{px}" y="{py}" width="{pw}" height="{bh:.1f}" preserveAspectRatio="xMidYMid slice"/></g>'
        f'<rect x="{px}" y="{py}" width="{pw}" height="{ph}" rx="16" fill="none" stroke="{LINE}" stroke-width="2"/>'
        f'<circle cx="{ax}" cy="{ay}" r="{ar + 4}" fill="{SURFACE}"/>'
        f'<image href="{avatar}" x="{ax - ar}" y="{ay - ar}" width="{ar * 2}" height="{ar * 2}" clip-path="url(#av)"/>'
        # message + follow
        f'<g id="msgbtn"><circle cx="{px + pw - 130}" cy="{py + bh + 30}" r="18" fill="{SURFACE}" stroke="{X_BORDER}" stroke-width="1.5"/>'
        f'<rect x="{px + pw - 139}" y="{py + bh + 24}" width="18" height="13" rx="2" fill="none" stroke="{INK}" stroke-width="1.7"/>'
        f'<path d="M{px + pw - 139} {py + bh + 25} L{px + pw - 130} {py + bh + 32} L{px + pw - 121} {py + bh + 25}" fill="none" stroke="{INK}" stroke-width="1.7"/></g>'
        f'<rect x="{px + pw - 100}" y="{py + bh + 12}" width="80" height="36" rx="18" fill="{INK}"/>'
        f'<text x="{px + pw - 60}" y="{py + bh + 35}" text-anchor="middle" font-family="{SANS}" font-size="15" font-weight="700" fill="{ON_INK}">Follow</text>'
        # identity
        f'<text x="{px + 22}" y="{py + bh + 84}" font-family="{SANS}" font-size="21" font-weight="800" fill="{INK}">shashank sn</text>'
        + verified(px + 22 + name_w + 14, py + bh + 77)
        + f'<text x="{px + 22}" y="{py + bh + 106}" font-family="{SANS}" font-size="15" fill="{X_MUTED}">@istupidpreneur</text>'
        f'<text x="{px + 22}" y="{py + bh + 138}" font-family="{SANS}" font-size="15" fill="{INK}">idiot savant</text>'
        # link + join date icons
        f'<g fill="none" stroke="{X_MUTED}" stroke-width="1.6" stroke-linecap="round">'
        f'<path d="M{px + 26} {py + bh + 165} l6 -6 M{px + 23} {py + bh + 163} a4 4 0 0 1 0 -5.5 l2 -2 a4 4 0 0 1 5.5 0 M{px + 35} {py + bh + 161} a4 4 0 0 1 0 5.5 l-2 2 a4 4 0 0 1 -5.5 0"/>'
        f'<rect x="{px + 150}" y="{py + bh + 155}" width="14" height="13" rx="2"/><path d="M{px + 150} {py + bh + 159} h14 M{px + 154} {py + bh + 152} v4 M{px + 160} {py + bh + 152} v4"/></g>'
        f'<text x="{px + 42}" y="{py + bh + 167}" font-family="{SANS}" font-size="14" fill="{X_BLUE}">getellora.com</text>'
        f'<text x="{px + 170}" y="{py + bh + 167}" font-family="{SANS}" font-size="14" fill="{X_MUTED}">Joined November 2024</text>'
    )

    css = []
    bubbles = []
    for k, (msg, s0, s1) in enumerate([("we built something good.", 18, 30), ("people still pick the other one.", 36, 50)]):
        bw = len(msg) * 7.1 + 28  # 13.5px semibold averages ~7.1px a character
        x, y = dx + dw - 16 - bw, dy + 112 + k * 48
        bubbles.append(
            f'<g id="m{k}"><rect x="{x:.0f}" y="{y}" width="{bw:.0f}" height="34" rx="17" fill="{X_BLUE}"/>'
            f'<clipPath id="t{k}"><rect x="{x + 12:.0f}" y="{y}" width="0" height="34"/></clipPath>'
            f'<text x="{x + 14:.0f}" y="{y + 22}" clip-path="url(#t{k})" font-family="{SANS}" font-size="13.5" font-weight="600" fill="{ON_ACCENT}">{msg}</text></g>'
        )
        css.append(
            f"@keyframes m{k}{{0%,{s0}%{{opacity:0;transform:translateY(8px)}}{s0 + 2}%,92%{{opacity:1;transform:translateY(0)}}97%,100%{{opacity:0}}}}#m{k}{{animation:m{k} {total}s infinite}}"
            f"@keyframes t{k}{{0%,{s0 + 1}%{{width:0}}{s1}%,100%{{width:{bw - 22:.0f}px}}}}#t{k} rect{{animation:t{k} {total}s infinite linear}}"
        )
    ty = dy + 112 + 2 * 48
    dm = (
        f'<clipPath id="av2"><circle cx="{dx + 30}" cy="{dy + 30}" r="15"/></clipPath>'
        f'<g id="dm"><rect x="{dx}" y="{dy}" width="{dw}" height="{dh}" rx="16" fill="{SURFACE}" stroke="{LINE}" stroke-width="2"/>'
        f'<image href="{avatar}" x="{dx + 15}" y="{dy + 15}" width="30" height="30" clip-path="url(#av2)"/>'
        f'<text x="{dx + 54}" y="{dy + 35}" font-family="{SANS}" font-size="15" font-weight="800" fill="{INK}">shashank sn</text>'
        + verified(dx + 54 + dm_name_w + 12, dy + 30, 7.5)
        + f'<g transform="translate({dx + dw - 38} {dy + 19}) scale(.85)"><path d="{X_LOGO}" fill="{INK}"/></g>'
        f'<line x1="{dx}" y1="{dy + 58}" x2="{dx + dw}" y2="{dy + 58}" stroke="{LINE}" stroke-width="2"/>'
        f'<text x="{dx + dw / 2}" y="{dy + 84}" text-anchor="middle" font-family="{SANS}" font-size="12" fill="{X_MUTED}">@istupidpreneur · 5,705 posts</text>'
        f'<rect x="{dx + 16}" y="{dy + dh - 46}" width="{dw - 32}" height="32" rx="16" fill="{X_FIELD}"/>'
        f'<text x="{dx + 32}" y="{dy + dh - 25}" font-family="{SANS}" font-size="13" fill="{X_MUTED}">start a new message</text>'
        + "".join(bubbles)
        + f'<g id="typing"><rect x="{dx + 16}" y="{ty}" width="64" height="34" rx="17" fill="{X_FIELD}"/>'
        + "".join(f'<circle class="dot" style="animation-delay:{i * 0.15:.2f}s" cx="{dx + 34 + i * 14}" cy="{ty + 17}" r="4" fill="{X_MUTED}"/>' for i in range(3))
        + "</g></g>"
    )

    click_x, click_y = px + pw - 126, py + bh + 34
    css.append(
        f"@keyframes typing{{0%,54%{{opacity:0}}57%,92%{{opacity:1}}97%,100%{{opacity:0}}}}#typing{{animation:typing {total}s infinite}}"
        "@keyframes dot{0%,60%,100%{transform:translateY(0)}30%{transform:translateY(-5px)}}.dot{animation:dot 1s infinite}"
        f"@keyframes dm{{0%,12%{{opacity:.3}}15%,94%{{opacity:1}}100%{{opacity:.3}}}}#dm{{animation:dm {total}s infinite}}"
        f"@keyframes cur{{0%{{transform:translate(480px,{h}px)}}10%{{transform:translate({click_x:.0f}px,{click_y:.0f}px)}}"
        f"12%{{transform:translate({click_x:.0f}px,{click_y + 3:.0f}px)}}14%,100%{{transform:translate({click_x:.0f}px,{click_y:.0f}px)}}}}"
        f"#cur{{animation:cur {total}s infinite cubic-bezier(.6,0,.3,1)}}"
        f"@keyframes btn{{0%,10%{{opacity:1}}12%{{opacity:.5}}14%,100%{{opacity:1}}}}#msgbtn{{animation:btn {total}s infinite}}"
    )
    write("p5-x", h, profile + dm + cursor(), "".join(css))


def main():
    OUT.mkdir(exist_ok=True)
    FONT_CACHE.mkdir(exist_ok=True)
    for build in (receipt, shelf, choose, deck, editor, xpanel):
        build()


if __name__ == "__main__":
    main()
