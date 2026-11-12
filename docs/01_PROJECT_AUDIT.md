# 01 — تدقيق المشروع والبيئة

> تاريخ الفحص: 2026-11-05 · نوع الفحص: قراءة فقط · لم يُعدَّل أي ملف داخل مجلد اللعبة.
> الدليل الآلي: `00_baseline/hashes.json`، `01_original/1.7.104.0/manifest.json`، `08_qa/reports/roundtrip_1.7.104.0.txt`، `08_qa/reports/coverage_baseline.json`.

## 1. اللعبة

| البند | القيمة | المصدر |
|---|---|---|
| المسار | `C:\Program Files (x86)\Steam\steamapps\common\Skyrim Special Edition` | — |
| الإصدار التنفيذي | `SkyrimSE.exe` 1.7.104.0 (SHA-256 `846efccf…1402f`) | VersionInfo + baseline |
| Steam | appid 489830، build 24914197، depots 489831/489832/489833، لغة english | `appmanifest_489830.acf` |
| النسخة | Special Edition + 4 محتويات CC مجانية (ليست Anniversary Edition) | `Skyrim.ccc` يذكر 74، المثبت 4 |
| عدد ملفات اللعبة | 46 ملفاً، 16.09 GB | baseline |
| تشغيل سابق | لا (`LastPlayed=0`، مجلد Saves فارغ، لا `plugins.txt`) | — |
| مودات / SKSE / ENB | لا يوجد | فحص المجلدات |

## 2. الملحقات

| الملحق | النوع | Localized | السجلات | Masters |
|---|---|---|---|---|
| Skyrim.esm | ESM | نعم | 920,181 | — |
| Update.esm | ESM | نعم | 21,385 | Skyrim |
| Dawnguard.esm | ESM | نعم | 103,755 | Skyrim, Update |
| HearthFires.esm | ESM | نعم | 19,262 | Skyrim, Update |
| Dragonborn.esm | ESM | نعم | 251,499 | Skyrim, Update |
| _ResourcePack.esl | ESL | نعم | 388 | Skyrim, Update, HearthFires |
| ccBGSSSE001-Fish.esm (Fishing) | ESM | نعم | 7,679 | الخمسة |
| ccBGSSSE025-AdvDSGS.esm (Saints & Seducers) | ESM | نعم | 3,183 | الخمسة |
| ccBGSSSE037-Curios.esl (Rare Curios) | ESL | نعم | 166 | الخمسة |
| ccQDRSSE001-SurvivalMode.esl | ESL | نعم | 699 | الخمسة |

**نتيجة جوهرية:** كل الملحقات Localized ← النص في ملفات STRINGS وحدها، ولا يلزم تعديل أي ESM/ESP للترجمة.

## 3. النصوص

- 30 ملف STRINGS إنجليزي (10 ملحقات × 3 أنواع) داخل BSA غير مضغوطة؛ استُخرجت إلى `01_original/1.7.104.0/strings/` للقراءة فقط.
- **roundtrip: 30/30 مطابق بايت-ببايت** بأداة `05_tools/skyrim_l10n/strings_io.py` (7 اختبارات ناجحة).
- الترميز UTF-8 لكل القيم (اختبار آلي على كل السطور).

| المقياس | القيمة |
|---|---|
| مدخلات | 92,751 |
| غير فارغة | 92,360 |
| كلمات | 1,253,078 |
| نصوص فريدة | 74,088 |
| نصوص مكررة أكثر من مرة | 7,270 |
| مدخلات فيها وسوم/متغيرات محمية | 3,095 |
| مفاتيح واجهة `translate_english.txt` | 861 |

حسب الملحق (غير الفارغة / الكلمات):

| الملحق | strings | dlstrings | ilstrings |
|---|---|---|---|
| skyrim | 30,288 / 114,243 | 2,668 / 408,903 | 34,225 / 442,571 |
| update | 1,132 / 3,971 | 298 / 18,198 | 152 / 2,195 |
| dawnguard | 3,655 / 14,717 | 454 / 19,753 | 4,020 / 47,464 |
| hearthfires | 1,536 / 5,426 | 29 / 3,357 | 708 / 8,009 |
| dragonborn | 5,273 / 21,431 | 628 / 52,587 | 5,086 / 59,733 |
| _resourcepack | 27 / 36 | 0 | 0 |
| fish | 808 / 3,316 | 219 / 14,090 | 0 |
| advdsgs | 394 / 1,635 | 73 / 6,373 | 10 / 10 |
| curios | 79 / 187 | 2 / 17 | 0 |
| survivalmode | 477 / 1,729 | 119 / 3,126 | 0 |

## 4. الوسوم والمتغيرات (يجب حفظها حرفياً)

`[pagebreak]` 1553 · `<p …>` 1352 · `<font …>` 1092 · `<Alias=…>` 880 · `<img …>` 511 · `<mag>` 492 · `<Global=…>` 330 · `<dur>` 327 · `<br>` 262 · `<b>` 240 · `<Alias.ShortName=…>` 170 · `<Alias.PronounObj=…>` 43 · `<Alias.Pronoun…>` · `<BribeCost>` 46 · `%.0f` 45 · `%s` 24 · `%d` 15 · قيم رقمية `<25>`, `<50>`…

## 5. الواجهة والخطوط

- `interface/fontconfig.txt`: `fonts_console.swf` + `fonts_en.swf` + `fonts_cclub.swf`؛ الخطوط المنطقية `$EverywhereFont`, `$EverywhereBoldFont`, `$EverywhereMediumFont`, `$DialogueFont`, `$StartMenuFont`, `$SkyrimBooks`, `$HandwrittenFont`, `$HandwrittenBold`, `$CClub_Font` وغيرها، و`validNameChars` لاتيني فقط.
- لا يوجد أي خط عربي في اللعبة.
- 54 ملف SWF للقوائم (dialoguemenu, bookmenu, quest_journal, inventorymenu, magicmenu, statsmenu, hudmenu…).

## 6. سكربتات Papyrus

14,026 ملف `.pex` داخل `Skyrim - Misc.bsa` — لم تُفحص نصوصها بعد (مرحلة لاحقة).

## 7. الأدوات على الجهاز

موجود: Python 3.12.10، Git، 7-Zip. غير موجود: xTranslator، SSEEdit، BSArch/BAE، JPEXS FFDec، Java، Champollion، Mod Organizer 2، Vortex، Creation Kit، SKSE.

## 8. ملاحظات مخاطرة

- مجلد المشروع داخل OneDrive: البيانات الحالية صغيرة (≈ 12 MB)، لكن أي استخراج أكبر يجب أن يكون خارج المزامنة.
- الإصدار 1.7.104 صدر في 27 أغسطس 2026؛ مشاريع التعريب المنشورة مبنية على 1.6.1170.
- مثال مبكر على النصوص المتعددة المعنى: «Mine» يظهر 588 مرة في `.strings` (**تأكد بعد الربط:** 587 منها نص تفاعل `ACTI.RNAM` على عروق الخام — فعل «استخرج/عدّن» لا ضمير الملكية) — لذلك الترجمة بالسياق لا بالنص وحده.
