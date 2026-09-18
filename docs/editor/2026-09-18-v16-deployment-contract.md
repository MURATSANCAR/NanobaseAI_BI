# V16-r3 dağıtım hazırlığı — çalıştırılmadı

Genel araç `apps/editor/scripts/deploy-verified-release.py`; hazırlanmış çalışma kopyası `/tmp/editor-deploy-v16-r3.py`. Kullanım uzak CPU'da `python3 deploy-verified-release.py CONTRACT.json`. Bu turda dağıtım başlatılmadı; hazır başarılı proof veya sahte imaj kimliği üretilmedi. Kod henüz gerçek dağıtımla DOĞRULANAMADI.

Contract zorunlu alanları:

- `remote_hostname`, `root`, `stage`, `release`, `previous_release`, `previous_backend_tree_sha256`, `qualified_generation_id`, `readiness_url`.
- `managed_directories`: en az backend/frontend/scripts/deploy/gpu; tam dizinler taşınır. runtime/secrets/evidence/git taşınamaz. `top_level_files`: paketin kökteki bütün yapılandırma/compose/Dockerfile dosyaları, `.env` hariç. Stage tam olarak bu köklerden oluşur; seçilmiş birkaç dosya kabul edilmez.
- `images:{api,document,web}`: gerçek Docker image ID değerleri. Dosya sayısı yalnız rapor metadatası olabilir; sabit50/11 güvenlik kuralı yoktur.
- `proofs`: `cleanup`, `qualification`, `backend_build`, `web_acceptance`, `main_sources`, `snapshot`; her biri mevcut bağımsız kanıtın `{path,sha256}` çifti. Eksik dosya/hash uyuşmazlığı durdurur.

`cleanup` mevcut R7 network-cleanup JSON biçimidir; returncode0/proxy_removed/boş errors gerekir. `qualification` R7 qualification.json biçimidir; aynı nesil, son qualification PASS ve hedef STOPPED gerekir. `backend_build` mevcut V16 build proof biçimidir: source_sha256, images[role,image,image_id,image_python_manifest,extra_python_files]. Image tam Python kümesi eşliği ve ek dosya olmaması gerekir; ayrıca API/document imajları başlatılmadan `/app` üzerinden bütün kaynak dosyalarının exact yol/hash kümesi bağımsız karşılaştırılır.

`web_acceptance` gerçek P5 UI kanıtıdır: PASS, semantic_acceptance false ve snapshot bağlı bağımsız grafik kabulü PASS. Web imaj ID'si snapshot'ta ayrıca sabitlenir; gerçek imajın bütün kaynak hashleri ve tüm build çıktıları karşılaştırılır.

`main_sources` teknik kaynak kanıtı: `{status:"PASS",branch:"main",clean:true,commit:<40hex>,source_files:{relative_path:sha256}}`. Kaynak kümesi bütün stage dosyalarını kapsar. Bu, nihai temiz main snapshot'ı alındıktan sonra üretilmeli; eski commit/eksik8dosyalık manifest kullanılmaz.

`snapshot` final teknik kapı kanıtı: `{status:"PASS",main_commit,release,qualified_generation_id,source_files,images,backend_files,web_sources,backend_tree_sha256,p5_web_image_id}`. Buradaki değerler main_sources, build proof, gerçek stage ve gerçek imajlarla birebir eşleşir. `backend_tree_sha256`, backend'e göre göreli bütün dosya hash sözlüğünün Python `json.dumps(...,sort_keys=True)` SHA256 değeridir. Bu belge proof yerine geçmez.

Önce canlı R7 backend tree + verify-release ve aktif job/PARSING yokluğu kontrol edilir. Tam kaynak ve `.env` ayrı özel rollback dizinine kopyalanır; yeniden idle kontrolü sonrası tam dizinler taşınır. İmajlar digest ID ile seçilir. Etkin Compose'un override dosyaları farklı imaj seçerse işlem reddedilip eski kaynak/env geri yüklenir; override dosyaları gizlice atlanmaz. Runtime'a özgü compose override varsa final stage/ortam sözleşmesi root tarafından ayrıca tutarlı hazırlanmalıdır.

Readiness sonrası gerçek verify-release(web dahil) ve verify.py geçmeden PASS yok. Başarısızlıkta önceki tam kaynak/env yeniden kurulur, servisler ve readiness doğrulanır; rollback sonucu ayrı kaydedilir. Araç analiz/soru/model işi başlatmaz, kitap/inceleme verisi yazmaz. Teknik dağıtım PASS kitap anlamsal kabulü değildir.

## Genişleyen kaynak kümesi

Yeni genel kaynak yükümlülük modülleri dosya sayısını artırabilir. Nihai snapshot `backend_files` ve `web_sources` tam göreli yol/hash sözlüklerini açıkça taşır. Bunlar stage, temiz main kaynak manifesti ve imaj içeriğiyle exact eşleşmeden dağıtım ilerlemez; aynı dosya sayısı veya önceki sürümün50/11sayısı kabul kanıtı değildir. Yeni epistemik/konum/sahiplik kapıları için gerçek kabul tamamlanana kadar final teknik snapshot üretilemez. Dağıtım başlatılmadı.
