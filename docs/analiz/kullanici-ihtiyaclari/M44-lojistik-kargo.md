# M44 — Lojistik ve Kargo Yönetimi: kullanıcı ihtiyaç analizi

Durum: analiz (kod yok) · Tarih: 2026-09-28 · Kaynaklar: `specs/M44.txt`, `specs/M29.txt`, `specs/M40.txt`, `specs/M42.txt`,
`ZEKİ_Veri_Haritasi2.html` (M44 satırları), `configs/semantic/knowledge/logo/knowledge/rules/{logo-erp.md, crm-timas.md}`
(Kural 10, 18, 19, C13, C19), `configs/semantic/knowledge/crm/{OKUNUR-TABLOLAR.md, table_descriptions.json}`
(`new_siparis`, `new_sevkiyat`, `new_kargobilgisi`, `new_kargotakipbilgisi`, `new_kargofirmasi`, `new_sipariskutusu`,
`new_kutustogu`), `docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`, `docs/analiz/crm-eticaret-entegrasyon-2026-09-27.md`,
`backend/semantic_bridge/access_catalog.json`, `src/canvas/modules.json`, bellek: `system-of-record-logo`, `logo-155-frozen-copy`,
`no-tech-names-on-screens`, `tsoft-no-write`, `no-silent-limits-rule`. Sunucuya bağlanılmadı; yeni ölçüm yok.

## 1. Modül ne işe yarar

İş tanımı (M44): sipariş → kargo etiketi otomasyonu, kurye seçimi (maliyet × hız), takip numarası bildirimi, teslimat anomalisi
uyarısı (K1); kurye performans karşılaştırması, bölge bazlı teslim süresi, toplu/bireysel gönderim maliyeti, kargo şikâyet ve iade
oranı (K3 — kurye değiştirme kararı insanda).

TİMAŞ'ın bugünkü durumu (kanıtla): kargo operasyonu **CRM'in içinde** yürüyor. Siparişte kargo firması (`new_kargofirmasiid`),
takip no ve URL, etiket basıldı bayrağı, ödeme şekli, koli adedi ve dört kargo firmasının entegrasyon sonucu/mesajı alanları
(Aras, UPS, MNG, Akademi) var; 11 kargo firması kaydı; ayrı "Kargo Bilgisi" tablosu (13.242 kayıt: çıkış/varış şubesi, desi, ağırlık,
tutar, teslim alan, teslim tarihi, iade durumu, satış kanalı) ve "Kargo Takip Bilgisi" (10.688). Yani etiket ve takip no üretimi
büyük olasılıkla zaten otomatik (varsayım: entegrasyon sonuç alanları bunu gösteriyor). Eksik olan: **maliyet ve performans
görünürlüğü**; kargo bilgisi alanlarının hepsi metin (ondalık virgüllü), bu da bir dışa aktarımın elle/topluca içeri alındığını
düşündürüyor (varsayım).

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| Sevkiyat / lojistik sorumlusu | CRM departman "Depo" (kod 7); sipariş aşamaları Depoda Bekliyor → Kutulandı → Sevk Edildi | Her gün | Masaüstü (depo ofisi) + telefon |
| Depo müdürü (kargo firması sözleşmesi, maliyet) | Depo | Haftalık / aylık | Masaüstü |
| Müşteri hizmetleri (nerede kaldı, hasarlı, iade) | Birim kanıtı yok (varsayım; M51 ile ortak); CRM destek talep konusu B2B/B2C/Depo var | Gün içinde soru bazında | Masaüstü |
| Satış temsilcisi / bölge (bayi teslimi) | Satış 49 kişi; SystemUser `new_KullancTipi` BMT | Soru bazında | Telefon |
| Finans (kargo faturası mutabakatı) | Mali İşler 10 | Ay sonu | Masaüstü |
| Yönetim (kurye değişimi kararı, K3) | — | Çeyreklik | Masaüstü |

## 3. Bugün bu iş nasıl yapılıyor

- **Sevkiyat sorumlusu:** CRM siparişi pusula → toplama → kutulama → sevk; kargo firması siparişte seçiliyor (kimin, hangi kurala
  göre seçtiği bilinmiyor — varsayım: müşteri/kanal varsayılanı). Entegrasyon sonucu alanları hata mesajını tutuyor; hata olunca
  elle yeniden deneme (varsayım). Sevk edilen sipariş için CRM'de `new_sevkiyat` açılıyor, Logo'ya `new_logoyaaktarildi` ile
  irsaliye/fatura olarak geçiyor (`new_faturanumarasi` → Logo `INVOICE.FICHENO`, 174.913 / 240.920 eşleşme, 2026-09-09).
- **Müşteri hizmetleri:** takip no CRM siparişinde; müşteriye bildirim `new_sevkiyatmailigonderildi` (Evet/Hayır) ile e-postayla
  (kanıt: alan adı; gönderimin hangi akışla yapıldığı ölçülmedi). timas.com.tr (T-soft) siparişleri CRM'e gelmiyor → D2C kargo
  takibi T-soft panelinde (varsayım).
- **Depo müdürü / finans:** kargo maliyeti `new_kargobilgisi.new_Tutar` (metin) ve Logo'daki kargo firması alış/hizmet faturası
  (TRCODE 4) — ikisinin karşılaştırıldığına dair iz yok. Kural C19 "sevk adedi başına maliyet, çıkış şubesine göre" tanımlı ama
  canlı sonucu kayıtlı değil.
- **Tıkanma (varsayım):** teslim tarihi ve iade durumu kargo firmasının raporundan geliyorsa gecikmeli; hangi siparişin geciktiği
  gün içinde görülemiyor; termin tarihi TİMAŞ'ta **hiçbir sistemde tutulmuyor** (iş kararı 2026-09-20) → "geç teslim" ancak
  sipariş → sevk → teslim süreleriyle ölçülebilir.

## 4. İhtiyaçlar ve acı noktaları

**Sevkiyat sorumlusu**
1. Günün sevk listesi ve entegrasyon hatası alan siparişler (hangi firma, hangi mesaj), yeniden deneme listesi.
2. Kutulandı ama sevk edilmemiş / sevk edildi ama takip no'su olmayan siparişler.
3. Teslim edilmemiş ve X günü geçmiş gönderiler (anomali).

**Depo müdürü**
1. Kargo firması bazında: gönderi, desi, maliyet, desi başı maliyet, ortalama teslim süresi, iade/hasar oranı.
2. Şehir/bölge bazında teslim süresi ve maliyet; hangi bölgede hangi firma daha iyi.
3. Aynı müşteriye aynı gün birden çok koli → birleştirme fırsatı ve kaçan tutar.

**Müşteri hizmetleri**
1. Sipariş/fatura/takip no ile tek arama → durum, firma, teslim bilgisi.
2. Gecikme/özür mesajı taslağı (gönderim insan onayıyla, kendi e-postasından).

**Finans**
1. Kargo firması faturası (Logo) ↔ CRM kargo kaydı toplamı mutabakatı, ay bazında.
2. Tahsilatlı kargo (`new_tahsilatlikargo`) tutarlarının izlenmesi.

## 5. Nasıl kullanmak isteyecekler

**Kullanıcı hikâyeleri**
- Sevkiyat sorumlusu olarak sabah entegrasyon hatası alan siparişleri görmek istiyorum, çünkü etiketi basılamayan koli rafta bekler.
- Sevkiyat sorumlusu olarak 5 günden uzun süredir teslim edilmemiş gönderileri firma bazında görmek istiyorum, çünkü firmayı arayıp takip ederim.
- Depo müdürü olarak üç kargo firmasını desi başı maliyet ve teslim süresiyle kıyaslamak istiyorum, çünkü yıllık sözleşme pazarlığına girerim.
- Depo müdürü olarak şehir bazında en hızlı firmayı görmek istiyorum, çünkü bölgeye göre firma kuralı koyarım.
- Müşteri hizmetleri uzmanı olarak sipariş numarasıyla kargonun nerede olduğunu tek aramada görmek istiyorum, çünkü müşteriyi bekletmem.
- Finans uzmanı olarak ay sonunda kargo faturasını CRM gönderi toplamıyla karşılaştırmak istiyorum, çünkü fazla faturayı itiraz ederim.

**Ana ekranlar ve akış**
- Açılış (`/kargo`): bugün sevk edilecek / edilen, entegrasyon hatası, takip no'suz sevk, teslim bekleyen (yaşa göre renk), son 30 gün
  desi başı maliyet. Her kutu listeye iner.
- Gönderi arama: sipariş no, fatura no, takip no, müşteri → gönderi kartı (aşama zaman çizelgesi: sipariş → depoda bekliyor → pusula →
  kutulandı → sevk → teslim).
- Firma karşılaştırma: firma × (gönderi, desi, maliyet, desi başı, ortanca teslim günü, iade oranı), şehir süzgeci.
- En sık 3 işlem: hata listesini açıp Excel'e al (2 tık), gönderi ara (2 tık), firma karşılaştırmasını ay seçip indir (3 tık).

**Zeki AI'ya soracakları örnek sorular**
- "Geçen ay Aras ile MNG'nin desi başı maliyeti ne?"
- "Doğu Anadolu'ya gönderilerde ortalama teslim kaç gün, firma bazında?"
- "Kutulanıp 2 günden fazla sevk edilmemiş sipariş var mı?"
- "En çok iade dönen 10 bayi ve kargo firması?"
- "Tahsilatlı kargoda bekleyen tutar ne kadar?"
- "Aynı gün aynı müşteriye birden fazla koli gönderdiğimiz kaç sipariş var, birleştirseydik ne kazanırdık?"

**Otomasyon katmanı**
- K1 (tam otomatik, salt okuma): aşama süreleri, hata listesi, anomali uyarısı, firma/bölge performans hesabı.
- Etiket ve takip no üretimi bugün CRM'in kendi entegrasyonunda (varsayım); bu modül etiket basmaz, kargo firmasına yazmaz.
- K2 (Zeki önerir, insan onaylar): gecikme/özür ve iade yönlendirme mesajı taslağı; birleştirme fırsatı.
- K3 (Zeki analiz, insan karar): kurye firması değişimi, bölge kuralı; öneri gerekçesiyle, karar kaydı portalda.
- K4: sözleşme pazarlığı, hasar tazmini.
- İş tanımındaki "kurye seçimi otomasyonu" ve "müşteriye takip bildirimi" CRM'de kurulu akışı değiştirmeyi gerektirir → açık soru.

**Bildirim / uyarı**
- Sevkiyat sorumlusu: entegrasyon hatası ve takip no'suz sevk (gün içinde, 15 dk'lık uyarı kontrolü; portal zili + e-posta).
- Depo müdürü: teslim bekleyen > N gün (N kullanıcı belirler), haftalık firma karnesi (planlı rapor, pazartesi 08:00).
- Finans: aylık mutabakat özeti (ayın 3'ü).

**Onay ve yetki (öneri)**
- `sayfa:kargo` — depo, müşteri hizmetleri, satış, finans.
- `ozellik:kargo.maliyet` (tutar ve desi başı maliyet) — açıkça verilir (depo müdürü, finans, yönetim).
- `ozellik:kargo.alici` (alıcı adı/adresi görme, KVKK) — açıkça verilir (sevkiyat, müşteri hizmetleri).
- `ozellik:kargo.karar` (kurye/bölge kararı kaydı) — açıkça verilir (depo müdürü, yönetim).

## 6. Veri

| Gereken veri | Kaynak (Logo / CRM / T-soft / kullanıcı girer / dış) | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Sipariş aşama tarihleri | CRM `new_siparisBase` (`new_siparistarihi`, `new_DepodaBekliyorDurumu`, `new_pusulaalinditarih`, `new_sipariskutulanditarihi`, `new_sevktarihi`, `new_tamamlanditarihi`, `statuscode`) | Kolonlar biliniyor | Doluluk oranı **ölçülecek** |
| Kargo firması, takip no, etiket, entegrasyon sonucu | CRM `new_siparisBase` (`new_kargofirmasiid`, `new_kargotakipno`, `new_kargotakipurl`, `new_etiketbasildi`, `new_{aras,ups,mng,akademi}kargoentegrasyon{sonucu,mesaji}`, `new_kutuadedi`, `new_kargoodemesekli`) | Kolonlar biliniyor | Hata oranı ve firma dağılımı **ölçülecek** |
| Gönderi maliyeti, desi, teslim | CRM `new_kargobilgisiBase` (13.242; metin alanlar, virgüllü ondalık — Kural C19) | Tanım var | Güncel mi (son kayıt tarihi), siparişe nasıl bağlandığı (`new_musteriirsno`/`new_KargoTakipNo` ↔ sipariş) **ölçülecek** |
| Takip bilgisi | CRM `new_kargotakipbilgisiBase` (10.688; irsaliye/fatura no, takip no, sipariş) | Tablo biliniyor | Kapsam **ölçülecek** |
| Kargo firmaları | CRM `new_kargofirmasiBase` (11) — yalnız `new_name`, `new_kargokodu` | Tablo biliniyor | **Kimlik alanları (`new_kullaniciadi`, `new_sifre`, `new_token`, `new_clientid`, `new_clientsecret`, UPS hesap no) asla seçilmez**; BT'ye güvenlik notu |
| Sevk (Logo gerçekleşen) | Logo `STLINE` TRCODE 7,8, IOCODE 4 (Kural 10); irsaliye `STFICHE` | Kural var | Yok |
| Kargo faturası (gerçek maliyet) | Logo alınan hizmet faturası (TRCODE 4) kargo firması carileri; muhasebe `EMFLINE` gider hesabı | Satınalma ölçüsü (`satinalma`) var | Kargo carileri ve gider hesap kodu **ölçülecek** |
| Adres / şehir | CRM `new_adresBase` (66.984), siparişte `new_teslimatadresiid`; Logo `CLCARD.CITY` | Tablolar biliniyor | Şehir doluluğu **ölçülecek** |
| Kargo şikâyeti | CRM talep yönetimi (BT içi, uygun değil); M51 müşteri hizmetleri kaydı | Müşteri şikâyet kaydı **bulunamadı** | M51'e bağlı; yoksa iade durumu + not |
| Pazar yeri / D2C gönderileri | Trendyol/Hepsiburada/T-soft panelleri | CRM'e gelmiyor (T-soft sonrası) | M40/M42 bağlantısına bağlı |
| Kargo firması API'si (canlı durum) | Firma API'leri | Kimlik bilgisi CRM'de ama okunmayacak | Ayrı salt okunur hesap gerekir (Soru 2) |

## 7. Diğer modüllerle bağ

- Girdi: M43 depo hattı (kutulama/sevk aşamaları), M40/M41/M42 kanal siparişleri, M29 ilk dağılım gönderileri, M30 saha satış
  (bayi teslim şikâyeti), M51 müşteri hizmetleri (şikâyet kaydı).
- Çıktı: M43 (sevk süreleri), M45/M46 finans (kargo gideri, bütçe), M59 bayi performansı (iade ve teslim), M29 (teslim anomalisi →
  dağılım takip), M51 (takip durumu).

## 8. Kısıtlar

- CRM ve Logo yalnız okunur; kargo firması sistemlerine yazma yok (etiket/iptal/yönlendirme yok).
- Müşteriye otomatik mesaj göndermek bu sürümde yok: taslak üretilir, gönderimi insan yapar (mesaj gönderimi kullanıcı onayı ister).
- KVKK: alıcı adı, teslim alan, adres, telefon kişisel veri → varsayılan ekranda maskeli; `ozellik:kargo.alici` ile açılır;
  dışa aktarımda da aynı kural. Model istemine kişisel veri gönderilmez.
- Kargo firması kimlik bilgileri (CRM `new_kargofirmasi` kullanıcı adı/şifre/token/secret) hiçbir sorguda seçilmez.
- Ekranda teknoloji adı yok; demo veri yok; sayı tavanı yok (listeler sayfalı).
- Termin tarihi tutulmuyor: "geç teslim" yerine "sipariş → teslim süresi" ve "teslim bekleyen yaş" kullanılır; 0 satır "gecikme
  yok" diye sunulmaz.

## 9. Kapsam önerisi

**İlk sürüm**
- Gönderi arama ve gönderi kartı (CRM sipariş + sevkiyat + kargo bilgisi + takip bilgisi).
- Günlük hat: entegrasyon hatası, takip no'suz sevk, kutulandı-sevk edilmedi, teslim bekleyen yaşı.
- Firma karnesi: gönderi, desi, maliyet, desi başı, ortanca teslim, iade oranı (kargo bilgisi tablosu güncelse).
- Uyarı kuralları + haftalık firma karnesi e-postası.

**Sonraki sürüm**
- Logo kargo faturası ↔ CRM gönderi mutabakatı.
- Şehir/bölge haritası, birleştirme fırsatı hesabı, kurye kural önerisi (K3) ve karar kaydı.
- Gecikme/özür/iade mesaj taslakları; M51 şikâyet kaydıyla kök neden sınıflaması.
- Kargo firması API'sinden salt okunur canlı durum (hesap verilirse).

**Mevcut kodda yeniden kullanılacaklar**
- `backend/semantic_bridge/alerts.py`, `reports.py`, `board.py`; M43 `stock_sources.py` (aynı CRM bağlantısı).
- main'deki `backend/semantic_bridge/budget_sources.py` (M46): `runner`, `firms_by_year`, `read_data_end` (Logo firma/yıl ve veri günü).
- `backend/semantic_bridge/management/` 5 dk önbellek + ⓘ kaynak SQL paneli deseni.
- `src/canvas/components/SearchSelect.tsx`, dışa aktarma (`ozellik:veri.disa-aktar`).

## 10. Uzmanlara sorulacak sorular

1. Kargo firması bugün siparişte kim tarafından, hangi kurala göre seçiliyor (müşteri, kanal, desi, bölge)? Kural yazılı mı?
2. `new_kargobilgisi` tablosu nasıl doluyor (firma raporu mu, elle mi) ve ne sıklıkla? Kargo firmalarından salt okunur API/rapor hesabı alınabilir mi?
3. Kargo faturası Logo'da hangi cari ve hangi gider hesabıyla işleniyor? Desi/tutar anlaşmaları (fiyat listeleri) nerede?
4. "Geç teslim" sizin için kaç gün (bölgeye göre)? Termin tutulmadığına göre hedef süre nedir?
5. timas.com.tr ve pazar yeri siparişlerinin kargosu da aynı depodan ve aynı firmalarla mı çıkıyor, yoksa platform anlaşmalı kargo mu?

## 11. Başarı ölçütü

- Entegrasyon hatası alan siparişin çözülme süresi (hata → sevk) ilk 2 ayda kısalıyor.
- Teslim bekleyen > N gün gönderi sayısı azalıyor; ortanca sipariş → teslim süresi (gün) aylık izleniyor.
- Desi başı kargo maliyeti yıllık sözleşme sonrası düşüyor (firma karnesiyle ölçülür).
- Müşteri hizmetlerinde "kargom nerede" cevabı < 30 sn.
- Aylık mutabakat farkı (Logo fatura − CRM gönderi tutarı) izleniyor ve gerekçelendiriliyor.

## 12. Uzman gözüyle en iyi sistem

Rol: 15 yıllık e-ticaret/yayın lojistiği müdürü. Sektör pratiği (genel bilgi, TİMAŞ verisiyle doğrulanmadı): iyi işleyen yayınevi ve
e-ticaret depoları çok firmalı kargo kullanır; kurye seçimini sipariş anında desi × bölge × vaat edilen süreye göre kuralla yapar;
firma karnesini (zamanında teslim, hasar, iade, desi başı maliyet) haftalık izler; "teslim edilmeyen" gönderiyi yaşına göre
proaktif takip eder; kargo faturasını gönderi bazında otomatik mutabakata sokar (fazla desi ve mükerrer faturayı yakalar).
Türkiye'de çok firmalı kargo entegratörleri bu işi tek panelden yapar. TİMAŞ'ta firma entegrasyonları CRM'de kurulu; eksik olan
ölçüm ve karşılaştırma.

Mükemmel sistem: her gönderinin sipariş → teslim zaman çizelgesi tek kartta; hata ve bekleyenler sabah listesinde; firma karnesi
şehir kırılımıyla; Logo faturası gönderi bazında eşleşmiş; kurye değişikliği öncesi "bu kural geçen çeyrekte uygulansaydı maliyet/süre
ne olurdu" simülasyonu.

Bir iş günü (saatler ve sayılar örnek biçimdir, ölçüm değildir):
- 08:00 Telefonda: "Dün 1.240 sipariş sevk, 9 entegrasyon hatası (7 Aras adres hatası), 31 gönderi 5 günü geçti."
- 08:30 Hata listesi: adres hatalı 7 siparişi müşteri hizmetlerine yönlendirir (liste Excel).
- 10:00 Teslim bekleyenler: 5+ gün olan 31 gönderiyi firma bazında ayırır, iki firmayı arar.
- 13:00 Müşteri hizmetlerinden soru: sipariş no ile kart → "Kutulandı 24.09, sevk 25.09, MNG, teslim yok"; Zeki AI özür mesajı taslağı.
- 15:00 Firma karnesi: Doğu bölgesinde X firmasının ortanca teslimi 2 gün daha uzun; K3 notu yazar.
- 17:00 Haftalık rapor taslağını yönetime iletir.

"Bunu görürsem hemen kullanırım":
1. Firma × şehir teslim süresi ve desi başı maliyet tablosu (sözleşme pazarlığı için).
2. Etiketi basılamayan / takip no'suz sevk listesi (sabah).
3. Gönderi kartında aşama zaman çizelgesi.

"Bunu yaparsanız kullanmam":
1. Kargo firmasına benim onayım olmadan otomatik iptal/yeniden gönderim yapmak.
2. Müşteri adres ve telefonunu herkese açık göstermek.
3. Termin olmadan "geç teslim %X" diye uydurma oran vermek.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (hangi tablo/görünüm/ölçü) | CRM (hangi varlık/alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Sipariş aşama süreleri | — | `new_siparisBase` tarih kolonları, `statuscode` | — | Operasyon CRM'de |
| Sevk gerçekleşti mi | `LG_411_01_STLINE` TRCODE 7,8 IOCODE 4, `STFICHE`, `INVOICE.FICHENO` | `new_sevkiyatBase.new_faturanumarasi`, `new_logoyaaktarildi` | — | Gerçekleşen sevk Logo'dadır |
| Entegrasyon hatası | — | `new_*kargoentegrasyon{sonucu,mesaji}`, `new_etiketbasildi` | Hata mesajını kapalı kümeye sınıflar (adres, telefon, desi/ağırlık, kimlik doğrulama, servis kapalı, diğer) — tek token + olasılık; düşük marj "belirsiz" | Farklı firmaların serbest metinlerini tek dile indirir |
| Firma karnesi | — | `new_kargobilgisiBase` (`new_Tutar`, `new_desi`, `new_sevkadeti`, `new_TeslimTarihi`, `new_kargoirstarihi`, `new_iadedurumu`, `new_alicisehir`, `new_kargofirmasi`) | — | Rakam SQL'den (`TRY_CAST(REPLACE(x, ',', '.') AS FLOAT)`) |
| Kargo faturası mutabakatı | TRCODE 4 alınan hizmet faturası (kargo carileri), `EMFLINE` gider hesabı | `new_kargobilgisi` toplamı | Fark gerekçesi özeti (mükerrer, fazla desi, kayıtsız gönderi) — rakamlar verilir | Finansın okuyacağı açıklama |
| Gecikme/özür/iade mesajı | — | Sipariş no, firma, aşama tarihi (kişisel veri modele gitmez) | Taslak metin | Müşteri hizmetleri hızlanır; gönderim insanda |
| Kurye kararı | — | Karne sonuçları | Karar gerekçesi özeti (K3) | Yönetim sunumu |
| Doğal dil soru | Katalog | Katalog (Kural C19 dahil) | Mevcut soru hattı | Yeni hat kurulmaz |

Model çağrısı `rt.llm_for("kargo")`; zamanlanmış sınıflama `QueuedLlm(..., purpose="bg:kargo")`. Ekranda yalnız "Zeki AI".

## 14. Kodlama planı (kodlayıcıya devir)

**Köprü dosyaları**
- `backend/semantic_bridge/shipping.py` — aşama süreleri, anomali, firma karnesi, mutabakat hesabı; 5 dk önbellek.
- `backend/semantic_bridge/shipping_sources.py` — CRM/Logo salt okunur SQL; dosyalar `backend/semantic_bridge/shipping_sql/`:
  `crm_siparis_asama.sql`, `crm_entegrasyon_hata.sql`, `crm_takipsiz_sevk.sql`, `crm_kargo_bilgisi.sql`, `crm_kargo_takip.sql`,
  `crm_kargo_firma.sql` (yalnız `new_kargofirmasiId, new_name, new_kargokodu`), `logo_sevk.sql`, `logo_kargo_fatura.sql`.
- `backend/semantic_bridge/shipping_store.py`, `backend/semantic_bridge/shipping_api.py`.

**Tablolar**
- `semantic_shipping_classes` (tenant_id, siparis_id, firma, mesaj_hash, sinif, olasilik, model_tarihi) — hata sınıflaması önbelleği.
- `semantic_shipping_decisions` (id, tenant_id, tur 'kurye'|'bolge'|'sozlesme', kapsam_json, gerekce, model_ozet, karar, karar_veren, tarih).
- `semantic_shipping_drafts` (id, tenant_id, siparis_id, tur 'gecikme'|'ozur'|'iade', metin, yazan, durum 'taslak'|'kullanildi').
- `semantic_shipping_settings` (tenant_id, anahtar, deger) — "teslim bekleyen N gün", bölge hedef süreleri.

**Uçlar** (`/api/v1/shipping/*`): `GET meta`, `GET overview`, `GET shipments?q=&firma=&durum=&sayfa=`, `GET shipments/{siparis_id}`,
`GET errors`, `GET untracked`, `GET waiting?gun=`, `GET carriers?baslangic=&bitis=&sehir=`, `GET reconcile?ay=`,
`POST drafts`, `GET decisions`, `POST decisions`, `GET export/{liste}.xlsx`, `GET settings`, `PUT settings`.

**Ekranlar** `src/canvas/shipping/`: `ShippingHome.tsx` (/kargo), `Shipment.tsx` (/kargo/gonderi/:id), `Errors.tsx` (/kargo/hatalar),
`Waiting.tsx` (/kargo/bekleyen), `Carriers.tsx` (/kargo/firmalar), `Reconcile.tsx` (/kargo/mutabakat). Menü: çalışma alanı `lojistik`,
bölüm «Kargo». Kampüs: «Lojistik» modül kartına «Kargo» bağlantısı.

**Yetki**: `sayfa:kargo`, `sayfa:kargo-firmalar`, `sayfa:kargo-mutabakat`; `ozellik:kargo.maliyet` (explicit), `ozellik:kargo.alici`
(explicit), `ozellik:kargo.karar` (explicit), `ozellik:kargo.taslak`.

**Zamanlayıcı**: mevcut `timas-alerts.timer` (15 dk) uyarı kuralları için yeterli; `timas-shipping.timer` her gün 06:45 — hata
sınıflaması (yeni mesajlar), karne önbelleği; pazartesi 08:00 karne e-postası `timas-reports.timer` ile. İlk kurulumda elle koşturulur.

**Kabul testleri (gerçek veri)**
1. Son 30 gün sevk edilen sipariş sayısı ekran = `SELECT COUNT(*) FROM Timas_MSCRM.dbo.new_siparisBase WHERE statuscode IN (100000000, 100000015) AND new_sevktarihi >= DATEADD(DAY,-30,GETDATE())`.
2. Firma bazında desi başı maliyet ekran = `SELECT new_kargofirmasi, SUM(TRY_CAST(REPLACE(new_Tutar, ',', '.') AS FLOAT)) / NULLIF(SUM(TRY_CAST(REPLACE(new_desi, ',', '.') AS FLOAT)), 0) FROM new_kargobilgisiBase WHERE statecode = 0 AND new_kargoirstarihi >= @bas AND new_kargoirstarihi < @bit GROUP BY new_kargofirmasi` (tarih kolonunun tipi önce ölçülür).
3. Şube bazında sevk adedi başına maliyet = Kural C19 doğrudan SQL'i (boş şube "Belirtilmemiş").
4. Entegrasyon hatası sayısı = dört firma sonuç alanında hata içeren (değer kümesi önce ölçülür) ve `new_kargotakipno IS NULL` siparişler; ekranla birebir.
5. Takip no'suz sevk = `statuscode = 100000000 AND ISNULL(new_kargotakipno,'') = ''` sayısı.
6. Logo sevk adedi (Kural 10: STLINE TRCODE 7,8 IOCODE 4 LINETYPE 0 CANCELLED 0, ay bazında) ile CRM sevkiyat (`new_sevkiyatBase`, aynı ay, `new_logoyaaktarildi = 1`) eşleşme oranı raporlanır; fark ayrıca listelenir.
7. Hiçbir uç yanıtında ve dışa aktarımda `new_kargofirmasi` kimlik kolonları yok (otomatik test: SQL dosyalarında yasak kolon adı taraması).

**Bağımlılık**: M43'ün CRM bağlantısı ve sipariş aşama SQL'i ile ortak (M43 önce ya da birlikte). M51 şikâyet kaydı sonraki sürüm.
M40/M42 platform gönderileri sonraki sürüm. Paralel kodlanabilir.

**Tahmini büyüklük**: M (ilk sürüm 2 gün; mutabakat + taslaklar ikinci sürümde M).
