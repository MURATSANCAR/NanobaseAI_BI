# Eşya sürekliliği (`props`) — ÖLÇÜM BEKLİYOR

Durum (2026-09-22): kod yazıldı, saf parçalar sentetik testle doğrulandı
(`tests/test_props.py`, 8 test). **Gerçek kitapta hiç koşmadı; kesinlik, geri çağırma ve
eşikler ölçülmedi.** Ölçülene kadar bulgular yalnız editör adayıdır.

## 1. Editör ne bakar

Bir karakterin taşıdığı nesne (çanta, sırt çantası, şemsiye, kitap, top, oyuncak, baston, asa,
çiçek, yiyecek, alet…) aynı sahnede açıklamasız kayboluyor ya da beliriyor mu; kırılan/kaybolan bir
nesne sonra açıklamasız sağlam ve yerinde görünüyor mu. (Şapka `SAPKA` türüyle `appearance`
denetimindedir; burada yinelenmez.)

Çelişki OLMAYANLAR: metnin açıkladığı değişim (bıraktı, verdi, kaybetti, buldu, tamir edildi,
yenisini aldı), sahne/gün değişimi, rüya/hayal/oyun, geçmişe dönüş, kırpımın kestiği ya da
yakında duran ama elde olmayan bir nesne.

## 2. Kaynaklar

1. **Özellik defteri** (`ed.character_attribute`, göç 024) `ESYA` satırları: metin satırı alıntı,
   resim satırı figür kutusu (bbox 0..1000) taşır; resim değeri en az iki bağımsız okumanın
   uyuşmasıyla yazılmıştır, aksi BELIRSIZ (çelişki kurmaz). Defter boşsa `_attributes.fill`
   doldurur (idempotent; `appearance` koştuysa 0 çağrı).
2. **Metin durum cümleleri** (`props.read_states`): director, parça başına 1 çağrı
   (1 500 kelime, sayfa bölünmez), kapalı küme:
   `YANINDA, BIRAKTI, KAYBOLDU, KIRILDI, BULDU, TAMIR_EDILDI`; nesne türü defterle aynı kapalı
   kümeden (`ITEMS`), `DIGER` ise nesnenin adı normalleştirilerek eşlenir. Özne karakter listesine
   eşlenmezse ya da alıntı sayfada bulunmazsa (`locate`) kayıt yok.

## 3. Kural (deterministik aday çıkarma, `props.candidates`)

Sahne: `_continuity.scenes` — geçiş kalıbı olan sayfa yeni sahnenin ilk sayfasıdır. Kalıplar genel
Türkçe (kitaba özel değil): zaman («ertesi gün/sabah», «sonraki gün», «N gün/hafta/ay/yıl sonra»,
«günler sonra», «akşam olunca», «sabah olduğunda», «aradan … geç…»), mekân («yola çıktı», «vardı»,
«ulaştı», «eve/geri/okula/köye/şehre döndü»). Hikâye dışı sayfa (`page_role` FRONT_MATTER/NON_STORY)
da sahneyi böler.

- **A. Sahne içi kayboluş/beliriş:** aynı karakter, aynı sahne; s.p'de X `YANINDA` (defter ya da
  metin), s.q'da (q≠p) defterin açık **YOK** satırı; arada X için BIRAKTI/KAYBOLDU/KIRILDI/BULDU
  yok → aday. q>p «kayboluyor», q<p «beliriyor». Resimde başka bir eşya görünmesi X'in yokluğunu
  kanıtlamaz (defter figür başına tek `ESYA` değeri taşır); metnin başka bir eşyayı anlatması da
  kanıtlamaz.
- **B. Kırılan/kaybolan sonra sağlam:** X için KIRILDI/KAYBOLDU s.p'de; sonra s.q'da X `YANINDA`
  (defter ya da metin); arada TAMIR_EDILDI/BULDU yok → aday (sahneden bağımsız). Arada BULDU
  varsa açıklama sayılır, bundan sonrası aday değil. İlk sağlam görünüş yeter (tek aday).

## 4. Yargı ve bulgu

`text_contradictions`/`appearance` ile aynı biçim: kitabın bütün metni + iki gözlem, director'a
kapalı soru, **iki sırada** (A→B, B→A); cevap tek harf C/U/B, olasılık logprobs'tan
(`Llm.choose`). Bulgu ancak `min(C_ileri, C_geri) ≥ PROPS_JUDGE_MIN`.

Her bulgu iki kanıt taşır: sayfa+alıntı (TEXT/STATE) ya da sayfa+bbox (IMAGE); `details.a/b`
içinde `evidence_id`/`mention_id`. Bulgunun `page/quote/bbox`'ı sonraki gözlemindir. Şiddet:
B kuralı ve olasılık ≥ `PROPS_ERROR_MIN` → ERROR, diğerleri WARN. Bir INFO satırı kapsamı bildirir.

## 5. Eşikler (ayardan; hepsi ölçülmedi)

`_continuity.setting(name, default)`: önce env `EDITOR_<NAME>`, sonra `settings()` alanı (varsa),
sonra varsayılan. `config.py` değişmedi.

| ad | env | varsayılan | anlamı |
|---|---|---|---|
| `props_judge_min` | `EDITOR_PROPS_JUDGE_MIN` | 0.5 | iki sırada da gereken «çelişki» olasılığı (text_contradictions'ta ölçülen başlangıç) |
| `props_error_min` | `EDITOR_PROPS_ERROR_MIN` | 0.8 | B kuralında bu üstü ERROR |
| `props_parallel` | `EDITOR_PROPS_PARALLEL` | 4 | eşzamanlı yargı çağrısı |

## 6. Model çağrısı sayısı

- Durum okuyucu (director): parça başına 1 → tipik kitapta 1–4.
- Yargı (director): aday başına 2.
- Defter boşsa `_attributes.fill`: metin parça başına 1 + figür başına 2–3 (appearance ile ortak;
  bir kez).

## 7. Yanlış alarm riskleri

1. Resim `ESYA=YOK` okuması: figür kırpımı eli kesmişse «yok» okunabilir; oylama (2 uyuşan okuma)
   tek okumanın gürültüsünü keser ama kırpım sistematik keserse geçer. Ölçümde YOK satırlarının
   doğruluğu ayrı sayılır.
2. Sahne sınırı kaçırılırsa (metin geçişi kalıp dışı kelimeyle anlatıyorsa) iki ayrı sahne bir
   sayılır → A kuralı fazla aday üretir; yargı «sahne değişti» diyebilir ama garanti değil.
3. Durum okuyucu özneyi yanlış kişiye bağlayabilir; alıntı kanıt olduğu için editör anında görür.
4. Grup sahnelerinde nesne el değiştirir (top); B kuralı yalnız aynı karakter için işler, A kuralı
   «verdi» (BIRAKTI) okunduysa susar.

## 8. ÖLÇÜM BEKLİYOR — ölçüm planı (gerçek kitap, GPU sunucusu)

```sh
ssh tt-gpu 'docker exec -i editor-mcp python -m editor.proofing <generation_id> --only props --dry' > props-<kitap>.json
ssh tt-gpu 'docker exec -i editor-mcp python -m editor.proofing <generation_id> --only props'
```

`--dry` de defteri doldurur (kitabın bilgisi, idempotent); yalnız `proof_run/proof_finding` yazılmaz.

Ölçülecekler (altı kitap):
1. **Durum okuyucu kesinliği:** `stats.reader` ve `candidates_detail` içindeki her STATE kaydı gözle:
   özne, tür, durum doğru mu; `unknown_subject`/`unverified_quote` oranı. Kabul ≥ 0.9.
2. **Sahne sınırı:** `stats.scenes` sayısı ile kitabın gerçek sahne sayısı karşılaştırılır; kaçan
   geçiş kalıpları `_continuity.TIME_SHIFT_RX/PLACE_SHIFT_RX`'e genel kelime olarak eklenir (kitaba
   özel kelime eklenmez).
3. **Denetim kesinliği:** her aday etiketlenir (gerçek / açıklanan değişim / kırpım / sahne sınırı
   hatası / özne hatası); `PROPS_JUDGE_MIN` ve `PROPS_ERROR_MIN` bu etiketli kümede seçilir.
4. **Geri çağırma (enjekte):** bir kitabın metnine «çantasını evde unuttu» + aynı sahnede resimde
   çanta → bulgu çıkmalı; «oyuncağı kırıldı» + üç sayfa sonra «oyuncağıyla oynadı» → B bulgusu
   çıkmalı; araya «babası tamir etti» eklenince çıkmamalı.
5. **Maliyet:** `model_call` üzerinden çağrı ve süre.

## 9. Açık kararlar

- `ESYA` türü appearance'ta da çelişki kurar (kalıcı olmayan tür, WARN); iki denetimin aynı çifti
  iki kez göstermesi olası. Ölçümden sonra biri sussun mu (appearance'ta ESYA'yı INFO'ya düşürmek
  o dosyaya dokunmayı gerektirir — bu görevde yapılmadı).
- «günler sonra» gibi sayısız geçişler sahne sınırıdır; gün sayısı burada kullanılmaz.
- Kapak/ön kapak figürleri defterde varsa sahne 0'a düşer; kapak sahnesi ölçümde ayrı sayılır.
