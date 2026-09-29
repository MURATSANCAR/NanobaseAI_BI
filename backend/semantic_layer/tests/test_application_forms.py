"""Yazar başvuru formları → Başvurular: başlık eşleme, satır dönüşümü, tekrar önleme, hata yalıtımı.

Başlıklar TİMAŞ'ın Genç (11-14) formunun yanıt tablosundan birebir (2026-09-29); değerler uydurmadır.
"""
from __future__ import annotations

import pytest
import sqlalchemy as sa

from semantic_bridge import application_forms as F
from semantic_bridge import editorial_applications as A
from semantic_layer.store.catalog_store import open_store

HEADER = ["Form ID", "Zaman Damgası", "Adınız", "Soyadınız", "E-posta Adresiniz", "Telefon Numaranız", "Mesleğiniz",
          "Ülke", "İl / Şehir", "İlçe", "Açık Adresiniz", "Özgeçmişiniz (CV)", "Eserinizin Adı ", "Eserinizin Türü ",
          "Eserinizin Konusu", "Eserinizin Özeti (Sinopsis)", "Hedef Okur Kitlesi", "Eserinizin Öne Çıkan Yönleri",
          "Referanslarınız ", "Eser Dosyanız",
          "Başvuru koşullarını okuduğumu, anladığımı ve forma girdiğim tüm bilgilerin doğruluğunu beyan ettiğimi onaylıyorum."]
T = "t1"


def row(fid="a1b2c3", ts="26.09.2026 14:03:11", name="Deniz", surname="Yılmaz", email="deniz@example.com",
        audience="Genç (11-14 Yaş)", title="Kayıp Harita"):
    return [fid, ts, name, surname, email, "0555 000 00 00", "Öğretmen", "Türkiye", "İstanbul", "Kadıköy", "Örnek Sk. 1",
            "https://drive.google.com/file/d/cv1", title, "Macera (Çocuk/Gençlik)", "Bir hazine arayışı",
            "Üç arkadaş eski bir harita bulur.", audience, "Ekip ruhu", "—", "https://drive.google.com/file/d/eser1",
            "Okudum, Onayladım"]


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    A._ready.clear()
    F._ready.clear()
    F.ensure(e)
    return e


def test_header_maps_every_question_by_name():
    cols = F.map_header(HEADER)
    assert cols["formId"] == 0 and cols["firstName"] == 2 and cols["lastName"] == 3
    assert cols["email"] == 4 and cols["address"] == 10 and cols["cv"] == 11 and cols["title"] == 12
    assert cols["synopsis"] == 15 and cols["audience"] == 16 and cols["workFile"] == 19 and cols["consent"] == 20
    assert len(cols) == len(HEADER)
    # sıra değişse de aynı alanlar bulunur
    shuffled = list(reversed(HEADER))
    c2 = F.map_header(shuffled)
    assert shuffled[c2["title"]] == "Eserinizin Adı " and shuffled[c2["lastName"]] == "Soyadınız"


def test_row_to_application():
    cols = F.map_header(HEADER)
    a = F.application_of(row(), cols)
    assert a["title"] == "Kayıp Harita" and a["author_name"] == "Deniz Yılmaz"
    assert a["author_email"] == "deniz@example.com" and a["author_expertise"] == "Öğretmen"
    assert (a["audience"], a["age_from"], a["age_to"]) == ("genc", 11, 14)
    assert a["summary"].startswith("Üç arkadaş") and a["channel"] == "web"
    assert a["received_on"].isoformat() == "2026-09-26"
    assert F.parse_audience("Çocuk (0-9 Yaş)") == ("cocuk", 0, 9)
    assert F.parse_audience("İlk Gençlik (9-11 Yaş)") == ("genc", 9, 11)
    # geçersiz e-posta yazılmaz, boş özet düşmez
    b = F.application_of(row(email="yok"), cols)
    assert b["author_email"] is None


def test_timestamp_is_istanbul_time():
    ts = F.parse_timestamp("01.01.2026 00:30:00")
    assert ts.isoformat() == "2025-12-31T21:30:00+00:00"
    assert F.parse_timestamp("bozuk") is None


def test_import_once_and_answers_update_without_touching_application(engine):
    rows = [HEADER, row(), row(fid="x9", title="İkinci")]
    r1 = F.import_sheet(engine, T, "sheetA", "Genç (11-14 Yaş) Başvuruları", rows)
    assert (r1["new"], r1["existing"]) == (2, 0)
    r2 = F.import_sheet(engine, T, "sheetA", "Genç", rows)
    assert (r2["new"], r2["existing"], r2["updated"]) == (0, 2, 0)
    with engine.connect() as c:
        apps = c.execute(sa.select(A.APPS)).fetchall()
    assert len(apps) == 2 and {a.status for a in apps} == {"yeni"} and {a.created_by for a in apps} == {F.ACTOR}
    assert all(a.page_estimate is None for a in apps)
    # tabloda cevap değişirse yalnız form yanıtı güncellenir
    changed = [HEADER, row(title="Başlık değişti"), row(fid="x9", title="İkinci")]
    r3 = F.import_sheet(engine, T, "sheetA", "Genç", changed)
    assert r3["updated"] == 1 and r3["new"] == 0
    with engine.connect() as c:
        titles = sorted(a.title for a in c.execute(sa.select(A.APPS)))
    assert titles == sorted(["Kayıp Harita", "İkinci"])  # başvurunun kendi alanı değişmedi
    app_id = next(a.id for a in apps if a.title == "Kayıp Harita")
    form = F.answers_for(engine, T, app_id)
    labels = {x["label"]: x["value"] for x in form["answers"]}
    assert labels["Eserin adı"] == "Başlık değişti" and labels["Açık adres"] == "Örnek Sk. 1"
    assert "Form kimliği" not in labels


def test_missing_required_column_skips_sheet(engine):
    bad = [h for h in HEADER if h != "Form ID"]
    res = F.import_sheet(engine, T, "sheetB", "Bozuk", [bad, row()[1:]])
    assert res["new"] == 0 and res["skipped"] == 1 and "Form kimliği" in res["problems"][0]


def test_sync_isolates_unshared_sheet(engine):
    def get(url, params):
        if "gizli" in url:
            raise F.FormError("Tablo servis hesabıyla paylaşılmamış.", 403)
        if "/values/" in url:
            return {"values": [HEADER, row()]}
        return {"properties": {"title": "Genç"}, "sheets": [{"properties": {"title": "Sayfa1"}}]}

    setting = ("https://docs.google.com/spreadsheets/d/gizliAAAAAAAAAAAAAAAAAAAA/edit "
               "acikBBBBBBBBBBBBBBBBBBBBBB")
    out = F.sync(engine, T, setting, lambda s: "x", http_get=get)
    assert out["new"] == 1 and out["errors"] == 1
    st = F.status(engine, T, setting)
    assert st["configured"] == 2 and st["lastRun"]["new"] == 1
    assert {s["sheetId"]: s["applications"] for s in st["sheets"]} == {"gizliAAAAAAAAAAAAAAAAAAAA": 0,
                                                                       "acikBBBBBBBBBBBBBBBBBBBBBB": 1}


def test_sheet_ids_from_links_and_ids():
    s = "https://docs.google.com/spreadsheets/d/1wME0i1A8aVoMHfP_w-qnn6nwssM7i0CbSbD67m5uvEM/edit?gid=0\n1yAvMQXw9_U5ZwMABMUJ1OYndM4Avh9V_xV4GdDQ3cQ0, 1yAvMQXw9_U5ZwMABMUJ1OYndM4Avh9V_xV4GdDQ3cQ0"
    assert F.sheet_ids(s) == ["1wME0i1A8aVoMHfP_w-qnn6nwssM7i0CbSbD67m5uvEM", "1yAvMQXw9_U5ZwMABMUJ1OYndM4Avh9V_xV4GdDQ3cQ0"]
    assert F.sheet_ids("") == []
