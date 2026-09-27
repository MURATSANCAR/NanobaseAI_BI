# M30 — Saha Satış Yönetimi ve Tahsilat (BMT): kullanıcı ihtiyaç analizi

Durum: analiz (kod yok) · Tarih: 2026-09-28 · Kaynaklar: `specs/M30.txt`, `specs/M46.txt`, `specs/M59.txt`, `specs/M18.txt`, `veri_haritasi2.txt`,
`configs/semantic/knowledge/logo/knowledge/{rules/logo-erp.md, metrics, caveats, sql/vadesi-gecmis-*.md, sql/ortalama-tahsilat-suresi-dso.md}`,
`configs/semantic/knowledge/crm/OKUNUR-TABLOLAR.md` + `table_descriptions.json`, `docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`,
`docs/analiz/kampus-kisisel-ekran-crm-2026-09-15.md`, `docs/analiz/crm-eticaret-entegrasyon-2026-09-27.md` (§4: Mobilmax `MMX_*`),
`docs/audits/logo-missing-descriptions-live-2026-09-09.json` (`MMX_*`, `VW_MMX_*` kolonları), `docs/analiz/yetki-mekanizmasi-2026-09-27.md`,
`docs/GELISTIRME-GUNLUGU.md` (M46), `backend/semantic_bridge/{budget*.py, access.py, author_relations.py, people.py, alerts.py}`,
kullanıcı belleği (sales-are-invoiced-lines, system-of-record-logo, logo-155-frozen-copy, crm-systemuser-directory, bi-app-vm-55, no-tech-names-on-screens).

Sunucuya bağlanılmadı; «ölçülecek» işaretli sayılar kodlamadan önce ölçülür.
Otomasyon: **K1** tam otomatik · **K2** Zeki önerir, insan onaylar · **K3** Zeki analiz eder, karar insanın · **K4** yalnız insan (K3/K4 tanımı varsayım).

## 1. Modül ne işe yarar

Saha satış temsilcisinin (TİMAŞ'ta CRM'deki adıyla **BMT**) müşteri ziyaretini hazırlar ve tahsilatı önceliklendirir: her müşteri için son siparişler,
ödeme durumu, vadesi geçmiş alacak, hedef sapması ve önerilecek kitaplar tek bir «ziyaret brifingi»nde; gecikmiş alacaklar 30/60/90+ gün kovalarında
bir tahsilat öncelik listesinde. Yöneticiye temsilci ve bölge bazında hedef–gerçekleşme ve tahsilat raporu verir.
Bugünkü sorun (varsayım + veri): bilgi üç yerde — Logo (fatura, cari hareket, çek/senet), CRM (sipariş, risk limiti, tahsilat girişi, ziyaret kaydı) ve
Logo veritabanındaki saha uygulaması tabloları (`MMX_*`: ziyaret, konum, tahsilat, plasiyer hedefi). Temsilci ziyaret öncesi bunları birleştiremiyor;
Logo'da ödeme kapama kullanılmadığı için «hangi fatura ödenmedi» bilgisi kesin değil (caveats: FIFO yaklaşımı).

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| BMT (bölge saha temsilcisi; açılımı veride yok — sorulacak) | Satış sahası; CRM `SystemUserBase.new_bmt = 1`, `new_KullancTipi` 1 = BMT; `AccountBase.OwnerId` alanının etiketi «BMT»; `new_illerBase.new_musteritemsilcisi` (il → temsilci) | Her gün, günde birkaç ziyaret (varsayım) | **Telefon** (ağırlıklı) |
| Kurum temsilcisi | CRM `new_KullancTipi` 2 = Kurum Temsilcisi; `AccountBase.new_KurumunTemsilcisi` | Haftalık | Telefon + masaüstü |
| Satış müdürü / bölge müdürü (öncelik onayı, ödeme planı onayı, performans) | Satış | Günlük | Masaüstü + telefon |
| Tahsilat/finans onaycısı (CRM tahsilatını onaylar/reddeder) | Mali işler (TeamMembership 10); `new_tahsilatBase.new_onaylayanid` | Günlük | Masaüstü |
| Merkez müşteri temsilcisi | `AccountBase.new_MerkezMusteriTemsilcisi` | Günlük | Masaüstü |
| Genel müdür | Yönetim | Haftalık | Telefon |

Sayılar: CRM «Satış» ekibi 49 kişi (TeamMembership, 2026-09-15); kaçının BMT olduğu **ölçülecek** (`SystemUserBase.new_bmt = 1 AND IsDisabled = 0`).

## 3. Bugün bu iş nasıl yapılıyor

- **BMT — ziyaret:** CRM `new_etkinlikBase` ziyaret kaydı olarak tutuluyor: `new_ziyarettipi` 4 = «Cari Ziyareti», `new_ziyaretsekli`, gerçekleşen ziyaret
  tarihi `new_GercZiyTarihi`, `new_Tahsilatinfo` («Tahsilat Açıklaması»), sorumlu `new_sorumlusu`; etkinlik son 30 günde 594 kayıt değişmiş (canlı modül,
  2026-09-15). Paralel olarak Logo veritabanında bir saha uygulamasının tabloları var: `VW_MMX_411_ZIYARET` (başlık, içerik, görüşülen yetkili, tarih,
  enlem/boylam, cari, rota), `…_ZIYARET_DETAY/HAREKET`, `VW_411_MMX_CLIENT_LOCATION_DETAILS` (işlem konumu, cariye mesafe km), `MMX_PLASIYER_HEDEF`,
  `VW_MMX_411_01_COLLECTION_PAYMENT` (tahsilat/ödeme: tip, tutar, vade, satış elemanı, senkron durumu), `VW_MMX_APPOINTMENTS_CLCARD` (randevu).
  Hangisinin bugün kullanıldığı ve satır sayıları **ölçülecek** (sorulacak, bölüm 10).
- **BMT — tahsilat:** CRM `new_tahsilatBase` (14.089 kayıt; son 30 günde 55 değişiklik): tip Çek/Senet/POS/Mail Order/Nakit; nakit iletim Kargo/ATM/Elden;
  akış Onay Bekliyor → Onaylandı → **Logoya Aktarıldı** / Reddedildi; red sebebi «Şekil şartı eksikliği», «Makbuz ile evrak uyumsuzluğu», «Vade
  uyumsuzluğu». Tıkanma: reddedilen tahsilat temsilciye geri dönüyor (sıklığı ölçülecek).
- **BMT — sipariş:** CRM siparişi; risk aşımında sipariş «Risk Limit Onayı Bekliyor» / «Risk Bilgisi Bekleniyor» durumuna düşüyor, sebebi
  `new_risketakilmasebebi` (Açık hesap limiti / Çek-senet limiti / Toplam limit / Sorunlu müşteri). Limitler **CRM'de** tutuluyor: `AccountBase`
  `new_acikhesaprisklimiti`, `new_ceksenet`, `new_toplamrisklimiti`, riskler `new_acikhesapriski`, `new_ceksenetriski`, `new_toplamrisk`,
  `new_crmaciksiparisriski`; Logo `CLRNUMS.ACCRISKLIMIT` hiçbir caride dolu değil (caveats, 2026-09-18).
- **BMT — hazırlık:** Brifing yok; temsilci Logo ekstresini ve CRM kartını ayrı açıyor ya da merkeze soruyor (varsayım). Satış destek talebi
  `new_satisdestekBase.new_talepyapanbmt` (25 kayıt — az kullanılıyor).
- **Satış müdürü:** hedef: CRM `new_satishedefleriBase` (bölge × kitap × ay, `new_BMT` bağı), müşteri yıllık hedefi `AccountBase.new_CariYilHedef`,
  saha uygulamasında `MMX_PLASIYER_HEDEF`; hangisinin güncel olduğu bilinmiyor (doluluk ölçülecek). Rapor muhtemelen Excel (varsayım).

## 4. İhtiyaçlar ve acı noktaları

- **BMT:** (1) Ziyaret öncesi 1 dakikada okunur brifing: son 3 sipariş, son ödeme, vadesi geçmiş (FIFO), risk/limit doluluğu, karşılıksız/iade çek olayı,
  bu müşteride hedef açığı en büyük 5 kitap, yeni çıkan kitaplar (M29). (2) Bugünün ziyaret ve tahsilat öncelik listesi, haritada/rotada sıralı.
  (3) Reddedilen tahsilatlarının nedeniyle listesi. (4) Görüşme notunu telefondan 30 saniyede bırakmak. (5) Bağlantı zayıfken son brifingin açılması.
- **Satış müdürü:** (1) Temsilci × bölge hedef–gerçekleşme ve vadesi geçmiş alacak tek tabloda. (2) Ödeme planı önerisini onaylamak/reddetmek.
  (3) Riskli müşteriye ziyaret önceliği. (4) Haftalık saha raporu kendiliğinden.
- **Finans onaycısı:** (1) Onay bekleyen tahsilatların yaşı ve tutarı. (2) Red sebeplerinin temsilci bazında dağılımı (eğitim ihtiyacı).
- **Genel müdür:** tahsilat süresi (DSO yaklaşımı) ve 90+ gün alacak eğilimi.

## 5. Nasıl kullanmak isteyecekler

**Kullanıcı hikâyeleri**
- BMT olarak sabah telefonda bugünkü ziyaret listemi öncelik sırasıyla görmek istiyorum, çünkü hangi müşteriye önce gideceğimi bilmek istiyorum.
- BMT olarak müşterinin kapısında brifingi açmak istiyorum, çünkü ödeme durumunu ve önerilecek kitapları konuşmadan önce bilmeliyim.
- BMT olarak görüşme sonrası kısa not ve bir sonraki adımı bırakmak istiyorum, çünkü müdürüm ve merkez aynı bilgiyi görmeli.
- BMT olarak reddedilen tahsilatımı ve nedenini görmek istiyorum, çünkü müşteriye tekrar gitmem gerekiyor.
- Satış müdürü olarak Zeki'nin önerdiği ödeme planını onaylamak istiyorum, çünkü vade ve iskonto yetkisi bende.
- Satış müdürü olarak pazartesi temsilci bazında hedef ve tahsilat tablosunu görmek istiyorum, çünkü haftalık toplantıyı buna göre yapıyorum.

**Ana ekranlar ve akış**
- Telefon ilk açılış («Bugün»): ziyaret listesi (öncelik puanı, gerekçe çipleri: «90+ gün 42 bin ₺», «hedef açığı %35», «yeni kitap geldi»), üstte
  3 sayı: vadesi geçmiş toplam, onay bekleyen tahsilat, bu ay hedef oranı.
- Müşteri brifingi (tek sayfa, kaydırmalı): Ödeme · Sipariş · Hedef · Öneri · Notlar. «Zeki AI özeti» 3 cümle en üstte.
- Tahsilat öncelik listesi: kovalar 1–30 / 31–60 / 61–90 / 90+, müşteri, tutar, son ödeme, sipariş durumu (riske takılmış mı).
- Yönetici (masaüstü): temsilci tablosu + bölge haritası (il), ödeme planı onay kuyruğu.
- En sık 3 işlem: brifing aç (1 dokunuş), not bırak (2 dokunuş + metin/ses), bugünkü listeyi sırala/filtrele (1 dokunuş).

**Zeki AI'ya soracakları**
- «Bu hafta vadesi 60 günü geçen müşterilerim kimler?»
- «Karadeniz bölgesinde hedefin gerisinde kalan kitaplar hangileri?»
- «Bu müşteri geçen yıl bu dönemde ne almıştı?»
- «Geçen ay reddedilen tahsilatlarımın nedenleri neydi?»
- «Hangi müşterimin çeki bu yıl karşılıksız çıktı?»
- «Ortalama tahsilat süremiz bölgemde kaç gün?»
- «Bu müşteriye hangi yeni çıkan kitapları önermeliyim?»

**Otomasyon katmanı**
- K1: brifing verisinin gece hazırlanması, vadesi geçmiş/risk sinyallerinin hesaplanması, haftalık saha raporu.
- K2: ziyaret öncelik listesi (Zeki sıralar, BMT sırayı değiştirir; müdür bölge önceliğini onaylar), kitap/kampanya önerisi, ödeme planı önerisi (müdür onayı),
  ziyaret sonrası takip e-posta taslağı (BMT gönderir — portal göndermez).
- K3: bölge/müşteri risk analizi (M59 gelene kadar basit sinyaller), temsilci performans yorumu.
- K4: kredi limiti değişikliği, tahsilatın onayı (CRM'de finans), müşteriyle anlaşma.

**Bildirim/uyarı**
- BMT: sabah 07:45 günün listesi (portal içi; telefon bildirimi ikinci sürüm); tahsilatı reddedildiğinde (CRM durum değişimi, 15 dk gecikmeyle);
  müşterisinin çeki karşılıksız olaya düştüğünde; müşterisinin siparişi risk onayına takıldığında.
- Satış müdürü: ödeme planı onay bekliyor (anında); M46 sapma uyarısı bölgesindeki kitaplara düştüğünde (`/api/v1/budget/deviations`); pazartesi 08:00
  haftalık rapor e-postası.
- Finans onaycısı: 48 saatten eski onay bekleyen tahsilat (günlük özet).

**Onay ve yetki**
- `sayfa:saha`. BMT yalnız kendi carilerini görür (CRM `AccountBase.OwnerId` = kendi `SystemUserId`; AD hesabı → `SystemUserBase.DomainName`).
- `ozellik:saha.herkesinki` (kapsam: bütün temsilciler; müdür, finans, yönetim).
- `ozellik:saha.not` (ziyaret notu yazma), `ozellik:saha.odeme-plani-onay` (explicit), `ozellik:saha.oncelik-duzenle` (bölge önceliğini değiştirme).
- Performans raporu (temsilci kıyası) `ozellik:saha.performans` — explicit (kişisel performans verisi).

## 6. Veri

| Gereken veri | Kaynak | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Temsilci ↔ müşteri ataması | CRM `AccountBase.OwnerId` («BMT»), `new_BMTilveyaCari` (BMT İl / BMT Cari), `new_illerBase.new_musteritemsilcisi`; Logo `LG_411_SLSMAN`, `INVOICE.SALESMANREF`, `MMX_CLIENT.CLIENT_SLSMAN_REF` | alanlar var | Hangisi güncel ölçülecek; «BMT İl» ise il → temsilci tablosundan çözülür. Servis hesabı sahipliği (ör. «Timas CRM») süzülmeli |
| AD hesabı ↔ CRM kullanıcısı | `SystemUserBase.DomainName`, `ActiveDirectoryGuid` | `people.py` çözüyor | CRM'de olmayan temsilci için boş durum |
| Müşteri ↔ Logo cari | `AccountBase.new_logicalref` → `CLCARD.LOGICALREF`, `new_CariKodu` → `CLCARD.CODE` | %98,6 eşleşme (2026-09-09) | Firma kopyası (211/411) farkı; `CODE` ile eşleme daha güvenli olabilir — ölçülecek |
| Satış, iade, net ciro (müşteri × kitap × ay) | Logo `STLINE` faturalı satır (`INVOICEREF<>0`), `LINENET` | tanımlı ölçüler | Logo .155 donmuş (son fatura 2026-08-17) |
| Cari bakiye, vadesi geçmiş, yaşlandırma | Logo `CLFLINE` + `PAYTRANS` FIFO (sertifikalı SQL `vadesi-gecmis-yaslandirma-fifo.md`) | tanımlı, yaklaşık | Kapama yok → yaklaşık; ekranda «yaklaşık» yazılmalı |
| Tahsilat süresi | DSO yaklaşımı (`ortalama-tahsilat-suresi-dso.md`) | tanımlı | Gerçekleşen süre ölçülemez |
| Çek/senet olayları | Logo `CSCARD`, `CSTRANS` (Kural 12) | tanımlı | — |
| Risk limiti ve risk | CRM `AccountBase` limit/risk alanları; `new_siparisBase.new_anliklimit/new_anlikrisk`, durum 100000004 | alanlar var | Doluluk ve güncelleme sıklığı ölçülecek; Logo limitleri boş |
| Tahsilat girişi ve onay akışı | CRM `new_tahsilatBase` | 14.089 kayıt | «Logoya Aktarıldı» kaydının Logo'daki karşılığı (KSLINES/CSCARD/BNFLINE) eşlemesi ölçülecek |
| Ziyaret kaydı | CRM `new_etkinlikBase` (tip 4); saha uygulaması `VW_MMX_411_ZIYARET*` | tablolar var | Hangisi canlı, satır sayısı/son tarih ölçülecek; konum verisi KVKK |
| Hedef | M46 `GET /api/v1/budget/targets` (kitap); CRM `new_satishedefleriBase` (bölge×kitap×ay, `new_BMT`); `AccountBase.new_CariYilHedef`; `MMX_PLASIYER_HEDEF` | M46 main'de | **Temsilci/müşteri hedefi M46'da yok**; CRM/saha uygulaması hedeflerinin doluluğu ölçülecek |
| Bayi risk skoru | M59 | kodlanmadı | İlk sürüm kendi sinyalleri (vadesi geçmiş, karşılıksız olay, risk doluluğu, iade oranı) — puan değil, sinyal |
| Önerilecek kitaplar | M46 hedef açığı, M29 yeni gelenler, müşterinin geçmiş alımı, M18 föy | kısmen | Föy M18 kodlanmadı → kitap özeti CRM `new_kitapBase` |
| Müşteri başına kârlılık | Logo `LINENET − AMOUNT×OUTCOST` | tanımlı, iş teyidi bekliyor | 2026 satırlarının ~%20'si maliyetsiz; 30.06.2026 sonrası maliyetlendirilmemiş |
| Sektör ödeme vadesi benchmark | dış | yok | İlk sürümde yok |

## 7. Diğer modüllerle bağ

- Girdi: **M46** (`/api/v1/budget/targets`, `/api/v1/budget/deviations?module=M30` — kitap sapması bölgeye cari satışıyla dağıtılır), **M59** (risk skoru;
  gelince sinyallerin yerini alır), **M29** (bölgeye gelen yeni kitaplar), **M18** (föy, kampanya), **M31** (okul ziyaretinde bayi eşleştirmesi → bayinin
  brifingine «şu okullar sizden alacak»).
- Çıktı: **M46** (bölge/temsilci gerçekleşmesi — M46 bugün kitap bazlı), **M59** (ziyaret notları, ödeme planı sonuçları), **M31** (ortak ziyaret tablosu).

## 8. Kısıtlar

- **Sahadan erişim:** portal müşteri ağında çalışıyor (`http://192.168.0.55/timas/`, bellek bi-app-vm-55). Telefonla sahadan erişim (VPN mi, dışa açık
  güvenli adres mi) **BT kararı**; bu karar olmadan telefon senaryosu yalnız ofis Wi-Fi'ında çalışır. Girişte yalnız AD (demo/davet yok).
- **CRM ve Logo'ya yazma yok.** «Saha rapor ve tahsilat verileri → LOGO + M59 güncelleme» ilk sürümde yok: tahsilat girişi CRM'de/saha uygulamasında
  kalır; ziyaret notu köprünün kendi tablosunda. Takip e-postası taslaktır, portal göndermez (temsilci kendi e-postasından).
- Ekranda teknoloji adı yok (saha uygulamasının ürün adı dahil: ekranda «saha uygulaması»). Demo veri yok. Sayı tavanı yok (liste kesilmez).
- Logo verisinin bittiği gün her brifingde yazılır. Vade/yaşlandırma «yaklaşık (FIFO)» etiketiyle.
- **KVKK:** cari kişisel kolonları (TCKNO, telefon, e-posta, adres, IBAN) seçilmez; `VW_MMX_*` konum ve «görüşülen yetkili GSM» kolonları okunmaz;
  temsilci konum geçmişi (`CLIENT_LOCATION_DETAILS`) izleme amaçlı kullanılmaz (çalışan konumu kişisel veri; amaç sınırlaması — hukuk teyidi).
  Temsilci performans kıyası yalnız yetkili yöneticiye. Tahsilat kaydında vergi/TC no, çek no, hesap no gösterilmez.

## 9. Kapsam önerisi

- **İlk sürüm:** portföy (temsilcinin carileri); müşteri brifingi (Logo satış/ödeme/çek + CRM risk/sipariş durumu/tahsilat durumu + M46 kitap hedef açığı
  + M29 yeni gelenler); tahsilat öncelik listesi (FIFO kovaları); ziyaret öncelik listesi (K2, gerekçeli); ziyaret notu (köprü tablosu); onay bekleyen/
  reddedilen tahsilat görünümü; yönetici haftalık tablosu; ödeme planı önerisi + onay kaydı (yalnız kayıt).
- **Sonraki sürüm:** M59 risk puanı; telefon bildirimi; rota/harita sıralaması (il/ilçe düzeyi, konum geçmişi değil); çevrimdışı brifing önbelleği;
  CRM'e ziyaret/not aktarımı (yetki gelirse); temsilci hedefinin M46'ya eklenmesi.
- **Yeniden kullanılacaklar:** `author_relations.py` (randevu → görüşme notu, ton, sıradaki adım, gizli not deseni), `people.py` (AD ↔ CRM),
  `budget.py` `approved_targets()`, `budget_sources.py` (`runner`, firma/yıl), `alerts.py` (olay/uyarı), `reports.py` (planlı e-posta raporu),
  `board_excel.py`, `access.py`; sertifikalı FIFO ve DSO SQL'leri (`configs/semantic/knowledge/logo/knowledge/sql/`).

## 10. Uzmanlara sorulacak sorular

1. BMT'nin açılımı ne; kaç BMT var ve müşteri ataması nerede güncel tutuluyor (CRM sahibi mi, il tablosu mu, Logo satış elemanı mı)?
2. Saha uygulaması (Logo veritabanındaki `MMX_*` tabloları) hâlâ kullanılıyor mu; ziyaret ve tahsilat girişi CRM'de mi orada mı?
3. CRM'deki risk limitleri kim tarafından, ne sıklıkla güncelleniyor; «Toplam Risk» alanı Logo'dan mı besleniyor?
4. Vade uzatma / ödeme planı / ek iskonto yetki basamakları neler (`new_EkVade`, `new_Ekiskonto`, «Vade İskonto Onaylayan»)?
5. Temsilci performans raporu prim hesabına giriyor mu; kimler görebilir?

## 11. Başarı ölçütü

- Ziyaret öncesi hazırlık süresi (anket, önce/sonra) ve brifing açılma oranı (ziyaret notu olan ziyaretlerin kaçında brifing açılmış).
- 90+ gün vadesi geçmiş alacak payı (FIFO) — 3 ay eğilimi, pilot bölge vs diğerleri.
- Tahsilat red oranı ve «şekil şartı eksikliği» payı (CRM `new_TahsilatReddilmeSebebi`).
- Onay bekleyen tahsilatın ortalama yaşı.
- Bölge hedef gerçekleşme oranı (M46 kitap hedeflerinin bölge satışıyla).
- Kullanım: haftalık aktif BMT oranı; not bırakılan ziyaret sayısı.

## 12. Uzman gözüyle en iyi sistem

**Uzman:** 15 yıllık bölge satış şefi. Sektör uygulaması (genel bilgi, doğrulanmadı): iyi dağıtım şirketlerinin saha satış (SFA) uygulamaları temsilciye
günlük rota, müşteri kartı, açık bakiye, son siparişler ve «bu müşteride satılmayan ama benzer müşterilerde satan ürünler» listesini tek ekranda verir;
tahsilat kovaları ve söz verilen ödeme (promise-to-pay) takibi yapılır; yönetici ziyaret sıklığı × ciro × tahsilat ilişkisini görür. En iyiler temsilciye
«neden bu müşteri bugün» gerekçesini gösterir ve çevrimdışı çalışır.

**TİMAŞ için mükemmel sistem:** sabah telefonda sıralı liste; her müşteride tek ekran brifing (ödeme, risk, hedef açığı, yeni kitap, son not); görüşme
sonunda sesli/kısa not ve «söz verilen ödeme tarihi»; söz tutulmazsa ertesi gün listede üste çıkar; müdür haftalık tabloda temsilciyi değil müşteriyi
konuşur; tahsilat reddi aynı gün temsilcide.

**Bir iş günü:** 07:45 «Bugün» ekranı: 6 müşteri; 1. sırada Trabzon'da bir kitapçı (90+ gün 42 bin ₺, çek iade olayı, yeni çıkan 3 kitap). Kapıda brifingi
açar; Zeki özeti: «Son ödeme 71 gün önce; bu yıl alımı geçen yılın %60'ı; çocuk kitaplarında hedef açığı büyük.» Görüşür, 20 bin ₺ çek alır (CRM/saha
uygulamasında tahsilat girer), portalda not: «Kalanı 15 Ekim sözü». Öğleden sonra 3 ziyaret daha. 18:00 reddedilen bir tahsilatının «vade uyumsuzluğu»
nedeniyle geri döndüğünü görür, yarın listeye eklenmiş.

**«Bunu görürsem hemen kullanırım»:** (1) Müşteri kapısında 1 dakikada okunan brifing — ödeme + hedef açığı + önerilecek 5 kitap. (2) Söz verilen ödeme
takibi ve tutulmayınca otomatik öncelik. (3) Reddedilen tahsilatın nedeniyle aynı gün bildirimi.

**«Bunu yaparsanız kullanmam»:** (1) Konumumu izleyen, kaç km gittiğimi müdüre raporlayan ekran. (2) CRM'de zaten girdiğim tahsilatı portalda tekrar
girmemi istemek. (3) Rakamı merkezdeki raporla tutmayan bakiye (FIFO yaklaşımı olduğu yazılmadan).

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (tablo/ölçü) | CRM (varlık/alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Portföy | `CLCARD` (CODE, DEFINITION_, CITY, SPECODE2), `SLSMAN` | `AccountBase.OwnerId`, `new_logicalref`, `new_CariKodu`, `new_BMTilveyaCari`, `new_illerBase.new_musteritemsilcisi`; `SystemUserBase.DomainName` | — | Atama CRM'de; cari Logo'da |
| Satış/iade özeti | `STLINE` faturalı satır, `LINENET`, `AMOUNT`, TRCODE 7/8/9 − 2/3 | — | — | Kayıt sistemi Logo |
| Bakiye, vadesi geçmiş | `CLFLINE`, `PAYTRANS` (FIFO sertifikalı SQL) | — | — | Sertifikalı, yaklaşık |
| Çek olayları | `CSCARD`, `CSTRANS` STATUS 11, 5/7 (Kural 12) | — | — | Olay Logo'da |
| Risk/limit | — | `AccountBase` limit/risk alanları; `new_siparisBase` durum 100000004/100000016, `new_risketakilmasebebi` | — | Limit CRM'de (Logo'da boş) |
| Tahsilat durumu | (ikinci sürüm: `KSLINES`, `BNFLINE`, `CSCARD` eşlemesi) | `new_tahsilatBase` statuscode, tip, red sebebi | Red nedeni açıklama metninin sınıflanması (kapalı küme: şekil/evrak/vade/diğer — tek token + olasılık) yalnız serbest metin `new_reddilmesebebi` doluysa | Serbest metin sınıflama |
| Hedef açığı | faturalı satış (bölge = temsilcinin carileri) | — (M46 köprü) | — | Rakam M46 + Logo |
| Öncelik puanı | yukarıdaki sinyaller | yukarıdaki sinyaller | Puan **kural** ile (ağırlıklar ekranda); model yalnız 1 cümle gerekçe yazar | Denetlenebilir öncelik |
| Brifing özeti | tüm rakamlar SQL'den | son notlar (köprü), sipariş durumu | 3 cümle Türkçe özet; rakamları verilen JSON'dan aynen kullanır, yeni rakam yazmaz | Okunabilirlik |
| Kitap önerisi | müşterinin 24 ay alımı, benzer müşterilerin alımı (aynı kanal/il) | `new_kitapBase` özet, hedef yaş | Aday listesinden «bu müşteriye uygun mu» sınıflaması + gerekçe | Eşleştirme |
| Takip e-postası taslağı | — | — | Taslak metin (temsilci düzenler, kendi gönderir) | Taslak metin |
| Ödeme planı önerisi | bakiye, vade planı | `new_vadegun`, `new_EkVade`, `new_TahsilatTipi` | Şablon metni; taksit sayısı/tutarı **kural** ile | Rakam modelden gelmez |
| Doğal dil soru | katalog ölçüleri | — | `/api/v1/ask` hattı (temsilci kapsamı süzgeçli — Aşama C veri kapsamı) | Aynı hat |

Model çağrısı: `rt.llm_for("saha")`; toplu gece brifing özetleri `/api/v1/llm/jobs` üzerinden kuyrukta; `LlmClient` doğrudan kurulmaz.

## 14. Kodlama planı (kodlayıcıya devir)

**Köprü dosyaları** — `backend/semantic_bridge/field_sales.py` (tablolar, portföy, sinyaller, öncelik, brifing, ödeme planı onayı, rapor),
`field_sales_sources.py` (Logo/CRM SQL; `budget_sources.runner`), `field_sales_api.py` (`register(...)`, `app.py`'ye iki satır).

**Tablolar**
- `semantic_field_portfolio` (tenant_id, systemuser_id, ad_hesap, crm_account_id, logo_clientref, logo_code, unvan, il, kanal, atama_kaynagi `owner|il|slsman`, asof)
- `semantic_field_signals` (logo_clientref, asof, bakiye, vadesi_gecmis, k_1_30, k_31_60, k_61_90, k_90p, son_odeme_tarihi, karsiliksiz_olay_12ay,
  risk_toplam, limit_toplam, risk_doluluk, siparis_riskte, ytd_net_ciro, gecen_yil_ayni_donem, iade_orani, hedef_acigi, oncelik_puani, gerekce_json)
- `semantic_field_briefs` (logo_clientref, asof, ozet_metin, oneri_kitaplar_json, model_is_kimligi)
- `semantic_saha_ziyaret` — **M30/M31 ortak ziyaret tablosu** (hangisi önce kodlanırsa açar): id, tenant_id, tur `cari|okul|kurum`, hedef_kimlik
  (logo_clientref / ziyaret_yeri_id / crm_account_id), sahip (AD hesabı), planlanan, gerceklesen, durum `planlandi|yapildi|iptal`, not, ton, sonraki_adim,
  sonraki_tarih, soz_odeme_tarihi, soz_odeme_tutari, gizli, eslik_eden_bayi (logo_clientref), olusturma/guncelleme
- `semantic_field_payment_plans` (id, logo_clientref, oneren, taksitler_json, gerekce, durum `taslak|onayda|onayli|reddedildi`, onaylayan, zaman)
- Yazmalar `semantic_audit`'e (`saha_ziyaret`, `saha_odeme_plani`).

**Uçlar** (`/api/v1/field/*`)
- `GET /today` (temsilcinin sıralı listesi) · `GET /portfolio?temsilci=` · `GET /customers/{clientref}/brief`
- `GET /collections?kova=&temsilci=` · `GET /collections/crm?durum=onay-bekliyor|reddedildi`
- `POST /visits` · `PATCH /visits/{id}` · `GET /visits?musteri=&tarih=`
- `POST /payment-plans` · `POST /payment-plans/{id}/submit|approve|reject`
- `GET /report/weekly?hafta=` · `GET /report/weekly.xlsx`
- `POST /run-due` (SYSTEM)

**Ekranlar** — `src/canvas/field/` (`TodayScreen.tsx` telefon öncelikli, `CustomerBrief.tsx`, `CollectionsTab.tsx`, `ManagerReport.tsx`, `VisitNoteSheet.tsx`, `api.ts`).
Rota `/timas/saha` (+ `/saha/musteri/:ref`). Menü: `satis` alanı, `{ id: 'saha', label: 'Saha ve tahsilat', section: 'Saha' }`. Kampüs: `ModulesMenu.tsx`
→ `M30: '/saha'`; Kampüs selam çipi «bugünkü ziyaretlerim» (BMT'ye). Telefon alt çubuğunda ilk sekme bu ekran olabilir (kullanıcı tercihi `prefs`).

**Yetki** — `sayfa:saha`; `ozellik:saha.herkesinki` (kapsam), `ozellik:saha.not`, `ozellik:saha.oncelik-duzenle`, `ozellik:saha.odeme-plani-onay` (**explicit**),
`ozellik:saha.performans` (**explicit**), export `ozellik:veri.disa-aktar`. `access.py` `RULES`: `("/api/v1/field/run-due", SYSTEM)`,
`("/api/v1/field/", frozenset({page("saha"), page("okul-tanitim")}))` (ortak ziyaret uçları); M46 `targets`/`deviations` satırlarına `page("saha")`.
Kapsam denetimi uç içinde: `ozellik:saha.herkesinki` yoksa her sorgu `semantic_field_portfolio.ad_hesap = oturum` ile süzülür (Zeki AI soru hattında da — Aşama C).

**Zamanlayıcı** — `scripts/server/timas-field.{service,timer}`: her gün 06:30 `run-due` (portföy, sinyaller, öncelik, brifing özetleri kuyruğa);
15 dakikada bir hafif tur (CRM tahsilat/sipariş durum değişimi → bildirim); pazartesi 07:30 haftalık rapor e-postası (`reports.py` yolu). İlk kez elle koşturulur.

**Kabul testleri** (gerçek Logo + CRM, doğrudan SQL referansı)
1. Vadesi geçmiş (FIFO): 5 örnek carinin kova tutarları = sertifikalı `vadesi-gecmis-yaslandirma-fifo.md` SQL'inin `WHERE C.LOGICALREF = @ref` süzgeçli sonucu (kuruş).
2. YTD net ciro: brifingdeki tutar = `SELECT SUM(CASE WHEN TRCODE IN (7,8,9) THEN LINENET ELSE -LINENET END) FROM LG_411_01_STLINE WHERE CLIENTREF = @ref
   AND LINETYPE = 0 AND CANCELLED = 0 AND INVOICEREF <> 0 AND TRCODE IN (2,3,7,8,9)`.
3. Portföy: temsilcinin cari sayısı = `SELECT COUNT(*) FROM Timas_MSCRM.dbo.AccountBase a JOIN Timas_MSCRM.dbo.SystemUserBase u ON u.SystemUserId = a.OwnerId
   WHERE u.DomainName = 'timas\<hesap>' AND a.StateCode = 0` (+ «BMT İl» carileri il tablosundan; kural ekranda yazılı).
4. CRM tahsilat: onay bekleyen = `SELECT COUNT(*), SUM(new_tutar) FROM Timas_MSCRM.dbo.new_tahsilatBase WHERE statecode = 0 AND statuscode = 100000000
   AND OwnerId = @u`; reddedilen son 30 gün aynı şekilde `statuscode = 100000002`.
5. Karşılıksız olay: brifingdeki bayrak = `EXISTS (SELECT 1 FROM LG_411_01_CSTRANS T WHERE T.STATUS = 11 AND T.DEVIR = 0 AND T.CANCELLED = 0
   AND T.DATE_ >= DATEADD(month, -12, @asof) AND T.CSREF IN (SELECT G.CSREF FROM LG_411_01_CSTRANS G WHERE G.CARDREF = @ref AND G.STATUS = 1 AND G.CANCELLED = 0))`
   — çekin müşterisi portföye giriş hareketinin carisidir (`CSCARD`'da cari kolonu yok; `CSTRANS.CARDREF` anlamı kodlamada `configs/schemas/logo-ldds.json`'dan doğrulanır;
   `DOC IN (1,2)` müşteri çeki/senedi süzgeci `CSCARD` üzerinde).
6. Risk doluluğu = `new_toplamrisk / NULLIF(new_toplamrisklimiti, 0)` CRM `AccountBase` (5 cari).
7. Hedef açığı: kitap hedefi `/api/v1/budget/targets` ile birebir; bölge dağılımı kuralı (cari payı × kitap hedefi) ekranda yazılı ve toplamı kitap hedefine eşit.
8. Kapsam: BMT hesabıyla başka temsilcinin carisine `GET /customers/{ref}/brief` 403.

**M59 ile çakışma (kodlamadan önce karar):** M59 analizi (`M59-bayi-risk-performans.md`) aynı cari için yaşlandırma, not ve «ziyaret brifingi»
(`/api/v1/dealers/{cari}`, `/{cari}/aging`, `POST /{cari}/brief`, `/{cari}/notes`) öneriyor. Öneri: **risk, yaşlandırma ve limit önerisi M59'un**
(tek kaynak); M30 brifingi bu uçları okur. M59 henüz yoksa M30 kendi `semantic_field_signals` tablosuyla başlar ve M59 gelince okumayı ona çevirir
(aynı FIFO SQL'i, sonuç değişmez). Ziyaret/görüşme notu tek tablo: `semantic_saha_ziyaret` (`tur='cari'`); M59 notları ayrı tablo açmaz, bunu okur/yazar.

**Bağımlılık** — M46 bitti. M59 beklenmez (sinyallerle başlar). M29 ile paralel (yeni gelenler bölümü M29 hazır olunca açılır). M31 ile ziyaret tablosu ortak.
Telefondan sahadan erişim BT kararı — kod bekletmez ama pilot için şart.

**Büyüklük** — L (3+ gün).
