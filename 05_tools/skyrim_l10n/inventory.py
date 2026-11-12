"""Build the translation inventory (SQLite) from the extracted English originals.

Every row is keyed by a stable identifier: "<plugin>|<kind>|0x<string_id>".
Record/field context (FormID, record type, quest, speaker) is filled in by a later step.

Usage:
    python -I inventory.py --project <project_root>
"""
import argparse
import collections
import hashlib
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skyrim_l10n import GAME_VERSION, PLUGIN_SOURCES, STRING_KINDS  # noqa: E402
from skyrim_l10n.strings_io import StringTable  # noqa: E402

# Engine tokens that must survive translation untouched.
TOKEN_RX = re.compile(
    r"<(?:Alias|Global|BribeCost|mag|dur|area|chance|\d+)[^<>]*>"   # runtime substitutions
    r"|</?(?:p|font|b|i|u|br|BR|div|img|li|ul)\b[^<>]*>"            # HTML-like markup in books/UI
    r"|\[pagebreak\]"
    r"|%[-+0#]?\d*(?:\.\d+)?[dsifuxX](?![A-Za-z])"                     # printf style (not "50% damage")
    r"|\$[A-Za-z_][A-Za-z0-9_]*",                                     # $ translation keys
    re.I,
)

# Bethesda convention: .strings = short names, .dlstrings = long descriptions/books,
# .ilstrings = dialogue lines. Refined later with real record/field data.
KIND_HINT = {"strings": "short_text", "dlstrings": "long_text", "ilstrings": "dialogue"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS source_strings (
    key           TEXT PRIMARY KEY,
    plugin        TEXT NOT NULL,
    kind          TEXT NOT NULL,
    string_id     INTEGER NOT NULL,
    source        TEXT NOT NULL,
    source_sha1   TEXT NOT NULL,
    char_len      INTEGER NOT NULL,
    word_count    INTEGER NOT NULL,
    tokens_json   TEXT NOT NULL,
    kind_hint     TEXT NOT NULL,
    record_type   TEXT,
    form_id       TEXT,
    editor_id     TEXT,
    field         TEXT,
    quest_edid    TEXT,
    speaker       TEXT,
    category      TEXT,
    eligibility   TEXT NOT NULL DEFAULT 'UNCLASSIFIED',
    game_version  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_src_sha1 ON source_strings(source_sha1);
CREATE INDEX IF NOT EXISTS ix_src_plugin ON source_strings(plugin, kind);

CREATE TABLE IF NOT EXISTS interface_strings (
    key           TEXT PRIMARY KEY,
    source        TEXT NOT NULL,
    tokens_json   TEXT NOT NULL,
    eligibility   TEXT NOT NULL DEFAULT 'UNCLASSIFIED',
    game_version  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS translations (
    key           TEXT PRIMARY KEY,
    target        TEXT NOT NULL,
    status        TEXT NOT NULL,          -- DRAFT, REVIEWED, ACCEPTED, BLOCKED_CONTEXT
    batch_id      TEXT,
    source_sha1   TEXT NOT NULL,          -- detects source changes after a game update
    updated_utc   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS qa_results (
    key           TEXT NOT NULL,
    batch_id      TEXT,
    check_id      TEXT NOT NULL,
    severity      TEXT NOT NULL,          -- CRITICAL, HIGH, MEDIUM, LOW
    message       TEXT NOT NULL,
    resolved      INTEGER NOT NULL DEFAULT 0,
    created_utc   TEXT NOT NULL
);
"""


def tokens_of(text):
    return TOKEN_RX.findall(text)


def build(project):
    src_dir = os.path.join(project, "01_original", GAME_VERSION)
    db_path = os.path.join(project, "03_translation", "db", "l10n.sqlite")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)
    con.execute("DELETE FROM source_strings")
    con.execute("DELETE FROM interface_strings")

    rows = []
    for plugin in PLUGIN_SOURCES:
        for kind in STRING_KINDS:
            table = StringTable.load(os.path.join(src_dir, "strings", f"{plugin}_english.{kind}"))
            for sid, raw in table.items():
                text = raw.decode("utf-8")
                rows.append((
                    f"{plugin}|{kind}|0x{sid:08X}", plugin, kind, sid, text,
                    hashlib.sha1(raw).hexdigest(), len(text), len(text.split()),
                    json.dumps(tokens_of(text), ensure_ascii=False), KIND_HINT[kind],
                    "EMPTY" if not text.strip() else "UNCLASSIFIED", GAME_VERSION,
                ))
    con.executemany(
        "INSERT INTO source_strings (key, plugin, kind, string_id, source, source_sha1, char_len, word_count,"
        " tokens_json, kind_hint, eligibility, game_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)

    with open(os.path.join(src_dir, "interface", "translate_english.txt"), "rb") as f:
        text = f.read().decode("utf-16")
    ui_rows = []
    for line in text.splitlines():
        if not line.strip():
            continue
        key, _, value = line.partition("\t")
        ui_rows.append((key, value, json.dumps(tokens_of(value), ensure_ascii=False), GAME_VERSION))
    con.executemany("INSERT OR REPLACE INTO interface_strings (key, source, tokens_json, game_version)"
                    " VALUES (?,?,?,?)", ui_rows)
    con.commit()
    return con, db_path


def coverage_report(con):
    q = con.execute
    report = {"game_version": GAME_VERSION, "by_plugin": {}, "totals": {}}
    for plugin, kind, n, nonempty, words in q(
            "SELECT plugin, kind, COUNT(*), SUM(eligibility!='EMPTY'), SUM(word_count) FROM source_strings"
            " GROUP BY plugin, kind ORDER BY plugin, kind"):
        report["by_plugin"].setdefault(plugin, {})[kind] = {"entries": n, "non_empty": nonempty, "words": words}
    t = report["totals"]
    t["entries"], t["non_empty"], t["words"] = q(
        "SELECT COUNT(*), SUM(eligibility!='EMPTY'), SUM(word_count) FROM source_strings").fetchone()
    t["unique_texts"] = q("SELECT COUNT(DISTINCT source_sha1) FROM source_strings WHERE eligibility!='EMPTY'").fetchone()[0]
    t["texts_repeated_more_than_once"] = q(
        "SELECT COUNT(*) FROM (SELECT source_sha1 FROM source_strings WHERE eligibility!='EMPTY'"
        " GROUP BY source_sha1 HAVING COUNT(*)>1)").fetchone()[0]
    t["entries_with_tokens"] = q("SELECT COUNT(*) FROM source_strings WHERE tokens_json!='[]'").fetchone()[0]
    t["interface_keys"] = q("SELECT COUNT(*) FROM interface_strings").fetchone()[0]
    t["translated"] = q("SELECT COUNT(*) FROM translations").fetchone()[0]
    t["accepted"] = q("SELECT COUNT(*) FROM translations WHERE status='ACCEPTED'").fetchone()[0]

    token_counts = collections.Counter()
    for (tj,) in q("SELECT tokens_json FROM source_strings WHERE tokens_json!='[]'"):
        for tok in json.loads(tj):
            token_counts[re.sub(r"[=\s].*", "", tok)[:24]] += 1
    report["token_types"] = dict(token_counts.most_common(40))
    report["most_repeated"] = [
        {"text": s, "count": c} for s, c in q(
            "SELECT source, COUNT(*) c FROM source_strings WHERE eligibility!='EMPTY'"
            " GROUP BY source_sha1 ORDER BY c DESC LIMIT 25")]
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    args = ap.parse_args()
    con, db_path = build(args.project)
    report = coverage_report(con)
    out = os.path.join(args.project, "08_qa", "reports", "coverage_baseline.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1, ensure_ascii=False)
    print(json.dumps(report["totals"], indent=1))
    print(f"db: {db_path}\nreport: {out}")


if __name__ == "__main__":
    main()
