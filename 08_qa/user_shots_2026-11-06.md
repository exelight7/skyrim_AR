# User screenshots 2026-11-06 (batch 2, images 16-35) - observed issues

1. Generic/ambient NPC dialogue still English (Marise Aravel, Bolli, Iris, Mjoll, Brand-Shei) - untranslated dialogue_line (expected, pending batches).
2. Subtitle "Name: text" - speaker name Arabic + English line; colon/name order mixes direction.
3. Journal bottom bar garbled: "اظهار علب ، الخريطة" (Show on map), "سن كمهمة نشطة" (Set active quest) - broken shaping / clipped glyphs.
4. Journal date line bidi wrong: "4E ,نار الموقد 4 ,ص ، 10:27 ,الخميس ،" - Latin commas, reversed segment order.
5. Item info card: "القيمة"/"الوزن" labels clipped at baseline; "الوزن" label partially hidden; item name "لحم بقري نيء" renders as "نحم بقري ء" (ي/ء issue), names cut at bottom.
6. Top-right HUD text "الفتا،" clipped/truncated (stealth/status text).
7. "المستوى" level label has stray trailing mark (colon rendered).
8. Main menu confirm buttons "نعم"/"لا" sit below baseline/clipped.
9. Journal quest text "يتسكّع" - shadda glyph renders badly.
10. Lower half of some frames shows a horizontal seam (graphics, likely not ours).

## Batch 3 (images 36-44) + root cause
- Skill names, top stats bar, button bar, item card labels: descenders clipped (not wrong glyphs).
  Root cause: UI font metrics ascent 1.30em/descent 0.57em vs Futura 0.97/0.22 -> baseline too low in fixed-height fields.
  Fix: font_prepare fit=0.85,840,360,180 for UI Regular/Bold; rebuilt fonts_ar.swf; redeployed. Needs in-game confirmation.
- Date line order (engine-composed "Day, time, date, 4E"): pieces concatenated by engine in LTR order - open.
