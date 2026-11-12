"""Compose Arabic item names from translated parts, so patterned names stay consistent and gender-correct.

Inputs (in the batch folder):
  base_*.tsv      '<English base name>\t<Arabic>|SKIP'  (hand-translated; wins over generated forms)
  suffix_of.tsv   '<English text after " of ">\t<Arabic definite noun phrase>'
  override.tsv    optional '<English full name>\t<Arabic>' for names composition cannot handle

Generated:
  * blessing tiers  'Hallowed Ebony Sword' -> 'سيف أبنوسي مُكرَّس'  (noun + material adj + tier adj, agreeing)
  * '<Base> of <Suffix>':
      - base is one word            -> construct state:  'خاتم' + 'التدمير الكبير'
      - base has modifiers          -> 'ذو' / 'ذات' (by the gender of the head noun) + suffix

Output: names_items.tsv ('English\tArabic') consumed by `translations.py apply-names`.

Usage: python -I compose_items.py --batch-dir <dir> --sources <english names file>
"""
import argparse
import glob
import os
import re

FEMININE_HEADS = {"فأس", "عصا", "مطرقة", "خوذة", "قلادة", "تميمة", "قفازات", "جرعة", "لفافة", "قلنسوة", "قبعة",
                  "سبيكة", "واقيات", "ملابس", "حقيبة", "صنارة", "دمية", "سترة", "عباءة", "جوهرة", "شظية", "مطرقة",
                  "ريشة", "عين", "يد", "كأس", "قارورة", "زجاجة", "سلّة", "حلّة", "ساق", "رأس", "شوكة", "قناع"}
MASCULINE_OVERRIDE = {"رأس", "قناع"}

WEAPONS = {  # English -> (Arabic noun phrase, feminine?)
    "Battleaxe": ("فأس قتال", True), "Battle Axe": ("فأس قتال", True), "War Axe": ("فأس حرب", True),
    "Warhammer": ("مطرقة حرب", True), "Bow": ("قوس", False), "Hunting Bow": ("قوس صيد", False),
    "Crossbow": ("قوس نشّاب", False), "Dagger": ("خنجر", False), "Greatsword": ("سيف ضخم", False),
    "Mace": ("صولجان", False), "Sword": ("سيف", False),
}
MATERIALS = {  # English -> masculine adjective (feminine adds ة) or a fixed prepositional phrase
    "Iron": "حديدي", "Steel": "فولاذي", "Imperial": "إمبراطوري", "Elven": "إلفي", "Glass": "زجاجي",
    "Ebony": "أبنوسي", "Daedric": "دايدري", "Dwarven": "دويمري", "Orcish": "أوركي", "Nordic": "نوردي",
    "Stalhrim": "ستالهريمي", "Silver": "فضي", "Dragonbone": "@من عظام التنين",
}
TIERS = {"Blessed": "مبارك", "Hallowed": "مُكرَّس", "Holy": "مقدّس", "Reverent": "مُوقَّر",
         "Sanctified": "مُطهَّر", "Virtuous": "فاضل"}


def fem(adj):
    return adj + "ة"


def tier_name(en):
    m = re.fullmatch(r"(%s) (?:(%s) )?(%s)" % ("|".join(TIERS), "|".join(MATERIALS), "|".join(WEAPONS)), en)
    if not m:
        return None
    tier, mat, weap = m.groups()
    noun, f = WEAPONS[weap]
    t = fem(TIERS[tier]) if f else TIERS[tier]
    if not mat:
        return f"{noun} {t}"
    mat_ar = MATERIALS[mat]
    if mat_ar.startswith("@"):
        return f"{noun} {t} {mat_ar[1:]}"
    return f"{noun} {fem(mat_ar) if f else mat_ar} {t}"


def head_is_feminine(ar):
    first = ar.split()[0]
    if first in MASCULINE_OVERRIDE:
        return False
    return first in FEMININE_HEADS or first.endswith("ة") or first.endswith("ات")


def compose_of(base_ar, suffix_ar):
    if " " not in base_ar.strip():
        return f"{base_ar} {suffix_ar}"
    return f"{base_ar} {'ذات' if head_is_feminine(base_ar) else 'ذو'} {suffix_ar}"


def read_tsv(path):
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\r\n")
            if not line.strip() or line.startswith("#"):
                continue
            en, _sep, ar = line.partition("\t")
            out[en.strip()] = ar.strip()
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--batch-dir", required=True)
    ap.add_argument("--sources", required=True, help="file with one English item name per line")
    args = ap.parse_args()
    base = {}
    for p in sorted(glob.glob(os.path.join(args.batch_dir, "base_*.tsv"))):
        for en, ar in read_tsv(p).items():
            if en in base and base[en] != ar:
                print(f"CONFLICT base {en!r}: {base[en]!r} vs {ar!r}")
            base[en] = ar
    suffix = read_tsv(os.path.join(args.batch_dir, "suffix_of.tsv"))
    ov_path = os.path.join(args.batch_dir, "override.tsv")
    override = read_tsv(ov_path) if os.path.exists(ov_path) else {}
    with open(args.sources, encoding="utf-8") as f:
        sources = [s.strip() for s in f if s.strip()]

    def base_ar(en):
        return base.get(en) or tier_name(en)

    out, missing = {}, []
    for en in sources:
        ar = override.get(en) or base.get(en) or tier_name(en)
        if ar is None and " of " in en:
            head, tail = en.split(" of ", 1)
            h, t = base_ar(head), suffix.get(tail)
            if h and t and h != "SKIP":
                ar = compose_of(h, t)
            elif h == "SKIP":
                ar = "SKIP"
        if ar is None:
            missing.append(en)
        else:
            out[en] = ar
    with open(os.path.join(args.batch_dir, "names_items.tsv"), "w", encoding="utf-8") as f:
        for en, ar in out.items():
            f.write(f"{en}\t{ar}\n")
    with open(os.path.join(args.batch_dir, "compose_missing.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(missing))
    print(f"{len(out)} names composed, {len(missing)} missing -> compose_missing.txt")


if __name__ == "__main__":
    main()
