# Yönlendirme ölçüm seti (taslak 1)

Tarih: 2026-10-01. Veri: [`yonlendirme-seti.jsonl`](yonlendirme-seti.jsonl) (1.100 satır). Kavram kimlikleri:
[`kavram-sahipligi.json`](kavram-sahipligi.json). Dönem ifadeleri: [`donem-ifadeleri.md`](donem-ifadeleri.md).

## Kapsam ve yöntem

| Set | Dosya | Soru | Etiket düzeyi |
|---|---|---:|---|
| set100 | `tests/text2sql/set100.jsonl` | 100 | tam |
| set1000 K0001–K0300 | `tests/text2sql/set1000.jsonl` | 300 | tam |
| set1000 K0301–K1000 | `tests/text2sql/set1000.jsonl` | 700 | yol: yol + kavram + dönem + boşluk + belirsizlik notu |
| complex100 | repo'da yok | — | atlandı |

complex100'ün kopyası repoda yok. Aranan klasörler `docs`, `scripts` ve `tests`; yalnız sunucu yolu geçiyor
(`/data/nanobaseai/bi/acceptance/complex100-20260930/`). `tests/text2sql/timas-copilot-complex.json`'daki 10 soru
istenmediği için etiketlenmedi.

Etiketleri kural ve okumayla tek tek elle verdim; model ya da kod koşturulmadı. Setlerin kendi `kaynak` alanı
(logo/crm/ikisi) yalnız karşılaştırma için `set_kaynak_etiketi` alanında tutuldu. `beklenen_yol` benim kararımdır.
Kararları dayandırdığım kaynaklar:
- iş kuralları
- `CRM-LOGO-KOPYA.md` ölçümü (sipariş = CRM öncesi süreç, sevkiyat = Logo kopyası, hedef = adet)
- CRM sözlüğü (hangi tablo var, hangisi ölü)
- `chat_topics.json` ve `chat_portal_areas.json` (portal alanları)

### Alanlar (tam etiket)

| Alan | Ne tutar |
|---|---|
| `id`, `set`, `soru` | Kaynak setteki kimlik, set adı ve soru metni |
| `set_kaynak_etiketi`, `set_rol`, `set_konu` | Setin kendi etiketleri |
| `beklenen_yol` | `finans_disi` / `portal` / `logo` / `crm` / `karma` |
| `set_etiketinden_farkli` | `ikisi` = `karma` sayılarak setin kendi etiketiyle karşılaştırma |
| `konu_varligi` | Sorunun konu varlığı |
| `olculer`, `kirilimlar`, `suzgecler` | İstenen ölçüler, kırılımlar ve süzgeçler |
| `donem_ham` | Sorudaki dönem ifadesi, ham metin |
| `yasaklar` | Cevapta yapılmaması gereken birleştirme ya da varsayım |
| `belirsizlik` | `{var, netlestirme_gerekir, neden}` |
| `kavramlar` | Kavram sözlüğündeki kimlikler |
| `motor_karsiligi` | `var:<id>`, `kismi:<id>`, `yok` ya da `chat_portal:<alan>` |
| `bosluk_siniflari` | İlk eleman birincil sınıftır; sayımlar ona göre |

Yol düzeyindeki 700 satırda `olculer`, `kirilimlar`, `suzgecler` ve `yasaklar` boştur (`null`).

### Ölçümde kullanım

Yönlendirici her soru için bir yol üretir; `beklenen_yol` ile eşleşme oranı ölçülür. Tam etiketli 400 soruda kavram,
dönem ve ölçü eşleşmesi de karşılaştırılabilir. `belirsizlik.netlestirme_gerekir=true` olan sorularda doğru davranış
cevap değil, netleştirme sorusudur.

## Yol dağılımı

| Yol | set100 | set1000 | Toplam | Pay |
|---|---:|---:|---:|---:|
| logo | 37 | 433 | **470** | %42,7 |
| crm | 33 | 281 | **314** | %28,5 |
| karma | 30 | 274 | **304** | %27,6 |
| portal | 0 | 12 | **12** | %1,1 |
| finans_disi | 0 | 0 | **0** | %0 |

- **`finans_disi` sorusu yok.** Setler kimlik/model, şirket dışı sohbet ve genel kültür sorusu içermiyor, bu yüzden
  `chat_scope` reddi ölçülemiyor. Bu sınıftan soru eklenmeli.
- Soruda geçen `BI_INTRO` metni kodda değişmiş. Görevde verilen metin: "Ben Zeki AI, size sadece finansal sorulara
  cevap verebilirim". `chat_scope.py`'deki bugünkü metin: "Ben Zeki AI; şirketinizin verileri ve modülleri hakkındaki
  sorulara cevap verebilirim" (2026-09-28 kararı, kapsam genişledi). Eklenecek finans dışı sorularda beklenen metin
  buna göre seçilmeli.
- **Portal** 12 soru:
  - K0581–K0587, K0661, K0669: destek/şikâyet → `musteri-destek`
  - K0535: sosyal medya reklamı → `reklam`
  - K0598: yönetim kurulu aksiyonu → `kurul`
  - K0519: matbaa teklifi → `uretim`

### Set etiketiyle karşılaştırma

| Set etiketi → beklenen yol | Soru |
|---|---:|
| logo → logo | 436 |
| logo → crm | 11 |
| logo → karma | 10 |
| crm → crm | 302 |
| crm → karma | 24 |
| crm → portal | 12 |
| crm → logo | 10 |
| ikisi → karma | 270 |
| ikisi → logo | 24 |
| ikisi → crm | 1 |

**92 soruda** benim etiketim setinkinden farklı. Nedenler, grup grup:

1. **Sipariş CRM'e geçti** (logo → crm/karma, 14 soru): C004, C038, D037, D039, A030, A031, K0281–K0288. Ölçüm,
   B2B siparişin Logo'da kopyası olmadığını gösterdi.
2. **Logo'dan CRM sınıflaması isteyenler karma** (logo → karma, 7 soru): K0203, K0231, K0232, K0235, K0236, K0241,
   K0953. Bunlar hedef, yeni çıkan kitap, tür ve set ürün soruları.
3. **CRM etiketli ama Logo verisi de gereken sorular karma** (crm → karma, 24 soru):
   - hakediş ve avans (11): B060, K0459, K0471–K0475, K0478, K0479, K0651, K0948. CRM'de hakediş kaydı yok; tutar
     Logo satışından hesaplanır, ödeme Logo'dadır.
   - gerçekleşen gideri Logo'da olanlar (8): etkinlik, reklam, kargo, fuar (B064, K0524, K0528, K0534, K0546–K0548,
     K0653)
   - diğer (5): K0427, K0504, K0540, K0634, K0662
4. **Gerçekleşen maliyet ve gider Logo** (ikisi/crm → logo, 34 soru). Örnekler:
   - baskı maliyeti: B061, K0502–K0505, K0516
   - sorusunda CRM geçmeyen sepet ve tahsilat soruları: A016, K0565
   - stopaj ve bedelsiz çıkış: K0477, K0648
   - kargo ve telif gideri: K0804, K0709
   - irsaliye ve fiyat kartı: A022, A096, K0835
   - tek kaynaktan cevaplanan "ikisi"ler: A024, A071, K0730, K0746
5. **Destek, sosyal medya ve kurul portal** (crm → portal, 12 soru).
6. **İki CRM kaydının karşılaştırması** (ikisi → crm, 1 soru): K0912 (sipariş ve tahsilatı giren aynı temsilci).

## Motorun karşılayabildiği

- Boşluk sınıfı olmayan, portal dışı soru: **120 / 1.088** (%11). Bunların 109'u `var`, 11'i `kismi`.
- Yola göre:
  - logo: 93 / 470
  - crm: 22 / 314
  - karma: 5 / 304
- Karma sorudaki 5 tam karşılık: K0715, K0765, K0773 (yazar kırılımlı satış), K0850, K0853 (çapraz kalite raporları).
- Kısmi karşılıklar ve typed gap dönen modlar boşluk sayıldı. Örnekler: `aging`, `profit`, Logo e-ticaret akışını
  okuyan `open_orders`.

## Karma soruların ortak kalıpları (304 soru)

| Birincil boşluk | Soru | Kalıp | Köprü durumu |
|---|---:|---|---|
| B25 iki sistem mutabakatı | 110 | Aynı olayın CRM kaydı ile Logo kaydını karşılaştırma | Aşağıdaki alt tabloya bakın |
| B22 telif/hakediş | 27 | CRM telif oranı × Logo net satış adedi/tutarı; avans mahsubu | Kitap köprüsü var; yazar = hak sahibi varsayılamaz |
| B19 hedef-gerçekleşen | 20 | CRM adet hedefi × Logo faturalı adet | Kitap köprüsü var (`new_StokKodu`); BMT ↔ temsilci/kanal **yok**; TL hedef **yok** |
| B26 etki/ilişki | 18 | Etkinlik, kampanya, reklam, ziyaret ya da şikâyet öncesi/sonrası satış | Pencere tanımı yok; korelasyon nedensellik değildir |
| B24 CRM sınıflaması | 18 | Tür, yayın tarihi, editör, dizi ve uyruğa göre Logo satışı | Kitap köprüsü var; motorda bu boyutlar yok |
| B16 CRM sipariş | 15 | CRM siparişi + Logo fatura/tahsilat/stok yan yana | Sevkiyat `logicalref` köprüsü var |
| B05 maliyet/kâr | 12 | Yazar/tür/dizi kırılımında kâr | Kâr tanımı doğrulanmadı |
| B18 ziyaret/etkinlik | 11 | Ziyaret × ciro, etkinlik ili × satış | Okul/kurum Account ↔ Logo cari: vergi no çoğu zaman yok |
| B04 vade/tahsil süresi | 11 | CRM kredi limiti/vade × Logo vadesi geçmiş borç | Müşteri köprüsü var; kapama doğrulanmadı |
| diğer | 62 | B20, B21, B10, B08, B31, B27, B23, B07, B29 vb. | — |

B25'in alt kalıpları (110 soru):

| Alt kalıp | Soru | Örnek | Köprü |
|---|---:|---|---|
| CRM sipariş/sevk ↔ Logo fatura/irsaliye | 35 | A021, B081, K0688 | `new_sevkiyat.new_logicalref` (var, yıl firması şart) |
| CRM plan/gider ↔ Logo muhasebe/fatura (etkinlik, reklam, kargo, bütçe, masraf) | 18 | B064, K0839, K0840 | **Yok** (reklam planı "Fatura Numarası" alanı aday) |
| Ana veri/kart tanımı eşleşmesi (müşteri, kitap, vergi no, adres, vade, temsilci) | 18 | K0634, K0753, K0764 | Vergi no / stok kodu (var); vergi no farkının kendisi ölçülemez |
| Telif/sözleşme ↔ Logo ödeme/cari | 16 | K0711, K0845, K0867 | **Yok** (yazar carisi ↔ CRM kişi) |
| CRM tahsilat ↔ Logo tahsilat/banka/çek | 11 | A049, K0811, K0863 | **Yok** (makbuz/slip no adayı, doğrulanmadı) |
| CRM baskı ↔ Logo üretim/matbaa faturası | 8 | K0733, K0888 | Kısmi (`new_logouretimfisi` = STFICHE.SPECODE) |
| diğer | 4 | K0808, K0865 | — |

## Mevcut motorun karşılayamadığı kavram sınıfları

"Birincil" sütununda her soru yalnız ilk boşluk sınıfıyla bir kez sayıldı (toplam 968). "Herhangi" sütunu, sınıfın
sorunun boşluk listesinde geçtiği soru sayısıdır.

| Sınıf | Ad | Birincil | Herhangi | Yol (birincil) | Örnek |
|---|---|---:|---:|---|---|
| B25 | iki sistem mutabakatı | 110 | 111 | logo 0 · crm 0 · karma 110 | B064, A021, A049, B081 |
| B01 | genel muhasebe ve vergi | 75 | 75 | logo 74 · crm 0 · karma 1 | A053, K0104, K0105, K0106 |
| B16 | CRM sipariş süreci ve bekleyen ürün | 75 | 77 | logo 0 · crm 60 · karma 15 | C004, C038, D037, A030 |
| B22 | telif, avans, hakediş, sözleşme parası/hakları | 64 | 64 | logo 0 · crm 37 · karma 27 | B055, D050, D053, A020 |
| B07 | baskı ve üretim | 54 | 54 | logo 26 · crm 23 · karma 5 | C010, C011, C026, C040 |
| B18 | CRM müşteri, ziyaret, etkinlik, temsilci faaliyeti | 53 | 53 | logo 0 · crm 42 · karma 11 | A044, A075, B090, K0420 |
| B04 | vade, yaşlandırma, tahsil süresi | 44 | 45 | logo 33 · crm 0 · karma 11 | A060, B007, B019, A008 |
| B05 | maliyet, kâr ve stok değeri | 41 | 45 | logo 29 · crm 0 · karma 12 | B029, B030, A071, B089 |
| B08 | kart ana verisi ve ticari koşul | 41 | 42 | logo 23 · crm 12 · karma 6 | B039, A026, A028, A056 |
| B29 | motorda olmayan küçük/ölü CRM varlığı | 39 | 39 | logo 0 · crm 35 · karma 4 | D069, A093, A094, A095 |
| B02 | banka, kasa ve nakit akışı | 35 | 36 | logo 34 · crm 0 · karma 1 | A029, K0070, K0071, K0072 |
| B23 | yayın kurulu, proje, yayın programı | 34 | 35 | logo 0 · crm 29 · karma 5 | A066, A067, A069, A098 |
| B19 | satış hedefi ve hedef-gerçekleşen | 31 | 31 | logo 0 · crm 11 · karma 20 | B073, B072, A023, B082 |
| B15 | belge düzeyi döküm ve kayıt izi | 29 | 29 | logo 27 · crm 2 · karma 0 | K0138, K0139, K0140, K0141 |
| B06 | tedarikçi borcu ve satınalma toplamları | 27 | 27 | logo 26 · crm 0 · karma 1 | K0087, K0088, K0089, K0090 |
| B20 | kampanya, reklam, numune | 25 | 25 | logo 0 · crm 17 · karma 8 | B066, A047, A073, K0530 |
| B03 | çek ve senet portföyü | 22 | 23 | logo 20 · crm 0 · karma 2 | A010, K0060, K0061, K0062 |
| B26 | etki/ilişki analizi | 21 | 21 | logo 2 · crm 1 · karma 18 | A072, B094, K0382, K0544 |
| B10 | uygulanan iskonto | 19 | 19 | logo 12 · crm 1 · karma 6 | A032, D015, B047, B085 |
| B09 | Logo belge akışı (irsaliye, ambar fişi) | 18 | 18 | logo 18 · crm 0 · karma 0 | A022, B086, K0149, K0263 |
| B13 | kohort, varlık-yokluk, pay sıralaması | 18 | 20 | logo 15 · crm 2 · karma 1 | D039, A006, A051, K0010 |
| B24 | CRM kitap sınıflaması ile Logo satışı | 18 | 21 | logo 0 · crm 0 · karma 18 | A100, K0231, K0232, K0235 |
| B21 | kargo | 16 | 16 | logo 0 · crm 10 · karma 6 | B074, A099, K0546, K0547 |
| B31 | mevcut ölçülerin birleşimi / eksik toplulaştırma | 16 | 18 | logo 11 · crm 0 · karma 5 | C021, K0026, K0042, K0099 |
| B11 | Logo satışında tanımsız kırılım | 15 | 17 | logo 15 · crm 0 · karma 0 | K0012, K0013, K0014, K0015 |
| B17 | CRM tahsilat kaydı | 10 | 10 | logo 0 · crm 10 · karma 0 | K0556, K0557, K0558, K0559 |
| B27 | tahmin ve senaryo | 6 | 10 | logo 1 · crm 0 · karma 5 | K0206, K0993, K0994, K0996 |
| B14 | döviz bakiyesi ve kur | 4 | 6 | logo 4 · crm 0 · karma 0 | K0050, K0133, K0136, K0339 |
| B12 | zaman şekli (hafta/çeyrek/rekor) | 3 | 5 | logo 3 · crm 0 · karma 0 | K0004, K0018, K0375 |
| B28 | dış veri | 3 | 3 | logo 3 · crm 0 · karma 0 | K0211, K0251, K0253 |
| B32 | geçmiş tarihli durum / dönemler arası devir | 2 | 4 | logo 1 · crm 0 · karma 1 | K0345, K0736 |

### Okuma

- **En büyük beş sınıf** 378 soru tutuyor, birincil boşlukların %39'u:
  - B25 mutabakat: 110
  - B01 muhasebe: 75
  - B16 CRM sipariş: 75
  - B22 telif: 64
  - B07 baskı/üretim: 54
- **Logo tarafının açığı** genel muhasebe (B01) ile banka/kasa/çek (B02+B03). Bunlara vade/kapama (B04),
  maliyet/stok değeri (B05) ve tedarikçi (B06) eklenince 216 Logo sorusu çıkıyor; motorda bu modüllerin hiçbiri yok.
- **CRM tarafının açığı** iki yerde toplanıyor:
  - sipariş süreci (B16, 60 soru)
  - CRM faaliyet ve sözleşme parası: B18, B22 ve B23 toplam 108 soru
  Motorun CRM raporları künye kalitesine (`book_quality`, `duplicate_*`) ve sözleşme tarihlerine odaklı.
- Bazı sınıflar küçük eklemelerle kapanabilir. Bunlar mevcut olgu tablosuna yeni boyut ya da ölçü eklemek demek:
  - B11: il, ülke, satış elemanı, fatura türü boyutları (15)
  - B12: hafta ve çeyrek boyutu (3)
  - B10: iskonto ölçüsü (19)
  - B24: tür, yayın tarihi, editör boyutu (18)
- Bazı sınıflar yeni köprü ister: B25'in 45 sorusu (tahsilat, telif ödemesi, plan/gider) ve B19'un kişi/kanal kırılımı.
  Köprü kurulmadan bu sorulara güvenilir cevap verilemez.

## Belirsizlik ve netleştirme

- 222 soruda belirsizlik notu var. Bekleyen iş kararlarına atıflar:

  | Karar | Konu | Soru |
  |---|---|---:|
  | 1 | termin | 7 |
  | 4 | kitap kapsamı | 4 |
  | 8 | fiyat listesi | 3 |
  | 6 | yıl kopyası | 2 |
  | 5 | etkinlik-yazar | 2 |
  | 3 | karşılıksız çek | 2 |
  | 11 | bekleyen sipariş tutarı | 2 |
  | 06/07 | tahsil süresi | 3 |
  | 2, 7, 9, 10 | sepet, bedelsiz satır, yurtdışı hak, "bu ara" | 1'er |

- `netlestirme_gerekir=true` olan sorular. Bu sorularda beklenen cevap netleştirme sorusudur:
  - A002: "bu ara"
  - C026: hangi kitap
  - B050: "yolda" hangi statü
  - K0151: D&R kartı
  - K0242: batma riski ölçütü
  - K0365: Kitapyurdu kartı
  - K0985: hangi imza günü
  - K0990: hangi kampanya
- **Dönem söylemeyen soru 656** (%60). Bunların bir kısmı durum sorusudur (stok, bakiye, kart eksikleri), bir kısmı da
  dönem ister ("en çok satan", "iade oranı"). Varsayılan dönem kuralı (bu yıl / bugüne kadar / tüm aktif kayıt)
  yazılmalı ve cevapta söylenmeli.
- Pasif CRM kaydı ekranda gösterilmez kuralıyla çelişen sorular var: K0432, K0636, K0764. Beklenen davranış "pasif
  kayıt gösterilmez" demek ya da yalnız sayı vermek; karar gerekiyor.
