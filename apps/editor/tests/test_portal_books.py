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
