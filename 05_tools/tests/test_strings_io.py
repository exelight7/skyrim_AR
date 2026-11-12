"""Tests for strings_io: synthetic round trips plus byte-identical checks on the extracted originals.

Run: python -I -m unittest discover -s 05_tools/tests -v   (from the project root)
"""
import glob
import os
import struct
import sys
import unittest

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)

from skyrim_l10n import GAME_VERSION  # noqa: E402
from skyrim_l10n.strings_io import StringTable, roundtrip_check  # noqa: E402

ARABIC = "مرحباً بك في سكايرم، يا <Alias=Player>!".encode("utf-8")


class SyntheticTests(unittest.TestCase):
    def test_build_parse_all_kinds(self):
        entries = [(1, b"Iron Sword"), (2, ARABIC), (7, b""), (9, b"Iron Sword")]
        for kind in ("strings", "dlstrings", "ilstrings"):
            with self.subTest(kind=kind):
                data = StringTable.build(kind, entries)
                table = StringTable.parse(data, kind)
                self.assertEqual(list(table.items()), entries)
                self.assertEqual(table.as_dict()[2].decode("utf-8"), ARABIC.decode("utf-8"))

    def test_dedupe_shares_offsets(self):
        data = StringTable.build("strings", [(1, b"Yes."), (2, b"Yes.")], dedupe=True)
        table = StringTable.parse(data, "strings")
        self.assertEqual(table.directory[0][1], table.directory[1][1])
        data2 = StringTable.build("strings", [(1, b"Yes."), (2, b"Yes.")], dedupe=False)
        self.assertGreater(len(data2), len(data))

    def test_length_prefix_includes_nul(self):
        data = StringTable.build("dlstrings", [(5, b"abc")])
        self.assertEqual(struct.unpack_from("<I", data, 16)[0], 4)

    def test_rejects_embedded_nul(self):
        with self.assertRaises(ValueError):
            StringTable.build("strings", [(1, b"a\0b")])

    def test_rejects_size_mismatch(self):
        data = StringTable.build("strings", [(1, b"abc")]) + b"junk"
        with self.assertRaises(ValueError):
            StringTable.parse(data, "strings")


ORIGINALS = sorted(glob.glob(os.path.join(PROJECT, "01_original", GAME_VERSION, "strings", "*_english.*")))


@unittest.skipUnless(ORIGINALS, "originals not extracted yet")
class OriginalRoundtripTests(unittest.TestCase):
    def test_every_original_is_byte_identical(self):
        self.assertGreaterEqual(len(ORIGINALS), 30)
        for path in ORIGINALS:
            with self.subTest(file=os.path.basename(path)):
                self.assertTrue(roundtrip_check(path)["identical"])

    def test_every_value_is_utf8(self):
        for path in ORIGINALS:
            for sid, value in StringTable.load(path).items():
                try:
                    value.decode("utf-8")
                except UnicodeDecodeError:
                    self.fail(f"{os.path.basename(path)} id {sid:#x} is not UTF-8")


if __name__ == "__main__":
    unittest.main()
