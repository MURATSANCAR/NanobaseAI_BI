"""Dosyadan kayıt açma: ekranın üstündeki yükleme alanına bırakılan dosya, önce eser/iş açmayı beklemeden
yeni bir eser (M3 metin, M5 prova) ya da çeviri işi (M4) açar.

Sözleşme: ad dosya adından gelir (arayüzdeki `titleFromFilename` ile aynı kural); yükleme reddedilirse açılan
kayıt geri alınır ve yarım eser/iş kalmaz; iş adı sonra düzeltilebilir; uçların sayfa ve işlem yetkisi var.
"""

from __future__ import annotations

import os

import pytest
import sqlalchemy as sa

from semantic_bridge import access as A
from semantic_bridge import editorial_desk as desk
from semantic_bridge import editorial_translation as T
from semantic_layer.store.catalog_store import open_store

TENANT = "timas"
TEXT = "BÖLÜM 1\n\nKış geldi. Yollar kapandı.\n\nBÖLÜM 2\n\nBahar geç geldi.".encode("utf-8")
SRC = b"CHAPTER ONE\n\nIt was cold. We waited.\n\nCHAPTER TWO\n\nNobody came."


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITORIAL_DIR", str(tmp_path))
    e = open_store("sqlite://").engine
    T._ready.clear()
    desk._ready.clear()
    T.ensure(e)
    desk.ensure(e)
    return e


def _count(engine, table) -> int:
    with engine.connect() as c:
        return int(c.execute(sa.select(sa.func.count()).select_from(table)).scalar_one())


@pytest.mark.parametrize("name,title", [
    ("Kayip_Zaman-son.docx", "Kayip Zaman son"),
    ("Bir Roman - Taslak 3.txt", "Bir Roman Taslak 3"),
    ("C:\\Belgeler\\Uzun  Yol.pdf", "Uzun Yol"),
    ("yalnizad", "yalnizad"),
    ("___.md", "___.md"),
])
def test_title_from_filename(name, title):
    assert desk.title_from_filename(name) == title


def test_manuscript_opens_work_named_after_file(engine, tmp_path):
    out = desk.create_from_file(engine, TENANT, "editor", False, "manuscript", "Kış_Masalı.txt", TEXT)
    assert out["title"] == "Kış Masalı" and out["version"] == 1 and out["chapters"] == 2
    works = desk.list_works(engine, TENANT, "editor", False)
    assert [w["id"] for w in works] == [out["workId"]]
    assert works[0]["manuscript"]["filename"] == "Kış_Masalı.txt" and works[0]["chapters"]["total"] == 2
    # Ad sonra düzeltilir.
    desk.update_work(engine, TENANT, "editor", False, out["workId"], {"title": "Kış Masalı (düzeltilmiş)"})
    assert desk.list_works(engine, TENANT, "editor", False)[0]["title"] == "Kış Masalı (düzeltilmiş)"
    # İkinci yükleme aynı eserde yeni sürüm açar (seçili eser yolu değişmedi).
    again = desk.upload_manuscript(engine, TENANT, "editor", False, out["workId"], "v2.txt", TEXT + "\n\nSon.".encode())
    assert again["version"] == 2


def test_rejected_file_leaves_no_half_work(engine, tmp_path):
    with pytest.raises(desk.DeskError):
        desk.create_from_file(engine, TENANT, "editor", False, "manuscript", "bos.txt", b"   \n\n  ")
    with pytest.raises(desk.DeskError):
        desk.create_from_file(engine, TENANT, "editor", False, "proof", "prova.docx", b"PK..")   # prova PDF olmalı
    with pytest.raises(desk.DeskError):
        desk.create_from_file(engine, TENANT, "editor", False, "manuscript", "x.txt", b"")
    with pytest.raises(desk.DeskError):
        desk.create_from_file(engine, TENANT, "editor", False, "cover", "x.txt", TEXT)
    assert _count(engine, desk.WORKS) == 0 and _count(engine, desk.FILES) == 0
    assert not [p for p in os.listdir(tmp_path) if os.path.isdir(os.path.join(tmp_path, p))]


def test_delete_empty_work_never_touches_work_with_files(engine):
    out = desk.create_from_file(engine, TENANT, "editor", False, "manuscript", "a.txt", TEXT)
    desk.delete_empty_work(engine, TENANT, out["workId"])
    assert _count(engine, desk.WORKS) == 1


def test_other_user_does_not_see_file_created_work(engine):
    desk.create_from_file(engine, TENANT, "editor", False, "manuscript", "a.txt", TEXT)
    assert desk.list_works(engine, TENANT, "baska", False) == []


def test_translation_job_from_file(engine):
    out = T.create_from_file(engine, TENANT, "editor", False, "The_Road.txt", SRC, "en", "tr")
    assert out["title"] == "The Road" and out["version"] == 1 and out["segments"] >= 5
    jobs = T.list_jobs(engine, TENANT, "editor", False, False)
    assert [j["id"] for j in jobs] == [out["jobId"]]
    # Dil çifti ve ad sonra düzeltilebilir; kaynak dil kaynak yüklendiği için kilitli.
    T.update_job(engine, TENANT, "editor", False, out["jobId"], {"title": "Yol", "targetLang": "de"})
    with pytest.raises(T.TranslationError):
        T.update_job(engine, TENANT, "editor", False, out["jobId"], {"sourceLang": "fr"})


def test_translation_rejected_source_deletes_job(engine):
    with pytest.raises(T.TranslationError):
        T.create_from_file(engine, TENANT, "editor", False, "bos.txt", b"  \n ", "en", "tr")
    with pytest.raises(T.TranslationError):
        T.create_from_file(engine, TENANT, "editor", False, "a.txt", SRC, "en", "en")   # aynı dil: iş hiç açılmaz
    with pytest.raises(T.TranslationError):
        T.create_from_file(engine, TENANT, "editor", False, "a.rtf", b"{\\rtf1}", "en", "tr")
    assert T.list_jobs(engine, TENANT, "editor", False, False) == []
    assert _count(engine, T.JOBS) == 0


def test_from_file_endpoints_are_gated():
    # Sayfa kapısı: eser ucu editoryal sayfalardan, çeviri ucu çeviri sayfalarından biriyle açılır.
    pages = A.rule_for("/api/v1/editorial/works-from-file")
    assert A.page("redaksiyon") in pages and A.page("son-okuma") in pages
    assert A.page("ceviri") in A.rule_for("/api/v1/editorial/translation/jobs-from-file")
    # İşlem kapısı: çeviri işi açmak «Çeviri işi yönetme» ister; eser açma sayfa yetkisiyle yapılır (eski davranış).
    assert A.features_for("PUT", "/api/v1/editorial/translation/jobs-from-file") == ["ozellik:ceviri.yonet"]
    assert A.features_for("PUT", "/api/v1/editorial/works-from-file") == []
