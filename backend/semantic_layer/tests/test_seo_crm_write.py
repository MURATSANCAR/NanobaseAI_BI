"""SEO → CRM kitap kartı yazımı: saf kurallar (alan listesi, uzunluk, alt metin, SQL). Ağ ve veritabanı yok."""
from datetime import datetime, timezone

import pytest

from semantic_bridge.seo_geo import crm_write as w

STAMP = datetime(2026, 10, 4, 9, 30, 15, 123, tzinfo=timezone.utc)


def test_alt_text_adds_author_and_respects_length():
    assert w.alt_text("Bitki Sevenler Kulübü", "Nick Arnold") == "Bitki Sevenler Kulübü – Nick Arnold kitap kapağı"
    assert w.alt_text("Nick Arnold Seçkisi", "Nick Arnold") == "Nick Arnold Seçkisi kitap kapağı"
    assert w.alt_text("", "X") == ""
    long = w.alt_text("Uzun " * 60, "Yazar")
    assert len(long) <= w.FIELDS["new_kapakalt"] and long.endswith(" kitap kapağı")


def test_build_maps_only_invisible_fields_and_skips_empty():
    f = w.build({"ProductName": "Kitap", "Model": "Yazar"},
                {"SeoTitle": "Kitap - Yazar | Timaş", "SeoDescription": "", "Details": "<p>sayfada görünür</p>",
                 "SearchKeywords": "a,b"}, STAMP)
    assert set(f) == {"new_seobaslik", "new_kapakalt", "new_seodurum", "new_seoguncelleme"}
    assert f["new_seodurum"] == w.DURUM_ONAYLANDI
    assert f["new_seoguncelleme"] == datetime(2026, 10, 4, 9, 30, 15)
    assert w.build({}, {}, STAMP) == {}


def test_build_cuts_to_crm_length():
    f = w.build({}, {"SeoDescription": "kelime " * 80}, STAMP)
    assert "new_seoaciklama" not in f  # tam cümle yok: yarım açıklama yazılmaz
    f = w.build({}, {"SeoDescription": "Bu kitap okura sade ve akıcı bir dille önemli bir konuyu anlatıyor. " * 4}, STAMP)
    assert len(f["new_seoaciklama"]) <= 160 and f["new_seoaciklama"].endswith(".")


def test_check_rejects_unlisted_and_too_long():
    w.check({"new_seobaslik": "x", "new_seodurum": 2, "new_seoguncelleme": STAMP})
    with pytest.raises(ValueError):
        w.check({"new_ozet": "arka kapak"})
    with pytest.raises(ValueError):
        w.check({"new_seobaslik": "x" * 101})


def test_sql_only_listed_columns_and_modifiedon():
    sql = w.update_sql("Timas_MSCRM.dbo.", ["new_seobaslik", "new_seodurum"])
    assert sql.startswith("UPDATE Timas_MSCRM.dbo.new_kitapBase SET new_seobaslik = ?, new_seodurum = ? WHERE")
    assert "ModifiedOn" not in sql  # mevcut kolonlara dokunulmaz
    assert sql.endswith("WHERE new_kitapId = ? AND statecode = 0")
    with pytest.raises(ValueError):
        w.update_sql("dbo.", ["new_seobaslik", "new_ozet"])
    with pytest.raises(ValueError):
        w.update_sql("dbo.", [])
    assert "new_kapakalt" in w.select_sql("dbo.")


def test_same_compares_text_fields_only():
    f = {"new_seobaslik": "A", "new_seodurum": 2}
    assert w.same(f, {"new_seobaslik": " A ", "new_seodurum": None})
    assert not w.same(f, {"new_seobaslik": None})


# ------------------------------------------------------------------ veritabanı akışı (SQLite + sahte CRM bağlantısı)
import json as _json

import sqlalchemy as _sa

from semantic_bridge.seo_geo import crm as _crm
from semantic_bridge.seo_geo.store import CRM_BOOKS, PRODUCTS, PROPOSALS, ensure

BOOK = "11111111-2222-3333-4444-555555555555"


class _Cur:
    def __init__(self, db):
        self.db, self.rowcount, self.description, self._row = db, 0, None, None

    def execute(self, sql, *args):
        self.db.sql.append((sql, args))
        if sql.startswith("SELECT"):
            cols = [*w.FIELDS, *w.TRACK]
            self.description = [(c,) for c in cols]
            self._row = tuple(self.db.card.get(c) for c in cols) if args[0] == BOOK else None
        else:
            keys = [k.split(" = ")[0].strip() for k in sql.split(" SET ")[1].split(" WHERE")[0].split(", ")]
            if args[-1] == BOOK:
                self.db.card.update(dict(zip(keys, args[:-1])))
                self.rowcount = 1

    def fetchone(self):
        return self._row


class _Conn:
    def __init__(self, db):
        self.db = db

    def cursor(self):
        return _Cur(self.db)

    def commit(self):
        self.db.commits += 1

    def rollback(self):
        pass

    def close(self):
        pass


class _Seo:
    def __init__(self, eng):
        self.eng, self.audits = eng, []

    def engine(self):
        return self.eng

    def tenant(self):
        return "t"

    def audit(self, *a):
        self.audits.append(a)


@pytest.fixture()
def env(monkeypatch):
    eng = _sa.create_engine("sqlite://")
    ensure(eng)
    db = type("DB", (), {})()
    db.card, db.sql, db.commits = {"new_seobaslik": "Eski başlık"}, [], 0
    monkeypatch.setattr(w, "_write_conn", lambda: _Conn(db))
    from semantic_bridge import admin as admin_mod
    monkeypatch.setattr(admin_mod, "conf", lambda k: {"CRM_SCHEMA": "Timas_MSCRM.dbo"}.get(k, ""))
    now = w.now()
    with eng.begin() as c:
        c.execute(PRODUCTS.insert().values(tenant_id="t", product_id="p1", name="Kitap", active=True, score=50,
                                           issues_json="[]", data_json=_json.dumps({"Barcode": "978-1", "ProductName": "Kitap", "Model": "Yazar",
                                                                                    "SeoTitle": "Kitap - Yazar | Timaş", "Brand": "Timaş"}), synced_at=now))
        c.execute(CRM_BOOKS.insert().values(tenant_id="t", ean="9781", book_id=BOOK, rights="var", data_json="{}", synced_at=now))
        c.execute(PROPOSALS.insert().values(id="pr1", tenant_id="t", product_id="p1", status="onaylandi",
                                            fields_json=_json.dumps({"SeoTitle": "Kitap - Yazar | Timaş", "SeoDescription": "Bu kitap okura sade ve akıcı bir dille önemli bir konuyu anlatıyor."}),
                                            before_json="{}", created_at=now, decided_at=now))
    return _Seo(eng), db, monkeypatch


def test_deneme_records_without_writing(env):
    seo, db, mp = env
    mp.setattr(w, "mode", lambda: "deneme")
    stats = w.run(seo, approve_ready=False, write=False, log_line=lambda s: None)
    assert stats["deneme"] == 1 and db.commits == 0 and db.card["new_seobaslik"] == "Eski başlık"
    item = w.listing(seo)["items"][0]
    assert item["status"] == "deneme" and item["name"] == "Kitap" and item["before"]["new_seobaslik"] == "Eski başlık"
    assert item["fields"]["new_kapakalt"] == "Kitap – Yazar kitap kapağı"
    with pytest.raises(RuntimeError):
        w.run(seo, approve_ready=False, write=True, log_line=lambda s: None)


def test_write_on_approve_then_verify_and_undo(env):
    seo, db, mp = env
    mp.setattr(w, "mode", lambda: "acik")
    assert w.on_approve(seo, "pr1", "kisi") == "yazildi"
    assert db.card["new_seobaslik"] == "Kitap - Yazar | Timaş" and db.card["new_seodurum"] == 2 and db.commits == 1
    upd = [s for s, _ in db.sql if s.startswith("UPDATE")][0]
    assert "Timas_MSCRM.dbo.new_kitapBase" in upd and "new_ozet" not in upd and "ModifiedOn" not in upd
    assert seo.audits and seo.audits[0][1] == "crm_write"
    # aynı değer ikinci kez yazılmaz
    assert w.on_approve(seo, "pr1", "kisi") == "degisiklik_yok"

    class _Ro:
        def execute(self, sql, limit):
            assert BOOK in sql
            return [], [{"id": BOOK, **{k: db.card.get(k) for k in w.FIELDS}}], False

        def close(self):
            pass

    mp.setattr(_crm, "connector", lambda: _Ro())
    v = w.verify(seo, log_line=lambda s: None)
    assert v == {"kayit": 1, "crm_ayni": 1, "crm_degisti": 0, "sitede": 0}  # T-soft meta açıklaması henüz farklı
    wid = [i for i in w.listing(seo)["items"] if i["status"] == "yazildi"][0]["id"]
    w.undo(seo, wid, "kisi")
    assert db.card["new_seobaslik"] == "Eski başlık"


def test_off_mode_does_nothing(env):
    seo, db, mp = env
    mp.setattr(w, "mode", lambda: "kapali")
    assert w.on_approve(seo, "pr1", "kisi") is None and not db.sql


def test_title_must_carry_author():
    assert w.title_has_author({"Model": "Nurşen Şirin"}, {"SeoTitle": "Kitap - Nurşen Şirin | Gülce"})
    assert not w.title_has_author({"Model": "Nurşen Şirin"}, {"SeoTitle": "Kitap | Gülce Çocuk"})
    assert w.title_has_author({"Model": "A Yazar, B Yazar"}, {"SeoTitle": "Kitap - A Yazar | Timaş"})
    assert w.title_has_author({}, {"SeoTitle": "Kitap | Timaş"}) and w.title_has_author({"Model": "X"}, {})


# ------------------------------------------------------------------ yazım sırası, geri al korumaları, onay kuralları
def _writes(seo):
    with seo.engine().connect() as c:
        return [dict(r) for r in c.execute(_sa.select(w.WRITES)).mappings()]


def test_old_value_is_recorded_before_crm_changes(env):
    seo, db, mp = env
    mp.setattr(w, "mode", lambda: "acik")
    seen = []
    real = _Cur.execute

    def spy(self, sql, *args):
        if sql.startswith("UPDATE"):
            seen.extend((r["status"], _json.loads(r["before_json"]).get("new_seobaslik")) for r in _writes(seo))
        return real(self, sql, *args)

    mp.setattr(_Cur, "execute", spy)
    assert w.on_approve(seo, "pr1", "kisi") == "yazildi"
    assert seen == [("yaziliyor", "Eski başlık")]
    assert [r["status"] for r in _writes(seo)] == ["yazildi"]


def test_failed_update_keeps_single_error_record(env):
    seo, db, mp = env
    mp.setattr(w, "mode", lambda: "acik")
    real = _Cur.execute

    def boom(self, sql, *args):
        if sql.startswith("UPDATE"):
            raise RuntimeError("izin yok")
        return real(self, sql, *args)

    mp.setattr(_Cur, "execute", boom)
    assert w.on_approve(seo, "pr1", "kisi") == "hata"
    rows = _writes(seo)
    assert len(rows) == 1 and rows[0]["status"] == "hata" and "izin yok" in rows[0]["error"]
    assert db.card["new_seobaslik"] == "Eski başlık"


def test_undo_refuses_when_crm_was_edited_later(env):
    seo, db, mp = env
    mp.setattr(w, "mode", lambda: "acik")
    w.on_approve(seo, "pr1", "kisi")
    db.card["new_seobaslik"] = "Editörün elle düzelttiği başlık"
    wid = _writes(seo)[0]["id"]
    with pytest.raises(RuntimeError, match="sonra değişmiş"):
        w.undo(seo, wid, "kisi")
    assert db.card["new_seobaslik"] == "Editörün elle düzelttiği başlık"
    assert _writes(seo)[0]["status"] == "yazildi"


def test_undo_only_latest_write_of_card(env):
    seo, db, mp = env
    mp.setattr(w, "mode", lambda: "acik")
    w.on_approve(seo, "pr1", "kisi")
    first = _writes(seo)[0]["id"]
    with seo.engine().begin() as c:
        c.execute(PROPOSALS.update().where(PROPOSALS.c.id == "pr1").values(
            fields_json=_json.dumps({"SeoTitle": "Yeni başlık - Yazar | Timaş"})))
    assert w.on_approve(seo, "pr1", "kisi") == "yazildi"
    with pytest.raises(RuntimeError, match="en son yazım"):
        w.undo(seo, first, "kisi")
    assert db.card["new_seobaslik"] == "Yeni başlık - Yazar | Timaş"


def test_undo_fails_when_card_not_updated(env):
    seo, db, mp = env
    mp.setattr(w, "mode", lambda: "acik")
    w.on_approve(seo, "pr1", "kisi")
    wid = _writes(seo)[0]["id"]
    real = _Cur.execute

    def passive(self, sql, *args):
        real(self, sql, *args) if sql.startswith("SELECT") else None
        if sql.startswith("UPDATE"):
            self.rowcount = 0

    mp.setattr(_Cur, "execute", passive)
    with pytest.raises(RuntimeError, match="güncellenemedi"):
        w.undo(seo, wid, "kisi")
    assert _writes(seo)[0]["status"] == "yazildi"


def test_odbc_password_is_braced_when_needed():
    assert w._odbc_value("timas_1") == "timas_1"
    assert w._odbc_value("a;b}c") == "{a;b}}c}"


class _Approver:
    """SeoGeo.approve'un ihtiyaç duyduğu kadarı: bellek içi SQLite, tek ürün, tek öneri."""

    def __init__(self, eng):
        self.eng, self.audits = eng, []

    def engine(self):
        return self.eng

    def product_row(self, pid):
        return {"data_json": _json.dumps({"SeoTitle": "Eski"}), "name": "Kitap"}

    def rescore(self, p, fields):
        return 80

    def audit(self, *a):
        self.audits.append(a)

    def proposal(self, pid):
        with self.eng.connect() as c:
            return dict(c.execute(_sa.select(PROPOSALS).where(PROPOSALS.c.id == pid)).mappings().first())


def _approver_env(status="hazir"):
    eng = _sa.create_engine("sqlite://")
    ensure(eng)
    with eng.begin() as c:
        c.execute(PROPOSALS.insert().values(id="pr9", tenant_id="t", product_id="p1", status=status, created_by="Ayşe",
                                            fields_json=_json.dumps({"SeoTitle": "Yeni"}), before_json="{}",
                                            created_at=w.now()))
    return _Approver(eng)


def test_requester_cannot_approve_own_proposal():
    from fastapi import HTTPException
    from semantic_bridge.seo_geo import SeoGeo

    a = _approver_env()
    with pytest.raises(HTTPException) as e:
        SeoGeo.approve(a, a.proposal("pr9"), {"SeoTitle": "Yeni"}, "ayşe", "", crm_write=False)
    assert e.value.status_code == 403 and a.proposal("pr9")["status"] == "hazir"
    assert SeoGeo.approve(a, a.proposal("pr9"), {"SeoTitle": "Yeni"}, "Mehmet", "", crm_write=False)["status"] == "onaylandi"


def test_second_concurrent_approval_is_rejected():
    from fastapi import HTTPException
    from semantic_bridge.seo_geo import SeoGeo

    a = _approver_env()
    stale = a.proposal("pr9")  # iki istek de «hazir» okudu
    SeoGeo.approve(a, stale, {"SeoTitle": "Yeni"}, "Mehmet", "", crm_write=False)
    with pytest.raises(HTTPException) as e:
        SeoGeo.approve(a, stale, {"SeoTitle": "Yeni"}, "Zeynep", "", crm_write=False)
    assert e.value.status_code == 409 and a.proposal("pr9")["decided_by"] == "Mehmet"


def test_bulk_run_updates_result_text(env):
    seo, db, mp = env
    mp.setattr(w, "mode", lambda: "acik")
    w.run(seo, approve_ready=False, write=True, log_line=lambda s: None)
    with seo.engine().connect() as c:
        r = c.execute(_sa.select(PROPOSALS.c.result).where(PROPOSALS.c.id == "pr1")).scalar()
    assert r == "Onaylandı. " + w.RESULT_TEXT["yazildi"]


def test_refresh_results_prefers_written(env):
    seo, db, mp = env
    mp.setattr(w, "mode", lambda: "acik")
    w.run(seo, approve_ready=False, write=True, log_line=lambda s: None)
    w.run(seo, approve_ready=False, write=True, log_line=lambda s: None)  # ikinci koşu: degisiklik_yok
    with seo.engine().begin() as c:
        c.execute(PROPOSALS.update().where(PROPOSALS.c.id == "pr1").values(result="eski metin"))
    assert w.refresh_results(seo, log_line=lambda s: None) == 1
    with seo.engine().connect() as c:
        r = c.execute(_sa.select(PROPOSALS.c.result).where(PROPOSALS.c.id == "pr1")).scalar()
    assert r.endswith(w.RESULT_TEXT["yazildi"])


def test_publisher_is_written_exactly_never_shortened():
    from semantic_bridge.seo_geo import propose
    t = "Levent Kayseri'de - Mustafa Orakçı | Timaş"
    assert propose.publisher_title(t, "Timaş Çocuk", 65) == "Levent Kayseri'de - Mustafa Orakçı | Timaş Çocuk"
    assert propose.publisher_title("Kitap - Yazar", "Timaş Tarih", 65) == "Kitap - Yazar | Timaş Tarih"
    # yayınevi her zaman eklenir; sınır yalnız «Ad - Yazar» kısmına (e-ticaret ekibi 10-06)
    long = "Bir Dehanın İzleri - II. Abdülhamid Han - Talha Uğurluel | Timaş"
    assert propose.publisher_title(long, "Timaş Tarih", 65) == "Bir Dehanın İzleri - II. Abdülhamid Han - Talha Uğurluel | Timaş Tarih"
    assert propose.publisher_title(t, "", 65) == "Levent Kayseri'de - Mustafa Orakçı"  # sitede yayınevi boşsa gösterilmez
    f = w.build({"ProductName": "Levent", "Model": "Mustafa Orakçı", "Brand": "Timaş Çocuk"}, {"SeoTitle": t}, STAMP)
    assert f["new_seobaslik"].endswith("| Timaş Çocuk")
    lim = {"title_min": 30, "title_max": 65, "meta_min": 120, "meta_max": 160}
    assert propose.enforce({"SeoTitle": t, "SeoDescription": ""}, lim, "Timaş Çocuk")["SeoTitle"].endswith("| Timaş Çocuk")


def test_enforce_drops_publisher_when_site_has_none_but_not_for_guides():
    from semantic_bridge.seo_geo import propose
    lim = {"title_min": 30, "title_max": 65, "meta_min": 120, "meta_max": 160}
    assert propose.enforce({"SeoTitle": "Kelebeği Yakala - Betül Özlü | Timaş", "SeoDescription": ""}, lim, "")["SeoTitle"] == "Kelebeği Yakala - Betül Özlü"
    assert propose.enforce({"SeoTitle": "Rehber | Timaş", "SeoDescription": ""}, lim)["SeoTitle"] == "Rehber | Timaş"



# ------------------------------------------------------------------ yarım meta açıklama (e-ticaret ekibi 10-06)
def test_meta_never_ends_mid_sentence():
    from semantic_bridge.seo_geo import propose
    cut = "Eser tasavvufi derinliği ve hitabî tarzıyla okuyucuya eşsiz bir"
    assert not propose.complete_sentence(cut)
    two = "Nevzat Tarhan duygusal zekayı Doğu ve Batı bakışıyla, günlük hayattan örneklerle ele alıyor. Kendini tanımak isteyenler için kapsamlı bir rehber sunan eser ayrıca"
    got = propose.fit_meta(two, 160)
    assert got == "Nevzat Tarhan duygusal zekayı Doğu ve Batı bakışıyla, günlük hayattan örneklerle ele alıyor."
    assert propose.fit_meta("Kısa. Ama sonu yarım kalan çok uzun bir ikinci cümle" * 3, 160) is None  # tam cümle çok kısa
    assert propose.fit_meta("Tam ve sığan bir cümle, okur için yazılmış bir açıklama metni burada bitiyor.", 160).endswith(".")
    lim = {"title_min": 30, "title_max": 65, "meta_min": 120, "meta_max": 160}
    out = propose.enforce({"SeoTitle": "Kitap - Yazar", "SeoDescription": cut + " " * 0}, lim, "Timaş")
    assert out["SeoDescription"] == "" and out["SeoTitle"] == "Kitap - Yazar | Timaş"
    assert any("tam cümle" in v for v in propose.violations({"SeoTitle": "Kitap - Yazar | Timaş", "SeoDescription": cut}, lim))


def test_crm_build_skips_incomplete_meta_but_writes_title():
    f = w.build({"ProductName": "Kitap", "Model": "Yazar", "Brand": "Timaş"},
                {"SeoTitle": "Kitap - Yazar", "SeoDescription": "Eser okuyucuya eşsiz bir"}, STAMP)
    assert "new_seoaciklama" not in f and f["new_seobaslik"] == "Kitap - Yazar | Timaş" and "new_kapakalt" in f


def test_repair_metas_trims_or_rewrites(env):
    seo, db, mp = env
    seo.conf = lambda k: ""
    with seo.engine().begin() as c:
        c.execute(PROPOSALS.update().where(PROPOSALS.c.id == "pr1").values(fields_json=_json.dumps(
            {"SeoTitle": "Kitap - Yazar | Timaş", "SeoDescription": "Eser okuyucuya eşsiz bir"})))

    class _Llm:
        def chat(self, messages, **k):
            return "Yazar bu kitapta okura sade bir dille önemli bir konuyu anlatıyor ve her yaştan okura hitap eden akıcı bir anlatım sunuyor."

    st = w.repair_metas(seo, _Llm(), log_line=lambda s: None)
    assert st["bozuk"] == 1 and st["yeniden_yazildi"] == 1
    with seo.engine().connect() as c:
        m = _json.loads(c.execute(_sa.select(PROPOSALS.c.fields_json).where(PROPOSALS.c.id == "pr1")).scalar())["SeoDescription"]
    assert m.endswith(".") and 90 <= len(m) <= 160
