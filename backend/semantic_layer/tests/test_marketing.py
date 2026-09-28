"""Pazarlama çekirdeği ve M15 yeni kitap planı: durum makinesi (iki göz, eşik üstü ikinci onay, revizyon), bütçe
satırlarında elle düzeltmenin korunması, materyal onay sırası, Zeki AI metin denetimi (alıntı, rakam, iddia, teknoloji
adı), yayın günü önceliği, hedef değişimi, bütçe çerçevesi ve kanal payı kuralları, liste süzgeçleri, «CRM'e işlenecek»
listesi, sözleşme ucu, dışa aktarım ve yetki kuralları.

Veriler yapaydır ve yalnız kuralları sınar; gerçek CRM/Logo kabulü test sunucusunda (`scripts/acceptance/m15/`).
"""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import date, timedelta

import pytest
import sqlalchemy as sa

from semantic_bridge import access as A
from semantic_bridge import budget as B
from semantic_bridge.marketing import core as C
from semantic_bridge.marketing import export as X
from semantic_bridge.marketing import guard as G
from semantic_bridge.marketing import plans as P
from semantic_layer.store.catalog_store import open_store

T = "t1"


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    C._ready.discard(id(e))
    B._ready.discard(id(e))
    C.ensure(e)
    B.ensure(e)
    yield e
    # `ensure` motoru id'siyle hatırlar: kapanan motorun id'si sonraki testte yeni bir motora verilirse tablolar hiç
    # kurulmaz («no such table: semantic_budget_meta»). Test bitince kayıt silinir.
    C._ready.discard(id(e))
    B._ready.discard(id(e))


def _st(**over):
    s = P.settings(lambda k: "")
    s.update(over)
    return s


def _plan(engine, user="ayse", pub="2026-11-15", stok="15201.0001"):
    return C.create_plan(engine, T, user, kind="yeni", baslik="Deneme · plan", stok_kodu=stok, yayin_tarihi=pub,
                         yayin_kaynagi="crm-kitap", hedef={"planId": None})


def _lines(engine, pid, *amounts, user="ayse"):
    return C.replace_lines(engine, T, user, pid, [{"kanal": "basin", "tutar": a, "baslangic": "2026-10-01", "bitis": "2026-11-30"}
                                                  for a in amounts])


class FakeCrm:
    def __init__(self, books=None, detail=None, spend=None):
        self._books = books or []
        self._detail = detail
        self._spend = spend or []

    def new_books(self, frm, to, fresh=False):
        return list(self._books)

    def book(self, stok, fresh=False):
        return self._detail

    def rivals(self, kitap_id):
        return []

    def special_days(self, kitap_id):
        return []

    def spend(self, since, fresh=False):
        return list(self._spend)

    def email_of(self, user):
        return None


def _book(code, **kw):
    b = {"kitapId": None, "stokKodu": code, "ad": f"Kitap {code}", "yazar": "Yazar A", "yayinevi": "Timaş Yayınları",
         "kitaplik": "Roman", "hedefKitle": "Yetişkin", "statu": None, "kapak": None,
         "tarihler": {"crm-kitap": None, "crm-proje": None, "uretim-dagilim": None, "uretim-depo": None},
         "projeId": None, "projeAdi": None, "sorumlu": None, "sorumluHesap": None}
    b.update(kw)
    return b


# ------------------------------------------------------------------ durum makinesi


def test_plan_ids_are_sequential_per_year(engine):
    a, b = _plan(engine, stok="A"), _plan(engine, stok="B")
    y = date.today().year
    assert a == f"MP-{y}-0001" and b == f"MP-{y}-0002"


def test_one_open_new_book_plan_per_book(engine):
    _plan(engine)
    with pytest.raises(C.MarketingError) as e:
        _plan(engine)
    assert e.value.status == 409


def test_submit_needs_lines_and_publication_date(engine):
    pid = _plan(engine)
    with pytest.raises(C.MarketingError):
        C.submit(engine, T, "ayse", pid)
    nodate = _plan(engine, pub=None, stok="X")
    _lines(engine, nodate, 100)
    with pytest.raises(C.MarketingError):
        C.submit(engine, T, "ayse", nodate)


def test_sender_cannot_approve_and_second_person_does(engine):
    pid = _plan(engine)
    _lines(engine, pid, 1000)
    C.submit(engine, T, "ayse", pid)
    with pytest.raises(C.MarketingError) as e:
        C.decide(engine, T, "ayse", pid, True, None, level="pazarlama", threshold=None)
    assert e.value.status == 409
    out = C.decide(engine, T, "mudur", pid, True, None, level="pazarlama", threshold=None)
    assert out["durum"] == "onayli" and out["onaylayan"] == "mudur"


def test_over_threshold_needs_two_different_approvers(engine):
    pid = _plan(engine)
    _lines(engine, pid, 60_000, 50_000)
    C.submit(engine, T, "ayse", pid)
    out = C.decide(engine, T, "mudur", pid, True, None, level="pazarlama", threshold=100_000)
    assert out["durum"] == "onayda"                                 # tek onay yetmez
    with pytest.raises(C.MarketingError):
        C.decide(engine, T, "mudur", pid, True, None, level="ust", threshold=100_000)
    out = C.decide(engine, T, "gm", pid, True, None, level="ust", threshold=100_000)
    assert out["durum"] == "onayli" and out["ustOnaylayan"] == "gm"


def test_upper_approval_is_refused_below_threshold_and_without_threshold(engine):
    pid = _plan(engine)
    _lines(engine, pid, 10)
    C.submit(engine, T, "ayse", pid)
    for th in (None, 100.0):
        with pytest.raises(C.MarketingError):
            C.decide(engine, T, "gm", pid, True, None, level="ust", threshold=th)


def test_reject_needs_reason_and_returns_editable(engine):
    pid = _plan(engine)
    _lines(engine, pid, 10)
    C.submit(engine, T, "ayse", pid)
    with pytest.raises(C.MarketingError):
        C.decide(engine, T, "mudur", pid, False, "", level="pazarlama", threshold=None)
    out = C.decide(engine, T, "mudur", pid, False, "Emsal yanlış", level="pazarlama", threshold=None)
    assert out["durum"] == "geri" and out["gerekce"] == "Emsal yanlış"
    _lines(engine, pid, 20)                                         # geri gönderilen plan düzenlenir
    assert C.submit(engine, T, "ayse", pid)["durum"] == "onayda"


def test_approved_plan_is_frozen_and_revision_archives_it(engine):
    pid = _plan(engine)
    _lines(engine, pid, 10)
    C.submit(engine, T, "ayse", pid)
    C.decide(engine, T, "mudur", pid, True, None, level="pazarlama", threshold=None)
    with pytest.raises(C.MarketingError):
        _lines(engine, pid, 99)
    with pytest.raises(C.MarketingError):
        C.revise(engine, T, "ayse", pid, "")
    new = C.revise(engine, T, "ayse", pid, "Hedef değişti")
    assert new["surum"] == 2 and new["oncekiId"] == pid and new["durum"] == "taslak" and len(new["lines"]) == 1
    with pytest.raises(C.MarketingError):
        C.revise(engine, T, "ayse", pid, "ikinci")                   # açık revizyon varken ikinci açılmaz
    C.submit(engine, T, "ayse", new["id"])
    out = C.decide(engine, T, "mudur", new["id"], True, None, level="pazarlama", threshold=None)
    assert out["archived"] == pid and C.plan_full(engine, T, pid)["durum"] == "arsiv"


def test_only_draft_is_deleted(engine):
    pid = _plan(engine)
    _lines(engine, pid, 10)
    C.submit(engine, T, "ayse", pid)
    with pytest.raises(C.MarketingError):
        C.delete_plan(engine, T, pid)


# ------------------------------------------------------------------ satırlar, takvim, materyal


def test_manual_edit_of_a_suggested_line_survives_a_new_suggestion(engine):
    pid = _plan(engine)
    C.put_suggested_lines(engine, T, "ayse", pid, [{"kanal": "basin", "tutar": 100}, {"kanal": "dijital", "tutar": 200}])
    plan = C.plan_full(engine, T, pid)
    items = [{**ln, "tutar": 150 if ln["kanal"] == "basin" else ln["tutar"]} for ln in plan["lines"]]
    plan = C.replace_lines(engine, T, "ayse", pid, items)
    assert {ln["kanal"]: ln["elleDuzeltildi"] for ln in plan["lines"]} == {"basin": True, "dijital": False}
    C.put_suggested_lines(engine, T, "ayse", pid, [{"kanal": "basin", "tutar": 999}, {"kanal": "dijital", "tutar": 300},
                                                   {"kanal": "medya", "tutar": 50}])
    plan = C.plan_full(engine, T, pid)
    by = {ln["kanal"]: ln["tutar"] for ln in plan["lines"]}
    assert by == {"basin": 150, "dijital": 300, "medya": 50}
    assert plan["butceToplam"] == 500


def test_line_validation(engine):
    pid = _plan(engine)
    with pytest.raises(C.MarketingError):
        C.replace_lines(engine, T, "ayse", pid, [{"kanal": "uzay", "tutar": 1}])
    with pytest.raises(C.MarketingError):
        C.replace_lines(engine, T, "ayse", pid, [{"kanal": "basin", "tutar": -5}])
    with pytest.raises(C.MarketingError):
        C.replace_lines(engine, T, "ayse", pid, [{"kanal": "basin", "tutar": 1, "baslangic": "2026-10-10", "bitis": "2026-10-01"}])


def test_template_tasks_count_back_from_publication_and_move_with_it(engine):
    pid = _plan(engine, pub="2026-11-15")
    C.replace_tasks(engine, T, "ayse", pid, P.template_tasks("2026-11-15", _st(), []), system=True)
    plan = C.plan_full(engine, T, pid)
    first = min(plan["tasks"], key=lambda t: t["gunFarki"])
    assert first["gunFarki"] == -60 and first["tarih"] == "2026-09-16"
    C.update_plan(engine, T, "ayse", pid, {"yayinTarihi": "2026-12-15"})
    C.reschedule(engine, T, "ayse", pid)
    plan = C.plan_full(engine, T, pid)
    assert min(plan["tasks"], key=lambda t: t["gunFarki"])["tarih"] == "2026-10-16"
    assert plan["yayinTarihiKaynagi"] == "elle"


def test_approved_plan_calendar_accepts_only_status(engine):
    pid = _plan(engine)
    _lines(engine, pid, 10)
    C.replace_tasks(engine, T, "ayse", pid, P.template_tasks("2026-11-15", _st(), []), system=True)
    C.submit(engine, T, "ayse", pid)
    C.decide(engine, T, "mudur", pid, True, None, level="pazarlama", threshold=None)
    tasks = C.plan_full(engine, T, pid)["tasks"]
    out = C.replace_tasks(engine, T, "ayse", pid, [{**tasks[0], "durum": "yapildi", "kanitUrl": "https://x"}])
    assert next(t for t in out["tasks"] if t["id"] == tasks[0]["id"])["durum"] == "yapildi"
    with pytest.raises(C.MarketingError):
        C.replace_tasks(engine, T, "ayse", pid, [{"is": "yeni iş", "durum": "bekliyor"}])


def test_material_needs_editorial_then_another_persons_marketing_approval(engine):
    pid = _plan(engine)
    m = C.add_material(engine, T, "ayse", pid, "foy", "Föy metni", "crm:new_TantmFyMetni")
    with pytest.raises(C.MarketingError):
        C.approve_material(engine, T, "mudur", m["id"], "pazarlama")      # önce editoryal
    C.approve_material(engine, T, "editor", m["id"], "editoryal")
    with pytest.raises(C.MarketingError):
        C.approve_material(engine, T, "editor", m["id"], "pazarlama")     # aynı kişi iki onay veremez
    out = C.approve_material(engine, T, "mudur", m["id"], "pazarlama")
    assert out["durum"] == "onayli"
    edited = C.update_material(engine, T, "ayse", m["id"], "Föy metni (düzeltildi)")
    assert edited["durum"] == "taslak" and edited["surum"] == 2 and edited["onaylayan"] is None and edited["kaynak"] == "kullanici"


def test_zeki_draft_replaces_its_own_draft_not_approved_ones(engine):
    pid = _plan(engine)
    a = C.add_material(engine, T, "ayse", pid, "sosyal", "ilk", "zeki", replace_draft=True)
    b = C.add_material(engine, T, "ayse", pid, "sosyal", "ikinci", "zeki", replace_draft=True)
    assert a["id"] == b["id"] and b["surum"] == 2
    C.approve_material(engine, T, "editor", a["id"], "editoryal")
    c = C.add_material(engine, T, "ayse", pid, "sosyal", "üçüncü", "zeki", replace_draft=True)
    assert c["id"] != a["id"]


def test_contract_exposes_only_approved_plans_and_materials(engine):
    pid = _plan(engine)
    _lines(engine, pid, 10)
    ok = C.add_material(engine, T, "ayse", pid, "foy", "onaylı föy", "zeki")
    C.add_material(engine, T, "ayse", pid, "sosyal", "taslak metin", "zeki")
    C.approve_material(engine, T, "editor", ok["id"], "editoryal")
    C.approve_material(engine, T, "mudur", ok["id"], "pazarlama")
    assert C.contract(engine, T)["total"] == 0
    C.submit(engine, T, "ayse", pid)
    C.decide(engine, T, "mudur", pid, True, None, level="pazarlama", threshold=None)
    out = C.contract(engine, T, stok="15201.0001")
    assert out["total"] == 1 and [m["tur"] for m in out["items"][0]["materials"]] == ["foy"]
    assert "zeki" not in out["items"][0]


def test_every_write_leaves_history(engine):
    pid = _plan(engine)
    _lines(engine, pid, 10)
    C.submit(engine, T, "ayse", pid)
    kinds = [e["ne"] for e in C.events(engine, pid)]
    assert {"olusturuldu", "butce", "onaya-gonderildi"} <= set(kinds)


# ------------------------------------------------------------------ metin denetimi


def test_guard_drops_unverified_quote_but_keeps_verbatim_one():
    src = ["Kitaptan alıntılar: Her yolculuk bir soruyla başlar."]
    out = G.check("Yazar şöyle diyor: «Her yolculuk bir soruyla başlar.» Okurlar sevecek. «Uydurma bir cümle burada.»", src)
    assert "Her yolculuk" in out["metin"] and "Uydurma" not in out["metin"]
    assert out["sayac"] == {"alinti-bulunamadi": 1}


def test_guard_drops_numbers_not_in_sources_or_facts():
    out = G.check("Kitap 1.250 adet sattı. Fiyatı 245 TL. 320 sayfa.", ["Sayfa sayısı: 320"], ["Kapak fiyatı: 245 TL"])
    assert "1.250" not in out["metin"] and "245 TL" in out["metin"] and "320" in out["metin"]
    assert out["sayac"] == {"kaynaksiz-rakam": 1}


def test_guard_drops_superiority_claims_and_tech_names():
    out = G.check("Yılın en çok satan romanı. Bu metni Qwen yazdı. Sıcak bir aile hikâyesi.", [], [], ["efsane"])
    assert out["metin"] == "Sıcak bir aile hikâyesi."
    assert out["sayac"] == {"kanitsiz-iddia": 1, "teknoloji-adi": 1}
    assert G.check("Efsane bir kitap.", [], [], ["efsane"])["dusenSayisi"] == 1


def test_guard_number_formats_match():
    assert G.numbers_in("12,5 ve 1.250") == {"125", "1250"}


# ------------------------------------------------------------------ kurallar


def test_publication_date_follows_the_configured_order():
    t = {"crm-kitap": None, "crm-proje": "2026-10-01", "uretim-dagilim": "2026-10-05", "uretim-depo": "2026-10-03"}
    assert P.resolve_pub(t, ["crm-kitap", "crm-proje", "uretim"]) == ("2026-10-01", "crm-proje")
    assert P.resolve_pub(t, ["uretim", "crm-proje"]) == ("2026-10-03", "uretim")    # depo girişi planın önünde
    assert P.resolve_pub({**t, "crm-proje": None, "uretim-depo": None}, ["crm-kitap", "crm-proje", "uretim"]) == ("2026-10-05", "uretim")
    assert P.resolve_pub({k: None for k in t}, ["crm-kitap"]) == (None, None)


def test_target_change_detection():
    saved = {"planId": "p1", "version": 1, "adet": 100, "ciro": 1000}
    assert not P.target_changed(saved, {"planId": "p1", "version": 1, "adet": 100, "ciro": 1000})
    assert P.target_changed(saved, {"planId": "p2", "version": 2, "adet": 100, "ciro": 1000})
    assert P.target_changed(saved, {"planId": "p1", "version": 1, "adet": 120, "ciro": 1000})
    assert P.target_changed({"planId": None}, {"planId": "p1", "version": 1, "adet": 1, "ciro": 1})
    # kitap planda hiç yoktu ve hâlâ yok: değişiklik değil
    assert not P.target_changed({"planId": "p1", "version": 1, "adet": None, "ciro": None},
                                {"planId": "p1", "version": 1, "adet": None, "ciro": None})


def test_budget_frame_prefers_crm_project_then_rate_then_department_ratio(engine):
    card = {"crmButce": {"toplamKurul": 50_000, "toplam": 40_000}, "hedef": {"ciro": 1_000_000}}
    assert P.budget_frame(engine, card, _st())["tutar"] == 50_000
    card["crmButce"] = {}
    f = P.budget_frame(engine, card, _st(rate=0.03))
    assert f["tutar"] == 30_000 and f["kaynak"] == "oran" and f["oran"]["kaynak"] == "ayar"
    assert P.budget_frame(engine, card, _st())["tutar"] is None           # oran yok, veri yok: uydurma yok
    with engine.begin() as c:
        c.execute(B.SALES.insert(), [dict(year=2025, month=m, stok_kodu="K", adet=1, ciro=100_000, maliyet=0, maliyetli_ciro=0)
                                     for m in range(1, 13)])
        c.execute(B.EXPENSES.insert(), [
            dict(year=2025, month=1, merkez_kodu="B04-PAZ-01", hesap="760", merkez_adi="PAZARLAMA", hesap_adi="x", tutar=24_000),
            dict(year=2025, month=1, merkez_kodu="B01-GMD-01", hesap="770", merkez_adi="GENEL MÜDÜRLÜK", hesap_adi="y", tutar=99_000)])
    B.meta_set(engine, "data_end", {"date": "2026-08-17"})
    f = P.budget_frame(engine, card, _st())
    assert f["oran"]["yil"] == 2025 and f["oran"]["oran"] == pytest.approx(0.02) and f["tutar"] == 20_000
    assert P.budget_frame(engine, {"crmButce": {}, "hedef": {}}, _st())["tutar"] is None   # hedef ciro yok


def test_channel_shares_use_emsal_spend_then_company_spend():
    spend = [
        {"id": "a", "tip": 1, "tipAdi": "Basın", "tutar": 300, "stokKodu": "E1"},
        {"id": "b", "tip": 4, "tipAdi": "Sosyal Medya", "tutar": 100, "stokKodu": "E1"},
        {"id": "c", "tip": 5, "tipAdi": "Dijital Pazarlama", "tutar": 600, "stokKodu": "Z9"},
        {"id": "c", "tip": 5, "tipAdi": "Dijital Pazarlama", "tutar": 600, "stokKodu": "Z8"},   # aynı kayıt iki kitaba bağlı
    ]
    crm = FakeCrm(spend=spend)
    em = P.channel_shares(crm, ["E1"], _st())
    assert em["taban"]["kaynak"] == "emsal" and em["paylar"] == {"basin": 0.75, "sosyal-medya": 0.25}
    co = P.channel_shares(crm, ["YOK"], _st())
    assert co["taban"]["kaynak"] == "sirket" and co["paylar"]["dijital"] == pytest.approx(0.6)
    assert P.channel_shares(FakeCrm(), [], _st())["paylar"] == {}


def test_suggested_lines_sum_to_the_frame_and_are_empty_without_frame():
    shares = {"paylar": {"basin": 1 / 3, "dijital": 2 / 3}, "taban": {"kaynak": "emsal", "kitap": 2}}
    lines = P.suggest_lines({"tutar": 10_000}, shares, "2026-11-15")
    assert round(sum(x["tutar"] for x in lines), 2) == 10_000
    assert lines[0]["baslangic"] == "2026-10-16"
    assert all(x["tutar"] == 0 for x in P.suggest_lines({"tutar": None}, shares, "2026-11-15"))


def test_crm_materials_come_with_their_source():
    out = P.crm_materials([{"alan": "new_tanitimfoymetni", "ad": "", "metin": "uzun föy"}, {"alan": "new_ozet", "ad": "", "metin": "arka"}])
    assert ("foy", "uzun föy", "crm:new_tanitimfoymetni") in out and ("arka-kapak", "arka", "crm:new_ozet") in out


def test_new_books_window_kpis_and_my_filter(engine):
    today = date.today()
    d = lambda n: (today + timedelta(days=n)).isoformat()  # noqa: E731
    books = [
        _book("A", tarihler={"crm-kitap": d(20), "crm-proje": None, "uretim-dagilim": None, "uretim-depo": None}, sorumluHesap="ayse"),
        _book("B", tarihler={"crm-kitap": d(90), "crm-proje": None, "uretim-dagilim": None, "uretim-depo": None}),
        _book("C", tarihler={"crm-kitap": None, "crm-proje": d(10), "uretim-dagilim": None, "uretim-depo": None}),
        _book("D", tarihler={"crm-kitap": d(400), "crm-proje": d(5), "uretim-dagilim": None, "uretim-depo": None}),  # esas tarih pencere dışı
    ]
    pid = _plan(engine, stok="C", pub=d(10), user="mehmet")
    _lines(engine, pid, 10, user="mehmet")
    C.submit(engine, T, "mehmet", pid)
    out = P.new_books(engine, T, "ayse", FakeCrm(books), _st(), frm=today, to=today + timedelta(days=120))
    assert [r["stokKodu"] for r in out["items"]] == ["C", "A", "B"] and out["total"] == 3
    assert out["kpi"]["plansiz"] == 1 and out["kpi"]["onayda"] == 1
    mine = P.new_books(engine, T, "ayse", FakeCrm(books), _st(), frm=today, to=today + timedelta(days=120), sahip="ben")
    assert [r["stokKodu"] for r in mine["items"]] == ["A"]
    mine = P.new_books(engine, T, "ayse", FakeCrm(books), _st(), frm=today, to=today + timedelta(days=120), sahip="ben", can_approve=True)
    assert [r["stokKodu"] for r in mine["items"]] == ["C", "A"]            # onayımı bekleyen de bana düşer
    only = P.new_books(engine, T, "ayse", FakeCrm(books), _st(), frm=today, to=today + timedelta(days=120), durum="plansiz")
    assert {r["stokKodu"] for r in only["items"]} == {"A", "B"}


def test_create_plan_pulls_crm_texts_and_template(engine):
    pub = (date.today() + timedelta(days=70)).isoformat()
    detail = {**_book("N1", tarihler={"crm-kitap": pub, "crm-proje": None, "uretim-dagilim": None, "uretim-depo": None},
                      sorumluHesap="ayse", kitapId="11111111-2222-3333-4444-555555555555"),
              "turler": "Roman", "yas": [None, None], "fiyat": 250.0, "sayfa": 320.0,
              "metinler": {"new_ozet": "Arka kapak", "new_BasnBlteni": "Bülten", "new_TantmFyMetni": None},
              "proje": {}}
    pid = P.create_new_book_plan(engine, T, "mehmet", FakeCrm(detail=detail), None, _st(), {"stokKodu": "N1"})
    plan = C.plan_full(engine, T, pid)
    assert plan["sahip"] == "ayse" and plan["yayinTarihi"] == pub and plan["yayinTarihiKaynagi"] == "crm-kitap"
    assert {(m["tur"], m["kaynak"]) for m in plan["materials"]} == {("arka-kapak", "crm:new_ozet"), ("basin-bulteni", "crm:new_BasnBlteni")}
    assert len(plan["tasks"]) == len(P.DEFAULT_TASKS)
    card = C.card_get(engine, T, "N1")
    assert card["emsal"]["hazir"] is False and card["hedef"]["planId"] is None


def test_plan_works_without_the_budget_module(engine, monkeypatch):
    """Bütçe (M46) kurulmamış / tabloları okunamıyor: M15 hata vermez, «hedef yok» ve boş çerçeveyle devam eder."""
    def broken(_engine):
        raise sa.exc.OperationalError("SELECT 1", {}, Exception("no such table: semantic_budget_meta"))

    monkeypatch.setattr(B, "ensure", broken)
    pub = (date.today() + timedelta(days=40)).isoformat()
    h = P.target_for(engine, T, "N2", pub)
    assert h["planId"] is None and "okunamıyor" in h["not"]
    assert P.targets_many(engine, T, {date.today().year: ["N2"]}) == {}
    assert P.data_end(engine) is None and P.dept_ratio(engine, _st()) is None
    detail = {**_book("N2", tarihler={"crm-kitap": pub, "crm-proje": None, "uretim-dagilim": None, "uretim-depo": None}),
              "turler": None, "yas": [None, None], "fiyat": None, "sayfa": None, "metinler": {}, "proje": {}}
    assert P.author_section(engine, None, detail)["not"].startswith("Bütçe modülünün")
    pid = P.create_new_book_plan(engine, T, "ayse", FakeCrm(detail=detail), None, _st(), {"stokKodu": "N2"})
    plan = C.plan_full(engine, T, pid)
    assert plan["hedef"]["planId"] is None and plan["butceCerceve"] is None
    out = P.new_books(engine, T, "ayse", FakeCrm(books=[detail]), _st(), frm=date.today(), to=date.today() + timedelta(days=120))
    assert out["total"] == 1 and out["items"][0]["hedef"] is None


def test_budget_tables_are_created_when_the_engine_id_was_remembered(monkeypatch):
    """Motor id'si eski bir motordan kalmışsa (ensure kurulumu atlar) okuma bir kez yeniden kurar."""
    e = open_store("sqlite://").engine
    B._ready.add(id(e))                                              # kurulmuş sanılıyor, tablo yok
    try:
        assert P.data_end(e) is None
        assert "semantic_budget_meta" in set(sa.inspect(e).get_table_names())
    finally:
        B._ready.discard(id(e))


def test_crm_todo_lists_differences_only(engine):
    pid = _plan(engine)
    _lines(engine, pid, 1234)
    m = C.add_material(engine, T, "ayse", pid, "basin-bulteni", "Yeni bülten", "zeki")
    same = C.add_material(engine, T, "ayse", pid, "arka-kapak", "Aynı metin", "crm:new_ozet")
    for x in (m, same):
        C.approve_material(engine, T, "editor", x["id"], "editoryal")
        C.approve_material(engine, T, "mudur", x["id"], "pazarlama")
    plan = C.plan_full(engine, T, pid)
    card = {"metinler": [{"alan": "new_ozet", "metin": "Aynı  metin"}, {"alan": "new_BasnBlteni", "metin": "Eski bülten"}], "crmButce": {}}
    items = P.crm_todo(plan, card)
    assert [(i["tur"], i.get("alan")) for i in items] == [("kitap-alani", "new_BasnBlteni"), ("butce-satiri", None)]
    assert items[1]["tutar"] == 1234 and items[0]["planOnayli"] is False


def test_digest_buckets_and_text():
    rows = [
        {"stokKodu": "A", "ad": "A", "yayinTarihi": "2026-10-10", "kalanGun": 12, "plan": None},
        {"stokKodu": "B", "ad": "B", "yayinTarihi": "2026-11-10", "kalanGun": 45, "plan": None},
        {"stokKodu": "C", "ad": "C", "yayinTarihi": "2026-10-15", "kalanGun": 17,
         "plan": {"durum": "onayli", "durumAdi": "Onaylı", "eksikMateryal": ["foy"], "hedefDegisti": True}},
    ]
    dg = P.digest(rows, _st())
    assert [r["stokKodu"] for r in dg["yayinaKalan"]["14"]] == ["A"] and [r["stokKodu"] for r in dg["yayinaKalan"]["60"]] == ["B"]
    assert [r["stokKodu"] for r in dg["materyalEksik"]] == ["C"] and [r["stokKodu"] for r in dg["hedefDegisti"]] == ["C"]
    assert "Tanıtım föyü" in P.digest_text(dg, "")
    assert P.digest_text(P.digest([], _st()), "") is None


# ------------------------------------------------------------------ dışa aktarım


def test_exports_hide_amounts_without_budget_right_and_package_has_only_approved(engine):
    pid = _plan(engine)
    _lines(engine, pid, 4321)
    ok = C.add_material(engine, T, "ayse", pid, "foy", "Onaylı föy", "zeki")
    C.add_material(engine, T, "ayse", pid, "sosyal", "Taslak", "zeki")
    C.approve_material(engine, T, "editor", ok["id"], "editoryal")
    C.approve_material(engine, T, "mudur", ok["id"], "pazarlama")
    plan = C.plan_full(engine, T, pid)
    assert "4321" not in X.plan_csv(plan, False) and "4321,00" in X.plan_csv(plan, True)
    rows = list(csv.reader(io.StringIO(X.plan_csv(plan, True).lstrip("﻿")), delimiter=";"))
    assert rows[0][0] == "Plan"
    names = zipfile.ZipFile(io.BytesIO(X.package_zip(plan, False))).namelist()
    assert [n for n in names if n.endswith(".txt") and n[0].isdigit()] == ["01-foy.txt"]


# ------------------------------------------------------------------ yetki


def test_access_rules_for_marketing():
    page = frozenset({A.page("pazarlama-yeni-kitap")})
    assert A.rule_for("/api/v1/marketing/plans") == page | {A.page("pazarlama-backlist")}   # M17 planı aynı uçlarla
    assert A.rule_for("/api/v1/marketing/run-due") == A.SYSTEM
    assert A.rule_for("/api/v1/marketing/contract/plans") == page
    assert A.page("pazarlama-yeni-kitap") in A.rule_for("/api/v1/budget/targets")
    f = A.features_for
    w = "ozellik:pazarlama.plan-yaz"
    assert f("POST", "/api/v1/marketing/plans") == [w] and f("PATCH", "/api/v1/marketing/plans/MP-2026-0001") == [w]
    assert f("PUT", "/api/v1/marketing/plans/MP-2026-0001/lines") == [w] and f("POST", "/api/v1/marketing/plans/x/suggest") == [w]
    assert f("PUT", "/api/v1/marketing/materials/m1") == [w]
    assert f("POST", "/api/v1/marketing/plans/x/approve") == [] and f("POST", "/api/v1/marketing/materials/m1/approve") == []
    assert f("GET", "/api/v1/marketing/plans/x") == []
    assert f("GET", "/api/v1/marketing/plans/x/export.pdf") == ["ozellik:veri.disa-aktar"]
    ex = A.explicit_keys()
    assert {"ozellik:pazarlama.plan-onay", "ozellik:pazarlama.butce-ust-onay", "ozellik:pazarlama.materyal-editoryal-onay"} <= ex
    assert "ozellik:pazarlama.plan-yaz" not in ex and "sayfa:pazarlama-yeni-kitap" in A.all_keys()


# ------------------------------------------------------------------ uçlar (köprü, sayfa ve işlem kapısı)


def _app(monkeypatch, store, settings):
    from fastapi.testclient import TestClient

    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod
    from semantic_bridge.app import Runtime, create_app
    from semantic_layer.candidates.llm_client import FakeLlm

    users = {"timas_session=a": "ayse", "timas_session=z": "zekiai"}
    monkeypatch.setattr(board_mod, "_fetch_user", lambda cookie: users.get(cookie))
    monkeypatch.setattr(board_mod, "_fetch_session", lambda cookie: {"username": users.get(cookie), "displayName": "x"})
    monkeypatch.setattr(admin_mod, "admins", lambda: ["zekiai"])
    monkeypatch.delenv("SEMANTIC_CALLER_TOKEN", raising=False)
    monkeypatch.delenv("SEMANTIC_ADMIN_TOKEN", raising=False)
    A._ready.clear()
    A.invalidate()
    # Önceki testlerin motor kaydı bu motorun id'sine denk gelebilir: pazarlama ve bütçe şeması bu motorda kurulsun.
    C._ready.discard(id(store.engine))
    B._ready.discard(id(store.engine))
    app = create_app(Runtime(settings, store=store, llm=FakeLlm([""])))
    return app, TestClient(app)


def test_endpoints_two_eyes_and_explicit_approval(monkeypatch, store, settings):
    app, client = _app(monkeypatch, store, settings)
    pub = (date.today() + timedelta(days=50)).isoformat()
    detail = {**_book("N9", tarihler={"crm-kitap": pub, "crm-proje": None, "uretim-dagilim": None, "uretim-depo": None}),
              "turler": None, "yas": [None, None], "fiyat": None, "sayfa": None, "metinler": {}, "proje": {}}
    crm = app.state.marketing["crm"]
    fake = FakeCrm(books=[detail], detail=detail)
    for name in ("book", "rivals", "special_days", "spend", "new_books", "email_of"):
        monkeypatch.setattr(crm, name, getattr(fake, name))
    a, z = {"cookie": "timas_session=a"}, {"cookie": "timas_session=z"}

    made = client.post("/api/v1/marketing/plans", json={"stokKodu": "N9"}, headers=a)
    assert made.status_code == 201, made.text
    pid = made.json()["id"]
    assert client.post("/api/v1/marketing/plans", json={"stokKodu": "N9"}, headers=a).status_code == 409
    r = client.put(f"/api/v1/marketing/plans/{pid}/lines", json={"items": [{"kanal": "basin", "tutar": 500}]}, headers=a)
    assert r.status_code == 200 and r.json()["butceToplam"] == 500
    assert client.post(f"/api/v1/marketing/plans/{pid}/submit", headers=a).json()["durum"] == "onayda"
    denied = client.post(f"/api/v1/marketing/plans/{pid}/approve", json={}, headers=a)
    assert denied.status_code == 403                                   # açıkça verilen yetki yok
    ok = client.post(f"/api/v1/marketing/plans/{pid}/approve", json={"note": "uygun"}, headers=z)
    assert ok.status_code == 200 and ok.json()["durum"] == "onayli"
    me = client.get("/api/v1/marketing/meta", headers=a).json()["me"]
    assert me["canWrite"] and me["canSeeBudget"] and not me["canApprove"]
    rows = client.get("/api/v1/marketing/new-books", headers=a).json()
    assert rows["total"] == 1 and rows["items"][0]["plan"]["durum"] == "onayli"
    assert client.post("/api/v1/marketing/run-due", headers=a).status_code == 403   # kişi zamanlayıcıyı tetikleyemez
    assert client.get("/api/v1/marketing/contract/plans?stok=N9", headers=a).json()["total"] == 1


def test_tables_are_created_once(engine):
    names = set(sa.inspect(engine).get_table_names())
    assert {"semantic_mkt_plans", "semantic_mkt_plan_lines", "semantic_mkt_tasks", "semantic_mkt_materials",
            "semantic_mkt_book_cards", "semantic_mkt_events", "semantic_mkt_jobs", "semantic_mkt_meta"} <= names
