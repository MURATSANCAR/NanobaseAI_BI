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
