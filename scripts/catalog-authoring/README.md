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
| 2026-09-29-etkinlik-fuar-gideri.py | «etkinlik ve fuar gideri» METRIC (Logo EMFLINE Σ(borç − alacak), iptal hariç, KEBIRCODE 740/760/770, hesaplar 740.03, 760.44.444–446, 760.45, 760.47.470/477, 770.44.444, 770.47.472); eş anlamlı «etkinlik gideri/giderleri», «fuar gideri»…; yansıtma fişi hariç (`extra.exclude_groups`: aynı ACCFICHEREF'te ACCOUNTCODE LIKE '7_1%'); CRM etkinlik kartı gideri «crm etkinlik kartı gideri» adına daraltılır. `--olc` bu yıl ve geçen yıl, yansıtma hariç/dahil (tam kapı 09-29, koordinatör kararı: kayıt sistemi Logo) | hızlı kapıda fark B064 ve A044; tam kapı Q63 referans 2026 = 4.831.871,56 — DOĞRULANAMADI, koordinatörde |
| 2026-09-29-kitap-yazari-crm.py | ZEKI-54: `kitap yazarı` (eş: kitabın yazarı, yazar adı; çıplak «yazar» yalnız `--kisa-ad`) → CRM CONTACTBASE.FullName, eser katılımı rol «Yazar», statecode 0; önce CRM/Logo salt okunur ölçüm (stok kodu ↔ ITEMS.CODE eşleşmesi) ve ölçülmüş `cross_source` bağ denetimi | henüz koşulmadı; `--kisa-ad` sözleşme sorularındaki «yazar» (Kural C9 hak sahibi) okumasını değiştirebilir — hızlı kapı önce/sonra |
| 2026-09-30-seyrek-olcu-kapsami.py | Sertifikalı METRIC formülünün topladığı, profilde bütün kopyalarda çoğunlukla boş kolonu (≥ %90) kaynağında ölçer (ölçünün kendi koşullarıyla toplam / dolu kayıt, dolu tutar, dolu kayıtların tarih aralığı) ve dolu pay < %10 ise «VERİ NOTU:» kolon açıklamasını bu sayılardan kurar; köprü o kolonu toplayan her cevabın `dataNotes`'una taşır (A044 sınıfı, soruya özel değil). Yıl kopyalı tablolar atlanır | kuru koşu 2026-09-30: 1 aday — `new_ToplamEtkinlikGideri` 57.972 kaydın 28'i dolu, 2015-10-16 – 2016-07-21, 9.275; okuma farkı yok (yalnız not) — `--apply` koordinatörde |
| 2026-09-29-ay-kolonu-gruplari.py | Ay kolonu grupları (K13): 12 ay kolonlu tablonun sertifikalı ENTITY eşlemesine `extra.month_columns` (ay → kolon) + `month_missing` (girilmemiş ay: dolu kayıtlarda boş ay NULL mı 0 mı, veriden). Adaylar profilden (ay adı ya da dönem sözlü 1–12 soneki, 12 sayısal kolon; sıra listeleri elenir); `--json` yan köprü denemesi (`SEMANTIC_MONTH_GROUPS_FILE`), `--exclude` yanlış aday. Derleyici sanal `ay/ay_adi/ay_degeri` kolonlarını CROSS APPLY VALUES açılımına çevirir, kapı eksik el açılımını onarıma yollar | kuru koşu: 7 aday, 2 yazılacak (CRM satış hedefi, AccountBase), 5 Logo görünümü/eski tablo yersiz; yan köprüde Q65 3/3 SAĞLAM |
