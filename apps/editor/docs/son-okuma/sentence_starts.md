# Cümle başı tekdüzeliği (`sentence_starts`) — ÖLÇÜM BEKLİYOR

Kaynak: `src/editor/proofing/sentence_starts.py`, `_word_variety.start_runs` (v1).

## Kural
Art arda cümleler aynı sözcükle (kökle) başlıyor ve bu tesadüf düzeyinde değil («Sonra … Sonra …»,
«Ama … Ama …»), model de bilinçli yineleme değil tekdüzelik diyorsa WARN.

## Karar
1. Cümleler `read_book` belirteç akışından (cümle başı işareti); bozuk span, hikâye dışı sayfa dışarıda.
   İlk sözcük Zemberek köküne iner; kesmeli özel ad kendi yazımıyla.
2. Sözcüğün kitapta cümle başlatma oranı p; art arda k cümle → p^(k−1) < `EDITOR_WORD_ECHO_ALPHA` (0,05).
   «Ben» %10 ise iki «Ben» olağan (0,1), üç değil (0,01); seyrek «Sonra» ikide aday.
3. Model (iki sıralı): tekdüzelik mi, bilinçli yineleme mi (vurgu, sıralama, şiir, tekerleme, ritim).

## Bulgu
İkinci cümlenin sayfası; `bbox` ikinci cümlenin ilk sözcüğü, `marks` aynı sayfadaki bütün cümle başları;
`group` «cümle başı · kök».
