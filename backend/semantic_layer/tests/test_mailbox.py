"""H4 Kurumsal e-posta: iş saatiyle SLA, Gmail cevabının ayrıştırılması, kural sürümü (taslak → onay, iki göz), ileti
kaydı (spam kuralı, geçmiş işareti, tekillik), Zeki AI sonucunun eşiklerle uygulanması, İK gizliliği, tür düzeltmesinin
doğruluk kaydı, başvuru alanlarının metinde doğrulanması, taslakta rakam/söz yasağı, SLA seviyeleri, yanıt tespiti,
doğruluk tablosu, CRM tanıma sorgusu, yetki kuralları.

Veriler yapaydır ve yalnız kuralları sınar; gerçek kutu ve CRM kabulü test sunucusunda (`scripts/acceptance/H4/`,
günlük 2026-09-28 H4). Kutuya ve modele bağlanılmaz.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from semantic_bridge import access as A
from semantic_bridge import mailbox as M
from semantic_bridge import mailbox_classify as K
from semantic_bridge import mailbox_sources as S
from semantic_layer.store.catalog_store import open_store

T = "t1"
ST = M.settings_from(lambda key, default="": M.DEFAULTS.get(key, default))
ALL = {"all": True, "hr": True}
NO_HR = {"all": True, "hr": False}


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    M._ready.discard(id(e))
    M.ensure(e)
    return e


def _item(pid="m1", subject="Konu", text="Merhaba", frm="okur@ornek.com", labels=("INBOX",), at=None, atts=()):
    return S.MailItem(provider_id=pid, thread_id=f"t-{pid}", received_at=at or datetime.now(timezone.utc), from_addr=frm,
                      from_name="Okur Adı", to=["timas@timas.com.tr"], subject=subject, labels=list(labels),
                      attachments=[S.Attachment(name=a, size=1000, mime="application/pdf") for a in atts], text=text)


def _start():
    return datetime.now(timezone.utc) - timedelta(days=1)


class _Choice:
    def __init__(self, labels, pick, p, margin, method="logprobs"):
        self.index = labels.index(pick) if pick in labels else None
        self.choice = pick if pick in labels else None
        self.probability, self.margin, self.method = p, margin, method

    def confident(self, min_prob, min_margin=0.0, min_coverage=0.0):
        return self.probability is not None and self.probability >= min_prob and (self.margin or 0) >= min_margin

    def as_dict(self):
        return {"method": self.method, "probs": None, "coverage": 1.0, "calls": 1, "error": None}


class _Llm:
    """Sahte kapı istemcisi: tür için verilen etiketi, öncelik için «Normal»i seçer; sohbette verilen metni döner."""

    def __init__(self, pick, p=0.95, margin=0.8, text=""):
        self.pick, self.p, self.margin, self.text = pick, p, margin, text

    def choose(self, prompt, labels, system=None):
        pick = self.pick if self.pick in labels else "Normal"
        return _Choice(labels, pick, self.p, self.margin)

    def chat(self, messages, **kw):
        return self.text


# ------------------------------------------------------------------ iş saatleri


def test_business_hours_skip_nights_weekends_and_holidays():
    cal = M.parse_calendar("1-5 09:00-18:00", "2026-10-29")
    fri = datetime(2026, 9, 25, 17, 0, tzinfo=M.TZ)                       # cuma 17:00
    due = M.add_business_hours(fri, 2, cal).astimezone(M.TZ)
    assert (due.weekday(), due.hour) == (0, 10)                           # pazartesi 10:00
    assert M.business_hours_between(fri, due, cal) == pytest.approx(2)
    wed = datetime(2026, 10, 28, 17, 0, tzinfo=M.TZ)                      # 29 Ekim tatil
    assert M.add_business_hours(wed, 2, cal).astimezone(M.TZ).date().isoformat() == "2026-10-30"
    assert M.parse_calendar("bozuk", "")["days"][1] == (540, 1080)          # bozuk ayar → pzt–cum 09–18


# ------------------------------------------------------------------ Gmail ayrıştırma


def _b64(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")


def test_parse_gmail_prefers_plain_text_lists_attachments_and_never_needs_send_scope():
    msg = {"id": "abc", "threadId": "th", "internalDate": "1790000000000", "labelIds": ["INBOX", "CATEGORY_PERSONAL"],
           "payload": {"headers": [{"name": "From", "value": "Ayşe Yazar <Ayse@Ornek.com>"}, {"name": "Subject", "value": "Dosya"},
                                   {"name": "To", "value": "timas@timas.com.tr"}],
                       "parts": [{"mimeType": "text/html", "body": {"data": _b64("<p>HTML</p>")}},
                                 {"mimeType": "text/plain", "body": {"data": _b64("Düz metin")}},
                                 {"mimeType": "application/pdf", "filename": "roman.pdf", "body": {"size": 2048, "attachmentId": "A1"}}]}}
    it = S.parse_gmail(msg)
    assert (it.from_addr, it.from_name, it.subject, it.text) == ("ayse@ornek.com", "Ayşe Yazar", "Dosya", "Düz metin")
    assert [a.public() for a in it.attachments] == [{"name": "roman.pdf", "size": 2048, "mime": "application/pdf"}]
    assert it.attachments[0].ref == "A1"
    assert S.html_to_text("<div>a<br>b</div><script>x</script>") == "a\nb"
    assert set(S.GMAIL_SCOPES) == {"https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.labels"}
    assert not any(hasattr(S.GmailSource, n) for n in ("send", "delete", "modify", "trash"))


def test_connection_state_says_why_the_box_is_not_connected():
    conf = lambda k, d="": {"MAIL_PROVIDER": "gmail", "MAIL_ADDRESS": "timas@timas.com.tr"}.get(k, d)  # noqa: E731
    S._GMAIL.clear()
    st = S.connection_state(conf)
    assert st["connected"] is False and "anahtar" in st["reason"].lower()
    st = S.connection_state(lambda k, d="": {"MAIL_PROVIDER": "graph"}.get(k, d))
    assert st["connected"] is False and "kurulmadı" in st["reason"]
    S._GMAIL.clear()


# ------------------------------------------------------------------ kurallar


def test_seed_is_active_and_draft_needs_another_approver(engine):
    active = M.active_rules(engine, T, ST)
    assert active["version"] == 1 and {c["role"] for c in active["categories"]} >= {"basvuru", "ik", "spam"}
    body = {"categories": [{"key": "sikayet", "label": "Şikâyet", "enabled": True},
                           {"key": "is-basvurusu", "label": "İş başvurusu", "role": "ik", "enabled": True}],
            "routes": [{"category": "sikayet", "unit": "Müşteri hizmetleri", "primary": "ayse", "manager": "mehmet"}],
            "sla": [{"category": "sikayet", "remindH": 8, "escalateH": 16, "topH": 24}]}
    d = M.save_draft(engine, T, "ayse", body, ST)
    assert d["status"] == "taslak" and d["version"] == 2
    assert M.active_rules(engine, T, ST)["version"] == 1                   # taslak yürürlüğü değiştirmez
    with pytest.raises(M.MailError) as e:
        M.approve_draft(engine, T, "ayse", 2)
    assert e.value.status == 403
    M.approve_draft(engine, T, "zeynep", 2)
    act = M.active_rules(engine, T, ST)
    assert act["version"] == 2 and act["routes"][0]["primary"] == "ayse"
    assert M.user_units(act, "mehmet") == {"Müşteri hizmetleri"}


@pytest.mark.parametrize("body,msg", [
    ({"categories": []}, "En az bir tür"),
    ({"categories": [{"key": "A B", "label": "x"}]}, "anahtarı"),
    ({"categories": [{"key": "ab", "label": "X"}, {"key": "cd", "label": "x"}]}, "iki türde"),
    ({"categories": [{"key": "ab", "label": "X"}], "sla": [{"category": "ab", "remindH": 48, "escalateH": 24, "topH": 72}]}, "hatırlatma ≤"),
    ({"categories": [{"key": "ab", "label": "X"}], "routes": [{"category": "zz"}]}, "bilinmeyen tür"),
    ({"categories": [{"key": "ab", "label": "X"}], "routes": [{"category": "ab", "primary": "Ali Veli"}]}, "hesap adı"),
])
def test_rules_validation(engine, body, msg):
    with pytest.raises(M.MailError) as e:
        M.save_draft(engine, T, "ayse", body, ST)
    assert msg in str(e.value)


# ------------------------------------------------------------------ kayıt ve sınıflama


def test_ingest_spam_rule_historical_and_duplicates(engine):
    rules = M.active_rules(engine, T, ST)
    start = _start()
    spam = M.ingest(engine, T, "gmail", _item("s1", labels=("SPAM",)), {}, rules, ST, start)
    old = M.ingest(engine, T, "gmail", _item("o1", at=start - timedelta(days=3)), {}, rules, ST, start)
    assert M.ingest(engine, T, "gmail", _item("s1"), {}, rules, ST, start) is None      # aynı sağlayıcı kimliği
    with engine.connect() as c:
        s = c.execute(M.MESSAGES.select().where(M.MESSAGES.c.id == spam)).first()
        o = c.execute(M.MESSAGES.select().where(M.MESSAGES.c.id == old)).first()
    assert (s.status, s.category, s.category_source) == ("arsiv", "tanitim", "kural")
    assert o.historical and o.due_at is None
    assert s.from_masked == "o***@ornek.com" and len(s.from_addr_hash) == 64
    cols = {c.name for c in M.MESSAGES.columns}
    assert not {"body", "text", "from_addr"} & cols                        # gövde ve açık adres saklanmaz


def test_classification_thresholds_spam_autoarchive_and_no_auto_assign_by_default(engine):
    rules = M.active_rules(engine, T, ST)
    enabled = [c for c in rules["categories"] if c["enabled"]]
    start = _start()
    a = M.ingest(engine, T, "gmail", _item("a"), {}, rules, ST, start)
    res = K.classify(_Llm("Tanıtım / reklam / spam"), _item("a"), enabled, {}, ST)
    assert res["category"] == "tanitim" and res["auto"] and not res["unsure"]
    M.apply_classification(engine, T, a, res, rules, ST, None, None, [])
    b = M.ingest(engine, T, "gmail", _item("b"), {}, rules, ST, start)
    res = K.classify(_Llm("Şikâyet", p=0.55, margin=0.1), _item("b"), enabled, {}, ST)
    assert res["unsure"] and res["category"] == "sikayet"
    M.apply_classification(engine, T, b, res, rules, ST, "Özet.", None, [])
    with engine.connect() as c:
        ra = c.execute(M.MESSAGES.select().where(M.MESSAGES.c.id == a)).first()
        rb = c.execute(M.MESSAGES.select().where(M.MESSAGES.c.id == b)).first()
    assert ra.status == "arsiv"
    assert rb.status == "yeni" and rb.unsure and rb.assignee is None and rb.model_category == "sikayet"
    lst = M.listing(engine, T, "biri", ALL, ST, view="unsure")
    assert [x["id"] for x in lst["items"]] == [b]


def test_auto_assign_only_for_opened_categories_above_auto_threshold(engine):
    M.save_draft(engine, T, "ayse", {"categories": [{"key": "sikayet", "label": "Şikâyet"}],
                                     "routes": [{"category": "sikayet", "unit": "MH", "primary": "ayse"}]}, ST)
    M.approve_draft(engine, T, "zeynep", 2)
    rules = M.active_rules(engine, T, ST)
    st = {**ST, "autoAssign": {"sikayet"}}
    mid = M.ingest(engine, T, "gmail", _item("c"), {}, rules, st, _start())
    res = K.classify(_Llm("Şikâyet"), _item("c"), rules["categories"], {}, st)
    M.apply_classification(engine, T, mid, res, rules, st, None, None, [])
    d = M.detail(engine, T, "ayse", {"all": False, "hr": False}, st, mid)
    assert (d["status"], d["assignee"], d["unit"]) == ("atandi", "ayse", "MH")
    assert any(e["action"] == "atandi" and e["by"] == "zeki" for e in d["events"])


def test_application_is_created_for_submission_category(engine):
    rules = M.active_rules(engine, T, ST)
    it = _item("d", subject="Roman dosyam: Kayıp Şehir", text="Merhaba, ben Ali Veli. 240 sayfalık romanım ektedir.",
               atts=("kayip-sehir.pdf",))
    mid = M.ingest(engine, T, "gmail", it, {}, rules, ST, _start())
    llm = _Llm("Dosya başvurusu", text='{"yazar": "Ali Veli", "eser": "Kayıp Şehir", "tur": "polisiye", "sayfa": "240"}')
    app = K.extract_application(llm, it, ST)
    assert (app["author_name"], app["work_title"], app["genre"], app["page_estimate"]) == ("Ali Veli", "Kayıp Şehir", None, 240)
    assert app["dropped"] == ["tur"]                                       # metinde «polisiye» yok → düşer
    res = K.classify(llm, it, rules["categories"], {}, ST)
    M.apply_classification(engine, T, mid, res, rules, ST, None, app, [a.public() for a in it.attachments])
    items = M.applications(engine, T, "yeni")["items"]
    assert len(items) == 1 and items[0]["workTitle"] == "Kayıp Şehir" and items[0]["attachments"][0]["name"] == "kayip-sehir.pdf"


# ------------------------------------------------------------------ İK gizliliği, atama, düzeltme


def _hr_message(engine):
    rules = M.active_rules(engine, T, ST)
    mid = M.ingest(engine, T, "gmail", _item("h", subject="Özgeçmişim"), {}, rules, ST, _start())
    M.apply_classification(engine, T, mid, K.classify(_Llm("İş başvurusu"), _item("h"), rules["categories"], {}, ST),
                           rules, ST, "İş başvurusu.", None, [])
    return mid


def test_hr_messages_are_hidden_without_explicit_right_even_for_see_all(engine):
    mid = _hr_message(engine)
    assert M.listing(engine, T, "yonetici", NO_HR, ST, view="unassigned")["total"] == 0
    assert M.listing(engine, T, "ik", ALL, ST, view="unassigned")["total"] == 1
    with pytest.raises(M.MailError) as e:
        M.detail(engine, T, "yonetici", NO_HR, ST, mid)
    assert e.value.status == 403
    with pytest.raises(M.MailError) as e:
        M.assign(engine, T, "ik", ALL, ST, mid, {"assignee": "satisci"}, lambda who: who == "ik2")
    assert e.value.status == 409
    out = M.assign(engine, T, "ik", ALL, ST, mid, {"assignee": "ik2"}, lambda who: who == "ik2")
    assert out["status"] == "atandi"
    assert M.badge(engine, T, "ik2", ST, hr=False) == {"mine": 0, "overdue": 0}
    assert M.badge(engine, T, "ik2", ST, hr=True)["mine"] == 1


def test_category_fix_is_recorded_and_model_choice_is_kept(engine):
    rules = M.active_rules(engine, T, ST)
    mid = M.ingest(engine, T, "gmail", _item("f"), {}, rules, ST, _start())
    M.apply_classification(engine, T, mid, K.classify(_Llm("Soru / bilgi talebi"), _item("f"), rules["categories"], {}, ST),
                           rules, ST, None, None, [])
    M.set_category(engine, T, "ayse", ALL, ST, mid, "sikayet")
    d = M.detail(engine, T, "ayse", ALL, ST, mid)
    assert d["category"] == "sikayet" and d["categorySource"] == "insan" and not d["unsure"]
    ev = [e for e in d["events"] if e["action"] == "tur-duzeltildi"][0]
    assert ev["detail"]["model"] == "soru" and ev["detail"]["yeni"] == "sikayet"


def test_status_transitions(engine):
    rules = M.active_rules(engine, T, ST)
    mid = M.ingest(engine, T, "gmail", _item("g"), {}, rules, ST, _start())
    with pytest.raises(M.MailError):
        M.set_status(engine, T, "ayse", ALL, ST, mid, "atandi")            # atanmamışken
    M.set_status(engine, T, "ayse", ALL, ST, mid, "arsiv")
    M.set_status(engine, T, "ayse", ALL, ST, mid, "yeni")                  # arşivden geri al
    out = M.set_status(engine, T, "ayse", ALL, ST, mid, "yanitlandi")
    assert out["status"] == "yanitlandi"
    assert M.detail(engine, T, "ayse", ALL, ST, mid)["firstReplyAt"] is not None


def test_scope_without_see_all_is_own_and_unit(engine):
    M.save_draft(engine, T, "ayse", {"categories": [{"key": "sikayet", "label": "Şikâyet"}],
                                     "routes": [{"category": "sikayet", "unit": "MH", "primary": "ayse", "backup": "can"}]}, ST)
    M.approve_draft(engine, T, "zeynep", 2)
    rules = M.active_rules(engine, T, ST)
    mid = M.ingest(engine, T, "gmail", _item("u"), {}, rules, ST, _start())
    M.assign(engine, T, "zeynep", ALL, ST, mid, {"assignee": "ayse"}, lambda w: False)
    own = {"all": False, "hr": False}
    assert M.listing(engine, T, "can", own, ST, view="unit")["total"] == 1
    assert M.listing(engine, T, "baskasi", own, ST, view="unit")["total"] == 0
    with pytest.raises(M.MailError):
        M.detail(engine, T, "baskasi", own, ST, mid)


# ------------------------------------------------------------------ SLA ve yanıt


def test_sla_levels_once_each_and_replied_messages_are_left_alone(engine):
    rules = M.active_rules(engine, T, ST)
    st = {**ST, "calendar": M.parse_calendar("1-7 00:00-24:00", ""), "inboxOwners": ["kutu"], "topManagers": ["gm"]}
    old = datetime.now(timezone.utc) - timedelta(hours=50)
    mid = M.ingest(engine, T, "gmail", _item("sla", at=old), {}, rules, st, old - timedelta(days=1))
    rep = M.ingest(engine, T, "gmail", _item("rep", at=old), {}, rules, st, old - timedelta(days=1))
    assert M.record_reply(engine, T, rep, old + timedelta(hours=1)) is True
    due = M.sla_due(engine, T, st)
    assert [(x["id"], x["level"], x["users"]) for x in due] == [(mid, "eskalasyon", ["kutu"])]
    M.mark_sla(engine, T, mid, "eskalasyon", {})
    assert M.sla_due(engine, T, st) == []                                  # hatırlatma da gönderilmiş sayılır
    later = datetime.now(timezone.utc) + timedelta(hours=30)
    assert [x["level"] for x in M.sla_due(engine, T, st, later)] == ["ust"]
    d = M.detail(engine, T, "x", ALL, st, rep)
    assert d["status"] == "yanitlandi" and any(e["action"] == "yanitlandi" and e["by"] == "kutu" for e in d["events"])


def test_report_counts_sla_from_first_reply(engine):
    rules = M.active_rules(engine, T, ST)
    st = {**ST, "calendar": M.parse_calendar("1-7 00:00-24:00", "")}
    t0 = datetime.now(timezone.utc) - timedelta(days=2)
    a = M.ingest(engine, T, "gmail", _item("r1", at=t0), {}, rules, st, t0 - timedelta(days=1))
    b = M.ingest(engine, T, "gmail", _item("r2", at=t0), {}, rules, st, t0 - timedelta(days=1))
    M.record_reply(engine, T, a, t0 + timedelta(hours=2))
    M.record_reply(engine, T, b, t0 + timedelta(hours=30))
    r = M.report(engine, T, st, (t0 - timedelta(days=1)).date(), datetime.now(timezone.utc).date())
    assert r["total"] == 2 and r["replied"] == 2 and r["slaRate"] == 0.5


# ------------------------------------------------------------------ Zeki AI metinleri


def test_draft_keeps_only_template_numbers_and_summary_drops_digits():
    it = _item(text="Siparişim 12345 gelmedi.")
    llm = _Llm("x", text="Merhaba,\nSiparişinizi 3 gün içinde göndereceğiz.\nİlgili birimimiz size dönüş yapacaktır.\n14 gün içinde iade edebilirsiniz.")
    out = K.draft_reply(llm, it, "Şikâyet", "İade süresi 14 gündür.", ST)
    assert "3 gün" not in out and "14 gün" in out and "dönüş" in out
    assert K.summarize(_Llm("x", text="Özet: Okur siparişini soruyor. Sipariş no 12345."), it, ST) == "Okur siparişini soruyor."
    assert K.order_refs("Sipariş no: TMS-12345 ve order #AB12C3", "", M.DEFAULTS["MAIL_ORDER_PATTERN"]) == ["TMS-12345", "AB12C3"]


def test_choose_without_probabilities_is_never_confident():
    plain = SimpleNamespace(chat=lambda messages, **kw: "Şikâyet")
    r = K.choose(plain, "?", ["Soru", "Şikâyet"], ST["thresholds"])
    assert r["index"] == 1 and r["yontem"] == "text" and not r["oneri"] and not r["otomatik"]


# ------------------------------------------------------------------ etiketleme


def test_accuracy_uses_majority_label_against_first_model_choice(engine):
    rules = M.active_rules(engine, T, ST)
    ids = []
    for i, pick in enumerate(["Şikâyet", "Soru / bilgi talebi"]):
        mid = M.ingest(engine, T, "gmail", _item(f"l{i}"), {}, rules, ST, _start())
        M.apply_classification(engine, T, mid, K.classify(_Llm(pick), _item(f"l{i}"), rules["categories"], {}, ST),
                               rules, ST, None, None, [])
        ids.append(mid)
    M.add_label(engine, T, "a", ALL, ST, ids[0], "sikayet")
    M.add_label(engine, T, "a", ALL, ST, ids[1], "sikayet")
    M.add_label(engine, T, "b", ALL, ST, ids[1], "sikayet")
    acc = M.accuracy(engine, T)
    assert (acc["n"], acc["agree"], acc["rate"]) == (2, 1, 0.5)
    assert acc["confusion"][0]["n"] >= 1
    assert M.labeling(engine, T, "a", ALL, ST)["total"] == 0


# ------------------------------------------------------------------ CRM ve yetki


def test_recognize_sql_is_read_only_and_escapes_addresses():
    sql = S.recognize_sql("Timas_MSCRM.dbo.", ["o'neil@ornek.com"])
    assert "N'o''neil@ornek.com'" in sql and "StateCode = 0" in sql
    assert not any(w in sql.upper() for w in ("INSERT", "UPDATE", "DELETE", "MERGE"))
    rows = [{"tur": "kisi", "adres": "a@b.co", "id": "{2}", "ad": "B", "proje": 1},
            {"tur": "kisi", "adres": "a@b.co", "id": "{1}", "ad": "A", "proje": 0}]
    out = S.recognize(lambda sql: rows, "x.", ["A@B.co", "bozuk"])
    assert out["a@b.co"]["kisi"]["id"] == "1" and out["a@b.co"]["kisi"]["coklu"]


def test_access_rules_for_mailbox_endpoints():
    assert A.rule_for("/api/v1/mailbox/run-due") == A.SYSTEM
    assert A.rule_for("/api/v1/mailbox/sla-due") == A.SYSTEM
    assert A.rule_for("/api/v1/mailbox/messages") == frozenset({"sayfa:kurumsal-eposta"})
    assert "sayfa:yazar-giris" in A.rule_for("/api/v1/mailbox/applications")
    f = A.features_for
    assert f("POST", "/api/v1/mailbox/messages/x/assign") == ["ozellik:eposta.ata"]
    assert f("POST", "/api/v1/mailbox/messages/x/to-intake") == ["ozellik:eposta.ata"]
    assert f("POST", "/api/v1/mailbox/messages/x/draft") == []
    assert f("POST", "/api/v1/mailbox/messages/x/to-hr") == []              # açıkça verilen, ucun içinde
    assert f("PUT", "/api/v1/mailbox/rules") == ["ozellik:eposta.kural"]
    assert f("POST", "/api/v1/mailbox/rules/approve") == []
    assert {"ozellik:eposta.ik", "ozellik:eposta.kural-onay"} <= A.explicit_keys()
    cat = json.loads(A.CATALOG_FILE.read_text(encoding="utf-8"))
    assert any(p["key"] == "sayfa:kurumsal-eposta" and p["area"] == "kayitlar" for p in cat["pages"])
