# Görev: kök neden teşhisi ve yama önerisi (kod DEĞİŞTİRMEDEN)

Türkçe doğal dil → SQL üreten BI köprüsünde tam kapı (`tests/text2sql/answer-gate.py`, 69 altın soru × 3 tekrar) bazı soruları
BOZUK/KARARSIZ buldu. Sana bir kök neden grubu veriliyor. İşin: nedeni KODDA bul, **genel** bir düzeltme tasarla, yamayı
öner. Kurmak, servis yeniden başlatmak ve kapıdan geçirmek ana oturumun işidir — sen yapma.

## Bağlayıcı kurallar
- **Soruya özel çözüm yasak.** Kitap/soru/kelime/tablo adıyla istisna, elle SQL, kalıp, katalog kaydı ya da kural belgesi satırı
  önerme. Düzeltme bir HATA SINIFINI kapatmalı; raporda o sınıfı ve başka hangi soruları etkileyebileceğini (iyi/kötü) yaz.
- Çalışma ağacındaki hiçbir dosyayı değiştirme, commit yapma, sunucuya dosya kopyalama, servis yeniden başlatma, kataloğa/kurala yazma.
  Yamanı kendi kopyanda hazırla: `mkdir -p /private/tmp/claude-501/diag-<grup> && cp -R backend /private/tmp/claude-501/diag-<grup>/backend`,
  orada düzenle, sonra `diff -ru backend /private/tmp/claude-501/diag-<grup>/backend > /private/tmp/claude-501/diag-<grup>/patch.diff`
  (çalışma dizininden, böylece yollar `backend/...` ile başlar). Python sözdizimini `python3 -c "import ast,sys; ast.parse(open(sys.argv[1]).read())" dosya` ile doğrula.
- Yerelde test/servis çalıştırma (proje kuralı: Mac'te işlem yok). Gözlem için sunucuyu SALT OKUNUR kullan:
  - Çözücü okuması (model yok, serbestçe): `POST http://127.0.0.1:8795/api/v1/semantic/resolve` `{"question": "..."}`, başlık `X-Semantic-Caller`.
  - Gerçek soru (`/api/v1/ask`): soru başına EN ÇOK 2 kez (model ve müşteri veritabanı paylaşımlı).
  - Köprü günlüğü: `ssh nanobase-direct 'sudo journalctl -u nanobase-semantic-bridge --since "-3 hours" --no-pager | grep -F "<soru başı>"'`
    (model ne yazdı, kapı neyi reddetti, seçici neyi tuttu). Son tam kapı koşusu 18.09 ~18:30–21:00 UTC arasıydı.
  - Önceki cevaplar: `sl_query_log` (soru, sql_text, answer_type, row_count, gate_json, created_at).
  Çağrı iskeleti (betiği scratch'e yaz, ssh ile stdin'den ver):
  ```bash
  ssh -o ConnectTimeout=15 nanobase-direct 'export T=$(sudo grep -E "^SEMANTIC_CALLER_TOKEN=" /etc/nanobase/semantic-bridge.env | cut -d= -f2-); python3 -' < betik.py
  ```
  ```python
  import json, os, urllib.request
  def call(path, body):
      req = urllib.request.Request("http://127.0.0.1:8795"+path, data=json.dumps(body).encode(),
            headers={"X-Semantic-Caller": os.environ["T"], "Content-Type": "application/json"})
      return json.load(urllib.request.urlopen(req, timeout=900))
  ```
  Katalog/log veritabanı: `DSN=$(sudo grep -E "^SEMANTIC_STORE_DSN=" /etc/nanobase/semantic-bridge.env | cut -d= -f2- | sed "s/+psycopg2//"); psql "$DSN" -Atc "..."` (yalnız SELECT).
- Parola, token, bağlantı dosyası içeriği yazdırma.

## Kod haritası
- `backend/semantic_layer/runtime/resolver.py` — soruyu katalog kavramlarına eşler (slot, kırılım, niteleyici, kaynak seçimi `_leave_other_source_to_model` civarı, satır sınırı/sıralama sayısı okuması).
- `backend/semantic_layer/runtime/compiler.py` — deterministik derleyici (`plan`, `compile`), LLM derleyici (`build_messages`, istem, `rules_for`), iki kaynaklı plan.
- `backend/semantic_layer/runtime/audit.py` — kapı: üretilen SQL sorunun yükümlülüklerini karşılıyor mu (`gate_report`, `_condition_holds`, referans kuralı).
- `backend/semantic_layer/runtime/critic.py` — eleştirmen: çoğalan toplam, çapraz birleştirme, anahtar uyuşmazlığı (`review`).
- `backend/semantic_layer/runtime/federated.py`, `absence.py`, `periods.py`, `table_selector.py`; köprü `backend/semantic_bridge/app.py` (`Runtime.ask`).
- Altın sorular ve referanslar: `tests/text2sql/answers-set100.json` (her girişte `note`: ajanın bulduğu fark). Son rapor: `tests/text2sql/reports/answer-gate-2026-09-18.log`.
- Bugünün günlüğü (yapılanlar, ölçümler): `docs/GELISTIRME-GUNLUGU.md` en üstteki 18 Eylül girişleri. Bekleyen iş kararları: `docs/TIMAS-IS-KARARLARI-BEKLEYEN.md` —
  bir sorunun doğru cevabı oradaki bir karara bağlıysa tahmin etme; "iş kararı bekliyor" de ve güvenli davranışı (netleştirme sormak / okumayı cevapta söylemek) öner.

## Çıktı
`/private/tmp/claude-501/diag-<grup>/REPORT.md` (Türkçe) ve varsa `patch.diff`. Raporda, her soru için: (1) gözlenen davranış ve kanıt (log satırı / resolve çıktısı),
(2) kök neden — dosya:satır, (3) önerilen genel düzeltme ve kapattığı hata sınıfı, (4) risk: hangi başka okumaları değiştirebilir, hızlı kapıda (`tests/text2sql/resolver-gate.py`)
ne görmeyi beklersin, (5) düzeltme kod değil de veri/kural/iş kararı gerektiriyorsa açıkça öyle yaz. Son mesajında 10–15 satırlık özet ver: soru → kök neden → yama var/yok → güven düzeyi.
