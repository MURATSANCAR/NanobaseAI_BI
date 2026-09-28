"""M37 Okur topluluğu: kişi verisi süzgeci, H2 okur çekirdeği bağlantı noktası (bağlı değil / bağlı), ilgi alanı özel
nitelikli çağrışım koruması (varsayılan kapalı, insan kararı modelle ezilmez), segment onay akışı (amaç, süre, ölçüm, iki
göz, onaylı segment düzenlenince taslağa dönüş, süre dolumu), programlar ve duyuru istemi, yorum durumu ve T-soft yorumunun
kişisel alansız okunması, yetki kuralları ve köprü uçlarının hiçbir cevabında kişi verisi olmaması.

Veriler yapaydır ve yalnız kuralları sınar; gerçek CRM/H2/T-soft kabulü test sunucusunda (scripts/acceptance/M37).
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta

import pytest

from semantic_bridge import access as A
from semantic_bridge import okur as O
from semantic_bridge import okur_sources as S
from semantic_layer.store.catalog_store import open_store

TN = "t1"


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    O._ready.discard(id(e))
    O.ensure(e)
    return e


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in ("OKUR_HASSAS_SEGMENT_ACIK", "OKUR_HASSAS_ESIK", "OKUR_SEGMENT_MAX_GUN", "OKUR_AMAC_EN_AZ", "OKUR_ALERT_RECIPIENTS"):
        monkeypatch.delenv(k, raising=False)


class FakeChoice:
    def __init__(self, choice, p, margin):
        self.choice, self.probability, self.margin = choice, p, margin

    def confident(self, min_prob, min_margin=0.0, min_coverage=0.0):
        return self.probability is not None and self.probability >= min_prob and self.margin >= min_margin


def chooser(answer_index: int, p: float, margin: float, calls: list):
    def choose(prompt, choices):
        calls.append((prompt, list(choices)))
        return FakeChoice(choices[answer_index], p, margin)
    return choose


PERSONAL_KEY_RX = re.compile(r'"(fullname|emailaddress\d|mobilephone|telephone\d|address1_[a-z_]+|email|telefon)"\s*:', re.I)


def assert_clean(payload) -> None:
    text = json.dumps(payload, ensure_ascii=False)
    assert not O.EMAIL_RX.search(text), text[:400]
    assert not O.PHONE_RX.search(text), text[:400]
    assert not PERSONAL_KEY_RX.search(text), text[:400]


# ------------------------------------------------------------------ kişi verisi süzgeci


def test_scrub_drops_personal_keys_and_masks_contacts_but_keeps_numbers():
    raw = {"toplam": 1250, "yil": 2026, "FullName": "Ali Veli", "EMailAddress1": "ali@ornek.com",
           "satirlar": [{"kaynak": "Fuar", "MobilePhone": "0532 111 22 33", "not": "ara: 0 (532) 111 22 33 / ali@ornek.com",
                         "address1_line1": "Kadıköy"}]}
    out = O.scrub(raw)
    assert out["toplam"] == 1250 and out["yil"] == 2026
    assert "FullName" not in out and "EMailAddress1" not in out
    row = out["satirlar"][0]
    assert "MobilePhone" not in row and "address1_line1" not in row
    assert "[telefon gizlendi]" in row["not"] and "[e-posta gizlendi]" in row["not"]
    assert_clean(out)
    # yıl, adet, stok kodu gibi kısa sayılar telefon sanılmaz
    assert O.mask_text("2026 yılında 15201 adet, stok 15201.01.0001") == "2026 yılında 15201 adet, stok 15201.01.0001"


def test_prompt_guard_refuses_contacts():
    with pytest.raises(O.OkurError):
        O.assert_no_personal("Okur ali@ornek.com yazdı")
    with pytest.raises(O.OkurError):
        O.assert_no_personal("Tel +90 532 111 22 33")
    O.assert_no_personal("Kasım okuma kulübü, 2026-11-12, 40 kişi")


def test_review_and_announcement_prompts_have_no_personal_data():
    msgs = O.review_messages("Küçük Prens", 2, "Kargo geç geldi, beni arayın 0532 111 22 33 veya x@y.com", "Kötü")
    text = json.dumps(msgs, ensure_ascii=False)
    assert "0532" not in text and "x@y.com" not in text and "[telefon gizlendi]" in text
    p = {"tur": "okuma_kulubu", "ad": "Kasım okuma kulübü", "tarih": "2026-11-12", "saat": "19:00", "sehir": "İstanbul",
         "yer": None, "kitapAdi": "Küçük Prens", "yazarAdi": "Antoine de Saint-Exupéry"}
    msgs = O.announcement_messages(p, {"spot": "Bir çocuk ve bir gezegen."}, {"amac": "Kasım okuma kulübü duyurusu"})
    assert "Küçük Prens" in msgs[1]["content"] and "uydurma" in msgs[1]["content"]
    assert O.clean_model_text("<think>x</think> \"Merhaba, bilgi için a@b.co\"") == "Merhaba, bilgi için [e-posta gizlendi]"


# ------------------------------------------------------------------ H2 bağlantı noktası


class FakeCore:
    def __init__(self):
        self.sized = []

    def okur_envanteri(self, tenant):
        return {"toplam": 130, "satirlar": [
            {"kaynak": "CRM kişi", "kayitTipi": "Fuar", "toplam": 100, "kvkkOnayli": 40, "iysOnayli": 35, "epostaIzinli": 30,
             "smsIzinli": 10, "ilgiAlaniDolu": 20, "silinebilir": 2, "cocukOlasi": 1, "FullName": "Ali Veli", "email": "a@b.com"},
            {"source": "CRM aday", "type": "Landing Page", "total": 30, "kvkk": 12}]}

    def izin_sagligi(self, tenant):
        return {"izinsiz_gonderim": 3, "silinebilir_etkin": 1}

    def segment_olcusu(self, tenant, kural):
        self.sized.append(kural)
        return {"total": 50, "email_ok": 20, "sms_ok": 5}

    def ilgi_alanlari(self, tenant):
        return [{"id": "n1", "ad": "Çocuk ve aile", "okur": 70}, {"id": "n2", "ad": "Tasavvuf", "okur": 30}, {"id": "n3", "name": "Tarih"}]


def test_core_not_connected_when_no_provider():
    class App:
        class state:  # noqa: N801
            pass
    assert S.ReadersCore.resolve(App()) is None or S.ReadersCore.resolve(App()).provider.__name__ == "semantic_bridge.readers"


def test_core_adapter_maps_names_and_strips_personal():
    class App:
        class state:  # noqa: N801
            readers_core = FakeCore()
    c = S.ReadersCore.resolve(App())
    assert c is not None
    inv = c.inventory(TN)
    assert inv["toplam"] == 130 and len(inv["satirlar"]) == 2
    assert inv["satirlar"][1] == {"kaynak": "CRM aday", "kayitTipi": "Landing Page", "toplam": 30, "kvkkOnayli": 12, "iysOnayli": None,
                                  "epostaIzinli": None, "smsIzinli": None, "ilgiAlaniDolu": None, "silinebilir": None, "cocukOlasi": None}
    assert_clean(inv)
    assert {x["tur"]: x["sayi"] for x in c.consent(TN)} == {"izinsiz_gonderim": 3, "silinebilir_etkin": 1}
    assert c.size(TN, {"ilgi_alanlari": ["n1"]}) == {"toplam": 50, "izinli": None, "eposta": 20, "sms": 5}
    assert [i["ad"] for i in c.interests(TN)] == ["Çocuk ve aile", "Tasavvuf", "Tarih"]
    assert c.rule_interests({"ve": [{"alan": "ilgi_alani", "deger": ["n2"]}, {"alan": "kaynak", "deger": "Fuar"}]}) == ["n2"]
    assert c.rule_text({}) is None and c.rule_fields() == []


def test_rule_interest_walk():
    rule = {"ilgi_alanlari": ["n1", "n2"], "kaynak": "Fuar", "ve": [{"interest": {"id": "n3"}}, {"field": "category", "in": ["n4"]}],
            "kayit_tarihi_sonra": "2025-01-01"}
    assert O.rule_interest_ids(rule) == ["n1", "n2", "n3", "n4"]


# ------------------------------------------------------------------ çağrışım koruması


def test_classify_interest_threshold_and_default_block(engine):
    calls = []
    assert O.classify_interest("Tasavvuf", chooser(0, 0.8, 0.6, calls))["isaret"] == "ozel"
    assert O.classify_interest("Çocuk ve aile", chooser(1, 0.97, 0.94, calls))["isaret"] == "degil"
    assert O.classify_interest("Felsefe", chooser(1, 0.7, 0.4, calls))["isaret"] == "bilinmiyor"   # eşik altı
    assert "KVKK" in calls[0][0] and calls[0][1] == list(O.FLAG_CHOICES)

    items = [{"id": "n1", "ad": "Çocuk ve aile"}, {"id": "n2", "ad": "Tasavvuf"}, {"id": "n3", "ad": "Tarih"}]
    answers = iter([(1, 0.97, 0.94), (0, 0.9, 0.8), (1, 0.6, 0.2)])

    def choose(prompt, choices):
        i, p, m = next(answers)
        return FakeChoice(choices[i], p, m)

    out = O.classify_missing(engine, TN, items, choose)
    assert out == {"sorulan": 3, "ozel": 1, "degil": 1, "bilinmiyor": 1, "hata": 0}
    g = O.guard_rule(engine, TN, ["n1", "n2", "n3", "n9"])
    assert not g["ok"] and {x["id"] for x in g["engel"]} == {"n2", "n3", "n9"}
    assert O.guard_rule(engine, TN, ["n1"])["ok"]
    view = {v["id"]: v["kullanilabilir"] for v in O.interest_view(engine, TN, items)}
    assert view == {"n1": True, "n2": False, "n3": False}


def test_sensitive_open_by_legal_decision_warns_but_unknown_stays_blocked(engine, monkeypatch):
    O.set_flag(engine, TN, "n2", "Tasavvuf", "ozel", kaynak="zeki")
    monkeypatch.setenv("OKUR_HASSAS_SEGMENT_ACIK", "1")
    g = O.guard_rule(engine, TN, ["n2"])
    assert g["ok"] and g["uyari"][0]["id"] == "n2"
    assert not O.guard_rule(engine, TN, ["n7"])["ok"]


def test_human_flag_is_not_overwritten_by_model_and_needs_reason(engine):
    with pytest.raises(O.OkurError):
        O.set_flag(engine, TN, "n1", "Çocuk", "degil", kaynak="insan", karar_veren="kvkk")
    O.set_flag(engine, TN, "n1", "Çocuk", "degil", kaynak="insan", karar_veren="kvkk", gerekce="Yaş grubu; inanç çıkarımı yok")
    O.set_flag(engine, TN, "n1", "Çocuk", "ozel", kaynak="zeki", olasilik=0.9)
    assert O.flags(engine, TN)["n1"]["isaret"] == "degil"
    out = O.classify_missing(engine, TN, [{"id": "n1", "ad": "Çocuk"}], chooser(0, 1, 1, []))
    assert out["sorulan"] == 0


# ------------------------------------------------------------------ segment akışı


def _seg(engine, user="ayse", **kw):
    body = {"ad": "Çocuk ve aile, e-posta izinli", "kural": {"ilgi_alanlari": ["n1"]}, "kanal": "eposta", **kw}
    return O.create_segment(engine, TN, user, body, O.rule_interest_ids(body["kural"]))


def test_segment_flow_purpose_duration_measure_two_eyes(engine):
    O.set_flag(engine, TN, "n1", "Çocuk ve aile", "degil", kaynak="insan", karar_veren="kvkk", gerekce="yaş grubu")
    s = _seg(engine)
    assert s["durum"] == "taslak" and s["ilgiAlanlari"] == ["n1"] and s["surum"] == 1
    ok = O.guard_rule(engine, TN, s["ilgiAlanlari"])
    with pytest.raises(O.OkurError, match="Amaç"):
        O.submit_segment(engine, TN, "ayse", s["id"], ok)
    O.update_segment(engine, TN, "ayse", s["id"], {"amac": "Kasım okuma kulübü duyurusu"})
    with pytest.raises(O.OkurError, match="Süre"):
        O.submit_segment(engine, TN, "ayse", s["id"], ok)
    O.update_segment(engine, TN, "ayse", s["id"], {"sureBitis": (date.today() + timedelta(days=500)).isoformat()})
    with pytest.raises(O.OkurError, match="en çok"):
        O.submit_segment(engine, TN, "ayse", s["id"], ok)
    O.update_segment(engine, TN, "ayse", s["id"], {"sureBitis": (date.today() + timedelta(days=60)).isoformat()})
    with pytest.raises(O.OkurError, match="ölçün"):
        O.submit_segment(engine, TN, "ayse", s["id"], ok)
    O.record_size(engine, TN, s["id"], {"toplam": 50, "izinli": 20, "eposta": 20, "sms": 5})
    out = O.submit_segment(engine, TN, "mehmet", s["id"], ok)
    assert out["durum"] == "onay_bekliyor" and out["gonderen"] == "mehmet"
    with pytest.raises(O.OkurError) as e:
        O.update_segment(engine, TN, "ayse", s["id"], {"ad": "x"})
    assert e.value.status == 409
    for who in ("ayse", "mehmet"):  # yazan ve gönderen onaylayamaz
        with pytest.raises(O.OkurError) as e:
            O.decide_segment(engine, TN, who, s["id"], True, None, ok)
        assert e.value.status == 403
    with pytest.raises(O.OkurError, match="gerekçe"):
        O.decide_segment(engine, TN, "kvkk", s["id"], False, "", ok)
    out = O.decide_segment(engine, TN, "kvkk", s["id"], True, "Uygun", ok)
    assert out["durum"] == "onaylandi" and out["onaylayan"] == "kvkk"
    assert [x["id"] for x in O.approved_segments(engine, TN)] == [s["id"]]
    # onaylı segment değişirse taslağa döner, sürüm artar, ölçüm silinir
    out, diff = O.update_segment(engine, TN, "ayse", s["id"], {"kural": {"ilgi_alanlari": ["n1"], "kaynak": "Fuar"}}, ["n1"])
    assert out["durum"] == "taslak" and out["surum"] == 2 and out["sonOlcum"] is None and diff["durum"]["once"] == "onaylandi"
    assert O.approved_segments(engine, TN) == []


def test_segment_blocked_by_sensitive_interest_and_expiry(engine):
    O.set_flag(engine, TN, "n2", "Tasavvuf", "ozel", kaynak="zeki", olasilik=0.9)
    s = _seg(engine, kural={"ilgi_alanlari": ["n2"]}, amac="Ramazan kitapları duyurusu için okurlar",
             sureBitis=(date.today() + timedelta(days=30)).isoformat())
    O.record_size(engine, TN, s["id"], {"toplam": 10})
    g = O.guard_rule(engine, TN, s["ilgiAlanlari"])
    with pytest.raises(O.OkurError) as e:
        O.submit_segment(engine, TN, "ayse", s["id"], g)
    assert e.value.status == 409 and "hukuk" in str(e.value)
    # süre dolumu
    O.set_flag(engine, TN, "n1", "Çocuk", "degil", kaynak="insan", karar_veren="kvkk", gerekce="yaş")
    s2 = _seg(engine, amac="Kasım okuma kulübü duyurusu", sureBitis=(date.today() + timedelta(days=10)).isoformat())
    O.record_size(engine, TN, s2["id"], {"toplam": 5})
    ok = O.guard_rule(engine, TN, ["n1"])
    O.submit_segment(engine, TN, "ayse", s2["id"], ok)
    O.decide_segment(engine, TN, "kvkk", s2["id"], True, None, ok)
    with engine.begin() as c:
        c.execute(O.SEGMENTS.update().where(O.SEGMENTS.c.id == s2["id"]).values(sure_bitis=(date.today() - timedelta(days=1)).isoformat()))
    assert [x["id"] for x in O.expire_segments(engine, TN)] == [s2["id"]]
    assert O.segment_detail(engine, TN, s2["id"])["durum"] == "suresi_doldu"


def test_segment_rule_cannot_carry_contacts(engine):
    with pytest.raises(O.OkurError):
        O.create_segment(engine, TN, "ayse", {"ad": "x", "kural": {"eposta": "ali@ornek.com"}}, [])
    with pytest.raises(O.OkurError):
        O.create_segment(engine, TN, "ayse", {"ad": "x", "kural": {}}, [])


def test_snapshot_and_trend(engine):
    inv = {"satirlar": [{"kaynak": "CRM kişi", "kayitTipi": "Fuar", "toplam": 100, "kvkkOnayli": 40},
                        {"kaynak": "CRM kişi", "kayitTipi": "Fuar", "toplam": 5, "kvkkOnayli": None},
                        {"kaynak": "CRM aday", "kayitTipi": "", "toplam": 30, "kvkkOnayli": 10}]}
    O.save_snapshot(engine, TN, inv, [{"tur": "a", "ad": "A", "sayi": 3}], "2026-09-01")
    O.save_snapshot(engine, TN, inv, [{"tur": "a", "ad": "A", "sayi": 5}], "2026-09-02")
    O.save_snapshot(engine, TN, inv, [{"tur": "a", "ad": "A", "sayi": 4}], "2026-09-02")   # aynı gün üzerine yazılır
    t = O.trend(engine, TN)["noktalar"]
    assert [(p["tarih"], p["toplam"], p["kvkkOnayli"], p["izinCeliskisi"]) for p in t] == [
        ("2026-09-01", 135, 50, 3), ("2026-09-02", 135, 50, 4)]
    assert O.consent_previous(engine, TN, "2026-09-02") == 3


# ------------------------------------------------------------------ programlar


def test_programs_crud_and_due(engine):
    with pytest.raises(O.OkurError):
        O.create_program(engine, TN, "ayse", {"tur": "konser", "ad": "x"})
    with pytest.raises(O.OkurError):
        O.create_program(engine, TN, "ayse", {"tur": "imza_gunu", "ad": "x", "saat": "25:00"})
    d = (date.today() + timedelta(days=3)).isoformat()
    p = O.create_program(engine, TN, "ayse", {"tur": "okuma_kulubu", "ad": "Kasım okuma kulübü", "tarih": d, "saat": "19:00",
                                              "sehir": "İstanbul", "kitapAdi": "Küçük Prens"})
    assert p["kalanGun"] == 3 and p["durum"] == "taslak"
    later = O.create_program(engine, TN, "ayse", {"tur": "anket", "ad": "Okur anketi"})
    assert [x["id"] for x in O.list_programs(engine, TN)["items"]] == [p["id"], later["id"]]   # tarihsiz sonda
    assert [x["id"] for x in O.due_programs(engine, TN, 7)] == [p["id"]]
    out, diff = O.update_program(engine, TN, "mehmet", p["id"], {"durum": "planlandi", "duyuruTaslagi": "Bilgi: 0532 111 22 33"})
    assert out["durum"] == "planlandi" and "[telefon gizlendi]" in out["duyuruTaslagi"] and diff["duyuru_taslagi"] == "değişti"
    with pytest.raises(O.OkurError):
        O.update_program(engine, TN, "mehmet", p["id"], {"segmentId": "yok"})
    O.delete_program(engine, TN, later["id"])
    assert O.list_programs(engine, TN)["total"] == 1


# ------------------------------------------------------------------ yorumlar


def test_comment_row_reads_no_personal_fields():
    raw = {"CommentId": 77, "ProductId": "12", "Rate": 80, "Comment": "Harika, bana yazın a@b.com", "CustomerName": "Ali Veli",
           "CustomerEmail": "ali@ornek.com", "MemberId": 5, "CreateDate": "2026-09-20 10:00:00", "IsApproved": 1, "Answer": ""}
    r = S.comment_row(raw)
    assert r["id"] == "77" and r["puan"] == 4 and r["onayli"] is True and r["sitedeCevap"] is False
    assert "[e-posta gizlendi]" in r["metin"]
    assert_clean(r)
    assert "Ali Veli" not in json.dumps(r, ensure_ascii=False)
    assert S.comment_row({"CommentId": 1, "Type": "question"}) is None
    assert S.comment_row({**raw, "Answer": "Teşekkürler"})["sitedeCevap"] is True


def test_review_status_merge_and_counts(engine):
    comments = [{"id": "1", "productId": "p1", "puan": 5, "tarih": "2026-09-20", "metin": "güzel", "sitedeCevap": False},
                {"id": "2", "productId": "p1", "puan": 2, "tarih": "2026-09-21", "metin": "geç geldi", "sitedeCevap": False},
                {"id": "3", "productId": "p2", "puan": 4, "tarih": "2026-09-19", "metin": "iyi", "sitedeCevap": True}]
    O.set_review(engine, TN, "ayse", "2", "p1", "taslak", "Özür dileriz.", "zeki")
    items = O.merge_reviews(comments, O.review_status(engine, TN), {"p1": "Küçük Prens"})
    assert [(x["id"], x["durum"]) for x in items] == [("2", "taslak"), ("1", "cevapsiz"), ("3", "cevaplandi")]
    assert items[0]["urun"] == "Küçük Prens" and items[0]["taslak"] == "Özür dileriz."
    assert O.review_counts(items) == {"cevapsiz": 1, "taslak": 1, "cevaplandi": 1, "toplam": 3}
    out = O.set_review(engine, TN, "ayse", "2", None, "cevaplandi")
    assert out["taslak"] == "Özür dileriz."          # işaretleme taslağı silmez
    with pytest.raises(O.OkurError):
        O.set_review(engine, TN, "ayse", "2", None, "yayinda")


# ------------------------------------------------------------------ yetki


def test_okur_rules():
    r = A.rule_for
    assert r("/api/v1/okur/overview") == frozenset({"sayfa:okur-toplulugu", "sayfa:okur-segmentler", "sayfa:okur-programlar", "sayfa:okur-yorumlar"})
    assert r("/api/v1/okur/segments/abc/decision") == frozenset({"sayfa:okur-segmentler"})
    assert r("/api/v1/okur/reviews") == frozenset({"sayfa:okur-yorumlar"})
    assert r("/api/v1/okur/programs") == frozenset({"sayfa:okur-programlar", "sayfa:okur-toplulugu"})
    assert r("/api/v1/okur/run-due") == A.SYSTEM
    f = A.features_for
    assert f("POST", "/api/v1/okur/segments") == ["ozellik:topluluk.segment-yaz"]
    assert f("POST", "/api/v1/okur/segments/preview-rule") == ["ozellik:topluluk.segment-yaz"]
    assert f("PATCH", "/api/v1/okur/segments/abc") == ["ozellik:topluluk.segment-yaz"]
    assert f("POST", "/api/v1/okur/segments/abc/submit") == ["ozellik:topluluk.segment-yaz"]
    assert f("POST", "/api/v1/okur/segments/abc/decision") == []          # açıkça verilen segment-onay ucun içinde
    assert f("POST", "/api/v1/okur/segments/abc/export") == []            # açıkça verilen liste-disa-aktar ucun içinde
    assert f("POST", "/api/v1/okur/categories/n1/decision") == []
    assert f("POST", "/api/v1/okur/categories/classify") == ["ozellik:topluluk.segment-yaz"]
    assert f("POST", "/api/v1/okur/programs/abc/draft") == ["ozellik:topluluk.program-yaz"]
    assert f("POST", "/api/v1/okur/reviews/77/draft") == ["ozellik:topluluk.yorum-taslak"]
    assert f("GET", "/api/v1/okur/reviews") == []
    assert {"ozellik:topluluk.segment-onay", "ozellik:topluluk.liste-disa-aktar"} <= A.explicit_keys()
    assert {"sayfa:okur-toplulugu", "ozellik:topluluk.segment-yaz", "ozellik:topluluk.program-yaz"} <= A.all_keys()


# ------------------------------------------------------------------ köprü


def _client(monkeypatch, store, settings, llm_replies=None):
    from fastapi.testclient import TestClient

    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod
    from semantic_bridge.app import Runtime, create_app
    from semantic_layer.candidates.llm_client import FakeLlm

    users = {"timas_session=a": "ayse", "timas_session=m": "mehmet", "timas_session=z": "zekiai"}
    monkeypatch.setattr(board_mod, "_fetch_user", lambda cookie: users.get(cookie))
    monkeypatch.setattr(board_mod, "_fetch_session", lambda cookie: {"username": users.get(cookie), "displayName": "x"})
    monkeypatch.setattr(admin_mod, "admins", lambda: ["zekiai"])
    monkeypatch.delenv("SEMANTIC_CALLER_TOKEN", raising=False)
    A._ready.clear()
    A.invalidate()
    app = create_app(Runtime(settings, store=store, llm=FakeLlm(by_keyword=llm_replies or {})))
    return app, TestClient(app)


def test_api_without_core_says_not_connected(monkeypatch, store, settings):
    app, client = _client(monkeypatch, store, settings)
    app.state.readers_core = None
    a = {"cookie": "timas_session=a"}
    ov = client.get("/api/v1/okur/overview", headers=a)
    assert ov.status_code == 200
    body = ov.json()
    if body["envanter"]["bagli"] is False:           # H2 modülü bu ağaçta yoksa
        assert "bağlı değil" in body["envanter"]["mesaj"]
        s = client.post("/api/v1/okur/segments", json={"ad": "Deneme", "kural": {"ilgi_alanlari": ["n1"]}}, headers=a).json()
        assert client.post(f"/api/v1/okur/segments/{s['id']}/preview", headers=a).status_code == 409
        assert client.delete(f"/api/v1/okur/segments/{s['id']}", headers=a).status_code == 200
    assert client.get("/api/v1/okur/meta", headers=a).json()["me"]["canApprove"] is False


def test_api_flow_with_core_and_no_personal_data(monkeypatch, store, settings):
    app, client = _client(monkeypatch, store, settings,
                          {"duyuru/davet": "Kasım okuma kulübüne davetlisiniz. Bilgi için okur@timas.com.tr",
                           "okur yorumuna": "İlginiz için teşekkür ederiz."})
    app.state.readers_core = FakeCore()
    a, m, z = {"cookie": "timas_session=a"}, {"cookie": "timas_session=m"}, {"cookie": "timas_session=z"}
    seen = []

    def j(resp, code=200):
        assert resp.status_code == code, resp.text
        seen.append(resp.json())
        return resp.json()

    ov = j(client.get("/api/v1/okur/overview", headers=a))
    assert ov["envanter"]["bagli"] and ov["envanter"]["toplam"] == 130 and ov["izin"]["toplam"] == 4
    cats = j(client.get("/api/v1/okur/categories", headers=a))
    assert {i["id"]: i["kullanilabilir"] for i in cats["items"]} == {"n1": False, "n2": False, "n3": False}   # sınıflanmadı
    assert client.post("/api/v1/okur/categories/n1/decision", json={"isaret": "degil", "gerekce": "yaş grubu"}, headers=a).status_code == 403
    j(client.post("/api/v1/okur/categories/n1/decision", json={"ad": "Çocuk ve aile", "isaret": "degil", "gerekce": "yaş grubu"}, headers=z))
    pr = j(client.post("/api/v1/okur/segments/preview-rule", json={"kural": {"ilgi_alanlari": ["n2"]}}, headers=a))
    assert pr["olcum"] is None and not pr["kvkk"]["ok"]
    s = j(client.post("/api/v1/okur/segments", json={"ad": "Çocuk ve aile", "kural": {"ilgi_alanlari": ["n1"]},
                                                     "amac": "Kasım okuma kulübü duyurusu",
                                                     "sureBitis": (date.today() + timedelta(days=30)).isoformat()}, headers=a), 201)
    assert s["kvkk"]["ok"]
    assert client.post(f"/api/v1/okur/segments/{s['id']}/submit", headers=a).status_code == 409   # ölçülmedi
    meas = j(client.post(f"/api/v1/okur/segments/{s['id']}/preview", headers=a))
    assert meas["sonOlcum"]["toplam"] == 50 and meas["sonOlcum"]["eposta"] == 20
    j(client.post(f"/api/v1/okur/segments/{s['id']}/submit", headers=a))
    assert client.post(f"/api/v1/okur/segments/{s['id']}/decision", json={"karar": "onayla"}, headers=m).status_code == 403   # yetki yok
    assert client.post(f"/api/v1/okur/segments/{s['id']}/export", headers=z).status_code == 501
    out = j(client.post(f"/api/v1/okur/segments/{s['id']}/decision", json={"karar": "onayla", "not": "uygun"}, headers=z))
    assert out["durum"] == "onaylandi"
    assert [x["id"] for x in j(client.get("/api/v1/okur/contract/segments", headers=a))["items"]] == [s["id"]]

    p = j(client.post("/api/v1/okur/programs", json={"tur": "okuma_kulubu", "ad": "Kasım okuma kulübü", "segmentId": s["id"],
                                                     "tarih": (date.today() + timedelta(days=5)).isoformat()}, headers=a), 201)
    d = j(client.post(f"/api/v1/okur/programs/{p['id']}/draft", headers=a))
    assert d["duyuruKaynak"] == "zeki" and "[e-posta gizlendi]" in d["duyuruTaslagi"]
    j(client.get("/api/v1/okur/programs", headers=a))
    j(client.get("/api/v1/okur/segments", headers=a))
    j(client.get(f"/api/v1/okur/segments/{s['id']}", headers=a))
    j(client.get("/api/v1/okur/consent-health", headers=a))
    j(client.get("/api/v1/okur/inventory", headers=a))
    run = j(client.post("/api/v1/okur/run-due"))
    assert run["anlikGoruntu"]["envanterSatiri"] == 2 and run["segmentOlcumu"]["olculen"] == 1 and run["eposta"] in ("bos", "alici_yok")
    j(client.get("/api/v1/okur/inventory", headers=a))
    for payload in seen:
        assert_clean(payload)

    # test verisi bırakılmaz
    assert client.delete(f"/api/v1/okur/programs/{p['id']}", headers=a).status_code == 200
    j(client.patch(f"/api/v1/okur/segments/{s['id']}", json={"ad": "Çocuk ve aile (kapanış)"}, headers=a))
    assert client.delete(f"/api/v1/okur/segments/{s['id']}", headers=a).status_code == 200
