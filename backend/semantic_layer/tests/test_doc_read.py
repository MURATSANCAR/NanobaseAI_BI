"""Ortak yapı taşı 4 — belge okuma ve OCR hattı (`semantic_bridge.doc_read`) ve bağlandığı yerler: M33 şartname
özeti (OCR etiketi, alıntı denetimi aynen), M55 özgeçmiş (OCR metni de maskeden geçer), M39 sektör raporu (taranmış
sayfa), M57 sertifika denetimi (kayıttaki tarih/ad belgede birebir).

Uzak okuyucu (GPU sunucusundaki kart servisi) sahte verilir; PDF metin katmanı `pdf_pages` yerine konur. Gerçek OCR
kabulü test sunucusunda (scripts/acceptance/zeki-ortak-belge-benzerlik).
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from semantic_bridge import doc_read as DR

CFG = {"ocr": True, "timeout": 30, "minChars": 20, "lowConfidence": 0.8}
TEXT_PAGE = "Teknik şartname: yüklenici teslim süresi içinde kırk beş gün boyunca numune verecektir."
OCR_PAGE = "Gecikme halinde günlük binde üç ceza uygulanır. Yerli malı belgesi istenir."


def _pdf(monkeypatch, pages):
    monkeypatch.setattr(DR, "pdf_pages", lambda data: list(pages))
    return b"%PDF-1.7 sahte"


def _remote(calls, conf=0.91):
    def fn(name, data, pages):
        calls.append(pages)
        return {"pages": [{"page": p, "text": OCR_PAGE, "source": "ocr", "confidence": conf} for p in (pages or [1])]}
    return fn


def test_text_layer_only_does_not_call_remote(monkeypatch):
    data = _pdf(monkeypatch, [TEXT_PAGE, TEXT_PAGE])
    calls = []
    r = DR.read("s.pdf", data, remote=_remote(calls), cfg=CFG)
    assert calls == [] and [p["okuma"] for p in r.pages] == ["metin", "metin"]
    assert r.summary()["ocrSayfa"] == [] and r.summary()["not"] is None


def test_scanned_pages_go_to_ocr_and_are_labelled(monkeypatch):
    data = _pdf(monkeypatch, [TEXT_PAGE, "", "  12 "])
    calls = []
    r = DR.read("s.pdf", data, remote=_remote(calls, conf=0.72), cfg=CFG)
    assert calls == [[2, 3]]                                              # yalnız metinsiz sayfalar gönderilir
    assert [p["okuma"] for p in r.pages] == ["metin", "ocr", "ocr"]
    s = r.summary()
    assert s["ocrSayfa"] == ["2", "3"] and s["enDusukGuven"] == 0.72 and s["dusukGuven"] == ["2", "3"]
    assert "OCR" in s["not"] and "%72" in s["not"]
    assert OCR_PAGE in r.text() and TEXT_PAGE in r.text()


def test_image_file_is_sent_whole(monkeypatch):
    calls = []
    r = DR.read("belge.png", b"\x89PNG....", remote=_remote(calls), cfg=CFG)
    assert calls == [None] and r.pages[0]["okuma"] == "ocr"


def test_ocr_off_or_unavailable_is_explicit_not_silent(monkeypatch):
    data = _pdf(monkeypatch, ["", TEXT_PAGE])
    r = DR.read("s.pdf", data, remote=_remote([]), cfg={**CFG, "ocr": False})
    assert r.unread_pages == ["1"] and "kapalı" in r.errors[0]
    monkeypatch.setattr(DR, "remote_available", lambda: False)
    r = DR.read("s.pdf", data, cfg=CFG)
    assert r.unread_pages == ["1"] and "bağlı değil" in r.errors[0]

    def broken(name, data, pages):
        raise RuntimeError("bağlantı kesildi")
    r = DR.read("s.pdf", data, remote=broken, cfg=CFG)
    assert r.unread_pages == ["1"] and "cevap vermedi" in r.errors[0]
    assert "okunamadı" in r.summary()["not"]


def test_type_and_magic_checks():
    with pytest.raises(DR.ReadError, match="Desteklenmeyen"):
        DR.read("a.exe", b"MZ", cfg=CFG)
    with pytest.raises(DR.ReadError, match="uyuşmuyor"):
        DR.read("a.pdf", b"not a pdf", cfg=CFG)
    with pytest.raises(DR.ReadError, match="boş"):
        DR.read("a.pdf", b"", cfg=CFG)
    r = DR.read("a.txt", "Satır 1\r\nSatır 2".encode("cp1254"), cfg=CFG)
    assert r.text() == "Satır 1\nSatır 2" and r.pages[0]["okuma"] == "metin"


def test_find_quote_is_verbatim_folded_and_reports_page(monkeypatch):
    data = _pdf(monkeypatch, [TEXT_PAGE, ""])
    r = DR.read("s.pdf", data, remote=_remote([]), cfg=CFG)
    hit = DR.find_quote("GÜNLÜK binde üç   ceza", r)
    assert hit == {"sayfa": "2", "okuma": "ocr", "guven": 0.91}
    assert DR.find_quote("teslim süresi içinde kırk beş gün", r)["okuma"] == "metin"
    assert DR.find_quote("günlük binde beş ceza", r) is None                  # uydurma alıntı bulunmaz
    assert DR.find_quote("kısa", r) is None                                   # çok kısa alıntı kanıt sayılmaz
    # sayfa sınırında bölünen alıntı: ilk parçanın sayfası
    assert DR.find_quote("numune verecektir gecikme halinde", r)["sayfa"] == "1"


# ------------------------------------------------------------------ M33 şartname


def test_tender_summary_marks_ocr_items_and_keeps_quote_check(monkeypatch):
    from semantic_bridge import tenders as T

    data = _pdf(monkeypatch, [TEXT_PAGE, ""])
    monkeypatch.setattr(DR, "remote_available", lambda: True)
    monkeypatch.setattr(DR, "remote_read", lambda name, d, pages, timeout=0: _remote([])(name, d, pages))
    monkeypatch.setattr(DR, "settings", lambda: CFG)
    text, reading = T.document_reading("sartname.pdf", data)
    assert OCR_PAGE in text

    def chat(messages):
        return ('{"konu": {"deger": "Numune", "kaynak": "yüklenici teslim süresi içinde kırk beş gün"}, '
                '"kosullar": [{"deger": "Günlük binde üç ceza", "kaynak": "Gecikme halinde günlük binde üç ceza uygulanır"},'
                ' {"deger": "Binde beş ceza", "kaynak": "Gecikme halinde günlük binde beş ceza uygulanır"}]}')

    out = T.summarize_text(text, chat, {"summaryChunk": 100000}, lambda a, b: None, reading=reading)
    assert out["konu"]["okuma"] == "metin" and out["konu"]["sayfa"] == "1"
    assert [k["okuma"] for k in out["kosullar"]] == ["ocr"] and out["kosullar"][0]["guven"] == 0.91
    assert out["atilan"] == 1                                                 # alıntısı belgede olmayan madde atıldı
    assert out["okuma"]["ocrSayfa"] == ["2"]


def test_tender_empty_scan_says_why(monkeypatch):
    from semantic_bridge import tenders as T

    data = _pdf(monkeypatch, [""])
    monkeypatch.setattr(DR, "remote_available", lambda: False)
    monkeypatch.setattr(DR, "settings", lambda: CFG)
    text, reading = T.document_reading("s.pdf", data)
    with pytest.raises(T.TenderError, match="bağlı değil"):
        T.summarize_text(text, lambda m: "{}", {"summaryChunk": 1000}, lambda a, b: None, reading=reading)


# ------------------------------------------------------------------ M55 özgeçmiş


def test_cv_ocr_text_goes_through_mask(monkeypatch):
    from semantic_bridge import hr_recruit_text as X

    cv = "Deneyim: Redaktör 2019-2024. Telefon 0532 111 22 33, e-posta ali@ornek.com"
    data = _pdf(monkeypatch, [""])
    monkeypatch.setattr(DR, "settings", lambda: CFG)
    monkeypatch.setattr(DR, "remote_available", lambda: True)
    monkeypatch.setattr(DR, "remote_read", lambda n, d, p, timeout=0: {"pages": [{"page": 1, "text": cv, "source": "ocr",
                                                                                  "confidence": 0.95}]})
    text, summary = X.extract_reading("cv.pdf", data)
    assert text == cv and summary["ocrSayfa"] == ["1"]
    masked, counts = X.rule_mask(text)
    assert "0532" not in masked and "ali@ornek.com" not in masked
    monkeypatch.setattr(DR, "remote_available", lambda: False)
    from semantic_bridge.hr_core import HrError
    with pytest.raises(HrError, match="bağlı değil"):
        X.extract_reading("cv.pdf", data)


# ------------------------------------------------------------------ M39 sektör raporu


def test_market_report_scanned_pages_filled(monkeypatch):
    from semantic_bridge import pazar_sources as src

    data = _pdf(monkeypatch, [TEXT_PAGE, ""])
    monkeypatch.setattr(DR, "settings", lambda: CFG)
    monkeypatch.setattr(DR, "remote_available", lambda: True)
    monkeypatch.setattr(DR, "remote_read", lambda n, d, p, timeout=0: _remote([])(n, d, p))
    pages = [{"sayfa": "1", "metin": TEXT_PAGE}, {"sayfa": "2", "metin": ""}]
    out, extra = src.read_scanned("rapor.pdf", data, pages)
    assert out[1]["metin"] == OCR_PAGE and out[1]["okuma"] == "ocr" and out[0]["metin"] == TEXT_PAGE
    assert extra["ocrSayfa"] == ["2"] and extra["ocrGuven"] == {"2": 0.91}


# ------------------------------------------------------------------ M57 sertifika


def test_certificate_check_finds_record_values_verbatim():
    import sqlalchemy as sa

    from semantic_bridge import hr_core as H
    from semantic_bridge import hr_learning as L
    from semantic_layer.store.catalog_store import open_store

    e = open_store("sqlite://").engine
    H._ready.discard(e)
    L._ready.discard(e)
    L.ensure(e)
    with e.begin() as c:
        c.execute(L.CERTIFICATES.insert().values(
            id="srt1", tenant_id="t1", employee_id="emp1", title="İş Sağlığı ve Güvenliği", source="yukleme",
            issued_on=date(2026, 3, 5), expires_on=date(2027, 3, 5), file_blob=b"%PDF-1.7", file_name="isg.pdf",
            file_mime="application/pdf", file_size=8, created_by="ali", created_at=datetime.now(timezone.utc)))

    def fake_read(name, data, allowed=None):
        return DR.Reading(filename=name, pages=[{"sayfa": "1", "metin": "İŞ SAĞLIĞI VE GÜVENLİĞİ eğitimini 5 Mart 2026 "
                                                 "tarihinde tamamlamıştır.", "okuma": "ocr", "guven": 0.88}])

    out = L.certificate_check(e, "t1", "srt1", read=fake_read)
    rows = {r["alan"]: r for r in out["alanlar"]}
    assert rows["Eğitim / belge adı"]["bulundu"] and rows["Eğitim / belge adı"]["okuma"] == "ocr"
    assert rows["Belge tarihi"]["bulundu"] and rows["Belge tarihi"]["sayfa"] == "1"
    assert rows["Geçerlilik bitişi"]["bulundu"] is False                      # belgede yok: İK görür
    assert out["employeeId"] == "emp1" and out["okuma"]["ocrSayfa"] == ["1"]
    assert "05 03 2026" in L.date_forms(date(2026, 3, 5)) and "5 mart 2026" in L.date_forms(date(2026, 3, 5))
