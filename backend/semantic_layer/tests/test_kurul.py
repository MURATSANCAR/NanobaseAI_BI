"""DYK Kurul: gösterge kataloğu (eşiksiz gelir, sürümlü düzeltme), renk kuralı (kendi eşiği > kaynak rengi > eşik yok;
kaynak yoksa renk ve sayı yok), ölçüm kaydı (önceki dönem, renk değişimi), sağlayıcı hatasının yalnız kendi göstergesini
düşürmesi, bölüm yorumu (sahip yazınca onaylı, onaylı yorum silinmez), toplantı/karar/aksiyon (sahip yalnız durum ve
not), paket (derle → özet → dondur; dondurulmuş içerik ve PDF değişmez, dosya değişirse verilmez, yeni derleme yeni
sürüm), Zeki AI metninde olgu dışı sayı → kaydedilmez, tutanak önerisi süzgeci, dağıtım satırları, hatırlatmalar (bir
kez) ve yetki kuralları + köprü uçlarının kapısı.

Veriler yapaydır ve yalnız kuralları sınar; gerçek modül çıktılarıyla kabul test sunucusunda (scripts/acceptance/DYK).
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from semantic_bridge import access as A
from semantic_bridge import kurul as K
from semantic_bridge import kurul_sources as S
from semantic_layer.store.catalog_store import open_store

TN = "t1"
NOW = datetime(2026, 9, 28, 6, 30, tzinfo=timezone.utc)


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    K._ready.discard(id(e))
    K.ensure(e)
    K.seed_library(e, TN)
    return e


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("KURUL_DIR", str(tmp_path / "kurul"))
    for k in ("KURUL_STALE_HOURS", "KURUL_ACTION_WARN_DAYS", "KURUL_COMMENT_REMIND_DAYS", "KURUL_HISTORY_MONTHS", "KURUL_COMPANY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(K, "today", lambda: date(2026, 9, 28))


def ok(v, **kw):
    return {"durum": "ok", "deger": v, "hedef": kw.get("hedef"), "onceki": kw.get("onceki"), "oncekiEtiket": kw.get("etiket"),
            "veriSonGunu": kw.get("gun", "2026-08-17"), "kaynak": "Test", "ekran": "/x", "renk": kw.get("renk"), "not": None, "ayrinti": {}}


def fake_pdf(content, summary, stamp) -> bytes:
    return b"%PDF-1.4\n" + K._dump({"c": content, "s": summary, "v": stamp["surum"]}).encode()


# ------------------------------------------------------------------ katalog ve renk


def test_library_seeds_without_thresholds_and_is_idempotent(engine):
    assert K.seed_library(engine, TN) == 0
    items = K.indicators(engine, TN)
    assert len(items) == len(S.LIBRARY)
    assert all(g["esikSari"] is None and g["esikKirmizi"] is None and g["sahip"] is None for g in items)
    assert {g["bolum"] for g in items} <= set(S.BOLUMLER)
    # sağlayıcısı tanımlı her gösterge bilinen bir sağlayıcıya bağlı
    assert {g["saglayici"] for g in S.LIBRARY if g["saglayici"]} <= set(S.PROVIDERS)
    out, diff = K.update_indicator(engine, TN, "cfo", "net_satis", {"esikSari": "900000000", "esikKirmizi": 800000000, "sahip": "CFO"})
    assert out["surum"] == 2 and out["sahip"] == "cfo" and diff["esikKirmizi"]["yeni"] == 800000000
    with pytest.raises(K.KurulError):   # azaldıkça kötü: sarı kırmızıdan küçük olamaz
        K.update_indicator(engine, TN, "cfo", "net_satis", {"esikSari": 1, "esikKirmizi": 5})
    assert K.seed_library(engine, TN) == 0 and K.indicator(engine, TN, "net_satis")["sahip"] == "cfo"



def test_legacy_default_description_is_refreshed_but_edited_one_is_kept(engine):
    import sqlalchemy as sa
    old = K.LEGACY_ACIKLAMA["kasa_banka"][0]
    new = next(g["aciklama"] for g in S.LIBRARY if g["kod"] == "kasa_banka")
    with engine.begin() as c:   # eski kurulum: açıklama eski hazır metinde, bir başkası elle yazılmış
        c.execute(K.INDICATORS.update().where(K.INDICATORS.c.kod == "kasa_banka").values(aciklama=old))
        c.execute(K.INDICATORS.update().where(K.INDICATORS.c.kod == "vadesi_gecmis_alacak").values(aciklama="Bizim tanımımız"))
    assert K.seed_library(engine, TN) == 0
    with engine.connect() as c:
        got = dict(c.execute(sa.select(K.INDICATORS.c.kod, K.INDICATORS.c.aciklama)
                              .where(K.INDICATORS.c.kod.in_(["kasa_banka", "vadesi_gecmis_alacak"]))).all())
    assert got["kasa_banka"] == new and "100 + 102" not in got["kasa_banka"]
    assert got["vadesi_gecmis_alacak"] == "Bizim tanımımız"


def test_state_and_color_rules():
    assert K.state_of(5, "artis_kotu", None, None) is None
    assert K.state_of(5, "artis_kotu", 3, 10) == "sari"
    assert K.state_of(10, "artis_kotu", 3, 10) == "kirmizi"
    assert K.state_of(40, "azalis_kotu", 50, 30) == "sari"
    assert K.state_of(30, "azalis_kotu", 50, 30) == "kirmizi"
    ind = {"yon": "azalis_kotu", "esikSari": None, "esikKirmizi": None}
    assert K.color_of(ind, ok(90.0, renk="sari")) == ("sari", "kaynak")        # kaynak modülün kendi rengi
    assert K.color_of(ind, ok(90.0)) == ("esik_yok", None)
    assert K.color_of({**ind, "esikSari": 95, "esikKirmizi": 80}, ok(90.0, renk="yesil")) == ("sari", "esik")
    assert K.color_of(ind, S.gray("m46", "plan yok")) == (None, None)
    assert K.trend(110, 100, "azalis_kotu") == {"yon": "yukari", "iyi": True, "oran": 0.1}
    assert K.trend(110, 100, "artis_kotu")["iyi"] is False
    assert K.trend(None, 100, "artis_kotu") is None


def test_format_is_turkish():
    assert K.fmt_value(848110178.82, "tl") == "848.110.179 ₺"
    assert K.fmt_short(848110178.82, "tl") == "848,1 Mn ₺"
    assert K.fmt_value(42.66, "yuzde") == "%42,7"
    assert K.fmt_value(-3, "adet") == "−3"
    assert K.fmt_value(None, "tl") == "—"


# ------------------------------------------------------------------ ölçüm


def test_measure_isolates_a_failing_provider(monkeypatch, engine):
    def boom(ctx):
        raise RuntimeError("bağlantı yok")

    monkeypatch.setattr(S, "PROVIDERS", {**S.PROVIDERS, "m45": boom, "m47": lambda ctx: {"risk_kritik": ok(2.0)}})
    inds = K.indicators(engine, TN, only_active=True)
    res = S.measure(S.Ctx(engine=engine, tenant=TN, conf=lambda k, d="": d, today=date(2026, 9, 28)),
                    [g for g in inds if g["saglayici"] in ("m45", "m47", None)])
    assert res["net_satis"]["durum"] == "hata" and "bağlantı yok" in res["net_satis"]["not"]
    assert res["risk_kritik"]["durum"] == "ok" and res["risk_kritik"]["deger"] == 2.0
    assert res["risk_kirmizi_gosterge"]["durum"] == "kaynak_yok"          # sağlayıcı bu kodu döndürmedi
    assert res["stok_riski"]["durum"] == "kaynak_yok" and res["stok_riski"]["deger"] is None


def test_record_gray_has_no_number_and_previous_period_is_compared(engine):
    K.record(engine, TN, "2026-08", {"net_satis": ok(100.0), "butce_satis": ok(95.0, renk="yesil")}, NOW - timedelta(days=30))
    ch = K.record(engine, TN, "2026-09", {"net_satis": ok(120.0), "butce_satis": ok(70.0, renk="kirmizi"),
                                         "stok_riski": S.gray(None, "kaynak yok")}, NOW)
    assert [c["kod"] for c in ch] == ["butce_satis"] and ch[0]["eski"] == "yesil" and ch[0]["yeni"] == "kirmizi"
    p = K.panel(engine, TN, "2026-09")
    flat = {g["kod"]: g for b in p["bolumler"] for g in b["gostergeler"]}
    assert flat["net_satis"]["onceki"] == 100.0 and flat["net_satis"]["oncekiEtiket"] == "Ağustos 2026 ölçümü"
    assert flat["net_satis"]["egilim"]["iyi"] is True
    gray = flat["stok_riski"]
    assert gray["durum"] == "kaynak_yok" and gray["deger"] is None and gray["degerMetin"] is None and gray["renk"] is None
    assert flat["pazarlama_plani"]["durum"] == "olculmedi" and flat["pazarlama_plani"]["deger"] is None
    assert [g["kod"] for g in p["kritik"]] == ["butce_satis"] and p["sayilar"]["yorumsuzRenkli"] == 1
    assert p["donemler"] == ["2026-09", "2026-08"]
    # aynı dönemde yeniden ölçüm üzerine yazar
    K.record(engine, TN, "2026-09", {"net_satis": ok(130.0)}, NOW + timedelta(hours=1))
    d = K.indicator_detail(engine, TN, "net_satis")
    assert [s["deger"] for s in d["seri"]] == [100.0, 130.0]


def test_stale_when_old_or_other_month(engine):
    assert K.is_stale(engine, TN)
    K.record(engine, TN, "2026-09", {"net_satis": ok(1.0)}, datetime.now(timezone.utc))
    assert not K.is_stale(engine, TN)
    assert K.is_stale(engine, TN, datetime.now(timezone.utc) + timedelta(hours=25))


def test_real_providers_report_gray_on_empty_modules(engine):
    """M47 kaydı boş ve M59 günlük turu koşmamış: sıfır değil «kaynak yok»."""
    ctx = S.Ctx(engine=engine, tenant=TN, conf=lambda k, d="": d, today=date(2026, 9, 28))
    r = S.m47(ctx)
    assert r["risk_kritik"]["durum"] == "kaynak_yok" and r["risk_kritik"]["deger"] is None
    assert r["risk_kirmizi_gosterge"]["durum"] == "kaynak_yok"
    d = S.m59(ctx)
    assert all(v["durum"] == "kaynak_yok" for v in d.values()) and set(d) == {"bayi_vadesi_gecmis", "bayi_yogunlasma", "bayi_d_segment"}
    assert S.m6(ctx)["sozlesme_bitecek"]["durum"] == "kaynak_yok"      # CRM bağlantısı verilmedi
    assert S.market_brief(ctx) is None and S.risk_briefing(ctx) is None


# ------------------------------------------------------------------ yorum


def test_comments_owner_direct_others_wait(engine):
    own = K.add_comment(engine, TN, "cfo", "net_satis", "2026-09", "Ağustos kapanışı geç geldi.", approve=True)
    assert own["durum"] == "onayli" and own["onaylayan"] == "cfo"
    other = K.add_comment(engine, TN, "sekreter", "net_satis", "2026-09", "Taslak", approve=False)
    assert other["durum"] == "taslak"
    with pytest.raises(K.KurulError) as e:
        K.delete_comment(engine, TN, own["id"])
    assert e.value.status == 409
    assert K.approve_comment(engine, TN, "cfo", other["id"])["durum"] == "onayli"
    assert K.approved_comments(engine, TN, "2026-09")["net_satis"]["metin"] == "Taslak"
    with pytest.raises(K.KurulError):
        K.add_comment(engine, TN, "cfo", "net_satis", "2026/09", "x", approve=True)


def test_model_text_with_foreign_number_is_not_saved():
    facts = {"deger": "848.110.179 ₺", "onceki": "594.300.000 ₺", "oran": "%42,7"}
    text, err = K.draft_text(lambda m: "Net satış 848.110.179 ₺ oldu; artış %42,7.", "s", facts)
    assert err is None and text
    text, err = K.draft_text(lambda m: "Net satış 900 milyon ₺ oldu.", "s", facts)
    assert text is None and "900" in err
    text, err = K.draft_text(None, "s", facts)
    assert text is None and "tanımlı değil" in err


def test_minutes_suggestions_keep_only_what_notes_say():
    notes = "2. madde: bayi alacağı için Ahmet ödeme planı hazırlayacak, 2026-10-15'e kadar. Bütçe revizyonu kabul edildi."
    raw = ('{"kararlar": [{"gundemSira": 2, "metin": "Bayi ödeme planı hazırlanacak", "aksiyonlar": [{"eylem": "Ödeme planı", '
           '"sahipAdayi": "Ahmet", "terminAdayi": "2026-10-15"}, {"eylem": "Kalan 45 bayiyi ara", "sahipAdayi": "Mehmet", '
           '"terminAdayi": "2026-11-01"}]}, {"metin": "Bütçe revizyonu 12.500.000 ₺ ile kabul edildi"}]}')
    items, dropped = K.parse_minutes("Tabii: " + raw, notes)
    assert len(items) == 1 and items[0]["gundemSira"] == 2
    assert items[0]["aksiyonlar"] == [{"eylem": "Ödeme planı", "sahipAdayi": "Ahmet", "terminAdayi": "2026-10-15"}]
    assert any("45" in d for d in dropped) and any("12.500.000" in d for d in dropped)
    assert K.parse_minutes("bozuk", notes) == ([], ["Zeki AI yanıtı okunamadı (JSON değil)."])


# ------------------------------------------------------------------ toplantı, karar, aksiyon


def _meeting(engine, tarih="2026-10-06"):
    return K.create_meeting(engine, TN, "sekreter", {"tarih": tarih, "katilimcilar": "Başkan, Üye A, Üye A"})


def test_meeting_agenda_decision_action_rules(engine):
    m = _meeting(engine)
    assert m["baslik"] == "Yönetim kurulu toplantısı" and m["katilimcilar"] == ["Başkan", "Üye A"]
    with pytest.raises(K.KurulError):
        K.create_meeting(engine, TN, "s", {"tarih": "06.10.2026"})
    with pytest.raises(K.KurulError):
        K.update_meeting(engine, TN, "s", m["id"], {"saat": "25:00"})
    ag = K.set_agenda(engine, TN, m["id"], [{"baslik": "Bütçe", "tur": "karar"}, {"baslik": "Pazar", "sureDk": "15"}])
    assert [(a["sira"], a["tur"], a["sureDk"]) for a in ag] == [(1, "karar", None), (2, "bilgi", 15)]
    d = K.add_decision(engine, TN, "sekreter", m["id"], {"metin": "Plan onaylandı", "gundemSira": 1,
                                                         "aksiyonlar": [{"eylem": "Revizyonu işle", "sahip": "CFO", "termin": "2026-09-20"}]})
    a = d["aksiyonlar"][0]
    assert a["sahip"] == "cfo" and a["gecikti"] is True and a["durumAdi"] == "Gecikti" and a["kalanGun"] == -8
    with pytest.raises(K.KurulError) as e:   # sahip eylemi değiştiremez
        K.update_action(engine, TN, "cfo", a["id"], {"eylem": "başka"}, full=False)
    assert e.value.status == 403
    out, diff = K.update_action(engine, TN, "cfo", a["id"], {"durum": "tamamlandi", "sonNot": "işlendi"}, full=False)
    assert out["durum"] == "tamamlandi" and out["tamamlanma"] and not out["gecikti"] and "durum" in diff
    out, _ = K.update_action(engine, TN, "sekreter", a["id"], {"durum": "acik"}, full=True)
    assert out["tamamlanma"] is None
    assert K.list_actions(engine, TN, durum="geciken")["total"] == 1
    assert K.list_actions(engine, TN, sahip="CFO")["items"][0]["karar"] == "Plan onaylandı"
    K.update_action(engine, TN, "cfo", a["id"], {"durum": "tamamlandi"}, full=False)
    with pytest.raises(K.KurulError) as e:
        K.delete_decision(engine, TN, d["id"])
    assert e.value.status == 409


def test_previous_decisions_follow_open_and_recently_closed(engine):
    old = _meeting(engine, "2026-06-01")
    last = _meeting(engine, "2026-09-01")
    now = _meeting(engine, "2026-10-06")
    K.add_decision(engine, TN, "s", old["id"], {"metin": "Eski açık", "aksiyonlar": [{"eylem": "süren iş", "termin": "2026-12-01"}]})
    K.add_decision(engine, TN, "s", old["id"], {"metin": "Eski aksiyonsuz"})
    K.add_decision(engine, TN, "s", last["id"], {"metin": "Son toplantı bilgisi"})
    prev = K.previous_decisions(engine, TN, now["id"])
    assert [p["karar"] for p in prev] == ["Eski açık", "Son toplantı bilgisi"]


# ------------------------------------------------------------------ paket


def _content(engine, mid):
    return K.build_content(engine, TN, mid, risk=None, risk_numbers=None, market={"donem": "2026-08", "metin": "Pazar 3,2 büyüdü"})


def test_package_freeze_is_immutable_and_versioned(engine):
    m = _meeting(engine)
    K.record(engine, TN, "2026-09", {"net_satis": ok(848110178.82), "butce_satis": ok(70.0, renk="kirmizi")}, NOW)
    p1 = K.compile_package(engine, TN, "sekreter", m["id"], _content(engine, m["id"]))
    assert p1["surum"] == 1 and p1["durum"] == "taslak"
    assert p1["icerik"]["eksikYorum"] == [{"kod": "butce_satis", "ad": K.indicator(engine, TN, "butce_satis")["ad"], "sahip": None}]
    # özet taslağı onaylanmadan dondurulmaz
    K.start_summary(engine, TN, p1["id"])
    K.finish_summary(engine, p1["id"], "Net satış 848.110.179 ₺.", None)
    with pytest.raises(K.KurulError) as e:
        K.freeze_package(engine, TN, "gm", p1["id"], fake_pdf)
    assert e.value.status == 409
    edited = K.edit_summary(engine, TN, p1["id"], "Net satış 848.110.179 ₺; hedef 999 milyon.")
    assert edited["ozetKaynak"] == "insan" and "999" in edited["olguDisiSayilar"]
    K.approve_summary(engine, TN, "gm", p1["id"])
    frozen = K.freeze_package(engine, TN, "gm", p1["id"], fake_pdf)
    assert frozen["durum"] == "donduruldu" and frozen["pdfSha256"]
    data, _ = K.package_pdf(engine, TN, p1["id"])
    assert hashlib.sha256(data).hexdigest() == frozen["pdfSha256"]
    # kaynak değer değişir: dondurulmuş içerik ve PDF aynı kalır
    K.record(engine, TN, "2026-09", {"net_satis": ok(900000000.0)}, NOW + timedelta(hours=2))
    again = K.package(engine, TN, p1["id"])
    assert again["icerikSha256"] == frozen["icerikSha256"] and K.package_pdf(engine, TN, p1["id"])[0] == data
    assert any(g["deger"] == 848110178.82 for b in again["icerik"]["gostergeler"] for g in b["gostergeler"])
    with pytest.raises(K.KurulError):
        K.edit_summary(engine, TN, p1["id"], "değişiklik")
    with pytest.raises(K.KurulError):
        K.freeze_package(engine, TN, "gm", p1["id"], fake_pdf)
    # dosya değişirse verilmez
    Path(_pdf_path(engine, p1["id"])).write_bytes(b"%PDF-1.4 bozuk")
    with pytest.raises(K.KurulError) as e:
        K.package_pdf(engine, TN, p1["id"])
    assert e.value.status == 409
    # yeni derleme yeni sürüm açar ve yeni değeri taşır
    p2 = K.compile_package(engine, TN, "sekreter", m["id"], _content(engine, m["id"]))
    assert p2["surum"] == 2 and p2["id"] != p1["id"]
    assert any(g["deger"] == 900000000.0 for b in p2["icerik"]["gostergeler"] for g in b["gostergeler"])
    # taslak yeniden derlenince aynı sürüm kalır, özet düşer
    K.edit_summary(engine, TN, p2["id"], "x")
    p2b = K.compile_package(engine, TN, "sekreter", m["id"], _content(engine, m["id"]))
    assert p2b["id"] == p2["id"] and p2b["ozetDurum"] == "yok"


def _pdf_path(engine, pid):
    with engine.connect() as c:
        return c.execute(K.sa.select(K.PACKAGES.c.pdf_yol).where(K.PACKAGES.c.id == pid)).scalar()


def test_summary_facts_carry_only_package_numbers(engine):
    m = _meeting(engine)
    K.record(engine, TN, "2026-09", {"net_satis": ok(848110178.82, onceki=594300000.0, etiket="Geçen yıl aynı dönem")}, NOW)
    p = K.compile_package(engine, TN, "s", m["id"], _content(engine, m["id"]))
    facts = K.summary_facts(p["icerik"])
    net = next(g for g in facts["gostergeler"] if g["ad"].startswith("Net satış"))
    assert net["deger"] == "848.110.179 ₺" and net["onceki"] == "594.300.000 ₺"
    assert not K.foreign_numbers("Net satış 848.110.179 ₺, geçen yıl 594.300.000 ₺.", facts)
    assert K.foreign_numbers("Net satış 850 milyon ₺.", facts) == {"850"}
    assert facts["pazarOzetiVar"] is True


def test_distribution_rows_and_frozen_requirement(engine):
    ad = K.save_member(engine, TN, "s", None, {"ad": "Başkan", "kurul": "yonetim", "adHesabi": "Baskan"})
    ext = K.save_member(engine, TN, "s", None, {"ad": "Dış Üye", "kurul": "danisma", "eposta": "dis@ornek.com"})
    rows = K.distribution_rows(engine, TN, [ad["id"], ext["id"]])
    assert [(r["kanal"], r["alici"]) for r in rows] == [("baglanti", "Başkan"), ("pdf", "Dış Üye")]
    assert "elle" in rows[1]["sonuc"]
    m = _meeting(engine)
    p = K.compile_package(engine, TN, "s", m["id"], _content(engine, m["id"]))
    with pytest.raises(K.KurulError):
        K.record_distribution(engine, TN, "gm", p["id"], rows)
    K.freeze_package(engine, TN, "gm", p["id"], fake_pdf)
    out = K.record_distribution(engine, TN, "gm", p["id"], rows)
    assert out["durum"] == "dagitildi" and len(out["dagitim"]) == 2
    # dağıtım kaydı olan üye silinmez, pasife alınır
    K.delete_member(engine, TN, ext["id"])
    assert next(x for x in K.members(engine, TN) if x["id"] == ext["id"])["aktif"] is False
    assert not K.visible_package({"durum": "taslak"}, False) and K.visible_package({"durum": "donduruldu"}, False)


def test_reminders_once(engine):
    m = _meeting(engine, "2026-10-01")          # 3 iş günü sonra
    K.add_decision(engine, TN, "s", m["id"], {"metin": "K", "aksiyonlar": [
        {"eylem": "yakında", "sahip": "a", "sahipEposta": "a@timas.com.tr", "termin": "2026-10-02"},
        {"eylem": "uzak", "sahip": "b", "termin": "2026-12-30"},
        {"eylem": "geçti", "sahip": "c", "termin": "2026-09-01"}]})
    K.update_indicator(engine, TN, "cfo", "butce_satis", {"sahip": "cfo", "sahipEposta": "cfo@timas.com.tr"})
    K.record(engine, TN, "2026-09", {"butce_satis": ok(70.0, renk="kirmizi")}, NOW)
    due = K.due_reminders(engine, TN)
    keys = sorted(x["key"].split(":")[0] for x in due)
    assert keys == ["aksiyon-gecti", "aksiyon-yaklasti", "yorum"]
    K.mark_sent(engine, TN, [x["key"] for x in due])
    assert K.due_reminders(engine, TN) == []


def test_pdf_renders_when_fpdf_is_available(engine):
    pytest.importorskip("fpdf")
    from semantic_bridge import kurul_pdf

    m = _meeting(engine)
    K.record(engine, TN, "2026-09", {"net_satis": ok(848110178.82), "stok_riski": S.gray(None, "kaynak yok")}, NOW)
    p = K.compile_package(engine, TN, "s", m["id"], _content(engine, m["id"]))
    data = kurul_pdf.render(p["icerik"], "## Genel durum\n- Net satış 848.110.179 ₺.", {"surum": 1, "donduran": "gm",
                                                                                      "dondurma": NOW.isoformat(), "icerikSha256": "ab" * 32})
    assert data.startswith(b"%PDF") and len(data) > 1000


# ------------------------------------------------------------------ yetki


def test_kurul_access_rules():
    assert A.rule_for("/api/v1/kurul/run-due") == A.SYSTEM
    assert A.rule_for("/api/v1/kurul/panel") == frozenset({"sayfa:kurul"})
    assert A.features_for("GET", "/api/v1/kurul/packages/p1/document.pdf") == ["ozellik:veri.disa-aktar"]
    assert A.features_for("POST", "/api/v1/kurul/packages/p1/freeze") == []        # açıkça verilen, uçta
    assert {"sayfa:kurul", "ozellik:kurul.hazirla", "ozellik:kurul.dondur", "ozellik:kurul.gosterge",
            "ozellik:kurul.aksiyon"} <= A.explicit_keys()
    assert {"ozellik:kurul.yorum"} <= A.all_keys() - A.explicit_keys()
    page = next(p for p in A.catalog()["pages"] if p["key"] == "sayfa:kurul")
    assert page["area"] == "finans" and page.get("explicit") is True


def test_bridge_gate_and_ownership(monkeypatch, store, settings, tmp_path):
    from semantic_bridge import kurul_pdf
    from semantic_layer.tests.test_access import TENANT, _app

    monkeypatch.setattr(K, "is_stale", lambda *a, **k: False)       # testte arka plan ölçümü başlamasın
    monkeypatch.setattr(kurul_pdf, "render", fake_pdf)
    app, client = _app(monkeypatch, store, settings)
    engine = store.engine
    A.ensure(engine, TENANT)
    a, m_, z = ({"cookie": f"timas_session={x}"} for x in ("a", "m", "z"))
    # Açıkça verilen sayfa: «Herkes» bütün yetkilerle açıkken bile kurul sayfası kapalı.
    assert client.get("/api/v1/kurul/panel", headers=a).status_code == 403
    assert client.get("/api/v1/kurul/panel", headers=z).status_code == 200
    rid = A.save_role(engine, TENANT, "zekiai", {"name": "Kurul üyesi", "perms": ["sayfa:kurul"]})["id"]
    A.add_binding(engine, TENANT, "zekiai", rid, {"type": "user", "subject": "mehmet"})
    A.invalidate()
    assert client.get("/api/v1/kurul/panel", headers=m_).status_code == 200
    assert client.post("/api/v1/kurul/meetings", json={"tarih": "2026-10-06"}, headers=m_).status_code == 403
    assert client.post("/api/v1/kurul/meetings", json={}, headers=z).status_code == 400
    mt = client.post("/api/v1/kurul/meetings", json={"tarih": "2026-10-06"}, headers=z).json()
    d = client.post(f"/api/v1/kurul/meetings/{mt['id']}/decisions",
                    json={"metin": "K", "aksiyonlar": [{"eylem": "iş", "sahip": "mehmet"}, {"eylem": "başkası", "sahip": "ayse"}]}, headers=z).json()
    mine, other = d["aksiyonlar"][0]["id"], d["aksiyonlar"][1]["id"]
    assert client.patch(f"/api/v1/kurul/actions/{mine}", json={"durum": "tamamlandi"}, headers=m_).status_code == 403   # kurul.aksiyon yok
    rid2 = A.save_role(engine, TENANT, "zekiai", {"name": "Kurul aksiyonu", "perms": ["ozellik:kurul.aksiyon"]})["id"]
    A.add_binding(engine, TENANT, "zekiai", rid2, {"type": "user", "subject": "mehmet"})
    A.invalidate()
    assert client.patch(f"/api/v1/kurul/actions/{mine}", json={"durum": "tamamlandi"}, headers=m_).status_code == 200
    assert client.patch(f"/api/v1/kurul/actions/{mine}", json={"eylem": "x"}, headers=m_).status_code == 403
    assert client.patch(f"/api/v1/kurul/actions/{other}", json={"durum": "tamamlandi"}, headers=m_).status_code == 403
    pk = client.post(f"/api/v1/kurul/meetings/{mt['id']}/packages", headers=z)
    assert pk.status_code == 201
    pid = pk.json()["id"]
    assert client.get(f"/api/v1/kurul/packages/{pid}", headers=m_).status_code == 404           # taslak üyeye görünmez
    assert client.post(f"/api/v1/kurul/packages/{pid}/freeze", headers=m_).status_code == 403
    assert client.post(f"/api/v1/kurul/packages/{pid}/freeze", headers=z).json()["durum"] == "donduruldu"
    got = client.get(f"/api/v1/kurul/packages/{pid}", headers=m_)
    assert got.status_code == 200 and got.json()["dagitim"] == []
    pdf = client.get(f"/api/v1/kurul/packages/{pid}/document.pdf", headers=z)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert client.get(f"/api/v1/kurul/packages/{pid}", headers=z).json()["dagitim"][0]["kanal"] == "indirme"
    assert client.post("/api/v1/kurul/run-due", headers=a).status_code == 403


def test_day_reads_utc_data_end_as_istanbul_day():
    """M48 Logo veri sonunu UTC saklar; gösterge İstanbul gününü okumalı (2026-09-28 kabulü: 16.08 ↔ 17.08)."""
    assert S._day("2026-08-16T21:00:00+00:00") == "2026-08-17"
    assert S._day(datetime(2026, 8, 16, 21, 0, tzinfo=timezone.utc)) == "2026-08-17"
    assert S._day("2026-08-17") == "2026-08-17" and S._day(date(2026, 8, 17)) == "2026-08-17"
    assert S._day(None) is None and S._day("") is None
