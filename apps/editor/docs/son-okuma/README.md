# Son okuma denetimleri — dizin

Her denetim `src/editor/proofing/<name>.py`; belge `docs/son-okuma/<name>.md`. Koşu:
`docker exec editor-mcp python -m editor.proofing <gen> [--only <name> ...] [--dry]`.

Durum sözlüğü: **ölçüldü** = kesinlik/geri çağırma sayısı kodda ve belgede var; **kısmen** =
bazı eşikler ölçülmüş, kesinlik yok; **ölçüm bekliyor** = gerçek kitapta etiketli ölçüm yok.

| denetim | LABEL | karar | belge | durum |
|---|---|---|---|---|
| `age_fit` | Yaşa uygunluk | deterministik okunabilirlik + model hassas içerik | [age_fit.md](age_fit.md) | kısmen (referans derlemi ölçüldü; kesinlik bekliyor) |
| `appearance` | Karakter görünüşü | defter + model yargı | [appearance.md](appearance.md) | ölçüm bekliyor |
| `dialogue` | Konuşmalar | defter + model yargı | [dialogue.md](dialogue.md) | ölçüm bekliyor |
| `edition_diff` | Baskı farkı | deterministik | [edition_diff.md](edition_diff.md) | ölçülemedi (iki sürümlü kitap yok) |
| `hyphenation` | Satır sonu bölme | deterministik (TDK) | [hyphenation.md](hyphenation.md) | ölçüm bekliyor |
| `imprint_crm` | Künye | deterministik | [imprint_crm.md](imprint_crm.md) | ölçüm bekliyor |
| `layout` | Sayfa düzeni | deterministik (geometri + render) | [layout.md](layout.md) | ölçüm bekliyor |
| `name_spelling` | Ad tutarlılığı | deterministik aday + model | [name_spelling.md](name_spelling.md) | ölçüm bekliyor |
| `props` | Eşyalar | defter + model yargı | [props.md](props.md) | ölçüm bekliyor |
| `series_canon` | Dizi tutarlılığı | deterministik + CCIP | [series_canon.md](series_canon.md) | kesinlik ölçülebilir, geri çağırma ölçülemez |
| `setting` | Mekân | defter + model yargı | [setting.md](setting.md) | ölçüm bekliyor |
| `spelling` | Yazım ve noktalama | kurallar + sözlük + model | [spelling.md](spelling.md) | kısmen (boşluk/hece eşikleri ölçüldü; kesinlik bekliyor) |
| `text_contradictions` | Çelişkiler | model öneri + deterministik doğrulama + model yargı | [text_contradictions.md](text_contradictions.md) | kısmen (window okuyucusu ölçülüp kapatıldı; kesinlik bekliyor) |
| `timeline` | Zaman sırası | defter + model yargı | [timeline.md](timeline.md) | ölçüm bekliyor |
| `word_variety` | Yakın tekrar | Zemberek kök + model anlam ayrımı + model yargı; kelime haritası | [word_variety.md](word_variety.md) | kısmen (Dilek Ağacı: 122 bulgu, 866 kök; kesinlik bekliyor) |
| `word_overuse` | Sık kullanılan sözcük | G² derlem karşılaştırması + model yargı | [word_overuse.md](word_overuse.md) | kısmen (2 kitapta sayı; kesinlik bekliyor) |
| `sentence_starts` | Cümle başları | tesadüf olasılığı + model yargı | [sentence_starts.md](sentence_starts.md) | kısmen (2 kitapta sayı; kesinlik bekliyor) |
| `phrase_repeats` | Tekrarlanan söz öbeği | kök dizisi öbekleri + model yargı | [phrase_repeats.md](phrase_repeats.md) | kısmen (2 kitapta sayı; kesinlik bekliyor) |
| `word_choice` | Sözcük seçimi | model aday + cümleyle doğrulama | [word_choice.md](word_choice.md) | kısmen (2 kitapta sayı; kesinlik bekliyor) |

İlk gerçek koşu (2026-09-22, «Levent Dünya Harikalarının Peşinde», nesil `60e5d717`; insan
doğrulaması yok, yalnız sayı): layout 78 (66 WARN), spelling 21 WARN, hyphenation 20 INFO,
age_fit 4 WARN + 2 INFO, name_spelling 3 WARN, imprint_crm 0, edition_diff 1 INFO,
series_canon 1 INFO.

## İsabet nasıl ölçülür (editör kararı)

Her bulgu için editör portalda (M5 Son Okuma) «Doğru» ya da «Yanlış alarm» der; ret gerekçesi kapalı
küme (TEXT_CORRECT, INTENDED_STYLE, DICTIONARY_GAP, WRONG_PAGE, EXPLAINED_IN_TEXT, NOT_AN_ISSUE, OTHER)
+ isteğe bağlı not. Karar `ed.proof_decision` tablosuna salt-ekleme yazılır; bulgunun **geçerli** kararı
en yeni satırdır (bir karar geri alınmaz, üstüne yenisi eklenir). Uygulama kitabı değiştirmez.

**Kural = denetim adı + sürümü.** İsabet, BÜTÜN kitaplardaki geçerli kararlardan sayılır — kuralın
isabeti kitaba özel değildir:

```sql
WITH gecerli AS (
  SELECT DISTINCT ON (finding_id) check_name, check_version, verdict
  FROM ed.proof_decision ORDER BY finding_id, created_at DESC)
SELECT check_name, check_version,
       count(*) FILTER (WHERE verdict='ACCEPT') AS dogru,
       count(*) FILTER (WHERE verdict='REJECT') AS yanlis_alarm,
       round(100.0*count(*) FILTER (WHERE verdict='ACCEPT')/count(*),1) AS isabet_yuzde
FROM gecerli GROUP BY 1,2 ORDER BY 1,2;
```

`isabet = doğru / (doğru + yanlış alarm)`; karar yoksa ölçü yok («henüz karar yok»). Kural değişince
`VERSION` artar ve yeni sürüm sıfırdan sayar; eski sürümün ölçüsü karşılaştırma için durur. Ret
gerekçelerinin dağılımı (`reason_code`) kuralın hangi yönde yanıldığını gösterir: DICTIONARY_GAP
yığılıyorsa sözlük, WRONG_PAGE yığılıyorsa kanıt eşleme, EXPLAINED_IN_TEXT yığılıyorsa yargı aşaması.

Kart servisi: `GET /v1/books/{id}/proofing` her denetimde `precision {accepted, rejected, rate}` ve her
bulguda `decision`; `POST …/findings/{id}/decision` tek yazma ucu (editörün kaydı). Köprü:
`POST /api/v1/editorial/proofing/decision`, karar veren = oturum kullanıcısı, `semantic_audit`'e düşer.

İlk karar (2026-09-23, test): «Baskılar arası fark» INFO bulgusuna timasai önce REJECT (TEXT_CORRECT,
«deneme — test kararı»), sonra ACCEPT verdi — akış doğrulaması; içerik kararı değildir.

## Bulgu metni (editörün ve yazarın dili)

Bütün bulgu metinleri tek yerde: `src/editor/proofing/_messages.py` (tür → şablon). Kalıp: **ne sorun** (sade cümle)
+ **nerede** (sayfa, satır, alıntı) + **neden önemli** (yarım cümle) + **ne yapılabilir** (somut öneri). Ana metinde
teknik terim, kısaltma, standart adı, renk kodu, oran yazımı yok; sayısal ayrıntı ayrı `detail` alanında ve orada da
sade dille («Okunurluk oranı 2,4; en az 3, küçük yazıda en az 4,5 olmalı.»). Renkler adıyla (renk kodu → genel
Türkçe renk adı eşlemesi, `color_name`), sayılar Türkçe (2,4 · 27.748), «CRM» yerine «yayınevi kaydı».

- Denetim bulguyu kurar (sayfa, önem, alıntı, kutu, `details`, ham öneri), metni `_messages.put(NAME, bulgu)` doldurur;
  hikâye/künye/dizi gibi öneri cümlesi taşıyan türlerde `advice=True` öneriyi de şablondan yazar. Denetim modülünde
  metin (f-string) yazılmaz; yeni bulgu türü = `_messages`'ta şablon + `tests/test_proof_messages.py`'de örnek.
- Metin kayıtlı alanlardan kurulduğu için kart servisi rapor okunurken yeniden üretir (`/proofing`: `message`,
  `suggestion`, `detail`; `export.docx`): **eski raporlar da yeni dille görünür**, veritabanındaki eski metin
  değişmez. Eski bir kayıtta alan yoksa eski metnin kendi kalıbından okunur (`_old_fields`: özet bulguları, eski
  künye/dizi türleri, hassas içerik gerekçesi); o da yoksa kayıtlı metin olduğu gibi döner (`fresh=False`,
  `missing=[alan]`). 2026-09-27: GPU'daki 38.779 bulgunun hepsi şablondan üretildi.
- Tür anahtarı `kind_of(check, bulgu)` («layout:contrast_low»): metne değil kayıtlı alanlara dayanır (künye ve dizi
  bulgularında `details.issue`). Bulgunun parmak izi metne dayanmamalı: alıntı + bu anahtar.
- Önem: ekranda «hata / uyarı / bilgi»; Word yorumunun başında «Mutlaka düzeltin / Bakmanız önerilir / Bilginize».
- İstisna: `age_fit.readability/sensitive`'in kendi `message`'ı stüdyonun yaş raporu içindir (`production/age_report`
  bulgu kimliğini o metinle kuruyor) ve değişmedi; son okumaya giden metin `age_fit.run()`'da şablondan.

## Word'e aktarım

`GET /v1/books/{id}/proofing/export.docx` (kart servisi; `_export_docx.py`): kitabın okunan metni, bulgular
Word yorumu (yazar «Zeki AI»). Yorum: `<önem> — <denetim adı>` / `s. N — <sade metin>` / `Öneri: …` / en sonda
parantez içinde tek satır ayrıntı; metin ekrandakiyle aynı (`_messages.word_comment`). «Yanlış alarm» denenler
hariç; yeri bulunamayan bulgu sayfa başlığına bağlanır («Metinde tam yeri bulunamadı…»), hiçbiri düşmez. Köprü
`GET /api/v1/editorial/proofing/export.docx?bookId=`, Son Okuma panelinde «Word'e aktar».
