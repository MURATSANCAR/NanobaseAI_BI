"""Onaylanan SEO önerisinin CRM kitap kartına yazılması (Timaş'ın 2026-09-29'da açtığı alanlar).

Yalnız ziyaretçinin sitede görmediği alanlar yazılır: Google başlığı, meta açıklama, kapak görselinin alt metni ve iki
takip alanı. Sayfada görünen alanlar (kısa tanım, SSS, kimler okumalı, ödüller, biyografi) bu modülde yok; liste dışı
alana yazma reddedilir. CRM'den T-soft'a aktarım ayrı bir uygulamanındır; bu alanların eşlemesi orada eklenmedikçe
yazılan değer sitede görünmez.

Kip (`SEO_CRM_WRITE`, Yönetim/ortam): `kapali` (varsayılan) hiçbir şey yapmaz; `deneme` yazılacak değeri ve CRM'deki
eski değeri kaydeder, CRM'e yazmaz (test sunucusu aynı canlı CRM'e bağlı); `acik` yazar. Her yazmada eski değer
saklanır ve kayıt geri alınabilir; `ModifiedOn` güncellenir ki aktarım uygulaması değişikliği görsün.

Bağlantı: `SEO_CRM_WRITE_CONNECTION_FILE` (yoksa CRM okuma bağlantısı). Okuma bağlayıcısı salt okunur açılır; yazma
için kendi bağlantısı açılır ve iş bitince kapanır.

Toplu koşu (köprü konteynerinde):  python -m semantic_bridge.seo_geo.crm_write --deneme|--yaz [--onayla] [--sinir N]
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import sqlalchemy as sa

from semantic_bridge.seo_geo import crm
from semantic_bridge.seo_geo.store import CRM_BOOKS, PRODUCTS, PROPOSALS, _md

log = logging.getLogger(__name__)

#: Yazılabilecek metin alanları ve CRM'deki uzunlukları. Bu liste ve TRACK dışındaki alana yazma kodda reddedilir.
FIELDS: dict[str, int] = {"new_seobaslik": 100, "new_seoaciklama": 300, "new_kapakalt": 150}
TRACK = ("new_seodurum", "new_seoguncelleme")
DURUM_ONAYLANDI = 2
#: Öneri alanı → CRM alanı.
FROM_PROPOSAL = {"SeoTitle": "new_seobaslik", "SeoDescription": "new_seoaciklama"}
ACTOR = "ZEKİ AI"

WRITES = sa.Table(
    "semantic_seo_crm_writes", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("product_id", sa.String(40), nullable=False, index=True),
    sa.Column("book_id", sa.String(40), nullable=False),
    sa.Column("proposal_id", sa.String(32)),
    sa.Column("mode", sa.String(12), nullable=False),          # deneme | acik
    sa.Column("status", sa.String(16), nullable=False),        # deneme | yazildi | hata | geri_alindi | degisiklik_yok
    sa.Column("fields_json", sa.Text, nullable=False),         # yazılan (ya da yazılacak) değerler
    sa.Column("before_json", sa.Text, nullable=False),         # CRM'deki eski değerler
    sa.Column("error", sa.String(1000)),
    sa.Column("by", sa.String(120)),
    sa.Column("at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("undone_by", sa.String(120)),
    sa.Column("undone_at", sa.DateTime(timezone=True)),
    sa.Column("checked_at", sa.DateTime(timezone=True)),      # gece denetimi
    sa.Column("crm_ok", sa.Boolean),                           # CRM'deki değer hâlâ yazdığımız mı
    sa.Column("on_site", sa.Boolean),                          # T-soft (site) başlık/meta yazdığımıza eşit mi
)


def now() -> datetime:
    return datetime.now(timezone.utc)


def mode() -> str:
    from semantic_bridge import admin as admin_mod

    m = (admin_mod.conf("SEO_CRM_WRITE") or "kapali").strip().lower()
    return m if m in ("kapali", "deneme", "acik") else "kapali"


# ------------------------------------------------------------------ saf kurallar
def _clean(v: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(v or ""))).strip()


def _cut(s: str, n: int) -> str:
    if len(s) <= n:
        return s
    head = s[:n]
    sp = head.rfind(" ")
    return (head[:sp] if sp > n * 0.6 else head).rstrip(" ,;:-–|")


def alt_text(name: Any, author: Any) -> str:
    """Kapak görselinin alt metni: «Kitap Adı – Yazar kitap kapağı» (en çok 150). Yazar yoksa ya da adda geçiyorsa yalnız ad."""
    n, a = _clean(name), _clean(author)
    if not n:
        return ""
    tail = " kitap kapağı"
    text = f"{n} – {a}{tail}" if a and a.lower() not in n.lower() else f"{n}{tail}"
    return text if len(text) <= FIELDS["new_kapakalt"] else _cut(n, FIELDS["new_kapakalt"] - len(tail)) + tail


def build(product: dict[str, Any], proposal_fields: dict[str, Any], stamp: datetime) -> dict[str, Any]:
    """Bir kitap için yazılacak alanlar. Boş öneri alanı yazılmaz (CRM'deki değer silinmez)."""
    out: dict[str, Any] = {}
    for src, dst in FROM_PROPOSAL.items():
        v = _clean(proposal_fields.get(src))
        if v:
            out[dst] = _cut(v, FIELDS[dst])
    alt = alt_text(product.get("ProductName") or product.get("name"), product.get("Model"))
    if alt:
        out["new_kapakalt"] = alt
    if out:
        out["new_seodurum"] = DURUM_ONAYLANDI
        out["new_seoguncelleme"] = stamp.replace(tzinfo=None, microsecond=0)
    return out


def check(fields: dict[str, Any]) -> None:
    """Liste dışı alan ya da uzun değer: yazma başlamadan durur."""
    for k, v in fields.items():
        if k in FIELDS:
            if not isinstance(v, str) or len(v) > FIELDS[k]:
                raise ValueError(f"{k} {len(str(v))} karakter, en çok {FIELDS[k]}")
        elif k not in TRACK:
            raise ValueError(f"{k} yazılabilir alanlar listesinde yok")


def same(fields: dict[str, Any], before: dict[str, Any]) -> bool:
    return all(_clean(before.get(k)) == _clean(fields.get(k)) for k in FIELDS if k in fields)


def select_sql(p: str) -> str:
    return f"SELECT {', '.join([*FIELDS, *TRACK])} FROM {p}new_kitapBase WHERE new_kitapId = ?"


def update_sql(p: str, keys: list[str]) -> str:
    bad = [k for k in keys if k not in FIELDS and k not in TRACK]
    if bad or not keys:
        raise ValueError(f"liste dışı alan: {bad}" if bad else "yazılacak alan yok")
    sets = ", ".join(f"{k} = ?" for k in keys)
    return f"UPDATE {p}new_kitapBase SET {sets}, ModifiedOn = GETUTCDATE() WHERE new_kitapId = ? AND statecode = 0"


# ------------------------------------------------------------------ CRM bağlantısı (yazma)
def _write_conn():
    import pyodbc  # yalnız sunucuda

    path = os.environ.get("SEO_CRM_WRITE_CONNECTION_FILE") or crm.CONNECTION_FILE
    with open(path, encoding="utf-8") as f:
        c = json.load(f)
    c = c.get("connection", c)
    cs = "DRIVER=%s;SERVER=%s,%s;DATABASE=%s;UID=%s;PWD=%s;TDS_Version=%s" % (
        c.get("driver", "FreeTDS"), c["host"], c.get("port", 1433), c["database"], c["user"], c["password"],
        c.get("tds_version", "7.4"))
    conn = pyodbc.connect(cs, timeout=int(c.get("login_timeout", 30)), autocommit=False)
    conn.timeout = 60
    try:
        conn.setdecoding(pyodbc.SQL_CHAR, encoding="utf-8")
        conn.setdecoding(pyodbc.SQL_WCHAR, encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    return conn


def _row(cur) -> Optional[dict[str, Any]]:
    r = cur.fetchone()
    return None if r is None else {d[0]: v for d, v in zip(cur.description, r)}


def _jsonable(d: dict[str, Any]) -> str:
    return json.dumps(d, ensure_ascii=False, default=lambda v: v.isoformat() if hasattr(v, "isoformat") else str(v))


# ------------------------------------------------------------------ toplu iş
def run(seo, *, approve_ready: bool, write: bool, limit: Optional[int] = None, user: str = ACTOR,
        log_line: Callable[[str], None] = print) -> dict[str, Any]:
    """1) `approve_ready`: bekleyen («hazir») önerileri ZEKİ AI adına onaylar (kullanıcı kararı 2026-10-03).
    2) Her ürünün son onaylı önerisinden CRM alanlarını kurar, CRM'deki eski değeri okur; `write` ve kip `acik` ise
    yazar, değilse deneme kaydı tutar."""
    from semantic_bridge import admin as admin_mod

    eng, tenant, m = seo.engine(), seo.tenant(), mode()
    WRITES.create(eng, checkfirst=True)
    if m == "kapali":
        raise RuntimeError("SEO_CRM_WRITE kapalı; önce «deneme» ya da «acik» yapılmalı.")
    if write and m != "acik":
        raise RuntimeError(f"Kip «{m}»: CRM'e yazmak için SEO_CRM_WRITE=acik olmalı.")
    p = crm._prefix(admin_mod.conf("CRM_SCHEMA"))
    stats: dict[str, int] = {"onaylanan": 0, "onay_atlanan": 0, "kitap": 0, "eslesmeyen": 0, "degisiklik_yok": 0,
                             "yazildi": 0, "deneme": 0, "hata": 0}

    if approve_ready:
        with eng.connect() as c:
            ready = c.execute(sa.select(PROPOSALS).where(PROPOSALS.c.tenant_id == tenant, PROPOSALS.c.status == "hazir")
                              .order_by(PROPOSALS.c.created_at)).mappings().all()
        for prop in ready:
            try:
                seo.approve(dict(prop), json.loads(prop["fields_json"] or "{}"), user, "Toplu onay (ZEKİ AI)", crm_write=False)
                stats["onaylanan"] += 1
            except Exception as e:  # noqa: BLE001 — değişikliksiz öneri (409) ya da eksik ürün atlanır
                stats["onay_atlanan"] += 1
                log.info("onay atlandı %s: %s", prop["id"], e)
        log_line(f"onay: {stats['onaylanan']} onaylandı, {stats['onay_atlanan']} atlandı")

    with eng.connect() as c:
        props = c.execute(sa.select(PROPOSALS).where(PROPOSALS.c.tenant_id == tenant, PROPOSALS.c.status == "onaylandi")
                          .order_by(PROPOSALS.c.decided_at.desc())).mappings().all()
        latest: dict[str, Any] = {}
        for pr in props:
            latest.setdefault(pr["product_id"], pr)
        prods = {r["id"]: r for r in c.execute(
            sa.select(PRODUCTS.c.product_id.label("id"), PRODUCTS.c.name, PRODUCTS.c.data_json)
            .where(PRODUCTS.c.tenant_id == tenant, PRODUCTS.c.product_id.in_(list(latest)) if latest else sa.false())).mappings()}
        books = {r["ean"]: r["book_id"] for r in c.execute(
            sa.select(CRM_BOOKS.c.ean, CRM_BOOKS.c.book_id).where(CRM_BOOKS.c.tenant_id == tenant)).mappings()}
    todo = list(latest.items())[: limit or None]
    log_line(f"onaylı öneri: {len(latest)} ürün, bu koşuda {len(todo)}")
    stamp = now()
    conn = _write_conn()
    try:
        for pid, prop in todo:
            prod = prods.get(pid)
            status = _process(seo, conn, p, prod, prop, books, write=write, user=user, stamp=stamp)
            stats[status] = stats.get(status, 0) + 1
            if status not in ("eslesmeyen", "bos"):
                stats["kitap"] += 1
            if status == "hata" and stats["hata"] >= 5 and stats["yazildi"] == 0 and stats["deneme"] == 0:
                log_line("ilk 5 kayıt hata verdi; koşu durdu (izin ya da bağlantı sorunu)")
                break
    finally:
        conn.close()
    log_line(json.dumps(stats, ensure_ascii=False))
    return stats


def _process(seo, conn, p: str, prod: Optional[dict[str, Any]], prop: dict[str, Any], books: dict[str, str], *,
             write: bool, user: str, stamp: datetime) -> str:
    """Tek ürün: alanları kur, CRM'deki eski değeri oku, yaz ya da dene, kaydet. Dönen: durum."""
    data = json.loads(prod["data_json"]) if prod else {}
    book = books.get(crm.ean_key(data.get("Barcode")))
    if not book:
        return "eslesmeyen"
    fields = build(data, json.loads(prop["fields_json"] or "{}"), stamp)
    if not fields:
        return "bos"
    cur = conn.cursor()
    wid, err, before = uuid.uuid4().hex, None, {}
    try:
        check(fields)
        cur.execute(select_sql(p), book)
        got = _row(cur)
        if got is None:
            raise RuntimeError("CRM'de kart bulunamadı")
        before = got
        if same(fields, before):
            status = "degisiklik_yok"
        elif write:
            keys = list(fields)
            cur.execute(update_sql(p, keys), *[fields[k] for k in keys], book)
            if cur.rowcount != 1:
                raise RuntimeError(f"güncellenen satır {cur.rowcount}")
            conn.commit()
            status = "yazildi"
        else:
            status = "deneme"
    except Exception as e:  # noqa: BLE001
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        status, err = "hata", str(e)[:1000]
    with seo.engine().begin() as c:
        c.execute(WRITES.insert().values(
            id=wid, tenant_id=seo.tenant(), product_id=prop["product_id"], book_id=book, proposal_id=prop["id"],
            mode="acik" if write else "deneme", status=status, fields_json=_jsonable(fields),
            before_json=_jsonable(before), error=err, by=user, at=now()))
    if status == "yazildi":
        seo.audit(user, "crm_write", prop["product_id"], prod["name"] if prod else prop["product_id"],
                  {"crm": book, "alanlar": list(fields), "kayit": wid})
    return status


def on_approve(seo, proposal_id: str, user: str) -> Optional[str]:
    """Öneri onaylanınca çağrılır: kip «acik» ise o kitabın görünmez SEO alanlarını CRM'e yazar, «deneme» ise yalnız
    kaydeder. Kip kapalıysa None. Hata onayı geri almaz; durum kayda ve dönüşe yazılır."""
    from semantic_bridge import admin as admin_mod

    m = mode()
    if m == "kapali":
        return None
    eng, tenant = seo.engine(), seo.tenant()
    WRITES.create(eng, checkfirst=True)
    with eng.connect() as c:
        prop = c.execute(sa.select(PROPOSALS).where(PROPOSALS.c.id == proposal_id)).mappings().first()
        if not prop:
            return None
        prod = c.execute(sa.select(PRODUCTS.c.product_id.label("id"), PRODUCTS.c.name, PRODUCTS.c.data_json).where(
            PRODUCTS.c.tenant_id == tenant, PRODUCTS.c.product_id == prop["product_id"])).mappings().first()
        data = json.loads(prod["data_json"]) if prod else {}
        ean = crm.ean_key(data.get("Barcode"))
        books = {r["ean"]: r["book_id"] for r in c.execute(sa.select(CRM_BOOKS.c.ean, CRM_BOOKS.c.book_id).where(
            CRM_BOOKS.c.tenant_id == tenant, CRM_BOOKS.c.ean == ean)).mappings()}
    try:
        conn = _write_conn()
    except Exception as e:  # noqa: BLE001
        log.warning("CRM yazma bağlantısı açılamadı: %s", e)
        return "hata"
    try:
        return _process(seo, conn, crm._prefix(admin_mod.conf("CRM_SCHEMA")), prod, dict(prop), books,
                        write=(m == "acik"), user=user, stamp=now())
    finally:
        conn.close()


_GUID = re.compile(r"^[0-9a-fA-F-]{36}$")


def verify(seo, log_line: Callable[[str], None] = lambda s: log.info(s)) -> dict[str, int]:
    """Gece denetimi: ürün başına son «yazildi» kaydı için (1) CRM'deki değer hâlâ yazdığımız mı, (2) T-soft'taki
    (sitedeki) başlık ve meta açıklama yazdığımıza eşit mi — eşlemesi eklenince «sitede» olur. Yalnız okur."""
    from semantic_bridge import admin as admin_mod

    eng, tenant = seo.engine(), seo.tenant()
    WRITES.create(eng, checkfirst=True)
    with eng.connect() as c:
        rows = c.execute(sa.select(WRITES).where(WRITES.c.tenant_id == tenant, WRITES.c.status == "yazildi")
                         .order_by(WRITES.c.at.desc())).mappings().all()
        last: dict[str, Any] = {}
        for r in rows:
            last.setdefault(r["product_id"], r)
        prods = {r["id"]: json.loads(r["data_json"] or "{}") for r in c.execute(
            sa.select(PRODUCTS.c.product_id.label("id"), PRODUCTS.c.data_json).where(
                PRODUCTS.c.tenant_id == tenant, PRODUCTS.c.product_id.in_(list(last)) if last else sa.false())).mappings()}
    if not last:
        return {"kayit": 0}
    p = crm._prefix(admin_mod.conf("CRM_SCHEMA"))
    ids = [r["book_id"] for r in last.values() if _GUID.match(r["book_id"] or "")]
    current: dict[str, dict[str, Any]] = {}
    con = crm.connector()
    try:
        for i in range(0, len(ids), 500):
            chunk = ", ".join(f"'{x}'" for x in ids[i:i + 500])
            _, out, _ = con.execute(f"SELECT new_kitapId AS id, {', '.join(FIELDS)} FROM {p}new_kitapBase "
                                    f"WHERE new_kitapId IN ({chunk})", 100000)
            for r in out:
                current[str(r["id"]).lower()] = r
    finally:
        try:
            con.close()
        except Exception:  # noqa: BLE001
            pass
    stats = {"kayit": len(last), "crm_ayni": 0, "crm_degisti": 0, "sitede": 0}
    stamp = now()
    with eng.begin() as c:
        for pid, r in last.items():
            wrote = json.loads(r["fields_json"])
            cur = current.get(str(r["book_id"]).lower(), {})
            crm_ok = all(_clean(cur.get(k)) == _clean(wrote.get(k)) for k in FIELDS if k in wrote)
            d = prods.get(pid, {})
            on_site = bool(wrote.get("new_seobaslik")) and _clean(d.get("SeoTitle")) == _clean(wrote.get("new_seobaslik")) \
                and (not wrote.get("new_seoaciklama") or _clean(d.get("SeoDescription")) == _clean(wrote.get("new_seoaciklama")))
            stats["crm_ayni" if crm_ok else "crm_degisti"] += 1
            stats["sitede"] += int(on_site)
            c.execute(WRITES.update().where(WRITES.c.id == r["id"]).values(checked_at=stamp, crm_ok=crm_ok, on_site=on_site))
    log_line(json.dumps(stats, ensure_ascii=False))
    return stats


def undo(seo, write_id: str, user: str) -> dict[str, Any]:
    """Yazılan kaydı CRM'deki eski değerine döndürür (yalnız «yazildi» kayıtlar; kip «acik» olmalı)."""
    from semantic_bridge import admin as admin_mod

    if mode() != "acik":
        raise RuntimeError("Geri almak için SEO_CRM_WRITE=acik olmalı.")
    eng = seo.engine()
    with eng.connect() as c:
        w = c.execute(sa.select(WRITES).where(WRITES.c.id == write_id, WRITES.c.tenant_id == seo.tenant())).mappings().first()
    if not w or w["status"] != "yazildi":
        raise RuntimeError("Geri alınacak yazılmış kayıt yok.")
    before = json.loads(w["before_json"] or "{}")
    keys = [k for k in json.loads(w["fields_json"]) if k in FIELDS or k in TRACK]
    p = crm._prefix(admin_mod.conf("CRM_SCHEMA"))
    conn = _write_conn()
    try:
        cur = conn.cursor()
        cur.execute(update_sql(p, keys), *[before.get(k) for k in keys], w["book_id"])
        conn.commit()
    finally:
        conn.close()
    with eng.begin() as c:
        c.execute(WRITES.update().where(WRITES.c.id == write_id).values(status="geri_alindi", undone_by=user, undone_at=now()))
    seo.audit(user, "crm_undo", w["product_id"], w["product_id"], {"crm": w["book_id"], "kayit": write_id})
    return {"id": write_id, "status": "geri_alindi"}


def listing(seo, limit: int = 200) -> dict[str, Any]:
    eng = seo.engine()
    WRITES.create(eng, checkfirst=True)
    with eng.connect() as c:
        rows = c.execute(sa.select(WRITES, PRODUCTS.c.name).select_from(WRITES.outerjoin(
            PRODUCTS, sa.and_(PRODUCTS.c.tenant_id == WRITES.c.tenant_id, PRODUCTS.c.product_id == WRITES.c.product_id)))
            .where(WRITES.c.tenant_id == seo.tenant()).order_by(WRITES.c.at.desc()).limit(limit)).mappings().all()
        counts = {k: v for k, v in c.execute(sa.select(WRITES.c.status, sa.func.count())
                                             .where(WRITES.c.tenant_id == seo.tenant()).group_by(WRITES.c.status)).all()}
    return {"mode": mode(), "counts": counts,
            "items": [{"id": r["id"], "productId": r["product_id"], "name": r["name"], "bookId": r["book_id"],
                       "status": r["status"], "mode": r["mode"], "error": r["error"], "by": r["by"],
                       "at": r["at"].isoformat() if r["at"] else None,
                       "checkedAt": r["checked_at"].isoformat() if r["checked_at"] else None,
                       "crmOk": r["crm_ok"], "onSite": r["on_site"],
                       "fields": json.loads(r["fields_json"]), "before": json.loads(r["before_json"])} for r in rows]}


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Onaylı SEO önerilerini CRM kitap kartına yaz (ya da dene).")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--deneme", action="store_true", help="CRM'e yazma; yazılacak ve eski değeri kaydet")
    g.add_argument("--yaz", action="store_true", help="CRM'e yaz (SEO_CRM_WRITE=acik şart)")
    ap.add_argument("--onayla", action="store_true", help="bekleyen önerileri önce ZEKİ AI adına onayla")
    ap.add_argument("--sinir", type=int, help="bu koşuda en çok kaç kitap")
    a = ap.parse_args()
    from semantic_bridge.app import app as _app  # köprünün kurulu uygulaması: veritabanı, ayarlar, SEO durumu

    run(_app.state.seo_geo, approve_ready=a.onayla, write=a.yaz, limit=a.sinir)
