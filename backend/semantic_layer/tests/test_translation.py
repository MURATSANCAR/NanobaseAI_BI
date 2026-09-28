"""M4 Çeviri: segmentleme, terim eşleme, otomatik denetim, XLIFF gidiş-dönüş ve iş akışı.

Sözleşme: kısaltma/baş harf/ondalıkta cümle bölünmez; başlık bölüm açar; terim hedefte çekimli biçimiyle de
bulunur; sayı/noktalama/yasak karşılık denetlenir; onaylı segment çevirmen kaydıyla ve XLIFF'le değişmez;
yeni kaynak sürümünde aynı cümlenin çevirisi korunur; kalite puanı MQM ağırlıklarıyla hesaplanır.
"""

from __future__ import annotations

import io
import zipfile

import pytest

from semantic_bridge import editorial_desk as desk
from semantic_bridge import editorial_translation as T
from semantic_layer.store.catalog_store import open_store

TENANT = "timas"


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITORIAL_DIR", str(tmp_path))
    e = open_store("sqlite://").engine
    T._ready.clear()
    desk._ready.clear()
    T.ensure(e)
    desk.ensure(e)
    return e


def test_sentences_respect_abbreviations_initials_and_decimals():
    s = T.split_sentences('Mr. Smith paid 3.5 dollars. J. K. Rowling wrote it. "Is it?" she asked. Then it rained… Next day came.')
    assert s == ['Mr. Smith paid 3.5 dollars.', 'J. K. Rowling wrote it.', '"Is it?" she asked.', 'Then it rained…', 'Next day came.']
    assert T.split_sentences("Hz. Muhammed geldi. Bkz. s. 12 ve vb. şeyler. Sonra gitti.") == [
        "Hz. Muhammed geldi.", "Bkz. s. 12 ve vb. şeyler.", "Sonra gitti."]
    # Küçük harfle süren: bölünmez. Büyük/küçük harfi olmayan yazı: noktalamayla bölünür.
    assert T.split_sentences("He said no. and left.") == ["He said no. and left."]
    assert len(T.split_sentences("ذهب إلى البيت. ثم نام؟ نعم.")) == 3


def test_headings_open_chapters_and_segments_keep_paragraphs():
    paras = [("CHAPTER ONE", True), ("It was cold. We waited.", False), ("Chapter 2: The Road", True), ("Nobody came.", False)]
    segs = T.segment(paras)
    assert [(s["chapter"], s["heading"], s["source"]) for s in segs] == [
        (1, True, "CHAPTER ONE"), (1, False, "It was cold."), (1, False, "We waited."),
        (2, True, "Chapter 2: The Road"), (2, False, "Nobody came.")]
    assert segs[1]["para"] == segs[2]["para"] and segs[0]["no"] == 1 and segs[-1]["no"] == 5


def test_pdf_lines_drop_page_numbers_and_running_heads():
    pages = [["THE ROAD", "It was a long", "road indeed.", "12"], ["THE ROAD", "Next page text.", "13"], ["THE ROAD", "More here.", "14"]]
    paras = T._join_lines(T.pdf_lines(pages))
    assert paras == [("It was a long road indeed.", False), ("Next page text.", False), ("More here.", False)]


def test_txt_md_and_docx_paragraphs():
    txt = "PROLOGUE\n\nFirst line\ncontinues here.\n\nSecond paragraph."
    assert T.paragraphs("a.txt", txt.encode()) == [("PROLOGUE", True), ("First line continues here.", False), ("Second paragraph.", False)]
    md = "# Başlangıç\nİlk paragraf.\n\nİkinci."
    assert T.paragraphs("a.md", md.encode())[0] == ("Başlangıç", True)
    docx = T.build_docx([("Bölüm 1", True), ("Merhaba dünya.", False)])
    assert T.paragraphs("x.docx", docx) == [("Bölüm 1", True), ("Merhaba dünya.", False)]
    with zipfile.ZipFile(io.BytesIO(docx)) as z:
        assert "word/document.xml" in z.namelist()
    with pytest.raises(T.TranslationError):
        T.paragraphs("x.rtf", b"{}")


class _Term:
    def __init__(self, src, tgt, forbidden="[]", status="onayli", id_="t"):
        self.source_term, self.target_term, self.forbidden_json, self.status, self.id = src, tgt, forbidden, status, id_


def test_terms_match_inflected_targets_and_forbidden_forms():
    idx = T.TermIndex([_Term("book", "kitap", '["defter"]', id_="1"), _Term("Grand Vizier", "Sadrazam", id_="2")])
    hits = idx.find("The books of the grand vizier were lost.")
    assert {t.id for t, _, _ in hits} == {"1", "2"}
    assert T.target_has("Sadrazamın kitabı kayboldu.", "kitap")          # p → b yumuşaması
    assert T.target_has("Sadrazamın kitapları.", "Sadrazam")
    assert not T.target_has("Defterler kayboldu.", "kitap")
    assert T.target_has("Eser kayboldu.", "kitap | eser")                 # | ile birden çok kabul
    issues = T.check_segment("The book is lost.", "Defter kayboldu.", idx.find("The book is lost."))
    assert {i["code"] for i in issues} >= {"terim", "yasak"}


def test_checks_numbers_punctuation_links_and_copy():
    codes = lambda s, t: {i["code"] for i in T.check_segment(s, t, [])}   # noqa: E731
    assert "sayi" in codes("He paid 1,000 dollars in 1998.", "1999'da 1.000 dolar ödedi.")
    assert "sayi" not in codes("He paid 1,000 dollars in 1998.", "1998'de 1.000 dolar ödedi.")
    assert "noktalama" in codes("Why?", "Neden.")
    assert "baglanti" in codes("See www.timas.com.tr now.", "Şimdi bakın.")
    assert "ayni" in codes("This is a test sentence.", "This is a test sentence.")
    assert "denge" in codes("He (quietly) left.", "Sessizce (çıktı.")
    assert T.check_segment("Anything.", "", []) == []


class _Row:
    def __init__(self, i, src, tgt, status="cevrildi"):
        self.id, self.source, self.target, self.status = i, src, tgt, status


def test_job_level_consistency_and_length_outliers():
    rows = [_Row(f"r{i}", f"Sentence number {i} is here and fine.", f"Cümle {i} burada ve yerinde.") for i in range(30)]
    rows += [_Row("a", "The same thing again.", "Yine aynı şey."), _Row("b", "The same thing again.", "Gene aynı şey.")]
    rows.append(_Row("long", "Short source here, indeed.", "Çok " * 80))
    out = T.job_checks(rows)
    assert {i["code"] for i in out["a"]} == {"tutarsiz"} and {i["code"] for i in out["b"]} == {"tutarsiz"}
    assert "uzunluk" in {i["code"] for i in out["long"]}
    assert "r3" not in out


def _job(engine, **kw):
    body = {"title": "The Road", "sourceLang": "en", "targetLang": "tr", "translator": "ayse", "reviewer": "mehmet", **kw}
    return T.create_job(engine, TENANT, "editor", body)["id"]


SRC = b"CHAPTER ONE\n\nThe road was long. He paid 12 coins.\n\nThe road was long.\n\nCHAPTER TWO\n\nNobody came to the Grand Vizier."


def test_flow_translate_review_quality_and_versions(engine):
    jid = _job(engine)
    up = T.upload_source(engine, TENANT, "editor", False, jid, "road.txt", SRC)
    assert up == {"version": 1, "segments": 6, "chapters": 2, "words": up["words"], "carried": 0}
    with pytest.raises(T.TranslationError) as e:
        T.upload_source(engine, TENANT, "editor", False, jid, "road.txt", SRC)
    assert e.value.status == 409
    # Yabancı kişi göremez; çevirmen görür ama iş açamaz/yönetemez.
    with pytest.raises(T.TranslationError):
        T.job_detail(engine, TENANT, "yabanci", False, jid)
    assert [j["id"] for j in T.list_jobs(engine, TENANT, "ayse", False, mine=True)] == [jid]
    segs = T.segments(engine, TENANT, "ayse", False, jid, None, "hepsi")["items"]
    first = next(s for s in segs if s["source"] == "The road was long.")
    r = T.save_segment(engine, TENANT, "ayse", False, first["id"], {"target": "Yol uzundu.", "status": "cevrildi"})
    assert r["status"] == "cevrildi" and r["repeatsFilled"] == 1        # tekrar eden cümle taslakla doldu
    # İnceleyen olmayan onaylayamaz; inceleyen düzelterek onaylar ve hata işaretler.
    with pytest.raises(T.TranslationError):
        T.review_segment(engine, TENANT, "ayse", False, first["id"], {"action": "onayla"})
    T.review_segment(engine, TENANT, "mehmet", False, first["id"], {"action": "onayla", "target": "Yol uzundu."})
    T.add_error(engine, TENANT, "mehmet", False, first["id"], {"category": "uslup", "severity": "kucuk"})
    with pytest.raises(T.TranslationError) as e:
        T.save_segment(engine, TENANT, "ayse", False, first["id"], {"target": "x", "status": "taslak"})
    assert e.value.status == 409
    coins = next(s for s in segs if "coins" in s["source"])
    T.save_segment(engine, TENANT, "ayse", False, coins["id"], {"target": "13 sikke ödedi", "status": "cevrildi"})
    flagged = T.segments(engine, TENANT, "ayse", False, jid, None, "sorunlu")["items"]
    assert {i["code"] for i in flagged[0]["issues"]} >= {"sayi", "noktalama"}
    q = T.quality(engine, TENANT, "editor", False, jid)
    assert q["mqm"]["reviewedWords"] == 4 and q["mqm"]["penalty"] == 1 and q["mqm"]["score"] == 75.0
    assert q["checks"]["byCode"]["sayi"] == 1 and q["stage"] == "ceviri"
    # Yeni kaynak sürümü: aynı cümlenin çevirisi taşınır, onay çevrildi'ye iner.
    up2 = T.upload_source(engine, TENANT, "editor", False, jid, "road2.txt", SRC + b"\n\nA new ending.")
    assert up2["version"] == 2 and up2["carried"] >= 2
    again = T.segments(engine, TENANT, "ayse", False, jid, None, "hepsi")["items"]
    assert {s["status"] for s in again if s["source"] == "The road was long."} == {"cevrildi", "taslak"}


def test_xliff_round_trip_keeps_approved_segments(engine):
    jid = _job(engine)
    T.upload_source(engine, TENANT, "editor", False, jid, "road.txt", SRC)
    segs = T.segments(engine, TENANT, "ayse", False, jid, None, "hepsi")["items"]
    T.save_segment(engine, TENANT, "ayse", False, segs[0]["id"], {"target": "BİRİNCİ BÖLÜM", "status": "cevrildi"})
    T.review_segment(engine, TENANT, "mehmet", False, segs[0]["id"], {"action": "onayla"})
    xlf, name = T.export_xliff(engine, TENANT, "ayse", False, jid)
    assert name.endswith(".xlf") and b'state="signed-off"' in xlf
    edited = xlf.replace(b"<source>Nobody came to the Grand Vizier.</source>",
                         b'<source>Nobody came to the Grand Vizier.</source><target state="translated">Sadrazama kimse gelmedi.</target>')
    edited = edited.replace('<target state="signed-off">BİRİNCİ BÖLÜM</target>'.encode(), '<target state="translated">DEĞİŞTİ</target>'.encode())
    out = T.import_xliff(engine, TENANT, "ayse", False, jid, edited)
    assert out["updated"] == 1 and out["confirmed"] == 1 and out["locked"] == 1
    with pytest.raises(T.TranslationError):
        T.import_xliff(engine, TENANT, "ayse", False, jid, b'<!DOCTYPE x [<!ENTITY a "b">]><xliff/>')


def test_terms_bank_import_candidates_and_redaction(engine):
    out = T.import_terms(engine, TENANT, "editor", "en", "tr", "kaynak;hedef;yasak;not\nGrand Vizier;Sadrazam;Büyük Vezir;Osmanlı\n;boş\n".encode())
    assert out == {"added": 1, "updated": 0, "skipped": 1}
    jid = _job(engine)
    T.upload_source(engine, TENANT, "editor", False, jid, "road.txt", SRC + b"\n\nThey met Aslan Bey. Then Aslan Bey left. Later Aslan Bey returned.")
    cands = T.term_candidates(engine, TENANT, "editor", False, jid)
    assert [c["term"] for c in cands] == ["Aslan Bey"]
    # Çevirmen yalnız işe bağlı aday önerir; aynı terim ikinci kez eklenmez.
    T.create_term(engine, TENANT, "ayse", False, {"source": "Aslan Bey", "target": "Aslan Bey", "jobId": jid}, True)
    with pytest.raises(T.TranslationError):
        T.create_term(engine, TENANT, "ayse", False, {"source": "aslan bey", "target": "x", "jobId": jid}, True)
    assert {t["status"] for t in T.list_terms(engine, TENANT, "en", "tr")["items"]} == {"onayli", "aday"}
    with pytest.raises(T.TranslationError):
        T.to_redaction(engine, TENANT, "editor", False, jid, False)          # çeviri bitmeden aktarılmaz
    for s in T.segments(engine, TENANT, "ayse", False, jid, None, "hepsi")["items"]:
        T.save_segment(engine, TENANT, "ayse", False, s["id"], {"target": f"Ç {s['no']}.", "status": "cevrildi"})
    red = T.to_redaction(engine, TENANT, "editor", False, jid, False)
    assert red["version"] == 1 and red["chapters"] == 2
    assert desk.chapters(engine, TENANT, "editor", False, red["workId"])["chapters"][0]["title"] == "Ç 1."


def test_access_rules_for_translation():
    from semantic_bridge import access as A
    assert A.rule_for("/api/v1/editorial/translation/jobs") == {"sayfa:ceviri", "sayfa:ceviri-masam"}
    assert A.features_for("POST", "/api/v1/editorial/translation/jobs") == ["ozellik:ceviri.yonet"]
    assert A.features_for("PUT", "/api/v1/editorial/translation/jobs/x/source") == ["ozellik:ceviri.yonet"]
    assert A.features_for("POST", "/api/v1/editorial/translation/jobs/x/draft") == ["ozellik:ceviri.yonet"]
    assert A.features_for("PUT", "/api/v1/editorial/translation/segments/x") == []
    assert A.features_for("PUT", "/api/v1/editorial/translation/jobs/x/xliff") == []
    assert A.features_for("POST", "/api/v1/editorial/translation/terms/propose") == []
    assert A.features_for("POST", "/api/v1/editorial/translation/terms") == ["ozellik:ceviri.terim"]
    assert A.features_for("DELETE", "/api/v1/editorial/translation/terms/x") == ["ozellik:ceviri.terim"]
    assert A.features_for("GET", "/api/v1/editorial/translation/jobs/x/export.docx") == ["ozellik:veri.disa-aktar"]
    assert A.features_for("GET", "/api/v1/editorial/translation/jobs/x/export.xlf") == []


class _Seg:
    def __init__(self, i, no, para, src):
        self.id, self.no, self.para, self.source, self.words = i, no, para, src, T.word_count(src)


def test_draft_review_and_repair_passes_with_evidence_rule():
    """Taslak → ikinci okuma → modelsiz denetimle onarım. İkinci okumanın uyarıyı artıran önerisi atılır; onarım
    yalnız uyarıyı azaltıyorsa kabul edilir. Sahte model: gerçek modelin cevap biçimi (JSON dizisi)."""
    import json as _json
    rows = [_Seg("a", 1, 1, "He paid 1,000 coins."), _Seg("b", 2, 1, "Why, it was the White Rabbit!"),
            _Seg("c", 3, 2, "Nobody came.")]
    idx = T.TermIndex([_Term("White Rabbit", "Beyaz Tavşan", id_="w")])
    calls = []

    def chat(messages):
        system, payload = messages[0]["content"], _json.loads(messages[1]["content"])
        kind = "taslak" if "cumleler" in payload else ("onarim" if "sorunlar" in _json.dumps(payload, ensure_ascii=False) else "okuma")
        calls.append(kind)
        if "cumleler" in payload:                      # 1) taslak: sayı yanlış, deyim kelimesi kelimesine, terim yok
            assert [c["p"] for c in payload["cumleler"]] == [1, 1, 2]
            assert payload["terimler"] == [{"kaynak": "White Rabbit", "hedef": "Beyaz Tavşan"}]
            return _json.dumps([{"n": 1, "t": "2.000 sikke ödedi."}, {"n": 2, "t": "Neden, Ak Tavşan'dı!"},
                                {"n": 3, "t": "Kimse gelmedi."}])
        if "sorunlar" in _json.dumps(payload, ensure_ascii=False):   # 3) onarım: sayıyı düzeltir
            return _json.dumps([{"n": o["n"], "t": "1.000 sikke ödedi."} for o in payload["ogeler"]])
        # 2) ikinci okuma: 2'yi düzeltir; 3'ü bozar (noktalamayı siler) → kanıt kuralı reddeder
        return _json.dumps([{"n": 2, "t": "Aa, Beyaz Tavşan'dı!", "h": "deyim"}, {"n": 3, "t": "Kimse gelmedi", "h": "x"}])

    out, st = T.draft_segments(rows, chat, idx, title="t", src="en", tgt="tr", context=lambda n: "", second_read=True)
    assert out == {"a": "1.000 sikke ödedi.", "b": "Aa, Beyaz Tavşan'dı!", "c": "Kimse gelmedi."}
    assert st["drafted"] == 3 and st["reviewed"] == 1 and st["rejected"] == 1 and st["repaired"] == 1 and st["left"] == 0
    assert calls == ["taslak", "okuma", "onarim"]

    # Varsayılan: ikinci okuma kapalı (ölçümde kazanç yoktu) — taslak + onarım, 2 çağrı; «b» taslaktaki hâliyle kalır.
    calls.clear()
    out, st = T.draft_segments(rows, chat, idx, title="t", src="en", tgt="tr", context=lambda n: "")
    assert st["reviewed"] == 0 and st["repaired"] >= 1
    assert "okuma" not in calls and calls[0] == "taslak"
    assert out["a"] == "1.000 sikke ödedi." and out["b"] == "Neden, Ak Tavşan'dı!"


def test_delete_job_cleans_companion_tables(engine):
    """Yan modül tabloları (hakediş bağı, kalite tahmini) iş silinince yetim kalmaz."""
    import sqlalchemy as _sa
    jid = _job(engine)
    with engine.begin() as c:
        c.execute(_sa.text("CREATE TABLE semantic_translation_links (job_id VARCHAR(32) PRIMARY KEY, person_id VARCHAR(32))"))
        c.execute(_sa.text("INSERT INTO semantic_translation_links VALUES (:j, 'p')"), {"j": jid})
        c.execute(_sa.text("INSERT INTO semantic_translation_links VALUES ('baska', 'p')"))
    T.delete_job(engine, TENANT, "editor", False, jid)
    with engine.connect() as c:
        assert [r[0] for r in c.execute(_sa.text("SELECT job_id FROM semantic_translation_links"))] == ["baska"]
