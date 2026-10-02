"""Yetki: AD grubu / OU / CRM rolü / kişi → rol → sayfa, birleşim kuralı ve köprüdeki sayfa kapısı.

Sözleşme: kişi bağlı olduğu rollerin birleşimini görür; «Herkes» giriş yapan herkese uygulanır ve kurulumda
bütün sayfaları açar (roller prod öncesi atanır); yönetici her şeyi görür; okunamayan dizin eski üyeleri
silmez; köprüdeki her uç bir kurala düşer, kuralı olmayan uç kişiye kapalıdır.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from semantic_bridge import access as A
from semantic_layer.store.catalog_store import open_store
from semantic_layer.tests.conftest import TENANT

ADMINS = {"zekiai"}


def is_admin(u: str) -> bool:
    return u in ADMINS


class FakeDirectory:
    def __init__(self):
        self.groups = {"satis_group": {"ayse", "ali"}}
        self.ous = {"ou=muhasebe,dc=timas,dc=local": {"mehmet"}}
        self.crm = {"11111111-2222-3333-4444-555555555555": {"zeynep"}}
        self.fail = False

    def group_members(self, g):
        if self.fail:
            raise RuntimeError("AD kapalı")
        return set(self.groups.get(g.lower(), set()))

    def ou_members(self, ou):
        if self.fail:
            raise RuntimeError("AD kapalı")
        return set(self.ous.get(ou.lower(), set()))

    def crm_role_members(self):
        if self.fail:
            raise RuntimeError("CRM kapalı")
        return {k: set(v) for k, v in self.crm.items()}


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    A._ready.clear()
    A.invalidate()
    A.ensure(e, TENANT)
    return e


def _narrow_everyone(engine):
    everyone = next(r for r in A.list_roles(engine, TENANT) if r["system"])
    A.save_role(engine, TENANT, "zekiai", {"name": "x", "allPerms": False, "perms": []}, everyone["id"])


def test_everyone_sees_every_page_until_roles_are_assigned(engine):
    acc = A.effective(engine, TENANT, "biri", is_admin)
    assert acc.all and acc.can("sayfa:finansal-denetim")
    roles = A.list_roles(engine, TENANT)
    assert [(r["name"], r["system"], r["allPerms"]) for r in roles] == [("Herkes", True, True)]
    A._ready.clear()
    A.ensure(engine, TENANT)                        # ikinci kurulum ikinci bir Herkes açmaz
    assert len(A.list_roles(engine, TENANT)) == 1


def test_permissions_are_the_union_of_the_bound_roles(engine):
    _narrow_everyone(engine)
    fin = A.save_role(engine, TENANT, "zekiai", {"name": "Finans", "perms": ["sayfa:finansal-denetim"]})["id"]
    seo = A.save_role(engine, TENANT, "zekiai", {"name": "Pazarlama", "perms": ["sayfa:seo-geo"]})["id"]
    A.add_binding(engine, TENANT, "zekiai", fin, {"type": "ad_group", "subject": "Satis_Group", "label": "Satis_Group"})
    A.add_binding(engine, TENANT, "zekiai", seo, {"type": "ou", "subject": "OU=Muhasebe,DC=timas,DC=local"})
    A.add_binding(engine, TENANT, "zekiai", seo, {"type": "crm_role", "subject": "11111111-2222-3333-4444-555555555555",
                                                  "label": "04-Pazarlama Uzmanı"})
    A.add_binding(engine, TENANT, "zekiai", seo, {"type": "user", "subject": "Ayse"})
    A.refresh(engine, FakeDirectory())

    ayse = A.effective(engine, TENANT, "ayse", is_admin)
    assert ayse.perms == {"sayfa:finansal-denetim", "sayfa:seo-geo"} and not ayse.all
    assert sorted(v for r in ayse.roles for v in r["via"]) == [
        "AD grubu: Satis_Group", "Giriş yapan herkes", "Kişi: ayse"]
    assert A.effective(engine, TENANT, "ali", is_admin).perms == {"sayfa:finansal-denetim"}
    assert A.effective(engine, TENANT, "mehmet", is_admin).perms == {"sayfa:seo-geo"}
    assert A.effective(engine, TENANT, "zeynep", is_admin).perms == {"sayfa:seo-geo"}
    nobody = A.effective(engine, TENANT, "yabanci", is_admin)
    assert nobody.perms == frozenset() and not nobody.can("sayfa:seo-geo")
    boss = A.effective(engine, TENANT, "zekiai", is_admin)
    assert boss.can("sayfa:finansal-denetim") and boss.view()["all"]


def test_unreadable_directory_keeps_the_last_members(engine):
    _narrow_everyone(engine)
    rid = A.save_role(engine, TENANT, "zekiai", {"name": "Finans", "perms": ["sayfa:finansal-denetim"]})["id"]
    A.add_binding(engine, TENANT, "zekiai", rid, {"type": "ad_group", "subject": "Satis_Group"})
    d = FakeDirectory()
    A.refresh(engine, d)
    d.fail = True
    out = A.refresh(engine, d)
    assert not out["ok"] and out["failed"][0]["error"].startswith("RuntimeError")
    assert A.effective(engine, TENANT, "ayse", is_admin).can("sayfa:finansal-denetim")
    bind = A.list_roles(engine, TENANT)[1]["bindings"][0]
    assert bind["members"] == 2 and "AD kapalı" in bind["error"]


def test_removing_a_binding_or_role_takes_the_pages_away(engine):
    _narrow_everyone(engine)
    rid = A.save_role(engine, TENANT, "zekiai", {"name": "Finans", "perms": ["sayfa:finansal-denetim"]})["id"]
    b = A.add_binding(engine, TENANT, "zekiai", rid, {"type": "user", "subject": "ayse"})
    assert A.effective(engine, TENANT, "ayse", is_admin).can("sayfa:finansal-denetim")
    A.delete_binding(engine, TENANT, b["id"])
    assert not A.effective(engine, TENANT, "ayse", is_admin).can("sayfa:finansal-denetim")
    A.add_binding(engine, TENANT, "zekiai", rid, {"type": "user", "subject": "ayse"})
    A.delete_role(engine, TENANT, rid)
    assert not A.effective(engine, TENANT, "ayse", is_admin).can("sayfa:finansal-denetim")


def test_invalid_changes_are_refused(engine):
    everyone = A.list_roles(engine, TENANT)[0]["id"]
    with pytest.raises(A.AccessError):
        A.delete_role(engine, TENANT, everyone)
    with pytest.raises(A.AccessError):
        A.add_binding(engine, TENANT, "zekiai", everyone, {"type": "user", "subject": "ayse"})
    with pytest.raises(A.AccessError):
        A.save_role(engine, TENANT, "zekiai", {"name": "X", "perms": ["sayfa:yok-boyle"]})
    rid = A.save_role(engine, TENANT, "zekiai", {"name": "Finans"})["id"]
    with pytest.raises(A.AccessError):
        A.save_role(engine, TENANT, "zekiai", {"name": "finans"})
    A.add_binding(engine, TENANT, "zekiai", rid, {"type": "user", "subject": "ayse"})
    with pytest.raises(A.AccessError):
        A.add_binding(engine, TENANT, "zekiai", rid, {"type": "user", "subject": "AYSE"})
    with pytest.raises(A.AccessError):
        A.add_binding(engine, TENANT, "zekiai", rid, {"type": "grup", "subject": "x"})
    # Herkes'in adı değişmez.
    A.save_role(engine, TENANT, "zekiai", {"name": "Başka", "allPerms": True}, everyone)
    assert A.list_roles(engine, TENANT)[0]["name"] == "Herkes"


def test_rules_cover_the_shared_endpoints():
    assert A.rule_for("/api/v1/financial-audit/overview") == {"sayfa:finansal-denetim"}
    assert A.rule_for("/api/v1/editorial/studio/jobs/abc/pdf/ic") == {"sayfa:kitap-tasarim", "sayfa:kitap-eczanesi"}
    assert A.rule_for("/api/v1/editorial/studio/library/covers") == {"sayfa:kapak-arsivi", "sayfa:kitap-tasarim"}
    # Kitap Eczanesi: kendi uçları yalnız kendi sayfası; redaksiyona açma ayrıca özellik ister, liste istemez.
    assert A.rule_for("/api/v1/editorial/pharmacy/books") == {"sayfa:kitap-eczanesi"}
    assert A.features_for("POST", "/api/v1/editorial/pharmacy/books/abc/redaction") == ["ozellik:kitap-eczanesi.redaksiyon"]
    assert A.features_for("GET", "/api/v1/editorial/pharmacy/books") == []
    assert "sayfa:kitap-eczanesi" in A.rule_for("/api/v1/editorial/proofing/word-alternatives")
    assert "sayfa:kisiler" in A.rule_for("/api/v1/editorial/contributors")
    assert A.rule_for("/api/v1/editorial/web/status") == A.OPEN
    assert A.rule_for("/api/v1/board/run-due") == A.SYSTEM
    assert A.rule_for("/api/v1/board") == {"sayfa:panolar", "sayfa:genel-bakis"}
    assert A.rule_for("/api/v1/access/me") == A.OWN
    assert A.rule_for("/api/v1/bilinmeyen") is None


# ------------------------------------------------------------------ köprü


def _app(monkeypatch, store, settings):
    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod
    from semantic_bridge.app import Runtime, create_app
    from semantic_layer.candidates.llm_client import FakeLlm

    users = {"timas_session=a": "ayse", "timas_session=z": "zekiai", "timas_session=m": "mehmet"}
    monkeypatch.setattr(board_mod, "_fetch_user", lambda cookie: users.get(cookie))
    monkeypatch.setattr(board_mod, "_fetch_session", lambda cookie: {"username": users.get(cookie), "displayName": "x"})
    monkeypatch.setattr(admin_mod, "admins", lambda: ["zekiai"])
    monkeypatch.delenv("SEMANTIC_CALLER_TOKEN", raising=False)
    monkeypatch.delenv("SEMANTIC_ADMIN_TOKEN", raising=False)
    A._ready.clear()
    A.invalidate()
    app = create_app(Runtime(settings, store=store, llm=FakeLlm([""])))
    return app, TestClient(app)


def test_every_bridge_route_has_a_rule(monkeypatch, store, settings):
    app, _ = _app(monkeypatch, store, settings)
    paths = {getattr(r, "path", "") for r in app.routes}
    missing = sorted(p for p in paths if p.startswith(("/api/", "/health")) and A.rule_for(p) is None)
    assert missing == []


def test_no_bridge_route_takes_request_as_query(monkeypatch, store, settings):
    """`from __future__ import annotations` + fonksiyon içinde içe aktarılan `Request` → FastAPI `request`i sorgu
    parametresi sanar, uç her istekte 422 döner (SEO rehberi 2026-09-27, M12 Üretim 2026-09-28 canlıda böyle çıktı)."""
    app, _ = _app(monkeypatch, store, settings)
    bad = []
    for route in app.routes:
        dep = getattr(route, "dependant", None)
        for q in (dep.query_params if dep is not None else []):
            if q.name in ("request", "body") or q.name[:1].isupper():
                bad.append(f"{sorted(route.methods)} {route.path}: {q.name}")
    assert bad == []


def test_page_gate_in_the_bridge(monkeypatch, store, settings):
    app, client = _app(monkeypatch, store, settings)
    engine = store.engine
    A.ensure(engine, TENANT)
    # Kurulumda herkes her şeyi görür: kapı kimseyi durdurmaz.
    assert client.get("/api/v1/financial-audit/catalog", headers={"cookie": "timas_session=a"}).status_code != 403
    _narrow_everyone(engine)
    rid = A.save_role(engine, TENANT, "zekiai", {"name": "Finans", "perms": ["sayfa:finansal-denetim"]})["id"]
    A.add_binding(engine, TENANT, "zekiai", rid, {"type": "user", "subject": "mehmet"})
    A.invalidate()

    denied = client.get("/api/v1/financial-audit/catalog", headers={"cookie": "timas_session=a"})
    assert denied.status_code == 403 and denied.json()["detail"]["code"] == "FORBIDDEN"
    assert client.get("/api/v1/financial-audit/catalog", headers={"cookie": "timas_session=m"}).status_code != 403
    assert client.get("/api/v1/financial-audit/catalog", headers={"cookie": "timas_session=z"}).status_code != 403
    # Çerezsiz (zamanlayıcı/betik) istek kapıdan geçer; kişi zamanlayıcı ucunu tetikleyemez.
    assert client.get("/api/v1/financial-audit/catalog").status_code != 403
    assert client.post("/api/v1/board/run-due", headers={"cookie": "timas_session=a"}).status_code == 403
    # Ortak uç (Kampüs rehberi, menü) oturumla açık kalır.
    me = client.get("/api/v1/access/me", headers={"cookie": "timas_session=a"}).json()
    assert me["perms"] == [] and me["all"] is False and me["roles"][0]["name"] == "Herkes"
    assert client.get("/api/v1/access/me", headers={"cookie": "timas_session=m"}).json()["perms"] == ["sayfa:finansal-denetim"]


def test_access_admin_endpoints(monkeypatch, store, settings):
    app, client = _app(monkeypatch, store, settings)
    z = {"cookie": "timas_session=z"}
    assert client.get("/api/v1/access/roles", headers={"cookie": "timas_session=a"}).status_code == 403
    made = client.post("/api/v1/access/roles", json={"name": "Editör", "perms": ["sayfa:editoryal"]}, headers=z)
    assert made.status_code == 201
    rid = made.json()["id"]
    b = client.post(f"/api/v1/access/roles/{rid}/bindings", json={"type": "user", "subject": "ayse", "label": "Ayşe"}, headers=z)
    assert b.status_code == 201
    roles = client.get("/api/v1/access/roles", headers=z).json()["items"]
    ed = next(r for r in roles if r["id"] == rid)
    assert ed["perms"] == ["sayfa:editoryal"] and ed["bindings"][0]["label"] == "Ayşe"
    bad = client.post("/api/v1/access/roles", json={"name": "editör"}, headers=z)
    assert bad.status_code == 422 and "zaten var" in bad.json()["detail"]["message"]
    assert client.delete(f"/api/v1/access/bindings/{b.json()['id']}", headers=z).json() == {"ok": True}
    assert client.delete(f"/api/v1/access/roles/{rid}", headers=z).json() == {"ok": True}
    from semantic_bridge import admin as admin_mod
    kinds = [row["kind"] for row in admin_mod.audit_list(store.engine)["items"]]
    assert kinds.count("access") == 4


# ------------------------------------------------------------------ ekran özellikleri (Aşama B)


def test_all_role_does_not_carry_the_explicit_features(engine):
    everyone = A.effective(engine, TENANT, "biri", is_admin)
    assert everyone.can("ozellik:pano.duzenle", "ozellik:tasarim.uret") and everyone.can("ozellik:tasarim.uret")
    for key in A.explicit_keys():
        assert not everyone.can(key), key          # kurulumda kimsenin yöneticiye özel yetkisi genişlemez
    assert A.explicit_keys() >= {"ozellik:oda.yonet", "ozellik:masa.herkesinki", "ozellik:yazar-giris.herkesinki",
                                 "ozellik:yayin-kurulu.gorusler", "ozellik:seo.onay", "ozellik:sohbet.yonet"}
    # Sohbet yönetimi: giriş servisi /api/v1/access/me'den okur; Herkes'in «bütün yetkiler»i sohbeti yönetici yapmaz,
    # portal yöneticisi (admin) her şeyi gördüğü gibi bunu da taşır.
    assert "ozellik:sohbet.yonet" not in everyone.view()["perms"]
    assert "ozellik:sohbet.yonet" in A.effective(engine, TENANT, "zekiai", is_admin).view()["perms"]
    rid = A.save_role(engine, TENANT, "zekiai", {"name": "Kurul", "perms": ["ozellik:yayin-kurulu.gorusler"]})["id"]
    A.add_binding(engine, TENANT, "zekiai", rid, {"type": "user", "subject": "ayse"})
    assert A.effective(engine, TENANT, "ayse", is_admin).can("ozellik:yayin-kurulu.gorusler")
    assert A.effective(engine, TENANT, "zekiai", is_admin).can("ozellik:oda.yonet")
    view = A.effective(engine, TENANT, "ayse", is_admin).view()
    assert view["all"] is False and "ozellik:yayin-kurulu.gorusler" in view["perms"] and "ozellik:oda.yonet" not in view["perms"]


def test_feature_rules_match_the_actions_not_the_reads():
    f = A.features_for
    assert f("POST", "/api/v1/ask") == ["ozellik:zeki.soru"] and f("POST", "/api/v1/ask/stream") == ["ozellik:zeki.soru"]
    assert f("GET", "/api/v1/board") == [] and f("PUT", "/api/v1/board") == ["ozellik:pano.duzenle"]
    assert f("GET", "/api/v1/board/export.xlsx") == ["ozellik:veri.disa-aktar"]
    assert f("GET", "/api/v1/reports/r1/file") == ["ozellik:veri.disa-aktar"]
    assert f("POST", "/api/v1/reports/r1/run") == ["ozellik:rapor.planla"] and f("POST", "/api/v1/reports/run-due") == []
    assert f("DELETE", "/api/v1/alerts/a1") == ["ozellik:uyari.kural"] and f("GET", "/api/v1/alerts/a1/events") == []
    assert f("POST", "/api/v1/editorial/studio/jobs") == ["ozellik:tasarim.uret"]
    assert f("POST", "/api/v1/editorial/studio/jobs/j1/art/k/regenerate") == ["ozellik:tasarim.uret"]
    assert f("POST", "/api/v1/editorial/studio/jobs/j1/art/k/approve") == ["ozellik:tasarim.uret"]
    assert f("POST", "/api/v1/editorial/studio/jobs/j1/kunye") == ["ozellik:tasarim.uret"]
    assert f("GET", "/api/v1/financial-audit/lines") == ["ozellik:denetim.detay"]
    assert f("POST", "/api/v1/seo-geo/questions/measure") == ["ozellik:seo.calistir"]
    assert f("POST", "/api/v1/seo-geo/proposals/p1/decide") == []          # onay ucun içinde (açıkça verilen)
    assert f("POST", "/api/v1/seo-geo/bios/k1/draft") == ["ozellik:seo.oneri-uret"]
    assert f("POST", "/api/v1/seo-geo/guides") == ["ozellik:seo.oneri-uret"]
    assert f("POST", "/api/v1/seo-geo/tech/crawl") == ["ozellik:seo.calistir"]
    assert f("POST", "/api/v1/seo-geo/worklist/abc/status") == ["ozellik:seo.calistir"]
    assert f("POST", "/api/v1/seo-geo/qsuggest/q1/accept") == ["ozellik:seo.calistir"]
    assert f("GET", "/api/v1/seo-geo/worklist/export.csv") == ["ozellik:veri.disa-aktar"]
    assert f("GET", "/api/v1/seo-geo/monthly/2026-08.pdf") == ["ozellik:veri.disa-aktar"]
    assert f("GET", "/api/v1/seo-geo/worklist") == [] and f("GET", "/api/v1/seo-geo/faq/p1") == []
    assert f("POST", "/api/v1/seo-geo/bios/drafts/d1/decide") == []        # onay ucun içinde
    assert f("POST", "/api/v1/seo-geo/indexnow/submit") == []              # onay ucun içinde
    # Okunamayan kitabı yeniden okutmak GPU'da okuma başlatır: yüklemeyle aynı yetki; liste okumak yetki istemez.
    assert f("POST", "/api/v1/editorial/ask/read/j1/retry") == ["ozellik:kitap.okut"]
    assert f("POST", "/api/v1/editorial/pharmacy/books/b1/reread") == ["ozellik:kitap.okut"]
    assert f("GET", "/api/v1/editorial/ask/read") == [] and f("GET", "/api/v1/editorial/pharmacy/books/b1") == []
    keys = {k for _, _, k in A.FEATURE_RULES}
    assert keys <= A.all_keys() - A.explicit_keys()


_STUDIO_READS_BY_POST = {"/api/v1/editorial/studio/jobs/{job}/plan/prepare",      # sayfa düzeni ekranının açılışı
                         "/api/v1/editorial/studio/jobs/{job}/narration/read"}     # metnin okunuşu, kayıt yok
_STUDIO_ADMIN_ONLY = {("DELETE", "/api/v1/editorial/studio/voices/{vid}"),          # ucun içinde yalnız yönetici
                      ("POST", "/api/v1/editorial/studio/library/refresh")}
_STUDIO_EXPORTS = {"/api/v1/editorial/studio/jobs/{job}/pdf/{kind}", "/api/v1/editorial/studio/jobs/{job}/age/pdf",
                   "/api/v1/editorial/studio/jobs/{job}/plan/versions/report", "/api/v1/editorial/studio/jobs/{job}/epub/file",
                   "/api/v1/editorial/studio/jobs/{job}/marketing/product/export",
                   "/api/v1/editorial/studio/jobs/{job}/marketing/social/zip",
                   "/api/v1/editorial/studio/jobs/{job}/marketing/guide/pdf"}


def _sample(path: str) -> str:
    import re
    return re.sub(r"\{[^}]+\}", "x1", path.replace("{path:path}", "OEBPS/p1.xhtml"))


def test_every_studio_write_needs_the_studio_permission(monkeypatch, store, settings):
    """Stüdyonun her yazma ucu (pazarlama kiti, e-kitap, ses kütüphanesi, efekt, ifade, insan kaydı, boyama, kolaj,
    künye, sayfa planı…) `tasarim.uret` ister; okumalar yalnız sayfa kuralına, indirmeler `veri.disa-aktar`a bağlı.
    Yeni bir stüdyo yazma ucu eklenince kural kendiliğinden kapsar; okuma gibi davranan POST bu listeye yazılır."""
    app, _ = _app(monkeypatch, store, settings)
    writes, bad = 0, []
    for r in app.routes:
        path = getattr(r, "path", "")
        if not path.startswith("/api/v1/editorial/studio"):
            continue
        for m in sorted(getattr(r, "methods", None) or ()):
            if m in ("HEAD", "OPTIONS"):
                continue
            got = A.features_for(m, _sample(path))
            if m == "GET":
                want = ["ozellik:veri.disa-aktar"] if path in _STUDIO_EXPORTS else []
            elif path in _STUDIO_READS_BY_POST or (m, path) in _STUDIO_ADMIN_ONLY:
                want = []
            else:
                want, writes = ["ozellik:tasarim.uret"], writes + 1
            if got != want:
                bad.append(f"{m} {path}: {got} (beklenen {want})")
    assert bad == []
    assert writes >= 75            # stüdyonun yazma uçları gerçekten tarandı (2026-09-29: 80)


def test_studio_gate_keeps_viewers_read_only(monkeypatch, store, settings):
    """Yalnız sayfası olan rol stüdyoyu görür ama pazarlama/e-kitap/ses/efekt yazamaz, dosya indiremez; yetkisi
    eklenince aynı istek kapıdan geçer."""
    app, _ = _app(monkeypatch, store, settings)
    client = TestClient(app, raise_server_exceptions=False)   # kapıdan geçen istek testte stüdyo servisine ulaşamaz
    engine = store.engine
    A.ensure(engine, TENANT)
    _narrow_everyone(engine)
    rid = A.save_role(engine, TENANT, "zekiai", {"name": "Tasarım izleyici", "perms": ["sayfa:kitap-tasarim"]})["id"]
    A.add_binding(engine, TENANT, "zekiai", rid, {"type": "user", "subject": "ayse"})
    A.invalidate()
    a = {"cookie": "timas_session=a", "origin": "http://testserver"}
    calls = [("PUT", "/api/v1/editorial/studio/jobs/j1/marketing/back-cover", {"text": "x"}),
             ("POST", "/api/v1/editorial/studio/jobs/j1/epub", {"layout": "auto"}),
             ("POST", "/api/v1/editorial/studio/voices", {}),
             ("POST", "/api/v1/editorial/studio/jobs/j1/sfx/suggest", {}),
             ("PUT", "/api/v1/editorial/studio/jobs/j1/narration/pages/p1/expression", {"items": []}),
             ("GET", "/api/v1/editorial/studio/jobs/j1/epub/file", None)]
    for m, p, body in calls:
        r = client.request(m, p, json=body, headers=a)
        assert r.status_code == 403 and r.json()["detail"]["message"] == "Bu işlem rolünüzde yok.", (m, p)
    assert client.get("/api/v1/editorial/studio/jobs/j1/marketing", headers=a).status_code != 403
    A.save_role(engine, TENANT, "zekiai", {"name": "Tasarım izleyici", "perms": [
        "sayfa:kitap-tasarim", "ozellik:tasarim.uret", "ozellik:veri.disa-aktar"]}, rid)
    A.invalidate()
    for m, p, body in calls:
        assert client.request(m, p, json=body, headers=a).status_code != 403, (m, p)


def test_single_social_image_download_needs_the_export_permission(monkeypatch, store, settings):
    """Tek sosyal görselin görüntülenmesi ve indirilmesi aynı yolda (`…/social/{sid}` ve `?download=1`): kapı yola
    baktığı için ayıramaz, indirme ucun içinde `veri.disa-aktar` ister; görüntüleme yalnız sayfa yetkisiyle kalır."""
    from semantic_bridge import editorial_studio_marketing as esm

    app, client = _app(monkeypatch, store, settings)
    got: list[dict] = []

    def fake_fetch(job, sub, params=None):
        got.append(dict(params or {}))
        return b"png", "image/png", None

    monkeypatch.setattr(esm, "fetch", fake_fetch)
    engine = store.engine
    A.ensure(engine, TENANT)
    _narrow_everyone(engine)
    rid = A.save_role(engine, TENANT, "zekiai", {"name": "Tasarım izleyici", "perms": ["sayfa:kitap-tasarim"]})["id"]
    A.add_binding(engine, TENANT, "zekiai", rid, {"type": "user", "subject": "ayse"})
    A.invalidate()
    a = {"cookie": "timas_session=a"}
    url = "/api/v1/editorial/studio/jobs/j1/marketing/social/s_0123abcd"
    view = client.get(url + "?w=640", headers=a)
    assert view.status_code == 200 and "attachment" not in view.headers.get("content-disposition", "")
    denied = client.get(url + "?download=1", headers=a)
    assert denied.status_code == 403 and denied.json()["detail"]["message"] == "Bu işlem rolünüzde yok."
    assert got == [{"w": 640}]                    # yetkisiz indirme stüdyo servisine hiç gitmedi
    A.save_role(engine, TENANT, "zekiai", {"name": "Tasarım izleyici", "perms": [
        "sayfa:kitap-tasarim", "ozellik:veri.disa-aktar"]}, rid)
    A.invalidate()
    ok = client.get(url + "?download=1", headers=a)
    assert ok.status_code == 200 and "attachment" in ok.headers["content-disposition"]
    assert got[-1] == {"download": "1"}
    assert client.get(url + "?download=1", headers={"cookie": "timas_session=z"}).status_code == 200   # yönetici


def test_feature_gate_in_the_bridge(monkeypatch, store, settings):
    app, client = _app(monkeypatch, store, settings)
    engine = store.engine
    A.ensure(engine, TENANT)
    _narrow_everyone(engine)
    rid = A.save_role(engine, TENANT, "zekiai", {"name": "Pano okuyucu", "perms": ["sayfa:panolar"]})["id"]
    A.add_binding(engine, TENANT, "zekiai", rid, {"type": "user", "subject": "ayse"})
    A.invalidate()
    a = {"cookie": "timas_session=a"}
    assert client.get("/api/v1/board", headers=a).status_code != 403
    put = client.put("/api/v1/board", json={"cards": []}, headers=a)
    assert put.status_code == 403 and put.json()["detail"]["message"] == "Bu işlem rolünüzde yok."
    assert client.post("/api/v1/ask", json={"question": "x"}, headers=a).status_code == 403
    A.save_role(engine, TENANT, "zekiai", {"name": "Pano okuyucu", "perms": ["sayfa:panolar", "ozellik:pano.duzenle"]}, rid)
    A.invalidate()
    assert client.put("/api/v1/board", json={"cards": []}, headers=a).status_code != 403


# ------------------------------------------------------------------ bağ adayları: sayılar ve üye listesi


def test_ou_count_includes_sub_units_and_escaped_commas():
    """Bağlanan OU alt ağacıyla okunur (`ou_members`); listede görünen sayı da alt birimleri saymalı."""
    dns = [
        "CN=Ali,OU=Satis,OU=Merkez,DC=timas,DC=local",
        "CN=Yilmaz\\, Ayse,OU=Satis,OU=Merkez,DC=timas,DC=local",
        "CN=Mehmet,OU=Merkez,DC=timas,DC=local",
        "CN=Administrator,CN=Users,DC=timas,DC=local",
    ]
    counts = A.ou_subtree_counts(dns)
    assert counts == {"OU=Satis,OU=Merkez,DC=timas,DC=local": 2, "OU=Merkez,DC=timas,DC=local": 3}
    assert A._dn_parts(dns[1])[0] == "CN=Yilmaz\\, Ayse"


def test_group_count_follows_nested_groups_and_skips_disabled_people():
    people = {"cn=ali,ou=a,dc=x", "cn=veli,ou=a,dc=x", "cn=can,ou=a,dc=x"}
    groups = {
        "CN=Ust,OU=G,DC=x": ["CN=Ali,OU=A,DC=x", "CN=Alt,OU=G,DC=x", "CN=Kapali,OU=A,DC=x"],
        "CN=Alt,OU=G,DC=x": ["CN=Veli,OU=A,DC=x", "CN=Ali,OU=A,DC=x", "CN=Ust,OU=G,DC=x"],   # döngü
        "CN=Bos,OU=G,DC=x": [],
    }
    counts = A.nested_group_counts(groups, people)
    assert counts == {"cn=ust,ou=g,dc=x": 2, "cn=alt,ou=g,dc=x": 2, "cn=bos,ou=g,dc=x": 0}


class _MemberDirectory(A.Directory):
    def __init__(self):
        super().__init__(lambda: {}, lambda: "")

    def list_people(self):
        return [{"subject": "ali", "label": "Ali Kaya", "hint": "ali", "detail": "Satis"},
                {"subject": "ayse", "label": "Ayşe Demir", "hint": "ayse", "detail": "Satis"}]

    def group_members(self, group):
        return {"ayse", "ali"} if group == "satis_group" else set()

    def ou_members(self, ou):
        return {"ali"}

    def crm_role_members(self):
        return {"11111111-2222-3333-4444-555555555555": {"ali", "eski"}}


def test_members_of_lists_people_with_names_and_flags_unknown_accounts():
    d = _MemberDirectory()
    assert [p["label"] for p in d.members_of("ad_group", "satis_group")] == ["Ali Kaya", "Ayşe Demir"]
    assert [p["subject"] for p in d.members_of("ou", "OU=Satis,DC=timas,DC=local")] == ["ali"]
    crm = d.members_of("crm_role", "{11111111-2222-3333-4444-555555555555}")
    assert [(p["subject"], p["detail"]) for p in crm] == [("ali", "Satis"), ("eski", "AD'de etkin hesabı yok")]
    with pytest.raises(A.AccessError):
        d.members_of("ou", " ")
    with pytest.raises(A.AccessError):
        d.members_of("yok", "x")
