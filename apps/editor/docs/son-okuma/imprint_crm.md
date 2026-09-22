# Künye — CRM karşılaştırması (`imprint_crm`) — ÖLÇÜM BEKLİYOR

Kaynak: `src/editor/proofing/imprint_crm.py` (v1). Deterministik; model yok, CRM'e bağlanmaz,
hiçbir şey yazmaz.

## 1. Kural — ne bulgudur, ne değildir

Kitapta basılı künye ile yayınevinin CRM kaydı arasındaki uyumsuzluk. Her bulgu basılı satırı
alıntılar.

| alan | karşılaştırma | bulgu |
|---|---|---|
| ISBN | kitaptaki her ISBN'in denetim hanesi (ISBN-13 mod 10, ISBN-10 mod 11); CRM ISBN'iyle rakam eşitliği | hane tutmuyor → ERROR; CRM'den farklı → ERROR (CRM'in `isbn10`/`ebook_isbn` alanındaysa INFO); künyede ISBN yok → WARN; CRM'in ISBN'i bozuk → WARN |
| kitap adı | CRM adı (`imprint.titles` ya da `crm_title`) kitabın **herhangi bir** sayfasının metninde (boşluksuz, katlanmış) var mı | bulunamadı → INFO («kapakta çizim olabilir»); **asla uyumsuzluk değil** |
| kişiler | her CRM katkı sahibi kitapta: SAME / DIFFERENT (tam bir ad kelimesi fazla/eksik) / ABSENT; kitabın etiketlediği (Yazar:, Çizer:, Çeviri:, Editör, Proje Editörü, Yayın Yönetmeni) ama CRM'de olmayan kişi | DIFFERENT → WARN; ABSENT → yazar/çizer/çevirmen WARN, editör rolleri INFO; etiketli-CRM'de yok → WARN (editör rolleri için yalnız `imprint` nesnesi varsa) |
| baskı | «N. Baskı» ↔ `imprint.edition_no`; eşitse ay/yıl ↔ `edition_date` (UTC → İstanbul +3) | numara farklı → WARN («dosya eski baskıya ait olabilir» eki basılı < CRM ise); tarih farklı → INFO |
| yaş | basılı «a - b Yaş» ↔ `shelf_text` aralığı ve `age_from/age_to` | raf farklı → WARN; hedef yaş basılı aralığın dışına taşıyor → WARN; CRM `ages_text` hedef yaşla çelişiyor → INFO (CRM kendi içinde tutarsız) |
| dizi | basılı «<Dizi> Kitaplığı/Kitaplar/Dizisi/Serisi [/ n]» ↔ `imprint_series`/`series` (genel kelimeler atılmış kelime kümeleri, biri diğerini kapsıyor mu) ve `imprint_series_no` | künyede yok → INFO; ad farklı → WARN (CRM'in iki alanı da tutmuyorsa mesajda söylenir); numara farklı → WARN |
| yayın no | «Yayın No n» / «YAYINLARI n» ↔ `publication_no` | farklı → WARN (dizi numarasıyla aynıysa mesaj bunu söyler) |
| sayfa | PDF sayfa sayısı (`page` tablosu) ↔ `page_count` | farklı → WARN |

Bulgu OLMAYAN: CRM kaydı olmayan kitap (tek INFO ile biter), kapakta çizim olan ad, bir web
kullanıcı adı olarak geçen yazar adı (ad satırı DIFFERENT ise onu bozmaz).

## 2. Girdi / kaynak

- Sayfa metni: `source.read(gid)`; künye sayfaları `imprint_pages`: ISBN, ©, «Sertifika No»
  ya da «N. Baskı» geçen sayfalar. Kişi etiketi için künye sayfaları + ilk 6 sayfa.
- CRM: `ed.book_crm_record` (`book_id` ile; `connectors/crm_covers.py` CRM'in erişilebildiği
  yerde koşup `catalog.store_crm_record` ile yazar). Temel alanlar: `crm_title, authors,
  illustrators, isbn, matched_by`. Genişletilmiş alanlar isteğe bağlı `imprint` nesnesinde:
  `titles, isbn13, isbn10, ebook_isbn, roles{Yazar,Çizer,Tercüme}, authors_text,
  illustrators_text, translators_text, editor, project_editor, publishing_director,
  edition_no, edition_date, shelf_text, age_from, age_to, ages_text, imprint_series,
  imprint_series_no, series, publication_no, page_count`. **Bağlayıcı bu nesneyi henüz
  taşımıyor** (modül docstring'i); yokken yalnız ISBN, ad ve yazar/çizer karşılaştırılır.
- Sayfa sayısı: `page` tablosunda `book_version_id` satır sayısı.

## 3. Karar mekanizması (deterministik)

- Metin katlama `fold`: NFKC, İ→i, I→ı, casefold, çğıöşüâîû→ASCII, aksan atma, harf-rakam dışı
  → boşluk. `squash`: boşluksuz («SOYA D» yine eşleşir).
- Ad satırı `name_line`: 2–6 kelime, cümle noktalaması yok; markdown/kenar noktalama/rol
  etiketi soyulur.
- `find_person`: ad satırı kelime çoklu-kümesi CRM adıyla eşitse SAME; ≥2 kelime ortak ve tam
  **1** kelime fark → DIFFERENT (docstring: iki+ kelime fark aynı satıra sıkışmış başka bir
  addır, altı kitapta ölçüldü); hiçbiri değilse sayfa metninde squash araması; yoksa ABSENT.
  Tek kelimelik CRM adı atlanır (SKIP).
- ISBN: «ISBN» ya da «Seri No» kelimesinden sonraki 60 karakterde `ISBN_RE`.
- Tarih: Dynamics UTC saklar; «Temmuz 2026» = 2026-06-30T21:00Z → `LOCAL` (+3, 2016'dan beri
  sabit).

## 4. Eşikler ve nereden okunduğu

Env/config yok; hepsi kodda.

| eşik | değer | yer |
|---|---|---|
| ISBN arama penceresi | 60 karakter | `printed_isbns` |
| ad satırı uzunluğu | 2–6 kelime | `name_line` |
| DIFFERENT | ortak ≥ 2, fark = 1 | `find_person` |
| etiketli kişi ↔ CRM kısmi eşleşme | squash eşit ya da uzunluk > 5 ve biri diğerini kapsıyor | `compare` (people) |
| kişi etiketi taranan sayfalar | künye sayfaları + ilk 6 sayfa | `compare` |
| `SERIES_GENERIC` | kitaplığı, kitaplık, kitaplar, kitap, dizisi, dizi, seri, serisi, cocuk, yayinlari, yayinevi | modül sabiti; yayınevi adı bilerek listede değil |
| saat dilimi | UTC+3 | `LOCAL` |

## 5. Bulgu biçimi

`page` (künye sayfası ya da None), `severity`, `message`, `quote` (basılı satırın eşleşen
kısmı + 24 karakter), `suggestion`, `details` (`printed`, `crm`, `role`, `matched_by`, …).
Stats: `crm (bool), matched_by, imprint_pages, imprint_fields (bool), compared [isbn, title,
people, edition, age, series, publication_no, pages]`.

## 6. Kendi hatası vs kitabın hatası

- CRM'in hatası da bulgu olarak yazılır ama ayırt edilir: CRM ISBN'i bozuk (WARN, «CRM
  kaydındaki ISBN'i düzeltin»), CRM iki dizi alanı tutmuyor, CRM yaş etiketleri tutarsız (INFO).
- Kendinin: CRM kaydı yok → tek INFO; alan `imprint`'te yok → karşılaştırılmaz (`compared`
  listesine girmez), bulgu değil. Generation bulunamazsa `KeyError` → koşu FAILED.

## 7. ÖLÇÜM BEKLİYOR

Kodda yazılı ölçümler (sayısız): `imprint_pages` altı kitapta hep tek ön sayfa (s2 ya da s3),
hikâye sayfası hiç eşleşmedi; DIFFERENT eşiği (tam 1 kelime) altı kitapta seçildi. Kesinlik
sayısı yok. Modül docstring'i «each explained with its measurement in the doc» diyor; bu belge
o ölçümü taşımıyor.

Plan:
```sh
ssh tt-gpu 'docker exec -i editor-mcp python -m editor.proofing <gen> --only imprint_crm --dry' > imprint-<kitap>.json
```
1. Altı kitapta `stats.compared` ve bulgular; her WARN/ERROR elle: gerçek uyumsuzluk / CRM
   hatası / okuma hatası (ISBN penceresi, ad satırı).
2. Geri çağırma (enjekte): `book_crm_record`'un geçici kopyasında ISBN'in bir hanesi, yazar
   soyadı, baskı numarası değiştirilir → her biri çıkmalı.
3. `imprint` nesnesi geldiğinde (bağlayıcı değişikliği ayrı iş) baskı/yaş/dizi/yayın no/sayfa
   alanları ilk kez ölçülür.

## İlk gerçek koşu (2026-09-22)

«Levent Dünya Harikalarının Peşinde», nesil `60e5d717`: **0 bulgu**. CRM kaydı olmasaydı bir
INFO çıkardı; dolayısıyla kayıt vardı ve karşılaştırılan temel alanlar uyuştu. Hangi alanların
karşılaştırıldığı (`stats.compared`) kaydedilmedi. İnsan doğrulaması yok.

## 8. Bilinen yanlış alarm riskleri ve açık sorular

1. **Ad satırı kapsamı**: «Editör» etiketli satır CRM'de rol yoksa (`imprint` yokken) WARN
   üretmez, ama `imprint` gelince her editör adı için WARN çıkar; CRM bu rolleri doldurmuyorsa
   sistematik yanlış alarm.
2. **Yazar adı yalnız kapakta çizim**: `find_person` ABSENT → WARN; kapak metin katmanı
   yoksa (OCR'a düşer) ad OCR hatasıyla DIFFERENT olabilir.
3. **Dizi kalıbı** yalnız «Kitaplığı|Kitaplar|Dizisi|Serisi» ile biten adları görür; «Geyikli
   Kitaplar|1» yakalanır, «Umutlu Kitaplar / 73» yakalanır, ama başka bir son ek yakalanmaz.
4. **Yayın no ↔ dizi no** karışması mesajda uyarılıyor; hangisinin doğru olduğu editörün.
5. `labelled_people` ad kalıbı en çok 5 kelime ve büyük harfle başlayan kelimeler; küçük harfli
   bağlaçlı adlar («van», «de») kesilir.
6. Açık: `imprint` nesnesinin bağlayıcı tarafı (CRM alan adları) bu belgede tanımlı değil;
   kodun beklediği anahtarlar §2'de.
