"""M28 Kurumsal ilişkiler: kişi/kurum kartı, KVKK alan sınırı, gizli not, temas zamanı, hediye programı (tekrar yok,
iki göz, kamu görevlisi hukuk onayı, CRM sipariş eşitlemesi), hediye önerisi, proje aşaması ve bütçe kapısı, teklif
dosyasında rakamın ve maddenin koddan gelmesi, CRM SQL'inin salt okunur ve kaçışlı olması, yetki kuralları.

Sözleşme: ortak çekirdek (`relations_core`) M7 ile aynı ısıyı verir; CRM'e yazan tek bir SQL yoktur.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from semantic_bridge import access as A
from semantic_bridge import public_affairs as PA
from semantic_bridge import public_affairs_docs as D
from semantic_bridge import public_affairs_sources as S
from semantic_bridge import relations_core as core
from semantic_layer.store.catalog_store import open_store

T = "t1"
GUID = "0A1B2C3D-1111-2222-3333-444455556666"
BOOK = "9f1b2c3d-1111-2222-3333-444455556666"
SCHEMA = "Timas_MSCRM.dbo"
ST = PA.settings_from(lambda k, d="": "")


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    PA._ready.discard(id(e))
    PA.ensure(e)
    yield e
    PA._ready.discard(id(e))


def _day(days: int) -> str:
    return (datetime.now(core.TZ) + timedelta(days=days)).date().isoformat()


# ------------------------------------------------------------------ çekirdek


def test_core_heat_matches_m7_and_accepts_accessors():
    from semantic_bridge import author_relations as R

    now = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)
    ms = [SimpleNamespace(status="yapildi", starts_at=now - timedelta(days=d), tone=t) for d, t in ((90, None), (100, "olumlu"), (130, "olumsuz"))]
    assert R.heat(ms, now) == core.heat(ms, now)
    notes = [SimpleNamespace(at=now - timedelta(days=d), tone=t) for d, t in ((0, "olumlu"),)]
    h = PA.person_heat(notes, now)
    assert h["parts"] == {"recency": 50, "frequency": 10, "tone": 20} and h["band"] == "sicak"
    assert PA.person_heat([], now)["band"] == "yok"
    assert R.RelationError is core.RelationError and R.TZ is core.TZ


# ------------------------------------------------------------------ KVKK


@pytest.mark.parametrize("text", ["İnanç grubu", "Mezhebi", "Siyasi görüş", "Parti üyeliği", "Cemaat", "Etnik köken", "Din", "sendika"])
def test_banned_terms_are_caught(text):
    assert PA.banned_hit(text) is not None


@pytest.mark.parametrize("text", ["Akademi", "Eğitim bilimleri", "Dinleme becerisi", "Tarih", "Partner kurum", "Kamu yönetimi"])
def test_ordinary_fields_pass(text):
    assert PA.banned_hit(text) is None


def test_field_list_rejects_sensitive_classes_and_scan_is_clean(engine):
    fields = PA.list_fields(engine, T)
    assert [f["key"] for f in fields] == [k for k, _ in PA.FIELD_DEFAULTS]
    with pytest.raises(core.RelationError) as e:
        PA.add_field(engine, T, "mudur", {"label": "Siyasi eğilim"}, ST["bannedExtra"])
    assert e.value.status == 422
    with pytest.raises(core.RelationError):
        PA.add_field(engine, T, "mudur", {"label": "Kültür"}, ["kultur"])   # ayardaki ek liste
    assert PA.add_field(engine, T, "mudur", {"label": "Kültür ve sanat"}, [])["key"] == "kultur-ve-sanat"
    with pytest.raises(core.RelationError):
        PA.create_person(engine, T, "ayse", {"name": "Deniz Hoca", "interests": ["Osmanlı tarihi", "cemaat ilişkileri"]})
    PA.create_person(engine, T, "ayse", {"name": "Deniz Hoca", "fieldKey": "akademi", "interests": ["Osmanlı tarihi"]})
    assert PA.kvkk_scan(engine, T)["count"] == 0
    with pytest.raises(core.RelationError, match="onaylı listede"):
        PA.create_person(engine, T, "ayse", {"name": "X Y", "fieldKey": "inanc"})


# ------------------------------------------------------------------ kişi, kurum, not


def test_person_card_one_per_crm_contact(engine):
    p = PA.create_person(engine, T, "ayse", {"name": "Prof.  Deniz Hoca", "crmContactId": GUID, "priority": "kritik",
                                             "isPublicOfficial": True})
    assert p["crmContactId"] == GUID.lower() and p["name"] == "Prof. Deniz Hoca" and p["isPublicOfficial"] is True
    with pytest.raises(core.RelationError) as e:
        PA.create_person(engine, T, "mehmet", {"name": "Başka", "crmContactId": GUID})
    assert e.value.status == 409 and e.value.extra["personId"] == p["id"]
    again, created = PA.person_for_crm(engine, T, "mehmet", {"crmContactId": GUID, "name": "Deniz Hoca"})
    assert again["id"] == p["id"] and created is False
    with pytest.raises(core.RelationError) as e:
        PA.update_person(engine, T, "zeynep", False, p["id"], {"archived": True})
    assert e.value.status == 403


def test_private_note_text_goes_only_to_writer_participants_and_sensitive_role(engine):
    p = PA.create_person(engine, T, "ayse", {"name": "Deniz Hoca"})
    with pytest.raises(core.RelationError, match="İleri tarihli"):
        PA.create_note(engine, T, "ayse", "Ayşe", False, {"personId": p["id"], "date": _day(3), "topic": "x"})
    n = PA.create_note(engine, T, "ayse", "Ayşe", False, {
        "personId": p["id"], "date": _day(-1), "time": "10:00", "topic": "Kurul üyeliği", "text": "gizli ayrıntı",
        "visibility": "ozel", "participants": [{"username": "Mehmet"}], "nextStep": "Kitap gönder", "nextOn": _day(-1)})
    other = PA.person_detail(engine, T, "zeynep", False, p["id"], ST)["timeline"][0]
    assert other["hidden"] is True and other["text"] is None and other["topic"] == "Gizli not" and other["nextStep"] is None
    assert PA.person_detail(engine, T, "mehmet", False, p["id"], ST)["timeline"][0]["text"] == "gizli ayrıntı"
    assert PA.person_detail(engine, T, "zeynep", True, p["id"], ST)["timeline"][0]["text"] == "gizli ayrıntı"
    with pytest.raises(core.RelationError) as e:
        PA.update_note(engine, T, "mehmet", False, n["id"], {"topic": "değişti"})
    assert e.value.status == 403
    done, _ = PA.update_note(engine, T, "mehmet", False, n["id"], {"nextDone": True})
    assert done["nextDone"] is True
    with pytest.raises(core.RelationError):
        PA.update_note(engine, T, "zeynep", False, n["id"], {"nextDone": False})   # metni göremeyen adımı da kapatamaz
    assert PA.home(engine, T, "ayse", ST)["lateSteps"] == 0


def test_due_list_uses_priority_limits(engine):
    crit = PA.create_person(engine, T, "ayse", {"name": "Kritik Kişi", "priority": "kritik"})
    PA.create_person(engine, T, "ayse", {"name": "Yeni Normal"})
    old = PA.create_person(engine, T, "ayse", {"name": "Eski Normal"})
    PA.create_note(engine, T, "ayse", "Ayşe", False, {"personId": old["id"], "date": _day(-200), "topic": "Tanışma"})
    fresh = PA.create_person(engine, T, "ayse", {"name": "Taze", "priority": "kritik"})
    PA.create_note(engine, T, "ayse", "Ayşe", False, {"personId": fresh["id"], "date": _day(-10), "topic": "Görüşme"})
    due = PA.list_people(engine, T, "ayse", ST, scope="zamani")
    assert {x["name"] for x in due["items"]} == {"Kritik Kişi", "Eski Normal"} and due["counts"]["zamani"] == 2
    assert due["items"][0]["id"] == crit["id"]   # hiç temas yok + kritik en üstte


def test_org_card_and_note_on_org(engine):
    o = PA.org_for_place(engine, T, "ayse", {"id": GUID, "name": "Üsküdar Belediyesi", "kurumTipi": 6, "city": "İstanbul"})[0]
    assert o["kind"] == "belediye" and o["crmVisitPlaceId"] == GUID.lower()
    assert PA.org_for_place(engine, T, "ayse", {"id": GUID, "name": "x"})[1] is False
    n = PA.create_note(engine, T, "ayse", "Ayşe", False, {"orgId": o["id"], "date": _day(-1), "time": "09:00", "topic": "Kütüphane"})
    assert n["orgId"] == o["id"] and n["personId"] is None


# ------------------------------------------------------------------ hediye programı


def _gift(engine, person_id, user="ayse", book=BOOK, month="2026-09"):
    return PA.add_gift(engine, T, user, {"personId": person_id, "crmBookId": book, "bookName": "Tarih Kitabı",
                                        "stockCode": "TMS001", "month": month, "reason": "tarih"})


def test_same_book_twice_to_same_person_is_refused(engine):
    p = PA.create_person(engine, T, "ayse", {"name": "Deniz Hoca"})
    g = _gift(engine, p["id"])
    with pytest.raises(core.RelationError) as e:
        _gift(engine, p["id"], month="2026-10")
    assert e.value.status == 409 and e.value.extra["giftId"] == g["id"]
    PA.update_gift(engine, T, "ayse", g["id"], {"status": "iptal"})
    g2 = _gift(engine, p["id"], month="2026-10")      # iptal edilen satır tekrar sayılmaz
    with pytest.raises(core.RelationError):
        PA.update_gift(engine, T, "ayse", g["id"], {"status": "oneri"})   # iptali geri almak tekrarı açardı
    with engine.connect() as c:
        rows = c.execute(PA.GIFTS.select()).fetchall()
    assert PA._duplicate_count(rows) == 0 and g2["status"] == "oneri"


def test_approval_two_eyes_and_public_official_legal_check(engine):
    official = PA.create_person(engine, T, "ayse", {"name": "İl Müdürü", "isPublicOfficial": True})
    plain = PA.create_person(engine, T, "ayse", {"name": "Yazar Dost"})
    g1 = _gift(engine, official["id"])
    g2 = _gift(engine, plain["id"])
    own = PA.approve_gifts(engine, T, "ayse", False, {"ids": [g2["id"]]})
    assert own["done"] == [] and "yazan" in own["skipped"][0]["reason"]
    out = PA.approve_gifts(engine, T, "mudur", False, {"ids": [g1["id"], g2["id"]]})
    assert out["done"] == [g2["id"]] and "hukuk" in out["skipped"][0]["reason"]
    out = PA.approve_gifts(engine, T, "mudur", False, {"ids": [g1["id"]], "legalOk": [g1["id"]]})
    assert out["done"] == [g1["id"]]
    got = PA.list_gifts(engine, T, month="2026-09")
    assert got["counts"]["onayli"] == 2 and all(x["approvedBy"] == "mudur" for x in got["items"])
    assert next(x for x in got["items"] if x["id"] == g1["id"])["legalOk"] is True
    with pytest.raises(core.RelationError):
        PA.update_gift(engine, T, "ayse", g2["id"], {"status": "donus"})   # onaylıdan doğrudan dönüşe geçilmez


def test_crm_order_sync_marks_shipped(engine):
    p = PA.create_person(engine, T, "ayse", {"name": "Deniz Hoca"})
    g = _gift(engine, p["id"])
    PA.approve_gifts(engine, T, "mudur", False, {"ids": [g["id"]]})
    with pytest.raises(core.RelationError):
        PA.update_gift(engine, T, "ayse", g["id"], {"crmOrderNo": "SP'1; DROP"})
    PA.update_gift(engine, T, "ayse", g["id"], {"crmOrderNo": "SP-2026-001"})
    oid = "aaaaaaaa-1111-2222-3333-444455556666"
    seen = []

    def run(sql):
        seen.append(sql)
        assert sql.lstrip().upper().startswith("SELECT")
        if "new_siparissatiriBase ss WHERE" in sql:
            return [{"siparis": oid, "stok_kodu": "tms001", "adet": 1}]
        return [{"id": oid, "no": "SP-2026-001", "tip": 12, "durum": 100000000, "sevk": "2026-09-20T21:00:00"}]

    out = PA.sync_orders(engine, T, run, SCHEMA, ST, {100000000: "Sevk Edildi"})
    assert out == {"checked": 1, "found": 1, "shipped": 1}
    row = PA.list_gifts(engine, T)["items"][0]
    assert row["status"] == "sevk" and row["shippedOn"] == "2026-09-21" and row["crmBookInOrder"] is True
    assert row["crmOrderStatusLabel"] == "Sevk Edildi" and "N'SP-2026-001'" in seen[0]
    fb, _ = PA.update_gift(engine, T, "ayse", g["id"], {"feedback": "Teşekkür etti, derste kullanacak"})
    assert fb["status"] == "donus"


def test_suggestion_is_rule_based_with_reason_and_skips_received(engine):
    a = PA.create_person(engine, T, "ayse", {"name": "Tarihçi", "fieldKey": "akademi", "interests": ["Osmanlı tarihi"],
                                             "priority": "kritik"})
    b = PA.create_person(engine, T, "ayse", {"name": "Eğitimci", "fieldKey": "egitim", "interests": ["okul öncesi"]})
    people = PA.list_people(engine, T, "ayse", ST)["items"]
    books = [{"id": BOOK, "ad": "Osmanlı'da Gündelik Hayat", "turler": "Tarih", "kategoriler": "Tarih > Osmanlı", "ozet": "", "stok_kodu": "X"}]
    out = PA.suggest(people, books, {}, PA.gifts_by_person(engine, T), ST)
    assert [x["personId"] for x in out] == [a["id"]]
    assert "tarih" in out[0]["reason"] and "kritik" in out[0]["reason"]
    assert len(PA.suggest(people, books, {}, PA.gifts_by_person(engine, T), ST, include_all=True)) == 2
    _gift(engine, a["id"])
    assert PA.suggest(people, books, {}, PA.gifts_by_person(engine, T), ST) == []
    assert b["id"] not in [x["personId"] for x in PA.suggest(people, books, {}, PA.gifts_by_person(engine, T), ST)]


# ------------------------------------------------------------------ projeler ve teklif dosyası


def test_project_stages_events_and_budget_gate(engine):
    o = PA.create_org(engine, T, "ayse", {"name": "İl Milli Eğitim", "kind": "meb"})
    p = PA.create_project(engine, T, "ayse", "Ayşe", {"title": "Okuma seferberliği", "kind": "okuma", "orgId": o["id"],
                                                     "budget": "125.000,50"})
    assert p["stage"] == "fikir" and p["budget"] == 125000.5
    PA.update_project(engine, T, "ayse", "Ayşe", p["id"], {"stage": "teklif", "stageNote": "Dosya verildi"})
    with pytest.raises(core.RelationError, match="bütçe onayı"):
        PA.update_project(engine, T, "ayse", "Ayşe", p["id"], {"stage": "uygulama"})
    with pytest.raises(core.RelationError) as e:
        PA.approve_project(engine, T, "ayse", False, p["id"], "budget")
    assert e.value.status == 409
    PA.approve_project(engine, T, "mudur", False, p["id"], "budget")
    out, _ = PA.update_project(engine, T, "ayse", "Ayşe", p["id"], {"stage": "uygulama"})
    assert out["stage"] == "uygulama" and out["budgetApprovedBy"] == "mudur"
    changed, _ = PA.update_project(engine, T, "ayse", "Ayşe", p["id"], {"budget": "150000"})
    assert changed["budgetApprovedBy"] is None          # bütçe değişince onay düşer
    ev = PA.project_detail(engine, T, p["id"])["events"]
    assert len(ev) == 4 and {e["stageTo"] for e in ev} == {"fikir", "teklif", "uygulama"}
    assert any(e["note"] == "Bütçe onaylandı" and e["user"] == "mudur" for e in ev)
    assert PA.list_projects(engine, T, "ayse")["total"] == 1


def test_proposal_numbers_and_articles_come_from_code():
    project = {"title": "Kütüphane bağışı", "kind": "bagis", "kindLabel": "Kütüphane bağışı",
               "books": [{"id": BOOK, "qty": 40}]}
    places = [{"ogrenci": 500, "ogretmen": 30}, {"ogrenci": None, "ogretmen": 12}]
    facts = PA.reach_facts(project, places, 38)
    assert facts == {"places": 2, "students": 500, "studentsUnknown": 1, "teachers": 42, "teachersUnknown": 0,
                     "bookTitles": 1, "booksPlanned": 40, "booksDelivered": 38}
    model = "## Amaç\nOkuma alışkanlığı.\nToplam 12.000 öğrenciye ulaşılacak.\n## Takvim\n2027 Ocak ayında başlar."
    doc = PA.proposal_document(project, {"name": "Üsküdar Belediyesi"}, model, facts,
                               [{"id": BOOK, "name": "Tarih Kitabı", "qty": 40}], "Timaş Yayınları")
    assert "12.000" not in doc and "2027" not in doc and "Okuma alışkanlığı." in doc
    assert "Öğrenci sayısı (CRM ziyaret yerleri): 500 — 1 kurumda öğrenci sayısı kayıtlı değil" in doc
    assert "m.10/4" in doc and "lexpera" in doc
    assert PA.criteria_for("etkinlik") == []
    assert D.report_text({"year": 2026, "people": {"total": 0, "critical": 0, "publicOfficials": 0, "byField": []},
                          "contacts": {"notes": 0, "people": 0, "orgs": 0},
                          "gifts": {"byStatus": {}, "sentBooks": 0, "sentPeople": 0, "feedback": 0, "duplicates": 0},
                          "crm": {"error": "CRM şu an okunamıyor."},
                          "projects": {"byStage": {}, "items": [], "reach": {"schools": 0, "students": 0, "books": 0, "participants": 0}}}
                         ).count("CRM okunamadı") == 1


# ------------------------------------------------------------------ CRM SQL


def test_crm_sql_is_read_only_escaped_and_skips_sensitive_columns():
    sqls = [S.contacts_sql(SCHEMA, "O'Neil%", 1, 2), S.contact_sql(SCHEMA, GUID), S.contact_tags_sql(SCHEMA, [GUID]),
            S.decision_makers_sql(SCHEMA), S.person_roles_sql(SCHEMA), S.places_sql(SCHEMA, "okul", 1, GUID, 0),
            S.places_by_id_sql(SCHEMA, [GUID]), S.city_stats_sql(SCHEMA, GUID, 1), S.cities_sql(SCHEMA),
            S.promo_totals_sql(SCHEMA, 2026, [12], [100000001, 100000003]), S.orders_by_no_sql(SCHEMA, ["SP-1"]),
            S.order_lines_sql(SCHEMA, [GUID]), S.order_status_labels_sql(SCHEMA), S.books_sql(SCHEMA, "tarih", 1),
            S.books_published_sql(SCHEMA, date(2026, 9, 1), date(2026, 10, 1)), S.books_by_id_sql(SCHEMA, [GUID], summary=True)]
    for sql in sqls:
        assert sql.lstrip().upper().startswith("SELECT"), sql
        assert not re.search(r"\b(INSERT|UPDATE|DELETE|MERGE|EXEC|DROP)\b", sql, re.I), sql
        assert not re.search(r"Milliyet|FamilyStatus|Children|DogumYili|evadres|SpousesName", sql, re.I), sql
    assert "N'%O''Neil[%]%'" in sqls[0] and "OFFSET 40 ROWS" in sqls[0] and "AccountRoleCode = 1" in sqls[0]
    assert "AccountRoleCode = 1" in sqls[3] and "StateCode = 0" in sqls[3]
    # CRM ünvan tablosunun ad kolonu new_unvanname (new_name yok; 2026-09-28 kabulünde kişi araması 207 ile düşüyordu)
    assert "u.new_unvanname AS unvan" in sqls[0] and "u.new_name" not in sqls[0]
    assert "TRY_CONVERT(int, NULLIF(z.new_renciSays, ''))" in sqls[7] and "new_KurumTipi = 1" in sqls[7]
    # yıl sınırı İstanbul gece yarısının UTC karşılığı; iptal ve birleştirilmiş siparişler sayılmaz
    assert "'2025-12-31T21:00:00'" in sqls[9] and "'2026-12-31T21:00:00'" in sqls[9] and "100000001, 100000003" in sqls[9]
    with pytest.raises(core.RelationError):
        S.contacts_sql("bad;name")
    with pytest.raises(core.RelationError):
        S.places_by_id_sql(SCHEMA, ["not-a-guid"])
    with pytest.raises(S.SourceError):
        S.orders_by_no_sql(SCHEMA, ["x'; DROP TABLE y--"])
    assert S.plain("<p>Bir&nbsp;<b>kitap</b></p>") == "Bir kitap"


# ------------------------------------------------------------------ yetki


def test_access_rules_for_public_affairs():
    assert A.rule_for("/api/v1/public-affairs/run-due") == A.SYSTEM
    assert A.rule_for("/api/v1/public-affairs/people") == frozenset({A.page("kurumsal-iliskiler")})
    assert A.features_for("POST", "/api/v1/public-affairs/people/abc/notes") == ["ozellik:iliskiler.duzenle"]
    assert A.features_for("POST", "/api/v1/public-affairs/gifts/suggest") == ["ozellik:iliskiler.duzenle"]
    assert A.features_for("POST", "/api/v1/public-affairs/gifts/approve") == []          # açıkça verilen onay ucun içinde
    assert A.features_for("POST", "/api/v1/public-affairs/projects/abc/approve") == []
    assert A.features_for("POST", "/api/v1/public-affairs/fields") == []
    assert A.features_for("GET", "/api/v1/public-affairs/report/export.pdf") == ["ozellik:veri.disa-aktar"]
    assert A.features_for("GET", "/api/v1/public-affairs/people") == []
    assert {"ozellik:iliskiler.onay", "ozellik:iliskiler.hassas"} <= A.explicit_keys()
    keys = A.all_keys()
    assert {"sayfa:kurumsal-iliskiler", "ozellik:iliskiler.duzenle"} <= keys
    page = next(p for p in A.catalog()["pages"] if p["key"] == "sayfa:kurumsal-iliskiler")
    assert page.get("explicit") is True
