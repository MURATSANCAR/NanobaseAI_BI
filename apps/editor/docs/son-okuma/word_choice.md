# Yabancı ve yaşa ağır sözcükler (`word_choice`) — ÖLÇÜM BEKLİYOR

Kaynak: `src/editor/proofing/word_choice.py` (v1).

## Kural
- **Yabancı** (her kitap): günümüz Batı dillerinden gelmiş, yerleşmemiş ve yaygın Türkçe karşılığı olan
  sözcük («online» → «çevrim içi»); Arapça/Farsça kökenli yerleşik sözcükler değil.
- **Yaşa ağır** (yalnız kitap profili çocuk ya da genç okur ise; `book_profile.audience`, yaş aralığı CRM'den):
  okurun anlamını büyük olasılıkla bilmeyeceği sözcük + daha basit karşılık.

## Karar
1. Kökler `word_variety._read` (içerik sözcükleri) + sözlüğün çözümleyemediği biçimler (yabancı için).
2. Aday: model, `EDITOR_WORD_CHOICE_BATCH` (150) köklük JSON çağrılarla (hiçbir kök atlanmaz); listede olmayan
   sözcük atılır (`*_not_in_list`), karşılığın her sözcüğü sözlükte olmalı (`dropped_invalid_alternative`).
3. Doğrulama: kitabın kendi cümlesiyle iki sıralı kapalı soru (yabancı: karşılık bu cümlede doğru ve daha
   uygun mu; yaş: bu okur için ağır mı). `p ≥ 0,5`.

## Bulgu
Sözcük başına bir: ilk geçtiği sayfa, `suggestion` karşılık, `details.pages` bütün sayfalar,
`group` «yabancı sözcük» / «yaşa ağır sözcük».

## Bilinen sınırlar
TDK karşılıklar kılavuzu yok; aday modelin bilgisidir, doğrulama kitabın cümlesiyle yapılır. Yayınevi
politikası (hangi yabancı sözcüğe izin) editör kararlarıyla ölçülecek.
