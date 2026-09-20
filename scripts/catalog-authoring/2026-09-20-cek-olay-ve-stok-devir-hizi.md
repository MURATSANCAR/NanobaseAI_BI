# İş kararları 2026-09-20 — K3 (karşılıksız/protesto çek) ve K12 (stok devir hızı)

Hiçbir şey yazılmadı: katalog, kural dosyası, sunucu kodu ve köprü olduğu gibi. Bütün ölçümler salt-okunur
(müşteri Logo DB: `connector_from_file`; katalog: store API okuma; çözücü/derleyici/kapı: süreç içinde, bellekte).

Dosyalar: `apply.py` (katalog yazım betiği, varsayılan kuru koşu) · `rules.patch` (-p0; Kural 12 + ölçü belgesi + caveat) ·
`patch.diff` (-p0; derleyici sıralama ölçüsü — K12'nin ön koşulu, aşağıda) · `dryrun.out`, `sim100.out`, `probe*.out` (kanıt).

## K3 — "bu yıl karşılıksız çıkan" = OLAY

**Karar.** "Karşılıksız çıkan", "protesto olan/edilen" dönem içinde o duruma DÜŞEN çeki sorar (çek hareketi `CSTRANS`),
güncel durumu (`CSCARD.CURRSTAT`) değil. Sıfat biçimleri ("karşılıksız çekler", "protestolu senetler") güncel durumda kalır.

**DB kanıtı (LG_411 = 2026; LG_211 = 2021–25).**
- `CSTRANS.STATUS` kodları `CURRSTAT` ile aynı: 11 karşılıksız, 5/7 protesto. 2026'da STATUS 11 hareketi: 6 satır / 6 çek,
  hepsi TRCODE 9 (işlem bordrosu, müşteri çeki), DOC 1, tarihleri 09.02–04.06.2026, **6.326.658 ₺**
  (476.658 + 350.000 + 1.000.000 + 3 × 1.500.000) — altın n=23 ile birebir. Altısının da güncel durumu 6 (iade edildi): CURRSTAT okuması bu yüzden 0 buluyor.
- Protesto olayı 2026'da yok. STATUS 7 × 83 ve STATUS 11 × 20 satır **devir**dir (TRCODE 0, tarih 01.01.2026): olay sayılmaz.
- Devir ayrımı: `DEVIR = 1 ⇔ TRCODE = 0` iki kopyada da istisnasız (411: 5.751 / 3.105; 211: aykırı 0). Kapı `TRCODE <> 0`'ı okuyamıyor,
  `DEVIR = (0)`'ı zorlayabiliyor → koşul böyle yazıldı. `CSTRANS.CANCELLED <> 0` satırı hiç yok (iki kopyada 0); koşul yine de taşınır.
- Çek / senet: karşılıksız olaylarının hepsi DOC 1 (çek); protesto olaylarının hepsi DOC 2 (senet) — 2021–24: 145 olay / 145 senet; karşılıksız 2021–25: 35 olay / 35 çek.
- Tekilleştirme: altı yılda aynı kayıt için birden çok 5/7/11 hareketi **0**. Yine de tutar çek başına bir kez sayılmalı: eleştirmen
  `CSTRANS ⨝ CSCARD` üzerinde `SUM(CSCARD.AMOUNT)`'ı FANOUT diye durduruyor (DISTINCT alt sorgulu biçimi de); `EXISTS` biçimi geçiyor ve 6 çek / 6.326.658 ₺ veriyor.

**Yazılacaklar (`apply.py`).**
1. Yeni DIMENSION_VALUE «karşılıksız çıkan çek» → `CSTRANS.STATUS IN (11)`, koşullar `CSTRANS.DEVIR = (0)`, `CSTRANS.CANCELLED = (0)`; eş anlamlı «karşılıksız çıkan».
2. Yeni DIMENSION_VALUE «protesto edilen» → `CSTRANS.STATUS IN (5, 7)`, aynı koşullar; eş anlamlılar «protesto», «protesto olan», «protesto edildi», «protesto edilen çek/senet».
3. Bu olay ifadeleri bugünkü güncel-durum kavramlarından çıkarılır (`update_concept`): `sem_1056b5aeebca` (karşılıksız çek, CURRSTAT 11) ←
   «karşılıksız çıkan», «karşılıksız çıkan çek»; `sem_89b066a42444` (protestolu, CURRSTAT 5/7) ← «protesto», «protesto olan», «protesto edilen», «protesto edildi».
   Kavramların kendisi, eşlemesi ve sıfat adları kalır. Yalın «protesto» da taşınır: çözücü «olan»ı düşürdüğü için soruda anahtar «protesto»dur (ölçüldü —
   taşınmadan önce slot CURRSTAT'ta kalıyor ve «veya» birleşimi bozuluyordu).
4. `rules.patch`: Kural 12'ye olay/güncel durum ayrımı, dönem = `CSTRANS.DATE_`, tutar çek başına bir kez (`EXISTS`); caveat'taki «bu yüzden boş döner» cümlesi düzeltilir.

**Bellekte doğrulama.** Q23 okuması: `CSTRANS.STATUS IN (11, 5, 7)` («veya» birleşimi çalışıyor) + `LG_CSCARD.DOC IN (1)` + THIS_YEAR.
`EXISTS` biçimli SQL kapıdan ve eleştirmenden geçiyor; dünkü CURRSTAT'lı SQL artık kapıda **reddediliyor**; `DEVIR = 0` eksikse kapı reddediyor.

**Risk.**
- Kapı dönemi zorlamıyor: soruda ölçü olmadığı için `temporal_binding` boş; tarihsiz ya da `DUEDATE` üzerinden tarihli SQL de geçiyor. Dönemin `CSTRANS.DATE_`
  olması yalnız Kural 12 metnine bağlı (2026'da iki okuma aynı 6 çeki veriyor — altı çekin vadesi de 2026 — ama genelde aynı değil). Kalıcı çözüm koddur: DIMENSION_VALUE'nun entity'si tarihliyse dönem ona bağlanmalı.
- «Protestolu X» / «karşılıksız çekler» güncel durumda kalıyor (bellekte doğrulandı). Yalın «protesto» artık olay okur («protesto durumu» ayrı kavram, etkilenmez).
- Kapı, cevabın karşılıksız/protesto ayrı ayrı koşullu toplamını `EXISTS` içinde farklı STATUS kümesiyle yazan alt sorguyu («exists+koşullu toplam» adayı) reddediyor; toplam tek değerle sorulduğu için Q23'ü etkilemez, ayrıştırma isteyen soruda model onarıma düşebilir.

## K12 — stok devir hızı ≠ CRM satış hızı

**Karar.** «devir hızı» → CRM `PRODUCTBASE.NEW_SATISHIZI` makine onayı geri çekilir; Logo'ya sertifikalı METRIC «stok devir hızı» yazılır.

**DB kanıtı.**
- Formül bileşenleri: pay = satış **adedi** (`STLINE.AMOUNT`, TRCODE 7/8/9; maliyet değil — ayrıca satış satırlarının ~%11–17'sinde `OUTCOST = 0`, maliyet tabanlı pay güvenilmez);
  payda = (açılış devri TRCODE 14 + güncel stok bakiyesi) / 2; `LINETYPE = 0`, `CANCELLED = 0`.
- Dünkü 0,696'nın nedeni **payda**: model `(stok + stok) / 2` yazdı — açılış devri yerine güncel stoku iki kez aldı (148.662 / 213.633 = 0,6959). Pay, kitaplar ve güncel stok referansla aynıydı.
- Önerilen tek ifadeli formül altın n=12 referansıyla (üç alt sorgu) **20/20 kitapta birebir**: İYİLİK TİMİ 148.662 / ((58.273 + 213.633)/2) = 1,0935; ŞİFAYI KAPTIK 1,4367; ANNE TERLİĞİ 1,6626.
- LG_411 STLINE'da devir satırları 28.088, hepsi 01.01.2026 ve IOCODE 1/2; 2026 dışı tarihli yalnız 2 satır var (TRCODE 13, 23.03.2027, 2 × 100.000 adet — üretimden giriş, veri hatası görünümünde; satışı etkilemez, o malzemenin stokunu şişirir).

**Yazılacaklar (`apply.py`).**
1. `vocabulary.withdraw`: `sl_vocabulary` 668b9422… («devir hızı», generated / otomatik-yoklama, APPROVED → PROPOSED); `sem_6e3242310e38` «satış temposu» kavramı ve diğer adları kalır.
2. Yeni METRIC «stok devir hızı» (STLINE): `SUM(CASE WHEN TRCODE IN (7,8,9) THEN AMOUNT ELSE 0 END) / NULLIF((SUM(CASE WHEN TRCODE = 14 THEN AMOUNT ELSE 0 END) + SUM(CASE WHEN IOCODE IN (1,2) THEN AMOUNT WHEN IOCODE IN (3,4) THEN -AMOUNT ELSE 0 END)) / 2.0, 0)`;
   `extra`: func RATIO, `state_measure: true` (varsayılan yıl eklenmez; güncel kopya tarihsiz okunur — kopya = yıl), koşullar `LINETYPE = (0)`, `CANCELLED = (0)`; eş anlamlılar «devir hızı», «stok devir oranı», «stok dönüş hızı».
3. `rules.patch`: ölçü belgesinde başlık + tek ifadeli yazım + «NEW_SATISHIZI satış hızıdır» notu.

**Bellekte doğrulama.** Q12 okuması: «stok devir hızı» CERTIFIED METRIC + «satan» (INFERRED, satış tutarı) + kitap; CRM kolonu ve ayrı «stok» slotu gidiyor. Deterministik derleyici SQL üretiyor, kapı ve eleştirmen boş.

**Risk — ÖNEMLİ, katalog tek başına Q12'yi düzeltmez.**
- Deterministik derleyici TOP-N'i **ilk ölçüye** göre sıralıyor (`compiler.py`: `metric_aliases[0]`). Kavram yazılınca Q12 `ORDER BY stok_devir_hizi DESC TOP 20` olur: en çok satan 20 kitap değil,
  devir hızı en yüksek 20 (CANAVARIM VE BEN 497,8; … ortalama stoku sıfıra yakın ürünler) — sertifikalı görünen yanlış cevap. `patch.diff` bunu genel olarak kapatır: birden çok ölçülü TOP-N'de sıralama ölçüsü
  soruda ÖNCE geçen ölçüdür (Türkçe sıralama yan cümlesi sayılan addan önce gelir). Bellekte: Q12 `ORDER BY satis_tutari DESC`; set100'de bugünkü katalogla deterministik SQL'i değişen soru **0**. Kavram bu yamadan ÖNCE yazılmamalı.
- Yamadan sonra da altınla tam tutmayabilir: «en çok satan» fiil kökünden satış **tutarı**na (LINENET) bağlanıyor, altın **adet**e göre sıralıyor — ilk 20'nin 13'ü ortak. Ayrıca derleyici kitabı `ITEMS.NAME` ile grupluyor
  (altın `CODE` anahtarıyla karşılaştırıyor; 2.852 ad birden çok kartta). «En çok satan kitap = adet mi tutar mı» ayrı bir iş kararıdır; devir hızı değerleri kitap bazında doğru çıkar.
- Geçmiş yıl: LG_211 tek kopyada 2021–25'i taşıyor, devir satırı yalnız kopya başında; «2024 stok devir hızı» bu formülle açılış = 0 okur. Ölçü belgesine «yalnız güncel kopya» yazıldı; geçmiş yıl sorusu için ayrı tanım gerekir.
- «satış hızı» PROPOSED kalıyor (bugün de çözülmüyor); «satış temposu/performansı», «tükenme hızı» CRM'de kalır.

## Risk ölçümü — set100 (çözücü süreç içinde, kavramlar yalnız bellekteki dizinde)

100 sorudan okuması değişen **2**: C021 (Q12) ve A010 (Q23) — ikisi de hedef. Elle eklenen 4 denetim sorusu: «Geçen yıl protesto olan senetler» CURRSTAT → CSTRANS (beklenen),
«Devir hızı en düşük kitaplar» CRM → Logo ölçüsü (beklenen); «Protestolu senetlerin toplam tutarı» ve «Ürünlerin satış hızı nedir?» değişmedi.
Katalogda yeni (mıknatıs) kelime yok. set1000 ölçülmedi.

## Uygulama sırası (ana oturum)
1. `patch -p0 < patch.diff` (derleyici) → kur → hızlı kapı.  2. `patch -p0 < rules.patch`.  3. `apply.py --apply` (README'deki systemd-run).  4. `resolver-gate.py` (yalnız Q12, Q23 değişmeli) → `answer-gate.py --only 12,23`.
