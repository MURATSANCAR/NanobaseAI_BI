"""ZEKI-19/24: kurul gündeminde editör raporu panoyla aynı kuraldan okunur (CRM «İç rapor» ya da portal işareti);
kanıt yoksa satıra «CRM'de yok» yazılmaz, ek dosya sayısı ayrıca gelir."""

from __future__ import annotations

from semantic_bridge import editorial_intake as m

A = "0A1B2C3D-0000-0000-0000-00000000000A"
B = "0a1b2c3d-0000-0000-0000-00000000000b"
C = "0a1b2c3d-0000-0000-0000-00000000000c"


def _r(pid, rapor, note=None):
    return {"new_yayinkurulutoplantilariId": pid[:-1] + "f", "proje_id": pid, "kod": 1, "proje": "P", "rapor_kod": rapor,
            "new_toplantikararnotu": note}


def test_report_sources_and_files():
    rows = [_r(A, 3), _r(B, 2), _r(C, None)]
    marks = {B.lower(): {3: {"on": "2026-09-01", "by": "ed", "display": "Editör Ad"}}}
    out = m.agenda(rows, None, marks, {A.lower(): 2})
    a, b, c = out
    assert (a["report"], a["reportSource"], a["files"]) == (True, "crm", 2)
    assert (b["report"], b["reportSource"], b["reportBy"], b["reportRequested"]) == (True, "portal", "Editör Ad", False)
    assert (c["report"], c["reportSource"], c["reportRequested"], c["files"]) == (False, None, False, 0)


def test_requested_and_unread_files():
    out = m.agenda([_r(C, 2)], None, {}, None)
    assert out[0]["reportRequested"] is True and out[0]["files"] is None


def test_note_html_is_plain():
    out = m.agenda([_r(C, None, "<p>Bas&inodot;ls&inodot;n.</p><p>&Ccedil;ok iyi</p>")], None)
    assert out[0]["note"] == "Basılsın.\nÇok iyi"


def test_files_sql_guards_ids():
    sql = m.project_files_sql("Timas_MSCRM.dbo", [A])
    assert "AnnotationBase" in sql and A.lower() in sql and "IsDocument = 1" in sql
