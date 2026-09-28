"""M4 Çeviri: segment birleştirme ve bölme (CAT araçlarındaki «merge / split»).

Cümle bölücü bazen yanlış böler («Oh dear! Oh dear! I shall be late!» üç segment olur) ya da bölmesi gereken
yerde bölmez. Çevirmen (ya da işi yöneten) bunu düzeltir:

- **Birleştir**: segment, aynı paragraftaki bir sonraki segmentle birleşir. Paragraf ve başlık sınırı aşılmaz
  (dışa aktarım paragrafı `para`'dan kurar). İlk segmentin kimliği kalır; kaynak ve dolu hedefler tek boşlukla
  birleşir; durum ikisinin düşüğüdür (boş < taslak < çevrildi < onaylı), onaylı ise «çevrildi»ye iner (birleşik
  metin yeniden incelenir); hedef doluysa durum «boş» kalmaz, «taslak» olur. İkinci segmentin inceleme hataları
  ilkine taşınır, ikinci satır silinir.
- **Böl**: segmentin kaynağı bir karakter konumundan ikiye ayrılır (aynı paragraf, aynı bölüm). Hedef ilk parçada
  kalır (çevirmen düzeltir), ikinci parça boş açılır. İlk parça onaylıysa «çevrildi»ye iner.
- Sıra numarası (`no`) işin tamamında bitişik tutulur: birleştirmede sonrakiler bir geri, bölmede bir ileri kayar.
- Eşzamanlılık: satırlar kilitlenir, istemcinin bildiği `updatedAt` (ve birleştirmede sonraki segmentin kimliği)
  tutmazsa 409. ZEKİ taslağı sürerken işin segmentleri değiştirilmez.
- Yeni kaynak sürümü (`upload_source`): paragrafın metni değişmediyse önceki sürümdeki bölünüşü korunur
  (`reuse_segmentation`); böylece birleştirilmiş/bölünmüş segmentin çevirisi normalleştirilmiş kaynakla eşleşip
  taşınır.

Yetki: işin çevirmeni ya da işi yöneten (`_roles(...)["translate"]`), `save_segment` ile aynı. Yazmalar köprüde
`semantic_audit`'e yazılır.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Optional

import sqlalchemy as sa

from semantic_bridge import editorial_translation as T

SEGMENTS, ERRORS, JOBS = T.SEGMENTS, T.ERRORS, T.JOBS
TranslationError = T.TranslationError

_RANK = {"bos": 0, "taslak": 1, "cevrildi": 2, "onaylandi": 3}
#: Kaydedilen hedefin üst sınırı `save_segment` ile aynı; birleşik segment de bunu aşamaz.
MAX_TARGET = 20000


def _check_can_edit(job: Any, user: str, see_all: bool) -> None:
    if not T._roles(job, user, see_all)["translate"]:
        raise TranslationError("Segmentleri yalnız işin çevirmeni ya da işi yöneten birleştirir/böler.", 403)
    if job.id in T._running or job.draft_state == "calisiyor":
        raise TranslationError("ZEKİ taslağı sürerken segmentler birleştirilemez ya da bölünemez.", 409)


def _check_fresh(s: Any, expected: Any) -> None:
    if expected and T._iso(s.updated_at) and expected != T._iso(s.updated_at):
        raise TranslationError(f"Segment bu arada {s.updated_by or 'başka biri'} tarafından değiştirildi; yeniden açın.", 409)


def _next(conn: sa.Connection, s: Any, lock: bool = False) -> Optional[Any]:
    q = (sa.select(SEGMENTS).where(SEGMENTS.c.job_id == s.job_id, SEGMENTS.c.no > s.no)
         .order_by(SEGMENTS.c.no).limit(1))
    return conn.execute(q.with_for_update() if lock else q).first()


def _merge_block(s: Any, n: Optional[Any]) -> Optional[str]:
    """Birleştirme neden yapılamaz (yapılabiliyorsa None)."""
    if s.heading:
        return "Başlık segmenti birleştirilmez."
    if n is None:
        return "Bu, işin son segmenti."
    if n.heading or n.para != s.para or n.chapter != s.chapter:
        return "Sonraki segment başka paragrafta; paragraflar birleştirilmez."
    return None


def _join(*parts: Optional[str]) -> str:
    return " ".join(p.strip() for p in parts if p and p.strip())


def next_segment(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, seg_id: str) -> dict[str, Any]:
    """Etkin segmentin işteki bir sonraki segmenti ve birleştirilip birleştirilemeyeceği (süzgeçten bağımsız)."""
    with engine.connect() as conn:
        s, job = T._segment(conn, tenant, seg_id, user, see_all)
        n = _next(conn, s)
    reason = _merge_block(s, n)
    return {
        "next": {"id": n.id, "no": n.no, "para": n.para, "source": n.source, "target": n.target or "", "status": n.status,
                 "updatedAt": T._iso(n.updated_at)} if n is not None else None,
        "mergeable": reason is None, "reason": reason,
    }


def merge_next(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, seg_id: str, body: dict[str, Any]) -> dict[str, Any]:
    with engine.begin() as conn:
        a, job = T._segment(conn, tenant, seg_id, user, see_all, lock=True)
        _check_can_edit(job, user, see_all)
        _check_fresh(a, body.get("updatedAt"))
        b = _next(conn, a, lock=True)
        if (reason := _merge_block(a, b)) is not None:
            raise TranslationError(reason, 409)
        if (want := body.get("nextId")) and want != b.id:
            raise TranslationError("Segment listesi bu arada değişti; yenileyip yeniden deneyin.", 409)
        _check_fresh(b, body.get("nextUpdatedAt"))
        source = _join(a.source, b.source)
        target = _join(a.target, b.target)
        if len(target) > MAX_TARGET:
            raise TranslationError("Birleşik segment çok uzun.")
        rank = min(_RANK.get(a.status, 0), _RANK.get(b.status, 0))
        status = {0: "bos", 1: "taslak", 2: "cevrildi", 3: "cevrildi"}[rank]
        if not target:
            status = "bos"
        elif status == "bos":
            status = "taslak"          # yarısı çevrilmiş segment boş sayılmaz
        now = T._now()
        v: dict[str, Any] = {
            "source": source, "words": T.word_count(source), "target": target, "status": status,
            # İki taslak da varsa birleşir; biri eksikse yarım taslak yanıltır, silinir (ZEKİ yeniden yazabilir).
            "draft": _join(a.draft, b.draft) if (a.draft or "").strip() and (b.draft or "").strip() else None,
            "submitted": target if status == "cevrildi" else None,
            "note": "\n".join(x.strip() for x in (a.note, b.note) if x and x.strip())[:2000] or None,
            "approved_by": None, "approved_at": None,
            "updated_by": user.lower(), "updated_at": now,
        }
        if status == "cevrildi":
            v["translated_by"] = a.translated_by or b.translated_by
            v["translated_at"] = a.translated_at or b.translated_at
        conn.execute(sa.update(SEGMENTS).where(SEGMENTS.c.id == a.id).values(**v))
        moved = conn.execute(sa.update(ERRORS).where(ERRORS.c.segment_id == b.id).values(segment_id=a.id)).rowcount
        conn.execute(sa.delete(SEGMENTS).where(SEGMENTS.c.id == b.id))
        conn.execute(sa.update(SEGMENTS).where(SEGMENTS.c.job_id == job.id, SEGMENTS.c.no > b.no)
                     .values(no=SEGMENTS.c.no - 1))
        T._sync_completed(conn, job.id)
        return {"id": a.id, "removed": b.id, "jobId": job.id, "source": source, "target": target, "status": status,
                "words": v["words"], "errorsMoved": int(moved or 0),
                "demoted": "onaylandi" in (a.status, b.status), "updatedAt": T._iso(now)}


def split_segment(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, seg_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """`at`: kaynakta bölme konumu (karakter; Unicode kod noktası). `source` gönderilirse sunucudakiyle aynı olmalı."""
    try:
        at = int(body.get("at"))
    except (TypeError, ValueError) as e:
        raise TranslationError("Bölme konumu geçersiz.") from e
    with engine.begin() as conn:
        s, job = T._segment(conn, tenant, seg_id, user, see_all, lock=True)
        _check_can_edit(job, user, see_all)
        _check_fresh(s, body.get("updatedAt"))
        if body.get("source") is not None and body["source"] != s.source:
            raise TranslationError("Segmentin kaynağı bu arada değişti; yeniden açın.", 409)
        if s.heading:
            raise TranslationError("Başlık segmenti bölünmez.", 409)
        left, right = s.source[:max(at, 0)].strip(), s.source[max(at, 0):].strip()
        if at <= 0 or at >= len(s.source) or not T.word_count(left) or not T.word_count(right):
            raise TranslationError("Segment bu konumdan bölünemez; iki parçada da en az bir kelime kalmalı.")
        status = "cevrildi" if s.status == "onaylandi" else s.status
        now = T._now()
        v: dict[str, Any] = {"source": left, "words": T.word_count(left), "status": status,
                             # Bütün cümlenin ZEKİ taslağı parçaya uymaz; ZEKİ parçaları yeniden yazabilir.
                             "draft": None, "updated_by": user.lower(), "updated_at": now}
        if s.status == "onaylandi":
            v.update(approved_by=None, approved_at=None)
        conn.execute(sa.update(SEGMENTS).where(SEGMENTS.c.job_id == job.id, SEGMENTS.c.no > s.no)
                     .values(no=SEGMENTS.c.no + 1))
        conn.execute(sa.update(SEGMENTS).where(SEGMENTS.c.id == s.id).values(**v))
        new_id = T._new()
        conn.execute(sa.insert(SEGMENTS).values(
            id=new_id, job_id=job.id, no=s.no + 1, para=s.para, chapter=s.chapter, chapter_title=s.chapter_title,
            heading=False, source=right, target="", draft=None, status="bos", words=T.word_count(right), submitted=None,
            note=None, translated_by=None, translated_at=None, approved_by=None, approved_at=None,
            updated_by=user.lower(), updated_at=now))
        T._sync_completed(conn, job.id)
        return {"id": s.id, "newId": new_id, "jobId": job.id, "source": left, "newSource": right, "status": status,
                "words": v["words"], "demoted": s.status == "onaylandi", "updatedAt": T._iso(now)}


def reuse_segmentation(conn: sa.Connection, job_id: str, segs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Yeni kaynak sürümünün segment listesi, önceki sürümdeki elle birleştirme/bölmeyi korur: metni birebir aynı
    kalan (boşluk dışında) paragrafın segmentleri önceki sürümdeki gibi bölünür. Metni değişen paragraf varsayılan
    bölücüyle gelir. Başlıklar tek segmenttir, dokunulmaz. `no` ve `words` yeniden hesaplanır."""
    old = conn.execute(sa.select(SEGMENTS.c.para, SEGMENTS.c.heading, SEGMENTS.c.source)
                       .where(SEGMENTS.c.job_id == job_id).order_by(SEGMENTS.c.no)).all()
    if not old:
        return segs
    by_para: dict[int, list[str]] = {}
    for para, heading, src in old:
        if not heading:
            by_para.setdefault(para, []).append(src)
    known: dict[str, list[list[str]]] = defaultdict(list)
    for srcs in by_para.values():
        known[" ".join(" ".join(srcs).split())].append(srcs)
    out: list[dict[str, Any]] = []
    i = 0
    while i < len(segs):
        s = segs[i]
        if s["heading"]:
            out.append(s)
            i += 1
            continue
        j = i
        while j < len(segs) and segs[j]["para"] == s["para"] and not segs[j]["heading"]:
            j += 1
        group = segs[i:j]
        cands = known.get(" ".join(" ".join(g["source"] for g in group).split()))
        prev = (cands.pop(0) if len(cands) > 1 else cands[0]) if cands else None
        if prev is not None and prev != [g["source"] for g in group]:
            group = [{"para": s["para"], "chapter": s["chapter"], "chapter_title": s["chapter_title"], "heading": False,
                      "source": src} for src in prev]
        out.extend(group)
        i = j
    for n, s in enumerate(out, 1):
        s["no"] = n
        s["words"] = T.word_count(s["source"])
    return out
