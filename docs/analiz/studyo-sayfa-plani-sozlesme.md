# Kitap Tasarım Stüdyosu — sayfa planı sözleşmesi (2026-09-25)

Üç paralel iş bu belgeye göre yazılır: **A** motor (sayfa planı, dizgi kalıbı, stüdyo servisi uçları), **B** otomatikler
(palet, balon önerisi, renk kuralları), **C** ekran + köprü + GPU giriş kapısı. Belgede yazmayan bir alan eklenecekse
önce buraya eklenir; ekip arası tek gerçek budur.

## Kullanıcı kararları (2026-09-25)
- Ekranda sayfa **silme, ekleme, sıralama, metin düzeltme, sayfa başına yerleşim**.
- Resim sayfada **fareyle sürüklenip bırakılır, köşeden büyütülüp küçültülür**; aynısı balon ve yazı kutusu için.
- Çocuk kitabında **konuşma balonu**: diyalog cümlesi sayfa metninden **çıkar, yalnız balonda** durur.
- **Renkli yazı**: ses sözcükleri, karakter konuşmaları karakter renginde, karakter adları vurgulu; editör seçtiği yere
  paletten renk verir.
- **Palet**: kitabın kendi resimlerinden otomatik; yalnız baskıya uygun ve beyaz zeminde okunur (WCAG kontrast ≥ 4.5)
  renkler; yetmezse Timaş sabit çocuk paletiyle tamamlanır; editör değiştirebilir.
- Balon ve yazı **resmin içine çizilmez**; dizgide resmin üstüne vektör olarak basılır (Türkçe harf bozulmaz, düzeltilebilir).

## Kavram
Bugün sayfalar metnin Typst akışından türüyor (`typeset.py` → `pagemap.json`) ve resimler sayfa **numarasıyla**
tutuluyor (`studio.json.pages["12"]`). Sayfa planında sayfa **kalıcı bir kayıt** olur:

1. Mevcut otomatik hat (`run.py`: profil → spec → fit → artplan → resim) aynen çalışır.
2. Resimler üretildikten sonra (ya da ilk kez plan istendiğinde) `plan.freeze(job_dir)` bugünkü `pagemap` + `artplan`
   + `studio.json`'dan **`plan.json`** üretir. Bundan sonra iç sayfalar `plan.json`'dan, yeni `templates/plan.typ` ile dizilir.
3. `plan.json` yoksa her şey bugünkü gibi `book.typ` ile çalışır (geri uyum; eski işler bozulmaz).
4. Ön sayfalar (iç kapak, künye, yazar/çizer) plana girmez, bugünkü gibi üretilir; künye `KunyePanel` ile düzenlenir.

## `plan.json` (iş klasöründe)
Ölçüler **mm**, köken taşma paylı sayfanın sol üstü (0,0); sayfa `W = trim_w + 2·bleed`, `H = trim_h + 2·bleed`.

```jsonc
{
  "version": 1,
  "rev": 7,                                  // her yazımda +1; eşzamanlı düzenleme denetimi
  "frozen_at": "2026-09-25T10:00:00Z",
  "frozen_by": "muratsancar",
  "page": {"w": 169, "h": 231, "bleed": 2, "safe": 8, "gutter": 4},   // spec'ten kopya
  "palette": {
    "colors": [{"name": "Gece mavisi", "hex": "#1F3B73", "source": "resim|timas|editor"}],   // 5–7 renk
    "text": "#2C2C2A",                                                 // gövde metni rengi
    "characters": {"Elif": "#B0341C", "Ayşe": "#1F6F5B"}             // karakter → renk
  },
  "pages": [
    {
      "id": "p_1a2b3c4d",                 // kalıcı; sıralama/silme bu kimlikle
      "chapter": 0,                        // bölüm dizini ya da null
      "layout": "art-top",                // aşağıdaki listeden; kullanıcı kutu oynatınca "custom"
      "art": {                             // resim yoksa null
        "id": "a_9f8e7d6c",               // kalıcı resim kimliği; studio.json.pages anahtarı bu olur
        "box": {"x": 0, "y": 0, "w": 169, "h": 118},
        "fit": "cover",                    // cover | contain
        "focus": {"x": 0.5, "y": 0.5}      // cover kırpmada odak (0–1)
      },
      "text": {                            // metin yoksa null
        "box": {"x": 14, "y": 126, "w": 141, "h": 88},
        "align": "left",                   // left | justify | center
        "size": 16,                        // pt; null → kitap varsayılanı
        "background": null,                // "text-over-art" için yarı saydam kutu: "#FFFFFFE6"
        "blocks": [
          {"id": "c0b3", "kind": "para",       // para | sound | heading
           "runs": [{"text": "Elif pencereden baktı. "},
                    {"text": "Ayşe", "color": "#B0341C", "weight": 700, "source": "auto"},
                    {"text": " çok heyecanlıydı."}]}
        ]
      },
      "bubbles": [
        {"id": "b_12ab", "speaker": "Elif", "text": "Bak, bir yıldız!",
         "shape": "oval",                  // oval | thought | shout | box
         "box": {"x": 12, "y": 14, "w": 52, "h": 22},
         "tail": {"x": 48, "y": 70},      // kuyruğun ucu (konuşanın ağzı/başı); null → kuyruksuz
         "color": null,                    // metin rengi; null → palette.characters[speaker] ya da text
         "source": "auto|editor"}
      ],
      "figures": [                         // kullanıcının ürettiği serbest figürler (saydam PNG)
        {"id": "f_77aa", "asset": "g_3c4d5e6f", "box": {"x": 110, "y": 60, "w": 40, "h": 52},
         "rotate": 0, "flip": false, "z": 3}
      ],
      "texts": [                           // kullanıcının eklediği serbest yazı kutuları (sayfa metninden ayrı)
        {"id": "t_55cc", "box": {"x": 20, "y": 40, "w": 60, "h": 18}, "align": "center", "size": 22,
         "background": null, "runs": [{"text": "Sihirli orman", "color": "#1F3B73", "weight": 800, "font": "heading"}],
         "z": 4}
      ],
      "overflow": false                    // dizgi yazar: metin kutusuna sığmadı mı
    }
  ],
  "assets": {                              // figür kütüphanesi (iş başına); sayfalarda asset kimliğiyle kullanılır
    "g_3c4d5e6f": {"kind": "figure", "prompt": "kırmızı balonlu küçük tilki", "path": "figur/g_3c4d5e6f.png",
                   "w_px": 1024, "h_px": 1331, "alpha": true, "by": "muratsancar", "at": "2026-09-25T11:02:00Z",
                   "characters": ["Elif"]}
  },
  "warnings": ["Sayfa sayısı 8'in katı değil: 2 sayfa eksik."]  // dizgi yazar
}
```

`run` alanları: `text` (zorunlu), `color` (hex), `weight` (400/700/800), `size` (pt), `font` ("body"|"heading"),
`source` ("auto" = kural üretti, "editor" = elle). Editörün verdiği `source:"editor"` run'ına otomatik kural dokunmaz.

**Yerleşim listesi** (`layout`), hazır kutular sayfa ölçüsünden hesaplanır (`plan.preset(layout, page)`):
`art-top` (resim üstte ~%52, yazı altta) · `art-bottom` · `art-full` (tam sayfa resim, yazı yok) ·
`art-left` / `art-right` (yarım sayfa yan yana) · `text-over-art` (tam sayfa resim + alt yarı saydam yazı kutusu) ·
`text-only` · `blank` (boş) · `custom` (kutular elle).

**Kurallar**
- Resim kutusu taşma payına kadar gidebilir; yazı ve balon kutusu güvenli alanın (bleed+safe) içinde kalmalı — dizgi
  aşanı `warnings`'e yazar, engellemez.
- Toplam iç sayfa (ön sayfalar dahil) 8'in katı değilse `warnings`; sayfa kendiliğinden eklenmez/silinmez.
- Metin kutusuna sığmayan metin **kesilmez**: dizgi `overflow: true` yazar, ekranda "metin taşıyor" uyarısı çıkar;
  editör kutuyu büyütür, puntoyu küçültür ya da "sonraki sayfaya taşı" der.
- `freeze` sırasında çocuk profilinde (`age_max ≤ 12` ve resim türü HER_SAYFA) `dialogue` blokları sayfa metninden
  çıkarılıp o sayfanın `bubbles` listesine konur (B'nin `bubbles.from_dialogue` + `bubbles.place`); diğer kitaplarda
  diyalog metinde kalır.
- Renk kuralları (B: `colorize`) yalnız çocuk profilinde otomatik uygulanır; editörün verdiği renk her zaman kazanır.

**Katmanlar (z sırası):** resim (0) → yazı kutusu (1) → balonlar (2) → figürler ve serbest yazılar kendi `z`'leriyle
(≥ 3). Ekranda "öne getir / arkaya gönder" `z`'yi değiştirir.

## Serbest figür (kullanıcı kararı 2026-09-25)
- Editör tarif yazar ("kırmızı balonlu küçük tilki"), istersen kitabın karakterlerinden birini referans seçer; figür
  kitabın üslubuyla, **saydam arka planla** üretilir, `assets`'e girer, seçili sayfaya varsayılan kutuyla eklenir.
- Saydamlık: önce resim modeli düz, tek renk bir zemin üzerinde figür çizer, sonra zemin ayıklanır (kenar yumuşatma
  dahil). Yeni bir model gerekiyorsa lisansı ticari kullanıma uygun olmalı; eklemeden önce ölçüm + gerekçe yazılır.
- Üretim GPU işidir (Temporal, bugünkü resim işleri gibi); ekran işin bitmesini bekler, bu sırada düzenleme sürer.
- Figür bir kez üretilir, birçok sayfada kullanılabilir; sayfadan silinmesi kütüphaneden silmez.

## Başlangıçta resim seçimi (kullanıcı kararı 2026-09-25: "tüm kitaplar çocuk kitabı olmayacak")
- İş açılırken (kitaptan ya da Word'den) seçim: `art_mode` = `auto` (varsayılan, önerilen) | `every_page` (HER_SAYFA) |
  `chapter` (BOLUM_BASI) | `none` (YOK). `POST jobs` ve `POST jobs/docx` (sorgu parametresi) bunu alır; `job.json`'a yazılır.
- `auto` dışındaki seçim profilin resim kararının **önüne geçer** (`profile.py` karar sırası: kullanıcı seçimi > yayınevi
  kaydı/çizer kuralı > model). `profile.json`'a `art_source: "editor"|"auto"` ve gerekçe yazılır; ekran otomatik kararı
  gerekçesiyle gösterir ("Okur yaşı 7–9, her sayfa resimli seçildi").
- `none`: resim adımı hiç koşmaz, görsel model açılmaz; sayfa planı `text-only` yerleşimle kurulur.
- Sonradan değiştirme: `POST jobs/{job}/art-mode {"art_mode": …}` → yerleşim yeniden kurulur (`restart` benzeri, plan
  varsa yeni plan; eski plan `plan-history`'de kalır), üretilmiş resimler silinmez, kullanılmayan resimlere düşer. GPU
  işi sürüyorsa 409.
- Otomatik çocuk öğeleri (balon, renkli yazı) yalnız `bubbles.wanted(profile)` doğruysa; resimsiz kitapta kullanıcı
  efekt yazı, şekil, fotoğraf ve figürü elle ekleyebilir.
- Ekran (C): yeni iş formunda dört seçenekli kartlar (kısa açıklamalı, `auto` seçili), iş sayfasında mevcut seçim ve
  "değiştir" (onaylı, sonuçlarını söyler). Köprü `art_mode`'u geçirir ve `art-mode` ucunu vekil eder.

- **Resimsiz kitabın kapağı (karar 2026-09-25):** `none` seçilince kapak yazı ağırlıklı (tipografik) üretilir: paletten
  zemin, başlık/yazar kitabın başlık fontuyla, isteğe bağlı şekil/desen; görsel model açılmaz. Kapak ekranında "kapağa resim
  üret" yine seçilebilir (tek kapak resmi için model açılır).

## A teslim notları (2026-09-25, `63389c49`) — sözleşmeye eklenenler
1. Blok `kind`: `para | dialogue | sound | heading`; `dialogue` balona geçmeyen kitapta metinde "– " ile basılır.
2. `plan.page` ek alanları: `art_ratio` (hazır yerleşimde resim bandı oranı), `body_size` (varsayılan punto).
3. Meşgul kuralı: aynı işte GPU işi sürüyorsa **yalnız GPU isteyen** yazanlar (resim, figür, kaliteyi artır, art-mode)
   409 `BUSY` döner; plan düzenlemeleri süren işi beklemez.
4. Sayfa dışına taşan kutu reddedilmez, sayfaya kırpılır (en küçük kenar 1 mm); dönen `page` düzeltilmiş hâlidir
   (çevrimdışı sıradaki düzenleme 400 ile kaybolmasın diye).
5. Metni olan sayfa resim-yalnız yerleşime (`art-full`, `blank`) geçirilmek istenirse 400: "önce metni taşıyın".
6. Hata gövdesi `{"code","detail"}`; `STALE`'de `rev`, `IN_USE`'da `pages`, `TOO_LARGE`'da `limit_mb`.
7. Dönüşler: `unused-art` → `{"art":[{"id","selected","approved","versions"}]}`; `figures` → `{"workflow","job","asset"}`;
   `jobs` → `{"busy","jobs":[…]}`; `photos` ayrıca `rev`, `warnings`, `figure`; `dpi_hint` sayfaya konduysa o kutudaki,
   konmadıysa tam sayfaya sığınca olacak dpi.
8. Ek alanlar: `bubbles[].size|warning|overflow`, `texts[].overflow`; kökte `updated_at|updated_by|built_seconds|
   restored_from`; asset'te `derived_from|upscale|dpi|sharpened|note|cutout|prompt_en|seed|mode|key`.
9. Şekil `fill`/`stroke`: hex ya da palet rolü (`accent|soft|ink`); Typst paletine `accent`, `ink` eklenir.
10. Ön kontrol "metin eksiksiz" denetimi plan varken planın metniyle karşılaştırır; efekt yazı ve şekil yazısı bu
    denetime girmez.
11. API'den çağrılan freeze balonları kuralla yerleştirir; hat sonundaki freeze kuyruğu konuşana yöneltmek için görsel
    okuyucuyu gateway üzerinden çağırır.

## Efekt yazılar ve süs/şekiller (kullanıcı kararı 2026-09-25: "sadece balon olmasın")
İki yeni iş: **D** motor (`apps/editor/src/editor/production/elements.py` + `templates/elements.typ`), **E** ekran
(`src/canvas/editorial/studio/elements/`). A ve C bunları yalnız çağırır/yerleştirir; çizim ve katalog D'de, paneller E'de.

**Efekt yazı:** `texts[]` öğesine isteğe bağlı `effect`:
```jsonc
"effect": {"style": "burst",          // burst | wave | arc | shadow | outline | stacked | bounce | rainbow
           "params": {"curve": 0.6,     // arc/wave: -1..1 kavis
                      "outline": "#FFFFFF", "outline_w": 0.8,   // mm
                      "shadow": "#1F3B73", "shadow_dx": 0.8, "shadow_dy": 0.8,
                      "colors": ["#B0341C", "#1F6F5B"],        // rainbow/bounce: harf harf dönen renkler
                      "burst_fill": "#FAC775", "burst_stroke": "#2C2C2A", "angle": -8}}
```
Harfler vektör kalır (Türkçe doğru, düzeltilebilir); kavis/dalga harf harf yerleştirmeyle yapılır. Renkler paletten.

**Şekil katmanı:** sayfa nesnesine `shapes` listesi (z sırası figürlerle aynı kural):
```jsonc
"shapes": [
  {"id": "s_1a2b", "kind": "sign",      // aşağıdaki katalog
   "box": {"x": 30, "y": 150, "w": 60, "h": 30}, "rotate": -4, "flip": false, "z": 5,
   "fill": "#F2E3C6", "stroke": "#5B3A1E", "stroke_w": 0.6, "opacity": 1,
   "params": {"posts": 1},              // türe özel
   "runs": [{"text": "Sihirli Orman", "color": "#5B3A1E", "weight": 800, "font": "heading"}],  // yazı taşıyan türlerde
   "text_size": 18}
]
```
**Katalog** (`elements.CATALOG`; her tür: Türkçe ad, grup, varsayılan kutu oranı, varsayılan renk rolleri, parametreler,
yazı taşır mı): çerçeve (`frame`: düz/dalgalı/noktalı/çift çizgi, tam sayfa kenarlık), köşe süsü (`corner`), serpiştirme
(`scatter`: yıldız/kalp/nokta/konfeti, adet ve tohum parametresi — deterministik), ok (`arrow`: düz/kıvrık), tabela (`sign`),
not kâğıdı (`note`), zarf (`envelope`), parşömen (`scroll`), rozet (`badge`: sayfa no/sayı), şerit (`ribbon`: bölüm başı),
yıldız (`star`), kalp (`heart`), bulut (`cloud`), patlama (`burst`), çizgi/dalga (`line`). Hepsi vektör; renk yoksa
paletten rol ile (`accent`, `soft`, `ink`) doldurulur.

**Uçlar (D):** `GET plan/elements/catalog` → katalog; `GET plan/elements/{kind}/preview?w=&style=` → küçük PNG (kitabın
paleti ve fontlarıyla; ekran kütüphanesi bunu gösterir); `GET plan/effects/{style}/preview?w=&text=` → efekt önizlemesi.
Yazan uç yok: şekil ve efekt sayfa `PUT`'uyla kaydedilir. Doğrulama `elements.validate(shape|effect)` → hata metni ya da None
(A'nın sayfa PUT'u bunu çağırır).

**Dizgi bağlantısı:** `plan.typ` `#import "elements.typ": draw-shape, effect-text` yapar; `shapes` öğesini
`draw-shape(s, palette, fonts)`, `effect`'li serbest yazıyı `effect-text(t, palette, fonts)` ile kutusuna çizer. Kutu, döndürme,
aynalama, z sırasını A uygular; `elements.typ` kutu içine (0,0,w,h) çizer.

**Ekran (E):** "Öğeler" paneli (katalog grupları, önizleme küçük resimleri, sayfaya sürükle-bırak ya da tıkla-ekle),
"Efekt yazı" paneli (hazır stiller, kavis/gölge/dış çizgi ayarları, paletten renkler), seçili şekil/efekt için özellik
paneli (renk rolleri, parametreler, yazı). Bileşenler C'nin düzenleyicisine takılabilir olarak dışa verilir:
`<ElementLibrary onAdd(shape)/>`, `<EffectTextPanel value onChange/>`, `<ShapeInspector value onChange/>`; sayfaya
ekleme/kaydetme C'nin otomatik kayıt sırasından geçer.

## Fotoğraf yükleme (kullanıcı kararı 2026-09-25)
- Editör bilgisayardan/telefondan fotoğraf yükler (JPEG, PNG, WebP; HEIC okunabiliyorsa o da — okunamıyorsa açık hata).
  Yükleme bugünkü stüdyo kalıbıyla ham gövde `PUT` + `filename` sorgu parametresi (multipart yok).
- Sunucu: EXIF yönü uygulanır, sRGB'ye çevrilir, EXIF/konum bilgisi silinir (kişisel veri), `foto/<gid>.<ext>` olarak
  saklanır, `assets`'e `{"kind": "photo", "w_px", "h_px", "alpha", "name", "by", "at"}` ile girer.
- Kullanım: (a) figür gibi serbest katman (`figures` listesi, aynı alanlar), (b) sayfanın ana resmi (`art.id` yerine
  `art.asset` = gid; `studio.json` sürümlerine karışmaz), (c) isteğe bağlı "arka planı kaldır" → yeni saydam asset
  (figür arka plan ayıklamasıyla aynı yol; düz zemin değilse sonuç ekranda önizlenir, kullanıcı onaylar).
- Baskı denetimi: yerleştirilen kutudaki etkin çözünürlük < 300 dpi ise sayfa `warnings`'ine "baskıda bulanık çıkabilir
  (… dpi)" yazılır; ön kontrol (preflight) da aynı denetimi yapar. Engellemez.
- **Kaliteyi artır** (kullanıcı kararı 2026-09-25): düşük dpi uyarısının yanında düğme. Mevcut büyütme hattı
  (`images.py` büyütme ucu, gateway `book-upscale` takma adı; açılamazsa Lanczos — o durumda ekranda "yalnız büyütüldü,
  keskinleştirilemedi") fotoğrafı yerleştirildiği kutunun 300 dpi ölçüsüne yetecek kadar, en çok 4×, büyütür → yeni asset
  (`kind: "photo"`, `derived_from: gid`, `upscale: 2|3|4`). Özgün silinmez. Ekran öncesi/sonrası karşılaştırma gösterir,
  editör onaylarsa sayfadaki kutu yeni asset'e geçer; "özgüne dön" her zaman mümkün. 4× de yetmezse ulaşılan dpi yazılır.
  Uç: `POST plan/assets/{gid}/upscale {"page": pid, "item": fid}` → `{"workflow": id}` (GPU işi; figür/resim işleriyle
  aynı sıra ve model devri kuralları).
- Boyut: tek dosya üst sınırı yönetim ayarı `STUDIO_UPLOAD_MB` (varsayılan 60) — ekranda yükleme alanında yazılı;
  aşarsa açık hata. Giriş kapısı ve portal nginx'i aynı değere göre ayarlanır (bugünkü Word ucu 21 MB kalıbı).

## Otomatik kayıt, kesintiye dayanıklılık (kullanıcı kararı 2026-09-25: "yapılanlar asla kaybolmasın")
- **Sunucu:** `plan.json` her yazımda atomik yazılır; önceki hâli `plan-history/<rev>.json` olarak saklanır (silinmez,
  tavan yok). `GET plan/history` sürüm listesi, `POST plan/restore {"rev": n}` o sürümü yeni sürüm olarak geri yükler.
- **Tarayıcı:** her düzenleme önce cihazdaki kalıcı depoya (IndexedDB; yoksa localStorage) iş kimliğiyle yazılır, sonra
  sıraya girer ve sunucuya gider. Sürükleme/yazma sırasında 600–800 ms bekleyip toplu gönderilir. Bağlantı yoksa sıra
  cihazda bekler; bağlantı gelince sırayla gönderilir. Sayfa yenilenirse açılışta cihazdaki gönderilmemiş sıra bulunur ve
  sunucuya yeniden uygulanır.
- **Çakışma:** sunucu `STALE` (409) dönerse ekran sunucudaki son planı alır, cihazdaki bekleyen düzenlemeleri **sayfa
  kimliği bazında** yeniden uygular (aynı sayfayı başkası da değiştirdiyse kullanıcıya "bu sayfa başka biri tarafından
  değiştirildi: benimkini koru / onunkini al" sorulur). Hiçbir durumda düzenleme sessizce atılmaz.
- Ekranda sürekli durum: "Kaydedildi · 12:04", "Kaydediliyor…", "Bağlantı yok — değişiklikler cihazda saklanıyor (3)".

## Resim kimliği göçü
`studio.json.pages` bugün sayfa numarası ve `"kapak"` ile anahtarlı. `freeze` her resimli sayfaya `a_<8hex>` kimliği verir
ve `studio.json.pages[<sayfa no>]` kaydını `studio.json.pages[<a_id>]`'e **taşır** (kapak değişmez). `artplan.scenes[].page`
yanına `art_id` eklenir. `studio.regenerate/select/approve` her iki anahtarı da kabul eder (plan yoksa numara).
Yeni eklenen resimli sayfa için sahne kaydı boş başlar; editör "resim üret" der (`regenerate(key=a_id, mode="new",
direction=…)`), yönlendirme zorunlu.

## Stüdyo servisi uçları (A yazar; `/v1/studio/jobs/{job}` altında, yetki bugünkü gibi Bearer + yazanlarda `X-Editor`)
| Yöntem | Yol | Gövde | Dönen |
|---|---|---|---|
| GET | `plan` | — | `plan.json` (yoksa 404 `{"code":"NO_PLAN"}`) |
| POST | `plan/freeze` | — | `plan.json` (varsa bozmaz, aynısını döner) |
| PUT | `plan/pages/{pid}` | `{"rev": n, "page": sayfa nesnesi}` | `{"page": …, "rev": n+1, "warnings": […]}` |
| POST | `plan/pages` | `{"rev": n, "after": pid\|null, "layout": "text-only"}` | yeni sayfa + rev |
| DELETE | `plan/pages/{pid}?rev=n` | — | `{"ok":true,"rev":n+1}`; resmi silinmez, "kullanılmayan resimler"e düşer |
| POST | `plan/order` | `{"rev": n, "ids": [pid…]}` (tam liste) | `plan.json` |
| POST | `plan/pages/{pid}/split` | `{"rev": n, "block": id, "at": char}` | iki sayfa (taşan metni yeni sayfaya) |
| PUT | `plan/palette` | `{"rev": n, "palette": …}` | `plan.json` |
| POST | `plan/pages/{pid}/bubbles/suggest` | — | önerilen `bubbles` (kaydetmez) |
| GET | `plan/pages/{pid}/preview?w=` | — | PNG (o sayfanın güncel dizgisi) |
| GET | `plan/unused-art` | — | sayfaya bağlı olmayan resim kimlikleri |
| POST | `plan/figures` | `{"prompt": "…", "characters": ["Elif"], "page": pid\|null}` | `{"workflow": id}` (GPU işi başlar; bitince asset `assets`'e, `page` verildiyse o sayfaya eklenir) |
| GET | `plan/assets/{gid}?w=` | — | PNG (saydam) |
| DELETE | `plan/assets/{gid}?rev=n` | — | kullanılıyorsa 409 (hangi sayfalarda) |
| PUT | `plan/photos?filename=…&page=pid` | ham dosya gövdesi | `{"asset": gid, "w_px", "h_px", "dpi_hint"}`; `page` verildiyse figür olarak eklenir |
| POST | `plan/assets/{gid}/cutout` | — | `{"workflow": id}` → saydam yeni asset (onaylanınca kullanılır) |
| GET | `plan/history` | — | `[{"rev", "at", "by", "what"}]` |
| POST | `plan/restore` | `{"rev": n}` | `plan.json` (yeni rev) |
| GET | `plan/jobs` | — | süren figür/resim işleri ve durumları (ekran bununla bekler) |

Her yazan uç `plan.json`'u atomik yazar (`os.replace`), `provenance.jsonl`'a satır ekler, iç sayfa PDF'ini ve önizlemeyi
yeniden derler (bugünkü `studio.rebuild` gibi; tüm kitap derlenir, süre ölçülür), sonuç `warnings`/`overflow` ile döner.
Aynı işte GPU işi sürüyorsa (busy) yazanlar **409** döner; `rev` uyuşmazsa **409** `{"code":"STALE"}`.

## Köprü uçları (C yazar; `backend/semantic_bridge`, bugünkü stüdyo kalıbıyla)
`/api/v1/editorial/studio/jobs/{job}/plan…` — yukarıdaki servis uçlarının birebir vekili; oturum zorunlu, yazanlar
`admin_mod.audit` kaydı düşer, `X-Editor` = oturumdaki AD hesabı. GPU giriş kapısı (`deploy/tt-gpu/editor-ingress/
add-studio-routes.py`) yeni yolları ve `PUT`/`DELETE` yöntemlerini tanır.

## B'nin A'ya verdiği saf fonksiyonlar (`apps/editor/src/editor/production/`)
- `palette.extract(image_paths: list[Path], n=6) -> list[{"name","hex","source"}]` — resimlerden, baskıya uygun,
  beyaza karşı kontrast ≥ 4.5; yetmezse `palette.TIMAS_KIDS` ile tamamlar. Ad Türkçe renk adı.
- `palette.assign_characters(characters: list[{"name", ...}], colors) -> {ad: hex}` — birbirinden ayrışan renkler.
- `colorize.apply(blocks, characters: dict[name,hex], palette) -> blocks` — `runs` üretir: ses sözcüğü (vurgu, büyük),
  karakter adı (karakter rengi, kalın). `source:"editor"` run'ına dokunmaz.
- `bubbles.from_dialogue(blocks, speakers: list[str]) -> (kalan_bloklar, bubbles)` — diyaloğu balona taşır; konuşanı
  bulamazsa `speaker=None`.
- `bubbles.place(bubbles, art_box, text_box, image_path, locate) -> bubbles` — `locate(image_path, name) -> bbox|None`
  (görsel okuyan model, gateway üzerinden; A çağrıyı verir, B sınarken sahte `locate` kullanır) ile kuyruğu konuşana,
  balonu resmin boş alanına (kenar/gökyüzü) yerleştirir; balonlar birbirini ve konuşanın yüzünü örtmez; yazı kutusunun
  ve güvenli alanın dışına taşmaz.
- Resim istemine çocuk profilinde balon için boş alan (üst bölgede sade gökyüzü/duvar) bırakma cümlesi eklenir.

**B teslim notları (2026-09-25, `d8d0db35`) — imzalara isteğe bağlı ekler:**
- `colorize.apply(blocks, characters, palette, *, body_size=None)`: ses sözcüğü run'ının `size`'ı gövde puntosunun
  1,35 katı; `body_size` verilmezse `size` yazılmaz. Vurgu rengi `palette.accent` varsa o, yoksa paletin karakterlere
  verilmemiş ilk rengi. `palette` plan paleti (dict) ya da renk listesi olabilir. Çıktıda blok `text` yerine `runs` taşır.
- `bubbles.place(..., *, page=None, size=14.0)`: `page` = `plan.page`; verilmezse sınır resim kutusudur. `size` balon puntosu.
- `locate(image_path, name) -> {"x","y","w","h"} | None`: konuşanın **başı/yüzü**, resme göre 0–1 oran (1,5'ten büyük
  değer piksel sayılır). Hata verirse kuyruk null olur, hat düşmez.
- Balon nesnesinde isteğe bağlı `"warning"` (metin): yer bulunamazsa ekranda gösterilir.
- Çocuk kitabı kuralı tek yerde: `bubbles.wanted(profile)` (freeze bunu kullanır).
- `images.py` çocuk profilinde üretilen sayfa resmi istemine balon için boş alan cümlesini ekler (düzeltme ve kapakta değil).

## Ekran (C yazar; `src/canvas/editorial/studio/`)
- Sayfa şeridi: küçük önizlemeler, sürükle-bırak sıralama, sil (onaylı), araya boş sayfa ekle, 8'in katı uyarısı.
- Sayfa tuvali: sayfanın dizgi önizlemesi üstünde resim, yazı kutusu ve balonlar **seçilebilir, sürüklenebilir, köşeden
  boyutlandırılabilir** (mm ↔ px ölçekli; güvenli alan ve taşma payı kılavuz çizgisi; kutular güvenli alana yapışır).
  Bırakınca `PUT plan/pages/{pid}`; dönen önizleme yenilenir. Klavye: ok tuşlarıyla 1 mm, Shift ile 5 mm.
- Sağ panel: yerleşim seçici, metin düzenleyici (blok blok; seçili yere paletten renk), balon listesi (metin, konuşan,
  biçim, sil, "balonları öner"), palet düzenleyici, taşma/uyarı listesi.
- Figür: "Figür üret" (tarif + isteğe bağlı karakter referansı) → iş biterken ekranda bekleme durumu; figür
  kütüphanesi paneli, figürü sayfaya sürükleyip bırakma; tuvalde sürükle, köşeden boyutlandır, döndür, aynala,
  öne/arkaya.
- Fotoğraf: "Fotoğraf yükle" (dosya seç ya da tuvale sürükle-bırak; telefonda kamera/galeri), yükleme ilerlemesi,
  kütüphanede figürlerle birlikte; sayfaya bırak, "sayfa resmi yap", "arka planı kaldır" (önizle → onayla);
  düşük çözünürlük uyarısı kutunun üstünde görünür. Yükleme bağlantı koparsa yeniden denenir; dosya cihazda
  (IndexedDB) yükleme bitene kadar tutulur.
- Serbest yazı: "Yazı ekle" → tuvalde kutu; sürükle/boyutlandır, yerinde yaz, paletten renk, punto, kalınlık.
- Otomatik kayıt ve çevrimdışı sıra (yukarıdaki bölüm); sürüm geçmişi paneli ("geri al" = `plan/restore`),
  tarayıcı içi geri al/yinele (Ctrl/Cmd+Z, Shift+Z).
- Telefonda: tuvalde yalnız görüntüleme + sağ paneldeki alanlarla düzenleme (sürükleme masaüstünde).
- Ekranda model/teknoloji adı yok ("Zeki AI" ya da işlev adı).

## C teslim notları (2026-09-25, `92671863`) — sözleşmeye eklenenler
1. `GET plan/pages/{pid}/preview` taşma paylı tam sayfayı (W×H) kapsar; ekran kutuları bu görüntünün üstüne yüzdeyle koyar.
2. `pages[].art.selected` salt okunurdur (seçili sürüm); istemci yazmaz.
3. Resimsiz sayfaya resimli yerleşim: istemci `art.id: null` gönderir, sunucu `a_<8hex>` verir ve boş sahne kaydı açar.
4. Hazır yerleşim formülü (`planModel.preset` ile aynı): s = bleed+safe; art-top resim {0,0,W,0,52H}, yazı altta güvenli
   alanda; art-bottom simetriği; art-left/right yarım sayfa; text-over-art yazı {s, 0,62H, W−2s, H−s−0,62H}, zemin
   `#FFFFFFE6`; text-only güvenli alan; art-full/blank yazısız. Cilt payı (gutter) kullanılmaz.
5. `plan/jobs` satırı: `{workflow, kind: figure|photo|upscale|cutout|art, status: queued|running|done|failed, page, item,
   source, asset, progress:[n,toplam], error, note}`.
6. `after: null` = başa ekle. Yapısal yazımlardan (ekle/sil/böl/sıra) sonra ekran planı yeniden okur; dönüş gövdesinin
   biçimine bağlı değildir.
7. Köprüde `GET /api/v1/editorial/studio/settings → {"upload_mb"}` (fotoğraf sınırı ekrana).
8. Hata gövdesi köprüden olduğu gibi geçer; ekran hem `{"code","detail"}` hem `{"detail":{…}}` okur.
9. Açık: geri al/yinele sayfa ekleme/silmeyi kapsamaz (sürüm geçmişi kapsar); tuvale bırakılan fotoğraf sunucunun
   varsayılan kutusuna düşer; ileride toplu `PUT plan/pages`. Profilde gerekçe `illustration_source`, kaynak `art_source`.
10. HEIC/HEIF kabul edilir (`pillow-heif`, JPEG'e dönüşür); imaj yeniden derlenene kadar canlıda açık hata verir.

## D teslim notları (2026-09-25, `8db7bca4`) — sözleşmeye eklenenler
1. **Renk alanı** (şekil `fill`/`stroke`, şekil ve serbest yazı run'ı `color`, efekt renk parametreleri): `"#RRGGBB"`,
   saydamlıkla `"#RRGGBBAA"`, `"none"` (boya yok) ya da palet rolü: `accent` (vurgu), `accent2`, `ink` (metin rengi),
   `pop`/`pop2` (canlı dolgu), `sun` (güneş sarısı), `rose` (kalp kırmızısı), `soft`/`soft2` (açık zemin), `paper`
   (kâğıt), `wood`/`bark` (ahşap), `deep` (koyu vurgu), `white`. Roller kitabın paletinden yalnız `elements.typ` →
   `roles(palette)` ile hesaplanır (Python ve ekran rol rengini katalogdan okur; ikinci hesap yok). A'nın 9. notundaki
   üç rol bu listeyle genişledi. Sayfa metni bloklarında (`text.blocks[].runs`) rol yok, yalnız hex.
2. **Çağrı:** `draw-shape(s, palette, fonts, mirror: s.flip)`, `effect-text(t, palette, fonts)`; `palette` = `plan.palette`
   (rengi yoksa Timaş çocuk paleti — önizleme uçlarıyla aynı), `fonts = {"body": spec.body_font, "heading":
   spec.heading_font}`. **Aynalama draw-shape'indir:** çağıran kutuyu aynalamaz (yoksa yazı ters okunur); kutunun yeri,
   döndürme ve z sırası çağıranın (plan.typ `shape-item`). Efekt yazıda `flip` yoktur/yok sayılır.
3. **Punto:** şekilde `text_size`, efekt yazıda `size` null → yazı kutuya sığacak kadar büyür/küçülür, taşma olmaz.
   Sayı verilirse sabittir; sığmazsa kesilmez, çizim `metadata((kind: "element-overflow", id))` bırakır. Dizgi bunu
   `typst.query` ile toplar, öğenin `overflow` alanına (şekil ve efekt yazı) ve plan `warnings`'e («N. sayfa: şeklin yazısı
   şekle sığmıyor», «serbest yazı kutusuna sığmıyor») yazar. `overflow` salt okunurdur; istemcinin gönderdiği atılır.
4. **Efekt ek parametreleri:** `waves` (dalga sayısı), `depth` (kabartma derinliği, harf boyuna oran), `spikes` ve `seed`
   (patlamanın uç sayısı ve tohumu; aynı tohum aynı çizim). Dış çizgi (`outline`, `outline_w`) ve gölge (`shadow`,
   `shadow_dx`, `shadow_dy`) her stilde çalışır. Renk parametresinde `null` = yok.
5. **Katalog** (`GET plan/elements/catalog`, tek biçim — ekran bunu okur):
   `{groups: [{key, name, kinds}], kinds: [{kind, name, group, text, box: {w, ratio, place}, fill, stroke, stroke_w,
   params: {anahtar: {label, type, default, choices?: [{value, label}], min, max, step}}, runs, presets: [{key, name,
   params, box}]}], effects: [{style, name, sample, box: {w, h}, params}], roles: [{key, name, hex}], fonts}`.
   `type`: `choice | number | int | bool | color | colors`; `min`/`max` null = açık uç (doğrulama sınırı değil).
   `box.w` kesim genişliğine oran, `ratio` en/boy, `place` `center | page | corner`. `presets[].key` önizleme ucunun
   `style`'ıdır; biçim seçilince `presets[].params` şeklin `params`'ına yazılır (her türde `params.style` yoktur).
   `roles[].hex` bu kitabın paletinden hesaplanmış rol rengidir.
6. **Yardımcılar:** `elements.new_shape(kind, page, preset)` (tıkla-ekle için motorun varsayılan şekli; renk,
   `stroke_w`, `text_size` null), `new_effect(style)`, `validate(obj)` (şekil ya da efekt → Türkçe hata ya da None),
   `palette_or_default(palette)`.
7. **Dosya:** `templates/elements.typ` dizgi klasörüne `plan.typ` ile birlikte kopyalanır (`typeset.Typesetter`); dosya
   yoksa yalnız o zaman yer tutucu yazılır (şekil çizilmez, efekt yazı düz yazı basılır, rol rengi metin rengine düşer).
8. **Uçlar (A'nın servisinde):** `GET plan/elements/catalog`, `GET plan/elements/{kind}/preview?w=&style=`,
   `GET plan/effects/{style}/preview?w=&text=` — saydam PNG, `Cache-Control: private, max-age=3600`, iş klasöründe
   `dizgi/ogeler/` önbelleği. Plan olmadan da çalışır. Hata: bilinmeyen tür/stil 404 `{"code":"NOT_FOUND"}`; bilinmeyen
   biçim ya da genişlik 16–4000 px dışı 400 `{"code":"INVALID"}`. Önizleme yazısına tavan yok (uzun yazı kutuya sığacak
   kadar küçülür); köprü de genişliği/yazıyı kırpmaz, motorun açık hatası geçer.
9. **Doğrulama:** sayfa `PUT`'unda her şekle ve her `texts[].effect`'e `elements.validate`; hata 400
   `{"code":"INVALID","detail":…}` (A'nın öteki doğrulama hataları da artık aynı kodla döner). Serbest yazı hizası
   `left | justify | center | right`.
10. **Ön kontrol «Metin eksiksiz»:** kitap tarafında efekt yazı ve şekil yazısı yoktur (A 10. not); PDF tarafında da o
    kutulardaki yazı okunmaz (katmanlar ve harf harf yerleşim metni çoğaltır, kitabın kelime dizisine karışmasın).
    Sayfa metni, balon ve düz serbest yazı kutusuyla örtüşen yer okunmaya devam eder (asıl metin asla düşmez).
    `PlanText.element_rects()` → `preflight._page_text`.

## E teslim notları (2026-09-25, `c462c27f`; bağlama DE-bağlama işinde) — ekranın okuduğu biçim
1. **Katalog, ekranda** (`elements/api.ts` → `normalizeCatalog`, D'nin 5. nottaki çıktısından tek dönüşüm):
   `{groups: [{id, name}], items: [{kind, name, group, aspect, width, place, full_page, roles: {fill, stroke, text},
   params: [{key, label, type, options, min, max, step, default}], text, runs, styles: [{value, label, params, box}],
   stroke_w, text_size}], effects: [{style, name, sample, params}], roles: {rol: {name, hex}}}`. Eşleme: `groups[].key →
   id`; `box.ratio → aspect`, `box.w → width`, `box.place → place` (`page` → `full_page`); `fill`/`stroke` → `roles`;
   `presets[] → styles[]` (`key → value`, `name → label`); `params` sözlüğü → anahtarlı liste; `roles` listesi → sözlük.
   E'nin ilk sürümü `styles`'ı `params.style` seçeneklerinden, `aspect`'i kökten bekliyordu; D'nin gerçek çıktısına göre
   düzeltildi (`catalog.fixture.json` motorun gerçek çıktısıdır, test bununla koşar).
2. **Hazır biçim** = `presets[]`: kütüphanede her biçim ayrı karo (önizleme `style` = biçim anahtarı); seçilince biçimin
   `params`'ı şeklin `params`'ına yazılır (çerçevede bu `params.style` olur). Seçili biçim, parametreleri şekildekilerle
   aynı olan ilk biçimdir.
3. **Yeni şekil** motorun `new_shape`'iyle aynı alanlar: kimlik `s_` + 8 onaltılık hane, `fill`/`stroke`/`stroke_w`/
   `text_size` null, `opacity` 1, `params` = türün varsayılanları + biçimin parametreleri, `runs` yazı taşıyan türün
   katalogdaki varsayılan yazısı (boş olabilir: yıldız, kalp, bulut). Kutu motorun `default_box` kuralıyla (genişlik
   kesim eninin `width` oranı, oran `aspect`, `page` = güvenli payın yarısı içeride tam sayfa, `corner` sol üst); güvenli
   alana sığmazsa oran korunarak küçülür.
4. **Renk seçenekleri:** kitabın paleti + «Metin rengi» (`ink`) + «Açık zemin» (`soft`) + «Beyaz»; değer hex yazılır,
   rol rengi katalogdaki `roles[].hex`'ten (dizgiyle aynı). «Otomatik» = null (türün rolü); efekt renginde null = «Yok».
   Rol adıyla gelen değer (motor varsayılanı, API) ekranda kitabın rengine çevrilip gösterilir.
5. **Efekt ayarları** katalogdaki stil parametrelerinden üretilir (kavis, dalga sayısı, dış çizgi, gölge, derinlik,
   patlama rengi/eğimi/uç/tohum, harf renkleri); stil seçilince varsayılanlar katalogdan, rol → hex. Harf renkleri
   boşsa dizgi kitabın paletinden sırayla boyar.
6. **Kaydırıcı aralığı** katalogdaki `min`/`max`'tan; açık uçta (ör. serpiştirme adedi) makul bir aralık, sayı kutusuna
   daha büyük değer yazılabilir (sınır yalnız motorun doğrulama sınırı).
7. **C'ye bağlama:** `slots.tsx` üç bileşeni verir. İstenen bağlam: `jobId`, `palette` (`plan.palette`), `page`
   (`plan.page`), `rev` (**paletin özeti** `paletteKey`; planın her sürümü değil — yoksa her kayıtta bütün küçük resimler
   yeniden istenir), `nextZ` (sayfadaki en büyük z + 1), `onZ` (komşu katmanla yer değiştirir, `restackStep`),
   `onRemove`. Şekil seçiliyken «Öge» sekmesinde yalnız E'nin paneli görünür (konum, dönüş, aynalama, katman, kaldırma
   onda). Tuvale bırakılan şekil bırakılan noktaya ortalanır (`centerBoxAt`); telefonda dokunarak eklenir ve ayarları
   «Öge» sekmesinde açılır. Tip kaynağı `engine.ts` (`PlanShape`, `PlanEffect`, `PlanEffectParams`, `PlanColorRole`);
   `elements/types.ts` bunları yeniden adlandırır.
8. Açık: şeklin tarayıcı taslağı (kaydedilmeden önceki anlık görüntü) yaklaşık bir kutudur; kesin çizim dizgi
   önizlemesiyle gelir. Aynı sayfaya bir şekil birden çok kez eklenebilir, kopyala/çoğalt düğmesi yok.

## J: Pazarlama kiti (2026-09-25) — sözleşmeye eklenenler
- Motor `production/marketing.py` + `api_marketing.py` (`/v1/studio/jobs/{job}/marketing…`), iş klasöründe `pazarlama/`
  (isler, ozet, arka-kapak, urun, sosyal/, kilavuz/, kayit.jsonl). Köprü `editorial_studio_marketing.py`
  (`/api/v1/editorial/studio/jobs/{job}/marketing…`), ekran `studio/marketing/` (stüdyoda «Pazarlama» bölümü, dört sekme).
- Metin motorda üretilir (kitabın metni yalnız stüdyo servisinde; gateway `book-director`); kitap pencere pencere
  bütünüyle okunur, alıntı/kelime metinde birebir aranır. Her çıktı editör onayı ister; onaysız indirme/uygulama/SEO yok.
- Arka kapak: `cover.py` onaylı ve «kapağa uygula» denen yazıyı `pazarlama/arka-kapak.json`'dan okur (yoksa CRM metni);
  uzunluk `templates/marketing/measure.typ` ile cover.typ'nin arka kapak bloğuyla aynı dizgide ölçülür — cover.typ'nin
  arka kapak bloğu değişirse measure.typ de değişir.
- Ürün sayfası SEO'ya `SeoGeo.external_proposal` ile «hazir» öneri olarak düşer; T-soft'a yazım yok.
- Sosyal görseller modelsiz (Pillow); model üretimi görsel kullanan görsel `draft` (ekranda uyarı, dosya adı TASLAK-).

## G: Seri karakter kartı (2026-09-25)
Kullanıcı sözü: "Aynı karakter serinin her kitabında aynı görünsün diye karakterin görünüşü ve renkleri bir kez kaydedilir,
her görselde kullanılır." Motor `production/characters.py`, uçlar `production/api_characters.py`, köprü
`editorial_studio_characters.py`, ekran `studio/characters/` (stüdyoda «Karakterler» düğmesi → yan panel).
- **Dizi kimliği** `series_canon` kurallarıyla: editörün iş için yazdığı ad (`seri.json`) > `book.universe` > künye «Dizi»
  (elle / okunan) ve kitap kaydı SERIES (`series_names`; dizi ismi olmayan yayınevi etiketi dizi değildir); `same_series`
  eşleşen dizi klasörü yeniden kullanılır. Bulunamazsa uçlar 409 `NO_SERIES`, ekran dizi adını sorar.
- **Depo** `<storage>/series/<dizi>/characters.json` (+`rev`, `gecmis/<rev>.json`, `ref/r_….png`); kart işe kopyalanmaz.
  Kart: `name, aliases, kind, age, species_en, look_tr, look_en, colors{hair,fur,eyes,skin,outfit,accent}, palette_color,
  outfits[{name, look_tr, look_en, color, default}], refs[{id, primary, source}], status draft|approved, version, en_stale`.
  İçerik değişen kart taslağa döner; resimlerde yalnız ONAYLI kart kullanılır. `palette_color` «Bu kitaba uygula» ile
  plan paletine (`palette.characters`) yazılır.
- **Resim hattı** (`images.Painter`): kartlı karakterin istem satırı kartın İngilizce tarifi + sabit renkler (ad + hex) +
  kıyafet; referansı kartın birincil görseli (düzenleme ucu referans görsel alıyor). Üretilen her sayfa resmi
  `karakter-denetimi.json`'a «bekliyor» yazılır, `CharacterCheck` iş akışı kuyruğa girer.
- **Denetim**: görsel okuyucu bütün bedenin kutusunu bulur, kesit görsel kimlik servisinde kartın referanslarıyla
  karşılaştırılır (ortanca uzaklık, eşik `ccip_same_max`). Uymayan resim yeni tohumla yeniden çizilir; en çok
  `STUDIO_CHARACTER_RETRIES` kez (yönetim ekranı, grup `studio`, varsayılan 3; köprü değeri `PUT /v1/studio/character-settings`
  ile stüdyoya iletir). Aşılınca en yakın sürüm seçili kalır, panelde «karakter kartına uymuyor». Düzeltme (fix) sürümü ve
  editörün onayladığı/başka sürüm seçtiği resim yeniden çizilmez.
- **Uçlar** `/v1/studio/jobs/{job}/character-cards` altında: `GET` · `PUT series` · `POST suggest|check|cards` ·
  `PUT|DELETE cards/{c_…}` · `POST cards/{c_…}/approve|translate|palette` · `PUT|POST cards/{c_…}/refs` ·
  `GET|DELETE cards/{c_…}/refs/{r_…}` · `POST …/refs/{r_…}/primary` · `GET history`; `GET|PUT /v1/studio/character-settings`.
  Köprü aynı yolları `/api/v1/editorial/studio/…` altında vekil eder (4xx gövdesi aynen; yazanlar `studio_character` denetim kaydı).

## Boyama / etkinlik kitabı (K, 2026-09-25) — resimli kitaptan türetilen ek ürün
- **Türetme:** kaynak iş değişmez. `POST jobs/{iş}/coloring {mode: coloring|coloring_activities, activities:[{kind,
  source?, count?}], captions: model|rule}` yeni iş açar; job.json'da `kind: "coloring"`, `derived_from`, `coloring`
  (seçenekler). `studio.new_job(..., extra=)` kancası. Hat Temporal `ColoringBook` (işçide, görsel model açılmaz):
  kaynak → çizgi → kısa cümle → etkinlik → kapak → dizgi → ön kontrol; adımlar `state.json`'da (hata «bitti + error»:
  akış ekranının «kaldığı yerden devam»ı kitap hattına aittir, boyama işi `coloring/retry` ile sürer).
- **Çizgi (modelsiz, `lineart.extract`):** ortanca süzgeç → CIELAB k-ortalama bölgeler → komşuluk grafiğinde zayıf sınır
  (ΔE/mm) ve küçük bölge birleştirme (`raster.merge_regions`, kapalı şekiller) → göz gibi küçük belirgin bölge korunur,
  koyu olan dolu siyah → yaşa göre kalınlık (≤6: 1,2 mm, ≤9: 0,9, üstü 0,6) → küçük delik doldurma → 2× ölçüde yumuşak
  kenarla yeniden ikileme. Çıktı 1 bit PNG (yalnız siyah/beyaz), 600 dpi.
- **Çizgi (görsel model, isteğe bağlı):** `POST coloring/art/{a_…}/redraw` → `ColoringRedraw` (GPU, busy, bitince
  `_release_if_idle`), kaynağın renkli resmi düzenleme ucuna «boyama sayfası» istemiyle, dönen çizgi `lineart.clean_drawn`
  ile aynı baskı kuralına. Yeni sürüm `mode: "lineart-model"`; ekranda «taslak» (lisans ticari değil). Boyama işinde
  «Düzelt / Farklı üret» ile gelen sürüm de `add_version` kancasında (`coloring.after_version`) ikilenir; artplan üslubu
  çizgi üslubudur.
- **Sayfalar (plan.json doğrudan kurulur):** her resim için [kısa cümle | boyama] çifti (boyama sağ sayfada, güvenli alanda
  `contain`), etkinlik sayfaları (başlık + yönerge serbest yazı, gövde `art.asset` = `etkinlik/<gid>.png`, varlık
  `kind: "activity"`), forma katına kadar «Kendi resmini çiz» (bilgi olarak yazılır), en sonda cevap anahtarı. Sayfa
  rolleri `coloring.json.pages[pid]`'de (plan sayfasına alan eklenmez; sayfa düzenlense de rol kalır).
- **Kısa cümle:** metin modeli (`production_coloring_caption`, en çok 8/12/16 kelime), tutmazsa kural (diyalogsuz ilk
  cümle). Editör `POST coloring/sentences {items:[{aid, text?, approved?}]}` ile düzeltir/onaylar; metin değişirse karşı
  sayfanın metni plan yazımıyla güncellenir.
- **Etkinlikler (`activities.py`, modelsiz, tohumlu):** renk sayıya göre boyama, noktaları birleştir (karakter
  referansının dış konturu), farkı bul (parça sil / aynala / kapalı alanı karart / boş alana şekil ekle), labirent,
  kelime avı (karakter adları + sık kelimeler, Türkçe büyük harf), eşleştirme (karakter ↔ gölge). Sayı tavanı yok;
  sığmayan yeni sayfaya geçer ya da bilgi olarak döner.
- **Kapak:** kaynak kapak resminin sol üst yarısı renkli, sağ alt yarısı çizgi; başlık «… – Boyama (ve Etkinlik)
  Kitabı»; ISBN yeni ürün için boşalır (künyede eksik görünür).
- **Uçlar:** servis `api_coloring.py` (`GET|POST coloring`, `POST coloring/retry|sentences`, `POST coloring/art/{a_}/redraw`),
  köprü `editorial_studio_coloring.py` (aynı yollar `/api/v1/editorial/studio/jobs/{iş}/coloring…`), GPU girişi
  `EDITOR-STUDYO-BOYAMA` bloğu. Ekran `studio/coloring/ColoringPanel` (stüdyo sayfasının altında).

## Okur araçları ve sürüm farkı (N hattı, 2026-09-25)
Servis `production/reader.py`, `production/versions_diff.py`, uçlar `production/api_reader.py` (api.py'ye `include_router`);
köprü `editorial_studio_reader.py`; ekran `studio/reader/` (Okur) ve `studio/diff/` (Karşılaştır), PlanEditor başlığında iki giriş.

| Yöntem | Yol (`/v1/studio/jobs/{job}/` altında) | Gövde / sorgu | Dönen |
|---|---|---|---|
| GET | `plan/reader` | — | `{age, band, picture_book, rev, child, turn}` (son okumaların özeti) |
| POST | `plan/reader/child` · `plan/reader/turn` | `{"passes": n}` (köprü yönetim ayarını koyar) | `{run, already}`; GPU işi sürüyorsa 409 `BUSY`; resimsiz kitapta `turn` 400 `NOT_AVAILABLE` |
| GET | `plan/reader/runs/{r_…}` | — | okuma: `flags[]` ya da `spreads[]`, `stats`, editör kararı her öğede |
| POST | `plan/reader/runs/{r_…}/resume` · `/decisions` | `{flag, decision: applied\|dismissed\|accepted\|rejected\|open}` | — |
| GET | `plan/versions` | — | bu işin geçmişi + aynı kitabın (aynı `book_id` / Word dosya adı) planlı işleri |
| GET | `plan/versions/compare?a=iş:rev&b=iş:rev` | rev `current` olabilir | `{a, b, pages[{a,b,match,status,text[],layout[]}], counts, words, global}` |
| GET | `plan/versions/preview?v=&page=&w=` · `visual?a=&b=&pa=&pb=` · `report?a=&b=` | — | PNG · `{regions[0–1], share}` · PDF |

- Okuma kaydı `okur/<r_…>.json` (okunan planın kopyası dahil), kararlar `okur/<r_…>.decisions.json`; geçmiş sürümün
  dizgisi `karsilastir/r<rev>/`, rapor `karsilastir/rapor-<özet>/`. Hepsi iş klasöründe, silinmez.
- İşaret alanları: `fid, page, no, target (block|bubble|free), id, start, end, quote, kind, reason, replacement, votes,
  passes`; `start/end` hedef metnin harf aralığı. Öneri uygulanınca ekran metni `setPage` ile değiştirir (plan sürümü artar).
- Yönetim ayarı `STUDIO_READER_PASSES` (grup `studio`, varsayılan 3): sayfa başına bağımsız okuma; sayfa çevirmede aday öneri sayısı.
