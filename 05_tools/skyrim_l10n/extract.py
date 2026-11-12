"""Copy the English string tables and interface text/font files out of the game BSAs.

Reads the game directory only. Writes to <project>/01_original/<version>/ and marks files read-only.

Usage:
    python -I extract.py --project <project_root> [--game-dir <dir>]
"""
import argparse
import json
import os
import stat
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skyrim_l10n import GAME_DIR_DEFAULT, GAME_VERSION, INTERFACE_FILES, PLUGIN_SOURCES, STRING_KINDS  # noqa: E402
from skyrim_l10n.bsa import BsaArchive  # noqa: E402
from skyrim_l10n.strings_io import sha256  # noqa: E402


def write_readonly(dest, data):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.exists(dest):
        os.chmod(dest, stat.S_IWRITE | stat.S_IREAD)
    with open(dest, "wb") as f:
        f.write(data)
    os.chmod(dest, stat.S_IREAD)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    ap.add_argument("--game-dir", default=GAME_DIR_DEFAULT)
    args = ap.parse_args()

    data_dir = os.path.join(args.game_dir, "Data")
    out_root = os.path.join(args.project, "01_original", GAME_VERSION)
    archives = {}
    manifest = {"game_version": GAME_VERSION, "files": {}}

    def pull(bsa_name, inner):
        if bsa_name not in archives:
            archives[bsa_name] = BsaArchive(os.path.join(data_dir, bsa_name))
        data = archives[bsa_name].read(inner)
        dest = os.path.join(out_root, *inner.split("/"))
        write_readonly(dest, data)
        manifest["files"][inner] = {"source_bsa": bsa_name, "size": len(data), "sha256": sha256(data)}
        print(f"extracted {inner} ({len(data)} bytes) from {bsa_name}")

    for plugin, bsa_name in PLUGIN_SOURCES.items():
        for kind in STRING_KINDS:
            pull(bsa_name, f"strings/{plugin}_english.{kind}")
    for inner in INTERFACE_FILES:
        pull("Skyrim - Interface.bsa", inner)

    with open(os.path.join(out_root, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
    print(f"{len(manifest['files'])} files -> {out_root}")


if __name__ == "__main__":
    main()
