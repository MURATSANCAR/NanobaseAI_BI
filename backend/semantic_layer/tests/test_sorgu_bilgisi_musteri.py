"""M38 Müşteri ilişkileri: her rakamın sorgu bilgisi. Ekran rakamları gece turunun cari/aksiyon/bulgu/puan/segment
tablolarından (portal ifadesi), tabloları dolduran Logo/CRM SQL'i gece turunda ÇALIŞAN metin (tur kaydında, köken);
cari ayrıntısı ve aylık grafik o istekte çalışan metinle; değer, risk, segment, etki ve sağlık puanı formülle."""
from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from semantic_bridge import field_sales_sources as S
from semantic_bridge import musteri as M
from semantic_bridge import musteri_kaynak as K
from semantic_bridge import musteri_sources as MS
from semantic_bridge import provenance as P
from semantic_bridge.management.kaynak import is_template
from semantic_layer.tests.test_musteri import USERS, T, _data, engine  # noqa: F401 — fikstür

SCHEMA = "Timas_MSCRM.dbo"


def _check(out):
    k = out["kaynaklar"]
    assert not k.get("error"), k
    assert P.uncovered_numbers(out, K.NOT_RAKAM) == []
    assert P.problems(out) == []
    for s in k["sources"].values():
        assert s["sql"].strip() and P.placeholders_left(s["sql"]) == [] and not is_template(s["sql"])
        assert s["connection"] in ("logo", "crm", "portal")
        assert "gizli-parola" not in s["sql"]
    return k


class _Conn:
    def __init__(self, name: str):
        self.cfg = {"database": "CRMDB" if name == "crm" else "LOGODB", "password": "gizli-parola"}

    def execute(self, sql, limit):
        if S.query_tag(sql) == "crm.kullanicilar":
            return ["x"], [dict(u) for u in USERS], False
        return ["x"], [], False

    def close(self):
        pass


def _night(source):
    kesim = date(2026, 8, 17)
    source.logo(lambda run: [run(q) for q in ("SELECT FIRMNR, BEGDATE, ENDDATE FROM L_CAPIPERIOD", S.data_end_sql("411"),
                                              S.clients_sql("411"), S.clients_sql("211"),
                                              MS.daily_sales_sql("211", date(2024, 4, 21), date(2025, 12, 31)),
                                              MS.daily_sales_sql("411", date(2026, 1, 1), kesim),
                                              MS.all_client_codes_sql("411"))])
    source.crm(lambda run: [run(q) for q in (S.crm_users_sql(SCHEMA), MS.crm_all_users_sql(SCHEMA), S.crm_accounts_sql(SCHEMA),
                                             MS.crm_health_accounts_sql(SCHEMA), MS.crm_last_orders_sql(SCHEMA, date(2025, 9, 28)),
                                             MS.crm_contact_consent_sql(SCHEMA))])
    return _data()


def _app(engine, monkeypatch):  # noqa: F811
    from fastapi import FastAPI, Request

    from semantic_bridge import musteri_api

    monkeypatch.setattr(M, "read_all", lambda source, st, now=None: _night(source))

    def auth(request: Request):
        return engine, T, "ayseb", "Ayşe"

    app = FastAPI()
    musteri_api.register(app, {
        "auth": auth, "require_caller": lambda r: None, "can": lambda u, k: True, "is_admin": lambda u: True,
        "audit": lambda *a, **k: None, "conf": lambda k, d="": d, "fresh": lambda: False,
        "crm_connect": lambda: _Conn("crm"), "logo_connect": lambda: _Conn("logo"), "llm": lambda batch=None: None,
        "engine": lambda: engine, "tenant": lambda: T})
    return TestClient(app)


def test_musteri_reads_have_their_own_tags():
    assert S.query_tag(MS.daily_sales_sql("411", date(2026, 1, 1), date(2026, 8, 17))) == "logo.gunluk_satis.411.2026-01-01"
    assert S.query_tag(MS.monthly_sql("411", "120.01", date(2026, 1, 1), date(2026, 8, 17))) == "logo.aylik_cari.411.2026-01-01"
    assert S.query_tag(MS.all_client_codes_sql("411")) == "logo.cari_kodlari.411"
    assert S.query_tag(MS.crm_health_accounts_sql(SCHEMA)) == "crm.cari_saglik"
    assert S.query_tag(MS.crm_last_orders_sql(SCHEMA, date(2025, 9, 28))) == "crm.son_siparis"
    assert S.query_tag(MS.crm_user_mail_sql(SCHEMA)) == "crm.kullanici_eposta"
    assert S.query_tag(S.crm_users_sql(SCHEMA)) == "crm.kullanicilar"


def test_every_customer_screen_cites_its_queries(engine, monkeypatch):  # noqa: F811
    c = _app(engine, monkeypatch)
    r = c.post("/api/v1/musteri/run-due?tur=gece")
    assert r.status_code == 200, r.text
    assert "sorgular" not in r.json()
    assert "logo.gunluk_satis.411.2026-01-01" in {q["key"] for q in M.meta_get(engine, T, "run")["sorgular"]}
    for path in ("/api/v1/musteri/meta", "/api/v1/musteri/overview", "/api/v1/musteri/accounts",
                 "/api/v1/musteri/accounts/120.01", "/api/v1/musteri/accounts/120.01/monthly", "/api/v1/musteri/actions",
                 "/api/v1/musteri/my-portfolio", "/api/v1/musteri/health", "/api/v1/musteri/health/score-history",
                 "/api/v1/musteri/segments"):
        resp = c.get(path)
        assert resp.status_code == 200, (path, resp.text)
        _check(resp.json())
    d = c.get("/api/v1/musteri/accounts/120.01").json()
    k = d["kaynaklar"]
    assert any(s.startswith("saha.canli.logo.faturalar") for s in k["sources"])   # bu istekte çalışan Logo metni
    assert k["sources"]["musteri.cariler.cari"]["origin"]
    assert "Kayıp riski" in k["formulas"]["risk"]["text"]
    assert "sorgular" not in c.get("/api/v1/musteri/meta").json()["run"]


def test_database_path_gives_the_same_numbers_as_the_in_memory_path(engine, monkeypatch):  # noqa: F811
    """Hız (2026-09-29): gece turu liste kolonlarını yazınca özet, cari listesi ve veri sağlığı veritabanında toplar/süzer/
    sayfalar. Aynı veriyle eski yol (satırlar belleğe) ve yeni yol aynı cevabı verir; sorgu bilgisi çalışan ifadeyi gösterir."""
    c = _app(engine, monkeypatch)
    assert c.post("/api/v1/musteri/run-due?tur=gece").status_code == 200
    assert M.list_ready(M.meta_get(engine, T, "run")) and M.list_ready(M.meta_get(engine, T, "health"))
    paths = ["/api/v1/musteri/overview", "/api/v1/musteri/overview?temsilci=ayseb", "/api/v1/musteri/accounts",
             "/api/v1/musteri/accounts?sort=ad&size=2&p=2", "/api/v1/musteri/accounts?q=kitab&risk=riskli",
             "/api/v1/musteri/accounts?kanal=BAYI&sort=puan", "/api/v1/musteri/health",
             "/api/v1/musteri/health?durum=&q=a&size=2&p=2", "/api/v1/musteri/actions?temsilci=ayseb"]
    new = {p: c.get(p).json() for p in paths}
    for p in paths:
        _check(new[p])
    src_of = lambda p: set(new[p]["kaynaklar"]["sources"])  # noqa: E731
    assert {"musteri.kanallar", "musteri.bakilacak", "musteri.bakilacak_sayi"} <= src_of("/api/v1/musteri/overview")
    assert {"musteri.cariler", "musteri.cariler_toplam"} <= src_of("/api/v1/musteri/accounts")
    assert "LIMIT" in new["/api/v1/musteri/accounts"]["kaynaklar"]["sources"]["musteri.cariler"]["sql"].upper()
    assert {"musteri.bulgular", "musteri.bulgular_sayi"} <= src_of("/api/v1/musteri/health")
    for key in ("run", "health"):                                             # liste kolonlarından önceki tur kaydı
        v = M.meta_get(engine, T, key)
        v.pop("_at", None)
        v.pop("liste", None)
        M.meta_set(engine, T, key, v)
    for p in paths:
        old = c.get(p).json()
        _check(old)
        assert {k: v for k, v in old.items() if k != "kaynaklar"} == {k: v for k, v in new[p].items() if k != "kaynaklar"}, p
    assert "musteri.kanallar" not in c.get("/api/v1/musteri/overview").json()["kaynaklar"]["sources"]
