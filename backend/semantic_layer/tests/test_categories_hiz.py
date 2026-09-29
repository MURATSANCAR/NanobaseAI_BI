"""Kategori ağacı hız (2026-09-29): özetin ortak kısmı süreç belleğinde, kişinin CRM kullanıcısı portal tablosunda.

Sözleşme: rakamlar eski hesapla birebir aynı (eski `overview` aşağıda aynen durur); yazma ucundan sonra özet yeniden
hesaplanır; «Verileri yenile» (X-Data-Refresh) belleği atlar; kişiye özel «benim bekleyenlerim» her istekte kişinin
kendi sorgusuyla; sorgu bilgisi rakamları üreten okumaları gösterir. Kişinin CRM kullanıcısı bir kez CRM'den okunur,
portal tablosuna yazılır; köprü yeniden kalkınca tablodan gelir, süresi geçince CRM arkada yeniden okunur.

Veriler yapaydır; gerçek CRM/Logo kabulü test sunucusunda.
"""
from __future__ import annotations

import threading
from collections import Counter
from types import SimpleNamespace
from typing import Any, Optional

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient

from semantic_bridge import admin as ADM
from semantic_bridge import board as BOARD
from semantic_bridge import categories as C
from semantic_bridge import categories_api as CA
from semantic_bridge import categories_sources as CS
from semantic_bridge import editorial_assign as M2
from semantic_bridge import provenance as P
from semantic_layer.store.catalog_store import open_store
from semantic_layer.tests.test_categories import T, _seed, _tree

COOKIE = {"cookie": "timas_session=a"}


def _eski_overview(engine: sa.engine.Engine, tenant: str, me_crm_id: Optional[str]) -> dict[str, Any]:
    """2026-09-29 öncesi `categories.overview` (aynen): yeni hesap bununla karşılaştırılır."""
    PR = C.PROFILES.c
    with engine.connect() as c:
        rows = c.execute(sa.select(C.PROFILES.c.status, C.PROFILES.c.crm_snapshot_json, C.PROFILES.c.priority_score,
                                   C.PROFILES.c.node_id, C.PROFILES.c.resolved_node_id)
                         .where(PR.tenant_id == tenant, PR.active.is_(True))).all()
        open_by_rule = dict(c.execute(sa.select(C.FINDINGS.c.rule_key, sa.func.count()).select_from(
            C.FINDINGS.join(C.PROFILES, sa.and_(PR.tenant_id == C.FINDINGS.c.tenant_id, PR.book_id == C.FINDINGS.c.book_id)))
            .where(C.FINDINGS.c.tenant_id == tenant, C.FINDINGS.c.status == "acik", PR.active.is_(True))
            .group_by(C.FINDINGS.c.rule_key)).all())
    status = Counter()
    fill = Counter()
    selling = selling_approved = placed = 0
    links: Counter = Counter()
    for st, raw, score, node_id, resolved in rows:
        status[st] += 1
        b = C.loads(raw, {})
        checks = {"kitaplik": bool(b.get("kitaplik")), "tur": bool(b.get("tur") or b.get("turMetni")),
                  "web": bool(b.get("web")), "hedefKitle": bool(b.get("hedefKitle")), "yas": bool(b.get("yas")),
                  "tema": bool(b.get("tema")), "ozet": bool(b.get("ozetVar")), "urunkategorisi": bool(b.get("urunkategorisi")),
                  "anahtarkelime": bool(b.get("anahtarkelime"))}
        for k, v in checks.items():
            fill[k] += int(v)
        for k in ("tema", "urunkategorisi", "raf", "sergilenecek", "anahtarkelime", "tur"):
            links[k] += len(b.get(k) or [])
        if (score or 0) > 0:
            selling += 1
            if node_id:
                selling_approved += 1
        if node_id or resolved:
            placed += 1
    n = len(rows)
    live = C.in_force(engine, tenant)
    dr = C.draft(engine, tenant)
    sync = C.meta_get(engine, tenant, "sync", {}) or {}
    pr = C.meta_get(engine, tenant, "priority", {}) or {}
    ts = C.meta_get(engine, tenant, "tsoft", {}) or {}
    labels = {"kitaplik": "Kitaplık", "tur": "Tür", "web": "Web kategorisi", "hedefKitle": "Hedef kitle",
              "yas": "Yaş aralığı", "tema": "Tema", "ozet": "Arka kapak metni", "urunkategorisi": "Ürün kategorisi",
              "anahtarkelime": "Anahtar kelime"}
    diff = C.crm_diff(engine, tenant) if status.get("onayli") or status.get("kismi") or status.get("red") else {"total": 0, "stale": 0, "books": 0}
    return {
        "activeBooks": n, "status": {k: status.get(k, 0) for k in C.PROFILE_STATUS}, "statusLabels": C.PROFILE_STATUS,
        "fill": [{"key": k, "label": lab, "filled": fill.get(k, 0), "total": n} for k, lab in labels.items()],
        "links": dict(links), "selling": selling, "sellingApproved": selling_approved, "placed": placed,
        "findings": {"open": sum(open_by_rule.values()), "byRule": open_by_rule,
                     "labels": {k: d["label"] for k, d in C.RULE_DEFS.items()}},
        "tree": {"inForce": live, "draft": dr}, "sync": sync, "priority": pr,
        "tsoft": {"syncedAt": ts.get("syncedAt"), "products": ts.get("products"), "categories": len(ts.get("categories") or {})},
        "mine": C.my_pending(engine, tenant, me_crm_id), "crmDiff": {"rows": diff["total"], "stale": diff["stale"], "books": diff["books"]},
        "thresholds": C.thresholds(),
    }


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    C._ready.discard(id(e))
    C.ensure(e)
    return e


def _bekle() -> None:
    """Arkadaki bellek hesaplarını bekler (bellek içi SQLite tek bağlantı: test iş parçacığıyla çakışmasın)."""
    for t in threading.enumerate():
        if t.name.startswith("bellek:") and t is not threading.current_thread():
            t.join(10)


@pytest.fixture
def crm(monkeypatch):
    """Sahte CRM: kişi → CRM kullanıcısı; kaç kez okunduğu sayılır. `down` True iken okuma hata verir."""
    state = {"calls": 0, "down": False, "ids": {"ayse": "ED1", "mehmet": "ED2"}}

    def fake_me(schema, run, username):
        state["calls"] += 1
        if state["down"]:
            raise RuntimeError("CRM kapalı")
        uid = state["ids"].get(username.lower())
        return {"id": uid, "name": username, "disabled": False} if uid else None

    monkeypatch.setattr(M2, "crm_me", fake_me)
    monkeypatch.setattr(CS, "runner", lambda path, timeout=None: (lambda sql: []))
    orig = ADM.conf
    monkeypatch.setattr(ADM, "conf", lambda k, d="": "Timas_MSCRM.dbo" if k == "CRM_SCHEMA" else orig(k, d))
    return state


def _client(engine, monkeypatch, user: str = "ayse") -> TestClient:
    monkeypatch.setattr(BOARD, "_fetch_session", lambda cookie: {"username": user, "displayName": user.title()})
    rt = SimpleNamespace(store=SimpleNamespace(engine=engine),
                         settings=SimpleNamespace(tenant_id=T, connection_file=None))
    app = FastAPI()
    CA.register(app, lambda: rt, lambda request: None, lambda u, k: True)
    return TestClient(app)


def _rakam(out: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in out.items() if k not in ("job", "kaynaklar")}


def _hazirla(engine) -> None:
    _seed(engine)
    _tree(engine)
    C.store_proposal(engine, T, "B5", {
        "kategori": {"proposed": "n_tas", "source": "Zeki AI", "method": "logprobs", "confident": True, "probability": 0.9},
        "tur": {"proposed": ["Roman"], "source": "Zeki AI", "method": "logprobs", "confident": True},
    }, "Zeki AI")
    C.decide(engine, T, "yy", "B5", {"fields": {"kategori": {"action": "kabul"}}}, me_crm_id=None, everyone=True)
    C.store_proposal(engine, T, "B1", {"kategori": {"proposed": "n_610", "source": "CRM beyanı", "method": "beyan",
                                                    "confident": True}}, "Zeki AI")


def test_new_overview_equals_old_computation(engine):
    _hazirla(engine)
    for me in ("ED1", "ED2", None):
        assert C.overview(engine, T, me) == _eski_overview(engine, T, me)
        assert list(C.overview(engine, T, me)) == list(_eski_overview(engine, T, me))   # anahtar sırası da aynı


def test_overview_endpoint_memory_write_and_refresh(engine, monkeypatch, crm):
    _hazirla(engine)
    hesap = {"n": 0}
    orig = C.overview_ortak

    def sayan(e, t):
        hesap["n"] += 1
        return orig(e, t)

    monkeypatch.setattr(C, "overview_ortak", sayan)
    client = _client(engine, monkeypatch)

    first = client.get("/api/v1/categories/overview", headers=COOKIE).json()
    assert _rakam(first) == _eski_overview(engine, T, "ED1") and hesap["n"] == 1
    assert first["mine"]["pending"] == 2                                   # B1 (taslak) ve B5 (kısmi) ED1'in
    assert P.uncovered_numbers(first) == [] and P.problems(first) == []
    sqls = [s["sql"] for s in first["kaynaklar"]["sources"].values()]
    assert any("semantic_book_profiles" in s and "'ED1'" in s for s in sqls)          # kişinin kendi sorgusu
    assert any("crm_snapshot_json" in s for s in sqls)                                # ortak kısmı hesaplayan okuma

    second = client.get("/api/v1/categories/overview", headers=COOKIE).json()
    assert _rakam(second) == _rakam(first) and hesap["n"] == 1             # bellekten
    assert P.uncovered_numbers(second) == []

    # Yazma ucu: özet düşer, arkada yeniden hesaplanır; sonraki okuma yeni rakamı eski hesapla aynı verir.
    r = client.post("/api/v1/categories/books/B1/decision", json={"all": "kabul"}, headers=COOKIE)
    assert r.status_code == 200, r.text
    _bekle()
    third = client.get("/api/v1/categories/overview", headers=COOKIE).json()
    assert _rakam(third) == _eski_overview(engine, T, "ED1")
    assert third["status"]["onayli"] == first["status"]["onayli"] + 1 and third["mine"]["pending"] == 1

    # «Verileri yenile»: bellek atlanır.
    n = hesap["n"]
    client.get("/api/v1/categories/overview", headers={**COOKIE, "x-data-refresh": "1"})
    assert hesap["n"] == n + 1


def test_mine_is_personal_while_common_part_is_shared(engine, monkeypatch, crm):
    _hazirla(engine)
    client = _client(engine, monkeypatch, "ayse")
    a = client.get("/api/v1/categories/overview", headers=COOKIE).json()
    # Aynı köprü (aynı bellek), başka kişi: ortak kısım bellekten, «benim bekleyenlerim» kişinin kendisi.
    monkeypatch.setattr(BOARD, "_fetch_session", lambda cookie: {"username": "mehmet", "displayName": "Mehmet"})
    m = client.get("/api/v1/categories/overview", headers=COOKIE).json()
    assert _rakam(a) == _eski_overview(engine, T, "ED1") and _rakam(m) == _eski_overview(engine, T, "ED2")
    assert a["mine"]["pending"] == 2 and m["mine"]["pending"] == 0
    assert any("'ED2'" in s["sql"] for s in m["kaynaklar"]["sources"].values())
    assert not any("'ED1'" in s["sql"] for s in m["kaynaklar"]["sources"].values())


def test_crm_user_is_read_once_stored_and_refreshed_behind(engine, monkeypatch, crm):
    client = _client(engine, monkeypatch)
    assert client.get("/api/v1/categories/meta", headers=COOKIE).json()["me"]["crmId"] == "ED1"
    assert crm["calls"] == 1
    assert C.meta_get(engine, T, "crm_me:ayse")["id"] == "ED1"                   # portal tablosunda
    client.get("/api/v1/categories/meta", headers=COOKIE)
    assert crm["calls"] == 1                                                   # süreç belleğinden

    # Köprü yeniden kalktı (yeni bellek): CRM beklenmez, tablodan gelir.
    again = _client(engine, monkeypatch)
    assert again.get("/api/v1/categories/meta", headers=COOKIE).json()["me"]["crmId"] == "ED1"
    assert crm["calls"] == 1

    # Süresi geçti: eldeki değer hemen döner, CRM arkada okunur.
    monkeypatch.setattr(CA, "KISI_TAZE", -1)
    assert again.get("/api/v1/categories/meta", headers=COOKIE).json()["me"]["crmId"] == "ED1"
    _bekle()
    assert crm["calls"] == 2

    # CRM kapalı, arkadaki okuma başarısız: eldeki değer kalır.
    crm["down"] = True
    assert again.get("/api/v1/categories/meta", headers=COOKIE).json()["me"]["crmId"] == "ED1"
    _bekle()


def test_crm_user_unknown_when_crm_down_and_nothing_stored(engine, monkeypatch, crm):
    crm["down"] = True
    client = _client(engine, monkeypatch, "zeynep")
    assert client.get("/api/v1/categories/meta", headers=COOKIE).json()["me"]["crmId"] is None
    assert C.meta_get(engine, T, "crm_me:zeynep") is None                      # başarısız okuma saklanmaz
    crm["down"] = False
    crm["ids"]["zeynep"] = "ED9"
    assert client.get("/api/v1/categories/meta", headers=COOKIE).json()["me"]["crmId"] == "ED9"
