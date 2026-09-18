# V16 sayfa kaynak defteri ara kabulü

`verify-source-unit-pages.py` gerçek uzak API ve bağımsız PostgreSQL üzerinden tamamlanmış `page_claims` kayıtlarını denetler. V4 kaynak birimleri için kaynak metni/ref/hash ve kapsam defterine ek olarak amaç kaydının SHA'sı, komşu kaynaklardan yeniden kurulan amaç girdi hash'i, adaydan önce sınıflandırma bayrakları ve PG oluşturulma sırası doğrulanır. `character_evidence.page_role`, `page_claims.page_role` ve geçmiş amaç kapısının rolü karşılaştırılır. Amaç geçmezse UNKNOWN ve boş adaylar korunmalıdır.

R5 gerçek tam koşu nesli `116bb4a8-b7b5-45dd-9986-ac80fd706533` için CPU'da ayrı hafif salt okunur izleyici başlatıldı. Her on tamamlanmış sayfa bir kez API/PG denetiminden geçer; henüz oluşmayan iddia sayfası başarısız sayılmaz. Son parti, nesil terminal duruma ulaştığında ondan az sayfayı da kapsar. Teknik hata olursa başarısız kanıt korunup bu izleyici durur; kitap kaydı veya inceleme kararı değiştirilmez. Bu işlem ana optik/semantik koşuyu çoğaltmaz ve model çağırmaz.

Uzak runtime: `/data/nanobaseai/editor/runtime/editor-page-ledger-monitor.py`; log `evidence/v16-r5-page-ledger-monitor.log`; parti kanıtlarının listesi `evidence/v16-r5-page-ledger-monitor.json`. Henüz parti sonucu yokken bu belge kabul iddiası değildir. `semantic_acceptance:false` ve tam kitap kapsamının ayrı olduğu bilgisi her kanıtta korunur.
