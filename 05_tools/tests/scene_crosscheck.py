"""Cross-check parsed SCEN records (quest, dialogue actions: actor alias + topic) against an xDump text dump.

Usage:
    python -I scene_crosscheck.py --project <root> --dump <xdump_scen.txt> --plugin hearthfires \
        --load-order Skyrim.esm,Update.esm,HearthFires.esm
"""
import argparse
import json
import os
import re
import sqlite3
import sys

HEADER_RX = re.compile(r"^\s*Record Header \[S\]: \[v\d+\] (\w{4}) - .*?\[([0-9A-F]{8})\]")
QUEST_RX = re.compile(r"^\s*PNAM - Quest: QUST - Quest \[([0-9A-F]{8})\]")
ACTION_RX = re.compile(r"^\s*Action #\d+ \[S\]:")
TYPE_RX = re.compile(r"^\s*ANAM - Type: (\w+)")
ALID_RX = re.compile(r"^\s*ALID - Actor ID: (-?\d+)")
TOPIC_RX = re.compile(r"^\s*DATA - Topic: DIAL - Dialog Topic \[([0-9A-F]{8})\]")


def key(fid_hex, load_order):
    fid = int(fid_hex, 16)
    return f"{load_order[fid >> 24]}:{fid & 0xFFFFFF:06X}"


def parse_dump(path, load_order):
    scenes, cur, action = {}, None, None
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = HEADER_RX.match(line)
            if m:
                cur = scenes.setdefault(key(m.group(2), load_order), {"quest": None, "dialogue": []}) \
                    if m.group(1) == "SCEN" else None
                action = None
                continue
            if cur is None:
                continue
            if ACTION_RX.match(line):
                action = {"type": None, "alias": None, "topic": None}
                continue
            m = QUEST_RX.match(line)
            if m:
                cur["quest"] = key(m.group(1), load_order)
                action = None
                continue
            if action is None:
                continue
            m = TYPE_RX.match(line)
            if m:
                action["type"] = m.group(1)
                if m.group(1) == "Dialogue":
                    cur["dialogue"].append(action)
                continue
            m = ALID_RX.match(line)
            if m and action["alias"] is None:
                action["alias"] = int(m.group(1))
                continue
            m = TOPIC_RX.match(line)
            if m:
                action["topic"] = key(m.group(1), load_order)
    return scenes


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    ap.add_argument("--dump", required=True)
    ap.add_argument("--plugin", required=True)
    ap.add_argument("--load-order", required=True)
    args = ap.parse_args()
    con = sqlite3.connect(os.path.join(args.project, "03_translation", "db", "l10n.sqlite"))
    ours = {}
    for form_key, quest, actions in con.execute(
            "SELECT form_key, quest_key, actions_json FROM scenes WHERE plugin=?", (args.plugin,)):
        ours[form_key] = {"quest": quest,
                          "dialogue": [(a["alias"], a["topic"]) for a in json.loads(actions) if a["type"] == 0]}
    dump = parse_dump(args.dump, args.load_order.split(","))
    stats = {"scenes_in_dump": len(dump), "dialogue_actions_in_dump": sum(len(s["dialogue"]) for s in dump.values()),
             "missing_in_ours": 0, "quest_mismatch": 0, "dialogue_mismatch": 0}
    examples = []
    for k, d in dump.items():
        o = ours.get(k)
        if o is None:
            stats["missing_in_ours"] += 1
            continue
        if d["quest"] != o["quest"]:
            stats["quest_mismatch"] += 1
            examples.append(("quest", k, d["quest"], o["quest"]))
        dd = [(a["alias"], a["topic"]) for a in d["dialogue"]]
        if dd != o["dialogue"]:
            stats["dialogue_mismatch"] += 1
            examples.append(("dialogue", k, dd[:4], o["dialogue"][:4]))
    print(json.dumps(stats, indent=1))
    for e in examples[:10]:
        print("  ", e)
    sys.exit(0 if not (stats["missing_in_ours"] or stats["quest_mismatch"] or stats["dialogue_mismatch"]) else 1)


if __name__ == "__main__":
    main()
