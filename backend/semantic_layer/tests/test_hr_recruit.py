"""M55 İşe alım: maskeleme (kural + model satır numarası), kanıtlı özet (alıntı satırın kendisi, puan yok), ilan
ayrımcılık denetimi, pozisyon onayı (iki göz), aday görünürlüğü (kendi pozisyonu / görüşmecisi), mülakat notunun gizliliği,
aşama kararı ve işe alınan adayın çalışan kaydı, saklama süresi ve imha (rıza geri çekilince hemen), e-postadan başvuru
aktarımı (tekrar yok), şablondan mektup ve teklif onayı (gönderim yok), ilgili kişi dışa aktarımı ve köprüdeki kapılar.

Veriler yapaydır ve yalnız kuralları sınar; gerçek veriyle kabul test sunucusunda (scripts/acceptance/M55).
"""
from __future__ import annotations

import base64
from datetime import timedelta

import pytest
import sqlalchemy as sa

from semantic_bridge import hr_core as H
from semantic_bridge import hr_recruit as R
from semantic_bridge import hr_recruit_text as X
from semantic_layer.store.catalog_store import open_store

TN = "t1"
ALL_KEYS = frozenset({R.F_ALL, R.F_SEE, R.F_DECIDE, R.F_POS_OPEN, R.F_LETTERS, R.F_TEMPLATES, R.F_EXPORT, R.F_KVKK})
HRW = H.Who("ik", "İK Uzmanı", False, ALL_KEYS)
GM = H.Who("gm", "Genel Müdür", False, frozenset({R.F_POS_APPROVE, R.F_OFFER_APPROVE}))
MGR = H.Who("mudur", "Birim Müdürü", False, frozenset({R.F_SEE, R.F_DECIDE}))
IV = H.Who("gorusmeci", "Görüşmeci", False, frozenset({R.F_SEE}))
NOBODY = H.Who("biri", "Biri", False, frozenset())

TCKN = "10000000146"          # sağlaması tutan örnek numara

CV = f"""Ayşe Yılmaz
Doğum tarihi: 01.02.1990
Medeni hal: Evli
T.C. {TCKN}
Tel: 0532 111 22 33 · ayse@example.com
Deneyim
2019-2023 X Yayınevi, redaktör: çocuk kitaplarında redaksiyon ve son okuma
2016-2019 Y Dergisi, editör yardımcısı
Sendika üyeliği: Basın-İş
Kronik rahatsızlığım nedeniyle uzaktan çalışmayı tercih ederim
Yabancı dil: İngilizce (ileri)
"""


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    H._ready.discard(e)
    R._ready.discard(e)
    R.ensure(e)
    H._purgers.clear()
    R.register_hooks()
    return e


def _position(engine, **kw):
    body = {"title": "Çocuk kitapları editörü", "competencies": ["Redaksiyon deneyimi", "İngilizce", "Bütçe yönetimi"],
            "hiringManager": "mudur", "team": ["gorusmeci"], **kw}
    pos, _ = R.save_position(engine, TN, "ik", body)
    return pos


def _candidate(engine, pid, name="Ayşe Yılmaz"):
    return R.create_candidate(engine, TN, "ik", {"fullName": name, "email": "ayse@example.com", "positionId": pid})


# ------------------------------------------------------------------ maskeleme ve kanıt


def test_rule_mask_hides_identity_contact_and_special_category_lines():
    masked, counts = X.rule_mask(CV)
    assert TCKN not in masked and "0532" not in masked and "ayse@example.com" not in masked
    assert "01.02.1990" not in masked and "Evli" not in masked
    assert "Basın-İş" not in masked and "Kronik" not in masked
    assert "redaktör" in masked and "İngilizce" in masked
    assert counts["kimlik"] == 1 and counts["telefon"] == 1 and counts["e-posta"] == 1 and counts["özel nitelikli"] == 2
    assert len(masked.split("\n")) == len(CV.split("\n"))                    # satır numaraları kaymaz
    assert X.rule_mask("Sipariş no 12345678901")[0] == "Sipariş no 12345678901"   # sağlaması tutmayan 11 hane


def test_model_mask_hides_only_the_lines_the_model_numbers():
    masked, _ = X.rule_mask("Deneyim: redaktör\nHobiler: cami derneği yöneticisi\nBeceri: InDesign")
    asked = []

    def chat(messages):
        asked.append(messages[-1]["content"])
        return "Cevap: [2, 99]"                       # 99 sorulmadı: yok sayılır
    out, n = X.model_mask(masked, chat)
    assert n == 1 and "cami" not in out and "redaktör" in out and "InDesign" in out
    assert "1: Deneyim: redaktör" in asked[0]


def test_evidence_quotes_are_the_lines_themselves_and_no_score_is_made():
    masked, _ = X.rule_mask(CV)
    lines = dict(X.numbered(masked))
    red = next(n for n, t in lines.items() if "redaktör" in t)
    eng = next(n for n, t in lines.items() if "İngilizce" in t)

    def chat(messages):
        return '{"1": [%d], "2": [%d, 999], "3": []}' % (red, eng)
    rows = X.evidence("Editör", ["Redaksiyon deneyimi", "İngilizce", "Bütçe yönetimi"], masked, chat)
    assert [(r["competency"], r["verdict"]) for r in rows] == [
        ("Redaksiyon deneyimi", "kanit_var"), ("İngilizce", "kanit_var"), ("Bütçe yönetimi", "kanit_yok")]
    assert rows[0]["quotes"] == [{"line": red, "text": lines[red]}]
    assert [q["line"] for q in rows[1]["quotes"]] == [eng]                    # uydurma satır numarası atıldı
    assert all(set(r) == {"competency", "verdict", "quotes"} for r in rows)     # puan/sıra alanı yok
    with pytest.raises(H.HrError):
        X.evidence("Editör", [], masked, chat)


def test_posting_discrimination_rules():
    text = "Aranan nitelikler\n25-35 yaş arası\nBay aday\nAskerliğini yapmış\nİleri düzey İngilizce"
    labels = [w["label"] for w in X.discrimination_rules(text)]
    assert labels == ["Yaş aralığı", "Cinsiyet koşulu", "Askerlik koşulu"]
    assert X.discrimination_rules("İleri düzey İngilizce ve 5 yıl deneyim") == []

    class Choice:
        def __init__(self, choice, p):
            self.choice, self.probs = choice, {X.DISCRIM_CHOICES[0]: p, X.DISCRIM_CHOICES[1]: 1 - p}
    assert X.discrimination_model("x", lambda p, ch: Choice(ch[0], 0.9), 0.8)["source"] == "zeki"
    assert X.discrimination_model("x", lambda p, ch: Choice(ch[1], 0.05), 0.8) is None
    assert "emin değil" in X.discrimination_model("x", lambda p, ch: Choice(ch[1], 0.3), 0.8)["label"]


def test_extract_text_checks_type_and_reads_odt():
    import io
    import zipfile

    with pytest.raises(H.HrError):
        X.extract_text("cv.exe", b"MZ")
    with pytest.raises(H.HrError):
        X.extract_text("cv.pdf", b"not a pdf")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("content.xml", '<?xml version="1.0"?><office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
                   'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:text>'
                   '<text:p>Redaktör</text:p><text:h>Deneyim</text:h></office:text></office:body></office:document-content>')
    assert X.extract_text("cv.odt", buf.getvalue()) == "Redaktör\nDeneyim"
    assert X.extract_text("cv.txt", "Satır 1\r\nSatır 2".encode("cp1254")) == "Satır 1\nSatır 2"


# ------------------------------------------------------------------ pozisyon


def test_position_approval_needs_a_second_person(engine):
    pos = _position(engine)
    boss = H.Who("ik", "İK", False, frozenset({R.F_POS_OPEN, R.F_POS_APPROVE}))
    out = R.position_transition(engine, TN, boss, pos["id"], "submit")
    assert out["state"] == "onayda"
    with pytest.raises(H.HrError, match="siz onaylayamazsınız"):
        R.position_transition(engine, TN, boss, pos["id"], "approve")
    with pytest.raises(H.HrError):
        R.position_transition(engine, TN, GM, pos["id"], "reject")          # gerekçesiz geri gönderme yok
    assert R.position_transition(engine, TN, GM, pos["id"], "approve")["state"] == "acik"
    with pytest.raises(H.HrError):
        R.position_transition(engine, TN, HRW, pos["id"], "submit")          # açık pozisyon yeniden onaya gitmez


def test_posting_text_is_checked_on_save(engine):
    pos = _position(engine)
    out, diff = R.save_position(engine, TN, "ik", {"postingText": "Dinamik ve genç bir ekip arıyoruz"}, pos["id"])
    assert out["postingWarnings"] and out["postingWarnings"][0]["label"].startswith("Yaşa")
    assert diff == {"ilanMetni": "değişti"}


# ------------------------------------------------------------------ görünürlük ve aşama


def test_candidate_visibility_follows_position_and_interview(engine):
    mine = _position(engine)
    other = _position(engine, title="Muhasebe uzmanı", hiringManager="baskasi", team=[])
    a = _candidate(engine, mine["id"])
    b = _candidate(engine, other["id"], "Mehmet Demir")
    c = _candidate(engine, None, "Pozisyonsuz")
    board = R.pipeline(engine, TN, MGR)
    assert [x["id"] for x in board["columns"]["basvurdu"]] == [a]
    assert R.pipeline(engine, TN, HRW)["total"] == 3
    assert R.pipeline(engine, TN, NOBODY)["total"] == 0
    with pytest.raises(H.HrError):
        R.detail(engine, TN, MGR, b, None)
    d = R.detail(engine, TN, MGR, a, None)
    assert d["email"] is None and d["can"]["decide"] and not d["can"]["downloadOriginal"]
    assert R.detail(engine, TN, HRW, a, None)["email"] == "ayse@example.com"
    # Görüşmeci mülakata eklenince (pozisyon ekibinde olmasa da) o adayı görür.
    outsider = H.Who("disaridan", "Dışarıdan", False, frozenset({R.F_SEE}))
    with pytest.raises(H.HrError):
        R.detail(engine, TN, outsider, b, None)
    R.create_interview(engine, TN, HRW, {"candidateId": b, "startsAt": "2026-10-01T10:00:00+03:00", "interviewers": ["disaridan"]})
    assert R.detail(engine, TN, outsider, b, None)["id"] == b
    assert c not in [x["id"] for x in R.pipeline(engine, TN, MGR)["columns"]["basvurdu"]]


def test_stage_change_is_a_person_decision_and_hiring_creates_an_employee(engine):
    pos = _position(engine)
    a = _candidate(engine, pos["id"])
    with pytest.raises(H.HrError):
        R.change_stage(engine, TN, IV, a, {"stage": "on_eleme"})                 # görmek karar vermek değil
    R.change_stage(engine, TN, MGR, a, {"stage": "on_eleme", "reason": "deneyim uygun"})
    with pytest.raises(H.HrError, match="sonucu seçin"):
        R.change_stage(engine, TN, HRW, a, {"stage": "sonuc"})
    out = R.change_stage(engine, TN, HRW, a, {"stage": "sonuc", "outcome": "ise_alindi", "startDate": "2026-11-01"})
    emp = H.get_employee(engine, TN, out["employeeId"])
    assert emp["displayName"] == "Ayşe Yılmaz" and emp["title"] == pos["title"] and emp["startDate"] == "2026-11-01"
    with pytest.raises(H.HrError):
        R.change_stage(engine, TN, HRW, a, {"stage": "mulakat"})
    log = R.detail(engine, TN, HRW, a, None)["stageLog"]
    assert [(x["from"], x["to"], x["actor"]) for x in log] == [(None, "basvurdu", "ik"), ("basvurdu", "on_eleme", "mudur"),
                                                               ("on_eleme", "sonuc", "ik")]


def test_interview_notes_stay_hidden_until_own_note_is_submitted(engine):
    pos = _position(engine)
    a = _candidate(engine, pos["id"])
    iv = R.create_interview(engine, TN, HRW, {"candidateId": a, "startsAt": "2026-10-01T10:00:00+03:00",
                                             "interviewers": ["mudur", "gorusmeci"]})
    R.save_note(engine, TN, MGR, iv["id"], {"scores": {"Redaksiyon deneyimi": 4}, "note": "iyi", "submit": True})
    seen = R.detail(engine, TN, IV, a, None)["interviews"][0]
    assert seen["notes"] == [] and seen["hiddenOthers"]
    R.save_note(engine, TN, IV, iv["id"], {"scores": {"Redaksiyon deneyimi": 3}, "note": "orta", "submit": True})
    seen = R.detail(engine, TN, IV, a, None)["interviews"][0]
    assert {n["author"] for n in seen["notes"]} == {"mudur", "gorusmeci"}
    with pytest.raises(H.HrError):
        R.save_note(engine, TN, IV, iv["id"], {"note": "değiştir"})               # teslim edilen not değişmez
    with pytest.raises(H.HrError):
        R.save_note(engine, TN, HRW, iv["id"], {"scores": {"x": 9}})
    with pytest.raises(H.HrError):
        R.save_note(engine, TN, HRW, iv["id"], {"note": "görüşmeci değilim"})


# ------------------------------------------------------------------ saklama ve imha


def test_retention_and_purge_keep_the_row_but_remove_personal_data(engine):
    pos = _position(engine)
    a = _candidate(engine, pos["id"])
    R.add_file(engine, TN, HRW, a, "cv.txt", CV.encode("utf-8"), 20)
    R.change_stage(engine, TN, HRW, a, {"stage": "sonuc", "outcome": "ret"})
    assert R.detail(engine, TN, HRW, a, None)["retention"]["until"] is None      # süre girilmedi → imha yok
    assert R.due_candidates(engine, TN, H.now()) == []
    H.put_retention(engine, TN, "kvkk", [{"dataClass": "aday_ret", "keepDays": 30, "legalBasis": "Politika"}])
    assert R.due_candidates(engine, TN, H.now()) == []
    assert R.due_candidates(engine, TN, H.now() + timedelta(days=31)) == [a]
    with engine.begin() as c:
        c.execute(R.CANDIDATES.update().where(R.CANDIDATES.c.id == a).values(outcome_at=H.now() - timedelta(days=40)))
    out = H.run_due_purge(engine, TN)
    assert {x["key"]: x["purged"] for x in out["classes"]}["aday"] == 1
    with engine.connect() as c:
        row = c.execute(sa.select(R.CANDIDATES).where(R.CANDIDATES.c.id == a)).first()
        files = c.execute(sa.select(sa.func.count()).select_from(R.FILES).where(R.FILES.c.candidate_id == a)).scalar()
    assert row.purged_at is not None and row.email is None and row.full_name == "(imha edildi)" and files == 0
    assert R.pipeline(engine, TN, HRW)["total"] == 0


def test_pool_consent_extends_and_its_withdrawal_purges_immediately(engine):
    pos = _position(engine)
    a = _candidate(engine, pos["id"])
    H.put_retention(engine, TN, "kvkk", [{"dataClass": "aday_ret", "keepDays": 30, "legalBasis": "P"},
                                         {"dataClass": "aday_havuz", "keepDays": 730, "legalBasis": "Açık rıza"}])
    H.publish_notice(engine, TN, "kvkk", {"audience": "aday", "title": "Aday aydınlatma", "body": "..."})
    consent = H.add_consent(engine, TN, "ik", {"subjectType": "aday", "subjectId": a, "purpose": "aday_havuzu", "channel": "eposta"},
                            lambda st, sid: H.subject_exists(engine, TN, st, sid))
    R.change_stage(engine, TN, HRW, a, {"stage": "sonuc", "outcome": "ret"})
    ret = R.detail(engine, TN, HRW, a, None)["retention"]
    assert ret["class"] == "aday_havuz"
    assert R.due_candidates(engine, TN, H.now() + timedelta(days=60)) == []
    H.withdraw_consent(engine, TN, "ik", consent["id"])
    assert R.due_candidates(engine, TN, H.now() + timedelta(seconds=1)) == [a]


def test_delete_on_request_needs_kvkk_and_leaves_a_record(engine):
    pos = _position(engine)
    a = _candidate(engine, pos["id"])
    no_kvkk = H.Who("ik2", "İK", False, frozenset({R.F_ALL}))
    with pytest.raises(H.HrError):
        R.delete_on_request(engine, TN, no_kvkk, a, "talep")
    with pytest.raises(H.HrError):
        R.delete_on_request(engine, TN, HRW, a, " ")
    assert R.delete_on_request(engine, TN, HRW, a, "12.10 e-postası") == 1
    runs = H.purge_runs(engine, TN)["items"]
    assert runs[0]["dataClass"] == "talep" and runs[0]["ids"] == [a] and runs[0]["actor"] == "ik"


def test_export_contains_everything_for_the_data_subject(engine):
    pos = _position(engine)
    a = _candidate(engine, pos["id"])
    R.add_file(engine, TN, HRW, a, "cv.txt", CV.encode("utf-8"), 20)
    H.log_access(engine, TN, "ik", "aday", a, "goruntule")
    out = R.export_candidate(engine, TN, HRW, a)
    assert out["email"] == "ayse@example.com" and out["files"][0]["originalText"].startswith("Ayşe")
    assert len(out["accessLog"]) == 1 and "can" not in out
    with pytest.raises(H.HrError):
        R.export_candidate(engine, TN, MGR, a)


# ------------------------------------------------------------------ e-postadan başvuru


def test_intake_creates_once_matches_position_by_subject_and_skips_bad_files(engine):
    pos = _position(engine)
    boss = H.Who("ik", "İK", False, frozenset({R.F_POS_OPEN}))
    R.position_transition(engine, TN, boss, pos["id"], "submit")
    R.position_transition(engine, TN, GM, pos["id"], "approve")
    body = {"messageId": "<abc@mail>", "from": {"name": "Ayşe Yılmaz", "email": "Ayse@Example.com"},
            "subject": "Çocuk kitapları editörü başvurusu", "body": "Merhaba, özgeçmişim ekte.",
            "attachments": [{"filename": "cv.txt", "contentBase64": base64.b64encode(CV.encode("utf-8")).decode()},
                            {"filename": "foto.jpg", "contentBase64": base64.b64encode(b"\xff\xd8").decode()}]}
    out = R.intake(engine, TN, body, "Timaş", 20)
    assert out["created"] and out["positionId"] == pos["id"] and out["files"] == 2
    assert [s["filename"] for s in out["skipped"]] == ["foto.jpg"] and out["ackDraft"] is None   # şablon yok → taslak yok
    again = R.intake(engine, TN, body, "Timaş", 20)
    assert again == {"id": out["id"], "created": False, "files": 0, "skipped": []}
    d = R.detail(engine, TN, HRW, out["id"], None)
    assert d["source"] == "eposta" and d["email"] == "ayse@example.com"
    assert any(TCKN in f["originalText"] and TCKN not in f["maskedText"] for f in d["files"])
    with pytest.raises(H.HrError):
        R.intake(engine, TN, {**body, "messageId": ""}, "Timaş", 20)


# ------------------------------------------------------------------ şablon ve yazışma


def test_letters_come_from_templates_and_offers_need_a_second_person(engine):
    pos = _position(engine)
    a = _candidate(engine, pos["id"])
    with pytest.raises(H.HrError, match="şablon yok"):
        R.draft_letter(engine, TN, HRW, a, "ret", {}, "Timaş")
    R.save_template(engine, TN, "ik", {"kind": "ret", "name": "Ret", "body": X.STARTERS["ret"], "state": "yururlukte"})
    R.save_template(engine, TN, "ik", {"kind": "teklif", "name": "Teklif", "body": X.STARTERS["teklif"], "state": "yururlukte"})
    m = R.draft_letter(engine, TN, HRW, a, "ret", {}, "Timaş Yayınları")
    assert "Sayın Ayşe Yılmaz" in m["body"] and pos["title"] in m["body"] and m["status"] == "taslak"
    sent = R.message_action(engine, TN, HRW, m["id"], "sent", {"channel": "eposta"})
    assert sent["status"] == "gonderildi" and sent["sentBy"] == "ik"
    offer = R.draft_letter(engine, TN, HRW, a, "teklif", {}, "Timaş Yayınları")
    assert "imza" not in offer["missing"]
    with pytest.raises(H.HrError, match="onaylanmalı"):
        R.message_action(engine, TN, HRW, offer["id"], "sent", {})
    R.message_action(engine, TN, HRW, offer["id"], "submit", {})
    self_approver = H.Who("ik", "İK", False, ALL_KEYS | {R.F_OFFER_APPROVE})
    with pytest.raises(H.HrError, match="siz onaylayamazsınız"):
        R.message_action(engine, TN, self_approver, offer["id"], "approve", {})
    with pytest.raises(H.HrError):
        R.message_action(engine, TN, GM, offer["id"], "approve", {})             # GM adayı görmüyor
    gm = H.Who("gm", "GM", False, frozenset({R.F_OFFER_APPROVE, R.F_ALL}))
    assert R.message_action(engine, TN, gm, offer["id"], "approve", {})["status"] == "onaylandi"
    assert R.message_action(engine, TN, HRW, offer["id"], "sent", {"channel": "elden"})["status"] == "gonderildi"


def test_soften_keeps_facts_or_falls_back():
    text = "Sayın Ayşe Yılmaz, 12.10.2026 tarihli görüşme"
    ok, note = X.soften(text, ["Ayşe Yılmaz", "12.10.2026"], lambda m: "Sevgili Ayşe Yılmaz, 12.10.2026 tarihli görüşmemiz")
    assert note is None and ok.startswith("Sevgili")
    kept, note = X.soften(text, ["Ayşe Yılmaz"], lambda m: "Sevgili aday, görüşmemiz")
    assert kept == text and "kayboldu" in note
    kept, note = X.soften(text, ["Ayşe Yılmaz"], lambda m: "Sayın Ayşe Yılmaz, 12.10.2026 görüşmesi, maaş 50000")
    assert kept == text and "sayı" in note


def test_ilan_template_with_discriminatory_text_cannot_go_live(engine):
    with pytest.raises(H.HrError, match="ayrımcı"):
        R.save_template(engine, TN, "ik", {"kind": "ilan", "name": "İlan", "body": "Bay aday aranıyor", "state": "yururlukte"})
    t, _ = R.save_template(engine, TN, "ik", {"kind": "ilan", "name": "İlan", "body": "Editör aranıyor", "state": "taslak"})
    t2, diff = R.save_template(engine, TN, "ik", {"body": "Editör aranıyor.", "state": "yururlukte"}, t["id"])
    assert t2["version"] == 2 and diff == {"metin": True, "durum": True}


# ------------------------------------------------------------------ hatırlatma


def test_reminders_need_a_threshold_and_carry_no_candidate_data(engine):
    pos = _position(engine)
    a = _candidate(engine, pos["id"])
    assert R.due_reminders(engine, TN, None) == []
    with engine.begin() as c:
        c.execute(R.CANDIDATES.update().where(R.CANDIDATES.c.id == a).values(stage_since=H.now() - timedelta(days=9)))
    items = R.due_reminders(engine, TN, 5)
    assert len(items) == 1
    text = R.reminder_text(items, 5, "https://portal/timas/ik/ise-alim")
    assert "Ayşe" not in text and pos["title"] in text and "1 aday" in text
    R.mark_reminded(engine, TN, items)
    assert R.due_reminders(engine, TN, 5) == []
    counters = R.pipeline(engine, TN, HRW, sla_days=5)["counters"]
    assert counters["overSla"] == 1 and counters["slaDays"] == 5
    assert R.pipeline(engine, TN, HRW)["counters"]["overSla"] is None


# ------------------------------------------------------------------ köprü


def test_bridge_gates_hr_pages_and_system_endpoints(monkeypatch, store, settings):
    from fastapi.testclient import TestClient

    from semantic_bridge import access as A
    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod
    from semantic_bridge.app import Runtime, create_app
    from semantic_layer.candidates.llm_client import FakeLlm
    from semantic_layer.tests.conftest import TENANT

    users = {"timas_session=a": "ayse", "timas_session=z": "zekiai"}
    monkeypatch.setattr(board_mod, "_fetch_user", lambda cookie: users.get(cookie))
    monkeypatch.setattr(board_mod, "_fetch_session", lambda cookie: {"username": users.get(cookie), "displayName": "x"})
    monkeypatch.setattr(admin_mod, "admins", lambda: ["zekiai"])
    monkeypatch.delenv("SEMANTIC_CALLER_TOKEN", raising=False)
    monkeypatch.delenv("HR_ADMIN_SEES_PERSONAL", raising=False)
    A._ready.clear()
    A.invalidate()
    client = TestClient(create_app(Runtime(settings, store=store, llm=FakeLlm([""]))))
    a, z = {"cookie": "timas_session=a"}, {"cookie": "timas_session=z"}
    # Herkes rolü kurulumda bütün sayfaları açar, İK sayfalarını açmaz.
    assert client.get("/api/v1/hr/recruit/pipeline", headers=a).status_code == 403
    assert client.get("/api/v1/hr/employees", headers=a).status_code == 403
    assert client.get("/api/v1/hr/me", headers=a).status_code == 200
    assert client.post("/api/v1/hr/purge/run-due", headers=a).status_code == 403
    assert client.post("/api/v1/hr/recruit/intake", json={}, headers=a).status_code == 403
    # Yönetici sayfayı açar ama duyarlı anahtar rolünde yoksa aday ekleyemez.
    assert client.get("/api/v1/hr/recruit/pipeline", headers=z).status_code == 200
    made = client.post("/api/v1/hr/recruit/candidates", json={"fullName": "X"}, headers=z)
    assert made.status_code == 403
    meta = client.get("/api/v1/hr/recruit/meta", headers=z).json()
    assert meta["me"]["can"]["all"] is False and meta["me"]["can"]["positionOpen"] is True
    # Zamanlayıcı ucu çerezsiz çalışır; tutanak yazılır.
    run = client.post("/api/v1/hr/purge/run-due")
    assert run.status_code == 200 and run.json()["ok"]
    assert client.post("/api/v1/hr/recruit/reminders/run-due").json()["mail"] == "esik_yok"
    bad = client.post("/api/v1/hr/recruit/intake", json={"from": {"email": "x@y.com"}})
    assert bad.status_code == 422
    with store.engine.connect() as c:
        assert c.execute(sa.select(sa.func.count()).select_from(H.PURGE_RUNS)).scalar() >= 1
    A._ready.clear()
    A.invalidate()
    _ = TENANT
