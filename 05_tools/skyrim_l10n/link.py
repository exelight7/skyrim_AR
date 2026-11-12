"""Link every localized string ID to the record/field that uses it, and build dialogue/quest context.

Reads plugins from the game Data folder (read-only) and writes context tables into the project DB.

Usage:
    python -I link.py --project <project_root> [--game-dir <dir>] [--plugins skyrim,update,...]
"""
import argparse
import collections
import json
import os
import sqlite3
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skyrim_l10n import GAME_DIR_DEFAULT, GAME_VERSION, PLUGIN_FILES, PLUGIN_SOURCES  # noqa: E402
from skyrim_l10n.esm import Plugin  # noqa: E402


# Localized (lstring) subrecords. "*" = any record type. Small sequential string IDs collide with
# ordinary 4-byte fields, so only these known text fields are trusted.
LSTRING_FIELDS = {
    "*": {"FULL", "DESC"},
    "INFO": {"NAM1", "RNAM"},
    "QUST": {"CNAM", "NNAM"},
    "BOOK": {"CNAM"},
    "NPC_": {"SHRT"},
    "MESG": {"ITXT"},
    "ACTI": {"RNAM"},
    "FLOR": {"RNAM"},
    "TACT": {"RNAM"},
    "MGEF": {"DNAM"},
    "WOOP": {"TNAM"},
    "AVIF": {"ANAM"},
    "PERK": {"EPF2"},
    "FACT": {"MNAM", "FNAM"},
    "REGN": {"RDMP"},
    "GMST": {"DATA"},     # only when EDID starts with "s"
    "BPTD": {"BPTN"},     # body part names (shown in dismemberment/targeting UI)
}

# Category of each (record, field); used for batching, QA length rules and style.
CATEGORY = {
    ("INFO", "NAM1"): "dialogue_line", ("INFO", "RNAM"): "player_choice", ("DIAL", "FULL"): "dialogue_topic",
    ("QUST", "FULL"): "quest_name", ("QUST", "CNAM"): "quest_journal", ("QUST", "NNAM"): "quest_objective",
    ("BOOK", "DESC"): "book_text", ("BOOK", "CNAM"): "book_description", ("BOOK", "FULL"): "book_title",
    ("NPC_", "FULL"): "npc_name", ("NPC_", "SHRT"): "npc_short_name",
    ("MESG", "DESC"): "message", ("MESG", "FULL"): "message_title", ("MESG", "ITXT"): "message_button",
    ("MGEF", "DNAM"): "magic_effect_description", ("MGEF", "FULL"): "magic_effect_name",
    ("SPEL", "FULL"): "spell_name", ("SPEL", "DESC"): "spell_description",
    ("SHOU", "FULL"): "shout_name", ("SHOU", "DESC"): "shout_description", ("WOOP", "FULL"): "word_of_power",
    ("WOOP", "TNAM"): "word_of_power_translation",
    ("PERK", "FULL"): "perk_name", ("PERK", "DESC"): "perk_description", ("PERK", "EPF2"): "perk_button",
    ("AVIF", "FULL"): "skill_name", ("AVIF", "DESC"): "skill_description", ("AVIF", "ANAM"): "skill_abbrev",
    ("LSCR", "DESC"): "loading_screen", ("GMST", "DATA"): "game_setting_text",
    ("CELL", "FULL"): "location_name", ("WRLD", "FULL"): "location_name", ("LCTN", "FULL"): "location_name",
    ("REFR", "FULL"): "map_marker", ("REGN", "RDMP"): "region_name",
    ("FACT", "FULL"): "faction_name", ("FACT", "MNAM"): "faction_rank", ("FACT", "FNAM"): "faction_rank",
    ("RACE", "FULL"): "race_name", ("RACE", "DESC"): "race_description",
    ("CLAS", "FULL"): "class_name", ("CLAS", "DESC"): "class_description",
    ("ACTI", "RNAM"): "activate_prompt", ("FLOR", "RNAM"): "activate_prompt", ("TACT", "RNAM"): "activate_prompt",
    ("PERK", "EPFD"): "perk_button", ("BPTD", "BPTN"): "body_part_name",
}
REVIEW_VISIBILITY = {"hdpt_full", "clfm_full", "proj_full", "expl_full", "hazd_full", "snct_full", "eyes_full",
                     "watr_full", "body_part_name", "coll_desc"}
ITEM_TYPES = {"WEAP", "ARMO", "AMMO", "ALCH", "INGR", "MISC", "KEYM", "SLGM", "SCRL", "LIGH", "BOOK", "APPA"}

# Condition function names, learned from xDump (xEdit) output by tests/xdump_crosscheck.py --learn-out.
# Only verified indices are named; others stay numeric. Never hand-guess these.
_FUNCS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "condition_functions.json")
COND_FUNCS = {}
if os.path.exists(_FUNCS_FILE):
    with open(_FUNCS_FILE, encoding="utf-8") as _f:
        COND_FUNCS = {int(k): v for k, v in json.load(_f)["functions"].items()}
# Functions whose first parameter is a FormID we want resolved to a global key.
FORM_PARAM_FUNCS = {"GetIsID", "GetInFaction", "GetIsRace", "GetIsVoiceType", "GetIsClass", "GetStage",
                    "GetStageDone", "GetQuestRunning", "GetInCell", "GetFactionRank", "GetInCurrentLoc",
                    "GetQuestCompleted", "GetDeadCount", "GetItemCount", "GetEquipped", "GetGlobalValue",
                    "GetRelationshipRank", "GetVMQuestVariable"}
RUN_ON = {0: "Subject", 1: "Target", 2: "Reference", 3: "CombatTarget", 4: "LinkedRef",
          5: "QuestAlias", 6: "PackageData", 7: "EventData"}

SCHEMA = """
DROP TABLE IF EXISTS string_refs;
CREATE TABLE string_refs (
    key TEXT NOT NULL, form_key TEXT NOT NULL, record_type TEXT NOT NULL, field TEXT NOT NULL,
    editor_id TEXT, seq INTEGER, detail TEXT
);
DROP TABLE IF EXISTS records;
CREATE TABLE records (form_key TEXT PRIMARY KEY, plugin TEXT, record_type TEXT, editor_id TEXT, full_key TEXT);
DROP TABLE IF EXISTS quests;
CREATE TABLE quests (form_key TEXT PRIMARY KEY, plugin TEXT, editor_id TEXT, name_key TEXT,
    stages_json TEXT, objectives_json TEXT, aliases_json TEXT);
DROP TABLE IF EXISTS topics;
CREATE TABLE topics (form_key TEXT PRIMARY KEY, plugin TEXT, editor_id TEXT, quest_key TEXT,
    subtype TEXT, prompt_key TEXT, branch_key TEXT);
DROP TABLE IF EXISTS infos;
CREATE TABLE infos (form_key TEXT, plugin TEXT, topic_key TEXT, previous_key TEXT, speaker_key TEXT,
    prompt_key TEXT, response_keys_json TEXT, conditions_json TEXT, seq INTEGER,
    PRIMARY KEY (form_key, plugin));
DROP TABLE IF EXISTS scenes;
CREATE TABLE scenes (form_key TEXT, plugin TEXT, editor_id TEXT, quest_key TEXT, actions_json TEXT,
    PRIMARY KEY (form_key, plugin));
DROP TABLE IF EXISTS actor_refs;
CREATE TABLE actor_refs (form_key TEXT, plugin TEXT, base_key TEXT, PRIMARY KEY (form_key, plugin));
DROP TABLE IF EXISTS speakers;
CREATE TABLE speakers (form_key TEXT, plugin TEXT, editor_id TEXT, name_key TEXT, short_key TEXT,
    female INTEGER, race_key TEXT, voice_key TEXT, factions_json TEXT, PRIMARY KEY (form_key, plugin));
"""


def u32(b, o=0):
    return struct.unpack_from("<I", b, o)[0]


def parse_ctda(payload, plugin, name):
    if len(payload) < 28:
        return None
    flags = payload[0]
    func = struct.unpack_from("<H", payload, 8)[0]
    p1, p2, run_on, ref = struct.unpack_from("<IIII", payload, 12)
    uses_global = bool(flags & 0x04)
    comp = plugin.form_key(u32(payload, 4), name) if uses_global else round(struct.unpack_from("<f", payload, 4)[0], 4)
    fname = COND_FUNCS.get(func, func)
    formish = fname in FORM_PARAM_FUNCS
    return {
        "func": fname, "func_id": func, "op": ["==", "!=", ">", ">=", "<", "<="][(flags >> 5) % 6],
        "value": comp, "or": bool(flags & 0x01),
        "p1": plugin.form_key(p1, name) if formish else p1, "p2": p2,
        "run_on": RUN_ON.get(run_on, run_on),
        "ref": plugin.form_key(ref, name) if run_on == 2 else None,
    }


def scan_plugin(prefix, plugin_path, string_ids, con):
    plugin = Plugin(plugin_path)
    name = os.path.basename(plugin_path)
    refs, recs, quests, topics, infos, speakers = [], [], [], [], [], []
    scenes, actor_refs = [], []
    info_seq = collections.Counter()

    def expected_kind(rtype, field):
        if field == "NAM1":
            return "ilstrings"
        if (field == "DESC" and rtype != "LSCR") or (field == "CNAM" and rtype in ("QUST", "BOOK")):
            return "dlstrings"
        return "strings"

    current = {"type": None, "field": None}

    def lkey(payload):
        if len(payload) != 4:
            return None
        sid = u32(payload)
        kinds = string_ids.get(sid)
        if not kinds:
            return None
        want = expected_kind(current["type"], current["field"])
        kind = want if want in kinds else sorted(kinds)[0]
        return f"{prefix}|{kind}|0x{sid:08X}"

    for rec in plugin.records():
        form_key = plugin.form_key(rec.form_id, name) if rec.form_id else f"{name}:HEADER"
        allowed = LSTRING_FIELDS["*"] | LSTRING_FIELDS.get(rec.type, set())
        subs = list(rec.subrecords())
        edid = next((p[:-1].decode("cp1252", "replace") for t, p in subs if t == "EDID"), None)
        full_key = None
        seq = 0
        stage = objective = None
        q_stages, q_objs, q_aliases = [], [], []
        resp_keys, conds, prompt_key, prev_key, speaker_key = [], [], None, None, None
        topic_quest = topic_sub = topic_prompt = topic_branch = None
        sp = {"short": None, "female": None, "race": None, "voice": None, "factions": []}
        epft = None
        alias_id = None
        scene_quest, scene_actions, action = None, [], None
        for t, pay in subs:
            current["type"], current["field"] = rec.type, t
            if rec.type == "PERK" and t == "EPFT" and pay:
                epft = pay[0]
            # PERK entry-point data is an lstring only when its function-parameter type is 7 (lstring).
            perk_label = rec.type == "PERK" and t == "EPFD" and epft == 7
            # ---- localized text references
            if perk_label or (t in allowed and not (rec.type == "GMST" and t == "DATA"
                                                    and not (edid or "").startswith("s"))):
                k = lkey(pay)
                if k:
                    detail = None
                    if rec.type == "QUST" and t == "CNAM":
                        detail = json.dumps({"stage": stage})
                    elif rec.type == "QUST" and t == "NNAM":
                        detail = json.dumps({"objective": objective})
                    elif rec.type == "INFO" and t == "NAM1":
                        detail = json.dumps({"response": len(resp_keys) + 1})
                    refs.append((k, form_key, rec.type, t, edid, seq, detail))
                    seq += 1
                    if t == "FULL":
                        full_key = k
            # ---- structural context
            if rec.type == "QUST":
                if t == "INDX" and len(pay) >= 2:
                    stage = struct.unpack_from("<H", pay)[0]
                    q_stages.append({"stage": stage, "log": []})
                elif t == "CNAM" and q_stages and lkey(pay):
                    q_stages[-1]["log"].append(lkey(pay))
                elif t == "QOBJ" and len(pay) >= 2:
                    objective = struct.unpack_from("<H", pay)[0]
                    q_objs.append({"objective": objective, "text": None})
                elif t == "NNAM" and q_objs and lkey(pay):
                    q_objs[-1]["text"] = lkey(pay)
                elif t in ("ALST", "ALLS") and len(pay) == 4:
                    alias_id = u32(pay)
                elif t == "ALID":
                    q_aliases.append({"id": alias_id, "name": pay[:-1].decode("cp1252", "replace")})
                elif t == "ALUA" and q_aliases and len(pay) == 4:
                    q_aliases[-1]["unique_actor"] = plugin.form_key(u32(pay), name)
                elif t == "ALFR" and q_aliases and len(pay) == 4:
                    q_aliases[-1]["forced_ref"] = plugin.form_key(u32(pay), name)
            elif rec.type == "SCEN":
                # Actions are delimited by ANAM(type) ... ANAM(empty marker).
                if t == "ANAM":
                    if len(pay) >= 2 and action is None:
                        action = {"type": struct.unpack_from("<H", pay)[0], "alias": None, "topic": None}
                    else:
                        if action is not None:
                            scene_actions.append(action)
                        action = None
                elif action is not None:
                    if t == "ALID" and len(pay) == 4:
                        action["alias"] = struct.unpack_from("<i", pay)[0]
                    elif t == "DATA" and len(pay) == 4 and action["type"] == 0:
                        action["topic"] = plugin.form_key(u32(pay), name)
                    elif t == "INAM" and len(pay) == 4:
                        action["index"] = u32(pay)
                elif t == "PNAM" and len(pay) == 4:
                    scene_quest = plugin.form_key(u32(pay), name)
            elif rec.type == "ACHR" and t == "NAME" and len(pay) == 4:
                actor_refs.append((form_key, prefix, plugin.form_key(u32(pay), name)))
            elif rec.type == "DIAL":
                if t == "QNAM":
                    topic_quest = plugin.form_key(u32(pay), name)
                elif t == "SNAM":
                    topic_sub = pay[:4].decode("ascii", "replace")
                elif t == "BNAM":
                    topic_branch = plugin.form_key(u32(pay), name)
            elif rec.type == "INFO":
                if t == "NAM1" and lkey(pay):
                    resp_keys.append(lkey(pay))
                elif t == "RNAM" and lkey(pay):
                    prompt_key = lkey(pay)
                elif t == "PNAM" and len(pay) == 4:
                    prev_key = plugin.form_key(u32(pay), name)
                elif t == "ANAM" and len(pay) == 4:
                    speaker_key = plugin.form_key(u32(pay), name)
                elif t == "DNAM" and len(pay) == 4:
                    # "Response Data": this INFO reuses the spoken lines of another (shared) INFO.
                    conds.append({"func": "SharedResponse", "info": plugin.form_key(u32(pay), name)})
                elif t == "CTDA":
                    c = parse_ctda(pay, plugin, name)
                    if c:
                        conds.append(c)
            elif rec.type == "NPC_":
                if t == "SHRT":
                    sp["short"] = lkey(pay)
                elif t == "ACBS" and len(pay) >= 4:
                    sp["female"] = int(bool(u32(pay) & 0x1))
                elif t == "RNAM" and len(pay) == 4:
                    sp["race"] = plugin.form_key(u32(pay), name)
                elif t == "VTCK" and len(pay) == 4:
                    sp["voice"] = plugin.form_key(u32(pay), name)
                elif t == "SNAM" and len(pay) >= 4:
                    sp["factions"].append(plugin.form_key(u32(pay), name))

        if edid or full_key:
            recs.append((form_key, prefix, rec.type, edid, full_key))
        if rec.type == "QUST":
            quests.append((form_key, prefix, edid, full_key, json.dumps(q_stages), json.dumps(q_objs),
                           json.dumps(q_aliases, ensure_ascii=False)))
        elif rec.type == "DIAL":
            topics.append((form_key, prefix, edid, topic_quest, topic_sub, full_key, topic_branch))
        elif rec.type == "INFO":
            topic = None
            for gtype, label in reversed(rec.parents):
                if gtype == 7:
                    topic = plugin.form_key(label, name)
                    break
            info_seq[topic] += 1
            # Speaker: exact NPC first, then the broadest identifying class (voice type, faction, race).
            for func, tag in (("GetIsID", ""), ("GetIsVoiceType", "voice:"), ("GetInFaction", "faction:"),
                              ("GetIsRace", "race:")):
                if speaker_key is not None:
                    break
                speaker_key = next((tag + c["p1"] for c in conds if c.get("func") == func
                                    and c.get("run_on") == "Subject" and c.get("op") == "=="
                                    and c.get("value") == 1.0 and isinstance(c.get("p1"), str)), None)
            if speaker_key is None:
                # Quest alias speaker; resolved to the alias name in classify() once all quests are known.
                speaker_key = next((f"alias:{c['p1']}" for c in conds if c.get("func") == "GetIsAliasRef"
                                    and c.get("run_on") == "Subject" and c.get("op") == "=="
                                    and c.get("value") == 1.0), None)
            infos.append((form_key, prefix, topic, prev_key, speaker_key, prompt_key, json.dumps(resp_keys),
                          json.dumps(conds), info_seq[topic]))
        elif rec.type == "SCEN":
            scenes.append((form_key, prefix, edid, scene_quest, json.dumps(scene_actions)))
        elif rec.type == "NPC_":
            speakers.append((form_key, prefix, edid, full_key, sp["short"], sp["female"], sp["race"], sp["voice"],
                             json.dumps(sp["factions"])))
    plugin.close()

    con.executemany("INSERT INTO string_refs VALUES (?,?,?,?,?,?,?)", refs)
    con.executemany("INSERT OR REPLACE INTO records VALUES (?,?,?,?,?)", recs)
    con.executemany("INSERT OR REPLACE INTO quests VALUES (?,?,?,?,?,?,?)", quests)
    con.executemany("INSERT OR REPLACE INTO topics VALUES (?,?,?,?,?,?,?)", topics)
    con.executemany("INSERT OR REPLACE INTO infos VALUES (?,?,?,?,?,?,?,?,?)", infos)
    con.executemany("INSERT OR REPLACE INTO speakers VALUES (?,?,?,?,?,?,?,?,?)", speakers)
    con.executemany("INSERT OR REPLACE INTO scenes VALUES (?,?,?,?,?)", scenes)
    con.executemany("INSERT OR REPLACE INTO actor_refs VALUES (?,?,?)", actor_refs)
    return len(refs)


def classify(con):
    """Copy the primary reference into source_strings and set category/eligibility."""
    cols = {r[1] for r in con.execute("PRAGMA table_info(source_strings)")}
    if "context_flags" not in cols:
        con.execute("ALTER TABLE source_strings ADD COLUMN context_flags TEXT")
    con.execute("UPDATE source_strings SET record_type=NULL, form_id=NULL, editor_id=NULL, field=NULL,"
                " category=NULL, quest_edid=NULL, speaker=NULL, context_flags=NULL,"
                " eligibility=CASE WHEN eligibility='EMPTY' THEN 'EMPTY' ELSE 'UNCLASSIFIED' END")
    first = {}
    for key, form_key, rtype, field, edid in con.execute(
            "SELECT key, form_key, record_type, field, editor_id FROM string_refs ORDER BY rowid"):
        first.setdefault(key, (form_key, rtype, field, edid))
    rows = []
    for key, (form_key, rtype, field, edid) in first.items():
        cat = CATEGORY.get((rtype, field))
        if cat is None:
            cat = "item_name" if (rtype in ITEM_TYPES and field == "FULL") else \
                  "item_description" if (rtype in ITEM_TYPES and field == "DESC") else \
                  f"{rtype.lower()}_{field.lower()}"
        rows.append((rtype, form_key, edid, field, cat, key))
    con.executemany("UPDATE source_strings SET record_type=?, form_id=?, editor_id=?, field=?, category=? WHERE key=?",
                    rows)
    # Quest and speaker for dialogue lines / player choices (resolved in Python; correlated SQL is too slow).
    for col in ("speaker_source", "speaker_alias"):
        if col not in cols:
            con.execute(f"ALTER TABLE source_strings ADD COLUMN {col} TEXT")
    con.execute("UPDATE source_strings SET speaker_source=NULL, speaker_alias=NULL")

    quest_edid = dict(con.execute("SELECT form_key, editor_id FROM quests ORDER BY rowid"))
    quest_alias = {}
    for qk, aliases in con.execute("SELECT form_key, aliases_json FROM quests ORDER BY rowid"):
        for a in json.loads(aliases):
            if isinstance(a, dict) and a.get("id") is not None:
                quest_alias[(qk, a["id"])] = a          # later plugins override earlier ones
    actor_base = dict(con.execute("SELECT form_key, base_key FROM actor_refs ORDER BY rowid"))
    topic_quest = dict(con.execute("SELECT form_key, quest_key FROM topics ORDER BY rowid"))
    # Dialogue actions in scenes: topic -> {(quest, alias_id)}
    topic_scene = collections.defaultdict(set)
    for scene_quest, actions in con.execute("SELECT quest_key, actions_json FROM scenes ORDER BY rowid"):
        for a in json.loads(actions):
            if a.get("type") == 0 and a.get("topic") and a.get("alias") is not None and a["alias"] >= 0:
                topic_scene[a["topic"]].add((scene_quest or topic_quest.get(a["topic"]), a["alias"]))

    def alias_target(qkey, alias_id):
        """Return (label, npc_key or None) for a quest alias."""
        a = quest_alias.get((qkey, alias_id))
        if not a:
            return None, None
        label = f"alias:{quest_edid.get(qkey)}.{a['name']}"
        npc = a.get("unique_actor") or actor_base.get(a.get("forced_ref"))
        return label, npc

    info_ctx = {}
    for form_key, topic_key, speaker_key in con.execute(
            "SELECT form_key, topic_key, speaker_key FROM infos ORDER BY rowid"):
        qkey = topic_quest.get(topic_key)
        q = quest_edid.get(qkey)
        speaker, source, alias_label = speaker_key, None, None
        if speaker_key and speaker_key.startswith("alias:"):
            alias_label, npc = alias_target(qkey, int(speaker_key[6:]))
            speaker, source = (npc or alias_label), "alias_condition"
        elif speaker_key:
            source = speaker_key.split(":")[0] if speaker_key.split(":")[0] in ("voice", "faction", "race") \
                else "npc_condition"
        if speaker is None or source in ("voice", "faction", "race"):
            candidates = {alias_target(sq, aid) for sq, aid in topic_scene.get(topic_key, ())}
            candidates.discard((None, None))
            if len(candidates) == 1:
                alias_label, npc = candidates.pop()
                speaker, source = (npc or alias_label), "scene"
            elif len(candidates) > 1:
                npcs = {npc or label for label, npc in candidates}
                if len(npcs) == 1:
                    speaker, source = npcs.pop(), "scene"
                elif speaker is None:
                    speaker, source = "multiple:" + ",".join(sorted(npcs))[:500], "scene_multiple"
        if speaker is None:
            source = None      # e.g. an alias condition whose alias is not defined in any loaded quest
        prev = info_ctx.get(form_key)
        if prev and speaker is None:
            speaker, source, alias_label = prev[1], prev[2], prev[3]
        info_ctx[form_key] = (q or (prev[0] if prev else None), speaker, source, alias_label)
    updates = []
    for key, (form_key, rtype, _field, _edid) in first.items():
        if rtype == "INFO" and form_key in info_ctx:
            updates.append(info_ctx[form_key] + (key,))
        elif rtype == "QUST":
            updates.append((quest_edid.get(form_key), None, None, None, key))
    con.executemany("UPDATE source_strings SET quest_edid=?, speaker=?, speaker_source=?, speaker_alias=?"
                    " WHERE key=?", updates)
    con.execute("UPDATE source_strings SET eligibility='PLAYER_VISIBLE' WHERE record_type IS NOT NULL"
                " AND eligibility!='EMPTY'")
    con.execute("UPDATE source_strings SET eligibility='BLOCKED_CONTEXT' WHERE record_type IS NULL"
                " AND eligibility!='EMPTY'")
    # Topic names of non-custom topics (Hello, Attack, Idle...) are never shown as menu entries.
    con.execute("""UPDATE source_strings SET eligibility='LIKELY_HIDDEN' WHERE eligibility='PLAYER_VISIBLE'
                   AND record_type='DIAL' AND form_id IN (SELECT form_key FROM topics WHERE subtype!='CUST')""")
    # Visibility not established for these record kinds; decided during the in-game test pass.
    con.execute(f"""UPDATE source_strings SET eligibility='REVIEW_VISIBILITY' WHERE eligibility='PLAYER_VISIBLE'
                    AND category IN ({','.join('?' * len(REVIEW_VISIBILITY))})""", sorted(REVIEW_VISIBILITY))
    # Identifier-looking text (no spaces, CamelCase or underscores) is suspicious wherever it appears.
    con.execute("""UPDATE source_strings SET eligibility='REVIEW_VISIBILITY' WHERE eligibility='PLAYER_VISIBLE'
                   AND instr(source,' ')=0 AND (instr(source,'_')>0 OR source GLOB '*[a-z][A-Z]*')""")

    # Manual decisions survive re-linking (e.g. technical GMST paths marked DO_NOT_TRANSLATE).
    con.execute("CREATE TABLE IF NOT EXISTS eligibility_overrides (key TEXT PRIMARY KEY, eligibility TEXT NOT NULL,"
                " reason TEXT, decided_utc TEXT)")
    con.execute("""UPDATE source_strings SET eligibility=(SELECT eligibility FROM eligibility_overrides o
                   WHERE o.key=source_strings.key) WHERE key IN (SELECT key FROM eligibility_overrides)""")

    # Context flags for dialogue lines.
    shared_targets = set()
    flags = collections.defaultdict(set)
    info_lines = collections.defaultdict(list)
    for form_key, resp, conds in con.execute("SELECT form_key, response_keys_json, conditions_json FROM infos"):
        keys = json.loads(resp)
        info_lines[form_key].extend(keys)
        for c in json.loads(conds):
            if c.get("func") == "SharedResponse":
                shared_targets.add(c["info"])
            elif c.get("func") == "GetPCIsSex" or (c.get("func") == "GetIsSex" and c.get("run_on") != "Subject"):
                for k in keys:
                    flags[k].add("player_gender_conditioned")
            elif c.get("func") == "GetIsSex":
                for k in keys:
                    flags[k].add("speaker_gender_conditioned")
    for info in shared_targets:
        for k in info_lines.get(info, []):
            flags[k].add("shared_response")
    con.executemany("UPDATE source_strings SET context_flags=? WHERE key=?",
                    [(json.dumps(sorted(v)), k) for k, v in flags.items()])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    ap.add_argument("--game-dir", default=GAME_DIR_DEFAULT)
    ap.add_argument("--plugins", default=",".join(PLUGIN_SOURCES))
    args = ap.parse_args()
    con = sqlite3.connect(os.path.join(args.project, "03_translation", "db", "l10n.sqlite"))
    con.executescript(SCHEMA)
    for prefix in args.plugins.split(","):
        ids = collections.defaultdict(set)
        for sid, kind in con.execute("SELECT string_id, kind FROM source_strings WHERE plugin=?", (prefix,)):
            ids[sid].add(kind)
        t = time.time()
        n = scan_plugin(prefix, os.path.join(args.game_dir, "Data", PLUGIN_FILES[prefix]), ids, con)
        con.commit()
        print(f"{prefix}: {n} references in {time.time() - t:.1f}s", flush=True)
    classify(con)
    con.commit()
    for row in con.execute("SELECT plugin, eligibility, COUNT(*) FROM source_strings GROUP BY 1,2 ORDER BY 1,2"):
        print(*row)
    print(f"version {GAME_VERSION}")


if __name__ == "__main__":
    main()
