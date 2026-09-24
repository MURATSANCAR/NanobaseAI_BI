# Son okuma denetimleri — dizin

Her denetim `src/editor/proofing/<name>.py`; belge `docs/son-okuma/<name>.md`. Koşu:
`docker exec editor-mcp python -m editor.proofing <gen> [--only <name> ...] [--dry]`.

Durum sözlüğü: **ölçüldü** = kesinlik/geri çağırma sayısı kodda ve belgede var; **kısmen** =
bazı eşikler ölçülmüş, kesinlik yok; **ölçüm bekliyor** = gerçek kitapta etiketli ölçüm yok.

| denetim | LABEL | karar | belge | durum |
|---|---|---|---|---|
| `age_fit` | Yaş uygunluğu | deterministik okunabilirlik + model hassas içerik | [age_fit.md](age_fit.md) | kısmen (referans derlemi ölçüldü; kesinlik bekliyor) |
| `appearance` | Görünüş sürekliliği | defter + model yargı | [appearance.md](appearance.md) | ölçüm bekliyor |
| `dialogue` | Diyalog atfı ve ses | defter + model yargı | [dialogue.md](dialogue.md) | ölçüm bekliyor |
| `edition_diff` | Baskılar arası fark | deterministik | [edition_diff.md](edition_diff.md) | ölçülemedi (iki sürümlü kitap yok) |
| `hyphenation` | Satır sonu heceleme | deterministik (TDK) | [hyphenation.md](hyphenation.md) | ölçüm bekliyor |
| `imprint_crm` | Künye — CRM karşılaştırması | deterministik | [imprint_crm.md](imprint_crm.md) | ölçüm bekliyor |
| `layout` | Sayfa düzeni | deterministik (geometri + render) | [layout.md](layout.md) | ölçüm bekliyor |
| `name_spelling` | Ad yazımı tutarlılığı | deterministik aday + model | [name_spelling.md](name_spelling.md) | ölçüm bekliyor |
| `props` | Eşya sürekliliği | defter + model yargı | [props.md](props.md) | ölçüm bekliyor |
| `series_canon` | Dizi tutarlılığı | deterministik + CCIP | [series_canon.md](series_canon.md) | kesinlik ölçülebilir, geri çağırma ölçülemez |
| `setting` | Mekân tutarlılığı | defter + model yargı | [setting.md](setting.md) | ölçüm bekliyor |
| `spelling` | Yazım ve noktalama | kurallar + sözlük + model | [spelling.md](spelling.md) | kısmen (boşluk/hece eşikleri ölçüldü; kesinlik bekliyor) |
| `text_contradictions` | Metin içi çelişki | model öneri + deterministik doğrulama + model yargı | [text_contradictions.md](text_contradictions.md) | kısmen (window okuyucusu ölçülüp kapatıldı; kesinlik bekliyor) |
| `timeline` | Zaman çizelgesi | defter + model yargı | [timeline.md](timeline.md) | ölçüm bekliyor |
| `word_variety` | Kelime çeşitliliği ve yakın tekrar | Zemberek kök + model anlam ayrımı + model yargı; kelime haritası | [word_variety.md](word_variety.md) | ölçüm bekliyor |

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
