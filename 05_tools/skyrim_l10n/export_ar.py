"""Export accepted Arabic translations (no English source text) to 03_translation/ar/.

One TSV per plugin: "key<TAB>arabic", with \\, \\t and \\n escaped.
UI keys (translate_english.txt) are stored under the "ui" prefix and go to ui.tsv.

Usage: python -I export_ar.py --project <project root>
"""
import argparse
import collections
import os
import sqlite3


def esc(s):
    return s.replace("\\", "\\\\").replace("\t", "\\t").replace("\r", "").replace("\n", "\\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    a = ap.parse_args()
    db = sqlite3.connect(os.path.join(a.project, "03_translation", "db", "l10n.sqlite"))
    out = os.path.join(a.project, "03_translation", "ar")
    os.makedirs(out, exist_ok=True)
    by = collections.defaultdict(list)
    for k, t in db.execute("select key, target from translations where status='ACCEPTED' order by key"):
        by[k.split("|")[0]].append((k, t))
    for plugin, rows in by.items():
        with open(os.path.join(out, plugin + ".tsv"), "w", encoding="utf-8", newline="\n") as f:
            f.write("key\tarabic\n")
            for k, t in rows:
                f.write(f"{k}\t{esc(t)}\n")
    print(f"{sum(map(len, by.values()))} strings in {len(by)} plugin files")


if __name__ == "__main__":
    main()
