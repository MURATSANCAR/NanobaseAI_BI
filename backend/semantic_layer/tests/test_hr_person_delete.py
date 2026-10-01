"""Özlük kaydı silinince M60 izin verisi sahipsiz kalmaz ama yok da olmaz (kullanıcı kararı 2026-09-29: hukuki süreç için
pasife al): kişinin özlük kaydı, belgeleri, izin talepleri, talep geçmişi, izin belgeleri (sağlık raporu olabilir) ve bakiye
defteri aynı işlemde ekranların okuduğu tablolardan çıkar, `semantic_hr_archive`'e (kim, ne zaman, bayt dahil) taşınır;
başkasının talebinde vekil olarak anılışı boşaltılır, eski değer arşive yazılır. Başka kişinin ve başka tenant'ın
satırlarına dokunulmaz; bağlı modül düşerse hiçbir şey taşınmaz.

Veriler yapaydır; bağ `hr_leave.register_hooks` ile kurulur (hr_portal hr_leave'i içe aktarmaz).
"""
from __future__ import annotations

from datetime import date

import pytest
import sqlalchemy as sa

from semantic_bridge import hr_core as H
from semantic_bridge import hr_leave as LV
from semantic_bridge import hr_portal as PT
from semantic_layer.store.catalog_store import open_store

TN = "t1"


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    for m in (H, PT, LV):
        m._ready.discard(e)
    LV.ensure(e)
    PT._person_cleanups.clear()
    LV.register_hooks()
    yield e
    PT._person_cleanups.clear()


def _person(c, pid: str, id_no: str, tenant: str = TN) -> None:
    c.execute(PT.PEOPLE.insert().values(id=pid, tenant_id=tenant, id_no=id_no, ad_soyad=f"Kişi {id_no}", durum="Aktif",
                                        data_json="{}", created_at=H.now(), updated_at=H.now()))


def _request(c, rid: str, pid: str, deputy: str | None = None, tenant: str = TN) -> None:
    t = H.now()
    c.execute(LV.REQUESTS.insert().values(id=rid, tenant_id=tenant, person_id=pid, type_key="rapor", start=date(2026, 9, 1),
                                          end=date(2026, 9, 3), days=3, deputy_person_id=deputy, status="onaylandi",
                                          created_at=t, updated_at=t))
    c.execute(LV.EVENTS.insert().values(tenant_id=tenant, request_id=rid, at=t, actor="u", action="olustur"))
    c.execute(LV.FILES.insert().values(id=f"f-{rid}", tenant_id=tenant, request_id=rid, filename="rapor.pdf", size=3,
                                       blob=b"pdf", uploaded_at=t))
    c.execute(LV.LEDGER.insert().values(tenant_id=tenant, person_id=pid, type_key="yillik", days=-3, reason="kullanim",
                                        request_id=rid, on_date=date(2026, 9, 1), at=t))


@pytest.fixture
def data(engine):
    with engine.begin() as c:
        for pid, no in (("p-ali", "1"), ("p-ayse", "2"), ("p-veli", "3")):
            _person(c, pid, no)
        _request(c, "r-ali-1", "p-ali", deputy="p-ayse")
        _request(c, "r-ali-2", "p-ali")
        _request(c, "r-ayse", "p-ayse", deputy="p-ali")      # Ali, Ayşe'nin talebinde vekil
        _request(c, "r-veli", "p-veli", deputy="p-ayse")
        c.execute(LV.LEDGER.insert().values(tenant_id=TN, person_id="p-ali", type_key="yillik", days=14, reason="acilis",
                                            on_date=date(2026, 1, 1), at=H.now()))
        c.execute(PT.PFILES.insert().values(id="pf-ali", tenant_id=TN, person_id="p-ali", field_key="saglik_raporu",
                                            filename="x.pdf", size=1, blob=b"x", uploaded_at=H.now()))
        # Başka tenant'ta aynı kimlikle vekil anılışı ve talep: dokunulmamalı.
        _person(c, "p-x", "9", tenant="t2")
        _request(c, "r-t2", "p-x", deputy="p-ali", tenant="t2")
        c.execute(LV.LEDGER.insert().values(tenant_id="t2", person_id="p-ali", type_key="yillik", days=5, reason="acilis",
                                            on_date=date(2026, 1, 1), at=H.now()))
    return engine


def _count(engine, table, **where) -> int:
    with engine.connect() as c:
        return c.execute(sa.select(sa.func.count()).select_from(table)
                         .where(*[table.c[k] == v for k, v in where.items()])).scalar()


def _archive(engine, **where) -> list:
    with engine.connect() as c:
        return c.execute(sa.select(H.ARCHIVE).where(*[H.ARCHIVE.c[k] == v for k, v in where.items()])
                         .order_by(H.ARCHIVE.c.id)).all()


def test_delete_person_archives_leave_rows_and_clears_deputy(data):
    out = PT.delete_person(data, TN, "p-ali", "ikuzman")

    assert out["idNo"] == "1" and out["files"] == 1 and out["archiveId"].startswith("arc_")
    assert out["linked"]["izin"] == {"requests": 2, "events": 2, "files": 2, "ledger": 3, "deputyCleared": 1}

    assert _count(data, PT.PEOPLE, tenant_id=TN, id="p-ali") == 0
    assert _count(data, PT.PFILES, tenant_id=TN, person_id="p-ali") == 0
    assert _count(data, LV.REQUESTS, tenant_id=TN, person_id="p-ali") == 0
    for rid in ("r-ali-1", "r-ali-2"):
        assert _count(data, LV.EVENTS, request_id=rid) == 0
        assert _count(data, LV.FILES, request_id=rid) == 0
    assert _count(data, LV.LEDGER, tenant_id=TN, person_id="p-ali") == 0

    # Ayşe'nin talebi kalır, vekil boşalır; Veli'nin talebindeki vekil (Ayşe) değişmez.
    with data.connect() as c:
        dep = dict(c.execute(sa.select(LV.REQUESTS.c.id, LV.REQUESTS.c.deputy_person_id)
                             .where(LV.REQUESTS.c.tenant_id == TN)).all())
    assert dep == {"r-ayse": None, "r-veli": "p-ayse"}
    for rid in ("r-ayse", "r-veli"):
        assert _count(data, LV.EVENTS, request_id=rid) == 1
        assert _count(data, LV.FILES, request_id=rid) == 1
    assert _count(data, LV.LEDGER, tenant_id=TN, person_id="p-ayse") == 1

    # Başka tenant'a dokunulmaz.
    assert _count(data, LV.REQUESTS, tenant_id="t2", deputy_person_id="p-ali") == 1
    assert _count(data, LV.LEDGER, tenant_id="t2", person_id="p-ali") == 1

    # Hiçbiri yok olmadı: hepsi tek arşiv kimliğiyle, yapan ve kaynak tabloyla arşivde.
    arc = _archive(data, tenant_id=TN, subject_id="p-ali")
    assert {a.batch_id for a in arc} == {out["archiveId"]} and {a.archived_by for a in arc} == {"ikuzman"}
    by_table: dict[str, int] = {}
    for a in arc:
        by_table[a.source_table] = by_table.get(a.source_table, 0) + 1
    assert by_table == {"semantic_hr_people": 1, "semantic_hr_people_files": 1, "semantic_hr_leave_requests": 2 + 1,
                        "semantic_hr_leave_events": 2, "semantic_hr_leave_files": 2, "semantic_hr_leave_ledger": 3}
    report = [a for a in arc if a.source_table == "semantic_hr_leave_files" and a.source_id == "f-r-ali-1"][0]
    assert report.blob == b"pdf" and H.load(report.row_json)["filename"] == "rapor.pdf" and "blob" not in H.load(report.row_json)
    person = [a for a in arc if a.source_table == "semantic_hr_people"][0]
    assert H.load(person.row_json)["id_no"] == "1" and person.reason == "personel_silindi"
    dep = [a for a in arc if a.reason == "vekil_bosaltildi"]
    assert [(a.source_id, H.load(a.row_json)["deputy_person_id"]) for a in dep] == [("r-ayse", "p-ali")]
    ledger = [H.load(a.row_json) for a in arc if a.source_table == "semantic_hr_leave_ledger"]
    assert sorted(x["days"] for x in ledger) == [-3.0, -3.0, 14.0]
    assert {x["on_date"] for x in ledger} == {"2026-09-01", "2026-01-01"}
    assert _archive(data, tenant_id="t2") == []


def test_delete_person_counts_and_second_delete_is_404(data):
    out = PT.delete_person(data, TN, "p-veli", "ikuzman")
    assert out["linked"]["izin"]["requests"] == 1 and out["linked"]["izin"]["deputyCleared"] == 0
    with pytest.raises(H.HrError) as e:
        PT.delete_person(data, TN, "p-veli", "ikuzman")
    assert e.value.status == 404


def test_failing_cleanup_rolls_back_whole_delete(data):
    def boom(c, tenant, pid, arc):
        raise RuntimeError("bağlı modül düştü")

    PT.register_person_cleanup(PT.PersonCleanup("zz-boom", lambda e: None, boom))
    with pytest.raises(RuntimeError):
        PT.delete_person(data, TN, "p-ali", "ikuzman")
    assert _count(data, PT.PEOPLE, tenant_id=TN, id="p-ali") == 1
    assert _count(data, LV.REQUESTS, tenant_id=TN, person_id="p-ali") == 2
    assert _count(data, LV.FILES, request_id="r-ali-1") == 1
    assert _count(data, LV.LEDGER, tenant_id=TN, person_id="p-ali") == 3
    assert _count(data, LV.REQUESTS, tenant_id=TN, deputy_person_id="p-ali") == 1
    assert _archive(data) == []
