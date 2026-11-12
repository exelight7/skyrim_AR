"""Skyrim-specific Arabic conversion: logical Arabic -> visual (pre-shaped, reordered, pre-wrapped) text.

Scaleform in Skyrim neither shapes Arabic nor lays it out right-to-left, and it wraps lines from the
left. We therefore (1) shape into presentation forms, (2) wrap the LOGICAL text ourselves with the
real font metrics and the measured field width, (3) reorder each line into visual order, and
(4) join lines with explicit newlines so the engine never needs to wrap.

Engine tokens (<Alias=...>, <mag>, [pagebreak], %d, HTML tags, $keys) are kept intact; runtime
substitutions reserve an estimated width while wrapping.

Usage:
    python -I arabic.py --context subtitle "النص العربي"
    python -I arabic.py --selftest
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
PROJECT = os.path.dirname(TOOLS)
sys.path.insert(0, os.path.join(TOOLS, "vendor"))
sys.path.insert(0, TOOLS)

import ar_shape  # noqa: E402

SKYRIM_TAG_PATTERNS = [
    r"<(?i:alias|global|bribecost|crimegold|mag|dur|area|chance|basename)\b[^<>]*>",   # engine accepts any case (<global=...>)
    r"<\d+>",
    r"</?(?:p|P|font|FONT|b|B|i|I|u|U|br|BR|Br|div|DIV|img|IMG|li|LI|ul|UL)\b[^<>]*/?>",
    r"\[pagebreak\]",
    None,   # control icons: filled from qa.CONTROL_TOKEN below (single source of truth)
    r"%[-+0#]?\d*(?:\.\d+)?[dsifuxX](?![A-Za-z])",
    r"\$[A-Za-z_][A-Za-z0-9_]*",
]
from skyrim_l10n.qa import CONTROL_TOKEN  # noqa: E402

SKYRIM_TAG_PATTERNS = [p if p is not None else CONTROL_TOKEN for p in SKYRIM_TAG_PATTERNS]
NEWLINE_TOKENS = ("\r\n", "\n", "<br>", "<BR>", "<br/>", "[pagebreak]")
TAG_RE = re.compile("|".join(f"(?:{p})" for p in SKYRIM_TAG_PATTERNS))

with open(os.path.join(HERE, "ui_contexts.json"), encoding="utf-8") as _f:
    CONTEXTS = json.load(_f)


def _estimate_key(tag):
    if tag.startswith("<Alias"):
        return "Alias"
    if tag.startswith("<Global"):
        return "Global"
    for k in ("mag", "dur", "BribeCost"):
        if tag == f"<{k}>":
            return k
    if re.fullmatch(r"<\d+>", tag):
        return "number"
    if tag.startswith("%"):
        return "printf"
    return None


class TokenMeasurer(ar_shape.Measurer):
    """Pixel measurer that also reserves width for runtime substitutions."""

    def __init__(self, px, font, size):
        super().__init__(px=px, font=font, size=size)
        self.estimates = CONTEXTS["_runtime_token_estimates"]

    def width(self, units):
        w = super().width(units)
        for u in units:
            if u.is_tag:
                key = _estimate_key(u.text)
                if key:
                    w += self.font.getlength(self.estimates[key])
        return w


_shapers = {}


def shaper_for(context, harakat="keep", wrap=True):
    key = (context, harakat, wrap)
    if key not in _shapers:
        ctx = CONTEXTS[context]
        meas = None
        if wrap and ctx.get("width"):
            font = os.path.join(PROJECT, CONTEXTS["_fonts"][ctx["font"]])
            meas = TokenMeasurer(px=ctx["width"] * ctx["safety"], font=font, size=ctx["font_px"])
        _shapers[key] = ar_shape.Shaper(mode="visual", base="rtl", harakat=harakat,
                                        tag_patterns=SKYRIM_TAG_PATTERNS, newline_tokens=NEWLINE_TOKENS,
                                        measurer=meas, wrap_sep="\n")
    return _shapers[key]


# Survival Mode wraps whole descriptions in "[SURV=...]"; the engine reads the raw prefix, so the
# wrapper must stay in place (not be reordered) and only the inner text is converted.
SURV_RX = re.compile(r"^\[SURV=(.*)\]$", re.S)


def to_visual(text, context, harakat="keep", wrap=True, force_right=False):
    """Convert one logical Arabic game string for the given UI context."""
    m = SURV_RX.match(text)
    if m:
        return "[SURV=" + to_visual(m.group(1), context, harakat, wrap, force_right) + "]"
    out = shaper_for(context, harakat, wrap).process(text)
    if force_right and CONTEXTS[context].get("html") and not out.lstrip().lower().startswith("<p"):
        out = f'<p align="right">{out}</p>'
    return out


def tokens(text):
    return sorted(TAG_RE.findall(text))


def max_line_width(visual, context):
    ctx = CONTEXTS[context]
    meas = TokenMeasurer(px=1, font=os.path.join(PROJECT, CONTEXTS["_fonts"][ctx["font"]]), size=ctx["font_px"])
    widths = []
    for line in re.split("|".join(re.escape(t) for t in NEWLINE_TOKENS), visual):
        units = ar_shape.to_units(ar_shape.tokenize(line, TAG_RE))
        widths.append(meas.width(units))
    return max(widths) if widths else 0


def selftest():
    samples = [
        ("subtitle", "أيها الغريب، استيقظت أخيراً. كنت تحاول عبور الحدود، أليس كذلك؟ مشيت مباشرة إلى كمين الإمبراطورية مثلنا تماماً، ومثل ذلك اللص هناك."),
        ("journal_objective", "تحدّث إلى <Alias=Questgiver> في <Alias=Location> واحصل على <Global=GoldReward> قطعة ذهبية."),
        ("item_card", "يُلحق بالهدف <mag> نقطة ضرر ناري لمدة <dur> ثوانٍ."),
        ("book_page", "الفصل الأول\nكان التنين ألدوين يحلّق فوق السماء.[pagebreak]الفصل الثاني\nلم يعد أحد يذكر اسمه."),
    ]
    arabic_base = re.compile("[آ-ي]")   # U+0621 (hamza) has no contextual forms
    for ctx, text in samples:
        vis = to_visual(text, ctx)
        assert tokens(vis) == tokens(text), (ctx, tokens(vis), tokens(text))
        assert not arabic_base.search(TAG_RE.sub("", vis)), f"unshaped letters remain in {ctx}"
        limit = CONTEXTS[ctx]["width"] * CONTEXTS[ctx]["safety"]
        w = max_line_width(vis, ctx)
        long_word = max(max_line_width(to_visual(wd, ctx, wrap=False), ctx) for wd in text.split())
        assert w <= limit or w <= long_word + 1, (ctx, w, limit)
        print(f"{ctx}: lines={vis.count(chr(10)) + 1} max_width={w:.0f}/{limit:.0f} tokens_ok")
    print("selftest: OK")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("text", nargs="?")
    ap.add_argument("--context", default="subtitle", choices=[k for k in CONTEXTS if not k.startswith("_")])
    ap.add_argument("--harakat", default="keep", choices=["keep", "strip", "shadda"])
    ap.add_argument("--no-wrap", action="store_true")
    ap.add_argument("--force-right", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    print(to_visual(args.text, args.context, args.harakat, not args.no_wrap, args.force_right))


if __name__ == "__main__":
    main()
