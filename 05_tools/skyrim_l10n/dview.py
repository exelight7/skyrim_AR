"""Context view for dialogue batches: for each row show quest, addressee/speaker with gender, and
the NPC reply (for topics/player choices) so the Arabic can agree in gender and register.

Usage: python -I dview.py --batch-dir DIR A B [--maxlen 300]
Output: <n>\t<quest>\t<who:M|F|?>\t<reply or prev>\t<source>   (all escaped, one line per row)
"""
import argparse
import json
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))


def esc(s):
    return (s or "").replace("\\", "\\\\").replace("\r", "").replace("\n", "\n").replace("\t", " ")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch-dir", required=True)
    ap.add_argument("a", type=int)
    ap.add_argument("b", type=int)
    ap.add_argument("--maxlen", type=int, default=160)
    args = ap.parse_args()
    con = sqlite3.connect(os.path.join(PROJECT, "03_translation", "db", "l10n.sqlite"))
    text = dict(con.execute("SELECT key, source FROM source_strings"))
    names = {}
    for fk, nk, fem in con.execute("SELECT form_key, name_key, female FROM speakers"):
        names[fk] = (text.get(nk) or fk, "F" if fem else "M")
    qname = dict(con.execute("SELECT form_key, editor_id FROM quests"))
    pc_sex = {}  # response key -> "M"/"F" when the INFO is conditioned on the player's sex
    for resp_json, cond_json in con.execute("SELECT response_keys_json, conditions_json FROM infos"):
        sex = None
        for c in json.loads(cond_json or "[]"):
            f, run = c.get("func"), c.get("run_on")
            if f == "GetPCIsSex" or (f == "GetIsSex" and run in ("Target", "CombatTarget")):
                if c.get("op") == "==":
                    sex = "F" if c.get("value") == 1.0 else "M"
        if sex:
            for k in json.loads(resp_json or "[]"):
                pc_sex[k] = sex
    rows = [json.loads(x) for x in open(os.path.join(args.batch_dir, "input.jsonl"), encoding="utf-8")]
    for i in range(args.a, min(args.b, len(rows))):
        r = rows[i]
        uid, cat = r["uid"], r["category"]
        quest, who, ctx = r.get("quest", ""), "", ""
        if cat == "dialogue_topic":
            t = con.execute("SELECT form_key, quest_key FROM topics WHERE prompt_key=?", (uid,)).fetchone()
            if t:
                quest = qname.get(t[1], "")
                inf = con.execute("SELECT speaker_key, response_keys_json FROM infos WHERE topic_key=? ORDER BY seq LIMIT 1", (t[0],)).fetchone()
                if inf:
                    sp = names.get(inf[0])
                    who = f"{sp[0]}:{sp[1]}" if sp else ""
                    resp = json.loads(inf[1] or "[]")
                    ctx = text.get(resp[0], "") if resp else ""
        elif cat == "player_choice":
            inf = con.execute("SELECT speaker_key, response_keys_json FROM infos WHERE prompt_key=? LIMIT 1", (uid,)).fetchone()
            if inf:
                sp = names.get(inf[0])
                who = f"{sp[0]}:{sp[1]}" if sp else ""
                resp = json.loads(inf[1] or "[]")
                ctx = text.get(resp[0], "") if resp else ""
            if not who and r.get("speaker"):
                who = r["speaker"]
        else:
            sk = con.execute("SELECT speaker FROM source_strings WHERE key=?", (uid,)).fetchone()
            sp = names.get(sk[0]) if sk and sk[0] else None
            who = f"{sp[0]}:{sp[1]}" if sp else r.get("speaker", "")
            if uid in pc_sex:
                who += f" PC:{pc_sex[uid]}"
        print(f"{i}\t{quest}\t{who}\t{esc(ctx)[:args.maxlen]}\t{esc(r['source'])}")
    print(f"# total {len(rows)}")


if __name__ == "__main__":
    main()
