"""M59 Kitapçı/bayi risk ve performans: kural doğrulama, açıklanabilir skor bileşenleri, grup başına segment eşiği,
hareketsiz cari, 12 ay seri istatistiği, kapsam (Logo özel kod 2) ve M30 ataması, eğilimin bugünkü kuralla yeniden
puanlanması, tekrar üretilebilir parmak izi, limit önerisi kuralı ve öneri eşitlemesi, iki gözlü kural onayı, aksiyon
kapsamı, brif biçimi ve sayı denetimi, SQL biçimi ve yetki kuralları.

Sözleşme: skoru model üretmez; aynı gün + aynı kural + aynı girdi → aynı parmak izi; BMT yalnız kendi carisini görür;
hazırlayan kuralını onaylayamaz; CRM'e yazılmaz (öneri portal tablosunda kalır).

Bu testler yalnız saf işlevleri ve köprünün kendi tablolarını (sqlite) sınar; gerçek DB kabulü
`scripts/acceptance/M59/reference_check.py` ile test sunucusunda yapılır.
"""

from __future__ import annotations

from datetime import date

import pytest

from semantic_bridge import access as A
from semantic_bridge import dealers as D
from semantic_bridge import dealers_sources as S
from semantic_bridge import field_sales as F
from semantic_layer.store.catalog_store import open_store

T = "t1"
U1 = "11111111-1111-1111-1111-111111111111"
ACC1 = "aaaaaaaa-0000-0000-0000-000000000001"
ACC2 = "aaaaaaaa-0000-0000-0000-000000000002"


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    D._ready.discard(id(e))
    F._ready.discard(id(e))
    D.ensure(e)
    return e


def rule(**over):
    r = D.default_rule()
    r.update(over)
    return {"surum": 1, **r}


def raw(**kw):
    base = {"logo_code": "120.01", "bakiye": 0.0, "gelmemis": 0.0, "plansiz": 0.0, "k_1_30": 0.0, "k_31_60": 0.0,
            "k_61_90": 0.0, "k_90p": 0.0, "vadesi_gecmis": 0.0, "satis_12ay": 100000.0, "iade_12ay": 0.0,
            "net_12ay": 100000.0, "pay": 0.001, "iade_orani": 0.0, "dso": None, "duzensizlik": 0.0, "aktif_ay": 12,
            "karsiliksiz": 0, "protesto": 0, "cek_tutar": 0.0, "risk_doluluk": None, "kanal": "KITAPCI", "hareketsiz": False}
    base.update(kw)
    return base


# ------------------------------------------------------------------ kural doğrulama


def test_rule_validation_weights_sum_and_increasing_thresholds():
    ok = D.validate_rule({})
    assert sum(ok["agirliklar"].values()) == 100 and ok["esikler"]["standart"] == {"A": 20, "B": 40, "C": 60}
    with pytest.raises(D.DealerError, match="toplamı 100"):
        D.validate_rule({"agirliklar": {"gecikme": 50}})
    with pytest.raises(D.DealerError, match="artan"):
        D.validate_rule({"esikler": {"standart": {"A": 50, "B": 40, "C": 60}}})
    with pytest.raises(D.DealerError, match="tam sayı"):
        D.validate_rule({"agirliklar": {"gecikme": 34.5, "cek": 20.5}})
    with pytest.raises(D.DealerError, match="en az bir kanal"):
        D.validate_rule({"kapsam": {"kanallar": [], "bosKanal": False}})
    k = D.validate_rule({"kapsam": {"kanallar": "kitapci, bayi"}})["kapsam"]
    assert k["kanallar"] == ["BAYI", "KITAPCI"]


# ------------------------------------------------------------------ skor


def test_components_are_explainable_and_sum_to_score():
    r = raw(bakiye=100000, k_90p=50000, k_1_30=10000, vadesi_gecmis=60000, karsiliksiz=1, protesto=1, cek_tutar=30000,
            iade_orani=0.2, risk_doluluk=0.9, duzensizlik=1.0, dso=180)
    ev = D.evaluate(r, rule())
    comps = {c["key"]: c for c in ev["bilesenler"]}
    assert comps["gecikme"]["deger"] == pytest.approx((4 * 50000 + 10000) / (4 * 100000))
    assert comps["cek"]["deger"] == 1.0                             # 1 karşılıksız + 0,5 protesto → 1'de kesilir
    assert comps["iade"]["deger"] == pytest.approx(0.5)             # %20 / tavan %40
    assert comps["limit"]["deger"] == pytest.approx(0.8)            # (0,9 − 0,5) / 0,5
    assert comps["duzensizlik"]["deger"] == pytest.approx(0.5)
    assert comps["tahsilat_suresi"]["deger"] == pytest.approx(0.5)  # (180 − 90) / 180
    assert ev["skor"] == pytest.approx(round(sum(c["puan"] for c in comps.values()), 1))
    assert "yaklaşık" in comps["gecikme"]["aciklama"] and "%90" in comps["limit"]["aciklama"]
    assert [c["puan"] for c in ev["bilesenler"]] == sorted((c["puan"] for c in ev["bilesenler"]), reverse=True)


def test_missing_limit_is_not_zero_risk_text_and_idle_has_no_segment():
    ev = D.evaluate(raw(risk_doluluk=None), rule())
    lim = next(c for c in ev["bilesenler"] if c["key"] == "limit")
    assert lim["puan"] == 0 and "girilmemiş" in lim["aciklama"]
    idle = D.evaluate(raw(hareketsiz=True, satis_12ay=0, net_12ay=0), rule())
    assert idle["segment"] is None and idle["skor"] is None


def test_key_accounts_use_their_own_thresholds():
    r = rule()
    assert D.segment_of(22, "standart", r) == "B" and D.segment_of(22, "anahtar", r) == "A"
    assert D.segment_of(60, "standart", r) == "D" and D.segment_of(60, "anahtar", r) == "C"
    assert D.group_of(raw(kanal="E-TICARET"), r) == "anahtar"
    assert D.group_of(raw(kanal="kitapci", pay=0.05), r) == "anahtar"      # ciro payı eşiği
    assert D.group_of(raw(kanal="KITAPCI", pay=0.001), r) == "standart"
    assert D.in_scope("kitapçı".upper().replace("Ç", "C"), r) and not D.in_scope("KURUM", r) and not D.in_scope(None, r)


def test_series_stats_and_dso():
    keys = S.month_keys(date(2026, 8, 17), 12)
    assert keys[0] == "2025-09" and keys[-1] == "2026-08" and len(keys) == 12
    months = {k: {"satis": 100.0, "iade": 10.0, "odeme": 50.0} for k in keys}
    st = D.series_stats(months, keys)
    assert st["satis_12ay"] == 1200 and st["iade_orani"] == 0.1 and st["duzensizlik"] == 0 and st["aktif_ay"] == 12
    assert st["buyume_6ay"] == 0
    one = D.series_stats({keys[-1]: {"satis": 1200.0}}, keys)
    assert one["aktif_ay"] == 1 and one["duzensizlik"] == pytest.approx(3.3166, rel=1e-3)
    assert D.series_stats({}, keys)["iade_orani"] is None
    assert D.dso_of(36500, 365000) == 36.5 and D.dso_of(0, 1000) is None and D.dso_of(100, 0) is None
    assert S.window_start(date(2026, 8, 17)) == date(2025, 9, 1)


# ------------------------------------------------------------------ kapsam ve atama (M30 ile aynı)


def _data():
    users = [{"id": U1, "ad": "Ayşe Bmt", "domain": "TIMAS\\ayseb", "bmt": 1}]
    accs = [{"account_id": ACC1, "unvan": "Kitapçı A", "cari_kodu": "120.01", "logicalref": None, "owner_id": U1,
             "owner_type": 8, "bmt_il_cari": 1, "kanal": 100000001, "il": "Trabzon", "il_temsilci": None,
             "limit_toplam": 100000, "risk_toplam": 90000}]
    clients = [{"ref": 5, "code": "120.01", "unvan": "A", "il": "TRABZON", "kanal": "KITAPCI"},
               {"ref": 6, "code": "120.02", "unvan": "B", "il": "RİZE", "kanal": "ZINCIR"},
               {"ref": 7, "code": "120.03", "unvan": "C", "il": "RİZE", "kanal": "KURUM"},
               {"ref": 8, "code": "120.04", "unvan": "D", "il": "RİZE", "kanal": "KITAPCI"}]
    end = date(2026, 8, 17)
    keys = S.month_keys(end)
    monthly = {"120.01": {k: {"satis": 1000.0, "iade": 100.0, "fatura": 1, "odeme": 500.0} for k in keys},
               "120.02": {keys[-1]: {"satis": 50000.0, "iade": 0.0, "fatura": 3, "odeme": 0.0}, "_son": "2026-08-10"}}
    return {"crm": {"users": users, "accounts": accs, "riskOrders": [{"account_id": ACC1, "adet": 2, "tutar": 5000, "sebep": 3}],
                    "flags": {ACC1: {"sorunlu": True, "kredi_askida": False, "vade_gun": 90, "ek_limit": None}}},
            "logo": {"cal": {"dataEnd": "2026-08-17", "year": 2026, "firm": "411", "prevFirm": "211"}, "agingAsof": "2026-08-17",
                     "end": "2026-08-17", "clients": clients,
                     "aging": {5: {"bakiye": 20000.0, "gelmemis": 5000.0, "k_1_30": 0, "k_31_60": 0, "k_61_90": 0,
                                   "k_90p": 15000.0, "vadesi_gecmis": 15000.0, "plansiz": 0.0}},
                     "cheques": {"120.01": {"karsiliksiz_adet": 1, "karsiliksiz_tutar": 7000, "protesto_adet": 0, "protesto_tutar": 0}},
                     "payments": {"120.01": {"son": "2026-06-01", "toplam": 6000.0}}, "monthly": monthly},
            "now": "2026-09-28"}


def test_build_scope_by_logo_channel_keeps_unassigned_and_idle():
    st = {"excludedOwners": [], "schema": "x.dbo"}
    rows, info = D.build(_data(), st, rule())
    by = {r["logo_code"]: r for r in rows}
    assert set(by) == {"120.01", "120.02", "120.04"}                 # KURUM kapsam dışı; CRM'siz cari kalır
    assert info["scope"] == 3 and info["clients"] == 4
    a = by["120.01"]
    assert a["bmt"] == "ayseb" and a["risk_doluluk"] == 0.9 and a["siparis_riskte"] == 2 and a["sorunlu"] is True
    assert a["karsiliksiz"] == 1 and a["son_odeme"] == "2026-06-01" and a["iade_orani"] == 0.1 and a["net_12ay"] == 10800
    assert by["120.02"]["bmt"] is None and by["120.02"]["son_fatura"] == "2026-08-10"
    assert by["120.04"]["hareketsiz"] is True
    assert by["120.02"]["pay"] == pytest.approx(50000 / 60800, rel=1e-4)
    assert len(a["seri"]) == 12 and a["seri"][-1]["ay"] == "2026-08"


# ------------------------------------------------------------------ eğilim, önceki segment, parmak izi


def test_trend_and_previous_segment_are_rescored_with_todays_rule_and_fingerprint_is_stable(engine):
    r = rule()
    today_raw = [raw(logo_code="120.01", bakiye=100000, k_90p=100000, vadesi_gecmis=100000, karsiliksiz=1)]
    prev = {"120.01": D._raw_from_row(raw(bakiye=100000, k_1_30=100000, vadesi_gecmis=100000))}
    rows = D.score_rows(today_raw, r, "2026-09-28", prev, prev, "2026-08-17", "2026-08-17")
    x = rows[0]
    assert x["onceki_segment"] == D.evaluate(prev["120.01"], r)["segment"]
    assert D.worse(x["segment"], x["onceki_segment"]) and x["egilim"] == "kotulesiyor"
    again = D.score_rows(today_raw, r, "2026-09-28", prev, prev, "2026-08-17", "2026-08-17")
    assert again[0]["fingerprint"] == x["fingerprint"]
    other = D.score_rows(today_raw, {**r, "surum": 2}, "2026-09-28", prev, prev, "2026-08-17", "2026-08-17")
    assert other[0]["fingerprint"] != x["fingerprint"]
    assert D.trend(50, None, 5) is None and D.trend(50, 47, 5) == "yatay" and D.trend(40, 50, 5) == "iyilesiyor"


def test_write_day_keeps_history_replaces_same_day_and_scopes(engine):
    r = rule()
    raws = [{**raw(logo_code="120.01", bmt="ayseb"), "seri": []}, {**raw(logo_code="120.02", bmt=None), "seri": []}]
    for g in ("2026-09-27", "2026-09-28", "2026-09-28"):
        rows = D.score_rows(raws, r, g, {}, {}, "2026-08-17", "2026-08-17")
        D.write_day(engine, T, g, rows, raws)
    assert D.latest_day(engine, T) == "2026-09-28"
    assert len(D.day_rows(engine, T, "2026-09-28", None)) == 2               # aynı gün iki kez → iki satır
    assert len(D.day_rows(engine, T, "2026-09-27", None)) == 2               # geçmiş gün kaldı
    assert [x["logo_code"] for x in D.day_rows(engine, T, "2026-09-28", "ayseb")] == ["120.01"]
    assert D.scoped(engine, T, "ayseb", "120.01", False)["logo_code"] == "120.01"
    with pytest.raises(D.DealerError) as e:
        D.scoped(engine, T, "ayseb", "120.02", False)
    assert e.value.status == 403
    assert D.scoped(engine, T, "mudur", "120.02", True)["logo_code"] == "120.02"
    g, prev = D.previous_raw(engine, T, "2026-09-28")
    assert g == "2026-09-27" and set(prev) == {"120.01", "120.02"}


def test_summary_counts_and_worsened_list():
    r = rule()
    rows = D.score_rows([raw(logo_code="a", bakiye=100, k_90p=100, vadesi_gecmis=100, karsiliksiz=1),
                         raw(logo_code="b"), raw(logo_code="c", hareketsiz=True)], r, "2026-09-28",
                        {"a": D._raw_from_row(raw())}, {}, None, None)
    s = D.summary(rows, [], r)
    assert s["cari"] == 3 and s["aktif"] == 2 and s["hareketsiz"] == 1
    assert sum(s["segment"]["standart"].values()) == 2
    assert [x["code"] for x in s["kotulesenler"]] == ["a"]
    assert s["kovalar"]["k_90p"] == 100 and s["kovaCari"]["k_90p"] == 1 and s["cekOlayCari"] == 1


# ------------------------------------------------------------------ limit önerisi


def _prow(**kw):
    base = {"logo_code": "120.01", "crm_account_id": ACC1, "segment": "A", "skor": 10.0, "hareketsiz": False,
            "limit_toplam": 100000.0, "risk_toplam": 90000.0, "risk_doluluk": 0.9, "net_12ay": 120000.0, "buyume_6ay": 0.1}
    base.update(kw)
    return base


def test_limit_proposal_rules():
    r = rule()
    up = D.limit_proposal(_prow(), r)
    assert up["degisim"] == "artir" and up["onerilen"] == 120000
    assert D.limit_proposal(_prow(buyume_6ay=-0.2), r) is None
    down = D.limit_proposal(_prow(segment="D", skor=70, risk_toplam=42300, risk_doluluk=0.423), r)
    assert down["degisim"] == "azalt" and down["onerilen"] == 43000     # yukarı yuvarlanır: riskin altına inmez and "D segmentinde" in down["gerekce"]
    new = D.limit_proposal(_prow(segment="B", limit_toplam=None, risk_doluluk=None), r)
    assert new["degisim"] == "tanimla" and new["onerilen"] == 20000              # aylık 10.000 × 2 ay
    assert D.limit_proposal(_prow(segment="C"), r) is None
    assert D.limit_proposal(_prow(crm_account_id=None), r) is None             # limit CRM'de; eşi yoksa öneri yok
    assert D.limit_proposal(_prow(hareketsiz=True), r) is None


def test_proposal_sync_is_idempotent_and_decisions_and_crm_done(engine):
    r = rule()
    rows = [_prow()]
    first = D.sync_proposals(engine, T, rows, r, "2026-09-28")
    assert len(first["new"]) == 1
    assert D.sync_proposals(engine, T, rows, r, "2026-09-29")["new"] == []     # aynı öneri ikinci kez açılmaz
    changed = D.sync_proposals(engine, T, [_prow(segment="D", risk_toplam=50000, risk_doluluk=0.5)], r, "2026-09-30")
    assert len(changed["new"]) == 1 and changed["dropped"] == 1
    pid = changed["new"][0]
    with pytest.raises(D.DealerError):
        D.decide_proposal(engine, T, "mudur", pid, False, "")                   # ret nedeni şart
    ok = D.decide_proposal(engine, T, "mudur", pid, True, None)
    assert ok["durum"] == "onayli"
    with pytest.raises(D.DealerError):
        D.decide_proposal(engine, T, "mudur", pid, True, None)
    done = D.crm_done(engine, T, "merkez", pid)
    assert done["durum"] == "crm_islendi" and done["crmIsleyen"] == "merkez"
    assert {p["durum"] for p in D.list_proposals(engine, T)} == {"gecersiz", "crm_islendi"}


# ------------------------------------------------------------------ kural yaşam döngüsü


def test_rule_lifecycle_two_eyes(engine):
    first = D.active_rule(engine, T)
    assert first["surum"] == 1 and first["durum"] == "yururlukte" and first["hazirlayan"] == "sistem"
    draft = D.create_rule(engine, T, "ali", {"agirliklar": {"gecikme": 45, "cek": 10}}, D.rule_body(first))
    assert draft["surum"] == 2 and draft["durum"] == "taslak"
    with pytest.raises(D.DealerError, match="gerekçe"):
        D.submit_rule(engine, T, "ali", draft["id"])
    D.edit_rule(engine, T, "ali", draft["id"], {"gerekce": "Gecikme daha belirleyici"})
    with pytest.raises(D.DealerError):
        D.edit_rule(engine, T, "veli", draft["id"], {"gerekce": "x"})           # hazırlayan değiştirir
    D.submit_rule(engine, T, "ali", draft["id"])
    with pytest.raises(D.DealerError) as e:
        D.decide_rule(engine, T, "ali", draft["id"], True, None)
    assert e.value.status == 403
    D.decide_rule(engine, T, "cfo", draft["id"], True, "uygun")
    now = D.active_rule(engine, T)
    assert now["surum"] == 2 and now["agirliklar"]["gecikme"] == 45
    assert {r["surum"]: r["durum"] for r in D.list_rules(engine, T)} == {1: "arsiv", 2: "yururlukte"}


# ------------------------------------------------------------------ aksiyon


def test_actions_scope_and_assignment(engine):
    row = {"logo_code": "120.01", "unvan": "A"}
    with pytest.raises(D.DealerError):
        D.add_action(engine, T, "ayseb", row, {"tur": "arama", "sahip": "veli"}, can_assign=False)
    a = D.add_action(engine, T, "mudur", row, {"tur": "ziyaret", "sahip": "ayseb", "termin": "2026-10-01"}, can_assign=True)
    D.add_action(engine, T, "mudur", {"logo_code": "120.09"}, {"tur": "arama"}, can_assign=True)
    mine = D.list_actions(engine, T, codes={"120.01"}, viewer="ayseb")
    assert [x["id"] for x in mine] == [a["id"]]
    out, diff = D.update_action(engine, T, "ayseb", a["id"], {"durum": "yapildi"}, manage=False)
    assert out["durum"] == "yapildi" and diff["durum"]["yeni"] == "yapildi"
    with pytest.raises(D.DealerError):
        D.update_action(engine, T, "veli", a["id"], {"durum": "iptal"}, manage=False)
    with pytest.raises(D.DealerError):
        D.add_action(engine, T, "mudur", row, {"tur": "yanlis"}, can_assign=True)


# ------------------------------------------------------------------ brif


def test_brief_facts_parse_and_number_guard():
    r = {**raw(bakiye=42350, k_90p=12000, vadesi_gecmis=20000, iade_orani=0.31, karsiliksiz=1), "son_odeme": "2026-07-14",
         "crm_account_id": ACC1, "limit_toplam": None, "siparis_riskte": 0, "egilim": "kotulesiyor",
         "bilesen_json": D._dump(D.evaluate(raw(bakiye=42350, k_90p=12000, vadesi_gecmis=20000, iade_orani=0.31,
                                               karsiliksiz=1), rule())["bilesenler"])}
    visits = [{"notu": "gizli not", "gizli": True}, {"notu": "Haftaya çek verecek", "gizli": False, "gerceklesen": "2026-09-20T10:00"}]
    facts = D.facts_of(r, visits)
    assert any("limit girilmemiş" in f for f in facts) and any("Haftaya çek" in f for f in facts)
    assert not any("gizli not" in f for f in facts)                            # gizli not brife girmez
    metin, items = D.rule_brief(r, visits)
    assert len(items) == 3 and metin
    out = "ÖZET: Bakiye 42.350,00 ₺.\nKONUŞULACAKLAR:\n- Çek\n- İade\n- Sipariş"
    m, its = D.parse_brief(out)
    assert m == "Bakiye 42.350,00 ₺." and its == ["Çek", "İade", "Sipariş"]
    assert D.numbers_ok(m, facts) and not D.numbers_ok("Bakiye 99.999 ₺", facts)
    assert D.parse_brief("serbest metin") == ("", [])


# ------------------------------------------------------------------ SQL biçimi


def test_sql_shapes_and_no_personal_columns():
    ms = S.monthly_sales_sql("411", date(2025, 9, 1), date(2026, 8, 17))
    assert "LINENET" in ms and "INVOICEREF <> 0" in ms and "LINETYPE = 0" in ms and "< '2026-08-18'" in ms
    assert "COUNT(DISTINCT CASE WHEN S.TRCODE IN (7,8,9) THEN S.INVOICEREF END)" in ms
    mp = S.monthly_payments_sql("411", date(2025, 9, 1), date(2026, 8, 17), (1, 20))
    assert "L.SIGN = 1" in mp and "TRCODE IN (1, 20)" in mp
    fl = S.crm_account_flags_sql("Timas_MSCRM.dbo")
    for col in ("Address", "Telephone", "EMail", "vergi", "TaxId"):
        assert col.lower() not in fl.lower()
    h = S.crm_risk_history_sql("Timas_MSCRM.dbo", ACC1, date(2025, 9, 28))
    assert "new_risklimitionaylayanid" in h and f"'{ACC1}'" in h
    with pytest.raises(S.SourceError):
        S.crm_risk_history_sql("Timas_MSCRM.dbo", "x'; DROP", date(2025, 9, 28))
    with pytest.raises(S.SourceError):
        S.monthly_sales_sql("4x1", date(2025, 9, 1), date(2026, 8, 17))
    rows = S.history_rows([{"NO": "S1", "DURUM": 100000004, "SEBEP": 3, "ONAYLAYAN_ID": U1, "TARIH": "2026-08-01"}], {U1: "Ali"})
    assert rows[0]["riskte"] and rows[0]["sebep"] == "Toplam limit" and rows[0]["onaylayan"] == "Ali"


def test_csv_and_morning_text():
    r = rule()
    rows = D.score_rows([raw(logo_code="a", unvan="Kitapçı A", bakiye=100, k_90p=100, vadesi_gecmis=100, karsiliksiz=1)],
                        r, "2026-09-28", {"a": D._raw_from_row(raw())}, {}, "2026-08-17", "2026-08-17")
    csv = D.csv_text(rows)
    assert csv.startswith("﻿Cari kodu;") and "Kitapçı A" in csv
    body = D.morning_text(D.summary(rows, [], r), 2, "2026-09-28", "2026-08-17")
    assert "Kitapçı A" in body and "yaklaşıktır" in body and "Onay bekleyen limit önerisi: 2" in body


# ------------------------------------------------------------------ yetki


def test_access_rules_for_dealer_endpoints():
    assert A.rule_for("/api/v1/dealers/run-due") == A.SYSTEM
    assert A.rule_for("/api/v1/dealers/list") == {"sayfa:bayi-risk"}
    assert A.rule_for("/api/v1/dealers/120.01/brief") == {"sayfa:bayi-risk"}
    f = A.features_for
    assert f("POST", "/api/v1/dealers/120.01/notes") == ["ozellik:bayi.not"] and f("GET", "/api/v1/dealers/120.01/notes") == []
    assert f("POST", "/api/v1/dealers/120.01/brief") == []                      # brif okuma sayılır
    assert f("POST", "/api/v1/dealers/actions") == ["ozellik:bayi.aksiyon"]
    assert f("PATCH", "/api/v1/dealers/actions/a1") == ["ozellik:bayi.aksiyon"]
    assert f("POST", "/api/v1/dealers/rules") == ["ozellik:bayi.kural"]
    assert f("POST", "/api/v1/dealers/rules/r1/submit") == ["ozellik:bayi.kural"]
    assert f("POST", "/api/v1/dealers/rules/r1/preview") == []
    assert f("POST", "/api/v1/dealers/rules/r1/approve") == []                  # açıkça verilen, ucun içinde
    assert f("POST", "/api/v1/dealers/limits/p1/approve") == []
    assert f("GET", "/api/v1/dealers/list/export.csv") == ["ozellik:veri.disa-aktar"]
    assert {"ozellik:bayi.herkesinki", "ozellik:bayi.limit-onay", "ozellik:bayi.kural-onay"} <= A.explicit_keys()
    assert "sayfa:bayi-risk" in A.all_keys()
