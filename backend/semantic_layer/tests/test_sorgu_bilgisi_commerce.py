"""Sorgu bilgisi — H3 E-ticaret müşterileri (G5 yayılımı): her rakam ucunda kaynaksız rakam yok, SQL çalışan metnin kendisi,
kişisel veri kayda girmez (yalnız SQL metni ve satır sayısı). Kabul: `scripts/acceptance/sorgu-bilgisi/g5_commerce.py`.
"""
from __future__ import annotations

import json

from semantic_bridge import commerce as C
from semantic_bridge import commerce_kaynak as CK
from semantic_bridge import provenance as P
from semantic_bridge import sorgu_yakala as Y
from semantic_layer.tests.test_commerce import TODAY, T, _h2, _key, _sync, conf
from semantic_layer.tests.test_commerce import _env, engine  # noqa: F401 — fixture


def _check(out: dict) -> dict:
    k = out.get("kaynaklar")
    assert k and not k.get("error"), k
    assert P.uncovered_numbers(out, CK.NOT_RAKAM) == []
    assert P.problems(out) == []
    assert k["sources"]
    text = json.dumps(k, default=str)
    assert "@" not in text.replace("'@", "")   # e-posta biçimli değer kayda girmez
    for s in k["sources"].values():
        assert s["sql"].strip() and P.placeholders_left(s["sql"]) == [], s
        assert s["connection"] in ("logo", "crm", "portal")
    return k


def _with(engine, build, fn, *a, **kw):
    with Y.yakala(engine) as q:
        out = fn(*a, **kw)
    return P.ekle(out, build(engine, T, out, q))


def test_overview_rfm_customers_card_funnel(engine):
    _sync(engine)
    st = C.settings(engine, T, conf())
    k = _check(_with(engine, CK.for_overview, C.overview, engine, T, st, "ay", today=TODAY))
    assert any("semantic_commerce_orders" in s["sql"] for s in k["sources"].values())
    _check(_with(engine, CK.for_rfm, C.rfm, engine, T, st, TODAY))
    _check(_with(engine, CK.for_moves, C.moves, engine, T, 30))
    _check(_with(engine, CK.for_customers, C.customers, engine, T))
    card = _with(engine, CK.for_customer, C.customer_card, engine, T, _key("e@v.com"))
    _check(card)
    _check(_with(engine, CK.for_funnel, C.funnel, engine, T, st, 30, today=TODAY))
    _check(_with(engine, CK.for_segments_summary, C.segments_summary, engine, T))


def test_triggers_runs_and_campaign(engine):
    _sync(engine)
    _h2(engine)
    st = C.settings(engine, T, conf())
    t = C.create_trigger(engine, T, "uzman", {"name": "Herkes", "kind": "geri-kazanim", "controlShare": 0.34,
                                               "params": {"minGun": 1, "maxGun": 400}}, st)
    _check(_with(engine, CK.for_run, C.preview, engine, T, t["id"], st, TODAY))
    run = C.run_trigger(engine, T, t["id"], "uzman", st, TODAY)
    _check(_with(engine, CK.for_runs, C.list_runs, engine, T))
    _check(_with(engine, CK.for_run, lambda: C._run_view(C.run_row(engine, T, run["id"]))))
    with Y.yakala(engine) as q:
        out = {"items": C.list_triggers(engine, T)}
    _check(P.ekle(out, CK.for_triggers(engine, T, out, q)))
    C.decide_run(engine, T, run["id"], "mudur", True)
    cp = C.create_campaign(engine, T, "uzman", {"runId": run["id"], "start": "2026-09-01", "end": "2026-09-30"}, st)
    _check(_with(engine, CK.for_campaign, C.campaign, engine, T, cp["id"], st))
    with Y.yakala(engine) as q:
        out = {"items": C.list_campaigns(engine, T)}
    _check(P.ekle(out, CK.for_campaigns(engine, T, out, q)))
