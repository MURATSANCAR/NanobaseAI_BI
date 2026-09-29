"""Kitap 360 hızı (2026-09-29): bağımsız CRM okumaları aynı anda (bağlantılar ortak havuzdan), masa eşleşmesi
yalnız o kitabın eserleri için, katalog dizini profil listesi başına bir kez. Sonuç ve sorgu bilgisi sırası değişmez."""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any

import pytest

from semantic_bridge import sorgu_izi as IZ
from semantic_layer.store.catalog_store import open_store

S = "Timas_MSCRM.dbo"
BOOK = "11111111-2222-3333-4444-555555555555"


# ------------------------------------------------------------------ sorgu_izi.birlikte

def test_birlikte_keeps_order_of_results_and_captured_reads():
    def is_(n: int, bekle: float):
        def f():
            time.sleep(bekle)
            IZ.dis("crm", f"SELECT {n} FROM Timas_MSCRM.dbo.new_kitapBase", rows=1, ms=1)
            return n
        return f

    t0 = time.perf_counter()
    with IZ.izle_dis() as got:
        out = IZ.birlikte(is_(1, 0.3), is_(2, 0.2), is_(3, 0.1))
    gecen = time.perf_counter() - t0
    assert out == [1, 2, 3]
    # bitiş sırası 3,2,1 — iz verilen sırada
    assert [g["sql"].split()[1] for g in got] == ["1", "2", "3"]
    assert gecen < 0.55, gecen          # sırayla 0,6 sn olurdu


def test_birlikte_raises_first_error_in_given_order_after_all_finish():
    bitti = []

    def iyi():
        time.sleep(0.1)
        bitti.append("iyi")
        return 1

    def kotu(ad):
        def f():
            raise ValueError(ad)
        return f

    with pytest.raises(ValueError, match="ilk"):
        IZ.birlikte(iyi, kotu("ilk"), kotu("ikinci"))
    assert bitti == ["iyi"]


def test_birlikte_single_job_runs_inline_and_passes_context_vars():
    import contextvars
    v: contextvars.ContextVar[str] = contextvars.ContextVar("k360_test", default="yok")
    v.set("var")
    assert IZ.birlikte(lambda: threading.current_thread().name) == [threading.current_thread().name]
    assert IZ.birlikte(lambda: v.get(), lambda: v.get()) == ["var", "var"]


# ------------------------------------------------------------------ editorial.book

def _fake_run(bekle: float, sirasi: list):
    lock = threading.Lock()

    def run(sql: str) -> dict[str, Any]:
        time.sleep(bekle)
        with lock:
            sirasi.append(sql)
        IZ.dis("crm", sql, rows=1, ms=int(bekle * 1000))
        if "FROM Timas_MSCRM.dbo.new_kitapBase b WHERE b.new_kitapId" in sql:
            return {"records": [{"new_kitapId": BOOK, "new_name": "Deneme Kitabı", "new_isbn13": "978-605-08-0000-0",
                                 "new_ozet": "<p>Özet</p>"}], "dbMs": 5}
        if "new_projeBase j LEFT JOIN" in sql:
            return {"records": [{"new_projeId": "p1", "new_name": "Proje", "fikir": "Fikir"}]}
        if "new_katilimcitipiBase" in sql:
            return {"records": [{"rol": "Yazar", "ContactId": "c1", "ad": "Ayşe"}, {"rol": "Çizer", "ContactId": "c2", "ad": "Ali"}]}
        if "new_yayinkurulutoplantilariBase" in sql:
            return {"records": [{"new_yayinkurulutoplantilariId": "t1", "statuscode": "Kabul", "proje": "Proje"}]}
        if "new_UretimBase" in sql:
            return {"records": [{"new_UretimId": "u1", "statuscode": "Açık"}]}
        return {"records": []}
    return run


def test_book_reads_in_parallel_and_keeps_sources_order():
    from semantic_bridge import editorial

    sirasi: list = []
    t0 = time.perf_counter()
    with IZ.izle_dis() as got:
        out = editorial.book(S, _fake_run(0.25, sirasi), BOOK)
    gecen = time.perf_counter() - t0
    assert len(sirasi) == 6
    assert gecen < 0.25 * 3, gecen       # sırayla 1,5 sn olurdu
    assert out["title"] == "Deneme Kitabı" and out["summary"] == "Özet" and out["summaryFrom"] == "new_ozet"
    assert {r["role"] for r in out["roles"]} == {"Yazar", "Çizer"}
    assert out["board"][0]["project"] == "Proje" and out["production"][0]["id"] == "u1"
    assert out["projects"][0]["idea"] == "Fikir"
    # sorgu bilgisi: kitap kartı, proje, sözleşme, rol, kurul, üretim — koşunun bitiş sırasından bağımsız
    kinds = [g["sql"] for g in got]
    assert "new_kitapId, b.new_name" in kinds[0]
    assert "new_projeBase j LEFT JOIN" in kinds[1]
    assert "new_new_sozlesme_new_kitapBase" in kinds[2]
    assert "new_katilimcitipiBase" in kinds[3]
    assert "new_yayinkurulutoplantilariBase" in kinds[4]
    assert "new_UretimBase" in kinds[5]


def test_book_hands_over_the_head_row_before_the_other_reads_finish():
    from semantic_bridge import editorial

    goruldu = {}
    t0 = time.perf_counter()

    def yavas(sql):
        if "new_kitapId, b.new_name" not in sql:
            time.sleep(0.4)
        return _fake_run(0.0, [])(sql)

    editorial.book(S, yavas, BOOK, on_head=lambda row: goruldu.update(an=time.perf_counter() - t0, row=row))
    assert goruldu["an"] < 0.3 and editorial.book_key(goruldu["row"]) == ("Deneme Kitabı", "978-605-08-0000-0")
    yok = {}
    with pytest.raises(editorial.EditorialError):
        editorial.book(S, lambda sql: {"records": []}, BOOK, on_head=lambda row: yok.update(row=row))
    assert "row" in yok and yok["row"] is None


def test_book_missing_is_404_and_bad_id_reads_nothing():
    from semantic_bridge import editorial

    sirasi: list = []

    def bos(sql):
        sirasi.append(sql)
        return {"records": []}

    with pytest.raises(editorial.EditorialError) as e:
        editorial.book(S, bos, BOOK)
    assert e.value.status == 404
    sirasi.clear()
    with pytest.raises(editorial.EditorialError):
        editorial.book(S, bos, "x' OR 1=1 --")
    assert sirasi == []


def test_scope_queries_run_together_and_attach_in_order():
    from semantic_bridge import crm_rights

    items = [{"id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "license": {"countries": [], "languages": []}}]

    def run(sql):
        time.sleep(0.2)
        if "new_ulkeBase" in sql:
            return {"records": [{"new_sozlesmeid": items[0]["id"], "ad": "Türkiye", "tur": "ulke"}]}
        return {"records": [{"new_sozlesmeid": items[0]["id"], "ad": "Türkçe", "tur": "dil"}]}

    t0 = time.perf_counter()
    crm_rights.attach_scope(items, run, "Timas_MSCRM.dbo.")
    assert time.perf_counter() - t0 < 0.35
    assert items[0]["license"] == {"countries": ["Türkiye"], "languages": ["Türkçe"]}


# ------------------------------------------------------------------ masa: yalnız bu kitabın eserleri

def test_list_works_title_filter_summarises_only_matching_works():
    from semantic_bridge import editorial_desk as desk

    e = open_store("sqlite://").engine
    desk.ensure(e)
    now = datetime.now(timezone.utc)
    with e.begin() as c:
        c.execute(desk.WORKS.insert(), [
            {"id": f"w{i}", "tenant_id": "t", "title": t, "members_json": "[]", "created_by": "ayse", "created_at": now}
            for i, t in enumerate(["Deneme Kitabı ", "Başka", "Üçüncü", "deneme kitabı"])])
    hepsi = [w for w in desk.list_works(e, "t", "ayse", False) if w["title"].strip().lower() == "deneme kitabı"]
    with IZ.izle(e) as ran:
        suzulen = desk.list_works(e, "t", "ayse", False, title="Deneme Kitabı")
    assert [w["id"] for w in suzulen] == [w["id"] for w in hepsi] and len(suzulen) == 2
    # 1 eser listesi + 1 imza + eser başına 4 özet okuması (4 eserin hepsi için olsaydı 18)
    assert len(ran) == 2 + 4 * 2
    assert desk.list_works(e, "t", "ayse", False, title="") == []
    assert desk.list_works(e, "t", "baskasi", False, title="Deneme Kitabı") == []


# ------------------------------------------------------------------ katalog dizini: profil listesi başına bir kez

def test_catalog_index_is_built_once_per_profile_list_and_context():
    from semantic_layer.models import ColumnProfile, SchemaProfile
    from semantic_layer.runtime import guardrails as G

    def prof(name, rows=10):
        return SchemaProfile(datasource_id="d", table_name=name, table_pattern=name, entity=name, schema_name="dbo",
                             columns=[ColumnProfile(name="X", data_type="int")], row_count=rows, context={})

    profiles = [prof("A"), prof("B")]
    kurulum = []
    asil = G._build_physical_index

    def sayan(p, c):
        kurulum.append(1)
        return asil(p, c)

    G._build_physical_index = sayan
    try:
        a = G.physicalize_sql("SELECT X FROM A", profiles, {})
        b = G.physicalize_sql("SELECT X FROM B", profiles, {})
        assert len(kurulum) == 1 and "A" in a and "B" in b
        G.physicalize_sql("SELECT X FROM A", profiles, {"n0": "1"})          # başka bağlam: ayrı dizin
        assert len(kurulum) == 2
        profiles.append(prof("C"))                                           # liste büyüdü: yeniden kurulur
        assert "C" in G.physicalize_sql("SELECT X FROM C", profiles, {})
        assert len(kurulum) == 3
        yeni = list(profiles)                                                # katalog yenilendi: yeni liste
        G.physicalize_sql("SELECT X FROM A", yeni, {})
        assert len(kurulum) == 4
    finally:
        G._build_physical_index = asil
    assert G.allowed_tables("SELECT X FROM C", profiles, {})[0]
    assert not G.allowed_tables("SELECT X FROM D", profiles, {})[0]
    profiles.append(prof("D"))
    assert G.allowed_tables("SELECT X FROM D", profiles, {})[0]


# ------------------------------------------------------------------ kart servisi: kapanmış açık bağlantı

def test_card_read_retries_once_when_the_kept_alive_connection_was_closed(monkeypatch):
    import httpx
    from semantic_bridge import editorial_cards as C

    cagri = []

    def cevap(req):
        cagri.append(req.url.path)
        if len(cagri) == 1:
            raise httpx.RemoteProtocolError("Server disconnected without sending a response.", request=req)
        return httpx.Response(200, json={"open": 2})

    istemci = httpx.Client(transport=httpx.MockTransport(cevap))
    monkeypatch.setenv("EDITOR_CATALOG_BASE", "http://kart.test")
    monkeypatch.setenv("EDITOR_CATALOG_KEY", "k")
    monkeypatch.setattr(C, "_client", lambda ca: istemci)
    assert C.review_queue(BOOK) == {"open": 2} and len(cagri) == 2
    cagri.clear()

    def hep_kopuk(req):
        cagri.append(1)
        raise httpx.RemoteProtocolError("Server disconnected without sending a response.", request=req)

    istemci2 = httpx.Client(transport=httpx.MockTransport(hep_kopuk))
    monkeypatch.setattr(C, "_client", lambda ca: istemci2)
    with pytest.raises(httpx.RemoteProtocolError):
        C.review_queue(BOOK)
    assert len(cagri) == 2                     # bir kez yeniden dener, sonsuz döngü yok
