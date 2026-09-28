# M47 — Risk Yönetimi ve Uyum: kullanıcı ihtiyaç analizi

Durum: kodlandı (dal `worktree-agent-a158e42e25cc349c0`, 2026-09-28; test sunucusunda doğrulanmadı) · Tarih: 2026-09-28 · Kaynaklar: iş tanımı `specs/M47.txt`, `specs/M49.txt`, `specs/DYK.txt`;
Veri Haritası (`veri_haritasi2.txt`: «Risk Girdileri», «İzleme Girdileri»); `PROJECT-MEMORY.md` (Finansal Denetim,
Yönetim Raporları/Baskı önerisi, M6, SEO «Haklar ve CRM», Yetki); `docs/analiz/finansal-denetim-2026-09-21.md`;
`docs/analiz/yetki-mekanizmasi-2026-09-27.md`; `docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`;
`configs/semantic/knowledge/logo/knowledge/caveats/logo-timas.md`; `configs/semantic/knowledge/crm/table_descriptions.json`
(`AccountBase`, `new_siparisBase`, `new_sozlesmeBase`); `backend/semantic_bridge/{financial_audit*.py,alerts.py,access.py,access_catalog.json}`;
kullanıcı belleği: live-bi-numbers-2026, logo-155-frozen-copy, crm-digital-rights-fields, timas-alerts, web-watch-open-sources,
customer-vm-web-watch-off, system-of-record-logo, no-tech-names-on-screens.

## 1. Modül ne işe yarar

İş tanımına göre M47: (1) **risk tespiti ve değerlendirme** — operasyonel (stok, lojistik, üretim), finansal (kur, faiz,
likidite), yasal uyum (telif, KVKK, ticaret mevzuatı), itibar (sosyal medya/basın) riskleri (K3, yönetim karar verir);
(2) **risk azaltma** — olasılık × etki risk matrisi ve öncelik sırası, iş sürekliliği planları (BCP), sigorta kapsamı
değerlendirmesi, uyum kontrol listesi ve takvimi (K2, hukuk + yönetim onaylar). Çıktı: risk matrisi, uyum raporu ve
yönetim kurulu risk brifingi (DYK'ya gider).

TİMAŞ'ın bugünkü sorunu: portalda **risk sinyali çok ama risk kaydı yok.** Sinyaller farklı ekranlarda dağınık duruyor:
finansal denetimin inceleme adayları (ör. kasa/çek ters bakiyesinde 2 hesap, 277.109,33 ₺), Baskı önerisinin «Risk/Acil»
kitapları, M6'nın «60 günde bitiyor» sözleşmeleri, SEO «Haklar ve CRM»'in internet hakkı olmayan kitapları, 2026'da 6
karşılıksız çek olayı (6,33 Mn ₺), maliyetlendirmenin 30.06.2026'da kalması, Logo kopyasının 17.08.2026'da donması.
Bunların **sahibi, eşiği, aksiyonu ve kurula giden özeti yok.** BCP, sigorta poliçeleri, KVKK envanteri ve uyum takvimi
hiçbir bağlı sistemde görünmüyor (varsayım: Excel/kâğıt ya da dış danışman).

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| Risk ve uyum koordinatörü (modülün sahibi) | **Varsayım** — TİMAŞ'ta bu unvan büyük olasılıkla yok; iş CFO ya da genel müdür yardımcısında (uzmanlara soru) | Haftalık; kurul öncesi yoğun | Masaüstü |
| Genel müdür (risk sahibi, K3 karar) | Üst yönetim — **varsayım** | Aylık; kritik uyarıda anlık | Telefon |
| CFO (finansal riskler: likidite, kur, alacak, faiz) | Finans — **varsayım** | Haftalık | İkisi de |
| Hukuk (telif, ticaret, KVKK uyumu; plan ve belge onayı) | İş tanımı «hukuk + yönetim onayı»; iç birim mi dış avukat mı **varsayım** | Olay bazlı, aylık uyum | Masaüstü |
| KVKK irtibat kişisi / veri sorumlusu temsilcisi | **Varsayım** (VERBİS kaydı varsa atanmıştır) | Aylık, başvuru geldikçe | Masaüstü |
| Operasyon sahipleri (depo/lojistik, üretim, satış) — risk sahibi | **Kanıt (birimler var)**: CRM BT taleplerinde Depo, Üretim, Satış departmanları | Aylık gözden geçirme | İkisi de |
| BT sorumlusu (M49 ile ortak: veri, erişim, yedek) | **Kanıt (birim var)**: CRM BT talep kaydı | Aylık | Masaüstü |
| Yönetim kurulu (DYK üzerinden) | Kurul — **varsayım** | Çeyreklik | Telefon/tablet |

## 3. Bugün bu iş nasıl yapılıyor

Doğrudan gözlem yok; hepsi **varsayım**, veriyle desteklenenler belirtildi.

- **Risk kaydı:** Resmî bir risk kaydı yoksa riskler yönetim toplantılarında sözlü konuşuluyor; varsa Excel'de, yılda bir
  güncelleniyor. Tıkanma: risk göstergesi (KRI) ile kayıt arasında bağ yok, «eşik aşıldı» bilgisi otomatik gelmiyor.
- **Finansal risk:** CFO kur, likidite ve alacağı kendi tablolarıyla izliyor. Veri: Logo'da ödeme kapama yok → alacak
  yaşlandırması yaklaşık (**kanıt**); risk limiti Logo'da tanımsız, CRM'de (**kanıt**).
- **Telif/sözleşme uyumu:** Telif birimi CRM'de sözleşme bitişini izliyor; biten sözleşmeyle satışın sürüp sürmediği
  sistematik kontrol edilmiyor (varsayım). Hak eksikleri SEO çalışmasında ortaya çıktı (**kanıt**: ~274 telif alış
  sözleşmesinde internet hakkı yok).
- **KVKK:** Aydınlatma, açık rıza ve iletişim izni CRM'de kısmen tutuluyor (**kanıt**: bayi başvurusu KVKK/iletişim izni ve
  tarihleri, İYS müşteri tipi alanları); envanter ve saklama süresi takibinin nerede yapıldığı bilinmiyor.
- **Vergi/ticari uyum:** Mali müşavir/muhasebe takviminde; portalın finansal denetimi Logo'da 2026 beyanname başlığı bulmadı
  (**kanıt**).
- **İtibar:** Basın ve web izleme portalda yalnız test sunucusunda (açık RSS + Wikidata); müşteri VM'inde kullanıcı
  kararıyla kapalı (**kanıt**: `customer-vm-web-watch-off`).
- **BCP / sigorta:** Poliçeler ve acil durum planları dosyada; yenileme tarihi takibi kişisel hatırlatmayla (varsayım).

## 4. İhtiyaçlar ve acı noktaları

**Risk ve uyum koordinatörü**
1. Tek risk kaydı: her riskin sahibi, olasılık × etki puanı, eğilimi, aksiyonu ve son gözden geçirme tarihi.
2. Göstergelerin (KRI) portaldaki mevcut verilerden kendiliğinden hesaplanması ve eşik aşınca riskin «gözden geçir» olması.
3. Uyum takvimi: yasal yükümlülükler, son günleri, kanıt belgeleri.
4. Kurul için üç sayfalık risk brifingi, her çeyrek aynı biçimde.

**Genel müdür**
1. Telefonda ilk 10 risk, kırmızıya dönen gösterge ve gecikmiş aksiyon.
2. «Bu risk için ne yapıyoruz, kim sorumlu» sorusunun tek cevabı.

**CFO**
1. Likidite, kur, müşteri yoğunlaşması, karşılıksız çek, vadesi geçmiş alacak göstergeleri eşikleriyle.

**Hukuk / KVKK**
1. Telif: süresi bitmiş ya da hakkı olmayan kitapların satışta olup olmadığı.
2. KVKK: işleme envanteri, saklama süreleri, başvuru ve ihlal kaydı, yıllık kontrol listesi.
3. Plan ve belge taslaklarının sürümlü onayı.

**Operasyon sahipleri**
1. Kendi alanındaki riskleri ve aksiyonları (stok, lojistik, üretim) görmek ve durumunu güncellemek.

## 5. Nasıl kullanmak isteyecekler

### Kullanıcı hikâyeleri

- Risk koordinatörü olarak bir riski kaydedip ona bir ya da birkaç gösterge bağlamak istiyorum, çünkü riskin gerçekten
  büyüyüp büyümediğini veriden görmeliyim.
- Risk koordinatörü olarak göstergesi kırmızıya dönen riskleri «gözden geçir» kuyruğunda görmek istiyorum, çünkü
  çeyreği beklemeden sahibine sormalıyım.
- Risk koordinatörü olarak uyum takviminde bu ayın yükümlülüklerini ve kanıtlarının yüklenip yüklenmediğini görmek
  istiyorum, çünkü denetimde kanıt isteniyor.
- Genel müdür olarak telefonda ısı haritasını ve ilk 10 riski görmek istiyorum, çünkü kurula girmeden önce durumu bilmeliyim.
- CFO olarak müşteri yoğunlaşması ve kur açığı göstergelerinin eşiklerini belirlemek istiyorum, çünkü eşiği ben
  sorumlu olduğum risk için koymalıyım.
- Hukuk olarak süresi bitmiş ama satışı süren kitapların listesini görmek istiyorum, çünkü telif ihlali riski doğuyor.
- KVKK irtibat kişisi olarak işleme envanterini ve saklama sürelerini güncel tutmak istiyorum, çünkü Kurul denetiminde
  istenir.
- Depo sorumlusu olarak kendi risklerimin aksiyonlarını telefondan «tamamlandı» işaretlemek istiyorum.
- Risk koordinatörü olarak Zeki AI'ın hazırladığı çeyreklik risk brifingini düzeltip onaylamak istiyorum, çünkü DYK
  paketine bu gidiyor.

### Ana ekranlar ve akış

Öneri: Finans alanında yeni sayfa **«Risk ve uyum»** (`/risk-uyum`).

1. **Özet** (ilk açılış): 5×5 ısı haritası (olasılık × etki; hücreye dokununca riskler), «gözden geçir» kuyruğu (eşik aşan
   gösterge, gözden geçirme tarihi geçen risk), gecikmiş aksiyonlar, bu ayın uyum yükümlülükleri.
2. **Risk kaydı**: liste (kategori, sahip, puan, eğilim, durum) → risk kartı (tanım, neden/sonuç, bağlı göstergeler ve
   son değerleri, aksiyonlar, gözden geçirme geçmişi, belgeler).
3. **Göstergeler (KRI)**: tanım (kaynak, formül, eşik sarı/kırmızı, yön, sahibi, sıklık), son 12 değer; kaynak ekranına
   bağlantı (finansal denetim bulgusu, bayi riski, baskı önerisi, sözleşme listesi).
4. **Uyum**: yükümlülük listesi (alan: telif, KVKK, vergi, ticaret, iş sağlığı), takvim, kanıt yükleme, durum.
5. **BCP ve sigorta**: kritik süreçler (kabul edilebilir kesinti süresi, sorumlu, son tatbikat), poliçeler (tür,
   teminat, bitiş), boşluk notu.
6. **Raporlar**: çeyreklik yönetim/kurul risk brifingi (taslak → onay → DYK).

En sık üç işlem:
- «Gözden geçir kuyruğunu temizlemek»: Özet → kuyruk öğesi → puan/eğilim güncelle + not = **3 dokunuş**.
- «Aksiyonu tamamlandı yapmak» (telefon): Özet → gecikmiş aksiyon → «Tamamlandı» (+ kanıt) = **2-3 dokunuş**.
- «Bu ayın uyum yükümlülükleri»: Uyum sekmesi (açılışta bu ay) = **2 dokunuş**.

### Zeki AI'a soracakları örnek sorular

- «Kırmızıya dönen göstergeler hangileri, hangi risklere bağlı?»
- «Sahibi olmayan ya da 90 günden uzun süredir gözden geçirilmemiş riskler?»
- «Cironun yüzde kaçı ilk 4 müşteriden geliyor, geçen yıla göre?»
- «Bu yıl karşılıksız çıkan çeklerin toplamı?»
- «Süresi bitmiş ama geçen ay satışı olan kitaplar?»
- «Önümüzdeki 60 günde biten sigorta poliçeleri?»
- «Döviz cinsinden telif yükümlülüğümüz ne kadar?»

### Otomasyon katmanı

| Adım | Katman | Not |
|---|---|---|
| Göstergelerin hesaplanması, eşik kontrolü, «gözden geçir» kuyruğu | K1 | Veri modüllerin uçlarından ve doğrudan SQL'den. |
| Gösterge tanımı ve eşik | K2 | Sahibi önerir, koordinatör onaylar; sürümlü. |
| Yeni risk önerisi (eşik aşımından, denetim bulgusundan) | K2 | Zeki AI risk kaydı taslağı yazar, koordinatör kabul/ret eder. |
| Olasılık × etki puanı, öncelik | K3 | İnsan puanlar; sistem yalnız göstergeyi yanına koyar. |
| Risk azaltma planı, BCP ve uyum belgesi taslağı | K2 | Zeki AI şablondan taslak; hukuk + yönetim onaylar. |
| Çeyreklik kurul risk brifingi | K2 | Zeki AI taslak; koordinatör ve genel müdür onaylar. |
| Mevzuat değişikliği takibi | K4 | Müşteride dış erişim kapalı; hukuk yüklediği metni Zeki AI özetler. |

### Bildirim / uyarı

- Risk sahibi: bağlı göstergesi kırmızıya döndüğünde, aksiyon termini 7 gün kala ve geçince; gözden geçirme tarihi geldiğinde.
- Koordinatör: haftalık özet (yeni kırmızılar, gecikmiş aksiyonlar, bu ayın uyum yükümlülükleri).
- Genel müdür: kritik (etki 5) riskin göstergesi kırmızıya dönünce aynı gün.
- Hukuk/KVKK: uyum yükümlülüğü son gününe 14 ve 3 gün kala; poliçe bitişine 60 gün kala.
- Kanal: e-posta + portal içi (Uyarılar altyapısı; kural = soru ya da modül ucu).

### Onay ve yetki

| Kim | Görür | Değiştirir | Onaylar |
|---|---|---|---|
| Risk koordinatörü | Hepsi | Risk kaydı, gösterge, uyum, BCP, sigorta | Gösterge tanımı, yeni risk önerisi |
| Genel müdür | Hepsi | — | Kurul brifingi, kritik risk kabulü |
| CFO | Hepsi | Finansal göstergelerin eşiği (öneri) | — |
| Hukuk / KVKK | Uyum, telif riskleri, KVKK envanteri | Uyum maddesi, kanıt, envanter | Plan/belge taslağı |
| Risk sahibi (operasyon) | Kendi riskleri | Aksiyon durumu, not | — |

## 6. Veri

| Gereken veri | Kaynak (Logo / CRM / T-soft / kullanıcı girer / dış) | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Finansal denetim bulguları | Portal `/api/v1/financial-audit/*` (Logo 2026) | 6 temel + 12 derin kontrol; son çalışmada 3 inceleme adayı, 2 muhasebe gözlemi; kasa/çek 2 hesap (277.109,33 ₺) | Bulgu ≠ risk; eşleme kuralı gerekir |
| Likidite, nakit | M45 (kodlanmadı), Logo banka/102 | Banka hareketleri finansal denetimde okunuyor | M45 gelince gösterge |
| Alacak riski, müşteri yoğunlaşması | Logo INVOICE/CLFLINE/PAYTRANS; M59 | İlk cariler Turkuvaz, Kitapyurdu, D-Market, Point (ölçüldü); FIFO yaklaşık vade | Yoğunlaşma oranı ölçülecek |
| Karşılıksız çek | Logo CSTRANS (STATUS 11) | 2026'da 6 olay, 6.326.658 ₺ (ölçüldü) | Hazır |
| Kur riski | Logo INVOICE `TRCURR ≠ 0`; M6 döviz sözleşmeleri | 74 döviz faturası (bilgi paketi) | Döviz borç/alacak pozisyonu ölçülecek |
| Faiz riski (kredi) | Logo banka kredileri (3xx/4xx hesaplar) | Görülmedi | Ölçülecek |
| Stok riski | Baskı önerisi (`management/baski_oneri.py`), CRM stok | «Risk/Acil» etiketleri var; Logo'da asgari stok tanımsız (ölçüldü) | Hazır (rapor önbelleğinden) |
| Veri tazeliği / sistem riski | Logo `MAX(DATE_)`; maliyetlendirme `OUTCOST` | Donmuş kopya 17.08.2026; maliyet 30.06.2026 | Gösterge olarak hazır |
| Lojistik | CRM `new_siparisBase` kargo entegrasyon sonuç/mesaj alanları, «Depoda Bekliyor» tarihi | Alanlar var | Doluluk ölçülecek |
| Tedarikçi yoğunlaşması (matbaa, kâğıt) | Logo INVOICE TRCODE 1/4 × `CLIENTREF` | Satınalma ölçüsü var | Tedarikçi türü sınıfı ölçülecek |
| Telif uyumu | CRM `new_sozlesmeBase` (bitiş, süresiz, statü, hak bitleri), M6, SEO «Haklar ve CRM» | İletim hakkı ölçüldü; M6 60 gün süzgeci | «Sözleşmesi bitmiş ama satan kitap» ölçülecek |
| KVKK | CRM izin alanları (`new_bayibasvurusukvkkizni`, iletişim izni, `obs_iys_customertype`), hassas kolon listesi | Alanlar var | İşleme envanteri ve saklama süreleri kullanıcı girer |
| Vergi/ticaret takvimi | Dış (GİB) + finansal denetim KDV bakiyeleri | 8 aylık KDV bakiyesi hesaplanıyor | Takvim elle yüklenir |
| İtibar | Basın ve web (test sunucusu) | Müşteri VM'inde kapalı | Müşteride elle kayıt |
| Sigorta poliçeleri, BCP | Kullanıcı girer | Yok | Tamamen yeni veri |
| Mevzuat değişiklikleri, sektör risk karşılaştırması | Dış | Yok; müşteride web kapalı | Yüklenen belge |

## 7. Diğer modüllerle bağ

- **Girdi alır:** Finansal denetim (bulgular), M45 (likidite, kur, bütçe sapması), M46 (sapma uyarıları), M59 (bayi segmenti,
  vadesi geçmiş, yoğunlaşma), M6/M54 (süre, hak eksikliği, telif yükümlülüğü), Baskı önerisi/M11 (stok riski), SEO «Haklar ve
  CRM» (dijital hak), M49 (erişim, yedek, KVKK teknik önlemleri), Basın ve web (test sunucusunda).
- **Çıktı verir:** DYK (risk matrisi yönetim sürümü, kritik riskler, uyum durumu), M45/M46 (risk karşılığı ve senaryo
  girdisi), Uyarılar (gösterge eşikleri).

## 8. Kısıtlar

- Portal Logo'ya ve CRM'e yazmaz; risk kaydı, uyum, BCP, sigorta köprünün kendi tablolarında.
- **Müşteride web taraması kapalı**: itibar ve mevzuat izleme otomatik değil; dış kaynak yalnız kullanıcı yüklemesiyle.
- Hukuki hüküm üretilmez: «uyumsuz», «ceza» gibi sonuçlar sistemden çıkmaz (finansal denetimin ilkesi); gösterge yalnız
  inceleme adayıdır.
- KVKK envanteri kişisel verinin kendisini değil **kategorisini** tutar; ihlal kaydı ayrıntısı yalnız KVKK yetkilisine açık.
- Ekranda teknoloji adı yok; demo veri yok (boş kayıtla açılır, göstergeler gerçek veriden); satır tavanı yok.
- Risk puanı insan kararıdır; sistem puanı değiştirmez, yalnız «gözden geçir» der.

## 9. Kapsam önerisi

**İlk sürüm**
- Risk kaydı (kategori, sahip, olasılık × etki, eğilim, aksiyon, gözden geçirme) + ısı haritası.
- Gösterge kütüphanesi: portalda **bugün hesaplanabilen** 10-12 gösterge (aşağıda §13), eşik, sahip, 12 değer geçmişi.
- «Gözden geçir» kuyruğu ve bildirimler.
- Uyum takvimi (elle yüklenen yükümlülükler, kanıt dosyası).

**Sonraki sürüm**
- Kurul risk brifingi (Zeki AI taslak) → DYK.
- BCP ve sigorta kaydı; poliçe bitiş uyarısı.
- KVKK işleme envanteri ve başvuru/ihlal kaydı.
- Yeni risk önerisi (eşik aşımından ve denetim bulgusundan) ve plan taslakları.
- Mevzuat metni yükleme + özet.

**Yeniden kullanılacaklar**
- `backend/semantic_bridge/alerts.py` (eşik, kenar bildirimi, `ALERT_REMIND_HOURS`, `smtp_settings`).
- `financial_audit_snapshot.py` (hazır rapor okuma; KRI ağır sorgu çalıştırmaz), `management/` önbelleği (Baskı önerisi).
- M46 `GET /api/v1/budget/deviations`, M59 `GET /api/v1/dealers/summary` (kodlanınca), M6 `editorial_mod.summary`
  (sözleşme 60 gün sayacı), `seo_geo/crm.py` (hak durumu).
- M2 sürümlü kural tablosu deseni (gösterge tanımları için), `admin.audit`.

## 10. Uzmanlara sorulacak sorular

1. Risk ve uyumun sahibi kim olacak (unvan/kişi); risk kaydı bugün bir yerde tutuluyor mu?
2. Yönetim kuruluna risk raporu hangi sıklıkla ve hangi biçimde gidiyor?
3. KVKK için VERBİS kaydı ve işleme envanteri var mı, kim tutuyor; saklama süreleri tanımlı mı?
4. Sigorta poliçeleri ve iş sürekliliği planları nerede, kim yeniliyor?
5. Telif ve sözleşme uyumunda en çok korkulan senaryo hangisi (biten sözleşmeyle satış, yurtdışı hak aşımı, korsan)?

## 11. Başarı ölçütü

- Her riskin sahibi ve son 90 gün içinde gözden geçirilmiş olması: oran %100'e.
- Kırmızı göstergeden «gözden geçirildi»ye geçen ortalama süre (hedef ≤ 7 gün).
- Gecikmiş aksiyon sayısının çeyrekten çeyreğe düşmesi.
- Uyum yükümlülüklerinde kanıt yüklenme oranı ve son gün kaçırma sayısı (hedef 0).
- Kurul risk brifinginin hazırlanma süresi (bugünkü ölçülecek → 1 gün).

## 12. Uzman gözüyle en iyi sistem

Kendimi orta ölçekli bir şirkette 15 yıllık bir risk ve uyum yöneticisinin yerine koyuyorum.

**İyi yayınevleri ve iyi yazılımlar bu işi nasıl yapıyor.** İyi yönetilen yayın gruplarında risk kaydı kısa tutulur (20-30
risk), her riskin tek sahibi vardır, çeyrekte bir gözden geçirilir ve **göstergeyle** yaşar: risk yalnız toplantıda değil,
göstergesi eşiği aştığında gündeme gelir. Yayıncılığa özgü ana riskler: telif/hak ihlali ve hak süresinin kaçırılması,
dağıtıcı ve büyük platform yoğunlaşması, iade riski, kâğıt fiyatı ve kur, matbaa/depo kesintisi, yazar itibarı, kişisel
veri (okur, öğretmen, bayi). İyi yönetişim-risk-uyum yazılımlarının ortak yanları: ısı haritası + risk kartı + kontrol/kanıt
kütüphanesi + denetim izi; kötü yanları: form yükü (kimse doldurmaz), otomatik veri beslemesi zayıf, raporlar sahte kesinlik
taşır. TİMAŞ'ın avantajı: göstergelerin çoğu için veri zaten portalda hesaplanıyor.

**TİMAŞ için mükemmel sistem:** Kısa bir risk kaydı; her risk en az bir göstergeye bağlı; göstergeler portalın diğer
modüllerinden ve Logo/CRM'den kendiliğinden gelir; eşik aşınca sahibine düşer; sahip telefonda iki dokunuşla «gözden
geçirdim, puan aynı, aksiyon şu» der. Uyum takvimi kanıt dosyasıyla kapanır. Çeyrek sonunda kurul brifingi Zeki AI
tarafından taslak olarak hazır gelir, rakamların hepsi göstergelerden, metni koordinatör düzeltir.

**Bir iş günü (risk ve uyum koordinatörü):**
- 09:00 — Özet: iki gösterge kırmızı — «Logo veri gecikmesi 42 gün» ve «ilk 4 müşteri payı %…» (ölçülecek); bir aksiyon
  gecikmiş (depo yangın tatbikatı).
- 09:30 — Veri gecikmesi riski (sahibi BT): kartta göstergenin son 12 değeri; BT'ye «canlı Logo erişimi» aksiyonu, termin.
- 11:00 — Hukukla uyum: «süresi bitmiş ama satan kitap» göstergesi 0'dan 5'e çıkmış; listeyi hukuka ve telif birimine
  atıyor.
- 14:00 — KVKK: bayi başvuru formunda izin tarihi boş kayıtlar; envanterde saklama süresi notu.
- 16:00 — Sigorta: iki poliçe 60 gün içinde bitiyor; CFO'ya teminat gözden geçirme aksiyonu.
- 17:00 — Çeyrek sonu yaklaşıyor; brifing taslağını üretip ilk okumayı yapıyor.

**«Bunu görürsem hemen kullanırım»**
1. Göstergelerin kendiliğinden gelmesi — form doldurmadan riskin nabzını görmek.
2. Risk sahibinin telefondan iki dokunuşla gözden geçirmesi.
3. Çeyreklik kurul brifinginin hazır taslağı, rakamları göstergelerden.

**«Bunu yaparsanız kullanmam»**
1. 200 maddelik hazır risk listesiyle açılan boş form cehennemi.
2. Sistemin kendiliğinden risk puanı değiştirmesi ya da «uyumsuz» hükmü vermesi.
3. Gösterge rakamının kaynağını gösterememek — denetçi sorduğunda cevap veremem.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

Başlangıç gösterge kütüphanesi ve üretim yolu:

| Adım | Logo (tablo / görünüm / ölçü) | CRM (varlık / alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| KRI: Logo veri gecikmesi (gün) | `MAX(DATE_)` `LG_411_01_INVOICE` (CANCELLED 0) | — | Yok | Veri riski ölçülebilir; bugün 17.08.2026. |
| KRI: maliyetsiz satış payı | `STLINE` `OUTCOST = 0` payı (faturalı, TRCODE 7,8) | — | Yok | Kâr raporlarının güvenilirliği. |
| KRI: müşteri yoğunlaşması (ilk 4 / ilk 10 cari payı) | `INVOICE` net ciro × `CLIENTREF` (sertifikalı `net_ciro`) | — | Yok | Tek müşteriye bağımlılık. |
| KRI: vadesi geçmiş alacak (90+) | `CLFLINE` + `PAYTRANS`, ölçü `vadesi_gecmis_alacak_fifo` (yaklaşık) | — | Yok | Kredi riski. |
| KRI: karşılıksız çek olayı | `LG_411_01_CSTRANS` STATUS 11 | — | Yok | Tahsilat riski. |
| KRI: döviz faturası / döviz yükümlülüğü | `INVOICE` `TRCURR ≠ 0`; M6 döviz sözleşmeleri | `new_sozlesmeBase.new_sozlesmeparabirimi` | Yok | Kur riski. |
| KRI: tedarikçi yoğunlaşması | `INVOICE` TRCODE 1,4 × `CLIENTREF` | — | Yok | Matbaa/kâğıt bağımlılığı. |
| KRI: süresi bitmiş ama satan kitap | `V_SatisRaporu_<yıl>` son 30 gün satış | `new_sozlesmeBase` (bitiş, süresiz, statecode, tip 5), `new_new_sozlesme_new_kitapBase` | Yok | Telif ihlali riski. |
| KRI: 60 gün içinde biten sözleşme | — | M6 özet (`contracts summary`) | Yok | Hak kaybı. |
| KRI: stokta riskli çok satan | Baskı önerisi önbelleği (öneri «Risk/Acil») | CRM stok | Yok | Satış kaybı. |
| KRI: finansal denetim açık inceleme adayı | `/api/v1/financial-audit/overview` (hazır rapor) | — | Yok | Kayıt riski. |
| KRI: bütçe sapması | M46 `/api/v1/budget/deviations` | — | Yok | Planlama riski. |
| KRI: KVKK izin eksikliği | — | `AccountBase.new_bayibasvurusukvkkizni`, `…kvkkizintarihi` | Yok | Uyum riski. |
| Yeni risk önerisi | Eşiği aşan göstergenin değeri | — | Risk kaydı taslağı (başlık, neden/sonuç, önerilen sahip) — sayılar girdiden | İnsan kabul eder. |
| Risk kategorisi | — | — | Kapalı küme sınıf (operasyonel / finansal / yasal / itibar / BT) — tek token + olasılık | Tutarlı sınıflama. |
| Plan, BCP, uyum listesi taslağı | — | — | Şablondan taslak metin | Yazma yükü; hukuk onaylar. |
| Mevzuat metni özeti | — | — | Yüklenen belgenin özeti ve etkilenen yükümlülük önerisi | Müşteride web kapalı; belge insan getirir. |
| Kurul risk brifingi | Bütün gösterge değerleri (JSON) | — | 1-2 sayfa taslak; her sayı girdide olmalı (sonradan denetim) | DYK paketi. |

Model çağrıları `rt.llm_for("risk")`; brifing ve mevzuat özeti `BATCH`. Ekranda yalnız «Zeki AI».

## 14. Kodlama planı (kodlayıcıya devir)

**Köprü dosyaları**
- `backend/semantic_bridge/risk.py` — risk kaydı, gösterge tanımı ve değeri, eşik, kuyruk, aksiyon, uyum, BCP, sigorta, brifing.
- `backend/semantic_bridge/risk_sources.py` — gösterge hesapçıları: her gösterge = `(kod, fonksiyon)`; kaynak ya doğrudan SQL
  (Logo/CRM, `budget_sources.runner` deseni) ya da köprü içi modül fonksiyonu (finansal denetim hazır raporu, M46
  `deviations`, M6 özet, Baskı önerisi önbelleği). Ağır Logo sorgusu yok; hazır raporlar okunur.
- `backend/semantic_bridge/risk_api.py` — `register(app, rt, require_caller, can)`.

**Tablolar**
- `semantic_risk_register` (id, tenant_id, baslik, tanim, kategori, alt_kategori, sahip, olasilik 1-5, etki 1-5, puan,
  egilim, durum acik|izleniyor|kabul|kapandi, kaynak elle|gosterge|denetim, son_gozden_gecirme, sonraki_gozden_gecirme,
  olusturan, tarihler, surum)
- `semantic_risk_indicators` (kod PK, tenant_id, ad, aciklama, kaynak_turu sql|modul, kaynak_ref, birim, yon artis_kotu|azalis_kotu,
  esik_sari, esik_kirmizi, sahip, siklik gunluk|haftalik|aylik, surum, durum taslak|yururlukte, onaylayan)
- `semantic_risk_indicator_values` (kod, olcum_at, deger, durum yesil|sari|kirmizi|olculemedi, veri_son_gunu, kanit_json)
- `semantic_risk_links` (risk_id, gosterge_kod)
- `semantic_risk_actions` (id, risk_id, eylem, sahip, termin, durum, kanit_ref, tamamlayan, tarih)
- `semantic_risk_reviews` (id, risk_id, tarih, eski_puan, yeni_puan, egilim, not, gozden_geciren)
- `semantic_compliance_items` (id, alan telif|kvkk|vergi|ticaret|is_sagligi|diger, madde, dayanak, siklik, sorumlu, aktif)
  ve `semantic_compliance_events` (item_id, donem, son_gun, durum, kanit_dosya, kapatan, tarih)
- `semantic_risk_policies` (id, tur, sigortaci, police_no_maskeli, teminat_json, prim, bas, bit, belge, not)
- `semantic_risk_bcp` (id, surec, kritiklik, kabul_kesinti_saat, veri_kaybi_saat, sorumlu, son_tatbikat, belge_surum, durum)
- `semantic_risk_reports` (id, donem, metin, girdi_hash, durum taslak|onayli, llm_job_id, onaylayan)
- Belgeler: `RISK_DIR` (`/data/nanobaseai/bi/var/risk`, kalıcı `bi_var` volümü; M8 dosya deseni).

**Uçlar** (`/api/v1/risk/*`)
- `GET summary` (ısı haritası, kuyruk, gecikmiş aksiyon, bu ayın uyumu)
- `GET/POST risks` · `GET/PATCH risks/{id}` · `POST risks/{id}/review` · `GET/POST/PATCH risks/{id}/actions`
- `GET indicators` · `POST indicators` (taslak) · `POST indicators/{kod}/approve` · `GET indicators/{kod}/values` ·
  `POST indicators/{kod}/measure` (şimdi ölç)
- `POST risks/suggest` (eşik aşımından taslak; model, 202) · `POST risks/classify` (model)
- `GET/POST/PATCH compliance/items` · `GET compliance/calendar?ay` · `POST compliance/events/{id}/evidence` (dosya) ·
  `POST compliance/events/{id}/close`
- `GET/POST/PATCH policies` · `GET/POST/PATCH bcp`
- `POST reports/draft` (model, 202) · `PATCH reports/{id}` · `POST reports/{id}/approve` · `GET reports/{id}/document.docx`
- `POST run-due` (SYSTEM) · `GET status`

**Ekranlar** `src/canvas/risk/`: `RiskScreen.tsx` (sekmeler Özet · Risk kaydı · Göstergeler · Uyum · BCP ve sigorta ·
Raporlar), `HeatMap.tsx` (5×5, dokunmatik, renk + sayı; renk körlüğü için hücrede puan yazılı), `RiskCard.tsx`,
`IndicatorCard.tsx`, `ComplianceCalendar.tsx`, `api.ts`. Rota `/timas/risk-uyum`. Menü: `navModel.ts` «Finans» alanına
«Risk ve uyum». Kampüs: `ModulesMenu.tsx` `LIVE.M47 = '/risk-uyum'`.

**Yetki**
- `sayfa:risk-uyum` → `/api/v1/risk/`; `run-due` SYSTEM.
- `ozellik:risk.yaz` (risk ve aksiyon), `ozellik:risk.gosterge` (**açıkça**; tanım ve eşik), `ozellik:risk.gosterge-onay`
  (**açıkça**; hazırlayan onaylayamaz), `ozellik:risk.rapor-onay` (**açıkça**), `ozellik:uyum.yaz`, `ozellik:uyum.kvkk`
  (**açıkça**; KVKK envanteri ve ihlal kaydı), `ozellik:risk.sigorta-bcp`.
- Risk sahibi yalnız kendi riskinin aksiyonunu değiştirir (sahiplik kontrolü uçta; `yazar-giris.herkesinki` deseni:
  `ozellik:risk.herkesinki` açıkça).

**Zamanlayıcı** `scripts/server/timas-risk.{timer,service}`: günde bir 06:15 `POST /api/v1/risk/run-due` → sıklığı gelen
göstergeleri ölçer (hazır raporları okuyarak), eşik değişiminde kuyruk + e-posta (yalnız kenarda; `alerts` deseni), aksiyon
ve uyum son günü hatırlatması, poliçe bitişi. İlk koşu elle.

**Kabul testleri** (gerçek DB; her gösterge değeri bağımsız sorguyla)
1. Veri gecikmesi: `SELECT MAX(DATE_) FROM LG_411_01_INVOICE WHERE CANCELLED = 0` → 2026-08-17; gösterge = bugün − bu tarih.
2. Müşteri yoğunlaşması: `WITH N AS (SELECT CLIENTREF, SUM(CASE WHEN TRCODE IN (7,8,9) THEN NETTOTAL ELSE -NETTOTAL END) AS
   n FROM LG_411_01_INVOICE WHERE CANCELLED = 0 AND TRCODE IN (2,3,7,8,9) AND DATE_ >= '2026-01-01' GROUP BY CLIENTREF)
   SELECT (SELECT SUM(n) FROM (SELECT TOP 4 n FROM N ORDER BY n DESC) t) / SUM(n) FROM N` = gösterge; payda 848.110.178,82 ₺.
3. Karşılıksız çek: `SELECT COUNT(DISTINCT CSREF), SUM(…) FROM LG_411_01_CSTRANS WHERE STATUS = 11 AND DATE_ >= '2026-01-01'`
   → 6 çek, 6.326.658 ₺ (kolon adları kabulde `CSTRANS` modeliyle doğrulanır).
4. Döviz faturası: `SELECT COUNT(*) FROM LG_411_01_INVOICE WHERE CANCELLED = 0 AND TRCURR <> 0` → bilgi paketindeki 74 ile
   aynı ya da farkı açıklanmış.
5. Süresi bitmiş ama satan kitap: CRM'de `statecode = 0 AND new_SozlesmeTipi = 5 AND ISNULL(new_suresizsozlesme,0) = 0 AND
   new_SozlesmeBitisTarihi < :bugun` sözleşmelerin stok kodları ∩ `V_SatisRaporu_2026` son 30 günde `Miktar > 0` → sayı ve
   liste göstergeyle aynı (kitabın başka yürürlükte sözleşmesi varsa listeden çıkar — kural testte ayrıca sınanır).
6. Maliyetsiz satış payı: M45 kabul 4 ile aynı sorgu, aynı değer (iki modül aynı rakamı söyler).
7. Finansal denetim: hazır rapordaki inceleme adayı sayısı = gösterge (Logo'ya yeni sorgu gitmediği `run_sql` kaydıyla doğrulanır).
8. Eşik kenarı: yapay değer dizisiyle (DB'siz birim testi) yeşil→kırmızı geçişinde tek bildirim, kırmızıda kalırken
   `ALERT_REMIND_HOURS` dolmadan ikinci bildirim yok.

**Bağımlılık:** Bağımsız başlayabilir (risk kaydı, uyum, göstergelerin Logo/CRM'den doğrudan olanları). M45 (likidite) ve
M59 (bayi) göstergeleri o modüller gelince bağlanır; uç şekli önceden anlaşılırsa paralel. DYK bu modülün `summary` ve
`reports` uçlarını okur.

**Tahmini büyüklük:** L (risk kaydı + ısı haritası M; gösterge motoru M; uyum/BCP/sigorta M; brifing S).
