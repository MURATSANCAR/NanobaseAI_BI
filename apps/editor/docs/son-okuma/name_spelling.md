# Ad yazımı tutarlılığı (`name_spelling`) — ÖLÇÜM BEKLİYOR

Kaynak: `src/editor/proofing/name_spelling.py`, `_spelling_text.py`, `_spelling_judge.py`,
`_spelling_rules.py` (FOREIGN, SUFFIX_START) (v1). Deterministik aday + model doğrulama.

## 1. Kural — ne bulgudur, ne değildir

Aynı ad kitap boyunca aynı yazılıyor mu.

- `ad_varyantı` (WARN): seyrek bir biçim, sık bir adın **bir harf** uzağında (4–7 harfli
  adlar) ya da **iki harf** (≥8 harf): «Kamil» / «Kâmil», «Irmak» / «İrmak» (aynı harfler,
  farklı büyük harf = 1 uzaklık sayılır).
- `küçük_harf` (WARN): kitabın büyük harfle yazdığı ad küçük harfle geçmiş **ve** küçük hâli
  sıradan bir kelime değil («masal», «defne» kelimedir; asla bildirilmez).

Bulgu OLMAYAN: çekim («Mert'in», «Merte» — ad + ek; kesme eksikliği `spelling`'in işi),
<4 harfli adlar (Can/Cem/Ece: çok yoğun), yabancı harf içeren biçimler (`FOREIGN`), bozuk
span/parça belirteçler, tamamı büyük harfli yazım, sözlükte sıradan kelime olan seyrek biçim
(adlar kümesinde değilse), modelin «bilinçli» dediği (karakter adı yanlış söylüyor, şaka, başka
kişi/yer).

## 2. Girdi / kaynak

- Kitap metni: `_spelling_text.read_book` (`source.read`; satır sonu çizgileri birleşik,
  cümle başı işaretli, bozuk span'lar ayrılmış; bkz. spelling.md §2).
- Sözlük: `_spelling_text.Lexicon` (zeyrek/Zemberek + hunspell tr_TR; `EDITOR_HUNSPELL_TR`).
- Defter: `character.canonical_name/aliases` ve `character_mention.surface_name` (≥4 harf,
  büyük harfle başlayan, tamamı büyük olmayan kelimeler).
- Adlar kümesi: cümle ortasında büyük harfli biçimler ∪ kesme işaretli büyük harfli biçimler ∪
  defter; kesmeli ya da defterde değilse sözlükte sıradan kelime olmamalı.
- Sayfa görüntüsü: `document.render_page` (yalnız OCR kaynaklı belirteçler için).

## 3. Karar mekanizması

1. **Oluşum sayımı**: her büyük harfli belirteç adlar kümesinde değilse en uzun adla
   «ad + ek» (`SUFFIX_START`) olarak eşlenir; cümle başında ve sıradan kelimeyse atlanır.
2. **Aday**: biçimler sıklığa göre; seyrek biçim için ilk sık biçim (`occ[major] ≥ 2` ve
   `> occ[rare]`) Damerau-Levenshtein ≤ sınır ve çekim değilse aday; tek eşleşme (break).
3. **Model** (`book-director`, `_spelling_judge`, `Llm.choose`, tek belirteç, olasılık
   logprobs'tan, **iki sırada sorulup ortalanır**):
   - `printed` — **yalnız `t.src == "OCR"`**: sayfa görüntüsünde bizim biçim mi, düzeltilmiş
     biçim mi basılı (34 karakterlik bağlam); `p_printed < KEEP` → `dropped_not_printed`.
   - `is_error` — her aday: cümle (160 kr bağlam) + kapalı soru («tutarsız yazım mı, bilinçli
     mi»); `p_error < KEEP` → `dropped_as_intentional`.
4. Kalan → WARN.

## 4. Eşikler ve nereden okunduğu

Env/config yok; sabitler.

| eşik | değer | yer | anlam |
|---|---|---|---|
| `MIN_LEN` | 4 | sabit | daha kısa adlar karşılaştırılmaz |
| `LONG` | 8 | sabit | bu uzunluktan itibaren 2 harf fark |
| uzaklık sınırı | 1 (4–7) / 2 (≥8) | `run` | «measured: docs, Uzaklık» — sayı kodda yok |
| sık biçim | ≥ 2 oluşum ve > seyrek | `run` | — |
| `J.KEEP` | 0,5 | `_spelling_judge` | iki yönlü seçimin argmax'ı; ayarlanmış değer değil |
| `EDITOR_HUNSPELL_TR` | env; varsayılan `/app/data/hunspell/tr_TR` | `_dict_path` | sözlük yolu |

## 5. Bulgu biçimi

`page, severity=WARN, quote` (basılı biçim, birleşik ise «söy-/ledi»), `message`
(«…kitapta bu ad N kez «X» diye yazılıyor» / «…küçük harfle yazılmış»), `suggestion`
(sık biçim + aynı ek), `details{kind, form, book_form, book_form_count, form_count, source
(TEXT_LAYER/OCR), book_form_pages, p_printed?, p_error}`.

Stats: `skip_common_word, variant_pairs, raw, dropped_not_printed, dropped_as_intentional,
kept:ad_varyantı, kept:küçük_harf`.

## 6. Kendi hatası vs kitabın hatası

- Kitabın: iki tür bulgu.
- Kendinin/okuyucunun: OCR yanlış okuması (`printed` sorusuyla elenir; **metin katmanı**
  belirteçleri için bu soru sorulmaz — katman basılı sayılır), defterdeki yanlış karakter adı
  (yayın yönetmeni «karakter» kaydedilmişse ad kümesine girer), sözlüğün özel ad kararı.
- Exception (FAILED): sözlük yok (`RuntimeError`), model erişilemiyor.

## 7. ÖLÇÜM BEKLİYOR

Kodda «Measured precision: docs/son-okuma/name_spelling.md» ve «measured: docs, Uzaklık»
deniyor; sayı yok. Bu belgede de yok.

Plan:
```sh
ssh tt-gpu 'docker exec -i editor-mcp python -m editor.proofing <gen> --only name_spelling --dry' > names-<kitap>.json
```
1. Altı kitapta `stats.raw` adaylarının hepsi (düşenler dâhil — `--dry` yalnız kalanları basar;
   düşenler için `stats` sayıları) elle etiketlenir: gerçek tutarsızlık / bilinçli / çekim
   kaçağı / OCR / defter kirliliği.
2. Uzaklık sınırı: 1 vs 2 harf için 4–7 ve ≥8 harfli adlarda kesinlik ayrı sayılır.
3. Geri çağırma (enjekte): bir kitabın metninde bir adın bir oluşumu değiştirilir («Kâmil» →
   «Kamil», «Defne» → «defne») → bulgu çıkmalı.
4. `KEEP` 0,5 üzerinde `p_error` dağılımına bakılır; eşik ancak etiketli kümede seçilir.

## İlk gerçek koşu (2026-09-22)

«Levent Dünya Harikalarının Peşinde», nesil `60e5d717`: **3 WARN**; s.83 «Ağabe» — kitapta 21
kez «Ağabey». İnsan doğrulaması yok.

## 8. Bilinen yanlış alarm riskleri ve açık sorular

1. **Metin katmanı kesikleri**: «Ağabe» gibi bir harfi düşmüş biçim katmandan geliyorsa
   `printed` sorusu sorulmaz; basılı sayfada «Ağabey» olup katmanın harf düşürmüş olması
   (kırpılmış glif, ligatür) ayırt edilmez. Açık: katman adayları için de görüntü sorusu.
2. **Hitap sözcükleri**: «Ağabey», «Anne», «Dede» sıradan kelime; adlar kümesine ancak
   kesmeli yazım ya da defter ile girer. Defter bunları karakter kaydetmişse her küçük harfli
   «ağabey» `küçük_harf` adayı olur — `lex.common` süzgeci son savunmadır.
3. **Tek eşleşme**: seyrek biçim ilk uygun sık biçime bağlanır (`break`); iki sık ad birbirine
   1 harf uzaksa (Ayşe/Ayşa gerçek iki kişi) model «başka kişi» demeli.
4. **Aynı ad başka kişi**: kural tek kitap içinde; dizi düzeyi `series_canon`.
5. **`major_count`** ekli biçimleri de sayar (host eşlemesi), mesajdaki «N kez» bu toplamdır.
