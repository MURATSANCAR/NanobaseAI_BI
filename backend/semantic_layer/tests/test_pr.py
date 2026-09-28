"""M20 Basın, medya ve halkla ilişkiler: PR dosyası durum makinesi (iki göz, onaylı metin değişince taslağa dönüş),
gönderim satırı kuralları (onaysız gönderilmiş sayılmaz, tek alıcılı e-posta ön koşulları, takip günü), medya kişisi
birleştirme ve «haberdar olmak istemiyor», yansıma kaydı (tekil bağlantı, gönderim satırına bağlanma, tarama adayı),
öneri puanı, rapor sayıları, Zeki AI metin denetimi ve ton kararı, CRM SQL'inin yalnız okuma olması, tek sayfa okuma,
yetki kuralları.

Veriler yapaydır ve yalnız kuralları sınar; gerçek CRM kabulü test sunucusunda (`scripts/acceptance/m20/`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pytest
import sqlalchemy as sa

from semantic_bridge import access as A
from semantic_bridge import pr as PR
from semantic_bridge import pr_sources as S
from semantic_layer.store.catalog_store import open_store

T = "t1"
BOOK = "0f8fad5b-d9cb-469f-a165-70867728950e"
BOOK2 = "7c9e6679-7425-40de-944b-e07fc1f90ae7"
G1 = "11111111-2222-3333-4444-555555555555"
G2 = "66666666-7777-8888-9999-000000000000"


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    PR._ready.discard(id(e))
    PR.ensure(e)
    yield e
    PR._ready.discard(id(e))


def _book(bid=BOOK, **kw):
    b = {"kitapId": bid, "stokKodu": "15201.0001", "ad": "Deniz Feneri", "yazar": "Ayşe Yazar", "yayinevi": "Timaş Yayınları",
         "kitaplik": "Roman", "hedefKitle": "Yetişkin", "turler": "Roman, Tarih", "yayinTarihi": "2026-10-15", "fiyat": 250.0,
         "sayfa": 320, "yas": [None, None], "metinler": [{"alan": "new_ozet", "ad": "Arka kapak metni",
                                                          "metin": "Bir fener bekçisinin hikâyesi. «Deniz her şeyi hatırlar.»"}]}
    b.update(kw)
    return b


def _kit(engine, user="ayse", release=("Bülten metni", "crm:new_BasnBlteni"), bid=BOOK):
    return PR.create_kit(engine, T, user, _book(bid), release)


def _contacts(dnc_second=False):
    crm_rows = [{"id": G1, "ad": "Mehmet Muhabir", "eposta": "mehmet@gazete.com", "telefon": None, "unvan": "Kültür editörü",
                 "mecra": "Gazete A", "kurum": None, "epostaYok": False, "topluYok": False, "iys": None},
                {"id": G2, "ad": "Zeynep Yazar", "eposta": "zeynep@dergi.com", "telefon": None, "unvan": None, "mecra": "Dergi B",
                 "kurum": None, "epostaYok": dnc_second, "topluYok": False, "iys": None}]
    return crm_rows


def _merged(engine, **kw):
    return PR.merge_contacts(_contacts(**kw), PR.overlays(engine, T))


# ------------------------------------------------------------------ PR dosyası


def test_kit_ids_are_sequential_and_one_open_kit_per_book(engine):
    a = _kit(engine)
    b = _kit(engine, bid=BOOK2)
    y = date.today().year
    assert a == f"PR-{y}-0001" and b == f"PR-{y}-0002"
    with pytest.raises(PR.PrError) as e:
        _kit(engine)
    assert e.value.status == 409
    PR.close_kit(engine, T, "ayse", a)
    assert _kit(engine) == f"PR-{y}-0003"            # kapalı dosya yenisine engel değil


def test_release_source_is_recorded(engine):
    k = PR.kit_full(engine, T, _kit(engine, release=("M15 bülteni", "m15:abc")))
    assert k["releaseNational"] == "M15 bülteni" and k["sources"] == {"national": "m15:abc"}
    empty = PR.kit_full(engine, T, _kit(engine, release=None, bid=BOOK2))
    assert empty["releaseNational"] is None and empty["sources"] == {}


def test_submit_needs_release_and_submitter_cannot_approve(engine):
    kid = _kit(engine, release=None)
    with pytest.raises(PR.PrError):
        PR.submit_kit(engine, T, "ayse", kid)
    PR.update_kit(engine, T, "ayse", kid, {"releaseNational": "Metin"})
    PR.submit_kit(engine, T, "ayse", kid)
    with pytest.raises(PR.PrError) as e:
        PR.decide_kit(engine, T, "AYSE", kid, True)
    assert e.value.status == 409
    with pytest.raises(PR.PrError):
        PR.decide_kit(engine, T, "mudur", kid, False, "")          # gerekçesiz geri gönderme yok
    out = PR.decide_kit(engine, T, "mudur", kid, True)
    assert out["status"] == "onayli" and out["approvedBy"] == "mudur"


def test_approval_covers_the_send_list_and_text_change_drops_it(engine):
    kid = _kit(engine)
    PR.add_sends(engine, T, "ayse", kid, _merged(engine))
    PR.submit_kit(engine, T, "ayse", kid)
    with pytest.raises(PR.PrError):
        PR.update_kit(engine, T, "ayse", kid, {"releaseNational": "değişti"})      # onayda metin değişmez
    kit = PR.decide_kit(engine, T, "mudur", kid, True)
    assert all(s["approved"] for s in kit["sends"])
    kit = PR.update_kit(engine, T, "ayse", kid, {"releaseNational": "yeni metin"})
    assert kit["status"] == "taslak" and kit["version"] == 2 and not any(s["approved"] for s in kit["sends"])
    assert kit["sources"]["national"] == "kullanici"


def test_owner_change_does_not_drop_approval(engine):
    kid = _kit(engine)
    PR.submit_kit(engine, T, "ayse", kid)
    PR.decide_kit(engine, T, "mudur", kid, True)
    assert PR.update_kit(engine, T, "ayse", kid, {"owner": "ali"})["status"] == "onayli"


def test_closed_kit_is_read_only_and_reopens(engine):
    kid = _kit(engine)
    PR.close_kit(engine, T, "ayse", kid)
    with pytest.raises(PR.PrError):
        PR.update_kit(engine, T, "ayse", kid, {"releaseLocal": "x"})
    assert PR.close_kit(engine, T, "ayse", kid, reopen=True)["status"] == "taslak"


def test_zeki_draft_fills_empty_fields_and_keeps_user_text(engine):
    kid = _kit(engine, release=None)
    PR.update_kit(engine, T, "ayse", kid, {"releaseLocal": "Kullanıcının yerel bülteni"})
    filled = PR.put_draft(engine, T, "ayse", kid, {"national": {"metin": "Zeki ulusal", "dusenSayisi": 0},
                                                   "local": {"metin": "Zeki yerel", "dusenSayisi": 1},
                                                   "openings": {"metin": "a\nb\nc", "dusenSayisi": 0}})
    k = PR.kit_full(engine, T, kid)
    assert filled["national"] == "alana-yazildi" and k["releaseNational"] == "Zeki ulusal" and k["sources"]["national"] == "zeki"
    assert filled["local"] == "oneri" and k["releaseLocal"] == "Kullanıcının yerel bülteni"
    assert k["draft"]["local"]["metin"] == "Zeki yerel" and k["draft"]["openings"]["metin"] == "a\nb\nc"


# ------------------------------------------------------------------ gönderim


def test_send_list_skips_duplicates_and_do_not_contact(engine):
    kid = _kit(engine)
    PR.update_kit(engine, T, "ayse", kid, {"pitchTemplate": "Merhaba {ad}, {mecra} okurları için…"})
    out = PR.add_sends(engine, T, "ayse", kid, _merged(engine, dnc_second=True))
    assert len(out["added"]) == 1 and out["skipped"][0]["neden"] == "haberdar olmak istemiyor"
    again = PR.add_sends(engine, T, "ayse", kid, _merged(engine))
    assert [s["neden"] for s in again["skipped"]] == ["listede var"] and len(again["added"]) == 1
    s = PR.kit_full(engine, T, kid)["sends"][0]
    assert s["pitch"] == "Merhaba Mehmet, Gazete A okurları için…" and s["pitchSource"] == "sablon" and s["status"] == "hazir"


def test_unapproved_send_cannot_be_marked_sent(engine):
    kid = _kit(engine)
    sid = PR.add_sends(engine, T, "ayse", kid, _merged(engine)[:1])["added"][0]
    with pytest.raises(PR.PrError) as e:
        PR.update_send(engine, T, "ayse", sid, {"status": "gonderildi"}, 5)
    assert e.value.status == 409
    PR.submit_kit(engine, T, "ayse", kid)
    PR.decide_kit(engine, T, "mudur", kid, True)
    s = PR.update_send(engine, T, "ayse", sid, {"status": "gonderildi", "sentAt": "2026-09-01"}, 5)
    assert s["followUpAt"] == "2026-09-06" and s["overdue"] is True
    with pytest.raises(PR.PrError):
        PR.update_send(engine, T, "ayse", sid, {"status": "hazir"}, 5)
    with pytest.raises(PR.PrError):
        PR.delete_send(engine, T, "ayse", sid)
    with pytest.raises(PR.PrError):
        PR.update_send(engine, T, "ayse", sid, {"pitch": "yeni"}, 5)
    assert PR.update_send(engine, T, "ayse", sid, {"status": "cevap"}, 5)["statusLabel"] == "Cevap geldi"


def test_late_send_needs_its_own_approval_by_someone_else(engine):
    kid = _kit(engine)
    PR.submit_kit(engine, T, "ayse", kid)
    PR.decide_kit(engine, T, "mudur", kid, True)
    sid = PR.add_sends(engine, T, "ayse", kid, _merged(engine)[:1])["added"][0]
    assert not PR.get_send(engine, T, sid)["approved"]
    with pytest.raises(PR.PrError):
        PR.approve_send(engine, T, "ayse", sid)
    assert PR.approve_send(engine, T, "mudur", sid)["approved"]
    PR.update_send(engine, T, "ali", sid, {"pitch": "elle yazıldı"}, 5)
    assert not PR.get_send(engine, T, sid)["approved"]                    # metin değişince onay düşer
    with pytest.raises(PR.PrError):
        PR.approve_send(engine, T, "ali", sid)


def test_mail_preconditions(engine):
    kid = _kit(engine)
    PR.update_kit(engine, T, "ayse", kid, {"pitchTemplate": "Merhaba {ad}"})
    sid = PR.add_sends(engine, T, "ayse", kid, _merged(engine)[:1])["added"][0]
    contact = _merged(engine)[0]
    kit = PR.kit_full(engine, T, kid)
    assert PR.mail_check(kit, PR.get_send(engine, T, sid), contact) == "PR dosyası onaylı değil."
    PR.submit_kit(engine, T, "ayse", kid)
    kit = PR.decide_kit(engine, T, "mudur", kid, True)
    assert PR.mail_check(kit, PR.get_send(engine, T, sid), contact) is None
    assert "e-posta adresi" in PR.mail_check(kit, PR.get_send(engine, T, sid), {**contact, "email": None})
    assert "haberdar olmak istemiyor" in PR.mail_check(kit, PR.get_send(engine, T, sid), {**contact, "doNotContact": True})
    done = PR.record_mail(engine, T, "ayse", sid, "gonderildi", 5)
    assert done["status"] == "gonderildi" and done["followUpAt"] == (PR.today() + timedelta(days=5)).isoformat()
    assert "zaten gönderildi" in PR.mail_check(kit, done, contact)
    failed_kid = _kit(engine, bid=BOOK2)
    sid2 = PR.add_sends(engine, T, "ayse", failed_kid, _merged(engine)[:1])["added"][0]
    assert PR.record_mail(engine, T, "ayse", sid2, "gonderilemedi", 5)["status"] == "hazir"


def test_overdue_sends_are_listed_until_answered(engine):
    kid = _kit(engine)
    sid = PR.add_sends(engine, T, "ayse", kid, _merged(engine)[:1])["added"][0]
    PR.submit_kit(engine, T, "ayse", kid)
    PR.decide_kit(engine, T, "mudur", kid, True)
    PR.update_send(engine, T, "ayse", sid, {"status": "gonderildi", "sentAt": "2026-09-01"}, 5)
    assert [x["id"] for x in PR.overdue_sends(engine, T, date(2026, 9, 10))] == [sid]
    assert PR.overdue_sends(engine, T, date(2026, 9, 5)) == []
    PR.update_send(engine, T, "ayse", sid, {"status": "cevap"}, 5)
    assert PR.overdue_sends(engine, T, date(2026, 9, 10)) == []


# ------------------------------------------------------------------ medya kişileri


def test_contacts_merge_overlay_and_crm_email_refusal(engine):
    m = _merged(engine, dnc_second=True)
    assert [c["key"] for c in m] == [f"crm:{G1}", f"crm:{G2}"] and m[1]["doNotContact"] and "CRM" in m[1]["dncReason"]
    PR.update_contact(engine, T, "ayse", f"crm:{G1}", {"topics": "çocuk, tarih, Çocuk", "outletType": "gazete"}, lambda g: g == G1)
    c = _merged(engine)[0]
    assert c["topics"] == ["çocuk", "tarih"] and c["outletType"] == "gazete" and c["hasOverlay"] and c["email"] == "mehmet@gazete.com"
    with pytest.raises(PR.PrError) as e:
        PR.update_contact(engine, T, "ayse", "crm:99999999-2222-3333-4444-555555555555", {"note": "x"}, lambda g: False)
    assert e.value.status == 404


def test_portal_contact_crud_and_do_not_contact(engine):
    with pytest.raises(PR.PrError):
        PR.create_contact(engine, T, "ayse", {"email": "a@b.com"})
    with pytest.raises(PR.PrError):
        PR.create_contact(engine, T, "ayse", {"name": "X", "email": "geçersiz"})
    cid = PR.create_contact(engine, T, "ayse", {"name": "Podcast Sunucusu", "outletType": "podcast", "email": "p@x.com"})
    PR.update_contact(engine, T, "ayse", cid, {"doNotContact": True, "dncReason": "Bülten istemiyor"}, lambda g: False)
    c = PR.find_contact(_merged(engine), cid)
    assert c["doNotContact"] and c["dncReason"] == "Bülten istemiyor" and c["source"] == "portal"
    assert PR.delete_contact(engine, T, "ayse", cid)["name"] == "Podcast Sunucusu"


def test_contact_with_history_is_not_deleted(engine):
    cid = PR.create_contact(engine, T, "ayse", {"name": "Radyocu", "email": "r@x.com"})
    kid = _kit(engine)
    PR.add_sends(engine, T, "ayse", kid, [PR.find_contact(_merged(engine), cid)])
    with pytest.raises(PR.PrError) as e:
        PR.delete_contact(engine, T, "ayse", cid)
    assert e.value.status == 409


# ------------------------------------------------------------------ yansıma


def test_coverage_url_is_unique_and_links_to_the_send(engine):
    kid = _kit(engine)
    sid = PR.add_sends(engine, T, "ayse", kid, _merged(engine)[:1])["added"][0]
    PR.submit_kit(engine, T, "ayse", kid)
    PR.decide_kit(engine, T, "mudur", kid, True)
    PR.update_send(engine, T, "ayse", sid, {"status": "gonderildi"}, 5)
    with pytest.raises(PR.PrError):
        PR.add_coverage(engine, T, "ayse", {"title": "x", "url": "ftp://x"})
    cov = PR.add_coverage(engine, T, "ayse", {"title": "Fener bekçisi romanı", "url": "https://gazete.com/a", "publishedAt": "2026-10-20",
                                              "contactKey": f"crm:{G1}", "crmBookId": BOOK, "summary": "x" * 900})
    assert cov["sendId"] == sid and cov["kitId"] == kid and len(cov["summary"]) == PR.SUMMARY_MAX
    assert PR.get_send(engine, T, sid)["status"] == "haber"
    with pytest.raises(PR.PrError) as e:
        PR.add_coverage(engine, T, "ayse", {"title": "tekrar", "url": "https://gazete.com/a"})
    assert e.value.status == 409


def test_web_candidates_enter_as_pending_and_rejected_stay_out(engine):
    items = [{"url": "https://site/a", "title": "Yazar söyleşisi", "label": "olumlu", "books": [{"id": BOOK.upper(), "title": "Deniz Feneri"}],
              "author": "Ayşe Yazar", "contactId": G2, "itemId": "i1", "publishedAt": "2026-10-02", "outlet": "Site"}]
    assert PR.import_web(engine, T, items) == {"eklenen": 1, "zatenVar": 0}
    cand = PR.list_coverage(engine, T, state="aday")[0]
    assert cand["tone"] == "olumlu" and cand["toneSource"] == "web" and cand["crmBookId"] == BOOK
    PR.update_coverage(engine, T, "ayse", cand["id"], {"state": "reddedildi"})
    assert PR.import_web(engine, T, items) == {"eklenen": 0, "zatenVar": 1}
    with pytest.raises(PR.PrError):
        PR.delete_coverage(engine, T, "ayse", cand["id"])


def test_zeki_tone_never_overrides_a_person(engine):
    cov = PR.add_coverage(engine, T, "ayse", {"title": "Başlık", "tone": "olumsuz"})
    assert PR.set_tone(engine, cov["id"], "olumlu", 0.9) is False
    other = PR.add_coverage(engine, T, "ayse", {"title": "Başka"})
    assert [c["id"] for c in PR.untoned(engine, T)] == [other["id"]]
    PR.set_tone(engine, other["id"], None, 0.4)                 # emin değil: bir daha denenmez
    assert PR.untoned(engine, T) == []


def test_archive_rows_join_the_list_read_only():
    a = {"id": "h1", "baslik": "Eski haber", "link": None, "tarih": "2024-05-01", "mecra": "Gazete A", "muhabirId": G1, "muhabir": "M",
         "gorusulenId": None, "yazar": "Ayşe Yazar", "kitapText": None, "books": [{"kitapId": BOOK, "ad": "Deniz Feneri"}]}
    row = PR.archive_as_coverage(a)
    assert row["readOnly"] and row["source"] == "crm-arsiv" and row["contactKey"] == f"crm:{G1}"
    rows = PR.filter_coverage([row], frm="2024-01-01", to="2024-12-31", book=BOOK, q="eski")
    assert len(rows) == 1 and PR.filter_coverage([row], frm="2025-01-01") == []


# ------------------------------------------------------------------ öneri ve rapor


def test_suggestion_score_is_explained_and_excludes_do_not_contact(engine):
    archive = [{"id": "h1", "tarih": (PR.today() - timedelta(days=30)).isoformat(), "muhabirId": G1, "gorusulenId": None,
                "books": [{"yazar": "Ayşe Yazar", "kitaplik": "Roman", "hedefKitle": "Yetişkin"}]}]
    contacts = _merged(engine)
    contacts[1]["topics"] = ["tarih"]
    ranked = PR.suggest(contacts, archive, _book(), {}, set())
    top = ranked[0]
    assert top["key"] == f"crm:{G1}" and top["score"] == 3 + 2 + 1 + 1 and "yazarın kitapları hakkında 1 haber" in top["reasons"]
    assert ranked[1]["score"] == 2 and ranked[1]["reasons"] == ["konu etiketi: tarih"]
    contacts[0]["doNotContact"] = True
    assert [r["key"] for r in PR.suggest(contacts, archive, _book(), {}, set())] == [f"crm:{G2}"]


def test_report_counts_by_period(engine):
    kid = _kit(engine)
    sids = PR.add_sends(engine, T, "ayse", kid, _merged(engine))["added"]
    PR.submit_kit(engine, T, "ayse", kid)
    PR.decide_kit(engine, T, "mudur", kid, True)
    PR.update_send(engine, T, "ayse", sids[0], {"status": "gonderildi", "sentAt": "2026-09-02"}, 5)
    PR.update_send(engine, T, "ayse", sids[0], {"status": "cevap"}, 5)
    PR.update_send(engine, T, "ayse", sids[1], {"status": "gonderildi", "sentAt": "2026-08-20"}, 5)
    PR.add_coverage(engine, T, "ayse", {"title": "A", "publishedAt": "2026-09-03", "outlet": "Gazete A", "tone": "olumlu",
                                        "crmBookId": BOOK, "bookTitle": "Deniz Feneri"})
    PR.add_coverage(engine, T, "ayse", {"title": "B", "publishedAt": "2026-07-01", "outlet": "Gazete A"})
    rep = PR.report(engine, T, "2026-09-01", "2026-09-07", [{"tarih": "2026-09-05"}, {"tarih": "2025-01-01"}])
    assert rep["sends"]["total"] == 1 and rep["sends"]["answered"] == 1 and rep["sends"]["answerRate"] == 1.0
    assert rep["coverage"]["total"] == 1 and rep["coverage"]["byTone"] == {"olumlu": 1}
    assert rep["coverage"]["books"][0]["count"] == 1 and rep["archive"]["total"] == 1
    assert "Kayıtlı yansıma: 1" in PR.report_facts(rep)
    assert PR.week_of(date(2026, 9, 28)) == ("2026-09-21", "2026-09-27")


# ------------------------------------------------------------------ Zeki AI


class _Llm:
    def __init__(self, reply):
        self.reply = reply

    def chat(self, messages, **_):
        return self.reply


@dataclass
class _Choice:
    choice: str
    p: float

    @property
    def probability(self):
        return self.p

    def confident(self, min_prob, min_margin=0.0):
        return self.p >= min_prob

    def as_dict(self):
        return {"method": "logprobs", "choice": self.choice}


class _Chooser:
    def __init__(self, choice, p):
        self.c = _Choice(choice, p)

    def choose(self, prompt, choices):
        assert self.c.choice in choices
        return self.c


def test_draft_drops_invented_numbers_quotes_and_tech_names():
    reply = ("Deniz Feneri okurla buluşuyor. Kitap 50 bin adet sattı. Kitabın cümlesi «Deniz her şeyi hatırlar» diye akılda "
             "kalıyor. Yazar «Uydurma alıntı burada» diyor. Qwen ile yazıldı. Kitap 320 sayfa.")
    out = PR.draft_part(_Llm(reply), _book(), "national")
    assert "50 bin" not in out["metin"] and "Uydurma" not in out["metin"] and "Qwen" not in out["metin"]
    assert "«Deniz her şeyi hatırlar»" in out["metin"] and "320 sayfa" in out["metin"] and out["dusenSayisi"] == 3


def test_tone_is_a_closed_choice_with_threshold():
    assert PR.classify_tone(_Chooser("Olumlu", 0.9), "t", None, "k", "y", 0.6, 0.2)[0] == "olumlu"
    tone, prob, _ = PR.classify_tone(_Chooser("Olumsuz", 0.5), "t", None, "k", "y", 0.6, 0.2)
    assert tone is None and prob == 0.5
    assert PR.classify_tone(None, "t", None, None, None, 0.6, 0.2)[0] is None


def test_settings_defaults():
    s = PR.settings(lambda k: "")
    assert s["followUpDays"] == 5 and s["reportWeekday"] == 1 and s["webWatch"] is False and s["crmRoles"] == []
    s = PR.settings(lambda k: {"PR_FOLLOW_UP_DAYS": "7", "WEB_WATCH_ENABLED": "1", "PR_CRM_MEDIA_ROLES": "Gazeteci, Editör"}.get(k, ""))
    assert s["followUpDays"] == 7 and s["webWatch"] and s["crmRoles"] == ["Gazeteci", "Editör"]


# ------------------------------------------------------------------ kaynaklar


def test_crm_sql_is_read_only_and_validates_input():
    sqls = [S.month_books_sql("Timas_MSCRM.dbo", date(2026, 9, 1), date(2026, 9, 30)), S.book_sql("Timas_MSCRM.dbo", BOOK),
            S.book_authors_sql("Timas_MSCRM.dbo", BOOK), S.media_contacts_sql("Timas_MSCRM.dbo", ["Gazeteci", "O'Brien"]),
            S.archive_sql("Timas_MSCRM.dbo"), S.archive_base_sql("Timas_MSCRM.dbo"), S.archive_books_sql("Timas_MSCRM.dbo"), S.promo_orders_sql("Timas_MSCRM.dbo", "15201.0001"),
            *S.book_search_sql("Timas_MSCRM.dbo", "fener'; drop", 0)]
    for q in sqls:
        body = "\n".join(line for line in q.splitlines() if not line.strip().startswith("--")).upper()
        assert not any(w in body.split() for w in ("INSERT", "UPDATE", "DELETE", "MERGE", "EXEC", "DROP"))
    assert "N'O''Brien'" in sqls[3] and "new_siparistipi = 12" in sqls[7]
    assert "'2026-08-31 21:00:00'" in sqls[0] and "'2026-09-30 21:00:00'" in sqls[0]
    with pytest.raises(S.SourceError):
        S.book_sql("Timas_MSCRM.dbo", "x' OR 1=1 --")
    with pytest.raises(S.SourceError):
        S.prefix("bad;name.dbo")


def test_archive_rows_merge_books_and_outlets():
    heads = [{"id": "{AAAA0000-0000-0000-0000-000000000001}", "baslik": "Haber", "tarih": "2024-03-02", "mecra1": "TRT", "mecra2": "TRT",
              "mecra3": None, "muhabir_id": G1.upper(), "muhabir": "M", "yayinlandi": 1}]
    links = [{"haber_id": "aaaa0000-0000-0000-0000-000000000001", "kitap_id": BOOK, "ad": "Deniz Feneri", "yazar": "Ayşe Yazar"}]
    a = S.archive_rows(heads, links)[0]
    assert a["mecra"] == "TRT" and a["muhabirId"] == G1 and a["books"][0]["ad"] == "Deniz Feneri" and a["yayinlandi"]


def test_single_page_read_respects_robots_and_parses_meta():
    page = (b'<html><head><title>Yedek</title><meta property="og:title" content="Fener romani &amp; yazari">'
            b'<meta property="article:published_time" content="2026-10-02T09:00:00+03:00">'
            b'<meta property="og:site_name" content="Gazete A"><meta name="description" content="Kisa ozet"></head></html>')
    out = S.fetch_page("https://www.gazete.com/x", get=lambda u: page, allowed=lambda u: True)
    assert out == {"title": "Fener romani & yazari", "publishedAt": "2026-10-02", "outlet": "Gazete A", "summary": "Kisa ozet",
                   "host": "www.gazete.com"}
    assert "robots" in S.fetch_page("https://www.gazete.com/x", get=lambda u: page, allowed=lambda u: False)["error"]
    assert "http" in S.fetch_page("file:///etc/passwd")["error"]


def test_private_addresses_are_not_fetched():
    assert S._public_host("127.0.0.1") is False and S._public_host("192.168.0.28") is False


# ------------------------------------------------------------------ yetki


def test_access_rules_for_pr():
    assert A.rule_for("/api/v1/pr/run-due") == A.SYSTEM
    assert A.rule_for("/api/v1/pr/home") == {"sayfa:basin-iliskileri"}
    f = A.features_for
    assert f("GET", "/api/v1/pr/contacts") == [] and f("POST", "/api/v1/pr/contacts") == ["ozellik:pr.duzenle"]
    assert f("PATCH", "/api/v1/pr/contacts/crm:" + G1) == ["ozellik:pr.duzenle"]
    assert f("POST", "/api/v1/pr/kits/PR-2026-0001/draft") == ["ozellik:pr.duzenle"]
    assert f("POST", "/api/v1/pr/kits/PR-2026-0001/approve") == []             # açıkça verilen; ucun içinde
    assert f("POST", "/api/v1/pr/sends/abc/mail") == [] and f("POST", "/api/v1/pr/sends/abc/approve") == []
    assert f("POST", "/api/v1/pr/coverage/preview") == ["ozellik:pr.duzenle"]
    assert f("GET", "/api/v1/pr/report/export.xlsx") == ["ozellik:veri.disa-aktar"]
    assert {"ozellik:pr.onay", "ozellik:pr.gonder"} <= A.explicit_keys()
    assert "ozellik:pr.duzenle" not in A.explicit_keys()
    page = next(p for p in A.catalog()["pages"] if p["key"] == "sayfa:basin-iliskileri")
    assert page["area"] == "pazarlama" and page.get("explicit") is True


def test_report_xlsx_has_the_items(engine):
    pytest.importorskip("openpyxl")
    from semantic_bridge import pr_export as X
    PR.add_coverage(engine, T, "ayse", {"title": "A", "publishedAt": "2026-09-03"})
    body = X.report_xlsx(PR.report(engine, T, "2026-09-01", "2026-09-07", []))
    assert body[:2] == b"PK"


def test_tables_have_tenant_and_no_crm_writes(engine):
    names = set(sa.inspect(engine).get_table_names())
    assert {"semantic_pr_contacts", "semantic_pr_kits", "semantic_pr_sends", "semantic_pr_coverage", "semantic_pr_events",
            "semantic_pr_jobs", "semantic_pr_meta"} <= names
