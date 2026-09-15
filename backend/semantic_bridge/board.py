"""Kişisel pano: kartlar ve son sonuçları sunucuda durur.

Pano tarayıcıda değil burada saklanır; kişi başka bilgisayardan girince aynı panoyu görür. Kart bir
SQL + grafik tipi + yerleşimdir; son sonucu da kartla birlikte durur ki pano açılınca sorgu koşmasın
(kullanıcı kuralı). Tazeleme elle ("Yenile"), istemcinin bayat sayması (5 dk) ya da zamanlayıcıyla
(`/api/v1/board/run-due`: saatlik / her gün HH:MM) olur.

Kullanıcı kimliği giriş servisinden (:8796 `/session`) çerezle çözülür; köprü kendi oturumu tutmaz.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

import sqlalchemy as sa

log = logging.getLogger(__name__)

_md = sa.MetaData()

CARDS = sa.Table(
    "semantic_board_cards", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("datasource_id", sa.String(80), nullable=False),
    sa.Column("username", sa.String(120), nullable=False, index=True),
    sa.Column("position", sa.Integer, nullable=False, default=0),
    sa.Column("title", sa.String(300), nullable=False),
    sa.Column("note", sa.Text),
    sa.Column("question", sa.Text),
    sa.Column("sql", sa.Text, nullable=False),
    sa.Column("chart", sa.String(16), nullable=False),
    sa.Column("depth", sa.Boolean, nullable=False, default=False),
    sa.Column("x", sa.Integer, nullable=False, default=0),
    sa.Column("y", sa.Integer, nullable=False, default=0),
    sa.Column("w", sa.Integer, nullable=False, default=460),
    sa.Column("h", sa.Integer, nullable=False, default=300),
    sa.Column("z", sa.Integer, nullable=False, default=20),
    sa.Column("sql_open", sa.Boolean, nullable=False, default=False),
    sa.Column("refresh", sa.String(8), nullable=False, default="manual"),
    sa.Column("refresh_at", sa.String(5)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("result_json", sa.Text),
    sa.Column("result_at", sa.DateTime(timezone=True)),
    sa.Column("last_auto_at", sa.DateTime(timezone=True)),
    sa.Column("last_error", sa.Text),
)

CHARTS = {"column", "bar", "line", "area", "pie", "donut", "scatter", "treemap", "kpi", "table"}
REFRESH = {"manual", "hourly", "daily"}
_ID = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
#: Sonuç kartla birlikte saklanır; motorun satır tavanı (500) zaten kesiyor, bu yalnız emniyet.
MAX_RESULT_CHARS = 2_000_000

_ready: set[int] = set()
_ready_lock = threading.Lock()
_due_lock = threading.Lock()
_LOCAL = timezone(timedelta(hours=float(os.environ.get("ALERT_TZ_OFFSET_HOURS", "3"))))
LOGIN_URL = os.environ.get("TIMAS_LOGIN_URL", "http://127.0.0.1:8796")


class BoardError(ValueError):
    """Kullanıcıya olduğu gibi gösterilecek düz Türkçe hata."""


class NoUser(Exception):
    """Çerez yok ya da oturum düşmüş."""


def ensure(engine: sa.engine.Engine) -> None:
    with _ready_lock:
        if id(engine) in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _ready.add(id(engine))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(v: Optional[datetime]) -> Optional[datetime]:
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _ms(v: Optional[datetime]) -> Optional[int]:
    v = _aware(v)
    return int(v.timestamp() * 1000) if v else None


def _iso(v: Optional[datetime]) -> Optional[str]:
    v = _aware(v)
    return v.isoformat() if v else None


# ------------------------------------------------------------------ kimlik


def user_of(cookie_header: str, *, fetch: Optional[Callable[[str], Optional[str]]] = None) -> str:
    """Giriş servisine çerezi iletir, kullanıcı adını alır. Oturum yoksa NoUser."""
    cookie = (cookie_header or "").strip()
    if not cookie:
        raise NoUser()
    user = (fetch or _fetch_user)(cookie)
    if not user:
        raise NoUser()
    return user[:120]


def session_of(cookie_header: str, *, fetch: Optional[Callable[[str], Optional[dict]]] = None) -> tuple[str, str]:
    """Oturumdaki hesap adı ve AD'deki ad soyad. Başkalarına kimin yaptığını göstermesi gereken yerler içindir."""
    cookie = (cookie_header or "").strip()
    if not cookie:
        raise NoUser()
    data = (fetch or _fetch_session)(cookie) or {}
    user = str(data.get("username") or "").strip()
    if not user:
        raise NoUser()
    display = str(data.get("displayName") or "").strip() or user
    return user[:120], display[:200]


def _fetch_session(cookie: str) -> Optional[dict]:
    req = urllib.request.Request(f"{LOGIN_URL}/session", headers={"Cookie": cookie})
    try:
        with urllib.request.urlopen(req, timeout=5) as res:  # noqa: S310 - loopback servis
            data = json.loads(res.read().decode("utf-8") or "{}")
    except Exception as e:  # noqa: BLE001
        log.warning("board: giriş servisi yanıt vermedi: %s", e)
        return None
    return data if isinstance(data, dict) else None


def _fetch_user(cookie: str) -> Optional[str]:
    data = _fetch_session(cookie) or {}
    u = data.get("username")
    return str(u) if u else None


# ------------------------------------------------------------------ kart


def _int(v: Any, default: int, lo: int, hi: int) -> int:
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _clean(card: dict[str, Any]) -> dict[str, Any]:
    cid = str(card.get("id") or "").strip()
    if not _ID.match(cid):
        raise BoardError("Kart kimliği geçersiz.")
    sql = str(card.get("sql") or "").strip()
    if not sql:
        raise BoardError("Kartın SQL'i boş olamaz.")
    title = " ".join(str(card.get("title") or "").split())[:300] or "Adsız kart"
    chart = str(card.get("chart") or "table")
    if chart not in CHARTS:
        chart = "table"
    refresh = str(card.get("refresh") or "manual")
    if refresh not in REFRESH:
        refresh = "manual"
    at = str(card.get("refreshAt") or "").strip()
    if refresh == "daily" and not _HHMM.match(at):
        at = "08:00"
    return {
        "id": cid,
        "title": title,
        "note": (str(card.get("note") or "").strip()[:2000] or None),
        "question": (str(card.get("question") or "").strip()[:2000] or None),
        "sql": sql[:50000],
        "chart": chart,
        "depth": bool(card.get("depth")),
        "x": _int(card.get("x"), 0, 0, 20000),
        "y": _int(card.get("y"), 0, 0, 200000),
        "w": _int(card.get("w"), 460, 200, 4000),
        "h": _int(card.get("h"), 300, 160, 4000),
        "z": _int(card.get("z"), 20, 0, 1_000_000),
        "sql_open": bool(card.get("sqlOpen")),
        "refresh": refresh,
        "refresh_at": at if refresh == "daily" else None,
    }


def to_dict(row: Any) -> dict[str, Any]:
    result = None
    if row["result_json"]:
        try:
            result = json.loads(row["result_json"])
            result["at"] = _ms(row["result_at"]) or 0
        except ValueError:
            result = None
    return {
        "id": row["id"],
        "title": row["title"],
        "note": row["note"] or "",
        "question": row["question"] or "",
        "sql": row["sql"],
        "chart": row["chart"],
        "depth": bool(row["depth"]),
        "x": row["x"], "y": row["y"], "w": row["w"], "h": row["h"], "z": row["z"],
        "sqlOpen": bool(row["sql_open"]),
        "refresh": row["refresh"],
        "refreshAt": row["refresh_at"],
        "createdAt": _iso(row["created_at"]),
        "updatedAt": _iso(row["updated_at"]),
        "lastAutoAt": _iso(row["last_auto_at"]),
        "lastError": row["last_error"],
        "result": result,
    }


def list_cards(engine: sa.engine.Engine, tenant: str, ds: str, user: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(sa.select(CARDS).where(CARDS.c.tenant_id == tenant, CARDS.c.datasource_id == ds,
                                                CARDS.c.username == user)
                         .order_by(CARDS.c.position, CARDS.c.created_at)).mappings().all()
    return [to_dict(r) for r in rows]


def save_cards(engine: sa.engine.Engine, tenant: str, ds: str, user: str, cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Kişinin panosunu bütünüyle yazar: listede olan eklenir/güncellenir, olmayan silinir.
    Sonuç ve tazeleme damgaları korunur; yalnız kart alanları değişir."""
    if not isinstance(cards, list):
        raise BoardError("Kart listesi bekleniyor.")
    if len(cards) > 200:
        raise BoardError("Bir panoda en çok 200 kart olabilir.")
    cleaned = [_clean(c) for c in cards]
    ids = [c["id"] for c in cleaned]
    if len(set(ids)) != len(ids):
        raise BoardError("Aynı kimlikli iki kart var.")
    now = _now()
    scope = (CARDS.c.tenant_id == tenant, CARDS.c.datasource_id == ds, CARDS.c.username == user)
    with engine.begin() as c:
        existing = {r["id"] for r in c.execute(sa.select(CARDS.c.id).where(*scope)).mappings().all()}
        gone = existing - set(ids)
        if gone:
            c.execute(CARDS.delete().where(*scope, CARDS.c.id.in_(list(gone))))
        for pos, card in enumerate(cleaned):
            vals = dict(card, position=pos, updated_at=now)
            if card["id"] in existing:
                # SQL değiştiyse eski sonuç bu kartı anlatmaz.
                old_sql = c.execute(sa.select(CARDS.c.sql).where(CARDS.c.id == card["id"], *scope)).scalar()
                if old_sql != card["sql"]:
                    vals.update(result_json=None, result_at=None, last_error=None)
                c.execute(CARDS.update().where(CARDS.c.id == card["id"], *scope).values(**vals))
            else:
                if c.execute(sa.select(CARDS.c.id).where(CARDS.c.id == card["id"])).first():
                    raise BoardError("Bu kart kimliği başka bir panoda kullanılıyor.")
                c.execute(CARDS.insert().values(tenant_id=tenant, datasource_id=ds, username=user,
                                                created_at=now, **vals))
    return list_cards(engine, tenant, ds, user)


Runner = Callable[[str], dict[str, Any]]


def _store_result(engine: sa.engine.Engine, card_id: str, result: dict[str, Any], *, auto: bool) -> dict[str, Any]:
    now = _now()
    slim = {
        "columns": result.get("columns") or [],
        "records": result.get("records") or [],
        "totalRows": result.get("totalRows"),
        "truncated": bool(result.get("truncated")),
    }
    raw = json.dumps(slim, ensure_ascii=False, default=str)
    if len(raw) > MAX_RESULT_CHARS:
        # Sığmayan sonuç kesilir ve kesildiği söylenir; sessiz kesme yok.
        keep = max(1, int(len(slim["records"]) * MAX_RESULT_CHARS / len(raw)))
        slim["records"] = slim["records"][:keep]
        slim["truncated"] = True
        raw = json.dumps(slim, ensure_ascii=False, default=str)
    vals: dict[str, Any] = {"result_json": raw, "result_at": now, "last_error": None}
    if auto:
        vals["last_auto_at"] = now
    with engine.begin() as c:
        c.execute(CARDS.update().where(CARDS.c.id == card_id).values(**vals))
    slim["at"] = _ms(now)
    return slim


def run_card(engine: sa.engine.Engine, tenant: str, ds: str, user: str, card_id: str, runner: Runner) -> Optional[dict[str, Any]]:
    with engine.connect() as c:
        row = c.execute(sa.select(CARDS).where(CARDS.c.id == card_id, CARDS.c.tenant_id == tenant,
                                               CARDS.c.datasource_id == ds, CARDS.c.username == user)).mappings().first()
    if not row:
        return None
    try:
        result = runner(row["sql"])
    except Exception as e:  # noqa: BLE001
        with engine.begin() as c:
            c.execute(CARDS.update().where(CARDS.c.id == card_id).values(last_error=str(e)[:2000]))
        raise
    return _store_result(engine, card_id, result, auto=False)


def _due(row: Any, now: datetime) -> bool:
    last = _aware(row["last_auto_at"])
    if row["refresh"] == "hourly":
        return last is None or now - last >= timedelta(minutes=55)
    if row["refresh"] == "daily":
        local = now.astimezone(_LOCAL)
        hh, mm = (row["refresh_at"] or "08:00").split(":")
        if (local.hour, local.minute) < (int(hh), int(mm)):
            return False
        return last is None or last.astimezone(_LOCAL).date() < local.date()
    return False


def run_due(engine: sa.engine.Engine, tenant: str, ds: str, runner: Runner, *, now: Optional[datetime] = None) -> dict[str, Any]:
    """Zamanı gelmiş kartları (bütün kullanıcılar) çalıştırır. Aynı anda tek tur."""
    now = now or _now()
    summary: dict[str, Any] = {"due": 0, "ran": 0, "errors": []}
    with _due_lock:
        with engine.connect() as c:
            rows = c.execute(sa.select(CARDS).where(CARDS.c.tenant_id == tenant, CARDS.c.datasource_id == ds,
                                                    CARDS.c.refresh != "manual")).mappings().all()
        for row in rows:
            if not _due(row, now):
                continue
            summary["due"] += 1
            try:
                _store_result(engine, row["id"], runner(row["sql"]), auto=True)
                summary["ran"] += 1
            except Exception as e:  # noqa: BLE001
                log.warning("board: kart %s tazelenemedi: %s", row["id"], e)
                with engine.begin() as c:
                    c.execute(CARDS.update().where(CARDS.c.id == row["id"]).values(last_error=str(e)[:2000], last_auto_at=now))
                summary["errors"].append({"id": row["id"], "user": row["username"], "error": str(e)[:300]})
    return summary
