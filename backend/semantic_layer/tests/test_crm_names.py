"""CRM varlık/alan etiketleri (`semantic_bridge/crm_names.py`, uç `/api/v1/semantic/crm-names`).

Denetlenen: Türkçe etiket İngilizceden önce; aynı alanın varlıklara göre farklı etiketi hem genel (en sık) hem
`varlık.alan` anahtarıyla; boş etiket atlanır; CRM okunamazsa boş harita ve 10 dk sonra yeniden deneme; köprüde uç açık
ve CRM bağlantısı yokken boş harita döner. Gerçek CRM'le kabul: günlük 2026-09-29.
"""
from __future__ import annotations

from semantic_bridge import crm_names as C


def test_build_language_priority_and_qualified_keys():
    ents = [{"ad": "new_kitap", "etiket": "Book", "dil": 1033}, {"ad": "new_kitap", "etiket": "Kitap Kartı", "dil": 1055},
            {"ad": "account", "etiket": " Firma ", "dil": 1055}]
    attrs = [
        {"varlik": "new_kitap", "ad": "new_durum", "etiket": "Kitap Durumu", "dil": 1055},
        {"varlik": "new_proje", "ad": "new_durum", "etiket": "Durum", "dil": 1055},
        {"varlik": "new_teklif", "ad": "new_durum", "etiket": "Durum", "dil": 1055},
        {"varlik": "new_kitap", "ad": "new_HaberMecrasName", "etiket": "Haber Mecrası", "dil": 1055},
        {"varlik": "new_kitap", "ad": "new_HaberMecrasName", "etiket": "News Outlet", "dil": 1033},
        {"varlik": "new_kitap", "ad": "new_bos", "etiket": "  ", "dil": 1055},
        {"varlik": "new_kitap", "ad": "new_yalniz_ing", "etiket": "Only English", "dil": 1033},
    ]
    out = C.build(ents, attrs)
    assert out["entities"] == {"new_kitap": "Kitap Kartı", "account": "Firma"}
    a = out["attributes"]
    assert a["new_durum"] == "Durum"                      # en sık etiket
    assert a["new_kitap.new_durum"] == "Kitap Durumu"     # varlığa özel fark ayrıca
    assert "new_proje.new_durum" not in a                 # genel etiketle aynıysa tekrar yazılmaz
    assert a["new_habermecrasname"] == "Haber Mecrası"    # Türkçe önce, anahtar küçük harf
    assert "new_bos" not in a
    assert a["new_yalniz_ing"] == "Only English"          # Türkçe yoksa İngilizce


def test_build_sends_only_prefixed_attributes():
    out = C.build([], [{"varlik": "account", "ad": "name", "etiket": "Ad", "dil": 1055},
                       {"varlik": "account", "ad": "address1_city", "etiket": "Şehir", "dil": 1055}])
    assert out["attributes"] == {"address1_city": "Şehir"}


def test_cache_failure_returns_empty_and_retries_later(monkeypatch):
    calls = {"n": 0}

    def run(sql):
        calls["n"] += 1
        raise RuntimeError("CRM kapalı")

    names = C.CrmNames(run)
    assert names.get() == {"entities": {}, "attributes": {}, "version": "0"}
    n = calls["n"]
    names.get()
    assert calls["n"] == n                                # hemen yeniden denemez
    t = C.time.time()
    monkeypatch.setattr(C.time, "time", lambda: t + 601)
    names.get()
    assert calls["n"] > n                                 # 10 dk sonra yeniden dener


def test_cache_serves_and_refreshes():
    rows = {"e": [{"ad": "new_kitap", "etiket": "Kitap", "dil": 1055}], "a": []}
    names = C.CrmNames(lambda sql: rows["e"] if "Entity e\nJOIN MetadataSchema.LocalizedLabel" in sql else rows["a"])
    first = names.get()
    assert first["entities"] == {"new_kitap": "Kitap"} and first["version"] != "0"


def test_bridge_endpoint_open_and_empty_without_crm(monkeypatch, store, settings):
    from semantic_bridge import access as A
    from semantic_layer.tests.test_access import _app

    monkeypatch.setenv("SEMANTIC_CRM_CONNECTION_FILE", "/yok/crm.json")
    assert A.rule_for("/api/v1/semantic/crm-names") == A.OPEN
    _, client = _app(monkeypatch, store, settings)
    r = client.get("/api/v1/semantic/crm-names")
    assert r.status_code == 200
    assert r.json()["entities"] == {} and r.json()["attributes"] == {}
