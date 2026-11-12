# 13 — التوافق والتغليف

## الشكل النهائي (مسودة)
```
SkyrimArabic/                       (MO2/Vortex mod root)
  Strings/<plugin>_english.strings|dlstrings|ilstrings   (30 files)
  Interface/fontconfig.txt
  Interface/fonts_ar.swf
  Interface/translate_english.txt
  [optional] SkyrimArabic.esp + SkyrimArabic.bsa  (packed alternative)
  README_AR.md, LICENSES/, manifest.json
```
- يستبدل ملفات `_english` فقط؛ `sLanguage` يبقى ENGLISH والصوت الإنجليزي يعمل.
- الملفات loose تتقدم على BSA تلقائياً؛ الإزالة = تعطيل المود.

## التوافق
| البند | السياسة |
|---|---|
| إصدار اللعبة | `manifest.json` يحمل 1.7.104.0 وsource_sha1 لكل سطر؛ أداة فحص تقارن بعد أي تحديث |
| DLC | الثلاثة مشمولة؛ الملفات لا تُثبت لملحق غير موجود |
| CC | الأربعة المثبتة فقط؛ أي CC آخر خارج النطاق حتى يُثبت |
| مودات أخرى (USSEP…) | خارج النطاق الأول؛ أي مود يستبدل STRINGS أو fontconfig يتعارض ويُوثق |
| Anniversary Edition | غير مثبتة؛ لا ادعاء دعم |

## الأمان
- لا تعديل لأي ملف في مجلد اللعبة، لا EXE ولا DLL.
- `00_baseline/hashes.json` + `--verify` قبل وبعد كل اختبار.
- الإصدار يُبنى من الصفر (`06_build` قابل للحذف) ويُقارن بالإصدار السابق.
