# Zaman çizelgesi (`timeline`) — ÖLÇÜM BEKLİYOR

Durum (2026-09-22): kod yazıldı, saf parçalar sentetik testle doğrulandı
(`tests/test_timeline.py`, 6 test). **Gerçek kitapta hiç koşmadı; kalıpların geri çağırması,
kesinlik ve eşikler ölçülmedi.** Ölçülene kadar bulgular yalnız editör adayıdır.

## 1. Editör ne bakar

Metnin zaman ifadeleri sayfa sırasında okunduğunda tutarlı mı: «ertesi sabah» dendikten sonra
aynı akış içinde aynı akşama dönüş; akşamdan öğlene geri gidiş; mevsimin bir geri gitmesi; bir
karakterin yaşının küçülmesi; doğum yılı, yıl ve yaşın tutmaması.

Çelişki OLMAYANLAR: geri dönüş/anı/rüya/hayal (MEMORY, DREAM, IMAGINATION, HYPOTHETICAL kipli
olaylar), özet ya da başka bir günün anlatımı, genel alışkanlık («her sabah»), selam («günaydın»,
«iyi geceler»), mecaz, farklı kişiler.

## 2. Çıkarma (deterministik, model yok — `timeline.extract`)

Kapalı Türkçe kalıplar, sayfa/paragraf/konum sırasıyla; alıntı kanıtı kalıbın geçtiği cümledir
(sayfanın kendi kelimeleri):

| tür | kalıp | değer |
|---|---|---|
| `GUN_VAKTI` | sabah / öğle(n) / akşam / gece (+ekler: -leyin, -üstü, -yarısı, -si, …) | SABAH, OGLE, AKSAM, GECE |
| `GUN_GECISI` | ertesi gün/sabah/akşam/gece; sonraki gün/hafta; N gün/hafta/ay/yıl sonra; günler/haftalar/aylar/yıllar sonra | gün sayısı (hafta 7, ay 30, yıl 365; belirsiz çoğul: `TIMELINE_UNKNOWN_DAYS` × birim); «ertesi sabah» ayrıca vakit SABAH |
| `MEVSIM` | ilkbahar/bahar, yaz (yalnız mevsim bağlamında: «yaz geldi», «yazın», «yaz tatili»…), sonbahar/güz, kış | ILKBAHAR, YAZ, SONBAHAR, KIS |
| `YAS` | «<Ad> N yaşında/yaşındaydı/yaşına girdi-bastı-geldi» | yaş; özne karakter listesine eşlenir (`resolve_subject`), eşlenmezse normalleştirilmiş ad; cümledeki yıl varsa `year` |
| `DOGUM` | «<Ad> … YYYY … doğdu/doğmuş» | doğum yılı |

Dışarıda: «her/bütün/bazı sabah…», «günaydın», «iyi akşamlar/geceler»; gün-geçişi kalıbının
içindeki vakit sözcüğü ayrıca vakit sayılmaz.

## 3. Sıra denetimi (deterministik, `timeline.check_order`)

Durum makinesi: gün sayacı, gün vakti, mevsim, özne başına yaş/doğum yılı. Yalnız gerçek olmayan
kipte olay taşıyan sayfalar (`_continuity.unreal_pages`: MEMORY/DREAM/IMAGINATION/HYPOTHETICAL;
gerçek olayla karışık sayfa girer) sıraya girmez.

- **GUN_VAKTI geri:** yeni vakit öncekinden erken. SABAH'a dönüş **örtük yeni gün** sayılır (aday
  değil, gün sayacı +1); diğer geri adımlar (akşam→öğle, gece→akşam, gece→öğle, öğle→… hariç) aday.
  Gün geçişi vakti sıfırlar.
- **MEVSIM geri:** döngüsel uzaklık 3 (yaz→ilkbahar aday; kış→ilkbahar ileri, aday değil).
- **YAS geri:** aynı özne için küçülen yaş.
- **TARIH:** doğum yılı ile (yıl, yaş) çifti: `yıl − doğum ∉ {yaş, yaş+1}` → aday (iki yönde:
  önce doğum sonra yaş, ya da tersi).

## 4. Yargı ve bulgu

Kitabın bütün metni + iki ifade + «okunan sıra sorunu», director'a kapalı soru, **iki sırada**;
cevap tek harf C/U/B, olasılık logprobs'tan (`Llm.choose`). Bulgu ancak
`min(C_ileri, C_geri) ≥ TIMELINE_JUDGE_MIN`. Metinde geri dönüş/anı/özet açıklaması varsa U beklenir.

Her bulgu iki kanıt (iki sayfa + alıntı; `details.a/b`). Şiddet: YAS/TARIH ve olasılık ≥
`TIMELINE_ERROR_MIN` → ERROR, diğerleri WARN. INFO satırı: ifade sayıları, dışlanan sayfalar, aday/bulgu.

## 5. Eşikler (ayardan; hepsi ölçülmedi)

| ad | env | varsayılan | anlamı |
|---|---|---|---|
| `timeline_judge_min` | `EDITOR_TIMELINE_JUDGE_MIN` | 0.5 | iki sırada gereken «çelişki» olasılığı |
| `timeline_error_min` | `EDITOR_TIMELINE_ERROR_MIN` | 0.8 | YAS/TARIH'te bu üstü ERROR |
| `timeline_parallel` | `EDITOR_TIMELINE_PARALLEL` | 4 | eşzamanlı yargı çağrısı |
| `timeline_unknown_days` | `EDITOR_TIMELINE_UNKNOWN_DAYS` | 2 | «günler sonra» kaç birim sayılır (yalnız gün sayacı; adaya etkisi yok) |

## 6. Model çağrısı sayısı

Çıkarma 0; yargı aday başına 2 (director). Kitap metni her soruda önek olduğu için önbellek çalışır.

## 7. Yanlış alarm / kaçırma riskleri

1. Kalıp dışı zaman anlatımı («güneş batarken», «yıldızlar çıkınca») okunmaz → kaçırma. Ölçümde
   kaçan kalıplar genel Türkçe olarak eklenir; kitaba özel kelime eklenmez.
2. Diyalog içindeki vakit («Akşam gel!») akış vakti değildir → yanlış aday; yargı «farklı olay»
   demeli. Ölçümde diyalog kaynaklı aday oranı sayılır; yüksekse tırnak içi ifadeler dışlanır
   (açık karar).
3. «yaz» sözcüğü: yalnız mevsim bağlamlı ekler/komşularla alınır; «yazı», «yazdı» alınmaz. Bazı
   mevsim anlamlı «yaz» kullanımları kaçabilir.
4. Yaş kalıbı ad-öncelikli («Ali on yaşında»); «on yaşındaki Ali» kaçar (özne sonra geliyor).
5. Sayfa hem gerçek hem anı olayı taşıyorsa anıdaki vakit sıraya girer; yargı ayırır.

## 8. ÖLÇÜM BEKLİYOR — ölçüm planı (gerçek kitap, GPU sunucusu)

```sh
ssh tt-gpu 'docker exec -i editor-mcp python -m editor.proofing <generation_id> --only timeline --dry' > timeline-<kitap>.json
ssh tt-gpu 'docker exec -i editor-mcp python -m editor.proofing <generation_id> --only timeline'
```

Ölçülecekler (altı kitap):
1. **Kalıp geri çağırması:** her kitabın metnindeki zaman ifadeleri elle işaretlenir; `stats.by_kind`
   ile karşılaştırılır. Kabul ≥ 0.8 (kaçanlar genel kalıp olarak eklenir).
2. **Sıra kesinliği:** `candidates_detail` etiketlenir (gerçek / anı-geri dönüş / diyalog / özet /
   kalıp hatası); eşikler bu kümede seçilir.
3. **Geri çağırma (enjekte):** «Ertesi sabah …» sonra «O akşam sofrada …» yerine «Aynı öğlen …»
   eklenip bulgu çıkmalı; «Ali dokuz yaşındaydı» / «Ali yedi yaşındaydı» ERROR çıkmalı; araya
   «yıllar önceydi, hatırladı» eklenince çıkmamalı.
4. **Maliyet:** aday sayısı × 2 çağrı; kitap başına süre.

## 9. Açık kararlar

- Diyalog içi vakit ifadeleri dışlansın mı (§7.2) — önce ölçüm.
- Gün sayacı şu an adaya dönüşmüyor (örn. «iki gün boyunca» ile sayılan gün uyuşmazlığı); ölçümde
  ihtiyaç görülürse kural eklenir.
- Anı/rüya sayfaları `usable_event` üzerinden geliyor; olay çıkarımı koşmamış nesilde dışlama yok
  (INFO satırında 0 görünür).
