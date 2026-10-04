# Kitaptan film, çizgi film ve sosyal medya kısa videosu — hat sözleşmesi

2026-10-04. Kullanıcı kararı: «paralelde hem sosyal medya paylaşımları hem de çizgi film için uçtan uca yapı; modelleri
ayağa kaldırma, sadece kod tarafını hazırla». Kod: `src/editor/production/film/`, uçlar `production/api_film.py`,
video servisi `images/video/`. Testler `tests/test_film.py` (modelsiz).

## Tek hat, üç biçim

| Biçim | Oran | Süre | Altyazı | Kanca | Ses düzeyi |
|---|---|---|---|---|---|
| `cizgi-film` | 16:9, 1920×1080 | 60–600 sn | ayrı .srt | — | −16 LUFS |
| `fragman` | 16:9 | 45–120 sn | ayrı .srt | ilk 5 sn | −14 LUFS |
| `reels` | 9:16, 1080×1920 | 15–90 sn | görüntüye basılı + .srt | ilk 3 sn | −14 LUFS |

Üslup: 2B çizgi film, 3B animasyon, suluboya, gerçekçi (`spec.STYLES`). Paylaşım kesitleri bitmiş filmden alınır:
Instagram Reels, TikTok, YouTube Shorts, YouTube, Instagram kare (`spec.PLATFORMS`); oran farklıysa bulanık dolgu.

## Adımlar ve onaylar

| # | Adım | Ne yapar | Model (gateway) | Onay |
|---|---|---|---|---|
| 1 | senaryo | Kitap özetinden çekim listesi; her çekim kitaptan birebir cümleye bağlı | `book-director` | editör |
| 2 | oyuncular | Karakter → onaylı kart (görünüş + referans) ve katalogdan ses | — | editör |
| 3 | ses | Replikler duygusuyla okunur; çekim süresi gerçek ses süresine uzar | `book-voice` | — |
| 4 | kareler | Her çekimin ilk karesi, karakter referansıyla; görsel denetçi | `book-image`, `book-vision-fast` | editör |
| 5 | çekim | İlk kare hareketlenir; tek konuşanlı yakın planda ağız sese uyar | `book-video` (KAPALI) | — |
| 6 | kurgu | Çekim + replik + efekt + ortam; kısma; ses düzeyi; altyazı | — (ffmpeg) | editör |
| 7 | paylaşım | Platform kesitleri, kapak karesi, açıklama + etiket taslağı | `book-director` | editör |

Bir adım yeniden üretilince sonraki adımlar «eski» olur (`store.set_stage`). Onaysız paylaşım paketi indirilemez.
Otomatik paylaşım yoktur (dış gönderim kapalı).

## Kurallar (kitaptan bağımsız)

- Çekim 2–10 sn. Uzun sahne art arda çekimdir. Replik süresi: 2,4 kelime/sn tahmini, gerçek süre sesten.
- Senaryo denetimi (`spec.check`): toplam süre biçim aralığında, çekim süresi sınırda, konuşan/görünen oyuncu
  listesinde, replik çekime sığıyor, görüntü tarifi dolu. Ölümcül sorun → senaryo sorunlarıyla yeniden istenir
  (en çok 3). Kitapta bulunamayan alıntı ölümcül değil, editöre «kanıtsız» gösterilir.
- Duygu → Sesli Okuma'nın ölçülmüş ifade tablosu (`expression.TABLE`); yeni ton ölçülmeden eklenmez. Bağırma =
  öfke hızı + kazanç.
- Ses seçimi: yaş + cinsiyet + rol kelimesi → `voices_zeki` katalogu; aynı ses iki ana karaktere verilmez. Katalogda
  çocuk sesi yok: çocuk karakter genç sesle okunur.
- Görsel denetçi kareyi reddederse yeni tohumla en çok 2 kez yeniden çizilir; çekim için üç örnek karede bakılır,
  bir kez yeniden çekilir. Yine geçmeyen editörün önüne «denetimden geçmedi» notuyla gelir.

## Video servisi sözleşmesi (`images/video/server.py`)

`POST /v1/video/generations` `{model: book-video, mode: i2v|s2v, image, prompt, negative_prompt, seconds, width,
height, seed, audio?}` → `{video, seconds, fps, frames, engine}`. Motor şimdilik Wan 2.2 (I2V-A14B, S2V-14B; kod
commit `1ea34ff4`). 81 karelik parçalar son kareden devam eder (16 fps). MiniMax-H3 / HunyuanVideo 1.5 karşılaştırması
bitince kazanan aynı sözleşmenin arkasına girer; istemci değişmez.

## Henüz yapılmayan (bilerek)

- **Modeller ayağa kaldırılmadı** (kullanıcı kararı 2026-10-04). `models.yaml`'daki `book-video` bloğu yorum
  satırıdır; çekim adımı başlatılırsa «Video üretimi bu kurulumda henüz açık değil» döner. Açma sırası: ağırlıkları
  `/data/editor/models/book-video/{i2v,s2v}` altına taşı → MANIFEST'e sha256 → `editor-video:1` derle → bloğu aç →
  açılış süresi, bellek tepesi, çekim başı süre ölç ve buraya yaz.
- Video servisi kodu GPU'da hiç çalıştırılmadı: Wan'ın `generate` imzası kaynak koddan okundu (guide_scale ikilisi,
  s2v `init_first_frame`), ilk kurulumda doğrulanacak.
- Büyütme (SeedVR2) ve ara kare (RIFE) servisi yok; kurgu lanczos ölçekler.
- Müzik yok; efekt ve ortam sesi GPU'daki telifsiz efekt havuzundan.
- Portal ekranı ve köprü vekili yok (sonraki adım).
