# M9 Fiyatlama ve Maliyet — veri ölçümü, kararlar, sunucuda kabul planı (2026-09-28)

Kod dalda yazıldı; test sunucusuna erişim ağ katmanında kapalı olduğu için (kullanıcı kararı: sunucu sonra) pytest,
vitest, tsc, kurulum ve gerçek veriyle kabul **yapılmadı — DOĞRULANAMADI**. Mac'te yalnız `py_compile` ve JSON doğrulaması koştu.
Aşağıdaki ölçümler 2026-09-28 00:20–01:00 arasında test sunucusundan, doğrudan bağlantıyla (`connector_from_file`) yapıldı.

## Ölçülen (gerçek DB)

| Konu | Ölçüm | Kaynak |
|---|---|---|
| Baskı bedeli | Matbaa faturası alınan hizmet (INVOICE.TRCODE 4, STLINE.LINETYPE 4), hizmet kartı `730.38.381` «Komple Baskı Giderleri»; **satırın `SPECODE`'u kitabın stok kodu** (`15201.01.6505` …), `AMOUNT` basılan adet, `LINENET` KDV hariç tutar. 2025'te 2.481 satır / 93,9 Mn ₺; 2026'da 21 matbaa (WPC 16,4 Mn, Çınar 15,5 Mn, Deha 6,6 Mn …). Birim 5–75 ₺. | LG_211 / LG_411 |
| Kâğıt | Timaş kâğıdı kendi alır: `15001…` kartları satın alma faturasıyla (TRCODE 1). 3. hamur 60 gr ≈ 48 ₺/kg, bristol 230 gr ≈ 30 ₺/kg, bandrol `15001.000.000001.BD` 0,30 ₺/adet (2026). Matbaa faturası kâğıtsız. | LG_411 |
| Gerçekleşen birim maliyet | Satış satırı `OUTCOST` (örnek: 15201.01.6505 en çok 19,21 ₺; aynı kitabın komple baskı birimi 5,40 ₺ → fark kâğıt + üretim yüklemesi). 2026 toptan (TRCODE 8) satırların %81'i maliyetli. | LG_411 |
| Üretim | Üretimden giriş (TRCODE 13) 9.439 satır, sarf (TRCODE 12) 10.098 satır; üretim emri tablosu firma düzeyinde (`LG_411_PRODORD`, dönem öneki yok). İleri tarihli (2027) emirler var — plan. Bu sürümde kullanılmadı. | LG_411 |
| Telif | CRM `new_sozlesmeBase`: `new_telifturu` 1 Brüt / 2 Net / 3 Değişken; `new_TelifTipi` 1 Baskıdan, 2 Satıştan, 3 Tek ödeme, 4 Baskıdan kademeli, 5 Baskı+Satış, 6 Satış+Baskı, 7 Satıştan kademeli, 8 Diğer; en sık «Net + Tek ödeme» (7.404), «Brüt + Baskıdan» (2.940). Avans `new_sozlesmeavanstutari`, para birimi 1 = TL. | CRM .28 |
| Kapak fiyatı | CRM üretim kaydı `new_kesinlesenbaskifiyati` baskının etiket fiyatıdır (maliyet değil): 85–900 ₺, hep 5'in katı; 2019–2026 her yıl 1.350–1.750 kayıtta dolu. Kitap kartı `new_kdvdahilfiyat` 9.675 kitapta dolu. | CRM .28 |
| KDV | CRM kitap kartında `new_kdvorani` 12.273 kitapta 0, 586'sında 10, 496'sında 20. | CRM .28 |
| Ebat | Kitap kartı `new_Ebat` serbest metin («13,5x21», «13,5*19,5»), 8.959 kitapta dolu. | CRM .28 |
| Logo tazeliği | .155 donmuş kopya, son fatura 2026-08-17 — ekran «veri sonu»nu yazar. | LG_411 |

## Kararlar (veriye bakılarak, gerekçeli)

1. **Birim maliyet = baskı hizmeti + kâğıt/kapak/bandrol**, baskı hizmeti emsallerden c(Q) = a + b/Q (sayfa başına, son 12 ay faturaları), kâğıt fiziksel (yaprak × ebat × gramaj × ₺/kg). Fire %10 ve kapak alanı katsayısı 2,3 ölçülemedi → varsayım, ekranda yazılı ve değiştirilebilir.
2. **Gerçekleşen marj** Logo'nun kendi maliyetiyle: net satış − Σ adet × OUTCOST; maliyetsiz satır marja girmez, oranı gösterilir. Telif ve genel gider brüt kâra dahil değil (ekranda yazılı).
3. **Kanal** = cari kartın grup kodu (`CLCARD.SPECODE2`, katalog kuralı «müşteri grubu / kanal»). Kitabevi / okul / e-ticaret / toplu satış eşlemesi bu kodların adlarından çıkar; eşleme tablosu yok, kod adıyla gösterilir.
4. **Telif** CRM sözleşmesinden: «baskıdan» tipler (1, 4, 5) basılan adet, diğerleri satılan adet üzerinden; «Tek ödeme» oran 0, avans sabit gider. Yabancı para avansı kur bilinmediği için TL kutusuna eklenmez, ekran uyarır.
5. **Rakip/e-ticaret fiyatı** taranmaz (bot korumalı siteler, izinli kanal yok); ekip elle girer, kaynağı ve günü tutulur, emsal bandına katılır.
6. **Backlist hedef oranı** = son 12 ayda ilk baskısı yapılan kitapların (maliyet ÷ KDV hariç kapak fiyatı) ortancası — bugünkü fiyatlama pratiği. Satış hızının fiyata tepkisi (esneklik) ölçülmedi; öneri maliyet tarafıdır (ekranda yazılı).
7. Onaylanan fiyat CRM'e yazılmaz (Web API yetkisi yok); ekran «CRM kitap kartına ayrıca girin» der.

## Sunucuda doğrulanacaklar (kod bu varsayımlarla yazıldı)

- `crm_kitap`: `new_markaBase` ↔ `new_kitapBase.new_yayinciid` ve `new_kitaplikBase` ↔ `new_kitapBase.new_kitaplikid` birleşimleri (M2'de proje tarafı `new_yayinciid`/`new_Kitaplik` idi; kitap tarafı ölçülmedi). Hata verirse yalnız bu iki JOIN düzeltilir.
- `crm_secenek`: StringMap birden çok dilde satır dönerse ilk gelen alınır — Türkçe ad geldiği denetlenir.
- `logo_baski` 211 kopyasında hizmet kartı adı da «Komple Baskı…» mı (`SC.DEFINITION_ LIKE N'Komple Bask%'`); 2025 dökümünde `730.38.381` vardı.
- `logo_kanal`: `TOTAL` = adet × KDV hariç liste fiyatı mı — bir kitapta `TOTAL/AMOUNT` ile CRM `new_kdvdahilfiyat/(1+KDV)` karşılaştırılır.
- Logo satış satırında KDV (`STLINE.VAT`) dağılımı CRM KDV'siyle tutarlı mı.
- Görüntü kurulum süresi (satış sorgusu 211'de beş yılı tarar; zaman aşımı `PRICING_QUERY_TIMEOUT_SEC` 900).

## Kabul sorguları (bağımsız referans, doğrudan bağlantı)

Ekranın/uçların verdiği rakam aşağıdakilerle birebir karşılaştırılır (`/tmp/claude-m9` altında, salt okunur):

```sql
-- 1) Bir kitabın matbaa faturaları (ekran: Kitap hesabı › Baskı geçmişi, Gerçekleşen › Basılan / Baskı bedeli)
SELECT CONVERT(date, I.DATE_) tarih, I.FICHENO, C.DEFINITION_ matbaa, SUM(S.AMOUNT) adet, SUM(S.LINENET) tutar
FROM LG_411_01_STLINE S JOIN LG_411_01_INVOICE I ON I.LOGICALREF = S.INVOICEREF
JOIN LG_411_SRVCARD SC ON SC.LOGICALREF = S.STOCKREF LEFT JOIN LG_411_CLCARD C ON C.LOGICALREF = I.CLIENTREF
WHERE I.CANCELLED = 0 AND S.CANCELLED = 0 AND I.TRCODE = 4 AND S.LINETYPE = 4 AND SC.CODE = '730.38.381'
  AND S.SPECODE = '15201.01.6505' GROUP BY CONVERT(date, I.DATE_), I.FICHENO, C.DEFINITION_;

-- 2) Aynı kitabın 2026 satışı ve Logo maliyeti (ekran: Gerçekleşen satırı; beklenen 2026: 13.394 adet satış, net 1.154.606,58 − iadeler)
SELECT SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE -S.AMOUNT END) adet,
       SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.LINENET ELSE -S.LINENET END) net,
       SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT * S.OUTCOST ELSE 0 END) maliyet
FROM LG_411_01_STLINE S JOIN LG_411_ITEMS IT ON IT.LOGICALREF = S.STOCKREF
WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.TRCODE IN (2,3,7,8,9) AND S.INVOICEREF <> 0 AND IT.CODE = '15201.01.6505';

-- 3) Kanal iskontosu (ekran: Veri ve varsayımlar › Kanal iskontoları)
SELECT C.SPECODE2, SUM(S.TOTAL) brut, SUM(S.LINENET) net, 1 - SUM(S.LINENET) / NULLIF(SUM(S.TOTAL), 0) iskonto
FROM LG_411_01_STLINE S JOIN LG_411_ITEMS IT ON IT.LOGICALREF = S.STOCKREF LEFT JOIN LG_411_CLCARD C ON C.LOGICALREF = S.CLIENTREF
WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.TRCODE IN (7,8) AND S.INVOICEREF <> 0 AND IT.CODE LIKE '152%'
  AND S.DATE_ >= '20250817' GROUP BY C.SPECODE2;   -- + 211 kopyasından 2025-08-17…2025-12-31

-- 4) Kâğıt ₺/kg (ekran: Veri ve varsayımlar › Kâğıt)
SELECT IT.CODE, IT.NAME, SUM(S.AMOUNT) kg, SUM(S.LINENET) tutar, SUM(S.LINENET) / SUM(S.AMOUNT) tl_kg
FROM LG_411_01_STLINE S JOIN LG_411_01_INVOICE I ON I.LOGICALREF = S.INVOICEREF JOIN LG_411_ITEMS IT ON IT.LOGICALREF = S.STOCKREF
WHERE I.CANCELLED = 0 AND S.CANCELLED = 0 AND I.TRCODE = 1 AND S.LINETYPE = 0 AND IT.CODE LIKE '15001%' AND I.DATE_ >= '20260215'
GROUP BY IT.CODE, IT.NAME;

-- 5) Telif (CRM; ekran: Kitap hesabı › Telif kutusu)
SELECT k.new_name, k.new_StokKodu, s.new_Telif, s.new_telifturu, s.new_TelifTipi, s.new_sozlesmeavanstutari, s.new_sozlesmeparabirimi
FROM new_kitapBase k JOIN new_sozlesmeBase s ON s.new_sozlesmeId = k.new_aktifsozlesmeid
WHERE k.new_StokKodu = '15201.01.6505';
```

Ek denetim: bir kitapta «Kâğıt + baskı hizmeti» önerisinin Logo `OUTCOST`'a yakınlığı (kâğıt hesabının doğrulaması); fark %25'i aşarsa fire/kapak varsayımı gözden geçirilir.

## Kurulum notları (erişim dönünce)

1. `main`e taşıma (paralel M10/M12/M46 taşımalarıyla; `navModel.ts`, `access_catalog.json`, `access.py`, `App.tsx`, `app.py`, `ModulesMenu.tsx` ortak dosyalar — üç yollu birleştirme).
2. Test sunucusu: yalnız değişen dosyalar, tek ssh bağlantısı (`ControlPath`), `git archive` akışı. Paylaşılan dosyalarda sunucu hâli + yalnız M9 farkı (M8/M7 dersi). Veri klasörü: `sudo install -d -o administrator /data/nanobaseai/bi/var/pricing`.
3. Aday ağaçta: `pytest backend/semantic_layer/tests/test_pricing_*.py test_access.py` + tam paket, `tsc -b`, `vitest` (menü ↔ yetki kataloğu dahil), `VITE_BASE=/timas/ VITE_ENGINE_BASE=/timas npm run build`.
4. Köprü: yeni paket import'u ve `app.py` değişikliği için köprünün yeniden başlaması gerekir (reload uçları yeni rota eklemez) — başka oturumun uçuştaki işi denetlenerek.
5. İlk istekte görüntü kurulur; süre ve kaynak satır sayıları `/api/v1/pricing/sources`'tan okunur. Kabul: yukarıdaki beş sorgu + kısa ömürlü `timasai` oturumuyla uçlar (overview, books, calc, analiz aç → onaya gönder → imza 403/409 denetimleri, actuals, backlist, proposals); test kayıtları silinir. `._*` sayısı 0.
6. Müşteri VM'ine kurulmaz (kullanıcı talimatı).
