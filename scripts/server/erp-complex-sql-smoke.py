#!/usr/bin/env python3
"""Execute 10 complex ERP SQLs via Query Gateway (same intents as NL prompts)."""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

QG = "http://127.0.0.1:8792"
DS = "erp"

CASES: list[dict[str, str]] = [
    {
        "id": "P01",
        "title": "YoY AR vs AP + collection",
        "sql": """
WITH years AS (
  SELECT 2025 AS y UNION ALL SELECT 2026
),
ar AS (
  SELECT EXTRACT(YEAR FROM fatura_tarihi)::int AS y, COALESCE(SUM(genel_toplam),0) AS ciro
  FROM faturalar WHERE EXTRACT(YEAR FROM fatura_tarihi) IN (2025,2026)
  GROUP BY 1
),
ap AS (
  SELECT EXTRACT(YEAR FROM fatura_tarihi)::int AS y, COALESCE(SUM(genel_toplam),0) AS gider
  FROM alis_faturalari WHERE EXTRACT(YEAR FROM fatura_tarihi) IN (2025,2026)
  GROUP BY 1
),
col AS (
  SELECT EXTRACT(YEAR FROM odeme_tarihi)::int AS y, COALESCE(SUM(tutar),0) AS tahsilat
  FROM tahsilatlar WHERE EXTRACT(YEAR FROM odeme_tarihi) IN (2025,2026)
  GROUP BY 1
)
SELECT y.y, COALESCE(ar.ciro,0) AS ar_ciro, COALESCE(ap.gider,0) AS ap_gider,
       COALESCE(col.tahsilat,0) AS tahsilat
FROM years y
LEFT JOIN ar ON ar.y=y.y LEFT JOIN ap ON ap.y=y.y LEFT JOIN col ON col.y=y.y
ORDER BY y.y
""".strip(),
    },
    {
        "id": "P02",
        "title": "Budget vs AP by code OPEX",
        "sql": """
SELECT b.departman_kod, b.butce_kodu, b.kalem_adi, b.planlanan_tutar,
       COALESCE(SUM(a.genel_toplam),0) AS gerceklesen,
       b.planlanan_tutar - COALESCE(SUM(a.genel_toplam),0) AS fark,
       CASE WHEN b.planlanan_tutar=0 THEN NULL
            ELSE ROUND(100.0*COALESCE(SUM(a.genel_toplam),0)/b.planlanan_tutar,2) END AS kullanim_pct
FROM butce_planlari b
LEFT JOIN alis_faturalari a
  ON a.butce_kodu=b.butce_kodu AND EXTRACT(YEAR FROM a.fatura_tarihi)=b.mali_yil
WHERE b.mali_yil=2026 AND LOWER(b.tur)='opex'
GROUP BY b.id, b.departman_kod, b.butce_kodu, b.kalem_adi, b.planlanan_tutar
ORDER BY kullanim_pct DESC NULLS LAST
LIMIT 50
""".strip(),
    },
    {
        "id": "P03",
        "title": "Category margin last 12m",
        "sql": """
SELECT COALESCE(k.ad,'(yok)') AS kategori, COALESCE(m.ad,'(yok)') AS marka,
       SUM(fk.tutar) AS ciro, SUM(fk.miktar) AS miktar,
       SUM((fk.birim_fiyat - COALESCE(u.alis_fiyat,0)) * fk.miktar) AS kaba_marj
FROM fatura_kalemleri fk
JOIN faturalar f ON f.id=fk.fatura_id
JOIN urunler u ON u.id=fk.urun_id
LEFT JOIN urun_kategorileri k ON k.id=u.kategori_id
LEFT JOIN markalar m ON m.id=u.marka_id
WHERE f.fatura_tarihi >= (CURRENT_DATE - INTERVAL '12 months')
  AND LOWER(COALESCE(f.durum,'')) NOT LIKE '%iptal%'
GROUP BY 1,2
ORDER BY ciro DESC NULLS LAST
LIMIT 40
""".strip(),
    },
    {
        "id": "P04",
        "title": "PO to invoice lag by supplier",
        "sql": """
SELECT t.unvan,
       COUNT(DISTINCT s.id) AS siparis_adet,
       COUNT(DISTINCT a.id) AS fatura_adet,
       ROUND(AVG(EXTRACT(EPOCH FROM (a.fatura_tarihi::timestamp - s.siparis_tarihi::timestamp))/86400.0)::numeric,2) AS ort_gun,
       COUNT(DISTINCT s.id) FILTER (WHERE a.id IS NULL) AS faturasiz_siparis
FROM satin_alma_siparisleri s
JOIN tedarikciler t ON t.id=s.tedarikci_id
LEFT JOIN alis_faturalari a ON a.siparis_id=s.id
WHERE EXTRACT(YEAR FROM s.siparis_tarihi)=2026
GROUP BY t.id, t.unvan
ORDER BY ort_gun DESC NULLS LAST
LIMIT 40
""".strip(),
    },
    {
        "id": "P05",
        "title": "Dead stock top 15",
        "sql": """
WITH moves AS (
  SELECT depo_id, urun_id, SUM(miktar) AS cikis_90
  FROM stok_hareketleri
  WHERE hareket_tarihi >= (CURRENT_DATE - INTERVAL '90 days')
  GROUP BY 1,2
)
SELECT d.ad AS depo, u.stok_kodu, u.ad AS urun,
       (sb.miktar - COALESCE(sb.rezervasyon,0)) AS net_stok,
       COALESCE(m.cikis_90,0) AS cikis_90,
       ROUND(((sb.miktar - COALESCE(sb.rezervasyon,0)) * COALESCE(u.alis_fiyat,0))::numeric,2) AS stok_tutar
FROM stok_bakiyeleri sb
JOIN urunler u ON u.id=sb.urun_id
JOIN depolar d ON d.id=sb.depo_id
LEFT JOIN moves m ON m.depo_id=sb.depo_id AND m.urun_id=sb.urun_id
WHERE (sb.miktar - COALESCE(sb.rezervasyon,0)) > 0 AND COALESCE(m.cikis_90,0)=0
ORDER BY stok_tutar DESC NULLS LAST
LIMIT 15
""".strip(),
    },
    {
        "id": "P06",
        "title": "Customer share + risk limit",
        "sql": """
WITH ciro AS (
  SELECT musteri_id, SUM(genel_toplam) AS tutar
  FROM faturalar WHERE EXTRACT(YEAR FROM fatura_tarihi)=2026
  GROUP BY 1
),
tot AS (SELECT SUM(tutar) AS yil_toplam FROM ciro),
tah AS (
  SELECT musteri_id, SUM(tutar) AS tahsilat FROM tahsilatlar
  WHERE EXTRACT(YEAR FROM odeme_tarihi)=2026 GROUP BY 1
)
SELECT m.unvan, c.tutar AS ciro,
       ROUND(100.0*c.tutar/NULLIF(t.yil_toplam,0),2) AS pay_pct,
       c.tutar - COALESCE(tah.tahsilat,0) AS acik_bakiye,
       m.risk_limit,
       CASE WHEN m.risk_limit IS NOT NULL AND (c.tutar - COALESCE(tah.tahsilat,0)) > m.risk_limit
            THEN true ELSE false END AS limit_asim
FROM ciro c
JOIN musteriler m ON m.id=c.musteri_id
CROSS JOIN tot t
LEFT JOIN tah ON tah.musteri_id=c.musteri_id
ORDER BY c.tutar DESC
LIMIT 15
""".strip(),
    },
    {
        "id": "P07",
        "title": "Branch revenue per headcount",
        "sql": """
WITH fat AS (
  SELECT sube_id, SUM(genel_toplam) AS ciro, COUNT(*) AS fatura_adet
  FROM faturalar WHERE EXTRACT(YEAR FROM fatura_tarihi)=2026 GROUP BY 1
),
sip AS (
  SELECT sube_id, COUNT(*) AS siparis_adet
  FROM satis_siparisleri WHERE EXTRACT(YEAR FROM siparis_tarihi)=2026 GROUP BY 1
),
per AS (
  SELECT sube_id, COUNT(*) FILTER (WHERE aktif IS TRUE) AS aktif_personel
  FROM personeller GROUP BY 1
)
SELECT s.kod, s.ad,
       COALESCE(f.ciro,0) AS ciro,
       COALESCE(sip.siparis_adet,0) AS siparis_adet,
       COALESCE(p.aktif_personel,0) AS aktif_personel,
       CASE WHEN COALESCE(p.aktif_personel,0)=0 THEN NULL
            ELSE ROUND((COALESCE(f.ciro,0)/p.aktif_personel)::numeric,2) END AS kisi_basi_ciro
FROM subeler s
LEFT JOIN fat f ON f.sube_id=s.id
LEFT JOIN sip ON sip.sube_id=s.id
LEFT JOIN per p ON p.sube_id=s.id
ORDER BY kisi_basi_ciro DESC NULLS LAST
""".strip(),
    },
    {
        "id": "P08",
        "title": "GL credit vs invoice by month",
        "sql": """
WITH gl AS (
  SELECT EXTRACT(MONTH FROM f.fis_tarihi)::int AS ay, SUM(k.alacak) AS gl_alacak
  FROM yevmiye_fisleri f
  JOIN yevmiye_kalemleri k ON k.fis_id=f.id
  JOIN hesap_planlari h ON h.id=k.hesap_id
  WHERE EXTRACT(YEAR FROM f.fis_tarihi)=2026
    AND (LOWER(h.ad) LIKE '%gelir%' OR LOWER(h.ad) LIKE '%sat%' OR LOWER(COALESCE(h.tip,'')) LIKE '%gelir%')
  GROUP BY 1
),
inv AS (
  SELECT EXTRACT(MONTH FROM fatura_tarihi)::int AS ay, SUM(genel_toplam) AS fatura_toplam
  FROM faturalar WHERE EXTRACT(YEAR FROM fatura_tarihi)=2026 GROUP BY 1
)
SELECT COALESCE(gl.ay, inv.ay) AS ay,
       COALESCE(gl.gl_alacak,0) AS gl_alacak,
       COALESCE(inv.fatura_toplam,0) AS fatura_toplam,
       COALESCE(gl.gl_alacak,0) - COALESCE(inv.fatura_toplam,0) AS fark
FROM gl FULL OUTER JOIN inv ON gl.ay=inv.ay
ORDER BY 1
""".strip(),
    },
    {
        "id": "P09",
        "title": "Price list leakage",
        "sql": """
SELECT u.ad AS urun, f.fatura_no, fk.birim_fiyat AS satis_fiyat, flk.fiyat AS liste_fiyat,
       ROUND((100.0*(flk.fiyat-fk.birim_fiyat)/NULLIF(flk.fiyat,0))::numeric,2) AS iskonto_pct,
       ROUND(((flk.fiyat-fk.birim_fiyat)*fk.miktar)::numeric,2) AS kayip
FROM fatura_kalemleri fk
JOIN faturalar f ON f.id=fk.fatura_id
JOIN urunler u ON u.id=fk.urun_id
JOIN fiyat_listesi_kalemleri flk ON flk.urun_id=fk.urun_id
JOIN fiyat_listeleri fl ON fl.id=flk.liste_id AND fl.aktif IS TRUE
WHERE EXTRACT(YEAR FROM f.fatura_tarihi)=2026
  AND fk.birim_fiyat < flk.fiyat * 0.90
ORDER BY kayip DESC NULLS LAST
LIMIT 20
""".strip(),
    },
    {
        "id": "P10",
        "title": "CAPEX plan vs AP vs open PO",
        "sql": """
WITH ap AS (
  SELECT butce_kodu, SUM(genel_toplam) AS gerceklesen
  FROM alis_faturalari
  WHERE EXTRACT(YEAR FROM fatura_tarihi)=2026 AND butce_kodu IS NOT NULL
  GROUP BY 1
),
po AS (
  SELECT a.butce_kodu, SUM(sk.tutar) AS acik_po
  FROM satin_alma_siparisleri s
  JOIN satin_alma_kalemleri sk ON sk.siparis_id=s.id
  LEFT JOIN alis_faturalari a ON a.siparis_id=s.id
  WHERE EXTRACT(YEAR FROM s.siparis_tarihi)=2026
  GROUP BY 1
)
SELECT b.butce_kodu, b.kalem_adi, b.planlanan_tutar,
       COALESCE(ap.gerceklesen,0) AS gerceklesen,
       COALESCE(po.acik_po,0) AS acik_po,
       b.planlanan_tutar - COALESCE(ap.gerceklesen,0) - COALESCE(po.acik_po,0) AS kalan
FROM butce_planlari b
LEFT JOIN ap ON ap.butce_kodu=b.butce_kodu
LEFT JOIN po ON po.butce_kodu=b.butce_kodu
WHERE b.mali_yil=2026 AND LOWER(b.tur)='capex'
ORDER BY kalan ASC
LIMIT 50
""".strip(),
    },
]


def qg_execute(sql: str) -> dict[str, Any]:
    body = {"datasource_id": DS, "sql": sql, "tenant_id": "default"}
    last_err = None
    for path in ("/api/v1/query/execute", "/internal/v1/queries/execute"):
        try:
            req = urllib.request.Request(
                f"{QG}{path}",
                data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, dict):
                    data.setdefault("ok", True)
                return data
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:400]
            except Exception:
                detail = str(exc)
            last_err = f"HTTP {exc.code}: {detail}"
        except Exception as exc:  # noqa: BLE001
            last_err = f"{type(exc).__name__}: {exc}"
    return {"ok": False, "error": str(last_err)[:400]}


def main() -> int:
    # discover execute endpoint via openapi if needed
    print(f"# ERP complex SQL smoke — {datetime.now(timezone.utc).isoformat()}", flush=True)
    results = []
    for i, c in enumerate(CASES, 1):
        print(f"\n== [{i}/10] {c['id']} {c['title']} ==", flush=True)
        t0 = time.time()
        out = qg_execute(c["sql"])
        elapsed = round(time.time() - t0, 2)
        ok = bool(out.get("ok"))
        err = out.get("error") or out.get("message")
        rows = out.get("rows") or []
        cols = out.get("columns") or []
        status = "PASS" if ok else "FAIL"
        print(f"→ {status} {elapsed}s rows={len(rows) if ok else None} cols={len(cols) if ok else None}", flush=True)
        if err:
            print(f"ERR: {str(err)[:300]}", flush=True)
        elif rows:
            print(f"SAMPLE: {json.dumps(rows[0], ensure_ascii=False, default=str)[:240]}", flush=True)
        results.append(
            {
                "id": c["id"],
                "title": c["title"],
                "elapsed_s": elapsed,
                "ok": ok,
                "row_count": len(rows) if ok else None,
                "columns": cols if ok else None,
                "error": str(err)[:400] if err else None,
                "sample": rows[0] if ok and rows else None,
            }
        )
    summary = {
        "total": len(results),
        "pass": sum(1 for r in results if r["ok"]),
        "fail": sum(1 for r in results if not r["ok"]),
    }
    payload = {
        "finished": datetime.now(timezone.utc).isoformat(),
        "datasource": DS,
        "results": results,
        "summary": summary,
    }
    with open("/tmp/erp-complex-sql-smoke.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n# SUMMARY {summary}", flush=True)
    return 0 if summary["fail"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
