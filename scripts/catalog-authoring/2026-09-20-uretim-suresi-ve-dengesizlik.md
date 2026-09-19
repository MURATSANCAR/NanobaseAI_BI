# h4 — Katalog sözlük boşluğu: öneri (Q10/C011, Q36/B073)

Tarih 2026-09-20 · katalog sürümü 70549 (ölçüm boyunca değişmedi; hiçbir şey yazılmadı) · uygulayacak: ana oturum.

Betik: `apply.py` (aynı klasör). Varsayılan KURU KOŞU; `--simulate` bellekte ölçer; `--apply` yazar.
Çalıştırma (dosya kopyalamadan, köprünün ortamıyla): `./run.sh [--withdraw-generic] [--include-optional] [--apply]`
(= `sudo systemd-run --pipe --wait … semantic-venv/bin/python - < apply.py`).

## 1. Gerçek veritabanı bulguları (salt-okunur, connector_from_file)

### Logo üretim — LG_411_DISPLINE / LG_411_WORKSTAT
| Ne | Sayı |
|---|---|
| DISPLINE satır | 1.221 (OPBEGDATE 05.01–17.08.2026) |
| WSREF dolu / yetim | 1.221 / 0 · 21 farklı istasyon |
| WORKSTAT kart | 56 (ACTIVE=0 olan 42) · ad `NAME`, kod `CODE` |
| PLNDURATION > 0 | 1.221/1.221 (88 … 150.000, ort. 7.247) |
| ACTDURATION > 0 | 1.200/1.221 |
| LINESTATUS | 3 = 1.200 satır (hepsinde ACTDURATION ve ACTDUEDATE dolu) · 1 = 21 satır (ACTDURATION 0, ACTDUEDATE NULL) |
| Tarih doluluğu | OPBEGDATE 1.221 · OPDUEDATE 1.221 · ACTBEGDATE 1.221 · ACTDUEDATE 1.200 |
| İptal kolonu | YOK (CANCELLED yok; yalnız LINESTATUS, RECSTATUS, WFSTATUS) |

**Birim kanıtı:** `RUNTIME = 65536` 1.221/1.221 satırda (Logo saat kodlaması: saat·2²⁴ + dk·2¹⁶ + sn·2⁸ → 1 dakika);
`PLNDURATION = PRODORD.PLNAMOUNT` 1.221/1.221 satırda (adet × 1 dk). Yani birim **dakika**, ama süre gerçek bir ölçüm değil:
planlanan süre = planlanan adet; gerçekleşen çoğunlukla plan + 200. (`ACTDURATION = ACTAMOUNT` yalnız 109 satırda.)

**"Geçen ay" (Ağustos 2026) hangi tarihe göre?**
| Tarih alanı | operasyon | istasyon | plan sa | gerçekleşen sa |
|---|---|---|---|---|
| ACTDUEDATE (gerçekleşen bitiş) — referans | 77 | 10 | 11.545 | 11.757 (sapma +212,5 sa) |
| OPBEGDATE (planlanan başlangıç) — profilin varsayılan tarih kolonu | 98 (77'si tamamlanmış) | 10 | 14.187 | 11.759 |
| OPDUEDATE (planlanan bitiş) | 107 (90) | 10 | 11.078 | 10.024 |
| ACTBEGDATE (gerçekleşen başlangıç) | 43 (28) | 6 (5) | 1.753 | 746 |

### CRM — Timas_MSCRM.dbo.new_satishedefleriBase
- 334.982 satır; 12 ay kolonu + `new_ToplamHedef` hepsi `int`; negatif ay değeri 0.
- `new_yil` (StringMap): 1=2023 (43.817 satır), 2=2024 (111.575), 3=2025 (55.909), **4="2000" (41.907)**, 100000000=2026 (68.327), **100000001="1991" (4.020)**, NULL 9.427 (ürünsüz). Kural C2 yalnız 1,2,3,100000000'i anlatıyor — 4 ve 100000001 belgelenmemiş.
- 2026 (statecode 0): 4.020 ürün, hedefi > 0 olan 3.429, hedefi 0 olan 591; aylık toplam = new_ToplamHedef (0 tutarsız ürün).
- **Kapalı biçim CV** (aşağıdaki formül) referansın `STDEV/AVG` sonucuyla 3.429/3.429 üründe birebir (en büyük fark 0,0); 591 üründe ikisi de NULL. En yüksek 3,4641 (= √12), 44 ürün eşit. Tüm yıllar birlikte: 8.586 ürün, en yüksek yine 3,4641, 11 ürün eşit.

## 2. Katalogda bugün ne var
- Profiller VAR: `DISPLINE` (LG_{n0}_DISPLINE, 192 kolon, zaman penceresi 2026-01-05…08-17), `WORKSTAT` (LG_{n0}_WORKSTAT, 41 kolon, "İş istasyonları"), `NEW_SATISHEDEFLERIBASE` (37 kolon).
- DISPLINE/WORKSTAT üstünde sertifikalı kavram YOK (5 aday LINESTATUS değeri, 1 reddedilmiş). "iş emri" PRODORD'un («baskı») eş anlamlısı — Logo'da iş emri DISPLINE'dır; dokunmadım, not.
- «gerçekleşen süre» → NEW_PLANSORUMLULARIBASE.NEW_TAMAMLANANISSURESI ve «planlanan süre» → …NEW_TOPLAMSURESI: ikisi de **makine onayı** (`sl_vocabulary.decided_by = otomatik-yoklama`, 2026-09-16). Q10'u CRM'e çeken bu.
- NEW_SATISHEDEFLERIBASE: 11 COLUMN + 2 ENTITY + durum değerleri sertifikalı; ölçü yok, "dengesiz" yok.
- Çözücü bugün: Q10 → slot CRM kolonu, çözülmeyen `istasyonlarinin, planlanandan`, kaynak ipucu TIMAS_MSCRM. Q36 → çözülmeyen `dengesiz`.

## 3. Önerilen kavramlar (çekirdek — `apply.py` varsayılanı)
Entity adları koşu anında tablo kalıbından okunur. Hepsi `human_certify(who="operator:claude (iş teyidi bekliyor)")`.

| # | Terim | Tür | Eşleme | Koşul / extra | Eş anlamlılar |
|---|---|---|---|---|---|
| 1 | iş istasyonu | COLUMN | WORKSTAT.NAME | — («masraf merkezi → EMCENTER.DEFINITION_» kalıbı) | iş istasyonları, iş istasyonu adı, üretim istasyonu |
| 2 | iş istasyonu kodu | COLUMN | WORKSTAT.CODE | — | — |
| 3 | operasyon gerçekleşen süresi | METRIC | `SUM(DISPLINE.ACTDURATION)` | `DISPLINE.ACTDURATION > (0)`; func SUM, unit dakika, link `DISPLINE.WSREF = WORKSTAT.LOGICALREF` | iş istasyonu(ları) gerçekleşen süresi |
| 4 | operasyon planlanan süresi | METRIC | `SUM(DISPLINE.PLNDURATION)` | koşulsuz; aynı extra | iş istasyonu(ları) planlanan süresi |
| 5 | operasyon süre farkı | METRIC | `SUM(DISPLINE.ACTDURATION - DISPLINE.PLNDURATION)` | `DISPLINE.ACTDURATION > (0)` (devam eden 21 satır eksi sapma üretmesin) | iş istasyonu(ları) süre farkı |
| 6 | dengesizlik katsayısı | METRIC | kapalı biçim CV: `SQRT((Σ POWER(SUM(ay),2) − POWER(Σ SUM(ay),2)/12)/11) / NULLIF(Σ SUM(ay)/12, 0)` (12 ay kolonu, `ISNULL(CAST(.. AS FLOAT),0)`) | `statecode IN (0)`; func RATIO, undated | dengesiz, dengesizlik, dengesiz dağılım, dengesizlik oranı |

Neden kapalı biçim: katalog formülü tek bir toplama ifadesidir; `CROSS APPLY (VALUES …)` taşıyamaz. Bu biçim hangi kırılımla gruplanırsa (ürün, bölge, BMT) o düzeyde ayları toplayıp CV verir; hedefi 0 olan grup NULL döner (dışlanmış olur). Köprünün 09-19'daki hatası (satır düzeyinde STDEV, CV 6,64 > √12) bu biçimde oluşamaz.

## 4. Karar gerektiren varsayımlar (iş teyidi)
1. **Süre birimi = dakika.** Kanıt güçlü (RUNTIME kodlaması) ama süre = adet×1 dk, gerçek zaman ölçümü değil. Formüller ham dakikayı toplar; ÷60 formüle gömülmedi (referans saat gösteriyor; altın kontrol yalnız satır sayısı = 10).
2. **"Geçen ay" tarih alanı.** Katalogda ölçü başına tarih kolonu tanımlanamıyor (`Mapping.time_primitive` derleyicide okunmuyor); deterministik derleyici `conventions.time_column(DISPLINE)` = OPBEGDATE kullanır. Referans ACTDUEDATE. Ağustos'ta ikisi de 10 istasyon / 77 tamamlanmış operasyon veriyor ama saatler farklı (tablo §1). Hangi tarih? Karar ACTDUEDATE olursa kod gerekir (ölçüye tarih kolonu) — bu öneri kapsamı dışında.
3. **Tamamlanma filtresi:** `ACTDURATION > 0` (⇔ LINESTATUS 3). İptal kolonu yok.
4. **'dengesiz' = CV (örneklem std. sapma / ortalama)**, Kural C2 ile aynı. Başka ölçü (en yüksek ay payı) istenirse formül değişir.
5. **Hedefi 0 olan ürünler dışlanır** (NULLIF → NULL): 2026'da 591 ürün.
6. **Yıl kapsamı:** ölçü `undated`; yıl süzgeci (new_yil = 100000000) kavrama GÖMÜLMEDİ (gelecek yıl bozulurdu). Yılsız okunursa tüm yıllar toplanır (en yüksek CV yine 3,4641, ama 11 ürün; 2026'da 44). "Hedef sorusu yıl demiyorsa bu yıl" kuralı C2'de modele yazılı; deterministik yol bunu bilmiyor. Ayrıca new_yil 4 ("2000") ve 100000001 ("1991") nedir? — iş sorusu.
7. `new_stokkarti IS NOT NULL` koşulu eklenmedi: derleyicinin `_pred_key_sql`'i IS NOT NULL okuyamıyor, okunamayan koşul deterministik yolu iptal ediyor. 2026'da ürünsüz satır 0; diğer yıllarda 29 + yılsız 9.427.

## 5. Risk — bellekte ölçüldü (`--simulate`, set100, yazmadan)
Çözücünün iki davranışı yeni anahtarları "mıknatıs" yapıyor: (a) fiil köprüsü `_metric_from_verb`: soruda ölçü yoksa bir kelimenin kökü, bir ölçü anahtarının **ilk kelimesinin** başıyla eşleşirse o ölçü; (b) `_backoff`: tek kelime, katalogda **yalnız bir kavramın** anahtarında geçiyorsa o kavram.
- İlk taslak (adlar «planlanan …», «gerçekleşen …», «aylara dağılım …», eş anlamlı «süre sapması») set100'de **6 soruyu** değiştirdi: C010 («planlanan bitiş tarihi» → PLNDURATION ölçüsü), B072 («aylar» → CV ölçüsü), A097 ve B087 («sapma» → DISPLINE ölçüsü; bunlar ödeme vadesi sapması). set1000'de «sapma/sapan» 4 soruda daha geçiyor (K0704, K0728, K0844, K0978) — hepsi başka konular.
- **Çekirdek öneri (yukarıdaki tablo): set100'de yalnız 2 soru değişiyor — C011 ve B073.** Adlar bu yüzden «operasyon …/iş istasyonu …» ile başlıyor ve «sapma», «fiili», «üretim …», «hedef …», «değişim …» anahtarlarda YOK.
- `--include-optional` («süre sapması» eş anlamlıları): A097, B087 ve "Bölge bazında hedefe göre sapma" sorusunu DISPLINE'a çekiyor → **önermiyorum**; genel çözüm `_backoff`'un çok kelimeli ölçü anahtarındaki nitelenen kelimeyi tek başına ölçü saymaması (kod işi).
- Katalogda yeni olan kelimeler: `istasyo/istasyon` (5 kavramda birden geçtiği için `_backoff` susar), `dengesiz/dengesizlik` (tek başına CV ölçüsünü çeker — kasıtlı; set100+set1000'de yalnız B073'te geçiyor).
- set100'de aynı kelimeleri taşıyan sorular: C010 (planlanan), C011, B073, C063/A023/A098/B082 (gerçekleşen), A047 (planlanan), A097/B087 (sapma), A019/A094 (süre). Çekirdekte C011 ve B073 dışındakilerin okuması DEĞİŞMEDİ.

### Çekirdek sonrası iki sorunun okuması
- **B073:** `dengesiz → METRIC (CV)`, `yıllık hedefin → NEW_TOPLAMHEDEF`; `urun` (Logo ITEMS.NAME) modele bırakılıyor. Ret sebebi kalkıyor. Ürün kırılımını (new_stokkarti) ve yılı model/kural C2 yazacak — tam kapıda doğrulanmalı.
- **C011:** `iş istasyonlarının → WORKSTAT.NAME` yerleşiyor, kaynak ipucu CRM'den çıkıyor (TIMAS_MSCRM → yok) ama «gerçekleşen süresi» hâlâ CRM kolonu, `planlanandan` çözülmüyor. **Tam çözmüyor.**
- **`--withdraw-generic` ile** (iki makine onayını `vocabulary.withdraw` ile geri çek): C011 kaynak ipucu **Logo** oluyor, CRM slotu kalkıyor; kalan `suresi, planlanandan` modele gidiyor (WORKSTAT sertifikalı tablo olarak düşürülemez). Bedeli: "Plan sorumlularının gerçekleşen süresi" gibi bir CRM sorusu RESOLVED → UNRESOLVED oluyor (kavramın kendi adı «tamamlanan iş süresi» kalır). set100/set1000'de böyle bir CRM sorusu yok. **İş kararı.**
- Doğal ifadeler çekirdekle tam çözülüyor: "İş istasyonu bazında geçen ay operasyon süre farkı nedir?" → RESOLVED (WORKSTAT.NAME + ölçü 5).
- C011'in kendi cümlesini ("gerçekleşen süresi planlanandan … saptı") kavrama eş anlamlı yapmak çözüyordu ama soruya özel kalıptır — önermiyorum. Genel çözüm kodda: aynı öbek iki kaynakta tanımlıysa (COLUMN duyuları) sorunun öbekle adlandırdığı kaynak duyuyu seçsin (`_primary_entity` yalnız METRIC/DIMENSION_VALUE'dan çıkıyor).

## 6. Yan bulgu
`tests/text2sql/source-reading.py --hide-*`: `Hidden` sarmalayıcı `publish_runtime_snapshot`'ı gerçek store'a devrediyor; çözücü her koşuda gizlenmiş dizini `sl_catalog_version`'a YENİ SÜRÜM olarak yazar ("yazmaz" deniyor ama yazar). `apply.py --simulate` bu çağrıyı kapatır (ölçüm sonrası sürüm 70549'da kaldı).

## 7. Uygulama sonrası
Köprü yeniden başlatılmaz (`ensure_fresh` 30 sn içinde yükler). Sonra: `resolver-gate.py` (beklenen: yalnız C011, B073 değişir), ardından tam kapıda Q10 ve Q36 + tam set regresyonu.
