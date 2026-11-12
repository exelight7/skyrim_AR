# skyrim_AR: تعريب Skyrim Special Edition

تعريب كامل لـ Skyrim SE (الإصدار 1.7.104.0) مع الإضافات الثلاث ومحتوى Creation Club (80 ملحقاً).

## الحالة
- **99.66%** من النصوص الظاهرة للاعب مترجمة: 94,063 من 94,384.
- مترجم بالكامل: الواجهة، والحوار، والمهام، والأغراض، والأسماء، والرسائل، وعناوين الكتب.
- الباقي: 322 من نصوص الكتب، وتظهر حالياً بالإنجليزية.
- الحروف متصلة، واتجاه النص من اليمين لليسار، والتشكيل يُعالج وقت البناء. لا يُعدَّل أي ملف EXE أو DLL.

## محتوى المستودع
| المجلد | المحتوى |
|---|---|
| `03_translation/ar/` | الترجمة العربية، ملف TSV لكل ملحق (`key<TAB>arabic`) |
| `03_translation/glossary.*` | المسرد المعتمد للمصطلحات والأسماء |
| `04_fonts/` | خطا Cairo وAmiri (رخصة OFL) وأدوات بناء خط SWF |
| `05_tools/` | أدوات الاستخراج والفحص والبناء والتثبيت (Python وPowerShell) |
| `docs/` | توثيق المشروع: المعمارية، ودليل الأسلوب، وسياسة المصطلحات، وخط الإنتاج |
| `DECISIONS.md` / `STATUS.md` | سجل القرارات وسجل التقدم |

## ما لا يحتويه المستودع
لا يحتوي على أي ملف من ملفات اللعبة، ولا على نصوصها الإنجليزية الأصلية، ولا على ملفات الحزمة المبنية، ولا على تعديلات قوائم الواجهة (لأنها شيفرة Bethesda المفكوكة). هذه كلها ملك لـ Bethesda. لبناء التعريب تحتاج نسختك الخاصة من اللعبة. خطوات الاستخراج والبناء موضّحة في `docs/02_TOOLCHAIN.md` و`docs/09_TRANSLATION_PIPELINE.md`.

## تنبيه توافق
تشحن الحزمة 24 قائمة واجهة SWF معدّلة، فتتعارض مع مودات الواجهة مثل SkyUI.

---

## English
Arabic localization of Skyrim Special Edition 1.7.104.0, including all DLC and Creation Club content (80 plugins). 99.66% of player-visible strings are translated; 322 book texts remain in English. Arabic shaping and RTL ordering are done at build time, with no EXE or DLL patching.

This repo contains only the Arabic translations (`03_translation/ar/`), the glossary, fonts (OFL), tools and docs. It contains no game files and none of Bethesda's original text. You need your own copy of the game to build the mod.

## License
Code: MIT (see `LICENSE`). Fonts: SIL Open Font License (see `04_fonts/src/*/OFL.txt`). Skyrim and its text are the property of Bethesda Softworks.
