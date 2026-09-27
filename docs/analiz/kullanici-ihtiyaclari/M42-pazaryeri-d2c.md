# M42 — Diğer Pazar Yerleri ve D2C Yönetimi: kullanıcı ihtiyaç analizi

Durum: analiz (kod yok) · Tarih: 2026-09-28 · Kaynaklar: `specs/M42.txt`, `specs/M34.txt`, `specs/M35.txt`, `specs/M40.txt`,
`specs/E_Ticaret_Müşteri_Yönetimi_Ent.txt`, `ZEKİ_Veri_Haritasi2.html` (M42, M34 satırları), `docs/analiz/crm-eticaret-entegrasyon-2026-09-27.md`,
`docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`, `configs/semantic/knowledge/logo/knowledge/{rules/logo-erp.md, rules/conventions.md, metrics/logo-timas.md, glossary/logo-timas.md, sql/2026-y-l-nda-kitapci-e-ticaret-ve-dagitici-kanallar-i-in-ay.md}`,
`configs/semantic/knowledge/crm/OKUNUR-TABLOLAR.md` (sipariş tipi, geliş kanalı, cari kanal alanları), `backend/semantic_bridge/seo_geo/connections.py`,
`PROJECT-MEMORY.md` (SEO & GEO), bellek: `tsoft-no-write`, `crm-tsoft-no-push-integration`, `seo-geo-module`, `sales-are-invoiced-lines`,
`logo-155-frozen-copy`, `no-tech-names-on-screens`, `customer-vm-web-watch-off`. Sunucuya bağlanılmadı; yeni ölçüm yok.

## 1. Modül ne işe yarar

İş tanımı (M42): Hepsiburada, D&R, idefix ve timas.com.tr (D2C) kanallarını birlikte yönetmek — kanal bazında stok/fiyat dengeleme,
sipariş birleştirme, kargo optimizasyonu (K1); timas.com.tr dönüşüm iyileştirme, sadakat programı, D2C'ye özel ürün/kampanya,
müşteri verisi zenginleştirme (K2). Çıktılar: çok kanal panosu (kanal satış ve kâr karşılaştırması, stok dağılımı), D2C analizi
(dönüşüm hunisi, D2C ve pazar yeri müşteri değeri), büyüme planı.

TİMAŞ'ın bugünkü durumu (kanıtla, `crm-eticaret-entegrasyon-2026-09-27.md`): CRM'de **hiçbir pazar yeri API entegrasyonu izi yok**.
Pazar yerleri CRM'de **toptan müşteri (cari)** olarak duruyor: KİTAPYURDU (son 180 günde 227 sipariş), D-MARKET/Hepsiburada (34),
Amazon Turkey (iki kart), Amazon Kindle US, Amazon Seller Central; firma kanalı "E-Ticaret". Logo'da kanal = cari özel kodu 2
(`SPECODE2 = 'E-TICARET'`). timas.com.tr T-soft üzerinde; **T-soft dönemi siparişleri CRM'e gelmiyor** (son 12 ayda 0). Yani
bugün "çok kanal" görünümü ancak Logo faturasından (cari bazında) kurulabilir; D2C sipariş ve davranış verisi portala hiç akmıyor.

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| E-ticaret / dijital satış müdürü (timas.com.tr + pazar yeri hesapları) | Ayrı ekip kanıtı yok (varsayım); CRM'de firma kanalı "E-Ticaret" ve satış hedefi bölgeleri "Hepsiburada, Kitapyurdu, B2C" var | Her gün | Masaüstü |
| Kanal / anahtar hesap yöneticisi (Kitapyurdu, Hepsiburada, D&R, idefix toptan ilişki) | Satış (49 kişi, TeamMembership) | Haftalık | Masaüstü + telefon |
| Pazarlama (sadakat, D2C kampanya) | Pazarlama (35) | Haftalık / kampanya dönemi | Masaüstü |
| Finans (kanal kârlılığı, iskonto) | Mali İşler (10) | Aylık | Masaüstü |
| Genel müdür / satış direktörü | — | Aylık | Telefon (varsayım) |

## 3. Bugün bu iş nasıl yapılıyor

- **E-ticaret müdürü:** timas.com.tr ürün, fiyat ve siparişleri T-soft panelinde (varsayım: stok/fiyat Logo'dan besleniyor — BT'ye
  soru; CRM `new_webstok` hiç dolu değil, stok CRM'den gitmiyor). Ürün içeriği CRM görünümlerinden bir kez yüklenmiş olabilir
  (`Tsoft_KitapDetay`, 2022-12). Analitik (GA4) ve Merchant Center erişimi portalda **yok**; Search Console'da servis hesabı sahip değil.
- **Kanal yöneticisi:** pazar yeri/online kitapçılar TİMAŞ'tan toptan alıyor; sipariş CRM'de (sipariş tipi seçenekleri arasında
  "Pazaryeri" (9) ve "Amazon Konsinye" (14) var; dağılımı ölçülmedi) ve B2B portalı kitapsiparis.com.tr üzerinden (son 90 günde 4.026
  sipariş, bütün B2B kanalları). Fatura Logo'da. Kanalın **son tüketiciye sattığı fiyat ve adet** (sell-through) TİMAŞ'ta yok.
- **Finans:** kanal bazında net ciro ve brüt kâr katalogda tanımlı ve soru hattında çalışıyor (`kanal_net_ciro`, kanal brüt kâr
  SQL çifti). Kanal başına kargo, komisyon, reklam gibi maliyetler Logo gider hesaplarında ayrıştırılmış mı bilinmiyor.
- **Tıkanma (varsayım):** hangi kanalın gerçekten kârlı olduğu (iskonto + iade + kargo sonrası) tek ekranda yok; D2C'nin müşteri
  değeri ölçülemiyor çünkü sipariş verisi T-soft'ta kalıyor.

## 4. İhtiyaçlar ve acı noktaları

**E-ticaret müdürü**
1. timas.com.tr siparişleri, sepet büyüklüğü, en çok satanlar, iade — T-soft'tan salt okunur, günlük.
2. Aynı kitabın kanallardaki fiyat/stok durumu: sitede stokta yok görünüp depoda olan, pazar yerinde TİMAŞ'tan ucuz satılan.
3. D2C müşterisinin tekrar alım oranı ve değeri (KVKK sınırında, anonim düzeyde).

**Kanal yöneticisi**
1. Cari (kanal) bazında aylık net ciro, adet, iskonto oranı, iade oranı, ortalama vade — yıl karşılaştırmalı.
2. Kanalın en çok aldığı ve iade ettiği kitaplar; kanal bazında bekleyen sipariş.
3. Satış hedefi (CRM `new_satishedefleri`, bölge = kanal) ↔ gerçekleşen.

**Pazarlama**
1. D2C'ye özel kampanya ve sadakat için hedef kitle ve geçmiş kampanya sonucu (M35 ile ortak).

**Finans**
1. Kanal kârlılığı: net ciro − satılan mal maliyeti − iskonto − iade − (bilinen) kargo; maliyetsiz satır ayrıca sayılır.

## 5. Nasıl kullanmak isteyecekler

**Kullanıcı hikâyeleri**
- Kanal yöneticisi olarak Kitapyurdu, Hepsiburada ve D&R'ın bu yıl aylık net cirosunu ve iade oranını yan yana görmek istiyorum, çünkü yıllık iskonto görüşmesine hazırlanırım.
- Kanal yöneticisi olarak bir kanalın son 90 günde en çok iade ettiği kitapları görmek istiyorum, çünkü sevkiyat adedini düzeltirim.
- E-ticaret müdürü olarak timas.com.tr'de "stokta yok" görünen ama depoda olan kitapları görmek istiyorum, çünkü kaçan satışı kurtarırım.
- E-ticaret müdürü olarak sitenin günlük sipariş ve ciro eğrisini kampanya günleriyle birlikte görmek istiyorum, çünkü kampanya etkisini ölçerim.
- Finans uzmanı olarak kanal bazında brüt kâr marjını iskonto ve iade sonrası görmek istiyorum, çünkü hangi kanala ne kadar iskonto verilebileceğini hesaplarım.
- Genel müdür olarak D2C'nin toplam cirodaki payını ve büyümesini telefonda görmek istiyorum.

**Ana ekranlar ve akış**
- Açılış (`/kanallar`): kanal kartları (E-ticaret carileri + timas.com.tr) — bu ay net ciro, geçen yıl aynı ay, iade oranı, iskonto oranı,
  brüt marj; veri günü (Logo son fatura) üstte.
- Kanal detayı: aylık eğri, en çok satan/iade edilen kitaplar, bekleyen sipariş, hedef ↔ gerçekleşen.
- timas.com.tr (D2C) sekmesi: günlük sipariş/ciro, en çok satanlar, stok-görünürlük farkı; analitik bağlanırsa huni.
- Fiyat/stok tutarlılığı: kitap × kanal (T-soft fiyatı, Logo liste fiyatı, CRM KDV dahil fiyat; stok görünür mü).
- En sık 3 işlem: kanal kıyasını açmak (1 tık), kanal detayından iade listesini Excel'e almak (3 tık), bir kitabın kanal dağılımını sormak (2 tık).

**Zeki AI'ya soracakları örnek sorular**
- "Bu yıl e-ticaret kanalında en çok ciro yapan 10 cari ve geçen yıla göre değişim?"
- "Hepsiburada'nın iade oranı son 6 ayda nasıl?"
- "Kitapyurdu'na geçen ay en çok hangi yayınevinin kitapları gitti?"
- "timas.com.tr'de dün kaç sipariş vardı?" (T-soft okunuyorsa)
- "Sitede stokta yok görünen ama depoda 100'den fazla olan kitaplar?"
- "E-ticaret kanalının brüt kâr marjı kitapçı kanalından ne kadar farklı?"

**Otomasyon katmanı**
- K1 (tam otomatik, **salt okuma**): kanal ciro/iade/iskonto/marj hesabı, T-soft sipariş ve ürün okuma, fiyat/stok tutarsızlık listesi.
  İş tanımındaki "kanal senkronizasyonu" (platformlara stok/fiyat gönderme) bu modülde **yok**: T-soft'a yazma yasak; pazar yerlerine
  yazma kullanıcı kararı gerektirir (açık soru, §10).
- K2 (Zeki önerir, insan onaylar): kanal bazında iskonto/fiyat önerisi (gerekçeli), D2C'ye özel kampanya ve sadakat programı taslağı,
  kampanya e-posta metin taslağı. Onay portal kaydıdır; hiçbir platforma gönderilmez.
- K3: kanal sözleşmesi ve iskonto oranı kararı.
- K4: sadakat programının hukuki/KVKK tasarımı.

**Bildirim / uyarı**
- E-ticaret müdürü: stokta-yok/depoda-var farkı ≥ eşik (günlük e-posta 09:00), site siparişi günlük ortalamanın altına düşerse.
- Kanal yöneticisi: kanal iade oranı eşiği aşarsa (haftalık).
- Yönetim: aylık kanal karnesi (planlı rapor, ayın 2'si).

**Onay ve yetki (öneri)**
- `sayfa:kanallar` — e-ticaret, satış, pazarlama, finans, yönetim.
- `sayfa:d2c` — e-ticaret, pazarlama, yönetim.
- `ozellik:kanal.marj` (brüt kâr, maliyet) — açıkça verilir (finans, yönetim, satış direktörü).
- `ozellik:kanal.oneri-karar` (fiyat/iskonto/kampanya önerisi onayı) — açıkça verilir.
- `ozellik:d2c.musteri` (anonimleştirilmiş müşteri kohortları) — açıkça verilir (KVKK).

## 6. Veri

| Gereken veri | Kaynak (Logo / CRM / T-soft / kullanıcı girer / dış) | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Kanal net ciro, adet, iade | Logo `STLINE` faturalı satır (`INVOICEREF <> 0`), TRCODE 7,8,9 − 2,3, `LINENET`; `CLCARD.SPECODE2` | `kanal_net_ciro` ölçüsü ve SQL çifti var | .155 donmuş (2026-08-17) |
| Pazar yeri ↔ cari eşlemesi | Logo `CLCARD` (CODE, DEFINITION_, SPECODE2 = 'E-TICARET'), CRM `AccountBase.new_logicalref`, `new_FirmaKanal`, `new_cariozelKod2` | Kanal kodu var; CRM–Logo cari bağı %98,6 | Hangi cari hangi platform (Hepsiburada = D-MARKET, Trendyol = ?) **ölçülecek** + kullanıcı onayı |
| Brüt kâr | `LINENET − AMOUNT × OUTCOST` | Tanımlı; maliyet 30.06.2026'ya kadar, 2026 satırlarının %20'si maliyetsiz | Maliyetsiz satır sayısı yazılır |
| İskonto | `STLINE` LINETYPE 2, `iskonto_yuku` ölçüsü | Tanımlı | Yok |
| Kanal siparişleri / bekleyen | CRM `new_siparisBase` (`new_siparistipi` 9 Pazaryeri, 14 Amazon Konsinye; `new_geliskanaliid`), Logo `ORFICHE` TRCODE 1 | Alanlar biliniyor | Tip dağılımı **ölçülecek** |
| Satış hedefi (kanal/bölge) | CRM `new_satishedefleriBase` (bölge: D&R, Hepsiburada, Kitapyurdu, B2C…; 12 ay sütun) | Tanımlı (Kural C-hedef) | Bölge ↔ cari eşlemesi **ölçülecek** |
| timas.com.tr ürünleri (fiyat, stok görünürlüğü) | T-soft REST1 `product/get` (salt okunur, `seo_geo/connections.py`) | SEO modülü gece okuyor (6.578 aktif ürün) | Stok/fiyat alanının güncelliği **ölçülecek** |
| timas.com.tr siparişleri | T-soft REST1 sipariş okuma yöntemi (`order/get…`; varsayım — konsol kataloğunda doğrulanacak; `READ_ONLY` deseni `get*`'e izin verir) | **Hiç okunmadı** | En kritik boşluk; KVKK kapsamı |
| D2C davranış (huni) | GA4 / site analitiği | Erişim **yok** | Müşteri yetki vermeli |
| D2C'nin Logo'daki izi | Logo fatura carisi (tek "internet/nihai müşteri" carisi mi? CRM `new_cariozelKod2` INTERNET, NiHAi seçenekleri var) | — | **Ölçülecek** |
| Hepsiburada/idefix/D&R mağaza verisi (satıcı olarak) | Platform API'leri | TİMAŞ'ın kendi mağazası olup olmadığı **bilinmiyor** | Soru 1 |
| Rakip fiyatı | Kazıma yasak (müşteride web taraması kapalı) | — | Yalnız resmî API ile |

## 7. Diğer modüllerle bağ

- Girdi: M43 stok (kanal stok görünürlüğü), M35 kampanya takvimi, M40 Trendyol ve M41 Amazon (aynı kanal panosuna katılır),
  M46 hedefler, M25 SEO (ürün sayfası sorunu → dönüşüm), M44 kargo maliyeti, M38/M37 müşteri/topluluk.
- Çıktı: M35 (kanal bazında kampanya önerisi), M9 Fiyatlama (kanal iskonto etkisi), M45 finans, M59 bayi/kanal risk (iade, vade),
  M24 bülten (D2C e-posta).
- M34 E-Ticaret ve Platform Yönetimi ile örtüşme: M34'ün "platform dashboard"u bu modülün çok kanal panosuyla aynı veri; tek pano
  kurulup M34/M40/M41/M42 sekmeleri olarak ayrılması önerilir (tekrar yok).

## 8. Kısıtlar

- **T-soft'a yazma yasak** (ürün, fiyat, stok, kampanya hiçbir şey gönderilmez). Pazar yerlerine yazma kullanıcı kararı; bu analizde
  yalnız okuma önerilir.
- CRM'e yazma yok; öneri/onay köprünün tablolarında (`semantic_channel_*`).
- Müşteride web taraması kapalı: rakip fiyatı/bestseller kazıma yok.
- KVKK: T-soft siparişindeki ad, adres, telefon, e-posta portala **alınmaz** ya da alınırsa tek yönlü özetlenir (müşteri anahtarı
  karma, yalnız kohort); sadakat programı için açık rıza ve aydınlatma metni müşteri (TİMAŞ hukuk) kararıdır.
- Ekranda teknoloji adı yok (T-soft, Hepsiburada gibi müşteri platform adları yazılabilir — SEO modülündeki karar); demo veri yok;
  sayı tavanı yok.

## 9. Kapsam önerisi

**İlk sürüm (Logo + CRM ile, dış bağlantı gerektirmeden)**
- Kanal karnesi: E-TICARET carileri tek tek + kanal toplamı; net ciro, adet, iade, iskonto, brüt marj (maliyetli kısım), yıl karşılaştırma.
- Kanal detayı: kitap bazında satış/iade, bekleyen sipariş, hedef ↔ gerçekleşen.
- Cari ↔ platform eşleme ekranı (kullanıcı onaylar; ör. D-MARKET = Hepsiburada).
- T-soft ürün okumasından (SEO modülünün mevcut gece okuması) fiyat/stok görünürlük farkı: sitede stokta yok ↔ Logo'da stok var.

**Sonraki sürüm**
- T-soft sipariş okuma (yöntem doğrulanınca, KVKK kararıyla): günlük D2C panosu, en çok satanlar, sepet, tekrar alım kohortu.
- Analitik bağlanırsa dönüşüm hunisi; D2C kampanya/sadakat önerileri (K2).
- Platform satıcı API'leri (TİMAŞ'ın kendi mağazası varsa, salt okunur).

**Mevcut kodda yeniden kullanılacaklar**
- `backend/semantic_bridge/seo_geo/connections.py` (T-soft salt okunur istemci ve `READ_ONLY` koruması), `seo_geo/crm.py`
  (`semantic_seo_crm_books`: T-soft ürünü ↔ CRM kitap, EAN-13), `seo_geo/store.py` (gece okunan ürün tablosu).
- `backend/semantic_bridge/management/` (önbellek, `{satis:<yıl>}`), `contracts_royalty.py` (Logo satış görünümünden kitap bazında okuma).
- Katalog SQL çiftleri: `2026-y-l-nda-kitapci-e-ticaret-ve-dagitici-kanallar-i-in-ay.md`, `kanal-baz-nda-br-t-k-r-marj-...md`.
- `alerts.py`, `reports.py`, `board.py`, `SearchSelect.tsx`.

## 10. Uzmanlara sorulacak sorular

1. TİMAŞ'ın Hepsiburada, idefix, D&R, Kitapyurdu üzerinde **kendi satıcı mağazası** var mı, yoksa hepsi TİMAŞ'tan toptan alıp kendisi mi satıyor? (Modülün yarısı buna bağlı.)
2. Pazar yerleri ve timas.com.tr için stok ve fiyatı bugün kim, hangi araçla gönderiyor (T-soft pazar yeri modülü, entegratör, elle)? Bu modül ileride **mağazaya yazmalı mı**, yoksa hep salt okuma + öneri mi kalmalı? (Kullanıcı kararı.)
3. timas.com.tr siparişleri Logo'ya hangi cari ile faturalanıyor (tek "internet müşterisi" carisi mi)?
4. T-soft sipariş verisinin (kişisel veri) portala alınmasına KVKK açısından onay var mı; yalnız anonim özet yeterli mi?
5. Kanal kârlılığında hangi maliyetler dahil olmalı (pazar yeri komisyonu, kargo, reklam) ve bunlar Logo'da hangi hesaplarda?

## 11. Başarı ölçütü

- Kanal karnesinin aylık yönetim toplantısında kullanılması; Excel ile hazırlanan kanal raporunun bırakılması.
- "Sitede stokta yok / depoda var" kitap sayısının 2 ayda düşmesi.
- Kanal iade oranındaki düşüş (öneriyle sevk adedi düzeltilen kanallarda).
- D2C (timas.com.tr) cirosunun toplam içindeki payının izlenebilir hâle gelmesi (bugün ölçülemiyor).

## 12. Uzman gözüyle en iyi sistem

Rol: 15 yıllık e-ticaret ve kanal müdürü. Sektör pratiği (genel bilgi, TİMAŞ verisiyle doğrulanmadı): iyi yayınevleri tüm kanalları
**kitap × kanal** matrisiyle yönetir: kanalın aldığı (sell-in), kanalın sattığı (sell-through, kanal raporundan), iade ve stok.
Çok kanallı satıcılar tek bir "ürün bilgi merkezi"nden içerik, tek stok havuzundan kanal payı dağıtır; D2C sitesini fiyat bekçisi
değil **müşteri ilişkisi** kanalı olarak kullanır (ön sipariş, imzalı baskı, set, abonelik). Türkiye'de çok kanallı entegratörler
stok/fiyatı tek panelden dağıtır; TİMAŞ'ta bu yazma katmanı bizim kapsamımız dışında kalır, ama ölçüm ve öneri katmanı en çok
değeri verir.

Mükemmel sistem: sabah kanal karnesi (dün + ay + yıl); kitap bazında "hangi kanal bu kitabı iyi satıyor, hangisi iade ediyor";
sitede stok/fiyat görünürlük hataları; D2C müşterisinin kohortu; kanal iskontosu değişince kâr simülasyonu.

Bir iş günü:
- 09:00 Telefonda: "Dün timas.com.tr 312 sipariş; Kitapyurdu bu ay geçen yılın %18 üstünde; Hepsiburada iade oranı %11'e çıktı."
- 09:30 Görünürlük farkı: sitede stokta yok görünen 27 kitap depoda var → T-soft'ta kendisi düzeltir (portal göndermez).
- 11:00 Hepsiburada detayında en çok iade edilen 10 kitabı indirir, kanal yöneticisine iletir.
- 14:00 Zeki AI'ya: "Kasım indirim döneminde D2C'ye özel hangi setler çıkarılabilir?" → set önerisi (M53) ve gerekçesi.
- 16:00 Finansla kanal marjı karşılaştırması; iskonto önerisini taslak olarak kaydeder.

"Bunu görürsem hemen kullanırım":
1. Kitap × kanal satış/iade matrisi.
2. Sitede stokta yok ↔ depoda var listesi.
3. Kanal bazında iskonto sonrası marj.

"Bunu yaparsanız kullanmam":
1. Benim onayım olmadan mağazaya fiyat/stok göndermek.
2. Pazar yeri toptan cirosunu "pazar yerinde satılan" gibi göstermek (sell-in ≠ sell-through).
3. Müşteri kişisel verisini herkese açık listelemek.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (hangi tablo/görünüm/ölçü) | CRM (hangi varlık/alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Kanal karnesi | `LG_411_01_STLINE` faturalı satır (`INVOICEREF <> 0`, TRCODE 7,8,9 − 2,3, `LINENET`), `LG_411_CLCARD.SPECODE2`, ölçüler `kanal_net_ciro`, `iade_orani`, `iskonto_yuku`, `brut_kar_marji`; önceki yıllar `LG_211_*` | — | — | Rakam kayıt sisteminden |
| Cari ↔ platform eşleme | `CLCARD` (CODE, DEFINITION_) | `AccountBase` (`new_logicalref`, `new_FirmaKanal`, `new_cariozelKod2`, ad) | Aday eşleşme önerir (cari unvanı → platform adı; kapalı küme: platform listesi + "platform değil") — tek token + olasılık; kullanıcı onaylar | Unvanlar (ör. D-MARKET) platform adına benzemiyor |
| Kanal siparişi / bekleyen | `ORFICHE`/`ORFLINE` TRCODE 1 | `new_siparisBase` (`new_siparistipi`, `new_geliskanaliid`, `statuscode`), `new_siparissatiriBase` | — | — |
| Hedef ↔ gerçekleşen | Kanal net ciro (yukarıda) | `new_satishedefleriBase` (bölge, stok kartı, 12 ay) | — | — |
| Site ürün/stok görünürlüğü | Stok bakiyesi (M43), liste fiyatı `PRCLIST` PTYPE 2 | `new_kitapBase.new_ean13`, `new_kdvdahilfiyat` | — | T-soft ürünü EAN-13 ile bağlanır (SEO modülü) |
| D2C siparişleri | Fatura carisi (ölçülecek) | — | Sipariş notlarından iade/şikâyet nedeni sınıflaması (kişisel veri çıkarılmış metin) | Nedenleri gruplar |
| Kanal yorumu | Karne rakamları | — | 3–5 cümle "bu ay kanalda ne oldu" özeti; rakamlar metne SQL'den verilir | Yönetim özeti |
| Kampanya/sadakat taslağı | Geçmiş satış (set, sezon) | Kampanya (`new_kampanya`, planlanan/gerçekleşen ciro boş) | Taslak metin ve gerekçe (K2) | Pazarlama hızlanır |
| Doğal dil soru | Katalog | Katalog | Mevcut soru hattı | — |

Model: `rt.llm_for("kanal")`; gece eşleme `QueuedLlm(..., purpose="bg:kanal")`. Ekranda yalnız "Zeki AI".

## 14. Kodlama planı (kodlayıcıya devir)

**Ortak iskelet (M40, M41, M42 aynı paketi paylaşır; önce bu modülle kurulur)**
- Paket `backend/semantic_bridge/channels/`:
  - `sources.py` — Logo/CRM salt okunur SQL (dosyalar `channels/sql/`: `logo_kanal_karne.sql`, `logo_cari_kitap.sql`,
    `logo_iade.sql`, `logo_iskonto.sql`, `logo_marj.sql`, `crm_kanal_siparis.sql`, `crm_hedef.sql`, `crm_cari.sql`), satış yılları için
    `{satis:<yıl>}` yer tutucusu (management deseni).
  - `platforms.py` — platform istemcileri için ortak **salt okunur** taban sınıf: `READ_ONLY` deseni (T-soft istemcisindeki gibi),
    yazma yöntemine istek atılırsa hata; kimlik Yönetim ekranından (`admin.conf`), Claude girmez.
  - `tsoft_orders.py` — T-soft sipariş okuma (yöntem konsol kataloğundan doğrulanınca), kişisel alanları içeri almadan özetler.
  - `mapping.py` — cari ↔ platform eşleme.
  - `store.py`, `api.py`.
- `backend/semantic_bridge/channels/d2c.py` — D2C özel hesaplar.

**Tablolar**
- `semantic_channel_accounts` (tenant_id, platform 'hepsiburada'|'trendyol'|'amazon'|'kitapyurdu'|'dr'|'idefix'|'timas.com.tr'|'diger',
  logo_cari_kodu, crm_account_id, yontem 'zeki'|'elle', olasilik, onaylayan, tarih).
- `semantic_channel_suggestions` (id, tenant_id, platform, tur 'iskonto'|'fiyat'|'kampanya'|'sadakat', payload_json, model_gerekce,
  durum, karar_veren, karar_tarihi).
- `semantic_d2c_orders_daily` (tenant_id, gun, siparis_sayisi, ciro, iade_sayisi, ortalama_sepet) — kişisel veri yok.
- `semantic_d2c_order_lines` (tenant_id, gun, barkod, adet, tutar) — kişisel veri yok.
- `semantic_d2c_cohorts` (tenant_id, kohort_ay, musteri_sayisi, tekrar_1, tekrar_3, tekrar_6) — müşteri anahtarı karmalanmış,
  ham anahtar saklanmaz.

**Uçlar** (`/api/v1/channels/*`): `GET meta`, `GET scorecard?yil=&ay=`, `GET channel/{platform}`, `GET channel/{platform}/books`,
`GET channel/{platform}/returns`, `GET targets?yil=`, `GET accounts`, `PUT accounts/{cari}`, `GET visibility` (site stok/fiyat farkı),
`GET d2c/daily`, `GET d2c/books`, `GET d2c/cohorts`, `GET suggestions`, `POST suggestions/{id}/decision`, `GET export/{liste}.xlsx`.

**Ekranlar** `src/canvas/channels/`: `ChannelsHome.tsx` (/kanallar), `Channel.tsx` (/kanallar/:platform), `Accounts.tsx`
(/kanallar/eslesme), `Visibility.tsx` (/kanallar/gorunurluk), `D2C.tsx` (/kanallar/timas-com-tr). Menü: yeni çalışma alanı
`platform` (etiket «Platform», `modules.json` grubu «Platform Yönetimi»), bölüm «Kanallar»; M40/M41 aynı alanda kendi bölümleriyle.
Kampüs: «Platform» modül kartı.

**Yetki** (yeni alan `platform`): `sayfa:kanallar`, `sayfa:kanal-eslesme`, `sayfa:kanal-gorunurluk`, `sayfa:d2c`;
`ozellik:kanal.marj` (explicit), `ozellik:kanal.oneri-karar` (explicit), `ozellik:kanal.eslesme` (cari ↔ platform onayı),
`ozellik:d2c.musteri` (explicit).

**Zamanlayıcı**: `timas-channels.timer` her gece 04:00 — karne önbelleği, görünürlük farkı (SEO modülünün 03:00 T-soft okumasından
sonra), eşleme adayları; T-soft sipariş okuma açıldığında aynı zamanlayıcıda önceki günün özeti. Planlı rapor ayın 2'si 08:00.

**Kabul testleri (gerçek veri, aynı kaynak)**
1. 2026 E-TICARET kanal net ciro (ay bazında) ekran = katalog SQL çifti `2026-y-l-nda-kitapci-e-ticaret-ve-dagitici-kanallar-i-in-ay`
   ile aynı tanım; faturalı satır tanımıyla: `SELECT MONTH(l.DATE_), SUM(CASE WHEN l.TRCODE IN (7,8,9) THEN l.LINENET ELSE -l.LINENET END) FROM dbo.LG_411_01_STLINE l JOIN dbo.LG_411_CLCARD c ON c.LOGICALREF = l.CLIENTREF WHERE l.LINETYPE = 0 AND l.CANCELLED = 0 AND l.INVOICEREF <> 0 AND l.TRCODE IN (2,3,7,8,9) AND c.SPECODE2 = 'E-TICARET' GROUP BY MONTH(l.DATE_)` — iki tanım arasındaki fark (başlık NETTOTAL vs satır LINENET, ≈ %0,6) ekranda açıklanır.
2. Cari bazında: 10 E-TICARET carisi için ekran = aynı sorgunun `GROUP BY c.CODE` hâli.
3. İade oranı = katalog `iade_orani` ölçüsünün kanal süzgeçli doğrudan SQL'i.
4. CRM sipariş tipi sayıları: `SELECT new_siparistipi, COUNT(*) FROM Timas_MSCRM.dbo.new_siparisBase WHERE new_siparistarihi >= DATEADD(DAY,-180,GETDATE()) GROUP BY new_siparistipi` — ekrandaki "Pazaryeri" ve "Amazon Konsinye" sayıları.
5. Görünürlük farkı: 10 kitapta T-soft stok alanı (SEO modülü tablosu) ve Logo bakiyesi (M43 sorgusu) elle karşılaştırılır; ekranla aynı.
6. Kişisel veri testi: `semantic_d2c_*` tablolarında ad/e-posta/telefon/adres kolonu yok (şema denetimi) ve uç yanıtlarında yok.

**Bağımlılık**: M43 stok bakiyesi (görünürlük farkı için; yoksa sekme kapalı). SEO modülünün T-soft okuması (var, test sunucusunda).
M40 ve M41 bu paketin üstüne kurulur → **M42 önce**. Paralel: kanal karnesi dış bağımlılıksız hemen yazılabilir.

**Tahmini büyüklük**: M (ilk sürüm karne + eşleme + görünürlük 2 gün); T-soft sipariş + D2C kohort ikinci sürümde M.
