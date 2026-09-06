---
name: logo-erp-dataset-timas
description: Logo ERP (LOGO_DB @192.168.0.155) veri yerleşimi — firma/dönem parçalanması, TRCODE anlamları ve analiz tuzakları
metadata:
  type: project
---

Müşteri Logo Tiger veritabanı `LOGO_DB` (MSSQL 2019, 192.168.0.155:1433, creds `configs/.env.local`) — Timaş Basım (yayıncılık/matbaa). 5.888 tablo, 1.837 view.

Firma = yıl snapshot'ı: 15/16/105/115=2015-16, 171=2017, 181=2018, 191=2019, 201=2020, **211=2021-2025 (tek dönem)**, **411=2026 (güncel)**. Çok yıllı analiz firma UNION'u ister; `LOGICALREF` firmalar arası farklı, ortak anahtar `CODE` (CLCARD %99,5 / ITEMS %92 örtüşür).

Bu kurulumda doğrulanmış TRCODE anlamları (repo'daki `configs/mssql-schema-hints.example.json` ve `tools/schema-indexer/scanner/mssql.py` bunu **yanlış** yazıyor — 3'ü "alış iade", 6'yı "satış iade" sanıyor):
- INVOICE: 1=mal alım, 3=**toptan satış iade**, 4=alınan hizmet, 6=**alım iade**, 7=perakende satış, 8=toptan satış, 9=verilen hizmet. Doğrulama: 2026 TR=3 toplamı 73,96M ≈ GL 610 hesabı 71,03M.
- ORFICHE: bu kurulumda TR=1 fişleri satış siparişi (e-ticaret/pazaryeri kanalı).

Analiz tuzakları: satır bazlı ciro = LINETYPE 0 − LINETYPE 2 (iskonto satırları ciro kadar büyük, ~%46); `OUTCOST` **birim** maliyet (ciro ile kıyaslamak için AMOUNT ile çarp); maliyetlendirme aylık gecikmeli (2026'da Temmuz-Ağustos boş); `STINVTOT` boş, stok LV_ view'ları/STLINE'dan hesaplanır; `PAYTRANS.PAID` beslenmiyor (yaşlandırma için kullanılamaz).

Boyutlar: `CLCARD.SPECODE2` = satış kanalı (KITAPCI/E-TICARET/DAGITICI/ZINCIR/KURUM…, cironun %96'sı dolu), `ITEMS.SPECODE` = yayınevi (10 karakterde kesik, normalize gerekir), SALESMANREF %83-88 dolu, DEPARTMENT/PROJECTREF hiç kullanılmıyor.

İlgili: [[feedback-customer-db-read-only]]
