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
