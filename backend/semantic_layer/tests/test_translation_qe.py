"""M4 Çeviri: ZEKİ kalite tahmini (segment kalite puanları).

Sözleşme: model cevabı JSON dizisi; geçersiz puan (aralık dışı, sayı değil) kırpılmaz, atılır; bilinmeyen/tekrar
eden numara atılır. Kanıt kuralı: alıntı hedefte birebir geçmiyorsa gerekçe atılır, puan kalır. Hedef değişince puan
eskir, şüpheli süzgecine girmez ve yeniden çalıştırmada yalnız o segment sorulur. Başlatma inceleyene/yöneticiye açık.
Sahte model: gerçek modelin cevap biçimi (JSON dizisi); yerel koşu kullanıcı kuralıyla yapılmaz, bu dosya sözleşmedir.
"""

from __future__ import annotations

import json

import pytest
import sqlalchemy as sa

from semantic_bridge import editorial_desk as desk
from semantic_bridge import editorial_translation as T
from semantic_bridge import editorial_translation_qe as Q
from semantic_layer.store.catalog_store import open_store

TENANT = "timas"


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITORIAL_DIR", str(tmp_path))
    e = open_store("sqlite://").engine
    T._ready.clear()
    desk._ready.clear()
    Q._ready.clear()
    T.ensure(e)
    desk.ensure(e)
    Q.ensure(e)
    return e


class _Now:
    """Arka plan iş parçacığı yerine aynı anda çalıştırır: sonuç test içinde okunabilsin."""

    def __init__(self, target, name=None, daemon=None):
        self.target = target

    def start(self):
        self.target()


# ------------------------------------------------------------------ cevap ayrıştırma ve kanıt kuralı


def test_parse_scores_categories_and_drops_invalid_items():
    targets = {1: "Yol uzundu.", 2: "Kimse gelmedi.", 3: "Sadrazam geldi.", 4: "x"}
    answer = "İşte sonuç:\n" + json.dumps([
        {"n": 1, "puan": 97, "kategori": "anlam", "alinti": "Yol", "gerekce": "gereksiz"},   # 85+: kategori istenmez
        {"n": 2, "puan": "62", "kategori": "Dil bilgisi", "alinti": "gelmedi", "gerekce": "Ek yanlış: «gelmedi»."},
        {"n": 2, "puan": 10},                                                              # tekrar: ilki geçer
        {"n": 3, "puan": 150},                                                             # aralık dışı: atılır
        {"n": 4, "puan": "yüksek"},                                                        # sayı değil: atılır
        {"n": 9, "puan": 50},                                                              # bilinmeyen numara
    ], ensure_ascii=False) + "\nbitti"
    got = Q.parse_qe(answer, targets)
    assert set(got) == {1, 2}
    assert got[1] == {"score": 97, "category": None, "severity": None, "reason": None, "span": None}
    assert got[2]["score"] == 62 and got[2]["category"] == "dilbilgisi" and got[2]["severity"] == "buyuk"
    assert got[2]["span"] == "gelmedi" and got[2]["reason"] == "Ek yanlış: «gelmedi»."
    assert Q.parse_qe("cevap yok", targets) == {} and Q.parse_qe("[bozuk", targets) == {}
    assert [Q.severity_of(s) for s in (100, 85, 84, 70, 69, 50, 49, 0)] == [None, None, "kucuk", "kucuk", "buyuk", "buyuk", "kritik", "kritik"]
    assert Q._cat("Yazım") == "yazim" and Q._cat("ÜSLUP") == "uslup" and Q._cat("biçim") == "bicim" and Q._cat("başka") is None


def test_evidence_rule_keeps_score_drops_unquoted_reason():
    t = {1: "Yaşlı adam  kapıyı yavaşça kapattı."}
    ok = Q.parse_qe(json.dumps([{"n": 1, "puan": 72, "kategori": "uslup", "alinti": "adam kapıyı", "gerekce": "Söz dizimi dağınık."}]), t)
    assert ok[1]["span"] == "adam kapıyı" and ok[1]["reason"] == "Söz dizimi dağınık."          # boşluk farkı hoş görülür
    bad = Q.parse_qe(json.dumps([{"n": 1, "puan": 72, "kategori": "anlam", "alinti": "genç kadın", "gerekce": "Kişi yanlış."}]), t)
    assert bad[1]["score"] == 72 and bad[1]["reason"] is None and bad[1]["span"] is None and bad[1]["category"] == "anlam"
    case = Q.parse_qe(json.dumps([{"n": 1, "puan": 60, "alinti": "YAŞLI ADAM", "gerekce": "x"}]), t)
    assert case[1]["reason"] is None                                                          # harf farkı birebir değil
    # Alıntı alanı yoksa gerekçedeki tırnak içlerinden biri hedefte geçmeli.
    quoted = Q.parse_qe(json.dumps([{"n": 1, "puan": 80, "gerekce": "Kaynaktaki «slowly» için «yavaşça» zayıf."}]), t)
    assert quoted[1]["span"] == "yavaşça"
    none = Q.parse_qe(json.dumps([{"n": 1, "puan": 80, "gerekce": "Genel olarak akıcı değil."}]), t)
    assert none[1]["reason"] is None and none[1]["score"] == 80


class _Term:
    def __init__(self, src, tgt, status="onayli", id_="t"):
        self.source_term, self.target_term, self.forbidden_json, self.status, self.id = src, tgt, "[]", status, id_


class _Row:
    def __init__(self, i, src, tgt, no=1):
        self.id, self.source, self.target, self.no, self.words = i, src, tgt, no, T.word_count(src)


def test_score_segments_batches_terms_and_missed_items():
    rows = [_Row(f"s{i}", f"The White Rabbit ran past number {i} and kept on running fast.", f"Beyaz Tavşan {i}.", i)
            for i in range(25)]
    idx = T.TermIndex([_Term("White Rabbit", "Beyaz Tavşan | Ak Tavşan")])
    calls, saved = [], {}

    def chat(messages):
        payload = json.loads(messages[1]["content"])
        calls.append(len(payload["ogeler"]))
        assert "İngilizce" in messages[0]["content"] and "Türkçe" in messages[0]["content"]
        assert payload["terimler"] == [{"kaynak": "White Rabbit", "hedef": "Beyaz Tavşan"}]
        assert set(payload["ogeler"][0]) == {"n", "k", "c"}
        # Son öğeye cevap yok (eksik), ilk öğe şüpheli ve kanıtı hedefte.
        out = [{"n": o["n"], "puan": 90} for o in payload["ogeler"][:-1]]
        out[0] = {"n": 1, "puan": 55, "kategori": "eksik", "alinti": "Beyaz Tavşan", "gerekce": "Cümlenin çoğu çevrilmemiş."}
        return json.dumps(out, ensure_ascii=False)

    st = Q.score_segments(rows, chat, idx, title="t", src="en", tgt="tr", save=saved.update)
    assert calls == [20, 5]                                   # 12 kelimelik 25 segment: 250 kelime / 20 segment sınırı
    assert st == {"scored": 23, "missed": 2, "suspect": 2, "evidence_dropped": 0}
    assert "s19" not in saved and "s24" not in saved
    assert saved["s0"]["hash"] == Q.qe_hash(rows[0].source, rows[0].target) and saved["s0"]["severity"] == "buyuk"


# ------------------------------------------------------------------ iş akışı: başlatma, eskime, süzgeç, yetki


SRC = b"CHAPTER ONE\n\nThe road was long. He paid 12 coins.\n\nThe road was long.\n\nCHAPTER TWO\n\nNobody came to the Grand Vizier."


def _fake_chat(calls):
    def chat(messages):
        payload = json.loads(messages[1]["content"])
        calls.append([o["c"] for o in payload["ogeler"]])
        out = []
        for o in payload["ogeler"]:
            if "kötü" in o["c"]:
                out.append({"n": o["n"], "puan": 60, "kategori": "eksik", "alinti": "kötü", "gerekce": "«kötü» kaynakta yok."})
            elif o["c"].startswith("Yol"):
                out.append({"n": o["n"], "puan": 70, "kategori": "dilbilgisi", "alinti": "uzundur", "gerekce": "Kip yanlış."})
            else:
                out.append({"n": o["n"], "puan": 90})
        return json.dumps(out, ensure_ascii=False)
    return chat


def test_run_stale_detection_and_suspect_filter(engine, monkeypatch):
    monkeypatch.setattr(Q.threading, "Thread", _Now)
    jid = T.create_job(engine, TENANT, "editor", {"title": "The Road", "sourceLang": "en", "targetLang": "tr",
                                                   "translator": "ayse", "reviewer": "mehmet"})["id"]
    T.upload_source(engine, TENANT, "editor", False, jid, "road.txt", SRC)
    segs: dict = {}
    for s in T.segments(engine, TENANT, "ayse", False, jid, None, "hepsi")["items"]:
        segs.setdefault(s["source"], s)                    # tekrar eden cümlenin ilk geçişi
    calls: list[list[str]] = []
    chat = _fake_chat(calls)
    # Çevrilmiş segment yokken başlatılmaz; çevirmen (yönetici değil) başlatamaz.
    with pytest.raises(T.TranslationError) as e:
        Q.start_qe(engine, TENANT, "mehmet", False, jid, {}, chat, False)
    assert e.value.status == 409
    T.save_segment(engine, TENANT, "ayse", False, segs["CHAPTER ONE"]["id"], {"target": "BİRİNCİ BÖLÜM", "status": "cevrildi"})
    T.save_segment(engine, TENANT, "ayse", False, segs["The road was long."]["id"], {"target": "Yol uzundu.", "status": "cevrildi"})
    coins = segs["He paid 12 coins."]["id"]
    T.save_segment(engine, TENANT, "ayse", False, coins, {"target": "12 sikke kötü ödedi.", "status": "cevrildi"})
    with pytest.raises(T.TranslationError) as e:
        Q.start_qe(engine, TENANT, "ayse", False, jid, {}, chat, False)
    assert e.value.status == 403
    with pytest.raises(T.TranslationError) as e:
        Q.start_qe(engine, TENANT, "mehmet", False, jid, {}, None, False)
    assert e.value.status == 503

    # İnceleyen başlatır: taslak durumundaki tekrar eden cümle tahmine girmez (yalnız çevrildi/onaylı).
    out = Q.start_qe(engine, TENANT, "mehmet", False, jid, {}, chat, False)
    assert out == {"segments": 3, "words": 10} and len(calls) == 1
    r = Q.job_qe(engine, TENANT, "ayse", False, jid, False)
    assert r["run"]["state"] == "bitti" and r["run"]["done"] == 3 and "3 segment puanlandı" in r["run"]["note"]
    assert r["canRun"] is False and Q.job_qe(engine, TENANT, "mehmet", False, jid, False)["canRun"] is True
    by = {i["segmentId"]: i for i in r["items"]}
    assert by[coins]["score"] == 60 and by[coins]["span"] == "kötü" and by[coins]["suspect"] and not by[coins]["stale"]
    road = by[segs["The road was long."]["id"]]
    assert road["score"] == 70 and road["reason"] is None and road["category"] == "dilbilgisi"    # kanıtsız gerekçe atıldı
    s = r["summary"]
    assert (s["translated"], s["scored"], s["suspect"], s["stale"], s["missing"]) == (3, 3, 2, 0, 0)
    assert s["average"] == 70.0                               # (90·2 + 70·4 + 60·4) / 10 kelime
    assert [b["segments"] for b in s["buckets"]] == [1, 1, 1, 0]
    assert [i["segmentId"] for i in r["items"] if i["suspect"]] == [road["segmentId"], coins]
    assert [(i["segmentId"], i["target"]) for i in r["lowest"]] == [(coins, "12 sikke kötü ödedi."), (road["segmentId"], "Yol uzundu.")]

    # Hepsi güncel: yeniden başlatma bir şey sormaz.
    with pytest.raises(T.TranslationError) as e:
        Q.start_qe(engine, TENANT, "mehmet", False, jid, {}, chat, False)
    assert e.value.status == 409

    # Çevirmen düzeltti: puan eskir, şüpheliden çıkar; yeniden çalıştırmada yalnız o segment sorulur.
    T.save_segment(engine, TENANT, "ayse", False, coins, {"target": "12 sikke ödedi.", "status": "cevrildi"})
    r2 = Q.job_qe(engine, TENANT, "mehmet", False, jid, False)
    c2 = next(i for i in r2["items"] if i["segmentId"] == coins)
    assert c2["stale"] and not c2["suspect"] and r2["summary"]["stale"] == 1 and r2["summary"]["missing"] == 1
    Q.start_qe(engine, TENANT, "mehmet", False, jid, {}, chat, False)
    assert calls[-1] == ["12 sikke ödedi."]
    c3 = next(i for i in Q.job_qe(engine, TENANT, "mehmet", False, jid, False)["items"] if i["segmentId"] == coins)
    assert c3["score"] == 90 and not c3["stale"] and not c3["suspect"]
    # «all»: güncel olanlar da yeniden puanlanır; bölüm süzgeci yalnız o bölümü sorar.
    Q.start_qe(engine, TENANT, "editor", False, jid, {"all": True, "chapter": 1}, chat, False)
    assert len(calls[-1]) == 3

    # Kaynağın yeni sürümü segment kimliklerini değiştirir: eski puanlar sonraki çalıştırmada temizlenir.
    T.upload_source(engine, TENANT, "editor", False, jid, "road2.txt", SRC + b"\n\nA new ending.")
    assert Q.job_qe(engine, TENANT, "mehmet", False, jid, False)["items"] == []
    Q.start_qe(engine, TENANT, "mehmet", False, jid, {}, chat, False)
    with engine.connect() as conn:
        live = {sid for (sid,) in conn.execute(sa.select(T.SEGMENTS.c.id).where(T.SEGMENTS.c.job_id == jid)).all()}
        stored = {sid for (sid,) in conn.execute(sa.select(Q.QE.c.segment_id).where(Q.QE.c.job_id == jid)).all()}
    assert stored and stored <= live


def test_manager_may_run_and_stale_running_state_is_reset(engine, monkeypatch):
    jid = T.create_job(engine, TENANT, "editor", {"title": "X", "sourceLang": "en", "targetLang": "tr", "translator": "ayse"})["id"]
    with engine.begin() as conn:
        conn.execute(sa.insert(Q.RUNS).values(job_id=jid, state="calisiyor", done=1, total=5))
    Q._ready.clear()
    Q.ensure(engine)
    run = Q.job_qe(engine, TENANT, "ayse", False, jid, True)
    assert run["run"]["state"] == "hata" and run["canRun"] is True       # çeviri işi yöneticisi (ceviri.yonet)


def test_access_rules_for_qe():
    from semantic_bridge import access as A
    assert A.rule_for("/api/v1/editorial/translation/jobs/x/qe") == {"sayfa:ceviri", "sayfa:ceviri-masam"}
    # Başlatma «ceviri.yonet YA DA inceleyen»: ucun içinde denetlenir, özellik kuralı yok.
    assert A.features_for("POST", "/api/v1/editorial/translation/jobs/x/qe") == []
    assert A.features_for("GET", "/api/v1/editorial/translation/jobs/x/qe") == []
