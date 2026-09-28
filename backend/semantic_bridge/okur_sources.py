"""M37 Okur topluluğu: kaynaklar (yalnız okuma).

1. **Okur çekirdeği (H2) — `ReadersCore`.** Kimlik, izin, ilgi alanı ve segment sayımı H2 okur veri tabanının işidir; bu
   modül kopyalamaz. H2 köprüde bir sağlayıcı kaydeder (`app.state.readers_core`, yoksa `app.state.readers`, o da yoksa
   `semantic_bridge.readers` modülü) ve aşağıdaki sözleşmeyi verir. Hiçbiri yoksa `ReadersCore.resolve` `None` döner,
   ekran «Okur çekirdeği bağlı değil» der. Her cevap `okur.scrub` ile kişi alanından arındırılır; M37 yalnız sayı alır.

   Sözleşme (M37 → H2; ilk ad Türkçe sözleşme adı, sonrakiler H2'nin kendi adı olursa diye kabul edilen eşdeğerler):

   | İş | Yöntem | Döndürdüğü |
   |---|---|---|
   | Kitle envanteri | `okur_envanteri(tenant)` · `inventory` · `overview` | `{"toplam": int, "tekil": int?, "satirlar": [{"kaynak", "kayitTipi", "toplam", "kvkkOnayli", "iysOnayli", "epostaIzinli", "smsIzinli", "ilgiAlaniDolu", "silinebilir", "cocukOlasi"}], "tazelik": [{"kaynak", "sonOkuma"}]}` |
   | İzin sağlığı | `izin_sagligi(tenant)` · `consent_health` · `consent_issues` | `[{"tur", "ad", "sayi", "aciklama"}]` ya da `{tur: sayi}` |
   | Kural sayımı | `segment_olcusu(tenant, kural)` · `segment_size` · `preview_rule` | `{"toplam": int, "izinli": int?, "eposta": int?, "sms": int?}` |
   | İlgi alanları | `ilgi_alanlari(tenant)` · `interests` · `interest_nodes` | `[{"id", "ad", "okur": int?}]` |
   | Kuraldaki ilgi alanları | `kural_ilgi_alanlari(kural)` · `rule_interests` (isteğe bağlı) | `[id]`; yoksa M37 kuralı gezer |
   | Kural cümlesi | `kural_cumlesi(kural)` · `explain_rule` (isteğe bağlı) | okunur Türkçe cümle |
   | Kural alanları | `kural_alanlari()` · `rule_fields` (isteğe bağlı) | segment kurucusunun alan listesi |

   Sayıların doğruluğu H2'nin kabulüdür; M37 kabulü yalnız «ekrandaki sayı = H2'nin verdiği sayı = doğrudan SQL» zincirini
   sınar (scripts/acceptance/M37).

2. **CRM etkinlikleri** (`new_etkinlikBase`): yıl bazında etkinlik sayısı, katılımcı ve satılan kitap adedi; tip, il, yazar,
   kitap. Okul/cari ziyareti tipli kayıtlar (`new_ziyarettipi` dolu = satış ziyareti) varsayılan olarak dışarıda
   (`OKUR_ETKINLIK_ZIYARET_HARIC`); okur etkinliği tipleri ölçülmedi, `OKUR_ETKINLIK_TIPLERI` ile daraltılır (boşsa hepsi).
3. **CRM kitap kartı** (`new_kitapBase`): program için kitap arama ve duyuru taslağı için spot/arka kapak metni.
4. **T-soft okur yorumları** (`product/getComments`, yalnız okuma): yorum kimliği, ürün, puan, tarih, onay, metin ve
   sitede cevap var mı. Yorumcu adı, e-postası, müşteri numarası hiç okunmaz (alan beyaz listesi); metindeki e-posta/telefon
   maskelenir. Metin saklanmaz; cevap alanının adı ölçülmedi (`_ANSWER_KEYS`).

Kişi kolonu (`FullName`, `EMailAddress1`, `MobilePhone`, `Address*`) okur için hiçbir SELECT'te yoktur. Etkinlikteki
yazar adı yazardır (okur değil) ve `yazar` adıyla gelir.
"""
from __future__ import annotations

import importlib
import logging
import threading
import time
from typing import Any, Callable, Optional

from semantic_bridge import budget_sources as bsrc
from semantic_bridge import okur as O

log = logging.getLogger("semantic.okur.sources")

SourceError = bsrc.SourceError
Runner = bsrc.Runner
runner = bsrc.runner
NOT_CONNECTED = "Okur çekirdeği bağlı değil"


class CoreUnavailable(RuntimeError):
    """H2 okur çekirdeği bağlı değil ya da istenen yöntemi vermiyor."""


def q(v: str) -> str:
    return "N'" + str(v).replace("'", "''") + "'"


def prefix(schema: str) -> str:
    s = (schema or "").strip().rstrip(".")
    return f"{s}." if s else ""


# ------------------------------------------------------------------ H2 okur çekirdeği

_CONTRACT: dict[str, tuple[str, ...]] = {
    "inventory": ("okur_envanteri", "inventory", "overview"),
    "consent": ("izin_sagligi", "consent_health", "consent_issues"),
    "size": ("segment_olcusu", "segment_size", "preview_rule"),
    "interests": ("ilgi_alanlari", "interests", "interest_nodes"),
    "rule_interests": ("kural_ilgi_alanlari", "rule_interests"),
    "rule_text": ("kural_cumlesi", "explain_rule"),
    "rule_fields": ("kural_alanlari", "rule_fields"),
}
_REQUIRED = ("inventory", "consent", "size", "interests")


def _pick(d: dict[str, Any], *names: str) -> Any:
    low = {str(k).lower(): v for k, v in d.items()}
    for n in names:
        if n.lower() in low and low[n.lower()] is not None:
            return low[n.lower()]
    return None


def _num(v: Any) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


class ReadersCore:
    """H2 sağlayıcısının etrafındaki ince kabuk: ad eşlemesi, biçim düzeltme, kişi verisi süzgeci."""

    def __init__(self, provider: Any) -> None:
        self.provider = provider

    @staticmethod
    def _has(provider: Any, key: str) -> Optional[Callable[..., Any]]:
        for name in _CONTRACT[key]:
            fn = getattr(provider, name, None)
            if callable(fn):
                return fn
        return None

    @classmethod
    def resolve(cls, app: Any = None) -> Optional["ReadersCore"]:
        """Köprüde kayıtlı H2 sağlayıcısı; zorunlu dört yöntemi vermeyen aday atlanır."""
        cands: list[Any] = []
        state = getattr(app, "state", None)
        for attr in ("readers_core", "readers"):
            v = getattr(state, attr, None) if state is not None else None
            if v is not None:
                cands.append(v)
        try:
            cands.append(importlib.import_module("semantic_bridge.readers"))
        except ImportError:
            pass
        except Exception as e:  # noqa: BLE001 — H2 modülü yüklenemezse bağlı değil sayılır
            log.warning("okur: H2 modülü yüklenemedi: %s", e)
        for c in cands:
            if all(cls._has(c, k) for k in _REQUIRED):
                return cls(c)
        return None

    def _call(self, key: str, *args: Any) -> Any:
        fn = self._has(self.provider, key)
        if fn is None:
            raise CoreUnavailable(f"{NOT_CONNECTED}: «{_CONTRACT[key][0]}» yöntemi yok.")
        try:
            return O.scrub(fn(*args))
        except CoreUnavailable:
            raise
        except O.OkurError:
            raise
        except Exception as e:  # noqa: BLE001 — H2'nin hatası düz cümleyle
            log.warning("okur: H2 %s hata verdi: %s", key, e)
            raise SourceError(f"Okur çekirdeği cevap vermedi ({str(e)[:200]}).") from None

    def inventory(self, tenant: str) -> dict[str, Any]:
        raw = self._call("inventory", tenant) or {}
        rows_raw = []
        if isinstance(raw, dict):
            rows_raw = _pick(raw, "satirlar", "rows", "kaynaklar", "sources") or []
        rows = []
        for r in rows_raw if isinstance(rows_raw, list) else []:
            if not isinstance(r, dict):
                continue
            rows.append({
                "kaynak": str(_pick(r, "kaynak", "source") or "-"),
                "kayitTipi": str(_pick(r, "kayitTipi", "kayit_tipi", "recordType", "type") or ""),
                "toplam": _num(_pick(r, "toplam", "total", "count")) or 0,
                "kvkkOnayli": _num(_pick(r, "kvkkOnayli", "kvkk_onayli", "kvkk")),
                "iysOnayli": _num(_pick(r, "iysOnayli", "iys_onayli", "iys")),
                "epostaIzinli": _num(_pick(r, "epostaIzinli", "eposta_izinli", "email_ok", "emailOk", "email")),
                "smsIzinli": _num(_pick(r, "smsIzinli", "sms_izinli", "sms_ok", "smsOk", "sms")),
                "ilgiAlaniDolu": _num(_pick(r, "ilgiAlaniDolu", "ilgi_alani_dolu", "interest", "withInterest")),
                "silinebilir": _num(_pick(r, "silinebilir", "deletable")),
                "cocukOlasi": _num(_pick(r, "cocukOlasi", "cocuk_olasi", "minor", "isMinor")),
            })
        tot = _num(_pick(raw, "toplam", "total")) if isinstance(raw, dict) else None
        fresh = (_pick(raw, "tazelik", "freshness", "sources_freshness") if isinstance(raw, dict) else None) or []
        return {"toplam": tot if tot is not None else sum(r["toplam"] for r in rows),
                "tekil": _num(_pick(raw, "tekil", "unique", "unique_readers")) if isinstance(raw, dict) else None,
                "satirlar": rows, "tazelik": fresh if isinstance(fresh, list) else []}

    def consent(self, tenant: str) -> list[dict[str, Any]]:
        raw = self._call("consent", tenant) or []
        if isinstance(raw, dict):
            items = _pick(raw, "items", "turler", "issues")
            raw = items if isinstance(items, list) else [{"tur": k, "ad": k, "sayi": v} for k, v in raw.items()]
        out = []
        for r in raw if isinstance(raw, list) else []:
            if not isinstance(r, dict):
                continue
            tur = str(_pick(r, "tur", "type", "kind", "key") or "")
            if not tur:
                continue
            out.append({"tur": tur, "ad": str(_pick(r, "ad", "label", "name") or tur),
                        "sayi": _num(_pick(r, "sayi", "count", "total")) or 0,
                        "aciklama": _pick(r, "aciklama", "description", "help")})
        return out

    def size(self, tenant: str, rule: dict[str, Any]) -> dict[str, Any]:
        raw = self._call("size", tenant, rule) or {}
        if not isinstance(raw, dict):
            raise SourceError("Okur çekirdeği segment büyüklüğünü sayı olarak vermedi.")
        tot = _num(_pick(raw, "toplam", "total", "count"))
        if tot is None:
            raise SourceError("Okur çekirdeği segment büyüklüğünü vermedi.")
        email = _num(_pick(raw, "eposta", "email_ok", "emailOk", "email"))
        sms = _num(_pick(raw, "sms", "sms_ok", "smsOk"))
        permitted = _num(_pick(raw, "izinli", "permitted", "consented"))
        return {"toplam": tot, "izinli": permitted, "eposta": email, "sms": sms}

    def interests(self, tenant: str) -> list[dict[str, Any]]:
        raw = self._call("interests", tenant) or []
        if isinstance(raw, dict):
            raw = _pick(raw, "items", "nodes", "ilgiAlanlari") or []
        out = []
        for r in raw if isinstance(raw, list) else []:
            if not isinstance(r, dict):
                continue
            iid = _pick(r, "id", "node_id", "kategori_id")
            if iid is None:
                continue
            out.append({"id": str(iid), "ad": str(_pick(r, "ad", "name", "label", "path") or iid),
                        "okur": _num(_pick(r, "okur", "count", "readers", "toplam"))})
        return out

    def rule_interests(self, rule: dict[str, Any]) -> list[str]:
        if self._has(self.provider, "rule_interests"):
            raw = self._call("rule_interests", rule) or []
            return [str(x) for x in raw] if isinstance(raw, (list, tuple, set)) else []
        return O.rule_interest_ids(rule)

    def rule_text(self, rule: dict[str, Any]) -> Optional[str]:
        if not self._has(self.provider, "rule_text"):
            return None
        try:
            v = self._call("rule_text", rule)
        except SourceError:
            return None
        return str(v)[:4000] if v else None

    def rule_fields(self) -> list[Any]:
        if not self._has(self.provider, "rule_fields"):
            return []
        try:
            v = self._call("rule_fields")
        except SourceError:
            return []
        return v if isinstance(v, list) else []


# ------------------------------------------------------------------ CRM etkinlikleri


def event_years_sql(schema: str, exclude_visits: bool) -> str:
    p = prefix(schema)
    cond = " AND e.new_ziyarettipi IS NULL" if exclude_visits else ""
    return (f"SELECT DISTINCT YEAR(e.new_BalangTarihi) AS yil FROM {p}new_etkinlikBase e"
            f" WHERE e.new_BalangTarihi IS NOT NULL{cond}")


def events_sql(schema: str, year: int, exclude_visits: bool, types: list[str]) -> str:
    """Yılın etkinlikleri (başlangıç tarihine göre). Yazar/kitap adı yazara ve kitaba aittir; okur kişisi seçilmez."""
    p = prefix(schema)
    cond = " AND e.new_ziyarettipi IS NULL" if exclude_visits else ""
    if types:
        cond += f" AND t.new_name IN ({', '.join(q(x) for x in types)})"
    return (
        "SELECT e.new_etkinlikId AS id, e.new_name AS ad, CAST(e.statuscode AS int) AS durum, e.new_BalangTarihi AS tarih,"
        " t.new_name AS tip, i.new_name AS il, y.FullName AS yazar, pr.Name AS kitap,"
        " e.new_katilimcisayisi AS katilimci, e.new_SatilanKitapAd AS satilan"
        f" FROM {p}new_etkinlikBase e"
        f" LEFT JOIN {p}new_etkinliktipiBase t ON t.new_etkinliktipiId = e.new_etkinliktipiid"
        f" LEFT JOIN {p}new_illerBase i ON i.new_illerId = e.new_il"
        f" LEFT JOIN {p}ContactBase y ON y.ContactId = e.new_lgiliYazar"
        f" LEFT JOIN {p}ProductBase pr ON pr.ProductId = e.new_lgiliKitap"
        f" WHERE e.new_BalangTarihi >= '{int(year)}-01-01' AND e.new_BalangTarihi < '{int(year) + 1}-01-01'{cond}"
    )


EVENT_STATES = {1: "Planlandı", 100000002: "Tamamlandı", 100000000: "İptal edildi", 2: "Etkin değil"}
DONE = 100000002


def read_events(crm: Runner, schema: str, year: int, exclude_visits: bool, types: list[str]) -> dict[str, Any]:
    """Yılın etkinlikleri ve özeti. Katılımcı ve satılan adet yalnız «Tamamlandı» kayıtlarda toplanır (kabul 6)."""
    rows = crm(events_sql(schema, year, exclude_visits, types))
    items = []
    for r in rows:
        d = r.get("durum")
        items.append({"id": str(r.get("id")), "ad": O._clean(r.get("ad")), "durum": int(d) if d is not None else None,
                      "durumAdi": EVENT_STATES.get(int(d)) if d is not None else None,
                      "tarih": str(r.get("tarih"))[:10] if r.get("tarih") else None, "tip": O._clean(r.get("tip")) or "(tipsiz)",
                      "il": O._clean(r.get("il")), "yazar": O._clean(r.get("yazar")), "kitap": O._clean(r.get("kitap")),
                      "katilimci": _num(r.get("katilimci")), "satilan": _num(r.get("satilan"))})
    done = [x for x in items if x["durum"] == DONE]

    def group(key: str) -> list[dict[str, Any]]:
        g: dict[str, dict[str, Any]] = {}
        for x in done:
            k = x[key] or "(boş)"
            a = g.setdefault(k, {"ad": k, "etkinlik": 0, "katilimci": 0, "satilan": 0})
            a["etkinlik"] += 1
            a["katilimci"] += x["katilimci"] or 0
            a["satilan"] += x["satilan"] or 0
        return sorted(g.values(), key=lambda a: (-a["satilan"], -a["etkinlik"]))

    by_state: dict[str, int] = {}
    for x in items:
        k = x["durumAdi"] or "Bilinmiyor"
        by_state[k] = by_state.get(k, 0) + 1
    return {"yil": year, "toplam": len(items), "durumlar": by_state, "tamamlanan": len(done),
            "katilimci": sum(x["katilimci"] or 0 for x in done), "satilan": sum(x["satilan"] or 0 for x in done),
            "katilimciBos": sum(1 for x in done if x["katilimci"] is None),
            "tipler": group("tip"), "iller": group("il"), "yazarlar": group("yazar"),
            "etkinlikler": sorted(items, key=lambda x: (x["durum"] != DONE, -(x["satilan"] or 0), x["tarih"] or ""))}


def read_event_years(crm: Runner, schema: str, exclude_visits: bool) -> list[int]:
    return sorted({int(r["yil"]) for r in crm(event_years_sql(schema, exclude_visits)) if r.get("yil")}, reverse=True)


# ------------------------------------------------------------------ CRM kitap kartı


def book_search_sql(schema: str, text: str) -> str:
    p = prefix(schema)
    like = "%" + text.replace("[", "[[]").replace("%", "[%]").replace("_", "[_]") + "%"
    return ("SELECT k.new_kitapId AS id, k.new_name AS ad, k.new_StokKodu AS stok, k.new_yazartext AS yazar"
            f" FROM {p}new_kitapBase k WHERE k.statecode = 0 AND (k.new_name LIKE {q(like)} OR k.new_StokKodu LIKE {q(like)}"
            f" OR k.new_yazartext LIKE {q(like)}) ORDER BY k.new_name")


def book_sql(schema: str, book_id: str) -> str:
    p = prefix(schema)
    return ("SELECT k.new_kitapId AS id, k.new_name AS ad, k.new_yazartext AS yazar, k.new_kitapspotu AS spot, k.new_ozet AS ozet"
            f" FROM {p}new_kitapBase k WHERE k.new_kitapId = {q(book_id)}")


def search_books(crm: Runner, schema: str, text: str) -> list[dict[str, Any]]:
    t = (text or "").strip()
    if len(t) < 2:
        return []
    return [{"id": str(r["id"]), "ad": O._clean(r.get("ad")), "stokKodu": O._clean(r.get("stok")), "yazar": O._clean(r.get("yazar"))}
            for r in crm(book_search_sql(schema, t))]


def read_book(crm: Runner, schema: str, book_id: Optional[str]) -> Optional[dict[str, Any]]:
    import re as _re

    if not book_id or not _re.fullmatch(r"[0-9A-Fa-f\-]{32,36}", str(book_id)):
        return None
    rows = crm(book_sql(schema, str(book_id)))
    if not rows:
        return None
    r = rows[0]
    spot = r.get("spot") or r.get("ozet") or ""
    spot = _re.sub(r"<[^>]+>", " ", str(spot))
    return {"id": str(r["id"]), "ad": O._clean(r.get("ad")), "yazar": O._clean(r.get("yazar")), "spot": O._clean(spot, 2000)}


# ------------------------------------------------------------------ T-soft yorumları

#: Okunan alanlar (küçük harf). Yorumcu adı/e-postası/müşteri numarası listede yok: bellekte bile tutulmaz.
_ID_KEYS = ("commentid", "id", "productcommentid")
_TEXT_KEYS = ("comment", "text", "content", "message", "body")
_TITLE_KEYS = ("title", "subject")
_RATE_KEYS = ("rate", "rating", "point", "score")
_DATE_KEYS = ("createdate", "createdat", "datetime", "date", "datetimestamp")
_APPROVE_KEYS = ("isapproved", "approved", "status", "isactive")
#: Sitedeki yayınevi cevabı alanı ölçülmedi (2026-09-25 okumasında 86 yorumun hiçbiri cevaplı değildi); bu adlardan biri
#: doluysa yorum «cevaplandı» sayılır. Kabul listesinde «ölçülecek».
_ANSWER_KEYS = ("answer", "reply", "adminanswer", "answertext", "replytext", "response", "commentanswer")
_KEEP = set(_ID_KEYS + _TEXT_KEYS + _TITLE_KEYS + _RATE_KEYS + _DATE_KEYS + _APPROVE_KEYS + _ANSWER_KEYS + ("productid", "type"))


def _get(r: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for k in keys:
        if k in r and r[k] not in (None, ""):
            return r[k]
    return None


def comment_row(raw: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Ham T-soft yorumu → kişisel alansız satır. Yorum olmayan (soru vb.) kayıt atlanır."""
    from semantic_bridge.seo_geo.reviews import star

    r = {str(k).lower(): v for k, v in raw.items() if str(k).lower() in _KEEP}
    t = r.get("type")
    if t is not None and str(t).strip().lower() != "comment":
        return None
    cid = _get(r, _ID_KEYS)
    if cid is None:
        return None
    appr = _get(r, _APPROVE_KEYS)
    approved = True if appr is None else str(appr).strip().lower() not in ("0", "false", "hayır", "passive", "pasif")
    text = _get(r, _TEXT_KEYS)
    return {"id": str(cid)[:40], "productId": str(r.get("productid") or "")[:40] or None,
            "puan": star(_get(r, _RATE_KEYS)), "tarih": str(_get(r, _DATE_KEYS) or "")[:40] or None,
            "onayli": approved, "baslik": O.mask_text(str(_get(r, _TITLE_KEYS) or ""))[:200] or None,
            "metin": O.mask_text(str(text or ""))[:4000], "sitedeCevap": bool(str(_get(r, _ANSWER_KEYS) or "").strip())}


class Comments:
    """T-soft yorumlarının kısa süreli bellek önbelleği (yorum metni diske yazılmaz)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._at = 0.0
        self._rows: list[dict[str, Any]] = []

    def read(self, ttl: float, fresh: bool = False) -> list[dict[str, Any]]:
        from semantic_bridge.seo_geo import connections

        with self._lock:
            if not fresh and self._rows and time.monotonic() - self._at < ttl:
                return self._rows
            if not connections.tsoft.configured():
                raise SourceError("T-soft bağlantısı tanımlı değil (Yönetim → SEO & GEO).")
            rows: list[dict[str, Any]] = []
            start = 0
            try:
                while True:
                    page = connections.tsoft.call("product/getComments", {"type": "comment", "start": start,
                                                                          "limit": connections.PAGE}).get("data") or []
                    page = page if isinstance(page, list) else []
                    for x in page:
                        if isinstance(x, dict):
                            c = comment_row(x)
                            if c:
                                rows.append(c)
                    start += len(page)
                    if len(page) < connections.PAGE:
                        break
            except connections.ConnectionError_ as e:
                raise SourceError(str(e)) from None
            self._rows, self._at = rows, time.monotonic()
            return rows

    def one(self, comment_id: str, ttl: float) -> Optional[dict[str, Any]]:
        for fresh in (False, True):
            for r in self.read(ttl, fresh):
                if r["id"] == str(comment_id):
                    return r
        return None


def product_names(engine, tenant: str, ids: list[str]) -> dict[str, str]:
    """T-soft ürün adları SEO deposundan (eşitlemeyle gelir; ek T-soft isteği yok)."""
    ids = [i for i in set(ids) if i]
    if not ids:
        return {}
    import sqlalchemy as sa

    try:
        from semantic_bridge.seo_geo.store import PRODUCTS
        with engine.connect() as c:
            return {r[0]: r[1] for r in c.execute(sa.select(PRODUCTS.c.product_id, PRODUCTS.c.name)
                                                  .where(PRODUCTS.c.tenant_id == tenant, PRODUCTS.c.product_id.in_(ids)))}
    except Exception as e:  # noqa: BLE001 — SEO deposu yoksa ad boş kalır
        log.warning("okur: ürün adları okunamadı: %s", e)
        return {}


def seo_review_total(engine, tenant: str) -> Optional[dict[str, int]]:
    """SEO'nun gece yorum özeti (kabul 7 ile tutarlılık için)."""
    import sqlalchemy as sa

    try:
        from semantic_bridge.seo_geo.reviews import REVIEWS
        with engine.connect() as c:
            r = c.execute(sa.select(sa.func.sum(REVIEWS.c.comments), sa.func.count()).where(REVIEWS.c.tenant_id == tenant)).first()
        return {"yorum": int(r[0] or 0), "urun": int(r[1] or 0)} if r and r[1] else None
    except Exception:  # noqa: BLE001
        return None
