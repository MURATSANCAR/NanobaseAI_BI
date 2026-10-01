import io

import pytest

from editor import portal_books as PB


def test_slug_turkish_and_empty():
    assert PB.slug("Dünyanın En Korkak Hayvanı") == "dunyanin-en-korkak-hayvani"
    assert PB.slug("İstediğim  İnsan!") == "istedigim-insan"
    assert PB.slug("   ") == "kitap"


def test_title_from_filename_when_not_given():
    assert PB.title_of("", "anne_terligi-son.pdf") == "anne terligi son"
    assert PB.title_of("  Anne Terliği ", "x.pdf") == "Anne Terliği"


@pytest.mark.parametrize("step,status,n,label", [
    (None, "QUEUED", 0, "Sırada"),
    ("1/15 Kitap ve içerik sürümü", "RUNNING", 1, "Hazırlanıyor"),
    ("4/15 OCR", "RUNNING", 4, "Metin okunuyor"),
    ("7/15 Karakter ve olay adayları", "RUNNING", 7, "Karakterler ve olaylar çıkarılıyor"),
    ("13/15 Doğrulama → sürümlü özet, rapor ve indeks", "RUNNING", 13, "Özet ve künye hazırlanıyor"),
    ("13/15 x", "SUCCEEDED", 15, "Hazır"),
])
def test_phase_hides_step_names(step, status, n, label):
    p = PB.phase(step, status)
    assert (p["n"], p["label"]) == (n, label)
    assert "OCR" not in p["label"]


def test_save_writes_pdf_and_reuses_same_content(tmp_path):
    a = b"%PDF-1.7 bir"
    name, size = PB.save(io.BytesIO(a), tmp_path, "Kitap.pdf", "Güzel Kitap")
    assert (name, size) == ("guzel-kitap.pdf", len(a))
    assert PB.save(io.BytesIO(a), tmp_path, "Kitap.pdf", "Güzel Kitap")[0] == "guzel-kitap.pdf"
    assert PB.save(io.BytesIO(b"%PDF-1.7 iki"), tmp_path, "Kitap.pdf", "Güzel Kitap")[0] == "guzel-kitap-2.pdf"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["guzel-kitap-2.pdf", "guzel-kitap.pdf"]


@pytest.mark.parametrize("data,filename,msg", [
    (b"PK\x03\x04", "kitap.pdf", "PDF değil"),
    (b"", "kitap.pdf", "boş"),
    (b"%PDF-1.7", "kitap.docx", "Yalnız PDF"),
])
def test_save_rejects_and_leaves_no_partial(tmp_path, data, filename, msg):
    with pytest.raises(PB.UploadError, match=msg):
        PB.save(io.BytesIO(data), tmp_path, filename, "")
    assert list(tmp_path.iterdir()) == []


def _row(status, attempt=1, workflow_id=None, jid="j1"):
    return {"id": jid, "status": status, "step": None, "workflow_id": workflow_id, "requested_by": "portal:ayse",
            "created_at": None, "finished_at": None, "attempt": attempt, "title": "Kitap", "page_count": 32,
            "submitted_at": None}


@pytest.mark.parametrize("status,attempt,wf,state", [
    ("QUEUED", 1, None, "sirada"),
    ("QUEUED", 1, "book-analysis-j1", "okunuyor"),
    ("RUNNING", 1, "book-analysis-j1", "okunuyor"),
    ("SUCCEEDED", 2, "book-analysis-j1", "hazir"),
    ("FAILED", 1, "book-analysis-j1", "yeniden"),
    ("FAILED", PB.ATTEMPTS, "book-analysis-j1", "okunamadi"),
    ("CANCELLED", 1, "book-analysis-j1", "okunamadi"),
])
def test_item_state(status, attempt, wf, state):
    it = PB.item(_row(status, attempt, wf), [], 0)
    assert it["state"] == state
    assert it["failed"] == (state == "okunamadi")
    assert it["requested_by"] == "ayse"


def test_item_counts_books_ahead_including_the_running_one():
    waiting = ["a", "j1", "b"]
    assert PB.item(_row("QUEUED"), waiting, busy=2)["ahead"] == 3
    assert PB.item(_row("QUEUED"), waiting, busy=1)["ahead"] == 2
    assert PB.item(_row("QUEUED"), waiting, busy=0)["ahead"] == 1
    assert PB.item(_row("RUNNING", workflow_id="w"), waiting, busy=1)["ahead"] is None
