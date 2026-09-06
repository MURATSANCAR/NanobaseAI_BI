# Bilgi paketi — `logo`

Semantic Layer'ın offline girdisi. Ürüne aittir; hiçbir üçüncü taraf proje düzenine bağlı değildir.

| İçerik | Ne işe yarar |
|---|---|
| `knowledge/rules,glossary,metrics,caveats/*.md` | operatör iş kuralları → **doküman kanıtı** (aday üretir, tek başına sertifika vermez) |
| `knowledge/sql/*.md`, `knowledge/pairs-export.yml` | doğrulanmış soru→SQL çiftleri → **History Miner** girdisi |
| `models/*/metadata.yml`, `relationships.yml` | veritabanı bağlantısı yokken offline profil (bootstrap/test); canlı profil varsa gerekmez |

Kullanım: `SEMANTIC_KNOWLEDGE_DIR=configs/semantic/knowledge/logo`.
Katalog büyüdükçe paket kendinden üretilebilir: `python -m semantic_layer.cli export-knowledge --out <dir>`
(çalışma anında "doğru" denen sorgular dahil).
