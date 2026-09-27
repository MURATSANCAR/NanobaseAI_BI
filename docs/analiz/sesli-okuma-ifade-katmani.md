# Sesli okuma — ifade katmanı (2026-09-27)

Kullanıcı kararı: «Zeki AI metni önceden okuyup her cümleyi işaretler: heyecan, merak, korku, neşe, fısıltı, üzüntü, ya
da vurgulanacak kelime. Ses bu işaretle o cümleyi farklı tonda, hızda ve duraklamayla okur. Editör işareti ekranda
cümle cümle değiştirebilir.» Kod: `apps/editor/src/editor/production/expression.py` (+ `api_expression.py`), ses servisi
`apps/editor/images/voice/server.py`, ekran `src/canvas/editorial/studio/narration/ExpressionEditor.tsx`.

Önce ölçüldü, sonra ürüne yalnız işe yarayan yol kondu. Bütün ölçümler TT GPU'da, GPU 1'de ana modelin yanında geçici
bir ses kabında (`editor-voice:1` + değiştirilmiş `server.py`, çalışan hiçbir kaba dokunulmadı), deneme işinin
(`2026092716271423aee2`, çocuk kitabı) kopyasında. Ölçüler: ortanca perde (F0, pYIN), perde aralığı (p90−p10 yarım
ton), konuşma hızı (hece/sn, etkin konuşmada), enerji (dBFS, etkin konuşmada), sesli kare oranı (fısıltı), anlaşılırlık
(ses geri tanındı — hizalayıcının Türkçe CTC modeli açgözlü çözümle — beklenen okunuşla harf hatası). Örnek sesler ve
ham ölçüler oturum karalama klasöründe (`ifade-deneme/`, `canli-sesler/`; depoya girmez).

## 1. Model talimatı nerede dinliyor?

Kitap bugün **tam klonla** okunuyor: referans sesi + referans cümlesinin metni (VoxCPM2 devam kipi, en tutarlı ses).
Talimat modele metnin başında «(…)» olarak verilir.

Matris: 3 nötr cümle × 9 ifade × 2 tohum, varsayılan kadın anlatıcı (referans 203 Hz, 6,3 yt):

| kip | ifade | F0 Hz | aralık yt | hece/sn | enerji dB | harf hatası |
|---|---|---|---|---|---|---|
| tam klon | nötr | 191 | 5,3 | 7,0 | −22,9 | %0,0 |
| tam klon | heyecan / fısıltı / üzüntü / öfke (talimatla) | 201–207 | 5,8–6,6 | **3,1–4,5** | ≈ | **%45–111** |
| referans-yalnız | nötr (talimatsız) | **222** | **10,1** | 6,6 | −21,4 | %1,3 |
| referans-yalnız | heyecan | 245 | 9,6 | 6,6 | −20,1 | %2,6 |
| referans-yalnız | fısıltı | 207 | 3,6 | 6,5 | −25,8 | %3,5 |
| referans-yalnız | üzüntü | 209 | 7,2 | 6,3 | −23,3 | %3,5 |
| referans-yalnız | öfke | **340** | 11,7 | 6,6 | −17,7 | %4,8 |

- **Tam klonda talimat sesli okunuyor** (tanıyıcı «enen fasazin duvord…» duyuyor; süre iki katı): bu yol kullanılamaz.
- **Referans-yalnız klonda** talimat dinleniyor (yön doğru: heyecan/neşe/şaşkınlık perde +%10–16 enerji +1–2 dB;
  fısıltı ve üzüntü −2…−4 dB, düz perde) ama **ses kimliği kayıyor**: talimatsız bile perde +%16 ve aralık iki kat;
  «keeping the same voice» eklense de +%13–43 (ikinci tur); öfke +%70.
- **Hız talimatla değişmiyor** (±%6): hız üretimden sonra perdeyi koruyan zaman esnetmeyle (rubberband) verilir.

## 2. Sayfa denemesi (a/b/c/d)

7. ve 5. sayfa (21 parça), elle işaretlenmiş ifadeler. Dosyalar `ifade-deneme/{a,b,b2,c,d}-sayfa{5,7}.mp3`.

| hâl | tanım | işaretli F0 Hz (nötr) | işaretli hece/sn (nötr) | harf hatası |
|---|---|---|---|---|
| a | bugünkü hâl (tam klon, talimatsız) | 199–206 (184–193) | 5,8–6,2 (6,4–7,1) | %4,1–4,5 |
| b | işaretli parça referans-yalnız + talimat | **262–438** (184–195) | 4,0–4,8 | **%10,4–11,8** |
| b2 | bütün parçalar referans-yalnız | 262–437 | 4,0 | %13,6–19,9 |
| c | b + hız/duraklama | 283–437 | 4,1–5,1 | %10,4–15,4 |
| d | canlı tarifli referans + b | 385–424 (324–370) | 5,0–5,9 | %21,4–21,7 |

- Kısa ünlem parçalarında («Yaşasın!», «Vak vak!», «diye güldüler.») talimat sesi **çocuk/cırlak** perdeye taşıyor
  (474–522 Hz), kelimeleri yutuyor («Aslan çok sevindi» → «en çok sevindek»).
- Fısıltı uzun cümlede gerçek: enerji −15 dB, sesli oranı 0,89 → 0,68, harf hatası **0/37**; ama iki kat yavaş.
- (d) «lively expressive storyteller, wide pitch range» tarifi 383 Hz'lik çizgi film sesi verdi, harf hatası %21:
  canlılık tarifle istenince perde sınırı konmalı (bkz. 6).

## 3. Vurgu

3 cümle × 3 tohum, hedef kelimenin öteki kelimelere göre farkı:

| yöntem | Δenerji dB | Δperde yt | harf hatası |
|---|---|---|---|
| vurgu yok (taban) | +1,1 | +0,5 | %0,0 |
| talimat «emphasizing the word …» (referans-yalnız) | +0,8 | −0,4 | %2,6 |
| büyük harf (tam klon) | +2,5 | −0,6 | %1,8 |
| **kelimeden önce kısa durak «...» (tam klon)** | **+3,0** | **+1,6** | **%0,3** |

Ürün: vurgulanan kelimeden önce okunuş metnine «...» (hizalanan kelimeler değişmez; kelime parçanın ilk kelimesiyse ya
da önünde zaten noktalama varsa eklenmez).

## 4. İfade örneği (üçüncü yol)

Aynı sesin referans cümlesi bir kez talimatla (referans-yalnız) okunur; üç tohum, servisin `measure`'ıyla ölçülür,
hedefe en yakın ve sınır içindeki aday seçilir (harf hatası ≤ %6, perde kayması ±%30). Cümle **tam klonla** üretilir:
kimlik referanstan, ton örnekten (`voice.prompt_audio`, devam kipi), talimat metne girmez. Yayınevi düzeyinde bir kez
(`_ses/ifade/<ses>/<ifade>.wav|json`), referans ya da talimat değişince yenilenir.

İkinci tur (6 cümle × 2 tohum, talimatsız tam klona göre fark; uzun = 6–8 kelimelik nötr cümle):

| ifade | yol | uzun cümle ΔF0 / Δenerji / Δhız | uzun harf hatası | kısa ünlem ΔF0 (en çok) | kısa harf hatası (taban %2,4) |
|---|---|---|---|---|---|
| heyecan | talimat (referans-yalnız) | +%23 / +2,4 dB / −%4 | %0,9 | +%43 (+69) | %5,6 |
| heyecan | ifade örneği | +%15 / −0,8 / **+%11** | %0,9 | +%42 (+124) | %4,8 |
| neşe | ifade örneği | +%12 / +1,6 / +%3 | %0,0 | +%49 (+122) | %8,7 |
| merak | ifade örneği | +%12 / +0,5 / +%3 | %0,4 | +%12 (+45) | %2,4 |
| şaşkınlık | ifade örneği | +%15 / +2,0 / +%7 | %0,4 | +%19 (+82) | %4,8 |
| **üzüntü** | ifade örneği | −%1 / **−9,0 dB** / **−%22** | %0,0 | −%13 / −11 dB | %2,4 |
| fısıltı | talimat (referans-yalnız) | +%7 / −3,1 / −%7 | %3,5 | +%31 | %13,5 |

Uzun nötr cümlede ifade örneği ölçülü ve kimliği koruyor; kısa ünlemde bütün yollar dağılıyor. Gerçek sayfada (uçtan
uca, Zeki AI işaretleriyle) yükselen tonlar ünlemli 7 kelimelik cümlede de aştı: canlı erkek seslerde neşe örneği
+%48–65 perde, harf hatası %10–12 (n = 2 cümle × 3 ses).

## 5. Ürün kararı ve etiket → üretim tablosu

Ton yalnız ölçümde sesi bozmadan çalışan iki ifadede; yükselen tonlar hız ve duraklamayla. Kısa parçada (5 kelimeden
az) ton hiç verilmez (hız/duraklama; tonu metnin kendi noktalaması taşır). Tablo `expression.TABLE`:

| ifade | ton | hız | önce durak | cümle sonu durak |
|---|---|---|---|---|
| nötr | — | 1,00 | — | ×1,0 |
| heyecan | — | 1,08 | — | ×0,75 |
| merak | — | 0,96 | 150 ms | ×1,35 |
| korku | — | 0,94 | 250 ms | ×1,35 |
| neşe | — | 1,04 | — | ×0,9 |
| fısıltı | talimat «whispering, very soft and breathy» (referans-yalnız) | 1,15 | 300 ms | ×1,4 |
| üzüntü | ifade örneği «sad, slow, low and soft voice» (tam klon), hedef perde −%3 enerji −5 dB | 1,00 | 200 ms | ×1,5 |
| öfke | — | 1,05 | — | ×0,85 |
| şaşkınlık | — | 1,00 | 250 ms | ×1,2 |
| vurgu | kelimeden önce «...» | | | |

Cümle sonu durak `narration.PAUSE`'un (noktalamaya göre) çarpanıdır.

**Uçtan uca doğrulama** (ürün kodu: `narration.narrate_page` → kanca → servis; 7 ses × 2 sayfa × ifade açık/kapalı):

| ifade | cümle | Δenerji dB (açık−kapalı) | Δhız | sesli oranı | harf hatası açık / kapalı |
|---|---|---|---|---|---|
| üzüntü (ifade örneği) | 14 (2 cümle × 7 ses) | −3…−10 (ortanca −5,3; iki erkek seste ≈0) | çoğunda −%5…−27 | ≈ | 15 / 15 (aynı) |
| fısıltı (talimat) | 7 (1 cümle × 7 ses) | −3,9…−13,2 | −%26…+4 | erkek seslerde −0,36…−0,75 (gerçek fısıltı) | 13/259 (%5,0) / 3/259 (%1,2) |
| nötr cümleler | 8 × 7 | ±1 | ±%6 | ≈ | ≈ |

Aynı girdinin iki üretimi arasında cümle başına perde ±%10–20 oynuyor (sayfa seslendirmesi tohum sabitlemiyor): tek
cümlelik perde farkı gürültü düzeyinde; enerji, hız ve sesli oranı farkları bunun üstünde.

## 6. Canlı masal anlatıcısı (yeni ses grubu)

`production/voices_lively.py`, narration.py'ye tek satırla eklenir; ekranda «Çocuk kitabı anlatıcısı»ndan sonra. 12
tarif × 2 tohum; ölçü referans cümlesinde (82 harf):

| aday | tohum | F0 Hz | aralık yt | harf hatası | karar |
|---|---|---|---|---|---|
| kadın masalcı (a) | 25 / 26 | 233 / 305 | 4,6 / 7,5 | 4 / 3 | ikinci tohum 300 Hz üstü |
| **kadın masalcı (b)** | **25** / 26 | **259** / 277 | **7,3** / 9,4 | 2 / 3 | seçildi: `canli-kadin-masalci` |
| kadın tiyatro (a) | 25 / 26 | 262 / 306 | 7,7 / 7,6 | 8 / 5 | elendi (harf hatası %10, 300 Hz üstü) |
| **kadın tiyatro (b) alto** | **25** / 26 | **207** / 194 | **8,1** / 6,5 | 3 / 3 | seçildi: `canli-kadin-sahne` |
| kadın nine (a) | 25 / 26 | 263 / 302 | 8,6 / 10,8 | 5 / 5 | |
| **kadın nine (b)** | 25 / **26** | 228 / **265** | 6,2 / **8,3** | 2 / 4 | seçildi: `canli-kadin-nine` |
| **erkek masalcı (a)** | **25** / 26 | **103** / 118 | **8,9** / 8,1 | 2 / 2 | seçildi: `canli-erkek-masalci` |
| erkek masalcı (b) | 25 / 26 | 72 / 95 | 6,8 / 7,2 | 3 / 2 | |
| erkek «theatrical … baritone» | 25 / 26 | **193 / 168** | 8,0 / 8,6 | 5 / 3 | **elendi (erkek > 150 Hz)** |
| **erkek radyo oyuncusu (bas-bariton)** | 25 / **26** | 80 / **120** | 8,6 / **11,5** | 3 / 5 | seçildi: `canli-erkek-radyo` |
| **erkek dede (a)** | **25** / 26 | **105** / 109 | **8,6** / 8,0 | 3 / 3 | seçildi: `canli-erkek-dede` |
| erkek dede (b) | 25 / 26 | 73 / 94 | 4,9 / 6,6 | 5 / 3 | |

Karşılaştırma: varsayılan kadın anlatıcı 203 Hz, 6,3 yt. Seçilenlerin **dinlenen referansı sabitlendi**:
`/data/editor/storage/production/_ses/sesler/canli-*.wav|json` (tarif metniyle; `narration.voice_ref` tarif aynıysa
kaydı kullanır, yeniden üretmez). md5: kadın-masalcı `13507deb…`, kadın-sahne `46fa2f0a…`, kadın-nine `59a26446…`,
erkek-masalcı `f5009933…`, erkek-radyo `caf77f69…`, erkek-dede `7643bb91…`. Her aday 5. ve 7. sayfayı ifade katmanı
açık ve kapalı okudu (`canli-sesler/<ses>/sayfa{5,7}-ifade-{acik,kapali}.mp3`). Varsayılan anlatıcı değişmedi.

## 7. Zeki AI önerisi

Ana model, kapalı küme: cümle başına tek harf (A–I) + harf olasılıkları (vLLM structured choice + logprobs), seçenek
sırası düz ve ters iki okuma, olasılıklar ortalanır; en olası ifade %50'nin altında ya da nötrün önünde 0,15'ten az
farkla öndeyse nötr. Vurgu: üç bağımsız okuma, en az ikisinde geçen ve cümlede birebir bulunan kelime. Deneme işinde
(5. sayfa 9 cümle 19 sn, 7. sayfa 12 cümle 46 sn): «Haydi Aslan, parka gidelim!» neşe %89, «Yaşasın!» heyecan %67,
«Parka gidiyoruz!» heyecan %80, «Ne güzel fikir!» neşe %91; anlatım ve «dedi» cümleleri nötr %83–99; «diye zıpladı»
heyecan %49 → eşik altı, nötr; «Eve dönme zamanı» nötr %57 / üzüntü %22 → nötr.

## Açık konular

- Yükselen tonlar (heyecan, neşe, şaşkınlık, merak, korku, öfke) yalnız hız ve duraklamayla; kısa ünlemi komşu
  cümlesiyle tek parça üretmek (tonu cümle içinde taşımak) sonraki deneme — `narration.pieces` bölmesini değiştirir.
- Ses servisi değişti (`style`, `rate`, `pause_before_ms`, `clone`, `cfg`, `voice.prompt_audio`, `measure`): imaj
  `editor-voice:2` GPU'da derlendi (`sha256:b0cf45d34e28…`, `server.py` md5 `2e513b88…`, ölçümdeki geçici kapla aynı
  dosya); `models.yaml` ve `editorctl` :2'yi gösterir. Gateway yeni imajla kurulana kadar eski servis bu alanları
  sessizce yok sayar: vurgu duraklaması ve cümle sonu duraklamaları yine çalışır, ton/hız/önceki durak çalışmaz.
- Sayfa seslendirmesi tohum sabitlemiyor: aynı sayfanın iki üretimi arasında cümle perdesi ±%10–20 oynuyor.
