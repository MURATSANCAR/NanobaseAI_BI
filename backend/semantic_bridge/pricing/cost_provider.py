"""M9 birim maliyet sağlayıcısı: diğer modüllerin (M32 kurumsal satış, M33 ihale, M53 set) kitap birim maliyetini
sorduğu tek yer.

`unit_costs(stok_kodlari)` → `{kod: {"maliyet": Decimal | None, "kaynak": "onayli-analiz" | "gerceklesen" | "yok",
"tarih": "YYYY-MM-DD" | None, ...}}`. İstenen her kod cevapta vardır. Öncelik:

1. **Onaylı analiz** — kitabın (stok kodu) onaylanmış M9 fiyat analizinde dondurulmuş birim maliyet
   (`result_json.summary.unitCost`: seçilen baskı adedinde basılan adet başına baskı + sabit gider payı; hesabın sahibi
   `model.unit_cost`). Birden çok onaylı analiz varsa Aşama 2 (kesin) Aşama 1'in (tahmini) önüne geçer, aynı aşamada en
   son onaylanan alınır. Tarih = o sürümün son onay imzasının günü.
2. **Gerçekleşen** — M9'un Logo anlık görüntüsündeki satılan malın maliyeti: kitabın maliyeti girilmiş satış
   satırlarının (`OUTCOST > 0`) en son yılı, `maliyet ÷ maliyetli adet` (`data.sales_summary` ile aynı tanım). Tarih = o
   yılın son günü (yıl veri sonuysa veri sonu). Sağlayıcı Logo'ya kendisi gitmez; görüntü yoksa bu adım boş geçer.
3. **Yok** — `maliyet: None`, not «maliyet bilinmiyor». Hiçbir yolda varsayılan ya da tahmini rakam üretilmez.

Maliyet görme yetkisi olmayana maliyet alanlarını çıkarmak modüllerin kendi kuralıdır; sağlayıcı yetkiye bakmaz.

Bağlanan biçimler (`app.py`):
- M32 / M53: `register_cost_provider(provider.birim)` → `{kod: {"birim": float, "tarih": ...}}` (yalnız bilinenler).
- M33: `app.state.unit_cost = provider.labelled()` → `.unit_costs(codes)` → `{kod: {"maliyet": Decimal, "kaynak":
  okunur metin}}` (ihale satırında «maliyet kaynağı» olarak yazılır).
"""
from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

from semantic_bridge.pricing import store as S

log = logging.getLogger("semantic.pricing.cost")

APPROVED, ACTUAL, NONE = "onayli-analiz", "gerceklesen", "yok"
LABELS = {APPROVED: "Onaylı fiyat analizi", ACTUAL: "Logo gerçekleşen maliyet", NONE: "Maliyet bilinmiyor"}
UNKNOWN_NOTE = "maliyet bilinmiyor"
#: Aşama önceliği: kesin fiyat analizi tahmini olanın önüne geçer.
STAGE_RANK = {"kesin": 2, "tahmini": 1}


def _dec(v: Any) -> Optional[Decimal]:
    """Pozitif sonlu sayı → 4 haneli Decimal; değilse None (sıfır ya da eksi maliyet «bilinmiyor» sayılır)."""
    if v is None or isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if x != x or x in (float("inf"), float("-inf")) or x <= 0:
        return None
    return Decimal(str(round(x, 4)))


def _codes(stok_kodlari: Iterable[Any]) -> list[str]:
    return [c for c in dict.fromkeys(str(k).strip() for k in (stok_kodlari or []) if k is not None) if c]


def _day(v: Any) -> Optional[str]:
    if v is None:
        return None
    return v.date().isoformat() if hasattr(v, "date") and callable(v.date) else str(v)[:10]


def approved_costs_stmt(tenant: str, codes: list[str]) -> Any:
    """Onaylı analiz okuması (sağlayıcı ve başka modüllerin sorgu bilgisi aynı ifadeyi kullanır)."""
    A = S.ANALYSES
    return (sa.select(A.c.id, A.c.stock_code, A.c.stage, A.c.version, A.c.title, A.c.result_json)
            .where(A.c.tenant_id == tenant, A.c.status == "onaylandi", A.c.stock_code.in_(codes)))


def approval_times_stmt(ids: list[str]) -> Any:
    """Onaylı analiz sürümlerinin son onay imzası anı."""
    P = S.APPROVALS
    return (sa.select(P.c.analysis_id, P.c.version, sa.func.max(P.c.at))
            .where(P.c.analysis_id.in_(ids), P.c.decision == "onay").group_by(P.c.analysis_id, P.c.version))


def approved_costs(engine: Any, tenant: str, codes: list[str]) -> dict[str, dict[str, Any]]:
    """Stok kodu → onaylı M9 analizindeki birim maliyet. Tablo yoksa ya da okunamazsa boş (sonraki adıma geçilir)."""
    if not codes or engine is None:
        return {}
    S.ensure(engine)
    with engine.connect() as c:
        rows = c.execute(approved_costs_stmt(tenant, codes)).mappings().all()
        signed: dict[tuple[str, int], Any] = {}
        ids = [r["id"] for r in rows]
        if ids:
            for aid, ver, at in c.execute(approval_times_stmt(ids)).all():
                signed[(aid, ver)] = at
    best: dict[str, tuple[tuple, dict[str, Any]]] = {}
    for r in rows:
        try:
            result = json.loads(r["result_json"] or "{}")
        except ValueError:
            continue
        summary = result.get("summary") if isinstance(result, dict) else None
        if not isinstance(summary, dict):
            continue
        cost = _dec(summary.get("unitCost"))
        if cost is None:
            continue
        at = signed.get((r["id"], r["version"]))
        day = _day(at)
        key = (STAGE_RANK.get(r["stage"], 0), at is not None, str(at or ""))
        item = {"maliyet": cost, "kaynak": APPROVED, "tarih": day, "analiz": r["id"], "analizAdi": r["title"],
                "asama": r["stage"], "adet": summary.get("qty")}
        code = r["stock_code"]
        if code not in best or key > best[code][0]:
            best[code] = (key, item)
    return {k: v for k, (_, v) in best.items()}


def actual_costs(snap: Optional[dict], codes: list[str]) -> dict[str, dict[str, Any]]:
    """Stok kodu → Logo'da gerçekleşen birim maliyet (maliyeti girilmiş satışların en son yılı)."""
    if not snap or not codes:
        return {}
    sales = snap.get("sales") or {}
    end = str(snap.get("dataEnd") or "")[:10] or None
    out: dict[str, dict[str, Any]] = {}
    for code in codes:
        years = sales.get(code) or {}
        for year in sorted(years, reverse=True):
            v = years[year] or {}
            qty = float(v.get("costedQty") or 0)
            cost = _dec(float(v.get("cogs") or 0) / qty) if qty > 0 else None
            if cost is None:
                continue
            day = end if end and end[:4] == str(year) else f"{year}-12-31"
            sold = float(v.get("soldQty") or 0)
            out[code] = {"maliyet": cost, "kaynak": ACTUAL, "tarih": day, "yil": int(year),
                         "kapsam": round(qty / sold, 4) if sold > 0 else None}
            break
    return out


def unit_costs(stok_kodlari: Iterable[Any], *, engine: Any = None, tenant: str = "",
               snapshot: Optional[dict] = None) -> dict[str, dict[str, Any]]:
    """Öncelik: onaylı analiz → gerçekleşen → yok. Her kod cevapta; bilinmeyenin maliyeti None."""
    codes = _codes(stok_kodlari)
    out = {c: {"maliyet": None, "kaynak": NONE, "tarih": None, "not": UNKNOWN_NOTE} for c in codes}
    if not codes:
        return out
    try:
        approved = approved_costs(engine, tenant, codes)
    except Exception as e:  # noqa: BLE001 — kayıt okunamazsa gerçekleşene düşülür
        log.warning("pricing: onaylı analiz maliyetleri okunamadı: %s", e)
        approved = {}
    rest = [c for c in codes if c not in approved]
    actual = actual_costs(snapshot, rest) if rest else {}
    for c in codes:
        hit = approved.get(c) or actual.get(c)
        if hit:
            out[c] = hit
    return out


def label(item: dict[str, Any]) -> str:
    """Ekranda yazılacak kaynak cümlesi (ihale satırının «maliyet kaynağı»)."""
    k = item.get("kaynak")
    if k == APPROVED:
        stage = S.STAGES.get(item.get("asama") or "", item.get("asama") or "")
        bits = [b for b in (stage, item.get("tarih")) if b]
        return f"{LABELS[APPROVED]} ({', '.join(bits)})" if bits else LABELS[APPROVED]
    if k == ACTUAL:
        return f"{LABELS[ACTUAL]} ({item['yil']})" if item.get("yil") else LABELS[ACTUAL]
    return LABELS[NONE]


class Provider:
    """Köprüde tek örnek: bağlam (veritabanı, kiracı, M9 görüntüsü) çağrı anında okunur; kurulumda Logo'ya gidilmez."""

    def __init__(self, engine: Callable[[], Any], tenant: Callable[[], str], snapshot: Callable[[], Optional[dict]]):
        self._engine, self._tenant, self._snapshot = engine, tenant, snapshot

    def _snap(self) -> Optional[dict]:
        try:
            return self._snapshot()
        except Exception as e:  # noqa: BLE001 — görüntü klasörü yoksa gerçekleşen adımı boş geçer
            log.warning("pricing: anlık görüntü okunamadı: %s", e)
            return None

    def unit_costs(self, stok_kodlari: Iterable[Any]) -> dict[str, dict[str, Any]]:
        try:
            engine, tenant = self._engine(), self._tenant()
        except Exception as e:  # noqa: BLE001
            log.warning("pricing: maliyet bağlamı kurulamadı: %s", e)
            engine, tenant = None, ""
        return unit_costs(stok_kodlari, engine=engine, tenant=tenant, snapshot=self._snap())

    def birim(self, stok_kodlari: Iterable[Any]) -> dict[str, dict[str, Any]]:
        """M32 / M53 biçimi: yalnız bilinen kodlar, `birim` float."""
        return {k: {"birim": float(v["maliyet"]), "tarih": v.get("tarih"), "kaynak": v["kaynak"]}
                for k, v in self.unit_costs(stok_kodlari).items() if v.get("maliyet") is not None}

    def labelled(self) -> "Labelled":
        return Labelled(self)


class Labelled:
    """M33 biçimi (`app.state.unit_cost.unit_costs(codes)`): yalnız bilinen kodlar, kaynak okunur metin."""

    def __init__(self, provider: Provider):
        self.provider = provider

    def unit_costs(self, stok_kodlari: Iterable[Any]) -> dict[str, dict[str, Any]]:
        return {k: {"maliyet": v["maliyet"], "kaynak": label(v), "tarih": v.get("tarih")}
                for k, v in self.provider.unit_costs(stok_kodlari).items() if v.get("maliyet") is not None}
