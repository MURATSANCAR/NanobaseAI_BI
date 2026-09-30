"""Yazar giriş panosu süzgeçleri: kartta marka ve proje türü CRM'den gelir (süzme ekranda yapılır)."""

from __future__ import annotations

from datetime import date

from semantic_bridge import editorial_intake as m

PID = "0a1b2c3d-0000-0000-0000-000000000001"


def _row(**kw):
    r = {"new_projeId": PID, "new_name": "Deneme", "yazar": "Yazar", "statuscode": "x", "durum_kod": 100000011,
         "rapor_kod": 1, "CreatedOn": "2026-03-04T10:00:00", "ModifiedOn": "2026-03-05T10:00:00",
         "marka": "Timaş Çocuk", "tur_kod": 1}
    r.update(kw)
    return r


def test_facts_sql_reads_brand_and_project_type_label():
    sql = m.facts_sql("Timas_MSCRM.dbo", "2025-01-01")
    assert "LEFT JOIN Timas_MSCRM.dbo.new_markaBase mk ON mk.new_markaId = j.new_yayinciid" in sql
    assert "mk.new_name AS marka" in sql
    assert "CAST(j.new_projeturu AS int) AS tur_kod" in sql
    # Köprünün sorgu yolu katalogda olmayan tabloyu reddeder (2026-09-29 aday köprüde görüldü): etiket sorguda okunmaz.
    assert "StringMapBase" not in sql and "EntityView" not in sql
    # Kapsam değişmedi: süzgeçler sorguya parametre olarak girmez.
    assert "j.statecode = 0 AND ISNULL(j.new_projetipi, 1) IN (1, 2) AND j.CreatedOn >= '2025-01-01'" in sql


def test_card_carries_brand_and_type_and_empty_stays_none():
    f = m.fact(_row())
    card = m.summarize(f, {}, date(2026, 9, 29), 14)
    assert (card["brand"], card["projectType"]) == ("Timaş Çocuk", "Editoryal")
    empty = m.summarize(m.fact(_row(marka="  ", tur_kod=None)), {}, date(2026, 9, 29), 14)
    assert (empty["brand"], empty["projectType"]) == (None, None)
    # CRM'e yeni bir tür eklenirse boşa düşmez, kendi değeriyle görünür.
    assert m.fact(_row(tur_kod=3))["projectType"] == "Pazarlama"
    assert m.fact(_row(tur_kod=7))["projectType"] == "Diğer tür (7)"


def test_board_lists_carry_fields_and_old_snapshot_without_them_still_reads():
    new = m.fact(_row())
    old = {k: v for k, v in m.fact(_row(new_projeId="0a1b2c3d-0000-0000-0000-000000000002")).items()
           if k not in ("brand", "projectType")}
    b = m.board({"facts": [new, old]}, {}, "", today=date(2026, 9, 29), late_days=14)
    rows = b["items"] + b["completed"] + b["closed"]
    assert sorted((r["brand"] or "") for r in rows) == ["", "Timaş Çocuk"]
    assert all("projectType" in r for r in rows)
