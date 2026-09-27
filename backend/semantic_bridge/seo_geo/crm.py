"""CRM kitap kartı ve dijital haklar: SEO/GEO ekranlarında ürünün yanında gösterilir. Yalnız okunur; CRM'e yazılmaz.

Ne okunur (2026-09-26/27 canlı CRM .28 ölçümü, docs/analiz/seo-geo-modul-2026-09-25.md → «CRM»):
- Kitap kartı `new_kitapBase`: T-soft ürününe `new_ean13` ile bağlanır (T-soft'ta aktif 6.578 kartın hepsinde dolu).
  SEO/GEO'ya yarayan alanlar: yayıncılık durumu, özgün ad/dil, ilk yayın, hedef kitle, yazar/çizer/çevirmen,
  tadımlık PDF (`new_okumalink`), video (`new_ProductWebsite`/`new_youtubelink`), spot, özet, tanıtım, öne çıkanlar,
  alıntılar, anahtar kelimeler. İç yazışma alanları (editör görüşü, baskı önerisi) okunmaz.
- Sözleşme `new_sozlesmeBase`, kitaba `new_new_sozlesme_new_kitapBase` ile: yalnız **Telif Alış** (tip 5) sayılır;
  Telif Satış (1) Timaş'ın hakkı yurtdışına sattığı sözleşmedir, internette gösterim hakkıyla ilgisi yoktur.
  İnternette gösterim = `new_iletimhakki` (umuma iletim). Yanında e-kitap, Z-kitap, sesli kitap hakları.
- CRM'deki `new_kitapsorusu` okuma-anlama test sorusudur (107 kitap); SSS şeması için kullanılmaz.

Hak kararı (kitap başına): yürürlükteki bütün Telif Alış sözleşmelerinde iletim hakkı varsa `var`; biri eksikse
`eksik`; hepsi var ama serbest metinli hak notu varsa `incele`; yürürlükte Telif Alış yoksa `yok` (koruma dışı
eserse `koruma_disi`). Kesin söz telif biriminindir; bu bir ön süzgeçtir.
"""
from __future__ import annotations

import html
import os
import re
from datetime import date, datetime
from typing import Any, Callable, Optional

from semantic_bridge.editorial import ACTIVE_STATUS, _prefix

CONNECTION_FILE = os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json")
ALIS, SATIS = 5, 1
#: Yayıncılık durumu etiketinin kodu → SEO uyarısı. Etiket CRM'den okunur; kod (YS05 …) etiketin başındadır.
STATUS_FLAGS = {"YS01": "iptal", "YS05": "bizim_degil", "YS06": "devredildi", "YS11": "cekildi", "YS12": "geri_istendi"}
RIGHTS = ("var", "incele", "eksik", "yok", "koruma_disi")
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
LIMIT = 500_000


def clean(v: Any, n: int = 0) -> Optional[str]:
    if v is None:
        return None
    t = _WS.sub(" ", html.unescape(_TAG.sub(" ", str(v)))).strip()
    if not t:
        return None
    return (t[: n - 1].rstrip() + "…") if n and len(t) > n else t


def ean_key(v: Any) -> str:
    return re.sub(r"[^0-9]", "", str(v or ""))


def _day(v: Any) -> Optional[date]:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return datetime.fromisoformat(str(v)[:10]).date() if v else None
    except ValueError:
        return None


def book_sql(p: str) -> str:
    return (
        "SELECT k.new_kitapId AS id, k.new_name AS name, k.new_ean13 AS ean, k.new_isbn13 AS isbn, k.new_ekitapisbn AS ebook_isbn,"
        " k.new_kitap_yayincilikstatusu AS status, CAST(ISNULL(k.new_tsoftaktif, 0) AS int) AS tsoft,"
        " k.new_orjinaladi AS original_title, k.new_orijinaldil AS original_language, k.new_ilkyayintarihi AS first_published,"
        " k.new_ilkyayinulkesi AS first_country, k.new_hedefkitle AS audience, k.new_hedefkitleyasbaslangic AS age_from,"
        " k.new_hedefkitleyasbitis AS age_to, k.new_yazartext AS authors, k.new_cizerlertext AS illustrators,"
        " k.new_tercumelertext AS translators, k.new_okumalink AS preview_pdf, k.new_ProductWebsite AS website,"
        " k.new_youtubelink AS youtube, k.new_turlertext AS genres, k.new_webkategorileritext AS web_categories,"
        " k.new_AnahtarKelimeler AS keywords, k.new_hastag AS hashtags, k.new_sayfasayisi AS pages,"
        " k.new_oncekiyayinevitext AS previous_publisher,"
        " LEFT(k.new_kitapspotu, 1200) AS spot, LEFT(k.new_ozet, 4000) AS summary, LEFT(k.new_TantmFyMetni, 3000) AS promo,"
        " LEFT(k.new_kitabinonecikanyanlari, 2000) AS highlights, LEFT(k.new_alintlar, 2000) AS quotes"
        f" FROM {p}new_kitapBase k WHERE k.statecode = 0 AND k.new_ean13 IS NOT NULL"
    )


def contract_sql(p: str) -> str:
    return (
        "SELECT sk.new_kitapid AS book_id, s.new_sozlesmeId AS id, s.new_name AS name, s.new_SozlesmeTipi AS kind,"
        " s.statuscode AS status, s.new_SozlesmeBitisTarihi AS ends, CAST(ISNULL(s.new_suresizsozlesme, 0) AS int) AS open_ended,"
        " s.new_fesihtarihi AS terminated, CAST(ISNULL(s.new_iletimhakki, 0) AS int) AS internet,"
        " CAST(ISNULL(s.new_EKitap, 0) AS int) AS ebook, CAST(ISNULL(s.new_ZKitapHakki, 0) AS int) AS zbook,"
        " CAST(ISNULL(s.new_SesliKitapHakki, 0) AS int) AS audiobook, CAST(ISNULL(s.new_KorumaDEser, 0) AS int) AS public_domain,"
        " LEFT(s.new_haklaraciklama, 600) AS rights_note"
        f" FROM {p}new_new_sozlesme_new_kitapBase sk JOIN {p}new_sozlesmeBase s ON s.new_sozlesmeId = sk.new_sozlesmeid"
        f" WHERE s.statecode = 0 AND s.new_SozlesmeTipi = {ALIS}"
    )


def party_sql(p: str) -> str:
    return (
        "SELECT t.new_sozlesmeid AS contract_id, c.FullName AS person, a.Name AS company"
        f" FROM {p}new_sozlesmetarafiBase t"
        f" JOIN {p}new_sozlesmeBase s ON s.new_sozlesmeId = t.new_sozlesmeid AND s.statecode = 0 AND s.new_SozlesmeTipi = {ALIS}"
        f" LEFT JOIN {p}ContactBase c ON c.ContactId = t.new_kisi LEFT JOIN {p}AccountBase a ON a.AccountId = t.new_Firma"
        " WHERE t.statecode = 0"
    )


def label_sql(p: str, attribute: str, entity: str = "new_kitap") -> str:
    """Seçenek etiketleri; aynı öznitelik adı başka varlıkta da olabilir, varlık adıyla daraltılır."""
    db = p.split(".")[0] + "." if p.count(".") >= 2 else ""
    return (f"SELECT sm.AttributeValue AS v, sm.Value AS l FROM {p}StringMap sm WHERE sm.LangId = 1055"
            f" AND sm.AttributeName = '{attribute}' AND sm.ObjectTypeCode IN"
            f" (SELECT e.ObjectTypeCode FROM {db}MetadataSchema.Entity e WHERE e.Name = '{entity}')")


def in_force(c: dict[str, Any], today: date) -> bool:
    if int(c.get("status") or 0) not in ACTIVE_STATUS:
        return False
    end, cut = _day(c.get("ends")), _day(c.get("terminated"))
    if cut and cut <= today:
        return False
    return bool(c.get("open_ended")) or end is None or end >= today


def verdict(contracts: list[dict[str, Any]], today: date) -> tuple[str, str]:
    """(karar, gerekçe). `contracts`: kitaba bağlı bütün Telif Alış sözleşmeleri (taraflarıyla)."""
    live = [c for c in contracts if in_force(c, today)]
    if not live:
        if any(c.get("public_domain") for c in contracts):
            return "koruma_disi", "Koruma dışı eser; telif sözleşmesi gerekmez."
        if contracts:
            return "yok", "Telif alış sözleşmelerinin hiçbiri yürürlükte değil (süresi dolmuş ya da feshedilmiş)."
        return "yok", "Kitaba bağlı telif alış sözleşmesi yok."
    missing = [c for c in live if not c.get("internet")]
    if missing:
        who = ", ".join(sorted({x for c in missing for x in c.get("parties") or []})) or "bir taraf"
        return "eksik", f"İnternette gösterim hakkı şu sözleşmede yok: {who}."
    if any(c.get("rights_note") for c in live):
        return "incele", "Hak notu var; telif birimi sözleşmeye bakmalı."
    return "var", "Yürürlükteki bütün telif alış sözleşmelerinde internette gösterim hakkı var."


def status_flag(label: Optional[str]) -> Optional[str]:
    code = (label or "").split(" ", 1)[0].upper()
    return STATUS_FLAGS.get(code)


def read(schema: str, execute: Callable[[str, int], Any], today: Optional[date] = None) -> list[dict[str, Any]]:
    """CRM'den bütün kitap kartlarını, hak özetiyle birlikte okur. `execute(sql, limit)` → (kolonlar, satırlar, kesik)."""
    p, today = _prefix(schema), today or date.today()

    def rows(sql: str) -> list[dict[str, Any]]:
        _, out, truncated = execute(sql, LIMIT)
        if truncated:
            raise RuntimeError("CRM sonucu kesildi; eksik veriyle karar verilmez.")
        return out

    labels = {int(r["v"]): r["l"] for r in rows(label_sql(p, "new_kitap_yayincilikstatusu"))}
    audience = {int(r["v"]): r["l"] for r in rows(label_sql(p, "new_hedefkitle"))}
    parties: dict[str, list[str]] = {}
    for r in rows(party_sql(p)):
        name = (r.get("person") or r.get("company") or "").strip()
        if name:
            parties.setdefault(str(r["contract_id"]).upper(), []).append(name)
    by_book: dict[str, list[dict[str, Any]]] = {}
    for r in rows(contract_sql(p)):
        c = {**r, "parties": parties.get(str(r["id"]).upper(), [])}
        by_book.setdefault(str(r["book_id"]).upper(), []).append(c)
    out = []
    for b in rows(book_sql(p)):
        ean = ean_key(b.get("ean"))
        if len(ean) < 8:
            continue
        contracts = by_book.get(str(b["id"]).upper(), [])
        decision, why = verdict(contracts, today)
        label = labels.get(int(b["status"])) if b.get("status") is not None else None
        live = [c for c in contracts if in_force(c, today)]
        out.append({
            "ean": ean, "bookId": str(b["id"]), "name": b.get("name"), "rights": decision, "rightsWhy": why,
            "statusLabel": label, "statusFlag": status_flag(label), "tsoftActive": bool(b.get("tsoft")),
            "isbn": clean(b.get("isbn")), "ebookIsbn": clean(b.get("ebook_isbn")),
            "originalTitle": clean(b.get("original_title")), "originalLanguage": clean(b.get("original_language")),
            "firstPublished": str(_day(b.get("first_published")) or "") or None, "firstCountry": clean(b.get("first_country")),
            "audience": audience.get(int(b["audience"])) if b.get("audience") is not None else None,
            "ageFrom": b.get("age_from"), "ageTo": b.get("age_to"),
            "authors": clean(b.get("authors")), "illustrators": clean(b.get("illustrators")),
            "translators": clean(b.get("translators")), "previousPublisher": clean(b.get("previous_publisher")),
            "previewPdf": clean(b.get("preview_pdf")),
            "video": next((clean(v) for v in (b.get("youtube"), b.get("website")) if v and "youtu" in str(v)), None),
            "genres": clean(b.get("genres")), "webCategories": clean(b.get("web_categories")),
            "keywords": clean(b.get("keywords")), "hashtags": clean(b.get("hashtags")), "pages": b.get("pages"),
            "spot": clean(b.get("spot")), "summary": clean(b.get("summary")), "promo": clean(b.get("promo")),
            "highlights": clean(b.get("highlights")), "quotes": clean(b.get("quotes")),
            "contracts": [{"name": c.get("name"), "parties": c["parties"], "inForce": in_force(c, today),
                           "ends": str(_day(c.get("ends")) or "") or None, "openEnded": bool(c.get("open_ended")),
                           "internet": bool(c.get("internet")), "ebook": bool(c.get("ebook")), "zbook": bool(c.get("zbook")),
                           "audiobook": bool(c.get("audiobook")), "publicDomain": bool(c.get("public_domain")),
                           "note": clean(c.get("rights_note"))} for c in contracts],
            "inForce": len(live),
        })
    return out


def connector():
    from semantic_layer.profiler.connectors import connector_from_file

    return connector_from_file(CONNECTION_FILE)
