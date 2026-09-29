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
| 2026-09-20-sozlesme-hak-sahibi.py | `sözleşme sahibi` (→ ACCOUNTBASE.Name, eş anlamlı 'hak sahibi / yazarlara göre') REDDEDİLİR: kolon yazar değil, imzalayan grup şirketimiz (Kural C9 düzeltmesi) | hızlı kapıda bu kavrama bağlı okuma yok; 'en çok sözleşmesi olan yazar' ve 'hak sahiplerine göre' canlı CRM referansıyla eş |
| 2026-09-28-sohbet-portal-verisi.py | Logo/CRM kataloğundan AYRI sohbet kataloğu (`semantic_chat_portal_catalog`): modüllerin kendi tabloları alan alan profillenir (ölçü/boyut/tarih/dışarıda, veriyle doğrulanan üst tablo bağı); `--apply` aday, `--certify` onay. Kişisel/gizli/serbest metin kolonu ve İK tablosu profile girmez | Logo/CRM sözlüğüne dokunmaz: hızlı kapıda okuma farkı 0 beklenir; önce/sonra adımları scripts/acceptance/sohbet-modul-verisi |
| 2026-09-29-kayit-adi-kolonlari.py | Kaydın ADI olan COLUMN eşlemelerine `record_label: true` (kaydı anan kelime = kolon kavramının adı; metin, kod kümesi değil). Derleyici o kırılımda kart anahtarını GROUP BY'a ekler, istem «anahtarıyla grupla» der (tam kapı 09-29 K5, C015) | hızlı kapıda okuma farkı 0 beklenir; tam kapı Q11 (2.402 satır) — DOĞRULANAMADI, koordinatörde |
