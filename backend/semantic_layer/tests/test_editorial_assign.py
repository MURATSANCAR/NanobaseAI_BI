"""M2 editör atama (yalnız CRM'den okunur) ve Masam › Görevlerim.

Sözleşme (2026-09-29): kim hangi projenin editörü CRM'dedir; portal atama yapmaz. Masam'daki görev listesi
CRM'de editörü oturumdaki kişi olan projelerdir; durum, termin, sayfa ve not kişinin kendi takibidir ve
yalnız CRM'de kendisine yazılı projede tutulabilir. Termini olan kayıtta termin değişikliği gerekçesiz
kaydedilmez; 30 günden eski kapanmış kayıt Masam'dan düşer.
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
KIT = "DDDDDDDD-DDDD-DDDD-DDDD-DDDDDDDDDDDD"
MARKA = "EEEEEEEE-EEEE-EEEE-EEEE-EEEEEEEEEEEE"
ME = {"id": ED1, "name": "Ayşe"}


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    A._ready.clear()
    A.ensure(e)
    return e


def project(pid=P1, kit=True, crm_editor=ED1):
    return {"id": pid, "name": "Deneme", "kitaplik": {"id": KIT, "name": "Çocuk Kitaplığı"} if kit else None,
            "marka": {"id": MARKA, "name": "Timaş"}, "crmEditorId": crm_editor, "crmEditor": "Ayşe", "pages": 120,
            "status": "İş Planı Çalışıyor"}


# ------------------------------------------------------------------ Masam › Görevlerim


def test_yalniz_crm_editoru_takip_edebilir(engine):
    with pytest.raises(A.AssignError) as e:
        A.save_mine(engine, T, "ayse", project=project(crm_editor=ED2), editor=ME, body={"status": "calisiyor"})
    assert e.value.status == 403
    t = A.save_mine(engine, T, "ayse", project=project(), editor=ME, body={"status": "calisiyor"})
    assert t["status"] == "calisiyor" and t["source"] == "crm" and t["pages"] == 120
    # ikinci değişiklik aynı kaydı günceller, yeni kayıt açmaz
    t2 = A.save_mine(engine, T, "ayse", project=project(), editor=ME, body={"due": "2026-11-01"})
    assert t2["id"] == t["id"] and t2["due"] == "2026-11-01"
    assert len(A.tasks(engine, T, editor_id=ED1)) == 1


def test_termin_degisikligi_gerekce_ister(engine):
    t = A.save_mine(engine, T, "ayse", project=project(), editor=ME, body={"due": "2026-10-31"})
    with pytest.raises(A.AssignError):
        A.update_task(engine, T, "ayse", t["id"], {"due": "2026-11-15"})
    out = A.update_task(engine, T, "ayse", t["id"], {"due": "2026-11-15", "reason": "Metin geç geldi"})
    assert out["due"] == "2026-11-15"
    log = A.task_history(engine, T, t["id"])[0]
    assert log["detail"]["due"] == ["2026-10-31", "2026-11-15"] and log["detail"]["reason"] == "Metin geç geldi"
    with pytest.raises(A.AssignError):
        A.update_task(engine, T, "ayse", t["id"], {"start": "2026-12-01"})  # termin başlangıçtan önce kalır


def test_pano_crm_projelerinden_kurulur():
    today = date(2026, 9, 29)
    p1, p2, p3 = project(P1), project(P2), project("33333333-3333-3333-3333-333333333333")
    mine = [
        {"id": "a", "projectId": P1, "status": "calisiyor", "createdAt": "2026-09-01", "doneAt": None, "updatedAt": None,
         "due": "2026-10-01", "overdue": False},
        # P2: 40 gün önce tamamlanmış → Masam'dan düşer
        {"id": "b", "projectId": P2, "status": "tamamlandi", "createdAt": "2026-07-01", "doneAt": "2026-08-20T10:00:00+00:00",
         "updatedAt": "2026-08-20T10:00:00+00:00", "due": None, "overdue": False},
        # başka projedeki (CRM'de artık size yazılı değil) kayıt görünmez
        {"id": "c", "projectId": "44444444-4444-4444-4444-444444444444", "status": "sirada", "createdAt": "2026-09-01",
         "doneAt": None, "updatedAt": None, "due": None, "overdue": False},
    ]
    out = A.board([p1, p2, p3], mine, today=today)
    assert [x["projectId"] for x in out] == [P1, p3["id"]]
    assert out[0]["id"] == "a" and out[0]["status"] == "calisiyor" and out[0]["project"] is p1
    # kaydı olmayan proje «sırada», kimliksiz, CRM sayfasıyla
    assert out[1]["id"] is None and out[1]["status"] == "sirada" and out[1]["pages"] == 120
    assert out[1]["category"] == "Kitaplık: Çocuk Kitaplığı"


def test_acik_kayit_kapanmistan_once_gelir():
    mine = [
        {"id": "eski", "projectId": P1, "status": "tamamlandi", "createdAt": "2026-09-20", "doneAt": "2026-09-25",
         "updatedAt": "2026-09-25", "due": None, "overdue": False},
        {"id": "yeni", "projectId": P1, "status": "beklemede", "createdAt": "2026-09-10", "doneAt": None,
         "updatedAt": None, "due": None, "overdue": False},
    ]
    assert A.board([project()], mine, today=date(2026, 9, 29))[0]["id"] == "yeni"


# ------------------------------------------------------------------ CRM sorguları


def test_editorsuz_sorgusu_durum_ve_kategoriyi_suzer():
    sql = A.pending_list_sql("Timas_MSCRM.dbo", 0, statuses=[100000020], since_year=2024, q="a'b",
                             category=f"kitaplik:{KIT}")
    assert "j.new_editoru IS NULL" in sql and "j.statuscode IN (100000020)" in sql and "j.statecode = 0" in sql
    assert "NOT IN" not in sql  # portal ataması kalmadı: CRM tek kaynak
    assert f"j.new_Kitaplik = '{KIT}'" in sql and "a''b" in sql
    assert "Timas_MSCRM.dbo.new_projeBase" in sql


def test_sorguya_gecersiz_kimlik_girmez():
    with pytest.raises(A.AssignError):
        A.pending_list_sql("Timas_MSCRM.dbo", 0, statuses=[], since_year=2024, category="tur:1")
    with pytest.raises(A.AssignError):
        A.pending_list_sql("Timas_MSCRM.dbo", 0, statuses=[], since_year=2024, category="kitaplik:x' OR 1=1 --")


def test_crm_kullanicisi_hesap_adiyla_eslesir():
    rows = {"records": [
        {"SystemUserId": ED2, "FullName": "Başka", "DomainName": "TIMAS\\xayse", "IsDisabled": False},
        {"SystemUserId": ED1, "FullName": "Ayşe", "DomainName": "TIMAS\\ayse", "IsDisabled": False},
    ]}
    me = A.crm_me("Timas_MSCRM.dbo", lambda sql: rows, "Ayse")
    assert me == {"id": ED1, "name": "Ayşe", "disabled": False}
    assert A.crm_me("Timas_MSCRM.dbo", lambda sql: {"records": []}, "ayse") is None
