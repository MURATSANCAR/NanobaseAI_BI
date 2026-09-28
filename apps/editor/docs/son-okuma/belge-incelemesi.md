# Belge incelemesi (Son Okuma → «Belge incele») — ÖLÇÜM BEKLİYOR

Kaynak: `src/editor/document_review.py`, `proofing/_doc_context.py`, `db/migrations/029_document_review.sql`;
kart servisi `/v1/documents*`; köprü `/api/v1/editorial/documents*`; ekran `src/canvas/editorial/DocumentReview.tsx`.

## Ne yapar

Editör Son Okuma ekranından bir belge yükler: **doc, docx, pdf, odt, rtf, txt, md**. ZEKİ AI metnini çıkarır ve
kitaplarda koşan **metin denetimlerini** aynı kodla bu metinde koşar:

| denetim | ne bulur |
|---|---|
| `word_variety` | aynı anlamda yakın tekrar + kelime haritası (anlamlar, deyimler) |
| `sentence_starts` | art arda aynı sözcükle başlayan cümleler |
| `phrase_repeats` | yinelenen kalıp ifadeler |
| `word_choice` | Türkçe karşılığı olan yabancı sözcük; okur çocuk/genç ise yaşa ağır sözcük |
| `word_overuse` | yazar tikleri (yayınevinin okunmuş kitaplarıyla karşılaştırma) |

Kitap okuması değildir: resim, karakter, olay, süreklilik, sayfa düzeni, heceleme okunmaz. Bulgular son okuma
listesiyle aynı biçimde gösterilir; editör kararı (doğru/yanlış alarm) belgede yoktur — kuralın isabeti kitap
bulgularından ölçülür. Word'e aktarım belgede de vardır.

## Metin çıkarma ve sayfa

| biçim | nasıl | sayfa |
|---|---|---|
| pdf | PyMuPDF, satır geometrisinden paragraf (`document.paragraphs_from_layout`) | basılı sayfa (PRINTED) |
| docx | python-docx: paragraflar + tablo hücreleri | yaklaşık |
| doc | antiword | yaklaşık |
| odt | `content.xml` (text:p / text:h) | yaklaşık |
| rtf | striprtf (cp1254) | yaklaşık |
| txt, md | utf-8 / cp1254; boş satır paragraf sınırı | yaklaşık |

Sayfası olmayan belgede konum bildirmek için paragraflar bölünmeden ~250 sözcüklük sayfalara dizilir
(`PAGE_WORDS`; basılı bir kitap sayfası kadar). Ekran «yaklaşık sayfa» der. Taranmış (metinsiz) PDF reddedilir
(«önce metin tanıma gerekir»). Dosya boyutuna uygulama sınır koymaz.

## Belge bağlamı

Denetimler kimlikle çağrılır; belge incelemesinde kimlik belgenindir ve `_doc_context` belgeyi taşır:
okuma belgenin sayfalarından, kitap profili yükleyenin okur kitlesi/yaş beyanından (yoksa bilinmiyor),
model kaydı kitaba bağlanmaz, sayfa görseli ve yer işareti yoktur, `word_overuse` derleminden kitap dışlanmaz.

## Kuyruk ve erişim

Yükleme `document_review` satırı açar (QUEUED); compose servisi `document-review` (`python -m
editor.document_review consume`) sırayla işler (RUNNING → DONE | FAILED). Bir denetimin düşmesi belgeyi
düşürmez (denetim FAILED, öbürleri koşar). Süreç yarıda ölürse belge başlarken yeniden kuyruğa alınır.

Belgeyi yalnız yükleyen ve yönetici görür (köprü; başkasınınki 404). Yetki: sayfa `son-okuma` ya da
`redaksiyon`; yükleme `ozellik:son-okuma.belge`; Word'e aktarım `ozellik:veri.disa-aktar`.

## Ölçüm

- Birim: `tests/test_document_review.py` 6/6 (docx+tablo, odt, rtf cp1254, txt/md, pdf basılı sayfa, reddetme,
  sayfalama, belge bağlamı). Gerçek bir `.doc` ile denenmedi.
- Uçtan uca (Dilek Ağacı metni `.docx` olarak, okur 7–9 yaş): göç uygulandı, belge oluştu (4.243 sözcük,
  yaklaşık sayfa); denetim sonuçları VPN koptuğu için okunamadı — DEVAM EDİYOR.
