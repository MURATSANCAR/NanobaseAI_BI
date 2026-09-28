"""M22 Sosyal medya: hesap, gönderi durum makinesi (iki göz, içerik değişince onayın düşmesi, bağlantıyla yayın),
platform sınırı, etiket ve zaman biçimi, takvim sayımı, özel gün / backlist fırsat kuralları, içe aktarma (başlık
eşleme, sayı biçimi, bağlantıyla gönderi eşleşmesi), aylık rapor, Zeki AI seçeneklerinin ayrıştırılması, yayına hazır
paket, yetki kuralları ve köprü uçları.

Veriler yapaydır ve yalnız kuralları sınar; gerçek CRM/Logo kabulü test sunucusunda (`scripts/acceptance/m22/`).
"""

from __future__ import annotations

import io
import zipfile
from datetime import date, timedelta

import pytest
import sqlalchemy as sa

from semantic_bridge import access as A
from semantic_bridge import social as S
from semantic_layer.store.catalog_store import open_store

T = "t1"


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    S._ready.discard(id(e))
    S.ensure(e)
    yield e
    S._ready.discard(id(e))


def _st(**over):
    s = S.settings(lambda k: "")
    s.update(over)
    return s


def _acc(engine, platform="instagram", handle="@timasyayinlari", user="ayse"):
    return S.create_account(engine, T, user, {"platform": platform, "handle": handle, "imprintAd": "Timaş"})


def _post(engine, acc, user="ayse", text="Yeni kitabımız raflarda.", when=None, **kw):
    when = when or (date.today() + timedelta(days=3)).isoformat() + " 10:00"
    return S.create_post(engine, T, user, {"accountId": acc["id"], "plannedAt": when, "text": text, **kw}, _st())


# ------------------------------------------------------------------ hesap


def test_account_validation_and_duplicates(engine):
    a = _acc(engine)
    assert a["platformAdi"] == "Instagram" and a["aktif"]
    with pytest.raises(S.SocialError) as e:
        _acc(engine, handle="@TIMASYAYINLARI")
    assert e.value.status == 409
    with pytest.raises(S.SocialError):
        S.create_account(engine, T, "ayse", {"platform": "myspace", "handle": "@x"})
    with pytest.raises(S.SocialError):
        S.create_account(engine, T, "ayse", {"platform": "x", "handle": "@x", "renk": "kirmizi"})
    old, new = S.update_account(engine, T, "ayse", a["id"], {"aktif": False, "ton": "Sıcak ve samimi"})
    assert old["aktif"] and not new["aktif"] and new["ton"] == "Sıcak ve samimi"
    with pytest.raises(S.SocialError) as e:
        _post(engine, a)
    assert e.value.status == 409                                          # pasif hesaba gönderi açılmaz


# ------------------------------------------------------------------ biçimler


def test_planned_time_and_hashtag_normalisation():
    assert S.planned("2026-10-05") == "2026-10-05 10:00"
    assert S.planned("2026-10-05T14:30:00") == "2026-10-05 14:30"
    assert S.planned(None) is None
    with pytest.raises(S.SocialError):
        S.planned("05.10.2026")
    assert S.hashtags("kitap, #Kitap  ##okuma #yeni-kitap") == "#kitap #okuma #yenikitap"
    assert S.hashtags(["#a", "b", ""]) == "#a #b" and S.hashtags("") is None
    assert S.tag_count("#a #b metin") == 2
    assert S.norm_url("https://www.instagram.com/p/ABC/?igsh=1") == S.norm_url("http://instagram.com/p/ABC")


# ------------------------------------------------------------------ durum makinesi


def test_idea_becomes_draft_when_text_arrives(engine):
    a = _acc(engine)
    p = S.create_post(engine, T, "ayse", {"accountId": a["id"]}, _st())
    assert p["status"] == "fikir" and p["id"].startswith(f"SM-{date.today().year}-")
    p = S.update_post(engine, T, "ayse", p["id"], {"text": "Metin"}, _st())
    assert p["status"] == "taslak"


def test_submit_needs_account_text_time_and_platform_limit(engine):
    a = _acc(engine, platform="x", handle="@timas")
    p = S.create_post(engine, T, "ayse", {"accountId": a["id"], "text": "kısa"}, _st())
    with pytest.raises(S.SocialError):
        S.transition(engine, T, "ayse", p["id"], "submit", _st())       # zaman yok
    S.update_post(engine, T, "ayse", p["id"], {"plannedAt": "2026-12-01", "text": "x" * 290}, _st())
    with pytest.raises(S.SocialError) as e:
        S.transition(engine, T, "ayse", p["id"], "submit", _st())       # X sınırı 280
    assert "280" in str(e.value)
    assert S.transition(engine, T, "ayse", p["id"], "submit", _st(limits={**S.DEFAULT_LIMITS, "x": 400}))["status"] == "onayda"


def test_instagram_tag_limit_blocks_submit(engine):
    a = _acc(engine)
    p = _post(engine, a, hashtags=" ".join(f"#e{i}" for i in range(31)))
    assert any(w["kod"] == "etiket" for w in p["uyarilar"])
    with pytest.raises(S.SocialError):
        S.transition(engine, T, "ayse", p["id"], "submit", _st())


def test_two_eyes_and_reject_needs_reason(engine):
    a = _acc(engine)
    p = _post(engine, a)
    S.transition(engine, T, "ayse", p["id"], "submit", _st())
    with pytest.raises(S.SocialError) as e:
        S.transition(engine, T, "ayse", p["id"], "approve", _st())
    assert e.value.status == 409
    with pytest.raises(S.SocialError):
        S.transition(engine, T, "mehmet", p["id"], "reject", _st())      # gerekçe yok
    back = S.transition(engine, T, "mehmet", p["id"], "reject", _st(), note="Görsel değişsin")
    assert back["status"] == "taslak" and back["note"] == "Görsel değişsin"
    S.transition(engine, T, "ayse", p["id"], "submit", _st())
    ok = S.transition(engine, T, "mehmet", p["id"], "approve", _st())
    assert ok["status"] == "onayli" and ok["approvedBy"] == "mehmet"


def test_onayda_is_frozen_and_withdraw_returns_to_draft(engine):
    a = _acc(engine)
    p = _post(engine, a)
    S.transition(engine, T, "ayse", p["id"], "submit", _st())
    with pytest.raises(S.SocialError) as e:
        S.update_post(engine, T, "ayse", p["id"], {"text": "değişti"}, _st())
    assert e.value.status == 409
    assert S.transition(engine, T, "ayse", p["id"], "withdraw", _st())["status"] == "taslak"


def test_content_change_drops_approval_but_time_change_keeps_it(engine):
    a = _acc(engine)
    p = _post(engine, a)
    S.transition(engine, T, "ayse", p["id"], "submit", _st())
    S.transition(engine, T, "mehmet", p["id"], "approve", _st())
    moved = S.update_post(engine, T, "ayse", p["id"], {"plannedAt": (date.today() + timedelta(days=9)).isoformat() + " 18:30"}, _st())
    assert moved["status"] == "onayli" and moved["approvedBy"] == "mehmet"
    edited = S.update_post(engine, T, "ayse", p["id"], {"text": "Yeni metin"}, _st())
    assert edited["status"] == "taslak" and edited["approvedBy"] is None
    assert any(e["ne"] == "onay-dustu" for e in S.events(engine, p["id"]))


def test_published_needs_url_and_is_frozen(engine):
    a = _acc(engine)
    p = _post(engine, a)
    S.transition(engine, T, "ayse", p["id"], "submit", _st())
    S.transition(engine, T, "mehmet", p["id"], "approve", _st())
    with pytest.raises(S.SocialError):
        S.transition(engine, T, "ayse", p["id"], "published", _st(), url="instagram.com/p/1")
    pub = S.transition(engine, T, "ayse", p["id"], "published", _st(), url="https://instagram.com/p/1")
    assert pub["status"] == "yayinlandi" and pub["publishedBy"] == "ayse"
    with pytest.raises(S.SocialError):
        S.update_post(engine, T, "ayse", p["id"], {"text": "sonradan"}, _st())
    fixed = S.update_post(engine, T, "ayse", p["id"], {"publishedUrl": "https://instagram.com/p/2", "kind": "alinti"}, _st())
    assert fixed["publishedUrl"].endswith("/2") and fixed["kind"] == "alinti"
    with pytest.raises(S.SocialError):
        S.transition(engine, T, "ayse", p["id"], "cancel", _st(), note="x")


def test_cancel_reopen_and_delete_rules(engine):
    a = _acc(engine)
    p = _post(engine, a)
    with pytest.raises(S.SocialError):
        S.transition(engine, T, "ayse", p["id"], "cancel", _st())         # gerekçe yok
    c = S.transition(engine, T, "ayse", p["id"], "cancel", _st(), note="Plan değişti")
    assert c["status"] == "iptal"
    with pytest.raises(S.SocialError):
        S.delete_post(engine, T, p["id"])                                   # iptal silinmez
    assert S.transition(engine, T, "ayse", p["id"], "reopen", _st())["status"] == "taslak"
    assert S.delete_post(engine, T, p["id"])["id"] == p["id"]
    with pytest.raises(S.SocialError) as e:
        S.get_post(engine, T, p["id"], _st())
    assert e.value.status == 404


def test_assets_are_validated_and_warnings_follow(engine):
    a = _acc(engine)
    p = _post(engine, a)
    assert {w["kod"] for w in p["uyarilar"]} >= {"gorsel-yok"}
    with pytest.raises(S.SocialError):
        S.update_post(engine, T, "ayse", p["id"], {"assets": [{"tip": "url", "url": "https://x"}]}, _st())
    with pytest.raises(S.SocialError):
        S.update_post(engine, T, "ayse", p["id"], {"assets": [{"tip": "studio", "job": "j1", "sid": "../etc"}]}, _st())
    ok = S.update_post(engine, T, "ayse", p["id"], {"assets": [{"tip": "studio", "job": "j1", "sid": "s_0123abcd", "ad": "Kare"},
                                                               {"tip": "studio", "job": "j1", "sid": "s_0123abcd"}]}, _st())
    assert len(ok["assets"]) == 1
    kods = {w["kod"] for w in ok["uyarilar"]}
    assert "gorsel-yok" not in kods and "lisans" in kods
    assert "lisans" not in {w["kod"] for w in S.get_post(engine, T, p["id"], _st(licensePending=False))["uyarilar"]}


def test_every_write_leaves_history(engine):
    a = _acc(engine)
    p = _post(engine, a)
    S.update_post(engine, T, "ayse", p["id"], {"kind": "kapak"}, _st())
    S.transition(engine, T, "ayse", p["id"], "submit", _st())
    acts = [e["ne"] for e in S.events(engine, p["id"])]
    assert acts[-1] == "olusturuldu" and "duzenlendi" in acts and acts[0] == "submit"


# ------------------------------------------------------------------ takvim


def test_calendar_counts_match_group_by(engine):
    a = _acc(engine)
    d0 = date(2026, 11, 2)
    for i, st_ in enumerate(("taslak", "taslak", "onayda")):
        p = _post(engine, a, when=f"{(d0 + timedelta(days=i)).isoformat()} 09:00")
        if st_ == "onayda":
            S.transition(engine, T, "ayse", p["id"], "submit", _st())
    _post(engine, a, when="2026-12-20 09:00")                                 # aralık dışı
    S.create_post(engine, T, "ayse", {"accountId": a["id"], "text": "tarihsiz"}, _st())
    cal = S.calendar(engine, T, _st(), d0, d0 + timedelta(days=6))
    with engine.connect() as c:
        ref = dict(c.execute(sa.text("SELECT status, COUNT(*) FROM semantic_social_posts WHERE planned_at >= :a AND planned_at <= :b "
                                     "GROUP BY status"), {"a": "2026-11-02 00:00", "b": "2026-11-08 23:59"}).all())
    assert cal["counts"] == ref == {"taslak": 2, "onayda": 1}
    assert len(cal["unscheduled"]) == 1
    with pytest.raises(S.SocialError):
        S.calendar(engine, T, _st(), d0, d0 - timedelta(days=1))


# ------------------------------------------------------------------ fırsat kuralları


def test_occasion_items_warn_only_when_no_linked_book_is_planned():
    from semantic_bridge.seo_geo import seasons as SS

    ref = date(2026, 11, 14)
    days = [{"key": "ogretmenler-gunu", "name": "Öğretmenler Günü", "source": "crm"},
            {"key": "uzak-gun", "name": "15 Mart Uzak Gün", "source": "crm"},
            {"key": "tarihsiz", "name": "Bilinmeyen Gün", "source": "crm"}]
    books = {"ogretmenler-gunu": [{"bookId": "b1", "ad": "A"}, {"bookId": "b2", "ad": "B"}]}
    out = S.occasion_items(days, books, ref, 30, 14, {}, SS.resolve, SS.next_occurrence)
    assert [o["key"] for o in out] == ["ogretmenler-gunu"]
    o = out[0]
    assert o["baslangic"] == "2026-11-24" and o["kalanGun"] == 10 and o["kitapSayisi"] == 2 and o["uyari"]
    out2 = S.occasion_items(days, books, ref, 30, 14, {"ogretmenler-gunu": {"b2"}}, SS.resolve, SS.next_occurrence)
    assert out2[0]["takvimde"] == 1 and not out2[0]["uyari"]
    assert out2[0]["kitaplar"][0]["bookId"] == "b1"                        # takvimde olmayan önce
    far = S.occasion_items(days, books, date(2026, 10, 1), 30, 14, {}, SS.resolve, SS.next_occurrence)
    assert far == []                                                          # 54 gün: pencere dışı


def test_backlist_rank_rules():
    ref = date(2026, 9, 28)
    sales = {"A": 500, "B": 900, "C": 800, "D": 1000, "E": 0, "F": 300}
    info = {"A": {"ilk_yayin": "2020-01-01", "ad": "A"}, "B": {"ilk_yayin": "2019-05-01", "ad": "B"},
            "C": {"ilk_yayin": "2026-06-01", "ad": "C"},            # yeni kitap
            "D": {"ilk_yayin": "2018-01-01", "ad": "D", "statu": "Tükendi"}, "E": {"ilk_yayin": "2010-01-01"},
            "F": {"ad": "F"}}                                           # ilk yayını bilinmiyor
    last = {"B": "2026-09-01 10:00"}                                   # 27 gün önce paylaşıldı
    out = S.backlist_rank(sales, info, last, ref, 365, 90, ["tükendi"])
    assert [x["stokKodu"] for x in out] == ["A"] and out[0]["sira"] == 1
    out = S.backlist_rank(sales, info, {}, ref, 365, 90)
    assert [x["stokKodu"] for x in out] == ["D", "B", "A"]
    assert S.month_window(date(2026, 8, 17)) == (2026 * 12 + 7 - 11, 2026 * 12 + 7)


# ------------------------------------------------------------------ içe aktarma


def test_header_mapping_and_number_formats():
    rows = [["Meta Business Suite dışa aktarım"], ["Gönderi bağlantısı", "Yayınlanma zamanı", "Erişim", "Beğeniler", "Yorumlar",
                                                   "Paylaşımlar", "Kaydetmeler", "Açıklama"],
            ["https://instagram.com/p/A", "03.11.2026 10:00", "1.234", "56", "7", "", "3", "x"],
            ["", "", "", "", "", "", "", ""],
            ["https://instagram.com/p/B", "", "100", "1", "0", "0", "0", "y"]]
    out = S.parse_rows(rows)
    assert out["cols"]["reach"] == "Erişim" and "Açıklama" in out["ignored"]
    assert out["rows"][0] == {"day": "2026-11-03", "post_url": "https://instagram.com/p/A", "reach": 1234.0, "likes": 56.0,
                              "comments": 7.0, "shares": None, "saves": 3.0}
    assert out["skipped"] == {"tarihsiz": 1, "bos": 1}
    assert len(S.parse_rows(rows, "2026-11-30")["rows"]) == 2
    assert S._num("1,234.5") == 1234.5 and S._num("12,5") == 12.5 and S._num("—") is None
    with pytest.raises(S.SocialError):
        S.parse_rows([["Ad", "Soyad"], ["a", "b"]])


def test_import_sums_match_db_and_link_posts_by_url(engine):
    a = _acc(engine)
    p = _post(engine, a)
    S.transition(engine, T, "ayse", p["id"], "submit", _st())
    S.transition(engine, T, "mehmet", p["id"], "approve", _st())
    S.transition(engine, T, "ayse", p["id"], "published", _st(), url="https://www.instagram.com/p/ABC/")
    csv_ = ("Date;Permalink;Reach;Impressions;Likes\n2026-11-03;https://instagram.com/p/ABC;1000;1500;40\n"
            "2026-11-04;https://instagram.com/p/ZZZ;250;300;5\n").encode("utf-8")
    imp = S.import_metrics(engine, T, "ayse", a["id"], "ig.csv", csv_)
    assert imp["satir"] == 2 and imp["eslesen"] == 1 and imp["toplam"]["reach"] == 1250
    with engine.connect() as c:
        db = c.execute(sa.text("SELECT SUM(reach) FROM semantic_social_metrics WHERE import_id = :i"), {"i": imp["id"]}).scalar()
    assert db == 1250
    assert S.post_metrics(engine, T, p["id"])[0]["reach"] == 1000
    with pytest.raises(S.SocialError):
        S.import_metrics(engine, T, "ayse", a["id"], "ig.pdf", b"x")
    S.delete_import(engine, T, imp["id"])
    assert S.post_metrics(engine, T, p["id"]) == [] and S.list_imports(engine, T) == []


def test_manual_metric_only_for_published_and_replaces_same_day(engine):
    a = _acc(engine)
    p = _post(engine, a)
    with pytest.raises(S.SocialError):
        S.add_manual_metric(engine, T, "ayse", p["id"], {"reach": 10})
    S.transition(engine, T, "ayse", p["id"], "submit", _st())
    S.transition(engine, T, "mehmet", p["id"], "approve", _st())
    S.transition(engine, T, "ayse", p["id"], "published", _st(), url="https://x.com/timas/status/1")
    S.add_manual_metric(engine, T, "ayse", p["id"], {"day": "2026-11-03", "reach": 10})
    S.add_manual_metric(engine, T, "ayse", p["id"], {"day": "2026-11-03", "reach": 20, "likes": 2})
    ms = S.post_metrics(engine, T, p["id"])
    assert len(ms) == 1 and ms[0]["reach"] == 20 and ms[0]["kaynak"] == "elle"
    with pytest.raises(S.SocialError):
        S.add_manual_metric(engine, T, "ayse", p["id"], {"reach": -1})


# ------------------------------------------------------------------ rapor


def test_report_groups_by_kind_and_account(engine):
    a = _acc(engine)
    b = _acc(engine, platform="x", handle="@timas")
    ids = []
    for acc, kind in ((a, "alinti"), (a, "kapak"), (b, "alinti")):
        p = _post(engine, acc, text="kısa metin", when="2026-11-05 10:00", kind=kind)
        S.transition(engine, T, "ayse", p["id"], "submit", _st())
        S.transition(engine, T, "mehmet", p["id"], "approve", _st())
        S.transition(engine, T, "ayse", p["id"], "published", _st(), url=f"https://example.com/{p['id']}")
        ids.append(p["id"])
    S.add_manual_metric(engine, T, "ayse", ids[0], {"day": "2026-11-06", "reach": 100, "likes": 10, "comments": 2})
    S.add_manual_metric(engine, T, "ayse", ids[1], {"day": "2026-11-06", "reach": 100, "likes": 2})
    S.add_manual_metric(engine, T, "ayse", ids[2], {"day": "2026-11-07", "reach": 50, "likes": 8, "shares": 2})
    S.add_manual_metric(engine, T, "ayse", ids[2], {"day": "2026-12-01", "reach": 999})     # başka ay
    rep = S.report(engine, T, "2026-11")
    assert rep["toplam"]["reach"] == 250 and rep["toplam"]["etkilesim"] == 24 and rep["toplam"]["oran"] == round(24 / 250, 4)
    kinds = {x["tur"]: x for x in rep["turler"]}
    assert kinds["alinti"]["gonderi"] == 2 and kinds["alinti"]["gonderiBasina"] == 11 and kinds["kapak"]["etkilesim"] == 2
    assert rep["turler"][0]["tur"] == "alinti"                               # gönderi başına etkileşime göre
    assert rep["gonderiSayisi"] == 3 and rep["gonderiDurum"] == {"yayinlandi": 3} and rep["onaySayisi"] == 3
    assert any("Toplam erişim: 250" == f for f in S.report_facts(rep))
    with pytest.raises(S.SocialError):
        S.report(engine, T, "kasım")


# ------------------------------------------------------------------ Zeki AI çıktısı ve paket


def test_parse_options():
    raw = ("SEÇENEK 1\nİlk metin burada.\nETİKETLER: #kitap #okuma\n\n**Seçenek 2:** İkinci metin.\n#roman #yeni\n\n"
           "Seçenek 3\nÜçüncü metin")
    out = S.parse_options(raw)
    assert [o["metin"] for o in out] == ["İlk metin burada.", "İkinci metin.", "Üçüncü metin"]
    assert out[0]["etiketler"] == "#kitap #okuma" and out[1]["etiketler"] == "#roman #yeni" and out[2]["etiketler"] == ""


def test_package_has_text_info_images_and_notes(engine):
    a = _acc(engine)
    p = _post(engine, a, hashtags="#kitap")
    S.update_post(engine, T, "ayse", p["id"], {"assets": [{"tip": "studio", "job": "j1", "sid": "s_0123abcd", "ad": "Kare görsel"},
                                                          {"tip": "creative", "id": "MC1"}]}, _st())
    S.transition(engine, T, "ayse", p["id"], "submit", _st())
    post = S.transition(engine, T, "mehmet", p["id"], "approve", _st())

    def fetch(ref):
        if ref["tip"] == "studio":
            return b"\x89PNG", "image/png"
        return None

    z = zipfile.ZipFile(io.BytesIO(S.package_zip(post, fetch, _st())))
    names = set(z.namelist())
    assert {"metin.txt", "bilgi.txt", "OKUBENI.txt", "01-kare-gorsel.png"} <= names
    assert z.read("metin.txt").decode().strip().endswith("#kitap")
    readme = z.read("OKUBENI.txt").decode()
    assert "2. görsel kaynağında bulunamadı" in readme and "lisans" in readme and "kendiliğinden" in readme


# ------------------------------------------------------------------ yetki


def test_access_rules_for_social():
    page = frozenset({A.page("sosyal-medya")})
    assert A.rule_for("/api/v1/social/calendar") == page
    assert A.rule_for("/api/v1/social/run-due") == A.SYSTEM
    f = A.features_for
    w = "ozellik:sosyal.duzenle"
    assert f("POST", "/api/v1/social/posts") == [w] and f("PATCH", "/api/v1/social/posts/SM-2026-0001") == [w]
    assert f("POST", "/api/v1/social/posts/SM-2026-0001/submit") == [w] and f("POST", "/api/v1/social/posts/x/draft") == [w]
    assert f("POST", "/api/v1/social/accounts") == [w] and f("PATCH", "/api/v1/social/accounts/a1") == [w]
    assert f("POST", "/api/v1/social/imports") == [w] and f("DELETE", "/api/v1/social/imports/i1") == [w]
    assert f("POST", "/api/v1/social/posts/x/approve") == [] and f("POST", "/api/v1/social/posts/x/reject") == []
    assert f("GET", "/api/v1/social/posts/x/package.zip") == ["ozellik:veri.disa-aktar"]
    assert f("GET", "/api/v1/social/report/export.pdf") == ["ozellik:veri.disa-aktar"]
    assert f("GET", "/api/v1/social/calendar") == []
    ex = A.explicit_keys()
    assert {"ozellik:sosyal.onay", "ozellik:sosyal.topluluk"} <= ex and w not in ex
    assert "sayfa:sosyal-medya" in A.all_keys() and "sayfa:sosyal-medya" not in ex


# ------------------------------------------------------------------ uçlar


def test_endpoints_two_eyes_and_explicit_approval(monkeypatch, store, settings):
    from fastapi.testclient import TestClient

    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod
    from semantic_bridge.app import Runtime, create_app
    from semantic_layer.candidates.llm_client import FakeLlm

    users = {"timas_session=a": "ayse", "timas_session=z": "zekiai"}
    monkeypatch.setattr(board_mod, "_fetch_user", lambda cookie: users.get(cookie))
    monkeypatch.setattr(board_mod, "_fetch_session", lambda cookie: {"username": users.get(cookie), "displayName": "x"})
    monkeypatch.setattr(admin_mod, "admins", lambda: ["zekiai"])
    monkeypatch.delenv("SEMANTIC_CALLER_TOKEN", raising=False)
    monkeypatch.delenv("SEMANTIC_ADMIN_TOKEN", raising=False)
    A._ready.clear()
    A.invalidate()
    S._ready.discard(id(store.engine))
    app = create_app(Runtime(settings, store=store, llm=FakeLlm([""])))
    client = TestClient(app)
    a, z = {"cookie": "timas_session=a"}, {"cookie": "timas_session=z"}

    acc = client.post("/api/v1/social/accounts", json={"platform": "instagram", "handle": "@timas"}, headers=a)
    assert acc.status_code == 201, acc.text
    when = (date.today() + timedelta(days=2)).isoformat()
    made = client.post("/api/v1/social/posts", json={"accountId": acc.json()["id"], "plannedAt": when, "text": "Merhaba"}, headers=a)
    assert made.status_code == 201, made.text
    pid = made.json()["id"]
    assert made.json()["plannedAt"] == f"{when} 10:00"
    assert client.post(f"/api/v1/social/posts/{pid}/submit", headers=a).json()["status"] == "onayda"
    assert client.post(f"/api/v1/social/posts/{pid}/approve", json={}, headers=a).status_code == 403
    ok = client.post(f"/api/v1/social/posts/{pid}/approve", json={"note": "uygun"}, headers=z)
    assert ok.status_code == 200 and ok.json()["status"] == "onayli"
    cal = client.get(f"/api/v1/social/calendar?frm={date.today()}&to={date.today() + timedelta(days=6)}", headers=a).json()
    assert cal["counts"] == {"onayli": 1} and cal["onayBekleyen"] == []
    me = client.get("/api/v1/social/meta", headers=a).json()["me"]
    assert me["canEdit"] and not me["canApprove"]
    assert client.get(f"/api/v1/social/posts/{pid}/package.zip", headers=a).status_code == 200
    assert client.post("/api/v1/social/run-due", headers=a).status_code == 403   # kişi zamanlayıcıyı tetikleyemez
    bad = client.post(f"/api/v1/social/posts/{pid}/published", json={"url": "yok"}, headers=a)
    assert bad.status_code == 400
    pub = client.post(f"/api/v1/social/posts/{pid}/published", json={"url": "https://instagram.com/p/X"}, headers=a)
    assert pub.json()["status"] == "yayinlandi"
    assert client.get("/api/v1/social/contract/posts", headers=a).json()["total"] == 1


def test_tables_are_created_once(engine):
    names = set(sa.inspect(engine).get_table_names())
    assert {"semantic_social_accounts", "semantic_social_posts", "semantic_social_post_events", "semantic_social_metrics",
            "semantic_social_imports", "semantic_social_jobs", "semantic_social_meta"} <= names
