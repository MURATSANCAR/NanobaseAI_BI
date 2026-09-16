---
nl: 2026 yılında ortalama gerçekleşen tahsilat süresi kaç gün (fatura tarihinden kapatan ödemenin tarihine)
sql: SELECT AVG(CAST(DATEDIFF(day, i."DATE_", o."DATE_") AS float)) AS ortalama_tahsilat_gun,
  COUNT(*) AS kapanan_kalem FROM PAYTRANS p JOIN INVOICE i ON i."LOGICALREF" = p."FICHEREF"
  JOIN PAYTRANS o ON o."LOGICALREF" = p."CROSSREF" WHERE p."MODULENR" = 4 AND p."SIGN" = 0
  AND p."CANCELLED" = 0 AND i."CANCELLED" = 0 AND i."TRCODE" IN (7,8,9) AND i."DATE_" >= '2026-01-01'
  AND i."DATE_" < '2027-01-01'
source: user
tags:
- source:enrich
- is-teyidi-bekliyor:2026-09-16
---

Tahsilat süresi (gerçekleşen): satış faturasının (TRCODE 7, 8, 9; iptal hariç) ödeme planı satırı
(PAYTRANS, MODULENR 4 = fatura, SIGN 0 = borç) ile onu kapatan ödeme hareketi (PAYTRANS, CROSSREF ile
bağlı) arasındaki gün farkının ortalaması. Yalnız kapanmış kalemler sayılır; açık kalemler ortalamaya
girmez. Dönem fatura tarihine göre alınır. Bu tanım 2026-09-16'da test ölçümüne göre yazıldı, iş
tarafı teyidi bekliyor.
