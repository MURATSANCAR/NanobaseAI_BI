# İki karta tek kapı (LLM dağıtıcı)

Kullanıcı kararı 2026-09-23: kitap okunmuyorken GPU 1'deki görsel model durur, yerine ana model
kalkar ve o da prompt'lara cevap verir — aynı anda yazan kullanıcılar sıra beklemez.

```
BI / müşteri VM ──CPU 127.0.0.1:18885 (ters tünel)──► llm-dispatch :8010 ─┬─► GPU 0 qwen38-27b (hep açık)
                                                                          └─► GPU 1 editor-model-director (analiz yokken)
```

- İki kartta aynı ağırlıklar (Qwen3.8-27B-FP8). GPU 1'deki model `models.yaml`'daki `also_serves`
  sayesinde `nanobaseAI` adına da cevap verir.
- `least_conn`: istek en az meşgul karta gider. GPU 1 analize geçince editörün geçidi modeli durdurur;
  dağıtıcı adı çözemez ya da bağlantı reddedilir, istek aynı anda GPU 0'a geçer — kullanıcı hata görmez.
- Bilinen sınır: analiz tam o anda kartı alırsa GPU 1'de **yazılmakta olan** bir cevap kesilir (başlamış
  cevap başka karta taşınamaz). Başlamamış istekler etkilenmez.
- Hangi kartın cevap verdiği `X-Served-By` başlığında.

Kurulum: `sudo bash /data/editor/llm-dispatch/install.sh` (koşan analiz varsa durur).
Geri alma: `sudo bash /data/editor/llm-dispatch/rollback.sh` — tünel yeniden doğrudan GPU 0'a (8001).
