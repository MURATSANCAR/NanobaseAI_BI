"""M2 editör atama: çakışma, takvim, öneri puanı, kural sürümü ve görev kuralları.

Sözleşme: atama ve termin köprünün tablolarındadır (CRM'e yazılmaz); izinle ya da kapasiteyi aşan eşzamanlı
işle kesişen atama çakışmadır ve yalnız açıkça «yine de» denirse kaydedilir; termini olmayan açık görev
kapasiteyi süresiz tutar; kural tablosu taslak → onay ile yürürlüğe girer, önceki sürüm arşive geçer; termini
olan görevde termin değişikliği gerekçesiz kaydedilmez.
"""

from __future__ import annotations

from datetime import date

import pytest

from semantic_bridge import editorial_assign as A
from semantic_layer.store.catalog_store import open_store

T = "t1"
P1 = "11111111-1111-1111-1111-111111111111"
P2 = "22222222-2222-2222-2222-222222222222"
ED1 = "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA"
ED2 = "BBBBBBBB-BBBB-BBBB-BBBB-BBBBBBBBBBBB"
ED3 = "CCCCCCCC-CCCC-CCCC-CCCC-CCCCCCCCCCCC"
KIT = "DDDDDDDD-DDDD-DDDD-DDDD-DDDDDDDDDDDD"
MARKA = "EEEEEEEE-EEEE-EEEE-EEEE-EEEEEEEEEEEE"
D = date.fromisoformat


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    A._ready.clear()
    A.ensure(e)
    return e


def project(pid=P1, kit=True, crm_editor=None):
    return {"id": pid, "name": "Deneme", "kitaplik": {"id": KIT, "name": "Çocuk Kitaplığı"} if kit else None,
            "marka": {"id": MARKA, "name": "Timaş"}, "crmEditorId": crm_editor, "pages": 120}


def task(start, due=None, **kw):
    return {"start": start, "due": due, "createdAt": start, **kw}


# ------------------------------------------------------------------ çakışma


def test_izin_araligi_kesisirse_cakisma():
    leave = [{"start": "2026-10-05", "end": "2026-10-09", "reason": "Yıllık izin"}]
    out = A.conflicts([], leave, None, D("2026-10-01"), D("2026-10-06"), today=D("2026-09-27"))
    assert [c["kind"] for c in out] == ["izin"]
    assert out[0]["from"] == "2026-10-05" and out[0]["to"] == "2026-10-06"
    assert A.conflicts([], leave, None, D("2026-10-10"), D("2026-10-20"), today=D("2026-09-27")) == []


def test_kapasite_asimi_ilk_gun_ve_en_kotu_sayi():
    open_tasks = [task("2026-10-01", "2026-10-10"), task("2026-10-05", "2026-10-20")]
    out = A.conflicts(open_tasks, [], 2, D("2026-10-03"), D("2026-10-15"), today=D("2026-09-27"))
    assert len(out) == 1 and out[0]["kind"] == "kapasite"
    assert out[0]["from"] == "2026-10-05" and out[0]["count"] == 3 and out[0]["capacity"] == 2
    # Aralık, iki işin kesiştiği günlere değmiyorsa aşım yok.
    assert A.conflicts(open_tasks, [], 2, D("2026-10-11"), D("2026-10-30"), today=D("2026-09-27")) == []


def test_terminsiz_gorev_kapasiteyi_suresiz_tutar():
    out = A.conflicts([task("2026-01-01", None)], [], 1, D("2027-06-01"), D("2027-06-02"), today=D("2026-09-27"))
    assert out and out[0]["kind"] == "kapasite"


def test_kapasite_yoksa_kapasite_denetimi_yok():
    many = [task("2026-10-01", "2026-12-01") for _ in range(20)]
    assert A.conflicts(many, [], None, D("2026-10-02"), D("2026-10-03")) == []


def test_takvim_cakisma_araliklari_birlesir():
    tasks_ = [{**task("2026-10-01", "2026-10-10"), "id": "a"}, {**task("2026-10-03", "2026-10-05"), "id": "b"}]
    leave = [{"id": "x", "start": "2026-10-08", "end": "2026-10-09", "reason": None}]
    cal = A.calendar(tasks_, leave, 1, D("2026-09-28"), D("2026-10-20"), today=D("2026-09-27"))
    assert cal["conflicts"] == [
        {"kind": "kapasite", "from": "2026-10-03", "to": "2026-10-05", "max": 2},
        {"kind": "izin", "from": "2026-10-08", "to": "2026-10-09", "max": 1},
    ]
    assert {b["id"] for b in cal["tasks"]} == {"a", "b"}


# ------------------------------------------------------------------ öneri


def test_oneri_kural_gecmis_ve_musaitligi_tartar():
    editors = {ED1: {"name": "Ayşe"}, ED2: {"name": "Burak"}, ED3: {"name": "Kapalı", "disabled": True}}
    exp = {"byEditor": {ED1: {"total": 10, f"kitaplik:{KIT}": 2}, ED2: {"total": 40, f"kitaplik:{KIT}": 20}}, "names": {}}
    rules = [{"kind": "kitaplik", "id": KIT, "name": "Çocuk", "primary": [ED1], "backup": [ED2]}]
    prof = {ED2: {"capacity": 2, "available": True}}
    busy = {ED2: [task("2026-09-01", "2026-12-31"), task("2026-09-01", "2026-12-31")]}
    out = A.candidates(project(), editors=editors, exp=exp, rules=rules, prof=prof, open_by_editor=busy,
                       leave_by_editor={}, start=D("2026-10-01"), due=D("2026-10-31"), today=D("2026-09-27"))
    ids = [c["id"] for c in out["items"]]
    assert ids == [ED1, ED2]
    assert out["items"][0]["rule"] == "birincil"
    assert out["items"][1]["conflicts"][0]["kind"] == "kapasite"
    assert out["excluded"] == [{"id": ED3, "name": "Kapalı", "reason": "CRM hesabı kapalı"}]
    assert out["category"]["kind"] == "kitaplik"


def test_oneri_kitapligi_olmayan_projede_marka_kurali():
    rules = [{"kind": "marka", "id": MARKA, "name": "Timaş", "primary": [ED2], "backup": []}]
    out = A.candidates(project(kit=False), editors={ED1: {"name": "A"}, ED2: {"name": "B"}}, exp={"byEditor": {}, "names": {}},
                       rules=rules, prof={}, open_by_editor={}, leave_by_editor={}, start=D("2026-10-01"),
                       due=D("2026-10-02"))
    assert out["items"][0]["id"] == ED2 and out["categoryLabel"] == "Marka: Timaş"


def test_atamaya_kapali_profil_disarida():
    out = A.candidates(project(), editors={ED1: {"name": "A"}}, exp={"byEditor": {}, "names": {}}, rules=[],
                       prof={ED1: {"available": False}}, open_by_editor={}, leave_by_editor={},
                       start=D("2026-10-01"), due=D("2026-10-02"))
    assert out["items"] == [] and out["excluded"][0]["reason"].startswith("Atamaya kapalı")


# ------------------------------------------------------------------ kural tablosu


def test_kural_taslak_onay_arsiv(engine):
    r1 = A.clean_rules([{"kind": "kitaplik", "id": KIT, "name": "Çocuk", "primary": [ED1], "backup": [ED1, ED2]}])
    assert r1[0]["backup"] == [ED2]  # birincil yedekte tekrarlanmaz
    v = A.save_draft(engine, T, "ayse", r1, "ilk")
    assert v["draft"]["version"] == 1 and v["active"] is None
    with pytest.raises(A.AssignError) as e:
        A.approve_draft(engine, T, "mudur", 99)
    assert e.value.status == 409
    v = A.approve_draft(engine, T, "mudur", 1)
    assert v["active"]["version"] == 1 and v["active"]["approvedBy"] == "mudur" and v["draft"] is None
    A.save_draft(engine, T, "ayse", r1, "ikinci")
    v = A.approve_draft(engine, T, "mudur", 2)
    assert v["active"]["version"] == 2 and [h["version"] for h in v["history"]] == [1]


def test_kural_dogrulama(engine):
    with pytest.raises(A.AssignError):
        A.clean_rules([{"kind": "kitaplik", "id": KIT, "primary": []}])
    with pytest.raises(A.AssignError):
        A.clean_rules([{"kind": "tur", "id": KIT, "primary": [ED1]}])
    with pytest.raises(A.AssignError):
        A.clean_rules([{"kind": "kitaplik", "id": KIT, "primary": [ED1]}, {"kind": "kitaplik", "id": KIT, "primary": [ED2]}])
    with pytest.raises(A.AssignError):
        A.clean_rules([{"kind": "kitaplik", "id": KIT, "primary": [ED1]}], known_editors={ED2})


def test_veriden_kural_onerisi_kapali_hesabi_atlar():
    exp = {"byEditor": {ED1: {f"kitaplik:{KIT}": 5}, ED2: {f"kitaplik:{KIT}": 9}, ED3: {f"kitaplik:{KIT}": 3}}}
    users = {ED1: {"disabled": False}, ED2: {"disabled": True}, ED3: {"disabled": False}}
    out = A.suggest_rules(exp, users, [{"kind": "kitaplik", "id": KIT, "name": "Çocuk"}])
    assert out == [{"kind": "kitaplik", "id": KIT, "name": "Çocuk", "primary": [ED1], "backup": [ED3]}]


# ------------------------------------------------------------------ atama ve görev


def _assign(engine, editor=ED1, role="editor", found=None, force=False, pid=P1):
    return A.assign(engine, T, "mudur", project=project(pid), editor={"id": editor, "name": "Ayşe"}, role=role,
                    start=D("2026-10-01"), due=D("2026-10-31"), pages=120, note=None, found=found or [], force=force)


def test_cakisma_varsa_zorlamadan_kaydetmez(engine):
    found = [{"kind": "izin", "text": "x"}]
    with pytest.raises(A.AssignError) as e:
        _assign(engine, found=found)
    assert e.value.status == 409 and e.value.data == {"conflicts": found}
    t = _assign(engine, found=found, force=True)
    assert t["status"] == "sirada" and t["source"] == "atama"
    assert A.task_history(engine, T, t["id"])[0]["detail"]["force"] is True


def test_projede_tek_acik_editor_gorevi(engine):
    _assign(engine)
    with pytest.raises(A.AssignError):
        _assign(engine)  # aynı kişi
    with pytest.raises(A.AssignError):
        _assign(engine, editor=ED2)  # ikinci editör
    d = _assign(engine, editor=ED2, role="destek")
    assert d["role"] == "destek"
    assert A.open_project_ids(engine, T) == [P1]


def test_termin_degisikligi_gerekce_ister(engine):
    t = _assign(engine)
    with pytest.raises(A.AssignError):
        A.update_task(engine, T, "ayse", t["id"], {"due": "2026-11-15"})
    out = A.update_task(engine, T, "ayse", t["id"], {"due": "2026-11-15", "reason": "Metin geç geldi"})
    assert out["due"] == "2026-11-15"
    log = A.task_history(engine, T, t["id"])[0]
    assert log["detail"]["due"] == ["2026-10-31", "2026-11-15"] and log["detail"]["reason"] == "Metin geç geldi"
    with pytest.raises(A.AssignError):
        A.update_task(engine, T, "ayse", t["id"], {"start": "2026-12-01"})  # termin başlangıçtan önce kalır


def test_tamamlanan_gorev_acik_sayilmaz(engine):
    t = _assign(engine)
    A.update_task(engine, T, "ayse", t["id"], {"status": "tamamlandi"})
    assert A.tasks(engine, T, open_only=True) == []
    assert A.get_task(engine, T, t["id"])["doneAt"]


def test_panoya_alma_yalniz_crm_editoru(engine):
    with pytest.raises(A.AssignError) as e:
        A.adopt(engine, T, "ayse", project=project(crm_editor=ED2), editor={"id": ED1, "name": "Ayşe"})
    assert e.value.status == 403
    t = A.adopt(engine, T, "ayse", project=project(crm_editor=ED1), editor={"id": ED1, "name": "Ayşe"})
    assert t["source"] == "crm" and t["due"] is None


def test_profil_kapasite_ve_izin(engine):
    with pytest.raises(A.AssignError):
        A.save_profile(engine, T, "mudur", ED1, "Ayşe", {"capacity": 0})
    p = A.save_profile(engine, T, "mudur", ED1, "Ayşe", {"capacity": "4", "available": True})
    assert p["capacity"] == 4
    with pytest.raises(A.AssignError):
        A.add_absence(engine, T, "ayse", ED1, {"start": "2026-10-10", "end": "2026-10-01"})
    a = A.add_absence(engine, T, "ayse", ED1, {"start": "2026-10-01", "end": "2026-10-10", "reason": "İzin"})
    assert A.absence_owner(engine, T, a["id"]) == ED1
    assert len(A.absences(engine, T, editor_id=ED1, start=D("2026-10-05"))) == 1
    assert A.absences(engine, T, editor_id=ED1, start=D("2026-10-11")) == []
    A.delete_absence(engine, T, a["id"])
    assert A.absences(engine, T) == []


# ------------------------------------------------------------------ CRM sorguları


def test_bekleyen_sorgusu_acik_gorevleri_ve_kategoriyi_suzer():
    sql = A.pending_list_sql("Timas_MSCRM.dbo", 0, statuses=[100000020], since_year=2024, exclude=[P1],
                             q="a'b", category=f"kitaplik:{KIT}")
    assert "j.new_editoru IS NULL" in sql and "j.statuscode IN (100000020)" in sql
    assert f"NOT IN ('{P1}')" in sql and f"j.new_Kitaplik = '{KIT}'" in sql and "a''b" in sql
    assert "Timas_MSCRM.dbo.new_projeBase" in sql


def test_sorguya_gecersiz_kimlik_girmez():
    with pytest.raises(Exception):
        A.pending_list_sql("Timas_MSCRM.dbo", 0, statuses=[], since_year=2024, exclude=["x' OR 1=1 --"])
    with pytest.raises(A.AssignError):
        A.pending_list_sql("Timas_MSCRM.dbo", 0, statuses=[], since_year=2024, exclude=[], category="tur:1")


def test_crm_kullanicisi_hesap_adiyla_eslesir():
    rows = {"records": [
        {"SystemUserId": ED2, "FullName": "Başka", "DomainName": "TIMAS\\xayse", "IsDisabled": False},
        {"SystemUserId": ED1, "FullName": "Ayşe", "DomainName": "TIMAS\\ayse", "IsDisabled": False},
    ]}
    me = A.crm_me("Timas_MSCRM.dbo", lambda sql: rows, "Ayse")
    assert me == {"id": ED1, "name": "Ayşe", "disabled": False}
    assert A.crm_me("Timas_MSCRM.dbo", lambda sql: {"records": []}, "ayse") is None
