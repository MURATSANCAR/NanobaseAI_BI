# Fable Tasarımı: Sözleşme-Temelli Doğal Dil → Veri Sistemi (2026-08-11)

Bu doküman, "uzak bir DB bağlansın, sistem onu anlasın, kullanıcı günlük dille
sordukça doğru veri gelsin" hedefi için sıfırdan tasarım yapılsaydı sistemin
nasıl kurulacağını tanımlar; sonunda mevcut kodla madde madde mutabakat
(conformance) haritası verir. `remote-db-nl-blueprint.md` faz/iş planıdır; bu
doküman onun **mimari anayasasıdır**.

---

## 1. Temel aksiyom

> **Hiçbir bileşen tahmin etmez. Ya doğrulanmış bilgiyle hareket eder ya da
> görünür şekilde reddeder.**

Bu aksiyom keyfi değil; bu kod tabanında aynı ihlal deseninin altı kez,
ölçülmüş zararla tekrarlandığı kanıtlandı:

| # | İhlal (tahmin + sessiz devam) | Ölçülmüş zarar |
|---|---|---|
| 1 | Compiler status kolonunu bilmiyordu, İngilizce `"status"` tahmin etti | 777 yayınlı erp senaryosunun 219'u her çalıştırmada patlayan SQL ile yayında |
| 2 | Prompt bütçesi şema bloğunu satır ortasından kesti, model devam etti | Uydurma kolon adları → `COLUMN_NOT_FOUND` kaskadları |
| 3 | Retrieval altyapısı çöktü, sistem boş şemayla sessizce devam etti | Aylarca fark edilmeden şemasız SQL üretimi (fail-open) |
| 4 | Önbellek bellek kopyasına güvendi, DB gerçeğini kontrol etmedi | Yanlış öğrenilmiş SQL, restart'a kadar tüm kullanıcılara süresiz servis |
| 5 | Deterministik SQL, koda gömülü izin listesinde olmayan view'e çarptı | Determinizm sessizce LLM repair döngüsüne düştü |
| 6 | "Ciro" kelimesi bağlamsız regex ile çözümlendi; tarih penceresi sessizce varsayıldı | Faturalanmış tutar ↔ satış geliri karışması; "toplam" sorusuna "bu yıl" cevabı |

Altısının ortak kökü: **bilginin tek, doğrulanmış bir kaynağı yoktu** ve
bileşenler eksik bilgide durmak yerine uydurup devam etti.

## 2. Çekirdek kavram: Veri Kaynağı Sözleşmesi (Datasource Contract)

Her bağlı veri kaynağı için, sistemin o kaynak hakkında bildiği **her şeyin**
tek, versiyonlu, kanıt-damgalı kaydı. Çalışma zamanındaki hiçbir bileşen ham
tahminle çalışmaz; yalnız sözleşmeden okur.

### 2.1 İçerik şeması

```jsonc
{
  "datasourceId": "erp",
  "contractVersion": 7,                  // her yeniden taramada artar
  "schemaFingerprint": "sha256:…",       // fiziksel şemanın parmak izi
  "createdAt": "…", "publishedAt": "…",
  "physical": {                          // SCANNER üretir — kanıt: information_schema
    "tables": [{
      "fqn": "public.faturalar",
      "type": "BASE TABLE",
      "rowCountApprox": 125000,
      "columns": [{
        "name": "durum",
        "type": "text",
        "nullable": false,
        "role": "STATUS",              // CLASSIFIER üretir: MEASURE|DIMENSION|DATE|STATUS|ID|…
        "enumValues": ["odendi","acik","iptal"],   // PROFILER üretir (örneklem)
        "piiFlag": false                            // ANNOTATOR önerir, insan onaylar
      }],
      "primaryKey": ["id"], "foreignKeys": […]
    }]
  },
  "semantic": {                          // ANNOTATOR taslağı + insan onayı
    "tables":  [{ "fqn": "public.faturalar", "businessName": "Faturalar",
                  "description": "…", "synonyms": ["fatura","invoice"],
                  "provenance": "human_approved" }],
    "columns": [{ "fqn": "public.faturalar.durum", "businessName": "Fatura Durumu",
                  "valueMap": {"iptal": "CANCELLED"}, "provenance": "llm_draft" }],
    "metrics": [{ "code": "toplam_fatura_tutari", "…": "…",
                  "provenance": "human_approved" }]
  },
  "policy": {                            // GÜVENLİK — koddan değil sözleşmeden
    "allowedTables": ["public.faturalar", "…"],   // scan çıktısından türetilir
    "maskedColumns": ["public.musteriler.tckn"],
    "costCeilings": { "maxEstimatedRows": 5000000 }
  }
}
```

### 2.2 Provenance (kanıt) modeli
Her semantik olgu üç durumdan birindedir ve durum, olgunun **nerede
kullanılabileceğini** belirler:

| Provenance | Üretici | Kullanım izni |
|---|---|---|
| `scanned` | information_schema / profiler | Her katman (fiziksel gerçek) |
| `llm_draft` | Offline annotator LLM | Yalnız inceleme ekranı — **çalışma zamanı asla** |
| `human_approved` | İnceleme ekranından onay | Her katman (K1 dahil) |

LLM canlı soru yolunda şema *yorumlamaz*; yorum bir kez, offline üretilir,
insan onaylar, sonra sonsuza dek deterministik kullanılır.

### 2.3 Versiyon ve bayatlama değişmezi (freshness invariant)
- Sözleşmeden türeyen her yapıt (Qdrant indeksi, senaryo, metrik derlemesi,
  prompt şema bloğu) üretildiği `contractVersion`'ı damgalar.
- Periyodik yeniden tarama fingerprint farkı bulursa `contractVersion+1`
  yayınlanır ve **etkilenen kolon/tabloya bağlı tüm yapıtlar otomatik STALE**
  olur (mevcut `mark_stale_by_column` genelleştirilir). Elle "bayat mı acaba?"
  denetimi bir onarım aracıdır (bkz. `revalidate_scenarios.py`), rejim değil.

## 3. Cevap merdiveni ve kesinlik sınıfı

```
K1  DOĞRULANMIŞ   senaryo şablonu / metrik derlemesi   LLM yok, bayt-özdeş SQL
K2  ÖNBELLEK      geçmişte başarılı Q→SQL              her okumada DB'ye karşı doğrulanır
K3  YORUM         LLM üretimi                          şema-RAG + guard + repair + cost-guard
```

Kurallar:
1. **Terfi esastır**: tekrar eden K3 kalıbı incelemeyle K1'e taşınır. KPI:
   cevapların LLM'siz oranı (determinism coverage).
2. **Kesinlik sınıfı kullanıcıya görünür**: her cevap kartı kaynağını taşır
   (`sql_source` zaten var; FE rozetleşir). Kullanıcı yeşile güvenmeyi,
   sarıyı kontrol etmeyi öğrenir — güven arayüzde inşa edilir.
3. **Aşağı düşüş serbest, yukarı sıçrama yasak**: K1 derleyemiyorsa K3'e
   düşmek güvenlidir; K3 çıktısı incelemesiz K1 sayılamaz.

## 4. Bileşenler: girdi → çıktı → hata semantiği

| Bileşen | Girdi | Çıktı | Eksik bilgide davranış |
|---|---|---|---|
| **Prober** | bağlantı bilgisi (+Vault ref) | erişim raporu (RO doğrulaması) | RW yetki görürse **reddeder** (bağlamaz) |
| **Scanner** | canlı DB | `physical` bölümü | erişemediği şemayı listeler, sessiz atlamaz |
| **Profiler** | tablo örneklemleri (PII filtreli) | enumValues, rowCount, tarih aralıkları | örnekleyemediğini `unprofiled` işaretler |
| **Classifier** | kolon adı+tip+örnekler | `role` ataması | emin değilse `role: UNKNOWN` — asla varsayılan atamaz |
| **Annotator (LLM, offline)** | physical+profil | `llm_draft` açıklama/eş-anlamlı/PII önerisi/metrik adayı | üretemediğini boş bırakır; **hiçbir çıktısı incelemesiz canlıya çıkmaz** |
| **Reviewer (insan, FE)** | draft'lar | `human_approved` olgular | onaylanmayan draft kalır, süresi dolan draft arşivlenir |
| **Contract Store** | yukarıdakiler | versiyonlu sözleşme | tek yazar onboarding sagası; çalışma zamanı salt-okur |
| **Index (Qdrant)** | sözleşme | şema/paraphrase embed | boş/erişilemez → K3 **görünür kısıtlı mod** (bkz. §6) |
| **Scenario Builder** | sözleşme | doğrulanmış SQL şablonları | plan sözleşmede karşılıksızsa **o senaryoyu reddeder**, build sürer |
| **Metric Compiler** | yayınlı metrik + sözleşme | bayt-özdeş SQL | bilinmeyen kolon/rol → `CompilerColumnUnknown` fırlatır |
| **Resolver** | soru + yayınlı katalog | (metrik, boyut, limit) veya `None` | eşik altı/çok-aday → `None` (K3'e düş) |
| **Gateway** | SQL + sözleşme policy | sonuç | politika ihlali → tipli hata; asla kısmi sonuç |
| **Eval Loop** | golden korpus + canlı sistem | accuracy/KPI raporu | gerileme → alarm; sessiz geçiş yok |

## 5. Onboarding sagası (durum makinesi)

```
CONNECT → PROBE → SCAN → PROFILE → CLASSIFY → INDEX → DERIVE_POLICY
   → ANNOTATE(llm_draft) → REVIEW(insan) → CONTRACT_PUBLISH(v1)
   → BUILD(senaryolar) → SEED_EVAL(soru üretiminden korpus) → ACTIVATE
```

- Her adım idempotent, `onboarding_state`'e yazar, kaldığı yerden devam eder
  (mevcut senaryo staged_pipeline deseni).
- `REVIEW` insan kapısıdır; atlanamaz. Onaysız kaynak `ACTIVATE` olamaz.
- `ACTIVATE` çalışan servislere sözleşmeyi yükletir (bugünkü "restart şart"
  dersi burada otomatikleşir).

## 6. Hata görünürlüğü matrisi (fail-visible)

| Durum | Yasak davranış (eski) | Zorunlu davranış |
|---|---|---|
| Retrieval/Index çökük | boş şemayla LLM'e devam | Cevap kartında "şema bağlamı doğrulanamıyor — sınırlı mod" + yalnız K1/K2 cevaplanır, K3 kapalı |
| Sözleşmede kolon yok | ad tahmini | derleme reddi → alt katmana düş |
| Önbellek-DB uyuşmazlığı | belleğe güven | DB kazanır, bellek düşer |
| Politika dışı tablo | LLM'e tamir ettir | tipli hata + kullanıcıya dürüst mesaj |
| Zaman penceresi belirsiz | sessiz "bu yıl" | tüm-zaman cevapla; pahalıysa cost-guard tarih sorar |
| Metrik belirsiz (ciro ↔ fatura) | ilk eşleşen | çift-aday → K3'e düş veya kullanıcıya seçenek |

## 7. Sürekli doğrulama döngüsü

Gecelik, kaynak başına: fingerprint tarama → drift raporu → etkilenen yapıt
revalidasyonu (EXPLAIN) → execution-accuracy eval (`--compare-baseline`,
gerileme=alarm) → determinism-coverage KPI. Kullanıcı geri bildirimi (👍 +
`sql_source`) terfi kuyruğunu besler; terfi daima incelemelidir.

---

## 8. Mevcut sistemle mutabakat haritası

Durum: ✅ uyumlu (bugün yapıldı dahil) · 🔶 kısmi · ❌ aykırı (planlı iş)

| Tasarım ilkesi | Mevcut durum | U | Yapılan / yapılacak |
|---|---|---|---|
| Compiler tahmin etmez | `CompilerColumnUnknown` + jenerasyonda `_stamp_status_columns` (her iki üreteç) | ✅ | **Bugün yapıldı** — commit'lenecek; erp yeniden build'i doğru `durum` kolonuyla üretecek |
| Build'de tek senaryo hatası build'i öldürmez | `stage_sql_compilation` senaryo-başına REJECTED + devam | ✅ | **Bugün yapıldı** |
| Yayınlı yapıtlar canlı şemaya karşı kanıtlı | `revalidate_scenarios.py` (EXPLAIN, literal bind, hata taksonomisi) — erp: 219 schema_error, sigorta: 441/441 temiz | ✅ | Araç var; **219 STALE işaretlemesi bu deploy'da**; gecelik cron Faz 4'te |
| Önbellek DB gerçeğine tabi | learned_query_cache `_fetch_exact` + TTL re-sync | ✅ | Önceki oturumda yapıldı |
| K1 metrik katmanı (GROUP BY/TOP-N dahil) | MetricCompiler genişletildi, 2 metrik canlı | ✅ | Önceki oturumda yapıldı |
| Fail-open retrieval yasak | `schema_retrieval_degraded` uyarısı var; K3'ü kapatan "sınırlı mod" yok | 🔶 | Blueprint Faz 1.3 — degraded modda K3 kapatma + FE banner |
| İzin listesi sözleşmeden | `allowed_tables` alanı destekli ama bi_reporting kodda sabit | ❌ | Blueprint Faz 0.3 — scan çıktısından datasource kaydına |
| Resolver katalogdan | ciro/adet çözümü kodda regex | ❌ | Blueprint Faz 3.1 — `SEMANTIC_RESOLVER_MODE` bayraklı geçiş |
| Sözleşme tek yapı olarak | bilgi dağınık: Qdrant + sc_* + secrets + kod sabitleri | ❌ | Blueprint Faz 1-2'nin birleştirme hedefi; contract v1 = mevcut kayıtların çatısı |
| Annotator + insan kapısı | yok (`TABLE_DESCRIPTIONS` elle sözlük) | ❌ | Blueprint Faz 2 |
| Kesinlik sınıfı FE'de görünür | `sql_source` payload'da var, rozet yok | 🔶 | Küçük FE işi, Faz 4.2 ile |
| Drift → otomatik STALE | `mark_stale_by_column` yalnız semantic_catalog'da | 🔶 | Faz 1.3'te senaryo/indeks kapsamına genişletme |
| Sözleşme yüklemesi restart'sız | store'lar boot'ta hydrate; değişiklik restart ister | ❌ | Faz 1.1 ACTIVATE adımı; kısa vadede runbook kuralı |

Bu haritadaki her ❌/🔶 satırı `remote-db-nl-blueprint.md`'de faz/iş olarak
mevcuttur; iki doküman birlikte okunmalıdır.
