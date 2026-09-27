# H1 — Kategori Ağacı Modülü: kullanıcı ihtiyaç analizi

Durum: analiz (kod yok) · Tarih: 2026-09-28 · Modül kimliği `categories` (`src/canvas/modules.json`, «Hazırlıklar» grubu)

Kaynaklar: iş tanımı `specs/Kategori_Ağacı_Modülü.txt` (ZEKİ_Moduller3.html'den), `ZEKİ_Veri_Haritasi2.html`,
`docs/analiz/crm-eticaret-entegrasyon-2026-09-27.md`, `docs/analiz/seo-geo-modul-2026-09-25.md`,
`docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`, `docs/analiz/yetki-mekanizmasi-2026-09-27.md`,
`apps/editor/docs/TUM-KITAP-TURLERI-ANALIZ.md`, `configs/semantic/knowledge/crm/table_descriptions.json` (CRM Türkçe
metadata, satır sayıları 2026-09-09 taraması), `configs/semantic/knowledge/logo/` (ITEMS, ölçü tanımları),
`backend/semantic_bridge/editorial_assign.py` (M2 kategori–editör kuralı), `backend/semantic_bridge/seo_geo/pages.py`,
`apps/editor/src/editor/production/profile.py` ve `marketing.py`, `src/canvas/nav/navModel.ts`,
`backend/semantic_bridge/access.py` + `access_catalog.json`, PROJECT-MEMORY.md, kullanıcı belleği
(tsoft-no-write, crm-tsoft-no-push-integration, customer-vm-web-watch-off, no-tech-names-on-screens,
system-of-record-logo, timas-logo-database-shape, editor-all-book-types, crm-book-project-link).

Bu analiz sunucuya bağlanmadan yazıldı. Sayıların hepsi yukarıdaki belgelerde daha önce ölçülmüş değerlerdir,
tarihleriyle verildi. Ölçülmemiş her şey «ölçülecek», kanıtı olmayan her iddia «varsayım» diye işaretlidir.

---

## 1. Modül ne işe yarar

TİMAŞ'ın her kitabı için tek, tutarlı bir «kitap profili» (künye + kategori mimarisi + özellikler + içerik özeti +
emsaller) üretir ve bu profili bir editörün onayından geçirerek saklar. İş tanımı iki aşama öngörüyor: (1) mevcut
kataloğun bir defa toptan elden geçirilmesi, hataların bulunması; (2) yeni kitap açıldıkça profilin kendiliğinden
taslak olarak hazırlanıp editöre sunulması.

Bugünkü sorun iş tanımında «Bazı alanlar eksik → yeni mimari bu ihtiyaçtan doğdu» diye geçiyor. Veri bunun daha
büyük olduğunu gösteriyor: CRM'de bir kitap **en az yedi ayrı sınıflama sisteminde** duruyor (Kitaplık, Ürün
Kategorisi ağacı, Raf Kategorisi, Sergilenecek Kategori, Tür metni, Web Kategorisi metni, Tema, ayrıca T-soft'taki
138 kategorilik site ağacı) ve bunların hiçbiri diğerine bağlı değil; bir kısmı 2016'dan beri güncellenmiyor
(ayrıntı §3, §6). Modülün asıl değeri, bu dağınık sınıflamaları tek bir onaylı ağaca bağlamak ve eksikleri kitap
kitap, öncelik sırasıyla kapattırmaktır.

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| Editör (profil onaylayan) | Editörya (CRM ekip üyeliği 54 kişi, 2026-09-15 ölçümü; `new_kitapBase.new_Editor`, `new_projeeditoru`) | Haftada birkaç kez; toplu güncelleme döneminde her gün | Masaüstü (uzun metin karşılaştırma) |
| Yayın yönetmeni / marka editoryal direktörü | Editörya yönetimi (`new_kitapBase.new_yayinyonetmeni`, `new_markaBase.new_EditoryalDirektoru` alanları var; kim olduğu ölçülecek) | Haftalık; ağaç değişikliğinde | Masaüstü; onay telefonda da |
| Katalog / ürün kartı sorumlusu | Varsayım: stok kartını açan kişi. CRM'de kitap kaydı ağırlıkla «Timas CRM» ortak hesabıyla oluşturuluyor (2026-09-15) → gerçek kişi sorulacak | Her gün (yeni kart açıldığında) | Masaüstü |
| E-ticaret / web içerik uzmanı | Pazarlama (CRM ekip üyeliği 35 kişi) — T-soft site kategorisini yöneten kişi varsayım | Haftalık | Masaüstü |
| SEO uzmanı | Pazarlama; mevcut «SEO & GEO» modülünün kullanıcısı | Haftalık | Masaüstü |
| Satış / raf sorumlusu | Satış (ekip 49 kişi). CRM'de raf firmasına göre raf kategorisi var (Timaş, D&R, TveK, Remzi, Nezih rafı) → kullanan kişi varsayım | Aylık, yeni dönem listelerinde | Masaüstü; bakış telefonda |
| Portal yöneticisi | BT / proje ekibi | Kurulumda ve ağaç sürümünde | Masaüstü |

## 3. Bugün bu iş nasıl yapılıyor

**Editör / katalog sorumlusu (kanıt: CRM şeması ve doluluk ölçümleri):** Kitap kartı CRM'de (`new_kitapBase`, 336
sütun) elle doldurulur. Sınıflama için aynı kartta ayrı ayrı şunlar var: `new_kitaplikid` (133 kitaplık),
`new_diziid` (744 dizi), seri (57), `new_yayineviid` → marka (34), `new_YayneviAltMarka` (12), `new_turlertext` (serbest
metin tür; aktif 9.091 kitabın %53'ünde dolu, 2026-09-24), `new_webkategorileritext` («Çocuk;6 - 10 Yaş Öykü Hikaye»
biçiminde serbest metin; %34), `new_hedefkitle` (%98,5 dolu), yaş başlangıç/bitiş + 14 ayrı «N Yaş» onay kutusu,
14 ayrı «N. Sınıf» onay kutusu, çoka-çok tablolar: ürün kategorisi (27.070 bağ), raf kategorisi (6.648), sergilenecek
kategori (3.642), tema (1.143), anahtar kelime (52.135), kavram/ünite (35.166), ders (5.740). Adım sayısı: bir kitabın
tam sınıflanması bu alanların ayrı ayrı açılıp seçilmesini gerektirir (varsayım: 15+ ekran işlemi). Tıkanma: hangi
alanın «doğru» olduğu tanımlı değil; serbest metin alanları aynı kavramı farklı yazımla tutuyor.

**E-ticaret / SEO (kanıt: T-soft okuması 2026-09-25):** Site kategorileri T-soft'ta ayrı bir ağaçtır (138 kategori,
136'sında SEO başlığı dolu, 42'sinde başlık = kategori adı). CRM'deki web kategori tabloları (`new_webkategori` 27,
`new_webaltkategori` 120) 2016'dan beri değişmemiş; CRM'den T-soft'a kategori aktaran bir mekanizma bulunamadı
(`crm-eticaret-entegrasyon-2026-09-27.md` §1, §5). Yani site kategorisi T-soft panelinde elle yönetiliyor (varsayım,
BT'ye sorulacak).

**Satış / raf (kanıt: CRM şeması):** Raf firmasına göre kategori (`new_bukitaphangialtkategorilerdeolmalBase`, 60 alt
kategori; raf firması seçenekleri Timaş/D&R/TveK/Remzi/Nezih) kitap kartında işaretlenir. Kullanılıp kullanılmadığı,
son değişiklik tarihi ölçülecek.

**Editoryal atama (kanıt: kod):** M2 editör atama kuralı kategori olarak «Kitaplık, yoksa marka» kullanıyor; 2024'ten
beri 2.738 etkin projede Kitaplık 1.341, marka 2.721 projede dolu (2026-09-27, `editorial_assign.py`). Yani Kitaplık
bugün editöryal işbölümünün fiilî kategorisidir ama projelerin yarısında boştur.

**Emsal kitap (kanıt: şema):** Kitap kartında «Emsal Kitaplar» (`new_RakipKitaplarLookUp`) ve «Rakip Kitaplar»
(`new_rakipkitaplar`) alanları var; rakip kitap tablosu (`new_rakipkitapBase`) 30.415 satır, satış adedi ve kategori
kolonlarıyla. Doluluğu ve verinin tarihi ölçülecek (varsayım: geçmişteki bir tarama işinden kaldı).

## 4. İhtiyaçlar ve acı noktaları

**Editör**
1. Bir kitabın bütün sınıflamalarını tek ekranda, çelişkileri işaretlenmiş hâlde görmek.
2. Öneriyi gerekçesiyle görmek (hangi cümleye, hangi alana dayandığı); tek tıkla kabul/düzelt/ret.
3. Toplu iş yükünü yönetilebilir parçalara bölmek: önce çok satan ve satışta olan kitaplar.
4. Kendi kitaplarını (yayın yönetmeni/editör bağı) ayrı süzmek.

**Yayın yönetmeni / marka direktörü**
1. Kategori ağacını (yayınevi → ana → alt → alt alt) tek yerde, sürümlü tutmak ve onaylamak.
2. Ağaç değişikliğinin etkisini önceden görmek: kaç kitap, hangi editör kuralı, hangi site kategorisi etkilenir.
3. Kategori bazında katalog dengesini görmek (kitap sayısı, satış, boşluk).

**Katalog / kart sorumlusu**
1. Yeni kart açıldığında taslak profilin hazır gelmesi (CRM'e yazılacak alanlarla birlikte).
2. «CRM'e işlenecek fark» listesini alıp CRM'de uygulamak (portal CRM'e yazmaz, §8).

**E-ticaret / SEO**
1. Timaş ağacı ↔ T-soft site kategorisi eşlemesi; eşlenmemiş ya da yanlış kategorideki ürünler listesi.
2. Arama/listeleme etiketlerinin kontrollü sözlükten gelmesi (SearchKeywords ile tutarlı).

**Satış / raf**
1. Timaş ağacından raf firmalarının kategorisine eşleme; yeni kitapta raf önerisi.

## 5. Nasıl kullanmak isteyecekler

### Kullanıcı hikâyeleri
- Editör olarak kitabın önerilen profilini mevcut CRM değerleriyle yan yana görmek istiyorum, çünkü neyin değiştiğini
  bir bakışta anlamalıyım.
- Editör olarak her önerinin kaynağını (arka kapak cümlesi, künye alanı, benzer kitap) görmek istiyorum, çünkü
  kanıtsız öneriyi onaylamam.
- Editör olarak yalnız kendi kitaplarımı ve önce satışta olanları görmek istiyorum, çünkü 9 bin kitabı sırasız
  onaylayamam.
- Editör olarak profili kısmen onaylamak istiyorum (kategoriler tamam, özet sonra), çünkü alanların olgunluğu farklı.
- Yayın yönetmeni olarak ağaca yeni alt kategori eklemeden önce kaç kitabın taşınacağını görmek istiyorum, çünkü
  ağaç değişikliği editör kurallarını ve site sayfalarını etkiler.
- Yayın yönetmeni olarak ağacın sürümlerini ve kimin neyi değiştirdiğini görmek istiyorum, çünkü kategori mimarisi
  kurum kararıdır.
- Katalog sorumlusu olarak onaylanan profillerin CRM'e girilecek farkını dosya olarak almak istiyorum, çünkü CRM'e ben
  işliyorum.
- E-ticaret uzmanı olarak T-soft'ta yanlış kategorideki ürünleri listelemek istiyorum, çünkü müşteri kitabı yanlış
  rafta arıyor.
- SEO uzmanı olarak kategori sayfasının hangi kitapları kapsaması gerektiğini ağaçtan okumak istiyorum, çünkü kategori
  sayfası önerileri buna dayanıyor.

### Ana ekranlar ve akış
1. **Özet (ilk açılış):** katalog sayacı (aktif kitap), profil durumu (onaylı / taslak / hiç yok), alan doluluk
   çubukları (Kitaplık, tür, web kategorisi, yaş, tema, özet), tutarsızlık sayısı, «bana düşenler» kutusu.
2. **Onay kuyruğu:** süzgeçler (benim kitaplarım, marka, kitaplık, satışta/satış dışı, öncelik = son 24 ay net adet),
   satır başına durum rozeti. Tek tıkla profil ekranına.
3. **Kitap profili:** solda mevcut (CRM + T-soft), sağda öneri; alan alan kabul/düzelt/ret; kaynak kanıtı açılır
   panelde; alt çubukta «Onayla», «Kısmi onay», «Yeniden üret».
4. **Kategori ağacı:** ağaç düzenleyici (taslak → onay), düğüm başına kitap sayısı, satış, eşlemeler (CRM Kitaplık,
   Ürün Kategorisi, Raf, T-soft, uluslararası konu kodu); sürüm geçmişi; etki önizlemesi.
5. **Tutarsızlıklar:** kural adı, kitap, çelişen alanlar, önerilen düzeltme; toplu seçim.
6. **CRM'e işlenecek fark:** onaylı profil ile CRM'in bugünkü değeri arasındaki fark; CSV/Excel.

En sık üç işlem ve tık sayısı:
- Bir profili onaylamak: kuyruk → satır (1) → «Onayla» (2). Hedef ≤ 2 tık, ≤ 60 sn.
- Tek alanı düzeltip onaylamak: satır (1) → alan açılır listesi (2) → seçim (3) → «Onayla» (4).
- Tutarsızlık listesinden toplu düzeltme: süzgeç (1) → tümünü seç (2) → «Öneriyi uygula» (3) → onay (4).

### Zeki AI'ya soracakları örnek sorular
- «Çocuk 6–10 yaş masal kategorisinde son iki yılda en çok satan 20 kitap hangisi?»
- «Kitaplığı boş olan ve bu yıl satışı olan kitapları göster.»
- «Web kategorisi ‹Çocuk› ama hedef kitlesi ‹Yetişkin› görünen kitaplar var mı?»
- «Tasavvuf kategorisinde kaç kitabımız var, kaçı satışta?»
- «‹Böcekleri Seven Kadın›a benzer, aynı hedef kitleye yazılmış bizim kitaplarımız hangileri?»
- «Kişisel gelişim ağacında en az kitap olan alt kategori hangisi?»
- «Bu ay açılan yeni kitaplardan profili onaylanmamış olanlar kimde bekliyor?»

### Otomasyon katmanı
| Adım | Katman | Not |
|---|---|---|
| CRM/T-soft/Logo'dan okuma, mevcut sınıflamaların toplanması | K1 | Gece, değişen kayıtlar |
| Deterministik tutarsızlık kuralları (ör. hedef kitle ↔ web kategorisi) | K1 | Yalnız liste üretir, değiştirmez |
| Kitap başına kategori/tema/etiket/özet önerisi | K2 | Zeki önerir, editör onaylar |
| Emsal kitap listesi | K2 | Rakam SQL'den, seçim gerekçesi Zeki'den |
| Kategori ağacı tasarımı ve değişikliği | K3 | Zeki etki analizi yapar, yayın yönetmeni karar verir |
| CRM'e işleme | K4 | İnsan işler; portal yalnız fark listesi verir |

### Bildirim/uyarı
- Yeni kart açıldı ve taslak hazır → kitabın editörüne (CRM `new_Editor`/`new_yayinyonetmeni`) portal bildirimi
  (Kampüs zil); isteğe bağlı günlük e-posta özeti (mevcut SMTP ayarı).
- Ağaç taslağı onay bekliyor → onay yetkisi olanlara.
- Tutarsızlık sayısı haftalık arttıysa → yayın yönetmenine haftalık özet.
- CRM'e işlenecek fark 7 günden eski → katalog sorumlusuna hatırlatma (eşik ayarlanabilir).

### Onay ve yetki (öneri)
| İşlem | Kim görür | Kim değiştirir | Kim onaylar | Anahtar |
|---|---|---|---|---|
| Sayfayı görmek | Editörya, Pazarlama, Satış | — | — | `sayfa:kategori-agaci` |
| Öneri üretmek / yeniden üretmek | — | Editör | — | `ozellik:kategori.oneri-uret` |
| Profil onayı | — | — | Editör (kendi kitabı), yayın yönetmeni (herkesinki) | `ozellik:kategori.profil-onay` (açıkça verilir), `ozellik:kategori.herkesinki` |
| Ağaç taslağı | — | Yayın yönetmeni, portal yöneticisi | — | `ozellik:kategori.agac-duzenle` |
| Ağaç sürümünü yürürlüğe almak | — | — | Yayın yönetmeni / yönetim | `ozellik:kategori.agac-onay` (açıkça verilir) |
| Fark listesini indirmek | Katalog sorumlusu | — | — | mevcut `ozellik:veri.disa-aktar` |

## 6. Veri

| Gereken veri | Kaynak | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Stok kodu, ad, ISBN, barkod, statü | CRM `new_kitapBase` (`new_StokKodu`, `new_name`, `new_urunadi`, `new_isbn13`, `new_ean13`, `statecode`, `new_kitap_yayincilikstatusu`) | 13.598 kart (2026-09-09); aktif kitap `new_Tip=1` 9.091 (2026-09-24) | Yok |
| Logo stok kartı eşleşmesi | Logo `LG_411_ITEMS.CODE` = CRM `new_StokKodu`; `ITEMS.SPECODE` = yayınevi | Hakediş ve bütçe modülleri aynı bağı kullanıyor | `STGRPCODE`, `CATEGORYID/NAME`, `SPECODE2..5` kullanımı ölçülecek |
| Yazar, çizer, çevirmen | CRM `new_yazartext`, `new_cizerlertext`, `new_eserkatilimBase` (36.330) | Hazır | Çevirmen metin alanı yok, eser katılım rolünden okunur |
| Yayınevi / marka / alt marka | CRM `new_yayineviid` → `new_markaBase` (34, `new_HedefKitleGrup`), `new_YayneviAltMarka` (12) | Hazır | — |
| Kitaplık | CRM `new_kitaplikid` → `new_kitaplikBase` (133) | Projede %49 dolu (2026-09-27) | Kitap kartında doluluk ölçülecek |
| Dizi / seri | CRM `new_diziid` (744), `new_seriBase` (57) | Şema var | Doluluk ölçülecek |
| Tür | CRM `new_turlertext` (%53), `new_rafturu`, `new_turBase` (121) | Ölçüldü (2026-09-24) | %47 boş; serbest metin, sözlük yok |
| Hedef kitle, yaş, sınıf | CRM `new_hedefkitle` (%98,5), `new_hedefkitleyasbaslangic/bitis`, `new_1Yas…new_14Yas`, `new_1Sinif…`, `new_yaslartext`, `new_siniflartext` | Hazır | Üç ayrı yaş gösterimi tutarlı mı ölçülecek |
| Web kategorisi (CRM) | `new_webkategorileritext` (%34; 3.428 kitap), `new_new_urunkategorisi_new_kitapBase` (27.070 bağ; `new_urunkategorisiBase` 1.152, `new_anakategoriid` ile hiyerarşi, `new_Site` eski siteler) | Metin alanı ölçüldü | Ürün kategorisinin güncelliği (son `ModifiedOn`) ölçülecek; eski çoklu site döneminden kalma olabilir |
| Site kategorisi (T-soft) | T-soft `category/getCategories` (138) + ürün `DefaultCategoryId`; SEO modülünde eşitleniyor (`semantic_seo_*`) | Okundu 2026-09-25 | CRM ile bağ kanıtlanamadı |
| Raf kategorisi | CRM `new_rafkategorisiBase` (75) + bağ 6.648; `new_bukitaphangialtkategorilerdeolmalBase` (60) + bağ 3.642 | Şema var | Kullanım ve güncellik ölçülecek |
| Tema | CRM `new_temaBase` (115) + bağ 1.143 | Şema var | Az kullanılıyor (kitapların küçük bir kısmı) |
| Etiket / anahtar kelime | CRM `new_anahtarkelimeBase` (5.755) + bağ 52.135; metin `new_AnahtarKelimeler`; T-soft `SearchKeywords` (2.686 ürün) | SEO eşlemesi: 2.351/2.353 aynı | Sözlük temizliği (eş anlam, yazım) yok |
| Kavram / ders | CRM kavram/ünite 1.396 + 35.166 bağ; ders 22 + 5.740 | Şema var | — |
| Kısa özet, arka kapak | CRM `new_ozet` (9.373, HTML), `new_kitapspotu` (6.869), `new_kitaptanitimwebmetni` (116), `new_TantmFyMetni` (4.653) | Ölçüldü (09-22, 09-27) | Web metni neredeyse boş |
| Motto cümlesi | CRM `new_kitabinenonemlicumlesi` (5.459) | Ölçüldü | %40 civarı kitapta yok (oran ölçülecek) |
| Öne çıkan yanlar / alıntılar | `new_kitabinonecikanyanlari` (6.471), `new_alintlar` (1.622) | Ölçüldü | — |
| Ritim, ana karakterler | CRM'de yok; editör motoru (kitap okuma modülü) okutulan kitaplarda karakter ve profil üretiyor | Kabul korpusu birkaç kitap | Kaç kitabın okutulduğu ölçülecek |
| Kitap tam metni (PDF arşivi) | İş tanımı «`{ISBN}.pdf`, vektör veritabanı aktif» diyor | CRM `new_dokumandurumu` (Yüklendi/Yüklenmedi), `new_okumalink` (tadımlık) alanları var | Arşivin yeri, kapsamı ve adlandırması ölçülecek; «aktif» iddiası doğrulanmadı |
| Timaş emsal (satış) | Logo `LG_<firma>_01_STLINE` faturalı satır; yayinevi_performans ölçüsü | Tanımlar sertifikalı | Logo kopyası (.155) 2026-08-17'de donmuş; güncellik riski |
| Timaş emsal (elle) | CRM `new_RakipKitaplarLookUp` («Emsal Kitaplar»), `new_rakipkitaplar` | Şema var | Doluluk ölçülecek |
| Rakip emsal | CRM `new_rakipkitapBase` (30.415; ad, yayınevi, kategoriler, satış adedi, tanıtım metni) | Şema var | Tarih ve kaynak ölçülecek |
| Uluslararası konu sınıflaması | Dış: uluslararası kitap konu standardı (Thema) dosyası | Yok | Lisans/erişim ve Türkçe sürüm doğrulanacak |
| Kategori ağacının kendisi, onaylar | Portal kendi tabloları | Yok | Kurulacak |

## 7. Diğer modüllerle bağ

- **Girdi alır:** CRM kitap kartı; Logo satış; T-soft kategori/ürün (SEO modülünün eşitlemesi); editör motorunun kitap
  profili ve pazarlama kiti (okutulmuş kitaplar); M2 kategori–editör kuralı (hangi düğüm hangi editörün).
- **Çıktı verir:**
  - M1 başvuru değerlendirmesi: «kategori önerisi» aynı ağaçtan seçilir.
  - M2 editör atama: kural tablosu bugün Kitaplık/marka üstünde; ağaç düğümüne geçiş seçeneği.
  - M10 ilk baskı ve M11 baskı tekrarı: emsal kitap listesi (aynı düğüm + hedef kitle).
  - M15–M18 pazarlama planları, M24 katalog/bülten: kategori bazlı kitap seçimi.
  - M25/M26 SEO & GEO: kategori sayfası kapsamı, arama etiketleri, ürün kategorisi düzeltme önerisi.
  - M34/M40/M41/M42 platform yönetimi: Timaş ağacı → pazaryeri kategori eşlemesi.
  - H2 okuyucu, H3 e-ticaret, M37 topluluk: «ilgi alanı» sözlüğü = ağaç düğümleri.
  - M39 pazar araştırması: kategori bazlı rakip görünümü.

## 8. Kısıtlar

- **T-soft'a yazma yasak** (kullanıcı kararı 2026-09-25): site kategorisi düzeltmesi yalnız öneri/liste olarak kalır.
- **CRM'e yazma yok:** onaylı profil portalın kendi tablolarında durur; CRM'e insan işler. Ekranda «CRM'e işlenmesi
  gereken fark» (M6 sözleşmelerdeki desen).
- **Müşteride web taraması kapalı** (2026-09-25): iş tanımındaki «ZEKİ dünya genelinde önde gelen yayınevlerini tarar»
  adımı müşteri VM'inde yapılamaz; bot korumalı siteler zaten taranmıyor. Yerine uluslararası konu sınıflama
  standardı dosya olarak içe alınır ve CRM'deki rakip kitap tablosu kullanılır.
- **Ekranda teknoloji adı yok:** «Zeki AI», «Zeki AI önerisi». T-soft müşteri platformu adı olarak kalabilir (SEO
  modülündeki karar).
- **Demo veri yok, sayı tavanı yok:** kuyruk bütün kataloğu kapsar; önceliklendirme sıralama ile yapılır, kesme ile
  değil.
- **Sabit çözüm yok:** kitaba özel kural/istem yazılmaz; kurallar veriden türetilir ve ekrandan yönetilir.
- **Model eğitimi:** iş tanımındaki ince ayar (500–1.000 onaylı profil, ≥%85 doğruluk) ilk sürümün önkoşulu değil;
  onaylar birikince değerlendirme seti olur (M50).
- **Hukuk:** kitap metni telifli içeriktir; özet ve alıntı yalnız iç kullanımda, dışa giden metin (site, katalog)
  editör onayından geçer. Kişisel veri yok (yazar adı zaten kamuya açık künye).

## 9. Kapsam önerisi

**İlk sürüm (en çok değer, en az bağımlılık)**
- Mevcut sınıflamaların tek ekranda toplanması (CRM alanları + T-soft kategori), alan doluluk panosu.
- Deterministik tutarsızlık kuralları ve liste.
- Kategori ağacı: CRM Kitaplık + marka + hedef kitle + mevcut web kategori metninden taslak ağaç önerisi; yayın
  yönetmeni onayı; sürüm.
- Kitap başına kategori + tür + yaş + etiket önerisi (kapalı küme seçimi), onay kuyruğu, kısmi onay.
- CRM'e işlenecek fark listesi (CSV/Excel).
- Öncelik: son 24 ay net adet (Logo) ile sıralama.

**Sonraki sürüm**
- Özet, motto, karakter, ritim alanları (editör motoruyla okutulmuş kitaplarda).
- Emsal kitap (Timaş + rakip), gerekçe cümlesi.
- T-soft ve raf firması eşleme ekranı; pazaryeri kategori eşlemesi (M34 ile).
- Uluslararası konu kodu eşlemesi.
- Yeni kart açıldığında kendiliğinden taslak (Aşama 2).

**Mevcut kodda yeniden kullanılacaklar**
- `backend/semantic_bridge/editorial_assign.py` — kategori (Kitaplık/marka) okuma, kural tablosu sürüm/onay deseni.
- `backend/semantic_bridge/seo_geo/connections.py` (yalnız okuma T-soft istemcisi), `seo_geo/store.py` (eşitlenmiş
  ürün/kategori), `seo_geo/pages.py` (kategori sayfası önerisi), `seo_geo/crm.py` (CRM kitap kartı okuma).
- `backend/semantic_bridge/contracts.py` — «CRM'e işlenmesi gereken fark» deseni.
- `backend/semantic_bridge/budget_sources.py` — Logo yıl/firma eşlemesi ve faturalı satır tanımı.
- `backend/semantic_bridge/admin.py` — `audit`, ayarlar (`admin.conf`).
- `apps/editor/src/editor/production/profile.py` (yaş/tür/ton), `characters.py`, `marketing.py` (özet) — köprüden
  vekil uçlarla okunur, yeniden yazılmaz.
- `src/canvas/editorial/` bileşenleri (kitap kartı `BookCard.tsx`, kapak `Cover.tsx`).

## 10. Uzmanlara sorulacak sorular

1. Bugün «doğru kategori» hangi alan: Kitaplık mı, web kategori metni mi, T-soft site ağacı mı? Hangisi terk edilebilir?
2. Ağacın seviyeleri iş tanımındaki gibi (Yayınevi → Ana → Alt → Alt alt) mı; yaş ve hedef kitle ağaçta mı yoksa ayrı
   eksen mi?
3. Raf firmalarına (D&R, TveK, Remzi, Nezih) göre raf kategorisi hâlâ kullanılıyor mu, kim güncelliyor?
4. PDF arşivi nerede, adlandırma gerçekten `{ISBN}.pdf` mi, kaç kitap var?
5. Onaylı profili CRM'e kim işleyecek ve CRM'e yeni alan (ör. «motto», «ritim») açılacak mı?

## 11. Başarı ölçütü

- Aktif kitaplarda «tek onaylı kategori düğümü» olan kitap oranı: başlangıç ölçülecek, hedef satışta olan kitapların
  tamamı.
- Onaylanan önerilerde editörün değiştirmeden kabul oranı (iş tanımı hedefi ≥ %85; müdahale < %15).
- Profil başına ortalama onay süresi (hedef ≤ 60 sn kategori-only profil).
- Tutarsızlık sayısının haftalık düşüşü.
- CRM'e işlenecek farkın yaşı (7 günden eski fark sayısı).
- Kullanım: haftalık aktif editör sayısı, onaylanan profil sayısı.

---

## 12. Uzman gözüyle en iyi sistem

Bakış açısı: 15 yıllık katalog ve metadata müdürü (bir yayınevinde kitap künyesinin, kategori mimarisinin ve
perakendeciye giden ürün bilgisinin sahibi).

**Sektörde iyi örnekler nasıl çalışıyor.** Büyük yayınevleri künye ve sınıflamayı tek bir «başlık yönetim sistemi»nde
tutar; site, katalog, perakendeci beslemesi (ONIX) ve iç raporlar bu tek kayıttan türetilir. Konu sınıflaması
uluslararası bir standarda (Thema; ABD'de BISAC) bağlanır, yayınevinin kendi ticari ağacı bunun üstünde durur ve her
perakendecinin kategori ağacına bir eşleme tablosuyla çevrilir. Etiketler kontrollü sözlükten seçilir; serbest metin
yalnız öneri kuyruğuna düşer. Künye tamlığı bir puanla izlenir, eksik künyeli kitaplar satış önceliğine göre
kapatılır. Metadata endüstri çalışmaları (ör. Nielsen'in metadata–satış ilişkisi raporları) tam künyeli kitapların
belirgin biçimde daha çok sattığını gösterir (oran bu analizde doğrulanmadı).

**TİMAŞ için mükemmel sistem.** Tek onaylı ağaç, her düğümde: CRM Kitaplık/ürün kategorisi/raf karşılığı, T-soft
kategorisi, uluslararası konu kodu, sorumlu editör (M2 kuralı). Her kitapta bir «profil» kaydı; her alanın kaynağı ve
onaylayanı belli. Yeni kart açıldığı gece taslak hazır; editör sabah onaylar; fark listesi CRM ekibine gider; bir
sonraki gece T-soft okumasıyla sitede görünüp görünmediği kontrol edilir.

**Bir iş günü (metadata müdürü):**
- 09:00 Özet ekranı: dün açılan kartlar ve taslakları, onay bekleyen profiller (editör bazında), yeni çıkan
  tutarsızlıklar, sitede yanlış kategoride görünen satıştaki kitaplar.
- 09:30 Kuyrukta «son 24 ayda en çok satan, kategorisi çelişkili» süzgeci; kuyruğun ilk sayfasını profil ekranında tek
  tek onaylar, bir kısmında kategoriyi düzeltir (her düzeltme ölçüm verisine döner).
- 11:00 Ağaç: «Kişisel gelişim > Mindfulness» alt kategorisi önerisi; etki önizlemesi: kaç kitap taşınır, M2'de hangi
  editöre düşer, T-soft'ta karşılığı var mı. Taslak olarak kaydeder, yayın yönetmenine gönderir.
- 14:00 Zeki AI'ya: «Çocuk 6–10 yaş öyküde son 12 ayda satışı düşen kitaplar hangileri, kategorileri doğru mu?»
- 16:00 CRM'e işlenecek fark listesini indirir, katalog sorumlusuna iletir.
- 17:30 Haftalık tamlık grafiği: satıştaki kitaplarda tek onaylı kategori oranı.

**«Bunu görürsem hemen kullanırım»**
1. Bir kitabın bütün sınıflamaları (CRM'deki yedi sistem + site) tek satırda, çelişen olanlar kırmızı.
2. Öneri + kaynak alıntı + olasılık; düşük olasılıkta «emin değilim» diyen dürüst ekran.
3. Ağaç değişikliğinde etki önizlemesi (kitap, editör kuralı, site kategorisi).

**«Bunu yaparsanız kullanmam»**
1. Modelin ağaçta olmayan kategori ya da serbest etiket uydurması; etiket sözlüğünün şişmesi.
2. Onaysız toplu değişiklik ya da CRM/siteye sessiz yazma.
3. 9 bin kitabı sırasız, önceliksiz kuyruğa dökmek; ya da kısmi onaya izin vermemek.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (tablo/görünüm/ölçü) | CRM (varlık/alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Katalog okuma | `LG_411_ITEMS` (CODE, NAME, SPECODE=yayınevi) — eşleşme denetimi | `new_kitapBase` künye alanları, `statecode`, `new_Tip` | — | Kayıt ve kimlik deterministik |
| Mevcut sınıflamaların toplanması | — | `new_kitaplikid`, `new_diziid`, `new_yayineviid`, `new_turlertext`, `new_webkategorileritext`, yaş/sınıf alanları, N:N tablolar (ürün kategorisi, raf, sergilenecek, tema, anahtar kelime, kavram, ders) | — | Okuma ve birleştirme SQL ile |
| Tutarsızlık tespiti | — | aynı alanlar | Yalnız metinsel çelişkide (özet ile kategori uyuşmuyor mu?) kapalı küme karar: «uyumlu / çelişkili / belirsiz» | Kurallar deterministik; model yalnız kuralın göremediği anlam farkında |
| Kategori önerisi | — | künye + `new_ozet` + `new_kitapspotu` + anahtar kelimeler + mevcut Kitaplık | Ağaçtaki aday düğümler arasından **tek token + olasılık** ile seçim (seçenekler A, B, C… harf etiketli); düşük marj → «belirsiz» | Kapalı küme; uydurma kategori imkânsız |
| Yaş / tür / hedef kitle | — | `new_hedefkitle`, yaş alanları, `new_turlertext` | Beyan boşsa ya da çelişkiliyse kapalı küme seçim; beyan varsa beyan kazanır (editör motorundaki kural) | Yayınevinin beyanı esastır |
| Tema ve etiket | — | `new_temaBase`, `new_anahtarkelimeBase` sözlüğü | Sözlükteki her aday için evet/hayır (tek token + olasılık); sözlük dışı etiket ayrı «yeni etiket önerisi» kuyruğuna | Kontrollü sözlük |
| Kısa özet, motto | — | `new_ozet`, `new_kitapspotu`, `new_kitabinenonemlicumlesi` | Taslak metin; motto metinde birebir aranır, bulunamazsa düşer | Metin üretimi gerçek değer; doğrulama deterministik |
| Karakter, ritim | — | — | Editör motorunun ürettiği kayıt okunur (köprüden vekil); köprü yeniden üretmez | Çift iş yapılmaz |
| Timaş emsal | `LG_411_01_STLINE` + `LG_211_01_STLINE` son 24 ay: net adet (Σ AMOUNT satış − iade), net ciro (Σ LINENET), faturalı satır (`INVOICEREF <> 0`, `CANCELLED = 0`, `LINETYPE = 0`, TRCODE 7/8/9 − 2/3); ölçü `yayinevi_performans` | aynı düğüm + hedef kitle + yaş | Rakam üretmez; «neden emsal» gerekçe cümlesi | Rakam SQL'den; model yorum |
| Rakip emsal | — | `new_rakipkitapBase` (ad, yazar, yayınevi, kategoriler) | Ad/yazar normalizasyonu sonrası belirsiz eşleşmede «aynı kitap mı» kapalı küme | Eşleştirme |
| Doğal dil soru | Katalogdaki ölçüler (net_ciro, yayinevi_performans) | Ağaç tabloları (portalın) | Mevcut soru hattı (NL → SQL); cevap metni | Var olan hat |

Model çağrıları: köprü içinde `rt.llm_for("categories", BATCH)` (toplu öneri gece), etkileşimli yeniden üretimde
`rt.llm_for("categories")`. `LlmClient` doğrudan kurulmaz. Köprüdeki `QueuedLlm.chat` bugün yalnız metin döndürüyor;
kapalı küme + olasılık için `apps/editor/src/editor/llm.py` → `choose()` desenindeki (`structured_outputs.choice`,
`logprobs`, `top_logprobs`) çağrı köprünün kapısına eklenmeli (`backend/semantic_layer/runtime/llm_queue.py`, yeni
`QueuedLlm.choose()`; sıra ve slot kapıdan geçer). Bu, H2–H4 için de ortak ihtiyaçtır; ayrı küçük iş olarak önce yapılır.

## 14. Kodlama planı (kodlayıcıya devir)

**Köprü dosyaları**
- `backend/semantic_bridge/categories.py` — depo: tablolar, ağaç sürümü, profil durumu, kurallar.
- `backend/semantic_bridge/categories_sources.py` — CRM okuma (künye + sınıflamalar, `ModifiedOn` deltası), Logo satış
  (yıl → firma eşlemesi `budget_sources.py`'deki gibi `L_CAPIPERIOD`'dan), T-soft kategori (SEO deposundan; yoksa
  `seo_geo/connections.py` salt okuma istemcisi).
- `backend/semantic_bridge/categories_propose.py` — model çağrıları (kapalı küme seçim, özet taslağı), kanıt doğrulama.
- `backend/semantic_bridge/categories_api.py` — `register(app, rt, require_caller, can)` (bütçe modülündeki desen),
  `app.py`'de iki satırla bağlanır.

**Tablolar (bi_meta Postgres, ilk kullanımda kurulur; hepsinde `tenant_id`)**
- `semantic_category_trees` — `id`, `version`, `status` (taslak|onay-bekliyor|yururlukte|arsiv), `created_by`,
  `approved_by`, `approved_at`, `note`.
- `semantic_category_nodes` — `id`, `tree_id`, `parent_id`, `level` (yayinevi|ana|alt|altalt|web), `name`, `code`,
  `sort`, `status`.
- `semantic_category_mappings` — `node_id`, `system` (crm_kitaplik|crm_urunkategorisi|crm_raf|crm_sergilenecek|
  tsoft|konu_standardi|marka), `external_id`, `external_name`, `approved_by`.
- `semantic_book_profiles` — `book_id` (CRM `new_kitapId`), `stock_code`, `isbn`, `status`
  (yok|taslak|kismi|onayli|red), `fields_json` (alan → {deger, kaynak, olasilik, onay}), `crm_snapshot_json`,
  `priority_score` (son 24 ay net adet), `model_call_ids`, `updated_at`.
- `semantic_book_profile_events` — `book_id`, `field`, `old`, `new`, `action` (oneri|kabul|duzeltme|ret), `user`,
  `at` (eğitim/ölçüm verisi de budur).
- `semantic_category_findings` — `book_id`, `rule_key`, `detail_json`, `status` (acik|duzeltildi|yoksay), `first_seen`,
  `last_seen`.
- `semantic_category_rules` — `rule_key`, `label`, `enabled`, `params_json` (kurallar ekrandan açılır/kapanır).
- `semantic_tag_vocabulary` — `tag`, `source` (crm_anahtarkelime|onayli|oneri), `status`, `merged_into`.

**Uçlar (`/api/v1/categories/*`)**
- `GET overview` — sayaçlar, doluluk, kuyruk özeti.
- `GET tree` · `GET tree/versions` · `PUT tree` (taslak) · `POST tree/submit` · `POST tree/approve` ·
  `GET tree/impact?draft=` (etki önizlemesi).
- `GET mappings` · `PUT mappings`.
- `GET books?filter=&owner=me&order=priority` · `GET books/{book_id}` (mevcut + öneri + kanıt).
- `POST books/{book_id}/propose` · `POST books/{book_id}/decision` (alan alan kabul/düzeltme/ret).
- `GET findings` · `POST findings/{id}/status`.
- `GET crm-diff` · `GET crm-diff/export.xlsx` (dışa aktarım anahtarı).
- `POST run-due` (SİSTEM; zamanlayıcı).
- Sözleşme uçları (diğer modüller okur): `GET profile/{stock_code}`, `GET nodes/{node_id}/books`.

**Ekranlar** `src/canvas/categories/`: `CategoriesHome.tsx` (özet), `ProfileQueue.tsx`, `BookProfile.tsx`,
`TreeEditor.tsx`, `Findings.tsx`, `CrmDiff.tsx`, `api.ts`. Rota `/timas/kategori-agaci` (+ `/kategori-agaci/kitap/:id`,
`/kategori-agaci/agac`, `/kategori-agaci/tutarsizlik`). Menü: `navModel.ts` → «Kayıtlar» alanı, öğe
`{ id: 'kategori-agaci', label: 'Kategori ağacı', to: '/kategori-agaci', hint: 'Kitap profili, kategori mimarisi ve
tutarsızlıklar' }`. Kampüs: modül kutusu (Hazırlıklar) + zilde «onay bekleyen profil» sayısı.

**Yetki** (`access_catalog.json` + `access.py`)
- Sayfa: `sayfa:kategori-agaci`; `RULES`: `("/api/v1/categories/run-due", SYSTEM)`, `("/api/v1/categories/",
  frozenset({page("kategori-agaci")}))`; sözleşme uçları M1/M2/SEO sayfa anahtarlarını da kabul eder.
- Özellik: `ozellik:kategori.oneri-uret` (POST propose), `ozellik:kategori.agac-duzenle` (PUT tree, PUT mappings),
  `ozellik:kategori.herkesinki` (kapsam), açıkça verilen: `ozellik:kategori.profil-onay`, `ozellik:kategori.agac-onay`
  (uç içinde denetlenir; ağacı gönderen onaylayamaz). Dışa aktarım: mevcut `ozellik:veri.disa-aktar` desenine
  `categories/crm-diff/export\.xlsx` eklenir.

**Zamanlayıcı** `scripts/server/timas-categories.{service,timer}` — her gece 03:40: CRM kitap kartlarında
`ModifiedOn` deltası, yeni kart → profil taslağı kuyruğa (model önceliği BATCH), tutarsızlık kurallarını yeniden koşar,
öncelik puanını (Logo) günceller. Pazar gecesi tam tur (delta kaçaklarına karşı).

**Kabul testleri (gerçek veri, doğrudan SQL; CRM .28, Logo .155 ayrı sorgu)**
1. Katalog sayacı: `SELECT COUNT(*) FROM Timas_MSCRM.dbo.new_kitapBase WHERE statecode = 0 AND new_Tip = 1;` =
   özet ekranındaki «aktif kitap» (2026-09-24'te 9.091).
2. Kitaplık doluluğu: `SELECT SUM(CASE WHEN new_kitaplikid IS NOT NULL THEN 1 ELSE 0 END) FROM
   Timas_MSCRM.dbo.new_kitapBase WHERE statecode = 0 AND new_Tip = 1;` = doluluk çubuğundaki sayı.
3. Ürün kategorisi bağlı kitap: `SELECT COUNT(DISTINCT u.new_kitapid) FROM
   Timas_MSCRM.dbo.new_new_urunkategorisi_new_kitapBase u JOIN Timas_MSCRM.dbo.new_kitapBase k ON k.new_kitapId =
   u.new_kitapid WHERE k.statecode = 0 AND k.new_Tip = 1;` = ekrandaki «ürün kategorisi var».
4. Tutarsızlık kuralı «yetişkin kitabı çocuk web kategorisinde»: `SELECT COUNT(*) FROM Timas_MSCRM.dbo.new_kitapBase
   WHERE statecode = 0 AND new_Tip = 1 AND new_hedefkitle = 3 AND new_webkategorileritext LIKE N'Çocuk;%';` = bu kuralın
   açık bulgu sayısı.
5. Tema bağı: `SELECT COUNT(*) FROM Timas_MSCRM.dbo.new_new_kitap_new_temaBase;` = ekrandaki tema bağ sayısı.
6. Öncelik puanı (tek kitap, 2026 kısmı): `SELECT SUM(CASE WHEN s.TRCODE IN (7,8,9) THEN s.AMOUNT ELSE -s.AMOUNT END)
   FROM LG_411_01_STLINE s JOIN LG_411_ITEMS i ON i.LOGICALREF = s.STOCKREF WHERE i.CODE = '<stok kodu>' AND
   s.CANCELLED = 0 AND s.LINETYPE = 0 AND s.INVOICEREF <> 0 AND s.TRCODE IN (2,3,7,8,9);` + aynı sorgu `LG_211_01_*`
   üzerinde son 24 ayın 2025'e düşen kısmı (`DATE_` süzgeci) = profildeki «son 24 ay net adet».
7. Onay izi: portalda onaylanan 10 profilin her alanı için `semantic_book_profile_events`'te kullanıcı ve zaman var;
   `admin.audit` kaydı var.
8. Uydurma kategori yok: bütün `semantic_book_profiles.fields_json` kategori değerleri yürürlükteki ağacın düğümü
   (`semantic_category_nodes`) — SQL ile sıfır istisna.

**Bağımlılık**
- Önce: köprü LLM kapısına kapalı küme + olasılık çağrısı (`QueuedLlm.choose`) — S; H1–H4 ortak.
- H1 başka modülü beklemez; H2 ve H3 «ilgi alanı» için H1'in ağacını kullanır (H1 bitmeden CRM Kitaplık/tür ile
  başlayabilirler). Paralel kodlanabilir.
- SEO modülünün T-soft eşitlemesi (var) okunur.

**Tahmini büyüklük:** L (toplam). Parçalar: kaynak okuma + özet + doluluk M; ağaç editörü + sürüm/onay M; öneri +
onay kuyruğu + profil ekranı L; tutarsızlık kuralları S; CRM fark listesi S; zamanlayıcı S.
