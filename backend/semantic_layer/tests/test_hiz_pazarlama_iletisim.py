"""Hız (2026-09-29): basın ilişkileri, kurumsal ilişkiler, etkinlikler, okur topluluğu, reklam, katalog ve bülten uçları
kaynağı (CRM / okur çekirdeği) beklemez.

Her modül için: (1) eski hesap = yeni hesap (bellekteki değer aynı işlevin aynı SQL ile döndürdüğü değer), (2) taze
bellekte kaynak ikinci kez okunmaz, (3) süre dolunca eldeki değer hemen döner ve kaynak arkada okunur, (4) ekranın kendi
«Yenile»si kaynağı bekler, «Verileri yenile» (X-Data-Refresh) beklemez. Veriler yapaydır.
"""
from __future__ import annotations

import time

import pytest

from semantic_bridge import hizli_kaynak as HK


def _bekle(sart, sure=3.0):
    son = time.time() + sure
    while time.time() < son:
        if sart():
            return True
        time.sleep(0.01)
    return False


def _sakin(b, anahtar):
    """Arkadaki okuma bitti ve değer yazıldı."""
    return _bekle(lambda: not b._k[anahtar].is_ and (b.yas(anahtar) or 99) < 5)


def _eskit(b, anahtar, sn):
    """Bellekteki kaydı `sn` saniye eskitir (süre dolmuş gibi)."""
    k = b._k[anahtar]
    k.an -= sn


class SayanCrm:
    """SQL başına sabit satır döndüren sahte CRM; her okumayı sayar. `hepsi`: ilk eşleşen anahtar sözcüğün satırları."""

    def __init__(self, cevap: dict[str, list[dict]]):
        self.cevap = cevap
        self.sql: list[str] = []

    def __call__(self, sql: str) -> list[dict]:
        self.sql.append(sql)
        for k, v in self.cevap.items():
            if k in sql:
                return [dict(r) for r in v]
        return []

    def say(self, parca: str) -> int:
        return sum(1 for s in self.sql if parca in s)


# ------------------------------------------------------------------ ortak yardımcı


def test_oku_taze_bayat_zorla_durt():
    b = HK.bellek("test-hk", 600)
    n = {"x": 0}

    def hesap():
        n["x"] += 1
        return [n["x"]]

    assert HK.oku(b, "a", hesap) == [1]
    assert HK.oku(b, "a", hesap) == [1] and n["x"] == 1                    # taze: kaynak okunmaz
    assert HK.oku(b, "a", hesap, durt=True) == [1] and n["x"] == 1         # «Verileri yenile», 60 sn'den genç: okunmaz
    _eskit(b, "a", 120)
    assert HK.oku(b, "a", hesap, durt=True) == [1]                          # eldeki hemen
    assert _bekle(lambda: n["x"] == 2) and _sakin(b, "a")                   # arkada okundu
    _eskit(b, "a", 700)
    assert HK.oku(b, "a", hesap) == [2]                                     # süre doldu: eldeki hemen
    assert _bekle(lambda: n["x"] == 3) and _sakin(b, "a")
    assert HK.oku(b, "a", hesap, zorla=True) == [4]                         # ekranın «Yenile»si: beklenir
    assert HK.oku(b, "yok", hesap, durt=True) == [5]                        # eldeki yoksa beklenir


def test_bayat_penceresi_gecince_beklenir(monkeypatch):
    monkeypatch.setenv("HIZLI_KAYNAK_BAYAT_SEC", "1000")
    b = HK.bellek("test-hk-bayat", 10)
    n = {"x": 0}

    def hesap():
        n["x"] += 1
        return n["x"]

    assert HK.oku(b, "a", hesap) == 1
    _eskit(b, "a", 2000)
    assert HK.oku(b, "a", hesap) == 2                                       # çok eski değer gösterilmez


def test_acilista_testte_kapali_zorla_calisir():
    assert HK.acilista("test", lambda: None) is None                        # pytest süreci: kaynak okunmaz
    olan = []
    t = HK.acilista("test", lambda: olan.append(1), 0, zorla=True)
    t.join(2)
    assert olan == [1]
    t = HK.acilista("test-hata", lambda: 1 / 0, 0, zorla=True)              # hata ekranı etkilemez
    t.join(2)


# ------------------------------------------------------------------ M20 basın ilişkileri: medya kişileri


G1 = "11111111-2222-3333-4444-555555555555"
G2 = "66666666-7777-8888-9999-000000000000"
H1 = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _pr_crm():
    from semantic_bridge import pr_sources as S

    fake = SayanCrm({
        "CRM medya kişileri": [
            {"id": G1, "ad": "Mehmet Muhabir", "eposta": "m@gazete.com", "telefon": None, "unvan": "Editör", "mecra": "Gazete A",
             "kurum": None, "eposta_yok": 0, "toplu_yok": 0, "iys": None},
            {"id": G2, "ad": "Zeynep Yazar", "eposta": "z@dergi.com", "telefon": "555", "unvan": None, "mecra": None,
             "kurum": "Dergi B", "eposta_yok": 1, "toplu_yok": 0, "iys": 1}],
        "haber ↔ kitap": [{"haber_id": H1, "kitap_id": G2, "stok_kodu": "15201.0001", "ad": "Deniz", "yazar": "Ayşe",
                           "kitaplik": "Roman", "hedef_kitle": "Yetişkin", "turler": "Roman"}],
        "Haber modülü arşivi": [{"id": H1, "baslik": "Söyleşi", "link": "https://x", "tarih": "2025-05-01", "yayinlandi": 1,
                                 "mecra1": "Gazete A", "muhabir_id": G1, "muhabir": "Mehmet Muhabir", "gorusulen_id": None}],
    })
    return S.Crm(lambda: "Timas_MSCRM.dbo", lambda: [], runner=lambda: fake), fake, S


def test_pr_kisiler_eski_hesap_yeni_hesap():
    crm, fake, S = _pr_crm()
    got = S.with_archive_counts(crm.media_contacts(), crm.archive())
    # eski hesap: SQL satırlarından doğrudan (bellek yokken ne dönüyorsa)
    heads = fake(S.archive_sql("Timas_MSCRM.dbo"))
    links = fake(S.archive_books_sql("Timas_MSCRM.dbo"))
    rows = [S.contact_row(r) for r in fake(S.media_contacts_sql("Timas_MSCRM.dbo", []))]
    assert got == S.with_archive_counts(rows, S.archive_rows(heads, links))
    assert [c["haberSayisi"] for c in got] == [1, 0]


def test_pr_kisiler_bellekten_ve_arkada_yenilenir():
    crm, fake, _S = _pr_crm()
    ilk = crm.media_contacts()
    crm.archive()
    assert fake.say("CRM medya kişileri") == 1 and fake.say("Haber modülü arşivi") == 1
    assert crm.media_contacts() == ilk and fake.say("CRM medya kişileri") == 1          # 10 dk içinde CRM okunmaz
    anahtar = next(k for k in crm._bellek._k if k[0] == "contacts")
    _eskit(crm._bellek, anahtar, 700)
    t0 = time.monotonic()
    assert crm.media_contacts() == ilk                                                  # süre doldu: eldeki hemen
    assert time.monotonic() - t0 < 0.5
    assert _bekle(lambda: fake.say("CRM medya kişileri") == 2)                          # CRM arkada okundu
    assert _sakin(crm._bellek, anahtar)
    crm.media_contacts(fresh=True)                                                      # ekranın «Yenile»si beklenir
    assert fake.say("CRM medya kişileri") == 3


def test_pr_arka_okuma_hatasi_eski_listeyi_birakir():
    from semantic_bridge import pr_sources as S

    calls = {"n": 0}

    def run(sql):
        calls["n"] += 1
        if calls["n"] > 1:
            raise S.SourceError("CRM düştü")
        return [{"id": G1, "ad": "Mehmet", "eposta": None, "telefon": None, "unvan": None, "mecra": "A", "kurum": None,
                 "eposta_yok": 0, "toplu_yok": 0, "iys": None}]

    crm = S.Crm(lambda: "Timas_MSCRM.dbo", lambda: [], runner=lambda: run)
    ilk = crm.media_contacts()
    _eskit(crm._bellek, next(iter(crm._bellek._k)), 700)
    assert crm.media_contacts() == ilk
    assert _bekle(lambda: calls["n"] == 2) and _bekle(lambda: not crm._bellek._k[next(iter(crm._bellek._k))].is_)
    assert crm.media_contacts() == ilk
    with pytest.raises(S.SourceError):
        crm.media_contacts(fresh=True)


# ------------------------------------------------------------------ M28 kurumsal ilişkiler: kişi rolleri ve rapor


@pytest.fixture
def portal():
    from semantic_layer.store.catalog_store import open_store

    return open_store("sqlite://").engine


def _pa_client(portal, monkeypatch, fake):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from semantic_bridge import public_affairs_api as PAA

    monkeypatch.setattr(PAA.src, "runner", lambda path: fake)
    app = FastAPI()
    PAA.register(app, {
        "auth": lambda r: (portal, "t1", "ayse", "Ayşe"), "require_caller": lambda r: None, "can": lambda u, k: True,
        "is_admin": lambda u: False, "audit": lambda *a, **k: None, "conf": lambda k, d="": d,
        "engine": lambda: portal, "tenant": lambda: "t1", "crm_file": lambda: "/yok", "llm": lambda p: None})
    return TestClient(app)


def _pa_fake():
    return SayanCrm({
        "new_kisiroluBase": [{"id": "0A1B2C3D-1111-2222-3333-444455556666", "ad": "Kanaat önderi", "kisi": 7},
                             {"id": "1A1B2C3D-1111-2222-3333-444455556666", "ad": "Yazar", "kisi": 0}],
        "AccountRoleCode = 1": [{"n": 42}],
        "new_siparissatiriBase": [{"tip": 12, "siparis": 3, "adet": 150}],
    })


def test_iliskiler_roller_eski_hesap_yeni_hesap_ve_bellek(portal, monkeypatch):
    from semantic_bridge import public_affairs_sources as src

    fake = _pa_fake()
    c = _pa_client(portal, monkeypatch, fake)
    r1 = c.get("/api/v1/public-affairs/crm/roles").json()
    # eski hesap: aynı SQL satırlarından ucun eski gövdesiyle
    roles = [{"id": src.lid(r.get("id")), "name": src.s(r.get("ad")), "people": src.ival(r.get("kisi")) or 0}
             for r in src.lower_rows(fake(src.person_roles_sql("Timas_MSCRM.dbo")))]
    n = src.lower_rows(fake(src.decision_makers_sql("Timas_MSCRM.dbo")))
    assert {k: r1[k] for k in ("personRoles", "decisionMakers")} == {"personRoles": roles, "decisionMakers": src.ival(n[0].get("n"))}
    assert r1["decisionMakers"] == 42 and not r1["kaynaklar"].get("error")
    r2 = c.get("/api/v1/public-affairs/crm/roles").json()
    assert r2 == r1 and fake.say("new_kisiroluBase") == 2                         # 1 uç + 1 eski hesap; ikinci istek okumaz


def test_iliskiler_rapor_crm_toplamlari_bellekten(portal, monkeypatch):
    from semantic_bridge import hizli_bellek as HB

    fake = _pa_fake()
    c = _pa_client(portal, monkeypatch, fake)
    r1 = c.get("/api/v1/public-affairs/report?year=2026").json()
    assert [(t["type"], t["orders"], t["books"]) for t in r1["crm"]["types"]] == [(12, 3, 150)]
    assert r1["crm"]["error"] is None and fake.say("new_siparissatiriBase") == 1
    b = HB.KAYIT["iliskiler.crm"]
    anahtar = next(k for k in b._k if str(k).startswith("promo:2026"))
    _eskit(b, anahtar, 700)
    t0 = time.monotonic()
    r2 = c.get("/api/v1/public-affairs/report?year=2026").json()
    assert r2["crm"] == r1["crm"] and time.monotonic() - t0 < 1.5                 # süre doldu: eldeki hemen
    assert _bekle(lambda: fake.say("new_siparissatiriBase") == 2)                 # CRM arkada okundu
