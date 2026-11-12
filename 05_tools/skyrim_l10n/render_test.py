"""Build the Arabic rendering proof-of-concept mod (T01-T14) and offline previews.

The mod replaces a small set of early-game strings with marked Arabic test text, in several variants:
  A = wrapped at build time (our pipeline)      B = not wrapped (engine wraps; expected to break)
  R = wrapped + <p align="right"> (HTML fields)  S = wrapped, harakat stripped
Every other string stays English. Output is an MO2-style mod folder plus a manifest and previews.

Usage:
    python -I render_test.py --project <root>
"""
import argparse
import csv
import json
import os
import re
import shutil
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skyrim_l10n import GAME_VERSION, STRING_KINDS  # noqa: E402
from skyrim_l10n import arabic  # noqa: E402
from skyrim_l10n.strings_io import StringTable  # noqa: E402

MOD_NAME = "SkyrimArabic_RenderTest"

LONG_LORE = ("حين عاد التنين ألدوين إلى سماء سكايرم، لم يكن أحد في الممالك التسع يتوقع أن يولد "
             "دوفاكين جديد. تقول الأسطورة إن «الدم التنيني» يمنح صاحبه القدرة على امتصاص أرواح "
             "التنانين وتعلُّم الصيحات (Thu'um) بسرعة لا يبلغها أحد. المستوى 25 – 100% – الساعة 3:45")
RALOF = ("أنت، أخيراً استيقظت. كنت تحاول عبور الحدود، أليس كذلك؟ وقعتَ في كمين الإمبراطوريين "
         "مثلنا تماماً، ومثل ذلك اللص هناك.")
LOKIR = ("لعنةً عليكم يا رجال العاصفة! كانت سكايرم بخير قبل أن تأتوا، والإمبراطورية كانت هادئة "
         "وكسولة. لولاكم لسرقتُ ذلك الحصان وكنت الآن في منتصف الطريق إلى هامرفيل.")
FORMS = ("اختبار الأشكال: لا، لأ، لإ، لآ — «صِفْ خَلْقَ خَوْدٍ كَمِثْلِ الشَّمْسِ إِذْ بَزَغَتْ» "
         "١٢٣ / 123 ؛ ؟ !")
BOOK = ("كتاب الاختبار\n\nالفصل الأول: عودة التنانين\n"
        "في العصر الرابع عادت التنانين إلى سماء سكايرم بعد غياب طويل. لم يصدّق أحد في البداية أن "
        "ألدوين، آكل العالم، قد عاد حقاً، حتى احترقت هلغن وتحولت إلى رماد. عندها فقط أدرك الناس أن "
        "النبوءات القديمة لم تكن مجرد حكايات تُروى للأطفال قرب المدفأة.[pagebreak]"
        "الفصل الثاني: الصيحة\n"
        "يقول الرهبان الرماديون إن الصيحة ليست سحراً، بل هي لغة التنانين نفسها. وكل كلمة منها تحمل "
        "قوة تهز الجبال، ولذلك لا ينطق بها إلا من صبر على التعلم سنوات طويلة في قمة العالم.")

# (test id, variant, selector, context, logical text). Selectors:
#   ("key", key) | ("form", form_key, field) | ("category", category) | ("ui", $key)
#   ("quest_lines", quest_edid, speaker_alias or None, category)
CASES = [
    ("T01", "A", ("ui", "$NEW"), "short_label", "لعبة جديدة"),
    ("T01", "A", ("ui", "$CONTINUE"), "short_label", "متابعة"),
    ("T01", "A", ("ui", "$LOAD"), "short_label", "تحميل"),
    ("T01", "A", ("ui", "$SETTINGS"), "short_label", "الإعدادات"),
    ("T01", "A", ("ui", "$CREDITS"), "short_label", "فريق العمل"),
    ("T01", "A", ("ui", "$CREATIONS"), "short_label", "الإبداعات"),
    ("T01", "A", ("ui", "$HELP"), "short_label", "مساعدة"),
    ("T01", "A", ("ui", "$QUIT"), "short_label", "خروج"),
    ("T14", "A", ("ui", "$Quit to desktop?  Any unsaved progress will be lost."), "message_box",
     "هل تريد الخروج إلى سطح المكتب؟ سيضيع أي تقدّم لم يُحفظ."),
    ("T02", "A/B", ("category", "loading_screen"), "loading_screen", LONG_LORE),
    ("T09", "A", ("quest_lines", "MQ101", "alias:MQ101.Ralof", "dialogue_line"), "subtitle", RALOF),
    ("T09", "B", ("quest_lines", "MQ101", "alias:MQ101.Prisoner01", "dialogue_line"), "subtitle", LOKIR),
    ("T07", "A", ("quest_lines", "MQ101", None, "dialogue_line"), "subtitle", FORMS),
    ("T03", "A", ("key", "skyrim|strings|0x000052D5"), "journal_objective", "طليق (Unbound) – المهمة 1"),
    ("T13", "R", ("key", "skyrim|strings|0x000027A4"), "journal_objective", "اهرب من هلغن"),
    ("T13", "A", ("key", "skyrim|strings|0x000027B0"), "journal_objective", "ادخل الحصن مع هادفار أو رالوف"),
    ("T13", "R", ("key", "skyrim|strings|0x00004654"), "journal_objective", "شُقَّ طريقك إلى الحصن"),
    ("T13", "A", ("key", "skyrim|strings|0x0000A4B0"), "journal_objective", "ابحث عن بعض العتاد"),
    ("T13", "R", ("key", "skyrim|strings|0x0001137E"), "journal_objective",
     "(اختياري) حاول فتح قفل القفص بأداة فتح الأقفال قبل أن يعود الحارس إلى مكانه"),
    ("T05", "R", ("key", "skyrim|strings|0x00002E15"), "journal_objective", "تحدّث إلى <Alias=RiverwoodFriend> في ريفروود"),
    ("T05", "A", ("key", "skyrim|strings|0x00002E14"), "journal_objective",
     "(اختياري) سافر إلى ريفروود مع <Alias=FactionFriend>"),
    ("T10", "R", ("key", "skyrim|strings|0x00006533"), "dialogue_topic", "أرسلني <Alias=RiverwoodFriend>. ريفروود في خطر."),
    ("T10", "A", ("key", "skyrim|strings|0x00006539"), "dialogue_topic", "دمّر تنينٌ بلدة هلغن."),
    ("T10", "R", ("key", "skyrim|strings|0x00006392"), "dialogue_topic", "كنت هناك، ورأيت التنين يحرق هلغن حتى سوّاها بالأرض."),
    ("T10", "A", ("key", "skyrim|strings|0x00001E85"), "dialogue_topic", "أريد التحدث إلى الجارل..."),
    ("T11", "A", ("form_of_key", "skyrim|strings|0x000006E3"), "short_label", "سيف حديدي"),
    ("T11", "A", ("key", "skyrim|strings|0x0000B642"), "short_label", "خنجر حديدي"),
    ("T11", "A", ("key", "skyrim|strings|0x0000D85D"), "short_label", "فأس حرب حديدية"),
    ("T11", "A", ("key", "skyrim|strings|0x0000DFE2"), "short_label", "لفائف القدمين"),
    ("T11", "A", ("key", "skyrim|strings|0x00006837"), "short_label", "درع إمبراطوري خفيف"),
    ("T11", "A", ("key", "skyrim|strings|0x00001A43"), "short_label", "حذاء إمبراطوري خفيف"),
    ("T11", "A", ("key", "skyrim|strings|0x0000E718"), "short_label", "درع من الجلد"),
    ("T12", "A", ("key", "skyrim|strings|0x00001C1B"), "short_label", "لهب"),
    ("T12", "A", ("key", "skyrim|strings|0x000032E8"), "short_label", "شفاء"),
    ("T12", "A", ("form_of_key", "skyrim|strings|0x00012345"), "item_card",
     "دفقة من النار تُلحق <mag> نقطة ضرر في الثانية. الأهداف المشتعلة تتلقى ضرراً إضافياً."),
    ("T08", "A/R/B", ("category", "book_text"), "book_page", BOOK),
]


def resolve(con, selector):
    kind = selector[0]
    if kind == "key":
        return [selector[1]]
    if kind == "form":
        return [k for (k,) in con.execute("SELECT key FROM string_refs WHERE form_key=? AND field=?", selector[1:])]
    if kind == "form_of_key":
        # Every plugin copy of the record that owns this string (later plugins override earlier ones).
        form, field = con.execute("SELECT form_key, field FROM string_refs WHERE key=?", (selector[1],)).fetchone()
        return [k for (k,) in con.execute("SELECT key FROM string_refs WHERE form_key=? AND field=?", (form, field))]
    if kind == "category":
        return [k for (k,) in con.execute("SELECT key FROM source_strings WHERE category=? AND eligibility!='EMPTY'"
                                          " ORDER BY key", (selector[1],))]
    if kind == "quest_lines":
        _k, quest, alias, cat = selector
        if alias:
            sql = "SELECT key FROM source_strings WHERE quest_edid=? AND speaker_alias=? AND category=? ORDER BY key"
            return [k for (k,) in con.execute(sql, (quest, alias, cat))]
        sql = ("SELECT key FROM source_strings WHERE quest_edid=? AND category=? AND (speaker_alias IS NULL OR"
               " speaker_alias NOT IN ('alias:MQ101.Ralof','alias:MQ101.Prisoner01')) ORDER BY key")
        return [k for (k,) in con.execute(sql, (quest, cat))]
    raise ValueError(selector)


def render_variant(text, context, variant, tid):
    marked = f"[{tid}{variant}] {text}"
    if variant == "B":
        return arabic.to_visual(marked, context, wrap=False)
    if variant == "R":
        return arabic.to_visual(marked, context, force_right=True)
    if variant == "S":
        return arabic.to_visual(marked, context, harakat="strip")
    return arabic.to_visual(marked, context)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    args = ap.parse_args()
    proj = args.project
    con = sqlite3.connect(os.path.join(proj, "03_translation", "db", "l10n.sqlite"))
    orig_dir = os.path.join(proj, "01_original", GAME_VERSION)
    mod = os.path.join(proj, "07_patch", MOD_NAME)
    if os.path.isdir(mod):
        shutil.rmtree(mod)
    os.makedirs(os.path.join(mod, "Strings"))
    os.makedirs(os.path.join(mod, "Interface"))

    replacements, ui_repl, manifest = {}, {}, []
    seen = set()
    for tid, variants, selector, context, text in CASES:
        if selector[0] == "ui":
            vis = render_variant(text, context, "A", tid) if tid != "T01" else arabic.to_visual(text, context)
            ui_repl[selector[1]] = vis
            manifest.append({"test": tid, "variant": "A", "target": selector[1], "context": context, "logical": text})
            continue
        keys = [k for k in resolve(con, selector) if k not in seen]
        vlist = variants.split("/")
        for i, key in enumerate(keys):
            v = vlist[i % len(vlist)]
            replacements[key] = render_variant(text, context, v, tid)
            seen.add(key)
            manifest.append({"test": tid, "variant": v, "target": key, "context": context, "logical": text})

    # ---- string tables: rebuild only the files that change, keeping every ID and order
    changed_files = 0
    by_file = {}
    for key, value in replacements.items():
        plugin, kind, sid = key.split("|")
        by_file.setdefault((plugin, kind), {})[int(sid, 16)] = value.encode("utf-8")
    for (plugin, kind), repl in sorted(by_file.items()):
        src = os.path.join(orig_dir, "strings", f"{plugin}_english.{kind}")
        table = StringTable.load(src)
        entries = [(sid, repl.get(sid, val)) for sid, val in table.items()]
        data = StringTable.build(kind, entries, dedupe=False)
        check = StringTable.parse(data, kind)
        assert [s for s, _ in check.items()] == [s for s, _ in table.items()], "ID order changed"
        with open(os.path.join(mod, "Strings", f"{plugin}_english.{kind}"), "wb") as f:
            f.write(data)
        changed_files += 1

    # ---- interface: translate file (UTF-16 LE with BOM, tab-separated, CRLF)
    with open(os.path.join(orig_dir, "interface", "translate_english.txt"), "rb") as f:
        raw = f.read()
    lines = raw.decode("utf-16").split("\r\n")
    out_lines = []
    for line in lines:
        k, sep, _v = line.partition("\t")
        out_lines.append(f"{k}\t{ui_repl[k]}" if sep and k in ui_repl else line)
    with open(os.path.join(mod, "Interface", "translate_english.txt"), "wb") as f:
        f.write(b"\xff\xfe" + "\r\n".join(out_lines).encode("utf-16-le"))

    # ---- fontconfig: keep symbol fonts, route text fonts to the Arabic library
    with open(os.path.join(orig_dir, "interface", "fontconfig.txt"), "rb") as f:
        fc = f.read().decode("latin-1")
    remap = {
        "$StartMenuFont": ('"SkyrimArabic UI"', "Normal"), "$DialogueFont": ('"SkyrimArabic UI"', "Normal"),
        "$EverywhereFont": ('"SkyrimArabic UI"', "Normal"), "$EverywhereBoldFont": ('"SkyrimArabic UI Bold"', "Normal"),
        "$EverywhereMediumFont": ('"SkyrimArabic UI"', "Normal"), "$SkyrimBooks": ('"SkyrimArabic Book"', "Normal"),
        "$HandwrittenFont": ('"SkyrimArabic Hand"', "Normal"), "$HandwrittenBold": ('"SkyrimArabic Hand"', "Normal"),
    }
    new_lines = []
    for line in fc.split("\r\n" if "\r\n" in fc else "\n"):
        m = re.match(r'map "(\$[^"]+)" = ".*?" (\w+)', line)
        if m and m.group(1) in remap:
            name, style = remap[m.group(1)]
            line = f'map "{m.group(1)}" = {name} {style}'
        new_lines.append(line)
        if line.startswith('fontlib "Interface\\fonts_en.swf"'):
            new_lines.append('fontlib "Interface\\fonts_ar.swf"')
    nl = "\r\n" if "\r\n" in fc else "\n"
    with open(os.path.join(mod, "Interface", "fontconfig.txt"), "wb") as f:
        f.write(nl.join(new_lines).encode("latin-1"))
    shutil.copy2(os.path.join(proj, "04_fonts", "build", "fonts_ar.swf"), os.path.join(mod, "Interface", "fonts_ar.swf"))

    # ---- licenses and manifest
    lic = os.path.join(mod, "LICENSES")
    os.makedirs(lic)
    shutil.copy2(os.path.join(proj, "04_fonts", "src", "cairo", "OFL.txt"), os.path.join(lic, "Cairo-OFL.txt"))
    shutil.copy2(os.path.join(proj, "04_fonts", "src", "amiri", "OFL.txt"), os.path.join(lic, "Amiri-OFL.txt"))
    with open(os.path.join(mod, "render_test_manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"game_version": GAME_VERSION, "replaced_strings": len(replacements),
                   "ui_keys": len(ui_repl), "entries": manifest}, f, ensure_ascii=False, indent=1)
    with open(os.path.join(proj, "08_qa", "render_tests", "render_test_checklist.csv"), "w", encoding="utf-8-sig",
              newline="") as f:
        w = csv.writer(f)
        w.writerow(["test", "variant", "context", "where to look", "expected", "result (OK/BROKEN)", "screenshot"])
        where = {"T01": "Main menu", "T02": "Any loading screen", "T03": "Journal > Quests (quest name)",
                 "T05": "Journal (after Helgen, quest Before the Storm)", "T07": "Helgen subtitles (other speakers)",
                 "T08": "Open any book or note", "T09": "Opening cart: Ralof (A) and Lokir (B) subtitles",
                 "T10": "Riverwood/Whiterun dialogue choices", "T11": "Inventory item names",
                 "T12": "Magic menu: Flames description", "T13": "Journal > Unbound objectives + HUD",
                 "T14": "Main menu > Quit confirmation"}
        for tid in sorted({m["test"] for m in manifest}):
            for v in sorted({m["variant"] for m in manifest if m["test"] == tid}):
                ctx = next(m["context"] for m in manifest if m["test"] == tid and m["variant"] == v)
                exp = {"A": "connected, right order, no engine wrap", "B": "likely broken order on wrap",
                       "R": "as A + right aligned", "S": "as A without harakat"}[v]
                w.writerow([tid, v, ctx, where[tid], exp, "", ""])
    print(f"replaced {len(replacements)} strings in {changed_files} files, {len(ui_repl)} UI keys -> {mod}")


if __name__ == "__main__":
    main()
