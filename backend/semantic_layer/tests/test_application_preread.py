"""Öneri 12 — M1 başvuru ön okuması (`semantic_bridge.application_preread`) ve belgeden alan çıkarmanın ortak parçaları
(`semantic_bridge.doc_extract`).

Sözleşme: uzun dosya sayfa bölünmeden örtüşen pencerelerle okunur ve bütün pencereler modele gider; her alanın
alıntısı belgede birebir bulunmalı, bulunmayan atılır ve sayılır; tür/kitle/tema/ilke kapalı kümeden; özet cümlesindeki
sayı alıntısında olmalı; yaş alıntıdan kodla okunur; kapalı küme seçiminde olasılık eşiğin altındaysa alan boş kalır;
taslak puan ve kabul/red önerisi doldurmaz, «temiz» hiç önermez; modele giden metinde yazarın adı, e-postası ve
etiketli kişi satırları yoktur. Model sahtedir; gerçek model ve OCR kabulü test sunucusunda
(scripts/acceptance/zeki-12-13).
"""

from __future__ import annotations

import json
import re

import pytest

from semantic_bridge import application_preread as PR
from semantic_bridge import doc_extract as X
from semantic_bridge import doc_read as DR
from semantic_bridge import editorial_applications as EA
from semantic_layer.store.catalog_store import open_store

T = "t1"
CFG_READ = {"ocr": False, "timeout": 30, "minChars": 5, "lowConfidence": 0.8}
P1 = "Bu roman, 1923 yılında İstanbul'da geçen bir aile hikâyesini anlatır. Yazar Deniz Yazar, deniz@ornek.com adresinden ulaşılabilir."
P2 = "Kitap 12-15 yaş arası genç okurlar için yazılmıştır. Ana tema dostluk ve cesarettir."
P3 = "Kahraman Ali, savaş yıllarında kardeşini arar. Kitapta sert bir kavga sahnesi ayrıntılı anlatılır."


def reading(*pages: str) -> DR.Reading:
    return DR.Reading(filename="eser.pdf", pages=[{"sayfa": str(i), "metin": t, "okuma": DR.METIN, "guven": None}
                                                  for i, t in enumerate(pages, start=1)])


class FakeChoice:
    def __init__(self, choice, prob=0.92, margin=0.85):
        self.choice, self._p, self.margin = choice, prob, margin

    @property
    def probability(self):
        return self._p

    def confident(self, min_prob, min_margin=0.0):
        return self._p >= min_prob and self.margin >= min_margin


def chooser(prob=0.92, margin=0.85, calls=None):
    def choose(prompt, labels):
        if calls is not None:
            calls.append((prompt, list(labels)))
        for want in ("Kurgu (roman, öykü, masal)", "Genç"):
            if want in labels:
                return FakeChoice(want, prob, margin)
        return FakeChoice(labels[0], prob, margin)
    return choose


WINDOW = {
    "tur": {"deger": "kurgu", "alinti": "Bu roman, 1923 yılında İstanbul'da geçen"},
    "kitle": {"deger": "genc", "alinti": "12-15 yaş arası genç okurlar için yazılmıştır"},
    "yas": {"alinti": "Kitap 12-15 yaş arası genç okurlar için"},
    "konu": {"deger": "1923 İstanbul'unda bir aile hikâyesi", "alinti": "1923 yılında İstanbul'da geçen bir aile hikâyesini anlatır"},
    "temalar": [{"deger": "Dostluk", "alinti": "Ana tema dostluk ve cesarettir"}, {"deger": "Uzay", "alinti": "Ana tema dostluk"}],
    "ozet": [{"cumle": "Roman 1923 İstanbul'unda bir aileyi anlatır.", "alinti": "1923 yılında İstanbul'da geçen bir aile hikâyesini anlatır"},
             {"cumle": "Kahraman 1950'de kardeşini arar.", "alinti": "Kahraman Ali, savaş yıllarında kardeşini arar"},
             {"cumle": "Ali kardeşini arar.", "alinti": "bu alıntı dosyada hiç geçmiyor"}],
    "ilke": [{"kategori": "siddet", "alinti": "sert bir kavga sahnesi ayrıntılı anlatılır"},
             {"kategori": "bilinmeyen", "alinti": "sert bir kavga sahnesi"}],
}


def cfg(**over):
    c = PR.settings(lambda k: "")
    c.update(over)
    return c


def similar(text):
    return {"items": [{"sira": 1, "kitapId": "K1", "stokKodu": "S1", "ad": "Kayıp Kardeş", "yazar": "A. B.",
                       "kitaplik": "Roman", "gerekce": ["özet benzerliği"], "puan": 0.9}], "kaynak": "benzerlik"}


# ------------------------------------------------------------------------------------------------ ortak parçalar


def test_windows_keep_pages_whole_overlap_and_cover_everything():
    pages = [("s%d " % i) + "kelime " * 140 for i in range(1, 6)]           # ~1000 karakter
    r = reading(*pages)
    wins = X.plan_windows(r, 2500, 1)
    assert [w.pages for w in wins] == [["1", "2"], ["2", "3"], ["3", "4"], ["4", "5"]]
    assert all(len(w.text) <= 2500 for w in wins)
    assert {p for w in wins for p in w.pages} == {"1", "2", "3", "4", "5"}
    assert X.plan_windows(r, 2500, 0)[1].pages == ["3", "4"]                 # örtüşme kapalı: ardışık
    assert len(X.plan_windows(r, 100000, 1)) == 1                             # kısa belge tek çağrı


def test_long_page_is_split_without_losing_text():
    long = "\n".join("Paragraf %d: " % i + "söz " * 120 for i in range(10))
    pieces = X._split_long(long, 1000)
    assert all(len(p) <= 1000 for p in pieces) and len(pieces) > 1
    assert re.sub(r"\s", "", "".join(pieces)) == re.sub(r"\s", "", long)
    wins = X.plan_windows(reading(long), 1500, 1)
    assert all(w.pages == ["1"] for w in wins) and all(len(w.text) <= 1500 for w in wins)


def test_numbers_dates_and_ages_come_from_the_quote():
    assert X.number_in("yazara %10 telif öder", percent=True) == 10
    assert X.number_in("1.250.000 TL avans", percent=False) == 1250000
    assert X.number_in("12,5 oranında değil %12,5 telif", percent=True) == 12.5
    assert X.number_in("5.000 TL ve 7.500 TL") is None                       # iki aday, model göstermedi
    assert X.number_in("5.000 TL ve 7.500 TL", "7.500") == 7500               # model yalnız hangisi olduğunu seçer
    assert X.number_in("15.000 TL avans", "20.000 TL") == 15000               # modelin sayısı değil alıntının sayısı
    assert X.number_in("2026 yılında 3 bin TL") == 3000                       # yıl para adayı değil, ölçek sözcüğü
    assert X.dates_in("31 Aralık 2030 tarihine kadar") == ["2030-12-31"]
    assert X.date_in("01.01.2026 ile 31.12.2030 arası") is None
    assert X.date_in("01.01.2026 ile 31.12.2030 arası", "31.12.2030") == "2030-12-31"
    assert X.years_in("5 (beş) yıl süreyle") == 5 and X.years_in("18 ay") == 1.5
    assert X.years_in("5 yıl, uzatılırsa 3 yıl") is None
    assert X.ages_in("12-15 yaş arası") == (12, 15) and X.ages_in("12 yaş ve üzeri") == (12, None)
    assert X.ages_in("genç okurlar") is None


def test_mask_all_hides_contact_labeled_lines_and_known_names():
    t = "İletişim ayse@x.com, 0532 123 45 67\nAdres: Kadıköy, İstanbul\nAYŞE YILMAZ imzaladı. Yılmaz'ın eseri."
    m = X.mask_all(t, ["Ayşe Yılmaz"])
    assert "ayse@x.com" not in m and "0532" not in m and "Kadıköy" not in m
    assert "AYŞE" not in m and "YILMAZ" not in m and "Yılmaz" not in m
    assert "Adres: [kişisel bilgi]" in m


# ------------------------------------------------------------------------------------------------ ön okuma


def test_analyse_keeps_only_quoted_closed_set_values_and_masks_the_author():
    sent = []

    def chat(messages):
        sent.append(messages)
        return json.dumps(WINDOW, ensure_ascii=False)

    calls = []
    out = PR.analyse(reading(P1, P2, P3), names=["Deniz Yazar"], chat=chat, choose=chooser(calls=calls), cfg=cfg(),
                     themes=["Dostluk", "Aile"], similar=similar)
    a = out["alanlar"]
    assert a["tur"]["deger"] == "kurgu" and a["tur"]["olasilik"] == 0.92 and a["tur"]["kanit"][0]["sayfa"] == "1"
    assert a["kitle"]["deger"] == "genc" and a["yas"]["alt"] == 12 and a["yas"]["ust"] == 15
    assert a["konu"]["deger"].startswith("1923") and [t["deger"] for t in a["temalar"]] == ["Dostluk"]
    assert [c["cumle"] for c in a["ozet"]["cumleler"]] == ["Roman 1923 İstanbul'unda bir aileyi anlatır."]
    assert [(i["kategori"], i["kanit"]["sayfa"]) for i in a["ilke"]] == [("siddet", "3")]
    assert out["atilan"] == 4                        # uydurma tema, sayısı alıntıda olmayan cümle, alıntısız cümle, bilinmeyen kategori
    assert out["pencere"]["sayi"] == 1 and out["kaynak"] == "zeki"
    text = json.dumps(sent, ensure_ascii=False)
    assert "deniz@ornek.com" not in text and "Deniz" not in text           # yazarın kişisel verisi modele gitmez
    assert all("Deniz" not in p for p, _ in calls)
    assert out["benzer"]["items"][0]["ad"] == "Kayıp Kardeş" and "puan" not in out["benzer"]["items"][0]


def test_draft_fills_only_editor_text_fields_never_scores_or_decision():
    out = PR.analyse(reading(P1, P2, P3), names=["Deniz Yazar"], chat=lambda m: json.dumps(WINDOW), choose=chooser(),
                     cfg=cfg(), themes=["Dostluk"], similar=similar)
    d = out["taslak"]
    assert set(d) == {"topic", "genre", "ageGroup", "overlapNote", "redline", "redlineNote", "report"}
    assert d["genre"] == PR.FORMS["kurgu"] and d["ageGroup"] == "12–15 yaş"
    assert d["redline"] == "dikkat" and "s. 3" in d["redlineNote"]
    assert "Kayıp Kardeş" in d["overlapNote"] and d["report"].startswith("Ön okuma taslağı")
    clean = PR.draft({"tur": None, "kitle": None, "yas": None, "konu": None, "ozet": None, "temalar": [], "ilke": []},
                     {"items": []})
    assert clean["redline"] is None                  # işaret yoksa «temiz» önerilmez; karar editörün


def test_unsure_choice_leaves_field_empty():
    out = PR.analyse(reading(P1, P2, P3), names=[], chat=lambda m: json.dumps(WINDOW), choose=chooser(prob=0.5, margin=0.1),
                     cfg=cfg(), themes=[])
    assert out["alanlar"]["tur"]["deger"] is None and out["alanlar"]["tur"]["emin"] is False
    assert out["taslak"]["genre"] is None
    assert out["alanlar"]["temalar"] == []           # tema listesi yoksa tema önerilmez


def test_majority_without_choose_and_tie_is_empty():
    ev = {"alinti": "x", "sayfa": "1", "okuma": "metin"}
    c = cfg()
    assert PR._decide([("kurgu", ev), ("kurgu", ev), ("siir", ev)], PR.FORMS, "?", None, c)["deger"] == "kurgu"
    assert PR._decide([("kurgu", ev), ("siir", ev)], PR.FORMS, "?", None, c)["deger"] is None


def test_summary_picks_three_to_five_sentences_with_their_quotes():
    words = ("Birinci", "İkinci", "Üçüncü", "Dördüncü", "Beşinci", "Altıncı", "Yedinci")
    page = " ".join(f"{w} bölümde kahraman yola çıkar ve yeni bir kasabaya varır." for w in words)
    window = {"ozet": [{"cumle": f"{w} bölümde yolculuk anlatılır.", "alinti": f"{w} bölümde kahraman yola çıkar"} for w in words]}

    def chat(messages):
        if "JSON listesi" in messages[0]["content"]:
            return "[1, 3, 5]"
        return json.dumps(window, ensure_ascii=False)

    oz = PR.analyse(reading(page), names=[], chat=chat, choose=None, cfg=cfg(), themes=[])["alanlar"]["ozet"]
    assert oz["aday"] == 7 and oz["secim"] == "zeki" and len(oz["cumleler"]) == 3
    assert oz["cumleler"][1]["kanit"]["alinti"].startswith("Üçüncü")
    oz2 = PR.analyse(reading(page), names=[], chat=lambda m: "[]" if "JSON listesi" in m[0]["content"] else json.dumps(window),
                     choose=None, cfg=cfg(), themes=[])["alanlar"]["ozet"]
    assert oz2["secim"] == "esit-aralik" and 3 <= len(oz2["cumleler"]) <= 5


def test_long_file_reads_every_window():
    pages = [f"Sayfa {i} metni: kahraman yolculuğuna devam eder ve yeni insanlarla tanışır. " * 20 for i in range(1, 9)]
    n = []
    PR.analyse(reading(*pages), names=[], chat=lambda m: n.append(1) or "{}", choose=None, cfg=cfg(windowChars=4000, overlap=1),
               themes=[])
    assert len(n) == len(X.plan_windows(reading(*pages), 4000, 1)) > 1


def test_no_model_and_unreadable_file_are_explicit():
    with pytest.raises(PR.PrereadError) as e:
        PR.analyse(reading(P1), names=[], chat=None, choose=None, cfg=cfg(), themes=[])
    assert e.value.status == 503
    with pytest.raises(PR.PrereadError, match="okunamadı"):
        PR.analyse(DR.Reading("x.pdf", [{"sayfa": "1", "metin": "", "okuma": DR.YOK, "guven": None}]), names=[],
                   chat=lambda m: "{}", choose=None, cfg=cfg(), themes=[])


def test_policy_categories_from_settings():
    assert PR.policy_categories('{"a": "Birinci"}') == {"a": "Birinci"}
    assert PR.policy_categories("bozuk") == PR.POLICY_DEFAULT and PR.policy_categories("") == PR.POLICY_DEFAULT


def test_readable_files_skip_cv_and_old_word():
    files = [{"id": "1", "kind": "dosya", "filename": "eser.pdf", "round": 1}, {"id": "2", "kind": "ozgecmis", "filename": "cv.pdf", "round": 1},
             {"id": "3", "kind": "revizyon", "filename": "eski.doc", "round": 1}]
    r = PR.readable(files, 1)
    assert [f["id"] for f in r] == ["1", "3"] and r[0]["readable"] and not r[1]["readable"] and "PDF" in r[1]["why"]


# ------------------------------------------------------------------------------------------------ uçlar


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITORIAL_APPLICATIONS_DIR", str(tmp_path / "apps"))
    e = open_store("sqlite://").engine
    EA._ready.discard(id(e))
    PR._ready.discard(id(e))
    EA.ensure(e)
    return e


class FakeLlm:
    def __init__(self):
        self.messages = []

    def chat(self, messages, **kw):
        self.messages.append(messages)
        return json.dumps(WINDOW, ensure_ascii=False)

    def choose(self, prompt, choices):
        return chooser()(prompt, choices)


def _client(engine, llm):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from semantic_bridge import application_preread_api as API

    app = FastAPI()
    audits = []
    API.spawn = lambda target, name: target()           # arka plan işi testte eşzamanlı
    API.register(app, {"session": lambda r: (engine, T, "ayse", "Ayşe Editör"), "audit": lambda *a, **k: audits.append(a),
                       "conf": lambda k: "", "llm": lambda: llm})
    return TestClient(app), audits


def test_endpoints_run_the_preread_and_carry_source_info(engine, monkeypatch):
    from semantic_bridge import provenance as P

    monkeypatch.setattr(DR, "settings", lambda: CFG_READ)
    monkeypatch.setattr(DR, "pdf_pages", lambda data: [P1, P2, P3])
    a = EA.create(engine, T, "ayse", "Ayşe Editör", {
        "title": "Kayıp Yıllar", "authorName": "Deniz Yazar", "summary": "Bir aile hikâyesi.", "authorBio": "Yazar.",
        "pageEstimate": 200, "channel": "eposta", "receivedOn": "2026-09-01", "categoryName": "Roman", "audience": "genc"})
    cv = EA.add_file(engine, T, "ayse", "Ayşe", a["id"], "cv.pdf", "ozgecmis", b"%PDF-1.4 cv")
    f = EA.add_file(engine, T, "ayse", "Ayşe", a["id"], "eser.pdf", "dosya", b"%PDF-1.4 eser")
    llm = FakeLlm()
    client, audits = _client(engine, llm)
    assert client.post(f"/api/v1/editorial/applications/{a['id']}/preread", json={"fileId": cv["id"]}).status_code == 400
    r = client.post(f"/api/v1/editorial/applications/{a['id']}/preread", json={"fileId": f["id"]})
    assert r.status_code == 200, r.text
    g = client.get(f"/api/v1/editorial/applications/{a['id']}/preread").json()
    assert g["preread"]["status"] == "hazir", g["preread"]["error"]
    res = g["preread"]["result"]
    assert res["alanlar"]["tur"]["deger"] == "kurgu" and res["dosya"]["ad"] == "eser.pdf"
    assert res["taslak"]["redline"] == "dikkat"
    assert [x["id"] for x in g["files"]] == [f["id"]]                     # özgeçmiş listede yok
    assert not P.uncovered_numbers(g) and not P.problems(g)
    assert "Deniz" not in json.dumps(llm.messages, ensure_ascii=False)
    assert audits and audits[0][1] == "ayse"


def test_endpoint_without_model_is_503(engine, monkeypatch):
    a = EA.create(engine, T, "ayse", "Ayşe Editör", {
        "title": "Kayıp Yıllar", "authorName": "Deniz Yazar", "summary": "Özet.", "authorBio": "Yazar.",
        "pageEstimate": 200, "channel": "eposta", "receivedOn": "2026-09-01", "categoryName": "Roman"})
    EA.add_file(engine, T, "ayse", "Ayşe", a["id"], "eser.pdf", "dosya", b"%PDF-1.4 eser")
    client, _ = _client(engine, None)
    r = client.post(f"/api/v1/editorial/applications/{a['id']}/preread", json={})
    assert r.status_code == 503 and "Zeki AI" in r.json()["detail"]["message"]
    g = client.get(f"/api/v1/editorial/applications/{a['id']}/preread").json()
    assert g["preread"] is None and g["model"] is False and len(g["files"]) == 1
