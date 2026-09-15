# Anlam kapısı (obligation gate) — uçtan uca tasarım ve bugünkü hatalar

Tarih: 2026-09-15. Kapsam: `backend/semantic_layer/runtime/audit.py` (`unmet_obligations`, `audit_sql`) ve onu çağıran
`CompilerRouter.compile` + `Runtime.ask`. Hiçbir madde bir müşterinin tablo adına bağlı değildir; örnekler
katalogdaki entity/kolon adlarıyla yazılmıştır, kural her kaynağa aynı uygulanır.

## 1. Kapı ne yapmalı

Soru çözümlenince elde bir **yükümlülük listesi** olur: "bu cevap şunları sağlamak zorunda". SQL hangi
derleyiciden gelirse gelsin (deterministik, model, onarım sonrası) kapı her yükümlülük için SQL'in içinde
**kanıt** arar. Kanıt yoksa cevap verilmez. Yanlış kabul (kanıtsız sayı) yanlış retten (doğru cevabın
reddi) daha pahalıdır; ama ikisi de ölçülmelidir, bugün yalnız biri ölçülüyor.

Yükümlülük türleri (tam liste, bugün eksik olanlar işaretli):

| Tür | Sorudan nasıl doğar | Bugün |
|---|---|---|
| Değer filtresi | "iade", "E-TİCARET kanalı" → `ENTITY.KOLON op {değerler}` | var |
| Varsayılan filtre | Katalogdaki iş kuralı: "iptal edilmemiş" → `ENTITY.CANCELLED = 0` | var |
| Dönem | "2026", "Ocak–Ağustos", "bu yıl" → `[başlangıç, bitiş)` + tarih bağlaması (`temporal_binding`) | var, dar |
| Karşılaştırma | "geçen yıla göre" → iki dönem ayrı sütunlarda | var, dar |
| Ölçü formülü | "net ciro" → sertifikalı formül | **yok** |
| Kırılım | "ay bazında", "kanal bazında" → GROUP BY anahtarı | **yok** |
| Sıralama + sınır | "en çok … 10" → ORDER BY ölçü DESC, LIMIT 10 | **yok** |
| İlişki önceliği | başlık/satır çakışmasında hangi referans kazanır | var |
| Yokluk | "hiç satılmayan" → anti-join sözleşmesi | var (birebir eşleşme) |

## 2. Ölçüm — kapı bugün ne yapıyor

İki ölçüm yapıldı (2026-09-15, `nanobase-direct`, katalog sürümü canlı):

**a) Şekil matrisi** — aynı doğru cevabın 17 farklı SQL şekli + reddedilmesi gereken 11 şekil, sentetik
yükümlülük (`INVOICE.CANCELLED = 0`, dönem 2026, karşılaştırma 2026/2025).

| Sonuç | Sayı |
|---|---|
| Doğru SQL kabul | 4 / 17 (`flat`, `flat_alias`, `filter_in_list`, `cmp_case_pivot`) |
| **Doğru SQL ret** | **13 / 17** |
| Yanlış SQL ret | 10 / 11 |
| **Yanlış SQL kabul** | 1 / 11 (`SUM(CASE WHEN CANCELLED=0 …)` — SUM için doğru, COUNT/AVG için yanlış olurdu) |

Reddedilen doğru şekiller: filtre CTE içinde, türetilmiş tablo içinde, iki CTE'de de var, UNION'un iki
kolunda da var, filtre INNER JOIN ON'da, `YEAR(DATE_)=2026`, `BETWEEN`, `<= '2026-12-31'`,
`ISNULL(CANCELLED,0)=0`, `CANCELLED <> 1`, karşılaştırma dönem-başına-CTE, karşılaştırma `GROUP BY YEAR`.

**b) Golden set** — 48 vakadan SQL'i olan 21'inin *beklenen* (doğru kabul edilen) SQL'i kapıdan geçirildi:

| Sonuç | Sayı |
|---|---|
| Kabul | 3 / 21 |
| Ret — kapı hatası | 9 |
| Ölçülemedi — golden satırı bozuk (SQL çift JSON kodlanmış) | 9 |

Yani: **kalite kapısı (`quality-gate.py`) yalnız tablo isabetini ölçüyor; doğru SQL'in kapıda reddedilmesini
hiçbir şey ölçmüyor.** Bu tasarımın ilk çıktısı o ölçümün eklenmesidir.

## 3. Bulunan hatalar

Sınıflar: **YR** yanlış ret, **YK** yanlış kabul, **EY** eksik yükümlülük, **S** süreç.

1. **YR — Kanıt yalnız dış SELECT'in WHERE'inde aranıyor** (`audit.py` `required_filters` ve dönem bloğu).
   `_AnswerScope` bir CTE/alt sorguyu tek entity'ye indirger ama içindeki WHERE'i okumaz. Modelin ve
   golden'ın en sık kalıbı ("önce CTE'de topla, sonra birleştir" — kritik `FANOUT` uyarısının *istediği*
   kalıp) bu yüzden her zaman reddediliyor. Kritik ile kapı birbirine zıt kalıp dayatıyor.
2. **YR — Dönem yalnız `>= başlangıç AND < bitiş` biçiminde tanınıyor** (`_bounded_columns`). `YEAR()=`,
   `BETWEEN`, `<= son gün`, `DATEFROMPARTS`, `CAST(… AS DATE)` reddediliyor. Aralık cebiri yok.
3. **YR — Dönem kanıtı için kaynağın kendi kapsamı sayılmıyor.** Profil `time_window` (kaynağın ölçülmüş
   tarih aralığı) biliniyor ama kapı kullanmıyor. Dönem-bölümlü kaynaklarda (her dönem ayrı tablo/şema)
   tarih filtresi olmayan doğru sorgu reddediliyor (golden: "en çok satan 10 kitap", "kanal bazında net ciro").
   Genel kural: kaynağın kapsamı ⊆ istenen dönem ise dönem kanıtlıdır.
4. **YR — Sertifikalı görünümlerin sözleşmesi yok.** `v_monthly_sales` gibi bir görünüm zaten filtreli ve
   dönemli olabilir; kapı görünümün entity'sini bilmediği için her yükümlülüğü karşılanmamış sayıyor.
   Katalog bir kaynağa "bu yükümlülükleri zaten sağlar" diyebilmeli (görünüm sözleşmesi).
5. **YR — Filtre eşdeğerlikleri tanınmıyor.** `ISNULL(k,0)=0`, `k <> 1` (iki değerli alan), `k IN (0)` /
   `k = 0` (bu var). Değer alanı profilde (`value_labels`, `sentinel_values`) olduğunda tümleyen hesaplanabilir.
6. **YR — INNER JOIN ON içindeki filtre kanıt sayılmıyor**; LEFT JOIN'in sağ tarafındaki ise sayılmamalı
   (bu ikincisi doğru çalışıyor). Kural join türüne göre olmalı, yerine göre değil.
7. **YR — Karşılaştırma yalnız "CASE-pivot" şeklini tanıyor** (`_period_outputs`). Dönem-başına CTE ve
   `GROUP BY dönem` şekilleri reddediliyor; ikisi de yaygın ve doğru.
8. **YR — Sınırsız dönem yükümlülüğü** ("son günler" → start/end `None`) hiçbir SQL ile karşılanamıyor.
   Çözümleyici sınır üretemiyorsa bu bir netleştirme olmalı, kapıya ulaşmamalı.
9. **YR — Çözümleyici netleştirmesi kapıda tekrar ret üretiyor** (`sq.unhandled/clarification`). Router
   zaten netleştirme döndürüyor; kapıdaki kopya, golden gibi harici doğru SQL'in ölçülmesini engelliyor ve
   "açılan", "alan" gibi sıradan Türkçe sözcükler niteleyici sanılınca cevap tamamen kapanıyor.
10. **YK — İki ölçü iki entity'de ise dönem yükümlülüğü hiç doğmuyor.** `temporal_binding` yalnız tek
    ölçü entity'si varken kuruluyor (`resolver.py` ~688). "Ay bazında iskonto oranı ve ortalama fatura"
    sorusunda dönem denetimi **yok**: yanlış yılı toplayan SQL geçer.
11. **YK — CASE içindeki filtre toplamsal olmayan agregalar için de kanıt sayılıyor.** `COUNT(*)`, `AVG`,
    `MIN` içinde `CASE … ELSE 0` satırı dışlamaz, sıfır olarak sayar. Kural agregaya göre olmalı.
12. **EY — Ölçü formülü denetlenmiyor.** "Net ciro" için `SUM(NETTOTAL)` yazan SQL geçer; sertifikalı
    formül işaret/koşul taşıyor olsa bile. (`net-ciro-line-formula-wrong` olayı buradan çıkmıştı.)
    Karşılaştırma bloğunda formül karşılaştırması var, tek dönemde yok.
13. **EY — Kırılım denetlenmiyor.** "Ay bazında" sorusuna tek satır dönen SQL geçer; `sq.grain` ve
    `sq.group_by` kapıda okunmuyor.
14. **EY — Sıralama ve sınır denetlenmiyor.** "En çok … 10" için `sq.limit=10` var, `ORDER BY` yönü ve
    `LIMIT` kontrol edilmiyor.
15. **S — Kapı reddi onarım turuna girmiyor.** Kritik (`FANOUT`) ve dry-run hatası modele geri gidip bir
    onarım alıyor; `INCOMPLETE_ANSWER` anında dönüyor (`app.py` ~738). Gerekçe metin olduğu için modele
    verilecek yapılı bir talimat da yok.
16. **S — Kapı reddi ölçülmüyor.** `quality-gate.py` yalnız tablo recall'u sayıyor. Golden beklenen SQL'in
    kapıdan geçme oranı ("kapı recall") yok; 9 golden satırı bozuk ve kimse fark etmemiş.
17. **S — Mutasyon testi tek şekil.** `tests/stress/obligation_mutations.py` yalnız düz SELECT üretiyor;
    CTE/alt sorgu/UNION/JOIN ON şekilleri yok. `test_obligations.py` de öyle.
18. **S — Aynı varsayılan filtre slotu iki kez** (`stline default cancelled` ×2) geliyor; zararsız ama
    gerekçe metnini şişiriyor ve ileride "iki kez kanıtla" hatasına açık.

## 4. Tasarım — yükümlülüğü cevabın kaynaklarına taşımak

Temel fikir: kanıt, **cevabı üreten her taban tablo oluşumuna giden yolda** aranır; SQL'in hangi katmanda
yazıldığı önemsizdir.

### 4.1 Kaynak ağacı

sqlglot `build_scope` ile kök kapsamdan başlanır. Her kaynak şu türlerden biridir:

- **Taban tablo** → entity (`logical_table`), profil (`time_window`, PK, değer alanları).
- **Türetilmiş** (CTE, alt sorgu, görünüm sözleşmesi olmayan görünüm) → kendi kapsamına iner; çıktı
  kolonlarının kökeni (lineage) takip edilir (`SELECT CANCELLED AS iptal` → dış `iptal=0` içerideki
  `CANCELLED` için kanıttır).
- **UNION** → her kol ayrı kaynaktır; yükümlülük **her kolda** sağlanmalı.
- **Sözleşmeli kaynak** (katalogda kayıtlı görünüm/küp) → sağladığı yükümlülükler beyan edilmiştir;
  içine inilmez.

Kök kapsamdan erişilmeyen CTE'ler ağaçta yoktur (bugünkü doğru davranış korunur).

### 4.2 Taşınan koşul kümesi

Bir taban tablo oluşumuna giden yolda toplanan **AND-bağlaçları**:

- Her ara kapsamın `WHERE`'i (kolon kökeni o tabloya iniyorsa);
- INNER JOIN'in `ON`'u; LEFT/RIGHT JOIN'de yalnız **koruyan** tarafın koşulu (sağ tarafın ON koşulu satır
  düşürmez, sayılmaz);
- `OR` dalları: koşul her dalda varsa sayılır, yoksa sayılmaz (bugünkü doğru davranış);
- `HAVING`: satır filtresi değil, sayılmaz;
- Toplamsal agregaların (`SUM`, koşullu `COUNT(CASE … THEN 1 END)`) CASE'i: yalnız o çıktı için kanıt
  (pivot); `AVG/MIN/MAX/COUNT(*)` içinde sayılmaz.

Koşullar **kanonik biçime** getirilir: `ENTITY.KOLON op {değerler}`; `IN (x)` ≡ `= x`; `ISNULL(k,d)=v`
→ `k=v` (d=v ise `k IS NULL` de dahil); iki değerli/enum alanda `k <> a` → `k IN (alan−{a})` (alan
profilden: `value_labels`, gözlenen değerler, `sentinel_values`).

### 4.3 Filtre yükümlülüğü

`ENTITY.KOLON op {V}` için: cevabın kaynak ağacındaki **her** `ENTITY` taban oluşumunun taşınan
kümesinde eşdeğer koşul olmalı. Eşdeğerlik: aynı kolon, uyumlu operatör, aynı değer kümesi; ya da
katalogdaki `equivalent_bindings` üzerinden başka entity'de (bugünkü kural). Entity hiç yoksa → "ölçü
bu entity'de değil" gerekçesi (formül yükümlülüğüyle birlikte okunur).

### 4.4 Dönem yükümlülüğü — aralık cebiri

Taşınan kümeden tarih kolonu başına bir **aralık** çıkarılır: `>=`, `>`, `<`, `<=`, `BETWEEN`,
`YEAR(k)=y`, `YEAR(k)=y AND MONTH(k)=m`, `DATEFROMPARTS`, `CAST(k AS DATE)` hepsi `[a, b)`'ye çevrilir.
Kaynağın kendi kapsamı (`time_window`) aralığa **kesişim** olarak eklenir. Yükümlülük: doğru kolonda
(`temporal_binding` + alternatifleri, join kanıtıyla) elde edilen aralık == istenen aralık. Kaynak
kapsamı istenen aralığın içindeyse SQL'de tarih koşulu olmasa da kanıtlıdır.

`temporal_binding` **ölçü başına** kurulur (madde 10): iki entity'li soruda iki bağlama, her biri kendi
ölçüsünün kaynaklarında aranır.

### 4.5 Karşılaştırma

"İki dönem ayrı çıktı" kanıtı üç şekilden herhangi biriyle sağlanır:
(a) CASE-pivot (bugünkü); (b) dönem-başına türetilmiş kaynak: iki kaynak, her birinin taşınan aralığı bir
döneme eşit, çıktıda ikisinden birer sütun; (c) `GROUP BY dönem-anahtarı` + taşınan aralık iki dönemin
birleşimine eşit. Üçünde de ölçü formülü her sütun için karşılaştırılır (bugünkü `expected <= proven`).

### 4.6 Yeni yükümlülükler

- **Formül:** her `METRIC` slotunun formülü, cevabın ilgili çıktı sütununda `_normalise_formula` ile
  karşılaştırılır. Eşdeğerlik sınıfı: formülün CASE koşulu WHERE'e taşınmış olabilir (taşınan küme ile
  birlikte okunur), CTE'de hesaplanıp dışarıda yeniden adlandırılmış olabilir (lineage).
- **Kırılım:** `sq.grain`/`sq.group_by` varsa kök kapsamda (ya da tek türetilmiş kaynakta) GROUP BY
  anahtarı ilgili kolonu/tarih kırılımını içermeli; sütun sayısı değil, anahtar denetlenir.
- **Sıralama/sınır:** `sq.limit` varsa `LIMIT/TOP` eşit ve `ORDER BY` ölçü sütununda, yön `order_desc`.

### 4.7 Yapılı sonuç

`unmet_obligations` metin listesi yerine `Unmet(kind, entity, column, expected, found_at, hint)` döner;
metin bundan üretilir. `hint` modele onarım talimatıdır ("`INVOICE` kaynağının WHERE'ine
`CANCELLED = 0` ekle"). Kapı reddi kritik gibi **bir onarım turu** alır; ikinci ret kesindir.

### 4.8 Değişmeyen ilkeler

- Kanıt bulunamayan yapı (bilinmeyen fonksiyon, dinamik SQL) **kapalı** kalır; ama gerekçe sınıfı
  "anlaşılmayan yapı" olur, "eksik filtre" değil.
- Katalog dışı bilgi kullanılmaz; değer alanı, kapsam penceresi ve sözleşmeler profil/katalogdan gelir.
- Deterministik derleyicinin SQL'i de aynı kapıdan geçer.

### 4.9 Dış incelemeden sonra sıkılaştırılan noktalar (2026-09-15)

- **Aralık eşitliği tip bilir.** `<= '2026-12-31'` ve `BETWEEN … AND '2026-12-31'` yalnız kolon tipi `date`
  ise günün sonuna kadar sayılır; `datetime` kolonda gece yarısında biter ve dönem eşit çıkmaz → ret.
  Tip profilden (`ColumnProfile.data_type`) gelir; bilinmiyorsa kapalı.
- **Ölçülmüş pencere kanıt değildir.** `time_window` bir istatistiktir; eksik yükleme dar pencere üretir ve
  filtresiz sorgu geçerdi. Yalnız **beyan edilmiş** kapsam (görünüm/kaynak sözleşmesi, adım 6) tarih
  filtresinin yerine geçer. Mekanizma hazır (`sources_from(profiles, declared=…)`), beyan yok → kural kapalı.
  Bunun karşı yüzü: beyan edilmiş 2026 tablosundan 2025 okuyan karşılaştırma reddedilir.
- **Anlaşılmayan yapı ayrı gerekçe.** Türetilmiş/hesaplanmış kolon üzerinden yazılmış bir koşul aşağı
  taşınamaz; ret "eksik filtre" değil "anlaşılmayan yapı: … türetilmiş bir kolon üzerinden yazılmış" der.
  Kendi ayrıştırıcı yok: sqlglot `build_scope` + yalnız düz geçen kolon kökeni.
- **Formül / kırılım / sınır yükümlülükleri** kodda ama varsayılan kapalı (`SEMANTIC_GATE_STRICT=1` ya da
  `strict=True`). Kapı recall'u hedefe gelmeden açılmaz (adım 7).
- **EXISTS yol değildir**; yokluk sözleşmesi ayrı türdür.
- **Çift varsayılan filtre** çözümleyicide tekilleştirildi (kapıda değil).
- **Karşılaştırma dönem bağlaması ölçü başına**: `temporal_binding["also"]` ile ikinci entity de bağlanır.

## 5. Doğrulama planı

1. **Kapı recall ölçümü** `quality-gate.py`'ye eklenir: golden `expected_sql`'lerin kapıdan geçme oranı;
   düşüş fatal. Önce 9 bozuk golden satırı düzeltilir (çift kodlanmış JSON).
2. **Şekil matrisi** `backend/semantic_layer/tests/test_gate_shapes.py` olarak eklendi: 17 doğru şekil
   kabul, 11 yanlış şekil ret (bugün başarısız olanlar `xfail(strict=True)`; düzeltme her birini çevirir).
3. `tests/stress/obligation_mutations.py` şekil boyutu kazanır (aynı mutasyonlar × 6 şekil).
4. Canlı sorgu günlüğünden son 30 günün `INCOMPLETE_ANSWER` kayıtları yeni kapıdan yeniden geçirilir;
   kaç tanesinin artık geçtiği ve **elle örneklenmiş 20 tanesinin gerçekten doğru olup olmadığı** raporlanır.

## 6. Uygulama sırası

| Adım | İçerik | Süre |
|---|---|---|
| 1 | Ölçüm: golden düzeltme + kapı recall + şekil testi (xfail) | 2 sa |
| 2 | Kaynak ağacı + taşınan koşul kümesi; filtre yükümlülüğü buna taşınır (madde 1, 5, 6, 11, 18) | 1 gün |
| 3 | Aralık cebiri + kaynak kapsamı + ölçü başına bağlama (madde 2, 3, 8, 10) | 1 gün |
| 4 | Karşılaştırma şekilleri b/c (madde 7) | ½ gün |
| 5 | Yapılı sonuç + onarım turu + netleştirmenin kapıdan çıkarılması (madde 9, 15) | ½ gün |
| 6 | Görünüm sözleşmesi (madde 4) — katalog şeması gerekir, ayrı karar | 1 gün |
| 7 | Yeni yükümlülükler: formül, kırılım, sınır (madde 12–14) | 1–2 gün |

Her adım kapı recall'u ve şekil testini çalıştırır; recall düşerse adım geri alınır.

## 7. Uygulama durumu (2026-09-15)

Adım 1–5 uygulandı: `audit.py` yeniden yazıldı (kaynak ağacı `_walk`, taşınan koşul kümesi
`_Occurrence.preds/intervals`, aralık cebiri `_intervals`, karşılaştırma a/b/c, yapılı `Unmet` + `gate_report`,
`CompilerRouter.compile` içinde bir onarım turu, netleştirme kapıdan çıkarıldı). Ölçüm araçları: `test_gate_shapes.py`
(şekil matrisi, xfail kalmadı), `obligation_mutations.py` 23 şekil × 1000 (23.000/23.000), `golden-eval.py`
`gate_recall`/`gate_refused`, `quality-gate.py` kapı recall (düşüş fatal) + yanlış kabul sayacı (≥1 fatal).
Golden kapı geçişi 3/21 → 14/21. Kalan 7 ret ve nedenleri:

| Vaka | Neden | Adım |
|---|---|---|
| Kanal bazında net ciro, Yayınevi bazında net ciro+marj, Aylık net satış | görünümden okuyor (`v_*`), sözleşme yok | 6 |
| En çok satan 10 kitap, Kanal bazında brüt kâr marjı | tarih filtresi yok; kaynak kapsamı beyan edilmemiş | 6 |
| Müşteri yoğunlaşması, Yayınevi YTD | `measure_expressions` kuralı (önceden var); YTD üst sınırı bugüne değil yıl sonuna | 7 / golden |

Adım 6 (beyan/görünüm sözleşmesi) ve 7 (strict yükümlülükler) açık.

## 8. Adım 6 tasarımı — kaynak kapsamı beyanı ve görünüm sözleşmesi (2026-09-15)

### 8.1 Ölçülen gerçek (neden ölçülmüş pencere beyan olamaz)

Katalogdaki `time_window` (iş tarihi kolonunun min/max'ı), canlı kaynakta:

| Tablo | Ölçülen pencere | Dönem dışı satır (sorgulandı) |
|---|---|---|
| `LG_411_01_INVOICE` (2026) | 2026-01-01 → 2026-08-17 (yedek günü) | 0 |
| `LG_411_01_STLINE` (2026) | 2026-01-01 → **2027-03-23** | **2 satır** 2027 tarihli (ileri tarihli) |
| `LG_211_01_STLINE` (2021–2025) | 2021-01-01 → **2030-03-20** | **70 satır** ≥ 2026, 2030'a kadar |
| `LG_171_01_STLINE` (2017) | 2017-01-01 → 2018-01-15 | ölçülmedi |

Sonuçlar: (1) min/max'a güvenen bir kapı, 2026 tablosunu "2027'yi de kapsıyor" sayardı; (2) tarih filtresi
olmayan bir 2026 sorgusu (golden "en çok satan 10 kitap") **2027 tarihli 2 satırı da toplar** — kapının bugün
bu golden'ı reddetmesi doğru; (3) `periods.tables_for` da aynı istatistiği kullanıyor ve ileri tarihli satır
için "başlangıca göre seç" gibi bir yama taşıyor. Bilgi paketinin kendi kuralı da bunu söylüyor
(`00-source-topology.md`: "min/max tarih aralığı yedeğin yetkili dönemini kanıtlamaz").

Görünümler: `v_monthly_sales`, `v_channel_net`, `v_imprint_perf`, `*_cube` **kaldırılan Wren yığınının**
nesneleri; `clean_rules` bunları istemden zaten siliyor, müşteri veritabanında yoklar. Bu görünümleri bekleyen
3 golden vaka geçersiz; "görünüm sözleşmesi" diye bir mekanizma gerekmez. Karar: o 3 vakanın beklenen SQL'i
ham tablolara göre iş tarafınca yeniden yazılır (aday: deterministik derleyicinin ürettiği SQL, iş onayıyla);
o zamana kadar kapıda kırmızı kalırlar ve taban 14/21 ile kaydedilmiştir.

### 8.2 Beyan: `coverage.yml` (bilgi paketi, `equivalences.yml`'nin yanına)

```yaml
schema_version: 1
# Bir kaynak kopyasının hangi işlem dönemini taşıdığı: insan beyanı, ölçüm değil.
coverage:
  - context: {n0: "411"}          # LG_{n0}_… kalıbındaki bütün tablolar
    from: 2026-01-01
    to: 2027-01-01                # yarı açık [from, to)
    date_role: business           # hangi tarih kolonu: entity'nin sertifikalı iş tarihi (conventions.time_column)
    verified_by: "…"              # kişi
    verified_on: 2026-09-15
    reason: "2026 canlı firma; 17.08.2026 yedeği"
  - context: {n0: "211"}
    from: 2021-01-01
    to: 2026-01-01
    verified_by: "…"
    verified_on: 2026-09-15
    reason: "2021–2025 tek firma yedeği"
```

Kurallar: `context` bir kalıp yer tutucusu kümesidir (tablo adı değil), o bağlamdaki her kalıp tabloya
uygulanır; isteğe bağlı `entities: [INVOICE, STLINE]` daraltır. Yer tutucusu olmayan (statik) tablo yalnız
`table:` ile adıyla beyan edilir. Aynı bağlam için örtüşen iki beyan → yükleme hatası. Beyan olmayan tablo
için kural kapalı kalır (bugünkü davranış).

### 8.3 Çürütme: ölçüm beyanı doğrulamaz, ama yalanlayabilir

Gece işi her beyanlı tablo için iş tarihi kolonunda **dönem dışı satır sayısını** ölçer
(`COUNT(*) WHERE d < from OR d >= to`) ve `semantic_coverage` tablosuna yazar: `(table, from, to, spill,
measured_at, status)`. `status`:

- `declared` — spill = 0. Kapı için kaynak **beyanlı**: tarih filtresi olmadan da dönem kanıtlıdır.
- `contested` — spill > 0. Beyan duruyor ama **tarih filtresi şart**; ret gerekçesi "kaynakta dönem dışı N satır
  var" der. Yönetim ekranında (`/timas/yonetim`, `semantic_audit`) görünür; iş tarafı ileri tarihli satırları
  temizler ya da beyanı düzeltir.

Bu, [[refutation-step]] ilkesinin aynısı: aday (beyan) insana sunulmadan önce veriyle kırılmaya çalışılır.
Bugünkü veriyle: `411` beyanı INVOICE için `declared`, STLINE için `contested` (2 satır); `211` STLINE
`contested` (70 satır).

### 8.4 Kapı ve derleyici bunu nasıl tüketir

- `sources_from(profiles, coverage)`: beyanlı+`declared` tabloya `window=[from,to)`, `declared=True`;
  `contested` tabloya `declared=False` (kural kapalı, gerekçeye spill eklenir). Kolon tipleri her zaman.
- **Birleşim kuralı** (beyan açılınca zorunlu): bir entity'nin birden çok oluşumu (yıl birleştirme UNION'ı)
  varsa, her oluşumun aralığı ⊆ istenen dönem **ve** oluşumların aralıklarının birleşimi == istenen dönem,
  örtüşme yok. Bugünkü "her oluşum == dönem" kuralı, beyanla kesişince `[2024,2027)` sorusunda iki kolu da
  reddederdi. Şekil matrisine 3 vaka eklenir: iki kollu doğru birleşim (kabul), bir kol eksik (ret), iki kol
  örtüşen (ret — [[period-union-double-counting]] hatasının kapı karşılığı).
- `periods.tables_for` önce beyanı okur, ölçülmüş pencereye yalnız beyan yoksa düşer; ileri tarihli satır
  yaması o zaman gereksizleşir.

### 8.5 Sıra ve süre

| # | İş | Süre |
|---|---|---|
| 1 | `coverage.yml` şeması + `Conventions.load_coverage` (doğrulama, örtüşme hatası) | 2 sa |
| 2 | Gece işi spill ölçümü + `semantic_coverage` + yönetim ekranı satırı | 3 sa |
| 3 | Kapı: `sources_from` beyan + birleşim kuralı + 3 şekil vakası | 3 sa |
| 4 | `periods.tables_for` beyan öncelikli | 1 sa |
| 5 | 411/211 beyanı iş tarafıyla yazılır; ileri tarihli 72 satır iş kararı | iş tarafı |
| 6 | 3 görünüm golden'ının ham tabloyla yeniden yazımı (iş onayı) | iş tarafı |

Beyan yazılmadan hiçbir kural açılmaz; 3. adım biter bitmez golden kapı geçişi yeniden ölçülür.

## 9. Canlı davranış örneği — çok parçalı bir istek (2026-09-15)

İstek: *"Yılbaşından 31 ağustosa kadar tüm satış yerlerimizle olan ciromuz. 2025 yılını da aynı şekilde 8 aylık
olarak yan sütuna ekleyin. Satış noktalarının hangi vilayette olduğu ve hangi bmt ye bağlı olduğu da ayrıca
yan sütunda bulunsun."* Köprüden canlı soruldu; cevap 0 sn'de **CLARIFICATION**: "'olan' ile hangi koşulu
kastediyorsunuz?". Çözümleyicinin gördüğü:

- ✅ ölçü: "ciro/satış" → sertifikalı `SUM(CASE WHEN INVOICE.TRCODE IN (7,8,9) …)`, varsayılan `CANCELLED=0`;
  karşılaştırma tanındı.
- ❌ dönem: "yılbaşından 31 ağustosa kadar" → YTD **bugüne** (2026-09-16) okundu, "31 ağustos" tanınmadı;
  "2025'i aynı şekilde 8 aylık" → **tam yıl** 2025. İki dönem de yanlış.
- ❌ kırılım: "satış yeri / satış noktası" (cari), "vilayet" (`CLCARD.CITY`), "BMT" (kaynakta `BMT` tablosu var)
  katalogda tanımsız → `unresolved`.
- ❌ sunum sözcükleri ("yan sütuna ekleyin", "ayrıca", "bulunsun") kavram sanıldı; "olan" niteleyici sanıldı ve
  soruyu tek başına durdurdu.

Kapı bu soruya hiç ulaşmadı; sorun çözümleyici ve sözlükte. Gereken: (a) "X'e kadar" ve "aynı şekilde N aylık"
dönem kalıpları (karşılaştırma dönemi = güncel dönemin aynası), (b) sözlük: satış yeri/nokta → CLCARD, vilayet →
CLCARD.CITY, BMT → ilişki (`BMT` tablosu), (c) sunum/bağlaç sözcükleri (`olan`, `yan sütun`, `ekleyin`) çözümleyicide
yok sayılır, niteleyici değildir. Bu üçü olmadan model yolu da doğru cevabı veremez: dönem çözümü derleyicide
([[period-union-double-counting]]), sözlük olmadan "vilayet" için kolon uydurulur.

