# Metrik tanımları (doğrulanmış, 2026-09-06)

## net_ciro
Σ NETTOTAL (TRCODE 7,8,9) − Σ NETTOTAL (TRCODE 2,3), CANCELLED = 0. Kaynak dbo_LG_411_01_INVOICE. Cube: sales_cube.net_ciro. Görünüm: v_monthly_sales.net_ciro.

## iade_orani
Σ NETTOTAL (2,3) / Σ NETTOTAL (7,8,9).

## iskonto_yuku
Σ TOTAL (LINETYPE 2) / Σ TOTAL (LINETYPE 0), TRCODE 7,8. Kaynak dbo_LG_411_01_STLINE. Cube: line_cube.iskonto / line_cube.brut_satir.

## brut_kar_marji
1 − Σ(AMOUNT × OUTCOST) / Σ TOTAL, LINETYPE 0, TRCODE 7,8, OUTCOST ≠ 0 (iskonto öncesi brüt marj). Cube: 1 − line_cube.maliyet / line_cube.maliyetli_ciro.

## satinalma
Σ NETTOTAL (TRCODE 1,4). Cube: sales_cube.alim.

## siparis_sayisi
COUNT(DISTINCT dbo_LG_411_01_ORFICHE.LOGICALREF), CANCELLED = 0; tutar = ORFICHE.NETTOTAL.

## kanal_net_ciro
Görünüm v_channel_net; cari kartı SPECODE2 üzerinden.

## yayinevi_performans
Görünüm v_imprint_perf: net_ciro (satır bazlı), satilan_adet, iade_adet, maliyetli_ciro, maliyet.

## ortalama_tahsilat_suresi_gerceklesen
AVG(DATEDIFF(gün, fatura tarihi, kapatan ödemenin tarihi)); kaynak PAYTRANS (MODULENR 4, SIGN 0, CANCELLED 0) ödeme planı satırı, kapatan ödeme CROSSREF ile bağlı ikinci PAYTRANS satırı, fatura INVOICE (TRCODE 7,8,9; CANCELLED 0). Yalnız kapanmış kalemler. Eş anlamlı: ortalama tahsilat vadesi (gerçekleşen), tahsilat süresi, alacak devir günü, DSO. İş teyidi bekliyor (2026-09-16).

## planlanan_odeme_vadesi
AVG(DATEDIFF(gün, fatura tarihi, PAYTRANS.DATE_)); PAYTRANS MODULENR 4, SIGN 0, CANCELLED 0; INVOICE TRCODE 7,8,9. Eş anlamlı: ödeme vadesi, vade günü, anlaşılan vade. İş teyidi bekliyor (2026-09-16).

### Kâr (müşteri / ürün bazında) — iş teyidi bekliyor
- Tanım: satış satırının **net tutarı** eksi satılan malın maliyeti: `STLINE.LINENET − STLINE.AMOUNT × STLINE.OUTCOST`; satış satırları TRCODE 7/8/9, `LINETYPE = 0`, `CANCELLED = 0`. İadeler (TRCODE 2/3) net satıştan düşülür.
- `STLINE.TOTAL` **kullanılmaz**: iskonto öncesi brüt tutardır; toptan satışta iskonto ~%46 olduğu için kârı yaklaşık iki kat gösterir. Fatura başlığı `NETTOTAL` da satır maliyetiyle çarpılınca satır sayısı kadar şişer; kâr satır düzeyinde hesaplanır.
- Veri notu (ölçüm 2026-09-16): 2026 satış satırlarının %20'sinde `OUTCOST = 0` (maliyet girilmemiş); cevapta bu satırların sayısı yazılmalı.
- "en çok kâr bıraktığımız müşteriler" = cari (`CLCARD`) bazında bu farkın toplamı, azalan sırada.

### Stok bakiyesi ("elimizde kalan", "stokta") — iş teyidi bekliyor
- Tanım: malzeme bazında `SUM(CASE WHEN STLINE.IOCODE IN (1,2) THEN STLINE.AMOUNT ELSE -STLINE.AMOUNT END)`; `LINETYPE = 0`, `CANCELLED = 0`, `IOCODE IN (1,2,3,4)` (1/2 giriş, 3/4 çıkış). `STINVTOT` boştur, stok STLINE'dan hesaplanır.
- Dönemsiz **durum** ölçüsüdür: 2026 kopyası devir satırlarıyla (TRCODE 14, 28.088 satır) başlar; stok yalnız güncel kopyadan, tarih filtresiz hesaplanır. "Elimizde hiç kalmamış" = bakiye ≤ 0; hiç hareketi olmayan malzemenin bakiyesi 0 sayılır (LEFT JOIN + ISNULL(...,0)), dışarıda bırakılmaz. Stok ve sipariş gibi iki çoklu ilişki aynı sorguda toplanmaz: her biri kendi alt sorgusunda malzeme bazında toplanır, sonra STOCKREF üzerinden birleştirilir.

### Bekleyen (açık) sipariş — iş teyidi bekliyor
- Satış siparişi satırı `LG_ORFLINE` (`TRCODE = 1`), kapanmamış `CLOSED = 0`, `CANCELLED = 0`, `LINETYPE = 0`; bekleyen miktar `AMOUNT − SHIPPEDAMOUNT`. Kitap/ürün bağı `ORFLINE.STOCKREF = ITEMS.LOGICALREF`.
- "Bekleyen siparişi olan kitaplar" = bu satırları olan malzemeler; CRM'deki "bekleyen ürün" (müşteri talebi kaydı) ayrı bir kavramdır, soru Logo stok/sipariş dediğinde kullanılmaz.

### Stok devir hızı — iş kararı 2026-09-20 (katalogda sertifikalı ölçü: «stok devir hızı»)
- Tanım: dönem satış adedi / ortalama stok. Günlük stok bakiyesi tutulmadığı için ortalama stok = (dönem başı stok + dönem sonu stok) / 2; dönem başı = devir satırları (TRCODE 14), dönem sonu = güncel stok bakiyesi. Satış adedi satış faturası satırlarından (TRCODE 7/8/9).
- Stok bakiyesi ile satış adedi aynı WHERE'de hesaplanmaz: stok filtresiz (tüm IOCODE, tarih yok), satış dönemli — iki ayrı alt sorgu, STOCKREF üzerinden birleştirme. Aksi halde stok = −satış çıkar.
- Tek ifadeyle de yazılır (katalogdaki formül): WHERE yalnız `LINETYPE = 0`, `CANCELLED = 0` taşır; satış, açılış ve bakiye aynı okumada **koşullu toplam**dır — `SUM(CASE WHEN TRCODE IN (7,8,9) THEN AMOUNT END) / NULLIF((SUM(CASE WHEN TRCODE = 14 THEN AMOUNT END) + SUM(CASE WHEN IOCODE IN (1,2) THEN AMOUNT WHEN IOCODE IN (3,4) THEN -AMOUNT END)) / 2.0, 0)`. Payda dönem sonu stok DEĞİL ortalama stoktur (açılış + güncel) / 2; yalnız güncel kopyadan okunur (kopya = yıl). Canlıda üç alt sorgulu referansla 20/20 birebir (İYİLİK TİMİ 1,09).
- CRM `PRODUCTBASE.NEW_SATISHIZI` **satış hızı**dır; devir hızı sorusu onunla cevaplanmaz.
