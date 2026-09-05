# NanobaseAI BI LLM — GPU sunucusu

Docker kullanılmayan GPU makinesi için servis dosyaları. Docker'lı kurulumda bunun yerine
`deploy/compose` içindeki `gpu-llm` profili kullanılır (aynı bayraklar).

```bash
sudo ./install.sh      # llama.cpp (CUDA, MTP) derler, ağırlıkları indirir, systemd servisini kurar
```

| Dosya | Amaç |
|---|---|
| `install.sh` | Tek komut kurulum (derleme + indirme + servis + sağlık) |
| `nanobaseai-bi-llm.service` | systemd birimi (`/etc/systemd/system/`) |
| `nanobaseai-bi-llm.env.example` | Ayarlar (`/etc/nanobaseai/nanobaseai-bi-llm.env`) |

Üretim profili: greedy, düşünme kapalı, MTP-3 (Q8 taslak), 24K bağlam, tek akış.
API anahtarı `/etc/nanobaseai/nanobaseai-bi-llm.key` — BI paketinde `LLM_API_KEY`.

Servis yalnız `127.0.0.1:8011` dinler; BI sunucusundan erişim SSH tüneli ile:

```bash
ssh -NT -L 127.0.0.1:8020:127.0.0.1:8011 <kullanici>@<gpu-sunucu>   # BI tarafında LLM_API_BASE=http://127.0.0.1:8020/v1
```

Ölçüm (A40 46 GB, N_CPU_MOE=26): prompt ~300 tok/s, üretim ~23 tok/s, MTP kabul ~%80,
2.000 tokenlik plan prompt'u ~7 s.
