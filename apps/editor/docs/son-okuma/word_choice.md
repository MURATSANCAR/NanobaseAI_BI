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

## Sürüm 2–3 (2026-09-27)
- CRM bağlayıcısı yeniden koşunca (22/25 kitap) yaş parçası ilk kez çalıştı: Anne Terliği (CRM: 4–6 yaş) 167,
  Levent (9–11) 39 bulgu. Künye/tanıtım sözcükleri (ISBN, TSE, OSB, «takdim») ve bozuk kökler («kv», «nim»)
  vardı → v2: 4 harften kısa kök ve kitapta hep büyük harfle geçen biçim dışarıda; doğrulama sorusu «bu cümle
  anlatı değil (künye, tanıtım, arka kapak)» seçeneğini taşır.
- v2 sonrası Anne Terliği hâlâ 164: «bijon», «ardiye», «hazırcevap», «iltifat» 4–6 yaş için gerçekten ağır — ya
  kitap beyan edilen yaştan zor ya CRM yaş aralığı yanlış; editörün göreceği asıl bilgi bu uyumsuzluk →
  v3: yaşa ağır sözcükler tek tek INFO, kitap geneli tek WARN (sayı, 1.000 sözcükte oran, güven sırasıyla
  tam liste ayrıntıda, mesajda ilk 15 + kalan sayısı). Yabancı sözcük sözcük başına WARN kalır.
