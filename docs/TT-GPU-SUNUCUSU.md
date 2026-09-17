# Türk Telekom GPU Sunucusu — erişim, envanter ve model kurulumu

Durum tarihi: 2026-09-17. Bu belge o gün yapılanların kaydıdır; "yapıldı", "ölçüldü" ve "henüz denenmedi" ayrı yazılır. Parola, OTP ve anahtar içeriği bu belgede ve repo'da **tutulmaz**.

## 1. Makineler

| Ad (ssh) | Adres | Tür | Donanım |
|---|---|---|---|
| `tt-gpu` | 172.23.85.10 | fiziksel | 2 × NVIDIA H100 NVL 94 GB (sürücü 580.173.02, CUDA 13.0), 192 çekirdek, 2015 GB RAM, sistem diski 436 GB, `/data` 5,8 TB |
| `tt-gpu-vm` | 172.23.85.11 | sanal | GPU yok, 32 çekirdek, 125 GB RAM, 95 GB disk |

İkisi de Ubuntu 24.04.4, internet çıkışı var, `sudo` parolasız. Açık portlar: `.10` → 22, 443 (nginx), 3389 (xrdp); `.11` → 22, 443.

Ölçülen sınırlar:

- **GPU'lar arası bağlantı `SYS`:** NVLink yok; iki kart ayrı işlemci soketinde, PCIe + soketler arası yol üzerinden konuşur. İki karta bölünen modelde hız bundan etkilenir.
- **İnternet çıkışı ≈ 100 Mbit (11–13 MB/sn):** ağ kartı 50 Gbit olmasına rağmen toplam indirme bu değeri geçmiyor. İki bağımsız kaynakla aynı anda ölçüldü; ikinci kaynak eklenince toplam 11 → 13 MB/sn oldu. Sınır TT'nin bu ağa verdiği çıkıştadır; sanal makinede de aynıdır. Paralel bağlantı, erişim anahtarı veya ayna bunu değiştirmez.

## 2. Erişim

### 2.1 Neden test sunucusundan doğrudan bağlanılamıyor

TT VPN ağ geçidi `https://sgmvpn.turktelekom.com.tr/ttvm` (88.255.76.166) bir Ivanti/Pulse Secure kapısıdır. `nanobase-direct` (38.247.162.28, ABD çıkışlı) bu adresin 443 portuna TCP seviyesinde ulaşamıyor (zaman aşımı); aynı adres Türkiye çıkışlı bağlantıdan `302` ile yanıt veriyor. DNS doğru çözülüyor. Neden büyük olasılıkla yurt dışı IP engelidir. Kalıcı çözüm TT'nin bu IP'ye izin vermesidir; talep edilmedi/yanıt alınmadı.

Test sunucusuna yine de `openconnect` 9.12, `/usr/local/sbin/ttvpn-login` (etkileşimli giriş) ve `/usr/local/sbin/ttvpn-script` (varsayılan rotayı ve DNS'i devralmayan rota betiği, arayüz `tun-tt`) kuruldu. Ağ geçidine ulaşılamadığı için gerçek oturumla denenemedi.

### 2.2 Çalışan yol: Mac üzerinden (kullanıcı kararıyla "Mac'te işlem yok" kuralına istisna)

1. **Araçlar:** yönetici parolası gerekmesin diye Homebrew `~/homebrew` altına kuruldu; `openconnect` 9.21 ve `ocproxy` 1.60 oradan derlendi (24 bağımlılık, yaklaşık 40 dakika). Sistem ayarına dokunulmadı.
2. **Giriş:** `~/bin/ttvpn-mac`. `openconnect --protocol=nc --script-tun` + `ocproxy -D 11080`: tünel kullanıcı alanında kalır, root istemez, Mac'in rotaları ve DNS'i değişmez. TT iç ağına yalnız `SOCKS5 127.0.0.1:11080` üzerinden çıkılır. Kullanıcı adı, parola ve e-postaya gelen OTP'yi **kullanıcı** yazar; hiçbiri diske yazılmaz. İkinci `password:` sorusu (ekranda `frmDefender`) hesap parolası değil OTP'dir — ilk denemede bu karıştırıldı.
3. **Sertifika:** ilk girişte "signer not found" uyarısı çıktı. Neden: `~/homebrew` altındaki GnuTLS kök sertifika dosyasını kendiliğinden bulmuyor. Sunucu sertifikası ayrıca doğrulandı (macOS `curl` hatasız; zincir TÜRK TELEKOMÜNİKASYON A.Ş → GeoTrust TLS RSA CA G1 → DigiCert Global Root G2; açık anahtar izi uyarıdakiyle aynı). Betiğe `--cafile ~/homebrew/etc/ca-certificates/cert.pem` eklendi; bu değişiklik henüz yeni bir girişle denenmedi.
4. **SSH:** `~/.ssh/config` içinde `tt-gpu` ve `tt-gpu-vm` (ProxyCommand `nc -X 5 -x 127.0.0.1:11080`, anahtar `nanobase_ed25519`). Anahtarı iki makineye kullanıcı `ssh-copy-id` ile yükledi.
5. **Uyku:** `caffeinate -imsu` arka planda. Kapak kapanırsa veya şarjdan çıkarsa Mac yine uyur; VPN kopunca yeniden OTP gerekir. Sunucuda çalışan işler (indirme, model) VPN kopmasından etkilenmez.

### 2.3 Test sunucusuna köprü

`~/bin/ttvpn-bridge` (Mac'te, arka planda, koparsa 5 saniyede yeniden bağlanır; durdurma `~/bin/ttvpn-bridge stop`): `nanobase-direct`'in `127.0.0.1:11080` portunu Mac'teki VPN vekiline ters tünelle bağlar. Sunucudan iki makinenin SSH karşılama satırı alındı. Port yalnız `127.0.0.1`'e açıktır; Docker konteynerleri göremez. Zincir sunucu → Mac → TT VPN olduğu için gece işlerine uygun değildir.

**Yapılmadı:** sunucudan parolasız SSH için TT makinelerinin `authorized_keys` dosyasına sunucu anahtarı eklenmedi (izin denetimi "izinsiz kalıcı erişim" sayıp reddetti). Sunucudan yalnız HTTP/API erişimi vardır.

## 3. Makinede bulunanlar (2026-09-17 envanteri)

| Ne | Durum |
|---|---|
| `~/mlops-pipeline/docker-compose.yml`: 2 × vLLM 0.25.1, `RedHatAI/gemma-4-31B-it-FP8-block`, port 8001 (GPU 0) ve 8002 (GPU 1), 32K bağlam | **Durduruldu, silinmedi.** Son istek GPU 0: 4 Eylül 21:08 UTC, GPU 1: 28 Ağustos 21:54 UTC. Yoğun dönem 22–23 Ağustos (14.400 + 6.225 istek). İsteklerin 20.722'si `172.30.27.167` (bir TT VPN kullanıcısı). Yeniden başlatma ayarı `unless-stopped`: makine yeniden başlasa da kendiliğinden açılmaz. |
| Gemma 4 31B dosyaları (32 GB, `~/.cache/huggingface`, root sahipli) | Duruyor — geri dönüş yolu. |
| `Qwen/Qwen3.8-27B-FP8` (30 GB) | **Silindi** (kullanıcı, `sudo rm`). |
| Docker derleme önbelleği 65,5 GB, CUDA 13.0.2 imajı, durmuş `vllm-gpu1` ve `timas-ml-train-run-…` konteynerleri | **Silindi** (kullanıcı). Sistem diski 175 → 269 GB boş. |
| `mssql-logo` (SQL Server 2022, port 1433): `LOGO_DB.mdf` 300,7 GB `/data/mssql_restore`, 124 GB RAM | **Çalışıyor.** Durdurma komutu izin denetiminde reddedildi; kullanıcıya bırakıldı. |
| `/data/Timas_LOGODB_Yedek_200820261257` (227 GB) | Duruyor. |
| Qdrant (6333, koleksiyon yok), Ollama (`nomic-embed-text`, yalnız localhost), `127.0.0.1:8003` Python servisi, `timas-ml:latest` imajı (22,8 GB, JupyterLab) | Dokunulmadı. 8003 servisi ve nginx siteleri incelenemedi (root gerektiren okuma reddedildi). |
| `/data` altında kitap klasörleri (485 GB, 444 GB, 166 GB…) | Dokunulmadı; sahibi bilinmiyor. |
| `~/client.ovpn`, `~/auth.txt` | İçleri açılmadı. |

Sanal makinede GPU, Docker konteyneri, Ollama yok; işletim sistemine kurulu bir SQL Server (2,3 GB) ve açık bir masaüstü oturumu var.

## 4. Qwen3.8-Flash-Next-FP8 denemesi

### 4.1 Model (Hugging Face kaydı + vLLM tarifi)

180 milyar parametre: 125B ana model (token başına 6B etkin, 512 uzman, 10+1 etkin) + 51B n-gram gömme tablosu + 4B MTP. FP8 dosyaları 185,6 GB, 131 parça, erişim açık. Görsel girişli, 262K bağlam, mimari `qwen4_exp` (Qwen4 önizlemesi), 31.08.2026. Özel imaj gerekir: `vllm/vllm-openai:qwen38-flash-next` (28,8 GB, geliştirme sürümü `0.1.dev20073`); makinedeki 0.25.1/0.27.1 çalıştırmaz.

### 4.2 Kapasite hesabı

- Disk: 186 GB → `/data` (3,8 TB boş). Rahat.
- RAM: tablo için ≥ 51 GB → yaklaşık 1785 GB kullanılabilir. Rahat.
- GPU: tablo GPU'da kalırsa ağırlıklar ≈ 173 GiB, sığmaz. `VLLM_PLE_CPU_OFFLOAD=1` ile kart başına ≈ 63 GiB ağırlık; %90 kullanımda kart başına ≈ 21 GiB pay. KV önbelleği küçük (48 katmanın 12'si tam dikkat, 2 KV başı; 262K ≈ 3 GB).

### 4.3 Riskler

1. İki H100 resmî doğrulanmış değil: tarif H100'de 4 kartı, iki kartı yalnız GB300'de (kart başına ≈ 190 GiB) doğrulamış.
2. Tarife göre 8 kartlı düz bölme FP8'in 128'lik bloklarıyla uyumsuz; iki kartın H100'de uyumu denenmemiş. Yedek: `--enable-expert-parallel`.
3. NVLink yok → hız tarifteki 1.430 token/sn'nin altında kalır.
4. İlk açılış 20–40 dakika sürebilir (186 GB yükleme + derleme + tablonun belleğe alınması).

İmaj önceden denetlendi: mimari kayıtlı (`Qwen4ExpForConditionalGeneration`), `ple_offload` kodu ve TP aralığı desteği var, `--moe-backend` ve `mtp` mevcut, CUDA 13.0 / `sm_90` sürücüyle uyumlu, iki kartı baştan reddeden bir kontrol görülmedi. Bu yalnız kodun reddetmediğini gösterir; belleğin yeteceğini göstermez.

Tahmin (ölçüm değil): ilk ayarlarla açılma %35–45, ayar kısarak %35–40, bu donanımda açılmama %20–25.

### 4.4 Sunucuda hazırlananlar

- İndirme: konteyner `qwen38-download` → `/data/hf-cache`. Hugging Face'in xet aktarımı takıldı (5 dakikada 4 MB); `HF_HUB_DISABLE_XET=1` ile düz HTTP'ye alındı, hattın tamamını (11 MB/sn) kullanıyor. Tek kopya.
- Çalıştırma dosyası: `/data/qwen38/docker-compose.yml` — tek servis, iki GPU birlikte (`--tensor-parallel-size 2`), `VLLM_PLE_CPU_OFFLOAD=1`, `--moe-backend triton`, `--gpu-memory-utilization 0.90`, `--max-model-len 131072`, `--max-num-seqs 64`, önek önbelleği, MTP tahminli çözümleme (3 token), `qwen3_coder` araç ve `qwen3` düşünme ayrıştırıcıları, port 8001, model adı `qwen3.8-flash-next`, sağlık denetimine 30 dakika başlangıç payı. `docker compose config` geçerli. Eski `mlops-pipeline` dosyalarına dokunulmadı; aynı portu kullandıkları için ikisi aynı anda açılmaz.

Bellek yetmezse sıra: bağlam 32K → eşzamanlı istek 16 → `--enforce-eager` → MTP kapalı → uzman paralel.

### 4.4.1 Sonuç (2026-09-18, gece): model iki H100'de ilk ayarlarla açıldı

- İndirme 131/131 parça; 144 dosyanın boyutu Hugging Face listesiyle tek tek karşılaştırıldı, fark yok.
- Açılış: ağırlıklar kart başına 64,58 GiB (yükleme 69 sn), KV önbelleği kart başına 15,75 GiB = 950.590 token (131K bağlamda 7,25 eşzamanlı tam istek), CUDA grafikleri yakalandı, GPU'larda 88 GiB dolu. Bellek hatası ve yeniden başlama yok; hiçbir ayar kısılmadı.
- NVLink'siz düzen denetimi: kartlar arası doğrudan erişim okuma/yazma `OK`, PCIe Gen5 x16, vLLM `CUSTOM`+`PYNCCL` all-reduce seçti. Eksik bulunan: işçi süreçleri NUMA düğümüne bağlı değildi (`cpus=0-191`). `--numa-bind` + konteynere `SYS_NICE` eklendi; sonrasında TP0 `0-47,96-143`, TP1 `48-95,144-191` (doğrulandı). Önceki dosya `docker-compose.numa-oncesi.yml`.
- Hız (düşünme kapalı, aynı betik):

| Test | NUMA öncesi | NUMA sonrası |
|---|---|---|
| Tek istek, 881 token Türkçe üretim | 130 tok/sn | 132 tok/sn |
| BI sorusu → T-SQL (116 token) | 2,0 sn | 0,7 sn |
| 8 eşzamanlı | 408 tok/sn toplam | 680 tok/sn toplam |
| 32 eşzamanlı | 1.361 tok/sn toplam | 1.500 tok/sn toplam |

  Uyarı: ilk ölçüm modelin ilk istekleriydi (soğuk önbellek); farkın bir kısmı NUMA'dan değil ısınmadan gelebilir. Ayrıştırmak için aynı koşulda tekrar ölçüm yapılmadı.
- BI sorusu: satış `TRCODE` kümesi, iptal hariç, aylık kırılımlı doğru T-SQL üretti (tek örnek; golden set koşturulmadı).
- Kitap sayfası okuma (3 sayfa, 1400 görsel token, 0,3–2,8 sn): s.29 balonu harfi harfine doğru ve konuşmacı "kız"; s.6 yazısız → "YOK"; s.22 metni hatasız okudu **ama** tırnaklar arasındaki anlatı cümlesini (`dedi Profesör Bulut gururla.`) atladı, düz yazıdaki diyaloğu "balon" diye etiketledi ve satır sonu tirelerini kendiliğinden birleştirdi. Sonuç: güçlü ikinci okuyucu, tek kaynak değil — bölüm 5'teki karar geçerli.

**Henüz yapılmadı:** BI golden set'inin bu modelle koşturulması, köprü/LLM kapısına bağlanması, 1.149 bölgelik OCR karşılaştırması, uzun bağlam ve düşünme açıkken ölçüm.

### 4.5 Geri dönüş

- `Qwen/Qwen3.8-27B-FP8` tek karta sığar, görsel girişli, editörün tanıdığı model; ikinci kart OCR'a kalır.
- Gemma 4 31B: `docker start mlops-pipeline-vllm-gpu0-1 mlops-pipeline-vllm-gpu1-1`.

## 5. Editör için OCR önerisi (karar, henüz denenmedi)

İncelenen kitap: «Ekrana Sığmayan Macera» (48 sayfa). Düz yazı sayfalarında metin PDF'te gömülü (s.13: 863 karakter) — OCR gerekmez. Balon ve süsleme yazıları eğriye çevrilmiş (s.29'da PDF 5 karakter veriyor); elle çizilmiş görünümlü, tamamı büyük harf, renkli çizim üstünde, Türkçe harfli. Editörün bugünkü okuyucuları (CPU'da PP-OCRv5 mobile + Tesseract) belge için yapılmıştır.

Seçim, iki katman:

1. **Ana okuyucu `PaddlePaddle/PaddleOCR-VL-1.6`** (0,96B, Apache-2.0): kartında serbest metin bulma ("text spotting") var, kutu koordinatı verir (editörün "ham metin + kutu + köken" sözleşmesi), vLLM ile GPU'da çalışır, yaklaşık 4–6 GB.
2. **İkinci bağımsız okuyucu + konuşmacı ataması: Qwen3.8-Flash-Next** (görsel girişli). Tek başına OCR motoru olarak önerilmez: kartında hiç OCR ölçümü yok, genel VLM'ler bulanık yazıyı "düzeltme" eğilimindedir, kutu ve tekrarlanabilirlik güvencesi yoktur. Bu, editör kaydındaki «betimlemenin metin sanılması» hatasının aynısını üretir.

Elenenler: `chandra-ocr-2` (OpenRAIL lisansı belirsiz), `baidu/Unlimited-OCR` ve `GLM-OCR` (belge/tablo ağırlıklı), `manga-ocr` (yalnız Japonca).

Bilinmeyen: PaddleOCR-VL-1.6'nın Türkçe büyük harf balon yazısındaki başarısı. Kanıt yolu: bu kitabın kayıtlı 1.149 bölgesi (821 anlaşma / 328 inceleme) iki yeni okuyucuyla koşturulur; 328'in kaçı çözülüyor, 821'in kaçı bozuluyor, İ/Ş/Ğ hataları sayılır. Kitaba özel ayar yapılmaz.

### 5.1 PaddleOCR-VL-1.6 kuruldu: istek gelince açılan, boşta kapanan Docker servisi (2026-09-18)

- Model (1,93 GB, 20 dosya) `/data/hf-cache` altına indi. Dosyalar `/data/paddleocr-vl/`: `docker-compose.yml`, `gateway.py`.
- İki konteyner: `paddleocr-vl` (vLLM 0.27.1, GPU 1, `restart: "no"`, dışarıya port açmaz) ve `paddleocr-gateway` (python:3.12-slim, yalnız standart kütüphane, port **8010**, `unless-stopped`, birkaç MB bellek). Kapı Docker soketi üzerinden hedef konteyneri başlatır/durdurur; soket bağlandığı için kapı konteyneri makinede root eşdeğeridir.
- Davranış: `GET /gateway/status` konteyneri başlatmadan durumu verir. Diğer her istek konteyneri açar, `/health` 200 olana kadar bekler, isteği iletir (soğuk açılışta yanıta `X-Cold-Start-Seconds` eklenir). `IDLE_SECONDS` (varsayılan 600, `OCR_IDLE_SECONDS` ile değişir) boyunca istek yoksa konteyner durdurulur.
- Doğrulandı: soğuk açılış 68,6 sn; Flash-Next kartı %90 kullanırken kalan payda açıldı (`--gpu-memory-utilization 0.05`, 2,15 GiB ağırlık + 2,21 GiB KV = 128.912 token, `--enforce-eager`); geçici 60 sn sınırıyla 66. saniyede kendiliğinden kapandı (çıkış 0), GPU 1 belleği 94,9 → 89,6 GiB'e döndü, Flash-Next sağlıklı kaldı. Açıkken GPU 1'de yaklaşık 1 GiB boş kalıyor — dar.
- İlk okuma denemesi (2 sayfa, 1400 px JPEG, sayfa başına 0,6–2,2 sn): kutu koordinatı veriyor (`Spotting:`) ve metni eksiksiz aktarıyor (Flash-Next'in atladığı `dedi Profesör Bulut gururla.` cümlesi var). **Ama Türkçe harflerde zayıf:** "DUR!" → "DURI", "Gıcırtıyla" → "Gıcirtıyla", "biriktirdiği" → "biriktirdigi", "Işık" → "İsik", "karışmıştı" → "karışmıştır"; `Spotting:` kipinde ş/ç/ğ/ı büyük ölçüde düşüyor. Flash-Next aynı sayfalarda harfleri doğru okumuştu.
- Bu, bölüm 5'teki iş bölümünü değiştirir (kanıtlanmış değil, iki sayfalık gözlem): **kutu ve eksiksizlik PaddleOCR-VL'den, harf doğruluğu Flash-Next'ten** gelmeli — örneğin PaddleOCR-VL kutuları bulur, her kutunun kırpımını Flash-Next okur, iki metin karşılaştırılır. Daha yüksek çözünürlükte PaddleOCR-VL'nin Türkçe başarısı ölçülmedi. Karar 1.149 bölgelik karşılaştırmaya bağlı; kullanıcı bu adım için beklememi istedi.

## 6. Açık işler

1. Modeli BI köprüsüne / LLM kapısına bağlama kararı ve golden set koşusu (model çalışıyor: `tt-gpu:8001`, ad `qwen3.8-flash-next`).
2. `mssql-logo` ve Logo yedeği hakkında kullanıcı kararı.
3. TT'den `38.247.162.28` için VPN izni ve internet çıkış sınırının yükseltilmesi talebi.
4. OCR karşılaştırması (bölüm 5).
5. Sunucudan SSH gerekiyorsa anahtar ekleme için açık onay.
6. İki makinenin parolaları kullanıcı adıyla aynı ve sohbette düz metin geçti; değiştirilmesi TT'nin kararıdır.
