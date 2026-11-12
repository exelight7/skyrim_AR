"""Record a SHA-256 baseline of every file in the game directory (read-only).

Usage:
    python -I baseline.py --game-dir <dir> --out <hashes.json> [--verify <hashes.json>]
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import sys

CHUNK = 8 * 1024 * 1024


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(CHUNK)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def scan(game_dir):
    result = {}
    for root, _dirs, files in os.walk(game_dir):
        for name in sorted(files):
            full = os.path.join(root, name)
            rel = os.path.relpath(full, game_dir).replace("\\", "/")
            st = os.stat(full)
            result[rel] = {"size": st.st_size, "mtime": int(st.st_mtime), "sha256": sha256_file(full)}
            print(f"hashed {rel}", file=sys.stderr, flush=True)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game-dir", required=True)
    ap.add_argument("--out")
    ap.add_argument("--verify", help="compare current state against an existing baseline file")
    args = ap.parse_args()

    current = scan(args.game_dir)
    if args.verify:
        with open(args.verify, encoding="utf-8") as f:
            base = json.load(f)["files"]
        changed = [k for k in base if k in current and base[k]["sha256"] != current[k]["sha256"]]
        missing = [k for k in base if k not in current]
        added = [k for k in current if k not in base]
        print(json.dumps({"changed": changed, "missing": missing, "added": added}, indent=2))
        sys.exit(1 if (changed or missing or added) else 0)

    doc = {
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "game_dir": args.game_dir,
        "file_count": len(current),
        "total_bytes": sum(v["size"] for v in current.values()),
        "files": current,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, sort_keys=True)
    print(f"wrote {args.out}: {len(current)} files")


if __name__ == "__main__":
    main()
