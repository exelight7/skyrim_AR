"""Mark record names the engine never displays as LIKELY_HIDDEN, using the records' own UI flags.

  MGEF  DATA flags & 0x00008000 ("Hide in UI")  -> FULL is never shown in the Active Effects list
  PERK  DATA playable == 0 or hidden == 1       -> FULL is never shown in the perk trees

The decision is stored in eligibility_overrides, so it survives re-linking (link.py re-applies overrides).
A string is only marked hidden when EVERY record that uses it is hidden; a name shared with a visible
record stays PLAYER_VISIBLE.

Usage: python -I visibility_flags.py --project <root> [--game-dir <dir>]
"""
import argparse
import datetime
import os
import sqlite3
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from skyrim_l10n import GAME_DIR_DEFAULT, PLUGIN_FILES  # noqa: E402
from skyrim_l10n.esm import Plugin  # noqa: E402

MGEF_HIDE_IN_UI = 0x00008000


def hidden_records(game_dir):
    hidden, visible = set(), set()
    for _prefix, fname in PLUGIN_FILES.items():
        path = os.path.join(game_dir, "Data", fname)
        if not os.path.exists(path):
            continue
        plugin = Plugin(path)
        try:
            for rec in plugin.records({"MGEF", "PERK"}):
                fk = plugin.form_key(rec.form_id, fname)
                for sub, pay in rec.subrecords():
                    if sub != "DATA":
                        continue
                    if rec.type == "MGEF" and len(pay) >= 4:
                        hide = bool(struct.unpack_from("<I", pay, 0)[0] & MGEF_HIDE_IN_UI)
                    elif rec.type == "PERK" and len(pay) >= 5:
                        hide = pay[3] == 0 or pay[4] == 1
                    else:
                        continue
                    (hidden if hide else visible).add(fk)
                    break
        finally:
            plugin.close()
    # A later plugin overriding a record decides its final state.
    return hidden - visible, visible


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    ap.add_argument("--game-dir", default=GAME_DIR_DEFAULT)
    args = ap.parse_args()
    hidden, _visible = hidden_records(args.game_dir)
    con = sqlite3.connect(os.path.join(args.project, "03_translation", "db", "l10n.sqlite"))
    users = {}
    for key, fk, rtype, field in con.execute(
            "SELECT key, form_key, record_type, field FROM string_refs"):
        users.setdefault(key, []).append((fk, rtype, field))
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    marked = 0
    for key, refs in users.items():
        named = [r for r in refs if r[1] in ("MGEF", "PERK") and r[2] == "FULL"]
        if not named or len(named) != len(refs):
            continue
        if all(fk in hidden for fk, _t, _f in named):
            cur = con.execute("SELECT eligibility FROM source_strings WHERE key=?", (key,)).fetchone()
            if cur and cur[0] == "PLAYER_VISIBLE":
                con.execute("INSERT OR REPLACE INTO eligibility_overrides VALUES (?,?,?,?)",
                            (key, "LIKELY_HIDDEN", "MGEF Hide-in-UI / non-playable or hidden PERK", ts))
                con.execute("UPDATE source_strings SET eligibility='LIKELY_HIDDEN' WHERE key=?", (key,))
                marked += 1
    con.commit()
    print(f"hidden records: {len(hidden)}; strings marked LIKELY_HIDDEN: {marked}")


if __name__ == "__main__":
    main()
