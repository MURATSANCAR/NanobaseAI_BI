# Zeki AI sesli not — GPU servisi (konuşma → Türkçe metin)

Saha (M30) ve okul (M31) ziyaret notunu konuşarak yazdırma. Kullanıcı kararı (2026-09-28): «kuralım ama çok kaliteli
Türkçe notları tutabilmeliyiz». Model seçimi ve kalite ölçümü: [OLCUM.md](OLCUM.md).

```
telefon (tarayıcı: kayıt → 16 kHz tek kanal WAV)
  → portal nginx (/timas/api/v1/voice-note, 21 MB, istek tamponu kapalı)
  → köprü /api/v1/voice-note (yetki, süre/boyut sınırı, geliş sırası kapısı)
  → GPU sesli not servisi :8797 (tek sıra, GPU 0, ≤10 GB)      ← test sunucusu: ters tünel 127.0.0.1:18892
                                                                ← müşteri VM: GPU nginx /bi-voice/… (onay bekliyor)
  → köprü: isteğe bağlı Zeki AI düzeltmesi (LLM kapısı, «sesli-not»; sayı denetimi)
  → metin not alanına eklenir; kişi düzeltip kaydeder
```

## Kurallar

- **Ses saklanmaz.** Köprü ve servis gövdeyi bellekte okur; ffmpeg'e boruyla verilir. Servis konteynerinin kök dosya
  sistemi salt okunur, `/tmp` bellekte (tmpfs). nginx konumlarında `proxy_request_buffering off` (gövde geçici
  dosyaya yazılmaz). Günlüklerde yalnız süre/boyut/bekleme; metin ve ses yok.
- **GPU'da derleme yok.** İmaj BI modelinin kullandığı hazır `vllm/vllm-openai:v0.27.1` (torch, transformers, ffmpeg
  içinde); kod `/data/voice-note/app`, model `/data/voice-note/models/current` salt okunur bağlanır.
- **GPU'yu boğmama.** Servis tek sıra (`VOICE_CONCURRENCY=1`, geliş sırası; bekleyen reddedilmez, 300 sn'de 503 +
  yeniden dene). Bellek payı `VOICE_MEM_FRACTION=0.11` (≈10 GB): aşarsa servis kendisi OOM olur, BI modeli etkilenmez.
  Köprünün kendi kapısı (`VOICE_NOTE_SLOTS`) yalnız köprü iş parçacıklarını korur.
- **Ekranda teknoloji adı yok** («Zeki AI sesli not»). Servisin `model` alanı `zeki-ses`; köprü bunu ekrana taşımaz.
- **Düzeltme anlamı ve rakamı değiştiremez**: sayı değerleri çoklu küme olarak aynı olmalı («yirmi bin» = «20.000»),
  kelime farkı ≤ %25, uzunluk oranı 0,6–1,5; tutmazsa ham metin döner ve neden söylenir.

## Dosyalar

| Dosya | Ne |
|---|---|
| `apps/voice-note/voice_note_service/` | servis kodu (FastAPI; `audio.py` çözme + sessizlikten bölme, `text.py` uydurma altyazı/tekrar temizliği, `engine.py` model, `app.py` uçlar ve sıra) |
| `compose.yaml` | konteyner tanımı (derleme yok, salt okunur kök, GPU 0) |
| `install.sh` | GPU'da kurulum: kod kopyası, model (eksikse indirir), anahtar (yoksa üretir, 0600), kaldırma, sağlık |
| `voice-note-tunnel.service` | GPU → test sunucusu ters tünel (127.0.0.1:18892) |
| `add-voice-route.py` | GPU genel nginx'ine müşteri VM yolu — **kullanıcı onayıyla**, uygulanmadı |
| `../../nanobase-direct/add-voice-note-route.py` | test sunucusu portal nginx'i: 21 MB, tampon kapalı |
| `infra/docker/bi/web.default.conf.template` | müşteri VM web kapısı: aynı konum |
| `olcum/` | ölçüm betikleri (`olc.py`, `runall.sh`, `indir.py`) ve sahada okunacak alan cümleleri |
| `scripts/acceptance/voice-note/kabul.py` | test sunucusunda uçtan uca kabul (K1–K6) |

## Kurulum sırası (main → test sunucusu → VM)

1. **GPU** (kod `main`den): `git archive main apps/voice-note deploy/tt-gpu/voice-note | ssh tt-gpu 'mkdir -p /tmp/voice-note-src && tar -x -C /tmp/voice-note-src'`,
   sonra GPU'da `VOICE_SRC=/tmp/voice-note-src/apps/voice-note /tmp/voice-note-src/deploy/tt-gpu/voice-note/install.sh`.
   Kontrol: `curl -s 127.0.0.1:8797/health` → `ready: true`; `find /data/voice-note/app -name '._*' | wc -l` → 0.
2. **Tünel (test sunucusu)**: test sunucusunda `/etc/ssh/sshd_config.d/60-editor-gpu-tunnel.conf` → `PermitListen`'e
   `127.0.0.1:18892` eklenir, `sshd -t && systemctl reload ssh`. GPU'da `voice-note-tunnel.service` →
   `/etc/systemd/system/`, `systemctl enable --now voice-note-tunnel`. Mevcut tünellere (18885 BI modeli) dokunulmaz.
3. **Köprü ortamı (test sunucusu)** `/etc/nanobase/semantic-bridge.env`: `VOICE_NOTE_URL=http://127.0.0.1:18892`,
   `VOICE_NOTE_TOKEN=<GPU'daki /data/voice-note/voice-note.env değeri>`. Portal nginx: `sudo python3 deploy/nanobase-direct/add-voice-note-route.py`.
   Yönetim › «Zeki AI sesli not» → «Sesli not açık». Kabul: `scripts/acceptance/voice-note/kabul.py` (timasai kısa oturumu,
   sahada okunmuş alan cümleleri).
4. **Müşteri VM'i** (yalnız test sunucusunda kabul geçince): GPU'da `sudo python3 add-voice-route.py` (**kullanıcı onayı**),
   VM `.env`: `VOICE_NOTE_URL=https://85.111.30.227/bi-voice`, `VOICE_NOTE_TOKEN`, `VOICE_NOTE_CA_FILE=/app/ad/gpu-editor-ca.pem`,
   `VOICE_NOTE_EXTRA_HEADER=X-Editor-Gate:<EDITOR_EXTRA_HEADER ile aynı değer>`; web ve köprü konteyneri yeniden oluşturulur.

## Telefon notu

Mikrofon (`getUserMedia`) yalnız güvenli bağlamda (https) açılır. Portal https değilse ya da tarayıcı mikrofonu
vermezse düğme «ses kaydı seç»e döner: telefonun kendi ses kaydedicisiyle kaydedilen dosya seçilir (Android'de
doğrudan kaydedici açılır; iPhone'da Ses Notları → Paylaş → Dosyalar'a kaydet → seç).
