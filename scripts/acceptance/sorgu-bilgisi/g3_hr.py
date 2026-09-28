"""Sorgu bilgisi kabulü · İK (test sunucusu, yan port köprüsü; yalnız okuma, hiçbir yere yazmaz).

Kayıtlar, işe alım, bağlılık, eğitim ve performans uçlarında K1–K3 (her portal SQL'i portal veritabanında, Logo metni
Logo'da koşar) ve:
  I1  İK kaynaklarında satır sayısı yok (gizlilik: sayı bir kişiyi / grubu ele verebilir);
  I2  «N çalışan» = çalışan sorgusunun (çalışan metin) satır sayısı;
  I3  «Açık pozisyon» = portal pozisyon kaydında durumu açık olan sayısı (doğrudan sorgu);
  I4  eğitim gideri «Gerçekleşen» = Logo gider sorgusunun Σ tutar'ı;
  I5  kapanmış her ankette eşik altı birim satırı «gizli» hesabına bağlı ve hesap metni rakam içermiyor.
Kimlik: timasai'nin kısa oturumu (İK anahtarları olan rol); anahtarı olmayan uç 403 → UYARI.
"""
from __future__ import annotations

import re

import sqlalchemy as sa

import kabul as KB

H = "/api/v1/hr"


def _rows_none(name: str, k: dict) -> None:
    bad = [sid for sid, s in (k.get("sources") or {}).items() if (s.get("stats") or {}).get("rows") is not None]
    KB.check(f"I1 {name}: satır sayısı yazılmıyor", not bad, ", ".join(bad[:5]))


def _one(path: str, heavy: bool, run: bool = True):
    st, out = KB.http(path, 1800)
    if st == 403:
        KB.check(f"ik {path}", None, "rolde yok")
        return None, None
    if st != 200:
        KB.check(f"ik {path}", False, f"HTTP {st}")
        return None, None
    k = KB.contract(f"ik {path}", out, ())
    _rows_none(path, k)
    got = KB.run_all(f"ik {path}", k, heavy) if run else {}
    return out, got


def main(heavy: bool) -> None:
    out, got = _one(f"{H}/employees", heavy)
    if out is not None:
        sel = [rows for sid, rows in got.items() if "calisan" in sid]
        if sel:
            KB.check("I2 ik: «N çalışan» = çalışan sorgusu satırı (fark: Python'da süzülen satır)",
                     True if out["total"] == max(len(r) for r in sel) else None,
                     f"ekran {out['total']} · sorgu {max(len(r) for r in sel)}")
    for p in ("units", "notices", "retention", "purge/preview", "purge/runs", "access-log"):
        _one(f"{H}/{p}", heavy)
    pipe, _ = _one(f"{H}/recruit/pipeline", heavy)
    if pipe is not None:
        with KB.portal().connect() as c:
            n = c.execute(sa.text("SELECT COUNT(*) FROM semantic_hr_positions WHERE state = 'acik'")).scalar()
        KB.check("I3 ik: «Açık pozisyon» = portal pozisyon kaydı (açık)", int(n or 0) == pipe["counters"]["openPositions"],
                 f"sorgu {n} · ekran {pipe['counters']['openPositions']}")
    for p in ("recruit/positions", "recruit/templates", "engagement/surveys", "engagement/trend", "engagement/suggestions",
              "engagement/me/surveys", "learning/dashboard", "learning/courses", "learning/sessions", "learning/needs",
              "learning/usage-map", "learning/guides", "learning/me", "learning/me/usage", "performance/me",
              "performance/team", "performance/goals", "performance/cycles"):
        _one(f"{H}/{p}", heavy)
    spend, sg = _one(f"{H}/learning/spend", heavy)
    if spend is not None and spend.get("configured"):
        logo = [rows for sid, rows in sg.items() if any(r.get("tutar") is not None for r in rows)]
        if logo:
            total = sum(KB.num(r.get("tutar")) for r in logo[0])
            KB.check("I4 ik: eğitim gideri = Logo gider sorgusu Σ", abs(total - KB.num(spend["total"])) < 0.05,
                     f"sorgu {total:,.2f} · ekran {spend['total']}")
    st, surveys = KB.http(f"{H}/engagement/surveys", 900)
    for s in (surveys.get("items") or [])[:20] if st == 200 else []:
        if s.get("state") != "kapandi":
            continue
        res, _ = _one(f"{H}/engagement/surveys/{s['id']}/results", heavy, run=False)
        if not res:
            continue
        k = res.get("kaynaklar") or {}
        hidden = [u for u in res.get("units") or [] if not u.get("shown")]
        bad = [u["unitId"] for u in hidden if (k.get("fields") or {}).get(f"units[]:{u['unitId']}") != "hesap:gizli"]
        text = ((k.get("formulas") or {}).get("gizli") or {}).get("text", "")
        KB.check(f"I5 ik: anket {s['id'][:8]} eşik altı birim «gizli»", not bad and not re.search(r"\d", text),
                 f"gizli olmayan {len(bad)} / {len(hidden)}")
    st, cycles = KB.http(f"{H}/performance/cycles", 900)
    for cy in (cycles.get("items") or [])[:5] if st == 200 else []:
        _one(f"{H}/performance/cycles/{cy['id']}/status", heavy)
        _one(f"{H}/performance/cycles/{cy['id']}/calibration", heavy)
