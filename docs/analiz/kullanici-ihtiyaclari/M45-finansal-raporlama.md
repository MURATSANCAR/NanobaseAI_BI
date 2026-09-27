# M45 — Finansal Raporlama ve Analiz: kullanıcı ihtiyaç analizi

Durum: analiz (kod yok; modülün bir kısmı başka ekranlarda var) · Tarih: 2026-09-28 · Kaynaklar: iş tanımı `specs/M45.txt`,
`specs/M46.txt`, `specs/DYK.txt`; Veri Haritası (`veri_haritasi2.txt`: «Finansal Girdiler», «Analitik Girdiler»);
`PROJECT-MEMORY.md` (Finansal Denetim, Yönetim Raporları, Vade/yaşlandırma, M6); `docs/analiz/finansal-denetim-2026-09-21.md`;
`docs/analiz/yetki-mekanizmasi-2026-09-27.md`; `configs/semantic/knowledge/logo/knowledge/{caveats,metrics,glossary}/logo-timas.md`;
`src/canvas/cfo.ts`, `src/canvas/stitch/screens.ts`, `src/canvas/nav/navModel.ts`, `backend/semantic_bridge/access_catalog.json`,
`backend/semantic_bridge/management/`; M46 Bütçe kodu (main'de: `backend/semantic_bridge/budget.py`, `budget_api.py`, `budget_sources.py`, `src/canvas/budget/`);
kullanıcı belleği: live-bi-numbers-2026, net-ciro-line-formula-wrong, sales-are-invoiced-lines, freelancer-payments-logo,
system-of-record-logo, cockpit-board, timas-alerts, logo-155-frozen-copy, no-tech-names-on-screens.

## 1. Modül ne işe yarar

İş tanımına göre M45 iki şey yapar: (1) Logo muhasebe verisinden **kendiliğinden** finansal rapor üretir — günlük gelir/gider
özeti, aylık gelir tablosu (P&L), bütçe–gerçekleşme karşılaştırması, vergi dönemi hatırlatması (K1); (2) finans yöneticisinin
kararına **analiz** hazırlar — kitap/seri kârlılığı (kitap başına katkı payı), 3-6-12 aylık ve 13 haftalık kayan nakit akışı
tahmini, baskı ve kampanya yatırımının geri dönüşü, iyimser/baz/kötümser senaryo (K3). Çıktıları yönetim sunumuna ve DYK kurul
paketine finansal özet olarak gider.

TİMAŞ'ın bugünkü sorunu (kanıta dayalı): portalda satış tarafı var, **gelir tablosu, gider, nakit ve kârlılık tarafı yok.**

| Portalda bugün olan | Nerede | M45 için ne kadarını karşılıyor |
|---|---|---|
| Genel bakış: 2026 net ciro, aylık seyir, toptan/perakende dağılımı, en büyük cari, en çok satan ve en çok iade alan kitap, Zeki AI'a soru | `/genel-bakis`, `src/canvas/cfo.ts` | Yalnız satış ve iade. Gider, maliyet, nakit yok. |
| Finansal denetim: mizan ve fiş eşitliği, 41 oran (17 hesaplandı, 24 önkoşul eksik), aylık KDV bakiyeleri, sabit kıymet cetveli, Logo hesap/fiş ayrıntısı | `/finansal-denetim`, `financial_audit*.py` | Kayıt **doğruluğu**. Rapor değil; oranlar gelir tablosunun kapanmamasından dolayı büyük ölçüde engelli. |
| Yönetim raporları: yalnız Baskı önerisi (+ tahmin sekmesi) | `/yonetim-raporlari`, `management/` | Stok/baskı kararı; finansal tablo yok. |
| Panolar, Planlı raporlar (Excel e-postası), Uyarılar (kural = soru) | Analiz alanı | Kişinin kendi sorusu için genel altyapı; hazır finansal rapor değil. |

**Eksik olan (M45'in asıl işi):** aylık gelir tablosu, gider kırılımı, bütçe–gerçekleşme (M46 hedeflerini okuyarak), kitap/seri/
yayınevi/kanal katkı payı (telif ve maliyet düşülmüş), nakit pozisyonu ve 13 haftalık nakit akışı, senaryo, vergi takvimi,
yönetime giden finansal özet metni.

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| Mali işler yöneticisi / CFO (iş tanımındaki «CFO Karar») | Finans / muhasebe yönetimi — unvan **varsayım** (iş tanımı «CFO» der; AD'de unvan alanı boş, `crm-systemuser-directory` belleği) | Her gün kısa bakış, ay kapanışında yoğun | Masaüstü (analiz), telefon (sabah özeti) |
| Muhasebe müdürü / muhasebe uzmanı | Muhasebe — **kanıt**: CRM `new_gorevbirimi` 3 = Muhasebe, CRM BT taleplerinde «Muhasebe» departmanı (`docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`) | Günlük; ay sonu kapanışında | Masaüstü |
| Genel müdür | Üst yönetim — **varsayım** | Haftalık, kurul öncesi | Telefon ağırlıklı |
| Satış direktörü | Satış — **kanıt**: CRM görev birimi 4 = Satış | Haftalık (kanal ve cari kârlılığı) | İkisi de |
| Yayın yönetmeni (kitap/seri kârlılığı) | Editörya — **kanıt**: CRM sözleşme statüsü «2- Yayın Yönetmeninde» | Aylık, baskı ve yeni kitap kararlarında | Masaüstü |
| Yönetim kurulu (dolaylı, DYK paketiyle) | Kurul — **varsayım** | Kurul dönemi | Telefon/tablet |

## 3. Bugün bu iş nasıl yapılıyor

Doğrudan gözlem yok; aşağıdakilerin çoğu **varsayım**, kanıtlı olanlar belirtildi.

- **CFO / mali işler:** Aylık gelir tablosu Logo'nun kendi mali raporlarından (mizan, gelir tablosu) alınıp Excel'de yönetim
  formatına çevriliyor (varsayım). Satış tarafı için mevcut rapor seti canlı Logo'yu (192.168.0.25) okuyor (**kanıt**:
  `logo-155-frozen-copy` belleği). Adımlar: Logo'dan döküm → Excel'de hesap gruplama → önceki yılla elle karşılaştırma →
  yorum metni → sunum. Tıkanma: maliyetlendirme gecikmeli çalıştığı için (aşağıda) ay sonu brüt kâr ancak haftalar sonra
  kesinleşiyor (**kanıt**: 2026 maliyetlendirmesi 30.06.2026'ya kadar işlenmiş, `caveats/logo-timas.md`).
- **Muhasebe:** Aylık KDV, muhtasar, e-defter berat takvimini kendi takvimleriyle izliyorlar (varsayım). Portalın finansal
  denetimi 2026 beyanname başlığını Logo'da bulamadı (**kanıt**: «2026 beyanname başlığı yok (25 tarihsel kayıt)»,
  `PROJECT-MEMORY.md`), yani beyan takibi Logo dışında yürüyor.
- **Nakit:** Banka bakiyeleri internet bankacılığından ya da Logo banka modülünden günlük toplanıyor (varsayım). Alacak
  tahsil tarihi Logo'dan kesin çıkmıyor: Logo'da ödeme kapama kullanılmıyor (**kanıt**: PAYTRANS 116.514 plan satırının
  14'ünde ödenen tutar dolu). Nakit tahmini bu yüzden bugün muhtemelen kişisel deneyimle yapılıyor (varsayım).
- **Kitap kârlılığı:** Telif gideri Logo'da «Yazarların Telif Ücreti» hizmet kartından ve yazar carisinden ödeniyor
  (**kanıt**: `freelancer-payments-logo` belleği) ama kitaba bağlanmıyor; CRM'de telif hakediş tablosu boş (**kanıt**:
  `NEW_ODEMEHAKEDISBASE` 0 satır). Kitap başına «satış − maliyet − telif» bugün hiçbir yerde birlikte durmuyor.
- **Genel müdür:** Genel bakış ekranına bakıyor ya da CFO'dan özet istiyor (varsayım).

## 4. İhtiyaçlar ve acı noktaları

**CFO / mali işler**
1. Ay kapanır kapanmaz, önceki ay ve önceki yılın aynı ayıyla yan yana, yönetim formatında gelir tablosu.
2. Önümüzdeki 13 hafta için nakit girişi/çıkışı: hangi hafta açık veriyor, neden (büyük telif ödemesi, matbaa ödemesi, vergi).
3. Bütçe sapmasının nedenini tek cümlede görmek; kalemden Logo fişine inebilmek.
4. Rakamın ne kadar güvenilir olduğunu görmek: maliyetlendirilmemiş satır oranı, veri son tarihi, «yaklaşık» hesaplar.
5. Kurul/yönetim için finansal özet metnini sıfırdan yazmamak.

**Muhasebe**
1. Hesap → rapor satırı eşlemesinin (gelir tablosu satırları) bir kez tanımlanıp denetlenebilmesi.
2. Vergi takvimi: hangi beyan hangi gün, hazırlığı bitti mi.
3. Rapordaki her rakamın Logo mizanıyla birebir tuttuğunun görünmesi (finansal denetimin 0,01 TL toleransıyla).

**Genel müdür**
1. Telefonda sabah 3-5 rakam: ciro, brüt kâr, nakit, vadesi geçmiş alacak, bütçe sapması; renkle.
2. «Neden?» sorusunu Zeki AI'a sorup kısa cevap almak.

**Satış direktörü**
1. Kanal ve büyük cari bazında kârlılık (iskonto sonrası), yalnız ciro değil.
2. İade ve iskonto yükünün kâra etkisi.

**Yayın yönetmeni**
1. Kitap ve seri bazında katkı payı: satış − satılan malın maliyeti − telif; baskı tekrar kararına girdi.
2. Yeni çıkan kitabın ilk 6-12 ayda kendini ödeyip ödemediği.

## 5. Nasıl kullanmak isteyecekler

### Kullanıcı hikâyeleri

- CFO olarak ayın ilk iş günü önceki ayın gelir tablosunu önceki ay ve geçen yılın aynı ayıyla yan yana görmek istiyorum,
  çünkü yönetim toplantısına Excel hazırlamadan girmek istiyorum.
- CFO olarak önümüzdeki 13 haftanın nakit akışını hafta hafta görmek istiyorum, çünkü açık veren haftayı önceden bilip
  ödeme sırasını ya da krediyi planlamalıyım.
- CFO olarak bir gider kaleminin bütçeden sapmasına tıklayıp hangi fişlerden geldiğini görmek istiyorum, çünkü sapmanın
  kayıt hatası mı gerçek harcama mı olduğunu ayırmalıyım.
- CFO olarak raporun hangi kısmının yaklaşık olduğunu (maliyetsiz satır, kapamasız vade) rakamın yanında görmek istiyorum,
  çünkü kurula yanlış kesinlikte rakam götürmek istemiyorum.
- CFO olarak Zeki AI'ın yazdığı aylık finansal özet taslağını düzeltip onaylamak istiyorum, çünkü kurul paketi bu metinle
  gidiyor.
- Muhasebe uzmanı olarak hesap planındaki her hesabın gelir tablosunun hangi satırına gittiğini bir kez eşlemek ve eşlenmemiş
  hesabı uyarı olarak görmek istiyorum, çünkü yeni açılan hesap raporda sessizce kaybolmamalı.
- Muhasebe uzmanı olarak bu ayın beyan takvimini ve her beyanın hazırlık durumunu görmek istiyorum, çünkü son günü
  kaçırmak ceza doğurur.
- Genel müdür olarak telefonda sabah beş rakamı ve kırmızı olanın nedenini görmek istiyorum, çünkü gün içinde masaüstüne
  oturmadan karar veriyorum.
- Satış direktörü olarak kanal ve cari bazında iskonto sonrası kâr görmek istiyorum, çünkü yüksek cirolu ama kâr
  bırakmayan müşteriyle koşulları yeniden konuşmalıyım.
- Yayın yönetmeni olarak bir serinin kitaplarını telif düşülmüş katkı payıyla sıralamak istiyorum, çünkü baskı tekrarı ve
  yeni cilt kararını kârlılığa göre vermek istiyorum.

### Ana ekranlar ve akış

Öneri: Finans alanında yeni sayfa **«Finansal raporlar»** (Genel bakış soru ekranı olarak kalır, finansal denetim ayrı kalır).
Sekmeler:

1. **Özet** (ilk açılış): 5-6 gösterge kartı — net ciro, brüt kâr (maliyetli satır oranıyla), faaliyet gideri, nakit
   pozisyonu, vadesi geçmiş alacak, bütçe sapması. Her kartta veri son tarihi ve «yaklaşık» rozeti. Altında «bu ay dikkat»
   listesi (en büyük 3 sapma, yaklaşan büyük ödeme, vergi son günü).
2. **Gelir tablosu:** aylık / çeyreklik / yıl başından; sütunlar bu dönem · önceki dönem · geçen yıl aynı dönem · bütçe.
   Satıra dokununca alt hesaplar, sonra Logo fişleri (finansal denetimdeki hesap → fiş geçişi yeniden kullanılır).
3. **Bütçe–gerçekleşme:** M46'nın yürürlükteki planını okur; departman ve kalem bazında sapma, sapma açıklaması alanı.
4. **Kârlılık:** kitap · seri · yayınevi · kanal · cari; satış, iskonto, satılan malın maliyeti, telif, katkı payı.
5. **Nakit:** bugünkü pozisyon + 13 haftalık tablo (giriş: planlı alacak, çek/senet vadesi; çıkış: satıcı borcu, telif
   takvimi, vergi, bütçe gider temposu); her satır kaynağıyla.
6. **Vergi takvimi:** yılın beyan günleri, sorumlu, durum.
7. **Senaryo** (ikinci sürüm): varsayım kaydırıcıları (satış hacmi, iskonto, kur, gider artışı) → gelir tablosu ve nakit.

En sık üç işlem:
- «Geçen ayın gelir tablosuna bakmak»: menü → Finansal raporlar → Gelir tablosu (açılışta son kapanmış ay seçili) = **2 dokunuş**.
- «Bir sapmanın kaynağını bulmak»: Özet'te sapma kartı → kalem → fiş listesi = **3 dokunuş**.
- «13 haftalık nakitte açık haftayı görmek»: Nakit sekmesi, açık hafta kırmızı ve en üstte = **2 dokunuş**.

Telefonda: yalnız Özet ve Nakit'in hafta listesi tam; gelir tablosu dikey kart listesine döner, geniş tablo kendi
kapsayıcısında kayar (AGENTS.md mobil kuralı).

### Zeki AI'a soracakları örnek sorular

- «Ağustos gelir tablosunu geçen yılın ağustosuyla karşılaştır, brüt kâr neden düştü?»
- «Bu yıl telif düşüldükten sonra en çok katkı payı bırakan 20 kitap hangileri?»
- «Önümüzdeki 13 haftada nakit açığı veren hafta var mı, en büyük çıkış kalemi ne?»
- «Pazarlama giderleri yıl başından bu yana bütçenin yüzde kaçında?»
- «Timaş Çocuk'un brüt kâr marjı geçen yıla göre nasıl?»
- «Kitapyurdu'nun iskonto sonrası kârlılığı D-Market'e göre nasıl?»
- «Bu ay hangi beyannameler var, son günleri ne?»
- «Maliyeti işlenmemiş satışlar cironun yüzde kaçı?»

### Otomasyon katmanı

| Adım | Katman | Not |
|---|---|---|
| Logo'dan günlük okuma, özet kartlar, aylık gelir tablosu taslağı | K1 | Rapor oluşur; «kapandı» işareti insanındır. |
| Bütçe–gerçekleşme karşılaştırması ve sapma uyarısı | K1 | Hedef/bütçe M46'dan; eşik M46 kararı. |
| Vergi takvimi hatırlatması | K1 | Takvim elle yüklenir (dış veri). |
| Hesap → rapor satırı eşlemesi | K2 | Zeki hesap adından önerir, muhasebe onaylar; eşlenmemiş hesap uyarıda kalır. |
| Aylık finansal özet metni, sapma açıklaması | K2 | Zeki taslak yazar, CFO düzeltir/onaylar; onaylı metin DYK'ya gider. |
| Kitap kârlılığı, nakit tahmini, yatırım geri dönüşü, senaryo | K3 | Zeki hesaplar ve varsayımlarını yazar; karar CFO/yönetim. |
| «Finansal kararlar → Logo kayıt entegrasyonu» (iş tanımı p2.4) | Kapsam dışı | Portal Logo'ya yazmaz. |

### Bildirim / uyarı

- CFO + genel müdür: her iş günü 08:30 özet e-postası (Planlı raporlar altyapısı; kart ve bağlantı, ek dosya yok).
- CFO: bütçe sapması eşiği aşılınca (Uyarılar: kural = soru), 13 haftalıkta açık hafta ilk kez göründüğünde.
- Muhasebe: beyan son gününe 7 ve 2 gün kala; eşlenmemiş yeni hesap göründüğünde.
- Kanal: e-posta (SMTP test sunucusunda ayarlı; müşteri VM'inde ölçülecek) + portal içi. Telefon bildirimi yok.

### Onay ve yetki

| Kim | Görür | Değiştirir | Onaylar |
|---|---|---|---|
| CFO | Hepsi | Senaryo, sapma açıklaması | Aylık rapor «kapandı», özet metni |
| Muhasebe | Hepsi | Hesap eşlemesi, vergi takvimi | Eşleme |
| Genel müdür | Özet, gelir tablosu, nakit | — | — |
| Satış direktörü | Kârlılık (kanal/cari) | — | — |
| Yayın yönetmeni | Kârlılık (kitap/seri) | — | — |

Öneri anahtarları: `sayfa:finansal-raporlar`; `ozellik:finans.nakit` (nakit ve banka görme — ayrı, çünkü satış ve editörya
için gerekmiyor), `ozellik:finans.esleme` (açıkça verilir), `ozellik:finans.rapor-onay` (açıkça verilir),
`ozellik:finans.senaryo`; mevcut `ozellik:veri.disa-aktar`, `ozellik:kart.sql-goster`. Zeki AI tarafında Aşama C'deki
`veri:muhasebe` kapsamı olmadan gelir tablosu soruları herkese açılmamalı.

## 6. Veri

| Gereken veri | Kaynak (Logo / CRM / T-soft / kullanıcı girer / dış) | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Muhasebe hareketleri (hesap, fiş, borç/alacak) | Logo EMFLINE/EMFICHE/EMUHACC | 2026 kopyası (411) finansal denetimde okunuyor: 246.404 hareket, 379 hesap, son kayıt 17.08.2026 | .155 donmuş kopya; canlı Logo (.25) okunamıyor. 2021–25 kopyası (211) finansal denetime eklenmedi → geçen yıl karşılaştırması için açılış/kapanış kuralı doğrulanmalı |
| Satış, iade, iskonto | Logo INVOICE/STLINE | Sertifikalı: net ciro 2026 848,1 Mn ₺ (fatura seviyesi), satır seviyesi LINENET; satış = faturalı satır | Hazır |
| Satılan malın maliyeti | STLINE `AMOUNT × OUTCOST` | Maliyetlendirme 30.06.2026'ya kadar; 2026 satış satırlarının %20'sinde OUTCOST = 0 | **Kritik boşluk**: aylık brüt kâr kapanan ay için kesin değil |
| Gelir tablosu kapanışı (7/A → 6xx yansıtma) | Logo | Finansal denetim: «7 grubu açıkken gelir tablosu kârlılık oranları geçmiş sayılmaz»; ACCTYPE güvenilmez (374/379 = 0) | Aylık yansıtma yapılıyor mu ölçülecek; hesap karakteri eşleme tablosuyla tutulmalı |
| Faaliyet giderleri, masraf merkezi | Logo EMFLINE 7xx | M46 (`budget_sources.py`) 7xx'i yansıtma (7x1) ve kapanış satırları hariç, masraf merkezine (`EMCENTER`) göre okuyup `semantic_budget_expense_actuals`'a yazıyor | M45 aynı tabloyu okur; 6xx gelir hesapları ve 7/A kapanışı ayrıca ölçülecek |
| Telif gideri (kitap bazında) | Logo hizmet kartı «Yazarların Telif Ücreti» + M6 hakediş tabloları | Logo'da cariye ödeniyor, kitaba bağlı değil; CRM hakediş 0 satır; M6 hakedişi yalnız portala alınmış sözleşmeler | Kitaba dağıtım kuralı gerekir (M54); geçmiş dönem ölçülecek |
| Baskı/üretim maliyeti (kitap bazında) | Logo alış (TRCODE 1/4) veya stok maliyeti | CRM baskı tabloları 2015–2018 (eski) | OUTCOST'un baskı maliyetini içerip içermediği ölçülecek |
| Banka bakiyeleri | Logo banka hareketleri | Finansal denetimde 17.405 banka hareketi okundu | Ekstre yok; donmuş kopyada bakiye 17.08'in |
| Alacak vadeleri | Logo PAYTRANS + CLFLINE | Kapama yok → vadesi geçmiş/yaşlandırma yalnız FIFO yaklaşık; DSO yaklaşık | Nakit girişi tahmini «yaklaşık» etiketli olmalı |
| Çek/senet portföyü | Logo CSCARD/CSTRANS | 2026'da 6 karşılıksız çek olayı (6,33 Mn ₺) ölçüldü | Portföy vadesine göre giriş ölçülecek |
| Satıcı borcu vadeleri | Logo PAYTRANS (320) | Satıcı borcu yaşlandırma FIFO sorgusu bilgi paketinde | Yaklaşık |
| Telif ödeme takvimi | M6 `semantic_contract_payments` | Test sunucusunda; deneme kayıtları silindi, gerçek kayıt yok | Kullanım başlayınca dolar |
| Bütçe ve hedef | M46 | main'de: `/timas/butce`; `GET /api/v1/budget/tracking`, `/targets`, `/deviations`; tablo `semantic_budget_dept_lines`, görünüm `semantic_budget_approved_targets` | Onaylı plan yoksa sekme «bütçe onaylanmadı» der |
| Vergi takvimi | Dış (GİB) | Yok; müşteri VM'inde web taraması kapalı | Yıllık takvim elle yüklenir |
| Kur | TCMB günlük dosya | M6 hakedişinde okunuyor | Kur tahmini yok; senaryoda kullanıcı girer |
| Faiz/enflasyon tahmini, sektör kârlılık karşılaştırması | Dış | Yok | Kullanıcı girer ya da ikinci sürüm |

## 7. Diğer modüllerle bağ

- **Girdi alır:** M46 (bütçe, kitap hedefleri, departman bütçesi), M6/M54 (telif gideri, telif ödeme takvimi), M9 (maliyet),
  M11 Baskı önerisi (baskı yatırımı), M18/M35 (kampanya maliyeti → geri dönüş), M59 (bayi bazlı beklenen tahsilat, riskli
  alacak), Finansal denetim (kontrol durumu → rapora «güvenilirlik» notu).
- **Çıktı verir:** DYK (finansal özet, gelir tablosu, nakit, bütçe sapması), M47 (likidite, kur, müşteri yoğunlaşması
  göstergeleri), M46 (gerçekleşme, revizyon girdisi), Panolar (kartlara eklenebilir göstergeler).

## 8. Kısıtlar

- Portal **Logo'ya ve CRM'e yazmaz**; iş tanımındaki «finansal kararlar → Logo kayıt entegrasyonu» kapsam dışıdır.
- **Veri tazeliği:** Logo .155 donmuş kopya (son fatura 17.08.2026). «Anlık» ifadesi ekranda kullanılmaz; her kartta veri
  son tarihi yazar. Canlı Logo erişimi TİMAŞ BT kararı.
- Ekranda teknoloji/ürün adı yok (mevcut rapor setine «mevcut rapor» denir); demo veri yok; satır/sonuç tavanı yok.
- «Yaklaşık» hesaplar (FIFO vade, DSO, maliyetsiz satır) rakamın yanında açıkça etiketlenir; boş sonuç «sıfır» gibi
  sunulmaz (finansal denetimin ilkesi).
- Vergi cezası, mevzuat uygunluk hükmü üretilmez (finansal denetim analizindeki sınır).
- KVKK: kitap kârlılığında telif satırı yazar adına iner; yazar bazında telif tutarı kişisel veridir → yetkiyle sınırlanır.

## 9. Kapsam önerisi

**İlk sürüm**
- Özet sekmesi (5-6 gösterge, veri son tarihi, yaklaşık rozetleri) + sabah e-postası.
- Aylık gelir tablosu: hesap → satır eşleme tablosu (muhasebe onaylı), dönem/önceki dönem/geçen yıl; satırdan fişe iniş.
- Bütçe–gerçekleşme (M46 uçlarından; onaylı plan yoksa sekme «bütçe onaylanmadı» der).
- Kârlılık: kitap/seri/yayınevi/kanal/cari için net satış − iskonto − satılan malın maliyeti; maliyetsiz satırlar ayrı
  sütunda; telif sütunu M6/M54 verisi olan kitaplarda dolu, olmayanda «telif verisi yok».
- Nakit: pozisyon + 13 haftalık tablo, her satırın kaynağı ve yaklaşıklığı yazılı.
- Vergi takvimi (elle yüklenir) + hatırlatma.

**Sonraki sürüm**
- Senaryo (iyimser/baz/kötümser) ve 3-6-12 ay nakit tahmini.
- Baskı ve kampanya yatırım geri dönüşü (M11, M18/M35 verisiyle).
- Zeki AI aylık özet metni ve sapma açıklaması (K2) → DYK paketi.
- Sektör karşılaştırması, faiz/enflasyon varsayımları.

**Yeniden kullanılacaklar**
- `backend/semantic_bridge/financial_audit.py`, `financial_audit_rules.py`, `financial_audit_evidence.py` — 2026 kopyasına
  kilitli okuma (`scope={n0:411}`), hesap → fiş ayrıntısı, hazır rapor/arşiv düzeni (`financial_audit_snapshot.py`).
- `backend/semantic_bridge/management/` — rapor = modül + `sql/`, dosya önbelleği, 5 dk yenileme, `LiveStatus`.
- `backend/semantic_bridge/budget_sources.py` (gider okuma tanımı, `L_CAPIPERIOD` yıl eşlemesi), `src/canvas/cfo.ts` (satış sorguları), `src/canvas/stitch/CardSql.tsx` (SQL'i göster).
- `backend/semantic_bridge/reports.py` (planlı e-posta), `alerts.py` (eşik uyarısı), `board.py` (panoya kart).
- `configs/semantic/knowledge/logo/knowledge/sql/{vadesi-gecmis-yaslandirma-fifo,satici-borcu-yaslandirma-fifo,ortalama-tahsilat-suresi-dso}.md`.
- `backend/semantic_bridge/contracts_royalty.py` (kur okuma), M46'nın gerçekleşme tabloları (`semantic_budget_*_actuals`).

## 10. Uzmanlara sorulacak sorular

1. Aylık gelir tablosunu Logo'da nasıl kapatıyorsunuz — 7/A mı 7/B mi; 7xx → 6xx yansıtma her ay mı, yıl sonunda mı?
2. Maliyetlendirme neden 30.06.2026'da kalmış, ne sıklıkla çalıştırılıyor; ay kapanışına bağlanabilir mi?
3. Kitap kârlılığında kitaba hangi maliyetler yüklenmeli (baskı, telif, tasarım/çeviri, pazarlama, genel gider payı)?
4. Banka bakiyesini ve nakit planını bugün hangi araçla, hangi sıklıkla tutuyorsunuz; Logo banka hesapları güncel mi?
5. Canlı Logo'ya (.25) salt okunur erişim ne zaman verilebilir?

## 11. Başarı ölçütü

- Ay kapanışından gelir tablosunun hazır olmasına kadar geçen süre: bugünkü ölçülecek → hedef 1 iş günü.
- Gelir tablosu toplamı ile Logo mizanı farkı: her ay |fark| < 0,01 TL; eşlenmemiş hesap sayısı 0.
- 13 haftalık nakit tahmininin sapması: her hafta tahmin/gerçekleşen karşılaştırması tutulur, 13 hafta sonra ortalama
  mutlak sapma raporlanır (hedef sayı ilk üç ay ölçüldükten sonra konur).
- Kullanım: CFO ve genel müdürün haftada en az 3 gün açması; kurul paketi finans bölümünün Excel'siz hazırlanması.
- Kârlılıkta maliyetsiz satır oranının ekranda görünür olması ve zamanla düşmesi (maliyetlendirme düzenliyse).

## 12. Uzman gözüyle en iyi sistem

Kendimi 15 yıllık bir mali işler direktörünün yerine koyuyorum: orta büyüklükte, toptan ağırlıklı (2026'da cironun ~%95'i
toptan faturada — `live-bi-numbers-2026`), iskontosu yüksek (satır iskontosu ~%46), telif ve baskı maliyeti değişken bir
yayınevi.

**İyi yayınevleri ve iyi yazılımlar bu işi nasıl yapıyor.** Büyük yayın gruplarında aylık «flash P&L» ay kapanışının ilk
2-3 iş gününde çıkar; asıl kıymet başlık (kitap) düzeyinde kârlılıktır: net satış − iade karşılığı − basım maliyeti − telif
− doğrudan pazarlama = başlık katkı payı. Telif, satıştan ödemeli sözleşmelerde dönem sonunu beklemeden **tahakkuk** olarak
aylık kâra yansıtılır; yoksa kitap ödendiği çeyrekte zarar, arada kârlı görünür. İade riski yüksek kanallarda (dağıtıcı,
zincir) iade karşılığı ayrılır. Kurumsal planlama yazılımlarının ortak iyi yanı: her rakamın kaynak fişe tek tıkla inmesi,
«tahmin» ile «gerçekleşen»in aynı tabloda renkle ayrılması, 13 haftalık nakit tablosunun her hafta kapanıp bir önceki
tahminle karşılaştırılması (tahmin doğruluğu görünür olur). Zayıf yanları: kurulum ağır, hesap eşlemesi aylarca sürer,
yorum metni yok.

**TİMAŞ için mükemmel sistem:** Logo'dan kendiliğinden kapanan bir aylık gelir tablosu (hesap eşlemesi bir kez onaylanır,
yeni hesap uyarı olur); yanında satış tarafından hesaplanan net satışla **mutabakat satırı** (muhasebe 600/610 ile fatura
satırı arasındaki fark ve nedeni); kitap/seri/yayınevi/kanal/cari katkı payı, telif tahakkuku M6/M54'ten; nakitte 13 hafta
her pazartesi yeniden kurulur ve geçen haftanın tahmini ile gerçekleşeni yan yana durur; her rakamın yanında «veri
17.08.2026'ya kadar», «maliyetsiz satır %20», «vade FIFO yaklaşık» gibi dürüst notlar; Zeki AI yalnız yorumu yazar,
rakamı asla. Her şey telefonda okunur, masaüstünde incelenir.

**Bir iş günü (CFO):**
- 08:30 — Telefona gelen özet: dün itibarıyla ciro, brüt kâr (maliyetli satır payıyla), nakit, vadesi geçmiş alacak,
  bütçe kullanımı. Kırmızı olan tek satır: «Pazarlama gideri Ağustos'ta bütçenin %128'i».
- 09:15 — Masaüstünde Bütçe–gerçekleşme → Pazarlama → alt hesap → fişler: tek bir fuar faturası iki kez kaydedilmiş gibi
  görünüyor; muhasebeye not düşüyor (fişi portaldan açıp Logo'da düzeltilecek).
- 11:00 — Nakit sekmesi: 6. hafta açık veriyor; neden kolonu «Telif ödeme takvimi: 3 büyük hakediş + KDV». Telif
  biriminden birini bir hafta öteleme ihtimalini soruyor.
- 14:00 — Kârlılık → Seri: yeni çocuk serisinin ilk 4 kitabı iade sonrası katkı payında eksi; baskı tekrarı kararına not.
- 16:30 — Zeki AI'ın aylık özet taslağını açıyor; iki cümleyi düzeltiyor, «onayla» → DYK paketine gidiyor.
- 17:30 — Muhasebeden «Ağustos kapandı» onayı geliyor; gelir tablosu kilitleniyor, sonraki değişiklik fark olarak görünür.

**«Bunu görürsem hemen kullanırım»**
1. Rakamdan Logo fişine iki dokunuşta inmek ve rakamın mizanla tuttuğunu gösteren yeşil işaret.
2. 13 haftalık nakitte geçen haftanın tahmini ile gerçekleşenin yan yana durması.
3. Kitap başına telif ve iade sonrası katkı payı — bugün hiçbir yerde yok.

**«Bunu yaparsanız kullanmam»**
1. Yaklaşık rakamı kesin gibi sunmak (maliyetsiz satırı marja katmak, FIFO vadeyi gerçek gecikme diye göstermek).
2. Logo mizanıyla kuruşu tutmayan gelir tablosu; bir kez yanlış çıkarsa ekip Excel'e geri döner.
3. Modelin yazdığı metinde tabloda olmayan bir rakam — tek bir uydurma sayı bütün modülün güvenini bitirir.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (tablo / görünüm / ölçü) | CRM (varlık / alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Aylık gelir tablosu | `LG_{firma}_01_EMFLINE` (DEBIT/CREDIT, DATE_, CANCELLED, ACCOUNTREF) + `LG_{firma}_01_EMFICHE` + `LG_{firma}_EMUHACC`; firma yılı `L_CAPIPERIOD`'dan (411 = 2026, 211 = 2021–25); 690/692 devir ve yıl sonu kapanış fişleri hariç | — | Yok | Rakam muhasebe kaydıdır. |
| Hesap → rapor satırı eşlemesi | `EMUHACC.CODE`, `DEFINITION_` (379 hareketli hesap, 2026) | — | Yeni/eşlenmemiş hesap için aday satır seçer: kapalı küme (satır kodları listesi), tek token + olasılık (`structured_outputs.choice` + logprobs); düşük marjlı öneri «belirsiz» işaretlenir | 379 hesabı elle eşlemek yorucu; seçim kapalı kümeden, insan onaylar. |
| Net satış mutabakatı | Sertifikalı `net_ciro` (INVOICE NETTOTAL, TRCODE 7,8,9 − 2,3) ve satır seviyesi `LINENET` (`INVOICEREF <> 0`) ↔ 600/610/611 hesapları | — | Yok | Satış ve muhasebe iki kaynaktır; fark görünür olmalı. |
| Brüt kâr / maliyetli satır oranı | `STLINE.AMOUNT × OUTCOST` (OUTCOST ≠ 0), ölçü `brut_kar_marji`; maliyetsiz satır payı ayrı | — | Yok | Maliyetlendirme gecikmesi (30.06.2026) rakamın yanında yazmalı. |
| Faaliyet gideri, departman | M46'nın okuduğu `semantic_budget_expense_actuals` (EMFLINE 7xx, `EMCENTER`) | — | Yok | M46 ile aynı tanım; iki modül farklı gider söylememeli. |
| Bütçe–gerçekleşme | M46 `GET /api/v1/budget/tracking`, `/deviations`, `semantic_budget_approved_targets` | — | Sapma açıklaması taslağı (K2) | Sayılar M46'dan; model yalnız neden cümlesi yazar. |
| Kitap/seri/kanal/cari kârlılığı | `STLINE` (LINENET, AMOUNT, OUTCOST), `ITEMS.SPECODE` (yayınevi), `CLCARD.SPECODE2` (kanal), `CLCARD` (cari) | `new_kitapBase` (seri/dizi, yayın yönetmeni — alan adları kabulde ölçülecek), `new_kitapBase.new_StokKodu` ↔ `ITEMS.CODE` | Yok | Deterministik toplam. |
| Telif tahakkuku | Logo «Yazarların Telif Ücreti» hizmet kartı (`LG_{firma}_SRVCARD`, alınan hizmet TRCODE 4) | M6 `semantic_contract_statements`, `semantic_contract_payments` (köprü tabloları) | Yok | Telif hesabı M6 motorundan (`contracts_royalty.py`). |
| 13 haftalık nakit | `PAYTRANS` (SIGN 0/1, DATE_), `CLFLINE`, `CSCARD`/`CSTRANS` (çek/senet vadesi, durum), `BNFLINE`/`BANKACC` ve 102 hesabı | `new_tahsilatBase` (statuscode «Onay Bekliyor», `new_vadetarihi`, `new_tutar`, `new_tahsilattipi`) — Logo'ya henüz aktarılmamış çek/senet | Yok | Vadeler SQL'den; CRM'deki onay bekleyen tahsilat Logo'ya düşmeden önce görünür. |
| Aylık finansal özet metni | Yukarıdaki sonuç JSON'u | — | 5-8 cümlelik Türkçe yorum taslağı; **çıktıdaki her sayı girdideki sayılardan biri olmalı** (sonradan düzenli ifadeyle denetlenir, tutmazsa taslak reddedilir) | Yazma yükü; kurul paketi bu metni kullanır. |
| Zeki AI'a serbest soru | Katalogdaki sertifikalı ölçüler (`configs/semantic/knowledge/logo/knowledge/metrics/logo-timas.md`) | CRM okunur tablolar | Mevcut `/api/v1/ask` hattı | Yeni motor yok. |

Model çağrıları `rt.llm_for("finance")` ile (arka plan işleri `BATCH` önceliği); `LlmClient` doğrudan kurulmaz. Ekranda
«Zeki AI önerisi» yazar.

## 14. Kodlama planı (kodlayıcıya devir)

**Köprü dosyaları** (M46 düzeni: `budget.py` / `budget_api.py` / `budget_sources.py` örnek alınır)
- `backend/semantic_bridge/finance.py` — tablolar, hesaplama (gelir tablosu, kârlılık, nakit, özet), onay akışı.
- `backend/semantic_bridge/finance_sources.py` — Logo/CRM okuma (`connector_from_file`, her çağrıda yeni bağlantı, zaman
  aşımı `FINANCE_QUERY_TIMEOUT_SEC`, sessiz kesme yok — `budget_sources.runner` kopyası değil, ortak yardımcıya taşınması
  önerilir). Firma yılı `L_CAPIPERIOD`'dan; kopya yıllar atlanır.
- `backend/semantic_bridge/finance_api.py` — `register(app, rt, require_caller, can)`; `app.py`'de M46 kaydının yanına.

**Tablolar**
- `semantic_finance_lines` (tenant_id, kod PK, ad, sira, ust_kod, isaret, tur gelir|gider|ara_toplam, formül_json)
- `semantic_finance_account_map` (tenant_id, hesap_kodu PK, satir_kodu, durum oneri|onayli|dislandi, oneri_satir,
  oneri_olasilik, onaylayan, onay_tarihi, not)
- `semantic_finance_account_actuals` (year, month, hesap_kodu, merkez_kodu, borc, alacak — Logo okumasının anlık görüntüsü)
- `semantic_finance_closes` (tenant_id, year, month PK, durum acik|kapandi, kapatan, kapanis_tarihi, ozet_hash, not)
- `semantic_finance_cash_runs` (id, tenant_id, run_at, veri_son_gunu, params_json) ve `semantic_finance_cash_lines`
  (run_id, hafta_baslangic, yon giris|cikis, kalem, kaynak, tutar, yaklasik bool, ayrinti_json)
- `semantic_finance_tax_calendar` (id, tenant_id, beyan, donem, son_gun, sorumlu, durum, not)
- `semantic_finance_notes` (id, tenant_id, year, month, tur ozet|sapma, hedef_anahtar, metin, durum taslak|onayli,
  llm_job_id, hazirlayan, onaylayan, tarih)
- `semantic_finance_meta` (anahtar → JSON: son okuma, veri son günü, maliyetli satır payı)

**Uçlar** (`/api/v1/finance/*`)
- `GET summary` · `GET status` · `POST refresh` · `POST run-due` (SYSTEM)
- `GET pnl?year&month&grain=ay|ceyrek|ytd&compare=onceki,gecen-yil,butce` · `GET pnl/lines/{kod}/accounts` ·
  `GET pnl/accounts/{hesap}/entries?page` (sayfalı fiş satırları)
- `GET account-map` · `PATCH account-map/{hesap}` · `POST account-map/suggest` (model işi, 202) · `POST account-map/approve`
- `GET reconciliation?year&month` (muhasebe net satış ↔ fatura net satış)
- `GET profitability?by=kitap|seri|yayinevi|kanal|cari&year&from&to&page`
- `GET cash?weeks=13` · `POST cash/rebuild` · `GET cash/history` (geçmiş tahmin ↔ gerçekleşen)
- `GET/POST/PATCH/DELETE tax-calendar`
- `GET notes` · `POST notes/draft` (model, 202) · `PATCH notes/{id}` · `POST notes/{id}/approve`
- `POST closes/{year}/{month}` (kapat) · `DELETE closes/{year}/{month}` (yeniden aç, gerekçe zorunlu)
- Dışa aktarma: `GET pnl/export.xlsx`, `GET profitability/export.csv` (`ozellik:veri.disa-aktar`)

**Ekranlar** `src/canvas/finance/`: `FinanceScreen.tsx` (sekme adreste), `SummaryTab.tsx`, `PnlTab.tsx`, `BudgetTab.tsx`
(M46 uçlarını okur), `ProfitTab.tsx`, `CashTab.tsx`, `TaxTab.tsx`, `AccountMapSheet.tsx`, `api.ts`. Rota
`/timas/finansal-raporlar` (`App.tsx`'te lazy). Menü: `navModel.ts` → «Finans» alanının **ilk** öğesi «Finansal raporlar».
Kampüs: `ModulesMenu.tsx` `LIVE.M45 = '/finansal-raporlar'`; `GROUP_HOME['Finans & Risk']` bu sayfaya yönelir. SQL'i göster
için `CardSql.tsx`.

**Yetki** (`access_catalog.json`, `access.py` RULES + FEATURE_RULES)
- `sayfa:finansal-raporlar` → önek `/api/v1/finance/`; `run-due` SYSTEM.
- `ozellik:finans.nakit` (Nakit sekmesi ve `cash*` uçları), `ozellik:finans.esleme` (**açıkça**), `ozellik:finans.kapanis`
  (**açıkça**), `ozellik:finans.not-onay` (**açıkça**; hazırlayan onaylayamaz), `ozellik:finans.vergi-takvimi`.
- Bütçe sekmesi M46 uçlarını okur → `access.RULES`'ta `/api/v1/budget/tracking` ve `/deviations` satırlarına
  `page("finansal-raporlar")` eklenir.

**Zamanlayıcı** `scripts/server/timas-finance.{timer,service}`: saatte bir `POST /api/v1/finance/run-due` → güncel yıl
hesap ay toplamları, maliyetli satır payı, veri son günü; pazartesi 07:00 nakit tablosunu yeniden kurar ve bir önceki
haftanın gerçekleşenini yazar; iş günü 08:30 özet e-postası (`alerts.smtp_settings`). İlk koşu elle yapılır
(`run-it-before-it-runs-itself`).

**Kabul testleri** (gerçek DB, test sunucusu; «bugün» = veri son günü `SELECT MAX(DATE_) FROM LG_411_01_INVOICE WHERE CANCELLED=0`)
1. Mizan denkliği: `SELECT SUM(DEBIT) - SUM(CREDIT) FROM LG_411_01_EMFLINE WHERE CANCELLED = 0` → |fark| < 0,01; ekranın
   gelir tablosu toplamı + bilanço tarafı aynı fişlerden gelir.
2. Gelir tablosu satırı: seçilen ay için `SELECT A.CODE, SUM(F.DEBIT - F.CREDIT) FROM LG_411_01_EMFLINE F JOIN
   LG_411_EMUHACC A ON A.LOGICALREF = F.ACCOUNTREF WHERE F.CANCELLED = 0 AND F.DATE_ >= '2026-07-01' AND F.DATE_ <
   '2026-08-01' AND A.CODE LIKE '6%' GROUP BY A.CODE` → eşlemedeki satır toplamlarıyla kuruşu kuruşuna eşit (kapanış
   fişleri hariç tutma kuralı iki tarafta aynı).
3. Net satış mutabakatı: `SELECT SUM(CASE WHEN TRCODE IN (7,8,9) THEN LINENET ELSE -LINENET END) FROM LG_411_01_STLINE
   WHERE CANCELLED = 0 AND LINETYPE = 0 AND INVOICEREF <> 0 AND TRCODE IN (2,3,7,8,9) AND DATE_ >= '2026-01-01' AND DATE_ <
   '2027-01-01'` → 837.901.631,04 ₺ (M46 kaynağında ölçülen değer) = ekrandaki «fatura net satış» satırı.
4. Maliyetli satır payı: `SELECT SUM(CASE WHEN OUTCOST <> 0 THEN LINENET END) / SUM(LINENET) FROM LG_411_01_STLINE WHERE
   CANCELLED = 0 AND LINETYPE = 0 AND INVOICEREF <> 0 AND TRCODE IN (7,8)` → özet kartındaki oranla eşit.
5. Kitap kârlılığı (rastgele 5 stok kodu): `SELECT SUM(CASE WHEN L.TRCODE IN (7,8,9) THEN L.LINENET ELSE -L.LINENET END),
   SUM(CASE WHEN L.OUTCOST <> 0 THEN (CASE WHEN L.TRCODE IN (7,8,9) THEN 1 ELSE -1 END) * L.AMOUNT * L.OUTCOST END) FROM
   LG_411_01_STLINE L JOIN LG_411_ITEMS I ON I.LOGICALREF = L.STOCKREF WHERE I.CODE = :kod AND L.CANCELLED = 0 AND
   L.LINETYPE = 0 AND L.INVOICEREF <> 0 AND L.TRCODE IN (2,3,7,8,9)` → ekranda net satış ve maliyet aynı.
6. Vadesi geçmiş alacak: bilgi paketindeki `sql/vadesi-gecmis-yaslandirma-fifo.md` sorgusu `GETDATE()` yerine veri son
   günüyle koşulur → Nakit sekmesindeki kova toplamlarıyla eşit.
7. Gider tutarlılığı: `semantic_budget_expense_actuals` ay toplamı (M46) = finans gelir tablosundaki faaliyet gideri
   satırları toplamı (aynı dışlama kuralıyla).
8. Model metni: özet taslağındaki her sayı girdi JSON'unda var (otomatik test; yapay girdiyle, DB'siz).

**Bağımlılık:** M46 bitti (main'de) → Bütçe sekmesi hemen bağlanır. M6 bitti → telif sütunu portala alınmış sözleşmelerle
başlar; M54 gelince kitap bazında tahakkuk. Paralel kodlanabilir: M47 ve DYK bu modülün `GET summary` ve `pnl` uçlarını okur,
sözleşme (uç şekli) önce yazılırsa üçü aynı anda ilerler.

**Tahmini büyüklük:** L (hesap eşlemesi + gelir tablosu M, kârlılık S, nakit M, not/model S).
