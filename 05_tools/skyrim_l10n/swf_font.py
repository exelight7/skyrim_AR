"""Build a Scaleform font library SWF (DefineFont3) from TrueType fonts.

Structure mirrors Skyrim's fonts_en.swf: for each font a DefineFont3 (with layout), a DefineFontName,
a DefineEditText using it, and a PlaceObject2 that puts it on the stage.

Glyphs are copied from the TTF outlines (quadratic curves map 1:1 to SWF curved edges).
Arabic is expected to be pre-shaped into presentation forms (U+FB50-FDFF, U+FE70-FEFF), so every
presentation-form code point the source font can produce is included.

Usage:
    python -I swf_font.py --out fonts_ar.swf --font "Name=path.ttf[:bold][:wght=700]" [...] \
        [--chars-file extra.txt] [--sample "text shown in the placed field"]
"""
import argparse
import struct
import zlib

from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont

EM = 1024 * 20          # DefineFont3 EM square (twentieths of a 1024 grid)

# Base set: printable ASCII, Latin-1 punctuation and letters, general punctuation used by Skyrim text.
BASE_RANGES = [(0x20, 0x7E), (0xA0, 0xFF), (0x2010, 0x2027), (0x2030, 0x203A), (0x2122, 0x2122),
               (0x0600, 0x06FF), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF)]


# ---------------------------------------------------------------- bit writer
class Bits:
    def __init__(self):
        self.out = bytearray()
        self.acc = 0
        self.n = 0

    def ub(self, value, nbits):
        for i in range(nbits - 1, -1, -1):
            self.acc = (self.acc << 1) | ((value >> i) & 1)
            self.n += 1
            if self.n == 8:
                self.out.append(self.acc)
                self.acc = self.n = 0

    def sb(self, value, nbits):
        self.ub(value & ((1 << nbits) - 1), nbits)

    def flush(self):
        if self.n:
            self.out.append(self.acc << (8 - self.n))
            self.acc = self.n = 0
        return bytes(self.out)


def sbits(*values):
    """Minimum signed bit count holding all values."""
    n = 1
    for v in values:
        while not (-(1 << (n - 1)) <= v < (1 << (n - 1))):
            n += 1
    return n


def rect(xmin, xmax, ymin, ymax):
    n = sbits(xmin, xmax, ymin, ymax)
    b = Bits()
    b.ub(n, 5)
    for v in (xmin, xmax, ymin, ymax):
        b.sb(v, n)
    return b.flush()


# ---------------------------------------------------------------- glyph -> SWF shape
class ShapePen(BasePen):
    """Collect contours as SWF edges in EM units (y flipped: SWF y grows downward)."""

    def __init__(self, glyphset, scale):
        super().__init__(glyphset)
        self.scale = scale
        self.records = []      # ('move', x, y) / ('line', x, y) / ('curve', cx, cy, x, y), absolute
        self.start = None
        self.cur = None

    def _pt(self, p):
        return round(p[0] * self.scale), round(-p[1] * self.scale)

    def _moveTo(self, p):
        self.start = self.cur = self._pt(p)
        self.records.append(("move",) + self.cur)

    def _lineTo(self, p):
        q = self._pt(p)
        if q != self.cur:
            self.records.append(("line",) + q)
            self.cur = q

    def _qCurveToOne(self, p1, p2):
        c, a = self._pt(p1), self._pt(p2)
        self.records.append(("curve",) + c + a)
        self.cur = a

    def _curveToOne(self, p1, p2, p3):
        # Cubic (CFF) fonts: approximate with two quadratics via midpoint split.
        p0 = self._getCurrentPoint()
        mid = [(p0[i] + 3 * p1[i] + 3 * p2[i] + p3[i]) / 8 for i in range(2)]
        c1 = [(p0[i] + 3 * p1[i]) / 4 * 1 for i in range(2)]
        c2 = [(3 * p2[i] + p3[i]) / 4 for i in range(2)]
        self._qCurveToOne(c1, mid)
        self._qCurveToOne(c2, p3)

    def _closePath(self):
        if self.cur != self.start:
            self.records.append(("line",) + self.start)
            self.cur = self.start

    _endPath = _closePath


def encode_shape(records):
    b = Bits()
    b.ub(1, 4)   # NumFillBits
    b.ub(0, 4)   # NumLineBits
    x = y = 0
    first = True
    for r in records:
        if r[0] == "move":
            nx, ny = r[1], r[2]
            b.ub(0, 1)                       # non-edge
            b.ub(0, 1)                       # StateNewStyles
            b.ub(0, 1)                       # StateLineStyle
            b.ub(0, 1)                       # StateFillStyle1
            b.ub(1 if first else 0, 1)       # StateFillStyle0
            b.ub(1, 1)                       # StateMoveTo
            n = sbits(nx, ny)
            b.ub(n, 5)
            b.sb(nx, n)
            b.sb(ny, n)
            if first:
                b.ub(1, 1)                   # FillStyle0 = 1
                first = False
            x, y = nx, ny
        elif r[0] == "line":
            dx, dy = r[1] - x, r[2] - y
            n = max(2, sbits(dx, dy))
            b.ub(1, 1)
            b.ub(1, 1)                       # straight
            b.ub(n - 2, 4)
            b.ub(1, 1)                       # general line
            b.sb(dx, n)
            b.sb(dy, n)
            x, y = r[1], r[2]
        else:
            cdx, cdy = r[1] - x, r[2] - y
            adx, ady = r[3] - r[1], r[4] - r[2]
            n = max(2, sbits(cdx, cdy, adx, ady))
            b.ub(1, 1)
            b.ub(0, 1)                       # curved
            b.ub(n - 2, 4)
            for v in (cdx, cdy, adx, ady):
                b.sb(v, n)
            x, y = r[3], r[4]
    b.ub(0, 6)                               # end record
    return b.flush()


# ---------------------------------------------------------------- tags
def tag(code, body):
    if len(body) < 63:
        return struct.pack("<H", (code << 6) | len(body)) + body
    return struct.pack("<HI", (code << 6) | 63, len(body)) + body


def load_font(path, wght=None):
    f = TTFont(path)
    if "fvar" in f:
        from fontTools.varLib import instancer
        axes = {a.axisTag: a.defaultValue for a in f["fvar"].axes}
        if wght is not None:
            axes["wght"] = wght
        f = instancer.instantiateVariableFont(f, axes)
    return f


ZWJ = "‍"


def presentation_form_glyphs(ttf):
    """Map presentation-form code points to the glyphs the font's own GSUB produces.

    Many fonts keep legacy, unmaintained outlines on the U+FB50-FEFF cmap entries (wrong weight,
    missing variations). Shaping the base letter in context with HarfBuzz yields the glyphs the
    designer actually uses for init/medi/fina/isol and the lam-alef ligatures.
    """
    import io
    import unicodedata

    import uharfbuzz as hb

    data = io.BytesIO()
    ttf.save(data)
    face = hb.Face(data.getvalue())
    font = hb.Font(face)
    order = ttf.getGlyphOrder()
    out = {}
    for cp in list(range(0xFB50, 0xFE00)) + list(range(0xFE70, 0xFF00)):
        decomp = unicodedata.decomposition(chr(cp))
        if not decomp.startswith("<"):
            continue
        form, *hexes = decomp.split()
        base = "".join(chr(int(h, 16)) for h in hexes)
        text = {"<initial>": base + ZWJ, "<medial>": ZWJ + base + ZWJ, "<final>": ZWJ + base,
                "<isolated>": base}.get(form)
        if text is None:
            continue
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(font, buf, {})
        gids = [i.codepoint for i in buf.glyph_infos if order[i.codepoint] not in (".notdef",)
                and i.cluster < len(text) and text[i.cluster] != ZWJ]
        # Accept only a single resulting glyph (ligatures such as lam-alef included).
        real = [g for g in gids if g != 0]
        if len(real) == 1:
            out[cp] = order[real[0]]
    return out


def define_font3(font_id, name, ttf, codes, bold=False):
    cmap = dict(ttf.getBestCmap())
    shaped = presentation_form_glyphs(ttf)
    cmap.update(shaped)              # prefer GSUB-derived glyphs over legacy cmap entries
    gs = ttf.getGlyphSet()
    upm = ttf["head"].unitsPerEm
    scale = EM / upm
    hmtx = ttf["hmtx"]
    glyphs = []
    for cp in sorted(c for c in set(codes) if c in cmap):
        gname = cmap[cp]
        pen = ShapePen(gs, scale)
        gs[gname].draw(pen)
        shape = encode_shape(pen.records)
        xs = [r[i] for r in pen.records for i in range(1, len(r), 2)] or [0]
        ys = [r[i] for r in pen.records for i in range(2, len(r), 2)] or [0]
        adv = min(32767, round(hmtx[gname][0] * scale))
        glyphs.append((cp, shape, adv, (min(xs), max(xs), min(ys), max(ys))))
    n = len(glyphs)
    shapes = b"".join(g[1] for g in glyphs)
    wide = (n + 1) * 2 + len(shapes) > 0xFFFF
    w = 4 if wide else 2
    offsets, pos = [], (n + 1) * w
    for g in glyphs:
        offsets.append(pos)
        pos += len(g[1])
    fmt = "<I" if wide else "<H"
    table = b"".join(struct.pack(fmt, o) for o in offsets) + struct.pack(fmt, pos) + shapes
    hhea = ttf["hhea"]
    ascent = round(hhea.ascent * scale)
    descent = round(-hhea.descent * scale)
    leading = round(hhea.lineGap * scale)
    flags = 0x80 | 0x04 | (0x08 if wide else 0) | (0x01 if bold else 0)
    nb = name.encode("utf-8")
    body = struct.pack("<HBBB", font_id, flags, 1, len(nb)) + nb + struct.pack("<H", n) + table
    body += b"".join(struct.pack("<H", g[0]) for g in glyphs)
    body += struct.pack("<HHh", min(ascent, 65535), min(descent, 65535), leading)
    body += b"".join(struct.pack("<h", g[2]) for g in glyphs)
    body += b"".join(rect(*g[3]) for g in glyphs)
    body += struct.pack("<H", 0)      # no kerning pairs
    return body, n


def define_font_name(font_id, name, copyright_text):
    return struct.pack("<H", font_id) + name.encode("utf-8") + b"\0" + copyright_text.encode("utf-8") + b"\0"


def define_edit_text(char_id, font_id, text, height_twips=400):
    # HasText|ReadOnly|HasTextColor|HasFont  /  NoSelect|UseOutlines
    flags1 = 0x80 | 0x08 | 0x04 | 0x01
    flags2 = 0x10 | 0x01
    body = struct.pack("<H", char_id) + rect(0, 20000, 0, 2000) + bytes([flags1, flags2])
    body += struct.pack("<HH", font_id, height_twips) + bytes([0, 0, 0, 255])
    body += b"\0" + text.encode("utf-8") + b"\0"
    return body


def place_object2(depth, char_id, y_twips):
    m = Bits()
    m.ub(0, 1)        # HasScale
    m.ub(0, 1)        # HasRotate
    n = sbits(0, y_twips)
    m.ub(n, 5)
    m.sb(0, n)
    m.sb(y_twips, n)
    return bytes([0x06]) + struct.pack("<HH", depth, char_id) + m.flush()


def build_swf(fonts, codes, sample, version=15):
    tags = [tag(69, struct.pack("<I", 0)), tag(9, b"\xff\xff\xff")]
    summary = []
    char_id = 1
    for depth, (name, path, bold, wght, copyright_text) in enumerate(fonts, start=1):
        ttf = load_font(path, wght)
        body, n = define_font3(char_id, name, ttf, codes, bold)
        tags.append(tag(75, body))
        tags.append(tag(88, define_font_name(char_id, name, copyright_text)))
        tags.append(tag(37, define_edit_text(char_id + 1, char_id, sample)))
        tags.append(tag(26, place_object2(depth, char_id + 1, depth * 600)))
        summary.append((name, n, len(body)))
        char_id += 2
    tags.append(tag(1, b""))
    tags.append(tag(0, b""))
    payload = rect(0, 1280 * 20, 0, 720 * 20) + struct.pack("<HH", 24 << 8, 1) + b"".join(tags)
    total = 8 + len(payload)
    swf = b"CWS" + bytes([version]) + struct.pack("<I", total) + zlib.compress(payload, 9)
    return swf, summary


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--font", action="append", required=True,
                    help='"Font Name=path.ttf[:bold][:wght=700]"; repeatable')
    ap.add_argument("--chars-file", help="UTF-8 text whose characters must also be included")
    ap.add_argument("--sample", default="ABC abc 123 \ufeb3\ufefc\ufe8e\ufee1")
    ap.add_argument("--copyright", default="SIL Open Font License 1.1 (see LICENSES)")
    args = ap.parse_args()
    codes = set()
    for a, z in BASE_RANGES:
        codes.update(range(a, z + 1))
    if args.chars_file:
        with open(args.chars_file, encoding="utf-8") as f:
            codes.update(ord(c) for c in f.read() if ord(c) > 0x1F and ord(c) <= 0xFFFF)
    fonts = []
    for spec in args.font:
        name, _, rest = spec.partition("=")
        parts = rest.split(":")
        path, bold, wght = parts[0], False, None
        for p in parts[1:]:
            if p == "bold":
                bold = True
            elif p.startswith("wght="):
                wght = float(p[5:])
        if len(parts) > 1 and len(parts[0]) == 1:   # Windows drive letter "C:\..."
            path = parts[0] + ":" + parts[1]
            for p in parts[2:]:
                if p == "bold":
                    bold = True
                elif p.startswith("wght="):
                    wght = float(p[5:])
        fonts.append((name, path, bold, wght, args.copyright))
    swf, summary = build_swf(fonts, codes, args.sample)
    with open(args.out, "wb") as f:
        f.write(swf)
    for name, n, size in summary:
        print(f"{name}: {n} glyphs, {size} bytes")
    print(f"wrote {args.out} ({len(swf)} bytes)")


if __name__ == "__main__":
    main()
