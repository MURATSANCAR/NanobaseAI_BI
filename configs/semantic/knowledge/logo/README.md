# Bilgi paketi — `logo`

Semantic Layer'ın offline girdisi. Ürüne aittir; hiçbir üçüncü taraf proje düzenine bağlı değildir.

| İçerik | Ne işe yarar |
|---|---|
| `knowledge/rules,glossary,metrics,caveats/*.md` | operatör iş kuralları → **doküman kanıtı** (aday üretir, tek başına sertifika vermez) |
| `knowledge/sql/*.md`, `knowledge/pairs-export.yml` | doğrulanmış soru→SQL çiftleri → **History Miner** girdisi |
| `models/*/metadata.yml`, `relationships.yml` | veritabanı bağlantısı yokken offline profil (bootstrap/test); canlı profil varsa gerekmez |
| `knowledge/reference/logo-ldds.md` | **üretilmiştir** — Logo'nun veri sözlüğü: kod kümeleri (fiş türleri, dövizler, kolon kodları) ve Türkçe tablo/kolon açıklamaları. Elle düzenlemeyin; `backend/scripts/import_logo_ldds.py` ile yeniden üretin. |
| `knowledge/reference/` | Doc Miner okur, **isteme girmez**. 168 KB'lık bir referans her isteme eklenirse şema, katalog ve örnekler bağlamdan taşar; kodlar zaten sorunun dokunduğu kolonlar üzerinden katalogdan gelir. Aynı kural `knowledge/sql/` için de geçerli (onlar recall ile ulaşır). |

Logo veritabanı ne yabancı anahtar tanımlar ne birincil anahtar ne de kolon açıklaması yazar;
tabloların anlamı, kod kümeleri, indeksler ve join grafiği `configs/schemas/logo-ldds.json`
dosyasından gelir (aynı üreticinin çıktısı). Profiler ve şema indeksleyici bu dosyayı kendiliğinden
okur.

Üretim iki kaynaktan yapılır: `LDDS.xls` (yapının tamamı — 310 tablo, 8.900 kolon, 2.088 indeks
segmenti, 1.210 ilişki, İngilizce açıklamalar) ve Logo'nun Türkçe tablo yapısı dökümanı
(`LOGO_TABLE_YAPISI.DOC`; "Unity Veri tabanı .doc" aynı dosyadır). Döküman 129 tablonun ve ~2.800
kolonun Türkçe açıklamasını, 163 kolonun Türkçe kod etiketlerini ve workbook'ta hiç geçmeyen 20
tabloyu ekler. Sorular Türkçe geldiği için açıklamalarda Türkçe metin önde tutulur:

```
python backend/scripts/import_logo_ldds.py LDDS.xls --doc LOGO_TABLE_YAPISI.DOC
```

Kullanım: `SEMANTIC_KNOWLEDGE_DIR=configs/semantic/knowledge/logo`.
Katalog büyüdükçe paket kendinden üretilebilir: `python -m semantic_layer.cli export-knowledge --out <dir>`
(çalışma anında "doğru" denen sorgular dahil).
