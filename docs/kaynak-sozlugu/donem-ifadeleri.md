# Dönem ifadeleri (test listesi taslağı)

Tarih: 2026-10-01. Kaynak: [`yonlendirme-seti.jsonl`](yonlendirme-seti.jsonl) içindeki `donem_ham` alanı
(set100 ve set1000, 1.100 soru). Sorulardaki dönem ifadelerini elle, ham metin olarak çıkardım; ayrıştırıcı
koşturulmadı. Büyük/küçük harf birleştirildi, ek ve yazım olduğu gibi bırakıldı ("bu yıl", "bu yılki", "bu yılın" ayrı
satırlardır). Ayrıştırıcı bunları aynı döneme çözmelidir.

## Sayılar

- Dönem ifadesi geçen soru: **444**. Dönem ifadesi geçmeyen soru: **656** (%60). Dönem söylemeyen sorularda varsayılan
  dönem kuralı uygulanmalı ve cevapta söylenmeli.
- Toplam ifade: **516** geçiş, **205** farklı ham ifade.

| Tür | Geçiş | Farklı ifade | Ayrıştırıcıdan beklenen |
|---|---:|---:|---|
| T01 göreli takvim birimi | 242 | 29 | Bu/geçen yıl, ay, hafta, çeyrek, gün; "bugün", "dün"; yarı açık `[başlangıç, bitiş)` |
| T07 tanecik / kırılım ifadesi | 58 | 17 | Dönem değil, kırılım: "ay ay", "aylık", "yıllara göre", "çeyrekler halinde". Dönem filtresi gibi okunmamalı |
| T03 kayan pencere (son N / önümüzdeki N) | 48 | 37 | "son üç ay", "son on iki ay", "önümüzdeki altı ay"; Türkçe sayı sözcükleri |
| T08 olaya göreli pencere / kayıt zamanı | 46 | 39 | Etkinlik, kampanya ya da zam öncesi/sonrası; "ilk yıl" (kitabın); kayıt zamanı (geriye dönük, mesai dışı). Takvim dönemi değil, olay tarihi gerekir |
| T02 karşılaştırma tabanı | 29 | 13 | "geçen yıla göre", "geçen yılın aynı dönemine göre": iki ayrı dönem üretir |
| T11 belirsiz / şimdi | 22 | 12 | "bu ara", "bu dönem", "şu an", "güncel": anlık durum ya da netleştirme |
| T12 dönem sonu / anlık durum tarihi | 22 | 12 | "ay sonu itibarıyla", "yıl sonu", "dönem sonu": tek `as_of` tarihi |
| T10 süre eşiği / yaşlandırma kovası | 16 | 15 | "otuz günden fazla", "doksan günü aşmış", "30/60/90": dönem değil, eşik |
| T04 yılsız ay adı | 13 | 11 | "Ağustos ayı", "eylül ayında", "temmuza göre", "aralık ayında … ocakta" |
| T06 yıl içi kısmi / bugüne kadar | 8 | 8 | "ilk sekiz ay", "yılbaşından bugüne", "şu ana kadarki", "geçen yıl aynı tarihte" |
| T05 mutlak yıl | 6 | 6 | "2026", "2024 ile 2025", "2021'den bugüne", "2025 kapanış / 2026 açılış" |
| T09 takvim/dış olay | 6 | 6 | Ramazan, pandemi sonrası, fuar dönemi, okul açılışı, yaz ayları: dış takvim ya da netleştirme |

## Bilinen hatalı kalıplar: setlerde var mı?

| Kalıp | Setlerde | Örnek soru | Beklenen çözüm (bugün 2026-10-01, yarı açık aralık) |
|---|---|---|---|
| "1-15 Mart" (gün aralığı + yılsız ay) | **yok** → sentetik test eklenmeli | — | `[2026-03-01, 2026-03-16)` |
| "Ocak-Mart" (ay aralığı) | **yok** → eklenmeli | — | `[2026-01-01, 2026-04-01)` |
| "2025'in ilk 3 ayı" | **yok**; benzeri var: "bu yılın ilk sekiz ayı", "geçen yılın ilk sekiz ayını" | K0252 | `[2025-01-01, 2025-04-01)`; K0252: `[2026-01-01, 2026-09-01)` ve `[2025-01-01, 2025-09-01)` |
| "ilk yarısı" | **yok** → eklenmeli | — | Yılın ilk yarısı `[2026-01-01, 2026-07-01)`; yıl bağlamı yoksa bu yıl |
| "aynı aralık" | **yok**; benzerleri var: "aynı dönemde", "aynı çeyrekte", "aynı ay içinde", "geçen yılın aynı dönemine göre" | C040, K0026, K0308, K0692, K0002, K0668 | Önceki dönem ifadesine bağlı ikinci aralık; K0002: `[2026-01-01, 2026-10-01)` ve `[2025-01-01, 2025-10-01)` |
| "geçen sene" | **var** | K0367 | `[2025-01-01, 2026-01-01)`. Karne 09-18: SQL 2026 kullanmış (YANLIŞ) |
| Yılsız ay adı | **var** (11 farklı ifade, 13 geçiş) | K0007, K0145, K0158, K0177, K0188, K0342, K0923, K0928, K0254, K0028, K0256 | İçinde bulunulan yıl. Ay bugünden sonra başlıyorsa önceki yıl (öneri; karar gerekli) |

Aşağıdaki ek kalıplar setlerde geçiyor ve test listesine girmeli:

- **Yıl geçişi**: "Aralık ayında kesilip **ocakta** irsaliyesi çıkan" (K0342). Ocak, aralığı izleyen yılın ocağıdır.
- **Ay sonu as-of**: "Ağustos sonu itibarıyla" (K0177) tek tarihe çözülür: `2026-08-31` sonu, yani `as_of=2026-09-01`.
  "Ay sonuna iki gün kala" (K0918) ayın son iki günüdür.
- **Hafta**: "bu hafta", "geçen haftaki / bir önceki haftaya göre" (K0054, K0205). Hafta pazartesi başlar. 2026-10-01
  perşembeye denk gelir; bu hafta `[2026-09-28, 2026-10-05)`, geçen hafta `[2026-09-21, 2026-09-28)`.
- **Çeyrek**:
  - "bu çeyrek" (bugün 4. çeyreğin ilk günü): `[2026-10-01, 2027-01-01)`
  - "geçen çeyrek": `[2026-07-01, 2026-10-01)`
  - "son çeyrek" (A004): son tamamlanmış çeyrek mi son üç ay mı → netleştirme
  - "dördüncü çeyrek" (K0452): yılın 4. çeyreği
- **Kayan pencere**:
  - "son on iki ay" (K0004): `[2025-10-01, 2026-10-01)`
  - "son üç yılın aralık ayları" (K0028): 2023, 2024 ve 2025 aralıkları; bu yılın aralığı henüz gelmedi
- **Mutlak + bugüne**: "2021'den bugüne" (K0006): `[2021-01-01, 2026-10-02)`. Yıl kopyaları kolon adıyla birleşir.
- **Durum tarihi**: "2025 kapanış / 2026 açılış" (K0344) iki as-of tarihidir. Dönem toplamı değildir.
- **Belirsiz**:
  - "bu ara" (A002): netleştirme (karar 10)
  - "bu dönem" (K0438, K0614): eğitim dönemi mi takvim yılı mı → netleştirme
  - "pandemi sonrası" (K0251), "Ramazan ayı" (K0253): dış takvim gerekir → netleştirme ya da dış veri

## 2026-09-18 karnesinde dönemden düşen sorular

`tests/text2sql/set1000-karne-0918.jsonl`'da **29 soru** "Dönem doğrulanamadı / karşılaştırma dönemleri ayrı ölçü
sütunlarında doğrulanamadı" gerekçesiyle RET aldı. Bu sorulardaki ham ifadeler aşağıda. Çoğu en basit iki kalıp:
"bu yıl" ve "geçen yıl(a göre)".

| Soru | Ham dönem ifadesi |
|---|---|
| K0002 | Geçen yılın aynı dönemine göre |
| K0006 | 2021'den bugüne · yıl yıl |
| K0011 | geçen yıla göre |
| K0020 | Geçen yıl · bu yıl |
| K0026 | Geçen çeyrekteki · aynı çeyrekte |
| K0028 | Yıl sonuna doğru · son üç yılın aralık aylarını |
| K0063, K0107, K0940 | bu yıl / Bu yıl |
| K0104 | Bu yılki · geçen yılla |
| K0123 | geçen yıla göre |
| K0216 | geçen yıl · bu yıl |
| K0251 | Pandemi sonrası yıllarda |
| K0337 | bu yılki |
| K0398 | bu ayki |
| K0449 | Geçen yılın · bu yılın |
| K0462 | Bu yıl · geçen yıla göre |
| K0508, K0960 | yıllara göre (kırılım; dönem sanılmamalı) |
| K0516 | son iki yılda |
| K0687 | Bu çeyrekte · geçen çeyreğe göre |
| K0789 | Fuar dönemlerindeki |
| K0230, K0232, K0285, K0288, K0304, K0606, K0805 | (dönem yok → "varsayılan dönem" doğrulanamadı) |

Aynı karnede dönem sözcükleri "katalogda tanımsız iş terimi" sanılarak da RET verildi. Bunlar ayrıştırıcının dönem
ifadesi olarak tüketmesi gereken parçalardır:

| Soru | Terim sanılan parça |
|---|---|
| K0006 | `den` ("2021'den") |
| K0053 | `itibariyla` ("aylar itibarıyla") |
| K0255 | `acilis` ("okul açılış dönemi") |
| K0344 | `acilis` ("2026 açılış") |
| K0294 | `sonunda, ay, ayda` ("ay sonunda … bir ayda … sonraki ayda") |

## Bütün ifadeler (sıklık sırasıyla, türe göre)

Örnek sütununda ifadenin geçtiği ilk 6 soru kimliği var.

| Tür | Ham ifade (küçük harf) | Geçiş | Örnek sorular |
|---|---|---:|---|
| T01 göreli takvim birimi | bu yıl | 98 | D039, A006, A030, A055, A023, A046 |
| T01 göreli takvim birimi | bu ay | 47 | K0019, K0051, K0072, K0079, K0093, K0139 |
| T01 göreli takvim birimi | bu yılki | 27 | A010, A053, K0013, K0015, K0077, K0096 |
| T01 göreli takvim birimi | bu hafta | 9 | K0205, K0283, K0332, K0391, K0561, K0659 |
| T01 göreli takvim birimi | geçen ay | 9 | C011, A051, K0075, K0150, K0167, K0374 |
| T01 göreli takvim birimi | bugün | 7 | K0137, K0202, K0331, K0390, K0877, K0922 |
| T01 göreli takvim birimi | bugünkü | 6 | K0050, K0078, K0132, K0321, K0327, K0997 |
| T01 göreli takvim birimi | geçen yıl | 6 | D039, K0020, K0042, K0216, K0442, K0707 |
| T01 göreli takvim birimi | bu çeyrekte | 4 | K0018, K0059, K0418, K0687 |
| T01 göreli takvim birimi | dün | 4 | K0138, K0204, K0861, K0920 |
| T01 göreli takvim birimi | bu ayki | 3 | K0263, K0398, K0643 |
| T01 göreli takvim birimi | bu ayın | 3 | K0155, K0157, K0364 |
| T01 göreli takvim birimi | bu yılın | 2 | K0001, K0449 |
| T01 göreli takvim birimi | geçen yılın | 2 | K0206, K0449 |
| T01 göreli takvim birimi | bu yıl içinde | 1 | A019 |
| T01 göreli takvim birimi | bu çeyrek | 1 | K0210 |
| T01 göreli takvim birimi | bugün itibarıyla | 1 | K0035 |
| T01 göreli takvim birimi | dördüncü çeyrek | 1 | K0452 |
| T01 göreli takvim birimi | geçen ayki | 1 | K0985 |
| T01 göreli takvim birimi | geçen ayın | 1 | K0019 |
| T01 göreli takvim birimi | geçen haftadan | 1 | K0205 |
| T01 göreli takvim birimi | geçen haftaki | 1 | K0054 |
| T01 göreli takvim birimi | geçen sene | 1 | K0367 |
| T01 göreli takvim birimi | geçen yılki | 1 | K0774 |
| T01 göreli takvim birimi | geçen çeyrekte | 1 | C038 |
| T01 göreli takvim birimi | geçen çeyrekteki | 1 | K0026 |
| T01 göreli takvim birimi | geçen çeyrekten | 1 | K0210 |
| T01 göreli takvim birimi | günün | 1 | K0202 |
| T01 göreli takvim birimi | yılı | 1 | K0206 |
| T02 karşılaştırma tabanı | geçen yıla göre | 10 | A032, A060, K0011, K0098, K0111, K0123 |
| T02 karşılaştırma tabanı | geçen aya göre | 3 | A029, K0115, K0229 |
| T02 karşılaştırma tabanı | aynı ay içinde | 2 | K0308, K0692 |
| T02 karşılaştırma tabanı | aynı gün | 2 | K0325, K0417 |
| T02 karşılaştırma tabanı | geçen yılla | 2 | K0013, K0104 |
| T02 karşılaştırma tabanı | geçen yılın aynı dönemine göre | 2 | K0002, K0668 |
| T02 karşılaştırma tabanı | geçen çeyreğe göre | 2 | K0418, K0687 |
| T02 karşılaştırma tabanı | aynı dönemde | 1 | C040 |
| T02 karşılaştırma tabanı | aynı çeyrekte | 1 | K0026 |
| T02 karşılaştırma tabanı | bir önceki haftaya göre | 1 | K0054 |
| T02 karşılaştırma tabanı | geçen yılın aynı aylarını | 1 | K0310 |
| T02 karşılaştırma tabanı | geçen yılın aynı ayına göre | 1 | K0392 |
| T02 karşılaştırma tabanı | geçen yılın aynı gününe göre | 1 | K0084 |
| T03 kayan pencere (son N / önümüzdeki N) | son üç yılda | 5 | K0056, K0663, K0961, K0973, K0978 |
| T03 kayan pencere (son N / önümüzdeki N) | son iki yılda | 3 | B057, K0516, K0953 |
| T03 kayan pencere (son N / önümüzdeki N) | önümüzdeki ay | 3 | K0245, K0527, K0999 |
| T03 kayan pencere (son N / önümüzdeki N) | önümüzdeki üç ayda | 3 | K0061, K0494, K0993 |
| T03 kayan pencere (son N / önümüzdeki N) | son üç ayda | 2 | C040, K0208 |
| T03 kayan pencere (son N / önümüzdeki N) | altı ay içinde | 1 | K0767 |
| T03 kayan pencere (son N / önümüzdeki N) | altı aydır | 1 | K0427 |
| T03 kayan pencere (son N / önümüzdeki N) | beş yıl önce | 1 | K0956 |
| T03 kayan pencere (son N / önümüzdeki N) | beş yıl üst üste | 1 | K0237 |
| T03 kayan pencere (son N / önümüzdeki N) | beş yıldır | 1 | K0211 |
| T03 kayan pencere (son N / önümüzdeki N) | bir ayda | 1 | K0294 |
| T03 kayan pencere (son N / önümüzdeki N) | bir yıldır | 1 | K0127 |
| T03 kayan pencere (son N / önümüzdeki N) | gelecek aylara | 1 | K0340 |
| T03 kayan pencere (son N / önümüzdeki N) | son altı ay | 1 | K0741 |
| T03 kayan pencere (son N / önümüzdeki N) | son altı ayda | 1 | K0827 |
| T03 kayan pencere (son N / önümüzdeki N) | son altı aydır | 1 | K0044 |
| T03 kayan pencere (son N / önümüzdeki N) | son altı ayın | 1 | K0161 |
| T03 kayan pencere (son N / önümüzdeki N) | son bir ayda | 1 | K0820 |
| T03 kayan pencere (son N / önümüzdeki N) | son bir haftada | 1 | K0635 |
| T03 kayan pencere (son N / önümüzdeki N) | son bir yılda | 1 | B061 |
| T03 kayan pencere (son N / önümüzdeki N) | son bir yıldır | 1 | K0423 |
| T03 kayan pencere (son N / önümüzdeki N) | son on iki ayda | 1 | K0664 |
| T03 kayan pencere (son N / önümüzdeki N) | son on iki aylık | 1 | K0807 |
| T03 kayan pencere (son N / önümüzdeki N) | son on iki ayın | 1 | K0004 |
| T03 kayan pencere (son N / önümüzdeki N) | son otuz günde | 1 | K0602 |
| T03 kayan pencere (son N / önümüzdeki N) | son çeyrekte | 1 | A004 |
| T03 kayan pencere (son N / önümüzdeki N) | son üç yıldır | 1 | K0486 |
| T03 kayan pencere (son N / önümüzdeki N) | son üç yıllık | 1 | K0474 |
| T03 kayan pencere (son N / önümüzdeki N) | son üç yılı | 1 | K0257 |
| T03 kayan pencere (son N / önümüzdeki N) | son üç yılın | 1 | K0963 |
| T03 kayan pencere (son N / önümüzdeki N) | önümüzdeki altmış gün için | 1 | K0082 |
| T03 kayan pencere (son N / önümüzdeki N) | önümüzdeki altı ayda | 1 | K0454 |
| T03 kayan pencere (son N / önümüzdeki N) | önümüzdeki otuz gün içinde | 1 | K0045 |
| T03 kayan pencere (son N / önümüzdeki N) | önümüzdeki yıl | 1 | K0968 |
| T03 kayan pencere (son N / önümüzdeki N) | önümüzdeki çeyrekte | 1 | K0994 |
| T03 kayan pencere (son N / önümüzdeki N) | önümüzdeki üç ayın | 1 | K0671 |
| T03 kayan pencere (son N / önümüzdeki N) | üç yıldır | 1 | K0223 |
| T04 yılsız ay adı | ağustos ayı | 2 | K0007, K0923 |
| T04 yılsız ay adı | eylül ayında | 2 | K0145, K0928 |
| T04 yılsız ay adı | aralık ayında | 1 | K0342 |
| T04 yılsız ay adı | ağustos | 1 | K0188 |
| T04 yılsız ay adı | ağustos için | 1 | K0158 |
| T04 yılsız ay adı | ağustos sonu itibarıyla | 1 | K0177 |
| T04 yılsız ay adı | kasım aylarına | 1 | K0254 |
| T04 yılsız ay adı | ocakta | 1 | K0342 |
| T04 yılsız ay adı | son üç yılın aralık aylarını | 1 | K0028 |
| T04 yılsız ay adı | son üç yılın haziran temmuz ağustosuna | 1 | K0256 |
| T04 yılsız ay adı | temmuza göre | 1 | K0007 |
| T05 mutlak yıl | 2021'den bugüne | 1 | K0006 |
| T05 mutlak yıl | 2024 ile 2025'i | 1 | K0250 |
| T05 mutlak yıl | 2025 ile 2026'da | 1 | K0024 |
| T05 mutlak yıl | 2025 kapanış | 1 | K0344 |
| T05 mutlak yıl | 2026 | 1 | K0003 |
| T05 mutlak yıl | 2026 açılış | 1 | K0344 |
| T06 yıl içi kısmi / bugüne kadar | bu yıl aynı tarihte | 1 | K0707 |
| T06 yıl içi kısmi / bugüne kadar | bu yılın ilk sekiz ayı | 1 | K0252 |
| T06 yıl içi kısmi / bugüne kadar | geçen yıl aynı tarihte | 1 | K0238 |
| T06 yıl içi kısmi / bugüne kadar | geçen yılın bu gününe kadar | 1 | K0383 |
| T06 yıl içi kısmi / bugüne kadar | geçen yılın ilk sekiz ayını | 1 | K0252 |
| T06 yıl içi kısmi / bugüne kadar | kalan aylarda | 1 | K0705 |
| T06 yıl içi kısmi / bugüne kadar | yılbaşından bugüne | 1 | K0009 |
| T06 yıl içi kısmi / bugüne kadar | şu ana kadarki | 1 | K0206 |
| T07 tanecik / kırılım ifadesi | aylık | 16 | K0073, K0086, K0102, K0105, K0182, K0312 |
| T07 tanecik / kırılım ifadesi | ay ay | 7 | C038, K0003, K0061, K0117, K0310, K0535 |
| T07 tanecik / kırılım ifadesi | yıllara göre | 6 | K0239, K0508, K0666, K0772, K0960, K0967 |
| T07 tanecik / kırılım ifadesi | aylara göre | 5 | K0022, K0136, K0299, K0548, K0669 |
| T07 tanecik / kırılım ifadesi | haftalık | 4 | K0018, K0082, K0404, K0436 |
| T07 tanecik / kırılım ifadesi | yıllar içinde | 4 | K0220, K0667, K0793, K0957 |
| T07 tanecik / kırılım ifadesi | her yıl | 3 | K0223, K0237, K0970 |
| T07 tanecik / kırılım ifadesi | yıllık | 3 | K0110, K0222, K0448 |
| T07 tanecik / kırılım ifadesi | aylar itibarıyla | 2 | K0053, K0109 |
| T07 tanecik / kırılım ifadesi | aylara | 1 | B073 |
| T07 tanecik / kırılım ifadesi | hangi aylarda | 1 | K0670 |
| T07 tanecik / kırılım ifadesi | yıl yıl | 1 | K0006 |
| T07 tanecik / kırılım ifadesi | yıllar itibarıyla | 1 | K0129 |
| T07 tanecik / kırılım ifadesi | yıllık hedefin | 1 | B073 |
| T07 tanecik / kırılım ifadesi | çeyrekler halinde | 1 | K0004 |
| T07 tanecik / kırılım ifadesi | çeyrekler itibarıyla | 1 | K0122 |
| T07 tanecik / kırılım ifadesi | çeyrekten çeyreğe | 1 | K0032 |
| T08 olaya göreli pencere / kayıt zamanı | ilk yıl | 4 | A098, K0756, K0779, K0783 |
| T08 olaya göreli pencere / kayıt zamanı | sonradan | 3 | K0176, K0916, K0917 |
| T08 olaya göreli pencere / kayıt zamanı | sonrasında | 3 | K0794, K0798, K0824 |
| T08 olaya göreli pencere / kayıt zamanı | altı ayda | 1 | K0731 |
| T08 olaya göreli pencere / kayıt zamanı | ertesi ay | 1 | K0909 |
| T08 olaya göreli pencere / kayıt zamanı | etkinlik sonrası | 1 | A072 |
| T08 olaya göreli pencere / kayıt zamanı | etkinlik sonrasında | 1 | B094 |
| T08 olaya göreli pencere / kayıt zamanı | geriye dönük tarihle | 1 | K0348 |
| T08 olaya göreli pencere / kayıt zamanı | geçmiş aya | 1 | K0172 |
| T08 olaya göreli pencere / kayıt zamanı | hafta sonu tarihine | 1 | K0173 |
| T08 olaya göreli pencere / kayıt zamanı | ilk kez | 1 | K0215 |
| T08 olaya göreli pencere / kayıt zamanı | ilk üç aylık | 1 | K0775 |
| T08 olaya göreli pencere / kayıt zamanı | imza günü yapılan haftalarda | 1 | K0788 |
| T08 olaya göreli pencere / kayıt zamanı | kampanya bittikten sonra | 1 | K0831 |
| T08 olaya göreli pencere / kayıt zamanı | kampanya bittikten sonraki ay | 1 | K0792 |
| T08 olaya göreli pencere / kayıt zamanı | kampanya dönemindeki | 1 | K0790 |
| T08 olaya göreli pencere / kayıt zamanı | kampanya dönemlerinde | 1 | K0544 |
| T08 olaya göreli pencere / kayıt zamanı | kampanya öncesine göre | 1 | K0790 |
| T08 olaya göreli pencere / kayıt zamanı | kapanış tarihinden sonra | 1 | K0172 |
| T08 olaya göreli pencere / kayıt zamanı | kayıt tarihinden sonra | 1 | K0349 |
| T08 olaya göreli pencere / kayıt zamanı | kaç gün sonra | 1 | K0815 |
| T08 olaya göreli pencere / kayıt zamanı | mesai saatleri dışında | 1 | K0347 |
| T08 olaya göreli pencere / kayıt zamanı | o günkü | 1 | K0736 |
| T08 olaya göreli pencere / kayıt zamanı | reklam sonrası üç aylık | 1 | K0786 |
| T08 olaya göreli pencere / kayıt zamanı | son fiyat güncellemesinde | 1 | K0572 |
| T08 olaya göreli pencere / kayıt zamanı | son girilen | 1 | K0924 |
| T08 olaya göreli pencere / kayıt zamanı | son zamdan sonra | 1 | K0802 |
| T08 olaya göreli pencere / kayıt zamanı | son üç baskısında | 1 | C026 |
| T08 olaya göreli pencere / kayıt zamanı | sonraki ay | 1 | K0918 |
| T08 olaya göreli pencere / kayıt zamanı | sonraki ayda | 1 | K0294 |
| T08 olaya göreli pencere / kayıt zamanı | sonraki aylarda | 1 | K0755 |
| T08 olaya göreli pencere / kayıt zamanı | sosyal medya reklamı verilen aylarda | 1 | K0797 |
| T08 olaya göreli pencere / kayıt zamanı | zam yaptıktan sonra | 1 | K0382 |
| T08 olaya göreli pencere / kayıt zamanı | zamanında | 1 | K0396 |
| T08 olaya göreli pencere / kayıt zamanı | zamdan sonra | 1 | K0835 |
| T08 olaya göreli pencere / kayıt zamanı | çıkışından bu yana | 1 | K0778 |
| T08 olaya göreli pencere / kayıt zamanı | önceki aylara | 1 | K0886 |
| T08 olaya göreli pencere / kayıt zamanı | önceki yılların | 1 | K0059 |
| T08 olaya göreli pencere / kayıt zamanı | üç ayda | 1 | K0777 |
| T09 takvim/dış olay | fuar dönemlerindeki | 1 | K0789 |
| T09 takvim/dış olay | kitap fuarı dönemlerinde | 1 | K0254 |
| T09 takvim/dış olay | okul açılış dönemi olan eylülde | 1 | K0255 |
| T09 takvim/dış olay | pandemi sonrası yıllarda | 1 | K0251 |
| T09 takvim/dış olay | ramazan ayı | 1 | K0253 |
| T09 takvim/dış olay | yaz aylarında | 1 | K0256 |
| T10 süre eşiği / yaşlandırma kovası | otuz günden fazla | 2 | K0600, K0878 |
| T10 süre eşiği / yaşlandırma kovası | bir haftadan uzun süredir | 1 | K0585 |
| T10 süre eşiği / yaşlandırma kovası | bir yılı aşmış | 1 | K0341 |
| T10 süre eşiği / yaşlandırma kovası | doksan günü aşmış | 1 | K0037 |
| T10 süre eşiği / yaşlandırma kovası | iki aylık | 1 | K0732 |
| T10 süre eşiği / yaşlandırma kovası | iki yıldan fazla | 1 | K0261 |
| T10 süre eşiği / yaşlandırma kovası | iki yıllık | 1 | K0738 |
| T10 süre eşiği / yaşlandırma kovası | otuz günden fazladır | 1 | K0608 |
| T10 süre eşiği / yaşlandırma kovası | otuz günden uzun süredir | 1 | K0284 |
| T10 süre eşiği / yaşlandırma kovası | otuz günlük dilimlerle | 1 | K0094 |
| T10 süre eşiği / yaşlandırma kovası | otuz, altmış, doksan gün | 1 | B007 |
| T10 süre eşiği / yaşlandırma kovası | yedi günden fazla | 1 | K0149 |
| T10 süre eşiği / yaşlandırma kovası | yedi günü geçtiği halde | 1 | K0291 |
| T10 süre eşiği / yaşlandırma kovası | yüz seksen günden eski | 1 | K0039 |
| T10 süre eşiği / yaşlandırma kovası | yüz yirmi günü aşan | 1 | K0385 |
| T11 belirsiz / şimdi | bu dönem | 4 | K0438, K0471, K0614, K0867 |
| T11 belirsiz / şimdi | şu an | 4 | K0372, K0487, K0605, K0660 |
| T11 belirsiz / şimdi | en son ne zaman | 2 | K0375, K0592 |
| T11 belirsiz / şimdi | güncel | 2 | K0070, K0826 |
| T11 belirsiz / şimdi | ne zaman | 2 | K0766, K0770 |
| T11 belirsiz / şimdi | şimdi | 2 | K0383, K0956 |
| T11 belirsiz / şimdi | anlık | 1 | K0407 |
| T11 belirsiz / şimdi | bu ara | 1 | A002 |
| T11 belirsiz / şimdi | en uzun süredir | 1 | K0395 |
| T11 belirsiz / şimdi | hâlâ | 1 | K0973 |
| T11 belirsiz / şimdi | sırada | 1 | K0655 |
| T11 belirsiz / şimdi | şu an itibarıyla | 1 | K0001 |
| T12 dönem sonu / anlık durum tarihi | yıl sonu | 4 | K0674, K0705, K0905, K0997 |
| T12 dönem sonu / anlık durum tarihi | ay sonu | 3 | K0179, K0907, K0934 |
| T12 dönem sonu / anlık durum tarihi | ay sonunda | 3 | K0189, K0294, K0909 |
| T12 dönem sonu / anlık durum tarihi | dönem sonu | 3 | K0280, K0339, K0343 |
| T12 dönem sonu / anlık durum tarihi | ay sonu itibarıyla | 2 | K0340, K0879 |
| T12 dönem sonu / anlık durum tarihi | ay sonuna iki gün kala | 1 | K0918 |
| T12 dönem sonu / anlık durum tarihi | bu ay sonunda | 1 | K0083 |
| T12 dönem sonu / anlık durum tarihi | dönem sonunda | 1 | K0906 |
| T12 dönem sonu / anlık durum tarihi | geçen ay sonuna göre | 1 | K0041 |
| T12 dönem sonu / anlık durum tarihi | geçen yıl sonu | 1 | K0345 |
| T12 dönem sonu / anlık durum tarihi | yıl başındaki | 1 | K0132 |
| T12 dönem sonu / anlık durum tarihi | yıl sonuna doğru | 1 | K0028 |
