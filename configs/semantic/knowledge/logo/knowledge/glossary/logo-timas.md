# Sözlük — Logo ERP / TİMAŞ

## Ciro / Net ciro
Satış faturalarının (TRCODE 7 perakende, 8 toptan, 9 verilen hizmet) NETTOTAL toplamı = satış; net ciro = satış − satış iadesi (TRCODE 2, 3). KDV dahildir.

## Satış iadesi
TRCODE 2 (perakende iade) ve 3 (toptan iade) faturaları; iade oranı = iade / satış.

## Satınalma
Mal alım (TRCODE 1) + alınan hizmet (TRCODE 4). Alım iadesi TRCODE 6 ayrıdır.

## Kanal
Cari kartındaki SPECODE2: KITAPCI, E-TICARET, DAGITICI, ZINCIR, KURUM, MAGAZA, FUAR; boş kod "(boş)".

## Yayınevi (imprint)
Malzeme kartındaki SPECODE (ITEMS.SPECODE); "Timaş Çocu", "İlk Genç T", "Genç Timaş" gibi.

## Başlık
Belirli dönemde hareket görmüş farklı malzeme (STOCKREF) sayısı.

## İskonto satırı
STLINE LINETYPE 2 satırları; TOTAL iskonto tutarıdır. Malzeme satırı LINETYPE 0.

## Maliyetlendirme
OUTCOST birim maliyet; Logo maliyetlendirme aylık gecikmeli çalışır, OUTCOST = 0 satırlar maliyetlendirilmemiştir.
