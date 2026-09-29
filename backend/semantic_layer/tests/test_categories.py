"""H1 Kategori ağacı: ağaç sürümü ve iki göz onayı, düğüm doğrulaması, CRM sınıflamalarından deterministik yerleşme,
veriden taslak ağaç, tutarsızlık kuralları, profil önerisi (kapalı küme, beyan kazanır), alan alan karar ve sahiplik,
uydurma kategori reddi, CRM'e işlenecek fark, etki önizlemesi, sözleşme uçları, yetki kuralları.

Veriler yapaydır ve yalnız kuralları sınar; gerçek CRM/Logo/T-soft kabulü test sunucusunda
(`scripts/acceptance/categories/`).
"""

from __future__ import annotations

import pytest

from semantic_bridge import access as A
from semantic_bridge import categories as C
from semantic_bridge import categories_propose as CP
from semantic_layer.runtime.llm_choose import Choice
from semantic_layer.store.catalog_store import open_store

T = "t1"
M_TC, M_TY = "M-COCUK", "M-TIMAS"
K_MASAL, K_TASAVVUF = "K-MASAL", "K-TASAVVUF"
LABELS = {"hedefKitle": {"1": "Çocuk", "2": "Genç", "3": "Yetişkin"}}


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    C._ready.discard(id(e))
    C.ensure(e)
    return e


def _book(bid, *, ad, marka=M_TC, kitaplik=K_MASAL, hedef=1, web="Çocuk;6 - 10 Yaş Öykü Hikaye", yas=(6, 10),
          tur=("Masal",), tema=(), kw=(), ozet=True, editor="ED1", stok=None, urun=("U1",), ean=None):
    kl = {K_MASAL: "Masal Kitaplığı", K_TASAVVUF: "Tasavvuf"}.get(kitaplik)
    root, _, sub = (web or "").partition(";")
    return {
        "id": bid, "stok": stok or f"S-{bid}", "ad": ad, "isbn": None, "ean": ean, "yazar": "Yazar",
        "kitaplik": {"id": kitaplik, "name": kl} if kitaplik else None, "dizi": None,
        "marka": {"id": marka, "name": {M_TC: "Timaş Çocuk", M_TY: "Timaş Yayınları"}[marka]} if marka else None,
        "hedefKitle": {"code": hedef, "label": LABELS["hedefKitle"][str(hedef)]} if hedef else None,
        "yas": {"bas": yas[0], "bit": yas[1]} if yas else None, "yasMetni": None, "turMetni": None, "rafTuru": None,
        "web": web, "webRoot": root or None, "webSub": sub or None,
        "editor": {"id": editor, "name": "Editör"} if editor else None, "yonetmen": None, "tsoftAktif": True,
        "ozetVar": ozet, "spotVar": False, "olusturma": "2026-01-01T00:00:00", "degisme": None,
        "urunkategorisi": [{"id": u, "name": f"Ürün {u}"} for u in urun], "raf": [], "sergilenecek": [],
        "tema": [{"id": t, "name": t} for t in tema], "anahtarkelime": [{"id": k, "name": k} for k in kw],
        "tur": [{"id": t, "name": t} for t in tur],
    }


def _crm(books):
    vocab = {"tur": {"T1": {"id": "T1", "name": "Masal", "active": True}, "T2": {"id": "T2", "name": "Roman", "active": True}},
             "tema": {"H1": {"id": "H1", "name": "Doğa", "active": True}, "H2": {"id": "H2", "name": "Dostluk", "active": True}},
             "anahtarkelime": {"A1": {"id": "A1", "name": "orman", "active": True}, "A2": {"id": "A2", "name": "tavşan", "active": True}}}
    return {"books": {b["id"]: b for b in books}, "vocab": vocab, "labels": LABELS}


def _seed(engine, books=None):
    books = books or [
        _book("B1", ad="Masal 1"), _book("B2", ad="Masal 2"), _book("B3", ad="Masal 3", web="Çocuk;0 - 5 Yaş"),
        _book("B4", ad="Yetişkin Tasavvuf", marka=M_TY, kitaplik=K_TASAVVUF, hedef=3, web="Yetişkin;Tasavvuf", yas=None,
              tur=("Roman",), editor="ED2"),
        _book("B5", ad="Çelişkili", marka=M_TY, kitaplik=None, hedef=3, web="Çocuk;6 - 10 Yaş Öykü Hikaye", yas=(6, 10),
              tur=(), ozet=False, urun=()),
    ]
    priority = {"byCode": {"S-B1": 500, "S-B2": 10, "S-B4": 50}, "start": "2024-08-17", "end": "2026-08-17", "months": 24}
    return C.apply_sync(engine, T, _crm(books), priority, {"products": {}, "categories": {}, "syncedAt": None})


def _tree(engine, actor="ayse"):
    """Timaş Çocuk → Çocuk → Masal Kitaplığı → 6-10 Yaş; Timaş Yayınları → Yetişkin → Tasavvuf."""
    nodes = [
        {"id": "n_tc", "parentId": None, "level": "yayinevi", "name": "Timaş Çocuk"},
        {"id": "n_c", "parentId": "n_tc", "level": "ana", "name": "Çocuk"},
        {"id": "n_masal", "parentId": "n_c", "level": "alt", "name": "Masal"},
        {"id": "n_610", "parentId": "n_masal", "level": "altalt", "name": "6 - 10 Yaş Öykü Hikaye"},
        {"id": "n_ty", "parentId": None, "level": "yayinevi", "name": "Timaş Yayınları"},
        {"id": "n_y", "parentId": "n_ty", "level": "ana", "name": "Yetişkin"},
        {"id": "n_tas", "parentId": "n_y", "level": "alt", "name": "Tasavvuf"},
    ]
    maps = [
        {"nodeId": "n_tc", "system": "marka", "externalId": M_TC, "externalName": "Timaş Çocuk"},
        {"nodeId": "n_c", "system": "hedef_kitle", "externalId": "1", "externalName": "Çocuk"},
        {"nodeId": "n_masal", "system": "crm_kitaplik", "externalId": K_MASAL, "externalName": "Masal Kitaplığı"},
        {"nodeId": "n_610", "system": "crm_webkategori", "externalId": "6 - 10 Yaş Öykü Hikaye"},
        {"nodeId": "n_ty", "system": "marka", "externalId": M_TY, "externalName": "Timaş Yayınları"},
        {"nodeId": "n_y", "system": "hedef_kitle", "externalId": "3", "externalName": "Yetişkin"},
        {"nodeId": "n_tas", "system": "crm_kitaplik", "externalId": K_TASAVVUF, "externalName": "Tasavvuf"},
    ]
    C.save_draft(engine, T, actor, {"nodes": nodes, "mappings": maps, "note": "ilk"})
    C.submit(engine, T, actor)
    C.decide_tree(engine, T, "mehmet", True, None, None)
    C.reresolve(engine, T)


# ------------------------------------------------------------------ ağaç


def test_tree_validation_refuses_bad_shapes(engine):
    with pytest.raises(C.CategoryError, match="adı boş"):
        C.save_draft(engine, T, "a", {"nodes": [{"id": "x", "level": "ana", "name": " "}]})
    with pytest.raises(C.CategoryError, match="altında olmalı"):
        C.save_draft(engine, T, "a", {"nodes": [{"id": "p", "level": "alt", "name": "P"},
                                                {"id": "c", "parentId": "p", "level": "ana", "name": "C"}]})
    with pytest.raises(C.CategoryError, match="kardeş"):
        C.save_draft(engine, T, "a", {"nodes": [{"id": "p", "level": "yayinevi", "name": "P"},
                                                {"id": "c1", "parentId": "p", "level": "ana", "name": "Çocuk"},
                                                {"id": "c2", "parentId": "p", "level": "ana", "name": "çocuk"}]})
    with pytest.raises(C.CategoryError, match="üst düğümü listede yok"):
        C.save_draft(engine, T, "a", {"nodes": [{"id": "c", "parentId": "yok", "level": "ana", "name": "C"}]})


def test_two_eyes_and_versions(engine):
    _tree(engine)
    live = C.in_force(engine, T)
    assert live["status"] == "yururlukte" and live["approvedBy"] == "mehmet"
    # Yeni taslak yürürlükteki ağacın kopyası, düğüm kimlikleri aynı.
    st = C.open_draft(engine, T, "ayse")
    assert {n["id"] for n in st["draft"]["nodes"]} == {n["id"] for n in st["inForce"]["nodes"]}
    C.submit(engine, T, "ayse")
    with pytest.raises(C.CategoryError, match="gönderen"):
        C.decide_tree(engine, T, "AYSE", True, None, None)
    with pytest.raises(C.CategoryError, match="gerekçe"):
        C.decide_tree(engine, T, "mehmet", False, None, "")
    with pytest.raises(C.CategoryError, match="onaydan geri"):
        C.save_draft(engine, T, "ayse", {"nodes": []})
    C.decide_tree(engine, T, "mehmet", True, None, "tamam")
    versions = C.tree_versions(engine, T)
    assert [v["status"] for v in versions] == ["yururlukte", "arsiv"]


# ------------------------------------------------------------------ yerleşme ve kurallar


def test_resolution_is_deterministic_and_respects_brand(engine):
    _seed(engine)
    _tree(engine)
    ctx = C.tree_ctx(engine, C.in_force(engine, T))
    b1 = C.loads(C.get_profile(engine, T, "B1")["crm_snapshot_json"], {})
    r = C.resolve(ctx, b1)
    assert r["nodeId"] == "n_610"                           # Kitaplık + web alt kategorisi → torun
    b3 = C.loads(C.get_profile(engine, T, "B3")["crm_snapshot_json"], {})
    assert C.resolve(ctx, b3)["nodeId"] == "n_masal"       # web alt kategorisi ağaçta yok → Kitaplık düğümü
    # Aynı Kitaplık başka markada: marka koşulu düğümü eler
    other = {**b1, "marka": {"id": M_TY, "name": "Timaş Yayınları"}}
    assert C.resolve(ctx, other)["nodeId"] is None
    b5 = C.loads(C.get_profile(engine, T, "B5")["crm_snapshot_json"], {})
    assert C.resolve(ctx, b5)["nodeId"] is None


def test_book_detail_says_which_logo_window_the_priority_covers(engine):
    """«Son N ay» puanı son eşitlemenin penceresiyle hesaplanır; ekran bitiş tarihini bu pencereden yazar."""
    _seed(engine)
    _tree(engine)
    d = C.book_detail(engine, T, "B1")
    assert d["priority"] == 500 and d["priorityWindow"] == {"start": "2024-08-17", "end": "2026-08-17", "months": 24}


def test_findings_rules(engine):
    _seed(engine)
    _tree(engine)
    out = C.list_findings(engine, T, status="acik")
    by = {(f["bookId"], f["rule"]) for f in out["items"]}
    assert ("B5", "hedef_kitle_web") in by                 # Yetişkin kart, Çocuk web kategorisi
    assert ("B5", "yas_hedef_kitle") in by                 # Yetişkin ama bitiş yaşı 10
    assert ("B5", "kitaplik_bos") in by and ("B5", "tur_bos") in by and ("B5", "ozet_bos") in by
    assert ("B5", "urun_kategorisi_yok") in by and ("B5", "agacta_karsiligi_yok") in by
    assert not any(b == "B1" for b, _ in by)
    # Kural kapatılınca bulgusu kapanır («düzeltildi»), yoksay kararı korunur
    f = next(x for x in out["items"] if x["bookId"] == "B5" and x["rule"] == "ozet_bos")
    C.set_finding_status(engine, T, "ayse", f["id"], "yoksay", "bilerek boş")
    C.update_rule(engine, T, "ayse", "kitaplik_bos", {"enabled": False})
    C.reresolve(engine, T)
    left = {(x["bookId"], x["rule"]) for x in C.list_findings(engine, T, status="acik")["items"]}
    assert ("B5", "kitaplik_bos") not in left and ("B5", "ozet_bos") not in left
    ign = C.list_findings(engine, T, status="yoksay")["items"]
    assert [x["rule"] for x in ign] == ["ozet_bos"]
    with pytest.raises(C.CategoryError, match="parametresi değil"):
        C.update_rule(engine, T, "ayse", "yas_hedef_kitle", {"params": {"x": 1}})


def test_suggest_draft_from_data(engine, monkeypatch):
    monkeypatch.setenv("CATEGORY_TREE_MIN_BOOKS", "2")
    books = [_book(f"C{i}", ad=f"Masal {i}") for i in range(3)] + [
        _book(f"Y{i}", ad=f"Tasavvuf {i}", marka=M_TY, kitaplik=K_TASAVVUF, hedef=3, web=None, yas=None) for i in range(2)]
    books.append(_book("TEK", ad="Tek", marka=M_TY, kitaplik=K_MASAL, hedef=2, web=None))   # eşik altı grup
    C.apply_sync(engine, T, _crm(books), None, None)
    st = C.suggest_draft(engine, T, "ayse")
    names = {n["path"] for n in st["draft"]["nodes"]}
    assert "Timaş Çocuk > Çocuk > Masal Kitaplığı" in names
    assert "Timaş Yayınları > Yetişkin > Tasavvuf" in names
    assert not any("Genç" in p for p in names)
    assert st["suggestion"]["skipped"]["az"] == 1 and st["suggestion"]["placed"] == 5
    # Model kullanmayan taslak «Zeki AI» adını taşımaz (2026-09-28 AI fırsatları, hemen-düzelt 3).
    assert st["draft"]["note"].startswith("Veriden taslak (kurala göre)") and "Zeki" not in st["draft"]["note"]
    with pytest.raises(C.CategoryError, match="üzerine yazmak"):
        C.suggest_draft(engine, T, "ayse")


# ------------------------------------------------------------------ öneri


class FakeLlm:
    """Her soruda `pick(prompt, choices)` seçimini döndürür; olasılık 0,9 / geri kalanı eşit."""

    def __init__(self, pick):
        self.pick, self.asked = pick, []

    def choose(self, prompt, choices, system=None, user_id=None):
        self.asked.append((prompt, list(choices)))
        c = self.pick(prompt, choices)
        if c is None:
            return Choice(None, None, None, "none")
        rest = (1 - 0.9) / max(1, len(choices) - 1)
        probs = {x: (0.9 if x == c else rest) for x in choices} if len(choices) > 1 else {c: 1.0}
        return Choice(c, choices.index(c), probs, "logprobs" if len(choices) > 1 else "single",
                      margin=0.9 - rest if len(choices) > 1 else 1.0, coverage=1.0)


def _proposer(engine, llm):
    tree = C.in_force(engine, T)
    ctx = C.tree_ctx(engine, tree)
    stats = CP.corpus_stats(C.all_snapshots(engine, T), ctx)
    th = {"minProb": 0.7, "minMargin": 0.3, "coShare": 0.25}
    return CP.Proposer(llm, ctx, vocab=_crm([])["vocab"], labels=LABELS, stats=stats, th=th)


def test_declared_values_win_and_model_is_not_asked(engine):
    _seed(engine)
    _tree(engine)
    llm = FakeLlm(lambda p, c: c[0])
    b1 = C.loads(C.get_profile(engine, T, "B1")["crm_snapshot_json"], {})
    out = _proposer(engine, llm).run(b1, {"ozet": "Kısa bir masal."}, [])
    assert out["kategori"]["proposed"] == "n_610" and out["kategori"]["method"] == "beyan"
    assert out["hedef_kitle"]["proposed"] == "Çocuk" and out["tur"]["proposed"] == ["Masal"]
    assert out["yas"]["proposed"] == "6-10"
    assert llm.asked == []


def test_model_walks_the_tree_only_inside_the_closed_set(engine):
    _seed(engine)
    _tree(engine)
    b5 = C.loads(C.get_profile(engine, T, "B5")["crm_snapshot_json"], {})
    llm = FakeLlm(lambda p, c: "Yetişkin" if "Yetişkin" in c else ("Tasavvuf" if "Tasavvuf" in c else c[0]))
    out = _proposer(engine, llm).run(b5, {"ozet": "Tasavvuf üzerine."}, [])
    k = out["kategori"]
    assert k["proposed"] == "n_tas" and k["confident"] is True and k["method"] == "logprobs"
    # İlk soru markanın düğümünden başlar (Timaş Yayınları'nın çocukları + «üstte kal»)
    assert llm.asked[0][1] == ["Yetişkin", CP.STAY]
    # Tür boş → CRM tür sözlüğünden seçilir; uydurma değer yok
    assert out["tur"]["proposed"][0] in {"Masal", "Roman"}


def test_low_confidence_is_marked_and_not_bulk_accepted(engine):
    _seed(engine)
    _tree(engine)

    class Unsure(FakeLlm):
        def choose(self, prompt, choices, system=None, user_id=None):
            self.asked.append((prompt, list(choices)))
            p = 1 / len(choices)
            return Choice(choices[0], 0, {x: p for x in choices}, "logprobs", margin=0.0, coverage=1.0)

    b5 = C.loads(C.get_profile(engine, T, "B5")["crm_snapshot_json"], {})
    out = _proposer(engine, Unsure(None)).run(b5, {}, [])
    assert out["kategori"]["confident"] is False and out["kategori"]["proposed"] == "n_y"   # ilk düzeyde durdu
    assert out["tur"]["confident"] is False and out["hedef_kitle"]["method"] == "beyan"
    C.store_proposal(engine, T, "B5", out, "Zeki AI")
    res = C.decide(engine, T, "yy", "B5", {"all": "kabul"}, me_crm_id=None, everyone=True)
    assert res["fields"]["kategori"]["state"] == "oneri" and res["fields"]["tur"]["state"] == "oneri"
    assert res["fields"]["hedef_kitle"]["state"] == "kabul" and res["status"] == "kismi"


def test_theme_candidates_come_from_text_and_are_evidenced(engine):
    _seed(engine)
    _tree(engine)
    b1 = C.loads(C.get_profile(engine, T, "B1")["crm_snapshot_json"], {})
    llm = FakeLlm(lambda p, c: "evet" if "«Doğa»" in p or "«orman»" in p else "hayır")
    out = _proposer(engine, llm).run(b1, {"ozet": "Ormanda yaşayan küçük bir tavşan doğa ile dost olur. orman çok güzel."},
                                     ["orman", "tavşan"])
    assert out["tema"]["proposed"] == ["Doğa"]
    assert out["tema"]["evidence"][0]["kind"] == "metin" and "doğa" in out["tema"]["evidence"][0]["text"].lower()
    assert out["etiket"]["proposed"] == ["orman"]


# ------------------------------------------------------------------ karar, sahiplik, fark


def test_decision_ownership_and_no_invented_category(engine):
    _seed(engine)
    _tree(engine)
    C.store_proposal(engine, T, "B1", {"kategori": {"proposed": "n_610", "source": "CRM beyanı", "method": "beyan",
                                                    "confident": True}}, "Zeki AI")
    with pytest.raises(C.CategoryError, match="editörü ya da yayın yönetmeni") as e:
        C.decide(engine, T, "zeynep", "B1", {"all": "kabul"}, me_crm_id="ED2", everyone=False)
    assert e.value.status == 403
    with pytest.raises(C.CategoryError, match="etkin bir düğümü"):
        C.decide(engine, T, "ed", "B1", {"fields": {"kategori": {"action": "duzeltme", "value": "uydurma"}}},
                 me_crm_id="ED1", everyone=False)
    out = C.decide(engine, T, "ed", "B1", {"all": "kabul"}, me_crm_id="ed1", everyone=False)
    assert out["status"] == "onayli" and out["nodeId"] == "n_610"
    ev = [e for e in out["events"] if e["action"] == "kabul"]
    assert ev and ev[0]["user"] == "ed"


def test_partial_approval_and_crm_diff(engine):
    _seed(engine)
    _tree(engine)
    C.store_proposal(engine, T, "B5", {
        "kategori": {"proposed": "n_tas", "source": "Zeki AI", "method": "logprobs", "confident": True, "probability": 0.9},
        "tur": {"proposed": ["Roman"], "source": "Zeki AI", "method": "logprobs", "confident": True},
        "hedef_kitle": {"proposed": "Yetişkin", "source": "CRM beyanı", "method": "beyan", "confident": True},
    }, "Zeki AI")
    out = C.decide(engine, T, "yy", "B5", {"fields": {"kategori": {"action": "kabul"}}}, me_crm_id=None, everyone=True)
    assert out["status"] == "kismi"
    diff = C.crm_diff(engine, T)
    rows = [(x["bookId"], x["crmField"], x["portalValue"]) for x in diff["items"]]
    assert ("B5", "Kitaplık", "Tasavvuf") in rows            # düğümün CRM Kitaplık karşılığı yazılır
    C.decide(engine, T, "yy", "B5", {"fields": {"tur": {"action": "kabul"}, "hedef_kitle": {"action": "ret"}}},
             me_crm_id=None, everyone=True)
    diff = C.crm_diff(engine, T)
    assert ("B5", "Tür", "Roman") in [(x["bookId"], x["crmField"], x["portalValue"]) for x in diff["items"]]
    assert C.get_profile(engine, T, "B5")["status"] == "onayli"
    data = C.crm_diff_xlsx(diff, "yy")
    assert data[:2] == b"PK"


def test_impact_preview_lists_moves_orphans_and_m2(engine):
    _seed(engine)
    _tree(engine)
    C.store_proposal(engine, T, "B4", {"kategori": {"proposed": "n_tas", "source": "CRM", "method": "beyan", "confident": True}}, "x")
    C.decide(engine, T, "yy", "B4", {"all": "kabul"}, me_crm_id=None, everyone=True)
    st = C.open_draft(engine, T, "ayse")
    nodes = [n for n in st["draft"]["nodes"] if n["id"] not in ("n_tas",)]
    C.save_draft(engine, T, "ayse", {"nodes": [{k: n[k] for k in ("id", "parentId", "level", "name", "code", "sort", "status")}
                                              for n in nodes]})
    imp = C.impact(engine, T)
    assert any(r["nodeId"] == "n_tas" for r in imp["removed"])
    assert [o["bookId"] for o in imp["orphanedApproved"]] == ["B4"]
    assert imp["books"]["lost"] >= 1


def test_contract_profile_and_node_books(engine):
    _seed(engine)
    _tree(engine)
    p = C.profile_by_stock(engine, T, "S-B1")
    assert p["fields"]["kategori"]["source"] == "crm" and p["fields"]["kategori"]["path"].endswith("6 - 10 Yaş Öykü Hikaye")
    nb = C.node_books(engine, T, "n_tc")
    assert nb["total"] == 3 and nb["items"][0]["bookId"] == "B1"      # satış önceliğine göre
    assert C.m2_node_for(engine, T, kitaplik_id=K_TASAVVUF.lower())["id"] == "n_tas"


def test_queue_order_owner_and_filters(engine):
    _seed(engine)
    q = C.list_books(engine, T)
    assert [x["bookId"] for x in q["items"]][:3] == ["B1", "B4", "B2"] and q["total"] == 5
    assert C.list_books(engine, T, owner="ED2")["total"] == 1
    assert C.list_books(engine, T, kitaplik="bos")["total"] == 1
    assert C.list_books(engine, T, selling="1")["total"] == 3
    assert C.list_books(engine, T, finding="hedef_kitle_web")["items"][0]["bookId"] == "B5"


def test_book_goes_inactive_when_it_leaves_crm(engine):
    _seed(engine)
    C.apply_sync(engine, T, _crm([_book("B1", ad="Masal 1")]), None, None)
    assert C.list_books(engine, T)["total"] == 1
    assert C.get_profile(engine, T, "B2")["active"] is False


# ------------------------------------------------------------------ yetki


def test_access_rules_for_categories():
    assert A.rule_for("/api/v1/categories/overview") == {"sayfa:kategori-agaci"}
    assert A.rule_for("/api/v1/categories/run-due") == A.SYSTEM
    assert "sayfa:editor-atama" in A.rule_for("/api/v1/categories/profile/15201.01.1")
    assert "sayfa:seo-geo" in A.rule_for("/api/v1/categories/nodes/n1/books")
    f = A.features_for
    assert f("POST", "/api/v1/categories/books/B1/propose") == ["ozellik:kategori.oneri-uret"]
    assert f("PUT", "/api/v1/categories/tree") == ["ozellik:kategori.agac-duzenle"]
    assert f("POST", "/api/v1/categories/tree/submit") == ["ozellik:kategori.agac-duzenle"]
    assert f("POST", "/api/v1/categories/tree/approve") == []            # açıkça verilen, ucun içinde
    assert f("POST", "/api/v1/categories/books/B1/decision") == []       # açıkça verilen, ucun içinde
    assert f("GET", "/api/v1/categories/crm-diff/export.xlsx") == ["ozellik:veri.disa-aktar"]
    assert f("GET", "/api/v1/categories/tree") == []
    explicit = A.explicit_keys()
    assert {"ozellik:kategori.agac-onay", "ozellik:kategori.profil-onay", "ozellik:kategori.herkesinki"} <= explicit
    assert "ozellik:kategori.oneri-uret" not in explicit
