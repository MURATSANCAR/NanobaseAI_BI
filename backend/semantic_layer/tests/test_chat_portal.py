"""Zeki AI sohbetine modül verisi (chat_portal, 2026-09-28).

Sınanan: alan kaydının tutarlılığı (konu ↔ alan ↔ sayfa), İK ve kişi tablolarının hiç okunmaması, kişisel/gizli/serbest
metin kolonlarının hiçbir seçenekte ve sonuçta yer almaması, veriyle doğrulanan üst tablo bağı, yalnız onaylı tablonun
cevap vermesi (yapı değişince eski onaylı profil + bekleyen yeni profil), sayfa yetkisi olmayana ret, satır kapsamı
(risk: sahibi/açanı), kiracı süzgeci (kiracısız alt tablo üst tablodan), sabit satır süzgeci (İK iletisi sayılmaz),
anlık görüntü tablosunda yalnız son gün, sorudaki değerin modelsiz koşula dönmesi (olumsuzlama dahil), dönem ve «ilk N»
okuma, eşik altı seçimde netleştirme, modelsiz durumda dürüst cevap, cevap metninde teknoloji adı olmaması ve köprünün
cevap biçimi. Her boş konu için en az üç gerçekçi soru ve beklenen tablo (PORTAL_QUESTIONS) — canlı kabul
scripts/acceptance/sohbet-modul-verisi aynı listeyi gerçek modelle sorar.

Veriler yapaydır (sqlite, modüllerin kendi tablo tanımlarıyla); gerçek veri ve gerçek model test sunucusunda.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
import sqlalchemy as sa

from semantic_bridge import access as A
from semantic_bridge import chat_portal as P
from semantic_bridge import chat_scope
from semantic_layer.runtime.llm_choose import Choice
from semantic_layer.store.catalog_store import open_store

TN = "t1"
TODAY = date(2026, 9, 28)
UTC = timezone.utc

# ------------------------------------------------------------------ her boş konu için gerçekçi sorular
# (konu, soru, beklenen tablo, beklenen ölçü/kırılım/koşul — kabulde modelin seçimi bununla karşılaştırılır)
PORTAL_QUESTIONS = [
    ("pazarlama", "Ekim'de yayımlanacak kitapların toplam pazarlama bütçesi ne?", "semantic_mkt_plans",
     "bütçe toplam toplamı; yayın tarihi ekim"),
    ("pazarlama", "Geçen ay planlanan pazarlama görevlerinin durumlarına göre sayısı?", "semantic_mkt_tasks",
     "kayıt sayısı; durum kırılımı; tarih geçen ay"),
    ("pazarlama", "Bülten sonuçlarında toplam açılan ve tıklanan sayısı?", "semantic_newsletter_results",
     "açılan toplamı / tıklanan toplamı"),
    ("pazarlama", "Bu ay kaç lansman kapandı?", "semantic_mkt_launches", "kayıt sayısı; durum; kapanış bu ay"),
    ("dijital", "Geçen ay reklam harcaması platform bazında ne kadardı?", "semantic_ads_daily",
     "harcama toplamı; reklam kampanyası › reklam hesabı › platform; gün geçen ay"),
    ("dijital", "Son 30 günde en çok etkileşim alan paylaşım türü hangisi?", "semantic_social_metrics",
     "beğeni toplamı; paylaşım › tür; gün son 30 gün"),
    ("dijital", "Aşamasına göre influencer işbirliği sayısı?", "semantic_infl_collabs", "kayıt sayısı; aşama kırılımı"),
    ("eticaret", "Dün sitede kaç sipariş geldi?", "semantic_commerce_orders", "kayıt sayısı; sipariş zamanı dün"),
    ("eticaret", "Trendyol'da geçen hafta en çok iade edilen 10 ürün hangileri?", "semantic_trendyol_claims",
     "adet toplamı; barkod/ürün; tarih geçen hafta; ilk 10"),
    ("eticaret", "Bu yıl ülke bazında yurtdışı satış cirosu?", "semantic_intl_sales", "satış ciro toplamı; ülke; yıl: 2026"),
    ("okur", "E-posta izni olan kaç okurumuz var?", "semantic_okur_inventory", "e-posta izinli toplamı; en son sayım günü"),
    ("okur", "Kaynağına göre KVKK onaylı okur sayısı?", "semantic_okur_inventory", "kvkk onaylı toplamı; kaynak; son gün"),
    ("okur", "Bu ay kaç topluluk programı yapılacak?", "semantic_okur_programs", "kayıt sayısı; tarih bu ay"),
    ("destek", "Yanıt hedefi bugün dolan kaç ileti var, hangi birimde?", "semantic_mail_messages",
     "kayıt sayısı; termin bugün; birim kırılımı"),
    ("destek", "Geçen hafta gelen iletiler kategorisine göre kaç tane?", "semantic_mail_messages",
     "kayıt sayısı; kategori; alınma geçen hafta"),
    ("destek", "Bu ay açılan destek taleplerinin sınıflara göre dağılımı?", "semantic_support_insights",
     "kayıt sayısı; sınıf; açılış bu ay"),
    ("risk", "Açık risk kayıtları kategoriye göre kaç tane?", "semantic_risk_register",
     "kayıt sayısı; durum: açık (sorudan); kategori"),
    ("risk", "Önümüzdeki 60 günde biten sigorta poliçeleri hangileri?", "semantic_risk_policies",
     "liste; bitiş önümüzdeki 60 gün"),
    ("risk", "Hangi risk göstergeleri kırmızıda?", "semantic_risk_indicator_alerts", "liste; durum: kırmızı (sorudan)"),
    ("yonetim", "Durumuna göre kurul aksiyonu sayısı?", "semantic_kurul_actions", "kayıt sayısı; durum kırılımı"),
    ("yonetim", "Bu yıl kaç kurul toplantısı yapıldı?", "semantic_kurul_meetings", "kayıt sayısı; tarih bu yıl"),
    ("yonetim", "Geçen ay kırmızı olan kurul göstergeleri hangileri?", "semantic_kurul_values",
     "liste; renk: kırmızı (sorudan); ölçüm geçen ay"),
    ("isletim", "Model kuyruğunda modüle göre ortalama bekleme süresi?", "sl_llm_job",
     "kuyruk bekleme ortalaması; modül kırılımı"),
    ("isletim", "Son gönderimi başarısız olan planlı raporlar hangileri?", "semantic_reports",
     "liste; son durum: failed; kişinin kendi raporları"),
    ("isletim", "Bu ay kaç sistem olayı açıldı?", "semantic_itops_incidents", "kayıt sayısı; açılış bu ay"),
    ("editoryal", "Hangi başvurular 30 günden fazladır değerlendirmede?", "semantic_editorial_applications",
     "liste; durum; alınma 30 günden eski"),
    ("editoryal", "Durumuna göre çeviri işi sayısı?", "semantic_translation_jobs", "kayıt sayısı; taslak durumu"),
    ("editoryal", "Önümüzdeki 30 günde termini gelen editör görevleri?", "semantic_editorial_tasks",
     "liste; termin önümüzdeki 30 gün"),
    ("editoryal", "Bu ay alınan baskı tekliflerinin ortalama birim fiyatı?", "semantic_production_quotes",
     "birim fiyat ortalaması; oluşturulma bu ay"),
    # 2026-09-29: dağıtımcı ve perakende katalogları (Başarı Dağıtım, D&R) — her kataloğun son görüntüsü sayılır
    ("dagitimci", "Başarı Dağıtım kataloğunda baskısı yok görünen TİMAŞ kitabı kaç tane?", "semantic_pazar_dagitim_titles",
     "kayıt sayısı; katalog: basari, katalog durumu: Baskısı Yok (sorudan); TİMAŞ grubu kitabı: evet; son görüntü"),
    ("dagitimci", "D&R kataloğunda yayınevine göre Prefix B2B stoğu toplamı?", "semantic_pazar_dagitim_titles",
     "dağıtımcı stoğu toplamı; yayınevi kırılımı; katalog: dr; son görüntü"),
    ("dagitimci", "Başarı'da satışta en çok kitabı olan 10 yayınevi hangisi?", "semantic_pazar_dagitim_titles",
     "kayıt sayısı; yayınevi kırılımı; katalog: basari, katalog durumu: Satışta (sorudan); ilk 10"),
    ("dagitimci", "Başarı'da üst kategoriye göre ortalama dağıtımcı iskontosu?", "semantic_pazar_dagitim_titles",
     "dağıtımcı iskontosu ortalaması; üst kategori kırılımı; katalog: basari (sorudan)"),
]


def test_every_portal_topic_has_three_realistic_questions():
    portal_topics = {t["id"] for t in chat_scope.topics() if t.get("portal")}
    assert portal_topics == {"pazarlama", "dijital", "eticaret", "okur", "destek", "risk", "yonetim", "isletim", "editoryal",
                             "dagitimci"}
    for tid in portal_topics:
        qs = [q for q in PORTAL_QUESTIONS if q[0] == tid]
        assert len(qs) >= 3, tid
        topic = chat_scope.topic(tid)
        for _, question, table, _ in qs:
            a = P.area_of_table(table)
            assert a is not None, table
            assert a["id"] in topic["portal"], (tid, table)
            assert P.serves(topic)


# ------------------------------------------------------------------ kayıt tutarlılığı

def test_area_registry_is_consistent_with_topics_and_access_catalog():
    pages = {p["key"] for p in A.catalog()["pages"]} | {f["key"] for f in A.catalog().get("features", [])}
    ids = [a["id"] for a in P.areas()]
    assert len(ids) == len(set(ids))
    topic_ids = {t["id"] for t in chat_scope.topics()}
    referenced = set()
    for t in chat_scope.topics():
        for aid in t.get("portal") or []:
            a = P.area(aid)
            assert a is not None, aid
            assert a["topic"] == t["id"], aid
            referenced.add(aid)
        if t.get("portal"):
            assert not t["data"], f"{t['id']}: portal konusu Logo/CRM alanı taşımaz"
    assert referenced == set(ids), "her alan bir konuya bağlı"
    for a in P.areas():
        assert a["topic"] in topic_ids
        assert a["pages"] and set(a["pages"]) <= pages, a["id"]
        assert a["keywords"], a["id"]
        re.compile(a["tables"])
        for table in (a.get("labels") or {}):
            assert re.search(a["tables"], table), (a["id"], table)
            assert not P.never_table(table), table
        rs = a.get("row_scope")
        if rs:
            assert rs["columns"] and set(rs["unless"]) <= pages


@pytest.mark.parametrize("table", ["semantic_hr_candidates", "semantic_hr_employees", "semantic_hr_survey_responses",
                                   "semantic_readers", "semantic_reader_consents", "semantic_people_profiles",
                                   "semantic_pr_contacts", "semantic_infl_people", "semantic_freelance_people",
                                   "semantic_commerce_customers", "semantic_kurul_members", "semantic_security_logins",
                                   "semantic_access_roles", "semantic_audit", "semantic_mkt_meta", "semantic_itops_state",
                                   "semantic_chat_portal_catalog"])
def test_hr_person_and_system_tables_never_belong_to_an_area(table):
    assert P.never_table(table)
    assert P.area_of_table(table) is None


def test_hr_topic_stays_closed():
    ik = chat_scope.topic("ik")
    assert ik.get("closed") and not ik.get("portal")
    assert not any(a["topic"] == "ik" for a in P.areas())


@pytest.mark.parametrize("name, tname, kind", [
    ("sahip", "str120", P.EXCLUDED), ("sahip_eposta", "str200", P.EXCLUDED), ("olusturan", "str120", P.EXCLUDED),
    ("author_email", "str200", P.EXCLUDED), ("author_phone", "str60", P.EXCLUDED), ("from_display", "str200", P.EXCLUDED),
    ("assignee", "str120", P.EXCLUDED), ("created_by", "str120", P.EXCLUDED), ("username", "str120", P.EXCLUDED),
    ("customer_key", "str64", P.EXCLUDED), ("evaluator_name", "str200", P.EXCLUDED), ("decided_name", "str200", P.EXCLUDED),
    ("api_token", "str200", P.EXCLUDED), ("parola", "str60", P.EXCLUDED),
    ("tanim", "text", P.EXCLUDED), ("subject", "str500", P.EXCLUDED), ("kanit_json", "text", P.EXCLUDED),
    ("durum", "str12", P.ATTRIBUTE), ("kategori", "str20", P.ATTRIBUTE), ("puan", "int", P.MEASURE),
    ("spend", "float", P.MEASURE), ("created_at", "datetime_tz", P.TIME), ("is_hr", "bool", P.DIMENSION),
    ("risk_id", "str32", P.KEY), ("tenant_id", "str80", P.TENANT), ("deleted_at", "datetime", P.SOFT_DELETE),
    ("from_segment", "str16", P.ATTRIBUTE), ("session_id", "str32", P.KEY), ("draft_state", "str20", P.ATTRIBUTE),
    ("draft_done", "int", P.MEASURE),
])
def test_column_classes(name, tname, kind):
    assert P.classify_column(name, tname)[0] == kind


# ------------------------------------------------------------------ yapay veri

@pytest.fixture
def engine(monkeypatch):
    for k in ("CHAT_PORTAL_REQUIRE_CERTIFIED", "CHAT_PORTAL_MIN_PROB", "CHAT_PORTAL_MIN_MARGIN", "CHAT_PORTAL_TIMEOUT_MS"):
        monkeypatch.delenv(k, raising=False)
    from semantic_bridge import ads, hr_core, mailbox, risk
    e = open_store("sqlite://").engine
    for mod in (risk, ads, hr_core, mailbox):
        mod._md.create_all(e)
    P._ready.discard(id(e))
    P._cache.clear()

    def at(y, m, d):
        return datetime(y, m, d, 9, 0, tzinfo=UTC)

    def risk_row(rid, tenant, baslik, kategori, durum, puan, sahip, created):
        return dict(id=rid, tenant_id=tenant, baslik=baslik, tanim="ayrıntı metni", kategori=kategori, durum=durum,
                    puan=puan, sahip=sahip, sahip_eposta=f"{sahip}@ornek.com", olusturan=sahip, kaynak="elle",
                    created_at=created, sonraki_gozden_gecirme="2026-10-15", surum=1)

    with e.begin() as c:
        c.execute(risk.RISKS.insert(), [
            risk_row("r1", TN, "Kâğıt tedarik gecikmesi", "operasyonel", "acik", 12, "ayse", at(2026, 9, 10)),
            risk_row("r2", TN, "Döviz kuru", "finansal", "acik", 20, "mehmet", at(2026, 8, 15)),
            risk_row("r3", TN, "Siber saldırı", "bilgi", "izleniyor", 15, "ayse", at(2026, 9, 20)),
            risk_row("r4", TN, "Eski dağıtım riski", "operasyonel", "kapandi", 4, "mehmet", at(2026, 1, 5)),
            risk_row("r9", "t2", "Başka kiracı", "operasyonel", "acik", 25, "zeynep", at(2026, 9, 12)),
        ])
        c.execute(risk.ACTIONS.insert(), [
            dict(id="a1", risk_id="r1", eylem="İkinci matbaa", durum="acik", sahip="ayse", olusturan="ayse", created_at=at(2026, 9, 11)),
            dict(id="a2", risk_id="r1", eylem="Stok artır", durum="tamamlandi", sahip="ayse", olusturan="ayse", created_at=at(2026, 9, 12)),
            dict(id="a3", risk_id="r2", eylem="Vadeli işlem", durum="acik", sahip="mehmet", olusturan="mehmet", created_at=at(2026, 8, 20)),
            dict(id="a4", risk_id="r9", eylem="Başka kiracı", durum="acik", sahip="zeynep", olusturan="zeynep", created_at=at(2026, 9, 13)),
        ])
        c.execute(ads.ACCOUNTS.insert(), [
            dict(id="acc1", tenant_id=TN, platform="meta", account_label="Timaş Meta", currency="TRY", created_by="x", created_at=at(2026, 1, 1)),
            dict(id="acc2", tenant_id=TN, platform="google", account_label="Timaş Google", currency="TRY", created_by="x", created_at=at(2026, 1, 1)),
        ])
        c.execute(ads.CAMPAIGNS.insert(), [
            dict(id="c1", tenant_id=TN, account_id="acc1", name_key="ekim", name="Ekim kampanyası", link_status="yok", created_at=at(2026, 8, 1)),
            dict(id="c2", tenant_id=TN, account_id="acc2", name_key="arama", name="Arama", link_status="yok", created_at=at(2026, 8, 1)),
        ])
        c.execute(ads.DAILY.insert(), [
            dict(campaign_id="c1", day="2026-08-03", spend=100.0, currency="TRY", import_id="i1"),
            dict(campaign_id="c1", day="2026-08-04", spend=50.0, currency="TRY", import_id="i1"),
            dict(campaign_id="c2", day="2026-08-04", spend=70.0, currency="TRY", import_id="i1"),
            dict(campaign_id="c2", day="2026-09-02", spend=999.0, currency="TRY", import_id="i1"),
        ])

        def mail(mid, status, is_hr, received):
            return dict(id=mid, tenant_id=TN, provider="gmail", provider_id=mid, received_at=received, from_addr_hash="h" + mid,
                        from_display="Ali Veli", from_masked="a***@x.com", subject="Siparişim nerede", summary="özet",
                        category="siparis", status=status, assignee="ayse", unit="Müşteri hizmetleri", is_hr=is_hr,
                        historical=False, unsure=False, created_at=received)
        c.execute(mailbox.MESSAGES.insert(), [mail("m1", "yeni", False, at(2026, 9, 27)), mail("m2", "yeni", True, at(2026, 9, 27)),
                                              mail("m3", "kapandi", False, at(2026, 9, 1))])
    return e


def _certified(engine):
    profiles = P.profile(engine, TN)
    P.save_candidates(engine, TN, profiles)
    P.certify(engine, TN, ["all"], "operator:test")
    return {p["table"]: p for p in profiles}


class Picker:
    """Model yerine: istemdeki adımı tanır, istenen seçeneği verilen olasılıkla seçer; her seçeneği kaydeder."""

    def __init__(self, p: float = 0.9, **wanted):
        self.wanted = {"tablo": None, "olcu": P.COUNT, "tarih": None, "kirilim": P.NONE_BREAKDOWN, "kosul": P.NO_MORE}
        self.wanted.update(wanted)
        self.p = p
        self.calls: list[tuple[str, list[str]]] = []

    def _step(self, prompt: str) -> str:
        if "hangi kayıtlardan" in prompt:
            return "tablo"
        if "hangi sayıyı" in prompt:
            return "olcu"
        if "hangi tarihe" in prompt:
            return "tarih"
        if "kırılmalı" in prompt:
            return "kirilim"
        return "kosul"

    def choose(self, prompt, labels, system=None):
        self.calls.append((prompt, list(labels)))
        want = self.wanted[self._step(prompt)]
        pick = next((x for x in labels if x == want), None) or next((x for x in labels if want and want in x), labels[0])
        rest = (1 - self.p) / max(1, len(labels) - 1)
        probs = {x: (self.p if x == pick else rest) for x in labels}
        return Choice(pick, labels.index(pick), probs, "logprobs", self.p - rest)

    def all_options(self) -> list[str]:
        return [o for _, labels in self.calls for o in labels]


RISK = {"id": "risk", "label": "risk ve uyum", "portal": ["risk-uyum"], "data": []}
DIJITAL = {"id": "dijital", "label": "sosyal medya ve dijital reklam", "portal": ["sosyal-medya", "reklam", "isbirlikleri"], "data": []}
DESTEK = {"id": "destek", "label": "müşteri hizmetleri", "portal": ["kurumsal-eposta", "musteri-destek"], "data": []}


def ask(engine, question, topic, picker, access=None):
    return P.answer(engine, TN, question, topic, user=None, llm=picker, today=TODAY, access=access)


# ------------------------------------------------------------------ profil

def test_profile_never_reads_hr_tables_and_excludes_personal_columns(engine):
    profiles = P.profile(engine, TN)
    names = {p["table"] for p in profiles}
    assert not any(n.startswith("semantic_hr_") for n in names)
    assert {"semantic_risk_register", "semantic_risk_actions", "semantic_ads_daily", "semantic_mail_messages"} <= names
    for p in profiles:
        for col, info in p["columns"].items():
            if P.is_person_or_secret(col, info):
                assert info["kind"] == P.EXCLUDED, (p["table"], col)
    reg = next(p for p in profiles if p["table"] == "semantic_risk_register")["columns"]
    assert reg["sahip"]["why"] == "kişisel veri" and reg["sahip_eposta"]["kind"] == P.EXCLUDED
    assert reg["tanim"]["why"] == "serbest metin"
    assert reg["durum"]["kind"] == P.DIMENSION and set(reg["durum"]["values"]) == {"acik", "izleniyor", "kapandi"}
    assert reg["puan"]["kind"] == P.MEASURE
    assert reg["created_at"]["kind"] == P.TIME
    assert reg["sonraki_gozden_gecirme"]["kind"] == P.TIME and reg["sonraki_gozden_gecirme"]["date_text"] == 10
    mail = next(p for p in profiles if p["table"] == "semantic_mail_messages")["columns"]
    for col in ("from_display", "from_masked", "assignee", "suggested_assignee", "subject", "summary"):
        assert mail[col]["kind"] == P.EXCLUDED, col
    assert mail["is_hr"]["kind"] == P.EXCLUDED and mail["is_hr"]["why"] == "alanın sabit süzgeci"


def test_parent_links_are_verified_in_the_data(engine):
    by = {p["table"]: p for p in P.profile(engine, TN)}
    assert by["semantic_risk_actions"]["parents"] == [
        {"column": "risk_id", "table": "semantic_risk_register", "key": "id", "coverage": 1.0}]
    assert [x["table"] for x in by["semantic_ads_daily"]["parents"]] == ["semantic_ads_campaigns"]
    assert [x["table"] for x in by["semantic_ads_campaigns"]["parents"]] == ["semantic_ads_accounts"]
    assert by["semantic_risk_register"]["parents"] == []


# ------------------------------------------------------------------ onay

def test_only_certified_tables_answer(engine):
    P.save_candidates(engine, TN, P.profile(engine, TN))
    out = ask(engine, "Açık risk kaydı sayısı?", RISK, Picker(tablo="risk kaydı"))
    assert out["type"] == "DATA_UNAVAILABLE" and "onaylanmadı" in out["text"]
    P.certify(engine, TN, ["risk-uyum"], "operator:test")
    out = ask(engine, "Açık risk kaydı sayısı?", RISK, Picker(tablo="risk kaydı"))
    assert out["type"] == "TEXT_TO_SQL"


def test_structure_change_keeps_certified_profile_until_recertified(engine):
    _certified(engine)
    with engine.begin() as c:
        c.execute(sa.text("ALTER TABLE semantic_risk_register ADD COLUMN yeni_alan VARCHAR(20)"))
    counts = P.save_candidates(engine, TN, P.profile(engine, TN, only=["risk-uyum"]))
    assert counts["pending"] == 1
    row = next(p for p in P.load(engine, TN) if p["table"] == "semantic_risk_register")
    assert row["status"] == P.CERTIFIED and row["pending"] and "yeni_alan" not in row["columns"]
    P.certify(engine, TN, ["semantic_risk_register"], "operator:test")
    row = next(p for p in P.load(engine, TN) if p["table"] == "semantic_risk_register")
    assert "yeni_alan" in row["columns"] and not row["pending"]


# ------------------------------------------------------------------ cevap

def test_count_with_value_from_question_and_tenant_filter(engine):
    _certified(engine)
    picker = Picker(tablo="risk kaydı")
    out = ask(engine, "Açık risk kaydı sayısı kaç?", RISK, picker)
    assert out["type"] == "TEXT_TO_SQL"
    assert out["records"] == [{P.COUNT: 2}]                     # r1, r2 (başka kiracının r9'u sayılmaz)
    f = out["plan"]["filters"]
    assert f == [{"path": [], "column": "durum", "value": "acik", "negate": False, "label": f[0]["label"], "source": "soru"}]
    assert "2" in out["text"] and "Risk ve uyum" in out["text"]


def test_negated_value_from_question(engine):
    _certified(engine)
    out = ask(engine, "Kapandı olmayan risk kaydı sayısı?", RISK, Picker(tablo="risk kaydı"))
    assert out["records"] == [{P.COUNT: 3}]
    assert out["plan"]["filters"][0]["negate"] is True


def test_group_and_sum_ordered_by_measure(engine):
    _certified(engine)
    out = ask(engine, "Kategori bazında risk puanı toplamı", RISK, Picker(tablo="risk kaydı", olcu="puan toplamı", kirilim="kategori"))
    assert out["records"] == [{"kategori": "finansal", "puan toplamı": 20}, {"kategori": "operasyonel", "puan toplamı": 16},
                              {"kategori": "bilgi", "puan toplamı": 15}]
    assert "En yüksek: finansal (20)" in out["text"]


def test_time_window_on_chosen_date_column(engine):
    _certified(engine)
    picker = Picker(tablo="risk kaydı", tarih="oluşturulma zamanı")
    out = ask(engine, "Bu ay açılan risk kaydı sayısı", RISK, picker)
    assert out["records"] == [{P.COUNT: 2}]                     # r1 (09-10), r3 (09-20)
    assert out["plan"]["window"] == {"start": "2026-09-01", "end": "2026-10-01", "text": "bu ay"}
    assert "2026-09-01 – 2026-09-30" in out["text"]


def test_parent_dimension_and_tenantless_child_filtered_through_parent(engine):
    _certified(engine)
    out = ask(engine, "Kategoriye göre risk aksiyonu sayısı", RISK,
              Picker(tablo="risk aksiyonu", kirilim="risk kaydı › kategori"))
    assert sorted(out["records"], key=lambda r: r["risk kaydı › kategori"]) == [
        {"risk kaydı › kategori": "finansal", P.COUNT: 1}, {"risk kaydı › kategori": "operasyonel", P.COUNT: 2}]


def test_two_step_join_to_grandparent_dimension(engine):
    _certified(engine)
    picker = Picker(tablo="reklam günlük", olcu="harcama toplamı", tarih="gün",
                    kirilim="reklam kampanyası › reklam hesabı (platform) › platform")
    out = ask(engine, "Geçen ay reklam harcaması platform bazında ne kadardı?", DIJITAL, picker)
    assert out["type"] == "TEXT_TO_SQL", out
    got = {r["reklam kampanyası › reklam hesabı (platform) › platform"]: r["harcama toplamı"] for r in out["records"]}
    assert got == {"meta": 150.0, "google": 70.0}              # eylül harcaması (999) geçen aya girmez


def test_hr_messages_are_never_counted(engine):
    _certified(engine)
    picker = Picker(tablo="kurumsal gelen kutusu iletisi")
    out = ask(engine, "Gelen kutusunda kaç ileti var?", DESTEK, picker)
    assert out["records"] == [{P.COUNT: 2}]                     # m2 İK iletisi: hiç sayılmaz
    assert not any("hr" in o.split(":")[0].split() for o in picker.all_options())   # süzgeç kolonu seçenek değil


def test_personal_columns_are_never_offered_nor_returned(engine):
    by = _certified(engine)
    listing = Picker(tablo="risk kaydı", olcu=P.LISTING)
    out = ask(engine, "Açık riskleri listele", RISK, listing)
    assert out["type"] == "TEXT_TO_SQL" and len(out["records"]) == 2
    excluded = {P.humanize(c) for p in by.values() for c, i in p["columns"].items() if i["kind"] == P.EXCLUDED}
    shown = {c["name"] for c in out["columns"]}
    assert not (shown & excluded), shown & excluded
    for r in out["records"]:
        assert "ayse" not in json.dumps(r, ensure_ascii=False) and "@" not in json.dumps(r, ensure_ascii=False)
    grouped = Picker(tablo="kurumsal gelen kutusu iletisi", kirilim="birim")
    out = ask(engine, "Birime göre ileti sayısı", DESTEK, grouped)
    assert out["records"] == [{"birim": "Müşteri hizmetleri", P.COUNT: 2}]
    for opt in listing.all_options() + grouped.all_options():
        low = opt.lower()
        for bad in ("sahip", "olusturan", "eposta", "display", "masked", "assignee", "subject", "summary", "tanim"):
            assert bad not in low, opt


def test_snapshot_table_counts_only_the_latest_day(engine):
    base = {"table": "semantic_okur_inventory", "area": "okur-kitlesi", "label": "okur envanteri", "tenant": "tenant_id",
            "pk": [], "parents": [], "snapshot": "tarih",
            "columns": {"tenant_id": {"type": "str80", "kind": P.TENANT, "label": "tenant id"},
                        "tarih": {"type": "str10", "kind": P.TIME, "label": "tarih", "date_text": 10},
                        "eposta_izinli": {"type": "int", "kind": P.MEASURE, "label": "eposta izinli"}}}
    with engine.begin() as c:
        c.execute(sa.text("CREATE TABLE semantic_okur_inventory (tenant_id VARCHAR(80), tarih VARCHAR(10), eposta_izinli INTEGER)"))
        c.execute(sa.text("INSERT INTO semantic_okur_inventory VALUES ('t1','2026-09-27',100),('t1','2026-09-28',110),('t2','2026-09-29',5)"))
    plan = P.Plan(table=base["table"], area=base["area"], measure=("sum", "eposta_izinli"), measure_label="eposta izinli toplamı")
    stmt, names = P.compile_plan(plan, {base["table"]: base}, TN, None, P.area("okur-kitlesi"))
    rows = P.execute(engine, stmt, 5000)
    assert rows == [{"c0": 110}] and plan.latest == "tarih"


def test_page_permission_is_required(engine):
    _certified(engine)
    nobody = A.Access(user="ali", admin=False, all=False, perms=frozenset({"sayfa:genel-bakis"}))
    out = ask(engine, "Açık risk kaydı sayısı?", RISK, Picker(tablo="risk kaydı"), access=nobody)
    assert out["type"] == "NOT_PERMITTED" and "«Risk ve uyum»" in out["text"]
    assert "records" not in out


def test_row_scope_owner_sees_only_own_rows(engine):
    _certified(engine)
    ayse = A.Access(user="ayse", admin=False, all=False, perms=frozenset({"sayfa:risk-uyum"}))
    picker = Picker(tablo="risk kaydı")
    out = ask(engine, "Açık risk kaydı sayısı?", RISK, picker, access=ayse)
    assert out["records"] == [{P.COUNT: 1}]                     # yalnız r1
    tables = picker.calls[0][1]
    assert "risk gözden geçirmesi" not in tables and "risk göstergesi ölçümü" not in tables   # sahiplik kolonu yok
    all_risks = A.Access(user="ayse", admin=False, all=False, perms=frozenset({"sayfa:risk-uyum", "ozellik:risk.herkesinki"}))
    out = ask(engine, "Açık risk kaydı sayısı?", RISK, Picker(tablo="risk kaydı"), access=all_risks)
    assert out["records"] == [{P.COUNT: 2}]
    admin = A.Access(user="yonetici", admin=True, all=False, perms=frozenset())
    out = ask(engine, "Açık risk kaydı sayısı?", RISK, Picker(tablo="risk kaydı"), access=admin)
    assert out["records"] == [{P.COUNT: 2}]


def test_low_confidence_asks_for_clarification(engine):
    _certified(engine)
    out = ask(engine, "Riskler?", RISK, Picker(tablo="risk kaydı", p=0.3))
    assert out["type"] == "CLARIFICATION" and "hangi kayıtlar" in out["text"]
    assert "records" not in out


def test_without_a_model_the_answer_is_honest(engine):
    _certified(engine)
    out = P.answer(engine, TN, "Açık risk kaydı sayısı?", RISK, user=None, llm=None, today=TODAY, access=None)
    assert out["type"] == "CLARIFICATION" and "records" not in out


_TECH = re.compile(r"qwen|vllm|nvidia|gpt|llama|openai|anthropic|claude|gemini|mistral|temporal|timesfm|llm|\bsql\b",
                   re.IGNORECASE)


def test_texts_carry_no_technology_names(engine):
    _certified(engine)
    nobody = A.Access(user="ali", admin=False, all=False, perms=frozenset())
    outs = [ask(engine, "Açık risk kaydı sayısı?", RISK, Picker(tablo="risk kaydı")),
            ask(engine, "Açık risk kaydı sayısı?", RISK, Picker(tablo="risk kaydı"), access=nobody),
            ask(engine, "Riskler?", RISK, Picker(tablo="risk kaydı", p=0.3)),
            P.answer(engine, TN, "x", RISK, user=None, llm=None, today=TODAY, access=None)]
    for o in outs:
        assert not _TECH.search(o["text"]), o["text"]


def test_bridge_response_shape(engine, monkeypatch):
    _certified(engine)
    logged = {}

    def log_query(**kw):
        logged.update(kw)
        return "q1"

    fake = SimpleNamespace(store=SimpleNamespace(engine=engine), settings=SimpleNamespace(tenant_id=TN),
                           llm_for=lambda module: Picker(tablo="risk kaydı"))
    from semantic_bridge.app import Runtime

    real = P.answer
    monkeypatch.setattr(P, "answer", lambda *a, **kw: real(*a, **{**kw, "today": TODAY, "access": None}))
    scope = chat_scope.Scope(chat_scope.DATA, chat_scope.topic("risk"), True)
    sq = SimpleNamespace(to_dict=lambda: {})
    resp = Runtime._answer_portal(fake, "Açık risk kaydı sayısı?", scope, sq, "th", {}, None, 50, log_query)
    assert resp["type"] == "TEXT_TO_SQL" and resp["records"] == [{P.COUNT: 2}] and resp["totalRows"] == 1
    assert "sql" not in resp                                     # panoya ekle Logo/CRM'e koşar: portal cevabında yok
    assert resp["summary"] and resp["semantic"]["portal"]["plan"]["table"] == "semantic_risk_register"
    assert logged["compiler"] == "portal" and logged["answer_type"] == "TEXT_TO_SQL" and logged["executed"] is True


def test_identity_question_still_gets_the_fixed_intro():
    scope = chat_scope.classify("Hangi modeli kullanıyorsun?")
    assert scope.intent == chat_scope.IDENTITY and scope.reply == chat_scope.BI_INTRO


# ------------------------------------------------------------------ modelsiz okuma

@pytest.mark.parametrize("question, start, end", [
    ("Geçen ay reklam harcaması", date(2026, 8, 1), date(2026, 9, 1)),
    ("Bu ay kaç lansman", date(2026, 9, 1), date(2026, 10, 1)),
    ("Son 30 günde en çok etkileşim", date(2026, 8, 30), date(2026, 9, 29)),
    ("Önümüzdeki 60 günde biten poliçeler", date(2026, 9, 28), date(2026, 11, 27)),
    ("Önümüzdeki iki ayda dolacak", date(2026, 9, 28), date(2026, 11, 28)),
    ("Dün sitede kaç sipariş geldi?", date(2026, 9, 27), date(2026, 9, 28)),
    ("Bugün dolacak kaç ileti var", date(2026, 9, 28), date(2026, 9, 29)),
    ("Geçen hafta gelen iletiler", date(2026, 9, 21), date(2026, 9, 28)),
    ("Bu yıl kaç toplantı", date(2026, 1, 1), date(2027, 1, 1)),
    ("Geçen yıl kaç ihale", date(2025, 1, 1), date(2026, 1, 1)),
    ("Ekim'de yayımlanacak kitaplar", date(2026, 10, 1), date(2026, 11, 1)),
    ("Ağustos 2025 bülten sonuçları", date(2025, 8, 1), date(2025, 9, 1)),
    ("2025'te kaç başvuru geldi", date(2025, 1, 1), date(2026, 1, 1)),
    ("Bu çeyrek kaç olay", date(2026, 7, 1), date(2026, 10, 1)),
    ("Hangi başvurular 30 günden fazladır değerlendirmede?", None, date(2026, 8, 29)),
])
def test_read_window(question, start, end):
    w = P.read_window(question, TODAY)
    assert w is not None and (w.start, w.end) == (start, end), w


@pytest.mark.parametrize("question", ["Aylık plan kalemleri", "Son üç bültenin sonuçları", "Açık risk kaydı sayısı",
                                      "Kategoriye göre işbirliği sayısı"])
def test_no_window_when_none_asked(question):
    assert P.read_window(question, TODAY) is None


@pytest.mark.parametrize("question, n, direction", [
    ("Trendyol'da geçen hafta en çok iade edilen 10 ürün", 10, "desc"),
    ("En çok etkileşim alan paylaşım türü", None, "desc"),
    ("En düşük puanlı 5 kitap", 5, "asc"),
    ("İlk 3 kampanya", 3, "desc"),
    ("Son 3 ayda iade oranı %20'yi geçen", None, None),
    ("Açık risk kaydı sayısı", None, None),
])
def test_read_top(question, n, direction):
    assert P.read_top(question) == (n, direction)


@pytest.mark.parametrize("question, expected", [
    ("Açık risk kaydı sayısı?", True), ("Bu ay kaç lansman kapandı?", True), ("Son bültenin açılma oranı?", True),
    ("Trendyol'da geçen hafta iade", True), ("Hangi başvurular değerlendirmede?", True),
    ("2026 net ciro ne kadar?", False), ("Müşteri iletişim bilgisi", False), ("Bu ay toptan satış tutarı", False),
])
def test_mentions_portal(question, expected):
    assert P.mentions_portal(question) is expected


def test_fold_turkish():
    assert P.fold("KIRMIZI") == "kirmizi" and P.fold("Açık") == "acik" and P.fold("İzleniyor") == "izleniyor"
    assert P.fmt_num(1234567.5) == "1.234.567,50" and P.fmt_num(20) == "20"
