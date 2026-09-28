"""M4 Çeviri: segment birleştirme ve bölme.

Sözleşme: birleştirme yalnız aynı paragraftaki sonraki segmentle olur (başlık/paragraf sınırı aşılmaz); ilk kimlik
kalır, kaynak/hedef tek boşlukla birleşir, durum ikisinin düşüğüdür ve onaylı «çevrildi»ye iner; ikincinin
inceleme hataları ilkine taşınır; `no` işin tamamında bitişik kalır. Bölme hedefi ilk parçada bırakır, ikinci parça
boş açılır. Rol, bayat sürüm ve süren ZEKİ taslağı reddedilir. Düzenlemeden sonra DOCX/XLIFF doğru paragrafları
kurar; yeni kaynak sürümünde metni aynı kalan paragrafın elle bölünüşü ve çevirisi korunur.
"""

from __future__ import annotations

import pytest
from xml.etree import ElementTree

from semantic_bridge import editorial_desk as desk
from semantic_bridge import editorial_translation as T
from semantic_bridge import editorial_translation_segments as S
from semantic_layer.store.catalog_store import open_store

TENANT = "timas"
SRC = (b"CHAPTER ONE\n\nOh dear! Oh dear! I shall be late!\n\nThe road was long. He paid 12 coins.\n\n"
       b"CHAPTER TWO\n\nNobody came.")


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITORIAL_DIR", str(tmp_path))
    e = open_store("sqlite://").engine
    T._ready.clear()
    desk._ready.clear()
    T.ensure(e)
    desk.ensure(e)
    return e


def _job(engine) -> str:
    jid = T.create_job(engine, TENANT, "editor", {"title": "Alice", "sourceLang": "en", "targetLang": "tr",
                                                  "translator": "ayse", "reviewer": "mehmet"})["id"]
    T.upload_source(engine, TENANT, "editor", False, jid, "alice.txt", SRC)
    return jid


def _segs(engine, jid):
    return T.segments(engine, TENANT, "ayse", False, jid, None, "hepsi")["items"]


def _by_src(engine, jid, src):
    return next(s for s in _segs(engine, jid) if s["source"] == src)


def _save(engine, sid, text, status="cevrildi"):
    return T.save_segment(engine, TENANT, "ayse", False, sid, {"target": text, "status": status})


def test_default_segmentation_splits_dialogue():
    segs = T.segment(T.paragraphs("a.txt", SRC))
    assert [(s["no"], s["para"], s["heading"], s["source"]) for s in segs] == [
        (1, 1, True, "CHAPTER ONE"), (2, 2, False, "Oh dear!"), (3, 2, False, "Oh dear!"), (4, 2, False, "I shall be late!"),
        (5, 3, False, "The road was long."), (6, 3, False, "He paid 12 coins."), (7, 4, True, "CHAPTER TWO"),
        (8, 5, False, "Nobody came.")]


def test_merge_joins_next_demotes_approved_moves_errors_and_renumbers(engine):
    jid = _job(engine)
    segs = _segs(engine, jid)
    a, b, c = segs[1], segs[2], segs[3]
    _save(engine, a["id"], "Aman!")                  # b aynı cümle: taslakla dolar
    _save(engine, b["id"], "Aman Tanrım!")
    for x in (a, b):
        T.review_segment(engine, TENANT, "mehmet", False, x["id"], {"action": "onayla"})
    T.add_error(engine, TENANT, "mehmet", False, b["id"], {"category": "uslup", "severity": "kucuk"})

    out = S.merge_next(engine, TENANT, "ayse", False, a["id"], {"nextId": b["id"]})
    assert out["source"] == "Oh dear! Oh dear!" and out["target"] == "Aman! Aman Tanrım!"
    assert out["status"] == "cevrildi" and out["demoted"] and out["errorsMoved"] == 1 and out["words"] == 4
    after = _segs(engine, jid)
    assert [s["no"] for s in after] == list(range(1, 8))
    assert b["id"] not in {s["id"] for s in after}
    merged = after[1]
    assert merged["id"] == a["id"] and merged["status"] == "cevrildi" and merged["errors"] == 1 and merged["para"] == 2
    detail = T.segment_detail(engine, TENANT, "ayse", False, a["id"])
    assert detail["approvedBy"] is None and len(detail["errorList"]) == 1

    # Boş segmentle birleşme: hedef dolu olduğu için «taslak» (boş sayılmaz).
    out = S.merge_next(engine, TENANT, "ayse", False, a["id"], {"nextId": c["id"]})
    assert out["source"] == "Oh dear! Oh dear! I shall be late!" and out["status"] == "taslak"
    assert out["target"] == "Aman! Aman Tanrım!"
    after = _segs(engine, jid)
    assert [s["no"] for s in after] == list(range(1, 7))
    assert [s["source"] for s in after][:3] == ["CHAPTER ONE", "Oh dear! Oh dear! I shall be late!", "The road was long."]

    # İki boş segment boş kalır.
    road = _by_src(engine, jid, "The road was long.")
    out = S.merge_next(engine, TENANT, "editor", False, road["id"], {})   # işi yöneten de birleştirebilir
    assert out["status"] == "bos" and out["target"] == "" and out["source"] == "The road was long. He paid 12 coins."


def test_merge_refuses_paragraph_heading_and_last_segment(engine):
    jid = _job(engine)
    segs = _segs(engine, jid)
    late, head, last = segs[3], segs[0], segs[-1]
    nxt = S.next_segment(engine, TENANT, "ayse", False, late["id"])
    assert not nxt["mergeable"] and "paragraf" in nxt["reason"] and nxt["next"]["source"] == "The road was long."
    assert S.next_segment(engine, TENANT, "ayse", False, segs[1]["id"])["mergeable"]
    for sid, word in ((late["id"], "paragraf"), (head["id"], "Başlık"), (last["id"], "son segment")):
        with pytest.raises(T.TranslationError) as e:
            S.merge_next(engine, TENANT, "ayse", False, sid, {})
        assert e.value.status == 409 and word in str(e.value)
    # Başlıktan önceki segment başlıkla birleşmez.
    coins = _by_src(engine, jid, "He paid 12 coins.")
    with pytest.raises(T.TranslationError):
        S.merge_next(engine, TENANT, "ayse", False, coins["id"], {})
    assert len(_segs(engine, jid)) == 8


def test_roles_stale_versions_and_running_draft_are_refused(engine):
    jid = _job(engine)
    segs = _segs(engine, jid)
    a, b = segs[1], segs[2]
    for user in ("mehmet", "yabanci"):                 # inceleyen ve yabancı birleştiremez/bölemez
        with pytest.raises(T.TranslationError) as e:
            S.merge_next(engine, TENANT, user, False, a["id"], {})
        assert e.value.status == 403
        with pytest.raises(T.TranslationError) as e:
            S.split_segment(engine, TENANT, user, False, a["id"], {"at": 3})
        assert e.value.status == 403
    with pytest.raises(T.TranslationError) as e:     # liste bu arada değişti
        S.merge_next(engine, TENANT, "ayse", False, a["id"], {"nextId": segs[3]["id"]})
    assert e.value.status == 409
    first = _save(engine, a["id"], "Aman", "taslak")["updatedAt"]
    T.save_segment(engine, TENANT, "ayse", False, a["id"], {"target": "Aman!", "status": "taslak", "updatedAt": first})
    with pytest.raises(T.TranslationError) as e:
        S.merge_next(engine, TENANT, "ayse", False, a["id"], {"nextId": b["id"], "updatedAt": first})
    assert e.value.status == 409
    with pytest.raises(T.TranslationError) as e:
        S.split_segment(engine, TENANT, "ayse", False, a["id"], {"at": 3, "updatedAt": first})
    assert e.value.status == 409
    T._running.add(jid)
    try:
        with pytest.raises(T.TranslationError) as e:
            S.merge_next(engine, TENANT, "ayse", False, a["id"], {})
        assert e.value.status == 409
        with pytest.raises(T.TranslationError) as e:
            S.split_segment(engine, TENANT, "ayse", False, a["id"], {"at": 3})
        assert e.value.status == 409
    finally:
        T._running.discard(jid)
    assert len(_segs(engine, jid)) == 8


def test_split_keeps_target_in_first_part_and_renumbers(engine):
    jid = _job(engine)
    coins = _by_src(engine, jid, "He paid 12 coins.")
    _save(engine, coins["id"], "12 sikke ödedi.")
    T.review_segment(engine, TENANT, "mehmet", False, coins["id"], {"action": "onayla"})
    T.add_error(engine, TENANT, "mehmet", False, coins["id"], {"category": "anlam", "severity": "buyuk"})
    src = coins["source"]
    for bad in (0, len(src), len(src) - 1, "x"):      # iki parçada da kelime kalmalı
        with pytest.raises(T.TranslationError) as e:
            S.split_segment(engine, TENANT, "ayse", False, coins["id"], {"at": bad})
        assert e.value.status == 400
    with pytest.raises(T.TranslationError) as e:
        S.split_segment(engine, TENANT, "ayse", False, coins["id"], {"at": 8, "source": "Başka metin."})
    assert e.value.status == 409
    head = _segs(engine, jid)[0]
    with pytest.raises(T.TranslationError) as e:
        S.split_segment(engine, TENANT, "ayse", False, head["id"], {"at": 3})
    assert e.value.status == 409

    out = S.split_segment(engine, TENANT, "ayse", False, coins["id"], {"at": src.index("12"), "source": src})
    assert out["source"] == "He paid" and out["newSource"] == "12 coins." and out["status"] == "cevrildi" and out["demoted"]
    after = _segs(engine, jid)
    assert [s["no"] for s in after] == list(range(1, 10))
    i = next(k for k, s in enumerate(after) if s["id"] == coins["id"])
    first, second = after[i], after[i + 1]
    assert (first["source"], first["target"], first["status"], first["errors"], first["words"]) == (
        "He paid", "12 sikke ödedi.", "cevrildi", 1, 2)
    assert (second["id"], second["source"], second["target"], second["status"], second["para"]) == (
        out["newId"], "12 coins.", "", "bos", first["para"])
    assert after[i + 2]["source"] == "CHAPTER TWO" and after[i + 2]["heading"]
    assert T.segment_detail(engine, TENANT, "ayse", False, coins["id"])["approvedBy"] is None


def _edit_alice(engine, jid):
    """Üç «Oh dear» parçasını birleştirir, «He paid 12 coins.»u böler, her şeyi çevirir."""
    oh = _segs(engine, jid)[1]
    S.merge_next(engine, TENANT, "ayse", False, oh["id"], {})
    S.merge_next(engine, TENANT, "ayse", False, oh["id"], {})
    coins = _by_src(engine, jid, "He paid 12 coins.")
    S.split_segment(engine, TENANT, "ayse", False, coins["id"], {"at": 8})
    words = {"CHAPTER ONE": "BİRİNCİ BÖLÜM", "Oh dear! Oh dear! I shall be late!": "Aman, aman! Geç kalacağım!",
             "The road was long.": "Yol uzundu.", "He paid": "Ödedi", "12 coins.": "12 sikke.",
             "CHAPTER TWO": "İKİNCİ BÖLÜM", "Nobody came.": "Kimse gelmedi."}
    for s in _segs(engine, jid):
        _save(engine, s["id"], words[s["source"]])


def test_docx_and_xliff_exports_after_edits(engine):
    jid = _job(engine)
    _edit_alice(engine, jid)
    data, name, missing = T.export_docx(engine, TENANT, "ayse", False, jid)
    assert missing == 0 and name.endswith(".docx")
    assert [t for t, _ in T.paragraphs("x.docx", data)] == [
        "BİRİNCİ BÖLÜM", "Aman, aman! Geç kalacağım!", "Yol uzundu. Ödedi 12 sikke.", "İKİNCİ BÖLÜM", "Kimse gelmedi."]
    xlf, _ = T.export_xliff(engine, TENANT, "ayse", False, jid)
    ns = {"x": "urn:oasis:names:tc:xliff:document:1.2"}
    units = ElementTree.fromstring(xlf).findall(".//x:trans-unit", ns)
    segs = _segs(engine, jid)
    assert [u.get("id") for u in units] == [s["id"] for s in segs]
    assert [u.get("resname") for u in units] == [str(n) for n in range(1, 8)]
    assert [u.find("x:source", ns).text for u in units][1:5] == [
        "Oh dear! Oh dear! I shall be late!", "The road was long.", "He paid", "12 coins."]
    # XLIFF gidiş-dönüşü düzenlenmiş segmentlerde de çalışır.
    edited = xlf.replace("<target state=\"translated\">12 sikke.</target>".encode(), "<target state=\"translated\">on iki sikke.</target>".encode())
    assert T.import_xliff(engine, TENANT, "ayse", False, jid, edited)["updated"] == 1


def test_new_source_version_keeps_manual_segmentation_and_carries_translation(engine):
    jid = _job(engine)
    _edit_alice(engine, jid)
    up = T.upload_source(engine, TENANT, "editor", False, jid, "alice2.txt", SRC + b"\n\nA new ending.")
    assert up["segments"] == 8 and up["carried"] == 7
    segs = _segs(engine, jid)
    assert [s["no"] for s in segs] == list(range(1, 9))
    merged = _by_src(engine, jid, "Oh dear! Oh dear! I shall be late!")
    assert merged["target"] == "Aman, aman! Geç kalacağım!" and merged["status"] == "cevrildi"
    assert [s["source"] for s in segs if s["para"] == merged["para"] + 1] == ["The road was long.", "He paid", "12 coins."]
    assert _by_src(engine, jid, "A new ending.")["status"] == "bos"
    # Metni değişen paragraf varsayılan bölücüyle gelir.
    changed = SRC.replace(b"I shall be late!", b"I shall be very late!")
    up = T.upload_source(engine, TENANT, "editor", False, jid, "alice3.txt", changed)
    oh = [s["source"] for s in _segs(engine, jid) if s["para"] == 2]
    assert oh == ["Oh dear!", "Oh dear!", "I shall be very late!"] and up["segments"] == 9


def test_access_rules_need_no_new_feature():
    from semantic_bridge import access as A
    assert A.rule_for("/api/v1/editorial/translation/segments/x/merge") == {"sayfa:ceviri", "sayfa:ceviri-masam"}
    for method, path in (("POST", "merge"), ("POST", "split"), ("GET", "next")):
        assert A.features_for(method, f"/api/v1/editorial/translation/segments/x/{path}") == []
