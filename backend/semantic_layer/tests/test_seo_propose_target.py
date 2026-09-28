"""SEO fırsat sorgusundan tek tıkla ürün önerisi: hedef sorgu isteme girer (kişisel veri maskeli), kayıtta olmayan
iddia yazılmaz diye uyarılır; öneri aynı akışla «hazır» kaydedilir, hedef sorgu ayrı tabloda; fırsat satırı önerinin
durumunu görür; başlık/meta/arama kelimesinde hedef kelimeler denetlenir. T-soft'a hiçbir istek gitmez.

Veriler yapaydır; model yerine sahte `chat`.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from semantic_bridge.seo_geo import SeoGeo, opportunities as op, propose, rules
from semantic_bridge.seo_geo.store import PRODUCTS, PROPOSALS, TARGETS, dumps
from semantic_layer.store.catalog_store import open_store

P = {"ProductName": "Küçük Prens", "Model": "Antoine de Saint-Exupéry", "Brand": "Timaş Çocuk", "Barcode": "9786050812348",
     "SeoTitle": "", "SeoDescription": "", "SearchKeywords": "", "Details": "<p>Bir çocuk ve bir gezegen.</p>",
     "SeoLink": "/kucuk-prens"}
LIM = {"title_min": 30, "title_max": 65, "meta_min": 120, "meta_max": 160, "desc_min_words": 150}
ANSWER = {"SeoTitle": "Küçük Prens - Antoine de Saint-Exupéry | Timaş Çocuk",
          "SeoDescription": "Küçük Prens kitabı, bir çocuğun gezegenler arasındaki yolculuğunu anlatır; Antoine de "
                            "Saint-Exupéry'nin sevilen eseri Timaş Çocuk etiketiyle okurla buluşuyor.",
          "SearchKeywords": "küçük prens, küçük prens kitabı, saint-exupéry", "Details": "<p>Bir çocuk ve bir gezegen.</p>"}


class Chat:
    model = "sahte"

    def __init__(self):
        self.calls = []

    def chat(self, messages, **kw):
        self.calls.append(messages)
        return json.dumps(ANSWER, ensure_ascii=False)


def test_prompt_carries_target_query_before_the_record():
    plain = propose.build_prompt(P, LIM)
    with_target = propose.build_prompt(P, LIM, "küçük prens kitabı")
    assert "HEDEF ARAMA SORGUSU" not in plain
    assert with_target.index("«küçük prens kitabı»") < with_target.index("ÜRÜN KAYDI")
    assert "YAZMA" in with_target and plain.split("ÜRÜN KAYDI")[1] == with_target.split("ÜRÜN KAYDI")[1]


def test_target_check_reports_missing_words():
    c = propose.target_check(ANSWER, "küçük prens kitabı")
    assert c["inMeta"] and c["inKeywords"] and not c["inTitle"] and c["missingTitle"] == ["kitabı"]
    assert propose.target_check(ANSWER, "") is None


@pytest.fixture
def seo():
    e = open_store("sqlite://").engine
    llm = Chat()
    rt = SimpleNamespace(store=SimpleNamespace(engine=e), settings=SimpleNamespace(tenant_id="t1"),
                         llm_for=lambda module, priority=None: llm)
    s = SeoGeo(lambda: rt)
    eng = s.engine()
    with eng.begin() as c:
        c.execute(PRODUCTS.insert().values(tenant_id="t1", product_id="p1", name="Küçük Prens", active=True, score=40,
                                           issues_json="[]", rules=",meta_missing,", data_json=dumps(P),
                                           synced_at=datetime.now(timezone.utc)))
    s._llm = llm
    return s


def test_proposal_for_query_is_recorded_and_masked(seo):
    target = {"query": "küçük prens kitabı ali@ornek.com", "page": "https://timas.com.tr/kucuk-prens", "position": 7.4,
              "impressions": 900, "clicks": 12, "kind": "yakin"}
    out = seo.make_proposal("p1", "seo-uzmani", target=target)
    assert out["status"] == "hazir"                                          # akış aynı: onay insanda
    sent = seo._llm.calls[0][0]["content"]
    assert "küçük prens kitabı" in sent and "ali@ornek.com" not in sent
    t = seo.targets([out["id"]])[out["id"]]
    assert t["query"].startswith("küçük prens kitabı") and "ali@ornek.com" not in t["query"] and t["impressions"] == 900
    # fırsat satırı: aynı ürün + aynı sorgu için istenen öneri görünür
    done = op.target_proposals(seo, ["p1"])
    assert done[("p1", op.fold(t["query"]))] == {"id": out["id"], "status": "hazir"}
    # hedefsiz öneri hedef tablosuna yazılmaz; bekleyen eski öneri yenisiyle değişir
    plain = seo.make_proposal("p1", "seo-uzmani")
    assert seo.targets([plain["id"]]) == {}
    with seo.engine().connect() as c:
        assert c.execute(PROPOSALS.select().where(PROPOSALS.c.status == "hazir")).all().__len__() == 1
        assert c.execute(TARGETS.select()).all().__len__() == 1               # sorgu kaydı iz olarak kalır


def test_no_tsoft_client_is_touched(seo, monkeypatch):
    from semantic_bridge.seo_geo import connections

    def forbidden(*a, **k):
        raise AssertionError("T-soft'a istek gitmemeli")
    for name in dir(connections.tsoft):
        if name.startswith(("update", "post", "put", "write", "send")) and callable(getattr(connections.tsoft, name)):
            monkeypatch.setattr(connections.tsoft, name, forbidden)
    seo.make_proposal("p1", "seo-uzmani", target={"query": "küçük prens"})
    assert rules.thresholds(seo.conf)["title_max"] >= 30
