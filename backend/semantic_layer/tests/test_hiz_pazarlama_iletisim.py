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


# ------------------------------------------------------------------ M27 etkinlikler: tip eşlemesi ve takvim


TY1 = "11111111-0000-0000-0000-000000000001"
TY2 = "11111111-0000-0000-0000-000000000002"


class SayanBaglanti:
    """Etkinlik kaynağının bağlantısı gibi davranır: `execute(sql, max)` → (kolonlar, satırlar, kesildi)."""

    def __init__(self, fake: SayanCrm):
        self.fake = fake

    def execute(self, sql, _max):
        return [], self.fake(sql), False

    def close(self):
        pass


def _ev_fake():
    from semantic_bridge import events as E

    bugun = E.today().isoformat() + " 09:00:00"
    return SayanCrm({
        "COUNT(e.new_etkinlikId)": [{"id": TY1, "ad": "Fuar", "durum": 0, "adet": 12, "son": bugun},
                                    {"id": TY2, "ad": "Satış ziyareti", "durum": 0, "adet": 900, "son": bugun}],
        "new_BalangTarihi >=": [{"id": "e1000000-0000-0000-0000-000000000001", "ad": "İmza günü", "tip_id": TY1, "tip": "Fuar",
                                 "baslangic": bugun, "bitis": bugun, "yer": "Kadıköy", "il": "İstanbul", "durum": 1},
                                {"id": "e1000000-0000-0000-0000-000000000002", "ad": "Ziyaret", "tip_id": TY2, "tip": "Satış ziyareti",
                                 "baslangic": bugun, "bitis": bugun, "durum": 1}],
    })


@pytest.fixture
def ev_engine(tmp_path, monkeypatch):
    from semantic_bridge import events as E
    from semantic_layer.store.catalog_store import open_store

    monkeypatch.setenv("EVENTS_DIR", str(tmp_path / "events"))
    e = open_store("sqlite://").engine
    E._ready.discard(id(e))
    E.ensure(e)
    yield e
    E._ready.discard(id(e))


def _ev_client(engine, fake, yenile):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from semantic_bridge import events_api

    app = FastAPI()
    svc = events_api.register(app, {
        "auth": lambda r: (engine, "t1", "ayse", "Ayşe"), "can": lambda u, k: True, "is_admin": lambda u: False,
        "audit": lambda *a, **k: None, "conf": lambda k, d="": d, "fresh": lambda: yenile["x"],
        "crm_connect": lambda: SayanBaglanti(fake), "logo_connect": lambda: None, "llm": lambda p: None,
        "system": lambda: (engine, "t1"), "require_caller": lambda r: None})
    return TestClient(app), svc


def test_etkinlik_tip_eslemesi_eski_hesap_yeni_hesap_ve_yenile(ev_engine):
    from semantic_bridge import events as E
    from semantic_bridge import events_sources as S

    fake, yenile = _ev_fake(), {"x": False}
    c, svc = _ev_client(ev_engine, fake, yenile)
    r1 = c.get("/api/v1/events/type-map").json()
    eski = E.type_rows(S.Source(lambda: SayanBaglanti(_ev_fake()), lambda: None, lambda: "Timas_MSCRM.dbo").types(),
                       E.type_map(ev_engine, "t1"))
    assert r1["items"] == eski and r1["counts"] == {"total": 2, "decided": 0, "suggested": 0}
    assert fake.say("COUNT(e.new_etkinlikId)") == 1
    assert c.get("/api/v1/events/type-map").json()["items"] == eski and fake.say("COUNT(e.new_etkinlikId)") == 1
    yenile["x"] = True                                                   # «Verileri yenile»: ekran beklemez
    assert c.get("/api/v1/events/type-map").json()["items"] == eski
    assert fake.say("COUNT(e.new_etkinlikId)") == 1                      # 60 sn'den genç okuma yeniden başlatılmaz
    b = svc.source._bellek
    _eskit(b, ("types",), 120)
    t0 = time.monotonic()
    assert c.get("/api/v1/events/type-map").json()["items"] == eski
    assert time.monotonic() - t0 < 1.5
    assert _bekle(lambda: fake.say("COUNT(e.new_etkinlikId)") == 2)      # arkada okundu


def test_etkinlik_takvimi_bellekten(ev_engine):
    from semantic_bridge import events as E

    fake, yenile = _ev_fake(), {"x": False}
    c, svc = _ev_client(ev_engine, fake, yenile)
    y = E.today().year
    r1 = c.get(f"/api/v1/events/calendar?year={y}&unmapped=1").json()
    assert r1["unmappedTypes"] == 2 and sorted(r1["events"], key=lambda e: e["id"])[0]["ad"] == "İmza günü"
    assert fake.say("new_BalangTarihi >=") == 1
    anahtar = next(k for k in svc.source._bellek._k if k[0] == "events")
    _eskit(svc.source._bellek, anahtar, 700)
    r2 = c.get(f"/api/v1/events/calendar?year={y}&unmapped=1").json()
    assert r2["events"] == r1["events"] and r2["months"] == r1["months"]
    assert _bekle(lambda: fake.say("new_BalangTarihi >=") == 2)


# ------------------------------------------------------------------ M37 okur topluluğu: okur çekirdeği özeti


def _okur_engine(seed: int = 0, n: int = 0):
    """Okur veri tabanı: sabit örnek (n=0) ya da `seed` ile üretilmiş `n` okur ve rastgele izin kanıtları."""
    import json
    import random
    from datetime import datetime, timezone

    from semantic_bridge import readers as R
    from semantic_bridge import readers_segments as RS
    from semantic_layer.store.catalog_store import open_store

    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    e = open_store("sqlite://").engine
    R._ready.discard(id(e))
    R.ensure(e)
    RS.ensure_tables(e)
    with e.begin() as c:
        def reader(rid, sources, *, status="aktif", interests=(), minor=False, attrs=None):
            c.execute(R.READERS.insert().values(
                reader_id=rid, tenant_id="t1", status=status, is_minor=minor, first_seen=now, last_touch=now,
                interests_json=json.dumps([{"ad": i} for i in interests]), attrs_json=json.dumps(attrs or {}),
                sources_json=json.dumps(sources), event_count=0, updated_at=now))

        def consent(rid, ch, st, src, tenant="t1"):
            c.execute(R.CONSENTS.insert().values(tenant_id=tenant, reader_id=rid, channel=ch, status=st, source=src, at=now))

        if not n:
            reader("r1", {"crm_contact": 1}, interests=["Tarih"])
            reader("r2", {"crm_contact": 1, "crm_lead": 2}, interests=["Tarih", "Roman"], minor=True)
            reader("r3", {"upload": 1}, attrs={"uyari": ["ortak_iletisim"]})
            reader("r9", {"crm_contact": 1}, status="birlesti")
            for rid, ch, st, src in (("r1", "email", "izinli", "iys"), ("r1", "kvkk", "izinli", "crm"), ("r2", "email", "izinli", "iys"),
                                     ("r2", "email", "ret", "crm"), ("r2", "kvkk", "izinli", "crm"), ("r9", "email", "izinli", "iys"),
                                     ("r9", "email", "ret", "crm")):
                consent(rid, ch, st, src)
        else:
            rnd = random.Random(seed)
            for i in range(n):
                reader(f"r{i}", {rnd.choice(["crm_contact", "crm_lead", "upload"]): 1},
                       status=rnd.choice(["aktif", "aktif", "aktif", "birlesti", "pasif"]),
                       attrs={"uyari": ["ortak_iletisim"]} if rnd.random() < 0.1 else {})
                for _ in range(rnd.randint(0, 5)):
                    consent(f"r{i}", rnd.choice(["email", "sms", "call", "kvkk"]), rnd.choice(["izinli", "ret"]),
                            rnd.choice(["iys", "crm", "form"]))
                if rnd.random() < 0.05:
                    consent(f"r{i}", "email", "izinli", "iys", tenant="t2")          # başka kiracı sayılmaz
        R._stamp(c, "t1")
    return e


def _eski_izin(engine, tenant):
    """2026-09-29 öncesi `Provider.izin_sagligi`: bütün izin tablosu Python'da."""
    from collections import Counter, defaultdict

    import sqlalchemy as sa

    from semantic_bridge import readers as R
    from semantic_bridge import readers_core as RC

    profs = R.profiles(engine, tenant, R.settings())
    alive = {p["id"] for p in profs}
    seen = defaultdict(set)
    with engine.connect() as c:
        for r in c.execute(sa.select(R.CONSENTS.c.reader_id, R.CONSENTS.c.channel, R.CONSENTS.c.status)
                           .where(R.CONSENTS.c.tenant_id == tenant)):
            if r.reader_id in alive:
                seen[(r.reader_id, r.channel)].add(r.status)
    conflicts = Counter(ch for (_rid, ch), st in seen.items() if {"izinli", "ret"} <= st)
    out = [{"tur": f"celiski_{ch}", "ad": RC.CONFLICT_LABELS[ch], "sayi": int(conflicts.get(ch, 0)),
            "aciklama": "Ret kazanır; yanlış olan kaynak kaydı düzeltilmeli."} for ch in (*R.CHANNELS, "kvkk")]
    shared = sum(1 for p in profs if "ortak_iletisim" in (p["attrs"].get("uyari") or []))
    out.append({"tur": "ortak_iletisim", "ad": "Ortak iletişim bilgisi (ebeveyn–çocuk olabilir)", "sayi": shared,
                "aciklama": "Aynı e-posta/telefonu taşıyan kayıtların doğum yılları 12+ yıl ayrışıyor."})
    return out


@pytest.mark.parametrize("seed,n", [(0, 0), (1, 300), (2, 800)])
def test_okur_izin_celiskisi_sql_eski_hesapla_ayni(seed, n, monkeypatch):
    from semantic_bridge import readers_core as RC

    for k in ("READERS_REQUIRE_KVKK", "READERS_CONSENT_SOURCES"):
        monkeypatch.delenv(k, raising=False)
    e = _okur_engine(seed, n)
    p = RC.Provider(lambda: e, lambda: "t1")
    assert p.izin_sagligi("t1") == _eski_izin(e, "t1")
    if not n:
        assert {x["tur"]: x["sayi"] for x in p.izin_sagligi("t1")}["celiski_email"] == 1     # birleşmiş r9 sayılmaz


def test_okur_ozeti_damga_degismedikce_bellekten(monkeypatch):
    from semantic_bridge import readers as R
    from semantic_bridge import readers_core as RC

    e = _okur_engine()
    p = RC.Provider(lambda: e, lambda: "t1")
    n = {"envanter": 0, "izin": 0}
    env0, izin0 = RC.Provider._envanter, RC.Provider._izin

    def say(ad, f):
        def w(*a):
            n[ad] += 1
            return f(*a)
        return staticmethod(w)

    monkeypatch.setattr(RC.Provider, "_envanter", say("envanter", env0))
    monkeypatch.setattr(RC.Provider, "_izin", say("izin", izin0))
    inv1, iz1 = p.okur_envanteri("t1"), p.izin_sagligi("t1")
    assert inv1["toplam"] == 3 and {r["kayitTipi"]: r["iysOnayli"] for r in inv1["satirlar"]}["crm_contact"] == 2
    assert p.okur_envanteri("t1") == inv1 and p.izin_sagligi("t1") == iz1 and n == {"envanter": 1, "izin": 1}
    with e.begin() as c:                                      # okur verisi değişti (tur/birleştirme damgası)
        c.execute(R.CONSENTS.insert().values(tenant_id="t1", reader_id="r1", channel="email", status="ret", source="crm"))
        R._stamp(c, "t1")
    time.sleep(0.002)
    iz2 = {x["tur"]: x["sayi"] for x in p.izin_sagligi("t1")}
    assert n["izin"] == 2 and iz2["celiski_email"] == 2       # eski damganın rakamı gösterilmez

