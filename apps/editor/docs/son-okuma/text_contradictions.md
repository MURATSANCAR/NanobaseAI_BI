# Metin içi çelişki (`text_contradictions`) — kısmen ölçüldü

Kaynak: `src/editor/proofing/text_contradictions.py` (v1). Model önerir, deterministik
doğrulama, model iki sırada yargılar.

## 1. Kural — ne bulgudur, ne değildir

Kitabın **kendi metninin** iki yerinde söylenen ve hikâyede ikisi birden doğru olamayacak iki
ifade; metinde değişimi açıklayan bir şey yok. Türler (`KINDS`): ZAMAN (gündüz/gece, önce/sonra,
gün sırası, süre; olmuş olay sonra hiç olmamış gibi), KARAKTER (yaş, akrabalık, ad, meslek,
söylenen özellik), YER (aynı anda iki yerde), NESNE (kırık/kayıp açıklamasız sağlam), SAYI.

Çelişki DEĞİL (prompt'ta ve yargıda açık): zamanla değişen durum (sonraki gün, büyüme,
taşınma), metnin açıkladığı değişim, rüya/hayal/oyun/şaka/yalan, bir karakterin yanlış bilgisi,
mecaz ve abartı, farklı kişiler/nesneler, **çizimlerle ilgili her şey** (görsel süreklilik
`appearance`/`props`/`setting`'in işi). Aynı span'daki ya da aynı alıntılı iki ifade aday olmaz
(«bir ifade kendisiyle çelişemez»).

Neden defter adımı (`knowledge.detect_contradictions`) değil (docstring): o adım modele yalnız
karakter kartlarını ve olay özetlerini gösterir, metni göstermez, sonra iki birebir alıntı
ister. Ölçüm (kayıtlı çağrılar): prompt v1 bir kitapta 19 aday, 19'u da görsel taramaların
ifadesi hakkında (metin hakkında 0; 1 kaydedildi, yanlış); prompt v2 altı kitapta 0 aday,
düşünme 12k bütçenin tamamını kullandı, düşünmesiz tekrar boş liste döndü.

## 2. Girdi / kaynak

- Yalnız sayfa metni: `source.read(gid)` span'ları, `[sSAYFA pPARAGRAF] metin` biçiminde
  birleştirilir (`book_text`). Künye/tanıtım/arka kapak da metnin içinde olabilir; prompt
  «hikâye değildir» der.
- Parçalar `parts`: ardışık **bütün** sayfalar, `PART_WORDS` kelimeye kadar (sayfa bölünmez).
- Doğrulama: `source.key` (normalleştirilmiş arama), `ledger.snap_quote` (sayfanın kendi
  kelimelerine oturtma), `ledger.norm`.
- Defter/CRM/sözlük kullanılmaz.

## 3. Karar mekanizması

1. **ÖNER** — iki okuyucu, birleşim:
   a. `propose_window` (**kapalı**, `WINDOW_READER=False`): bütün kitap bağlam, soru bir parça
      hakkında («s{lo}–s{hi} cümlelerinden hangisi kitabın başka yerindekiyle çelişir»),
      `PROPOSE_SCHEMA` (en çok 60 aday), `max_tokens=8000`, temp 0, thinking kapalı. Docstring:
      altı kitapta **ve** enjekte edilen 16 çelişkinin hepsinde boş liste döndü; daha güçlü
      model için tutuldu, yalnız GPU zamanı yaktığı için kapatıldı.
   b. `facts_of`: parça başına değişmemesi gereken bilgiler (`FACT_KINDS`: YAS, AKRABALIK, AD,
      SAYI, OZELLIK; `subject, kind, aspect, value, page, paragraph, quote`; `FACT_SCHEMA`, en
      çok 120 madde). `pair_facts`: aynı **özne + tür**, farklı **değer** → aday; deterministik.
      `aspect` anahtara **alınmaz** (okuyucu aynı özelliği iki sayfada farklı adlandırıyor —
      «kardeş sayısı»/«kaç kardeş»; enjekte sayı çelişkilerini gizlediği ölçülmüş).
2. **DOĞRULA** (`locate`): iki alıntı da sayfasında bulunmalı (verilen paragraf önce; birebir
   normalleştirilmiş, yoksa `snap_quote`); aynı span ya da aynı alıntı → düşer; aynı çift iki
   okuyucudan gelirse birleştirilir (`by`).
3. **YARGILA** (`judge`): bütün kitap bağlam + iki ifade, `Llm.choose("book-director",
   ["C","U","B"])` — C çelişki, U yok/açıklanıyor, B karar verilemiyor; **iki sırada** (A→B,
   B→A); `p_contradiction = min(C_ileri, C_geri)`; `≥ JUDGE_MIN` → bulgu. Eşzamanlı
   `PARALLEL` yargı.

## 4. Eşikler ve nereden okunduğu

Env/config yok; modül sabitleri.

| eşik | değer | anlam / ölçüm (kodda) |
|---|---|---|
| `JUDGE_MIN` | 0,5 | iki sırada da gereken C olasılığı; altı kitabın etiketli çiftleri + enjekte vakalar üzerinde seçildi: 0,5'te yargının gördüğü her enjekte vaka kaldı, yanlış etiketli çiftler düştü («Eşik» bölümü — sayılar kodda yok) |
| `PART_WORDS` | 1 500 | en yoğun ölçülen parça 41 bilgi verdi; şema sınırı 120 |
| `WINDOW_READER` | False | yukarıda |
| `PARALLEL` | 4 | çalışan GPU analizinin yanında küçük |
| öneri listesi sınırı | 60 (window) / 120 (facts) | proje kuralı: her liste sınırlı |
| `max_tokens` | 8 000 | okuyucular |
| alıntı uzunluğu | ≤600 kr | `STR` |

## 5. Bulgu biçimi

Her bulgu **WARN**. `page` ve `quote` = **ikinci** (sayfa sırasına göre sonraki) ifade;
`message`: «Metin içi çelişki (tür): s.A “…” ile s.B “…” birlikte doğru olamaz. <why>»;
`suggestion` sabit («iki yeri karşılaştırıp birini düzeltin ya da değişimi açıklayan bir cümle
ekleyin»); `details{kind, a{page,idx,quote}, b{…}, why, proposed_by [facts|window],
judge{forward, reverse}, p_contradiction}`.

Stats: `paragraphs, parts, proposed_window, facts, proposed_facts, unverified_quotes,
candidates, judge_failed, readers_failed, confirmed, candidates_detail (her aday + p)`.

## 6. Kendi hatası vs kitabın hatası

- Kitabın: doğrulanmış ve yargılanmış çift.
- Kendinin: uydurma/yerleşmeyen alıntı (`unverified_quotes`), okuyucu çağrısı düşen parça
  (`readers_failed`; **hepsi** düşerse `RuntimeError` → FAILED), yargı çağrısı düşen çift
  (`judge_failed`, aday atlanır), aspect adlandırma tutarsızlığı (anahtara alınmayarak
  sönümlenir).

## 7. Ölçüm

Kodda yazılı olanlar:
- Defter adımı prompt v1/v2 sonuçları (§1).
- `propose_window`: altı kitap + 16 enjekte çelişki → hep boş liste («Ölçüm 2»).
- `PART_WORDS`: 1 500 kelimelik en yoğun parça 41 bilgi.
- `JUDGE_MIN` seçim gerekçesi (sayısız).

### ÖLÇÜM BEKLİYOR

Docstring «Measured precision/recall: docs/son-okuma/text_contradictions.md» diyor; kesinlik ve
geri çağırma **sayısı** kodda yok. Etiketli çift sayısı, 16 enjekte vakanın kaçının `facts`
yoluyla yakalandığı yazılı değil.

Plan:
```sh
ssh tt-gpu 'docker exec -i editor-mcp python -m editor.proofing <gen> --only text_contradictions --dry' > tc-<kitap>.json
```
1. `stats.candidates_detail` her aday (p ile) elle etiketlenir: gerçek / açıklanan değişim /
   farklı kişi / okuyucu değer hatası. Kesinlik = confirmed içinde gerçek payı; 0,5 eşiği bu
   etiketli kümede yeniden bakılır.
2. Geri çağırma: 16 enjekte vaka (yaş, akrabalık, ad, sayı, özellik, zaman, yer, nesne) yeniden
   koşulur; `facts` yolunun yakaladığı/yakalamadığı tür başına yazılır. ZAMAN/YER/NESNE
   türleri **yalnız window okuyucusundan** gelebilir; o kapalıyken bu türlerin geri çağırması
   yapısal olarak 0'dır — ölçüm bunu açıkça yazmalı.
3. Maliyet: `model_call` üzerinden parça başına 1 okuma + aday başına 2 yargı; bütün kitap
   bağlamı her yargıda tekrar (sunucu önek önbelleği).

## İlk gerçek koşu (2026-09-22)

«Levent Dünya Harikalarının Peşinde», nesil `60e5d717`: koşu özetinde bu denetim için sayı
**verilmedi** (koşulmadı mı, 0 mı bilinmiyor). Kaydedilen diğer sekiz denetim kendi
belgelerinde.

## 8. Bilinen yanlış alarm riskleri ve açık sorular

1. **Tür kapsamı**: `facts` yolu yalnız KARAKTER ve SAYI üretir; ZAMAN/YER/NESNE bulgusu
   bugün çıkamaz. `KIND_TR` ve mesaj bu türleri destekler ama üretici yok.
2. **Özne normalleştirme**: «Levent» / «Levent’in» / «o» aynı özne sayılmaz; farklı yazımlar
   çifti kaçırır (geri çağırma), aynı ad farklı kişi yanlış çift kurar (kesinlik) — yargı
   «farklı kişiler» demeli.
3. **Değer eşitliği** `ledger.norm` ile: «yedi» / «7» farklı değer → sahte aday; yargıya kalır.
4. **Uzun kitapta bağlam**: her yargı bütün kitabı taşır; model bağlam sınırını aşarsa
   `Llm.choose` hata verir → `judge_failed` (sessiz kayıp). Sınır kodda yok.
5. **Tek B (kararsız) okuması**: `min(C, C)` kullanılır; B yüksekse bulgu çıkmaz — bilinçli.
6. **Künye/arka kapak** metne dâhil: «yazar 1980 doğumlu» ile hikâye karakteri karışabilir;
   prompt uyarıyor, süzgeç yok.
