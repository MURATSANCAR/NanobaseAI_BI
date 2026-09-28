# M39 — Pazar Araştırması ve Rekabet Analizi: kullanıcı ihtiyaç analizi

Durum: kod var (main) — test sunucusunda kabul bekliyor (testler koordinatörde) · Analiz tarihi: 2026-09-28 · Kaynaklar: iş tanımı `specs/M39.txt` (ZEKİ_Moduller3.html'den),
`specs/DYK.txt` (M39 → kurul özeti), `specs/M15.txt` (M38/M39 analizine atıf), `specs/Kategori_Ağacı_Modülü.txt` (rakip
emsal), `specs/M9.txt` (emsal ve pazar fiyatı), `specs/ANALIZ-EK.md`; depoda `docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`,
`docs/analiz/seo-geo-modul-2026-09-25.md`, `docs/analiz/kitap-yazar-web-taramasi-2026-09-24.md` (başlık düzeyinde),
`PROJECT-MEMORY.md`, `AGENTS.md` («Basın ve web taraması»), `configs/semantic/knowledge/crm/table_descriptions.json`
(2026-09-09), `configs/semantic/knowledge/logo/knowledge/`, `backend/semantic_bridge/seo_geo/competitors.py`,
`seo_geo/seasons.py`, `backend/semantic_bridge/web_watch.py`; bellek: customer-vm-web-watch-off, web-watch-open-sources,
seo-geo-module, live-bi-numbers-2026, no-tech-names-on-screens, chat-persona-zeki-ai. `ZEKİ_Veri_Haritasi2.html` verilen
klasörde yok. Sunucuya bağlanılmadı; sayılar depodaki tarihli ölçümlerdir.

## 1. Modül ne işe yarar

İş tanımına göre modülün iki işi var, ikisi de K3 (Zeki analiz eder, yönetim karar verir). Pazar araştırması: Türkiye kitap
pazarının büyüklüğü ve büyümesi, kategori bazında pazar payı, okur demografisi ve davranış değişimi, uluslararası
yayıncılık eğilimleri. Rekabet analizi: rakip yayınevlerinin yayın takvimi ve lansman stratejisi, fiyat ve indirim
stratejisi, kanal ve dağıtım gücü, TİMAŞ'ın rekabet konum haritası. Çıktılar: pazar araştırma raporu, rakip karşılaştırma
matrisi, yönetim özeti (fırsat/tehdit, öncelikli aksiyon). Bu özet DYK (Danışma ve Yönetim Kurulu) modülüne girer.

TİMAŞ'ın bugünkü durumu: CRM'de beklenmedik ölçüde zengin bir rakip verisi var. "Rakip Kitap" varlığında 30.415 kayıt
bulunuyor: kitap adı, yayınevi, yazar, ISBN, liste fiyatı, sayfa sayısı, cilt, kâğıt boyutu, baskı sayısı, kategoriler,
satış adedi, satış durumu, tanıtım metni ve bağlantılar. 214 TİMAŞ kitabı rakip kitaplara emsal olarak bağlanmış. Ancak bu
verinin nereden, ne zaman toplandığı ve güncel olup olmadığı bilinmiyor. Pazar büyüklüğü ve payı için dış veri gerekiyor
(sektör raporları) ve depoda hiç yok. TİMAŞ kendi satışını Logo'dan biliyor, ama bu **sell-in**, yani kitapçıya ve
dağıtıcıya satış. Okurun ne aldığını (sell-through) yalnız kendi sitesinde görebiliyor. Dijital izleme (web, sosyal,
çok satanlar) müşteri ortamında kullanıcı kararıyla kapalı. Bot korumalı siteler kurallar gereği taranmıyor.

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| Genel müdür / yönetim kurulu | Yönetim. DYK iş tanımı M39'dan fırsat/tehdit özeti alıyor (kanıt) | Aylık / çeyreklik | Telefon, sunum |
| Yayın yönetmeni (Kültür, Çocuk) | Editörya. CRM departman seçeneklerinde Kültür Editorya ve Çocuk Editorya var (kanıt) | Aylık, yayın planı döneminde yoğun | Masaüstü |
| Yayın kurulu üyesi / editör (emsal ve rakip) | Editörya. Rakip kitap ↔ TİMAŞ kitabı emsal bağı var (kanıt); M1 ve M10 emsal kullanıyor | Kitap başına | Masaüstü |
| Pazarlama müdürü | Pazarlama | Aylık | Masaüstü, telefon |
| Satış müdürü (kanal gücü) | Satış | Çeyreklik | Masaüstü |
| Fiyatlama (M9) | Mali İşler / yayın yönetimi — **varsayım** | Yeni kitapta | Masaüstü |
| Telif / yabancı haklar (rakip çeviri eğilimleri) | Telif birimi — **varsayım** | Fuar dönemlerinde | Masaüstü |

## 3. Bugün bu iş nasıl yapılıyor

- **Yönetim.** Sektör raporlarını (Türkiye Yayıncılar Birliği yıllık raporu, bandrol ve ISBN istatistikleri) okuyup
  toplantıda tartışıyor (**varsayım**). Pazar payı TİMAŞ'ın kendi cirosunun raporda geçen pazar büyüklüğüne oranıyla kabaca
  hesaplanıyor (**varsayım**).
- **Yayın yönetmeni ve editör.** Rakip kitaplar CRM'de "Rakip Kitap" varlığında tutuluyor. 30.415 kaydın yayınevi linki,
  "Link ID" ve iki satış adedi kolonu, bir kitap sitesinden toplu çekildiği izlenimini veriyor (**varsayım**; kaynak,
  yöntem ve tarih **ölçülecek**). Emsal bağı yalnız 214 kitapta var, yani kullanım sınırlı. Yeni kitap kararında rakibe
  kitapçı sitelerinden elle bakılıyor (**varsayım**).
- **Pazarlama.** SEO & GEO modülünün "Rakipler" ekranı aynı kitap aramasında rakip sitelerin (D&R, Kitapyurdu gibi
  perakendeciler) Google sırasını gösteriyor. Bu rakip *site* görünümüdür, rakip *yayınevi* görünümü değildir. Test
  sunucusunda çalışıyor, aylık kotalı arama servisi kullanıyor.
- **Basın ve web taraması.** 55 açık RSS akışı ve Wikidata ile yazar ve kitap haberlerini topluyor (test sunucusunda). Müşteri
  VM'inde kullanıcı kararıyla kapalı.
- **Sıkıntı.** Rakip verisinin tazeliği bilinmiyor. Pazar büyüklüğü rakamları raporlarda kalıyor, sistemde değil. Rakip
  yayınevi bazında karşılaştırma yapılmıyor.

## 4. İhtiyaçlar ve acı noktaları

**Yönetim**
1. Aylık tek sayfa: pazarda ne oldu, TİMAŞ nerede, üç fırsat ve üç tehdit. Her rakamın kaynağıyla.
2. TİMAŞ'ın kategori bazında büyümesi ile pazarın büyümesinin karşılaştırması (dış rakam varsa).

**Yayın yönetmeni / editör**
1. Bir kategoride rakiplerin fiyat bandı, sayfa sayısı ve formatı. TİMAŞ'ın aynı kategorideki konumu.
2. Yeni kitap için emsal rakip kitaplar (konu, fiyat, format).
3. Rakip yayınevlerinin yeni çıkanları (tazelik sorunu çözülürse).

**Pazarlama / satış**
1. Rakip fiyat ve indirim davranışı (kampanya dönemlerinde).
2. Kanal gücü: TİMAŞ'ın kanallardaki payı (Logo) ile rakiplerin görünürlüğü (arama sırası).

**Fiyatlama**
1. Kategori × sayfa sayısı × format için rakip fiyat dağılımı.

## 5. Nasıl kullanmak isteyecekler

**Kullanıcı hikâyeleri**
- Genel müdür olarak ayda bir, kaynakları belli, tek sayfalık bir pazar özeti okumak istiyorum, çünkü kurula
  hazırlanıyorum.
- Yayın yönetmeni olarak "kişisel gelişim" kategorisinde rakip yayınevlerinin fiyat bandını ve bizim konumumuzu görmek
  istiyorum, çünkü yeni kitabın fiyatını ve formatını buna göre önereceğim.
- Editör olarak yeni bir kitap projesi için emsal rakip kitapları konu ve format benzerliğiyle görmek istiyorum, çünkü yayın
  kuruluna emsalle gitmeliyim.
- Pazarlama müdürü olarak sektör raporunu yüklediğimde önemli rakamların sayfa numarasıyla çıkarılmasını istiyorum, çünkü
  raporun tamamını okumaya vaktim yok.
- Satış müdürü olarak kategorimizde TİMAŞ kitaplarının kanallardaki satış payının yıllar içindeki değişimini görmek
  istiyorum, çünkü kanal stratejisini buna göre kuracağım.
- Yönetici olarak rakip verisinin ne zaman güncellendiğini her ekranda görmek istiyorum, çünkü eski veriyle karar vermem.

**Ana ekranlar ve akış**
- *Pazar özeti* (ilk açılış). Son onaylı yönetim özeti. TİMAŞ'ın kendi göstergeleri (kategori ve yayınevi bazında büyüme,
  Logo). Yüklenmiş sektör raporlarından onaylı rakamlar, kaynak ve sayfa numarasıyla. Rakip verisinin tazelik şeridi.
- *Rakipler*. Yayınevi × kategori matrisi: kitap sayısı, medyan liste fiyatı, sayfa başı fiyat, yeni kayıt sayısı.
  TİMAŞ satırı aynı ölçülerle.
- *Emsal bul*. Kitap adı ya da konu girilir; rakip ve TİMAŞ emsalleri benzerlik gerekçesiyle gelir.
- *Raporlar*. Sektör raporu yükleme (PDF/Excel), Zeki AI rakam çıkarımı, insan onayı, özet taslağı.
- Tık sayıları: bir kategoride fiyat bandını görmek 2 tık; emsal aramak 1 arama + 1 tık; rapor yükleyip rakam onaylamak
  3 adım.
- Telefonda yönetim özeti ve göstergeler okunur. Matris ve rapor işi masaüstünde yapılır.

**Zeki AI'a soracakları örnek sorular**
1. "Rakip yayınevlerinde 200–300 sayfalık kişisel gelişim kitaplarının ortalama fiyatı ne?"
2. "Bizim çocuk kitaplarımızın ortalama fiyatı rakiplerin medyanına göre nerede?"
3. "Geçen yıl hangi kategoride cirosu en çok büyüdük?"
4. "Son yüklenen sektör raporuna göre pazar kaç adet büyüdü, bizim adet büyümemiz ne?"
5. "Bu yeni projeye (konu: …) benzeyen rakip kitaplar hangileri, fiyatları ne?"
6. "Rakip kitap verisi en son ne zaman güncellenmiş?"
7. "Yayınevlerimiz (markalarımız) içinde hangisi toplam cirodan en çok pay alıyor?"

**Otomasyon katmanı**
- K1: CRM rakip kitap verisinin gece anlık görüntüsü, kategori normalleştirmesi (onaylı eşleme), fiyat bantları; TİMAŞ'ın
  kendi kategori/yayınevi göstergeleri (Logo).
- K2: Zeki AI rakip kategori ↔ TİMAŞ kategori eşlemesi ve rapordan rakam çıkarımı önerir, insan onaylar. Emsal önerileri
  gerekçeli gelir.
- K3: Yönetim özeti taslağı (fırsat/tehdit/aksiyon) Zeki AI'dan; onaylayan pazarlama müdürü ya da yönetim. Karar kurulda.
- K4: Yeni sektör raporunun bulunup yüklenmesi, odak grup ve anket çalışması insanda.
- İş tanımındaki "sosyal medya ve Google Trends izleme", "Amazon/Trendyol çok satan listesi takibi" ve "rakip web sitesi
  izleme" bu sürümde yok. Müşteride web taraması kapalı, bot korumalı siteler taranmaz, Google Trends'in resmi ve kararlı
  bir erişimi yok (**varsayım**). Bunlar ancak lisanslı veri ya da kullanıcının yüklediği dosyayla gelir.

**Bildirim / uyarı**
- Pazarlama müdürüne: aylık özet taslağı hazır olduğunda e-posta.
- Yönetime: özet onaylandığında e-posta ve telefonda kart. DYK kurul paketine girdi.
- Veri sahibine: rakip verisi N gündür güncellenmemişse uyarı (N ekipçe belirlenir).

**Onay ve yetki**
- `sayfa:pazar-arastirma`: özet ve TİMAŞ göstergeleri.
- `sayfa:pazar-rakipler`: rakip matrisi ve emsal.
- `ozellik:pazar.rapor-yukle`: sektör raporu yükler.
- `ozellik:pazar.rakam-onay`: çıkarılan rakamları onaylar.
- `ozellik:pazar.kategori-esleme`: rakip kategori eşlemesini onaylar.
- `ozellik:pazar.ozet-onay` (explicit): yönetim özetini onaylayıp DYK'ya gönderir.
- `ozellik:veri.disa-aktar` (var).

## 6. Veri

| Gereken veri | Kaynak | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Rakip kitaplar | CRM `new_rakipkitapBase` (30.415): `new_name`, `new_Yaynevi`, `new_Yazarlar`, `new_Isnb`, `new_ListeFiyat`, `new_SayfaSays`, `new_CiltTipi`, `new_KagitBoyutu`, `new_BaskSays`, `new_Kategoriler`, `new_SatisAdedi`, `new_SatAdedi2`, `new_SatisDurumu`, `new_TanitimMetni`, `new_YayneviLinki`, `new_LinkID`, `CreatedOn`, `ModifiedOn` | Alanlar biliniyor | Kaynak, toplanma tarihi, tazelik, satış adedinin anlamı (kümülatif mi, site sıralaması mı) **ölçülecek** |
| Emsal bağı | CRM `new_new_kitap_new_rakipkitapBase` (214) | Biliniyor | Kullanım dar |
| TİMAŞ kategori ve yayınevi performansı | Logo `v_imprint_perf` (`yayinevi_performans`), `V_SatisRaporu_411/211`; CRM `new_kitapBase` (kitaplık 133, dizi 744, `new_webkategorileritext`, hedef kitle) | Ölçü tanımlı; kayıtlı SQL "yayınevi bazında net ciro" | Kitap ↔ kategori eşlemesi kısmi (web kategori metni 3.428 kitapta) |
| TİMAŞ kanal payı | Logo `CLCARD.SPECODE2` (`kanal_net_ciro`) | Tanımlı | Sell-in; okura satış değil |
| TİMAŞ fiyat bandı | CRM `new_kdvdahilfiyat` (11.232 kitapta dolu), `new_SayfaSays`/sayfa alanı | Biliniyor | — |
| Pazar büyüklüğü, kategori payı | Sektör raporları (Yayıncılar Birliği, bandrol/ISBN istatistikleri, TÜİK kültür istatistikleri) | Depoda yok | **En büyük boşluk.** Kullanıcı yükler; rakam insan onaylı |
| Okur demografisi ve davranışı | Okur anketi, odak grup, TÜİK | Yok (CRM anketi 2 kayıt) | M37 anketiyle ileride |
| Rakip web görünürlüğü | Arama sonucu servisi (`seo_geo/competitors.py`, aylık kota) | Test sunucusunda var; rakip = perakende siteleri | Yayınevi düzeyine çevrilmeli; müşteride açılması kullanıcı kararı |
| Haber ve lansman | Açık RSS (`web_watch.py`, 55 akış) | Test sunucusunda; VM'de kapalı | Müşteride kapalı |
| Çok satan listeleri, sosyal medya, arama eğilimi | Dış | Yok. Bot korumalı siteler taranmaz | Lisanslı veri ya da dosya yükleme |
| Kendi sitemizde arama talebi | Search Console (yalnız okuma) | Var (son 3 ay 9,73 milyon gösterim) | Yalnız TİMAŞ sitesine gelen talep |

## 7. Diğer modüllerle bağ

- Girdi alır: M38 (kanal ve cari yoğunlaşması), M34 (pazar yeri sell-in), M36 (dijital satış), M37 (okur anketi), M25/M26
  (arama talebi, rakip site sıraları, sezon), M9 (TİMAŞ fiyatları), Kategori Ağacı çalışması (TİMAŞ kategorileri).
- Çıktı verir: DYK (kurul özeti), M1 Yayın Kurulu ve M10 Satış Tahmini (emsal rakip kitaplar), M9 Fiyatlama (rakip fiyat
  bandı), M15 Yeni Kitap Pazarlama Planı (pazar bağlamı), M35 (rakip indirim davranışı, veri gelirse), M46 Bütçe.

## 8. Kısıtlar

- **Müşteride web taraması kapalı** (`WEB_WATCH_ENABLED = 0`, 2026-09-25 kullanıcı kararı). M39'un dijital izleme kısmı
  müşteride ancak kullanıcı açıkça "aç" derse çalışır. Test sunucusunda açık kalabilir.
- **Bot korumasını aşan araç kullanılmaz** (1000Kitap, Kitapyurdu, D&R, Hepsiburada, Ekşi 403 veriyor; iki kez reddedildi).
  Yeni kaynak yalnız açık RSS/API, robots.txt'e uyan istek ya da lisanslı veridir.
- **Rakip verisinin hukuki durumu.** CRM'deki rakip kitap verisi bir siteden toplanmışsa kullanım koşulları ve veri tabanı
  hakkı (FSEK) açısından hukuka sorulmalı. İlk sürüm veriyi yalnız kurum içi analizde kullanır, yayımlamaz. Tanıtım metni
  (üçüncü kişinin eseri) ekrana ve modele toplu kopyalanmaz; emsal benzerliği için yalnız kısa özet alanı kullanılır.
- **Sektör raporları telifli olabilir.** Yüklenen rapor portalda yalnız yetkili kişilere açılır. Zeki AI'ın çıkardığı rakam
  sayfa numarasıyla atıflanır; uzun alıntı yapılmaz.
- CRM'e yazılmaz. Kategori eşlemesi ve emsal önerisi köprünün tablolarında durur.
- Ekranda teknoloji adı yok (arama sonucu servisinin adı da yazmaz; "arama sonuçları" denir). Demo veri yok: pazar
  büyüklüğü rakamı yüklenmiş ve onaylanmış bir kaynak yoksa "kaynak yok" yazar, tahmin uydurulmaz. Sayı tavanı yok.
- KVKK: bu modül kişisel veri işlemez. Rakip yazar adları kamuya açık yayın bilgisidir. Okur anketi (ileride) yalnız toplu
  sonuçla gelir.
- Zeki AI sohbeti bugün finans dışı soruları reddediyor (`chat_scope.py`). Pazar soruları için kapsam genişletilmeli.

## 9. Kapsam önerisi

**İlk sürüm** (depodaki veriyle, dış taramasız)
- Rakip kitap verisinin anlık görüntüsü ve tazelik göstergesi (kayıt tarihi dağılımı).
- Rakip kategori ↔ TİMAŞ kategori eşlemesi (Zeki AI önerir, insan onaylar).
- Yayınevi × kategori fiyat, format ve sayfa matrisi; TİMAŞ satırı.
- Emsal bul: rakip + TİMAŞ kitapları, konu ve format benzerliği.
- TİMAŞ iç pazar göstergeleri: kategori, yayınevi ve kanal bazında büyüme (Logo).
- Sektör raporu yükleme, rakam çıkarımı ve onayı, aylık yönetim özeti taslağı → DYK.

**Sonraki sürüm**
- Arama sonucu verisinin (SEO Rakipler) yayınevi düzeyine çevrilmesi ve açık RSS'teki lansman haberleri (müşteride
  kullanıcı kararıyla).
- Lisanslı çok satan ya da perakende satış verisi (varsa).
- Okur anketi (M37 ile) ve demografi.
- Rakip verisinin düzenli tazelenmesi için izinli kaynak (yayınevlerinin kendi katalog dosyaları, açık ISBN/künye
  kaynakları).

**Mevcut kodda yeniden kullanılacaklar**
- `backend/semantic_bridge/seo_geo/competitors.py` (arama sonucu sırası, rakip alan adı listesi, kota yönetimi).
- `backend/semantic_bridge/web_watch.py` (açık RSS, ilgili/ilgisiz sınıflama deseni; `WEB_WATCH_ENABLED` bayrağı).
- `backend/semantic_bridge/seo_geo/seasons.py` (sezon talebi).
- Logo `v_imprint_perf`, kayıtlı SQL `yayinevi-bazinda-net-ciro-ve-brut-k-r-marji-nedir.md`,
  `yay-nevi-baz-nda-2026-ytd-net-ciro-sat-sat-rlar-eksi-iade-sa.md`.
- `backend/semantic_bridge/presentation.py` ve `reports.py` (yönetim özeti ve dışa aktarma; sunum çıktısı gerekiyorsa).
- `access.py`, `admin.py` audit.

## 10. Uzmanlara sorulacak sorular

1. (Editörya / BT) CRM'deki 30.415 rakip kitap kaydı nereden, hangi yöntemle, ne zaman toplandı? Hâlâ güncelleniyor mu?
   "Satış Adedi" ve "Satış Adedi 2" ne anlama geliyor?
2. (Yönetim) Rakip olarak izlenmesi gereken yayınevleri hangileri (kategori bazında)?
3. (Yönetim / pazarlama) Hangi sektör raporlarına erişiminiz var (Yayıncılar Birliği, bandrol istatistikleri, ücretli
   pazar araştırması)? Hangi sıklıkla geliyor?
4. (Hukuk) Rakip kitap verisinin kurum içi analizde kullanımında bir kısıt var mı?
5. (Yönetim) Kurul özetinde hangi göstergeler her ay mutlaka yer almalı?

## 11. Başarı ölçütü

- Aylık yönetim özetinin zamanında (ayın ilk haftası) onaylanıp DYK'ya gitmesi.
- Özetteki her rakamın kaynağının belli olması: kaynaksız rakam 0.
- Yayın kurulu dosyalarında emsal rakip kitap kullanım oranı (bugün 214 bağ).
- Kategori eşlemesinin kapsamı: rakip kayıtların eşlenmiş oranı.
- Kullanım: yayın yönetmenlerinin fiyat bandı ve emsal ekranını açma sıklığı.

## 12. Uzman gözüyle en iyi sistem

*15 yıllık bir yayıncılık pazar araştırması ve strateji müdürünün gözünden (uzman görüşü, TİMAŞ verisine dayanmaz).*

Büyük pazarlarda yayınevleri üç veri katmanıyla çalışır. (1) **Perakende satış paneli:** kitapçı kasalarından toplanan
haftalık satış verisi. Pazar payı, kategori büyümesi ve rakip kitabın gerçek satışı buradan gelir. (2) **Üst veri ve
katalog veri tabanları:** yayımlanan ve yayımlanacak bütün kitapların künye, fiyat ve kategori bilgisi. Rakip yayın
takvimi buradan izlenir. (3) **Talep sinyalleri:** arama eğilimi, çok satan listeleri, sosyal konuşma. Strateji ekibi bu
üçünü aylık bir "pazar nabzı" raporuna döker; her rakam kaynağıyla, her yorum rakamla desteklenir. Türkiye'de perakende
satış paneli sınırlı. Bu yüzden kendi sell-in verisi, sektör raporları ve katalog verisi daha çok ağırlık taşır.

TİMAŞ için mükemmel sistem: CRM'deki rakip katalog düzenli ve izinli bir kaynaktan tazelenir. Kategoriler TİMAŞ ağacına
eşlenir. Logo'dan gelen iç büyüme, sektör raporlarının onaylı rakamlarıyla aynı tabloda durur. Zeki AI her ay kaynaklı bir
özet taslağı yazar, yönetim onaylar ve kurula gider. Editör yeni kitapta emsali tek aramayla bulur.

**Uzmanın bir günü (sistemle; strateji / pazarlama müdürü)** — *örnek senaryo; sayılar temsilîdir, ölçüm değildir*
- 08:45 Telefonda: "Aylık pazar özeti taslağı hazır. Rakip katalog verisi 400 gündür güncellenmedi."
- 09:30 Masaüstünde *Raporlar*. Yayıncılar Birliği'nin yeni yıllık raporunu yükler. Zeki AI 18 rakam çıkarır (toplam adet,
  bandrol, kategori dağılımı), her biri sayfa numarasıyla. 16'sını onaylar, 2'sini düzeltir.
- 10:30 *Pazar özeti*: TİMAŞ'ın çocuk kategorisindeki büyümesi (Logo) ile raporun çocuk kategorisi büyümesi yan yana.
  Zeki AI taslağında "çocukta pazardan hızlı büyüyoruz" cümlesi. Kaynak satırlarını kontrol eder.
- 13:00 Yayın yönetmeniyle toplantı: *Rakipler* matrisinde kişisel gelişim kategorisi, rakiplerin 250 sayfa civarı
  kitaplarının medyan fiyatı ve TİMAŞ'ın konumu. Yeni kitabın fiyat önerisi M9'a not olarak düşer.
- 15:00 *Emsal bul*: yayın kurulundaki yeni projenin konusu yazılır, 12 rakip ve 5 TİMAŞ emsali gelir. İkisini kurul
  dosyasına ekler.
- 17:00 Özeti düzenleyip onaylar. DYK paketine girer, yönetime e-posta gider.

**"Bunu görürsem hemen kullanırım"**
1. Kategori bazında rakip fiyat ve format matrisi, TİMAŞ satırıyla.
2. Raporu yükleyince sayfa numaralı rakam çıkarımı.
3. Her rakamın kaynağı ve tarihi görünen aylık özet taslağı.

**"Bunu yaparsanız kullanmam"**
1. Kaynağı olmayan "pazar büyüklüğü tahmini" üretmek.
2. Rakip verisinin yaşını gizlemek.
3. Sell-in rakamını "pazar payı" diye sunmak.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (tablo / görünüm / ölçü) | CRM (varlık / alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Rakip katalog anlık görüntüsü ve tazelik | — | `new_rakipkitapBase` (bütün alanlar, `CreatedOn`, `ModifiedOn`, `statecode`) | — | Kurallı kopya ve sayım |
| Kategori normalleştirme | — | `new_rakipkitapBase.new_Kategoriler` (serbest metin), TİMAŞ `new_kitaplikBase`, `new_webkategorileritext`, Kategori Ağacı | Rakip kategori metnini TİMAŞ kategori listesinden birine eşler (kapalı küme, tek token + olasılık). Düşük olasılık "belirsiz" | Serbest metin kategoriler kuralla eşlenemez; onay insanda |
| Fiyat ve format matrisi | — | `new_ListeFiyat`, `new_SayfaSays`, `new_CiltTipi`, `new_KagitBoyutu`, `new_Yaynevi`; TİMAŞ `new_kdvdahilfiyat` | — | Medyan ve çeyrekler SQL ile |
| Emsal bulma | TİMAŞ emsalinin satışı `V_SatisRaporu_411/211` | Rakip: ad, yazar, kategori, sayfa, fiyat; kısa tanıtım (ilk birkaç cümle). TİMAŞ: `new_ozet`, `new_kitapspotu` | Aday kümesi kurallı süzgeçle (kategori, sayfa ±, fiyat ±) daraltılır; model konu benzerliğini sıralar ve gerekçe yazar | Konu benzerliği metin işidir |
| TİMAŞ iç göstergeleri | `v_imprint_perf`, `V_SatisRaporu_411/211` (kategori için kitap ↔ kitaplık eşlemesi), `kanal_net_ciro`, `net_ciro`; faturalı satır, `LINENET` | Kitap ↔ kitaplık/dizi | — | Rakam SQL'den |
| Rapordan rakam çıkarma | — | — | Yüklenen PDF/Excel'den gösterge, değer, birim ve sayfa çıkarır (yapılandırılmış çıktı). Her rakam insan onayına düşer | Uzun raporu okuma işi |
| Yönetim özeti | Onaylı iç rakamlar | Onaylı dış rakamlar | Fırsat, tehdit ve aksiyon taslağı yazar; her cümle bir rakama bağlanır (bağsız cümle reddedilir) | K3; karar yönetimde |
| Doğal dil soru | Katalog ölçüleri | `new_rakipkitapBase` (katalogda) | Soru → SQL | `chat_scope.py` kapsamı genişletilmeli |

Model `rt.llm_for("pazar", priority)` ile çağrılır. Rapor çıkarımı ve özet düşük öncelikli arka plan işidir. Uzun PDF'ler
sayfa sayfa gönderilir. `LlmClient` doğrudan kurulmaz. Dış yapay zekâ hizmetine rapor gönderilmez.

## 14. Kodlama planı (kodlayıcıya devir)

**Köprü dosyaları**
- `backend/semantic_bridge/pazar.py`: depo, fiyat/format matrisi, emsal süzgeci, özet akışı.
- `backend/semantic_bridge/pazar_sources.py`: CRM rakip katalog ve TİMAŞ kitapları (`connector_from_file`), Logo
  (yayınevi, kategori, kanal), yüklenen dosyaların metni (PDF metin katmanı; taranmış PDF'te sayfa görüntüsünden okuma
  ikinci sürüm).
- `backend/semantic_bridge/pazar_api.py`: `register(app, rt=..., can=..., audit=...)`.

**Tablolar** (`semantic_pazar_` öneki)
- `semantic_pazar_competitor_books` (tenant_id, crm_id, ad, yayinevi, yazarlar, isbn, liste_fiyat, sayfa, cilt, kagit,
  baski_sayisi, kategori_ham, kategori_id, satis_adedi_ham, satis_durumu, crm_created, crm_modified, kopyalandi_at)
- `semantic_pazar_category_map` (kategori_ham, kategori_id, olasilik, durum [oneri|onaylandi|reddedildi], onaylayan)
- `semantic_pazar_categories` (id, ad, ust_id, kaynak [kitaplik|web|agac]): TİMAŞ kategori listesi
- `semantic_pazar_reports` (id, kaynak, yil, baslik, dosya_yolu, yukleyen, durum, yuklendi_at)
- `semantic_pazar_report_figures` (id, report_id, gosterge, deger, birim, donem, sayfa, alinti_kisa, durum
  [oneri|onaylandi|duzeltildi|reddedildi], onaylayan)
- `semantic_pazar_briefs` (id, donem, taslak_md, kaynaklar_json, durum [taslak|onay_bekliyor|onaylandi], yazan, onaylayan,
  dyk_gonderildi_at)
- `semantic_pazar_watchlist` (yayinevi, kategori, ekleyen): izlenen rakipler

**Uçlar** (`/api/v1/pazar/*`)
- `GET overview` · `GET freshness`
- `GET competitors?yayinevi=&kategori=&q=&page=` · `GET matrix?kategori=&metrik=` · `GET own-market?boyut=kategori|yayinevi|kanal&yil=`
- `GET category-map?durum=` · `POST category-map/{kategori_ham}/decision` · `POST category-map/suggest`
- `POST comparables` (ad/konu → emsal listesi, gerekçeli)
- `POST reports` (dosya) · `GET reports` · `POST reports/{id}/extract` · `GET reports/{id}/figures` ·
  `POST figures/{id}/decision`
- `GET briefs` · `POST briefs/draft?donem=` · `PATCH briefs/{id}` · `POST briefs/{id}/approve`
- `GET watchlist` · `POST watchlist` · `POST run-due` (sistem jetonu)

**Ekranlar**: `src/canvas/pazar/` → `MarketHome.tsx`, `CompetitorMatrix.tsx`, `ComparablesScreen.tsx`,
`ReportsScreen.tsx`, `BriefEditor.tsx`. Rotalar `/timas/pazar-arastirma`, `/pazar-arastirma/rakipler`,
`/pazar-arastirma/emsal`, `/pazar-arastirma/raporlar`, `/pazar-arastirma/ozet/:donem`. Menü: `navModel.ts` Analiz alanı,
"Pazar ve rakip" öğesi (Yönetim raporlarına yakın; yöneticinin çalışma alanı). Kampüs: `ModulesMenu.tsx` `LIVE` içine
`M39: '/pazar-arastirma'`, `GROUP_HOME` içine `'Müşteri & Pazar'` (M38 ile ortak grup; kart M38'e gidiyorsa M39 ikinci
bağlantı).

**Yetki**: `sayfa:pazar-arastirma`, `sayfa:pazar-rakipler`, `sayfa:pazar-raporlar`; `ozellik:pazar.rapor-yukle`,
`ozellik:pazar.rakam-onay`, `ozellik:pazar.kategori-esleme`, `ozellik:pazar.ozet-onay` (**explicit**); mevcut
`ozellik:veri.disa-aktar`. Yüklenen raporun dosyası yalnız `sayfa:pazar-raporlar` yetkisiyle indirilir.

**Zamanlayıcı**: `scripts/server/timas-pazar.timer`, haftalık (pazartesi 05:30). Rakip katalog anlık görüntüsü, tazelik,
yeni kategori metinleri için eşleme önerisi, iç göstergeler. Ayın ilk iş günü özet taslağı. Dış tarama yok; ileride
açılırsa `WEB_WATCH_ENABLED` benzeri ayrı bir bayrakla (`MARKET_WATCH_ENABLED`, VM'de 0).

**Kabul testleri** (doğrudan bağlantıyla)
1. Rakip katalog ve tazelik: `SELECT COUNT(*), MIN(CreatedOn), MAX(CreatedOn), MAX(ModifiedOn) FROM dbo.new_rakipkitapBase
   WHERE statecode = 0` = ekrandaki kayıt sayısı ve tazelik şeridi (2026-09-09 kataloğunda satır 30.415).
2. Yayınevi fiyat bandı: `SELECT new_Yaynevi, COUNT(*), PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY new_ListeFiyat)
   OVER (PARTITION BY new_Yaynevi) FROM dbo.new_rakipkitapBase WHERE statecode = 0 AND new_ListeFiyat > 0` (DISTINCT
   yayınevi) = matris medyanları (5 yayınevi örneği).
3. TİMAŞ fiyat bandı: `SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY new_kdvdahilfiyat) OVER () FROM
   dbo.new_kitapBase WHERE statecode = 0 AND new_kdvdahilfiyat > 0` (kategori süzgeciyle) = matristeki TİMAŞ satırı.
4. Emsal bağı: `SELECT COUNT(*) FROM dbo.new_new_kitap_new_rakipkitapBase` (katalogda 214) = "CRM'de kayıtlı emsal"
   sayısı; bir kitabın emsalleri CRM bağıyla birebir.
5. Yayınevi (marka) cirosu: kayıtlı SQL `yay-nevi-baz-nda-2026-ytd-net-ciro-sat-sat-rlar-eksi-iade-sa.md` doğrudan
   Logo'da koşulur = iç göstergeler ekranı.
6. Kanal payı: kayıtlı SQL `2026-y-l-nda-kitapci-e-ticaret-ve-dagitici-kanallar-i-in-ay.md` = kanal grafiği; "pay"
   paydası bütün kanalların pozitif net cirosu (katalog kuralı).
7. Rapor rakamı: onaylı her rakam için sayfa numarası elle açılıp değer doğrulanır (10 rakam örneklemi); çıkarım doğruluk
   oranı kayda geçer.
8. Özet: onaylı özetteki her cümlenin `kaynaklar_json`'da en az bir rakama bağlı olduğu otomatik test edilir.

**Bağımlılık**: Bağımsız başlayabilir (CRM ve Logo okuması hazır). Kategori eşlemesi "Kategori Ağacı" çalışmasının
ağacını kullanır; ağaç yoksa CRM kitaplık listesiyle başlar. DYK modülü özeti okur. M9 ve M1 emsal çıktısını sonradan
bağlar. Paralel kodlanabilir.

**Tahmini büyüklük**: L (3+ gün). Katalog, matris ve emsal M; rapor yükleme, çıkarım ve özet M; ekranlar M.
