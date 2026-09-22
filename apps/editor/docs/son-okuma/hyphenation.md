# Satır sonu heceleme (`hyphenation`) — ÖLÇÜM BEKLİYOR

Kaynak: `src/editor/proofing/hyphenation.py`, `_hyphenation_tr.py`, `_layout_lines.py` (v1).
Deterministik; model çağrısı yok.

## 1. Kural — ne bulgudur, ne değildir

Basılı satır sonlarında kısa çizgiyle bölünen kelimelerin TDK hece sınırına ve satır sonu
kurallarına uygunluğu. Yeniden akıtılmış metne değil, PDF katmanındaki **gerçek satır
geometrisine** bakar: satır sonundaki çizgi, aynı metin çerçevesindeki sonraki satırla (ya da
sonraki sayfanın ilk satırıyla) birleştirilir, kelime yeniden kurulur.

| rule | severity | ne |
|---|---|---|
| `not_syllable_boundary` | ERROR | bölme hece sınırında değil («kütü-phane») |
| `single_letter` | WARN | satır sonunda ya da başında tek harf («a-», «-a») |
| `apostrophe_hyphen` | WARN | kesme işaretinden sonra çizgi («Ankara'-»); TDK: yalnız kesme kalır |
| `page_turn` | WARN | bölünen kelime yaprak çevrilince devam ediyor (tek PDF sayfası = recto → sonraki sayfa arkada) |
| `spread_break` | INFO | bölünen kelime karşı sayfada (aynı forma) devam ediyor |
| `lookalike_dash` | WARN | çizgi yerine en/em tire, figür tiresi ya da eksi (U+2012/2013/2014/2212) |
| `stray_hyphen` | WARN | satır **içinde** kalmış heceleme çizgisi («kitap- ları», metin yeniden akmış) |
| `proper_noun` | INFO | özel ad bölünmüş (TDK'ye aykırı değil; yayınevi üslubu çoğunlukla bölmez) |
| `apostrophe_suffix` | INFO | özel adın kesmeli eki bölünmüş («Ali'nin-ki»); bölme kesmede yapılabilir |
| `ladder` | INFO | art arda `LADDER`=3'ten fazla satır çizgiyle bitiyor (merdiven) |

Bulgu OLMAYAN: sert çizgili birleşik/hecelenmiş kelime («SEV-Mİ-YO-», «ön-»; `compound`),
büyük harfle başlayan devam («iki-» + «Üç»: yeni kelime, `not_a_break`), noktalama/rakam
sonrası çizgi («1990-», « -»), hecelenemeyen belirteç (harf dışı karakter, ünlüsüz; sayılır,
bildirilmez), TDK'nin ekli kısa çizgisi («-hatta söylenen- gözlüklü»: `stray_hyphen` kapsam
dışı).

## 2. Girdi / kaynak

- PDF: `_layout_lines.book(gid)` → `document._open_version` (PyMuPDF), `page.layer_health`.
- Satırlar: `page_lines` — yatay (`dir=(1,0)`) ve **gerçekten çizilen** glifler (MuPDF
  `char_flags`: 16 dolu, 32 konturlu, 64 kırpılmış; alfa 0 ve kırpılmışlar atılır; aynı yerde
  ikinci kez çizilen glif bir kez sayılır, kontur+dolgu «outlined» işaretlenir).
- `layer_unreliable` sayfalar (document.py: LETTER_SPACED / GARBLED_CHARACTERS /
  SCRAMBLED_WORDS) atlanır ve `stats.pages_skipped_unreliable_layer`'a yazılır.
- Özel Ad Sözlüğü: `character.canonical_name/aliases` (≥3 harf, büyük harfle başlayan
  kelimeler) + kitabın kendi yazımı (`_Vocab`: kelime küçük harfle hiç basılmamış ve cümle
  ortasında büyük harfle basılmışsa özel ad; cümle başındaki «Haklısınız» değil).
- Hece kuralı: `_hyphenation_tr` (TDK «Hece yapısı ve satır sonunda kelimelerin bölünmesi»):
  her hecede tek ünlü; iki ünlü arasında 0 ünsüz → ünlüler arasından, 1 → sonraki heceye,
  2 → birer, 3+ → yalnız sonuncusu sonraki heceye. `TDK_EXAMPLES` 27 örnek (araba …
  şiir) `self_check` ile doğrulanır: `python -m editor.proofing._hyphenation_tr`.

## 3. Karar mekanizması (deterministik)

1. Satır `HYPHENS` (`-`, U+00AD yumuşak çizgi — InDesign dışa aktarır, U+2010, U+2011) ya da
   `LOOKALIKE` ile bitiyor mu.
2. Devam satırı `_continuation`: aynı çerçevede, altta (`dy > 0.3×boyut`), en çok
   2,2 satır yüksekliği aşağıda, yatay örtüşen, **stil uyumlu** (`_same_style`: son glifin
   boyutu ile ilk glifin boyutu %20 içinde, rakam satırı değil). Yoksa sonraki sayfanın ilk
   satırı `_next_page_first` (aynı font, boyut %10 içinde) → `turn`.
3. `analyse_break`: kelime = satır sonundaki harf/kesme/çizgi dizisi; türü `compound` /
   `in_suffix` / `not_a_break` / `apos_hyphen` / `break`.
4. `break` için `tr.syllable_breaks(word)`: kesme noktası hece sınırında değilse ERROR (öneri:
   en yakın izinli sınır ya da «bölmeden»); sınırdaysa ama bir tarafta tek harf kaldıysa WARN.
5. Özel ad: `word[0]` büyük, tamamı büyük değil ve (kesmeli ek geliyor **ya da** karakter
   sözlüğünde **ya da** kitapta küçük harfle hiç basılmamış ve [cümle ortasında büyük harfle
   basılmış **ya da** bu satırda cümle başında değil]).
6. `stray_hyphen`: satır içinde «xx- yy» kalıbı; iki yarım hece sınırında, çizgi `HYPHENS`'ten,
   önce açılmış bir ekli çizgi yok ve birleşik kelime kitapta bütün olarak basılmış.

## 4. Eşikler ve nereden okunduğu

Hiçbiri env/config'ten gelmez; koda gömülü.

| eşik | değer | yer | anlam |
|---|---|---|---|
| `LADDER` | 3 | modül sabiti | InDesign varsayılan sınırı, Bringhurst |
| devam satırı uzaklığı | 0,3 < dy ≤ 2,2 × boyut | `_continuation` | altı kitapta ölçülen satır aralığı 1,1–1,6 × boyut |
| stil eşleşmesi | boyut farkı ≤ %20 | `_same_style` | folyo/gömme büyük harf değil |
| sonraki sayfa ilk satırı | aynı font, boyut ≤ %10 | `_next_page_first` | — |
| özel ad sözlüğü kelime uzunluğu | ≥ 3 harf | `_proper_names` | — |
| tek harf | cut < 2 ya da kalan < 2 | `allowed_breaks` | TDK: tek harf bırakılmaz |

## 5. Bulgu biçimi

Her bulgu: `page`, `severity`, `message`, `quote` («sol-parça- / sağ satırın başı»), `bbox`
(satır kutusu, 0..1000; ladder'da ilk satırdan son satıra), `suggestion` (doğru bölme ya da
«(bölmeden)»), `details.rule` (+ `word`, `cut`, `syllables`, `char`, `next_page`).

Stats: `pages, pages_skipped_unreliable_layer, line_end_breaks, checked, compound, unresolved
(devamı bulunamayan), not_syllabifiable, lines_unreadable_glyphs (PUA gliflı satır: özel kodlu
font), findings_by_rule`.

## 6. Kendi hatası vs kitabın hatası

- Kitabın: yukarıdaki on kural.
- Kendinin (stats'a yazılır, bulgu değil): devamı bulunamayan çizgi (`unresolved`), PUA
  font satırı (`lines_unreadable_glyphs`), hecelenemeyen kelime, güvenilmez katmanlı sayfa.
- Exception (koşu FAILED): PDF açılamıyor, DB.

## 7. ÖLÇÜM BEKLİYOR

Modül docstring'i «Precision measured on six books: see docs/son-okuma/hyphenation.md» diyor;
kodda sayı yok, bu belgede de yok. Ölçülen tek şey satır aralığı (1,1–1,6 × boyut, 2,2 eşiği
için).

Plan:
```sh
ssh tt-gpu 'docker exec -i editor-mcp python -m editor.proofing <gen> --only hyphenation --dry' > hyph-<kitap>.json
```
Altı kitapta:
1. Her `not_syllable_boundary` ERROR'u sayfa görüntüsüyle gözle: gerçek dizgi hatası /
   hece kuralının yakalamadığı yabancı kelime / devam satırı yanlış eşleşmiş.
2. `proper_noun` INFO'larında `_Vocab` kararı: gerçek özel ad payı.
3. `stray_hyphen` WARN'larında TDK ekli çizgisi kaçağı var mı.
4. `unresolved` sayısı: devam bulunamayan çizgi oranı (geri çağırma kaybı).
5. `page_turn` / `spread_break`: PDF sayfa 1 = recto varsayımı bu kitaplarda doğru mu
   (kapak sayfası PDF'e dâhilse parite kayar).

## İlk gerçek koşu (2026-09-22)

«Levent Dünya Harikalarının Peşinde», nesil `60e5d717`: **20 INFO**, WARN/ERROR yok. Kural
kırılımı kaydedilmedi (`stats.findings_by_rule` bakılmadı). İnsan doğrulaması yok.

## 8. Bilinen yanlış alarm riskleri ve açık sorular

1. **Yabancı kelimeler**: TDK kuralı Batı kökenli kelimeleri de aynı kurala bağlar
   (`kont-rol`), ama İngilizce ad/marka («Google», «Sherlock») ünlü sayısına göre hecelenir;
   ERROR çıkabilir.
2. **Sayfa paritesi**: `page_turn` PDF'in 1. sayfasını recto sayar; kapak PDF'te varsa ters
   döner (WARN ↔ INFO yer değiştirir).
3. **İki sütun / konuşma balonu**: `_continuation` yatay örtüşme ister; balon içindeki kısa
   satırlarda devam bulunamayabilir (`unresolved`) ya da yanlış balona bağlanabilir.
4. **Özel ad kararı kitabın yazımına bağlı**: yalnız cümle başında geçen bir ad küçük
   harfle hiç basılmamış sayılır ve `_sentence_start(before)` bakılır; `before` bir önceki
   satırdan alındığında noktalama kaybolmuş olabilir.
5. `LOOKALIKE` çizgiyle biten satırda kelime bölünmemiş olabilir (cümle içi tire satır sonuna
   denk gelmiş); `analyse_break` bunu sağ satır büyük harfle başlıyorsa eler, küçük harfle
   başlıyorsa WARN üretir.
6. Modül tablosundaki «WARN: hyphen after an apostrophe» için `continue` var: aynı satır
   için `proper_noun`/`page_turn` bakılmaz — bilinçli mi belirsiz.
