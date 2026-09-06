---
nl: "Yayınevi bazında net ciro ve brüt kâr marjı nedir?"
sql: |
  SELECT yayinevi, baslik, net_ciro, satilan_adet, iade_adet, 1 - maliyet / NULLIF(maliyetli_ciro, 0) AS brut_kar_marji FROM v_imprint_perf ORDER BY net_ciro DESC
source: verified-view-2026-09-06
datasource: logo-tunnel
---
