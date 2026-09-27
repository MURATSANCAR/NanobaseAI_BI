# Sesli okumaya efekt sesleri — kaynaklar, lisanslar, havuz, kapsama

Tarih: 2026-09-27/28. Karar: her şey YEREL (bulut servis yok, kitap metni dışarı gitmez). Kullanıcı isteği: «çocuk
kitapları için kitap içinde patlama, vak vak, rüzgâr, ateş vs. için efekt sesleri; ücretsiz olanlardan devasa bir havuz,
ihtiyaç olanı doğrudan kullan» + «havuz o kadar geniş olmalı ki her kitabı sorunsuz ve eksiksiz karşılamalı».

Kod: `apps/editor/src/editor/production/sfx.py` (kitap: ipucu, seçim, karışım), `sfx_library.py` (havuz: katalog,
arama, önizleme, kaynakça), `api_sfx.py` (uçlar); havuzu kuran betikler `apps/editor/deploy/sfx/`; ekran
`src/canvas/editorial/studio/narration/SoundEffects*.tsx`; köprü `backend/semantic_bridge/editorial_studio_sfx.py`.

## 1. Kaynak seçimi (lisans kuralı: ticari kullanım + atıfsız ya da atfı künyeye yazılabilir + resmî indirme yolu)

| Kaynak | Lisans (kaynak sayfasından) | Durum | Not |
|---|---|---|---|
| Sonniss #GameAudioGDC 2015–2020 | [GDC Bundle lisansı](https://sonniss.com/gdc-bundle-license/): telifsiz, ticari, **atıfsız**; ses dosyası olarak yeniden dağıtım yasak; **yapay zekâ eğitiminde kullanım yasak** | ALINDI | Resmî sayfa [sonniss.com/gameaudiogdc](https://sonniss.com/gameaudiogdc)'deki «Mirror #1» = `ftpmirror.your.org/pub/misc/sonniss*`. Her yılın License.pdf'i arşivle saklandı. Havuz ürün dışına verilmez; yalnız bitmiş esere (sesli kitap) karıştırılır. Gömme (arama dizini) eğitim değildir; model bu seslerle eğitilmez. |
| Sonniss #GameAudioGDC 2021–2024 | aynı | ALINAMADI | Ana adres `downloads.sonniss.com` Cloudflare «Just a moment» denetimi istiyor (aşılmaz, kural); `hippolytus.feralhosting.com` aynası TCP bağlantısını kabul edip yanıt vermiyor (2026-09-27, GPU'dan ve Mac'ten). Resmî torrent dosyası da Cloudflare arkasında. Kullanıcı tarayıcıdan indirip GPU'ya koyarsa `indir_sonniss.sh` yerine elle `_indir/sonniss/<yıl>/` altına bırakılıp `havuz.py ac` ile eklenir. |
| Kenney ses paketleri | [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) (her paket sayfasında «License: Creative Commons CC0») | ALINDI (8 paket) | [kenney.nl/assets/category:Audio](https://kenney.nl/assets/category:Audio). Konuşma paketleri (voiceover-pack, voiceover-pack-fighter: İngilizce seslendirme) efekt olmadığı için alınmadı. |
| FSD50K (Freesound klipleri) | Klip başına Freesound yükleyicisinin lisansı (CC0, CC BY 3.0, CC BY-NC 3.0, Sampling+); küme [Zenodo 4060432](https://zenodo.org/records/4060432) | ALINDI (yalnız **CC0 + CC BY**) | NC ve Sampling+ klipler kataloğa girmez. CC BY klipler kitap sonundaki «ses efektleri kaynakçası»na yazar + başlık + Freesound bağlantısıyla girer (künyeye kendiliğinden). Zenodo md5'leriyle doğrulandı. |
| OpenGameArt (seçilmiş CC0 paketler) | Sayfanın «License(s)» alanı yalnız CC0 (tek tek okundu) | ALINDI (11 sayfa) | Toplu tarama/kazıma yok; `indir_opengameart.sh`'teki liste elle seçilmiş sayfalar. |
| Wikimedia Commons | Dosya başına: kamu malı, CC0, CC BY (SA/NC/ND ve GFDL alınmaz) | ALINDI (resmî MediaWiki API) | Kök kategoriler `indir_commons.py`'de; alt kategorilere 4 kat inilir (Commons kategori ağı döngülü). BY-SA bilinçli alınmadı: karışımdaki sayfa sesini de aynı lisansa bağlardı. CC BY dosyalar kaynakçaya girer. |
| Freesound (CC0, doğrudan) | CC0 | KULLANICI ANAHTAR AÇARSA | Resmî API anahtar ister; hesap açılmadı. FSD50K zaten Freesound'un 19.873 CC0 + 23.506 CC BY klibini veriyor. Anahtar açılırsa yalnız `license:"Creative Commons 0"` süzgeciyle indirici yazılabilir. |
| BBC Sound Effects (RemArc) | Kişisel/eğitim/araştırma; ticari değil | ELENDİ | Ticari kullanım yok. |
| ESC-50, UrbanSound8K, AudioSet | NC / YouTube kaynaklı | ELENDİ | Ticari değil ya da hak belirsiz. |
| xeno-canto (kuş sesleri) | Çoğu CC BY-NC-SA | ELENDİ | NC. |
| Pixabay, Mixkit, Zapsplat, SoundBible | Kendi lisansları; kayıt/Cloudflare/sayfa kazıma gerekir; Zapsplat ücretsiz katmanda atıf + hesap | ELENDİ | Resmî toplu indirme yolu yok. |

## 2. Havuz (GPU `/data/editor/sfx`)

Yer kararı: `/data` 5,8 TB, kurulum başında 3,5 TB boş. Kural: en az %20 (1,16 TB) ve en az 500 GB boş kalsın → tavan
≈ 2,3 TB. Lisansı temiz, resmî yolu açık kaynakların hepsi bu tavanın çok altında kalıyor (ayrıntı: bölüm 4); yer
sınır olmadı, sınır lisans ve erişim.

Klasör yapısı: `<kaynak>/…` (açılmış dosyalar), `<kaynak>/katalog.jsonl` (kaynak, lisans + bağlantı, özgün ad,
kategori, süre, örnekleme hızı, kanal, LUFS, tepe, kırpılma oranı, sha256, atıf), `_dizin/` (birleşik katalog, ses
gömmesi `gomme.npy`, göbek düzeltmesi `gobek.npy`, metin kolu `metin/metin.onnx`), `_indir/` (arşivler), `_olcum/`
(kapsama ölçümü), `uretim/` (yerelde üretilen efektler). Mac artığı (`._*`, `__MACOSX`) açılmaz; sayım 0.

İşaretler (katalogda `flags`): `yuksek` (> −10 LUFS), `kirpik` (örneklerin > %0,1'i tam ölçekte), `uzun` (> 120 sn),
`kisa` (< 0,15 sn), `sessiz` (< −60 LUFS ya da tepe < −50 dBFS). Aramada kırpık/sessiz dosya geri düşer.

SONUÇ_HAVUZ

## 3. Arama (metinden ses)

- Gömme modeli: **LAION CLAP `laion/larger_clap_general`** (HF model kartı **Apache-2.0**; rev `ada0c23a…`, sha256'lar
  `/data/editor/models/MANIFEST.json`'da, LICENSE yanında). Ses kolu havuz kurulurken GPU 0'da geçici kapta küçük bellek
  payıyla (%5) çalıştı; metin kolu ONNX'e çevrildi (torch ile kosinüs 1,0) ve stüdyo kabında CPU'da çalışır
  (onnxruntime). Not: LAION-Audio-630K eğitim verisinde ticari olmayan kayıtlar da var; modelin kendi lisansı Apache-2.0,
  biz yalnız arama için kullanıyoruz (üretim yok, eğitim yok).
- Puan = kosinüs(sorgu, ses) − 0,5 × göbek + 0,25 × etiket eşleşmesi; göbek (CSLS) = dosyanın kategori ağacından
  üretilen 409 genel sorguya en yüksek 10 benzerliğinin ortalaması (her aramada öne çıkan «her şeye benzeyen» uzun/karışık
  kayıtlar geri düşer). Türkçe tarif Zeki AI ile İngilizceye çevrilir (yayınevi düzeyinde önbellek); model yoksa
  kategori ağacındaki Türkçe anahtar kelimelerle.
- Kategori ağacı `sfx_library.CATEGORIES`: 11 grup, 100+ kategori, her kategoride İngilizce ve Türkçe anahtar kelime.

## 4. Kapsama ölçümü (yayınevinin çocuk kitapları)

SONUÇ_KAPSAMA

## 5. Boşluk doldurma: yerelde efekt üretimi

| Model | Lisans | Karar |
|---|---|---|
| **MOSS-SoundEffect v2.0** (OpenMOSS) | Apache-2.0 (HF kartı + github.com/OpenMOSS/MOSS-TTS) | **SEÇİLDİ**: metinden 48 kHz, ≤ 30 sn; havuzda karşılığı olmayan ipucu için üretilir, `uretim/` altına «Zeki AI üretimi» olarak girer |
| MiDashengLM-Gen (Xiaomi) | Apache-2.0 | Aday (denenmedi) |
| Stable Audio Open 1.0 / Small | Stability AI Community License (yıllık gelir 1 M$ altı ücretsiz) | **KOŞULLU** — kullanıcıya bırakıldı, kullanılmadı |
| AudioLDM 2, Tango 2 | CC BY-NC-SA 4.0 | ELENDİ (NC) |
| AudioGen (AudioCraft), MMAudio | CC BY-NC 4.0 | ELENDİ (NC) |
| Woosh (Sony) | Ticari olmayan | ELENDİ |

SONUÇ_URETIM

## 6. Karışım kuralları (sfx.py)

- Anlatım 0. saniyeden olduğu gibi başlar; kelime zamanları değişmez (e-kitap vurgusu bozulmaz). Karışım ayrı dosya
  (`ses/efekt/karisim/<sayfa>.mp3`); efekt kapalıysa ya da karışım eskiyse anlatım çalar.
- Anlık efekt: kelimenin başında («birlikte») ya da alıntının bitiminde («ardından»); dosyanın en çok 4 sn'si, kuyruk
  0,25 sn yumuşak kısılır; düzey −23 LUFS (dosyanın ölçülmüş yüksekliğinden) + editörün ±dB'si.
- Ortam: −38 LUFS, sayfa boyunca döngü, giriş/çıkış 1,5 sn.
- Efekt yolu anlatım sürerken otomatik kısılır (sidechain; anlatım anahtar).
- Son sayfa sesi −16 LUFS, gerçek tepe −1,5 dBTP, iki geçişli doğrusal normalleştirme.
- Varsayılan: profildeki yaş bandı 12 yaşın altında başlıyorsa açık, değilse kapalı; bant yoksa kapalı.

## 7. Kurulumda gerekenler

1. GPU: `/data/editor/sfx` hazır (bu çalışma). Stüdyo kapları için **birim**: `deploy/docker-compose.yml`'de
   `editor-studio` ve `editor-studio-worker`'a `${EDITOR_ROOT}/sfx:/data/editor/sfx:ro` (imaja girmez).
2. Stüdyo imajı `editor-py-studio` yeniden derlenir: `ffmpeg` + `onnxruntime==1.30.0` + `tokenizers==0.23.2`
   (images/studio/Dockerfile). Deneme derlemesinde boyut 1,56 → 2,29 GB.
3. GPU giriş kapısı: `sudo python3 deploy/tt-gpu/editor-ingress/add-studio-routes.py` (EDITOR-STUDYO-EFEKT bloğu).
4. Köprü + ön yüz: main'e alınınca olağan kurulum (test sunucusu → VM). Müşteri VM'inde havuz GPU'dadır; VM stüdyoyu
   GPU üzerinden kullandığı için ek kopya gerekmez.
5. Model çağrıları gateway üzerinden (`book-director`); üretim modeli (MOSS) gateway'e takma ad olarak EKLENMEDİ: şimdilik
   yalnız havuz doldurma betiği (`uret.sh`) geçici kapta çalıştırır. Canlıda «bulunamadı → o anda üret» için gateway'e
   `book-sfx` takma adı ayrı iş.
