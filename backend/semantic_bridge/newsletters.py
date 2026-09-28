"""M24 E-bülten: segment sayacı (izin kuralı tek yerde), segment başına kitap önerisi, gövde ve konu satırı taslağı,
onay, gönderime hazır HTML, sonuç okuma.

**Portal toplu e-posta göndermez.** Gönderim TİMAŞ'ın izin yönetimi olan e-posta aracından yapılır; portal içerik,
segment tanımı ve sonuç raporu üretir. Portalın SMTP hesabı bülten için kullanılmaz.

**Kişi listesi dışarı çıkmaz.** Segment ucu yalnız sayı ve dağılım döner; kişi kimliği, adı, e-posta adresi hiçbir
sorguda seçilmez, hiçbir uçtan dönmez, hiçbir tabloya yazılmaz. Dosyadan sonuç alınırken kişi satırları yalnız sayılır,
dosya ve adresler saklanmaz.

**İzin kuralı (`permit_sql`, tek yer):** kişi etkin (`StateCode = 0`) ve toplu e-postaya izin veriyor
(`DoNotBulkEMail` 1 değil) ve e-postaya izin veriyor (`DoNotEMail` 1 değil) ve İYS onayı var (`new_iysonayi = 1`) ve
e-posta adresi dolu. `NEWSLETTER_REQUIRE_KVKK=1` ise KVKK onayı da şarttır. Segment süzgeçleri (ilgi alanı, yaş,
«haberdar olmak istiyorum») bu kuralın üstüne eklenir, kuralı gevşetemez.
"""
from __future__ import annotations

import csv
import html as H
import io
import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Callable, Optional

import sqlalchemy as sa

from semantic_bridge import catalogs as C

log = logging.getLogger("semantic.newsletters")
_md = sa.MetaData()

NEWSLETTERS = sa.Table(
    "semantic_newsletters", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("title", sa.String(300), nullable=False),
    sa.Column("segment_json", sa.Text, nullable=False),
    sa.Column("segment_size", sa.Integer),                            # izinli kişi sayısı (yalnız sayı)
    sa.Column("segment_detail_json", sa.Text),                        # izin dağılımı (yalnız sayılar)
    sa.Column("segment_at", sa.DateTime(timezone=True)),
    sa.Column("special_day", sa.String(120)),
    sa.Column("planned_at", sa.String(10)),
    sa.Column("status", sa.String(12), nullable=False),               # taslak | onayda | onayli | gonderildi | arsiv
    sa.Column("subject_options_json", sa.Text),
    sa.Column("subject_chosen", sa.String(300)),
    sa.Column("intro", sa.Text),
    sa.Column("html", sa.Text),
    sa.Column("dropped_json", sa.Text),                               # denetimde düşen cümleler
    sa.Column("submitted_by", sa.String(120)),
    sa.Column("submitted_at", sa.DateTime(timezone=True)),
    sa.Column("approved_by", sa.String(120)),
    sa.Column("approved_at", sa.DateTime(timezone=True)),
    sa.Column("note", sa.Text),
    sa.Column("sent_ref", sa.String(40)),                             # CRM kampanya kimliği (sonuç buradan okunur)
    sa.Column("sent_at", sa.String(10)),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)
NL_ITEMS = sa.Table(
    "semantic_newsletter_items", _md,
    sa.Column("newsletter_id", sa.String(32), primary_key=True),
    sa.Column("crm_book_id", sa.String(40), primary_key=True),
    sa.Column("stok_kodu", sa.String(80)),
    sa.Column("ad", sa.String(500)),
    sa.Column("position", sa.Integer, nullable=False),
    sa.Column("reason", sa.Text),
    sa.Column("text", sa.Text),
    sa.Column("text_source", sa.String(12)),
)
RESULTS = sa.Table(
    "semantic_newsletter_results", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("newsletter_id", sa.String(32), nullable=False, index=True),
    sa.Column("source", sa.String(8), nullable=False),                # crm | dosya | elle
    sa.Column("sent", sa.Integer),
    sa.Column("opened", sa.Integer),
    sa.Column("clicked", sa.Integer),
    sa.Column("unsubscribed", sa.Integer),
    sa.Column("bounced", sa.Integer),
    sa.Column("note", sa.Text),
    sa.Column("imported_by", sa.String(120)),
    sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
)

STATUSES = {"taslak": "Taslak", "onayda": "Onay bekliyor", "onayli": "Onaylı, gönderime hazır", "gonderildi": "Gönderildi",
            "arsiv": "Arşiv"}
#: Kişi kartındaki ilgi bayrakları (CRM `ContactBase`). Kolon adları yalnız bu listeden SQL'e girer.
CONTACT_FLAGS = {"new_tarihveakademi": "Tarih ve akademi", "new_sosyalbilimlerincelemearastirma": "Sosyal bilimler, inceleme, araştırma",
                 "new_timasakademi": "Timaş Akademi", "new_ElenceliBilgi": "Eğlenceli bilgi"}
DEFAULT_KEYWORDS = {"new_tarihveakademi": ["tarih", "akademi", "akademik"],
                    "new_sosyalbilimlerincelemearastirma": ["sosyal", "inceleme", "araştırma", "sosyoloji", "psikoloji", "felsefe"],
                    "new_timasakademi": ["akademi", "akademik"], "new_ElenceliBilgi": ["bilgi", "bilim", "eğlenceli"]}

_ready: set[int] = set()


def ensure(engine: sa.engine.Engine) -> None:
    if id(engine) in _ready:
        return
    _md.create_all(engine, checkfirst=True)
    _ready.add(id(engine))


def settings() -> dict[str, Any]:
    try:
        kw = json.loads(C._conf("NEWSLETTER_INTEREST_KEYWORDS", "") or "{}")
    except ValueError:
        kw = {}
    keywords = {k: list(v) for k, v in DEFAULT_KEYWORDS.items()}
    for k, v in (kw or {}).items():
        if isinstance(v, list):
            keywords[str(k)] = [str(x) for x in v if str(x).strip()]
    return {"requireKvkk": C._conf("NEWSLETTER_REQUIRE_KVKK", "0").strip().lower() in ("1", "true", "evet", "on"),
            "subjects": max(1, int(C._conf_float("NEWSLETTER_SUBJECT_OPTIONS", 5))),
            "keywords": keywords}


# ------------------------------------------------------------------ segment ve izin kuralı


def permit_sql(require_kvkk: bool, a: str = "c") -> str:
    """İzin kuralının TEK tanımı. Segment sayısına yalnız bu koşulu sağlayan kişi girer."""
    cond = (f"COALESCE({a}.DoNotBulkEMail, 0) = 0 AND COALESCE({a}.DoNotEMail, 0) = 0 AND {a}.new_iysonayi = 1"
            f" AND NULLIF(LTRIM(RTRIM({a}.EMailAddress1)), '') IS NOT NULL")
    if require_kvkk:
        cond += f" AND {a}.new_kvkkonayi = 1"
    return "(" + cond + ")"


def normalize_segment(raw: Any) -> dict[str, Any]:
    s = raw if isinstance(raw, dict) else {}

    def age(v):
        try:
            n = int(v)
        except (TypeError, ValueError):
            return None
        return n if 0 <= n <= 120 else None

    flags = [f for f in (s.get("ilgiBayraklari") or []) if f in CONTACT_FLAGS]
    links = [str(x).lower() for x in (s.get("ilgiAlanlari") or []) if C_GUID.match(str(x))]
    out = {"ilgiBayraklari": sorted(set(flags)), "ilgiAlanlari": sorted(set(links)), "yasMin": age(s.get("yasMin")),
           "yasMax": age(s.get("yasMax")), "haberdar": bool(s.get("haberdar"))}
    if out["yasMin"] is not None and out["yasMax"] is not None and out["yasMin"] > out["yasMax"]:
        out["yasMin"], out["yasMax"] = out["yasMax"], out["yasMin"]
    return out


C_GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def _years_ago(ref: date, years: int) -> date:
    try:
        return ref.replace(year=ref.year - years)
    except ValueError:  # 29 Şubat
        return ref.replace(year=ref.year - years, day=28)


def segment_filters(p: str, seg: dict[str, Any], ref: date) -> list[str]:
    """Segment süzgeçleri (izin kuralı dışında). İlgi bayrakları ve CRM ilgi alanı bağları VEYA ile birleşir."""
    out = ["c.StateCode = 0"]
    anyof = [f"c.{f} = 1" for f in seg["ilgiBayraklari"]]
    if seg["ilgiAlanlari"]:
        ids = ", ".join("'" + i + "'" for i in seg["ilgiAlanlari"])
        anyof.append(f"EXISTS (SELECT 1 FROM {p}new_contact_new_kitapilgialanBase l WHERE l.contactid = c.ContactId"
                     f" AND l.new_kitapilgialanid IN ({ids}))")
    if anyof:
        out.append("(" + " OR ".join(anyof) + ")")
    dob = "COALESCE(c.new_DogumTarihi, c.BirthDate)"
    if seg["yasMin"] is not None:
        out.append(f"{dob} <= '{_years_ago(ref, seg['yasMin']).isoformat()}'")
    if seg["yasMax"] is not None:
        out.append(f"{dob} > '{_years_ago(ref, seg['yasMax'] + 1).isoformat()}'")
    if seg["haberdar"]:
        out.append("c.new_haberdarolmakistiyorum = 1")
    return out


def segment_sql(p: str, seg: dict[str, Any], require_kvkk: bool, ref: date) -> str:
    """Yalnız sayılar: süzgece uyan kişi, izinli kişi ve izinsizlerin nedene göre dağılımı. Kişi kolonu seçilmez."""
    permit = permit_sql(require_kvkk)
    where = " AND ".join(segment_filters(p, seg, ref))
    return (
        "SELECT COUNT(*) AS aday,"
        f" COUNT(DISTINCT CASE WHEN {permit} THEN c.ContactId END) AS izinli,"
        " SUM(CASE WHEN COALESCE(c.DoNotBulkEMail, 0) = 1 THEN 1 ELSE 0 END) AS toplu_red,"
        " SUM(CASE WHEN COALESCE(c.DoNotEMail, 0) = 1 THEN 1 ELSE 0 END) AS eposta_red,"
        " SUM(CASE WHEN COALESCE(c.new_iysonayi, 0) <> 1 THEN 1 ELSE 0 END) AS iys_yok,"
        " SUM(CASE WHEN NULLIF(LTRIM(RTRIM(c.EMailAddress1)), '') IS NULL THEN 1 ELSE 0 END) AS adres_yok,"
        " SUM(CASE WHEN COALESCE(c.new_kvkkonayi, 0) = 1 THEN 1 ELSE 0 END) AS kvkk_var,"
        f" SUM(CASE WHEN {permit} AND COALESCE(c.new_kvkkonayi, 0) = 1 THEN 1 ELSE 0 END) AS izinli_kvkk"
        f" FROM {p}ContactBase c WHERE {where}"
    )


def segment_result(row: Optional[dict[str, Any]], require_kvkk: bool) -> dict[str, Any]:
    r = {k.lower(): v for k, v in (row or {}).items()}
    n = {k: int(r.get(k) or 0) for k in ("aday", "izinli", "toplu_red", "eposta_red", "iys_yok", "adres_yok", "kvkk_var", "izinli_kvkk")}
    return {"izinli": n["izinli"], "aday": n["aday"], "izinsiz": n["aday"] - n["izinli"],
            "dagilim": {"topluEpostaReddi": n["toplu_red"], "epostaReddi": n["eposta_red"], "iysOnayiYok": n["iys_yok"],
                        "adresYok": n["adres_yok"], "kvkkOnayli": n["kvkk_var"], "izinliVeKvkk": n["izinli_kvkk"]},
            "kural": ("Etkin kişi · toplu e-postaya ve e-postaya izin veriyor · İYS onayı var · e-posta adresi dolu"
                      + (" · KVKK onayı var" if require_kvkk else "")),
            "kvkkSart": require_kvkk}


def describe(seg: dict[str, Any], interests: dict[str, str]) -> str:
    parts = [CONTACT_FLAGS[f] for f in seg["ilgiBayraklari"]] + [interests.get(i, "ilgi alanı") for i in seg["ilgiAlanlari"]]
    s = ("İlgi: " + ", ".join(parts)) if parts else "Bütün izinli okurlar"
    if seg["yasMin"] is not None or seg["yasMax"] is not None:
        s += f" · yaş {seg['yasMin'] if seg['yasMin'] is not None else '…'}–{seg['yasMax'] if seg['yasMax'] is not None else '…'}"
    if seg["haberdar"]:
        s += " · kampanyadan haberdar olmak istiyor"
    return s


# ------------------------------------------------------------------ bülten kayıtları


# Okuma ifadeleri ayrı kurulur: aynı ifade hem çalıştırılır hem sorgu bilgisinde gösterilir (catalogs_kaynak.py).


def newsletter_stmt(tenant: str, nid: str):
    return sa.select(NEWSLETTERS).where(NEWSLETTERS.c.id == nid, NEWSLETTERS.c.tenant_id == tenant)


def newsletters_stmt(tenant: str, durum: str = ""):
    q = sa.select(NEWSLETTERS).where(NEWSLETTERS.c.tenant_id == tenant)
    if durum == "acik":
        q = q.where(NEWSLETTERS.c.status != "arsiv")
    elif durum:
        q = q.where(NEWSLETTERS.c.status == durum)
    return q.order_by(NEWSLETTERS.c.updated_at.desc())


def item_counts_stmt(ids: list[str]):
    return (sa.select(NL_ITEMS.c.newsletter_id, sa.func.count()).where(NL_ITEMS.c.newsletter_id.in_(ids or [""]))
            .group_by(NL_ITEMS.c.newsletter_id))


def results_stmt(ids: list[str]):
    return sa.select(RESULTS).where(RESULTS.c.newsletter_id.in_(ids or [""])).order_by(RESULTS.c.imported_at)


def own_results_stmt(nid: str):
    return sa.select(RESULTS).where(RESULTS.c.newsletter_id == nid).order_by(RESULTS.c.imported_at.desc())


def nl_items_stmt(nid: str):
    return sa.select(NL_ITEMS).where(NL_ITEMS.c.newsletter_id == nid).order_by(NL_ITEMS.c.position)


def report_stmt(tenant: str):
    return (sa.select(NEWSLETTERS).where(NEWSLETTERS.c.tenant_id == tenant,
                                         NEWSLETTERS.c.status.in_(("onayli", "gonderildi", "arsiv")))
            .order_by(NEWSLETTERS.c.sent_at.desc(), NEWSLETTERS.c.updated_at.desc()))


def _row(c, tenant: str, nid: str):
    r = c.execute(newsletter_stmt(tenant, nid)).mappings().first()
    if not r:
        raise C.CatalogError("Bülten bulunamadı.", 404)
    return r


def _view(r) -> dict[str, Any]:
    return {"id": r["id"], "baslik": r["title"], "segment": normalize_segment(C.load(r["segment_json"], {})),
            "segmentBuyuklugu": r["segment_size"], "segmentDagilim": C.load(r["segment_detail_json"], None),
            "segmentZamani": C.iso(r["segment_at"]), "ozelGun": r["special_day"], "planlanan": r["planned_at"],
            "durum": r["status"], "durumAdi": STATUSES.get(r["status"], r["status"]),
            "konular": C.load(r["subject_options_json"], []) or [], "konu": r["subject_chosen"], "giris": r["intro"],
            "dusen": C.load(r["dropped_json"], []) or [], "gonderen": r["submitted_by"], "gonderim": C.iso(r["submitted_at"]),
            "onaylayan": r["approved_by"], "onayZamani": C.iso(r["approved_at"]), "not": r["note"],
            "crmKampanya": r["sent_ref"], "gonderimTarihi": r["sent_at"], "olusturan": r["created_by"],
            "olusturma": C.iso(r["created_at"]), "guncelleme": C.iso(r["updated_at"])}


def _day(v: Any) -> Optional[str]:
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10]).isoformat()
    except ValueError:
        raise C.CatalogError("Tarih YYYY-AA-GG biçiminde olmalı.") from None


def create(engine, tenant: str, user: str, body: dict[str, Any]) -> dict[str, Any]:
    title = C._text(body.get("baslik"), 300)
    if not title:
        raise C.CatalogError("Bülten adı gerekli.")
    nid, t = C.uid(), C.now()
    with engine.begin() as c:
        c.execute(NEWSLETTERS.insert().values(id=nid, tenant_id=tenant, title=title, segment_json=C.dump(normalize_segment(body.get("segment"))),
                                              special_day=C._text(body.get("ozelGun"), 120), planned_at=_day(body.get("planlanan")),
                                              status="taslak", created_by=user, created_at=t, updated_at=t))
    return get(engine, tenant, nid)


def get(engine, tenant: str, nid: str) -> dict[str, Any]:
    with engine.connect() as c:
        return _view(_row(c, tenant, nid))


def list_newsletters(engine, tenant: str, durum: str = "") -> dict[str, Any]:
    with engine.connect() as c:
        rows = c.execute(newsletters_stmt(tenant, durum)).mappings().all()
        ids = [r["id"] for r in rows] or [""]
        n_items = dict(c.execute(item_counts_stmt(ids)).all())
        res = _latest_results(c, ids)
    items = []
    for r in rows:
        v = _view(r)
        v.pop("dusen", None)
        items.append({**v, "kitap": int(n_items.get(r["id"], 0)), "sonuc": res.get(r["id"])})
    return {"items": items, "total": len(items)}


def _latest_results(c, ids: list[str]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for r in c.execute(results_stmt(ids)).mappings():
        out[r["newsletter_id"]] = _result_view(r)
    return out


def _rate(a: Optional[int], b: Optional[int]) -> Optional[float]:
    return round(a / b, 4) if a is not None and b else None


def _result_view(r) -> dict[str, Any]:
    return {"id": r["id"], "kaynak": r["source"], "gonderilen": r["sent"], "acilan": r["opened"], "tiklanan": r["clicked"],
            "abonelikIptal": r["unsubscribed"], "geriDonen": r["bounced"], "not": r["note"], "kim": r["imported_by"],
            "zaman": C.iso(r["imported_at"]), "acilmaOrani": _rate(r["opened"], r["sent"]), "tiklamaOrani": _rate(r["clicked"], r["sent"])}


def _editable(r) -> None:
    if r["status"] != "taslak":
        raise C.CatalogError("Yalnız taslak bülten değiştirilir; önce taslağa geri alın.", 409)


def update(engine, tenant: str, nid: str, body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    vals: dict[str, Any] = {}
    with engine.begin() as c:
        r = _row(c, tenant, nid)
        after_send = {"crmKampanya", "gonderimTarihi"}
        if set(body) - after_send:
            _editable(r)
        elif r["status"] not in ("onayli", "gonderildi"):
            raise C.CatalogError("Gönderim bilgisi yalnız onaylı bültene girilir.", 409)
        if "baslik" in body:
            t = C._text(body["baslik"], 300)
            if not t:
                raise C.CatalogError("Bülten adı boş olamaz.")
            vals["title"] = t
        if "segment" in body:
            seg = normalize_segment(body["segment"])
            if C.dump(seg) != r["segment_json"]:
                vals.update(segment_json=C.dump(seg), segment_size=None, segment_detail_json=None, segment_at=None)
        if "ozelGun" in body:
            vals["special_day"] = C._text(body["ozelGun"], 120)
        if "planlanan" in body:
            vals["planned_at"] = _day(body["planlanan"])
        if "konu" in body:
            vals["subject_chosen"] = C._text(body["konu"], 300)
        if "giris" in body:
            vals["intro"] = C._text(body["giris"], 6000)
        if "crmKampanya" in body:
            ref = str(body["crmKampanya"] or "").strip().lower()
            if ref and not C_GUID.match(ref):
                raise C.CatalogError("CRM kampanya kimliği geçersiz.")
            vals["sent_ref"] = ref or None
        if "gonderimTarihi" in body:
            vals["sent_at"] = _day(body["gonderimTarihi"])
        diff = {k: {"eski": r[k], "yeni": v} for k, v in vals.items() if r[k] != v and k not in ("intro",)}
        if "intro" in vals and vals["intro"] != r["intro"]:
            diff["intro"] = "değişti"
        if vals:
            vals["updated_at"] = C.now()
            c.execute(NEWSLETTERS.update().where(NEWSLETTERS.c.id == nid).values(**vals))
    return get(engine, tenant, nid), diff


def delete(engine, tenant: str, nid: str) -> dict[str, Any]:
    with engine.begin() as c:
        r = _row(c, tenant, nid)
        if r["status"] != "taslak":
            raise C.CatalogError("Yalnız taslak bülten silinir; diğerleri arşive alınır.", 409)
        c.execute(NL_ITEMS.delete().where(NL_ITEMS.c.newsletter_id == nid))
        c.execute(RESULTS.delete().where(RESULTS.c.newsletter_id == nid))
        c.execute(C.JOBS.delete().where(C.JOBS.c.ref_id == nid))
        c.execute(NEWSLETTERS.delete().where(NEWSLETTERS.c.id == nid))
    return _view(r)


def set_segment_count(engine, tenant: str, nid: str, seg: dict[str, Any], res: dict[str, Any]) -> None:
    with engine.begin() as c:
        r = _row(c, tenant, nid)
        if C.dump(seg) != r["segment_json"]:
            return  # sayılan segment kayıttaki değil: yazılmaz
        c.execute(NEWSLETTERS.update().where(NEWSLETTERS.c.id == nid).values(
            segment_size=res["izinli"], segment_detail_json=C.dump({k: res[k] for k in ("aday", "izinsiz", "dagilim", "kural")}),
            segment_at=C.now()))


def _items(c, nid: str) -> list[dict[str, Any]]:
    return [dict(r) for r in c.execute(nl_items_stmt(nid)).mappings()]


def set_items(engine, tenant: str, nid: str, items: list[dict[str, Any]], pool: dict[str, Any], price_source: str) -> dict[str, Any]:
    books = {b["id"]: b for b in pool.get("books") or []}
    if not isinstance(items, list):
        raise C.CatalogError("Kitap listesi gerekli.")
    ids = [str((it or {}).get("crmKitapId") or "").lower() for it in items]
    if any(not i for i in ids) or len(set(ids)) != len(ids):
        raise C.CatalogError("Listede kimliği boş ya da iki kez geçen kitap var.")
    with engine.begin() as c:
        r = _row(c, tenant, nid)
        _editable(r)
        old = {x["crm_book_id"]: x for x in _items(c, nid)}
        c.execute(NL_ITEMS.delete().where(NL_ITEMS.c.newsletter_id == nid))
        for pos, (bid, it) in enumerate(zip(ids, items), start=1):
            prev, b = old.get(bid) or {}, books.get(bid)
            if not prev and b is None:
                raise C.CatalogError(f"Kitap havuzda yok: {bid}.", 409)
            text = C._text(it.get("metin"), 3000) if "metin" in it else prev.get("text")
            src = prev.get("text_source") if text == prev.get("text") else ("kullanici" if text else None)
            c.execute(NL_ITEMS.insert().values(newsletter_id=nid, crm_book_id=bid, stok_kodu=(b or {}).get("stok") or prev.get("stok_kodu"),
                                               ad=(b or {}).get("ad") or prev.get("ad"), position=pos,
                                               reason=prev.get("reason") or C._text(it.get("gerekce"), 2000), text=text, text_source=src))
        c.execute(NEWSLETTERS.update().where(NEWSLETTERS.c.id == nid).values(updated_at=C.now()))
    rebuild_html(engine, tenant, nid, pool, price_source)
    return detail(engine, tenant, nid, pool, price_source)


def detail(engine, tenant: str, nid: str, pool: Optional[dict[str, Any]], price_source: str) -> dict[str, Any]:
    books = {b["id"]: b for b in (pool or {}).get("books") or []}
    with engine.connect() as c:
        r = _row(c, tenant, nid)
        rows = _items(c, nid)
        results = [_result_view(x) for x in c.execute(own_results_stmt(nid)).mappings()]
    out = _view(r)
    out["kitaplar"] = []
    for it in rows:
        b = books.get(it["crm_book_id"])
        out["kitaplar"].append({"crmKitapId": it["crm_book_id"], "stokKodu": it["stok_kodu"], "ad": (b or {}).get("ad") or it["ad"],
                                "yazar": (b or {}).get("yazar"), "sira": it["position"], "gerekce": it["reason"], "metin": it["text"],
                                "metinKaynagi": it["text_source"], "fiyat": C.price_of(b, price_source) if b else None,
                                "kapak": (b or {}).get("kapak"), "webUrl": (b or {}).get("webUrl"),
                                "satistanKalkti": bool(b and C.out_of_sale(b)), "havuzdaYok": pool is not None and b is None})
    out["html"] = r["html"]
    out["sonuclar"] = results
    return out


def transition(engine, tenant: str, user: str, nid: str, action: str, note: Optional[str] = None) -> dict[str, Any]:
    flows = {"submit": ({"taslak"}, "onayda"), "withdraw": ({"onayda"}, "taslak"), "approve": ({"onayda"}, "onayli"),
             "reject": ({"onayda"}, "taslak"), "mark-sent": ({"onayli"}, "gonderildi"),
             "archive": ({"taslak", "onayli", "gonderildi"}, "arsiv"), "reopen": ({"onayli", "arsiv"}, "taslak")}
    if action not in flows:
        raise C.CatalogError("İşlem geçersiz.", 404)
    allowed, target = flows[action]
    t = C.now()
    with engine.begin() as c:
        r = _row(c, tenant, nid)
        if r["status"] not in allowed:
            raise C.CatalogError(f"Bülten «{STATUSES.get(r['status'])}» durumundayken bu işlem yapılamaz.", 409)
        vals: dict[str, Any] = {"status": target, "updated_at": t}
        if action == "submit":
            n = c.execute(sa.select(sa.func.count()).select_from(NL_ITEMS).where(NL_ITEMS.c.newsletter_id == nid)).scalar() or 0
            if not n or not (r["subject_chosen"] or "").strip() or not r["html"]:
                raise C.CatalogError("Onaya göndermeden önce kitap ekleyin, taslağı oluşturun ve konu satırını seçin.", 409)
            if r["segment_size"] is None:
                raise C.CatalogError("Onaya göndermeden önce segment büyüklüğünü sayın.", 409)
            vals.update(submitted_by=user, submitted_at=t, note=None)
        elif action == "approve":
            if (r["submitted_by"] or "").lower() == user.lower():
                raise C.CatalogError("Onaya gönderen kişi aynı bülteni onaylayamaz.", 403)
            vals.update(approved_by=user, approved_at=t)
        elif action == "reject":
            if not (note or "").strip():
                raise C.CatalogError("Geri gönderme gerekçesi yazın.")
            vals.update(note=note.strip()[:2000])
        elif action == "mark-sent":
            vals.update(sent_at=r["sent_at"] or C.today().isoformat())
        elif action == "reopen":
            vals.update(approved_by=None, approved_at=None)
        c.execute(NEWSLETTERS.update().where(NEWSLETTERS.c.id == nid).values(**vals))
    return get(engine, tenant, nid)


def pending_stmt(tenant: str):
    return sa.select(sa.func.count()).select_from(NEWSLETTERS).where(NEWSLETTERS.c.tenant_id == tenant, NEWSLETTERS.c.status == "onayda")


def pending_counts(engine, tenant: str) -> dict[str, int]:
    with engine.connect() as c:
        n = c.execute(pending_stmt(tenant)).scalar() or 0
    return {"bultenOnayda": int(n)}


# ------------------------------------------------------------------ kitap önerisi


def interest_scorer(seg: dict[str, Any], interests: dict[str, str], keywords: dict[str, list[str]]):
    """Segmentin ilgi alanı → kitabın tür/Kitaplık/web kategorisi metninde sözcük eşleşmesi (1 ya da 0) ve gerekçesi.
    Ilgi seçilmediyse None (bütün kitaplar eşit)."""
    groups: list[tuple[str, list[str]]] = []
    for f in seg["ilgiBayraklari"]:
        groups.append((CONTACT_FLAGS[f], [C.fold(k) for k in keywords.get(f, [])]))
    for i in seg["ilgiAlanlari"]:
        name = interests.get(i) or ""
        toks = [t for t in re.findall(r"[a-z0-9]+", C.fold(name)) if len(t) >= 4]
        if toks:
            groups.append((name, toks))
    groups = [(n, [t for t in toks if t]) for n, toks in groups if toks]
    if not groups:
        return None

    def score(b: dict[str, Any]) -> tuple[Optional[float], Optional[str]]:
        text = C.fold(" ".join(str(b.get(k) or "") for k in ("tur", "kitaplik", "web")))
        words = set(re.findall(r"[a-z0-9]+", text))
        for name, toks in groups:
            hit = next((t for t in toks if t in words or any(w.startswith(t) for w in words)), None)
            if hit:
                return 1.0, f"«{name}» ilgisiyle eşleşti (tür/kategori: {hit})"
        return 0.0, None

    return score


def suggest(pool: dict[str, Any], seg: dict[str, Any], special_day: Optional[str], interests: dict[str, str], cfg: dict[str, Any],
            ncfg: dict[str, Any], exclude: list[str], price_source: str) -> dict[str, Any]:
    scorer = interest_scorer(seg, interests, ncfg["keywords"])
    res = C.candidates(pool, {"ozelGun": special_day}, cfg, exclude=exclude, extra_score=scorer, price_source=price_source)
    res["ilgiEslesen"] = sum(1 for x in res["items"] if (x["parcalar"].get("ilgi") or 0) > 0) if scorer else None
    return res


# ------------------------------------------------------------------ taslak (Zeki AI) ve HTML


def _parse_json(raw: str) -> Optional[dict[str, Any]]:
    raw = (raw or "").strip()
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return None
    try:
        v = json.loads(m.group(0))
    except ValueError:
        return None
    return v if isinstance(v, dict) else None


def run_draft(engine, tenant: str, jid: str, nid: str, chat: Callable[[list[dict[str, str]]], str],
              read_texts: Callable[[list[str]], dict[str, dict[str, Optional[str]]]], pool: dict[str, Any], price_source: str,
              interests: dict[str, str], ncfg: dict[str, Any]) -> None:
    """Gövde (giriş + kitap başına kısa metin) ve konu satırı seçenekleri. Rakam, alıntı, üstünlük iddiası denetimden
    geçmezse cümle düşer; elle yazılmış kitap metnine dokunulmaz."""
    from semantic_bridge.marketing import guard

    try:
        C.job_update(engine, jid, status="calisiyor", step="Kitap metinleri okunuyor")
        d = detail(engine, tenant, nid, pool, price_source)
        if not d["kitaplar"]:
            raise C.CatalogError("Önce bültene kitap ekleyin.", 409)
        texts = read_texts([k["crmKitapId"] for k in d["kitaplar"]])
        days = {x["key"]: x for x in pool.get("days") or []}
        day = days.get(d.get("ozelGun") or "")
        seg_text = describe(d["segment"], interests)
        sources = [d["baslik"], seg_text, (day or {}).get("ad") or ""]
        books = []
        for n, k in enumerate(d["kitaplar"], start=1):
            t = texts.get(k["crmKitapId"]) or {}
            src = t.get("kisa") or t.get("ozet") or ""
            sources += [k["ad"] or "", k["yazar"] or "", t.get("kisa") or "", t.get("ozet") or ""]
            books.append(f"{n}. {k['ad']} — {k['yazar'] or ''}\nTanıtım: {src[:1500]}")
        n_subj = ncfg["subjects"]
        sys_msg = ("Timaş Yayınları'nın e-bülten editörüsün. Okura giden bültenin giriş paragrafını, her kitap için 2-3 cümlelik "
                   "tanıtımı ve konu satırı seçeneklerini yazarsın. Yalnız verilen tanıtım metinlerindeki bilgileri kullan; sayı, "
                   "ödül, alıntı, fiyat, indirim ya da «en çok satan» gibi üstünlük iddiası ekleme. Cevabı yalnız JSON olarak ver: "
                   '{"giris": "...", "kitaplar": [{"no": 1, "metin": "..."}], "konular": ["...", "..."]}')
        user = (f"Bülten: {d['baslik']}\nOkur kitlesi: {seg_text}\n" + (f"Özel gün: {day['ad']}\n" if day else "")
                + f"Konu satırı seçeneği sayısı: {n_subj} (her biri en çok 70 karakter)\n\nKitaplar:\n" + "\n\n".join(books))
        C.job_update(engine, jid, step="Zeki AI taslağı yazıyor")
        raw = chat([{"role": "system", "content": sys_msg}, {"role": "user", "content": user}]) or ""
        data = _parse_json(raw)
        if data is None:
            raise C.CatalogError("Zeki AI cevabı okunamadı; yeniden deneyin.", 502)
        dropped: list[dict[str, str]] = []
        intro = guard.check(str(data.get("giris") or ""), sources)
        dropped += intro["dusen"]
        subjects = []
        for s in (data.get("konular") or [])[: n_subj * 2]:
            chk = guard.check(str(s).strip()[:120], sources)
            if chk["metin"] and not chk["dusen"]:
                subjects.append(chk["metin"])
            dropped += [{**x, "yer": "konu"} for x in chk["dusen"]]
        subjects = list(dict.fromkeys(subjects))[:n_subj]
        by_no = {}
        for x in data.get("kitaplar") or []:
            try:
                by_no[int(x.get("no"))] = str(x.get("metin") or "")
            except (TypeError, ValueError, AttributeError):
                continue
        with engine.begin() as c:
            for n, k in enumerate(d["kitaplar"], start=1):
                if k["metin"] and k["metinKaynagi"] == "kullanici":
                    continue
                t = texts.get(k["crmKitapId"]) or {}
                chk = guard.check(by_no.get(n, ""), [k["ad"] or "", k["yazar"] or "", t.get("kisa") or "", t.get("ozet") or ""])
                dropped += [{**x, "yer": k["ad"] or ""} for x in chk["dusen"]]
                c.execute(NL_ITEMS.update().where(NL_ITEMS.c.newsletter_id == nid, NL_ITEMS.c.crm_book_id == k["crmKitapId"])
                          .values(text=chk["metin"] or None, text_source="zeki" if chk["metin"] else None))
            r = _row(c, tenant, nid)
            chosen = r["subject_chosen"] if r["subject_chosen"] in subjects else (subjects[0] if subjects else None)
            c.execute(NEWSLETTERS.update().where(NEWSLETTERS.c.id == nid).values(
                intro=intro["metin"] or None, subject_options_json=C.dump(subjects), subject_chosen=chosen,
                dropped_json=C.dump(dropped[:200]), updated_at=C.now()))
        rebuild_html(engine, tenant, nid, pool, price_source)
        C.job_update(engine, jid, status="bitti", step=None, result={"konu": len(subjects), "dusen": len(dropped)})
    except Exception as e:  # noqa: BLE001
        log.exception("newsletter draft failed")
        C.job_update(engine, jid, status="hata", step=None, error=str(e)[:500] or e.__class__.__name__)


def render_html(d: dict[str, Any]) -> str:
    """Gönderime hazır e-posta HTML'i (satır içi stil, tablo düzeni). Kişiye özel alan yok; abonelikten çıkma bağlantısı
    gönderim aracının kendi yer tutucusuyla eklenir."""
    e = H.escape
    rows = []
    for k in d["kitaplar"]:
        img = (f'<img src="{e(k["kapak"])}" alt="{e(k["ad"] or "")}" width="96" style="display:block;border:0;border-radius:4px">'
               if k.get("kapak") else "")
        title = e(k["ad"] or "")
        if k.get("webUrl"):
            title = f'<a href="{e(k["webUrl"])}" style="color:#4c1d95;text-decoration:none">{title}</a>'
        price = f'<div style="margin-top:6px;font-weight:bold">{e(C.tr_money(k["fiyat"]))}</div>' if k.get("fiyat") is not None else ""
        rows.append(
            '<tr><td style="padding:12px 0;border-top:1px solid #eee" valign="top" width="108">' + img + "</td>"
            '<td style="padding:12px 0 12px 12px;border-top:1px solid #eee" valign="top">'
            f'<div style="font-size:16px;font-weight:bold">{title}</div>'
            f'<div style="color:#555;font-size:13px">{e(k.get("yazar") or "")}</div>'
            f'<div style="margin-top:6px;font-size:14px;line-height:1.5">{e(k.get("metin") or "")}</div>{price}</td></tr>')
    intro = "".join(f'<p style="margin:0 0 12px;font-size:15px;line-height:1.6">{e(p)}</p>'
                    for p in (d.get("giris") or "").split("\n") if p.strip())
    return ("<!doctype html><html lang=\"tr\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width\">"
            f"<title>{e(d.get('konu') or d['baslik'])}</title></head>"
            '<body style="margin:0;background:#f6f5fb;font-family:Arial,Helvetica,sans-serif;color:#1f1b2e">'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:16px">'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;background:#fff;border-radius:8px">'
            f'<tr><td style="padding:20px 20px 8px"><div style="font-size:12px;color:#6d28d9;font-weight:bold">TİMAŞ YAYINLARI</div>'
            f'<h1 style="margin:6px 0 12px;font-size:22px">{e(d["baslik"])}</h1>{intro}</td></tr>'
            '<tr><td style="padding:0 20px 12px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
            + "".join(rows) + "</table></td></tr>"
            '<tr><td style="padding:12px 20px 20px;font-size:11px;color:#777;line-height:1.5">Bu e-postayı Timaş Yayınları\'ndan '
            "ileti almaya izin verdiğiniz için alıyorsunuz. Fiyatlar gönderim günü geçerlidir.<br>"
            "{{ABONELIKTEN_CIKMA_BAGLANTISI}}</td></tr></table></td></tr></table></body></html>")


def rebuild_html(engine, tenant: str, nid: str, pool: Optional[dict[str, Any]], price_source: str) -> None:
    d = detail(engine, tenant, nid, pool, price_source)
    html_text = render_html(d) if d["kitaplar"] else None
    with engine.begin() as c:
        c.execute(NEWSLETTERS.update().where(NEWSLETTERS.c.id == nid).values(html=html_text))


# ------------------------------------------------------------------ sonuçlar


_COLS = {
    "sent": ("gonderilen", "gonderim", "gonderildi", "sent", "delivered", "teslim", "toplam", "total"),
    "opened": ("acilan", "acilma", "acildi", "okunan", "okundu", "opened", "opens", "open"),
    "clicked": ("tiklanan", "tiklama", "tiklandi", "clicked", "clicks", "click"),
    "unsubscribed": ("abonelik", "cikan", "iptal", "unsubscribed", "unsubscribe", "unsub"),
    "bounced": ("geri donen", "donen", "hatali", "bounced", "bounce"),
}
_TRUE = {"1", "evet", "yes", "true", "x", "var", "e", "y"}


def _col_key(h: str) -> Optional[str]:
    f = C.fold(h).replace("_", " ")
    for k, names in _COLS.items():
        if any(n in f for n in names):
            return k
    return None


def parse_results(text: str) -> dict[str, Any]:
    """E-posta aracının dışa aktarım dosyası. İki biçim: (1) özet (başlık + sayılar), (2) kişi satırlı (e-posta kolonlu):
    satırlar yalnız sayılır, adres okunmaz, saklanmaz. Dönen yalnız toplamlardır."""
    text = (text or "").lstrip("﻿").strip()
    if not text:
        raise C.CatalogError("Dosya boş.")
    try:
        dialect = csv.Sniffer().sniff(text[:4000], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = [r for r in csv.reader(io.StringIO(text), dialect) if any(x.strip() for x in r)]
    if len(rows) < 2:
        raise C.CatalogError("Dosyada başlık ve en az bir satır olmalı.")
    head = rows[0]
    keys = [_col_key(h) for h in head]
    # Kişi satırlı dosya: veri satırlarında e-posta adresi geçer. Adres yalnız bu tespit için bakılır, okunmaz, saklanmaz.
    per_person = any("@" in cell for r in rows[1:6] for cell in r)
    out: dict[str, Optional[int]] = {k: None for k in _COLS}
    if per_person:
        body = rows[1:]
        out["sent"] = len(body)
        for k in ("opened", "clicked", "unsubscribed", "bounced"):
            idx = [i for i, kk in enumerate(keys) if kk == k]
            if idx:
                i = idx[0]
                out[k] = sum(1 for r in body if i < len(r) and (C.fold(r[i]) in _TRUE or re.match(r"^\d{1,4}[-./]\d", r[i].strip() or "")
                                                                  or (r[i].strip().isdigit() and int(r[i]) > 0)))
        return {**out, "bicim": "kisi", "satir": len(body),
                "not": f"Kişi satırlı dosya: {len(body)} satır sayıldı; adresler okunmadı ve saklanmadı."}
    vals = rows[1]
    for i, k in enumerate(keys):
        if k and out[k] is None and i < len(vals):
            n = re.sub(r"[^\d]", "", vals[i])
            out[k] = int(n) if n else None
    if out["sent"] is None:
        raise C.CatalogError("Dosyada gönderilen sayısı bulunamadı (başlıkta «gönderilen» ya da «sent» olmalı).")
    return {**out, "bicim": "ozet", "satir": 1, "not": "Özet dosyası."}


def add_result(engine, tenant: str, user: str, nid: str, source: str, counts: dict[str, Any], note: Optional[str]) -> dict[str, Any]:
    def n(v):
        if v in (None, ""):
            return None
        try:
            x = int(float(v))
        except (TypeError, ValueError):
            raise C.CatalogError("Sayılar tam sayı olmalı.") from None
        if x < 0:
            raise C.CatalogError("Sayılar eksi olamaz.")
        return x

    vals = {k: n(counts.get(k)) for k in ("sent", "opened", "clicked", "unsubscribed", "bounced")}
    if vals["sent"] is None:
        raise C.CatalogError("Gönderilen sayısı gerekli.")
    for k in ("opened", "clicked", "unsubscribed", "bounced"):
        if vals[k] is not None and vals[k] > vals["sent"]:
            raise C.CatalogError("Açılan/tıklanan/çıkan/geri dönen sayısı gönderilenden büyük olamaz.")
    with engine.begin() as c:
        r = _row(c, tenant, nid)
        if r["status"] not in ("onayli", "gonderildi", "arsiv"):
            raise C.CatalogError("Sonuç yalnız onaylanmış ve gönderilmiş bültene girilir.", 409)
        rid = C.uid()
        c.execute(RESULTS.insert().values(id=rid, newsletter_id=nid, source=source, note=C._text(note, 1000), imported_by=user,
                                          imported_at=C.now(), **vals))
        row = c.execute(sa.select(RESULTS).where(RESULTS.c.id == rid)).mappings().first()
    return _result_view(row)


def delete_result(engine, tenant: str, nid: str, rid: str) -> dict[str, Any]:
    with engine.begin() as c:
        _row(c, tenant, nid)
        row = c.execute(sa.select(RESULTS).where(RESULTS.c.id == rid, RESULTS.c.newsletter_id == nid)).mappings().first()
        if not row:
            raise C.CatalogError("Sonuç bulunamadı.", 404)
        c.execute(RESULTS.delete().where(RESULTS.c.id == rid))
    return _result_view(row)


def crm_linked(engine, tenant: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        return [dict(r) for r in c.execute(sa.select(NEWSLETTERS.c.id, NEWSLETTERS.c.sent_ref)
                                           .where(NEWSLETTERS.c.tenant_id == tenant, NEWSLETTERS.c.sent_ref.isnot(None),
                                                  NEWSLETTERS.c.status.in_(("onayli", "gonderildi", "arsiv")))).mappings()]


def record_crm_result(engine, tenant: str, nid: str, counts: dict[str, Any]) -> bool:
    """CRM kampanya sayaçları değiştiyse yeni sonuç satırı (kaynak crm). Aynıysa yazılmaz."""
    sent = counts.get("toplam")
    if sent is None:
        return False
    vals = {"sent": int(sent), "opened": int(counts["okunan"]) if counts.get("okunan") is not None else None,
            "clicked": int(counts["tiklanan"]) if counts.get("tiklanan") is not None else None, "unsubscribed": None,
            "bounced": None}
    with engine.begin() as c:
        last = c.execute(sa.select(RESULTS).where(RESULTS.c.newsletter_id == nid, RESULTS.c.source == "crm")
                         .order_by(RESULTS.c.imported_at.desc())).mappings().first()
        if last and all(last[k] == v for k, v in vals.items()):
            return False
        c.execute(RESULTS.insert().values(id=C.uid(), newsletter_id=nid, source="crm", imported_by="sistem", imported_at=C.now(),
                                          note=f"CRM kampanyası: {counts.get('ad') or ''}"[:1000], **vals))
    return True


def report(engine, tenant: str) -> dict[str, Any]:
    with engine.connect() as c:
        rows = c.execute(report_stmt(tenant)).mappings().all()
        res = _latest_results(c, [r["id"] for r in rows] or [""])
    items = [{"id": r["id"], "baslik": r["title"], "durum": r["status"], "durumAdi": STATUSES.get(r["status"]),
              "gonderimTarihi": r["sent_at"], "segmentBuyuklugu": r["segment_size"], "konu": r["subject_chosen"],
              "crmKampanya": r["sent_ref"], "sonuc": res.get(r["id"])} for r in rows]
    with_res = [i["sonuc"] for i in items if i["sonuc"] and i["sonuc"]["gonderilen"]]
    tot = {k: sum((x.get(k) or 0) for x in with_res) for k in ("gonderilen", "acilan", "tiklanan")}
    return {"items": items, "toplam": {**tot, "acilmaOrani": _rate(tot["acilan"], tot["gonderilen"]),
                                       "tiklamaOrani": _rate(tot["tiklanan"], tot["gonderilen"]), "bulten": len(with_res)}}
