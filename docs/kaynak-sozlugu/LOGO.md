# TİMAŞ Logo ERP — kaynak sözlüğü

Üretim: 2026-10-01T04:54 · Veritabanı: Logo (LOGODATABASEN, canlı .25) · Makine okunur sürüm: [`logo-sozluk.json`](logo-sozluk.json) (sunucu kopyası: `/data/nanobaseai/bi/acceptance/claude-review-20261001/sozluk/logo-sozluk.json`).

Bu belge Logo tablolarının **iş anlamını** derler; bir doğruluk/kabul belgesi değildir. Her anlamın kaynağı ve güven düzeyi ayrı yazılır. Eski semantik katalog yalnız **aday anlam** kaynağıdır (sertifika durumu korunmuştur).

## Kapsam ve yöntem

- Firma kopyaları: **411 = 2026-01-01–2026-12-31**, **211 = 2021-01-01–2025-12-31**. Aynı şirketin yıl kopyaları; ayrı şirket değil. Aynı DB'de 211/411 dışında 123 firma numarası daha var.
- Ölçüm penceresi: 2026-09-01 ≤ DATE_ < 2026-10-01 (411); kart/parametre tablolarında tüm tablo; PAYTRANS'ta DATE_ vade tarihidir.
- Ölçüm kuralı: Yalnız SELECT; oturum READ UNCOMMITTED + LOCK_TIMEOUT 20000; toplulaştırılmış (GROUP BY / COUNT / SUM); ham satır çekilmedi.
- Gönderilen sorgu: **357** (Logo'ya; hepsi SELECT). Hatalı: 71 — tamamı betik kaynaklı (GROUPING SETS 32 ifade sınırı, toplam içinde alt sorgu, belirsiz kolon adı), düzeltilip yeniden koşuldu. **Sonuç olarak dönen 1205 deadlock: 0**, kilit zaman aşımı (1222): 0. Not: ortak yardımcı `query()` 1205'te en çok iki kez sessiz yeniden dener; bu iç denemeler kayda alınmadı. En uzun sorgu 22.3 sn, medyan 410 ms.
- Güven ölçeği: **yüksek** = proje kararı/golden/motor + canlı ölçümle tutarlı; **orta** = üretici sözlüğü (LDDS) ya da eski sertifikalı eşleme; canlı çelişki yok; **düşük** = yalnız eski aday/takma ad; **tahmin** = yalnız kolon adından çıkarım.
- Kaynak kısaltmaları: `ldds` üretici veri sözlüğü, `proje` iş tanımları/kurallar, `motor` yeni finans sözleşmesi, `golden` altın referans SQL, `eski` emekli katalog, `olcum` bu çalışmanın canlı ölçümü, `ad_cikarimi` yalnız kolon adı.
- Eski katalog (yedek, salt okunur): kavram durumları {'CERTIFIED': 5023, 'REJECTED': 387, 'CANDIDATE': 1204, 'DISCOVERED': 9, 'DEPRECATED': 1}; türler {'COLUMN': 3831, 'DIMENSION_VALUE': 2135, 'METRIC': 155, 'RELATIONSHIP': 19, 'DEFAULT_FILTER': 258, 'ENTITY': 226}; sözlük {'PROPOSED': 31739, 'APPROVED': 8226, 'DROPPED': 1187}.

## En önemli bulgular

- **Fatura başlığı = satırların toplamı (KDV dahil).** 2026-09'da 7/8/2/3 türlerinin tüm faturalarında `INVOICE.NETTOTAL = Σ STLINE.VATMATRAH + Σ STLINE.VATAMNT`; `GROSSTOTAL = Σ TOTAL`, `TOTALDISCOUNTS = Σ iskonto satırı TOTAL`, `TOTALDISCOUNTED ≈ Σ LINENET`. NETTOTAL ödenecek tutardır; satır net cirosu LINENET'tir (KDV hariç).
- **Net ciro üç farklı sayı verir (2026-09):** motor (satır, LINETYPE 0) 245.632.081,09 ₺; hizmet satırları dahil 245.350.590,51 ₺; başlık NETTOTAL (KDV dahil) 245.563.910,06 ₺. Satış KDV payı ≈ %0,1 (kitap) olduğundan fark küçük; asıl fark hizmet satırları ve TRCODE 3 içindeki 1,28 Mn ₺ hizmet iadesinden gelir.
- **STLINE.TRCODE 9 hiçbir zaman malzeme satırı değil:** 2026-09'daki 26 satırın hepsi LINETYPE 4 (hizmet). Motorun `TRCODE IN (7,8,9) AND LINETYPE=0` koşulu 9'u fiilen dışlar.
- **Fatura sayısı çelişkisi:** motor 7/8/9 sayar (13.680 Eylül, 88.757 2026), proje KPI ve eski sertifikalı tanım 2/3/7/8/9 (13.800 / 92.137).
- **Maliyet güncel değil:** 2026-09 satış satırlarının yalnız %0,8'inde OUTCOST dolu → kâr/marj güncel aylarda hesaplanamaz.
- **Ödeme kapama kullanılmıyor:** 2026 PAYTRANS'ta 139.648 satırın 0'ında CROSSREF, 14'ünde PAID dolu; yaşlandırma ancak yaklaşık (FIFO/DSO) yapılabilir. PAYTRANS.DATE_ vade tarihidir (faturada ort. +40,9 gün), işlem tarihi PROCDATE.
- **Kaynak referansları modüle göre farklı tabloya gider:** CLFLINE.SOURCEFREF MODULENR 7'de banka **satırına** (BNFLINE), PAYTRANS.FICHEREF MODULENR 5'te cari **satırına** (CLFLINE), 7'de BNFLINE'a gider (LDDS/ad beklentisi fiş başlığıydı; başlığa eşleşme %0).
- **IOCODE iki tabloda farklı kodlanır:** STLINE'da çıkış 4 (1 giriş, 2 ambar giriş, 3 ambar çıkış), STFICHE'de çıkış 3 (1 giriş, 2 ambar).
- **LDDS ile veri çelişkisi:** LDDS belge kodu listesi çek/senet cari hareketini MODULENR 3 sayar; veride 6 (CSROLL'a %100). CSCARD.CURRSTAT etiketleri de proje kuralıyla (Kural 12) çelişir.
- **Kanal kartların %86'sında boş** (CLCARD.SPECODE2) ama 2026-09 satış cirosunun yalnız %2,5'i boş kanallı carilerden; kanal değerlerinde yazım varyantları var (BAYI/BAYİ, YURTDIŞI/YURTDISI).
- **Özel görünüm tanımları okunamıyor:** hesap (zekiai) VIEW DEFINITION iznine sahip değil; 1.431 özel görünümün 0'ının SQL'i okunabildi.
- **Yedek kopyalar canlı adla yan yana:** `LG_411_01_STLINE_yedek1` (1,14 Mn satır), `LG_411_01_STLINE_20260430_RETAMOUNT`, `BCKP_030826LG_411_01_STLINE`, `LG_411_FAYEAR_YEDEKK`; motor bunları seçmemeli.

## 1. Tablo aileleri (dolu olanlar)

Satır sayıları `sys.partitions`'tan (2026-10-01). `dönem` aileleri `LG_<firma>_01_<AİLE>`, `firma` aileleri `LG_<firma>_<AİLE>`, `ortak` tablolar `L_`. Ad kaynağı: `ldds` üretici Türkçe açıklaması, `proje/olcum` proje belgesi veya ölçüm, `ad_cikarimi` yalnız tablo adından (tahmin). Sınıf kaynağı: `elle` = bu çalışma (çoğu ad + LDDS açıklamasına dayanır), `ldds_aciklama` = üretici açıklamasından, `ad` = yedek adı kalıbı, `tahmin` = dayanaksız.


### hareket_satiri (33)

| Aile | Kapsam | İş adı | Ad kaynağı | 411 satır | 211 satır | Sınıf kaynağı | Not |
|---|---|---|---|---:|---:|---|---|
| `STLINE` | dönem | Malzeme hareketleri | ldds | 2.153.392 | 12.195.380 | elle |  |
| `EMFLINE` | dönem | Muhasebe hareketleri | ldds | 307.857 | 1.828.007 | elle |  |
| `ORFLINE` | dönem | Sipariş hareketleri | ldds | 227.145 | 912.637 | elle |  |
| `STSHIPPEDAMOUNT` | dönem | Sevk edilen miktar izleme | ad_cikarimi | 212.945 | 637.673 | elle |  |
| `PREACCDISTDETLINE` | dönem | Ön muhasebe dağıtım detay satırları | ad_cikarimi | 210.404 | 888.669 | elle |  |
| `ACCDISTDETLN` | dönem | Muhasebe dağıtım detay satırları | ad_cikarimi | 167.558 | 780.678 | elle |  |
| `PAYTRANS` | dönem | Ödeme/Tahsilat hareketleri | ldds | 139.648 | 1.102.705 | elle |  |
| `EARCHIVEDET` | dönem | e-Arşiv belge detayları | ad_cikarimi | 120.388 | 517.162 | elle |  |
| `CLFLINE` | dönem | Cari hesap hareketleri | ldds | 119.838 | 840.348 | elle |  |
| `EBOOKDETAILDOC` | dönem | e-Defter belge detayları | ad_cikarimi | 114.544 | 572.288 | elle |  |
| `EINVOICEDET` | dönem | e-Fatura detayları | ad_cikarimi | 38.670 | 192.829 | elle |  |
| `DEFNFLDSTRANV` | dönem | Tanımlı alan değerleri (hareket) | ad_cikarimi | 31.109 | 171.685 | elle |  |
| `BNFLINE` | dönem | Banka hareketleri | ldds | 21.323 | 119.617 | elle |  |
| `CSTRANS` | dönem | Çek/Senet hareketleri | ldds | 9.177 | 21.611 | elle |  |
| `STLINEEXCH` | dönem | Stok satırı döviz bilgileri | ldds+elle | 5.686 | 26.397 | elle |  |
| `COSTDISTPEG` | dönem | Maliyet dağıtım bağları | ad_cikarimi | 5.143 | 29.643 | elle |  |
| `POLINE` | firma | Üretim emri satırları | ldds+elle | 4.731 | 28.237 | elle |  |
| `TAXDECLLINE` | firma | Vergi beyannamesi satırları | ad_cikarimi | 3.502 | 3.502 | elle |  |
| `INVEXIMLINES` | dönem | İthalat/ihracat satırları | ad_cikarimi | 3.486 | 16.032 | elle |  |
| `BNCREPAYTR` | firma | Banka kredi geri ödeme planı | ldds+elle | 2.956 | 2.764 | elle |  |
| `COSTDISTLN` | dönem | Maliyet dağıtım satırları | ldds+elle | 2.583 | 13.989 | elle |  |
| `QPRODLINE` | dönem | Hızlı üretim satırları | ldds+elle | 1.479 | 17.970 | elle |  |
| `KSLINES` | dönem | Kasa işlemleri | ldds | 1.377 | 7.921 | elle |  |
| `DISPLINE` | firma | Üretim operasyon (iş emri) satırları | ldds+elle | 1.287 | 7.683 | elle |  |
| `COSTDISTFC` | dönem | Maliyet dağıtım fişleri | ldds+elle | 1.262 | 7.210 | elle |  |
| `REPAYPLANSLN` | firma | Geri ödeme planı satırları | ldds+elle | 617 | 617 | elle |  |
| `INVOICEEXCH` | dönem | Fatura döviz tutarları | ldds | 377 | 1.636 | elle |  |
| `STFEXCH` | dönem | Malzeme fişi döviz tutarları | ldds | 50 | 1.620 | elle |  |
| `ORDLINEEXCH` | dönem | Sipariş satırı döviz tutarları | ldds | 14 | 2.705 | elle |  |
| `IMPSRVREL` | dönem | (tanımsız — yalnız ad) | – | 7 | 73 | elle |  |
| `EXIMHISTORY` | dönem | İthalat geçmişi | ldds | 3 | 19 | elle |  |
| `ORDFEXCH` | dönem | Sipariş fişi döviz tutarları | ldds | 2 | 420 | elle |  |
| `STLNIOPEGGING` | dönem | (tanımsız — yalnız ad) | – | 0 | 443 | elle | 211'de var, 411'de boş |

### belge_basligi (14)

| Aile | Kapsam | İş adı | Ad kaynağı | 411 satır | 211 satır | Sınıf kaynağı | Not |
|---|---|---|---|---:|---:|---|---|
| `STFICHE` | dönem | Stok fişleri | ldds | 126.815 | 620.137 | elle |  |
| `EMFICHE` | dönem | Muhasebe fişleri | ldds | 114.397 | 569.452 | elle |  |
| `INVOICE` | dönem | Faturalar | ldds | 101.874 | 502.826 | elle |  |
| `PERDOC` | dönem | Personel/kişi belgeleri | ldds+elle | 90.831 | 528.206 | elle |  |
| `ORFICHE` | dönem | Sipariş fişleri | ldds | 59.956 | 263.047 | elle |  |
| `CLFICHE` | dönem | Cari hesap fişeri | ldds | 5.365 | 23.453 | elle |  |
| `BNFICHE` | dönem | Banka fişleri | ldds | 2.563 | 17.254 | elle |  |
| `PRODORD` | firma | Üretim emirleri (baskı) | proje/olcum | 1.287 | 7.683 | elle |  |
| `CSROLL` | dönem | Çek/Senet bordroları | ldds | 950 | 6.633 | elle |  |
| `QPRODUCT` | dönem | Hızlı Üretim | ldds | 151 | 2.522 | elle |  |
| `TAXDECLHDR` | firma | (LDDS TR yok) Text Declaration Header Info | ldds_en | 25 | 25 | elle |  |
| `INVEXIMINFO` | dönem | İthalat / ihracat işlem fişleri | ldds | 3 | 19 | elle |  |
| `EXTRAINFO` | dönem | (tanımsız — yalnız ad) | – | 2 | 1 | elle |  |
| `INVOICEINTEL` | dönem | Fatura ek notları | ldds | 0 | 24 | elle | 211'de var, 411'de boş |

### kart (55)

| Aile | Kapsam | İş adı | Ad kaynağı | 411 satır | 211 satır | Sınıf kaynağı | Not |
|---|---|---|---|---:|---:|---|---|
| `SHIPINFO` | firma | Sevkiyat adresleri | ldds+elle | 382.337 | 319.253 | elle |  |
| `CLCARD` | firma | Cari hesap kartları | ldds | 257.378 | 255.748 | elle |  |
| `GUARANTOR` | dönem | Kefil/teminat kişileri | ldds+elle | 97.918 | 475.664 | elle |  |
| `BOMLINE` | firma | Reçete satırları | ldds+elle | 38.977 | 35.693 | elle |  |
| `OCCUPATION` | firma | Meslek tanımları | ldds+elle | 34.800 | 203.340 | elle |  |
| `ITEMS` | firma | Malzemeler | ldds | 32.859 | 29.759 | elle |  |
| `UNITBARCODE` | firma | Birim barkodları | ldds+elle | 27.078 | 24.393 | elle |  |
| `EMCENTER` | firma | Masraf merkezleri | proje/olcum | 17.448 | 16.500 | elle |  |
| `BOMASTER` | firma | Ürün reçetesi başlıkları | ldds+elle | 10.648 | 9.735 | elle |  |
| `BOMREVSN` | firma | Reçete revizyonları | ldds+elle | 10.648 | 9.735 | elle |  |
| `ITMBOMAS` | firma | Malzeme–reçete atamaları | ldds+elle | 10.647 | 9.734 | elle |  |
| `STCOMPLN` | firma | Karma koli bileşenleri | ldds+elle | 5.899 | 5.892 | elle |  |
| `CSCARD` | dönem | Çek/Senet kartları | ldds | 4.238 | 8.189 | elle |  |
| `EMUHACC` | firma | Muhasebe hesap planı | proje/olcum | 1.374 | 1.371 | elle |  |
| `FAREGIST` | firma | Sabit kıymet kayıtları | ldds+elle | 1.093 | 1.481 | elle |  |
| `FINTABLEITEM` | firma | Finansal tablo kalemleri | ldds+elle | 993 | 993 | elle |  |
| `SRVCARD` | firma | Hizmet kartları | ldds+elle | 232 | 232 | elle |  |
| `SRVUNITA` | firma | Hizmet kaydı-Birim ataması | ldds | 230 | 230 | elle |  |
| `CAMPAIGN` | firma | Kampanyalar | ldds+elle | 210 | 209 | elle |  |
| `PAYPLANS` | firma | Ödeme planları | proje/olcum | 188 | 187 | elle |  |
| `PAYLINES` | firma | Ödeme planı satırları | ldds+elle | 184 | 183 | elle |  |
| `BANKACC` | firma | Banka hesapları | proje/olcum | 118 | 115 | elle |  |
| `REPAYPLANS` | firma | Geri ödeme planları | ldds | 68 | 68 | elle |  |
| `OPERTION` | firma | Operasyonlar | ldds | 57 | 54 | elle |  |
| `ROUTING` | firma | Üretim rotaları | ldds | 57 | 54 | elle |  |
| `RTNGLINE` | firma | Üretim rota stırları | ldds | 57 | 54 | elle |  |
| `OPRTREQ` | firma | Operasyon ihtiyacları | ldds | 56 | 53 | elle |  |
| `WORKSTAT` | firma | İş istasyonları | ldds | 56 | 53 | elle |  |
| `WFTASK` | firma | İş akışı kartları | ldds | 48 | 48 | elle |  |
| `CLINTEL` | firma | Cari hesap istihbarat bilgileri | ldds | 37 | 37 | elle |  |
| `FAREGNEWVALUE` | firma | (tanımsız — yalnız ad) | – | 31 | 31 | elle |  |
| `DECARDS` | firma | İndirim/Masraf kartları | ldds | 26 | 22 | elle |  |
| `BNCREDITCARD` | firma | Banka kredileri (Port) | ldds | 17 | 98 | elle |  |
| `BNCARD` | firma | Banka kartları | proje/olcum | 14 | 14 | elle |  |
| `EBOOKINFO` | firma | e-Defter bilgileri | ad_cikarimi | 10 | 120 | elle |  |
| `SUPPEVALCRLN` | firma | (tanımsız — yalnız ad) | – | 10 | 10 | elle |  |
| `KSCARD` | firma | Kasa kartları | proje/olcum | 9 | 9 | elle |  |
| `FINTBLHEADER` | firma | Mali tablo kayıtları | ldds | 7 | 7 | elle |  |
| `PROJECT` | firma | Projeler | ldds+elle | 4 | 4 | elle |  |
| `FIRMDOC` | firma | Döküman katalog girişi(watermark) | ldds | 3 | 3 | elle |  |
| `MARKETPLACE` | firma | (tanımsız — yalnız ad) | – | 3 | 3 | elle |  |
| `REFLECT` | firma | Yansıtmalar | ldds | 3 | 3 | elle |  |
| `REFLECTTRANS` | firma | Yansıtma hareketleri | ldds | 3 | 3 | elle |  |
| `SUPPEVALCR` | firma | (tanımsız — yalnız ad) | – | 3 | 3 | elle |  |
| `FAEXPENSE` | firma | Sabit kıymet gider atamaları | ldds | 2 | 2 | elle |  |
| `MARK` | firma | Markalar | ldds | 2 | 2 | elle |  |
| `SHFTTIME` | firma | Vardiya zamanları | ldds | 2 | 2 | elle |  |
| `SHIFT` | firma | Vardiyalar | ldds | 2 | 2 | elle |  |
| `WSCHCODE` | firma | İş istasyonu özellikleri | ldds | 2 | 2 | elle |  |
| `WSGRPASS` | firma | İş istasyonu-grup ataması | ldds | 2 | 2 | elle |  |
| `WSGRPF` | firma | İş istasyonu grupları | ldds | 2 | 2 | elle |  |
| `ACCDISTTEMP` | firma | Genel muhasebe dağıtım şablonları | ldds | 1 | 1 | elle |  |
| `ACCDISTTEMPLN` | firma | Hesap dağıtım şablonları | ldds | 1 | 1 | elle |  |
| `PRODUCTLINE` | firma | (tanımsız — yalnız ad) | – | 1 | 1 | elle |  |
| `WSCHVAL` | firma | İş istasyonu özellik değerleri | ldds | 1 | 1 | elle |  |

### toplam/ozet_tablo (8)

| Aile | Kapsam | İş adı | Ad kaynağı | 411 satır | 211 satır | Sınıf kaynağı | Not |
|---|---|---|---|---:|---:|---|---|
| `FAYEAR` | firma | Sabit kıymet yıllık bilgileri | ldds+elle | 100.904 | 121.980 | elle |  |
| `CLRNUMS` | dönem | Cari risk toplamları | proje/olcum | 5.282 | 237.228 | elle |  |
| `CLCOLLATRLRISK` | dönem | Cari teminat riski | ad_cikarimi | 2.256 | 232.904 | elle |  |
| `CSHTOTS` | dönem | Kasa toplamları | ldds+elle | 1.557 | 8.851 | elle |  |
| `SRVNUMS` | dönem | Hizmet toplamları | ldds+elle | 1.444 | 3.660 | elle |  |
| `BNTOTFIL` | dönem | Banka toplamları | ldds+elle | 585 | 3.173 | elle |  |
| `GNTOTBN` | dönem | Banka genel toplamları | ldds+elle | 57 | 82 | elle |  |
| `GNTOTCSH` | dönem | Kasa genel toplamları | ldds+elle | 10 | 14 | elle |  |

### parametre (71)

| Aile | Kapsam | İş adı | Ad kaynağı | 411 satır | 211 satır | Sınıf kaynağı | Not |
|---|---|---|---|---:|---:|---|---|
| `INVDEF` | firma | Malzeme–ambar parametreleri (asgari/azami stok) | proje/olcum | 3.983.209 | 3.607.239 | elle |  |
| `CMPGNLINE` | firma | Kampanya tanım satırları | ldds+elle | 840.011 | 827.882 | elle |  |
| `GLASSGN` | firma | Genel muhasebe bağlantı atamaları | ad_cikarimi | 504.587 | 636.447 | elle |  |
| `PRCLSTDIV` | firma | Fiyat listesi işyeri dağılımı | ad_cikarimi | 349.111 | 346.148 | elle |  |
| `PRCLIST` | firma | Fiyat listeleri (alış/satış) | proje/olcum | 317.349 | 314.419 | elle |  |
| `L_FIRMPARAMS` | ortak | Firma parametreleri | ad_cikarimi | 268.466 | – | elle |  |
| `CRDACREF` | firma | Kart muhasebe hesap bağlantıları | ldds+elle | 220.419 | 200.726 | elle |  |
| `ITMUNITA` | firma | Malzeme birim atamaları | ldds+elle | 33.376 | 29.860 | elle |  |
| `ITMCLSAS` | firma | Malzeme sınıf atamaları | ldds+elle | 32.858 | 29.758 | elle |  |
| `L_DISTRICT` | ortak | Semt/mahalle listesi | ad_cikarimi | 32.055 | – | elle |  |
| `L_CURRENCYLIST` | ortak | Döviz türleri listesi | proje/olcum | 26.581 | – | elle |  |
| `L_LDOCNUM` | ortak | Belge numaralama sayaçları | ldds+elle | 16.903 | – | elle |  |
| `ITMFACTP` | firma | Malzeme fabrika parametreleri | ldds+elle | 15.902 | 12.841 | elle |  |
| `SUPPASGN` | firma | Tedarikçi atamaları | ldds+elle | 13.296 | 13.296 | elle |  |
| `SPECODES` | firma | Özel kod ve yetki kodu tanımları | proje/olcum | 9.465 | 9.263 | elle |  |
| `L_CAPIWHOUSE` | ortak | Ambar (depo) tanımları | proje/olcum | 6.318 | – | elle |  |
| `L_GIBLNSBRCTYPREL` | ortak | (tanımsız — yalnız ad) | – | 4.055 | – | elle |  |
| `ACCFCASGN` | dönem | (tanımsız — yalnız ad) | – | 3.857 | 25.031 | elle |  |
| `L_DAILYEXCHANGES` | ortak | Günlük döviz kurları | ldds+elle | 3.653 | – | elle |  |
| `EMUHACCSUBACCASGN` | firma | Alt hesap atamaları | ad_cikarimi | 3.269 | 3.260 | elle |  |
| `SLSCLREL` | firma | Satış elemanı–cari ilişkisi | ldds+elle | 1.827 | 1.827 | elle |  |
| `L_GIBOTHERPARAMS` | ortak | (tanımsız — yalnız ad) | – | 1.603 | – | elle |  |
| `L_TOWN` | ortak | İlçe listesi | ad_cikarimi | 973 | – | elle |  |
| `L_GTIP_DEF` | ortak | GTİP tanımları | ad_cikarimi | 774 | – | elle |  |
| `L_PRICEINDEX` | ortak | Fiyat endeksleri | ad_cikarimi | 772 | – | elle |  |
| `L_GTIP_CODE` | ortak | GTİP kodları | ad_cikarimi | 760 | – | elle |  |
| `L_GIBFAREGTYPE` | ortak | (tanımsız — yalnız ad) | – | 726 | – | elle |  |
| `L_GIBLINERECTYPEREL` | ortak | (tanımsız — yalnız ad) | – | 481 | – | elle |  |
| `L_CAPIDIV` | ortak | İşyeri tanımları | ad_cikarimi | 475 | – | elle |  |
| `DEFNFLDSCARDV` | firma | (tanımsız — yalnız ad) | – | 406 | 406 | elle |  |
| `L_PCKCODES` | ortak | Ambalaj kodları | ad_cikarimi | 378 | – | elle |  |
| `L_GIBSUBRECTYPE` | ortak | (tanımsız — yalnız ad) | – | 357 | – | elle |  |
| `LOCATIONSFOR` | firma | (tanımsız — yalnız ad) | – | 270 | 280 | elle |  |
| `L_COUNTRY` | ortak | Ülke listesi | ldds+elle | 256 | – | elle |  |
| `L_CAPIEXTINFO` | ortak | (tanımsız — yalnız ad) | – | 218 | – | elle |  |
| `L_GIBDOCLINETYPEREL` | ortak | (tanımsız — yalnız ad) | – | 147 | – | elle |  |
| `L_CURRENCYPARS` | ortak | Döviz parametreleri | ad_cikarimi | 143 | – | elle |  |
| `L_CAPIDEPT` | ortak | Bölüm tanımları | ad_cikarimi | 101 | – | elle |  |
| `L_CAPIFACTDIV` | ortak | Fabrika–işyeri bağları | ad_cikarimi | 101 | – | elle |  |
| `L_CAPIFACTORY` | ortak | Fabrika tanımları | ad_cikarimi | 101 | – | elle |  |
| `L_CAPIFIRM` | ortak | Firma tanımları | proje/olcum | 101 | – | elle |  |
| `L_CAPIPERIOD` | ortak | Firma dönemleri (211/411 yıl aralıkları) | proje/olcum | 101 | – | elle |  |
| `APPPARAM` | firma | Uygulama parametreleri | ad_cikarimi | 96 | 94 | elle |  |
| `L_CTYCODES` | ortak | Şehir kodları | ad_cikarimi | 93 | – | elle |  |
| `L_CITY` | ortak | İl listesi | ldds+elle | 82 | – | elle |  |
| `TAXDECLLINEACC` | firma | (tanımsız — yalnız ad) | – | 78 | 78 | elle |  |
| `ACCCODES` | firma | Muhasebe kodları | ldds+elle | 72 | 70 | elle |  |
| `L_PAYTYPES` | ortak | Ödeme türleri | ad_cikarimi | 71 | – | elle |  |
| `L_REGIMETYP` | ortak | Rejim türleri | ad_cikarimi | 70 | – | elle |  |
| `SHFTASGN` | firma | Vardiya atamaları | ldds | 56 | 53 | elle |  |
| `TSKSHELN` | firma | Görev çizelgesi tablosu | ldds | 45 | 45 | elle |  |
| `UNITSETL` | firma | Birim seti satırları (birimler) | proje/olcum | 34 | 33 | elle |  |
| `L_GIBDOCTYPE` | ortak | (tanımsız — yalnız ad) | – | 31 | – | elle |  |
| `L_SHPAGENT` | ortak | Taşıyıcı (kargo) tanımları | ldds+elle | 31 | – | elle |  |
| `CLPARAMS` | dönem | (tanımsız — yalnız ad) | – | 28 | 14 | elle |  |
| `L_GIBRECTYPE` | ortak | (tanımsız — yalnız ad) | – | 23 | – | elle |  |
| `L_TRADGRP` | ortak | Ticari işlem grupları | ldds+elle | 23 | – | elle |  |
| `L_SHPTYPES` | ortak | Sevkiyat türleri | ldds+elle | 18 | – | elle |  |
| `L_GIBLINETYPE` | ortak | (tanımsız — yalnız ad) | – | 14 | – | elle |  |
| `UNITSETF` | firma | Birim setleri | proje/olcum | 13 | 13 | elle |  |
| `RULES` | dönem | (tanımsız — yalnız ad) | – | 12 | 12 | elle |  |
| `L_FRGTYPES` | ortak | (tanımsız — yalnız ad) | – | 10 | – | elle |  |
| `EBOOKPARAMS` | firma | (tanımsız — yalnız ad) | – | 10 | 10 | elle |  |
| `WHLIST` | firma | Ambar listeleri | ldds | 8 | 8 | elle |  |
| `L_CAPIUNIT` | ortak | Birim tanımları | ad_cikarimi | 7 | – | elle |  |
| `REFLECTASGN` | dönem | Yansıtma atamaları | ldds | 6 | 48 | elle |  |
| `L_PRICEINDEXTYP` | ortak | (tanımsız — yalnız ad) | – | 4 | – | elle |  |
| `TRANSAC` | dönem | Firma dönem bilgileri | ldds | 1 | 1 | elle |  |
| `PRODUCERPARAMS` | firma | (tanımsız — yalnız ad) | – | 1 | 1 | elle |  |
| `TRGPAR` | firma | Trigger parametreleri | ldds | 1 | 1 | elle |  |
| `STLINENEGLEVEL` | dönem | (tanımsız — yalnız ad) | – | – | 828 | tahmin | yalnız 211'de var |

### log/sistem (43)

| Aile | Kapsam | İş adı | Ad kaynağı | 411 satır | 211 satır | Sınıf kaynağı | Not |
|---|---|---|---|---:|---:|---|---|
| `LOGREP` | firma | Logo işlem günlüğü | ldds+elle | 12.043.366 | 76.162 | elle |  |
| `HISTORY` | dönem | Kayıt değişiklik geçmişi | ad_cikarimi | 761.987 | 5.085.668 | elle |  |
| `DATAEXCHHISTORY` | dönem | Veri aktarım geçmişi | ad_cikarimi | 443.195 | 2.278.255 | elle |  |
| `L_CAPIRIGHT` | ortak | (tanımsız — yalnız ad) | – | 233.587 | – | elle |  |
| `L_DYNREPUSRR` | ortak | (tanımsız — yalnız ad) | – | 127.999 | – | elle |  |
| `FICHEOBJECT` | dönem | Fişe bağlı nesneler/ekler | ad_cikarimi | 87.400 | 413.872 | elle |  |
| `HISTORY` | firma | Kayıt değişiklik geçmişi | ad_cikarimi | 86.878 | 1.020.053 | elle |  |
| `CHANGELOG` | firma | Değişiklik günlüğü | ad_cikarimi | 41.185 | 283.593 | elle |  |
| `DOCPRINT` | dönem | Belge yazdırma günlüğü | ad_cikarimi | 8.114 | 156.331 | elle |  |
| `L_CDBTMP` | ortak | Form boyutları | ldds | 8.091 | – | elle |  |
| `APPROVE` | dönem | Onay kayıtları | ad_cikarimi | 5.904 | 5.613 | elle |  |
| `L_CAPIDRIGHT` | ortak | (tanımsız — yalnız ad) | – | 5.549 | – | elle |  |
| `L_USERWINPREF` | ortak | (tanımsız — yalnız ad) | – | 1.818 | – | elle |  |
| `L_BRWSSTAT` | ortak | (tanımsız — yalnız ad) | – | 1.566 | – | elle |  |
| `L_DEFNFLDSD` | ortak | (tanımsız — yalnız ad) | – | 1.100 | – | elle |  |
| `L_RPFILTS*` | ortak | Rapor filtre düzenleri (firma no ekli) | – | 600 | 522 | elle | 117 firma kopyası, toplam 20424 satır (tüm firmalar) |
| `L_GOUSERS` | ortak | Kullanıcılar | ldds | 355 | – | elle |  |
| `L_MANDFLDS` | ortak | (tanımsız — yalnız ad) | – | 345 | – | elle |  |
| `L_RPLAYS_*` | ortak | Rapor tasarım düzenleri (firma no ekli) | – | 335 | 327 | elle | 124 firma kopyası, toplam 22313 satır (tüm firmalar) |
| `L_STATUSINFO` | ortak | (tanımsız — yalnız ad) | – | 124 | – | elle |  |
| `L_DYNREP` | ortak | (tanımsız — yalnız ad) | – | 121 | – | elle |  |
| `L_USERBLOBTABLE` | ortak | (tanımsız — yalnız ad) | – | 88 | – | elle |  |
| `L_CAPIUSER` | ortak | (tanımsız — yalnız ad) | – | 85 | – | elle |  |
| `L_TABLELAYS_*` | ortak | Tablo görünüm düzenleri (firma no ekli) | – | 84 | 80 | elle | 89 firma kopyası, toplam 5226 satır (tüm firmalar) |
| `L_LBSLOADUSRRIGHTS` | ortak | (tanımsız — yalnız ad) | – | 65 | – | elle |  |
| `L_CAPITERMINAL` | ortak | (tanımsız — yalnız ad) | – | 43 | – | elle |  |
| `L_USERSDEF` | ortak | (tanımsız — yalnız ad) | – | 33 | – | elle |  |
| `L_ADLOGS` | ortak | (tanımsız — yalnız ad) | – | 21 | – | elle |  |
| `L_FRMOD` | ortak | (tanımsız — yalnız ad) | – | 20 | – | elle |  |
| `L_CAPIGROUP` | ortak | (tanımsız — yalnız ad) | – | 12 | – | elle |  |
| `L_LOG` | ortak | (tanımsız — yalnız ad) | – | 7 | – | elle |  |
| `L_MESSAGES` | ortak | (tanımsız — yalnız ad) | – | 3 | – | elle |  |
| `L_TSPROPS` | ortak | (tanımsız — yalnız ad) | – | 3 | – | elle |  |
| `L_CAPIVERS` | ortak | (tanımsız — yalnız ad) | – | 2 | – | elle |  |
| `L_TEXTFAV` | ortak | (tanımsız — yalnız ad) | – | 2 | – | elle |  |
| `L_CAPIPROG` | ortak | (tanımsız — yalnız ad) | – | 1 | – | elle |  |
| `L_CAPISIGN` | ortak | (tanımsız — yalnız ad) | – | 1 | – | elle |  |
| `L_CAPIWEBCONN` | ortak | (tanımsız — yalnız ad) | – | 1 | – | elle |  |
| `L_MAPCONFIG` | ortak | (tanımsız — yalnız ad) | – | 1 | – | elle |  |
| `APPROVAL` | dönem | (tanımsız — yalnız ad) | – | 0 | 830 | elle | 211'de var, 411'de boş |
| `APPROVERS` | dönem | (tanımsız — yalnız ad) | – | 0 | 1 | elle | 211'de var, 411'de boş |
| `RESPONSEHISTORY` | dönem | (tanımsız — yalnız ad) | – | 0 | 29.553 | elle | 211'de var, 411'de boş |
| `RULEHISTORY` | dönem | (tanımsız — yalnız ad) | – | 0 | 25.405 | elle | 211'de var, 411'de boş |

### yedek/kopya (12)

| Aile | Kapsam | İş adı | Ad kaynağı | 411 satır | 211 satır | Sınıf kaynağı | Not |
|---|---|---|---|---:|---:|---|---|
| `STLINE_yedek1` | dönem | Yedek/kopya: STLINE (Malzeme hareketleri) | ad | 1.143.737 | – | ad | yalnız 411'de var |
| `FAYEAR_YEDEKK` | firma | Yedek/kopya: FAYEAR (Sabit kıymet yıllık bilgileri) | ad | 118.263 | – | ad | yalnız 411'de var |
| `L_FIRMPARAMS_20170102` | ortak | Yedek/kopya: L_FIRMPARAMS (Firma parametreleri) | ad | 44.850 | – | ad |  |
| `L_LDOCNUM_2025_ONCESI` | ortak | Yedek/kopya: L_LDOCNUM (Belge numaralama sayaçları) | ad | 41.184 | – | ad |  |
| `L_LDOCNUM_BCKK` | ortak | Yedek/kopya: L_LDOCNUM (Belge numaralama sayaçları) | ad | 16.590 | – | ad |  |
| `L_LDOCNUM311220162` | ortak | Yedek/kopya: L_LDOCNUM (Belge numaralama sayaçları) | ad | 15.051 | – | ad |  |
| `L_LDOCNUM31122016` | ortak | Yedek/kopya: L_LDOCNUM (Belge numaralama sayaçları) | ad | 15.048 | – | ad |  |
| `L_LDOCNUM_YDK` | ortak | Yedek/kopya: L_LDOCNUM (Belge numaralama sayaçları) | ad | 13.747 | – | ad |  |
| `STLINE_20260430_RETAMOUNT` | dönem | Yedek/kopya: STLINE (Malzeme hareketleri) | ad | 3.067 | – | ad | yalnız 411'de var |
| `FAREGIST_YEDEK` | firma | Yedek/kopya: FAREGIST (Sabit kıymet kayıtları) | ad | 1.508 | – | ad | yalnız 411'de var |
| `L_CAPIPERIOD_YEDEK` | ortak | Yedek/kopya: L_CAPIPERIOD (Firma dönemleri (211/411 yıl aralıkları)) | ad | 124 | – | ad |  |
| `CRDACREF_copy` | firma | Yedek/kopya: CRDACREF (Kart muhasebe hesap bağlantıları) | ad | – | 83.770 | ad | yalnız 211'de var |

Logo'nun kendi görünümleri (LV_): `BNFLINE`, `CLCARD`, `CLEKSTRE`, `CLFLINE`, `CLTOTFIL`, `CLTOTFILV1`, `CSCARD`, `EMUHTOT`, `EMUHTOTV1`, `EMUHTOTV2`, `EMUHTOTV3`, `EXIMDISTPEG`, `GNTOTCL`, `GNTOTST`, `GNTOTVRNT`, `ITEMS`, `MULTIADDTAXLN`, `ORDER_ITEMS`, `ORDER_SERVICE`, `ORFLINE`, `QCFICHECHECK`, `QCPARAMCHECK`, `SALES_ITEMS`, `SALES_ITEMS_TOTAL`, `SALES_SERVICE`, `SALES_SERVICE_TOTAL`, `SRVNUMS`, `SRVTOT`, `STINVENS`, `STINVTOT`, `STINVTOT_V1`, `STINVTOT_V2`, `STINVTOT_V3`, `STINVTOT_V4`, `STINVTOT_V5`, `STLINE`, `STLINEFORINVCALC`, `TRDGRP`, `VRNTINVENS`, `VRNTINVTOT`.

## 2. Ana ailelerin kolon sözlüğü

Burada yalnız iş anlamı kararlaştırılmış (elle yazılmış), golden SQL'de geçen ya da eski katalogda sertifikalı kolonlar listelenir. Tüm fiziksel kolonlar (anlam, LDDS açıklaması, 2026-09 doluluk/farklı değer/min/max, eski katalog eşlemesi, kişisel veri işareti) JSON'dadır.

| Aile | 411 tablo | 411 satır | 2026-09 ölçülen | Kolon | yüksek | orta | düşük | tahmin |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| STLINE | `LG_411_01_STLINE` | 2.153.392 | 322.567 | 336 | 25 | 197 | 1 | 113 |
| INVOICE | `LG_411_01_INVOICE` | 101.874 | 14.419 | 181 | 14 | 102 | 1 | 64 |
| STFICHE | `LG_411_01_STFICHE` | 126.815 | 18.987 | 181 | 4 | 113 | 0 | 64 |
| ORFICHE | `LG_411_01_ORFICHE` | 59.956 | 8.149 | 149 | 2 | 91 | 0 | 56 |
| ORFLINE | `LG_411_01_ORFLINE` | 227.145 | 31.455 | 186 | 4 | 144 | 1 | 37 |
| CLCARD | `LG_411_CLCARD` | 257.378 | 257.378 | 391 | 6 | 158 | 1 | 226 |
| ITEMS | `LG_411_ITEMS` | 32.859 | 32.859 | 231 | 5 | 133 | 3 | 90 |
| CLFLINE | `LG_411_01_CLFLINE` | 119.838 | 16.300 | 130 | 8 | 76 | 3 | 43 |
| CLFICHE | `LG_411_01_CLFICHE` | 5.365 | 932 | 84 | 1 | 60 | 0 | 23 |
| PAYTRANS | `LG_411_01_PAYTRANS` | 139.648 | 13.096 | 84 | 8 | 52 | 2 | 22 |
| KSLINES | `LG_411_01_KSLINES` | 1.377 | 108 | 136 | 3 | 79 | 0 | 54 |
| KSCARD | `LG_411_KSCARD` | 9 | 9 | 30 | 0 | 26 | 0 | 4 |
| BNFICHE | `LG_411_01_BNFICHE` | 2.563 | 278 | 72 | 0 | 52 | 0 | 20 |
| BNFLINE | `LG_411_01_BNFLINE` | 21.323 | 2.484 | 178 | 5 | 96 | 0 | 77 |
| BANKACC | `LG_411_BANKACC` | 118 | 118 | 59 | 0 | 40 | 0 | 19 |
| CSCARD | `LG_411_01_CSCARD` | 4.238 | 4.238 | 101 | 5 | 74 | 0 | 22 |
| CSROLL | `LG_411_01_CSROLL` | 950 | 101 | 80 | 2 | 61 | 0 | 17 |
| CSTRANS | `LG_411_01_CSTRANS` | 9.177 | 217 | 35 | 4 | 26 | 0 | 5 |
| PRCLIST | `LG_411_PRCLIST` | 317.349 | 317.349 | 69 | 7 | 48 | 0 | 14 |
| STINVTOT | `LG_411_01_STINVTOT` | 0 | – | 45 | 0 | 39 | 1 | 5 |
| GNTOTST | `LG_411_01_GNTOTST` | 0 | – | 42 | 0 | 38 | 0 | 4 |
| EMFICHE | `LG_411_01_EMFICHE` | 114.397 | 15.728 | 73 | 1 | 54 | 0 | 18 |
| EMFLINE | `LG_411_01_EMFLINE` | 307.857 | 36.974 | 83 | 8 | 51 | 0 | 24 |
| EMUHACC | `LG_411_EMUHACC` | 1.374 | 1.374 | 88 | 2 | 67 | 0 | 19 |
| EMCENTER | `LG_411_EMCENTER` | 17.448 | 17.448 | 27 | 0 | 23 | 1 | 3 |
| PAYPLANS | `LG_411_PAYPLANS` | 188 | 188 | 33 | 0 | 28 | 0 | 5 |
| UNITSETL | `LG_411_UNITSETL` | 34 | 34 | 23 | 0 | 21 | 0 | 2 |
| UNITSETF | `LG_411_UNITSETF` | 13 | 13 | 22 | 1 | 20 | 0 | 1 |
| SPECODES | `LG_411_SPECODES` | 9.465 | 9.465 | 18 | 0 | 10 | 0 | 8 |
| CLRNUMS | `LG_411_01_CLRNUMS` | 5.282 | 5.282 | 114 | 3 | 90 | 0 | 21 |
| L_CAPIPERIOD | `L_CAPIPERIOD` | 101 | 2 | 12 | 5 | 0 | 0 | 7 |
| L_CAPIFIRM | `L_CAPIFIRM` | 101 | 2 | 233 | 2 | 0 | 0 | 231 |
| L_CURRENCYLIST | `L_CURRENCYLIST` | 26.581 | 26.581 | 17 | 2 | 0 | 0 | 15 |
| L_CAPIWHOUSE | `L_CAPIWHOUSE` | 6.318 | 288 | 34 | 2 | 0 | 0 | 32 |

### STLINE — Malzeme hareketleri

`LG_411_01_STLINE` · 411: 2.153.392 satır · 211: 12.195.380 · ölçüm: WHERE DATE_>='20260901' AND DATE_<'20261001' (322.567 satır)

| Kolon | Tür | Anlam | Güven | Kaynak | 2026-09 dolu / farklı | Eski katalog | Golden |
|---|---|---|---|---|---|---|---|
| `LOGICALREF` | int | Satırın tekil kimliği (birincil anahtar; FK tanımı yok). | yüksek | ldds, olcum, eski, golden | 322.567 / 322.567 | satış satırı sayısı (CERTIFIED, operator:claude (arşiv P100, 2026-09-21)); toplam miktar (CERTIFIED, rule-miner) | B030 |
| `STOCKREF` | int | Malzeme kartı → ITEMS.LOGICALREF. Hizmet satırında (LINETYPE 4) hizmet kartına, iskonto satırında 0'a gider. | yüksek | ldds, proje, olcum, eski, golden | 189.615 / 6.014 | STLINE.STOCKREF -> ITEMS.LOGICALREF (CERTIFIED, claude-inceleme); stok kartı referansı (CERTIFIED, otomatik-yoklama) | A027, A051, C004 |
| `LINETYPE` | smallint | Satır türü: 0 malzeme, 2 iskonto, 3 masraf, 4 hizmet, 8 sabit kıymet (kod tablosuna bak). | yüksek | ldds, proje, olcum, eski, golden | 135.463 / 5 | adet (CERTIFIED, seed); brut kar marji (CERTIFIED, seed) | A022, A027, A032, A051 |
| `TRCODE` | smallint | Bağlı fiş/belge türü. Satırın TRCODE'u bağlı INVOICE ve STFICHE TRCODE'u ile birebir aynıdır (2026-09: %100). | yüksek | ldds, olcum, proje, eski, golden | 322.567 / 14 | adet (CERTIFIED, seed); brut kar marji (CERTIFIED, seed) | A022, A032, B029, B030 |
| `DATE_` | datetime | Hareket (fiş) tarihi; dönem süzgeci bu kolonla yapılır. | yüksek | proje, golden, ldds, eski, olcum_dolu | 322.567 / – | irsaliye tarihi (CANDIDATE) | A022, A032, A051, B029 |
| `GLOBTRANS` | smallint | İndirim/masraf satırı fiş geneline mi uygulanmış (1 genel, 0 satır). | orta | ldds, olcum, eski | 887 / 2 | islem muhasep (CERTIFIED) | – |
| `PRODORDERREF` | int | Bağlı üretim emri (baskı) → PRODORD.LOGICALREF; sarf (12) / üretimden giriş (13) satırlarında. | yüksek | proje, olcum, eski, golden | 45 / 46 | ilgil uret emr (REJECTED) | C026 |
| `SOURCEINDEX` | smallint | İşlem ambarı numarası → L_CAPIWHOUSE.NR (FIRMNR=411). 4 = Timaş Satış Deposu 2, 10 = B2C (İnternet Satışları) Deposu. | yüksek | proje, olcum, eski, golden | 316.910 / 31 | ambar (CERTIFIED, operator); depokodu (CANDIDATE) | A027 |
| `IOCODE` | smallint | Giriş/çıkış yönü: 1 giriş, 2 ambar girişi (transfer), 3 ambar çıkışı (transfer), 4 çıkış; 0 = stok etkisiz satır (hizmet/iskonto). | yüksek | ldds, olcum, proje, eski, golden | 320.898 / 5 | sevkiyat (CERTIFIED, operator); stok bakiyesi (CERTIFIED, operator) | A027, A051, C004, C015 |
| `STFICHEREF` | int | Bağlı irsaliye/stok fişi → STFICHE.LOGICALREF (2026-09 eşleşme %100). | yüksek | ldds, olcum, eski | 319.799 / 18.987 | logicalref (CERTIFIED, rule-miner); stok fis stock (REJECTED) | – |
| `INVOICEREF` | int | Bağlı fatura → INVOICE.LOGICALREF; 0 = faturalanmamış satır. Satış ölçülerinde 'faturalı satır' koşulu INVOICEREF<>0. | yüksek | proje, motor, golden, olcum, eski | 284.986 / 14.420 | STLINE.INVOICEREF -> INVOICE.LOGICALREF (CERTIFIED, claude-inceleme); adet (CERTIFIED, seed) | A021, A022, A032, B030 |
| `CLIENTREF` | int | Cari kart → CLCARD.LOGICALREF. | yüksek | proje, olcum, eski, golden | 317.044 / 1.281 | STLINE.CLIENTREF -> CLCARD.LOGICALREF (CERTIFIED, claude-inceleme); iş ortağı (CERTIFIED, otomatik-yoklama) | A022, B029, B030, C015 |
| `ORDTRANSREF` | int | Bağlı sipariş satırı → ORFLINE.LOGICALREF. | yüksek | proje, olcum, eski, golden | 31.425 / 31.417 | siparis id (CANDIDATE); ilgil siparis hareket (REJECTED) | A021 |
| `ORDFICHEREF` | int | Bağlı sipariş fişi → ORFICHE.LOGICALREF. | yüksek | proje, olcum, eski | 31.265 / 8.075 | ilgil siparis fis (REJECTED) | – |
| `CENTERREF` | int | Masraf merkezi → EMCENTER.LOGICALREF (gider sorusu bununla cevaplanmaz). | yüksek | proje, olcum, eski | 2.888 / 295 | islem yapildik depo (REJECTED) | – |
| `ACCOUNTREF` | int | Muhasebe hesabı → EMUHACC.LOGICALREF. | yüksek | ldds, olcum | 179.647 / 88 | – | – |
| `SPECODE` | varchar(17) | Satır özel kodu (serbest). | orta | ldds, eski, olcum_dolu | 1.728 / 187 | hareket ozel kodu (CANDIDATE); satır ozel kodu (CANDIDATE) | – |
| `AMOUNT` | float | İşlem miktarı (satır biriminde). Adet ölçülerinde UINFO1/UINFO2 ile ana birime çevrilir; 2026-09 malzeme satırlarının tamamında UINFO1=UINFO2=1. | yüksek | proje, motor, olcum, eski, golden | 189.238 / – | adet (CERTIFIED, seed); brut kar marji (CERTIFIED, seed) | A022, A027, A051, B029 |
| `PRICE` | float | Birim fiyat (satır birimi, işlem/yerel para). | orta | ldds, proje, eski, olcum_dolu | 167.582 / – | birim fiyat (CERTIFIED, rule-miner); birimfiyat (CANDIDATE) | – |
| `TOTAL` | float | Satır brüt tutarı (iskonto öncesi, KDV hariç). İskonto satırında (LINETYPE 2) TOTAL = iskonto tutarıdır. | yüksek | proje, olcum, eski, golden | 300.909 / – | brut kar marji (CERTIFIED, seed); iskonto orani (CERTIFIED, operator) | A032, D015 |
| `TRCURR` | smallint | İşlem dövizi türü: 0 yerel (TL), 1 USD, 20 EUR, 17 GBP (L_CURRENCYLIST.CURTYPE). | yüksek | ldds, olcum | 70 / 4 | – | – |
| `TRRATE` | float | İşlem dövizi kuru. | orta | ldds, olcum_dolu | 70 / – | – | – |
| `DISTCOST` | float | Satıra Dağıtılan Maliyet (Distributed Cost to Line) | orta | ldds, eski, olcum_dolu | 133.511 / – | indirim oranı (CERTIFIED, rule-miner) | – |
| `DISTDISC` | float | Fiş geneli indirimlerden satıra dağıtılan pay. | orta | ldds, eski, olcum_dolu | 133.631 / – | indirim tutar (CERTIFIED, rule-miner); iskonto tutarı (CERTIFIED, rule-miner) | – |
| `UOMREF` | int | Satır birimi → UNITSETL.LOGICALREF. | yüksek | ldds, olcum | 189.238 / 8 | – | – |
| `USREF` | int | Birim seti → UNITSETF.LOGICALREF. | yüksek | ldds, olcum | 189.238 / 7 | – | – |
| `UINFO1` | float | Satır birimi → ana birim çevrim payı. | orta | ldds, motor, olcum | 189.238 / – | – | – |
| `UINFO2` | float | Satır birimi → ana birim çevrim paydası. | orta | ldds, motor, olcum | 189.238 / – | – | – |
| `VAT` | float | Satır KDV oranı (%). | orta | ldds, eski, olcum_dolu | 3.932 / – | kdv (CANDIDATE); kdv oranı (CANDIDATE) | – |
| `VATAMNT` | float | Satır KDV tutarı. | yüksek | ldds, olcum, eski | 3.333 / – | genel toplam (CERTIFIED, rule-miner); kdv tutarı (CERTIFIED, rule-miner) | – |
| `VATMATRAH` | float | KDV matrahı (iskonto sonrası, KDV hariç). INVOICE.NETTOTAL = Σ VATMATRAH + Σ VATAMNT (2026-09: 7/8/2/3 türlerinde tüm faturalarda). | yüksek | olcum, eski | 159.096 / – | genel toplam (CERTIFIED, rule-miner); kdvli tutar (CERTIFIED, rule-miner) | – |
| `BILLED` | smallint | Faturalandı bayrağı: 1 faturalanmış. INVOICEREF ile çoğunlukla tutarlı ama tam değil (2026-09: TRCODE 7'de BILLED=0 olup INVOICEREF dolu 354 satır). | orta | proje, olcum, eski, golden | 284.815 / 2 | faturalanmamış sevk tutarı (CERTIFIED, operator); faturalanmamış sevkiyat (CERTIFIED, operator) | A022 |
| `RETCOST` | float | İade satırı maliyeti (birim). 2026-09 toptan iade (3) satırlarının %99'unda dolu. | orta | ldds, olcum, eski | 1.359 / – | iade maliyeti (CANDIDATE) | – |
| `OUTCOST` | float | Çıkış birim maliyeti (maliyetlendirme çalıştırıldıktan sonra doldurulur). Satır maliyeti = AMOUNT × OUTCOST. 2026-09 satış satırlarının yalnız %0,8'inde dolu → güncel ay kâr/maliyet hesaplanamaz. | yüksek | proje, olcum, eski, golden | 1.458 / – | brut kar marji (CERTIFIED, seed); kâr (CERTIFIED, operator) | B029, B030 |
| `CANCELLED` | smallint | İptal bayrağı: 0 geçerli, 1 iptal. | yüksek | proje, ldds, eski, golden | 0 / 1 | faturalanmamış sevk tutarı (CERTIFIED, operator); faturalanmamış sevkiyat (CERTIFIED, operator) | A021, A022, A027, A032 |
| `LINENET` | float | Satır net tutarı: iskonto sonrası, KDV hariç. Fatura bazında Σ LINENET ≈ Σ VATMATRAH (iskonto satırlarında LINENET 0). | yüksek | proje, motor, olcum, eski, golden | 159.161 / – | faturalanmamış sevk tutarı (CERTIFIED, operator); kâr (CERTIFIED, operator) | B029, B030 |
| `SALESMANREF` | int | Satış elemanı → LG_SLSMAN.LOGICALREF. | orta | ldds, olcum | 89.605 / 23 | – | – |

### INVOICE — Faturalar

`LG_411_01_INVOICE` · 411: 101.874 satır · 211: 502.826 · ölçüm: WHERE DATE_>='20260901' AND DATE_<'20261001' (14.419 satır)

| Kolon | Tür | Anlam | Güven | Kaynak | 2026-09 dolu / farklı | Eski katalog | Golden |
|---|---|---|---|---|---|---|---|
| `LOGICALREF` | int | Fatura Log. Ref. (Invoice Logical Reference) | orta | ldds, eski, golden, olcum_dolu | 14.419 / 14.419 | INVOICE.LOGICALREF -> PAYTRANS.FICHEREF (CERTIFIED); INVOICE.LOGICALREF -> STLINE.INVOICEREF (CERTIFIED, claude-inceleme) | A021, A032, A060, B019 |
| `GRPCODE` | smallint | Fatura grubu: 1 alış, 2 satış (TRCODE ile tutarlı). | yüksek | ldds, olcum, eski | 14.419 / 2 | grup türü (CERTIFIED, otomatik-yoklama); kurumsal grup (CERTIFIED, seed) | – |
| `TRCODE` | smallint | Fatura türü (kod tablosu). Satış 7/8/9, satış iadesi 2/3, alış 1/4, alım iadesi 6. | yüksek | proje, ldds, olcum, eski, golden | 14.419 / 8 | alim iade (CERTIFIED, claude-inceleme); alinan hizmet (CERTIFIED, claude-inceleme) | A006, A016, A032, A060 |
| `FICHENO` | varchar(17) | Fatura numarası (belge no). | orta | ldds, eski, olcum_dolu | 14.419 / 14.419 | fatura no (CANDIDATE) | – |
| `DATE_` | datetime | Fatura tarihi. | yüksek | proje, golden, eski, olcum_dolu | 14.419 / – | fatura tarihi (CANDIDATE); kanal payi yuz (CANDIDATE) | A006, A016, A060, B019 |
| `SPECODE` | varchar(11) | Fatura özel kodu. 2026-09: 'B2C' = internet (B2C) perakende faturaları, ambar 10. | orta | ldds, olcum, eski | 8.164 / 6 | fatura ozel kodu (CANDIDATE) | – |
| `CLIENTREF` | int | Cari → CLCARD.LOGICALREF. | yüksek | proje, olcum, eski, golden | 14.383 / 1.193 | INVOICE.CLIENTREF -> CLCARD.LOGICALREF (CERTIFIED, seed); cari sayi (CERTIFIED, claude-inceleme) | A006, A016, B019, D039 |
| `SOURCEINDEX` | smallint | Fatura ambarı → L_CAPIWHOUSE.NR. | yüksek | ldds, olcum | 14.418 / 21 | – | – |
| `CANCELLED` | smallint | İptal bayrağı: 0 geçerli, 1 iptal (2026'da 41 iptal satış faturası). | yüksek | proje, olcum, eski, golden | 0 / 1 | geçerliliği kaldırılmış (CERTIFIED, otomatik-yoklama); invoice default cancelled (CERTIFIED, seed) | A006, A016, A021, A032 |
| `TOTALDISCOUNTS` | float | Toplam iskonto tutarı (= Σ iskonto satırı TOTAL). | yüksek | ldds, olcum, eski | 5.759 / – | iskonto toplam (CERTIFIED, rule-miner); toplam iskonto (CERTIFIED, rule-miner) | – |
| `TOTALDISCOUNTED` | float | İskonto sonrası toplam (KDV hariç) ≈ Σ satır LINENET. | yüksek | ldds, olcum | 14.417 / – | – | – |
| `TOTALVAT` | float | Toplam KDV (= Σ satır VATAMNT). | yüksek | ldds, olcum, eski | 1.497 / – | fatura kdv tutarı (CERTIFIED, rule-miner); toplam kdv (CERTIFIED, rule-miner) | – |
| `GROSSTOTAL` | float | Brüt toplam: iskonto öncesi malzeme/hizmet tutarı (KDV hariç) = Σ satır TOTAL. | yüksek | ldds, olcum, eski | 14.419 / – | mal / hizmet toplam tutarı (CERTIFIED, rule-miner); matrah (CANDIDATE) | – |
| `NETTOTAL` | float | Fatura net toplamı = ödenecek tutar, KDV dahil (Σ satır VATMATRAH + Σ VATAMNT; 2026-09'da 7/8/2/3 türlerinde %100 eşit). Satır net cirosu (LINENET) değildir. | yüksek | proje, motor, olcum, eski, golden | 14.397 / – | ciro (CERTIFIED, seed); fatura toplam (CERTIFIED, rule-miner) | A016, D039 |
| `TRCURR` | smallint | İşlem dövizi türü (0 yerel). | yüksek | ldds, olcum | 32 / 4 | – | – |
| `TRNET` | float | İşlem dövizi cinsinden net tutar. | orta | ldds, proje, olcum_dolu | 14.362 / – | – | – |
| `PAYDEFREF` | int | Ödeme planı → PAYPLANS.LOGICALREF. | yüksek | ldds, olcum | 6.431 / 27 | – | – |
| `ACCFICHEREF` | int | Muhasebe fişi → EMFICHE.LOGICALREF. | yüksek | ldds, olcum | 14.383 / 14.384 | – | – |
| `SALESMANREF` | int | Satış elemanı → LG_SLSMAN. | orta | ldds, olcum | 10.438 / 22 | – | – |
| `EINVOICE` | smallint | Aday anlam (eski katalog/TİMAŞ görünüm takma adı): e mükellef tipi | düşük | eski, olcum_dolu | 14.020 / 3 | e mükellef tipi (CERTIFIED, rule-miner) | – |

### STFICHE — Stok fişleri

`LG_411_01_STFICHE` · 411: 126.815 satır · 211: 620.137 · ölçüm: WHERE DATE_>='20260901' AND DATE_<'20261001' (18.987 satır)

| Kolon | Tür | Anlam | Güven | Kaynak | 2026-09 dolu / farklı | Eski katalog | Golden |
|---|---|---|---|---|---|---|---|
| `GRPCODE` | smallint | Fiş grubu: 1 satınalma, 2 satış, 3 malzeme yönetimi. | orta | olcum, eski | 18.987 / 3 | malzeme yönetimi (CERTIFIED, rule-miner); satis (CANDIDATE) | – |
| `TRCODE` | smallint | İrsaliye/stok fişi türü (kod tablosu). | yüksek | ldds, olcum, eski | 18.987 / 12 | alım iade irs (CERTIFIED, rule-miner); alım iade irsaliyesi (CERTIFIED, rule-miner) | – |
| `IOCODE` | smallint | Fiş yönü: 1 giriş, 2 ambar (transfer), 3 çıkış. DİKKAT: satırda (STLINE) çıkış 4'tür. | yüksek | ldds, olcum, eski | 18.987 / 3 | ambar (CANDIDATE); g/c kodu (CANDIDATE) | – |
| `FICHENO` | varchar(17) | Fiş Numarası (Voucher Number) | orta | ldds, eski, olcum_dolu | 18.987 / 18.900 | irsaliye no (CERTIFIED, rule-miner); irsaliye numarası (CERTIFIED, rule-miner) | – |
| `DOCODE` | varchar(33) | Belge Numarası (Document Number) | orta | ldds, eski, olcum_dolu | 16.081 / 14.858 | belge numarası (CERTIFIED, rule-miner) | – |
| `INVOICEREF` | int | Bağlı fatura → INVOICE.LOGICALREF (0 = faturalanmamış irsaliye). | yüksek | ldds, olcum | 15.696 / 13.888 | – | – |
| `PORDERFICHENO` | varchar(17) | Üretim Emri Fiş Numarası (Production Order Voucher Number) | orta | ldds, eski, olcum_dolu | 45 / 46 | üretim emri no (CERTIFIED, rule-miner) | – |
| `BILLED` | smallint | Faturalandı bayrağı (2026-09'da INVOICEREF ile birebir). | yüksek | olcum, eski | 15.696 / 2 | faturalandırılmış (CANDIDATE) | – |
| `NETTOTAL` | float | İrsaliye net toplamı. | orta | ldds, olcum_dolu | 16.193 / – | – | – |
| `GENEXP3` | varchar(51) | Fiş Genel Açıklaması (Voucher General Description) | orta | ldds, eski, olcum_dolu | 35 / 11 | fis aciklama3 (CERTIFIED, rule-miner) | – |

### ORFICHE — Sipariş fişleri

`LG_411_01_ORFICHE` · 411: 59.956 satır · 211: 263.047 · ölçüm: WHERE DATE_>='20260901' AND DATE_<'20261001' (8.149 satır)

| Kolon | Tür | Anlam | Güven | Kaynak | 2026-09 dolu / farklı | Eski katalog | Golden |
|---|---|---|---|---|---|---|---|
| `LOGICALREF` | int | Sipariş fişi log. Ref. (Order Voucher Logical Reference) | orta | ldds, eski, golden, olcum_dolu | 8.149 / 8.149 | siparis sayisi (CERTIFIED, seed); kaynak ref (CANDIDATE) | A021, B050 |
| `TRCODE` | smallint | Sipariş türü: 1 alınan (satış) sipariş, 2 verilen (alış) sipariş. 2026-09'da yalnız 1. | yüksek | ldds, proje, olcum, eski, golden | 8.149 / 1 | alınan sipariş (CERTIFIED, rule-miner); sipariş (CERTIFIED, operator) | A021, B050, D037, D039 |
| `FICHENO` | varchar(17) | Fiş Numarası (Voucher Number) | orta | ldds, eski, golden, olcum_dolu | 8.149 / 8.149 | sipariş numarası (CERTIFIED, rule-miner); fiş no (CANDIDATE) | A021 |
| `DATE_` | datetime | Tarih (Date) | orta | ldds, eski, golden, olcum_dolu | 8.149 / – | hareket tarihi (CERTIFIED, rule-miner); sipariş tarihi (CERTIFIED, rule-miner) | D039 |
| `SPECODE` | varchar(11) | Özel kod; 2026-09 fişlerin %99,8'i 'B2C' (internet satışı). | orta | olcum, eski | 8.134 / 2 | hareket ozel kodu (CANDIDATE) | – |
| `CLIENTREF` | int | Cari Hesap Ref. (Account Receivable / Payable Reference) | orta | ldds, eski, golden, olcum_dolu | 8.149 / 132 | ORFICHE.CLIENTREF -> CLCARD.LOGICALREF (CERTIFIED, claude-inceleme); satıcı referansı (CERTIFIED, otomatik-yoklama) | D037, D039 |
| `NETTOTAL` | float | Sipariş fişi net toplamı (sipariş tutarı). | yüksek | proje, eski, golden, olcum_dolu | 8.132 / – | siparis tutar (CERTIFIED, seed); alacak (CANDIDATE) | A021 |
| `STATUS` | smallint | Onay durumu: 1 öneri, 2 sevkedilemez, 4 sevkedilebilir. | orta | ldds, olcum, eski | 8.149 / 2 | sevkedilebilir (CANDIDATE, rule-miner); sevkedilemez (CANDIDATE, rule-miner) | – |
| `CUSTORDNO` | varchar(51) | Müşteri Sipariş Fişi Numarası (Customer Order Voucher Number) | orta | ldds, eski, olcum_dolu | 8.149 / 8.131 | musteri sip no (CERTIFIED, rule-miner) | – |
| `CANCELLED` | smallint | İptal Edilmiş (Cancelled) | orta | ldds, eski, golden | 0 / 1 | iptal (CERTIFIED, operator); sipariş (CERTIFIED, operator) | A021, B050, D037, D039 |

### ORFLINE — Sipariş hareketleri

`LG_411_01_ORFLINE` · 411: 227.145 satır · 211: 912.637 · ölçüm: WHERE DATE_>='20260901' AND DATE_<'20261001' (31.455 satır)

| Kolon | Tür | Anlam | Güven | Kaynak | 2026-09 dolu / farklı | Eski katalog | Golden |
|---|---|---|---|---|---|---|---|
| `LOGICALREF` | int | Sipariş hareketi log. Ref. (Order Transaction Logical Reference) | orta | ldds, golden, olcum_dolu | 31.455 / 31.455 | – | A012, A021 |
| `STOCKREF` | int | Malzeme Kartı Referansı (Item Card Reference) | orta | ldds, eski, golden, olcum_dolu | 30.759 / 2.933 | ORFLINE.STOCKREF -> ITEMS.LOGICALREF (CANDIDATE); item id (CANDIDATE) | A012, C004 |
| `ORDFICHEREF` | int | Sipariş fişi → ORFICHE.LOGICALREF (%100). | yüksek | proje, olcum, eski, golden | 31.455 / 8.149 | ORFLINE.ORDFICHEREF -> ORFICHE.LOGICALREF (CANDIDATE) | A021, B050, C038 |
| `CLIENTREF` | int | Cari Hesap Ref. (Account Receivable / Payable Reference) | orta | ldds, golden, olcum_dolu | 31.455 / 132 | – | A012, A031 |
| `LINETYPE` | smallint | Satır türü (LineType) | orta | ldds, eski, golden, olcum_dolu | 1.478 / 3 | bekleyen sipariş (CERTIFIED, operator); bekleyen sipariş miktarı (CERTIFIED, operator) | A012, A030, A031, B050 |
| `TRCODE` | smallint | Fiş Türü (Voucher Type) | orta | ldds, eski, golden, olcum_dolu | 31.455 / 1 | bekleyen sipariş (CERTIFIED, operator); bekleyen sipariş miktarı (CERTIFIED, operator) | A012, A030, A031, B050 |
| `DATE_` | datetime | Tarih (Date) | orta | ldds, golden, olcum_dolu | 31.455 / – | – | A030, C038 |
| `AMOUNT` | float | Sipariş miktarı. | yüksek | proje, golden, eski, olcum_dolu | 30.759 / – | bekleyen sipariş (CERTIFIED, operator); bekleyen sipariş miktarı (CERTIFIED, operator) | A012, A030, A031, B050 |
| `PRICE` | float | Sipariş satırı birim fiyatı. | orta | proje, eski, golden, olcum_dolu | 30.748 / – | bekleyen sipariş tutarı (CERTIFIED, operator); satır tutar (CANDIDATE) | A031, B050 |
| `TOTAL` | float | Sipariş satırı brüt tutarı. | orta | proje, eski, olcum_dolu | 31.444 / – | toplam tutar (CANDIDATE) | – |
| `SHIPPEDAMOUNT` | float | Bu satırdan sevk edilen miktar; bekleyen = AMOUNT − SHIPPEDAMOUNT. | yüksek | proje, golden, eski, olcum_dolu | 30.083 / – | bekleyen sipariş (CERTIFIED, operator); bekleyen sipariş miktarı (CERTIFIED, operator) | A012, A030, A031, B050 |
| `CLOSED` | smallint | Satır kapandı bayrağı (2026-09'da tüm satırlarda 0 — kapama kullanılmıyor görünüyor). | orta | proje, olcum, eski, golden | 0 / 1 | bekleyen sipariş (CERTIFIED, operator); bekleyen sipariş miktarı (CERTIFIED, operator) | A012, A031, B050, C004 |
| `DUEDATE` | datetime | Teslim termini; sevk gecikmesi STLINE.DATE_ ile karşılaştırılır. | yüksek | proje, eski, golden, olcum_dolu | 31.438 / – | sipariş termini (CERTIFIED, operator); temin date (CANDIDATE) | A012 |
| `LINENET` | float | Sipariş satırı net tutarı. | orta | ldds, olcum, eski | 30.670 / – | net satır tutarı (CANDIDATE) | – |
| `CANCELLED` | smallint | İptal Edilmiş (Cancelled) | orta | ldds, eski, golden | 0 / 1 | bekleyen sipariş (CERTIFIED, operator); bekleyen sipariş miktarı (CERTIFIED, operator) | A012, A030, A031, B050 |

### CLCARD — Cari hesap kartları

`LG_411_CLCARD` · 411: 257.378 satır · 211: 255.748 · ölçüm: tum_tablo (257.378 satır)

| Kolon | Tür | Anlam | Güven | Kaynak | 2026-09 dolu / farklı | Eski katalog | Golden |
|---|---|---|---|---|---|---|---|
| `LOGICALREF` | int | Cari Hesap Kartı Logical Ref. (Account Receivable / Payable Card Logical Reference) | orta | ldds, eski, golden, olcum_dolu | 257.378 / 257.378 | CLCARD.LOGICALREF -> INVOICE.CLIENTREF (CERTIFIED, seed); musteri id (CERTIFIED, rule-miner) | A006, A008, A012, A016 |
| `ACTIVE` | smallint | 0 kullanımda, 1 kullanım dışı. | yüksek | ldds, eski, olcum, golden | 27.787 / 2 | aktif (CERTIFIED); aktif müşteri (CERTIFIED, rule-miner) | A006 |
| `CARDTYPE` | smallint | Kart türü: 1 alıcı, 2 satıcı, 3 alıcı+satıcı (kartların %99,96'sı 3). | yüksek | ldds, olcum, eski | 257.378 / 4 | musteri tipi (CERTIFIED, rule-miner); alıcı (CANDIDATE, rule-miner) | – |
| `CODE` | varchar(17) | Cari kodu. Önek hesap planını izler: 120 müşteri (248k kart), 320 satıcı (7,1k), 195 iş avansı, 381, 136, 121, 340, TRN/TSF/HB-/N11/AMZ pazaryeri önekleri. | yüksek | proje, olcum, eski, golden | 257.378 / 257.378 | cari kod (CERTIFIED, rule-miner); cari kodu (CERTIFIED, seed) | A006, A008, A031, B029 |
| `DEFINITION_` | varchar(201) | Cari unvanı (aynı unvanlı farklı kartlar var; CODE ile grupla). | yüksek | proje, eski, golden, olcum_dolu | 257.312 / – | cari ad (CERTIFIED, rule-miner); cari adı (CERTIFIED, rule-miner) | A006, A012, A016, A022 |
| `SPECODE` | varchar(11) | Cari özel kodu 1: cari türü (ALICILAR, YAZARLAR, MÜTERCİM, ÇİZER, MATBAALAR, KAĞITÇILAR...). Serbest çalışan ayrımında kullanılır. | orta | proje, olcum, eski | 17.350 / 38 | musteri ozel kod (CERTIFIED, rule-miner); cari tur (CANDIDATE) | – |
| `CITY` | varchar(21) | Şehir. | yüksek | proje, eski, olcum_dolu | 256.417 / 835 | şehir (CERTIFIED, rule-miner) | – |
| `TELNRS1` | varchar(51) | Telefon Numarası 1 (Phone Number 1) | orta | ldds, eski, olcum_dolu | 104.572 / 80.710 | telefon (CERTIFIED, rule-miner); tel1 (CANDIDATE, rule-miner) | – |
| `FAXNR` | varchar(51) | Faks Numarası (Fax Number) | orta | ldds, eski, olcum_dolu | 3.953 / 2.480 | faks (CERTIFIED, rule-miner) | – |
| `TAXNR` | varchar(16) | Vergi numarası (Tax Number) | orta | ldds, eski, olcum_dolu | 13.664 / 11.154 | cari vn (CERTIFIED, rule-miner); vergi numarası (CERTIFIED, rule-miner) | – |
| `TAXOFFICE` | varchar(31) | Vergi dairesi (Tax Office) | orta | ldds, eski, olcum_dolu | 19.149 / 2.025 | cari vd (CERTIFIED, rule-miner); vergi dairesi (CERTIFIED, rule-miner) | – |
| `DISCRATE` | float | Kartta tanımlı iskonto oranı. | orta | proje, eski, golden, olcum_dolu | 5 / – | iskonto tanımlı (CERTIFIED, operator); kartında tanımlı iskonto (CERTIFIED, operator) | D015 |
| `EXTENREF` | int | Dosya Uzantısı Referansı (Extension File Reference) | orta | ldds, eski | 0 / 1 | uzantı kodu (CERTIFIED, otomatik-yoklama) | – |
| `PAYMENTREF` | int | Ödeme Planı Referansı (Payment Plan Reference) | orta | ldds, eski, olcum_dolu | 30.950 / 71 | ödeme takvimi referansı (CERTIFIED, otomatik-yoklama) | – |
| `EMAILADDR` | varchar(251) | E-Posta Adresi (E-Mail Address) | orta | ldds, eski, olcum_dolu | 251.758 / – | email (CERTIFIED, rule-miner); mail (CANDIDATE, rule-miner) | – |
| `WEBADDR` | varchar(101) | WEB adresi (WEB Address) | orta | ldds, eski, olcum_dolu | 57 / 49 | site linki (CERTIFIED, otomatik-yoklama) | – |
| `WARNMETHOD` | smallint | İhtar metodu (Reminder Method) | orta | ldds, eski | 0 / 1 | hatırlatma metodu (CERTIFIED, otomatik-yoklama) | – |
| `CLANGUAGE` | smallint | Dil (Language) | orta | ldds, eski, olcum_dolu | 932 / 3 | konuşma dili (CERTIFIED, otomatik-yoklama) | – |
| `VATNR` | varchar(33) | KDV numarası (VAT Number) | orta | ldds, eski, olcum_dolu | 1 / 2 | kdv no (CERTIFIED, otomatik-yoklama) | – |
| `BLOCKED` | smallint | Engellenmiş (Blocked) | orta | ldds, eski | 0 / 1 | kullanıma kapalı (CERTIFIED, otomatik-yoklama) | – |
| `BANKBRANCHS3` | varchar(17) | Banka Şubesi Numarası 3 (Bank Branch Number 3) | orta | ldds, eski, olcum_dolu | 7 / 8 | banka şube no (CERTIFIED, otomatik-yoklama) | – |
| `DELIVERYMETHOD` | varchar(13) | Teslimat Şekli (Delivery Type) | orta | ldds, eski | 0 / 1 | teslimat biçimi (CERTIFIED, otomatik-yoklama) | – |
| `TEXTINC` | smallint | Ayrıntılı Açıklama İçerir (Contains Detail Description) | orta | ldds, eski, olcum_dolu | 1 / 2 | Açıklama İşareti (CERTIFIED, otomatik-yoklama) | – |
| `SITEID` | smallint | Veri Merkezi (Data Processing Site) | orta | ldds, eski | 0 / 1 | iş yeri (CERTIFIED, otomatik-yoklama) | – |
| `EDINO` | varchar(25) | Veri Aktarım No (Data Interchange ID) | orta | ldds, eski, olcum_dolu | 3 / 4 | dii kodu (CERTIFIED, otomatik-yoklama) | – |
| `TRADINGGRP` | varchar(17) | Ticari İşlem Grubu (Trading Option) | orta | ldds, eski, olcum_dolu | 212.764 / 12 | ticari seçenek (CERTIFIED, otomatik-yoklama) | – |
| `CAPIBLOCK_CREADEDDATE` | datetime | Oluşturulma Tarihi (Created Date) | orta | ldds, eski, olcum_dolu | 257.378 / – | kart oluşturma tarihi (CERTIFIED, otomatik-yoklama) | – |
| `CAPIBLOCK_CREATEDHOUR` | smallint | Oluşturulma Saati (Created Hour) | orta | ldds, eski, olcum_dolu | 256.762 / 24 | açılış saati (CERTIFIED, otomatik-yoklama) | – |
| `CAPIBLOCK_MODIFIEDDATE` | datetime | Değiştirilme Tarihi (Modified Date) | orta | ldds, eski, olcum_dolu | 11.976 / – | değişme tarihi (CERTIFIED, otomatik-yoklama) | – |
| `PAYMENTPROC` | smallint | Borç izleme (0: döviz (Tracking Debit (0: Currency) | orta | ldds, eski, olcum_dolu | 196 / 2 | döviz durumu (CERTIFIED, otomatik-yoklama) | – |
| `PPGROUPCODE` | varchar(17) | Ödeme planı grup kodu (Payment Plan Card Group Code) | orta | ldds, eski | 0 / 1 | vade grubu (CERTIFIED, otomatik-yoklama) | – |
| `TAXOFFCODE` | varchar(31) | Vergi dairesi kodu (Tax Office Code) | orta | ldds, eski, olcum_dolu | 840 / 386 | vergi dairesi no (CERTIFIED, otomatik-yoklama) | – |
| `TOWNCODE` | varchar(13) | İlçe kodu (Town Code) | orta | ldds, eski, olcum_dolu | 191.526 / 725 | ilçe kod (CERTIFIED, otomatik-yoklama) | – |
| `TOWN` | varchar(51) | İlçe açıklaması (Town Description) | orta | ldds, eski, olcum_dolu | 230.244 / 1.555 | ilçe (CERTIFIED, rule-miner) | – |
| `CITYCODE` | varchar(13) | Şehir Kodu (City Code) | orta | ldds, eski, olcum_dolu | 199.152 / 179 | yerleşim kodu (CERTIFIED, otomatik-yoklama) | – |
| `ORDSENDMETHOD` | smallint | Sipariş formu gönderim metodu (Order Form Sending Method) | orta | ldds, eski | 0 / 1 | sipariş gönderim şekli (CERTIFIED, otomatik-yoklama) | – |
| `DSPSENDMETHOD` | smallint | İrsaliye form gönderimi metodu (Receipt/Dispatch Form Sending Method) | orta | ldds, eski | 0 / 1 | irsaliye yollama metodu (CERTIFIED, otomatik-yoklama) | – |
| `INVSENDMETHOD` | smallint | Fatura Gönderim Metodu (Invoice Form Sending Method) | orta | ldds, eski | 0 / 1 | gönderim tercihi (CERTIFIED, otomatik-yoklama) | – |
| `SUBSCRIBERSTAT` | smallint | Abone durumu (Subscriber Status) | orta | ldds, eski, olcum_dolu | 23 / 2 | abonelik durumu (CERTIFIED, otomatik-yoklama) | – |
| `SUBSCRIBEREXT` | varchar(17) | Abone ek bilgi (Subscriber Additional Info) | orta | ldds, eski | 0 / 1 | ek abone bilgisi (CERTIFIED, otomatik-yoklama) | – |
| `AUTOPAIDBANK` | varchar(25) | Otomatik Ödeme Banka Kodu (Autopayment Bank Code) | orta | ldds, eski | 0 / 1 | otomatik ödeme yapan banka (CERTIFIED, otomatik-yoklama) | – |
| `PAYMENTTYPE` | smallint | Ödeme türü (Payment Type) | orta | ldds, eski | 0 / 1 | cari ödeme tipi (CERTIFIED, otomatik-yoklama) | – |
| `LASTSENDREMLEV` | int | İhtar işlemleri seviyesi (Reminds level) | orta | ldds, eski | 0 / 1 | İhtar aşaması (CERTIFIED, otomatik-yoklama) | – |
| `EXTACCESSFLAGS` | int | 1. E-iş ortamında erişilebilir 2. Satış noktalarında erişilebilir (1. Accessible in e-business environment 2. Accessible in points of sale) | orta | ldds, eski, olcum_dolu | 4.606 / 3 | satış noktası erişimi (CERTIFIED, otomatik-yoklama) | – |
| `ORDSENDFORMAT` | smallint | Sipariş formu gönderim formatı (Order Form Sending Format) | orta | ldds, eski | 0 / 1 | sipariş formatı (CERTIFIED, otomatik-yoklama) | – |
| `DSPSENDFORMAT` | smallint | İrsaliye Formu Gönderim Formatı (Dispatch Form Sending Format) | orta | ldds, eski, olcum_dolu | 1 / 2 | irsaliye çıkış formatı (CERTIFIED, otomatik-yoklama) | – |
| `INVSENDFORMAT` | smallint | Fatura Gönderim Formatı (Invoice Form Sending Format) | orta | ldds, eski, olcum_dolu | 1 / 2 | fatura formatı (CERTIFIED, otomatik-yoklama) | – |
| `REMSENDFORMAT` | smallint | İhtar formu gönderim formatı (Reminder Form Sending Format) | orta | ldds, eski | 0 / 1 | hatırlatma şablonu (CERTIFIED, otomatik-yoklama) | – |
| `CLORDFREQ` | smallint | Sipariş sıklığı (gün) (Order Frequency (Day)) | orta | ldds, eski, olcum_dolu | 218.261 / 2 | sipariş sıklığı gün (CERTIFIED, otomatik-yoklama) | – |
| `ORDDAY` | smallint | Sipariş Günleri (Days of Orders) | orta | ldds, eski, olcum_dolu | 125 / 3 | sipariş ayı günü (CERTIFIED, otomatik-yoklama) | – |
| `LOGOID` | varchar(25) | Logo ID (Logo ID) | orta | ldds, eski, olcum_dolu | 5.526 / 5.403 | logo kimlik (CERTIFIED, otomatik-yoklama) | – |
| `LIDCONFIRMED` | smallint | Logo ID Onaylansın mı? (Evet / Hayır) (Logo ID Approved? (Yes / No)) | orta | ldds, eski | 0 / 1 | Logo ID onayı (CERTIFIED, otomatik-yoklama) | – |
| `EXPREGNO` | varchar(25) | İhracat Birlik Plaka Numarası (Export Union Registration Number) | orta | ldds, eski | 0 / 1 | ihracat kayıt no (CERTIFIED, otomatik-yoklama) | – |
| `EXPDOCNO` | varchar(33) | İhracat Belge Numarası (Export Document Number) | orta | ldds, eski | 0 / 1 | dış ticaret belge no (CERTIFIED, otomatik-yoklama) | – |
| `EXPBUSTYPREF` | int | İhracat liman izni (Permition Port Reference) | orta | ldds, eski | 0 / 1 | liman izni (CERTIFIED, otomatik-yoklama) | – |
| `PIECEORDINFLICT` | smallint | Parçalı sipariş teslimatı (Partially Order Delivery) | orta | ldds, eski | 0 / 1 | parçalı gönderim (CERTIFIED, otomatik-yoklama) | – |
| `COLLECTINVOICING` | smallint | Toplu Faturalama (Batch Billing) | orta | ldds, eski | 0 / 1 | toplu kesim (CERTIFIED, otomatik-yoklama) | – |
| `EBUSDATASENDTYPE` | smallint | E-İş Veri Gönderim Bilgileri (E-Business Data Sending Infos) | orta | ldds, eski, olcum_dolu | 24 / 2 | e-iş gönderim türü (CERTIFIED, otomatik-yoklama) | – |
| `INISTATUSFLAGS` | int | Banka Fişi Ve Satış Faturaları İçin Öndeğer (Default For Bank Slip and Sales Invoices) | orta | ldds, eski, olcum_dolu | 1 / 2 | varsayılan fiş (CERTIFIED, otomatik-yoklama) | – |
| `SLSORDERSTATUS` | smallint | Cari hesaptan LDX aracılığıyla gelen sipariş hareketlerinin içeriye hangi statüde alınacağını belirler. (Cari hesaptan LDX aracılığıyla gelen sipariş hareketlerinin içeriye hangi statüde alınacağını belirler.) | orta | ldds, eski | 0 / 1 | sipariş giriş statüsü (CERTIFIED, otomatik-yoklama) | – |
| `SLSORDERPRICE` | smallint | Cari hesaptan LDX aracılığıyla gelen sipariş hareketlerinin içeriye hangi statüde alınacağını belirler. (Cari hesaptan LDX aracılığıyla gelen sipariş hareketlerinin içeriye hangi statüde alınacağını belirler.) | orta | ldds, eski | 0 / 1 | LDX statüsü (CERTIFIED, otomatik-yoklama) | – |
| `LTRSENDMETHOD` | smallint | Mektup Yollama Metodu (Letter Sending Method) | orta | ldds, eski | 0 / 1 | mektup yollama şekli (CERTIFIED, otomatik-yoklama) | – |
| `LTRSENDFORMAT` | smallint | Mektup Yollama Formatı (Letter Sending Format) | orta | ldds, eski | 0 / 1 | mektup formatı (CERTIFIED, otomatik-yoklama) | – |
| `SAMEITEMCODEUSE` | smallint | Aynı malzeme kodları kullanılacak (Use Same Material Codes) | orta | ldds, eski | 0 / 1 | ortak malzeme kodu (CERTIFIED, otomatik-yoklama) | – |
| `STATECODE` | varchar(13) | Eyalet Kodu (State Code) | orta | ldds, eski | 0 / 1 | eyalet kodu (CERTIFIED, otomatik-yoklama) | – |
| `WFLOWCRDREF` | int | İş Akış Kartı Referansı (WFTASK Reference) | orta | ldds, eski | 0 / 1 | akış kartı referansı (CERTIFIED, otomatik-yoklama) | – |
| `PARENTCLREF` | int | Cari hesap mantıksal referansı (Accounts Receivable / Payable Logical Reference) | orta | ldds, eski, olcum_dolu | 6 / 4 | üst cari (CERTIFIED, otomatik-yoklama) | – |
| `LOWLEVELCODES1` | int | Hiyerarşi kodu 1 (Hierarchy Code1) | orta | ldds, eski, olcum_dolu | 257.102 / 257.089 | sınıf kodu (CERTIFIED, otomatik-yoklama) | – |
| `LOWLEVELCODES2` | int | Hiyerarşi kodu 2 (Hierarchy Code2) | orta | ldds, eski, olcum_dolu | 6 / 3 | ikinci hiyerarşi kodu (CERTIFIED, otomatik-yoklama) | – |
| `LOWLEVELCODES3` | int | Hiyerarşi kodu 3 (Hierarchy Code3) | orta | ldds, eski | 0 / 1 | üçüncü seviye kod (CERTIFIED, otomatik-yoklama) | – |
| `LOWLEVELCODES4` | int | Hiyerarşi kodu 4 (Hierarchy Code4) | orta | ldds, eski | 0 / 1 | dördüncü hiyerarşi kodu (CERTIFIED, otomatik-yoklama) | – |
| `LOWLEVELCODES6` | int | Hiyerarşi kodu 6 (Hierarchy Code6) | orta | ldds, eski | 0 / 1 | altıncı seviye kod (CERTIFIED, otomatik-yoklama) | – |
| `LOWLEVELCODES7` | int | Hiyerarşi kodu 7 (Hierarchy Code7) | orta | ldds, eski | 0 / 1 | yedinci seviye kodu (CERTIFIED, otomatik-yoklama) | – |
| `LOWLEVELCODES8` | int | Hiyerarşi kodu 8 (Hierarchy Code8) | orta | ldds, eski | 0 / 1 | cari hiyerarşi (CERTIFIED, otomatik-yoklama) | – |
| `LOWLEVELCODES10` | int | Hiyerarşi kodu 10 (Hierarchy Code10) | orta | ldds, eski | 0 / 1 | seviye kodu (CERTIFIED, otomatik-yoklama) | – |
| `PURCHBRWS` | smallint | Satın alma için (For Purchasing) | orta | ldds, eski, olcum_dolu | 257.377 / 2 | satın alma yetkisi (CERTIFIED, otomatik-yoklama) | – |
| `SALESBRWS` | smallint | Satış ve dağıtım için (For Sales & Distribution) | orta | ldds, eski, olcum_dolu | 257.377 / 2 | satış dağıtım durumu (CERTIFIED, otomatik-yoklama) | – |
| `IMPBRWS` | smallint | İthalat için (For Import) | orta | ldds, eski, olcum_dolu | 257.377 / 2 | dış alım (CERTIFIED, otomatik-yoklama) | – |
| `EXPBRWS` | smallint | İhracat için (For Export) | orta | ldds, eski, olcum_dolu | 257.377 / 2 | dış ticaret (CERTIFIED, otomatik-yoklama) | – |
| `FINBRWS` | smallint | Finans için (For Finance) | orta | ldds, eski, olcum_dolu | 257.377 / 2 | finans bölümü (CERTIFIED, otomatik-yoklama) | – |
| `ADDTOREFLIST` | smallint | Referans listesine ekle (Add to Reference List) | orta | ldds, eski, olcum_dolu | 1 / 2 | referans listesinde (CERTIFIED, otomatik-yoklama) | – |
| `TEXTREFTR` | smallint | GO sayfa düzenleyicisi (Türkçe) (GO Page Editor (Turkish)) | orta | ldds, eski | 0 / 1 | sayfa düzeni (CERTIFIED, otomatik-yoklama) | – |
| `TEXTREFEN` | smallint | GO sayfa düzenleyicisi (İngilizce) (GO Page Editor (English)) | orta | ldds, eski | 0 / 1 | düzenleme referansı (CERTIFIED, otomatik-yoklama) | – |
| `CLCRM` | smallint | Cari hesap CRM içinde kullanılıyor mu? (Is Ar/Ap used in CRM?) | orta | ldds, eski | 0 / 1 | CRM kaydı (CERTIFIED, otomatik-yoklama) | – |
| `GRPFIRMNR` | smallint | Grup şirketi numarası (Group Company Number) | orta | ldds, eski | 0 / 1 | bağlı şirket (CERTIFIED, otomatik-yoklama) | – |
| `CONSCODEREF` | int | CONSCODES referansı (CONSCODES Reference) | orta | ldds, eski | 0 / 1 | konsinye referansı (CERTIFIED, otomatik-yoklama) | – |
| `SPECODE2` | varchar(11) | Satış kanalı / müşteri grubu (KITAPCI, E-TICARET, DAGITICI, ZINCIR, ...); boş = 'Grup kodu boş'. Kartların %86'sında boş, ama 2026-09 satış cirosunun yalnız %2,5'i boş kanallı. | yüksek | proje, motor, olcum, eski, golden | 36.268 / 32 | kanal (CERTIFIED, operator); kanal kodu (CERTIFIED, claude-inceleme) | B019 |
| `SPECODE3` | varchar(11) | Özel kod 3 (Auxiliary Code3) | orta | ldds, eski, olcum_dolu | 219.773 / 17 | musteri ozel kod 3 (CERTIFIED, rule-miner) | – |
| `SPECODE4` | varchar(11) | Özel kod 4 (Auxiliary Code4) | orta | ldds, eski, olcum_dolu | 6.251 / 45 | musteri ozel kod 4 (CERTIFIED, rule-miner) | – |
| `SPECODE5` | varchar(11) | Özel kod 5 (Auxiliary Code5) | orta | ldds, eski, olcum_dolu | 36.091 / 32 | musteri ozel kod 5 (CERTIFIED, rule-miner); bmt (CANDIDATE) | – |
| `OFFSENDMETHOD` | smallint | Teklif/sözleşme gönderim yöntemi (Proposal/Contract Sending Method) | orta | ldds, eski | 0 / 1 | teklif gönderim şekli (CERTIFIED, otomatik-yoklama) | – |
| `OFFSENDFORMAT` | smallint | Teklif/sözleşme gönderim biçimi (Proposal/Contract Sending Format) | orta | ldds, eski | 0 / 1 | gönderim biçimi (CERTIFIED, otomatik-yoklama) | – |
| `EBANKNO` | smallint | Elektronik bankacılık (E-Banking) | orta | ldds, eski, olcum_dolu | 8 / 3 | e-banka kodu (CERTIFIED, otomatik-yoklama) | – |
| `LOANGRPCTRL` | smallint | Borç takip işlemleri grup şirketi bazında yapılacak (Debt tracking operations will be done base on group company) | orta | ldds, eski | 0 / 1 | borç takip grubu (CERTIFIED, otomatik-yoklama) | – |
| `BANKNAMES2` | varchar(51) | Banka adı 2 (Bank Name2) | orta | ldds, eski, olcum_dolu | 1.094 / 82 | ikinci banka adı (CERTIFIED, otomatik-yoklama) | – |
| `BANKNAMES3` | varchar(51) | Banka adı 3 (Bank Name3) | orta | ldds, eski, olcum_dolu | 20 / 19 | üçüncü banka adı (CERTIFIED, otomatik-yoklama) | – |
| `LDXFIRMNR` | smallint | Veri aktarımının şirketi (Compnay of Data Transfer) | orta | ldds, eski | 0 / 1 | aktarım firması (CERTIFIED, otomatik-yoklama) | – |
| `ACCEPTEINV` | smallint | E-fatura mükellefi bayrağı (1 evet). | orta | eski, olcum_dolu | 7.196 / 2 | e fatura (CERTIFIED, rule-miner) | – |
| `DEFINITION2` | varchar(201) | Aday anlam (eski katalog/TİMAŞ görünüm takma adı): cari unvan2, uretici firma unvan2 | düşük | eski, olcum_dolu | 21.802 / – | cari unvan2 (CERTIFIED, rule-miner); uretici firma unvan2 (CERTIFIED, rule-miner) | – |

### ITEMS — Malzemeler

`LG_411_ITEMS` · 411: 32.859 satır · 211: 29.759 · ölçüm: tum_tablo (32.859 satır)

| Kolon | Tür | Anlam | Güven | Kaynak | 2026-09 dolu / farklı | Eski katalog | Golden |
|---|---|---|---|---|---|---|---|
| `LOGICALREF` | int | Malzeme Kartı (Item Card Logical Reference) | orta | ldds, eski, golden, olcum_dolu | 32.859 / 32.859 | ITEMS.LOGICALREF -> STLINE.STOCKREF (CERTIFIED, seed); gaz stok logicalref (CERTIFIED, rule-miner) | A012, A027, A051, A055 |
| `ACTIVE` | smallint | 0 kullanımda, 1 kullanım dışı (kart listelerinde ACTIVE=0). | yüksek | proje, ldds, eski, golden, olcum_dolu | 423 / 2 | aktif stok kartı (CERTIFIED, operator); tup stok aktif (CERTIFIED, rule-miner) | A051, A056 |
| `CARDTYPE` | smallint | Malzeme kartı türü: 1 ticari mal, 10 hammadde, 11 yarı mamul, 12 mamul (kitap), 13 tüketim malı, 4 sabit kıymet, 20 malzeme sınıfı. | yüksek | ldds, olcum, eski | 32.859 / 8 | depozitolu mal (CERTIFIED, otomatik-yoklama); genel malzeme sınıfı (CERTIFIED, rule-miner) | – |
| `CODE` | varchar(25) | Stok (kitap) kodu; CRM new_kitapBase.new_stokkodu ile eşleşir. | yüksek | proje, motor, eski, golden, olcum_dolu | 32.859 / 32.859 | gaz kodu (CERTIFIED, rule-miner); gaz stok kodu (CERTIFIED, rule-miner) | A027, A051, A055, A056 |
| `NAME` | varchar(51) | Malzeme/kitap adı. | yüksek | proje, eski, golden, olcum_dolu | 32.832 / 29.398 | gaz cinsi (CERTIFIED, rule-miner); gaz stok adi (CERTIFIED, rule-miner) | A012, A027, A051, A055 |
| `STGRPCODE` | varchar(25) | Stok grup kodu. | orta | proje, eski, olcum_dolu | 15.023 / 16 | aktif pasif (CERTIFIED, rule-miner); itm grpcode (CERTIFIED, rule-miner) | – |
| `SPECODE` | varchar(11) | Yayınevi/imprint (Timaş Çocuk, Genç Timaş, Mavi Kirpi...); ayrıca kısa kodlar (T, Ç, TARCIN...) var. | orta | proje, olcum, eski | 30.909 / 63 | dizi (CERTIFIED, seed); imprint (CERTIFIED, seed) | – |
| `CYPHCODE` | varchar(11) | Yetki Kodu (Auth. Code) | orta | ldds, eski, olcum_dolu | 12.303 / 8 | urun yetki kodu (CERTIFIED, rule-miner) | – |
| `UNITSETREF` | int | Birim seti → UNITSETF.LOGICALREF. | yüksek | ldds, olcum, eski | 32.858 / 10 | tup stok birim set id (CERTIFIED, rule-miner) | – |
| `EXPCTGNO` | varchar(25) | İhracat Kategori Numarası (Export Category Number) | orta | ldds, eski, olcum_dolu | 12.061 / 23 | yayin yönetmeni (CERTIFIED, rule-miner) | – |
| `SPECODE2` | varchar(11) | Özel kod 2 (Auxiliary Code2) | orta | ldds, eski, olcum_dolu | 11.646 / 115 | tup stok specode2 (CERTIFIED, rule-miner); urun ozel kodu2 (CERTIFIED, rule-miner) | – |
| `SPECODE3` | varchar(11) | Özel kod 3 (Auxiliary Code3) | orta | ldds, eski, olcum_dolu | 11.084 / 675 | tup stok specode3 (CERTIFIED, rule-miner); urun ozel kodu3 (CERTIFIED, rule-miner) | – |
| `SPECODE4` | varchar(11) | Özel kod 4 (Auxiliary Code4) | orta | ldds, eski, olcum_dolu | 11.757 / 2.109 | tup stok specode4 (CERTIFIED, rule-miner); urun ozel kodu4 (CERTIFIED, rule-miner) | – |
| `SPECODE5` | varchar(11) | Özel kod 5 (Auxiliary Code5) | orta | ldds, eski, olcum_dolu | 14.262 / 524 | cikis tarihi (CERTIFIED, rule-miner); tup stok specode5 (CERTIFIED, rule-miner) | – |
| `NAME2` | varchar(51) | Aday anlam (eski katalog/TİMAŞ görünüm takma adı): stok adi2, t descr, tup stok adi2 | düşük | eski | 0 / 1 | stok adi2 (CERTIFIED, rule-miner); tup stok adi2 (CERTIFIED, rule-miner) | – |
| `NAME3` | varchar(201) | Aday anlam (eski katalog/TİMAŞ görünüm takma adı): stok adi3, tup stok adi3 | düşük | eski, olcum_dolu | 804 / – | stok adi3 (CERTIFIED, rule-miner); tup stok adi3 (CERTIFIED, rule-miner) | – |
| `NAME4` | varchar(201) | Aday anlam (eski katalog/TİMAŞ görünüm takma adı): stok adi4 | düşük | eski, olcum_dolu | 10 / – | stok adi4 (CERTIFIED, rule-miner) | – |

### CLFLINE — Cari hesap hareketleri

`LG_411_01_CLFLINE` · 411: 119.838 satır · 211: 840.348 · ölçüm: WHERE DATE_>='20260901' AND DATE_<'20261001' (16.300 satır)

| Kolon | Tür | Anlam | Güven | Kaynak | 2026-09 dolu / farklı | Eski katalog | Golden |
|---|---|---|---|---|---|---|---|
| `CLIENTREF` | int | Cari → CLCARD.LOGICALREF. | yüksek | proje, olcum, eski, golden | 16.266 / 1.524 | CLFLINE.CLIENTREF -> CLCARD.LOGICALREF (CERTIFIED, claude-inceleme) | A008 |
| `SOURCEFREF` | int | Kaynak belge; hedef modüle göre değişir: 4→INVOICE, 5→CLFICHE, 6→CSROLL, 7→BNFLINE (satır!), 10→KSLINES. 2026-09'da hepsi %99–100. | yüksek | olcum, eski | 16.291 / 16.023 | kaynak ref (CANDIDATE) | – |
| `DATE_` | datetime | Hareket tarihi. | yüksek | proje, eski, olcum_dolu | 16.300 / – | fatura tarihi (CANDIDATE) | – |
| `MODULENR` | smallint | Kaynak modül: 4 fatura, 5 cari hesap fişi, 6 çek/senet bordrosu, 7 banka, 10 kasa, 61 çek/senet (1 satır). | yüksek | ldds, olcum, eski | 16.300 / 6 | cari hesap fişleri (CERTIFIED, rule-miner); kasa fişi (CERTIFIED, operator) | – |
| `TRCODE` | smallint | Cari hareket türü; MODULENR ile birlikte okunur (kod tablosu). | yüksek | ldds, proje, olcum, eski | 16.300 / 23 | alacak d (CERTIFIED, rule-miner); alınan h f (CERTIFIED, rule-miner) | – |
| `TRANNO` | varchar(17) | Hareket numarası (Transaction Number) | orta | ldds, eski, olcum_dolu | 16.300 / 15.628 | islem no (CERTIFIED, rule-miner); fatura no (CANDIDATE) | – |
| `LINEEXP` | varchar(251) | Hareket açıklaması (Transaction Description) | orta | ldds, eski, olcum_dolu | 9.284 / – | clfline lineexp (CERTIFIED, rule-miner); satir açiklamasi (CANDIDATE) | – |
| `SIGN` | smallint | 0 borç (cari borçlanır: satış faturası), 1 alacak (tahsilat, alış faturası). | yüksek | ldds, eski, olcum, golden | 2.095 / 2 | alacak hareketi (CERTIFIED, rule-miner); borç alacak yönü (CERTIFIED, otomatik-yoklama) | A008 |
| `AMOUNT` | float | Yerel para tutar (TL). | yüksek | proje, motor, eski, golden, olcum_dolu | 16.278 / – | müşteri tahsilatı (CERTIFIED, operator:claude (muhasebe testi, 2026-09-21)); tedarikçi ödemesi (CERTIFIED, operator:claude (muhasebe testi, 2026-09-21)) | A008 |
| `TRNET` | float | İşlem dövizi tutarı. | orta | eski, ldds, olcum_dolu | 16.154 / – | credit cur (CERTIFIED, rule-miner); debit cur (CERTIFIED, rule-miner) | – |
| `CANCELLED` | smallint | İptal bayrağı. | yüksek | proje, motor, eski, golden | 0 / 1 | müşteri tahsilatı (CERTIFIED, operator:claude (muhasebe testi, 2026-09-21)); tedarikçi ödemesi (CERTIFIED, operator:claude (muhasebe testi, 2026-09-21)) | A008 |
| `SPECODE2` | varchar(41) | Aday anlam (eski katalog/TİMAŞ görünüm takma adı): hareket ozel kodu2 | düşük | eski | 0 / 1 | hareket ozel kodu2 (CERTIFIED, rule-miner) | – |

### CLFICHE — Cari hesap fişeri

`LG_411_01_CLFICHE` · 411: 5.365 satır · 211: 23.453 · ölçüm: WHERE DATE_>='20260901' AND DATE_<'20261001' (932 satır)

| Kolon | Tür | Anlam | Güven | Kaynak | 2026-09 dolu / farklı | Eski katalog | Golden |
|---|---|---|---|---|---|---|---|
| `FICHENO` | varchar(17) | Fiş Numarası (Voucher Number) | orta | ldds, eski, olcum_dolu | 932 / 932 | cari fiş no (CERTIFIED, otomatik-yoklama) | – |
| `TRCODE` | smallint | Cari hesap fişi türü (1 nakit tahsilat, 2 nakit ödeme, 3 borç dekontu, 4 alacak dekontu, 5 virman, 14 açılış, 46 alınan serbest meslek makbuzu, 70 kredi kartı, 71 kredi kartı iade, 72 firma kredi kartı...). | yüksek | ldds, olcum, eski | 932 / 6 | acilis fisi (CANDIDATE); alacak dekont (CANDIDATE) | – |
| `DEBIT` | float | Fiş borç toplamı. | orta | ldds, olcum | 42 / – | – | – |
| `CREDIT` | float | Fiş alacak toplamı. | orta | ldds, olcum | 927 / – | – | – |
| `REPDEBIT` | float | Borç (RD) (Debit (Reporting Currency)) | orta | ldds, eski | 0 / – | raporlama borcu (CERTIFIED, otomatik-yoklama) | – |
| `REPCREDIT` | float | Alacak (RD) (Credit (Reporting Currency)) | orta | ldds, eski | 0 / – | fiş alacak (CERTIFIED, otomatik-yoklama) | – |
| `CAPIBLOCK_CREATEDMIN` | smallint | Oluşturulma Dakikası (Created Minute) | orta | ldds, eski, olcum_dolu | 907 / 59 | fiş dakikası (CERTIFIED, otomatik-yoklama) | – |
| `CAPIBLOCK_CREATEDSEC` | smallint | Oluşturulma Saniyesi (Created Second) | orta | ldds, eski, olcum_dolu | 918 / 60 | fiş saniyesi (CERTIFIED, otomatik-yoklama) | – |
| `CAPIBLOCK_MODIFIEDBY` | smallint | Değiştiren (Modified By) | orta | ldds, eski, olcum_dolu | 925 / 7 | kaydı güncelleyen (CERTIFIED, otomatik-yoklama) | – |
| `CAPIBLOCK_MODIFIEDDATE` | datetime | Değiştirilme Tarihi (Modified Date) | orta | ldds, eski, olcum_dolu | 925 / – | kayıt güncelleme (CERTIFIED, otomatik-yoklama) | – |
| `INVOREF` | int | Cari Hesap Hareketi Logical Ref. (Account Receivable / Payable Transaction Reference) | orta | ldds, eski | 0 / 1 | borç alacak ref (CERTIFIED, otomatik-yoklama) | – |
| `CASHACCREF` | int | Kasa muhasebe hesabı ref. (Safe Deposit General Ledger Account Reference) | orta | ldds, eski, olcum_dolu | 812 / 3 | kasa muhasebe hesabı (CERTIFIED, otomatik-yoklama) | – |
| `CASHCENREF` | int | Kasa masraf merkezi ref. (Safe Deposit Overhead Pool Reference) | orta | ldds, eski, olcum_dolu | 812 / 2 | kasa masraf merkezi (CERTIFIED, otomatik-yoklama) | – |
| `PRINTCNT` | smallint | Basılmış Toplam Hesap (Total Count Of Printed) | orta | ldds, eski | 0 / 1 | basılmış kopya (CERTIFIED, otomatik-yoklama) | – |
| `CANCELLEDACC` | smallint | Muhasebeleştirme İşlemi İptal Edilmiş (Cancelled Posting To General Ledger) | orta | ldds, eski | 0 / 1 | işlem iptali (CERTIFIED, otomatik-yoklama) | – |
| `LINEEXCTYP` | smallint | Döviz Türü (Satır) (F. Currency Type (Line)) | orta | ldds, eski | 0 / 1 | satır döviz türü (CERTIFIED, otomatik-yoklama) | – |
| `ORGLOGICREF` | int | Orijinal Kayıt Log. Ref. (Original Record Logical Reference) | orta | ldds, eski | 0 / 1 | kayıt izi (CERTIFIED, otomatik-yoklama) | – |
| `BNACCREF` | int | EMUHACC LOGICALREF (EMUHACC LOGICALREF) | orta | ldds, eski | 0 / 1 | işlem fiş no (CERTIFIED, otomatik-yoklama) | – |
| `POINTCOMMCENREF` | int | Masraf Merkezi Referansı (Overhead Pools Reference) | orta | ldds, eski | 0 / 1 | gider havuzu (CERTIFIED, otomatik-yoklama) | – |
| `STATUS` | smallint | Durumu (Status) | orta | ldds, eski | 0 / 1 | vade durumu (CERTIFIED, otomatik-yoklama) | – |
| `WFLOWCRDREF` | int | İş akış kartı referansı (Work Flow Card Reference) | orta | ldds, eski | 0 / 1 | workflow kartı (CERTIFIED, otomatik-yoklama) | – |
| `POSTERMINALNUM` | varchar(31) | POS terminal numarası (POS Terminal Number) | orta | ldds, eski | 0 / 1 | pos noktası (CERTIFIED, otomatik-yoklama) | – |

### PAYTRANS — Ödeme/Tahsilat hareketleri

`LG_411_01_PAYTRANS` · 411: 139.648 satır · 211: 1.102.705 · ölçüm: WHERE DATE_>='20260901' AND DATE_<'20261001' (13.096 satır)

| Kolon | Tür | Anlam | Güven | Kaynak | 2026-09 dolu / farklı | Eski katalog | Golden |
|---|---|---|---|---|---|---|---|
| `LOGICALREF` | int | Ödeme /Tahsilat hareketleri log. Ref. (Payment / Collection Transaction Logical Reference) | orta | ldds, eski, golden, olcum_dolu | 13.096 / 13.096 | PAYTRANS.LOGICALREF -> PAYTRANS.CROSSREF (CANDIDATE) | B007 |
| `CARDREF` | int | Cari → CLCARD.LOGICALREF. | yüksek | ldds, olcum | 13.062 / 1.484 | – | – |
| `DATE_` | datetime | Vade (ödeme planı) tarihi — işlem tarihi değil; işlem tarihi PROCDATE. Faturada ort. 40,9 gün sonrası. | yüksek | proje, olcum, eski, golden | 13.096 / – | vade tarihi (CERTIFIED, rule-miner) | A060, B019 |
| `MODULENR` | smallint | Kaynak modül: 4 fatura, 5 cari fiş, 6 çek/senet, 7 banka, 10 kasa. | yüksek | ldds, olcum, eski, golden | 13.096 / 6 | firma kredi cı fişi (CERTIFIED, rule-miner); iade edilen çekler (CERTIFIED, rule-miner) | A060, B007, B019 |
| `SIGN` | smallint | 0 borç (alacağımız doğar), 1 alacak. | orta | olcum, eski, golden | 2.531 / 2 | borc alacak (CERTIFIED, rule-miner); borç toplamı (CERTIFIED, rule-miner) | A060, B019 |
| `FICHEREF` | int | Kaynak kayıt; modüle göre: 4→INVOICE, 5→CLFLINE (fiş değil satır), 6→CSROLL, 7→BNFLINE, 10→KSLINES. | yüksek | olcum, golden | 13.096 / 12.600 | – | A060, B019 |
| `FICHELINEREF` | int | Kaynak satır referansı; 2026-09'da 206 satırda dolu, hedefi doğrulanamadı. | düşük | olcum | 206 / 207 | – | – |
| `TRCODE` | smallint | Tanımlanmış fiş türü (Specified Voucher Type) | orta | ldds, eski, olcum_dolu | 13.096 / 15 | firma kredi cı fişi (CERTIFIED, rule-miner); iade edilen çekler (CERTIFIED, rule-miner) | – |
| `TOTAL` | float | Ödeme planı satırı tutarı. | yüksek | proje, golden, eski, olcum_dolu | 13.096 / – | borç toplamı (CERTIFIED, rule-miner); alacak (CANDIDATE) | – |
| `PAID` | float | Kapatılan (ödenen) tutar. 2026'da 139.648 satırın 14'ünde dolu — kapama kullanılmıyor. | yüksek | proje, olcum, golden | 0 / – | – | B007 |
| `CROSSREF` | int | Kapatan karşı ödeme satırı → PAYTRANS.LOGICALREF. 2026'da hiç dolu değil. | yüksek | proje, olcum, golden | 0 / 1 | – | B007 |
| `CANCELLED` | smallint | İptal Edilmiş (Cancelled) | orta | ldds, eski, golden | 0 / 1 | odeme (CANDIDATE) | A060, B007, B019 |
| `PROCDATE` | datetime | İşlem (belge) tarihi. | yüksek | ldds, olcum, eski | 13.096 / – | islem tarihi (CERTIFIED, rule-miner) | – |
| `PAYMENTTYPE` | smallint | Ödeme türü: 0 işlem yok, 1 nakit, 2 çek, 3 senet, 4 kredi kartı. | orta | ldds, olcum, eski | 1.229 / 5 | cash (CANDIDATE); check (CANDIDATE) | – |
| `LINEEXP` | varchar(201) | Aday anlam (eski katalog/TİMAŞ görünüm takma adı): paytrans lineexp | düşük | eski, olcum_dolu | 800 / – | paytrans lineexp (CERTIFIED, rule-miner) | – |

### KSLINES — Kasa işlemleri

`LG_411_01_KSLINES` · 411: 1.377 satır · 211: 7.921 · ölçüm: WHERE DATE_>='20260901' AND DATE_<'20261001' (108 satır)

| Kolon | Tür | Anlam | Güven | Kaynak | 2026-09 dolu / farklı | Eski katalog | Golden |
|---|---|---|---|---|---|---|---|
| `CARDREF` | int | Kasa kartı → KSCARD.LOGICALREF. | yüksek | ldds, olcum | 108 / 4 | – | – |
| `TRCODE` | smallint | Kasa hareket türü: 11 cari hesap tahsilatı, 12 cari hesap ödemesi, 21-22 banka, 31-39 fatura, 61-64 çek/senet, 71-74 kasa (virman/açılış). | orta | ldds, olcum, eski | 108 / 6 | alinan vade fark (CANDIDATE); alinan vade fark fatur (CANDIDATE) | – |
| `AMOUNT` | float | Tutar (TL). | yüksek | proje, olcum_dolu | 108 / – | – | – |
| `SIGN` | smallint | 0 giriş (tahsil), 1 çıkış (ödeme). | yüksek | proje, olcum | 17 / 2 | – | – |

### KSCARD — Kasa kartları

`LG_411_KSCARD` · 411: 9 satır · 211: 9 · ölçüm: tum_tablo (9 satır)

| Kolon | Tür | Anlam | Güven | Kaynak | 2026-09 dolu / farklı | Eski katalog | Golden |
|---|---|---|---|---|---|---|---|
| `CODE` | varchar(17) | Kasa kodu. | orta | ldds, olcum_dolu | 9 / 9 | – | – |
| `NAME` | varchar(51) | Kasa adı. | orta | ldds, olcum_dolu | 9 / 9 | – | – |

### BNFICHE — Banka fişleri

`LG_411_01_BNFICHE` · 411: 2.563 satır · 211: 17.254 · ölçüm: WHERE DATE_>='20260901' AND DATE_<'20261001' (278 satır)

| Kolon | Tür | Anlam | Güven | Kaynak | 2026-09 dolu / farklı | Eski katalog | Golden |
|---|---|---|---|---|---|---|---|
| `TRCODE` | smallint | Banka fişi türü: 1 banka işlem, 2 virman, 3 gelen havale, 4 gönderilen havale, 16 banka alınan hizmet faturası. | orta | ldds, olcum, eski | 278 / 5 | banka fiş türü (CERTIFIED, otomatik-yoklama); hava (CANDIDATE) | – |
| `MODULENR` | smallint | Modül Numarası (Module Number) | orta | ldds, eski, olcum_dolu | 278 / 1 | kayıt türü numarası (CERTIFIED, otomatik-yoklama); bank (CANDIDATE) | – |
| `SOURCEFREF` | int | Bağlı fiş ref. (Voucher Reference That Connected) | orta | ldds, eski | 0 / 1 | bağlı fiş no (CERTIFIED, otomatik-yoklama) | – |
| `ACCOUNTED` | smallint | Muhasebeleştirildi (Posted to General Ledger) | orta | ldds, eski, olcum_dolu | 278 / 1 | muhasebe kaydı yapıldı (CERTIFIED, otomatik-yoklama) | – |
| `DEBITTOT` | float | Borç Toplamı (Debit Total) | orta | ldds, eski, olcum_dolu | 196 / – | borç yekünü (CERTIFIED, otomatik-yoklama) | – |
| `GENEXP1` | varchar(51) | Açıklama (Description) | orta | ldds, eski, olcum_dolu | 278 / 66 | fiş açıklama metni (CERTIFIED, otomatik-yoklama) | – |
| `CAPIBLOCK_CREATEDHOUR` | smallint | Oluşturulma Saati (Created Hour) | orta | ldds, eski, olcum_dolu | 278 / 12 | kaydedilme saati (CERTIFIED, otomatik-yoklama) | – |
| `CAPIBLOCK_MODIFIEDHOUR` | smallint | Değiştirilme Saati (Modified Hour) | orta | ldds, eski, olcum_dolu | 20 / 11 | son değişme saati (CERTIFIED, otomatik-yoklama) | – |
| `CANCELLEDACC` | smallint | Muhasebeleştirme İşlemi İptal Edilmiş (Cancelled Posting to General Ledger) | orta | ldds, eski | 0 / 1 | iptal edilmiş işlem (CERTIFIED, otomatik-yoklama) | – |
| `GENEXCTYP` | smallint | Döviz Türü (Genel) (F. Currency Type (General)) | orta | ldds, eski, olcum_dolu | 278 / 1 | yabancı para türü (CERTIFIED, otomatik-yoklama) | – |
| `LINEEXCTYP` | smallint | Döviz Türü (Satır) (F. Currency Type (Line)) | orta | ldds, eski, olcum_dolu | 4 / 2 | sabit kur (CERTIFIED, otomatik-yoklama) | – |
| `REPDEBIT` | float | Borç (RD) (Debit (Reporting Currency)) | orta | ldds, eski, olcum_dolu | 3 / – | RD borcu (CERTIFIED, otomatik-yoklama) | – |
| `REPCREDIT` | float | Alacak (RD) (Credit (Reporting Currency)) | orta | ldds, eski, olcum_dolu | 4 / – | RD alacak (CERTIFIED, otomatik-yoklama) | – |
| `TEXTINC` | smallint | Ayrıntılı Açıklama İçerir (1- Evet (Contains Detail Description (1:Yes) | orta | ldds, eski | 0 / 1 | detay içerir (CERTIFIED, otomatik-yoklama) | – |
| `CRCARDWZD` | smallint | Ödeme sihirbazı tarafından mı oluşturuldu? (Has it been generated by payment wizard?) | orta | ldds, eski | 0 / 1 | ödeme sihirbazı işareti (CERTIFIED, otomatik-yoklama); payment wizard credit card (CANDIDATE) | – |
| `TRANGRPNO` | varchar(17) | Hareket grup numarası (fiş) (Transaction Group Nr. (For slip)) | orta | ldds, eski | 0 / 1 | işlem grup numarası (CERTIFIED, otomatik-yoklama) | – |
| `COLLATROLLREF` | int | COLLATRLROLL referansı (COLLATRLROLL Reference) | orta | ldds, eski | 0 / 1 | teminat ID (CERTIFIED, otomatik-yoklama) | – |
| `COLLATTRNREF` | int | COLLATRLTRAN referansı (COLLATRLTRAN Reference) | orta | ldds, eski | 0 / 1 | teminat fiş referansı (CERTIFIED, otomatik-yoklama) | – |
| `BNCRREF` | int | Banka kredileri (Port) referansı (Bank Credits Port Reference) | orta | ldds, eski, olcum_dolu | 14 / 13 | kredi portföy referansı (CERTIFIED, otomatik-yoklama) | – |
| `REFLECTED` | smallint | KDV aktarıldı mı? (VAT Transferred?) | orta | ldds, eski | 0 / 1 | KDV yansıtıldı mı (CERTIFIED, otomatik-yoklama) | – |
| `REFLACCFICHEREF` | int | Genel Muhasebe Fişleri Referansı (General Ledger Vouchers Reference) | orta | ldds, eski | 0 / 1 | banka fişi no (CERTIFIED, otomatik-yoklama) | – |
| `CANCELLEDREFLACC` | smallint | İptal edilen faturanın KDV tutarı aktarıldı mı? (Is cancelled invoice's VAT amount transferred?) | orta | ldds, eski | 0 / 1 | iptal faturada KDV aktarımı (CERTIFIED, otomatik-yoklama) | – |

### BNFLINE — Banka hareketleri

`LG_411_01_BNFLINE` · 411: 21.323 satır · 211: 119.617 · ölçüm: WHERE DATE_>='20260901' AND DATE_<'20261001' (2.484 satır)

| Kolon | Tür | Anlam | Güven | Kaynak | 2026-09 dolu / farklı | Eski katalog | Golden |
|---|---|---|---|---|---|---|---|
| `BANKREF` | int | Banka kartı → BNCARD.LOGICALREF (%100). | yüksek | ldds, olcum | 2.484 / 7 | – | – |
| `BNACCREF` | int | Banka hesabı → BANKACC.LOGICALREF (%100). | yüksek | ldds, olcum | 2.484 / 34 | – | – |
| `SOURCEFREF` | int | Banka fişi → BNFICHE.LOGICALREF (MODULENR 7'de %99,4). MODULENR 0 satırlarında (kredi kartı fişinden doğan) boş. | yüksek | olcum | 1.560 / 320 | – | – |
| `SIGN` | smallint | 0 giriş, 1 çıkış. | yüksek | proje, olcum | 914 / 2 | – | – |
| `TRCODE` | smallint | Hareket türü (Transaction Type) | orta | ldds, eski, olcum_dolu | 2.484 / 7 | banka işlem fişi (CERTIFIED, rule-miner); çek ödemesi (CERTIFIED, rule-miner) | – |
| `MODULENR` | smallint | Kaynak modül: 7 banka, 0 kredi kartı fişinden (CLFICHE 70), 6/61/62/65 çek/senet, 10 kasa. | orta | ldds, olcum, eski | 1.569 / 7 | bank (CANDIDATE) | – |
| `AMOUNT` | float | Tutar (TL). | yüksek | proje, olcum_dolu | 2.446 / – | – | – |

### BANKACC — Banka hesapları

`LG_411_BANKACC` · 411: 118 satır · 211: 115 · ölçüm: tum_tablo (118 satır)

| Kolon | Tür | Anlam | Güven | Kaynak | 2026-09 dolu / farklı | Eski katalog | Golden |
|---|---|---|---|---|---|---|---|
| `CARDTYPE` | smallint | Banka hesap türü: 1 ticari, 2 kredi, 3 dövizli ticari, 4 dövizli kredi; 5 LDDS'de yok (POS/kredi kartı hesabı olabilir — tahmin). | orta | ldds, olcum, eski | 118 / 4 | kredi hesabı (CERTIFIED, otomatik-yoklama); dovizl ticar (CANDIDATE) | – |
| `DEFINITION_` | varchar(51) | Banka Hesabı Adı (Bank Account Name) | orta | ldds, eski, olcum_dolu | 118 / 114 | banka hesabı adı (CERTIFIED, otomatik-yoklama) | – |
| `NOTEMARGIN` | float | Senet kredi marjı (P. Note Loan Margin) | orta | ldds, eski | 0 / – | senet kredi farkı (CERTIFIED, otomatik-yoklama) | – |
| `CHECKLIMIT` | float | Çek Kredi Limiti (Check Loan Limit) | orta | ldds, eski, olcum_dolu | 7 / – | çek garantisi limiti (CERTIFIED, otomatik-yoklama) | – |
| `CUSTINTEREST` | float | Cari Hesap Faizi (Current Account Interest) | orta | ldds, eski | 0 / – | cari faiz (CERTIFIED, otomatik-yoklama) | – |
| `SKINTEREST` | float | Senet karşılığı kredi (Aylık) (Loan Against P.Note (Monthly)) | orta | ldds, eski | 0 / – | senet kredisi faizi (CERTIFIED, otomatik-yoklama) | – |
| `CKINTEREST` | float | Çek karşılığı kredi (Aylık) (Loan Against Check (Monthly)) | orta | ldds, eski | 0 / – | çek karşılığı kredi aylık (CERTIFIED, otomatik-yoklama) | – |
| `FONPER` | float | Fon Oranı (Fund Rate) | orta | ldds, eski | 0 / – | fon oranı değeri (CERTIFIED, otomatik-yoklama) | – |
| `EXTENREF` | int | Dosya Uzantısı Referansı (Extension File Reference) | orta | ldds, eski | 0 / 1 | dosya uzantısı referansı (CERTIFIED, otomatik-yoklama) | – |
| `CAPIBLOCK_CREATEDHOUR` | smallint | Oluşturulma Saati (Created Hour) | orta | ldds, eski, olcum_dolu | 118 / 14 | hesap oluşturulma saati (CERTIFIED, otomatik-yoklama) | – |
| `TEXTINC` | smallint | Ayrıntılı Açıklama İçerir (Contains Detail Description) | orta | ldds, eski | 0 / 1 | açıklama bayrağı (CERTIFIED, otomatik-yoklama) | – |
| `KKUSAGE` | smallint | Kredi Kartı Hareketleri (Credit Card Transactions) | orta | ldds, eski | 0 / 1 | kredi kartı hareketi (CERTIFIED, otomatik-yoklama) | – |
| `COLLATRLLIMIT` | float | Teminat limiti (Collateral Limit) | orta | ldds, eski, olcum_dolu | 2 / – | teminat limiti (CERTIFIED, otomatik-yoklama) | – |
| `WTHCLTRLINTEREST` | float | Teminatsız kredi faiz oranı (Unsecured Credit Interest Rate) | orta | ldds, eski | 0 / – | teminatsız faiz (CERTIFIED, otomatik-yoklama) | – |
| `WTHCLTRLLIMIT` | float | Teminatsız kredi limiti (Unsecured Credit Limit) | orta | ldds, eski, olcum_dolu | 10 / – | teminatsız kredi limiti (CERTIFIED, otomatik-yoklama) | – |

### CSCARD — Çek/Senet kartları

`LG_411_01_CSCARD` · 411: 4.238 satır · 211: 8.189 · ölçüm: tum_tablo (4.238 satır)

| Kolon | Tür | Anlam | Güven | Kaynak | 2026-09 dolu / farklı | Eski katalog | Golden |
|---|---|---|---|---|---|---|---|
| `LOGICALREF` | int | Çek / Senet Kartı Logical Ref. (Check / P. Note Card Logical Reference) | orta | ldds, eski, golden, olcum_dolu | 4.238 / 4.238 | cscardref (CANDIDATE) | A010 |
| `DOC` | smallint | 1 müşteri çeki, 2 müşteri senedi, 3 kendi çekimiz, 4 borç senedimiz. | yüksek | proje, ldds, olcum, eski, golden | 4.238 / 3 | finansal araç tipi (CERTIFIED, otomatik-yoklama); muster senet (CERTIFIED, operator) | A010 |
| `CURRSTAT` | smallint | Güncel durum (son CSTRANS.STATUS ile aynı kod): 1 portföyde, 2 ciro edildi, 4 tahsile verildi, 6 iade edildi, 7 protesto edildi, 8 tahsil edildi, 9 kendi çekimiz (ödendi/verildi), 11 karşılıksız. LDDS listesi bununla çelişir; proje kuralı veriyle doğrulandı. | yüksek | proje, olcum, eski | 4.238 / 8 | ciro edilen çek (CERTIFIED, operator); karşılıksız çek (CERTIFIED, operator) | – |
| `PORTFOYNO` | varchar(17) | Portföy numarası (Portfolio Number) | orta | ldds, eski, olcum_dolu | 4.238 / 4.079 | portföy no (CERTIFIED, rule-miner) | – |
| `DUEDATE` | datetime | Vade tarihi. | yüksek | proje, eski, olcum_dolu | 4.238 / – | vade (CANDIDATE) | – |
| `SETDATE` | datetime | Düzenleme tarihi. | yüksek | proje, olcum_dolu | 4.228 / – | – | – |
| `AMOUNT` | float | Çek/senet tutarı (çek başına bir kez sayılır). | yüksek | proje, eski, golden, olcum_dolu | 4.238 / – | tutar (CANDIDATE) | A010 |
| `DEVIR` | smallint | 1 = önceki yıldan devreden kart (2026'da 2.967 / 4.238). | orta | proje, olcum | 2.967 / 2 | – | – |
| `CANCELLED` | smallint | İptal Edilmiş (Cancelled) | orta | ldds, eski, golden | 0 / 1 | hayır (CANDIDATE, rule-miner) | A010 |

### CSROLL — Çek/Senet bordroları

`LG_411_01_CSROLL` · 411: 950 satır · 211: 6.633 · ölçüm: WHERE DATE_>='20260901' AND DATE_<'20261001' (101 satır)

| Kolon | Tür | Anlam | Güven | Kaynak | 2026-09 dolu / farklı | Eski katalog | Golden |
|---|---|---|---|---|---|---|---|
| `CARDREF` | int | Cari → CLCARD.LOGICALREF (cari bordrolarında). | yüksek | ldds, olcum | 86 / 75 | – | – |
| `CENTERREF` | int | Masraf Merkezi Ref. (Overhead Pool Reference) | orta | ldds, eski, olcum_dolu | 84 / 2 | masraf havuzu (CERTIFIED, otomatik-yoklama) | – |
| `ROLLNO` | varchar(9) | Fiş numarası (Slip Number) | orta | ldds, eski, olcum_dolu | 101 / 100 | çek fişi no (CERTIFIED, otomatik-yoklama) | – |
| `CYPHCODE` | varchar(11) | Yetki Kodu (Auth. Code) | orta | ldds, eski | 0 / 1 | yetki no (CERTIFIED, otomatik-yoklama) | – |
| `DATE_` | datetime | Tarih (Date) | orta | ldds, eski, olcum_dolu | 101 / – | kesim tarihi (CERTIFIED, otomatik-yoklama) | – |
| `TRCODE` | smallint | Bordro türü: 1 çek girişi, 2 senet girişi, 3 çek çıkışı (cariye), 4 senet çıkışı (cariye), 5 çek çıkışı (banka tahsil), 6 senet çıkışı (banka tahsil), 9 işlem bordrosu (müşteri çeki), 10 işlem bordrosu (müşteri senedi), 11 kendi çekimiz, 12 borç senedimiz. | yüksek | ldds, olcum, eski | 101 / 7 | islem bordro (CANDIDATE); senet giri (CANDIDATE) | – |
| `DESTBRANCH` | smallint | Hedef işyeri (Target Division) | orta | ldds, eski | 0 / 1 | gideceği yer (CERTIFIED, otomatik-yoklama) | – |
| `DESTDEPARTMENT` | smallint | Hedef bölüm (Target Department) | orta | ldds, eski | 0 / 1 | gideceği bölüm (CERTIFIED, otomatik-yoklama) | – |
| `CARDMD` | smallint | Kart Modül Numarası (Card Module Number) | orta | ldds, eski, olcum_dolu | 86 / 3 | kart modül (CERTIFIED, otomatik-yoklama); cari (CANDIDATE) | – |
| `PROCTYPE` | smallint | İşlem Bordrosu Türü (Group Processing Slip Voucher Type (For Only Group Processing Slips. For The Others “0”)) | orta | ldds, eski, olcum_dolu | 15 / 3 | grup bordrosu (CERTIFIED, otomatik-yoklama) | – |
| `ONEPAYLINE` | smallint | (Ortalama) Tek Satırdaki Ödeme ((Average) Payment on One Line) | orta | ldds, eski | 0 / 1 | tek satır ödeme (CERTIFIED, otomatik-yoklama) | – |
| `FROMCASH` | smallint | Kasadan (From Safe Deposit) | orta | ldds, eski | 0 / 1 | senet kasa (CERTIFIED, otomatik-yoklama) | – |
| `ACCOUNTED` | smallint | Muhasebeleştirildi (Posted to General Ledger) | orta | ldds, eski, olcum_dolu | 101 / 1 | deftere işlenme (CERTIFIED, otomatik-yoklama) | – |
| `AVERAGEAGE` | int | Ortalama Yaş (Average Age) | orta | ldds, eski, olcum_dolu | 101 / 62 | ortalama yaş (CERTIFIED, otomatik-yoklama) | – |
| `REPORTRATE` | float | RD Kuru (Reporting Currency Exchange Rate) | orta | ldds, eski | 0 / – | finansal kuru (CERTIFIED, otomatik-yoklama) | – |
| `ACCFICHEREF` | int | Genel Muhasebe Fişi Referansı (General Ledger Voucher Reference) | orta | ldds, eski, olcum_dolu | 101 / 101 | defter fişi (CERTIFIED, otomatik-yoklama) | – |
| `CASHTRANSREF` | int | Kasa hareketi ref. (Safe Deposit Transaction Reference) | orta | ldds, eski | 0 / 1 | kasa hareketi no (CERTIFIED, otomatik-yoklama) | – |
| `CAPIBLOCK_CREADEDDATE` | datetime | Oluşturulma Tarihi (Created Date) | orta | ldds, eski, olcum_dolu | 101 / – | ekleme tarihi (CERTIFIED, otomatik-yoklama) | – |
| `CAPIBLOCK_CREATEDMIN` | smallint | Oluşturulma Dakikası (Created Minute) | orta | ldds, eski, olcum_dolu | 99 / 52 | zaman dakikası (CERTIFIED, otomatik-yoklama) | – |
| `CAPIBLOCK_CREATEDSEC` | smallint | Oluşturulma Saniyesi (Created Second) | orta | ldds, eski, olcum_dolu | 98 / 51 | giriş saniyesi (CERTIFIED, otomatik-yoklama) | – |
| `CAPIBLOCK_MODIFIEDSEC` | smallint | Değiştirilme Saniyesi (Modified Second) | orta | ldds, eski, olcum_dolu | 100 / 50 | düzenleme saniyesi (CERTIFIED, otomatik-yoklama) | – |
| `CANCELLEDACC` | smallint | Muhasebeleştirme İşlemi İptal Edilmiş (Cancelled Posting) | orta | ldds, eski | 0 / 1 | kayıt iptali (CERTIFIED, otomatik-yoklama) | – |
| `OPSTAT` | smallint | Hareket durumu (Transaction Status) | orta | ldds, eski | 0 / 1 | bordro durumu (CERTIFIED, otomatik-yoklama) | – |
| `INFIDX` | float | Enflasyon Endeksi (Inflation Index) | orta | ldds, eski | 0 / – | enflasyon katsayısı (CERTIFIED, otomatik-yoklama) | – |
| `COLLATROLLREF` | int | COLLATRLROLL referansı (COLLATRLROLL Reference) | orta | ldds, eski | 0 / 1 | çek bordro numarası (CERTIFIED, otomatik-yoklama) | – |
| `GRPFIRMTRANS` | smallint | Grup şirketi işlemi (doğru/yanlış) (Group Company Transaction (True/False)) | orta | ldds, eski | 0 / 1 | grup ilişkili işlem (CERTIFIED, otomatik-yoklama) | – |
| `BNCREREF` | int | Banka kredileri (Port) referansı (Bank Credits Port Reference) | orta | ldds, eski | 0 / 1 | banka port no (CERTIFIED, otomatik-yoklama) | – |
| `FROMBANK` | smallint | Bankadan (From Bank) | orta | ldds, eski | 0 / 1 | kaynak banka (CERTIFIED, otomatik-yoklama) | – |

### CSTRANS — Çek/Senet hareketleri

`LG_411_01_CSTRANS` · 411: 9.177 satır · 211: 21.611 · ölçüm: WHERE DATE_>='20260901' AND DATE_<'20261001' (217 satır)

| Kolon | Tür | Anlam | Güven | Kaynak | 2026-09 dolu / farklı | Eski katalog | Golden |
|---|---|---|---|---|---|---|---|
| `CSREF` | int | Çek/senet kartı → CSCARD.LOGICALREF (%100). | yüksek | proje, olcum | 217 / 187 | – | – |
| `ROLLREF` | int | Bordro → CSROLL.LOGICALREF (%100). | yüksek | olcum | 217 / 101 | – | – |
| `TRCODE` | smallint | Bordro türü (CSROLL.TRCODE ile aynı kodlar); devir satırında 0. | orta | proje, olcum, eski | 217 / 7 | işlem bordrosu (kendi çekimiz) (CERTIFIED, rule-miner); işlem bordrosu (müşteri çeki) (CERTIFIED, rule-miner) | – |
| `DEVIR` | smallint | 1 = yıl başı devir satırı (olay değildir). | yüksek | proje, eski | 0 / 1 | karşılıksız çıkan çek (CERTIFIED, operator:claude (iş kararı 2026-09-20)); protesto edilen (CERTIFIED, operator:claude (iş kararı 2026-09-20)) | – |
| `STATUS` | smallint | Hareketle düşülen durum (CSCARD.CURRSTAT ile aynı kodlar). Karşılıksız olayı STATUS 11, protesto 5/7. | yüksek | proje, olcum, eski | 217 / 6 | karşılıksız çıkan çek (CERTIFIED, operator:claude (iş kararı 2026-09-20)); protesto edilen (CERTIFIED, operator:claude (iş kararı 2026-09-20)) | – |
| `CANCELLED` | smallint | İptal Edilmiş (Cancelled) | orta | ldds, eski | 0 / 1 | karşılıksız çıkan çek (CERTIFIED, operator:claude (iş kararı 2026-09-20)); protesto edilen (CERTIFIED, operator:claude (iş kararı 2026-09-20)) | – |

### PRCLIST — Fiyat listeleri (alış/satış)

`LG_411_PRCLIST` · 411: 317.349 satır · 211: 314.419 · ölçüm: tum_tablo (317.349 satır)

| Kolon | Tür | Anlam | Güven | Kaynak | 2026-09 dolu / farklı | Eski katalog | Golden |
|---|---|---|---|---|---|---|---|
| `CARDREF` | int | Malzeme → ITEMS.LOGICALREF (%100). | yüksek | proje, olcum, golden | 317.349 / 24.746 | – | A056 |
| `CLSPECODE` | varchar(11) | Fiyatın geçerli olduğu cari özel kodu (kanal/cari grubu). | orta | proje | 0 / 1 | – | – |
| `PRICE` | float | Liste fiyatı. | yüksek | proje, eski, olcum_dolu | 317.264 / – | fiyat (CANDIDATE); satis fiyati (CANDIDATE) | – |
| `UOMREF` | int | Birim → UNITSETL.LOGICALREF (%100). | yüksek | olcum | 317.349 / 9 | – | – |
| `CURRENCY` | smallint | Fiyat dövizi (160 = TL). | orta | proje, eski, olcum_dolu | 317.349 / 3 | eur (CANDIDATE, rule-miner); usd (CANDIDATE) | – |
| `PRIORITY` | smallint | Aynı anda geçerli birden çok listede öncelik. | orta | proje, olcum_dolu | 127.575 / 8 | – | – |
| `PTYPE` | smallint | Fiyat türü: 1 alış, 2 satış (317 bin satırın 317.075'i satış). | yüksek | proje, ldds, olcum, eski, golden | 317.349 / 3 | fiyat türü (CERTIFIED, otomatik-yoklama); satış fiyatı (CERTIFIED, operator) | A056 |
| `BEGDATE` | datetime | Geçerlilik başlangıcı. | yüksek | proje, olcum_dolu | 317.349 / – | – | – |
| `ENDDATE` | datetime | Geçerlilik bitişi. | yüksek | proje, olcum_dolu | 317.349 / – | – | – |
| `CAPIBLOCK_CREADEDDATE` | datetime | Oluşturulma Tarihi (Created Date) | orta | ldds, eski, olcum_dolu | 317.349 / – | fiyat degisim tarihi (CERTIFIED, rule-miner) | – |
| `ACTIVE` | smallint | 0 kullanımda, 1 kullanım dışı. | yüksek | proje, olcum, eski, golden | 1.146 / 2 | satış fiyatı (CERTIFIED, operator) | A056 |

### STINVTOT — Günlük malzeme ambar toplamları

> LG_411_01_STINVTOT tablosu boş (0 satır); stok günlük toplamı LV_411_01_STINVTOT görünümünden okunur.

`LG_411_01_STINVTOT` · 411: 0 satır · 211: 0 · ölçüm: – (– satır)

| Kolon | Tür | Anlam | Güven | Kaynak | 2026-09 dolu / farklı | Eski katalog | Golden |
|---|---|---|---|---|---|---|---|
| `RESERVED` | float | Rezerve miktarı (Reserved Quantity) | orta | ldds, eski | – | gerçek stok (CERTIFIED, rule-miner); rezv miktari (CERTIFIED, rule-miner) | – |
| `ONHAND` | float | Ambar-gün bazında eldeki miktar değişimi (LV_411_01_STINVTOT görünümü; LG_411_01_STINVTOT tablosu boş). | orta | proje, olcum, eski | – | env kesir (CERTIFIED, rule-miner); gerçek stok (CERTIFIED, rule-miner) | – |

### GNTOTST — Genel ambar toplamları

> Tablo 411 ve 211'de boş; sıfır stok anlamına gelmez.

`LG_411_01_GNTOTST` · 411: 0 satır · 211: 0 · ölçüm: – (– satır)

| Kolon | Tür | Anlam | Güven | Kaynak | 2026-09 dolu / farklı | Eski katalog | Golden |
|---|---|---|---|---|---|---|---|
| `ONHAND` | float | Genel stok toplamı; tablo 2026 ve 2021–25'te boş (0 satır). | orta | olcum, eski | – | eldeki stok (CANDIDATE) | – |

### EMFICHE — Muhasebe fişleri

`LG_411_01_EMFICHE` · 411: 114.397 satır · 211: 569.452 · ölçüm: WHERE DATE_>='20260901' AND DATE_<'20261001' (15.728 satır)

| Kolon | Tür | Anlam | Güven | Kaynak | 2026-09 dolu / farklı | Eski katalog | Golden |
|---|---|---|---|---|---|---|---|
| `TRCODE` | smallint | Muhasebe fişi türü: 1 açılış, 2 tahsil, 3 tediye, 4 mahsup, 5 özel, 6 kur farkı. | yüksek | ldds, olcum, eski | 15.728 / 3 | mahsup (CANDIDATE); ozel (CANDIDATE) | – |
| `FICHENO` | varchar(33) | Fiş Numarası (Voucher Number) | orta | ldds, eski, olcum_dolu | 15.728 / 15.728 | mahsup nr (CERTIFIED, rule-miner); fiş no (CANDIDATE) | – |
| `MODULENR` | smallint | Fişi üreten modül: 0 muhasebe (elle), 2 satınalma faturası, 3 satış faturası, 4 cari hesap, 5 çek/senet, 6 banka, 7 kasa (sayılar kaynak belgelerle örtüşür). | orta | eski, olcum | 15.716 / 7 | cari hesap fişi (CERTIFIED, rule-miner); dağıtım fişi (CERTIFIED, rule-miner) | – |

### EMFLINE — Muhasebe hareketleri

`LG_411_01_EMFLINE` · 411: 307.857 satır · 211: 1.828.007 · ölçüm: WHERE DATE_>='20260901' AND DATE_<'20261001' (36.974 satır)

| Kolon | Tür | Anlam | Güven | Kaynak | 2026-09 dolu / farklı | Eski katalog | Golden |
|---|---|---|---|---|---|---|---|
| `DATE_` | datetime | Tarih (Date) | orta | ldds, golden, olcum_dolu | 36.974 / – | – | A053, B064 |
| `SIGN` | smallint | 0 borç, 1 alacak. | yüksek | olcum, eski | 18.729 / 2 | muhasep fis satir (REJECTED) | – |
| `ACCOUNTREF` | int | Hesap → EMUHACC.LOGICALREF (%100). | yüksek | olcum, eski | 36.974 / 154 | muhasep fis satir (REJECTED) | – |
| `ACCFICHEREF` | int | Muhasebe fişi → EMFICHE.LOGICALREF (%100). | yüksek | olcum, eski, golden | 36.974 / 15.728 | muhasep fis satir (REJECTED) | B064 |
| `CENTERREF` | int | Masraf merkezi → EMCENTER.LOGICALREF. | yüksek | proje, olcum, eski, golden | 20.750 / 301 | islem gerceklestik (REJECTED) | A053 |
| `KEBIRCODE` | varchar(101) | Kebir (ana) hesap kodu, örn. 600 yurtiçi satışlar, 120 alıcılar, 320 satıcılar. | yüksek | eski, olcum | 36.974 / 42 | alim kdv (CERTIFIED, rule-miner); alıcılar hesabı bakiyesi (CERTIFIED, operator:claude (muhasebe sözlüğü, 2026-09-21)) | – |
| `ACCOUNTCODE` | varchar(101) | Hesap planı kodu (Tekdüzen); gider = 7 ile başlayan hesaplar. | yüksek | proje, eski, golden, olcum_dolu | 36.974 / 154 | etkinlik ve fuar gideri (CERTIFIED, operator:claude (tam kapı 2026-09-29, kayıt sistemi Logo)); gider (CERTIFIED, operator) | A053, B064 |
| `DEBIT` | float | Borç tutarı. | yüksek | proje, eski, golden, olcum_dolu | 18.245 / – | alıcılar hesabı bakiyesi (CERTIFIED, operator:claude (muhasebe sözlüğü, 2026-09-21)); alınan çekler hesabı bakiyesi (CERTIFIED, operator:claude (muhasebe sözlüğü, 2026-09-21)) | A053, B064 |
| `CREDIT` | float | Alacak tutarı. | yüksek | proje, eski, golden, olcum_dolu | 18.729 / – | alıcılar hesabı bakiyesi (CERTIFIED, operator:claude (muhasebe sözlüğü, 2026-09-21)); alınan çekler hesabı bakiyesi (CERTIFIED, operator:claude (muhasebe sözlüğü, 2026-09-21)) | A053, B064 |
| `CANCELLED` | smallint | İptal Edilmiş (Cancelled) | orta | ldds, eski, golden | 0 / 1 | alıcılar hesabı bakiyesi (CERTIFIED, operator:claude (muhasebe sözlüğü, 2026-09-21)); alınan çekler hesabı bakiyesi (CERTIFIED, operator:claude (muhasebe sözlüğü, 2026-09-21)) | A053, B064 |

### EMUHACC — Muhasebe hesap planı

`LG_411_EMUHACC` · 411: 1.374 satır · 211: 1.371 · ölçüm: tum_tablo (1.374 satır)

| Kolon | Tür | Anlam | Güven | Kaynak | 2026-09 dolu / farklı | Eski katalog | Golden |
|---|---|---|---|---|---|---|---|
| `CODE` | varchar(101) | Hesap kodu. | yüksek | ldds, eski, olcum_dolu | 1.374 / 1.374 | muhasebe hesap kodu (CERTIFIED, operator:claude (parti 1, 2026-09-21)); hesap kodu (CANDIDATE) | – |
| `DEFINITION_` | varchar(101) | Hesap adı. | yüksek | ldds, eski, olcum_dolu | 1.374 / 966 | muhasebe hesap adı (CERTIFIED, operator:claude (parti 1, 2026-09-21)); açıklaması (CANDIDATE) | – |
| `ACCTYPE` | smallint | Hesap türü: 0 borç, 1 alacak, 2 borç+alacak. | orta | ldds, olcum, eski | 23 / 2 | alacak (CANDIDATE) | – |

### EMCENTER — Masraf merkezleri

`LG_411_EMCENTER` · 411: 17.448 satır · 211: 16.500 · ölçüm: tum_tablo (17.448 satır)

| Kolon | Tür | Anlam | Güven | Kaynak | 2026-09 dolu / farklı | Eski katalog | Golden |
|---|---|---|---|---|---|---|---|
| `LOGICALREF` | int | Masraf Merkezi Log. Ref. (Overhead Pool Logical Reference) | orta | ldds, golden, olcum_dolu | 17.448 / 17.448 | – | A053 |
| `DEFINITION_` | varchar(101) | Genel gider açıklaması (Overhead Description) | orta | ldds, eski, golden, olcum_dolu | 17.446 / 12.523 | masraf merkezi (CERTIFIED, operator); mm aciklamasi (CANDIDATE) | A053 |

### PAYPLANS — Ödeme planları

`LG_411_PAYPLANS` · 411: 188 satır · 211: 187 · ölçüm: tum_tablo (188 satır)

| Kolon | Tür | Anlam | Güven | Kaynak | 2026-09 dolu / farklı | Eski katalog | Golden |
|---|---|---|---|---|---|---|---|
| `DEFINITION_` | varchar(201) | Ödeme planı açıklaması (Payment Plan Description) | orta | ldds, eski, olcum_dolu | 102 / – | ödeme planı (CERTIFIED, operator:claude (arşiv P100, 2026-09-21)); ödeme planı tanımı (CERTIFIED, otomatik-yoklama) | – |

### UNITSETL — Birim seti satırları (birimler)

`LG_411_UNITSETL` · 411: 34 satır · 211: 33 · ölçüm: tum_tablo (34 satır)

| Kolon | Tür | Anlam | Güven | Kaynak | 2026-09 dolu / farklı | Eski katalog | Golden |
|---|---|---|---|---|---|---|---|
| `CODE` | varchar(11) | Birim kodu (Unit Code) | orta | ldds, eski, olcum_dolu | 34 / 27 | mbd kodu (CERTIFIED, rule-miner); gaz birim kodu (CANDIDATE) | – |
| `NAME` | varchar(51) | Birim açıklaması (Unit Description) | orta | ldds, eski, olcum_dolu | 34 / 29 | birim (CERTIFIED, operator:claude (arşiv P100, 2026-09-21)); mbd adi (CERTIFIED, rule-miner) | – |
| `MAINUNIT` | smallint | 1 = setin ana birimi. | orta | ldds, olcum, eski | 13 / 2 | mbd ana birim (CERTIFIED, rule-miner) | – |
| `CONVFACT1` | float | Çevrim katsayısı payı (ana birime). | orta | ldds, olcum | 34 / – | – | – |
| `CONVFACT2` | float | Çevrim katsayısı paydası. | orta | ldds, olcum | 34 / – | – | – |

### UNITSETF — Birim setleri

`LG_411_UNITSETF` · 411: 13 satır · 211: 13 · ölçüm: tum_tablo (13 satır)

| Kolon | Tür | Anlam | Güven | Kaynak | 2026-09 dolu / farklı | Eski katalog | Golden |
|---|---|---|---|---|---|---|---|
| `CARDTYPE` | smallint | Birim seti türü: 1 uzunluk, 2 alan, 3 hacim, 4 ağırlık, 5 kullanıcı tanımlı. | yüksek | ldds, olcum, eski | 13 / 5 | agirlik olcu (CANDIDATE); hac olcu (CANDIDATE) | – |

### SPECODES — Özel kod ve yetki kodu tanımları

`LG_411_SPECODES` · 411: 9.465 satır · 211: 9.263 · ölçüm: tum_tablo (9.465 satır)

| Kolon | Tür | Anlam | Güven | Kaynak | 2026-09 dolu / farklı | Eski katalog | Golden |
|---|---|---|---|---|---|---|---|
| `CODETYPE` | smallint | 1 özel kod, 2 yetki kodu, 4 satış hedefi stok kodu, 10 (LDDS'de yok). | orta | ldds, olcum, eski | 9.465 / 5 | hedef stok kodu (CANDIDATE); satis hedef stok kodu (CANDIDATE) | – |
| `SPECODETYPE` | smallint | Özel kodun ait olduğu kayıt türü (1 stok kartı, 23 satış faturası, ...; 26 cari kart — CLCARD.SPECODE2 kanal değerleri burada, SPETYP2=1). | orta | ldds, olcum, eski | 9.448 / 27 | alinan hizmet kart (CANDIDATE); alis indir (CANDIDATE) | – |
| `SPETYP1` | smallint | Kodun 1. özel kod alanına ait olduğunu gösterir (SPETYP2..5 aynı mantık). | tahmin | olcum | 77 / 2 | – | – |

### CLRNUMS — Cari risk toplamları

`LG_411_01_CLRNUMS` · 411: 5.282 satır · 211: 237.228 · ölçüm: tum_tablo (5.282 satır)

| Kolon | Tür | Anlam | Güven | Kaynak | 2026-09 dolu / farklı | Eski katalog | Golden |
|---|---|---|---|---|---|---|---|
| `CLCARDREF` | int | Cari → CLCARD.LOGICALREF. | yüksek | proje, eski, olcum_dolu | 5.281 / 5.282 | risk referansı (CERTIFIED, otomatik-yoklama) | – |
| `RISKOVER` | smallint | Risk Kontrolü (Credit Control) | orta | ldds, eski | 0 / 1 | kredi kontrolü (CERTIFIED, otomatik-yoklama) | – |
| `PS` | float | Protestolu Senetler (Bounced P.Notes) | orta | ldds, eski, olcum_dolu | 21 / – | dönen senet (CERTIFIED, otomatik-yoklama) | – |
| `KC` | float | Karşılıksız Çekler (NSF Check) | orta | ldds, eski, olcum_dolu | 8 / – | karşılıksız çek değeri (CERTIFIED, otomatik-yoklama) | – |
| `RISKBALANCED` | float | Sevkedilen (Ayarlanan) Risk (Delivered Credit) | orta | ldds, eski | 0 / – | ayarlanan risk (CERTIFIED, otomatik-yoklama) | – |
| `CEKRISKFACTOR` | float | Çek Risk Faktörü (Check Risk Factor) | orta | ldds, eski, olcum_dolu | 3.921 / – | çek risk faktörü (CERTIFIED, otomatik-yoklama) | – |
| `SENETRISKFACTOR` | float | Senet risk faktörü (P.Note Risk Factor) | orta | ldds, eski, olcum_dolu | 3.921 / – | senet risk faktörü (CERTIFIED, otomatik-yoklama) | – |
| `CEK0_DEBIT` | float | Çek (Borç) (Check Debit) | orta | ldds, eski, olcum_dolu | 523 / – | çek meblağı (CERTIFIED, otomatik-yoklama) | – |
| `CEK0_CREDIT` | float | Çek (Alacak) (Check Credit) | orta | ldds, eski | 0 / – | cari çek alacağı (CERTIFIED, otomatik-yoklama) | – |
| `SENET0_CREDIT` | float | Senet - Alacak (P.Note Credit) | orta | ldds, eski | 0 / – | pnote alacağı (CERTIFIED, otomatik-yoklama) | – |
| `CEKCURR0_DEBIT` | float | Çek (Borç) (Check Debit) | orta | ldds, eski, olcum_dolu | 42 / – | çek bedeli (CERTIFIED, otomatik-yoklama) | – |
| `CEKCURR1_DEBIT` | float | Çek (Borç) (Check Debit) | orta | ldds, eski, olcum_dolu | 2 / – | çekli borç (CERTIFIED, otomatik-yoklama) | – |
| `SENETCURR1_CREDIT` | float | Senet - Alacak (P.Note Credit) | orta | ldds, eski | 0 / – | bono kredisi (CERTIFIED, otomatik-yoklama) | – |
| `ORDRISKOVER` | smallint | Sipariş risk aşımı (Order Risk Over) | orta | ldds, eski, olcum_dolu | 183 / 2 | limit ihlali (CERTIFIED, otomatik-yoklama) | – |
| `DESPRISKOVER` | smallint | İrsaliye risk aşımı (Receipt Risk Over) | orta | ldds, eski, olcum_dolu | 183 / 2 | teslimat riski (CERTIFIED, otomatik-yoklama) | – |
| `USEREPRISK` | smallint | Risk takibinde kullanılacak (Will be used On Credit Tracking) | orta | ldds, eski | 0 / 1 | risk takibi (CERTIFIED, otomatik-yoklama) | – |
| `REPRISKTOTAL` | float | RD risk toplamı (Reporting Currency Credit Total) | orta | ldds, eski, olcum_dolu | 153 / – | raporlama para birimi riski (CERTIFIED, otomatik-yoklama) | – |
| `REPDESPRISKTOTAL` | float | RD irsaliye risk toplamı (Reporting Currency Disp./Rec. Credit Total) | orta | ldds, eski | 0 / – | disp risk (CERTIFIED, otomatik-yoklama) | – |
| `REPRISKBALANCED` | float | RD ayarlanmış risk (Reporting Currency Delivered Credit) | orta | ldds, eski | 0 / – | ayarlanmış risk (CERTIFIED, otomatik-yoklama) | – |
| `REPPS` | float | RD protestolu senetler (Reporting Currency Bounced P.Notes) | orta | ldds, eski | 0 / – | ödenmeyen senet (CERTIFIED, otomatik-yoklama) | – |
| `REPKC` | float | RD karşılıksız çekler (Reporting Currency NSF Check) | orta | ldds, eski | 0 / – | çeki karşılıksız çıkan (CERTIFIED, otomatik-yoklama) | – |
| `ORDRISKTOTAL` | float | Sipariş risk limiti (Order Credit Limit) | orta | ldds, eski | 0 / – | sipariş kredisi (CERTIFIED, otomatik-yoklama) | – |
| `REPORDRISKTOTAL` | float | RD sipariş risk toplamı (Reporting Currency Order Credit Limit) | orta | ldds, eski | 0 / – | kredi limiti riski (CERTIFIED, otomatik-yoklama) | – |
| `REPORDRISKTOTALSUGG` | float | RD sipariş risk toplamı (öneri) (Reporting Currency Order Credit Limit (Quotation)) | orta | ldds, eski | 0 / – | risk tutarı önerisi (CERTIFIED, otomatik-yoklama) | – |
| `RISKTYPES1` | smallint | Risk tipi 1 (Risk Tipi1) | orta | ldds, eski, olcum_dolu | 948 / 2 | risk derecesi (CERTIFIED, otomatik-yoklama) | – |
| `RISKTYPES4` | smallint | Risk tipi 4 (Risk Tipi4) | orta | ldds, eski, olcum_dolu | 948 / 2 | dördüncü risk (CERTIFIED, otomatik-yoklama) | – |
| `RISKTYPES5` | smallint | Risk tipi 5 (Risk Tipi5) | orta | ldds, eski, olcum_dolu | 948 / 2 | beşinci risk (CERTIFIED, otomatik-yoklama) | – |
| `RISKTYPES6` | smallint | Risk tipi 6 (Risk Tipi6) | orta | ldds, eski, olcum_dolu | 350 / 2 | altıncı risk tipi (CERTIFIED, otomatik-yoklama) | – |
| `RISKTYPES8` | smallint | Risk tipi 8 (Risk Tipi8) | orta | ldds, eski, olcum_dolu | 350 / 2 | sekizinci risk tipi (CERTIFIED, otomatik-yoklama) | – |
| `RISKTYPES9` | smallint | Risk tipi 9 (Risk Tipi9) | orta | ldds, eski | 0 / 1 | dokuzuncu risk tipi (CERTIFIED, otomatik-yoklama) | – |
| `RISKTYPES10` | smallint | Risk tipi 10 (Risk Tipi10) | orta | ldds, eski | 0 / 1 | risk kodu (CERTIFIED, otomatik-yoklama) | – |
| `RISKTYPES14` | smallint | Risk tipi 14 (Risk Tipi14) | orta | ldds, eski | 0 / 1 | 14 numaralı risk (CERTIFIED, otomatik-yoklama) | – |
| `RISKTYPES15` | smallint | Risk tipi 15 (Risk Tipi15) | orta | ldds, eski | 0 / 1 | on beşinci risk (CERTIFIED, otomatik-yoklama) | – |
| `CSTSENETRISKFACTOR` | float | Müşteri senedi risk oranı (Customer P.Note Risk Rate) | orta | ldds, eski | 0 / – | senedi risk skoru (CERTIFIED, otomatik-yoklama) | – |
| `ACCRISKOVER` | smallint | Açık hesap risk limiti aşıldığında: 1: Evet; 0: Hayır (When Charge Accounts Risk Limit Exceeded  1: Yes  0: No) | orta | ldds, eski, olcum_dolu | 183 / 2 | limit aşımı durumu (CERTIFIED, otomatik-yoklama) | – |
| `CSTCSRISKOVER` | smallint | Müşteri çek/senet risk limiti aşıldığında: 1: Evet; 0: Hayır (When Customer Check/P.Notes Risk Limit Exceeded  1: Yes  0: No) | orta | ldds, eski, olcum_dolu | 183 / 2 | aşım durumu (CERTIFIED, otomatik-yoklama) | – |
| `MYCSRISKOVER` | smallint | Firma çek/senet risk limiti aşıldığında: 1: Evet; 0: Hayır (When Company Check/P.Notes Risk Limit Exceeded  1: Yes  0: No) | orta | ldds, eski, olcum_dolu | 183 / 2 | Çek riski aşımı (CERTIFIED, otomatik-yoklama) | – |
| `RISKCTRLTYPE` | smallint | Risk kontrolü işlemler bazında yapılacak: 1: Evet; 0: Hayır (Risk control will be done basis on transactions  1: Yes  0: No) | orta | ldds, eski | 0 / 1 | risk denetimi (CERTIFIED, otomatik-yoklama) | – |
| `ACCRISKTOTAL` | float | Güncel açık hesap riski. | yüksek | proje, eski, olcum_dolu | 3.978 / – | açık risk (CERTIFIED, otomatik-yoklama) | – |
| `REPMYCSRISKTOTAL` | float | Firma çek/senet risk toplamı (raporlama dövizi) (Company Check/P.Note Risk Total (Reporting Currency)) | orta | ldds, eski | 0 / – | firma risk bakiyesi (CERTIFIED, otomatik-yoklama) | – |
| `ACCRISKLIMIT` | float | Açık hesap risk limiti (güncel kopyada hiç >0 yok). | yüksek | proje | 0 / – | – | – |
| `CSTCSRISKLIMIT` | float | Müşteri çeki risk limiti (Customer Check Risk Limit) | orta | ldds, eski | 0 / – | çeki risk limiti (CERTIFIED, otomatik-yoklama) | – |
| `REPCSTCSRISKLIMIT` | float | Müşteri çeki risk limiti (raporlama dövizi) (Customer Check Risk Limit (Reporting Currency)) | orta | ldds, eski | 0 / – | cari çek riski (CERTIFIED, otomatik-yoklama) | – |
| `REPMYCSRISKLIMIT` | float | Firma çeki risk limiti (raporlama dövizi) (Company Check Risk Limit (Reporting Currency)) | orta | ldds, eski | 0 / – | Cari çek limiti (CERTIFIED, otomatik-yoklama) | – |
| `DESPRISKLIMIT` | float | İrsaliye risk limiti (Dispatch/Receipt Risk Limit) | orta | ldds, eski | 0 / – | sevkiyat risk limiti (CERTIFIED, otomatik-yoklama) | – |
| `REPDESPRISKLIMIT` | float | İrsaliye risk limiti (raporlama dövizi) (Dispatch/Receipt Risk Limit (Reporting Currency)) | orta | ldds, eski | 0 / – | irsaliye kredi limiti (CERTIFIED, otomatik-yoklama) | – |
| `ORDRISKLIMIT` | float | Sipariş risk limiti (sevk edilebilir) (Order Risk Limit (Deliverable)) | orta | ldds, eski | 0 / – | sevk edilebilir limit (CERTIFIED, otomatik-yoklama) | – |
| `REPORDRISKLIMIT` | float | Sipariş risk limiti (sevk edilebilir) (raporlama dövizi) (Order Risk Limit (Deliverable) (Reporting Currency)) | orta | ldds, eski | 0 / – | raporlama risk limiti (CERTIFIED, otomatik-yoklama) | – |
| `REPORDRISKLIMITSUGG` | float | Sipariş risk limiti (öneri) (raporlama dövizi) (Order Risk Limit (Proposal) (Reporting Currency)) | orta | ldds, eski | 0 / – | raporlama dövizli risk limiti (CERTIFIED, otomatik-yoklama) | – |
| `ACCRSKBLNCED` | float | Açık hesap kapanan riski (Charge Account Closed Risk) | orta | ldds, eski | 0 / – | kapalı risk bakiyesi (CERTIFIED, otomatik-yoklama) | – |
| `CSTCSRSKBLNCED` | float | Müşteri çeki / müşteri senedi kapanan riski (Customer Check / Customer P.Note Closed Risk) | orta | ldds, eski | 0 / – | senedi kapanan risk (CERTIFIED, otomatik-yoklama) | – |
| `REPCSTCSRSKBLNCED` | float | Müşteri çeki / müşteri senedi kapanan riski (raporlama dövizi) (Customer Check / Customer P.Note Closed Risk (Reporting Currency)) | orta | ldds, eski | 0 / – | müşteri senet riski (CERTIFIED, otomatik-yoklama) | – |
| `MYCSRSKBLNCED` | float | Firma çeki / firma senedi kapanan riski (Company Check / Company P.Note Closed Risk) | orta | ldds, eski | 0 / – | firma senedi riski (CERTIFIED, otomatik-yoklama) | – |
| `REPMYCSRSKBLNCED` | float | Firma çeki / firma senedi kapanan riski (raporlama dövizi) (Company Check / Company P.Note Closed Risk (Reporting Currency)) | orta | ldds, eski | 0 / – | çek senet kapama (CERTIFIED, otomatik-yoklama) | – |
| `DESPRSKBLNCED` | float | İrsaliye kapanan riski (Dispatch / Receipt Closed Risk) | orta | ldds, eski | 0 / – | irsaliye kapanan risk (CERTIFIED, otomatik-yoklama) | – |
| `REPORDRSKBLNCED` | float | Sipariş kapanan riski (sevk edilebilir) (raporlama dövizi) (Order Closed Risk (Deliverable) (Reporting Currency)) | orta | ldds, eski | 0 / – | kapanan sevk riski (CERTIFIED, otomatik-yoklama) | – |
| `ORDRSKBLNCEDSUG` | float | Sipariş kapanan riski (öneri) (Order Closed Risk (Proposal)) | orta | ldds, eski | 0 / – | kapalı risk teklifi (CERTIFIED, otomatik-yoklama) | – |
| `REPORDRSKBLNCEDSUG` | float | Sipariş kapanan riski (öneri) (raporlama dövizi) (Order Closed Risk (Proposal) (Reporting Currency)) | orta | ldds, eski | 0 / – | önerilen risk (CERTIFIED, otomatik-yoklama) | – |

### L_CAPIPERIOD — Firma dönemleri (211/411 yıl aralıkları)

`L_CAPIPERIOD` · 411: 101 satır · 211: – · ölçüm: WHERE FIRMNR IN (211,411) (2 satır)

| Kolon | Tür | Anlam | Güven | Kaynak | 2026-09 dolu / farklı | Eski katalog | Golden |
|---|---|---|---|---|---|---|---|
| `FIRMNR` | smallint | Firma (şirket-yıl kopyası) numarası: 211 = 2021–2025, 411 = 2026. | yüksek | proje, olcum | 2 / 2 | – | – |
| `BEGDATE` | datetime | Dönem başlangıcı. | yüksek | proje, olcum | 2 / – | – | – |
| `ENDDATE` | datetime | Dönem bitişi. | yüksek | proje, olcum | 2 / – | – | – |
| `PERLOCALCTYPE` | smallint | Dönemin yerel para birimi (160 = TL). | yüksek | proje, olcum | 2 / 1 | – | – |
| `PERREPCURR` | smallint | Raporlama dövizi (1 = USD). | yüksek | proje, olcum | 2 / 1 | – | – |

### L_CAPIFIRM — Firma tanımları

`L_CAPIFIRM` · 411: 101 satır · 211: – · ölçüm: WHERE NR IN (211,411) (2 satır)

| Kolon | Tür | Anlam | Güven | Kaynak | 2026-09 dolu / farklı | Eski katalog | Golden |
|---|---|---|---|---|---|---|---|
| `NR` | smallint | Firma numarası (211, 411; veritabanında 101 firma kaydı). | yüksek | proje, olcum | 2 / 2 | – | – |
| `TITLE` | varchar(51) | Firma unvanı (211 ve 411 ikisi de TİMAŞ BASIM). | yüksek | olcum | 2 / 2 | – | – |

### L_CURRENCYLIST — Döviz türleri listesi

`L_CURRENCYLIST` · 411: 26.581 satır · 211: – · ölçüm: tum_tablo (26.581 satır)

| Kolon | Tür | Anlam | Güven | Kaynak | 2026-09 dolu / farklı | Eski katalog | Golden |
|---|---|---|---|---|---|---|---|
| `CURTYPE` | smallint | Döviz türü kodu (TRCURR karşılığı): 1 USD, 13 JPY, 17 GBP, 20 EUR, 160 TL. | yüksek | proje, olcum | 26.581 / 187 | – | – |
| `CURCODE` | varchar(6) | Döviz kısa kodu. | yüksek | olcum | 26.581 / 189 | – | – |

### L_CAPIWHOUSE — Ambar (depo) tanımları

`L_CAPIWHOUSE` · 411: 6.318 satır · 211: – · ölçüm: WHERE FIRMNR IN (211,411) (288 satır)

| Kolon | Tür | Anlam | Güven | Kaynak | 2026-09 dolu / farklı | Eski katalog | Golden |
|---|---|---|---|---|---|---|---|
| `NR` | smallint | Ambar numarası (STLINE/INVOICE.SOURCEINDEX karşılığı; FIRMNR ile birlikte). | yüksek | proje, olcum, eski | 286 / 148 | bagli depo numarasi (CERTIFIED, rule-miner); islem cikis depo nr (CERTIFIED, rule-miner) | – |
| `NAME` | varchar(51) | Ambar adı (0 Merkez, 4 Timaş Satış Deposu 2, 10 B2C, 100+ matbaa ambarları). | yüksek | proje, olcum, eski | 288 / 135 | bagli depo adi (CERTIFIED, rule-miner); depo adi (CERTIFIED, rule-miner) | – |

## 3. Kod sözlüğü

Sayılar 2026-09 (411, DATE_ penceresi; kartlarda tüm tablo). Anlam önceliği: elle doğrulanmış > LDDS > TİMAŞ görünüm etiketi (eski kural madencisi) > eski katalog. JSON'da 551 kodlu kolonun tamamı, LDDS etiketi ve çelişen eski etiketlerle birlikte durur.

### BANKACC.CARDTYPE

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `1` | 53 | Ticari hesap | yüksek | ldds, olcum | LDDS: ticari hesap |
| `2` | 10 | Kredi hesabı | yüksek | ldds, olcum | LDDS: kredi hesabı |
| `3` | 24 | Dövizli ticari hesap | yüksek | ldds, olcum | LDDS: dövizli ticari |
| `4` | 0 | Dövizli kredi hesabı | yüksek | ldds | LDDS: dövizli kredi |
| `5` | 31 | LDDS'de yok (31 hesap) — POS/kredi kartı hesabı olabilir | tahmin | olcum | – |

### BNFICHE.TRCODE

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `1` | 12 | Banka işlem fişi | yüksek | ldds, eski | LDDS: Bnka işlem fişi |
| `2` | 104 | Virman fişi | yüksek | ldds, olcum | LDDS: Virman Fişi |
| `3` | 82 | Gelen havaleler | yüksek | ldds, olcum | – |
| `4` | 46 | Gönderilen havaleler | yüksek | ldds, olcum | – |
| `16` | 34 | Banka alınan hizmet faturası | orta | eski, olcum | user defined input slip (REJECTED) |

### BNFLINE.MODULENR

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `0` | 915 | Kredi kartı tahsilatından doğan banka satırı (CLFLINE 70 ile tutar/satır eşleşir; SOURCEFREF 0) | orta | olcum | – |
| `6` | 2 | Çek/senet | orta | ldds, olcum | LDDS: Çek/Senet |
| `7` | 1.452 | Banka | yüksek | ldds, olcum | – |
| `10` | 1 | Kasa | orta | ldds, olcum | – |
| `61` | 38 | Çek/senet (tahsil bordrosu) | tahmin | olcum | – |
| `62` | 38 | Çek/senet | tahmin | olcum | – |
| `65` | 38 | Çek/senet (tutar 0) | tahmin | olcum | – |

### BNFLINE.SIGN

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `0` | 1.570 | Giriş (borç) | yüksek | proje, olcum | – |
| `1` | 914 | Çıkış (alacak) | yüksek | proje, olcum | – |

### BNFLINE.TRCODE

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `1` | 947 | Banka işlem | yüksek | ldds, olcum | LDDS: banka Işlem; banka işlem fişi (CERTIFIED); mal alim (REJECTED) |
| `2` | 992 | Virman | yüksek | ldds, olcum | LDDS: virman işlemi; perakende satis iade (REJECTED) |
| `3` | 130 | Gelen havale | yüksek | ldds, olcum | LDDS: gelen hava; toptan iade (REJECTED) |
| `4` | 379 | Gönderilen havale | yüksek | ldds, olcum | LDDS: gönd.hava; alinan hizmet (REJECTED) |
| `5` | 0 | Açılış | orta | ldds | LDDS: açılış işlemi; açiliş fişi (CANDIDATE) |
| `10` | 1 | Bilinmiyor | tahmin |  | – |
| `11` | 1 | Bilinmiyor | tahmin |  | – |
| `16` | 34 | Alınan hizmet faturası | orta | eski, olcum | alinan hizmet fat (CANDIDATE) |

Çapraz dağılım (MODULENR, TRCODE, SIGN, CANCELLED), 2026-09:

| MODULENR | TRCODE | SIGN | CANCELLED | n | tutar | carili |
|---|---|---|---|---|---|---|
| 0 | 1 | 0 | 0 | 910 | 20.590.176,35 | 910 |
| 0 | 1 | 1 | 0 | 5 | 157.838,14 | 5 |
| 6 | 10 | 0 | 0 | 1 | 5.044.100,00 | 0 |
| 6 | 11 | 0 | 0 | 1 | 1.600.000,00 | 0 |
| 7 | 1 | 0 | 0 | 13 | 7.067.149,59 | 0 |
| 7 | 1 | 1 | 0 | 18 | 26.628.188,82 | 0 |
| 7 | 2 | 0 | 0 | 439 | 95.940.378,97 | 0 |
| 7 | 2 | 1 | 0 | 439 | 95.940.378,97 | 0 |
| 7 | 3 | 0 | 0 | 130 | 51.551.605,45 | 130 |
| 7 | 4 | 1 | 0 | 379 | 53.404.099,89 | 379 |
| 7 | 16 | 1 | 0 | 34 | 339.773,79 | 0 |
| 10 | 1 | 1 | 0 | 1 | 500.000,00 | 0 |
| 61 | 2 | 1 | 0 | 38 | 11.718.600,00 | 0 |
| 62 | 2 | 0 | 0 | 38 | 11.718.600,00 | 0 |
| 65 | 2 | 0 | 0 | 38 | 0,00 | 0 |

### CLCARD.ACTIVE

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `0` | 229.591 | Kullanımda | yüksek | ldds, eski, olcum | aktif müşteri (CERTIFIED); aktif (CERTIFIED) |
| `1` | 27.787 | Kullanım dışı | yüksek | ldds, eski, olcum | pasif müşteri (CERTIFIED); pasif (CERTIFIED) |

### CLCARD.CARDTYPE

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `1` | 100 | Alıcı | yüksek | ldds, olcum | – |
| `2` | 0 | Satıcı | yüksek | ldds | – |
| `3` | 257.273 | Alıcı + satıcı | yüksek | ldds, olcum | LDDS: Alıcı+Satıcı; alıcı+satıcı (CANDIDATE) |
| `4` | 4 | LDDS'de yok (4 kart) | tahmin | olcum | – |
| `22` | 1 | LDDS'de yok (1 kart) | tahmin | olcum | – |

### CLFICHE.TRCODE

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `1` | 0 | Nakit tahsilat | yüksek | ldds | – |
| `2` | 0 | Nakit ödeme | yüksek | ldds | LDDS: Borç ödeme |
| `3` | 0 | Borç dekontu | yüksek | ldds | – |
| `4` | 2 | Alacak dekontu | yüksek | ldds, olcum | alinan hizmet (REJECTED) |
| `5` | 37 | Virman fişi | yüksek | ldds, olcum | – |
| `6` | 0 | Kur farkı fişi | orta | ldds | alim iade (REJECTED) |
| `12` | 0 | Özel fiş | orta | ldds | – |
| `14` | 0 | Açılış fişi | yüksek | ldds | – |
| `41` | 0 | Verilen vade farkı faturası | orta | ldds | – |
| `42` | 0 | Alınan vade farkı faturası | orta | ldds | – |
| `46` | 21 | Alınan serbest meslek makbuzu | yüksek | ldds, olcum | – |
| `70` | 867 | Kredi kartı fişi | yüksek | ldds, olcum | – |
| `71` | 1 | Kredi kartı iade fişi | yüksek | ldds, olcum | – |
| `72` | 4 | Firma kredi kartı fişi | yüksek | ldds, olcum | – |
| `73` | 0 | Firma kredi kartı iade fişi | orta | ldds | – |

### CLFLINE.MODULENR

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `4` | 14.383 | Fatura → SOURCEFREF = INVOICE | yüksek | ldds, olcum | LDDS: Fatura; faturalar (CANDIDATE) |
| `5` | 1.210 | Cari hesap fişi → CLFICHE | yüksek | ldds, olcum | LDDS: Cari Hesap; cari hesap fişleri (CERTIFIED) |
| `6` | 84 | Çek/senet bordrosu → CSROLL (LDDS belge kodu listesi 3 der; veri 6) | yüksek | ldds, olcum | LDDS: çek/senet; çek senet (CANDIDATE); çek ve senet işlemleri (CERTIFIED) |
| `7` | 543 | Banka → BNFLINE (satır) | yüksek | ldds, olcum | LDDS: banka; banka fişi (CANDIDATE) |
| `10` | 79 | Kasa → KSLINES | yüksek | ldds, olcum | LDDS: Kasa; kasa fişi (CERTIFIED); kasa işlemleri (CANDIDATE) |
| `61` | 1 | Çek/senet (karşılıksız/iade bordrosu) — 1 satır | tahmin | olcum, eski | çek senet (CANDIDATE) |

### CLFLINE.SIGN

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `0` | 14.205 | Borç (cari borçlanır) | yüksek | ldds, eski, olcum | LDDS: Borç; borç hareketi (CERTIFIED) |
| `1` | 2.095 | Alacak (cari alacaklanır) | yüksek | ldds, eski, olcum | LDDS: Alacak; alacak hareketi (CERTIFIED) |

### CLFLINE.TRCODE

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `1` | 81 | Nakit tahsilat (MODULENR 5 cari fiş veya 10 kasa) | yüksek | ldds, olcum | LDDS: Nakit tahsilat |
| `2` | 7 | Nakit ödeme | yüksek | ldds, olcum | – |
| `3` | 1 | Borç dekontu (MODULENR 61'de çek iadesi) | orta | ldds, eski | LDDS: Borç dekontu |
| `4` | 2 | Alacak dekontu | yüksek | ldds, olcum | – |
| `5` | 263 | Virman | yüksek | ldds, olcum | LDDS: Virman Işlemi; virman fişi (CANDIDATE) |
| `6` | 0 | Kur farkı işlemi | orta | ldds | kur farkı fişi (CANDIDATE) |
| `12` | 0 | Özel işlem | orta | ldds | – |
| `14` | 0 | Açılış fişi | orta | ldds, eski | açılış işlemi (CANDIDATE) |
| `20` | 130 | Gelen havale (banka) | yüksek | ldds, olcum | LDDS: Gelen havaleler |
| `21` | 379 | Gönderilen havale (banka) | yüksek | ldds, olcum | LDDS: Gönderilen havaleler; gonderilen hava (CANDIDATE); giden havale (CERTIFIED) |
| `28` | 34 | Alınan hizmet faturası (banka modülü) | orta | eski, olcum | alınan h f (CERTIFIED) |
| `29` | 0 | Verilen hizmet faturası (banka modülü) | orta | eski | verilen h f (CERTIFIED) |
| `31` | 117 | Mal alım faturası | yüksek | ldds, olcum | LDDS: Mal alım fat; satın alma faturası (CERTIFIED); satınalma f (CERTIFIED) |
| `32` | 64 | Perakende satış iade faturası | yüksek | ldds, olcum | LDDS: Perakende satış iade fat; perakende satis iade fat (CANDIDATE) |
| `33` | 56 | Toptan satış iade faturası | yüksek | ldds, olcum | LDDS: Toptan satış iade fat; toptan satis iade fat (CANDIDATE) |
| `34` | 462 | Alınan hizmet faturası | yüksek | ldds, olcum | LDDS: Alınan hizmet fat; alınan h f (CANDIDATE) |
| `35` | 0 | Alınan proforma | orta | ldds | LDDS: Alınan proforma fat |
| `36` | 4 | Alım iade faturası | yüksek | ldds, olcum | LDDS: Alım iade fat; satın alma iade faturası (CERTIFIED); alim iade fat (CANDIDATE) |
| `37` | 8.120 | Perakende satış faturası | yüksek | ldds, olcum | LDDS: Perakende satış fat; p fatura (CERTIFIED) |
| `38` | 5.545 | Toptan satış faturası | yüksek | ldds, olcum | LDDS: Toptan satış fat; t fatura (CERTIFIED) |
| `39` | 15 | Verilen hizmet faturası | yüksek | ldds, olcum | verilen h f (CANDIDATE) |
| `41` | 0 | Verilen vade farkı faturası | orta | ldds | LDDS: Verilen vade farkı fat |
| `42` | 0 | Alınan vade farkı faturası | orta | ldds | LDDS: Alınan Vade farkı fat |
| `43` | 0 | Alınan fiyat farkı faturası | orta | ldds | LDDS: Alınan fiyat farkı fat |
| `44` | 0 | Verilen fiyat farkı faturası | orta | ldds | LDDS: Verilen fiyat farkı fat |
| `45` | 0 | Verilen serbest meslek makbuzu | orta | ldds | – |
| `46` | 21 | Alınan serbest meslek makbuzu (telif/tercüme) | yüksek | ldds, olcum | satinalma (CANDIDATE); alınan meslek makbuzu (CERTIFIED) |
| `56` | 0 | Müstahsil makbuzu | orta | ldds | LDDS: Müsthsil makbuzu |
| `61` | 55 | Çek girişi | yüksek | ldds, olcum | cek giri (CANDIDATE) |
| `62` | 4 | Senet girişi | yüksek | ldds, olcum | – |
| `63` | 25 | Çek çıkışı (cari hesaba) | yüksek | ldds, olcum | LDDS: Çek çıkış cari hesaba; çek ç (c h ) (CERTIFIED) |
| `64` | 0 | Senet çıkışı (cari hesaba) | orta | ldds | LDDS: Senet çıkış cari hesaba |
| `70` | 910 | Kredi kartı fişi (tahsilat) | yüksek | ldds, olcum | k k fişi (CERTIFIED) |
| `71` | 1 | Kredi kartı iade fişi | yüksek | ldds, olcum | – |
| `72` | 4 | Firma kredi kartı fişi (ödeme) | yüksek | ldds, olcum | f k k fişi (CERTIFIED) |
| `73` | 0 | Firma kredi kartı iade fişi | orta | ldds | – |

Çapraz dağılım (MODULENR, TRCODE, SIGN, CANCELLED), 2026-09:

| MODULENR | TRCODE | SIGN | CANCELLED | n | tutar | kaynakli |
|---|---|---|---|---|---|---|
| 4 | 31 | 1 | 0 | 117 | 16.701.790,44 | 117 |
| 4 | 32 | 1 | 0 | 64 | 33.790,63 | 64 |
| 4 | 33 | 1 | 0 | 56 | 2.301.526,05 | 56 |
| 4 | 34 | 1 | 0 | 462 | 22.447.510,88 | 462 |
| 4 | 36 | 0 | 0 | 4 | 936.752,27 | 4 |
| 4 | 37 | 0 | 0 | 8.120 | 7.699.246,08 | 8.120 |
| 4 | 38 | 0 | 0 | 5.545 | 239.812.108,27 | 5.545 |
| 4 | 39 | 0 | 0 | 15 | 387.872,39 | 15 |
| 5 | 1 | 1 | 0 | 4 | 31.223,65 | 0 |
| 5 | 2 | 0 | 0 | 5 | 21.957.701,58 | 0 |
| 5 | 4 | 1 | 0 | 2 | 29.371,33 | 2 |
| 5 | 5 | 0 | 0 | 70 | 1.966.233,25 | 70 |
| 5 | 5 | 1 | 0 | 193 | 1.966.233,25 | 193 |
| 5 | 46 | 1 | 0 | 21 | 2.603.655,39 | 21 |
| 5 | 70 | 1 | 0 | 910 | 20.590.176,35 | 910 |
| 5 | 71 | 0 | 0 | 1 | 2.145,00 | 1 |
| 5 | 72 | 0 | 0 | 4 | 155.693,14 | 4 |
| 6 | 61 | 1 | 0 | 55 | 59.559.980,50 | 55 |
| 6 | 62 | 1 | 0 | 4 | 1.350.000,00 | 4 |
| 6 | 63 | 0 | 0 | 25 | 31.387.209,36 | 25 |
| 7 | 20 | 1 | 0 | 130 | 51.551.605,45 | 130 |
| 7 | 21 | 0 | 0 | 379 | 53.404.099,89 | 379 |
| 7 | 28 | 0 | 0 | 34 | 339.773,79 | 34 |
| 10 | 1 | 1 | 0 | 77 | 331.155,50 | 77 |
| 10 | 2 | 0 | 0 | 2 | 5.744,00 | 2 |
| 61 | 3 | 0 | 0 | 1 | 100.000,00 | 1 |

### CSCARD.CURRSTAT

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `1` | 174 | Portföyde | yüksek | proje, olcum | LDDS: Müşteriden iade; müşteriye iade (REJECTED) |
| `2` | 2.736 | Ciro edildi | yüksek | proje, olcum | LDDS: Müşteri-de tahsil; portföyden tahsil (REJECTED) |
| `3` | 0 | Teminata verildi | yüksek | proje | LDDS: Müşteride protesto |
| `4` | 368 | Tahsile verildi | yüksek | proje, olcum | LDDS: Tahsil edilemiyor; portföyde karşılıksız (REJECTED) |
| `5` | 0 | Protestolu tahsile verildi | yüksek | proje | LDDS: Bankada protestolu |
| `6` | 42 | İade edildi | yüksek | proje, olcum | LDDS: Müşteriden portföye iade; iade edildi (CANDIDATE); muster portfo iade (REJECTED) |
| `7` | 83 | Protesto edildi | yüksek | proje, olcum | LDDS: Bankadan portföye iade; bank portfo iade (REJECTED) |
| `8` | 809 | Tahsil edildi | yüksek | proje, olcum | LDDS: Müşteriden protestolu iade; müşteriden karşılıksız iade (REJECTED) |
| `9` | 6 | Kendi çekimiz — ödendi/verildi (yalnız DOC 3) | tahmin | olcum | LDDS: Cirodan tahsil, A:Tahsil edilemiyor); (doc=3 ise |
| `11` | 20 | Karşılığı yok | yüksek | proje, olcum | karşiliği yok (CANDIDATE); karşılıksız çek (CERTIFIED) |
| `12` | 0 | Tahsil edilemiyor | yüksek | proje | – |

### CSCARD.DEVIR

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `0` | 1.271 | Dönem içi kart | orta | olcum | – |
| `1` | 2.967 | Önceki dönemden devir | orta | proje, olcum | – |

### CSCARD.DOC

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `1` | 3.945 | Müşteri çeki | yüksek | proje, ldds, olcum | LDDS: müşteri çeki |
| `2` | 269 | Müşteri senedi | yüksek | proje, ldds, olcum | LDDS: müşteri senedi; muster senet (CERTIFIED) |
| `3` | 24 | Kendi çekimiz | yüksek | proje, ldds, olcum | LDDS: kendi çekimiz; kent cek (CANDIDATE) |
| `4` | 0 | Borç senedimiz | yüksek | proje, ldds | LDDS: borç senedimiz |

### CSROLL.TRCODE

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `1` | 55 | Çek girişi | yüksek | ldds, olcum | – |
| `2` | 4 | Senet girişi | yüksek | ldds, olcum | – |
| `3` | 25 | Çek çıkışı (cari hesaba) | yüksek | ldds, olcum | LDDS: Çek çıkış(cari hesaba |
| `4` | 0 | Senet çıkışı (cari hesaba) | yüksek | ldds | LDDS: Senet çıkış (cari hesaba |
| `5` | 1 | Çek çıkışı (banka tahsil) | yüksek | ldds, olcum | LDDS: Çek çıkış(banka tahsil |
| `6` | 1 | Senet çıkışı (banka tahsil) | yüksek | ldds, olcum | LDDS: Senet çıkış (Banka tahsil |
| `7` | 0 | Çek çıkışı (banka teminat) | orta | ldds | LDDS: Çek çıkış (banka teminat |
| `8` | 0 | Senet çıkışı (banka teminat) | orta | ldds | LDDS: Senet çıkış (banka teminat |
| `9` | 10 | İşlem bordrosu (müşteri çeki) | yüksek | ldds, olcum | LDDS: İşlem Bordrosu (müşteri çeki |
| `10` | 5 | İşlem bordrosu (müşteri senedi) | yüksek | ldds, olcum | LDDS: İşlem bordrosu (müşteri senedi |
| `11` | 0 | İşlem bordrosu (kendi çekimiz) | orta | ldds | LDDS: İşlem bordrosu (kendi çekimiz |
| `12` | 0 | İşlem bordrosu (borç senedimiz) | orta | ldds | LDDS: İşlem bordrosu (borç senedimiz |

### CSTRANS.STATUS

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `1` | 114 | Portföyde | yüksek | proje, ldds, olcum | – |
| `2` | 44 | Ciro edildi | yüksek | proje, ldds, olcum | ciro edilt (CANDIDATE) |
| `3` | 0 | Teminata verildi | yüksek | proje, ldds | – |
| `4` | 15 | Tahsile verildi | yüksek | proje, ldds, olcum | tah verilt (CANDIDATE) |
| `5` | 0 | Protestolu tahsile verildi | yüksek | proje, ldds | protesto edilen (CERTIFIED) |
| `6` | 1 | İade edildi | yüksek | proje, ldds, olcum | iade edilt (CANDIDATE) |
| `7` | 0 | Protesto edildi | yüksek | proje | LDDS: Protesto edildi, Tahsil edildi, Kendi çekimiz; protesto edilt (CANDIDATE); protesto edilen (CERTIFIED) |
| `8` | 38 | Tahsil edildi | yüksek | proje, olcum | – |
| `9` | 5 | Kendi çekimiz (verildi) | orta | eski, olcum | – |
| `11` | 0 | Karşılığı yok (karşılıksız) | yüksek | proje, ldds | LDDS: Karşılığı yok; karşılıksız çıkan çek (CERTIFIED) |
| `12` | 0 | Tahsil edilemiyor | yüksek | proje, ldds | – |

### EMFICHE.MODULENR

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `0` | 12 | Muhasebe (elle fiş) | orta | eski, olcum | – |
| `1` | 0 | Malzeme fişi | orta | eski | – |
| `2` | 582 | Satınalma faturası | yüksek | eski, olcum | satınalma ft (CERTIFIED) |
| `3` | 13.765 | Satış faturası | yüksek | eski, olcum | satış ft (CERTIFIED) |
| `4` | 925 | Cari hesap fişi | yüksek | eski, olcum | – |
| `5` | 101 | Çek/senet bordrosu | yüksek | eski, olcum | çek senet (CANDIDATE) |
| `6` | 278 | Banka fişi | yüksek | eski, olcum | – |
| `7` | 65 | Kasa işlemi | orta | eski, olcum | – |
| `20` | 0 | Dağıtım fişi | orta | eski | – |

Çapraz dağılım (TRCODE, MODULENR, CANCELLED), 2026-09:

| TRCODE | MODULENR | CANCELLED | n |
|---|---|---|---|
| 2 | 7 | 0 | 48 |
| 3 | 7 | 0 | 2 |
| 4 | 0 | 0 | 12 |
| 4 | 2 | 0 | 582 |
| 4 | 3 | 0 | 13.765 |
| 4 | 4 | 0 | 925 |
| 4 | 5 | 0 | 101 |
| 4 | 6 | 0 | 278 |
| 4 | 7 | 0 | 15 |

### EMFICHE.TRCODE

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `1` | 0 | Açılış | yüksek | ldds | LDDS: açılış |
| `2` | 48 | Tahsil | yüksek | ldds, olcum | LDDS: tahsil |
| `3` | 2 | Tediye | yüksek | ldds, olcum | LDDS: tediye |
| `4` | 15.678 | Mahsup | yüksek | ldds, olcum | LDDS: mahsup |
| `5` | 0 | Özel | orta | ldds | LDDS: özel |
| `6` | 0 | Kur farkı | orta | ldds | LDDS: kur farkı hesabı |

### EMFLINE.SIGN

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `0` | 18.245 | Borç | yüksek | olcum | – |
| `1` | 18.729 | Alacak | yüksek | olcum | – |

### EMFLINE.TRCODE

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `1` | 0 | Açılış | orta | eski | açiliş (CANDIDATE) |
| `2` | 96 | Tahsil | yüksek | ldds, olcum | LDDS: tahsil |
| `3` | 4 | Tediye | yüksek | ldds, olcum | LDDS: tediye |
| `4` | 36.874 | Mahsup | yüksek | ldds, olcum | LDDS: mahsup; deger yayk olduk standart para cekm yatirm temel nakit islem (REJECTED) |
| `5` | 0 | Özel | orta | ldds | LDDS: özel |
| `6` | 0 | Kur farkı | orta | ldds | LDDS: kur farkı hesabı; kur farki (CANDIDATE) |

### EMUHACC.ACCTYPE

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `0` | 1.351 | Borç | orta | ldds | – |
| `1` | 0 | Alacak | orta | ldds | – |
| `2` | 23 | Borç+alacak | orta | ldds, olcum | LDDS: Borç+Alacak |

### INVOICE.GRPCODE

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `1` | 619 | Alış faturası | yüksek | ldds, olcum | LDDS: Alış Faturası; satinalma (CANDIDATE); kurumsal grup (CERTIFIED) |
| `2` | 13.800 | Satış faturası | yüksek | ldds, olcum | LDDS: Satış Faturası; satiş (CANDIDATE) |

### INVOICE.TRCODE

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `1` | 117 | Mal alım faturası | yüksek | ldds, proje, olcum | satınalma faturası (CANDIDATE) |
| `2` | 64 | Perakende satış iade faturası | yüksek | ldds, proje, olcum | perakende satis iade fatur (CANDIDATE); perakende satis iade (CERTIFIED) |
| `3` | 56 | Toptan satış iade faturası | yüksek | ldds, proje, olcum | toptan satis iade fatur (CANDIDATE); toptan satis iade (CERTIFIED) |
| `4` | 498 | Alınan hizmet faturası | yüksek | ldds, proje, olcum | alinan hizmet fatur (CANDIDATE); alım faturası (CERTIFIED) |
| `5` | 0 | Alınan proforma fatura | orta | ldds | – |
| `6` | 4 | Alım iade faturası | yüksek | ldds, proje, olcum | LDDS: alım iade faturası; satınalma iade faturası (CANDIDATE); alim iade fatur (CANDIDATE) |
| `7` | 8.120 | Perakende satış faturası | yüksek | ldds, proje, olcum | perakende satis fatur (CANDIDATE); perakende satis (CERTIFIED) |
| `8` | 5.545 | Toptan satış faturası | yüksek | ldds, proje, olcum | toptan satis (CERTIFIED) |
| `9` | 15 | Verilen hizmet faturası | yüksek | proje, eski, olcum | verilen proforma faturası (CANDIDATE) |
| `10` | 0 | Verilen proforma fatura | tahmin | eski | – |
| `13` | 0 | Satınalma fiyat farkı faturası | tahmin | eski | – |
| `14` | 0 | Satış fiyat farkı faturası | tahmin | eski | – |

### ITEMS.ACTIVE

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `0` | 32.436 | Kullanımda | yüksek | ldds, proje | LDDS: Aktif; aktif stok kartı (CERTIFIED) |
| `1` | 423 | Kullanım dışı | yüksek | ldds, proje | LDDS: Pasif |

### ITEMS.CARDTYPE

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `1` | 13.550 | Ticari mal | yüksek | ldds, olcum | LDDS: (TM) Ticari Mal |
| `2` | 0 | Karma koli | yüksek | ldds | LDDS: (KK) Karma Koli |
| `3` | 0 | Depozitolu mal | yüksek | ldds | LDDS: (DM) Depozitolu Mal |
| `4` | 16 | Sabit kıymet | yüksek | ldds, olcum | LDDS: (SK) Sabit Kıymet |
| `10` | 405 | Hammadde (kâğıt vb.) | yüksek | ldds, olcum | LDDS: (HM) Hammadde; hammat (CANDIDATE) |
| `11` | 3.068 | Yarı mamul | yüksek | ldds, olcum | LDDS: (YM) Yarı Mamul |
| `12` | 15.806 | Mamul (basılan kitap) | yüksek | ldds, olcum | LDDS: (MM) Mamul |
| `13` | 11 | Tüketim malı | yüksek | ldds, olcum | LDDS: (TK) Tüketim Malı |
| `20` | 2 | Malzeme sınıfı (genel) | yüksek | ldds, olcum | LDDS: (MS) Malzeme Sınıfı (Genel); genel malzeme sınıfı (CERTIFIED) |
| `21` | 0 | Malzeme sınıfı (tablolu) | yüksek | ldds | LDDS: (MT) Malzeme Sınıfı (Tablolu) |
| `22` | 1 | LDDS'de yok (1 kart) | tahmin | olcum | genel malzeme sınıfı (CANDIDATE) |

### KSLINES.SIGN

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `0` | 91 | Giriş / tahsil | yüksek | proje, olcum | – |
| `1` | 17 | Çıkış / ödeme | yüksek | proje, olcum | – |

### KSLINES.TRCODE

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `11` | 77 | Cari hesap tahsilatı | yüksek | ldds, olcum | LDDS: Cari hesap Tahsilat |
| `12` | 2 | Cari hesap ödemesi | yüksek | ldds, olcum | LDDS: Cari hesap, |
| `21` | 0 | Bankaya yatırılan | tahmin | ldds | LDDS: 22: Banka |
| `22` | 1 | Bankadan çekilen | tahmin | ldds, olcum | user defined output slip (REJECTED) |
| `34` | 2 | Fatura (alınan hizmet) ödemesi | tahmin | ldds, olcum | – |
| `73` | 13 | Kasa virman (giriş) | tahmin | ldds, olcum | – |
| `74` | 13 | Kasa virman (çıkış) | tahmin | ldds, olcum | – |

### ORFICHE.STATUS

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `1` | 0 | Öneri | orta | ldds | – |
| `2` | 79 | Sevkedilemez | orta | ldds, olcum | sevkedilebilir (CANDIDATE) |
| `4` | 8.070 | Sevkedilebilir | orta | ldds, olcum | sevkedilemez (CANDIDATE) |

### ORFICHE.TRCODE

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `1` | 8.149 | Alınan (satış) sipariş | yüksek | ldds, proje, olcum | LDDS: Alınan siparişler; satiş siparişi (CANDIDATE); alınan sipariş (CERTIFIED) |
| `2` | 0 | Verilen (satınalma) sipariş | orta | ldds | LDDS: Verilen siparişler |

### ORFLINE.CLOSED

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `0` | 31.455 | Açık | yüksek | proje | bekleyen sipariş (CERTIFIED) |
| `1` | 0 | Kapandı | yüksek | proje | – |

### ORFLINE.LINETYPE

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `0` | 29.977 | Malzeme (stok) satırı | yüksek | ldds, eski, olcum | LDDS: Malzeme satırı; stok satırı (CERTIFIED) |
| `2` | 696 | İskonto satırı | orta | ldds, olcum | LDDS: İndirim; indir (CANDIDATE) |
| `4` | 782 | Hizmet satırı | orta | ldds, olcum | LDDS: Hizmet |

### ORFLINE.STATUS

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `1` | 0 | Öneri | orta | ldds | – |
| `2` | 300 | Sevkedilemez | orta | ldds, olcum | – |
| `4` | 31.155 | Sevkedilebilir | orta | ldds, olcum | – |

### PAYTRANS.MODULENR

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `4` | 10.994 | Fatura (FICHEREF→INVOICE) | yüksek | ldds, olcum | LDDS: fatura; satin alma (CANDIDATE); mal alım faturası (CANDIDATE) |
| `5` | 1.274 | Cari hesap (FICHEREF→CLFLINE) | yüksek | ldds, olcum | LDDS: cari hesap; muhasebe (CANDIDATE); devir (CANDIDATE) |
| `6` | 205 | Çek/senet (FICHEREF→CSROLL) | orta | ldds, olcum | LDDS: çek/senet; müşteri çeki (CANDIDATE); müşteri senedi (CANDIDATE) |
| `7` | 543 | Banka (FICHEREF→BNFLINE) | yüksek | ldds, olcum | LDDS: banka; gelen havale (CANDIDATE) |
| `10` | 79 | Kasa (FICHEREF→KSLINES) | yüksek | ldds, olcum | LDDS: Kasa; nakit tahsilat (CANDIDATE); virman fişi (CANDIDATE) |
| `61` | 1 | Çek/senet cari hareketi | tahmin | ldds | iade edilen çekler (CERTIFIED); çek alacak dekontu (CERTIFIED) |

### PAYTRANS.PAYMENTTYPE

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `0` | 11.867 | İşlem yapılmayacak | orta | ldds, olcum | – |
| `1` | 88 | Nakit | orta | ldds | – |
| `2` | 195 | Çek | orta | ldds | – |
| `3` | 10 | Senet | orta | ldds | – |
| `4` | 936 | Kredi kartı | orta | ldds, olcum | – |
| `5` | 0 | Mağaza kartı | orta | ldds | – |

### PAYTRANS.SIGN

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `0` | 10.565 | Borç (müşteri satış faturası, alım iadesi, ödeme) | yüksek | olcum | – |
| `1` | 2.531 | Alacak (alış faturası, satış iadesi, tahsilat) | yüksek | olcum | – |

### PRCLIST.PTYPE

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `1` | 273 | Alış fiyatı | yüksek | ldds, proje, olcum | LDDS: Satınalam fiyatı |
| `2` | 317.075 | Satış fiyatı | yüksek | ldds, proje, olcum | – |
| `4` | 1 | LDDS'de yok (1 satır) | tahmin | olcum | – |

### STFICHE.GRPCODE

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `1` | 155 | Satınalma | orta | eski, olcum | satın alma (CANDIDATE) |
| `2` | 16.884 | Satış | orta | eski, olcum | satis (CANDIDATE) |
| `3` | 1.948 | Malzeme yönetimi (fire/sarf/üretim/ambar/sayım) | orta | eski, olcum | LDDS: Malzeme Yönetimi |

### STFICHE.IOCODE

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `1` | 972 | Giriş | yüksek | ldds, olcum | LDDS: Girdi |
| `2` | 540 | Ambar (transfer) | yüksek | ldds, olcum | LDDS: Ambar |
| `3` | 17.475 | Çıkış | yüksek | ldds, olcum | LDDS: Çıktı |

### STFICHE.TRCODE

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `1` | 152 | Mal alım irsaliyesi | yüksek | ldds, olcum | satınalma irsaliyesi (CERTIFIED) |
| `2` | 68 | Perakende satış iade irsaliyesi | yüksek | ldds, olcum | LDDS: Per. sat. iade irs; per sat iade irs (CERTIFIED); perakande satış iade irsaliyesi (CERTIFIED) |
| `3` | 74 | Toptan satış iade irsaliyesi | yüksek | ldds, olcum | LDDS: Topt.sat. iade irs; toptan sat iade irs (CERTIFIED) |
| `4` | 0 | Konsinye çıkış iade irsaliyesi | orta | ldds | LDDS: Kons. çıkış iade irs |
| `5` | 0 | Konsinye giriş irsaliyesi | orta | ldds | LDDS: Konsinye giriş irs |
| `6` | 3 | Alım iade irsaliyesi | yüksek | ldds, olcum | LDDS: Alım iade irs; satınalma iade irsaliyesi (CERTIFIED) |
| `7` | 10.432 | Perakende satış irsaliyesi | yüksek | ldds, olcum | LDDS: Perakende satış irs; perakande satış irsaliyesi (CERTIFIED) |
| `8` | 6.310 | Toptan satış irsaliyesi | yüksek | ldds, olcum | LDDS: Toptan satış irs; toptan sat irs (CERTIFIED) |
| `9` | 0 | Konsinye çıkış irsaliyesi | orta | ldds | LDDS: Konsinye çıkış irs |
| `10` | 0 | Konsinye giriş iade irsaliyesi | orta | ldds | LDDS: Konsinye giriş iade irs |
| `11` | 107 | Fire fişi | yüksek | ldds, olcum | – |
| `12` | 622 | Sarf fişi | yüksek | ldds, olcum | – |
| `13` | 675 | Üretimden giriş fişi | yüksek | ldds, olcum | LDDS: üretimden giriş fişi |
| `14` | 0 | Devir fişi | yüksek | ldds | – |
| `25` | 540 | Ambar fişi | yüksek | ldds, olcum | – |
| `50` | 3 | Sayım fazlası | yüksek | eski, olcum | sayım fazlası fişi (CERTIFIED); sayım fazlası(+) (CANDIDATE) |
| `51` | 1 | Sayım eksiği | yüksek | eski, olcum | sayım eksiği fişi (CERTIFIED); sayım eksiği( ) (CERTIFIED) |

### STLINE.BILLED

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `0` | 37.752 | Faturalanmamış | yüksek | proje, olcum | faturalanmamış sevkiyat (CERTIFIED) |
| `1` | 284.815 | Faturalanmış | yüksek | proje, olcum | – |

### STLINE.IOCODE

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `0` | 1.669 | Stok etkisiz satır (hizmet / irsaliyesiz iskonto) | orta | olcum | – |
| `1` | 3.782 | Giriş (alış, satış iadesi, üretimden giriş, sayım fazlası) | yüksek | ldds, proje, olcum | LDDS: Girdi |
| `2` | 7.476 | Ambar girişi (transferin alan ambarı) | yüksek | ldds, proje, olcum | LDDS: Ambardan giriş |
| `3` | 7.476 | Ambar çıkışı (transferin veren ambarı) | yüksek | ldds, proje, olcum | LDDS: Ambardan çıkış |
| `4` | 302.164 | Çıkış (satış, sarf, fire, alım iadesi, sayım eksiği) | yüksek | ldds, proje, olcum | LDDS: Çıktı8 |

### STLINE.LINETYPE

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `0` | 187.104 | Malzeme satırı | yüksek | ldds, proje, olcum | LDDS: Malzeme; maliyetli (REJECTED) |
| `1` | 0 | Promosyon | orta | ldds | – |
| `2` | 133.158 | İskonto (indirim) satırı; TOTAL iskonto tutarı, LINENET 0 | yüksek | ldds, proje, olcum | LDDS: İndirim; iskonto satir (CERTIFIED) |
| `3` | 171 | Masraf satırı | orta | ldds, eski | LDDS: Masraf; promotion (REJECTED) |
| `4` | 2.126 | Hizmet satırı | yüksek | ldds, eski, olcum | LDDS: Hizmet |
| `5` | 0 | Depozito | orta | ldds | LDDS: Depozit |
| `6` | 0 | Karma koli | orta | ldds | – |
| `7` | 0 | Karma koli satırı | orta | ldds | – |
| `8` | 8 | Sabit kıymet satırı | yüksek | ldds, eski, olcum | LDDS: Sabit kıymet; fixed asset (REJECTED) |
| `9` | 0 | Ek malzeme | orta | ldds | LDDS: Ek Malzeme |
| `10` | 0 | Malzeme sınıfı | orta | ldds | – |
| `11` | 0 | Fason | orta | ldds | LDDS: Fason1 |

### STLINE.TRCODE

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `1` | 800 | Mal alım irsaliyesi/faturası satırı | yüksek | ldds, proje, olcum | satınalma faturası (CANDIDATE); alınan vade farkı faturası (CANDIDATE) |
| `2` | 196 | Perakende satış iadesi | yüksek | ldds, proje, olcum | perakende satış iade faturası (CANDIDATE) |
| `3` | 1.582 | Toptan satış iadesi | yüksek | ldds, proje, olcum | toptan satış iade faturası (CANDIDATE) |
| `4` | 1.576 | Alınan hizmet faturası satırı (stok fişinde 4 = konsinye çıkış iade; 2026-09'da yalnız fatura satırı, LINETYPE 4) | yüksek | ldds, olcum | – |
| `5` | 0 | Konsinye giriş irsaliyesi (fatura bağlamında alınan proforma) | orta | ldds | alınan proforma faturası (CANDIDATE) |
| `6` | 49 | Alım iadesi | yüksek | ldds, proje, olcum | satınalma iade faturası (CANDIDATE) |
| `7` | 42.539 | Perakende satış (2026-09: çoğu B2C internet, ambar 10) | yüksek | ldds, proje, olcum | perakende satış faturası (CANDIDATE) |
| `8` | 257.687 | Toptan satış | yüksek | ldds, proje, olcum | toptan satis faturalari (CERTIFIED); irsaliye (CERTIFIED) |
| `9` | 26 | Verilen hizmet faturası satırı (stok fişinde 9 = konsinye çıkış). 2026-09'da 26 satırın hepsi LINETYPE 4 hizmet — LINETYPE=0 süzgeçli satış ölçülerine hiç girmez. | yüksek | ldds, olcum | verilen proforma faturası (CANDIDATE) |
| `10` | 0 | Konsinye giriş iade irsaliyesi | orta | ldds | – |
| `11` | 107 | Fire fişi | yüksek | ldds, olcum | – |
| `12` | 1.827 | Sarf fişi (baskıda çekilen malzeme) | yüksek | ldds, proje, olcum | – |
| `13` | 1.215 | Üretimden giriş fişi (basılan adet) | yüksek | ldds, proje, olcum | satınalma fiyat farkı faturası (CANDIDATE) |
| `14` | 0 | Devir fişi (açılış) | yüksek | ldds, proje | fiyat farkı (CERTIFIED); satış fiyat farkı faturası (CANDIDATE) |
| `25` | 14.952 | Ambar (transfer) fişi — her transfer bir IOCODE 2 + bir IOCODE 3 satırı | yüksek | ldds, olcum | – |
| `50` | 9 | Sayım fazlası fişi | yüksek | eski, olcum | – |
| `51` | 2 | Sayım eksiği fişi | yüksek | eski, olcum | – |

Çapraz dağılım (TRCODE, IOCODE, LINETYPE), 2026-09:

| TRCODE | IOCODE | LINETYPE | n | aktif | faturali | irsaliyeli | miktar | total | linenet | kdv | outcost_dolu |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 0 | 2 | 1 | 1 | 1 | 0 | 0,00 | 0,01 | 0,00 | 0,00 | 0 |
| 1 | 0 | 4 | 11 | 11 | 11 | 0 | 3.042,00 | 279.804,83 | 279.804,83 | 42.008,53 | 0 |
| 1 | 1 | 0 | 705 | 705 | 608 | 705 | 1.759.881,25 | 13.898.655,23 | 13.866.657,09 | 1.501.195,90 | 0 |
| 1 | 1 | 2 | 75 | 75 | 50 | 75 | 0,00 | 31.998,13 | 0,00 | 0,00 | 0 |
| 1 | 1 | 8 | 8 | 8 | 8 | 8 | 20,00 | 8.200.699,74 | 8.200.699,74 | 89.011,24 | 0 |
| 2 | 0 | 2 | 3 | 3 | 3 | 0 | 0,00 | 3.930,75 | 0,00 | 0,00 | 0 |
| 2 | 1 | 0 | 171 | 171 | 169 | 171 | 177,00 | 39.264,88 | 33.753,57 | 104,06 | 11 |
| 2 | 1 | 2 | 19 | 19 | 14 | 17 | 0,00 | 4.333,45 | 0,00 | 0,00 | 0 |
| 2 | 4 | 4 | 3 | 3 | 3 | 0 | 3,00 | 360,00 | 300,00 | 60,00 | 0 |
| 3 | 0 | 4 | 1 | 1 | 1 | 0 | 1,00 | 1.278.470,99 | 1.278.470,99 | 0,00 | 0 |
| 3 | 1 | 0 | 1.356 | 1.356 | 1.270 | 1.356 | 10.149,00 | 1.980.304,02 | 1.328.904,19 | 406,12 | 12 |
| 3 | 1 | 2 | 224 | 224 | 149 | 224 | 0,00 | 651.399,83 | 0,00 | 0,00 | 0 |
| 3 | 4 | 2 | 1 | 1 | 1 | 0 | 0,00 | 3.870,00 | 0,00 | 0,00 | 0 |
| 4 | 0 | 2 | 280 | 280 | 280 | 0 | 0,00 | 1.006.755,25 | 1.001.133,72 | 0,00 | 0 |
| 4 | 0 | 4 | 1.296 | 1.296 | 1.296 | 0 | 1.557.483,00 | 20.152.698,07 | 20.139.033,66 | 3.652.091,13 | 0 |
| 6 | 0 | 2 | 1 | 1 | 1 | 0 | 0,00 | 740,67 | 0,00 | 0,00 | 0 |
| 6 | 0 | 4 | 1 | 1 | 1 | 0 | 1,00 | 381.818,18 | 381.818,18 | 38.181,82 | 0 |
| 6 | 4 | 0 | 46 | 46 | 46 | 46 | 11.202,75 | 471.460,77 | 470.720,10 | 46.032,17 | 0 |
| 6 | 4 | 2 | 1 | 1 | 0 | 1 | 0,00 | 740,67 | 0,00 | 0,00 | 0 |
| 7 | 0 | 2 | 37 | 37 | 37 | 0 | 0,00 | 145.954,61 | 0,00 | 0,00 | 0 |
| 7 | 4 | 0 | 36.082 | 36.082 | 34.733 | 36.082 | 43.386,00 | 8.923.212,93 | 7.982.791,10 | 76.466,76 | 312 |
| 7 | 4 | 2 | 5.473 | 5.473 | 3.964 | 5.231 | 0,00 | 730.196,32 | 0,00 | 0,00 | 0 |
| 7 | 4 | 3 | 171 | 171 | 75 | 96 | 0,00 | 84,02 | 0,00 | 0,00 | 0 |
| 7 | 4 | 4 | 776 | 776 | 776 | 0 | 776,00 | 93.120,00 | 77.500,00 | 15.500,00 | 0 |
| 8 | 0 | 4 | 12 | 12 | 12 | 0 | 12,00 | 595.252,58 | 595.252,58 | 3.388,60 | 0 |
| 8 | 4 | 0 | 130.632 | 130.632 | 121.386 | 130.632 | 1.955.564,00 | 444.103.425,38 | 239.462.523,28 | 67.355,64 | 1.048 |
| 8 | 4 | 2 | 127.043 | 127.043 | 120.065 | 127.043 | 0,00 | 204.642.927,10 | 2.025,00 | 0,00 | 0 |
| 9 | 0 | 4 | 26 | 26 | 26 | 0 | 26,00 | 372.867,75 | 324.527,83 | 63.344,56 | 0 |
| 11 | 4 | 0 | 107 | 107 | 0 | 107 | 7.541,00 | 0,00 | 0,00 | 0,00 | 14 |
| 12 | 4 | 0 | 1.827 | 1.827 | 0 | 1.827 | 2.327.520,47 | 0,00 | 0,00 | 0,00 | 61 |
| 13 | 1 | 0 | 1.215 | 1.215 | 0 | 1.215 | 2.654.462,00 | 14.059,92 | 14.059,92 | 0,00 | 0 |
| 25 | 2 | 0 | 7.476 | 7.476 | 0 | 7.476 | 309.813,64 | 95.085,00 | 95.085,00 | 0,00 | 0 |
| 25 | 3 | 0 | 7.476 | 7.476 | 0 | 7.476 | 309.813,64 | 95.085,00 | 95.085,00 | 0,00 | 0 |
| 50 | 1 | 0 | 9 | 9 | 0 | 9 | 245,00 | 342,00 | 342,00 | 0,00 | 0 |
| 51 | 4 | 0 | 2 | 2 | 0 | 2 | 14,00 | 0,00 | 0,00 | 0,00 | 0 |

### UNITSETF.CARDTYPE

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `1` | 1 | Uzunluk | yüksek | ldds, olcum | LDDS: Uzunluk ölçüleri |
| `2` | 1 | Alan | yüksek | ldds, olcum | LDDS: Alan ölçüleri |
| `3` | 1 | Hacim | yüksek | ldds, olcum | LDDS: Hacim ölçüleri |
| `4` | 1 | Ağırlık | yüksek | ldds, olcum | LDDS: Ağırlık ölçüleri |
| `5` | 9 | Kullanıcı tanımlı | yüksek | ldds, olcum | LDDS: Kullanıcı tanımlı ölçüler |

### STLINE.CANCELLED

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `0` | 322.567 | Geçerli (iptal değil) | yüksek | proje, ldds | LDDS: Hayır; stline default cancelled (CERTIFIED) |
| `1` | 0 | İptal | yüksek | proje, ldds | LDDS: Evet; iptal (CERTIFIED) |

### INVOICE.CANCELLED

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `0` | 14.419 | Geçerli (iptal değil) | yüksek | proje, ldds | trcode (CERTIFIED); invoice default cancelled (CERTIFIED) |
| `1` | 0 | İptal | yüksek | proje, ldds | iptal (CERTIFIED) |

### STLINE.TRCURR

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `0` | 322.497 | Yerel para (TL) | yüksek | ldds, olcum | – |
| `1` | 36 | USD | yüksek | olcum | – |
| `13` | 0 | JPY | yüksek | olcum | – |
| `17` | 3 | GBP | yüksek | olcum | – |
| `20` | 31 | EUR | yüksek | olcum | – |
| `160` | 0 | TL (açık kodla) | yüksek | olcum | – |

### STLINE.SOURCEINDEX

> Ambar adı L_CAPIWHOUSE (FIRMNR=411, NR=SOURCEINDEX); 2026-09 satırlarının %100'ü eşleşti. 100–144 matbaa ambarları, 200+ konsinye depolar, 312 Kocaeli Fuar, 333 İmza ve Etkinlik deposu.

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `4` | 268.476 | Timaş Satış Deposu 2 | yüksek | olcum | – |
| `10` | 31.592 | B2C (İnternet Satışları) Deposu | yüksek | olcum | – |
| `3` | 5.676 | Timaş Perakende Satış Deposu | yüksek | olcum | – |
| `0` | 5.657 | Merkez | yüksek | olcum | – |
| `312` | 2.770 | Kocaeli Fuar Deposu | yüksek | olcum | – |
| `2` | 2.556 | Bab-ı Ali Satış Deposu | yüksek | olcum | – |
| `15` | 2.086 | Koltukaltı Depo | yüksek | olcum | – |
| `24` | 808 | Tarçın Kafe | yüksek | olcum | – |
| `333` | 745 | İmza ve Etkinlik Deposu | yüksek | olcum | – |
| `135` | 658 | Adin Matbaa | yüksek | olcum | – |
| `100` | 423 | Çınar Matbaa | yüksek | olcum | – |
| `303` | 296 | Tüyap Diyarbakır Fuar Deposu | yüksek | olcum | – |
| `139` | 131 | Deha Matbaa | yüksek | olcum | – |
| `121` | 112 | Pelikan Matbaa | yüksek | olcum | – |
| `5` | 99 | Arızalı Mamül Deposu | yüksek | olcum | – |
| `114` | 89 | WPC Matbaa | yüksek | olcum | – |
| `1` | 84 | Timaş Satış Deposu 1 | yüksek | olcum | – |
| `102` | 68 | Sistem Matbaa | yüksek | olcum | – |
| `101` | 56 | Seçil Matbaa | yüksek | olcum | – |
| `104` | 33 | Mega Matbaa | yüksek | olcum | – |
| `142` | 26 | Çalış Matbaa | yüksek | olcum | – |
| `126` | 25 | İmak Matbaa | yüksek | olcum | – |
| `17` | 25 | Üretim Ambarı | yüksek | olcum | – |
| `143` | 23 | Akaş Matbaa | yüksek | olcum | – |
| `134` | 22 | Yıldız Matbaa | yüksek | olcum | – |
| `26` | 14 | Şube Transfer Deposu | yüksek | olcum | – |
| `144` | 6 | Tdv Matbaa | yüksek | olcum | – |
| `141` | 4 | Epsilon Matbaa | yüksek | olcum | – |
| `20` | 4 | POD Ambarı (Print On Demant) | yüksek | olcum | – |
| `130` | 2 | Uzunist Dijital Matbaa | yüksek | olcum | – |
| `66` | 1 | Başakşehir Ankara Geçici | yüksek | olcum | – |

### CLCARD.SPECODE2

> Tanım SPECODES'ta CODETYPE=1, SPECODETYPE=26, SPETYP2=1 (cari kart 2. özel kod). Yazım varyantları var: BAYI/BAYİ, YURTDIŞI/YURTDISI, ZINCIR/ZİNCİR MAĞ.

| Değer | Kart | 2026-09 satış LINENET (₺) | Anlam |
|---|---:|---:|---|
| `` | 221.110 | 6.235.985,87 | Grup kodu boş |
| `E-TICARET` | 21.402 | 51.661.259,25 | Satış kanalı (kod değerinin kendisi) |
| `DIGER` | 7.243 | 574.781,41 | Satış kanalı (kod değerinin kendisi) |
| `KITAPCI` | 4.238 | 125.361.764,51 | Satış kanalı (kod değerinin kendisi) |
| `TUKETICI` | 1.054 | – | Satış kanalı (kod değerinin kendisi) |
| `YURTDIŞI` | 720 | – | Satış kanalı (kod değerinin kendisi) |
| `KURUM` | 406 | 322.359,00 | Satış kanalı (kod değerinin kendisi) |
| `YAZAR` | 372 | 422.954,00 | Satış kanalı (kod değerinin kendisi) |
| `BAYI` | 138 | – | Satış kanalı (kod değerinin kendisi) |
| `DAGITICI` | 136 | 35.916.085,23 | Satış kanalı (kod değerinin kendisi) |
| `ZINCIR` | 107 | 22.647.713,26 | Satış kanalı (kod değerinin kendisi) |
| `ABONE` | 96 | – | Satış kanalı (kod değerinin kendisi) |
| `MARKET` | 94 | – | Satış kanalı (kod değerinin kendisi) |
| `FUAR` | 84 | 1.617.299,75 | Satış kanalı (kod değerinin kendisi) |
| `EDİTÖRYAL ` | 42 | – | Satış kanalı (kod değerinin kendisi) |
| `HAVUZ` | 41 | 537.377,75 | Satış kanalı (kod değerinin kendisi) |
| `MERKEZ` | 23 | – | Satış kanalı (kod değerinin kendisi) |
| `BAYİ` | 18 | – | Satış kanalı (kod değerinin kendisi) |
| `INTERNET` | 14 | – | Satış kanalı (kod değerinin kendisi) |
| `PERSONEL` | 8 | 7.420,47 | Satış kanalı (kod değerinin kendisi) |
| `OKUL` | 6 | – | Satış kanalı (kod değerinin kendisi) |
| `ZİNCİR MAĞ` | 4 | 162.304,75 | Satış kanalı (kod değerinin kendisi) |
| `MAGAZA` | 4 | 1.220.751,35 | Satış kanalı (kod değerinin kendisi) |
| `NİHAİ` | 3 | – | Satış kanalı (kod değerinin kendisi) |
| `ORTAKCARI` | 3 | – | Satış kanalı (kod değerinin kendisi) |
| `HİPİCON` | 2 | – | Satış kanalı (kod değerinin kendisi) |
| `FIRSAT` | 2 | – | Satış kanalı (kod değerinin kendisi) |
| `PERAKENDE` | 2 | – | Satış kanalı (kod değerinin kendisi) |
| `YURTDISI` | 2 | – | Satış kanalı (kod değerinin kendisi) |
| `test` | 2 | – | Satış kanalı (kod değerinin kendisi) |
| `TİMAŞ OKUL` | 1 | – | Satış kanalı (kod değerinin kendisi) |
| `kı` | 1 | – | Satış kanalı (kod değerinin kendisi) |

### PAYTRANS.TRCODE

> PAYTRANS.TRCODE bağlamını MODULENR belirler: 4'te fatura türü (INVOICE.TRCODE 1..9), 5'te cari fiş türü (CLFICHE.TRCODE), 6'da bordro türü (CSROLL.TRCODE), 7'de banka fişi türü (BNFICHE: 3 gelen havale, 4 gönderilen havale, 16 hizmet faturası), 10'da 1 tahsil / 2 ödeme. Tek başına okunmaz.

| Değer | 2026-09 sayı | Anlam | Güven | Kaynak | Çelişen/ek etiket |
|---|---:|---|---|---|---|
| `1` | 354 | Bilinmiyor | tahmin |  | – |
| `2` | 91 | Bilinmiyor | tahmin |  | – |
| `3` | 402 | Bilinmiyor | tahmin |  | – |
| `4` | 936 | Bilinmiyor | tahmin |  | – |
| `5` | 308 | Bilinmiyor | tahmin |  | – |
| `6` | 4 | Bilinmiyor | tahmin |  | – |
| `7` | 7.813 | Bilinmiyor | tahmin |  | – |
| `8` | 2.184 | Bilinmiyor | tahmin |  | – |
| `9` | 15 | Bilinmiyor | tahmin |  | – |
| `14` | 1 | Bilinmiyor | tahmin |  | – |
| `16` | 34 | Bilinmiyor | tahmin |  | – |
| `46` | 18 | Bilinmiyor | tahmin |  | – |
| `70` | 931 | Bilinmiyor | tahmin |  | – |
| `71` | 1 | Bilinmiyor | tahmin |  | – |
| `72` | 4 | Bilinmiyor | tahmin |  | – |

Çapraz dağılım (MODULENR, TRCODE, SIGN, CANCELLED), 2026-09:

| MODULENR | TRCODE | SIGN | CANCELLED | n | total | paid | kapamali |
|---|---|---|---|---|---|---|---|
| 4 | 1 | 1 | 0 | 126 | 13.045.662,75 | 0,00 | 0 |
| 4 | 2 | 1 | 0 | 74 | 39.249,37 | 0,00 | 0 |
| 4 | 3 | 1 | 0 | 223 | 12.461.262,65 | 0,00 | 0 |
| 4 | 4 | 1 | 0 | 555 | 26.573.086,12 | 0,00 | 0 |
| 4 | 6 | 0 | 0 | 4 | 927.347,47 | 0,00 | 0 |
| 4 | 7 | 0 | 0 | 7.813 | 7.603.643,12 | 0,00 | 0 |
| 4 | 8 | 0 | 0 | 2.184 | 101.750.097,25 | 0,00 | 0 |
| 4 | 9 | 0 | 0 | 15 | 20.544,43 | 0,00 | 0 |
| 5 | 1 | 1 | 0 | 4 | 31.223,65 | 0,00 | 0 |
| 5 | 2 | 0 | 0 | 5 | 21.957.701,58 | 0,00 | 0 |
| 5 | 4 | 1 | 0 | 2 | 29.371,33 | 0,00 | 0 |
| 5 | 5 | 0 | 0 | 75 | 7.663.717,54 | 0,00 | 0 |
| 5 | 5 | 1 | 0 | 233 | 6.494.856,05 | 0,00 | 0 |
| 5 | 14 | 1 | 0 | 1 | 3.735,00 | 0,00 | 0 |
| 5 | 46 | 1 | 0 | 18 | 2.239.870,39 | 0,00 | 0 |
| 5 | 70 | 1 | 0 | 931 | 21.255.712,64 | 0,00 | 0 |
| 5 | 71 | 0 | 0 | 1 | 2.145,00 | 0,00 | 0 |
| 5 | 72 | 0 | 0 | 4 | 155.693,14 | 0,00 | 0 |
| 6 | 1 | 1 | 0 | 147 | 79.674.400,00 | 0,00 | 0 |
| 6 | 2 | 1 | 0 | 10 | 1.450.000,00 | 0,00 | 0 |
| 6 | 3 | 0 | 0 | 48 | 24.811.991,00 | 0,00 | 0 |
| 7 | 3 | 1 | 0 | 130 | 51.517.235,09 | 0,00 | 0 |
| 7 | 4 | 0 | 0 | 379 | 53.397.015,00 | 0,00 | 0 |
| 7 | 16 | 0 | 0 | 34 | 338.085,22 | 0,00 | 0 |
| 10 | 1 | 1 | 0 | 77 | 331.155,50 | 0,00 | 0 |
| 10 | 2 | 0 | 0 | 2 | 5.744,00 | 0,00 | 0 |
| 61 | 3 | 0 | 0 | 1 | 750.000,00 | 0,00 | 0 |

## 4. Anahtar ilişkiler (FK yok — ölçülmüş eşleşme)

> LOGICALREF aralıkları tablolar arasında örtüşür: yanlış hedef tabloda da yüksek 'eşleşme' çıkabilir (örn. PAYTRANS MODULENR 7 FICHEREF → INVOICE %92). Hedef, modül anlamı + %100 eşleşme birlikte okunarak seçildi.

Pencere: kaynak tablonun 2026-09 satırları (kartlarda tüm tablo). `dolu` = referans ≠ 0; `oran` = hedefte bulunan / dolu.

| Kaynak.kolon | Koşul | Hedef | Satır | Dolu | Eşleşen | Oran | Durum |
|---|---|---|---:|---:|---:|---:|---|
| `01_STLINE.INVOICEREF` |  | `01_INVOICE.LOGICALREF` | 322.567 | 284.986 | 284.986 | 1,00 | dogrulandi |
| `01_STLINE.STFICHEREF` |  | `01_STFICHE.LOGICALREF` | 322.567 | 319.799 | 319.799 | 1,00 | dogrulandi |
| `01_STLINE.STOCKREF` |  | `ITEMS.LOGICALREF` | 322.567 | 189.615 | 189.615 | 1,00 | dogrulandi |
| `01_STLINE.CLIENTREF` |  | `CLCARD.LOGICALREF` | 322.567 | 317.044 | 317.044 | 1,00 | dogrulandi |
| `01_STLINE.ORDFICHEREF` |  | `01_ORFICHE.LOGICALREF` | 322.567 | 31.265 | 31.265 | 1,00 | dogrulandi |
| `01_STLINE.ORDTRANSREF` |  | `01_ORFLINE.LOGICALREF` | 322.567 | 31.425 | 31.425 | 1,00 | dogrulandi |
| `01_STLINE.UOMREF` |  | `UNITSETL.LOGICALREF` | 322.567 | 189.238 | 189.238 | 1,00 | dogrulandi |
| `01_STLINE.USREF` |  | `UNITSETF.LOGICALREF` | 322.567 | 189.238 | 189.238 | 1,00 | dogrulandi |
| `01_STLINE.PRCLISTREF` |  | `PRCLIST.LOGICALREF` | 322.567 | 2.262 | 2.262 | 1,00 | dogrulandi |
| `01_STLINE.PAYDEFREF` |  | `PAYPLANS.LOGICALREF` | 322.567 | 0 | 0 | – | bos_kolon |
| `01_STLINE.SALESMANREF` |  | `LG_SLSMAN.LOGICALREF` | 322.567 | 89.605 | 89.605 | 1,00 | dogrulandi |
| `01_STLINE.CENTERREF` |  | `EMCENTER.LOGICALREF` | 322.567 | 2.888 | 2.888 | 1,00 | dogrulandi |
| `01_STLINE.ACCOUNTREF` |  | `EMUHACC.LOGICALREF` | 322.567 | 179.647 | 179.647 | 1,00 | dogrulandi |
| `01_STLINE.PRODORDERREF` |  | `PRODORD.LOGICALREF` | 322.567 | 45 | 45 | 1,00 | dogrulandi |
| `01_STLINE.SOURCEINDEX` | T.FIRMNR=411 | `L_CAPIWHOUSE.NR` | 322.567 | 316.910 | 316.910 | 1,00 | dogrulandi |
| `01_INVOICE.CLIENTREF` |  | `CLCARD.LOGICALREF` | 14.419 | 14.383 | 14.383 | 1,00 | dogrulandi |
| `01_INVOICE.PAYDEFREF` |  | `PAYPLANS.LOGICALREF` | 14.419 | 6.431 | 6.431 | 1,00 | dogrulandi |
| `01_INVOICE.ACCFICHEREF` |  | `01_EMFICHE.LOGICALREF` | 14.419 | 14.383 | 14.383 | 1,00 | dogrulandi |
| `01_INVOICE.SALESMANREF` |  | `LG_SLSMAN.LOGICALREF` | 14.419 | 10.438 | 10.438 | 1,00 | dogrulandi |
| `01_INVOICE.PROJECTREF` |  | `PROJECT.LOGICALREF` | 14.419 | 0 | 0 | – | bos_kolon |
| `01_INVOICE.SOURCEINDEX` | T.FIRMNR=411 | `L_CAPIWHOUSE.NR` | 14.419 | 14.418 | 14.418 | 1,00 | dogrulandi |
| `01_STFICHE.INVOICEREF` |  | `01_INVOICE.LOGICALREF` | 18.987 | 15.696 | 15.696 | 1,00 | dogrulandi |
| `01_STFICHE.CLIENTREF` |  | `CLCARD.LOGICALREF` | 18.987 | 17.363 | 17.363 | 1,00 | dogrulandi |
| `01_ORFICHE.CLIENTREF` |  | `CLCARD.LOGICALREF` | 8.149 | 8.149 | 8.149 | 1,00 | dogrulandi |
| `01_ORFICHE.PAYDEFREF` |  | `PAYPLANS.LOGICALREF` | 8.149 | 15 | 15 | 1,00 | dogrulandi |
| `01_ORFLINE.ORDFICHEREF` |  | `01_ORFICHE.LOGICALREF` | 31.455 | 31.455 | 31.455 | 1,00 | dogrulandi |
| `01_ORFLINE.STOCKREF` |  | `ITEMS.LOGICALREF` | 31.455 | 30.759 | 30.759 | 1,00 | dogrulandi |
| `01_ORFLINE.CLIENTREF` |  | `CLCARD.LOGICALREF` | 31.455 | 31.455 | 31.455 | 1,00 | dogrulandi |
| `01_ORFLINE.UOMREF` |  | `UNITSETL.LOGICALREF` | 31.455 | 30.759 | 30.759 | 1,00 | dogrulandi |
| `01_CLFLINE.CLIENTREF` |  | `CLCARD.LOGICALREF` | 16.300 | 16.266 | 16.266 | 1,00 | dogrulandi |
| `01_CLFLINE.SOURCEFREF` | S.MODULENR=4 | `01_INVOICE.LOGICALREF` | 14.383 | 14.383 | 14.383 | 1,00 | dogrulandi |
| `01_CLFLINE.SOURCEFREF` | S.MODULENR=5 | `01_CLFICHE.LOGICALREF` | 1.210 | 1.201 | 1.201 | 1,00 | dogrulandi |
| `01_CLFLINE.SOURCEFREF` | S.MODULENR=6 | `01_CSROLL.LOGICALREF` | 84 | 84 | 84 | 1,00 | dogrulandi |
| `01_CLFLINE.SOURCEFREF` | S.MODULENR=7 | `01_BNFICHE.LOGICALREF` | 543 | 543 | 0 | 0,00 | yanlis_hedef |
| `01_CLFLINE.SOURCEFREF` | S.MODULENR=10 | `01_KSLINES.LOGICALREF` | 79 | 79 | 79 | 1,00 | dogrulandi |
| `01_CLFLINE.ACCFICHEREF` |  | `01_EMFICHE.LOGICALREF` | 16.300 | 15.922 | 15.921 | 1,00 | dogrulandi |
| `01_PAYTRANS.CARDREF` |  | `CLCARD.LOGICALREF` | 13.096 | 13.062 | 13.062 | 1,00 | dogrulandi |
| `01_PAYTRANS.FICHEREF` | S.MODULENR=4 | `01_INVOICE.LOGICALREF` | 10.994 | 10.994 | 10.994 | 1,00 | dogrulandi |
| `01_PAYTRANS.FICHEREF` | S.MODULENR=5 | `01_CLFICHE.LOGICALREF` | 1.274 | 1.274 | 0 | 0,00 | yanlis_hedef |
| `01_PAYTRANS.FICHEREF` | S.MODULENR=6 | `01_CSROLL.LOGICALREF` | 205 | 205 | 205 | 1,00 | dogrulandi |
| `01_PAYTRANS.FICHEREF` | S.MODULENR=7 | `01_BNFICHE.LOGICALREF` | 543 | 543 | 0 | 0,00 | yanlis_hedef |
| `01_PAYTRANS.FICHEREF` | S.MODULENR=10 | `01_KSLINES.LOGICALREF` | 79 | 79 | 79 | 1,00 | dogrulandi |
| `01_PAYTRANS.FICHELINEREF` |  | `01_CLFLINE.LOGICALREF` | 13.096 | 206 | 204 | 0,99 | dogrulandi |
| `01_PAYTRANS.CROSSREF` |  | `01_PAYTRANS.LOGICALREF` | 13.096 | 0 | 0 | – | bos_kolon |
| `01_KSLINES.CARDREF` |  | `KSCARD.LOGICALREF` | 108 | 108 | 108 | 1,00 | dogrulandi |
| `01_KSLINES.ACCFICHEREF` |  | `01_EMFICHE.LOGICALREF` | 108 | 78 | 78 | 1,00 | dogrulandi |
| `01_BNFLINE.SOURCEFREF` |  | `01_BNFICHE.LOGICALREF` | 2.484 | 1.560 | 1.446 | 0,93 | kismi |
| `01_BNFLINE.BNACCREF` |  | `BANKACC.LOGICALREF` | 2.484 | 2.484 | 2.484 | 1,00 | dogrulandi |
| `01_BNFLINE.BANKREF` |  | `BNCARD.LOGICALREF` | 2.484 | 2.484 | 2.484 | 1,00 | dogrulandi |
| `01_BNFLINE.CLIENTREF` |  | `CLCARD.LOGICALREF` | 2.484 | 1.424 | 1.424 | 1,00 | dogrulandi |
| `01_BNFLINE.ACCFICHEREF` |  | `01_EMFICHE.LOGICALREF` | 2.484 | 1.443 | 1.443 | 1,00 | dogrulandi |
| `01_CSTRANS.CSREF` |  | `01_CSCARD.LOGICALREF` | 217 | 217 | 217 | 1,00 | dogrulandi |
| `01_CSTRANS.ROLLREF` |  | `01_CSROLL.LOGICALREF` | 217 | 217 | 217 | 1,00 | dogrulandi |
| `01_CSROLL.CARDREF` |  | `CLCARD.LOGICALREF` | 101 | 86 | 86 | 1,00 | dogrulandi |
| `01_EMFLINE.ACCFICHEREF` |  | `01_EMFICHE.LOGICALREF` | 36.974 | 36.974 | 36.974 | 1,00 | dogrulandi |
| `01_EMFLINE.ACCOUNTREF` |  | `EMUHACC.LOGICALREF` | 36.974 | 36.974 | 36.974 | 1,00 | dogrulandi |
| `01_EMFLINE.CENTERREF` |  | `EMCENTER.LOGICALREF` | 36.974 | 20.750 | 20.750 | 1,00 | dogrulandi |
| `ITEMS.UNITSETREF` |  | `UNITSETF.LOGICALREF` | 32.859 | 32.858 | 32.858 | 1,00 | dogrulandi |
| `UNITSETL.UNITSETREF` |  | `UNITSETF.LOGICALREF` | 34 | 34 | 34 | 1,00 | dogrulandi |
| `PRCLIST.CARDREF` |  | `ITEMS.LOGICALREF` | 317.349 | 317.349 | 317.349 | 1,00 | dogrulandi |
| `PRCLIST.UOMREF` |  | `UNITSETL.LOGICALREF` | 317.349 | 317.349 | 317.349 | 1,00 | dogrulandi |
| `BANKACC.BANKREF` |  | `BNCARD.LOGICALREF` | 118 | 118 | 118 | 1,00 | dogrulandi |

### Modüle göre hedef testi (aynı referansın aday tablolardaki eşleşmesi)

| Kaynak.kolon | MODULENR | Dolu | INVOICE | CLFICHE | CLFLINE | CSROLL | BNFICHE | BNFLINE | KSLINES |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `PAYTRANS.FICHEREF` | 4 | 10.994 | 10.994 | 0 | 10.357 | 0 | 0 | 0 | 0 |
| `PAYTRANS.FICHEREF` | 5 | 1.274 | 830 | 0 | 1.274 | 0 | 0 | 0 | 0 |
| `PAYTRANS.FICHEREF` | 6 | 205 | 153 | 205 | 204 | 205 | 203 | 205 | 201 |
| `PAYTRANS.FICHEREF` | 7 | 543 | 497 | 0 | 533 | 0 | 0 | 543 | 0 |
| `PAYTRANS.FICHEREF` | 10 | 79 | 53 | 79 | 77 | 0 | 77 | 79 | 79 |
| `PAYTRANS.FICHEREF` | 61 | 1 | 1 | 0 | 1 | 0 | 0 | 0 | 0 |
| `CLFLINE.SOURCEFREF` | 4 | 14.383 | 14.383 | 0 | 13.280 | 0 | 0 | 0 | 0 |
| `CLFLINE.SOURCEFREF` | 5 | 1.201 | 943 | 1.201 | 1.199 | 0 | 0 | 1.157 | 0 |
| `CLFLINE.SOURCEFREF` | 6 | 84 | 28 | 84 | 84 | 84 | 83 | 84 | 84 |
| `CLFLINE.SOURCEFREF` | 7 | 543 | 497 | 0 | 533 | 0 | 0 | 543 | 0 |
| `CLFLINE.SOURCEFREF` | 10 | 79 | 53 | 79 | 77 | 0 | 77 | 79 | 79 |
| `CLFLINE.SOURCEFREF` | 61 | 1 | 1 | 0 | 1 | 0 | 0 | 1 | 0 |
| `BNFLINE.SOURCEFREF` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `BNFLINE.SOURCEFREF` | 6 | 2 | 0 | 2 | 2 | 2 | 2 | 2 | 2 |
| `BNFLINE.SOURCEFREF` | 7 | 1.443 | 1.443 | 1.439 | 1.443 | 0 | 1.443 | 1.443 | 0 |
| `BNFLINE.SOURCEFREF` | 10 | 1 | 0 | 1 | 1 | 0 | 1 | 1 | 1 |
| `BNFLINE.SOURCEFREF` | 61 | 38 | 38 | 0 | 38 | 0 | 0 | 35 | 0 |
| `BNFLINE.SOURCEFREF` | 62 | 38 | 38 | 0 | 38 | 0 | 0 | 35 | 0 |
| `BNFLINE.SOURCEFREF` | 65 | 38 | 38 | 0 | 38 | 0 | 0 | 35 | 0 |

Sonuç (modül anlamı + %100 eşleşme): CLFLINE.SOURCEFREF 4→INVOICE, 5→CLFICHE, 6→CSROLL, 7→BNFLINE, 10→KSLINES; PAYTRANS.FICHEREF 4→INVOICE, 5→CLFLINE, 6→CSROLL, 7→BNFLINE, 10→KSLINES; BNFLINE.SOURCEFREF 7→BNFICHE (MODULENR 0'da boş). LDDS'nin bu ailelerde tanımladığı 370 ilişki JSON'da (`ldds_iliskileri`, ölçülüp ölçülmediği işaretli).

## 5. TİMAŞ'a özel tablo ve görünümler

2.634 özel nesne (1.431 görünüm, 1.203 tablo). Bağlantı hesabı (zekiai) VIEW DEFINITION iznine sahip değil: 1.431 özel görünümün hiçbirinin SQL tanımı okunamadı. Açıklamalar ad + kolon listesi + eski kural madencisi kanıtından (2026-09-16'da tanımlar okunabiliyordu). Aynı DB'de 211/411 dışındaki firma numaralarına ait LG_/LV_ nesneleri; kapsam SEMANTIC_FIRMS ile sınırlıdır. (123 firma no, 54.662 nesne.)

| Önek | Görünüm | Tablo | Tablo satırı | Adında 411 | Adında 211 | Açıklama (ad + kolon çıkarımı) | Örnek |
|---|---:|---:|---:|---:|---:|---|---|
| `LG` | 0 | 562 | 65.383 | 7 | 7 | Standart olmayan LG_ tabloları: LG_XT* (genişletilmiş alanlar), LG_NTLCK_* (kilit), LG_EXCHANGE_<firma> (firma bazlı günlük kur), LG_SLS* (Logo CRM satış modülü). | LG_ACTPEPL, LG_CATEGLISTS, LG_CNTSLSMASG |
| `MS` | 20 | 258 | 1.679.027 | 40 | 40 | Logo WMS/depo eklentisi tabloları (paketleme, sevkiyat, sayım); çoğu 0 satır. | MS_191_01_CKFICHE, MS_191_01_CKFLINE, MS_191_01_PCKCORDER |
| `NY` | 245 | 5 | 36.145 | 0 | 7 | TİMAŞ'a özel analiz görünümleri (net satış, vadeler, bakiye, B2C fatura, bedelsiz gönderim, iade oranları); çoğu yıl/firma eki taşır. | NY_2017_GRBY_NetSatis, NY_2018_GRBY_NetSatis, NY_2019_GRBY_NetSatis |
| `VW` | 207 | 0 | 0 | 103 | 80 | Danışman/üçüncü taraf rapor görünümleri, firma-dönem kodlu (VW_411_01_*): cari ekstre, ayrıntılı tahsilat, satış analizi, kârlılık analizi, banka hareketi, çek/senet, malzeme envanteri, sipariş detayları, mobil saha (MMX). | VW_000_01_CSCARD_WITH_ROLLREF, VW_211_01_ALIS_SATIS_CIRO, VW_211_01_AYLARA_GORE_CARI_SATIS |
| `V` | 153 | 0 | 0 | 4 | 13 | TİMAŞ rapor görünümleri: satış raporu (V_SatisRaporu_411: fatura no/tarih, cari, kanal, malzeme, miktar, net/KDV tutarları), cari limit kontrolleri, sipariş–irsaliye–fatura listeleri, Amazon/e-ticaret kırılımları. | V_CARI_LIMITS, V_CARI_LIMITS_020_F, V_CARI_LIMITS_191 |
| `EOS` | 145 | 0 | 0 | 0 | 10 | Rapor görünümleri (cari bakiye, satınalma, e-fatura statüsü, ambar fişleri, bekleyen sipariş); ağırlıkla eski firma numaraları. | EOS_150_SATINALMA_191, EOS_150_SATINALMA_192, EOS_150_SATINALMA_193 |
| `AA` | 132 | 0 | 0 | 0 | 0 | Analiz/hedef görünümleri (hedef–gerçekleşen, tahsilat takip, 5 yıllık satış, bekleyen sipariş, cari ekstre). | AA_171_CARI_CLCARD, AA_171_CARİ_KART, AA_2016_HEDEF_GERC_CARI |
| `DLG` | 0 | 117 | 26.237 | 3 | 11 | Logo eklenti tabloları (netlock, mutabakat, LPAY). | DLG_LPAYPARAMS_191, DLG_LPAYPARAMS_211, DLG_LPAYPAYMENTS_191 |
| `KDV` | 100 | 0 | 0 | 1 | 3 | Firma bazında KDV dağıtım/maliyet görünümleri. | KDV_DAGITIM_MALIYET_015, KDV_DAGITIM_MALIYET_016, KDV_DAGITIM_MALIYET_171 |
| `MMX` | 0 | 97 | 1.567 | 26 | 20 | Mobil saha satış eklentisi (ziyaret, dağıtım, sayım); çoğu 0 satır. | MMX_211_01_BELGE_DETAY_TEMP, MMX_211_01_BELGE_TEMP, MMX_211_01_COLLECTION_PAYMENT |
| `XX` | 84 | 0 | 0 | 0 | 0 | Satış elemanı kısaltmalı bekleyen sipariş/cari ekstre görünümleri. | XX_ANKARA_IRS_SATIS, XX_ANKARA_SATISLAR, XX_ANKARA_SATISLAR_015 |
| `ZEN` | 56 | 19 | 21 | 31 | 25 | Tüp/gaz kiralama eklentisi (ad çıkarımı); tabloları 0 satır (yalnız ZEN_SBT_TUP_HAREKET 21) — TİMAŞ iş verisi değil. | ZEN_211_01_TUP_KIMLIK_KARTI_SAYIM, ZEN_211_01_TUP_KIMLIK_KARTI_SAYIM_HAREKET, ZEN_411_01_TUP_KIMLIK_KARTI_SAYIM |
| `A` | 55 | 0 | 0 | 0 | 9 | A_MS_* / A_*_CRM_URETIM_STATUS: danışman çalışma görünümleri (barkod, fiyat listesi, depo, CRM üretim durumu). | A_2019_CRM_URETIM_STATUS, A_2020_CRM_URETIM_STATUS, A_2021_CRM_URETIM_STATUS |
| `KPMG` | 52 | 0 | 0 | 3 | 3 | Denetim (KPMG) için satış/KDV/üretim sarf raporları. | KPMG_KDV_SET_ALT_URUN, KPMG_KDV_Setsiz_Kontrol, KPMG_KDV_URETIM_SARF_ALL_MODUL |
| `KMPG` | 42 | 0 | 0 | 2 | 2 | Denetim için satınalma ve maliyet dağıtım raporları (KPMG yazım hatası). | KMPG_EOS_STNALMA_FAT_DETAY_2022, KMPG_MLYT_DGTM_DETAY_2019, KMPG_MLYT_DGTM_DETAY_2019_KDV |
| `WT` | 31 | 0 | 0 | 0 | 0 | Eski yılların (2015–2023) birleşik satış/üretim/stok görünümleri. | WT_L_2015, WT_LOGO_2015, WT_LOGO_2016 |
| `LM` | 0 | 30 | 25 | 0 | 14 | POS eklentisi tabloları; çoğu boş. | LM_173_01_POSDETAIL, LM_173_01_POSMASTERDOWN, LM_173_01_POSMASTERUP |
| `T` | 0 | 29 | 6.483.955 | 0 | 0 | Tarihsel/özel tablolar: T_USATIS_2006…2014 eski yıl satışları, T_SATIS_HEDEFI_*, T_UYUM_* (mizan/bilanço), T_BMALIYET. | T_BMALIYET, T_BRM_MLYTLER, T_CARI_GRUBU |
| `ESP` | 0 | 20 | 194.647 | 0 | 0 | Saha satış eklentisi tabloları (firma ürün, hareketler, fiş). | ESP_ALTURUNGRUBU, ESP_ANAURUNGRUBU, ESP_BARKODTIPI |
| `LAV` | 16 | 0 | 0 | 0 | 16 | LAV_211_01_*: cari detaylı ekstre, fiyat, maliyet, müşteri–ürün ilişkisi görünümleri (yalnız 211). | LAV_211_01_AJANDA, LAV_211_01_CARI_DETAYLI_EKSTRE, LAV_211_01_CLCARD |
| `ARV` | 13 | 0 | 0 | 1 | 3 | Muhasebe kaynak hareketleri, envanter maliyeti, MM detay arşiv görünümleri. | ARV_021_ACCNTSRCTRNS, ARV_122_ACCNTSRCTRNS, ARV_129_ACCNTSRCTRNS |
| `CRM` | 12 | 0 | 0 | 0 | 7 | CRM'e beslenen stok/fiyat/depo bilgisi görünümleri. | CRM_Account, CRM_Stok_Bilgisi_Depo_Programı_201, CRM_Stok_Bilgisi_Depo_Programı_211 |
| `MV` | 10 | 0 | 0 | 3 | 3 | Rapor ara görünümleri: satış toplamları, vade raporu, cari hareket analizi (211/411). | MV_BY_ITEMS, MV_BY_MARK_LIST, MV_BY_RAF_ETIKETI |
| `DV` | 1 | 8 | 0 | 0 | 9 | Açıklama yok (ad çıkarımı yapılmadı) | DV_211_01_ITEMS, DV_211_01_KULLANICILAR, DV_211_01_MUSTERI_URUN_ILISKISI |
| `HRMS` | 2 | 7 | 65.833 | 2 | 2 | HRMS eklentisi (borç kapama, son alım, malzeme hata denetimi). | HRMS_021_BORCKAPAMA, HRMS_211_BORCKAPAMA, HRMS_211_SONALIM |
| `TSoft` | 9 | 0 | 0 | 0 | 0 | T-soft e-ticaret entegrasyon görünümleri (ürün, cari, sipariş, stok, kampanya). | TSoft_AnaUrun, TSoft_Cari, TSoft_CariHareket |
| `AB` | 1 | 5 | 1.563 | 0 | 0 | Açıklama yok (ad çıkarımı yapılmadı) | AB_CariAylıkBakiye, AB_Mizan_2021, AB_Mizan_2022 |
| `Pbi` | 6 | 0 | 0 | 0 | 0 | Power BI kaynak görünümleri (120/320 bakiye, fuar satış/stok). | Pbi_Bakiye_120, Pbi_Bakiye_320, Pbi_Fuar_Satis |
| `TG` | 0 | 6 | 22.030 | 0 | 0 | Açıklama yok (ad çıkarımı yapılmadı) | TG_DEFTER_TOPLAMI, TG_EDEFTER_HATA_LISTESI, TG_EMFICHE_GLOBLINENO |
| `CLOSEDDIST` | 0 | 5 | 0 | 1 | 0 | Kapatma dağıtım yardımcı tabloları. | CLOSEDDIST_015_01, CLOSEDDIST_181_01, CLOSEDDIST_311_01 |
| `KAPAT` | 0 | 5 | 51 | 1 | 0 | Borç kapama yardımcı tabloları. | KAPAT_015_01, KAPAT_181_01, KAPAT_311_01 |
| `PB` | 4 | 0 | 0 | 2 | 2 | Power BI kaynak görünümleri (PayTrans, Tarçın satış; 211/411). | PB_PayTrans_211, PB_PayTrans_411, PB_Tarcin_Satis_211 |
| `PBI` | 4 | 0 | 0 | 0 | 0 | Power BI kaynak görünümleri (fiyat listesi, POS, Uçan Kitap). | PBI_FiyatList, PBI_POSDetay, PBI_UcanKitap_Satis |
| `Tsoft` | 2 | 1 | 1 | 0 | 0 | T-soft entegrasyon görünümleri. | Tsoft_Adres, Tsoft_FirmaveDonemNo, Tsoft_Yazar |
| `171` | 2 | 0 | 0 | 0 | 0 | Açıklama yok (ad çıkarımı yapılmadı) | 171_stok_kartı, 171_stok_kartı_new |
| `AAAA` | 2 | 0 | 0 | 0 | 0 | Açıklama yok (ad çıkarımı yapılmadı) | AAAA_KASA_TEST, AAAA_NY_TEST |
| `l` | 0 | 2 | 248 | 0 | 0 | Açıklama yok (ad çıkarımı yapılmadı) | l_CAPIFIRM_BCK, l_CAPIPERIO_BCK |
| `Netahsilat` | 0 | 2 | 5.797 | 0 | 0 | Açıklama yok (ad çıkarımı yapılmadı) | Netahsilat_Account, Netahsilat_Transaction |
| `SATIS` | 2 | 0 | 0 | 0 | 0 | Eski satış raporu görünümleri. | SATIS_NEW_015, SATIS_RP |
| `YTL` | 0 | 2 | 268 | 0 | 0 | Açıklama yok (ad çıkarımı yapılmadı) | YTL_DRIVETBL, YTL_SPACETBL |
| `BCKP` | 0 | 1 | 16 | 1 | 0 | Yedek kopya tablo(lar)ı (BCKP_030826LG_411_01_STLINE). | BCKP_030826LG_411_01_STLINE |

### Güncel (411) ve kritik nesneler

| Nesne | Tür | Satır | Eski kural madenciliğinde kaynak | Kolonlar |
|---|---|---:|---:|---|
| `V_SatisRaporu_411` | VIEW | – | 17 | FIRMAKOD, Sipariş Numarası, Fatura No, Fatura Tarihi, Ay, Yıl, Cari Kodu, Cari Ünvanı, Şehir, İlçe, Satıcı Kodu, Fatura Türü, Satis_Iade, Satır Türü, Malzeme/Hizmet Kodu, Malzeme/Hizmet Adı, Miktar, Birim, Birim Fiyat, İndirim Tutar, İndirim Oranı, Fiyat Farkı, Net Tutar, KDV Oranı, KDV Tutarı, KDVli Tutar, KANAL |
| `V_SatisRaporu_411_ETicaret` | VIEW | – | 0 | FIRMAKOD, Sipariş Numarası, Fatura No, Fatura Tarihi, Ay, Yıl, Cari Kodu, Cari Ünvanı, Şehir, İlçe, Satıcı Kodu, Fatura Türü, Satis_Iade, Satır Türü, Malzeme/Hizmet Kodu, Malzeme/Hizmet Adı, Miktar, Birim, Birim Fiyat, İndirim Tutar, İndirim Oranı, Fiyat Farkı, Net Tutar, KDV Oranı, KDV Tutarı, KDVli Tutar, KANAL |
| `KPMG_V_SatisRaporu_411` | VIEW | – | 13 | FIRMAKOD, Sipariş Numarası, Fatura No, Fatura Tarihi, Ay, Yıl, Cari Kodu, Cari Ünvanı, VergiNo, Şehir, İlçe, Satıcı Kodu, Fatura Türü, Satis_Iade, Satır Türü, Malzeme/Hizmet Kodu, Malzeme/Hizmet Adı, Miktar, Birim, Birim Fiyat, İndirim Tutar, İndirim Oranı, Fiyat Farkı, Net Tutar, KDV Oranı, KDV Tutarı, KDVli Tutar, KANAL |
| `V_SatisRaporu_Amazon_2026` | VIEW | – | 15 | FIRMAKOD, Sipariş Numarası, Fatura No, Fatura Tarihi, Ay, Yıl, Cari Kodu, Cari Ünvanı, Şehir, İlçe, Satıcı Kodu, Fatura Türü, Satis_Iade, Satır Türü, Malzeme/Hizmet Kodu, Malzeme/Hizmet Adı, Miktar, Birim, Birim Fiyat, İndirim Tutar, İndirim Oranı, Fiyat Farkı, Net Tutar, KDV Oranı, KDV Tutarı, KDVli Tutar, KANAL, MusteriSipNo |
| `V_Miktar_Amazon_411` | VIEW | – | 0 | Malzeme Kodu, new_ean13, new_yayineviidName, Malzeme Adı, 2026 Miktar, Toplam Miktar, Cari Kodu, Cari Ünvanı |
| `V_YazarEkstre_411` | VIEW | – | 32 | SatırNo, DURUM, LOGICALREF, CROSSREF, CARDREF, CARI_KOD, CARI_AD, BMT, KANAL, SEHIR, ISLEM_TARIHI, VADE_TARİHİ, MODULENR, SIGN, FICHEREF, FICHELINEREF, TRCODE, BELGE_NO, İŞLEM_TÜRÜ, BORC, ALACAK, BAKİYE, PAID, CROSSTOTAL, TRRATE, MODIFIED, CLOSINGRATE, PAYNO … |
| `PB_PayTrans_411` | VIEW | – | 22 | CARI_KOD, CariUnvan, KANAL, ISLEM_TARIHI, Birlestime, VADE_TARİHİ, borc-alacak, İŞLEM TİPİ, İŞLEM_TÜRÜ, TOTAL |
| `PB_Tarcin_Satis_411` | VIEW | – | 2 | CODE, DEFINITION_, PRICE, TARIH, IRSALIYE_NO, FATURA_NO, ÜRÜN KODU, ÜRÜN ADI, MİKTAR, TUTAR, KDV, TOPLAM |
| `MV_RPR_411_01_SATIS_TOPLAMLARI` | VIEW | – | 0 | AY, YIL, FATURA_TOPLAM, ISKONTO_TOPLAM, TUTAR, TOPLAM_KDV, NET_TUTAR, TOPLAM_IADE |
| `MV_RPR_411_01_MIND_VADE_RAPORU` | VIEW | – | 4 | ROW_ID, CARDREF, CODE, ilgili, NAME, Tel1, Tel2, Musteri_Temsilcisi, Borc_Bakiyesi, Borc_Gunu_Gecen, Borc_Gunu_Gelmeyen, Alacak_Bakiyesi, Alacak_Gunu_Gecen, Alacak_Gunu_gelmeyen, SonVadeTarihi, EnYakinVadeTarihi, SPECODE, CYPHCODE, ORTALAMA_VADETARIHI, ENESKIBORC, GECEN_GUN |
| `MV_RPR_411_01_MIND_CARI_HAREKET_ANALIZI` | VIEW | – | 69 | LOGICALREF, HAREKET_OZEL_KODU, HAREKET_OZEL_KODU2, MUSTERI_TIPI, AKTIFLIK_DURUMU, MUSTERI_ID, AKTIFLIK, MUSTERI_KODU, MUSTERI_ADI, MUSTERI_OZEL_KOD, ULKE, SEHIR, MUSTERI_OZEL_KOD_2, MUSTERI_OZEL_KOD_3, MUSTERI_OZEL_KOD_4, MUSTERI_OZEL_KOD_5, HAREKET_TARIHI, KAYNAK_REF, MODUL_NUMARASI, TR_CODE, IPTAL, MODUL_ACIKLAMA, ISLEM_TIPI, ISLEM_NO, BELGE_NO, TUTAR, BORC, ALACAK … |
| `VW_411_01_SATIS_ANALIZI` | VIEW | – | 0 | HAREKET_TURU, HAREKET_OZEL_KODU, SATICI, HAREKET_TARIHI, KAYNAK_DEPO, MIKTAR, FIYAT, TOPLAM, KDV, KDV_TUTAR, KDV_MATRAH, EK_VERGI, CIKIS_MALIYETI, NET_TOPLAM, KAR, GIRIS_CIKIS, CIKIS_MALIYET_RD, NET_TOPLAM_RD, FIYAT_FARKI_TUTARI, FIYAT_FARKI_RD, KAR_RD, FIS_NO, AMBAR_NO, OZEL_KODU, MUSTERI_KODU, MUSTERI, MUSTERI_OZEL_KODU, MALZEME_KODU … |
| `VW_411_01_KARLILIK_ANALIZI` | VIEW | – | 0 | ROW_ID, STRNS_TRCODE, STRNS_SOURCEINDEX, STRNS_FACTORYNR, DATE_, DOVIZ_ADI, STRNS_DATE_, STRNS_DATE_DETAILS, CLNTC_CODE, CLNTC_DEFINITION_, CLNTC_SPECODE, ITMSC_CODE, ITMSC_NAME, ITMSC_SPECODE, INVFC_FICHENO, INVFC_BRANCH, INVFC_DEPARTMENT, SLSMC_CODE, SLSMC_DEFINITION_, SLSMC_SPECODE, SLSMC_TYP, A_Ocak, A_Subat, A_Mart, A_Nisan, A_Mayis, A_Haziran, A_Temmuz … |
| `VW_411_01_AYRINTILI_TAHSILAT` | VIEW | – | 0 | ROW_ID, CARI_UNVAN, CARI_KODU, CARI_ID, FISNO, SALESMANREF, SALESMAN_NAME, TARIH, VADE, GECEN_GUN, TURU, MODULENR, TIP, TRCODE, TUTAR, ODENEN, KALAN |
| `VW_411_01_CLEKSTRE` | VIEW | – | 0 | ROW_ID, CL_DEFINITION, SL_DEFINITION, LOGICALREF, CLIENTREF, SOURCEFREF, DATE_, TRANNO, TRCODE, MODULENR, SALESMANREF, AMOUNT, CYPHCODE, DEBIT, CREDIT, DESCR, BANK_ACC, TRCURR, TRNET, DEBIT_CUR, CREDIT_CUR, DOCODE, ISLEM_ADI, ISLEM_ADI_KISA, BAKIYE, DOVIZLI_BAKIYE |
| `VW_411_01_MUSTERI_RISK_RAPORU` | VIEW | – | 0 | LOGICALREF, TCKNO, TAXNR, SPECODE5, CODE, UNVAN, SEHIR, SPECODE, BAKIYE, CEKSENET, KENDICEKSENET, TOPLAMBORC, GUNUGECENBORC, ENESKIBORC, BEKLEYENSIPARIS, FATURALANMAMISIRSALIYE |
| `VW_411_01_FATURALANMAMIS_IRSALIYELER` | VIEW | – | 0 | LOGICALREF, CLIENTREF, DATE_, FICHENO, SPECODE, NETTOTAL, GENEXP1, CARI_UNVAN, CARI_KODU |
| `VW_411_01_MALZEME_ENVANTER_RAPORU` | VIEW | – | 0 | URUN_ID, URUN_KODU, URUN_ADI, DEPO_ID, DEPO_ADI, URUN_YETKI_KODU, URUN_OZEL_KODU, URUN_OZEL_KODU2, URUN_OZEL_KODU3, URUN_OZEL_KODU4, URUN_OZEL_KODU5, URUN_GRUP_KODU, KALAN_STOK_MIKTARI, ORTALAMA_MALIYET, ORTALAMA_TUTAR, SON_SATINALMA_FIYAT, SATINALMA_TUTAR |
| `AA_BEKLEYEN_SIP_V3` | VIEW | – | 0 | ÜRÜN KODU, ÜRÜN ADI, FİYATI (KDV HARİÇ), YAYINEVİ, KİTAPLIK, TÜR, YAZAR, ÇIKIŞ_TARİHİ, ÇIKIŞ YILI, ÇIKIŞ AYI, BEKLEYEN MİKTAR, İKİTELLİ DEPO, ANKARA DEPO, TOPLAM STOK |
| `NY_Vadeler_2024` | VIEW | – | 32 | TRCURR, DÖNEM, SatırNo, DURUM, LOGICALREF, CROSSREF, CARDREF, CARI_KOD, CARI_AD, BMT, KANAL, SEHIR, ISLEM_TARIHI, VADE_TARİHİ, MODULENR, SIGN, FICHEREF, FICHELINEREF, TRCODE, BELGE_NO, İŞLEM TİPİ, İŞLEM_TÜRÜ, BORC, ALACAK, BAKİYE, TOTAL, PAID, CROSSTOTAL … |
| `ABCekSenetView` | VIEW | – | 32 | cscardref, DOC, Çek/SenetTürü, CURRSTAT, Şimdiki Statüsü, PORTFOYNO, BANKNAME, SPECODE, CITY, Vade, Tutar, NetTutar, INUSE, CANCELLED, İptal Edilmiş, SALESMANREF, BMT, TRCODE, CekSenetIslemTuru, STATUS, IslemTuru, CARDREF, ACCREF |
| `BCKP_030826LG_411_01_STLINE` | USER_TABLE | 16 | 0 | LOGICALREF, STOCKREF, LINETYPE, PREVLINEREF, PREVLINENO, DETLINE, TRCODE, DATE_, FTIME, GLOBTRANS, CALCTYPE, PRODORDERREF, SOURCETYPE, SOURCEINDEX, SOURCECOSTGRP, SOURCEWSREF, SOURCEPOLNREF, DESTTYPE, DESTINDEX, DESTCOSTGRP, DESTWSREF, DESTPOLNREF, FACTORYNR, IOCODE, STFICHEREF, STFICHELNNO, INVOICEREF, INVOICELNNO … |
| `STLINENEGLEVEL41101` | USER_TABLE | 410 | 0 | LREF, CODE, NAME, SOURCEINDEX, SOURCECOSTGRP, DATE_, FTIME, FICHENO, TRCODE, AMOUNT, NEGAMOUNT |
| `T_USATIS_2014` | USER_TABLE | 493.632 | 0 | Stok_Kodu, Stok_Adı, YAYINEVİ, KİTAPLIK, TÜR, YAZAR, YAYIN YÖNETMENİ, YETİŞKİN-ÇOCUK, AKTİF-PASİF, Cari_Kod, Cari_Ad, CARİ KOD, CARİ ÜNVAN, MÜŞTERİ TÜRÜ, SATIŞ TÜRÜ, KANAL, BÖLGE, BMT, ŞEHİR, İLÇE, YIL, AY, ÇIKIŞ TARİHİ, ÇIKIŞ YILI, ÇIKIŞ AYI, İade_Durum, MİKTAR, BRUT_TUTAR … |
| `T_BMALIYET` | USER_TABLE | 3.890 | 0 | STOKKODU, STOKADI, BMLYT |

## 6. Eski katalog ↔ yeni motor (contracts.py)

Eski katalog yalnız aday anlamdır; `sertifika` = `human_certified_by`. Ölçümler 2026-09, 411.

| Kavram | Eski katalog (sertifikalı anlamlar) | Yeni motor | Proje belgesi | 2026-09 ölçüm | Fark / çelişki |
|---|---|---|---|---|---|
| **Net ciro / net satış** | #1 DBO_LG_{n0}_{n1}_INVOICE: `SUM(CASE WHEN INVOICE.TRCODE IN (7, 8, 9) THEN INVOICE.NETTOTAL ELSE -INVOICE.NETTOTAL END)` [INVOICE.TRCODE IN (2,3,7,8,9)] (seed)<br>#2 DBO_LG_{n0}_{n1}_STLINE: `SUM(CASE WHEN STLINE.TRCODE IN (7, 8, 9) THEN STLINE.LINENET ELSE -STLINE.LINENET END)` [STLINE.LINETYPE = (0), STLINE.CANCELLED = (0), STLINE.TRCODE IN (2,3,7,8,9), STLINE.INVOIC] (operator)<br>+2 aday/reddedilmiş | `net_sales`: `SUM(CASE WHEN f.TRCODE IN (2,3) THEN -f.LINENET ELSE f.LINENET END)` — Faturalı malzeme satırında satış (7/8/9) eksi iade (2/3); iskonto sonrası KDV hariç.<br>Koşul: STLINE: CANCELLED=0, LINETYPE=0, INVOICEREF<>0, TRCODE IN (istenen kodlar), DATE_ aralığı | TIMAS-IS-TANIMLARI #01: satır LINENET 7,8,9 − 2,3; iptal ve hizmet dışı satır hariç | motor_satir_LINETYPE0: 245.632.081,09<br>satir_hizmet_dahil_LINETYPE0_4: 245.350.590,51<br>baslik_NETTOTAL_KDV_dahil: 245.563.910,06 | Eski katalogda aynı terimin 2 sertifikalı anlamı var: (1) INVOICE.NETTOTAL (KDV dahil başlık, seed) ve (2) STLINE.LINENET (satır, operator). Motor (2)'yi uyguluyor. LINETYPE=0 nedeniyle TRCODE 9 (yalnız hizmet satırı) ve 7/8/3 içindeki hizmet satırları dışarıda kalır; '7/8/9' etiketi yanıltıcı. Sözlük/glossary dosyası hâlâ 'NETTOTAL, KDV dahil' der → belge çelişkisi. |
| **Satış tutarı (iade düşülmeden)** | #1 DBO_LG_{n0}_{n1}_INVOICE: `SUM(INVOICE.NETTOTAL)` [INVOICE.TRCODE IN (7,8,9)] (-)<br>#1 DBO_LG_{n0}_{n1}_INVOICE: `SUM(CASE WHEN INVOICE.TRCODE IN (7, 8, 9) THEN INVOICE.NETTOTAL ELSE 0 END)` [INVOICE.TRCODE IN (2,3,7,8,9)] (seed)<br>#3 DBO_LG_{n0}_{n1}_STLINE: `SUM(CASE WHEN STLINE.TRCODE IN (7, 8, 9) THEN STLINE.LINENET ELSE 0 END)` [STLINE.LINETYPE = (0), STLINE.CANCELLED = (0), STLINE.TRCODE IN (2,3,7,8,9), STLINE.INVOIC] (operator:claude)<br>+13 aday/reddedilmiş | `sales_amount`: `SUM(CASE WHEN f.TRCODE IN (7,8,9) THEN f.LINENET ELSE 0 END)` — Faturalı malzeme satırı, iskonto sonrası KDV hariç; iadeler düşülmeden satış (7/8/9).<br>Koşul: STLINE: CANCELLED=0, LINETYPE=0, INVOICEREF<>0, TRCODE IN (istenen kodlar), DATE_ aralığı | Kural 1: TRCODE 7,8,9 | motor_satir: 246.688.056,60<br>baslik_NETTOTAL: 247.899.226,74 | Eski 'satis tutari' INVOICE.NETTOTAL (KDV dahil) seed sertifikalı + STLINE.LINENET operator:claude sertifikalı; 'satis' SUM(NETTOTAL) 7,8,9. Motor satır LINENET (KDV hariç, iskonto sonrası). |
| **İade tutarı** | #1 DBO_LG_{n0}_{n1}_INVOICE: `SUM(CASE WHEN INVOICE.TRCODE IN (2, 3) THEN INVOICE.NETTOTAL ELSE 0 END)` [INVOICE.TRCODE IN (2,3,7,8,9)] (claude-inceleme)<br>+1 aday/reddedilmiş | `return_amount`: `SUM(CASE WHEN f.TRCODE IN (2,3) THEN f.LINENET ELSE 0 END)` — İptal edilmemiş faturalı malzeme iadesi; LINENET, KDV hariç, pozitif gösterim.<br>Koşul: STLINE: CANCELLED=0, LINETYPE=0, INVOICEREF<>0, TRCODE IN (istenen kodlar), DATE_ aralığı | #01 iade düşümü (iş teyidi bekliyor) | motor_satir_LINETYPE0: 1.055.975,51<br>baslik_NETTOTAL: 2.335.316,68<br>dislanan_iade_hizmet_satiri: 1.278.470,99 | Eski: INVOICE.NETTOTAL 2,3 (KDV dahil). Motor: STLINE.LINENET 2,3 LINETYPE 0. 2026-09'da TRCODE 3 içinde 1,28 Mn ₺'lik tek hizmet satırı (LINETYPE 4) motorda iade sayılmıyor; başlıkta sayılıyor. |
| **Fatura sayısı** | #3 DBO_LG_{n0}_{n1}_INVOICE: `COUNT(INVOICE.LOGICALREF)` [INVOICE.TRCODE IN (2,3,7,8,9)] (claude-excel-taslak)<br>+2 aday/reddedilmiş | `invoice_count`: `COUNT_BIG(*)` — İptal edilmemiş satış fatura başlıkları; satırlar değil INVOICE belgeleri (7/8/9).<br>Koşul: INVOICE: CANCELLED=0, TRCODE IN (7,8,9), DATE_ aralığı | Bellek/yerleşik kural: KPI kapsamı INVOICE.TRCODE IN (2,3,7,8,9) | motor_7_8_9_eylul: 13.680<br>kpi_2_3_7_8_9_eylul: 13.800<br>motor_7_8_9_2026: 88.757<br>kpi_2_3_7_8_9_2026: 92.137 | ÇELİŞKİ: motor iade faturalarını (2,3) saymıyor; eski sertifikalı tanım ve proje KPI kuralı sayıyor (2026: fark = iade fatura adedi). |
| **Fatura toplamı** | #1 LG_{n0}_{n1}_INVOICE: `SUM(INVOICE.NETTOTAL)`  (rule-miner) | `invoice_amount`: `SUM(f.NETTOTAL)` — İptal edilmemiş satış faturası NETTOTAL; fatura toplamı, satır net cirosu değildir.<br>Koşul: INVOICE: CANCELLED=0, TRCODE IN (7,8,9), DATE_ aralığı | Kural 1: tutar NETTOTAL (KDV dahil) | baslik_7_8_9: 247.899.226,74 | Eski rule-miner 'fatura toplam' SUM(NETTOTAL) süzgeçsiz (alış dahil). Motor yalnız satış 7,8,9, iade düşülmez. |
| **Satılan adet** | #1 LG_{n0}_{n1}_STLINE: `AMOUNT COLUMN `  (seed)<br>#1 DBO_LG_{n0}_{n1}_STLINE: `SUM(STLINE.AMOUNT)` [STLINE.LINETYPE = (0), STLINE.TRCODE IN (7,8), STLINE.INVOICEREF NOT IN (0)] (seed)<br>#2 DBO_LG_{n0}_{n1}_STLINE: `SUM(CASE WHEN STLINE.TRCODE IN (7, 8) THEN STLINE.AMOUNT ELSE 0 END)` [STLINE.LINETYPE = (0), STLINE.TRCODE IN (2,3,7,8), STLINE.INVOICEREF NOT IN (0)] (claude-inceleme)<br>+2 aday/reddedilmiş | `sold_quantity`: `SUM(CASE WHEN f.TRCODE IN (7,8) THEN f.AMOUNT ELSE 0 END)` — Faturalı malzeme satırı; perakende/toptan 7/8, iadeler düşülmeden miktar; hizmet 9 hariç.<br>Koşul: STLINE: CANCELLED=0, LINETYPE=0, INVOICEREF<>0, TRCODE IN (istenen kodlar), DATE_ aralığı; UINFO1/UINFO2 birim denetimi | #20 satılan adet TRCODE 7,8,9 IOCODE 3,4 | motor_7_8: 1.855.864,00 | Eski 'satilan adet'/'adet' CANCELLED süzgeci taşımıyor. Kural 20 TRCODE 9'u adet kapsamına alır; motor 9'u adet dışı bırakır (hizmet). |
| **Tahsilat (müşteri ödeme hareketleri)** | #1 LG_{n0}_{n1}_CLFLINE: `SUM(CASE WHEN CLCARD.CODE LIKE '120%' THEN LG_CLFLINE.AMOUNT ELSE 0 END)` [LG_CLFLINE.CANCELLED IN (0), LG_CLFLINE.SIGN IN (1), LG_CLFLINE.TRCODE IN (1,20,61,62,70)] (operator:claude (muhasebe testi, 2026-09-21))<br>+1 aday/reddedilmiş | `collections`: `SUM(f.AMOUNT)` — 120 müşteri carileri, iptal olmayan alacak hareketleri SIGN=1; nakit/havale/çek/senet/kart (1,20,61,62,70). Çek/senet teslimi dahil, yalnız nakit tahsil değildir.<br>Koşul: CLFLINE ⨝ CLCARD: CANCELLED=0, SIGN=1, TRCODE IN (1,20,61,62,70), CLCARD.CODE LIKE '120%' | #07 gerçekleşen tahsilat süresi kapama yok → hesaplanamaz | motor: 98.018.727,20 | Motor = eski sertifikalı 'müşteri tahsilatı' (operator:claude muhasebe testi). Eski 'tahsilat' tek kelime adayı yalnız TRCODE 1 (nakit) idi. Çek/senet girişi (61/62) nakit tahsil değildir; 131 (ortaklar) önekli gelen havaleler (2026-09: 33,8 Mn) dışarıda. |
| **Kâr** | #1 LG_{n0}_{n1}_STLINE: `SUM(CASE WHEN STLINE.TRCODE IN (7, 8, 9) THEN STLINE.LINENET - STLINE.AMOUNT * STLINE.OUTCOST ELSE -(STLINE.LI` [STLINE.LINETYPE = (0), STLINE.CANCELLED = (0), STLINE.TRCODE IN (2,3,7,8,9)] (operator) | yok<br>Koşul: Sözleşmede yok → netleştirme | #03 LINENET − AMOUNT×OUTCOST (iş teyidi bekliyor) | outcost_dolu_yuzde_satis_satirlari: 0,82 | Eski operator sertifikası var, motor desteklemiyor. 2026-09 satış satırlarının %0,8'inde OUTCOST dolu (maliyetlendirme 30.06.2026'ya kadar işlenmiş) → güncel ay kârı ölçülemez. |
| **Maliyet** | #1 DBO_LG_{n0}_{n1}_STLINE: `SUM(STLINE.AMOUNT * STLINE.OUTCOST)` [STLINE.LINETYPE = (0), STLINE.CANCELLED = (0), STLINE.TRCODE IN (7,8,9)] (operator) | yok<br>Koşul: Sözleşmede yok | #02 AMOUNT × OUTCOST | – | Motorda yok; OUTCOST doluluğu yukarıdaki gibi. |
| **Brüt kâr marjı** | #1 DBO_LG_{n0}_{n1}_STLINE: `1 - SUM(CASE WHEN STLINE.TRCODE IN (7, 8) AND STLINE.OUTCOST <> 0 THEN STLINE.AMOUNT * STLINE.OUTCOST ELSE 0 E` [STLINE.LINETYPE = (0), STLINE.TRCODE IN (2,3,7,8)] (seed)<br>#2 DBO_LG_{n0}_{n1}_STLINE: `(1 - SUM(STLINE.AMOUNT * STLINE.OUTCOST) / NULLIF(SUM(STLINE.TOTAL), 0)) * 100` [STLINE.LINETYPE = (0)] (seed)<br>#3 DBO_LG_{n0}_{n1}_STLINE: `1 - SUM(CASE WHEN STLINE.LINETYPE = 0 AND STLINE.OUTCOST <> 0 THEN STLINE.AMOUNT * STLINE.OUTCOST ELSE 0 END) ` [STLINE.TRCODE IN (7,8)] (seed) | yok<br>Koşul: Sözleşmede yok | Kural 2: OUTCOST<>0 satırlarda 1 − Σ(AMOUNT×OUTCOST)/Σ TOTAL | – | Eski katalogda üç farklı seed sertifikalı formül (TOTAL/LINENET paydası, OUTCOST<>0 süzgeci, ×100) — kendi içinde çelişkili. |
| **İskonto oranı** | #1 DBO_LG_{n0}_{n1}_STLINE: `SUM(CASE WHEN STLINE.LINETYPE = 2 THEN STLINE.TOTAL ELSE 0 END) / NULLIF(SUM(CASE WHEN STLINE.LINETYPE = 0 THE` [STLINE.TRCODE IN (7,8)] (operator)<br>+1 aday/reddedilmiş | yok<br>Koşul: Sözleşmede yok | #04 Σ TOTAL(LINETYPE 2)/Σ TOTAL(LINETYPE 0) | – | Eski operator tanımı = proje kararı = golden A032 yöntemi; motorda yok. |
| **Stok bakiyesi** | #1 DBO_LG_{n0}_{n1}_STLINE: `SUM(CASE WHEN STLINE.IOCODE IN (1, 2) THEN STLINE.AMOUNT ELSE -STLINE.AMOUNT END)` [STLINE.LINETYPE = (0), STLINE.CANCELLED = (0), STLINE.IOCODE IN (1,2,3,4)] (operator) | yok<br>Koşul: logo_reports stok: LV_STINVTOT.ONHAND ile STLINE IOCODE (1,2)−(3,4) uzlaşması | #09 yalnız cari kopya | – | Eski operator tanımı STLINE yönlü toplam; yeni rapor iki kaynağı uzlaştırmadan miktar vermez. |
| **Bekleyen sipariş** | #1 LG_{n0}_{n1}_ORFLINE: `SUM(LG_ORFLINE.AMOUNT - LG_ORFLINE.SHIPPEDAMOUNT)` [LG_ORFLINE.TRCODE IN (1), LG_ORFLINE.CLOSED IN (0), LG_ORFLINE.CANCELLED IN (0), LG_ORFLIN] (operator)<br>#1 LG_{n0}_{n1}_ORFLINE: `CLOSED IN ['0']` [LG_ORFLINE.TRCODE IN (1), LG_ORFLINE.CANCELLED IN (0), LG_ORFLINE.LINETYPE IN (0), LG_ORFL] (operator)<br>#1 LG_{n0}_{n1}_ORFLINE: `SUM((LG_ORFLINE.AMOUNT - LG_ORFLINE.SHIPPEDAMOUNT) * LG_ORFLINE.PRICE)` [LG_ORFLINE.CLOSED IN (0), LG_ORFLINE.TRCODE IN (1), LG_ORFLINE.CANCELLED IN (0), LG_ORFLIN] (operator) | yok<br>Koşul: logo_reports açık sipariş: ORFLINE CLOSED/SHIPPEDAMOUNT güncel durum; geçmiş tarihli açık durum üretilmez | #10 TRCODE 1, CLOSED=0, AMOUNT>SHIPPEDAMOUNT | – | CLOSED 2026-09'da hiç 1 değil; açık satır belirleyicisi fiilen AMOUNT>SHIPPEDAMOUNT. |
| **Sipariş sayısı** | #1 DBO_LG_{n0}_{n1}_ORFICHE: `COUNT(DISTINCT ORFICHE.LOGICALREF)`  (seed) | yok<br>Koşul: Sözleşmede yok | #15 ORFICHE TRCODE 1, iptal hariç | – | Eski seed tanımı TRCODE/CANCELLED süzgeci taşımıyor; proje kararı taşıyor. |
| **Ortalama fatura (sepet) tutarı** | #1 DBO_LG_{n0}_{n1}_INVOICE: `AVG(INVOICE.NETTOTAL)` [INVOICE.TRCODE IN (7,8), INVOICE.TRCODE IN (7,8,9)] (claude-inceleme)<br>#1 LG_{n0}_{n1}_INVOICE: `AVG(INVOICE.NETTOTAL)` [INVOICE.TRCODE IN (7,8,9), INVOICE.CANCELLED IN (0)] (operator) | yok<br>Koşul: invoice_amount / invoice_count işlemiyle türetilebilir | - | – | Eski iki tanım: 7,8 ve 7,8,9 + CANCELLED; KDV dahil NETTOTAL. |
| **Aktif müşteri** | #1 LG_{n0}_CLCARD: `ACTIVE IN ['0']`  (rule-miner) | `active_customers`: `COUNT_BIG(*)` — CRM AccountBase statecode=0 ve Aktif Müşteri durum nedeni; potansiyel, pasif, arşiv ve sorunlu müşteri statüleri dahil değildir.<br>Koşul: CRM AccountBase statecode=0 + 'Aktif Müşteri' durum nedeni | - | – | Eski: Logo CLCARD.ACTIVE=0 (kart kullanımda; 229.591 kart). Motor: CRM aktif müşteri (11.904). Farklı sistem ve anlam. |
| **Kanal** | #1 DBO_LG_{n0}_CLCARD: `SPECODE2 COLUMN `  (operator) | `channel`: `` — Logo müşteri kartı SPECODE2 satış kanalı<br>Koşul: CLCARD.SPECODE2 | #05 | – | Uyumlu. |
| **Gider** | #1 LG_{n0}_{n1}_EMFLINE: `SUM(EMFLINE.DEBIT - EMFLINE.CREDIT)` [EMFLINE.CANCELLED IN (0), EMFLINE.ACCOUNTCODE LIKE '7%'] (operator) | yok<br>Koşul: Sözleşmede yok | Kural 16: EMFLINE ACCOUNTCODE LIKE '7%', DEBIT−CREDIT | – | Motorda yok. |

## 7. Açık sorular

1. Fatura sayısı kapsamı: motor 7/8/9, proje KPI ve eski sertifika 2/3/7/8/9. Hangisi resmi? (Eylül 2026 farkı 120 belge.)
2. Net ciroda hizmet satırları (LINETYPE 4) ve TRCODE 9 dışarıda kalsın mı? Motor etiketi '7/8/9' diyor ama 9 hiçbir zaman LINETYPE 0 değil.
3. TRCODE 3 içindeki büyük hizmet iade satırı (2026-09: 1,28 Mn ₺, LINETYPE 4) iade/net ciroya girmeli mi?
4. STLINE.BILLED ile INVOICEREF tutarsız satırlar (TRCODE 7: 354) — faturalı satır ölçütü INVOICEREF mi kalsın?
5. PAYTRANS.FICHELINEREF hedefi doğrulanamadı (206 dolu satır; CLFLINE'a ters eşleşme 0).
6. BNFLINE MODULENR 61/62/65 ve CLFLINE/PAYTRANS MODULENR 61 anlamı LDDS'de yok.
7. BANKACC.CARDTYPE 5, CLCARD.CARDTYPE 4/22, ITEMS.CARDTYPE 22, PRCLIST.PTYPE 4, SPECODES.CODETYPE 10 LDDS'de tanımsız.
8. CSCARD.CURRSTAT için LDDS etiketleri proje kuralıyla (Kural 12) çelişiyor; proje kuralı veriyle doğrulanmış kabul edildi.
9. OUTCOST 2026-07 sonrası boş: maliyetlendirme ne zaman çalıştırılacak? Kâr/marj soruları o zamana kadar dürüst 'hesaplanamaz' döner.
10. Özel görünümlerin SQL tanımları okunamıyor (VIEW DEFINITION izni yok). V_SatisRaporu_411'in 'Net Tutar' tanımı motorla karşılaştırılamadı.
11. SPECODES.SPECODETYPE 24 (7.405 kod) ve 26 (cari kart özel kodları) LDDS listesinde yok; 24'ün hangi kayıt türüne ait olduğu doğrulanmadı.
12. LG_411_01_STLINE_yedek1 (1,14 Mn satır), LG_411_01_STLINE_20260430_RETAMOUNT ve BCKP_030826LG_411_01_STLINE yedek kopyaları sorgu kapsamından açıkça dışlanmalı.

## Ek: dosyalar ve yeniden üretim

- Ölçüm betikleri (sunucu): `/tmp/claude-fin88/sozluk/{measure,extra,views,viewcols,refs,refs2,build,md}.py`; ham ölçümler `measure.json`, `extra.json`, `views.json`, `refs.json`.
- Eski katalog çıkarımı: `pg_restore -a -t sl_concept|sl_mapping|sl_vocabulary|sl_evidence -f -` (yedek dosyasından stdout'a; hiçbir DB'ye geri yükleme yapılmadı).
- Kaynak öncelikleri: elle doğrulanmış anlam > LDDS > eski sertifikalı eşleme > TİMAŞ görünüm takma adı > ad çıkarımı (`tahmin`).
