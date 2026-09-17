# V13 web adayı: küçük bölge, bağlam ve konuşma kaynakları

18 Eylül 2026. Linux sunucusunda ayrı aday dizininden npm kilitli kurulum, TypeScript/Vite build ve Docker image build geçti. Aktif web/Compose/env değiştirilmedi; yerel test çalıştırılmadı.

- Aday dizini: `/data/nanobaseai/editor/runtime/candidates/web-source-analysis-v13-r1`.
- İmaj: `nanobase-editor-web:source-analysis-v13-r1-20260918`.
- İmaj içerik kimliği: `sha256:b2cc5fa05dadd460491a3e7f367a5f5f383c073f392a32e438f143cd1db97baf`.
- Kaynak manifest SHA256: `84ec58fc2dbf647598411417b5496a969b5b5870354fb12e29601f6c001b83d6`.
- İmajdan okunan build manifest ile 9 kaynak ve 3 çıktı dosyasının gerçek bayt hashleri eşleşti.
- Kanıtlar: ana kurulum `evidence/web-source-analysis-v13-r1-build.log` ve `evidence/web-source-analysis-v13-r1-candidate.json`.

Bu aday dört yeni API kayıt türünü ister: source_fragments, fragment_checks, page_context_roles, cross_page_attributions. Bu enum desteği olmayan eski backend üzerine dağıtılmaz. Küçük bölge ham metni/okuyucusu ve değişmeyen ilk satır ayrı gösterilir; kaynak kutuları ayrı seçilebilir. Sayfa amacı otomatik sınıflandırmadır. Doğrulanmış konuşma bağlantısı yalnız desteklenen söz parçası ve konuşmacıyla gösterilir; figürün bütün kimliği veya global karakter birliği kabul edilmez.

V12 neslinin canlı API kayıtları bu kontrolde figure_identity=0, semantic_reviews=0, semantic_synthesis=0 idi. Boş kayıtlar dolu kart kabulü sayılmadı; V12 anlamsal kartların pozitif UI kabulü DOĞRULANAMADI.

## Gerçek V13 kayıtları oluştuğunda kabul

Aşağıdaki komut hedef Linux'ta, V13 backend ve bu web imajı dağıtıldıktan sonra çalıştırılır. RUN_FILE yerine gerçek V13 API koşusunun kanıt dosyası kullanılır. Sonuç eksikse beklenen cevap/sahte kayıt üretilmez; ilgili pozitif senaryo doğrulanamadı kalır.

```sh
EDITOR_VERIFY_RUN_FILE=evidence/RUN_FILE.json \
EDITOR_VERIFY_FRAGMENTS=1 \
EDITOR_VERIFY_CONTEXT_DIALOGUE=1 \
EDITOR_VERIFY_OUTPUT_DIR=evidence/review-ui-v13-source \
node scripts/verify-review-ui.cjs
```

Fragment kontrolü gerçek TEXT_AGREED küçük bölgeyi ve gerçek parent kaydını şart koşar; ham metin, okuyucu, ilk satır, her iki bbox navigasyonu ve 320/390/768/1440 px taşma kontrol edilir. Context/dialogue kontrolü gerçek bağlam kaydı ve en az bir dialogue_link_verified bağlantıyı şart koşar; konuşmacı/alınan söz API ile birebir karşılaştırılır ve kaynak sayfasına dönüş sınanır. Bütün sekmeler ve logout kontrolleri aynı koşuda kalır.

V12/V13 semantic kartlarında gerçek dolu kayıt oluştuğunda ayrı çıktı klasörüyle `EDITOR_VERIFY_SEMANTIC=1` kullanılır. Bu bayrak gerçek identity.links, review.candidate_count ve synthesis.statements ister. Build/hash doğrulaması tarayıcı, kitap anlamı veya üretim kabulünün yerine geçmez.
