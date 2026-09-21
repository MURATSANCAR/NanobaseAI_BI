# Finansal Denetim — kaynak, uygulama ve kabul kapsamı

## Ürün

Finans & Risk → Finansal Denetim, `/timas/finansal-denetim`.
Mevcut kanvas kabuğu, açık renkli cam yüzeyler, mor/mercan vurgular.
Beş görünüm: denetim özeti, kontrol kütüphanesi, Logo kayıtları, dayanak veriler ve kaynak belge.
Rapor JSON olarak mevcut hesaplama, kaynak hash'i, sürüm, kapsam ve sınırlamalarla indirilir.
Kontrol kataloğu ayrıca indirilebilir. Hiçbir işlem Logo'ya yazmaz.

## Kaynak ve tamlık

Kullanıcının verdiği `zirve denetim .pdf`, 241 sayfa, 12 Haziran 2020,
“Elektronik Defter Denetimi Analiz Dokümanı — ERPDENET”.
SHA-256: `39ff5b294a1a62ade786228980251d14ab691820c6d16fb7fc677a1fe21039b3`.

Belgedeki “yazılımcı için not” ifadeleri kaynak verisidir, çalıştırma talimatı değildir.
`scripts/extract-financial-audit.py` tüm sayfaların metnini ve sayfa kökenlerini
`configs/financial-audit/source.json` içinde korur. Kaynak belge metni herkese açık
arayüz paketine gömülmez; oturum/caller korumalı `/api/v1/financial-audit/catalog` üzerinden okunur.
Kaynakta 169 not oluşumu vardır (not 1 veri yapısı açıklamasıdır).
Başlık ayrıştırıcısının tarih/tutarları başlık sanması ve bazı numaraları atlaması düzeltildi.
649 çalışma kaydı bulunur: 41 analiz notu, 127 kontrol notu, 212 numaralı inceleme
maddesi ve 269 bölüm metni paketi. Bölüm paketleri numarasız açıklamaları da kapsar.
Bunlar **649 bağımsız, doğrulanmış iş kuralı değildir**: paketlerle alt maddeler örtüşür,
bir not birden fazla kontrol içerebilir. Atomik çıkarımın ve bütün PDF iş doğruluğunun
kabulü hâlâ **DOĞRULANAMADI**; kayıt sayısı başarı oranı olarak kullanılamaz.
Katalog `DRAFT_REQUIRES_REVIEW`, `completeControlCoverage=false` taşır.

Özgün kaynak korunur; uygulanan formül ve düzeltme gerekçesi ayrıca gösterilir:

- Not 88 yok. Not 115 üç, 143 ve 160 ikişer kez geçiyor. Kimlikler oluşum sırasını içerir.
- s.60–61 / not 49: senet kontrolünün açıklamasında çek kodu yazıyor.
- s.47 / not 16–17 ve s.51 / not 25: maddi duran varlık başlığı altında 24 kullanılıyor.
- s.56 / not 36: brüt satış kârı formülünde satış indirimleri düşülmemiş görünüyor.
- s.57 / not 39: faaliyet giderleri başlığında 65 yazıyor.
- s.58 / not 41–42: finansman gideri paydası 660−661 yazıyor.
- s.65 / not 51 ve s.131 / not 119: eski parasal eşikler güncel mevzuat kabul edilmez.
- Devir hızlarındaki 360 gün ve sektör eşikleri dönem/politika parametresi olarak ayrıca onaylanmalı.

## Gerçek kaynak

Tek şirket; teknik kaynak numaraları şirket seçimi değildir.
`configs/semantic/knowledge/logo/coverage.yml` içindeki beyanla 2026 kaynağı seçilir.
İlk sürüm yalnız 2026 işlem dönemine açıktır. 2021–2025 kopyaları eklenmeden
açılış/kapanış ve örtüşen kayıt kuralları doğrulanmalıdır.
Bağlı Logo SQL: `.155 / LOGO_DB`; gerçek test sunucusu üzerinden erişilir.
İlk salt okunur ölçüm: 246.404 hareket, 379 hareketli hesap, son kayıt 17.08.2026.
Arayüzde yedek ve son veri tarihi görünür; güncel Eylül verisi gibi sunulmaz.

## Uygulanan hesaplamalar

`backend/semantic_bridge/financial_audit.py`, gerçek köprünün `/api/v1/financial-audit/*`
uçları. Mevcut çağıran/portal yetkilendirmesini kullanır. SQL kataloğa doğrulatılır,
dönem aktarılır, kesilmiş sonuçtan başarı üretilmez. Ortak kilit ve 120 saniyelik
önbellek aynı ağır sorgunun paralel kopyalarını engeller. SQL, kod hash'i ve zaman rapordadır.

Canlı kabulde FAYEAR sorgusunun ortak katmanda yanlışlıkla 211 yedeğine yönlenip
2026 için boş döndüğü yakalandı. Denetim sorguları mevcut `scope={n0:411}` desteğiyle
2026 fiziksel kopyasına bağlanır; yürütmeden önce ve yanıtta başka yedek kimliği
bulunursa 409 ile reddedilir. Bu bir şirket seçimi değildir. Test referansı aynı
sabit kaynakta bağımsız sorgudur. E-defter ödeme tipi grupları kaynak veritabanının
`SQL_Latin1_General_CP1254_CI_AS` karşılaştırmasıyla büyük/küçük harf varyantlarını
birleştirir; bağımsız satır referansı bu Türkçe karşılaştırmayı korur.

| Kontrol | Kapsam |
|---|---|
| Mizan eşitliği | Net borç/alacak farkı; 0,01 TL tolerans |
| Fiş eşitliği | Fiş başına ayrı borç/alacak dengesi |
| Kasa/çek ters bakiyesi | Yalnız kaynakta açık tanımlı 100/101 alt hesapları |
| Hesap bağlantısı | ACCOUNTREF → EMUHACC |
| Eksik tutar | NULL DEBIT veya CREDIT |
| Fiş bağlantısı | ACCFICHEREF → EMFICHE |

**Canlı keşif nedeniyle yapılan düzeltme:** 379 kartın 374'ünde ACCTYPE=0,
5'inde ACCTYPE=2; gelir ve borç hesapları da borç karakterli işaretlenmiş.
Bu alanı muhasebe karakteri kabul eden ilk sürüm 98 yanlış/şüpheli aday üretti.
Bu sonuç geçersizdir; son sürüm yalnız 100/101 için kaynak tanımını kullanır.
Diğer hesaplarda karakter kontrolü tamamlanmış sayılmaz.

41 analiz notunun tamamına formül, hesaplanabilirlik koşulu ve ilgili Logo hesaplarına
doğrudan geçiş bağlandı. Gelir tablosu oranlarında mükerrer sonuç yaratacak 690/692
devir hesapları hesaplamaya katılmaz. Açılış ve dönem
hareketleri ayrıdır. Maddi duran varlıklarda 25; faaliyet giderlerinde 63; brüt kârda
net satışlardan maliyet düşümü; finansman giderinde 660+661 kullanılır. Devir süresi
2026-01-01–2026-08-17 arasındaki 229 takvim günüyle hesaplanır; 360 güne otomatik yıllıklaştırılmaz.
Stok devir hızının ticari mal ve mamul alt hesapları ayrı tutulur. Önceki kapanış
mutabakatı olmayan açılış ortalaması üzerinden doğrulanmış devir hızı verilmez.

17 oran hesaplanabilir; 24 oran payda, kapanış, maliyet yansıtması veya net vergi sonucu
önkoşulları nedeniyle engellenir. 7 grubu açıkken gelir tablosu kârlılık oranları
geçmiş sayılmaz. Pay ve payda gözlemleri görünür, engelli sonuçta oran değeri boştur.
Sektör yeterliliği/başarı/başarısızlık hükmü üretilmez.

`financial_audit_rules.py` her kaynak oluşumuna durum, hesap kapsamı, Logo hesap
kimlikleri, gözlem, gereken kanıt ve kaynak düzeltmesini bağlar. `ACCTYPE` kullanılmadan
açık hesap yönü tablosuyla alt hesap ters bakiye **gözlemi** çıkarılır; bu gözlem işlem
niteliğinin veya tüm notun doğrulandığı anlamına gelmez. Alıcı/satıcı ve reeskont
hesapları birbirinden kopyalanmaz. Tarih, belge numarası ve döviz alanlarının ham profil
sayıları raporda kalır; e-defter XML anlamı doğrulanmış gibi kullanılmaz.

İkinci kaynak keşfinde `LG_411_01_EBOOKDETAILDOC` ile `LG_411_FAYEAR`/`FAREGIST`
bulundu; e-defter alanlarının yalnız EMFLINE içinde arandığı ilk kapsam genişletildi.
Belge yok/ödeme yok bayraklarıyla eksik alan gözlemi, fişte birden fazla tür ve
belge–hesap ilişkileri çalışır. Başlık belgesi bütün fişe, satır belgesi yalnız kendi
satırına bağlanır; ilişki tekilleştirilerek tutar/sayı çoğalması önlenir.
`/documents` gerçek belge tarihi/numarası/tür kodu/ödeme şekli/fiş-satır kimliğini
sayfalı döndürür. Tür kodları henüz sürüm sözlüğüyle kabul edilmediği için otomatik
fatura/çek/senet uygunluk sonucu verilmez.

Sabit kıymet cetveli yıl/grup/yöntem/ay bazında ayrı gösterilir; gruplar birbirine
eklenmez, birikimli amortisman alanları aylardan toplanmaz. `LOCFIGS2_PERDDEPR`
kaynak dönem tutarı olarak gösterilir; yöntem, varlık hesabı ve mevzuat kabulü değildir.
Destek kaynağı okunamazsa `unavailableDatasets` ve `unverified` döner; ana mizanın
sonuçları kaybolmaz, belgesel kontrol geçmiş sayılmaz.

20 ayrı aynı-fiş karşı hesap gözlemi tek toplulaştırılmış sorguyla hesaplanır:
karşılık/654, stok/üretim yansıtmaları, tahakkuk/gelir, sermaye/banka.
Açılış fişleri hariçtir. Karşı hesap görünmemesi yalnız inceleme adayıdır;
7/A–7/B, alış/satış/iade, ayni sermaye ve dönemleme belgesi ayrıca gerekir.
Aylık 190/191/391 birikimli bakiyeleri ayrı ayrı sunulur. Ay/yıl sonu onayı yokken
bakiye bulunması otomatik vergi hatası sayılmaz. Yıl sonu notları Ağustos yedeğinde
`not_due` taşır.

Her rapor özel dizinde değişmez JSON olarak saklanır. `/runs` son 30 raporu listeler;
`/runs/{id}` aynı hesaplama sonucunu döndürür. `/runs/{id}/reviews/{controlId}` sorumlu,
not, kanıt referansı, aktör ve sürümlü geçmişi tutar. Optimistic concurrency ve dosya
kilidi çakışan güncellemeyi 409 ile reddeder. `passed` manuel durum değildir;
kanıt eklemek otomatik sonucu değiştirmez. Yazılanlar yalnız çalışma kâğıtlarıdır,
Logo verisi değildir. Dosyalar servis kullanıcısına özel 0700 dizin/0600 dosyalardadır:
`/data/nanobaseai/bi/var/financial-audit/workpapers` (`FINANCIAL_AUDIT_DATA_DIR` ile değişebilir).

Detay: hesap seçimi → sayfalı Logo hareketleri; tarih, fiş/belge no, borç, alacak,
açıklama, fiş/satır kimliği. Detay ayrı okuma olarak etiketlidir; özetin aynı
yürütmesiymiş gibi sunulmaz. İptal hareket/fişler mali kapsam dışında tutulur;
eksik fiş bağlantısı ayrıca raporlanır. Boş veya eksik kapsam olumlu kabul edilmez.

## İlave öneriler / henüz uygulanmayanlar

- Dönemsel mevzuatın bütün maddeler için etkin tarihli, uzman onaylı kural sürümüne dönüştürülmesi.
- Mükerrer fatura/ödeme, alış-satış/cari/genel muhasebe mutabakatları.
- Dönem kesimi, geriye tarihli kayıt, olağandışı tutar ve hareketsiz bakiye kontrolleri.
- Sorumlu, açıklama, belge referansı ve inceleme geçmişi mevcut; hedef tarih, yeniden kontrol ve yetkili kapanış henüz yok.
- Risk tutarının fiş/satır kimliğiyle tekilleştirilmesi; aynı tutarı farklı kontrollerde toplamamak.
- Kalıcı rapor mevcut; önceki dönem farkı ve düzeltilen/yeni bulgu karşılaştırması henüz yok.
- Beyanname, banka ekstresi, mutabakat ve fiili sayım belgelerinin ayrı kanıt olarak alınması.
- Vergi cezası/uygunsuzluk sonucunun dönemsel hukuki dayanak ve uzman incelemesi olmadan üretilmemesi.
- JSON dışa aktarımı var; PDF/Excel çalışma kâğıdı, ikili dosya eki ve otomatik zamanlama henüz yok.

## Kabul

Yerel test çalıştırılmadı. Derleme `nanobase-direct` üzerinde yapıldı.
Gerçek HTTP cevabı bağımsız gerçek DB sorgusuyla `scripts/server/financial-audit-acceptance.py`
üzerinden karşılaştırıldı. Son sürümde **144/144 teknik karşılaştırma geçti**; başarısız
karşılaştırma yok. Nihai sürüm hashleri ve çalışma kâğıdı geçmişi dahil son kabul
`docs/audits/financial-audit-2026-09-21/acceptance.json` dosyasında tutulur.
Bu sayı bütün PDF'nin ürün kabulü değildir. Test listesi tüm hesap kimlikleri/tutarları,
41 oran tanımı ve hesap engelleri, açılış/dönem ayrımı, 20 karşı hesap gözlemi,
8 aylık KDV bakiyeleri, e-defter belge grupları ve ayrıntıları, sabit kıymet cetvelinin
54 grubu, oranların Logo hesap bağlantıları, gerçek detay/sayfalama, arşiv eşitliği,
inceleme geçmişi/çakışma kontrolü ve yetkisiz erişimi kapsar. Tam hesap ve belge satırları
özel sunucu kanıtında tutulur; depodaki kanıt kimlik/hash, sayım ve kontrol statülerini içerir.

Gerçek kaynakta temel 6 kontrolden 5'i geçti, kasa/çek kontrolünde 2 hesap inceleme adayı
bulundu (277.109,33 TL; zarar/ceza değildir). Kaynak çalışma kayıtlarında 17 hesaplandı,
24 doğrulanamadı, 597 kanıt bekliyor, 6 dönemi gelmedi, 3 inceleme adayı ve 2 muhasebe
gözlemi vardır. Bu sayılar örtüşen paketleri içerir; toplanmış risk veya başarı oranı değildir.
Önceki ACCTYPE temelli 98 aday sonucu kullanılmaz.

### Mevzuat doğrulamasının sınırı

GİB'in [Nisan 2026 tevsik bilgilendirmesi](https://cdn.gib.gov.tr/api/gibportal-file/file/getFileResources?objectKey=arsiv%2Fyardim-kaynaklar%2Finfografikler%2Fpdfs%2Fmal-hizmet-tevik.pdf)
30.000 TL eşiğini belirtir; [459 Sıra No.lu tebliğ](https://gib.gov.tr/mevzuat/kanun/434/teblig/7953)
ile birlikte referans olarak saklanır. Kasa satırına bakarak ceza hesaplanmaz.
[GİB'in örtülü sermaye açıklaması](https://gib.gov.tr/mevzuat/kanun/435/ozelge/28381)
dönem başı özsermaye ve ilişkili kişi borçları ayrımını destekler; özelge tüm işlemler için
bağımsız uygunluk onayı değildir. PDF'deki bütün vergi oranları/istisnaları için güncel
mevzuat kabulü yapılmış değildir.

Mevcut Chrome oturumu üzerinden gerçek portal ekranı doğrulandı; kullanıcıdan ek
parola/oturum gerekmedi. Özet, kontrol ayrıntısı/inceleme formu, Logo hareketleri,
e-defter/sabit kıymet tabloları ve kaynak metin 320/390/768/1440 genişliklerinde
sayfa taşması göstermedi; geniş tablolar yalnız kendi kapsayıcılarında kayıyor.
Logo kasa hesabında 50'şer hareketlik iki sayfa, e-defterde iki belge sayfası,
kasa filtresi (1.090 belge), kaynak 41→42 sayfa geçişi çalıştı. Gerçek inceleme
notu portal kullanıcısı ve zamanıyla saklandı; kontrol sonucu otomatik geçmedi.
Tarayıcı kanıtı: `docs/audits/financial-audit-2026-09-21/browser.json`.

JSON indirme düğmesi çağrıldı, ancak tarayıcı indirme olayı zaman aşımına uğradı;
indirme yöneticisi sayfası tarayıcı URL politikasıyla engellendi. İndirilen dosyanın
istemcide tamamlanması **DOĞRULANAMADI**; arşiv/API cevap eşliği bunun yerine geçmez.
Müşteri VM'inde kurulumu ve gerçek kullanıcı kabulü ayrıca doğrulanmadan üretime hazır denmez.
