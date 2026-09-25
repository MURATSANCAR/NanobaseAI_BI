# Kelime çeşitliliği ve yakın tekrar (`word_variety`) — ÖLÇÜM BEKLİYOR (sayılar var, editör kararı yok)

Kaynak: `src/editor/proofing/word_variety.py` (hat, model çağrıları), `_word_variety.py` (saf
parçalar), `_spelling_text.py` (okuma + Zemberek sözlüğü), `_spelling_judge.py` (`_ab`, `KEEP`) (v1).
Deterministik kök + model anlam ayrımı + deterministik aday + model yargı.

İstek (redaksiyon, 2026-09-23): «Bir kitaptaki tekil kelime haritası. *Göze girdi, gözüme toz kaçtı,
dolabın gözü* — burada üç farklı göz var; bunu fark edecek mi?»

## 0. Analiz — neden basit sayım yetmez

Bir kelime sayacı (boşlukla böl, say) Türkçe kitapta dört yerde yanılır:

| sorun | örnek | basit sayım ne yapar | doğrusu |
|---|---|---|---|
| **Çekim** (eklemeli dil) | göze / gözüme / gözü | üç ayrı kelime sayar; tekrarı göremez | tek kök: *göz* |
| **Çok anlamlılık / eş seslilik** | organ *göz*, dolabın *gözü*, *göze girmek* | üçünü tek kelime sayar; yanlış «tekrar» uyarır | üç anlam; birbirinin tekrarı değil |
| **Kök çakışması** | *yüz* (surat), *yüz* (100), *yüzmek* | ekli biçim hangisi? | sözlük çözümlemesi + kitabın kendi kullanımı |
| **Tekrar olmayan tekrar** | *yavaş yavaş*, *göz göze* (ikileme); özel adlar; *ve, bu, bir* | tekrar sayar | ikileme, ad ve işlev sözcüğü dışarıda |

Yani iş iki katmanlıdır: **kök** (biçimi sözlük maddesine indirmek; kural işi) ve **anlam** (aynı
kökün o cümlede hangi anlamda olduğu; bağlam işi — kuralla çözülmez).

### Değerlendirilen seçenekler

**Kök için:**
- Kelime listesi / kök kesme (stemmer): Türkçede «gözlük»ü «göz»e, «yüzdü»yü «yüz»e indirir —
  yanlış. **Reddedildi.**
- **Zemberek morfolojisi (zeyrek)**: editörde zaten var (yazım denetimi kullanıyor, MIT/Apache).
  Biçimi sözlük maddesine indirir, türünü (ad/fiil/sıfat/zarf/zamir…) verir; fiil maddesi mastardır
  («yüzmek»), ad «yüz» ile karışmaz. Birden çok çözümlemede kural: özel ad okuması düşer → en az
  türetmeli çözümleme (çekim grubu sınırı; türetilmiş sözcük kendi maddesidir: «gözlük» ≠ göz+lük,
  «yüzdü» = yüzmek) → kitapta tek çözümlü biçimleriyle sık olan kök («gözüme», «gözü» varsa «göze» →
  göz, pınar anlamındaki «göze» değil) → kısa gövde («koşa» → koşmak). Kökün çözümlemelerinde
  belirteç/zamir/bağlaç/edat/soru/ünlem varsa işlev sözcüğüdür («bir»). **Seçildi.**
  İlk sürüm «en uzun gövde» kuralıydı; sunucudaki gerçek Zemberek çözümlemesiyle denenince «göze»yi
  pınar maddesine, «koşa»yı sıfata, «bir»i içerik sözcüğüne götürdü (2026-09-25) — düzeltildi.

**Anlam için:**
- Sözlükteki anlam listesi (TDK): elde lisanslı bir anlam veritabanı yok; olsa da hangi anlamın
  kullanıldığını yine bağlam söyler. **Yok.**
- Gömme (embedding) + kümeleme: cümle gömmesi cümlenin konusunu taşır, sözcüğün anlamını değil;
  «dolabın gözü» ile «gözü dolabın içinde» aynı kümeye düşer. Küme sayısı da bir eşik ister.
  **Reddedildi.**
- **Model ile gruplama** (`book-director`, JSON şema): kökün bütün geçişleri bağlamlarıyla numaralı
  verilir; model anlamlara göre gruplar, her gruba kısa etiket ve (varsa) deyimi mastar hâliyle yazar.
  Karşılaştırmalı iş (geçişler yan yana) — tek tek «bu hangi anlam?» sormaktan tutarlı. Deyim
  («göze girmek») ayrı anlam olarak çıkar. **Seçildi.**

**Tekrar mesafesi için:**
- Sabit sözcük penceresi (ör. 30 sözcük): çocuk kitabında 30 sözcük üç sayfa, romanda iki satırdır.
  **Reddedildi.**
- İstatistik (kitap sıklığına göre «beklenenden yakın»): dil doğası gereği kümelenir (dolap sahnesinde
  «dolap» sık geçer); rastgele dağılım varsayımı her sahneyi işaretler. **Reddedildi.**
- **Cümle penceresi**: aynı ya da bir sonraki cümle. Okurun tekrarı fark ettiği mesafe; cümle boyu
  türle ölçeklenir. Ayar: `EDITOR_WORD_ECHO_SENTENCES` (0 = aynı cümle). **Seçildi.**

**Tekrarın kusur olup olmadığı:** yakın tekrar her zaman kusur değildir (vurgu, tekrar sanatı,
tekerleme, çocuk kitabında bilinçli yineleme, diyalog, başka söylenişi olmayan terim). Bunu kural
bilemez: son adım kapalı model sorusudur (diğer denetimlerle aynı biçim: tek harf, logprobs, iki
sırada sorulup ortalanır).

## 1. Kural — ne bulgudur, ne değildir

**Bulgu (WARN):** aynı kök **ve aynı anlam**, ardışık geçişler arasında en çok
`ECHO_SENTENCES` cümle, ve model «redaksiyonda düzeltilmeli» diyor (`p ≥ 0,5`).

**Bulgu olmayan:**
- farklı anlamlar yan yana («göze girdi … gözüme toz kaçtı»): tekrar değildir; sayısı
  `stats.near_repeat_different_sense`, örnekleri `stats.near_repeat_different_sense_examples`
  (editörün «fark etti mi» sorusunun cevabı buradadır);
- ikileme (art arda iki belirteç aynı kök: «yavaş yavaş», «göz göze», «koşa koşa»);
- özel adlar (kesmeli büyük harf; cümle ortasında büyük harf; cümle başında sözlükte yalnız özel ad);
- işlev sözcükleri (Zemberek türü bağlaç, zamir, edat, belirteç, soru, ünlem, sayı): haritada
  sayılır, tekrar adayı olmaz;
- sözlüğün çözümleyemediği biçim (yazım denetiminin işi): `stats.unknown_forms`;
- hikâye dışı sayfa (`page_role` FRONT_MATTER/NON_STORY), bozuk span, satır sonu parçası;
- modelin «bilinçli / gerekli» dediği tekrar: `stats.dropped_as_intentional`.

## 2. Girdi / kaynak

- Kitap metni: `_spelling_text.read_book` (`source.read`; satır sonu çizgileri birleşik, cümle başı
  işaretli, bozuk span'lar ayrılmış; bkz. spelling.md §2).
- Sözlük: `_spelling_text.Lexicon.analyses` (zeyrek / Zemberek): `dict_item.lemma`, `primary_pos`,
  `secondary_pos` (Prop), `stem`.
- Hikâye sayfası: `_continuity.story_pages`.

## 3. Karar mekanizması

1. **Geçişler** (`_read`): her belirteç → ad mı sözcük mü (`word_kind`) → küçük harf biçim →
   Zemberek adayları (`candidates`) → kök (`choose_lemmas`). Cümle numarası belirteç akışından
   (`sentence_ids`; sayfa sınırı cümleyi bölmez).
2. **Anlam** (model, `proof_word_senses` v1): kitapta ≥2 kez geçen her içerik kökü. Geçişler
   `SENSE_BATCH`'lik çağrılara paketlenir (`rounds`); büyük kök birden çok tura bölünür, sonraki tur
   önceki turun etiketleriyle sorulur («aynı anlamsa etiketi AYNEN kullan»). Cevap doğrulanır
   (`merge_senses`): numara bu çağrıda olmalı, bir numara bir gruba, bir grup başka kökün numarasını
   taşıyorsa her kök kendininkini alır; etiket ya da deyim eşitse var olan anlama katılır.
   Atlanan numaralar **bir kez** yeniden sorulur; yine atlanırsa haritada «belirsiz (model atamadı)»
   ve `stats.sense_unassigned`. Hiçbir kök ya da geçiş sessizce düşmez.
3. **Aday**: kök başına ikileme ayıklanır (`drop_reduplication`), aynı anlamlı geçişler cümle
   penceresiyle kümelenir (`clusters`).
4. **Yargı** (model, `_spelling_judge._ab`, tek harf, iki sırada ortalama): pasaj (ilk geçişin
   span'ından sonuncununkine) geçişler `[[ ]]` içinde; «düzeltilmeli mi / bilinçli mi».
5. **Öneri** (model, `proof_word_alternatives` v1): kalan her bulgu için aynı anlamı veren en çok
   5 karşılık (`suggestion`; uygulama metni değiştirmez).

## 4. Eşikler ve nereden okunduğu

| eşik | değer | yer | anlam |
|---|---|---|---|
| `ECHO_SENTENCES` | 1 | env `EDITOR_WORD_ECHO_SENTENCES` | ardışık iki geçiş arası en çok cümle (0 = aynı cümle) |
| `SENSE_BATCH` | 80 | env `EDITOR_WORD_SENSE_BATCH` | anlam çağrısı başına geçiş; yalnız çağrı boyu, kapsam değil |
| `CONTEXT_CHARS` | 70 | env `EDITOR_WORD_CONTEXT_CHARS` | anlam için geçişin iki yanında karakter |
| `PARALLEL` | 4 | env `EDITOR_WORD_VARIETY_PARALLEL` | aynı anda model çağrısı |
| `J.KEEP` | 0,5 | `_spelling_judge` | iki yönlü seçimin argmax'ı; ayarlanmış değer değil |
| MTLD eşiği | 0,72 | `_word_variety.mtld` | ölçünün yazındaki sabiti (McCarthy & Jarvis 2010) |

Hiçbiri tek kitapta ayarlanmadı; `ECHO_SENTENCES=1` redaksiyon alışkanlığıdır, ölçülene kadar öyle.

## 5. Bulgu biçimi

```json
{"page": 12, "severity": "WARN",
 "quote": "Gözü doldu. Sonra yine gözü doldu.",
 "message": "«göz» aynı anlamda (organ, görme) 2 kez yakın geçiyor: s.12 «Gözü», s.12 «gözü».",
 "suggestion": "gözleri, bakışı",
 "details": {"lemma": "göz", "sense": "organ, görme", "idiom": "", "count": 2, "pages": [12],
             "forms": ["Gözü", "gözü"], "p_flaw": 0.81,
             "passage_marked": "[[Gözü]] doldu. Sonra yine [[gözü]] doldu.", "window_sentences": 1}}
```

## 6. Kelime haritası (`proof_run.stats`)

Denetimin istatistiği haritanın kendisidir; kart servisi `GET /v1/books/{id}/proofing/word-map`
en yeni başarılı koşunun `stats`'ını verir. Kesme yok: bütün kökler, bütün sayfalar.

| alan | anlam |
|---|---|
| `map[]` | her kök: `lemma`, `pos`, `count`, `forms` {biçim: sayı}, `pages`, `ambiguous` (kök belirsizdi), `senses[]` (≥2 geçişli içerik kökü: `label`, `idiom`, `count`, `pages`, `example`) |
| `word_tokens`, `content_tokens` | sayılan sözcük / içerik sözcüğü geçişi |
| `distinct_lemmas`, `distinct_content_lemmas` | tekil kök sayısı (dağarcık) |
| `hapax_content_lemmas` | bir kez geçen içerik kökü |
| `polysemous_lemmas`, `idiom_senses` | birden çok anlamla geçen kök; deyim olarak geçen anlam |
| `mtld_lemma`, `mtld_form` | çeşitlilik (MTLD) kök ve biçim üstünden; TTR'nin aksine uzunluktan büyük ölçüde bağımsız, kitaplar arası karşılaştırılabilir |
| `near_repeat_different_sense(_examples)` | yakın ama farklı anlamlı geçişler (tekrar sayılmadı) |
| `unknown_forms[]` | sözlüğün çözümlemediği biçimler |
| `candidates`, `kept`, `dropped_as_intentional`, `sense_calls`, `sense_retried`, `sense_unassigned`, `skip_*` | hat sayaçları |

## 7. Maliyet (tahmin, ölçülmedi)

Anlam çağrısı ≈ (≥2 geçişli içerik kökü geçişleri) / 80. Resimli çocuk kitabı (1–3 bin sözcük):
5–20 çağrı. 300 sayfalık roman (~80 bin sözcük, ~40 bin içerik geçişi): ~500 çağrı + yargı (aday
başına 2 tek-token çağrı). Tek-token çağrılar ucuz; anlam çağrıları düşünme kapalı, JSON.

## 8. Ölçüm — BEKLİYOR (ilk gerçek koşu 2026-09-25)

**İlk koşu — «Dilek Ağacı» (64 sayfa, nesil `54cc9789`), insan kararı yok, yalnız sayı:**

| tur | ne değişti | bulgu | aday | bilinçli diye düşen | farklı anlamda yakın | çok anlamlı kök | deyim |
|---|---|---|---|---|---|---|---|
| dry 1 | ilk kod (en uzun gövde) | 154 | 207 | 53 | 44 | 171 | 79 |
| dry 2 | en az türetme + kapalı sınıf + büyük harf başlık + kitap sıklığı yargıda | 123 | 151 | 28 | 11 | 160 | 50 |
| gerçek | aynı kod, öneri ayıklama | 122 | 150 | 28 | 12 | 155 | 51 |

Kitap: 3.670 sözcük geçişi, 866 kök (766 içerik), 390 bir kez geçen, MTLD (kök) 87,3; anlam çağrısı 31,
atanamayan geçiş 0; süre ~6 dk. Tur 1'in kök hataları (gözle): «de» → demek, «ile» → il, «için» → iç,
«ben/o» içerik sözcüğü; tur 2'de yok. Kalan gözlem: «işte» → iş (Zemberek «işte»yi yalın işlev sözcüğü
vermiyor), «ünlü» → ün (sözlükte ayrı madde yok), «olmak/almak» çok ince anlam bölünmesi (almak 16 anlam).
Bulguların çoğu gerçek yakın tekrar görünüyor («yürüdüler … yürüdüm», «korktum … korktuğum»), ama
kesinlik editör kararıyla ölçülecek; çocuk kitabında bilinçli yinelemenin payı henüz bilinmiyor.


Yapılacak (gerçek kitapta, `--dry`):
`docker exec editor-mcp python -m editor.proofing <gen> --only word_variety --dry`

1. **Kök doğruluğu**: rastgele 200 geçiş, kök elle kontrol (özellikle `ambiguous`).
2. **Anlam ayrımı**: çok anlamlı çıkan her kök + tek anlamlı çıkan ilk 30 sık kök; etiket grupları
   doğru mu (yanlış birleştirme / yanlış bölme ayrı sayılır). «göz, yüz, el, baş, dil, kol, ağız»
   gibi bilinen çok anlamlılar ayrıca bakılır (ölçüm listesi; koda girmez).
3. **Tekrar bulgusu**: editör kararı (`proof_decision`) ile isabet — README'deki SQL.
4. **Kaçırılan**: bir bölüm elle redakte edilip bulgularla karşılaştırılır (geri çağırma).

## 9. Bilinen sınırlar ve sonraki adımlar

- **Kitap geneli aşırı kullanım** («aslında» 200 kez) v1'de bulgu değil: haritada sıklık var ama
  «bu kitapta fazla» demek için karşılaştırma derlemi gerekir. Aday derlem: editörün okuduğu öbür
  kitaplar (tür bazında kök sıklığı) — kitaba özel değil, veri. v2.
- **Portal ekranı** (2026-09-25): Son Okuma (M5) → «Kelime haritası» paneli (`src/canvas/editorial/WordMapPanel.tsx`);
  köprü `GET /api/v1/editorial/proofing/word-map?bookId=`. Sayfaya atlama yok (sayfa numarası metin).
- **Bölüm bazında çeşitlilik** (MTLD bölüm bölüm): bölüm sınırı defterde kesinleşince.
- Deyim yalnız model etiketinden gelir; deyim sözlüğü yok.
- Zemberek'in bilmediği biçimler (yöresel, uydurma) haritada `unknown_forms`'ta kalır; tekrarları
  aranmaz.
