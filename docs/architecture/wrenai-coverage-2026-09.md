# WrenAI main (0.13.4) — yetenek envanteri ve kullanım durumumuz

Tarih: 2026-09-06 · Proje: `/data/nanobaseai/bi/wren-project/logo_timas` · Motor: `wrenai 0.13.4` (`core/wren`), `wren-core-py 0.7.6`

Amaç: "eksiksiz kullan" talimatına karşı, upstream'deki **her** mekanizmayı listelemek ve durumunu göstermek.

## 1. CLI komut grupları

| Komut | Ne yapar | Durum |
|---|---|---|
| `wren query` / `--sql` | MDL üzerinden SQL çalıştır | **Kullanılıyor** (köprü `run_sql`, MCP `run_sql`) |
| `wren dry-plan` | MDL SQL → hedef lehçe SQL, DB'siz | **Kullanılıyor** (MCP aracı; köprüde `dry_run` tercih edildi) |
| `wren dry-run` | Canlı DB'de doğrula, satır döndürme | **Kullanılıyor** (köprü ask akışında zorunlu adım) |
| `wren context init/validate/build/show/upgrade` | MDL proje yaşam döngüsü | **Kullanılıyor** (deploy betiği) |
| `wren context instructions` | `knowledge/rules` tam metni | **Kullanılıyor** (köprü `load_rules`) |
| `wren context import` (dbt / OSI) | dbt veya OSI semantik modelinden MDL | Kullanılmıyor — kaynağımız Logo MSSQL, dbt/OSI yok |
| `wren context set-profile` | Profil bağla | **Kullanılıyor** (`logo-tunnel`) |
| `wren profile add/list/switch/debug/import/rm` | Bağlantı profilleri (`~/.wren/profiles.yml`) | **Kullanılıyor** |
| `wren memory index/status/check/describe` | Şema+bilgi indeksi (LanceDB) | **Kullanılıyor** |
| `wren memory fetch` (get_context) | Soruya göre şema dilimi | **Kullanılıyor** (köprü istemi) |
| `wren memory recall` | Benzer NL→SQL çiftleri | **Kullanılıyor** (köprü istemi) |
| `wren memory store` | Onaylı çifti `knowledge/sql/` altına yaz | **Kullanılıyor** (kampanyanın 8 doğrulanmış çifti yazıldı) |
| `wren memory list/forget/dump/load/export/reset` | Çift yönetimi | Kullanılabilir; `list`/`check` kullanıldı, diğerleri gerektiğinde |
| `wren memory watch` | Kaynak değişince otomatik yeniden indeksle | Kullanılmıyor (deploy betiği elle indeksliyor) |
| `wren cube list/describe/query` | Ön-toplulaştırılmış küpler | **Kullanılıyor** (`sales_cube`, `line_cube`) — ölçüler doğru; kırılımlı sorgu SQL Server'da upstream hatası (bkz. docs/upstream Issue 3), kırılım için view'ler kullanılıyor |
| `wren serve mcp` | 17 araçlı MCP sunucusu | **Kullanılıyor** (`nanobase-wren-mcp` :8090) |
| `wren skills list/get` | Ajan iş akışı rehberleri (6 skill) | Rehber olarak okundu; köprü istemi bu akışı uyguluyor |
| `wren ask --guided/--direct` | İstem şekillendirme şablonu | Kullanılmıyor — köprü kendi Türkçe sistem istemini kuruyor |
| `wren docs connection-info` | Bağlayıcı alan referansı | **Kullanılıyor** (deploy betiği) |
| `wren utils parse-type/translate-type` | Tip normalizasyonu | Kullanılmıyor (tipler legacy MDL'den geldi) |
| `wren genbi build/register/verify/open/deploy` | Ajanın yazdığı statik BI uygulaması, Vercel'e deploy | Kullanılmıyor — kendi cockpit'imiz var |

## 2. Doğruluk katmanları

| Katman | Durum |
|---|---|
| MDL (model/kolon/ilişki) | **7 model, 1620 kolon, 8 ilişki** |
| Kolon/model açıklamaları | **Eklendi** (Türkçe; TRCODE/LINETYPE/OUTCOST anlamları) |
| Hesaplanmış kolonlar | **Eklendi** (`net_signed_total`, `line_cost`, `is_sale`, `invoice_month` …) |
| Views | **Eklendi** (`v_monthly_sales`, `v_channel_net`, `v_imprint_perf`) |
| Cubes | **Eklendi** (`sales_cube`, `line_cube`) |
| `knowledge/rules` | **8 kural** (TRCODE, LINETYPE, maliyet, alt sorgu, fan-out) |
| `knowledge/glossary` · `metrics` · `caveats` | **Eklendi** (sözlük, metrik tanımları, veri uyarıları) |
| `knowledge/sql` doğrulanmış çiftler | **18** (8 legacy + 2 düzeltme + 8 kampanya) |
| LanceDB memory index | **1635 şema öğesi + çiftler** |
| `dry_run` doğrulama + tek onarım turu | **Köprüde zorunlu** |
| `policy.py` salt-SELECT | **Her zaman açık** (motor içi) |
| `strict_mode` + `denied_functions` | **Açıldı ve canlı doğrulandı**: ham `dbo.LG_411_01_INVOICE` reddedildi (MODEL_NOT_FOUND), MDL modeli çalıştı. Köprü de `load_config` ile aynı ayarı okuyor |

## 3. SDK ve entegrasyon

| Bileşen | Durum |
|---|---|
| `wren` Python API (`WrenEngine`) | **Kullanılıyor** (köprü doğrudan bu API üzerinde) |
| MCP sunucusu | **Kullanılıyor** (:8090, 17 araç) |
| `wren-pydantic` (Pydantic AI toolkit) | **Kuruldu** (0.3.0 + pydantic-ai 1.107.5); 6 araçlı ajan modu için hazır |
| `wren-langchain` (LangChain/LangGraph) | Kurulmadı — Pydantic AI ile aynı işi yapar, ikisi gereksiz |
| `wren-core-wasm` | Kullanılmıyor (tarayıcı içi planlama; bizde sunucu tarafı) |
| dbt / OSI içe aktarma | Kullanılmıyor (kaynak yok) |
| GenBI uygulama üretimi | Kullanılmıyor (kendi cockpit'imiz) |

## 4. Bilinçli kullanılmayanlar (gerekçe)

- **GenBI**: ürün arayüzümüz `apps/cockpit`; GenBI Vercel'e statik uygulama atar, whitelabel kuralımıza ve mevcut portala uymaz.
- **dbt / OSI import**: elimizde dbt projesi veya OSI semantik modeli yok; MDL'yi doğrudan Logo şemasından ürettik.
- **`wren ask` şablonları**: İngilizce genel şablon; bizim Türkçe, T-SQL ve Logo kurallarına özel sistem istemimiz daha dar.
- **`wren-langchain`**: `wren-pydantic` ile örtüşüyor.
- **`memory watch`**: prod'da dosya değişimi elle deploy ile olur; otomatik yeniden indeks gereksiz yük.
- **`utils parse-type`**: tipler legacy MDL'den doğru geldi.

## 5. Env / ayar knob'ları

| Değişken | Kullanımımız |
|---|---|
| `WREN_HOME` | Varsayılan (`~/.wren`) — profil + config burada |
| `WREN_PROJECT_HOME` | Köprü ve MCP `--project` ile açık yol veriyor |
| `WREN_MEMORY_BACKEND` | Varsayılan `lancedb` (extra kurulu) |
| `WREN_EMBEDDING_MODEL` | Varsayılan `paraphrase-multilingual-MiniLM-L12-v2` (Türkçe için uygun) |
| `WREN_DB_STATEMENT_TIMEOUT` | **Ayarlanmalı** (bağlantı profiline `statement_timeout`) — uzun süren sorgular için |


## 6. Bu turda kapatılanlar (2026-09-06 gece)

| Eksik | Durum |
|---|---|
| Model/kolon açıklamaları yok → zayıf retrieval | 7 model + ~60 kritik kolon Türkçe açıklandı; indeks 1635 → **1663 şema öğesi** |
| Hesaplanmış kolon yok | `net_signed_total`, `line_cost`, `is_sale/is_sales_return/is_purchase`, `is_item_line/is_discount_line`, `invoice_month/line_month` |
| View yok | `v_monthly_sales`, `v_channel_net`, `v_imprint_perf` (build: 7 model + **3 view**) |
| Cube yok | `sales_cube` (satis, iade, net_ciro, alim, satis_fatura_sayisi), `line_cube` (brut_satir, iskonto, maliyetli_ciro, maliyet, satilan_adet) |
| glossary / metrics / caveats yok | Üçü de yazıldı (Türkçe, doğrulanmış tanımlar ve veri uyarıları) |
| strict_mode kapalı | Açıldı, köprüde de etkin, canlı test edildi |
| Onaylı cevaplar saklanmıyor | Kampanyanın 8 doğrulanmış çifti `wren memory store` ile yazıldı → **18 çift** |
| Ajan SDK yok | `wren-pydantic` kuruldu |
