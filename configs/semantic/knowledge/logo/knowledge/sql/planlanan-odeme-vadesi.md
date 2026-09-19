---
nl: 2026 yılında satış faturalarında planlanan ortalama ödeme vadesi kaç gün (fatura tarihinden vade tarihine)
sql: SELECT AVG(CAST(DATEDIFF(day, i."DATE_", p."DATE_") AS float)) AS planlanan_vade_gun,
  COUNT(*) AS plan_kalemi FROM PAYTRANS p JOIN INVOICE i ON i."LOGICALREF" = p."FICHEREF"
  WHERE p."MODULENR" = 4 AND p."SIGN" = 0 AND p."CANCELLED" = 0 AND i."CANCELLED" = 0
  AND i."TRCODE" IN (7,8,9) AND i."DATE_" >= '2026-01-01' AND i."DATE_" < '2027-01-01'
source: user
tags:
- source:enrich
- is-teyidi-bekliyor:2026-09-16
---

Planlanan ödeme vadesi: satış faturasının ödeme planı satırındaki vade tarihi (PAYTRANS.DATE_,
MODULENR 4, SIGN 0) ile fatura tarihi arasındaki gün farkının ortalaması. Gerçekleşen tahsilat
süresinden farklıdır: bu, anlaşılan vadedir; o, paranın gerçekten geldiği gündür.
