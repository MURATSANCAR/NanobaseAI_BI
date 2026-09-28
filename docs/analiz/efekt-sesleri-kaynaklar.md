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

Ölçüm anındaki havuz (2026-09-28 03:00; `havuz.py rapor` → `_olcum/havuz-rapor.json`):

| Kaynak | Dosya | Boyut | Süre |
|---|---|---|---|
| FSD50K (CC0 + CC BY, dev kümesi) | 34.976 | 21,5 GB | 67,6 sa |
| Sonniss 2015, 2016, 2017 (1–5. parça) | 1.806 | 39,7 GB | 24,6 sa |
| Wikimedia Commons | 2.241 | 14,7 GB | 52,0 sa |
| Kenney | 611 | 0,03 GB | 0,2 sa |
| OpenGameArt CC0 | 578 | 0,02 GB | 0,2 sa |
| Zeki AI üretimi | 38 | 0,01 GB | — |
| **Toplam** | **40.250** | **76 GB** | **144,6 sa** |

Sürenler (gözetimsiz, `tamamla.sh` bitince ekler): Sonniss 2017 (6–9), 2018, 2019, 2020 (~95 GB; ayna 2–6 MB/s'ye
düştü), FSD50K eval (CC0+CC BY ~8,4 bin klip), Commons'un kalan adayları (API isteği POST'a alındı: 40 uzun başlık GET
adresine sığmıyordu, HTTP 414). İşaretliler: yüksek 922, kırpık 953, uzun 718, kısa 129, sessiz 151; kategorisiz 2.684.

Kategori kapsaması (dosya etiketinden; bir dosya birden çok kategoride sayılabilir) — kullanıcının saydıkları:
ördek 86, köpek 627, kedi 541, horoz 167, inek 60, kuş 1.560, aslan/büyük kedi 513; rüzgâr 3.630, yağmur 781, gök
gürültüsü 656, dalga 664, dere 728, ateş 914; kapı 2.750, zil 1.478, saat 1.515, araba 3.253, tren 800; patlama 1.687,
düşme 1.416, koşma 875, çarpma 2.865, sıçrama 369; boing 365, whoosh 414, pop 462, ding 494; orman 479, sahil 229,
okul/oyun alanı 935, şehir 953. Eksik kategori yok; en ince: öpücük 3, maymun 23, kazma 28, papağan 30, kartal 35,
su altı 38, baykuş 40, balina/yunus 44.

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
- Seçim (`sfx.rerank`): aramanın ilk 16 adayı Zeki AI'ye adı/klasörü/etiketi/süresiyle gösterilir; tek harf (A…P) ya
  da X (hiçbiri) kapalı kümede, olasılıklar belirteç olasılığından. Adaylar bu olasılıkla sıralanır; varsayılan birincisi,
  ekranda ilk 3'ü. İpucu kaydında `fit` = 1 − P(X).
- Hata ve düzeltme (2026-09-28): kaydedilen tokenizer dolgu ayarını taşıyordu, stüdyonun metin kodlayıcısı dolgu
  belirteçlerine de dikkat ediyordu → bütün sorgular aynı birkaç «göbek» dosyaya gidiyordu. Kodlayıcı dolguyu kendisi
  yapar ve maskeler; `havuz.py metin` uçtan uca eşdeğerliği (stüdyo kodlayıcısı ↔ torch, kosinüs 1,0) denetler.

## 4. Kapsama ölçümü (yayınevinin çocuk kitapları)

Derlem: GPU `/data/organized` (yalnız okuma) — `cocuk/` altındaki bütün PDF'ler + künyesinde 12 yaşın altında
başlayan bant yazan öteki kitaplar; aynı metin tek sayılır → **390 kitap, 21.120 sayfa, 1,83 M kelime**
(`deploy/sfx/kapsama.py metin`). Metin okumadaki paragraf kurucuyla.

İpucu çıkarımı: stüdyonun istemiyle (sfx.PROMPT, kitaba özel değil), Zeki AI gateway üzerinden, 4 sayfa bir çağrıda,
**üç tur** (1 × sıcaklık 0,2 + 2 × 0,7; turların birleşimi). 0,2'de model çok sayfalı parçada çoğunlukla boş liste
verdi (dere sayfası: 0,2 → 0 ipucu, 0,7 → «şırıl şırıl akan»); stüdyo bu yüzden 3 × 0,7 okuyup 2/3 oylar.
Alıntısı metinde birebir geçmeyen ipucu atıldı (tur başına ~%6). Sonuç: **3.596 ipucu geçişi, 2.647 benzersiz tarif**
(anlık 2.497, ortam 150). En sık kategoriler: su 192, çarpma 164, koşma 125, rüzgâr 125, araba 96, düşme 93,
kalabalık 88, kapı 80, gülme 75, ateş 59, kırılma 59 …

Karşılandı ölçüsü (stüdyonun seçim yolu, `kapsama.py secim`): aramanın ilk N adayı Zeki AI'ye adı/klasörü/etiketiyle
gösterilir, tek harfle en uygunu ya da «hiçbiri» seçilir (belirteç olasılığı); **P(uygun ses var) ≥ 0,5 → karşılandı**.
Ses dinlenmediği için ölçü tutucudur: sesi doğru ama adı «20090610 0 ambience.ogg» olan dosyaya «hiçbiri» diyebilir.
Dinleyerek doğrulamak için her puan bandından çiftler `_olcum/dinleme-ornekleri.json`'da.

| Durum (havuz) | Benzersiz tarif karşılanan | Geçiş (kitaptaki her kullanım) |
|---|---|---|
| 40.212 dosya, ilk 8 aday | %71,4 (1.889 / 2.647) | %76,5 |
| 40.212 dosya, ilk 16 aday (stüdyo varsayılanı) | **%79,4** (2.101) | **%83,2** |
| + 38 yerel üretim (en az 2 kez geçen karşılanmayanlar) | %79,1 (seçim yeniden koşuldu; model seçiminde ±%0,5 oynama) | %83,9 |

Karşılayan kaynak (16 aday): Freesound/FSD50K 1.835–1.915, Sonniss 88–92, Commons 69–81, OpenGameArt 13, Kenney 2–3,
üretim 82. Benzerlik puanı eşiğiyle (0,2) kapsama %98,1 görünür ama bu puan tek başına doğruluk göstermez (yargıda ilk
adayın doğru çıkma oranı %42) — rapor bunu değil Zeki AI seçimini esas alır.

Hedef ≥ %98'e ulaşılmadı. Karşılanmayanlar çoğunlukla tek kez geçen, çok özgül tarifler (ör. «filin ağır adımları»,
«simit yeme sesi», «koltuğa oturma», «deprem sarsıntısı», «ud tellerinin tınlaması», «tablet bildirim sesi», «ezan»);
listenin tamamı `_olcum/karsilanmayan.json`, en sık 50'si `_olcum/rapor.json`. Kapatma yolu (sürüyor, §5):
karşılanmayan her tarif için yerel üretim + Sonniss 2017–2020'nin kalan arşivleri; ölçüm zinciri (`tamamla.sh`)
indirme ve üretim bitince havuzu genişletip ölçümü kendiliğinden yeniden koşar.

## 5. Boşluk doldurma: yerelde efekt üretimi

| Model | Lisans | Karar |
|---|---|---|
| **MOSS-SoundEffect v2.0** (OpenMOSS) | Apache-2.0 (HF kartı + github.com/OpenMOSS/MOSS-TTS) | **SEÇİLDİ**: metinden 48 kHz, ≤ 30 sn; havuzda karşılığı olmayan ipucu için üretilir, `uretim/` altına «Zeki AI üretimi» olarak girer |
| MiDashengLM-Gen (Xiaomi) | Apache-2.0 | Aday (denenmedi) |
| Stable Audio Open 1.0 / Small | Stability AI Community License (yıllık gelir 1 M$ altı ücretsiz) | **KOŞULLU** — kullanıcıya bırakıldı, kullanılmadı |
| AudioLDM 2, Tango 2 | CC BY-NC-SA 4.0 | ELENDİ (NC) |
| AudioGen (AudioCraft), MMAudio | CC BY-NC 4.0 | ELENDİ (NC) |
| Woosh (Sony) | Ticari olmayan | ELENDİ |

Kurulum: ağırlıklar `/data/editor/models/sfx-uretim/MOSS-SoundEffect-v2.0` (HF rev `e35df4d8…`, 11 GB, SHA256SUMS +
MANIFEST.json kaydı, LICENSE), kod `github.com/OpenMOSS/MOSS-TTS @ 934d6826…`, kendi Python ortamı
`/data/editor/sfx/_ops/moss-venv` (torch 2.9 cu128; paket torch 2.9/transformers 4.57 istiyor). Betikler `uret.sh`
(agirlik | ortam | uret) ve `uret.py`. Ölçülen: GPU'da ~15 sn/ses (100 adım, 4 sn anlık / 12 sn ortam), bellek ~17 GB;
işlemcide ~2,5 dk/ses. GPU 0 (BI modeli) doluydu (12 GB payda bellek yetmedi); editörün kartı 1'de yalnız kartta
başkalarına en az 8–12 GB kalıyorken ve stüdyoda süren iş yokken üretilir, yer kalmazsa model bellekten çıkar.

Yapılan: en az iki kez geçen 38 karşılanmayan tarif GPU 1'de üretildi (9,6 dk) ve havuza «Zeki AI üretimi» olarak
girdi. Kalan ~508 tek geçişli tarif işlemcide gözetimsiz üretiliyor (kartlara dokunmaz; ~20 saat), ardından
`tamamla.sh` kataloğu/gömmeyi/ölçümü yeniler. Üretilen seslerin kalitesi DİNLENMEDİ; ölçüm bunları kendi tarifleriyle
eşleştirdiği için «karşılandı» saymaya yatkındır — editörün dinleyerek elemesi gerekir (kütüphanede kaynak adı «Zeki AI
üretimi»). Canlıda «bulunamadı → o anda üret» için gateway'e takma ad eklenmedi (ayrı iş).

## 5b. İpucu çıkarımının sağlamlaştırılması (deneme kitabında görüldü)

- Model sayfa başına çoğu okumada boş liste veriyordu: «Vak vak!» geçen 7. sayfada 3 okumanın 2'si boş, oylama
  ipucunu düşürdü. Düzeltme: dil kuralı (`sfx.sound_hints`: ikilemeler + Türkçe ses fiili kökleri; kitaptan bağımsız)
  (1) istemde «şu ifadelere ayrıca karar ver» diye gider, (2) oylamada ayrı bir kanıt sayılır (kural + bir okuma
  = kalır). Karakterin ağzından çıkan yansıma sözcüğün efekt olduğu isteme açıkça yazıldı. Sonuç: aynı sayfada 3/3 koşuda
  «Vak vak» ve «Pıt pıt pıt».
- Okumalar aynı ipucuna farklı tarif yazabiliyor («Vakvak'ın eğlenceli seslendirme efekti» ↔ «ördek vaklıyor»);
  eşleştirme her tarifi dener, Zeki AI seçiminde uygunluğu en yüksek olan kalır.

- Zeki AI adaylardan emin değilse (uygunluk < 0,35) ses kendiliğinden seçilmez, karışıma girmez; ekranda «emin değil,
  dinleyip seçin» yazar (bir koşuda «Pıt pıt pıt» 0,19 uygunlukla «makine dönüşü»ne gitmişti).
- Çok sessiz kayıt karışımda en çok +18 dB yükseltilir (denemede +27 dB gürültü tabanını da kaldırıyordu); aramada
  −42 LUFS altı dosya hafifçe geri düşer.

## 5c. Deneme (iş `2026092716271423aee2` kopyası `202609280000005f0e01`, «Etimesgutlu Bebek Aslan»)

Son koşu (anlatım gerçek seslendirme modeliyle, öneri + seçim Zeki AI, karışım stüdyo imajında):

| Sayfa / anlatıcı | Efekt (alıntı → ses, kaynak, lisans) | Yer (sn) | Süre anlatım → karışım | LUFS / gerçek tepe |
|---|---|---|---|---|
| 5 / sıcak masalcı | «zıpladı» → Jump Arcade (Commons, CC BY 4.0; Zeki AI uygunluk 0,87) | 22,58 | 22,98 → 23,45 | −16,8 / −1,9 |
| 5 / kadın anlatıcı | aynı | 21,83 | 22,23 → 22,70 | −16,5 / −3,1 |
| 7 / sıcak masalcı | «Vak vak» → 20130403_duck.04 (Freesound, CC BY 3.0; 0,66); «Pıt pıt pıt» → Boing raw (Commons, CC BY 4.0; 0,69) | 5,06 · 15,23 | 26,65 → 26,65 | −16,8 / −1,7 |
| 7 / kadın anlatıcı | aynı | 5,07 · 13,91 | 24,99 → 24,99 | −16,5 / −2,8 |

Dosyalar (efektli ve efektsiz mp3 + `yerlesim.json`) oturumun scratchpad'inde `efekt-sesleri/`; kategori başına bir
örnek efekt `efekt-sesleri/ornekler/` (kaynak/lisans `ornekler.json`). Park ortamı bu koşuda önerilmedi (önceki bir
koşuda elle eklenmişti).

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
