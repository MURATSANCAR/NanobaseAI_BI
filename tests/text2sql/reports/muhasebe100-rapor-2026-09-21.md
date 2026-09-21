# ZEKİ AI — Muhasebe Birimi Testi (100 soru)

**Tarih:** 21.09.2026 · **Veri dönemi:** 01.01.2026 – 17.08.2026 (Logo, firma 411)  
**Yöntem:** Her soru köprüye bir kez soruldu. Aynı soru için köprüden bağımsız bir referans SQL yazılıp müşteri veritabanında çalıştırıldı; kolon ve kod anlamları katalogdaki etiketlerden okundu. 100 cevap tek tek elle hükümlendirildi (otomatik eşleştirici 61 'doğru' saydı; elle kontrolde bunların çoğu sahte eşleşme çıktı).

## Sonuç: **27 / 100 doğru**

| Hüküm | Soru |
|---|---|
| ✅ Doğru | 16 |
| ✅ Doğru (2. okuma) | 10 |
| ✅ Doğru ret | 1 |
| ❌ Yanlış değer | 46 |
| ❌ Veri varken 'yok' | 10 |
| ⚠️ Gereksiz ret | 13 |
| ❌ SQL hatası | 4 |

## Kategoriye göre

| Kategori | Doğru | Yanlış | Veri varken 'yok' | Ret | SQL hatası |
|---|---|---|---|---|---|
| A — Mizan ve hesap bakiyeleri | 3 / 12 | 5 | 1 | 1 | 2 |
| B — Alıcılar ve tahsilat | 2 / 12 | 7 | 0 | 1 | 2 |
| C — Satıcılar ve borçlar | 0 / 10 | 5 | 4 | 1 | 0 |
| D — Banka | 3 / 10 | 6 | 0 | 1 | 0 |
| E — Kasa | 5 / 5 | 0 | 0 | 0 | 0 |
| F — Çek ve senet | 3 / 10 | 3 | 2 | 2 | 0 |
| G — KDV ve vergi | 1 / 10 | 5 | 2 | 2 | 0 |
| H — Satışlar ve gelir tablosu | 3 / 10 | 5 | 0 | 2 | 0 |
| I — Giderler ve masraf merkezleri | 3 / 10 | 6 | 0 | 1 | 0 |
| J — Sabit kıymet ve amortisman | 1 / 5 | 1 | 1 | 2 | 0 |
| K — Yevmiye ve fiş kontrolü | 3 / 6 | 3 | 0 | 0 | 0 |

## Başlıca hata sınıfları

1. **Satıcı / alış tarafı kör (Satıcılar 0/10).** Alış faturası soruları "0" ya da "kayıt yok" dönüyor; veride 1.274 tedarikçi ve 492,4 Mn ₺ alış faturası var. Güçlü hipotez: "fatura" kavramı satış kapsamına (TRCODE 2,3,7,8,9) kilitli, alış faturaları (TRCODE 1, 4) filtrede eleniyor.
2. **"Gider" farklı soruları tek sayıya yutuyor.** 65.335.626,98 ₺ (7'li hesap net gideri) üç ayrı soruya cevap olarak döndü: tedarikçi ödemesi (M026), genel yönetim gideri (M081), gider/satış oranı (M088).
3. **Muhasebe hesabı yerine yan tablo.** 101 Alınan Çekler bakiyesi yerine çek kartları toplamı (M011), 600 hesabı yerine satış satırları (M009, M070), KDV'de satır tutarı: satış faturası KDV'si 4,49 Mn yerine **1,787 milyar** (M064, ~400 kat).
4. **Veri varken "kayıt yok" (10 soru) — en tehlikeli sınıf.** Hata mesajından daha zararlı, çünkü inandırıcı: 108 hesabı, tahsildeki çekler (270,7 Mn), protestolu senetler, alış KDV'si, 360 Ödenecek Vergi.
5. **Temel muhasebe kelimeleri katalogda yok (13 gereksiz ret).** "borç", "satıcı", "hesaplanan", "kdv", "tahsil", "ödemelerin", "gruplarına" tanımsız diye reddediliyor.
6. **Müşterinin özel rapor görünümlerine gitme (4 SQL hatası).** `AA_LOGO_MIZAN`, `MIND_VADE_RAPORU`, `AA_CAR_EKSTRE`: model standart defter yerine bu görünümleri seçiyor, kolonları tutmuyor.

## Referans çalışmasında çıkan muhasebe bulguları (sistemden bağımsız, veri gerçeği)

- **Mizan dengede.** Toplam borç = alacak = 8.589.117.368,97 ₺; 91.559 fişin hiçbiri dengesiz değil.
- **391 ile fatura KDV'si tutmuyor.** Hesaplanan KDV defterde 5.046.474 ₺; satış faturalarında 4.490.682 ₺; satış kısmında defter 174 bin ₺ eksik. İndirilecek KDV defterde faturadan 3,87 Mn fazla.
- **Kokpitteki "net ciro" (848,1 Mn) KDV dahil.** KDV hariç 843,8 Mn; gelir tablosuna göre net satış 841,7 Mn.
- **Ödeme kapama kullanılmıyor.** 116.514 ödeme planı satırının yalnız 14'ünde ödenen tutar dolu → vade/yaşlandırma yalnız yaklaşık hesaplanabilir.
- **Banka modülü muhasebeyle tutmuyor.** Çek tahsilatları banka modülünde nakit gibi işlenmemiş. Kasa modülü 39,0 Mn, muhasebe 100 hesabı 2,9 Mn.
- **Sabit kıymet sicili 4 iptal kaydı içeriyor.** İptaller hariç 94,2 Mn / amortisman 30,3 Mn; defterdeki birikmiş amortisman (257+268) 46,6 Mn — 2026 amortismanı henüz deftere yazılmamış.
- **Katalogda yanlış etiket.** Çek kartı durum kolonunun (CSCARD.CURRSTAT) açıklaması veriyle çelişiyor; doğru etiketler çek hareketi durum kolonunda (CSTRANS.STATUS). Kanıt: "tahsile verildi" 270.714.013 ₺ = 101.02 bakiyesi birebir.
- **Müşteri/tedarikçi ayrımı kart türünden yapılamıyor** (%99 "Alıcı+Satıcı"); ayrım cari kodunun 120/320 ile başlamasından yapılabiliyor.


## 100 soru — tam liste


### A — Mizan ve hesap bakiyeleri

| # | Soru | Köprünün cevabı | Hüküm | Gerekçe |
|---|---|---|---|---|
| M001 | Bu yılın mizanını ana hesap gruplarına göre çıkarır mısın? | AA_LOGO_MIZAN tablosunda ANAHEAP adında kolon yok.; AA_LOGO_MIZAN tablosunda BORC adında kolon yok.; AA_LOGO_M | ❌ SQL hatası | Müşterinin özel görünümüne (AA_LOGO_MIZAN) gitti, kolonlar yok |
| M002 | 1 ile 7 arasındaki hesap gruplarında toplam borç ve alacak ne kadar? | Toplam borc: 8.589.117.368,97 · Toplam alacak: 8.589.117.368,97 | ✅ Doğru | 8.589.117.368,97 borç = alacak, referansla birebir |
| M003 | 102 Bankalar hesabının bugünkü bakiyesi ne? | MIND_VADE_RAPORU tablosunda BNACCREF adında kolon yok. | ❌ SQL hatası | Alakasız MIND_VADE_RAPORU görünümüne gitti |
| M004 | 120 Alıcılar hesabının borç bakiyesi ne kadar? | Borc bakiyesi: 642.617.291,83 | ❌ Yanlış değer | 642,6 Mn; doğru 120 bakiyesi 136,1 Mn |
| M005 | 320 Satıcılar hesabında ne kadar alacak bakiyesi var? | Alacak bakiyesi: 0,00 | ❌ Yanlış değer | 0,00; doğru 320 alacak bakiyesi 55,3 Mn |
| M006 | En çok hareket gören on muhasebe hesabı hangileri? | 10 satır döndü. İlk 3: 1. Hareket sayisi 71.096 · 600.01.152 · Mamuller 2. Hareket sayisi 49.471 · 120.01.001  | ✅ Doğru | 600 ve 120 alt hesapları en hareketli, ölçümle uyumlu |
| M007 | Borç ve alacak toplamları birbirini tutuyor mu, mizan dengede mi? | 'borc' katalogda tanımlı değil, ama şemada karşılığı olabilecek bir kolon var: AA_CAR_EKSTRE.BORC, AA_TAHSILAT | ⚠️ Gereksiz ret | 'borç' tanımsız diye reddetti; mizan dengede (fiş dengesizliği 0) |
| M008 | Hesap planında kaç tane muhasebe hesabı var? | Hesap sayisi: 1.374 | ✅ Doğru | 1.374 hesap, birebir |
| M009 | 600 Yurtiçi Satışlar hesabının bu yılki alacak toplamı ne? | Alacak toplami: 922.727.839,97 Veri kapsamı: STLINE kayıtları 17.08.2026 tarihinde bitiyor; 'bu yilki' dönemi  | ❌ Yanlış değer | 922,7 Mn satış SATIRLARINDAN; 600 hesabının alacağı 910,1 Mn |
| M010 | Bu yıl hiç hareket görmeyen muhasebe hesapları hangileri? | 995 satır döndü. İlk 3: 1. 100 · KASA HESABİ                         2. 100.01 · KASA HESABİ                   | ❌ Yanlış değer | 995 hesap; doğru 583 |
| M011 | 101 Alınan Çekler hesabının bakiyesi ne kadar? | Bakiye: 1.127.129.742,74 | ❌ Yanlış değer | 1,127 Mr çek KARTLARI toplamı; 101 hesap bakiyesi 301,3 Mn |
| M012 | 108 Diğer Hazır Değerler hesabında ne kadar tutar var? | Bu koşullara uyan kayıt yok (sonuç boş). | ❌ Veri varken 'yok' | 'kayıt yok'; 108 hesabında 4.713 hareket, 12,1 Mn |

### B — Alıcılar ve tahsilat

| # | Soru | Köprünün cevabı | Hüküm | Gerekçe |
|---|---|---|---|---|
| M013 | En çok borcu olan on müşteri kim? | 10 satır döndü. İlk 3: 1. Senet borcu 17.497,80 · 12001.01.ÖZ124 · ÖZ ANKARA YAY.DAĞ.KİT.KIRT.OYUN.SAN. VE TİC | ❌ Yanlış değer | Senet borcunu listeledi; soru müşteri cari borcu |
| M014 | Bu yıl müşterilerden toplam ne kadar tahsilat yaptık? | Tahsilat tutari: 1.279.613.662,89 | ❌ Yanlış değer | 1,28 Mr; doğru tahsilat 896,6 Mn |
| M015 | Vadesi geçmiş müşteri alacaklarımız toplam ne kadar? | Toplam vadesi gecmis alacak: -94.143.348,37 | ❌ Yanlış değer | −94,1 Mn (alacak eksi olamaz); doğru ~149,0 Mn |
| M016 | Alacaklarımızı 30, 60, 90 gün diye yaşlandırır mısın? | Açık alacak / alacak yaşlandırması bu veride fatura bazında yapılamaz (ölçüm 2026-09-16): Logo yaşlandırması ö | ⚠️ Gereksiz ret | Yaşlandırma reddedildi; ödeme kapama kullanılmıyor ama yaklaşık hesap mümkün |
| M017 | Hangi müşterilerin bakiyesi bir milyon lirayı aşıyor? | 111 satır döndü. İlk 3: 1. Bakiyesi 222.679.595,08 2. Bakiyesi 65.850.955,15 3. Bakiyesi 46.831.393,89 | ❌ Yanlış değer | 111 müşteri; doğru 25 |
| M018 | Aylara göre tahsilat tutarlarımız nasıl dağılıyor? | 8 satır döndü. İlk 3: 1. Tahsilat tutari 282.591,71 · 2026-01-01 2. Tahsilat tutari 230.526,12 · 2026-02-01 3. | ❌ Yanlış değer | Ocak 282 bin; aylık tahsilat ~110 Mn mertebesinde olmalı |
| M019 | Ortalama tahsilat süremiz kaç gün? | Ortalama tahsilat gun: 30,29 · Plan kalemi: 70.470 | ❌ Yanlış değer | 30,3 gün; standart yöntemle 37,4 gün |
| M020 | Risk limitini aşmış müşteriler hangileri? | Bu koşullara uyan kayıt yok (sonuç boş). Muhtemel neden (bilgi paketi): Cari risk limiti bu veride **tanımlı d | ✅ Doğru ret | Risk limiti hiç tanımlı değil, bunu söyledi |
| M021 | Bu yıl hiç ödeme yapmamış ama borcu olan müşteriler var mı? | LG_CLFLINE tablosunda CARDREF adında kolon yok. | ❌ SQL hatası | CLFLINE'da olmayan CARDREF kolonu |
| M022 | Müşteri cari hareketlerinde en çok hangi işlem türü var? | 27 satır döndü. İlk 3: 1. Islem turu 37 · Hareket sayisi 49.548 2. Islem turu 38 · Hareket sayisi 21.009 3. Is | ✅ Doğru | 37 → 49.548, 38 → 21.009, birebir |
| M023 | Tahsilatlarımız geçen yıla göre arttı mı? | Tahsilat 2025: 188.714.387,67 · Tahsilat 2026: 84.831.026,67 Karşılaştırmada takvim dönemleri kullanıldı; döne | ❌ Yanlış değer | 2026: 84,8 Mn (doğru 896,6 Mn) ve eş dönem uygulanmadı |
| M024 | En büyük beş müşterinin toplam alacak içindeki payı yüzde kaç? | AA_CAR_EKSTRE tablosunda CARIKODU adında kolon yok. | ❌ SQL hatası | AA_CAR_EKSTRE görünümünde olmayan kolon |

### C — Satıcılar ve borçlar

| # | Soru | Köprünün cevabı | Hüküm | Gerekçe |
|---|---|---|---|---|
| M025 | En çok borcumuz olan on tedarikçi hangisi? | 10 satır döndü. İlk 3: 1. Cek borcu 28.250.000,00 · Senet borcu 0,00 · Toplam borcu 28.250.000,00 · 12001.01.K | ❌ Yanlış değer | Çek borcunu listeledi; soru tedarikçi cari borcu |
| M026 | Bu yıl tedarikçilere toplam ne kadar ödeme yaptık? | Toplam odeme: 65.335.626,98 | ❌ Yanlış değer | 65,3 Mn = 7'li hesap GİDERİ; tedarikçi ödemesi 482,7 Mn |
| M027 | Vadesi gelmiş ama henüz ödenmemiş satıcı borçlarımız ne kadar? | Bu koşullara uyan kayıt yok (sonuç boş). | ❌ Veri varken 'yok' | 'kayıt yok'; vadesi geçmiş satıcı borcu ~87,8 Mn |
| M028 | Satıcı borçlarımızı vadesine göre yaşlandırır mısın? | 'satici' katalogda tanımlı değil, ama şemada karşılığı olabilecek bir kolon var: KDV_V_SATISRAPORU.SATICI KODU | ⚠️ Gereksiz ret | 'satıcı' tanımsız diye reddetti |
| M029 | Aylara göre tedarikçi ödemelerimiz nasıl? | 3699 satır döndü. İlk 3: 1. Odeme tutari 9.411.574,50 · 2026-01-01 · 32001.01.YU026 · YUZU KİTAP YAYINCILIK A. | ❌ Yanlış değer | 3.699 tek tek satır; soru aylık toplam |
| M030 | Bu yıl alış faturası kestiğimiz kaç farklı tedarikçi var? | Tedarikci sayisi: 0 Veri kapsamı: INVOICE kayıtları 17.08.2026 tarihinde bitiyor; 'bu yil' dönemi 01.01.2026–1 | ❌ Yanlış değer | 0; alış faturası kesilen 1.274 tedarikçi |
| M031 | Alış faturalarımızın toplam tutarı ne kadar? | Bu koşullara uyan kayıt yok (sonuç boş). | ❌ Veri varken 'yok' | 'kayıt yok'; alış faturaları 492,4 Mn (KDV dahil) |
| M032 | Ortalama ödeme süremiz kaç gün? | Ortalama odeme suresi gun: Belirtilmemiş · Kapanan kalem: 0 | ❌ Yanlış değer | 'Belirtilmemiş'; standart yöntemle 28,8 gün |
| M033 | En büyük alış faturası hangi tedarikçiden? | Bu koşullara uyan kayıt yok (sonuç boş). Muhtemel neden (bilgi paketi): Satır düzeyinde satış tutarı = `STLINE | ❌ Veri varken 'yok' | 'kayıt yok'; alış faturası var |
| M034 | Satıcılara olan borcumuz geçen aya göre arttı mı? | Bu koşullara uyan kayıt yok (sonuç boş). Karşılaştırmada takvim dönemleri kullanıldı; dönemlerin eşit veri kap | ❌ Veri varken 'yok' | 'kayıt yok'; satıcı borcu önceki ay 73,3 Mn |

### D — Banka

| # | Soru | Köprünün cevabı | Hüküm | Gerekçe |
|---|---|---|---|---|
| M035 | Banka hesaplarımızın bakiyeleri ne? | 55 satır döndü. İlk 3: 1. Bakiye 13.920,00 · 10201 .01.001 · TİMAŞ KUVEYTTURK BEYAZIT ŞUBESİ - 90050275 - 12 2 | ❌ Yanlış değer | 55 satır ve bakiyeler tutmuyor; referans 13 banka hesabı bakiyesi |
| M036 | Bu yıl bankalara toplam ne kadar para girdi ve çıktı? | Giren para: 2.342.168.472,73 · Cikan para: 1.850.355.066,27 | ✅ Doğru (2. okuma) | Banka modülü okuması (2,34/1,85 Mr); muhasebe 102'ye göre 1,53/1,40 Mr |
| M037 | Hangi bankada en çok hareket var? | 11 satır döndü. İlk 3: 1. Hareket sayisi 6.881 · 10201 · KUVEYT TURK 2. Hareket sayisi 5.349 · 10206 · GARANTİ | ✅ Doğru (2. okuma) | Kuveyt Türk en hareketli; banka modülü okuması |
| M038 | Aylara göre banka giriş ve çıkışlarımız nasıl? | 8 satır döndü. İlk 3: 1. Giris 458.583.838,97 · Cikis 223.418.395,35 · 2026-01-01 2. Giris 256.643.002,33 · Ci | ✅ Doğru (2. okuma) | Aylık banka giriş/çıkış, banka modülü okuması |
| M039 | Kaç tane banka hesabımız var? | Banka hesabi sayisi: 118 | ❌ Yanlış değer | 118; aktif 85, tanımlı 87, hareketli 55 |
| M040 | Geçen ay banka hareketlerimizin net tutarı ne oldu? | Net tutar: 6.299.076,76 | ❌ Yanlış değer | +6,3 Mn; doğru net −4,9 Mn |
| M041 | En büyük on banka çıkışı hangileri? | 10 satır döndü. İlk 3: 1. Cikis tutari 711.578.067,47 · 10201 · KUVEYT TURK · 10201 .01.002 2. Cikis tutari 44 | ❌ Yanlış değer | İlk satır 711,6 Mn — tek çıkış değil toplam; liste hatalı |
| M042 | Banka bazında net nakit akışı nasıl? | 11 satır döndü. İlk 3: 1. Net nakit akisi 280.794.157,23 · KUVEYT TURK 2. Net nakit akisi 141.325.696,06 · VAK | ❌ Yanlış değer | 11 banka; muhasebe kırılımı 14 |
| M043 | Banka girişlerimiz geçen yılın aynı dönemine göre nasıl değişti? | 8 satır döndü. İlk 3: 1. Giris 2026 0,00 · Giris 2025 120.495.944,80 · Fark -120.495.944,80 · 2025-01-01 2. Gi | ❌ Yanlış değer | 2026 girişi 0,00 dedi; gerçek 1,53 Mr |
| M044 | Havale ve EFT ile yapılan ödemelerin toplamı ne kadar? | 'odemelerin' katalogda tanımlı değil, ama şemada karşılığı olabilecek bir kolon var: TSOFT_KAMPANYA.ÖDEME PLAN | ⚠️ Gereksiz ret | 'ödemelerin' tanımsız diye reddetti; havale/EFT 405,9 Mn |

### E — Kasa

| # | Soru | Köprünün cevabı | Hüküm | Gerekçe |
|---|---|---|---|---|
| M045 | Kasaların bakiyeleri ne kadar? | 7 satır döndü. İlk 3: 1. Bakiye 38.665.867,44 · 100.01 ·  2. Bakiye 48.938,50 · 100.02 ·  3. Bakiye 108.910,40 | ✅ Doğru (2. okuma) | Kasa modülü 38,7 Mn ≈ 39,0 Mn (muhasebe 100 hesabı 2,9 Mn — veri çelişkili) |
| M046 | Bu yıl kasaya ne kadar para girdi, ne kadar çıktı? | Giren para: 54.715.968,02 · Cikan para: 15.683.689,58 | ✅ Doğru (2. okuma) | Kasa modülü okuması (54,7/15,7 Mn); muhasebe 59,9/57,2 Mn |
| M047 | Hangi kasada en çok işlem yapılmış? | 7 satır döndü. İlk 3: 1. Islem sayisi 414 · 100.05 · Tarçın Kafe Kasası 2. Islem sayisi 230 · 100.03 · Peraken | ✅ Doğru | En çok işlem gören kasa, 7 kasa |
| M048 | Aylara göre kasa hareketlerimiz nasıl? | 8 satır döndü. İlk 3: 1. Giren 5.671.562,07 · Cikan 227.526,41 · Net 5.444.035,66 · 2026-01-01 2. Giren 480.80 | ✅ Doğru | Aylık kasa hareketleri |
| M049 | Kaç kasamız var? | Kasa sayisi: 9 | ✅ Doğru | 9 kasa, birebir |

### F — Çek ve senet

| # | Soru | Köprünün cevabı | Hüküm | Gerekçe |
|---|---|---|---|---|
| M050 | Portföydeki müşteri çeklerimiz toplam ne kadar? | Toplam tutar: 30.289.524,00 | ✅ Doğru | Portföydeki çekler 30.289.524, birebir |
| M051 | Bankaya tahsile verdiğimiz çeklerin tutarı ne kadar? | Bu koşullara uyan kayıt yok (sonuç boş). | ❌ Veri varken 'yok' | 'kayıt yok'; tahsildeki çekler 270,7 Mn (412 çek) |
| M052 | Bu yıl karşılıksız çıkan çeklerin toplam tutarı ne? | Toplam tutar: 6.326.658,00 | ✅ Doğru | Karşılıksız 6.326.658, birebir (bugün düzeltilen) |
| M053 | Protesto olan senetler var mı, tutarları ne? | Bu koşullara uyan kayıt yok (sonuç boş). | ❌ Veri varken 'yok' | 'kayıt yok'; protestolu senet 877.714 (83 senet) |
| M054 | Vadesi gelecek ay dolan çekler hangileri? | 174 satır döndü. İlk 3: 1. LOGICALREF 3.031 · DOC 1 · AMOUNT 3.000.000,00 · CURRSTAT 4 2. LOGICALREF 3.037 · D | ❌ Yanlış değer | 174 çek; doğru 126 |
| M055 | Çeklerimizi durumlarına göre dağılım olarak gösterir misin? | 6 satır döndü. İlk 3: 1. Durum kodu 2 · Cek sayisi 2.616 · Toplam tutar 539.091.801,38 2. Durum kodu 8 · Cek s | ✅ Doğru | Durumlara göre dağılım, 6 grup |
| M056 | Senetlerin toplam tutarı çeklere göre ne kadar? | Cek tutar: 1.127.129.742,74 · Senet tutar: 0,00 · Fark: -1.127.129.742,74 | ❌ Yanlış değer | Senet 0,00; doğru 12,3 Mn |
| M057 | En büyük tutarlı on çek hangi müşteriden? | 'tutarli' katalogda tanımlı bir kavram değil; bu yüzden üretilen sorgu doğrulanamadı. Şemada karşılığı olabile | ⚠️ Gereksiz ret | 'tutarlı' kelimesi tanımsız diye reddetti |
| M058 | Tahsil edilmiş çeklerin toplamı ne kadar? | 'tahsil' katalogda tanımlı bir kavram değil; bu yüzden üretilen sorgu doğrulanamadı. Şemada karşılığı olabilec | ⚠️ Gereksiz ret | 'tahsil' tanımsız diye reddetti; tahsil edilen çek 261,3 Mn |
| M059 | Ciro edilen çekler toplam ne kadar? | Ciro edilen cek tutari: 0,00 | ❌ Yanlış değer | 0,00; ciro edilen çek 158,1 Mn (bu yıl) |

### G — KDV ve vergi

| # | Soru | Köprünün cevabı | Hüküm | Gerekçe |
|---|---|---|---|---|
| M060 | Bu yılki hesaplanan KDV toplamımız ne? | Hesaplanan kdv: 4.490.682,10 | ✅ Doğru (2. okuma) | Satış faturası KDV'si 4.490.682 (391 hesabı 5.046.474 — mutabakat farkı var) |
| M061 | İndirilecek KDV toplamı ne kadar? | Indirilecek kdv: 8.512.761,91 | ❌ Yanlış değer | 8,5 Mn; indirilecek KDV 65,2 Mn |
| M062 | Hesaplanan ile indirilecek KDV arasındaki fark ne? | 'hesaplanan' katalogda tanımlı değil, ama şemada karşılığı olabilecek bir kolon var: NY_B2C_FATURA_RAPORU.HESA | ⚠️ Gereksiz ret | 'hesaplanan' tanımsız diye reddetti |
| M063 | Aylara göre hesaplanan KDV nasıl dağılıyor? | 8 satır döndü. İlk 3: 1. Hesaplanan kdv 8.423.726,18 · 2026-01-01 2. Hesaplanan kdv 10.705.091,85 · 2026-02-01 | ❌ Yanlış değer | Aylık 8,4 Mn; yıllık toplam 5,0 Mn — imkânsız |
| M064 | Satış faturalarındaki toplam KDV tutarı ne kadar? | Kdv tutari: 1.787.283.096,16 | ❌ Yanlış değer | 1,787 MİLYAR; satış faturası KDV'si 4,49 Mn (400 kat) |
| M065 | Alış faturalarındaki toplam KDV ne kadar? | Bu koşullara uyan kayıt yok (sonuç boş). | ❌ Veri varken 'yok' | 'kayıt yok'; alış faturası KDV'si 61,2 Mn |
| M066 | Ödenecek vergi ve fonlar hesabında ne kadar tutar var? | Bu koşullara uyan kayıt yok (sonuç boş). | ❌ Veri varken 'yok' | 'kayıt yok'; 360 hesabında 9,0 Mn |
| M067 | Geçen ay ne kadar KDV ödememiz çıkıyor? | Bu soruyu cevaplayamıyorum: 'kdv' burada tanımlı bir kavram değil. İş terimiyse portalden tanımlayabilirsiniz. | ⚠️ Gereksiz ret | 'kdv' tanımsız diye reddetti |
| M068 | KDV'si sıfır olan faturalar var mı, kaç tane? | Kdv sifir fatura sayisi: 66.365 | ❌ Yanlış değer | 66.365; doğru 67.263 |
| M069 | Hangi fatura türünde en çok KDV var? | 5 satır döndü. İlk 3: 1. Fatura turu 8 · Toplam kdv 2.986.137,60 2. Fatura turu 9 · Toplam kdv 820.410,23 3. F | ❌ Yanlış değer | En çok KDV'yi toptan satış (2,99 Mn) dedi; gerçekte alınan hizmet 47,5 Mn |

### H — Satışlar ve gelir tablosu

| # | Soru | Köprünün cevabı | Hüküm | Gerekçe |
|---|---|---|---|---|
| M070 | Bu yılki net satışlarımız ne kadar? | Satis tutari: 922.727.839,97 Veri kapsamı: STLINE kayıtları 17.08.2026 tarihinde bitiyor; 'bu yilki' dönemi 01 | ❌ Yanlış değer | 922,7 Mn satış satırından; gelir tablosu net satış 841,7 Mn |
| M071 | Satış iadelerimiz toplam ne kadar? | Satis iade tutari: 74.308.487,24 | ❌ Yanlış değer | 74,3 Mn; doğru 71,0 Mn |
| M072 | Satış iskontolarımız ne kadar tuttu? | Satis tutari: 922.727.839,97 · Iskonto orani: 0,46 Veri kapsamı: STLINE kayıtları 17.08.2026 tarihinde bitiyor | ❌ Yanlış değer | Oran 0,46 verdi; tutar sorulmuş (611: 2,8 Mn, fatura iskontosu 747,9 Mn) |
| M073 | Aylara göre net satış tutarlarımız nasıl? | 8 satır döndü. İlk 3: 1. Satis tutari 110.485.687,96 · 2026-01-01 2. Satis tutari 138.579.830,54 · 2026-02-01  | ✅ Doğru (2. okuma) | Aylık satış tutarları, satır düzeyinde okuma |
| M074 | Bu yılki satışlarımız geçen yılın aynı dönemine göre nasıl? | Bu yilki satis tutari: 922.727.839,97 · Gecen yilin satis tutari: 619.266.128,89 Karşılaştırmada eş dönem kull | ❌ Yanlış değer | 922,7 / 619,3 Mn; eş dönem net satış 841,7 / 556,3 Mn |
| M075 | Brüt satış, iade ve iskonto ile net satışı ayrı ayrı gösterir misin? | Bu soruyu cevaplayamıyorum: 'ayri' burada tanımlı bir kavram değil. İş terimiyse portalden tanımlayabilirsiniz | ⚠️ Gereksiz ret | 'ayrı' kelimesi tanımsız diye reddetti |
| M076 | Bu yıl kaç satış faturası kestik? | Kayit sayisi: 73.660 Veri kapsamı: INVOICE kayıtları 17.08.2026 tarihinde bitiyor; 'bu yil' dönemi 01.01.2026– | ✅ Doğru (2. okuma) | 73.660 (iade dahil satış kapsamı); iade hariç 70.664 — iş tanımı 73.660 |
| M077 | Toptan ve perakende satışlarımızın payı ne? | Sorudaki kavramlar tanımlı (perakende satislarimizin, toptan), ama bunları tek bir hesapta birleştiren bir tan | ⚠️ Gereksiz ret | Toptan/perakende payını birleştiremedi |
| M078 | İade oranımız yüzde kaç? | Iade tutari: 74.308.487,24 · Satis tutari: 922.418.666,06 · Iade orani yuzde: 8,06 | ✅ Doğru (2. okuma) | Fatura tutarına göre ~%8,1; defterden %7,76 |
| M079 | Dövizli faturalarımızın toplam tutarı ne kadar? | Toplam tutar: 4.891.851,38 | ❌ Yanlış değer | 4,9 Mn; dövizli fatura toplamı tutmuyor |

### I — Giderler ve masraf merkezleri

| # | Soru | Köprünün cevabı | Hüküm | Gerekçe |
|---|---|---|---|---|
| M080 | Bu yılki pazarlama giderlerimiz ne kadar? | Pazarlama gideri: -204.869.160,73 | ❌ Yanlış değer | −204,9 Mn (işaret ters); pazarlama 242,4 Mn |
| M081 | Genel yönetim giderlerimiz toplam ne? | Gider toplam: 65.335.626,98 | ❌ Yanlış değer | 65,3 Mn = yine 7'li toplam; genel yönetim 54,1 Mn |
| M082 | Masraf merkezlerine göre giderlerimiz nasıl dağılıyor? | 1628 satır döndü. İlk 3: 1. Gider 48.410.142,55 · GENEL MÜDÜRLÜK MASRAF MERKEZİ 2. Gider 34.135.742,66 · LOJİS | ❌ Yanlış değer | 1.628 merkez; gider yazılan 1.851 |
| M083 | En çok gider yazılan on masraf merkezi hangisi? | 10 satır döndü. İlk 3: 1. Gider tutari 48.410.142,55 · B01-GMD-01 · GENEL MÜDÜRLÜK MASRAF MERKEZİ 2. Gider tut | ✅ Doğru | En çok gider yazılan 10 merkez, Genel Müdürlük başta |
| M084 | Aylara göre giderlerimiz nasıl değişiyor? | 8 satır döndü. İlk 3: 1. Gider 39.548.956,54 · 2026-01-01 2. Gider 46.086.907,20 · 2026-02-01 3. Gider 45.472. | ✅ Doğru | Aylık gider dağılımı |
| M085 | Pazarlama ile genel yönetim giderlerini karşılaştırır mısın? | Gider kategorisi: Pazarlama · Gider tutari: 10.204.445,74 | ❌ Yanlış değer | Pazarlama 10,2 Mn; doğru 242,4 Mn |
| M086 | Giderlerimiz geçen aya göre arttı mı? | Sorudaki koşulların tamamı doğrulanamadı: ölçünün katalog kapsamı doğrulanamadı | ⚠️ Gereksiz ret | Kapsam doğrulanamadı diye reddetti |
| M087 | Hizmet alımlarımızın toplam tutarı ne kadar? | Hizmet alim tutari: 297.249.602,82 | ❌ Yanlış değer | 297,2 Mn hizmet kartından; muhasebe 249,8 Mn |
| M088 | Giderlerin satışlara oranı yüzde kaç? | Gider: 65.335.626,98 · Satis: 922.727.839,97 · Gider orani yuzde: 7,08 | ❌ Yanlış değer | %7,08 (yine 65,3 Mn gider); doğru %35,2 |
| M089 | Kaç tane masraf merkezimiz var? | Masraf merkezi sayisi: 17.343 | ✅ Doğru (2. okuma) | 17.343 tanımlı merkez (düşük güvenli soru) |

### J — Sabit kıymet ve amortisman

| # | Soru | Köprünün cevabı | Hüküm | Gerekçe |
|---|---|---|---|---|
| M090 | Sabit kıymetlerimizin toplam giriş maliyeti ne kadar? | 'sabit, kiymetlerimizin, giris' katalogda tanımlı bir kavram değil; bu yüzden üretilen sorgu doğrulanamadı. Şe | ⚠️ Gereksiz ret | 'sabit kıymet giriş' tanımsız diye reddetti — bugün eklenen kavram yakalanmadı |
| M091 | Birikmiş amortisman toplamımız ne? | Sabit kiymet amortismani: 340.063,28 'varsayılan' dönemi kısmen gözleniyor: FAREGIST kayıtları 1991-01-01–2026 | ❌ Yanlış değer | 340.063; doğru 30,3 Mn — yıl filtresi girdi |
| M092 | Sabit kıymet gruplarına göre maliyetler nasıl dağılıyor? | 'gruplarina' katalogda tanımlı değil, ama şemada karşılığı olabilecek bir kolon var: A_MS_ITEMS_PRCLIST_GRPCOD | ⚠️ Gereksiz ret | 'gruplarına' tanımsız diye reddetti |
| M093 | Bu yıl kaç yeni sabit kıymet aldık? | Yeni sabit kiymet sayisi: 58 | ✅ Doğru | 58 yeni kıymet, birebir |
| M094 | Amortismanı tamamen bitmiş kıymetler hangileri? | Bu koşullara uyan kayıt yok (sonuç boş). 'varsayılan' dönemi kısmen gözleniyor: FAREGIST kayıtları 1991-01-01– | ❌ Veri varken 'yok' | 'kayıt yok'; 226 kıymetin amortismanı bitmiş |

### K — Yevmiye ve fiş kontrolü

| # | Soru | Köprünün cevabı | Hüküm | Gerekçe |
|---|---|---|---|---|
| M095 | Bu yıl kaç muhasebe fişi kesildi? | Muhasebe fisi sayisi: 91.559 | ✅ Doğru | 91.559 fiş, birebir |
| M096 | Fiş türlerine göre dağılım nasıl? | 15 satır döndü. İlk 3: 1. Modul no 0 · Fis turu 1 · Fis sayisi 1 2. Modul no 0 · Fis turu 4 · Fis sayisi 367 3 | ❌ Yanlış değer | 15 grup; fiş türü 5 |
| M097 | Borç ve alacağı tutmayan fiş var mı? | 4 satır döndü. İlk 3: 1. LOGICALREF 2.127 · REPDEBIT 14.693,09 · REPCREDIT 42.227,63 · 4110000001 2. LOGICALRE | ❌ Yanlış değer | 4 'tutmayan' fiş buldu; gerçekte dengesiz fiş YOK — yanlış alarm |
| M098 | Aylara göre muhasebe fişi sayısı nasıl? | 8 satır döndü. İlk 3: 1. Fisi sayisi 11.846 · 2026-01-01 2. Fisi sayisi 15.290 · 2026-02-01 3. Fisi sayisi 11. | ✅ Doğru | Aylık fiş sayısı |
| M099 | En çok satırlı on muhasebe fişi hangileri? | 10 satır döndü. İlk 3: 1. Fisi ref 52.670 · Fisi turu 4 · Satir sayisi 670 · 411052100 2. Fisi ref 87.148 · Fi | ✅ Doğru | En çok satırlı 10 fiş |
| M100 | Bu ay hiç muhasebe kaydı girildi mi? | Muhasebe kayit sayisi: 0 | ❌ Yanlış değer | '0' dedi; doğrusu 'veri 17.08'de bitiyor' demekti |

## Ek — SQL karşılaştırması (her soru)


### M001 · Bu yılın mizanını ana hesap gruplarına göre çıkarır mısın?

**Hüküm:** ❌ SQL hatası — Müşterinin özel görünümüne (AA_LOGO_MIZAN) gitti, kolonlar yok  
**Referans tanımı:** Mizan: 2026 yevmiye satırları (EMFLINE, CANCELLED=0, açılış fişi dahil), hesap kodunun ilk hanesine göre Tek Düzen ana hesap grubu; borç, al

**Köprünün SQL'i:**
```sql
-- yorum: 'mizanini' → AA_LOGO_MIZAN tablosu, dönem toplamı
-- yorum: 'ana' → AA_LOGO_MIZAN.ANAHESAP kolonu
-- yorum: 'gruplarina' → AA_LOGO_MIZAN.ANAHESAP kolonu
SELECT 
    "ANAHEAP" AS ana_hesap_grubu,
    SUM("BORC") AS toplam_borc,
    SUM("ALACAK") AS toplam_alacak,
    SUM("BORC") - SUM("ALACAK") AS net_bakiye
FROM AA_LOGO_MIZAN
WHERE "DATE_" >= '2026-01-01' AND "DATE_" < '2027-01-01'
GROUP BY "ANAHEAP"
ORDER BY "ANAHEAP"
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT CASE LEFT(L.ACCOUNTCODE,1) WHEN '1' THEN '1 Dönen Varlıklar' WHEN '2' THEN '2 Duran Varlıklar' WHEN '3' THEN '3 Kısa Vadeli Yabancı Kaynaklar'
 WHEN '4' THEN '4 Uzun Vadeli Yabancı Kaynaklar' WHEN '5' THEN '5 Özkaynaklar' WHEN '6' THEN '6 Gelir Tablosu Hesapları' WHEN '7' THEN '7 Maliyet Hesapları'
 WHEN '8' THEN '8 Serbest' WHEN '9' THEN '9 Nazım Hesaplar' ELSE LEFT(L.ACCOUNTCODE,1) END grup, SUM(L.DEBIT) borc, SUM(L.CREDIT) alacak,
 CASE WHEN SUM(L.DEBIT-L.CREDIT)>0 THEN SUM(L.DEBIT-L.CREDIT) ELSE 0 END borc_bakiye,
 CASE WHEN SUM(L.DEBIT-L.CREDIT)<0 THEN -SUM(L.DEBIT-L.CREDIT) ELSE 0 END alacak_bakiye
FROM LG_411_01_EMFLINE L WHERE L.CANCELLED=0 AND YEAR(L.DATE_)=YEAR(GETDATE()) GROUP BY CASE LEFT(L.ACCOUNTCODE,1) WHEN '1' THEN '1 Dönen Varlıklar' WHEN '2' THEN '2 Duran Varlıklar' WHEN '3' THEN '3 Kısa Vadeli Yabancı Kaynaklar'
 WHEN '4' THEN '4 Uzun Vadeli Yabancı Kaynaklar' WHEN '5' THEN '5 Özkaynaklar' WHEN '6' THEN '6 Gelir Tablosu Hesapları' WHEN '7' THEN '7 Maliyet Hesapları'
 WHEN '8' THEN '8 Serbest' WHEN '9' THEN '9 Nazım Hesaplar' ELSE LEFT(L.ACCOUNTCODE,1) END ORDER BY 1
```

### M002 · 1 ile 7 arasındaki hesap gruplarında toplam borç ve alacak ne kadar?

**Hüküm:** ✅ Doğru — 8.589.117.368,97 borç = alacak, referansla birebir  
**Referans tanımı:** 1–7 hesap gruplarında (hesap kodu ilk hanesi 1..7) 2026 toplam borç ve toplam alacak; iptal hariç, açılış dahil.

**Köprünün SQL'i:**
```sql
-- yorum: 'gruplarinda' → EMUHACC.CODE ile hesap grubu (ilk 1-7 karakter)
-- yorum: 'borc' → EMFLINE.DEBIT toplamı
-- yorum: 'alacak' → EMFLINE.CREDIT toplamı
SELECT 
    SUM("DEBIT") AS toplam_borc,
    SUM("CREDIT") AS toplam_alacak
FROM EMFLINE
WHERE "CANCELLED" = 0
  AND LEFT("ACCOUNTCODE", 1) IN ('1','2','3','4','5','6','7')
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT SUM(L.DEBIT) toplam_borc, SUM(L.CREDIT) toplam_alacak, SUM(L.DEBIT-L.CREDIT) fark FROM LG_411_01_EMFLINE L
WHERE L.CANCELLED=0 AND YEAR(L.DATE_)=YEAR(GETDATE()) AND LEFT(L.ACCOUNTCODE,1) BETWEEN '1' AND '7'
```

### M003 · 102 Bankalar hesabının bugünkü bakiyesi ne?

**Hüküm:** ❌ SQL hatası — Alakasız MIND_VADE_RAPORU görünümüne gitti  
**Referans tanımı:** 102 Bankalar muhasebe bakiyesi = Σ(borç − alacak), hesap kodu 102 ile başlayan tüm alt hesaplar, açılış dahil, iptal hariç, DATE_ ≤ bugün.

**Köprünün SQL'i:**
```sql
-- yorum: 'bakiyesi' → MIND_VADE_RAPORU.Borc_Bakiyesi, banka hesabı 102 için borç bakiyesi.
SELECT m."Borc_Bakiyesi" AS bakiye
FROM MIND_VADE_RAPORU m
JOIN BANKACC b ON m."BNACCREF" = b."LOGICALREF"
WHERE b."CODE" = '102'
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT SUM(L.DEBIT-L.CREDIT) bakiye_102 FROM LG_411_01_EMFLINE L WHERE L.CANCELLED=0 AND L.ACCOUNTCODE LIKE '102%' AND L.DATE_ <= GETDATE()
```

### M004 · 120 Alıcılar hesabının borç bakiyesi ne kadar?

**Hüküm:** ❌ Yanlış değer — 642,6 Mn; doğru 120 bakiyesi 136,1 Mn  
**Referans tanımı:** 120 Alıcılar kebir bakiyesi = Σ(borç − alacak) (hesap 120%), 2026, açılış dahil, iptal hariç. Pozitif = borç bakiyesi.

**Köprünün SQL'i:**
```sql
-- yorum: 'borc' → MIND_VADE_RAPORU.Borc_Bakiyesi, toplam
-- yorum: 'bakiyesi' → MIND_VADE_RAPORU.Borc_Bakiyesi, toplam
SELECT SUM(MIND_VADE_RAPORU.[Borc_Bakiyesi]) AS borc_bakiyesi
FROM MIND_VADE_RAPORU
WHERE MIND_VADE_RAPORU.[SPECODE] = 'ALICILAR'
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT SUM(L.DEBIT-L.CREDIT) bakiye_120, SUM(L.DEBIT) borc, SUM(L.CREDIT) alacak FROM LG_411_01_EMFLINE L WHERE L.CANCELLED=0 AND L.ACCOUNTCODE LIKE '120%' AND YEAR(L.DATE_)=YEAR(GETDATE())
```

### M005 · 320 Satıcılar hesabında ne kadar alacak bakiyesi var?

**Hüküm:** ❌ Yanlış değer — 0,00; doğru 320 alacak bakiyesi 55,3 Mn  
**Referans tanımı:** 320 Satıcılar kebir alacak bakiyesi = Σ(alacak − borç) (hesap 320%), 2026, açılış dahil, iptal hariç.

**Köprünün SQL'i:**
```sql
-- yorum: 'bakiyesi' → MIND_VADE_RAPORU.Borc_Bakiyesi, 320 hesabına ait toplam borç bakiyesi
SELECT SUM([Borc_Bakiyesi]) AS alacak_bakiyesi
FROM [MIND_VADE_RAPORU]
WHERE [SPECODE] = '320'
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT SUM(L.CREDIT-L.DEBIT) alacak_bakiye_320, SUM(L.DEBIT) borc, SUM(L.CREDIT) alacak FROM LG_411_01_EMFLINE L WHERE L.CANCELLED=0 AND L.ACCOUNTCODE LIKE '320%' AND YEAR(L.DATE_)=YEAR(GETDATE())
```

### M006 · En çok hareket gören on muhasebe hesabı hangileri?

**Hüküm:** ✅ Doğru — 600 ve 120 alt hesapları en hareketli, ölçümle uyumlu  
**Referans tanımı:** Hareket = 2026 yevmiye satırı sayısı (iptal hariç), en alt (muavin) hesap kodu bazında, ilk 10.

**Köprünün SQL'i:**
```sql
-- yorum: 'goren' → EMFLINE.ACCOUNTREF üzerinden hesap bazında hareket satırı sayısı (COUNT)
SELECT TOP 10
    h."CODE" AS hesap_kodu,
    h."DEFINITION_" AS hesap_adi,
    COUNT(*) AS hareket_sayisi
FROM EMFLINE t
JOIN EMUHACC h ON h."LOGICALREF" = t."ACCOUNTREF"
WHERE t."CANCELLED" = 0
GROUP BY h."CODE", h."DEFINITION_"
ORDER BY hareket_sayisi DESC
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT TOP 10 L.ACCOUNTCODE hesap, MAX(A.DEFINITION_) ad, COUNT(*) hareket, SUM(L.DEBIT) borc, SUM(L.CREDIT) alacak FROM LG_411_01_EMFLINE L
LEFT JOIN LG_411_EMUHACC A ON A.LOGICALREF=L.ACCOUNTREF WHERE L.CANCELLED=0 AND YEAR(L.DATE_)=YEAR(GETDATE()) GROUP BY L.ACCOUNTCODE ORDER BY COUNT(*) DESC
```

### M007 · Borç ve alacak toplamları birbirini tutuyor mu, mizan dengede mi?

**Hüküm:** ⚠️ Gereksiz ret — 'borç' tanımsız diye reddetti; mizan dengede (fiş dengesizliği 0)  
**Referans tanımı:** Mizan denkliği: 2026 tüm yevmiye satırları (iptal hariç) toplam borç = toplam alacak mı; ayrıca fiş bazında borç≠alacak olan fiş sayısı.

**Köprünün SQL'i:**
```sql
(SQL üretilmedi)
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT SUM(L.DEBIT) toplam_borc, SUM(L.CREDIT) toplam_alacak, ROUND(SUM(L.DEBIT)-SUM(L.CREDIT),2) fark,
 (SELECT COUNT(*) FROM (SELECT ACCFICHEREF FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND YEAR(DATE_)=YEAR(GETDATE()) GROUP BY ACCFICHEREF HAVING ABS(SUM(DEBIT)-SUM(CREDIT))>0.01) x) dengesiz_fis
FROM LG_411_01_EMFLINE L WHERE L.CANCELLED=0 AND YEAR(L.DATE_)=YEAR(GETDATE())
```

### M008 · Hesap planında kaç tane muhasebe hesabı var?

**Hüküm:** ✅ Doğru — 1.374 hesap, birebir  
**Referans tanımı:** Hesap planı = LG_411_EMUHACC kart sayısı (tüm seviyeler).

**Köprünün SQL'i:**
```sql
-- yorum: 'planinda' → EMUHACC.LOGICALREF, COUNT(*)
SELECT COUNT(*) AS hesap_sayisi
FROM EMUHACC
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT COUNT(*) toplam_hesap, SUM(CASE WHEN ACTIVE=0 THEN 1 ELSE 0 END) aktif, SUM(CASE WHEN SUBACCOUNTS=0 THEN 1 ELSE 0 END) muavin_alt_hesapsiz,
 SUM(CASE WHEN LEVEL_=0 THEN 1 ELSE 0 END) seviye0_ana, SUM(CASE WHEN LEVEL_=1 THEN 1 ELSE 0 END) seviye1, SUM(CASE WHEN LEVEL_=2 THEN 1 ELSE 0 END) seviye2 FROM LG_411_EMUHACC
```

### M009 · 600 Yurtiçi Satışlar hesabının bu yılki alacak toplamı ne?

**Hüküm:** ❌ Yanlış değer — 922,7 Mn satış SATIRLARINDAN; 600 hesabının alacağı 910,1 Mn  
**Referans tanımı:** 600 Yurtiçi Satışlar 2026 alacak (CREDIT) toplamı, hesap 600%, iptal hariç (brüt alacak; iade/iskonto 610/611 ayrı hesapta).

**Köprünün SQL'i:**
```sql
-- yorum: 'yurtici' → KONSOLIDE_MIZAN hesabı 600 Yurtiçi Satışlar; alacak toplamı ALACAK kolonu
-- yorum: 'yurtici' → STLINE TRCODE 7,8,9 satış satırlarının LINENET toplamı; 600 Yurtiçi Satışlar hesabı
SELECT SUM(CASE WHEN STLINE.[TRCODE] IN (7, 8, 9) THEN STLINE.[LINENET] ELSE 0 END) AS alacak_toplami
FROM [dbo].[STLINE] AS STLINE
WHERE STLINE.[CANCELLED] = 0
  AND STLINE.[LINETYPE] = 0
  AND STLINE.[TRCODE] IN (2, 3, 7, 8, 9)
  AND STLINE.[DATE_] >= '2026-01-01'
  AND STLINE.[DATE_] < '2027-01-01'
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT SUM(L.CREDIT) alacak_600, SUM(L.DEBIT) borc_600, SUM(L.CREDIT-L.DEBIT) net_600 FROM LG_411_01_EMFLINE L WHERE L.CANCELLED=0 AND L.ACCOUNTCODE LIKE '600%' AND YEAR(L.DATE_)=YEAR(GETDATE())
```

### M010 · Bu yıl hiç hareket görmeyen muhasebe hesapları hangileri?

**Hüküm:** ❌ Yanlış değer — 995 hesap; doğru 583  
**Referans tanımı:** Hareketsiz hesap = alt hesabı olmayan (SUBACCOUNTS=0, kayıt alabilen muavin) hesap kartı, 2026'da hiçbir yevmiye satırı yok (iptal hariç). T

**Köprünün SQL'i:**
```sql
-- yorum: 'gormeyen' → EMFLINE'da hiç satırı olmayan EMUHACC hesapları (NOT EXISTS)
SELECT
    h."CODE" AS hesap_kodu,
    h."DEFINITION_" AS hesap_adi
FROM EMUHACC h
WHERE NOT EXISTS (
    SELECT 1
    FROM EMFLINE t
    WHERE t."ACCOUNTREF" = h."LOGICALREF"
      AND t."CANCELLED" = 0
      AND t."DATE_" >= '2026-01-01'
      AND t."DATE_" < '2027-01-01'
)
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
WITH U AS (SELECT L.ACCOUNTREF FROM LG_411_01_EMFLINE L WHERE L.CANCELLED=0 AND YEAR(L.DATE_)=YEAR(GETDATE()) GROUP BY L.ACCOUNTREF)
SELECT A.CODE, A.DEFINITION_, A.ACTIVE FROM LG_411_EMUHACC A LEFT JOIN U ON U.ACCOUNTREF=A.LOGICALREF WHERE A.SUBACCOUNTS=0 AND U.ACCOUNTREF IS NULL ORDER BY A.CODE
```

### M011 · 101 Alınan Çekler hesabının bakiyesi ne kadar?

**Hüküm:** ❌ Yanlış değer — 1,127 Mr çek KARTLARI toplamı; 101 hesap bakiyesi 301,3 Mn  
**Referans tanımı:** 101 Alınan Çekler muhasebe bakiyesi = Σ(borç − alacak), hesap 101%, açılış dahil, iptal hariç.

**Köprünün SQL'i:**
```sql
-- yorum: 'bakiyesi' → LG_CSCARD.AMOUNT toplamı, DOC=1 (alınan çek) ve CANCELLED=0
SELECT SUM(LG_CSCARD."AMOUNT") AS bakiye
FROM LG_CSCARD
WHERE LG_CSCARD."DOC" = 1
  AND LG_CSCARD."CANCELLED" = 0
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT SUM(L.DEBIT-L.CREDIT) bakiye_101 FROM LG_411_01_EMFLINE L WHERE L.CANCELLED=0 AND L.ACCOUNTCODE LIKE '101%'
```

### M012 · 108 Diğer Hazır Değerler hesabında ne kadar tutar var?

**Hüküm:** ❌ Veri varken 'yok' — 'kayıt yok'; 108 hesabında 4.713 hareket, 12,1 Mn  
**Referans tanımı:** 108 Diğer Hazır Değerler muhasebe bakiyesi = Σ(borç − alacak), hesap 108%, açılış dahil, iptal hariç.

**Köprünün SQL'i:**
```sql
-- yorum: 'degerler' → EMUHACC.CODE = '108' hesabının EMFLINE borç-alacak bakiyesi.
SELECT SUM(EMFLINE.[DEBIT] - EMFLINE.[CREDIT]) AS bakiye
FROM EMFLINE
JOIN EMUHACC ON EMUHACC.[LOGICALREF] = EMFLINE.[ACCOUNTREF]
WHERE EMUHACC.[CODE] = '108'
  AND EMFLINE.[CANCELLED] = 0
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT SUM(L.DEBIT-L.CREDIT) bakiye_108 FROM LG_411_01_EMFLINE L WHERE L.CANCELLED=0 AND L.ACCOUNTCODE LIKE '108%'
```

### M013 · En çok borcu olan on müşteri kim?

**Hüküm:** ❌ Yanlış değer — Senet borcunu listeledi; soru müşteri cari borcu  
**Referans tanımı:** Müşteri = cari kart kodu 120 ile başlayan (CLCARD.CARDTYPE neredeyse hepsi 3=Alıcı+Satıcı, ayırt etmiyor). Borç = cari bakiye Σ(SIGN0 borç −

**Köprünün SQL'i:**
```sql
-- yorum: 'borcu' → CLRNUMS.SENETCURR0_DEBIT, müşteri senedi borç bakiyesi toplamı.
SELECT TOP 10
    c."CODE" AS cari_kodu,
    c."DEFINITION_" AS unvan,
    SUM(r."SENETCURR0_DEBIT") AS senet_borcu
FROM CLRNUMS r
JOIN CLCARD c ON c."LOGICALREF" = r."CLCARDREF"
WHERE r."CLCARDREF" <> 0
GROUP BY c."CODE", c."DEFINITION_"
ORDER BY senet_borcu DESC
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
WITH B AS (SELECT L.CLIENTREF, SUM(CASE WHEN L.SIGN=0 THEN L.AMOUNT ELSE -L.AMOUNT END) bakiye
 FROM LG_411_01_CLFLINE L JOIN LG_411_CLCARD C ON C.LOGICALREF=L.CLIENTREF
 WHERE L.CANCELLED=0 AND C.CODE LIKE '120%' GROUP BY L.CLIENTREF) SELECT TOP 10 C.CODE, C.DEFINITION_, B.bakiye FROM B JOIN LG_411_CLCARD C ON C.LOGICALREF=B.CLIENTREF ORDER BY B.bakiye DESC
```

### M014 · Bu yıl müşterilerden toplam ne kadar tahsilat yaptık?

**Hüküm:** ❌ Yanlış değer — 1,28 Mr; doğru tahsilat 896,6 Mn  
**Referans tanımı:** Tahsilat = müşteri (120%) carilerinde 2026 alacak kayıtları: TRCODE 1 nakit tahsilat, 20 gelen havale, 61 çek girişi, 62 senet girişi, 70 kr

**Köprünün SQL'i:**
```sql
-- yorum: 'tahsilat' → PAYTRANS.TOTAL toplamı, MODULENR 4, SIGN 0, CANCELLED 0, 2026 yılı.
SELECT SUM(PAYTRANS."TOTAL") AS tahsilat_tutari
FROM PAYTRANS
WHERE PAYTRANS."CANCELLED" = 0
  AND PAYTRANS."MODULENR" = 4
  AND PAYTRANS."SIGN" = 0
  AND PAYTRANS."DATE_" >= '2026-01-01'
  AND PAYTRANS."DATE_" < '2027-01-01'
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT SUM(L.AMOUNT) tahsilat, COUNT(*) adet FROM LG_411_01_CLFLINE L JOIN LG_411_CLCARD C ON C.LOGICALREF=L.CLIENTREF WHERE L.CANCELLED=0 AND C.CODE LIKE '120%' AND L.SIGN=1 AND L.TRCODE IN (1,20,61,62,70) AND YEAR(L.DATE_)=YEAR(GETDATE())
```

### M015 · Vadesi geçmiş müşteri alacaklarımız toplam ne kadar?

**Hüküm:** ❌ Yanlış değer — −94,1 Mn (alacak eksi olamaz); doğru ~149,0 Mn  
**Referans tanımı:** Vadesi geçmiş müşteri alacağı. Logo'da ödeme kapama (PAYTRANS.PAID/CROSSREF) KULLANILMIYOR (116.514 satırın 14'ünde PAID≠0), bu yüzden FIFO:

**Köprünün SQL'i:**
```sql
-- yorum: 'vadesi' → AA_CAR_EKSTRE.VADE_TARİHİ kolonu, vade tarihi
-- yorum: 'alacaklarimiz' → AA_CAR_EKSTRE.ALACAK kolonu, alacak tutarı
-- yorum: 'gecmis' → AA_CAR_EKSTRE.VADE_TARİHİ < GETDATE() koşulu
SELECT SUM(AA_CAR_EKSTRE."ALACAK") AS toplam_vadesi_gecmis_alacak
FROM AA_CAR_EKSTRE
WHERE AA_CAR_EKSTRE."VADE_TARİHİ" < GETDATE()
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
WITH B AS (SELECT L.CLIENTREF, SUM(CASE WHEN L.SIGN=0 THEN L.AMOUNT ELSE -L.AMOUNT END) bakiye
 FROM LG_411_01_CLFLINE L JOIN LG_411_CLCARD C ON C.LOGICALREF=L.CLIENTREF
 WHERE L.CANCELLED=0 AND C.CODE LIKE '120%' GROUP BY L.CLIENTREF),
N AS (SELECT CARDREF, SUM(TOTAL) nd FROM LG_411_01_PAYTRANS WHERE CANCELLED=0 AND SIGN=0 AND DATE_ >= CAST(GETDATE() AS date) GROUP BY CARDREF)
SELECT SUM(CASE WHEN B.bakiye-ISNULL(N.nd,0) > 0 THEN B.bakiye-ISNULL(N.nd,0) ELSE 0 END) vadesi_gecmis,
 COUNT(CASE WHEN B.bakiye-ISNULL(N.nd,0) > 0 THEN 1 END) cari_sayisi, SUM(B.bakiye) toplam_bakiye
FROM B LEFT JOIN N ON N.CARDREF=B.CLIENTREF WHERE B.bakiye>0
```

### M016 · Alacaklarımızı 30, 60, 90 gün diye yaşlandırır mısın?

**Hüküm:** ⚠️ Gereksiz ret — Yaşlandırma reddedildi; ödeme kapama kullanılmıyor ama yaklaşık hesap mümkün  
**Referans tanımı:** Müşteri alacak yaşlandırması (FIFO): pozitif bakiye, cari başına en yeni PAYTRANS borç (SIGN=0) vade satırlarından geriye dağıtılır; dağıtıl

**Köprünün SQL'i:**
```sql
(SQL üretilmedi)
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
WITH B AS (SELECT L.CLIENTREF, SUM(CASE WHEN L.SIGN=0 THEN L.AMOUNT ELSE -L.AMOUNT END) bakiye
 FROM LG_411_01_CLFLINE L JOIN LG_411_CLCARD C ON C.LOGICALREF=L.CLIENTREF
 WHERE L.CANCELLED=0 AND C.CODE LIKE '120%' GROUP BY L.CLIENTREF),
P AS (SELECT P.CARDREF, P.DATE_, P.TOTAL, SUM(P.TOTAL) OVER (PARTITION BY P.CARDREF ORDER BY P.DATE_ DESC, P.LOGICALREF DESC ROWS UNBOUNDED PRECEDING) cum
 FROM LG_411_01_PAYTRANS P WHERE P.CANCELLED=0 AND P.SIGN=0 AND P.CARDREF IN (SELECT CLIENTREF FROM B WHERE bakiye>0)),
A AS (SELECT P.CARDREF, P.DATE_, CASE WHEN B.bakiye >= P.cum THEN P.TOTAL WHEN B.bakiye > P.cum - P.TOTAL THEN B.bakiye - (P.cum - P.TOTAL) ELSE 0 END acik
 FROM P JOIN B ON B.CLIENTREF=P.CARDREF)
SELECT kova, SUM(acik) tutar, COUNT(DISTINCT CARDREF) cari FROM (SELECT A.CARDREF, A.acik, CASE WHEN DATEDIFF(day, A.DATE_, CAST(GETDATE() AS date)) <= 0 THEN '0 vadesi gelmemiş'
 WHEN DATEDIFF(day, A.DATE_, CAST(GETDATE() AS date)) <= 30 THEN '1 1-30 gün'
 WHEN DATEDIFF(day, A.DATE_, CAST(GETDATE() AS date)) <= 60 THEN '2 31-60 gün'
 WHEN DATEDIFF(day, A.DATE_, CAST(GETDATE() AS date)) <= 90 THEN '3 61-90 gün' ELSE '4 90+ gün' END kova FROM A WHERE A.acik>0) x
GROUP BY kova
UNION ALL SELECT '5 plana dağıtılamayan', SUM(B.bakiye) - (SELECT SUM(acik) FROM A), NULL FROM B WHERE B.bakiye>0
ORDER BY 1
```

### M017 · Hangi müşterilerin bakiyesi bir milyon lirayı aşıyor?

**Hüküm:** ❌ Yanlış değer — 111 müşteri; doğru 25  
**Referans tanımı:** Müşteri (120%) cari bakiyesi (CLFLINE, açılış dahil, iptal hariç) > 1.000.000 TL olanlar.

**Köprünün SQL'i:**
```sql
-- yorum: 'bakiyesi' → MIND_VADE_RAPORU.Borc_Bakiyesi, toplam borç bakiyesi
-- yorum: 'lirayi' → MIND_VADE_RAPORU.Borc_Bakiyesi, 1.000.000 TL eşiği
SELECT
    m."Borc_Bakiyesi" AS bakiyesi
FROM MIND_VADE_RAPORU m
WHERE m."Borc_Bakiyesi" > 1000000
ORDER BY m."Borc_Bakiyesi" DESC
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
WITH B AS (SELECT L.CLIENTREF, SUM(CASE WHEN L.SIGN=0 THEN L.AMOUNT ELSE -L.AMOUNT END) bakiye
 FROM LG_411_01_CLFLINE L JOIN LG_411_CLCARD C ON C.LOGICALREF=L.CLIENTREF
 WHERE L.CANCELLED=0 AND C.CODE LIKE '120%' GROUP BY L.CLIENTREF) SELECT C.CODE, C.DEFINITION_, B.bakiye FROM B JOIN LG_411_CLCARD C ON C.LOGICALREF=B.CLIENTREF WHERE B.bakiye > 1000000 ORDER BY B.bakiye DESC
```

### M018 · Aylara göre tahsilat tutarlarımız nasıl dağılıyor?

**Hüküm:** ❌ Yanlış değer — Ocak 282 bin; aylık tahsilat ~110 Mn mertebesinde olmalı  
**Referans tanımı:** M014 tahsilat tanımı, 2026, ay kırılımı.

**Köprünün SQL'i:**
```sql
-- yorum: 'tahsilat' → LG_CLFLINE.MODULENR = 10 (Kasa) ve TRCODE = 1 (Nakit tahsilat) hareketlerinin AMOUNT toplamı.
SELECT 
    DATEFROMPARTS(YEAR("DATE_"), MONTH("DATE_"), 1) AS ay,
    SUM("AMOUNT") AS tahsilat_tutari
FROM LG_CLFLINE
WHERE "CANCELLED" = 0
  AND "MODULENR" = 10
  AND "TRCODE" = 1
GROUP BY DATEFROMPARTS(YEAR("DATE_"), MONTH("DATE_"), 1)
ORDER BY ay
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT MONTH(L.DATE_) ay, SUM(L.AMOUNT) tahsilat, COUNT(*) adet FROM LG_411_01_CLFLINE L JOIN LG_411_CLCARD C ON C.LOGICALREF=L.CLIENTREF WHERE L.CANCELLED=0 AND C.CODE LIKE '120%' AND L.SIGN=1 AND L.TRCODE IN (1,20,61,62,70) AND YEAR(L.DATE_)=YEAR(GETDATE()) GROUP BY MONTH(L.DATE_) ORDER BY 1
```

### M019 · Ortalama tahsilat süremiz kaç gün?

**Hüküm:** ❌ Yanlış değer — 30,3 gün; standart yöntemle 37,4 gün  
**Referans tanımı:** Ortalama tahsilat süresi (DSO) = dönem sonu müşteri net bakiyesi (120% cari, CLFLINE) ÷ dönem net satış faturaları (müşteri CLFLINE TRCODE 3

**Köprünün SQL'i:**
```sql
-- yorum: 'tahsilat' → PAYTRANS (MODULENR 4, SIGN 0) ile INVOICE (TRCODE 7,8,9) üzerinden DATEDIFF ile hesaplanır.
SELECT AVG(CAST(DATEDIFF(day, i."DATE_", p."DATE_") AS float)) AS ortalama_tahsilat_gun, COUNT(*) AS plan_kalemi
FROM PAYTRANS p
JOIN INVOICE i ON i."LOGICALREF" = p."FICHEREF"
WHERE p."MODULENR" = 4
  AND p."SIGN" = 0
  AND p."CANCELLED" = 0
  AND i."CANCELLED" = 0
  AND i."TRCODE" IN (7, 8, 9)
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
WITH B AS (SELECT L.CLIENTREF, SUM(CASE WHEN L.SIGN=0 THEN L.AMOUNT ELSE -L.AMOUNT END) bakiye
 FROM LG_411_01_CLFLINE L JOIN LG_411_CLCARD C ON C.LOGICALREF=L.CLIENTREF
 WHERE L.CANCELLED=0 AND C.CODE LIKE '120%' GROUP BY L.CLIENTREF),
S AS (SELECT SUM(CASE WHEN L.TRCODE IN (37,38,39) THEN L.AMOUNT WHEN L.TRCODE IN (32,33) THEN -L.AMOUNT ELSE 0 END) satis, DATEDIFF(day, DATEFROMPARTS(YEAR(GETDATE()),1,1), MAX(L.DATE_))+1 gun
 FROM LG_411_01_CLFLINE L JOIN LG_411_CLCARD C ON C.LOGICALREF=L.CLIENTREF WHERE L.CANCELLED=0 AND C.CODE LIKE '120%' AND YEAR(L.DATE_)=YEAR(GETDATE()))
SELECT (SELECT SUM(bakiye) FROM B) alacak, S.satis, S.gun, ROUND((SELECT SUM(bakiye) FROM B)/S.satis*S.gun,1) dso_gun FROM S
```

### M020 · Risk limitini aşmış müşteriler hangileri?

**Hüküm:** ✅ Doğru ret — Risk limiti hiç tanımlı değil, bunu söyledi  
**Referans tanımı:** Risk limiti aşımı = LG_411_01_CLRNUMS'ta limiti tanımlı (RISKLIMIT>0 veya ACCRISKLIMIT>0) ve risk toplamı limiti aşan müşteri.

**Köprünün SQL'i:**
```sql
-- yorum: 'risk' → CLRNUMS.ACCRISKTOTAL, cari açık hesap riski
-- yorum: 'limitini' → CLRNUMS.ACCRISKLIMIT, cari açık hesap risk limiti
-- yorum: 'asmis' → CLRNUMS.ACCRISKTOTAL > CLRNUMS.ACCRISKLIMIT ve ACCRISKLIMIT > 0
SELECT
    c."CODE" AS cari_kodu,
    c."DEFINITION_" AS unvan,
    r."ACCRISKLIMIT" AS risk_limiti,
    ISNULL(r."ACCRISKTOTAL", 0) AS acik_risk,
    ISNULL(r."ACCRISKTOTAL", 0) - r."ACCRISKLIMIT" AS asim_tutari
FROM CLRNUMS r
JOIN CLCARD c ON c."LOGICALREF" = r."CLCARDREF"
WHERE r."ACCRISKLIMIT" > 0
  AND ISNULL(r."ACCRISKTOTAL", 0) > r."ACCRISKLIMIT"
ORDER BY asim_tutari DESC
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT COUNT(*) kayit, SUM(CASE WHEN RISKLIMIT>0 OR ACCRISKLIMIT>0 OR CSTCSRISKLIMIT>0 OR MYCSRISKLIMIT>0 THEN 1 ELSE 0 END) limit_tanimli,
 SUM(CASE WHEN (RISKLIMIT>0 AND RISKTOTAL>RISKLIMIT) OR (ACCRISKLIMIT>0 AND ACCRISKTOTAL>ACCRISKLIMIT) THEN 1 ELSE 0 END) asan FROM LG_411_01_CLRNUMS
```

### M021 · Bu yıl hiç ödeme yapmamış ama borcu olan müşteriler var mı?

**Hüküm:** ❌ SQL hatası — CLFLINE'da olmayan CARDREF kolonu  
**Referans tanımı:** Müşteri (120%) cari bakiyesi > 0 ve 2026'da hiç tahsilat kaydı (M014 tanımı: TRCODE 1,20,61,62,70, SIGN=1) olmayan cariler.

**Köprünün SQL'i:**
```sql
-- yorum: 'odeme' → PAYTRANS (MODULENR 4, SIGN 0, CANCELLED 0) tahsilat kaydı
-- yorum: 'borcu' → CLFLINE borç-alacak bakiyesi (borç > alacak)
-- yorum: 'yapmamis' → NOT EXISTS: PAYTRANS'ta tahsilat kaydı olmayan cariler
SELECT 
    c."CODE" AS cari_kodu,
    c."DEFINITION_" AS unvan,
    ISNULL(b.bakiye, 0) AS borc_bakiyesi
FROM CLCARD c
LEFT JOIN (
    SELECT 
        "CARDREF",
        SUM(CASE WHEN "SIGN" = 0 THEN "AMOUNT" ELSE 0 END) - 
        SUM(CASE WHEN "SIGN" = 1 THEN "AMOUNT" ELSE 0 END) AS bakiye
    FROM dbo_LG_411_01_CLFLINE
    WHERE "CANCELLED" = 0
    GROUP BY "CARDREF"
    HAVING SUM(CASE WHEN "SIGN" = 0 THEN "AMOUNT" ELSE 0 END) - 
           SUM(CASE WHEN "SIGN" = 1 THEN "AMOUNT" ELSE 0 END) > 0
) b ON c."LOGICALREF" = b."CARDREF"
WHERE c."ACTIVE" = 0
  AND b."CARDREF" IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 
      FROM PAYTRANS p
      WHERE p."CARDREF" = c."LOGICALREF"
        AND p."MODULENR" = 4
        AND p."SIGN" = 0
        AND p."CANCELLED" = 0
        AND p."DATE_" >= '2026-01-01'
        AND p."DATE_" < '2027-01-01'
  )
ORDER BY b.bakiye DESC
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
WITH B AS (SELECT L.CLIENTREF, SUM(CASE WHEN L.SIGN=0 THEN L.AMOUNT ELSE -L.AMOUNT END) bakiye
 FROM LG_411_01_CLFLINE L JOIN LG_411_CLCARD C ON C.LOGICALREF=L.CLIENTREF
 WHERE L.CANCELLED=0 AND C.CODE LIKE '120%' GROUP BY L.CLIENTREF) SELECT C.CODE, C.DEFINITION_, B.bakiye FROM B JOIN LG_411_CLCARD C ON C.LOGICALREF=B.CLIENTREF WHERE B.bakiye>0
AND NOT EXISTS (SELECT 1 FROM LG_411_01_CLFLINE L WHERE L.CLIENTREF=B.CLIENTREF AND L.CANCELLED=0 AND L.SIGN=1 AND L.TRCODE IN (1,20,61,62,70) AND YEAR(L.DATE_)=YEAR(GETDATE())) ORDER BY B.bakiye DESC
```

### M022 · Müşteri cari hareketlerinde en çok hangi işlem türü var?

**Hüküm:** ✅ Doğru — 37 → 49.548, 38 → 21.009, birebir  
**Referans tanımı:** Müşteri (120%) cari hareketleri (CLFLINE, iptal hariç, 2026) TRCODE bazında adet; etiket katalog CLFLINE.TRCODE açıklamasından (14 = açılış,

**Köprünün SQL'i:**
```sql
-- yorum: 'islem' → LG_CLFLINE."TRCODE" kolonu, hareket türü kırılımı
SELECT "TRCODE" AS islem_turu, COUNT(*) AS hareket_sayisi
FROM LG_CLFLINE
WHERE "CANCELLED" = 0
GROUP BY "TRCODE"
ORDER BY hareket_sayisi DESC
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT L.TRCODE, CASE L.TRCODE WHEN 1 THEN 'Nakit tahsilat' WHEN 2 THEN 'Nakit ödeme' WHEN 3 THEN 'Borç dekontu' WHEN 4 THEN 'Alacak dekontu' WHEN 5 THEN 'Virman' WHEN 6 THEN 'Kur farkı'
 WHEN 14 THEN 'Açılış' WHEN 20 THEN 'Gelen havale' WHEN 21 THEN 'Gönderilen havale' WHEN 31 THEN 'Mal alım fat' WHEN 32 THEN 'Perakende satış iade fat' WHEN 33 THEN 'Toptan satış iade fat'
 WHEN 34 THEN 'Alınan hizmet fat' WHEN 36 THEN 'Alım iade fat' WHEN 37 THEN 'Perakende satış fat' WHEN 38 THEN 'Toptan satış fat' WHEN 39 THEN 'Verilen hizmet fat'
 WHEN 61 THEN 'Çek girişi' WHEN 62 THEN 'Senet girişi' WHEN 63 THEN 'Çek çıkışı' WHEN 64 THEN 'Senet çıkışı' WHEN 70 THEN 'Kredi kartı fişi' ELSE CAST(L.TRCODE AS varchar) END tur,
 COUNT(*) adet, SUM(L.AMOUNT) tutar FROM LG_411_01_CLFLINE L JOIN LG_411_CLCARD C ON C.LOGICALREF=L.CLIENTREF WHERE L.CANCELLED=0 AND C.CODE LIKE '120%' AND YEAR(L.DATE_)=YEAR(GETDATE()) GROUP BY L.TRCODE ORDER BY COUNT(*) DESC
```

### M023 · Tahsilatlarımız geçen yıla göre arttı mı?

**Hüküm:** ❌ Yanlış değer — 2026: 84,8 Mn (doğru 896,6 Mn) ve eş dönem uygulanmadı  
**Referans tanımı:** Tahsilat (M014 tanımı) 2026 01.01–son veri günü vs 2025 aynı gün aralığı (LG_211 tabloları, 120% cari); ayrıca 2025 tam yıl.

**Köprünün SQL'i:**
```sql
-- yorum: 'tahsilatlarimiz' → LG_CLFLINE.AMOUNT, TRCODE=1 (nakit tahsilat), CANCELLED=0, 2025 ve 2026 karşılaştırması
SELECT 
    SUM(CASE WHEN "DATE_" >= '2025-01-01' AND "DATE_" < '2026-01-01' THEN "AMOUNT" ELSE 0 END) AS tahsilat_2025,
    SUM(CASE WHEN "DATE_" >= '2026-01-01' AND "DATE_" < '2027-01-01' THEN "AMOUNT" ELSE 0 END) AS tahsilat_2026
FROM LG_CLFLINE
WHERE "TRCODE" = 1
  AND "CANCELLED" = 0
  AND "DATE_" >= '2025-01-01'
  AND "DATE_" < '2027-01-01'
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
WITH M AS (SELECT MAX(DATE_) mx FROM LG_411_01_CLFLINE WHERE CANCELLED=0),
T26 AS (SELECT SUM(L.AMOUNT) t FROM LG_411_01_CLFLINE L JOIN LG_411_CLCARD C ON C.LOGICALREF=L.CLIENTREF WHERE L.CANCELLED=0 AND C.CODE LIKE '120%' AND L.SIGN=1 AND L.TRCODE IN (1,20,61,62,70) AND YEAR(L.DATE_)=YEAR(GETDATE())),
T25 AS (SELECT SUM(CASE WHEN L.DATE_ <= DATEADD(year,-1,M.mx) THEN L.AMOUNT ELSE 0 END) ayni_donem, SUM(L.AMOUNT) tam_yil FROM LG_211_01_CLFLINE L JOIN LG_211_CLCARD C ON C.LOGICALREF=L.CLIENTREF CROSS JOIN M
 WHERE L.CANCELLED=0 AND C.CODE LIKE '120%' AND L.SIGN=1 AND L.TRCODE IN (1,20,61,62,70) AND YEAR(L.DATE_)=YEAR(GETDATE())-1)
SELECT T26.t tahsilat_2026, T25.ayni_donem tahsilat_2025_ayni_donem, T25.tam_yil tahsilat_2025_tam, ROUND((T26.t/T25.ayni_donem-1)*100,1) degisim_yuzde FROM T26, T25
```

### M024 · En büyük beş müşterinin toplam alacak içindeki payı yüzde kaç?

**Hüküm:** ❌ SQL hatası — AA_CAR_EKSTRE görünümünde olmayan kolon  
**Referans tanımı:** En büyük 5 müşterinin (120% cari, pozitif bakiye) bakiyesinin, borç bakiyeli tüm müşterilerin toplam bakiyesine oranı.

**Köprünün SQL'i:**
```sql
-- yorum: 'alacak' → AA_CAR_EKSTRE.ALACAK kolonu, toplam alacak tutarı.
-- yorum: 'alacak' → AA_CAR_EKSTRE.ALACAK kolonu, cari bazında toplam alacak tutarı.
WITH customer_receivables AS (
    SELECT 
        c."CODE" AS cari_kodu,
        c."DEFINITION_" AS unvan,
        SUM(e."ALACAK") AS toplam_alacak
    FROM AA_CAR_EKSTRE e
    JOIN CLCARD c ON c."CODE" = e."CARIKODU"
    WHERE e."ALACAK" > 0
    GROUP BY c."CODE", c."DEFINITION_"
),
ranked AS (
    SELECT 
        cari_kodu,
        unvan,
        toplam_alacak,
        SUM(toplam_alacak) OVER () AS genel_toplam_alacak
    FROM customer_receivables
)
SELECT TOP 5
    cari_kodu,
    unvan,
    toplam_alacak,
    (toplam_alacak / NULLIF(genel_toplam_alacak, 0)) * 100 AS pay_yuzde
FROM ranked
ORDER BY toplam_alacak DESC
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
WITH B AS (SELECT L.CLIENTREF, SUM(CASE WHEN L.SIGN=0 THEN L.AMOUNT ELSE -L.AMOUNT END) bakiye
 FROM LG_411_01_CLFLINE L JOIN LG_411_CLCARD C ON C.LOGICALREF=L.CLIENTREF
 WHERE L.CANCELLED=0 AND C.CODE LIKE '120%' GROUP BY L.CLIENTREF), T AS (SELECT TOP 5 bakiye FROM B WHERE bakiye>0 ORDER BY bakiye DESC)
SELECT (SELECT SUM(bakiye) FROM T) ilk5, SUM(bakiye) toplam_pozitif, ROUND((SELECT SUM(bakiye) FROM T)/SUM(bakiye)*100,2) pay_yuzde,
 ROUND((SELECT SUM(bakiye) FROM T)/(SELECT SUM(bakiye) FROM B)*100,2) pay_net_toplama_gore FROM B WHERE bakiye>0
```

### M025 · En çok borcumuz olan on tedarikçi hangisi?

**Hüküm:** ❌ Yanlış değer — Çek borcunu listeledi; soru tedarikçi cari borcu  
**Referans tanımı:** Tedarikçi = cari kodu 320 ile başlayan. Borcumuz = Σ(SIGN1 alacak − SIGN0 borç) CLFLINE, iptal hariç, açılış dahil. İlk 10.

**Köprünün SQL'i:**
```sql
-- yorum: 'tedarikçi çek borcu' → CLRNUMS.CEK1_DEBIT (cari risk tablosunda tedarikçi çek borcu)
-- yorum: 'tedarikçi senet borcu' → CLRNUMS.SENET1_DEBIT (cari risk tablosunda tedarikçi senet borcu)
SELECT TOP 10
    c."CODE" AS cari_kodu,
    c."DEFINITION_" AS unvan,
    ISNULL(r."CEK1_DEBIT", 0) AS cek_borcu,
    ISNULL(r."SENET1_DEBIT", 0) AS senet_borcu,
    ISNULL(r."CEK1_DEBIT", 0) + ISNULL(r."SENET1_DEBIT", 0) AS toplam_borcu
FROM CLRNUMS r
JOIN CLCARD c ON c."LOGICALREF" = r."CLCARDREF"
WHERE r."CEK1_DEBIT" > 0 OR r."SENET1_DEBIT" > 0
ORDER BY toplam_borcu DESC
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
WITH B AS (SELECT L.CLIENTREF, SUM(CASE WHEN L.SIGN=1 THEN L.AMOUNT ELSE -L.AMOUNT END) bakiye
 FROM LG_411_01_CLFLINE L JOIN LG_411_CLCARD C ON C.LOGICALREF=L.CLIENTREF
 WHERE L.CANCELLED=0 AND C.CODE LIKE '320%' GROUP BY L.CLIENTREF) SELECT TOP 10 C.CODE, C.DEFINITION_, B.bakiye FROM B JOIN LG_411_CLCARD C ON C.LOGICALREF=B.CLIENTREF ORDER BY B.bakiye DESC
```

### M026 · Bu yıl tedarikçilere toplam ne kadar ödeme yaptık?

**Hüküm:** ❌ Yanlış değer — 65,3 Mn = 7'li hesap GİDERİ; tedarikçi ödemesi 482,7 Mn  
**Referans tanımı:** Tedarikçi ödemesi = 320% carilerde 2026 borç kayıtları: TRCODE 2 nakit ödeme, 21 gönderilen havale, 63 çek çıkışı, 64 senet çıkışı, 72 firma

**Köprünün SQL'i:**
```sql
-- yorum: 'odeme' → EMFLINE'da gider hesaplarında (7%) DEBIT-CREDIT toplamı, tedarikçiye yapılan ödeme.
SELECT SUM(EMFLINE."DEBIT" - EMFLINE."CREDIT") AS toplam_odeme
FROM [dbo].[EMFLINE] AS EMFLINE
WHERE EMFLINE."CANCELLED" = 0
  AND EMFLINE."ACCOUNTCODE" LIKE '7%'
  AND EMFLINE."DATE_" >= '2026-01-01' AND EMFLINE."DATE_" < '2027-01-01'
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT SUM(L.AMOUNT) odeme, COUNT(*) adet FROM LG_411_01_CLFLINE L JOIN LG_411_CLCARD C ON C.LOGICALREF=L.CLIENTREF WHERE L.CANCELLED=0 AND C.CODE LIKE '320%' AND L.SIGN=0 AND L.TRCODE IN (2,21,63,64,72) AND YEAR(L.DATE_)=YEAR(GETDATE())
```

### M027 · Vadesi gelmiş ama henüz ödenmemiş satıcı borçlarımız ne kadar?

**Hüküm:** ❌ Veri varken 'yok' — 'kayıt yok'; vadesi geçmiş satıcı borcu ~87,8 Mn  
**Referans tanımı:** Vadesi gelmiş ödenmemiş satıcı borcu, FIFO (M015 aynası): tedarikçi alacak bakiyesi − vadesi gelmemiş (PAYTRANS SIGN=1, DATE_ ≥ bugün) alaca

**Köprünün SQL'i:**
```sql
-- yorum: 'odenmis' → LG_CSCARD.CURRSTAT <> 8 (tahsil edilmemiş)
-- yorum: 'vadesi' → LG_CSCARD.DUEDATE, vade tarihi
-- yorum: 'satici' → LG_CSCARD.DOC = 4 (borç senedimiz)
-- yorum: 'borclarimiz' → LG_CSCARD.AMOUNT, senet tutarı
-- yorum: 'gelmis' → LG_CSCARD.DUEDATE <= GETDATE()
-- yorum: 'odenmemis' → LG_CSCARD.CURRSTAT <> 8 (tahsil edilmemiş)
SELECT SUM(LG_CSCARD.[AMOUNT]) AS odenmemis_borc_senet_tutari
FROM [dbo].[LG_CSCARD] AS LG_CSCARD
WHERE LG_CSCARD.[CANCELLED] = 0
  AND LG_CSCARD.[DOC] = 4
  AND LG_CSCARD.[DUEDATE] <= GETDATE()
  AND LG_CSCARD.[CURRSTAT] <> 8
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
WITH B AS (SELECT L.CLIENTREF, SUM(CASE WHEN L.SIGN=1 THEN L.AMOUNT ELSE -L.AMOUNT END) bakiye
 FROM LG_411_01_CLFLINE L JOIN LG_411_CLCARD C ON C.LOGICALREF=L.CLIENTREF
 WHERE L.CANCELLED=0 AND C.CODE LIKE '320%' GROUP BY L.CLIENTREF),
N AS (SELECT CARDREF, SUM(TOTAL) nd FROM LG_411_01_PAYTRANS WHERE CANCELLED=0 AND SIGN=1 AND DATE_ >= CAST(GETDATE() AS date) GROUP BY CARDREF)
SELECT SUM(CASE WHEN B.bakiye-ISNULL(N.nd,0) > 0 THEN B.bakiye-ISNULL(N.nd,0) ELSE 0 END) vadesi_gecmis,
 COUNT(CASE WHEN B.bakiye-ISNULL(N.nd,0) > 0 THEN 1 END) cari_sayisi, SUM(B.bakiye) toplam_bakiye
FROM B LEFT JOIN N ON N.CARDREF=B.CLIENTREF WHERE B.bakiye>0
```

### M028 · Satıcı borçlarımızı vadesine göre yaşlandırır mısın?

**Hüküm:** ⚠️ Gereksiz ret — 'satıcı' tanımsız diye reddetti  
**Referans tanımı:** Satıcı borç yaşlandırması FIFO (M016 aynası; PAYTRANS SIGN=1 vadeleri).

**Köprünün SQL'i:**
```sql
(SQL üretilmedi)
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
WITH B AS (SELECT L.CLIENTREF, SUM(CASE WHEN L.SIGN=1 THEN L.AMOUNT ELSE -L.AMOUNT END) bakiye
 FROM LG_411_01_CLFLINE L JOIN LG_411_CLCARD C ON C.LOGICALREF=L.CLIENTREF
 WHERE L.CANCELLED=0 AND C.CODE LIKE '320%' GROUP BY L.CLIENTREF),
P AS (SELECT P.CARDREF, P.DATE_, P.TOTAL, SUM(P.TOTAL) OVER (PARTITION BY P.CARDREF ORDER BY P.DATE_ DESC, P.LOGICALREF DESC ROWS UNBOUNDED PRECEDING) cum
 FROM LG_411_01_PAYTRANS P WHERE P.CANCELLED=0 AND P.SIGN=1 AND P.CARDREF IN (SELECT CLIENTREF FROM B WHERE bakiye>0)),
A AS (SELECT P.CARDREF, P.DATE_, CASE WHEN B.bakiye >= P.cum THEN P.TOTAL WHEN B.bakiye > P.cum - P.TOTAL THEN B.bakiye - (P.cum - P.TOTAL) ELSE 0 END acik
 FROM P JOIN B ON B.CLIENTREF=P.CARDREF)
SELECT kova, SUM(acik) tutar, COUNT(DISTINCT CARDREF) cari FROM (SELECT A.CARDREF, A.acik, CASE WHEN DATEDIFF(day, A.DATE_, CAST(GETDATE() AS date)) <= 0 THEN '0 vadesi gelmemiş'
 WHEN DATEDIFF(day, A.DATE_, CAST(GETDATE() AS date)) <= 30 THEN '1 1-30 gün'
 WHEN DATEDIFF(day, A.DATE_, CAST(GETDATE() AS date)) <= 60 THEN '2 31-60 gün'
 WHEN DATEDIFF(day, A.DATE_, CAST(GETDATE() AS date)) <= 90 THEN '3 61-90 gün' ELSE '4 90+ gün' END kova FROM A WHERE A.acik>0) x
GROUP BY kova
UNION ALL SELECT '5 plana dağıtılamayan', SUM(B.bakiye) - (SELECT SUM(acik) FROM A), NULL FROM B WHERE B.bakiye>0
ORDER BY 1
```

### M029 · Aylara göre tedarikçi ödemelerimiz nasıl?

**Hüküm:** ❌ Yanlış değer — 3.699 tek tek satır; soru aylık toplam  
**Referans tanımı:** M026 ödeme tanımı, 2026, ay kırılımı.

**Köprünün SQL'i:**
```sql
-- yorum: 'odemelerimiz' → PAYTRANS (MODULENR 4, SIGN 1, CANCELLED 0) tedarikçiye yapılan ödemeler, CLCARD üzerinden tedarikçi kırılımı
SELECT 
    DATEFROMPARTS(YEAR(p."DATE_"), MONTH(p."DATE_"), 1) AS ay,
    c."CODE" AS tedarikci_kodu,
    c."DEFINITION_" AS tedarikci_unvani,
    SUM(p."TOTAL") AS odeme_tutari
FROM PAYTRANS p
INNER JOIN CLCARD c ON p."CARDREF" = c."LOGICALREF"
WHERE p."CANCELLED" = 0
  AND p."MODULENR" = 4
  AND p."SIGN" = 1
GROUP BY 
    DATEFROMPARTS(YEAR(p."DATE_"), MONTH(p."DATE_"), 1),
    c."CODE",
    c."DEFINITION_"
ORDER BY ay, odeme_tutari DESC
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT MONTH(L.DATE_) ay, SUM(L.AMOUNT) odeme, COUNT(*) adet FROM LG_411_01_CLFLINE L JOIN LG_411_CLCARD C ON C.LOGICALREF=L.CLIENTREF WHERE L.CANCELLED=0 AND C.CODE LIKE '320%' AND L.SIGN=0 AND L.TRCODE IN (2,21,63,64,72) AND YEAR(L.DATE_)=YEAR(GETDATE()) GROUP BY MONTH(L.DATE_) ORDER BY 1
```

### M030 · Bu yıl alış faturası kestiğimiz kaç farklı tedarikçi var?

**Hüküm:** ❌ Yanlış değer — 0; alış faturası kesilen 1.274 tedarikçi  
**Referans tanımı:** Alış faturası = INVOICE TRCODE 1 (mal alım) + 4 (alınan hizmet), iptal hariç, 2026; farklı CLIENTREF sayısı.

**Köprünün SQL'i:**
```sql
-- yorum: 'alis' → INVOICE.TRCODE IN (1,4) alış faturaları; farklı tedarikçi sayısı COUNT(DISTINCT CLIENTREF)
-- yorum: 'alis' → INVOICE.GRPCODE = 1 (Alış Faturası) ve TRCODE IN (2,3,7,8,9) kısıtıyla farklı tedarikçi sayısı
SELECT COUNT(DISTINCT "CLIENTREF") AS tedarikci_sayisi
FROM INVOICE
WHERE "GRPCODE" = 1
  AND "TRCODE" IN (2, 3, 7, 8, 9)
  AND "CANCELLED" = 0
  AND "DATE_" >= '2026-01-01'
  AND "DATE_" < '2027-01-01'
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT COUNT(DISTINCT CLIENTREF) tedarikci, SUM(CASE WHEN TRCODE=1 THEN 1 ELSE 0 END) mal_alim_fatura, COUNT(*) fatura FROM LG_411_01_INVOICE WHERE CANCELLED=0 AND TRCODE IN (1,4) AND YEAR(DATE_)=YEAR(GETDATE())
```

### M031 · Alış faturalarımızın toplam tutarı ne kadar?

**Hüküm:** ❌ Veri varken 'yok' — 'kayıt yok'; alış faturaları 492,4 Mn (KDV dahil)  
**Referans tanımı:** Alış faturası toplamı = INVOICE TRCODE 1+4, iptal hariç, 2026; NETTOTAL (KDV dahil, cariye yansıyan; CLFLINE TRCODE 31 toplamıyla birebir) v

**Köprünün SQL'i:**
```sql
-- yorum: 'alis' → INVOICE.TRCODE IN (1,4) satınalma faturaları, toplam GROSSTOTAL
SELECT SUM(INVOICE.[GROSSTOTAL]) AS toplam_tutar
FROM [dbo].[INVOICE] AS INVOICE
WHERE INVOICE.[CANCELLED] = 0
  AND INVOICE.[TRCODE] IN (2, 3, 7, 8, 9)
  AND INVOICE.[TRCODE] IN (1, 4)
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT SUM(CASE WHEN TRCODE IN (1,4) THEN NETTOTAL ELSE 0 END) kdv_dahil, SUM(CASE WHEN TRCODE IN (1,4) THEN NETTOTAL-TOTALVAT ELSE 0 END) kdv_haric,
 SUM(CASE WHEN TRCODE=6 THEN NETTOTAL ELSE 0 END) alim_iade_kdv_dahil FROM LG_411_01_INVOICE WHERE CANCELLED=0 AND TRCODE IN (1,4,6) AND YEAR(DATE_)=YEAR(GETDATE())
```

### M032 · Ortalama ödeme süremiz kaç gün?

**Hüküm:** ❌ Yanlış değer — 'Belirtilmemiş'; standart yöntemle 28,8 gün  
**Referans tanımı:** Ortalama ödeme süresi (DPO) = dönem sonu tedarikçi (320%) net alacak bakiyesi ÷ dönem net alış faturaları (tedarikçi CLFLINE TRCODE 31,34 − 

**Köprünün SQL'i:**
```sql
-- yorum: 'odeme' → PAYTRANS (MODULENR 4, SIGN 0) ile INVOICE (TRCODE 7,8,9) üzerinden fatura tarihinden kapatan ödeme tarihine DATEDIFF ortalaması.
SELECT AVG(CAST(DATEDIFF(day, i."DATE_", o."DATE_") AS float)) AS ortalama_odeme_suresi_gun,
       COUNT(*) AS kapanan_kalem
FROM PAYTRANS p
JOIN INVOICE i ON i."LOGICALREF" = p."FICHEREF"
JOIN PAYTRANS o ON o."LOGICALREF" = p."CROSSREF"
WHERE p."MODULENR" = 4
  AND p."SIGN" = 0
  AND p."CANCELLED" = 0
  AND i."CANCELLED" = 0
  AND i."TRCODE" IN (7, 8, 9)
  AND i."DATE_" >= '2026-01-01'
  AND i."DATE_" < '2027-01-01'
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
WITH B AS (SELECT L.CLIENTREF, SUM(CASE WHEN L.SIGN=1 THEN L.AMOUNT ELSE -L.AMOUNT END) bakiye
 FROM LG_411_01_CLFLINE L JOIN LG_411_CLCARD C ON C.LOGICALREF=L.CLIENTREF
 WHERE L.CANCELLED=0 AND C.CODE LIKE '320%' GROUP BY L.CLIENTREF),
S AS (SELECT SUM(CASE WHEN L.TRCODE IN (31,34) THEN L.AMOUNT WHEN L.TRCODE=36 THEN -L.AMOUNT ELSE 0 END) alis, DATEDIFF(day, DATEFROMPARTS(YEAR(GETDATE()),1,1), MAX(L.DATE_))+1 gun
 FROM LG_411_01_CLFLINE L JOIN LG_411_CLCARD C ON C.LOGICALREF=L.CLIENTREF WHERE L.CANCELLED=0 AND C.CODE LIKE '320%' AND YEAR(L.DATE_)=YEAR(GETDATE()))
SELECT (SELECT SUM(bakiye) FROM B) borc, S.alis, S.gun, ROUND((SELECT SUM(bakiye) FROM B)/S.alis*S.gun,1) dpo_gun FROM S
```

### M033 · En büyük alış faturası hangi tedarikçiden?

**Hüküm:** ❌ Veri varken 'yok' — 'kayıt yok'; alış faturası var  
**Referans tanımı:** En büyük alış faturası = INVOICE TRCODE 1/4, iptal hariç, 2026, en yüksek NETTOTAL; tedarikçi CLCARD.

**Köprünün SQL'i:**
```sql
-- yorum: 'alis' → INVOICE.TRCODE IN (1,4) satınalma faturaları, tutar NETTOTAL.
SELECT c.[CODE] AS cari_kodu, c.[DEFINITION_] AS tedarikci, i.[FICHENO] AS fatura_no, i.[DATE_] AS fatura_tarihi, i.[NETTOTAL] AS tutar
FROM INVOICE AS i
JOIN CLCARD AS c ON i.[CLIENTREF] = c.[LOGICALREF]
WHERE i.[TRCODE] IN (1, 4)
  AND i.[TRCODE] IN (2, 3, 7, 8, 9)
  AND i.[CANCELLED] = 0
ORDER BY i.[NETTOTAL] DESC
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT TOP 3 I.FICHENO, I.DATE_, I.TRCODE, I.NETTOTAL, I.NETTOTAL-I.TOTALVAT kdv_haric, C.CODE, C.DEFINITION_ FROM LG_411_01_INVOICE I JOIN LG_411_CLCARD C ON C.LOGICALREF=I.CLIENTREF
WHERE I.CANCELLED=0 AND I.TRCODE IN (1,4) AND YEAR(I.DATE_)=YEAR(GETDATE()) ORDER BY I.NETTOTAL DESC
```

### M034 · Satıcılara olan borcumuz geçen aya göre arttı mı?

**Hüküm:** ❌ Veri varken 'yok' — 'kayıt yok'; satıcı borcu önceki ay 73,3 Mn  
**Referans tanımı:** 320 Satıcılar muhasebe alacak bakiyesi geçen ay sonu (EOMONTH(GETDATE(),-1) = 31.08.2026) vs önceki ay sonu (31.07.2026). Veri 17.08'de biti

**Köprünün SQL'i:**
```sql
-- yorum: 'saticilara' → CLCARD.SPECODE2 = 'TEDARIKCI' ile tedarikçi cariler, LG_CLFLINE borç-alacak bakiyesi
-- yorum: 'saticilara' → CLCARD.SPECODE2 = 'TEDARIKCI' ile tedarikçi cariler, LG_CLFLINE AMOUNT ile borç-alacak bakiyesi
SELECT
    SUM(CASE WHEN l."DATE_" >= '2026-08-01' AND l."DATE_" < '2026-09-01' 
             THEN ISNULL(l."AMOUNT", 0) ELSE 0 END) AS borc_bakiyesi_gecen_ay,
    SUM(CASE WHEN l."DATE_" >= '2026-09-01' AND l."DATE_" < '2026-10-01' 
             THEN ISNULL(l."AMOUNT", 0) ELSE 0 END) AS borc_bakiyesi_bu_ay
FROM LG_CLFLINE l
JOIN CLCARD c ON l."CLIENTREF" = c."LOGICALREF"
WHERE l."CANCELLED" = 0
  AND c."SPECODE2" = 'TEDARIKCI'
  AND l."DATE_" >= '2026-08-01'
  AND l."DATE_" < '2026-10-01'
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT SUM(CASE WHEN L.DATE_ <= EOMONTH(GETDATE(),-2) THEN L.CREDIT-L.DEBIT ELSE 0 END) onceki_ay_sonu,
 SUM(CASE WHEN L.DATE_ <= EOMONTH(GETDATE(),-1) THEN L.CREDIT-L.DEBIT ELSE 0 END) gecen_ay_sonu FROM LG_411_01_EMFLINE L WHERE L.CANCELLED=0 AND L.ACCOUNTCODE LIKE '320%'
```

### M035 · Banka hesaplarımızın bakiyeleri ne?

**Hüküm:** ❌ Yanlış değer — 55 satır ve bakiyeler tutmuyor; referans 13 banka hesabı bakiyesi  
**Referans tanımı:** Banka hesap bakiyeleri = muhasebe 102 alt (muavin) hesap bazında Σ(borç − alacak), açılış dahil, iptal hariç; sıfır ve hareketsiz hesaplar h

**Köprünün SQL'i:**
```sql
-- yorum: 'bakiyeleri' → LG_BNFLINE.AMOUNT, SIGN 0 giriş, 1 çıkış; net bakiye = giriş - çıkış.
SELECT 
    ba."CODE" AS hesap_kodu,
    ba."DEFINITION_" AS hesap_adi,
    SUM(CASE WHEN b."SIGN" = 0 THEN b."AMOUNT" ELSE -b."AMOUNT" END) AS bakiye
FROM LG_BNFLINE b
JOIN BANKACC ba ON b."BNACCREF" = ba."LOGICALREF"
WHERE b."CANCELLED" = 0
GROUP BY ba."CODE", ba."DEFINITION_"
ORDER BY ba."CODE"
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT A.CODE, A.DEFINITION_, SUM(L.DEBIT-L.CREDIT) bakiye FROM LG_411_01_EMFLINE L JOIN LG_411_EMUHACC A ON A.LOGICALREF=L.ACCOUNTREF
WHERE L.CANCELLED=0 AND L.ACCOUNTCODE LIKE '102%' GROUP BY A.CODE, A.DEFINITION_ HAVING ABS(SUM(L.DEBIT-L.CREDIT))>0.005 ORDER BY 3 DESC
```

### M036 · Bu yıl bankalara toplam ne kadar para girdi ve çıktı?

**Hüküm:** ✅ Doğru (2. okuma) — Banka modülü okuması (2,34/1,85 Mr); muhasebe 102'ye göre 1,53/1,40 Mr  
**Referans tanımı:** Bankalara giren/çıkan (ana okuma) = muhasebe 102 hesapları 2026 borç (giriş) ve alacak (çıkış) toplamı, açılış fişi (EMFICHE TRCODE 1) hariç

**Köprünün SQL'i:**
```sql
-- yorum: 'para' → LG_BNFLINE.AMOUNT, SIGN ile giriş/çıkış ayrımı
SELECT 
    SUM(CASE WHEN LG_BNFLINE.[SIGN] = 0 THEN LG_BNFLINE.[AMOUNT] ELSE 0 END) AS giren_para,
    SUM(CASE WHEN LG_BNFLINE.[SIGN] = 1 THEN LG_BNFLINE.[AMOUNT] ELSE 0 END) AS cikan_para
FROM LG_BNFLINE
WHERE LG_BNFLINE.[CANCELLED] = 0
  AND LG_BNFLINE.[DATE_] >= '2026-01-01' 
  AND LG_BNFLINE.[DATE_] < '2027-01-01'
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT SUM(L.DEBIT) giris, SUM(L.CREDIT) cikis, SUM(L.DEBIT-L.CREDIT) net FROM LG_411_01_EMFLINE L WHERE L.CANCELLED=0 AND L.ACCOUNTCODE LIKE '102%' AND YEAR(L.DATE_)=YEAR(GETDATE()) AND L.ACCFICHEREF NOT IN (SELECT LOGICALREF FROM LG_411_01_EMFICHE WHERE TRCODE=1)
```

### M037 · Hangi bankada en çok hareket var?

**Hüküm:** ✅ Doğru (2. okuma) — Kuveyt Türk en hareketli; banka modülü okuması  
**Referans tanımı:** Hareket = banka modülü satır sayısı (BNFLINE, iptal hariç, 2026, açılış TRCODE 5 ve devir MODULENR 666 hariç), banka kartı (BNCARD) bazında;

**Köprünün SQL'i:**
```sql
-- yorum: 'banka' → BNCARD.LOGICALREF, LG_BNFLINE.BANKREF ile JOIN; 'en çok hareket' → COUNT(*) azalan.
/* yorum: 'banka' → BNCARD.LOGICALREF, LG_BNFLINE.BANKREF ile JOIN; 'en çok hareket' → COUNT(*) azalan. */ SELECT b.[CODE] AS banka_kodu, b.[DEFINITION_] AS banka, COUNT(*) AS hareket_sayisi FROM LG_BNFLINE AS l JOIN BNCARD AS b ON b.[LOGICALREF] = l.[BANKREF] WHERE l.[CANCELLED] = 0 GROUP BY b.[CODE], b.[DEFINITION_] ORDER BY hareket_sayisi DESC
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT K.CODE, K.DEFINITION_, COUNT(*) hareket, SUM(L.AMOUNT) tutar FROM LG_411_01_BNFLINE L JOIN LG_411_BNCARD K ON K.LOGICALREF=L.BANKREF
WHERE L.CANCELLED=0 AND L.TRCODE<>5 AND L.MODULENR<>666 AND YEAR(L.DATE_)=YEAR(GETDATE()) GROUP BY K.CODE, K.DEFINITION_ ORDER BY 3 DESC
```

### M038 · Aylara göre banka giriş ve çıkışlarımız nasıl?

**Hüküm:** ✅ Doğru (2. okuma) — Aylık banka giriş/çıkış, banka modülü okuması  
**Referans tanımı:** M036 ana okuması (102 borç=giriş, alacak=çıkış, açılış hariç), ay kırılımı.

**Köprünün SQL'i:**
```sql
-- yorum: 'giris' → LG_BNFLINE.SIGN = 0, AMOUNT toplamı
-- yorum: 'cikislarimiz' → LG_BNFLINE.SIGN = 1, AMOUNT toplamı
SELECT
    DATEFROMPARTS(YEAR("DATE_"), MONTH("DATE_"), 1) AS ay,
    SUM(CASE WHEN "SIGN" = 0 THEN "AMOUNT" ELSE 0 END) AS giris,
    SUM(CASE WHEN "SIGN" = 1 THEN "AMOUNT" ELSE 0 END) AS cikis
FROM LG_BNFLINE
WHERE "CANCELLED" = 0
GROUP BY DATEFROMPARTS(YEAR("DATE_"), MONTH("DATE_"), 1)
ORDER BY ay
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT MONTH(L.DATE_) ay, SUM(L.DEBIT) giris, SUM(L.CREDIT) cikis, SUM(L.DEBIT-L.CREDIT) net FROM LG_411_01_EMFLINE L WHERE L.CANCELLED=0 AND L.ACCOUNTCODE LIKE '102%' AND YEAR(L.DATE_)=YEAR(GETDATE()) AND L.ACCFICHEREF NOT IN (SELECT LOGICALREF FROM LG_411_01_EMFICHE WHERE TRCODE=1) GROUP BY MONTH(L.DATE_) ORDER BY 1
```

### M039 · Kaç tane banka hesabımız var?

**Hüküm:** ❌ Yanlış değer — 118; aktif 85, tanımlı 87, hareketli 55  
**Referans tanımı:** Banka hesabı = LG_411_BANKACC kartı, POS/kredi kartı hesapları (CARDTYPE 5) hariç; aktif = ACTIVE=0.

**Köprünün SQL'i:**
```sql
-- yorum: 'banka hesabı' → BANKACC tablosu, COUNT(*) ile hesaplanır.
SELECT COUNT(*) AS banka_hesabi_sayisi
FROM BANKACC
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT SUM(CASE WHEN CARDTYPE IN (1,2,3) AND ACTIVE=0 THEN 1 ELSE 0 END) aktif_banka_hesabi, SUM(CASE WHEN CARDTYPE IN (1,2,3) THEN 1 ELSE 0 END) tanimli_banka_hesabi,
 COUNT(*) tum_kartlar_pos_dahil, (SELECT COUNT(DISTINCT BNACCREF) FROM LG_411_01_BNFLINE WHERE CANCELLED=0) hareketli_2026, (SELECT COUNT(DISTINCT BANKREF) FROM LG_411_01_BNFLINE) banka_sayisi FROM LG_411_BANKACC
```

### M040 · Geçen ay banka hareketlerimizin net tutarı ne oldu?

**Hüküm:** ❌ Yanlış değer — +6,3 Mn; doğru net −4,9 Mn  
**Referans tanımı:** Geçen ay = önceki takvim ayı (bugün 21.09.2026 → Ağustos 2026). Net = 102 borç − alacak, açılış hariç. Veri 17.08'de bitiyor (kısmi ay).

**Köprünün SQL'i:**
```sql
-- yorum: 'gecen ay' → LG_BNFLINE.DATE_ 2026-08-01 ile 2026-09-01 arası; 'net tutar' → giriş (SIGN=0) − çıkış (SIGN=1) AMOUNT toplamı.
SELECT SUM(CASE WHEN LG_BNFLINE."SIGN" = 0 THEN LG_BNFLINE."AMOUNT" ELSE -LG_BNFLINE."AMOUNT" END) AS net_tutar
FROM LG_BNFLINE
WHERE LG_BNFLINE."CANCELLED" = 0
  AND LG_BNFLINE."DATE_" >= '2026-08-01'
  AND LG_BNFLINE."DATE_" < '2026-09-01'
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT SUM(L.DEBIT) giris, SUM(L.CREDIT) cikis, SUM(L.DEBIT-L.CREDIT) net, MAX(L.DATE_) son_tarih FROM LG_411_01_EMFLINE L WHERE L.CANCELLED=0 AND L.ACCOUNTCODE LIKE '102%' AND L.ACCFICHEREF NOT IN (SELECT LOGICALREF FROM LG_411_01_EMFICHE WHERE TRCODE=1)
AND L.DATE_ >= DATEADD(day,1,EOMONTH(GETDATE(),-2)) AND L.DATE_ <= EOMONTH(GETDATE(),-1)
```

### M041 · En büyük on banka çıkışı hangileri?

**Hüküm:** ❌ Yanlış değer — İlk satır 711,6 Mn — tek çıkış değil toplam; liste hatalı  
**Referans tanımı:** Banka çıkışı = BNFLINE SIGN=1, banka hesapları (CARDTYPE 1,2,3), iptal hariç, 2026; açılış, virman (hesaplar arası), kur farkı, çek izleme h

**Köprünün SQL'i:**
```sql
-- yorum: 'cikisi' → LG_BNFLINE.SIGN = 1 (çıkış) ve AMOUNT toplamı
SELECT TOP 10
    b."CODE" AS banka_kodu,
    b."DEFINITION_" AS banka,
    a."CODE" AS hesap_kodu,
    a."DEFINITION_" AS hesap,
    SUM(l."AMOUNT") AS cikis_tutari
FROM LG_BNFLINE l
JOIN BNCARD b ON b."LOGICALREF" = l."BANKREF"
JOIN BANKACC a ON a."LOGICALREF" = l."BNACCREF"
WHERE l."CANCELLED" = 0
  AND l."SIGN" = 1
GROUP BY b."CODE", b."DEFINITION_", a."CODE", a."DEFINITION_"
ORDER BY cikis_tutari DESC
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT TOP 10 L.DATE_, K.DEFINITION_ banka, A.DEFINITION_ hesap, L.TRCODE, L.AMOUNT, L.LINEEXP, CL.DEFINITION_ cari FROM LG_411_01_BNFLINE L JOIN LG_411_BANKACC A ON A.LOGICALREF=L.BNACCREF
JOIN LG_411_BNCARD K ON K.LOGICALREF=L.BANKREF LEFT JOIN LG_411_CLCARD CL ON CL.LOGICALREF=L.CLIENTREF WHERE L.CANCELLED=0 AND A.CARDTYPE IN (1,2,3) AND L.TRCODE NOT IN (2,5,6,10,11) AND L.SIGN=1 AND YEAR(L.DATE_)=YEAR(GETDATE()) ORDER BY L.AMOUNT DESC
```

### M042 · Banka bazında net nakit akışı nasıl?

**Hüküm:** ❌ Yanlış değer — 11 banka; muhasebe kırılımı 14  
**Referans tanımı:** Banka bazında net nakit akışı = 102 muavin (her biri bir banka) 2026 borç − alacak, açılış hariç.

**Köprünün SQL'i:**
```sql
-- yorum: 'nakit' → LG_BNFLINE.AMOUNT, SIGN 0 giriş / 1 çıkış
-- yorum: 'akisi' → SUM(CASE SIGN 0 THEN AMOUNT ELSE -AMOUNT END)
SELECT 
    b."DEFINITION_" AS banka,
    SUM(CASE WHEN l."SIGN" = 0 THEN l."AMOUNT" ELSE -l."AMOUNT" END) AS net_nakit_akisi
FROM LG_BNFLINE l
JOIN BNCARD b ON b."LOGICALREF" = l."BANKREF"
WHERE l."CANCELLED" = 0
GROUP BY b."DEFINITION_"
ORDER BY net_nakit_akisi DESC
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT L.ACCOUNTCODE, MAX(A.DEFINITION_) banka, SUM(L.DEBIT) giris, SUM(L.CREDIT) cikis, SUM(L.DEBIT-L.CREDIT) net FROM LG_411_01_EMFLINE L JOIN LG_411_EMUHACC A ON A.LOGICALREF=L.ACCOUNTREF
WHERE L.CANCELLED=0 AND L.ACCOUNTCODE LIKE '102%' AND YEAR(L.DATE_)=YEAR(GETDATE()) AND L.ACCFICHEREF NOT IN (SELECT LOGICALREF FROM LG_411_01_EMFICHE WHERE TRCODE=1) GROUP BY L.ACCOUNTCODE ORDER BY 5 DESC
```

### M043 · Banka girişlerimiz geçen yılın aynı dönemine göre nasıl değişti?

**Hüküm:** ❌ Yanlış değer — 2026 girişi 0,00 dedi; gerçek 1,53 Mr  
**Referans tanımı:** Banka girişi (102 borç, açılış hariç) 2026 01.01–son veri günü vs 2025 aynı gün aralığı (LG_211_01_EMFLINE).

**Köprünün SQL'i:**
```sql
-- yorum: 'girislerimiz' → LG_BNFLINE.SIGN = 0 (giriş/tahsil) ve AMOUNT toplamı
SELECT 
    DATEFROMPARTS(YEAR(b."DATE_"), MONTH(b."DATE_"), 1) AS ay,
    SUM(CASE WHEN YEAR(b."DATE_") = 2026 THEN b."AMOUNT" ELSE 0 END) AS giris_2026,
    SUM(CASE WHEN YEAR(b."DATE_") = 2025 THEN b."AMOUNT" ELSE 0 END) AS giris_2025,
    SUM(CASE WHEN YEAR(b."DATE_") = 2026 THEN b."AMOUNT" ELSE 0 END) - 
    SUM(CASE WHEN YEAR(b."DATE_") = 2025 THEN b."AMOUNT" ELSE 0 END) AS fark
FROM LG_BNFLINE b
WHERE b."SIGN" = 0 
  AND b."CANCELLED" = 0
  AND (
      (YEAR(b."DATE_") = 2026 AND MONTH(b."DATE_") <= 8)
      OR 
      (YEAR(b."DATE_") = 2025 AND MONTH(b."DATE_") <= 8)
  )
GROUP BY DATEFROMPARTS(YEAR(b."DATE_"), MONTH(b."DATE_"), 1)
ORDER BY ay
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
WITH M AS (SELECT MAX(DATE_) mx FROM LG_411_01_EMFLINE WHERE CANCELLED=0),
G26 AS (SELECT SUM(L.DEBIT) g FROM LG_411_01_EMFLINE L WHERE L.CANCELLED=0 AND L.ACCOUNTCODE LIKE '102%' AND YEAR(L.DATE_)=YEAR(GETDATE()) AND L.ACCFICHEREF NOT IN (SELECT LOGICALREF FROM LG_411_01_EMFICHE WHERE TRCODE=1)),
G25 AS (SELECT SUM(L.DEBIT) g FROM LG_211_01_EMFLINE L WHERE L.CANCELLED=0 AND L.ACCOUNTCODE LIKE '102%' AND L.DATE_ >= DATEFROMPARTS(YEAR(GETDATE())-1,1,1) AND L.DATE_ <= DATEADD(year,-1,(SELECT mx FROM M))
 AND L.ACCFICHEREF NOT IN (SELECT LOGICALREF FROM LG_211_01_EMFICHE WHERE TRCODE=1))
SELECT G26.g giris_2026, G25.g giris_2025_ayni_donem, ROUND((G26.g/G25.g-1)*100,1) degisim_yuzde FROM G26, G25
```

### M044 · Havale ve EFT ile yapılan ödemelerin toplamı ne kadar?

**Hüküm:** ⚠️ Gereksiz ret — 'ödemelerin' tanımsız diye reddetti; havale/EFT 405,9 Mn  
**Referans tanımı:** Havale/EFT ile ödeme = BNFLINE TRCODE 4 (gönderilen havale, katalog etiketi) SIGN=1, iptal hariç, 2026 (tüm banka hesapları). CLFLINE TRCODE

**Köprünün SQL'i:**
```sql
(SQL üretilmedi)
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT SUM(L.AMOUNT) havale_eft_odeme, COUNT(*) adet FROM LG_411_01_BNFLINE L WHERE L.CANCELLED=0 AND L.TRCODE=4 AND L.SIGN=1 AND YEAR(L.DATE_)=YEAR(GETDATE())
```

### M045 · Kasaların bakiyeleri ne kadar?

**Hüküm:** ✅ Doğru (2. okuma) — Kasa modülü 38,7 Mn ≈ 39,0 Mn (muhasebe 100 hesabı 2,9 Mn — veri çelişkili)  
**Referans tanımı:** Kasa bakiyeleri (ana) = muhasebe 100 muavin bakiyeleri Σ(borç − alacak), açılış dahil. Kasa modülü (KSLINES, kasa kartı bazında Σ SIGN0−SIGN

**Köprünün SQL'i:**
```sql
-- yorum: 'bakiyeleri' → LG_KSLINES.AMOUNT, SIGN=0 (giriş) toplamı eksi SIGN=1 (çıkış) toplamı, kasa bazında.
SELECT 
    KSCARD."CODE" AS kasa_kodu,
    KSCARD."SPECODE" AS kasa_ek_kodu,
    SUM(CASE WHEN KSLINES."SIGN" = 0 THEN KSLINES."AMOUNT" ELSE -KSLINES."AMOUNT" END) AS bakiye
FROM LG_KSLINES AS KSLINES
JOIN LG_KSCARD AS KSCARD ON KSLINES."CARDREF" = KSCARD."LOGICALREF"
WHERE KSLINES."CANCELLED" = 0
GROUP BY KSCARD."CODE", KSCARD."SPECODE"
ORDER BY KSCARD."CODE"
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT A.CODE, A.DEFINITION_, SUM(L.DEBIT-L.CREDIT) bakiye FROM LG_411_01_EMFLINE L JOIN LG_411_EMUHACC A ON A.LOGICALREF=L.ACCOUNTREF WHERE L.CANCELLED=0 AND L.ACCOUNTCODE LIKE '100%' GROUP BY A.CODE, A.DEFINITION_ ORDER BY 1
```

### M046 · Bu yıl kasaya ne kadar para girdi, ne kadar çıktı?

**Hüküm:** ✅ Doğru (2. okuma) — Kasa modülü okuması (54,7/15,7 Mn); muhasebe 59,9/57,2 Mn  
**Referans tanımı:** Kasaya giren/çıkan (ana) = muhasebe 100 borç/alacak 2026, açılış fişi hariç (kasalar arası virman 1,49 Mn her iki tarafta). Kasa modülü ALT'

**Köprünün SQL'i:**
```sql
-- yorum: 'para' → LG_KSLINES.AMOUNT, SIGN ile giriş/çıkış ayrımı
SELECT
    SUM(CASE WHEN LG_KSLINES.[SIGN] = 0 THEN LG_KSLINES.[AMOUNT] ELSE 0 END) AS giren_para,
    SUM(CASE WHEN LG_KSLINES.[SIGN] = 1 THEN LG_KSLINES.[AMOUNT] ELSE 0 END) AS cikan_para
FROM LG_KSLINES
WHERE LG_KSLINES.[CANCELLED] = 0
  AND LG_KSLINES.[DATE_] >= '2026-01-01'
  AND LG_KSLINES.[DATE_] < '2027-01-01'
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT SUM(L.DEBIT) giris, SUM(L.CREDIT) cikis FROM LG_411_01_EMFLINE L WHERE L.CANCELLED=0 AND L.ACCOUNTCODE LIKE '100%' AND YEAR(L.DATE_)=YEAR(GETDATE()) AND L.ACCFICHEREF NOT IN (SELECT LOGICALREF FROM LG_411_01_EMFICHE WHERE TRCODE=1)
```

### M047 · Hangi kasada en çok işlem yapılmış?

**Hüküm:** ✅ Doğru — En çok işlem gören kasa, 7 kasa  
**Referans tanımı:** İşlem = kasa modülü satırı (KSLINES, iptal hariç, 2026, açılış 71 hariç), kasa kartı bazında adet.

**Köprünün SQL'i:**
```sql
-- yorum: 'islem' → LG_KSLINES.LOGICALREF satır sayısı (COUNT)
-- yorum: 'yapilmis' → LG_KSLINES.CANCELLED = 0 (iptal edilmemiş hareketler)
SELECT 
    k."CODE" AS kasa_kodu,
    k."NAME" AS kasa_adi,
    COUNT(l."LOGICALREF") AS islem_sayisi
FROM LG_KSLINES l
JOIN LG_KSCARD k ON k."LOGICALREF" = l."CARDREF"
WHERE l."CANCELLED" = 0
GROUP BY k."CODE", k."NAME"
ORDER BY islem_sayisi DESC
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT K.CODE, K.NAME, COUNT(*) islem, SUM(L.AMOUNT) tutar FROM LG_411_01_KSLINES L JOIN LG_411_KSCARD K ON K.LOGICALREF=L.CARDREF WHERE L.CANCELLED=0 AND L.TRCODE<>71 AND YEAR(L.DATE_)=YEAR(GETDATE()) GROUP BY K.CODE, K.NAME ORDER BY 3 DESC
```

### M048 · Aylara göre kasa hareketlerimiz nasıl?

**Hüküm:** ✅ Doğru — Aylık kasa hareketleri  
**Referans tanımı:** Kasa hareketleri ay kırılımı (ana) = muhasebe 100 borç (giriş) / alacak (çıkış), 2026, açılış hariç.

**Köprünün SQL'i:**
```sql
-- yorum: 'kasa hareketleri' → LG_KSLINES, SIGN ile giriş/çıkış ayrımı, AMOUNT toplamı, DATE_ ay kırılımı.
SELECT 
    DATEFROMPARTS(YEAR("DATE_"), MONTH("DATE_"), 1) AS ay,
    SUM(CASE WHEN "SIGN" = 0 THEN "AMOUNT" ELSE 0 END) AS giren,
    SUM(CASE WHEN "SIGN" = 1 THEN "AMOUNT" ELSE 0 END) AS cikan,
    SUM(CASE WHEN "SIGN" = 0 THEN "AMOUNT" ELSE 0 END) - SUM(CASE WHEN "SIGN" = 1 THEN "AMOUNT" ELSE 0 END) AS net
FROM LG_KSLINES
WHERE "CANCELLED" = 0
GROUP BY DATEFROMPARTS(YEAR("DATE_"), MONTH("DATE_"), 1)
ORDER BY ay
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT MONTH(L.DATE_) ay, SUM(L.DEBIT) giris, SUM(L.CREDIT) cikis, COUNT(*) satir FROM LG_411_01_EMFLINE L WHERE L.CANCELLED=0 AND L.ACCOUNTCODE LIKE '100%' AND YEAR(L.DATE_)=YEAR(GETDATE()) AND L.ACCFICHEREF NOT IN (SELECT LOGICALREF FROM LG_411_01_EMFICHE WHERE TRCODE=1) GROUP BY MONTH(L.DATE_) ORDER BY 1
```

### M049 · Kaç kasamız var?

**Hüküm:** ✅ Doğru — 9 kasa, birebir  
**Referans tanımı:** Kasa = LG_411_KSCARD kartı (ACTIVE=0 aktif).

**Köprünün SQL'i:**
```sql
-- yorum: 'kasa' → LG_KSCARD tablosundaki kasa kartlarının sayısı.
SELECT COUNT(*) AS kasa_sayisi
FROM LG_KSCARD
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT COUNT(*) kasa, SUM(CASE WHEN ACTIVE=0 THEN 1 ELSE 0 END) aktif, (SELECT COUNT(DISTINCT CARDREF) FROM LG_411_01_KSLINES WHERE CANCELLED=0) hareketli FROM LG_411_KSCARD
```

### M050 · Portföydeki müşteri çeklerimiz toplam ne kadar?

**Hüküm:** ✅ Doğru — Portföydeki çekler 30.289.524, birebir  
**Referans tanımı:** Portföydeki müşteri çeki = CSCARD DOC=1 (müşteri çeki), CURRSTAT=1 (Portföyde), iptal hariç; AMOUNT toplamı.

**Köprünün SQL'i:**
```sql
-- yorum: 'portfoydeki' → LG_CSCARD.CURRSTAT IN (1); 'musteri ceklerimiz' → LG_CSCARD.DOC = 1; toplam → SUM(AMOUNT)
SELECT SUM(LG_CSCARD."AMOUNT") AS toplam_tutar
FROM [dbo].[LG_CSCARD] AS LG_CSCARD
WHERE LG_CSCARD."CANCELLED" = 0
  AND LG_CSCARD."DOC" = 1
  AND LG_CSCARD."CURRSTAT" = 1
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT SUM(C.AMOUNT) tutar, COUNT(*) adet FROM LG_411_01_CSCARD C WHERE C.CANCELLED=0 AND C.DOC=1 AND C.CURRSTAT=1
```

### M051 · Bankaya tahsile verdiğimiz çeklerin tutarı ne kadar?

**Hüküm:** ❌ Veri varken 'yok' — 'kayıt yok'; tahsildeki çekler 270,7 Mn (412 çek)  
**Referans tanımı:** Bankaya tahsile verilen çek = CSCARD DOC=1, CURRSTAT=4 (Tahsile verildi), iptal hariç.

**Köprünün SQL'i:**
```sql
-- yorum: 'verdigimiz' → LG_CSCARD.DOC = 3 (kendi çekimiz)
-- yorum: 'tahsile' → LG_CSCARD.CURRSTAT = 4 (tahsile verildi)
SELECT SUM(LG_CSCARD.[AMOUNT]) AS tutar
FROM [dbo].[LG_CSCARD] AS LG_CSCARD
WHERE LG_CSCARD.[CANCELLED] = 0
  AND LG_CSCARD.[DOC] IN (1)
  AND LG_CSCARD.[DOC] = 3
  AND LG_CSCARD.[CURRSTAT] = 4
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT SUM(C.AMOUNT) tutar, COUNT(*) adet FROM LG_411_01_CSCARD C WHERE C.CANCELLED=0 AND C.DOC=1 AND C.CURRSTAT=4
```

### M052 · Bu yıl karşılıksız çıkan çeklerin toplam tutarı ne?

**Hüküm:** ✅ Doğru — Karşılıksız 6.326.658, birebir (bugün düzeltilen)  
**Referans tanımı:** Bu yıl karşılıksız çıkan çek = 2026 tarihli, devir olmayan (TRCODE<>0) CSTRANS hareketi STATUS=11 (Karşılığı yok) olan müşteri çekleri; tuta

**Köprünün SQL'i:**
```sql
-- yorum: 'karşılıksız cikan ceklerin' → CSTRANS.STATUS = 11, CSTRANS.DEVIR = 0, CSTRANS.CANCELLED = 0, CSTRANS.DATE_ 2026; tutar LG_CSCARD.AMOUNT (çek başına bir kez, EXISTS ile).
SELECT SUM(CSCARD."AMOUNT") AS toplam_tutar
FROM LG_CSCARD AS CSCARD
WHERE CSCARD."CANCELLED" = 0
  AND EXISTS (
    SELECT 1
    FROM CSTRANS AS T
    WHERE T."CSREF" = CSCARD."LOGICALREF"
      AND T."STATUS" = 11
      AND T."DEVIR" = 0
      AND T."CANCELLED" = 0
      AND T."DATE_" >= '2026-01-01'
      AND T."DATE_" < '2027-01-01'
  )
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT SUM(C.AMOUNT) tutar, COUNT(DISTINCT C.LOGICALREF) adet FROM LG_411_01_CSCARD C WHERE C.CANCELLED=0 AND C.DOC IN (1,3)
AND EXISTS (SELECT 1 FROM LG_411_01_CSTRANS T WHERE T.CSREF=C.LOGICALREF AND T.CANCELLED=0 AND T.STATUS=11 AND T.TRCODE<>0 AND YEAR(T.DATE_)=YEAR(GETDATE()))
```

### M053 · Protesto olan senetler var mı, tutarları ne?

**Hüküm:** ❌ Veri varken 'yok' — 'kayıt yok'; protestolu senet 877.714 (83 senet)  
**Referans tanımı:** Protestolu senet = CSCARD DOC=2 (müşteri senedi), CURRSTAT IN (5 protestolu tahsilde, 7 protesto edildi), iptal hariç.

**Köprünün SQL'i:**
```sql
-- yorum: 'senetler' → LG_CSCARD.DOC = 2 (müşteri senedi)
SELECT
    c."LOGICALREF" AS senet_ref,
    c."AMOUNT"     AS tutar
FROM LG_CSCARD c
WHERE c."DOC" = 2
  AND c."CANCELLED" = 0
  AND EXISTS (
      SELECT 1
      FROM CSTRANS t
      WHERE t."CSREF" = c."LOGICALREF"
        AND t."STATUS" IN (5, 7)
        AND t."DEVIR" = 0
        AND t."CANCELLED" = 0
  )
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT SUM(C.AMOUNT) tutar, COUNT(*) adet, MIN(C.DUEDATE) ilk_vade, MAX(C.DUEDATE) son_vade FROM LG_411_01_CSCARD C WHERE C.CANCELLED=0 AND C.DOC=2 AND C.CURRSTAT IN (5,7)
```

### M054 · Vadesi gelecek ay dolan çekler hangileri?

**Hüküm:** ❌ Yanlış değer — 174 çek; doğru 126  
**Referans tanımı:** Gelecek ay = bugünden sonraki takvim ayı (Ekim 2026). Vadesi dolan çek = DOC IN (1 müşteri çeki, 3 kendi çekimiz), iptal hariç, henüz kapanm

**Köprünün SQL'i:**
```sql
-- yorum: 'vadesi' → LG_CSCARD.DUEDATE, çekin vade tarihi
-- yorum: 'dolan' → LG_CSCARD.DUEDATE, gelecek ay aralığında (2026-10-01 – 2026-10-31)
SELECT
    "LOGICALREF",
    "DOC",
    "AMOUNT",
    "DUEDATE",
    "SETDATE",
    "CURRSTAT"
FROM LG_CSCARD
WHERE "DOC" = 1
  AND "CANCELLED" = 0
  AND "DUEDATE" >= '2026-10-01'
  AND "DUEDATE" < '2026-11-01'
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT C.PORTFOYNO, C.DOC, C.CURRSTAT, C.DUEDATE, C.AMOUNT, C.OWING, C.BANKNAME FROM LG_411_01_CSCARD C WHERE C.CANCELLED=0 AND C.DOC IN (1,3) AND C.CURRSTAT IN (1,4,9)
AND C.DUEDATE >= DATEADD(day,1,EOMONTH(GETDATE())) AND C.DUEDATE <= EOMONTH(GETDATE(),1) ORDER BY C.DUEDATE, C.AMOUNT DESC
```

### M055 · Çeklerimizi durumlarına göre dağılım olarak gösterir misin?

**Hüküm:** ✅ Doğru — Durumlara göre dağılım, 6 grup  
**Referans tanımı:** Müşteri çekleri (DOC=1) güncel durum (CURRSTAT) dağılımı, iptal hariç; adet ve tutar.

**Köprünün SQL'i:**
```sql
-- yorum: 'çeklerimizi' → LG_CSCARD.DOC = 1 (müşteri çeki); 'durum' → LG_CSCARD.CURRSTAT.
SELECT
    "CURRSTAT" AS durum_kodu,
    COUNT(*)   AS cek_sayisi,
    SUM("AMOUNT") AS toplam_tutar
FROM LG_CSCARD
WHERE "DOC" = 1
  AND "CANCELLED" = 0
GROUP BY "CURRSTAT"
ORDER BY cek_sayisi DESC
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT C.CURRSTAT, CASE C.CURRSTAT WHEN 1 THEN 'Portföyde' WHEN 2 THEN 'Ciro edildi' WHEN 3 THEN 'Teminata verildi' WHEN 4 THEN 'Tahsile verildi'
 WHEN 5 THEN 'Protestolu tahsile verildi' WHEN 6 THEN 'İade edildi' WHEN 7 THEN 'Protesto edildi' WHEN 8 THEN 'Tahsil edildi'
 WHEN 9 THEN 'Kendi çekimiz' WHEN 10 THEN 'Borç senedimiz' WHEN 11 THEN 'Karşılığı yok' WHEN 12 THEN 'Tahsil edilemiyor' ELSE CAST(C.CURRSTAT AS varchar) END durum, COUNT(*) adet, SUM(C.AMOUNT) tutar FROM LG_411_01_CSCARD C WHERE C.CANCELLED=0 AND C.DOC=1 GROUP BY C.CURRSTAT ORDER BY 1
```

### M056 · Senetlerin toplam tutarı çeklere göre ne kadar?

**Hüküm:** ❌ Yanlış değer — Senet 0,00; doğru 12,3 Mn  
**Referans tanımı:** Senet (DOC 2 müşteri senedi + 4 borç senedimiz) toplam tutarı vs çek (DOC 1 + 3) toplam tutarı; CSCARD tüm durumlar, iptal hariç (2026 firma

**Köprünün SQL'i:**
```sql
-- yorum: 'senetlerin' → LG_CSCARD.DOC IN (2,4) AMOUNT toplamı; çekler DOC IN (1,3)
SELECT
  SUM(CASE WHEN "DOC" IN (1, 3) THEN "AMOUNT" ELSE 0 END) AS cek_tutar,
  SUM(CASE WHEN "DOC" IN (2, 4) THEN "AMOUNT" ELSE 0 END) AS senet_tutar,
  SUM(CASE WHEN "DOC" IN (2, 4) THEN "AMOUNT" ELSE 0 END)
    - SUM(CASE WHEN "DOC" IN (1, 3) THEN "AMOUNT" ELSE 0 END) AS fark
FROM LG_CSCARD
WHERE "CANCELLED" = 0
  AND "DOC" IN (1)
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT SUM(CASE WHEN DOC IN (2,4) THEN AMOUNT ELSE 0 END) senet, SUM(CASE WHEN DOC IN (1,3) THEN AMOUNT ELSE 0 END) cek,
 ROUND(SUM(CASE WHEN DOC IN (2,4) THEN AMOUNT ELSE 0 END)/SUM(CASE WHEN DOC IN (1,3) THEN AMOUNT ELSE 0 END)*100,2) senet_cek_orani_yuzde FROM LG_411_01_CSCARD WHERE CANCELLED=0
```

### M057 · En büyük tutarlı on çek hangi müşteriden?

**Hüküm:** ⚠️ Gereksiz ret — 'tutarlı' kelimesi tanımsız diye reddetti  
**Referans tanımı:** Müşteri çeki (DOC=1, iptal hariç, tüm durumlar) AMOUNT'a göre ilk 10; müşteri = çekin portföye giriş hareketindeki cari (CSTRANS CARDMD=5, S

**Köprünün SQL'i:**
```sql
(SQL üretilmedi)
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
WITH G AS (SELECT T.CSREF, T.CARDREF, ROW_NUMBER() OVER (PARTITION BY T.CSREF ORDER BY T.DATE_, T.LOGICALREF) rn FROM LG_411_01_CSTRANS T WHERE T.CANCELLED=0 AND T.CARDMD=5 AND T.STATUS=1)
SELECT TOP 10 C.PORTFOYNO, C.AMOUNT, C.DUEDATE, C.CURRSTAT, CL.CODE, CL.DEFINITION_ musteri, C.OWING borclu FROM LG_411_01_CSCARD C LEFT JOIN G ON G.CSREF=C.LOGICALREF AND G.rn=1
LEFT JOIN LG_411_CLCARD CL ON CL.LOGICALREF=G.CARDREF WHERE C.CANCELLED=0 AND C.DOC=1 ORDER BY C.AMOUNT DESC
```

### M058 · Tahsil edilmiş çeklerin toplamı ne kadar?

**Hüküm:** ⚠️ Gereksiz ret — 'tahsil' tanımsız diye reddetti; tahsil edilen çek 261,3 Mn  
**Referans tanımı:** Tahsil edilmiş çek = CSCARD DOC=1, CURRSTAT=8 (Tahsil edildi), iptal hariç.

**Köprünün SQL'i:**
```sql
(SQL üretilmedi)
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT SUM(C.AMOUNT) tutar, COUNT(*) adet FROM LG_411_01_CSCARD C WHERE C.CANCELLED=0 AND C.DOC=1 AND C.CURRSTAT=8
```

### M059 · Ciro edilen çekler toplam ne kadar?

**Hüküm:** ❌ Yanlış değer — 0,00; ciro edilen çek 158,1 Mn (bu yıl)  
**Referans tanımı:** Ciro edilen çek = CSCARD DOC=1, CURRSTAT=2 (Ciro edildi), iptal hariç (devirle gelenler dahil).

**Köprünün SQL'i:**
```sql
-- yorum: 'ciro edilen çekler' → LG_CSCARD.CURRSTAT = 2, tutar LG_CSCARD.GIROAMOUNT toplamı.
SELECT SUM("GIROAMOUNT") AS ciro_edilen_cek_tutari
FROM LG_CSCARD
WHERE "CANCELLED" = 0
  AND "CURRSTAT" = 2
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT SUM(C.AMOUNT) tutar, COUNT(*) adet FROM LG_411_01_CSCARD C WHERE C.CANCELLED=0 AND C.DOC=1 AND C.CURRSTAT=2
```

### M060 · Bu yılki hesaplanan KDV toplamımız ne?

**Hüküm:** ✅ Doğru (2. okuma) — Satış faturası KDV'si 4.490.682 (391 hesabı 5.046.474 — mutabakat farkı var)  
**Referans tanımı:** Hesaplanan KDV = 2026 (01.01–17.08) 391 Hesaplanan KDV hesabının ALACAK hareketleri (açılış fişi hariç; borç tarafı aylık KDV mahsup kaydı o

**Köprünün SQL'i:**
```sql
-- yorum: 'hesaplanan kdv' → INVOICE.TOTALVAT, 'bu yilki' → DATE_ 2026 aralığı.
SELECT SUM(INVOICE."TOTALVAT") AS hesaplanan_kdv
FROM [dbo].[INVOICE] AS INVOICE
WHERE INVOICE."CANCELLED" = 0
  AND INVOICE."TRCODE" IN (7, 8, 9)
  AND INVOICE."DATE_" >= '2026-01-01'
  AND INVOICE."DATE_" < '2027-01-01'
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT (SELECT SUM(CREDIT) FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND ACCOUNTCODE LIKE '391%' AND TRCODE<>1) AS hesaplanan_kdv_391_alacak, (SELECT SUM(CREDIT) FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND ACCOUNTCODE LIKE '391.01%' ) AS satis_kdv_391_01, (SELECT SUM(CREDIT) FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND ACCOUNTCODE LIKE '391.02%' ) AS alis_iade_kdv_391_02, (SELECT SUM(TOTALVAT) FROM LG_411_01_INVOICE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND TRCODE IN (7,8,9) ) AS fatura_kdv_satis_789, (SELECT SUM(TOTALVAT) FROM LG_411_01_INVOICE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND TRCODE IN (2,3) ) AS fatura_kdv_satis_iade_23
```

### M061 · İndirilecek KDV toplamı ne kadar?

**Hüküm:** ❌ Yanlış değer — 8,5 Mn; indirilecek KDV 65,2 Mn  
**Referans tanımı:** İndirilecek KDV = 2026 191 İndirilecek KDV hesabının BORÇ hareketleri (açılış hariç; alacak tarafı aylık mahsup). 191.01 alış KDV'si + 191.0

**Köprünün SQL'i:**
```sql
-- yorum: 'kdv' → FAREGIST.VATAMOUNT toplamı (indirilecek KDV).
SELECT SUM(FAREGIST."VATAMOUNT") AS indirilecek_kdv
FROM FAREGIST
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT (SELECT SUM(DEBIT) FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND ACCOUNTCODE LIKE '191%' AND TRCODE<>1) AS indirilecek_kdv_191_borc, (SELECT SUM(DEBIT) FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND ACCOUNTCODE LIKE '191.01%' ) AS alis_kdv_191_01, (SELECT SUM(DEBIT) FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND ACCOUNTCODE LIKE '191.02%' ) AS satis_iade_kdv_191_02, (SELECT SUM(TOTALVAT) FROM LG_411_01_INVOICE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND TRCODE IN (1,4) ) AS fatura_kdv_alis_14, (SELECT SUM(TOTALVAT) FROM LG_411_01_INVOICE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND TRCODE IN (6) ) AS fatura_kdv_alis_iade_6
```

### M062 · Hesaplanan ile indirilecek KDV arasındaki fark ne?

**Hüküm:** ⚠️ Gereksiz ret — 'hesaplanan' tanımsız diye reddetti  
**Referans tanımı:** Fark = hesaplanan KDV (391 alacak) − indirilecek KDV (191 borç), 2026 01.01–17.08. Negatif = indirilecek fazla → devreden KDV.

**Köprünün SQL'i:**
```sql
(SQL üretilmedi)
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT (SELECT SUM(CREDIT) FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND ACCOUNTCODE LIKE '391%' AND TRCODE<>1) - (SELECT SUM(DEBIT) FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND ACCOUNTCODE LIKE '191%' AND TRCODE<>1) AS fark_391_eksi_191, (SELECT SUM(CREDIT) FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND ACCOUNTCODE LIKE '391%' AND TRCODE<>1) AS hesaplanan, (SELECT SUM(DEBIT) FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND ACCOUNTCODE LIKE '191%' AND TRCODE<>1) AS indirilecek
```

### M063 · Aylara göre hesaplanan KDV nasıl dağılıyor?

**Hüküm:** ❌ Yanlış değer — Aylık 8,4 Mn; yıllık toplam 5,0 Mn — imkânsız  
**Referans tanımı:** Aylık hesaplanan KDV = 391 alacak hareketleri, 2026 aylara göre (açılış hariç). Ağustos 1–17.

**Köprünün SQL'i:**
```sql
-- yorum: 'hesaplanan kdv' → INVOICE.TOTALVAT kolonu, aylık toplam.
SELECT 
    DATEFROMPARTS(YEAR("DATE_"), MONTH("DATE_"), 1) AS ay,
    SUM("TOTALVAT") AS hesaplanan_kdv
FROM INVOICE
WHERE "CANCELLED" = 0
GROUP BY DATEFROMPARTS(YEAR("DATE_"), MONTH("DATE_"), 1)
ORDER BY ay
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT MONTH(DATE_) AS ay, SUM(CREDIT) AS hesaplanan_kdv FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND TRCODE<>1 AND ACCOUNTCODE LIKE '391%' GROUP BY MONTH(DATE_) ORDER BY ay
```

### M064 · Satış faturalarındaki toplam KDV tutarı ne kadar?

**Hüküm:** ❌ Yanlış değer — 1,787 MİLYAR; satış faturası KDV'si 4,49 Mn (400 kat)  
**Referans tanımı:** Satış faturalarındaki KDV = INVOICE.TOTALVAT, TRCODE 7 perakende + 8 toptan + 9 verilen hizmet, iptal hariç, 2026.

**Köprünün SQL'i:**
```sql
-- yorum: 'satis faturalarindaki' → INVOICE.GRPCODE IN (2) [CERTIFIED]
-- yorum: 'kdv tutari' → INVOICE.GROSSTOTAL toplamı [CERTIFIED]
SELECT SUM(INVOICE."GROSSTOTAL") AS kdv_tutari
FROM INVOICE
WHERE INVOICE."CANCELLED" = 0
  AND INVOICE."GRPCODE" IN (2)
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT (SELECT SUM(TOTALVAT) FROM LG_411_01_INVOICE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND TRCODE IN (7,8,9) ) AS satis_fatura_kdv_789, (SELECT SUM(TOTALVAT) FROM LG_411_01_INVOICE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND TRCODE IN (7,8,9) ) - (SELECT SUM(TOTALVAT) FROM LG_411_01_INVOICE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND TRCODE IN (2,3) ) AS iade_dusulmus_kdv, (SELECT SUM(TOTALVAT) FROM LG_411_01_INVOICE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND TRCODE IN (2,3,7,8,9) ) AS kdv_satis_kapsami_23789_isaretsiz
```

### M065 · Alış faturalarındaki toplam KDV ne kadar?

**Hüküm:** ❌ Veri varken 'yok' — 'kayıt yok'; alış faturası KDV'si 61,2 Mn  
**Referans tanımı:** Alış faturalarındaki KDV = INVOICE.TOTALVAT, TRCODE 1 mal alım + 4 alınan hizmet, iptal hariç, 2026.

**Köprünün SQL'i:**
```sql
-- yorum: 'alis' → INVOICE.TRCODE IN (1, 4) alış faturaları
-- yorum: 'kdv' → INVOICE.TOTALVAT toplam KDV tutarı
SELECT SUM(INVOICE.[TOTALVAT]) AS toplam_kdv
FROM [dbo].[INVOICE] AS INVOICE
WHERE INVOICE.[CANCELLED] = 0
  AND INVOICE.[TRCODE] IN (2, 3, 7, 8, 9)
  AND INVOICE.[TRCODE] IN (1, 4)
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT (SELECT SUM(TOTALVAT) FROM LG_411_01_INVOICE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND TRCODE IN (1,4) ) AS alis_fatura_kdv_14, (SELECT SUM(TOTALVAT) FROM LG_411_01_INVOICE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND TRCODE IN (1) ) AS mal_alim_kdv_1, (SELECT SUM(TOTALVAT) FROM LG_411_01_INVOICE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND TRCODE IN (4) ) AS hizmet_alim_kdv_4, (SELECT SUM(TOTALVAT) FROM LG_411_01_INVOICE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND TRCODE IN (1,4) ) - (SELECT SUM(TOTALVAT) FROM LG_411_01_INVOICE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND TRCODE IN (6) ) AS iade_dusulmus
```

### M066 · Ödenecek vergi ve fonlar hesabında ne kadar tutar var?

**Hüküm:** ❌ Veri varken 'yok' — 'kayıt yok'; 360 hesabında 9,0 Mn  
**Referans tanımı:** Ödenecek Vergi ve Fonlar (360) bakiyesi = 17.08.2026 itibarıyla alacak − borç, açılış devri dahil (bilanço bakiyesi).

**Köprünün SQL'i:**
```sql
-- yorum: 'vergi' → EMUHACC.CODE '391' (Ödenecek Vergi ve Fonlar) hesabı, EMFLINE DEBIT-CREDIT bakiyesi.
SELECT SUM(EMFLINE."DEBIT" - EMFLINE."CREDIT") AS odenecek_vergi_fon_bakiyesi
FROM EMFLINE
JOIN EMUHACC ON EMFLINE."ACCOUNTREF" = EMUHACC."LOGICALREF"
WHERE EMUHACC."CODE" = '391'
  AND EMFLINE."CANCELLED" = 0
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT SUM(CREDIT-DEBIT) AS bakiye_360_alacak, SUM(CASE WHEN TRCODE=1 THEN CREDIT-DEBIT ELSE 0 END) AS acilis_devri, SUM(CASE WHEN TRCODE<>1 THEN CREDIT ELSE 0 END) AS yil_alacak, SUM(CASE WHEN TRCODE<>1 THEN DEBIT ELSE 0 END) AS yil_borc FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND ACCOUNTCODE LIKE '360%'
```

### M067 · Geçen ay ne kadar KDV ödememiz çıkıyor?

**Hüküm:** ⚠️ Gereksiz ret — 'kdv' tanımsız diye reddetti  
**Referans tanımı:** 'Geçen ay' = Ağustos 2026 (veri 17'sinde bitiyor, 1–17). Ödenecek KDV = o ayın hesaplanan KDV (391 alacak) − indirilecek KDV (191 borç); neg

**Köprünün SQL'i:**
```sql
(SQL üretilmedi)
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT (SELECT SUM(CREDIT) FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND ACCOUNTCODE LIKE '391%' AND DATE_>='20260801' AND DATE_<'20260901') - (SELECT SUM(DEBIT) FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND ACCOUNTCODE LIKE '191%' AND DATE_>='20260801' AND DATE_<'20260901') AS agustos_kdv_391_eksi_191, (SELECT SUM(CREDIT) FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND ACCOUNTCODE LIKE '391%' AND DATE_>='20260801' AND DATE_<'20260901') AS agustos_hesaplanan, (SELECT SUM(DEBIT) FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND ACCOUNTCODE LIKE '191%' AND DATE_>='20260801' AND DATE_<'20260901') AS agustos_indirilecek, (SELECT SUM(CREDIT) FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND ACCOUNTCODE LIKE '360.03%' AND DATE_>='20260801' AND DATE_<'20260901') AS agustos_kdv2_tevkifat_360_03, (SELECT SUM(CREDIT) FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND ACCOUNTCODE LIKE '391%' AND DATE_>='20260701' AND DATE_<'20260801') - (SELECT SUM(DEBIT) FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND ACCOUNTCODE LIKE '191%' AND DATE_>='20260701' AND DATE_<'20260801') AS temmuz_kdv_391_eksi_191
```

### M068 · KDV'si sıfır olan faturalar var mı, kaç tane?

**Hüküm:** ❌ Yanlış değer — 66.365; doğru 67.263  
**Referans tanımı:** KDV'si sıfır fatura = INVOICE.TOTALVAT = 0, iptal hariç, 2026, tüm fatura türleri.

**Köprünün SQL'i:**
```sql
-- yorum: 'kdv' → INVOICE.TOTALVAT = 0, TRCODE IN (2,3,7,8,9), CANCELLED = 0
SELECT COUNT(DISTINCT "LOGICALREF") AS kdv_sifir_fatura_sayisi
FROM INVOICE
WHERE "TRCODE" IN (2, 3, 7, 8, 9)
  AND "CANCELLED" = 0
  AND "TOTALVAT" = 0
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT SUM(CASE WHEN TOTALVAT=0 THEN 1 ELSE 0 END) AS kdv_sifir_fatura, COUNT(*) AS toplam_fatura, SUM(CASE WHEN TOTALVAT=0 AND TRCODE IN (7,8,9) THEN 1 ELSE 0 END) AS kdv_sifir_satis_789, SUM(CASE WHEN TRCODE IN (7,8,9) THEN 1 ELSE 0 END) AS satis_789, SUM(CASE WHEN TOTALVAT=0 AND TRCODE IN (1,4) THEN 1 ELSE 0 END) AS kdv_sifir_alis_14 FROM LG_411_01_INVOICE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101'
```

### M069 · Hangi fatura türünde en çok KDV var?

**Hüküm:** ❌ Yanlış değer — En çok KDV'yi toptan satış (2,99 Mn) dedi; gerçekte alınan hizmet 47,5 Mn  
**Referans tanımı:** Fatura türü = INVOICE.TRCODE (katalog etiketleri; 9 = verilen hizmet katalog etiketinde yok, Logo standardı), tür bazında SUM(TOTALVAT), 202

**Köprünün SQL'i:**
```sql
-- yorum: 'kdv' → INVOICE."TOTALVAT" kolonu, TRCODE bazında toplam
SELECT "TRCODE" AS fatura_turu, SUM("TOTALVAT") AS toplam_kdv
FROM INVOICE
WHERE "CANCELLED" = 0 AND "TRCODE" IN (2, 3, 7, 8, 9)
GROUP BY "TRCODE"
ORDER BY toplam_kdv DESC
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT TRCODE, CASE TRCODE WHEN 1 THEN 'Mal alım' WHEN 2 THEN 'Perakende satış iade' WHEN 3 THEN 'Toptan satış iade' WHEN 4 THEN 'Alınan hizmet' WHEN 6 THEN 'Alım iade' WHEN 7 THEN 'Perakende satış' WHEN 8 THEN 'Toptan satış' WHEN 9 THEN 'Verilen hizmet' ELSE CAST(TRCODE AS varchar(5)) END AS fatura_turu, COUNT(*) AS fatura, SUM(TOTALVAT) AS kdv FROM LG_411_01_INVOICE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' GROUP BY TRCODE ORDER BY kdv DESC
```

### M070 · Bu yılki net satışlarımız ne kadar?

**Hüküm:** ❌ Yanlış değer — 922,7 Mn satış satırından; gelir tablosu net satış 841,7 Mn  
**Referans tanımı:** Net satışlar (gelir tablosu) = 60 Brüt Satışlar (600+601+602 alacak−borç) − 61 Satış İndirimleri (610+611+612 borç−alacak), 2026 01.01–17.08

**Köprünün SQL'i:**
```sql
SELECT SUM(CASE WHEN STLINE.[TRCODE] IN (7, 8, 9) THEN STLINE.[LINENET] ELSE 0 END) AS satis_tutari
FROM (SELECT [CANCELLED], [DATE_], [LINENET], [LINETYPE], [TRCODE] FROM [dbo].[LG_211_01_STLINE] UNION ALL SELECT [CANCELLED], [DATE_], [LINENET], [LINETYPE], [TRCODE] FROM [dbo].[LG_411_01_STLINE]) AS STLINE
WHERE STLINE.[CANCELLED] = 0
  AND STLINE.[CANCELLED] = 0
  AND STLINE.[LINETYPE] = 0
  AND STLINE.[TRCODE] IN (2, 3, 7, 8, 9)
  AND STLINE.[DATE_] >= '2026-01-01' AND STLINE.[DATE_] < '2027-01-01'
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT (SUM(CASE WHEN LEFT(ACCOUNTCODE,2)='60' THEN CREDIT-DEBIT ELSE 0 END) - SUM(CASE WHEN LEFT(ACCOUNTCODE,2)='61' THEN DEBIT-CREDIT ELSE 0 END)) AS net_satis_gelir_tablosu FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101'
```

### M071 · Satış iadelerimiz toplam ne kadar?

**Hüküm:** ❌ Yanlış değer — 74,3 Mn; doğru 71,0 Mn  
**Referans tanımı:** Satış iadeleri = 610 Satıştan İadeler borç−alacak, 2026.

**Köprünün SQL'i:**
```sql
-- yorum: 'satis iadelerimiz' → INVOICE.TRCODE IN (2,3), toplam NETTOTAL.
SELECT SUM(INVOICE.[NETTOTAL]) AS satis_iade_tutari
FROM [dbo].[INVOICE] AS INVOICE
WHERE INVOICE.[CANCELLED] = 0
  AND INVOICE.[TRCODE] IN (2, 3)
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT (SELECT SUM(DEBIT-CREDIT) FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND ACCOUNTCODE LIKE '610%' ) AS satis_iade_610, (SELECT SUM(NETTOTAL-TOTALVAT) FROM LG_411_01_INVOICE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND TRCODE IN (2,3) ) AS iade_fatura_kdv_haric, (SELECT SUM(NETTOTAL) FROM LG_411_01_INVOICE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND TRCODE IN (2,3) ) AS iade_fatura_kdv_dahil, (SELECT SUM(1) FROM LG_411_01_INVOICE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND TRCODE IN (2,3) ) AS iade_fatura_adet
```

### M072 · Satış iskontolarımız ne kadar tuttu?

**Hüküm:** ❌ Yanlış değer — Oran 0,46 verdi; tutar sorulmuş (611: 2,8 Mn, fatura iskontosu 747,9 Mn)  
**Referans tanımı:** Satış iskontoları = 611 Satış İskontoları borç−alacak, 2026 (sonradan verilen iskontolar).

**Köprünün SQL'i:**
```sql
SELECT SUM(CASE WHEN (STLINE.[CANCELLED] = 0) AND (STLINE.[LINETYPE] = 0) AND (STLINE.[TRCODE] IN (2, 3, 7, 8, 9)) THEN CASE WHEN STLINE.[TRCODE] IN (7, 8, 9) THEN STLINE.[LINENET] ELSE 0 END END) AS satis_tutari, SUM(CASE WHEN (STLINE.[TRCODE] IN (7, 8)) THEN CASE WHEN STLINE.[LINETYPE] = 2 THEN STLINE.[TOTAL] ELSE 0 END END) / NULLIF(SUM(CASE WHEN (STLINE.[TRCODE] IN (7, 8)) THEN CASE WHEN STLINE.[LINETYPE] = 0 THEN STLINE.[TOTAL] ELSE 0 END END), 0) AS iskonto_orani
FROM (SELECT [CANCELLED], [DATE_], [LINENET], [LINETYPE], [TOTAL], [TRCODE] FROM [dbo].[LG_211_01_STLINE] UNION ALL SELECT [CANCELLED], [DATE_], [LINENET], [LINETYPE], [TOTAL], [TRCODE] FROM [dbo].[LG_411_01_STLINE]) AS STLINE
WHERE STLINE.[CANCELLED] = 0
  AND STLINE.[CANCELLED] = 0
  AND (((STLINE.[CANCELLED] = 0) AND (STLINE.[LINETYPE] = 0) AND (STLINE.[TRCODE] IN (2, 3, 7, 8, 9))) OR ((STLINE.[TRCODE] IN (7, 8))))
  AND STLINE.[DATE_] >= '2026-01-01' AND STLINE.[DATE_] < '2027-01-01'
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT (SELECT SUM(DEBIT-CREDIT) FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND ACCOUNTCODE LIKE '611%' ) AS satis_iskonto_611, (SELECT SUM(TOTALDISCOUNTS) FROM LG_411_01_INVOICE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND TRCODE IN (7,8,9) ) AS fatura_iskontolari_789
```

### M073 · Aylara göre net satış tutarlarımız nasıl?

**Hüküm:** ✅ Doğru (2. okuma) — Aylık satış tutarları, satır düzeyinde okuma  
**Referans tanımı:** Aylık net satış = gelir tablosu tanımı (60 alacak−borç − 61 borç−alacak), 2026 aylara göre; Ağustos 1–17.

**Köprünün SQL'i:**
```sql
SELECT DATEFROMPARTS(YEAR(STLINE.[DATE_]), MONTH(STLINE.[DATE_]), 1) AS ay, SUM(CASE WHEN STLINE.[TRCODE] IN (7, 8, 9) THEN STLINE.[LINENET] ELSE 0 END) AS satis_tutari
FROM (SELECT [CANCELLED], [DATE_], [LINENET], [LINETYPE], [TRCODE] FROM [dbo].[LG_211_01_STLINE] UNION ALL SELECT [CANCELLED], [DATE_], [LINENET], [LINETYPE], [TRCODE] FROM [dbo].[LG_411_01_STLINE]) AS STLINE
WHERE STLINE.[CANCELLED] = 0
  AND STLINE.[CANCELLED] = 0
  AND STLINE.[LINETYPE] = 0
  AND STLINE.[TRCODE] IN (2, 3, 7, 8, 9)
  AND STLINE.[DATE_] >= '2026-01-01' AND STLINE.[DATE_] < '2027-01-01'
GROUP BY DATEFROMPARTS(YEAR(STLINE.[DATE_]), MONTH(STLINE.[DATE_]), 1)
ORDER BY DATEFROMPARTS(YEAR(STLINE.[DATE_]), MONTH(STLINE.[DATE_]), 1)
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT MONTH(DATE_) AS ay, (SUM(CASE WHEN LEFT(ACCOUNTCODE,2)='60' THEN CREDIT-DEBIT ELSE 0 END) - SUM(CASE WHEN LEFT(ACCOUNTCODE,2)='61' THEN DEBIT-CREDIT ELSE 0 END)) AS net_satis FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND LEFT(ACCOUNTCODE,2) IN ('60','61') GROUP BY MONTH(DATE_) ORDER BY ay
```

### M074 · Bu yılki satışlarımız geçen yılın aynı dönemine göre nasıl?

**Hüküm:** ❌ Yanlış değer — 922,7 / 619,3 Mn; eş dönem net satış 841,7 / 556,3 Mn  
**Referans tanımı:** Eş dönem: 2026 01.01–17.08 vs 2025 01.01–17.08 (LG_211_01_EMFLINE / LG_211_01_INVOICE). Net satış gelir tablosu tanımıyla; fatura KPI ayrıca

**Köprünün SQL'i:**
```sql
SELECT SUM(CASE WHEN (STLINE.[DATE_] >= '2026-01-01' AND STLINE.[DATE_] < '2026-08-18') THEN CASE WHEN STLINE.[TRCODE] IN (7, 8, 9) THEN STLINE.[LINENET] ELSE 0 END END) AS bu_yilki_satis_tutari, SUM(CASE WHEN (STLINE.[DATE_] >= '2025-01-01' AND STLINE.[DATE_] < '2025-08-18') THEN CASE WHEN STLINE.[TRCODE] IN (7, 8, 9) THEN STLINE.[LINENET] ELSE 0 END END) AS gecen_yilin_satis_tutari
FROM (SELECT [CANCELLED], [DATE_], [LINENET], [LINETYPE], [TRCODE] FROM [dbo].[LG_211_01_STLINE] UNION ALL SELECT [CANCELLED], [DATE_], [LINENET], [LINETYPE], [TRCODE] FROM [dbo].[LG_411_01_STLINE]) AS STLINE
WHERE STLINE.[CANCELLED] = 0
  AND STLINE.[CANCELLED] = 0
  AND STLINE.[LINETYPE] = 0
  AND STLINE.[TRCODE] IN (2, 3, 7, 8, 9)
  AND ((STLINE.[DATE_] >= '2026-01-01' AND STLINE.[DATE_] < '2026-08-18') OR (STLINE.[DATE_] >= '2025-01-01' AND STLINE.[DATE_] < '2025-08-18'))
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT (SELECT (SUM(CASE WHEN LEFT(ACCOUNTCODE,2)='60' THEN CREDIT-DEBIT ELSE 0 END) - SUM(CASE WHEN LEFT(ACCOUNTCODE,2)='61' THEN DEBIT-CREDIT ELSE 0 END)) FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20260818') AS net_satis_2026, (SELECT (SUM(CASE WHEN LEFT(ACCOUNTCODE,2)='60' THEN CREDIT-DEBIT ELSE 0 END) - SUM(CASE WHEN LEFT(ACCOUNTCODE,2)='61' THEN DEBIT-CREDIT ELSE 0 END)) FROM LG_211_01_EMFLINE WHERE CANCELLED=0 AND DATE_>='20250101' AND DATE_<'20250818') AS net_satis_2025_ayni_donem, (SELECT SUM(CASE WHEN TRCODE IN (7,8,9) THEN NETTOTAL ELSE -NETTOTAL END) FROM LG_411_01_INVOICE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20260818' AND TRCODE IN (2,3,7,8,9)) AS kpi_ciro_2026, (SELECT SUM(CASE WHEN TRCODE IN (7,8,9) THEN NETTOTAL ELSE -NETTOTAL END) FROM LG_211_01_INVOICE WHERE CANCELLED=0 AND DATE_>='20250101' AND DATE_<'20250818' AND TRCODE IN (2,3,7,8,9)) AS kpi_ciro_2025
```

### M075 · Brüt satış, iade ve iskonto ile net satışı ayrı ayrı gösterir misin?

**Hüküm:** ⚠️ Gereksiz ret — 'ayrı' kelimesi tanımsız diye reddetti  
**Referans tanımı:** Gelir tablosu satış bölümü: brüt satış (60x alacak−borç), iade (610), iskonto (611), diğer indirim (612), net satış; 2026.

**Köprünün SQL'i:**
```sql
(SQL üretilmedi)
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT SUM(CASE WHEN LEFT(ACCOUNTCODE,2)='60' THEN CREDIT-DEBIT ELSE 0 END) AS brut_satis_60, SUM(CASE WHEN LEFT(ACCOUNTCODE,3)='610' THEN DEBIT-CREDIT ELSE 0 END) AS iade_610, SUM(CASE WHEN LEFT(ACCOUNTCODE,3)='611' THEN DEBIT-CREDIT ELSE 0 END) AS iskonto_611, SUM(CASE WHEN LEFT(ACCOUNTCODE,3)='612' THEN DEBIT-CREDIT ELSE 0 END) AS diger_indirim_612, (SUM(CASE WHEN LEFT(ACCOUNTCODE,2)='60' THEN CREDIT-DEBIT ELSE 0 END) - SUM(CASE WHEN LEFT(ACCOUNTCODE,2)='61' THEN DEBIT-CREDIT ELSE 0 END)) AS net_satis FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND LEFT(ACCOUNTCODE,2) IN ('60','61')
```

### M076 · Bu yıl kaç satış faturası kestik?

**Hüküm:** ✅ Doğru (2. okuma) — 73.660 (iade dahil satış kapsamı); iade hariç 70.664 — iş tanımı 73.660  
**Referans tanımı:** Satış faturası = INVOICE TRCODE 7 perakende + 8 toptan + 9 verilen hizmet (bizim kestiklerimiz), iptal hariç, 2026.

**Köprünün SQL'i:**
```sql
SELECT COUNT(DISTINCT INVOICE.[LOGICALREF]) AS kayit_sayisi
FROM [dbo].[LG_411_01_INVOICE] AS INVOICE
WHERE INVOICE.[CANCELLED] = 0
  AND INVOICE.[GRPCODE] IN (2)
  AND INVOICE.[DATE_] >= '2026-01-01' AND INVOICE.[DATE_] < '2027-01-01'
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT SUM(CASE WHEN TRCODE IN (7,8,9) THEN 1 ELSE 0 END) AS satis_faturasi_789, SUM(CASE WHEN TRCODE IN (2,3,7,8,9) THEN 1 ELSE 0 END) AS satis_kapsami_23789, SUM(CASE WHEN TRCODE IN (2,3) THEN 1 ELSE 0 END) AS iade_23 FROM LG_411_01_INVOICE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101'
```

### M077 · Toptan ve perakende satışlarımızın payı ne?

**Hüküm:** ⚠️ Gereksiz ret — Toptan/perakende payını birleştiremedi  
**Referans tanımı:** Toptan = TRCODE 8 − iade 3, Perakende = TRCODE 7 − iade 2; KDV hariç (NETTOTAL−TOTALVAT), 2026; pay = kanal / (toptan+perakende). Verilen hi

**Köprünün SQL'i:**
```sql
(SQL üretilmedi)
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT kanal, net, CAST(100.0*net/SUM(net) OVER () AS decimal(9,2)) AS pay_yuzde, brut_iade_oncesi FROM (SELECT CASE WHEN TRCODE IN (8,3) THEN 'Toptan' ELSE 'Perakende' END AS kanal, SUM(CASE WHEN TRCODE IN (7,8) THEN NETTOTAL-TOTALVAT ELSE -(NETTOTAL-TOTALVAT) END) AS net, SUM(CASE WHEN TRCODE IN (7,8) THEN NETTOTAL-TOTALVAT ELSE 0 END) AS brut_iade_oncesi FROM LG_411_01_INVOICE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND TRCODE IN (2,3,7,8) GROUP BY CASE WHEN TRCODE IN (8,3) THEN 'Toptan' ELSE 'Perakende' END) t ORDER BY net DESC
```

### M078 · İade oranımız yüzde kaç?

**Hüküm:** ✅ Doğru (2. okuma) — Fatura tutarına göre ~%8,1; defterden %7,76  
**Referans tanımı:** İade oranı = 610 Satış iadeleri / 60 brüt satış (defter), 2026.

**Köprünün SQL'i:**
```sql
-- yorum: 'iade oranı' → INVOICE.TRCODE (2,3) iade / (7,8,9) satış, NETTOTAL üzerinden yüzde.
SELECT
    SUM(CASE WHEN "TRCODE" IN (2, 3) THEN "NETTOTAL" ELSE 0 END) AS iade_tutari,
    SUM(CASE WHEN "TRCODE" IN (7, 8, 9) THEN "NETTOTAL" ELSE 0 END) AS satis_tutari,
    (SUM(CASE WHEN "TRCODE" IN (2, 3) THEN "NETTOTAL" ELSE 0 END) * 100.0)
        / NULLIF(SUM(CASE WHEN "TRCODE" IN (7, 8, 9) THEN "NETTOTAL" ELSE 0 END), 0) AS iade_orani_yuzde
FROM INVOICE
WHERE "CANCELLED" = 0
  AND "TRCODE" IN (2, 3, 7, 8, 9)
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT CAST(100.0*(SELECT SUM(DEBIT-CREDIT) FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND ACCOUNTCODE LIKE '610%' )/(SELECT SUM(CREDIT-DEBIT) FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND ACCOUNTCODE LIKE '60%' ) AS decimal(9,3)) AS iade_orani_610_brut_satis, CAST(100.0*(SELECT SUM(NETTOTAL) FROM LG_411_01_INVOICE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND TRCODE IN (2,3) )/(SELECT SUM(NETTOTAL) FROM LG_411_01_INVOICE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND TRCODE IN (7,8,9) ) AS decimal(9,3)) AS iade_orani_fatura_tutar, CAST(100.0*(SELECT SUM(1) FROM LG_411_01_INVOICE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND TRCODE IN (2,3) )/(SELECT SUM(1) FROM LG_411_01_INVOICE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND TRCODE IN (7,8,9) ) AS decimal(9,3)) AS iade_orani_fatura_adet
```

### M079 · Dövizli faturalarımızın toplam tutarı ne kadar?

**Hüküm:** ❌ Yanlış değer — 4,9 Mn; dövizli fatura toplamı tutmuyor  
**Referans tanımı:** Dövizli fatura = INVOICE.TRCURR <> 0 (0 = TL), iptal hariç, 2026, tüm türler; TL karşılığı NETTOTAL (KDV dahil), döviz tutarı TRNET; döviz k

**Köprünün SQL'i:**
```sql
-- yorum: 'dovizli' → INVOICE.TRCURR <> 0, dövizli fatura filtresi
SELECT SUM(INVOICE.[NETTOTAL]) AS toplam_tutar
FROM [dbo].[INVOICE] AS INVOICE
WHERE INVOICE.[CANCELLED] = 0
  AND INVOICE.[TRCODE] IN (2, 3, 7, 8, 9)
  AND INVOICE.[TRCURR] <> 0
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT C.CURCODE AS doviz, COUNT(*) AS fatura, SUM(V.TRNET) AS doviz_tutari, SUM(V.NETTOTAL) AS tl_karsiligi_kdv_dahil, SUM(CASE WHEN V.TRCODE IN (7,8,9) THEN V.NETTOTAL ELSE 0 END) AS tl_satis, SUM(CASE WHEN V.TRCODE IN (1,4) THEN V.NETTOTAL ELSE 0 END) AS tl_alis FROM LG_411_01_INVOICE V LEFT JOIN L_CURRENCYLIST C ON C.FIRMNR=411 AND C.CURTYPE=V.TRCURR WHERE V.CANCELLED=0 AND V.DATE_>='20260101' AND DATE_<'20270101' AND V.TRCURR<>0 GROUP BY C.CURCODE ORDER BY tl_karsiligi_kdv_dahil DESC
```

### M080 · Bu yılki pazarlama giderlerimiz ne kadar?

**Hüküm:** ❌ Yanlış değer — −204,9 Mn (işaret ters); pazarlama 242,4 Mn  
**Referans tanımı:** Pazarlama giderleri = 760 Pazarlama Satış Dağıtım Giderleri borç−alacak, 2026 (761 yansıtma hariç).

**Köprünün SQL'i:**
```sql
-- yorum: 'pazarlama' → EMUHACC.DEFINITION_ içinde 'pazarlama' geçen 7'li gider hesapları
SELECT SUM(EMFLINE.[DEBIT] - EMFLINE.[CREDIT]) AS pazarlama_gideri
FROM [dbo].[EMFLINE] AS EMFLINE
INNER JOIN [dbo].[EMUHACC] AS EMUHACC
    ON EMFLINE.[ACCOUNTREF] = EMUHACC.[LOGICALREF]
WHERE EMFLINE.[CANCELLED] = 0
  AND EMFLINE.[ACCOUNTCODE] LIKE '7%'
  AND EMUHACC.[DEFINITION_] LIKE '%pazarlama%'
  AND EMFLINE.[DATE_] >= '2026-01-01'
  AND EMFLINE.[DATE_] < '2027-01-01'
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT (SELECT SUM(DEBIT-CREDIT) FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND ACCOUNTCODE LIKE '760%' ) AS pazarlama_760
```

### M081 · Genel yönetim giderlerimiz toplam ne?

**Hüküm:** ❌ Yanlış değer — 65,3 Mn = yine 7'li toplam; genel yönetim 54,1 Mn  
**Referans tanımı:** Genel yönetim giderleri = 770 borç−alacak, 2026 (771 yansıtma hariç).

**Köprünün SQL'i:**
```sql
-- yorum: 'giderlerimiz' → EMFLINE.DEBIT - EMFLINE.CREDIT, ACCOUNTCODE LIKE '7%', CANCELLED = 0
SELECT SUM("DEBIT" - "CREDIT") AS gider_toplam
FROM EMFLINE
WHERE "CANCELLED" = 0
  AND "ACCOUNTCODE" LIKE '7%'
  AND "DATE_" >= '2026-01-01'
  AND "DATE_" < '2027-01-01'
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT (SELECT SUM(DEBIT-CREDIT) FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND ACCOUNTCODE LIKE '770%' ) AS genel_yonetim_770
```

### M082 · Masraf merkezlerine göre giderlerimiz nasıl dağılıyor?

**Hüküm:** ❌ Yanlış değer — 1.628 merkez; gider yazılan 1.851  
**Referans tanımı:** Masraf merkezi gideri = 7 grubu gider hesapları (xx1 yansıtma hesapları hariç: fiilen 710, 730, 760, 770, 780) borç−alacak, CENTERREF>0, EMC

**Köprünün SQL'i:**
```sql
-- yorum: 'masraf merkezlerine' → EMCENTER.DEFINITION_ (masraf merkezi adı)
-- yorum: 'giderlerimiz' → SUM(EMFLINE.DEBIT - EMFLINE.CREDIT), ACCOUNTCODE LIKE '7%', CANCELLED = 0
SELECT
    c."DEFINITION_" AS masraf_merkezi,
    SUM(f."DEBIT" - f."CREDIT") AS gider
FROM EMFLINE f
JOIN EMCENTER c ON f."CENTERREF" = c."LOGICALREF"
WHERE f."CANCELLED" = 0
  AND f."ACCOUNTCODE" LIKE '7%'
  AND f."DATE_" >= '2026-01-01'
  AND f."DATE_" < '2027-01-01'
GROUP BY c."DEFINITION_"
ORDER BY gider DESC
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT C.CODE AS merkez_kodu, C.DEFINITION_ AS merkez, SUM(L.DEBIT-L.CREDIT) AS gider FROM LG_411_01_EMFLINE L JOIN LG_411_EMCENTER C ON C.LOGICALREF=L.CENTERREF WHERE L.CANCELLED=0 AND L.DATE_>='20260101' AND DATE_<'20270101' AND L.CENTERREF>0 AND LEFT(L.ACCOUNTCODE,1)='7' AND SUBSTRING(L.ACCOUNTCODE,3,1)<>'1' GROUP BY C.CODE, C.DEFINITION_ ORDER BY gider DESC
```

### M083 · En çok gider yazılan on masraf merkezi hangisi?

**Hüküm:** ✅ Doğru — En çok gider yazılan 10 merkez, Genel Müdürlük başta  
**Referans tanımı:** M082 tanımıyla ilk 10 masraf merkezi (gider büyükten küçüğe).

**Köprünün SQL'i:**
```sql
-- yorum: 'yazilan' → EMFLINE.DEBIT - EMFLINE.CREDIT toplamı (gider tutarı)
SELECT TOP 10
    ec."CODE" AS masraf_merkezi_kodu,
    ec."DEFINITION_" AS masraf_merkezi,
    SUM(ef."DEBIT" - ef."CREDIT") AS gider_tutari
FROM EMFLINE ef
JOIN EMCENTER ec ON ec."LOGICALREF" = ef."CENTERREF"
WHERE ef."CANCELLED" = 0
  AND ef."ACCOUNTCODE" LIKE '7%'
  AND ef."DATE_" >= '2026-01-01'
  AND ef."DATE_" < '2027-01-01'
GROUP BY ec."CODE", ec."DEFINITION_"
ORDER BY gider_tutari DESC
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT TOP 10 C.CODE AS merkez_kodu, C.DEFINITION_ AS merkez, SUM(L.DEBIT-L.CREDIT) AS gider FROM LG_411_01_EMFLINE L JOIN LG_411_EMCENTER C ON C.LOGICALREF=L.CENTERREF WHERE L.CANCELLED=0 AND L.DATE_>='20260101' AND DATE_<'20270101' AND L.CENTERREF>0 AND LEFT(L.ACCOUNTCODE,1)='7' AND SUBSTRING(L.ACCOUNTCODE,3,1)<>'1' GROUP BY C.CODE, C.DEFINITION_ ORDER BY gider DESC
```

### M084 · Aylara göre giderlerimiz nasıl değişiyor?

**Hüküm:** ✅ Doğru — Aylık gider dağılımı  
**Referans tanımı:** Aylık gider = 7 grubu gider hesapları (yansıtma xx1 hariç) borç−alacak, 2026 aylara göre; faaliyet giderleri (760+770) ayrı kolon.

**Köprünün SQL'i:**
```sql
-- yorum: 'giderlerimiz' → EMFLINE.DEBIT - EMFLINE.CREDIT, ACCOUNTCODE LIKE '7%', CANCELLED = 0
SELECT 
    DATEFROMPARTS(YEAR("DATE_"), MONTH("DATE_"), 1) AS ay,
    SUM("DEBIT" - "CREDIT") AS gider
FROM EMFLINE
WHERE "CANCELLED" = 0
  AND "ACCOUNTCODE" LIKE '7%'
  AND "DATE_" >= '2026-01-01'
  AND "DATE_" < '2027-01-01'
GROUP BY DATEFROMPARTS(YEAR("DATE_"), MONTH("DATE_"), 1)
ORDER BY ay
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT MONTH(DATE_) AS ay, SUM(DEBIT-CREDIT) AS gider, SUM(CASE WHEN LEFT(ACCOUNTCODE,3) IN ('760','770') THEN DEBIT-CREDIT ELSE 0 END) AS faaliyet_760_770 FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND LEFT(ACCOUNTCODE,1)='7' AND SUBSTRING(ACCOUNTCODE,3,1)<>'1' GROUP BY MONTH(DATE_) ORDER BY ay
```

### M085 · Pazarlama ile genel yönetim giderlerini karşılaştırır mısın?

**Hüküm:** ❌ Yanlış değer — Pazarlama 10,2 Mn; doğru 242,4 Mn  
**Referans tanımı:** 760 Pazarlama vs 770 Genel yönetim, borç−alacak, 2026.

**Köprünün SQL'i:**
```sql
-- yorum: 'pazarlama' → EMCENTER.SPECODE = 'PAZARLAMA ' ile masraf merkezi gideri
-- yorum: 'karsilastirir' → karşılaştırma: pazarlama ve genel yönetim giderleri yan yana
SELECT
    CASE
        WHEN c."SPECODE" = 'PAZARLAMA ' THEN 'Pazarlama'
        ELSE 'Genel Yönetim'
    END AS gider_kategorisi,
    SUM(f."DEBIT" - f."CREDIT") AS gider_tutari
FROM EMFLINE f
JOIN EMCENTER c ON f."CENTERREF" = c."LOGICALREF"
WHERE f."CANCELLED" = 0
  AND f."ACCOUNTCODE" LIKE '7%'
  AND f."DATE_" >= '2026-01-01'
  AND f."DATE_" < '2027-01-01'
  AND (c."SPECODE" = 'PAZARLAMA ' OR c."SPECODE" = 'GENEL YÖNETİM')
GROUP BY
    CASE
        WHEN c."SPECODE" = 'PAZARLAMA ' THEN 'Pazarlama'
        ELSE 'Genel Yönetim'
    END
ORDER BY gider_tutari DESC
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT LEFT(ACCOUNTCODE,3) AS hesap, CASE LEFT(ACCOUNTCODE,3) WHEN '760' THEN 'Pazarlama satış dağıtım' ELSE 'Genel yönetim' END AS ad, SUM(DEBIT-CREDIT) AS gider FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND LEFT(ACCOUNTCODE,3) IN ('760','770') GROUP BY LEFT(ACCOUNTCODE,3) ORDER BY gider DESC
```

### M086 · Giderlerimiz geçen aya göre arttı mı?

**Hüküm:** ⚠️ Gereksiz ret — Kapsam doğrulanamadı diye reddetti  
**Referans tanımı:** 'Geçen ay' = Ağustos 2026. Eş dönem: Ağustos 1–17 vs Temmuz 1–17 (birincil); Temmuz tamamı ayrıca. Gider = 7 grubu gider hesapları (yansıtma

**Köprünün SQL'i:**
```sql
(SQL üretilmedi)
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT (SELECT SUM(DEBIT-CREDIT) FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND LEFT(ACCOUNTCODE,1)='7' AND SUBSTRING(ACCOUNTCODE,3,1)<>'1' AND DATE_>='20260801' AND DATE_<'20260818') AS agustos_1_17, (SELECT SUM(DEBIT-CREDIT) FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND LEFT(ACCOUNTCODE,1)='7' AND SUBSTRING(ACCOUNTCODE,3,1)<>'1' AND DATE_>='20260701' AND DATE_<'20260718') AS temmuz_1_17, (SELECT SUM(DEBIT-CREDIT) FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND LEFT(ACCOUNTCODE,1)='7' AND SUBSTRING(ACCOUNTCODE,3,1)<>'1' AND DATE_>='20260701' AND DATE_<'20260801') AS temmuz_tamami, (SELECT SUM(DEBIT-CREDIT) FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND LEFT(ACCOUNTCODE,1)='7' AND SUBSTRING(ACCOUNTCODE,3,1)<>'1' AND DATE_>='20260601' AND DATE_<'20260701') AS haziran_tamami
```

### M087 · Hizmet alımlarımızın toplam tutarı ne kadar?

**Hüküm:** ❌ Yanlış değer — 297,2 Mn hizmet kartından; muhasebe 249,8 Mn  
**Referans tanımı:** Hizmet alımları = INVOICE TRCODE 4 Alınan hizmet faturası, KDV hariç (NETTOTAL−TOTALVAT), iptal hariç, 2026.

**Köprünün SQL'i:**
```sql
-- yorum: 'hizmet' → INVOICE.TRCODE = 4 (alınan hizmet faturası)
-- yorum: 'alimlarimizin' → INVOICE.NETTOTAL (KDV dahil net tutar)
SELECT SUM(INVOICE.[NETTOTAL]) AS hizmet_alim_tutari
FROM [dbo].[INVOICE] AS INVOICE
WHERE INVOICE.[CANCELLED] = 0
  AND INVOICE.[TRCODE] = 4
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT (SELECT SUM(NETTOTAL-TOTALVAT) FROM LG_411_01_INVOICE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND TRCODE IN (4) ) AS hizmet_alim_kdv_haric, (SELECT SUM(NETTOTAL) FROM LG_411_01_INVOICE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND TRCODE IN (4) ) AS hizmet_alim_kdv_dahil, (SELECT SUM(1) FROM LG_411_01_INVOICE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND TRCODE IN (4) ) AS fatura_adet
```

### M088 · Giderlerin satışlara oranı yüzde kaç?

**Hüküm:** ❌ Yanlış değer — %7,08 (yine 65,3 Mn gider); doğru %35,2  
**Referans tanımı:** Gider/satış oranı = faaliyet giderleri (760+770) / net satış (gelir tablosu), 2026.

**Köprünün SQL'i:**
```sql
-- yorum: 'giderlerin' → EMFLINE.DEBIT - EMFLINE.CREDIT (ACCOUNTCODE LIKE '7%'), 'satışlara' → STLINE.LINENET (TRCODE 7,8,9)
SELECT 
    gider,
    satis,
    (gider / NULLIF(satis, 0)) * 100 AS gider_orani_yuzde
FROM (
    SELECT 
        (SELECT SUM(e.DEBIT - e.CREDIT) 
         FROM dbo_LG_411_01_EMFLINE e
         WHERE e.CANCELLED = 0
           AND e.ACCOUNTCODE LIKE '7%'
           AND e.DATE_ >= '2026-01-01'
           AND e.DATE_ < '2027-01-01') AS gider,
        (SELECT SUM(s.LINENET) 
         FROM dbo_LG_411_01_STLINE s
         WHERE s.CANCELLED = 0
           AND s.LINETYPE = 0
           AND s.TRCODE IN (7, 8, 9)
           AND s.DATE_ >= '2026-01-01'
           AND s.DATE_ < '2027-01-01') AS satis
) t
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT CAST(100.0*SUM(CASE WHEN LEFT(ACCOUNTCODE,3) IN ('760','770') THEN DEBIT-CREDIT ELSE 0 END)/(SUM(CASE WHEN LEFT(ACCOUNTCODE,2)='60' THEN CREDIT-DEBIT ELSE 0 END) - SUM(CASE WHEN LEFT(ACCOUNTCODE,2)='61' THEN DEBIT-CREDIT ELSE 0 END)) AS decimal(9,2)) AS faaliyet_gideri_orani, CAST(100.0*SUM(CASE WHEN LEFT(ACCOUNTCODE,1)='7' AND SUBSTRING(ACCOUNTCODE,3,1)<>'1' THEN DEBIT-CREDIT ELSE 0 END)/(SUM(CASE WHEN LEFT(ACCOUNTCODE,2)='60' THEN CREDIT-DEBIT ELSE 0 END) - SUM(CASE WHEN LEFT(ACCOUNTCODE,2)='61' THEN DEBIT-CREDIT ELSE 0 END)) AS decimal(9,2)) AS tum_7_gider_orani, SUM(CASE WHEN LEFT(ACCOUNTCODE,3) IN ('760','770') THEN DEBIT-CREDIT ELSE 0 END) AS faaliyet_gideri, (SUM(CASE WHEN LEFT(ACCOUNTCODE,2)='60' THEN CREDIT-DEBIT ELSE 0 END) - SUM(CASE WHEN LEFT(ACCOUNTCODE,2)='61' THEN DEBIT-CREDIT ELSE 0 END)) AS net_satis FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101'
```

### M089 · Kaç tane masraf merkezimiz var?

**Hüküm:** ✅ Doğru (2. okuma) — 17.343 tanımlı merkez (düşük güvenli soru)  
**Referans tanımı:** Masraf merkezi sayısı = LG_411_EMCENTER; kullanımda = ACTIVE=0 (katalog: 0=Kullanımda, 1=Kullanım dışı).

**Köprünün SQL'i:**
```sql
-- yorum: 'masraf merkezimiz' → EMCENTER tablosu, COUNT(*) ile toplam kayıt sayısı.
SELECT COUNT(*) AS masraf_merkezi_sayisi
FROM EMCENTER
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT SUM(CASE WHEN ACTIVE=0 THEN 1 ELSE 0 END) AS kullanimda, COUNT(*) AS tanimli_toplam, (SELECT COUNT(DISTINCT CENTERREF) FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND CENTERREF>0) AS yil_icinde_kullanilan, (SELECT COUNT(DISTINCT CENTERREF) FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND CENTERREF>0 AND LEFT(ACCOUNTCODE,1)='7' AND SUBSTRING(ACCOUNTCODE,3,1)<>'1') AS gider_yazilan FROM LG_411_EMCENTER
```

### M090 · Sabit kıymetlerimizin toplam giriş maliyeti ne kadar?

**Hüküm:** ⚠️ Gereksiz ret — 'sabit kıymet giriş' tanımsız diye reddetti — bugün eklenen kavram yakalanmadı  
**Referans tanımı:** Toplam giriş maliyeti = LG_411_FAREGIST SUM(INVALUE), CANCELLED=0 (tüm sicil, elden çıkanlar dahil).

**Köprünün SQL'i:**
```sql
(SQL üretilmedi)
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT SUM(INVALUE) AS giris_maliyeti, COUNT(*) AS kayit, SUM(CASE WHEN QUANTITY>TOTOUT THEN INVALUE ELSE 0 END) AS elde_olan_maliyet, (SELECT SUM(INVALUE) FROM LG_411_FAREGIST) AS iptaller_dahil FROM LG_411_FAREGIST WHERE CANCELLED=0
```

### M091 · Birikmiş amortisman toplamımız ne?

**Hüküm:** ❌ Yanlış değer — 340.063; doğru 30,3 Mn — yıl filtresi girdi  
**Referans tanımı:** Birikmiş amortisman = FAREGIST SUM(ACCUMDEPR), CANCELLED=0.

**Köprünün SQL'i:**
```sql
SELECT SUM(FAREGIST.[ACCUMDEPR]) AS sabit_kiymet_amortismani
FROM [dbo].[LG_411_FAREGIST] AS FAREGIST
WHERE FAREGIST.[CANCELLED] IN (0)
  AND FAREGIST.[DATEIN] >= '2026-01-01' AND FAREGIST.[DATEIN] < '2027-01-01'
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT SUM(ACCUMDEPR) AS birikmis_amortisman, SUM(BEGDEPR) AS kayitli_devir_amortismani, SUM(ACCUMDEPR+BEGDEPR) AS toplam_devir_dahil, (SELECT SUM(ACCUMDEPR) FROM LG_411_FAREGIST) AS iptaller_dahil, (SELECT SUM(CREDIT-DEBIT) FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' AND LEFT(ACCOUNTCODE,3) IN ('257','268')) AS defter_257_268_bakiye FROM LG_411_FAREGIST WHERE CANCELLED=0
```

### M092 · Sabit kıymet gruplarına göre maliyetler nasıl dağılıyor?

**Hüküm:** ⚠️ Gereksiz ret — 'gruplarına' tanımsız diye reddetti  
**Referans tanımı:** Sabit kıymet grubu = kıymetin malzeme kartı (FAREGIST.CRDREF → LG_411_ITEMS, CARDTYPE 4) kodunun ilk 3 hanesi = TDHP hesap grubu (EMUHACC ad

**Köprünün SQL'i:**
```sql
(SQL üretilmedi)
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT LEFT(IT.CODE,3) AS hesap_grubu, MAX(A.DEFINITION_) AS grup, COUNT(*) AS kayit, SUM(F.INVALUE) AS giris_maliyeti, SUM(F.ACCUMDEPR) AS birikmis_amortisman FROM LG_411_FAREGIST F JOIN LG_411_ITEMS IT ON IT.LOGICALREF=F.CRDREF LEFT JOIN LG_411_EMUHACC A ON A.CODE=LEFT(IT.CODE,3) WHERE F.CANCELLED=0 GROUP BY LEFT(IT.CODE,3) ORDER BY giris_maliyeti DESC
```

### M093 · Bu yıl kaç yeni sabit kıymet aldık?

**Hüküm:** ✅ Doğru — 58 yeni kıymet, birebir  
**Referans tanımı:** Bu yıl yeni sabit kıymet = FAREGIST DATEIN 2026 içinde, CANCELLED=0 (hepsi TRANSFER=0 satınalma).

**Köprünün SQL'i:**
```sql
-- yorum: 'sabit' → FAREGIST tablosu, sabit kıymet kayıtları
-- yorum: 'kiymet' → FAREGIST tablosu, sabit kıymet kayıtları
SELECT COUNT(*) AS yeni_sabit_kiymet_sayisi
FROM FAREGIST
WHERE "DATEIN" >= '2026-01-01'
  AND "DATEIN" < '2027-01-01'
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT COUNT(*) AS yeni_kiymet, SUM(INVALUE) AS maliyet, SUM(CASE WHEN TRANSFER=0 THEN 1 ELSE 0 END) AS satinalma_kaydi, SUM(QUANTITY) AS adet FROM LG_411_FAREGIST WHERE CANCELLED=0 AND DATEIN>='20260101' AND DATEIN<'20270101'
```

### M094 · Amortismanı tamamen bitmiş kıymetler hangileri?

**Hüküm:** ❌ Veri varken 'yok' — 'kayıt yok'; 226 kıymetin amortismanı bitmiş  
**Referans tanımı:** Amortismanı bitmiş = INVALUE>0 ve ACCUMDEPR+BEGDEPR ≥ INVALUE, CANCELLED=0, elde (QUANTITY>TOTOUT). Giriş maliyetine göre sıralı.

**Köprünün SQL'i:**
```sql
-- yorum: 'kiymetler' → FAREGIST tablosu, sabit kıymet kayıtları
-- yorum: 'bitmis' → FAREGIST.ACCUMDEPR >= FAREGIST.INVALUE (amortisman giriş maliyetine ulaşmış)
SELECT 
    "LOGICALREF",
    "REGDEFINITION",
    "INVALUE",
    "ACCUMDEPR",
    "DEPRRATE",
    "DATEOFDEPR"
FROM FAREGIST
WHERE "CANCELLED" = 0
  AND "DATEIN" >= '2026-01-01'
  AND "DATEIN" < '2027-01-01'
  AND "INVALUE" > 0
  AND "ACCUMDEPR" >= "INVALUE"
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT F.REGCODE, F.REGDEFINITION, F.DATEIN, F.INVALUE, F.ACCUMDEPR+F.BEGDEPR AS amortisman FROM LG_411_FAREGIST F WHERE F.CANCELLED=0 AND F.QUANTITY>F.TOTOUT AND F.INVALUE>0 AND F.ACCUMDEPR+F.BEGDEPR>=F.INVALUE-0.01 ORDER BY F.INVALUE DESC
```

### M095 · Bu yıl kaç muhasebe fişi kesildi?

**Hüküm:** ✅ Doğru — 91.559 fiş, birebir  
**Referans tanımı:** Muhasebe fişi = LG_411_01_EMFICHE, CANCELLED=0, 2026 (01.01–17.08).

**Köprünün SQL'i:**
```sql
-- yorum: 'muhasebe' → EMFICHE tablosu (Muhasebe fişleri)
-- yorum: 'fisi' → EMFICHE.LOGICALREF (fiş sayısı)
SELECT COUNT("LOGICALREF") AS muhasebe_fisi_sayisi
FROM EMFICHE
WHERE "DATE_" >= '2026-01-01'
  AND "DATE_" < '2027-01-01'
  AND "CANCELLED" = 0
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT COUNT(*) AS fis, SUM(CASE WHEN TRCODE<>1 THEN 1 ELSE 0 END) AS acilis_haric FROM LG_411_01_EMFICHE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101'
```

### M096 · Fiş türlerine göre dağılım nasıl?

**Hüküm:** ❌ Yanlış değer — 15 grup; fiş türü 5  
**Referans tanımı:** Fiş türü = EMFICHE.TRCODE (katalog: 1 açılış, 2 tahsil, 3 tediye, 4 mahsup, 5 özel, 6 kur farkı), 2026.

**Köprünün SQL'i:**
```sql
-- yorum: 'fis' → EMFICHE.MODULENR modül numarası, TRCODE fiş türü; dağılım COUNT ve NETTOTAL toplamı.
SELECT
    "MODULENR" AS modul_no,
    "TRCODE" AS fis_turu,
    COUNT(*) AS fis_sayisi
FROM EMFICHE
WHERE "CANCELLED" = 0
GROUP BY "MODULENR", "TRCODE"
ORDER BY "MODULENR", "TRCODE"
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT TRCODE, CASE TRCODE WHEN 1 THEN 'Açılış' WHEN 2 THEN 'Tahsil' WHEN 3 THEN 'Tediye' WHEN 4 THEN 'Mahsup' WHEN 5 THEN 'Özel' WHEN 6 THEN 'Kur farkı' END AS fis_turu, COUNT(*) AS fis FROM LG_411_01_EMFICHE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' GROUP BY TRCODE ORDER BY fis DESC
```

### M097 · Borç ve alacağı tutmayan fiş var mı?

**Hüküm:** ❌ Yanlış değer — 4 'tutmayan' fiş buldu; gerçekte dengesiz fiş YOK — yanlış alarm  
**Referans tanımı:** Tutmayan fiş = fiş satırlarında (EMFLINE, iptal hariç) SUM(DEBIT) ≠ SUM(CREDIT) (0,01 tolerans). Ek kontrol (ek_sql): başlıkta TOTALACTIVE ≠

**Köprünün SQL'i:**
```sql
-- yorum: 'borc' → CLFICHE.REPDEBIT (cari fişinin borç toplamı)
-- yorum: 'alacagi' → CLFICHE.REPCREDIT (cari fişinin alacak toplamı)
-- yorum: 'fis' → CLFICHE (cari hesap fişleri)
-- yorum: 'tutmayan' → CLFICHE.REPDEBIT <> CLFICHE.REPCREDIT (fişin borç ve alacak toplamlarının eşit olmaması)
SELECT 
    "LOGICALREF",
    "FICHENO",
    "DATE_",
    "REPDEBIT",
    "REPCREDIT"
FROM CLFICHE
WHERE "CANCELLED" = 0
  AND "REPDEBIT" <> "REPCREDIT"
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT H.FICHENO, H.DATE_, H.TRCODE, L.borc, L.alacak, L.borc-L.alacak AS fark FROM (SELECT ACCFICHEREF, SUM(DEBIT) AS borc, SUM(CREDIT) AS alacak, COUNT(*) AS satir FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' GROUP BY ACCFICHEREF) L JOIN LG_411_01_EMFICHE H ON H.LOGICALREF=L.ACCFICHEREF WHERE H.CANCELLED=0 AND ABS(L.borc-L.alacak)>0.01 ORDER BY ABS(L.borc-L.alacak) DESC
```

### M098 · Aylara göre muhasebe fişi sayısı nasıl?

**Hüküm:** ✅ Doğru — Aylık fiş sayısı  
**Referans tanımı:** Aylık muhasebe fişi sayısı = EMFICHE CANCELLED=0, 2026 aylara göre.

**Köprünün SQL'i:**
```sql
-- yorum: 'muhasebe' → EMFICHE tablosu, muhasebe fişleri
-- yorum: 'fisi' → EMFICHE.LOGICALREF, COUNT ile sayım
SELECT 
    DATEFROMPARTS(YEAR("DATE_"), MONTH("DATE_"), 1) AS ay,
    COUNT("LOGICALREF") AS fisi_sayisi
FROM EMFICHE
WHERE "CANCELLED" = 0
GROUP BY DATEFROMPARTS(YEAR("DATE_"), MONTH("DATE_"), 1)
ORDER BY ay
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT MONTH(DATE_) AS ay, COUNT(*) AS fis FROM LG_411_01_EMFICHE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' GROUP BY MONTH(DATE_) ORDER BY ay
```

### M099 · En çok satırlı on muhasebe fişi hangileri?

**Hüküm:** ✅ Doğru — En çok satırlı 10 fiş  
**Referans tanımı:** Fiş başına satır = EMFLINE (iptal hariç) ACCFICHEREF'e göre COUNT, en çok 10; EMFICHE'den fiş no/tarih/tür.

**Köprünün SQL'i:**
```sql
-- yorum: 'satirli' → EMFLINE satır sayısı (COUNT) üzerinden sıralama
-- yorum: 'muhasebe' → EMFICHE (muhasebe fişi) tablosu
-- yorum: 'fisi' → EMFICHE.LOGICALREF ve FICHENO
SELECT TOP 10
    f."LOGICALREF" AS fisi_ref,
    f."FICHENO" AS fisi_no,
    f."DATE_" AS tarih,
    f."TRCODE" AS fisi_turu,
    COUNT(l."LOGICALREF") AS satir_sayisi
FROM EMFICHE f
JOIN EMFLINE l ON l."ACCFICHEREF" = f."LOGICALREF"
WHERE f."CANCELLED" = 0
GROUP BY f."LOGICALREF", f."FICHENO", f."DATE_", f."TRCODE"
ORDER BY satir_sayisi DESC
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT TOP 10 H.FICHENO, H.DATE_, H.TRCODE, L.satir, L.borc FROM (SELECT ACCFICHEREF, SUM(DEBIT) AS borc, SUM(CREDIT) AS alacak, COUNT(*) AS satir FROM LG_411_01_EMFLINE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101' GROUP BY ACCFICHEREF) L JOIN LG_411_01_EMFICHE H ON H.LOGICALREF=L.ACCFICHEREF WHERE H.CANCELLED=0 ORDER BY L.satir DESC, H.FICHENO
```

### M100 · Bu ay hiç muhasebe kaydı girildi mi?

**Hüküm:** ❌ Yanlış değer — '0' dedi; doğrusu 'veri 17.08'de bitiyor' demekti  
**Referans tanımı:** 'Bu ay' = Eylül 2026. EMFICHE fiş tarihi (DATE_) veya giriş tarihi (CAPIBLOCK_CREADEDDATE) ≥ 01.09.2026.

**Köprünün SQL'i:**
```sql
-- yorum: 'muhasebe' → EMUHACC.CYPHCODE = 'MUHASEBE' (muhasebe hesapları)
SELECT COUNT(*) AS muhasebe_kayit_sayisi
FROM EMUHACC
WHERE EMUHACC."CYPHCODE" = 'MUHASEBE'
  AND EMUHACC."CAPIBLOCK_CREADEDDATE" >= '2026-09-01'
  AND EMUHACC."CAPIBLOCK_CREADEDDATE" < '2026-10-01'
```
**Referans SQL (bağımsız, DB'de çalıştırıldı):**
```sql
SELECT SUM(CASE WHEN DATE_>='20260901' THEN 1 ELSE 0 END) AS eylul_tarihli_fis, SUM(CASE WHEN CAPIBLOCK_CREADEDDATE>='20260901' THEN 1 ELSE 0 END) AS eylulde_girilen_fis, MAX(DATE_) AS son_fis_tarihi, MAX(CAPIBLOCK_CREADEDDATE) AS son_giris_tarihi FROM LG_411_01_EMFICHE WHERE CANCELLED=0
```