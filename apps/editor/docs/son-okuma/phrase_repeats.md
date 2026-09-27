# Kalıp ifade tekrarı (`phrase_repeats`) — ÖLÇÜM BEKLİYOR

Kaynak: `src/editor/proofing/phrase_repeats.py`, `_word_variety.repeated_phrases` (v1).

## Kural
Aynı söz öbeği (kök dizisi; ekler değişebilir: «kalbi küt küt attı» = «kalbim küt küt atıyordu») kitapta
en az iki kez geçiyor ve model göze batan kalıp anlatım diyorsa WARN. Mesafe aranmaz.

## Karar
1. Kök dizisi `word_variety._read`; özel ad, bozuk span, hikâye dışı sayfa öbeği koparır.
2. Aday: tek cümle, bitişik, ≥ 3 sözcük, ≥ 2 içerik sözcüğü («bir gün daha» sayılmaz), ≥ 2 geçiş, üst üste
   binen geçiş tek. Yalnız en uzun hâl; kısa öbeğin fazladan geçişi varsa o da bildirilir. Uzunluk sınırı yok.
3. Model (iki sıralı): kalıp anlatım mı; deyim, ad, terim, nakarat, bilinçli yineleme mi.

## Bulgu
İkinci geçişin sayfası; `marks` o geçişin sözcükleri; `details.occurrences` her geçiş (sayfa, metin, bağlam).

## Ölçüm (dry, 2026-09-27)
- Dilek Ağacı: 32 → 21 bulgu (yinelenen OCR eki okuma dışı kalınca s.22'deki sahte tekrarlar gitti);
  «kısa yoldan zengin olma» s.37/41, «bir top kırmızı kurdele» s.24/25.
- Duvarları Yıkmak: 256 → 132 (fiil şartı: fiilsiz ad öbeği terimdir, «sosyal medya»); «vakti gelmedi mi» 5,
  «hiç düşündünüz mü» 5, «gözler önüne seriyor» 2. Zayıflar da var («bir şey yaptılar»).
