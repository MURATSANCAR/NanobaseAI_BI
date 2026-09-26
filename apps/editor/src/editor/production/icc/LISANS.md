# Baskı provası renk profilleri — kaynak ve lisans

Stüdyonun «3B ve prova» ekranı (`production/proof.py`) sayfa görüntüsünü bu profillerle kâğıda basılmış hâline
çevirir. Dosyalar değiştirilmeden kopyalanmıştır.

| Dosya | Kâğıt (ekrandaki ad) | Basım koşulu | SHA-256 |
|---|---|---|---|
| `FOGRA39L_coated.icc` | Kuşe, Mat kuşe | ISO 12647-2 kâğıt türü 1/2 (parlak ve mat kaplamalı), FOGRA39 karakterizasyon verisi | `3ff7ca2a650ad47a8d2a929eb23ef162ccf979d013ade56e441c1f55156a261f` |
| `FOGRA47L_uncoated.icc` | 1. hamur (ofset) | ISO 12647-2 kâğıt türü 4 (kaplamasız beyaz), FOGRA47 | `60150fc527a946b8dcee957db4f6d4e57592eb05ded55352b0cfa10e4c34b1b9` |
| `FOGRA30L_uncoated_yellowish.icc` | Şamua | ISO 12647-2 kâğıt türü 5 (kaplamasız sarımsı), FOGRA30 | `f7efb003871198f93e4420fa301be6243aef9c7b5dd22c8bc516ef0a70aecadf` |

**Kaynak:** colord projesinin profil verisi (https://www.freedesktop.org/software/colord/), Ubuntu 24.04 resmî
deposundaki `colord-data` 1.4.7-1build2 paketi (`/usr/share/color/icc/colord/`). İnternetten ayrıca indirilmedi;
TT GPU sunucusunda kurulu resmî paketten alındı, SHA-256 değerleri paket dosyalarıyla aynı.

**Lisans:** CC0-1.0 (kamu malı). Paketin `copyright` dosyası: `Files: data/profiles/*` → `License: CC0-1.0`
(© 2012 Richard Hughes). Profillerin kendi telif etiketi: «This profile is free of known copyright restrictions».
Profiller, FOGRA'nın serbestçe yayımladığı karakterizasyon verisinden colord araçlarıyla üretilmiştir; ticari
kullanım ve yeniden dağıtım serbesttir, atıf zorunlu değildir (yine de burada kaynak yazılıdır).

**Sınırlar (bilerek):**
- Parlak ve mat kuşe aynı basım standardına (kâğıt türü 1/2) bağlıdır, renk provası ikisinde aynıdır; fark yüzey
  parlaklığıdır ve 3B görünümde malzeme olarak gösterilir.
- Bu profiller ekran provası içindir. Matbaaya giden baskı PDF'i matbaanın profiliyle (`EDITOR_CMYK_ICC`) üretilir;
  matbaa profili verildiğinde prova da ona göre yapılmalıdır (açık iş).
