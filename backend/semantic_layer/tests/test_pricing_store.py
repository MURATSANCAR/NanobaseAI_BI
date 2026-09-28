"""M9 kayıtları: analiz yaşam döngüsü, iki göz onay, aşamaya göre imza, pazar fiyatı, varsayılanlar, toplu zam teklifi."""

from __future__ import annotations

import pytest

from semantic_bridge import access as A
from semantic_bridge.pricing import store as S
from semantic_layer.store.catalog_store import open_store

T = "t1"


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    S._ready.discard(id(e))
    S.ensure(e)
    return e


def _analysis(engine, **kw):
    body = {"title": "Deneme Kitap", "stage": "tahmini", "specs": {"pages": 208}, "inputs": {"qtys": [1000, 3000]}}
    body.update(kw)
    return S.create_analysis(engine, T, "hazirlayan", body)


def _ready(engine, a):
    return S.update_analysis(engine, T, "hazirlayan", a["id"], {"chosenPrice": 240, "chosenQty": 3000})


def test_create_validates(engine):
    with pytest.raises(S.PricingError, match="adı"):
        S.create_analysis(engine, T, "u", {"title": "  "})
    with pytest.raises(S.PricingError, match="Aşama"):
        S.create_analysis(engine, T, "u", {"title": "X", "stage": "baska"})
    a = _analysis(engine)
    assert a["status"] == "taslak" and a["version"] == 1 and [r["role"] for r in a["required"]] == ["mali", "satis"]
    assert S.list_analyses(engine, T)["total"] == 1


def test_submit_requires_choice_and_freezes(engine):
    a = _analysis(engine)
    with pytest.raises(S.PricingError, match="seçin"):
        S.submit(engine, T, "hazirlayan", a["id"], {"summary": {}})
    _ready(engine, a)
    sub = S.submit(engine, T, "hazirlayan", a["id"], {"summary": {"price": 240}})
    assert sub["status"] == "onayda" and sub["version"] == 2 and sub["result"]["summary"]["price"] == 240
    with pytest.raises(S.PricingError, match="değiştirilemez"):
        S.update_analysis(engine, T, "hazirlayan", a["id"], {"note": "x"})


def test_stage1_two_signatures_and_four_eyes(engine):
    a = _ready(engine, _analysis(engine))
    a = S.submit(engine, T, "hazirlayan", a["id"], {})
    v = a["version"]
    with pytest.raises(S.PricingError, match="gönderen"):
        S.decide(engine, T, "hazirlayan", a["id"], "mali", "onay", "", v, True)
    with pytest.raises(S.PricingError, match="yetkiniz yok"):
        S.decide(engine, T, "mali1", a["id"], "mali", "onay", "", v, False)
    with pytest.raises(S.PricingError, match="istenmiyor"):
        S.decide(engine, T, "paz1", a["id"], "pazarlama", "onay", "", v, True)
    with pytest.raises(S.PricingError, match="değişti"):
        S.decide(engine, T, "mali1", a["id"], "mali", "onay", "", v - 1, True)
    a = S.decide(engine, T, "mali1", a["id"], "mali", "onay", "", v, True)
    assert a["status"] == "onayda"
    with pytest.raises(S.PricingError, match="tek rol"):
        S.decide(engine, T, "mali1", a["id"], "satis", "onay", "", v, True)
    with pytest.raises(S.PricingError, match="kararını verdi"):
        S.decide(engine, T, "mali2", a["id"], "mali", "onay", "", v, True)
    a = S.decide(engine, T, "satis1", a["id"], "satis", "onay", "uygun", v, True)
    assert a["status"] == "onaylandi" and len(a["approvals"]) == 2


def test_stage2_needs_four_and_reject_returns_to_draft(engine):
    a = _ready(engine, _analysis(engine, stage="kesin"))
    assert len(a["required"]) == 4
    a = S.submit(engine, T, "hazirlayan", a["id"], {})
    v = a["version"]
    for role, user in (("mali", "m"), ("satis", "s"), ("pazarlama", "p")):
        a = S.decide(engine, T, user, a["id"], role, "onay", "", v, True)
    assert a["status"] == "onayda"
    with pytest.raises(S.PricingError, match="nedenini"):
        S.decide(engine, T, "y", a["id"], "yonetim", "ret", " ", v, True)
    a = S.decide(engine, T, "y", a["id"], "yonetim", "ret", "Fiyat yüksek", v, True)
    assert a["status"] == "reddedildi"
    # Düzeltme taslağa döndürür; yeniden gönderince imzalar yeni sürümde sıfırdan.
    a = S.update_analysis(engine, T, "hazirlayan", a["id"], {"chosenPrice": 220})
    assert a["status"] == "taslak"
    a = S.submit(engine, T, "hazirlayan", a["id"], {})
    assert a["version"] == v + 1 and a["approvals"] == [] and len(a["history"]) == 4


def test_withdraw_and_archive(engine):
    a = _ready(engine, _analysis(engine))
    a = S.submit(engine, T, "hazirlayan", a["id"], {})
    with pytest.raises(S.PricingError, match="arşive"):
        S.archive(engine, T, "hazirlayan", a["id"])
    a = S.withdraw(engine, T, "hazirlayan", a["id"])
    assert a["status"] == "taslak"
    S.archive(engine, T, "hazirlayan", a["id"])
    assert S.list_analyses(engine, T)["total"] == 0
    assert S.list_analyses(engine, T, status="arsiv")["total"] == 1


def test_market_prices(engine):
    a = _analysis(engine)
    with pytest.raises(S.PricingError, match="adını"):
        S.market_add(engine, T, "u", {"price": 100})
    with pytest.raises(S.PricingError, match="sıfırdan"):
        S.market_add(engine, T, "u", {"title": "Rakip", "price": 0})
    with pytest.raises(S.PricingError, match="http"):
        S.market_add(engine, T, "u", {"title": "Rakip", "price": 250, "url": "javascript:x"})
    m = S.market_add(engine, T, "u", {"title": "Rakip", "price": "250", "pages": 200, "analysisId": a["id"],
                                      "publisher": "Başka Yayınevi", "seenOn": "2026-09-20"})
    got = S.get_analysis(engine, T, a["id"])["market"]
    assert len(got) == 1 and got[0]["price"] == 250 and got[0]["seenOn"] == "2026-09-20"
    with pytest.raises(S.PricingError, match="yalnız giren"):
        S.market_delete(engine, T, "baskasi", m["id"], False)
    S.market_delete(engine, T, "baskasi", m["id"], True)
    assert S.get_analysis(engine, T, a["id"])["market"] == []


def test_defaults(engine):
    d = S.get_defaults(engine, T)
    assert d["targetMargin"] == 0.15 and d["qtys"] == [1000, 2000, 3000, 5000]
    with pytest.raises(S.PricingError, match="arasında"):
        S.save_defaults(engine, T, "u", {"targetMargin": 1.5})
    with pytest.raises(S.PricingError, match="sıfır olamaz"):
        S.save_defaults(engine, T, "u", {"sellThrough": 0})
    d = S.save_defaults(engine, T, "u", {"targetMargin": 0.2, "qtys": [5000, 1500, 1500],
                                         "channelMix": {"kitabevi": 3, "e-ticaret": 1}})
    assert d["targetMargin"] == 0.2 and d["qtys"] == [1500, 5000] and d["channelMix"] == {"kitabevi": 0.75, "e-ticaret": 0.25}
    assert d["updatedBy"] == "u"


def test_proposals(engine):
    with pytest.raises(S.PricingError, match="en az bir"):
        S.proposal_create(engine, T, "haz", "Zam", [], {})
    p = S.proposal_create(engine, T, "haz", "Eylül zammı", [{"code": "15201.01.1", "from": 100, "to": 120}], {"ratio": 0.2})
    assert p["status"] == "onayda" and p["count"] == 1
    with pytest.raises(S.PricingError, match="yalnız Mali"):
        S.proposal_decide(engine, T, "m", p["id"], "onay", "", False)
    with pytest.raises(S.PricingError, match="hazırlayan"):
        S.proposal_decide(engine, T, "haz", p["id"], "onay", "", True)
    p = S.proposal_decide(engine, T, "m", p["id"], "onay", "", True)
    assert p["status"] == "onaylandi" and p["decidedBy"] == "m"
    assert S.proposal_list(engine, T)["items"][0]["count"] == 1


def test_access_rules_cover_pricing():
    assert A.rule_for("/api/v1/pricing/overview") == frozenset({A.page("fiyatlama")})
    assert A.features_for("POST", "/api/v1/pricing/analyses") == ["ozellik:fiyatlama.yaz"]
    assert A.features_for("POST", "/api/v1/pricing/analyses/abc/submit") == ["ozellik:fiyatlama.yaz"]
    assert A.features_for("PATCH", "/api/v1/pricing/analyses/abc") == ["ozellik:fiyatlama.yaz"]
    assert A.features_for("POST", "/api/v1/pricing/calc") == []
    # İmza ucu sayfa yetkisiyle açılır; rolün açık yetkisini uç kendisi denetler.
    assert A.features_for("POST", "/api/v1/pricing/analyses/abc/decide") == []
    keys = A.all_keys()
    for role in S.APPROVERS:
        assert S.approve_key(role) in keys
