"""Build the Arabic localization mod from ACCEPTED translations.

Every accepted string is converted for its UI context (shaping, build-time wrapping, visual order).
Untranslated strings stay English. Output: 07_patch/SkyrimArabic (MO2/loose layout) + build report.

Usage:
    python -I build_mod.py --project <root>
"""
import argparse
import json
import os
import re
import shutil
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skyrim_l10n import GAME_VERSION, PLUGIN_SOURCES, STRING_KINDS, arabic, qa  # noqa: E402
from skyrim_l10n.strings_io import StringTable  # noqa: E402

MOD_NAME = "SkyrimArabic"
CONTEXT_OF = {
    "dialogue_line": "subtitle", "player_choice": "dialogue_topic", "dialogue_topic": "dialogue_topic",
    "quest_objective": "journal_objective", "quest_journal": "journal_text", "book_text": "book_page",
    "loading_screen": "loading_screen", "message": "message_box",
    "magic_effect_description": "item_card", "spell_description": "item_card", "perk_description": "perk_card",
    "item_description": "item_card", "shout_description": "item_card", "skill_description": "skill_card",
    "race_description": "item_card", "class_description": "item_card", "book_description": "item_card",
    "word_of_power_translation": "short_label",
}
FONTCONFIG_MAP = {
    "$StartMenuFont": ('"SkyrimArabic UI"', "Normal"), "$DialogueFont": ('"SkyrimArabic UI"', "Normal"),
    "$EverywhereFont": ('"SkyrimArabic UI"', "Normal"), "$EverywhereBoldFont": ('"SkyrimArabic UI Bold"', "Normal"),
    "$EverywhereMediumFont": ('"SkyrimArabic UI"', "Normal"), "$SkyrimBooks": ('"SkyrimArabic Book"', "Normal"),
    "$HandwrittenFont": ('"SkyrimArabic Hand"', "Normal"), "$HandwrittenBold": ('"SkyrimArabic Hand"', "Normal"),
}


def context_for(category, text):
    ctx = CONTEXT_OF.get(category)
    if ctx:
        return ctx
    if category == "game_setting_text" and len(text) > 40:
        return "message_box"
    return "short_label"


def harakat_for(context):
    # In-game evidence (2026-11-05): tanween on alef looks like hamza in the UI font -> keep only shadda.
    return "keep" if arabic.CONTEXTS[context]["font"] == "book" else "shadda"


def visual(text, context, wrap=True):
    return arabic.to_visual(text, context, harakat=harakat_for(context), wrap=wrap)


def write_fontconfig(orig_dir, out_path):
    with open(os.path.join(orig_dir, "interface", "fontconfig.txt"), "rb") as f:
        fc = f.read().decode("latin-1")
    nl = "\r\n" if "\r\n" in fc else "\n"
    lines = []
    for line in fc.split(nl):
        m = re.match(r'map "(\$[^"]+)" = ".*?" (\w+)', line)
        if m and m.group(1) in FONTCONFIG_MAP:
            name, style = FONTCONFIG_MAP[m.group(1)]
            line = f'map "{m.group(1)}" = {name} {style}'
        lines.append(line)
        if line.startswith('fontlib "Interface\\fonts_en.swf"'):
            lines.append('fontlib "Interface\\fonts_ar.swf"')
    with open(out_path, "wb") as f:
        f.write(nl.join(lines).encode("latin-1"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    args = ap.parse_args()
    proj = args.project
    con = sqlite3.connect(os.path.join(proj, "03_translation", "db", "l10n.sqlite"))
    orig_dir = os.path.join(proj, "01_original", GAME_VERSION)
    mod = os.path.join(proj, "07_patch", MOD_NAME)
    if os.path.exists(os.path.join(mod, "install_receipt.json")):
        sys.exit("The mod is installed (install_receipt.json present). Run Uninstall-LooseMod.ps1 first, "
                 "or use 05_tools/install/Deploy-Arabic.ps1 which does uninstall -> build -> install.")
    if os.path.isdir(mod):
        shutil.rmtree(mod)
    for sub in ("Strings", "Interface", "LICENSES"):
        os.makedirs(os.path.join(mod, sub))

    problems = []
    rows = con.execute("""SELECT t.key, t.target, s.category, s.source, s.source_sha1, t.source_sha1
                          FROM translations t JOIN source_strings s ON s.key=t.key
                          WHERE t.status='ACCEPTED'""").fetchall()
    by_file = {}
    for key, target, category, source, sha_now, sha_tr in rows:
        if sha_now != sha_tr:
            problems.append(f"STALE {key}: source changed since translation")
            continue
        ctx = context_for(category, target)
        vis = visual(target, ctx)
        if qa.tokens(vis) != qa.tokens(source):
            problems.append(f"TOKENS {key}")
            continue
        plugin, kind, sid = key.split("|")
        by_file.setdefault((plugin, kind), {})[int(sid, 16)] = vis.encode("utf-8")

    files = 0
    for (plugin, kind), repl in sorted(by_file.items()):
        table = StringTable.load(os.path.join(orig_dir, "strings", f"{plugin}_english.{kind}"))
        entries = [(sid, repl.get(sid, val)) for sid, val in table.items()]
        data = StringTable.build(kind, entries, dedupe=True)
        check = StringTable.parse(data, kind)
        assert [s for s, _ in check.items()] == [s for s, _ in table.items()]
        with open(os.path.join(mod, "Strings", f"{plugin}_english.{kind}"), "wb") as f:
            f.write(data)
        files += 1

    # Interface translate file: values must stay single-line (a raw newline breaks every later key).
    ui = dict(con.execute("SELECT substr(key,4), target FROM translations WHERE key LIKE 'ui|%' AND status='ACCEPTED'"))
    with open(os.path.join(orig_dir, "interface", "translate_english.txt"), "rb") as f:
        lines = f.read().decode("utf-16").split("\r\n")
    out_lines, ui_used = [], 0
    for line in lines:
        k, sep, _v = line.partition("\t")
        if sep and k in ui:
            v = visual(ui[k], "short_label", wrap=False)
            if any(c in v for c in "\r\n\t"):
                problems.append(f"UI_NEWLINE {k}")
            else:
                line = f"{k}\t{v}"
                ui_used += 1
        out_lines.append(line)
    with open(os.path.join(mod, "Interface", "translate_english.txt"), "wb") as f:
        f.write(b"\xff\xfe" + "\r\n".join(out_lines).encode("utf-16-le"))
    assert len(out_lines) == len(lines)

    write_fontconfig(orig_dir, os.path.join(mod, "Interface", "fontconfig.txt"))
    shutil.copy2(os.path.join(proj, "04_fonts", "build", "fonts_ar.swf"), os.path.join(mod, "Interface", "fonts_ar.swf"))
    # Patched menus (subtitle speaker order, Arabic date comma, zero letter spacing): build_menus.py
    import subprocess
    subprocess.run([sys.executable, "-I", os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_menus.py"),
                    "--project", proj], check=True, stdout=subprocess.DEVNULL)
    menus_dir = os.path.join(proj, "06_build", "menus")
    for name in sorted(os.listdir(menus_dir)):
        if name.endswith(".swf"):
            shutil.copy2(os.path.join(menus_dir, name), os.path.join(mod, "Interface", name))
    shutil.copy2(os.path.join(proj, "04_fonts", "src", "cairo", "OFL.txt"), os.path.join(mod, "LICENSES", "Cairo-OFL.txt"))
    shutil.copy2(os.path.join(proj, "04_fonts", "src", "amiri", "OFL.txt"), os.path.join(mod, "LICENSES", "Amiri-OFL.txt"))

    report = {"game_version": GAME_VERSION, "strings_written": sum(len(v) for v in by_file.values()),
              "string_files": files, "ui_keys": ui_used, "problems": problems}
    with open(os.path.join(proj, "08_qa", "reports", "build_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in report.items() if k != "problems"}), f"problems={len(problems)}")
    for p in problems[:20]:
        print("  ", p)


if __name__ == "__main__":
    main()
