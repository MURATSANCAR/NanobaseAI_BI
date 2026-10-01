# CRM'deki hareket tabloları: Logo kopyası mı, ayrı veri mi?

Sorgu tarihi: **2026-10-01**. Kaynaklar: prod CRM (.28) ve canlı Logo (firma 411 = 2026, firma 211 = 2025, dönem 01).
Bütün sorgular salt SELECT, `READ UNCOMMITTED` + `NOLOCK` + `LOCK_TIMEOUT 20000` ile koştu. Toplam 138 sorgu atıldı.
1205 deadlock da zaman aşımı da olmadı. Bir sorgu, takma adda ayrılmış kelime kullandığım için hata verdi; düzeltip
yeniden koşturdum. Ham çıktılar ve betikler test sunucusunda:
`/data/nanobaseai/bi/acceptance/claude-review-20261001/sozluk/kopya-olcum.json` ve `.../sozluk/kopya-ham/`.

CRM tarihleri UTC olarak tutuluyor. Gün ve ay sınırları `DATEADD(hour,3,…)` ile İstanbul saatine çevrildi.
CRM ile Logo ayrı sunucularda. Karşılaştırma Python'da yapıldı, iki kaynağa giden tek bir SQL yok.

## Özet

| Aile | Tablolar | Sınıf | Tek satır kanıt |
|---|---|---|---|
| Sevkiyat | new_sevkiyat, new_sevkiyatsatiri | **logo_kopyasi** (yön CRM→Logo) | 2026-09-15'te 276 CRM sevkiyatından 275'i Logo STFICHE'de, `new_logicalref` = LOGICALREF ve 274 fatura no eşleşiyor; Eylül 2026 Logo TRCODE 8 faturalı LINENET'in %99,3'ü CRM kaynaklı |
| Sipariş | new_siparis, new_siparissatiri | **logo_oncesi_surec** | 2026-09-15'teki 239 ve 2025-09-16'daki 238 CRM siparişinden hiçbiri Logo ORFICHE'de yok (0 eşleşme). Logo'ya sevkiyat üzerinden irsaliye/fatura olarak gidiyor |
| Malzeme hareketi | new_malzemehareketi, new_malzemehareketsatiri, new_serilothareketsatiri | **crm_ozgun** (depo/WMS defteri; içinde kısmen Logo olayı var) | Eylül 2026'da `new_logicalref` 0/8.212 dolu. Raf transferi çıkışı 1,12 Mn adet, Logo'da karşılığı yok. Sayım fazlası 465k adet, Logo TRCODE 50'de 245 |
| Bekleyen ürün | new_bekleyenurun | **logo_oncesi_surec** | Stok yokken siparişten düşen talep. 2026'da 21.025 kayıt / 314k adet bekliyor, `new_logoyaislendi` 2026'da 0 |
| Koli | new_kutustogu, new_sipariskutusu | **crm_ozgun** | Ambalaj kolisi kullanımı, Eylül 2026'da 5.666 kayıt ve sipariş başına 1 koli. Finansal olay değil |
| Satış hedefi | new_satishedefleri | **crm_ozgun** | Kitap × BMT × yıl için aylık ADET hedefi. 2026'da 68.327 satır ve 13,82 Mn adet. Logo'da hedef yok |

## 1. Sevkiyat ailesi: logo_kopyasi

**Logo bağı:** Bağ doğrudan ve dolu.

| CRM alanı | Logo karşılığı |
|---|---|
| `new_sevkiyat.new_logicalref` | `LG_4xx_01_STFICHE.LOGICALREF` |
| `new_sevkiyat.new_name` (B2B0363459_1, CRM0363438_1) | `STFICHE.DOCODE` |
| `new_sevkiyat.new_faturanumarasi` (TIM2026…) | `INVOICE.FICHENO` |

Aktarım durumunu `new_logoyaaktarildi` ve `new_logomesaji` ("İrsaliye Başarıyla Aktarıldı") gösteriyor.
`new_logicalref` Eylül 2026'daki 6.612 belgenin 6.610'unda dolu.

**Yön:** Kayıt CRM'de oluşup Logo'ya irsaliye olarak itiliyor. Aynı olay iki yerde duruyor ve kayıt sistemi Logo.

**Tazelik:** Son kayıt 2026-09-30 17:57. Her iş günü 88–418 belge geliyor.

**Ay karşılaştırması (2026-09):**

| | CRM sevkiyat | Logo TRCODE 8 |
|---|---|---|
| B2B önekli belge | 2.414 | 2.412 |
| B2B tutar (KDV hariç) | 67,00 Mn | 66,98 Mn faturalı (+0,18 Mn faturasız) |
| CRM önekli belge | 4.198 | 3.864 (3.088 faturalı + 776 faturasız) |
| CRM önekli tutar | 182,65 Mn | 170,64 Mn faturalı |

- Farkın kaynağı şu: faturası olmayan 1.049 CRM sevkiyatı (13,56 Mn) Logo'da **TRCODE 25 (depolar arası sevk)** olarak
  yazılıyor. Logo'da tutarları 0, satırları iki kat. Bu düşülünce CRM 236,1 Mn, Logo 237,6 Mn kalıyor (fark %0,6).
- Logo TRCODE 8 faturalı LINENET 239,15 Mn. Bunun 237,55 Mn'si (%99,3) B2B/CRM önekli belgelerden geliyor.
- 2025-09'da B2B tarafı CRM'de 51,23 Mn, Logo'da 50,72 Mn. Logo'da ayrıca 10,4 Mn tutarında CRM'den gelmeyen TRCODE 8
  var (MRA/MRK/RAM/SAM önekli ve boş DOCODE).

**Günlük anahtar kesişimi:**

| | 2026-09-15 | 2025-09-16 |
|---|---|---|
| CRM sevkiyatı (logicalref dolu) | 276 | 152 |
| Logo STFICHE'de bulunan | 275 | 150 |
| Fatura no eşleşen | 274 | 150 |
| Belge tutarı eşit olan | 242 | 128 |
| Logo TRCODE 8 B2B/CRM adlı → CRM'de var | 256/257 | 128/128 |
| Logo TRCODE 8 diğer → CRM'de var | 0/1 | 0/118 |
| Logo TRCODE 7 (perakende, e-ticaret) → CRM'de var | 0/320 | 0/378 |
| Logo TRCODE 25 CRM adlı → CRM'de var | 18/18 | 21/21 |

Tutar farkı örnekleri: B2B0363468_1'de CRM 12.900, Logo 12.760. CRM0363559_1'de CRM 16.200, Logo 19.440.
Fiyat ve iskonto Logo'da sonradan değişebiliyor; doğru değer Logo'daki.

Uyarı: `new_logicalref` yıllar arasında çakışıyor. 2026'daki 131k LOGICALREF'leri eski yıllardaki CRM kayıtlarında da
geçiyor. Bağ kurulurken yıl firması (2026→411, 2025→211) ve tarih filtresi şart.

## 2. Sipariş ailesi: logo_oncesi_surec

**Logo bağı:** Logo'ya giden bir bağ yok.

- Eylül 2026'da `new_logoyaaktarildi` hiçbir kayıtta "Evet" değil ve `new_logoozelkod` boş.
- Sipariş adı (B2B0363459) Logo ORFICHE'nin DOCODE ya da FICHENO alanında geçmiyor (iki günde 0/239 ve 0/238).
- Akış şöyle: sipariş → sevkiyat (`new_sevkiyat.new_siparisid`, sevkiyat adı = sipariş no + `_1`) → Logo irsaliye/fatura.

**Durumlar:** Siparişte Logo'da olmayan durumlar var: Taslak, İptal, Risk Limit Onayı Bekliyor, Depoda Bekliyor,
Pusula Alındı, Kutulandı, Birleştirildi, Tamamlandı. Sipariş tipi alanında B2B, Dağılım, Standart, Fuar, Telif,
Okul Örneği gibi değerler bulunuyor.

**Tazelik:** Son kayıt 2026-09-30 23:42. Günde 6–438 sipariş geliyor.

**2026-09:**
- CRM'de 5.944 sipariş var: 5.563'ü Tamamlandı, 176'sı İptal.
- Tamamlanan siparişlerin satırlarında 2,13 Mn adet ve 260,4 Mn tutar var.
- Logo ORFICHE'de 8.149 fiş, 7,55 Mn tutar ve 39.038 adet var. Bunlar ağırlıkla TS1 önekli ya da numaralı
  e-ticaret/perakende siparişleri ve TRCODE 7 perakende faturaya dönüşüyorlar.
- Logo'da CRM adlı yalnız 15 ORFICHE var.
- 2025-09 için aynı tablo: CRM 5.364 sipariş, Logo 6.757 ORFICHE ve 98.732 adet.

**Sonuç:** Siparişin Logo'da kopyası yok. Bu tablolar sipariş sürecinin kendi verisi. Sevk edilen kısım
sevkiyat ailesi üzerinden Logo'ya geçiyor.

## 3. Malzeme hareketi ailesi: crm_ozgun (depo/WMS defteri)

**Logo bağı:**
- Eylül 2026'da `new_logicalref` 0/8.212 dolu ve `new_logoyaaktarildi` hiçbir kayıtta "Evet" değil.
- `new_logouretimfisi` yalnız "üretimden giriş" kayıtlarında dolu. Bu değer Logo TRCODE 13 fişinin `STFICHE.SPECODE`
  alanına karşılık geliyor (örnek: 000354). 15–16 Eylül'deki 13 CRM fişinin 12'si Logo'da bulundu.
  Belge no da bağ kuruyor: `new_belgeno` cnı-551 ↔ DOCODE CNI2026000000551.

İşlem türüne göre 2026-09 karşılaştırması (adet):

| CRM işlem türü | CRM | Logo karşılığı | Logo | Alt sınıf |
|---|---|---|---|---|
| 7 İrsaliye (çıkış) | 2.036.364 | TRCODE 8 | 1.955.564 | logo_kopyasi (sevkiyat satırına bağlı) |
| 6 Depolar arası sevk (çıkış) | 110.861 | TRCODE 25 (tek yön) | 309.813 | kısmi |
| 1 Üretimden giriş | 1.137.731 | TRCODE 13 | 2.654.462 | kısmi (SPECODE bağı) |
| 2 Faturalı kabul | 291.127 | TRCODE 1 | 1.759.881 | kısmi, belge bağı yok |
| 3 Sayım fazlası | 465.333 | TRCODE 50 | 245 | crm_ozgun |
| 8 Sayım eksiği | 147.749 | TRCODE 51 | 14 | crm_ozgun |
| 5 Raf transferi | 1.123.587 çıkış / 1.127.087 giriş | yok | — | crm_ozgun |

`new_serilothareketsatiri`, malzeme hareket satırının raf/lot düzeyine bölünmüş hali. Miktar toplamları aynı
(örnek: üretim girişi iki tabloda da 1.137.731). Son kayıt 2026-09-30 18:03.

**Sonuç:** Bu aile depo yönetiminin raf, lot ve sayım defteri. Finansal karşılığı Logo'da tutuluyor.
İrsaliye kısmı sevkiyatla aynı olayı ikinci kez sayar.

## 4. Bekleyen ürün: logo_oncesi_surec

- Stok yokken sipariş satırından düşen talep kaydı (`new_siparissatiriid`, `new_urunid`, `new_firmaid`, `new_adet`).
- Durumlar: Bekleyen, Siparişe Eklendi, İptal.
- `new_logoyaislendi` tarihsel olarak 62.612 kayıtta "Evet", 2026'da hiçbirinde değil.
- 2026'da bekleyen: 21.025 kayıt, 314.130 adet, 2.266 ürün, 717 firma. Siparişe eklenen 462, iptal edilen 6.372 kayıt.
- Son kayıt 2026-09-30 22:03.
- Bu bir talep kaydı, satış değil. Logo'da karşılığı yok.

## 5. Koli: crm_ozgun

- `new_sipariskutusu`: siparişe kullanılan koli. Eylül 2026'da 5.666 kayıt, 5.665 sipariş ve 11.094 koli var;
  kayıtların %99,98'i "1 Numaralı Koli".
- `new_kutustogu`: koli stoğundan yapılan çıkışlar (5.657 kayıt).
- Ambalaj operasyonu; finans kapsamı dışında.

## 6. Satış hedefleri: crm_ozgun (hedef-gerçekleşen sorusunun hedef tarafı)

**İçerik:**
- Kırılım: kitap (`new_stokkarti` → new_kitap) × BMT (`new_BMT` → systemuser) × yıl.
- `new_StokKodu`, Logo stok koduyla aynı (2026'da 68.327/68.327 eşit).
- BMT ya bir satış temsilcisi ya da bir kanal hesabı: Hepsiburada, Kitapyurdu, D&R, Point, B2C, Amazon, Merkez Satış.
- Hedef, `new_ocak`…`new_aralik` alanlarında aylık **ADET** olarak tutuluyor. `new_ToplamHedef` her satırda aylar
  toplamına eşit (uyumsuz satır yok). Tutar alanı yok.

**Yıl alanı (`new_yil`) optionset:**

| Kod | Etiket | Not |
|---|---|---|
| 1 | 2023 | |
| 2 | 2024 | |
| 3 | 2025 | |
| 4 | "2000" | 2025 içinde girilmiş 41.907 satır, 7,79 Mn adet; muhtemelen ikinci bir 2025 sürümü |
| 100000000 | 2026 | |
| 100000001 | "1991" | 2026-02'de girilmiş 4.020 satır, 2,65 Mn adet |
| (boş) | — | 9.427 satır, hedef değeri yok |

**Kırılımın zaman içindeki değişimi:**
- 2023–2024: `new_bolge` × kitap. Bölgeler: BABIALİ, İSTANBUL, D&R, HEPSİBURADA, KİTAPYURDU, B2C, EGE…
- 2025–2026: bölge alanı boş, kırılım BMT × kitap.

**2026 hedefi:**
- 68.327 satır, 4.020 kitap, 17 BMT, toplam 13,82 Mn adet. Son kayıt 2026-06-25.
- Aynı yıl, bölge, kitap ve BMT anahtarı tekrar eden 114 grup var.

2026 aylık hedef ile Logo'da faturalı satılan adedin karşılaştırması (bin adet):

| Ay | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---|---|---|---|---|---|---|---|---|
| Hedef | 844 | 984 | 1.082 | 923 | 726 | 793 | 939 | 929 | 1.910 |
| Logo gerçekleşen | 944 | 1.140 | 1.080 | 1.203 | 733 | 973 | 873 | 1.227 | 1.856 |

## Finans motoru için kural önerisi

1. **Gerçekleşen satış, ciro, miktar, fatura sayısı ve iade** yalnız Logo'dan gelir (STLINE/INVOICE). Sevkiyat ve
   sevkiyat satırı bu sorularda **kullanılmaz**. Logo olayının CRM'deki kopyası oldukları için iki kaynağı toplamak
   çift sayım üretir. CRM tutarları Logo'daki sonradan yapılan fiyat düzeltmelerini de taşımaz.
2. **Sevkiyat → Logo bağı** yalnız bağlam eklemek için kurulur (CRM siparişinin tipi, kampanya, depo, sipariş kanalı).
   Bağ `new_sevkiyat.new_logicalref = STFICHE.LOGICALREF` üzerinden, yıl firması ve tarih filtresiyle kurulur.
   Ölçü yine Logo'dan okunur.
3. **Sipariş, bekleyen sipariş, iptal ve bekleyen ürün** soruları için kaynak CRM'dir (`logo_oncesi_surec`).
   Cevap "sipariş" ya da "talep" diye etiketlenmeli, "satış" denmemeli. Logo ORFICHE ayrı bir akış
   (e-ticaret/perakende) ve CRM siparişiyle toplanmamalı.
4. **Malzeme hareketi, seri lot ve koli** finans kapsamı dışında kalır. Stok miktarı ve değeri Logo'dan okunur.
5. **Hedef-gerçekleşen** sorusunda hedef `new_satishedefleri`'nden (adet), gerçekleşen Logo faturalı satış adedinden
   gelir. Eşleme kitap düzeyinde `new_StokKodu = LG_411_ITEMS.CODE` üzerinden yapılır. Açık noktalar:
   - Yıl kodu etiketten okunmalı. "2000" ve "1991" etiketli kümeler iş tarafı onaylamadan kullanılmamalı.
   - Tekrar eden 114 anahtar grubu ayıklanmalı.
   - BMT'nin Logo cari/kanal karşılığı (CLCARD.SPECODE2 ya da temsilci) henüz ölçülmedi. Kişi ya da kanal düzeyinde
     hedef-gerçekleşen sorulursa önce bu eşlemenin kurulması gerekir.
   - Hedefin tutar karşılığı yok; TL hedef sorulursa "hedef yalnız adet olarak tutuluyor" denmeli.
6. Pasif kuralı her CRM tablosunda uygulanır: `statecode=0` ve statuscode etiketi Pasif değil. Sevkiyat ve malzeme
   hareketinde hemen hemen bütün kayıtlar etkin. Sipariş satırında statuscode anlamlı değil: sevk edilmiş satırların
   çoğu "Yeni" görünüyor. Sipariş durumu `new_siparis.statuscode`'dan okunmalı.
