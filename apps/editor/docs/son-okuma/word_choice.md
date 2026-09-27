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

## Ölçüm (dry, 2026-09-27)
- İlk istem («seç») modelde boş liste döndürüyordu (online/feedback bile); her sözcüğü sınıflandırma istenince
  yakalanıyor. İlk sürümdeki «online → çevrim içi» örneği modeli «internet → çevrim içi» yanlışına yöneltti; kaldırıldı.
- Duvarları Yıkmak: 3.372 kök + 780 tanınmayan biçim, 119 aday, cümleyle doğrulamada 109 elendi, 9 kaldı:
  perspektif → bakış açısı, faktör → etken, enteresan → ilginç, problem → sorun, pozitif → olumlu,
  realite → gerçeklik, anksiyete → kaygı, defo → kusur; «suiistimal → suistimal» yazım farkıydı → 1-2 harf
  uzak karşılık artık atılır.
- Dilek Ağacı: 0 (çocuk kitabı).
- **Yaş parçası hiçbir kitapta koşmadı:** `book_crm_record` 6 kitap, hiçbirinde okur kitlesi/yaş yok.
