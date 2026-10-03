"""Arşiv kipi (editor.archive): görsel sayfa seçimi, ad anahtarı / kesik parça, toplu kuyruk planı (kuru koşu),
okur kitlesi ipucu, iş akışında arşivde koşmayan adımlar, yakın tekrar önerisinin ertelenmesi, kuyruk sırası.
Model ve veritabanı yok; iş akışı Temporal'ın zaman atlayan test sunucusunda sahte aktivitelerle koşar."""
from __future__ import annotations

import asyncio
import hashlib
import uuid
from collections.abc import Sequence
from pathlib import Path

import pymupdf
import pytest
from temporalio.common import RawValue

from editor import archive as A


# ------------------------------------------------------------------ görsel sayfa seçimi
def test_threshold_image_share_or_drawings():
    assert A.page_is_visual(0.05, 0) and A.page_is_visual(0.9, 0)
    assert A.page_is_visual(0.0, 40)
    assert not A.page_is_visual(0.049, 39)


def test_select_visual_keeps_the_cover_even_without_a_picture():
    ms = [(0.0, 0), (0.0, 3), (0.3, 0), (0.0, 120), (0.01, 10)]
    assert A.select_visual(ms) == [1, 3, 4]


def _png(w=200, h=200) -> bytes:
    pm = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, w, h), False)
    pm.clear_with(128)
    return pm.tobytes("png")


def _book(path: Path, kinds: list[str]) -> Path:
    """kinds: text | image | logo | drawing — 400×600 pt sayfalar."""
    doc = pymupdf.open()
    for k in kinds:
        p = doc.new_page(width=400, height=600)
        p.insert_text((40, 60), "Bir varmış bir yokmuş, evvel zaman içinde.", fontsize=11)
        if k == "image":
            p.insert_image(pymupdf.Rect(40, 100, 360, 400), stream=_png())       # %40
        elif k == "logo":
            p.insert_image(pymupdf.Rect(180, 540, 220, 580), stream=_png(20, 20))  # %0,7
        elif k == "drawing":
            for i in range(50):
                p.draw_line((40, 100 + 8 * i), (360, 104 + 8 * i))
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    return path


def test_visual_pages_skips_text_and_logo_pages(tmp_path, monkeypatch):
    from editor import document
    pdf = _book(tmp_path / "k.pdf", ["text", "text", "image", "logo", "drawing", "text"])
    monkeypatch.setattr(document, "_open_version", lambda bv, repair=True: (pymupdf.open(pdf), {}))
    out = A.visual_pages("bv")
    assert out["pages"] == [1, 3, 5]
    assert out["page_count"] == 6 and out["rule"] == {"image_share": 0.05, "min_drawings": 40, "cover": 1,
                                                      "layerless_ink": document.LAYERLESS_INK_MIN}


# ------------------------------------------------------------------ ad anahtarı, kesik parça, başlık
@pytest.mark.parametrize("a,b", [
    ("Cocuk/6-9_yas/3-mehmetakif_ozalit.pdf", "Cocuk/6-9_yas/mehmetakif-yeni (10).pdf"),
    ("Kurgu_Disi/kalbiminefendisi-3 Baskiozalit.pdf", "Kurgu_Disi/kalbiminefendisi baski.pdf"),
    ("Kurgu_Disi/bilimtarihisohbetleri-135x210-13f (7).pdf", "Kurgu_Disi/bilimtarihisohbetleri.pdf"),
    ("Cocuk/10-12_yas/Peygamber ve Cocuk tashih.pdf", "x/Peygamber ve Çocuk.pdf"),
])
def test_name_key_matches_the_same_book(a, b):
    assert A.name_key(a) == A.name_key(b) != ""


@pytest.mark.parametrize("a,b", [
    ("x/Kitap-2_BASKI (2).pdf", "x/Kitap-3_BASKI (2).pdf"),          # seri numarası ayrı kitap
    ("Kurgu_Disi/104-115 Kudüs_K47_12.pdf", "Kurgu_Disi/Kudüs.pdf"),  # dergi yazısı, kitap değil
])
def test_name_key_keeps_series_numbers_apart(a, b):
    assert A.name_key(a) != A.name_key(b)


def test_fragments_need_a_long_version_of_the_same_name():
    rows = [{"path": "a/3-mehmetakif_ozalit.pdf", "pages": 6}, {"path": "a/mehmetakif (2).pdf", "pages": 128},
            {"path": "a/herseyicintesekkurler (2).pdf", "pages": 8}, {"path": "a/herseyicintesekkurler.pdf", "pages": 18},
            {"path": "a/banyo baskı.pdf", "pages": 8},                    # kısa ama uzun sürümü yok: kitap
            {"path": "a/hz adem baski.pdf", "pages": 48}, {"path": "a/1-hz adem.pdf", "pages": 48}]
    fr = A.fragments(rows)
    assert set(fr) == {"a/3-mehmetakif_ozalit.pdf", "a/herseyicintesekkurler (2).pdf"}
    assert fr["a/3-mehmetakif_ozalit.pdf"] == {"path": "a/mehmetakif (2).pdf", "pages": 128}


@pytest.mark.parametrize("path,title", [
    ("Kurgu/BU BIZIM ANLASMAMIZ 15X21,5_BASKI (2).pdf", "BU BIZIM ANLASMAMIZ"),
    ("Kurgu_Disi/yazdiklariylayasayanlar-135x210-18f.pdf", "yazdiklariylayasayanlar"),
    ("Cocuk/0-5_yas/Merakli Kutu 3. Baskı İç.pdf", "Merakli Kutu"),
    ("Kurgu_Disi/Yirmi İki Mürekkep Damlası baski.pdf", "Yirmi İki Mürekkep Damlası"),
])
def test_clean_title(path, title):
    assert A.clean_title(path) == title


def test_category_hints_never_leave_the_reader_unknown():
    for cat in ("Cocuk/0-5_yas", "Cocuk/6-9_yas", "Cocuk/10-12_yas", "Cocuk/13+_yas", "Kurgu", "Kurgu_Disi"):
        assert A.hint_for(cat)["audience"] in ("CHILD", "YOUNG", "ADULT")
    assert A.hint_for("Cocuk/13+_yas")["audience"] == "YOUNG"
    assert A.hint_for("Kurgu")["forms"] == ["FICTION"]
    assert "FICTION" not in A.hint_for("Kurgu_Disi")["forms"]
    assert A.age_group(A.hint_for("Cocuk/6-9_yas")) == "6-9" and A.age_group(A.hint_for("Cocuk/13+_yas")) == "13+"
    assert A.hint_for("Baska")["audience"] is None


# ------------------------------------------------------------------ toplu kuyruk planı (kuru koşu)
def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_plan_dry_run_counts(tmp_path):
    root = tmp_path / "kitaplar"
    _book(root / "Cocuk/6-9_yas/masal.pdf", ["image", "text"] * 7)
    _book(root / "Cocuk/6-9_yas/3-masal_ozalit.pdf", ["image"])                       # kesik parça
    b = _book(root / "Kurgu/roman.pdf", ["text"] * 20)
    (root / "Kurgu/roman (2).pdf").write_bytes(b.read_bytes())                        # aynı sha: kopya
    c = _book(root / "Kurgu_Disi/deneme.pdf", ["text", "drawing"])
    (root / "notlar.json").write_text("{}")
    (root / "Kurgu/._roman.pdf").write_bytes(b"mac artigi")
    # ön tarama satırı olan dosya ölçülmez (sayılar satırdan); olmayan burada ölçülür
    pre = {"Kurgu_Disi/deneme.pdf": {"path": "Kurgu_Disi/deneme.pdf", "sha256": _sha(c), "pages": 2,
                                     "visual_pages": 1, "cover_visual": 0, "text_chars": 90, "bytes": 10}}
    p = A.plan(root, pre, known=lambda shas: {_sha(c): "SUCCEEDED"} if _sha(c) in shas else {})
    assert p["files"] == 5
    assert [r["path"] for r in p["take"]] == ["Cocuk/6-9_yas/masal.pdf", "Kurgu/roman (2).pdf"]
    sk = p["skipped"]
    assert [f["path"] for f in sk["fragment"]] == ["Cocuk/6-9_yas/3-masal_ozalit.pdf"]
    assert sk["duplicate"] == [{"path": "Kurgu/roman.pdf", "same_as": "Kurgu/roman (2).pdf"}]
    assert [f["path"] for f in sk["already"]] == ["Kurgu_Disi/deneme.pdf"]
    s = p["summary"]
    kid = s["by_category"]["Cocuk/6-9_yas"]
    assert (kid["books"], kid["pages"], kid["visual_pages"], kid["text_only_pages"], kid["audience"]) == \
        (1, 14, 7, 7, "CHILD")
    assert s["by_category"]["Kurgu"]["visual_pages"] == 1          # resimsiz kapak yine taranır
    assert s["total"]["books"] == 2 and s["skipped"] == {"duplicate": 1, "fragment": 1, "unreadable": 0, "already": 1}
    assert "TOPLAM" in A.report_text(p) and "kesik parça: Cocuk/6-9_yas/3-masal_ozalit.pdf" in A.report_text(p)


def test_cli_dry_run_writes_nothing(tmp_path, capsys, monkeypatch):
    root = tmp_path / "kitaplar"
    _book(root / "Kurgu/roman.pdf", ["text"] * 3)
    monkeypatch.setattr(A, "intake", lambda *a: pytest.fail("kuru koşu kitap almamalı"))
    assert A.main(["enqueue", "--root", str(root), "--dry-run", "--no-db"]) == 0
    out = capsys.readouterr().out
    assert "Kurgu" in out and "Kuru koşu: hiçbir şey yazılmadı." in out


def test_intake_rejects_paths_outside_the_root(tmp_path):
    with pytest.raises(FileNotFoundError):
        A.intake(tmp_path / "kok", {"path": "../disari.pdf", "category": "Kurgu"})


# ------------------------------------------------------------------ okur kitlesi: CRM yoksa arşiv rafı
def test_profile_uses_the_archive_shelf_when_crm_is_missing(monkeypatch):
    from editor import book_type as bt
    stored = {}

    def one(sql, *args):
        if sql.startswith("SELECT * FROM book_profile"):
            return stored.get("row")
        if "FROM generation g" in sql and "b.title" in sql:
            return {"book_id": "b1", "title": "masal", "book_version_id": "bv1"}
        if "FROM book_crm_record" in sql:
            return None
        if "FROM page" in sql:
            return {"n": 32, "drawn": 30}
        if sql.startswith("INSERT INTO book_profile"):
            keys = ("generation_id", "form", "form_source", "form_detail", "audience", "audience_source",
                    "age_from", "age_to", "illustrated_pages", "pages", "model_call_id")
            stored["row"] = dict(zip(keys, args))
            return {"generation_id": args[0]}
        raise AssertionError(sql)

    monkeypatch.setattr(bt.db, "one", one)
    monkeypatch.setattr(bt.db, "J", lambda v: v)        # öbür testler psycopg'u taklitle değiştirebilir
    monkeypatch.setattr(bt, "settings", lambda: type("S", (), {"min_illustration_ink": 0.02})())
    monkeypatch.setattr(bt, "_archive_hint", lambda gid: A.hint_for("Kurgu"))
    monkeypatch.setattr(bt, "_refresh_from_crm", lambda row: None)
    monkeypatch.setattr(bt, "_not_a_book_of", lambda gid, n: None)    # kitap (katalog kuralı sayfa okur)
    row = asyncio.run(bt.profile("g1"))
    assert (row["audience"], row["audience_source"], row["form"], row["form_source"]) == \
        ("ADULT", "ARCHIVE", "FICTION", "ARCHIVE")
    stored.clear()

    async def model_form(gid, title, genres, candidates):
        assert candidates == ["NARRATIVE_NONFICTION", "EXPOSITORY", "ACTIVITY", "POETRY"]
        return {"form": "EXPOSITORY", "model_call_id": 7}

    monkeypatch.setattr(bt, "_archive_hint", lambda gid: {**A.hint_for("Cocuk/6-9_yas"), "forms": A.hint_for("Kurgu_Disi")["forms"]})
    monkeypatch.setattr(bt, "_model_form", model_form)
    row = asyncio.run(bt.profile("g1"))
    assert (row["audience"], row["age_from"], row["age_to"], row["form"]) == ("CHILD", 6, 9, "EXPOSITORY")


# ------------------------------------------------------------------ iş akışı: hangi adım koşar
REDACTION_ONLY = {"proofreading", "confirm_text_visual", "continuity_checks", "detect_contradictions",
                  "queue_contradictions"}


def _run_workflow(profile: str):
    testing = pytest.importorskip("temporalio.testing")
    from temporalio import activity
    from temporalio.worker import Worker
    from editor.workflow.workflows import BookFullAnalysis
    calls: list[tuple[str, list]] = []
    results = {
        "prepare_generation": lambda job: {"generation_id": "g1", "book_version_id": "bv1", "profile": profile},
        "page_manifest": lambda bv: {"page_count": 6, "needs_ocr": [2]},
        "archive_visual_pages": lambda bv: {"pages": [1, 3, 5]},
        "scan_page_fast": lambda gid, p: {"page_no": p, "uncertain": p in (3, 5)},
        "confirm_text_visual": lambda gid: {"pages": 0, "proposed": 0, "confirmed": 0, "confirmed_pages": [],
                                            "pages_failed": []},
        "text_chunks": lambda gid: [[1, 6]],
        "resolve_identity": lambda gid: {"characters": 1},
        "narrative_roles": lambda gid: {"pages": [2, 3]},
        "rebuild_outputs": lambda gid: {"technical_status": "SUCCEEDED"},
        "archive_outputs": lambda gid: {"technical_status": "SUCCEEDED"},
        "detect_contradictions": lambda gid: {"found": 0},
        "queue_contradictions": lambda gid: {"queued": 0},
    }

    @activity.defn(dynamic=True)
    async def fake(args: Sequence[RawValue]) -> dict:
        name = activity.info().activity_type
        vals = [activity.payload_converter().from_payload(a.payload) for a in args]
        calls.append((name, vals))
        fn = results.get(name)
        return fn(*vals) if fn else {}

    async def main():
        try:
            env = await testing.WorkflowEnvironment.start_time_skipping()
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"Temporal test sunucusu yok: {e}")
        async with env, Worker(env.client, task_queue="t", workflows=[BookFullAnalysis], activities=[fake]):
            wid = f"wf-{uuid.uuid4().hex}"
            out = await env.client.execute_workflow("BookFullAnalysis", "job1", id=wid, task_queue="t")
            hist = await env.client.get_workflow_handle(wid).fetch_history()
            # patch işaretleri (workflow.patched): marker olaylarının ayrıntı yüklerinde
            marks = []
            for ev in hist.events:
                if ev.HasField("marker_recorded_event_attributes"):
                    for p in ev.marker_recorded_event_attributes.details.values():
                        marks += [x.data.decode("utf-8", "replace") for x in p.payloads]
            return out, " ".join(marks)
    out, hist = asyncio.run(main())
    return out, calls, hist


def _names(calls):
    return [n for n, _ in calls]


def test_archive_workflow_leaves_redaction_out_and_scans_only_pictures():
    out, calls, hist = _run_workflow("archive")
    names = set(_names(calls))
    assert not names & REDACTION_ONLY and "rebuild_outputs" not in names
    assert {"archive_visual_pages", "archive_outputs", "ocr_page", "extract_chunk", "resolve_identity",
            "verify_modality", "merge_events", "narrative_roles", "visual_identity", "emotions_themes",
            "book_metadata"} <= names
    assert sorted(v[1] for n, v in calls if n == "scan_page_fast") == [1, 3, 5]
    assert sorted(v[1] for n, v in calls if n == "scan_page_deep") == [3, 5]
    assert [v[1] for n, v in calls if n == "scan_page_deep_key"] == [3]          # 2 düz metin sayfası
    assert out["profile"] == "archive" and out["visual_pages"] == 3 and set(out["deferred"]) == REDACTION_ONLY
    assert "archive-profile-v1" in hist and "full-recommend-v1" not in hist
    assert [v for n, v in calls if n == "finish_job"][-1][1] == "SUCCEEDED"


def test_full_workflow_is_unchanged():
    out, calls, hist = _run_workflow("full")
    names = set(_names(calls))
    assert {"proofreading", "confirm_text_visual", "continuity_checks", "rebuild_outputs"} <= names
    assert not {"archive_visual_pages", "archive_outputs"} & names
    assert sorted(v[1] for n, v in calls if n == "scan_page_fast") == [1, 2, 3, 4, 5, 6]
    assert sorted(v[1] for n, v in calls if n == "scan_page_deep_key") == [2, 3]
    assert "profile" not in out
    # normal kipte yeni işaret alınmaz: eski geçmişlerle aynı komut dizisi
    assert "archive-profile-v1" not in hist and "redaction-profile-v1" not in hist
    # kategori/yaş önerisi tam okumada da, kendi işaretiyle (2026-10-03)
    assert "full-recommend-v1" in hist and "archive-recommend-v1" not in hist
    assert names & {"archive_recommend"} and _names(calls).index("rebuild_outputs") < _names(calls).index(
        "archive_recommend")


def test_redaction_workflow_runs_what_the_archive_left_out():
    out, calls, hist = _run_workflow("redaction")
    names = _names(calls)
    assert REDACTION_ONLY <= set(names) and "rebuild_outputs" in names
    assert not {"page_manifest", "text_layer", "scan_page_fast", "extract_chunk", "archive_outputs"} & set(names)
    assert names.index("queue_contradictions") < names.index("rebuild_outputs")
    assert out["profile"] == "redaction" and "redaction-profile-v1" in hist


# ------------------------------------------------------------------ yakın tekrar önerisi: editör açınca
def test_word_alternatives_are_deferred_by_default():
    from editor.proofing import word_variety as WV
    assert WV.ALTERNATIVES_AT_READ is False


def test_fill_alternatives_fills_deferred_findings(monkeypatch):
    from editor.proofing import word_variety as WV
    rows = [{"id": "f1", "page_no": 4, "details": {"lemma": "göz", "sense": "organ", "passage_marked": "[[göz]] … [[gözü]]",
                                                 "forms": ["göz", "gözü"], "alternatives": "deferred"}},
            {"id": "f2", "page_no": 9, "details": {"lemma": "yol", "sense": "", "passage_marked": "x",
                                                 "forms": ["yol", "yolu"], "alternatives": "deferred"}}]
    seen, stored = [], {}
    monkeypatch.setattr(WV, "_deferred", lambda gid, ids: rows if ids is None else [r for r in rows if r["id"] in ids])
    monkeypatch.setattr(WV, "_store", lambda fid, alts: stored.__setitem__(fid, alts))
    monkeypatch.setattr(WV.T, "lexicon", lambda: object())
    monkeypatch.setattr(WV, "Llm", lambda gid: object())
    monkeypatch.setattr(WV.D, "llm_gid", lambda gid: gid)

    async def alts(llm, lex, lemma, sense, marked, page, forms):
        seen.append((lemma, sense, page, forms))
        if lemma == "yol":
            raise WV.ModelError("düştü")
        return ["bakış"]

    monkeypatch.setattr(WV, "_alternatives", alts)
    res = asyncio.run(WV.fill_alternatives("g1"))
    assert res == {"filled": 1, "failed": 1, "pending": 1}
    assert stored == {"f1": ["bakış"]}
    assert seen[0] == ("göz", {"label": "organ"}, 4, ["göz", "gözü"]) and seen[1][1] is None
    assert asyncio.run(WV.fill_alternatives("g1", ["f9"])) == {"filled": 0, "failed": 0, "pending": 0}


# ------------------------------------------------------------------ kuyruk: arşiv portalı bekletmez
def test_retry_keeps_the_profile_and_its_data(monkeypatch):
    from editor import portal_books as PB
    inserted = []
    monkeypatch.setattr(PB, "ATTEMPTS", 3)
    import editor.db as db
    monkeypatch.setattr(db, "all_rows", lambda sql, *a: [
        {"id": "j1", "book_version_id": "bv", "requested_by": "arsiv:Kurgu", "profile": "archive", "attempt": 1,
         "progress": {"attempt": 1, "archive": {"category": "Kurgu"}, "result": {"error": "x"}}}])
    monkeypatch.setattr(db, "one", lambda sql, *a: inserted.append((sql, a)) or {"id": "j2"})
    monkeypatch.setattr(db, "J", lambda v: v)
    assert PB.retry_failed() == 1
    sql, (bv, profile, who, progress) = inserted[0]
    assert (profile, who) == ("archive", "arsiv:Kurgu")
    assert progress == {"archive": {"category": "Kurgu"}, "attempt": 2, "retry_of": "j1"}


def test_queue_order_puts_portal_books_before_the_archive():
    """Toplu arşiv (`arsiv:` önekli) sona; portaldan gelen kitap — Kitap Eczanesi'nden arşiv kipinde yüklenen de —
    önde. Sorgu parametreli koştuğu için LIKE'taki yüzde işareti kaçışlı."""
    from editor import portal_books as PB
    assert PB.QUEUE_ORDER.startswith("(requested_by LIKE 'arsiv:%%')")


def test_portal_upload_profile_settings():
    from editor import portal_books as PB
    assert PB.job_settings("", "") == ("full", {"attempt": 1})
    prof, prog = PB.job_settings("archive", "Cocuk/6-9_yas")
    assert prof == "archive"
    assert prog["archive"]["category"] == "Cocuk/6-9_yas" and prog["archive"]["audience"] == "CHILD"
    assert prog["archive"]["age_from"] == 6 and prog["archive"]["source"] == "portal"
    # kategorisiz arşiv kitabı: ipucu boş, okur kitlesini metin belirler
    prof, prog = PB.job_settings("ARCHIVE", "../etc")
    assert prof == "archive" and prog["archive"]["category"] is None and prog["archive"]["audience"] is None
    with pytest.raises(PB.UploadError):
        PB.job_settings("redaction", "")


# ------------------------------------------------------------------ Kitap Eczanesi listesi (saf parçalar)
def _job(book, title, profile, status, *, jid=None, cat=None, who="arsiv:Kurgu", wf=None, at="2026-10-01T10:00:00+00:00",
         attempt=1, done=None):
    import datetime as dt
    t = dt.datetime.fromisoformat(at)
    return {"book_id": uuid.UUID(book), "title": title, "id": jid or uuid.uuid4(), "profile": profile, "status": status,
            "step": None, "workflow_id": wf, "requested_by": who, "created_at": t, "submitted_at": t,
            "finished_at": dt.datetime.fromisoformat(done) if done else None, "attempt": attempt, "category": cat,
            "page_count": 120}


B1, B2, B3 = (str(uuid.UUID(int=i)) for i in (1, 2, 3))


def _books():
    q = uuid.UUID(int=99)
    rows = [
        _job(B1, "Çalıkuşu", "archive", "SUCCEEDED", cat="Kurgu", done="2026-10-01T12:00:00+00:00"),
        _job(B1, "Çalıkuşu", "redaction", "RUNNING", who="portal:ayse", wf="w1", at="2026-10-02T09:00:00+00:00"),
        _job(B2, "İnce Memed", "archive", "QUEUED", jid=q, cat="Kurgu"),
        _job(B3, "Uyku Masalı", "archive", "FAILED", cat="Cocuk/0-5_yas", who="portal:mehmet", attempt=99),
    ]
    return A.shape(rows, {B1}, [str(q)], busy=1)


def test_shape_one_row_per_book_with_read_and_redaction():
    by = {b["id"]: b for b in _books()}
    b1 = by[B1]
    assert b1["read"]["state"] == "hazir" and b1["redaction"]["state"] == "okunuyor" and b1["proofed"]
    assert b1["bulk"] and b1["read"]["requested_by"] is None and b1["redaction"]["requested_by"] == "ayse"
    assert b1["category"] == "Kurgu"
    # sıradaki ilk iş + süren bir okuma = önünde 1 iş
    assert by[B2]["read"]["state"] == "sirada" and by[B2]["read"]["ahead"] == 1 and by[B2]["redaction"] is None
    assert by[B3]["read"]["state"] == "okunamadi" and not by[B3]["bulk"] and by[B3]["read"]["requested_by"] == "mehmet"


def test_select_search_is_turkish_and_case_insensitive():
    books = _books()
    assert [b["id"] for b in A.select(books, q="CALIKUSU")["items"]] == [B1]
    assert [b["id"] for b in A.select(books, q="ince")["items"]] == [B2]
    assert A.select(books, q="yok")["total"] == 0


def test_select_filters_facets_and_pages():
    books = _books()
    out = A.select(books)
    assert out["total"] == 3 and out["all"] == 3
    assert out["facets"]["categories"] == {"Kurgu": 2, "Cocuk/0-5_yas": 1}
    assert out["facets"]["states"] == {"hazir": 1, "sirada": 1, "okunamadi": 1, "redaksiyon": 1}
    assert [b["id"] for b in out["items"]] == [B1, B2, B3]     # ada göre (Türkçe harf katlanır)
    assert [b["id"] for b in A.select(books, category="Kurgu", state="sirada")["items"]] == [B2]
    assert [b["id"] for b in A.select(books, state="redaksiyon")["items"]] == [B1]
    assert A.select(books, category="Kurgu")["facets"]["states"] == {"hazir": 1, "sirada": 1, "redaksiyon": 1}
    page = A.select(books, offset=1, limit=1)
    assert [b["id"] for b in page["items"]] == [B2] and page["total"] == 3
    assert [b["id"] for b in A.select(books, sort="recent")["items"]][0] == B1


def test_select_uncategorised_filter():
    import copy
    books = copy.deepcopy(_books())
    books[0]["category"] = None
    out = A.select(books, category="-")
    assert [b["id"] for b in out["items"]] == [books[0]["id"]]
    assert out["facets"]["categories"][""] == 1
