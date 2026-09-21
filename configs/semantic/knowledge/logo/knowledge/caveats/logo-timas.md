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
- **Vade / yaşlandırma yalnız YAKLAŞIK hesaplanır (ölçüm 2026-09-21): Logo'da ödeme kapama kullanılmıyor** — PAYTRANS'ta 116.514 plan satırının yalnız 14'ünde ödenen tutar dolu, CROSSREF bağlantısı yok. Bu yüzden hangi faturanın ödendiği bilinmez; yöntem FIFO'dur: carinin bugünkü net bakiyesi (CLFLINE, CANCELLED 0; müşteri 120%: borç − alacak, tedarikçi 320%: alacak − borç) o carinin EN YENİ vade satırlarından (PAYTRANS, CANCELLED 0; müşteri SIGN 0, tedarikçi SIGN 1) geriye doğru dağıtılır, eski satırlar ödenmiş sayılır. Vadesi geçmiş = cari başına max(0, bakiye − vadesi gelmemiş (DATE_ ≥ bugün) plan satırları). Yaşlandırma = dağıtılan tutar, vadeden bugüne gün farkına göre kovalanır (vadesi gelmemiş, 1-30, 31-60, 61-90, 90+); plana dağıtılamayan kalan ayrıca gösterilir. Fatura tutarını fatura tarihine göre yaşlandırıp alacak diye sunma (kesilen fatura ≠ alacak). Cevabın yorum satırında 'FIFO yaklaşımı, Logo'da kapama yok' yazılmalı.
- **Tahsilat / ödeme süresi gerçekleşen olarak ölçülemez (kapama yok); DSO / DPO yaklaşımı kullanılır:** ortalama tahsilat süresi = müşteri (120%) bugünkü net bakiyesi ÷ yıl başından bu yana müşteri satış faturaları (CLFLINE TRCODE 37, 38, 39 eksi iade 32, 33) × aynı dönemin gün sayısı (1 Ocak → son hareket günü). Ortalama ödeme süresi aynası: tedarikçi (320%) net bakiyesi ÷ alış faturaları (CLFLINE TRCODE 31, 34 eksi 36) × gün. Planlanan (sözleşmesel) vade PAYTRANS.DATE_ − fatura tarihi ayrı bir ölçüdür; cevapta hangisinin verildiği ve yaklaşık olduğu yazılmalı.
- Asgari / azami stok seviyesi bu veride **tanımlı değil** (ölçüm 2026-09-18): `INVDEF.MINLEVEL` güncel kopyadaki 3,98 milyon malzeme–ambar satırının hiçbirinde sıfırdan büyük değil (seviye kontrolü açık 125.682 satırda da 0). "Asgari stok seviyesinin altına düşen malzemeler" sorusu bu yüzden boş döner; boş sonuç "hiçbir malzeme seviyenin altında değil" anlamına gelmez, seviye girilmemiştir.
- Cari risk limiti bu veride **tanımlı değil** (ölçüm 2026-09-18, doğrudan veritabanı): güncel kopyada (`LG_411_01_CLRNUMS`, 4.893 satır) ve 2021–25 kopyasında (237.228 satır) `ACCRISKLIMIT > 0` olan hiçbir cari yok. "Risk limitini aşan cariler" sorusu bu yüzden boş döner; boş sonuç "kimse limitini aşmadı" değil, "limit girilmemiş" demektir. (2015–2020 eski firma kopyalarında limitli kayıtlar vardır; güncel soruda okunmaz.)
- Karşılıksız / protestolu çek: **güncel durumda** (`LG_411_01_CSCARD.CURRSTAT`) 2026 vadeli karşılıksız (11) ya da protestolu (5, 7) müşteri çeki yok; karşılıksız görünen 20 çek (2,52 M ₺) 2018–2019 vadelidir. "Bu yıl karşılıksız **çıkan**" ise olaydır (Kural 12, iş kararı 2026-09-20) ve boş DEĞİLDİR: 2026'da `CSTRANS.STATUS = 11` hareketi görmüş 6 müşteri çeki, 6.326.658 ₺ (ölçüm 2026-09-20, doğrudan veritabanı); hepsi sonradan iade edildiği için güncel durumları 6'dır. 2026'da protesto olayı yok.

## CRM sözleşme tutar alanları boş

- `NEW_SOZLESMEBASE.new_teliftutari` ve `new_ajansservisucreti` bu kurulumda hiçbir sözleşmede dolu değil (14.824 aktif sözleşme, 0 dolu); telif hakediş tablosu `NEW_ODEMEHAKEDISBASE` boştur. "Ortalama telif tutarı", "ajans servis ücreti toplamı" soruları bu yüzden boş/NULL döner — veri yok, hesap hatası değil. Sözleşme adedi ve yüzde tabanlı telif (`new_Telif`, `NEW_TELIFTANIMBASE.new_TelifYuzdesi`) verilebilir.
- `NEW_URETIMBASE.new_UretimAdedi` hiç dolu değil; gerçekleşen üretim `NEW_BASKIBASE.new_uretimadedi` (39 kayıt).

## Telif hakedişi ve ödeme kaydı yok

- **Hakediş verisi yok:** telif hakediş / ödeme hakediş tablosu (`NEW_ODEMEHAKEDISBASE`) bu kurulumda hiç kayıt içermiyor (0 satır) ve taramada profili yok; "ödenmemiş hakediş", "dönemi kapanmış hakediş", "hakediş tutarı" soruları cevaplanamaz — veri girilmemiş. Ödeme dönemi kayıtları (`NEW_ODEMEDONEMIBASE`, 7 kayıt) var ama hakedişe bağlı değil.
- **Baskı işlemi / baskı maliyeti verisi eski:** `NEW_BASKIISLEMBASE` 2015–2017 (23 satır, birim fiyat 1 satırda dolu), `NEW_BASKIBASE` 2016–2018, satış senaryosu 2014 (4 satır). "Son bir yılda kitap başına baskı maliyeti", "birim fiyatı en çok artan işlem tipi" soruları bu yüzden boş döner — güncel veri yok.
- **Etkinlik yazarı yok:** etkinlik–yazar eşleşme tablosu boş, `new_lgiliYazar` boş; yazar bazında etkinlik gideri hesaplanamaz.
- **Etkinlik bütçesi yok:** etkinliklere bağlı bütçe kaydı/sütunu bulunmuyor; "etkinlik gideri bütçenin neresinde" sorusunda karşılaştırma yapılamaz, yalnız toplam gider verilir.
- **Reklam planı onayı boş:** 68 reklam planının hiçbirinde onay tarihi/onay biti ve teslim işareti dolu değil; "onaylanmış ama teslim edilmemiş" sorusu 0 döner (veri girilmemiş).
- **Telif tahakkuk verisi eski:** `NEW_ODEMEBASE` tahakkuk kayıtları yalnız 2014 (48 kayıt); "bu yıl telif tahakkuku" boş döner — veri yok.
- **Kampanya ciro alanları boş:** `NEW_KAMPANYABASE.new_planlananciro` ve `new_gerceklesenciro` 4 kampanyanın hiçbirinde dolu değil; planlanan/gerçekleşen kampanya cirosu karşılaştırması veri yokluğundan yapılamaz.

