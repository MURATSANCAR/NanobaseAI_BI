"""M30 Saha satış ve tahsilat: temsilci ataması (CRM sahibi / BMT İl), Logo eşleşmesi (kod önce), FIFO kova satırları,
öncelik kuralı ve gerekçe çipleri, müşteri hedefi dağıtımı (M46 payı; toplam plana eşit), ödeme planı kuralı ve iki göz,
ziyaret notu (gizli not), ödeme sözü, bildirim tekilliği, CRM tahsilat görünümü (yeniden girdirme yok, kapsam), özetteki
sayı denetimi, haftalık rapor, SQL biçimi ve yetki kuralları.

Sözleşme: model rakam üretmez (özetteki her sayı olgularda geçer); kişisel kolon seçilmez; kişi yalnız kendi carisini görür;
öneren/gönderen ödeme planını onaylayamaz; gizli not başkasına ve özete gitmez.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from semantic_bridge import access as A
from semantic_bridge import field_sales as F
from semantic_bridge import field_sales_sources as S
from semantic_layer.store.catalog_store import open_store

T = "t1"
U1 = "11111111-1111-1111-1111-111111111111"
U2 = "22222222-2222-2222-2222-222222222222"
ACC1 = "aaaaaaaa-0000-0000-0000-000000000001"
ACC2 = "aaaaaaaa-0000-0000-0000-000000000002"
ACC3 = "aaaaaaaa-0000-0000-0000-000000000003"


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    F._ready.discard(id(e))
    F.ensure(e)
    return e


USERS = [{"id": U1, "ad": "Ayşe Bmt", "domain": "TIMAS\\ayseb", "bmt": 1},
         {"id": U2, "ad": "Timas CRM", "domain": "TIMAS\\servis", "bmt": 0}]


def _acc(aid, code, owner, mode=1, il_rep=None, **kw):
    return {"account_id": aid, "unvan": f"Kitapçı {code}", "cari_kodu": code, "logicalref": None, "owner_id": owner,
            "owner_type": 8, "bmt_il_cari": mode, "kanal": 100000001, "il": "Trabzon", "il_temsilci": il_rep, **kw}


# ------------------------------------------------------------------ atama ve eşleşme


def test_assignment_owner_il_and_service_account():
    accs = [_acc(ACC1, "120.01", U1), _acc(ACC2, "120.02", U2, mode=0, il_rep=U1), _acc(ACC3, "120.03", U2)]
    out = {a["cari_kodu"]: a for a in F.assign(accs, USERS, ["Timas CRM"])}
    assert out["120.01"]["ad_hesap"] == "ayseb" and out["120.01"]["atama_kaynagi"] == "owner"
    assert out["120.02"]["ad_hesap"] == "ayseb" and out["120.02"]["atama_kaynagi"] == "il"     # BMT İl → il temsilcisi
    assert out["120.03"]["ad_hesap"] is None                                                   # servis hesabı süzülür
    team = F.assign([_acc(ACC1, "120.01", U1, owner_type=9)], USERS, [])
    assert team[0]["ad_hesap"] is None                                                          # takıma atanmış kayıt


def test_logo_match_code_first_then_ref_and_unmatched_clients_stay():
    accs = F.assign([_acc(ACC1, "120.01", U1), {**_acc(ACC2, None, U1), "logicalref": "77"}], USERS, [])
    clients = [{"ref": 5, "code": "120.01", "unvan": "A", "il": "TRABZON", "kanal": "KITAPCI"},
               {"ref": 77, "code": "120.09", "unvan": "B", "il": "RİZE", "kanal": "BAYI"},
               {"ref": 88, "code": "120.10", "unvan": "C", "il": "RİZE", "kanal": "BAYI"}]
    rows = {r["logo_code"]: r for r in F.match_clients(accs, clients)}
    assert rows["120.01"]["crm_account_id"] == ACC1 and rows["120.01"]["logo_kanal"] == "KITAPCI"
    assert rows["120.09"]["crm_account_id"] == ACC2                                             # ref ile
    assert rows["120.10"]["crm_account_id"] is None and rows["120.10"]["ad_hesap"] is None      # CRM'de yok, temsilcisiz


# ------------------------------------------------------------------ öncelik


def test_score_chips_and_cap():
    sig = {"vadesi_gecmis": 42000, "k_90p": 42000, "karsiliksiz_olay_12ay": 1, "risk_doluluk": 1.0, "siparis_riskte": 2,
           "hedef_acigi": 0.35, "ytd_net_ciro": 60, "gecen_yil_ayni_donem": 100}
    pts, chips = F.score(sig, {"gecikmeRank": 1.0, "soz": {"tarih": "2026-09-01", "tutar": 5000}, "red": 1, "mudur": "bölge",
                               "sonZiyaret": "2026-06-01", "today": date(2026, 9, 28), "visitCycleDays": 30})
    assert pts == 100.0                                                   # toplam 100'de kesilir
    keys = [c["key"] for c in chips]
    assert {"gecikme", "doksan", "cek", "risk", "siparis", "soz", "red", "hedef", "satis", "ziyaret", "mudur"} == set(keys)
    assert chips[0]["points"] >= chips[-1]["points"]
    lab = {c["key"]: c["label"] for c in chips}
    assert lab["doksan"] == "90+ gün 42 bin ₺" and lab["hedef"] == "Hedef açığı %35" and lab["satis"].endswith("%40 gerisinde")


def test_score_quiet_customer_gets_nothing():
    pts, chips = F.score({"vadesi_gecmis": 0, "risk_doluluk": 0.3, "ytd_net_ciro": 120, "gecen_yil_ayni_donem": 100},
                         {"gecikmeRank": 0, "today": date(2026, 9, 28), "sonZiyaret": "2026-09-20", "visitCycleDays": 30})
    assert pts == 0 and chips == []


def test_overdue_rank_is_relative_to_the_reps_portfolio():
    rows = [{"logo_code": c, "ad_hesap": "a", "vadesi_gecmis": v, "k_1_30": v} for c, v in (("x", 100), ("y", 1000), ("z", 0))]
    r = {x["logo_code"]: x for x in F.ranked(rows, promises={}, rejected={}, boosts={}, last_visits={}, cycle=30, now=date(2026, 9, 28))}
    assert r["y"]["puan"] > r["x"]["puan"] > r["z"]["puan"] == 0
    assert F.pct_ranks({"a": 0, "b": 5, "c": 10}) == {"a": 0.0, "b": 0.5, "c": 1.0}


# ------------------------------------------------------------------ hedef


def test_customer_targets_sum_to_plan_and_expected_share():
    plan = {"plan": {"id": "p"}, "items": [
        {"hedef": {"ciro": 1200.0}, "aylik": [{"ciro": 100.0, "adet": 1} for _ in range(12)]}]}
    prev = {"a": 300.0, "b": 100.0, "c": -50.0}
    t, info = F.customer_targets(prev, plan, {}, date(2026, 6, 30), 2026)
    assert info["kaynak"] == "m46" and round(t["a"]["yil"] + t["b"]["yil"], 2) == 1200.0 and "c" not in t
    assert t["a"]["yil"] == 900.0 and t["a"]["beklenen"] == 450.0              # yarı yıl, eşit aylar
    t2, info2 = F.customer_targets(prev, None, {"a": 730.0}, date(2026, 7, 2), 2026, "auto")
    assert info2["kaynak"] == "crm" and t2["a"]["beklenen"] == round(730 * 183 / 365, 2)
    assert F.customer_targets(prev, None, {}, date(2026, 7, 2), 2026, "m46")[0] == {}


def test_book_target_gap_uses_customer_share():
    items = [{"stokKodu": "K1", "ad": "Kitap", "hedef": {"adet": 1000, "ciro": 100000},
              "aylik": [{"adet": 1000 / 12} for _ in range(12)]}]
    gaps = F.book_target_gaps({"K1": 50}, {"K1": 500}, {"K1": 10}, items, date(2026, 12, 31), 2026)
    assert gaps[0]["pay"] == 0.1 and gaps[0]["beklenen"] == 100.0 and gaps[0]["acikAdet"] == 90.0 and gaps[0]["acikCiro"] == 9000.0
    assert F.book_target_gaps({}, {"K1": 500}, {}, items, date(2026, 12, 31), 2026) == []


def test_suggestions_exclude_bought_and_need_similar_min():
    similar = F.merge_similar([{"stok": "A", "ad": "a", "cari": "c1", "adet": 5, "ciro": 50},
                               {"stok": "A", "ad": "a", "cari": "c2", "adet": 5, "ciro": 50},
                               {"stok": "A", "ad": "a", "cari": "c3", "adet": 1, "ciro": 10},
                               {"stok": "B", "ad": "b", "cari": "c1", "adet": 5, "ciro": 50},
                               {"stok": "C", "ad": "c", "cari": "c1", "adet": 9, "ciro": 90}])
    assert similar["A"]["cari"] == 3
    out = F.suggestions({"C"}, similar, {"N": {"ad": "yeni", "ilk": "2026-09-01"}}, 3)
    assert [x["stok"] for x in out] == ["A", "N"] and out[1]["yeni"] and "Yeni çıktı" in out[1]["neden"][0]


# ------------------------------------------------------------------ ödeme planı


def test_plan_installments_rounding_and_month_end():
    rows = F.plan_installments(10050, 3, date(2026, 1, 31))
    assert [r["tarih"] for r in rows] == ["2026-01-31", "2026-02-28", "2026-03-31"]
    assert [r["tutar"] for r in rows] == [3300, 3300, 3450] and round(sum(r["tutar"] for r in rows), 2) == 10050


def test_plan_flow_two_eyes(engine):
    cust = {"logo_code": "120.01", "unvan": "A", "ad_hesap": "ayseb", "vadesi_gecmis": 12000, "odeme_12ay": 48000}
    p = F.create_plan(engine, T, "ayseb", cust, {}, 6, date(2026, 9, 28))
    assert p["durum"] == "taslak" and len(p["taksitler"]) == 3 and p["taksitToplam"] == 12000   # 12000 ÷ 4000/ay
    with pytest.raises(F.FieldError):
        F.submit_plan(engine, T, "baskasi", p["id"])
    F.edit_plan(engine, T, "ayseb", p["id"], {"taksitler": [{"tarih": "2026-11-15", "tutar": 6000}, {"tarih": "2026-10-15", "tutar": 6000}]})
    s = F.submit_plan(engine, T, "ayseb", p["id"])
    assert s["durum"] == "onayda" and s["taksitler"][0]["tarih"] == "2026-10-15"
    with pytest.raises(F.FieldError) as e:
        F.decide_plan(engine, T, "ayseb", p["id"], True, None)
    assert e.value.status == 409
    with pytest.raises(F.FieldError):
        F.decide_plan(engine, T, "mudur", p["id"], False, "")                         # red gerekçe ister
    d = F.decide_plan(engine, T, "mudur", p["id"], True, "uygun")
    assert d["durum"] == "onayli" and d["onaylayan"] == "mudur"
    with pytest.raises(F.FieldError):
        F.create_plan(engine, T, "ayseb", {**cust, "vadesi_gecmis": 0}, {}, 6)


# ------------------------------------------------------------------ ziyaret ve söz


def test_visit_note_private_and_promise(engine):
    v = F.add_visit(engine, T, "ayseb", {"hedef": "120.01", "notu": "Kalanı 15 Ekim sözü", "gizli": True,
                                         "sozOdemeTarihi": "2026-09-15", "sozOdemeTutari": "20.000,50", "ton": "olumlu"}, "A")
    assert v["durum"] == "yapildi" and v["gerceklesen"] and v["sozOdemeTutari"] == 20000.5
    other = F.list_visits(engine, T, "mudur", admin=False)
    assert other[0]["notu"] is None and other[0]["gizliNot"] is True
    own = F.list_visits(engine, T, "ayseb", codes=set())
    assert own[0]["notu"] == "Kalanı 15 Ekim sözü"
    assert F.broken_promises(engine, T, {"120.01": "2026-09-01"}, date(2026, 9, 28))["120.01"]["tarih"] == "2026-09-15"
    assert F.broken_promises(engine, T, {"120.01": "2026-09-20"}, date(2026, 9, 28)) == {}      # sonra ödeme var
    with pytest.raises(F.FieldError):
        F.update_visit(engine, T, "baskasi", v["id"], {"notu": "x"})
    out, diff = F.update_visit(engine, T, "ayseb", v["id"], {"notu": "yeni", "ton": "notr"})
    assert out["notu"] == "yeni" and diff["notu"] == {"degisti": True} and diff["ton"]["yeni"] == "notr"
    with pytest.raises(F.FieldError):
        F.add_visit(engine, T, "ayseb", {"hedef": "120.01", "planlanan": "28.09.2026"}, None)
    assert F.last_visit_days(engine, T)["120.01"] == v["gerceklesen"][:10]


def test_private_note_never_reaches_the_summary_facts():
    b = {"asof": "2026-09-28", "signals": {"bakiye": 1, "vadesi_gecmis": 0, "k_90p": 0, "ytd_net_ciro": 0, "gecen_yil_ayni_donem": 0},
         "ziyaretler": [{"notu": "gizli bilgi", "gizli": True}, {"notu": "açık not", "gizli": False, "gerceklesen": "2026-09-20"}]}
    text = " ".join(F.facts_of(b))
    assert "gizli bilgi" not in text and "açık not" in text


def test_summary_numbers_must_come_from_facts():
    facts = ["Vadesi geçmiş (yaklaşık): 42.350,00 ₺.", "Son ödeme: 2026-07-19 (71 gün önce)."]
    assert F.numbers_ok("Son ödeme 71 gün önce; vadesi geçmiş 42.350 ₺.", facts)
    assert not F.numbers_ok("Bu yıl alımı %60 düştü.", facts)


# ------------------------------------------------------------------ bildirim ve öncelik kaydı


def test_events_are_written_once(engine):
    assert F.add_event(engine, T, "ayseb", "tahsilat-red", "id1", "Tahsilat reddedildi")
    assert not F.add_event(engine, T, "ayseb", "tahsilat-red", "id1", "Tahsilat reddedildi")
    assert len(F.events(engine, T, "ayseb")) == 1 and F.mark_seen(engine, T, "ayseb") == 1
    assert F.events(engine, T, "ayseb")[0]["goruldu"] is True


def test_override_replaces_and_expires(engine):
    F.add_override(engine, T, "mudur", "120.01", {"neden": "bölge toplantısı", "bitis": "2026-09-30"})
    o = F.add_override(engine, T, "mudur", "120.01", {"neden": "yeni neden"})
    assert list(F.overrides(engine, T, date(2026, 9, 28)).values())[0]["neden"] == "yeni neden"
    F.delete_override(engine, T, o["id"])
    F.add_override(engine, T, "mudur", "120.02", {"neden": "x", "bitis": "2026-09-01"})
    assert F.overrides(engine, T, date(2026, 9, 28)) == {}
    with pytest.raises(F.FieldError):
        F.add_override(engine, T, "mudur", "120.03", {"neden": " "})


# ------------------------------------------------------------------ gece turu birleştirmesi


def _data():
    return {"now": "2026-09-28", "warnings": [], "crm": {
        "users": USERS, "accounts": [_acc(ACC1, "120.01", U1, limit_toplam=100000, risk_toplam=92000),
                                     _acc(ACC2, "120.02", U2)],
        "riskOrders": [{"account_id": ACC1, "adet": 1, "tutar": 5000, "sebep": 3}], "collections": [], "crmVisits": []},
        "logo": {"cal": {"year": 2026, "firm": "411", "prevFirm": "211", "dataEnd": "2026-08-17"}, "agingAsof": "2026-09-28",
                 "clients": [{"ref": 5, "code": "120.01", "unvan": "A", "il": "TRABZON", "kanal": "KITAPCI"},
                             {"ref": 6, "code": "120.02", "unvan": "B", "il": "RİZE", "kanal": "BAYI"}],
                 "aging": {5: {"bakiye": 50000, "gelmemis": 8000, "k_1_30": 0, "k_31_60": 0, "k_61_90": 0, "k_90p": 42000,
                               "vadesi_gecmis": 42000, "plansiz": 0}},
                 "payments": {"120.01": {"son": "2026-07-19", "toplam": 24000}},
                 "ytd": {"120.01": {"satis": 70000, "iade": 10000, "son_fatura": "2026-08-10"}},
                 "ly": {"120.01": {"satis": 100000, "iade": 0}}, "lyFull": {"120.01": {"satis": 150000, "iade": 0},
                                                                          "120.02": {"satis": 50000, "iade": 0}},
                 "cheques": {"120.01": {"karsiliksiz_adet": 1, "karsiliksiz_tutar": 20000, "protesto_adet": 0, "protesto_tutar": 0}},
                 "mmxVisits": {}, "mmxCollections": {}}}


def _settings():
    return F.settings_from(lambda k, d="": d)


def test_build_snapshot_and_scope(engine):
    portfolio, signals, info = F.build(_data(), _settings(), None, {})
    s = {x["logo_code"]: x for x in signals}["120.01"]
    assert s["ytd_net_ciro"] == 60000 and s["iade_orani"] == round(10000 / 70000, 4) and s["gecen_yil_ayni_donem"] == 100000
    assert s["risk_doluluk"] == 0.92 and s["siparis_riskte"] == 1 and s["siparis_riskte_sebep"] == "Toplam limit"
    assert s["karsiliksiz_olay_12ay"] == 1 and s["son_odeme_tarihi"] == "2026-07-19" and s["hedef_acigi"] is None
    assert info["assigned"] == 1 and info["portfolio"] == 2                     # 120.02 servis hesabında: temsilcisiz
    F.write_snapshot(engine, T, portfolio, signals)
    mine = F.portfolio_rows(engine, T, "ayseb")
    assert [r["logo_code"] for r in mine] == ["120.01"] and mine[0]["vadesi_gecmis"] == 42000
    assert len(F.portfolio_rows(engine, T, None)) == 2
    assert F.in_scope(engine, T, "ayseb", "120.01", False)["unvan"]
    with pytest.raises(F.FieldError) as e:
        F.in_scope(engine, T, "baskasi", "120.01", False)
    assert e.value.status == 403
    F.write_snapshot(engine, T, portfolio[:1], signals[:1])                     # tam değiştirme
    assert len(F.portfolio_rows(engine, T, None)) == 1


# ------------------------------------------------------------------ CRM tahsilat


def test_crm_collections_view_scope_and_reasons():
    now = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)
    items = [{"id": "c1", "ad": "T1", "account_id": ACC1, "owner_id": U1, "durum": S.T_PENDING, "tip": 100000000, "tutar": 1000,
              "olusturma": "2026-09-25T12:00:00"},
             {"id": "c2", "ad": "T2", "account_id": ACC2, "owner_id": U2, "durum": S.T_REJECTED, "tutar": 500,
              "red_tarihi": "2026-09-20T09:00:00", "red_sebep": 100000002},
             {"id": "c3", "ad": "T3", "account_id": ACC1, "owner_id": U2, "durum": S.T_REJECTED, "tutar": 700,
              "red_tarihi": "2026-09-21T09:00:00", "red_sebep": 100000003, "red_metin": "makbuz yok"}]
    users = {U1: {"hesap": "ayseb", "ad": "Ayşe"}, U2: {"hesap": "servis", "ad": "S"}}
    accs = {ACC1: {"logo_code": "120.01", "unvan": "A"}, ACC2: {"logo_code": "120.02", "unvan": "B"}}
    pend = F.collections_view(items, durum="onay-bekliyor", owner_ids={U1}, codes={"120.01"}, users=users, accounts=accs,
                              labels={}, now=now)
    assert pend["count"] == 1 and pend["items"][0]["yasSaat"] == 72.0 and pend["items"][0]["tip"] == "Çek"
    rej = F.collections_view(items, durum="reddedildi", owner_ids={U1}, codes={"120.01"}, users=users, accounts=accs,
                             labels={"c3": {"etiket": 100000001, "olasilik": None}}, now=now)
    assert [x["id"] for x in rej["items"]] == ["c3"]                                 # başkasının carisi değil, kendi carisi
    assert rej["items"][0]["zekiEtiket"]["etiket"] == "Makbuz ile evrak uyumsuzluğu"
    assert rej["reasons"][0]["sebep"] == "Diğer"
    with pytest.raises(F.FieldError):
        F.collections_view(items, durum="yanlis", owner_ids=None, codes=None, users=users, accounts=accs, labels={})


# ------------------------------------------------------------------ haftalık rapor


def test_weekly_report_rows():
    rows = [{"ad_hesap": "ayseb", "temsilci_ad": "Ayşe", "ytd_net_ciro": 60000, "gecen_yil_ayni_donem": 100000,
             "hedef_beklenen": 80000, "vadesi_gecmis": 42000, "k_90p": 42000, "karsiliksiz_olay_12ay": 1}]
    visits = [{"tur": "cari", "durum": "yapildi", "gerceklesen": "2026-09-22T10:00", "sahip": "ayseb", "notu": "x"},
              {"tur": "cari", "durum": "yapildi", "gerceklesen": "2026-09-29T10:00", "sahip": "ayseb", "notu": "x"}]
    cols = [{"owner_id": U1, "durum": S.T_PENDING, "tutar": 1000}, {"owner_id": U1, "durum": S.T_REJECTED, "red_tarihi": "2026-09-23"}]
    out = F.weekly_report(rows, visits, cols, {U1: {"hesap": "ayseb"}}, date(2026, 9, 21), date(2026, 9, 27))
    x = out[0]
    assert x["ziyaret"] == 1 and x["not"] == 1 and x["onayBekleyen"] == 1 and x["reddedilen"] == 1
    assert x["hedefOrani"] == 0.75 and x["buyume"] == -0.4
    assert F.week_bounds("2026-W39") == (date(2026, 9, 21), date(2026, 9, 27))
    assert F.week_bounds("", date(2026, 9, 28)) == (date(2026, 9, 21), date(2026, 9, 27))
    assert F.report_xlsx(out, date(2026, 9, 21), date(2026, 9, 27))[:2] == b"PK"


# ------------------------------------------------------------------ SQL biçimi


def test_sql_shapes_follow_the_certified_definitions():
    ag = S.aging_sql("411", 2026, date(2026, 9, 28), clientref=12)
    assert "LG_411_01_CLFLINE" in ag and "LG_411_01_PAYTRANS" in ag and "C.CODE LIKE '120%'" in ag and "L.CLIENTREF = 12" in ag
    assert "ORDER BY PT.DATE_ DESC, PT.LOGICALREF DESC" in ag and "'2026-09-28'" in ag
    sales = S.sales_sql("411", date(2026, 1, 1), date(2026, 8, 17))
    assert "INVOICEREF <> 0" in sales and "LINETYPE = 0" in sales and "TRCODE IN (2,3,7,8,9)" in sales and "< '2026-08-18'" in sales
    ch = S.cheque_events_sql("411", date(2025, 9, 28))
    assert "T.STATUS = 11" in ch and "T.DEVIR = 0" in ch and "K.DOC IN (1, 2)" in ch and "G.STATUS = 1" in ch
    crm = S.crm_collections_sql("Timas_MSCRM.dbo", date(2026, 6, 30))
    for secret in ("vergitckimlikno", "ceknumarasi", "hesapno", "bankanumarasi", "subeno"):
        assert secret not in crm.lower()
    acc = S.crm_accounts_sql("Timas_MSCRM.dbo")
    assert "Address" not in acc and "Telephone" not in acc and "EMail" not in acc
    mmx = S.mmx_visits_sql("411", date(2025, 9, 28))
    assert "LAT" not in mmx and "GSM" not in mmx and "ICERIK" not in mmx
    with pytest.raises(S.SourceError):
        S.aging_sql("4x1", 2026, date(2026, 9, 28))
    with pytest.raises(S.SourceError):
        S.invoices_for_sql("411", "120'; DROP")
    with pytest.raises(S.SourceError):
        S.crm_orders_for_sql("Timas_MSCRM.dbo", "not-a-guid", 90, date(2026, 9, 28))
    assert S.trcodes("") == (1, 20, 61, 62, 70) and S.trcodes("1, 20") == (1, 20)


def test_crm_dates_are_istanbul_days():
    assert S.day("2026-06-30T21:00:00") == "2026-07-01" and S.day("1900-01-01") is None and S.day("2026-08-14") == "2026-08-14"


# ------------------------------------------------------------------ yetki


def test_access_rules_for_field_endpoints():
    assert A.rule_for("/api/v1/field/run-due") == A.SYSTEM
    assert A.rule_for("/api/v1/field/today") == {"sayfa:saha"}
    assert A.rule_for("/api/v1/field/visits/abc") == {"sayfa:saha", "sayfa:okul-tanitim"}
    assert "sayfa:saha" in A.rule_for("/api/v1/budget/targets")
    f = A.features_for
    assert f("POST", "/api/v1/field/visits") == ["ozellik:saha.not"] and f("GET", "/api/v1/field/visits") == []
    assert f("POST", "/api/v1/field/payment-plans/p1/submit") == ["ozellik:saha.not"]
    assert f("POST", "/api/v1/field/payment-plans/p1/approve") == []           # açıkça verilen, ucun içinde
    assert f("DELETE", "/api/v1/field/overrides/o1") == ["ozellik:saha.oncelik-duzenle"]
    assert f("GET", "/api/v1/field/report/weekly.xlsx") == ["ozellik:veri.disa-aktar"]
    assert {"ozellik:saha.herkesinki", "ozellik:saha.odeme-plani-onay", "ozellik:saha.performans"} <= A.explicit_keys()
    assert "sayfa:saha" in A.all_keys()


# ------------------------------------------------------------------ sabah saha brifi


class _BriefLlm:
    def __init__(self, text):
        self.text = text

    def chat(self, messages, **kw):
        return self.text


def test_morning_brief_masks_names_and_falls_back_to_rule_text():
    kpi = {"vadesiGecmis": 42_350.0, "k90": 12_000.0, "onayBekleyen": 2}
    planned = [{"hedef": "120.01", "hedefAd": "Ayşe Yılmaz", "planlanan": "2026-09-28T10:30", "musteri": None}]
    top = [{"code": "120.01", "unvan": "Ayşe Yılmaz", "il": "İstanbul", "kanal": "Kitapçı", "gerekce": [{"label": "Vadesi geçmiş 42 bin ₺"}]},
           {"code": "120.02", "unvan": "Deniz Kitabevi", "il": "Ankara", "kanal": None, "gerekce": []}]
    facts, plain, names = F.morning_facts(kpi, planned, top, "2026-09-28")
    blob = " ".join(facts)
    assert "Ayşe" not in blob and "Deniz" not in blob and "[A]" in blob and "[B]" in blob   # ad modele gitmez
    assert names == {"A": "Ayşe Yılmaz", "B": "Deniz Kitabevi"}
    rule = F.morning_rule_text(plain)
    assert "Ayşe Yılmaz 10:30" in rule and "42 bin ₺" in rule and len(plain) == 5
    ok = F.morning_brief(facts, plain, names, _BriefLlm("Bugün [A] ziyareti 10:30'da. Öncelik [B]. Vadesi geçmiş 42 bin ₺."))
    assert ok["kaynak"] == "zeki" and "Ayşe Yılmaz" in ok["metin"] and "[A]" not in ok["metin"]
    bad = F.morning_brief(facts, plain, names, _BriefLlm("[A] 99 bin ₺ ödeyecek."))        # uydurma rakam
    assert bad["kaynak"] == "kural" and bad["metin"] == rule
    unk = F.morning_brief(facts, plain, names, _BriefLlm("[C] ile görüşün."))               # bilinmeyen etiket
    assert unk["kaynak"] == "kural" and unk["neden"] == "bilinmeyen-etiket"
    assert F.morning_brief(facts, plain, names, None)["kaynak"] == "kural"
    empty, _, _ = F.morning_facts({"vadesiGecmis": 0}, [], [], "2026-09-28")
    assert empty == ["Bugün (2026-09-28) planlı ziyaret yok.", "Portföyde vadesi geçmiş alacak yok."]
    assert A.features_for("GET", "/api/v1/field/today/brief") == []
# ------------------------------------------------------------------ kabul hataları (2026-09-28)


def test_payment_plan_body_is_validated_before_the_customer_state():
    """Bozuk gövde her caride 422; gövde sağlam ama vadesi geçmiş alacak yoksa 409 (eskiden ikisi de 400)."""
    eng = open_store("sqlite://").engine
    F._ready.discard(id(eng))
    F.ensure(eng)
    none_due = {"logo_code": "120.09", "unvan": "Z", "ad_hesap": "ayseb", "vadesi_gecmis": 0, "odeme_12ay": 0}
    due = {**none_due, "vadesi_gecmis": 12000, "odeme_12ay": 48000}
    for bad in ("iki", True, 2.5, 0, 25, -1, "3,5"):
        with pytest.raises(F.FieldError) as e:
            F.create_plan(eng, T, "ayseb", none_due, {"taksitSayisi": bad}, 6, date(2026, 9, 28))
        assert e.value.status == 422, bad
    with pytest.raises(F.FieldError) as e:
        F.create_plan(eng, T, "ayseb", none_due, {"taksitSayisi": 2, "baslangic": "15.10.2026"}, 6, date(2026, 9, 28))
    assert e.value.status == 422                                                   # tarih biçimi de önce
    with pytest.raises(F.FieldError) as e:
        F.create_plan(eng, T, "ayseb", none_due, {}, 6, date(2026, 9, 28))
    assert e.value.status == 409
    p = F.create_plan(eng, T, "ayseb", due, {"taksitSayisi": "4", "baslangic": "2026-10-15"}, 6, date(2026, 9, 28))
    assert len(p["taksitler"]) == 4 and p["taksitler"][0]["tarih"] == "2026-10-15" and p["taksitToplam"] == 12000
    assert len(F.create_plan(eng, T, "ayseb", due, {"taksitSayisi": 24.0}, 6, date(2026, 9, 28))["taksitler"]) == 24


def test_short_write_turns_a_lock_wait_into_a_quick_retryable_error(engine):
    import sqlalchemy as sa

    class Orig(Exception):
        pgcode = "55P03"

    with pytest.raises(F.FieldError) as e:
        with F.short_write(engine):
            raise sa.exc.OperationalError("INSERT …", {}, Orig("lock timeout"))
    assert e.value.status == 503 and "tekrar deneyin" in str(e.value)
    with pytest.raises(sa.exc.OperationalError):                                   # kilit dışı hata olduğu gibi
        with F.short_write(engine):
            raise sa.exc.OperationalError("INSERT …", {}, Exception("disk dolu"))
    with F.short_write(engine) as c:                                               # sqlite: SET LOCAL yok, yazma olur
        c.execute(F.META.insert().values(tenant_id=T, key="k", value_json='{"a": 1}', updated_at=F._now()))
    assert F.meta_get(engine, T, "k")["a"] == 1


def _field_app(engine, calls):
    from fastapi import FastAPI, HTTPException, Request

    from semantic_bridge import field_sales_api

    def auth(request: Request):
        user = request.headers.get("x-test-user")
        if not user:
            raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Oturum gerekli."})
        return engine, T, user, user

    def source(name):
        def connect():
            calls.append(name)                     # yazma yolunda CRM/Logo'ya bağlanılmaz
            raise AssertionError(f"{name} bağlantısı istenmemeli")
        return connect

    app = FastAPI()
    field_sales_api.register(app, {
        "auth": auth, "require_caller": lambda r: None, "can": lambda u, k: False, "is_admin": lambda u: False,
        "audit": lambda *a, **k: calls.append("audit"), "conf": lambda k, d="": d, "fresh": lambda: False,
        "crm_connect": source("crm"), "logo_connect": source("logo"), "llm": lambda: calls.append("llm"),
        "engine": lambda: engine, "tenant": lambda: T})
    return app


def test_visit_note_write_is_local_and_403_carries_forbidden(engine):
    """Kabul: tek geçerli not 120 sn'de zaman aşımına düşmüştü; yazma yolu yalnız yerel tablolar (CRM/Logo/model yok).
    FieldError(403) ön yüze FIELD koduyla gidiyordu → engine.ts «oturum düştü» sanıyordu: artık FORBIDDEN."""
    import time

    from fastapi.testclient import TestClient

    portfolio, signals, _ = F.build(_data(), _settings(), None, {})
    F.write_snapshot(engine, T, portfolio, signals)
    calls: list[str] = []
    client = TestClient(_field_app(engine, calls))
    me, other = {"x-test-user": "ayseb"}, {"x-test-user": "baskasi"}

    t0 = time.monotonic()
    r = client.post("/api/v1/field/visits", json={"hedef": "120.01", "notu": "kabul denemesi", "gizli": True}, headers=me)
    assert r.status_code == 201, r.text
    assert time.monotonic() - t0 < 5
    assert calls == ["audit"]                                                     # CRM/Logo/model çağrısı yok
    vid = r.json()["id"]
    r2 = client.patch(f"/api/v1/field/visits/{vid}", json={"ton": "notr"}, headers=me)
    assert r2.status_code == 200 and r2.json()["ton"] == "notr"
    assert "crm" not in calls and "logo" not in calls and "llm" not in calls

    for method, path, body in (("post", "/api/v1/field/visits", {"hedef": "120.01", "notu": "x"}),
                               ("patch", f"/api/v1/field/visits/{vid}", {"notu": "başkası"}),
                               ("post", "/api/v1/field/payment-plans", {"code": "120.01"})):
        denied = getattr(client, method)(path, json=body, headers=other)
        assert denied.status_code == 403, (path, denied.text)
        assert denied.json()["detail"]["code"] == "FORBIDDEN", path

    bad = client.post("/api/v1/field/payment-plans", json={"code": "120.01", "taksitSayisi": "iki"}, headers=me)
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "FIELD"
    assert client.post("/api/v1/field/visits", json={"hedef": "120.01", "ton": "kizgin"}, headers=me).status_code == 422


def test_slow_write_log_names_the_waiting_step():
    from semantic_bridge import field_sales_api as FA

    assert FA._slow_write("ziyaret notu", 0.0, [("oturum", 0.1), ("kayıt", 0.5)]) is None
    msg = FA._slow_write("ziyaret notu", 0.0, [("oturum", 0.1), ("kapsam", 0.2), ("kayıt", 121.0)])
    assert msg and "kayıt 120.80 sn" in msg and "121.0 sn" in msg
