"""M51 Müşteri hizmetleri: kimlik bilgisi kolon yasağı, değer güvenliği, kişisel veri maskesi, kapalı küme sınıflama eşiği,
taslakta rakamın modelden gelmemesi, SSS eşleşmesi, SLA/kalite hesabı, SSS açığı ve onay kuralı, bağlamın veri alanı
kapısı ve aday seçimi, destek masası istemcisinin yalnız okuması, yetki kuralları.

Sözleşme: masaya, CRM'e ve Logo'ya yazılmaz; `new_kargofirmasi` / `new_webuser` parola-token kolonları hiçbir SQL'de geçmez;
taslaktaki her rakam talepte ya da SQL olgusunda vardır; talep metni köprüde saklanmaz.

Not: kullanıcı kuralı gereği bu testler yerelde koşturulmaz; sunucuda `scripts/acceptance/M51/calistir.sh` koşturur.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta

import pytest

from semantic_bridge import access as A
from semantic_bridge import support as S
from semantic_bridge import support_sources as src
from semantic_bridge.field_sales_sources import SourceError
from semantic_layer.runtime.llm_choose import Choice
from semantic_layer.store.catalog_store import open_store

T = "t1"
ACC1 = "aaaaaaaa-0000-0000-0000-000000000001"
ACC2 = "aaaaaaaa-0000-0000-0000-000000000002"
ORD1 = "bbbbbbbb-0000-0000-0000-000000000001"
CON1 = "cccccccc-0000-0000-0000-000000000001"
SCHEMA = "Timas_MSCRM.dbo"


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    S._ready.discard(id(e))
    S.ensure(e)
    return e


def _st(**kw):
    st = S.settings_from(lambda k, d="": d)
    st.update(kw)
    return st


# ------------------------------------------------------------------ kimlik bilgisi yasağı


def _all_sql() -> list[str]:
    today = date(2026, 9, 28)
    return [
        src.crm_contacts_sql(SCHEMA, email="a@b.com", phone="0532 111 22 33"),
        src.crm_webusers_sql(SCHEMA, "a@b.com"),
        src.crm_accounts_sql(SCHEMA, ids=[ACC1], code="120.01", email="a@b.com", phone="02121112233"),
        src.crm_account_search_sql(SCHEMA, "Kitap", 0, 25, [100000008]),
        src.crm_orders_sql(SCHEMA, accounts=[ACC1], since=today),
        src.crm_orders_sql(SCHEMA, order_no="TS-240915"),
        src.crm_orders_sql(SCHEMA, accounts=[ACC1], open_only=True),
        src.crm_shipments_sql(SCHEMA, [ORD1]),
        src.crm_tracking_sql(SCHEMA, [ORD1]),
        src.crm_cargo_info_sql(SCHEMA, ["123"], ["IRS1"]),
        src.crm_cargo_firms_sql(SCHEMA),
        src.crm_order_status_sql(SCHEMA),
        src.crm_knowledge_sql(SCHEMA),
        src.crm_email_templates_sql(SCHEMA),
        src.logo_invoices_sql("411", "120.01", today),
        src.logo_invoices_by_no_sql("411", ["A1"]),
        src.logo_client_sql("411", "120.01"),
        src.logo_data_end_sql("411"),
    ]


def test_no_sql_touches_credential_columns():
    for sql in _all_sql():
        low = sql.lower()
        for col in src.FORBIDDEN_COLUMNS:
            assert not re.search(rf"(?<![a-z0-9_]){col}(?![a-z0-9_])", low), (col, sql)


def test_cargo_firm_query_selects_only_id_name_code():
    sql = src.crm_cargo_firms_sql(SCHEMA)
    cols = re.search(r"SELECT (.*) FROM", sql).group(1)
    assert [c.strip().split(" AS ")[0] for c in cols.split(",")] == ["f.new_kargofirmasiId", "f.new_name", "f.new_kargokodu"]


@pytest.mark.parametrize("col", ["new_sifre", "new_token", "new_clientsecret", "NEW_KULLANICIADI", "obs_emailforgotpasswordtoken"])
def test_guard_refuses_forbidden_column(col):
    with pytest.raises(SourceError):
        src.guard(f"SELECT f.{col} FROM Timas_MSCRM.dbo.new_kargofirmasiBase f")


def test_guard_does_not_trip_on_longer_names():
    src.guard("SELECT new_tokenlike_x, new_sifreli FROM t")   # başka kolon; yasak değil


def test_contact_query_never_selects_email_or_phone():
    sql = src.crm_contacts_sql(SCHEMA, email="okur@example.com", phone="+90 (532) 111-22-33")
    select = sql.split(" FROM ")[0]
    assert "EMail" not in select and "Phone" not in select and "Telephone" not in select
    assert "'5321112233'" in sql and "N'okur@example.com'" in sql


# ------------------------------------------------------------------ değer güvenliği


@pytest.mark.parametrize("bad", ["x' OR 1=1 --", "a@b", "", "a@b.c'om"])
def test_email_literal_rejects(bad):
    with pytest.raises(SourceError):
        src.email_literal(bad)


def test_order_and_code_literals():
    assert src.order_literal(" TS-240915 ") == "TS-240915"
    with pytest.raises(SourceError):
        src.order_literal("1'; DROP TABLE x--")
    with pytest.raises(SourceError):
        src.code_literal("120'01")
    with pytest.raises(SourceError):
        src.phone_digits("12345")
    assert src.like_literal("50%_[x]") == "50[%][_][[]x]"


def test_orders_sql_pending_definition_and_window():
    sql = src.crm_orders_sql(SCHEMA, accounts=[ACC1], since=date(2025, 9, 28))
    assert "new_bekleyenadet > 0" in sql and "NOT IN (100000015, 100000000, 100000001, 100000003, 2)" in sql
    assert "s.new_siparistarihi >= '2025-09-28' OR" in sql    # açık sipariş pencereden bağımsız gelir
    sql2 = src.crm_orders_sql(SCHEMA, order_no="TS-1")
    assert "new_name = N'TS-1'" in sql2 and "new_b2csiparisnumarasi" in sql2


def test_text_number_c19():
    assert src.text_number("1.234,50") == 1234.5
    assert src.text_number("12,5") == 12.5
    assert src.text_number("12.5") == 12.5
    assert src.text_number("") is None and src.text_number("yok") is None


def test_rating_scale():
    assert src.rating_5(0.8) == 4.0
    assert src.rating_5(4) == 4.0
    assert src.rating_5(0) is None and src.rating_5(None) is None


# ------------------------------------------------------------------ kişisel veri maskesi


def test_mask_personal_and_model_text():
    t = ("Merhaba, siparişim TS-240915 gelmedi. Telefonum 0532 111 22 33, e-postam ali@example.com, "
         "IBAN TR12 0006 1005 1978 6457 8413 26, TC 12345678901.\nSaygılarımla\nAli Veli\nAdres: Kadıköy")
    m = S.model_text("Kargo", t, 1500)
    for leak in ("0532", "ali@example.com", "TR12", "12345678901", "Kadıköy", "Ali Veli"):
        assert leak not in m
    assert "TS-240915" in m and "[telefon]" in m and "[e-posta]" in m


def test_model_text_is_truncated():
    assert len(S.model_text("k", "a" * 5000, 300)) == 300


# ------------------------------------------------------------------ sınıflama


class FakeLlm:
    def __init__(self, klass_probs, urgency="normal"):
        self.klass_probs, self.urgency, self.prompts = klass_probs, urgency, []

    def choose(self, prompt, choices, **kw):
        self.prompts.append(prompt)
        if set(choices) == set(S.URGENCY):
            return Choice(self.urgency, choices.index(self.urgency), {c: (0.9 if c == self.urgency else 0.05) for c in choices},
                          "logprobs", margin=0.85)
        probs = {c: self.klass_probs.get(c, 0.0) for c in choices}
        best = max(probs, key=probs.get)
        second = sorted(probs.values())[-2]
        return Choice(best, choices.index(best), probs, "logprobs", margin=probs[best] - second)

    def chat(self, messages, **kw):
        return self.reply


def test_classify_confident_and_unsure(engine):
    classes = S.list_classes(engine, T, active_only=True)
    st = _st()
    ok = S.classify(FakeLlm({"Kargo gecikmesi": 0.92, "Diğer": 0.08}), "Kargo", "Siparişim gelmedi", classes, st)
    assert ok["klass"] == "kargo-gecikmesi" and ok["urgency"] == "normal"
    low = S.classify(FakeLlm({"Kargo gecikmesi": 0.5, "Hasarlı / eksik ürün": 0.45}), "x", "y", classes, st)
    assert low["klass"] is None and low["guess"] == "kargo-gecikmesi"   # eşik altı: sınıflanamadı, yalnız tahmin


def test_classify_prompt_masks_personal_data(engine):
    llm = FakeLlm({"Diğer": 1.0})
    S.classify(llm, "Konu", "Beni 0532 111 22 33'ten arayın", S.list_classes(engine, T), _st())
    assert all("0532" not in p for p in llm.prompts)


def test_classify_without_model_raises(engine):
    with pytest.raises(S.SupportError):
        S.classify(None, "a", "b", S.list_classes(engine, T), _st())


# ------------------------------------------------------------------ taslak: rakam modelden gelmez


def test_fill_draft_fills_placeholders_and_drops_invented_numbers():
    facts = {"siparis_no": "TS-240915", "kargo_firmasi": "Aras", "takip_no": "123456789"}
    raw = ("Merhaba, {siparis_no} numaralı siparişiniz {kargo_firmasi} ile yola çıktı. Takip numaranız {takip_no}. "
           "Kargonuz 3 gün içinde elinizde olur. Teslim tarihi {teslim_tarihi} olarak görünüyor. İyi okumalar.")
    out = S.fill_draft(raw, facts, "Siparişim nerede?", "Timaş")
    assert "TS-240915" in out["text"] and "Aras" in out["text"] and "123456789" in out["text"]
    assert "3 gün" not in out["text"]                  # uydurma rakam → cümle düşer
    assert "teslim_tarihi" not in out["text"]          # olgusu olmayan yer tutucu → cümle düşer
    assert out["dropped"] == 2 and out["text"].endswith("Timaş")


def test_fill_draft_allows_numbers_from_ticket():
    out = S.fill_draft("48–64. sayfalar için özür dileriz.", {}, "Kitabın 48-64. sayfaları eksik", "")
    assert "48–64" in out["text"]


def test_facts_from_context_uses_first_order_and_cargo():
    ctx = {"match": {"contacts": [{"ad": "Ayşe Yılmaz"}]},
           "orders": [{"id": ORD1, "no": "TS-1", "tarih": "2026-09-01", "durumAd": "Sevk edildi", "sevkTarihi": "2026-09-03",
                       "kargoFirma": None, "takipNo": "T1", "takipUrl": None, "bekleyen": 0, "acik": False}],
           "cargo": [{"orderIds": [ORD1], "takipNo": "T1", "firma": "Aras", "teslimTarihi": "05.09.2026"}],
           "shipments": [{"orderId": ORD1, "faturaNo": "F1", "logo": {"tarih": "2026-09-03"}}]}
    f = S.facts_from_context(ctx)
    assert f["siparis_no"] == "TS-1" and f["kargo_firmasi"] == "Aras" and f["teslim_tarihi"] == "05.09.2026"
    assert f["siparis_tarihi"] == "01.09.2026" and f["fatura_no"] == "F1" and "bekleyen_adet" not in f


def test_edit_ratio_and_order_refs():
    assert S.edit_ratio("abc", "abc") == 0.0
    assert S.edit_ratio("abc", "xyz") == 1.0
    assert S.order_refs("Sipariş no TS-240915, tel 05321112233") == ["TS-240915"]


# ------------------------------------------------------------------ SSS eşleştirme


def test_faq_lexical_match_and_threshold():
    idx = S.FaqIndex(None)
    idx.load([{"source": "destek", "id": "1", "title": "Kargom nerede?", "text": "Kargo takip numaranızla takip edebilirsiniz."},
              {"source": "crm", "id": "2", "title": "E-kitap nasıl indirilir", "text": "Uygulamadan giriş yapın."}])
    r = idx.match("Kargom gelmedi, kargo takip nerede", _st())
    assert r["method"] == "lexical" and r["matches"][0]["id"] == "1"
    none = idx.match("Fatura adresimi değiştirmek istiyorum", _st(faqMinLexical=0.5))
    assert none["matches"] == []


def test_faq_embedding_path():
    vec = {"Kargom nerede?\nx": [1.0, 0.0], "E-kitap\ny": [0.0, 1.0]}

    def embed(texts):
        return [vec.get(t, [0.9, 0.1]) for t in texts]

    idx = S.FaqIndex(embed)
    idx.load([{"source": "destek", "id": "1", "title": "Kargom nerede?", "text": "x"},
              {"source": "destek", "id": "2", "title": "E-kitap", "text": "y"}])
    r = idx.match("kargo", _st())
    assert r["method"] == "embedding" and r["matches"][0]["id"] == "1"


# ------------------------------------------------------------------ SLA ve kalite


def _t(name, opened, **kw):
    d = datetime.fromisoformat(opened)
    return {"name": name, "opening_date": d.date().isoformat(), "opening_time": d.time().isoformat(), **kw}


def test_sla_state():
    now = datetime(2026, 9, 28, 12, 0)
    assert S.sla_state(_t("1", "2026-09-28T08:00:00", response_by="2026-09-28 11:00:00"), now, 0.8) == "asildi"
    assert S.sla_state(_t("2", "2026-09-28T08:00:00", response_by="2026-09-28 12:30:00"), now, 0.8) == "yaklasiyor"
    assert S.sla_state(_t("3", "2026-09-28T08:00:00", response_by="2026-09-29 08:00:00"), now, 0.8) == "icinde"
    assert S.sla_state(_t("4", "2026-09-28T08:00:00", first_responded_on="2026-09-28 09:00:00",
                          resolution_by="2026-09-28 10:00:00"), now, 0.8) == "asildi"
    assert S.sla_state(_t("5", "2026-09-28T08:00:00"), now, 0.8) is None
    assert S.sla_state(_t("6", "2026-09-28T08:00:00", agreement_status="Failed"), now, 0.8) == "asildi"


def test_quality_numbers(engine):
    cur = [_t("A", "2026-09-20T10:00:00", status_category="Resolved", first_responded_on="2026-09-20 10:30:00",
              resolution_date="2026-09-20 14:00:00", feedback_rating=0.8),
           _t("B", "2026-09-21T10:00:00", status_category="Open", first_responded_on="2026-09-21 11:30:00", via_customer_portal=1),
           _t("C", "2026-09-22T10:00:00", status_category="Open")]
    prev = [_t("P", "2026-08-20T10:00:00")]
    ins = {"A": {"klass": "kargo-gecikmesi", "raisedByHash": "h1", "faqHit": True},
           "B": {"klass": "kargo-gecikmesi", "raisedByHash": "h1", "faqHit": False},
           "C": {"klass": None, "raisedByHash": "h2", "faqHit": False},
           "P": {"klass": "fatura"}}
    q = S.quality(cur, prev, cur[1:], ins, S.list_classes(engine, T), date(2026, 9, 1), date(2026, 9, 30),
                  datetime(2026, 9, 28, 12), _st(), per_agent=False)
    assert q["opened"] == 3 and q["resolved"] == 1 and q["openNow"] == 2
    assert q["firstResponseMedianMin"] == 60.0            # 30 ve 90 dakikanın medyanı
    assert q["resolutionMedianHours"] == 4.0 and q["csat"] == 4.0 and q["csatCount"] == 1
    assert q["channel"] == {"portal": 1, "eposta": 2}
    topics = {t["klass"]: t for t in q["topics"]}
    assert topics["kargo-gecikmesi"]["count"] == 2 and topics["siniflanamadi"]["count"] == 1
    assert q["repeat"]["count"] == 1                        # aynı kişi, aynı konu, 1 gün arayla
    assert q["agents"] is None


# ------------------------------------------------------------------ sınıflar, SSS açığı, sonuç


def test_seed_and_class_rules(engine):
    cls = S.list_classes(engine, T)
    assert [c["klass"] for c in cls][:2] == ["kargo-gecikmesi", "hasarli-eksik"] and len(cls) == 9
    with pytest.raises(S.SupportError):
        S.save_class(engine, T, "u", "diger", {"label": "Diğer", "active": False})
    out = S.save_class(engine, T, "u", "kargo-gecikmesi", {"label": "Kargo gecikmesi", "slaFirstHours": "4", "slaResolveHours": 24})
    assert out["slaFirstHours"] == 4.0 and out["slaResolveHours"] == 24.0
    with pytest.raises(S.SupportError):
        S.save_class(engine, T, "u", "Kötü Kod", {"label": "x"})


def test_gaps_candidate_and_approval(engine):
    classes = S.list_classes(engine, T)
    ins = [{"ticket": f"T{i}", "klass": "ekitap-erisim", "faqHit": False, "openedOn": "2026-09-20"} for i in range(4)]
    ins.append({"ticket": "X", "klass": "fatura", "faqHit": False, "openedOn": "2026-09-20"})
    r = S.refresh_gaps(engine, T, ins, classes, _st(gapMinTickets=3), date(2026, 9, 1))
    assert r["new"] == 1
    gaps = S.list_gaps(engine, T)
    assert len(gaps) == 1 and gaps[0]["klass"] == "ekitap-erisim" and gaps[0]["tickets"] == 4
    gid = gaps[0]["id"]
    with pytest.raises(S.SupportError):
        S.patch_gap(engine, T, gid, "mudur", {"status": "onayli"})          # metinsiz onay yok
    g = S.patch_gap(engine, T, gid, "mudur", {"question": "E-kitap nasıl indirilir?", "draft": "Uygulamadan…", "status": "onayli"})
    assert g["status"] == "onayli" and g["approvedBy"] == "mudur"
    assert S.approved_faq(engine, T)[0]["id"] == gid
    S.refresh_gaps(engine, T, ins + [{"ticket": "T9", "klass": "ekitap-erisim", "faqHit": False, "openedOn": "2026-09-21"}],
                   classes, _st(gapMinTickets=3), date(2026, 9, 1))
    g2 = S.list_gaps(engine, T)[0]
    assert g2["tickets"] == 5 and g2["question"] == "E-kitap nasıl indirilir?"   # metne dokunulmaz


def test_insight_outcome_keeps_only_ratio(engine):
    S.upsert_insight(engine, T, "HD-1", klass="fatura", draft="Merhaba, faturanız ektedir.")
    with pytest.raises(S.SupportError):
        S.record_outcome(engine, T, "HD-2", "u", True, "x")
    i = S.record_outcome(engine, T, "HD-1", "u", True, "Merhaba, faturanız ektedir.")
    assert i["finalSent"] is True and i["editRatio"] == 0.0
    with engine.connect() as c:
        row = c.execute(S.INSIGHTS.select()).first()
    assert "final_text" not in row._mapping.keys()


def test_set_class_marks_human(engine):
    S.upsert_insight(engine, T, "HD-1", klass="fatura", klass_by="zeki")
    i = S.set_class(engine, T, "HD-1", "temsilci", "iade-cayma", "yüksek", S.list_classes(engine, T))
    assert i["klass"] == "iade-cayma" and i["klassBy"] == "temsilci" and i["urgency"] == "yüksek"
    with pytest.raises(S.SupportError):
        S.set_class(engine, T, "HD-1", "temsilci", "yok-boyle", None, S.list_classes(engine, T))


# ------------------------------------------------------------------ bağlam: veri alanı ve aday seçimi


class FakeSource(S.Source):
    def __init__(self, crm_rows, logo_rows=None):
        super().__init__(lambda: None, lambda: None, lambda st: src.DestekClient("", "", ""))
        self.crm_rows, self.logo_rows, self.sqls = crm_rows, logo_rows or {}, []

    def crm(self, fn):
        def run(sql):
            src.guard(sql)
            self.sqls.append(sql)
            for key, rows in self.crm_rows.items():
                if key in sql:
                    return rows
            return []
        return fn(run)

    def logo(self, fn):
        def run(sql):
            self.sqls.append(sql)
            for key, rows in self.logo_rows.items():
                if key in sql:
                    return rows
            return []
        return fn(run)

    def logo_calendar(self, now):
        return {"firms": {2026: "411"}, "year": 2026, "firm": "411", "dataEnd": "2026-08-17"}


def _crm(two_accounts=False):
    accs = [{"account_id": ACC1, "unvan": "Kitapçı A", "cari_kodu": "120.01", "kanal": 100000001}]
    if two_accounts:
        accs.append({"account_id": ACC2, "unvan": "Kitapçı B", "cari_kodu": "120.02", "kanal": 100000008})
    return {
        "FROM Timas_MSCRM.dbo.ContactBase": [{"contact_id": CON1, "ad": "Ayşe", "account_id": ACC1, "account_type": 1}],
        "FROM Timas_MSCRM.dbo.new_webuserBase": [],
        "FROM Timas_MSCRM.dbo.AccountBase": accs,
        "FROM Timas_MSCRM.dbo.new_siparisBase": [
            {"order_id": ORD1, "no": "TS-1", "tarih": "2026-09-01", "durum": 100000004, "tip": 1, "adet": 10, "bekleyen": 4,
             "takip_no": "T1", "kargo_firma_id": None, "account_id": ACC1}],
        "FROM Timas_MSCRM.dbo.new_sevkiyatBase": [{"shipment_id": "dddddddd-0000-0000-0000-000000000001", "no": "S1",
                                                   "order_id": ORD1, "tarih": "2026-09-03", "durum": 100000000, "fatura_no": "F1"}],
        "FROM Timas_MSCRM.dbo.new_kargotakipbilgisiBase": [],
        "FROM Timas_MSCRM.dbo.new_kargobilgisiBase": [{"takip_no": "T1", "firma": "Aras", "tutar": "12,5", "teslim_tarihi": "05.09.2026"}],
        "FROM Timas_MSCRM.dbo.new_kargofirmasiBase": [],
        "StringMapBase": [],
    }


def test_context_requires_cari_domain():
    with pytest.raises(S.SupportError) as e:
        S.context(FakeSource(_crm()), _st(), email="a@b.com", domains=frozenset({"satis"}))
    assert e.value.status == 403


def test_context_hides_sales_without_satis_domain():
    out = S.context(FakeSource(_crm()), _st(), email="a@b.com", domains=frozenset({"cari"}), now=date(2026, 9, 28))
    assert out["account"]["cariKodu"] == "120.01" and out["orders"] == [] and out["hidden"]


def test_context_full_and_logo_data_end():
    fs = FakeSource(_crm(), {"LG_411_01_INVOICE I JOIN": [{"tarih": "2026-08-10", "no": "F1", "tur": 8, "tutar": 100}],
                             "I.FICHENO IN": [{"no": "F1", "tarih": "2026-08-10", "tur": 8, "tutar": 100, "cari": "120.01"}]})
    out = S.context(fs, _st(), email="a@b.com", domains=None, now=date(2026, 9, 28))
    o = out["orders"][0]
    assert o["riskte"] and o["acik"] and o["durumAd"] == "Risk limit onayı bekliyor"
    assert out["cargo"][0]["firma"] == "Aras" and out["cargo"][0]["tutar"] == 12.5 and out["cargo"][0]["orderIds"] == [ORD1]
    assert out["logo"]["dataEnd"] == "2026-08-17" and out["invoices"][0]["no"] == "F1"
    assert out["shipments"][0]["logo"]["no"] == "F1"
    assert out["summary"] == {"orders": 1, "open": 1, "risk": 1, "pending": 4.0}


def test_context_two_accounts_needs_choice():
    out = S.context(FakeSource(_crm(two_accounts=True)), _st(), email="a@b.com", domains=None, now=date(2026, 9, 28))
    assert out["needsChoice"] and len(out["match"]["accounts"]) == 2 and out["orders"] == []


def test_dealer_view_counts():
    out = S.dealer(FakeSource(_crm()), _st(), ACC1, domains=None, now=date(2026, 9, 28))
    assert out["dealerSummary"]["open"] == 1 and out["dealerSummary"]["risk"] == 1 and out["dealerSummary"]["pending"] == 4.0


# ------------------------------------------------------------------ destek masası istemcisi


def test_destek_client_is_read_only_and_pages():
    calls = []

    def http(url, headers):
        calls.append(url)
        assert headers["Authorization"] == "token k:s"
        start = int(re.search(r"limit_start=(\d+)", url).group(1))
        n = 500 if start == 0 else 3
        return {"data": [{"name": f"{start + i}"} for i in range(n)]}

    c = src.DestekClient("http://destek", "k", "s", http=http)
    rows = c.tickets(opened_from="2026-09-01")
    assert len(rows) == 503 and len(calls) == 2 and "HD%20Ticket" in calls[0]
    with pytest.raises(src.DestekError):
        c._get("/api/method/helpdesk.api.ticket.reply", {})
    with pytest.raises(src.DestekError):
        c.ticket("x/../../y")
    with pytest.raises(src.DestekError):
        src.DestekClient("", "", "").tickets()


def test_clean_html_drops_quoted_history():
    s = src.clean_html("<p>Kargom gelmedi</p><blockquote>eski yazışma</blockquote>")
    assert s == "Kargom gelmedi"


# ------------------------------------------------------------------ yetki kuralları ve katalog


def test_access_rules():
    assert A.rule_for("/api/v1/support/context") == frozenset({A.page("musteri-destek")})
    assert A.rule_for("/api/v1/support/classify/run-due") == A.SYSTEM
    assert A.rule_for("/api/v1/support/run-due") == A.SYSTEM
    assert A.rule_for("/api/v1/support/panel/context") == A.SYSTEM
    assert A.features_for("POST", "/api/v1/support/draft") == ["ozellik:destek.oneri"]
    assert A.features_for("POST", "/api/v1/support/classify") == ["ozellik:destek.oneri"]
    assert A.features_for("POST", "/api/v1/support/classify/run-due") == []
    assert A.features_for("PUT", "/api/v1/support/insights/HD-1/class") == ["ozellik:destek.oneri"]
    assert A.features_for("GET", "/api/v1/support/context") == []   # açıkça verilen: ucun içinde


def test_catalog_keys():
    cat = json.loads(A.CATALOG_FILE.read_text(encoding="utf-8"))
    pages = {p["key"] for p in cat["pages"]}
    feats = {f["key"]: f for f in cat["features"]}
    assert "sayfa:musteri-destek" in pages
    for k in ("baglam", "sss", "herkesinki", "ayar"):
        assert feats[f"ozellik:destek.{k}"].get("explicit") is True
    assert not feats["ozellik:destek.oneri"].get("explicit")
    assert "ozellik:destek.baglam" in A.explicit_keys()
