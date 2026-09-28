"""Tahmin istemcisi — tek yer (ortak yapı taşı 6; docs/analiz/ai-firsatlari/README.md).

Baskı Öneri'nin gecelik tahmin işi (`management/zeki_tahmin.py`) kitap başına 12 aylık satış tahminini kantilleriyle
(p10/p50/p80/p90) yönetim raporları önbelleğine yazar (`<MANAGEMENT_REPORT_CACHE_DIR>/baski-oneri-tahmin.json`). Bütçe
(M46), stok (M43) ve pazarlama backlist ekranları bu dosyayı **yalnız bu modülden** okur; servis çağrısı tahmin işinde
kalır (sınama, önbellek ve GPU sırası orada).

Ekran sözleşmesi: rakam motordan gelir; aralık (p10–p90) varsa her zaman p50 ile birlikte gösterilir, «tahmin» etiketi
taşır; kantil dosyada yoksa aralık **uydurulmaz** — `aralik: False` ve «aralık yok» döner, ekran yalnız p50'yi gösterir.

Birden çok ayın toplamında kantiller toplanır (aylık p10'ların toplamı). Bu, aylar arası tam bağımlılık varsayımıdır:
gerçek dönem aralığı bundan dardır; ekranda «aylık aralıkların toplamı» diye yazılır ve temkinli (geniş) okunur.

Kitap tahmini saf okumadır: ağa ve modele gitmez; dosya yoksa ya da bozuksa boş sözlük. Tek istisna `forecast_series`:
kitap dışı bir seri (13 haftalık nakitte tahsilat/ödeme) için tahmin servisine aynı sıradan gider; servis yoksa hata
verir ve ekran aralığı göstermez.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable, Optional

REPORT_FILE = "baski-oneri-tahmin.json"
#: Dosyada tutulan kantiller (zeki_tahmin.KEEP_QUANTILES ile aynı adlar).
QUANTILES = ("p10", "p50", "p80", "p90")
#: Senaryo ↔ kantil eşlemesi (M46 bütçe: muhafazakâr / temel / iyimser).
SCENARIO_QUANTILE = {"muhafazakar": "p10", "temel": "p50", "iyimser": "p90"}
NO_RANGE = "aralık yok"


def cache_path() -> Path:
    root = Path(os.environ.get("MANAGEMENT_REPORT_CACHE_DIR", "/data/nanobaseai/bi/var/management-reports"))
    return root / REPORT_FILE


def _series(v: Any) -> Optional[list[float]]:
    if not isinstance(v, list) or not v:
        return None
    out = []
    for x in v:
        try:
            f = float(x or 0)
        except (TypeError, ValueError):
            return None
        out.append(max(0.0, f if f == f else 0.0))
    return out


def parse(snap: dict[str, Any]) -> dict[str, Any]:
    """Önbellek dosyasının içeriği → istemci sözlüğü. `p50` her zaman vardır (eski okuyucularla uyumlu); diğer kantiller
    yalnız dosyada varsa gelir. `kantiller`: dosyada gerçekten bulunan kantil adları."""
    data = (snap or {}).get("data") or {}
    fc = data.get("forecasts") or {}
    if not isinstance(fc, dict) or not fc or not data.get("forecastStart"):
        return {}
    out: dict[str, Any] = {"start": data["forecastStart"], "updatedAt": snap.get("updatedAt"), "dataEnd": data.get("dataEnd"),
                           "lastFullMonth": data.get("lastFullMonth"), "horizon": data.get("horizon")}
    present = []
    for q in QUANTILES:
        by_code = {}
        for code, v in fc.items():
            s = _series((v or {}).get(q)) if isinstance(v, dict) else None
            if s is not None:
                by_code[code] = s
        if by_code or q == "p50":
            out[q] = by_code
            if by_code:
                present.append(q)
    out["kantiller"] = present
    return out


def read(path: Optional[Path] = None) -> dict[str, Any]:
    """Baskı Öneri'nin 12 aylık kitap tahmini (kantilleriyle). Yoksa boş sözlük."""
    try:
        snap = json.loads((path or cache_path()).read_text())
    except (OSError, ValueError):
        return {}
    return parse(snap) if isinstance(snap, dict) else {}


def has_range(fc: dict[str, Any]) -> bool:
    """Tahminde p10 ve p90 kantilleri var mı (en az bir kitap için)."""
    return bool(fc) and bool(fc.get("p10")) and bool(fc.get("p90"))


def series(fc: dict[str, Any], code: str) -> Optional[dict[str, Optional[list[float]]]]:
    """Kitabın aylık tahmin serileri. p50 yoksa None; p10/p90 yoksa o anahtar None."""
    p50 = ((fc or {}).get("p50") or {}).get(code)
    if not p50:
        return None
    return {q: ((fc.get(q) or {}).get(code) if q != "p50" else p50) for q in ("p10", "p50", "p90")}


def _sum(vals: Optional[list[float]], months: Iterable[int], weights: Optional[dict[int, float]] = None) -> Optional[float]:
    if vals is None:
        return None
    tot = 0.0
    for j in months:
        if 0 <= j < len(vals):
            tot += vals[j] * (weights.get(j, 1.0) if weights else 1.0)
    return tot


def band(fc: dict[str, Any], code: str, months: Iterable[int], weights: Optional[dict[int, float]] = None) -> Optional[dict[str, Any]]:
    """Seçilen ayların (tahmin başlangıcından 0'dan sayılan sıra) toplam tahmini. Dönen: p50 ve varsa p10/p90;
    `aralik` False ise p10/p90 None'dır ve `not` «aralık yok» (uydurulmaz). Kitap tahminde yoksa None."""
    s = series(fc, code)
    if s is None:
        return None
    months = list(months)
    p50 = _sum(s["p50"], months, weights)
    p10 = _sum(s["p10"], months, weights)
    p90 = _sum(s["p90"], months, weights)
    ok = p10 is not None and p90 is not None
    return {"p10": p10 if ok else None, "p50": p50, "p90": p90 if ok else None, "aralik": ok,
            "not": None if ok else NO_RANGE}


def rounded(b: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if b is None:
        return None
    return {**b, **{q: (None if b.get(q) is None else round(b[q])) for q in ("p10", "p50", "p90")}}


def window(fc: dict[str, Any], code: str) -> Optional[dict[str, Any]]:
    """30/60/90 gün (tahmin başlangıcından ilk 1/2/3 ay) bandı: {"baslangic", "g30": {p10,p50,p90,aralik}, …}."""
    s = series(fc, code)
    if s is None:
        return None
    out: dict[str, Any] = {"baslangic": fc.get("start"), "aralik": s["p10"] is not None and s["p90"] is not None}
    for key, n in (("g30", 1), ("g60", 2), ("g90", 3)):
        out[key] = rounded(band(fc, code, range(n)))
    out["not"] = None if out["aralik"] else NO_RANGE
    return out


def total(fc: dict[str, Any], code: str, quantile: str = "p50", months: int = 12) -> Optional[float]:
    """İlk `months` ayın toplamı, istenen kantilde. Kantil yoksa None (çağıran p50'ye düşer ya da aralık yok der)."""
    s = ((fc or {}).get(quantile) or {}).get(code)
    if not s:
        return None
    return float(sum(s[:months]))


#: Servisin 9 kantil satırındaki sıra (zeki_tahmin.KEEP_QUANTILES ile aynı).
SERVICE_QUANTILE_INDEX = {"p10": 0, "p50": 4, "p90": 8}


def forecast_series(series: dict[str, list[float]], horizon: int, *, start: str = "", post: Any = None,
                    ready: Any = None) -> dict[str, dict[str, list[float]]]:
    """Genel seri tahmini (ör. haftalık tahsilat/ödeme): tahmin servisine aynı `/forecast/batch` ucuyla, takvim ek
    değişkeni olmadan gider. Dönen: seri → {"p10", "p50", "p90"} (her biri `horizon` uzunluğunda, eksi değer 0'a
    kırpılır). Servis yoksa ya da kantil dönmezse hata yükselir; çağıran bandı göstermez (uydurmaz).
    Haftalık seride servis frekans bilmez; bu kullanım kabul listesinde «ölçülecek» olarak durur."""
    from semantic_bridge.management import zeki_tahmin as T

    (ready or T.service_ready)()
    payload = {"horizon": int(horizon), "calendar": False, "engine": "timesfm3",
               "series": [{"id": k, "start": start, "values": [float(x or 0) for x in v]} for k, v in series.items()]}
    out = (post or T.post_batch)(payload)
    res: dict[str, dict[str, list[float]]] = {}
    for r in (out or {}).get("results") or []:
        q = r.get("quantiles") or []
        if not q or not all(isinstance(row, list) and len(row) > max(SERVICE_QUANTILE_INDEX.values()) for row in q):
            continue
        res[str(r.get("id"))] = {name: [max(0.0, float(row[j] or 0)) for row in q[:horizon]]
                                 for name, j in SERVICE_QUANTILE_INDEX.items()}
    missing = [k for k in series if k not in res]
    if missing:
        raise RuntimeError(f"Tahmin servisi şu seriler için kantil döndürmedi: {', '.join(missing)}")
    return res


def month_offset(fc: dict[str, Any], year: int, month: int) -> Optional[int]:
    """Takvim ayının tahmin serisindeki sırası (başlangıç ayı 0). Başlangıç yoksa None."""
    st = str((fc or {}).get("start") or "")
    try:
        y, m = int(st[:4]), int(st[5:7])
    except ValueError:
        return None
    return (year * 12 + month - 1) - (y * 12 + m - 1)
