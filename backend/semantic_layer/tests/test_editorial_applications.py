"""M1 başvuru, editör değerlendirmesi ve yayın kurulu: akışın sözleşmesi.

Sözleşme: zorunlu alanlar (eser, yazar, özet, biyografi, sayfa tahmini) olmadan başvuru açılmaz; numara yıl içinde
sıralıdır; editör raporu tamamlanmadan kurula çıkılmaz/reddedilmez; red ve revizyon gerekçe ister; kurul gündemine
yalnız «kurula çıkacak» başvuru girer; yalnız üye oy verir, üye kendi oyunu vermeden dağılımı görmez; kararı başkan
ya da yönetici kaydeder, başvurunun durumu kararla değişir; kapanan oturumda kararsız kalan ertelenir ve sıraya döner.
Pazar özeti: ilk yıl = yayın ayı dahil 12 ay, iade düşülür, senaryolar çeyreklerdir, baskı önerisi 500'e yuvarlanır.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from semantic_bridge import access as ACC
from semantic_bridge import editorial_applications as M
from semantic_bridge import editorial_applications_market as K
from semantic_layer.store.catalog_store import open_store

T = "t1"
CAT = "0a1b2c3d-1111-2222-3333-444455556666"
PDF = b"%PDF-1.4\n%\xe2\xe3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITORIAL_APPLICATIONS_DIR", str(tmp_path / "apps"))
    e = open_store("sqlite://").engine
    M._ready.discard(id(e))
    M.ensure(e)
    return e


def _app(engine, **over):
    body = {"title": "Osmanlı'da Kahve ve Toplum", "authorName": "Deniz Yazar", "summary": "Kahvehanelerin tarihi.",
            "authorBio": "Tarihçi.", "pageEstimate": 240, "channel": "eposta", "receivedOn": "2026-09-01",
            "categoryId": CAT, "categoryName": "Tarih Kitaplığı", "audience": "yetiskin"}
    body.update(over)
    return M.create(engine, T, "ayse", "Ayşe Editör", body)


def _evaluate(engine, aid, user="ayse", **over):
    body = {"contentScore": 80, "mission": 75, "publishing": 70, "commercial": 60, "recommendation": "kabul",
            "redline": "temiz", "report": "Güçlü bir dosya.", "submit": True}
    body.update(over)
    return M.save_evaluation(engine, T, user, "Ayşe Editör", aid, body, manager=False)


def test_required_fields_and_numbering(engine):
    for key, msg in (("title", "Eser adı"), ("summary", "Eser özeti"), ("authorBio", "biyografisi"), ("pageEstimate", "Sayfa")):
        with pytest.raises(M.ApplicationError, match=msg):
            _app(engine, **{key: ""})
    with pytest.raises(M.ApplicationError, match="E-posta"):
        _app(engine, authorEmail="yok")
    with pytest.raises(M.ApplicationError, match="Kategori adı"):
        _app(engine, categoryName="")
    with pytest.raises(M.ApplicationError, match="Yaş"):
        _app(engine, ageFrom=12, ageTo=8)
    a, b = _app(engine), _app(engine, title="İkinci")
    assert (a["no"], b["no"]) == ("B-2026-0001", "B-2026-0002")
    assert a["status"] == "yeni" and a["channelLabel"] == "E-posta" and a["audienceLabel"] == "Yetişkin"
    lst = M.listing(engine, T, "ayse", view="kuyruk")
    assert [x["no"] for x in lst["items"]] == ["B-2026-0002", "B-2026-0001"] and lst["counts"]["yeni"] == 2
    assert M.listing(engine, T, "ayse", view="kuyruk", q="ikinci")["items"][0]["title"] == "İkinci"


def test_evaluation_gates_the_editor_decision(engine):
    a = _app(engine)
    with pytest.raises(M.ApplicationError, match="yönetimi"):
        M.assign(engine, T, "ayse", "Ayşe", a["id"], "mehmet", "Mehmet", manager=False)
    a = M.assign(engine, T, "ayse", "Ayşe", a["id"], "ayse", "Ayşe Editör", manager=False)
    assert a["status"] == "degerlendirmede" and a["evaluator"] == "ayse"
    with pytest.raises(M.ApplicationError, match="atanan editör"):
        M.save_evaluation(engine, T, "mehmet", "Mehmet", a["id"], {"report": "x"}, manager=False)
    with pytest.raises(M.ApplicationError, match="editör raporu"):
        M.editor_decision(engine, T, "ayse", "Ayşe", a["id"], "kurula", None, manager=False)
    with pytest.raises(M.ApplicationError, match="eksik: .*ticari"):
        _evaluate(engine, a["id"], commercial=None)
    with pytest.raises(M.ApplicationError, match="açıklaması"):
        _evaluate(engine, a["id"], redline="dikkat")
    with pytest.raises(M.ApplicationError, match="0 ile 100"):
        _evaluate(engine, a["id"], mission=140)
    e = _evaluate(engine, a["id"])
    assert e["submitted"] and e["total"] == 68 and e["recommendationLabel"] == "Kabul"
    with pytest.raises(M.ApplicationError, match="gerekçe"):
        M.editor_decision(engine, T, "ayse", "Ayşe", a["id"], "red", "", manager=False)
    out = M.editor_decision(engine, T, "ayse", "Ayşe", a["id"], "kurula", None, manager=False)
    assert out["status"] == "kurul_bekliyor"
    d = M.detail(engine, T, "ayse", a["id"], can_see_names=False)
    assert [x["action"] for x in d["log"]][:3] == ["karar_kurula", "rapor_tamamlandi", "atandi"]


def test_reject_archives_and_reopen_starts_a_new_round(engine):
    a = _app(engine)
    M.assign(engine, T, "ayse", "Ayşe", a["id"], "ayse", "Ayşe", manager=False)
    _evaluate(engine, a["id"], recommendation="red")
    out = M.editor_decision(engine, T, "ayse", "Ayşe", a["id"], "red", "Kapsam dar.", manager=False)
    assert out["status"] == "red" and out["decidedBy"] == "ayse"
    assert M.listing(engine, T, "ayse", view="arsiv")["items"][0]["id"] == a["id"]
    assert M.listing(engine, T, "ayse", view="kuyruk")["items"] == []
    with pytest.raises(M.ApplicationError, match="Kapanmış"):
        M.update(engine, T, "ayse", "Ayşe", a["id"], {"title": "Yeni ad"})
    letter = M.create_letter(engine, T, "ayse", "Ayşe Editör", a["id"], "red", if_missing=True)
    again = M.create_letter(engine, T, "ayse", "Ayşe Editör", a["id"], "red", if_missing=True)
    assert letter["id"] == again["id"] and "Kapsam dar." in letter["body"] and "Sayın Deniz Yazar" in letter["body"]
    with pytest.raises(M.ApplicationError, match="gerekçesi"):
        M.reopen(engine, T, "ayse", "Ayşe", a["id"], "", manager=False)
    r = M.reopen(engine, T, "ayse", "Ayşe", a["id"], "Revize dosya geldi.", manager=False)
    assert r["status"] == "degerlendirmede" and r["round"] == 2
    assert M.detail(engine, T, "ayse", a["id"], can_see_names=False)["evaluation"] is None


def test_waiting_days_count_from_the_step_not_the_last_edit(engine, monkeypatch):
    """«N gündür bu adımda»: durumun değiştiği günden sayılır; düzenleme ve aynı durumda yeniden atama sıfırlamaz."""
    t0 = datetime(2026, 9, 1, 9, tzinfo=timezone.utc)
    clock = [t0]
    monkeypatch.setattr(M, "_now", lambda: clock[0])
    a = _app(engine)
    clock[0] = t0 + timedelta(days=3)
    assert M.listing(engine, T, "ayse")["items"][0]["waitingDays"] == 3
    clock[0] = t0 + timedelta(days=2)
    M.assign(engine, T, "ayse", "Ayşe", a["id"], "ayse", "Ayşe", manager=False)       # yeni → değerlendirmede
    clock[0] = t0 + timedelta(days=9)
    M.update(engine, T, "ayse", "Ayşe", a["id"], {"title": "Yeni ad"})               # durum değişmez
    clock[0] = t0 + timedelta(days=10)
    M.assign(engine, T, "ayse", "Ayşe", a["id"], "mehmet", "Mehmet", manager=True)   # durum yine değerlendirmede
    clock[0] = t0 + timedelta(days=12)
    assert M.listing(engine, T, "ayse")["items"][0]["waitingDays"] == 10
    _evaluate(engine, a["id"], user="mehmet")
    M.editor_decision(engine, T, "mehmet", "Mehmet", a["id"], "kurula", None, manager=False)
    clock[0] = t0 + timedelta(days=13)
    assert M.listing(engine, T, "ayse")["items"][0]["waitingDays"] == 1


def test_files_are_checked_and_stored(engine):
    a = _app(engine)
    with pytest.raises(M.ApplicationError, match="PDF, DOCX"):
        M.add_file(engine, T, "ayse", "Ayşe", a["id"], "a.exe", "dosya", b"MZ")
    with pytest.raises(M.ApplicationError, match="uyuşmuyor"):
        M.add_file(engine, T, "ayse", "Ayşe", a["id"], "a.pdf", "dosya", b"PK\x03\x04xxxx")
    with pytest.raises(M.ApplicationError, match="10 MB"):
        M.add_file(engine, T, "ayse", "Ayşe", a["id"], "a.pdf", "dosya", b"%PDF" + b"0" * M.FILE_MAX)
    f = M.add_file(engine, T, "ayse", "Ayşe", a["id"], "../../dosya.pdf", "dosya", PDF)
    assert f["filename"] == "dosya.pdf" and f["bytes"] == len(PDF)
    got = M.file_for(engine, T, f["id"])
    assert open(got["path"], "rb").read() == PDF and got["mime"] == "application/pdf"
    with pytest.raises(M.ApplicationError):
        M.file_for(engine, "baska", f["id"])
    M.delete_file(engine, T, "ayse", "Ayşe", f["id"])
    with pytest.raises(M.ApplicationError, match="bulunamadı"):
        M.file_for(engine, T, f["id"])


def _to_board(engine, title="Kurul dosyası"):
    a = _app(engine, title=title)
    M.assign(engine, T, "ayse", "Ayşe", a["id"], "ayse", "Ayşe", manager=False)
    _evaluate(engine, a["id"])
    M.editor_decision(engine, T, "ayse", "Ayşe", a["id"], "kurula", None, manager=False)
    return a


def test_board_session_voting_privacy_and_decision(engine):
    a, b = _to_board(engine), _to_board(engine, "Başka dosya")
    s = M.create_session(engine, T, "baskan", "Başkan", {"date": "2026-10-02", "time": "10:00",
                                                          "members": [{"username": "uye1", "display": "Üye Bir"}, "uye2"]})
    ms = [m["username"] for m in s["members"]]
    assert ms[0] == "baskan" and sorted(ms) == ["baskan", "uye1", "uye2"]
    fresh = _app(engine, title="Değerlendirilmemiş")
    with pytest.raises(M.ApplicationError, match="Kurula çıkacak"):
        M.add_to_agenda(engine, T, "baskan", "Başkan", s["id"], fresh["id"], manager=False)
    with pytest.raises(M.ApplicationError, match="başkan"):
        M.add_to_agenda(engine, T, "uye1", "Üye", s["id"], a["id"], manager=False)
    M.add_to_agenda(engine, T, "baskan", "Başkan", s["id"], a["id"], manager=False)
    M.add_to_agenda(engine, T, "baskan", "Başkan", s["id"], b["id"], manager=False)
    assert M.detail(engine, T, "ayse", a["id"], can_see_names=False)["status"] == "kurulda"

    with pytest.raises(M.ApplicationError, match="üyesi değilsiniz"):
        M.vote(engine, T, "yabanci", "Y", s["id"], a["id"], {"vote": "kabul", "mission": 1, "publishing": 1, "commercial": 1})
    with pytest.raises(M.ApplicationError, match="Üç eksen"):
        M.vote(engine, T, "uye1", "Üye Bir", s["id"], a["id"], {"vote": "kabul", "mission": 80})
    with pytest.raises(M.ApplicationError, match="gerekçe"):
        M.vote(engine, T, "uye1", "Üye Bir", s["id"], a["id"], {"vote": "red", "mission": 1, "publishing": 1, "commercial": 1})
    M.vote(engine, T, "uye1", "Üye Bir", s["id"], a["id"], {"vote": "kabul", "mission": 80, "publishing": 70, "commercial": 90})

    # uye2 henüz oy vermedi: dağılımı görmez, adları da görmez.
    d2 = M.session_detail(engine, T, "uye2", s["id"], manager=False, can_see_names=False)
    it = next(x for x in d2["items"] if x["appId"] == a["id"])
    assert it["tally"] == {"voted": 1, "members": 3, "hidden": True} and it["votes"] is None and d2["isMember"]
    M.vote(engine, T, "uye2", "Üye İki", s["id"], a["id"], {"vote": "kabul", "mission": 60, "publishing": 60, "commercial": 60})
    M.vote(engine, T, "uye2", "Üye İki", s["id"], a["id"], {"vote": "revizyon", "mission": 60, "publishing": 60,
                                                           "commercial": 60, "note": "Kurgu zayıf."})  # oy değişir
    it = next(x for x in M.session_detail(engine, T, "uye2", s["id"], manager=False, can_see_names=False)["items"]
              if x["appId"] == a["id"])
    assert it["tally"]["counts"]["revizyon"] == 1 and it["tally"]["tie"] and it["myVote"]["vote"] == "revizyon"
    # Başkan adıyla görür; skor = eksen ortalamalarının ortalaması.
    dc = M.session_detail(engine, T, "baskan", s["id"], manager=False, can_see_names=False, accept=70, revise=50)
    it = next(x for x in dc["items"] if x["appId"] == a["id"])
    assert sorted(v["memberName"] for v in it["votes"]) == ["Üye Bir", "Üye İki"]
    assert it["tally"]["total"] == 70.0 and it["tally"]["byScore"] == "kabul" and it["editor"]["recommendation"] == "kabul"

    with pytest.raises(M.ApplicationError, match="başkan"):
        M.decide(engine, T, "uye1", "Üye", s["id"], a["id"], {"decision": "kabul"}, manager=False)
    out = M.decide(engine, T, "baskan", "Başkan", s["id"], a["id"],
                   {"decision": "kabul", "note": "Oy birliğine yakın.", "printRun": "3000", "publishOn": "2027-03-01"}, manager=False)
    assert out["status"] == "kabul"
    with pytest.raises(M.ApplicationError, match="oy değişmez"):
        M.vote(engine, T, "uye1", "Üye Bir", s["id"], a["id"], {"vote": "red", "note": "x", "mission": 1, "publishing": 1, "commercial": 1})
    letter = M.create_letter(engine, T, "baskan", "Başkan", a["id"], "kabul", if_missing=True)
    assert "01.03.2027" in letter["body"]
    # Karar geri alınınca taslak yazı da gider, başvuru gündeme döner.
    M.decide(engine, T, "baskan", "Başkan", s["id"], a["id"], {"decision": ""}, manager=False)
    d = M.detail(engine, T, "ayse", a["id"], can_see_names=False)
    assert d["status"] == "kurulda" and d["letters"] == []
    M.decide(engine, T, "baskan", "Başkan", s["id"], a["id"], {"decision": "kabul"}, manager=False)
    hist = M.detail(engine, T, "ayse", a["id"], can_see_names=True)["board"][0]
    assert hist["decision"] == "kabul" and hist["tally"]["voted"] == 2 and len(hist["votes"]) == 2

    # Oturum kapanınca kararsız kalan başvuru ertelenir ve kurul sırasına döner.
    assert M.close_session(engine, T, "baskan", "Başkan", s["id"], manager=False)["postponed"] == 1
    assert M.detail(engine, T, "ayse", b["id"], can_see_names=False)["status"] == "kurul_bekliyor"
    with pytest.raises(M.ApplicationError, match="kapandı"):
        M.vote(engine, T, "uye1", "Üye", s["id"], b["id"], {"vote": "kabul", "mission": 1, "publishing": 1, "commercial": 1})
    lst = M.sessions(engine, T, "uye1")["items"][0]
    assert lst["state"] == "kapandi" and lst["agenda"] == {"items": 2, "decided": 2} and lst["myVotes"] == 1


def test_accepted_application_links_to_crm_project(engine):
    a = _to_board(engine)
    with pytest.raises(M.ApplicationError, match="kabul edilen"):
        M.link_crm_project(engine, T, "ayse", "Ayşe", a["id"], CAT, "Proje")
    s = M.create_session(engine, T, "baskan", "Başkan", {"date": "2026-10-02"})
    M.add_to_agenda(engine, T, "baskan", "Başkan", s["id"], a["id"], manager=False)
    M.decide(engine, T, "baskan", "Başkan", s["id"], a["id"], {"decision": "kabul"}, manager=False)
    out = M.link_crm_project(engine, T, "ayse", "Ayşe", a["id"], CAT.upper(), "CRM projesi")
    assert out["crmProjectId"] == CAT and out["crmProjectName"] == "CRM projesi"


def test_tally_majority_tie_and_thresholds():
    class V:
        def __init__(self, vote, m=None, p=None, c=None):
            self.vote, self.mission, self.publishing, self.commercial = vote, m, p, c
    t = M.tally([V("kabul", 90, 80, 70), V("kabul", 70, 70, 70), V("red", 30, 40, 50), V("cekimser")], 5, accept=70, revise=50)
    assert t["majority"] == "kabul" and not t["tie"] and t["counts"]["cekimser"] == 1
    assert t["axes"] == {"mission": 63.3, "publishing": 63.3, "commercial": 63.3} and t["byScore"] == "revizyon"
    assert M.tally([], 3)["majority"] is None and M.tally([], 3)["total"] is None
    assert M.tally([V("red", 10, 10, 10)], 1)["byScore"] == "red"


def test_market_first_year_net_of_returns_and_scenarios():
    today = date(2026, 9, 28)
    start, end = K.window(today)
    assert (start, end) == (date(2022, 9, 1), date(2025, 9, 1))
    books = [{"id": f"k{i}", "ad": f"Kitap {i}", "kod": f"K{i}", "ilk": "2024-03-15", "dizi": "Dizi A" if i < 2 else "Dizi B"}
             for i in range(5)]
    books.append({"id": "kx", "ad": "Satışsız", "kod": "KX", "ilk": "2024-03-01", "dizi": None})
    sales = []
    for i, qty in enumerate([1200, 900, 400, 300, 100]):
        sales.append({"kod": f"K{i}", "yil": 2024, "ay": 3, "kanal": "Mağaza", "tur": "Satış", "adet": qty})
        sales.append({"kod": f"K{i}", "yil": 2025, "ay": 2, "kanal": "E-ticaret", "tur": "Satış", "adet": 100})   # 12. ay
        sales.append({"kod": f"K{i}", "yil": 2025, "ay": 3, "kanal": "E-ticaret", "tur": "Satış", "adet": 1000})  # 13. ay: dışarıda
    sales.append({"kod": "K0", "yil": 2024, "ay": 4, "kanal": "Toptancı", "tur": "İade", "adet": 200})
    out = K.compute(books, sales, today)
    assert out["books"] == 6 and out["withSales"] == 5 and out["withoutSales"] == 1
    firsts = {b["code"]: b["firstYear"] for b in out["list"]}
    assert firsts["K0"] == 1100 and firsts["K4"] == 200 and firsts["KX"] == 0
    assert out["scenarios"] == {"kotumser": 400, "baz": 500, "iyimser": 1000}
    assert out["printRun"]["suggested"] == 500
    assert out["series"] == {"name": "Dizi A", "count": 2, "of": 2}
    ch = {c["name"]: c["qty"] for c in out["channels"]}
    # Son 36 ay: 2023-10 … 2026-09 → bütün satırlar.
    assert ch == {"Mağaza": 2900, "E-ticaret": 5500, "Toptancı": -200} and out["last36"] == 8200
    assert out["curve"][0] == 400 and len(out["curve"]) == 12
    assert K.channel_label("KITAPCI") == "Kitapçı" and K.channel_label("  ") == "Kanal girilmemiş"


def test_overlap_query_uses_significant_words_only():
    sql = K.overlap_sql("Timas_MSCRM.dbo", "Bir Kahve ve Osmanlı İçin Yeni Roman", None)
    assert "kahve" in sql and "osmanlı" in sql and "roman" not in sql.split("WHERE", 1)[1]
    assert ">= 2" in sql
    assert K.overlap_sql("Timas_MSCRM.dbo", "Ve bir", None) is None
    one = K.overlap_sql("Timas_MSCRM.dbo", "Kahve", "0a1b2c3d-1111-2222-3333-444455556666")
    assert ">= 1" in one and "new_Katilimsaglayan = '0a1b2c3d-1111-2222-3333-444455556666'" in one
    with pytest.raises(K.MarketError):
        K.cohort_sql("Timas_MSCRM.dbo", "x' OR 1=1 --", date(2022, 1, 1), date(2025, 1, 1))
    assert "N'A''B'" in K.sales_sql(2025, ["A'B"])


def test_access_rules_for_m1():
    pages = ACC.rule_for("/api/v1/editorial/applications/abc")
    assert pages == {"sayfa:basvurular", "sayfa:yayin-kurulu"}
    assert ACC.rule_for("/api/v1/editorial/board-sessions/x/votes/y") == {"sayfa:yayin-kurulu", "sayfa:basvurular"}
    assert ACC.features_for("POST", "/api/v1/editorial/applications") == ["ozellik:basvuru.yaz"]
    assert ACC.features_for("PUT", "/api/v1/editorial/applications/a/files") == ["ozellik:basvuru.yaz"]
    assert ACC.features_for("GET", "/api/v1/editorial/applications/a") == []
    assert ACC.features_for("PUT", "/api/v1/editorial/board-sessions/s/votes/a") == []
    keys = ACC.all_keys()
    assert {"sayfa:basvurular", "ozellik:basvuru.yaz", "ozellik:basvuru.yonet", "ozellik:yayin-kurulu.yonet"} <= set(keys)


# ------------------------------------------------------------------ kabul referans betiği (scripts/acceptance/m1/market_ref.py)


def _market_ref():
    import importlib.util
    from pathlib import Path

    p = Path(__file__).resolve().parents[3] / "scripts" / "acceptance" / "m1" / "market_ref.py"
    if not p.is_file():
        pytest.skip("kabul betiği bu ağaçta yok")
    spec = importlib.util.spec_from_file_location("m1_market_ref", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)   # içe aktarım DB'ye bağlanmaz (bağlantı yalnız main'de)
    return mod


def test_market_ref_reads_dates_as_text_or_date():
    from datetime import datetime

    R = _market_ref()
    want = 2023 * 12 + 4
    for v in (date(2023, 5, 1), datetime(2023, 5, 1, 0, 0), "2023-05-01", "2023-05-01 00:00:00.000", "2023-05-01T00:00:00",
              b"2023-05-01", "01.05.2023", "1/5/2023"):
        assert R.month_index(v) == want, v
    assert R.month_index(None) is None and R.month_index("") is None and R.month_index("bilinmiyor") is None
    assert R.month_index("2023-13-01") is None
    idx, bad = R.cohort_index([{"kod": "A", "ilk": "2023-05-01"}, {"kod": "B", "ilk": date(2024, 1, 2)}, {"kod": "C", "ilk": None}])
    assert idx == {"A": want, "B": 2024 * 12} and bad == ["C"]


def test_market_ref_multi_statement_query_sets_nocount():
    R = _market_ref()
    sql = R.cohort_sql("Tarih Kitaplığı")
    assert sql.lstrip().upper().startswith("SET NOCOUNT ON;") and sql.index("DECLARE") > sql.index("NOCOUNT")
    assert "N'Tarih Kitaplığı'" in sql
    assert "N'Ali''nin Kitaplığı'" in R.cohort_sql("Ali'nin Kitaplığı")   # tırnak kaçışı
