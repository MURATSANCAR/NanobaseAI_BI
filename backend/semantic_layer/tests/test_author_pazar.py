"""Yazar kartında «Pazarda bu yazar» (author_pazar) ve Zeki AI'ın dağıtımcı kataloğu alanı (chat_portal
«dagitimci-katalog»).

Sınanan: ad katlama ve çoklu yazar ayrıştırma («Kolektif» hariç, unvan ve harf farkı atılır), barkodla ve stok koduyla
doğrulanan kitaplar, Başarı'nın doğrulanan kitapta kullandığı yazımla eşleşme, yalnız son görüntüdeki başlıklar,
TİMAŞ / başka yayınevi kırılımı, en yüksek baskı, fiyat aralığı, D&R'de de olanlar, belirsizlik nedenleri (tek sözcük,
barkodla doğrulanamama, alan farkı, TİMAŞ'ta bağlanmamış aynı ad), çıkış endeksinin iki görüntüden önce boş kalması,
sorgu bilgisinin her rakamı kapsaması; sohbet alanında kolon adı/notu, yazarın kişisel veri sayılıp seçenek olmaması,
kaynak başına son görüntü (bir katalog o gün okunmadıysa onun son görüntüsü) ve cevaba eklenen alan notu ile gün.

Veriler yapaydır (sqlite) ve yalnız kuralları sınar; gerçek katalogla kabul test sunucusunda.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
import sqlalchemy as sa

from semantic_bridge import author_pazar as AP
from semantic_bridge import chat_portal as P
from semantic_bridge import chat_scope
from semantic_bridge import pazar_dagitim as D
from semantic_bridge import provenance as PV
from semantic_layer.runtime.llm_choose import Choice
from semantic_layer.store.catalog_store import open_store

T = "t1"
D0, D1 = date(2026, 9, 24), date(2026, 9, 25)
OLD = date(2026, 9, 10)
TABLE = "semantic_pazar_dagitim_titles"


@pytest.fixture
def engine(monkeypatch):
    monkeypatch.setenv("PAZAR_DAGITIM_ARALIK_GUN", "35")
    for k in ("CHAT_PORTAL_REQUIRE_CERTIFIED", "CHAT_PORTAL_MIN_PROB", "CHAT_PORTAL_MIN_MARGIN"):
        monkeypatch.delenv(k, raising=False)
    e = open_store("sqlite://").engine
    D._ready.discard(id(e))
    D.ensure(e)
    AP._INDEX.clear()
    P._ready.discard(id(e))
    P._cache.clear()
    return e


def _t(barkod, yazar, *, kaynak="basari", yayinevi="Rakip Yayınları", timas=False, durum="Satışta", baski=1,
       fiyat=100.0, ust="Çocuk Kitapları", son=D1, stok=10, iskonto=35.0):
    return {"tenant_id": T, "kaynak": kaynak, "barkod": barkod, "ad": f"Kitap {barkod[-3:]}", "yazar": yazar,
            "cevirmen": None, "yayinevi": yayinevi, "kategori": f"{ust}>Alt", "ust_kategori": ust, "sayfa": 120,
            "basim_yili": 2024, "stok": stok, "site_stok": None, "fiyat": fiyat, "iskonto": iskonto, "dr_fiyat": None,
            "durum": durum, "baski_no": baski, "timas": timas, "stok_kodu": None, "ilk_gorulme": OLD,
            "son_gorulme": son, "guncellendi_at": datetime(2026, 9, 25, tzinfo=timezone.utc)}


def _snap(e, kaynak, tarih):
    with e.begin() as c:
        c.execute(D.SNAPS.insert().values(tenant_id=T, kaynak=kaynak, tarih=tarih, kaynak_zamani=f"{tarih} 11:04",
                                          yontem="gece", satir=1, degisen=0, yeni=0, kaybolan=0,
                                          okundu_at=datetime(2026, 9, 25, tzinfo=timezone.utc)))


def _seed(e, extra=()):
    rows = [
        _t("9786050000011", "Mustafa Ulusoy", yayinevi="Timaş Çocuk", timas=True, baski=12, fiyat=150.0),
        _t("9786050000028", "Mustafa Ulusoy, Ayşe Kaya", yayinevi="Timaş Çocuk", timas=True, durum="Baskısı Yok",
           baski=3, fiyat=90.0),
        _t("9786050000035", "Mustafa Ulusoy", baski=5, fiyat=200.0),
        _t("9786050000042", "Kolektif"),
        _t("9786050000059", "Mustafa Ulusoy", son=OLD),                      # katalogdan düşmüş
        _t("9786050000066", "Prof. Dr. MUSTAFA  ULUSOY", yayinevi="Diğer Yayınevi", durum="Temin Edilemiyor",
           baski=None, fiyat=120.0),
        _t("9786050000035", None, kaynak="dr", yayinevi="Rakip Yayınları", durum="Site: Satışa açık · Prefix: Satışa açık",
           son=D1, iskonto=None),
        *extra,
    ]
    with e.begin() as c:
        c.execute(D.TITLES.insert(), rows)
        c.execute(D.BARKOD.insert(), [{"tenant_id": T, "barkod": "9786050000028", "stok_kodu": "TMS001"}])
    _snap(e, "basari", D1)
    _snap(e, "dr", D1)


BOOKS = [{"new_ean13": "978-605-0000011", "new_StokKodu": None}, {"new_ean13": None, "new_StokKodu": "TMS001"}]


# ------------------------------------------------------------------ ad katlama


def test_name_key_and_split():
    assert AP.name_key("Prof. Dr. İlber ORTAYLI") == "ilber ortayli"
    assert AP.name_key("Émile Zola (Derleyen)") == "emile zola"
    assert AP.split_authors("Ahmet Ümit, Mehmet Yılmaz; Ayşe Kaya") == ["ahmet umit", "mehmet yilmaz", "ayse kaya"]
    assert AP.split_authors("Kolektif") == [] and AP.split_authors("KOMİSYON") == []
    assert AP.split_authors("Ali Can & Kolektif") == ["ali can"]
    assert AP.split_authors(None) == []


# ------------------------------------------------------------------ yazar kartı


def test_market_splits_verified_and_name_matches(engine):
    _seed(engine)
    out = AP.market(engine, T, "Mustafa Ulusoy", books=BOOKS)
    got = {b["barkod"]: b for b in out["kitaplar"]}
    assert set(got) == {"9786050000011", "9786050000028", "9786050000035", "9786050000066"}   # kolektif ve düşen yok
    assert got["9786050000011"]["dogrulandi"] and got["9786050000028"]["dogrulandi"]            # barkod / stok kodu
    assert not got["9786050000035"]["dogrulandi"] and got["9786050000035"]["drde"]
    assert out["dogrulanan"] == 2 and out["drdeOlan"] == 1
    assert out["timas"] == {"kitap": 2, "satista": 1, "baskisiYok": 1, "diger": 0, "dogrulanan": 2}
    assert out["diger"] == {"kitap": 2, "satista": 1, "baskisiYok": 1, "diger": 0, "dogrulanan": 0}
    assert out["enYuksekBaski"]["baski"] == 12
    assert (out["fiyat"]["enDusuk"], out["fiyat"]["enYuksek"], out["fiyat"]["orta"]) == (90.0, 200.0, 135.0)
    assert [p["yayinevi"] for p in out["yayinevleri"]][0] == "Timaş Çocuk"
    assert not out["belirsiz"] and out["nedenler"] == []
    assert out["tarih"] == "2026-09-25" and out["kaynakZamani"] == "2026-09-25 11:04"
    assert out["cikis"] is None and "en az iki" in out["cikisNot"]
    assert "pazar payı" not in (out["not"] + out["cikisNot"]).lower()
    assert [b["timas"] for b in out["kitaplar"]][:2] == [True, True]                          # TİMAŞ önce


def test_catalog_spelling_of_verified_book_is_used(engine):
    """CRM'deki ad ile Başarı'nın yazımı farklıysa, doğrulanan kitaptaki yazım da aranır."""
    _seed(engine, extra=[_t("9786050000073", "Mustafa A. Ulusoy", yayinevi="Başka Yayınevi")])
    with engine.begin() as c:
        c.execute(D.TITLES.update().where(D.TITLES.c.barkod == "9786050000011").values(yazar="Mustafa A. Ulusoy"))
    AP._INDEX.clear()
    out = AP.market(engine, T, "Mustafa Ulusoy", books=BOOKS)
    assert "9786050000073" in {b["barkod"] for b in out["kitaplar"]}
    assert "Mustafa A. Ulusoy" in out["adlar"]


@pytest.mark.parametrize("books, needle", [(None, "kitap listesi okunamadı"), ([], "barkodla bulunamadı")])
def test_single_word_name_without_verification_is_ambiguous(engine, books, needle):
    _seed(engine, extra=[_t("9786050000080", "Mevlana", yayinevi="Başka Yayınevi")])
    out = AP.market(engine, T, "Mevlânâ", books=books)
    assert [b["barkod"] for b in out["kitaplar"]] == ["9786050000080"]
    assert out["belirsiz"] and any("tek sözcük" in n for n in out["nedenler"])
    assert any(needle in n for n in out["nedenler"])


def test_disjoint_categories_and_unlinked_timas_title_are_flagged(engine):
    _seed(engine, extra=[_t("9786050000097", "Mustafa Ulusoy", ust="Tarih", yayinevi="Başka Yayınevi"),
                         _t("9786050000103", "Mustafa Ulusoy", yayinevi="Timaş Yayınları", timas=True)])
    with engine.begin() as c:   # başka yayınevlerinde yalnız Tarih kalsın
        c.execute(D.TITLES.update().where(D.TITLES.c.barkod.in_(["9786050000035", "9786050000066"]))
                  .values(ust_kategori="Tarih"))
    out = AP.market(engine, T, "Mustafa Ulusoy", books=BOOKS)
    assert out["belirsiz"]
    assert any("örtüşmüyor" in n and "Tarih" in n for n in out["nedenler"])
    assert any("CRM'de bu yazara bağlı değil" in n for n in out["nedenler"])


def test_not_read_yet(engine):
    out = AP.market(engine, T, "Mustafa Ulusoy", books=BOOKS)
    assert out["okundu"] is False and out["kitaplar"] == [] and out["tarih"] is None


def test_outflow_after_two_snapshots(engine):
    _seed(engine)
    _snap(engine, "basari", D0)
    with engine.begin() as c:
        c.execute(D.OBS.insert(), [
            {"tenant_id": T, "kaynak": "basari", "barkod": "9786050000011", "tarih": D1, "stok": 3, "onceki_stok": 10,
             "cikis": 7, "giris": 0, "ilk": False},
            {"tenant_id": T, "kaynak": "basari", "barkod": "9786050000035", "tarih": D1, "stok": 7, "onceki_stok": 10,
             "cikis": 3, "giris": 0, "ilk": False}])
    out = AP.market(engine, T, "Mustafa Ulusoy", books=BOOKS)
    assert out["cikis"] == {"bas": "2026-09-24", "son": "2026-09-25", "timas": 7, "diger": 3}
    assert {b["barkod"]: b["cikis"] for b in out["kitaplar"]}["9786050000011"] == 7


def test_index_rebuilds_after_new_snapshot(engine):
    _seed(engine)
    assert "yeni yazar" not in AP.author_index(engine, T)[1]
    with engine.begin() as c:
        c.execute(D.TITLES.insert(), [_t("9786050000110", "Yeni Yazar", son=date(2026, 9, 26))])
        c.execute(D.TITLES.update().where(D.TITLES.c.son_gorulme == D1, D.TITLES.c.kaynak == "basari")
                  .values(son_gorulme=date(2026, 9, 26)))
    _snap(engine, "basari", date(2026, 9, 26))
    assert "yeni yazar" in AP.author_index(engine, T)[1]


def test_every_number_has_a_source(engine):
    _seed(engine)
    out = AP.market(engine, T, "Mustafa Ulusoy", books=BOOKS)
    stmts = out.pop("_sorgular")
    payload = PV.bagla(out, lambda: AP.kaynaklar(engine, T, out, stmts))
    assert not payload["kaynaklar"].get("error")
    assert PV.problems(payload) == []
    assert PV.uncovered_numbers(payload) == []


# ------------------------------------------------------------------ Zeki AI: dağıtımcı kataloğu alanı


class Picker:
    def __init__(self, **wanted):
        self.wanted = {"tablo": None, "olcu": P.COUNT, "tarih": None, "kirilim": P.NONE_BREAKDOWN, "kosul": P.NO_MORE}
        self.wanted.update(wanted)
        self.calls: list[list[str]] = []

    def choose(self, prompt, labels, system=None):
        self.calls.append(list(labels))
        step = ("tablo" if "hangi kayıtlardan" in prompt else "olcu" if "hangi sayıyı" in prompt else
                "tarih" if "hangi tarihe" in prompt else "kirilim" if "kırılmalı" in prompt else "kosul")
        want = self.wanted[step]
        pick = next((x for x in labels if x == want), None) or next((x for x in labels if want and want in x), labels[0])
        rest = 0.1 / max(1, len(labels) - 1)
        return Choice(pick, labels.index(pick), {x: (0.9 if x == pick else rest) for x in labels}, "logprobs", 0.9 - rest)


LABEL = "dağıtımcı ve perakende kataloğundaki kitap"


def _chat_seed(e):
    _seed(e)
    with e.begin() as c:   # D&R o gün okunmadı: son görüntüsü 24 Eylül
        c.execute(D.TITLES.insert(), [_t("9786050000127", None, kaynak="dr", son=D0, iskonto=None,
                                         durum="Site: silinmiş · Prefix: Satışa açık")])
        c.execute(D.SNAPS.delete().where(D.SNAPS.c.kaynak == "dr"))
        c.execute(D.TITLES.update().where(D.TITLES.c.kaynak == "dr").values(son_gorulme=D0))
    _snap(e, "dr", D0)
    profiles = P.profile(e, T, only=["dagitimci-katalog"])
    P.save_candidates(e, T, profiles)
    P.certify(e, T, ["dagitimci-katalog"], "operator:test")
    return {p["table"]: p for p in profiles}


def test_topic_and_area_are_registered():
    t = chat_scope.topic("dagitimci")
    assert t and t["portal"] == ["dagitimci-katalog"] and not t["data"] and P.serves(t)
    a = P.area_of_table(TABLE)
    assert a and a["id"] == "dagitimci-katalog"
    for bad in ("semantic_pazar_dagitim_meta", "semantic_pazar_dagitim_obs", "semantic_pazar_dagitim_barkod"):
        assert P.area_of_table(bad) is None
    assert P.mentions_portal("Başarı Dağıtım kataloğunda kaç kitap var?")
    assert P.mentions_portal("D&R'de satışa açık Timaş kitabı kaç tane?")


def test_profile_labels_notes_and_personal_columns(engine):
    p = _chat_seed(engine)[TABLE]
    cols = p["columns"]
    assert cols["yazar"]["kind"] == P.EXCLUDED and cols["cevirmen"]["kind"] == P.EXCLUDED
    assert cols["stok"]["label"].startswith("dağıtımcı stoğu") and "Prefix B2B" in cols["stok"]["note"]
    assert "999" in cols["site_stok"]["note"] and "iskonto" in cols["iskonto"]["note"]
    assert "%80" in cols["timas"]["note"] and cols["timas"]["kind"] == P.DIMENSION
    assert cols["kaynak"]["kind"] == P.DIMENSION and set(cols["kaynak"]["values"]) == {"basari", "dr"}
    assert cols["durum"]["kind"] == P.DIMENSION
    assert p["snapshot"] == "son_gorulme" and p["snapshot_per"] == "kaynak"


def test_counts_each_catalogues_latest_snapshot(engine):
    _chat_seed(engine)
    picker = Picker(tablo=LABEL)
    out = P.answer(engine, T, "Dağıtımcı kataloglarında kaç kitap var?", chat_scope.topic("dagitimci"), user=None,
                   llm=picker, today=date(2026, 9, 29), access=None)
    # Başarı 25 Eylül: 5 başlık (düşen hariç); D&R 24 Eylül: 2 başlık — bütün tablonun en büyük günü değil.
    assert out["type"] == "TEXT_TO_SQL" and out["records"] == [{P.COUNT: 7}]
    assert "basari 2026-09-25, dr 2026-09-24" in out["text"]
    assert "okura satışı" in out["text"] and "pazar payı" not in out["text"].lower()
    for opt in (o for labels in picker.calls for o in labels):
        assert "yazar" not in opt.lower() and "çevirmen" not in opt.lower()


def test_status_from_question_and_column_note(engine):
    _chat_seed(engine)
    out = P.answer(engine, T, "Başarı'da baskısı yok görünen kitap sayısı?", chat_scope.topic("dagitimci"), user=None,
                   llm=Picker(tablo=LABEL), today=date(2026, 9, 29), access=None)
    assert out["records"] == [{P.COUNT: 1}]                       # 9786050000028 (katalog: basari, durum sorudan)
    assert "katalog durumu: Başarı: stok durumu" in out["text"]


def test_page_permission(engine):
    from semantic_bridge import access as A

    _chat_seed(engine)
    nobody = A.Access(user="ali", admin=False, all=False, perms=frozenset({"sayfa:genel-bakis"}))
    out = P.answer(engine, T, "Kaç kitap var?", chat_scope.topic("dagitimci"), user=None, llm=Picker(tablo=LABEL),
                   today=date(2026, 9, 29), access=nobody)
    assert out["type"] == "NOT_PERMITTED"
    stok = A.Access(user="ali", admin=False, all=False, perms=frozenset({"sayfa:stok"}))
    out = P.answer(engine, T, "Kaç kitap var?", chat_scope.topic("dagitimci"), user=None, llm=Picker(tablo=LABEL),
                   today=date(2026, 9, 29), access=stok)
    assert out["type"] == "TEXT_TO_SQL"


def test_sum_uses_latest_snapshot_per_catalogue(engine):
    """Toplam da kaynak başına son görüntüyle: düşen başlığın stoğu eklenmez."""
    by = _chat_seed(engine)
    base = by[TABLE]
    plan = P.Plan(table=TABLE, area="dagitimci-katalog", measure=("sum", "stok"), measure_label="stok toplamı")
    stmt, _ = P.compile_plan(plan, by, T, None, P.area("dagitimci-katalog"))
    assert P.execute(engine, stmt, 5000) == [{"c0": 70}]            # 7 güncel başlık × 10
    assert plan.latest == "son_gorulme" and base["snapshot_per"] == "kaynak"
    assert sa.inspect(engine).has_table(TABLE)
