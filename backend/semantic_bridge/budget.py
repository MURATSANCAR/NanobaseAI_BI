"""M46 Bütçe planlama ve kontrolü: kitap bazlı satış hedefleri, yeni kitap programı, departman bütçesi, senaryolar,
onay akışı, hedef–gerçekleşme izleme ve sapma uyarısı.

**Akış (K2 — veriden kurala göre öneri, yönetim onaylar):** «Veriden öneri» (model yok; ekranda «Zeki AI» adını taşımaz) bir yıl için üç taslak plan kurar (muhafazakâr /
temel / iyimser). Taslak düzenlenir (kitap hedefi, program, departman), onaya gönderilir, onay yetkisi olan ve taslağı
göndermemiş biri onaylar (iki göz). Onaylanan plan o yılın **yürürlükteki** planıdır; önceki yürürlükteki plan arşive
geçer. Yürürlükteki plan «revize et» ile yeni bir taslak sürüme kopyalanır (gerekçe zorunlu); o onaylanınca yerini alır.
Her yazma `semantic_audit`'e düşer.

**Taban penceresi:** plan yılından önceki 12 ay Logo'da tamamsa taban o takvim yılıdır (2026 planı → 2025); değilse
verinin bittiği aydan önceki son 12 tam ay (veri 17.08.2026'da bitiyorsa Ağustos 2025 – Temmuz 2026).

**Öneri (model yok, gerekçesi satırda):**
- *Backlist* (ilk yayını taban penceresinin sonundan önce): taban adet = penceredeki net adet; plan yılı verinin
  ötesindeyse ve kitap Baskı Öneri'nin ZEKİ AI 12 aylık tahmininde varsa taban = tahminin p50 toplamı (tahmin
  pencereden sonraki 12 aydır). Hedef adet = taban × (1 + hacim büyümesi); birim fiyat = penceredeki net birim fiyat ×
  (1 + fiyat artışı); marj = kitabın maliyetli satırlarındaki marj (yoksa yayınevinin, o da yoksa şirketin) + marj
  değişimi. Tabanda satışı olmayan kitap öneriye girmez (elle eklenebilir).
- *Yeni kitap* (ilk yayını pencere sonundan plan yılı sonuna): pencerede çıkan kitapların (kohort) yayınevi bazında
  «satışta geçen ay başına net adet» ortalaması × kitabın plan yılındaki satış ayı sayısı × (1 + hacim büyümesi); fiyat
  ve marj kohortun yayınevi ortalaması.
- *Yeni kitap programı*: yayınevi başına pencerede çıkan başlık sayısı kadar başlık beklenir; CRM'de adıyla planlanmış
  olanlar kitap hedefidir, geri kalan «ek başlık» × kohortun başlık başına ortalaması.
- *Departman bütçesi*: masraf merkezi × ana gider hesabı, pencerenin aynı takvim ayı × (1 + gider artışı).
- Varsayılanlar: hacim büyümesi muhafazakâr %5 / temel %10 / iyimser %15 (iş tanımı); fiyat artışı ve gider artışı
  veriden (en son yılın ilk ayları ile geçen yılın aynı ayları; fiyat, iki dönemde de satılan kitaplarda ölçülür).

**İzleme:** yıllık hedef aylara taban penceresinin şirket aylık dağılımıyla yayılır (yeni kitapta yayın ayından
itibaren); verinin bittiği güne kadar beklenen = hedef × geçen payı (ay içinde gün oranı). Oran = gerçekleşen ÷
beklenen; %80 altı sapmadır (plan parametresi `esik`). Departmanda kullanım = gerçekleşen ÷ dönem bütçesi; ≥ %100 aşım,
≥ %90 erken uyarı.

**Diğer modüllere sözleşme:** `approved_targets()` (köprü içi), `GET /api/v1/budget/targets` ve
`GET /api/v1/budget/deviations`, veritabanında `semantic_budget_approved_targets` görünümü. Ayrıntı günlükte
(2026-09-28, M46).
"""
from __future__ import annotations

import calendar
import csv
import io
import json
import logging
import math
import os
import threading
import time
import uuid
from datetime import date, datetime, timezone
from typing import Any, Callable, Iterable, Optional
from zoneinfo import ZoneInfo

import sqlalchemy as sa

from semantic_bridge import budget_sources as src

log = logging.getLogger("semantic.budget")
TZ = ZoneInfo("Europe/Istanbul")
_md = sa.MetaData()

PLANS = sa.Table(
    "semantic_budget_plans", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("year", sa.Integer, nullable=False),
    sa.Column("scenario", sa.String(20), nullable=False),
    sa.Column("version", sa.Integer, nullable=False),
    sa.Column("status", sa.String(12), nullable=False),        # taslak | onayda | onayli | arsiv
    sa.Column("title", sa.String(200), nullable=False),
    sa.Column("params_json", sa.Text, nullable=False),
    sa.Column("basis_json", sa.Text, nullable=False),
    sa.Column("note", sa.Text),
    sa.Column("revision_of", sa.String(32)),
    sa.Column("revision_reason", sa.Text),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
    sa.Column("submitted_by", sa.String(120)),
    sa.Column("submitted_at", sa.DateTime(timezone=True)),
    sa.Column("decided_by", sa.String(120)),
    sa.Column("decided_at", sa.DateTime(timezone=True)),
    sa.Column("decision_note", sa.Text),
    sa.Index("ix_semantic_budget_plans_year", "tenant_id", "year"),
)
BOOKS = sa.Table(
    "semantic_budget_book_targets", _md,
    sa.Column("plan_id", sa.String(32), primary_key=True),
    sa.Column("stok_kodu", sa.String(60), primary_key=True),
    sa.Column("ad", sa.String(400)),
    sa.Column("segment", sa.String(12), nullable=False),        # yeni | backlist
    sa.Column("yayinevi", sa.String(200)),
    sa.Column("kitaplik", sa.String(200)),
    sa.Column("ilk_yayin", sa.String(10)),
    sa.Column("adet", sa.Float, nullable=False),
    sa.Column("ciro", sa.Float, nullable=False),
    sa.Column("marj", sa.Float),
    sa.Column("oneri_json", sa.Text, nullable=False),
    sa.Column("note", sa.String(500)),
    sa.Column("edited_by", sa.String(120)),
    sa.Column("edited_at", sa.DateTime(timezone=True)),
)
PROGRAM = sa.Table(
    "semantic_budget_program", _md,
    sa.Column("plan_id", sa.String(32), primary_key=True),
    sa.Column("yayinevi", sa.String(200), primary_key=True),
    sa.Column("baslik", sa.Integer, nullable=False),            # planlanan toplam yeni başlık
    sa.Column("bilinen", sa.Integer, nullable=False),           # CRM'de adıyla planlanmış (kitap hedefi olan)
    sa.Column("ek_baslik", sa.Integer, nullable=False),         # adı henüz belli olmayan başlık
    sa.Column("baslik_adet", sa.Float, nullable=False),         # ek başlık başına beklenen net adet
    sa.Column("baslik_ciro", sa.Float, nullable=False),
    sa.Column("marj", sa.Float),
    sa.Column("oneri_json", sa.Text, nullable=False),
    sa.Column("note", sa.String(500)),
    sa.Column("edited_by", sa.String(120)),
    sa.Column("edited_at", sa.DateTime(timezone=True)),
)
DEPTS = sa.Table(
    "semantic_budget_dept_lines", _md,
    sa.Column("plan_id", sa.String(32), primary_key=True),
    sa.Column("merkez_kodu", sa.String(60), primary_key=True),
    sa.Column("hesap", sa.String(3), primary_key=True),
    sa.Column("merkez_adi", sa.String(200)),
    sa.Column("hesap_adi", sa.String(200)),
    sa.Column("aylar_json", sa.Text, nullable=False),           # 12 aylık tutar
    sa.Column("oneri_json", sa.Text, nullable=False),
    sa.Column("note", sa.String(500)),
    sa.Column("edited_by", sa.String(120)),
    sa.Column("edited_at", sa.DateTime(timezone=True)),
)
SALES = sa.Table(
    "semantic_budget_sales_actuals", _md,
    sa.Column("year", sa.Integer, primary_key=True),
    sa.Column("month", sa.Integer, primary_key=True),
    sa.Column("stok_kodu", sa.String(60), primary_key=True),
    sa.Column("adet", sa.Float, nullable=False),
    sa.Column("ciro", sa.Float, nullable=False),
    sa.Column("maliyet", sa.Float, nullable=False),
    sa.Column("maliyetli_ciro", sa.Float, nullable=False),
)
EXPENSES = sa.Table(
    "semantic_budget_expense_actuals", _md,
    sa.Column("year", sa.Integer, primary_key=True),
    sa.Column("month", sa.Integer, primary_key=True),
    sa.Column("merkez_kodu", sa.String(60), primary_key=True),
    sa.Column("hesap", sa.String(3), primary_key=True),
    sa.Column("merkez_adi", sa.String(200)),
    sa.Column("hesap_adi", sa.String(200)),
    sa.Column("tutar", sa.Float, nullable=False),
)
BOOKINFO = sa.Table(
    "semantic_budget_books", _md,
    sa.Column("stok_kodu", sa.String(60), primary_key=True),
    sa.Column("ad", sa.String(400)),
    sa.Column("yazar", sa.String(300)),
    sa.Column("yayinevi", sa.String(200)),
    sa.Column("kitaplik", sa.String(200)),
    sa.Column("ilk_yayin", sa.String(10)),
    sa.Column("liste_fiyati", sa.Float),
    sa.Column("statu", sa.String(200)),
    sa.Column("in_logo", sa.Boolean, nullable=False, default=False),   # Logo'da stok kartı açılmış
)
META = sa.Table(
    "semantic_budget_meta", _md,
    sa.Column("key", sa.String(60), primary_key=True),
    sa.Column("value_json", sa.Text, nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)
ALERTS = sa.Table(
    "semantic_budget_alerts", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("year", sa.Integer, nullable=False),
    sa.Column("plan_id", sa.String(32), nullable=False),
    sa.Column("kind", sa.String(12), nullable=False),          # satis | gider | revizyon
    sa.Column("scope", sa.String(12), nullable=False),         # kitap | yayinevi | segment | toplam | merkez
    sa.Column("key", sa.String(120), nullable=False),
    sa.Column("label", sa.String(400)),
    sa.Column("ratio", sa.Float),
    sa.Column("expected", sa.Float),
    sa.Column("actual", sa.Float),
    sa.Column("gap", sa.Float),
    sa.Column("detail_json", sa.Text),
    sa.Column("modules", sa.String(60)),                       # bu uyarıyı okuyacak modüller
    sa.Column("status", sa.String(10), nullable=False),        # acik | kapandi | bilgi
    sa.Column("first_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("last_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("closed_at", sa.DateTime(timezone=True)),
    sa.Column("notified_at", sa.DateTime(timezone=True)),
    sa.Index("ix_semantic_budget_alerts_open", "tenant_id", "year", "status"),
)

SCENARIOS = {"muhafazakar": "Muhafazakâr", "temel": "Temel", "iyimser": "İyimser"}
STATUSES = {"taslak": "Taslak", "onayda": "Onay bekliyor", "onayli": "Yürürlükte", "arsiv": "Arşiv"}
SEGMENTS = {"yeni": "Yeni kitap", "backlist": "Backlist"}
DEFAULT_GROWTH = {"muhafazakar": 0.05, "temel": 0.10, "iyimser": 0.15}
DEFAULT_THRESHOLD = 0.80
EARLY_WARNING = 0.90
#: Kitap uyarısı hedef cirosunun bu payını oluşturan kitaplar (büyükten küçüğe; ABC'nin A sınıfı) için açılır.
#: 2026-09-28 kabulünde 2026 temel planda 11.276 kitabın 7.720'si eşik altındaydı; çoğu yılda birkaç bin liralık
#: kitaplardı ve her biri pazarlama/saha modülüne iş olarak gidemez. Diğer kitapların durumu ekranda ve listede kalır.
DEFAULT_ALERT_SCOPE = 0.80
#: Satış sapması uyarısını okuyacak modüller (iş tanımı: M18 pazarlama planı, M30 saha; M15/M17/M29 hedefi girdi alır).
SALES_ALERT_MODULES = "M15,M17,M18,M29,M30"
PAGE_SIZE = 100
AY = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]

_ready: set[int] = set()
_lock = threading.Lock()


class BudgetError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def ensure(engine: sa.engine.Engine) -> None:
    key = id(engine)
    with _lock:
        if key in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _create_view(engine)
        _ready.add(key)


def _create_view(engine: sa.engine.Engine) -> None:
    """Diğer modüllerin doğrudan SQL ile okuyacağı onaylı hedefler (yürürlükteki planın kitap satırları)."""
    body = ("SELECT p.tenant_id, p.year, p.id AS plan_id, p.version, p.scenario, p.decided_at AS approved_at, "
            "p.decided_by AS approved_by, b.stok_kodu, b.ad, b.segment, b.yayinevi, b.kitaplik, b.ilk_yayin, "
            "b.adet AS hedef_adet, b.ciro AS hedef_ciro, b.marj AS hedef_marj "
            "FROM semantic_budget_plans p JOIN semantic_budget_book_targets b ON b.plan_id = p.id "
            "WHERE p.status = 'onayli'")
    try:
        with engine.begin() as c:
            if engine.dialect.name == "postgresql":
                c.execute(sa.text("CREATE OR REPLACE VIEW semantic_budget_approved_targets AS " + body))
            else:
                c.execute(sa.text("CREATE VIEW IF NOT EXISTS semantic_budget_approved_targets AS " + body))
    except Exception as e:  # noqa: BLE001 — görünüm kolaylıktır, uçlar ona dayanmaz
        log.warning("budget: onaylı hedef görünümü kurulamadı: %s", e)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> date:
    return datetime.now(TZ).date()


def _iso(v: Optional[datetime]) -> Optional[str]:
    if v is None:
        return None
    return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()


def _j(v: Optional[str], default: Any) -> Any:
    try:
        return json.loads(v) if v else default
    except ValueError:
        return default


def _dump(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


def _num(v: Any, label: str, *, allow_none: bool = False, minimum: Optional[float] = 0.0,
         maximum: Optional[float] = None) -> Optional[float]:
    if v is None or v == "":
        if allow_none:
            return None
        raise BudgetError(f"{label} boş olamaz.")
    try:
        n = float(str(v).replace(",", ".")) if isinstance(v, str) else float(v)
    except (TypeError, ValueError):
        raise BudgetError(f"{label} sayı olmalı.") from None
    if math.isnan(n) or math.isinf(n):
        raise BudgetError(f"{label} sayı olmalı.")
    if minimum is not None and n < minimum:
        raise BudgetError(f"{label} {minimum:g} değerinden küçük olamaz.")
    if maximum is not None and n > maximum:
        raise BudgetError(f"{label} {maximum:g} değerinden büyük olamaz.")
    return n


def _text(v: Any, limit: int) -> Optional[str]:
    s = " ".join(str(v or "").split())
    return s[:limit] or None


# ------------------------------------------------------------------ meta (gerçekleşme tazeliği)


def meta_get(engine: sa.engine.Engine, key: str) -> dict[str, Any]:
    with engine.connect() as c:
        row = c.execute(sa.select(META).where(META.c.key == key)).first()
    if not row:
        return {}
    return {**_j(row.value_json, {}), "_at": _iso(row.updated_at)}


def meta_set(engine: sa.engine.Engine, key: str, value: dict[str, Any]) -> None:
    now = _now()
    with engine.begin() as c:
        if c.execute(sa.select(META.c.key).where(META.c.key == key)).first():
            c.execute(META.update().where(META.c.key == key).values(value_json=_dump(value), updated_at=now))
        else:
            c.execute(META.insert().values(key=key, value_json=_dump(value), updated_at=now))


def data_end(engine: sa.engine.Engine) -> Optional[date]:
    v = meta_get(engine, "data_end").get("date")
    return date.fromisoformat(v) if v else None


# ------------------------------------------------------------------ pencere ve dağılım


def month_index(y: int, m: int) -> int:
    return y * 12 + (m - 1)


def from_index(i: int) -> tuple[int, int]:
    return i // 12, i % 12 + 1


def window(year: int, end: Optional[date]) -> dict[str, Any]:
    """Taban penceresi: [başlangıç, bitiş) ay dizini ve okunur adı."""
    if end is None:
        raise BudgetError("Logo gerçekleşmesi henüz okunmadı; önce «Gerçekleşmeyi yenile».", 409)
    last_full = month_index(end.year, end.month) - (0 if end.day == calendar.monthrange(end.year, end.month)[1] else 1)
    if last_full >= month_index(year - 1, 12):
        start = month_index(year - 1, 1)
        label = f"{year - 1} yılı"
    else:
        start = last_full - 11
        a, b = from_index(start), from_index(last_full)
        label = f"{AY[a[1] - 1]} {a[0]} – {AY[b[1] - 1]} {b[0]}"
    return {"start": start, "end": start + 12, "label": label, "years": sorted({from_index(i)[0] for i in range(start, start + 12)})}


def elapsed_shares(year: int, asof: Optional[date]) -> list[float]:
    """Plan yılının her ayından verinin bittiği güne kadar geçen pay (0–1)."""
    out = []
    for m in range(1, 13):
        if asof is None or asof < date(year, m, 1):
            out.append(0.0)
        elif asof >= date(year, m, calendar.monthrange(year, m)[1]):
            out.append(1.0)
        else:
            out.append(asof.day / calendar.monthrange(year, m)[1])
    return out


def normalized(weights: Iterable[float]) -> list[float]:
    w = [max(0.0, float(x or 0)) for x in weights]
    s = sum(w)
    return [x / s for x in w] if s > 0 else [1 / 12] * 12


def active_weights(weights: list[float], first_month: int) -> list[float]:
    """Yeni kitapta yayın ayından önceki aylar sıfır, kalan yeniden 1'e ölçeklenir."""
    w = [x if i + 1 >= first_month else 0.0 for i, x in enumerate(weights)]
    s = sum(w)
    return [x / s for x in w] if s > 0 else w


def expected_share(weights: list[float], elapsed: list[float]) -> float:
    return sum(w * e for w, e in zip(weights, elapsed))


# ------------------------------------------------------------------ gerçekleşme okuma (bizim tablolar)


def _sales_by_code(engine: sa.engine.Engine, start: int, end: int) -> dict[str, dict[str, float]]:
    """[start, end) ay dizini aralığında kitap başına toplamlar + ay ay adet (dizin → adet)."""
    y0, y1 = from_index(start)[0], from_index(end - 1)[0]
    out: dict[str, dict[str, Any]] = {}
    with engine.connect() as c:
        rows = c.execute(sa.select(SALES).where(SALES.c.year.between(y0, y1))).all()
    for r in rows:
        i = month_index(r.year, r.month)
        if i < start or i >= end:
            continue
        d = out.setdefault(r.stok_kodu, {"adet": 0.0, "ciro": 0.0, "maliyet": 0.0, "maliyetli_ciro": 0.0, "aylar": {},
                                         "aylarCiro": {}})
        d["adet"] += r.adet
        d["ciro"] += r.ciro
        d["maliyet"] += r.maliyet
        d["maliyetli_ciro"] += r.maliyetli_ciro
        d["aylar"][i] = d["aylar"].get(i, 0.0) + r.adet
        d["aylarCiro"][i] = d["aylarCiro"].get(i, 0.0) + r.ciro
    return out


def _expenses_by_line(engine: sa.engine.Engine, start: int, end: int) -> dict[tuple[str, str], dict[str, Any]]:
    y0, y1 = from_index(start)[0], from_index(end - 1)[0]
    out: dict[tuple[str, str], dict[str, Any]] = {}
    with engine.connect() as c:
        rows = c.execute(sa.select(EXPENSES).where(EXPENSES.c.year.between(y0, y1))).all()
    for r in rows:
        i = month_index(r.year, r.month)
        if i < start or i >= end:
            continue
        d = out.setdefault((r.merkez_kodu, r.hesap), {"merkez_adi": r.merkez_adi, "hesap_adi": r.hesap_adi, "aylar": [0.0] * 12})
        d["aylar"][r.month - 1] += r.tutar
    return out


def _book_info(engine: sa.engine.Engine) -> dict[str, dict[str, Any]]:
    with engine.connect() as c:
        return {r.stok_kodu: dict(r._mapping) for r in c.execute(sa.select(BOOKINFO)).all()}


def _is_trade(code: str) -> bool:
    """157 ile başlayan kodlar ticari üründür (kitap değil); yönetim raporlarıyla aynı ayrım."""
    return code.startswith("157")


# ------------------------------------------------------------------ öneri


def _price_index(engine: sa.engine.Engine, end: date) -> dict[str, Any]:
    """Fiyat artışı: verinin son yılının tam ayları ile geçen yılın aynı ayları; iki dönemde de satılan kitaplar,
    Σ bu yıl ciro ÷ Σ (bu yıl adet × geçen yıl birim fiyat) − 1 (sepet değişimi fiyat sayılmaz)."""
    last_full = window(end.year + 1, end)["end"]  # verinin son tam ayından sonraki ay
    y = end.year
    months = [m for m in range(1, 13) if month_index(y, m) < last_full]
    if not months:
        return {"value": None, "label": "ölçülemedi"}
    cur = _sales_by_code(engine, month_index(y, months[0]), month_index(y, months[-1]) + 1)
    prev = _sales_by_code(engine, month_index(y - 1, months[0]), month_index(y - 1, months[-1]) + 1)
    num = den = 0.0
    for code, a in cur.items():
        b = prev.get(code)
        if _is_trade(code) or not b or a["adet"] <= 0 or b["adet"] <= 0 or a["ciro"] <= 0 or b["ciro"] <= 0:
            continue
        num += a["ciro"]
        den += a["adet"] * (b["ciro"] / b["adet"])
    if den <= 0:
        return {"value": None, "label": "ölçülemedi"}
    label = f"{AY[months[0] - 1]}–{AY[months[-1] - 1]} {y} / {y - 1}"
    return {"value": round(num / den - 1, 4), "label": label}


def _expense_index(engine: sa.engine.Engine, end: date) -> dict[str, Any]:
    last_full = window(end.year + 1, end)["end"]
    y = end.year
    months = [m for m in range(1, 13) if month_index(y, m) < last_full]
    if not months:
        return {"value": None, "label": "ölçülemedi"}
    cur = _expenses_by_line(engine, month_index(y, months[0]), month_index(y, months[-1]) + 1)
    prev = _expenses_by_line(engine, month_index(y - 1, months[0]), month_index(y - 1, months[-1]) + 1)
    a = sum(sum(d["aylar"]) for d in cur.values())
    b = sum(sum(d["aylar"]) for d in prev.values())
    if b <= 0:
        return {"value": None, "label": "ölçülemedi"}
    return {"value": round(a / b - 1, 4), "label": f"{AY[months[0] - 1]}–{AY[months[-1] - 1]} {y} / {y - 1}"}


def default_params(engine: sa.engine.Engine, year: int) -> dict[str, Any]:
    end = data_end(engine)
    w = window(year, end)
    price, expense = _price_index(engine, end), _expense_index(engine, end)
    return {
        "hacim": dict(DEFAULT_GROWTH),
        "fiyat": price["value"] if price["value"] is not None else 0.0,
        "fiyatKaynak": f"Ölçüldü: {price['label']}" if price["value"] is not None else "Ölçülemedi; elle girin.",
        "gider": expense["value"] if expense["value"] is not None else 0.0,
        "giderKaynak": f"Ölçüldü: {expense['label']}" if expense["value"] is not None else "Ölçülemedi; elle girin.",
        "marjDegisim": 0.0,
        "esik": DEFAULT_THRESHOLD,
        "uyariKapsam": DEFAULT_ALERT_SCOPE,
        "tahmin": year > end.year,
        "pencere": w["label"],
    }


def _clean_params(body: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    p = dict(base)
    if "hacim" in body and isinstance(body["hacim"], dict):
        hv = dict(p.get("hacim") or DEFAULT_GROWTH)
        for k in SCENARIOS:
            if k in body["hacim"]:
                hv[k] = _num(body["hacim"][k], f"{SCENARIOS[k]} hacim büyümesi", minimum=-0.9, maximum=5)
        p["hacim"] = hv
    for key, label, lo, hi in (("fiyat", "Fiyat artışı", -0.9, 5), ("gider", "Gider artışı", -0.9, 5),
                               ("marjDegisim", "Marj değişimi", -1, 1), ("esik", "Uyarı eşiği", 0.05, 1),
                               ("uyariKapsam", "Uyarı kapsamı", 0.05, 1)):
        if key in body and body[key] is not None and body[key] != "":
            p[key] = _num(body[key], label, minimum=lo, maximum=hi)
            if key in ("fiyat", "gider"):
                p[key + "Kaynak"] = "Elle girildi"
    if "tahmin" in body:
        p["tahmin"] = bool(body["tahmin"])
    return p


def _margin(maliyet: float, maliyetli_ciro: float) -> Optional[float]:
    return 1 - maliyet / maliyetli_ciro if maliyetli_ciro > 0 else None


def _forecast_total(fc: dict[str, Any], code: str) -> Optional[float]:
    vals = (fc.get("p50") or {}).get(code)
    if not vals:
        return None
    return float(sum(vals[:12]))


def build_suggestion(engine: sa.engine.Engine, year: int, scenario: str, params: dict[str, Any],
                     forecast: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Bir senaryo için kitap hedefleri, program ve departman satırları (yazmaz; döner)."""
    end = data_end(engine)
    w = window(year, end)
    g = float((params.get("hacim") or DEFAULT_GROWTH).get(scenario, DEFAULT_GROWTH.get(scenario, 0.1)))
    p = float(params.get("fiyat") or 0)
    dm = float(params.get("marjDegisim") or 0)
    use_fc = bool(params.get("tahmin")) and bool(forecast)
    info = _book_info(engine)
    sales = _sales_by_code(engine, w["start"], w["end"])
    w_end_day = date(*from_index(w["end"]), 1)
    y_end = date(year + 1, 1, 1)

    # yayınevi ve şirket marjı (maliyetli satırlar), aylık dağılım
    pub: dict[str, dict[str, float]] = {}
    company = {"maliyet": 0.0, "maliyetli_ciro": 0.0}
    month_adet, month_ciro = [0.0] * 12, [0.0] * 12
    for code, s in sales.items():
        if _is_trade(code):
            continue
        yv = (info.get(code) or {}).get("yayinevi") or "Yayınevi belirsiz"
        d = pub.setdefault(yv, {"maliyet": 0.0, "maliyetli_ciro": 0.0})
        d["maliyet"] += s["maliyet"]
        d["maliyetli_ciro"] += s["maliyetli_ciro"]
        company["maliyet"] += s["maliyet"]
        company["maliyetli_ciro"] += s["maliyetli_ciro"]
        for i, q in s["aylar"].items():
            month_adet[from_index(i)[1] - 1] += q
        for i, q in s["aylarCiro"].items():
            month_ciro[from_index(i)[1] - 1] += q
    company_margin = _margin(company["maliyet"], company["maliyetli_ciro"])

    def pub_margin(yv: str) -> tuple[Optional[float], str]:
        d = pub.get(yv)
        m = _margin(d["maliyet"], d["maliyetli_ciro"]) if d else None
        if m is not None:
            return m, "yayınevi ortalaması"
        return company_margin, "şirket ortalaması"

    # kohort: pencerede ilk yayını olan kitaplar
    cohort: dict[str, dict[str, float]] = {}
    for code, b in info.items():
        d0 = b.get("ilk_yayin")
        if not d0 or _is_trade(code):
            continue
        dd = date.fromisoformat(d0)
        i0 = month_index(dd.year, dd.month)
        if not (w["start"] <= i0 < w["end"]):
            continue
        yv = b.get("yayinevi") or "Yayınevi belirsiz"
        k = cohort.setdefault(yv, {"baslik": 0, "adet": 0.0, "ciro": 0.0, "ay": 0.0, "maliyet": 0.0, "maliyetli_ciro": 0.0})
        k["baslik"] += 1
        k["ay"] += w["end"] - i0
        s = sales.get(code)
        if s:
            k["adet"] += max(0.0, s["adet"])
            k["ciro"] += max(0.0, s["ciro"])
            k["maliyet"] += s["maliyet"]
            k["maliyetli_ciro"] += s["maliyetli_ciro"]
    all_k = {"baslik": 0, "adet": 0.0, "ciro": 0.0, "ay": 0.0, "maliyet": 0.0, "maliyetli_ciro": 0.0}
    for k in cohort.values():
        for f in all_k:
            all_k[f] += k[f]

    def per_month(yv: str) -> tuple[float, float, Optional[float], str]:
        """Yeni kitap için: satışta geçen ay başına adet, net birim fiyat, marj, kaynak."""
        k = cohort.get(yv)
        src_label = f"{yv} yeni kitapları"
        if not k or k["ay"] <= 0 or k["adet"] <= 0:
            k, src_label = all_k, "bütün yeni kitaplar"
        if k["ay"] <= 0 or k["adet"] <= 0:
            return 0.0, 0.0, company_margin, "kohort yok"
        return k["adet"] / k["ay"], k["ciro"] / k["adet"], _margin(k["maliyet"], k["maliyetli_ciro"]) or company_margin, src_label

    books: list[dict[str, Any]] = []
    new_codes: set[str] = set()
    # yeni kitaplar: ilk yayını pencere sonundan plan yılı sonuna
    for code, b in info.items():
        d0 = b.get("ilk_yayin")
        if not d0 or _is_trade(code):
            continue
        dd = date.fromisoformat(d0)
        if not (w_end_day <= dd < y_end):
            continue
        # Yayın tarihi geçmiş ama Logo'da stok kartı hiç açılmamış kayıt o kodla yayımlanmamıştır (e-kitap, hak
        # kaydı, iptal); hedef yalnız kartı olan ya da yayın tarihi henüz gelmemiş kitaba konur.
        if not b.get("in_logo") and end and dd <= end:
            continue
        yv = b.get("yayinevi") or "Yayınevi belirsiz"
        first = 1 if dd.year < year else dd.month
        months_on = 13 - first
        rate, unit, margin, label = per_month(yv)
        adet = round(rate * months_on * (1 + g))
        unit_p = unit * (1 + p)
        m = None if margin is None else min(0.99, max(-1.0, margin + dm))
        books.append({"stok_kodu": code, "ad": b.get("ad"), "segment": "yeni", "yayinevi": b.get("yayinevi"),
                      "kitaplik": b.get("kitaplik"), "ilk_yayin": d0, "adet": float(adet), "ciro": round(adet * unit_p, 2),
                      "marj": None if m is None else round(m, 4),
                      "oneri": {"yontem": "kohort", "kaynak": label, "aySatis": round(rate, 3), "satisAyi": months_on,
                                "birimFiyat": round(unit_p, 2), "hacim": g, "fiyat": p, "marjKaynak": label}})
        new_codes.add(code)
    # backlist
    for code, s in sales.items():
        if _is_trade(code) or code in new_codes:
            continue
        b = info.get(code) or {}
        d0 = b.get("ilk_yayin")
        if d0 and date.fromisoformat(d0) >= w_end_day:
            continue
        fc_total = _forecast_total(forecast or {}, code) if use_fc else None
        base = fc_total if fc_total is not None else s["adet"]
        if base <= 0:
            continue
        adet = round(base * (1 + g))
        if adet <= 0:
            continue
        # Birim fiyat kitabın kendi net satışından; yoksa (yalnız tahmin, ya da bedelsiz çıkış) yayınevinin yeni kitap
        # ortalaması. CRM liste fiyatı iskonto öncesidir, net ciro hedefine taban olamaz.
        unit = s["ciro"] / s["adet"] if s["adet"] > 0 and s["ciro"] > 0 else None
        own = _margin(s["maliyet"], s["maliyetli_ciro"])
        if own is not None:
            margin, mlabel = own, "kitabın kendi satışı"
        else:
            margin, mlabel = pub_margin(b.get("yayinevi") or "Yayınevi belirsiz")
        if unit is None:
            _, unit, _, _ = per_month(b.get("yayinevi") or "Yayınevi belirsiz")
        unit_p = (unit or 0) * (1 + p)
        m = None if margin is None else min(0.99, max(-1.0, margin + dm))
        books.append({"stok_kodu": code, "ad": b.get("ad"), "segment": "backlist", "yayinevi": b.get("yayinevi"),
                      "kitaplik": b.get("kitaplik"), "ilk_yayin": d0, "adet": float(adet), "ciro": round(adet * unit_p, 2),
                      "marj": None if m is None else round(m, 4),
                      "oneri": {"yontem": "tahmin" if fc_total is not None else "gecmis", "tabanAdet": round(base, 2),
                                "gecmisAdet": round(s["adet"], 2), "gecmisCiro": round(s["ciro"], 2),
                                "tahminAdet": None if fc_total is None else round(fc_total, 2),
                                "birimFiyat": round(unit_p, 2), "hacim": g, "fiyat": p, "marjKaynak": mlabel}})

    # yeni kitap programı
    known: dict[str, int] = {}
    for b in books:
        if b["segment"] == "yeni":
            known[b["yayinevi"] or "Yayınevi belirsiz"] = known.get(b["yayinevi"] or "Yayınevi belirsiz", 0) + 1
    program = []
    for yv in sorted(set(cohort) | set(known)):
        k = cohort.get(yv) or {"baslik": 0, "adet": 0.0, "ciro": 0.0, "ay": 0.0, "maliyet": 0.0, "maliyetli_ciro": 0.0}
        planned = int(k["baslik"])
        extra = max(0, planned - known.get(yv, 0))
        per_title = (k["adet"] / k["baslik"]) if k["baslik"] else 0.0
        unit = (k["ciro"] / k["adet"]) if k["adet"] > 0 else 0.0
        margin = _margin(k["maliyet"], k["maliyetli_ciro"]) or company_margin
        adet_t = round(per_title * (1 + g), 1)
        program.append({"yayinevi": yv, "baslik": max(planned, known.get(yv, 0)), "bilinen": known.get(yv, 0),
                        "ek_baslik": extra, "baslik_adet": adet_t, "baslik_ciro": round(adet_t * unit * (1 + p), 2),
                        "marj": None if margin is None else round(min(0.99, max(-1.0, margin + dm)), 4),
                        "oneri": {"kohortBaslik": planned, "kohortAdet": round(k["adet"], 1), "hacim": g, "fiyat": p,
                                  "pencere": w["label"]}})

    # departman
    ge = float(params.get("gider") or 0)
    depts = []
    for (center, hesap), d in sorted(_expenses_by_line(engine, w["start"], w["end"]).items()):
        aylar = [round(x * (1 + ge), 2) for x in d["aylar"]]
        if not any(abs(x) > 0.004 for x in aylar):
            continue
        depts.append({"merkez_kodu": center, "hesap": hesap, "merkez_adi": d["merkez_adi"], "hesap_adi": d["hesap_adi"],
                      "aylar": aylar, "oneri": {"taban": [round(x, 2) for x in d["aylar"]], "gider": ge}})

    basis = {"pencere": w["label"], "pencereBas": "%04d-%02d" % from_index(w["start"]),
             "pencereSon": "%04d-%02d" % from_index(w["end"] - 1), "veriSonu": end.isoformat() if end else None,
             "tahmin": {"kullanildi": use_fc, "baslangic": (forecast or {}).get("start")},
             "dagilim": {"adet": [round(x, 6) for x in normalized(month_adet)],
                         "ciro": [round(x, 6) for x in normalized(month_ciro)]},
             "sirketMarj": None if company_margin is None else round(company_margin, 4),
             "kohort": {"baslik": all_k["baslik"], "aySatis": round(all_k["adet"] / all_k["ay"], 3) if all_k["ay"] else None}}
    return {"books": books, "program": program, "depts": depts, "basis": basis}


# ------------------------------------------------------------------ plan yazma


def _plan_row(c: Any, tenant: str, plan_id: str, *, lock: bool = False) -> Any:
    q = sa.select(PLANS).where(PLANS.c.tenant_id == tenant, PLANS.c.id == str(plan_id)[:32])
    if lock and c.engine.dialect.name == "postgresql":
        q = q.with_for_update()
    row = c.execute(q).first()
    if not row:
        raise BudgetError("Plan bulunamadı.", 404)
    return row


def _next_version(c: Any, tenant: str, year: int) -> int:
    v = c.execute(sa.select(sa.func.max(PLANS.c.version)).where(PLANS.c.tenant_id == tenant, PLANS.c.year == year)).scalar()
    return int(v or 0) + 1


def _check_year(year: Any) -> int:
    y = int(_num(year, "Yıl", minimum=2015, maximum=2100))
    return y


def _write_lines(c: Any, plan_id: str, sug: dict[str, Any]) -> None:
    for b in sug["books"]:
        c.execute(BOOKS.insert().values(
            plan_id=plan_id, stok_kodu=b["stok_kodu"][:60], ad=(b.get("ad") or "")[:400] or None, segment=b["segment"],
            yayinevi=(b.get("yayinevi") or "")[:200] or None, kitaplik=(b.get("kitaplik") or "")[:200] or None,
            ilk_yayin=b.get("ilk_yayin"), adet=b["adet"], ciro=b["ciro"], marj=b["marj"],
            oneri_json=_dump({"adet": b["adet"], "ciro": b["ciro"], "marj": b["marj"], **b["oneri"]})))
    for p in sug["program"]:
        c.execute(PROGRAM.insert().values(
            plan_id=plan_id, yayinevi=p["yayinevi"][:200], baslik=p["baslik"], bilinen=p["bilinen"], ek_baslik=p["ek_baslik"],
            baslik_adet=p["baslik_adet"], baslik_ciro=p["baslik_ciro"], marj=p["marj"],
            oneri_json=_dump({"baslik": p["baslik"], "ek_baslik": p["ek_baslik"], "baslik_adet": p["baslik_adet"],
                              "baslik_ciro": p["baslik_ciro"], "marj": p["marj"], **p["oneri"]})))
    for d in sug["depts"]:
        c.execute(DEPTS.insert().values(
            plan_id=plan_id, merkez_kodu=d["merkez_kodu"][:60], hesap=d["hesap"][:3], merkez_adi=(d["merkez_adi"] or "")[:200],
            hesap_adi=(d["hesap_adi"] or "")[:200], aylar_json=_dump(d["aylar"]),
            oneri_json=_dump({"aylar": d["aylar"], **d["oneri"]})))


def generate(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any],
             forecast: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    """Veriden hesaplanan öneri (kural, model yok): seçilen senaryolar için birer taslak plan."""
    year = _check_year(body.get("year"))
    raw = body.get("scenarios")
    scenarios = [s for s in (list(SCENARIOS) if raw is None else raw) if s in SCENARIOS]
    if not scenarios:
        raise BudgetError("En az bir senaryo seçin.")
    params = _clean_params(body.get("params") or {}, default_params(engine, year))
    out = []
    for sc in scenarios:
        sug = build_suggestion(engine, year, sc, params, forecast)
        now = _now()
        pid = uuid.uuid4().hex
        with engine.begin() as c:
            v = _next_version(c, tenant, year)
            c.execute(PLANS.insert().values(
                id=pid, tenant_id=tenant, year=year, scenario=sc, version=v, status="taslak",
                title=f"{year} · {SCENARIOS[sc]} · sürüm {v}", params_json=_dump(params), basis_json=_dump(sug["basis"]),
                created_by=user, created_at=now, updated_by=user, updated_at=now))
            _write_lines(c, pid, sug)
        out.append(plan_summary(engine, tenant, pid))
    return out


def _editable(row: Any) -> None:
    if row.status != "taslak":
        raise BudgetError("Yalnız taslak plan değiştirilebilir; yürürlükteki planı «Revize et» ile yeni sürüme alın.", 409)


def recompute(engine: sa.engine.Engine, tenant: str, user: str, plan_id: str, body: dict[str, Any],
              forecast: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Parametreler değişince öneriyi yeniden kurar; elle düzeltilmiş satırlar korunur."""
    with engine.connect() as c:
        row = _plan_row(c, tenant, plan_id)
    _editable(row)
    params = _clean_params(body.get("params") or {}, _j(row.params_json, {}))
    sug = build_suggestion(engine, row.year, row.scenario, params, forecast)
    with engine.begin() as c:
        row = _plan_row(c, tenant, plan_id, lock=True)
        _editable(row)
        kept_b = {r.stok_kodu: r for r in c.execute(sa.select(BOOKS).where(BOOKS.c.plan_id == row.id, BOOKS.c.edited_by.isnot(None))).all()}
        kept_p = {r.yayinevi: r for r in c.execute(sa.select(PROGRAM).where(PROGRAM.c.plan_id == row.id, PROGRAM.c.edited_by.isnot(None))).all()}
        kept_d = {(r.merkez_kodu, r.hesap): r for r in c.execute(sa.select(DEPTS).where(DEPTS.c.plan_id == row.id, DEPTS.c.edited_by.isnot(None))).all()}
        for t in (BOOKS, PROGRAM, DEPTS):
            c.execute(t.delete().where(t.c.plan_id == row.id))
        sug["books"] = [b for b in sug["books"] if b["stok_kodu"] not in kept_b]
        sug["program"] = [p for p in sug["program"] if p["yayinevi"] not in kept_p]
        sug["depts"] = [d for d in sug["depts"] if (d["merkez_kodu"], d["hesap"]) not in kept_d]
        _write_lines(c, row.id, sug)
        for t, kept in ((BOOKS, kept_b), (PROGRAM, kept_p), (DEPTS, kept_d)):
            for r in kept.values():
                c.execute(t.insert().values(**dict(r._mapping)))
        c.execute(PLANS.update().where(PLANS.c.id == row.id).values(
            params_json=_dump(params), basis_json=_dump(sug["basis"]), updated_by=user, updated_at=_now()))
    return plan_summary(engine, tenant, plan_id)


def update_plan(engine: sa.engine.Engine, tenant: str, user: str, plan_id: str, body: dict[str, Any]) -> dict[str, Any]:
    vals: dict[str, Any] = {}
    if "title" in body:
        t = _text(body.get("title"), 200)
        if not t:
            raise BudgetError("Plan adı boş olamaz.")
        vals["title"] = t
    if "note" in body:
        vals["note"] = _text(body.get("note"), 4000)
    if not vals:
        raise BudgetError("Değiştirilecek alan yok.")
    with engine.begin() as c:
        row = _plan_row(c, tenant, plan_id, lock=True)
        if row.status == "arsiv":
            raise BudgetError("Arşivdeki plan değiştirilemez.", 409)
        c.execute(PLANS.update().where(PLANS.c.id == row.id).values(**vals, updated_by=user, updated_at=_now()))
    return plan_summary(engine, tenant, plan_id)


def delete_plan(engine: sa.engine.Engine, tenant: str, plan_id: str) -> dict[str, Any]:
    with engine.begin() as c:
        row = _plan_row(c, tenant, plan_id, lock=True)
        if row.status not in ("taslak",):
            raise BudgetError("Yalnız taslak plan silinebilir.", 409)
        for t in (BOOKS, PROGRAM, DEPTS):
            c.execute(t.delete().where(t.c.plan_id == row.id))
        c.execute(PLANS.delete().where(PLANS.c.id == row.id))
    return {"id": row.id, "title": row.title}


def submit(engine: sa.engine.Engine, tenant: str, user: str, plan_id: str) -> dict[str, Any]:
    with engine.begin() as c:
        row = _plan_row(c, tenant, plan_id, lock=True)
        if row.status != "taslak":
            raise BudgetError("Yalnız taslak onaya gönderilir.", 409)
        n = c.execute(sa.select(sa.func.count()).select_from(BOOKS).where(BOOKS.c.plan_id == row.id)).scalar()
        if not n:
            raise BudgetError("Planda kitap hedefi yok.")
        c.execute(PLANS.update().where(PLANS.c.id == row.id).values(
            status="onayda", submitted_by=user, submitted_at=_now(), decision_note=None, updated_by=user, updated_at=_now()))
    return plan_summary(engine, tenant, plan_id)


def withdraw(engine: sa.engine.Engine, tenant: str, user: str, plan_id: str) -> dict[str, Any]:
    with engine.begin() as c:
        row = _plan_row(c, tenant, plan_id, lock=True)
        if row.status != "onayda":
            raise BudgetError("Plan onayda değil.", 409)
        c.execute(PLANS.update().where(PLANS.c.id == row.id).values(status="taslak", updated_by=user, updated_at=_now()))
    return plan_summary(engine, tenant, plan_id)


def decide(engine: sa.engine.Engine, tenant: str, user: str, plan_id: str, approve: bool, note: Any = None) -> dict[str, Any]:
    """Onay ya da geri gönderme. Gönderen onaylayamaz (iki göz). Onayda önceki yürürlükteki plan arşive geçer."""
    note_t = _text(note, 2000)
    if not approve and not note_t:
        raise BudgetError("Geri gönderme gerekçesi yazın.")
    archived = None
    with engine.begin() as c:
        row = _plan_row(c, tenant, plan_id, lock=True)
        if row.status != "onayda":
            raise BudgetError("Plan onay beklemiyor.", 409)
        if (row.submitted_by or "").lower() == user.lower():
            raise BudgetError("Onaya gönderen kişi aynı planı onaylayamaz; başka bir yetkili onaylamalı.", 409)
        now = _now()
        if approve:
            prev = c.execute(sa.select(PLANS).where(PLANS.c.tenant_id == tenant, PLANS.c.year == row.year,
                                                    PLANS.c.status == "onayli")).first()
            if prev:
                c.execute(PLANS.update().where(PLANS.c.id == prev.id).values(status="arsiv", updated_by=user, updated_at=now))
                archived = prev.id
            c.execute(PLANS.update().where(PLANS.c.id == row.id).values(
                status="onayli", decided_by=user, decided_at=now, decision_note=note_t, updated_by=user, updated_at=now))
            c.execute(ALERTS.insert().values(
                id=uuid.uuid4().hex, tenant_id=tenant, year=row.year, plan_id=row.id, kind="revizyon", scope="toplam",
                key=f"plan:{row.id}", label=f"{row.title} yürürlüğe girdi" + (" (önceki plan arşivlendi)" if prev else ""),
                detail_json=_dump({"onceki": archived, "onaylayan": user}), modules=SALES_ALERT_MODULES,
                status="bilgi", first_at=now, last_at=now))
        else:
            c.execute(PLANS.update().where(PLANS.c.id == row.id).values(
                status="taslak", decided_by=user, decided_at=now, decision_note=note_t, updated_by=user, updated_at=now))
    out = plan_summary(engine, tenant, plan_id)
    out["archived"] = archived
    return out


def revise(engine: sa.engine.Engine, tenant: str, user: str, plan_id: str, reason: Any) -> dict[str, Any]:
    """Yürürlükteki planın yeni taslak sürümü (sezon/piyasa değişimi). Onaylanınca eskisinin yerini alır."""
    why = _text(reason, 2000)
    if not why:
        raise BudgetError("Revizyon gerekçesi yazın.")
    with engine.begin() as c:
        row = _plan_row(c, tenant, plan_id)
        if row.status != "onayli":
            raise BudgetError("Yalnız yürürlükteki plan revize edilir.", 409)
        now = _now()
        pid = uuid.uuid4().hex
        v = _next_version(c, tenant, row.year)
        c.execute(PLANS.insert().values(
            id=pid, tenant_id=tenant, year=row.year, scenario=row.scenario, version=v, status="taslak",
            title=f"{row.year} · {SCENARIOS.get(row.scenario, row.scenario)} · sürüm {v} (revizyon)",
            params_json=row.params_json, basis_json=row.basis_json, note=row.note, revision_of=row.id,
            revision_reason=why, created_by=user, created_at=now, updated_by=user, updated_at=now))
        for t in (BOOKS, PROGRAM, DEPTS):
            for r in c.execute(sa.select(t).where(t.c.plan_id == row.id)).all():
                c.execute(t.insert().values(**{**dict(r._mapping), "plan_id": pid}))
    return plan_summary(engine, tenant, pid)


# ------------------------------------------------------------------ satır düzeltme


def update_book(engine: sa.engine.Engine, tenant: str, user: str, plan_id: str, code: str, body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    vals: dict[str, Any] = {}
    if "adet" in body:
        vals["adet"] = float(round(_num(body["adet"], "Hedef adet")))
    if "ciro" in body:
        vals["ciro"] = round(_num(body["ciro"], "Hedef ciro"), 2)
    if "marj" in body:
        m = _num(body["marj"], "Hedef marj", allow_none=True, minimum=-1, maximum=0.99)
        vals["marj"] = None if m is None else round(m, 4)
    if "note" in body:
        vals["note"] = _text(body.get("note"), 500)
    if not vals:
        raise BudgetError("Değiştirilecek alan yok.")
    with engine.begin() as c:
        row = _plan_row(c, tenant, plan_id, lock=True)
        _editable(row)
        cur = c.execute(sa.select(BOOKS).where(BOOKS.c.plan_id == row.id, BOOKS.c.stok_kodu == code)).first()
        if not cur:
            raise BudgetError("Bu planda böyle bir kitap yok.", 404)
        diff = {k: {"eski": getattr(cur, k), "yeni": v} for k, v in vals.items() if getattr(cur, k) != v}
        c.execute(BOOKS.update().where(BOOKS.c.plan_id == row.id, BOOKS.c.stok_kodu == code).values(
            **vals, edited_by=user, edited_at=_now()))
        c.execute(PLANS.update().where(PLANS.c.id == row.id).values(updated_by=user, updated_at=_now()))
    return book_row(engine, tenant, plan_id, code), diff


def add_book(engine: sa.engine.Engine, tenant: str, user: str, plan_id: str, body: dict[str, Any]) -> dict[str, Any]:
    code = _text(body.get("stokKodu"), 60)
    if not code:
        raise BudgetError("Stok kodu boş olamaz.")
    info = _book_info(engine).get(code) or {}
    with engine.connect() as c:
        row = _plan_row(c, tenant, plan_id)
    seg = body.get("segment") if body.get("segment") in SEGMENTS else (
        "yeni" if (info.get("ilk_yayin") or "")[:4] == str(row.year) else "backlist")
    with engine.begin() as c:
        row = _plan_row(c, tenant, plan_id, lock=True)
        _editable(row)
        if c.execute(sa.select(BOOKS.c.stok_kodu).where(BOOKS.c.plan_id == row.id, BOOKS.c.stok_kodu == code)).first():
            raise BudgetError("Bu kitap planda zaten var.", 409)
        adet = float(round(_num(body.get("adet"), "Hedef adet")))
        ciro = round(_num(body.get("ciro"), "Hedef ciro"), 2)
        marj = _num(body.get("marj"), "Hedef marj", allow_none=True, minimum=-1, maximum=0.99)
        c.execute(BOOKS.insert().values(
            plan_id=row.id, stok_kodu=code, ad=_text(body.get("ad"), 400) or info.get("ad"), segment=seg,
            yayinevi=info.get("yayinevi"), kitaplik=info.get("kitaplik"), ilk_yayin=info.get("ilk_yayin"),
            adet=adet, ciro=ciro, marj=marj, oneri_json=_dump({"yontem": "elle"}), note=_text(body.get("note"), 500),
            edited_by=user, edited_at=_now()))
    return book_row(engine, tenant, plan_id, code)


def delete_book(engine: sa.engine.Engine, tenant: str, user: str, plan_id: str, code: str) -> dict[str, Any]:
    with engine.begin() as c:
        row = _plan_row(c, tenant, plan_id, lock=True)
        _editable(row)
        cur = c.execute(sa.select(BOOKS).where(BOOKS.c.plan_id == row.id, BOOKS.c.stok_kodu == code)).first()
        if not cur:
            raise BudgetError("Bu planda böyle bir kitap yok.", 404)
        c.execute(BOOKS.delete().where(BOOKS.c.plan_id == row.id, BOOKS.c.stok_kodu == code))
        c.execute(PLANS.update().where(PLANS.c.id == row.id).values(updated_by=user, updated_at=_now()))
    return {"stokKodu": code, "ad": cur.ad}


def update_program(engine: sa.engine.Engine, tenant: str, user: str, plan_id: str, yayinevi: str, body: dict[str, Any]) -> dict[str, Any]:
    vals: dict[str, Any] = {}
    if "ekBaslik" in body:
        vals["ek_baslik"] = int(round(_num(body["ekBaslik"], "Ek başlık sayısı")))
    if "baslikAdet" in body:
        vals["baslik_adet"] = round(_num(body["baslikAdet"], "Başlık başına adet"), 1)
    if "baslikCiro" in body:
        vals["baslik_ciro"] = round(_num(body["baslikCiro"], "Başlık başına ciro"), 2)
    if "marj" in body:
        m = _num(body["marj"], "Marj", allow_none=True, minimum=-1, maximum=0.99)
        vals["marj"] = None if m is None else round(m, 4)
    if "note" in body:
        vals["note"] = _text(body.get("note"), 500)
    if not vals:
        raise BudgetError("Değiştirilecek alan yok.")
    with engine.begin() as c:
        row = _plan_row(c, tenant, plan_id, lock=True)
        _editable(row)
        cur = c.execute(sa.select(PROGRAM).where(PROGRAM.c.plan_id == row.id, PROGRAM.c.yayinevi == yayinevi)).first()
        if not cur:
            raise BudgetError("Bu planda böyle bir program satırı yok.", 404)
        if "ek_baslik" in vals:
            vals["baslik"] = cur.bilinen + vals["ek_baslik"]
        c.execute(PROGRAM.update().where(PROGRAM.c.plan_id == row.id, PROGRAM.c.yayinevi == yayinevi).values(
            **vals, edited_by=user, edited_at=_now()))
        c.execute(PLANS.update().where(PLANS.c.id == row.id).values(updated_by=user, updated_at=_now()))
    return next(p for p in program(engine, tenant, plan_id)["items"] if p["yayinevi"] == yayinevi)


def update_dept(engine: sa.engine.Engine, tenant: str, user: str, plan_id: str, center: str, hesap: str,
                body: dict[str, Any]) -> dict[str, Any]:
    with engine.begin() as c:
        row = _plan_row(c, tenant, plan_id, lock=True)
        _editable(row)
        cur = c.execute(sa.select(DEPTS).where(DEPTS.c.plan_id == row.id, DEPTS.c.merkez_kodu == center,
                                                DEPTS.c.hesap == hesap)).first()
        if not cur:
            raise BudgetError("Bu planda böyle bir bütçe satırı yok.", 404)
        aylar = _j(cur.aylar_json, [0.0] * 12)
        if "aylar" in body:
            raw = body["aylar"]
            if not isinstance(raw, list) or len(raw) != 12:
                raise BudgetError("12 aylık tutar gerekli.")
            aylar = [round(_num(x, f"{AY[i]} tutarı", minimum=None), 2) for i, x in enumerate(raw)]
        elif "yillik" in body:
            total = _num(body["yillik"], "Yıllık bütçe", minimum=None)
            base = sum(aylar)
            shares = [x / base for x in aylar] if base else [1 / 12] * 12
            aylar = [round(total * s, 2) for s in shares]
        else:
            raise BudgetError("Değiştirilecek alan yok.")
        vals = {"aylar_json": _dump(aylar), "edited_by": user, "edited_at": _now()}
        if "note" in body:
            vals["note"] = _text(body.get("note"), 500)
        c.execute(DEPTS.update().where(DEPTS.c.plan_id == row.id, DEPTS.c.merkez_kodu == center, DEPTS.c.hesap == hesap).values(**vals))
        c.execute(PLANS.update().where(PLANS.c.id == row.id).values(updated_by=user, updated_at=_now()))
    return next(d for d in departments(engine, tenant, plan_id)["items"] if d["merkezKodu"] == center and d["hesap"] == hesap)


# ------------------------------------------------------------------ okuma: plan


def _totals(c: Any, plan_id: str) -> dict[str, Any]:
    seg = {}
    for s, n, adet, ciro, kar in c.execute(
            sa.select(BOOKS.c.segment, sa.func.count(), sa.func.sum(BOOKS.c.adet), sa.func.sum(BOOKS.c.ciro),
                      sa.func.sum(BOOKS.c.ciro * sa.func.coalesce(BOOKS.c.marj, 0)))
            .where(BOOKS.c.plan_id == plan_id).group_by(BOOKS.c.segment)).all():
        seg[s] = {"kitap": int(n), "adet": float(adet or 0), "ciro": float(ciro or 0), "brutKar": float(kar or 0)}
    prog = c.execute(sa.select(sa.func.sum(PROGRAM.c.ek_baslik), sa.func.sum(PROGRAM.c.ek_baslik * PROGRAM.c.baslik_adet),
                               sa.func.sum(PROGRAM.c.ek_baslik * PROGRAM.c.baslik_ciro),
                               sa.func.sum(PROGRAM.c.ek_baslik * PROGRAM.c.baslik_ciro * sa.func.coalesce(PROGRAM.c.marj, 0)))
                     .where(PROGRAM.c.plan_id == plan_id)).first()
    program_t = {"ekBaslik": int(prog[0] or 0), "adet": float(prog[1] or 0), "ciro": float(prog[2] or 0), "brutKar": float(prog[3] or 0)}
    gider = sum(sum(_j(r.aylar_json, [])) for r in c.execute(sa.select(DEPTS.c.aylar_json).where(DEPTS.c.plan_id == plan_id)).all())
    adet = sum(s["adet"] for s in seg.values()) + program_t["adet"]
    ciro = sum(s["ciro"] for s in seg.values()) + program_t["ciro"]
    kar = sum(s["brutKar"] for s in seg.values()) + program_t["brutKar"]
    return {"segments": seg, "program": program_t, "adet": adet, "ciro": ciro, "brutKar": kar,
            "marj": (kar / ciro) if ciro else None, "gider": gider,
            "kitap": sum(s["kitap"] for s in seg.values())}


def _plan_dict(row: Any, totals: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    return {
        "id": row.id, "year": row.year, "scenario": row.scenario, "scenarioLabel": SCENARIOS.get(row.scenario, row.scenario),
        "version": row.version, "status": row.status, "statusLabel": STATUSES.get(row.status, row.status),
        "title": row.title, "note": row.note, "params": _j(row.params_json, {}), "basis": _j(row.basis_json, {}),
        "revisionOf": row.revision_of, "revisionReason": row.revision_reason,
        "createdBy": row.created_by, "createdAt": _iso(row.created_at), "updatedBy": row.updated_by, "updatedAt": _iso(row.updated_at),
        "submittedBy": row.submitted_by, "submittedAt": _iso(row.submitted_at),
        "decidedBy": row.decided_by, "decidedAt": _iso(row.decided_at), "decisionNote": row.decision_note,
        **({"totals": totals} if totals is not None else {}),
    }


def plan_summary(engine: sa.engine.Engine, tenant: str, plan_id: str) -> dict[str, Any]:
    with engine.connect() as c:
        row = _plan_row(c, tenant, plan_id)
        return _plan_dict(row, _totals(c, row.id))


def list_plans(engine: sa.engine.Engine, tenant: str, year: Optional[int] = None) -> dict[str, Any]:
    with engine.connect() as c:
        q = sa.select(PLANS).where(PLANS.c.tenant_id == tenant)
        if year:
            q = q.where(PLANS.c.year == int(year))
        rows = c.execute(q.order_by(PLANS.c.year.desc(), PLANS.c.version.desc())).all()
        items = [_plan_dict(r, _totals(c, r.id)) for r in rows]
        years = sorted({r[0] for r in c.execute(sa.select(PLANS.c.year).where(PLANS.c.tenant_id == tenant).distinct()).all()})
    return {"items": items, "years": years}


def _approved(c: Any, tenant: str, year: int) -> Any:
    return c.execute(sa.select(PLANS).where(PLANS.c.tenant_id == tenant, PLANS.c.year == year, PLANS.c.status == "onayli")).first()


# ------------------------------------------------------------------ izleme


def _asof(engine: sa.engine.Engine, year: int) -> Optional[date]:
    end = data_end(engine)
    if end is None or end < date(year, 1, 1):
        return None
    return min(end, date(year, 12, 31))


def _book_weights(basis: dict[str, Any], segment: str, ilk_yayin: Optional[str], year: int, kind: str) -> list[float]:
    w = normalized((basis.get("dagilim") or {}).get(kind) or [1] * 12)
    if segment == "yeni" and ilk_yayin:
        d = date.fromisoformat(ilk_yayin)
        first = 1 if d.year < year else (13 if d.year > year else d.month)
        return active_weights(w, first)
    return w


def _status(ratio: Optional[float], threshold: float) -> str:
    if ratio is None:
        return "baslamadi"
    if ratio >= 1:
        return "iyi"
    if ratio >= threshold:
        return "izle"
    return "sapma"


def _track_books(engine: sa.engine.Engine, row: Any, rows: list[Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Kitap satırlarına gerçekleşme ekler."""
    asof = _asof(engine, row.year)
    basis = _j(row.basis_json, {})
    threshold = float(_j(row.params_json, {}).get("esik") or DEFAULT_THRESHOLD)
    elapsed = elapsed_shares(row.year, asof)
    actual = _sales_by_code(engine, month_index(row.year, 1), month_index(row.year, 13)) if asof else {}
    out = []
    for r in rows:
        a = actual.get(r.stok_kodu) or {"adet": 0.0, "ciro": 0.0, "maliyet": 0.0, "maliyetli_ciro": 0.0}
        wa = _book_weights(basis, r.segment, r.ilk_yayin, row.year, "adet")
        wc = _book_weights(basis, r.segment, r.ilk_yayin, row.year, "ciro")
        exp_a = r.adet * expected_share(wa, elapsed)
        exp_c = r.ciro * expected_share(wc, elapsed)
        ratio_c = (a["ciro"] / exp_c) if exp_c > 0 else None
        ratio_a = (a["adet"] / exp_a) if exp_a > 0 else None
        # durum ciroya göre (hedefin parasal karşılığı); cirosuz hedefte adete göre
        ratio = ratio_c if r.ciro > 0 else ratio_a
        out.append({"beklenenAdet": round(exp_a, 1), "beklenenCiro": round(exp_c, 2), "gercekAdet": round(a["adet"], 1),
                    "gercekCiro": round(a["ciro"], 2), "gercekMarj": _margin(a["maliyet"], a["maliyetli_ciro"]),
                    "oranAdet": None if ratio_a is None else round(ratio_a, 4),
                    "oranCiro": None if ratio_c is None else round(ratio_c, 4),
                    "durum": _status(ratio, threshold)})
    return out, {"asof": asof.isoformat() if asof else None, "esik": threshold, "gecenPay": round(sum(elapsed) / 12, 4)}


def _book_dict(r: Any, track: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    o = _j(r.oneri_json, {})
    return {"stokKodu": r.stok_kodu, "ad": r.ad, "segment": r.segment, "segmentLabel": SEGMENTS.get(r.segment, r.segment),
            "yayinevi": r.yayinevi, "kitaplik": r.kitaplik, "ilkYayin": r.ilk_yayin, "adet": r.adet, "ciro": r.ciro,
            "marj": r.marj, "brutKar": None if r.marj is None else round(r.ciro * r.marj, 2), "oneri": o,
            "elle": r.edited_by is not None, "note": r.note, "editedBy": r.edited_by, "editedAt": _iso(r.edited_at),
            **({"izleme": track} if track is not None else {})}


SORTS = {
    "ciro": (BOOKS.c.ciro.desc(),), "adet": (BOOKS.c.adet.desc(),), "ad": (BOOKS.c.ad.asc(),),
    "kod": (BOOKS.c.stok_kodu.asc(),),
}


def books(engine: sa.engine.Engine, tenant: str, plan_id: str, *, segment: str = "", q: str = "", yayinevi: str = "",
          sort: str = "ciro", page: int = 0, durum: str = "") -> dict[str, Any]:
    with engine.connect() as c:
        row = _plan_row(c, tenant, plan_id)
        cond = [BOOKS.c.plan_id == row.id]
        if segment in SEGMENTS:
            cond.append(BOOKS.c.segment == segment)
        if yayinevi:
            cond.append(BOOKS.c.yayinevi == yayinevi)
        if q.strip():
            like = "%" + q.strip().lower().replace("%", "").replace("_", "") + "%"
            cond.append(sa.or_(sa.func.lower(BOOKS.c.ad).like(like), sa.func.lower(BOOKS.c.stok_kodu).like(like)))
        rows = c.execute(sa.select(BOOKS).where(*cond).order_by(*SORTS.get(sort, SORTS["ciro"]), BOOKS.c.stok_kodu)).all()
        pubs = [p for (p,) in c.execute(sa.select(BOOKS.c.yayinevi).where(BOOKS.c.plan_id == row.id).distinct()).all() if p]
    trackable = _asof(engine, row.year) is not None
    if trackable:
        tr, info = _track_books(engine, row, rows)
        items = [_book_dict(r, t) for r, t in zip(rows, tr)]
        if durum in ("iyi", "izle", "sapma", "baslamadi"):
            items = [i for i in items if i["izleme"]["durum"] == durum]
        if sort == "sapma":
            items.sort(key=lambda i: (i["izleme"]["gercekCiro"] - i["izleme"]["beklenenCiro"]))
    else:
        info = {"asof": None}
        items = [_book_dict(r) for r in rows]
    total = len(items)
    page = max(0, int(page))
    return {"items": items[page * PAGE_SIZE:(page + 1) * PAGE_SIZE], "total": total, "page": page, "pageSize": PAGE_SIZE,
            "yayinevleri": sorted(pubs, key=lambda s: s.lower()), "izleme": info}


def book_row(engine: sa.engine.Engine, tenant: str, plan_id: str, code: str) -> dict[str, Any]:
    with engine.connect() as c:
        row = _plan_row(c, tenant, plan_id)
        r = c.execute(sa.select(BOOKS).where(BOOKS.c.plan_id == row.id, BOOKS.c.stok_kodu == code)).first()
    if not r:
        raise BudgetError("Bu planda böyle bir kitap yok.", 404)
    if _asof(engine, row.year):
        t, _ = _track_books(engine, row, [r])
        return _book_dict(r, t[0])
    return _book_dict(r)


def program(engine: sa.engine.Engine, tenant: str, plan_id: str) -> dict[str, Any]:
    with engine.connect() as c:
        row = _plan_row(c, tenant, plan_id)
        rows = c.execute(sa.select(PROGRAM).where(PROGRAM.c.plan_id == row.id).order_by(PROGRAM.c.yayinevi)).all()
    items = [{"yayinevi": r.yayinevi, "baslik": r.baslik, "bilinen": r.bilinen, "ekBaslik": r.ek_baslik,
              "baslikAdet": r.baslik_adet, "baslikCiro": r.baslik_ciro, "marj": r.marj,
              "adet": round(r.ek_baslik * r.baslik_adet, 1), "ciro": round(r.ek_baslik * r.baslik_ciro, 2),
              "oneri": _j(r.oneri_json, {}), "elle": r.edited_by is not None, "note": r.note,
              "editedBy": r.edited_by, "editedAt": _iso(r.edited_at)} for r in rows]
    return {"items": items}


def departments(engine: sa.engine.Engine, tenant: str, plan_id: str) -> dict[str, Any]:
    with engine.connect() as c:
        row = _plan_row(c, tenant, plan_id)
        rows = c.execute(sa.select(DEPTS).where(DEPTS.c.plan_id == row.id).order_by(DEPTS.c.merkez_kodu, DEPTS.c.hesap)).all()
    asof = _asof(engine, row.year)
    elapsed = elapsed_shares(row.year, asof)
    actual = _expenses_by_line(engine, month_index(row.year, 1), month_index(row.year, 13)) if asof else {}
    month_now = asof.month if asof else None
    items = []
    for r in rows:
        aylar = _j(r.aylar_json, [0.0] * 12)
        a = (actual.get((r.merkez_kodu, r.hesap)) or {}).get("aylar") or [0.0] * 12
        budget_ytd = sum(b * e for b, e in zip(aylar, elapsed))
        actual_ytd = sum(a)
        usage = (actual_ytd / budget_ytd) if budget_ytd > 0 else None
        items.append({
            "merkezKodu": r.merkez_kodu, "merkezAdi": r.merkez_adi, "hesap": r.hesap, "hesapAdi": r.hesap_adi,
            "aylar": aylar, "yillik": round(sum(aylar), 2), "oneri": _j(r.oneri_json, {}), "elle": r.edited_by is not None,
            "note": r.note, "editedBy": r.edited_by,
            **({"izleme": {"butceDonem": round(budget_ytd, 2), "gercek": round(actual_ytd, 2), "gercekAylar": [round(x, 2) for x in a],
                           "kullanim": None if usage is None else round(usage, 4),
                           "buAyKullanim": (round(a[month_now - 1] / (aylar[month_now - 1] * elapsed[month_now - 1]), 4)
                                            if month_now and aylar[month_now - 1] > 0 and elapsed[month_now - 1] > 0 else None),
                           "durum": ("asim" if usage is not None and usage >= 1 else
                                     "yaklasti" if usage is not None and usage >= EARLY_WARNING else
                                     "normal" if usage is not None else "baslamadi")}} if asof else {})})
    return {"items": items, "asof": asof.isoformat() if asof else None}


def tracking(engine: sa.engine.Engine, tenant: str, year: int, plan_id: Optional[str] = None) -> dict[str, Any]:
    """Hedef–gerçekleşme özeti: toplam, segment, yayınevi, ay ay seri, departman kullanımı."""
    with engine.connect() as c:
        row = _plan_row(c, tenant, plan_id) if plan_id else _approved(c, tenant, int(year))
        if row is None:
            return {"year": int(year), "plan": None}
        rows = c.execute(sa.select(BOOKS).where(BOOKS.c.plan_id == row.id)).all()
        plan = _plan_dict(row, _totals(c, row.id))
    asof = _asof(engine, row.year)
    if asof is None:
        return {"year": row.year, "plan": plan, "asof": None}
    tr, info = _track_books(engine, row, rows)
    basis = _j(row.basis_json, {})
    groups: dict[str, dict[str, dict[str, float]]] = {"segment": {}, "yayinevi": {}}
    total = {"hedefCiro": 0.0, "hedefAdet": 0.0, "beklenenCiro": 0.0, "beklenenAdet": 0.0, "gercekCiro": 0.0, "gercekAdet": 0.0}
    counts = {"iyi": 0, "izle": 0, "sapma": 0, "baslamadi": 0}
    for r, t in zip(rows, tr):
        counts[t["durum"]] += 1
        vals = {"hedefCiro": r.ciro, "hedefAdet": r.adet, "beklenenCiro": t["beklenenCiro"], "beklenenAdet": t["beklenenAdet"],
                "gercekCiro": t["gercekCiro"], "gercekAdet": t["gercekAdet"]}
        for k in total:
            total[k] += vals[k]
        for g, key in (("segment", SEGMENTS.get(r.segment, r.segment)), ("yayinevi", r.yayinevi or "Yayınevi belirsiz")):
            d = groups[g].setdefault(key, {k: 0.0 for k in total} | {"kitap": 0})
            d["kitap"] += 1
            for k in total:
                d[k] += vals[k]
    # hedef dışı satış: planda olmayan kitapların gerçekleşmesi (yeni kitap programı ve eksik kalanlar)
    all_actual = _sales_by_code(engine, month_index(row.year, 1), month_index(row.year, 13))
    in_plan = {r.stok_kodu for r in rows}
    outside = {"ciro": 0.0, "adet": 0.0, "kitap": 0}
    for code, a in all_actual.items():
        if code in in_plan or _is_trade(code):
            continue
        outside["ciro"] += a["ciro"]
        outside["adet"] += a["adet"]
        outside["kitap"] += 1
    prog = plan["totals"]["program"]
    elapsed = elapsed_shares(row.year, asof)
    wc = normalized((basis.get("dagilim") or {}).get("ciro") or [1] * 12)
    program_expected = prog["ciro"] * expected_share(wc, elapsed)
    # ay ay seri (ciro): hedef dağılımı ve gerçekleşme
    series = []
    month_actual = [0.0] * 12
    with engine.connect() as c:
        for y, m, ciro in c.execute(sa.select(SALES.c.year, SALES.c.month, sa.func.sum(SALES.c.ciro))
                                    .where(SALES.c.year == row.year, ~SALES.c.stok_kodu.like("157%"))
                                    .group_by(SALES.c.year, SALES.c.month)).all():
            month_actual[m - 1] = float(ciro or 0)
    plan_ciro = plan["totals"]["ciro"]
    for i in range(12):
        series.append({"ay": i + 1, "hedef": round(plan_ciro * wc[i], 2),
                       "gercek": round(month_actual[i], 2) if elapsed[i] > 0 else None, "gecen": elapsed[i]})

    def fin(d: dict[str, float]) -> dict[str, Any]:
        ratio = d["gercekCiro"] / d["beklenenCiro"] if d["beklenenCiro"] > 0 else None
        return {**{k: round(v, 2) for k, v in d.items()}, "oran": None if ratio is None else round(ratio, 4),
                "durum": _status(ratio, info["esik"])}

    tot_all = dict(total)
    tot_all["beklenenCiro"] += program_expected
    tot_all["gercekCiro"] += outside["ciro"]
    tot_all["hedefCiro"] += prog["ciro"]
    dep = departments(engine, tenant, row.id)
    dep_tot = {"butce": 0.0, "butceDonem": 0.0, "gercek": 0.0}
    for d in dep["items"]:
        dep_tot["butce"] += d["yillik"]
        if d.get("izleme"):
            dep_tot["butceDonem"] += d["izleme"]["butceDonem"]
            dep_tot["gercek"] += d["izleme"]["gercek"]
    return {
        "year": row.year, "plan": plan, "asof": info["asof"], "esik": info["esik"], "gecenPay": info["gecenPay"],
        "uyariKapsam": (lambda share, keys: {"pay": share, "kitap": len(keys),
                                             "sapma": sum(1 for r, t in zip(rows, tr) if t["durum"] == "sapma" and r.stok_kodu in keys)})(
            float(plan["params"].get("uyariKapsam") or DEFAULT_ALERT_SCOPE),
            alert_scope(rows, float(plan["params"].get("uyariKapsam") or DEFAULT_ALERT_SCOPE))),
        "kitapHedefleri": fin(total), "sirket": fin(tot_all),
        "program": {"hedefCiro": round(prog["ciro"], 2), "beklenenCiro": round(program_expected, 2)},
        "hedefDisi": {k: round(v, 2) if isinstance(v, float) else v for k, v in outside.items()},
        "durumlar": counts,
        "segmentler": [{"ad": k, **fin(v)} for k, v in sorted(groups["segment"].items())],
        "yayinevleri": [{"ad": k, **fin(v)} for k, v in sorted(groups["yayinevi"].items(), key=lambda kv: -kv[1]["hedefCiro"])],
        "aylar": series,
        "gider": {**{k: round(v, 2) for k, v in dep_tot.items()},
                  "kullanim": round(dep_tot["gercek"] / dep_tot["butceDonem"], 4) if dep_tot["butceDonem"] > 0 else None,
                  "asim": sum(1 for d in dep["items"] if (d.get("izleme") or {}).get("durum") == "asim"),
                  "yaklasti": sum(1 for d in dep["items"] if (d.get("izleme") or {}).get("durum") == "yaklasti")},
    }


def compare(engine: sa.engine.Engine, tenant: str, year: int) -> dict[str, Any]:
    """Aynı yılın planları yan yana (arşiv hariç): senaryo seçimi için."""
    with engine.connect() as c:
        rows = c.execute(sa.select(PLANS).where(PLANS.c.tenant_id == tenant, PLANS.c.year == int(year),
                                                PLANS.c.status != "arsiv").order_by(PLANS.c.version)).all()
        items = [_plan_dict(r, _totals(c, r.id)) for r in rows]
    end = data_end(engine)
    ref = None
    if end:
        w = window(int(year), end)
        s = _sales_by_code(engine, w["start"], w["end"])
        ref = {"pencere": w["label"], "ciro": round(sum(v["ciro"] for k, v in s.items() if not _is_trade(k)), 2),
               "adet": round(sum(v["adet"] for k, v in s.items() if not _is_trade(k)), 1)}
        e = _expenses_by_line(engine, w["start"], w["end"])
        ref["gider"] = round(sum(sum(d["aylar"]) for d in e.values()), 2)
    return {"year": int(year), "items": items, "taban": ref}


# ------------------------------------------------------------------ sözleşme: diğer modüllerin okuduğu hedefler


def approved_targets(engine: sa.engine.Engine, tenant: str, year: int, *, codes: Optional[Iterable[str]] = None,
                     segment: str = "", yayinevi: str = "", with_actuals: bool = True) -> dict[str, Any]:
    """Yürürlükteki planın kitap hedefleri (M15/M17/M18/M29/M30 okur). Onaylı plan yoksa `plan: None`."""
    with engine.connect() as c:
        row = _approved(c, tenant, int(year))
        if row is None:
            return {"year": int(year), "plan": None, "items": [], "program": []}
        cond = [BOOKS.c.plan_id == row.id]
        want = [str(x).strip() for x in (codes or []) if str(x).strip()]
        if want:
            cond.append(BOOKS.c.stok_kodu.in_(want))
        if segment in SEGMENTS:
            cond.append(BOOKS.c.segment == segment)
        if yayinevi:
            cond.append(BOOKS.c.yayinevi == yayinevi)
        rows = c.execute(sa.select(BOOKS).where(*cond).order_by(BOOKS.c.ciro.desc(), BOOKS.c.stok_kodu)).all()
        prog = c.execute(sa.select(PROGRAM).where(PROGRAM.c.plan_id == row.id).order_by(PROGRAM.c.yayinevi)).all()
    basis = _j(row.basis_json, {})
    track = _track_books(engine, row, rows)[0] if (with_actuals and _asof(engine, row.year)) else [None] * len(rows)
    items = []
    for r, t in zip(rows, track):
        wa = _book_weights(basis, r.segment, r.ilk_yayin, row.year, "adet")
        wc = _book_weights(basis, r.segment, r.ilk_yayin, row.year, "ciro")
        items.append({
            "stokKodu": r.stok_kodu, "ad": r.ad, "segment": r.segment, "yayinevi": r.yayinevi, "kitaplik": r.kitaplik,
            "ilkYayin": r.ilk_yayin,
            "hedef": {"adet": r.adet, "ciro": r.ciro, "marj": r.marj, "brutKar": None if r.marj is None else round(r.ciro * r.marj, 2)},
            "aylik": [{"ay": i + 1, "adet": round(r.adet * wa[i], 2), "ciro": round(r.ciro * wc[i], 2)} for i in range(12)],
            **({"gerceklesme": t} if t is not None else {}),
        })
    return {
        "year": row.year,
        "plan": {"id": row.id, "version": row.version, "scenario": row.scenario, "title": row.title,
                 "approvedAt": _iso(row.decided_at), "approvedBy": row.decided_by, "revisionOf": row.revision_of},
        "asof": (lambda d: d.isoformat() if d else None)(_asof(engine, row.year)),
        "items": items,
        "program": [{"yayinevi": p.yayinevi, "ekBaslik": p.ek_baslik, "baslikAdet": p.baslik_adet,
                     "baslikCiro": p.baslik_ciro, "marj": p.marj} for p in prog],
    }


# ------------------------------------------------------------------ uyarılar


def alert_scope(rows: list[Any], share: float) -> set[str]:
    """Hedef cirosu büyükten küçüğe sıralanınca toplamın `share` payını oluşturan kitaplar (payı geçen kitap dahil)."""
    ordered = sorted(rows, key=lambda r: (-(r.ciro or 0), r.stok_kodu))
    total = sum(max(0.0, r.ciro or 0) for r in ordered)
    out: set[str] = set()
    acc = 0.0
    for r in ordered:
        if total > 0 and acc >= share * total - 1e-9:
            break
        out.add(r.stok_kodu)
        acc += max(0.0, r.ciro or 0)
    return out


def evaluate_alerts(engine: sa.engine.Engine, tenant: str, year: int) -> dict[str, Any]:
    """Yürürlükteki planda %eşik altındaki kitap/yayınevi/toplam ve aşan departman satırı için uyarı açar; düzelen kapanır."""
    with engine.connect() as c:
        row = _approved(c, tenant, year)
    if row is None or _asof(engine, year) is None:
        return {"year": year, "opened": 0, "closed": 0, "open": 0}
    tr = tracking(engine, tenant, year, row.id)
    with engine.connect() as c:
        rows = c.execute(sa.select(BOOKS).where(BOOKS.c.plan_id == row.id)).all()
    t_books, _ = _track_books(engine, row, rows)
    scope = float(_j(row.params_json, {}).get("uyariKapsam") or DEFAULT_ALERT_SCOPE)
    in_scope = alert_scope(rows, scope)
    failing: dict[tuple[str, str, str], dict[str, Any]] = {}
    for r, t in zip(rows, t_books):
        if t["durum"] == "sapma" and r.stok_kodu in in_scope:
            failing[("satis", "kitap", r.stok_kodu)] = {
                "label": f"{r.ad or r.stok_kodu}", "ratio": t["oranCiro"] if r.ciro > 0 else t["oranAdet"],
                "expected": t["beklenenCiro"], "actual": t["gercekCiro"], "gap": round(t["beklenenCiro"] - t["gercekCiro"], 2),
                "detail": {"segment": r.segment, "yayinevi": r.yayinevi, "beklenenAdet": t["beklenenAdet"], "gercekAdet": t["gercekAdet"]}}
    for g in tr["yayinevleri"]:
        if g["durum"] == "sapma":
            failing[("satis", "yayinevi", g["ad"])] = {"label": g["ad"], "ratio": g["oran"], "expected": g["beklenenCiro"],
                                                       "actual": g["gercekCiro"], "gap": round(g["beklenenCiro"] - g["gercekCiro"], 2),
                                                       "detail": {"kitap": g["kitap"]}}
    s = tr["sirket"]
    if s["durum"] == "sapma":
        failing[("satis", "toplam", "sirket")] = {"label": "Şirket satış hedefi", "ratio": s["oran"], "expected": s["beklenenCiro"],
                                                  "actual": s["gercekCiro"], "gap": round(s["beklenenCiro"] - s["gercekCiro"], 2), "detail": {}}
    for d in departments(engine, tenant, row.id)["items"]:
        iz = d.get("izleme") or {}
        if iz.get("durum") == "asim":
            failing[("gider", "merkez", f"{d['merkezKodu']}|{d['hesap']}")] = {
                "label": f"{d['merkezAdi']} · {d['hesapAdi']}", "ratio": iz["kullanim"], "expected": iz["butceDonem"],
                "actual": iz["gercek"], "gap": round(iz["gercek"] - iz["butceDonem"], 2), "detail": {"yillik": d["yillik"]}}
    now = _now()
    opened = closed = 0
    with engine.begin() as c:
        cur = {(a.kind, a.scope, a.key): a for a in c.execute(sa.select(ALERTS).where(
            ALERTS.c.tenant_id == tenant, ALERTS.c.year == year, ALERTS.c.plan_id == row.id, ALERTS.c.status == "acik")).all()}
        for k, v in failing.items():
            vals = {"label": v["label"][:400], "ratio": v["ratio"], "expected": v["expected"], "actual": v["actual"],
                    "gap": v["gap"], "detail_json": _dump(v["detail"]), "last_at": now}
            if k in cur:
                c.execute(ALERTS.update().where(ALERTS.c.id == cur[k].id).values(**vals))
            else:
                c.execute(ALERTS.insert().values(id=uuid.uuid4().hex, tenant_id=tenant, year=year, plan_id=row.id, kind=k[0],
                                                 scope=k[1], key=k[2][:120], modules=SALES_ALERT_MODULES if k[0] == "satis" else None,
                                                 status="acik", first_at=now, **vals))
                opened += 1
        for k, a in cur.items():
            if k not in failing:
                c.execute(ALERTS.update().where(ALERTS.c.id == a.id).values(status="kapandi", closed_at=now, last_at=now))
                closed += 1
        # arşive geçen planların açık uyarıları kapanır
        c.execute(ALERTS.update().where(ALERTS.c.tenant_id == tenant, ALERTS.c.year == year, ALERTS.c.plan_id != row.id,
                                        ALERTS.c.status == "acik").values(status="kapandi", closed_at=now))
    return {"year": year, "planId": row.id, "opened": opened, "closed": closed, "open": len(failing)}


def _alert_dict(a: Any) -> dict[str, Any]:
    return {"id": a.id, "year": a.year, "planId": a.plan_id, "kind": a.kind, "scope": a.scope, "key": a.key, "label": a.label,
            "ratio": a.ratio, "expected": a.expected, "actual": a.actual, "gap": a.gap, "detail": _j(a.detail_json, {}),
            "modules": [m for m in (a.modules or "").split(",") if m], "status": a.status,
            "firstAt": _iso(a.first_at), "lastAt": _iso(a.last_at), "closedAt": _iso(a.closed_at), "notifiedAt": _iso(a.notified_at)}


def deviations(engine: sa.engine.Engine, tenant: str, year: int, *, status: str = "acik", kind: str = "",
               scope: str = "", module: str = "", page: int = 0) -> dict[str, Any]:
    with engine.connect() as c:
        cond = [ALERTS.c.tenant_id == tenant, ALERTS.c.year == int(year)]
        if status in ("acik", "kapandi", "bilgi"):
            cond.append(ALERTS.c.status == status)
        if kind in ("satis", "gider", "revizyon"):
            cond.append(ALERTS.c.kind == kind)
        if scope:
            cond.append(ALERTS.c.scope == scope)
        if module:
            cond.append(ALERTS.c.modules.like(f"%{module[:8]}%"))
        rows = c.execute(sa.select(ALERTS).where(*cond).order_by(sa.func.coalesce(ALERTS.c.gap, -1e18).desc(),
                                                                   ALERTS.c.last_at.desc())).all()
    total = len(rows)
    page = max(0, int(page))
    return {"items": [_alert_dict(a) for a in rows[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]], "total": total, "page": page,
            "pageSize": PAGE_SIZE}


def notify(engine: sa.engine.Engine, tenant: str, year: int, recipients: list[str], link: str,
           send: Callable[[str, str, list[str]], str]) -> dict[str, Any]:
    """Bildirilmemiş yeni uyarılar için tek özet e-posta (liste bağlantıda; sayı ve toplam açık e-postada)."""
    with engine.connect() as c:
        rows = c.execute(sa.select(ALERTS).where(ALERTS.c.tenant_id == tenant, ALERTS.c.year == year,
                                                 ALERTS.c.status == "acik", ALERTS.c.notified_at.is_(None))).all()
    if not rows:
        return {"sent": 0, "status": "yok"}
    if not recipients:
        return {"sent": 0, "status": "no_recipient", "pending": len(rows)}
    sales = [r for r in rows if r.kind == "satis"]
    costs = [r for r in rows if r.kind == "gider"]
    lines = [f"{year} bütçesinde yeni sapma uyarıları:", ""]
    if sales:
        gap = sum(r.gap or 0 for r in sales if r.scope == "kitap")
        lines.append(f"- Satış hedefinin %{int(DEFAULT_THRESHOLD * 100)} altına düşen: {sum(1 for r in sales if r.scope == 'kitap')} kitap, "
                     f"{sum(1 for r in sales if r.scope == 'yayinevi')} yayınevi; kitaplarda beklenenden eksik ciro {_tr(gap)} ₺.")
        if any(r.scope == "toplam" for r in sales):
            lines.append("- Şirket toplam satışı hedefin eşiğinin altında.")
    if costs:
        lines.append(f"- Bütçesini aşan departman kalemi: {len(costs)}; aşım {_tr(sum(r.gap or 0 for r in costs))} ₺.")
    lines += ["", f"Tam liste ve ayrıntı: {link}" if link else "Tam liste Bütçe ekranının İzleme sekmesinde."]
    status = send(f"ZEKİ bütçe uyarısı: {year}", "\n".join(lines), recipients)
    if status == "sent":
        with engine.begin() as c:
            c.execute(ALERTS.update().where(ALERTS.c.id.in_([r.id for r in rows])).values(notified_at=_now()))
    return {"sent": len(rows) if status == "sent" else 0, "status": status}


def _tr(v: float) -> str:
    s = f"{v:,.0f}".replace(",", ".")
    return s


# ------------------------------------------------------------------ gerçekleşmeyi yenileme


class Refresher:
    """Logo/CRM okumasını arka planda yapar; aynı anda tek okuma."""

    def __init__(self, engine_fn: Callable[[], sa.engine.Engine], logo_file: Callable[[], str], crm_file: Callable[[], str]):
        self._engine = engine_fn
        self._logo = logo_file
        self._crm = crm_file
        self._thread: Optional[threading.Thread] = None
        self._guard = threading.Lock()
        self.state: dict[str, Any] = {"running": False, "step": None, "startedAt": None, "error": None}

    def status(self) -> dict[str, Any]:
        engine = self._engine()
        ensure(engine)
        years = {}
        with engine.connect() as c:
            for r in c.execute(sa.select(META).where(META.c.key.like("sales:%"))).all():
                years[r.key.split(":")[1]] = {**_j(r.value_json, {}), "at": _iso(r.updated_at)}
            for r in c.execute(sa.select(META).where(META.c.key.like("expense:%"))).all():
                years.setdefault(r.key.split(":")[1], {})["gider"] = {**_j(r.value_json, {}), "at": _iso(r.updated_at)}
        de = meta_get(engine, "data_end")
        bk = meta_get(engine, "books")
        return {**self.state, "dataEnd": de.get("date"), "dataEndAt": de.get("_at"), "books": bk,
                "years": dict(sorted(years.items()))}

    def needed_years(self, engine: sa.engine.Engine, extra: Iterable[int] = ()) -> list[int]:
        end = data_end(engine)
        today = _today()
        top = end.year if end else today.year
        years = {top - 1, top}
        with engine.connect() as c:
            for (y,) in c.execute(sa.select(PLANS.c.year).distinct()).all():
                if y <= top:
                    years |= {y - 1, y}
        years |= set(extra)
        return sorted(y for y in years if 2015 <= y <= top)

    def due(self, engine: sa.engine.Engine, now: Optional[float] = None) -> list[int]:
        """Tazelenmesi gereken yıllar: verinin son yılı `BUDGET_ACTUALS_TTL` (1 sa), geçmiş yıllar 7 gün."""
        now = now or time.time()
        end = data_end(engine)
        top = end.year if end else _today().year
        ttl_now = int(os.environ.get("BUDGET_ACTUALS_TTL", "3600"))
        ttl_past = int(os.environ.get("BUDGET_ACTUALS_PAST_TTL", str(7 * 86400)))
        out = []
        for y in self.needed_years(engine):
            m = meta_get(engine, f"sales:{y}")
            at = m.get("_at")
            age = now - datetime.fromisoformat(at).timestamp() if at else None
            if age is None or age > (ttl_now if y >= top else ttl_past):
                out.append(y)
        return out

    def start(self, years: Optional[list[int]] = None, force_books: bool = True) -> bool:
        with self._guard:
            if self._thread and self._thread.is_alive():
                return False
            self.state.update(running=True, step="Başlıyor", startedAt=time.time(), error=None)
            self._thread = threading.Thread(target=self.run, args=(years, force_books), daemon=True, name="budget-refresh")
            self._thread.start()
            return True

    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def run(self, years: Optional[list[int]] = None, force_books: bool = False) -> dict[str, Any]:
        """`years` None = gereken bütün yıllar, [] = hiçbiri (yalnız bayat kitap kartı). Kitap kartı günde bir."""
        engine = self._engine()
        ensure(engine)
        done: dict[str, Any] = {}
        try:
            self.state.update(running=True, step="Logo dönemleri")
            logo = src.runner(self._logo())
            firms = src.firms_by_year(logo)
            end = src.read_data_end(logo, firms)
            if end:
                meta_set(engine, "data_end", {"date": end.isoformat()})
            want = self.needed_years(engine) if years is None else years
            for y in want:
                if y not in firms:
                    continue
                self.state["step"] = f"{y} satışları"
                rows, ms = src.timed(lambda y=y: src.read_sales(logo, firms, y))
                with engine.begin() as c:
                    c.execute(SALES.delete().where(SALES.c.year == y))
                    for i in range(0, len(rows), 5000):
                        c.execute(SALES.insert(), rows[i:i + 5000])
                meta_set(engine, f"sales:{y}", {"rows": len(rows), "dbMs": ms, "firm": firms[y],
                                                "ciro": round(sum(r["ciro"] for r in rows), 2)})
                self.state["step"] = f"{y} giderleri"
                exp, ms2 = src.timed(lambda y=y: src.read_expenses(logo, firms, y))
                with engine.begin() as c:
                    c.execute(EXPENSES.delete().where(EXPENSES.c.year == y))
                    for i in range(0, len(exp), 5000):
                        c.execute(EXPENSES.insert(), exp[i:i + 5000])
                meta_set(engine, f"expense:{y}", {"rows": len(exp), "dbMs": ms2, "tutar": round(sum(r["tutar"] for r in exp), 2)})
                done[str(y)] = {"satis": len(rows), "gider": len(exp)}
            self.state["step"] = "Kitap kartları"
            books_m = meta_get(engine, "books")
            ttl = int(os.environ.get("BUDGET_BOOKS_TTL", "86400"))
            stale = not books_m.get("_at") or time.time() - datetime.fromisoformat(books_m["_at"]).timestamp() > ttl
            if stale or force_books:
                names = src.read_item_names(logo, firms)
                crm_rows: dict[str, dict[str, Any]] = {}
                crm_error = None
                try:
                    crm_rows = src.read_books(src.runner(self._crm()))
                except src.SourceError as e:
                    crm_error = str(e)
                if crm_rows or not books_m:
                    with engine.connect() as c:
                        codes = {r[0] for r in c.execute(sa.select(SALES.c.stok_kodu).distinct()).all()}
                    rows = []
                    for code in sorted(codes | set(crm_rows)):
                        b = crm_rows.get(code) or {}
                        rows.append({"stok_kodu": code[:60], "ad": ((b.get("ad") or names.get(code) or "")[:400]) or None,
                                     "yazar": (b.get("yazar") or "")[:300] or None, "yayinevi": (b.get("yayinevi") or "")[:200] or None,
                                     "kitaplik": (b.get("kitaplik") or "")[:200] or None, "ilk_yayin": b.get("ilk_yayin"),
                                     "liste_fiyati": b.get("liste_fiyati"), "statu": (b.get("statu") or "")[:200] or None,
                                     "in_logo": code in names or code in codes})
                    with engine.begin() as c:
                        c.execute(BOOKINFO.delete())
                        for i in range(0, len(rows), 5000):
                            c.execute(BOOKINFO.insert(), rows[i:i + 5000])
                    meta_set(engine, "books", {"rows": len(rows), "crm": len(crm_rows), "crmError": crm_error})
                done["kitap"] = len(crm_rows)
            self.state.update(running=False, step=None, error=None, finishedAt=time.time())
            return {"ok": True, "done": done, "dataEnd": end.isoformat() if end else None}
        except Exception as e:  # noqa: BLE001 — eski gerçekleşme kalır, hata ekranda
            log.warning("budget refresh failed: %s", e)
            msg = str(e) if isinstance(e, (src.SourceError, BudgetError)) else f"Okuma hata verdi: {str(e)[:200]}"
            self.state.update(running=False, step=None, error=msg, finishedAt=time.time())
            return {"ok": False, "error": msg, "done": done}


def books_csv(engine: sa.engine.Engine, tenant: str, plan_id: str) -> str:
    """Planın bütün kitap hedefleri (izleme varsa gerçekleşmeyle) — Excel'in açtığı biçim (; ve ondalık virgül)."""
    data = books(engine, tenant, plan_id, page=0)
    total = data["total"]
    items = []
    page = 0
    while len(items) < total:
        items += books(engine, tenant, plan_id, page=page)["items"]
        page += 1
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    head = ["Stok kodu", "Kitap", "Segment", "Yayınevi", "Kitaplık", "İlk yayın", "Hedef adet", "Hedef ciro", "Hedef marj",
            "Öneri adet", "Öneri ciro", "Elle düzeltildi"]
    track = bool(items and items[0].get("izleme"))
    if track:
        head += ["Beklenen ciro (bugüne)", "Gerçekleşen ciro", "Gerçekleşen adet", "Oran", "Durum"]
    w.writerow(head)

    def n(v: Any, d: int = 2) -> str:
        return "" if v is None else f"{float(v):.{d}f}".replace(".", ",")

    for i in items:
        row = [i["stokKodu"], i["ad"] or "", i["segmentLabel"], i["yayinevi"] or "", i["kitaplik"] or "", i["ilkYayin"] or "",
               n(i["adet"], 0), n(i["ciro"]), n(i["marj"], 4), n(i["oneri"].get("adet"), 0), n(i["oneri"].get("ciro")),
               "evet" if i["elle"] else ""]
        if track:
            t = i["izleme"]
            row += [n(t["beklenenCiro"]), n(t["gercekCiro"]), n(t["gercekAdet"], 0), n(t["oranCiro"], 4), t["durum"]]
        w.writerow(row)
    return "﻿" + buf.getvalue()
