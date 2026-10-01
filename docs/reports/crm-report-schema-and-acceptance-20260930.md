# CRM raporları: kaynak envanteri ve bağımsız kabul

2026-09-30 itibarıyla yeni CRM raporlarının fiziksel alanları ve yayımlanmış ilişkileri,
eski semantik kataloğa başvurmadan doğrudan bağlı `Timas_MSCRM` metadata kaynağından
incelendi. Bu belge **canlı API kabul sonucu değildir**. Kabul koşucusu hazırdır;
bu çalışma sırasında ürün testi veya dağıtım yapılmamıştır.

## 1 Ekim: metadata ile hesap kapsamını ayıran düzeltme

Paralel kod incelemesinde aktif sözleşme tarafının kişi/kurum bağlantısı
çözülemediğinde bazı raporlarda taraf listesinin sessiz eksilebildiği bulundu.
`5b68f9546` sürümünde `contract_author_roles`, `contract_expiry` ve
`contract_revision_evidence`, yalnız çıktıya giren ilgili sözleşmeler için
`INCOMPLETE_SOURCE_COVERAGE` bildirir. Pasif kişi/kurum bilgisi açılmaz;
dönem veya çıktı dışındaki eksiklikler sonucu kısmi yapmaz.

Bağımsız kabul referansı mevcut LEFT JOIN anti-join sorgusuyla bu eksikliği
ayrı denetler; özel kapsam gap'i ve API ile saklanan tam sonuçta
`sourceComplete=false` zorunludur. Başka bir tarihçe açıklaması bu kontrolün
yerine geçmez. Plan kaynaklı açık boşluklar da bölümün kapsam durumuna taşınır.
Yeni tablo veya alan eklenmedi: **31 tablo / 161 alan** metadata kapsamı aynıdır.
5b68f9546 sürümünün CR024 gerçek API kontrolünde 999 satır bağımsız
referansla eşleşti; anti-join gerçek eksik aktif taraf bağını buldu ve yeni
özel gap/API+saklanan sonuç sourceComplete=false kontrolü geçti
(**BOUNDARY_PASS**, tam cevap değildir). Diğer ilgili senaryoların koşusu
sürüyor; sonraki planlayıcı değişiklikleri yeniden kabul gerektirir.

## Tam envanter

Test sunucusundaki kanıt:

`/tmp/codex-crm-full-inventory-20260930-r2.json`

SHA256: `ee26a27cc48bd6fa7d5d631453d4a75025c61517705e2602ea0927e341fe9a8e`

| Metadata kümesi | Satır sayısı |
| --- | ---: |
| Fiziksel tablo/görünüm | 3.081 |
| Fiziksel kolon | 90.399 |
| Benzersiz indeks/PK kolon kaydı | 2.105 |
| Fiziksel yabancı anahtar kolon ilişkisi | 1.922 |
| Yayımlanmış entity/etiket kaydı | 873 |
| Yayımlanmış alan/etiket kaydı | 31.199 |
| Yayımlanmış metadata ilişkisi | 11.767 |
| Türkçe durum/sebep etiketi | 2.128 |

Kitap, eser katılımı, kişi, müşteri, görev/randevu, sözleşme ve kapsam varlıklarından
başlayan ilişki grafiğinin bağlı kapanışı 840 mantıksal varlıktır. Bu geniş kapanış,
ortak kullanıcı/organizasyon ilişkilerini de içerir; bütün varlıkların iş anlamının
doğrulandığı veya bütün tablolardan iş verisi okunduğu anlamına gelmez.

Envanterde her tablo için `tableCoverage` satırı bulunur: raporda kullanılan,
tarihçe kanıtı gereken, ilişkili fakat henüz rapora bağlanmayan veya yalnız envantere
alınmış. `statecode`/`statuscode` varlığı ve kapsam gerekçesi saklanır.
`reportTableBindings` rapor ailesi–fiziksel tablo eşlemesini verir. Gerekli tablolarda
eksik tespit edilmemiştir. İlk statik alan çapraz kontrolünde 23 tabloya ait 115 alan
fiziksel envanterle eşleşmiştir; bu kontrol SQL/API kabulünün yerine geçmez.

Envanter sorguları yalnız metadata okur (`sourceWrites=0`, `businessRowsRead=0`).
`AuditBase` için `TOP (0)` okuma yetkisi ayrıca doğrulanmıştır.

## Genişletilmiş statik kapsam kontrolü

İlk **23 tablo / 115 alan** kontrolü sabit tablo çağrılarına aitti. Sonraki
kontrol, `crm_reports.py` içindeki sabit çağrılara dört dinamik hak/dil/bölge/ülke
N:N ve sözlük çiftini, yeni revizyon/protokol alanlarını ve WHERE/aktiflik
koşullarının alanlarını ekledi: **31 fiziksel tablo / 161 farklı tablo–kolon
çifti**. Aşağıdaki harita bu genişletilmiş kapsamın tamamıdır; aynı kolon adı
farklı tablolarda ayrı sayılır.

Karşılaştırma, mevcut `/tmp/codex-crm-full-inventory-20260930-r2.json` dosyası
üzerinden yapıldı. Dosyanın SHA256 değeri yeniden okunarak doğrulandı:
`ee26a27cc48bd6fa7d5d631453d4a75025c61517705e2602ea0927e341fe9a8e`.
Büyük/küçük harften bağımsız **eksik tablo/alan: 0**. Tam harf yazımıyla beş
fark vardır: `new_kitapBase.new_stokkodu`, Account/Contact `statecode` ve
`statuscode` başlıkları. Bunlar eksik alan değildir; mevcut SQL ve şema
kontrolünün harf duyarsız karşılaştırması kapsamında eşleşir. Harita kodda
kullanılan yazımı korur.

31/161 sayısı raporun iş verisi kaynaklarını kapsar; ortak executor içindeki
`INFORMATION_SCHEMA.COLUMNS`, durum etiketi için `StringMapBase` ve
`MetadataSchema.Entity` metadata okumaları bu sayıya dahil değildir. Envanterdeki
3.081 tablo/görünümün tüm alanlarının rapor tarafından kullanıldığı iddia edilmez.

Bu işlem **metadata ve statik kaynak kapsamı kontrolüdür**: yeni iş verisi
sorgusu veya ürün koşusu açılmadı. SQL'in çalıştığını, hesapların doğru olduğunu,
31 raporun API kabulünden geçtiğini veya tüm CRM varlıklarının iş anlamının
çözüldüğünü göstermez. Yayımlanmış ilişkilerin varlığı, sözleşme hukuki önceliği
ya da eski/yeni audit değerlerinin çözüldüğü anlamına gelmez.

| Kullanılan fiziksel tablo | Alan sayısı | Kontrol edilen alanlar |
| --- | ---: | --- |
| `AccountBase` | 9 | `AccountId`, `CreatedOn`, `ModifiedOn`, `Name`, `PrimaryContactId`, `TerritoryId`, `new_VergiNo`, `statecode`, `statuscode` |
| `ActivityPartyBase` | 4 | `ActivityId`, `IsPartyDeleted`, `PartyId`, `PartyObjectTypeCode` |
| `ActivityPointerBase` | 10 | `ActivityId`, `ActivityTypeCode`, `CreatedOn`, `OwnerId`, `RegardingObjectId`, `RegardingObjectTypeCode`, `ScheduledEnd`, `ScheduledStart`, `StateCode`, `Subject` |
| `ContactBase` | 12 | `ContactId`, `CreatedOn`, `EMailAddress1`, `FullName`, `MobilePhone`, `ModifiedOn`, `ParentCustomerId`, `ParentCustomerIdType`, `Telephone1`, `new_yazarmi`, `statecode`, `statuscode` |
| `CustomerAddressBase` | 6 | `AddressNumber`, `City`, `Country`, `ObjectTypeCode`, `ParentId`, `StateOrProvince` |
| `SystemUserBase` | 3 | `FullName`, `IsDisabled`, `SystemUserId` |
| `TaskBase` | 3 | `ActivityId`, `new_iptalmi`, `new_randevuid` |
| `TerritoryBase` | 2 | `Name`, `TerritoryId` |
| `new_blgeBase` | 3 | `new_blgeId`, `new_name`, `statecode` |
| `new_contact_accountBase` | 2 | `accountid`, `contactid` |
| `new_dilBase` | 3 | `new_dilId`, `new_name`, `statecode` |
| `new_eserkatilimBase` | 5 | `new_Katilimsaglayan`, `new_Kitap`, `new_eserkatilimId`, `new_katilimciTipi`, `statecode` |
| `new_hakBase` | 3 | `new_hakId`, `new_name`, `statecode` |
| `new_isplaniBase` | 12 | `CreatedOn`, `ModifiedOn`, `OwnerId`, `new_gercekbitistarihi`, `new_isEmriDurumu`, `new_isplaniId`, `new_isplaniiptal`, `new_planadi`, `new_projeasamasiid`, `new_projeid`, `new_tahminibitistarihi`, `statecode` |
| `new_katilimcitipiBase` | 3 | `new_katilimcitipiId`, `new_name`, `statecode` |
| `new_kitapBase` | 23 | `CreatedOn`, `ModifiedOn`, `OwnerId`, `new_Editor`, `new_KitapProjesi`, `new_YayneviAltMarka`, `new_baskisayisi`, `new_baskitarihi`, `new_ilkyayintarihi`, `new_isbn13`, `new_kitapId`, `new_name`, `new_oncekiyayineviid`, `new_projeeditoru`, `new_projekarti`, `new_sonyayintarihi`, `new_stokkodu`, `new_yayinciid`, `new_yayineviid`, `new_yayinyonetmeni`, `new_yazartext`, `statecode`, `statuscode` |
| `new_kitapgecmisiBase` | 6 | `CreatedOn`, `new_baskisayisi`, `new_kdvdahilfiyat`, `new_kitapgecmisiId`, `new_kitapid`, `statecode` |
| `new_markaBase` | 4 | `new_markaId`, `new_name`, `statecode`, `statuscode` |
| `new_new_hak_new_sozlesmeBase` | 2 | `new_hakid`, `new_sozlesmeid` |
| `new_new_proje_new_kitapBase` | 2 | `new_kitapid`, `new_projeid` |
| `new_new_sozlesme_new_blgeBase` | 2 | `new_blgeid`, `new_sozlesmeid` |
| `new_new_sozlesme_new_dilBase` | 2 | `new_dilid`, `new_sozlesmeid` |
| `new_new_sozlesme_new_kitapBase` | 2 | `new_kitapid`, `new_sozlesmeid` |
| `new_new_sozlesme_new_ulkeBase` | 2 | `new_sozlesmeid`, `new_ulkeid` |
| `new_projeBase` | 3 | `new_name`, `new_projeId`, `statecode` |
| `new_projeasamalariBase` | 3 | `new_name`, `new_projeasamalariId`, `statecode` |
| `new_sozlesmeBase` | 15 | `new_EkProtokolyeni`, `new_SozlesmeBaslangicTarihi`, `new_SozlesmeBitisTarihi`, `new_anasozlesmeid`, `new_ekprotokolbitist`, `new_ekprotokolsurelimi`, `new_ekprotokoltarihi`, `new_fesihtarihi`, `new_name`, `new_revizebitistarihi`, `new_sozlesmeId`, `new_suresizsozlesme`, `new_yenilemebaslangictarihi`, `new_yenilemebitistarihi`, `statecode` |
| `new_sozlesmetarafiBase` | 6 | `new_Firma`, `new_TarafTipi`, `new_kisi`, `new_sozlesmeid`, `new_sozlesmetarafiId`, `statecode` |
| `new_sozlesmetaraftipiBase` | 3 | `new_name`, `new_sozlesmetaraftipiId`, `statecode` |
| `new_ulkeBase` | 3 | `new_name`, `new_ulkeId`, `statecode` |
| `new_yaynevialtmarkaBase` | 3 | `new_name`, `new_yaynevialtmarkaId`, `statecode` |

Aktiflik denetiminde durum alanlı özel varlıklar ve Contact/Account süzülür;
N:N ilişkiler yalnız aktif uçlar üzerinden rapora katılır. SystemUser kapalı
hesapları `IsDisabled` ile korunur. TaskBase ve ActivityPartyBase üzerinde
ayrı statecode yoktur; görev/randevu durumları ActivityPointerBase üzerinden
süreç anlamıyla süzülür. Bu istisnalar pasif CRM iş kaydı kullanma izni değildir.

Revizyon ebeveyni yalnız UUID metin eşitliğiyle sınıflanır; aktif karşılık
bulunamaması pasif kaydı rapora alma gerekçesi yapılmaz. `contract_overlap` ve
`contract_revision_evidence` tanım boşluklarını korur. Audit kaynaklarının
mevcudiyeti ve sınırlı olay örnekleri, desteklenen API ile eski/yeni değer
kabulünün yerine geçmez.

## Hesabı değiştiren alan ve ilişki bulguları

| İş anlamı | Doğrulanan fiziksel kaynak | Sınır |
| --- | --- | --- |
| Güncel ISBN/ISSN | `new_kitapBase.new_isbn13` | `new_isbn` eski ISBN; elektronik ISBN ayrı alan |
| Kitap–kişi yazar | `new_eserkatilim.new_Kitap`, `new_Katilimsaglayan`, aktif `new_katilimcitipi` rol adı `Yazar` | `new_eserkatilimcisiId` Account'a gider; Contact kimliği değildir |
| Yayın evi | `new_kitap.new_yayineviid → new_marka.new_markaId` | Aynı adlı farklı kimlikler birleştirilmez |
| İki alt marka alanı | `new_yayinciid → new_marka`; `new_YayneviAltMarka → new_yaynevialtmarka` | İki alan aynı varlık değildir; ana yayıncı hiyerarşisi otomatik çıkarılmaz |
| Kitap tarihleri | `new_ilkyayintarihi`: İlk Baskı Tarihi; `new_sonyayintarihi`: Son Yayın Tarihi | `CreatedOn` yayın tarihi değildir |
| Editör ve sahip | `new_Editor`, `new_projeeditoru`, `new_yayinyonetmeni`, `OwnerId` ayrı | Sahip takım olabilir; kullanıcı kaydı yoksa kişi varsayılmaz |
| Müşteri vergi numarası | `AccountBase.new_VergiNo` | Boş değerler ortak kimlik değildir; ad benzerliğiyle birleşme yapılmaz |
| Müşteri şehir/adres | `CustomerAddressBase.ParentId`, `ObjectTypeCode=1`, `AddressNumber=1` | Metadata'daki `Account.Address1_City` fiziksel `AccountBase` kolonu değildir |
| Kişi–müşteri | Contact parent, Account birincil kişi ve `new_contact_accountBase` N:N | Üç ilişki yolu ayrı gösterilir; kişi ve müşteri kimlikleri tekilleştirilir |
| Görüşmeden doğan görev | `TaskBase.new_randevuid → appointment.ActivityId`; katılımcılar `ActivityPartyBase` | Serbest metinden görev icat edilmez |
| Sözleşme kapsamı | Ayrı kitap, hak, dil, bölge ve ülke N:N tabloları | Eksik kapsam sınırsız hak demek değildir |

CRM kitap, kişi ve müşteri sayımlarında mevcut aktiflik sözleşmesi uygulanır.
Özel ilişki/sözlük varlıkları `statecode=0` ile okunur. Standart görev/randevu
durumlarının süreç anlamı korunur: açık görev `0`; gelecek açık/zamanlanmış randevu
`0/3`; geçmiş tamamlanmış görüşme `1` olabilir. İptal `2` dahil edilmez.
Kullanıcı hesapları `IsDisabled` ile açıklanır; kapalı kullanıcı geçmiş atamalardan
sessizce düşürülmez.

## Tam cevap olarak sunulmayan alanlar

- `AuditBase` kolonlarının okunabilmesi, eski/yeni değer çözümünün veya tarihçenin
  eksiksizliğinin doğrulanması değildir. Genel alan değişikliği ve aşamaya giriş
  hesabı ayrıca kanıt ister.
- `new_kitapgecmisiBase` baskı/fiyat kayıtları genel bütün-alan tarihçesi değildir.
- Son değiştirme tarihi, aşama başlangıcı kabul edilmez.
- Revize, yenileme, fesih ve ana sözleşme tarihlerinin hukuki önceliği metadata
  alan adlarından çıkarılmaz.
- Bölge ve ülke kapsamlarının nasıl birlikte yorumlandığı, salt kimlik kesişimiyle
  hukuken doğrulanmış olmaz. Çakışma raporu aday incelemesidir.
- Önceki yayın evi alanı bir tarihsel geçerlilik aralığı sağlamaz.
- Şehir yazımı normalizasyonu resmi şehir–bölge eşlemesi değildir.

Bu sınırlar `gaps` ile taşınır. Böyle raporlar kısmi cevap olabilir; tam iş doğruluğu
veya sayısal kabul başarısı olarak sayılmamalıdır.

Sonraki kontrollü tarihçe incelemesi, şirket/kitap/sözleşme denetiminin açık olduğunu
ve aktif kaynak kayıtlarına bağlı gerçek audit olaylarının bulunduğunu gösterdi.
Bir kitap yayıncı alanı güncellemesi de mevcut. Ancak SDK eski/yeni değer
çözümlemesi henüz doğrulanmadı; rapora yeni bir tarihsel hesap eklenmedi.
Sözleşme log metinlerinin büyük bölümü PDF yolu olduğundan bu tablo alan değişikliği
geçmişi kabul edilmedi. Ek kanıtlar test sunucusunda
`/tmp/codex-crm-history-20260930/discovery.json` ve `discovery2.json` dosyalarındadır.

`contract_overlap` raporu, hiç aday çıkmasa bile `scope_interpretation_unverified`
açıklamasını taşıyan `UNVERIFIED_DEFINITION` boşluğu üretir. Bunun bağımsız kabulü
yalnız `BOUNDARY_PASS` olabilir; ülke/bölge anlamı kanıtlanmadan koşulsuz bir
"çakışma yok" veya kesin çakışma cevabı verilemez.

`contract_revision_evidence` yalnız kayıtlı revizyon kanıtını gösterir:
`new_anasozlesmeid` **nvarchar(100)** metindir; yayımlanmış lookup değildir.
UUID eşitliği boş, geçersiz metin, öz referans, başka aktif kayıt ve aktif karşılığı
bulunamayan değer olarak ayrılır. `new_EkProtokolyeni`, `new_ekprotokolsurelimi`,
`new_ekprotokoltarihi`, `new_ekprotokolbitist` alanları ayrı sunulur. Etiketi
"Ek Protokol (hatalı)" olan `new_ekprotokol` kullanılmaz. Eski/yeni audit decoder,
otomatik sözleşme soy ağacı veya tarihlerin hukuki öncelik hesabı eklenmemiştir.
Bu rapor da açık tanım boşluğu taşır ve en fazla `BOUNDARY_PASS` alabilir.

## Üretim çıktı sözleşmesi

`crm_reports.py` içinde `CRM_REPORT_CAPABILITIES.output_contracts`, gerçek
`Sources` alanlarından ve rapor satırı kurucularından çıkarılmış 8 ortak alan
kümesiyle 31 raporun çıktı kapsamını tanımlar. Her satır türünün alanları,
kimlik/kırılım düzeyi, uygulanan tarih filtresi ve tanım boşlukları ayrı kaydedilir.
`describe_crm_report_output(report)` yalnız seçilen raporun alanlarını açar;
plan denetçisi bütün raporların genişletilmiş alan listelerini birlikte almaz.

Bu sözleşme yeni bir hesap veya alan seçme özelliği değildir. Örneğin stok kodu
mükerrer adaylarında ISBN, yayıncı ve baskı alanları zaten bulunur; kısa açıklamada
sayılmamaları yetenek yokluğu değildir. Buna karşılık kişi iletişim raporunda
telefon/e-posta değerleri değil, doluluk göstergeleri vardır. Bir alanın çıktıda
olması, o alana göre keyfî filtreleme veya geçmiş durum hesabının desteklendiğini
göstermez. Ortak boş-sonuç satırı, karışık satır türlerinde NULL alanlar ve açık
limit davranışı da sözleşmede belirtilir. Statik bildirim kapsamı 31/31'dir;
planlayıcı davranışının gerçek API kabulü ayrıca gerekir.

## Ayrı çıktı ve filtre kapsamının genişletilmesi

İlk 31 genel rapora `work_due_missing` ve `contract_author_differences` eklendi;
rapor/çıktı sözleşmesi ve bağımsız koşucu şimdi 33 aileyi kapsar. Önceki
`work_due` tüm dönem işlerini, `contract_author_roles` tüm kayıtlı tarafları
sunmaya devam eder. Yeni yetenekler soru kimliğine veya soru metnine bağlı değildir.

- `subbrand_consistency`, kitap bulgularının yayıncı kimliği başına sayısını da
  verir. Boş kimlik ve çözülemeyen farklı kimlikler birleştirilmez; doğrulanmamış
  altmarka hiyerarşisi yine açık tanım boşluğudur.
- `publication_dates`, mevcut bütün kitap ayrıntısını korur. Ayrıca `as_of`
  itibarıyla ilk baskı veya son yayın tarihi gelmiş ve alan eksikliği bulunan
  kayıtları `arrived_missing` türünde, `date_basis` ile ayrı ayrı verir. Tarih
  sırası sinyalleri `chronology_signal` türündedir. Aynı kitap birden çok türde
  ve iki tarih temeliyle bulunabilir; satır sayısı benzersiz kitap sayısı değildir.
  Kontrol edilen eksik alanlar görünürdür; kurumsal zorunluluk kararı varsayılmaz.
- `work_due_missing`, gelecek dönem işlerine sorumlu veya aktif aşama eksikliği
  koşulunu uygular. Geçmiş terminli açık işleri eksiklik şartından bağımsız korur;
  `overdue` bunları ayırır. Kullanılan tarih tahmini iş-planı bitişidir.
- `contract_overlap`, her iki sözleşmenin ham başlangıç/bitiş alanlarını ve
  İstanbul takviminde kayıtlı ana tarihlerin kesişim başlangıç/bitişini verir.
  Eksik veya kesişmeyen tarihlerde kesişim NULL'dır; hukuki geçerlilik ve
  ülke/bölge yorumunun doğrulanmamış olması değişmez.
- `contract_author_differences`, yalnız dolu ve karşılaştırılabilir Contact
  kimlik kümelerini kıyaslar; eşit kümeleri çıkarır. Account/karışık tür veya
  eksik bağlarda satır `UNVERIFIED_IDENTITY_TYPES_OR_MISSING` ve açık gap ile
  korunur. İsim eşleştirmesi, yazar=hak sahibi veya kurum=kişi varsayımı yoktur.

Bağımsız koşucuda eski CR001–CR031 kimlikleri korundu; CR032 eksik atamalı işleri,
CR033 taraf-yazar kimlik farklarını kapsar. Yeni satır kimlikleri, tarih kesişimi,
JSON kişi kümesi farkları ve yayıncı toplamları bağımsız kaynak okumalarıyla
karşılaştırılır. Bu değişiklikler için henüz gerçek API/DB kabul sonucu yoktur;
yerel ürün testi çalıştırılmadı.

## Aday grupları ile kimlik sınıflandırmasının sınırı

`duplicate_title`, `duplicate_isbn`, `duplicate_book_code` ve `title_variants`
ayrıntılardaki alanları yan yana gösterir; farklı eser / farklı baskı / olası
mükerrer şeklinde hesaplanmış bir sınıflandırma üretmez. `decision` bütün adaylara
aynı uyarıyı verir. Yalnız aday ve karşılaştırma alanı isteyen sorular bu nedenle
otomatik kısmi cevaba çevrilmez. Buna karşılık sınıfları gerçekten ayırmayı isteyen
soru, bu raporla tam karşılanmış sayılamaz; eksik ayrım reddedilmeli veya açık bir
kısmi cevap boşluğu olarak taşınmalıdır. Kaynak alanlarının varlığı, kimlik
kanıtının veya sınıflandırmanın yerine geçmez.

Aday ailesinin yapılandırılmış çıktı sözleşmesi bu ayrımı üç bölümde taşır:
`supported` ham alanların yan yana karşılaştırılmasını ve aday listesini,
`non_claims` aynı eser/kesin mükerrer/otomatik birleştirme iddialarının
kurulmadığını, `unsupported_requested_operations` ise yalnız olumlu olarak
istenirse eksik sayılacak kimlik sınıflandırmasını belirtir. `non_claims` kullanıcı
yasağına uyulduğu anlamına gelir; zorunlu eksik çıktı veya otomatik çalışma zamanı
`gap` değildir. Örneğin "kesin mükerrer deme" sınıflandırma isteği değildir;
"farklı eserlerle olası mükerrerleri ayır" ise mevcut aday raporunun hesaplamadığı
zorunlu bir işlemdir.

İletişim raporundaki `contact_field_present_count`, e-posta VEYA telefon/cep
alanlarından biri dolu olan benzersiz kişi sayısıdır. Gerçek ulaşılabilirlik,
teslim edilebilirlik veya her kanalın ayrı toplamı değildir. `has_email` ve
`has_phone` da yalnız alan doluluğunu gösterir; mevcut çıktı notu bu sınırı açıklar.

## Değişiklik geçmişi sözleşmesinin açık sınırı

`book_change_history` için yapılandırılmış `supported` bilgisi güncel aktif
kitapların **son ModifiedOn** dönem kohortunu ve bu kitapların aynı dönemdeki
aktif baskı/fiyat snapshotlarını tarif eder. `non_claims`, snapshotların eski/yeni
audit olmadığını, ModifiedOn'un değişen alanı kanıtlamadığını, yayıncı tarihçesi
ve değişiklik nedeninin çözülmediğini belirtir. Bu raporun mevcut koşulsuz tarihçe
`gap` davranışı korunur.

"Doğrulayamadığını belirt" koşuluyla istenen desteklenen liste ve açık tarihçe
boşluğu kısmi cevap olabilir. Bu, zorunlu eski/yeni zaman çizelgesini veya farklı
bir nüfus filtresini karşılamaz: dönemde herhangi bir kez değişmiş bütün kitaplar,
son ModifiedOn'u döneme giren kitaplarla aynı küme değildir. Sözleşme açıklaması
hesapları veya kaynak okumalarını değiştirmez.

## İş planlarında nüfus ve işaret ayrımı

`work_due.population_contract` bütün dönem işlerini ve geçmiş terminli açık
işleri kapsar; `missing_owner`/`missing_stage` yalnız işarettir. `work_due_missing`
ise gelecek dönem nüfusunu bu iki eksiklikten en az biriyle süzer, geçmiş terminli
açık işleri yine korur. "Eksiklerini belirt" ifadesi tek başına tam atamalı işleri
çıkarma izni değildir. Bağımsız CR022 ve CR032 bu iki nüfusu ayrı karşılaştırır;
kabul koşucusunun beklentileri dar rapora uydurulmaz.

`work_stage_history` güncel açık işleri ve mevcut aşamayı sunar, koşulsuz tarihçe
boşluğu taşır. Son değiştirme tarihini aşamaya giriş saymama yasağına uyar.
Kullanıcı mevcut işleri ve doğrulanamayan kısmı açıkça isterse bu kısmi çıktı
uygundur; yalnız üç aydan uzun bekleyen nüfus veya sayısal bekleme süresi zorunlu
istenmişse tarihçe boşluğu bunların yerine geçmez.

## Kabul koşucusunun kapsamı

`scripts/acceptance/finance_contracts/crm_reports_live.py` 33 rapor ailesini gerçek
uygulama `/api/v1/ask` akışıyla ve aynı `resultId` üzerinden saklanan tam sonuçla
karşılaştırmak üzere hazırlanmıştır. Ürün modülünü import etmez; üretilmiş SQL'i
referans diye yeniden çalıştırmaz. Bağımsız sabit SQL'ler gerçek CRM'den kayıtları
okur; kimlik, kırılım ve sayımlar ayrı referans hesaplarında kurulur.

Kontroller:

- Tam kolon kümesi, her satır kimliği, satır sayısı, bütün kolon değerleri, NULL,
  sayısal tolerans, önizleme/tam sonuç tutarlılığı ve kesilme bilgisi.
- Tek rapor bir bölüm kapsayıcısındaysa, aynı saklanan yürütmenin bölüm veri seti
  ve genel bakış satırı birlikte kontrol edilir.
- API öncesi/sonrası bağımsız okumalar karşılaştırılır. Veri değişmişse sayısal
  kabul verilmez; yapısal sorunlar veri değişimiyle gizlenmez.
- Yayındaki kaynak hashleri ve yüklenmiş motor hashinin eşleşmesi.
- Her 10 soruda ilerleme; `FULL_ANSWER_PASS`, `BOUNDARY_PASS`, `FAIL`, `UNVERIFIED`
  ayrı sayılır. `BOUNDARY_PASS` sayısal/tam cevap başarısı değildir.
- Mevcut `timasai` hesabına 15 dakikalık oturum; `finally` içinde silme.
- Diğer ağır kabul koşularıyla ortak `/tmp/finance-composable-live.lock` kilidi.

Yalnız test sunucusunda, main kurulumu ve kapsam dondurma sonrası çalıştırılır:

```bash
sudo -n /data/nanobaseai/bi/semantic-venv/bin/python -u \
  scripts/acceptance/finance_contracts/crm_reports_live.py \
  --out /tmp/<oturuma-ozgu-bos-dizin> --as-of 2026-09-30
```

Referans günü canlı planlayıcının İstanbul günüyle aynı değilse koşucu durur;
tarihleri sessizce değiştirmez. Bu belgede henüz koşu sonucu veya üretim kabulü
iddiası yoktur.


## Tam nesne envanteri ve açık keşif kuyruğu

30 Eylül 2026 17:57:47 UTC envanteri 3.081 fiziksel tablo/görünüm ve 90.399
kolon içerir. Mevcut 33 raporun 31 doğrudan tablo / 161 alan kapsamı dışında
**3.050 nesne UNREVIEWED** kalır; gereksiz veya eşdeğer sayılmaz. Bunların
400'ü metadata ile özel `new_*` varlıklarına, 332'si kullanılan tablolara fiziksel
FK ile bağlanır. Bu iki küme birbirini dışlayan sayılar değildir.

400 özel nesnenin tamamı korunarak yalnız keşif önceliği oluşturuldu: kitap–eser
103, sözleşme–hak–royalty 17, iş–proje 45, kişi–müşteri 101, diğer 134.
Gruplar ad/etiket/ilişki ipucudur, iş anlamı kabulü değildir. Genel Owner ve
Activity RegardingObjectId bağları öncelik kanıtı yapılmadı. View/Base/Extension
eşdeğerliği kanıtlanmadığı için ad benzerliğiyle nesneler birleştirilmedi.
`NY_CRM_SIPARISLER` ve `NY_CRM_Siparisler` gibi fiziksel kimliklerin harf büyüklüğü korundu.

Kanıtlar test sunucusunda
`/data/nanobaseai/bi/acceptance/finance-expanded-20260930/reviews/crm-coverage/`:
`coverage-matrix.csv/json`, `unreviewed-custom-entities.csv/json`,
`discovery-priority.csv`, `DISCOVERY-PRIORITY.md`. Metadata envanteri SHA-256:
`ee26a27cc48bd6fa7d5d631453d4a75025c61517705e2602ea0927e341fe9a8e`.
Bu öncelik çalışmasında yeni DB/API veya ürün testi yoktur.
