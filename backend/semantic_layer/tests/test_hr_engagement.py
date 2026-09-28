"""M58 Çalışan deneyimi ve bağlılık: anonimlik (cevap ve yorum tablolarında kişi/jeton/saat yok, davetle birleştirilecek
ortak kolon yok, kapanışta davetler silinir), tek cevap, basılı kod, gösterim eşiği (girilmeden sonuç yok, yalnız yükseltilir,
eşik altı birim üst birimle, fark saldırısına karşı artık kuralı), sonuç açıkken gösterilmez, eNPS/endeks hesabı, şablon onayı
(iki göz), oryantasyon daveti, yorum maskesi ve tema sınıflama, öneri kutusu (adsızda yazar yok, kişiyle ilgili şikâyet
birime gitmez), aksiyon planı, imha ve köprü kapıları.

Veriler yapaydır ve yalnız kuralları sınar; gerçek kabul test sunucusunda (scripts/acceptance/M58).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
import sqlalchemy as sa

from semantic_bridge import hr_core as H
from semantic_bridge import hr_engagement as E
from semantic_bridge import hr_engagement_text as T
from semantic_layer.store.catalog_store import open_store

TN = "t1"
TODAY = date(2026, 10, 5)
HRW = H.Who("ikuzman", "İK", False, frozenset({E.F_SURVEY_ADMIN, E.F_SUGG_ADMIN, E.F_ACTION, E.F_COMMENTS}))
HR2 = H.Who("ikmudur", "İK Müdürü", False, frozenset({E.F_SURVEY_ADMIN}))


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    H._ready.discard(e)
    E._ready.discard(e)
    E.ensure(e)
    H._purgers.clear()
    E.register_hooks()
    return e


@pytest.fixture
def org(engine):
    """Şirket → Editörya (Çocuk, Yetişkin alt birimleri) ve Satış. Her kişinin AD hesabı var, biri bilgisayarsız."""
    ids = {}
    ed, _ = H.save_unit(engine, TN, "ik", {"name": "Editörya"})
    cocuk, _ = H.save_unit(engine, TN, "ik", {"name": "Çocuk", "parentId": ed["id"]})
    yet, _ = H.save_unit(engine, TN, "ik", {"name": "Yetişkin", "parentId": ed["id"]})
    satis, _ = H.save_unit(engine, TN, "ik", {"name": "Satış"})
    ids.update(ed=ed["id"], cocuk=cocuk["id"], yet=yet["id"], satis=satis["id"])
    n = 0
    for unit, count in (("cocuk", 6), ("yet", 2), ("satis", 5)):
        for i in range(count):
            n += 1
            e, _ = H.save_employee(engine, TN, "ik", {"displayName": f"Kişi{n} Soyad{n}", "username": f"u{n}", "unitId": ids[unit]})
            ids[f"u{n}"] = e["id"]
    depo, _ = H.save_employee(engine, TN, "ik", {"displayName": "Depo Çalışanı", "unitId": ids["satis"]})
    ids["depo"] = depo["id"]
    mgr, _ = H.save_employee(engine, TN, "ik", {"displayName": "Editörya Müdürü", "username": "edmudur", "unitId": ids["ed"]})
    H.save_unit(engine, TN, "ik", {"managerEmployeeId": mgr["id"]}, ids["ed"])
    return ids


def _template(engine, kind="baglilik", **kw):
    t, _ = E.save_template(engine, TN, "ikuzman", {"kind": kind, **T.STARTERS[kind], **kw})
    E.template_transition(engine, TN, HRW, t["id"], "submit")
    return E.template_transition(engine, TN, HR2, t["id"], "approve")


def _survey(engine, **kw):
    t = _template(engine)
    body = {"templateId": t["id"], "opensAt": TODAY.isoformat(), "closesAt": (TODAY + timedelta(days=10)).isoformat(), **kw}
    s, _ = E.save_survey(engine, TN, "ikuzman", body)
    return E.open_survey(engine, TN, "ikuzman", s["id"], today=TODAY)


def _answer(engine, sid, user, answers, today=TODAY):
    tok = E.issue_link(engine, TN, user, sid)
    return E.submit_public(engine, tok, {"answers": answers}, delay_max=0, today=today)


# ------------------------------------------------------------------ anonimlik


def test_response_and_comment_tables_have_no_identity_columns(engine):
    for table in (E.RESPONSES, E.COMMENTS):
        cols = {c.name for c in table.columns}
        assert not any(x in col for col in cols for x in ("employee", "username", "token", "user", "author", "_at"))
    assert isinstance(E.RESPONSES.c.submitted_day.type, sa.Date)
    shared = ({c.name for c in E.INVITES.columns} & {c.name for c in E.RESPONSES.columns}) - {"survey_id", "tenant_id"}
    assert shared == set()                                 # davetle birleştirilecek ortak kolon yok (kimlik, zaman, sıra)


def test_one_answer_per_invite_and_invites_deleted_on_close(engine, org):
    s = _survey(engine, minGroup=3)
    assert s["state"] == "acik" and s["invited"] == 14     # hesabı olan 13 kişi + müdür; bilgisayarsız dahil değil
    out = _answer(engine, s["id"], "u1", {"enps": 10, "gurur": 5, "acik_degis": "Kişi2 Soyad2 ile toplantılar uzun, tel 0532 111 22 33"})
    assert out["ok"]
    with pytest.raises(H.HrError):
        E.issue_link(engine, TN, "u1", s["id"])            # cevapladı: yeni bağlantı yok
    with engine.connect() as c:
        resp = c.execute(sa.select(E.RESPONSES)).first()
        com = c.execute(sa.select(E.COMMENTS)).first()
        inv = c.execute(sa.select(E.INVITES).where(E.INVITES.c.responded.is_(True))).all()
    assert resp.unit_id is None and resp.submitted_day == TODAY and '"acik_degis"' not in resp.answers_json
    assert "Kişi2" not in com.masked_text and "0532" not in com.masked_text and "[kişi]" in com.masked_text
    assert len(inv) == 1
    E.close_survey(engine, TN, "ikuzman", s["id"])
    with engine.connect() as c:
        assert c.execute(sa.select(sa.func.count()).select_from(E.INVITES)).scalar() == 0
    closed = E.get_survey(engine, TN, s["id"])
    assert closed["invited"] == 14 and closed["responded"] == 1
    with pytest.raises(H.HrError):                          # kapanmış ankete cevap yok
        E.public_form(engine, "yok")


def test_my_surveys_only_self_and_validation(engine, org):
    s = _survey(engine)
    mine = E.my_surveys(engine, TN, "u2")
    assert [m["id"] for m in mine] == [s["id"]] and mine[0]["responded"] is False
    tok = E.issue_link(engine, TN, "u2", s["id"])
    form = E.public_form(engine, tok, today=TODAY)
    assert form["open"] and not form["alreadyResponded"] and "adınızla saklanmaz" in form["anonymity"]
    with pytest.raises(H.HrError):
        E.submit_public(engine, tok, {"answers": {"enps": 11}}, delay_max=0, today=TODAY)
    with pytest.raises(H.HrError):
        E.submit_public(engine, tok, {"answers": {}}, delay_max=0, today=TODAY)
    with pytest.raises(H.HrError):                          # kapanıştan sonra
        E.submit_public(engine, tok, {"answers": {"enps": 5}}, delay_max=0, today=TODAY + timedelta(days=11))


def test_paper_codes_are_single_use_and_not_linked_to_people(engine, org):
    s = _survey(engine, minGroup=3)
    codes = E.paper_codes(engine, TN, s["id"], 2)
    assert len(codes) == 2 and len(codes[0]) == 11
    E.submit_public(engine, codes[0].lower(), {"answers": {"enps": 8}}, delay_max=0, today=TODAY)
    with pytest.raises(H.HrError):
        E.submit_public(engine, codes[0], {"answers": {"enps": 8}}, delay_max=0, today=TODAY)
    pr = E.progress(engine, TN, s["id"])
    assert pr["paperIssued"] == 2 and pr["paperUsed"] == 1 and pr["responses"] == 1 and pr["noAccount"] == 1
    assert set(pr) >= {"invited", "responded", "rate"} and "people" not in pr


# ------------------------------------------------------------------ eşik ve sonuç


def test_results_hidden_while_open_and_without_threshold(engine, org):
    s = _survey(engine)
    for u in ("u1", "u2", "u3"):
        _answer(engine, s["id"], u, {"enps": 9})
    assert E.results(engine, TN, s["id"])["reason"] == "acik"
    E.close_survey(engine, TN, "ikuzman", s["id"])
    r = E.results(engine, TN, s["id"])
    assert r["suppressed"] and r["reason"] == "esik_yok"
    E.save_survey(engine, TN, "ikuzman", {"minGroup": 3}, s["id"])
    r = E.results(engine, TN, s["id"])
    assert not r["suppressed"] and r["n"] == 3 and r["enps"] == 100.0
    with pytest.raises(H.HrError):                          # eşik yalnız yükseltilir
        E.save_survey(engine, TN, "ikuzman", {"minGroup": 2}, s["id"])
    assert E.trend(engine, TN)[0]["enps"] == 100.0          # eşik sonradan girilince eğilim satırı yenilendi


def test_enps_and_index_formula():
    qs = [{"key": "enps", "type": "enps", "text": "e"}, {"key": "a", "type": "likert5", "text": "a"},
          {"key": "b", "type": "likert5", "text": "b"}]
    rows = [{"enps": 10, "a": 5, "b": 1}, {"enps": 9, "a": 3}, {"enps": 6, "a": 4, "b": 3}, {"enps": 7}]
    out = E.aggregate(qs, rows)
    assert out["enps"] == 25.0                              # (2 − 1) / 4
    assert out["items"][1]["mean"] == 4.0 and out["items"][2]["mean"] == 2.0
    assert out["index"] == round(((4 - 1) / 4 * 100 + (2 - 1) / 4 * 100) / 2, 1)


def test_unit_breakdown_threshold_and_difference_rule(engine, org):
    s = _survey(engine, minGroup=3, unitBreakdown=True)
    for n in range(1, 7):                                   # Çocuk: 6 yanıt
        _answer(engine, s["id"], f"u{n}", {"enps": 10})
    for n in (7, 8):                                        # Yetişkin: 2 yanıt (eşik altı)
        _answer(engine, s["id"], f"u{n}", {"enps": 0})
    for n in (9, 10, 11):                                   # Satış: 3 yanıt
        _answer(engine, s["id"], f"u{n}", {"enps": 5})
    E.close_survey(engine, TN, "ikuzman", s["id"])
    r = E.results(engine, TN, s["id"])
    units = {u["unitName"]: u for u in r["units"]}
    assert units["Editörya"]["shown"] and units["Editörya"]["n"] == 8 and units["Satış"]["shown"]
    # Çocuk tek başına 6 ≥ 3 ama gösterilirse Editörya − Çocuk = 2 yanıt Yetişkin'i ele verir → o da gizlenir.
    assert not units["Çocuk"]["shown"] and not units["Yetişkin"]["shown"] and units["Yetişkin"]["n"] is None
    assert units["Yetişkin"]["mergedInto"] == "Editörya"
    one = E.results(engine, TN, s["id"], org["yet"])
    assert one["suppressed"] and one["mergedInto"] == "Editörya" and "enps" not in one
    ed = E.results(engine, TN, s["id"], org["ed"])
    assert not ed["suppressed"] and ed["n"] == 8 and ed["enps"] == 50.0


def test_breakdown_requires_threshold(engine, org):
    t = _template(engine)
    with pytest.raises(H.HrError):
        E.save_survey(engine, TN, "ikuzman", {"templateId": t["id"], "opensAt": "2026-10-05", "closesAt": "2026-10-15", "unitBreakdown": True})


def test_template_needs_second_person(engine, org):
    t, _ = E.save_template(engine, TN, "ikuzman", {"kind": "nabiz", **T.STARTERS["nabiz"]})
    E.template_transition(engine, TN, HRW, t["id"], "submit")
    with pytest.raises(H.HrError):
        E.template_transition(engine, TN, HRW, t["id"], "approve")
    ok = E.template_transition(engine, TN, HR2, t["id"], "approve")
    assert ok["state"] == "yururlukte"
    changed, _ = E.save_template(engine, TN, "ikuzman", {"questions": T.STARTERS["nabiz"]["questions"][:1]}, t["id"])
    assert changed["state"] == "taslak" and changed["version"] == 2
    with pytest.raises(H.HrError):                          # onaysız şablondan anket yok
        E.save_survey(engine, TN, "ikuzman", {"templateId": t["id"], "opensAt": "2026-10-05", "closesAt": "2026-10-15"})


def test_orientation_invites_new_hires_at_milestone(engine, org):
    t = _template(engine, kind="oryantasyon_30")
    s, _ = E.save_survey(engine, TN, "ikuzman", {"templateId": t["id"], "opensAt": "2026-10-01", "closesAt": "2026-12-31"})
    E.open_survey(engine, TN, "ikuzman", s["id"], today=TODAY)
    assert E.get_survey(engine, TN, s["id"])["invited"] == 0
    H.save_employee(engine, TN, "ik", {"startDate": "2026-09-03"}, org["u1"])    # 30. gün 10-03
    H.save_employee(engine, TN, "ik", {"startDate": "2026-09-20"}, org["u2"])    # 30. gün 10-20: henüz değil
    out = E.run_due(engine, TN, today=TODAY)
    assert out["orientationInvites"] == 1 and E.my_surveys(engine, TN, "u1")[0]["id"] == s["id"]
    assert E.run_due(engine, TN, today=TODAY)["orientationInvites"] == 0


def test_run_due_opens_planned_and_closes_due(engine, org):
    t = _template(engine)
    s, _ = E.save_survey(engine, TN, "ikuzman", {"templateId": t["id"], "opensAt": "2026-10-10", "closesAt": "2026-10-12"})
    assert E.open_survey(engine, TN, "ikuzman", s["id"], today=TODAY)["state"] == "planli"
    assert E.run_due(engine, TN, today=date(2026, 10, 10))["opened"] == 1
    assert E.run_due(engine, TN, today=date(2026, 10, 13))["closed"] == [s["id"]]


class Choice:
    def __init__(self, choice, p=0.9):
        self.choice, self.probs = choice, {choice: p}


def test_theme_classification_and_summary_only_above_threshold(engine, org):
    s = _survey(engine, minGroup=2)
    for u in ("u1", "u2", "u3"):
        _answer(engine, s["id"], u, {"acik_degis": "İş yükü çok fazla"})
    asked = []
    n = E.classify_comments(engine, TN, lambda p, labels: (asked.append(p), Choice("1"))[1], T.DEFAULT_THEMES)
    assert n == 3 and "İş yükü" in asked[0]
    E.close_survey(engine, TN, "ikuzman", s["id"])
    out = E.summarize_themes(engine, TN, s["id"], lambda msgs: "Çalışanlar iş yükünden yakınıyor.")
    assert out == {T.DEFAULT_THEMES[0]: "Çalışanlar iş yükünden yakınıyor."}
    th = E.themes(engine, TN, s["id"])
    assert th["themes"][0]["count"] == 3 and th["themes"][0]["summary"] and th["comments"] is None
    assert len(E.themes(engine, TN, s["id"], raw=True)["comments"]) == 3


# ------------------------------------------------------------------ öneri ve aksiyon


def test_anonymous_suggestion_keeps_no_author_and_personal_complaint_stays_with_hr(engine, org):
    anon = E.create_suggestion(engine, TN, "u1", {"text": "Servis saatleri değişsin", "anonymous": True})
    named = E.create_suggestion(engine, TN, "u2", {"text": "Kişi3 Soyad3 bize bağırıyor", "anonymous": False})
    with engine.connect() as c:
        row = c.execute(sa.select(E.SUGGESTIONS).where(E.SUGGESTIONS.c.id == anon["id"])).first()
    assert row.author_employee_id is None and anon["followCode"] and E.track_suggestion(engine, TN, anon["followCode"])["id"] == anon["id"]
    assert [x["id"] for x in E.my_suggestions(engine, TN, "u2")] == [named["id"]]
    asked = []

    def choose(prompt, labels):
        asked.append(prompt)
        return Choice(labels[T.DEFAULT_TOPICS.index(T.PERSONAL_TOPIC)] if "bağırıyor" in prompt else labels[1])
    assert E.suggest_topics(engine, TN, choose, T.DEFAULT_TOPICS) == 2
    assert all("Kişi3" not in p for p in asked)              # ad modele gitmedi
    with pytest.raises(H.HrError):
        E.suggestion_action(engine, TN, HRW, named["id"], "route", {"unitId": org["satis"]}, T.DEFAULT_TOPICS)
    routed = E.suggestion_action(engine, TN, HRW, anon["id"], "route", {"unitId": org["ed"]}, T.DEFAULT_TOPICS)
    assert routed["state"] == "yonlendirildi"
    mgr = H.Who("edmudur", "M", False, frozenset({E.F_SUGG_ANSWER}))
    assert [x["id"] for x in E.list_suggestions(engine, TN, mgr)] == [anon["id"]]
    assert E.suggestion_action(engine, TN, mgr, anon["id"], "answer", {"answer": "Değişti"}, T.DEFAULT_TOPICS)["state"] == "cevaplandi"
    with pytest.raises(H.HrError):
        E.list_suggestions(engine, TN, H.Who("u5", "x", False, frozenset()))


def test_actions_hr_creates_manager_updates_state_only(engine, org):
    a, _ = E.save_action(engine, TN, HRW, {"title": "Birim toplantısı", "unitId": org["ed"], "dueOn": "2026-11-01"})
    mgr = H.Who("edmudur", "M", False, frozenset())
    assert E.list_actions(engine, TN, mgr)["items"][0]["canEdit"]
    done, _ = E.save_action(engine, TN, mgr, {"state": "tamam", "note": "Yapıldı"}, a["id"])
    assert done["state"] == "tamam" and done["closedAt"]
    with pytest.raises(H.HrError):
        E.save_action(engine, TN, mgr, {"title": "değiştir"}, a["id"])
    with pytest.raises(H.HrError):
        E.save_action(engine, TN, mgr, {"title": "yeni"})
    assert E.list_actions(engine, TN, H.Who("u9", "x", False, frozenset()))["items"] == []


def test_comment_purge_after_retention(engine, org):
    s = _survey(engine, minGroup=2)
    _answer(engine, s["id"], "u1", {"acik_iyi": "Ekip"})
    E.close_survey(engine, TN, "ikuzman", s["id"])
    assert E.due_comments(engine, TN, H.now()) == []
    H.put_retention(engine, TN, "ik", [{"dataClass": E.DC_COMMENTS, "keepDays": 1, "legalBasis": "Aydınlatma metni"}])
    assert E.due_comments(engine, TN, H.now() + timedelta(days=2)) == [s["id"]]
    assert E.purge_comments(engine, TN, [s["id"]], H.now()) == 1


def test_mask_names_handles_suffixes_and_case():
    out, n = T.mask_names("AYŞE'ye söyledim, ayşe yılmaz da biliyor", ["Ayşe Yılmaz"])
    assert "yşe" not in out.lower() and n == 2


# ------------------------------------------------------------------ köprü


def test_bridge_gates_engagement_and_public_form(monkeypatch, store, settings):
    from fastapi.testclient import TestClient

    from semantic_bridge import access as A
    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod
    from semantic_bridge.app import Runtime, create_app
    from semantic_layer.candidates.llm_client import FakeLlm

    users = {"timas_session=a": "ayse", "timas_session=z": "zekiai"}
    monkeypatch.setattr(board_mod, "_fetch_user", lambda cookie: users.get(cookie))
    monkeypatch.setattr(board_mod, "_fetch_session", lambda cookie: {"username": users.get(cookie), "displayName": "x"})
    monkeypatch.setattr(admin_mod, "admins", lambda: ["zekiai"])
    monkeypatch.delenv("SEMANTIC_CALLER_TOKEN", raising=False)
    A._ready.clear()
    A.invalidate()
    client = TestClient(create_app(Runtime(settings, store=store, llm=FakeLlm([""]))))
    a, z = {"cookie": "timas_session=a"}, {"cookie": "timas_session=z"}
    assert client.get("/api/v1/hr/engagement/me/surveys", headers=a).status_code == 403
    assert client.get("/api/v1/hr/engagement/me/surveys", headers=z).status_code == 200
    assert client.get("/api/v1/hr/engagement/templates", headers=z).status_code == 200
    # Yorum metni duyarlı: yönetici rolüyle almadıkça göremez.
    assert client.get("/api/v1/hr/engagement/surveys/x/themes?raw=1", headers=z).status_code == 403
    assert client.get("/api/v1/hr/survey-public/yok").status_code == 404                     # oturumsuz uç kapıdan geçer
    assert client.get("/api/v1/hr/survey-public/yok", headers=a).status_code == 404
    assert client.post("/api/v1/hr/engagement/run-due", headers=a).status_code == 403
    assert client.post("/api/v1/hr/engagement/run-due").status_code == 200
    A._ready.clear()
    A.invalidate()
