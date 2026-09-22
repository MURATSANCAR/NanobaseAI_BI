# Mekân tutarlılığı (`setting`) — ÖLÇÜM BEKLİYOR

Durum (2026-09-22): kod yazıldı, saf parçalar sentetik testle doğrulandı
(`tests/test_setting.py`, 4 test). **Gerçek kitapta hiç koşmadı; okuyucu kesinliği ve eşikler
ölçülmedi.** Ölçülene kadar bulgular yalnız editör adayıdır.

## 1. Editör ne bakar

Aynı mekân kitap boyunca tutarlı tarif ediliyor mu: odanın/evin düzeni, kapı/pencere yönü, kat,
şehir/ülke; metnin «içeride / gece / yağmurlu» dediği sayfada resim tersini gösteriyor mu.

Çelişki OLMAYANLAR: aynı adla anılan iki farklı yer, metnin açıkladığı değişim (taşındılar,
eşyalar yer değiştirdi, ev yenilendi, başka odaya geçtiler), rüya/hayal/oyun, bir karakterin
yanılgısı, bakış açısına göre değişen tarif (sağ/sol).

## 2. Ölçülen ve ÖLÇÜLMEYEN

Figür kimliği gibi bir **mekân kimliği yok**: resimde «aynı oda» tanınmaz. Bu yüzden resim tarafında
yalnız metnin o sayfa için söylediği ve kapalı kümede sorulabilen üç özellik karşılaştırılır:

| aspect | metin değeri | resme soru | harf |
|---|---|---|---|
| `IC_DIS` | IC / DIS | sahne içeride mi dışarıda mı | I / D / B |
| `ISIK` | GUNDUZ / GECE | gündüz mü gece mi | G / K / B |
| `HAVA` | GUNESLI / YAGMURLU / KARLI | hava nasıl | G / Y / K / B |

**Resimden ölçülmeyenler (uydurulmaz, yalnız metin–metin):** oda/ev düzeni (`DUZEN`), kapı ve
pencere yönü (`KAPI_YONU`, `PENCERE_YONU`), kat (`KAT`), şehir/ülke (`KONUM`). Bunlar için resimde
tanınacak bir «aynı mekân» referansı yok; iki sayfanın resmini yan yana koyup «aynı oda mı, kapı
aynı yerde mi» diye sormak ölçülmemiş bir görsel kimlik varsayımı olurdu.

## 3. Akış

1. **Metin okuyucu** (`setting.read_facts`; director, parça başına 1 çağrı, düşünme kapalı,
   sıcaklık 0): `place`, `aspect` (kapalı küme), `value`, sayfa/paragraf/alıntı. Alıntı sayfada
   bulunmazsa kayıt yok. Görsel aspect'lerde değer kapalı kümeye çevrilir (Türkçe harfler
   sadeleştirilir: «gündüz» → GUNDUZ); küme dışı değer çift kurmaz.
2. **Metin–metin çift** (`pair_facts`, deterministik): aynı normalleştirilmiş mekân adı + aynı
   aspect + farklı değer, iki AYRI sayfada. Her değeri en erken sayfadaki bilgi temsil eder.
3. **Yargı** (iki sırada kapalı soru, `Llm.choose`, C/U/B): bulgu ancak
   `min(C_ileri, C_geri) ≥ SETTING_JUDGE_MIN`. Çift başına 2 çağrı.
4. **Metin–resim** (`visual_facts` + `ask_image`): görsel aspect'li metin bilgisi, sayfası resimliyse
   (`page_scan` satırı var), derin görsel modele sayfa görüntüsüyle tek kapalı soru; olasılık
   logprobs'tan. Metnin değerine **ters** bir değerin olasılığı ≥ `SETTING_IMAGE_MIN` → bulgu;
   «B = belli değil» bulgu değil. Sayfa+aspect başına 1 çağrı.
5. Her bulgu iki kanıt: metin–metin → iki sayfa+alıntı; metin–resim → sayfa+alıntı ve aynı sayfanın
   resmi (bbox tam sayfa `[0,0,1000,1000]`, `details.b.seen` resmin okunan değeri). Şiddet WARN
   (mekân tarifi kalıcı sayılmıyor; ölçümden sonra ERROR eşiği düşünülebilir). INFO satırı kapsamı
   ve ölçülmeyen kısmı bildirir.

## 4. Eşikler (ayardan; hepsi ölçülmedi)

| ad | env | varsayılan | anlamı |
|---|---|---|---|
| `setting_judge_min` | `EDITOR_SETTING_JUDGE_MIN` | 0.5 | iki sırada gereken «çelişki» olasılığı |
| `setting_image_min` | `EDITOR_SETTING_IMAGE_MIN` | 0.7 | resmin metne ters değer verme olasılığı |
| `setting_parallel` | `EDITOR_SETTING_PARALLEL` | 4 | eşzamanlı model çağrısı |

## 5. Model çağrısı sayısı

Metin okuyucu: parça başına 1 (director; 1–4). Yargı: metin–metin çift başına 2 (director).
Resim: görsel aspect'li metin bilgisi başına 1 (book-vision-deep). Sıra: director işleri önce,
görsel model sonra (iki model kartta birlikte durmaz; `check` içinde director yargıları görsel
sorulardan önce biter).

## 6. Yanlış alarm / kaçırma riskleri

1. Mekân adı tutarsız yazılırsa («oda» / «Ali'nin odası») çift kurulmaz → kaçırma. Okuyucuya
   «her yerde aynı ad» dendi; ölçümde ad dağılımına bakılır.
2. `IC_DIS`/`ISIK`/`HAVA` metin bilgisi o sayfanın sahnesi olmayabilir («dışarıda yağmur yağıyordu»
   içeriden söylenir) → resimle yanlış karşılaştırma. Ölçümde bu oran sayılır; yüksekse metin
   bilgisine «sahne o an» şartı için ayrı bir kapalı soru eklenir (açık karar).
3. Resimli çift sayfada (iki sayfa tek çizim) sayfa görüntüsü yarım sahne olabilir.
4. Gece sahnesinde iç mekân aydınlık çizilir; `ISIK` sorusunda «B = kapalı mekân» seçeneği var ama
   model gündüz diyebilir.

## 7. ÖLÇÜM BEKLİYOR — ölçüm planı (gerçek kitap, GPU sunucusu)

```sh
ssh tt-gpu 'docker exec -i editor-mcp python -m editor.proofing <generation_id> --only setting --dry' > setting-<kitap>.json
ssh tt-gpu 'docker exec -i editor-mcp python -m editor.proofing <generation_id> --only setting'
```

Ölçülecekler (altı kitap):
1. **Okuyucu kesinliği:** `stats.reader.facts` tümü gözle: mekân adı, aspect, değer, alıntı doğru mu;
   `unverified_quote` oranı. Kabul ≥ 0.9.
2. **Resim kararı:** `visual_detail` içindeki her satır (metin değeri, resmin `seen` değeri,
   `p_against`) gözle; `SETTING_IMAGE_MIN` bu kümede seçilir. B (belli değil) oranı yazılır.
3. **Metin–metin kesinliği:** `candidates_detail` etiketlenir (gerçek / farklı mekân / açıklanan /
   bakış açısı); `SETTING_JUDGE_MIN` seçilir.
4. **Geri çağırma (enjekte):** metne «odanın penceresi bahçeye bakıyordu» + sonra «penceresinden
   sokağı izledi» → bulgu; «gece olmuştu» yazılıp gündüz resmi olan sayfa → resim bulgusu.
5. **Maliyet.**

## 8. Açık kararlar

- Resimden ölçülmeyen aspect'ler (§2) için ileride «mekân kimliği» (aynı sahne kırpımlarını
  gömme ile kümeleme) düşünülebilir; bu görevde yok, uydurulmadı.
- «Sahne o an» şartı (§6.2) — önce ölçüm.
- Tüm bulgular WARN; ERROR eşiği ölçümden sonra.
