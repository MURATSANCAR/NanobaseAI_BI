# 2. adım — parti 1: aday kavramlar, çürütme ve risk ölçümü

Tarih: 2026-09-21 · İmza: `operator:claude (parti 1, 2026-09-21)` · **Kataloğa hiçbir şey yazılmadı.**
Betik: `apply.py` (varsayılan kuru koşu, `--apply` ile yazar, `--simulate` ile bellekte ölçer).
Kuru koşu çıktısı: `kuru-kosu.json`.

Kaynaklar: müşteri Logo veritabanı (salt okunur, `connector_from_file`; 2026 = `LG_411_*`,
2021–25 = `LG_211_*`), katalog `sl_schema_profile.columns_json[].description` (doğrulandı, kabul
edilmedi), katalog `certified_index` (çakışma denetimi), `set100.jsonl` (risk ölçümü).

## Özet

| Tablo | Üretilen aday | Onaya hazır | Elendi |
|---|---:|---:|---:|
| SHIPINFO (VW) | 6 | **3** | 3 |
| OCCUPATION | 5 | **1** | 4 |
| EMUHACC | 5 | **3** | 2 |
| POLINE | 4 | **2** | 2 |
| SRVCARD | 5 | **5** | 0 |
| FAREGIST | 7 | **6** | 1 |
| INVDEF | 4 | **0** | 4 |
| **Toplam** | **36** | **20** | **16** |

**set100 risk ölçümü: 100 soruda okuması değişen 0.** (`--narrow-sabit-kiymet` açıkken de 0.)
Pozitif kontrol olarak 14 elle soru ölçüldü, 11'inin okuması hedeflenen yönde değişti — yani
adaylar ölü değil, yalnız set100'ün kapsamadığı alanı dolduruyorlar.

---

## SHIPINFO — teslimat kartı

Entity seçimi: adaylar **görünüm** entity'sine (`SHIPINFO` / `VW_{n0}_SHIPINFO`) yazılıyor, taban
tabloya (`LG_SHIPINFO` / `LG_{n0}_SHIPINFO`) değil. Gerekçe: `sem_8361970a8cc5` «gönderim şehri»
zaten görünüm entity'sinde. Taban tabloya yazmak aynı veriyi iki entity'ye bölerdi
(«entity adı tarama kapsamına bağlı» hatası). Görünümde TOWN/COUNTRY/DISTRICT + hazır
`CARI_CODE`/`CARI_UNVAN` var; satır sayısı 370.467 (taban tablo 370.630).

**Onaya hazır**

| terim | tür | alan | DB kanıtı |
|---|---|---|---|
| teslimat kartı (+ teslimat adresi kartı, sevkiyat adresi kartı) | ENTITY | SHIPINFO | 370.630 kart, 238.287 cari; SHIPINFOREF dolu: fatura 69.577/81.801, irsaliye 72.517/101.695, sipariş 48.685/48.687 |
| teslimat ilçesi (+ teslimat ilçeleri) | COLUMN | SHIPINFO.TOWN | 365.752/370.630 dolu (%98,7) |
| teslimat ülkesi (+ teslimat ülkeleri) | COLUMN | SHIPINFO.COUNTRY | 370.416/370.630 dolu (%99,9) |

Bağ doğrulandı: `INVOICE.SHIPINFOREF = SHIPINFO.LOGICALREF` üstünden 2026 satış faturaları
(TRCODE 2,3,7,8,9, iptalsiz) şehre göre kırılıyor: İstanbul 22.680 fatura / 763.675.956 ₺,
Kocaeli 3.056 / 146.877.545 ₺, Ankara 6.182 / 127.193.903 ₺.

**Elenenler**

- **«teslimat şehri» → SHIPINFO.CITY** — *elendi (zaten var)*: `sem_8361970a8cc5` «gönderim şehri»
  aynı kolonu taşıyor, eş anlamlıları arasında `teslimat sehr` de var. Yeni kavram tam kopya olurdu.
- **«teslimat bilgisi / teslimat bilgileri»** — *elendi (çakışma)*: anahtar `teslimat bilk` bugün
  CRM'de `sem_1eefa73533f8` «ürün teslim bilgisi» (`ACCOUNTBASE.NEW_URUNTESLIMBILGISI`) üstünde.
  Aynı anahtarda iki sertifikalı kavram çözücüyü ikileme sokar → terim «teslimat kartı»na çekildi.
  Aynı gerekçeyle «gönderim ilçesi» (`sem_9b82ace134ba`) ve «gönderim ülkesi» (`sem_0e5a598a8503`)
  eş anlamlıları da verilmedi.
- **«aktif teslimat kartı» → ACTIVE** — *elendi (ayırt edici değil)*: 370.630 kartın 370.584'ü
  ACTIVE=0. Kırılım üretmez.

---

## OCCUPATION — üretimde kaynak kullanımı

**Onaya hazır**

| terim | tür | alan | DB kanıtı |
|---|---|---|---|
| üretimde kaynak kullanımı (+ kaynak kullanım kaydı, üretim kaynak kullanımı) | ENTITY | OCCUPATION | 32.937 kayıt, 1.221 üretim emri, 1.221 iş emri satırı, 21 çalışan (EMPREF); OCCTYPE hepsi 4 (işgücü), TOOLREF hepsi 0 |

**Elenenler — bu tablonun süre ölçüleri kırıldı**

- **«kaynak planlanan süresi» → SUM(DURATION) WHERE OCCSTATUS=1** — *elendi (çift sayma)*:
  toplam **8.848.628**; `DISPLINE.PLNDURATION` toplamı da **8.848.628** — birebir aynı sayı.
  DISPLINE tarafı zaten sertifikalı («operasyon planlanan süresi», `sem_1dd04aa3bcd0`). İki tablodan
  aynı sayı → birleşince 2× hata. («yıl birleştirme çift sayması» ile aynı sınıf.)
- **«kaynak gerçekleşen süresi» → SUM(DURATION) WHERE OCCSTATUS=2** — *elendi (birim
  doğrulanamadı)*: toplam 39.150.215, DISPLINE.ACTDURATION ise 8.874.702 (4,4×). DISPLINE için
  ilan edilmiş birim dakika; aynı birim burada 21 çalışan için yılda 27.000 saat/kişi verir —
  imkânsız. Birim (saniye mi, kaynak-dakikası mı) bir iş kararı olmadan formüle gömülemez.
- **«kaynak kullanım miktarı» → AMOUNT** — *elendi (bilgi yok)*: 15.233 satırın toplamı 15.233,0;
  her satırda 1. Ölçü değil, sayaç.
- **«planlanan» / «gerçekleşen» → OCCSTATUS DIMENSION_VALUE** — *elendi (tek kelime yasağı)*:
  tek kelimelik genel öbekler; h4 turunda aynı kelimeler Logo sorusunu CRM'e çekmişti.

---

## EMUHACC — muhasebe hesap planı

**Onaya hazır**

| terim | tür | alan | DB kanıtı |
|---|---|---|---|
| muhasebe hesabı (+ muhasebe hesapları, muhasebe hesap planı, genel muhasebe hesabı) | ENTITY | EMUHACC | 1.374 hesap, 3 seviye, 23'ü kullanım dışı; `EMFLINE.ACCOUNTREF` 246.404/246.404 dolu |
| muhasebe hesap kodu (+ muhasebe hesap kodları, genel muhasebe hesap kodu) | COLUMN | EMUHACC.CODE | 1.374/1.374 dolu; 1–9 ana grubunun hepsi var (7'li 337, 1'li 299 …) |
| muhasebe hesap adı (+ muhasebe hesap adları, muhasebe hesap açıklaması) | COLUMN | EMUHACC.DEFINITION_ | 1.374/1.374 dolu |

Bağ doğrulandı: `EMFLINE.ACCOUNTREF = EMUHACC.LOGICALREF` ile 2026 yevmiyesi hesap adına göre
kırılıyor: «Y.İçi TL Alıcılar» 49.471 satır / 1.113.883.623 ₺ borç, «Y.İçi TL Satıcılar» 41.237 /
522.082.997 ₺, «Kuveyt Türk Özel Finans A.Ş.» 4.352 / 1.217.092.085 ₺.
Bugün katalogda `muhasep hesap`, `hesap kodu`, `hesap adi`, `hesap pla` anahtarlarının hiçbiri yok —
yani muhasebe soruları hesap kırılımını hiç alamıyor. B088 («Bütçelediğimiz pazarlama giderinin ne
kadarı muhasebeye gerçekten düşmüş?») bu boşluğun içinde.

**Elenenler**

- **«hesap» / «hesap kodu» / «hesap adı» (öneksiz)** — *elendi (mıknatıs riski)*: katalogda `hesap`
  kelimesini içeren 25+ anahtar var (`cari hesap fisi`, `bank hesap adi`, `acik hesap baki` …).
  Öneksiz öbek, çözücünün tek-kelime geri düşüşüyle cari/banka sorularını muhasebeye çekerdi.
  Hepsi «muhasebe …» önekiyle yazıldı.
- **«masraf merkezi» → CENTERREF** — *elendi (boş + çakışma)*: EMUHACC.CENTERREF 1.374/1.374
  kayıtta 0; ayrıca terim zaten `sem_41cbbafc7a5c` (EMCENTER.DEFINITION_) üstünde.

---

## POLINE — üretim emri satırı

**Onaya hazır**

| terim | tür | alan | DB kanıtı |
|---|---|---|---|
| üretim emri satırı (+ üretim emri satırları, üretim emri kalemi) | ENTITY | POLINE | 4.491 satır / 1.221 emir; LINETYPE 0 = sarf edilecek malzeme (3.270), LINETYPE 4 = üretilecek mamul (1.221) |
| üretim emri planlanan malzeme miktarı (+ üretim emri malzeme planı, üretim emrinde planlanan malzeme) | METRIC | SUM(POLINE.AMOUNT) WHERE LINETYPE IN (0) | 7.769.499,91 — fiilî sarf (STLINE TRCODE 12/IOCODE 4) 20.211.220,23; **ayrı sayılar, ayrı anlam** |

Çakışma kuralına uyuldu: «üretim emri» öbeği `sem_a310716b1d12` «baskı» (PRODORD) üstünde kalıyor;
yeni kavram yalnız «üretim emri **satırı**» öbeğini taşıyor. «sarf miktarı / malzeme sarfı / sarf
edilen malzeme» eş anlamlıları bilerek verilmedi — onlar `sem_761633159662` «çekilen malzeme»
(STLINE, fiilî sarf) üstünde.

**Elenenler**

- **«üretim emri planlanan üretim miktarı» → SUM(AMOUNT) WHERE LINETYPE=4** — *elendi (çift
  sayma)*: toplam **8.848.628**; `PRODORD.PLNAMOUNT` toplamı da **8.848.628** — birebir aynı.
  Başlık tarafı («baskı») zaten sertifikalı.
- **«fire faktörü» → SCRAPFACT** — *elendi (boş)*: 4.491/4.491 satırda 0.

---

## SRVCARD — hizmet kartı

**Onaya hazır**

| terim | tür | alan | DB kanıtı |
|---|---|---|---|
| hizmet kartı (+ hizmet kartları, hizmet tanımı) | ENTITY | SRVCARD | 232 kart; 108'i 2026'da kullanılmış; 19.905 hizmet satırı / 305.014.447 ₺ net |
| hizmet kartı adı (+ hizmet kartı açıklaması, hizmet adı) | COLUMN | SRVCARD.DEFINITION_ | 230/232 dolu |
| hizmet kartı kodu (+ hizmet kodu) | COLUMN | SRVCARD.CODE | 232/232 dolu (hesap planı düzeninde, ör. 730.38.381) |
| alınan hizmet kartı (+ satın alınan hizmet kartı) | DIMENSION_VALUE | SRVCARD.CARDTYPE IN (1) | 204 kart; 15.296 satır / 293.622.955 ₺ |
| verilen hizmet kartı (+ satılan hizmet kartı) | DIMENSION_VALUE | SRVCARD.CARDTYPE IN (2) | 26 kart; 4.609 satır / 11.391.492 ₺ |

Bağ doğrulandı: `STLINE.STOCKREF = SRVCARD.LOGICALREF`, `STLINE.LINETYPE = 4`. En büyük kalemler:
«Komple Baskı Giderleri» 64.150.247 ₺, «Yazarların Telif Ücreti» 51.528.186 ₺, «Yabancı Yayın
Telif Hakları» 31.216.254 ₺. Bu 305 Mn ₺'lik gider kalemi bugün hiçbir kavramla karşılanmıyor.

**Kalan çakışma (bilerek bırakıldı, kuru koşuda basılıyor)**

`hizmet kart` anahtarı bugün `sem_77a33538f993` «hizmet kartı» COLUMN → `COSTDISTLN.SRVREF`
üstünde, `otomatik-yoklama` ile sertifikalı (gerekçesi `{"yoklama": {"examples": 3}}` — insan
kararı değil). Kırma denemesi: o eşleme maliyet dağıtım fişi satırının hizmet **referansı**dır,
hizmet kartının kendisi değil; kart tablosu SRVCARD'dır. Çürütülemedi ama zayıf olduğu gösterildi.
Ölçüm: set100'de 0 değişiklik; «Hizmet kartı adına göre gider tutarları» sorusu
`COSTDISTLN.SRVREF` yerine `SRVCARD.DEFINITION_` okumaya geçiyor (istenen yön).
**Öneri:** ENTITY yazıldıktan sonra `sem_77a33538f993`'ün terimi «maliyet dağıtım hizmet referansı»
olarak daraltılsın — ayrı, küçük bir iş kararı.

**«alinan hizmet» / «verilen hizmet» öbekleri** `INVOICE.TRCODE` üstünde (fatura türü). Terimler
bu yüzden «… kartı» ile bitiriliyor; öbeksiz kullanılmadı.

---

## FAREGIST — sabit kıymet kaydı

**Onaya hazır**

| terim | tür | alan | DB kanıtı |
|---|---|---|---|
| sabit kıymet kaydı (+ sabit kıymet kayıtları, demirbaş kaydı, demirbaş kayıtları) | ENTITY | FAREGIST | 1.079 kayıt (4 iptal), DATEIN 1991-01-01 – 2026-08-12; 15 sabit kıymet kartına (ITEMS.CARDTYPE=4) CRDREF ile bağlı |
| sabit kıymet giriş maliyeti (+ demirbaş alım bedeli, sabit kıymet alım bedeli, demirbaş giriş maliyeti) | METRIC | SUM(FAREGIST.INVALUE), CANCELLED IN (0) | 99.504.558,83 ₺; 1.055/1.079 dolu |
| birikmiş amortisman (+ toplam amortisman, sabit kıymet amortismanı, demirbaş amortismanı) | METRIC | SUM(FAREGIST.ACCUMDEPR), CANCELLED IN (0) | 32.553.265,68 ₺; 1.016/1.079 dolu |
| amortisman oranı (+ amortisman oranları, demirbaş amortisman oranı) | COLUMN | FAREGIST.DEPRRATE | 1.059/1.079 sıfırdan farklı; taşıt %20/5 yıl, bina %2/50 yıl, arsa 0 |
| sabit kıymet kayıt açıklaması (+ demirbaş açıklaması, sabit kıymet açıklaması) | COLUMN | FAREGIST.REGDEFINITION | 1.061/1.079 dolu |
| sabit kıymet alım tarihi (+ demirbaş alım tarihi, sabit kıymet giriş tarihi) | COLUMN | FAREGIST.DATEIN | 1.079/1.079 dolu; 2026'da 58 kayıt / 2.748.461 ₺ |

Kırılım doğrulandı (`CRDREF → ITEMS`): ARSALAR 19 kayıt / 39.471.576 ₺, TİCARİ TAŞITLAR 59 /
17.478.619 ₺ (8.011.767 ₺ amortisman), ÖZEL MALİYETLER 178 / 9.372.963 ₺, DİĞER DEMİRBAŞLAR 215 /
7.228.326 ₺, BİLGİSAYARLAR 169 / 5.968.162 ₺, YAZILIM LİSANSLARI 157 / 5.770.519 ₺.

**Elenen**

- **«sabit kıymet» (öbeksiz) eş anlamlısı** — *elendi (çakışma)*: aşağıdaki bölüme bakınız.

**Kalan risk (kayıt altına alındı)**: `amortisman` kelimesi katalogda bugün **hiç geçmiyor**
(kuru koşu «katalogda yeni kelimeler» satırı bunu basıyor). İki yeni kavram (birikmiş amortisman,
amortisman oranı) bu kelimeyi paylaşıyor; soruda tek başına «amortisman» geçerse çözücünün
tek-kelime geri düşüşü ikisinden birini seçer. Tek kelimelik eş anlamlı **verilmedi**; bu yalnız
geri düşüşün kendi davranışı ve iki aday aynı tabloda olduğu için yanlış tabloya gitmez.

---

## «Sabit kıymet» teriminin STLINE'dan geri çekilmesi — ayrı iş kararı

**Bugünkü durum.** `sem_6e4f6a20811d` «sabit kiymet», DIMENSION_VALUE,
`STLINE.LINETYPE IN (8)`, `rule-miner` tarafından sertifikalanmış (insan kararı yok;
`explain.gate.passed = false`, «support 0 < 3»).

**Çürütme denemesi — eşleme yanlış DEĞİL.** Logo'da STLINE.LINETYPE 8 gerçekten sabit kıymet
satırıdır; kardeşi LINETYPE 4 katalogda zaten «**hizmet satırı**» (`sem_f86504d24520`) adıyla
duruyor. Yani hata eşlemede değil, **terimin genişliğinde**: kardeş kavram «… satırı» ile
bitiyor, bu biri bitmiyor.

**Ölçü.** Canlı LG_411'de:

| kaynak | kapsam | tutar |
|---|---:|---:|
| STLINE LINETYPE = 8 | 60 satır | 3.469.868 ₺ (LINENET) |
| FAREGIST (iptalsiz) | 1.079 kayıt | 99.504.559 ₺ giriş maliyeti |

«Sabit kıymetlerimizin toplam değeri ne kadar?» sorusu bugün 3,5 Mn ₺ okur; doğrusu ~99,5 Mn ₺.
Bu, 29 kat hatalı bir cevaptır ve kapıdan sessizce geçer (kavram sertifikalı).

**Önerilen düzeltme (genel, soruya özel değil).** Eşlemeye dokunmadan terimi daralt:
`sabit kiymet` → `sabit kıymet satırı`, kardeş kavramla aynı kalıp. Boşalan `sabit kiymet`
anahtarını bu parti **doldurmuyor** — yeni FAREGIST kavramları «sabit kıymet kaydı», «sabit kıymet
giriş maliyeti» gibi öbeklerle geliyor. Öbeksiz anahtar boş kalır; onu hangi kavramın alacağı
(kayıt mı, giriş maliyeti mi) iş tarafının kararıdır.

Betikte `--narrow-sabit-kiymet` bayrağı bunu yapar; **varsayılan kapalıdır** ve `--apply` ile
birlikte verilmedikçe hiçbir şey değiştirmez. `sem_6e4f6a20811d` insan tarafından sertifikalanmış
olsaydı betik «DOKUNMA (kişi kararı)» der ve atlardı. Ölçüm: bayrak açıkken de set100'de
**0 değişiklik**.

---

## INVDEF — aday YOK, tablo boş

1. adımın sınıflamasında A kovasının en büyük karşılıksız tablosu (10,8 Mn satır). Gerçek veri
bunu **tamamen çürüttü**:

| kolon | LG_411 (3.980.876 satır) | LG_211 (3.607.239 satır) |
|---|---:|---:|
| MINLEVEL ≠ 0 | 0 | 0 |
| MAXLEVEL ≠ 0 | 0 | 0 |
| SAFELEVEL ≠ 0 | 0 | 0 |
| ABCCODE ≠ 0 | 0 | 0 |
| LOCATIONREF ≠ 0 | 0 | 0 |
| PERCLOSEDATE dolu | — | 0 |

Tablo 146 ambar × 29.066 malzemenin **kartezyen çarpımı**; her (ambar, malzeme) çifti için içi boş
bir satır. Taşıdığı tek bilgi `INVENNO` + `ITEMREF` çifti, o da zaten `sem_f67c237a2909` «ambar»
(STLINE.SOURCEINDEX, 25 ambar adıyla L_CAPIWHOUSE üzerinden) ile karşılanıyor.

Elenen adaylar: «asgari stok seviyesi» (MINLEVEL), «azami stok seviyesi» (MAXLEVEL), «güvenlik
stok seviyesi» (SAFELEVEL), «ABC kodu» (ABCCODE) — hepsi *boş kolon*.

**Yan bulgu — set100/A028.** «Asgari stok seviyesinin altına düşmüş malzemeler hangi ambarlarda
var?» sorusunun veri karşılığı **yok**: Logo'da asgari stok seviyesi alanı hiç doldurulmamış.
Bu bir kavram eksiği değil, veri eksiğidir; doğru davranış dürüst rettir. Ayrı bir iş kararı
olarak kayda geçirilmeli.

---

## set100 risk ölçümü

Ölçüm yöntemi h4 ajanınınkiyle aynı: adaylar yalnız **bellekteki** `certified_index`'e eklenir
(`_WithProposal`), `publish_runtime_snapshot` kapatılır, köprüyle aynı kurulan iki çözücü
(`SemanticResolver`, aynı `Conventions` + `coverage` + `verified_pairs`) 100 soruyu önce/sonra
okur, slot okuması değişen sorular basılır. `source-reading.py --hide-*` kullanılmadı.

```
sudo systemd-run … python - --simulate ~/testset/set100.jsonl < apply.py
→ {"soru": 100, "okuması_değişen": 0}

… --narrow-sabit-kiymet --simulate ~/testset/set100.jsonl < apply.py
→ {"soru": 100, "okuması_değişen": 0}
```

**Hedef tutturuldu: sıfır değişiklik.** Gerileme adayı yok, dolayısıyla elenen aday da yok.

Pozitif kontrol (elle sorular, beklenen yönde değişim):

| soru | önce | sonra |
|---|---|---|
| Birikmiş amortismanımız toplam ne kadar? | UNRESOLVED (`amortismanimiz`) | METRIC FAREGIST.ACCUMDEPR |
| Sabit kıymet giriş maliyetimiz toplam ne kadar? | PARTIAL — STLINE.AMOUNT*OUTCOST + STLINE.LINETYPE | METRIC FAREGIST.INVALUE |
| Teslimat ilçesine göre fatura sayısı? | PARTIAL — `ilcesine` → **CLCARD.TOWN** (yanlış taraf) | COLUMN SHIPINFO.TOWN |
| Teslimat ülkesine göre ciro? | PARTIAL (`teslimat`, `ulkesine` çözülmemiş) | COLUMN SHIPINFO.COUNTRY |
| Muhasebe hesabı kırılımında gider toplamı? | PARTIAL (`muhasebe` çözülmemiş) | ENTITY EMUHACC |
| Hizmet kartı adına göre gider tutarları? | COLUMN COSTDISTLN.SRVREF | COLUMN SRVCARD.DEFINITION_ |
| Verilen hizmet kartı sayısı kaç? | INVOICE.TRCODE sayımı (yanlış tablo) | SRVCARD.CARDTYPE sayımı |
| Üretim emri satırlarında planlanan malzeme miktarı? | ENTITY PRODORD | ENTITY POLINE |
| Üretimde kaynak kullanımı kayıtları kaç tane? | PARTIAL — CLCARD sayımı (yanlış tablo) | ENTITY OCCUPATION |
| Teslimat kartı sayısı kaç? | UNRESOLVED, hint TIMAS_MSCRM | ENTITY SHIPINFO + sayım |
| Amortisman oranı en yüksek demirbaşlar? | UNRESOLVED, hint TIMAS_MSCRM | METRIC FAREGIST.DEPRRATE (PARTIAL: `demirbaslar` hâlâ açık — tek kelime kuralı gereği) |

`set1000.jsonl` üzerindeki aynı ölçüm arka planda başlatıldı; uygulamadan önce sonucuna bakılmalı.

---

## Uygulama sırası önerisi

Her adımdan sonra köprü kendi kataloğunu 30 sn içinde yeniler; `resolver-gate.py` ile
`~/testset/resolver-baseline-set100.json` karşılaştırılmalı, ancak ondan sonra bir sonraki adım.

1. **FAREGIST** (6 kavram) — en yüksek değer, sıfır çakışma, 99,5 Mn ₺'lik bir alan bugün hiç
   okunmuyor.
2. **EMUHACC** (3 kavram) — sıfır çakışma; muhasebe kırılımını açar (B088'in ön koşulu).
3. **SRVCARD** (5 kavram) — 305 Mn ₺'lik gider kalemi; `hizmet kart` çakışması bilinerek alınıyor.
   Hemen ardından `sem_77a33538f993`'ün terimi daraltılmalı (ayrı karar).
4. **SHIPINFO** (3 kavram) — görünüm entity'sine, mevcut «gönderim şehri» ile aynı yere.
5. **POLINE** (2 kavram) — «üretim emri» öbeğine dokunmadığı doğrulanarak.
6. **OCCUPATION** (1 kavram) — yalnız entity; süre ölçüsü birim kararı gelene kadar yazılmaz.
7. **`--narrow-sabit-kiymet`** — ayrı iş kararı; 1. adım yazıldıktan ve doğrulandıktan sonra,
   tek başına.

**INVDEF için adım yok.** Bunun yerine iş tarafına iki soru: (a) asgari/azami stok seviyeleri
Logo'da neden hiç doldurulmamış, doldurulacak mı? (b) A028 tipi sorular için dürüst ret kabul
mü, yoksa seviye başka bir kaynakta mı tutuluyor?
