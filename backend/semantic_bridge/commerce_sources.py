"""H3 E-ticaret müşteri yönetimi: okumalar (yalnız okuma) ve kişisel alanların ayıklanması.

- **T-soft** (site siparişi ve üyeleri) SEO & GEO modülünün yalnız okuma istemcisiyle okunur
  (`seo_geo.connections.tsoft`; `READ_ONLY` deseni: yalnız `auth/*` ve `*/get*`). **T-soft'a hiçbir şey gönderilmez.**
  Liste yöntemleri 500'lük sayfalarla sonuna kadar okunur; tavan yok.
- **Alan adları ölçülmedi** (T-soft yöntem kataloğu girişsiz okunamıyor): her rolün aday alan adları `FIELDS`'tadır,
  Yönetim ekranındaki `COMMERCE_TSOFT_FIELDS` (JSON) ile değiştirilir. Okumada hangi rolün hangi alandan geldiği ve
  bulunamayan roller kaydedilir (ekranda «alan eşlemesi»); kabul listesinde «ölçülecek».
- **Kişisel veri diske yazılmaz.** Sipariş/üye kaydındaki e-posta, telefon, ad bellekte H2'nin tuzlu özetine
  (`readers.digest`, `READERS_HASH_SALT`) çevrilir; ham değer hiçbir tabloya, günlüğe, modele gitmez. İl adı tutulur
  (H2 ile aynı). Adres ve ad yalnız yetkili ekranda ve dışa aktarım anında T-soft'tan anlık okunur (`read_person`).
- **Ürün görüntülenme** T-soft'tan yeniden okunmaz: SEO eşitlemesinin `semantic_seo_products.data_json` alanından
  (`StatViews`, `Barcode`).
- **Kitap ve ilgi alanı:** barkod (EAN-13) → H1 kitap profili (`semantic_book_profiles`: onaylı ya da CRM'den çözülen
  kategori düğümü, CRM oluşturma tarihi); H1 boşsa SEO'nun CRM kitap eşlemesi (`semantic_seo_crm_books`, düğüm yok).
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Iterator, Optional

import sqlalchemy as sa

from semantic_bridge import budget_sources as bsrc
from semantic_bridge import readers as R

log = logging.getLogger("semantic.commerce.sources")

SourceError = bsrc.SourceError
Runner = bsrc.Runner
runner = bsrc.runner

#: Rol → aday alan adları (ilk bulunan kullanılır). Ölçülmedi; `COMMERCE_TSOFT_FIELDS` ile değiştirilir.
FIELDS: dict[str, list[str]] = {
    # sipariş
    "order_no": ["OrderCode", "OrderId", "OrderNo", "OrderNumber", "Id"],
    "ordered_at": ["OrderDateTime", "OrderDate", "CreateDateTime", "CreatedDate", "DateTime"],
    "status": ["OrderStatus", "OrderStatusName", "StatusName", "Status"],
    "status_id": ["OrderStatusId", "StatusId"],
    "total": ["OrderTotalPrice", "OrderTotal", "GeneralTotal", "TotalPrice", "Total"],
    "discount": ["DiscountTotal", "TotalDiscount", "Discount", "CouponDiscount"],
    "shipping": ["CargoPrice", "CargoTotal", "ShippingPrice", "ShippingTotal"],
    "coupon": ["CouponCode", "Coupon", "PromotionCode"],
    "payment": ["PaymentTypeName", "PaymentType", "PaymentMethod"],
    "utm_source": ["UtmSource", "utm_source", "Utm_Source"],
    "utm_campaign": ["UtmCampaign", "utm_campaign", "Utm_Campaign"],
    "customer_id": ["CustomerId", "MemberId", "UserId", "CustomerCode"],
    "is_guest": ["IsGuest", "GuestOrder", "Guest"],
    "lines": ["OrderDetails", "Products", "Details", "OrderProducts", "Items"],
    # sipariş satırı
    "line_barcode": ["Barcode", "ProductBarcode", "Ean", "EAN"],
    "line_code": ["ProductCode", "StockCode", "Code"],
    "line_qty": ["Quantity", "Count", "Piece"],
    "line_amount": ["TotalPrice", "LineTotal", "Total", "SellingPrice", "Price"],
    # kişisel (yalnız özete çevrilir)
    "email": ["CustomerEmail", "CustomerMail", "Email", "EMail", "Mail"],
    "phone": ["CustomerGsm", "CustomerPhone", "Gsm", "Mobile", "MobilePhone", "Phone", "Telephone"],
    "name": ["CustomerName", "CustomerFullName", "FullName", "NameSurname"],
    "first_name": ["Name", "FirstName"],
    "last_name": ["Surname", "LastName"],
    "city": ["CustomerCity", "InvoiceCity", "DeliveryCity", "City"],
    # üye
    "member_id": ["CustomerId", "MemberId", "Id", "UserId"],
    "member_created": ["RegisterDate", "CreateDateTime", "CreatedDate", "RegistrationDate"],
    "consent_email": ["EmailPermission", "AllowEmail", "MailPermission", "IsEmailNotification", "Newsletter"],
    "consent_sms": ["SmsPermission", "AllowSms", "IsSmsNotification", "SmsNotification"],
    "consent_kvkk": ["KvkkPermission", "KvkkApproved", "IsKvkkApproved", "Kvkk"],
    "consent_date": ["PermissionDate", "PermissionUpdateDate", "UpdateDateTime"],
}
#: Kişisel roller: yalnız özet için okunur; alan eşlemesi raporunda da adı geçer, değeri geçmez.
PERSONAL_ROLES = ("email", "phone", "name", "first_name", "last_name")
#: İptal/iade sayılan sipariş durumu metni (ayar boşsa). Geçersiz sipariş ciroya, RFM'e, tetiğe girmez; tabloda kalır.
CANCEL_RE = re.compile(r"\b(?:iptal|iade|cancel|refund|return|red|başarısız|basarisiz|fail)")
_EAN = re.compile(r"^[0-9]{8,14}$")


def fields(conf: Callable[[str, str], str]) -> dict[str, list[str]]:
    out = {k: list(v) for k, v in FIELDS.items()}
    raw = (conf("COMMERCE_TSOFT_FIELDS", "") or "").strip()
    if raw:
        try:
            over = json.loads(raw)
            for k, v in (over or {}).items():
                if k in out and v:
                    out[k] = [str(x) for x in (v if isinstance(v, list) else [v])]
        except ValueError:
            log.warning("commerce: COMMERCE_TSOFT_FIELDS JSON değil; varsayılan alanlar kullanıldı")
    return out


def pick(row: dict[str, Any], names: list[str]) -> tuple[Optional[str], Any]:
    """İlk dolu alan (ad, değer). Büyük/küçük harf duyarsız."""
    if not isinstance(row, dict):
        return None, None
    low = {str(k).lower(): k for k in row}
    for n in names:
        k = low.get(n.lower())
        if k is not None and row[k] not in (None, ""):
            return k, row[k]
    return None, None


def num(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("₺", "").replace("TL", "").strip()
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_dt(v: Any) -> Optional[datetime]:
    """T-soft tarih biçimleri: Unix saniye, ISO, «GG.AA.YYYY SS:DD(:ss)». Sonuç UTC değil yerel saattir (site saati);
    tz bilgisi eklenmez, gün sınırı sitenin gününe göre kalır."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.replace(tzinfo=None)
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day)
    if isinstance(v, (int, float)) or (isinstance(v, str) and v.strip().isdigit() and len(v.strip()) >= 9):
        try:
            ts = float(v)
            if ts > 1e12:
                ts /= 1000
            return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().replace(tzinfo=None)
        except (OverflowError, OSError, ValueError):
            return None
    s = str(v).strip()
    for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d.astimezone().replace(tzinfo=None) if d.tzinfo else d
    except ValueError:
        return None


def ean_key(v: Any) -> Optional[str]:
    s = re.sub(r"[^0-9]", "", str(v or ""))
    return s if _EAN.match(s) else None


def truthy(v: Any) -> Optional[bool]:
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("1", "true", "evet", "yes", "on", "e"):
        return True
    if s in ("0", "false", "hayir", "hayır", "no", "off", "h"):
        return False
    return None


def is_cancelled(status: Optional[str], status_id: Any, cancel_list: list[str]) -> bool:
    if cancel_list:
        vals = {str(x).strip().casefold() for x in cancel_list}
        return (status or "").strip().casefold() in vals or str(status_id or "").strip() in vals
    # «İ» küçültülünce noktalı iki harfe dönüşür; önce düz «i» yapılır, sonra harf büyüklüğü katlanır.
    return bool(status and CANCEL_RE.search(status.replace("İ", "i").casefold()))


# ------------------------------------------------------------------ kişisel alan → özet


@dataclass
class Person:
    """Bir sipariş/üye kaydının kişisel alanlarının yalnız özeti (ham değer yok)."""
    email_hash: Optional[str] = None
    phone_hash: Optional[str] = None
    name_hash: Optional[str] = None
    city: Optional[str] = None


def person_of(row: dict[str, Any], f: dict[str, list[str]], key: bytes) -> Person:
    _, email = pick(row, f["email"])
    _, phone = pick(row, f["phone"])
    _, name = pick(row, f["name"])
    if not name:
        _, fn = pick(row, f["first_name"])
        _, ln = pick(row, f["last_name"])
        name = " ".join(str(x) for x in (fn, ln) if x) or None
    _, city = pick(row, f["city"])
    nm = R.norm_name(name)
    return Person(email_hash=R.email_key(email, key), phone_hash=R.phone_key(phone, key),
                  name_hash=R.digest("n", nm, key) if nm else None,
                  city=(re.sub(r"\s+", " ", str(city)).strip()[:80] or None) if city else None)


def customer_key(member_id: Any, p: Person, key: bytes) -> Optional[str]:
    """Müşteri anahtarı (tuzlu özet): e-posta → üye numarası → telefon. Aynı e-postayla misafir ve üye siparişleri
    tek müşteride birleşir. Ham değerden türetilmez; e-posta/telefon özetinden türetilir (ayrı ad alanı «c»)."""
    if p.email_hash:
        return R.digest("c", "e:" + p.email_hash, key)
    mid = str(member_id or "").strip()
    if mid and mid not in ("0", "-1"):
        return R.digest("c", "m:" + mid, key)
    if p.phone_hash:
        return R.digest("c", "p:" + p.phone_hash, key)
    return None


@dataclass
class OrderRec:
    order_no: str
    ordered_at: Optional[datetime]
    status: Optional[str]
    valid: bool
    total: float
    discount: Optional[float]
    shipping: Optional[float]
    coupon: Optional[str]
    payment: Optional[str]
    utm_source: Optional[str]
    utm_campaign: Optional[str]
    customer_key: Optional[str]
    member_ref: Optional[str]
    is_guest: bool
    person: Person
    lines: list[dict[str, Any]] = field(default_factory=list)


def _s(v: Any, n: int) -> Optional[str]:
    if v is None:
        return None
    s = re.sub(r"\s+", " ", str(v)).strip()
    return s[:n] or None


def order_of(row: dict[str, Any], f: dict[str, list[str]], key: bytes, cancel_list: list[str],
             found: Optional[dict[str, str]] = None) -> Optional[OrderRec]:
    """Ham T-soft sipariş kaydından kişisel alanı ayıklanmış sipariş. Numarası yoksa None."""
    def g(role: str) -> Any:
        k, v = pick(row, f[role])
        if k and found is not None and role not in found:
            found[role] = k
        return v

    no = g("order_no")
    if no in (None, ""):
        return None
    status = _s(g("status"), 60)
    sid = g("status_id")
    mid = g("customer_id")
    guest_flag = truthy(g("is_guest"))
    p = person_of(row, f, key)
    for role in ("email", "phone", "city"):
        k, _v = pick(row, f[role])
        if k and found is not None and role not in found:
            found[role] = k
    lines = []
    raw_lines = g("lines")
    if isinstance(raw_lines, dict):
        raw_lines = list(raw_lines.values())
    for ln in raw_lines if isinstance(raw_lines, list) else []:
        if not isinstance(ln, dict):
            continue
        kb, bc = pick(ln, f["line_barcode"])
        kc, code = pick(ln, f["line_code"])
        kq, qty = pick(ln, f["line_qty"])
        ka, amt = pick(ln, f["line_amount"])
        if found is not None:
            for role, k in (("line_barcode", kb), ("line_code", kc), ("line_qty", kq), ("line_amount", ka)):
                if k and role not in found:
                    found[role] = k
        lines.append({"barcode": ean_key(bc) or _s(bc, 40), "code": _s(code, 80), "qty": num(qty) or 0.0,
                      "amount": num(amt) or 0.0})
    mref = str(mid).strip() if mid not in (None, "", 0, "0") else None
    return OrderRec(
        order_no=str(no).strip()[:60], ordered_at=parse_dt(g("ordered_at")), status=status,
        valid=not is_cancelled(status, sid, cancel_list), total=num(g("total")) or 0.0, discount=num(g("discount")),
        shipping=num(g("shipping")), coupon=_s(g("coupon"), 80), payment=_s(g("payment"), 60),
        utm_source=_s(g("utm_source"), 120), utm_campaign=_s(g("utm_campaign"), 160),
        customer_key=customer_key(mref, p, key), member_ref=mref,
        is_guest=bool(guest_flag) if guest_flag is not None else mref is None, person=p, lines=lines)


@dataclass
class MemberRec:
    member_ref: str
    created: Optional[datetime]
    person: Person
    evidences: list[R.Evidence]
    customer_key: Optional[str]


def member_of(row: dict[str, Any], f: dict[str, list[str]], key: bytes, false_is_ret: bool,
              found: Optional[dict[str, str]] = None) -> Optional[MemberRec]:
    k, mid = pick(row, f["member_id"])
    if mid in (None, ""):
        return None
    p = person_of(row, f, key)
    _, created = pick(row, f["member_created"])
    kd, when = pick(row, f["consent_date"])
    at = parse_dt(when) or parse_dt(created)
    at_utc = at.replace(tzinfo=timezone.utc) if at else None
    ev: list[R.Evidence] = []
    for ch, role in (("email", "consent_email"), ("sms", "consent_sms"), ("kvkk", "consent_kvkk")):
        kk, v = pick(row, f[role])
        if kk and found is not None and role not in found:
            found[role] = kk
        t = truthy(v)
        if t is True:
            ev.append(R.Evidence(ch, "izinli", "tsoft", at_utc, kk))
        elif t is False and (false_is_ret or ch == "kvkk"):
            ev.append(R.Evidence(ch, "ret", "tsoft", at_utc, kk))
    if found is not None:
        for role, kk in (("member_id", k), ("consent_date", kd)):
            if kk and role not in found:
                found[role] = kk
    mref = str(mid).strip()
    return MemberRec(member_ref=mref, created=parse_dt(created), person=p, evidences=ev,
                     customer_key=customer_key(mref, p, key))


# ------------------------------------------------------------------ T-soft okuması (yalnız okuma)


def tsoft():
    from semantic_bridge.seo_geo import connections

    return connections.tsoft


def _tsoft_error() -> type:
    from semantic_bridge.seo_geo import connections

    return connections.ConnectionError_


def pages(client: Any, path: str, params: dict[str, Any], page: int = 500) -> Iterator[list[dict[str, Any]]]:
    """Liste yöntemini sonuna kadar okur (boş ya da eksik sayfa gelene kadar). Tavan yok. Aynı sayfa iki kez gelirse
    (sayfalama desteklenmiyorsa) durur ve hata atar — sonsuz döngü ve çift kayıt olmasın."""
    start = 0
    first_ids: Optional[str] = None
    while True:
        data = client.call(path, {**params, "start": start, "limit": page})
        rows = data.get("data") or []
        if isinstance(rows, dict):
            rows = list(rows.values())
        rows = [r for r in rows if isinstance(r, dict)]
        sig = json.dumps(rows[:1], sort_keys=True, default=str)[:400] if rows else ""
        if start and sig and sig == first_ids:
            raise SourceError(f"T-soft {path}: sayfalama çalışmadı (aynı sayfa yeniden geldi).")
        if start == 0:
            first_ids = sig
        if rows:
            yield rows
        if len(rows) < page:
            return
        start += len(rows)


def order_params(conf: Callable[[str, str], str], since: Optional[date]) -> dict[str, Any]:
    raw = (conf("COMMERCE_TSOFT_ORDER_PARAMS", "") or "").strip()
    try:
        params = json.loads(raw) if raw else {}
    except ValueError:
        params = {}
    if not isinstance(params, dict):
        params = {}
    if since is not None:
        p_from = (conf("COMMERCE_TSOFT_DATE_PARAM", "OrderDateTimeStart") or "").strip()
        fmt = conf("COMMERCE_TSOFT_DATE_FORMAT", "%Y-%m-%d") or "%Y-%m-%d"
        if p_from:
            params[p_from] = since.strftime(fmt)
    return params


def read_person(client: Any, conf: Callable[[str, str], str], f: dict[str, list[str]], *, member_ref: Optional[str],
                order_no: Optional[str], expect_email_hash: Optional[str], key: bytes) -> Optional[dict[str, Any]]:
    """Tek kişinin ad/e-posta/telefonu T-soft'tan anlık (yalnız yetkili ekran ve dışa aktarım). Dönen kaydın kimliği ve
    e-posta özeti beklenenle aynı değilse (süzgeç yok sayılmışsa) hiçbir şey döndürmez — başkasının verisi gösterilmez.
    Değerler saklanmaz."""
    tries: list[tuple[str, dict[str, Any], list[str], Optional[str]]] = []
    if member_ref:
        tries.append((conf("COMMERCE_TSOFT_MEMBER_PATH", "customer/get") or "customer/get",
                      {conf("COMMERCE_TSOFT_MEMBER_ID_PARAM", "CustomerId") or "CustomerId": member_ref}, f["member_id"], member_ref))
    if order_no:
        tries.append((conf("COMMERCE_TSOFT_ORDER_PATH", "order/get") or "order/get",
                      {conf("COMMERCE_TSOFT_ORDER_ID_PARAM", "OrderCode") or "OrderCode": order_no}, f["order_no"], order_no))
    for path, params, id_roles, want in tries:
        try:
            data = client.call(path, {**params, "start": 0, "limit": 5})
        except Exception as e:  # noqa: BLE001 — bağlantı hatası bir sonraki yolu denemeyi engellemez
            log.info("commerce: kişi bilgisi okunamadı (%s): %s", path, e)
            continue
        rows = data.get("data") or []
        for r in rows if isinstance(rows, list) else []:
            if not isinstance(r, dict):
                continue
            _, rid = pick(r, id_roles)
            if str(rid or "").strip() != str(want):
                continue
            _, email = pick(r, f["email"])
            if expect_email_hash and R.email_key(email, key) != expect_email_hash:
                continue
            _, phone = pick(r, f["phone"])
            _, name = pick(r, f["name"])
            if not name:
                _, fn = pick(r, f["first_name"])
                _, ln = pick(r, f["last_name"])
                name = " ".join(str(x) for x in (fn, ln) if x) or None
            consent = {}
            for ch, role in (("email", "consent_email"), ("sms", "consent_sms")):
                _, v = pick(r, f[role])
                consent[ch] = truthy(v)
            return {"ad": _s(name, 200), "eposta": R.norm_email(email), "cep": R.norm_phone(phone), "izin": consent}
    return None


# ------------------------------------------------------------------ portal tablolarından okuma (SEO, H1)


def _table(engine: sa.engine.Engine, name: str) -> Optional[sa.Table]:
    try:
        if not sa.inspect(engine).has_table(name):
            return None
        return sa.Table(name, sa.MetaData(), autoload_with=engine)
    except Exception as e:  # noqa: BLE001
        log.info("commerce: %s okunamadı: %s", name, e)
        return None


def site_products(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    """SEO eşitlemesinin son ürün hâli: barkod, ad, toplam görüntülenme, toplam satış (T-soft sayacı)."""
    t = _table(engine, "semantic_seo_products")
    if t is None:
        return []
    out = []
    with engine.connect() as c:
        for r in c.execute(sa.select(t.c.product_id, t.c.name, t.c.data_json, t.c.synced_at).where(t.c.tenant_id == tenant)):
            try:
                d = json.loads(r.data_json or "{}")
            except ValueError:
                d = {}
            _, bc = pick(d, ["Barcode", "ProductBarcode", "Ean"])
            _, views = pick(d, ["StatViews", "ViewCount", "Views"])
            _, sold = pick(d, ["CountTotalSales", "TotalSales"])
            out.append({"product_id": str(r.product_id), "barcode": ean_key(bc), "name": r.name,
                        "views": int(num(views) or 0) if views is not None else None,
                        "sold_total": num(sold), "synced_at": r.synced_at})
    return out


def book_index(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    """Barkod → kitap (kimlik, ad, düğüm, CRM oluşturma günü) ve yürürlükteki ağacın düğümleri. H1 yoksa SEO'nun CRM
    kitap eşlemesi (düğümsüz)."""
    books: dict[str, dict[str, Any]] = {}
    nodes: dict[str, dict[str, Any]] = {}
    source = "yok"
    prof = _table(engine, "semantic_book_profiles")
    if prof is not None:
        with engine.connect() as c:
            for r in c.execute(sa.select(prof.c.ean, prof.c.book_id, prof.c.name, prof.c.node_id, prof.c.resolved_node_id,
                                         prof.c.crm_created_at, prof.c.active).where(prof.c.tenant_id == tenant)):
                e = ean_key(r.ean)
                if e:
                    books[e] = {"bookId": r.book_id, "name": r.name, "node": r.node_id or r.resolved_node_id,
                                "created": (str(r.crm_created_at or "")[:10] or None), "active": bool(r.active)}
        if books:
            source = "h1"
        try:
            from semantic_bridge import categories as H1

            tree = H1.in_force(engine, tenant)
            if tree:
                for n in H1.nodes_of(engine, tree["id"]):
                    nodes[n["id"]] = {"id": n["id"], "name": n["name"], "parent": n.get("parent_id") or n.get("parentId"),
                                      "level": n.get("level")}
        except Exception as e:  # noqa: BLE001 — H1 ağacı yoksa ilgi alanı çalışmaz, satış okuması sürer
            log.info("commerce: kategori ağacı okunamadı: %s", e)
    if not books:
        crm = _table(engine, "semantic_seo_crm_books")
        if crm is not None:
            with engine.connect() as c:
                for r in c.execute(sa.select(crm.c.ean, crm.c.book_id, crm.c.name).where(crm.c.tenant_id == tenant)):
                    e = ean_key(r.ean)
                    if e:
                        books[e] = {"bookId": r.book_id, "name": r.name, "node": None, "created": None, "active": True}
            if books:
                source = "seo"
    return {"books": books, "nodes": nodes, "source": source}


def node_at_level(nodes: dict[str, dict[str, Any]], node_id: Optional[str], level: str) -> Optional[str]:
    """Düğümün istenen düzeydeki atası (kendisi o düzeydeyse kendisi). `level` = «yaprak» ise olduğu gibi."""
    if not node_id or level == "yaprak":
        return node_id
    seen: set[str] = set()
    cur = node_id
    while cur and cur in nodes and cur not in seen:
        seen.add(cur)
        if nodes[cur].get("level") == level:
            return cur
        cur = nodes[cur].get("parent")
    return node_id


def day_range(d: date) -> tuple[datetime, datetime]:
    return datetime(d.year, d.month, d.day), datetime(d.year, d.month, d.day) + timedelta(days=1)


def chunks(items: list[Any], n: int = 500) -> Iterable[list[Any]]:
    for i in range(0, len(items), n):
        yield items[i:i + n]
