# 03 — بنية الاستخراج

## الخط

```
Game Data (read-only)
  └─ BSA v105 ──bsa.py──► 01_original/1.7.104.0/{strings,interface}  (read-only + manifest.json SHA-256)
                              └─ strings_io.py roundtrip (30/30 byte-identical)
                              └─ inventory.py ──► 03_translation/db/l10n.sqlite
                                                    source_strings / interface_strings / translations / qa_results
  └─ ESM/ESL ──esm.py + link.py (done, 100% linked)──► record_type, form_id, editor_id, field, quest, speaker, conditions
                └─ verified against xDump (xEdit 4.1.5f): tests/xdump_crosscheck.py
  └─ scripts/*.pex ──Champollion (pending)──► player-visible Papyrus literals
  └─ interface/*.swf ──FFDec (pending)──► hard-coded UI text and text field sizes
```

## المفتاح الثابت

`<plugin>|<kind>|0x<STRING_ID>` مثل `skyrim|ilstrings|0x0001A2B3`. يبقى ثابتاً بين الإصدارات طالما لم تغيّر Bethesda المعرّف؛ `source_sha1` يكشف أي تغيير في النص الأصلي بعد التحديث.

## الأهلية (`eligibility`)

| القيمة | المعنى |
|---|---|
| `PLAYER_VISIBLE` | يُترجم (90,457) |
| `REVIEW_VISIBILITY` | الظهور غير مثبت أو النص يشبه معرّفاً (1,821) — يُحسم داخل اللعبة |
| `LIKELY_HIDDEN` | أسماء مواضيع حوار غير مخصصة (82) |
| `BLOCKED_CONTEXT` | يحتاج تحقيقاً قبل الترجمة (0 حالياً) |
| `EMPTY` | فارغ (391) |

قائمة الحقول المحلية المعتمدة في `link.py → LSTRING_FIELDS` (FULL، DESC، INFO.NAM1/RNAM، QUST.CNAM/NNAM، BOOK.CNAM، NPC_.SHRT، MESG.ITXT، ACTI/FLOR/TACT.RNAM، MGEF.DNAM، WOOP.TNAM، AVIF.ANAM، PERK.EPF2، PERK.EPFD عندما EPFT=7، FACT.MNAM/FNAM، REGN.RDMP، GMST.DATA للإعدادات s*، BPTD.BPTN). استُخرجت بالتجربة لأن أرقام النصوص صغيرة ومتتالية وتتصادم مع حقول عادية لو قُبل أي حقل من 4 بايت.

## الكتابة (لاحقاً)

`StringTable.build()` يبني جداول جديدة بنفس ترتيب المعرّفات؛ المشاركة في الإزاحات تُلغى عند اختلاف الترجمة لسياقين. التحقق بعد البناء: نفس عدد المعرّفات ونفس المجموعة لكل ملف.
