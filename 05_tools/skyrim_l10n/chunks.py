"""Helpers for translating long batches in numbered chunks.

view: print rows [a, b) of a batch as "<n>\t[quest|speaker]\t<names hint>\t<source>" (escaped, one line each).
put:  read "<n>\t<Arabic>" lines from a chunk file and append "<uid>\t<Arabic>" to the batch's ar.tsv.

Usage:
    python -I chunks.py view --batch-dir DIR A B
    python -I chunks.py put --batch-dir DIR CHUNK_FILE
"""
import argparse
import json
import os
import sys


def rows(bdir):
    with open(os.path.join(bdir, "input.jsonl"), encoding="utf-8") as f:
        return [json.loads(x) for x in f]


def esc(s):
    return s.replace("\\", "\\\\").replace("\n", "\n").replace("\t", "\t")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["view", "put"])
    ap.add_argument("--batch-dir", required=True)
    ap.add_argument("args", nargs="*")
    a = ap.parse_args()
    rs = rows(a.batch_dir)
    if a.cmd == "view":
        lo, hi = int(a.args[0]), int(a.args[1])
        for i in range(lo, min(hi, len(rs))):
            r = rs[i]
            ctx = "|".join(x for x in (r.get("quest", ""), r.get("speaker", "")) if x)
            names = ";".join(f"{k}={v}" for k, v in r.get("names", {}).items())
            print(f"{i}\t{ctx}\t{names}\t{esc(r['source'])}")
        print(f"# total {len(rs)}")
    else:
        out, bad = [], 0
        with open(a.args[0], encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\r\n")
                if not line.strip():
                    continue
                n, sep, ar = line.partition("\t")
                if not sep or not n.strip().isdigit() or int(n) >= len(rs):
                    bad += 1
                    print("bad line:", line[:80])
                    continue
                out.append(f"{rs[int(n)]['uid']}\t{ar}")
        with open(os.path.join(a.batch_dir, "ar.tsv"), "a", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")
        print(f"appended {len(out)} rows, {bad} bad")


if __name__ == "__main__":
    main()
