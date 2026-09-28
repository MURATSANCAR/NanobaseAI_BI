# M16 — Lansman / Yayın Ayı Pazarlama: kullanıcı ihtiyaç analizi

Durum: kod var (main) — test sunucusu kabulünde «depo stoku ekranda boş» bulundu; düzeltme 2026-09-28 (eksik tamamlama turu), yeniden kabul bekliyor · Analiz tarihi: 2026-09-28 · Kaynaklar: `specs/M16.txt` (ZEKİ_Moduller3.html), `specs/M5.txt` ve `specs/M7.txt` (M16'yı tetikleyen/besleyen bağlar), `ZEKİ_Veri_Haritasi2.html` (Lansman Girdileri, Gerçek Zamanlı Veri), `configs/semantic/knowledge/crm/table_descriptions.json` (CRM MetadataSchema, döküm 2026-09-09), `configs/semantic/knowledge/crm/OKUNUR-TABLOLAR.md`, `docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`, `docs/analiz/crm-eticaret-entegrasyon-2026-09-27.md`, `docs/analiz/kitap-yazar-web-taramasi-2026-09-24.md`, `docs/analiz/seo-geo-modul-2026-09-25.md`, `docs/GELISTIRME-GUNLUGU.md` (M46, M7 girişleri), `backend/semantic_bridge/budget_sources.py`, `web_watch.py`, `author_relations.py`, `seo_geo/`, `alerts.py`, `access.py`, `src/canvas/nav/navModel.ts`, `docs/analiz/kullanici-ihtiyaclari/M15-yeni-kitap-pazarlama.md` (ortak pazarlama çekirdeği), kullanıcı belleği (logo-155-frozen-copy, timas-crm-prod-28, system-of-record-logo, sales-are-invoiced-lines, tsoft-no-write, customer-vm-web-watch-off, web-watch-open-sources, no-tech-names-on-screens, no-silent-limits-rule, llm-gate).

> Kural: sunucuya bağlanılmadı. CRM satır sayıları tablo sözlüğünün 2026-09-09 dökümündendir (canlıda **ölçülecek**). Ölçülmemiş her şey **ölçülecek**, kanıtsız her iddia **varsayım**.

## 1. Modül ne işe yarar

Kitabın yayın haftasını ve ilk ayını yönetir: M15'te onaylanan planı gün gün uygulanabilir bir **lansman paketi**ne çevirir (ilk hafta sosyal medya yoğunlaştırması, basın lansmanı, yazar etkinlik takvimi, ön sipariş ve ilk baskı stok koordinasyonu), yayın gününden itibaren **ilk 7 gün ve ilk 30 günü izler** (satış, sipariş, stok, medya yansıması) ve lansman sonrası değerlendirme raporunu Zeki AI ile hazırlar; bütçe revizyonu ve sonraki adım kararı insanda kalır (iş tanımı: K2 yoğunlaştırma, K1 tetikleyiciler, K3 değerlendirme).

TİMAŞ'ın bugünkü sorunu: yayın günü ile ilgili bilgi dört yerde — üretimin depo giriş/dağılım tarihi (CRM üretim kartı), ilk dağılım siparişleri (CRM sipariş tipi «Dağılım»), bayilerin açık ve bekleyen siparişleri (CRM sipariş satırı, «Bekleyen Ürün»), faturalı satış (Logo). Lansmanın ilk günlerinde «kitap rafa ulaştı mı, ön sipariş ne kadar, ilk hafta hedefe göre nerede» sorularının tek ekranı yok. Ek olarak portalın okuduğu Logo kopyası 2026-08-17'de donmuş (.155); canlı satış bugün portalda görünmüyor.

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| Kitap pazarlama sorumlusu (lansman sahibi) | Pazarlama (CRM proje `new_pazarlamasorumlusuid`; ekip «Pazarlama» 35 kişi) | Lansman haftası her gün, sonra haftalık | Masaüstü + telefon (yayın günü sahada) |
| Pazarlama müdürü | Pazarlama | Lansman haftasında günde bir bakış; değerlendirme toplantısı | Telefon (pano), masaüstü (rapor) |
| Sosyal medya / dijital uzmanı | Pazarlama (varsayım: CRM pazarlama tipinde «Sosyal Medya», «Dijital Pazarlama») | Yayın haftası günde birkaç kez | Telefon ağırlıklı |
| Etkinlik / yazar ilişkileri sorumlusu | Pazarlama ya da Editörya (varsayım). Kanıt: CRM `new_etkinlikBase` «Sorumlusu», «İlgili Yazar», «İlgili Kitap»; M7 randevu kaydı | Etkinlik başına | Telefon + masaüstü |
| Satış / dağıtım sorumlusu | Satış (ekip 49 kişi); M29 İlk Dağılım | Yayın haftası her gün | Masaüstü |
| E-ticaret sorumlusu | Varsayım (T-soft sayfası, pazar yerleri) | Yayın günü | Masaüstü |
| Basın sorumlusu | Pazarlama (varsayım); M20 | Lansman haftası | Masaüstü |
| Genel müdür | Yönetim | Lansman raporu | Telefon |

## 3. Bugün bu iş nasıl yapılıyor

- **Lansman sahibi** (varsayım, CRM izine dayanarak): yayın tarihi üretimden sorulur (CRM `new_UretimBase.new_DepoGiriTarihi`, `new_dagilimtarihi`); ilk dağılım satışla konuşulur (CRM sipariş tipi 2 «Dağılım»); sosyal medya ve basın takvimi Excel/paylaşımlı takvimde; etkinlikler CRM «Etkinlik» kaydında (57.013 kayıt; çoğu satış ziyareti, etkinlik türü 371 çeşit) ya da web «Haber ve Etkinlik» (65 kayıt: kitap tanıtım, imza günü, söyleşi, fuar). Adım: en az 5 ayrı araç. Tıkanma: ilk hafta satışı bayiden/e-ticaretten geç geliyor, Logo faturası günlük, «saatlik izleme» yapılamıyor.
- **Sosyal medya uzmanı**: platformların kendi planlayıcılarıyla (varsayım); portal hiçbir sosyal medya platformuna bağlı değil.
- **Satış/dağıtım**: bekleyen siparişleri CRM «Bekleyen Ürün» (772.616 kayıt; durum Bekleyen / Siparişe Eklendi / İptal) üzerinden izliyor (varsayım: kitap depoya girince bekleyenler siparişe ekleniyor).
- **Pazarlama müdürü**: lansman sonucu için satıştan rapor istiyor (varsayım); medya yansıması CRM «Haber» modülüne 2025-06'dan beri girilmiyor (ölü modül, 2026-09-15 ölçümü).

## 4. İhtiyaçlar ve acı noktaları

**Lansman sahibi**
1. Yayın gününe kadar ve sonrasındaki 30 günün tek kontrol listesi: her maddenin sahibi, tarihi, «yapıldı» kanıtı.
2. Kitap depoya girdi mi, dağılım siparişleri çıktı mı, ön sipariş/bekleyen ne kadar — tek bakışta.
3. İlk 7 gün günlük sinyal: CRM siparişi (canlı) + Logo faturası (günlük; veri sonu tarihiyle) hedefin aylık dağılımına göre.
4. Yazar etkinliklerinin takvimi ve her etkinliğin sonucu (katılımcı, satılan kitap — CRM etkinlik alanları).

**Pazarlama müdürü**
1. Aynı hafta lansmanı olan kitapların telefonda tek pano görünümü: hedefe göre yeşil/sarı/kırmızı.
2. 7. ve 30. gün sonunda otomatik hazırlanmış değerlendirme: satış/hedef, emsalle karşılaştırma, yapılan/yapılmayan işler, önerilen sonraki adım.
3. Bütçe revizyonu kararını gerekçesiyle kaydetmek.

**Satış/dağıtım**
1. Talep ile stok çatışmasını erken görmek: bekleyen sipariş > depo stoku ise uyarı.

**Sosyal medya uzmanı**
1. Yayın günü ve ilk hafta içerik planının onaylı materyallerle hazır olması; hangi gönderinin yapıldığını tek tıkla işaretlemek.

## 5. Nasıl kullanmak isteyecekler

### Kullanıcı hikâyeleri
- Lansman sahibi olarak **onaylı M15 planından tek tıkla lansman paketi** açmak istiyorum, çünkü planı yeniden yazmak istemiyorum.
- Lansman sahibi olarak **yayın gününe göre sıralı kontrol listesini** ve kimde ne beklediğini görmek istiyorum, çünkü lansman haftası dağınık e-postayla yürüyor.
- Lansman sahibi olarak **ilk 7 günün sipariş ve satışını hedefin o güne düşen payıyla** karşılaştırmak istiyorum, çünkü erken müdahale ancak ilk hafta mümkün.
- Satış sorumlusu olarak **bekleyen sipariş, depo stoku ve dağılım siparişini** aynı satırda görmek istiyorum, çünkü raf boş kalırsa lansman boşa gider.
- Pazarlama müdürü olarak **7. ve 30. günde hazır bir lansman raporu** ve «bütçeyi artır / aynı kalsın / kes» kararını gerekçesiyle kaydetmek istiyorum.
- Etkinlik sorumlusu olarak **yazar etkinliğinin sonucunu (katılımcı, satılan kitap) lansman raporuna** eklemek istiyorum.
- Sosyal medya uzmanı olarak **o günün gönderilerini ve onaylı görsellerini telefonda** görüp «yapıldı» işaretlemek istiyorum.

### Ana ekranlar ve akış
- **İlk açılış (`/pazarlama/lansman`)**: «Bu hafta ve gelecek 4 hafta lansmanlar» şeridi (kapak, ad, yayın günü, gün sayacı D-7…D+30, durum rengi). Altında «Bugün yapılacaklar» (bütün lansmanların bugünkü maddeleri, sahibine göre).
- **Lansman ekranı (`/pazarlama/lansman/:id`)**: sekmeler Kontrol listesi · İzleme (ilk 7/30 gün) · Etkinlikler · Medya · Değerlendirme. Telefonda İzleme ve Kontrol listesi önce gelir.
- En sık üç işlem: (1) madde «yapıldı» + kanıt bağlantısı — 1 tık; (2) İzleme'ye bakmak — lansman şeridinden 1 tık; (3) değerlendirmede karar + gerekçe — 2 tık.

### Zeki AI'ya soracakları
1. «Bu hafta çıkan kitapların ilk üç gün sipariş adedi ve hedefin o güne düşen payı ne?»
2. «Bu kitabın bekleyen siparişi depo stokundan fazla mı?»
3. «Emsallerine göre bu kitabın ilk haftası iyi mi kötü mü?»
4. «Hangi bayiler dağılım siparişi almadı?»
5. «Geçen ayki lansmanlardan hangisinin 30. gün satışı hedefin altında kaldı, neden?»
6. «Bu yazarın imza gününde kaç kitap satıldı?»
7. «Lansman raporunu iki paragrafta özetle, sonraki ay için üç öneri yaz.»

### Otomasyon katmanı
| Adım | Katman | Not |
|---|---|---|
| Lansman paketinin plandan açılması, kontrol listesi şablonu, tarihler | K1 | Plan onaylanınca ve yayın günü kesinleşince kendiliğinden |
| Yayın günü tespiti (depo girişi / dağılım tarihi) ve D-0 işareti | K1 | CRM üretim kartından; çelişki varsa uyarı |
| İlk 7/30 gün izleme verisinin toplanması | K1 | CRM sipariş (saatlik), Logo fatura (günlük), stok |
| Stok–talep uyarısı | K1 | Kural: bekleyen > depo stoku |
| **Sosyal medya/e-bülten gönderimi, reklam aktivasyonu** | **K4** (bu sürüm) | İş tanımı K1 diyor; portal hiçbir sosyal/reklam/e-posta platformuna bağlı değil ve dış kanala kendiliğinden yayın kullanıcı onayı olmadan yapılmaz. Sistem hatırlatır, kişi yayınlar, «yapıldı» işaretler. Bağlantı gelince K2'ye (onaylı içerik, tek tıkla zamanla) çıkar |
| Basın lansmanı ve etkinlik koordinasyonu | K2 | Zeki AI taslak takvim/davet metni; insan onaylar |
| Teşekkür/etkileşim mesaj taslakları | K2 | Zeki AI taslak |
| Lansman raporu | K3 | Rakamlar SQL, özet ve öneri Zeki AI; karar insanda |
| Bütçe revizyonu | K3 | Karar kaydı plan geçmişine |

### Bildirim / uyarı
- D-7: lansman sahibine «kontrol listesinde açık N madde» özeti.
- D-0 sabahı: pazarlama müdürüne o günün lansmanları + depo/dağılım durumu.
- Stok–talep çatışması (bekleyen sipariş > depo stoku, ya da dağılım siparişi yok) → satış ve lansman sahibine, anında (günde en çok bir kez aynı kitap için).
- İlk 7 günde günlük satış/sipariş hedef payının belirgin altında → lansman sahibine günlük özet (eşik ayarı Yönetim → Pazarlama; varsayılan M46'nın %80 kuralı).
- D+7 ve D+30: değerlendirme raporu hazır → müdüre ve sahibine e-posta.
- Kanal: e-posta (köprü SMTP) + Uyarılar rozeti; telefon alt çubuğundaki «Uyarılar» sayacı.

### Onay ve yetki
- Görür: `sayfa:pazarlama-lansman`.
- Değiştirir: `ozellik:pazarlama.lansman-yaz` (paket, kontrol listesi, etkinlik ve medya kaydı; «Bütün» ile gelir).
- Değerlendirme kararı ve bütçe revizyonu: `ozellik:pazarlama.plan-onay` (M15 ile aynı, açıkça verilir).
- Rakamları (ciro) görmek: `ozellik:pazarlama.butce-gor`; satış kullanıcıları adetleri görür.

## 6. Veri

| Gereken veri | Kaynak | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Onaylı pazarlama planı | M15 sözleşme ucu `GET /api/v1/marketing/contract/plans?stok=&durum=onayli` | M15 henüz kodlanmadı | M15'e bağımlı |
| Yayın günü (kesin) | CRM `new_UretimBase.new_DepoGiriTarihi`, `new_dagilimtarihi`, `new_baskikartidurumu = 2 (Yeni Baskı)`; `new_kitapBase.new_ilkyayintarihi`, `new_BaskiDurumu` (Baskı Kararı Alındı/Üretimde/Depo Teslim) | Alanlar var (tablo sözlüğü) | Hangisinin esas olduğu **uzmana sorulacak** |
| Baskı adedi | CRM üretim `new_kesinlesenbaskiadeti`, `new_netbaskiadedi`; kitap `new_nihaibaskiadeti` («İlk Baskı Adedi») | Alanlar var | Doluluk **ölçülecek** |
| Dağıtıcı raf/sipariş | CRM `new_siparisBase` (tip 2 = Dağılım, 1 = B2B, 8 = B2C, 9 = Pazaryeri…), `new_siparissatiriBase.new_StokKodu`, `new_adet`, `new_sevkedilenadet`, `new_bekleyenadet` | 333.063 sipariş / 9,7 Mn satır; canlı (.28) | Raf (satış noktasındaki stok) verisi **yok**; bayinin rafı bilinmez |
| Ön sipariş / bekleyen | (a) Açık sipariş satırları: Baskı Öneri'nin `management/sql/baski_oneri/crm_bekleyen_siparis.sql` sorgusu (kapanmış durumlar, B2C, tarihsiz sipariş ve iki iç cari hariç; stok kodu = `Product.ProductNumber` üzerinden `new_urunid`); (b) CRM `new_bekleyenurunBase` (Bekleyen/Siparişe Eklendi/İptal, `new_urunid`, `new_adet`, `new_firmaid`) | (a) canlı raporda kullanılıyor; (b) 772.616 kayıt | (b)'nin (a)'dan farkı (stoksuzken açılan «bekleyen ürün» mü) **uzmana sorulacak** |
| İlk 7 gün satış | Logo STLINE faturalı satır (günlük) | Tanım `budget_sources.sales_sql` | **Logo kopyası 2026-08-17'de donmuş**; canlı Logo (.25) erişimi TİMAŞ BT kararı. Donmuş kopyayla lansman izleme anlamsız → ekranda «satış verisi 17.08.2026'da bitiyor» uyarısı; sipariş sinyali CRM'den canlı |
| Sipariş sinyali (saatlik) | CRM sipariş satırı (`new_siparistarihi`, UTC → İstanbul günü) | Canlı .28 | Sipariş satış değildir (kayıt sistemi Logo); ekranda «sipariş» diye ayrı etiketlenir |
| Depo stoku | Logo görünümü `EOS_DEPO_STOK_KONTROL_211` (Baskı Öneri `logo_depo_stok.sql`, 157 hariç) | Baskı Öneri kullanıyor | .155 donmuş; CRM sipariş satırında sipariş anındaki depo stoku (`new_siparisanindakistokadedi`) yedek sinyal |
| E-ticaret sayfası hazır mı | T-soft ürün (SEO modülü gece okuyor: aktif, fiyat, görsel, açıklama) | `semantic_seo_*` tabloları, test sunucusunda | Yalnız okuma; VM'de SEO modülü yok |
| Sosyal medya etkileşimi | Platform API'leri | **Yok** (bağlantı yok) | Elle giriş ya da sonraki sürüm (M22) |
| Reklam dönüşümü | Reklam paneli API'leri | **Yok** | M21'e bağlı |
| Medya yansıması | «Basın ve web» (`semantic_web_mentions`) | Test sunucusunda; **müşteri VM'inde kapalı** | VM'de elle kayıt (bağlantı + mecra + tarih); M20 |
| Yazar etkinlikleri | CRM `new_etkinlikBase` (tip, ilgili yazar/kitap, tarih, yer, katılımcı, satılan kitap adedi, gelir, gider), `new_webhaberetkinlikBase`; M7 randevular (`semantic_author_meetings`) | Alanlar var | Lansman etkinliğinin «lansman» diye ayırt edilmesi **ölçülecek** (etkinlik tipi listesi) |
| Hedef | M46 `targets?stok=` (aylık dağılım; yeni kitapta yayın ayından itibaren) | Main'de | Günlük pay için aylık hedef gün oranıyla bölünür (M46 izleme yöntemiyle aynı) |
| Emsal ilk hafta/ay | Logo STLINE + CRM emsal bağı | M15 karnesinde | — |

## 7. Diğer modüllerle bağ

- **Girdi**: M15 (onaylı plan, onaylı materyaller) · M5 (yayın onayı: «M16 tetiklenir») · M12 (baskı adedi, depo giriş) · M29 (ilk dağılım planı) · M7 (yazar etkinlik takvimi) · M46 (aylık hedef) · M19 (onaylı görseller) · SEO modülü (ürün sayfası durumu).
- **Çıktı**: M18 (lansman ayı takvimi, sonuç) · M20 (basın lansmanı, yansıma) · M21/M22/M23 (ilk hafta içerik ve bütçe) · M29/M30 (stok–talep uyarısı) · M46 (bütçe revizyon kararı bilgisi) · M17 (30. gün sonu zayıf kalan kitap ileride backlist aktivasyon adayı).

## 8. Kısıtlar

- **Dış kanala otomatik yayın yok**: sosyal medya, e-posta, reklam platformlarına portal gönderim yapmaz (bağlantı yok; T-soft'a yazma yasak; kullanıcı onayı olmadan dış kanal yok). İş tanımındaki K1 tetikleyiciler bu sürümde hatırlatma + kontrol listesi olur.
- **CRM'e yazma yok**: etkinlik ve medya kaydı köprünün kendi tablolarında; CRM'e girilecekler «CRM'e işlenecek» listesinde.
- **Logo veri sonu**: .155 kopyası 17.08.2026'da bitiyor → «anlık satış» Logo'dan yapılamaz; ekranda her zaman veri sonu. Canlı Logo erişimi gelene kadar ilk hafta sinyali CRM siparişidir ve öyle etiketlenir.
- **Müşteri VM'inde basın/web taraması kapalı** → VM'de medya sekmesi elle kayıt.
- **Ekranda teknoloji adı yok**, **demo veri yok**, **sayı tavanı yok**.
- **KVKK**: etkinlik katılımcı kişisel verisi tutulmaz, yalnız sayı. Bayi adları iş verisi; dışa aktarım yetkiyle.

## 9. Kapsam önerisi

**İlk sürüm**
- Onaylı M15 planından lansman paketi (kontrol listesi: kanal, tarih, sahip, kanıt).
- Yayın günü tespiti (CRM üretim/kitap tarihleri, çelişki uyarısı).
- İzleme: CRM sipariş sinyali (günlük/saatlik), dağılım siparişleri, bekleyen, Logo faturalı satış (veri sonu etiketli), depo stoku, M46 hedefinin günlük payı, emsal ilk 7/30 gün.
- Stok–talep uyarısı.
- Etkinlik listesi (CRM okuma + elle ek), medya kaydı (test sunucusunda «Basın ve web»den, VM'de elle).
- D+7 / D+30 değerlendirme raporu (rakam SQL, özet ve öneri Zeki AI), karar kaydı.

**Sonraki sürüm**
- Sosyal medya ve reklam platformu okuma bağlantıları (M21/M22 ile; yalnız okuma).
- Onaylı içerik için zamanlanmış gönderim (kullanıcı ayrıca karar verirse; K2).
- Canlı Logo bağlantısı gelince satışın saatlik/günlük tazelenmesi.

**Mevcut kodda yeniden kullanılacaklar**
- Pazarlama çekirdeği (`backend/semantic_bridge/marketing/`, M15 belgesinde şema): plan, takvim (`semantic_mkt_tasks`), materyal, geçmiş.
- `budget_sources.py` (Logo satış, veri sonu, yıl→firma), `budget.approved_targets` (aylık hedef).
- `web_watch.py` (`semantic_web_mentions`; test sunucusunda).
- `seo_geo` ürün tabloları (T-soft sayfa durumu).
- `author_relations.py` (M7 randevular, yazar koşulu), `rooms` (Kampüs oda ayırma — lansman toplantısı).
- `alerts.smtp_settings`, `budget_api._send_mail` kalıbı; `board` (panoya kart ekleme: «lansman izleme» kartı).

## 10. Uzmanlara sorulacak sorular

1. «Yayın günü» hangisi: depo girişi mi, dağılımın çıktığı gün mü, e-ticarette satışa açıldığı gün mü?
2. Ön sipariş nasıl alınıyor (B2B portalında, pazar yerlerinde, CRM «Bekleyen Ürün» olarak mı)?
3. Lansman haftasında bugün hangi işler standart (kontrol listesi) — kim hazırlıyor?
4. Canlı Logo (.25) okuma yetkisi ya da .155 kopyasının düzenli tazelenmesi mümkün mü (BT kararı)?
5. Lansmanı «başarılı» saymak için bakılan ölçü nedir (ilk ay adet, hedefe oran, ikinci baskı kararı)?

## 11. Başarı ölçütü

- Lansmanı olan kitapların D-7'de kontrol listesinin tamamlanma oranı.
- Stok–talep uyarısından sonra kaç gün içinde sevk yapıldığı (CRM sipariş/sevkiyat tarihlerinden).
- D+7 ve D+30 raporunun zamanında (otomatik) hazır olma oranı ve raporda karar kaydı oranı.
- Lansman sahiplerinin haftalık aktif kullanımı; «yapıldı» kanıt bağlantısı olan madde oranı.

## 12. Uzman gözüyle en iyi sistem

**Kim konuşuyor:** 15 yıllık yayınevi pazarlama müdürü, lansman haftasını onlarca kez yönetmiş.

**Sektörde iyi örnekler** (genel sektör uygulaması; TİMAŞ'ta doğrulanmadı): lansman bir «savaş odası» gibi yönetilir; yayın gününden geri sayan tek kontrol listesi, her maddenin tek sahibi, günlük kısa toplantı. İlk haftanın ana göstergesi rafa ulaşmadır (sell-in) ve ardından okura satıştır (sell-through); iyi sistemler ikisini ayırır. Satış noktası verisi bulunmayan yayınevleri sipariş ve bekleyen sipariş eğrisini erken gösterge olarak kullanır. Lansman sonrası 1. hafta ve 1. ay «ne işe yaradı, ne yaramadı» notu bir sonraki kitabın planına geri beslenir.

**TİMAŞ için mükemmel sistem:** kitap depoya girdiği an lansman panosu kendiliğinden açılır; D-7'den D+30'a her gün «ne yapılacak, ne yapıldı, rakam nerede» tek ekranda; rafı boş kalma riski satışla aynı anda görünür; 7. ve 30. gün raporu toplantıdan önce hazırdır.

**Bir iş günü (yayın günü, D-0):**
- 08:30 — Telefonda lansman panosu: kitap dün depoya girmiş, dağılım siparişleri 80 bayiye çıkmış, 3 büyük zincirde bekleyen sipariş depo stokunun üstünde (kırmızı).
- 08:45 — Satış sorumlusu aynı uyarıyı görmüş; ek baskı mı, depo transferi mi — not düşer.
- 10:00 — Sosyal medya uzmanı bugünün üç gönderisini onaylı görsellerle yayınlar, her birini «yapıldı» + bağlantıyla işaretler.
- 12:00 — Basın sorumlusu iki röportaj bağlantısını medya sekmesine ekler.
- 15:00 — Zeki AI'a: «Bugün öğlene kadar kaç sipariş geldi, emsallerin ilk günü ne kadardı?» (sipariş sinyali CRM'den, emsal Logo'dan).
- 18:00 — Yazarın akşamki imza günü için etkinlik kaydı açık; ertesi sabah katılımcı ve satılan kitap sayısı girilecek.
- D+7 sabah — Hazır rapor: sipariş/satış eğrisi, hedef payı, emsal karşılaştırması, yapılan/yapılmayan işler, Zeki AI'ın iki paragraflık özeti ve üç önerisi. Müdür «dijital bütçeyi ikinci haftaya kaydır» kararını gerekçesiyle kaydeder.

**«Bunu görürsem hemen kullanırım» (3):**
1. Rafa ulaşma (dağılım + bekleyen + stok) ile satışın aynı grafikte, ayrı renklerde.
2. Bütün lansmanların «bugün yapılacaklar» listesi, telefonda tek tıkla «yapıldı».
3. 7. ve 30. gün raporunun kendiliğinden hazır olması; emsalle karşılaştırmalı.

**«Bunu yaparsanız kullanmam» (3):**
1. Donmuş/eski veriyi «anlık» diye göstermek (veri sonu yazmadan).
2. Benim onayım olmadan sosyal medyaya ya da e-postaya kendiliğinden gönderi atmak.
3. Lansman haftasında her gün onlarca e-posta bildirimi (tek günlük özet yeter, yalnız kritik stok uyarısı anında).

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (hangi tablo/görünüm/ölçü) | CRM (hangi varlık/alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Lansman paketinin açılması | — | — (plan köprüde, M15) | — | Deterministik şablon |
| Yayın günü tespiti | `LG_{firma}_ITEMS` (kart açıldı mı) | `new_UretimBase` (`new_DepoGiriTarihi`, `new_dagilimtarihi`, `new_baskikartidurumu`), `new_kitapBase.new_ilkyayintarihi`, `new_BaskiDurumu` | — | Tarih kuralı |
| Sipariş sinyali (saatlik) | — | `new_siparisBase` (`new_siparistarihi`, `new_siparistipi`, `statuscode` — iptal/taslak hariç), `new_siparissatiriBase` (`new_StokKodu`, `new_adet`, `new_sevkedilenadet`, `new_bekleyenadet`) | — | Canlı kaynak CRM; sipariş olarak etiketlenir |
| Bekleyen / ön sipariş | — | Açık sipariş satırları (`crm_bekleyen_siparis.sql`, `Product.ProductNumber` = stok kodu); `new_bekleyenurunBase` (`statuscode = 1`) | — | SQL |
| Faturalı satış (günlük) | `LG_{firma}_01_STLINE` faturalı satır, iade eksi, net adet / net ciro (LINENET); veri sonu `MAX(DATE_)` | — | — | Kayıt sistemi Logo |
| Depo stoku | `EOS_DEPO_STOK_KONTROL_211` (`logo_depo_stok.sql`) | Yedek: `new_siparissatiriBase.new_siparisanindakistokadedi` | — | SQL |
| Hedefin günlük payı | — (M46 hesaplar) | — | — | M46 `targets.aylik` |
| Etkinlik sonucu | — | `new_etkinlikBase` (`new_lgiliKitap`, `new_lgiliYazar`, `new_katilimcisayisi`, `new_SatilanKitapAd`, `new_etkinlikgeliri`, `new_ToplamEtkinlikGideri`, `statuscode`) | — | SQL |
| Medya yansıması | — | — | Test sunucusunda «Basın ve web» zaten olumlu/olumsuz/nötr etiketliyor; M16 yalnız okur | Mevcut hat |
| Basın lansmanı/etkinlik davet metni, teşekkür mesajı | — | Kitap metin alanları (`new_ozet`, `new_kitapspotu`), yazar adı | Taslak metin | Metin üretimi |
| Lansman raporu | Yukarıdaki satış/stok ölçüleri | Sipariş, bekleyen, etkinlik | Rakam tablosunu **okuyup** 2 paragraf özet ve en fazla 3 öneri yazar; rakam üretmez, tablodaki rakamı aynen kullanır | Yorum ve öneri gerekçesi |
| Stok–talep uyarısı | Stok | Bekleyen, dağılım | — | Kural |

Model çağrıları LLM kapısından: rapor ve metin taslakları `rt.llm_for("marketing", BATCH)` (gece/zamanlı), ekranda «yeniden yaz» `NORMAL`. `LlmClient` doğrudan kurulmaz.

## 14. Kodlama planı (kodlayıcıya devir)

**Ön koşul — pazarlama çekirdeği**: paket `backend/semantic_bridge/marketing/` ve tabloları `semantic_mkt_plans`, `semantic_mkt_plan_lines`, `semantic_mkt_tasks`, `semantic_mkt_materials`, `semantic_mkt_events` (şema M15 belgesi §14; M15 önce main'e girer). M16 bu pakete `launch.py` ekler, `api.py`'ye uçlarını kaydeder.

**Yeni tablolar**
- `semantic_mkt_launches`: `id` (`ML-<yıl>-<sıra>`), `tenant_id`, `plan_id` (M15 planı), `stok_kodu`, `crm_kitap_id`, `yayin_gunu`, `yayin_gunu_kaynagi` (`uretim-depo|uretim-dagilim|kitap|elle`), `durum` (`hazirlik|yayinda|izleme|kapandi`), `sahip`, `olusturma`, `kapanis`.
- `semantic_mkt_launch_daily`: `launch_id`, `gun`, `siparis_adet` (CRM, iptal hariç), `siparis_satiri`, `dagilim_adet`, `bekleyen_adet`, `fatura_net_adet`, `fatura_net_ciro` (Logo), `depo_stok`, `hedef_payi_adet`, `veri_sonu_logo`, `okuma_zamani` (her gün bir satır; saatlik okuma aynı satırı günceller).
- `semantic_mkt_launch_events`: `id`, `launch_id`, `kaynak` (`crm:<etkinlikId>|elle`), `tur`, `tarih`, `yer`, `katilimci`, `satilan`, `gelir`, `gider`, `not`.
- `semantic_mkt_launch_media`: `id`, `launch_id`, `kaynak` (`web:<itemId>|elle`), `mecra`, `baslik`, `url`, `tarih`, `ton` (`olumlu|olumsuz|notr`), `giren`.
- `semantic_mkt_launch_reviews`: `id`, `launch_id`, `gun` (7|30), `rakam_json` (SQL sonuçları, SQL metinleri), `ozet` (Zeki AI), `oneriler_json`, `karar` (`artir|koru|kes|diger`), `gerekce`, `karar_veren`, `karar_zamani`.
- Kontrol listesi maddeleri çekirdeğin `semantic_mkt_tasks` tablosunda (`plan_id` + `launch_id` kolonu eklenir; `gun_farki` D-n / D+n).

**Uçlar** (`/api/v1/marketing/launches…`)
- `GET launches?from=&to=&durum=` (şerit), `GET launches/today` (bugün yapılacaklar, kişiye göre).
- `POST launches` `{plan_id}` (onaylı M15 planından; plan onaylı değilse 409), `GET|PATCH launches/{id}`.
- `PUT launches/{id}/tasks/{tid}` (`durum`, `kanit_url`).
- `GET launches/{id}/tracking?gun=7|30` (günlük seri + emsal + hedef payı + her serinin SQL'i).
- `GET|POST launches/{id}/events`, `GET|POST launches/{id}/media`.
- `POST launches/{id}/reviews/{gun}/draft` (Zeki AI özeti; iş kuyruğu), `POST launches/{id}/reviews/{gun}/decide` (`plan-onay` gerekir).
- `GET launches/{id}/export.pdf` (lansman raporu).
- `POST launches/run-due` (SYSTEM): saatlik sipariş okuması, günlük Logo/stok okuması, uyarılar, D+7/D+30 rapor taslağı.

**Ekranlar**: `src/canvas/marketing/launch/` — `LaunchHome.tsx` (şerit + bugün), `LaunchScreen.tsx` (sekmeler `ChecklistTab`, `TrackingTab` — ECharts çizgi: sipariş, fatura, hedef payı, emsal; `EventsTab`, `MediaTab`, `ReviewTab`). Rotalar `/pazarlama/lansman`, `/pazarlama/lansman/:id`. Menü: alan `pazarlama`, bölüm «Planlama», `{ id: 'pazarlama-lansman', label: 'Lansman', to: '/pazarlama/lansman', section: 'Planlama' }`. Kampüs `LIVE.M16 = '/pazarlama/lansman'`. Telefon: şerit yatay kaydırmalı, kontrol listesi 44 px satırlar.

**Yetki**: `sayfa:pazarlama-lansman`; `ozellik:pazarlama.lansman-yaz`; karar `ozellik:pazarlama.plan-onay` (explicit, M15'te tanımlı); ciro `ozellik:pazarlama.butce-gor`. `access.RULES`: `/api/v1/marketing/launches/run-due` → SYSTEM; `/api/v1/marketing/launches` → `page("pazarlama-lansman")`. M46 `targets` satırına `page("pazarlama-lansman")` eklenir (ya da köprü içi `approved_targets`).

**Zamanlayıcı**: `timas-marketing-launch.timer` — saatte bir `POST /api/v1/marketing/launches/run-due`: yalnız `durum in (hazirlik, yayinda, izleme)` lansmanlar için CRM sipariş okuması (hafif, stok kodu listesiyle); günde bir (07:00) Logo satış + stok + veri sonu; D+7/D+30 sabahı rapor taslağı; uyarılar günlük özette birleşir (stok çatışması hariç). İlk kurulumda elle koşturulur.

**Kabul testleri** (test sunucusu, gerçek CRM .28 + Logo .155; bir geçmiş yeni kitap üzerinde «geriye dönük lansman» olarak)
1. **Sipariş sinyali**: `SELECT CAST(DATEADD(hour, 3, s.new_siparistarihi) AS date) AS gun, SUM(ss.new_adet) FROM Timas_MSCRM.dbo.new_siparissatiriBase ss JOIN Timas_MSCRM.dbo.new_siparisBase s ON s.new_siparisId = ss.new_siparisid WHERE ss.new_StokKodu = '<kod>' AND s.statuscode NOT IN (1, 100000001) AND s.new_siparistarihi >= '<D-14>' AND s.new_siparistarihi < '<D+31>' GROUP BY CAST(DATEADD(hour, 3, s.new_siparistarihi) AS date)` = `semantic_mkt_launch_daily.siparis_adet` gün gün (UTC→İstanbul dönüşümü M7'deki yöntemle aynı; +3 sabit ofset yerine köprünün mevcut dönüştürücüsü kullanılıyorsa o).
2. **Faturalı satış**: `budget_sources.sales_sql` mantığıyla gün kırılımı — `SELECT CAST(S.DATE_ AS date), SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE -S.AMOUNT END) FROM dbo.LG_{firma}_01_STLINE S JOIN dbo.LG_{firma}_ITEMS I ON I.LOGICALREF = S.STOCKREF WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9) AND I.CODE = '<kod>' AND S.DATE_ >= '<D>' AND S.DATE_ < '<D+31>' GROUP BY CAST(S.DATE_ AS date)` = `fatura_net_adet`; `veri_sonu_logo` = `data_end_sql` sonucu.
3. **Bekleyen**: Baskı Öneri'nin `crm_bekleyen_siparis.sql` sorgusunun o stok kodu satırı = ekrandaki «açık sipariş»; ayrıca `SELECT SUM(b.new_adet) FROM Timas_MSCRM.dbo.new_bekleyenurunBase b JOIN Timas_MSCRM.dbo.ProductBase p ON p.ProductId = b.new_urunid WHERE b.statuscode = 1 AND p.ProductNumber = '<kod>'` = ekrandaki «bekleyen ürün» (iki ayrı satır, ayrı etiket).
4. **Dağılım**: `new_siparistipi = 2` siparişlerin satır adedi toplamı ve bayi sayısı (`COUNT(DISTINCT s.new_firmaid)`) = İzleme'deki «dağılım» satırı.
5. **Hedef payı**: `semantic_budget_approved_targets` + M46 aylık dağılımından D..D+6 gün payı = `hedef_payi_adet` toplamı (M46 izleme yöntemiyle aynı gün oranı).
6. **Etkinlik**: `SELECT COUNT(*), SUM(new_SatilanKitapAd) FROM Timas_MSCRM.dbo.new_etkinlikBase WHERE new_lgiliKitap = '<kitap>' AND statuscode = 100000002` = Etkinlikler sekmesi toplamı.
7. **Rapor**: D+7 raporundaki her rakam `rakam_json`'daki SQL sonucuyla aynı; özet metninde tabloda olmayan rakam yok (sayı çıkarıp karşılaştıran test); ekranda teknoloji adı 0.
8. **Dış kanal**: kod tabanında M16'nın hiçbir dış platforma (sosyal, e-posta pazarlama, T-soft) yazan çağrısı yok (statik tarama).

**Bağımlılık**: M15 (onaylı plan ve çekirdek) önce. M46 hazır. M29/M12 isteğe bağlı (yoksa CRM okuma). M19 paralel. M20/M22 sonra bağlanır.

**Tahmini büyüklük**: M (1–2 gün; çekirdek hazırsa).
