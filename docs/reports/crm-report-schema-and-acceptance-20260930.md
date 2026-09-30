# CRM raporları: kaynak envanteri ve bağımsız kabul

2026-09-30 itibarıyla yeni CRM raporlarının fiziksel alanları ve yayımlanmış ilişkileri,
eski semantik kataloğa başvurmadan doğrudan bağlı `Timas_MSCRM` metadata kaynağından
incelendi. Bu belge **canlı API kabul sonucu değildir**. Kabul koşucusu hazırdır;
bu çalışma sırasında ürün testi veya dağıtım yapılmamıştır.

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

## Kabul koşucusunun kapsamı

`scripts/acceptance/finance_contracts/crm_reports_live.py` 31 rapor ailesini gerçek
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
