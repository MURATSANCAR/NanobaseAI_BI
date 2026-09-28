"""Grup 4 (pazarlama) sorgu bilgisi: modüllerin ortak kullandığı kaynak kayıtları (sözleşme `provenance.py`).

Pazarlama ekranlarının çoğu rakamını başka modüllerin önbelleğinden okur: satış ve gider bütçe modülünün Logo
gerçekleşme tablolarından (`semantic_budget_sales_actuals`, `semantic_budget_expense_actuals`), hedef yürürlükteki
bütçe planından, emsal satışı ilk baskı tahmininin veri kümesinden. Burada o kaynaklar tek yerde kaydedilir; gösterilen
SQL uçta çalışan ifadenin kendisidir, tabloyu dolduran asıl Logo/CRM sorgusu `origin` olarak eklenir.

Kurallar provenance.py ile aynı: şablon SQL yok, sır yok, kişisel veride sonuç satırı yok (yalnız satır sayısı).
"""
from __future__ import annotations

import os
import re
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

from semantic_bridge import provenance as P

CRM_FILE_DEFAULT = "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"


def crm_db() -> Optional[str]:
    """CRM bağlantı dosyasından YALNIZ veritabanı adı (SSMS'te kopyala-çalıştır için «USE [..]» satırı)."""
    return P.connection_database(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", CRM_FILE_DEFAULT))


def logo_db(rt: Optional[Callable[[], Any]] = None) -> Optional[str]:
    """Logo bağlantı dosyasından yalnız veritabanı adı (köprünün ayarı; yoksa ortam değişkeni)."""
    path = None
    if rt is not None:
        try:
            path = rt().settings.connection_file
        except Exception:  # noqa: BLE001 — ad okunamazsa «USE» satırı yazılmaz, SQL yine gösterilir
            path = None
    return P.connection_database(path or os.environ.get("SEMANTIC_CONNECTION_FILE"))


def year_of(v: Any) -> Optional[int]:
    try:
        return int(str(v)[:4])
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ bütçe modülü önbelleği (Logo satış ve gider)


def logo_satis(k: P.Kaynaklar, engine: Any, years: Iterable[int], logo_db_name: Optional[str]) -> list[str]:
    """`semantic_budget_sales_actuals`'ı dolduran Logo satış sorguları (yıl başına; hangi firma kopyasıyla okunduysa)."""
    from semantic_bridge import budget_kaynak as BK

    ys = sorted({int(y) for y in years if y})
    if not ys:
        return []
    try:
        sales, _exp = BK.logo_sources(k, engine, ys, logo_db_name)
    except sa.exc.SQLAlchemyError:
        return []
    return sales


def logo_gider(k: P.Kaynaklar, engine: Any, years: Iterable[int], logo_db_name: Optional[str]) -> list[str]:
    from semantic_bridge import budget_kaynak as BK

    ys = sorted({int(y) for y in years if y})
    if not ys:
        return []
    try:
        _sales, exp = BK.logo_sources(k, engine, ys, logo_db_name)
    except sa.exc.SQLAlchemyError:
        return []
    return exp


def butce_satis(k: P.Kaynaklar, engine: Any, id: str, title: str, stmt: Any, years: Iterable[int],
                logo_db_name: Optional[str], *, description: str = "") -> str:
    """Bütçe modülünün Logo satış önbelleği okuması (çalışan ifade) + onu dolduran Logo sorguları."""
    origin = logo_satis(k, engine, years, logo_db_name)
    return k.portal(id, title, stmt, engine, origin=origin, description=description or (
        "Bütçe modülünün Logo faturalı satış önbelleği (semantic_budget_sales_actuals): kitap × ay net adet ve net ciro "
        "(satır net tutarı, iade düşülmüş)."))


def veri_sonu(k: P.Kaynaklar, engine: Any, logo_db_name: Optional[str]) -> Optional[str]:
    """Logo veri sonu (son faturalı satış günü) sorgusu; bütçe modülü okuduysa."""
    from semantic_bridge import budget as B
    from semantic_bridge import budget_sources as bsrc

    try:
        end = B.data_end(engine)
        if not end:
            return None
        m = B.meta_get(engine, f"sales:{end.year}")
        de = B.meta_get(engine, "data_end")
    except sa.exc.SQLAlchemyError:
        return None
    if not m.get("firm"):
        return None
    return k.sorgu("logo.verisonu", "Logo veri sonu", "logo", bsrc.data_end_sql(m["firm"]), database=logo_db_name,
                   ran_at=de.get("_at"), description="Son faturalı satış satırının tarihi.")


# ------------------------------------------------------------------ bütçe planı hedefleri (M46)


def hedef_plan_stmt(tenant: str, year: int):
    from semantic_bridge import budget as B

    return B.approved_stmt(tenant, int(year))


def hedef_kitap_stmt(plan_id: str, codes: Iterable[str]):
    """`budget.approved_targets`'ın kitap hedefi okuması (aynı ifade: plan + stok kodları, ciroya göre sıralı)."""
    from semantic_bridge import budget as B

    cond = [B.BOOKS.c.plan_id == plan_id]
    want = [str(x).strip() for x in codes if str(x or "").strip()]
    if want:
        cond.append(B.BOOKS.c.stok_kodu.in_(want))
    return sa.select(B.BOOKS).where(*cond).order_by(B.BOOKS.c.ciro.desc(), B.BOOKS.c.stok_kodu)


def hedefler(k: P.Kaynaklar, engine: Any, tenant: str, codes_by_year: dict[int, list[str]], *, prefix: str = "butce") -> list[str]:
    """Yıl başına yürürlükteki bütçe planı ve kitap hedefleri okuması. Plan yoksa yalnız plan sorgusu (boş döner)."""
    from semantic_bridge import budget as B

    ids: list[str] = []
    for y, codes in sorted(codes_by_year.items()):
        y = int(y)
        ids.append(k.portal(f"{prefix}.plan.{y}", f"Yürürlükteki bütçe planı · {y}", hedef_plan_stmt(tenant, y), engine,
                            description="Bütçe ve hedefler modülünde o yıl için onaylı plan (semantic_budget_plans)."))
        try:
            with engine.connect() as c:
                row = c.execute(hedef_plan_stmt(tenant, y)).first()
        except sa.exc.SQLAlchemyError:
            row = None
        if row is not None:
            ids.append(k.portal(f"{prefix}.hedef.{y}", f"Kitap satış hedefleri · {y}", hedef_kitap_stmt(row.id, codes), engine,
                                description="Onaylı bütçe planındaki kitap hedefleri: hedef net adet, hedef net ciro, marj "
                                            "(semantic_budget_books). Aylık hedef = yıllık hedef × taban döneminin ay payı."))
    return ids


F_HEDEF = ("Hedef = yayın yılının yürürlükteki (onaylı) bütçe planındaki kitap hedefi: net adet ve net ciro. Plan ya da "
           "kitap planda yoksa «onaylı hedef yok».")


# ------------------------------------------------------------------ ilk baskı tahmini veri kümesi (M10)


#: Görüntüde kalmış şablon işaretleri (ör. «{satis:yil}»): ortak denetimin `{ad}` kalıbı iki noktalıyı yakalamaz.
_TEMPLATE = re.compile(r"\{[A-Za-z_][\w:]*\}")


def ilk_baski(k: P.Kaynaklar, state: Any, *, prefix: str = "ilkbaski") -> list[str]:
    """İlk baskı tahmininin veri kümesini dolduran sorgular (CRM kitaplar, CRM emsal bağı, Logo aylık kanal satışı).
    Rapor görüntüsünde kaydedilen çalışmış metin kullanılır; görüntü yoksa kayıt açılmaz."""
    store = getattr(getattr(state, "management_reports", None), "first_print", None)
    if store is None:
        return []
    try:
        snap, _eng = store.load()
    except Exception:  # noqa: BLE001
        return []
    stats = (snap or {}).get("sourceStats") or {}
    names = {"crm_kitaplar": ("crm", "CRM kitap kartları"), "crm_emsal": ("crm", "CRM emsal bağları"),
             "logo_aylik_kanal": ("logo", "Logo aylık kanal satışı (son yıl)")}
    ids = []
    for sid, (conn, title) in names.items():
        s = stats.get(sid) or {}
        sql = s.get("sql")
        if not sql or P.placeholders_left(sql) or _TEMPLATE.search(sql):
            continue
        desc = ("İlk baskı tahmini veri kümesini dolduran sorgu. Aylık satış sorgusu yıl başına ayrı koşar (yıllık satış "
                "görünümü); burada son koşan yılın metni var, diğer yıllar aynı metnin yıl değiştirilmiş hâlidir."
                if sid == "logo_aylik_kanal" else "İlk baskı tahmini veri kümesini dolduran sorgu.")
        try:
            ids.append(k.sorgu(f"{prefix}.{sid}", title, conn, sql, rows=s.get("rows"), ms=s.get("dbMs"),
                               ran_at=(snap or {}).get("asOf"),
                               database=crm_db() if conn == "crm" else logo_db(), description=desc))
        except P.ProvenanceError:
            continue
    return ids


def not_found_ok(fn: Callable[[], Any], default: Any = None) -> Any:
    try:
        return fn()
    except sa.exc.SQLAlchemyError:
        return default


# ------------------------------------------------------------------ yenileme işlerinin kaydettiği çalışmış SQL'ler


def recording(run: Callable[[str], Any], conn: str, out: list[dict[str, Any]]) -> Callable[[str], Any]:
    """Koşucuyu sarar: her çalışan SQL'in metni, bağlantısı, satır sayısı, süresi ve anı `out`a yazılır. Sonuç satırı
    yazılmaz (kişisel veri kayda girmez). Aynı metin iki kez koşarsa bir kez kaydedilir."""
    import time as _time
    from datetime import datetime as _dt

    def run_(sql: str) -> Any:
        t0 = _time.monotonic()
        rows = run(sql)
        if not any(x["sql"] == sql for x in out):
            if isinstance(rows, list):
                n: Optional[int] = len(rows)
            elif isinstance(rows, dict):
                n = len(rows.get("records") or rows.get("rows") or [])
            else:
                n = None
            out.append({"conn": conn, "sql": sql, "rows": n, "dbMs": int((_time.monotonic() - t0) * 1000),
                        "at": _dt.now().isoformat(timespec="seconds")})
        return rows
    return run_


def _title_of(sql: str, conn: str, i: int) -> str:
    import re

    for line in sql.splitlines():
        s = line.strip()
        if s.startswith("--"):
            t = s.lstrip("-").strip()
            if t:
                return t[:120]
    m = re.search(r"(?is)\bFROM\s+([\w\.\[\]]+)", sql)
    what = m.group(1).split(".")[-1].strip("[]") if m else str(i)
    return f"{'CRM' if conn == 'crm' else 'Logo'} okuması · {what}"


def kayitli(k: P.Kaynaklar, runs: Iterable[dict[str, Any]], prefix: str, logo_db_name: Optional[str], *,
            description: str = "", match: Optional[Callable[[str], bool]] = None) -> list[str]:
    """Yenileme işinin kaydettiği çalışmış CRM/Logo SQL'lerini kaynak olarak ekler (yer tutuculu olan atlanır).
    `match`: yalnız metni bu koşula uyan sorgular (ör. belirli bir tabloyu okuyanlar)."""
    ids: list[str] = []
    for i, r in enumerate(runs or [], 1):
        conn = r.get("conn")
        sql = r.get("sql")
        if conn not in ("crm", "logo") or not sql or (match is not None and not match(sql)):
            continue
        try:
            ids.append(k.sorgu(f"{prefix}.{i}", _title_of(sql, conn, i), conn, sql, rows=r.get("rows"), ms=r.get("dbMs"),
                               ran_at=r.get("at"), database=crm_db() if conn == "crm" else logo_db_name,
                               description=description))
        except P.ProvenanceError:
            continue
    return ids
