# Kitap pazarı veri kaynağı — `API_URUN_DB` (Logo prod .25): uçtan uca inceleme ve ekran kullanım haritası

> §0 günceldir; §1–§10 ilk inceleme (arşiv dahil) olarak durur.

Ölçüm: 2026-09-29. Bütün rakamlar test sunucusundan `zekiai` hesabıyla doğrudan SQL ile (`connector_from_file`, köprü env'i,
`OPTION (MAXDOP 2)` — .25 canlı ERP) alındı. Betikler oturum çalışma klasöründeydi (`/tmp/claude-kpazar/derin{1,2,3}.py`).

## 0. Güncelleme (2026-09-29 akşam) — kullanılan kaynaklar ve kurulan yapı

**Kullanıcı kararı:** müşteri yalnız `basari_list`, `prefix_list` ve `urun_list` görünümünü kullanıyor; diğerleri
(`urun_list_BACKUP` arşivi, `LOGO_TARCIN_ITEM_LIST`, `urun_raf`, `LOGO_TO_BASARI`, `URUN_LIST_TO_LOGO`) dikkate alınmaz.
Aşağıdaki §4–§5'teki arşiv ölçümleri (2025 çıkış endeksi, korelasyon 0,92–0,94, ×3,0) **yöntemin sınaması olarak
kalır, üründe kullanılmaz**; üründeki endeks portalın kendi gece görüntülerinden oluşur (en az iki görüntü gerekir).

**`urun_list` = `basari_list` ∪ `prefix_list`** (`UNION ALL`): Başarı satırları «Tedarikci: Başarı Dağıtım», Prefix
satırları «Tedarikci: Prefix»; marka boş; Prefix'te stok = `available_stock` (site stoğu, 386.124/386.124), fiyat =
`list_price`, kategori/yazar/durum/D&R fiyatı yok. Portal ayrıntıyı kaybetmemek için iki tabloyu doğrudan okur.

**D&R alanlarının anlamı** (D&R Prefix servis belgesi «Xml-Service», kullanıcı verdi; veriyle karşılaştırıldı):

| Alan | Anlam | Veride |
|---|---|---|
| `deleted` | 1 = D&R ve İdefix sitelerinden silinmiş | 382.203 satır 1; bunların 153.167'si Prefix B2B'de hâlâ satışta (1,53 M adet) |
| `sale_status_code` | Siteler: 0 satışa açık, 1 stokta yok, 4 satış dışı | silinmişlerde hep 4; etkinlerde 0 |
| `available_stock` | D&R + İdefix sitelerinin toplam stoğu | 999 (1.092), 500.000, 10.000.014 gibi yer tutucular var → ≥999 saklanmaz |
| `b2bstock` + `prefix_sale_status` | Prefix B2B stoğu ve durumu (0 stokta yok, 1 satışa açık) | 155 bin başlıkta stok |
| `dr_price` / `list_price` | D&R satış fiyatı / liste fiyatı | ortalama %80 |
| `row_num` | servis sayfa satır no (sayfa = 20.000) | üst sınır 406.124, satır 386.124 → **17. sayfa (320.001–340.000) yazılmamış** |
| API'de olup tabloda olmayan | yazar/kişiler, Prefix indirimli fiyat ve oranı, ürün özellikleri, görsel, teslim süresi | — |

Başarı'daki `rc`, `pc`, `rn` iş verisi değil: kaynağın bildirdiği toplam kayıt, sayfa, satır no (2026-09-25:
234.841 bildirildi, 234.705 yazıldı).

**Kurulan (dal `claude/kitap-pazari-arastirmasi-db-61a1b8`):** `backend/semantic_bridge/pazar_dagitim.py` +
`pazar_dagitim_api.py` (`/api/v1/pazar/dagitim/*`), tablolar `semantic_pazar_dagitim_{titles,obs,snapshots,barkod,meta}`
(yalnız değişen satır), zamanlayıcı `timas-pazar-dagitim.timer` (06:15). Ekranlar (yeni sayfa yok, kullanıcı kararı):
Stok listesinde «Dağıtımcıda» kolonu ve süzgeci (Başarı'da baskısı yok görünen / tükenmiş), Bitecekler ve Fazla stokta
kolon, kitap detayında «Dağıtımcı ve perakende» kutusu; Pazar › Özet'te «Dağıtımcı nabzı» (kategori / yayınevi / ay,
TİMAŞ grubu payı; iki görüntü birikene kadar boş). İşaret yalnız TİMAŞ grubunda (başlıklarının ≥%80'i TİMAŞ Logo'sunda
kartı olan marka; dağıttığı başka şirket markaları dahil, perakendede satılan tek tük kitap hariç).

**Gerçek veri kabulü (yan köprü :8788, gerçek oturum, 2026-09-29):** baskısı yok görünen **514**, Başarı'da tükenmiş
**1.121** kitap; kaynağa doğrudan SQL ile bağımsız referans: 514/514 ve 1.121/1.121, fazla 0, eksik 0.

## 1. Özet

1. `API_URUN_DB`, **Başarı Dağıtım** kataloğunun (235 bin başlık, 2.526 yayınevi) ve **D&R** B2B kataloğunun (386 bin başlık)
   kopyasıdır; ayrıca Başarı kataloğunun **35 tarihli görüntüsü** (2024-03-21 → 2026-01-01, 7,5 M satır) var.
2. **Satış hızı vekili doğrulandı:** TİMAŞ'ın 2025'te Başarı'ya kitap bazında sevkiyatı (Logo) ile Başarı deposundaki stok
   hareketi arasında korelasyon **0,92–0,94** (2.150 barkod). Sıralama güvenilir; mutlak adet ise görüntü aralığı yüzünden
   **~3 kat eksik** (Logo net sevk 227.590 ↔ arşiv düşüşü 75.321). → «Endeks» olarak gösterilir, adet olarak değil.
3. **Tek eksik tarih:** arşiv 1 Ocak 2026'da duruyor; güncel iki tablo tek görüntü ve üzerine yazılıyor. İleriye dönük
   her şey bizim gece görüntümüze bağlı (bkz. §5 F1).
4. **TİMAŞ eşleşmesi %99:** Başarı'daki 4.326 TİMAŞ grubu başlığın 4.283'ü Logo 2026 barkoduyla (`LG_411_UNITBARCODE`) bağlanıyor.
5. En büyük boşluk **Pazar ve rakip (M39)** ekranında: bugün kaynağı ve tazeliği bilinmeyen CRM «Rakip Kitap» (≈30 bin)
   kullanılıyor. Bu veri onun yerine geçer ve yanına satış hızı, yeni çıkan, yeni baskı, fiyat endeksi ekler.

## 2. Erişim ve kaynak

- `zekiai` önce yanlışlıkla `db_datawriter`'dı (okuma yok, yazma var); BT 2026-09-29'da **yalnız `db_datareader`** yaptı.
  Bu veritabanına hiçbir koşulda yazılmaz. Görünüm tanımları (`VIEW DEFINITION` yok) okunamıyor.
- `.25`'teki diğer veritabanlarına (`LOGO_DBN`, `LogoHizliSatisDB`, `LogoRobotPosDb`, `YEDEKTBLDB`, `PRODEYS`, `BORDRO_DB`,
  `SmIntegrationDb*`, `SYNC_LOGOTIGER*`) erişim yok.
- **Kim dolduruyor, ne sıklıkla — bilinmiyor.** İpuçları: `URUN_LIST_TO_LOGO` (stok adı, yayınevi, ürün türü, fiyat, KDV),
  `LOGO_TARCIN_ITEM_LIST` (Logo'da «TARÇIN» özel kodlu 7.064 ürün), `urun_raf` (29 raf: Dünya Edebiyatı, Timaş Çocuk, Yuzu,
  Kutu Oyunları…). Büyük olasılıkla TİMAŞ'ın perakende/e-ticaret tarafı başka yayınevlerinin kitaplarını Başarı API'sinden
  Logo'ya almak için kurmuş. Güncel tablolar 2026-09-25 11:04 (Başarı) ve 10:47 (D&R) tarihli. → BT'ye sorulacak.

| Tablo | Satır | İçerik | Zaman |
|---|---:|---|---|
| `urun_list_BACKUP` | 7.525.932 | Başarı kataloğu görüntüleri, 233.599 barkod | 35 görüntü: 2024 aylık, 2025-02'den beri ayın 1'i ve 15'i |
| `basari_list` | 234.705 | Başarı kataloğu, güncel | 2026-09-25, tek görüntü |
| `prefix_list` | 386.124 | D&R B2B kataloğu, güncel (6.263 marka) | 2026-09-25, tek görüntü |
| `LOGO_TARCIN_ITEM_LIST` | 7.064 | Logo «TARÇIN» ürünleri | 2024-12-31 |
| `urun_raf` | 29 | Raf adları | 2026-01-21 |
| Görünümler | — | `urun_list`, `URUN_LIST_TO_LOGO`, `LOGO_TO_BASARI` (Logo↔Başarı barkod/fiyat) | — |

## 3. Veri kalitesi

**Başarı (`basari_list`) — iyi.** Doluluk: barkod, ad, marka, kategori, fiyat, iskonto, stok durumu, görsel %100; yazar %98,
basım yılı %96, sayfa %95, tanıtım metni %90, kâğıt %90, kapak %91, baskı sayısı %87, çevirmen %21.
- Kategori iki seviyeli (`Üst>Alt`): 38 üst, 630 alt kategori.
- `ebat` («çokebatlı») ve `renk` («karışıkçokrenkli») bilgi taşımıyor. `kdv` hep 0.00.
- `stok_durum`: Satışta 147.830 · Baskısı Yok 52.594 · Temin Edilemiyor 33.863 · Satış Dışı 418.
- `iskonto` (dağıtımcı iskontosu): en sık %35, %30, %40, %38.
- `depo_stok` başlıkların %33'ünde sıfırdan büyük.

**D&R (`prefix_list`) — fiyat ve varlık için iyi, stok için dikkat.**
- Dolu alanlar: `list_price` %100, `dr_price` %95, `bread_crumb` kategori yolu %100 (ör. `Kitap|Çocuk ve Gençlik|Gençlik 10+ Yas|Roman/Öykü`),
  kapak tipi %100, uzun tanıtım %99.
- `available_stock` yalnız 3.920 satırda dolu. Stok bilgisi `b2bstock`'ta: 155 bin başlıkta > 0, toplam ≈1,78 M adet.
- `deleted=1` 382.203 satırda; bu satırların hiçbirinde `available_stock` yok, ama `b2bstock` var. Anlamı doğrulanmadı
  (büyük olasılıkla «D&R sitesinde listelenmiyor»). Süzgeç olarak kullanılmaz.
- D&R satış fiyatı ortalama liste fiyatının **%80'i**. Başarı başlıklarının 184.894'ü D&R'de de var; 130.418'inde liste
  fiyatı iki kaynakta aynı.

**Arşiv (`urun_list_BACKUP`)**
- `tarih` metin (`'2025-12-01'`), görüntü başına ≈209–224 bin satır; barkod başına görüntüde tek satır (2024-08: 01 ve 07 iki görüntü).
- Katalog büyüyor: 209 bin → 224 bin başlık. Ortalama liste fiyatı **137 ₺ → 226 ₺** (21 ayda +%65). Aynı barkodlarda
  2025-01 → 2026-01 fiyat oranı **×1,31**; 110.821 başlık zamlandı.
- Yeni çıkan başlık: görüntü başına 400–800 (15 günlük), Ekim–Aralık'ta yükseliyor.
- Baskı sayısı artan (yeni baskı): 2025 boyunca 6.334 başlık.

## 4. Doğrulama: stok düşüşü gerçekten satış mı?

Logo'da Başarı cari hesabı: `12001.01.BA104` «BAŞARI DAĞITIM KİT.KIRT.YAY.TİC.AŞ.» (LOGICALREF 13183, etkin).
TİMAŞ → Başarı 2025: 12.114 satış satırı, 257.048 adet (`TRCODE 8`), iade 6.237 (`TRCODE 3`). 2026 (29 Eylül'e kadar): 229.965 adet.
Başarı TİMAŞ'ın büyük bir kanalı.

Kitap bazında (2025, TİMAŞ grubu, 2.150 eşleşen barkod):

| Karşılaştırma | Korelasyon |
|---|---:|
| Logo sevk ↔ Başarı stok girişi | 0,92 |
| Logo net sevk ↔ Başarı stok düşüşü | 0,94 |
| Logo sevk ↔ Başarı stok düşüşü | 0,94 |

- Toplamlar: Logo net sevk 227.590 · arşiv girişi 74.498 · arşiv düşüşü 75.321 → **kalibrasyon katsayısı ≈3,0**.
  15 günlük görüntüler, iki görüntü arasında gelip giden stoğu göremez.
- Örnek: İyilik Timi — Logo 11.850 adet sevk, arşiv düşüşü 2.596. Sıralamada ilk sırada, hem Logo'da hem arşivde.
- **Karar:** rakip kitaplar için «Başarı çıkış endeksi» (arşiv düşüşü) sıralama ve eğilim için kullanılır. Adet gösterilecekse
  «≈ tahmini, ×3,0 TİMAŞ kalibrasyonu» etiketiyle ve aralık olarak gösterilir. Bu tüketiciye satış değil, dağıtımcıdan
  perakendeye çıkıştır. «Pazar payı» diye sunulmaz (M39 kuralı).

## 5. Bulgular (ekranlara girecek türden)

**Kategori (Başarı güncel)**

| Üst kategori | Başlık | Satışta | Ort. fiyat ₺ | TİMAŞ grubu başlık | 2025 çıkış endeksi | TİMAŞ'ın endeks payı |
|---|---:|---:|---:|---:|---:|---:|
| Edebiyat | 82.209 | 54.813 | 273 | 854 | 669.298 | %1,8 |
| Çocuk Kitapları | 59.647 | 39.185 | 191 | 2.165 | 674.122 | %8,4 |
| Tarih | 13.934 | 9.128 | 373 | 523 | 37.213 | %4,2 |
| İslam | 12.594 | 8.012 | 381 | 105 | 30.322 | %7,6 |
| Din | 2.774 | 1.567 | 316 | 125 | 8.100 | %18,8 |
| Psikoloji | 3.192 | 2.276 | 340 | 90 | 25.731 | %2,8 |

**Yayınevleri (2025 çıkış endeksi, ilk 10):** İş Bankası 139 bin · Masa Kitap 134 bin (39 başlıkla; Celal Şengör'ün kitapları) ·
Altın Kitaplar 97 bin · YKY 85 bin · Kelime 61 bin · Can Sanat 46 bin · Günışığı 37 bin · Ötüken 33 bin · Can Çocuk 32 bin ·
**Timaş Çocuk 30 bin** (10.). İlk Genç Timaş 20 bin (14.), Genç Timaş 15 bin (19.).

**Yeni çıkan (2025'ten beri arşive ilk giren):** Ketebe 318, İş Bankası 314, YKY 256, Everest 243, İndigo 215.
**Yeni baskı (2025):** İş Bankası 1.482, YKY 848, İletişim 296, Ötüken 219, **Timaş Çocuk 211, Timaş Yayınları 150**.

**TİMAŞ'ın rafta görünürlüğü**
- Başarı «Satışta»: Timaş Çocuk 1.069, Timaş Yayınları 743, Timaş Tarih 330, Genç Timaş 254, İlk Genç Timaş 195, Gülce 165.
- D&R: Timaş Çocuk 1.385 başlık (793'ünde B2B stok var, 28.587 adet), Timaş Yayınları 1.346 (892; 12.488 adet).
- Başarı'da satışta olup **D&R kataloğunda hiç olmayan** TİMAŞ başlığı: 321. D&R B2B stoğu sıfır olan: 540.
- **Başarı'da «Baskısı Yok» görünen ama Logo'da stoğu olan TİMAŞ başlıkları:** Timaş Çocuk 163, Timaş Yayınları 114,
  Timaş Tarih 30, Genç Timaş 24, İlk Genç 21, Gülce 20. Örnekler: Levent ve Sevimli Kuzu 8, Levent Bayram Ziyaretinde 4,
  Levent İlk Okuma Kitaplarım dizisi, Mini Masallar dizisi. Bu kitaplar bizde var ama dağıtımcı kitapçılara «baskısı yok»
  diyor olabilir; satış kaybı adayı. **Not:** adetler ham bakiyedir (planlı üretim girişi ayıklanmadı). Ekrana Stok modülünün
  formülüyle (`stock_sql/logo_bakiye.sql`, `STOCK_EXCLUDE_PLANNED`) girmeli.

## 6. Ekran kullanım haritası

Öncelik = iş değeri × verinin hazır olması. Rota ve dosyalar `src/canvas/nav/navModel.ts` ve `backend/semantic_bridge/`'ten.

| # | Ekran (rota) | Bugün | Bu veriyle eklenecek | Kullanılan alanlar |
|---|---|---|---|---|
| 1 | **Pazar ve rakip / Rakipler ve emsal** (`/pazar-arastirma`, `pazar.py`, `pazar_api.py`) | CRM «Rakip Kitap», kaynak ve tazelik bilinmiyor | Rakip kataloğu Başarı+D&R olur (tazelik şeridi gerçek tarih gösterir). Yeni sekmeler: **Pazar nabzı** (kategori × ay çıkış endeksi, TİMAŞ endeks payı), **Yayınevi karnesi** (başlık, yeni çıkan/ay, yeni baskı, endeks, ort. fiyat, iskonto), **Çok çıkanlar** (alt kategori başına ilk 20, 15 günlük), **Fiyat endeksi** (kategori ortalama fiyat eğrisi). Emsal bulucu 235 bin başlıktan arar. | marka, kategori, yazar, fiyat, iskonto, baskı sayısı, basım yılı, sayfa, kapak, stok farkı, ilk görünme |
| 2 | **Stok** (`/stok`, `stock.py`) + **Baskı önerisi** (`/yonetim-raporlari/baski-oneri`, `management/baski_oneri.py`) | Logo bakiye, CRM stok, tükenme süresi | Kitap satırına **Başarı depo stoğu**, **D&R B2B stoğu**, **dağıtımcıda tükendi** işareti. Yeni liste **«Dağıtımcıda görünmüyor»**: Başarı'da Baskısı Yok/Temin Edilemiyor, Logo’da stok var (≈385 başlık). Baskı kararında dağıtımcı stoğu da hesaba girer (kanalda bekleyen adet). | barkod, stok_durum, depo_stok, b2bstock |
| 3 | **Fiyatlama ve maliyet — M9** (`/fiyatlama`, `pricing/`) | Rakip fiyatı elle giriliyor (`semantic_pricing_market`) | Kitabın alt kategorisi + sayfa aralığı + kapak için **rakip liste fiyatı dağılımı** (medyan, p25–p75), **₺/sayfa**, **D&R satış fiyatı**; elle giriş yerine otomatik öneri (elle düzeltme kalır). Backlist zam önerisinde «rakipler bu kategoride 2025'te ×1,31 zamladı». | fiyat, sayfa, kapak, kategori, dr_price, list_price, arşiv fiyatı |
| 4 | **İlk baskı tahmini — M10** (`/ilk-baski`, `management/ilk_baski*.py`) | Yalnız TİMAŞ'ın benzer kitapları | Benzer **rakip** kitapların arşive ilk girişinden sonraki 6/12 aylık çıkış endeksi ve kaçıncı baskıya ulaştıkları. İlk baskı adedinde «bu alt kategoride yeni kitapların %X'i ilk yıl 2. baskıya geçti». | ilk görünme, baskı sayısı değişimi, stok farkı |
| 5 | **Başvurular / Yayın kurulu — M1** (`/basvurular`, `/yayin-kurulu`) | Ön okuma (tür, kitle, tema), editör raporu | Başvuru kartına **pazar kutusu**: alt kategorinin çıkış eğilimi, rakip başlık sayısı, son 12 ayda çıkan yeni başlık, en çok çıkan 5 rakip, yazarın başka yayınevindeki kitaplarının endeksi. | kategori, yazar, çevirmen, stok farkı |
| 6 | **Kanal karnesi / Cari eşleme** (`/kanallar`, `channels/scorecard.py`) | Logo sell-in, iskonto, iade | Başarı kanalı için **sell-in (Logo) ↔ sell-through (Başarı çıkışı) ↔ kanalda bekleyen (Başarı stoğu)**; iade riski erken uyarısı (sevk yüksek, çıkış düşük). | depo_stok farkı + Logo `12001.01.BA104` hareketleri |
| 7 | **Kampanyalar** (`/kampanyalar`) + **E-ticaret Farklar** (`/e-ticaret`) | Site ↔ Logo ↔ CRM fiyat farkı | **D&R fiyatı ↔ site fiyatı ↔ liste fiyatı** farkı; D&R'nin indirim yaptığı TİMAŞ kitapları; kampanya adaylarında rakip indirim seviyesi. | dr_price, list_price, iskonto |
| 8 | **Yazar ilişkileri** (`/yazar-iliskileri`, `author_growth.py`) | Yazarın Logo satış eğilimi | Yazarın **tüm yayınevlerindeki** kitaplarının endeksi (rakipte yükselen yazar, bizdeki yazarın rakipteki kitabı). | yazar, marka, stok farkı |
| 9 | **Panolar / Zeki AI sohbet** (`board.py`, `chat_portal_areas.json`) | Logo + CRM | `semantic_market_*` tabloları yeni alan olarak eklenir: «çocuk kitaplarında en çok çıkan 10 rakip», «Timaş Çocuk'un endeks payı nasıl değişti». | özet tablolar |
| 10 | **SEO: Satıştan kalkan / Google Alışveriş** (`seo_geo/sunset.py`, `shopping.py`) | Site ürün akışı | Başarı «Baskısı Yok» ↔ site satışta çelişkisi; ISBN/fiyat akışı denetiminde D&R fiyatı. | stok_durum, dr_price |

## 7. Altyapı (hiçbir ekran bunsuz başlamaz)

- **F1 — Gece görüntüsü:** her gece `basari_list` ve `prefix_list` okunur, `semantic_market_*` tablolarına **yalnız değişen
  satırlar** yazılır (barkod, tarih, stok, fiyat, iskonto, durum, baskı sayısı). Başarı'da 15 günde ≈42 bin satırın stoğu
  değişiyor, bu yüzden günlük fark küçük kalır. Tam kopya yılda ≈226 M satır eder, yapılmaz. Kalıp M39'daki gibi:
  `timas-pazar.timer` → `POST /api/v1/pazar/run-due` → `apply_snapshot()`. Kaynağın ne sıklıkla tazelendiğini bu iş
  ilk haftada kendisi ölçer.
- **F2 — Arşivi bir kez içe al:** 35 görüntüden barkod × dönem çıkış/giriş/fiyat/baskı özeti (7,5 M satırdan ≈3 M fark
  satırı), gece işiyle aynı tabloya.
- **F3 — Eşleme:** barkod anahtarı `seo_geo/crm.py: ean_key()`. TİMAŞ kitabı: EAN → CRM `new_ean13`/`new_isbn13` →
  `new_StokKodu` = Logo `ITEMS.CODE` (ya da doğrudan `LG_{firma}_UNITBARCODE`). Marka adları kaynaklar arasında farklı
  («Timaş İlk Genç» ↔ «İlk Genç Timaş», «Doğan Egmont» ↔ «Doğan ve Egmont Yayıncılık»), bu yüzden marka eşleme tablosu
  gerekir. Kategoriler için Başarı 630 alt kategori ↔ D&R `bread_crumb` ↔ TİMAŞ kategori ağacı (`categories.py`); eşleme
  M39'daki kapalı küme seçimle yapılır ve insan onaylar.
- **F4 — Endeks tanımı tek yerde:** `çıkış = Σ max(0, önceki_stok − stok)` ardışık görüntüler arasında. Kalibrasyon katsayısı
  her gece TİMAŞ'ın Logo sevkiyle yeniden ölçülür ve ekranda gösterilir. Görüntü aralığı değişirse (15 gün → 1 gün) katsayı
  değişir, eski ve yeni dönem ayrı etiketlenir.
- **F5 — Erişim yolu:** modül SQL'i Logo bağlantı dosyasıyla `API_URUN_DB.dbo.…` üç parçalı adla okur (aynı sunucu). Sohbet motoru
  bu veritabanını doğrudan taramaz, yalnız `semantic_market_*` tablolarını görür.

## 8. Kurallar ve sınırlar

- Kaynağa yazılmaz; T-soft, CRM ve Logo'ya da yazılmaz.
- «Pazar payı», «pazar büyüklüğü» denmez. Doğru adlar: «Başarı çıkış endeksi», «TİMAŞ'ın Başarı endeks payı».
  Başarı tek dağıtımcıdır. D&R ve Kitapyurdu doğrudan alımları, okul ve kurumsal satışlar bu veride yok.
- Ekranda teknoloji adı yok. Kaynak adı olarak «Başarı Dağıtım kataloğu» ve «D&R kataloğu» yazılır.
- Adet gösterilirse aralık ve «tahmini» etiketiyle gösterilir. Sıralama ve eğilim ana kullanımdır.

## 9. Açık sorular

1. `API_URUN_DB`'yi kim, hangi sıklıkla güncelliyor? Arşiv neden 2026-01-01'de durdu? (BT)
2. D&R `deleted` ve `prefix_sale_status` alanlarının anlamı.
3. «Dağıtımcıda görünmüyor» listesindeki başlıklar için Başarı'ya bilgi gidiyor mu? Yani bu satış kaybı mı, yoksa bilinçli
   bir liste dışı bırakma mı? (Satış / Başarı sorumlusu)

## 10. Önerilen sıra

| Faz | İş | Ekrana çıkan |
|---|---|---|
| 1 | F1 gece görüntüsü + F2 arşiv içe alma + F3 barkod/marka eşleme + F4 endeks | — (altyapı) |
| 2 | Stok/Baskı önerisine dağıtımcı stoğu + «Dağıtımcıda görünmüyor» listesi | 2 |
| 3 | Pazar ve rakip: kaynak değişimi + Pazar nabzı + Yayınevi karnesi + Çok çıkanlar | 1 |
| 4 | Fiyatlama otomatik rakip fiyatı + İlk baskı rakip emsali | 3, 4 |
| 5 | Başvuru pazar kutusu, Kanal karnesi Başarı, Kampanya/E-ticaret D&R fiyatı, Yazar, Zeki AI alanı | 5–9 |
