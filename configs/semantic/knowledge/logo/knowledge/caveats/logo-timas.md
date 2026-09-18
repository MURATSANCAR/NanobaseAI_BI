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
- **Açık alacak / alacak yaşlandırması bu veride fatura bazında yapılamaz (ölçüm 2026-09-16).** Logo yaşlandırması ödeme planı satırlarının kapatılmasına (PAYTRANS.CROSSREF / PAID, "borç kapama") dayanır. 2026 kopyasında (LG_411) fatura plan satırlarının hiçbiri kapatılmamış (70.521 satırın 0'ı); 2021–2025 kopyasında açık görünen plan satırları toplamı (≈ 647 M TL) cari net bakiyeyle (≈ 117,5 M TL) uyuşmuyor. Bu yüzden "vadesi geçen alacak", "yaşlandırma", "30-60-90 gün" istendiğinde: fatura tutarlarını fatura tarihine göre yaşlandırıp "alacak" diye sunma (kesilen fatura ≠ alacak). Cevaplanabilir olan: cari bazlı net bakiye (CLFLINE borç − alacak, CANCELLED = 0); yaşlandırma yalnız 2021–2025 kopyasında ve yalnız kapatılmış plan satırlarıyla, kapsam eksikliği açıkça yazılarak. Bunlar sağlanamıyorsa NO_SQL: alacak yaşlandırması için borç kapama verisi yok.
- **Gerçekleşen tahsilat süresi 2026 için ölçülemez:** kapatan ödeme kaydı (CROSSREF) yok. Planlanan vade (PAYTRANS.DATE_ − fatura tarihi) hesaplanabilir; cevapta hangisinin verildiği yazılmalı.
- Asgari / azami stok seviyesi bu veride **tanımlı değil** (ölçüm 2026-09-18): `INVDEF.MINLEVEL` güncel kopyadaki 3,98 milyon malzeme–ambar satırının hiçbirinde sıfırdan büyük değil (seviye kontrolü açık 125.682 satırda da 0). "Asgari stok seviyesinin altına düşen malzemeler" sorusu bu yüzden boş döner; boş sonuç "hiçbir malzeme seviyenin altında değil" anlamına gelmez, seviye girilmemiştir.
- Cari risk limiti bu veride **tanımlı değil** (ölçüm 2026-09-18, doğrudan veritabanı): güncel kopyada (`LG_411_01_CLRNUMS`, 4.893 satır) ve 2021–25 kopyasında (237.228 satır) `ACCRISKLIMIT > 0` olan hiçbir cari yok. "Risk limitini aşan cariler" sorusu bu yüzden boş döner; boş sonuç "kimse limitini aşmadı" değil, "limit girilmemiş" demektir. (2015–2020 eski firma kopyalarında limitli kayıtlar vardır; güncel soruda okunmaz.)
- Karşılıksız / protestolu çek: güncel kopyada (`LG_411_01_CSCARD`) 2026 vadeli karşılıksız (CURRSTAT 11) ya da protestolu (5, 7) müşteri çeki **kayıt yok** (ölçüm 2026-09-18, doğrudan veritabanı); karşılıksız görünen 20 çek (2,52 M ₺) 2018–2019 vadelidir. "Bu yıl karşılıksız çıkan çekler" sorusu bu yüzden boş döner.

## CRM sözleşme tutar alanları boş

- `NEW_SOZLESMEBASE.new_teliftutari` ve `new_ajansservisucreti` bu kurulumda hiçbir sözleşmede dolu değil (14.824 aktif sözleşme, 0 dolu); telif hakediş tablosu `NEW_ODEMEHAKEDISBASE` boştur. "Ortalama telif tutarı", "ajans servis ücreti toplamı" soruları bu yüzden boş/NULL döner — veri yok, hesap hatası değil. Sözleşme adedi ve yüzde tabanlı telif (`new_Telif`, `NEW_TELIFTANIMBASE.new_TelifYuzdesi`) verilebilir.
- `NEW_URETIMBASE.new_UretimAdedi` hiç dolu değil; gerçekleşen üretim `NEW_BASKIBASE.new_uretimadedi` (39 kayıt).

## Telif hakedişi ve ödeme kaydı yok

- **Hakediş verisi yok:** telif hakediş / ödeme hakediş tablosu (`NEW_ODEMEHAKEDISBASE`) bu kurulumda hiç kayıt içermiyor (0 satır) ve taramada profili yok; "ödenmemiş hakediş", "dönemi kapanmış hakediş", "hakediş tutarı" soruları cevaplanamaz — veri girilmemiş. Ödeme dönemi kayıtları (`NEW_ODEMEDONEMIBASE`, 7 kayıt) var ama hakedişe bağlı değil.
- **Baskı işlemi / baskı maliyeti verisi eski:** `NEW_BASKIISLEMBASE` 2015–2017 (23 satır, birim fiyat 1 satırda dolu), `NEW_BASKIBASE` 2016–2018, satış senaryosu 2014 (4 satır). "Son bir yılda kitap başına baskı maliyeti", "birim fiyatı en çok artan işlem tipi" soruları bu yüzden boş döner — güncel veri yok.
- **Etkinlik yazarı yok:** etkinlik–yazar eşleşme tablosu boş, `new_lgiliYazar` boş; yazar bazında etkinlik gideri hesaplanamaz.
- **Etkinlik bütçesi yok:** etkinliklere bağlı bütçe kaydı/sütunu bulunmuyor; "etkinlik gideri bütçenin neresinde" sorusunda karşılaştırma yapılamaz, yalnız toplam gider verilir.
- **Reklam planı onayı boş:** 68 reklam planının hiçbirinde onay tarihi/onay biti ve teslim işareti dolu değil; "onaylanmış ama teslim edilmemiş" sorusu 0 döner (veri girilmemiş).

