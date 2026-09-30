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

## Kabul koşucusu

`scripts/acceptance/finance_contracts/crm_reports_live.py` 30 rapor ailesini gerçek
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
