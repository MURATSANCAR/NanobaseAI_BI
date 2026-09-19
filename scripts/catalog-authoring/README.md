# Katalog yazım betikleri

Kalite kapısının (tests/text2sql/answer-gate.py) gösterdiği sözlük boşluklarını kapatan, **ürünün kendi
store API'siyle** çalışan idempotent betikler. Ham SQL yok; her kavram `human_certify` ile yazılır ki gece
motoru geri almasın. İmza: `operator:claude (iş teyidi bekliyor)` — iş tarafı teyit edince imza değişir.

Koşu (köprünün ortamıyla, sunucuda):

    sudo systemd-run --pipe --wait --collect -p User=administrator \
      -p EnvironmentFile=/etc/nanobase/semantic-bridge.env \
      -E PYTHONPATH=/data/nanobaseai/bi/frontend/backend \
      /data/nanobaseai/bi/semantic-venv/bin/python - [--apply] < betik.py

`--apply` yoksa kuru koşudur (yalnız ne yazacağını basar). Yazdıktan sonra: köprüyü yenile →
`resolver-gate.py` (yalnız hedeflenen soruların okuması değişmeli) → `answer-gate.py --only …`.

| Betik | Ne ekler | Kapı sonucu |
|---|---|---|
| 2026-09-20-hedef-es-anlamlilari.py | `hedef / satış hedefi / toplam hedef` → `yıllık hedef` (NEW_TOPLAMHEDEF) | Q65, Q69 SAĞLAM; yalnız 3 hedef sorusu etkilendi |
| 2026-09-20-uretim-suresi-ve-dengesizlik.py | iş istasyonu (WORKSTAT), operasyon süreleri (DISPLINE), dengesizlik katsayısı (CV) | Q36 SAĞLAM; Q10 yanlış CRM cevabından dürüst redde; yalnız 2 soru etkilendi |
