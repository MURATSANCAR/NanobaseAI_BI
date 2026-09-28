"""M4 Çeviri — çevirmen eşleştirme önerisi (editorial_translation_match.py).

Sözleşme: adaylar M4 işlerindeki çevirmenler + «Çeviri» rolü olan aktif M8 kartları; her sinyal ayrı döner
(dil çifti kelimesi, MQM, zamanında teslim, açık yük/hız ya da boş saat, teslim günü izni); sıralama sözlük
sırası: müsait → dil çifti → yük sığar → MQM → zamanında teslim → açık yük. Bilinmeyen sinyal cezalandırmaz.
Kart e-postası rehberde bir portal kullanıcısınınkiyle aynıysa tek aday olur. Hiçbir tabloya yazılmaz.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
import sqlalchemy as sa

from semantic_bridge import editorial_translation as T
from semantic_bridge import editorial_translation_match as M
from semantic_bridge import freelance as F
from semantic_layer.store.catalog_store import open_store

TENANT = "timas"
# Pazartesi.
TODAY = date(2026, 9, 28)


def _at(d: date, hour: int = 12) -> datetime:
    return datetime(d.year, d.month, d.day, hour, tzinfo=timezone.utc)


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITORIAL_DIR", str(tmp_path))
    monkeypatch.setenv("FREELANCE_DIR", str(tmp_path / "fl"))
    e = open_store("sqlite://").engine
    T._ready.clear()
    F._ready.discard(id(e))
    T.ensure(e)
    F.ensure(e)
    return e


def _job(engine, translator, *, src="en", tgt="tr", segs=(("onaylandi", 100),), due=None, completed=None,
         name=None, errors=(), events=()):
    """Doğrudan satır yazar: `segs` (durum, kelime) listesi, `errors` ağırlık anahtarları, `events` (gün, kelime)."""
    jid = uuid.uuid4().hex
    with engine.begin() as c:
        c.execute(sa.insert(T.JOBS).values(
            id=jid, tenant_id=TENANT, title=f"Eser {jid[:4]}", source_lang=src, target_lang=tgt, translator=translator,
            translator_name=name, due_date=due, source_version=1 if segs else 0, draft_state="yok", draft_done=0,
            draft_total=0, created_by="editor", created_at=_at(TODAY - timedelta(days=60)),
            completed_at=_at(completed) if completed else None))
        seg_ids = []
        for i, (st, w) in enumerate(segs, 1):
            sid = uuid.uuid4().hex
            seg_ids.append(sid)
            c.execute(sa.insert(T.SEGMENTS).values(id=sid, job_id=jid, no=i, para=i, chapter=1, chapter_title="",
                                                   heading=False, source="x", target="", status=st, words=w))
        for sev in errors:
            c.execute(sa.insert(T.ERRORS).values(id=uuid.uuid4().hex, job_id=jid, segment_id=seg_ids[0], category="uslup",
                                                 severity=sev, created_by="mehmet", created_at=_at(TODAY)))
        for d, w in events:
            c.execute(sa.insert(T.EVENTS).values(id=uuid.uuid4().hex, job_id=jid, segment_id=seg_ids[0] if seg_ids else "-",
                                                 username=translator, action="cevrildi", words=w, at=_at(d)))
    return jid


def _person(engine, name, *, roles=("ceviri",), hours=20, **kw):
    return F.create_person(engine, TENANT, "editor", {"name": name, "roles": list(roles), "weeklyHours": hours, **kw})


def _names(res):
    return [c["name"] for c in res["items"]]


def _by(res, name):
    return next(c for c in res["items"] if c["name"] == name)


# ---------------------------------------------------------------------------------------------- sıralama ve sinyaller

def test_ranking_and_signals(engine):
    due = TODAY + timedelta(days=29)                       # 30 gün kaldı (bugün dahil)
    # Ayşe: EN→TR'de 1000 onaylı kelime, 10 küçük hata (MQM 99), zamanında bitmiş; açık işte 500 boş kelime; hızı 100/gün.
    _job(engine, "ayse", name="Ayşe Kaya", due=date(2026, 9, 1), completed=date(2026, 8, 30),
         errors=["kucuk"] * 10, segs=[("onaylandi", 1000)], events=[(date(2026, 8, 30), 1500), (date(2026, 9, 20), 1500)])
    _job(engine, "ayse", name="Ayşe Kaya", segs=[("bos", 300), ("taslak", 200), ("cevrildi", 50)])
    _job(engine, "ayse", segs=())                         # kaynağı yüklenmemiş iş
    # Mehmet: yalnız DE→TR; puanı daha yüksek ama çift uymuyor.
    _job(engine, "mehmet", name="Mehmet Can", src="de", segs=[("onaylandi", 2000)], due=date(2026, 9, 10),
         completed=date(2026, 9, 12))
    # Zeynep: EN→TR 300 kelime, 3 büyük hata → MQM 95.
    _job(engine, "zeynep", name="Zeynep Ak", segs=[("onaylandi", 300)], errors=["buyuk"] * 3)
    # M8: kartında İngilizce etiketi olan çevirmen, teslim gününde izinli çevirmen, pasif ve başka roldeki kişi.
    _person(engine, "Deniz Serbest", styles=["İngilizce edebiyat"], email="deniz@ornek.com")
    _person(engine, "Ece İzinli", styles=["ingilizce"],
            away=[{"from": (due - timedelta(days=2)).isoformat(), "to": (due + timedelta(days=3)).isoformat()}])
    p = _person(engine, "Pasif Kişi")
    F.update_person(engine, TENANT, "editor", p["id"], {"status": "pasif"})
    _person(engine, "Çizer Kişi", roles=("cizer",))

    res = M.match(engine, TENANT, "en", "tr", 1000, due.isoformat(), today=TODAY)

    assert _names(res) == ["Ayşe Kaya", "Zeynep Ak", "Deniz Serbest", "Mehmet Can", "Ece İzinli"]
    assert [c["rank"] for c in res["items"]] == [1, 2, 3, 4, 5] and res["total"] == 5
    assert res["order"].startswith("Sıralama:") and res["assumptions"]["wordsPerPage"] == 250

    a = _by(res, "Ayşe Kaya")
    assert a["source"] == "portal" and a["portalLogin"] and a["username"] == "ayse"
    s = a["signals"]
    assert s["pair"] == {"words": 1050, "jobs": 2, "tier": 2, "tag": None, "otherPairs": []}
    assert s["quality"] == {"mqm": 99.0, "reviewedWords": 1000, "penalty": 10, "scope": "cift"}
    assert s["onTime"] == {"onTime": 1, "total": 1, "rate": 1.0}
    # Açık yük: boş + taslak (500); çevrildi olan çevirmenin elinden çıkmıştır. Hız 3000 / 30 gün.
    assert s["load"]["openWords"] == 500 and s["load"]["openJobs"] == 1 and s["load"]["noSourceJobs"] == 1
    assert s["load"]["perDay"] == 100.0 and s["load"]["daysNeeded"] == 15 and s["load"]["daysLeft"] == 30
    assert s["load"]["fits"] is True and s["load"]["hours"] is None
    assert s["availability"] == {"awayOnDue": None, "ranges": []}
    assert {n["key"] for n in a["notes"]} >= {"dil-cifti", "acik-yuk", "inceleme-puani", "zamaninda-teslim"}

    m = _by(res, "Mehmet Can")["signals"]
    assert m["pair"]["tier"] == 0 and m["pair"]["otherPairs"] == ["de→tr"]
    assert m["quality"]["scope"] == "genel" and m["quality"]["mqm"] == 100.0
    assert m["onTime"] == {"onTime": 0, "total": 1, "rate": 0.0}
    # Hızı ölçülmemiş çevirmenin yükü «bilinmiyor»: aşağı itilmez.
    assert m["load"]["fits"] is None

    z = _by(res, "Zeynep Ak")["signals"]
    assert z["quality"]["mqm"] == 95.0 and z["onTime"]["rate"] is None

    d = _by(res, "Deniz Serbest")
    assert d["source"] == "serbest" and not d["portalLogin"] and d["username"] is None and d["personId"]
    ds = d["signals"]
    assert ds["pair"]["tier"] == 1 and ds["pair"]["tag"] == "İngilizce edebiyat"
    # 28 Eyl – 27 Eki: 22 iş günü × 4 saat = 88 saat boş; 1000 kelime = 4 sayfa × 1 saat.
    assert ds["load"]["hours"]["workdays"] == 22 and ds["load"]["hours"]["free"] == 88.0
    assert ds["load"]["hours"]["needed"] == 4.0 and ds["load"]["fits"] is True
    assert ds["quality"]["mqm"] is None

    e = _by(res, "Ece İzinli")["signals"]["availability"]
    assert e["awayOnDue"] is True and len(e["ranges"]) == 1
    assert _by(res, "Ece İzinli")["notes"][0]["tone"] == "uyari"


def test_load_that_does_not_fit_goes_down_and_own_job_is_excluded(engine):
    due = TODAY + timedelta(days=9)                        # 10 gün kaldı
    ev = [(TODAY - timedelta(days=29), 1500), (TODAY - timedelta(days=1), 1500)]
    _job(engine, "ali", name="Ali", segs=[("cevrildi", 800)], events=ev)
    open_job = _job(engine, "ali", name="Ali", segs=[("bos", 5000)])
    _job(engine, "veli", name="Veli", segs=[("cevrildi", 200)], events=ev)

    res = M.match(engine, TENANT, "en", "tr", 1000, due.isoformat(), today=TODAY)
    assert _names(res) == ["Veli", "Ali"]
    ali = _by(res, "Ali")["signals"]["load"]
    assert ali["openWords"] == 5000 and ali["daysNeeded"] == 60 and ali["fits"] is False
    assert _by(res, "Veli")["signals"]["load"]["fits"] is True
    assert next(n for n in _by(res, "Ali")["notes"] if n["key"] == "acik-yuk")["tone"] == "uyari"

    # Atanmakta olan iş Ali'nin açık işiyse kendi yükünden düşülür; eşitlikte çiftteki kelimesi çok olan önde.
    res = M.match(engine, TENANT, "en", "tr", 1000, due.isoformat(), exclude_job=open_job, today=TODAY)
    assert _names(res) == ["Ali", "Veli"]
    assert _by(res, "Ali")["signals"]["load"]["openWords"] == 0

    # Teslim tarihi yoksa yük «sığar mı» sorusu cevapsız kalır; kelime ve tarih boş da olabilir.
    res = M.match(engine, TENANT, "en", "tr", "", None, today=TODAY)
    assert {c["signals"]["load"]["fits"] for c in res["items"]} == {None}


def test_freelancer_capacity_window(engine):
    due = TODAY + timedelta(days=4)                        # Cuma: 5 iş günü
    p = _person(engine, "Kısıtlı Çevirmen", hours=10)
    pkg = F.create_package(engine, TENANT, "editor", {"title": "Başka çeviri", "role": "ceviri", "due": due.isoformat(),
                                                      "tasks": [{"title": "Bölüm 1", "units": 8, "effortHours": 8,
                                                                 "start": TODAY.isoformat()}]})
    task = F.get_package(engine, TENANT, pkg["id"])["tasks"][0]
    F.assign(engine, TENANT, "editor", [{"taskId": task["id"], "personId": p["id"]}])
    res = M.match(engine, TENANT, "en", "tr", 1000, due.isoformat(), today=TODAY)
    h = res["items"][0]["signals"]["load"]["hours"]
    assert (h["capacity"], h["busy"], h["free"], h["needed"], h["activeTasks"]) == (10.0, 8.0, 2.0, 4.0, 1)
    assert res["items"][0]["signals"]["load"]["fits"] is False
    # Aynı iş 400 kelime (1,6 saat) olsaydı sığardı.
    assert M.match(engine, TENANT, "en", "tr", 400, due.isoformat(), today=TODAY)["items"][0]["signals"]["load"]["fits"] is True


# ---------------------------------------------------------------------------------------------- birleştirme

def test_freelancer_card_linked_to_portal_user_by_email(engine):
    _job(engine, "ayse", name="Ayşe Kaya", segs=[("onaylandi", 400)], due=date(2026, 9, 1), completed=date(2026, 9, 3))
    p = _person(engine, "Ayşe Kaya (serbest)", email="Ayse@Timas.com.tr")
    pkg = F.create_package(engine, TENANT, "editor", {"title": "Eski çeviri", "role": "ceviri", "due": "2026-09-10",
                                                      "tasks": [{"title": "Tamamı", "units": 1}]})
    task = F.get_package(engine, TENANT, pkg["id"])["tasks"][0]
    with engine.begin() as c:
        c.execute(sa.update(F.TASKS).where(F.TASKS.c.id == task["id"]).values(
            person_id=p["id"], status="onaylandi", first_delivered_at=_at(date(2026, 9, 9))))

    calls = []

    def directory():
        calls.append(1)
        return {"ayse": "ayse@timas.com.tr", "baska": "x@y.z"}

    res = M.match(engine, TENANT, "en", "tr", 0, None, directory=directory, today=TODAY)
    assert len(calls) == 1 and res["total"] == 1
    c = res["items"][0]
    assert c["source"] == "ikisi" and c["username"] == "ayse" and c["personId"] == p["id"] and c["portalLogin"]
    # Portal işi geç (1 / 1 geç), serbest görev zamanında: toplam 1 / 2.
    assert c["signals"]["onTime"] == {"onTime": 1, "total": 2, "rate": 0.5}
    assert c["signals"]["load"]["hours"] is not None

    # Bağ yoksa (rehber okunamadı) iki ayrı aday, kaynak etiketiyle; öneri yine döner.
    def broken():
        raise RuntimeError("rehber kapalı")

    res = M.match(engine, TENANT, "en", "tr", 0, None, directory=broken, today=TODAY)
    assert sorted(c["source"] for c in res["items"]) == ["portal", "serbest"]


def test_directory_is_not_read_without_emailed_freelancers(engine):
    _job(engine, "ayse", segs=[("onaylandi", 10)])
    _person(engine, "E-postasız Çevirmen")
    calls = []
    M.match(engine, TENANT, "en", "tr", 0, None, directory=lambda: calls.append(1) or {}, today=TODAY)
    assert calls == []


# ---------------------------------------------------------------------------------------------- doğrulama ve erişim

def test_validation_and_no_writes(engine):
    with pytest.raises(T.TranslationError):
        M.match(engine, TENANT, "en", "en", 0, None, today=TODAY)
    with pytest.raises(T.TranslationError):
        M.match(engine, TENANT, "xx", "tr", 0, None, today=TODAY)
    with pytest.raises(T.TranslationError):
        M.match(engine, TENANT, "en", "tr", 0, "28.10.2026", today=TODAY)
    with pytest.raises(T.TranslationError):
        M.match(engine, TENANT, "en", "tr", "çok", None, today=TODAY)
    assert M.match(engine, TENANT, "en", "tr", 0, None, today=TODAY)["items"] == []
    _job(engine, "ayse")

    def snapshot():
        with engine.connect() as c:
            return [c.execute(sa.select(sa.func.count()).select_from(t)).scalar_one()
                    for t in (T.JOBS, T.SEGMENTS, T.ERRORS, T.EVENTS, F.PEOPLE, F.TASKS)]

    before = snapshot()
    M.match(engine, TENANT, "en", "tr", 100, None, today=TODAY)
    assert snapshot() == before
    # Başka kiracının işi görünmez.
    assert M.match(engine, "baska", "en", "tr", 0, None, today=TODAY)["items"] == []


def test_access_rule_for_match():
    from semantic_bridge import access as A
    assert A.rule_for("/api/v1/editorial/translation/match") == {"sayfa:ceviri", "sayfa:ceviri-masam"}
    assert A.features_for("GET", "/api/v1/editorial/translation/match") == []
