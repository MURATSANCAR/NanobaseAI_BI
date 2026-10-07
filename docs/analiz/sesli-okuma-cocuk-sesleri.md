# Sesli okuma: çizgi film çocuk sesleri (2026-10-07)

Neden: ses kataloğunda (`voices_zeki.py`) çocuk sesi yoktu; kitaptan çizgi filmde çocuk karakterler (ilk deneme Timaş'ın
«Levent» serisi, ilkokul çağında bir erkek çocuk) genç sesle konuşuyordu. Katalogdaki eski küçük çocuk sesleri
2026-10-03'te kullanıcı tarafından «çok kötü» bulunup kaldırılmıştı (8 yaş tarifi kalitede tutmamıştı).

İstenen: «karakter» grubuna dört ses — erkek çocuk (7–10), kız çocuk (7–10), küçük erkek çocuk (4–6), küçük kız çocuk
(4–6).

**Durum: adaylar üretildi ve ölçüldü, kullanıcının dinleyip seçmesi bekleniyor.** Sesler kodda «onay bekliyor»
(`voices_zeki.CHILD_VOICES`, `PENDING`): katalogda görünmez, kimliği genç sese gider; çocuk karakteri bugünkü gibi okunur.

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
