# 02 — سلسلة الأدوات

الحالة (2026-11-05): **أدوات المشروع وأدوات المجتمع مثبتة بشكل محمول في `%USERPROFILE%\SkyrimArabic_Tools` (خارج OneDrive، بلا تعديل للسجل أو PATH). المسارات والإصدارات والبصمات في `05_tools/tool_paths.json`. ينقص xTranslator فقط.**

## التثبيت الفعلي والتحقق

| الأداة | الإصدار | المصدر | تحقق البصمة | تحقق التشغيل |
|---|---|---|---|---|
| xEdit (`xTESEdit64.exe` بالخيار `-sse`) + BSArch + xDump | 4.1.5f / BSArch 0.9c | GitHub TES5Edit/TES5Edit | لا توجد بصمة منشورة؛ الحجم مطابق لـAPI | **xDump قرأ `ccBGSSSE037-Curios.esl` مع ملفاته الأساسية من 1.7.104 وحلّ نصوصه من BSA في 9.7 ثوانٍ** |
| JPEXS FFDec | 26.4.0 | GitHub jindrapetrik/jpexs-decompiler | **مطابقة للبصمة المنشورة** | `--help` يعمل |
| Temurin JRE (محمول) | 21.0.13+9 | GitHub adoptium | **مطابقة للبصمة المنشورة** | `java -version` يعمل |
| Champollion | 1.3.2 | GitHub Orvid/Champollion | لا توجد بصمة منشورة | `--help` يعمل |
| Mod Organizer 2 (محمول) | 2.5.2 | GitHub ModOrganizer2/modorganizer | لا توجد بصمة منشورة | لم يُشغَّل بعد (يحتاج إعداد instance عبر الواجهة) |
| مكتبات Python (venv معزول) | fonttools 4.68.0، uharfbuzz 0.57.0، Pillow 13.0.0، python-bidi 0.6.12، arabic-reshaper 3.1.0، spylls 0.1.7 | PyPI | — | مثبتة |
| قاموس Hunspell العربي (Ayaspell) | LibreOffice/dictionaries master | GitHub | — | الملفات موجودة؛ اختبار spylls عند كتابة فاحص QA |
| **xTranslator** | — | **Nexus فقط (mod 134) — يتطلب تسجيل دخول؛ لا إصدارات على GitHub** | — | **غير مثبت** |

**ملاحظة xDump:** يطبع النص المحلول لا معرّف STRING. ربط المعرّفات بالسجلات سيتم بمحلل ESM خاص بالمشروع (يقرأ المعرّف ذي 4 بايت في الحقول المحلية) مع xDump مرجعاً للتحقق وفك الشروط.

## أدوات المشروع (`05_tools/skyrim_l10n/`)

| الملف | الوظيفة | الحالة |
|---|---|---|
| `baseline.py` | SHA-256 لكل ملفات اللعبة + `--verify` لإثبات عدم التغيير | يعمل (46 ملفاً) |
| `bsa.py` | قراءة/استخراج BSA v104/v105 (قراءة فقط؛ LZ4 اختياري للأرشيفات المضغوطة) | يعمل |
| `strings_io.py` | قراءة/كتابة strings/dlstrings/ilstrings + `roundtrip` | 30/30 مطابق |
| `extract.py` | نسخ الأصول الإنجليزية إلى `01_original/` للقراءة فقط + manifest | يعمل (36 ملفاً) |
| `inventory.py` | قاعدة SQLite للجرد + تقرير تغطية | يعمل (92,751 مدخلاً) |
| `tests/test_strings_io.py` | 7 اختبارات (اصطناعية + كل الأصول) | ناجحة |

## أدوات المجتمع المطلوبة

| الأداة | الدور | متى نحتاجها |
|---|---|---|
| SSEEdit (xEdit) | ربط String ID بالسجل/الحقل/المهمة/المتكلم/الشروط (سكربت تصدير، بدون حفظ) | المرحلة 4 |
| xTranslator | تحقق مستقل من ملفات STRINGS المبنية | قبل كل إصدار |
| JPEXS FFDec + Java | فحص SWF وبناء `fonts_ar.swf` | إثبات العرض |
| Champollion | فك `.pex` لقراءة الإشعارات الثابتة | مرحلة Papyrus |
| Mod Organizer 2 | تثبيت واختبار قابل للإزالة | الاختبار داخل اللعبة |
| BSArch | تغليف BSA اختياري للإصدار | الإصدار |

## مكتبات Python المطلوبة

`fonttools`, `uharfbuzz`, `Pillow`, `python-bidi`, `arabic-reshaper` (للمقارنة فقط)، و`hunspell`/قاموس عربي للتدقيق الإملائي. ستُثبَّت في بيئة افتراضية داخل المشروع (`.venv`) لا على مستوى النظام.

## مبدأ

Python مصدر الحقيقة للبناء؛ xTranslator وxEdit للتحقق والسياق. لا أداة تُستخدم دون `--help` وفحص roundtrip على بياناتنا الفعلية.
