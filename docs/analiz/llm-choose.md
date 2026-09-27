# Kapalı küme seçim — `QueuedLlm.choose`

Modelden serbest metin değil, **verilen seçeneklerden biri** ve **her seçeneğin olasılığı** istenir.
Kategori önerisi (H1), e-posta sınıflama, müşteri segmenti, SSS eşleştirme, «uyumlu / çelişkili / belirsiz» gibi
bütün kapalı küme kararları için ortak çağrıdır. Uydurma sınıf imkânsızdır; ne kadar emin olunduğu tek çağrıda okunur.

Kod: `backend/semantic_layer/runtime/llm_choose.py` (saf işlevler) ve `llm_queue.py` → `QueuedLlm.choose`.
Testler: `backend/semantic_layer/tests/test_llm_choose.py`, `test_llm_client_http.py` (`complete`).
Kapının kendisi: [docs/LLM-KAPISI.md](../LLM-KAPISI.md).

## İmza

```python
QueuedLlm.choose(
    prompt: str,                 # soru ve bağlam; seçenek listesi ve «yalnız harfi yaz» sona eklenir
    choices: list[str],          # seçenekler; boş, tekrarlı ya da boşluktan ibaret olamaz (ValueError)
    *,
    system: str | None = None,   # isteğe bağlı sistem mesajı
    top_logprobs: int = 20,      # ilk token için istenen aday sayısı (vLLM varsayılan üst sınırı 20)
    text_max_tokens: int = 16,   # yedek yolda düz metin cevabın bütçesi
    user_id: str | None = None,  # bilette görünür
    cancel: threading.Event | None = None,
    on_admitted: Callable[[Ticket], None] | None = None,
) -> Choice
```

`Choice` alanları:

| Alan | Anlamı |
|---|---|
| `choice` | seçilen seçeneğin kendisi (verdiğiniz metin); eşlenemediyse `None` |
| `index` | `choices` içindeki sırası |
| `probs` | seçenek → olasılık, toplamı 1; yedek yolda `None` |
| `probability` | `probs[choice]` |
| `margin` | p(seçilen) − en yüksek diğer olasılık |
| `coverage` | ilk token olasılık kütlesinin etiketlere düşen payı; düşükse model başka bir şey yazmak istemiş |
| `method` | `logprobs` · `text` (yedek, olasılık yok) · `none` (eşlenemedi) · `single` (tek seçenek, model çağrılmaz) |
| `calls` | yapılan model çağrısı (eleme turları dahil) |
| `raw`, `error` | modelin son metni; yapılandırılmış yolun neden kullanılamadığı |

`confident(min_prob, min_margin=0.0, min_coverage=0.0)` eşiği uygular. Olasılık yoksa her zaman `False`.
`as_dict()` kayda/JSON'a yazmak için.

## Nasıl çalışır

1. Seçenekler **A, B, C … Z** etiketleriyle sorunun sonuna listelenir. Etiket tek karakter, dolayısıyla tek token'dır;
   seçenek «Çocuk Kitapları > Masal» gibi çok token'lı olsa da model yalnız etiketi yazar.
2. İstek: `max_tokens=1`, `temperature=0`, `structured_outputs: {"choice": ["A", "B", …]}` (cevap etiketlere
   kilitlenir), `logprobs: true`, `top_logprobs: 20`, akışsız. İstemcinin `extra`'sı (düşünme kapalı bayrağı,
   `LLM_EXTRA_BODY_JSON`) aynen gider.
3. O tek token'ın adaylarından her etiketin payı toplanır («A» ve « A» ikisi de A'dır) ve etiketler arasında
   normalize edilir. Seçim en olası etikettir.
4. **26'dan çok seçenek:** eleme turu. Seçenekler dengeli gruplara bölünür (60 → 20+20+20), her grubun galibi
   finale kalır. `P(c) = P(grup içinde c) × P(finalde c'nin grubunun galibi)` — toplamı yine 1. Seçim finalin
   seçimidir; marjı eksi çıkabilir, o zaman `confident` `False` döner. Sayı tavanı yok, tur sayısı büyür.
   Her tur ayrı bilettir (arada başka modüller de sıra alır).
5. **Sıra ve slot:** her model çağrısı `chat` ile aynı bileti alır (`sl_llm_queue`, modül ve öncelik
   `rt.llm_for(...)`'dan). Yedek yolun ikinci isteği aynı bilet içinde kalır, yeniden sıraya girmez.

## Yedek yol ve hatalar

| Durum | Sonuç |
|---|---|
| Uç `structured_outputs`/`logprobs` bilmiyor (400/404/405/413/415/422/501) | aynı biletle düz metin sorulur; metin etikete ya da seçeneğin tamamına eşlenirse `method="text"`, `probs=None` |
| Cevapta olasılık yok ya da etiketlerin hiçbiri aday değil | cevap metni eşlenir (ek çağrı yok); eşlenemezse bir kez düz metin |
| Metin eşlenemedi | `choice=None`, `method="none"` |
| İstemcide `complete` yok (eski/sahte istemci) | doğrudan düz metin yolu |
| Model hiç cevap veremedi (bağlantı, zaman aşımı, 429 sonrası süre doldu, 5xx), iptal | **istisna yükselir** |

Metin eşleme yalnız kesin eşleşme kabul eder: «B», «(B)», «B)», «Cevap: B» ya da seçeneğin tamamı (Türkçe
büyük/küçük harf farkı gözetmeden). «Roman değil», «A veya B» eşlenmez.

İstisna bilinçli: model yokken toplu işin yüzlerce kaydı «emin değil» kuyruğuna düşmesin; bu «sonra dene»dir.

## Örnek

```python
from semantic_layer.runtime.llm_queue import BATCH

llm = rt.llm_for("categories", BATCH)          # gece toplu öneri; ekranda anlık üretimde öncelik vermeyin
adaylar = ["Çocuk > Masal", "Çocuk > Resimli Öykü", "Gençlik > Fantastik"]
r = llm.choose(
    f"Kitabın künyesi ve özeti aşağıda. Hangi kategoriye girer?\n\n{kunye}\n\nÖzet: {ozet}",
    adaylar,
)
if r.confident(0.80, min_margin=0.30):
    oneri_kaydet(r.choice, olasilik=r.probability, kanit=r.as_dict())
else:
    emin_degil_kuyruguna(adaylar, sonuc=r.as_dict())   # method "text"/"none" da buraya düşer
```

Ayrı bir betikte: `QueuedLlm(LlmClient(...), LlmQueue.from_env(store.engine), purpose="bg:categories").choose(...)`.

## Eşik önerisi

Eşik çağırana aittir; modül karar vermez. Başlangıç için (gerçek veriyle ölçülmeden kesinleşmez):

- **Otomatik kabul** (insan görmeden yazılacaksa): `p ≥ 0.90` ve `margin ≥ 0.50`.
- **Öneri olarak göster** (insan onaylayacak): `p ≥ 0.70` ve `margin ≥ 0.30`.
- Altı ve `method` `text`/`none`: «emin değil» kuyruğu.
- `coverage < 0.5` sık görülüyorsa istem ya da düşünme kapalı bayrağı bozuktur; eşik değil istem düzeltilir.

Eşiği sabit yazmayın: modülün ayarına (`admin.conf`/env) koyun, golden set üzerinde kabul oranı ile isabeti
birlikte ölçerek seçin. Aynı model, sıcaklık 0 ve tek token'da koşular arası olasılık farkı 0 ölçüldü
(vllm-choice-logprobs); farklı istem sürümleri arasında ise değişir — istem değişince eşik yeniden ölçülür.

## Ne zaman kullanılmaz

- **Rakam, tarih, ad üretmek.** Rakamı model üretmez; SQL üretir.
- **Deterministik kuralın bildiği karar.** Beyan varsa beyan kazanır, kural varsa kural; model yalnız kuralın
  göremediği anlam farkında.
- **Açık uçlu sınıf** («yeni etiket öner»): seçenek listesi yoksa bu çağrı değil; ayrı öneri kuyruğu.
- **Çok etiketli karar** (bir kitaba birden çok tema): tek seçim değil; her aday için ayrı evet/hayır
  (`["evet", "hayır"]`) çağrısı yapın.
- **Çok büyük düz liste** (yüzlerce düğüm): eleme turu çalışır ama gruplar arası olasılık yaklaşıktır; ağaç varsa
  önce üst düğüm, sonra alt düğüm seçtirin (hiyerarşik seçim).
- **Sırası anlam taşıyan seçenekler** (1–5 puan): etiket harflerle gider, model sırayı bilir ama olasılık
  kalibrasyonu ölçülmeden puan ortalaması olarak kullanmayın.

## Bilinen varsayımlar (ölçülecek)

- Uç TT GPU vLLM (`nanobaseAI`): `structured_outputs.choice` + `logprobs` çalışıyor, `guided_choice` etkisiz
  (ölçüm: vllm-choice-logprobs). Başka uca geçilirse önce tek çağrıyla bakın: `method` `logprobs` dönmeli.
- `top_logprobs`'un kısıtlama (structured_outputs) öncesi mi sonrası mı dağılımdan geldiği vLLM ayarına bağlıdır;
  öncesiyse `coverage` modelin etiket dışına ne kadar kaydığını gösterir, sonrasıysa hep ~1'dir. İlk kurulumda ölçülecek.
- Düşünme kapalı bayrağı yoksa tek token `<think>` olabilir; o zaman yapılandırılmış yol boşa gider ve yedek yol da
  16 token'da kesilebilir → `none`. Bayrak: `LLM_EXTRA_BODY_JSON={"chat_template_kwargs":{"enable_thinking":false}}`.
