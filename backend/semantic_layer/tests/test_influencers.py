"""M23 İşbirlikleri: kayıt defteri (hesap tekilliği, kullanıcı adı okuma, ücretin yetkiye göre gizlenmesi), işbirliği
aşama kapıları (seçim onayı, iki göz, bağlantı, yasal etiket, sonuç), ödeme satırı (hazır → onaylı → ödendi, iptal),
aday sırası (konu/yaş/tazelik/bütçe, aynı kitabı almış ve «iletişim kurulmasın» ayrı listede), ilişki puanı, takipçi
sıçraması, hatırlatmalar, CSV içe aktarma, taslakta model denetimi ve sabit yasal etiket, rapor (harcama, CPE),
yetki kuralları ve uçların FastAPI imzaları.

Veriler yapaydır ve yalnız kuralları sınar; gerçek CRM/portal kabulü test sunucusunda (scripts/acceptance/M23).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa

from semantic_bridge import access as A
from semantic_bridge import influencers as I
from semantic_bridge import influencers_sources as S
from semantic_layer.store.catalog_store import open_store

TN = "t1"
BOOK = "11111111-2222-3333-4444-555555555555"
BOOK2 = "66666666-2222-3333-4444-555555555555"


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    I._ready.discard(id(e))
    I.ensure(e)
    return e


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in ("INFLUENCER_RANK_WEIGHTS", "INFLUENCER_TOPIC_WORDS", "INFLUENCER_COOLDOWN_DAYS", "INFLUENCER_JUMP_PCT",
              "INFLUENCER_CONTENT_WAIT_DAYS", "INFLUENCER_LINK_GRACE_DAYS", "INFLUENCER_PAYOUT_DAY",
              "INFLUENCER_MONTHLY_BUDGET", "INFLUENCER_DISCLOSURE_KINDS", "INFLUENCER_GIFT_NEEDS_APPROVAL",
              "INFLUENCER_API_ENABLED", "INFLUENCER_BUDGET_WARN_PCT"):
        monkeypatch.delenv(k, raising=False)


def _person(engine, name="Ayşe Okur", **kw):
    body = {"name": name, "topics": ["tarih"], "ageGroups": ["18+"],
            "accounts": [{"platform": "instagram", "handle": f"@{I.fold(name.split()[0])}okur"}], **kw}
    return I.create_person(engine, TN, "sorumlu", body)["id"]


def _collab(engine, pid, kind="ucretli", fee="1500", book=BOOK, user="sorumlu", **kw):
    return I.create_collab(engine, TN, user, {"personId": pid, "kind": kind, "fee": fee, "crmBookId": book,
                                              "bookTitle": "Osmanlı'da Bir Gün", **kw})["id"]


# ------------------------------------------------------------------ kayıt defteri


def test_handle_is_read_from_url_or_at_sign():
    assert I.norm_handle("https://www.instagram.com/Kitap.Kurdu/?hl=tr") == "kitap.kurdu"
    assert I.norm_handle("@Kitap_Kurdu") == "kitap_kurdu"
    assert I.norm_handle("https://www.youtube.com/c/OkurKanal") == "okurkanal"
    assert I.norm_handle("boşluk var") is None
    assert S.handle("https://x.com/okur") == "okur"


def test_an_account_belongs_to_one_person(engine):
    _person(engine, "Ayşe Okur")
    with pytest.raises(I.InfluencerError) as e:
        I.create_person(engine, TN, "sorumlu", {"name": "Başka", "accounts": [{"platform": "instagram", "handle": "ayseokur"}]})
    assert e.value.status == 409


def test_fee_range_is_hidden_without_approval_or_payment_right(engine):
    pid = I.create_person(engine, TN, "sorumlu", {"name": "Ücretli Kişi", "feeMin": "1000", "feeMax": "2500"})["id"]
    hidden = I.get_person(engine, TN, pid, can_fee=False)
    assert hidden["feeMin"] is None and hidden["feeMax"] is None and hidden["feeSet"] is True
    shown = I.get_person(engine, TN, pid, can_fee=True)
    assert shown["feeMin"] == 1000.0 and shown["feeMax"] == 2500.0
    assert all(p["feeMin"] is None for p in I.list_people(engine, TN, can_fee=False)["items"])
    with pytest.raises(I.InfluencerError) as e:
        I.update_person(engine, TN, "sorumlu", pid, {"feeMin": "10"}, can_fee=False)
    assert e.value.status == 403
    with pytest.raises(I.InfluencerError):
        I.update_person(engine, TN, "mudur", pid, {"feeMin": "3000"}, can_fee=True)   # alt > üst


def test_unknown_topic_and_platform_are_refused(engine):
    with pytest.raises(I.InfluencerError):
        I.create_person(engine, TN, "u", {"name": "X", "topics": ["uzay-yolu"]})
    with pytest.raises(I.InfluencerError):
        I.create_person(engine, TN, "u", {"name": "X", "accounts": [{"platform": "myspace", "handle": "x"}]})
    pid = I.create_person(engine, TN, "u", {"name": "Y", "topics": "Tarih ve biyografi, Çocuk"})["id"]
    assert I.get_person(engine, TN, pid, True)["topics"] == ["tarih", "cocuk"]


def test_csv_import_creates_people_and_measurements(engine):
    _person(engine, "Ayşe Okur")
    text = ("Ad;Platform;Kullanıcı adı;Konu;Takipçi\n"
            "Mehmet Kitap;Instagram;@mehmetkitap;Edebiyat;12.500\n"
            ";instagram;ayseokur;;900\n"
            "Hatalı;;@kimsesiz;;\n"
            "Bilinmez;Myspace;x;;\n")
    out = I.import_csv(engine, TN, "sorumlu", text)
    assert out["eklenen"] == 1 and out["mevcut"] == 1 and out["olcum"] == 2
    assert [e["satir"] for e in out["okunamayan"]] == [4, 5]
    people = {p["name"]: p for p in I.list_people(engine, TN, can_fee=False)["items"]}
    assert people["Mehmet Kitap"]["followers"] == 12500 and people["Mehmet Kitap"]["topics"] == ["edebiyat"]


# ------------------------------------------------------------------ işbirliği akışı


def test_paid_collab_walks_the_gates_to_payment_and_closes(engine):
    pid = _person(engine)
    cid = _collab(engine, pid)
    with pytest.raises(I.InfluencerError, match="onaylanmadan"):
        I.update_collab(engine, TN, "sorumlu", cid, {"stage": "gonderildi"}, can_fee=False)
    with pytest.raises(I.InfluencerError, match="başka biri"):
        I.approve_collab(engine, TN, "sorumlu", cid, {"decision": "onay"})
    I.approve_collab(engine, TN, "mudur", cid, {"decision": "onay"})
    I.update_collab(engine, TN, "sorumlu", cid, {"stage": "gonderildi", "crmOrderNo": "SP-1001"}, can_fee=False)
    with pytest.raises(I.InfluencerError, match="bağlantı"):
        I.update_collab(engine, TN, "sorumlu", cid, {"stage": "yayinda"}, can_fee=False)
    out, _ = I.update_collab(engine, TN, "sorumlu", cid, {"stage": "yayinda", "publishedUrl": "https://instagram.com/p/abc"},
                             can_fee=False)
    assert out["publishedAt"] is not None and out["fee"] is None         # ücret yetkisizde boş
    with pytest.raises(I.InfluencerError, match="etiket"):
        I.update_collab(engine, TN, "sorumlu", cid, {"stage": "rapor", "engagement": 400}, can_fee=False)
    with pytest.raises(I.InfluencerError, match="erişim ya da etkileşim"):
        I.update_collab(engine, TN, "sorumlu", cid, {"stage": "rapor", "disclosureOk": True}, can_fee=False)
    I.update_collab(engine, TN, "sorumlu", cid, {"stage": "rapor", "disclosureOk": True, "engagement": 400, "reach": 9000},
                    can_fee=False)
    with pytest.raises(I.InfluencerError, match="kendiliğinden"):
        I.update_collab(engine, TN, "sorumlu", cid, {"stage": "kapali"}, can_fee=False)
    I.update_collab(engine, TN, "sorumlu", cid, {"stage": "odeme"}, can_fee=False)
    pays = I.list_payouts(engine, TN)
    assert len(pays["items"]) == 1 and pays["items"][0]["amount"] == 1500.0 and pays["items"][0]["status"] == "hazir"
    pay_id = pays["items"][0]["id"]
    with pytest.raises(I.InfluencerError):                               # ücret ödeme aşamasında değişmez
        I.update_collab(engine, TN, "mudur", cid, {"fee": "2000"}, can_fee=True)
    with pytest.raises(I.InfluencerError, match="açan"):
        I.decide_payout(engine, TN, "sorumlu", pay_id, {"action": "onayla"}, can_approve=True, can_pay=True)
    I.decide_payout(engine, TN, "mudur", pay_id, {"action": "onayla"}, can_approve=True, can_pay=False)
    with pytest.raises(I.InfluencerError) as e:
        I.decide_payout(engine, TN, "mudur", pay_id, {"action": "ode", "logoDocNo": "X"}, can_approve=True, can_pay=False)
    assert e.value.status == 403
    with pytest.raises(I.InfluencerError, match="belge"):
        I.decide_payout(engine, TN, "muhasebe", pay_id, {"action": "ode"}, can_approve=False, can_pay=True)
    I.decide_payout(engine, TN, "muhasebe", pay_id, {"action": "ode", "logoDocNo": "HZ-2026-17"}, can_approve=False, can_pay=True)
    c = I.get_collab(engine, TN, cid, True)
    assert c["stage"] == "kapali" and c["payout"]["status"] == "odendi" and c["payout"]["logoDocNo"] == "HZ-2026-17"
    assert [e["action"] for e in c["events"]][:2] == ["olusturuldu", "onay"]


def test_every_open_payout_belongs_to_a_collab_in_payment(engine):
    """Kabul 5'in kuralı: hazır/onaylı satırın işi «ödeme»de; iptal edilen satırın işi rapora döner."""
    pid = _person(engine)
    cid = _collab(engine, pid)
    I.approve_collab(engine, TN, "mudur", cid, {})
    I.update_collab(engine, TN, "s", cid, {"stage": "rapor", "publishedUrl": "https://x.com/a/1", "disclosureOk": True,
                                           "reach": 10}, can_fee=False)
    I.update_collab(engine, TN, "s", cid, {"stage": "odeme"}, can_fee=False)
    with pytest.raises(I.InfluencerError, match="geri alınmaz"):
        I.update_collab(engine, TN, "s", cid, {"stage": "rapor"}, can_fee=False)
    pay = I.list_payouts(engine, TN)["items"][0]
    with pytest.raises(I.InfluencerError, match="neden"):
        I.decide_payout(engine, TN, "mudur", pay["id"], {"action": "iptal"}, can_approve=True, can_pay=False)
    I.decide_payout(engine, TN, "mudur", pay["id"], {"action": "iptal", "note": "tutar yanlış"}, can_approve=True, can_pay=False)
    assert I.get_collab(engine, TN, cid, True)["stage"] == "rapor"
    with engine.connect() as c:
        bad = c.execute(sa.select(sa.func.count()).select_from(I.PAYOUTS.join(I.COLLABS, I.COLLABS.c.id == I.PAYOUTS.c.collab_id))
                        .where(I.PAYOUTS.c.status.in_(("hazir", "onayli")), I.COLLABS.c.stage != "odeme")).scalar()
    assert bad == 0
    assert I.list_payouts(engine, TN)["items"] == []


def test_gift_closes_from_report_and_never_reaches_payment(engine, monkeypatch):
    monkeypatch.setenv("INFLUENCER_GIFT_NEEDS_APPROVAL", "0")
    pid = _person(engine)
    cid = _collab(engine, pid, kind="hediye", fee="")
    I.update_collab(engine, TN, "s", cid, {"stage": "rapor", "publishedUrl": "https://x.com/a/1", "disclosureOk": True,
                                           "engagement": 50}, can_fee=False)
    with pytest.raises(I.InfluencerError, match="Ücreti olmayan"):
        I.update_collab(engine, TN, "s", cid, {"stage": "odeme"}, can_fee=False)
    out, _ = I.update_collab(engine, TN, "s", cid, {"stage": "kapali"}, can_fee=False)
    assert out["stage"] == "kapali"
    with pytest.raises(I.InfluencerError, match="yeniden açılmaz"):
        I.update_collab(engine, TN, "s", cid, {"stage": "rapor"}, can_fee=False)


def test_rejection_needs_a_reason_and_abandons(engine):
    cid = _collab(engine, _person(engine))
    with pytest.raises(I.InfluencerError, match="neden"):
        I.approve_collab(engine, TN, "mudur", cid, {"decision": "ret"})
    I.approve_collab(engine, TN, "mudur", cid, {"decision": "ret", "note": "bütçe yok"})
    assert I.get_collab(engine, TN, cid, False)["stage"] == "vazgecildi"


def test_same_book_to_same_person_needs_explicit_repeat(engine):
    pid = _person(engine)
    _collab(engine, pid)
    with pytest.raises(I.InfluencerError) as e:
        _collab(engine, pid)
    assert e.value.status == 409
    assert _collab(engine, pid, repeat=True)


def test_do_not_contact_blocks_new_collab(engine):
    pid = I.create_person(engine, TN, "u", {"name": "Kapalı", "doNotContact": True})["id"]
    with pytest.raises(I.InfluencerError, match="iletişim kurulmasın"):
        _collab(engine, pid)


def test_paid_collab_needs_a_fee(engine):
    with pytest.raises(I.InfluencerError, match="ücret"):
        _collab(engine, _person(engine), fee="")


# ------------------------------------------------------------------ aday sırası


def _book(**kw):
    return {"kitapId": BOOK, "ad": "Osmanlı'da Bir Gün", "turler": "Tarih, Biyografi", "raf": "Tarih", "hedefKitle": "Yetişkin",
            "yas": [18, None], **kw}


def test_book_topics_come_from_crm_text_with_word_rule():
    cfg = I.settings()
    assert I.book_profile(_book(), cfg)["topics"] == ["tarih"]
    assert I.book_profile(_book(turler="Dinozorlar ansiklopedisi", raf=None), cfg)["topics"] == []
    assert "din-tasavvuf" in I.book_profile(_book(turler="Din, Tasavvuf", raf=None), cfg)["topics"]
    assert I.book_profile(_book(yas=[7, 10]), cfg)["ageGroups"] == ["7-10"]


def test_ranking_prefers_topic_fit_and_lists_the_excluded(engine):
    fit = _person(engine, "Tarihçi Kız")
    other = I.create_person(engine, TN, "u", {"name": "Masalcı", "topics": ["cocuk"], "ageGroups": ["7-10"]})["id"]
    had = _person(engine, "Almış Olan")
    _collab(engine, had)
    dnc = I.create_person(engine, TN, "u", {"name": "Rahatsız Etme", "topics": ["tarih"], "doNotContact": True})["id"]
    cfg = I.settings()
    out = I.candidates(engine, TN, _book(), I.book_profile(_book(), cfg), budget=None, can_fee=False)
    order = [i["personId"] for i in out["items"]]
    assert order.index(fit) < order.index(other)
    assert {e["personId"] for e in out["excluded"]} == {had, dnc}
    first = out["items"][0]
    assert "konu uyumu: Tarih ve biyografi" in first["reason"] and 0 <= first["score"] <= 100
    assert out["total"] == len(out["items"]) == 2                          # tavan yok: herkes listede


def test_recent_collab_and_budget_lower_the_score(engine):
    pid = I.create_person(engine, TN, "u", {"name": "Pahalı", "topics": ["tarih"], "feeMin": "5000"})["id"]
    cfg = I.settings()
    prof = I.book_profile(_book(), cfg)
    base = I.candidates(engine, TN, _book(), prof, budget=None, can_fee=True)["items"][0]
    tight = I.candidates(engine, TN, _book(), prof, budget=1000, can_fee=True)["items"][0]
    assert tight["parts"]["butce"] == 0.0 and tight["score"] < base["score"]
    assert I.candidates(engine, TN, _book(), prof, budget=1000, can_fee=False)["items"][0]["feeMin"] is None
    _collab(engine, pid, book=BOOK2)
    fresh = I.candidates(engine, TN, _book(), prof, budget=None, can_fee=True)["items"][0]
    assert fresh["parts"]["tazelik"] == 0.0 and "gün önce" in fresh["reason"]


def test_relation_score_parts():
    today = I._today()
    Row = type("Row", (), {})

    def c(stage, days_ago):
        r = Row()
        r.stage, r.published_at, r.due_publish, r.created_day = stage, today - timedelta(days=days_ago), None, today
        return r

    rel = I.relation([c("kapali", 0), c("yayinda", 100), c("vazgecildi", 10)], today)
    assert rel["parts"] == {"yakinlik": 40, "siklik": 20, "sonuc": 20} and rel["score"] == 80 and rel["band"] == "sicak"
    assert I.relation([c("vazgecildi", 1)], today)["score"] == 0


def test_follower_jump_uses_only_our_own_measurements(engine):
    pid = _person(engine)
    acc = I.get_person(engine, TN, pid, False)["accounts"][0]["id"]
    today = I._today()
    I.add_snapshot(engine, TN, "u", acc, {"day": (today - timedelta(days=20)).isoformat(), "followers": 10000})
    I.add_snapshot(engine, TN, "u", acc, {"day": today.isoformat(), "followers": 14000})
    j = I.get_person(engine, TN, pid, False)["jumps"]
    assert len(j) == 1 and j[0]["pct"] == 40.0
    with pytest.raises(I.InfluencerError):
        I.add_snapshot(engine, TN, "u", acc, {"day": (today + timedelta(days=1)).isoformat(), "followers": 1})


# ------------------------------------------------------------------ hatırlatmalar ve pano


def test_reminders_and_one_time_sending(engine):
    today = I._today()
    pid = _person(engine)
    late = _collab(engine, pid, duePublish=(today - timedelta(days=3)).isoformat())
    soon = _collab(engine, pid, book=BOOK2, duePublish=(today + timedelta(days=1)).isoformat())
    items = I.reminders(engine, TN, I.settings(), today)
    kinds = {(i["kind"], i["collabId"]) for i in items}
    assert ("baglanti-yok", late) in kinds and ("yayin-yaklasti", soon) in kinds and ("teklif-onay-bekliyor", late) in kinds
    I.mark_sent(engine, TN, [i["key"] for i in items])
    assert I.unsent(engine, TN, I.reminders(engine, TN, I.settings(), today)) == []
    b = I.board(engine, TN, "sorumlu", can_fee=False)
    assert b["waitingApproval"] == 2 and b["linkLate"] == 1 and b["month"]["spend"] is None
    assert [col["stage"] for col in b["columns"]] == list(I.BOARD)


# ------------------------------------------------------------------ taslak


def _facts(engine, cid):
    return I.draft_facts(engine, TN, cid, {"ad": "Osmanlı'da Bir Gün", "yazar": "Ali Yazar", "ozet": "İstanbul'da 1850 yılında bir gün.",
                                           "oneCikan": None, "turler": "Tarih", "hedefKitle": "Yetişkin"})


def test_draft_drops_invented_numbers_and_keeps_the_fixed_disclosure(engine):
    cid = _collab(engine, _person(engine))
    f = _facts(engine, cid)
    d = I.render_draft("brief", f, lambda m: "Kitap 1850 yılında geçiyor. Kitap 50 bin sattı.")
    assert d["source"] == "zeki" and "1850" in d["body"] and "50 bin" not in d["body"]
    assert len(d["dropped"]) == 1 and d["dropped"][0]["neden"] == "kaynaksiz-rakam"
    assert I.DISCLOSURE_CLAUSE in d["body"]
    rule = I.render_draft("brief", f, None)
    assert rule["source"] == "kural" and I.DISCLOSURE_CLAUSE in rule["body"]
    saved = I.save_draft(engine, TN, "sorumlu", cid, "brief", d)
    with pytest.raises(I.InfluencerError, match="onaylı"):
        I.mark_mailed(engine, TN, "sorumlu", cid, saved["id"])
    I.edit_draft(engine, TN, "sorumlu", cid, saved["id"], {"body": "yasal madde silindi"})
    with pytest.raises(I.InfluencerError, match="yasal etiket"):
        I.approve_draft(engine, TN, "mudur", cid, saved["id"])
    ok = I.save_draft(engine, TN, "sorumlu", cid, "brief", rule)
    I.approve_draft(engine, TN, "mudur", cid, ok["id"])
    assert I.mark_mailed(engine, TN, "sorumlu", cid, ok["id"])["sentBy"] == "sorumlu"


def test_model_tech_name_in_draft_falls_back_to_template(engine):
    cid = _collab(engine, _person(engine))
    d = I.render_draft("iletisim", _facts(engine, cid), lambda m: "Bu metni Qwen yazdı.")
    assert d["source"] == "kural" and "Qwen" not in d["body"]


# ------------------------------------------------------------------ rapor


def test_report_spend_and_cost_per_engagement(engine):
    today = I._today()
    pid = _person(engine)
    a = _collab(engine, pid, fee="1000")
    b = _collab(engine, pid, fee="500", book=BOOK2)
    gone = _collab(engine, pid, fee="9999", repeat=True)
    for cid, eng in ((a, 400), (b, 100)):
        I.approve_collab(engine, TN, "mudur", cid, {})
        I.update_collab(engine, TN, "s", cid, {"stage": "rapor", "publishedUrl": "https://x.com/a/1", "disclosureOk": True,
                                               "engagement": eng}, can_fee=False)
    I.approve_collab(engine, TN, "mudur", gone, {"decision": "ret", "note": "vazgeçildi"})
    rep = I.report(engine, TN, today.replace(day=1), today, can_fee=True)
    assert rep["total"]["spend"] == 1500.0 and rep["total"]["engagement"] == 500 and rep["total"]["cpe"] == 3.0
    assert rep["total"]["collabs"] == 2
    hidden = I.report(engine, TN, today.replace(day=1), today, can_fee=False)
    assert hidden["total"]["spend"] is None and hidden["total"]["cpe"] is None and hidden["items"][0]["fee"] is None
    assert I.report_xlsx(rep, {"toplam": 10.0, "kayit": 1}, True)[:2] == b"PK"


# ------------------------------------------------------------------ kaynak SQL ve yetki


def test_crm_sql_is_read_only_and_escaped():
    sql = S.promo_orders_sql("Timas_MSCRM.dbo", ["SP-1", "x'; DROP TABLE a;--"])
    assert "new_siparistipi = 12" in sql and "DROP" not in sql
    assert "new_mecratipi4 = 6" in S.crm_spend_sql("Timas_MSCRM.dbo", I._today(), I._today())
    assert "new_Instagram" in S.social_summary_sql("Timas_MSCRM.dbo")
    for q in (sql, S.book_sql("Timas_MSCRM.dbo", BOOK), S.social_contacts_sql("Timas_MSCRM.dbo", {"instagram": ["@a"]})):
        assert q.lstrip("- M23:").upper().count("SELECT") >= 1
        assert not any(w in q.upper() for w in ("INSERT ", "UPDATE ", "DELETE ", "MERGE "))
    with pytest.raises(S.SourceError):
        S.book_sql("Timas_MSCRM.dbo", "'; x")


def test_access_rules_for_the_module():
    assert A.rule_for("/api/v1/influencers/board") == {"sayfa:isbirlikleri"}
    assert A.rule_for("/api/v1/influencers/run-due") == A.SYSTEM
    f = A.features_for
    assert f("POST", "/api/v1/influencers/people") == ["ozellik:isbirligi.duzenle"]
    assert f("PATCH", "/api/v1/influencers/collabs/c1") == ["ozellik:isbirligi.duzenle"]
    assert f("POST", "/api/v1/influencers/collabs/c1/draft") == ["ozellik:isbirligi.duzenle"]
    assert f("POST", "/api/v1/influencers/collabs/c1/approve") == []           # açıkça verilen, ucun içinde
    assert f("POST", "/api/v1/influencers/collabs/c1/drafts/d1/approve") == []
    assert f("POST", "/api/v1/influencers/payouts/p1/decide") == []
    assert f("GET", "/api/v1/influencers/payouts/export.xlsx") == ["ozellik:veri.disa-aktar"]
    assert f("GET", "/api/v1/influencers/board") == []
    assert {"ozellik:isbirligi.onay", "ozellik:isbirligi.odeme"} <= A.explicit_keys()


def test_routes_take_request_and_body_correctly():
    from fastapi import FastAPI

    app = FastAPI()
    from semantic_bridge import influencers_api

    influencers_api.register(app, lambda: None, lambda r: None, lambda u, k: True)
    bad = []
    for route in app.routes:
        dep = getattr(route, "dependant", None)
        for q in (dep.query_params if dep is not None else []):
            if q.name in ("request", "body") or q.name[:1].isupper():
                bad.append(f"{sorted(route.methods)} {route.path}: {q.name}")
    assert bad == []
    paths = {getattr(r, "path", "") for r in app.routes}
    assert all(A.rule_for(p) is not None for p in paths if p.startswith("/api/"))


def test_amounts_are_kept_as_decimal(engine):
    cid = _collab(engine, _person(engine), fee="1234,56")
    with engine.connect() as c:
        fee = c.execute(sa.select(I.COLLABS.c.fee).where(I.COLLABS.c.id == cid)).scalar()
    assert Decimal(str(fee)) == Decimal("1234.56")
