# Vendored from the game-arabization skill (scripts/ar_shape.py) on 2026-11-05. Do not edit here;
# Skyrim-specific behaviour lives in 05_tools/skyrim_l10n/arabic.py.
#!/usr/bin/env python3
"""
ar_shape.py - Arabic pre-shaper + bidi reorderer for game engines.

Use it when a game draws Arabic letters DISCONNECTED (no OpenType shaping)
and/or BACKWARDS (no right-to-left layout). It converts logical Arabic text into
Unicode Presentation Forms (one fixed glyph per contextual shape) and, in
"visual" mode, reorders every line into left-to-right visual order, so an engine
that only draws glyphs one after another shows correct, connected Arabic.

Modes
  visual   (default) shape + reorder each line for engines with NO shaping and NO RTL
  forms    shape only, keep logical order (engine does RTL/bidi itself but cannot shape)
  reorder  reorder only, no shaping (engine shapes but lays everything out LTR)
  wrap     keep LOGICAL text, only insert line breaks measured on the real shaped width
           (engines that shape but do not wrap: RPG Maker MZ messages, fixed text boxes)

What it handles
  * all Arabic letters incl. hamza forms, taa marbuta, alef maksura, tatweel,
    lam-alef ligatures (لا لأ لإ لآ), Persian/Urdu letters (پ چ ژ ک گ ی ڤ ...)
  * harakat (keep / strip / keep only shadda)
  * tags and placeholders are protected and transparent for joining
    (<color=red>..</color>, {0}, {b}..{/b}, %s, %1$d, RPG Maker \\C[2] \\N[1] ...)
  * paired tags are re-paired after reversal; "state codes" such as RPG Maker
    \\C[n] are re-emitted so colours still cover the right words
  * numbers / Latin words stay left-to-right inside Arabic, brackets mirrored
  * word wrap BEFORE reversal (by character count or by real pixel width)
  * multi-line: each line is reordered on its own, line order is never flipped

Input / output
  ar_shape.py "النص هنا"                      -> prints result
  ar_shape.py -i in.txt -o out.txt             -> every line of a text file
  ar_shape.py --csv in.csv --column ar -o out.csv   (other columns untouched)
  ar_shape.py --json in.json -o out.json [--json-key-re "^(text|name)$"]
  ar_shape.py --explain "لا"                   -> code points of the result
  ar_shape.py --selftest

Pure Python 3.8+, no dependencies (Pillow only for --wrap-px).
"""
import os
import argparse
import csv
import io
import json
import re
import sys
import unicodedata

# --------------------------------------------------------------------------
# Presentation-form tables, built from the Unicode database at import time
# --------------------------------------------------------------------------
_FORM_TAGS = {'<isolated>': 'iso', '<final>': 'fin', '<initial>': 'ini', '<medial>': 'med'}
FORMS = {}      # base letter -> {'iso': ch, 'fin': ch, 'ini': ch, 'med': ch}
LAM_ALEF = {}   # alef variant -> {'iso': ch, 'fin': ch}
ALEFS = '\u0622\u0623\u0625\u0627'   # آ أ إ ا
LAM = '\u0644'


def _build_tables():
    # FE70-FEFF (Presentation Forms-B) first so it wins over the FB50 block.
    for start, end in ((0xFE70, 0xFEFF), (0xFB50, 0xFDFF)):
        for cp in range(start, end + 1):
            ch = chr(cp)
            dec = unicodedata.decomposition(ch)
            if not dec:
                continue
            parts = dec.split()
            form = _FORM_TAGS.get(parts[0])
            if not form:
                continue
            bases = [chr(int(p, 16)) for p in parts[1:]]
            if len(bases) == 1 and unicodedata.category(bases[0]) == 'Lo':
                FORMS.setdefault(bases[0], {}).setdefault(form, ch)
            elif len(bases) == 2 and bases[0] == LAM and bases[1] in ALEFS:
                LAM_ALEF.setdefault(bases[1], {}).setdefault(form, ch)


_build_tables()

ZWJ, ZWNJ, TATWEEL, SHADDA = '\u200d', '\u200c', '\u0640', '\u0651'
BIDI_CONTROLS = set('\u200e\u200f\u061c\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069')
MIRROR = dict(zip('()[]{}<>«»‹›', ')(][}{><»«›‹'))
PERSIAN_TO_ARABIC = {'\u06cc': '\u064a', '\u06a9': '\u0643', '\u06c0': '\u0647\u0654'}


def joining_type(ch):
    """D=dual, R=right, C=join-causing, T=transparent, U=non-joining."""
    if ch in (TATWEEL, ZWJ):
        return 'C'
    if ch == ZWNJ:
        return 'U'
    cat = unicodedata.category(ch)
    if cat in ('Mn', 'Me', 'Cf'):
        return 'T'
    f = FORMS.get(ch)
    if not f:
        return 'U'
    if 'ini' in f or 'med' in f:
        return 'D'
    if 'fin' in f:
        return 'R'
    return 'U'


def is_arabic_mark(ch):
    return unicodedata.category(ch) == 'Mn' and (
        '\u0610' <= ch <= '\u061a' or '\u064b' <= ch <= '\u065f' or ch == '\u0670'
        or '\u06d6' <= ch <= '\u06ed' or '\u08d3' <= ch <= '\u08ff')


# --------------------------------------------------------------------------
# Tokenizing: protected tags/placeholders vs. characters
# --------------------------------------------------------------------------
DEFAULT_TAG_PATTERNS = [
    r'<[^<>\n]{1,200}>',                                  # <b> <color=#fff> </color> <br>
    r'\{[^{}\n]{0,200}\}',                                # {0} {name} {b} {/b} {w}
    r'%(?:\d+\$)?[-+#0]*\d*(?:\.\d+)?[sdifuxXcp@%]',      # printf %s %d %1$s %.2f
    r'\\[A-Za-z]+\[[^\]\n]*\]',                           # RPG Maker \C[2] \N[1] \V[3]
    r'\\[A-Za-z{}.|!<>^$]',                               # RPG Maker \G \{ \. \| \! ...
]
_PAIR_RE = re.compile(r'^(?:<(/?)([A-Za-z][\w-]*)[^>]*>|\{(/?)([A-Za-z][\w-]*)[^}]*\})$')


class Unit:
    """A visual unit: a protected tag, or a base character + its marks."""
    __slots__ = ('text', 'is_tag', 'bidi', 'state', 'is_state')

    def __init__(self, text, is_tag=False):
        self.text = text
        self.is_tag = is_tag
        self.bidi = None
        self.state = None
        self.is_state = False

    def __repr__(self):
        return ('T' if self.is_tag else 'U') + repr(self.text)


def tokenize(text, tag_re):
    toks = []
    pos = 0
    if tag_re is not None:
        for m in tag_re.finditer(text):
            toks.extend(('ch', c) for c in text[pos:m.start()])
            toks.append(('tag', m.group(0)))
            pos = m.end()
    toks.extend(('ch', c) for c in text[pos:])
    return toks


# --------------------------------------------------------------------------
# Shaping (logical order in, logical order out)
# --------------------------------------------------------------------------
def shape_tokens(toks, harakat='keep'):
    n = len(toks)
    jt = ['T' if k == 'tag' else joining_type(c) for k, c in toks]

    def prev_j(i):
        j = i - 1
        while j >= 0 and jt[j] == 'T':
            j -= 1
        return j

    def next_j(i):
        j = i + 1
        while j < n and jt[j] == 'T':
            j += 1
        return j if j < n else -1

    out = []
    consumed = set()
    for i, (kind, c) in enumerate(toks):
        if i in consumed:
            continue
        if kind == 'tag':
            out.append(('tag', c))
            continue
        if c in (ZWJ, ZWNJ) or c in BIDI_CONTROLS:
            continue                                   # used for context, then dropped
        if is_arabic_mark(c):
            if harakat == 'strip' or (harakat == 'shadda' and c != SHADDA):
                continue
            out.append(('ch', c))
            continue
        t = jt[i]
        if t not in ('D', 'R'):
            out.append(('ch', c))
            continue
        p = prev_j(i)
        joins_prev = p != -1 and jt[p] in ('D', 'C')
        if c == LAM:
            q = next_j(i)
            if q != -1 and toks[q][0] == 'ch' and toks[q][1] in LAM_ALEF:
                lig = LAM_ALEF[toks[q][1]].get('fin' if joins_prev else 'iso')
                if lig:
                    out.append(('ch', lig))
                    consumed.add(q)
                    continue
        q = next_j(i)
        joins_next = t == 'D' and q != -1 and jt[q] in ('D', 'R', 'C')
        form = ('med' if joins_next else 'fin') if joins_prev else ('ini' if joins_next else 'iso')
        f = FORMS.get(c, {})
        fallback = {'med': ('fin', 'ini', 'iso'), 'ini': ('iso',), 'fin': ('iso',), 'iso': ()}[form]
        g = f.get(form)
        for alt in fallback:
            if g:
                break
            g = f.get(alt)
        out.append(('ch', g or c))
    return out


def shape(text, harakat='keep', tag_re=None):
    """Logical text -> logical text in presentation forms."""
    return ''.join(c for _, c in shape_tokens(tokenize(text, tag_re), harakat))


# --------------------------------------------------------------------------
# Bidi (simplified UBA, enough for game strings: one paragraph per line)
# --------------------------------------------------------------------------
def to_units(toks):
    units = []
    for kind, c in toks:
        if kind == 'tag':
            units.append(Unit(c, True))
        elif units and not units[-1].is_tag and unicodedata.category(c) in ('Mn', 'Me') \
                and unicodedata.category(units[-1].text[0]) not in ('Zs',):
            units[-1].text += c                         # mark stays with its base
        else:
            units.append(Unit(c))
    return units


def _strong(cls):
    return cls in ('L', 'R')


def resolve_levels(units, base):
    # initial classes
    for u in units:
        if u.is_tag:
            u.bidi = 'ON'
        else:
            b = unicodedata.bidirectional(u.text[0]) or 'ON'
            u.bidi = {'NSM': 'ON', 'BN': 'ON', 'B': 'WS', 'S': 'WS',
                      'LRE': 'ON', 'RLE': 'ON', 'PDF': 'ON', 'LRO': 'ON', 'RLO': 'ON',
                      'LRI': 'ON', 'RLI': 'ON', 'FSI': 'ON', 'PDI': 'ON'}.get(b, b)
    cls = [u.bidi for u in units]
    n = len(cls)
    if base == 'auto':
        first = next((c for c in cls if c in ('L', 'R', 'AL')), 'R')
        base = 'ltr' if first == 'L' else 'rtl'
    base_level = 1 if base == 'rtl' else 0
    sos = 'R' if base_level else 'L'
    # W2: EN after AL -> AN ; W3: AL -> R
    last = sos
    for i, c in enumerate(cls):
        if c in ('L', 'R', 'AL'):
            last = c
        elif c == 'EN' and last == 'AL':
            cls[i] = 'AN'
    cls = ['R' if c == 'AL' else c for c in cls]
    # W4: single separator between numbers
    for i in range(1, n - 1):
        if cls[i] == 'ES' and cls[i - 1] == 'EN' and cls[i + 1] == 'EN':
            cls[i] = 'EN'
        elif cls[i] == 'CS' and cls[i - 1] == cls[i + 1] and cls[i - 1] in ('EN', 'AN'):
            cls[i] = cls[i - 1]
    # W5: ET next to EN -> EN
    i = 0
    while i < n:
        if cls[i] == 'ET':
            j = i
            while j < n and cls[j] == 'ET':
                j += 1
            if (i > 0 and cls[i - 1] == 'EN') or (j < n and cls[j] == 'EN'):
                for k in range(i, j):
                    cls[k] = 'EN'
            i = j
        else:
            i += 1
    # W6: remaining separators -> ON ; W7: EN after L -> L
    cls = ['ON' if c in ('ES', 'ET', 'CS') else c for c in cls]
    last = sos
    for i, c in enumerate(cls):
        if c in ('L', 'R'):
            last = c
        elif c == 'EN' and last == 'L':
            cls[i] = 'L'
    # N1/N2: neutrals take surrounding direction (numbers count as R) else base
    def dir_of(c):
        return 'R' if c in ('R', 'EN', 'AN') else ('L' if c == 'L' else None)
    i = 0
    while i < n:
        if dir_of(cls[i]) is None:
            j = i
            while j < n and dir_of(cls[j]) is None:
                j += 1
            before = dir_of(cls[i - 1]) if i > 0 else sos
            after = dir_of(cls[j]) if j < n else sos
            d = before if before == after else sos
            for k in range(i, j):
                cls[k] = d
            i = j
        else:
            i += 1
    # I1/I2: implicit levels
    levels = []
    for c in cls:
        if base_level == 0:
            levels.append(0 if c == 'L' else (1 if c == 'R' else 2))
        else:
            levels.append(1 if c == 'R' else 2)
    # L1: trailing whitespace -> base level
    k = n - 1
    while k >= 0 and (units[k].is_tag or units[k].text.isspace()):
        if units[k].text.isspace():
            levels[k] = base_level
        k -= 1
    return levels, base_level


def reorder(units, levels):
    order = list(range(len(units)))
    if not units:
        return order
    hi = max(levels)
    odd = [l for l in levels if l % 2]
    if not odd:
        return order
    lowest_odd = min(odd)
    for lvl in range(hi, lowest_odd - 1, -1):
        i = 0
        n = len(order)
        while i < n:
            if levels[order[i]] >= lvl:
                j = i
                while j < n and levels[order[j]] >= lvl:
                    j += 1
                order[i:j] = order[i:j][::-1]
                i = j
            else:
                i += 1
    return order


def _marks_first(text):
    """base+marks -> marks+base. Zero-width Arabic marks are drawn to the right of the pen,
    so in left-to-right visual order they must come BEFORE their letter."""
    if len(text) > 1 and unicodedata.category(text[1]) in ('Mn', 'Me'):
        return text[1:] + text[0]
    return text


def visual_line(units, base, state_family=None, marks='before'):
    """Logical units of ONE line -> visual string (left-to-right)."""
    if not units:
        return ''
    levels, _ = resolve_levels(units, base)
    order = reorder(units, levels)
    # pair tags (<b>..</b>, {i}..{/i}) in logical order
    stacks, pairs = {}, []
    for idx, u in enumerate(units):
        if not u.is_tag or u.is_state:
            continue
        m = _PAIR_RE.match(u.text)
        if not m:
            continue
        closing = (m.group(1) or m.group(3)) == '/'
        name = (m.group(2) or m.group(4)).lower()
        if not closing:
            stacks.setdefault(name, []).append(idx)
        elif stacks.get(name):
            pairs.append((stacks[name].pop(), idx))
    texts = [units[i].text if units[i].is_tag or marks != 'before' else _marks_first(units[i].text)
             for i in order]
    pos = {u_idx: v for v, u_idx in enumerate(order)}
    for o, c in pairs:
        vo, vc = pos[o], pos[c]
        if vo > vc:
            texts[vo], texts[vc] = texts[vc], texts[vo]
    # mirror brackets that ended up in RTL runs
    for v, u_idx in enumerate(order):
        u = units[u_idx]
        if not u.is_tag and levels[u_idx] % 2 and u.text in MIRROR:
            texts[v] = MIRROR[u.text]
    if state_family is None:
        return ''.join(texts)
    # re-emit state codes (e.g. RPG Maker \C[n]) in visual order
    fam = state_family
    out, cur = [], fam['start']
    for v, u_idx in enumerate(order):
        u = units[u_idx]
        if u.is_state:
            continue
        if not u.is_tag and not u.text.isspace() and u.state != cur:
            out.append(fam['make'](u.state))
            cur = u.state
        out.append(texts[v])
    if cur != fam['end']:
        out.append(fam['make'](fam['end']))
    return ''.join(out)


# --------------------------------------------------------------------------
# Wrapping (logical, before reorder)
# --------------------------------------------------------------------------
class Measurer:
    def __init__(self, chars=None, px=None, font=None, size=None):
        self.chars, self.px = chars, px
        self.font = None
        if px:
            from PIL import ImageFont
            self.font = ImageFont.truetype(font, size, layout_engine=ImageFont.Layout.BASIC)

    @property
    def limit(self):
        return self.px or self.chars

    def width(self, units):
        visible = ''.join(u.text for u in units if not u.is_tag and not u.is_state)
        if self.font is not None:
            return self.font.getlength(visible)
        return sum(1 for ch in visible if unicodedata.category(ch) not in ('Mn', 'Me', 'Cf'))


def wrap_units(units, meas):
    """Greedy word wrap on spaces. Returns list of unit lists."""
    words, cur = [], []
    for u in units:
        if not u.is_tag and u.text == ' ':
            words.append(cur)
            cur = []
        else:
            cur.append(u)
    words.append(cur)
    lines, line = [], []
    for w in words:
        cand = line + ([Unit(' ')] if line else []) + w
        if line and meas.width(cand) > meas.limit:
            lines.append(line)
            line = list(w)
        else:
            line = cand
    lines.append(line)
    return lines


# --------------------------------------------------------------------------
# Public pipeline
# --------------------------------------------------------------------------
DEFAULT_NEWLINES = ('\r\n', '\n', '\\n')   # real newlines + the literal two characters \n


class Shaper:
    def __init__(self, mode='visual', base='rtl', harakat='keep', tag_patterns=None,
                 state_code=None, state_default=None, newline_tokens=DEFAULT_NEWLINES,
                 measurer=None, normalize_persian=False, wrap_sep='\n', marks='before'):
        pats = list(tag_patterns if tag_patterns is not None else DEFAULT_TAG_PATTERNS)
        self.state_re = re.compile(state_code) if state_code else None
        if self.state_re is not None:
            pats.insert(0, state_code)
        newlines = sorted({t for t in newline_tokens if t}, key=len, reverse=True)
        self.nl_re = re.compile('(' + '|'.join(re.escape(t) for t in newlines) + ')') if newlines else None
        self.tag_re = re.compile('|'.join('(?:%s)' % p for p in pats)) if pats else None
        self.mode, self.base, self.harakat = mode, base, harakat
        self.state_default = state_default
        self.meas = measurer
        self.normalize_persian = normalize_persian
        self.wrap_sep = wrap_sep
        self.marks = marks

    def _wrap_logical(self, text):
        """Greedy wrap of logical text; widths measured on the shaped glyphs (spaces break joining,
        so shaping each word alone gives the same glyphs as in context)."""
        words = text.split(' ')
        def width(t):
            return self.meas.width(to_units(shape_tokens(tokenize(t, self.tag_re), self.harakat)))
        lines, cur = [], ''
        for w in words:
            cand = (cur + ' ' + w) if cur else w
            if cur and width(cand) > self.meas.limit:
                lines.append(cur)
                cur = w
            else:
                cur = cand
        lines.append(cur)
        return self.wrap_sep.join(lines)

    def _state_family(self, units):
        """Mark state-code units, give every unit its active state."""
        if self.state_re is None:
            return None
        tmpl = None
        cur = self.state_default
        start = cur
        for u in units:
            m = self.state_re.fullmatch(u.text) if u.is_tag else None
            if m:
                u.is_state = True
                cur = m.group(1)
                if tmpl is None:
                    tmpl = (u.text[:m.start(1)], u.text[m.end(1):])
            u.state = cur
        if tmpl is None:
            for u in units:
                u.is_state = False
            return None
        return {'start': start, 'end': cur,
                'make': lambda v, t=tmpl: '' if v is None else t[0] + v + t[1]}

    def process(self, text):
        """One game string (may contain several lines) -> converted string."""
        if self.normalize_persian:
            text = ''.join(PERSIAN_TO_ARABIC.get(c, c) for c in text)
        parts = self.nl_re.split(text) if self.nl_re else [text]
        segs, seps = parts[0::2], parts[1::2]
        if self.mode == 'wrap':
            if not self.meas:
                raise ValueError('wrap mode needs --wrap-px/--wrap-chars')
            out = []
            for i, s in enumerate(segs):
                out.append(self._wrap_logical(s))
                if i < len(seps):
                    out.append(seps[i])
            return ''.join(out)
        seg_units = []
        for s in segs:
            toks = tokenize(s, self.tag_re)
            if self.mode in ('visual', 'forms'):
                toks = shape_tokens(toks, self.harakat)
            seg_units.append(to_units(toks))
        # state codes are tracked across the whole string (they survive line breaks)
        fam = self._state_family([u for us in seg_units for u in us])
        carry = fam['start'] if fam else None
        out = []
        for i, us in enumerate(seg_units):
            lines = wrap_units(us, self.meas) if self.meas else [us]
            rendered = []
            for ln in lines:
                if self.mode == 'forms':
                    rendered.append(''.join(u.text for u in ln))
                elif fam:
                    end = ln[-1].state if ln else carry
                    rendered.append(visual_line(ln, self.base, dict(fam, start=carry, end=end), self.marks))
                    carry = end
                else:
                    rendered.append(visual_line(ln, self.base, None, self.marks))
            out.append(self.wrap_sep.join(rendered))
            if i < len(seps):
                out.append(seps[i])
        return ''.join(out)


def explain(s):
    rows = []
    for ch in s:
        try:
            name = unicodedata.name(ch)
        except ValueError:
            name = '?'
        rows.append('U+%04X  %s  %s' % (ord(ch), ch if ch.isprintable() else ' ', name))
    return '\n'.join(rows)


# --------------------------------------------------------------------------
# Self test
# --------------------------------------------------------------------------
def selftest():
    S = Shaper()
    cases = [
        ('سلام', '\ufee1\ufefc\ufeb3'),                         # lam-alef ligature (final)
        ('لا', '\ufefb'),                                       # lam-alef isolated
        ('بيت', '\ufe96\ufef4\ufe91'),
        ('ـبـ', '\u0640\ufe92\u0640'),                          # tatweel forces medial
        ('مرحبا 123', '123 \ufe8e\ufe92\ufea3\ufeae\ufee3'),
        ('(نعم)', '(\ufee2\ufecc\ufee7)'),                      # brackets mirrored
        ('<b>بك</b> هنا', '\ufe8e\ufee8\ufeeb <b>\ufeda\ufe91</b>'),   # tags re-paired
        ('اسمي {0}!', '!{0} \ufef2\ufee4\ufeb3\ufe8d'),
        ('Level 5 مستوى', '\ufeef\ufeee\ufe98\ufeb4\ufee3 Level 5'),    # و does not join forward
        ('<color=red>ب</color>ك', '\ufeda<color=red>\ufe91</color>'),   # joins across a tag
    ]
    ok = True
    for src, want in cases:
        got = S.process(src)
        if got != want:
            ok = False
            print('FAIL %r\n  got  %s\n  want %s' % (src, ' '.join('%04X' % ord(c) for c in got),
                                                     ' '.join('%04X' % ord(c) for c in want)))
    # forms mode keeps logical order
    if Shaper(mode='forms').process('سلام') != '\ufeb3\ufefc\ufee1':
        ok = False
        print('FAIL forms mode')
    # state codes (RPG Maker colour) follow their words
    st = Shaper(state_code=r'\\C\[(\d+)\]', state_default='0')
    got = st.process('أ \\C[2]ب\\C[0] ج')
    want = '\ufe9d \\C[2]\ufe8f \\C[0]\ufe83'
    if got != want:
        ok = False
        print('FAIL state codes: %r != %r' % (got, want))
    # harakat go before their letter in visual mode
    if Shaper().process('ب\u064e') != '\u064e\ufe8f':
        ok = False
        print('FAIL marks order')
    # wrap mode keeps logical text
    w = Shaper(mode='wrap', measurer=Measurer(chars=8)).process('اهلا بك يا صديقي')
    if w != 'اهلا بك\nيا صديقي':
        ok = False
        print('FAIL wrap mode: %r' % w)
    # multi-line: line order preserved
    if Shaper().process('أ\nب') != '\ufe83\n\ufe8f':
        ok = False
        print('FAIL multiline')
    print('selftest: %s (%d forms, %d lam-alef)' % ('OK' if ok else 'FAILED', len(FORMS), len(LAM_ALEF)))
    return ok


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8')
        except Exception:
            pass
    ap = argparse.ArgumentParser(description='Arabic pre-shaper + bidi reorder for game text.')
    ap.add_argument('text', nargs='*', help='text to process (or use -i / --csv / --json)')
    ap.add_argument('-i', '--input', help='UTF-8 text file, processed line by line')
    ap.add_argument('-o', '--output', help='output file (default: stdout)')
    ap.add_argument('--csv', help='CSV/TSV file; process one column')
    ap.add_argument('--column', help='column name (or 0-based index) for --csv')
    ap.add_argument('--delimiter', default=None, help='CSV delimiter (auto-detect if omitted)')
    ap.add_argument('--json', help='JSON file; process string values')
    ap.add_argument('--json-key-re', help='only process values whose key matches this regex')
    ap.add_argument('--mode', choices=['visual', 'forms', 'reorder', 'wrap'], default='visual')
    ap.add_argument('--base', choices=['rtl', 'ltr', 'auto'], default='rtl')
    ap.add_argument('--harakat', choices=['keep', 'strip', 'shadda'], default='keep')
    ap.add_argument('--marks', choices=['before', 'after'], default='before',
                    help='visual mode: put harakat before (default, right for most fonts) or after their letter')
    ap.add_argument('--tag', action='append', default=[], help='extra regex for protected tokens')
    ap.add_argument('--no-default-tags', action='store_true')
    ap.add_argument('--state-code', help=r'regex with one group for state codes, e.g. "\\C\[(\d+)\]"')
    ap.add_argument('--state-default', help='state assumed at the start of each string, e.g. 0')
    ap.add_argument('--newline-token', action='append', default=None,
                    help='line separator inside a string (default: real newline). Repeatable, '
                         'e.g. --newline-token "\\n" --newline-token "<br>"')
    ap.add_argument('--wrap-sep', default=None,
                    help='line separator inserted by wrapping (default: first --newline-token, else newline)')
    ap.add_argument('--wrap-chars', type=int, help='wrap lines to N visible characters')
    ap.add_argument('--wrap-px', type=int, help='wrap lines to N pixels (needs --font --size)')
    ap.add_argument('--font', help='TTF/OTF used for --wrap-px measuring')
    ap.add_argument('--size', type=int, help='font size in px for --wrap-px')
    ap.add_argument('--normalize-persian', action='store_true', help='ی->ي, ک->ك before shaping')
    ap.add_argument('--explain', action='store_true', help='print code points of the result')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args(argv)

    if a.selftest:
        return 0 if selftest() else 1

    meas = None
    if a.wrap_px:
        if not (a.font and a.size):
            ap.error('--wrap-px needs --font and --size')
        meas = Measurer(px=a.wrap_px, font=a.font, size=a.size)
    elif a.wrap_chars:
        meas = Measurer(chars=a.wrap_chars)
    newlines = a.newline_token if a.newline_token is not None else list(DEFAULT_NEWLINES)
    tags = ([] if a.no_default_tags else list(DEFAULT_TAG_PATTERNS)) + a.tag
    sh = Shaper(mode=a.mode, base=a.base, harakat=a.harakat, tag_patterns=tags,
                state_code=a.state_code, state_default=a.state_default,
                newline_tokens=newlines, measurer=meas, normalize_persian=a.normalize_persian,
                wrap_sep=a.wrap_sep if a.wrap_sep is not None else (newlines[0] if a.newline_token else '\n'),
                marks=a.marks)

    out = io.StringIO()
    if a.csv:
        with open(a.csv, encoding='utf-8-sig', newline='') as f:
            data = f.read()
        delim = a.delimiter or ('\t' if a.csv.lower().endswith(('.tsv', '.tab')) else
                                csv.Sniffer().sniff(data[:4096], delimiters=',;\t|').delimiter)
        rows = list(csv.reader(io.StringIO(data), delimiter=delim))
        if not rows:
            return 0
        if a.column is None:
            ap.error('--csv needs --column')
        col = int(a.column) if a.column.isdigit() else rows[0].index(a.column)
        start = 0 if a.column.isdigit() else 1
        for r in rows[start:]:
            if col < len(r) and r[col]:
                r[col] = sh.process(r[col])
        csv.writer(out, delimiter=delim, lineterminator='\n').writerows(rows)
    elif a.json:
        with open(a.json, encoding='utf-8-sig') as f:
            data = json.load(f)
        key_re = re.compile(a.json_key_re) if a.json_key_re else None

        def walk(o, key=None):
            if isinstance(o, dict):
                return {k: walk(v, k) for k, v in o.items()}
            if isinstance(o, list):
                return [walk(v, key) for v in o]
            if isinstance(o, str) and (key_re is None or (key is not None and key_re.search(str(key)))):
                return sh.process(o)
            return o
        json.dump(walk(data), out, ensure_ascii=False, indent=1)
        out.write('\n')
    elif a.input:
        with open(a.input, encoding='utf-8-sig') as f:
            for line in f.read().split('\n'):
                out.write(sh.process(line) + '\n')
    else:
        text = ' '.join(a.text) if a.text else sys.stdin.read().rstrip('\n')
        res = sh.process(text)
        out.write((explain(res) if a.explain else res) + '\n')

    if a.output:
        os.makedirs(os.path.dirname(os.path.abspath(a.output)), exist_ok=True)
        with open(a.output, 'w', encoding='utf-8', newline='') as f:
            f.write(out.getvalue())
    else:
        sys.stdout.write(out.getvalue())
    return 0


if __name__ == '__main__':
    sys.exit(main())
