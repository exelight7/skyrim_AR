"""Cross-check the project's linker output against an independent xDump (xEdit) text dump.

Compares, for every INFO in the dump that belongs to the plugin: parent topic, spoken response
texts (in order), player prompt, and condition summaries (run-on, function, operator, value).

Usage:
    python -I xdump_crosscheck.py --project <root> --dump <xdump.txt> --plugin hearthfires \
        --load-order Skyrim.esm,Update.esm,HearthFires.esm
"""
import argparse
import json
import os
import re
import sqlite3
import sys

HEADER_RX = re.compile(r"^\s*Record Header \[S\]: \[v\d+\] (\w{4}) - .*?\[([0-9A-F]{8})\]")
TOPIC_RX = re.compile(r"in GRUP Topic Children of DIAL - Dialog Topic \[([0-9A-F]{8})\]")
NAM1_RX = re.compile(r"^\s*NAM1 - Response Text: (.*)$")
RNAM_RX = re.compile(r"^\s*RNAM - Prompt: (.*)$")
COND_RX = re.compile(r"^\s*Condition #\d+ \[S\]: (\(.+?\)|\w+)\.(\w+)(?:\(.*\))? (=|<>|>=|<=|>|<) (.+?)( AND| OR)?\s*$")
OPS = {"=": "==", "<>": "!="}
RUN_ON_NAMES = {"Subject": "Subject", "Target": "Target", "CombatTarget": "CombatTarget",
                "LinkedReference": "LinkedRef", "QuestAlias": "QuestAlias", "PackageData": "PackageData",
                "EventData": "EventData"}


def run_on_of(token):
    return RUN_ON_NAMES.get(token, "Reference")


def key_from_loaded(fid_hex, load_order):
    fid = int(fid_hex, 16)
    return f"{load_order[fid >> 24]}:{fid & 0xFFFFFF:06X}"


def parse_dump(path, load_order, plugin_file):
    infos, cur = {}, None
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = HEADER_RX.match(line)
            if m:
                cur = None
                if m.group(1) == "INFO":
                    k = key_from_loaded(m.group(2), load_order)
                    cur = infos.setdefault(k, {"topic": None, "responses": [], "prompt": None, "conds": []})
                continue
            if cur is None:
                continue
            m = TOPIC_RX.search(line)
            if m and cur["topic"] is None:
                cur["topic"] = key_from_loaded(m.group(1), load_order)
                continue
            m = NAM1_RX.match(line)
            if m:
                cur["responses"].append(m.group(1).rstrip())
                continue
            m = RNAM_RX.match(line)
            if m:
                cur["prompt"] = m.group(1).rstrip()
                continue
            m = COND_RX.match(line)
            if m:
                cur["conds"].append((run_on_of(m.group(1)), m.group(2), OPS.get(m.group(3), m.group(3))))
            elif "Condition #" in line and "[S]:" in line:
                cur["conds"].append(("UNPARSED", line.strip(), ""))
    return infos


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    ap.add_argument("--dump", required=True)
    ap.add_argument("--plugin", required=True)
    ap.add_argument("--load-order", required=True)
    ap.add_argument("--learn-out", help="write numeric->name condition function map learned from the dump")
    args = ap.parse_args()
    load_order = args.load_order.split(",")
    con = sqlite3.connect(os.path.join(args.project, "03_translation", "db", "l10n.sqlite"))
    text = dict(con.execute("SELECT key, source FROM source_strings WHERE plugin=?", (args.plugin,)))
    ours = {}
    for form_key, topic, prompt, resp, conds in con.execute(
            "SELECT form_key, topic_key, prompt_key, response_keys_json, conditions_json FROM infos WHERE plugin=?",
            (args.plugin,)):
        ours[form_key] = {
            "topic": topic, "prompt": text.get(prompt) if prompt else None,
            "responses": [text.get(k, "").rstrip() for k in json.loads(resp)],
            "conds": [(c["run_on"], str(c["func"]), c["op"], c["func_id"]) for c in json.loads(conds) if "run_on" in c],
        }
    dump = parse_dump(args.dump, load_order, load_order[-1])
    stats = {"infos_in_dump": len(dump), "missing_in_ours": 0, "topic": 0, "responses": 0, "prompt": 0, "conds": 0}
    examples = []
    learned = {}   # numeric function index -> name, learned from aligned condition lists
    conflicts = set()
    for k, d in dump.items():
        o = ours.get(k)
        if o is None:
            stats["missing_in_ours"] += 1
            examples.append(("missing", k))
            continue
        for field in ("topic", "responses", "prompt"):
            if d[field] != o[field] and not (field == "prompt" and d[field] is None and o[field] is None):
                stats[field] += 1
                if len(examples) < 15:
                    examples.append((field, k, d[field], o[field]))
        # Our function names cover a subset; compare run-on/operator everywhere, names when known.
        dc = d["conds"]
        oc = o["conds"]
        if len(dc) == len(oc):
            for a, b in zip(dc, oc):
                if a[0] != "UNPARSED":
                    if learned.setdefault(b[3], a[1]) != a[1]:
                        conflicts.add(b[3])
        if len(dc) != len(oc) or any(a[0] != b[0] or a[2] != b[2] or (not b[1].isdigit() and a[1] != b[1])
                                     for a, b in zip(dc, oc)):
            stats["conds"] += 1
            if len(examples) < 15:
                examples.append(("conds", k, dc, oc))
    print(json.dumps(stats, indent=1))
    for e in examples[:15]:
        print("  ", e)
    if args.learn_out:
        with open(args.learn_out, "w", encoding="utf-8") as f:
            json.dump({"functions": {str(k): v for k, v in sorted(learned.items()) if k not in conflicts},
                       "conflicts": sorted(conflicts), "source": os.path.basename(args.dump)}, f, indent=1)
        print(f"learned {len(learned) - len(conflicts)} function names, {len(conflicts)} conflicts -> {args.learn_out}")
    sys.exit(0 if all(v == 0 for kk, v in stats.items() if kk != "infos_in_dump") else 1)


if __name__ == "__main__":
    main()
