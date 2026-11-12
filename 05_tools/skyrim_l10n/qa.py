"""Automatic QA for Arabic translations (logical text, before shaping).

Each check returns findings (severity, check_id, message). A translation with any CRITICAL or HIGH
finding is not accepted. Rules come from docs/10_LINGUISTIC_QA.md and in-game evidence
(e.g. raw newlines break translate_english.txt; injected HTML shows literally in non-HTML fields).
"""
import re
from collections import Counter

# Controller/keyboard icons the engine substitutes ([Activate], [PS3_X], [RotatePick]). Bracketed prose in
# books ("[which is]", "[Optional]", "[NEW SAVE]") is NOT a token.
CONTROL_NAMES = ("Activate|Right Attack/Block|Left Attack/Block|Ready Weapon|Shout|Jump|Sprint|Sneak|Favorites|"
                 "Move|Forward|Back|Strafe Left|Strafe Right|Cancel|Left|Right|Tween Menu|Accept|Look|Wait|Journal|"
                 "Pause|Quicksave|Quickload|Run|Toggle POV|Auto-Move|Zoom In|Zoom Out|Up|Down|Inventory|Magic|Map|"
                 "Stats|Toggle Always Run|Quick Inventory|Quick Magic|Quick Map|Quick Stats|XButton|YButton|"
                 "Left Thumbstick|Right Thumbstick|Mouse Move|Item Zoom|Rotate")
CONTROL_TOKEN = (r"\[(?:(?:" + CONTROL_NAMES + r")|[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+"
                 r"|[A-Z][a-z]+(?:[A-Z][A-Za-z0-9]*)+|[A-Z][a-z]+\d+)\]")
TOKEN_RX = re.compile(
    r"<(?i:alias|global|bribecost|crimegold|mag|dur|area|chance|basename)\b[^<>]*>|<\d+>"
    r"|</?(?:p|P|font|FONT|b|B|i|I|u|U|br|BR|Br|hr|HR|div|DIV|img|IMG|li|LI|ul|UL)\b[^<>]*/?>"
    r"|\[pagebreak\]|<pagebreak>|" + CONTROL_TOKEN + r"|%[-+0#]?\d*(?:\.\d+)?[dsifuxX](?![A-Za-z])|\$[A-Za-z_][A-Za-z0-9_]*")
ARABIC = re.compile(r"[؀-ۿ]")
LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z'’]+")
DIGITS = re.compile(r"\d+(?:[.,]\d+)?")
PERSIAN = re.compile(r"[یکۀ]")
# Spellings that are always wrong in MSA (no hamza / wrong form). Word-bounded.
ALWAYS_WRONG = {
    "الى": "إلى", "انت": "أنت", "انتم": "أنتم", "اذا": "إذا", "لان": "لأن", "اين": "أين",
    "امام": "أمام", "اول": "أول", "اخر": "آخر", "انا": "أنا", "ايضا": "أيضاً", "احد": "أحد",
    "اريد": "أريد", "اكثر": "أكثر", "اقل": "أقل", "اسف": "آسف", "الان": "الآن",
    "هاذا": "هذا", "هاذه": "هذه", "لاكن": "لكن", "ذالك": "ذلك", "مسؤل": "مسؤول", "شيئ": "شيء",
}
WORD = re.compile(r"[ء-يٰٱ]+")
LATIN_PUNCT_NEAR_AR = re.compile(r"[؀-ۿ]\s?[,?;]|[,?;]\s?[؀-ۿ]")
NEGATION_EN = re.compile(r"\b(?:not|never|no|n't|nothing|none|nobody|nowhere|cannot|can't|won't|don't|didn't)\b", re.I)
NEGATION_AR = re.compile(
    r"(?<![ء-ي])[وفأ]?(?:لا|لم|لن|لما|ليس|ليست|ليسوا|لست|لستِ|لستم|لسنا|ما|غير|بلا|دون|عدم|"
    r"أبداً|أبدا|قط|إلا|لولا|كلا|ممنوع|يتعذر|تعذر|يستحيل|مستحيل)(?![ء-ي])")
STRIP_TAGS = re.compile(r"<[^<>]*>")
HARAKAT = re.compile(r"[ً-ْٰ]")

# Latin words allowed to stay (game abbreviations shown as-is).
LATIN_ALLOW = {"XP", "HP", "UI", "FOV", "HDR", "DLC", "FPS", "VSync", "Bethesda", "net", "Steam", "Xbox",
               "PlayStation", "Network", "PS", "PSN", "EULA", "DNS", "PC", "OK", "ID", "Kinect", "TAA", "FXAA",
               "SSAO", "HUD", "PIN", "AM", "PM", "LB", "RB", "LT", "RT", "Esc", "Tab", "Ctrl", "Alt", "Shift",
               "Bink", "Havok", "Scaleform", "Autodesk", "Microsoft", "Windows", "DirectX", "NVIDIA", "AMD",
               "Nintendo", "Switch", "Joy", "Con", "ZeniMax", "Media", "amiibo", "Plus", "Legend", "Zelda", "NFC",
               "SURV"}   # engine marker for Survival Mode text: [SURV=...]
ORDINAL_SUFFIXES = {"st", "nd", "rd", "th", " of "}   # " of " joins day and month in the date line
URL_RX = re.compile(r"https?://\S+|\b[\w.-]+\.(?:net|com|org)\b(?:/\S*)?")


def tokens(text):
    return Counter(TOKEN_RX.findall(text))


# Cipher fonts draw Latin letters as in-world glyphs (Daedric, Dragon, Falmer, Dwemer, Mage script).
# Text inside them must stay Latin, so it is removed before the language checks. Font tags nest the
# way Scaleform renders them: each <font face=...> pushes, each </font> pops.
CIPHER_FACE = re.compile(r"""face\s*=\s*['"]?\$(?:Daedric|Dragon|Falmer|Dwemer|MageScript)Font""", re.I)
FONT_TAG = re.compile(r"<(/?)font\b[^<>]*>", re.I)


def strip_cipher(text):
    out, stack, pos = [], [], 0
    for m in FONT_TAG.finditer(text):
        if not any(stack):
            out.append(text[pos:m.start()])
        out.append(m.group(0))
        if m.group(1):
            if stack:
                stack.pop()
        else:
            stack.append(bool(CIPHER_FACE.search(m.group(0))))
        pos = m.end()
    if not any(stack):
        out.append(text[pos:])
    return "".join(out)


def check(source, target, category="", in_translate_file=False, glossary=None):
    """Return list of (severity, check_id, message)."""
    out = []
    if not target or not target.strip():
        # Ordinal suffixes (st/nd/rd/th) are glued to a number at runtime ("4th"); Arabic needs none,
        # so a single space is the correct translation.
        if source in ORDINAL_SUFFIXES and target == " ":
            return []
        return [("CRITICAL", "empty", "empty translation")]
    if tokens(source) != tokens(target):
        out.append(("CRITICAL", "tokens", f"tokens differ: src={sorted(tokens(source).elements())} "
                                           f"tgt={sorted(tokens(target).elements())}"))
    if source.startswith("[SURV=") and not (target.startswith("[SURV=") and target.endswith("]")):
        out.append(("CRITICAL", "surv_wrapper", "Survival Mode wrapper [SURV=...] must enclose the whole text"))
    if "\0" in target or any(ord(c) < 0x20 and c not in "\n\r\t" for c in target):
        out.append(("CRITICAL", "control_chars", "control characters"))
    if in_translate_file and any(c in target for c in "\r\n\t"):
        out.append(("CRITICAL", "translate_file_newline", "newline/tab inside translate_english.txt value"))
    if target.count("\n") > source.count("\n") + 0:
        out.append(("HIGH", "added_newlines", "translation adds line breaks; wrapping is done at build time"))
    source, target = strip_cipher(source), strip_cipher(target)
    # Tokens such as [pagebreak] are not prose; a text whose only Latin is inside cipher fonts needs no Arabic.
    if not ARABIC.search(STRIP_TAGS.sub("", target)) and LATIN_WORD.search(STRIP_TAGS.sub("", TOKEN_RX.sub(" ", source))):
        out.append(("HIGH", "untranslated", "no Arabic letters in translation"))
    rest = URL_RX.sub(" ", TOKEN_RX.sub(" ", target))
    latin = [w for w in LATIN_WORD.findall(rest) if w not in LATIN_ALLOW
             and not (glossary and w in glossary.get("_latin_allowed", ()))]
    if latin:
        out.append(("HIGH", "latin_words", f"Latin words left: {latin[:5]}"))
    src_digits = sorted(DIGITS.findall(URL_RX.sub(" ", TOKEN_RX.sub(" ", source))))
    tgt_digits = sorted(DIGITS.findall(rest.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))))
    if src_digits != tgt_digits:
        out.append(("HIGH", "numbers", f"numbers differ: {src_digits} vs {tgt_digits}"))
    if PERSIAN.search(target):
        out.append(("HIGH", "persian_letters", "Persian ی/ک/ۀ letters"))
    bare = HARAKAT.sub("", target)
    if NEGATION_EN.search(source) and not NEGATION_AR.search(bare):
        out.append(("HIGH", "negation", "source negates, translation has no negation word"))
    for w in WORD.findall(bare):
        if w in ALWAYS_WRONG:
            out.append(("HIGH", "spelling", f"{w} -> {ALWAYS_WRONG[w]}"))
    if LATIN_PUNCT_NEAR_AR.search(STRIP_TAGS.sub("", target)):
        out.append(("MEDIUM", "latin_punct", "Latin , ? ; next to Arabic (use ، ؟ ؛)"))
    if "  " in target:
        out.append(("LOW", "double_space", "double space"))
    if glossary:
        for en, ar in glossary.get("terms", {}).items():
            if re.search(rf"\b{re.escape(en)}\b", source) and ar not in target:
                out.append(("MEDIUM", "glossary", f"'{en}' expected as '{ar}'"))
    return out


def blocking(findings):
    return any(sev in ("CRITICAL", "HIGH") for sev, _c, _m in findings)
