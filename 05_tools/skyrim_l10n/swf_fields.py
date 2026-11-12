"""List text fields (DefineEditText) in Scaleform menu SWFs with their instance names and geometry.

Output (JSON): one entry per placed text field: swf, sprite id, instance name, width/height (px at stage
scale), font id/name, font height (px), alignment, wordWrap/multiline/html flags, variable name.

Usage:
    python -I swf_fields.py <menu.swf> [...] --out fields.json
"""
import argparse
import json
import os
import struct
import zlib

ALIGN = {0: "left", 1: "right", 2: "center", 3: "justify"}


class BitReader:
    def __init__(self, data, pos=0):
        self.d, self.byte, self.bit = data, pos, 0

    def ub(self, n):
        v = 0
        for _ in range(n):
            v = (v << 1) | ((self.d[self.byte] >> (7 - self.bit)) & 1)
            self.bit += 1
            if self.bit == 8:
                self.bit, self.byte = 0, self.byte + 1
        return v

    def sb(self, n):
        v = self.ub(n)
        return v - (1 << n) if n and v & (1 << (n - 1)) else v

    def align(self):
        if self.bit:
            self.bit, self.byte = 0, self.byte + 1
        return self.byte


def read_rect(d, pos):
    r = BitReader(d, pos)
    n = r.ub(5)
    vals = [r.sb(n) for _ in range(4)]
    return vals, r.align()


def iter_tags(d, pos, end):
    while pos < end:
        h = struct.unpack_from("<H", d, pos)[0]
        code, ln = h >> 6, h & 63
        pos += 2
        if ln == 63:
            ln = struct.unpack_from("<I", d, pos)[0]
            pos += 4
        yield code, pos, ln
        pos += ln
        if code == 0:
            break


def cstr(d, pos):
    end = d.index(b"\0", pos)
    return d[pos:end].decode("utf-8", "replace"), end + 1


def parse_edit_text(d, pos):
    cid = struct.unpack_from("<H", d, pos)[0]
    (xmin, xmax, ymin, ymax), p = read_rect(d, pos + 2)
    f1, f2 = d[p], d[p + 1]
    p += 2
    info = {"id": cid, "width": (xmax - xmin) / 20, "height": (ymax - ymin) / 20,
            "word_wrap": bool(f1 & 0x40), "multiline": bool(f1 & 0x20), "html": bool(f2 & 0x02),
            "auto_size": bool(f2 & 0x40)}
    if f1 & 0x01:
        info["font_id"] = struct.unpack_from("<H", d, p)[0]
        p += 2
    if f2 & 0x80:
        info["font_class"], p = cstr(d, p)
    if f1 & 0x01:
        info["font_px"] = struct.unpack_from("<H", d, p)[0] / 20
        p += 2
    if f1 & 0x04:
        p += 4
    if f1 & 0x02:
        p += 2
    if f2 & 0x20:
        info["align"] = ALIGN.get(d[p], d[p])
        p += 9
    info["variable"], p = cstr(d, p)
    if f1 & 0x80:
        info["initial_text"], p = cstr(d, p)
        info["initial_text"] = info["initial_text"][:120]
    return info


def parse_place(d, pos, ln, code):
    flags = d[pos]
    p = pos + 1
    flags2 = 0
    if code == 70:
        flags2 = d[p]
        p += 1
    p += 2  # depth
    if code == 70 and (flags2 & 0x08 or (flags2 & 0x10 and flags & 0x02)):
        _cls, p = cstr(d, p)
    cid = None
    if flags & 0x02:
        cid = struct.unpack_from("<H", d, p)[0]
        p += 2
    if flags & 0x04:
        r = BitReader(d, p)
        if r.ub(1):
            n = r.ub(5)
            r.sb(n)
            r.sb(n)
        if r.ub(1):
            n = r.ub(5)
            r.sb(n)
            r.sb(n)
        n = r.ub(5)
        r.sb(n)
        r.sb(n)
        p = r.align()
    if flags & 0x08:   # color transform
        r = BitReader(d, p)
        has_add, has_mult = r.ub(1), r.ub(1)
        n = r.ub(4)
        for _ in range((4 if has_mult else 0) + (4 if has_add else 0)):
            r.sb(n)
        p = r.align()
    if flags & 0x10:
        p += 2
    name = None
    if flags & 0x20:
        name, p = cstr(d, p)
    return cid, name


def analyze(path):
    raw = open(path, "rb").read()
    d = raw[:8] + (zlib.decompress(raw[8:]) if raw[:3] == b"CWS" else raw[8:])
    _r, p = read_rect(d, 8)
    p += 4
    fonts, edits, places = {}, {}, []

    def walk(start, end, sprite):
        for code, pos, ln in iter_tags(d, start, end):
            if code in (48, 75):
                fid = struct.unpack_from("<H", d, pos)[0]
                nl = d[pos + 4]
                fonts[fid] = d[pos + 5:pos + 5 + nl].decode("utf-8", "replace").rstrip("\0")
            elif code == 37:
                e = parse_edit_text(d, pos)
                edits[e["id"]] = e
            elif code in (26, 70):
                try:
                    cid, name = parse_place(d, pos, ln, code)
                except (IndexError, struct.error):
                    continue
                if cid is not None:
                    places.append((sprite, cid, name))
            elif code == 39:
                sid = struct.unpack_from("<H", d, pos)[0]
                walk(pos + 4, pos + ln, sid)

    walk(p, len(d), 0)
    out = []
    for sprite, cid, name in places:
        if cid in edits:
            e = dict(edits[cid])
            e["font"] = fonts.get(e.get("font_id"))
            out.append({"swf": os.path.basename(path), "sprite": sprite, "instance": name, **e})
    # Unplaced text fields (instantiated from ActionScript) are listed too.
    placed = {cid for _s, cid, _n in places}
    for cid, e in edits.items():
        if cid not in placed:
            out.append({"swf": os.path.basename(path), "sprite": None, "instance": None, **e,
                        "font": fonts.get(e.get("font_id"))})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("swfs", nargs="+")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    rows = []
    for s in args.swfs:
        rows.extend(analyze(s))
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1, ensure_ascii=False)
    print(f"{len(rows)} text fields -> {args.out}")


if __name__ == "__main__":
    main()
