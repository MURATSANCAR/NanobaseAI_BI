# Editör GPU erişimi: Mac üzerinden mevcut VPN

18 Eylül 2026 canlı kontrolü. Erişim bilgisi projenin Claude kayıtlarındaki
`tt-gpu-servers.md` dosyasından bulundu. Parola ve VPN sırları bu belgeye alınmaz.

## Doğrulanan erişim

- Mac üzerinde openconnect ve ocproxy; SOCKS: `127.0.0.1:11080`.
- `tt-gpu` SSH tanımı bu SOCKS üzerinden GPU sunucusuna bağlanır.
- GPU sunucusu: `gpuubuntu`, iki NVIDIA H100 NVL, kart başına 95830 MiB.
- `qwen38-flash-next` konteyneri healthy; GPU localhost 8001 üzerinde
  `/health` ve `/v1/models` yanıt veriyor.
- Sunulan model adı `qwen3.8-flash-next`, ağırlık
  `Qwen/Qwen3.8-Flash-Next-FP8`, bildirilen bağlam 131072.

Doğrudan CPU sunucusundan GPU'nun özel IP'sine erişim başarısız olması,
Mac VPN yolunun kapalı olduğu anlamına gelmez.

## Bu oturumda kurulan yönlendirme

Mac'ten iki SSH yönlendirmesi kuruldu:

```sh
ssh -fNT -o BatchMode=yes -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
  -L 127.0.0.1:18081:127.0.0.1:8001 tt-gpu
ssh -fNT -o BatchMode=yes -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
  -R 127.0.0.1:18881:127.0.0.1:18081 nanobase-direct
```

CPU sunucusunda `http://127.0.0.1:18881/v1/models` üzerinden Flash-Next model
kimliği canlı doğrulandı. Dinleme adresleri yalnız loopback'tir.
Bu komutlar mevcut tüneller çalışırken tekrar başlatılmaz; port sahipliği kontrol edilir.

## Kabul sınırı ve kalan iş

Bu doğrulama taşıma tamamlandı veya kitap analizi geçti demek değildir.
Editör konteynerinin localhost'u sunucunun localhost'u değildir; Docker içinden
kontrollü erişim, yapılandırılabilir model adresi/adı ve gerçek kitap API/DB kabulü
henüz tamamlanmadı. Eski CPU model servisleri bu işlemde değiştirilmedi.

Mac/VPN/SSH oturumu kapanırsa bu yol kesilir. Otomatik yeniden başlatma servisi
kurulmadı; mevcut yönlendirme müşteri ortamı için Mac'ten bağımsız kalıcı ağ
kurulumunun yerine geçmez.
