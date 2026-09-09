# Ajan için kısa kurallar (Logo / TİMAŞ, 2026) — tam kurallar knowledge/rules/ altındadır
1. Her belge/hareket sorgusunda "CANCELLED" = 0. Bu kurulum tek şirketin yıllar içindeki yedek/anlık görüntü kaynaklarını kullanır. Teknik kaynak kodlarından ayrı şirket üretme; yıl kapsamını doğrulanmış kaynak metaverisinden belirle.
2. Satış = INVOICE."TRCODE" IN (7,8,9); satış iadesi = (2,3); net ciro = satış − iade; satınalma = (1,4). Tutar INVOICE."NETTOTAL" (TL, KDV dahil), tarih "DATE_".
3. Satır analizi STLINE: LINETYPE 0 malzeme satırı (adet "AMOUNT", tutar "TOTAL" iskonto öncesi), LINETYPE 2 iskonto satırı; maliyet = AMOUNT*OUTCOST yalnız OUTCOST <> 0; brüt marj = 1 − Σmaliyet/ΣTOTAL.
4. Kanal = CLCARD."SPECODE2" (boş → '(boş)'); yayınevi = ITEMS."SPECODE"; unvan = CLCARD."DEFINITION_"; müşteri/tedarikçi kırılımında CLCARD."CODE" ile grupla ve unvanı yanında göster.
5. Ay kovası: DATEFROMPARTS(YEAR("DATE_"), MONTH("DATE_"), 1) AS ay (GROUP BY aynı ifade); EXTRACT/DATE_TRUNC/DATE_PART çalışmaz.
6. "ilk N / en çok N" → SELECT TOP N … ORDER BY; T-SQL: LIMIT yok, GROUP BY'da takma ad yok, bölmede NULLIF(...,0).
7. Oran/pay 0–1 kesir olarak döner; yalnız soru "yüzde" derse ×100. Başlık (INVOICE/ORFICHE) sayarken satır tablosuna JOIN yapma; grup ortalaması aynı GROUP BY içinde.
8. Hazır nesneler: v_monthly_sales (yil, ay, satis, iade, net_ciro), v_channel_net, v_imprint_perf; sales_cube, line_cube, orders_cube. Uyan varsa ham tabloya inme.
