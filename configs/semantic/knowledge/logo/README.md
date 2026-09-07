# Bilgi paketi — `logo`

Semantic Layer'ın offline girdisi. Ürüne aittir; hiçbir üçüncü taraf proje düzenine bağlı değildir.

| İçerik | Ne işe yarar |
|---|---|
| `knowledge/rules,glossary,metrics,caveats/*.md` | operatör iş kuralları → **doküman kanıtı** (aday üretir, tek başına sertifika vermez) |
| `knowledge/sql/*.md`, `knowledge/pairs-export.yml` | doğrulanmış soru→SQL çiftleri → **History Miner** girdisi |
| `models/*/metadata.yml`, `relationships.yml` | veritabanı bağlantısı yokken offline profil (bootstrap/test); canlı profil varsa gerekmez |
| `knowledge/glossary/logo-ldds-codes.md` | **üretilmiştir** — Logo'nun veri sözlüğündeki kod kümeleri (fiş türleri, dövizler, kolon kodları). Elle düzenlemeyin; `backend/scripts/import_logo_ldds.py` ile yeniden üretin. |

Logo veritabanı ne yabancı anahtar tanımlar ne de kolon açıklaması yazar; tabloların anlamı ve join
grafiği `configs/schemas/logo-ldds.json` dosyasından gelir (aynı üreticinin çıktısı). Profiler ve
şema indeksleyici bu dosyayı kendiliğinden okur.

Kullanım: `SEMANTIC_KNOWLEDGE_DIR=configs/semantic/knowledge/logo`.
Katalog büyüdükçe paket kendinden üretilebilir: `python -m semantic_layer.cli export-knowledge --out <dir>`
(çalışma anında "doğru" denen sorgular dahil).
