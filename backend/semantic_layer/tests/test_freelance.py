"""Serbest çalışanlar (M8): kayıt, portfolyo, paket/görev, toplu dağıtım önerisi, kapasite, teslim, hakediş, yazışma."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from semantic_bridge import access as A
from semantic_bridge import freelance as F
from semantic_bridge import freelance_logo as L
from semantic_layer.store.catalog_store import open_store

T = "t1"
# Pazartesi 2026-09-28, İstanbul öğlen.
TODAY = date(2026, 9, 28)
NOW = datetime(2026, 9, 28, 9, 0, tzinfo=timezone.utc)
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture
def engine(monkeypatch, tmp_path):
    monkeypatch.setattr(F, "_today", lambda: TODAY)
    monkeypatch.setattr(F, "_now", lambda: NOW)
    monkeypatch.setenv("FREELANCE_DIR", str(tmp_path))
    e = open_store("sqlite://").engine
    F._ready.discard(id(e))
    F.ensure(e)
    return e


def _person(engine, name="Ayşe Çizer", roles=("cizer",), hours=20, **kw):
    return F.create_person(engine, T, "editor1", {"name": name, "roles": list(roles), "weeklyHours": hours, **kw})


def _package(engine, tasks, role="cizer", due="2026-10-09", title="Gökyüzü — iç resimler"):
    return F.create_package(engine, T, "editor1", {"title": title, "role": role, "due": due, "bookTitle": "Gökyüzü",
                                                   "tasks": tasks})


def _tasks(engine, package_id):
    return F.get_package(engine, T, package_id)["tasks"]


# ---------------------------------------------------------------------------------------------- kayıt

def test_person_validation_and_duplicates(engine):
    with pytest.raises(F.FreelanceError, match="rol"):
        F.create_person(engine, T, "u", {"name": "X", "roles": []})
    with pytest.raises(F.FreelanceError, match="E-posta"):
        _person(engine, email="yanlis")
    p = _person(engine, email="Ayse@Ornek.com", styles=["suluboya", "Suluboya", "çocuk"],
                rates=[{"role": "cizer", "unit": "çizim", "price": "1.250,5".replace(".", "")}])
    assert p["email"] == "ayse@ornek.com"
    assert p["styles"] == ["suluboya", "çocuk"]
    assert p["rates"] == [{"role": "cizer", "unit": "çizim", "price": 1250.5}]
    with pytest.raises(F.FreelanceError) as e:
        _person(engine, name="Başka", email="ayse@ornek.com")
    assert e.value.status == 409
    crm = "0a1b2c3d-0000-1111-2222-333344445555"
    q = _person(engine, name="CRM'den", crmContactId=crm.upper())
    assert F.lookup_crm(engine, T, [crm, "bozuk"]) == {crm: q["id"]}
    with pytest.raises(F.FreelanceError, match="zaten kayıtlı"):
        _person(engine, name="Yine", crmContactId=crm)


def test_away_ranges_must_be_ordered(engine):
    with pytest.raises(F.FreelanceError, match="önce"):
        _person(engine, away=[{"from": "2026-10-10", "to": "2026-10-01"}])


def test_portfolio_checks_content_and_deletes_file(engine, tmp_path):
    p = _person(engine)
    with pytest.raises(F.FreelanceError, match="uyuşmuyor"):
        F.add_portfolio(engine, T, "u", p["id"], "resim.png", b"not a png", {})
    with pytest.raises(F.FreelanceError, match="JPG"):
        F.add_portfolio(engine, T, "u", p["id"], "resim.exe", PNG, {})
    f = F.add_portfolio(engine, T, "u", p["id"], "kapak.png", PNG, {"tags": ["kapak", "dijital"], "book": "Gökyüzü"})
    assert f["title"] == "kapak" and f["tags"] == ["kapak", "dijital"]
    path, name, mime = F.portfolio_file(engine, T, f["id"])
    assert mime == "image/png" and path.startswith(str(tmp_path))
    listed = F.list_people(engine, T)["items"][0]
    assert listed["preview"] == [f["id"]]
    F.delete_portfolio(engine, T, f["id"])
    with pytest.raises(F.FreelanceError):
        F.portfolio_file(engine, T, f["id"])


# ---------------------------------------------------------------------------------------------- paket, atama, kapasite

def test_package_tasks_default_effort_and_price(engine):
    pkg = _package(engine, [{"title": "Bölüm 1–4", "units": 8, "unitPrice": 1500}])
    [t] = _tasks(engine, pkg["id"])
    assert t["effortHours"] == 48.0            # 8 çizim × 6 saat (rol varsayılanı)
    assert t["amount"] == 12000.0 and t["unit"] == "çizim" and t["due"] == "2026-10-09"
    with pytest.raises(F.FreelanceError, match="en az bir"):
        _package(engine, [])
    with pytest.raises(F.FreelanceError, match="Termin"):
        _package(engine, [{"title": "x", "units": 1, "start": "2026-10-10", "due": "2026-10-01"}])


def test_capacity_spreads_remaining_work_and_flags_overload(engine):
    p = _person(engine, hours=20, away=[{"from": "2026-10-05", "to": "2026-10-09"}])
    pkg = _package(engine, [{"title": "A", "units": 1, "effortHours": 30, "start": "2026-09-28", "due": "2026-10-02"}])
    [t] = _tasks(engine, pkg["id"])
    F.assign(engine, T, "editor1", [{"taskId": t["id"], "personId": p["id"]}])
    cap = F.capacity(engine, T, weeks=3)
    row = cap["people"][0]
    w1, w2, w3 = row["weeks"]
    assert (w1["capacity"], w1["load"], w1["ratio"]) == (20.0, 30.0, 1.5)
    assert w2["capacity"] == 0.0 and w2["away"] is True     # bütün hafta müsait değil
    assert w3["capacity"] == 20.0 and w3["load"] == 0.0


def test_overdue_work_lands_on_today(engine):
    p = _person(engine)
    pkg = _package(engine, [{"title": "Geciken", "units": 1, "effortHours": 12, "start": "2026-09-14", "due": "2026-09-18"}])
    [t] = _tasks(engine, pkg["id"])
    F.assign(engine, T, "editor1", [{"taskId": t["id"], "personId": p["id"]}])
    daily = F.load_by_day([_row(engine, t["id"])], [], TODAY)
    assert daily == {TODAY: 12.0}
    assert F.overview(engine, T, "editor1")["tasks"]["late"] == 1


def _row(engine, task_id):
    import sqlalchemy as sa
    with engine.connect() as c:
        return c.execute(sa.select(F.TASKS).where(F.TASKS.c.id == task_id)).first()


def test_suggest_prefers_free_people_and_does_not_pile_up(engine):
    busy = _person(engine, name="Dolu Kişi", hours=20)
    free1 = _person(engine, name="Boş Bir", hours=20)
    free2 = _person(engine, name="Boş İki", hours=20)
    _person(engine, name="Mizanpajcı", roles=("mizanpaj",), hours=40)
    old = _package(engine, [{"title": "Eski iş", "units": 1, "effortHours": 20, "start": "2026-09-28", "due": "2026-10-02"}])
    F.assign(engine, T, "editor1", [{"taskId": _tasks(engine, old["id"])[0]["id"], "personId": busy["id"]}])
    pkg = _package(engine, [{"title": f"Parça {i}", "units": 1, "effortHours": 16, "start": "2026-09-28", "due": "2026-10-02"}
                            for i in (1, 2)])
    ids = [t["id"] for t in _tasks(engine, pkg["id"])]
    out = F.suggest(engine, T, ids)
    picks = [o["suggested"] for o in out]
    assert set(picks) == {free1["id"], free2["id"]}          # ikisi aynı kişiye yığılmaz
    assert all(c["name"] != "Mizanpajcı" for o in out for c in o["candidates"])
    assert out[0]["candidates"][-1]["name"] == "Dolu Kişi" and not out[0]["candidates"][-1]["fits"]


def test_assignment_rules(engine):
    p = _person(engine)
    off = _person(engine, name="Pasif")
    F.update_person(engine, T, "u", off["id"], {"status": "pasif"})
    pkg = _package(engine, [{"title": "A", "units": 2}])
    [t] = _tasks(engine, pkg["id"])
    with pytest.raises(F.FreelanceError, match="pasif"):
        F.assign(engine, T, "u", [{"taskId": t["id"], "personId": off["id"]}])
    done = F.assign(engine, T, "u", [{"taskId": t["id"], "personId": p["id"]}])
    assert done[0]["name"] == p["name"] and _tasks(engine, pkg["id"])[0]["status"] == "atandi"
    with pytest.raises(F.FreelanceError, match="Yalnız atanmamış"):
        F.delete_task(engine, T, "u", t["id"])
    F.assign(engine, T, "u", [{"taskId": t["id"], "personId": None}])
    assert _tasks(engine, pkg["id"])[0]["status"] == "atanmadi"


# ---------------------------------------------------------------------------------------------- teslim ve hakediş

def _accepted(engine, person, title="Kapak", units=1, price=4000, role="kapak"):
    pkg = _package(engine, [{"title": title, "units": units, "unitPrice": price}], role=role, title=f"{title} paketi")
    [t] = _tasks(engine, pkg["id"])
    F.assign(engine, T, "editor1", [{"taskId": t["id"], "personId": person["id"]}])
    d = F.add_delivery(engine, T, "editor1", t["id"], link="https://example.com/kapak.pdf")
    F.decide_delivery(engine, T, "editor1", d["id"], {"decision": "kabul"})
    return pkg, t


def test_delivery_revision_then_accept(engine):
    p = _person(engine, roles=("kapak",))
    pkg = _package(engine, [{"title": "Kapak", "units": 1, "unitPrice": 4000}], role="kapak")
    [t] = _tasks(engine, pkg["id"])
    with pytest.raises(F.FreelanceError, match="beklemiyor"):
        F.add_delivery(engine, T, "u", t["id"], link="https://x.y/1")
    F.assign(engine, T, "u", [{"taskId": t["id"], "personId": p["id"]}])
    with pytest.raises(F.FreelanceError, match="http"):
        F.add_delivery(engine, T, "u", t["id"], link="ftp://x")
    d1 = F.add_delivery(engine, T, "u", t["id"], filename="kapak.pdf", data=b"%PDF-1.7 ...", note="ilk")
    with pytest.raises(F.FreelanceError, match="incelenmedi"):
        F.add_delivery(engine, T, "u", t["id"], link="https://x.y/2")
    with pytest.raises(F.FreelanceError, match="düzeltileceği"):
        F.decide_delivery(engine, T, "u", d1["id"], {"decision": "revizyon"})
    F.decide_delivery(engine, T, "u", d1["id"], {"decision": "revizyon", "note": "Başlık büyüsün"})
    d2 = F.add_delivery(engine, T, "u", t["id"], link="https://x.y/2")
    assert d2["version"] == 2
    F.decide_delivery(engine, T, "u", d2["id"], {"decision": "kabul"})
    [t] = _tasks(engine, pkg["id"])
    assert t["status"] == "onaylandi" and t["revisions"] == 1 and len(t["deliveries"]) == 2
    path, name = F.delivery_file(engine, T, d1["id"])
    assert name == "kapak.pdf"
    with pytest.raises(F.FreelanceError, match="bağlantı"):
        F.delivery_file(engine, T, d2["id"])
    person = F.get_person(engine, T, p["id"])
    assert person["stats"]["onTimeRate"] == 1.0 and person["stats"]["payable"] == 4000.0


def test_payout_flow_with_two_eyes(engine):
    p = _person(engine, roles=("kapak",), logoCard="320.01.001")
    _accepted(engine, p, "Kapak A", price=4000)
    _accepted(engine, p, "Kapak B", units=2, price=1250.555)
    [group] = F.payable(engine, T)
    assert group["total"] == 6501.12 and len(group["tasks"]) == 2
    out = F.create_payout(engine, T, "editor1", {"personId": p["id"]})
    assert out["no"] == 1 and out["total"] == 6501.12
    assert F.payable(engine, T) == []
    with pytest.raises(F.FreelanceError, match="Yalnız onay bekleyen"):
        F.payout_action(engine, T, "mudur", out["id"], "approve", {}, True)
    F.payout_action(engine, T, "editor1", out["id"], "submit", {}, False)
    with pytest.raises(F.FreelanceError) as e:
        F.payout_action(engine, T, "mudur", out["id"], "approve", {}, False)
    assert e.value.status == 403
    with pytest.raises(F.FreelanceError, match="başka biri"):
        F.payout_action(engine, T, "editor1", out["id"], "approve", {}, True)
    F.payout_action(engine, T, "mudur", out["id"], "approve", {}, True)
    with pytest.raises(F.FreelanceError, match="belge"):
        F.payout_action(engine, T, "mudur", out["id"], "pay", {"paidOn": "2026-09-25"}, True)
    with pytest.raises(F.FreelanceError, match="ileri"):
        F.payout_action(engine, T, "mudur", out["id"], "pay", {"paidOn": "2026-10-25", "paidRef": "x"}, True)
    F.payout_action(engine, T, "mudur", out["id"], "pay", {"paidOn": "2026-09-25", "paidRef": "Havale 4471"}, True)
    got = F.get_payout(engine, T, out["id"])
    assert got["status"] == "odendi" and got["paidRef"] == "Havale 4471" and len(got["lines"]) == 2
    name, data = F.payout_csv(engine, T, out["id"])
    assert name == "hakedis-1-Ayse-Cizer.csv"
    text = data.decode("utf-8-sig")
    assert "320.01.001" in text and "6501,12" in text and "Ödendi" in text
    # Satırlar dondurulur: görevin ücreti sonradan değişemez.
    with pytest.raises(F.FreelanceError, match="Hakedişe girmiş"):
        F.update_task(engine, T, "u", got["lines"][0]["taskId"], {"unitPrice": 1})


def test_draft_delete_releases_the_work(engine):
    p = _person(engine, roles=("kapak",))
    _accepted(engine, p)
    out = F.create_payout(engine, T, "editor1", {"personId": p["id"]})
    F.payout_action(engine, T, "editor1", out["id"], "submit", {}, False)
    with pytest.raises(F.FreelanceError, match="nedeni"):
        F.payout_action(engine, T, "mudur", out["id"], "return", {}, True)
    F.payout_action(engine, T, "mudur", out["id"], "return", {"note": "Fatura gelmedi"}, True)
    assert F.get_payout(engine, T, out["id"])["returnNote"] == "Fatura gelmedi"
    F.payout_action(engine, T, "editor1", out["id"], "delete", {}, False)
    assert len(F.payable(engine, T)) == 1
    again = F.create_payout(engine, T, "editor1", {"personId": p["id"]})
    assert again["no"] == 2


def test_cancel_package_blocked_by_payout(engine):
    p = _person(engine, roles=("kapak",))
    pkg, _ = _accepted(engine, p)
    F.create_payout(engine, T, "editor1", {"personId": p["id"]})
    with pytest.raises(F.FreelanceError, match="iptal edilemez"):
        F.update_package(engine, T, "u", pkg["id"], {"status": "iptal"})


# ---------------------------------------------------------------------------------------------- yazışma

def test_messages_unread_and_email(engine):
    p = _person(engine, email="ayse@ornek.com")
    nomail = _person(engine, name="Adresi Yok")
    pkg = _package(engine, [{"title": "A", "units": 1}, {"title": "B", "units": 1}])
    a, b = _tasks(engine, pkg["id"])
    F.assign(engine, T, "editor1", [{"taskId": a["id"], "personId": p["id"]}, {"taskId": b["id"], "personId": nomail["id"]}])
    th = f"p:{pkg['id']}"
    sent: list[dict] = []
    out = F.post_message(engine, T, "editor1", "Editör Bir", th, {"kind": "giden", "body": "Merhaba", "personId": p["id"]},
                         lambda m: sent.append(m) or "gonderildi")
    assert out["emailStatus"] == "gonderildi" and sent[0]["to"] == "ayse@ornek.com" and sent[0]["subject"] == pkg["title"]
    assert F.post_message(engine, T, "editor1", "Editör Bir", th, {"kind": "giden", "body": "x", "personId": nomail["id"]},
                          lambda m: "gonderildi")["emailStatus"] == "adres-yok"
    assert F.post_message(engine, T, "editor1", "Editör Bir", th, {"kind": "giden", "body": "x", "personId": p["id"]},
                          None)["emailStatus"] == "ayar-yok"
    stranger = _person(engine, name="Pakette Yok")
    with pytest.raises(F.FreelanceError, match="görevli değil"):
        F.post_message(engine, T, "editor1", "E", th, {"kind": "gelen", "body": "x", "personId": stranger["id"]})
    F.post_message(engine, T, "editor1", "E", th, {"kind": "gelen", "body": "Tamam, cuma teslim", "personId": p["id"]})
    # Yazan için okunmamış yok; başka ekip üyesine iletiler (sistem satırları hariç) okunmamış.
    assert F.inbox(engine, T, "editor1")["unread"] == 0
    other = F.inbox(engine, T, "editor2")
    assert other["unread"] == 4 and other["items"][0]["title"] == pkg["title"]
    view = F.thread(engine, T, "editor2", th)
    assert [m["kind"] for m in view["messages"]].count("sistem") == 3        # açıldı + iki atama
    gelen = [m for m in view["messages"] if m["kind"] == "gelen"][0]
    assert gelen["authorDisplay"] == p["name"]
    assert {r["name"] for r in view["recipients"]} == {p["name"], nomail["name"]}
    assert F.inbox(engine, T, "editor2")["unread"] == 0
    with pytest.raises(F.FreelanceError):
        F.thread(engine, T, "editor2", "x:bozuk")


# ---------------------------------------------------------------------------------------------- Logo ve yetki

def test_logo_sql_is_read_only_and_escaped():
    sql = L.cards_sql("O'Neil%")
    assert sql.startswith("SELECT TOP 40") and "O''Neil[%]" in sql and "LG_411_CLCARD" in sql
    assert "N'ÇİZER'" in L.cards_sql("")
    lines = L.lines_sql("320.01.001")
    assert "LG_411_01_CLFLINE" in lines and "L.CANCELLED = 0" in lines and "'20260101'" in lines
    with pytest.raises(L.LogoError):
        L.lines_sql("x'; DROP TABLE y--")


def test_logo_movements_sum_sides():
    calls = []

    def run(sql):
        calls.append(sql)
        if "TOP 1" in sql:
            return {"records": [{"CODE": "320.01.001", "DEFINITION_": "Ayşe Çizer", "SPECODE": "ÇİZER"}]}
        return {"records": [{"DAY": "2026-07-01", "TRCODE": 46, "SIGN": 1, "AMOUNT": 5000, "NO": "SM1"},
                            {"DAY": "2026-07-10", "TRCODE": 21, "SIGN": 0, "AMOUNT": 4000}], "dbMs": 12}

    out = L.movements(run, "320.01.001")
    assert out["credit"] == 5000 and out["debit"] == 4000 and out["balance"] == 1000
    assert out["lines"][0]["type"] == "Alınan serbest meslek makbuzu" and out["lines"][1]["side"] == "borc"


def test_logo_movements_read_every_line_and_never_sum_a_cut_list():
    """Sessiz tavan yok: yılın bütün hareketleri okunur; okuma güvenlik sınırı aşılırsa yarım toplam gösterilmez."""
    assert "TOP" not in L.lines_sql("320.01.001")

    def run(sql):
        if "TOP 1" in sql:
            return {"records": [{"CODE": "320.01.001", "DEFINITION_": "Ayşe Çizer", "SPECODE": "ÇİZER"}]}
        return {"records": [{"DAY": "2026-07-01", "TRCODE": 46, "SIGN": 1, "AMOUNT": 5000}], "truncated": True}

    with pytest.raises(L.LogoError) as e:
        L.movements(run, "320.01.001")
    assert e.value.status == 413


def test_access_rules_for_freelance():
    page = A.page("serbest-calisanlar")
    assert A.rule_for("/api/v1/editorial/freelance/people") == frozenset({page})
    assert A.page("kisiler") in A.rule_for("/api/v1/editorial/freelance/lookup")
    assert page in A.rule_for("/api/v1/editorial/contributors")
    assert A.features_for("POST", "/api/v1/editorial/freelance/people") == ["ozellik:serbest.yonet"]
    assert A.features_for("POST", "/api/v1/editorial/freelance/payouts/x/submit") == ["ozellik:serbest.yonet"]
    # Onay/ödeme açıkça verilen yetkiyle ucun içinde denetlenir; yazışma ve öneri sayfayla gelir.
    assert A.features_for("POST", "/api/v1/editorial/freelance/payouts/x/approve") == []
    assert A.features_for("POST", "/api/v1/editorial/freelance/threads/p:1/messages") == []
    assert A.features_for("POST", "/api/v1/editorial/freelance/suggest") == []
    assert A.features_for("GET", "/api/v1/editorial/freelance/payouts/x/export.csv") == ["ozellik:veri.disa-aktar"]
    explicit = {f["key"] for f in A.catalog()["features"] if f.get("explicit")}
    assert "ozellik:serbest.hakedis-onay" in explicit


def test_unwritable_storage_is_a_plain_error(engine, monkeypatch, tmp_path):
    blocker = tmp_path / "dosya"
    blocker.write_text("klasör değil")
    monkeypatch.setenv("FREELANCE_DIR", str(blocker))
    p = _person(engine)
    with pytest.raises(F.FreelanceError) as e:
        F.add_portfolio(engine, T, "u", p["id"], "kapak.png", PNG, {})
    assert e.value.status == 503 and "kaydedilemedi" in str(e.value)
