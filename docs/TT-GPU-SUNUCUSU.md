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
5. **Bağlanma tarifi (2026-09-24'te doğrulandı, hesap `deniz.akko`):**
   1. Açık kalmış eski girişleri kapat: `pkill -f 'openconnect --protocol=nc'`. Asılı yarım oturum yeni girişi `p=login-denied` ile reddettirir.
   2. Şifreyi **elle yazma**. Tarayıcıda `https://sgmvpn.turktelekom.com.tr/ttvm` aç, şifreyi yaz, göz simgesiyle doğru olduğunu gör, kopyala (Sign in'e basma).
   3. `~/bin/ttvpn-mac` → `username:` `deniz.akko` → `password:` Cmd+V → ikinci `password:` (`frmDefender`) e-postadaki OTP.
   4. Başarı: `p=user-confirm` → `/dana/user/#` → `Configured as 172.30.x.x`. Kontrol: `ssh tt-gpu hostname` → `gpuubuntu`.

   **Hata kodları:** `welcome.cgi?p=failed` = şifre yanlış (OTP e-postası gönderilmez); `p=login-denied` = eski oturum çakışması; `p=defender` = şifre kabul, OTP bekleniyor. Art arda `failed` hesabı kilitler — iki yanlıştan sonra durup tarayıcıdan doğrula.

   **24 Eylül'de öğrenilen:** terminal `p=failed` verip tarayıcı giriyor gibi göründüğünde sebep istemci değildi. Uygulama içi tarayıcının ağ kaydı tarayıcının da 3 kez `p=failed` alıp 4.'de girdiğini gösterdi; şifre elle her seferinde aynı yazılamıyordu. Denenip **işe yaramayan** yollar (tekrarlama): tarayıcı kimliği (`--useragent`), şifreyi form alanıyla verme (`-F frmLogin:password=…`, üstelik reddedilince şifreyi kendiliğinden yeniden gönderip kilide yaklaştırır), tarayıcının `DSID` çereziyle bağlanma (`-C`, `hostname packet error 0x07` — web oturumu tünel açmaz). Teşhis için: uygulama içi tarayıcıda `/ttvm` açılır, kullanıcı girer, `welcome.cgi?p=` sırasına bakılır.
6. **Uyku:** `caffeinate -imsu` arka planda. Kapak kapanırsa veya şarjdan çıkarsa Mac yine uyur; VPN kopunca yeniden OTP gerekir. Sunucuda çalışan işler (indirme, model) VPN kopmasından etkilenmez.

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

## 4.0 Güncel durum (2026-09-19): ana model Qwen3.8-27B-FP8, sunulan ad `nanobaseAI`

Kullanıcı kararıyla Flash-Next bırakıldı ve **kalıcı silindi** (konteynerler, `vllm/vllm-openai:qwen38-flash-next` etiketi, 173 GB model, `/data/qwen38`; komutu kullanıcı çalıştırdı: `scripts/server/tt-gpu-flash-next-sil.sh`). Neden: 186 GB model 2 × 94 GB karta ancak n-gram tablosu RAM'e atılarak sığıyordu (resmî tarif 4 kart); Soğuk açılışta 64 → 88 GiB sıçraması bundan geliyordu.

- **Kurulum:** `/data/qwen27/docker-compose.yml` (depoda `deploy/tt-gpu/compose.qwen27b.yaml`), konteyner `qwen38-27b`, imaj `vllm/vllm-openai:v0.27.1` (mimari `Qwen3_5ForConditionalGeneration` ve `Qwen3_5MTP` bu imajda kayıtlı; özel imaj gerekmez). Tek sunucu, port 8001, **2026-09-19 21:10'dan beri yalnız GPU 0** (`--tensor-parallel-size 1`, `--numa-bind`; GPU 1 editör modülünün, `apps/editor`; öncesinde iki karta bölünmüş TP2 idi), `--gpu-memory-utilization 0.80`, 131K bağlam, 32 eşzamanlı istek, önek önbelleği, MTP 3 token, `qwen3_coder` araç ve `qwen3` düşünme ayrıştırıcıları. Geçiş betiği: `scripts/server/tt-gpu-qwen27b-cutover.sh`.
- **Sunulan ad `nanobaseAI`** (kullanıcı kararı): tüketiciler arkadaki modeli bilmez; gerçek model `/v1/models` → `root` alanında (`Qwen/Qwen3.8-27B-FP8`). Model değişirse tüketici ayarı değişmez. Ad değiştirme betiği: `scripts/server/model-name-switch.sh` (köprü, Editör api/worker, TİMAŞ VM bridge).
- **Açılış:** indirme 81 dosya / 30 GB, boyutlar Hugging Face listesiyle eş; ilk açılış ≈ 7 dk (derleme 9,7 sn + Triton ısınması). Kart başına ≈ 77–81 GB dolu; KV önbelleği 1.602.153 token (131K bağlamda 12,2 eşzamanlı tam istek; Flash-Next'te 950.590 / 7,25).
- **Ölçüm (düşünme kapalı, aynı makinede):**

| Test | Flash-Next (09-18) | 27B-FP8 TP2 + MTP |
|---|---|---|
| Tek istek, 800 token Türkçe üretim | 130 tok/sn | **177 tok/sn** |
| BI sorusu → T-SQL (≈ 130 token) | 0,7 sn | **0,5 sn** |
| 20.335 token istem, kısa cevap | — | 2,2 sn; tekrar (önek önbelleği) 0,4 sn |
| 8 eşzamanlı | 680 tok/sn | **902 tok/sn** |
| 32 eşzamanlı | 1.500 tok/sn | **2.256 tok/sn** |

- **Doğrulanan yollar:** düşünme kapalı bayrağı (`reasoning` boş), `structured_outputs.choice` + `logprobs` (tek token, aday olasılıkları), görsel girdi (Türkçe harfli yazı 1,0 sn'de harfi harfine: `GICIRTIYLA AÇILDI! Işık, şüphe, düğüm`), CPU sunucusundan `127.0.0.1:18885` tüneli.
- **Henüz yapılmadı:** set100'ün tamamı, uzun süreli yük. Kalite kabulü bu ölçümlere bağlıdır; hız ölçümü kalite kanıtı değildir.

## 4. Qwen3.8-Flash-Next-FP8 denemesi (geçmiş kayıt — model 2026-09-19'da silindi)

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

**Henüz yapılmadı:** BI golden set'inin bu modelle koşturulması, köprü/LLM kapısına bağlanması, uzun bağlam ve düşünme açıkken ölçüm.

### 4.5 Geri dönüş

- `Qwen/Qwen3.8-27B-FP8` tek karta sığar, görsel girişli.
- Gemma 4 31B: `docker start mlops-pipeline-vllm-gpu0-1 mlops-pipeline-vllm-gpu1-1`.

## 5. Açık işler

1. Modeli BI köprüsüne / LLM kapısına bağlama kararı ve golden set koşusu (model çalışıyor: `tt-gpu:8001`, ad `qwen3.8-flash-next`).
2. `mssql-logo` ve Logo yedeği hakkında kullanıcı kararı.
3. TT'den `38.247.162.28` için VPN izni ve internet çıkış sınırının yükseltilmesi talebi.
4. Sunucudan SSH gerekiyorsa anahtar ekleme için açık onay.
5. İki makinenin parolaları kullanıcı adıyla aynı ve sohbette düz metin geçti; değiştirilmesi TT'nin kararıdır.
