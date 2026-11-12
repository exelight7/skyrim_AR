"""Offline preview that emulates Scaleform text layout for the render-test variants.

Emulation: glyphs drawn left-to-right with no shaping (PIL BASIC layout), explicit newlines honoured,
and greedy left-to-right word wrapping at the field width (what the engine does when a line is too
long). Paragraph alignment comes from the context or an inline <p align="...">. This predicts layout;
it is NOT proof of in-game rendering.

Usage:
    python -I preview.py --project <root>
"""
import argparse
import json
import os
import re
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skyrim_l10n import arabic  # noqa: E402

TAG_RE = arabic.TAG_RE
SCALE = 1.5


def engine_wrap(line, font, width):
    """Scaleform-like greedy wrap of an already-visual line (left to right)."""
    words, out, cur = line.split(" "), [], ""
    for w in words:
        cand = f"{cur} {w}" if cur else w
        if cur and font.getlength(cand) > width:
            out.append(cur)
            cur = w
        else:
            cur = cand
    out.append(cur)
    return out


def draw_case(title, visual, ctx_name):
    ctx = arabic.CONTEXTS[ctx_name]
    font_path = os.path.join(arabic.PROJECT, arabic.CONTEXTS["_fonts"][ctx["font"]])
    size = round(ctx["font_px"] * SCALE)
    font = ImageFont.truetype(font_path, size, layout_engine=ImageFont.Layout.BASIC)
    width = round((ctx["width"] or 600) * SCALE)
    align = ctx["align"]
    m = re.search(r'<p align="(\w+)">', visual)
    if m:
        align = m.group(1)
    text = visual.replace("[pagebreak]", "\n— page —\n")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = TAG_RE.sub(lambda t: "" if t.group(0).startswith(("<p", "</p", "<font", "</font", "<b", "</b", "<i", "</i"))
                      else t.group(0), text)
    lines = []
    for raw in text.split("\n"):
        lines.extend(engine_wrap(raw, font, width))
    line_h = round(size * 1.35)
    head = 26
    img = Image.new("RGB", (width + 20, head + line_h * max(1, len(lines)) + 14), (24, 24, 24))
    d = ImageDraw.Draw(img)
    d.text((6, 4), f"{title}  [{ctx_name} {ctx['width']}px, align={align}]", fill=(150, 200, 255),
           font=ImageFont.truetype(font_path, 16, layout_engine=ImageFont.Layout.BASIC))
    d.rectangle([10, head, 10 + width, head + line_h * max(1, len(lines)) + 4], outline=(90, 90, 90))
    for i, ln in enumerate(lines):
        w = font.getlength(ln)
        x = {"right": 10 + width - w, "center": 10 + (width - w) / 2}.get(align, 10)
        d.text((x, head + 2 + i * line_h), ln, fill=(235, 235, 235), font=font)
    return img


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    args = ap.parse_args()
    man_path = os.path.join(args.project, "07_patch", "SkyrimArabic_RenderTest", "render_test_manifest.json")
    with open(man_path, encoding="utf-8") as f:
        manifest = json.load(f)["entries"]
    from skyrim_l10n.render_test import render_variant
    picked, seen = [], set()
    for e in manifest:
        k = (e["test"], e["variant"], e["logical"][:40])
        if k in seen:
            continue
        seen.add(k)
        picked.append(e)
    tiles = [draw_case(f"{e['test']}{e['variant']}", render_variant(e["logical"], e["context"], e["variant"], e["test"])
                       if not e["target"].startswith("$") or e["test"] != "T01" else arabic.to_visual(e["logical"], e["context"]),
                       e["context"]) for e in picked]
    out_dir = os.path.join(args.project, "08_qa", "render_tests", "preview")
    os.makedirs(out_dir, exist_ok=True)
    pages, page, h = [], [], 0
    for t in tiles:
        if h + t.height > 1800 and page:
            pages.append(page)
            page, h = [], 0
        page.append(t)
        h += t.height + 8
    pages.append(page)
    for n, page in enumerate(pages, 1):
        W = max(t.width for t in page)
        H = sum(t.height + 8 for t in page)
        sheet = Image.new("RGB", (W, H), (0, 0, 0))
        y = 0
        for t in page:
            sheet.paste(t, (0, y))
            y += t.height + 8
        sheet.save(os.path.join(out_dir, f"preview_{n}.png"))
    print(f"{len(tiles)} cases on {len(pages)} sheets -> {out_dir}")


if __name__ == "__main__":
    main()
