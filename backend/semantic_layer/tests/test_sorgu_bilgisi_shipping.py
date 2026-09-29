"""Sorgu bilgisi · M44 Lojistik ve kargo: her ucun cevabındaki her rakam bir kaynağa bağlı, SQL çalışmış metin.

CRM ve Logo sahte çalıştırıcıyla okunur ama SQL'ler gerçek dosyalardan gerçek doldurmayla kurulur (`sql()` +
`recording`); önbellekten dönen okumada da kaynak görünür. Denetlenen: kaynaksız rakam yok, kayıt tutarlı, yer tutucu yok,
kargo firması kimlik kolonu hiçbir gösterilen sorguda yok, kişisel kolon okuyan sorgu listelenmez.
Gerçek CRM/Logo kabulü: `scripts/acceptance/sorgu-bilgisi/g3_shipping.py`.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import pytest

from semantic_bridge import provenance as P
from semantic_bridge import shipping as S
from semantic_bridge import shipping_kaynak as K
from semantic_bridge import shipping_sources as src
from semantic_layer.store.catalog_store import open_store
from semantic_layer.tests.test_shipping import cargo

TN = "t1"
FIRM = "0a000000-0000-0000-0000-000000000001"
ORDER = "0f000000-0000-0000-0000-000000000001"
COST = "ozellik:kargo.maliyet"


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    S._ready.discard(id(e))
    S.ensure(e)
    return e


def _order(**over):
    today = S.today()
    r = {"siparis_id": ORDER, "siparis_no": "SP-1", "siparis_tarihi": datetime.combine(today - timedelta(days=5), datetime.min.time()),
         "durum": 100000000, "tip": 3, "depoda_bekliyor": None, "pusula": None,
         "kutulandi": datetime.combine(today - timedelta(days=4), datetime.min.time()),
         "sevk_tarihi": datetime.combine(today - timedelta(days=3), datetime.min.time()), "tamamlandi": None,
         "firma_id": FIRM, "takip_no": "T1", "takip_url": None, "etiket": 1, "kutu": "2", "odeme_sekli": 1,
         "aras_sonuc": "Hata", "aras_mesaj": "Adres eksik", "musteri": "Müşteri", "cari_kodu": "120.1", "il": "İstanbul"}
    r.update(over)
    return r


class FakeRun:
    """Sahte bağlantı: `sql()` ile kurulan metnin dosya adına göre satır döndürür."""

    def __call__(self, text: str) -> list[dict]:
        if "L_CAPIPERIOD" in text:
            y = S.today().year
            return [{"FIRMNR": 411, "BEGDATE": date(y - 1, 1, 1), "ENDDATE": date(y, 12, 31)}]
        last = getattr(src._tl, "last", None)
        name = last[0] if last and last[1] == text else ""
        irs = (S.today() - timedelta(days=8)).strftime("%d.%m.%Y")
        return {
            "crm_kargo_firma": [{"id": FIRM, "ad": "ARAS KARGO", "kod": "ARAS"}],
            "crm_kargo_bilgisi": [cargo(1, irs=irs), cargo(2, irs=irs, teslim=(S.today() - timedelta(days=6)).strftime("%d.%m.%Y")),
                                  cargo(3, irs=irs, takip="T1")],
            "crm_siparis_asama": [_order()],
            "crm_sevk_sayisi": [{"adet": 12, "bugun": 2}],
            "crm_kargo_takip": [{"belge_no": "B1", "takip_no": "T1", "olusturma": datetime(2026, 9, 1)}],
            "crm_sevkiyat": [{"id": "0e000000-0000-0000-0000-000000000001", "no": "SV1", "tarih": datetime(2026, 9, 2),
                              "tur": 7, "fatura_no": "F1", "logoda": 1, "eposta": 1}],
            "crm_sevkiyat_ay": [{"fatura_no": "F1"}],
            "logo_sevk": [{"fatura_no": "F1", "satir": 3, "adet": 10}],
            "logo_fatura_no": [{"no": "F1", "tarih": date(2026, 9, 2), "tur": 8}],
            "logo_kargo_fatura": [{"cari": "320.9", "kdv_dahil": 120.0, "kdv": 20.0}],
            "logo_kargo_cari_aday": [{"cari": "320.9", "unvan": "Aras Kargo", "fatura": 3, "kdv_haric": 300.0, "son": date(2026, 9, 1)}],
        }.get(name, [])


def _client(engine, monkeypatch, perms: set[str]):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from semantic_bridge import shipping_api

    monkeypatch.setattr(src, "runner", lambda path: FakeRun())
    app = FastAPI()
    conf = {"SHIPPING_LOGO_CARRIER_CODES": "ARAS KARGO=320.9"}
    cache = shipping_api.register(app, {
        "auth": lambda r: (engine, TN, "ayse", "Ayşe"), "require_caller": lambda r: None, "can": lambda u, k: k in perms,
        "is_admin": lambda u: False, "audit": lambda *a, **k: None, "conf": lambda k, d="": conf.get(k, d),
        "engine": lambda: engine, "tenant": lambda: TN, "logo_file": lambda: "", "crm_file": lambda: "",
        "llm": lambda p: None, "send_mail": lambda *a: "ok",
    })
    client = TestClient(app)
    client.kargo_cache = cache        # hız testleri belleği eskitir / arka plan işini bekler
    return client


def _check(out: dict) -> dict:
    k = out.get("kaynaklar")
    assert k and not k.get("error"), k
    assert P.uncovered_numbers(out, K.NOT_RAKAM) == []
    assert P.problems(out) == []
    for s in k["sources"].values():
        assert s["sql"].strip() and P.placeholders_left(s["sql"]) == [], (s["id"], P.placeholders_left(s["sql"]))
        low = s["sql"].lower()
        assert not any(col in low for col in src.FORBIDDEN_COLUMNS), s["id"]
        assert "as alici" not in low and "as teslim_alan" not in low
    json.dumps(out, default=str)
    return k


@pytest.mark.parametrize("perms", [set(), {COST, "ozellik:kargo.alici", "sayfa:kargo-mutabakat"}])
def test_every_shipping_endpoint_has_no_unsourced_number(engine, monkeypatch, perms):
    c = _client(engine, monkeypatch, perms)
    paths = ["/overview", "/errors", "/untracked", "/boxed", "/waiting", "/carriers", "/shipments", f"/shipments/{ORDER}"]
    if perms:
        paths += ["/reconcile?ay=" + (S.today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m"), "/reconcile/candidates"]
    for path in paths:
        r = c.get("/api/v1/shipping" + path)
        assert r.status_code == 200, (path, r.text)
        _check(r.json())


def test_cached_read_still_shows_the_filling_query(engine, monkeypatch):
    c = _client(engine, monkeypatch, set())
    first = c.get("/api/v1/shipping/waiting").json()["kaynaklar"]
    again = c.get("/api/v1/shipping/waiting").json()["kaynaklar"]       # 5 dk önbellekten
    assert "kargo.index.crm_kargo_bilgisi" in first["sources"] and "kargo.index.crm_kargo_bilgisi" in again["sources"]
    s = again["sources"]["kargo.index.crm_kargo_bilgisi"]
    assert "Timas_MSCRM.dbo.new_kargobilgisiBase" in s["sql"] and s["stats"]["rows"] == 3


def test_overview_counts_point_to_their_own_filtered_query(engine, monkeypatch):
    c = _client(engine, monkeypatch, set())
    k = c.get("/api/v1/shipping/overview").json()["kaynaklar"]
    hata = set(k["formulas"]["hata"]["inputs"])
    takipsiz = set(k["formulas"]["takipsiz"]["inputs"])
    assert "kargo.errors.crm_siparis_asama" in hata and "kargo.untracked.crm_siparis_asama" in takipsiz
    assert k["sources"]["kargo.errors.crm_siparis_asama"]["sql"] != k["sources"]["kargo.untracked.crm_siparis_asama"]["sql"]


# ------------------------------------------------------------------ anlık görüntü (hız, 2026-09-29)


class Boom:
    """CRM'e gidilirse cevap 503 olur: görüntüden dönmesi gereken okuma canlıya gitmiş demektir."""

    def __call__(self, text: str) -> list[dict]:
        raise src.SourceError("CRM'e gidilmemeliydi")


SCREENS = ["/overview", "/errors", "/untracked", "/boxed", "/waiting", "/carriers"]


def _numbers(out: dict) -> dict:
    return {k: v for k, v in out.items() if k != "kaynaklar"}


def _no_crm(engine, monkeypatch, perms):
    c = _client(engine, monkeypatch, perms)        # yeni süreç gibi: bellek boş
    monkeypatch.setattr(src, "runner", lambda path: Boom())
    return c


def test_pack_roundtrip_keeps_every_type():
    import uuid
    from datetime import time as dtime
    from decimal import Decimal

    v = [{"a": datetime(2026, 9, 1, 8, 30, 15, 120), "b": date(2026, 9, 1), "c": Decimal("12.50"), "d": uuid.UUID(ORDER),
          "e": dtime(10, 5), "f": b"\x00\x01", "g": (1, "x"), "h": None, "i": 1.25, "j": True, "k": "Ç", "l": [1, [2]]}]
    assert S.unpack(json.loads(json.dumps(S.pack(v)))) == v
    with pytest.raises(TypeError):
        S.pack({"x": object()})
    assert S.snapshot_key(("errors", date(2026, 8, 30))) == '["errors", "2026-08-30"]'


def test_snapshot_gives_the_same_numbers_without_touching_crm(engine, monkeypatch):
    live = _client(engine, monkeypatch, {COST})
    before = {p: live.get("/api/v1/shipping" + p).json() for p in SCREENS}       # canlı okuma, görüntüye yazar
    c = _no_crm(engine, monkeypatch, {COST})
    for p in SCREENS:
        r = c.get("/api/v1/shipping" + p)
        assert r.status_code == 200, (p, r.text)
        out = r.json()
        assert _numbers(out) == _numbers(before[p]), p                          # eski hesap = yeni hesap
        k = _check(out)
        snaps = {sid: s for sid, s in k["sources"].items() if sid.endswith(".anlik")}
        assert snaps and all(s["connection"] == "portal" and s["origin"] for s in snaps.values()), p
        assert all("semantic_shipping_snapshots" in s["sql"] for s in snaps.values())
    k = c.get("/api/v1/shipping/waiting").json()["kaynaklar"]
    assert "kargo.index.crm_kargo_bilgisi" in k["sources"]["kargo.index.anlik"]["origin"]
    assert "kargo.index.anlik" in k["formulas"]["bekleyen"]["inputs"]


def test_old_snapshot_goes_live_and_run_due_refreshes_it(engine, monkeypatch):
    from datetime import timezone

    assert _client(engine, monkeypatch, set()).get("/api/v1/shipping/overview").status_code == 200
    with engine.begin() as conn:
        conn.execute(S.SNAPSHOTS.update().values(alindi=datetime.now(timezone.utc) - timedelta(hours=3)))
    assert _no_crm(engine, monkeypatch, set()).get("/api/v1/shipping/overview").status_code == 503   # eski görüntü kullanılmaz
    timer = _client(engine, monkeypatch, set())
    assert timer.post("/api/v1/shipping/run-due?gorev=anlik").json()["anlik"]["ok"] is True
    assert _no_crm(engine, monkeypatch, set()).get("/api/v1/shipping/overview").status_code == 200


# ------------------------------------------------------------------ hız, 2. tur (2026-09-29)

MUTABAKAT = {COST, "sayfa:kargo-mutabakat"}


def _last_month() -> str:
    return (S.today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")


@pytest.fixture
def file_engine(tmp_path):
    """Dosyadaki SQLite: arka plan tazelemesi istekle aynı anda okur; bellek içi tek bağlantı paylaşılmasın."""
    e = open_store(f"sqlite:///{tmp_path / 'kargo.db'}").engine
    S._ready.discard(id(e))
    S.ensure(e)
    return e


def _expire(c, seconds: float = 3600) -> None:
    """Bellekteki değerlerin süresini doldurur (5 dk / 30 dk beklemeden)."""
    for e in c.kargo_cache._data.values():
        e.at -= seconds


def test_unpack_text_is_the_same_as_unpack():
    import uuid
    from datetime import time as dtime
    from decimal import Decimal

    v = [{"a": datetime(2026, 9, 1, 8, 30, 15, 120), "b": date(2026, 9, 1), "c": Decimal("12.50"), "d": uuid.UUID(ORDER),
          "e": dtime(10, 5), "f": b"\x00\x01", "g": (1, ("x", date(2026, 1, 2))), "h": None, "i": 1.25, "j": True,
          "k": "Ç", "l": [1, [2, {"m": (Decimal("1.5"),)}]]}]
    text = json.dumps(S.pack(v), ensure_ascii=False)
    assert S.unpack_text(text) == S.unpack(json.loads(text)) == v


def test_expired_memory_answers_at_once_and_does_not_reopen_the_same_snapshot(file_engine, monkeypatch):
    """Süresi dolan değer: istek beklemez (CRM'e ya da görüntüye gitmez), arkada denetlenir; tablodaki görüntü bellektekiyle
    aynıysa yeniden açılmaz (eskiden 5 dakikada bir ≈8 MB görüntü istek içinde açılıp dizin yeniden kuruluyordu)."""
    import time as _t

    engine = file_engine
    c = _client(engine, monkeypatch, {COST})
    before = {}
    for p in SCREENS:
        before[p] = _numbers(c.get("/api/v1/shipping" + p).json())
        c.kargo_cache.idle()
    monkeypatch.setattr(src, "runner", lambda path: Boom())             # CRM'e gidilirse 503 olurdu
    opened: list[int] = []
    real = S.unpack_text
    monkeypatch.setattr(S, "unpack_text", lambda t: (opened.append(1), real(t))[1])
    _expire(c)
    for p in SCREENS:
        r = c.get("/api/v1/shipping" + p)
        assert r.status_code == 200 and _numbers(r.json()) == before[p], p     # eski hesap = yeni hesap
        _check(r.json())
        c.kargo_cache.idle()
    assert opened == []
    assert all(_t.monotonic() - e.at < 60 for e in c.kargo_cache._data.values() if e.persist)


def test_newer_snapshot_is_opened_in_the_background_with_its_index(file_engine, monkeypatch):
    """Zamanlayıcı yeni görüntü yazdıysa istek eldekini alır; yenisi ve gönderi kaydı dizini arkada hazırlanır, sonraki
    istek dizini yeniden kurmaz."""
    import time as _t

    engine = file_engine
    c = _client(engine, monkeypatch, set())
    old = c.get("/api/v1/shipping/waiting").json()["toplam"]
    key = S.snapshot_key("index")
    snap = S.snapshot_read(engine, TN, key, 45)
    irs = (S.today() - timedelta(days=8)).strftime("%d.%m.%Y")
    _t.sleep(0.01)
    S.snapshot_write(engine, TN, key, snap["deger"] + [cargo(9, irs=irs)], snap["sorgular"])   # zamanlayıcı yazdı
    monkeypatch.setattr(src, "runner", lambda path: Boom())
    built: list[int] = []
    real = S.CargoIndex

    class Counting(real):
        def __init__(self, *a, **k):
            built.append(1)
            super().__init__(*a, **k)
    monkeypatch.setattr(S, "CargoIndex", Counting)
    _expire(c)
    assert c.get("/api/v1/shipping/waiting").json()["toplam"] == old          # beklemeden, eldeki
    c.kargo_cache.idle()
    assert built == [1]                                                        # dizin arkada kuruldu
    r = c.get("/api/v1/shipping/waiting")
    assert r.status_code == 200 and r.json()["toplam"] == old + 1 and built == [1]
    _check(r.json())


def test_opening_list_and_reconcile_come_from_the_snapshot(engine, monkeypatch):
    """Gönderi listesinin açılış sayfası ve mutabakat da görüntüde: yeni süreç CRM/Logo'ya gitmeden aynı cevabı verir;
    sorgu bilgisinde görüntü okuması ve kökeni (mutabakatta Logo faturası ve gönderi kaydı). Arama görüntüye yazılmaz."""
    live = _client(engine, monkeypatch, MUTABAKAT)
    paths = ["/shipments", "/reconcile?ay=" + _last_month()]
    before = {}
    for p in paths:
        before[p] = live.get("/api/v1/shipping" + p).json()
        live.kargo_cache.idle()
    c = _no_crm(engine, monkeypatch, MUTABAKAT)
    for p in paths:
        r = c.get("/api/v1/shipping" + p)
        assert r.status_code == 200, (p, r.text)
        out = r.json()
        assert _numbers(out) == _numbers(before[p]), p
        k = _check(out)
        snaps = [s for sid, s in k["sources"].items() if sid.endswith(".anlik")]
        assert snaps and all(s["connection"] == "portal" and s["origin"] for s in snaps), p
    rec = c.get("/api/v1/shipping/reconcile?ay=" + _last_month()).json()["kaynaklar"]
    origin = rec["sources"]["kargo.reconcile.anlik"]["origin"]
    assert any(o.startswith("kargo.index.") for o in origin) and any("logo_kargo_fatura" in o for o in origin)
    assert c.get("/api/v1/shipping/shipments?q=SP-1").status_code == 503      # arama canlı okunur


def test_run_due_writes_the_opening_list_and_last_month_reconcile(engine, monkeypatch):
    timer = _client(engine, monkeypatch, set())
    out = timer.post("/api/v1/shipping/run-due?gorev=anlik").json()
    assert out["anlik"]["ok"] and out["anlikListe"]["ok"] and out["anlikMutabakat"]["ok"], out
    c = _no_crm(engine, monkeypatch, MUTABAKAT)
    assert c.get("/api/v1/shipping/shipments").status_code == 200
    assert c.get("/api/v1/shipping/reconcile?ay=" + _last_month()).status_code == 200
