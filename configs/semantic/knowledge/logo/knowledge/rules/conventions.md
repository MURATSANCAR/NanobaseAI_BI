# Katalog kuralları — enrich-context (2026-09-06)

Kolon/enum/varsayılan filtre boşluklarını kapatmak için yazılmıştır; `logo-erp.md`'deki kurallar değiştirilmemiştir.

## Default filters
- Belge/hareket modellerinde (INVOICE, STLINE, ORFICHE, ORFLINE, CLFLINE) `CANCELLED = 0` varsayılan filtredir; iptal belgeleri yalnız açıkça sorulursa dahil et.
- Açık sipariş = `ORFLINE.CANCELLED = 0 AND CLOSED = 0 AND AMOUNT > SHIPPEDAMOUNT`.
- Ürün / yayınevi / adet analizinde `STLINE.LINETYPE = 0` (malzeme satırı) varsayılan; iskonto satırları (LINETYPE 2) yalnız iskonto sorularında.
- Maliyet / marj hesabında `OUTCOST <> 0` (maliyetlendirilmiş satır) varsayılan; OUTCOST = 0 satırlar marja girmez.
- Yıl belirtilmeyen sorular 2026 YTD'dir (`DATE_ >= '2026-01-01'`); veri kesiti Ağustos 2026 (kısmi ay).

## Naming conventions
- "ciro / satış tutarı" = `INVOICE.NETTOTAL`, TRCODE IN (7,8,9); "net ciro" = satış − satış iadesi (TRCODE 2,3). "satır bazlı ciro / yayınevi cirosu" = `STLINE.TOTAL`, LINETYPE 0.
- "KDV hariç ciro" = `NETTOTAL − TOTALVAT` (NETTOTAL KDV dahildir; 2026'da KDV payı ≈ %0,5).
- "kanal / satış kanalı" = faturanın carisindeki `CLCARD.SPECODE2`; boş = '(boş)'. "Kanal payı" = kanal net cirosu / TÜM kanalların pozitif net ciro toplamı (yalnız seçili kanalların toplamı değil).
- "yayınevi / imprint / dizi" = `ITEMS.SPECODE`; değerler 10 karakterde kesiktir ("Timaş Çocu" = Timaş Çocuk) — gruplarken kesik değeri olduğu gibi kullan.
- "başlık" = hareket görmüş farklı malzeme sayısı `COUNT(DISTINCT STLINE.STOCKREF)`; kitap adı değildir.
- "unvan / müşteri adı / tedarikçi adı" = `CLCARD.DEFINITION_` (NAME değil); "cari kodu" = `CLCARD.CODE`. Müşteri/tedarikçi kırılımında `CODE` (veya LOGICALREF) ile grupla ve unvanı yanında göster — yalnız unvanla gruplama aynı unvanlı carileri birleştirir.
- "kitap adı" = `ITEMS.NAME`; "stok kodu" = `ITEMS.CODE`.
- "adet" = `STLINE.AMOUNT` (LINETYPE 0); "iade oranı (adet)" = Σ AMOUNT (TRCODE 2,3) / Σ AMOUNT (7,8); "iade oranı (tutar)" = Σ NETTOTAL (2,3) / Σ NETTOTAL (7,8,9).
- "satınalma" = TRCODE 1 (mal alım) + 4 (alınan hizmet); alım iadesi (6) düşülmez.
- "sipariş sayısı" = `COUNT(DISTINCT ORFICHE.LOGICALREF)`; "sipariş tutarı" = `ORFICHE.NETTOTAL` (ORFLINE.TOTAL değil).
- "brüt kâr marjı / marj" = iskonto öncesi brüt marj: 1 − Σ(AMOUNT × OUTCOST) / Σ TOTAL, LINETYPE 0, OUTCOST ≠ 0.
- Oran/pay sözleşmesi: `*_orani` 0–1 kesir; `*_yuzde` ya da soruda "yüzde" geçiyorsa 0–100. Soru "yüzde" demiyorsa kesir döndür ve kolonu `_orani` diye adlandır.
- Ay kovası: `DATEFROMPARTS(YEAR("DATE_"), MONTH("DATE_"), 1)` ve kolon adı `ay`; ay adı gerekiyorsa uygulama tarafı çevirir.

## External identifiers
- `LOGICALREF` kaynak anlık görüntüsü içindeki dahili anahtardır. Başka yedekte aynı numaranın bulunması tek başına aynı kaydı kanıtlamaz. Kaynaklar arası varlık eşleştirmesinde doğrulanmış iş anahtarları ve ilişkiler kullanılmalıdır. Bu teknik ayrım ayrı şirketler olduğu anlamına gelmez.
- `*REF` kolonlarında (SALESMANREF, PROJECTREF, CLIENTREF, STOCKREF…) boş değer `0`'dır, NULL değil; `LEFT JOIN … ON x.REF = y.LOGICALREF` 0 için eşleşmez, saymak için `REF <> 0` kullan.
- e-Fatura alanları (EINVOICE, PROFILEID, ESTATUS) yalnız bayraktır; GİB / dış sistem kimlik eşlemesi bu projede tanımlı değildir.

## Currency
- Tüm tutar kolonları TL'dir: INVOICE.NETTOTAL/GROSSTOTAL/TOTALVAT, STLINE.TOTAL/PRICE/OUTCOST, ORFICHE.NETTOTAL, ORFLINE.TOTAL, CLFLINE.AMOUNT. Döviz belgelerinde (TRCURR ≠ 0; 2026'da 74 fatura) TL karşılığı bu kolonlardadır, döviz tutarı TRNET, kur TRRATE. Toplamlarda TL kolonlarını kullan; kurla çarpma/çevirme yapma, TRNET'i toplama.
- REPORTNET / REPORTRATE Logo raporlama dövizidir; analizde kullanma.
- Gösterim: TL, 2 ondalık, binlik ayırıcı (tr-TR); ekranda ₺ kısaltmaları (₺M, ₺Mr).
- KDV: NETTOTAL KDV dahil; STLINE.TOTAL KDV hariç (satır KDV'si VATAMNT). Marj/iskonto oranları KDV hariç satır tutarlarından, ciro KDV dahil başlıktan hesaplanır — ikisini karıştırma.

## Canonical tables
- Tek şirket vardır; farklı veri kaynakları yıllar içindeki yedek/anlık görüntülerdir. Tablo önekleri şirket kimliği değildir. Yıl kapsamı ve yedek önceliği doğrulanmış kaynak eşlemesinden alınmalıdır. Örtüşen yedekler ayrı şirketler gibi toplanamaz; yalnız tablo adı veya tek bir ileri tarihli kayıttan kaynak dönemi çıkarılamaz.
- Ciro/satış/iade/alım için fatura başlığı `dbo_LG_411_01_INVOICE` kanoniktir; sipariş modülü (`ORFICHE`) tüm satışları kapsamaz, sipariş dışında ciro için kullanma. Ürün / yayınevi / adet / marj için `dbo_LG_411_01_STLINE`.
- Hazır nesneler: aylık seri `v_monthly_sales`, kanal `v_channel_net`, yayınevi `v_imprint_perf`; ölçüler `sales_cube`, `line_cube`. SQL Server'da küp kırılımı (dimensions) upstream hatası verir — kırılım için görünümleri kullan, küpleri yalnız toplam ölçü için.
- Cari hareket `dbo_LG_411_01_CLFLINE` borç/alacak analizine uygundur; ancak `PAYTRANS.PAID` beslenmez (vade/yaşlandırma yapılamaz) ve `STINVTOT` boştur (stok STLINE'dan hesaplanır) — bunları kaynak olarak önerme.
- **Satır düzeyinde satış tutarı = `STLINE.LINENET`** (iskonto sonrası net satır tutarı). `STLINE.TOTAL` iskonto öncesi brüt liste tutarıdır; ciro, kâr, zarar, "maliyetin altında satış" gibi hesaplarda **kullanılmaz** (toptanda iskonto ~%46 olduğu için sonucu iki kat şaşırtır). Fatura başlığı (`INVOICE.NETTOTAL`) satır maliyetiyle aynı sorguda toplanmaz; satır hesabı satırda kalır. Satış satırları `TRCODE IN (7, 8, 9)` (9 dahil), `LINETYPE = 0`, `CANCELLED = 0`. Maliyet `STLINE.AMOUNT × STLINE.OUTCOST`; `OUTCOST = 0` satırlar maliyeti girilmemiş satırlardır, sayıları cevapta yazılır.
- Tam sayı (`int`) sütunları toplarken taşma olur: `SUM(CAST(sutun AS BIGINT))` yaz (CRM `new_UretimAdedi`, `new_OnerilenBaskiAdeti` gibi adet sütunları; Logo `AMOUNT` ondalıklıdır, gerekmez).
- Oran/pay bir dönem kırılımıyla soruluyorsa ("son iki yılda nasıl değişti", "yıl bazında oranı") pay ve payda **aynı dönem penceresinde** hesaplanır: her yılın payı o yılın toplamına bölünür; iki yıllık sabit payda kullanılmaz. "Son iki yıl" kırılımı yıl bazındadır (ay değil); değişim = son yıl − önceki yıl.
- **Payın paydası**: "X olanların payı/oranı" sorusunda payda, X koşulu KALDIRILMIŞ aynı varlık kümesidir (aktif bütün kayıtlar). X bir alt tabloda duruyorsa (sözleşmenin tarafı, siparişin satırı) sayılan varlık ana tablodan okunur ve alt tablo `LEFT JOIN` ile, kendi varsayılan filtresi `ON` içinde bağlanır: `COUNT(DISTINCT CASE WHEN alt.kosul THEN ana.id END) / COUNT(DISTINCT ana.id)`. Alt tablodan sayılan ya da `INNER JOIN`/`WHERE alt.…` ile yazılan payda, alt satırı hiç olmayan kayıtları düşürür ve oranı şişirir. Dönem kırılımı da sayılan varlığın KENDİ tarihinden alınır (alt satırın kayıt tarihinden değil).
- Tablonun satırlarına verildiği adla (FROM'daki ad ya da takma ad) başvur; `FROM Timas_MSCRM_dbo_NEW_X` yazıp sütunu `NEW_X.kolon` diye niteleme.
