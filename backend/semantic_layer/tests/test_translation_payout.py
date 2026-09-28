"""M4 çeviri işi → M8 serbest çalışan işi ve hakediş.

Sözleşme: iş bir M8 çeviri kişisine ve kelime ücretine bağlanır; «İş paketi aç» M8'de tek paket + kişiye atanmış
görev açar (yeniden basılırsa ikinci görev açmaz); «Hakedişe aktar» yalnız son aktarımdan sonra onaylanan (ya da
çevrilen) kelimeyi M8'de kabul edilmiş işe çevirir, aynı kelime iki kez gitmez; ödenecek iş ve hakediş M8'in
kendi işlevleriyle oluşur.
"""

from __future__ import annotations

import pytest

from semantic_bridge import access as A
from semantic_bridge import editorial_desk as desk
from semantic_bridge import editorial_translation as T
from semantic_bridge import freelance as F
from semantic_bridge import translation_payout as P
from semantic_layer.store.catalog_store import open_store

TENANT = "timas"
# Kelime: CHAPTER ONE 2 · The road was long. 4 · He paid 12 coins. 4 · The road was long. 4 · CHAPTER TWO 2 ·
# Nobody came to the Grand Vizier. 6 → 22.
SRC = b"CHAPTER ONE\n\nThe road was long. He paid 12 coins.\n\nThe road was long.\n\nCHAPTER TWO\n\nNobody came to the Grand Vizier."
TOTAL = 22


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITORIAL_DIR", str(tmp_path / "editorial"))
    monkeypatch.setenv("FREELANCE_DIR", str(tmp_path / "freelance"))
    e = open_store("sqlite://").engine
    T._ready.clear()
    desk._ready.clear()
    F._ready.discard(id(e))
    P._ready.discard(id(e))
    desk.ensure(e)
    P.ensure(e)
    return e


def _job(engine, **kw):
    body = {"title": "The Road", "sourceLang": "en", "targetLang": "tr", "translator": "ayse", "reviewer": "mehmet",
            "dueDate": "2030-01-31", **kw}
    jid = T.create_job(engine, TENANT, "editor", body)["id"]
    T.upload_source(engine, TENANT, "editor", False, jid, "road.txt", SRC)
    return jid


def _translator(engine, name="Ayşe Çevirmen", roles=("ceviri",), price=0.5):
    return F.create_person(engine, TENANT, "editor", {
        "name": name, "roles": list(roles), "weeklyHours": 30,
        "rates": [{"role": "ceviri", "unit": "kelime", "price": price}] if "ceviri" in roles else []})["id"]


def _segs(engine, jid):
    return T.segments(engine, TENANT, "ayse", False, jid, None, "hepsi")["items"]


def _translate(engine, seg, approve=True):
    if seg["status"] != "onaylandi":
        T.save_segment(engine, TENANT, "ayse", False, seg["id"], {"target": f"Ç {seg['no']}.", "status": "cevrildi"})
    if approve:
        T.review_segment(engine, TENANT, "mehmet", False, seg["id"], {"action": "onayla"})


def _payable_tasks(engine):
    return [t for g in F.payable(engine, TENANT) for t in g["tasks"]]


def test_link_validation_and_roles(engine):
    jid = _job(engine)
    pid = _translator(engine)
    other = _translator(engine, name="Çizer", roles=("cizer",))
    st = P.status(engine, TENANT, "editor", False, jid)
    assert st["link"] is None and st["words"]["total"] == TOTAL
    assert [(p["id"], p["rate"]) for p in st["people"]] == [(pid, 0.5)]       # yalnız çeviri rolündekiler
    with pytest.raises(P.PayoutError) as e:
        P.status(engine, TENANT, "ayse", False, jid)                            # çevirmen yönetemez
    assert e.value.status == 403
    with pytest.raises(P.PayoutError, match="sıfırdan büyük"):
        P.set_link(engine, TENANT, "editor", False, jid, {"personId": pid, "rate": "0"})
    with pytest.raises(P.PayoutError) as e:
        P.set_link(engine, TENANT, "editor", False, jid, {"personId": other, "rate": "0,5"})
    assert e.value.status == 409
    with pytest.raises(P.PayoutError, match="esası"):
        P.set_link(engine, TENANT, "editor", False, jid, {"personId": pid, "rate": "0,5", "basis": "sayfa"})
    with pytest.raises(P.PayoutError) as e:
        P.open_package(engine, TENANT, "editor", False, jid)                    # bağ yokken paket açılmaz
    assert e.value.status == 409
    out = P.set_link(engine, TENANT, "editor", False, jid, {"personId": pid, "rate": "0,5"})
    assert out["rate"] == 0.5 and out["basis"] == "onaylanan"


def test_package_is_created_once_and_assigned(engine):
    jid = _job(engine)
    pid = _translator(engine)
    P.set_link(engine, TENANT, "editor", False, jid, {"personId": pid, "rate": "0.5"})
    first = P.open_package(engine, TENANT, "editor", False, jid)
    assert first["created"] is True and first["units"] == TOTAL
    pkg = F.get_package(engine, TENANT, first["packageId"])
    assert pkg["role"] == "ceviri" and pkg["bookTitle"] == "The Road" and pkg["due"] == "2030-01-31"
    [task] = pkg["tasks"]
    assert (task["units"], task["unit"], task["unitPrice"], task["status"], task["personId"]) == (TOTAL, "kelime", 0.5, "atandi", pid)
    assert task["due"] == "2030-01-31" and task["effortHours"] > 0
    # Yeniden basmak ikinci paket/görev açmaz; ücret değişince açık görev de değişir.
    P.set_link(engine, TENANT, "editor", False, jid, {"personId": pid, "rate": "0.6"})
    again = P.open_package(engine, TENANT, "editor", False, jid)
    assert again["created"] is False and again["taskId"] == first["taskId"]
    assert F.list_packages(engine, TENANT, "editor")["total"] == 1
    assert F.get_package(engine, TENANT, first["packageId"])["tasks"][0]["unitPrice"] == 0.6
    # M8 kapasitesi görevi kişinin yükü olarak görür.
    cap = F.capacity(engine, TENANT, role="ceviri")
    assert [t["id"] for t in cap["people"][0]["tasks"]] == [first["taskId"]]


def test_transfer_moves_only_new_words_and_is_idempotent(engine):
    jid = _job(engine)
    pid = _translator(engine)
    P.set_link(engine, TENANT, "editor", False, jid, {"personId": pid, "rate": "0.5"})
    with pytest.raises(P.PayoutError):
        P.transfer(engine, TENANT, "editor", False, jid)                        # paket açılmadan aktarılmaz
    opened = P.open_package(engine, TENANT, "editor", False, jid)
    assert P.transfer(engine, TENANT, "editor", False, jid)["moved"] == 0      # onaylı kelime yok
    assert _payable_tasks(engine) == []

    segs = _segs(engine, jid)
    road = next(s for s in segs if s["source"] == "The road was long.")
    _translate(engine, road)                                                    # 4 kelime onaylandı
    out = P.transfer(engine, TENANT, "editor", False, jid)
    assert (out["moved"], out["transferred"], out["amount"]) == (4, 4, 2.0)
    [chunk] = _payable_tasks(engine)
    assert (chunk["units"], chunk["unit"], chunk["unitPrice"], chunk["amount"], chunk["personId"]) == (4, "kelime", 0.5, 2.0, pid)
    # Asıl görev kalan kelimeyle açık kalır (kapasite kalan işi görür).
    tasks = {t["id"]: t for t in F.get_package(engine, TENANT, opened["packageId"])["tasks"]}
    assert tasks[opened["taskId"]]["units"] == TOTAL - 4 and tasks[opened["taskId"]]["status"] == "atandi"
    assert tasks[chunk["id"]]["deliveries"][0]["decision"] == "kabul"

    # Aynı istek ikinci kez: yeni kelime yok, yeni tutar yok.
    assert P.transfer(engine, TENANT, "editor", False, jid)["moved"] == 0
    assert len(_payable_tasks(engine)) == 1

    # Çevrilmiş ama onaylanmamış kelime onaylanan esasında aktarılmaz.
    coins = next(s for s in segs if "coins" in s["source"])
    _translate(engine, coins, approve=False)
    assert P.transfer(engine, TENANT, "editor", False, jid)["moved"] == 0

    # Hepsi onaylanınca kalan kelimenin tamamı asıl görevle gider.
    for s in _segs(engine, jid):
        _translate(engine, s)
    out = P.transfer(engine, TENANT, "editor", False, jid)
    assert (out["moved"], out["transferred"], out["taskId"]) == (TOTAL - 4, TOTAL, opened["taskId"])
    payable = _payable_tasks(engine)
    assert sorted(t["units"] for t in payable) == [4, TOTAL - 4]
    assert sum(t["amount"] for t in payable) == TOTAL * 0.5

    st = P.status(engine, TENANT, "editor", False, jid)
    assert (st["link"]["transferred"], st["link"]["pending"], st["task"]["open"]) == (TOTAL, 0, False)
    assert [m["words"] for m in st["moves"]] == [TOTAL - 4, 4]

    # Hakediş M8'in kendi işleviyle: iki görev tek belgede.
    doc = F.create_payout(engine, TENANT, "editor", {"personId": pid})
    assert doc["total"] == TOTAL * 0.5
    st = P.status(engine, TENANT, "editor", False, jid)
    assert {m["payout"]["no"] for m in st["moves"]} == {doc["no"]}
    assert P.transfer(engine, TENANT, "editor", False, jid)["moved"] == 0


def test_translated_basis_and_passive_person_blocks_without_side_effects(engine):
    jid = _job(engine)
    pid = _translator(engine)
    P.set_link(engine, TENANT, "editor", False, jid, {"personId": pid, "rate": "1", "basis": "cevrilen"})
    opened = P.open_package(engine, TENANT, "editor", False, jid)
    coins = next(s for s in _segs(engine, jid) if "coins" in s["source"])
    _translate(engine, coins, approve=False)                                    # çevrildi, onaysız: 4 kelime
    F.update_person(engine, TENANT, "editor", pid, {"status": "pasif"})
    with pytest.raises(P.PayoutError) as e:
        P.transfer(engine, TENANT, "editor", False, jid)
    assert e.value.status == 409
    st = P.status(engine, TENANT, "editor", False, jid)
    assert (st["link"]["transferred"], st["link"]["pending"]) == (0, 4)
    assert len(F.get_package(engine, TENANT, opened["packageId"])["tasks"]) == 1
    F.update_person(engine, TENANT, "editor", pid, {"status": "aktif"})
    out = P.transfer(engine, TENANT, "editor", False, jid)
    assert (out["moved"], out["amount"]) == (4, 4.0)


def test_access_rules_for_translation_payout():
    base = "/api/v1/editorial/translation/jobs/x/payout"
    assert A.rule_for(base) == {"sayfa:ceviri", "sayfa:ceviri-masam"}
    assert A.features_for("GET", base) == ["ozellik:serbest.yonet"]
    for method, path in (("PUT", base), ("POST", base + "/package"), ("POST", base + "/transfer")):
        assert sorted(A.features_for(method, path)) == ["ozellik:ceviri.yonet", "ozellik:serbest.yonet"]
    # Çeviri işinin kendi uçları değişmedi.
    assert A.features_for("PATCH", "/api/v1/editorial/translation/jobs/x") == ["ozellik:ceviri.yonet"]
