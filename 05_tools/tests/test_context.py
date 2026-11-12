"""Regression tests for the context database built by link.py.

Run: python -I -m unittest discover -s 05_tools/tests -v   (from the project root)
"""
import json
import os
import sqlite3
import unittest

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT = os.path.dirname(TOOLS)
DB = os.path.join(PROJECT, "03_translation", "db", "l10n.sqlite")
FUNCS = os.path.join(TOOLS, "skyrim_l10n", "condition_functions.json")


def _has_context():
    if not os.path.exists(DB):
        return False
    con = sqlite3.connect(DB)
    return bool(con.execute("SELECT name FROM sqlite_master WHERE name='string_refs'").fetchone())


class ConditionFunctionTable(unittest.TestCase):
    def test_verified_names(self):
        with open(FUNCS, encoding="utf-8") as f:
            funcs = json.load(f)["functions"]
        # Indices verified against xEdit output; 130 is NOT GetIsSex (an earlier guess that xDump disproved).
        self.assertEqual(funcs["70"], "GetIsSex")
        self.assertEqual(funcs["72"], "GetIsID")
        self.assertEqual(funcs["131"], "GetPCIsSex")
        self.assertNotEqual(funcs.get("130"), "GetIsSex")


@unittest.skipUnless(_has_context(), "context not built yet")
class ContextCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.con = sqlite3.connect(DB)

    def test_every_non_empty_string_is_linked(self):
        n = self.con.execute("SELECT COUNT(*) FROM source_strings WHERE eligibility NOT IN ('EMPTY')"
                             " AND record_type IS NULL").fetchone()[0]
        self.assertEqual(n, 0)

    def test_no_reference_to_unknown_string(self):
        n = self.con.execute("SELECT COUNT(*) FROM string_refs r LEFT JOIN source_strings s ON s.key=r.key"
                             " WHERE s.key IS NULL").fetchone()[0]
        self.assertEqual(n, 0)

    def test_field_kind_consistency(self):
        # Spoken lines live in .ilstrings, quest journal entries and book text in .dlstrings.
        bad = self.con.execute("""
            SELECT COUNT(*) FROM string_refs r JOIN source_strings s ON s.key=r.key
            WHERE (r.field='NAM1' AND s.kind!='ilstrings')
               OR (r.record_type='QUST' AND r.field='CNAM' AND s.kind!='dlstrings')
               OR (r.record_type='BOOK' AND r.field='DESC' AND s.kind!='dlstrings')""").fetchone()[0]
        self.assertEqual(bad, 0)

    def test_every_dialogue_line_has_a_quest(self):
        n = self.con.execute("SELECT COUNT(*) FROM source_strings WHERE category='dialogue_line'"
                             " AND quest_edid IS NULL").fetchone()[0]
        self.assertEqual(n, 0)

    def test_unknown_speakers_stay_rare(self):
        total, unknown = self.con.execute("SELECT COUNT(*), SUM(speaker IS NULL) FROM source_strings"
                                          " WHERE category='dialogue_line'").fetchone()
        self.assertLess(unknown / total, 0.05)

    def test_known_scene_speakers(self):
        # MQ101 (Unbound): scene lines resolve through quest aliases to the named NPCs.
        names = {s for (s,) in self.con.execute("""
            SELECT n.source FROM source_strings d JOIN speakers p ON p.form_key=d.speaker
            JOIN source_strings n ON n.key=p.name_key
            WHERE d.quest_edid='MQ101' AND d.speaker_source='scene'""")}
        self.assertTrue({"Hadvar", "Ralof"} <= names, names)

    def test_mine_is_an_activation_prompt(self):
        cats = dict(self.con.execute("SELECT category, COUNT(*) FROM source_strings WHERE source='Mine'"
                                     " GROUP BY 1"))
        self.assertGreater(cats.get("activate_prompt", 0), 500)


if __name__ == "__main__":
    unittest.main()
