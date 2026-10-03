import io

import pytest

from editor import portal_books as PB


def test_slug_turkish_and_empty():
    assert PB.slug("Dünyanın En Korkak Hayvanı") == "dunyanin-en-korkak-hayvani"
    assert PB.slug("İstediğim  İnsan!") == "istedigim-insan"
    assert PB.slug("   ") == "kitap"


def test_title_from_filename_when_not_given():
    # dosya adından: sondaki dosya hâli sözcüğü («son») atılır, Türkçe başlık yazımı (editor.book_title)
    assert PB.title_of("", "anne_terligi-son.pdf") == "Anne Terligi"
    assert PB.title_of("", "1- todişin bir günü (2).pdf") == "Todişin Bir Günü"
    # kişinin yazdığı ad olduğu gibi (yalnız boşluk sadeleşir)
    assert PB.title_of("  Anne  Terliği ", "x.pdf") == "Anne Terliği"
    assert PB.title_of("küçük harfle yazdım", "x.pdf") == "küçük harfle yazdım"


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


def _row(status, attempt=1, workflow_id=None, jid="j1", hold=None):
    return {"id": jid, "status": status, "step": None, "workflow_id": workflow_id, "requested_by": "portal:ayse",
            "created_at": None, "finished_at": None, "attempt": attempt, "title": "Kitap", "page_count": 32,
            "submitted_at": None, "hold": hold}


@pytest.mark.parametrize("status,attempt,wf,state", [
    ("QUEUED", 1, None, "sirada"),
    ("QUEUED", 1, "book-analysis-j1", "okunuyor"),
    ("RUNNING", 1, "book-analysis-j1", "okunuyor"),
    ("SUCCEEDED", 2, "book-analysis-j1", "hazir"),
    ("FAILED", 1, "book-analysis-j1", "yeniden"),
    ("FAILED", PB.ATTEMPTS, "book-analysis-j1", "okunamadi"),
    ("CANCELLED", 1, "book-analysis-j1", "beklemede"),
    ("CANCELLED", 1, None, "beklemede"),
])
def test_item_state(status, attempt, wf, state):
    it = PB.item(_row(status, attempt, wf), [], 0)
    assert it["state"] == state
    assert it["failed"] == (state == "okunamadi")
    assert it["requested_by"] == "ayse"


def test_held_job_is_on_hold_not_unreadable():
    """Bilerek bekletilen iş (CANCELLED + progress.hold, ör. arşiv pilotu dışı) «beklemede»: hata değil, etiket satırda."""
    it = PB.item(_row("CANCELLED", hold="pilot-2026-10-02"), [], 0)
    assert it["state"] == "beklemede" and not it["failed"] and it["hold"] == "pilot-2026-10-02"
    assert PB.item(_row("FAILED", PB.ATTEMPTS), [], 0)["hold"] is None
    # satırda `hold` alanı hiç yoksa (eski sorgu) da düşmez
    r = _row("CANCELLED"); r.pop("hold")
    assert PB.item(r, [], 0)["state"] == "beklemede"


def test_item_counts_books_ahead_including_the_running_one():
    waiting = ["a", "j1", "b"]
    assert PB.item(_row("QUEUED"), waiting, busy=2)["ahead"] == 3
    assert PB.item(_row("QUEUED"), waiting, busy=1)["ahead"] == 2
    assert PB.item(_row("QUEUED"), waiting, busy=0)["ahead"] == 1
    assert PB.item(_row("RUNNING", workflow_id="w"), waiting, busy=1)["ahead"] is None


class _FakeDb:
    """`editor.db.one` yerine: SQL'in ilk sözcüklerine göre sabit cevaplar; eklenen işi kaydeder."""

    def __init__(self, job=None, busy=False, last=None, insert_ok=True):
        self.job, self.busy, self.last, self.insert_ok, self.inserted = job, busy, last, insert_ok, None

    def one(self, sql, *args):
        if sql.startswith("SELECT book_version_id, profile FROM analysis_job WHERE id="):
            return self.job
        if "status IN ('QUEUED','RUNNING') LIMIT 1" in sql:
            return {"x": 1} if self.busy else None
        if sql.startswith("SELECT id, status, progress"):
            return self.last
        if sql.startswith("INSERT INTO analysis_job"):
            self.inserted = args
            return {"id": "new-job"} if self.insert_ok else None
        raise AssertionError(sql)


def _use(monkeypatch, fake):
    # Veritabanı sürücüsü kurulu olmasa da (geliştirici makinesi) koşsun: `editor.db` yerine sahte modül.
    import sys
    import types
    import editor
    mod = types.ModuleType("editor.db")
    mod.one, mod.J = fake.one, (lambda v: v)
    monkeypatch.setitem(sys.modules, "editor.db", mod)
    monkeypatch.setattr(editor, "db", mod, raising=False)


def test_reread_opens_a_fresh_job_with_the_kept_fields(monkeypatch):
    fake = _FakeDb(job={"book_version_id": "bv1", "profile": "archive"},
                   last={"id": "old", "status": "FAILED",
                         "progress": {"attempt": 3, "archive": {"category": "Kurgu"}, "retry_of": "older", "error": "x"}})
    _use(monkeypatch, fake)
    out = PB.reread("old", "ayse")
    assert out == {"job_id": "new-job", "retry_of": "old"}
    bv, profile, who, progress, bv2 = fake.inserted
    assert (bv, profile, who, bv2) == ("bv1", "archive", "portal:ayse", "bv1")
    assert progress == {"archive": {"category": "Kurgu"}, "attempt": 1, "retry_of": "old", "manual_retry": True}


def test_reread_refuses_running_or_not_failed_and_unknown_job(monkeypatch):
    _use(monkeypatch, _FakeDb(job={"book_version_id": "bv1", "profile": "full"}, busy=True))
    with pytest.raises(PB.RereadRefused, match="sırada"):
        PB.reread("j", "ayse")
    _use(monkeypatch, _FakeDb(job={"book_version_id": "bv1", "profile": "full"},
                              last={"id": "j", "status": "SUCCEEDED", "progress": {}}))
    with pytest.raises(PB.RereadRefused, match="düşmüş değil"):
        PB.reread("j", "ayse")
    _use(monkeypatch, _FakeDb(job={"book_version_id": "bv1", "profile": "redaction"}))
    with pytest.raises(PB.RereadRefused):
        PB.reread("j", "ayse")
    _use(monkeypatch, _FakeDb(job=None))
    with pytest.raises(LookupError):
        PB.reread("j", "ayse")
    with pytest.raises(ValueError):
        PB.reread("j", " ")


def test_reread_second_click_does_not_add_a_second_job(monkeypatch):
    # Aynı anda gelen ikinci istek: koşullu ekleme satır döndürmez, kişiye «zaten sırada» gider.
    _use(monkeypatch, _FakeDb(job={"book_version_id": "bv1", "profile": "full"},
                              last={"id": "j", "status": "FAILED", "progress": {}}, insert_ok=False))
    with pytest.raises(PB.RereadRefused, match="sırada"):
        PB.reread("j", "ayse")
