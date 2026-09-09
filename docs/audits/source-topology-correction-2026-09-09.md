# Tek şirket ve yedek kaynakları düzeltmesi — 2026-09-09

Kullanıcının doğruladığı iş anlamı: tek şirket vardır; farklı veritabanları yıllar
boyunca alınan yedeklerdir. 411/211 teknik kodları ayrı şirket değildir.

## Yayınlanan düzeltmeler

- Üretimde `SEMANTIC_PATTERN_LABELS=Firma` kaldırıldı.
- Modelin yüklediği dört bilgi belgesindeki ayrı şirket / geçmiş yıllar yok
  varsayımları düzeltildi. Öncelikli `00-source-topology.md` eklendi.
- Veri sözlüğü ipucunda `firma 411` yerine `Kaynak 411` kullanılıyor.
  Üretimin mevcut JS dosyasına tek metin değişikliği uygulanıp yeni içerik hashli
  dosya ve index yayımlandı; tüm yerel ön yüz yayımlanmadı.
- AGENTS.md kalıcı proje kuralı güncellendi.
- Önceki kabul raporuna yorumun geri çekildiği eklendi. Tarihsel sayısal ölçümler
  korunuyor; ayrı firma varsayımlı referanslar doğru yedek seçimini kanıtlamıyor.

## Gerçek ortam kanıtları

Sunucudan salt okunur sorguyla bağlı DB adı `LOGO_DB` doğrulandı. Erişilebilir
kullanıcı DB listesinde `LOGO_DB` ve `Timas_MSCRM` bulundu. Bu liste yedeklerin
harici konumları, geçmiş bağlantıları veya yetkili dönemleri hakkında kanıt değildir.
Profil tarih aralıkları 211 STLINE için 2030, 411 STLINE için 2027 gibi ileri
kayıtlar içeriyor; yalnız min/max tarih yedek önceliğini belirlemez.

Gerçek katalog API kontrolünde toplam 4.874 tablo döndü; bağlam `n0/n1` teknik
anahtarlarıyla geldi, `Firma` etiketi yok. Canlı tarayıcıda 320, 390, 768 ve
1440 pikselde kaynak ipuçları doğrulandı; sayfa scrollWidth değerleri görünüm
 genişliğine eşitti. 390 piksel ekran görüntüsü de incelendi.
Yerel test veya yapay veri kullanılmadı.

## Açık doğrulama

**DOĞRULANAMADI:** Veritabanı–yedek tarihi–yetkili işlem dönemi eşlemesi ve örtüşen
kayıtlarda hangi yedeğin esas alınacağı. Kullanıcıdan bu eşlemenin kaynağı istendi.
Mevcut dönem seçici/UNION davranışı bu düzeltmeyle yeniden tasarlanmadı. Model
bilgisi düzeltmesi, tüm sorularda doğru kaynak seçimi ve tekilleştirme garantisi
vermez. Yeni sayısal kabul sonucu ilan edilmedi; önceki 100 sorunun kaynak seçimi
kabulü doğru referansla yeniden değerlendirilmelidir.

Kanıt dizini: `outputs/source-topology-20260909/`.
Sunucu yedekleri: `/data/nanobaseai/bi/backups/source-topology-20260909/release-204009/`.
