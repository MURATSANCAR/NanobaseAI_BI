# Tek çağrılı özne seçimi — aday, üretime bağlı değil (18 Eylül 2026)

## Genel soru

Rol V8 (`source_role_bindings.py`) iddia başına üç serbest graf çağrısı yapıyor, yavaş ve doğru iddiaları da reddediyor. Aynı özne–yüklem denetimi, modelin **karar vermediği** tek çağrıyla yapılabilir mi?

## Aday

`apps/editor/backend/editor/source_subject_choice.py` (`source-subject-choice-v1`). Model iddianın her yüklemi için kapalı bir form doldurur: iddia öznesi türü (`WORDS / ANONYMOUS_SPEAKER / NONE_STATED`) ve sözcük kimlikleri, aynı olayı bildiren kaynak sözcükleri, kaynak öznesi türü (`WORDS / SPEAKER / ADDRESSEE / UNSTATED`). Bütün kimlikler çalışma anında üretilen gerçek sözcük kimlikleridir; form şeması, kapalı kümeler ve kimlikler kodla doğrulanır, dışına çıkan çıktı `INVALID_SUBJECT_CHOICE_FORM` olur. Kararı deterministik kurallar verir: aynı özne sözcüğü, birinci kişi kaynağa adlı özne yalnız ad konuşmanın **dışında** da geçiyorsa, aktarma yüklemine adlı aktaran yalnız ad kaynakta varsa. Ad listesi ya da kitap kuralı yoktur. Kapalı küme vLLM kısıtlı çözümlemeyle değil, istem + doğrulamayla sağlanır: `editor.analysis.model` yalnız `json_object` destekliyor.

## Gerçek ölçüm

`nanobase-direct`, canlı `api` konteynerinde salt okunur; mevcut genel sürücü `scripts/probe-source-role-bindings.py` (gerçek API == bağımsız PG eşliği, korunan kayıt/inceleme hashleri önce/sonra eşit, uygulama yazımı 0). Nesil `116bb4a8`, sayfalar 5/10/13/27/29/34/38, 14 gerçek pasaj, GPU Qwen. Modül SHA-256 `b6f34613…`.

| | Rol V8 birleşik (`cited-semantics-probe-…111543…`) | Tek çağrı | Tek çağrı AND kişi eki kapısı |
|---|---:|---:|---:|
| Yapısal PASS / inceleme | 5 / 9 | 11 / 3 | 10 / 4 |
| Model çağrısı | pasaj başına 2–3 | 14 | 14 |
| Toplam model süresi | — | 46,1 sn | 46,1 sn |
| Kesin yanlış PDF27 iddiası | reddedildi | **geçti** | reddedildi |

Kanıt: `evidence/source-role-bindings-probe-20260918T120129177928Z.json`, tekrar `…T120332712704Z.json`, birleşik tablo `evidence/subject-choice-and-person-gate-20260918.json`.

## Bulgular

1. **Tek çağrı tek başına yetmiyor.** Model, "Bilge'nin … yüklediği ve … bayıldığı" sıralı ortaçlarında ikinci ortacın öznesini `NONE_STATED` doldurdu; kesin yanlış iddia geçti. Aynı iddiayı model çağırmayan [kişi eki kapısı](2026-09-18-person-agreement-candidate.md) yakalıyor. İki kapı AND olmadan kullanılamaz.
2. **Kararlı değil.** Aynı girdiyle ikinci koşuda 14 formun 3'ü, 14 kararın 1'i değişti (sıcaklık 0, sabit seed). PDF34 "Defne, … bir robot olduğunu gururla belirtir" ilk koşuda incelemede kaldı, ikincisinde geçti: model kaynakta belirtilmemiş özneyi `WORDS [Defne]` doldurdu. Bu iddia özne bakımından muğlaktır; geçmesi doğru kabul edilemez.
3. V8'in reddedip birleşik adayın geçirdiği 5 iddia gözle okundu ve kaynakla uyumlu göründü (adsız konuşmacı, edilgen emir, aktaranı konuşma dışında geçen dolaylı anlatım). Bu okuma bağımsız anlamsal kabul değildir.
4. Kalan retler: drop-cap nedeniyle kaynakta "efne'nin" (okuma görünümü kullanılmadı), "Annem → annesinin" iyelik kişisi dönüşümü (meşru dolaylı anlatım, kural yok).

## Açık kapsam

- Modelin doldurduğu form bağımsız doğrulanmıyor; yanlış kaynak dilbilgisi okuması yapısal PASS üretebilir. `NONE_STATED` ve `WORDS` seçimleri biçimbilimle çapraz denetlenmeli (ilgi hâli + ortaç başı kuralı kişi eki modülünde var).
- 14 pasaj, tek kitap, iki koşu. Kararlılık için çoklu koşu uzlaşması ya da kısıtlı çözümleme denenmedi.
- `reading_views` (tire/drop-cap birleşimi) bağlanmadı. Üretime, imaja ve pakete bağlı değil; `semantic_acceptance=false`. Rol V8 yerine geçirilmesi önerilmez; ölçüm, V8'in fazla retlerinin tek çağrıyla azaltılabildiğini ve deterministik kapının zorunlu olduğunu gösterir.
