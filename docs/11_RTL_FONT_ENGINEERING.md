# 11 — هندسة العرض العربي والخطوط

الحالة (2026-11-05): **خط البناء كاملاً جاهز ومختبر خارج اللعبة؛ ينتظر الاختبار داخل اللعبة (L4).**

## ما هو مؤكد
- ملفات STRINGS بترميز UTF-8 ← الحروف العربية تصل إلى المحرك.
- لا خط عربي في `fonts_*.swf`؛ Scaleform لا يشكّل العربية ([Autodesk](https://help.autodesk.com/cloudhelp/ENU/Scaleform-Help/scaleform_help/font/right_left_text.html)).
- المشاريع المنشورة تترك اللفّ للمحرك، فتنكسر الأسطر الطويلة وتنقلب ([173078](https://www.nexusmods.com/skyrimspecialedition/mods/173078)).
- حقول النص الفعلية مقاسة من SWF (`08_qa/reports/swf_text_fields.json`، 187 حقلاً)، وكلها HTML.

## الخط (`04_fonts/`)
| الخط المنطقي في fontconfig | الخط العربي | المصدر |
|---|---|---|
| `$EverywhereFont`, `$DialogueFont`, `$StartMenuFont`, `$EverywhereMediumFont` | SkyrimArabic UI (Cairo 400) | OFL |
| `$EverywhereBoldFont` | SkyrimArabic UI Bold (Cairo 700، اسم مستقل بلا علم Bold حتى لا يطبّق Scaleform تعريضاً صناعياً يطمس النقاط) | OFL |
| `$SkyrimBooks` | SkyrimArabic Book (Amiri Regular) | OFL |
| `$HandwrittenFont`, `$HandwrittenBold` | SkyrimArabic Hand (Amiri Bold) — مؤقت | OFL |
| خطوط الرموز (Dragon_script، Daedric، Dwemer، Falmer، الأزرار، CClub) | بلا تغيير من `fonts_en.swf` | — |

- `font_prepare.py`: يثبّت محاور الخط المتغير، ويعيد تسمية العائلة، ويوجّه كل خانة presentation form إلى الشكل الذي يولّده **GSUB الخط نفسه** عبر HarfBuzz. السبب: رسوم هذه الخانات في Cairo قديمة، بوزن خاطئ وأحجام صغيرة («دو» و«م»)، وقد رأيت ذلك في المعاينة الأولى قبل الإصلاح.
- `swf_font.py`: يكتب `fonts_ar.swf` (DefineFont3 + DefineFontName + DefineEditText + PlaceObject2) مباشرة من خطوط TTF. منحنيات TrueType التربيعية تنتقل كما هي إلى منحنيات SWF.
- **تحقق مستقل:** FFDec 26.4.0 قرأ الملف ورسم نصاً عربياً مُشكَّلاً مسبقاً، فظهر متصلاً وبالترتيب الصحيح (`08_qa/render_tests/zoom_all.png`).

## التحويل (`arabic.py`)
نص منطقي ← تشكيل ← **لفّ بالبكسل بخط القياس نفسه** وبعرض الحقل × 0.92 ← حجز عرض للمتغيرات وقت التشغيل (`<Alias>`, `<mag>`, `%d`…) ← ترتيب مرئي لكل سطر ← فواصل `\n` صريحة. الوسوم محمية، و`<p align="right">` اختياري لحقول HTML.

- أداة التشكيل والاتجاه مأخوذة من مهارة game-arabization (`05_tools/vendor/ar_shape.py`، مع بصمة المصدر).
- **ترتيب bidi مطابق لمرجع مستقل** (python-bidi + arabic-reshaper) في 8 حالات، منها الأرقام و`%` والإنجليزي والأقواس ولام-ألف.

## الأدلة حتى الآن
| المستوى | الدليل | النتيجة |
|---|---|---|
| L1 | 20 اختباراً (منها مقارنة bidi، حفظ الوسوم، العرض ≤ الحد، تغطية الخط لكل حرف في الحزمة) | ناجحة |
| L3 | معاينة تحاكي Scaleform (`08_qa/render_tests/preview/`) | A سليم؛ B ينقلب ترتيب أسطره كما في المشاريع الحالية |
| L4 | داخل اللعبة | **لم يُجرَ بعد** — `08_qa/render_tests/IN_GAME_TEST_AR.md` |

## أسئلة مفتوحة يحسمها L4
1. هل تحترم الحقول `\n` الصريح؟ (المتوقع نعم)
2. هل يقلب `<p align="right">` المحاذاة في القوائم اليسارية (الحوار، الدفتر، الكتب)؟
3. التنوين على الألف في Cairo يشبه الهمزة ← حذف التنوين في الواجهة أم إبقاؤه؟
4. هل الحجوم والقص مقبولة؟ وهل يُرسم الخط المصدَّر في كل القوائم؟
5. عرض بطاقة العنصر (item_card) غير مقاس بعد (400px تقدير).

## المسار B (SKSE) يبقى احتياطياً
لا يُفتح إلا إذا فشل المسار A في سؤال 1 أو 2.
