# Metin bütçesi ve pencereleme — uzun ve kurgu dışı kitaplar

**Durum (2026-09-28):** kod ve sentetik test dalda; **ÖLÇÜM BEKLİYOR** — gerçek kitapta koşulmadı,
testler koordinatörde (editor-py imajı). Kaynak: `TUM-KITAP-TURLERI-ANALIZ.md` §4 ve §6.3;
grup belgesi `docs/analiz/ai-firsatlari/B-editoryal-kayitlar.md` (öneri 4), README «en değerli 20» #14.

## 1. Bugün kitap modele nasıl gidiyordu (kod okuması)

| Adım (iş akışı) | Kod | Girdi | Uzun kitapta |
|---|---|---|---|
| Karakter/olay adayları (7) | `knowledge.extract_chunk`, `text_chunks(size=4)` | 4 sayfalık parça | zaten pencereli — değişmedi |
| Kimlik (8) | `identity.propose` (+ onarım, denetçi, uzlaştırma) | bütün anmalar + anma geçen her sayfanın tam metni; denetçi aynısı + gruplar | bağlamı aşıyor (Babam Abdülhamid ~200k); 120'den çok anma listelenemiyor |
| Olay kipi (9) | `verify_event_modality` | 25'lik parti + sayfa özeti | parti — değişmedi |
| Olay birleştirme + sıra (9) | `merge_events` | bütün olaylar | 120 sınırı: Böcekleri 677 olayın 102'si sıraya girdi |
| Anlatı rolleri (9) | `assign_narrative_roles` | bütün zaman çizelgesi | 120 sınırı, sessiz |
| Tema birleştirme (10) | `link_emotions_and_themes` | bütün bölüm temaları | sınır + bağlam |
| Çelişki (defter) | `detect_contradictions` | karakter tablosu + bütün zaman çizelgesi | bağlam |
| Son okuma hakemleri | `proofing/{appearance,props,setting,timeline,dialogue,text_contradictions}` | **bütün kitap metni** her kapalı soruda | 130k üstünde her yargı düşüyor, denetim sessizce boş |
| Sürümlü özet (13) | `outputs.summarize` → `_condense` | doğrulanmış iddialar | zaten parça parça (80 000 karakter) — sınır ayara alındı |
| Kitap özeti (eski üretici) | `summary.book_summary` | alıntılar `[:60000]` | eski yol (`guard_legacy_producer`), dokunulmadı — açık |

Özet, karakter kartı, kurul/analiz raporu ve kategori kartı bu adımların çıktısından beslenir; kimlik ve
olay sırası uzun kitapta düşünce hepsi eksik ya da hiç çıkmıyordu.

## 2. Mekanizma (`src/editor/budget.py`)

1. **Bütçe:** `bağlam − cevap payı (max_tokens) − güvenlik payı`. Bağlam: `EDITOR_CONTEXT_TOKENS`, yoksa
   geçidin bildirdiği `--max-model-len`, o da yoksa sunulan 131072. Sayım önce tahmin (karakter /
   `EDITOR_BUDGET_CHARS_PER_TOKEN`); tahmin bütçenin `EDITOR_BUDGET_COUNT_ABOVE` payını geçince
   geçidin `/v1/tokenize` ucu (modelin kendi belirteçleyicisi, sohbet şablonu dahil) gerçek sayar ve
   bu metnin karakter/belirteç oranı pencere planında kullanılır. Geçit `tokenize`/`detokenize`'ı
   vLLM'in kökündeki uca iletir (`gateway._upstream_path`).
2. **Sığan girdi bugünkü yoldan:** tek çağrı, aynı istem, aynı işlem. Kısa kitapta fazladan çağrı da
   yapılmaz (tahmin eşiğin altındaysa sayım sorulmaz).
3. **Pencere planı (`plan`):** birimler okuma sırasında (sayfa ya da sayfa sırasındaki kayıt), birim
   bölünmez. Pencere, içindeki son bölüm başından kesilir (dolu payı ≥ `EDITOR_WINDOW_CHAPTER_SNAP`);
   bölüm başından kesilen pencere örtüşmez, bölüm içinden kesilen `EDITOR_WINDOW_OVERLAP_PAGES`
   (sayfa) / `EDITOR_WINDOW_OVERLAP_ITEMS` (kayıt) örtüşür. Pencere, cevabın listeleyebileceğinden
   **bir eksik** kayıt taşır (`items_room`): sınıra dayanan liste kesilmiş listeden ayırt edilemez.
4. **Birleştirme (kodla):**
   - etiket (anlatı rolü): iki pencere farklı derse olayın **kenardan en uzak** durduğu pencere kazanır;
     her çelişki `reading.role_conflicts` içinde (okumalar + pencere sayfaları);
   - sıra: pencereler sayfa sırasında, her olay ilk göründüğü yerde; iki pencere arasında sıra uydurulmaz;
   - grup (olay tekrarı, tema, kimlik): ortak üye taşıyan iki pencerenin grupları birleşir; **aynı
     pencerenin ayırdığı iki grup hiçbir zincirle birleşmez**; reddedilen bağlar raporlanır;
   - tema: pencere grupları ikinci düzeyde aynı istemle yeniden birleştirilir (map-reduce); grup hep
     özgün bölüm temalarının kimliğini taşır → kanıtı onların sayfa alıntıları;
   - çelişki: aynı kanıt çifti örtüşmede iki kez bulunursa bir kez yazılır.
5. **Kimlik (`identity.propose_book`):** sığıyorsa aynen `propose`. Sığmıyorsa anma geçen sayfalar
   üzerinden pencere (anma sayısı da sınırda); her pencerede bugünkü öneri/onarım/denetçi/kurtarma aynen;
   pencere kimlikleri kitap geneline çevrilir. Birleştirme:
   - örtüşen sayfadaki anmayı iki pencere yerleştirdiyse gruplar birleşir — tür/cinsiyet/birey↔topluluk
     çelişkisinde birleşmez, anma kenardan uzak pencerede kalır ve çelişki (UNCERTAIN) sayılır;
   - ortak anması olmayan gruplar (1. bölümde ve 20. bölümde geçen kişi) yalnız modelin önerisiyle ve
     **kod koruması** ile birleşir (`cross_guard`): iki taraf aynı pencerede görülmemiş olmalı
     (`SAME_WINDOW`), tür/cinsiyet/kapsam bağdaşmalı, alıntı kitapta normalleştirilmiş haliyle
     **birebir** bulunmalı (`QUOTE_NOT_IN_BOOK`) ve iki tarafın adını içermeli
     (`QUOTE_DOES_NOT_NAME_BOTH`). Grup tablosu uzunsa o da ada göre sıralanıp pencerelenir.
   - Bir pencere düşerse anmaları çözülmemiş kalır ve `audit.failed`'de listelenir; kitap düşmez.
6. **Son okuma hakemleri (`proofing/_continuity.JudgeText`):** bütün metin sığıyorsa her soruda aynı
   bütün metin (bugünkü davranış, önek önbelleği). Sığmıyorsa çiftin sayfaları ve komşuları, her yanda
   birer sayfa büyüyerek `EDITOR_JUDGE_CONTEXT_TOKENS`'a kadar; atlanan aralık metinde işaretli.
7. **Kanıt:** pencereli her sonuç sayfa aralığını taşır — tema iddiası `payload.windows`, kimlik
   iddiası `payload.windows` (+ kısa `identity_audit`), defter çelişkisi `payload.window`, son okuma
   bulgusu `details.judge_context` (görülen sayfa aralığı), adım sonucu `reading` (pencereler, düşenler,
   çelişkiler, reddedilen bağlar). Liste sınırına çarpan her cevap `cap_hits` ile sayılır.

Değişmeyenler: rakamı model üretmez; alıntılar defterde her zamanki gibi birebir aranır (`ledger`);
kitaba ya da türe özel kural yok; model yalnız editör geçidinden.

## 3. Ayarlar (env, `EDITOR_*`)

| Ayar | Varsayılan | Fiziksel anlamı |
|---|---|---|
| `CONTEXT_TOKENS` | 0 (geçitten / 131072) | modelin sunulan bağlamı |
| `BUDGET_SAFETY_TOKENS` | 2048 | şablon, şema yönlendirmesi, sayım hatası payı |
| `BUDGET_CHARS_PER_TOKEN` | 2,8 | tahmin oranı (analiz §4 ölçümü) |
| `BUDGET_COUNT_ABOVE` | 0,8 | bu payın altındaki tahmin sayılmadan sığar |
| `BUDGET_TOKENIZE` | 1 | 0: geçide sayım sorulmaz, tahmin kullanılır |
| `BUDGET_FORCE_TOKENS` | 0 | ölçüm için: girdi bütçesini bu sayıya indirir (sığan kitabı pencereli yoldan geçirmek) |
| `WINDOW_OVERLAP_PAGES` | 1 | bölüm içi kesimde örtüşen sayfa |
| `WINDOW_OVERLAP_ITEMS` | 8 | bölüm içi kesimde örtüşen kayıt (olay, tema) |
| `WINDOW_CHAPTER_SNAP` | 0,5 | pencerenin en az bu kadarı doluysa bölüm başından kes |
| `WINDOW_PARALLEL` | 4 | aynı anda koşan pencere çağrısı |
| `JUDGE_CONTEXT_TOKENS` | 32768 | uzun kitapta bir yargı sorusunun gördüğü metin |
| `SUMMARY_INPUT_MAX_CHARS` | 80000 | sürümlü özetin tek çağrıdaki iddia JSON'u (eski sabit) |

Hepsi ilk değerdir, gerçek kitapta ölçülmedi; ölçüm aşağıda.

## 4. Test (sentetik, `tests/test_budget_windows.py`)

600 sayfalık sentetik kitap (sayfa ~2 100 karakter, 40 sayfada bir bölüm): plan her sayfayı bir kez
sahiplenir, bütçeyi aşmaz, bölüm başında kesip örtüşmez, bölüm içinde örtüşür; 677 kayıtta pencere ≤ 119;
etiket çelişkisinde kenardan uzak pencere; sıra ilk görünüşten; aynı pencerenin grupları birleşmez;
yargı bağlamı kısa kitapta bütün metin, uzun kitapta çiftin çevresi ve bulguda görülen sayfalar.
Olay birleştirme: kısa kitapta **tek çağrı ve birebir aynı istem**; 700+ olayda her çağrı ≤ 119 kayıt,
her olay sırada bir kez, pencere sınırındaki tekrarlar birleşir. Anlatı rolleri: örtüşme çelişkisi
raporlanır. Kimlik: kısa kitapta aynen `propose`; 300 anmalı kitapta 3 pencere, örtüşmeyle birleşme,
pencereler arası birleşmede aynı-pencere ve uydurma alıntı reddi, bütün anmalar tek karakterde bir kez.

## 5. Gerçek kitapta ölçüm planı (koordinatör koşar)

Ön koşul: kod GPU sunucusuna kuruldu (`editorctl install && editorctl up`; geçit yeniden başlar), editör
testleri editor-py imajında (`apps/editor` kökünde) yeşil:
`python -m pytest tests/test_budget_windows.py tests/test_props.py tests/test_setting.py tests/test_timeline.py tests/test_dialogue.py tests/test_appearance.py tests/test_llm_limits.py tests/test_identity_repair.py -q`
ve ardından bütün `tests/`.

1. **Sayım ucu:** yönetici model açıkken geçit üzerinden `/v1/tokenize` bir `count` döndürüyor mu
   (`{"model":"book-director","messages":[{"role":"user","content":"deneme"}]}`). Dönmüyorsa
   pencereleme tahminle çalışır; sonuçta `fit.counted_by = "estimate"` görünür — bunu not et.
2. **Kısa kitap değişmedi:** mevcut resimli çocuk kitaplarından ikisi yeni nesil olarak koşulur.
   Ölçüt: `merge_events`, `narrative_roles`, `themes`, `contradictions`, `resolve_identity` adımlarında
   `model_call` sayısı eskisiyle aynı (her biri 1 + mevcut onarım/denetçi), adım sonuçlarında `reading`
   yok, regresyon denetimleri önceki nesille aynı sonuç.
3. **Zorla pencereli (aynı kitap, iki yol):** Böcekleri Seven Kadın bugün sığıyor —
   `EDITOR_BUDGET_FORCE_TOKENS=30000` ile yeni nesil. Karşılaştır (tek çağrılı nesille):
   karakter sayısı ve anma eşleşmesi (iki nesilde aynı karaktere düşen anma çiftleri, kesinlik/duyarlılık),
   sıraya giren olay (bugün 102/677 → hedef: kullanılabilir olayın tamamı), rol verilen olay (120 → tamamı),
   tema sayısı, defter çelişkisi, `cap_hits` = 0, `reading.failed` = [], `role_conflicts` sayısı,
   `cross_window.refused` nedenleri. Tek görsel okuma gürültüdür: aynı ayarla ikinci koşu da yapılır,
   fark iki aynı-ayar koşusu arasındaki farkla kıyaslanır.
4. **Uzun kitaplar:** Babam Abdülhamid (~200k token, bugün kimlikte düşüyor), Rüzgârın Ardından (~198k),
   Osmanlı Taşra Maliyesi (~482k, 544 s). Ölçüt: kitap biter; `model_call` hatalarında «context length»
   = 0; kimlik `audit.windowed`, pencere sayısı, düşen pencere 0; son okuma `judge_context.whole_book=false`
   ve `judge_failed` / aday oranı (bugün hepsi düşüyordu); GPU süresi kitap başına; editörün göz kontrolü
   için 20 rastgele pencereler-arası birleşme (alıntı + iki tarafın sayfaları) doğru mu.
5. **Eşikler:** `JUDGE_CONTEXT_TOKENS` (16k/32k/64k: yargı isabeti ve süre), `WINDOW_OVERLAP_*`,
   `WINDOW_CHAPTER_SNAP`. Sonuç bu belgeye yazılır; «ölçüm bekliyor» kalkar.

Yardımcı SQL (defter, salt okuma):

```sql
-- adım başına çağrı ve bağlam aşımı
SELECT prompt_name, count(*), count(*) FILTER (WHERE error ILIKE '%context length%') AS overflow
FROM ed.model_call WHERE generation_id = :gid GROUP BY 1 ORDER BY 1;
-- pencere kanıtı taşıyan iddialar
SELECT kind, count(*) FROM ed.claim WHERE generation_id = :gid AND payload ? 'windows' GROUP BY 1;
-- sıraya giren / rol verilen olay
SELECT count(*) FILTER (WHERE story_order IS NOT NULL) AS ordered,
       count(*) FILTER (WHERE narrative_role IS NOT NULL) AS roled, count(*) AS events
FROM ed.event WHERE generation_id = :gid AND merged_into IS NULL;
```

## 6. Bilinen sınırlar (bilerek)

- Pencereler arasında hikâye sırası uydurulmaz: geri dönüş (MEMORY) başka pencerenin olayından önceye
  alınmaz; pencereler sayfa sırasıyla dizilir.
- Anlatı rolü penceresine göre görecelidir; kitap geneli «doruk» tek pencerede seçilir.
- Defterdeki çelişki adımı birbirinden uzak iki penceredeki ifadeleri karşılaştırmaz; son okumanın
  `text_contradictions` denetimi olgu çiftlerini bütün kitapta kodla eşlediği için bu açığı kapatır.
- İlişkisel etiket («Babam») ile özel ad («X») farklı pencerelerdeyse ancak model alıntıyla önerirse birleşir.
- Eski üretici `summary.book_summary`'deki `[:60000]` alıntı kırpması (yalnız izlenmeyen nesiller) duruyor.
