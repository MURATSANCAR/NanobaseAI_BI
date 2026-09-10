# Finans & Bütçe Masası (yeni arayüz)

NanobaseAI Semantic Bridge'in (`backend/semantic_bridge`, :8795) önüne konan yönetim kokpiti.
Köprü sözleşmesi: `/api/v1/ask`, `/api/v1/run_sql`, `/api/v1/generate_summary`, `/api/v1/engine`,
`/api/v1/feedback`. Bu uygulama yalnız o uçları tüketir; istemci `src/lib/engine.ts`.

## Geliştirme

```bash
# 1) sunucudaki köprüye tünel (port yalnız 127.0.0.1'e bağlı)
ssh -N -L 8795:127.0.0.1:8795 nanobase-direct

# 2) uygulama
cd apps/cockpit && npm install && ENGINE_URL=http://127.0.0.1:8795 npm run dev   # http://localhost:5180
```

`VITE_DATA_MODE=fixture` ile motor olmadan (gerçek rakamlardan alınmış önbellekle) çalışır;
`auto` (varsayılan) önce canlıyı dener, olmazsa önbelleğe düşer ve üst çubukta **ÖNBELLEK** yazar.

## Üretim

Motor: **Semantic Layer** (`backend/semantic_layer` kataloğu + `backend/semantic_bridge` köprüsü).
Doğruluk kaynağı bi_meta'daki sertifikalı katalog; LLM yalnız katalog MISS olduğunda devreye girer.

```bash
./scripts/server/deploy-semantic-bridge.sh     # migrate + pipeline + systemd nanobase-semantic-bridge + gece worker
./scripts/server/switch-timas-api.sh semantic  # nginx /timas/api/ → :8795
VITE_BASE=/timas/ VITE_ENGINE_BASE=/timas npm run build && rsync dist/ nanobase-direct:/data/nanobaseai/bi/cockpit/dist/
```

Ayrıntılı kurulum/doğrulama/geri dönüş: `docs/architecture/semantic-bridge-runbook.md`.

## Veri kuralları (Logo, firma 411 = 2026)

`src/lib/metrics.ts` başındaki yorumda; TRCODE/LINETYPE/OUTCOST anlamları canlı veride doğrulanmıştır.

## Sunucu notları

- Gömme servisi A40 GPU'da (`nanobaseai-bi-embed.service`), LLM köprüsü `OPENAI_API_BASE` ile ayarlanır;
  Semantic Layer LLM'i yalnız katalog MISS ve karmaşık sorularda çağırır.
- Gece 02:00: `nanobase-semantic-worker.timer` profil → madencilik → sertifikasyon → sürüm; sonrasında
  köprüye `/api/v1/semantic/reload`.
- İş kuralları ve doğrulanmış soru→SQL çiftleri `configs/semantic/knowledge/logo` bilgi paketindedir;
  katalog büyüdükçe `python -m semantic_layer.cli export-knowledge --out <dir>` ile kendinden üretilir.



### Derleyici A/B (Faz 8)

```bash
# gölge mod: SuperSonic cevabı değiştirmeden yanında ölçülür
# (birim env dosyasından okur; komut satırı ön eki servise ULAŞMAZ)
sudo tee -a /etc/nanobase/semantic-bridge.env >/dev/null <<'ENV'
SUPERSONIC_BASE=http://127.0.0.1:9080
SUPERSONIC_DATASETS=INVOICE=7,STLINE=8
SUPERSONIC_MODE=shadow
ENV
sudo systemctl restart nanobase-semantic-bridge
curl -s http://127.0.0.1:8795/api/v1/semantic/ab | head -c 400      # örnek sayısı, uyuşma oranı, gecikme

# ölçüm koşusu (aynı SemanticQuery, üç derleyici, gerçek sonuç karşılaştırması)
PYTHONPATH=backend python3 tests/text2sql/compiler-ab-eval.py --store "$NANOBASE_META_DSN" \
  --compilers deterministic,existing_llm,supersonic --bridge http://127.0.0.1:8795 \
  --truth artifacts/timas/complex-truth.json --out artifacts/timas/compiler-ab.json
```
