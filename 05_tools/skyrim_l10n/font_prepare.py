"""Prepare static, renamed TTFs for the Skyrim Arabic font library and for build-time measuring.

For each source font: instantiate variable axes, point every Arabic presentation-form code point at
the glyph the font's own GSUB produces (see swf_font.presentation_form_glyphs), and rename the
family. The same files feed swf_font.py and the line-wrapping measurer, so measured widths equal
in-game advances.

Usage:
    python -I font_prepare.py --out-dir 04_fonts/build/static \
        --font "SkyrimArabic UI|Regular|04_fonts/src/cairo/Cairo-VF.ttf|wght=400" ...
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skyrim_l10n.swf_font import load_font, presentation_form_glyphs  # noqa: E402


def rename(ttf, family, style):
    full = f"{family} {style}".strip()
    ps = full.replace(" ", "")
    for rec in ttf["name"].names:
        if rec.nameID in (1, 16):
            rec.string = family
        elif rec.nameID in (2, 17):
            rec.string = style
        elif rec.nameID == 4:
            rec.string = full
        elif rec.nameID == 6:
            rec.string = ps
        elif rec.nameID == 3:
            rec.string = f"{ps};SkyrimArabicProject"


def fit_metrics(ttf, scale, ascent, descent, gap):
    """Shrink every outline/advance by `scale` (UPM kept) and declare Futura-like line metrics.

    Skyrim's menus size single-line fields for Futura (ascent ~0.97em, descent ~0.22em). Scaleform
    puts the baseline at gutter + declared ascent, so Cairo's tall metrics (1.30/0.57em) pushed the
    baseline down and clipped every descender (dots under ya, bowls of nun/ra/qaf) in fixed fields.
    """
    from fontTools.ttLib.scaleUpem import scale_upem
    upm = ttf["head"].unitsPerEm
    scale_upem(ttf, round(upm * scale))
    ttf["head"].unitsPerEm = upm
    hhea, os2 = ttf["hhea"], ttf["OS/2"]
    hhea.ascent, hhea.descent, hhea.lineGap = ascent, -descent, gap
    os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap = ascent, -descent, gap
    os2.usWinAscent, os2.usWinDescent = ascent, descent


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--font", action="append", required=True, help='"Family|Style|source.ttf[|wght=700][|fit=0.85,840,360,180]"')
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)
    for spec in args.font:
        family, style, src, *opts = spec.split("|")
        wght = next((float(o[5:]) for o in opts if o.startswith("wght=")), None)
        ttf = load_font(src, wght)
        remap = presentation_form_glyphs(ttf)
        for table in ttf["cmap"].tables:
            if table.isUnicode():
                table.cmap.update(remap)
        fit = next((o[4:] for o in opts if o.startswith("fit=")), None)
        if fit:  # fit=scale,ascent,descent,gap  (font units)
            s, a, d, g = fit.split(",")
            fit_metrics(ttf, float(s), int(a), int(d), int(g))
        rename(ttf, family, style)
        out = os.path.join(args.out_dir, f"{family.replace(' ', '')}-{style}.ttf")
        ttf.save(out)
        print(f"{out}: {len(remap)} presentation forms mapped to GSUB glyphs")


if __name__ == "__main__":
    main()
