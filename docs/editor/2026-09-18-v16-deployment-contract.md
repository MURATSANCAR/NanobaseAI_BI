# V16-r3 dağıtım hazırlığı — çalıştırılmadı

Genel araç `apps/editor/scripts/deploy-verified-release.py`; hazırlanmış çalışma kopyası `/tmp/editor-deploy-v16-r3.py`. Kullanım uzak CPU'da `python3 deploy-verified-release.py CONTRACT.json`. Bu turda dağıtım başlatılmadı; hazır başarılı proof veya sahte imaj kimliği üretilmedi. Kod henüz gerçek dağıtımla DOĞRULANAMADI.

Contract zorunlu alanları:

- `remote_hostname`, `root`, `stage`, `release`, `previous_release`, `previous_backend_tree_sha256`, `qualified_generation_id`, `readiness_url`.
- `managed_directories`: en az backend/frontend/scripts/deploy/gpu; tam dizinler taşınır. runtime/secrets/evidence/git taşınamaz. `top_level_files`: paketin kökteki bütün yapılandırma/compose/Dockerfile dosyaları, `.env` hariç. Stage tam olarak bu köklerden oluşur; seçilmiş birkaç dosya kabul edilmez.
- `images:{api,document,web}`: gerçek Docker image ID değerleri. Dosya sayısı yalnız rapor metadatası olabilir; sabit50/11 güvenlik kuralı yoktur.
- `proofs`: `cleanup`, `qualification`, `backend_build`, `web_acceptance`, `main_sources`, `snapshot`; her biri mevcut bağımsız kanıtın `{path,sha256}` çifti. Eksik dosya/hash uyuşmazlığı durdurur.

`cleanup` mevcut R7 network-cleanup JSON biçimidir; returncode0/proxy_removed/boş errors gerekir. `qualification` R7 qualification.json biçimidir; aynı nesil, son qualification PASS ve hedef STOPPED gerekir. `backend_build` mevcut V16 build proof biçimidir: backend_manifest, images[role,image,image_id,image_source_manifest,exact_source_path_set,extra_python_files]. Image tam Python kümesi eşliği ve ek dosya olmaması gerekir; ayrıca API/document imajları başlatılmadan `/app` üzerinden bütün kaynak dosyalarının exact yol/hash kümesi bağımsız karşılaştırılır.

`web_acceptance` gerçek P5 UI kanıtıdır: PASS, semantic_acceptance false ve snapshot bağlı bağımsız grafik kabulü PASS. Web imaj ID'si snapshot'ta ayrıca sabitlenir; gerçek imajın bütün kaynak hashleri ve tüm build çıktıları karşılaştırılır.

`main_sources` teknik kaynak kanıtı: `{status:"PASS",branch:"main",clean:true,commit:<40hex>,source_files:{relative_path:sha256}}`. Kaynak kümesi bütün stage dosyalarını kapsar. Bu, nihai temiz main snapshot'ı alındıktan sonra üretilmeli; eski commit/eksik8dosyalık manifest kullanılmaz.

`snapshot` final teknik kapı kanıtı: `{status:"PASS",main_commit,release,qualified_generation_id,source_files,images,backend_files,web_sources,backend_tree_sha256,p5_web_image_id}`. Buradaki değerler main_sources, build proof, gerçek stage ve gerçek imajlarla birebir eşleşir. `backend_tree_sha256`, backend'e göre göreli bütün dosya hash sözlüğünün Python `json.dumps(...,sort_keys=True)` SHA256 değeridir. Bu belge proof yerine geçmez.

Önce canlı R7 backend tree + verify-release ve aktif job/PARSING yokluğu kontrol edilir. Tam kaynak ve `.env` ayrı özel rollback dizinine kopyalanır; yeniden idle kontrolü sonrası tam dizinler taşınır. İmajlar digest ID ile seçilir. Etkin Compose'un override dosyaları farklı imaj seçerse işlem reddedilip eski kaynak/env geri yüklenir; override dosyaları gizlice atlanmaz. Runtime'a özgü compose override varsa final stage/ortam sözleşmesi root tarafından ayrıca tutarlı hazırlanmalıdır.

Readiness sonrası gerçek verify-release(web dahil) ve verify.py geçmeden PASS yok. Başarısızlıkta önceki tam kaynak/env yeniden kurulur, servisler ve readiness doğrulanır; rollback sonucu ayrı kaydedilir. Araç analiz/soru/model işi başlatmaz, kitap/inceleme verisi yazmaz. Teknik dağıtım PASS kitap anlamsal kabulü değildir.

## Genişleyen kaynak kümesi

Yeni genel kaynak yükümlülük modülleri dosya sayısını artırabilir. Nihai snapshot `backend_files` ve `web_sources` tam göreli yol/hash sözlüklerini açıkça taşır. Bunlar stage, temiz main kaynak manifesti ve imaj içeriğiyle exact eşleşmeden dağıtım ilerlemez; aynı dosya sayısı veya önceki sürümün50/11sayısı kabul kanıtı değildir. Yeni epistemik/konum/sahiplik kapıları için gerçek kabul tamamlanana kadar final teknik snapshot üretilemez. Dağıtım başlatılmadı.

## R3 tam stage hazırlığı — dağıtım yapılmadı

CPU `/data/nanobaseai/editor/runtime/deploy-v16-r3-complete-stage`233uygulama dosyası içerir: backend/frontend/scripts/deploy/gpu/ocr/ocr-vl/speech ve kök compose/config dosyaları. Secrets, gerçek.env, runtime, evidence, node_modules, dist ve bytecode hariçtir. Güncel bağımsız helperlar dahil bütün scripts taşındı. Stage/backend52dosya mevcut `evidence/v16-r3-build-proof.json` fullbackendmanifestiyle exact; web11kaynak P5adayimajmanifestiyle exact eşleşti. Kanıt `evidence/v16-r3-stage-preparation.json` açıkça PREPARED_NOT_ACCEPTED.

Adaycontract `runtime/v16-r3-deployment-contract-PENDING.json`: gerçek R7 cleanup/qualification, finalR3backendbuild ve P5webAPI/PG/UI proof yolları/hashleri bağlı. `main_sources` ve `snapshot` dosyaları yok; hashleri PENDING_NOT_ACCEPTED. Bu halde araç ilerleyemez. Root bütün değişiklikleri main'e alıp temiz snapshot oluşturduktan ve integratedV7gerçek kabulü tamamlandıktan sonra stage güncelliği yeniden denetlenerek bu iki gerçek proof bağlanmalıdır. Daha sonra değişen script/helper dosyası da yeni source manifest gerektirir.

Etkin CPU Compose salt okunur kontrolünde compose.feature.yaml mevcut değil; COMPOSE_FILE yalnız compose.yaml/models/ocr/reread/gpu içeriyor. API/workerR7backend, parser/rereadR7document, gatewayöncekiweb seçili. Plan yalnız release ve üç imageenv alanını exactR3API/document ve P5webimageID ile güncellemek; etkinCompose görüntüsü farklı imajı gölgelerse dağıtım kapısı reddeder. Ana env veya servis değiştirilmedi.

## R4 aday stage — R3 korunur

Qualificationv2 ve son genel kaynakbirimi değişikliğinden sonra R3stage/imajı kullanılmaz. CPU `runtime/deploy-v16-r4-complete-stage`234dosya,52backendexactR4build ve11webexactP5manifest içerir. Yeni `source_qualification_reference.py` dahil bütün scripts/config taşındı; R3dizinleri/kanıtları korunur. KaynakunitSHA `5c8cbd611718d5769f6c1cd5f29a658d47d6a99b4c59326091559ae356378469`, semanticSHA `0627947e3f6bc7aec54c36f4db8f48e59f7bd2fa0c5639792dd249779085c0e8`, qualificationSHA `b6413249de9bcc7533b441f251d306902fd2668c4e1985d9d4d230d0550d24d8` finalfreeze ile eşleşti.

Gerçek R4API image `sha256:96ccb20acef0bbb452b1223c250881439341d79c03c862a70e202bc87cfdcd58`, document `sha256:d8988ced104fa28bb826694c962aeb521c449194c8b58df364a68b177d24ce60`; P5web aynı. `runtime/v16-r4-deployment-contract-PENDING.json` güncelbuild/R7qualification-cleanup/P5kanıtlarına hashbağlıdır; `evidence/v16-r4-stage-preparation.json` PREPARED_NOT_ACCEPTED. Temizmain/finaltechnicalsnapshot dosyaları yok, integratedV7sonkabul bekleniyor. Dağıtım yapılmadı; eksikproof kapısı açılamaz. Rootcommit sonrası bütünstagehashleri tekrar main'e bağlanmalıdır.
