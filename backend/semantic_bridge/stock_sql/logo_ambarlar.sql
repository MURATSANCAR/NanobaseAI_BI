-- Logo ambar tanımları (Kural 14): numara, ad, maliyet grubu. CRM depo kartının `new_ambarmaliyetgrubu` alanı bu COSTGRP'tir.
SELECT NR AS ambar_no, NAME AS ambar_adi, COSTGRP AS maliyet_grubu
FROM dbo.L_CAPIWHOUSE
WHERE FIRMNR = {firma_nr}
