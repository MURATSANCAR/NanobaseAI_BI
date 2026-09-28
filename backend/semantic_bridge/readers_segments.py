"""H2 Okuyucu veri tabanı: kural tabanlı segment motoru, onay akışı, izin denetimli liste dışa aktarımı.

H3 (e-ticaret) ve M37 (okur topluluğu) bu motoru kullanır; yeniden yazmaz. Yeni alan eklemek için
`register_field(ad, etiket, tür, okuyucu)` (örn. H3 «son sipariş», «sipariş sayısı»). Segment `domain` alanı
okur | eticaret.

**Tanım** `{"match": "all"|"any", "rules": [{"field", "op", "value"}]}` — her kural okunur bir cümleye çevrilir
(`explain`; model yok, açıklama kuralın kendisidir). Boş kural listesi bütün etkin okurlardır.

**Sayılar** her zaman kuralın kendisinden (profil tablosu) hesaplanır; model rakam üretmez. Zeki AI yalnız doğal dil
isteğinden **taslak kural** önerir (`draft_from_text`): seçenekler kapalı kümedir (alan adları, iller, etiketler bu
kurulumdaki veriden), listede olmayan değer atılır ve notu yazılır. Modele kişisel veri gitmez.

**Akış:** taslak → onay-bekliyor → onaylı (açıkça verilen `ozellik:okur.segment-onay`; taslağı yazan onaylayamaz)
| geri gönderildi (taslak). Onaylı segmentte kural değişirse sürüm artar ve yeniden onay ister. Arşiv.

**Dışa aktarım** yalnız onaylı segmentten, amaç yazılarak, açıkça verilen `ozellik:okur.liste-aktar` ile ve
`READERS_EXPORT_ENABLED` açıkken (hukuk teyidine kadar kapalı). Liste anında üretilir, portalda saklanmaz; kişi
bilgisi o an CRM'den okunur ve CRM'deki **güncel** izin bayrağı yeniden denetlenir (okuma turundan sonra ret veren
girmez). Dışarıda kalanlar nedeniyle sayılır. Kimin, ne zaman, hangi amaçla, kaç kişiyi aldığı ve hangi okurların
listede olduğu (okur numarası; kişisel veri değil) kaydedilir — KVKK başvurusunda «bu kişi hangi listelere girdi»
sorusunun cevabı buradadır.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import re
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

from semantic_bridge import readers as R

log = logging.getLogger("semantic.readers.segments")
_md = sa.MetaData()

SEGMENTS = sa.Table(
    "semantic_reader_segments", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("name", sa.String(200), nullable=False),
    sa.Column("definition_json", sa.Text, nullable=False),
    sa.Column("explanation", sa.Text),
    sa.Column("status", sa.String(16), nullable=False),              # taslak | onay-bekliyor | onayli | arsiv
    sa.Column("owner", sa.String(120), nullable=False),
    sa.Column("submitted_at", sa.DateTime(timezone=True)),
    sa.Column("approved_by", sa.String(120)),
    sa.Column("approved_at", sa.DateTime(timezone=True)),
    sa.Column("decision_note", sa.String(1000)),
    sa.Column("version", sa.Integer, nullable=False, default=1),
    sa.Column("domain", sa.String(10), nullable=False, default="okur"),   # okur | eticaret
    sa.Column("origin", sa.String(10)),                                   # elle | zeki
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
)
SNAPSHOTS = sa.Table(
    "semantic_reader_segment_snapshots", _md,
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("segment_id", sa.String(32), nullable=False, index=True),
    sa.Column("at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("version", sa.Integer),
    sa.Column("total", sa.Integer, nullable=False),
    sa.Column("email_ok", sa.Integer, nullable=False),
    sa.Column("sms_ok", sa.Integer, nullable=False),
    sa.Column("call_ok", sa.Integer, nullable=False),
)
EXPORTS = sa.Table(
    "semantic_reader_exports", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("segment_id", sa.String(32), nullable=False),
    sa.Column("segment_name", sa.String(200)),
    sa.Column("segment_version", sa.Integer),
    sa.Column("user", sa.String(120), nullable=False),
    sa.Column("at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("purpose", sa.String(500), nullable=False),
    sa.Column("channel", sa.String(8), nullable=False),
    sa.Column("count", sa.Integer, nullable=False),
    sa.Column("excluded_no_consent", sa.Integer, nullable=False),
    sa.Column("excluded_json", sa.Text),
)
EXPORT_MEMBERS = sa.Table(
    "semantic_reader_export_members", _md,
    sa.Column("export_id", sa.String(32), nullable=False, index=True),
    sa.Column("reader_id", sa.String(24), nullable=False, index=True),
)


def ensure_tables(engine: sa.engine.Engine) -> None:
    _md.create_all(engine, checkfirst=True)


STATUS_LABELS = {"taslak": "Taslak", "onay-bekliyor": "Onay bekliyor", "onayli": "Onaylı", "arsiv": "Arşiv"}
EXCLUDE_LABELS = {"ret": "Ret vermiş", "izin_yok": "İzin bilinmiyor (İYS kaydı yok)", "kvkk_yok": "KVKK açık rızası yok",
                  "cocuk": "18 yaş altı (ebeveyn rızası bilinmiyor)", "adres_yok": "Adresi CRM'de yok",
                  "canli_ret": "CRM'de az önce ret işaretlenmiş",
                  "okur_yok": "Okur veri tabanında henüz eşleşmedi (site müşterisi)"}

# ------------------------------------------------------------------ alanlar

FIELDS: dict[str, dict[str, Any]] = {}


def register_field(name: str, label: str, kind: str, getter: Callable[[dict[str, Any]], Any],
                   options: Optional[Callable[[list[dict[str, Any]]], list[str]]] = None, help: str = "") -> None:
    """Segment alanı. `kind`: set (değerlerden biri), range (sayı arası), number (≥/≤), days (son N gün / N günden eski),
    bool. `getter(profil)` set için liste, diğerleri için tek değer döner."""
    FIELDS[name] = {"label": label, "kind": kind, "get": getter, "options": options, "help": help}


def _opts(fn: Callable[[dict[str, Any]], Iterable[Any]]) -> Callable[[list[dict[str, Any]]], list[str]]:
    def run(profs: list[dict[str, Any]]) -> list[str]:
        c: Counter = Counter()
        for p in profs:
            for v in fn(p) or []:
                if v:
                    c[str(v)] += 1
        return [v for v, _n in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))]
    return run


def _attr(name: str) -> Callable[[dict[str, Any]], list[str]]:
    return lambda p: p["attrs"].get(name, [])


_STATUSES = lambda _p: ["izinli", "ret", "bilinmiyor"]  # noqa: E731

register_field("kaynak", "Kaynak", "set", lambda p: list(p["sources"]), lambda _p: list(R.SOURCE_LABELS))
register_field("il", "İl", "set", lambda p: [p["city"]] if p["city"] else [], _opts(lambda p: [p["city"]]))
register_field("yas", "Yaş", "range", lambda p: p["age"], help="Doğum yılı bilinmeyen okur yaş koşuluna girmez.")
register_field("cinsiyet", "Cinsiyet", "set", lambda p: [p["gender"]] if p["gender"] else [], _opts(lambda p: [p["gender"]]))
register_field("form_tipi", "Form tipi (CRM)", "set", _attr("form_tipi"), _opts(_attr("form_tipi")))
register_field("kayit_tipi", "Kayıt tipi (CRM)", "set", _attr("kayit_tipi"), _opts(_attr("kayit_tipi")))
register_field("katilim_kaynagi", "Katılım kaynağı (aday)", "set", _attr("katilim_kaynagi"), _opts(_attr("katilim_kaynagi")))
register_field("utm_kaynak", "Kampanya kaynağı (UTM)", "set", _attr("utm_kaynak"), _opts(_attr("utm_kaynak")))
register_field("utm_kampanya", "Kampanya adı (UTM)", "set", _attr("utm_kampanya"), _opts(_attr("utm_kampanya")))
register_field("ilgi", "İlgi alanı", "set", lambda p: p["interests"], _opts(lambda p: p["interests"]))
register_field("etkinlik_adi", "Katıldığı etkinlik (yükleme)", "set", _attr("etkinlik_adi"), _opts(_attr("etkinlik_adi")))
register_field("etkinlik_sayisi", "Etkinlik katılım sayısı", "number", lambda p: p["events"])
register_field("ilk_kayit", "İlk kayıt", "days", lambda p: p["firstSeen"])
register_field("son_temas", "Son temas", "days", lambda p: p["lastTouch"],
               help="Kayıt, etkinlik, izin değişikliği ya da yüklemeden en yenisi.")
register_field("izin_email", "E-posta izni", "set", lambda p: [p["consent"]["email"]], _STATUSES)
register_field("izin_sms", "SMS izni", "set", lambda p: [p["consent"]["sms"]], _STATUSES)
register_field("izin_arama", "Arama izni", "set", lambda p: [p["consent"]["call"]], _STATUSES)
register_field("kvkk", "KVKK açık rıza", "set", lambda p: [p["consent"]["kvkk"]], _STATUSES)
register_field("cocuk", "18 yaş altı", "bool", lambda p: p["minor"])

OPS = {"set": ("in", "not_in"), "range": ("between",), "number": ("gte", "lte"), "days": ("within", "older"), "bool": ("is",)}
OP_LABELS = {"in": "şunlardan biri", "not_in": "şunlardan biri değil", "between": "arası", "gte": "en az", "lte": "en çok",
             "within": "son … gün içinde", "older": "… günden eski", "is": "evet/hayır"}


def fold(v: Any) -> str:
    """Türkçe büyük/küçük harf duyarsız karşılaştırma anahtarı («İstanbul» = «istanbul», «IĞDIR» = «ığdır»)."""
    return str(v).replace("İ", "i").replace("I", "ı").lower().strip()


def field_catalog(profs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for name, f in FIELDS.items():
        opts = f["options"](profs) if f["options"] else None
        labels = None
        if name == "kaynak":
            labels = dict(R.SOURCE_LABELS)
        elif name in ("izin_email", "izin_sms", "izin_arama", "kvkk"):
            labels = dict(R.STATUS_LABELS)
        out.append({"field": name, "label": f["label"], "kind": f["kind"], "ops": list(OPS[f["kind"]]),
                    "options": opts, "optionLabels": labels, "help": f["help"] or None})
    return out


# ------------------------------------------------------------------ doğrulama, değerlendirme, açıklama


def validate(defn: Any, profs: Optional[list[dict[str, Any]]] = None, strict: bool = True
             ) -> tuple[dict[str, Any], list[str]]:
    """Tanımı temizler. `strict` iken hatalı kural 400 verir; değilse atılır ve notu döner (Zeki önerisi için).
    `profs` verilirse set değerleri bu kurulumdaki seçeneklere göre denetlenir (büyük/küçük harf duyarsız)."""
    notes: list[str] = []
    if not isinstance(defn, dict):
        raise R.ReadersError("Segment tanımı geçersiz.")
    match = defn.get("match", "all")
    if match not in ("all", "any"):
        raise R.ReadersError("Eşleşme «all» ya da «any» olmalı.")
    rules_in = defn.get("rules") or []
    if not isinstance(rules_in, list):
        raise R.ReadersError("Kurallar liste olmalı.")
    opts_cache: dict[str, dict[str, str]] = {}
    clean = []

    def bad(msg: str) -> None:
        if strict:
            raise R.ReadersError(msg)
        notes.append(msg)

    for i, r in enumerate(rules_in, 1):
        if not isinstance(r, dict):
            bad(f"{i}. kural okunamadı.")
            continue
        name, op, val = r.get("field"), r.get("op"), r.get("value")
        f = FIELDS.get(name)
        if not f:
            bad(f"{i}. kural: «{name}» diye bir alan yok.")
            continue
        if op not in OPS[f["kind"]]:
            bad(f"{i}. kural: «{f['label']}» için «{op}» koşulu kullanılamaz.")
            continue
        kind = f["kind"]
        if kind == "set":
            vals = val if isinstance(val, list) else [val]
            vals = [str(v).strip() for v in vals if v is not None and str(v).strip()]
            if profs is not None and f["options"]:
                if name not in opts_cache:
                    opts_cache[name] = {fold(o): o for o in f["options"](profs)}
                known = opts_cache[name]
                kept = [known[fold(v)] for v in vals if fold(v) in known]
                for v in vals:
                    if fold(v) not in known:
                        bad(f"{i}. kural: «{f['label']}» için «{v}» bu veride yok.")
                vals = kept
            if not vals:
                bad(f"{i}. kural: «{f['label']}» için değer seçilmedi.")
                continue
            clean.append({"field": name, "op": op, "value": sorted(set(vals), key=vals.index)})
        elif kind == "range":
            lo, hi = (val + [None, None])[:2] if isinstance(val, list) else (None, None)
            try:
                lo = None if lo in (None, "") else int(lo)
                hi = None if hi in (None, "") else int(hi)
            except (TypeError, ValueError):
                bad(f"{i}. kural: «{f['label']}» sınırları sayı olmalı.")
                continue
            if lo is None and hi is None or (lo is not None and hi is not None and lo > hi):
                bad(f"{i}. kural: «{f['label']}» aralığı geçersiz.")
                continue
            clean.append({"field": name, "op": op, "value": [lo, hi]})
        elif kind in ("number", "days"):
            try:
                n = int(val)
            except (TypeError, ValueError):
                bad(f"{i}. kural: «{f['label']}» için sayı girilmeli.")
                continue
            if n < 0:
                bad(f"{i}. kural: «{f['label']}» eksi olamaz.")
                continue
            clean.append({"field": name, "op": op, "value": n})
        elif kind == "bool":
            if not isinstance(val, bool):
                bad(f"{i}. kural: «{f['label']}» evet ya da hayır olmalı.")
                continue
            clean.append({"field": name, "op": op, "value": val})
    return {"match": match, "rules": clean}, notes


def _test(rule: dict[str, Any], p: dict[str, Any], now: datetime) -> bool:
    f = FIELDS[rule["field"]]
    got = f["get"](p)
    op, val = rule["op"], rule["value"]
    kind = f["kind"]
    if kind == "set":
        have = {fold(x) for x in (got or []) if x}
        want = {fold(x) for x in val}
        hit = bool(have & want)
        return hit if op == "in" else not hit
    if kind == "range":
        if got is None:
            return False
        lo, hi = val
        return (lo is None or got >= lo) and (hi is None or got <= hi)
    if kind == "number":
        g = got or 0
        return g >= val if op == "gte" else g <= val
    if kind == "days":
        if got is None:
            return False
        limit = now - timedelta(days=val)
        return got >= limit if op == "within" else got < limit
    if kind == "bool":
        return bool(got) is bool(val)
    return False


def matches(defn: dict[str, Any], p: dict[str, Any], now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(timezone.utc)
    rules = defn.get("rules") or []
    if not rules:
        return True
    res = (_test(r, p, now) for r in rules if r.get("field") in FIELDS)
    return all(res) if defn.get("match", "all") == "all" else any(res)


def evaluate(defn: dict[str, Any], profs: list[dict[str, Any]], now: Optional[datetime] = None) -> list[dict[str, Any]]:
    now = now or datetime.now(timezone.utc)
    return [p for p in profs if matches(defn, p, now)]


def counts(members: list[dict[str, Any]], cfg: dict[str, Any]) -> dict[str, Any]:
    """Toplam ve kanal başına: izinli, ret, bilinmiyor, dışa aktarılabilir + dışarıda kalma nedenleri."""
    out: dict[str, Any] = {"total": len(members), "minors": sum(1 for p in members if p["minor"])}
    for ch in R.CHANNELS:
        c = Counter(p["consent"][ch] for p in members)
        why: Counter = Counter()
        ok = 0
        for p in members:
            e, reason = R.exportable(p, ch, cfg)
            if e:
                ok += 1
            else:
                why[reason] += 1
        out[ch] = {"izinli": c["izinli"], "ret": c["ret"], "bilinmiyor": c["bilinmiyor"], "exportable": ok,
                   "excluded": dict(why)}
    out["kvkk"] = dict(Counter(p["consent"]["kvkk"] for p in members))
    return out


def _vals(v: list[Any], name: str) -> str:
    if name == "kaynak":
        v = [R.SOURCE_LABELS.get(x, x) for x in v]
    elif name in ("izin_email", "izin_sms", "izin_arama", "kvkk"):
        v = [R.STATUS_LABELS.get(x, x).lower() for x in v]
    v = [str(x) for x in v]
    return v[0] if len(v) == 1 else ", ".join(v[:-1]) + " ya da " + v[-1]


def explain(defn: dict[str, Any]) -> str:
    """Kuralı okunur Türkçe cümleye çevirir (deterministik)."""
    rules = defn.get("rules") or []
    if not rules:
        return "Bütün etkin okurlar."
    parts = []
    for r in rules:
        f = FIELDS.get(r["field"])
        if not f:
            continue
        lab, op, v = f["label"], r["op"], r["value"]
        if op == "in":
            parts.append(f"{lab.lower()} {_vals(v, r['field'])} olan")
        elif op == "not_in":
            parts.append(f"{lab.lower()} {_vals(v, r['field'])} olmayan")
        elif op == "between":
            lo, hi = v
            parts.append(f"{lab.lower()} {lo}–{hi} arası" if lo is not None and hi is not None
                         else f"{lab.lower()} en az {lo}" if lo is not None else f"{lab.lower()} en çok {hi}")
        elif op == "gte":
            parts.append(f"{lab.lower()} en az {v}")
        elif op == "lte":
            parts.append(f"{lab.lower()} en çok {v}")
        elif op == "within":
            parts.append(f"{lab.lower()} son {v} gün içinde olan")
        elif op == "older":
            parts.append(f"{lab.lower()} {v} günden eski olan")
        elif op == "is":
            parts.append(f"{lab.lower()} olan" if v else f"{lab.lower()} olmayan")
    head = "Şu koşulların hepsini sağlayan okurlar: " if defn.get("match", "all") == "all" else \
        "Şu koşullardan en az birini sağlayan okurlar: "
    return head + "; ".join(parts) + "."


# ------------------------------------------------------------------ segment kaydı ve akış


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _view(r: Any) -> dict[str, Any]:
    return {"id": r.id, "name": r.name, "definition": R._load(r.definition_json, {"match": "all", "rules": []}),
            "explanation": r.explanation, "status": r.status, "statusLabel": STATUS_LABELS.get(r.status, r.status),
            "owner": r.owner, "submittedAt": R._iso(r.submitted_at), "approvedBy": r.approved_by,
            "approvedAt": R._iso(r.approved_at), "decisionNote": r.decision_note, "version": r.version,
            "domain": r.domain, "origin": r.origin, "createdAt": R._iso(r.created_at), "updatedBy": r.updated_by,
            "updatedAt": R._iso(r.updated_at)}


def _get(conn, tenant: str, sid: str) -> Any:
    r = conn.execute(sa.select(SEGMENTS).where(sa.and_(SEGMENTS.c.tenant_id == tenant, SEGMENTS.c.id == sid))).first()
    if not r:
        raise R.ReadersError("Segment bulunamadı.", 404)
    return r


def segments_stmt(tenant: str, status: str = "", domain: str = ""):
    """Segment listesi okuması (aynı ifade sorgu bilgisinde)."""
    q = sa.select(SEGMENTS).where(SEGMENTS.c.tenant_id == tenant)
    if status:
        q = q.where(SEGMENTS.c.status.in_(status.split(",")))
    else:
        q = q.where(SEGMENTS.c.status != "arsiv")
    if domain:
        q = q.where(SEGMENTS.c.domain == domain)
    return q.order_by(SEGMENTS.c.updated_at.desc())


def snapshots_stmt(tenant: str):
    return sa.select(SNAPSHOTS).where(SNAPSHOTS.c.tenant_id == tenant).order_by(SNAPSHOTS.c.at)


def history_stmt(tenant: str, sid: str):
    return sa.select(SNAPSHOTS).where(sa.and_(SNAPSHOTS.c.tenant_id == tenant, SNAPSHOTS.c.segment_id == sid)).order_by(SNAPSHOTS.c.at)


def exports_stmts(tenant: str, page: int, size: int) -> dict[str, Any]:
    return {"say": sa.select(sa.func.count()).select_from(EXPORTS).where(EXPORTS.c.tenant_id == tenant),
            "sayfa": (sa.select(EXPORTS).where(EXPORTS.c.tenant_id == tenant).order_by(EXPORTS.c.at.desc())
                      .offset(max(0, page) * size).limit(size))}


def list_segments(engine: sa.engine.Engine, tenant: str, status: str = "", domain: str = "") -> list[dict[str, Any]]:
    R.ensure(engine)
    with engine.connect() as c:
        rows = list(c.execute(segments_stmt(tenant, status, domain)))
        snaps: dict[str, Any] = {}
        for s in c.execute(snapshots_stmt(tenant)):
            snaps[s.segment_id] = s
    out = []
    for r in rows:
        v = _view(r)
        s = snaps.get(r.id)
        v["lastSnapshot"] = {"at": R._iso(s.at), "total": s.total, "email": s.email_ok, "sms": s.sms_ok,
                             "call": s.call_ok} if s else None
        out.append(v)
    return out


def get_segment(engine: sa.engine.Engine, tenant: str, sid: str) -> dict[str, Any]:
    R.ensure(engine)
    with engine.connect() as c:
        return _view(_get(c, tenant, sid))


def create(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any],
           profs: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    R.ensure(engine)
    name = (body.get("name") or "").strip()
    if len(name) < 3:
        raise R.ReadersError("Segment adı en az 3 harf olmalı.")
    defn, _ = validate(body.get("definition") or {"match": "all", "rules": []}, profs)
    domain = body.get("domain") or "okur"
    if domain not in ("okur", "eticaret"):
        raise R.ReadersError("Alan «okur» ya da «eticaret» olmalı.")
    now = _now()
    sid = uuid.uuid4().hex
    with engine.begin() as c:
        c.execute(SEGMENTS.insert().values(id=sid, tenant_id=tenant, name=name[:200], definition_json=R._dump(defn),
                                           explanation=explain(defn), status="taslak", owner=user, version=1,
                                           domain=domain, origin="zeki" if body.get("origin") == "zeki" else "elle",
                                           created_at=now, updated_by=user, updated_at=now))
        return _view(_get(c, tenant, sid))


def update(engine: sa.engine.Engine, tenant: str, sid: str, user: str, body: dict[str, Any],
           profs: Optional[list[dict[str, Any]]] = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Ad/tanım değişikliği. Onaylı ya da onay bekleyen segment taslağa döner; onaylıda sürüm artar."""
    R.ensure(engine)
    now = _now()
    with engine.begin() as c:
        r = _get(c, tenant, sid)
        if r.status == "arsiv":
            raise R.ReadersError("Arşivdeki segment değiştirilemez.", 409)
        vals: dict[str, Any] = {}
        diff: dict[str, Any] = {}
        if "name" in body:
            name = (body.get("name") or "").strip()
            if len(name) < 3:
                raise R.ReadersError("Segment adı en az 3 harf olmalı.")
            if name != r.name:
                vals["name"], diff["name"] = name[:200], [r.name, name]
        if "definition" in body:
            defn, _ = validate(body["definition"], profs)
            if R._dump(defn) != r.definition_json:
                vals.update(definition_json=R._dump(defn), explanation=explain(defn))
                diff["definition"] = [R._load(r.definition_json, {}), defn]
        if not vals:
            return _view(r), {}
        if "definition" in diff and r.status in ("onayli", "onay-bekliyor"):
            vals.update(status="taslak", approved_by=None, approved_at=None, submitted_at=None,
                        version=(r.version or 1) + (1 if r.status == "onayli" else 0))
            diff["status"] = [r.status, "taslak"]
        c.execute(SEGMENTS.update().where(SEGMENTS.c.id == sid).values(**vals, updated_by=user, updated_at=now))
        return _view(_get(c, tenant, sid)), diff


def submit(engine: sa.engine.Engine, tenant: str, sid: str, user: str) -> dict[str, Any]:
    with engine.begin() as c:
        r = _get(c, tenant, sid)
        if r.status != "taslak":
            raise R.ReadersError("Yalnız taslak onaya gönderilir.", 409)
        c.execute(SEGMENTS.update().where(SEGMENTS.c.id == sid).values(
            status="onay-bekliyor", submitted_at=_now(), decision_note=None, updated_by=user, updated_at=_now()))
        return _view(_get(c, tenant, sid))


def decide(engine: sa.engine.Engine, tenant: str, sid: str, user: str, approve: bool, note: Optional[str] = None
           ) -> dict[str, Any]:
    """İki göz: taslağı yazan ya da son değiştiren onaylayamaz. Geri göndermede not zorunlu."""
    with engine.begin() as c:
        r = _get(c, tenant, sid)
        if r.status != "onay-bekliyor":
            raise R.ReadersError("Segment onay beklemiyor.", 409)
        if user.lower() in {(r.owner or "").lower(), (r.updated_by or "").lower()}:
            raise R.ReadersError("Segmenti yazan ya da son değiştiren kişi onaylayamaz.", 403)
        if not approve and not (note or "").strip():
            raise R.ReadersError("Geri gönderme nedeni yazılmalı.")
        vals = {"status": "onayli", "approved_by": user, "approved_at": _now()} if approve else \
            {"status": "taslak", "submitted_at": None}
        c.execute(SEGMENTS.update().where(SEGMENTS.c.id == sid).values(
            **vals, decision_note=(note or None) and note.strip()[:1000]))
        return _view(_get(c, tenant, sid))


def archive(engine: sa.engine.Engine, tenant: str, sid: str, user: str) -> dict[str, Any]:
    with engine.begin() as c:
        _get(c, tenant, sid)
        c.execute(SEGMENTS.update().where(SEGMENTS.c.id == sid).values(status="arsiv", updated_by=user, updated_at=_now()))
        return _view(_get(c, tenant, sid))


def pending_stmt(tenant: str):
    return sa.select(SEGMENTS.c.owner, SEGMENTS.c.updated_by).where(sa.and_(
        SEGMENTS.c.tenant_id == tenant, SEGMENTS.c.status == "onay-bekliyor"))


def pending_for(engine: sa.engine.Engine, tenant: str, user: str) -> int:
    """Kişinin onaylayabileceği (kendisinin yazmadığı) bekleyen segment sayısı."""
    R.ensure(engine)
    with engine.connect() as c:
        rows = list(c.execute(pending_stmt(tenant)))
    u = user.lower()
    return sum(1 for r in rows if u not in {(r.owner or "").lower(), (r.updated_by or "").lower()})


# ------------------------------------------------------------------ önizleme, anlık görüntü, sözleşme


def preview(engine: sa.engine.Engine, tenant: str, defn: Any, cfg: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Yalnız sayılar (kişi yok)."""
    cfg = cfg or R.settings()
    profs = R.profiles(engine, tenant, cfg)
    clean, _ = validate(defn, profs)
    mem = evaluate(clean, profs)
    out = counts(mem, cfg)
    out["explanation"] = explain(clean)
    out["definition"] = clean
    out["of"] = len(profs)
    return out


def members(engine: sa.engine.Engine, tenant: str, sid: str, cfg: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    """Segmentin güncel üyeleri (profil). Diğer modüller için; kişi bilgisi içermez."""
    seg = get_segment(engine, tenant, sid)
    return evaluate(seg["definition"], R.profiles(engine, tenant, cfg))


def summary(engine: sa.engine.Engine, tenant: str, sid: str, cfg: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Sözleşme ucu (M24, M37, M35): yalnız onaylı segmentin adı, açıklaması ve sayıları."""
    cfg = cfg or R.settings()
    seg = get_segment(engine, tenant, sid)
    if seg["status"] != "onayli":
        raise R.ReadersError("Yalnız onaylı segmentin özeti verilir.", 409)
    mem = evaluate(seg["definition"], R.profiles(engine, tenant, cfg))
    return {"id": seg["id"], "name": seg["name"], "explanation": seg["explanation"], "version": seg["version"],
            "domain": seg["domain"], "approvedAt": seg["approvedAt"], "counts": counts(mem, cfg)}


def snapshot_all(engine: sa.engine.Engine, tenant: str, cfg: Optional[dict[str, Any]] = None) -> int:
    """Onaylı segmentlerin günlük sayısı (üye listesi saklanmaz)."""
    cfg = cfg or R.settings()
    profs = R.profiles(engine, tenant, cfg)
    now = _now()
    n = 0
    with engine.begin() as c:
        for r in c.execute(sa.select(SEGMENTS).where(sa.and_(SEGMENTS.c.tenant_id == tenant, SEGMENTS.c.status == "onayli"))).fetchall():
            cnt = counts(evaluate(R._load(r.definition_json, {}), profs, now), cfg)
            c.execute(SNAPSHOTS.insert().values(tenant_id=tenant, segment_id=r.id, at=now, version=r.version,
                                                total=cnt["total"], email_ok=cnt["email"]["exportable"],
                                                sms_ok=cnt["sms"]["exportable"], call_ok=cnt["call"]["exportable"]))
            n += 1
    return n


def history(engine: sa.engine.Engine, tenant: str, sid: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        return [{"at": R._iso(s.at), "version": s.version, "total": s.total, "email": s.email_ok, "sms": s.sms_ok,
                 "call": s.call_ok}
                for s in c.execute(history_stmt(tenant, sid))]


def segments_containing(engine: sa.engine.Engine, tenant: str, profile: dict[str, Any],
                        cfg: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = list(c.execute(sa.select(SEGMENTS).where(sa.and_(SEGMENTS.c.tenant_id == tenant, SEGMENTS.c.status == "onayli"))))
    now = _now()
    return [{"id": r.id, "name": r.name} for r in rows if matches(R._load(r.definition_json, {}), profile, now)]


# ------------------------------------------------------------------ dışa aktarım


def _blocked_live(source: str, row: dict[str, Any], channel: str, cfg: dict[str, Any]) -> bool:
    for rule in cfg["flagRules"]:
        if rule.get("source") != source or rule.get("channel") != channel or rule.get("status") != "ret":
            continue
        v = row.get(rule.get("field"))
        try:
            if v is not None and int(v) == int(rule.get("value", 1)):
                return True
        except (TypeError, ValueError):
            continue
    return False


_PREF = {"crm_contact": 0, "crm_lead": 1, "crm_account": 2}


def export(engine: sa.engine.Engine, tenant: str, sid: str, user: str, channel: str, purpose: str,
           read_personal: Callable[[list[tuple[str, str]]], dict[tuple[str, str], dict[str, Any]]],
           cfg: Optional[dict[str, Any]] = None) -> tuple[str, bytes, dict[str, Any]]:
    cfg = cfg or R.settings()
    if not cfg["exportEnabled"]:
        raise R.ReadersError("Liste dışa aktarımı bu ortamda kapalı (rıza metni ve çocuk kayıtları için hukuk teyidi "
                             "bekleniyor; yönetici Yönetim → Okur veri tabanı ayarından açar).", 409)
    if channel not in R.CHANNELS:
        raise R.ReadersError("Kanal e-posta, SMS ya da arama olmalı.")
    purpose = (purpose or "").strip()
    if len(purpose) < 5:
        raise R.ReadersError("Dışa aktarımın amacı yazılmalı (en az 5 harf).")
    seg = get_segment(engine, tenant, sid)
    if seg["status"] != "onayli":
        raise R.ReadersError("Yalnız onaylı segment dışa aktarılır.", 409)
    profs = evaluate(seg["definition"], R.profiles(engine, tenant, cfg))
    why: Counter = Counter()
    ok_ids: list[str] = []
    for p in profs:
        e, reason = R.exportable(p, channel, cfg)
        if e:
            ok_ids.append(p["id"])
        else:
            why[reason] += 1
    links = [l for l in R.links_of(engine, tenant, ok_ids) if l.source in _PREF]
    live = read_personal([(l.source, l.source_id) for l in links]) if links else {}
    by_reader: dict[str, list[Any]] = {}
    for l in links:
        by_reader.setdefault(l.reader_id, []).append(l)
    city = {p["id"]: p["city"] for p in profs}
    rows_out: list[list[str]] = []
    exported: list[str] = []
    for rid in ok_ids:
        recs = sorted(by_reader.get(rid, []), key=lambda l: (_PREF[l.source], -(R._utc(l.created_at) or _now()).timestamp()))
        lv = [(l.source, live.get((l.source, l.source_id))) for l in recs]
        lv = [(s, x) for s, x in lv if x and int(x.get("durum") or 0) == 0]
        if any(_blocked_live(s, x, channel, cfg) for s, x in lv):
            why["canli_ret"] += 1
            continue
        addr, name = None, None
        for _s, x in lv:
            if channel == "email":
                addr = R.norm_email(x.get("eposta")) or R.norm_email(x.get("eposta2"))
            else:
                addr = R.norm_phone(x.get("cep"))
            if addr:
                name = x.get("ad")
                break
        if not addr:
            why["adres_yok"] += 1
            continue
        rows_out.append([rid, (name or "").strip(), addr, city.get(rid) or ""])
        exported.append(rid)
    head = ["okur_no", "ad_soyad", {"email": "eposta", "sms": "cep_telefonu", "call": "telefon"}[channel], "il"]
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(head)
    w.writerows(rows_out)
    data = ("﻿" + buf.getvalue()).encode("utf-8")
    eid = uuid.uuid4().hex
    now = _now()
    excluded = sum(why.values())
    with engine.begin() as c:
        c.execute(EXPORTS.insert().values(id=eid, tenant_id=tenant, segment_id=sid, segment_name=seg["name"],
                                          segment_version=seg["version"], user=user, at=now, purpose=purpose[:500],
                                          channel=channel, count=len(exported), excluded_no_consent=excluded,
                                          excluded_json=R._dump(dict(why))))
        for i in range(0, len(exported), 2000):
            c.execute(EXPORT_MEMBERS.insert(), [{"export_id": eid, "reader_id": r} for r in exported[i:i + 2000]])
    slug = re.sub(r"[^a-z0-9]+", "-", seg["name"].replace("İ", "i").lower().translate(R._TR)).strip("-")[:40] or "segment"
    fname = f"okur-listesi-{slug}-{channel}-{now.strftime('%Y%m%d-%H%M')}.csv"
    rec = {"id": eid, "count": len(exported), "excluded": dict(why), "excludedTotal": excluded, "segment": seg["name"],
           "channel": channel, "purpose": purpose, "fileName": fname}
    return fname, data, rec


def record_export(engine: sa.engine.Engine, tenant: str, *, list_id: str, list_name: str, version: Optional[int],
                  user: str, channel: str, purpose: str, reader_ids: list[str], excluded: dict[str, int]) -> str:
    """Başka modülün (H3 tetik listesi) izin denetimli dışa aktarımını aynı deftere yazar: KVKK başvurusunda «bu kişi
    hangi listelere girdi» sorusu tek yerden cevaplanır. `list_id` segment kimliği yerine modülün liste kimliğidir."""
    R.ensure(engine)
    eid = uuid.uuid4().hex
    with engine.begin() as c:
        c.execute(EXPORTS.insert().values(id=eid, tenant_id=tenant, segment_id=list_id[:32], segment_name=list_name[:200],
                                          segment_version=version, user=user, at=_now(), purpose=purpose[:500],
                                          channel=channel, count=len(reader_ids), excluded_no_consent=sum(excluded.values()),
                                          excluded_json=R._dump(dict(excluded))))
        for i in range(0, len(reader_ids), 2000):
            c.execute(EXPORT_MEMBERS.insert(), [{"export_id": eid, "reader_id": r} for r in reader_ids[i:i + 2000]])
    return eid


def list_exports(engine: sa.engine.Engine, tenant: str, page: int = 0, size: int = 50) -> dict[str, Any]:
    R.ensure(engine)
    q = exports_stmts(tenant, page, size)
    with engine.connect() as c:
        total = c.execute(q["say"]).scalar() or 0
        rows = list(c.execute(q["sayfa"]))
    return {"items": [_export_view(r) for r in rows], "total": total, "page": page, "pageSize": size}


def _export_view(r: Any) -> dict[str, Any]:
    why = R._load(r.excluded_json, {})
    return {"id": r.id, "segmentId": r.segment_id, "segment": r.segment_name, "version": r.segment_version,
            "user": r.user, "at": R._iso(r.at), "purpose": r.purpose, "channel": r.channel,
            "channelLabel": R.CHANNEL_LABELS.get(r.channel, r.channel), "count": r.count,
            "excludedTotal": r.excluded_no_consent,
            "excluded": [{"reason": k, "label": EXCLUDE_LABELS.get(k, k), "count": v} for k, v in why.items()]}


def exports_of_readers(engine: sa.engine.Engine, tenant: str, reader_ids: list[str]) -> list[dict[str, Any]]:
    if not reader_ids:
        return []
    with engine.connect() as c:
        rows = list(c.execute(sa.select(EXPORTS).join(EXPORT_MEMBERS, EXPORT_MEMBERS.c.export_id == EXPORTS.c.id)
                              .where(sa.and_(EXPORTS.c.tenant_id == tenant, EXPORT_MEMBERS.c.reader_id.in_(reader_ids)))
                              .order_by(EXPORTS.c.at.desc())))
    seen, out = set(), []
    for r in rows:
        if r.id not in seen:
            seen.add(r.id)
            out.append(_export_view(r))
    return out


def exports_since(engine: sa.engine.Engine, tenant: str, since: datetime) -> list[dict[str, Any]]:
    with engine.connect() as c:
        return [_export_view(r) for r in c.execute(sa.select(EXPORTS).where(sa.and_(
            EXPORTS.c.tenant_id == tenant, EXPORTS.c.at >= since)).order_by(EXPORTS.c.at))]


# ------------------------------------------------------------------ Zeki AI: doğal dilden taslak kural


def draft_prompt(text: str, catalog: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Modele giden mesaj: alan listesi ve kapalı seçenekler + istek. Kişi verisi yok."""
    lines = []
    for f in catalog:
        opts = f.get("options")
        o = ""
        if opts:
            o = " Seçenekler: " + " | ".join(opts[:200])
        lines.append(f"- {f['field']} ({f['label']}; tür {f['kind']}; koşullar {', '.join(f['ops'])}).{o}")
    system = ("Sen bir yayınevinin okur pazarlama asistanısın. İstenen okur grubunu yalnız verilen alanlar ve "
              "seçeneklerle kural olarak yaz. Sayı tahmin etme. Yalnız JSON döndür: "
              '{"match":"all","rules":[{"field":"...","op":"...","value":...}],"name":"kısa ad"}. '
              "set türünde value liste; range türünde [en az, en çok] (boş taraf null); number ve days türünde tam sayı "
              "(days: within = son N gün içinde, older = N günden eski); bool türünde true/false.")
    user = "Alanlar:\n" + "\n".join(lines) + f"\n\nİstek: {text.strip()[:1000]}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse_draft(raw: str) -> dict[str, Any]:
    m = re.search(r"\{.*\}", raw or "", re.S)
    if not m:
        raise R.ReadersError("Zeki AI anlaşılır bir kural önermedi; kuralı elle kurabilirsiniz.", 422)
    try:
        d = json.loads(m.group(0))
    except ValueError:
        raise R.ReadersError("Zeki AI anlaşılır bir kural önermedi; kuralı elle kurabilirsiniz.", 422) from None
    if not isinstance(d, dict):
        raise R.ReadersError("Zeki AI anlaşılır bir kural önermedi.", 422)
    return d


def draft_from_text(engine: sa.engine.Engine, tenant: str, text: str,
                    chat: Callable[[list[dict[str, str]]], str], cfg: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    if len((text or "").strip()) < 5:
        raise R.ReadersError("İsteği biraz daha açık yazın.")
    cfg = cfg or R.settings()
    profs = R.profiles(engine, tenant, cfg)
    cat = field_catalog(profs)
    d = parse_draft(chat(draft_prompt(text, cat)))
    clean, notes = validate({"match": d.get("match", "all"), "rules": d.get("rules") or []}, profs, strict=False)
    cnt = counts(evaluate(clean, profs), cfg)
    name = str(d.get("name") or "").strip()[:120] or text.strip()[:80]
    return {"name": name, "definition": clean, "explanation": explain(clean), "notes": notes, "counts": cnt}

