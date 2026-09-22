# Yazım ve noktalama (`spelling`) — kısmen ölçüldü

Kaynak: `src/editor/proofing/spelling.py`, `_spelling_rules.py`, `_spelling_text.py`,
`_spelling_judge.py`, `_spelling_geometry.py` (v1). Deterministik kurallar + sözlükler önerir,
model yalnız onaylar/reddeder; düzeltme uygulanmaz.

## 1. Kural — ne bulgudur, ne değildir

| kind | ne | model? |
|---|---|---|
| `bilinmeyen_kelime` | iki Türkçe çözümleyicinin de tanımadığı biçim; öneri: bitişik ek/edat («geliyormu» → «geliyor mu», «diyorki»), sözlük önerisi (uzaklık ≤2), yapışık iki kelime | evet |
| `tekrarlanan_hece` | «ortalamamamız»: sözlükte isim olan -mA eylemliği (ortalama, dondurma) «ma/me» iki kez yazılmış; çift biçim dilbilgisel olduğundan sözlük yakalamaz | evet |
| `tekrarlanan_kelime` | satır içinde çift **işlev sözcüğü** («ve ve»; içerik sözcüğü ikilemedir: «koş koş»); satır sonu/başında aynı kelime (klasik dizgi hatası; içerik sözcüğüyse model) | işlev: hayır; satır geçişi: evet |
| `ek_uyumu` | ayrı yazılan soru eki ve «da»nın ünlü uyumu («geliyor mu», «sen de»); kesmeli ekte ünsüz benzeşmesi («Mert'de»), kaynaştırma («Defne'e»), uyum («Mert'ın» — yalnız kitabın aynı adı düzenli çektiği yerde) | hayır |
| `kesme_eksik` | kitapta kesmeyle yazılan ad ek almış, kesme yok («Mertin») | hayır |
| `gereksiz_kesme` | cins isimden sonra kesme («kitap'ı»); kısaltma/harf («cm'den», «‘b’yi») ve «bi’şey» hariç | hayır |
| noktalama (7 kalıp) | işaretten önce boşluk, virgül/noktalı virgül/iki noktadan sonra boşluk yok, cümle sonu bitişik, tırnak içi boşluk, çift nokta, çift işaret, dört nokta | hayır; boşluk kalıpları **glif geometrisi** ile doğrulanır |
| `büyük_harf` | noktadan sonra küçük harf; kısaltma, rakam («6. hükümdar»), üç nokta hariç | yalnız OCR |
| `tutarlılık` | kitap üslubu: kesme (’/'), üç nokta (…/...), tırnak (“ ”/" "), konuşma çizgisi (–/—/-); bir biçim ≥ `HOUSE_SHARE` ise azınlık biçimi **sayfa başına bir** bulgu | hayır |

Bulgu OLMAYAN (çocuk kitabı dili ve düzen gürültüsü): uzatma (3+ aynı harf; çift ünlü/son
harf tek hâli kelimeyse: «Yook», «Heyy»), gülme («Ahahaha»), stilize büyük/küçük («TiRtIlDaN»),
kitabın kendi sözcüğü (**2+ sayfada** basılan biçim: uydurma kelime, karakter ağzı), cümle
ortasında büyük harfli biçim (ad: `name_spelling`'e), ≤2 harf, yabancı harf (`FOREIGN`), çizgili
birleşik/hecelenmiş («Or-man»), OCR büyük harf I/İ karışıklığı (öbür noktayla kelimeyse), bozuk
span, parça belirteç, arka ünlüden sonra «de» (emir kipi «de» olabilir — altı kitaptaki dört
vuruş da buydu), OCR span'ında noktalama boşluğu/üslup (OCR şekilleri normalleştirir).

## 2. Girdi / kaynak

- `read_book`: `source.read` span'ları (TEXT_LAYER ya da OCR; OCR «supplement» span'ları sıra
  belirsiz), NFKC, ligatür boşluğu («reﬂ ekslerim»), URL/e-posta/etiket maskeli. Satır sonu
  çizgileri birleştirilir: span içinde, span'lar arası, sayfalar arası («söy-» s.95 / «ledi»
  s.96; en yakın küçük harfle başlayan span, birleşim kelime olmalı). Eşleşmeyen parça
  `fragment`, bildirilmez. Bozuk span: ≥3 kelime yapışık biçim, OCR döngüsü (aynı kelime 3×),
  ya da ≥`GARBLE_MIN_BAD` küçük harfli kelime sözlük dışı ve oran ≥ `GARBLE_RATIO`.
- Sözlük `Lexicon`: zeyrek (Zemberek morfolojisi; MIT / Apache-2.0) **ya da** hunspell tr_TR
  (tdd-ai, MPL-2.0; spylls ile) kabul ederse geçerli; ikisi de reddederse geçersiz. Gerekçe
  kodda: her biri tek başına diğerinin kabul ettiği doğru biçimleri reddediyor (zeyrek:
  «okurkenki»; hunspell: «sitemkâr», «herhâlde»). Şapkalı harf düzleştirilerek ikinci deneme.
  Yol: env `EDITOR_HUNSPELL_TR`, yoksa `/app/data/hunspell/tr_TR`; yoksa `RuntimeError`.
- Glif geometrisi: PyMuPDF rawdict (`TEXT_INHIBIT_SPACES`), `_spelling_geometry.glyphs`.
- Sayfa görüntüsü: `document.render_page` (model sorusu için).

## 3. Karar mekanizması

Sıra, her aday için (`spelling.run`):
1. **Geometri** (yalnız boşluk kalıpları, `geometry` alanı): işaretin sol/sağ komşusuyla arası
   `printed_gap` → aynı satırda değilse **düşer** (satır sonu boşluktur); `gap_em ≥ SPACE_EM`
   basılı boşluk. `confirms`: kural «önce boşluk» türündeyse boşluk varsa hata; «sonra boşluk
   yok» türündeyse boşluk yoksa hata. Ölçülemezse (`found=False`) düşer, `unmeasured_gap`.
2. **`printed`** (`needs_model` ya da OCR kaynaklı ve `tutarlılık` değilse): sayfa görüntüsü +
   «basılı metinde hangisi harfi harfine yazıyor?» — bizim biçim ve **bütün** öneriler birlikte
   (A–G harfleri), iki sırada, ortalama. Gerekçe kodda: tek yanlış görünümlü seçenekle model
   «ehven-i şer» seçer («Hepsı» > «Heps», basılı «Hepsi»). Öneri yoksa evet/hayır iki kutupta.
   `p_printed < KEEP` → düşer.
3. **`is_error`** (`needs_model`): cümle (160 kr) + soru; A «Yazım/dizgi hatası» / B «Bilinçli
   ya da doğru kullanım (ses taklidi, uzatma, ağız, çocuk dili, uydurma sözcük, tekerleme,
   yabancı sözcük, ikileme)»; iki sırada ortalama; `p_error < KEEP` → düşer.
Model: `book-director`, `Llm.choose` (tek belirteç, olasılık logprobs'tan, thinking kapalı).

## 4. Eşikler ve nereden okunduğu

| eşik | değer | yer | anlam / ölçüm (kodda) |
|---|---|---|---|
| `SPACE_EM` | 0,12 em | `_spelling_geometry` | altı kitabın tüm katman satırları: kelime içi harf aralığı p99 0,020–0,065 em; katmanda boşluk olan aralıklar p5 0,17–0,26 em (p1 0,058–0,21); 0,12 arada |
| `GARBLE_MIN_BAD` / `GARBLE_RATIO` | 3 / 0,25 | `_spelling_text` | «measured: docs, Bozuk katman» — sayı kodda yok |
| `HOUSE_SHARE` | 0,8 | `_spelling_rules` | «measured: docs, Tutarlılık» — sayı kodda yok |
| `KEEP` | 0,5 | `_spelling_judge` | iki yönlü seçimin argmax'ı; ayarlanmış değer değil |
| kitabın sözcüğü | ≥2 sayfa | `unknown_words`, `doubled_syllables` | tekrarlanan hata nadir |
| öneri uzaklığı | Damerau-Levenshtein ≤ 2, en çok 5 öneri | `_suggestions` | — |
| kısa kelime | ≤2 harf atlanır | `unknown_words` | — |
| `tekrarlanan_hece` en az uzunluk | 6 harf | `doubled_syllables` | altı kitapta 44 ham ünsüz+ünlü çiftlemesi, bu kalıp dışında hepsi dilbilgisel |
| yapışık kelime bölme | en az 2 parça, parça ≥3 harf (öneri), ≥2 (bozukluk) | `segment` | — |
| OCR büyük harf I/İ | ≤6 aday konum | `_caps_ocr_ambiguous` | — |
| bağlam | model: 160 kr; görüntü: 34 kr | `context`, `_alt_phrases` | — |
| `EDITOR_HUNSPELL_TR` | env; varsayılan `/app/data/hunspell/tr_TR` | `_dict_path` | — |

## 5. Bulgu biçimi

Tüm bulgular **WARN**. `page, quote` (basılı biçim / kalıp çevresi ±14 kr / üslup ±20 kr),
`message` (`MESSAGES[kind]` ya da noktalama kuralı metni), `suggestion`, `details{kind, source,
word?, suggestions?, how?, rule?, printed_gap?, p_printed?, p_error?, style?, used?,
book_majority?, count_on_page?, book_counts?, across_line?, previous?, name?, suffix?, unit?}`.

Stats: `raw:<kind>` (her kural), `garbled_spans, fragments, skip_short, skip_foreign,
skip_expressive, skip_ocr_caps, skip_name, skip_book_vocabulary, dropped_by_glyph_gap,
unmeasured_gap, dropped_not_printed, dropped_as_intentional, kept:<kind>`.

## 6. Kendi hatası vs kitabın hatası

- Kitabın: §1 tablosu.
- Okuyucunun/katmanın (elenir, stats'a yazılır): katman boşluk artefaktı («Merhaba , Defne .»
  basılı «Merhaba, Defne.»; satır sonu virgülünden sonra kaybolan boşluk) → geometri; OCR
  yanlış okuma («kitapşık») → `printed`; bozuk span, parça, OCR döngüsü → hiç aday olmaz.
- Sözlüğün: iki çözümleyicinin de bilmediği doğru kelime → `is_error` sorusu son savunma.
- Exception (FAILED): sözlük dosyası yok, model erişilemiyor.

## 7. Ölçüm

Kodda yazılı olanlar (altı kitap):
- `SPACE_EM` dağılımları (§4).
- `tekrarlanan_hece`: 44 ham çiftleme, kalıp dışı hepsi dilbilgisel.
- «de» arka ünlüden sonra: dört vuruş, dördü de emir kipi.
- `printed` tek seçenek yanlılığı («Hepsı»/«Heps»/«Hepsi»).
- Çözümleyici uyuşmazlığı örnekleri (okurkenki, sitemkâr, herhâlde).

### ÖLÇÜM BEKLİYOR

Kodda «measured: docs» denip sayısı olmayanlar: bozuk katman eşiği (3 / 0,25), üslup payı
(0,8), **genel kesinlik** («Measured precision: see docs, Ölçüm»). Bu belgede yok.

Plan:
```sh
ssh tt-gpu 'docker exec -i editor-mcp python -m editor.proofing <gen> --only spelling --dry' > spelling-<kitap>.json
```
1. Altı kitapta `kept:<kind>` bulguları kind başına elle etiketlenir (gerçek / bilinçli / katman /
   OCR / sözlük eksiği); kesinlik kind başına.
2. `dropped_*` sayıları ile atılanlardan örneklem: yanlış düşürülen var mı (geri çağırma).
3. `GARBLE_RATIO`: bozuk işaretlenen span'lar gözle; 0,25 altı/üstü.
4. `HOUSE_SHARE`: her kitapta `book_counts`; 0,8 altında kalan gerçek karışık üslup var mı.
5. Geri çağırma (enjekte): «geliyormu», «Mertin», «kitap'ı», «ve ve», «çocuklar,dedi» (katmanda
   gerçek bitişik) → her biri çıkmalı; «Merhaba , Defne» (kern ile kapatılmış) → çıkmamalı.

## İlk gerçek koşu (2026-09-22)

«Levent Dünya Harikalarının Peşinde», nesil `60e5d717`: **21 WARN**. Örnekler: «ortalamamamız»
(`tekrarlanan_hece`), kesme işareti «’»/«'» karışımı (`tutarlılık`, sayfa başına bir), çift
nokta, «mizdeki» (`bilinmeyen_kelime`, muhtemelen satır kırığı parçası). İnsan doğrulaması yok.

## 8. Bilinen yanlış alarm riskleri ve açık sorular

1. **Parça kaçağı**: «mizdeki» gibi satır başı parçası, önceki span'ın sonu çizgisiz kırıldıysa
   ve birleşim `segment`'e uymadıysa `fragment` işaretlenmez → `bilinmeyen_kelime`. Model
   sorusu («yazım hatası mı?») parçayı hata sayabilir. Açık: cümle-ortası küçük harfli span
   başlangıcı için `lex.valid` başarısızsa `fragment` yalnız `_starts_sentence` yanlışken;
   noktadan sonra gelen parça kaçar.
2. **`tutarlılık` sayısı**: azınlık biçim her sayfada bir bulgu; 30 sayfada karışık kesme →
   30 WARN. Ekranda tek gruplanmış öğe daha doğru olabilir (açık karar).
3. **Öneri yokken `bilinmeyen_kelime`**: `suggestion=None`; model sorusu sözlükten bağımsız,
   uydurma sözcük «bilinçli» sayılmalı — `KEEP=0,5` bunu ölçmeden sınırlıyor.
4. **Geometri bulunamayan işaret** (`unmeasured_gap`): katman metni glifle uyuşmuyorsa (özel
   font) bütün noktalama boşluk adayları düşer — sessiz geri çağırma kaybı.
5. **Kesmeli ad uyumu** yalnız kitabın aynı adı düzenli çektiği yerde; tek geçen ad için
   «Holmes’u» türü bulgu üretilmez (bilinçli).
6. **OCR span'larında** noktalama ve üslup hiç bakılmaz; katmansız kitapta bu kurallar sessiz.
