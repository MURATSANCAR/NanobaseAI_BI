# Görünüş sürekliliği (`appearance`) — ÖLÇÜM BEKLİYOR

Durum (2026-09-22): kod ve göç yazıldı, saf parçalar sentetik testle doğrulandı
(`tests/test_appearance.py`, 13 test). **Gerçek kitapta hiç koşmadı; kesinlik, geri çağırma ve
eşikler ölçülmedi.** Ölçülene kadar bulgular yalnız editör adayıdır ve bu dosya "ölçüm
bekliyor" der.

## 1. Editör ne bakar

Aynı karakterin görünüşü kitap boyunca tutarlı mı: saç rengi, göz rengi, ten/kürk rengi,
gözlük, şapka, üst ve alt giysinin rengi, elindeki eşya. Çocuk kitabında asıl kaynak resimdir:
s.12'de kırmızı tişört, s.28'de mavi tişört ve metin arada üstünü değiştirdiğini söylemiyorsa
bu bir süreklilik hatasıdır. Metin de kaynaktır ("sarı saçlı Ali" derken çizim kızıl) ve
metin–metin çelişkisi de olur ("gözlüklü" / "gözlüksüz").

Çelişki OLMAYANLAR: metnin açıkladığı değişim (üstünü değiştirdi, ıslandı, kılık değiştirdi,
büyüdü, saçını kestirdi, gözlüğünü çıkardı, eşyayı bıraktı), rüya/hayal/oyun, geçmişe dönüş,
kırpımın kestiği ya da ışığın değiştirdiği bir ayrıntı, resimde yanlış tanınmış bir figür.

## 2. Yapı: özellik defteri + denetim

Var olan iskelet değişmedi; üstüne iki şey geldi.

### A. Özellik defteri (`ed.character_attribute`, göç 024; `proofing/_attributes.py`)

Her karakterin metinden ve resimden okunan özellikleri **sayfa sayfa**, her satır kendi
kanıtıyla:

| alan | TEXT satırı | IMAGE satırı |
|---|---|---|
| `evidence_id` | alıntının `evidence` satırı (kind TEXT, `quote_verified`) | figürün görsel kanıtı (`character_mention.evidence_id` → `visual_region`) |
| `quote` | sayfadaki kelimesi kelimesine alıntı | — |
| `mention_id`, `bbox` | — | okunan figür ve kutusu (0..1000) |
| `reader` | `attribute_text@<sürüm>` | `attribute_image@<sürüm>` |
| `readings` | modelin öznesi/değeri | oyların her birinin değeri |
| `confidence` | alıntı birebir doğrulandıysa 1.0, oturtulduysa 0.6 | uyuşan okuma payı (2/2, 2/3) |

Salt ekleme (`forbid_change` tetikleyicisi). `character_attribute_read` ne okunduğunu tutar
(TEXT: sayfa; IMAGE: figür): aynı nesil + aynı okuyucu sürümü için **yeniden okunmaz**; prompt
sürümü artınca yeni satırlar eklenir, eskiler kalır. Özellik vermeyen sayfa/figür de "okundu"
sayılır, yoksa her koşuda yeniden okunurdu.

**Sözlük (kapalı küme, kitaptan bağımsız):**

| tür | değerler | kalıcı |
|---|---|---|
| `SAC_RENGI` | SIYAH KAHVERENGI SARI KIZIL GRI_BEYAZ MAVI YESIL PEMBE MOR TURUNCU KIRMIZI DIGER YOK BELIRSIZ | evet |
| `GOZ_RENGI` | KAHVERENGI SIYAH MAVI YESIL GRI DIGER YOK BELIRSIZ | evet |
| `TEN_KURK_RENGI` | renkler + COK_RENKLI DIGER YOK BELIRSIZ | evet |
| `GOZLUK` | VAR YOK BELIRSIZ | evet |
| `SAPKA` | VAR YOK BELIRSIZ | hayır |
| `UST_GIYSI_RENGI`, `ALT_GIYSI_RENGI` | renkler + COK_RENKLI DIGER YOK BELIRSIZ | hayır |
| `ESYA` | CANTA SIRT_CANTASI SEMSIYE KITAP TOP OYUNCAK BASTON ASA CICEK YIYECEK ALET DIGER YOK BELIRSIZ | hayır |

"Kalıcı" = hikâye içinde nadiren değişir; çelişkisi daha ağır (ERROR eşiği, §4). Küme dışı
cevap değer değildir (kayıt yok). BELIRSIZ kaydedilir ama çelişki kurmaz.

**Okuma akışı ve model çağrısı sayısı:**

- TEXT (`book-director`, düşünme kapalı, sıcaklık 0, prompt `attribute_text@1`): kitap metni
  1 500 kelimelik parçalara bölünür (sayfa bölünmez); parça başına **1 çağrı** → tipik bir
  resimli kitapta 1–4 çağrı. Model kapalı kümeden liste verir; özne karakter listesine
  (`resolve_subject`: olduğu gibi → kesme işaretinden önce → sondan kelime düşürerek) eşlenir,
  eşlenmeyen özne tahmin edilmez; alıntı sayfada birebir ya da sayfanın kendi kelimelerine
  oturtularak (`snap_quote`) bulunmazsa kayıt yoktur. Tek okuma yeter: kanıt alıntıdır, değer
  kapalı kümedendir.
- IMAGE (`book-vision-deep`, sıcaklık 0.6, prompt `attribute_image@1`): kimliği çözülmüş
  (`RESOLVED`) her figür kırpımı (`vision._crop`, kimlik adımının kullandığı aynı kırpım) için
  **2 bağımsız okuma**; bir türde uyuşmazlarsa **3.** okuma. Tür başına karar (`decide`): en az
  2 okuma aynı değer ve o değer tek başına önde → değer; yoksa BELIRSIZ. Çoğunluk kırpımda
  bütün figür görmüyorsa (`gorunur`) figür atlanır. **Figür başına 2–3 çağrı; sayfa başına
  = sayfadaki çözülmüş figür sayısı × 2–3.** Bir sayfada tek çağrıda tüm türler okunur.
- Sıra: önce metin (director), sonra resim (derin görsel model); iki model kartta birlikte
  durmaz, sıra geçişi bir tutar.

### B. Denetim (`proofing/appearance.py`, NAME `appearance`, LABEL «Görünüş sürekliliği»)

1. Defter boşsa doldurulur (idempotent).
2. **Çıkarma** (deterministik, `conflicts`): aynı karakter + aynı tür + farklı değer, iki AYRI
   sayfada → aday çift. Her değeri en erken sayfadaki satır temsil eder (aynı sayfada metin
   önce); ikinci değer için ilkinin sayfasından farklı en erken satır. Aynı sayfadaki metin–resim
   farkı bu denetimin değil, metin–görsel teyidinin (`confirm_text_visual`) işidir. Metin–metin,
   resim–resim ve metin–resim çiftleri aynı yoldan geçer. Üç değer → üç çift.
3. **Yargı** (text_contradictions ile aynı biçim): kitabın bütün metni + iki gözlem, director'a
   kapalı soru, **iki sırada** (A→B, B→A); cevap tek harf C/U/B, olasılık logprobs'tan
   (`Llm.choose`). Bulgu ancak `min(C_ileri, C_geri) ≥ JUDGE_MIN`. Metin bir açıklama taşıyorsa
   (üstünü değiştirdi, yeni tişört) U beklenir. **Çift başına 2 çağrı** (director; kitap metni
   önek olduğu için önbellek çalışır).
4. Her bulgu iki kanıt taşır: sayfa + alıntı (TEXT) ya da sayfa + bbox (IMAGE), `details.a/b`
   içinde `evidence_id`/`mention_id`. Bulgunun `page/quote/bbox`'ı sonraki gözlemindir.
5. Bir INFO satırı defter kapsamını bildirir (karakter, metin/resim kaydı, okunamayan kırpım,
   belirsiz değer, aday ve bulgu sayısı).

## 3. Yanlış alarm riskleri

1. Kimlik hatası: figür yanlış karaktere bağlıysa "farklı saç" çıkar. Denetim yalnız `RESOLVED`
   figürleri okur; yine de bulgu iki figürü gösterir, editör bakar. (Ölçümde kimliğe bağlı
   yanlış alarmlar ayrı sayılacak.)
2. Kapak/ön kapak figürleri: kapak çizimi iç sayfalardan farklı olabilir (başka sanatçı, başka
   sahne). Şimdilik dahil; ölçümde kapaktan gelen alarm oranı ayrı yazılır, gerekirse
   `page_role='FRONT_MATTER'` dışarıda bırakılır (açık karar).
3. Renk adlandırma: kırmızı/turuncu, mavi/mor, kahverengi/kızıl sınırı. Oylama (2 uyuşan
   okuma) tek okumanın gürültüsünü keser ama sistematik bir adlandırma kayması geçer; ölçümde
   bakılacak. Gerekirse "komşu renk" çiftleri (KIRMIZI–TURUNCU vb.) INFO'ya düşürülür — henüz
   yapılmadı, önce ölçüm.
4. Kıyafet/eşya doğal olarak sahneden sahneye değişir; yargı "metin açıklamıyorsa" der ama
   hikâye günler geçirdiğinde metin bunu söylemeyebilir. Kalıcı olmayan türlerde bulgu WARN.
5. Metin okuyucu özneyi yanlış kişiye bağlayabilir ("annesinin kırmızı tişörtü" → çocuk).
   Alıntı kanıt olduğu için editör anında görür; ölçümde sayılır.

## 4. Eşikler (hepsi ölçülmedi)

- `JUDGE_MIN = 0.5` — text_contradictions'ta altı kitap + enjekte vakalarla ölçülmüş başlangıç
  değeri; burada aynı biçimde yeniden ölçülecek.
- `ERROR_MIN = 0.8` — kalıcı türde (saç, göz, ten/kürk, gözlük) bu olasılığın üstü ERROR, diğer
  her şey WARN. Sezgisel; ölçümde ERROR'ların hepsinin gerçek olması beklenir.
- `MIN_AGREE = 2`, `MAX_READINGS = 3`, `VOTE_TEMPERATURE = 0.6` — projedeki oylama düzeniyle
  (text-visual, continuity) aynı.
- `PART_WORDS = 1500` — text_contradictions ile aynı gerekçe.

## 5. Ölçüm planı (gerçek kitap, GPU sunucusu)

Kullanıcı yapar; komutlar:

```sh
# 1. imajı yeni kaynakla kur, göçü uygula (024 tabloları)
ssh tt-gpu 'cd /data/editor && ./deploy/editorctl cli migrate'
# 2. deftersiz koşu: bir nesilde yalnız bu denetim, deftere yazmadan bulgu görmek için
ssh tt-gpu 'docker exec -i editor-mcp python -m editor.proofing <generation_id> --only appearance --dry' > appearance-<kitap>.json
# 3. deftere yazan koşu (proof_run/proof_finding + kuyruk)
ssh tt-gpu 'docker exec -i editor-mcp python -m editor.proofing <generation_id> --only appearance'
```

Not: `--dry` de özellik defterini doldurur (defter denetimin değil, kitabın bilgisidir ve
idempotenttir); yalnız `proof_run/proof_finding` yazılmaz.

Ölçülecekler (altı kitap):

1. **Okuyucu kesinliği (defter):** her kitaptan rastgele 30 IMAGE satırı ve bütün TEXT
   satırları gözle kontrol: değer doğru mu? BELIRSIZ oranı (kaç figürde hangi tür)?
   Kabul: IMAGE kalıcı türlerde ≥ 0.9 doğru; TEXT özne eşlemesi ≥ 0.95.
   SQL: `SELECT character_id, page_no, kind, value, source, confidence, quote, bbox FROM
   ed.character_attribute WHERE generation_id=... ORDER BY random() LIMIT 30`.
2. **Oylama tutarlılığı:** aynı figür ikinci kez okunduğunda (prompt sürümü artırılarak) değer
   aynı mı — tek okumadaki 18/26 tutarlılığın (UYGULAMA-NOTLARI) ne kadar üstüne çıkıyor.
3. **Denetim kesinliği:** `candidates_detail` içindeki her çift etiketlenir (gerçek çelişki /
   açıklanan değişim / kimlik hatası / renk adlandırma / kapak). JUDGE_MIN ve ERROR_MIN bu
   etiketli kümede seçilir; text_contradictions'taki gibi tabloya yazılır.
4. **Geri çağırma:** altı kitapta bilinen süreklilik hatası yoksa enjekte vaka: bir kitabın
   metnine "kırmızı tişört" eklenip çizim mavi ise bulgu çıkmalı; metne "üstünü değiştirdi"
   eklenince çıkmamalı (metin tarafı için yeterli; resim tarafı için bilinen hatalı kitap
   gerekir — açık).
5. **Maliyet:** `model_call` üzerinden çağrı ve süre: figür başına ortalama çağrı (2'ye ne
   kadar yakın), kitap başına toplam süre.

Sonuçlar bu dosyaya ve modül docstring'ine yazılır; o zamana kadar başlık "ÖLÇÜM BEKLİYOR".

## 6. Açık kararlar

- Kapak figürleri dahil mi (§3.2).
- Komşu renk çiftleri INFO'ya düşürülsün mü (§3.3) — önce ölçüm.
- `ESYA` sahne değişkeni: kalsın mı, yoksa yalnız INFO mu — ölçümde yanlış alarm oranına göre.
- Kimliği `RESOLVED` olmayan (aday) figürler defterde yok; kimlik kapsamı düşük kitaplarda
  denetim az şey görür. Kapsam INFO satırında görünür.

## İlk gerçek ölçüm — 2026-09-23, «Levent Dünya Harikalarının Peşinde» (nesil 60e5d717, `--dry`)

- Defter: 9 karakter, **0 metin** ve 1 792 resim kaydı (155 çözülmüş figür, 39 figür kırpımı okunamadı, 359 görsel çağrı); 290 değer BELİRSİZ.
- Tür dağılımı (230 figür × 8 tür): göz rengi 193/230 belirsiz (küçük kırpımda göz okunmuyor), alt giysi 77 belirsiz, saç 17; gözlük/şapka/üst giysi hiç belirsiz değil.
- 207 aday çift iki sıralı yargıya girdi, **0 bulgu**. İnsan doğrulaması yok: bu «yanlış alarm yok» demektir, «kaçırılan yok» demez.
- **Gözlem (genel):** metin okuyucu 9 parçada 0 özellik çıkardı — çocuk kitabında görünüş metinde nadiren yazılıyor ya da istem çok dar; ikinci kitapta ölçülmeden karar verilmez. Göz rengi türü bu çözünürlükte ölçülemiyor; ya kırpım büyütülmeli ya tür INFO'ya düşmeli.
