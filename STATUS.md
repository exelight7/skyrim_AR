# حالة المشروع — تعريب Skyrim SE 1.7.104.0

آخر تحديث: 2026-11-06

## منجز (بدليل)
- فحص البيئة كاملاً للقراءة فقط ← docs/01_PROJECT_AUDIT.md
- بصمات SHA-256 لـ46 ملفاً (16.09 GB) ← 00_baseline/hashes.json
- استخراج 30 ملف STRINGS إنجليزي + ملفات الواجهة والخطوط (36 ملفاً، للقراءة فقط) ← 01_original/1.7.104.0/
- roundtrip مطابق بايت-ببايت 30/30، و7 اختبارات ناجحة
- قاعدة الجرد: 92,751 مدخلاً (92,360 غير فارغ، 74,088 فريد، 1,253,078 كلمة) + 861 مفتاح واجهة
- الوثائق 01–15 (مسودات مبنية على الدليل)

- تثبيت محمول للأدوات خارج OneDrive (xEdit/xDump/BSArch، FFDec، Java، Champollion، MO2، venv، قاموس عربي) ← 05_tools/tool_paths.json

- ربط 92,360/92,360 نصاً بسجله وحقله؛ قاعدة سياق للمهام والحوار والشخصيات؛ مطابقة مستقلة مع xDump (1,896 INFO بلا فروق)؛ 13 اختباراً ناجحاً ← docs/05_QUEST_CONTEXT_SYSTEM.md

- ربط المشاهد والـaliases بالشخصيات: المتكلم معروف بالاسم لـ34,643 سطراً (77.9%)، والمجهول 1,684 فقط (3.8%)؛ مطابقة xDump: 202 مشهد و646 alias بلا فروق؛ 15 اختباراً ناجحاً

- حزمة اختبار العرض العربي جاهزة (07_patch/SkyrimArabic_RenderTest): خط عربي SWF من Cairo وAmiri، وتشكيل ولفّ وقت البناء، و1,906 نصاً اختبارياً، ومعاينة تحاكي Scaleform، و20 اختباراً ناجحاً، وسكربتا تثبيت وإزالة مجرَّبان على مجلد وهمي

- **اختبار داخل اللعبة (لقطات المستخدم):** الحروف متصلة والترتيب صحيح واللف الذي نصنعه محترم. اكتُشف خللان وأُصلحا: سطر جديد داخل translate_english.txt، ووسم المحاذاة يظهر حرفياً.
- **خط الإنتاج يعمل:** تصدير الدفعات ← ترجمة ← فحص آلي (qa.py) ← ذاكرة ترجمة ← بناء ← اختبارات ← تثبيت (Deploy-Arabic.ps1).
- **النطاق الآن 80 ملحقاً** (اللعبة نزّلت محتوى Creation Club كاملاً): 99,012 نصاً، نحو 1.36 مليون كلمة، كلها مربوطة بسياقها.
- **المترجم والمثبت في اللعبة:** الواجهة 861/861، وإعدادات النظام 882، وأسماء الأماكن 2,494، وأسماء الشخصيات والمخلوقات 3,594. المجموع 6,970 نصاً (7.2% من النصوص، ونحو 1% من الكلمات، لأن الأسماء قصيرة).

- **دفعات جديدة مقبولة ومثبتة (2026-11-05):** أسماء المهام 572 وأهدافها 3,079 (B005/B006)، وأسماء الأغراض 10,528 (B007: أسلحة ودروع وجرعات ومفاتيح وطعام وأسماك وأثاث هارثفاير)، وأسماء السحر والمزايا والصيحات والتسحيرات 4,951 (B008).
- **المجموع المقبول الآن:** 25,948 نصاً من 95,085 ظاهراً للاعب (27.3%)، و79,589 كلمة؛ الواجهة 861/861. المثبت في اللعبة: 26,108 نصاً في 80 ملفاً، بلا أي مشكلة بناء، وملفات اللعبة الأصلية لم تتغير (التحقق: changed=[]).
- **دفعات إضافية (2026-11-05):** أسماء الأشياء في العالم والأعراق والفئات والأزرار 5,479 (B009)، وأوصاف التأثيرات والمزايا والأغراض والمهارات والأعراق والصيحات 2,146 (B010) مع الحفاظ على كل `<mag>` و`<dur>` والأرقام.
- **المثبت الآن في اللعبة:** 33,733 نصاً في 113 ملفاً، 20 اختباراً ناجحاً، وملفات اللعبة الأصلية لم تتغير (changed=[]).
- **حماية جديدة:** نصوص وضع النجاة `[SURV=...]` تُبنى مع إبقاء الغلاف في مكانه (فحص CRITICAL جديد).
- **أدوات جديدة:** `compose_items.py` (بناء أسماء «X of Y» بقواعد الإضافة و«ذو/ذات»)، و`visibility_flags.py` (استبعاد 495 اسماً مخفياً بأعلام اللعبة نفسها).

- **دفعات 2026-11-06:** إصلاح الخط العريض المتقطع (خط Bold منفصل)، وتركيب التاريخ، ومذكرات المهام 2,118 (B012)، وشاشات التحميل 380 (B013)، والرسائل ونصوص المساعدة 1,020 + عناوينها وأزرارها (B014)، وعناوين الكتب 1,445 (B015)، وخيارات اللاعب ومواضيع الحوار 7,783 مجموعة / 9,506 نصاً (B016) بمخاطبة حسب جنس المحاوَر.
- **المقبول الآن:** 48,690 من 94,388 (51.6%)، و282,546 كلمة. **المثبت في اللعبة:** 48,853 نصاً في 154 ملفاً، problems=0، والاختبارات ناجحة.
- **المتبقي فئتان فقط:** سطور الحوار المنطوقة 44,259، ونصوص الكتب 1,439 (نحو 500 ألف كلمة).
- **الحوار المنطوق بدأ (B017_mq، المهمة الرئيسية):** 2,640 من 3,978 سطراً مقبولة بلا رفض، مع مخاطبة حسب جنس اللاعب في السطور المشروطة، ولغة التنانين مكتوبة بحروف عربية. المقبول الكلي الآن 51,689 من 94,388 (54.8%)، والمثبت في اللعبة 51,585 نصاً (problems=0).

## التالي (بالترتيب)
1. ✅ أسماء الأماكن والشخصيات (قواعد التسمية في docs/08)
2. ✅ أسماء المهام وأهدافها، وأسماء الأغراض والتعاويذ والمزايا ← ✅ أسماء الأشياء في العالم والأوصاف ← ✅ عناوين الكتب والرسائل وشاشات التحميل ومذكرات المهام وخيارات الحوار
3. الحوار حسب المهام (الرئيسية ← الحرب الأهلية ← النقابات ← الإضافات ← الجانبية)
4. الكتب وشاشات التحميل

## لم يبدأ
البحث القصصي المكتوب (LORE_DATABASE)، وملفات أصوات الشخصيات.

## عوائق
xTranslator يحتاج تنزيلاً يدوياً من Nexus؛ الاختبار داخل اللعبة ينتظر لقطاتك؛ تذكّر إزالة الحزمة بعده.

## 2026-11-06 (later)
- UI font metrics fixed (descender clipping), skill/perk description widths, letterSpacing=0 in 24 menus, subtitle speaker order + Arabic date comma (build_menus.py). Confirmed in-game by user screenshots (clipping/letter spacing).
- B017_mq main quest dialogue: COMPLETE (3,978 groups / 4,533 strings).
- B018_cw civil war dialogue: COMPLETE (1,869 groups / 2,111 strings; 3 developer placeholders skipped).
- Overall: 55,334 / 94,384 player-visible strings accepted (58.6%); 55,497 strings deployed. Target 75% needs ~15,450 more.
- Next: Thieves Guild (TG), College (MG), Companions (C), Dark Brotherhood (DB), then DA/MS, DLC1/DLC2, generic Dialogue.

## 2026-11-06 (75% milestone)
- Completed batches: B019_tg, B020_mg, B021_db, B022_c, B023_da, B024_ms, B025_wi, B026_ff (Favor/Freeform 1,374 groups / 1,496 strings), B027_dr (DialogueRiften 823 / 915).
- B028_dw (DialogueWhiterun): 430 of 755 groups accepted; rows 430-755 still pending.
- Overall: 70,877 / 94,384 player-visible strings accepted (75.09%). Target 75% REACHED.
- Deployed via Deploy-Arabic.ps1: 71,040 strings in 159 string files + 861 UI keys, 186 files installed, problems=0, render selftest OK. Not yet verified in-game for the new batches.
- Later same day: B028_dw (DialogueWhiterun) COMPLETE 755/815 strings; B029_ds (DialogueSolitude) COMPLETE 680/711. Overall 71,924 / 94,384 (76.20%). Deployed 72,087 strings, problems=0, 20 tests OK.
- 2026-11-07: B030_dwh (DialogueWindhelm) COMPLETE 548/554 strings; B031_dm (DialogueMarkarth) COMPLETE 465/472. Overall 72,950 / 94,384 (77.29%). Redeployed, 20 tests OK.
- Next candidates: DialogueGeneric (715), DialogueFollower (525), DLC2DialogueRavenRock (416), DialogueWinterholdCollege (313).
- Remaining untranslated: ~21,000 dialogue lines (DialogueGeneric/Solitude/Windhelm/Follower/Markarth, DLC1/DLC2 quests) and 1,439 book texts.

## 2026-11-11 (90% milestone)
- Completed batches since 77%: B032_dg (DialogueGeneric), B033_df (DialogueFollower), B034_dc (College/towns), B035_sys (guards, marriage, carriages, hirelings), B036_d2 (Raven Rock / Skaal / Tel Mithryn / Thirsk, 1,393 strings), B037_dq (Dragonborn quests DLC2MQ*/RR/SV/TT/MH/Kolbjorn, 1,847), B038_dg (Dawnguard quests DLC1VQ*/Soul Cairn/Chantry/Serana, 2,465), B039_mx (mixed: Hearthfire, adoption, Cidhna Mine, crime guards, orc strongholds, trainers, Maul, Shor's Stone, Mara quests, stables, shout words, M'aiq; 2,118).
- Overall: 84,949 / 94,384 player-visible strings accepted (90.0%). Target 90% REACHED.
- Deployed via Deploy-Arabic.ps1 to E:\SteamLibrary\...\Skyrim Special Edition\Data: 85,112 strings in 164 string files + 861 UI keys, 191 files installed, problems=0, render selftest OK. Not yet verified in-game for the new batches.
- QA fixes applied in passing: "Highpoint Tower" -> glossary form, reavers -> glossary form, removed Abrahamic phrasing ("بارك الله فيك") from Dunmer lines.
- Remaining: ~9,400 strings (1,439 book texts with unresolved context, BardSongs, ~500 small dialogue groups).

## 2026-11-11 (98% milestone)
- Completed batches since 90%: B040_r1 (BYOH houses/adoption, BardSongs incl. Dovahzul verses transliterated, Bards College quests, Khajiit caravans, Dawnguard fort/castle, RH/RV radiant quests, Serana commentary, Soul Cairn; 1,440), B041_r2 (Thirsk, Frea/Neloth epilogue, Raven Rock townsfolk, Skaal Village, Tel Mithryn, Tame Dragon; 1,414), B042_r3 (Dawnstar, Falkreath, Ivarstead, Karthwasten, Kynesgrove, Largashbur, Markarth; 1,435), B043_r4 (Riften, Riverwood, Rorikstead farms, Bards College class, Solitude; 1,404), B044_r5 (Solitude/Whiterun/Windhelm/Winterhold scenes, investments, marriage, bounty collectors, world encounters; 1,420), B045_r6 (world encounters, Thalmor, Medresi Dran, Illia, Eldergleam, Forelhost; 487).
- Overall: 92,549 / 94,384 player-visible strings accepted (98.06%). Target 98% REACHED.
- Deployed via Deploy-Arabic.ps1: 92,712 strings in 166 string files + 861 UI keys, 193 files installed, problems=0, render selftest OK. Not yet verified in-game for the new batches.
- QA notes: all rejections were negation/digit/glossary-form gates and were fixed (e.g. "Bards College" -> كلية الشعراء, "Shrine of Talos" -> مزار تالوس, "Thieves Guild" -> نقابة اللصوص). Two slips of Abrahamic phrasing caught and replaced with "الآلهة".
- Remaining: ~1,835 strings (1,439 book texts, ~390 small dialogue groups).

## 2026-11-11 (all dialogue done, 98.5%)
- B046_r7 + B047_dl: last 396 dialogue lines translated. All dialogue_line strings are now accepted. Overall 92,945 / 94,384 (98.48%). Redeployed.
- Remaining: 1,439 book_text strings (~3.0M source chars, ~500k words). B048_bk1 exported (40 books), not yet translated.
- Known blocker for books: qa.py flags Latin text inside $DaedricFont/$DragonFont spans (cipher fonts that must stay Latin). Needs an exemption that tracks the font-tag stack before book import.

## 2026-11-11 (books in progress, 98.67%)
- Cipher-font blocker resolved: qa.py strips text inside $Daedric/$Dragon/$Falmer/$Dwemer/$MageScript font spans before language checks (tag-stack aware); 20 tests + selftest OK.
- Book batches accepted with 0 open rejections: B048_bk1 (40), B049_bk2 (60 groups/70 strings: Fishing CC, Dawnfang/Goldbrand/Kagrenac CC), B050_bk3 (40: Dawnfang/Umbra/Gray Cowl/Lord's Mail CC), B051_bk4 (30: Saints & Seducers CC).
- Overall 93,125 / 94,384 (98.67%). Redeployed: 93,288 strings, 193 files, problems=0. Not verified in-game.
- Pitfall: batch input.tsv has NO header row; chunk index = line number - 1. A shifted import in B050 was caught and its 15 rows deleted before re-import.
- Remaining: ~1,239 unique book texts.

## 2026-11-11 (books, 98.72%)
- B052_bk5 (30: Blackbone Isle/Cyrus CC, unicorn, Nix-Hound, Whiterun poison ledger, Blue God goblins, netch leather, Hasedoki, The Light and the Dark, Crimson Dirks 3) and B053_bk6 (25: Crimson Dirks 2/5/6 and dossiers) accepted, 0 open rejections.
- Term fixes re-imported: "Teleport Pet:" -> «نقل الحيوان الأليف:» (B049), "Seducers" -> «المغويات» (B050).
- Overall 93,180 / 94,384 (98.72%). Redeployed: 93,343 strings, 193 files, problems=0, tests OK. Not verified in-game.
- Remaining: 1,184 unique book texts.

## 2026-11-11 (books, B054-B056)
- B054_bk7 (25: Crimson Dirks 1/4/8/9, Tyra's tests, Bjormund/Crowstooth bounties), B055_bk8 (25: Crimson Dirks 7, Mythic Dawn/Oblivion Gate CC, Rielle, Vigil journal, Greencap, stalhrim note, Crypt of the Heart), B056_bk9 (25: Remnants/Fijeh, The Ebon Arm, The Alik'r, Myrwatch, Hendraheim, Bloodchill Manor) accepted, 0 open rejections.
- Overall 93,255 / 94,384 (98.80%). Redeployed: 93,418 strings, problems=0. Remaining 1,109 books (~2.63M chars).
- B057_bk10 (25: Stormbear champion duel, Ironwood/ataxia, Eslaf Erol vault heist, Pit champion cup, Equilibrium) and B058_bk11 (25: Vigil/Dawnstar vampire cure, Galur Rithari, Staff of Chaos, Mannimarco bone forge, Forgotten Seasons v1) accepted, 0 rejections. Fixed «إيستمارش» spelling in B052. Remaining books: 1059 2583299 (count, chars).
- B059_bk12 (26: Forgotten Seasons notes, pet taming, spell titles), B060_bk13 (36: haunted farm journals, Dawnguard caches, Valerica/Soul Cairn, Adalvald, Aetherium Wars, Bloodspring, Jiub), B061_bk14 (30: Redwater, Fur Trader, Ruunvald I-IV, Minorne, Falmer texts) accepted, 0 open rejections.
- qa.py fix: the 'untranslated' check now ignores tokens like [pagebreak], so books written entirely in $FalmerFont (must stay Latin) pass. Tests + selftest OK.
- Remaining books after B061: 974 2507971 (count, chars).
- B062_bk15 (30), B063_bk16 (31: Black Books, Gratian journal, The Axe Man, Wind and Sand), B064_bk17 (30: Poison Song I/III-VII, Varieties of Faith in the Empire, Lives of the Saints, Bone I, Nerevar at Red Mountain, Anticipations) accepted, 0 open rejections. Remaining books: 884 2352192 (count, chars).

B065_bk18 – B070_bk23 (30 book groups each) accepted. B069/B070 added; `<pagebreak>` (angle-bracket form) now treated as a token in qa.py. Deployed checkpoint: 93,677 / 94,384 strings accepted (99.25%); remaining ~707 book_text strings.

B071_bk24 – B073_bk26 (30 groups each) accepted and deployed. qa.py now also treats `<hr>` as a tag token. Pending: remaining book_text strings (see translations.py stats).
B074_bk27 and B075_bk28 accepted and deployed.

## 2026-11-12 (books, 99.51%)
- B076_bk29 and B077_bk30 had been imported partially; B077 is now complete (9 missing rows translated: Waters of Oblivion, On Artaeum, Armorers' Challenge, How Orsinium Passed to the Orcs, 2920 Second Seed, Gold Ribbon of Merit, A Dance in Fire 4, two notes). 30/30, 0 rejections.
- B078_bk31 (30: Sithis, Red Book of Riddles, Children of the Sky, Gauldur journal, Code of Malacath, Brothers of Darkness, Cake and the Diamond, Hope of the Redoran, Three Thieves, 2920 Mid Year, Immortal Blood, Wolf Queen 1 and 7, spell tomes, notes) accepted, 0 rejections.
- Spelling fixes: Boethiah -> «بوثيا», Antiochus -> «أنطيوخس» (B077).
- Overall 93,919 / 94,384 (99.51%); book_text 974/1439. Redeployed: 94,082 strings, 193 files, problems=0, tests + selftest OK. Not verified in-game.
- Remaining: 465 book_text strings.

## 2026-11-12 (books, B079)
- B079_bk32 (30: Markarth sellsword guide, Dwemer Essays ch.1, Dwemer Inquiries III, Chimarvamidium, The Seed, Night of Tears, Opusculus Lamae Bal, Olaf and the Dragon, Brief History of the Empire II, Black Arrow II, Princess Talara IV, 2920 Sun's Dusk, Sixteen Accords VI, Wraith's Wedding Dowry, The Final Lesson, Heavy Armor Forging, notes, spell tomes) accepted, 0 rejections.
- Two documented waivers (qa_waivers.tsv): source markup `</Font>` and `<align='left'>` kept verbatim.
- Overall 93,949 / 94,384 (99.54%); book_text 1004/1439. Redeployed: 94,112 strings, 193 files, problems=0, selftest OK. Not verified in-game. Remaining: 435 book_text strings.

## 2026-11-12 (books, B080)
- B080_bk33 (30: Song of Pelinal 3-4, Chimarvamidium variant, Chronicles of Nchuleft, Spirit of the Daedra, On Oblivion, Commentaries on the Mysterium Xarxes II, Last Seed/Sun's Height of 2920, Feyfolken III, Thief, Beggar Prince, Breathing Water, Horror of Castle Xyr, Cicero's journal, Gauldur and Arondil journals, notes, spell tomes) accepted, 0 open rejections.
- Pitfall: in Bash heredocs, a Python literal '\n' arrived as a real newline and split a row across lines; ar.tsv was rebuilt from the chunk files. Use chr(92)+'n' in such scripts.
- Overall 93,979 / 94,384 (99.57%); book_text 1034/1439. Redeployed: 94,142 strings, 193 files, problems=0, selftest OK. Not verified in-game. Remaining: 405 book_text strings.

## 2026-11-12 (books, non-stop run)
- B081_bk34 and B082_bk35 accepted (30/30 each, 0 open rejections). Not yet redeployed (deploy once at end of run).
- Helper for lean batches: scratchpad bk.py (new = export+print; done = rebuild ar.tsv from t*.raw, import, show rejections only).
- Spelling fixes in passing: Windhelm -> «ويندهيلم» (name_form), Northwatch Keep -> «قلعة المرصد الشمالي», Oakflesh -> «جلد البلوط», Fire Storm -> «عاصفة نارية», Telekinesis -> «التحريك الذهني».

## 2026-11-12 (installer)
- Mod rebuilt from the database: 94,226 strings in 166 files + 861 UI keys (95,087 accepted), problems=0, tests + selftest OK.
- Installer (05_tools/installer_ui) now performs a real install/update/uninstall: the build embeds 07_patch/SkyrimArabic as payload.zip; files go to Data as loose files with staging, SHA-256 receipt (Data/SkyrimArabic/receipt.tsv), backup of pre-existing files, rollback on failure. Verified on a dummy game folder only (193 files byte-identical to 07_patch; uninstall restores the prior state). Not yet run against the real game.
- Rendering reworked: opaque shaped window + separate static shadow window, cached layers, baked particle sheets, one 60-72 Hz beat. Measured on this PC: 32-43 fps at 62-71% of a core before, ~70 fps at 33-40% after.
- Output copy: 09_release/SkyrimArabic-Installer.exe. Rebuild the installer after every build_mod.py run to refresh the payload.
