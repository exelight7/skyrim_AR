"""Batch export/import of translations with translation-memory propagation and QA gating.

Identical source text in the same category is translated once and applied to every key that uses it
(the category keeps e.g. a "Mine" activation prompt apart from other uses of the same word).

Usage:
    python -I translations.py export --project . --batch B001 --ui
    python -I translations.py export --project . --batch B002 --category game_setting_text [--limit 400]
    python -I translations.py import --project . --batch B001          # reads batches/B001/ar.tsv
    python -I translations.py stats  --project .

Draft file format (ar.tsv, UTF-8): "<uid>\t<arabic>" per line; write line breaks inside a string as \\n.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skyrim_l10n import qa  # noqa: E402


def db(project):
    con = sqlite3.connect(os.path.join(project, "03_translation", "db", "l10n.sqlite"))
    con.execute("CREATE INDEX IF NOT EXISTS ix_src_cat ON source_strings(source_sha1, category)")
    return con


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


NAME_CATEGORIES = ("npc_name", "location_name", "map_marker", "region_name", "faction_name", "quest_name")


def approved_names(con, min_len=4):
    """English proper name -> Arabic, from accepted name translations (only unambiguous ones)."""
    seen, weak = {}, set()
    for src, tgt, cat in con.execute(
            f"""SELECT s.source, t.target, s.category FROM translations t JOIN source_strings s ON s.key=t.key
                WHERE t.status='ACCEPTED' AND s.category IN ({','.join('?' * len(NAME_CATEGORIES))})""",
            NAME_CATEGORIES):
        src = src.strip()
        if len(src) >= min_len and src[0].isupper():
            seen.setdefault(src, set()).add(tgt.strip())
            # Strict (HIGH) only for places and factions. NPC names are often generic noun phrases whose
            # Arabic form changes with definiteness (حصان دويمري / الحصان الدويمري); quest names are often
            # plain sentences; single words are often ordinary English -> softer MEDIUM check.
            if (cat in ("npc_name", "quest_name") or tgt.strip().startswith("من ")
                    or (" " not in src and cat not in ("location_name", "map_marker", "region_name"))):
                weak.add(src)
    out = {k: next(iter(v)) for k, v in seen.items() if len(v) == 1}
    approved_names.weak = weak
    return out


_NAME_RX_CACHE = {}


def names_in(text, names):
    """Proper names occurring as whole phrases in text (longest match wins; one compiled regex)."""
    import re as _re
    key = id(names)
    rx = _NAME_RX_CACHE.get(key)
    if rx is None:
        alts = "|".join(_re.escape(n) for n in sorted(names, key=len, reverse=True))
        rx = _re.compile(r"(?<![A-Za-z])(?:" + alts + r")(?![A-Za-z])") if alts else None
        _NAME_RX_CACHE[key] = rx
    if rx is None:
        return []
    out = []
    for m in rx.finditer(text):
        if m.group(0) not in out:
            out.append(m.group(0))
    return out


def load_glossary(project, con=None):
    path = os.path.join(project, "03_translation", "glossary.json")
    g = None
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            g = json.load(f)
    if con is not None:
        g = g or {"terms": {}}
        g["names"] = approved_names(con)
    return g


def esc(s):
    return s.replace("\\", "\\\\").replace("\t", "\\t").replace("\r", "").replace("\n", "\\n")


def unesc(s):
    out, i = [], 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            out.append({"n": "\n", "t": "\t", "\\": "\\"}.get(s[i + 1], s[i + 1]))
            i += 2
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def speaker_names(con):
    names = {}
    for fk, nk in con.execute("SELECT form_key, name_key FROM speakers WHERE name_key IS NOT NULL"):
        names[fk] = nk
    text = dict(con.execute("SELECT key, source FROM source_strings WHERE kind='strings'"))
    return {fk: text.get(nk) for fk, nk in names.items()}


def export(args):
    con = db(args.project)
    bdir = os.path.join(args.project, "03_translation", "batches", args.batch)
    os.makedirs(bdir, exist_ok=True)
    rows = []
    if args.ui:
        done = {k[3:] for (k,) in con.execute("SELECT key FROM translations WHERE key LIKE 'ui|%'")}
        for key, source in con.execute("SELECT key, source FROM interface_strings ORDER BY key"):
            if key not in done and source.strip():
                rows.append({"uid": f"ui|{key}", "n": 1, "category": "interface", "source": source})
    else:
        where = ["s.eligibility='PLAYER_VISIBLE'",
                 "NOT EXISTS (SELECT 1 FROM translations t WHERE t.key=s.key)"]
        params = []
        if args.category:
            where.append(f"s.category IN ({','.join('?' * len(args.category))})")
            params += args.category
        if args.plugin:
            where.append("s.plugin=?")
            params.append(args.plugin)
        if args.quest:
            where.append(f"s.quest_edid IN ({','.join('?' * len(args.quest))})")
            params += args.quest
        names = speaker_names(con) if not args.category or "dialogue_line" in args.category else {}
        sql = (f"SELECT MIN(s.key), COUNT(*), s.category, s.source, MIN(s.quest_edid), MIN(s.speaker),"
               f" MIN(s.speaker_alias) FROM source_strings s WHERE {' AND '.join(where)}"
               f" GROUP BY s.source_sha1, s.category ORDER BY MIN(s.quest_edid), MIN(s.key)")
        for uid, n, cat, source, quest, speaker, alias in con.execute(sql, params):
            r = {"uid": uid, "n": n, "category": cat, "source": source}
            if quest:
                r["quest"] = quest
            sp = names.get(speaker) if speaker else None
            if sp or alias or speaker:
                r["speaker"] = sp or alias or speaker
            rows.append(r)
            if args.limit and len(rows) >= args.limit:
                break
    if not args.ui and not (args.category and set(args.category) <= set(NAME_CATEGORIES) - {"quest_name"}):
        names = approved_names(con)
        for r in rows:
            hits = names_in(r["source"], names)
            if hits:
                r["names"] = {n: names[n] for n in hits}
    with open(os.path.join(bdir, "input.jsonl"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(os.path.join(bdir, "input.tsv"), "w", encoding="utf-8") as f:
        for r in rows:
            ctx = " ".join(f"{k}={r[k]}" for k in ("category", "quest", "speaker") if k in r)
            if "names" in r:
                ctx += " names=" + ";".join(f"{k}={v}" for k, v in r["names"].items())
            f.write(f"{r['uid']}\t{ctx}\t{esc(r['source'])}\n")
    print(f"{len(rows)} groups covering {sum(r['n'] for r in rows)} strings -> {bdir}")


def import_batch(args):
    con = db(args.project)
    glossary = load_glossary(args.project)
    bdir = os.path.join(args.project, "03_translation", "batches", args.batch)
    with open(os.path.join(bdir, "input.jsonl"), encoding="utf-8") as f:
        inputs = {r["uid"]: r for r in map(json.loads, f)}
    approved = approved_names(con)
    # Documented waivers ("<uid>\t<check_id>\t<reason>"), e.g. a source typo we correct on purpose.
    waivers = {}
    wpath = os.path.join(bdir, "qa_waivers.tsv")
    if os.path.exists(wpath):
        with open(wpath, encoding="utf-8") as f:
            for line in f:
                parts = line.rstrip("\r\n").split("\t")
                if len(parts) >= 3 and parts[2].strip():
                    waivers.setdefault(parts[0], set()).add(parts[1])
    drafts = {}
    with open(os.path.join(bdir, args.file), encoding="utf-8-sig") as f:
        for ln, line in enumerate(f, 1):
            line = line.rstrip("\r\n")
            if not line.strip() or line.startswith("#"):
                continue
            uid, sep, ar = line.partition("\t")
            if not sep:
                print(f"line {ln}: no tab")
                continue
            # Keys and values may carry meaningful leading/trailing spaces (runtime concatenation).
            drafts[uid] = unesc(ar)
    accepted = rejected = keys_written = 0
    report = []
    ts = now()
    for uid, target in drafts.items():
        inp = inputs.get(uid)
        if inp is None:
            report.append(f"UNKNOWN uid {uid}")
            rejected += 1
            continue
        source = inp["source"]
        findings = qa.check(source, target, inp["category"], in_translate_file=uid.startswith("ui|"),
                            glossary=glossary)
        # Approved proper names must appear in their approved Arabic form (HIGH: name consistency).
        if inp["category"] not in NAME_CATEGORIES:
            for en in names_in(source, approved):
                ar = qa.HARAKAT.sub("", approved[en])
                bare_target = qa.HARAKAT.sub("", target)
                # Construct state (إضافة) drops the article: المعبد -> معبد ميراك.
                forms = [ar] + ([ar[2:]] if ar.startswith("ال") else [])
                if not any(f in bare_target for f in forms):
                    sev = "MEDIUM" if en in approved_names.weak else "HIGH"
                    findings.append((sev, "name_form", f"'{en}' must be written '{ar}'"))
        if uid in waivers:
            findings = [(("WAIVED" if c in waivers[uid] else sev), c, m) for sev, c, m in findings]
        status = "REJECTED" if qa.blocking(findings) else "ACCEPTED"
        if uid.startswith("ui|"):
            keys = [uid]
            sha = hashlib.sha1(source.encode("utf-8")).hexdigest()
        else:
            sha = con.execute("SELECT source_sha1 FROM source_strings WHERE key=?", (uid,)).fetchone()[0]
            keys = [k for (k,) in con.execute("SELECT key FROM source_strings WHERE source_sha1=? AND category=?",
                                               (sha, inp["category"]))]
        con.execute("DELETE FROM qa_results WHERE key=?", (uid,))
        for sev, cid, msg in findings:
            con.execute("INSERT INTO qa_results VALUES (?,?,?,?,?,0,?)", (uid, args.batch, cid, sev, msg, ts))
        if status == "ACCEPTED":
            accepted += 1
            for k in keys:
                con.execute("INSERT OR REPLACE INTO translations VALUES (?,?,?,?,?,?)",
                            (k, target, status, args.batch, sha, ts))
            keys_written += len(keys)
        else:
            rejected += 1
            report.append(f"REJECTED {uid}: " + "; ".join(f"{s}:{c}:{m}" for s, c, m in findings
                                                          if s in ("CRITICAL", "HIGH")))
        for sev, cid, msg in findings:
            if sev in ("MEDIUM",) and status == "ACCEPTED":
                report.append(f"warn {uid}: {cid}: {msg}")
    missing = [u for u in inputs if u not in drafts]
    con.commit()
    with open(os.path.join(bdir, "import_report.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(report))
    print(f"accepted {accepted} groups ({keys_written} strings), rejected {rejected}, "
          f"missing {len(missing)} of {len(inputs)}")
    for line in report[:40]:
        print("  ", line)


def apply_names(args):
    """Turn per-source translations (names_*.tsv: '<English>\\t<Arabic|SKIP>') into ar.tsv for the batch.

    One English source -> one Arabic form everywhere in the batch, which keeps names consistent across
    categories (e.g. a location name, its map marker and its region). SKIP marks internal editor/test
    names as DO_NOT_TRANSLATE (persisted in eligibility_overrides).
    """
    import glob as _glob
    con = db(args.project)
    bdir = os.path.join(args.project, "03_translation", "batches", args.batch)
    mapping = {}
    for path in sorted(_glob.glob(os.path.join(bdir, "names_*.tsv"))):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\r\n")
                if not line.strip():
                    continue
                en, _sep, ar = line.partition("\t")
                # Same escaping as ar.tsv (\n, \t, \\), so multi-line descriptions fit on one line.
                en, ar = unesc(en), unesc(ar)
                if en in mapping and mapping[en] != ar:
                    print(f"CONFLICT {en!r}: {mapping[en]!r} vs {ar!r}")
                mapping[en] = ar
    with open(os.path.join(bdir, "input.jsonl"), encoding="utf-8") as f:
        inputs = [json.loads(x) for x in f]
    out, skipped, missing = [], [], []
    for r in inputs:
        ar = mapping.get(r["source"].strip())
        if ar is None:
            missing.append(r["source"])
        elif ar == "SKIP":
            skipped.append(r["uid"])
        else:
            out.append(f"{r['uid']}\t{esc(ar)}")
    with open(os.path.join(bdir, "ar.tsv"), "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    ts = now()
    con.execute("CREATE TABLE IF NOT EXISTS eligibility_overrides (key TEXT PRIMARY KEY, eligibility TEXT NOT NULL,"
                " reason TEXT, decided_utc TEXT)")
    for uid in skipped:
        sha, cat = con.execute("SELECT source_sha1, category FROM source_strings WHERE key=?", (uid,)).fetchone()
        for (k,) in con.execute("SELECT key FROM source_strings WHERE source_sha1=? AND category=?", (sha, cat)).fetchall():
            con.execute("INSERT OR REPLACE INTO eligibility_overrides VALUES (?,?,?,?)",
                        (k, "DO_NOT_TRANSLATE", f"internal editor/test name ({args.batch})", ts))
            con.execute("UPDATE source_strings SET eligibility='DO_NOT_TRANSLATE' WHERE key=?", (k,))
    con.commit()
    print(f"{len(out)} rows -> ar.tsv, {len(skipped)} groups marked DO_NOT_TRANSLATE, {len(missing)} unmapped")
    for m in missing[:20]:
        print("   unmapped:", m)


def tm_fill(args):
    """Apply accepted translations to untranslated keys with identical source text and category."""
    con = db(args.project)
    tm = {}
    for sha, cat, target, batch in con.execute(
            """SELECT s.source_sha1, s.category, t.target, t.batch_id FROM translations t
               JOIN source_strings s ON s.key=t.key WHERE t.status='ACCEPTED'"""):
        tm.setdefault((sha, cat), (target, batch))
    todo = con.execute("""SELECT s.key, s.source_sha1, s.category FROM source_strings s
                          WHERE s.eligibility='PLAYER_VISIBLE'
                          AND NOT EXISTS (SELECT 1 FROM translations t WHERE t.key=s.key)""").fetchall()
    ts = now()
    rows = [(k, tm[(sha, cat)][0], "ACCEPTED", f"TM:{tm[(sha, cat)][1]}", sha, ts)
            for k, sha, cat in todo if (sha, cat) in tm]
    con.executemany("INSERT INTO translations VALUES (?,?,?,?,?,?)", rows)
    con.commit()
    print(f"translation memory filled {len(rows)} strings")


def stats(args):
    con = db(args.project)
    total = con.execute("SELECT COUNT(*) FROM source_strings WHERE eligibility='PLAYER_VISIBLE'").fetchone()[0]
    done = con.execute("SELECT COUNT(*) FROM translations t JOIN source_strings s ON s.key=t.key"
                       " WHERE t.status='ACCEPTED' AND s.eligibility='PLAYER_VISIBLE'").fetchone()[0]
    ui_total = con.execute("SELECT COUNT(*) FROM interface_strings WHERE trim(source)!=''").fetchone()[0]
    ui_done = con.execute("SELECT COUNT(*) FROM translations WHERE key LIKE 'ui|%' AND status='ACCEPTED'").fetchone()[0]
    words = con.execute("SELECT COALESCE(SUM(s.word_count),0) FROM translations t JOIN source_strings s ON s.key=t.key"
                        " WHERE t.status='ACCEPTED'").fetchone()[0]
    print(json.dumps({"strings_accepted": done, "strings_total": total, "pct": round(100 * done / total, 2),
                      "ui_accepted": ui_done, "ui_total": ui_total, "words_accepted": words}, indent=1))
    by_cat = con.execute("""SELECT s.category, COUNT(*), SUM(t.key IS NOT NULL) FROM source_strings s
                            LEFT JOIN translations t ON t.key=s.key AND t.status='ACCEPTED'
                            WHERE s.eligibility='PLAYER_VISIBLE' GROUP BY 1 ORDER BY 2 DESC""").fetchall()
    for cat, n, d in by_cat[:30]:
        print(f"  {cat:32} {d or 0:>6}/{n:<6}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")   # -I ignores PYTHONIOENCODING; Arabic must print on Windows
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--project", required=True)
    e.add_argument("--batch", required=True)
    e.add_argument("--ui", action="store_true")
    e.add_argument("--category", nargs="*")
    e.add_argument("--plugin")
    e.add_argument("--quest", nargs="*")
    e.add_argument("--limit", type=int)
    i = sub.add_parser("import")
    i.add_argument("--project", required=True)
    i.add_argument("--batch", required=True)
    i.add_argument("--file", default="ar.tsv")
    s = sub.add_parser("stats")
    s.add_argument("--project", required=True)
    f = sub.add_parser("tm-fill")
    f.add_argument("--project", required=True)
    n = sub.add_parser("apply-names")
    n.add_argument("--project", required=True)
    n.add_argument("--batch", required=True)
    args = ap.parse_args()
    {"export": export, "import": import_batch, "stats": stats, "tm-fill": tm_fill,
     "apply-names": apply_names}[args.cmd](args)


if __name__ == "__main__":
    main()
