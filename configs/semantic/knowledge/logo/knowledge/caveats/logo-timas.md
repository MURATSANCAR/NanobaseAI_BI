# Veri uyarıları (Logo LOGO_DB, tek şirketin kaynakları)

- NETTOTAL KDV dahildir; 2026 satışlarında KDV payı ≈ %0,5 (KDV hariç ≈ 917,9 M TL).
- Fatura başlığı (INVOICE) ile hareket satırı (STLINE) toplamları arasında ≈ %0,6 fark vardır (hizmet satırları, yuvarlama); kartlar başlıktan, marj/iskonto satırdan hesaplanır.
- STLINE.TOTAL iskonto ÖNCESİ brüt tutardır; iskontolar ayrı satırlarda (LINETYPE 2). Marj iskonto öncesidir; iskonto sonrası marj ≈ %75.
- Maliyetlendirme 30.06.2026'ya kadar işlenmiştir; sonraki satırların OUTCOST = 0 → marj hesaplarına girmez (≈ 404 M TL satır cirosu maliyetsiz).
- TRCODE 6 (alım iadesi, ≈ 20 M TL) satınalma tutarından düşülmez.
- Döviz faturaları (TRCURR ≠ 0, 74 adet) TL karşılığıyla dahildir.
- Aylık/gruplu ortalama için bağımsız skaler alt sorgu yazma (her satıra aynı değeri döndürür); aynı GROUP BY veya CTE kullan.
- Başlık tablosundan sayım yaparken satır tablosuna JOIN etme veya COUNT(DISTINCT başlık.LOGICALREF) kullan (fan-out).
- Tek şirket vardır. Farklı kaynaklar yıllar içindeki yedeklerdir; teknik kodlar ayrı şirket değildir. Dönem kapsamı ve yedek önceliği doğrulanmış kaynak eşlemesinden belirlenir.
