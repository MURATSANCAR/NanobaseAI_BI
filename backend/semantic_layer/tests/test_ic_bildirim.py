"""Bilgi İşlem'e giden beş bildirimin ortak şablonu (ic_bildirim) ve kopma bildiriminin gürültü önlemesi.

Sınananlar: her bildirimin HTML'i ve düz metni üretilir; konu durumla başlar; «Ne oldu / Etkisi / Ne yapmalı»,
bağlantı ve alt not var; teknoloji adı yok; ileti `multipart/alternative` (ekliyse `multipart/mixed`); departmansız
CRM listesinde yalnız ad, kullanıcı adı ve oluşturulma tarihi. Gürültü: kısa kesinti ve köprünün planlı yeniden
başlatması olay açmaz, e-posta göndermez; uzun kesintide tek kopma ve tek düzelme e-postası gider.

Veriler yapaydır ve yalnız kuralları sınar; gerçek tablolarla kabul `scripts/acceptance/bt-eposta/kabul.py`.
"""

from __future__ import annotations

import email
import io
import re
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa

from semantic_bridge import crm_unassigned as CU
from semantic_bridge import data_security as D
from semantic_bridge import ic_bildirim as IB
from semantic_bridge import it_ops as I
from semantic_bridge import mailbox as M
from semantic_layer.store.catalog_store import open_store
from semantic_layer.tests.conftest import TENANT

UTC = timezone.utc
LOCAL = timezone(timedelta(hours=3))
T0 = datetime(2026, 9, 29, 6, 42, tzinfo=UTC)          # 09:42 İstanbul
LINK = "https://portal.timas.com.tr/timas/uyarilar"
BT = ["bilgiislem@timas.com.tr"]
ST = {"everySec": 300, "failsToOpen": 2, "outageMin": 10, "restartGraceMin": 5, "logoStaleDays": 3, "crmStaleHours": 24,
      "remindHours": 0, "staleRemindHours": 0, "weeklyDay": 1, "reportHour": 8}
DIRTY = "OperationalError: FreeTDS pyodbc; uvicorn systemd nginx; vLLM Qwen3.8-27B; Temporal PostgreSQL docker"


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    I._ready.discard(id(e))
    I.ensure(e)
    return e


class Outbox:
    def __init__(self, result: str = "sent"):
        self.result = result
        self.notices: list[IB.Notice] = []

    def __call__(self, notice, to):
        self.notices.append(notice)
        return self.result


def tour(engine, ring, ok, at, st=ST, detail="zaman aşımı"):
    I.record_check(engine, TENANT, ring, ok, detail=detail, at=at)
    return I.evaluate(engine, TENANT, [{"ring": ring, "ok": ok, "detail": detail}], st, now=at)


def assert_template(n: IB.Notice, tag: str, link_part: str) -> tuple[str, str]:
    """Her bildirimin ortak sözleşmesi."""
    html, text = IB.render_html(n), IB.render_text(n)
    assert n.subject.startswith(f"[{tag}] "), n.subject
    assert len(n.subject) <= 200 and n.headline
    for title in ("Ne oldu", "Etkisi", "Ne yapmalı"):
        assert f">{title}</p>" in html, title
    for title in ("NE OLDU", "ETKİSİ", "NE YAPMALI"):
        assert title in text, title
    assert IB.FOOTER in html and IB.FOOTER in text
    assert link_part in n.link and n.link in text and f'href="{n.link}"' in html
    assert "max-width:640px" in html and "<link" not in html and 'lang="tr"' in html
    assert IB.tech_words(html) == [] and IB.tech_words(text) == [], (IB.tech_words(html), IB.tech_words(text))
    assert re.search(r"(parola|password|şifre|anahtar)\w*\s*[:=]", text, re.I) is None   # değer yazılmaz
    return html, text


# ------------------------------------------------------------------ şablon


def test_turkish_suffixes_and_dates():
    at = lambda h, m: datetime(2026, 9, 29, h, m, tzinfo=LOCAL)  # noqa: E731
    assert IB.hm_suffix(at(9, 42)) == "09:42'den" and IB.hm_suffix(at(10, 40)) == "10:40'tan"
    assert IB.hm_suffix(at(9, 43)) == "09:43'ten" and IB.hm_suffix(at(9, 36)) == "09:36'dan"
    assert IB.hm_suffix(at(12, 0), "de") == "12:00'de" and IB.hm_suffix(at(10, 27), "de") == "10:27'de"
    assert IB.hm_suffix(at(9, 30), "de") == "09:30'da" and IB.hm_suffix(at(10, 0)) == "10:00'dan"
    assert IB.suffix("Ağustos") == "tan" and IB.suffix("Eylül") == "den"
    assert IB.day_range(datetime(2026, 9, 22, 8, tzinfo=LOCAL), datetime(2026, 9, 28, 8, tzinfo=LOCAL)) == "22–28 Eylül"
    assert IB.day_range(datetime(2026, 9, 29, tzinfo=LOCAL), datetime(2026, 10, 5, tzinfo=LOCAL)) == "29 Eylül – 5 Ekim"
    assert IB.portal_link(LINK, "sistem-durumu") == "https://portal.timas.com.tr/timas/sistem-durumu"
    assert IB.portal_link("", "sistem-durumu") == ""


def test_plain_removes_technology_and_error_class_names():
    t = IB.plain(DIRTY)
    assert IB.tech_words(t) == [] and "OperationalError" not in t
    assert "Zeki AI modeli" in t and "veritabanı" in t
    assert IB.plain("smtp.gmail.com:587 reddetti") == "smtp.gmail.com:587 reddetti"   # sunucu adı bozulmaz


def test_message_is_multipart_alternative_and_mixed_with_attachment():
    n = IB.Notice(tone="bilgi", subject=IB.subject("Bilgi", "deneme"), headline="Tek cümle.", what=["a"], impact=["b"],
                  actions=["c"], link="https://x/timas/yonetim", at=T0)
    msg = email.message_from_bytes(IB.message(n, "zeki@timas.com.tr", BT).as_bytes())
    assert msg.get_content_type() == "multipart/alternative"
    assert [p.get_content_type() for p in msg.get_payload()] == ["text/plain", "text/html"]
    msg = email.message_from_bytes(IB.message(n, "zeki@timas.com.tr", BT, [("a.xlsx", b"x", CU.XLSX_MIME)]).as_bytes())
    assert msg.get_content_type() == "multipart/mixed"
    parts = [p.get_content_type() for p in msg.walk()]
    assert "multipart/alternative" in parts and CU.XLSX_MIME in parts


def test_html_is_escaped():
    n = IB.Notice(tone="kesinti", subject="[Kesinti] x", headline="<script>alert(1)</script>", what=["<b>"], at=T0)
    html = IB.render_html(n)
    assert "<script>" not in html and "&lt;script&gt;" in html


# ------------------------------------------------------------------ 1) kopma ve düzelme — gürültü önleme


def test_short_outage_sends_nothing(engine):
    out = Outbox()
    tour(engine, "logo", False, T0)
    tour(engine, "logo", False, T0 + timedelta(minutes=5))           # iki deneme ama 5 dk < 10 dk
    assert not I.list_incidents(engine, TENANT)["items"]
    tour(engine, "logo", True, T0 + timedelta(minutes=8))
    I.notify(engine, TENANT, ST, out, BT, link=LINK, now=T0 + timedelta(minutes=8))
    assert out.notices == [] and not I.list_incidents(engine, TENANT, state="all")["items"]


def test_planned_restart_is_not_an_outage(engine):
    out = Outbox()
    boot = T0 + timedelta(minutes=6)
    assert I.note_boot(engine, TENANT, boot) and not I.note_boot(engine, TENANT, boot)   # süreç başına bir kez
    # Durma (açılıştan önce) ve açılış (sonra) sırasındaki başarısız denemeler sayılmaz.
    for m in (4, 8, 10):
        tour(engine, "model", False, T0 + timedelta(minutes=m), detail="kapı durdu")
    I.notify(engine, TENANT, ST, out, BT, link=LINK, now=T0 + timedelta(minutes=10))
    assert out.notices == [] and not I.list_incidents(engine, TENANT, state="all")["items"]
    assert I.in_restart_window(T0 + timedelta(minutes=2), [boot], 5) and not I.in_restart_window(T0, [boot], 5)
    # Açılış kaydı yalnız son BOOT_KEEP_DAYS günü tutar.
    I.note_boot(engine, TENANT, boot + timedelta(days=I.BOOT_KEEP_DAYS + 1))
    assert I.boots(engine, TENANT) == [boot + timedelta(days=I.BOOT_KEEP_DAYS + 1)]


def test_long_outage_sends_one_down_and_one_fixed(engine):
    out = Outbox()
    for m in (0, 5, 10, 15, 20, 25):
        tour(engine, "logo", False, T0 + timedelta(minutes=m), detail=DIRTY)
        I.notify(engine, TENANT, ST, out, BT, link=LINK, now=T0 + timedelta(minutes=m))
    assert len(out.notices) == 1                                    # açıldı (10. dk), sonra ikinci e-posta yok
    down = out.notices[0]
    assert down.subject == "[Kesinti] Logo bağlantısı 09:42'den beri yanıt vermiyor"
    html, text = assert_template(down, "Kesinti", "/timas/sistem-durumu")
    assert "Satış, ciro" in text and "3 kez art arda" in text     # etkisi ve 10. dk'ya dek deneme sayısı
    tour(engine, "logo", True, T0 + timedelta(minutes=45))
    I.notify(engine, TENANT, ST, out, BT, link=LINK, now=T0 + timedelta(minutes=45))
    I.notify(engine, TENANT, ST, out, BT, link=LINK, now=T0 + timedelta(minutes=50))
    assert len(out.notices) == 2
    fixed = out.notices[1]
    assert fixed.subject == "[Düzeldi] Logo bağlantısı 10:27'de geri geldi · 45 dk sürdü" and fixed.tone == "duzeldi"
    assert_template(fixed, "Düzeldi", "/timas/sistem-durumu")
    assert IB.TONES["duzeldi"]["bar"] in IB.render_html(fixed) and IB.TONES["kesinti"]["bar"] in html


def test_stale_data_notice_says_since_when(engine):
    end = datetime(2026, 8, 17, 18, 0, tzinfo=UTC)
    I.record_check(engine, TENANT, "logo", True, data_end=end, at=T0)
    I.evaluate(engine, TENANT, [{"ring": "logo", "ok": True, "data_end": end}], ST, now=T0)
    out = Outbox()
    I.notify(engine, TENANT, ST, out, BT, link=LINK, now=T0)
    n = out.notices[0]
    assert n.subject == "[Uyarı] Logo verisi 17 Ağustos'tan beri güncellenmiyor" and n.tone == "uyari"
    assert_template(n, "Uyarı", "/timas/sistem-durumu")
    I.notify(engine, TENANT, ST, out, BT, link=LINK, now=T0 + timedelta(days=3))
    assert len(out.notices) == 1                                   # hatırlatma varsayılanda kapalı


def test_jobs_digest_uses_the_template():
    n = I.jobs_digest_notice([{"label": "Planlı raporlar", "lastAt": T0.isoformat(), "lastError": DIRTY, "every": "5 dk"}],
                             T0, LINK)
    assert n.subject == "[Uyarı] Zamanlanmış işler · 1 iş hata verdi · 29 Eylül"
    assert_template(n, "Uyarı", "/timas/sistem-durumu")


# ------------------------------------------------------------------ 2) haftalık sağlık özeti


def test_weekly_notice(engine):
    for m in (0, 5, 10):
        tour(engine, "vpn", False, T0 - timedelta(days=2) + timedelta(minutes=m))
    tour(engine, "vpn", True, T0 - timedelta(days=2) + timedelta(minutes=40))
    now = datetime(2026, 9, 29, 5, 0, tzinfo=UTC)                   # 08:00 İstanbul; pencere 22–28 Eylül
    n = I.weekly_notice(engine, TENANT, now, [], LINK)
    assert n.subject == "[Haftalık] Sistem sağlığı · 22–28 Eylül" and n.tone == "bilgi"
    html, text = assert_template(n, "Haftalık", "/timas/sistem-durumu")
    assert "Şirket ağı bağlantısı · 1 · 40 dk" in text and "toplam kesinti 40 dk" in n.headline
    quiet = I.weekly_notice(engine, TENANT, now + timedelta(days=14), [], LINK)
    assert "kesintisiz" in quiet.headline


# ------------------------------------------------------------------ 3) güvenlik


def test_security_alert_and_digest_notices():
    a = {"id": 1, "rule": "hatali_giris", "username": "ahmet", "severity": "kritik",
         "summary": "«ahmet» hesabına 7 hatalı giriş denendi; kaynak adres: 10.0.4.27."}
    n = D.alert_notice([a], IB.portal_link(LINK, "veri-guvenligi"), T0)
    assert n.subject == "[Güvenlik] Art arda hatalı giriş · «ahmet» hesabı · 29 Eylül 09:42" and n.tone == "guvenlik"
    assert_template(n, "Güvenlik", "/timas/veri-guvenligi")
    two = D.alert_notice([a, dict(a, id=2, rule="yeni_yonetici", username="ayse", summary="«ayse» yönetici oldu.")],
                         IB.portal_link(LINK, "veri-guvenligi"), T0)
    assert two.subject.startswith("[Güvenlik] 2 yeni güvenlik uyarısı") and len(two.impact) == 2
    d = D.digest_notice_from({"ayse": {"forbidden": 4, "not_permitted": 1}}, T0, IB.portal_link(LINK, "veri-guvenligi"))
    assert d.subject == "[Günlük] Portal erişim özeti · 1 kişi · 29 Eylül"
    assert_template(d, "Günlük", "/timas/veri-guvenligi")
    assert D.digest_notice_from({}, T0) is None                    # kayıt yoksa e-posta yok


# ------------------------------------------------------------------ 4) kurumsal e-posta kutusu


def test_mailbox_connection_notices():
    since, now = T0 - timedelta(minutes=30), T0 + timedelta(minutes=3)
    n = M.connection_down_notice("timas@timas.com.tr", since, now, "Gmail API: invalid_grant", LINK)
    assert n.subject == "[Kesinti] Kurumsal e-posta kutusu 09:12'den beri okunamıyor"
    html, text = assert_template(n, "Kesinti", "/timas/kurumsal-eposta")
    assert "timas@timas.com.tr kutusu" in text
    f = M.connection_fixed_notice("timas@timas.com.tr", since, T0 + timedelta(minutes=95), T0 + timedelta(minutes=96), LINK)
    assert f.subject == "[Düzeldi] Kurumsal e-posta kutusu 11:17'de yeniden okundu · 2 sa 5 dk sürdü"
    assert_template(f, "Düzeldi", "/timas/kurumsal-eposta")


# ------------------------------------------------------------------ 5) departmansız CRM kullanıcıları


class FakeDirectory:
    def _crm_prefix(self):
        return "CRM.dbo."

    def _crm_rows(self, sql):
        if "SystemUserBase" in sql:
            return [{"Id": "A", "FullName": "Ali Kaya", "DomainName": "TIMAS\\ali", "InternalEMailAddress": "ali@timas.com.tr",
                     "CreatedOn": datetime(2025, 1, 2), "BirimAdi": "Timaş"},
                    {"Id": "B", "FullName": "Eski Hesap", "DomainName": "TIMAS\\eski", "InternalEMailAddress": None,
                     "CreatedOn": None, "BirimAdi": "Timaş"}]
        return [{"Id": "a", "Name": "07-Temel Rol"}]

    def list_people(self):
        return [{"subject": "ali", "label": "Ali Kaya", "hint": "ali", "detail": "Satis"}]


def test_crm_unassigned_mail_carries_only_needed_fields():
    from openpyxl import load_workbook

    sent = []
    out = CU.send(FakeDirectory(), lambda k, d="": {"CRM_UNASSIGNED_TO": "bilgiislem@timas.com.tr", "ALERT_LINK": LINK}.get(k, d),
                  lambda n, to, att: sent.append((n, to, att)) or "sent", now=datetime(2026, 9, 29, 7, 0))
    assert out["status"] == "sent"
    n, to, att = sent[0]
    assert n.subject == "[Bilgi] CRM'de departmanı olmayan 2 kullanıcı · 29 Eylül 07:00" and n.tone == "bilgi"
    html, text = assert_template(n, "Bilgi", "/timas/yonetim")
    assert "ali@timas.com.tr" not in html + text and "Ali Kaya" not in text   # gövdede kişi yok; birim sayıları var
    assert "1 kişinin şirket dizininde etkin hesabı yok" in text
    wb = load_workbook(io.BytesIO(att[0][1]))
    ws = wb["Kişiler"]
    assert [c.value for c in ws[1]] == ["#", "Ad Soyad", "Kullanıcı adı", "CRM'de oluşturulma"]
    cells = [str(c.value) for row in ws.iter_rows() for c in row if c.value is not None]
    assert "ali@timas.com.tr" not in cells and "07-Temel Rol" not in cells and "ali" in cells
    # Yetkiler ekranındaki tam liste değişmedi.
    full = load_workbook(io.BytesIO(CU.xlsx(CU.build(FakeDirectory()))))["Kişiler"]
    assert full.max_column == 9


def test_all_five_recipient_settings_exist():
    from semantic_bridge import admin as admin_mod

    keys = {s["key"] for s in admin_mod.SPEC}
    assert {"ITOPS_RECIPIENTS", "ITOPS_WEEKLY_TO", "SECURITY_ALERT_RECIPIENTS", "MAIL_CONNECTION_ALERT_TO",
            "CRM_UNASSIGNED_TO", "ITOPS_OUTAGE_MIN", "ITOPS_RESTART_GRACE_MIN", "ITOPS_REMIND_HOURS"} <= keys
    st = I.settings(lambda k, d="": d)
    assert (st["outageMin"], st["restartGraceMin"], st["remindHours"]) == (10, 5, 0)
