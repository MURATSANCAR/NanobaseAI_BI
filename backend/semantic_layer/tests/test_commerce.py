"""H3 E-ticaret müşteri yönetimi: kişisel alan ayıklama (özet, ham değer yok), iptal/iade ayrımı, müşteri anahtarı
(misafir + üye aynı e-postayla tek müşteri), sayfalama (tavansız, tekrar eden sayfada durma), RFM segmenti ve geçiş,
tetik adayları, H2 bağlantısı (site üyesi okur olur, izin kararı H2'nin), kontrol grubu ayrımı (tam oran, deterministik),
iki göz onayı, kontrol grubunun dışa aktarılmaması, kampanya sonucu ve güven aralığı, M42 D2C özeti, yetki kuralları,
portal tablolarında kişisel veri olmaması.

Veriler yapaydır ve yalnız kuralları sınar; gerçek T-soft/Logo kabulü test sunucusunda (`scripts/acceptance/H3/`).
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime, timedelta

import pytest
import sqlalchemy as sa

from semantic_bridge import access as A
from semantic_bridge import commerce as C
from semantic_bridge import commerce_sources as src
from semantic_bridge import readers as R
from semantic_bridge import readers_segments as S
from semantic_bridge.seo_geo import connections
from semantic_layer.store.catalog_store import open_store

T = "t1"
SALT = "test-tuzu-en-az-16-karakter"
KEY = SALT.encode()
TODAY = date(2026, 9, 28)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("READERS_HASH_SALT", SALT)
    monkeypatch.setenv("READERS_CONSENT_SOURCES", "iys,tsoft")
    monkeypatch.setenv("READERS_REQUIRE_KVKK", "0")
    monkeypatch.setenv("READERS_EXPORT_ENABLED", "1")
    yield
    R._PROVIDERS.pop(C.SOURCE, None)
    R.ADDRESS_SOURCES.discard(C.SOURCE)
    C.FACTS.bound = None


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    R._ready.discard(id(e))
    C._ready.discard(id(e))
    R.ensure(e)
    C.ensure(e)
    return e


def conf(over=None):
    over = over or {}
    return lambda k, d="": over.get(k, d)


def order(no, when, total, *, member=None, email=None, phone=None, status="Onaylandı", lines=(), name="Ayşe Yılmaz", city="İstanbul"):
    return {"OrderCode": no, "OrderDateTime": when, "OrderStatus": status, "OrderTotalPrice": total, "CustomerId": member,
            "CustomerEmail": email, "CustomerGsm": phone, "CustomerName": name, "CustomerCity": city,
            "OrderDetails": [{"Barcode": b, "Quantity": q, "TotalPrice": a} for b, q, a in lines]}


def member(mid, email, perm=1):
    return {"CustomerId": mid, "Email": email, "Name": "Üye", "Surname": "Kişi", "EmailPermission": perm,
            "RegisterDate": "2024-01-01 10:00:00"}


ORDERS = [
    order("O1", "2026-09-20 10:00:00", 100, member=11, email="a@x.com", lines=[("9786050000011", 2, 100)]),
    order("O2", "2026-05-01 10:00:00", 50, member=11, email="A@X.com "),
    order("O3", "2026-03-01 10:00:00", 80, email="b@y.com", lines=[("9786050000011", 1, 80)]),
    order("O4", "2026-09-27 10:00:00", 70, member=12, email="c@z.com", status="İptal edildi"),
    order("O5", "2026-09-10 10:00:00", 40, member=13, email="d@w.com", phone="0532 111 22 33"),
    order("O6", "2026-09-01 10:00:00", 30, member=14, email="e@v.com"),
    order("O7", "2026-08-15 10:00:00", 30, member=14, email="e@v.com"),
    order("O8", "2026-08-01 10:00:00", 30, member=14, email="e@v.com"),
    order("O9", "2026-07-15 10:00:00", 30, member=14, email="e@v.com"),
]
MEMBERS = [member(11, "a@x.com"), member(12, "c@z.com", 0), member(13, "d@w.com"), member(14, "e@v.com")]


class FakeTsoft:
    """Yalnız okuma yöntemlerini kabul eden sahte istemci (gerçeğiyle aynı `READ_ONLY` deseni)."""

    def __init__(self, orders=ORDERS, members=MEMBERS, ignore_start=False):
        self.orders, self.members, self.ignore_start = list(orders), list(members), ignore_start
        self.calls = []

    def call(self, path, params=None):
        assert connections.READ_ONLY.match(path), path
        self.calls.append(path)
        rows = self.orders if path.startswith("order/") else self.members
        start = 0 if self.ignore_start else int(params.get("start", 0))
        return {"success": True, "data": rows[start:start + int(params.get("limit", 500))]}


def _sync(engine, **kw):
    return C.sync(engine, T, FakeTsoft(**kw), conf(), full=True, today=TODAY, key=KEY)


def _key(email):
    return src.customer_key(None, src.Person(email_hash=R.email_key(email, KEY)), KEY)


# ------------------------------------------------------------------ ayıklama


def test_order_strip_keeps_only_hashes():
    f = src.fields(conf())
    o = src.order_of(ORDERS[4], f, KEY, [])
    assert o.valid and o.total == 40 and o.member_ref == "13" and not o.is_guest
    assert o.person.email_hash == R.email_key("d@w.com", KEY) and o.person.phone_hash == R.phone_key("05321112233", KEY)
    dump = repr(o)
    assert "@" not in dump and "111 22 33" not in dump and "Ayşe" not in dump and "Yılmaz" not in dump
    assert src.is_cancelled("IADE EDİLDİ", None, []) and not src.is_cancelled("Kredi kartı onayı bekleniyor", None, [])
    bad = src.order_of(ORDERS[3], f, KEY, [])
    assert not bad.valid
    assert src.order_of(ORDERS[3], f, KEY, ["Onaylandı"]).valid        # ayar listesi verilince yalnız o liste


def test_customer_key_merges_guest_and_member_by_email():
    f = src.fields(conf())
    a1 = src.order_of(ORDERS[0], f, KEY, [])
    a2 = src.order_of(ORDERS[1], f, KEY, [])                          # büyük harf + boşluk
    g = src.order_of(order("G", "2026-01-01", 1, email="a@x.com"), f, KEY, [])
    assert a1.customer_key == a2.customer_key == g.customer_key
    assert g.is_guest and not a1.is_guest
    assert a1.customer_key != R.email_key("a@x.com", KEY)               # ayrı ad alanı
    assert src.order_of({"OrderStatus": "x"}, f, KEY, []) is None       # numarasız kayıt


def test_field_override_and_parsers():
    f = src.fields(conf({"COMMERCE_TSOFT_FIELDS": '{"total": ["Tutar"]}'}))
    assert f["total"] == ["Tutar"] and f["order_no"][0] == "OrderCode"
    assert src.num("1.234,50") == 1234.5 and src.num("1,234.50") == 1234.5 and src.num("") is None
    assert src.parse_dt("28.09.2026 10:15") == datetime(2026, 9, 28, 10, 15)
    assert src.parse_dt("2026-09-28T10:15:00") == datetime(2026, 9, 28, 10, 15)
    assert src.ean_key("978-605-000-0011") == "9786050000011" and src.ean_key("12") is None


def test_pages_reads_to_end_and_stops_on_repeated_page():
    client = FakeTsoft(orders=[order(f"N{i}", "2026-09-01", 1) for i in range(1203)])
    got = [r for p in src.pages(client, "order/get", {}) for r in p]
    assert len(got) == 1203 and client.calls.count("order/get") == 3   # 500 + 500 + 203; tavan yok
    with pytest.raises(src.SourceError):
        list(src.pages(FakeTsoft(orders=[order(f"N{i}", "2026-09-01", 1) for i in range(600)], ignore_start=True),
                       "order/get", {}))


def test_tsoft_client_refuses_writes():
    assert connections.READ_ONLY.match("order/get") and connections.READ_ONLY.match("customer/get")
    for p in ("order/update", "customer/setCustomer", "order/delete"):
        assert not connections.READ_ONLY.match(p)


# ------------------------------------------------------------------ RFM


def test_segment_rules_and_buckets():
    st = {"activeDays": 90, "loyalOrders": 4, "loyalRevenue": 0}
    assert C.segment_of(0, 0, None, st) == "siparissiz"
    assert C.segment_of(1, 10, 5, st) == "ilk"
    assert C.segment_of(2, 10, 5, st) == "aktif"
    assert C.segment_of(4, 10, 5, st) == "sadik"
    assert C.segment_of(9, 10, 91, st) == "kayip"
    assert C.segment_of(2, 1000, 5, {**st, "loyalRevenue": 500}) == "sadik"
    assert [C.r_bucket(d) for d in (0, 30, 31, 90, 180, 365, 366, None)] == [0, 0, 1, 1, 2, 3, 4, 4]
    assert [C.f_bucket(n) for n in (1, 2, 3, 4, 5, 9, 10)] == [0, 1, 2, 2, 3, 3, 4]
    ms = C.m_scores({"a": 10, "b": 20, "c": 30, "d": 40, "e": 50})
    assert ms == {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5}


def test_sync_builds_customers_and_no_personal_data(engine):
    info = _sync(engine)
    assert info["orders"] == 9 and info["invalid"] == 1 and info["members"] == 4 and not info["missing"]
    with engine.connect() as c:
        segs = {r.customer_key: r.segment for r in c.execute(sa.select(C.CUSTOMERS.c.customer_key, C.CUSTOMERS.c.segment))}
        lines = c.execute(sa.select(sa.func.count()).select_from(C.LINES)).scalar()
    assert segs[_key("a@x.com")] == "aktif" and segs[_key("b@y.com")] == "kayip"
    assert segs[_key("c@z.com")] == "siparissiz" and segs[_key("d@w.com")] == "ilk" and segs[_key("e@v.com")] == "sadik"
    assert lines == 2
    # Kabul K6 ile aynı tarama: hiçbir kolonda e-posta ya da cep telefonu biçimli değer yok.
    phone = re.compile(r"^\+?(90)?0?5\d{9}$")
    with engine.connect() as c:
        for t in (C.ORDERS, C.LINES, C.CUSTOMERS, C.MOVES, C.PRODUCT_STATS, C.META):
            for row in c.execute(sa.select(t)):
                for v in row:
                    if isinstance(v, str):
                        assert "@" not in v and not phone.match(re.sub(r"[\s()-]", "", v)), (t.name, v)
    # Kabul K5: aktif müşteri sayısı iki yoldan aynı.
    cut = datetime(2026, 9, 28) - timedelta(days=90)
    with engine.connect() as c:
        a = c.execute(sa.select(sa.func.count()).select_from(C.CUSTOMERS).where(C.CUSTOMERS.c.last_order >= cut)).scalar()
        b = c.execute(sa.select(sa.func.count(sa.distinct(C.ORDERS.c.customer_key))).where(
            C.ORDERS.c.valid.is_(True), C.ORDERS.c.ordered_at >= cut)).scalar()
    assert a == b == 3


def test_segment_moves_recorded(engine):
    _sync(engine)
    more = ORDERS + [order("O10", "2026-09-26 10:00:00", 20, member=13, email="d@w.com")]
    C.sync(engine, T, FakeTsoft(orders=more), conf(), full=True, today=TODAY, key=KEY)
    mv = C.moves(engine, T, 30)
    assert any(x["from"] == "ilk" and x["to"] == "aktif" and x["musteri"] == 1 for x in mv["items"])


def test_overview_and_d2c(engine):
    _sync(engine)
    ov = C.overview(engine, T, C.settings(engine, T, conf()), "ay", today=TODAY)
    # Eylül 1–27: O1, O5, O6 geçerli; O4 iptal.
    assert ov["cur"]["siparis"] == 3 and ov["cur"]["ciro"] == 170 and ov["cur"]["iptal"] == 1
    assert ov["top"][0]["barkod"] == "9786050000011"
    d = C.d2c_site(engine, T, "2026-01-01", "2026-09-31")
    assert d["bagli"] and d["siparis"] == 8 and d["ciro"] == 390 and d["musteri"] == 4


# ------------------------------------------------------------------ tetik, H2, kontrol grubu, dışa aktarım


def test_split_is_exact_and_deterministic():
    keys = [f"k{i}" for i in range(101)]
    t, k = C.split("run1", keys, 0.1)
    assert len(k) == 10 and len(t) == 91 and not set(t) & set(k)
    assert C.split("run1", keys, 0.1) == (t, k) and C.split("run2", keys, 0.1) != (t, k)


def test_trigger_validation(engine):
    st = C.settings(engine, T, conf())
    with pytest.raises(C.CommerceError) as e:
        C.create_trigger(engine, T, "u", {"name": "Sepet", "kind": "terk-sepeti"}, st)
    assert e.value.status == 409
    with pytest.raises(C.CommerceError):
        C.create_trigger(engine, T, "u", {"name": "Geri", "kind": "geri-kazanim", "params": {"minGun": 200, "maxGun": 100}}, st)
    with pytest.raises(C.CommerceError):
        C.create_trigger(engine, T, "u", {"name": "Geri", "kind": "geri-kazanim", "controlShare": 0.9}, st)


def _h2(engine):
    C.FACTS.bind(lambda: engine, lambda: T)
    C.register_h2()
    b = {"contacts": [], "leads": [], "accounts": [], "iys": [], "iysFields": [], "events": {}, "interests": {},
         "contributors": set(), "campaigns": [], "labels": {}, "errors": {}, "readAt": "2026-09-28T03:20:00"}
    return R.sync(engine, T, b, R.settings(), KEY, today=TODAY)


def test_site_members_become_readers_and_consent_is_h2s(engine):
    _sync(engine)
    s = _h2(engine)
    assert s["read"][C.SOURCE] == 5                                   # e-postası olan her site müşterisi/üyesi
    profs = {p["id"]: p for p in R.profiles(engine, T)}
    rmap = C.reader_of(engine, T, [_key("d@w.com"), _key("c@z.com"), _key("b@y.com")])
    cfg = R.settings()
    assert R.exportable(profs[rmap[_key("d@w.com")]], "email", cfg) == (True, None)
    assert R.exportable(profs[rmap[_key("c@z.com")]], "email", cfg)[1] == "ret"       # sitede izin kapalı → ret
    assert R.exportable(profs[rmap[_key("b@y.com")]], "email", cfg)[1] == "izin_yok"  # misafir, kanıt yok
    # H2 segment motoru e-ticaret alanlarını okur.
    mem = S.evaluate({"match": "all", "rules": [{"field": "eticaret_segment", "op": "in", "value": ["Sadık"]}]}, list(profs.values()))
    assert [m["id"] for m in mem] == [rmap.get(_key("e@v.com")) or C.reader_of(engine, T, [_key("e@v.com")])[_key("e@v.com")]]


def test_run_approve_export_and_campaign(engine):
    _sync(engine)
    _h2(engine)
    st = C.settings(engine, T, conf())
    t = C.create_trigger(engine, T, "uzman", {"name": "Herkes", "kind": "geri-kazanim", "controlShare": 0.34,
                                               "params": {"minGun": 1, "maxGun": 400}}, st)
    pv = C.preview(engine, T, t["id"], st, TODAY)
    assert pv["candidates"] == 4 and pv["reachable"] == 3 and pv["excluded"] == {"izin_yok": 1}
    run = C.run_trigger(engine, T, t["id"], "uzman", st, TODAY)
    assert (run["target"], run["control"]) == (2, 1)
    with pytest.raises(C.CommerceError) as e:
        C.export_run(engine, T, run["id"], "crm", "Bülten gönderimi", lambda k: {}, lambda rows: {})
    assert e.value.status == 409                                     # onaysız liste
    with pytest.raises(C.CommerceError) as e:
        C.decide_run(engine, T, run["id"], "uzman", True)
    assert e.value.status == 403                                     # yazan onaylayamaz
    C.decide_run(engine, T, run["id"], "mudur", True)
    site = lambda rows: {r.customer_key: {"ad": "Kişi", "eposta": f"k-{r.customer_key[:6]}@ornek.invalid", "cep": None,
                                          "izin": {"email": True}} for r in rows}
    name, data, rec = C.export_run(engine, T, run["id"], "crm", "Eylül geri kazanım", lambda k: {}, site)
    rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig")), delimiter=";"))
    members = C.run_members(engine, T, run["id"])
    target_readers = {m.reader_id for m in members if m.grp == "hedef"}
    control_readers = {m.reader_id for m in members if m.grp == "kontrol"}
    assert rows[0][2] == "eposta" and {r[0] for r in rows[1:]} == target_readers and not control_readers & {r[0] for r in rows[1:]}
    assert rec["count"] == 2
    ex = S.list_exports(engine, T)["items"][0]
    assert ex["segment"].startswith("E-ticaret") and ex["count"] == 2      # H2 defterinde
    cp = C.create_campaign(engine, T, "uzman", {"runId": run["id"], "start": "2026-09-01", "end": "2026-09-30"}, st)
    res = cp["result"]
    # Doğrudan sorgu: pencere içindeki geçerli sipariş, grup başına.
    lo, hi = datetime(2026, 9, 1), datetime(2026, 10, 1)
    for g in ("hedef", "kontrol"):
        keys = [m.customer_key for m in members if m.grp == g]
        with engine.connect() as c:
            n = c.execute(sa.select(sa.func.count()).select_from(C.ORDERS).where(
                C.ORDERS.c.customer_key.in_(keys), C.ORDERS.c.valid.is_(True), C.ORDERS.c.ordered_at >= lo,
                C.ORDERS.c.ordered_at < hi)).scalar()
        assert res[g]["siparis"] == n and res[g]["kisi"] == len(keys)
    assert "Kontrol grubu 30 kişiden küçük; sonuç güvenilir değil." in res["uyarilar"]


def test_lift_confidence_interval():
    lf = C.lift(1000, 100, 1000, 60)
    assert lf["fark"] == pytest.approx(0.04) and lf["anlamli"]
    assert lf["alt"] == pytest.approx(0.04 - 1.96 * ((0.1 * 0.9 + 0.06 * 0.94) / 1000) ** 0.5, abs=1e-6)
    assert not C.lift(20, 2, 20, 1)["anlamli"]
    assert C.lift(0, 0, 10, 1)["fark"] is None


def test_prompt_guard():
    with pytest.raises(C.CommerceError):
        C.assert_no_personal("iletişim: a@b.com")
    with pytest.raises(C.CommerceError):
        C.assert_no_personal("tel 0532 111 22 33")
    C.assert_no_personal("- Fark istatistiksel olarak anlamlı")


# ------------------------------------------------------------------ yetki


def test_access_rules_for_commerce():
    assert A.rule_for("/api/v1/commerce/overview") == {"sayfa:eticaret-musteri"}
    assert A.rule_for("/api/v1/commerce/run-due") == A.SYSTEM
    assert {"sayfa:kampanya", "sayfa:kanal-d2c"} <= set(A.rule_for("/api/v1/commerce/segments/summary"))
    f = A.features_for
    assert f("POST", "/api/v1/commerce/triggers") == ["ozellik:eticaret.tetik"]
    assert f("PATCH", "/api/v1/commerce/triggers/t1") == ["ozellik:eticaret.tetik"]
    assert f("POST", "/api/v1/commerce/triggers/t1/run") == ["ozellik:eticaret.tetik"]
    assert f("POST", "/api/v1/commerce/campaigns") == ["ozellik:eticaret.tetik"]
    assert f("PUT", "/api/v1/commerce/settings") == ["ozellik:eticaret.ayar"]
    assert f("POST", "/api/v1/commerce/refresh") == ["ozellik:eticaret.ayar"]
    assert f("POST", "/api/v1/commerce/runs/r1/approve") == []            # açıkça verilen, ucun içinde
    assert f("POST", "/api/v1/commerce/runs/r1/export") == ["ozellik:veri.disa-aktar"]
    explicit = A.explicit_keys()
    assert {"ozellik:eticaret.liste-onay", "sayfa:eticaret-musteri"} <= explicit
    assert "ozellik:eticaret.tetik" not in explicit
