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

## Müşterinin "alması" — alan / almış / alıp / satın alan müşteri
Müşteri bizden **satın almıştır** = adına satış faturası kesilmiştir (INVOICE TRCODE 7, 8, 9; iptal hariç). "Geçen yıl alıp" = geçen yıl satış faturası olan cari. Alım (TRCODE 1) tedarikçiden bizim alımımızdır, müşterinin alması değil.

## Kaybedilen müşteri
Geçen dönemde satış faturası olan, bu dönemde hiç satış faturası **olmayan** cari (müşteri düzeyinde yokluk, NOT EXISTS); yanına geçen dönem cirosu yazılır. "Bu yıl hiç sipariş vermemiş" dendiğinde sipariş fişi (LG_ORFICHE TRCODE 1) aranır — sipariş modülü tüm satışları kapsamadığı için cevapta "sipariş" ölçütü olduğu belirtilir.

