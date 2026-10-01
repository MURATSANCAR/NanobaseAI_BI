"""M38 Müşteri ilişkileri: değer pencereleri (Logo kesimine göre), medyan alım aralığı ve yedekleri, kural risk puanı ve
nedenleri (donmuş veri, CRM siparişi yumuşatır, kayıp düzeyi), iki yıl kopyasının firma yıllarına kırpılması (çift sayım
yok), M30 atamasıyla portföy kapsamı, segmentler, aksiyon ve 30/90 gün sonucu, veri sağlığı bulguları (Logo bağı, tekrar,
sahipsiz, ortak hesap, izin çelişkisi, güvenlik) ve yaşam döngüsü (kendiliğinden kapanma, «CRM'de düzeltildi» →
doğrulama ya da yeniden açılma), SQL biçimi (kişisel kolon yok, `new_kargofirmasi`'na sorgu yok) ve yetki kuralları.

Sözleşme: model puan ve rakam üretmez; kişi yalnız kendi portföyünü görür; CRM'e yazılmaz; şahıs carisinin adı modele ve
veri sağlığı listesine gitmez.
"""

from __future__ import annotations

from datetime import date

import pytest

from semantic_bridge import access as A
from semantic_bridge import crm_people_rules as R
from semantic_bridge import musteri as M
from semantic_bridge import musteri_sources as S
from semantic_layer.store.catalog_store import open_store

T = "t1"
U1 = "11111111-1111-1111-1111-111111111111"
U2 = "22222222-2222-2222-2222-222222222222"
U3 = "33333333-3333-3333-3333-333333333333"
ACC1 = "aaaaaaaa-0000-0000-0000-000000000001"
ACC2 = "aaaaaaaa-0000-0000-0000-000000000002"
ACC3 = "aaaaaaaa-0000-0000-0000-000000000003"
ACC4 = "aaaaaaaa-0000-0000-0000-000000000004"
KESIM = date(2026, 8, 17)
NOW = date(2026, 9, 28)


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    M._ready.discard(id(e))
    M.ensure(e)
    return e


def _st(**kw):
    st = M.settings_from(lambda k, d="": d)
    st.update(kw)
    return st


def _days(pairs):
    return {g: {"satis": s, "iade": i, "fatura": 1.0 if s else 0.0} for g, s, i in pairs}


# ------------------------------------------------------------------ değer ve aralık


def test_value_windows_end_at_the_logo_cutoff():
    days = _days([("2026-08-10", 1000, 100), ("2025-09-01", 500, 0), ("2025-08-17", 300, 0), ("2024-09-01", 2000, 0),
                  ("2026-09-01", 9999, 0)])                                   # kesimden sonrası pencereye girmez
    s = M.value_stats(days, KESIM)
    assert s["net_12ay"] == 1400 and s["net_onceki_12ay"] == 2300           # 2025-08-17 önceki pencerenin son günü
    assert s["net_yil"] == 900 and s["iade_orani_12ay"] == round(100 / 1500, 4) and s["iade_orani_onceki"] == 0
    assert s["son_fatura"] == "2026-08-10" and s["gun_son_alim"] == 7 and s["degisim"] == round(1400 / 2300 - 1, 4)


def test_median_interval_and_fallbacks():
    assert M.median_interval(["2026-01-01", "2026-01-31", "2026-03-01", "2026-03-11"]) == 29.0
    assert M.median_interval(["2026-01-01"]) is None
    stats = {"a": {"alim_gunleri": ["2026-01-01", "2026-01-11", "2026-01-21"]},
             "b": {"alim_gunleri": ["2026-02-01"]}, "c": {"alim_gunleri": ["2026-02-01"]}, "d": {"alim_gunleri": []}}
    out = M.resolve_intervals(stats, {"a": "KITAPCI", "b": "KITAPCI", "c": "BAYI"}, 3, 60)
    assert out["a"] == (10.0, "kendi") and out["b"] == (10.0, "kanal") and out["c"] == (10.0, "genel")
    assert out["d"] == (None, None)
    assert M.resolve_intervals({"x": {"alim_gunleri": ["2026-01-01"]}}, {}, 3, 60)["x"] == (60.0, "ayar")


# ------------------------------------------------------------------ kayıp riski


def _acc(**kw):
    base = {"net_12ay": 40000, "net_onceki_12ay": 100000, "gun_son_alim": 60, "medyan_aralik_gun": 20.0,
            "iade_orani_12ay": 0.30, "iade_orani_onceki": 0.05, "alim_gunleri": ["2026-06-18"], "son_fatura": "2026-06-18",
            "son_siparis": "2026-03-01", "crm_account_id": ACC1}
    return {**base, **kw}


def test_risk_reasons_are_rule_chips_and_capped():
    pts, level, chips = M.risk(_acc(), _st(), NOW)
    keys = {c["key"] for c in chips}
    assert keys == {"aralik", "dusus", "iade", "siparis"} and pts == 100.0 and level == "yuksek"
    assert any("60 gündür alım yok (olağan aralık 20 gün)" in c["label"] for c in chips)
    assert M.rule_summary(chips).endswith(".")


def test_crm_order_after_the_cutoff_softens_and_blocks_lost():
    quiet = _acc(net_12ay=100000, iade_orani_12ay=0.05, gun_son_alim=200, son_siparis="2026-09-20")
    pts, level, chips = M.risk(quiet, _st(), NOW)
    aralik = next(c for c in chips if c["key"] == "aralik")
    assert aralik["points"] == 20.0 and "CRM'de 2026-09-20 tarihli sipariş var" in aralik["label"]
    assert level != "kayip"
    lost = M.risk({**quiet, "son_siparis": "2026-01-01"}, _st(), NOW)
    assert lost[1] == "kayip"                                               # 200 ≥ max(180, 4 × 20)


def test_quiet_and_never_bought():
    assert M.risk(_acc(gun_son_alim=None), _st(), NOW) == (0.0, "yok", [])
    ok = M.risk(_acc(net_12ay=110000, gun_son_alim=10, iade_orani_12ay=0.05, son_siparis="2026-09-10"), _st(), NOW)
    assert ok[1] == "dusuk" and ok[2] == []


def test_segments_and_bands():
    bands = M.value_bands({"a": 800, "b": 150, "c": 50, "d": 0})
    assert bands == {"a": "A", "b": "B", "c": "C", "d": "-"}
    assert M.trend(-0.2, 100) == "dusen" and M.trend(0.2, 100) == "buyuyen" and M.trend(None, 0) == "yeni"


# ------------------------------------------------------------------ iki yıl kopyası


def test_firm_windows_never_count_a_day_twice():
    firms = {2021: "211", 2022: "211", 2023: "211", 2024: "211", 2025: "211", 2026: "411"}
    w = S.firm_windows(firms, date(2024, 8, 18), KESIM)
    assert w == [("211", date(2024, 8, 18), date(2025, 12, 31)), ("411", date(2026, 1, 1), KESIM)]
    sql = S.daily_sales_sql("411", date(2026, 1, 1), KESIM)
    assert "LINETYPE = 0" in sql and "INVOICEREF <> 0" in sql and "TRCODE IN (2,3,7,8,9)" in sql and "< '2026-08-18'" in sql
    assert "GROUP BY C.CODE, SH.DATE_" in sql and "SELECT *" not in sql

    rows = {"411": [{"CODE": "120.01", "GUN": "2026-02-01", "SATIS": 100, "IADE": 0, "FATURA": 1}],
            "211": [{"CODE": "120.01", "GUN": "2025-02-01", "SATIS": 50, "IADE": 5, "FATURA": 1}]}

    def run(sql):
        return rows["411" if "LG_411_" in sql else "211"]
    daily = S.read_daily(run, firms, date(2024, 8, 18), KESIM)
    assert daily == {"120.01": {"2026-02-01": {"satis": 100.0, "iade": 0.0, "fatura": 1.0},
                                "2025-02-01": {"satis": 50.0, "iade": 5.0, "fatura": 1.0}}}


def test_clients_merge_by_code_current_year_wins():
    cur = [{"REF": 5, "CODE": "120.01", "UNVAN": "A", "IL": "X", "KANAL": "KITAPCI"}]
    old = [{"REF": 5, "CODE": "120.09", "UNVAN": "B", "IL": "Y", "KANAL": "BAYI"},
           {"REF": 7, "CODE": "120.01", "UNVAN": "A eski", "IL": "X", "KANAL": "KITAPCI"}]
    out = S.read_clients(lambda sql: cur if "LG_411_" in sql else old, "411", ["211"])
    by = {c["code"]: c for c in out}
    assert by["120.01"]["unvan"] == "A" and by["120.09"]["ref"] == -1 and out[-1]["code"] == "120.01"


# ------------------------------------------------------------------ gece turu: satırlar ve kapsam


USERS = [{"id": U1, "ad": "Ayşe Bmt", "domain": "TIMAS\\ayseb", "bmt": 1},
         {"id": U2, "ad": "Timas CRM", "domain": "TIMAS\\servis", "bmt": 0}]


def _crm_acc(aid, code, owner, **kw):
    return {"account_id": aid, "unvan": f"Kitapçı {code}", "cari_kodu": code, "logicalref": None, "owner_id": owner,
            "owner_type": 8, "bmt_il_cari": 1, "kanal": 100000001, "il": "Trabzon", "il_temsilci": None, **kw}


def _data():
    daily = {"120.01": _days([("2026-01-05", 10000, 0), ("2026-02-05", 10000, 0), ("2026-03-05", 10000, 0),
                              ("2025-06-01", 60000, 0)]),
             "120.02": _days([("2026-08-01", 5000, 0), ("2025-08-01", 5000, 0)])}
    return {"now": NOW.isoformat(), "warnings": [],
            "logo": {"kesim": KESIM.isoformat(), "daily": daily,
                     "cal": {"year": 2026, "firm": "411", "prevFirm": "211", "firms": {"2025": "211", "2026": "411"}},
                     "clients": [{"ref": 5, "code": "120.01", "unvan": "A Kitabevi", "il": "TRABZON", "kanal": "KITAPCI"},
                                 {"ref": 6, "code": "120.02", "unvan": "Ali Veli", "il": "RİZE", "kanal": "BAYI"},
                                 {"ref": 7, "code": "120.03", "unvan": "C Ltd", "il": "RİZE", "kanal": "BAYI"}],
                     "codes": {"411": ["120.01\x005", "120.02\x006", "120.03\x007"]}},
            "crm": {"users": USERS, "allUsers": [{"id": U1, "ad": "Ayşe Bmt", "kapali": 0}, {"id": U2, "ad": "Timas CRM", "kapali": 0},
                                                 {"id": U3, "ad": "Eski", "kapali": 1}],
                    "accounts": [_crm_acc(ACC1, "120.01", U1), _crm_acc(ACC2, "120.02", U2)],
                    "health": [{"account_id": ACC1, "ad": "A Kitabevi Ltd. Şti.", "cari_kodu": "120.01", "logicalref": "5",
                                "owner_id": U1, "owner_type": 8, "kanal": 100000001, "kanal_tipi": 100000006, "il": "Trabzon",
                                "vergi_dairesi": "Hızırbey", "iys_tip": 1, "toplu_yok": 0, "izin_kaniti": 1},
                               {"account_id": ACC2, "ad": "Ali Veli", "cari_kodu": "120.02", "logicalref": None,
                                "owner_id": U2, "owner_type": 8, "kanal": None, "kanal_tipi": None, "il": "Rize",
                                "iys_tip": 0, "toplu_yok": 0, "izin_kaniti": 0},
                               {"account_id": ACC3, "ad": "A Kitabevi", "cari_kodu": None, "logicalref": None,
                                "owner_id": U3, "owner_type": 8, "kanal": 100000001, "kanal_tipi": None, "il": "Trabzon",
                                "vergi_dairesi": "Hızırbey", "iys_tip": 1, "toplu_yok": 1, "izin_kaniti": 0,
                                "eposta_izin_tarihi": "2026-01-01"},
                               {"account_id": ACC4, "ad": "Deniz Kitapevi", "cari_kodu": "999.99", "logicalref": None,
                                "owner_id": U1, "owner_type": 9, "kanal": 100000001, "kanal_tipi": None, "il": "Ordu",
                                "iys_tip": 1, "toplu_yok": 0, "izin_kaniti": 1}],
                    "orders": [{"account_id": ACC1, "son": "2026-03-01", "adet": 3}, {"account_id": ACC3, "son": "2019-01-01", "adet": 0}],
                    "contacts": [{"contact_id": "cccccccc-0000-0000-0000-000000000001", "account_id": ACC1, "kvkk": 0, "iys": 1,
                                  "toplu_yok": 0, "veri_durumu": 2},
                                 {"contact_id": "cccccccc-0000-0000-0000-000000000002", "account_id": ACC1, "kvkk": 1, "iys": 1,
                                  "toplu_yok": 0, "veri_durumu": None}],
                    "campaigns": [{"account_id": ACC3, "son": "2026-05-01", "adet": 2}],
                    "visits": [], "security": [{"kayit_id": "new_webuserBase.new_sifre", "ozet": "x (3 dolu satır)", "onem": "yuksek"}]}}


def test_build_accounts_scope_and_person_flag(engine):
    rows, info = M.build_accounts(_data(), _st(), {"120.01": "2026-09-01"}, {})
    by = {r["cari_kodu"]: r for r in rows}
    a = by["120.01"]
    assert a["temsilci"] == "ayseb" and a["net_12ay"] == 30000 and a["net_onceki_12ay"] == 60000 and a["son_ziyaret"] == "2026-09-01"
    assert a["medyan_aralik_gun"] == 31.0 and a["aralik_kaynagi"] == "kendi" and a["gun_son_alim"] == 165
    assert a["risk_duzeyi"] in ("yuksek", "kayip") and a["risk_gecis"] == NOW.isoformat() and a["neden_ozeti"]
    assert by["120.02"]["temsilci"] is None                                   # ortak hesap: temsilcisiz
    assert by["120.02"]["bireysel_mi"] is True and by["120.03"]["risk_duzeyi"] == "yok"
    assert info["accounts"] == 3 and info["assigned"] == 1
    M.write_accounts(engine, T, rows)
    assert [r["cari_kodu"] for r in M.account_rows(engine, T, "ayseb")] == ["120.01"]
    assert len(M.account_rows(engine, T, None)) == 3
    with pytest.raises(M.MusteriError) as e:
        M.in_scope(engine, T, "baskasi", "120.01", False)
    assert e.value.status == 403
    # Düzey geçişi korunur; Zeki AI özeti nedenler değişmedikçe kalır.
    M.save_summary(engine, T, "120.01", "Zeki AI metni", "zeki", a["ozet_hash"])
    rows2, _ = M.build_accounts(_data(), _st(), {}, M.previous_accounts(engine, T))
    a2 = {r["cari_kodu"]: r for r in rows2}["120.01"]
    assert a2["neden_ozeti"] == "Zeki AI metni" and a2["ozet_kaynagi"] == "zeki" and a2["onceki_risk_duzeyi"] == a["risk_duzeyi"]


def test_overview_filters_and_sorts(engine):
    rows, _ = M.build_accounts(_data(), _st(), {}, {})
    ov = M.overview(rows, [], {"puan": 80.0})
    assert ov["kpi"]["cari"] == 3 and ov["kpi"]["saglik"] == 80.0
    assert {k["kanal"] for k in ov["kanallar"]} == {"KITAPCI", "BAYI"}
    assert sum(k["net12"] for k in ov["kanallar"]) == ov["kpi"]["net12"]
    assert [r["cari_kodu"] for r in M.filter_rows(rows, kanal="kitapci")] == ["120.01"]
    assert [r["cari_kodu"] for r in M.filter_rows(rows, q="ali")] == ["120.02"]
    assert all(r["risk_duzeyi"] in ("yuksek", "kayip") for r in M.filter_rows(rows, risk_="riskli"))
    segs = M.segments_of([{**r, **M.card(r)} for r in rows], NOW.isoformat())
    assert sum(s["boyut"] for s in segs) == 2                                 # değeri olmayan cari segmentte değil


# ------------------------------------------------------------------ aksiyon


def test_actions_and_outcomes(engine):
    rows, _ = M.build_accounts(_data(), _st(), {}, {})
    M.write_accounts(engine, T, rows)
    acc = M.in_scope(engine, T, "ayseb", "120.01", False)
    with pytest.raises(M.MusteriError):
        M.add_action(engine, T, "ayseb", acc, {"tur": "yanlis", "aciklama": "x"})
    with pytest.raises(M.MusteriError):
        M.add_action(engine, T, "ayseb", acc, {"tur": "arama", "aciklama": " "})
    a = M.add_action(engine, T, "ayseb", acc, {"tur": "ziyaret", "aciklama": "Çocuk yeni çıkanlar", "termin": "2026-10-02"})
    assert a["sahip"] == "ayseb" and a["riskDuzeyi"] == acc["risk_duzeyi"] and a["durum"] == "acik"
    with pytest.raises(M.MusteriError) as e:
        M.update_action(engine, T, "baskasi", a["id"], {"durum": "yapildi"}, False)
    assert e.value.status == 403
    out, diff = M.update_action(engine, T, "ayseb", a["id"], {"durum": "yapildi", "sonucNotu": "Sipariş sözü"}, False)
    assert out["durum"] == "yapildi" and "durum" in diff
    act = {**M.get_action(engine, T, a["id"]), "tarih": "2026-01-01"}
    daily = {"120.01": _days([("2025-12-20", 700, 0), ("2026-01-05", 1000, 100), ("2026-03-05", 500, 0)])}
    upd = M.action_outcomes([act], daily, KESIM)[0]
    assert upd["onceki_30g"] == 700 and upd["sonuc_30g"] == 900 and upd["sonuc_90g"] == 1400
    young = M.action_outcomes([{**act, "tarih": "2026-08-01"}], daily, KESIM)[0]
    assert young["sonuc_30g"] is None and young["sonuc_90g"] is None          # pencere dolmadan sıfır yazılmaz
    M.write_outcomes(engine, [upd])
    eff = M.action_effect(M.list_actions(engine, T))
    assert eff["gun30"] == {"olgun": 1, "alan": 1, "oran": 1.0}


# ------------------------------------------------------------------ veri sağlığı


def test_health_findings_rules_and_masking():
    found, ask, info = M.health_findings(_data(), _st(), {}, T)
    by = {}
    for f in found:
        by.setdefault(f["tur"], []).append(f)
    assert {f["kayit_id"] for f in by["logo_bagi_yok"]} == {ACC3, ACC4}          # ACC2: kodu Logo'da var
    assert [f["kayit_id"] for f in by["eksik_kanal"]] == [ACC2]
    assert {f["kayit_id"] for f in by["sahipsiz"]} == {ACC3, ACC4}              # devre dışı sahip, takım
    assert [f["kayit_id"] for f in by["ortak_hesap"]] == [ACC2]
    iz = {(f["varlik"], f["kayit_id"], f["eslesen_kayit_id"]) for f in by["izin_celiskisi"]}
    assert ("account", ACC2, None) in iz and ("account", ACC3, "kampanya") in iz
    assert ("contact", "cccccccc-0000-0000-0000-000000000001", None) in iz and len(iz) == 3
    dup = by["olasi_tekrar"]
    assert len(dup) == 1 and {dup[0]["kayit_id"], dup[0]["eslesen_kayit_id"]} == {ACC1, ACC3} and dup[0]["olasilik"] == 0.9
    assert by["guvenlik"][0]["varlik"] == "sistem"
    assert next(f for f in found if f["kayit_id"] == ACC2)["ad"] == "Şahıs carisi"   # bireysel cari maskeli
    assert info["etkin_cari"] == 4 and info["bulgulu_cari"] == 4 and info["puan"] == 0.0
    assert info["veriDurumu"] == {"2": 1, "bos": 1} and ask == []


def test_fuzzy_duplicates_go_to_the_model_and_decisions_stick():
    accs = [{"account_id": ACC1, "ad": "Deniz Kitabevi Yayıncılık", "il": "Ordu", "cari_kodu": "1", "iys_tip": 1},
            {"account_id": ACC2, "ad": "Deniz Kitabevleri", "il": "Ordu", "cari_kodu": "2", "iys_tip": 1},
            {"account_id": ACC3, "ad": "Deniz Kitabevi", "il": "Rize", "cari_kodu": "3", "iys_tip": 1}]
    pairs = M.duplicate_candidates(accs, 0.86, 6)
    assert len(pairs) == 1 and pairs[0]["sor"] is True and {pairs[0]["a"], pairs[0]["b"]} == {ACC1, ACC2}
    assert "Ordu" in M.dup_prompt(accs[0], accs[1]) and "Vergi dairesi" in M.dup_prompt(accs[0], accs[1])
    data = _data()
    data["crm"]["health"] = accs
    data["crm"]["security"], data["crm"]["contacts"], data["crm"]["campaigns"] = [], [], []
    _, ask, _ = M.health_findings(data, _st(), {}, T)
    assert len(ask) == 1
    found, ask, _ = M.health_findings(data, _st(), {pairs[0]["cift"]: {"karar": "farkli", "olasilik": 0.9}}, T)
    assert ask == [] and not [f for f in found if f["tur"] == "olasi_tekrar"]
    found, _, _ = M.health_findings(data, _st(), {pairs[0]["cift"]: {"karar": "ayni", "olasilik": 0.93}}, T)
    assert [f["olasilik"] for f in found if f["tur"] == "olasi_tekrar"] == [0.93]
    person = [{**a, "iys_tip": 0} for a in accs]
    data["crm"]["health"] = person
    _, ask, _ = M.health_findings(data, _st(), {}, T)
    assert ask == []                                                         # şahıs carisi modele sorulmaz


def test_finding_lifecycle(engine):
    f1 = {"id": "f1", "tur": "logo_bagi_yok", "varlik": "account", "kayit_id": ACC1, "eslesen_kayit_id": None,
          "cari_kodu": "1", "ad": "A", "olasilik": None, "ozet": "x", "onem": "orta"}
    f2 = {**f1, "id": "f2", "kayit_id": ACC2}
    assert M.sync_findings(engine, T, [f1, f2], "2026-09-27")["yeni"] == 2
    with pytest.raises(M.MusteriError):
        M.mark_finding(engine, T, "crm", "f1", {"durum": "yoksay"}, False)        # gerekçesiz yok sayılmaz
    M.mark_finding(engine, T, "crm", "f1", {"durum": "crmde_duzeltildi"}, False)
    M.mark_finding(engine, T, "crm", "f2", {"durum": "crmde_duzeltildi"}, False)
    st = M.sync_findings(engine, T, [f2], "2026-09-28")                         # f1 düzelmiş, f2 hâlâ var
    assert st["dogrulanan"] == 1 and st["tutmayan"] == 1
    rows = {r["id"]: r for r in M.list_findings(engine, T, durum="")}
    assert rows["f1"]["durum"] == "dogrulandi" and rows["f2"]["durum"] == "acik" and "hâlâ var" in rows["f2"]["isaret_notu"]
    st = M.sync_findings(engine, T, [], "2026-09-29")
    assert st["kapanan"] == 1 and {r["id"]: r["durum"] for r in M.list_findings(engine, T, durum="")}["f2"] == "kapandi"
    assert M.sync_findings(engine, T, [f2], "2026-09-30")["yeniden_acilan"] == 1
    sec = {**f1, "id": "s1", "tur": "guvenlik", "varlik": "sistem", "kayit_id": "t.k"}
    M.sync_findings(engine, T, [f2, sec], "2026-10-01")
    assert all(r["tur"] != "guvenlik" for r in M.list_findings(engine, T, security=False))
    with pytest.raises(M.MusteriError) as e:
        M.mark_finding(engine, T, "crm", "s1", {"durum": "crmde_duzeltildi"}, False)
    assert e.value.status == 403
    assert "guvenlik" not in M.finding_counts(engine, T, False)
    assert M.findings_csv(M.list_findings(engine, T))[:3] == b"\xef\xbb\xbf"


def test_score_history(engine):
    assert M.save_score(engine, T, {"tarih": "2026-09-27", "puan": 80.0, "etkin_cari": 10, "bulgulu_cari": 2, "sayilar": {}}) is None
    assert M.save_score(engine, T, {"tarih": "2026-09-28", "puan": 75.0, "etkin_cari": 10, "bulgulu_cari": 3, "sayilar": {}}) == 80.0
    assert [p["puan"] for p in M.score_history(engine, T, 3650)] == [80.0, 75.0]


# ------------------------------------------------------------------ SQL ve kişi verisi


def test_sql_has_no_personal_columns_and_never_touches_cargo_secrets():
    schema = "Timas_MSCRM.dbo"
    for sql in (S.crm_health_accounts_sql(schema), S.crm_contact_consent_sql(schema), S.crm_last_orders_sql(schema, NOW),
                S.crm_all_users_sql(schema)):
        R.assert_no_personal(sql)
    assert "new_VergiNo" not in S.crm_health_accounts_sql(schema) and "new_VergiDairesi" in S.crm_health_accounts_sql(schema)
    assert "FirstName" not in S.crm_contact_consent_sql(schema) and "EMailAddress1" not in S.crm_contact_consent_sql(schema)
    with pytest.raises(S.SourceError):
        S.secret_count_sql(schema, "new_kargofirmasiBase", "new_sifre")
    cols = S.secret_columns_sql(schema)
    assert "SELECT TABLE_NAME AS tablo, COLUMN_NAME AS kolon" in cols and "Timas_MSCRM.INFORMATION_SCHEMA.COLUMNS" in cols
    assert "SELECT COUNT(*)" in S.webservice_log_secret_sql(schema)
    with pytest.raises(S.SourceError):
        S.monthly_sql("411", "120'; DROP", date(2025, 1, 1), KESIM)
    with pytest.raises(S.SourceError):
        S.crm_campaign_sends_sql(schema, "t; x", "a", "b", NOW)
    with pytest.raises(ValueError):
        R.assert_no_personal("SELECT Telephone1 FROM AccountBase")
    assert R.is_person_account({"iys_tip": 0}) and R.is_person_account({"cari_turu": 4}) and not R.is_person_account({"iys_tip": 1})


def test_summary_facts_never_carry_a_person_name():
    row = {"cari_kodu": "120.02", "ad": "Ali Veli", "bireysel_mi": True, "net_12ay": 5000.0, "net_onceki_12ay": 5000.0,
           "gun_son_alim": 16, "logo_kesim": "2026-08-17", "nedenler_json": "[]"}
    prompt = M.summary_prompt(row, M.facts_of(row))
    assert "Ali Veli" not in prompt
    assert M.numbers_ok("Son 12 ay 5.000,00 ₺ aldı.", M.facts_of(row)) and not M.numbers_ok("Alım %40 düştü.", M.facts_of(row))


def test_monthly_series_fills_gaps():
    s = M.monthly_series([{"ay": "2026-08", "satis": 10, "iade": 0, "net": 10}], KESIM, 3)
    assert [x["ay"] for x in s] == ["2026-06", "2026-07", "2026-08"] and s[0]["net"] == 0.0


# ------------------------------------------------------------------ hız: süzgeç/sıra/sayfa veritabanında (2026-09-29)


def _synthetic(n=60, seed=7):
    """Türkçe harf, boş değer, eşit puan, % ve _ içeren yapay cari satırları (gece turunun yazdığı kolonlarla)."""
    import random

    rnd = random.Random(seed)
    keys = list(M.build_accounts(_data(), _st(), {}, {})[0][0].keys())
    names = ["Işık Kitabevi", "İstanbul Dağıtım", "çınar yayın", "ALİ VELİ", None, "Kitapçı %50", "a_b kitap", "Öz Kırtasiye"]
    rows = []
    for i in range(n):
        r = {k: None for k in keys}
        r.update({"cari_kodu": f"120.{rnd.randint(0, 999):03d}.{i}", "ad": rnd.choice(names),
                  "logo_kanal": rnd.choice(["KITAPCI", "BAYI", None, "", "Belirsiz", "DAĞITICI"]),
                  "bolge": rnd.choice(["RİZE", "İstanbul", "izmir", None, "Rize"]), "temsilci": rnd.choice(["ayseb", None, "mehmet"]),
                  "bireysel_mi": rnd.random() < 0.2, "risk_duzeyi": rnd.choice(list(M.LEVELS)),
                  "risk_puani": rnd.choice([None, 0.0, 35.0, 60.0, round(rnd.uniform(0, 100), 1)]),
                  "net_12ay": rnd.choice([None, 0.0, round(rnd.uniform(-500, 90000), 2)]),
                  "net_onceki_12ay": rnd.choice([None, 0.0, round(rnd.uniform(0, 90000), 2)]),
                  "net_yil": rnd.choice([None, round(rnd.uniform(-100, 50000), 2)]),
                  "degisim": rnd.choice([None, round(rnd.uniform(-1, 2), 4)]), "fatura_12ay": rnd.choice([None, 0, rnd.randint(1, 40)]),
                  "gun_son_alim": rnd.choice([None, 0, rnd.randint(1, 900)]),
                  "segment": rnd.choice([None, "A · KITAPCI · Büyüyen", "B · BAYI · Düşen"]), "nedenler_json": "[]"})
        rows.append(r)
    return rows


def _old_page(rows, p, size, sort, **flt):
    """Uçtaki eski hesap (satırlar bellekte süzülür, sıralanır, sayfalanır) — birebir kopya."""
    rows = M.filter_rows(rows, **flt)
    rows.sort(key=M.SORTS.get(sort, M.SORTS["oncelik"]))
    size, p = max(1, min(1000, int(size or 50))), max(1, int(p or 1))
    return {"items": [M.card(r) for r in rows][(p - 1) * size:p * size], "page": p, "size": size, "total": len(rows),
            "pages": max(1, -(-len(rows) // size)),
            "toplam": {"net12": round(sum(M.num(r.get("net_12ay")) for r in rows), 2),
                       "riskli": sum(1 for r in rows if r.get("risk_duzeyi") in ("yuksek", "kayip"))}}


def test_accounts_page_in_the_database_equals_the_python_list(engine):
    M.write_accounts(engine, T, _synthetic())
    filters = [{}, {"kanal": "kitapci"}, {"kanal": "belirsiz"}, {"kanal": "dagitici"}, {"bolge": "rize"}, {"bolge": "istanbul"},
               {"risk_": "riskli"}, {"risk_": "orta,dusuk"}, {"risk_": "yanlis"}, {"q": "kitap"}, {"q": " a"}, {"q": "%"},
               {"q": "_"}, {"q": "IŞIK"}, {"segment": "A · KITAPCI · Büyüyen"}, {"kanal": "bayi", "q": "a"}]
    for owner in (None, "ayseb"):
        # Eşitlikte eski sıra satırların okunduğu sıradır; veritabanı yolu cari koduyla ayırır: aynı tabana oturt.
        base = sorted(M.account_rows(engine, T, owner), key=lambda r: r["cari_kodu"])
        for flt in filters:
            for sort in list(M.SORTS) + ["yok"]:
                for p, size in ((1, 50), (2, 7), (1, 1000)):
                    new, _ = M.accounts_page(engine, T, owner, sort=sort, p=p, size=size, **flt)
                    assert new == _old_page(list(base), p, size, sort, **flt), (owner, flt, sort, p, size)


def test_overview_in_the_database_equals_the_python_overview(engine):
    M.write_accounts(engine, T, _synthetic())
    score = {"puan": 80.0}
    for owner in (None, "ayseb", "kimse"):
        base = sorted(M.account_rows(engine, T, owner), key=lambda r: r["cari_kodu"])
        new, stmts = M.overview_sql(engine, T, owner, [], score)
        old = M.overview(base, [], score)
        # Aynı değerli iki kanalın sırası eski yolda satırların okunduğu sıraya bağlıydı; yenide kanal adıyla ayrılır.
        by_name = lambda o: {**o, "kanallar": sorted(o["kanallar"], key=lambda g: g["kanal"])}  # noqa: E731
        assert by_name(new) == by_name(old), owner
        assert [g["net12"] for g in new["kanallar"]] == [g["net12"] for g in old["kanallar"]]
        assert set(stmts) == {"kanallar", "bakilacak", "bakilacak_sayi"}
    assert {k["kanal"] for k in new["kanallar"]} == set()                     # temsilcisi olmayan kapsam boş


def test_findings_page_in_the_database_equals_the_python_list(engine):
    import random

    rnd = random.Random(3)
    found = [{"id": f"f{rnd.randint(0, 99999):05d}-{i}", "tur": rnd.choice(list(M.HEALTH_TYPES)), "varlik": "account",
              "kayit_id": f"k-{i}", "eslesen_kayit_id": None, "cari_kodu": rnd.choice([None, f"120.{i}"]),
              "ad": rnd.choice([None, "Işık Kitabevi", "Şahıs carisi", "ALİ %5", "Işık Kitabevi"]), "olasilik": None,
              "ozet": rnd.choice(["Kanal boş", "Cari kodu / Logo bağı dolu", "a_b"]), "onem": rnd.choice(["yuksek", "orta", "dusuk"])}
             for i in range(80)]
    M.sync_findings(engine, T, found, "2026-09-27")
    changed = [{**f, "ad": "Yeni Ad", "ozet": "değişti"} if i % 5 == 0 else f for i, f in enumerate(found[:60])]
    M.sync_findings(engine, T, changed, "2026-09-28")                         # 20 kapanır, 12'sinin metni değişir
    with engine.begin() as c:
        c.execute(M.FINDINGS.update().where(M.FINDINGS.c.id.in_([f["id"] for f in found[:10]])).values(ara=None))
    assert M.backfill_finding_search(engine, T) == 10
    for security in (False, True):
        for durum in ("acik-hepsi", "", "kapandi"):
            for tur in ("", "eksik_kanal", "guvenlik"):
                for q in ("", "kit", "ışık", " a", "%", "_", "değişti", "K-1"):
                    rows = M.list_findings(engine, T, tur=tur, durum=durum, q=q, security=security)
                    for p, size in ((1, 50), (2, 9)):
                        new, total, _ = M.findings_page(engine, T, tur=tur, durum=durum, q=q, security=security, p=p, size=size)
                        assert total == len(rows) and new == rows[(p - 1) * size:p * size], (security, durum, tur, q, p)


def test_list_columns_are_added_to_an_existing_table():
    import sqlalchemy as sa

    e = open_store("sqlite://").engine
    with e.begin() as c:
        c.execute(sa.text("CREATE TABLE semantic_musteri_accounts (tenant_id VARCHAR(80), cari_kodu VARCHAR(40), ad VARCHAR(300))"))
    M._ready.discard(id(e))
    M.ensure(e)
    have = {c["name"] for c in sa.inspect(e).get_columns("semantic_musteri_accounts")}
    assert {"ara", "kanal_ara", "bolge_ara", "ad_sira", "oncelik", "deger_riskte"} <= have
    assert "ara" in {c["name"] for c in sa.inspect(e).get_columns("semantic_musteri_health_findings")}


# ------------------------------------------------------------------ yetki


def test_access_rules_for_musteri_endpoints():
    assert A.rule_for("/api/v1/musteri/run-due") == A.SYSTEM
    assert A.rule_for("/api/v1/musteri/overview") == {"sayfa:musteri-iliskileri"}
    assert A.rule_for("/api/v1/musteri/accounts/120.01/monthly") == {"sayfa:musteri-iliskileri"}
    assert A.rule_for("/api/v1/musteri/health") == {"sayfa:musteri-veri-sagligi"}
    assert A.rule_for("/api/v1/musteri/health/abc/mark") == {"sayfa:musteri-veri-sagligi"}
    f = A.features_for
    assert f("POST", "/api/v1/musteri/accounts/120.01/actions") == ["ozellik:musteri.eylem-yaz"]
    assert f("PATCH", "/api/v1/musteri/actions/a1") == ["ozellik:musteri.eylem-yaz"]
    assert f("GET", "/api/v1/musteri/actions") == [] and f("POST", "/api/v1/musteri/accounts/120.01/summary") == []
    assert f("POST", "/api/v1/musteri/health/f1/mark") == ["ozellik:musteri.bulgu-isaretle"]
    assert f("GET", "/api/v1/musteri/health/export.csv") == ["ozellik:veri.disa-aktar"]
    assert f("GET", "/api/v1/musteri/accounts/export.csv") == ["ozellik:veri.disa-aktar"]
    assert {"ozellik:musteri.herkesinki", "ozellik:musteri.guvenlik-bulgulari"} <= A.explicit_keys()
    assert {"sayfa:musteri-iliskileri", "sayfa:musteri-veri-sagligi", "ozellik:musteri.eylem-yaz"} <= A.all_keys()
