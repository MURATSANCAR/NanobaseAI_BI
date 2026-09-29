# Sözleşme karşılaştırma — editör ve hukukçu gözüyle eksikler, plan (2026-09-29)

İlk sürüm (`contracts_compare*.py`, `/telif-sozlesme/karsilastirma`) «CRM'e girilen şart emsalden farklı mı» sorusunu
cevaplıyor. Hukukçunun sorusu «bu metinde bizim için riskli ya da standart dışı hüküm var mı». Aşağıdaki 13 madde bu
aralığı kapatır. Her maddede önce ölçüm (test sunucusu, CRM .28 salt okuma), sonra karar ve tasarım.

Genel kurallar: model yalnız madde türü tanımada ve yalnız kendi GPU modelimizle (LLM kapısı, maskeli metin, kapalı
küme seçimi); sayıları model üretmez. CRM'e yazma yok. Her rakamda sorgu bilgisi. Her ekran 320–1440 px.

## Faz 1 — doğruluk ve günlük iş

### 1. Tutarlar kura göre düzeltilir (yanıltan hata)
- **Ölçüm:** Emsal dönemi 5 yıl; USD/TRY 2021'de ~7,5, 2026'da ~41. TL avans ve tek ödeme nominal kıyaslanınca eski
  sözleşme «düşük», yeni «yüksek» çıkıyor. TÜFE için kurumsal kaynak (EVDS) anahtar istiyor; TCMB günlük kur dosyası
  açık ve depoda okuyucu var (`contracts_royalty.tcmb_rate`). Logo fatura kuru (TRRATE) yalnız 2021 sonrası.
- **Karar:** TL tutar maddeleri (avans, tek ödeme, görsel bedeli) sözleşmenin başladığı ayın ilk iş gününün TCMB USD
  alış kuruyla dolara çevrilip kıyaslanır; dövizli sözleşme kendi para biriminde kalır (zaten aynı para birimiyle
  kıyaslanıyor). Kur okunamayan ayın tutarı kıyasa girmez ve «kur yok» yazar (tahmin edilmez).
- **Tasarım:** kur önbelleği `CONTRACT_COMPARE_DIR/kur.json` (ay → kur, kaynak, gün); CRM görüntüsü okunurken eksik
  aylar tamamlanır (ilk sefer ~300 ay, sonra yalnız yeni ay). Ekranda «18.000 TL ≈ 2.400 USD (Mart 2023 kuru 7,50)».

### 2. İnceleme kaydı ve Excel
- **Eksik:** farkı gören kişi «incelendi / bilinçli istisna / CRM düzeltilmeli / hukuka sorulacak» diyemiyor, not
  düşemiyor; aynı fark her açılışta tekrar önüne geliyor.
- **Tasarım:** `semantic_contract_compare_reviews` (anlaşma, madde, değerin izi, durum, not, sorumlu, kim/ne zaman).
  Değer CRM'de değişirse eski inceleme «eski değere ait» olur. Tarama süzgeci «incelenmemiş», sözleşmede madde başına
  «İşaretle». Yetki `ozellik:sozlesme-karsilastirma.inceleme`. Liste CSV + ortak Excel katmanı (`bicim=xlsx`).

### 3. Taslak aşamasında uyarı
- **Eksik:** en değerli an imzadan önce; «Yeni sözleşme» formunda oran/avans girilirken emsal uyarısı yok.
- **Tasarım:** `POST …/compare/terms` (kayıt tutmaz) + formda «Emsal kontrolü» paneli (girildikçe, 600 ms bekleme).

### 4. Şekil denetimi (FSEK 52 ve kayıt bütünlüğü)
- **Dayanak:** FSEK md. 52 — mali haklara ilişkin sözleşmeler yazılı yapılır ve konusu olan haklar ayrı ayrı
  gösterilir; gösterilmeyen hak devredilmiş sayılmaz. Süre ve yer belirtilmemişse yorumla doldurulur (uyuşmazlık riski).
- **Denetimler (Telif Alış; koruma dışı eser hariç):** en az bir mali hak işaretli · süre (yıl ya da bitiş) ya da
  süresiz · başlangıç tarihi · hak sahibi (taraf kaydı) · bağlı kitap · ücret şartı (oran, tek ödeme ya da açıklama).
  CRM'de Telif Alış için bölge alanı yok → denetlenemez, ekranda yazılır. Hukuki görüş değildir, kayıt denetimidir.
- **Tasarım:** sözleşmede «Şekil denetimi» bölümü, taramada KPI + süzgeç.

### 5. Hak açıklaması sınıfı
- Haklar ve lisanslar ekranının Zeki AI sınıfı (`rights_notes`, tablo varsa) serbest metnin yanında gösterilir.

## Faz 2 — kıyasın zenginleşmesi

### 6. Ticari benzerlik ölçütleri
- **Ölçüm:** aracı (ajans) taraf 2.768 kayıt; kitap web ana kategorisi kitap kartında; orijinal dil 2.097 sözleşmede;
  sözleşme–kitap bağı 13.032 sözleşme (14.840 bağın 14.840'ı stok kodlu). Logo satışı stok kodu × ay × 6 yıl zaten
  hazırlanıyor (`author_snapshots` «sales» parçası) → yeni Logo sorgusu gerekmez.
- **Tasarım:** isteğe bağlı ölçütler: *ajans üzerinden* · *hak sahibinin satış dilimi* (son 36 ay, hak sahibinin
  bütün kitaplarının net satış adedi; yok / alt / orta / üst %20) · *kitap kategorisi* · *yerli/çeviri*. Ekranda
  «Kıyas ölçütleri» seçimi; varsayılanı Yönetim ayarı. Gevşetmede önce isteğe bağlılar düşer.

### 7. İlişkili kayıtlar ve olaylar
- Anlaşmanın öbür kopyaları, ana/bağlı sözleşmeler, ek protokol, muvafakatname, ikale, fesih, yenileme tarihleri ve
  portal zeyilnameleri sözleşme görünümünde zaman sırasıyla.

## Faz 3 — hukuk birimi

### 8. Standart pozisyonlar (playbook)
- **Eksik:** kırmızı çizgiler tanımlı değil. Hukuk biriminin listesi elimizde yok → mekanizma kurulur, liste ekrandan
  yazılır. «Emsalden öneri üret» düğmesi her madde için emsal aralığını (%5–%95, çoğunluk değeri) *öneri* olarak açar;
  yetkili onaylamadan kural olmaz.
- **Tasarım:** `semantic_contract_positions` (madde, kapsam: tip/ödeme türü, işlem: en az/en çok/eşit/içinde/zorunlu/
  yasak, değer, düzey: kırmızı çizgi/uyarı, gerekçe, durum: öneri/onaylı, kim). Sözleşmede ve taramada ihlaller.
  Yetki `ozellik:sozlesme-karsilastirma.pozisyon` (açıkça verilir).

### 9. Hukuki madde türleri (belge metni)
- **Eksik:** belgede fesih, münhasırlık, hakların geri dönüşü, stok eritme, tercih hakkı, hesap denetimi, cezai şart,
  yetkili mahkeme, manevi haklar, kişisel veri hükümleri tanınmıyor; «fesih maddesi yok» denemiyor.
- **Tasarım:** kapalı tür kümesi (20 tür). Önce kural (katlanmış anahtar sözcük, başlık), kalan madde Zeki AI kapalı
  küme seçimiyle (`choose`, olasılık ve fark eşiği; altı «belirsiz»). Belge başına tür haritası ve eksik türler
  (arşivde türün ne kadar yaygın olduğuyla). Eşlemede aynı türdeki maddeler öne alınır.

### 10. Belge arşivi: toplu yükleme, eşleştirme, HEIC
- **Ölçüm:** CRM'de 9 ek (8 HEIC). Köprüde HEIC okuyucu yok (`pillow_heif` kurulu değil).
- **Tasarım:** çoklu yükleme; sözleşme numarası dosya adından ya da ilk sayfadan (CRM'de var olan numara) bulunur,
  kişi değiştirebilir. HEIC: paket kuruluysa JPEG'e çevrilip okunur, değilse nedeni yazılır (paket kurulumu ayrı adım).
- **Açık soru (Timaş):** imzalı sözleşmelerin asıl arşivi nerede (dosya sunucusu, taranmış klasör)?

### 11. Word raporu
- Sözleşme karşılaştırması ve belge farkı Word olarak (değişen kelime renkli, silinen üstü çizili). Yetki
  `ozellik:veri.disa-aktar`.

### 12. Kişisel veri ve saklama
- Belge metni ekranda maskeli (kimlik no, telefon, e-posta, IBAN, adres/ad etiketli satırlar); maskesiz görüntüleme
  yalnız belge yetkisiyle ve değişiklik kaydına yazılarak. Yüklenen belgeye saklama süresi ayarı (0 = süresiz).

### 13. Kademeli telif — yapılamaz
- CRM'de kademe tablosu yok (INFORMATION_SCHEMA'da `kademe`/`tier` adlı tablo 0). Portal kaydının kademeleri kıyas
  için emsal bulamaz. Veri gelirse eklenir.

## Sıra ve kabul
Faz 1 → Faz 2 → Faz 3; her faz ayrı commit, test sunucusunda aday ağaç + yan köprü + gerçek CRM ile kabul
(`scripts/acceptance/sozlesme-karsilastirma/kabul.py` genişler): kur çevirisi bağımsız TCMB okumasıyla, inceleme
kaydı SQL'le, şekil denetimi SQL sayımıyla, ticari ölçütler SQL + Logo ile, pozisyon ihlali elle kurulan kuralla,
madde türleri bilinen örnek belgeyle, Word dosyası açılıp metniyle denetlenir. Test kaydı bitince silinir.
