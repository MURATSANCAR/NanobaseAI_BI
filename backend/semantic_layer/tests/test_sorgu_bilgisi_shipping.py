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
    shipping_api.register(app, {
        "auth": lambda r: (engine, TN, "ayse", "Ayşe"), "require_caller": lambda r: None, "can": lambda u, k: k in perms,
        "is_admin": lambda u: False, "audit": lambda *a, **k: None, "conf": lambda k, d="": conf.get(k, d),
        "engine": lambda: engine, "tenant": lambda: TN, "logo_file": lambda: "", "crm_file": lambda: "",
        "llm": lambda p: None, "send_mail": lambda *a: "ok",
    })
    return TestClient(app)


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
