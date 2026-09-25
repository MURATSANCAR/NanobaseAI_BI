# Yaş uygunluğu (`age_fit`) — kısmen ölçüldü

Kaynak: `src/editor/proofing/age_fit.py`, `_age_fit_text.py`, `_age_fit_ref.py` (v1).
Bu belgedeki her sayı o dosyalardan alınmıştır; kodda olmayan sayı yazılmadı.

## 1. Kural — ne bulgudur, ne değildir

İki bağımsız parça, ikisi de editör adayı üretir; hiçbiri kitap hakkında hüküm değildir.

**A. Okunabilirlik (deterministik).** Kitabın beyan ettiği yaş bandı için yayımlanmış kitapların
metni nasıl görünüyorsa onunla karşılaştırma. Bulgu olan:
- `LONG_SENTENCE`: bir cümle, bant kitaplarının cümlelerinin %99'undan uzun (kelime sayısı >
  `sentence_words_p99`). Satır sonunda bölünüp birleştirilmemiş kelime içeren cümle (`BROKEN`:
  «ne- sonra») sayılmaz — resim çevresinde okuma sırası belirsizdir, uzunluk yazarın değildir.
- `HARD_PAGE`: sayfa metni bant kitaplarının sayfalarının %99'undan zor; üç ölçünün (Ateşman
  alt %1, Bezirci–Yılmaz üst %1, ortalama cümle uzunluğu üst %1) **en az ikisi** eşiği aşıyor ve
  sayfada en az `page_min_sentences` cümle var.
- `BOOK_MEASURES` (her zaman INFO): kitap geneli sayılar ve bant içindeki yüzdelik yeri.

Bulgu OLMAYAN: kitap düzeyinde «bu kitap bu yaşa zor/kolay» hükmü. Gerekçe kodda:
formüller 6-10 kitaplarını yetişkin romanlarından yalnız AUC 0,70–0,73 ile ayırıyor
(`_age_fit_ref` docstring), hüküm için zayıf. Bir formülün kendi sınıf tablosu da kullanılmaz:
5–12. sınıf ders kitaplarında uydurulmuştur.

**B. Hassas içerik (model).** Bir pasajın beyan edilen yaş için editörün dikkatini gerektiren
içerik taşıyıp taşımadığı. Kapalı kümedeki kategoriler: `NONE, VIOLENCE, FEAR, UNSAFE_IMITABLE,
SUBSTANCE, DEATH_GRIEF, INSULT_DISCRIMINATION, SEXUAL`. Prompt'un kendisi «hikâyenin olağan
çatışması, hafif heyecan, eğlenceli abartı, sonucu gösterilip doğrusu öğretilen hata ve masalsı
tehlike» için A (NONE) der. Her bulgu tek bir pasajdır, kitap hakkında hüküm değil.

## 2. Girdi / kaynak

- Sayfa metni: `source.read(gid)` (span'lar; rol `heading` işaretli).
- Yaş bandı, yalnız kitabın kendi sözü, sırayla (`declared_band`):
  1. `claim` tablosu `kind='METADATA', subject='AGE_RANGE'`, durumu REJECTED/SUPERSEDED/
     EDITOR_REJECTED olmayan; editör onaylı/düzeltilmiş olan önce, sonra en yeni;
  2. `book.age_group`;
  3. sayfa metninde basılı bant (`BAND`: «6-10 yaş», «6 ile 10 yaş»; `BAND_PLUS`: «8+ yaş» → 8–18).
  Bant bulunamazsa INFO `NO_BAND`; okunabilirlik yalnız ölçülür, uyarı üretilmez.
- Referans derlem: `_age_fit_ref.REFERENCE` (koda gömülü yüzdelikler; bkz. §7).
- Hikâye dışı metin atılır (`story_paragraphs`): künye (`IMPRINT`, `IMPRINT_LINE`: ISBN,
  Sertifika No, ©, Tel:, www., Raf …), yazar biyografisi (`BIO`: doğum yılı + «doğdu» …),
  içindekiler (`TOC`: dört+ nokta + sayı), bozuk paragraf (`garbled`), başlık (`is_heading`:
  ≤6 kelime, cümle sonu yok, harflerin >%80'i büyük).

## 3. Karar mekanizması

**Okunabilirlik**: tamamen deterministik, `_age_fit_text.measure`. Hece = ünlü sayısı (ünlüsüz
belirteç 1); kelime = harf dizisi, kesme eki gövdeyle (`Ali'nin` tek kelime), rakam sayılmaz;
cümle sonu `. ! ? …` (dizi tek son), diyalog satırı ve paragraf sonu. `stream`: cümle ortasında
biten düzen bloğu bir sonrakine bağlanır (resim çevresine kırılmış satır). Formüller kodda:
Ateşman 1997 (`198.825 − 40.175·hece/kelime − 2.610·kelime/cümle`), Çetinkaya–Uzun 2010
(`118.823 − 25.987·… − 0.971·…`), Bezirci–Yılmaz 2010 (YOD). Yüzdelik yeri `_pct` ile
tablodan doğrusal ara değer.

**Hassas içerik**: sözlük seçer, model karar verir, ikinci çağrı doğrular.
1. `LEXICON` (genel Türkçe kökler, kitaba özel değil; her kök kelime başında: «bira» «biraz»ı
   yakalamaz) bir paragrafta geçerse paragraf + önceki paragrafın son 600 karakteri aday olur.
2. `Llm.choose("book-director", …, harfler A–H, prompt=PromptRef("proof_age_sensitive","1"))`:
   tek belirteç, olasılıklar logprobs'tan. **Tek sıra** (spelling/text_contradictions'taki
   iki sıralı sorgu burada yok). En olası harf A ise biter.
3. A değilse `Llm.chat("book-director", schema=QUOTE_SCHEMA, max_tokens=700, temperature=0,
   thinking=False, prompt=PromptRef("proof_age_sensitive_quote","1"))`: kategori + pasajdan
   **harfi harfine** alıntı + tek cümle neden. Kategori değişirse (`category_changed`) ya da
   alıntı pasajda yoksa (`ledger.norm` ile; `quote_not_verbatim`) aday düşer.
4. Eşzamanlılık `asyncio.Semaphore(4)`; bir pasajın çağrısı düşerse `failed` sayılır, kalanlar
   sürer.

## 4. Eşikler ve nereden okunduğu

Hiçbiri env/config'ten okunmaz; hepsi koda gömülü.

| eşik | değer | yer | fiziksel anlam |
|---|---|---|---|
| `sentence_words_p99` | 24 | `_age_fit_ref.REFERENCE["6-10"]` | 6-10 kitaplarında cümlelerin %99'u bu kelimeden kısa (kitap ağırlıklı); p99 ötesi çıkarım artefaktı (noktasız liste, şiir) |
| `sentence_words_p50` | 6 | aynı | mesajda gösterilen ortanca |
| `page_min_sentences` | 3 | aynı | 1–2 cümlelik sayfa oran vermez |
| `page_atesman_p1` | 42,5 | aynı | 14.051 sayfa, kitap ağırlıklı; sayfa Ateşman alt %1 |
| `page_yod_p99` | 18,63 | aynı | sayfa Bezirci–Yılmaz üst %1 |
| `page_asl_p99` | 15,67 | aynı | sayfa ortalama cümle (kelime) üst %1 |
| `book_pct` | tablolar | aynı | 288 kitap üzerinde kitap düzeyi yüzdelik (Ateşman/Çetinkaya/YOD/ASL, p1…p99) |
| HARD_PAGE için aşılan ölçü | ≥ 2 / 3 | `readability` | tek ölçü yetmez |
| «daha zor» (yalnız INFO ayrıntısı) | yüzdelik ≥ 95 (yod, asl) / ≤ 5 (atesman) | `readability` | mesaja yazılmaz, `details.harder` |
| referans için en az kitap | 30 | `_age_fit_ref` docstring | 30 altı bant referans almaz |
| bozuk paragraf | ≥5 belirteç ve parça payı ≥ 0,25 **ya da** ≥2 harf-rakam yapışması | `garbled` | 0,25: altı kitapta 4.201 paragrafın 19'u (13 karışık konuşma balonu, 2 iletişim/fiyat satırı, 4 bilerek hecelenmiş satır); 0,20'de sıradan cümleler düşmeye başlıyor |
| hassas: WARN için olasılık | ≥ 0,8 | `sensitive` | altı INFO |
| hassas: bağlam | önceki paragrafın son 600 kr | `candidates` | — |
| eşzamanlı çağrı | 4 | `sensitive` | — |

Bant eşlemesi (`reference_for`): beyan edilen bant, ölçülmüş bir bandın **içindeyse** (7-9,
6-10'un içinde) o referans kullanılır; başka bant (ör. 4-5, 9-12) yalnız kitap düzeyi INFO alır.
Bugün tek referans var: `"6-10"`.

## 5. Bulgu biçimi

| kind | severity | page | quote | details |
|---|---|---|---|---|
| `BOOK_MEASURES` | INFO | None | — | measures, band, reference, percentile_in_band, harder |
| `NO_BAND` | INFO | None | — | — |
| `LONG_SENTENCE` | WARN | sayfa | cümle (≤600 kr) | words, band, reference, threshold |
| `HARD_PAGE` | WARN | sayfa | — | measures, exceeds, band, reference |
| `SENSITIVE` | kategoriye göre, p ≥ 0,8 ise: VIOLENCE/UNSAFE_IMITABLE/SUBSTANCE/SEXUAL/INSULT_DISCRIMINATION → WARN; FEAR/DEATH_GRIEF → **her zaman INFO**; p < 0,8 → INFO | sayfa | modelin harfi harfine alıntısı | category, probability, probs (≥0,01 olanlar), lexicon, band |

Stats: `band, band_source, reference, dropped_paragraphs, book, pages_measured, pages,
book_percentile_in_band, sensitive{candidates, classified_not_none, quote_not_verbatim,
category_changed, failed, confirmed, by_category, results}`.

## 6. Kendi hatası vs kitabın hatası

- Kitabın hatası (bulgu): uzun cümle, zor sayfa, hassas pasaj.
- Denetimin kendi durumu (bulgu değil, stats/INFO): bant yok (`NO_BAND`), bant için derlem yok
  (INFO mesajında «karşılaştırma derlemi yok»), pasaj çağrısı düştü (`failed`), alıntı doğrulanamadı
  (`quote_not_verbatim`), kategori tutmadı (`category_changed`). Hiçbiri exception değildir;
  yalnız `source.read`/DB hatası ya da tüm model çağrılarının düşmesi koşuyu FAILED yapar.

## 7. Ölçüm

Kodda yazılı olanlar (`_age_fit_ref` docstring, 2026-09-22, GPU sunucusu `/data/organized`):
- Yayınevi derlemi 418 kitap; ≥300 kelimeli: 288 kitap «6-10 yaş» (ya da 7-9), 5 kitap «4-5
  yaş», 33 yetişkin romanı (bant yok). Metin katmanı `document.paragraphs_from_layout` ile
  paragraflanmış; analiz edilmiş altı kitapta iki yol 2,2 Ateşman puanı içinde uyuşuyor.
- Yüzdelikler kitap ağırlıklı. Cümle uzunluğu 6-10: p50 6, p90 11, p99 24, p99.5 39, p99.9 98;
  yetişkin romanı: p50 6, p90 14, p99 24, p99.5 28.
- Sayfa ölçüleri 14.051 sayfa üzerinde (≥3 cümleli sayfalar).
- Kitap düzeyinde ayırma gücü (AUC, 288 vs 33): Ateşman 0,73; Çetinkaya–Uzun 0,73;
  kelime/cümle 0,70; Bezirci–Yılmaz 0,70; uzun kelime payı 0,57.
- Bozuk paragraf eşiği: altı kitap, 4.201 paragraf (yukarıda).

### ÖLÇÜM BEKLİYOR

Kodda «measured (doc)» denip sayısı yazılmayanlar — bu belgede de yok, ölçülmedi:
1. **Sözlük geri çağırması**: `LEXICON`'un yakaladığı pasajlar, sınıflandırıcının kitabın
   **her** paragrafına koşulmasıyla karşılaştırılacak (kaç hassas pasaj sözlüğe takılmadı).
2. **Hassas içerik kesinliği** (altı kitap, v1): modül docstring'i «Measured precision (six
   books, v1): see docs» diyor; sayı kodda yok.
3. **LONG_SENTENCE / HARD_PAGE kesinliği**: her bulgu elle etiketlenmedi.

Plan:
```sh
ssh tt-gpu 'docker exec -i editor-mcp python -m editor.proofing <gen> --only age_fit --dry' > age_fit-<kitap>.json
```
- `stats.sensitive.results` içindeki her adayı (lexicon, probs, category, confirmed) gözle
  etiketle: gerçek / olağan çatışma / bağlam dışı. Kesinlik = confirmed içinde gerçek payı.
- Geri çağırma için `candidates(pages)` yerine tüm paragrafları `sensitive(..., only=…)` ile
  koştur (fonksiyon `only` parametresini bu amaçla alıyor), sözlüğün kaçırdıklarını say.
- `LONG_SENTENCE` bulgularını `BROKEN` dışı kalan düzen kırıklarına karşı gözle.

## İlk gerçek koşu (2026-09-22)

«Levent Dünya Harikalarının Peşinde», nesil `60e5d717`: **4 WARN + 2 INFO**; s.36'da «silah»
kaynaklı hassas içerik adayı. İnsan doğrulaması yapılmadı; bunlar sayıdır, isabet değil.

## 8. Bilinen yanlış alarm riskleri ve açık sorular

1. **Tek sıralı yargı**: hassas sınıflandırma harf sırasına duyarlı olabilir; spelling'deki
   iki sıra + ortalama burada yok. Ölçümde bakılacak.
2. **Sözlük genişliği**: `ateş`, `yak-`, `kaybol`, `yabancı`, `gizlice`, `karanlık` gündelik
   kelimeler; aday sayısı yüksek olur, maliyet modelde (kesinlik değil geri çağırma sorunu değil).
3. **Bant kaynağı tutarsızlığı**: `age_fit.declared_band` REJECTED/SUPERSEDED/EDITOR_REJECTED
   dışı her claim'i kabul ederken `layout._age_band` yalnız VERIFIED/EDITOR_APPROVED/
   EDITOR_CORRECTED alıyor; iki denetim aynı kitapta farklı bant görebilir.
4. **Referans yalnız 6-10**: 4-5 yaş (5 kitap) ve bantsız kitaplar hiç uyarı almaz; bu
   sessizlik «uygun» demek değildir, INFO mesajı bunu söyler.
5. **Derlem artefaktı**: referans metin katmanından; uçlar düzen artefaktı içerir, eşikler bu
   yüzden muhafazakâr (az uyarır). Gerçek uzun cümle p99'un altında kalabilir.
6. **Diyalog payı** ölçülüyor ama hiçbir eşiğe bağlı değil (yalnız INFO).
7. `BIO` kalıbı doğum yılı + «doğdu» arıyor: yazar tanıtımı bu kalıba uymuyorsa hikâye
   metnine karışır ve okunabilirliği bozar.

## 9. Stüdyoda yeniden kullanım (2026-09-25)

Kitap Tasarım Stüdyosu'nun yaş uygunluğu raporu (`production/age_report.py`) bu denetimin `readability` ve `sensitive`
fonksiyonlarını stüdyo işinin güncel metnine uygular (kopya kural yok). `sensitive` bunun için isteğe bağlı `llm`
alır (çağrı kaydı işin `provenance.jsonl`'ına). Rapora eklenen kelime düzeyi ve MEB/okul ölçütleri:
`docs/analiz/meb-uygunluk-olcutleri.md`.
