"""Skyrim SE Arabic localization toolkit (read-only access to game files)."""
import os
import re

GAME_DIR_DEFAULT = r"C:\Program Files (x86)\Steam\steamapps\common\Skyrim Special Edition"
GAME_VERSION = "1.7.104.0"

# Official plugins in load order; Creation Club plugins are discovered from the Data folder because
# the game downloads/updates them itself (observed 2026-11-05: 4 -> ~70 CC plugins after a launch).
BASE_PLUGINS = [
    ("skyrim", "Skyrim.esm", "Skyrim - Interface.bsa"),
    ("update", "Update.esm", "Skyrim - Interface.bsa"),
    ("dawnguard", "Dawnguard.esm", "Skyrim - Interface.bsa"),
    ("hearthfires", "HearthFires.esm", "Skyrim - Interface.bsa"),
    ("dragonborn", "Dragonborn.esm", "Skyrim - Interface.bsa"),
    ("_resourcepack", "_ResourcePack.esl", "_ResourcePack.bsa"),
]
CC_RX = re.compile(r"^cc[a-z]{6}\d{3}[-_].+\.(esm|esl)$", re.I)


def discover_plugins(game_dir=GAME_DIR_DEFAULT):
    """Return [(prefix, plugin_file, bsa_file)] for every official localized plugin present."""
    data = os.path.join(game_dir, "Data")
    names = {n.lower(): n for n in os.listdir(data)} if os.path.isdir(data) else {}
    out = [p for p in BASE_PLUGINS if p[1].lower() in names]
    # Creation Club load order comes from Skyrim.ccc; unlisted ones go last, alphabetically.
    order = []
    ccc = os.path.join(game_dir, "Skyrim.ccc")
    if os.path.exists(ccc):
        with open(ccc, encoding="utf-8", errors="replace") as f:
            order = [ln.strip().lower() for ln in f if ln.strip()]
    rank = {n: i for i, n in enumerate(order)}
    ccs = sorted((n for n in names.values() if CC_RX.match(n)), key=lambda n: (rank.get(n.lower(), 10**6), n.lower()))
    for n in ccs:
        stem = os.path.splitext(n)[0]
        bsa = names.get(stem.lower() + ".bsa")
        if bsa:
            out.append((stem.lower(), n, bsa))
    return out


_DISCOVERED = discover_plugins()
PLUGIN_SOURCES = {prefix: bsa for prefix, _f, bsa in _DISCOVERED}
PLUGIN_FILES = {prefix: f for prefix, f, _b in _DISCOVERED}

STRING_KINDS = ("strings", "dlstrings", "ilstrings")

# Interface files relevant to text and fonts.
INTERFACE_FILES = (
    "interface/translate_english.txt",
    "interface/fontconfig.txt",
    "interface/fonts_en.swf",
    "interface/fonts_console.swf",
    "interface/fonts_cclub.swf",
    "interface/gfxfontlib.swf",
)
