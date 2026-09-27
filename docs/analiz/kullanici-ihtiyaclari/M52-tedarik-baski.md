# M52 — Tedarik Zinciri ve Baskı Yönetimi: kullanıcı ihtiyaç analizi

Durum: analiz (kod yok) · Tarih: 2026-09-28 · Kaynaklar: `specs/M52.txt`, `specs/M12.txt`, `specs/M11.txt`, `specs/M10.txt`,
`ZEKİ_Veri_Haritasi2.html` (M52, M12 satırları), M12 kodu (başka ajan, dalda: `.claude/worktrees/agent-a83583b6e0e83abe9/backend/semantic_bridge/{production.py, production_plan.py, production_store.py}`),
`configs/semantic/knowledge/logo/knowledge/{rules/logo-erp.md (Kural 20), metrics/logo-timas.md, caveats/logo-timas.md, rules/crm-timas.md (C17)}`,
`configs/semantic/knowledge/crm/{OKUNUR-TABLOLAR.md, table_descriptions.json}` (`new_Uretim`, `new_baski`, `new_baskiislem`,
`new_kagitcinsi`, `new_kagitebadi`, `new_uretimplanlamatakvimi`, `new_baskioneri`, AccountBase `new_ozelKod`),
`docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`, `backend/semantic_bridge/management/`, bellek: `freelancer-payments-logo`,
`system-of-record-logo`, `logo-155-frozen-copy`, `invoice-count-sales-scope`, `timas-logo-database-shape`. Sunucuya bağlanılmadı.

## 1. Modül ne işe yarar

İş tanımı (M52): talep tahminine dayalı baskı adedi önerisi, matbaa kapasite ve fiyat karşılaştırması, kağıt/malzeme tedarik
planlaması, baskı takvimi ve kritik yol (K2); matbaa üretim aşaması izleme, teslim gecikmesi, tedarikçi ödeme/fatura takibi, stok
kapasitesi × baskı adedi uyumu (K1). Çıktılar: baskı planı, üretim takip, maliyet raporu.

**M12 ile sınır (net):** M12 Üretim Yönetimi şu an kodlanıyor (`/uretim`, uçlar `/api/v1/editorial/production/*`, yetki
`sayfa:uretim`, `ozellik:uretim.yaz`, `ozellik:uretim.matbaa-onay`). M12 **tek kitabın tek baskısı** düzeyindedir: üretim kartı,
geriye doğru takvim, matbaa atama ve onayı, matbaa teklifi (`semantic_production_quotes`), aşama gecikmesi, baskı çıkışı, matbaa
performans istatistiği (`/printers`: iş sayısı, zamanında teslim, ortanca süre, birim fiyat ve eğilimi, kalite).
**M52 portföy ve tedarikçi düzeyidir:** (a) bütün baskıların ay × matbaa yükü ve çakışması, (b) kağıt/malzeme ihtiyacı ve
tedariki, (c) matbaa ve kağıtçıya olan borç, fatura ve ödeme takvimi (Logo), (d) birim baskı maliyeti eğilimi (portföy), (e) depo
kapasitesi × gelecek baskılar (M43), (f) yıllık matbaa/kağıtçı değerlendirmesi ve sözleşme hazırlığı. M52 kart açmaz, matbaa
atamaz, teklif girmez — M12'nin verisini okur. Baskı adedi önerisi M10/M11 ve mevcut "Baskı önerisi" raporundadır; M52 yalnız
toplamını plan girdisi olarak kullanır.

TİMAŞ'ın bugünkü sorunu: üretim kartları CRM'de (16.129; 2026'da 1.708 etkin kart — M12 ölçümü 2026-09-28) ayrıntılı kağıt ihtiyacı
alanlarıyla dolu, matbaa bir seçenek listesi (~40); ama **matbaa teklif geçmişi CRM'de yok** (`new_baskiislem` 23 satır, 2015–2017),
matbaalara ve kağıtçılara olan borç Logo'da ve kapama kullanılmadığı için yalnız FIFO yaklaşımıyla görülebiliyor.

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| Prodüksiyon (üretim) müdürü | CRM departman "Üretim" (kod 10); M12 iş tanımında "prodüksiyon müdürü onaylar" | Her gün | Masaüstü |
| Satın alma / kağıt tedarik sorumlusu | Birim kanıtı yok (varsayım; üretim içinde olabilir); Logo cari özel kodu "KAĞITÇILAR" | Haftalık | Masaüstü |
| Finans – tedarikçi ödemeleri | Mali İşler 10 | Haftalık ödeme günü, ay sonu | Masaüstü |
| Yayın yönetmeni / genel yayın yönetmeni (baskı adedi ve takvim onayı) | CRM kitapta `new_yayinyonetmeni` | Aylık baskı planı toplantısı (varsayım) | Masaüstü + telefon |
| Depo müdürü (gelecek baskıların yer ihtiyacı) | Depo | Haftalık | Masaüstü |
| Üst yönetim (maliyet eğilimi, matbaa sözleşmeleri) | — | Aylık/çeyreklik | Telefon (varsayım) |

## 3. Bugün bu iş nasıl yapılıyor

- **Prodüksiyon müdürü:** CRM üretim kartı akışı: (0) Baskı Hazırlık → (1) Editoryal Hazırlık → (2) Bilgi Kontrol → (3) Üretim Maliyet
  Çalışması → (4) Kesin Adet/Fiyat → (5) Matbaa Belirleme → Matbaada → Depo Girişi; bekleme nedeni (Matbaa Belirlenmedi,
  Yoğunluk…), öncelik, baskı ayı (`new_baskiayi`), planlanan tarihler ayın 1/15/25'ine yığılı (M12 ölçümü: plan tarihleri takvim
  kuralıdır). Baskı planı değişiklikleri `new_uretimplanlamatakvimi` (2.490 kayıt, değişiklik sebebi: kayıt hatası, sözleşme,
  editör, yazar, mütercim kaynaklı). Matbaa kapasitesi hiçbir sistemde yok; aylık yük muhtemelen tecrübe/telefonla (varsayım).
- **Satın alma (kağıt):** kartta kapak/iç/şömiz/harita/afiş/yan kağıt/ayraç için kağıt cinsi, tabaka ve kg ihtiyacı hesaplı
  (`new_*netkagitihtiyacikg`, `new_*brutkagitihtiyacikg`, `new_*toplamkagitihtiyaci`). Kağıdı TİMAŞ mı alıyor matbaa mı — veride
  kesin değil: Logo'da "KAĞITÇILAR" cari özel kodu var (CRM `new_ozelKod` seçeneği, "Logo'daki özel kod alanına denk gelen alan")
  → en azından bir kısmını TİMAŞ alıyor (varsayım). Ay bazında toplam kağıt ihtiyacı ekranı yok.
- **Finans:** matbaa ve kağıt faturaları Logo'da alış (TRCODE 1 mal, 4 hizmet); satıcı bakiyesi 320; Logo'da **ödeme kapama
  kullanılmıyor** (PAYTRANS 116.514 plan satırının 14'ünde ödenen dolu) → hangi faturanın ödendiği bilinmez, vade FIFO yaklaşımıyla.
- **Tıkanma (varsayım):** aynı ay aynı matbaaya çok iş yığılınca gecikme; kağıt fiyatı değişimi maliyete geç yansıyor; ödeme takvimi
  üretim takvimiyle yan yana görülmüyor.

## 4. İhtiyaçlar ve acı noktaları

**Prodüksiyon müdürü**
1. Önümüzdeki 3–6 ayın baskı yükü: ay × matbaa × adet/forma; aynı aya yığılma ve çakışma uyarısı.
2. Matbaa karnesi portföy düzeyinde (M12 `/printers`'tan) ve yıllık değerlendirme sunumu.
3. Kritik yol: baskı → ciltleme → depo → dağıtım → yayın ayı; gecikme riski olan işlerin portföy listesi (M12 kart gecikmelerinin toplamı).

**Satın alma**
1. Aylık kağıt ihtiyacı (kağıt cinsi × ebat × kg), açık kartlardan; önceki ayların alışıyla karşılaştırma.
2. Kağıt alış fiyatı eğilimi (Logo alış satırları, kağıtçı cariler).

**Finans**
1. Matbaa/kağıtçı bazında borç, vadesi geçmiş (FIFO), önümüzdeki 30/60/90 gün ödeme planı.
2. Üretim kartı ↔ fatura eşleşmesi: faturası gelmemiş biten iş, işi olmayan fatura.

**Yönetim**
1. Birim baskı maliyeti eğilimi (kitap tipi/cilt/sayfa kırılımı).
2. Baskıya bağlı toplam nakit çıkışı tahmini (önümüzdeki çeyrek).

## 5. Nasıl kullanmak isteyecekler

**Kullanıcı hikâyeleri**
- Prodüksiyon müdürü olarak önümüzdeki 4 ayın matbaa yükünü tek tabloda görmek istiyorum, çünkü Eylül yığılmasını Temmuz'da dağıtırım.
- Prodüksiyon müdürü olarak aynı hafta aynı matbaaya düşen işleri görmek istiyorum, çünkü okul sezonunda gecikme riskini azaltırım.
- Satın alma sorumlusu olarak açık kartların aylık kağıt ihtiyacını kağıt cinsine göre görmek istiyorum, çünkü kağıdı fiyat artmadan alırım.
- Finans uzmanı olarak matbaa bazında önümüzdeki 60 günün ödeme yükünü görmek istiyorum, çünkü nakit planına koyarım.
- Finans uzmanı olarak depo girişi yapılmış ama faturası gelmemiş baskıları görmek istiyorum, çünkü tahakkuku kaçırmam.
- Yönetici olarak birim baskı maliyetinin son 24 ay eğilimini görmek istiyorum, çünkü fiyatlama (M9) ve matbaa pazarlığına girerim.

**Ana ekranlar ve akış**
- Açılış (`/tedarik`): önümüzdeki 6 ay × matbaa ısı tablosu (adet ve iş sayısı), çakışma uyarıları, bu ay kağıt ihtiyacı (kg),
  30 gün ödeme yükü, birim maliyet eğilimi kıvılcım grafiği.
- Sekmeler: Baskı yükü · Kağıt ve malzeme · Tedarikçi borç ve ödeme · Maliyet eğilimi · Matbaa değerlendirme · Depo uyumu.
- En sık 3 işlem: ay seçip yükü görmek (1 tık), kağıt ihtiyacını Excel'e almak (2 tık), bir matbaanın borç/fatura/iş listesini açmak (2 tık).

**Zeki AI'ya soracakları örnek sorular**
- "Ekim'de hangi matbaaya kaç kitap basılacak?"
- "Önümüzdeki üç ayda 60 gr kitap kâğıdı ihtiyacımız kaç ton?"
- "X Matbaa'ya vadesi geçmiş borcumuz ne kadar?"
- "Son 12 ayda amerikan ciltli 200 sayfalık kitapların birim baskı maliyeti nasıl değişti?"
- "Depo girişi olmuş ama faturası gelmemiş baskılar hangileri?"
- "Kasım'da depoya girecek toplam adet nedir, yerimiz yeter mi?"

**Otomasyon katmanı**
- K1 (tam otomatik, salt okuma): yük tablosu, çakışma uyarısı, kağıt ihtiyacı, borç/ödeme planı, fatura eşleşmesi, maliyet eğilimi.
  "Matbaa üretim aşaması anlık izleme" M12'nindir; M52 yalnız toplar.
- K2 (Zeki önerir, insan onaylar): yük dengeleme önerisi (işi başka aya/matbaaya kaydır), kağıt alım zamanı önerisi, matbaa sipariş
  formu/teknik şartname taslağı, gecikme eskalasyon e-posta taslağı. Onay portal kaydıdır; CRM kartı değişmez (değişiklik M12'de/CRM'de insan eliyle).
- K3: yıllık matbaa sözleşmesi, çerçeve kağıt alımı.
- K4: fiyat pazarlığı, kalite kabul.
- Baskı adedi ve matbaa seçimi onayı M12'de kalır (`ozellik:uretim.matbaa-onay`).

**Bildirim / uyarı**
- Prodüksiyon müdürü: bir ay × matbaada eşik aşılınca (eşik kullanıcı tanımlı kapasite; yoksa geçmiş 12 ayın en yüksek aylık yükü
  referans olarak gösterilir, "kapasite" denmez) — haftalık e-posta + portal zili.
- Finans: her pazartesi 08:00 önümüzdeki 30 gün matbaa/kağıtçı ödeme listesi (planlı rapor).
- Satın alma: ayın 1'inde gelecek 3 ay kağıt ihtiyacı özeti.

**Onay ve yetki (öneri)**
- `sayfa:tedarik` — üretim, satın alma, yayın yönetimi, depo.
- `ozellik:tedarik.borc` (tedarikçi borç, fatura, ödeme) — **açıkça verilir** (finans, üretim müdürü, yönetim).
- `ozellik:tedarik.maliyet` (birim maliyet, teklif fiyatı) — açıkça verilir.
- `ozellik:tedarik.kapasite` (matbaa kapasite ve eşik tanımı) — üretim müdürü.
- `ozellik:tedarik.oneri-karar` (yük dengeleme/kağıt önerisi kararı) — üretim müdürü, satın alma.

## 6. Veri

| Gereken veri | Kaynak (Logo / CRM / T-soft / kullanıcı girer / dış) | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Baskı kartları (adet, ay, matbaa, aşama, öncelik) | CRM `new_UretimBase` (`new_kesinlesenbaskiadeti`, `new_netbaskiadedi`, `new_baskiayi`, `new_new_baskitarihi`, `new_Matbaa`, `statuscode`, `new_oncelikdurumu`, `new_BeklemeDurumu`, `new_baskitipi`, `new_UretimTipi`, `new_ciltlemesekli`) — M12 `/cards` üzerinden | M12 ölçtü ve okuyor | Yok (M12'ye bağlı) |
| Matbaa performansı | M12 `/api/v1/editorial/production/printers` | M12'de hesaplanıyor | Kalite işaretlemesi yeni; geçmiş yok |
| Matbaa teklifleri | M12 `semantic_production_quotes` (portal) | Yeni tablo; geçmiş yok | Eski teklifler (e-posta/Excel) içe alınacak mı? (Soru 3) |
| Matbaa kapasitesi | — | Hiçbir kaynakta yok | Kullanıcı girer (Soru 1) |
| Kağıt ihtiyacı | CRM `new_UretimBase` (`new_{kapak,icsayfabir,icsayfaiki,somiz,harita,afis,yankagit,ayrac}{netkagitihtiyacikg,brutkagitihtiyacikg,toplamkagitihtiyaci,kagitcinsiid}`), `new_kagitcinsi` (102), `new_kagitebadi` (97) | Alanlar biliniyor | Doluluk ve birim (kg mı tabaka mı) **ölçülecek** |
| Kağıt alışı ve fiyatı | Logo `INVOICE`/`STLINE` TRCODE 1 (mal alımı), cari `CLCARD.SPECODE = 'KAĞITÇILAR'` (varsayım: Logo değeri CRM seçeneğiyle aynı yazım); `PRCLIST` alış fiyatı | Satınalma ölçüsü (`satinalma`) katalogda | Kağıt malzeme kartları (hangi stok kodu grubu) ve cari listesi **ölçülecek** |
| Matbaa faturaları | Logo TRCODE 1/4, `CLCARD.SPECODE = 'MATBAALAR'` (varsayım aynı) | — | **Ölçülecek**; üretim kartı ↔ fatura bağ anahtarı yok (Soru 4) |
| Borç, vade, ödeme | Logo `CLFLINE` (320, TRCODE 31/34 − 36), `PAYTRANS` (SIGN 1); ölçüler `ortalama_odeme_suresi`, `planlanan_odeme_vadesi`, FIFO yaşlandırma | Tanımlı; kapama yok → yaklaşık | Her ekranda "FIFO yaklaşımı" notu zorunlu |
| Gerçekleşen üretim adedi | Logo `LG_<firma>_PRODORD`, `STFICHE` TRCODE 13 (`PRODSTAT` 0 gerçek), ölçü "üretilen adet" (Kural 20) | M12 okuyor | Yok |
| Birim baskı maliyeti | CRM `new_kesinlesenbaskifiyati`, `new_toplammaliyet`, `new_paketlemebirimmaliyeti`; Logo üretim maliyeti (`PRDCOST` tabloları; varsayım) ve satılan mal maliyeti `OUTCOST` | CRM alanları biliniyor; `OUTCOST` 30.06.2026'ya kadar | CRM fiyat alanlarının doluluğu **ölçülecek** |
| Depo kapasitesi | — (M43'te kullanıcı girer) | Yok | M43'e bağlı |
| Satış tahmini (M3/M10/M11) | Baskı Öneri raporu, tahmin servisi | Canlı | M10 henüz yok |
| Plan değişikliği geçmişi | CRM `new_uretimplanlamatakvimi` (2.490) | Tablo biliniyor | Karta bağ kolonu **ölçülecek** (profilde görünmedi) |

## 7. Diğer modüllerle bağ

- Girdi: M12 (kartlar, gecikmeler, matbaa karnesi, teklifler), M10/M11 ve Baskı Öneri (planlanan adet), M43 (depo stoğu ve kapasite),
  M9 Fiyatlama (maliyet hedefi), M46 Bütçe (üretim bütçesi).
- Çıktı: M12 (yük dengeleme önerisi — insan uygular), M45/M46 finans (ödeme planı, maliyet eğilimi), M9 (birim maliyet eğrisi),
  M43 (gelecek depo girişleri), M29 İlk dağılım (kritik yol tarihleri).

## 8. Kısıtlar

- CRM ve Logo yalnız okunur. M12'nin portal tablolarına M52 yazmaz (yalnız okur, M12'nin uçlarından).
- Matbaa/kağıtçıya e-posta göndermek yok: taslak üretilir, gönderim insan.
- Tedarikçi borcu yaklaşık (FIFO): ekranda ve dışa aktarımda "Logo'da kapama yok, FIFO yaklaşımı" yazar; kesin borç gibi sunulmaz.
- Ekranda teknoloji adı yok; demo veri yok; kapasite girilmemişse "tanımlı değil" yazar.
- Sayı tavanı yok.
- Hukuki: matbaa sözleşmeleri ve bandrol/YAYFED uyumu M12'de; M52 yalnız sözleşme değerlendirme sunumu hazırlar.

## 9. Kapsam önerisi

**İlk sürüm**
- Baskı yükü: ay × matbaa (adet, iş sayısı, forma varsa), çakışma listesi, geçmiş 12 ayın aynı ayıyla karşılaştırma.
- Kağıt ihtiyacı: açık kartlardan ay × kağıt cinsi (kg).
- Tedarikçi borç ve ödeme: MATBAALAR/KAĞITÇILAR carileri (ölçüm sonrası) için bakiye, FIFO vadesi geçmiş, planlanan ödeme 30/60/90.
- Depo girişi olmuş – faturası görünmeyen baskılar (eşleme kuralı kullanıcıyla netleşince; o zamana kadar matbaa × ay toplamı karşılaştırması).

**Sonraki sürüm**
- Matbaa kapasitesi girişi ve yük dengeleme önerisi (K2), kağıt alım zamanı önerisi.
- Birim maliyet eğilimi (tip/cilt/sayfa kırılımı) ve yıllık matbaa değerlendirme sunumu (Word/PDF).
- Matbaa sipariş formu / teknik şartname taslağı (kart alanlarından), eskalasyon taslağı.

**Mevcut kodda yeniden kullanılacaklar**
- M12: `production.py` (kart okuma, firma/dönem bulma, `/printers`), `production_plan.py` (`printer_stats`, `parse_day`).
- `backend/semantic_bridge/management/` (5 dk önbellek, kaynak SQL paneli), `contracts_docs.py` (dış kütüphanesiz Word çıktısı).
- Katalogdaki FIFO/vade SQL'leri: `configs/semantic/knowledge/logo/knowledge/sql/{satici-borcu-yaslandirma-fifo.md, satici-borcu-vadesi-gecmis-fifo.md, planlanan-odeme-vadesi.md}`.
- `alerts.py`, `reports.py`, `SearchSelect.tsx`.

## 10. Uzmanlara sorulacak sorular

1. Matbaaların aylık kapasitesini (adet/forma/makine) biliyor musunuz; yoksa geçmiş en yüksek aylık iş referans alınabilir mi?
2. Kağıdı TİMAŞ mı satın alıp matbaaya veriyor, matbaa mı alıyor, yoksa ikisi karışık mı? Kağıt stoğu Logo'da tutuluyor mu?
3. Matbaa teklifleri bugün nerede (e-posta, Excel)? Geçmiş teklifler portala bir kez içe alınsın mı?
4. Matbaa faturası hangi alanla üretim kartına bağlanabilir (fatura açıklamasında URTN-… üretim no, stok kodu)?
5. Matbaalara ödeme vadesi ve ödeme günleri sabit mi (ör. 90 gün, ayın 15'i)?

## 11. Başarı ölçütü

- Aynı ay × matbaada eşik aşımı sayısı ve M12 gecikme oranı sezon öncesine göre düşüyor.
- Kağıt ihtiyacının en az 1 ay önceden görülme oranı (kartın kağıt alanı dolu ve baskı ayı ≥ 30 gün sonra).
- Faturası gelmemiş biten baskı sayısı ay sonunda sıfıra yakın.
- Finansın ödeme listesini hazırlama süresi (elle Excel → hazır liste) kısalıyor.
- Aylık baskı planı toplantısında ekranın kullanılması (erişim günlüğü).

## 12. Uzman gözüyle en iyi sistem

Rol: 15 yıllık yayınevi prodüksiyon/tedarik müdürü. Sektör pratiği (genel bilgi, TİMAŞ verisiyle doğrulanmadı): büyük yayınevleri
yıllık bir baskı planını aylık "matbaa slotları"na böler, okul ve fuar sezonundan önce kapasiteyi rezerve eder; kağıdı çerçeve
anlaşmayla ve fiyat endeksine göre alır; matbaayı teslim/kalite/fiyat karnesiyle yılda bir değerlendirir; dijital baskı ve talebe göre
baskı (POD) ile düşük adetli backlist'in stok riskini azaltır. TİMAŞ'ın kartında zaten "Matbu / Dijital / POD" baskı tipi var.

Mükemmel sistem: 6 aylık yük takvimi M12 kartlarından kendiliğinden dolu; aşırı yüklü ay kırmızı; kağıt ihtiyacı cins bazında ton
olarak; her matbaanın borcu, önümüzdeki ödemeleri ve karnesi tek sayfada; "bu işi Kasım'a kaydırırsam yayın ayı kaçar mı" sorusuna
kritik yol cevabı.

Bir iş günü:
- 08:30 Açılış: Ekim'de iki matbaada geçen yılın en yüksek ayının %30 üstü yük; 6 iş aynı haftada.
- 09:00 Çakışma listesinden 2 baskı tekrarı işini (öncelik "Normal") Kasım'a kaydırma önerisini onaylar; M12'de kartı değiştirmesi için not.
- 10:30 Kağıt: Kasım–Ocak ihtiyacı 60 gr kitap kâğıdı X ton; satın almaya ihtiyaç listesini gönderir.
- 13:00 Finans soruyor: "Y Matbaa'ya borç?" → tedarikçi sayfası: bakiye, FIFO vadesi geçmiş, 30 gün ödemesi, açık işler.
- 15:00 Zeki AI ile gecikmedeki 3 işin matbaaya eskalasyon e-posta taslağı; kendisi düzenleyip gönderir.
- 16:30 Çeyrek sonu için matbaa değerlendirme sunumunu indirir.

"Bunu görürsem hemen kullanırım":
1. Ay × matbaa yük ısı tablosu ve çakışma listesi.
2. Kağıt ihtiyacı cins × ay (ton).
3. Matbaa sayfası: iş + borç + ödeme + karne bir arada.

"Bunu yaparsanız kullanmam":
1. M12'deki kartla çelişen ikinci bir üretim kaydı (iki yerde veri girmek).
2. Kesin borç gibi gösterilen FIFO tahmini.
3. Kapasite bilmeden "kapasite aşıldı" demek.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (hangi tablo/görünüm/ölçü) | CRM (hangi varlık/alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Baskı yükü | `LG_<firma>_PRODORD`, `STFICHE` TRCODE 13 (gerçekleşen) | `new_UretimBase` (M12 `/cards` ile) | — | Rakam kart ve fiş sayımı |
| Çakışma ve dengeleme | — | Kart önceliği, bekleme durumu, yayın ayı | Öneri gerekçesi yazar ("öncelik Normal, yayın ayı Aralık, Kasım'a kayarsa kritik yol 12 gün pay bırakır") — sayılar kural hesabından | Karar hızlanır, hesap deterministik kalır |
| Kağıt ihtiyacı | Kağıt alış satırları TRCODE 1 (kağıtçı cariler) | `new_Uretim` kağıt alanları, `new_kagitcinsi`, `new_kagitebadi` | — | Sayısal toplam |
| Tedarikçi borç/ödeme | `CLFLINE` (320), `PAYTRANS` SIGN 1, `CLCARD.SPECODE` | AccountBase `new_ozelKod` (karşılaştırma) | Borç özeti metni (FIFO notu dahil) | Finansa okunur özet |
| Fatura ↔ kart eşleme | `INVOICE` (FICHENO, GENEXP açıklama), `STLINE` | `new_Uretim` (üretim no, stok kodu, matbaa) | Belirsiz eşleşmede aday seçimi (kapalı küme: aday kart id'leri + "hiçbiri") — tek token + olasılık; düşük marj insana | Serbest açıklama metnini karta bağlamak |
| Birim maliyet eğilimi | `OUTCOST`, üretim maliyet tabloları (varsayım) | `new_kesinlesenbaskifiyati`, `new_toplammaliyet`, `new_ciltlemesekli`, sayfa | Eğilim yorumu (2–3 cümle) | Yönetim özeti |
| Sipariş formu / şartname taslağı | — | Kart teknik alanları (ebat, kağıt, cilt, selofan, lak, adet) | Taslak metin | Matbaaya giden yazışma hızlanır; gönderim insanda |
| Doğal dil soru | Katalog ("satinalma", "ortalama_odeme_suresi", FIFO) | Katalog | Mevcut soru hattı | Yeni hat yok |

Model: `rt.llm_for("tedarik")`; gece eşleme işi `QueuedLlm(..., purpose="bg:tedarik")`. Ekranda yalnız "Zeki AI".

## 14. Kodlama planı (kodlayıcıya devir)

**Köprü dosyaları**
- `backend/semantic_bridge/supply.py` — yük, çakışma, kağıt, borç/ödeme, eşleme, eğilim hesabı; M12 kartlarını M12 modülünün iç
  fonksiyonundan okur (HTTP değil, `semantic_bridge.production` import) ; 5 dk önbellek.
- `backend/semantic_bridge/supply_sources.py` + `backend/semantic_bridge/supply_sql/`: `logo_tedarikci_cari.sql` (SPECODE
  MATBAALAR/KAĞITÇILAR), `logo_tedarikci_bakiye.sql`, `logo_tedarikci_fifo.sql` (katalog SQL'inden), `logo_planlanan_odeme.sql`,
  `logo_alis_satir.sql` (TRCODE 1/4, tedarikçi carileri), `logo_uretim_giris.sql` (TRCODE 13), `crm_kagit_ihtiyaci.sql`,
  `crm_kagit_cins.sql`, `crm_plan_degisiklik.sql`.
- `backend/semantic_bridge/supply_store.py`, `backend/semantic_bridge/supply_api.py`.

**Tablolar**
- `semantic_supply_capacity` (tenant_id, matbaa, ay NULL, kapasite_adet, kapasite_forma, not, giren, tarih).
- `semantic_supply_suggestions` (id, tenant_id, tur 'yuk'|'kagit'|'eskalasyon', kart_id NULL, payload_json, model_gerekce, durum, karar_veren, karar_tarihi).
- `semantic_supply_invoice_links` (tenant_id, logo_firma, invoice_ref, kart_id, yontem 'kural'|'zeki'|'elle', olasilik, onaylayan).
- `semantic_supply_supplier_map` (tenant_id, crm_matbaa_secenek, logo_cari_kodu) — CRM matbaa seçenek adı ↔ Logo cari.

**Uçlar** (`/api/v1/supply/*`): `GET meta`, `GET overview`, `GET load?aylar=6`, `GET conflicts`, `GET paper?aylar=3`,
`GET suppliers`, `GET suppliers/{cari}` (iş + borç + ödeme + karne), `GET payments?gun=30|60|90`, `GET unbilled`,
`GET cost-trend?kirilim=`, `GET suggestions`, `POST suggestions/{id}/decision`, `GET capacity`, `PUT capacity`,
`GET supplier-map`, `PUT supplier-map`, `POST drafts` (şartname/eskalasyon), `GET export/{liste}.xlsx`.

**Ekranlar** `src/canvas/supply/`: `SupplyHome.tsx` (/tedarik), `Load.tsx` (/tedarik/yuk), `Paper.tsx` (/tedarik/kagit),
`Suppliers.tsx` (/tedarik/tedarikciler), `Supplier.tsx` (/tedarik/tedarikci/:cari), `CostTrend.tsx` (/tedarik/maliyet),
`Capacity.tsx` (/tedarik/kapasite). Menü: çalışma alanı `lojistik`, bölüm «Tedarik»; M12 «Üretim yönetimi» Editoryal'de kalır,
iki ekran birbirine bağlantı verir. Kampüs: «Lojistik» modül kartında «Tedarik ve baskı».

**Yetki**: `sayfa:tedarik`, `sayfa:tedarik-yuk`, `sayfa:tedarik-kagit`, `sayfa:tedarik-tedarikciler`, `sayfa:tedarik-maliyet`;
`ozellik:tedarik.borc` (explicit), `ozellik:tedarik.maliyet` (explicit), `ozellik:tedarik.kapasite`, `ozellik:tedarik.oneri-karar`,
`ozellik:tedarik.eslesme` (fatura–kart eşleşmesini onaylama, explicit).

**Zamanlayıcı**: `timas-supply.timer` her gece 03:30 — fatura ↔ kart eşleme adayları (model arka plan), öneri üretimi; pazartesi
08:00 ödeme listesi `timas-reports.timer` ile. İlk kurulumda elle koşturulur.

**Kabul testleri (gerçek veri)**
1. Ay × matbaa iş sayısı ve adet toplamı = M12 `/cards` çıktısının aynı süzgeçle toplamı (fark 0) ve doğrudan CRM:
   `SELECT new_baskiayi, new_Matbaa, COUNT(*), SUM(new_kesinlesenbaskiadeti) FROM Timas_MSCRM.dbo.new_UretimBase WHERE statecode = 0 AND statuscode NOT IN (<Depo Girişi>, <İptal>) GROUP BY new_baskiayi, new_Matbaa` (durum kodları M12'deki `STAGES` ile aynı).
2. Matbaa/kağıtçı cari listesi: `SELECT CODE, DEFINITION_ FROM dbo.LG_411_CLCARD WHERE SPECODE IN ('MATBAALAR','KAĞITÇILAR')` — ekranla birebir; boşsa özel kod yazımı ölçülür, kural uydurulmaz.
3. Tedarikçi bakiyesi: 10 cari için ekran = `SELECT c.CODE, SUM(CASE WHEN f.SIGN = 1 THEN f.AMOUNT ELSE -f.AMOUNT END) FROM dbo.LG_411_01_CLFLINE f JOIN dbo.LG_411_CLCARD c ON c.LOGICALREF = f.CLIENTREF WHERE f.CANCELLED = 0 AND c.CODE IN (...) GROUP BY c.CODE` (alacak − borç; 320 yönü katalog ölçüsüyle aynı).
4. FIFO vadesi geçmiş borç = katalogdaki `satici-borcu-vadesi-gecmis-fifo` SQL'inin aynı carilerle çıktısı (fark 0).
5. 2026 üretimden giriş adedi (ay bazında) = Kural 20 "üretilen adet" (`STLINE TRCODE 13, IOCODE 1`) doğrudan SQL'i.
6. Kağıt ihtiyacı: 10 kartta ekrandaki kg = CRM kart alanlarının toplamı (`new_kapaktoplamkagitihtiyaci + new_icsayfabirtoplamkagitihtiyaci + …`, birim önce ölçülür).
7. Alış toplamı (tedarikçi carileri, 2026) = katalog "satinalma" ölçüsünün aynı cari süzgeciyle çıktısı.

**Bağımlılık**: **M12 önce bitmeli** (kart okuma fonksiyonu ve `/printers`); M43 depo kapasitesi sonraki sürüm. Tedarikçi borç/ödeme
sekmesi M12'den bağımsız → paralel başlanabilir.

**Tahmini büyüklük**: L (ilk sürüm yük + kağıt + borç ≈ 3 gün; eşleme ve öneriler ikinci sürümde M).
