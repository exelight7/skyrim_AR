"""Build the patched menu SWFs shipped by the Arabic mod (Interface/*.swf loose files).

Two changes, both reproducible from the vanilla 1.7.104.0 menus in 02_extracted:
  1. ActionScript 2 edits from 05_tools/swf_mods/<menu>/scripts/... compiled in with JPEXS FFDec
     (-importScript): subtitle speaker-name order (hudmenu), Arabic comma in date lines
     (tweenmenu, quest_journal).
  2. letterSpacing="N" -> "0" in every DefineEditText initial HTML. Any tracking splits joined
     Arabic letters (tweenmenu used 6.5 px, other menus 0.8-2 px). GlobalFunc.SetText keeps the
     field's letterSpacing, so zeroing the initial format is enough.

Usage: python -I build_menus.py --project <root>
"""
import argparse
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib

MENUS = ["bartermenu", "bookmenu", "containermenu", "craftingmenu", "dialoguemenu", "favoritesmenu",
         "giftmenu", "hudmenu", "inventorymenu", "levelupmenu", "loadingmenu", "lockpickingmenu",
         "magicmenu", "map", "messagebox", "quest_journal", "racesex_menu", "sharedcomponents",
         "sleepwaitmenu", "startmenu", "statsmenu", "textentry", "trainingmenu", "tutorialmenu",
         "tweenmenu"]
LS_RX = re.compile(rb'letterSpacing="-?[0-9.]+"')


def read_swf(path):
    with open(path, "rb") as f:
        d = f.read()
    sig = d[:3]
    if sig == b"CWS":
        body = zlib.decompress(d[8:])
    elif sig == b"FWS":
        body = d[8:]
    else:
        raise ValueError(f"unsupported SWF signature {sig!r} in {path}")
    return sig, d[3], body


def write_swf(path, sig, version, body):
    out = struct.pack("<3sBI", sig, version, len(body) + 8)
    out += zlib.compress(body, 9) if sig == b"CWS" else body
    with open(path, "wb") as f:
        f.write(out)


def zero_letter_spacing(body):
    """Return (new_body, edited_fields). Only top-level DefineEditText (code 37) tags are touched."""
    nbits = body[0] >> 3
    pos = (5 + 4 * nbits + 7) // 8 + 4          # RECT + frame rate + frame count
    out, edited = [body[:pos]], 0
    while pos < len(body):
        hdr = struct.unpack_from("<H", body, pos)[0]
        code, ln, hlen = hdr >> 6, hdr & 0x3F, 2
        if ln == 0x3F:
            ln, hlen = struct.unpack_from("<I", body, pos + 2)[0], 6
        data = body[pos + hlen:pos + hlen + ln]
        if code == 37:
            new = LS_RX.sub(b'letterSpacing="0"', data)
            if new != data:
                edited += 1
                data = new
            out.append(struct.pack("<HI", (code << 6) | 0x3F, len(data)) + data)
        else:
            out.append(body[pos:pos + hlen + ln])
        pos += hlen + ln
        if code == 0:
            break
    return b"".join(out), edited


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    args = ap.parse_args()
    proj = os.path.abspath(args.project)
    tools = json.load(open(os.path.join(proj, "05_tools", "tool_paths.json"), encoding="utf-8"))
    src_dir = os.path.join(proj, "02_extracted", "1.7.104.0", "interface")
    mods_dir = os.path.join(proj, "05_tools", "swf_mods")
    out_dir = os.path.join(proj, "06_build", "menus")
    os.makedirs(out_dir, exist_ok=True)
    report = {}
    with tempfile.TemporaryDirectory() as tmp:
        for menu in MENUS:
            src = os.path.join(src_dir, menu + ".swf")
            if os.path.isdir(os.path.join(mods_dir, menu)):
                # FFDec cannot open paths with non-ASCII characters (the project folder is Arabic),
                # so the input and the script folder are staged in the ASCII temp directory.
                staged = os.path.join(tmp, menu + ".in.swf")
                shutil.copy2(src, staged)
                scripts = os.path.join(tmp, menu + "_as")
                shutil.copytree(os.path.join(mods_dir, menu), scripts)
                compiled = os.path.join(tmp, menu + ".swf")
                r = subprocess.run([tools["java"], "-jar", tools["ffdec_jar"], "-importScript", staged, compiled,
                                    scripts], capture_output=True, text=True)
                if r.returncode != 0 or not os.path.exists(compiled) or "SEVERE" in (r.stdout + r.stderr):
                    sys.exit(f"FFDec failed for {menu}:\n{r.stdout}\n{r.stderr}")
                src = compiled
            sig, ver, body = read_swf(src)
            body, edited = zero_letter_spacing(body)
            target = os.path.join(out_dir, menu + ".swf")
            if not edited and src.startswith(src_dir):
                if os.path.exists(target):
                    os.remove(target)       # nothing to change: ship the vanilla menu untouched
                continue
            write_swf(os.path.join(out_dir, menu + ".swf"), sig, ver, body)
            # Round-trip check: re-reading must give identical tag stream and no tracking left.
            sig2, ver2, body2 = read_swf(os.path.join(out_dir, menu + ".swf"))
            assert (sig2, ver2, body2) == (sig, ver, body), menu
            assert not re.search(rb'letterSpacing="(?!0")', body2), menu
            report[menu] = {"scripts": os.path.isdir(os.path.join(mods_dir, menu)), "fields_zeroed": edited}
    for k, v in report.items():
        print(f"{k}: scripts={'yes' if v['scripts'] else 'no'} letterSpacing_fields={v['fields_zeroed']}")
    with open(os.path.join(proj, "08_qa", "reports", "menus_build.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)


if __name__ == "__main__":
    main()
