#!/usr/bin/env python3
"""CFO özetini arka planda üretir.

Ekran açılışında sekiz sorgu koşturmak yerine bu betik dakikada bir çalışır ve
tek bir JSON yazar. Ekran o dosyayı okur: açılış anlık olur, veritabanı her
kullanıcı için yeniden yorulmaz.

Çıktı: /data/nanobaseai/bi/metrics/cfo.json
"""
import datetime as dt
import json
import os
import pathlib
import time
import urllib.error
import urllib.request

BRIDGE = os.environ.get("BRIDGE", "http://127.0.0.1:8795")
ENV = "/etc/nanobase/semantic-bridge.env"
OUT = pathlib.Path(os.environ.get("OUT", "/data/nanobaseai/bi/metrics/cfo.json"))

YEAR = dt.date.today().year
PREV = YEAR - 1
PERIOD = {2026: "LG_411", 2025: "LG_211", 2024: "LG_211", 2023: "LG_211"}
pfx = lambda y: PERIOD.get(y, "LG_411")

NET = "SUM(CASE WHEN I.[TRCODE] IN (7,8,9) THEN I.[NETTOTAL] ELSE -I.[NETTOTAL] END)"
F = "I.[CANCELLED]=0 AND I.[TRCODE] IN (2,3,7,8,9)"
rng = lambda y: f"I.[DATE_]>='{y}-01-01' AND I.[DATE_]<'{y + 1}-01-01'"

QUERIES = {
    "months": lambda y: f"SELECT MONTH(I.[DATE_]) AS ay, {NET} AS net_ciro, COUNT(*) AS fatura FROM [dbo].[{pfx(y)}_01_INVOICE] AS I WHERE {F} AND {rng(y)} GROUP BY MONTH(I.[DATE_]) ORDER BY ay",
    "prevMonths": lambda y: f"SELECT MONTH(I.[DATE_]) AS ay, {NET} AS net_ciro, COUNT(*) AS fatura FROM [dbo].[{pfx(PREV)}_01_INVOICE] AS I WHERE {F} AND {rng(PREV)} GROUP BY MONTH(I.[DATE_]) ORDER BY ay",
    "totals": lambda y: f"SELECT SUM(CASE WHEN I.[TRCODE] IN (7,8,9) THEN I.[NETTOTAL] ELSE 0 END) AS brut_satis, SUM(CASE WHEN I.[TRCODE] IN (2,3) THEN I.[NETTOTAL] ELSE 0 END) AS iade_tutari, SUM(CASE WHEN I.[TRCODE] IN (2,3) THEN 1 ELSE 0 END) AS iade_fatura, COUNT(*) AS toplam_fatura, MAX(I.[DATE_]) AS son_fatura FROM [dbo].[{pfx(y)}_01_INVOICE] AS I WHERE {F} AND {rng(y)}",
    "units": lambda y: f"SELECT SUM(CASE WHEN L.[TRCODE] IN (7,8,9) THEN L.[AMOUNT] ELSE -L.[AMOUNT] END) AS satilan_adet, COUNT(DISTINCT L.[STOCKREF]) AS baslik_sayisi, COUNT(*) AS satir FROM [dbo].[{pfx(y)}_01_STLINE] AS L WHERE L.[CANCELLED]=0 AND L.[LINETYPE]=0 AND L.[TRCODE] IN (2,3,7,8,9) AND L.[DATE_]>='{y}-01-01' AND L.[DATE_]<'{y + 1}-01-01'",
    "channels": lambda y: f"SELECT I.[TRCODE] AS trcode, {NET} AS net_ciro, COUNT(*) AS fatura FROM [dbo].[{pfx(y)}_01_INVOICE] AS I WHERE {F} AND {rng(y)} GROUP BY I.[TRCODE] ORDER BY net_ciro DESC",
    "customers": lambda y: f"SELECT TOP 5 C.[DEFINITION_] AS cari, {NET} AS net_ciro FROM [dbo].[{pfx(y)}_01_INVOICE] AS I INNER JOIN [dbo].[{pfx(y)}_CLCARD] AS C ON C.[LOGICALREF]=I.[CLIENTREF] WHERE {F} AND {rng(y)} GROUP BY C.[DEFINITION_] ORDER BY net_ciro DESC",
    "items": lambda y: f"SELECT TOP 8 IT.[NAME] AS urun, IT.[CODE] AS kod, SUM(CASE WHEN L.[TRCODE] IN (7,8,9) THEN L.[AMOUNT] ELSE -L.[AMOUNT] END) AS adet, SUM(CASE WHEN L.[TRCODE] IN (7,8,9) THEN L.[LINENET] ELSE -L.[LINENET] END) AS net_ciro FROM [dbo].[{pfx(y)}_01_STLINE] AS L INNER JOIN [dbo].[{pfx(y)}_ITEMS] AS IT ON IT.[LOGICALREF]=L.[STOCKREF] WHERE L.[CANCELLED]=0 AND L.[LINETYPE]=0 AND L.[TRCODE] IN (2,3,7,8,9) AND L.[DATE_]>='{y}-01-01' AND L.[DATE_]<'{y + 1}-01-01' GROUP BY IT.[NAME], IT.[CODE] ORDER BY adet DESC",
    "returnItems": lambda y: f"SELECT TOP 6 IT.[NAME] AS urun, IT.[CODE] AS kod, SUM(L.[AMOUNT]) AS iade_adet, SUM(L.[LINENET]) AS iade_tutar FROM [dbo].[{pfx(y)}_01_STLINE] AS L INNER JOIN [dbo].[{pfx(y)}_ITEMS] AS IT ON IT.[LOGICALREF]=L.[STOCKREF] WHERE L.[CANCELLED]=0 AND L.[LINETYPE]=0 AND L.[TRCODE] IN (2,3) AND L.[DATE_]>='{y}-01-01' AND L.[DATE_]<'{y + 1}-01-01' GROUP BY IT.[NAME], IT.[CODE] ORDER BY iade_tutar DESC",
}


def token() -> str:
    with open(ENV) as fh:
        for line in fh:
            if line.startswith("SEMANTIC_CALLER_TOKEN="):
                return line.split("=", 1)[1].strip()
    raise SystemExit("caller token bulunamadi")


def run(sql: str, tok: str) -> list:
    body = json.dumps({"sql": sql, "limit": 200}).encode()
    req = urllib.request.Request(
        f"{BRIDGE}/api/v1/run_sql",
        data=body,
        headers={"Content-Type": "application/json", "X-Semantic-Caller": tok},
    )
    with urllib.request.urlopen(req, timeout=180) as res:
        return json.load(res).get("records", [])


def main() -> int:
    tok = token()
    out = {"year": YEAR, "prevYear": PREV, "generatedAt": dt.datetime.now().isoformat(timespec="seconds")}
    errors = {}
    t0 = time.time()
    for name, make in QUERIES.items():
        try:
            out[name] = run(make(YEAR), tok)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            # Bir sorgu patlarsa öncekiler korunur; ekran eksik kartı boş gösterir.
            errors[name] = str(exc)[:200]
    out["elapsedMs"] = int((time.time() - t0) * 1000)
    if errors:
        out["errors"] = errors
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(out, ensure_ascii=False))
    tmp.replace(OUT)  # atomik: yarım dosya okunmaz
    OUT.chmod(0o644)
    print(f"yazildi {OUT} · {out['elapsedMs']} ms · hata {len(errors)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
