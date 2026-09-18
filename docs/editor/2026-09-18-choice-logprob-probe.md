# Kapalı kümeli aday olasılığı — büyük Qwen ile, eğitimsiz (18 Eylül 2026)

## Soru

NanoJev'in (Qwen3-0.6B üzerine karar başlıkları; metin üretmeden adaylar üzerinde olasılık dağılımı) bize çekici gelen iki özelliği, kapalı küme ve dağılım, canlı büyük Qwen'den eğitimsiz alınabilir mi?

## Bulgu: alınabilir

Canlı vLLM ucu (`qwen3.8-flash-next`) `structured_outputs.choice` ile kapalı kümeyi zorluyor (küme dışı token olasılığı −9999) ve `logprobs/top_logprobs` ile her adayın olasılığını döndürüyor. `guided_choice` alanı bu sürümde etkisiz. Yani NanoJev'in çıktı sözleşmesi (durum + soru + adaylar → dağılım) tek token'lık bir çağrıyla mevcut modelden elde ediliyor; eğitim, veri, ek GPU belleği gerekmiyor. NanoJev eğitimi bu aşamada gereksiz.

## Gerçek ölçüm

Sürücü `apps/editor/scripts/probe-choice-logprob.py` (`choice-logprob-probe-v1`), canlı `api` konteynerinde, girdi `evidence/v16-r5-eligible-claims-readonly.json` (R5'in kabul edilmiş 91 gerçek iddiası ve kayıtlı kaynak metni). Soru: "iddiadaki her yüklemin öznesi kaynaktaki öznesiyle aynı mı?" A evet / B hayır / C anlaşılmıyor; yalnız tek token. Beklenen cevap verilmedi, uygulama yazımı 0. Kanıt: `evidence/choice-logprob-probe-20260918T212652Z.json`.

| Ölçü | Sonuç |
|---|---|
| Çağrı | 182 (91 × 2 geçiş), çağrı başına 1 çıktı token'ı |
| Süre | 86,4 sn ve 86,9 sn / geçiş (ardışık, toplu değil) |
| İki geçiş arasında olasılık farkı | **0,0** (91 iddianın hepsinde); 0,5 eşiğinde karar değişimi 0 |
| P(aynı özne) ≥ 0,9 | 78 |
| 0,5 ≤ P < 0,9 | 10 |
| P < 0,5 | 3 |
| Bilinen yanlış PDF27 iddiası | P(aynı özne) = 0,22, P(değişmiş) = 0,77 — 91 iddianın en düşük **2.**'si |
| En düşük 1. | PDF34 "Defne, … bir robot olduğunu … belirtir" (P = 0,15) — tek çağrılı formda koşular arası kararı değişen muğlak iddia |
| En düşük 3. | PDF21 edilgen cümle (P = 0,43) |

Karşılaştırma: aynı modelin serbest JSON formu (`source-subject-choice-v1`) PDF27'yi geçirmiş ve koşular arası kararsızdı. Tek token'lık kapalı küme aynı hatayı yakalıyor ve deterministik.

## Sınırlar

- Yine aynı modelin yargısıdır; bağımsız kanıt değildir. Biçimbilim kapısıyla AND olarak kullanılmalı; 0,5–0,9 bandı incelemeye gitmeli.
- 91 iddianın yalnız 1'i bilinen hatadır; diğer düşük olasılıklı iddialar gözle bakılmadı, etiket yok. Yakalama/yanlış alarm oranı doğrulama seti etiketlenmeden ölçülemez.
- Tek kitap, tek soru biçimi. Eşik (0,5 / 0,9) ölçülmüş bir kalibrasyon değildir.
- İstem birinci kişi kuralını içeriyor; bu dil kuralıdır, kitap kuralı değil. Kitap/karakter adı yok.
- Toplu çağrı denenmedi; roman ölçeğinde maliyet ölçülmedi.
- Üretime bağlı değil; `semantic_acceptance=false`.
