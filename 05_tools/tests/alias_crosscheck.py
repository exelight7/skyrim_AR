"""Cross-check quest aliases (id, name, unique actor, forced reference) against an xDump QUST dump.

Usage:
    python -I alias_crosscheck.py --project <root> --dump <xdump.txt> --plugin hearthfires \
        --load-order Skyrim.esm,Update.esm,HearthFires.esm
"""
import argparse
import json
import os
import re
import sqlite3
import sys

HEADER_RX = re.compile(r"^\s*Record Header \[S\]: \[v\d+\] (\w{4}) - .*?\[([0-9A-F]{8})\]")
ID_RX = re.compile(r"^\s*AL(?:ST|LS) - (?:Reference|Location) Alias ID: (\d+)")
NAME_RX = re.compile(r"^\s*ALID - Alias Name: (.*)$")
UA_RX = re.compile(r"^\s*ALUA - Unique Actor: .*?\[([0-9A-F]{8})\]")
FR_RX = re.compile(r"^\s*ALFR - Forced Reference: .*?\[([0-9A-F]{8})\]")


def key(fid_hex, lo):
    fid = int(fid_hex, 16)
    return f"{lo[fid >> 24]}:{fid & 0xFFFFFF:06X}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    ap.add_argument("--dump", required=True)
    ap.add_argument("--plugin", required=True)
    ap.add_argument("--load-order", required=True)
    args = ap.parse_args()
    lo = args.load_order.split(",")
    dump, cur = {}, None
    with open(args.dump, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = HEADER_RX.match(line)
            if m:
                cur = dump.setdefault(key(m.group(2), lo), []) if m.group(1) == "QUST" else None
                continue
            if cur is None:
                continue
            if (m := ID_RX.match(line)):
                cur.append({"id": int(m.group(1)), "name": None})
            elif cur and (m := NAME_RX.match(line)):
                cur[-1]["name"] = m.group(1).rstrip()
            elif cur and (m := UA_RX.match(line)):
                cur[-1]["unique_actor"] = key(m.group(1), lo)
            elif cur and (m := FR_RX.match(line)):
                cur[-1]["forced_ref"] = key(m.group(1), lo)
    con = sqlite3.connect(os.path.join(args.project, "03_translation", "db", "l10n.sqlite"))
    ours = {k: json.loads(a) for k, a in con.execute(
        "SELECT form_key, aliases_json FROM quests WHERE plugin=?", (args.plugin,))}
    stats = {"quests": len(dump), "aliases": sum(len(v) for v in dump.values()), "mismatched_quests": 0}
    for k, d in dump.items():
        if d != ours.get(k):
            stats["mismatched_quests"] += 1
            if stats["mismatched_quests"] <= 5:
                print("  mismatch", k, d[:3], (ours.get(k) or [])[:3])
    print(json.dumps(stats, indent=1))
    sys.exit(1 if stats["mismatched_quests"] else 0)


if __name__ == "__main__":
    main()
