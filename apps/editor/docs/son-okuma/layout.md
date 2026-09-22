# Sayfa düzeni (`layout`) — ÖLÇÜM BEKLİYOR

Kaynak: `src/editor/proofing/layout.py`, `_layout_lines.py` (v1). Deterministik; model yok.
Her bulgu onu üreten ölçümü `details`'ta taşır.

## 1. Kural — ne bulgudur, ne değildir

| rule | severity | ne |
|---|---|---|
| `folio_duplicate` | ERROR | aynı sayfa numarası iki kez basılmış |
| `folio_sequence` | ERROR | numara, kitabın sabit ofsetini (fiziksel sayfa − basılı numara modu) bozuyor: eksik/çift/sıra dışı sayfa |
| `folio_parity` | WARN | tek numaralar sol (çift) sayfalara düşüyor (PDF 1. sayfa = recto varsayımı) |
| `folio_position` | INFO | folyo diğer sayfalardan farklı yükseklikte (> 2 pt) |
| `margin_outside_trim` | ERROR | metin kesim çizgisinin dışında |
| `margin_safe_zone` | WARN | metin kesime `SAFE_MM`'den (cilt tarafında `GUTTER_MM`) yakın |
| `body_size` | WARN | sayfanın gövde metni kitabın gövde puntosundan ≥ `SIZE_TOL_PT` farklı |
| `leading` | WARN | satır aralığı aynı puntodaki kitap ortancasından > `LEAD_TOL` farklı |
| `age_type_size` | WARN | gövde x-yüksekliği (mm, renderdan) bandın en küçük okuru için alışılanın %90'ının altında |
| `orphan` | WARN | öksüz: paragrafın ilk satırı sayfa sonunda tek |
| `widow` | WARN | dul: paragrafın son satırı sonraki sayfanın başında tek |
| `text_hidden` | WARN | metin renderda görünmüyor (resmin/nesnenin altında) |
| `contrast_low` | WARN < 3:1; INFO 3–4,5:1 (küçük metin) | metin rengi ↔ altındaki zemin/resim WCAG 1.4.3 |
| `contrast_busy` | INFO | ortanca geçiyor ama zeminin en kötü %10'u < 3:1 ve zemin desenli (sd ≥ 0,02) |

Bulgu OLMAYAN: konturlu (outline) metin — kontrastı kontur taşır; rakam satırları (folyo) gövde
sayılmaz; güvenilmez katmanlı sayfalar atlanır; <80 glif gövde metni olan sayfa «metin
sayfası» değildir (resim altı yazı), punto/aralık için bakılmaz.

## 2. Girdi / kaynak

- PDF ve `layer_health`: `_layout_lines.book`; satırlar `page_lines` (yalnız çizilen glifler:
  alfa 0, kırpılmış, ne dolu ne konturlu atılır — docstring: altı kitaptan birinde 3.498 alfa-0
  ve 2.706 kırpılmış glif ayıklandı; üst üste iki kez çizilen satır bir kez).
- Gövde stili `body_style`: en çok glif basan (font, 0,5 pt'ye yuvarlanmış boyut).
- TrimBox: PDF'ten; yoksa sayfa dikdörtgeni (`stats.has_trimbox`).
- Yaş bandı `_age_band`: `claim` METADATA/AGE_RANGE, **yalnız** VERIFIED/EDITOR_APPROVED/
  EDITOR_CORRECTED; yoksa `book.age_group`; içindeki rakamların min/max.
- Render: PyMuPDF `get_pixmap`, 150 dpi (kontrast), 600 dpi (x-yüksekliği). Metinsiz sayfa:
  `add_redact_annot(page.rect)` + `apply_redactions(images=NONE, graphics=NONE)` → yalnız
  metin silinir.

## 3. Karar mekanizması (deterministik)

- **Folyo**: kesimin üst/alt %15'indeki ≤4 haneli rakam satırları; en yaygın (font, boyut)
  stili folyo stilidir; <3 folyo varsa denetim yapılmaz. Ofset = mod(numara − sayfa).
- **Kenar**: her satır için üst/alt/cilt/dış uzaklık; en yakın kenar sınırla karşılaştırılır.
  Recto = tek PDF sayfası; cilt = recto'da sol, verso'da sağ.
- **Gövde**: sayfada gövde fontlu satırlar; ≥80 glif; sayfa puntosu = en çok glifli boyut;
  satır aralığı = art arda ana punto satırlarının taban çizgisi farkı, 0,8–1,9 × punto arası,
  yatay örtüşen, ≥3 ölçüm → ortanca; kitap aralığı = punto başına ortancaların ortancası.
- **x-yüksekliği**: gövde font/boyutlu satırlardaki `xzvwunmrcsaeo` harflerinin 600 dpi
  kırpımında mürekkep satırlarının yüksekliği; ≥10 örnek gerekli, 60'ta durur; ortanca (mm).
  Alışılan değer `conventional_xheight_mm(age)`: 5 yaşta ~4 mm, 11 yaşta ~2 mm'ye doğrusal
  (Hughes & Wilkins 2000; Wilkins ve ark. 2009, J. Res. Reading 32:402), taban 2 mm.
- **Dul/öksüz**: sayfa sınırında gövde satırları (`_is_body`: satırın bir parçası gövde font ve
  boyut ±1 pt); paragraf sınırı `para_end`: cümle sonu **ve** sonraki satırda yeni paragraf
  işareti (diyalog çizgisi/tırnak, girinti > 0,6 × punto, satır sağ kenardan > 1,5 × punto kısa,
  ya da > 2,2 × punto boşluk). Paragraf sayfa sınırını aşıyorsa ve önceki/sonraki satır paragraf
  sonuysa bulgu.
- **Kontrast**: satır renk koşullarına bölünür (`_runs`, ≥2 harf); basılı render ile metinsiz
  render farkı > 40 olan pikseller «değişen»; <12 değişen piksel → `hidden`; değişenlerin fark
  değeri ≥ %60 yüzdelik olanlar glif çekirdeği → metin parlaklığı ortancası; zemin = metinsiz
  renderın x-yüksekliği bandı (taban çizgisinden 0,55 × punto yukarı). WCAG kontrast ortanca
  (`c_med`) ve en kötü %10 (`c_p10`). Büyük metin: ≥18 pt ya da ≥14 pt kalın. Sayfa + renk +
  kural başına **tek** bulgu (en kötü koşu temsil eder, `lines` sayısı yazılır).

## 4. Eşikler ve nereden okunduğu

Env/config yok; hepsi modül sabiti ya da gömülü sayı.

| eşik | değer | yer | fiziksel anlam |
|---|---|---|---|
| `SAFE_MM` | 5,0 mm | sabit | matbaa güvenli alanı (3–6 mm anılır; 5 yaygın spek) |
| `GUTTER_MM` | 10,0 mm | sabit | tutkallı ciltte 3–6 mm kaybolur + güvenli alan |
| `SIZE_TOL_PT` | 0,5 pt | sabit | okurun fark ettiği punto farkı (0,2–0,3 ölçekleme görünmez) |
| `LEAD_TOL` | 0,08 | sabit | satır aralığında %8 |
| `WCAG_NORMAL` / `WCAG_LARGE` | 4,5 / 3,0 | sabit | WCAG 1.4.3 |
| `RENDER_ZOOM` | 150/72 | sabit | 150 dpi, ≥9 pt gövdede glif maskesi için yeter |
| x-yüksekliği render | 600 dpi | `measure_xheight` | — |
| x-yüksekliği örnek | ≥10, en çok 60 | `measure_xheight` | — |
| x-yüksekliği uyarı | xh < 0,9 × alışılan | `check_age` | %10 tolerans |
| folyo bölgesi | üst/alt %15 | `_folios` | — |
| folyo yükseklik farkı | > 2,0 pt | `check_folios` | — |
| en az folyo | 3 | `check_folios` | — |
| metin sayfası | ≥80 glif gövde fontu | `check_body` | resim altı yazı değil |
| aralık ölçüm aralığı | 0,8–1,9 × punto, ≥3 ölçüm | `check_body` | — |
| gövde satırı boyut toleransı | ±1,0 pt | `_is_body` | — |
| paragraf sınırı | girinti 0,6, kısa satır 1,5, boşluk 2,2 × punto | `para_end` | — |
| değişen piksel | fark > 40 (0–255), ≥12 piksel | `run_contrast` | — |
| glif çekirdeği | fark ≥ %60 yüzdelik | `run_contrast` | kenar yumuşatma mürekkep+kâğıt karışımı |
| zemin bandı | taban − 0,55 × punto | `run_contrast` | x-yüksekliği |
| desenli zemin | `bg_lum_sd` ≥ 0,02 | `check_contrast` | resim üstü |
| büyük metin | ≥18 pt ya da ≥14 pt kalın | `measure_contrast` | WCAG |

## 5. Bulgu biçimi

`page, severity, message, quote` (satır metninin ilk 60 karakteri ya da folyo), `bbox` (satır
ya da grup kutusu, 0..1000), `suggestion` (yalnız `folio_sequence`), `details.rule` +
ölçüm alanları (`mm, limit_mm, side, size, book_size, leading, book_leading, xheight_mm,
conventional_mm, age_min, text_lum, bg_lum_med, bg_lum_sd, c_med, c_p10, color, lines,
over_picture, next_page, prev_page, printed, expected, offset`).

Stats: `pages, pages_skipped_unreliable_layer, has_trimbox, folios, folio_offset, folio_style,
margin_mm_min, margin_mm_p05, body_font, body_size, body_pages, book_leading, age_band,
body_xheight_mm, conventional_xheight_mm, widows, orphans, contrast_runs, contrast_groups,
contrast_warn, hidden, findings_by_rule (severity:rule → sayı)`.

## 6. Kendi hatası vs kitabın hatası

- Kitabın: tablodaki kurallar.
- Kendinin (sessizce atlanır, stats'a yazılır): TrimBox yok (sayfa kenarı kullanılır —
  kenar ölçümü anlamsızlaşır, `has_trimbox=false`), <3 folyo, <10 x-yüksekliği örneği, yaş bandı
  yok, güvenilmez katman. `text_hidden` sınırda: metin gerçekten resim altında olabilir (kitabın)
  ya da render/redaksiyon farkı (kendinin).
- Exception (FAILED): PDF açılamıyor, `body_style` boş (metinsiz kitap: `("", 0.0)` döner,
  sonraki adımlar boş çalışır).

## 7. ÖLÇÜM BEKLİYOR

Kodda yazılı ölçüm: `_layout_lines` glif ayıklama sayıları (bir kitapta 3.498 alfa-0, 2.706
kırpılmış). Eşiklerin hiçbiri bu külliyatta ölçülerek seçilmedi; sabitlerin yanındaki
gerekçeler literatür/spek (WCAG, matbaa güvenli alanı, Hughes & Wilkins). Kesinlik yok.

Plan:
```sh
ssh tt-gpu 'docker exec -i editor-mcp python -m editor.proofing <gen> --only layout --dry' > layout-<kitap>.json
```
1. `findings_by_rule` altı kitapta; her kural için en çok 20 bulgu sayfa görüntüsüyle
   etiketlenir (gerçek / bilinçli tasarım / ölçüm hatası).
2. `body_size`: künye, arka kapak, içindekiler sayfaları ayrı sayılır (bkz. §8-1).
3. `contrast_low` WARN'ları: renk okuması `text_lum` ile gerçek renk karşılaştırılır; kontur
   tespiti (`outlined`) kaçırdı mı.
4. `margin_safe_zone`: TrimBox'lı kitaplarda `margin_mm_p05`; TrimBox'sızlarda kural anlamsız.
5. `age_type_size`: `body_xheight_mm` ile cetvelle ölçülen basılı x-yüksekliği (bir kitap).
6. Dul/öksüz: `para_end` kararı iki sütunlu/resim çevreli sayfalarda.

## İlk gerçek koşu (2026-09-22)

«Levent Dünya Harikalarının Peşinde», nesil `60e5d717`: **78 bulgu, 66 WARN**. Öne çıkanlar:
s.3 gövde 11 pt / kitap 15 pt (`body_size`); kırmızı metin–resim kontrastı 2,8:1
(`contrast_low` WARN). İnsan doğrulaması yok; yalnız sayı.

## 8. Bilinen yanlış alarm riskleri ve açık sorular

1. **Künye sayfası `body_size`**: künye gövde fontuyla küçük puntoda dizilir ve ≥80 glif
   taşır; kural bunu «gövde metni farklı punto» diye WARN'lar (ilk koşudaki s.3 muhtemelen bu).
   `page_role` (FRONT_MATTER/NON_STORY) burada kullanılmıyor — açık karar.
2. **Kontrast, çocuk kitabında renkli metin**: kırmızı/turuncu metin resim üstünde WCAG 3:1'i
   sık geçmez; kural WCAG'ı olduğu gibi uygular, yayınevi üslubu değil.
3. **Sayfa paritesi**: `folio_parity`, kenar (recto/verso) ve dul/öksüz PDF 1. sayfayı recto
   sayar; PDF kapakla başlıyorsa cilt/dış kenar yer değiştirir.
4. **TrimBox yok**: kenar kuralı sayfa dikdörtgenine göre; taşma payı (bleed) varsa her satır
   «güvenli» görünür; yoksa her satır kesime yakın görünür.
5. **Yaş bandı kaynağı** `age_fit`'ten farklı (yalnız doğrulanmış claim); iki denetim farklı
   bant görebilir.
6. **x-yüksekliği** yalnız gövde fontunun küçük harflerinden; el yazısı/dekoratif gövde
   fontunda ölçüm sapar.
7. **`text_hidden`** redaksiyonun görünmez metni de «silmesi»yle tetiklenir: PDF'te zaten
   görünmeyen metin (`visible` süzgeci kaçırdıysa) WARN olur.
8. `check_body` `main[0].text[:60]` alıntısı sayfanın ilk gövde satırı; bulgunun kutusu tüm
   ana punto satırlarını kapsar — ekranda büyük kutu.
