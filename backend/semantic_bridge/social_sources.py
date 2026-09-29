"""M22 Sosyal medya: kaynak okuması (yalnız okuma).

- **CRM** (`SEMANTIC_CRM_CONNECTION_FILE`, şema Yönetim → CRM şeması): kitap arama ve kitap kartındaki sosyal/tanıtım
  metinleri (`new_kitap` görünümü, M15 ile aynı ad/yayınevi çözümü), marka/imprint hesapları (`new_markaBase`,
  `new_instagramkullaniciadi`), özel günler ve kitap bağı (`new_ozelgunlerBase`, `new_new_kitap_new_ozelgunlerBase`;
  tarih yöntemi SEO sezon takvimiyle aynı: `seo_geo.seasons` saf işlevleri — VM'de SEO modülü olmasa da çalışır),
  yayın aralığındaki yeni kitaplar, telif sözleşmesindeki hak açıklaması (alıntı paylaşımında uyarı).
- **Logo** buradan okunmaz: backlist çok satanlar M46'nın Logo gerçekleşme önbelleğinden
  (`semantic_budget_sales_actuals`, faturalı satır, iade eksi; `semantic_budget_books` künye). Pazarlama çekirdeği
  (M15) de aynı önbelleği okur; Logo'ya ikinci yük binmez.
- **Stüdyo** (Kitap Tasarım Stüdyosu pazarlama kiti): kitaba bağlı işlerin sosyal görselleri ve alıntıları
  (`editorial_studio_marketing`, yalnız okuma).
- **Basın ve web** (`semantic_web_mentions`): yalnız `WEB_WATCH_ENABLED=1` iken; müşteri VM'inde kapalı.
- **M19 içerik arşivi**: dalda; `app.state.marketing_creative` kurulunca onaylı varlıkları okunur (bağlantı noktası).

Yazma yok: CRM'e giden tek komut `SELECT`tir. `new_kargofirmasi` gibi parola/anahtar kolonu olan tablolar okunmaz.
"""
from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import Any, Callable, Optional

import sqlalchemy as sa

from semantic_bridge import budget_sources as bsrc
from semantic_bridge.marketing.sources import BOOK_TIP, SourceError, _long, _utc_bound, code, crm_runner, guid, prefix

log = logging.getLogger("semantic.social.sources")

Runner = Callable[[str], list[dict[str, Any]]]
PAGE_SIZE = 20

#: Kitap kartında sosyal içerik için okunan metin alanları (ekranda adıyla, kaynak olarak Zeki AI'a gider).
TEXT_FIELDS = {
    "new_sosyalmedyametni": "Sosyal medya metni", "new_ozet": "Arka kapak metni", "new_kitapspotu": "Kitap spotu",
    "new_kitabinenonemlicumlesi": "Kitabın en önemli cümlesi", "new_alintlar": "Kitaptan alıntılar",
    "new_hastag": "Hashtag", "new_AnahtarKelimeler": "Anahtar kelimeler", "new_kitabinonecikanyanlari": "Bu kitap neden önemli?",
}


def _s(v: Any) -> Optional[str]:
    return bsrc._clean(v)


def _d(v: Any) -> Optional[str]:
    d = bsrc._day(v)
    return d.isoformat() if d and d.year >= 1950 else None


def _q(s: str) -> str:
    return str(s or "").replace("'", "''")


# ------------------------------------------------------------------ SQL

_BOOK = """
    k.new_kitapId AS kitap_id, k.new_stokkodu AS stok_kodu, k.new_name AS ad, k.new_yazartext AS yazar,
    k.new_yayineviid AS yayinevi_id, k.new_yayineviidName AS yayinevi, k.new_kitaplikidName AS kitaplik,
    k.new_resimurl AS kapak, CAST(DATEADD(HOUR, 3, k.new_ilkyayintarihi) AS DATE) AS ilk_yayin"""


def search_sql(schema: str, q: str, page: int) -> str:
    """Ad, yazar ya da stok kodunda geçen kitap kartları; sayfalı, toplam `COUNT(*) OVER ()` ile (tavan yok)."""
    p = prefix(schema)
    term = _q(re.sub(r"\s+", " ", q.strip())[:120])
    where = ""
    if term:
        where = (f" AND (k.new_name LIKE N'%{term}%' OR k.new_yazartext LIKE N'%{term}%' OR k.new_stokkodu LIKE N'{term}%')")
    return f"""
-- Kitap arama (CRM, yalnız okuma).
SELECT {_BOOK}, COUNT(*) OVER () AS toplam
FROM {p}new_kitap AS k
WHERE k.statecode = 0 AND k.new_Tip = {BOOK_TIP} AND k.new_stokkodu IS NOT NULL{where}
ORDER BY k.new_ilkyayintarihi DESC, k.new_name
OFFSET {max(0, int(page)) * PAGE_SIZE} ROWS FETCH NEXT {PAGE_SIZE} ROWS ONLY""".strip()


def book_sql(schema: str, stok: str) -> str:
    p = prefix(schema)
    cols = ", ".join(f"k.{c} AS {c}" for c in TEXT_FIELDS)
    return f"""
-- Sosyal içerik için kitap kartı (CRM, yalnız okuma).
SELECT {_BOOK}, k.new_hedefkitleyasbaslangic AS yas_bas, k.new_hedefkitleyasbitis AS yas_bit, k.new_youtubelink AS youtube,
       {cols}
FROM {p}new_kitap AS k
WHERE k.statecode = 0 AND k.new_stokkodu = '{code(stok)}'""".strip()


def rights_sql(schema: str, kitap_id: str) -> str:
    """Kitabın yürürlükteki telif alış sözleşmelerindeki hak açıklaması (SEO modülünün `contract_sql`'iyle aynı bağ)."""
    p = prefix(schema)
    return f"""
-- Telif alış sözleşmesi hak açıklaması (alıntı paylaşımı uyarısı; yalnız okuma).
SELECT s.new_name AS ad, LEFT(s.new_haklaraciklama, 600) AS hak
FROM {p}new_new_sozlesme_new_kitapBase AS sk
JOIN {p}new_sozlesmeBase AS s ON s.new_sozlesmeId = sk.new_sozlesmeid
WHERE sk.new_kitapid = '{guid(kitap_id)}' AND s.statecode = 0 AND s.new_SozlesmeTipi = 5
  AND NULLIF(LTRIM(RTRIM(CAST(s.new_haklaraciklama AS nvarchar(max)))), '') IS NOT NULL""".strip()


def brands_sql(schema: str) -> str:
    p = prefix(schema)
    return f"""
-- Marka (imprint) kartları ve Instagram kullanıcı adı (yalnız okuma).
SELECT m.new_markaId AS id, m.new_name AS ad, m.new_instagramkullaniciadi AS instagram, m.new_markaurl AS url
FROM {p}new_markaBase AS m
WHERE m.statecode = 0
ORDER BY m.new_name""".strip()


def days_sql(schema: str) -> str:
    p = prefix(schema)
    return (f"SELECT o.new_ozelgunlerId AS id, o.new_name AS name, o.new_ozelgunhafta1 AS w1, o.new_ozelgunlerhafta2 AS w2,"
            f" CONVERT(varchar(19), o.new_Tarih, 120) AS dt FROM {p}new_ozelgunlerBase o WHERE o.statecode = 0")


def links_sql(schema: str) -> str:
    """Özel gün ↔ kitap (barkod şartı yok: SEO'nun aksine kitap sayfası değil, kitabın kendisi bağlanır)."""
    p = prefix(schema)
    return (f"SELECT l.new_ozelgunlerid AS day_id, k.new_kitapId AS book_id, k.new_name AS name, k.new_StokKodu AS stok"
            f" FROM {p}new_new_kitap_new_ozelgunlerBase l JOIN {p}new_kitapBase k ON k.new_kitapId = l.new_kitapid"
            f" WHERE k.statecode = 0")


def new_books_sql(schema: str, frm: date, to: date) -> str:
    """İlk yayın tarihi [frm, to] içinde olan kitap kartları (M15/M46 ile aynı kitap tanımı: statecode 0, tip Kitap)."""
    p = prefix(schema)
    lo, hi = _utc_bound(frm), _utc_bound(to + timedelta(days=1))
    return f"""
-- Yayın aralığındaki yeni kitaplar (CRM, yalnız okuma). Tarih UTC saklanır; aralık İstanbul gününe çevrildi.
SELECT {_BOOK}
FROM {p}new_kitap AS k
WHERE k.statecode = 0 AND k.new_Tip = {BOOK_TIP} AND k.new_stokkodu IS NOT NULL
  AND k.new_ilkyayintarihi >= '{lo}' AND k.new_ilkyayintarihi < '{hi}'
ORDER BY k.new_ilkyayintarihi, k.new_name""".strip()


def _book(r: dict[str, Any]) -> dict[str, Any]:
    return {"kitapId": (_s(r.get("kitap_id")) or "").lower() or None, "stokKodu": _s(r.get("stok_kodu")), "ad": _s(r.get("ad")),
            "yazar": _s(r.get("yazar")), "yayineviId": (_s(r.get("yayinevi_id")) or "").lower() or None,
            "yayinevi": _s(r.get("yayinevi")), "kitaplik": _s(r.get("kitaplik")), "kapak": _s(r.get("kapak")),
            "ilkYayin": _d(r.get("ilk_yayin"))}


# ------------------------------------------------------------------ CRM okuyucu


class Crm:
    def __init__(self, schema: Callable[[], str], runner: Callable[[], Runner] = crm_runner):
        self.schema = schema
        self.runner = runner

    def _run(self, sql: str) -> list[dict[str, Any]]:
        try:
            return self.runner()(sql)
        except bsrc.SourceError as e:
            raise SourceError(str(e)) from None

    def search(self, q: str, page: int = 0) -> dict[str, Any]:
        rows = self._run(search_sql(self.schema(), q, page))
        total = int(rows[0].get("toplam") or 0) if rows else 0
        return {"items": [_book(r) for r in rows], "total": total, "page": page, "pageSize": PAGE_SIZE}

    def book(self, stok: str) -> Optional[dict[str, Any]]:
        rows = self._run(book_sql(self.schema(), stok))
        if not rows:
            return None
        r = rows[0]
        out = _book(r)
        out["metinler"] = [{"alan": f, "ad": lbl, "metin": _long(r.get(f) if r.get(f) is not None else r.get(f.lower()))}
                           for f, lbl in TEXT_FIELDS.items()]
        out["metinler"] = [m for m in out["metinler"] if m["metin"]]
        out["youtube"] = _s(r.get("youtube"))
        out["yas"] = [r.get("yas_bas"), r.get("yas_bit")]
        return out

    def rights(self, kitap_id: str) -> list[dict[str, Any]]:
        return [{"sozlesme": _s(r.get("ad")), "hak": _long(r.get("hak"))} for r in self._run(rights_sql(self.schema(), kitap_id))]

    def brands(self) -> list[dict[str, Any]]:
        out = []
        for r in self._run(brands_sql(self.schema())):
            ig = _s(r.get("instagram"))
            out.append({"id": (_s(r.get("id")) or "").lower(), "ad": _s(r.get("ad")), "url": _s(r.get("url")),
                        "instagram": ig.lstrip("@") if ig else None})
        return out

    def new_books(self, frm: date, to: date) -> list[dict[str, Any]]:
        seen: dict[str, dict[str, Any]] = {}
        for r in self._run(new_books_sql(self.schema(), frm, to)):
            b = _book(r)
            if b["stokKodu"]:
                seen.setdefault(b["stokKodu"], b)
        return list(seen.values())

    def special_days(self) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
        """Özel günler (aynı adlılar birleşik, kodda tanımlı hareketli günler eklenir) ve gün anahtarı → kitaplar."""
        from semantic_bridge.seo_geo import seasons as S

        days, books = self.special_days_crm()
        return S.merge_builtin(days), books

    def special_days_crm(self) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
        """Yalnız CRM'den okunan kısım (kodda tanımlı günler eklenmeden): saklanabilir, JSON'a çevrilebilir."""
        from semantic_bridge.seo_geo import seasons as S

        days: dict[str, dict[str, Any]] = {}
        by_id: dict[str, str] = {}
        for r in self._run(days_sql(self.schema())):
            name = _s(r.get("name"))
            if not name:
                continue
            key = S.slug(name)
            d = days.setdefault(key, {"key": key, "name": name, "source": "crm", "crmIds": [], "weekFrom": None, "weekTo": None,
                                      "fixedDate": None})
            d["crmIds"].append(str(r["id"]))
            if r.get("w1") and not d["weekFrom"]:
                d["weekFrom"], d["weekTo"] = int(r["w1"]), int(r.get("w2") or r["w1"])
            d["fixedDate"] = d["fixedDate"] or S._crm_date(r.get("dt"))
            by_id[str(r["id"]).lower()] = key
        books: dict[str, dict[str, dict[str, Any]]] = {}
        for r in self._run(links_sql(self.schema())):
            key = by_id.get(str(r.get("day_id") or "").lower())
            bid = (_s(r.get("book_id")) or "").lower()
            if not key or not bid:
                continue
            books.setdefault(key, {}).setdefault(bid, {"bookId": bid, "ad": _s(r.get("name")), "stokKodu": _s(r.get("stok"))})
        return list(days.values()), {k: list(v.values()) for k, v in books.items()}


# ------------------------------------------------------------------ M46 önbelleği (Logo satışı)


def backlist_stmts(lo: int, hi: int) -> tuple[Any, Any]:
    """Pencere ay indeksleri (yıl*12 + ay-1) arasında kitap başına net adet; künye tablosu."""
    from semantic_bridge import budget as B

    idx = B.SALES.c.year * 12 + B.SALES.c.month - 1
    return (sa.select(B.SALES.c.stok_kodu, sa.func.sum(B.SALES.c.adet).label("adet")).where(idx >= lo, idx <= hi)
            .group_by(B.SALES.c.stok_kodu), sa.select(B.BOOKINFO))


def backlist_sales(engine: sa.engine.Engine) -> tuple[dict[str, float], dict[str, dict[str, Any]], Optional[date], tuple[int, int]]:
    """Son 12 tam ay (veri sonunun ayı dahil) kitap başına net adet, künye ve pencere. Bütçe modülü kurulu değilse
    boş döner (fırsat kutusunda «satış verisi yok» yazar)."""
    from semantic_bridge import budget as B
    from semantic_bridge import social as S

    try:
        B.ensure(engine)
        end = B.data_end(engine)
    except Exception as e:  # noqa: BLE001 — M46 kurulmamış olabilir
        log.info("social: bütçe önbelleği okunamadı: %s", e)
        return {}, {}, None, (0, 0)
    if end is None:
        return {}, {}, None, (0, 0)
    lo, hi = S.month_window(end)
    sq, iq = backlist_stmts(lo, hi)
    with engine.connect() as c:
        rows = c.execute(sq).all()
        info = {r.stok_kodu: dict(r._mapping) for r in c.execute(iq).all()}
    return {r[0]: float(r[1] or 0) for r in rows}, info, end, (lo, hi)


# ------------------------------------------------------------------ basın ve web (bayrakla)


def press_stmt(tenant: str, since: date):
    from semantic_bridge import web_watch as W

    return sa.select(W.ITEMS.c.title, W.ITEMS.c.url, W.ITEMS.c.source, W.ITEMS.c.published_at,
                     W.MENTIONS.c.author, W.MENTIONS.c.books_json, W.MENTIONS.c.label) \
        .select_from(W.MENTIONS.join(W.ITEMS, W.ITEMS.c.id == W.MENTIONS.c.item_id)) \
        .where(W.MENTIONS.c.tenant_id == tenant, W.MENTIONS.c.label.in_(("olumlu", "notr")),
               sa.func.coalesce(W.ITEMS.c.published_at, W.ITEMS.c.fetched_at) >= since) \
        .order_by(W.ITEMS.c.published_at.desc())


def press_mentions(engine: sa.engine.Engine, tenant: str, since: date) -> list[dict[str, Any]]:
    """Son günlerde yazar/kitap hakkında çıkan olumlu ya da nötr haberler. Tablo yoksa boş."""
    try:
        with engine.connect() as c:
            rows = c.execute(press_stmt(tenant, since)).all()
    except Exception as e:  # noqa: BLE001 — web taraması bu kurulumda yok
        log.info("social: basın kayıtları okunamadı: %s", e)
        return []
    import json

    out = []
    for r in rows:
        try:
            books = json.loads(r.books_json or "[]")
        except ValueError:
            books = []
        out.append({"baslik": r.title, "url": r.url, "kaynak": r.source, "tarih": r.published_at.date().isoformat() if r.published_at else None,
                    "yazar": r.author, "kitaplar": books, "ton": r.label})
    return out


# ------------------------------------------------------------------ stüdyo pazarlama kiti


def studio_assets(kitap_id: Optional[str], title: Optional[str]) -> dict[str, Any]:
    """Kitaba bağlı stüdyo işlerinin sosyal görselleri (onaylı olanlar işaretli) ve alıntıları. Stüdyo kapalıysa boş
    ve `hata` dolu; ekran «stüdyo şu an yanıt vermiyor» der."""
    from semantic_bridge import editorial_studio as es
    from semantic_bridge import editorial_studio_marketing as esm

    try:
        data = es.jobs()
    except Exception as e:  # noqa: BLE001
        log.info("social: stüdyo işleri okunamadı: %s", e)
        return {"items": [], "alintilar": [], "hata": "Stüdyo şu an yanıt vermiyor."}
    jobs = data.get("items") if isinstance(data, dict) else data
    want_id = (kitap_id or "").lower()
    want_title = " ".join(str(title or "").casefold().split())
    items, quotes, errors = [], [], []
    for j in jobs or []:
        src = j.get("source") or {}
        linked = bool(want_id) and str(src.get("crm_book_id") or "").lower() == want_id
        same = bool(want_title) and " ".join(str(j.get("title") or "").casefold().split()) == want_title
        if not (linked or same):
            continue
        try:
            view = esm.request("GET", str(j.get("id")), "", timeout=60)
        except Exception as e:  # noqa: BLE001
            errors.append(str(e)[:120])
            continue
        for s in (view.get("social") or {}).get("items") or []:
            items.append({"tip": "studio", "job": j.get("id"), "sid": s.get("id"), "ad": s.get("headline") or s.get("template"),
                          "boyut": f"{s.get('w')}×{s.get('h')}", "sablon": s.get("template"), "gorsel": s.get("visual"),
                          "onayli": bool(s.get("approved")), "taslak": bool(s.get("draft"))})
        quotes += [q for q in view.get("quotes") or [] if q and q not in quotes]
    return {"items": items, "alintilar": quotes, "hata": "; ".join(errors) or None}


def studio_file(job: str, sid: str) -> tuple[bytes, str]:
    from semantic_bridge import editorial_studio_marketing as esm

    data, mime, _ = esm.fetch(job, f"/social/{sid}", {"download": "1"})
    return data, mime


def studio_preview(job: str, sid: str, width: int) -> tuple[bytes, str]:
    from semantic_bridge import editorial_studio_marketing as esm

    data, mime, _ = esm.fetch(job, f"/social/{sid}", {"w": width})
    return data, mime


# ------------------------------------------------------------------ M19 içerik arşivi (bağlantı noktası)


def creative_provider(state: Any) -> Any:
    """M19 (`marketing_creative*`, tablolar `semantic_mkt_creative_*`) main'e girince `app.state.marketing_creative`
    kurulur. Beklenen arayüz (sözlük ya da nesne): `contract_assets(stok=, kanal=, durum="onayli") -> list[dict]`
    (her öğe en az `id`, `ad`/`format`, `onayli`) ve isteğe bağlı `asset_file(id) -> (bytes, mime)`. Yoksa None."""
    prov = getattr(state, "marketing_creative", None)
    if prov is None:
        return None
    if isinstance(prov, dict):
        return prov if callable(prov.get("contract_assets")) else None
    return prov if callable(getattr(prov, "contract_assets", None)) else None


def creative_assets(state: Any, stok: Optional[str], platform: Optional[str]) -> dict[str, Any]:
    prov = creative_provider(state)
    if prov is None or not stok:
        return {"bagli": prov is not None, "items": []}
    fn = prov["contract_assets"] if isinstance(prov, dict) else prov.contract_assets
    try:
        rows = fn(stok=stok, kanal=platform or "", durum="onayli") or []
    except Exception as e:  # noqa: BLE001
        log.warning("social: içerik arşivi okunamadı: %s", e)
        return {"bagli": True, "items": [], "hata": "İçerik arşivi okunamadı."}
    items = [{"tip": "creative", "id": str(r.get("id")), "ad": r.get("ad") or r.get("format") or str(r.get("id")),
              "boyut": r.get("format"), "onayli": bool(r.get("onayli", True))} for r in rows if r.get("id")]
    return {"bagli": True, "items": items}


def creative_file(state: Any, aid: str) -> Optional[tuple[bytes, str]]:
    prov = creative_provider(state)
    if prov is None:
        return None
    fn = prov.get("asset_file") if isinstance(prov, dict) else getattr(prov, "asset_file", None)
    return fn(aid) if callable(fn) else None
