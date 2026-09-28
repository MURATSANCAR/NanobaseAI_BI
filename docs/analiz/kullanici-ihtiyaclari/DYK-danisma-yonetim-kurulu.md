# DYK — Danışma ve Yönetim Kurulu: kullanıcı ihtiyaç analizi

Durum: kodlandı (dal `dyk`, 2026-09-28; test sunucusunda doğrulanmadı — kabul `scripts/acceptance/DYK`) · Tarih: 2026-09-28 · Kaynaklar: iş tanımı `specs/DYK.txt`, `specs/M45.txt`, `specs/M46.txt`,
`specs/M47.txt`, `specs/M39.txt`, `specs/M50.txt`; Veri Haritası (`veri_haritasi2.txt`: «Stratejik Girdi», «Pazar
Girdileri»); `PROJECT-MEMORY.md` (Kampüs, Yönetim Raporları, Finansal Denetim, M6, Yetki); `docs/GELISTIRME-GUNLUGU.md`;
`src/canvas/stitch/ModulesMenu.tsx` (`LIVE`, `GROUP_HOME`), `src/canvas/modules.json`, `src/canvas/nav/navModel.ts`,
`src/canvas/cfo.ts`; `backend/semantic_bridge/{budget.py,budget_api.py,access.py,access_catalog.json,board.py,reports.py,alerts.py,editorial_export.py}`;
`docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`; `configs/semantic/knowledge/crm/table_descriptions.json`
(`new_sozlesmeBase.new_sozlesmestatusu`, `new_yknotu`); kullanıcı belleği: live-bi-numbers-2026, cockpit-board,
no-demo-login, logo-155-frozen-copy, no-tech-names-on-screens, test-login-as-timasai.

## 1. Modül ne işe yarar

İş tanımına göre DYK, kurulun «kokpiti»dir: (1) **stratejik karar desteği** — bütün modüllerden (M1–M58) özet KPI paneli
(yeşil/sarı/kırmızı), büyük yatırım ve kaynak kararı için senaryo, pazar/rekabet fırsat-tehdit özeti (M39), ZEKİ projesinin
sağlık ve ilerleme raporu (M50) (K3); (2) **kurumsal yönetim desteği** — yıllık strateji/iş planı özeti, risk matrisinin üst
yönetim sürümü (M47), finansal tablolar ve bütçe özeti (M45–M46), İK/organizasyon sağlığı (M55–M58) (K3); (3) **kurul
gündemi ve karar takibi** — gündem hazırlığı, önceki kararların uygulama takibi, karar kaydı, aksiyon maddeleri, kurul
paketi (K4: insan yürütür, ZEKİ yardım eder).

Önemli ayrım: portalda zaten bir **«Yayın kurulu»** ekranı var (`/yayin-kurulu`, M1 — kitap kabul kurulu, CRM'deki 499
yayın kurulu toplantısı). DYK ondan farklıdır: **şirketin danışma ve yönetim kurulu**. Kodda da «board» adı Panolar'a
(`board.py`, `semantic_board_cards`) ait; DYK tabloları ve uçları «kurul» adını kullanmalı.

TİMAŞ'ın bugünkü sorunu: kurul için bilgi bugün her bölümden ayrı ayrı toplanıyor (varsayım). Portalda KPI'lar dağınık:
Genel bakış (ciro), Finansal denetim, Baskı önerisi, Bütçe (M46, main'de), Sözleşmeler (M6), editoryal ekranlar, SEO & GEO.
**Tek sayfalık kurul görünümü, kurul paketi ve karar/aksiyon takibi hiçbir sistemde yok.** Ayrıca 60 modülün çoğu henüz
kodlanmadı (`ModulesMenu.LIVE`'da 20 giriş) → panelin önemli kısmı başlangıçta «kaynak yok» olacak; bunun dürüstçe
gösterilmesi gerekir.

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| Yönetim kurulu başkanı ve üyeleri | Yönetim kurulu — **varsayım** (üye listesi yok; AD hesabı olup olmadıkları bilinmiyor) | Toplantı öncesi (aylık/çeyreklik), arada haftalık bakış | **Telefon / tablet** |
| Danışma kurulu üyeleri | Danışma kurulu — **varsayım**; büyük olasılıkla şirket dışı kişiler | Toplantı öncesi | Tablet / PDF |
| Genel müdür (paketi sunan, aksiyonların sahibi) | Üst yönetim — **varsayım** | Haftalık | İkisi de |
| Kurul sekreteri / yönetim asistanı (paketi hazırlayan, tutanak yazan) | Genel müdürlük — **varsayım**; M46 masraf merkezlerinde «B01-GMD-01 Genel Müdürlük» var (`budget_sources.py` notu) | Toplantı öncesi yoğun, sonrası tutanak | Masaüstü |
| Bölüm yöneticileri (KPI ve aksiyon sahipleri: finans, satış, editörya, pazarlama, İK, BT) | İlgili birimler — birimler **kanıtlı** (CRM görev birimleri/departmanları), kişiler varsayım | Aylık KPI yorumu; aksiyon güncellemesi | İkisi de |
| CFO (finans bölümünün sahibi) | Finans — **varsayım** | Toplantı öncesi | Masaüstü |

## 3. Bugün bu iş nasıl yapılıyor

Doğrudan gözlem yok; **varsayım**, kanıtlı noktalar belirtildi.

- **Kurul sekreteri:** Toplantıdan 1-2 hafta önce bölümlerden sunum/rakam ister (e-posta), gelen dosyaları tek sunumda
  birleştirir, PDF'i üyelere e-postayla gönderir. Tıkanma: rakamların farklı kaynaklardan ve farklı tarihlerden gelmesi
  (ör. ciro Logo'dan, hedef Excel'den), son dakika değişiklikleri, sürüm karışıklığı.
- **Kararlar:** Tutanak Word'de; aksiyon maddeleri bir sonraki toplantıda sözlü sorulur. Karar takibinin sistemde olmadığı
  varsayımı: CRM'de yönetim kurulu toplantısı varlığı görülmedi (yalnız yayın kurulu toplantıları var — **kanıt**).
- **Kurul onayı gereken işler (kanıt, yorum gerekli):** CRM sözleşme akışında «4- YK- Onayında» adımı ve `new_yknotu`
  («YK Notu») alanı var. «YK» yönetim kurulu ise kurul bazı yazar sözleşmelerini tek tek onaylıyor demektir; yayın kurulu
  ise DYK'yı ilgilendirmez (uzmana soru).
- **Genel müdür:** Genel bakış ekranını ve bölüm raporlarını kendisi derliyor (varsayım).
- **Dış üyeler:** Portal girişi yalnız AD (**kanıt**: `no-demo-login` — demo/davet/misafir girişi hiçbir gerekçeyle geri
  gelmez). AD hesabı olmayan kurul üyesi portala giremez → paket e-posta/PDF ile gitmek zorunda.

## 4. İhtiyaçlar ve acı noktaları

**Kurul üyesi**
1. Tek sayfada şirketin durumu: 10-15 gösterge, renkli, önceki dönem ve hedefe göre, telefonda okunur.
2. «Neden kırmızı?» sorusuna tek cümle ve sahibi.
3. Önceki kararların ne durumda olduğu (tamamlandı / gecikti / sorun).
4. Paketin toplantıdan en az birkaç gün önce, sabit bir sürümle gelmesi.

**Kurul sekreteri**
1. Paketi bölümlerden toplamak yerine sistemden **derlemek**; sürümü dondurmak.
2. Gündem şablonu, karar tutanağı şablonu, aksiyon listesi.
3. Aksiyon sahiplerine hatırlatma; toplantı öncesi durum toplama.

**Genel müdür**
1. Paketi göndermeden önce gözden geçirip her bölüme kısa yorum eklemek.
2. Kurulun kararlarını sahiplerine aksiyon olarak dağıtmak ve izlemek.

**Bölüm yöneticisi**
1. Kendi göstergesinin yorumunu yazmak (neden sarı, ne yapıyoruz) — tek yerde, tek biçimde.
2. Kendisine düşen kurul aksiyonunu görmek ve durumunu güncellemek.

## 5. Nasıl kullanmak isteyecekler

### Kullanıcı hikâyeleri

- Kurul üyesi olarak toplantıdan önce telefonda tek sayfalık göstergeleri renkleriyle görmek istiyorum, çünkü toplantıya
  hazırlıklı gelmek istiyorum ama 60 sayfa okuyamam.
- Kurul üyesi olarak kırmızı bir göstergeye dokununca sahibinin yorumunu ve eğilimini görmek istiyorum, çünkü soru sormadan
  önce bağlamı bilmeliyim.
- Kurul üyesi olarak önceki toplantıların kararlarının durumunu tek listede görmek istiyorum, çünkü aynı konuyu her
  toplantıda yeniden açmak istemiyorum.
- Kurul sekreteri olarak «Ekim toplantısı paketi»ni bir tuşla derlemek ve sürümünü dondurmak istiyorum, çünkü rakamlar
  toplantıya kadar değişmemeli.
- Kurul sekreteri olarak karar ve aksiyonları toplantı sırasında ya da hemen sonra kaydetmek istiyorum, çünkü tutanak ve
  takip aynı kayıttan çıkmalı.
- Genel müdür olarak paketteki Zeki AI yönetici özetini düzeltip onaylamak istiyorum, çünkü kurula benim adımla gidiyor.
- Bölüm yöneticisi olarak kendi göstergeme yorum yazmak istiyorum, çünkü kırmızıyı açıklamadan pakete girmesini istemiyorum.
- Bölüm yöneticisi olarak bana atanmış kurul aksiyonunu telefondan güncellemek istiyorum.

### Ana ekranlar ve akış

Öneri: yeni çalışma alanı gerektirmeden **Kampüs'te «Kurul» kartı** + Finans alanında «Kurul» sayfası (`/kurul`); menüde
yalnız yetkisi olana görünür.

1. **Panel** (ilk açılış): bölüm kartları (Finans · Satış ve bayi · Yayın ve editörya · Stok ve üretim · Pazarlama ·
   Risk ve uyum · İK · ZEKİ projesi). Her kartta 1-3 gösterge, renk, önceki döneme ok, «kaynak yok» gri durumu, veri son
   günü. Üstte «kritik uyarılar» şeridi (kırmızı + etki yüksek).
2. **Gösterge ayrıntısı**: 12 dönem seyri, hedef, eşik, sahibin yorumu, kaynak ekrana bağlantı (yetkisi varsa).
3. **Toplantılar**: takvim; toplantı sayfası = gündem (sürükle-sırala), eklenen paket, katılımcılar, kararlar, aksiyonlar.
4. **Paket**: derle → gözden geçir (bölüm yorumları, Zeki AI yönetici özeti) → dondur (sürüm, tarih) → PDF → dağıt.
5. **Kararlar ve aksiyonlar**: bütün kararlar (toplantı, konu, karar metni), aksiyon (sahip, termin, durum, son not);
   süzgeç «gecikenler».
6. **Senaryolar** (sonraki sürüm): M46 senaryoları ve M45 senaryo sonuçlarının kurul özeti.

En sık üç işlem:
- «Durumu görmek» (üye, telefon): Kampüs → Kurul kartı = **1 dokunuş**; kırmızı göstergenin yorumu **2**.
- «Paketi derleyip dondurmak» (sekreter): Toplantı → «Paketi derle» → gözden geçir → «Dondur» = **4 dokunuş** + yorum
  bekleyen bölüm varsa uyarı.
- «Aksiyonu güncellemek» (bölüm yöneticisi): bildirim bağlantısı → durum + not = **2 dokunuş**.

Telefon/tablet: Panel ve Kararlar ekranları dikey tek sütun; PDF paketi A4 dikey, telefonda okunur puntoda.

### Zeki AI'a soracakları örnek sorular

- «Bu çeyrekte bütçenin gerisinde kalan bölümler hangileri ve neden?»
- «Geçen toplantıdan bu yana gecikmiş kurul aksiyonları?»
- «Net ciro geçen yılın aynı dönemine göre ne kadar arttı, iade ve iskonto hesaba katıldığında?»
- «En büyük 3 riskimiz ne, bu çeyrekte ne değişti?»
- «Yeni kitap programında plana göre kaç kitap gecikti?»
- «ZEKİ projesinde bu ay hangi modüller devreye alındı?»

### Otomasyon katmanı

| Adım | Katman | Not |
|---|---|---|
| Göstergelerin toplanması, renk, eğilim | K1 | Modüllerden kendiliğinden; hedef/eşik gösterge sahibinden. |
| Paket derleme (gösterge anlık görüntüsü + bölüm yorumları + ekler) | K1 | Sekreter başlatır; dondurma insanın. |
| Yönetici özeti, bölüm yorumu taslağı | K2 | Zeki AI taslak; genel müdür / bölüm yöneticisi onaylar. |
| Senaryo özetleri | K3 | Sayılar M45/M46'dan; karar kurulun. |
| Gündem, tutanak, karar kaydı | K4 | İnsan yazar; Zeki AI şablon ve tutanak taslağı (not girişinden) önerir. |
| Aksiyon hatırlatma | K1 | Termin yaklaşınca sahibine. |

### Bildirim / uyarı

- Bölüm yöneticisi: paket derlenmeden 5 iş günü önce «göstergenize yorum bekleniyor»; kırmızıya dönen göstergesi için.
- Kurul üyeleri: paket dondurulunca (AD'li üyeye bağlantı, AD'siz üyeye PDF eki — gizlilik kararı uzmana soru).
- Aksiyon sahibi: termine 7 gün kala ve geçince; toplantıdan 3 gün önce «durum güncelle».
- Genel müdür: kritik uyarı şeridine yeni madde düşünce.
- Kanal: e-posta + portal içi; telefon bildirimi yok.

### Onay ve yetki

| Kim | Görür | Değiştirir | Onaylar |
|---|---|---|---|
| Kurul üyesi (AD'li) | Panel, dondurulmuş paketler, kararlar, aksiyonlar | — | — |
| Kurul sekreteri | Hepsi | Toplantı, gündem, karar, aksiyon, paket taslağı | — |
| Genel müdür | Hepsi | Yönetici özeti | Paketi dondurma/dağıtma |
| Bölüm yöneticisi | Panel + kendi bölümü | Kendi gösterge yorumu, kendi aksiyonu | — |
| Yönetici (portal) | Gösterge kataloğu | Gösterge tanımı, eşik, sahip | — |

Kural: kurul panelindeki özet rakamı görmek, kaynak modülün sayfasını açma yetkisi vermez (kaynak bağlantısı yalnız o
sayfanın yetkisi olana çalışır).

## 6. Veri

| Gereken veri | Kaynak (Logo / CRM / T-soft / kullanıcı girer / dış) | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Net ciro, iade, satılan adet, yıl karşılaştırması | Logo (katalog `net_ciro`, `iade_orani`; `src/canvas/cfo.ts`) | 2026 (17.08'e kadar) 848,1 Mn ₺, +%42,7; iade %8,1 | Donmuş kopya → «veri son günü» her kartta |
| Bütçe/hedef gerçekleşme, departman kullanımı, yeni kitap programı | M46 (main'de): `B.tracking`, `B.deviations`, `B.approved_targets`, tablo `semantic_budget_alerts` | Kod var; onaylı plan olup olmadığı ölçülecek | Onaylı plan yoksa «plan onaylanmadı» |
| Brüt marj (maliyetli satır) | Logo `STLINE` | %20 satır maliyetsiz, maliyet 30.06'ya kadar | Kartta kapsam notu |
| Finansal denetim durumu | `financial_audit_snapshot` hazır raporu | Var | — |
| Gelir tablosu, nakit | M45 | Kodlanmadı | Gri |
| Risk matrisi, kritik riskler | M47 | Kodlanmadı | Gri |
| Bayi segmenti, vadesi geçmiş alacak | M59 (kodlanmadı); geçici olarak bilgi paketi FIFO sorgusu | Sorgu var | Yaklaşık etiketi |
| Sözleşme: biten, portala alınan, hakediş | M6 `editorial_mod.summary` (60 gün sayacı), `semantic_contract_*` | Var | — |
| Yayın kurulu kararları (kitap kabul) | CRM yayın kurulu toplantıları (499), `/api/v1/editorial/board/summary` | Var | — |
| Editör iş yükü, çeviri, son okuma, stüdyo | M2, M4, M5, M13/14 tabloları | Kodlar var (bazıları test sunucusunda) | KPI tanımı gerekir |
| Stok riski | Baskı önerisi önbelleği | Var | — |
| SEO/GEO görünürlük | `seo_geo` | Test sunucusunda | Müşteri VM'inde durumu ölçülecek |
| Pazar/rekabet (M39) | Dış | Yok; müşteride web kapalı | Gri / elle yüklenen not |
| İK (M55–58) | Dış/İK sistemi | Yok | Gri |
| ZEKİ proje sağlığı (M50 yerine) | Portalın kendisi: `ModulesMenu.LIVE` (canlı modül sayısı), `semantic_audit` (yazma etkinliği), oturum kayıtları (giriş servisi), kalite kapısı sonuçları | Parçalar var | Kullanım ve kalite göstergeleri tanımlanmalı; ölçülecek |
| Kurul üyeleri, toplantılar, gündem, kararlar, aksiyonlar | Kullanıcı girer | Hiçbir sistemde yok (CRM'de yalnız yayın kurulu) | Tamamen yeni veri |
| Strateji ve iş planı metni | Kullanıcı yükler | Yok | Belge |

## 7. Diğer modüllerle bağ

- **Girdi alır:** M45 (finansal özet, gelir tablosu, nakit), M46 (bütçe, hedef, sapma, senaryo), M47 (risk matrisi yönetim
  sürümü, uyum), M59 (bayi riski), M6/M54 (telif yükümlülüğü, kritik yenilemeler), M1 yayın kurulu, M2/M4/M5 (editoryal
  üretim), Baskı önerisi (stok), SEO & GEO, M39 (pazar), M50 (ZEKİ sağlığı), M55–M58 (İK) — bunların her biri **gösterge
  sağlayıcı** olarak bağlanır; olmayan gri görünür.
- **Çıktı verir:** Kurul kararları → aksiyonlar (sahip modül/kişi), M46 (kurulun onayladığı bütçe revizyonu notu), M47
  (kurulun kabul ettiği risk iştahı/eşik), Kampüs (Kurul kartı).

## 8. Kısıtlar

- **Giriş yalnız AD**; AD'siz kurul üyesi için davet/misafir hesabı açılmaz → PDF paketi e-postayla (`no-demo-login`).
- Portal Logo'ya ve CRM'e yazmaz; kurul kayıtları köprü tablolarında.
- Paket dondurulduktan sonra değişmez; düzeltme yeni sürümdür (denetim izi).
- Gizlilik: kurul paketi şirketin en hassas belgesidir → sayfa ve dışa aktarma ayrı, açıkça verilen yetkiyle; dağıtım
  kaydı (kime, ne zaman) tutulur; e-posta ekinde parola/şifreleme kararı uzmana sorulur.
- «Kaynak yok» göstergesi kırmızı değil gridir; demo/örnek rakam asla konmaz.
- Veri tazeliği: her göstergede veri son günü; Logo donmuş kopyası paketin kapağında yazar.
- Ekranda ve PDF'te teknoloji adı yok («Zeki AI»); satır tavanı yok.

## 9. Kapsam önerisi

**İlk sürüm**
- Gösterge kataloğu (tanım, sağlayıcı, eşik, sahip, dönem) + bugün canlı modüllerden 12-15 gösterge.
- Kurul paneli (telefon öncelikli), gösterge ayrıntısı, bölüm yorumu.
- Toplantı, gündem, karar, aksiyon kaydı; aksiyon hatırlatma.
- Paket: derle → dondur → PDF → dağıtım kaydı.

**Sonraki sürüm**
- Zeki AI yönetici özeti ve tutanak taslağı.
- M45, M47, M59 gösterge sağlayıcıları (modüller geldikçe).
- Senaryo özetleri (M45/M46), strateji/iş planı belgesi ve hedef ağacı.
- ZEKİ proje sağlığı göstergeleri (kullanım, kalite kapısı).

**Yeniden kullanılacaklar**
- M46: `budget.tracking`, `budget.deviations`, `budget.approved_targets` (köprü içi çağrı).
- `src/canvas/cfo.ts` sorguları (net ciro, iade, yıl karşılaştırması) — sunucu tarafına taşınmalı (anlık görüntü için).
- `financial_audit_snapshot.py` (hazır rapor), `management/` önbelleği (Baskı önerisi), `editorial.summary` /
  `board_summary` (M6, M1).
- `editorial_export.py` (sunucuda PDF), `contracts_docs.py` (Word), `alerts.smtp_settings`, `admin.audit`, `reports.py`
  (e-posta gönderim deseni), `board.py` (kart/grafik bileşenleri ön yüzde `src/canvas/board/Chart.tsx`).

## 10. Uzmanlara sorulacak sorular

1. Kurul üyeleri kimler, kaçının şirket AD hesabı var; danışma kurulu şirket dışından mı?
2. Kurul hangi sıklıkla toplanıyor; paket kaç gün önce gidiyor, bugünkü paketin bölümleri neler?
3. Sözleşme akışındaki «YK onayı» yönetim kurulu mu? Evetse kurul hangi sözleşmeleri onaylıyor (tutar/tür eşiği)?
4. Kurul paketinin dağıtımında gizlilik kuralı nedir (e-posta eki serbest mi, parola şart mı, yalnız okuma mı)?
5. Kurulun görmek istediği ilk 10 gösterge ve her birinin sahibi kim; hedef/eşikleri kim belirler?

## 11. Başarı ölçütü

- Paket hazırlık süresi: bugünkü (ölçülecek, iş günü) → 1 iş günü; bölümlerden e-postayla dosya toplama 0.
- Paketteki göstergelerin kaynağa izlenebilirliği %100 (her rakamın kaynak modülü ve veri son günü yazılı).
- Kurul aksiyonlarında zamanında kapanma oranı çeyrekten çeyreğe artar; «durumu bilinmeyen» aksiyon 0.
- Kurul üyelerinin toplantı öncesi paneli açma oranı (AD'li üyelerde).
- Gri («kaynak yok») göstergelerin sayısı modüller geldikçe azalır — ZEKİ ilerlemesinin kendisi bir göstergedir.

## 12. Uzman gözüyle en iyi sistem

Kendimi 15 yıldır yönetim kurullarında sekreterlik yapmış bir kurumsal yönetim uzmanının ve bir bağımsız kurul üyesinin
yerine koyuyorum.

**İyi şirketler ve iyi yazılımlar bu işi nasıl yapıyor.** İyi yönetilen şirketlerde kurul paketi sabit bir iskelete
oturur: (1) genel müdürün 1 sayfalık özeti, (2) gösterge tablosu (kurulun seçtiği 10-15 gösterge, hedef ve eşikle), (3)
karar gerektiren konular (her biri 1-2 sayfa: seçenekler, öneri, etkisi), (4) bilgi konuları, (5) önceki kararların
takibi, (6) ekler. Kurul yazılımlarının güçlü yanları: tek sürüm, güvenli dağıtım, tablette okuma ve not alma, karar ve
aksiyon kaydı, erişim izi. Zayıf yanları: rakamlar içeriye yine elle PDF olarak girer — iş sistemleriyle bağ yoktur.
Yayıncılıkta kurulun özellikle baktığı göstergeler: net satış ve büyüme, iade oranı, brüt marj, yeni başlık programı,
backlist payı, stok devir hızı ve eskiyen stok, telif yükümlülüğü ve avans riski, alacak ve büyük müşteri yoğunlaşması,
nakit.

**TİMAŞ için mükemmel sistem:** Gösterge tablosu elle değil modüllerden gelir; her göstergenin sahibi yorumunu sistemde
yazar; paket bir tuşla derlenir ve dondurulur; AD'li üyeler telefonda okur, AD'siz üyelere aynı sürümün PDF'i gider;
toplantıda kararlar ve aksiyonlar aynı ekrana yazılır, ertesi gün sahiplerine düşer; bir sonraki paketin «önceki kararlar»
bölümü kendiliğinden dolar. Kurulun göremediği alan (henüz kodlanmamış modül) açıkça gri durur — kurul ZEKİ'nin ilerlemesini
de buradan izler.

**Bir iş günü (kurul sekreteri, toplantıdan 7 gün önce):**
- 09:00 — Toplantı sayfası: gündem taslağı önceki toplantıdan kopyalanmış; «önceki kararlar» listesinde 3 aksiyon gecikmiş.
- 09:30 — «Paketi derle»: 14 göstergeden 11'i hazır, 3'ü gri (İK, pazar, nakit — modül yok); 2 bölüm yöneticisinin yorumu
  eksik → sistem hatırlatma gönderiyor.
- 11:00 — Satış direktörünün yorumu geliyor («bayi alacağında 90+ artışı iki büyük caride; ödeme planı yapıldı»).
- 14:00 — Genel müdür Zeki AI'ın yönetici özetini açıyor, iki cümleyi değiştiriyor, onaylıyor.
- 15:00 — «Dondur»: paket v1, PDF; AD'li üyelere bağlantı, iki dış üyeye PDF; dağıtım kaydı.
- Toplantı günü: kararlar ekrandan yazılıyor; ertesi sabah 6 aksiyon sahiplerine düşüyor.

**«Bunu görürsem hemen kullanırım»**
1. Bir tuşla derlenen ve dondurulan paket — bölümlerden dosya toplamaya son.
2. Telefonda tek sayfa gösterge tablosu, her kırmızının yanında sahibinin yorumu.
3. Önceki kararların durumunun kendiliğinden gelmesi.

**«Bunu yaparsanız kullanmam»**
1. Paket gönderildikten sonra rakamların arkadan değişmesi — kurul üyesi iki farklı sayı görürse güven biter.
2. Gri olması gereken göstergeyi boş ya da sıfır göstermek, ya da örnek rakamla doldurmak.
3. Kurul paketinin herkesin görebildiği bir sayfada durması ya da kimin indirdiğinin bilinmemesi.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (tablo / görünüm / ölçü) | CRM (varlık / alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Satış göstergeleri | `LG_411_01_INVOICE` (katalog `net_ciro` fatura seviyesi, `iade_orani`), 2025 için `LG_211_01_INVOICE`; eş dönem kırpma veri son gününe göre | — | Yok | Manşet KPI; fatura seviyesi anlamı (güven sıralaması `net-ciro-line-formula-wrong` belleğine uygun). |
| Brüt marj | `STLINE` (faturalı, `OUTCOST ≠ 0`), ölçü `brut_kar_marji` | — | Yok | Kapsam notuyla. |
| Bütçe/hedef | M46 tabloları (`semantic_budget_*`) | — | Yok | Köprü içi çağrı. |
| Alacak | `CLFLINE` + `PAYTRANS` (FIFO, yaklaşık) ya da M59 özeti | — | Yok | — |
| Sözleşme ve telif | — (M6 hakediş: köprü tabloları) | `new_sozlesmeBase` (bitiş, statü; «YK Onayında» = statü 4, `new_yknotu`) | Yok | Kurul onayı bekleyen sözleşme sayısı göstergesi (YK = yönetim kurulu ise). |
| Yayın kurulu | — | Yayın kurulu toplantıları (`/api/v1/editorial/board/summary`) | Yok | — |
| Stok riski | Baskı önerisi önbelleği | CRM stok | Yok | — |
| Göstergenin rengi ve eğilimi | — | — | Yok (eşik kuralı) | Deterministik olmalı. |
| Bölüm yorumu taslağı | Göstergenin 12 dönem değeri | — | Bölüm yöneticisine 2-3 cümle taslak; sayılar girdiden | Yorum yükü; yönetici onaylar. |
| Yönetici özeti | Bütün göstergeler + onaylı yorumlar (JSON) | — | 1 sayfa özet taslağı; her sayı girdide olmalı (sonradan düzenli ifadeyle denetim, tutmazsa taslak reddedilir) | Genel müdür onaylar. |
| Tutanak taslağı | — | — | Sekreterin serbest notlarından karar/aksiyon listesi önerisi (yapılandırılmış: karar metni, sahip adayı, termin adayı) | Sekreter onaylar; kişi eşleştirme rehberden (`people.py`). |
| Gündem önerisi | — | — | Gecikmiş aksiyon + kırmızı göstergelerden gündem maddesi önerisi | K4 yardım. |
| Serbest soru | Katalog | CRM | Mevcut `/api/v1/ask` (kurul üyesinin veri kapsamı Aşama C'ye bağlı) | Yeni motor yok. |

Model çağrıları `rt.llm_for("kurul")`, arka planda `BATCH`. Kapalı seçim gerekirse (gündem maddesi kategorisi) tek token +
olasılık. Ekranda ve PDF'te yalnız «Zeki AI».

## 14. Kodlama planı (kodlayıcıya devir)

**Köprü dosyaları**
- `backend/semantic_bridge/kurul.py` — gösterge kataloğu, anlık görüntü, toplantı, gündem, karar, aksiyon, paket.
- `backend/semantic_bridge/kurul_sources.py` — **gösterge sağlayıcıları**: her sağlayıcı `(kod, fn(engine, tenant) ->
  {deger, hedef, onceki, veri_son_gunu, kaynak, ayrinti})`. Köprü içi çağrı (HTTP değil): M46 `budget.tracking` /
  `deviations`, `financial_audit_snapshot` hazır raporu, `management` önbelleği (Baskı önerisi), `editorial.summary` /
  `board_summary`; Logo satış göstergeleri doğrudan SQL (`budget_sources.runner` deseni). Sağlayıcı yoksa `kaynak_yok`.
  Böylece kurul üyesinin M46/M6 sayfa yetkisi olması gerekmez; kurul yalnız özeti görür.
- `backend/semantic_bridge/kurul_api.py` — `register(app, rt, require_caller, can)`.
- PDF: `editorial_export.py`'deki sunucu PDF yolu (fpdf2) → `kurul_pdf.py`.

**Tablolar** (adlar «kurul»; «board» Panolar'ındır)
- `semantic_kurul_indicators` (kod PK, tenant_id, bolum, ad, aciklama, saglayici, birim, yon, esik_sari, esik_kirmizi,
  hedef_kaynagi, sahip, sira, aktif, surum)
- `semantic_kurul_values` (kod, donem (YYYY-MM ya da YYYY-Qn), olcum_at, deger, hedef, onceki, renk, durum ok|kaynak_yok|hata,
  veri_son_gunu, ayrinti_json)
- `semantic_kurul_comments` (kod, donem, metin, durum taslak|onayli, yazan, onaylayan, llm_job_id)
- `semantic_kurul_meetings` (id, tenant_id, tur yonetim|danisma, tarih, yer, durum planlandi|yapildi|iptal, katilimcilar_json, not)
- `semantic_kurul_agenda` (meeting_id, sira, baslik, tur karar|bilgi, sunan, sure_dk, ek_ref)
- `semantic_kurul_decisions` (id, meeting_id, gundem_sira, metin, oy_ozeti, yazan, tarih)
- `semantic_kurul_actions` (id, decision_id, eylem, sahip, termin, durum acik|tamamlandi|gecikti|iptal, son_not, guncelleyen, tarih)
- `semantic_kurul_packages` (id, meeting_id, surum, durum taslak|donduruldu|dagitildi, icerik_json (anlık görüntü),
  ozet_metin, pdf_yol, pdf_sha256, donduran, dondurma_at)
- `semantic_kurul_distribution` (package_id, alici, kanal baglanti|pdf, gonderen, gonderim_at, sonuc)
- `semantic_kurul_members` (id, ad, eposta, ad_hesabi (varsa), kurul yonetim|danisma, aktif)
- Dosyalar: `KURUL_DIR` (`/data/nanobaseai/bi/var/kurul`, kalıcı `bi_var` volümü; 0700/0600 — finansal denetim deseni).

**Uçlar** (`/api/v1/kurul/*`)
- `GET panel?donem` · `GET indicators` · `GET indicators/{kod}?donem` · `POST indicators` / `PATCH indicators/{kod}` (yönetici)
- `POST indicators/{kod}/comments` · `POST comments/{id}/draft` (model, 202) · `POST comments/{id}/approve`
- `GET/POST/PATCH meetings` · `GET meetings/{id}` · `PUT meetings/{id}/agenda` · `POST meetings/{id}/decisions` ·
  `PATCH decisions/{id}` · `GET/POST/PATCH actions` (sahip kendi aksiyonunu günceller) · `POST meetings/{id}/minutes/draft` (model)
- `POST meetings/{id}/packages` (derle) · `GET packages/{id}` · `POST packages/{id}/summary/draft` (model) ·
  `POST packages/{id}/freeze` · `GET packages/{id}/document.pdf` · `POST packages/{id}/distribute`
- `POST run-due` (SYSTEM) · `GET status`

**Ekranlar** `src/canvas/kurul/`: `KurulScreen.tsx` (sekmeler Panel · Toplantılar · Kararlar ve aksiyonlar · Paketler),
`IndicatorTile.tsx` (renk + ok + «kaynak yok» gri + veri son günü; renk yalnız renkle değil simgeyle de), `IndicatorSheet.tsx`,
`MeetingPage.tsx`, `PackageBuilder.tsx`, `api.ts`. Rotalar `/timas/kurul`, `/timas/kurul/toplanti/:id`. Menü: `navModel.ts`
«Finans» alanına «Kurul» (yalnız `sayfa:kurul` olana görünür — `visibleNav` zaten süzer). Kampüs: `ModulesMenu.tsx`
`LIVE.DYK = '/kurul'`, `GROUP_HOME['DYK — Danışma & Yönetim Kurulu'] = { to: '/kurul', hint: 'Kurul göstergeleri, paket ve kararlar' }`.

**Yetki**
- `sayfa:kurul` → `/api/v1/kurul/`; `run-due` SYSTEM. «Herkes» rolüne **verilmez** (kurulumda yalnız yönetici; roller
  prod öncesi atanır).
- `ozellik:kurul.hazirla` (**açıkça**; toplantı, gündem, karar, paket taslağı — sekreter), `ozellik:kurul.dondur`
  (**açıkça**; dondurma ve dağıtım — genel müdür), `ozellik:kurul.gosterge` (**açıkça**; katalog ve eşik),
  `ozellik:kurul.yorum` (kendi bölümünün göstergesine yorum), `ozellik:kurul.aksiyon` (kendi aksiyonu; sahiplik uçta),
  PDF indirme `ozellik:veri.disa-aktar` + `sayfa:kurul`.

**Zamanlayıcı** `scripts/server/timas-kurul.{timer,service}`: günde bir 06:30 `POST /api/v1/kurul/run-due` → bütün
göstergelerin güncel dönem değerini sağlayıcılardan alır (hazır raporları okur, ağır sorgu yok), renk değişimini
kaydeder, aksiyon termin hatırlatmaları, toplantıdan 5 iş günü önce yorum hatırlatması. İlk koşu elle.

**Kabul testleri** (gerçek DB; test sunucusu)
1. Net ciro göstergesi: `SELECT SUM(CASE WHEN TRCODE IN (7,8,9) THEN NETTOTAL ELSE -NETTOTAL END) FROM LG_411_01_INVOICE
   WHERE CANCELLED = 0 AND TRCODE IN (2,3,7,8,9) AND DATE_ >= '2026-01-01' AND DATE_ < '2027-01-01'` → 848.110.178,82 ₺;
   geçen yıl eş dönemi `LG_211_01_INVOICE`, `DATE_ >= '2025-01-01' AND DATE_ <= '2025-08-17'` → 594,3 Mn ₺; artış +%42,7.
2. İade oranı: `SUM(TRCODE 2,3) / SUM(TRCODE 7,8,9)` aynı süzgeçle → %8,1.
3. Bütçe göstergesi: `budget.tracking(engine, tenant, 2026)` sonucundaki şirket toplamı oranı = panel değeri; onaylı plan
   yoksa durum `kaynak_yok` (değer 0 değil).
4. Sözleşme göstergesi: `/api/v1/editorial/contracts/summary` `expiring` = panel «60 günde biten sözleşme».
5. Dondurma değişmezliği: paket donduktan sonra kaynak değer değişse de (`semantic_kurul_values` yeni satır) `GET
   packages/{id}` içeriği ve `pdf_sha256` aynı kalır; yeni derleme yeni sürüm açar (DB'siz birim testi + gerçek koşu).
6. Gri kural: sağlayıcısı olmayan gösterge `durum = kaynak_yok`, renk yok; panelde sayı yazmaz (ön yüz testi).
7. Yetki: `sayfa:kurul` olmayan oturum `GET /api/v1/kurul/panel` → 403; `kurul.dondur` olmayan `POST …/freeze` → 403;
   aksiyon sahibi olmayan kişi başkasının aksiyonunu güncelleyemez → 403 (test kullanıcısı `timasai` kısa oturumu, test
   sonunda kayıtlar silinir).
8. Model metni: yönetici özeti taslağındaki her sayı `icerik_json` içinde var; olmayan sayı içeren taslak kaydedilmez.

**Bağımlılık:** M46 main'de → bütçe göstergeleri hemen. M45, M47, M59 gelmeden de başlanır (gri); onlar geldikçe
`kurul_sources.py`'ye sağlayıcı eklenir (her biri S). Paralel kodlanabilir; tek ön koşul sağlayıcı arayüzünün sabitlenmesi.

**Tahmini büyüklük:** L (gösterge kataloğu + panel M; toplantı/karar/aksiyon M; paket + PDF + dağıtım M; model taslakları S).
