"""Tests for the Arabic pipeline (shaper, bidi parity, font library coverage).

Needs the project venv (Pillow, python-bidi, arabic-reshaper); skipped otherwise.
Run: <venv python> -I -m unittest discover -s 05_tools/tests -v
"""
import json
import os
import struct
import sys
import unittest
import zlib

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)

try:
    import arabic_reshaper
    from bidi.algorithm import get_display

    from skyrim_l10n import arabic
    HAVE_DEPS = True
except ImportError:
    HAVE_DEPS = False

SWF = os.path.join(PROJECT, "04_fonts", "build", "fonts_ar.swf")
MOD = os.path.join(PROJECT, "07_patch", "SkyrimArabic_RenderTest")


def swf_font_codes(path):
    """Return {font name: set(code points)} from DefineFont3 tags."""
    with open(path, "rb") as f:
        raw = f.read()
    d = raw[:8] + zlib.decompress(raw[8:])
    nbits = d[8] >> 3
    pos = 8 + (5 + 4 * nbits + 7) // 8 + 4
    fonts = {}
    while pos < len(d):
        h = struct.unpack_from("<H", d, pos)[0]
        code, ln = h >> 6, h & 63
        pos += 2
        if ln == 63:
            ln = struct.unpack_from("<I", d, pos)[0]
            pos += 4
        if code == 75:
            b = d[pos:pos + ln]
            flags, nl = b[2], b[4]
            name = b[5:5 + nl].decode()
            p = 5 + nl
            n = struct.unpack_from("<H", b, p)[0]
            p += 2
            w = 4 if flags & 0x08 else 2
            cto = struct.unpack_from("<I" if w == 4 else "<H", b, p + n * w)[0]
            codes = [struct.unpack_from("<H", b, p + cto + 2 * i)[0] for i in range(n)]
            assert codes == sorted(codes), f"{name}: code table not sorted"
            fonts.setdefault(name, set()).update(codes)
        if code == 0:
            break
        pos += ln
    return fonts


@unittest.skipUnless(HAVE_DEPS, "venv dependencies missing")
class ShaperTests(unittest.TestCase):
    CASES = ["المستوى 25 – 100% – الساعة 3:45", "نسبة 100% فقط", "الصيحات (Thu'um) بسرعة",
             "اكسب 50 قطعة ذهبية [T05]", "الضرر -20 نقطة", "<mag> نقطة", "عام 4E 201", "لا، لأ، لإ، لآ"]

    def test_bidi_matches_independent_reference(self):
        rs = arabic_reshaper.ArabicReshaper({"delete_harakat": False, "support_ligatures": True})
        for t in self.CASES:
            with self.subTest(text=t):
                self.assertEqual(arabic.to_visual(t, "short_label"), get_display(rs.reshape(t), base_dir="R"))

    def test_tokens_preserved_and_lines_fit(self):
        text = ("تحدّث إلى <Alias=Questgiver> في <Alias=Location> واحصل على <Global=GoldReward> قطعة ذهبية، "
                "ثم عُد قبل أن تمر <dur> ساعة على %d من الأيام.")
        for ctx in ("subtitle", "journal_objective", "dialogue_topic", "book_page", "message_box"):
            with self.subTest(context=ctx):
                vis = arabic.to_visual(text, ctx)
                self.assertEqual(arabic.tokens(vis), arabic.tokens(text))
                limit = arabic.CONTEXTS[ctx]["width"] * arabic.CONTEXTS[ctx]["safety"]
                self.assertLessEqual(arabic.max_line_width(vis, ctx), limit)

    def test_selftest(self):
        arabic.selftest()


@unittest.skipUnless(os.path.exists(SWF), "font library not built")
class FontLibraryTests(unittest.TestCase):
    def test_fonts_present_and_sorted(self):
        fonts = swf_font_codes(SWF)
        self.assertEqual(set(fonts), {"SkyrimArabic UI", "SkyrimArabic UI Bold", "SkyrimArabic Book", "SkyrimArabic Hand"})

    @unittest.skipUnless(os.path.isdir(MOD), "render test mod not built")
    def test_every_character_of_the_test_pack_is_covered(self):
        sys.path.insert(0, TOOLS)
        from skyrim_l10n.strings_io import StringTable
        fonts = swf_font_codes(SWF)
        with open(os.path.join(MOD, "render_test_manifest.json"), encoding="utf-8") as f:
            targets = {e["target"] for e in json.load(f)["entries"] if not e["target"].startswith("$")}
        used = set()
        sdir = os.path.join(MOD, "Strings")
        for name in os.listdir(sdir):
            plugin, kind = name.rsplit("_english.", 1)
            for sid, val in StringTable.load(os.path.join(sdir, name)).items():
                if f"{plugin}|{kind}|0x{sid:08X}" in targets:
                    used.update(ord(c) for c in val.decode("utf-8") if ord(c) >= 0x20)
        for font in ("SkyrimArabic UI", "SkyrimArabic UI Bold", "SkyrimArabic Book"):
            missing = sorted(c for c in used if c not in fonts[font] and c != 0xA0)
            self.assertEqual(missing, [], f"{font} lacks {[hex(c) for c in missing[:20]]}")


if __name__ == "__main__":
    unittest.main()
