# M15 — Yeni Kitap Pazarlama Planı ve Materyalleri: kullanıcı ihtiyaç analizi

Durum: kod var (main) — test sunucusunda kabul 10/11 (2026-09-28 06:40; kalan: plan PDF'i 500) · Analiz tarihi: 2026-09-28 · Kaynaklar: `specs/M15.txt` (ZEKİ_Moduller3.html), `ZEKİ_Veri_Haritasi2.html` (M46 Bütçe & Satış Hedefleri, Editöryal Girdiler, Pazar & Satış Girdileri), `configs/semantic/knowledge/crm/table_descriptions.json` (CRM MetadataSchema, döküm 2026-09-09), `configs/semantic/knowledge/crm/OKUNUR-TABLOLAR.md`, `docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`, `docs/analiz/crm-eticaret-entegrasyon-2026-09-27.md`, `docs/analiz/kitap-yazar-web-taramasi-2026-09-24.md`, `docs/analiz/seo-geo-modul-2026-09-25.md`, `docs/analiz/studyo-sayfa-plani-sozlesme.md` («J: Pazarlama kiti»), `docs/analiz/yetki-mekanizmasi-2026-09-27.md`, `docs/audits/crm-kullanici-bilgileri-2026-09-14.md`, `docs/GELISTIRME-GUNLUGU.md` (M46 girişi, 2026-09-28), `backend/semantic_bridge/budget.py`, `budget_sources.py`, `budget_api.py`, `access.py`, `access_catalog.json`, `seo_geo/seasons.py`, `seo_geo/__init__.py`, `web_watch.py`, `author_relations.py`, `apps/editor/src/editor/production/marketing.py` + `api_marketing.py`, `src/canvas/nav/navModel.ts`, `src/canvas/stitch/ModulesMenu.tsx`, `apps/editor/docs/TUM-KITAP-TURLERI-ANALIZ.md`, kullanıcı belleği (seo-geo-module, tsoft-no-write, customer-vm-web-watch-off, web-watch-open-sources, editor-book-visuals-qwen-image, no-tech-names-on-screens, sales-are-invoiced-lines, logo-155-frozen-copy, system-of-record-logo, no-silent-limits-rule, llm-gate, vllm-choice-logprobs).

> Kural: sunucuya bağlanılmadı. Sayılar yalnız depodaki ölçümlerden alındı. CRM tablo satır sayıları CRM tablo sözlüğünün 2026-09-09 dökümündendir (canlı .28'de yeniden **ölçülecek**). Ölçülmemiş her şey **ölçülecek**, kanıtsız her iddia **varsayım** diye işaretlidir.

## 1. Modül ne işe yarar

Yayına hazırlanan her yeni kitap için tek bir **pazarlama planı paketi** üretir: kitap karnesi (yazarın geçmişi, emsal kitapların gerçek satışı, hedef kitle), M46'dan gelen onaylı satış hedefi, kanal ve bütçe dağılımı, yayın gününden geri sayan eylem takvimi ve materyal brief'leri (arka kapak, föy, basın bülteni, sosyal medya ve e-bülten taslakları). Plan pazarlama yöneticisinin onayından geçer; onaylanan plan M16 (lansman), M18 (aylık plan), M19 (görsel/metin üretimi), M20–M23 (basın, reklam, sosyal medya, influencer) için tek girdi olur.

TİMAŞ'ın bugünkü sorunu: planın parçaları CRM'de var ama dağınık ve birbirine bağlı değil. Proje kartında pazarlama önceliği, basın/kampanya/toplam pazarlama bütçesi, 3 ve 12 aylık potansiyel satış, «pazarlama ayrıntısı» serbest metni (`new_projeBase`); kitap kartında föy metni, basın bülteni, sosyal medya metni, planlanan tanıtım ve reklam mecraları (`new_kitapBase`); harcama ayrı varlıklarda («Pazarlama Bütçe Modülü», «Reklam»). Kitap bazlı satış hedefi CRM'de hiç dolu değil (`new_ilkyilsatishedefi` 2023–2028 kayıtlarında 0 — M46 ölçümü); hedef artık M46'dan geliyor. Emsal kitapların satışı (CRM'de 19.424 emsal çifti var) Logo satışıyla yan yana hiçbir ekranda görünmüyor; plan ile gerçekleşen karşılaştırılamıyor (harcama CRM'de, satış Logo'da, iki ayrı SQL sunucusu).

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| Kitap pazarlama sorumlusu (planın sahibi) | Pazarlama. Kanıt: CRM proje kartında `new_pazarlamasorumlusuid` («Pazarlama Sorumlusu») alanı; CRM ekip üyeliği «Pazarlama» 35 kişi (canlı CRM, 2026-09-15) | Her gün; yeni kitap başına 3–6 hafta yoğun | Masaüstü |
| Pazarlama müdürü (onaycı) | Pazarlama. Kanıt: CRM «Reklam» ve «Promosyon Bütçesi» varlıklarında `new_pazarlamayoneticisionayi` alanı | Haftada birkaç kez (onay, öncelik) | Masaüstü; onay telefonda |
| Dijital pazarlama / sosyal medya uzmanı | Pazarlama (varsayım: CRM pazarlama tipi seçeneklerinde «Sosyal Medya» ve «Dijital Pazarlama» ayrı) | Plan başına birkaç kez | Masaüstü |
| Basın ve halkla ilişkiler sorumlusu | Pazarlama (varsayım: pazarlama tipi «Basın», «Medya»); ayrıntı M20 analizinde | Plan başına | Masaüstü |
| Yayın yönetmeni / kitabın editörü | Editörya (ekip 54 kişi). Kanıt: CRM reklam planında `new_editortalonay` («Editoryal Onay») | Kitap başına 1–2 kez (metin doğruluğu, konumlama) | Masaüstü |
| Grafik tasarımcı (brief alıcı) | Grafik (ekip 13 kişi) | Plan başına | Masaüstü |
| Genel müdür (üst bütçe onayı) | Yönetim. Kanıt: CRM reklam planı ve promosyon bütçesinde `new_genelmuduronayi` | Eşiği aşan bütçede | Telefon |
| Satış müdürü (okuyucu) | Satış (ekip 49 kişi) | Ayda birkaç kez (ilk dağılım, M29) | Masaüstü |

Rol ↔ kişi eşlemesi veride zayıf: CRM `SystemUser` unvan/birim alanları neredeyse boş (JobTitle 0/186), departman yalnız ekip üyeliğinden okunuyor. Hangi kişinin hangi rolde olduğu **uzmana sorulacak**; AD grup dökümü yetki analizinde hâlâ açık (`yetki-mekanizmasi` §11).

## 3. Bugün bu iş nasıl yapılıyor

- **Kitap pazarlama sorumlusu** (CRM izine dayanan **varsayım**): yayın kurulu aşamasında proje kartına pazarlama önceliği (%), basın/kampanya/toplam pazarlama bütçesi ve «pazarlama ayrıntısı» girilir; kitap kartına föy metni (4.653 kitapta dolu), arka kapak (9.373), spot (6.869), basın bülteni, sosyal medya metni, hashtag (3.587) ve «Kitabın planlanan tanıtım ve reklam mecraları» serbest metni yazılır (dolu sayılar `crm-eticaret-entegrasyon-2026-09-27.md`; basın bülteni, sosyal medya metni ve mecra alanlarının doluluğu **ölçülecek**). Planın kendisi, takvim ve kanal dağılımı için CRM'de nesne yok → Word/Excel + e-posta (**varsayım**). Adım sayısı: en az 4 ayrı ekran/belge. Tıkanma: benzer kitapların gerçek satışını bulmak için Logo raporu ya da satışa sormak gerekiyor; hedef yok.
- **Harcama kaydı**: CRM «Pazarlama Bütçe Modülü» (`new_pazarlamamoduluBase`, 435 kayıt; tip Basın/Medya/Promosyon/Sosyal Medya/Dijital Pazarlama/Satış Kampanyası, mecra alt tipleri, tutar, başlangıç–bitiş, kitap bağı 202) ve «Reklam» (`new_reklamplaniBase`, 71 kayıt; editoryal → pazarlama yöneticisi → genel müdür onayı, fatura no, gerçekleşen teslim). Bu kayıtların 2026'da hâlâ girilip girilmediği **ölçülecek** (CRM'de «ölü modül» örnekleri var: haberler 2025-06, iş planı 2025-12).
- **Pazarlama müdürü**: onay CRM onay kutularıyla (reklam planı) ya da e-postayla (**varsayım**). Plan–hedef–gerçekleşen karşılaştırması yok.
- **Editör**: arka kapak ve tanıtım metinlerini CRM'e yazıyor; Kitap Tasarım Stüdyosu'nda işi olan kitaplarda «Pazarlama kiti» arka kapak, ürün sayfası, sosyal görsel ve öğretmen kılavuzu taslağı üretiyor (studio J, test sunucusunda).
- **Grafik**: brief'i e-postayla ya da yüz yüze alıyor (**varsayım**); CRM üretim kartında «Dosyaların grafik teslim tarihi» alanı var.

## 4. İhtiyaçlar ve acı noktaları

**Kitap pazarlama sorumlusu**
1. Yayına kaç gün kaldığını ve planı eksik kitapları tek listede görmek (yayın tarihi CRM'de üç yerde: proje «önerilen yayın tarihi», kitap «ilk baskı tarihi», üretim «dağılım/depo giriş tarihi»).
2. Emsal ve yazar geçmişini rakamla görmek: emsal kitapların ilk 3/6/12 ay net satışı (Logo, iade düşülmüş, faturalı).
3. CRM'de zaten yazılı metinleri yeniden yazmamak; plan onları kaynağıyla göstermeli.
4. Kanal/bütçe önerisinin gerekçeli gelmesi, elle düzeltmenin yeniden hesapta korunması.
5. Takvimin yayın gününden geri sayarak kendiliğinden kurulması.

**Pazarlama müdürü**
1. Onay bekleyen planları, bütçe toplamını ve kitabın M46 hedefini tek satırda görmek.
2. Aynı ayda çakışan lansmanları ve toplam bütçeyi görmek (M18'e köprü).
3. Onayın kaydı: kim, ne zaman, hangi sürümü onayladı.

**Editör / yayın yönetmeni**
1. Materyal metinlerinde kitabın içeriğine aykırı iddia olmaması (alıntı birebir kitaptan).
2. Kendi onayının pazarlama onayından ayrı görünmesi.

**Genel müdür**
1. Eşik üstü bütçede tek ekranda gerekçe + hedef + emsal görüp telefondan onaylamak.

## 5. Nasıl kullanmak isteyecekler

### Kullanıcı hikâyeleri
- Kitap pazarlama sorumlusu olarak **önümüzdeki 120 günde yayımlanacak ve planı olmayan kitapları** görmek istiyorum, çünkü planı geç başlayan kitap lansmanı kaçırıyor.
- Kitap pazarlama sorumlusu olarak **tek tuşla Zeki AI'ın kitap karnesi ve kanal/bütçe önerisini** almak istiyorum, çünkü emsal araştırması bugün yarım gün sürüyor.
- Kitap pazarlama sorumlusu olarak **CRM'deki föy, arka kapak ve basın bülteni metnini kaynağıyla plana çekmek** istiyorum, çünkü aynı metni üç kez yazmak istemiyorum.
- Kitap pazarlama sorumlusu olarak **planı PDF olarak satış ve grafik ekibine** göndermek istiyorum, çünkü onlar portalda plan açmayacak.
- Pazarlama müdürü olarak **onay kuyruğumu, her planın hedefini ve bütçesini** görmek, gerekçe yazarak geri göndermek istiyorum, çünkü onay bugün e-posta zincirinde kayboluyor.
- Pazarlama müdürü olarak **M46 hedefi değişen kitapların planını** işaretli görmek istiyorum, çünkü hedef değişince bütçe değişmeli.
- Editör olarak **materyal taslaklarında kitaptan alıntıların birebir doğrulandığını** görmek istiyorum, çünkü yanlış alıntı yayınevinin itibarını bozar.
- Genel müdür olarak **eşik üstü bütçeli planı telefonda tek ekranda onaylamak** istiyorum.

### Ana ekranlar ve akış
- **İlk açılış (`/pazarlama/yeni-kitap`)**: üstte dört sayı kartı — «Planı yok (yayına ≤ 60 gün)», «Onay bekleyen», «Materyali eksik», «Hedefi değişen». Altında kitap listesi: kapak küçük resmi, ad, yazar, yayınevi, yayın tarihi + kaynağı, kalan gün, M46 hedefi (adet/ciro), plan durumu, bütçe, sorumlu. Varsayılan süzgeç «Bana düşenler» (sorumlu olduğum + onayımı bekleyen). Liste tavansız, sanal kaydırmalı; süzgeçler yayınevi, kitaplık, hedef kitle, durum.
- **Plan ekranı (`/pazarlama/plan/:id`)**: sekmeler Karne · Kanal ve bütçe · Takvim · Materyaller · Onay ve geçmiş. Sağ sütunda Zeki AI önerisi ve gerekçesi.
- En sık üç işlem:
  1. Taslak planı oluşturmak: listede kitap → «Zeki AI taslağı hazırla» → 2 tık (taslak arka planda kurulur, hazır olunca plan açılır).
  2. Bütçe satırını düzeltmek: satır içinde tutar/tarih → 1 tık + yazma; toplam ve hedefe oran anında yenilenir.
  3. Onaya göndermek / onaylamak: 1 tık (+ isteğe bağlı gerekçe); geri göndermede gerekçe zorunlu.

### Zeki AI'ya soracakları (gerçek iş dilinde)
1. «Bu kitabın emsallerinden hangisi ilk üç ayda en iyi sattı, o kitaba ne yapmıştık?»
2. «Aynı kitaplıktaki romanlar son iki yılda ilk 12 ayda ortalama kaç adet sattı?»
3. «Yazarın önceki kitaplarının 2025 net satışı ve iade oranı ne?»
4. «Ekim'de yayımlanacak çocuk kitaplarının toplam pazarlama bütçesi ve hedef cirosu ne?»
5. «Bu plandaki bütçe hedef cironun yüzde kaçı; emsallerde bu oran neydi?»
6. «Öğretmenler günü haftasına denk gelen yeni kitaplar hangileri?»
7. «Basın bütçesi en yüksek beş planı ve onay durumlarını göster.»
8. «Bu kitap için üç farklı sosyal medya gönderisi taslağı yaz, kitaptan birebir alıntı kullan.»

### Otomasyon katmanı
(K1 tam otomatik · K2 Zeki önerir, insan onaylar · K3 Zeki analiz eder, insan karar verir · K4 insan yapar, sistem yalnız kaydeder — K4 bu analizin yorumudur, iş tanımında yok.)

| Adım | Katman | Not |
|---|---|---|
| Plan bekleyen kitap listesi, kalan gün | K1 | CRM + üretim tarihlerinden |
| Kitap karnesi rakamları (yazar geçmişi, emsal satışı, hedef kitle) | K1 | SQL; model rakam üretmez |
| M46 hedefinin plana alınması, hedef değişince işaret | K1 | `targets` + `deviations?kind=revizyon` |
| Takvim iskeleti (yayın gününden geri sayım) | K1 | Şablon; kullanıcı değiştirir |
| Kanal önceliği ve bütçe dağılımı | K2 | Zeki AI gerekçeli önerir, sorumlu düzeltir, müdür onaylar |
| Materyal taslakları (föy, basın bülteni, sosyal, e-bülten konu satırı, video senaryosu) | K2 | Kitapta birebir aranmayan alıntı düşer |
| Basın listesi / influencer eşleşmesi | K2 | M20 / M23'ten gelir; ilk sürümde yok |
| Bütçe revizyonu (hedef değişince) | K3 | Zeki AI farkı ve etkisini gösterir, karar insanda |
| Toplam pazarlama bütçesi tavanı, dış ajans seçimi | K4 | İnsan kararı, sistem kaydeder |

### Bildirim / uyarı
- Plan onaya gönderildi → onaycıya e-posta (köprünün SMTP ayarı `alerts.smtp_settings`) + Uyarılar rozeti.
- Yayına 60 / 30 / 14 gün kala planı onaylı olmayan kitap → sorumluya ve müdüre, günde bir özet e-posta (tek tek değil).
- Yayına 21 gün kala onaylı materyali eksik plan → sorumluya.
- M46'da onaylı plan değişti (`deviations?kind=revizyon`) → hedefi değişen kitapların plan sahiplerine.
- Plan onaylandı / geri gönderildi → plan sahibine.
- SMTP ya da alıcı yoksa bildirim kayıtta bekler ve ekranda «gönderilemedi: e-posta ayarı yok» yazar (M46 davranışıyla aynı).

### Onay ve yetki
- Görür: `sayfa:pazarlama-yeni-kitap` olan herkes. Bütçe tutarları `ozellik:pazarlama.butce-gor` ile (satış ve grafik ekibi planı tutarsız görebilir).
- Değiştirir: `ozellik:pazarlama.plan-yaz` (taslak, düzenleme, Zeki AI önerisi, materyal taslağı, onaya gönderme; «Bütün» ile gelir).
- Onaylar: `ozellik:pazarlama.plan-onay` (açıkça verilir; gönderen onaylayamaz). Eşik üstü bütçe: `ozellik:pazarlama.butce-ust-onay` (açıkça verilir). Eşik Yönetim → «Pazarlama» ayarında girilir; girilmemişse ikinci onay istenmez (sayı uydurulmaz).
- Editoryal onay (materyallerde): `ozellik:pazarlama.materyal-editoryal-onay` (açıkça verilir) — CRM'deki «Editoryal Onay» kutusunun karşılığı.
- Dışa aktarma (PDF/CSV): mevcut `ozellik:veri.disa-aktar`.

## 6. Veri

| Gereken veri | Kaynak | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Yeni kitap listesi ve yayın tarihi | CRM `new_kitapBase.new_ilkyayintarihi`, `new_projeBase.new_nerilenYaynTarihi` / `new_hedeflenenbaskitarihi` / `new_yayintarihi`, `new_UretimBase.new_dagilimtarihi` / `new_DepoGiriTarihi` | Alanlar var (tablo sözlüğü); M46 2026 CRM'inde 1.041 yayın tarihli kayıttan 563'ünü yeni kitap saydı | Üç tarihten hangisinin «yayın günü» olduğu **uzmana sorulacak**; doluluk **ölçülecek** |
| Onaylı satış hedefi (adet, ciro, marj, aylık dağılım) | M46 `GET /api/v1/budget/targets?year=&segment=yeni&stok=` | Main'de (f2f85077); sözleşme günlükte | Onaylı plan yoksa `plan:null` — ekran «hedef henüz onaylanmadı» der |
| Kitap bazlı pazarlama bütçesi çerçevesi | İş tanımı M46'dan bekliyor | M46'da **yok** (kitap hedefi + departman gideri var, kitap bazlı pazarlama bütçesi yok) | Kural **uzmana sorulacak** (yüzde mi, öncelik sınıfı mı); M46'ya departman bütçesi ucu gerekebilir |
| CRM'deki mevcut pazarlama bütçesi ve öncelik | `new_projeBase.new_basinbutcesi`, `new_kampanyabutcesi`, `new_toplampazarlamabutcesi(_kurulsonucu)`, `new_pazarlamaonceligi`, `new_kitabinpazarlamaonceligi`; `new_kitapBase.new_toplampazarlamabutcesi` | Alanlar var | Doluluk **ölçülecek** |
| Yazar geçmişi | CRM `new_eserkatilimBase` + `new_katilimcitipiBase.new_name = N'Yazar'` → `new_kitapBase.new_StokKodu`; Logo `LG_{firma}_01_STLINE` | Yazar koşulu `author_relations.py`'de yazılı; satış SQL'i `budget_sources.sales_sql` | Yok (ölçülebilir) |
| Emsal kitaplar | CRM `new_new_kitap_new_emsalkitap3Base` (kitap↔kitap, 19.424 çift) | Tablo sözlüğünde | Yeni kitapların kaçında emsal girildiği **ölçülecek**; yoksa Zeki AI aynı kitaplık + hedef kitle + tür + fiyat bandından aday önerir (K2) |
| Emsalin ilk 3/6/12 ay satışı | Logo STLINE (faturalı, iade eksi) + emsalin `new_ilkyayintarihi` | Tanım M46 ile aynı | Logo .155 kopyası 2026-08-17'de bitiyor; 2025 ve öncesi tam |
| Hedef kitle | CRM `new_hedefkitle` (%98,5 dolu), yaş başlangıç/bitiş, sınıf, sosyoekonomik ve entelektüel düzey lookup'ları, `new_turlertext` (%53) | `TUM-KITAP-TURLERI-ANALIZ.md` | Demografi (M38/M39 okur analizi) **yok**; sosyoekonomik alan doluluğu **ölçülecek** |
| Rakip kitap | CRM `new_rakipkitapBase` (30.415; ad, yayınevi, satış adedi, liste fiyatı, tanıtım metni) + bağ `new_new_kitap_new_rakipkitapBase` (214) | Tablo sözlüğünde | «Satış adedi» alanının kaynağı ve güncelliği **ölçülecek**; web kazıma ve Amazon/Trendyol API'si **yok** (bot koruması, kural) |
| Önceki kampanya sonuçları | CRM pazarlama bütçe modülü (435), reklam (71), `new_kampanyaBase` (308; planlanan/gerçekleşen ciro) | Tablo sözlüğünde | Kitap bazlı harcama ↔ satış bağı kurulmamış; 2026 kullanımı **ölçülecek** |
| Mevcut materyal metinleri | CRM `new_ozet`, `new_kitapspotu`, `new_TantmFyMetni`, `new_tanitimfoymetni`, `new_BasnBlteni`, `new_sosyalmedyametni`, `new_hastag`, `new_AnahtarKelimeler`, `new_kitabinenonemlicumlesi`, `new_alintlar`, `new_KitabnPlanlananTantmveReklamMecralar` | Doluluğun bir kısmı ölçülü (`crm-eticaret`) | Basın bülteni / sosyal medya metni doluluğu **ölçülecek** |
| Kapak | M13 / stüdyo kapağı; CRM `new_resimurl` (göreli yol, 7.886 kitapta) | Stüdyo kapak üretiyor | CRM göreli yolunun tam adresi **ölçülecek** (T-soft görsel adresi SEO modülünde okunuyor) |
| Yazar biyografi ve fotoğraf | Kullanıcı girer; CRM kişi kartı; stüdyo `front.bios_for_author` | Kısmen | Fotoğraf kullanım hakkı kaydı yok |
| Özel günler | CRM `new_ozelgunlerBase` (93) + kitap bağı (~820); SEO sezon takvimi tabloları | `seo_geo/seasons.py` okuyor | — |
| Tahmini baskı tarihi | M12 üretim takvimi; bugün CRM `new_UretimBase` | M12 durumu bu analizde doğrulanmadı | M12 sözleşmesi netleşince bağlanır |
| Satış tahmini (ilk baskı) | M10 | Durumu doğrulanmadı | M10 hazır olunca karneye «tahmin» satırı |

## 7. Diğer modüllerle bağ

- **Girdi**: M46 (onaylı kitap hedefi, aylık dağılım, revizyon uyarısı) · M1 (kurul kararı, proje kartı, pazarlama bütçesi ön değeri) · M5 (yayın onayı → plan kesinleşir) · M12 (baskı/dağılım tarihi) · M13/M14 ve stüdyo (kapak, arka kapak, pazarlama kiti) · M10 (ilk baskı satış tahmini) · M7 (yazar ilişkisi, etkinlik uygunluğu) · SEO sezon takvimi (özel gün).
- **Çıktı**: M16 (onaylı plan → lansman paketi) · M18 (planın aylık takvime düşmesi, bütçe toplamı) · M19 (materyal brief'leri) · M20 (basın bülteni taslağı, hedef medya) · M21 (dijital bütçe satırları) · M22 (sosyal içerik takvimi) · M23 (influencer brief) · M29 (satışa plan özeti) · M25 (onaylı ürün sayfası metni SEO önerisi olarak — mevcut `external_proposal`).

## 8. Kısıtlar

- **CRM'e yazma yok**: iş tanımındaki «Dynamics CRM'de kampanya kaydı oluşturulur» yapılamaz. Plan köprünün kendi tablolarında durur; ekranda «CRM'e işlenecek» listesi (kitap kartına yazılacak onaylı föy/basın bülteni/sosyal metin, pazarlama bütçe modülüne girilecek satırlar) verilir, kopyalanır ya da CSV indirilir (M6'daki «CRM'e işlenmesi gereken fark» kalıbı).
- **Logo'ya yazma yok.** Logo yalnız gerçekleşmiş satış için okunur (satış = faturalı satır, net ciro = LINENET).
- **T-soft'a yazma yasak**: ürün sayfası metni yalnız SEO modülüne öneri olarak düşer.
- **Web kazıma yok**: iş tanımındaki «web scraper + Amazon/Trendyol API» rakip verisi yapılmaz; rakip bilgisi CRM rakip kitap tablosundan. Müşteri VM'inde basın/web taraması kapalı.
- **Ekranda teknoloji adı yok**: «Zeki AI». Görsel modelin ürettiği görseller ticari izin gelene kadar «taslak — ticari kullanım izni bekleniyor» etiketli (stüdyo kuralı).
- **Demo veri yok, sayı tavanı yok** («top 20 emsal» değil; bütün emsaller, sıralı).
- **Veri sonu**: Logo .155 kopyası 2026-08-17'de bitiyor; karnedeki her Logo rakamının yanında «veri sonu» tarihi yazılır.
- **Hukuki/KVKK**: reklam metninde kanıtsız üstünlük iddiası («en çok satan», «bir numara») yazılmaz — Zeki AI taslağında yasaklı kalıp listesi; iddia varsa kanıt (Logo sırası) gösterilir; hukuk birimine doğrulatılmalı (**varsayım**: Ticari Reklam ve Haksız Ticari Uygulamalar Yönetmeliği kapsamı). Yazar fotoğrafı ve alıntı kullanım hakkı sözleşmeye (M6) bağlı. Basın/influencer listesindeki kişisel veriler CRM'den okunur, dışa aktarım yetkiyle.

## 9. Kapsam önerisi

**İlk sürüm** (en çok değer, en az bağımlılık — yalnız M46 ve CRM/Logo okuma):
- Plan bekleyen yeni kitap listesi (CRM tarihleri + kaynak etiketi, kalan gün, M46 hedefi, durum).
- Kitap karnesi: yazar geçmişi (Logo), emsal kitapların ilk 3/6/12 ay satışı (CRM emsal + Logo), hedef kitle ve tür (CRM), rakip kitaplar (CRM), CRM'deki proje bütçe/öncelik değerleri.
- Plan: kanal/bütçe satırları (CRM pazarlama tipi kümesiyle), takvim (şablon + düzenleme), durum makinesi ve onay (gönderen onaylayamaz, eşik üstü ikinci onay), geçmiş, PDF/CSV.
- Zeki AI: kanal/bütçe önerisinin gerekçesi, föy/basın bülteni/sosyal/e-bülten taslakları (kitap metni stüdyodaysa stüdyo pazarlama kitine yönlendirme; değilse CRM metinlerinden).
- «CRM'e işlenecek» listesi.
- Sözleşme ucu (M16/M18/M19 okur).

**Sonraki sürüm**:
- Plan ↔ gerçekleşen: CRM pazarlama bütçe modülü/reklam harcamasının plan satırlarına eşlenmesi; lansman sonrası 90 gün satış/hedef.
- Önceki kampanya etkisi (CRM kampanya + sipariş kampanya kodu).
- M20/M23 bağları (basın listesi, influencer eşleşmesi), M10 tahmini, M12 kesin baskı tarihi.
- Onaylanan plan ve metinlerin M50 eğitim verisi olarak dışa aktarılması (iş tanımındaki SFT; model eğitimi bu modülde yapılmaz).

**Mevcut kodda yeniden kullanılacaklar**
- `backend/semantic_bridge/budget_sources.py`: `runner`, `firms_by_year`, `sales_sql`, `data_end_sql`, `read_books` (Logo/CRM okuma, yıl → firma).
- `backend/semantic_bridge/budget.py`: `approved_targets(engine, tenant, year, codes=, segment=)` (köprü içi hedef okuma), onay deseni (gönderen onaylayamaz, sürüm/arşiv).
- `backend/semantic_bridge/budget_api.py`: `register(app, rt, require_caller, can)` kalıbı, `_send_mail`.
- `backend/semantic_bridge/seo_geo/seasons.py`: özel gün ↔ kitap bağı.
- `backend/semantic_bridge/seo_geo/__init__.py` `external_proposal`: ürün sayfası metnini SEO önerisi yapmak.
- `backend/semantic_bridge/editorial_studio_marketing.py` + `apps/editor/src/editor/production/marketing.py`: arka kapak, ürün sayfası, sosyal görsel, öğretmen kılavuzu (stüdyo işi olan kitaplarda).
- `backend/semantic_bridge/author_relations.py`: CRM yazar koşulu.
- `src/canvas/components/SearchSelect.tsx`, `src/canvas/budget/*` (sekme düzeni, taslak/onay ekranı), `CardSql.tsx` (rakamın SQL'i).

## 10. Uzmanlara sorulacak sorular

1. Bugün yeni kitap pazarlama planı hangi belgeyle yapılıyor, hangi aşamada başlıyor (kurul onayı mı, yayın onayı mı) ve yayından kaç hafta önce kesinleşmeli?
2. Yayın günü olarak hangi tarih esas: proje «önerilen yayın tarihi», kitap «ilk baskı tarihi» mi, üretim «dağılım tarihi» mi?
3. Kitap başına pazarlama bütçesi nasıl belirleniyor (hedef cironun yüzdesi, öncelik sınıfı, sabit tutar)? Genel müdür onayı hangi tutarın üstünde gerekiyor?
4. CRM «Pazarlama Bütçe Modülü» ve «Reklam» kayıtları bugün de tutuluyor mu; kitap bazlı harcamanın doğru kaynağı hangisi (yoksa Logo masraf merkezi mi)?
5. Emsal kitap (CRM «emsal kitap» bağı) kim tarafından ve hangi aşamada giriliyor; güvenilir mi?

## 11. Başarı ölçütü

- Yayından 30 gün önce onaylı planı olan yeni kitap oranı (ekranda, aylık); hedef iş birimiyle konuşulur, sayı uydurulmaz.
- İlk taslaktan onaya geçen süre (plan geçmişinden ölçülür; ilk ay taban alınır).
- Zeki AI kanal/bütçe önerisinin onaylanan plandaki satırlarla örtüşme oranı ve materyal taslaklarının düzeltmesiz onay oranı.
- Onaylı planların %100'ünde M46 hedefi ve «veri sonu» tarihi görünür.
- Lansman sonrası 90 gün: plan bütçesi / net ciro ve hedefe ulaşma oranı (sonraki sürüm).
- Kullanım: haftalık aktif pazarlama kullanıcısı, «CRM'e işlenecek» listesinin kapanma oranı.

## 12. Uzman gözüyle en iyi sistem

**Kim konuşuyor:** 15 yıllık yayınevi pazarlama müdürü.

**Sektörde iyi örnekler nasıl yapıyor** (genel sektör uygulaması; TİMAŞ'ta doğrulanmadı): büyük yayınevleri her yeni başlık için yayın tarihinden geri sayan bir **başlık pazarlama planı** tutar; planın kalbi **emsal başlıklar** (comp titles) ve onların gerçek satışıdır. Satış ekibine giden tek sayfalık **ön bilgi föyü** (advance information sheet) yayından aylar önce hazırdır. Başlık yönetim yazılımları (title management) planı, meta veriyi, materyal durumunu ve bütçeyi tek kayıtta tutar; her bütçe satırının sahibi ve ölçüsü vardır; lansman sonrası 4., 12. ve 26. haftada «plan tuttu mu» incelemesi yapılır.

**TİMAŞ için mükemmel sistem:** kitap kurul onayını aldığı an planı olan, emsallerin Logo satışını kendiliğinden getiren, CRM'deki metinleri yeniden yazdırmayan, hedefle bağlı ve onayı iki tıkta biten bir plan; plan onaylanınca lansman, aylık takvim ve içerik üretimi kendiliğinden beslenir.

**Bir iş günü:**
- 08:45 — Pazarlama alanı açılır. Üst kartlar: 3 kitap yayına 30 gün kala planı onaysız, 1 kitabın M46 hedefi dün revize edildi, 2 planda föy onaysız.
- 09:00 — Hedefi değişen kitabın planı: Zeki AI eski/yeni hedefi ve bütçe/hedef oranını yan yana koymuş, «bütçeyi %X düşür ya da hedefi koru» iki seçeneği gerekçesiyle sunmuş. Müdür birini seçer, not yazar.
- 09:30 — Onay kuyruğu: iki plan. Birinde basın bütçesi emsallerin iki katı; Zeki AI gerekçesi «yazar televizyon programına çıkıyor» notuna dayanıyor. Onaylar. Diğerini «emsal yanlış: çocuk kitabı değil gençlik» diye geri gönderir.
- 11:00 — Satış toplantısı öncesi: Ekim'de çıkacak 12 kitabın plan özetini PDF alır.
- 14:00 — Sorumlulardan biri yeni kitabın taslağını Zeki AI'dan alır: karne (yazarın 4 kitabı, emsal 7 kitap, ilk 12 ay satışları), önerilen kanal dağılımı, takvim, föy/basın bülteni/3 sosyal gönderi taslağı. Föyü düzeltir, editöre materyal onayına yollar.
- 16:30 — Müdür Zeki AI'a sorar: «Bu ay onaylanan planların toplam bütçesi pazarlama departman bütçesinin yüzde kaçı?»
- 17:30 — Gün sonu özeti e-postası: onaylanan 3 plan M18 takvimine düştü, 1 plan geri gönderildi.

**«Bunu görürsem hemen kullanırım» (3):**
1. Emsal kitapların ilk 3/6/12 ay gerçek net satışı tek tabloda, her rakamın SQL'i açılabilir.
2. Yayın gününden geri sayan takvim; eksik materyal ve geciken iş kırmızı.
3. Plan – hedef – harcama tek satırda; hedef değişince plan kendiliğinden işaretlenir.

**«Bunu yaparsanız kullanmam» (3):**
1. CRM'de zaten yazdığımız föyü, arka kapağı, bütçeyi forma yeniden yazdırmak (çift giriş).
2. Zeki AI'ın uydurma rakam ya da kanıtsız iddia («çok satan», takipçi sayısı) üretmesi.
3. Onayı beş adımlı bürokrasiye çevirmek ya da benim onayım olmadan dış kanala (sosyal medya, e-posta) kendiliğinden yayın yapmak.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (hangi tablo/görünüm/ölçü) | CRM (hangi varlık/alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Plan bekleyen kitap listesi | `LG_{firma}_ITEMS` (stok kartı açılmış mı; M46'daki «kartı yoksa yayımlanmamış» kuralı) | `new_kitapBase` (`new_ilkyayintarihi`, `new_Tip = 1`, `new_kitap_yayincilikstatusu`), `new_projeBase` (önerilen yayın tarihi, kurul sonucu), `new_UretimBase` (dağılım/depo giriş) | — | Liste deterministik; model gerekmez |
| Yazar geçmişi | `LG_{firma}_01_STLINE` faturalı satır (`INVOICEREF <> 0`, `LINETYPE = 0`, `CANCELLED = 0`, TRCODE 7/8/9 − 2/3), net adet, net ciro = LINENET; yıl → firma `L_CAPIPERIOD` (211 = 2021–2025, 411 = 2026) | `new_eserkatilimBase` + `new_katilimcitipiBase.new_name = N'Yazar'` → `new_kitapBase.new_StokKodu` | — | Rakam SQL'den |
| Emsal satışı (ilk 3/6/12 ay) | Aynı STLINE tanımı, emsalin ilk yayın tarihinden itibaren pencereler | `new_new_kitap_new_emsalkitap3Base`, emsalin `new_ilkyayintarihi` | Emsal girilmemişse aday seçimi: aynı kitaplık/hedef kitle/tür/fiyat bandındaki kitaplardan «bu kitaba emsal mi?» evet/hayır — kapalı küme, tek token + olasılık; düşük marj «belirsiz» | Emsal seçimi yargıdır; rakam yine SQL |
| Hedef kitle ve konumlama özeti | — | `new_hedefkitle`, yaş/sınıf/düzey, `new_turlertext`, `new_ozet`, `new_kitapspotu`, `new_kitabinonecikanyanlari` | 3–4 cümlelik hedef okur ve konumlama özeti (kaynak alanlar gösterilir) | Dağınık metni özetler |
| Rakip kitaplar | — | `new_rakipkitapBase` + bağ tablosu | Rakip tanıtım metinlerinden «fark» maddeleri (taslak) | Metin karşılaştırma |
| M46 hedefi | (M46 kendi Logo okumasını yapar) | — | — | `GET /api/v1/budget/targets` |
| Kanal ve bütçe önerisi | Emsallerin satışı (yukarıdaki ölçü) | Emsallerin pazarlama bütçe modülü/reklam kayıtları (`new_pazarlamamoduluBase` + kitap bağı, `new_reklamplaniBase` + kitap bağı), proje bütçe alanları | Kanal payı önerisi **kural + emsal oranlarıyla** hesaplanır (kod); model yalnız gerekçe cümlesini yazar ve kanal sırası için kısa açıklama verir | Bütçe rakamını model üretmez |
| Takvim | — | Özel günler (`new_ozelgunlerBase` + bağ), yazar etkinlikleri (`new_etkinlikBase`) | — | Şablon + tarih hesabı |
| Materyal taslakları | — | CRM metin alanları (kaynak); stüdyo işi varsa kitabın tam metni stüdyoda | Föy, basın bülteni, sosyal gönderi (3 platform), e-bülten konu satırı, 30–60 sn video senaryosu taslağı; alıntılar metinde birebir aranır, bulunmayan düşer | Asıl model değeri burada |
| Onay, geçmiş | — | — | — | Deterministik |
| Doğal dil soru | Katalog ölçüleri (net ciro satır, satılan adet) | Katalogdaki CRM varlıkları | Sohbet hattı (mevcut `/api/v1/ask`) | Ekranda «Zeki AI'a sor» kutusu mevcut hattı kullanır |

Model çağrıları LLM kapısından: `rt.llm_for("marketing", NORMAL)` (ekrandaki «öneri al» — kullanıcı bekliyor) ve `rt.llm_for("marketing", BATCH)` (gece karne/aday ön hazırlığı). `LlmClient` doğrudan kurulmaz. Kapalı kümeli kararlar (emsal evet/hayır, kanal etiketi) `structured_outputs.choice` + `logprobs` ile tek token.

## 14. Kodlama planı (kodlayıcıya devir)

### Pazarlama çekirdeği (M15–M18 ortak; M15 kurar, diğerleri genişletir)
Paket `backend/semantic_bridge/marketing/` (SEO'daki `seo_geo/` paketi gibi):
- `__init__.py` — `register(app, rt, require_caller, can)` (`budget_api.register` kalıbı); `app.py`'de iki satır: `from semantic_bridge import marketing` + `app.state.marketing = marketing.register(app, rt, _require_caller, _can)`.
- `core.py` — tablolar (ilk kullanımda kurulur, `budget.py` gibi SQLAlchemy Core, `tenant_id` her tabloda), plan durum makinesi, geçmiş, `semantic_audit` yazımı.
- `sources.py` — Logo/CRM okuma (`budget_sources.runner/firms_by_year/sales_sql` yeniden kullanılır; CRM bağlantısı `SEMANTIC_CRM_CONNECTION_FILE`).
- `plans.py` — M15 iş mantığı (karne, öneri, materyal).
- `api.py` — uçlar.

**Tablolar**
- `semantic_mkt_plans`: `id` (`MP-<yıl>-<sıra>`), `tenant_id`, `kind` (`yeni|backlist|aylik`), `stok_kodu`, `crm_kitap_id`, `crm_proje_id`, `baslik`, `durum` (`taslak|onayda|onayli|geri|arsiv`), `surum`, `onceki_id`, `sahip` (AD hesabı), `yayin_tarihi`, `yayin_tarihi_kaynagi` (`crm-kitap|crm-proje|uretim|elle`), `hedef_json` (M46 `plan.id`, `version`, `hedef.adet/ciro/marj`, `aylik`), `butce_toplam`, `donem` (M18 için `YYYY-MM`), `olusturan`, `olusturma`, `gonderen`, `gonderme`, `onaylayan`, `onay_zamani`, `ust_onaylayan`, `ust_onay_zamani`, `gerekce`.
- `semantic_mkt_plan_lines`: `id`, `plan_id`, `kanal` (`basin|medya|promosyon|sosyal-medya|dijital|satis-kampanyasi|etkinlik|influencer|diger` — CRM `new_pazarlamatipi` kümesi + etkinlik/influencer), `alt_kanal` (CRM mecra tipi adı), `aciklama`, `tutar`, `baslangic`, `bitis`, `kpi_json`, `kaynak` (`zeki|kullanici|crm`), `gerekce`, `elle_duzeltildi`.
- `semantic_mkt_tasks`: `id`, `plan_id`, `tarih`, `gun_farki` (yayın gününe göre), `is`, `kanal`, `sorumlu`, `durum` (`bekliyor|yapildi|atlandi`), `kanit_url`, `materyal_id`.
- `semantic_mkt_materials`: `id`, `plan_id`, `stok_kodu`, `tur` (`foy|arka-kapak|basin-bulteni|sosyal|e-bulten-konu|video-senaryo|kapak-brief|influencer-brief`), `metin`, `kaynak` (`crm:<alan>|studio:<iş>|zeki|kullanici`), `durum` (`taslak|editoryal-onayli|onayli`), `onaylayan`, `onay_zamani`, `surum`, `dogrulama_json` (alıntı arama sonucu).
- `semantic_mkt_book_cards`: `stok_kodu`, `tenant_id`, `veri_json` (karne), `asof`, `veri_sonu` (Logo son fatura günü).
- `semantic_mkt_events`: `id`, `plan_id`, `zaman`, `kim`, `ne`, `eski_json`, `yeni_json`.

**Uçlar** (`/api/v1/marketing/…`)
- `GET meta` — kanallar, durumlar, eşik, veri sonu.
- `GET new-books?from=&to=&durum=&yayinevi=&sahip=` — plan bekleyen/planlı yeni kitaplar (tavan yok, sayfalı).
- `GET books/{stok_kodu}/card` — karne (önbellek + `?yenile=1`).
- `POST plans` `{kind:'yeni', stok_kodu|crm_kitap_id}` → taslak; `GET plans?kind=&durum=&sahip=&donem=`; `GET|PATCH plans/{id}`.
- `PUT plans/{id}/lines`, `PUT plans/{id}/tasks`.
- `POST plans/{id}/suggest` — Zeki AI kanal/bütçe gerekçesi + materyal taslakları (iş kuyruğu; `GET plans/{id}/jobs` durum).
- `POST plans/{id}/materials` (`{tur}` → taslak), `PUT materials/{mid}`, `POST materials/{mid}/approve` (`{seviye:'editoryal'|'pazarlama'}`).
- `POST plans/{id}/submit|approve|reject|revise` (onay; gönderen onaylayamaz → 409; eşik üstü ikinci onay).
- `GET plans/{id}/export.pdf`, `GET plans/{id}/export.csv`, `GET plans/{id}/crm-todo` («CRM'e işlenecek» listesi).
- `GET contract/plans?stok=&kind=&durum=onayli&donem=` — sözleşme ucu (M16, M18, M19, M20–M23 okur): onaylı planın satırları, takvimi, onaylı materyalleri.
- `POST run-due` (SYSTEM) — günlük hatırlatma + karne önbelleği tazeleme.

**Ekranlar**: `src/canvas/marketing/` — `MarketingHome.tsx` (sayı kartları), `NewBooksList.tsx`, `PlanScreen.tsx` (sekmeler `CardTab`, `ChannelsTab`, `CalendarTab`, `MaterialsTab`, `HistoryTab`), `api.ts`, `parts.tsx`. Rotalar (`src/App.tsx`): `/pazarlama/yeni-kitap`, `/pazarlama/plan/:id` (menüde `also`). Menü (`navModel.ts`, alan `pazarlama`): yeni bölüm **«Planlama»**, öğe `{ id: 'pazarlama-yeni-kitap', label: 'Yeni kitap planı', to: '/pazarlama/yeni-kitap', section: 'Planlama', also: ['/pazarlama/plan'] }`; alan ipucu `'Plan, içerik, SEO & GEO'`. Kampüs: `ModulesMenu.tsx` `LIVE.M15 = '/pazarlama/yeni-kitap'`, `GROUP_HOME['Pazarlama'] = { to: '/pazarlama/yeni-kitap', hint: 'Yeni kitap planı, lansman, backlist ve aylık plan' }` (M18 gelince `/pazarlama/aylik-plan`). Telefonda liste kart görünümü, onay düğmesi 44 px.

**Yetki** (`access_catalog.json` + `access.py`)
- Sayfa `sayfa:pazarlama-yeni-kitap` (alan `pazarlama`); `RULES`: `("/api/v1/marketing/", {page("pazarlama-yeni-kitap"), …diğer pazarlama sayfaları})`, `("/api/v1/marketing/run-due", SYSTEM)`.
- Özellikler: `ozellik:pazarlama.plan-yaz`, `ozellik:pazarlama.butce-gor`, `ozellik:pazarlama.plan-onay` (explicit), `ozellik:pazarlama.butce-ust-onay` (explicit), `ozellik:pazarlama.materyal-editoryal-onay` (explicit). `FEATURE_RULES`: `POST|PUT|PATCH ^/api/v1/marketing/plans(/[^/]+(/lines|/tasks|/suggest|/materials|/submit|/revise))?$` → `plan-yaz`; onay uçları ucun içinde (`budget.decide` gibi).
- M46 sözleşmesi için: `access.RULES`'taki `/api/v1/budget/targets` ve `/api/v1/budget/deviations` satırlarına `page("pazarlama-yeni-kitap")` eklenir (M46 günlüğündeki talimat). Köprü içinden okunacaksa `budget.approved_targets(...)` kullanılır, HTTP gerekmez.
- Zeki AI veri kapsamı (Aşama C): serbest soru kutusu `satis` ve `stok` alanlarını ister; rol tanımında belirtilir.

**Zamanlayıcı**: `scripts/server/timas-marketing.{service,timer}` — her gün 07:30 `POST /api/v1/marketing/run-due`: hatırlatmalar (60/30/14/21 gün kuralları), M46 `deviations?kind=revizyon` okuma, onaylı olmayan planların karnelerini tazeleme (Logo okuması son yıl için; geçmiş yıllar haftada bir). İlk kurulumda elle bir kez koşturulur (kural: zamanlı işi önce elle koştur).

**Kabul testleri** (test sunucusu, gerçek Logo .155 + CRM .28, kısa ömürlü oturum; bittiğinde test verisi silinir)
1. **Liste kapsamı**: `SELECT COUNT(*) FROM Timas_MSCRM.dbo.new_kitapBase WHERE statecode = 0 AND new_Tip = 1 AND new_ilkyayintarihi >= '<bugün>' AND new_ilkyayintarihi < '<bugün+120>'` (+ yayıncılık statüsü süzgeci, uzmanın cevabına göre) = ekrandaki «yayına 120 gün» satır sayısı (tavan yok).
2. **Yazar geçmişi**: seçilen yazar için CRM `SELECT k.new_StokKodu FROM new_eserkatilimBase e JOIN new_katilimcitipiBase t ON t.new_katilimcitipiId = e.new_katilimciTipi JOIN new_kitapBase k ON k.new_kitapId = e.new_Kitap WHERE e.statecode = 0 AND t.new_name = N'Yazar' AND e.new_eserkatilimcisiId = '<kişi>'` → Logo `budget_sources.sales_sql('211', 2025)` bu kodlarla süzülünce net adet ve net ciro toplamı = karnedeki «2025 yazar satışı» (kuruşu kuruşuna).
3. **Emsal satışı**: `SELECT new_kitapidTwo FROM new_new_kitap_new_emsalkitap3Base WHERE new_kitapidOne = '<kitap>'` (ve ters yön) → her emsal için ilk yayın tarihinden 12 aylık pencerede Logo faturalı net adet (yıl sınırında iki firma birleşir) = karnedeki emsal satırları; en az 3 kitapta.
4. **Hedef**: `SELECT hedef_adet, hedef_ciro, hedef_marj FROM semantic_budget_approved_targets WHERE year = 2026 AND stok_kodu = '<kod>'` = plan ekranındaki hedef; M46'da plan revize edilince ertesi `run-due`'da plan «hedefi değişen»e düşer.
5. **CRM ön değerleri**: `SELECT new_toplampazarlamabutcesi, new_basinbutcesi, new_kampanyabutcesi, new_pazarlamaonceligi FROM new_projeBase WHERE new_projeId = '<proje>'` = karnedeki «CRM'deki bütçe» paneli; `new_kitapBase.new_TantmFyMetni` = föy materyalinin kaynak metni (karakter karakter).
6. **Bütçe toplamı**: `SELECT SUM(tutar) FROM semantic_mkt_plan_lines WHERE plan_id = '<id>'` = ekran toplamı = CSV toplamı = PDF toplamı.
7. **Onay**: gönderen onaylayınca 409; `plan-onay` olmayan 403; eşik üstü planda tek onay «onayli»ya geçirmez; her adım `semantic_audit`'te.
8. **Alıntı doğrulama**: stüdyo işi olan bir kitapta materyal taslağındaki her alıntı kitap metninde birebir bulunur; bulunmayan düşer ve sayısı ekranda yazar.
9. **Teknoloji adı**: ekrana ve PDF'e giden metinlerde model/ürün adı taraması 0.

**Bağımlılık**: M46 (main'de) — hazır. M12/M13/M10 isteğe bağlı (yoksa CRM tarihleri ve stüdyo). M16, M17, M18 bu çekirdeğe dayanır: çekirdek şema (bu bölüm) önce main'e girerse M17 ve M19/M53 paralel kodlanabilir; M16 ve M18 M15'ten sonra.

**Tahmini büyüklük**: L (çekirdek + M15 ekranları + onay + PDF; 3–4 gün).
