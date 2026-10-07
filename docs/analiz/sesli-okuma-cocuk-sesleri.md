# Sesli okuma: çizgi film çocuk sesleri (2026-10-07)

Neden: ses kataloğunda (`voices_zeki.py`) çocuk sesi yoktu; kitaptan çizgi filmde çocuk karakterler (ilk deneme Timaş'ın
«Levent» serisi, ilkokul çağında bir erkek çocuk) genç sesle konuşuyordu. Katalogdaki eski küçük çocuk sesleri
2026-10-03'te kullanıcı tarafından «çok kötü» bulunup kaldırılmıştı (8 yaş tarifi kalitede tutmamıştı).

İstenen: «karakter» grubuna dört ses — erkek çocuk (7–10), kız çocuk (7–10), küçük erkek çocuk (4–6), küçük kız çocuk
(4–6).

**Durum:** 1. yöntemin (yalnız tarif) adaylarını kullanıcı dinledi: «daha iyilerini üret». 2. yöntem (tını
dönüştürme + klon, aşağıda «2. yöntem») ölçümle dört öneri verdi; kullanıcı seçimi ölçüme bıraktı, ana oturum doğrulayıp
sabitleyecek. Sesler kodda hâlâ «onay bekliyor» (`voices_zeki.CHILD_VOICES`, `PENDING`): katalogda görünmez, kimliği genç
sese gider; çocuk karakteri bugünkü gibi okunur.

## Yöntem

- Model ve kaynak: katalogla aynı — VoxCPM2 (`book-voice`, gateway üzerinden), yalnız yazılı İngilizce tariften
  tasarım. Gerçek kişi kaydı, klon, dış ses havuzu yok.
- Betik: `apps/editor/deploy/ses/cocuk_sesleri.py` (adımlar `uret`, `taban`, `sec`). GPU'da geçici kapta koştu
  (`editor-py-studio:0.15.9-f70ebaf0`, ağ `editor-net`); çalışan kaplara dokunulmadı, ses model kabını gateway açıp
  kapattı. Çıktı `tt-gpu:/data/editor/ses-havuzu/cocuk/` (`ham/<ses>/<tarif>-s<tohum>.wav|json`, `olcum.json`,
  `aday/`, `sec.md`).
- Ölçüm ses servisinin kendisinde (`measure: true`, `images/voice/server.py` `_measure`): ortanca perde (librosa pyin,
  60–600 Hz, etkin konuşma kareleri), sesli oranı, Türkçe hizalayıcının açgözlü çözümüyle harf hatası (cer).
- Cümle (`voices_zeki.CHILD_TEXT`, Türkçe özel harflerin hepsi): «Anne, bak! Bahçede kocaman bir kaplumbağa var. Adını
  Pamuk koyalım mı? Ben ona her gün su veririm, şimdi söz veriyorum.»
- Üç tur, 172 aday: 1. tur a–d tarifleri × 4 tohum (11, 23, 47, 89); 2. tur e–h × 6 tohum (+131, 197); 3. tur yalnız
  küçük kız d ve h tarifine 6 tohum daha (bantta iki aday kalmıştı). GPU'da üretim toplam ~3,5 dk; 2. tur gateway'in ses
  ve okuma modellerini sırayla açıp kapatması yüzünden 21 dk bekledi.

## Bulgular

1. **«high-pitched / very high / tiny» kelimeleri sesi cıyaklamaya götürüyor.** 1. tur tariflerinde perde 330–555 Hz,
   harf hatası %10–63; hiçbir aday kullanılamadı (voices_lively notundaki tuzağın aynısı, bu kez istenen yönde ama
   fazlasıyla). 2. turda perde kelimesi kaldırıldı, yerine yaş + sakin/net okuma yazıldı («not squeaky», «speaking
   slowly and clearly to his mother»): perde 250–320 Hz'e indi, hata yarıya düştü.
2. **Katalogdaki %5 harf hatası eşiği bu cümlede yetişkin seste de tutmuyor.** Taban ölçümü: katalogdaki genç kadın ve
   genç erkek tarifleri aynı çocuk cümlesini okudu (12 kayıt) → cer 0,053–0,213, ortanca 0,080. Ünlemli konuşma cümlesi
   ve «Pamuk» özel adı hatayı yükseltiyor; tanıyıcı yetişkin konuşmasıyla eğitilmiş. Bu yüzden eşik **cer ≤ 0,10**
   (yetişkin genç sesin bu cümledeki ortancası + 2 puan), sesli oranı ≥ 0,5 aynı. 172 adaydan yalnız biri %5'in altında
   (küçük kız d/613, 0,032).
3. **Perde tek başına çocuğu yetişkin kadından ayırmıyor.** Aynı cümlede genç kadın tarifi 300–335 Hz, genç erkek tarifi
   200–292 Hz okudu (cümlenin kendisi «çocukça» okutuyor). Hedef bant (7–10 yaş 230–340, 4–6 yaş 260–390 Hz) sıralamayı
   belirler, eleme ölçütü değildir; çocuk mu, çocuk taklidi yapan yetişkin mi ayrımı kullanıcının kulağına kalır.
4. Erkek çocukta e/g/h tarifleri bazı tohumlarda yetişkin erkeğe kaydı (128–200 Hz); kız çocukta f tarifi («not
   squeaky» dediği hâlde) 410–490 Hz'e çıktı.

### Taban (katalogdaki genç seslerin tarifiyle aynı cümle)

| Taban sesi | Tohum | f0 (Hz) | Sesli oranı | cer |
|---|---|---|---|---|
| genç erkek | 11 | 292,1 | 0,717 | 0,085 |
| genç erkek | 23 | 261,7 | 0,781 | 0,106 |
| genç erkek | 47 | 245,6 | 0,827 | 0,053 |
| genç erkek | 89 | 199,5 | 0,738 | 0,074 |
| genç erkek | 131 | 277,3 | 0,724 | 0,053 |
| genç erkek | 197 | 200,7 | 0,735 | 0,074 |
| genç kadın | 11 | 320,4 | 0,848 | 0,074 |
| genç kadın | 23 | 335,5 | 0,765 | 0,106 |
| genç kadın | 47 | 312,1 | 0,820 | 0,117 |
| genç kadın | 89 | 437,6 | 0,763 | 0,117 |
| genç kadın | 131 | 300,6 | 0,758 | 0,053 |
| genç kadın | 197 | 319,4 | 0,898 | 0,213 |

### Tarif başına özet (172 aday)

Tariflerin tam metni betikte (`TARIFLER`). a: «8 yaşında, tiz, berrak çocuk sesi»; b: «9 yaş, ergenlik öncesi, hafif»;
c: «çizgi filmde çocuk seslendirmen, enerjik»; d: «okul çocuğu, yumuşak tiz, utangaç» (küçüklerde «okul öncesi, ince
tiz ses, kısa duraklamalar»); e: «okul kitabından sesli okuyan, sakin, net»; f: «doğal çocuk sesi, cıyaklamayan, sakin»
(küçüklerde «annesine gününü anlatan»); g: «aile filminde çocuk anlatıcı, rahat»; h: «annesine yavaş ve net konuşan»
(küçüklerde «anaokulu çocuğu, kelime kelime yavaş»).

| Ses | Tarif | Aday | f0 ortanca (en az–en çok) | cer ortanca (en iyi) | Eşiği geçen |
|---|---|---|---|---|---|
| erkek çocuk | a | 4 | 451 (394–508) | 0,266 (0,149) | 0 |
| erkek çocuk | b | 4 | 460 (397–514) | 0,272 (0,160) | 0 |
| erkek çocuk | c | 4 | 351 (318–358) | 0,245 (0,106) | 0 |
| erkek çocuk | d | 4 | 326 (287–364) | 0,149 (0,117) | 0 |
| erkek çocuk | e | 6 | 250 (150–374) | 0,144 (0,106) | 0 |
| erkek çocuk | f | 6 | 367 (276–461) | 0,165 (0,064) | 2 |
| erkek çocuk | g | 6 | 228 (158–328) | 0,138 (0,117) | 0 |
| erkek çocuk | h | 6 | 186 (128–388) | 0,133 (0,085) | 1 |
| kız çocuk | a | 4 | 418 (330–472) | 0,293 (0,213) | 0 |
| kız çocuk | b | 4 | 525 (413–539) | 0,415 (0,340) | 0 |
| kız çocuk | c | 4 | 363 (336–377) | 0,266 (0,191) | 0 |
| kız çocuk | d | 4 | 355 (334–379) | 0,261 (0,223) | 0 |
| kız çocuk | e | 6 | 310 (268–360) | 0,170 (0,128) | 0 |
| kız çocuk | f | 6 | 461 (410–491) | 0,218 (0,170) | 0 |
| kız çocuk | g | 6 | 310 (277–413) | 0,149 (0,085) | 1 |
| kız çocuk | h | 6 | 318 (262–383) | 0,139 (0,064) | 2 |
| küçük erkek | a | 4 | 425 (413–488) | 0,261 (0,170) | 0 |
| küçük erkek | b | 4 | 482 (400–520) | 0,282 (0,202) | 0 |
| küçük erkek | c | 4 | 328 (324–392) | 0,229 (0,128) | 0 |
| küçük erkek | d | 4 | 336 (219–413) | 0,096 (0,064) | 2 |
| küçük erkek | e | 6 | 321 (274–383) | 0,128 (0,085) | 1 |
| küçük erkek | f | 6 | 312 (263–372) | 0,160 (0,064) | 2 |
| küçük erkek | g | 6 | 311 (271–364) | 0,170 (0,117) | 0 |
| küçük erkek | h | 6 | 185 (81–332) | 0,106 (0,096) | 0 |
| küçük kız | a | 4 | 431 (364–555) | 0,292 (0,138) | 0 |
| küçük kız | b | 4 | 480 (336–533) | 0,479 (0,191) | 0 |
| küçük kız | c | 4 | 362 (322–418) | 0,298 (0,255) | 0 |
| küçük kız | d | 10 | 352 (263–545) | 0,149 (0,032) | 2 |
| küçük kız | e | 6 | 315 (282–366) | 0,197 (0,160) | 0 |
| küçük kız | f | 6 | 336 (272–399) | 0,180 (0,117) | 0 |
| küçük kız | g | 6 | 327 (311–392) | 0,256 (0,181) | 0 |
| küçük kız | h | 12 | 293 (218–458) | 0,133 (0,064) | 5 |

Bütün adayların tek tek ölçümü: `tt-gpu:/data/editor/ses-havuzu/cocuk/sec.md` ve `olcum.json`.

## Dinlemeye giden adaylar

Seçim: eşiği geçenler, önce hedef bant içi, sonra hedef perdeye (7–10 yaş erkek 265, kız 275; 4–6 yaş erkek 300, kız
310 Hz) yakınlık; ilk üç, önce her tariften biri. Dosyalar `tt-gpu:/data/editor/ses-havuzu/cocuk/aday/<ses>-<sıra>.wav`
(`liste.json` sha256 ile).

| Aday | Tarif | Tohum | f0 (Hz) | Sesli oranı | cer | Süre (sn) |
|---|---|---|---|---|---|---|
| cocuk-erkek-1 | f | 131 | 275,7 | 0,646 | 0,064 | 7,3 |
| cocuk-erkek-2 | h | 89 | 248,5 | 0,728 | 0,085 | 9,2 |
| cocuk-erkek-3 | f | 23 | 314,9 | 0,884 | 0,096 | 8,1 |
| cocuk-kiz-1 | h | 11 | 261,7 | 0,873 | 0,064 | 9,9 |
| cocuk-kiz-2 | g | 131 | 316,7 | 0,907 | 0,085 | 9,0 |
| cocuk-kiz-3 | h | 131 | 316,7 | 0,881 | 0,085 | 9,9 |
| kucuk-erkek-1 | f | 131 | 305,9 | 0,870 | 0,074 | 10,8 |
| kucuk-erkek-2 | e | 23 | 288,7 | 0,925 | 0,085 | 8,5 |
| kucuk-erkek-3 | d | 23 | 277,3 | 0,813 | 0,064 | 8,0 |
| kucuk-kiz-1 | h | 131 | 295,5 | 0,845 | 0,074 | 9,1 |
| kucuk-kiz-2 | h | 401 | 290,4 | 0,850 | 0,064 | 8,2 |
| kucuk-kiz-3 | d | 11 | 359,6 | 0,914 | 0,096 | 8,8 |

Ek dinlenebilecek: küçük kız d/613 (`ham/kucuk-kiz/d-s613.wav`) 263,2 Hz, cer 0,032 — bütün setin en düşük harf hatası;
bandın alt sınırının (265) 2 Hz altında kaldığı için listeye girmedi.

## Kod (onay bekliyor)

- `voices_zeki.CHILD_VOICES`: dört ses, grup `karakter`, tarif = ilk sıradaki adayın tarifi. `child_state(PINNED)`
  sabit kaydı olanı kataloğa (`VOICES`) koyar, olmayanı `PENDING`'e ve `ALIASES`'e yazar: `cocuk-*` → genç ses,
  `kucuk-*` → aynı cinsten büyük çocuk (o da bekliyorsa genç ses). `cocuk-kiz`/`cocuk-erkek` eski kimliklerdi; onayla
  eski ayarlar da yeni çocuk sesine gider (o seslerle okunmuş sayfalar «güncel değil» olur).
- Neden «geçici olarak en iyi adayı sabitle» değil: sabit kayıt sesin kimliğidir ve imajla müşteriye gider; kullanıcı
  başka aday seçerse o sesle okunmuş bütün sayfalar «güncel değil» olurdu. Bekleyen ses bugünkü davranışı hiç
  değiştirmez; onay tek adımdır.
- `film/cast.py` `CANDIDATES`: çocuk karakterde sıra çocuk → küçük çocuk → genç → masal sesi. Onay bekleyen kimlik
  genç sese çevrilip tek kez sayılır (bugünkü dağılım aynen). Görünüş/rol okul öncesi yaşı söylüyorsa küçük çocuk sesi
  öne alınır.
- `narration.guess_voice`: «girl/boy» tarifi çocuk sesine, okul öncesini açıkça söyleyen tarif («toddler»,
  «kindergarten», «preschool», «tiny», «5-year-old») küçük çocuk sesine; «little/young/small» yaş söylemez, küçük
  sayılmaz.

### Onay adımı (kullanıcı seçince)

1. Seçilen aday `apps/editor/src/editor/production/sesler/zeki/<ses>.wav` olarak depoya konur.
2. `voices_zeki.PINNED`'e `"<ses>": _p("<ses>", CHILD_TEXT, "<sha256>")` (sha256 `aday/liste.json`'da) eklenir.
3. Seçilen aday ilk sıradaki değilse `CHILD_VOICES`'teki tarif o adayın tarifiyle değiştirilir.
4. Testler: `test_voices.py::test_catalog_voices_use_packaged_reference` kaydı ve süresini (5–16 sn) denetler.

(Yukarıdaki onay adımı 1. yönteme aittir; 2. yöntemde metin `method.metin`, kayıt `aday2/`'den — aşağıda.)

---

# 2. yöntem: tını dönüştürme + klon (2026-10-07)

Kullanıcı 1. yöntemin adaylarını dinledi: «daha iyilerini üret». Seçimi sonra ölçüme bıraktı («sen seç, en iyisi
olsun»).

## Yöntem

Çocuk sesi = yüksek F0 + kısa ses yolu (formantlar ~%15–25 yukarı). Ses modele tarif ettirilmez, temiz okuyan bir
kayıttan sinyal işlemeyle yapılır. Betik `apps/editor/deploy/ses/cocuk_donustur.py`; çıktı
`tt-gpu:/data/editor/ses-havuzu/cocuk/v2/` ve `aday2/`.

1. **Dönüşüm (CPU, ağsız geçici kap `editor-voice:5` + parselmouth 0.4.7 + pyworld 0.3.5):** 19 kaynak kayıt —
   katalogdan en temiz okuyan 6 ses (genç/roman/masal/gelişim kadın, genç/gelişim erkek) ve 1. yöntemin 13 adayı. Kaynak
   kayıtların hepsi modelimizin ürettiği seslerdir; gerçek kişi kaydı yok. Izgara: Praat «Change gender» formant oranı
   {1,12; 1,18; 1,24; 1,30} × hedef ortanca perde {250…330 Hz} × perde aralığı {1,0; 1,2; 1,4}; WORLD aynı formant ve perde
   ızgarası, aralık 1,2 (F0 log düzleminde, zarf ve aperiyodiklik frekans ekseninde sıkıştırılır). 1.520 dönüşüm.
   Kız çocuğu yalnız kadın kaynaktan, erkek çocuğu iki kaynaktan.
2. **Klon (GPU, yalnız gateway üzerinden book-voice, tek toplu çalıştırma 263 sn):** ses başına 8 dönüştürülmüş kayıt,
   sayfa okumasıyla aynı düzen (ref_audio + ref_text, tam klon, tohum yok), iki metin: ölçüm cümlesi ve 60 kelimelik
   paragraf (bu iş için yazıldı: kar yağan sabah, kardan adam). 64 klon.
3. **Ölçüm (CPU):** perde (pyin), harf hatası iki tanıyıcıyla — ses servisinin hizalayıcısı (wav2vec2 Türkçe) ve
   Whisper large-v3-turbo (MIT) —, yaş/cinsiyet (audeering wav2vec2-large-robust-24-ft-age-gender: kadın/erkek/çocuk
   olasılığı + yaş; **lisansı CC BY-NC-SA 4.0**, yalnız ölçüm aracı olarak kullanıldı, ürüne/imaja girmez), konuşmacı
   benzerliği (microsoft wavlm-base-plus-sv, MIT), bozulma belirtisi (paragrafta > 7 yarım ton perde sıçraması,
   ortancanın 15 dB üstünde enerji).
4. **Seçim (ana oturumun ölçütü):** eleme harf hatası ≤ 0,10 (iki metnin ortalaması ve paragraf ayrı); puan =
   0,45·çocuk olasılığı + 0,25·(1 − |yaş − hedef|/5) + 0,20·(1 − cer/0,10) + 0,10·paragrafta klon↔referans benzerliği,
   bozulmada −0,10. Hedef yaş çocuk 8,5, küçük 5. Çocuk olasılığı ve yaş iki klonun ortalaması (sayfayı klon okur).
   Önerilen: elenmeyenlerden, öteki önerilenlerle paragraf klonu benzerliği 0,85'i aşmayan en yüksek puanlı (bütün ses
   sıraları denenir); ayrışan yoksa en yüksek puanlı + uyarı.

## Bulgular

1. **Yaş modeli katalogu ve 1. yöntemi doğru okuyor.** Katalogdaki 21 sesin hepsi yetişkin (çocuk olasılığı ≤ 0,001, yaş
   30–67; kadın/erkek olasılığı ≥ 0,98). 1. yöntemin dinlemeye giden 12 adayından 8'i yetişkin çıktı (çocuk olasılığı < 0,2) — ör. `cocuk-erkek-1`
   36 yaşında erkek (0,996), `cocuk-kiz-1` 32 yaşında kadın; kullanıcının «daha iyi» istemesiyle tutarlı. 172 adayın
   ortanca çocuk olasılığı 0,18, yaşı 22.
2. **Dönüşümde çocuksuluk formant oranıyla geliyor.** Katalog kaynağında formant 1,12 → çocuk olasılığı ortanca 0,003,
   yaş 29; 1,30 → 0,43, yaş 20; en çocuksu dönüşümler 0,98–0,996 (yaş 7–11). 1. yöntem adaylarından 1,12 bile 0,99+.
   Perde tek başına yetmiyor (1,12 / 330 Hz yine yetişkin kadın).
3. **Hizalayıcının harf hatası çocuksu seste tanıyıcı yanlılığı; Whisper ikinci görüş.** Çocuksu dönüşümlerde hizalayıcı
   0,29–0,54 verdi; aynı kayıtları Whisper 0,000–0,043 okudu. Klonların hepsinde Whisper harf hatası 0–0,011 (ortanca 0),
   katalogda 0–0,007, genç seslerin çocuk cümlesinde 0–0,043. Hizalayıcı yetişkin konuşmasıyla eğitilmiş; klonda telaffuz
   modelden gelir. Hizalayıcı ölçütüyle 32 klondan yalnız 2'si elemeyi geçiyor ve ikisi de yetişkin (çocuk 0,06–0,09, yaş
   21–29). **Elemede Whisper harf hatası kullanıldı** (`CER_KAYNAK=cer_w`); iki puan tabloda yan yana. Not: Whisper'ın dil
   modeli bozuk telaffuzu tahminle düzeltebilir; harf hatası 0 «kusursuz telaffuz» demek değildir.
4. **Klon dönüşüm tınısını tutuyor.** Paragraf klonu ↔ dönüştürülmüş referans benzerliği 0,94–0,996; klon ↔ çevrilmemiş
   kaynak 0,42–0,94 (formant oranı büyüdükçe düşüyor). Klonların çocuk olasılığı referansınkiyle aynı bantta.
5. **Konuşmacı benzerliği bu seslerde ayırt etmiyor.** Farklı kaynaklı aday çiftleri arasında benzerlik en az 0,801,
   ortanca 0,949, en çok 0,990 (441 çift). 0,85 eşiği bu ölçekte «aynı kişi» anlamına gelmiyor; önerilen dört sesten dört
   çift > 0,85 (en yükseği kız çocuk ↔ küçük kız 0,989, kaynakları farklı tohumdan iki kız sesi). Ayrışma kulakla
   doğrulanmalı.
6. **Bozulma belirtisi yok.** 32 paragrafta perde sıçraması 0; enerji patlaması en çok %0,86 (eşik %1).
7. Aynı kayıt iki seste: `kucuk-erkek-2` ve `kucuk-kiz-3` aynı dönüşüm (genç kadın, WORLD 1,30 / 330 Hz) — ikisi
   birlikte seçilmemeli.

## Önerilen ve dinlemedeki adaylar (Whisper elemesi)

Dosyalar `tt-gpu:/data/editor/ses-havuzu/cocuk/aday2/<aday>-{referans,klon-cumle,klon-paragraf}.wav`; karşılaştırma için
1. yöntemin ilk adayı `<ses>-0-onceki.wav`; tam liste `aday2/liste.json` ve `aday2/sec.md`. Hücreler: f0 / harf hatası
(hizalayıcı·Whisper) / çocuk olasılığı / yaş.

| Aday | Puan W (h) | Yöntem | Referans | Klon cümle | Klon paragraf | Benzerlik par↔ref / ↔kaynak |
|---|---|---|---|---|---|---|
| **cocuk-erkek-1 önerilen** | 0,983 (0,783×) | WORLD, genç kadın, 1,30 / 290 / 1,2 | 295,5 / 0,379·0,007 / 0,99 / 10,2 | 329,7 / 0,287·0 / 0,99 / 9,5 | 313,0 / 0,414·0 / 1,00 / 7,0 | 0,992 / 0,556 |
| cocuk-erkek-2 | 0,949 (0,749×) | WORLD, gelişim kadın, 1,30 / 290 / 1,2 | 293,8 / 0,268·0,007 / 0,97 / 12,8 | 305,9 / 0,298·0 / 0,98 / 10,9 | 331,7 / 0,32·0 / 1,00 / 7,9 | 0,984 / 0,584 |
| cocuk-erkek-3 | 0,934 (0,734×) | WORLD, 1. yöntem küçük erkek-1, 1,12 / 270 / 1,2 | 272,5 / 0,309·0 / 1,00 / 4,8 | 289,6 / 0,266·0 / 0,99 / 8,8 | 292,1 / 0,304·0 / 0,99 / 10,5 | 0,943 / 0,772 |
| **cocuk-kiz-1 önerilen** | 0,992 (0,791×) | WORLD, 1. yöntem kız-2, 1,30 / 290 / 1,2 | 295,5 / 0,394·0,043 / 0,99 / 8,6 | 283,8 / 0,372·0 / 0,99 / 9,9 | 285,4 / 0,542·0 / 1,00 / 7,1 | 0,944 / 0,535 |
| cocuk-kiz-2 | 0,944 (0,744×) | Praat, 1. yöntem küçük kız d/613, 1,30 / 250 / 1,2 | 254,3 / 0,383·0 / 0,99 / 7,3 | 242,8 / 0,426·0 / 0,98 / 9,0 | 266,3 / 0,461·0 / 1,00 / 6,0 | 0,984 / 0,576 |
| cocuk-kiz-3 | 0,914 (0,714×) | Praat, 1. yöntem kız-3, 1,12 / 250 / 1,0 | 252,8 / 0,149·0 / 1,00 / 7,4 | 249,9 / 0,138·0 / 1,00 / 4,9 | 249,9 / 0,172·0 / 1,00 / 8,8 | 0,970 / 0,809 |
| **kucuk-erkek-1 önerilen** | 0,928 (0,728×) | Praat, 1. yöntem küçük erkek-1, 1,12 / 330 / 1,0 | 337,5 / 0,106·0 / 1,00 / 5,1 | 333,6 / 0,128·0 / 1,00 / 6,2 | 341,4 / 0,188·0 / 1,00 / 6,6 | 0,989 / 0,942 |
| kucuk-erkek-2 | 0,897 (0,697×) | WORLD, genç kadın, 1,30 / 330 / 1,2 | 335,5 / 0,379·0,007 / 1,00 / 7,2 | 361,7 / 0,309·0 / 0,99 / 7,8 | 357,5 / 0,436·0 / 1,00 / 6,2 | 0,991 / 0,562 |
| kucuk-erkek-3 | 0,887 (0,687×) | WORLD, 1. yöntem küçük erkek-1, 1,18 / 330 / 1,2 | 333,6 / 0,362·0 / 1,00 / 5,1 | 343,4 / 0,351·0 / 1,00 / 6,9 | 368,0 / 0,489·0 / 1,00 / 7,4 | 0,961 / 0,739 |
| **kucuk-kiz-1 önerilen** | 0,988 (0,788×) | WORLD, 1. yöntem kız-3, 1,30 / 310 / 1,2 | 317,6 / 0,394·0 / 1,00 / 5,8 | 316,7 / 0,404·0 / 1,00 / 4,7 | 313,0 / 0,48·0 / 1,00 / 5,1 | 0,941 / 0,586 |
| kucuk-kiz-2 | 0,914 (0,717×) | Praat, 1. yöntem kız-3, 1,24 / 290 / 1,0 | 293,8 / 0,309·0 / 1,00 / 5,0 | 293,8 / 0,351·0 / 0,99 / 6,7 | 292,1 / 0,351·0,003 / 1,00 / 6,4 | 0,957 / 0,641 |
| kucuk-kiz-3 | 0,885 (0,685×) | WORLD, genç kadın, 1,30 / 330 / 1,2 | 335,5 / 0,379·0,007 / 1,00 / 7,2 | 365,9 / 0,351·0 / 0,99 / 8,6 | 339,4 / 0,414·0 / 1,00 / 5,9 | 0,993 / 0,566 |

Önerilen dört kayıt (sabitlenmedi; referanslar 48 kHz tek kanal, 9,0–11,8 sn):

| Ses | Dosya | Metin | sha256 |
|---|---|---|---|
| cocuk-erkek | `aday2/cocuk-erkek-1-referans.wav` | READER_TEXT | `14c66310d7d561ae7e2359bfb2d683cdaee334dbcc9d89819b0683d6bd9534f6` |
| cocuk-kiz | `aday2/cocuk-kiz-1-referans.wav` | CHILD_TEXT | `aed6240f456e900de6c8a1cef111a92a4087c2bdefa4a11ffb2d1ddb5940cf3a` |
| kucuk-erkek | `aday2/kucuk-erkek-1-referans.wav` | CHILD_TEXT | `4afba5879027735174b8ce831169ad90fa574741fadf33f75da082aa07c6e54a` |
| kucuk-kiz | `aday2/kucuk-kiz-1-referans.wav` | CHILD_TEXT | `ff164e52bb9fa1020c713ca930eed64c73b0c2b58ecb57dcb4dfa941503db41f` |

Hazır PINNED satırları (ana oturum doğrulayınca, wav `sesler/zeki/<ses>.wav` olarak konup):

```python
    "cocuk-erkek": _p("cocuk-erkek", READER_TEXT, "14c66310d7d561ae7e2359bfb2d683cdaee334dbcc9d89819b0683d6bd9534f6"),
    "cocuk-kiz": _p("cocuk-kiz", CHILD_TEXT, "aed6240f456e900de6c8a1cef111a92a4087c2bdefa4a11ffb2d1ddb5940cf3a"),
    "kucuk-erkek": _p("kucuk-erkek", CHILD_TEXT, "4afba5879027735174b8ce831169ad90fa574741fadf33f75da082aa07c6e54a"),
    "kucuk-kiz": _p("kucuk-kiz", CHILD_TEXT, "ff164e52bb9fa1020c713ca930eed64c73b0c2b58ecb57dcb4dfa941503db41f"),
```

`CHILD_VOICES[*].method` bu dört kaydın yöntemini taşır; başka aday seçilirse o adayın `liste.json`'daki `yontem`'i yazılır.

## Doğrulanamayanlar

- Erkek/kız ayrımı ölçülmedi: yaş modelinin «çocuk» sınıfında cinsiyet yok. Erkek çocuk önerisi kadın kaynaktan
  (genç kadın, formant 1,30); erkek mi kız mı duyulduğu kulakla doğrulanmalı.
- Konuşmacı benzerliği modeli bu seslerde ayırt edici değil (bulgu 5); dört sesin birbirinden ayrışması ölçülemedi.
- Whisper'ın 0 harf hatası dil modeli düzeltmesini içerebilir; telaffuz netliği dinlenmeli.
- Dönüştürülmüş referans tam klonda sayfa okumasına (sözcük zamanı, uzun bölüm) sokulmadı; yalnız iki metin okundu.
