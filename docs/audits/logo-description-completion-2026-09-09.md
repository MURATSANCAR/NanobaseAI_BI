# Logo açıklama tamamlama — 9 Eylül 2026

## Değişiklik

- 330 tablo / 9.316 kolonluk mevcut sözlük korundu.
- 145 tabloya ve 2.527 kolona Türkçe açıklama eklendi.
- Tablo eklemelerinin 104 tanesi mevcut kaynak metnin çevirisi/karakter kodlaması onarımı; 41 tanesi açık kolon açıklamasından türetilmiş tablo tanımıdır.
- Her ekleme `description_tr_provenance` içinde kaynak metnini, dosyasını ve yöntemini taşır.
- Önceki açıklamalar, türler, kod değerleri, indeksler ve ilişkiler değişmedi; tam JSON karşılaştırmasıyla doğrulandı.
- 25 odaklı test geçti.

## Kalan kaynak eksikleri

| Kapsam | Önce | Sonra |
|---|---:|---:|
| Hiçbir dilde tablo açıklaması yok | 93 | 52 |
| Türkçe tablo açıklaması yok | 201 | 56 |
| Hiçbir dilde kolon açıklaması yok | 13 | 13 |
| Türkçe kolon açıklaması yok | 2.578 | 51 |

Açıklamalar yalnız kaynakta mevcut anlam üzerinden tamamlandı. Kaynakta boş bırakılmış
13 kolonun anlamı; `Text/Tax`, çap/yarıçap, referans hedefi gibi çelişkiler tahmin edilmedi.
`Port` terimi kaynakta açıklanmadığı için çevrilmeden korundu. “Kullanımda değil” gibi
kaynak ifadelerinin çevrilmesi, alanın iş anlamının belgelendiği anlamına gelmez.

Verilen [web sözlüğü](https://ugurozpinar.github.io/Logo/Tablo%20A%C3%A7%C4%B1klamalar%C4%B1%20Yeni/)
ve aynı deponun eski tablo açıklamaları karşılaştırıldı; boş kolonlara ek tanım bulunamadı.
Web sözlüğünün kaynak metinleri mevcut JSON'da tutuldu, çeviriler ayrı haritalarda incelendi.

Tam eklemeler, kaynak metinleri, çelişkiler ve kalan tüm adlar aynı adlı JSON dosyasındadır.
Önceki `logo-missing-descriptions-*-2026-09-09` raporları tamamlamadan önceki denetimdir.

## Üretim durumu

Aday katalog hazırlandı: 4.121 profilden 877 profil, 443 tablo açıklaması ve 10.905 kolon
 açıklaması güncellendi. Üretime geçiş ve indeks/kalite doğrulaması devam ediyor.
Yayın kayıtları: `/data/nanobaseai/bi/backups/logo-description-completion-20260909`.

## Hiçbir dilde açıklaması olmayan kolonlar

- `ITEMS.BUFFER`
- `INVEXIMINFO.COUNTRYREF`
- `INVEXIMINFO.FREEZONEREF`
- `INVEXIMINFO.PAYTYPEREF`
- `INVEXIMINFO.BRBANKREF`
- `INVEXIMINFO.CUSTOMREF`
- `INVEXIMINFO.SHPTYPREF`
- `INVEXIMINFO.SHPAGNREF`
- `INVEXIMINFO.REGTYPREF`
- `INVEXIMINFO.BANKREFNR`
- `INVEXIMLINES.CUSTOMREF`
- `INVEXIMLINES.COUNTRYREF`
- `INVEXIMLINES.ORIGINCNTRREF`

## İndeks doğrulaması

Aday `semantic_catalog_logo_tr_20260909`: 50.809 kayıt, 1.529 entity, 39.957 farklı
entity/kolon çifti, eksik indeks kolonu 0. Tüm payload kayıtları geri okunup beklenen
metinlerle karşılaştırıldı. İlk oluşturma 43.715 değişmeyen vektörü yeniden kullandı;
7.094 yeni metin gömüldü. Son incelemenin 8 metin düzeltmesi ayrıca işlendi ve tüm
koleksiyon yeniden doğrulandı.

Yeni açıklamaları sınayan altı Türkçe aramada beklenen tablo ilk 10 sonuçta bulundu:
banka kredileri, dahilde işleme izin belgesi, bütçe revizyon fişleri, iş akışı dönemleri,
kefiller, özellik seti. Bu sınırlı kontrol tüm iş sorularının doğruluğunu kanıtlamaz.

Kalite referansı önceki yayının gerçekten ölçülen `stage/published-quality.json` dosyasıdır;
soru kümesi, ret tanımı veya eşikler değiştirilmez. Mevcut 3 kesin ret ve 9 netleştirme
isteği adayın resolver/compiler karşılaştırmasında aynı kaldı.
