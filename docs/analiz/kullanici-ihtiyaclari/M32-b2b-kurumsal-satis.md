# M32 — B2B Web Sitesi ve Kurumsal Satış Yönetimi: kullanıcı ihtiyaç analizi

Durum: kod var (main) — test sunucusunda kabul 38/40 (2026-09-28 08:00; «teklif için kitap» doğrulanamadı) · Analiz tarihi: 2026-09-28 · Kaynaklar: `specs/M32.txt`, `specs/M18.txt`, `specs/M28.txt` (başlık), `specs/M53.txt` (başlık),
`veri_haritasi2.txt`, `docs/analiz/crm-eticaret-entegrasyon-2026-09-27.md` (§2 B2B ürün servisi, §4 B2B portal), `docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`,
`configs/semantic/knowledge/crm/OKUNUR-TABLOLAR.md` + `table_descriptions.json`, `configs/semantic/knowledge/logo/knowledge/{rules/logo-erp.md (Kural 3, 8, 11), glossary, sql/kanal-bazinda-net-ciro-nedir.md}`,
`docs/analiz/yetki-mekanizmasi-2026-09-27.md`, `backend/semantic_bridge/{access.py, budget*.py, contracts*.py, board_excel.py}`,
kullanıcı belleği (tsoft-no-write, system-of-record-logo, no-tech-names-on-screens, sales-are-invoiced-lines).

Sunucuya bağlanılmadı; «ölçülecek» işaretli sayılar kodlamadan önce ölçülür.
Otomasyon: **K1** tam otomatik · **K2** Zeki önerir, insan onaylar · **K3** Zeki analiz eder, karar insanın · **K4** yalnız insan (K3/K4 tanımı varsayım).

## 1. Modül ne işe yarar

İki iş birlikte tanımlanmış: (a) **B2B web sitesi** — bayilerin/kurumların sipariş verdiği sitede müşteri profiline göre öneri, kampanya ve hatırlatma;
(b) **kurumsal satış** — şirket, kamu, vakıf ve eğitim kurumlarına tema/sektör bazlı paket (liderlik seti, çocuk kütüphanesi, yeni çalışan paketi, yılsonu
hediyesi) önerisi, kuruma özel proje dosyası ve teklif, fırsat takibi, teklif kabulünden siparişe geçiş.
Veride görülen durum: B2B site bugün **bayi sipariş portalıdır** (kitapsiparis.com.tr; CRM'e canlı bağlı; son 90 günde 4.026 sipariş, 5.090 bayi kullanıcısı —
`crm-eticaret-entegrasyon`, 2026-09-27) ve ~40 bayi ürün listesini servis üzerinden çekiyor. Kurumsal satış için CRM'deki standart fırsat/teklif
araçları kullanılmıyor (`OpportunityBase` 12, `QuoteBase` 1 kayıt) → teklif ve pipeline bugün sistem dışında (varsayım: Excel/Word/e-posta).

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| Kurumsal satış temsilcisi | Satış; CRM `SystemUserBase.new_KullancTipi` 2 = «Kurum Temsilcisi»; `AccountBase.new_KurumunTemsilcisi` | Günlük | Masaüstü (teklif) + telefon (görüşme) |
| Satış müdürü (teklif ve indirim onayı) | Satış | Günlük | Masaüstü |
| B2B portal / e-ticaret sorumlusu (site kampanyası, öne çıkanlar) | Satış/e-ticaret (varsayım; kişi bilinmiyor) | Haftalık | Masaüstü |
| Merkez müşteri temsilcisi (bayi siparişleri) | `AccountBase.new_MerkezMusteriTemsilcisi` | Günlük | Masaüstü |
| Pazarlama (föy, tema katalogları) | Pazarlama | Aylık | Masaüstü |
| Muhasebe / hukuk (sözleşme, fatura koşulu) | Mali işler | Teklif başına | Masaüstü |

Kurum temsilcisi sayısı **ölçülecek** (`SystemUserBase.new_KullancTipi = 2`, etkin).

## 3. Bugün bu iş nasıl yapılıyor

- **Bayi B2B siparişi:** Bayi kitapsiparis.com.tr'de sipariş verir; CRM'de sipariş «Timas CRM» servis hesabıyla açılır, `new_yenib2b`, `new_webuserid`,
  geliş kanalı (`new_geliskanaliid` → «kitapsiparis.com.tr»; alan adı kodlamada doğrulanır), sipariş tipi 1 = B2B. B2B ödeme yöntemleri cari kartında
  (`AccountBase.new_oykredikarti`, `new_oyacikhesap`, `new_oyhavale`, `new_b2bkullanabilir`). Site içi arama/sepet günlükleri CRM'de **yok**; sitenin
  işletmecisi ve günlüklere erişim sorulacak.
- **Kurumsal satış:** Kurum cari kartları Logo'da kanal `SPECODE2 = 'KURUM'`, CRM'de `new_KurumRolu` (Müşteri / Devlet Kurumu / Resmi / Özel STK) ve
  `new_cariozelKod2` 100000007 = KURUM. Teklif CRM dışında hazırlanıyor (varsayım; teklif/fırsat tabloları boş). Fiyat Logo `PRCLIST` (satış listesi
  PTYPE 2) ve CRM `new_fiyatlistesiBase` (3 liste, 6.087 öğe) / `new_iskontolistesiBase` (2 liste, 11.598 öğe); cari iskontosu `CLCARD.DISCRATE`,
  CRM `new_Ekiskonto`, `new_iskontosablonuid`.
- **Tıkanma (varsayım):** her kurum teklifi sıfırdan; hangi kurumun ne zaman bütçe ayırdığı bilinmiyor; teklifin sonucu (kazanıldı/kaybedildi) kayıtlı değil;
  kabul edilen teklif CRM'de siparişe elle dönüşüyor.

## 4. İhtiyaçlar ve acı noktaları

- **Kurumsal temsilci:** (1) Tema/sektör bazlı hazır paket kütüphanesi (stokta, fiyatı güncel). (2) 10 dakikada kuruma özel teklif + proje dosyası (PDF/Word).
  (3) Hacim indirimi ve marjın teklif anında görünmesi (onay gerekip gerekmediği). (4) Fırsat listesi: aşama, değer, sonraki adım, karar tarihi.
  (5) Dönemsel hatırlatma: yılsonu hediyesi, öğretmenler günü, kurum yıldönümü (geçen yıl alan kurumlar).
- **Satış müdürü:** (1) İndirim/marj eşiğini aşan teklifler için onay kuyruğu. (2) Kazanma/kaybetme nedenleri. (3) KURUM kanalı ciro eğilimi.
- **B2B sorumlusu:** (1) Bayi segmentine göre öne çıkarılacak kitap/kampanya listesi (site dışında hazırlanıp siteye elle girilir — bölüm 8).
  (2) Bir süredir sipariş vermeyen bayi listesi. (3) Bayinin sık aradığı ama sipariş etmediği ürünler (site günlüğü gelirse).

## 5. Nasıl kullanmak isteyecekler

**Kullanıcı hikâyeleri**
- Kurumsal temsilci olarak «çocuk kütüphanesi, 200 kitap, bütçe 60 bin ₺» diye yazıp stokta olan paketi görmek istiyorum, çünkü müşteri aynı gün teklif bekliyor.
- Kurumsal temsilci olarak teklifi kurum logosuyla PDF/Word almak istiyorum, çünkü resmî yazışma olarak gönderiyorum.
- Kurumsal temsilci olarak teklifin aşamasını ve sonucunu kaydetmek istiyorum, çünkü gelecek yıl aynı kuruma döneceğim.
- Satış müdürü olarak marjı eşiğin altına düşen teklifleri onaylamak istiyorum, çünkü indirim yetkisi bende.
- B2B sorumlusu olarak 60 gündür sipariş vermeyen bayileri ve son aldıkları kategorileri görmek istiyorum, çünkü kampanya hazırlıyorum.
- Satış müdürü olarak Aralık'ta hangi kurumların geçen yıl hediye kitabı aldığını Ekim'de görmek istiyorum.

**Ana ekranlar ve akış**
- İlk açılış (masaüstü): «Fırsatlarım» — aşama sütunları (Aday → Görüşüldü → Teklif → Karar → Kazanıldı/Kaybedildi), toplam değer, karar tarihi yaklaşanlar;
  sağda «Bu ay hatırlatmalar» (geçen yıl bu dönemde alan kurumlar).
- Paket oluşturucu: tema/sektör/yaş/bütçe/adet → Zeki önerisi (liste, stok, fiyat, marj) → düzenle → teklif.
- Teklif: kalemler, hacim indirimi (kural), marj, onay durumu, belge (PDF/Word), gönderildi/kabul/ret kaydı.
- B2B paneli: bayi segmentleri, sipariş vermeyenler, öne çıkarılacak kitap listesi (dışa aktarım).
- En sık 3 işlem: paket önerisi al (2 tık), teklif belgesi üret (1 tık), fırsat aşamasını güncelle (1 tık).

**Zeki AI'ya soracakları**
- «Geçen yıl Aralık'ta kurumsal hediye alan kurumlar kimler, ne kadar aldılar?»
- «Liderlik temalı, stokta 100'den fazla olan kitaplarımız hangileri?»
- «KURUM kanalında bu yıl net ciro geçen yılın ne kadarı?»
- «Hangi bayiler 60 gündür sipariş vermedi?»
- «Bu teklifte %35 indirimle marj ne olur?»
- «Kaybettiğimiz tekliflerin en sık nedeni ne?»

**Otomasyon katmanı**
- K2: tema paketi önerisi; hedef kurum listesi ve öncelik; teklif mektubu ve proje dosyası taslağı; dönemsel teklif planı.
- K1: dönemsel hatırlatmalar (geçen yıl alan kurumlar), sipariş vermeyen bayi listesi, B2B segment raporu.
- K3: kazanılan/kaybedilen fırsat analizi, KURUM kanal eğilimi.
- K4: indirim eşiği üstü onay (müdür), sözleşme imzası, siteye içerik yerleştirme (site işletmecisi).
- İş tanımındaki «B2B site kişiselleştirme — tam otomatik (K1)» ilk sürümde **yapılamaz** (bölüm 8): öneriler listelenir, siteye insan/işletmeci taşır.

**Bildirim/uyarı**
- Temsilci: fırsatın karar tarihi 7 gün içinde (sabah); dönemsel hatırlatma (dönemden 45 gün önce); teklif onaylandı/reddedildi (anında).
- Müdür: onay bekleyen teklif (anında); ay sonunda kazanma oranı özeti.
- B2B sorumlusu: haftalık «sipariş vermeyen bayi» listesi (pazartesi).

**Onay ve yetki**
- `sayfa:kurumsal-satis`; temsilci kendi fırsatlarını görür, `ozellik:kurumsal.herkesinki` bütün ekip.
- `ozellik:kurumsal.teklif` (paket/teklif hazırlama), `ozellik:kurumsal.teklif-onay` (explicit; indirim/marj eşiği üstü), `ozellik:kurumsal.b2b` (bayi paneli),
  belge/CSV `ozellik:veri.disa-aktar`.

## 6. Veri

| Gereken veri | Kaynak | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Kurum carileri ve segmenti | Logo `CLCARD.SPECODE2 = 'KURUM'`; CRM `AccountBase.new_KurumRolu`, `new_cariozelKod2`, `IndustryCode` (endüstri), `new_KurumunTemsilcisi` | alanlar var | Şirket/kamu/vakıf/eğitim ayrımının doluluğu **ölçülecek**; `IndustryCode` büyük olasılıkla boş |
| Kurum satış geçmişi | Logo faturalı satır (`INVOICEREF<>0`, `LINENET`), fatura başlığı sayısı `COUNT(DISTINCT INVOICE.LOGICALREF)` | tanımlı | Logo .155 donmuş (17.08.2026) |
| Bayi B2B siparişleri | CRM `new_siparisBase` (tip 1, `new_yenib2b`, `new_webuserid`, geliş kanalı), `new_webuserBase` (5.057) | ölçüldü (4.026 / 90 gün) | — |
| B2B site davranışı (giriş, arama, sepet, terk) | Site işletmecisi | **yok** | Erişim ve izin sorulacak; yoksa K1 kişiselleştirme ve sepet hatırlatma yapılamaz |
| Fiyat ve iskonto | Logo `PRCLIST` (Kural 8), `CLCARD.DISCRATE`; CRM `new_fiyatlistesi*`, `new_iskontolistesi*`, `new_iskontosablonu` | var | Hangisinin geçerli olduğu (Logo mu CRM mi) sorulacak |
| Stok | Logo stok bakiyesi | tanımlı | donmuş kopya |
| Marj | Logo `AMOUNT × OUTCOST` (maliyetli satırlar) | tanımlı (iş teyidi bekliyor) | 30.06.2026 sonrası maliyetsiz; yeni kitapta maliyet yok → teklif marjı «tahmini» etiketiyle ve son maliyetli satırdan |
| Tema/kategori | CRM `new_kitapBase` (tür, hedef yaş, seri, özet), `new_webkategoriitem` (2.483, 2022) | kısmi | Kategori Ağacı modülü yok; tema etiketleri modelle önerilip insan onaylar |
| Föy / ürün kartı | M18 (kodlanmadı); CRM `new_TantmFyMetni`, `new_ozet` | kısmi | M18 gelene kadar CRM föy metni |
| Fırsat/teklif geçmişi | CRM `OpportunityBase` (12), `QuoteBase` (1) | kullanılmıyor | Köprü tablosu sıfırdan; geçmiş yok |
| Kurum bütçe dönemleri | Kullanıcı girer; geçmiş alım ayından türetilir | yok | — |

## 7. Diğer modüllerle bağ

- Girdi: **M18** (föy paketi, kampanya takvimi), **M53** Hediye/Set (set ürünleri), **M46** (kitap hedefi — kurumsal satışın katkısı), **M28** Kurumsal ilişkiler
  (kanaat önderi/kurum ilişkisi), **M33** (kamu kurumu ihaleleri — kamu kurumlarına doğrudan satış burada, ihale M33'te), **Kategori Ağacı** (gelince).
- Çıktı: **M30** (bayi segment bilgisi, sipariş vermeyen bayi → ziyaret önceliği), **M46** (KURUM kanal gerçekleşmesi), **M12** (özel baskı talebi: kurum logolu
  kapak/ön söz — ikinci sürüm, varsayım).

## 8. Kısıtlar

- **Siteye yazma yok:** B2B sitesi CRM'e bağlı üçüncü taraf/iç yazılım (işletmeci sorulacak). T-soft yasağının mantığıyla (bellek: tsoft-no-write) portal
  **hiçbir web sitesine** içerik, kampanya ya da öneri göndermez; iş tanımındaki K1 site kişiselleştirmesi ilk sürümde «öneri listesi + dışa aktarım»dır.
- **CRM'e ve Logo'ya yazma yok:** «teklif → CRM kaydı → sipariş → LOGO entegrasyonu» ilk sürümde yok; kabul edilen teklif sipariş formatında dışa aktarılır,
  CRM'de insan açar.
- Ekranda teknoloji adı yok; demo veri yok; sayı tavanı yok.
- **Hukuki:** teklif ve sözleşme taslakları hukuk/muhasebe onayı olmadan «nihai» sayılmaz; kamu kurumlarına satışta 4734 sayılı Kanun kapsamı M33'tedir.
  Kurum iletişim kişileri KVKK kapsamında; toplu e-posta İYS izni olan kişilere (CRM `obs_sendtoemailiys`, `DoNotEMail`).
- Bayi kullanıcı adı/şifre kolonları (`new_webuserBase`, `NY_Web_UserName_Password`, servis günlüğü) **okunmaz** (güvenlik notu, crm-eticaret §7.5/10).

## 9. Kapsam önerisi

- **İlk sürüm:** kurum müşteri listesi (Logo KURUM + CRM kurum rolü) ve alım geçmişi; tema paketi oluşturucu (stok, fiyat, tahmini marj); teklif (kalem,
  hacim indirimi kuralı, onay eşiği, PDF/Word belge); fırsat takibi (köprü tablosu, aşama, sonuç, neden); dönemsel hatırlatma; bayi B2B paneli (sipariş
  vermeyen bayi, segment, öne çıkarılacak kitap listesi dışa aktarımı).
- **Sonraki sürüm:** site davranış günlüğü (izin gelirse) ile bayi kişiselleştirme listeleri; hedef kurum listesi (dış kaynak — kullanıcı yükler);
  kazan/kaybet modeli; teklif → CRM sipariş aktarımı (yetki gelirse); özel baskı (M12).
- **Yeniden kullanılacaklar:** `contracts_docs.py` (Word belge üretimi deseni), `board_excel.py`, `budget.py` (onay/iki göz/audit), `budget_sources.runner`,
  `author_relations.py` (aşama + sonraki adım deseni), `access.py`.

## 10. Uzmanlara sorulacak sorular

1. kitapsiparis.com.tr'yi kim işletiyor; arama/sepet günlüklerine erişim ve sitede öne çıkarma/kampanya alanına içerik koyma yetkisi kimde?
2. Kurumsal teklif bugün nasıl hazırlanıyor (şablon var mı), kim onaylıyor, indirim yetki basamakları ne?
3. KURUM kanalındaki carileri şirket / kamu / vakıf / okul diye nerede ayırıyorsunuz?
4. Geçerli fiyat ve iskonto listesi Logo'da mı CRM'de mi tutuluyor; kurumsal teklifte hangisi esas?
5. Kurumlara özel baskı (logolu kapak, kurum adına önsöz) yapılıyor mu; en az adet ve süre nedir?

## 11. Başarı ölçütü

- Teklif hazırlama süresi (talep → gönderim), hedef aynı gün.
- Teklif → sipariş dönüşüm oranı ve ortalama teklif değeri; kaybedilen tekliflerde neden dağılımı.
- KURUM kanal net ciro (Logo) — önceki yılın aynı dönemiyle.
- Dönemsel hatırlatmadan doğan fırsat sayısı.
- B2B: 60+ gün sipariş vermeyen bayi sayısının azalması; B2B portal sipariş payı.

## 12. Uzman gözüyle en iyi sistem

**Uzman:** 15 yıllık kurumsal satış müdürü (yayın/hediye). Sektör uygulaması (genel bilgi, doğrulanmadı): kurumsal satışta iyi ekipler hazır tema
paketleri (liderlik, çocuk kütüphanesi, yeni çalışan) ve fiyat/teklif (CPQ) araçlarıyla dakikalar içinde teklif çıkarır; indirim onayı kural tabanlıdır;
fırsat hattı (pipeline) aşama/olasılık/karar tarihiyle izlenir; yılsonu hediyesi gibi dönemsel alımlar geçen yılın alıcı listesiyle 2–3 ay önceden
aranır. B2B portallarda bayiye geçmiş alımına göre «eksik tamamla» ve yeni çıkan listesi sunulur.

**TİMAŞ için mükemmel sistem:** kurum kartında geçmiş alımlar ve kurum takvimi; paket oluşturucu stok/fiyat/marjla anında; teklif kurum antetli belge;
indirim eşiği aşılırsa müdüre tek tık onay; kabulde sipariş dosyası; Ekim'de «geçen yıl Aralık'ta alanlar» listesi; bayi tarafında sipariş vermeyen bayi
listesi saha ekibine (M30) gider.

**Bir iş günü:** 09:00 «Fırsatlarım»: bir bankanın İK birimi 300 yeni çalışan paketi istiyor. Paket oluşturucu: kişisel gelişim + iş hayatı, stokta 120+,
kişi başı bütçe 250 ₺ → 3 kitaplık 4 alternatif, marj ve stok görünür. Birini seçer, %30 hacim indirimi eşiği aşınca müdür onayına düşer; 11:00 onay gelir,
PDF teklif gider. Öğleden sonra geçen yıl hediye alan 18 kurumu arar; 3'ü için fırsat açar. 17:00 kaybedilen bir teklife «fiyat» nedeni yazar.

**«Bunu görürsem hemen kullanırım»:** (1) Bütçe ve adetten stokta olan paket önerisi, marjıyla. (2) Tek tıkla kurumsal görünümlü teklif belgesi.
(3) «Geçen yıl bu dönemde alan kurumlar» listesi.

**«Bunu yaparsanız kullanmam»:** (1) Stokta olmayan ya da fiyatı eski kitabı pakete koyan öneri. (2) CRM'de ve portalda aynı teklifi iki kez yazdırmak.
(3) İndirim onayını e-postaya ve portala bölmek (onay tek yerde olmalı).

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (tablo/ölçü) | CRM (varlık/alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Kurum listesi | `CLCARD` SPECODE2 = KURUM, CODE, DEFINITION_, CITY | `AccountBase.new_KurumRolu`, `new_cariozelKod2`, `new_KurumunTemsilcisi`, `new_logicalref`/`new_CariKodu` | Kurum unvanından segment önerisi (şirket/kamu/vakıf/okul/üniversite — kapalı küme, tek token + olasılık), insan onaylar | Serbest metin sınıflama |
| Alım geçmişi | faturalı satış `LINENET`, `AMOUNT`; fatura sayısı başlıktan | — | — | Kayıt sistemi Logo |
| Tema etiketi | — | `new_kitapBase` özet, tür, hedef yaş, seri | Kitaba tema etiketleri önerisi (liderlik, çocuk kütüphanesi…) — kapalı küme; onaylanan etiket köprü tablosunda | Kategori ağacı yok |
| Paket önerisi | stok bakiyesi, `PRCLIST` fiyatı, maliyet (son maliyetli satır) | fiyat/iskonto listeleri | Aday kitaplar kural ile süzülür (stok, bütçe, tema); model yalnız sıralama gerekçesi | Rakam SQL |
| İndirim / marj | fiyat × adet, `OUTCOST` | `new_Ekiskonto`, iskonto şablonu | — (kural) | Denetlenebilir |
| Teklif mektubu / proje dosyası | — | kurum adı, temsilci | Taslak metin (kurum ihtiyacı, kitap seçimi gerekçesi) — temsilci düzenler | Taslak |
| Bayi segmenti | bayi faturalı satış, son alım tarihi, kategori karması | `new_siparisBase` B2B kanal, `new_webuserBase` sayısı (yalnız sayım) | Segment adı ve öneri cümlesi | Özet |
| Fırsat analizi | — | (köprü) | Kaybetme nedeni serbest metninin sınıflanması | Sınıflama |

Model çağrısı `rt.llm_for("kurumsal")`; toplu tema etiketleme `/api/v1/llm/jobs`; `LlmClient` doğrudan kurulmaz.

## 14. Kodlama planı (kodlayıcıya devir)

**Köprü dosyaları** — `backend/semantic_bridge/corporate_sales.py`, `corporate_sales_sources.py`, `corporate_sales_api.py`, `corporate_sales_docs.py`
(teklif PDF/Word; `contracts_docs.py` deseni).

**Tablolar**
- `semantic_corp_accounts` (logo_clientref, logo_code, crm_account_id, unvan, segment, segment_kaynak `crm|oneri|elle`, temsilci, il, ilk_alim, son_alim, asof)
- `semantic_corp_themes` (stok_kodu, tema, kaynak `oneri|elle`, olasilik, onaylayan, zaman)
- `semantic_corp_opportunities` (id, logo_clientref/crm_account_id, ad, tema, asama `aday|gorusuldu|teklif|karar|kazanildi|kaybedildi`, deger, karar_tarihi,
  sahip, kaybetme_nedeni, sonraki_adim, olusturma/guncelleme)
- `semantic_corp_quotes` (id, firsat_id, surum, kalemler_json (stok, adet, liste fiyatı, indirim, net, tahmini maliyet), toplam, marj, onay_durumu, onaylayan,
  belge_yolu, gonderildi, sonuc)
- `semantic_corp_reminders` (logo_clientref, donem_ayi, gecen_yil_tutar, durum)
- Yazmalar `semantic_audit`'e (`corp_quote`, `corp_opportunity`, `corp_theme`).

**Uçlar** (`/api/v1/corporate/*`)
- `GET /accounts` · `GET /accounts/{ref}` · `PATCH /accounts/{ref}` (segment)
- `POST /packages/suggest` {tema, yas, butce, adet} · `GET /themes` · `POST /themes/{stok}/approve`
- `GET/POST /opportunities` · `PATCH /opportunities/{id}`
- `POST /opportunities/{id}/quotes` · `PATCH /quotes/{id}` · `POST /quotes/{id}/submit|approve|reject` · `GET /quotes/{id}/document.(pdf|docx)`
- `GET /reminders?ay=` · `GET /b2b/dealers?durum=sessiz&gun=60` · `GET /b2b/highlights.csv`
- `POST /run-due` (SYSTEM)

**Ekranlar** — `src/canvas/corporate/` (`Pipeline.tsx`, `PackageBuilder.tsx`, `QuoteEditor.tsx`, `DealerPanel.tsx`, `api.ts`). Rota `/timas/kurumsal-satis`
(+ `/kurumsal-satis/firsat/:id`). Menü: `satis` alanı, `{ id: 'kurumsal-satis', label: 'Kurumsal ve B2B', section: 'Kurumsal' }`. Kampüs: `ModulesMenu.tsx`
→ `M32: '/kurumsal-satis'`. Telefonda fırsat listesi ve aşama güncelleme; paket/teklif masaüstü.

**Yetki** — `sayfa:kurumsal-satis`; `ozellik:kurumsal.herkesinki`, `ozellik:kurumsal.teklif`, `ozellik:kurumsal.teklif-onay` (**explicit**; gönderen onaylayamaz),
`ozellik:kurumsal.b2b`, `ozellik:kurumsal.tema-onay`; belge/CSV `ozellik:veri.disa-aktar`. `access.py` `RULES`: `("/api/v1/corporate/run-due", SYSTEM)`,
`("/api/v1/corporate/", frozenset({page("kurumsal-satis")}))`; `FEATURE_RULES` belge uçlarını `ozellik:veri.disa-aktar` listesine ekler.

**Zamanlayıcı** — `scripts/server/timas-corporate.{service,timer}`: gece 04:00 `run-due` (kurum listesi ve alım özeti, dönemsel hatırlatma, sessiz bayi listesi);
pazartesi 07:30 B2B özeti e-postası. İlk kez elle koşturulur.

**Kabul testleri**
1. KURUM kanal net ciro (yıl) = `SELECT SUM(CASE WHEN L.TRCODE IN (7,8,9) THEN L.LINENET ELSE -L.LINENET END) FROM LG_411_01_STLINE L JOIN LG_411_CLCARD C
   ON C.LOGICALREF = L.CLIENTREF WHERE C.SPECODE2 = 'KURUM' AND L.LINETYPE = 0 AND L.CANCELLED = 0 AND L.INVOICEREF <> 0 AND L.TRCODE IN (2,3,7,8,9)`
   (ve `v_channel_net` KURUM satırı ile tutarlılık notu).
2. Kurum alım geçmişi: fatura sayısı = `SELECT COUNT(DISTINCT LOGICALREF) FROM LG_411_01_INVOICE WHERE CLIENTREF = @ref AND CANCELLED = 0 AND TRCODE IN (7,8,9)`.
3. B2B siparişleri (son 90 gün) = `SELECT COUNT(*) FROM Timas_MSCRM.dbo.new_siparisBase s WHERE s.statecode = 0 AND s.new_yenib2b = 1 AND s.CreatedOn >= DATEADD(day,-90,GETDATE())`
   (geliş kanalı süzgeci ile ikinci sayım; 2026-09-27 ölçümü 4.026 ile büyüklük kıyası).
4. Paket fiyatı: her kalemin liste fiyatı = geçerli `PRCLIST` (PTYPE 2, ACTIVE 0, CURRENCY 160, BEGDATE ≤ bugün ≤ ENDDATE; birden çok liste varsa seçilen liste
   ekranda yazılı); stok > 0.
5. Marj: kalem tahmini maliyeti = o kitabın son maliyetli satış satırının `OUTCOST`'u (`OUTCOST <> 0`, en yeni `DATE_`) — doğrudan SQL ile 5 kitap.
6. Sessiz bayi: `GET /b2b/dealers?gun=60` listesi = son faturası 60 günden eski ve önceki 12 ayda ≥ 1 faturası olan bayi/kitapçı carileri (Logo INVOICE).
7. Onay: eşik üstü teklif `ozellik:kurumsal.teklif-onay` olmadan onaylanamaz (403), gönderen onaylayamaz (409).

**Bağımlılık** — bağımsız başlanabilir; M18 föyü gelince paket kartına eklenir; M33 ile kamu kurumu ayrımı (ihale varsa M33, doğrudan satış M32).
B2B site günlüğü işletmeci iznine bağlı — ilk sürümü bekletmez.

**Büyüklük** — M (1–2 gün) ilk sürüm (site kişiselleştirmesi hariç); tema etiketleme ve belge üretimiyle L'ye yaklaşabilir.
