"""Context-linking coverage report (JSON) from the project DB.

Usage:
    python -I context_report.py --project <project_root>
"""
import argparse
import json
import os
import sqlite3


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    args = ap.parse_args()
    con = sqlite3.connect(os.path.join(args.project, "03_translation", "db", "l10n.sqlite"))
    q = lambda sql, *p: con.execute(sql, p).fetchall()  # noqa: E731

    dl = "category='dialogue_line'"
    report = {
        "eligibility": dict(q("SELECT eligibility, COUNT(*) FROM source_strings GROUP BY 1")),
        "linked_non_empty": q("SELECT SUM(record_type IS NOT NULL), COUNT(*) FROM source_strings"
                              " WHERE eligibility!='EMPTY'")[0],
        "categories": dict(q("SELECT category, COUNT(*) FROM source_strings WHERE eligibility!='EMPTY'"
                             " GROUP BY 1 ORDER BY 2 DESC")),
        "by_plugin_eligibility": [list(r) for r in q(
            "SELECT plugin, eligibility, COUNT(*) FROM source_strings GROUP BY 1,2 ORDER BY 1,2")],
        "dialogue": {
            "lines": q(f"SELECT COUNT(*) FROM source_strings WHERE {dl}")[0][0],
            "with_quest": q(f"SELECT COUNT(*) FROM source_strings WHERE {dl} AND quest_edid IS NOT NULL")[0][0],
            "speaker_exact_npc": q(f"SELECT COUNT(*) FROM source_strings WHERE {dl} AND speaker IS NOT NULL"
                                   " AND speaker NOT LIKE '%:%:%' AND speaker NOT LIKE 'voice:%'"
                                   " AND speaker NOT LIKE 'faction:%' AND speaker NOT LIKE 'race:%'"
                                   " AND speaker NOT LIKE 'alias:%'")[0][0],
            "speaker_quest_alias": q(f"SELECT COUNT(*) FROM source_strings WHERE {dl} AND speaker LIKE 'alias:%'")[0][0],
            "speaker_voice_type": q(f"SELECT COUNT(*) FROM source_strings WHERE {dl} AND speaker LIKE 'voice:%'")[0][0],
            "speaker_faction": q(f"SELECT COUNT(*) FROM source_strings WHERE {dl} AND speaker LIKE 'faction:%'")[0][0],
            "speaker_race": q(f"SELECT COUNT(*) FROM source_strings WHERE {dl} AND speaker LIKE 'race:%'")[0][0],
            "speaker_unknown": q(f"SELECT COUNT(*) FROM source_strings WHERE {dl} AND speaker IS NULL")[0][0],
            "speaker_multiple_candidates": q(f"SELECT COUNT(*) FROM source_strings WHERE {dl}"
                                             " AND speaker LIKE 'multiple:%'")[0][0],
            "speaker_source": dict(q(f"SELECT COALESCE(speaker_source,'unknown'), COUNT(*) FROM source_strings"
                                     f" WHERE {dl} GROUP BY 1 ORDER BY 2 DESC")),
            "unknown_speaker_by_quest": [list(r) for r in q(
                f"SELECT quest_edid, COUNT(*) FROM source_strings WHERE {dl} AND speaker IS NULL"
                " GROUP BY 1 ORDER BY 2 DESC LIMIT 20")],
        },
        "context_flags": {
            "player_gender_conditioned": q("SELECT COUNT(*) FROM source_strings"
                                           " WHERE context_flags LIKE '%player_gender_conditioned%'")[0][0],
            "speaker_gender_conditioned": q("SELECT COUNT(*) FROM source_strings"
                                            " WHERE context_flags LIKE '%speaker_gender_conditioned%'")[0][0],
            "shared_response": q("SELECT COUNT(*) FROM source_strings WHERE context_flags LIKE '%shared_response%'")[0][0],
        },
        "tables": {t: q(f"SELECT COUNT(*) FROM {t}")[0][0]
                   for t in ("string_refs", "records", "quests", "topics", "infos", "speakers", "scenes",
                             "actor_refs")},
        "top_quests_by_lines": [list(r) for r in q(
            f"SELECT quest_edid, COUNT(*) FROM source_strings WHERE {dl} GROUP BY 1 ORDER BY 2 DESC LIMIT 30")],
    }
    out = os.path.join(args.project, "08_qa", "reports", "coverage_context.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1, ensure_ascii=False)
    print(json.dumps({k: report[k] for k in ("eligibility", "linked_non_empty", "dialogue", "context_flags",
                                             "tables")}, indent=1))
    print("top quests:", report["top_quests_by_lines"][:12])
    print(f"report: {out}")


if __name__ == "__main__":
    main()
