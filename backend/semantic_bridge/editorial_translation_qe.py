"""M4 Çeviri: ZEKİ kalite tahmini (segment kalite puanları). Bir TAHMİNDİR; MQM inceleme puanı değildir.

Çevrilmiş (çevrildi / onaylandı) her segment, kaynağıyla birlikte ~250 kelimelik parçalar hâlinde modele sorulur
(LLM kapısından, çağıranın verdiği `chat` ile). Model her öğe için 0–100 arası tek puan verir (yeterlik + akıcılık);
puan 85'in altındaysa MQM kategorisini (anlam, eksik, terim, dilbilgisi, yazim, uslup, bicim), çeviriden birebir
alıntıyı ve tek cümlelik Türkçe gerekçeyi yazar.

- **Kanıt kuralı:** alıntı hedef metinde birebir (boşluk farkı dışında) geçmiyorsa gerekçe ve alıntı atılır, puan
  kalır. Alıntı alanı yoksa gerekçedeki «…» / “…” / "…" alıntılarından en az biri hedefte geçmelidir.
- **Eskime:** puanla birlikte kaynak+hedef metnin özeti (`target_hash`) saklanır. Hedef sonradan değiştiyse puan
  «eski» gösterilir, şüpheli süzgecine girmez ve bir sonraki çalıştırmada yeniden puanlanır.
- Ağırlık puandan türetilir (modelden istenmez): 85 altı küçük, 70 altı büyük, 50 altı kritik.
- Kayıtlar yeni tablolarda (`semantic_translation_qe`, `semantic_translation_qe_runs`); mevcut çeviri tablolarına
  sütun eklenmez. Silinen iş/segmentin artık puanları süreç açılışında ve her çalıştırmada temizlenir.
- Yetki: sayfa (`sayfa:ceviri` / `sayfa:ceviri-masam`) + işteki rol. Model harcayan başlatma işin inceleyenine,
  işi açana / «Masam: herkesin işi» yetkilisine ya da `ozellik:ceviri.yonet` sahibine açıktır (ucun içinde).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import unicodedata
from collections import defaultdict
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

from semantic_bridge import editorial_translation as T

log = logging.getLogger("semantic.editorial_translation_qe")
_md = sa.MetaData()

QE = sa.Table(
    "semantic_translation_qe", _md,
    sa.Column("segment_id", sa.String(32), primary_key=True),
    sa.Column("job_id", sa.String(32), nullable=False, index=True),
    sa.Column("score", sa.Integer, nullable=False),               # 0–100
    sa.Column("category", sa.String(20)),                          # T.CATEGORIES anahtarı; puan < 85 ise
    sa.Column("severity", sa.String(10)),                          # kucuk | buyuk | kritik (puandan)
    sa.Column("reason", sa.Text),                                  # kanıtı tutan tek cümle
    sa.Column("span", sa.Text),                                    # hedeften birebir alıntı
    sa.Column("target_hash", sa.String(64), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)
RUNS = sa.Table(
    "semantic_translation_qe_runs", _md,
    sa.Column("job_id", sa.String(32), primary_key=True),
    sa.Column("state", sa.String(20), nullable=False, default="yok"),   # yok | calisiyor | bitti | hata
    sa.Column("note", sa.String(500)),
    sa.Column("done", sa.Integer, nullable=False, default=0),
    sa.Column("total", sa.Integer, nullable=False, default=0),
    sa.Column("chapter", sa.Integer),
    sa.Column("started_by", sa.String(120)),
    sa.Column("started_at", sa.DateTime(timezone=True)),
    sa.Column("finished_at", sa.DateTime(timezone=True)),
)

#: Bu puanın altı «ZEKİ şüpheli». Kategori/gerekçe yalnız bunun altında istenir.
SUSPECT_BELOW = 85
#: Puan kovaları (dağılım): alt sınır, etiket. Ağırlık eşikleriyle aynı.
BUCKETS: tuple[tuple[int, int, str], ...] = ((85, 100, "85–100"), (70, 84, "70–84"), (50, 69, "50–69"), (0, 49, "0–49"))

_ready: set[int] = set()
_lock = threading.Lock()
_running: set[str] = set()


def ensure(engine: sa.engine.Engine) -> None:
    """Tabloları açar; süreçteki ilk çağrıda yarıda kalan çalıştırmayı «hata»ya çeker ve silinmiş işlerin artık
    kayıtlarını temizler."""
    with _lock:
        if id(engine) in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        with engine.begin() as conn:
            conn.execute(sa.update(RUNS).where(RUNS.c.state == "calisiyor").values(
                state="hata", note="Servis yeniden başladı; kalan segmentler için tahmini yeniden başlatın."))
            jobs = sa.select(T.JOBS.c.id)
            conn.execute(sa.delete(QE).where(QE.c.job_id.notin_(jobs)))
            conn.execute(sa.delete(RUNS).where(RUNS.c.job_id.notin_(jobs)))
        _ready.add(id(engine))


def qe_hash(source: str, target: str) -> str:
    """Puanın hangi metne verildiği: kaynak + hedef (boşluklar sadeleştirilmiş)."""
    norm = lambda s: " ".join((s or "").split())   # noqa: E731
    return hashlib.sha256(f"{norm(source)}\x00{norm(target)}".encode("utf-8")).hexdigest()


def severity_of(score: int) -> Optional[str]:
    if score >= SUSPECT_BELOW:
        return None
    if score < 50:
        return "kritik"
    if score < 70:
        return "buyuk"
    return "kucuk"


# ============================================================================================ model

QE_SYSTEM = (
    "Sen deneyimli bir çeviri kalite değerlendiricisisin. {src} kaynaktan {tgt} diline yapılmış bir kitap çevirisinden "
    "numaralı öğeler okuyacaksın; her öğede numara («n»), kaynak («k») ve çeviri («c») var. Her çeviriyi yalnız kendi "
    "kaynağıyla karşılaştır ve 0–100 arası tek bir tam sayı puan ver. Puan iki şeyi birlikte ölçer: anlamın eksiksiz ve "
    "doğru aktarılması (yeterlik) ve {tgt} dilinde doğal, kurallı akış (akıcılık).\n"
    "Ölçek: 95–100 kusursuz; 85–94 yayına uygun, en çok zevk meselesi; 70–84 küçük ama gerçek bir sorun; 50–69 belirgin "
    "hata (anlam kayması, dil bilgisi, yanlış terim); 50'nin altı ağır anlam hatası ya da çevrilmemiş/eksik bölüm.\n"
    "Puan 85'in altındaysa en önemli sorunu şu kategorilerden biriyle adlandır: anlam (anlam hatası ya da kayması), "
    "eksik (eksik çeviri ya da kaynakta olmayan ekleme), terim («terimler» listesine uymayan karşılık dahil), "
    "dilbilgisi, yazim (yazım ve noktalama), uslup, bicim. «alinti» alanına sorunlu bölümü çeviriden («c») harfi harfine, "
    "hiç değiştirmeden kopyala; «gerekce» alanına sorunu tek bir Türkçe cümleyle yaz.\n"
    "Doğru olan farklı bir çeviri seçeneğini ya da üslup tercihini hata sayma; emin değilsen yüksek puan ver. "
    "Her numara için tam bir öğe döndür. Cevabın yalnız bir JSON dizisi olsun, başka hiçbir şey yazma: "
    '[{{"n": <numara>, "puan": <0-100>, "kategori": "<kategori>", "alinti": "<çeviriden birebir>", '
    '"gerekce": "<tek cümle>"}}]. Puan 85 ve üstündeyse yalnız «n» ve «puan» yaz.'
)

_QUOTE = re.compile(r"«([^»]+)»|“([^”]+)”|\"([^\"]+)\"|‘([^’]+)’")
_CAT_ALIAS = {"dil bilgisi": "dilbilgisi", "yazım": "yazim", "noktalama": "yazim", "üslup": "uslup", "biçim": "bicim",
              "eksik / fazla": "eksik", "fazla": "eksik", "ekleme": "eksik", "anlam hatası": "anlam"}


def _cat(v: Any) -> Optional[str]:
    s = " ".join(T.fold(str(v or "")).split())
    if not s:
        return None
    s = _CAT_ALIAS.get(s, s)
    flat = "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch)).replace("ı", "i")
    flat = flat.replace(" ", "")
    return flat if flat in T.CATEGORIES else None


def _score(v: Any) -> Optional[int]:
    """0–100 tam sayı; aralık dışı ya da sayı olmayan puan geçersizdir (kırpılmaz)."""
    if isinstance(v, bool):
        return None
    try:
        x = float(str(v).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    if x != x or x < 0 or x > 100:
        return None
    return int(round(x))


def _clean_span(s: str) -> str:
    return " ".join(s.split()).strip().strip("«»“”\"'‘’").strip()


def in_target(span: str, target: str) -> bool:
    """Kanıt: alıntı hedefte birebir geçiyor mu (yalnız boşluk farkı hoş görülür; büyük/küçük harf farkı değil)."""
    s = _clean_span(span or "")
    return bool(s) and s in " ".join((target or "").split())


def parse_qe(answer: str, targets: dict[int, str]) -> dict[int, dict[str, Any]]:
    """Modelin cevabı → {numara: {score, category, severity, reason, span}}. Numarası bilinmeyen, puanı geçersiz öğe
    atılır; aynı numara ikinci kez gelirse ilki geçer. Kanıt kuralı burada uygulanır."""
    m = re.search(r"\[.*\]", answer or "", re.S)
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return {}
    out: dict[int, dict[str, Any]] = {}
    for d in data if isinstance(data, list) else []:
        if not isinstance(d, dict):
            continue
        try:
            n = int(d.get("n"))
        except (TypeError, ValueError):
            continue
        if n not in targets or n in out:
            continue
        score = _score(d.get("puan", d.get("score")))
        if score is None:
            continue
        item: dict[str, Any] = {"score": score, "category": None, "severity": severity_of(score), "reason": None, "span": None}
        if score < SUSPECT_BELOW:
            item["category"] = _cat(d.get("kategori", d.get("category")))
            reason = " ".join(str(d.get("gerekce") or d.get("reason") or "").split()) or None
            quote = d.get("alinti", d.get("span"))
            target = targets[n]
            if isinstance(quote, str) and quote.strip():
                span = _clean_span(quote) if in_target(quote, target) else None
            else:
                # Alıntı alanı yoksa gerekçedeki tırnak içlerinden hedefte geçen ilki kanıttır.
                found = [next(g for g in q.groups() if g) for q in _QUOTE.finditer(reason or "")]
                span = next((_clean_span(q) for q in found if in_target(q, target)), None)
            if span:
                item["span"], item["reason"] = span, reason
        out[n] = item
    return out


def score_segments(rows: list[Any], chat: Callable[[list[dict[str, str]]], str], index: "T.TermIndex", *,
                   title: str, src: str, tgt: str, progress: Callable[[int], None] = lambda n: None,
                   save: Callable[[dict[str, dict[str, Any]]], None] = lambda d: None) -> dict[str, int]:
    """Segmentleri parça parça puanlar; her parçanın sonucunu `save`e verir (kimlik → kayıt). Veritabanına yazmaz.
    Döner: {"scored", "missed", "suspect", "evidence_dropped"}."""
    names = {"src": T.LANGS.get(src, src), "tgt": T.LANGS.get(tgt, tgt)}
    system = QE_SYSTEM.format(**names)
    stats = {"scored": 0, "missed": 0, "suspect": 0, "evidence_dropped": 0}
    step = 0
    for batch in T._batches(rows):
        used: dict[str, str] = {}
        for r in batch:
            for t, _, _ in index.find(r.source):
                if t.status == "onayli" and t.target_term:
                    used[t.source_term] = t.target_term.split("|")[0].strip()
        payload = {"eser": title, "terimler": [{"kaynak": k, "hedef": v} for k, v in used.items()],
                   "ogeler": [{"n": i, "k": r.source, "c": r.target} for i, r in enumerate(batch, 1)]}
        answer = chat([{"role": "system", "content": system},
                       {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}])
        got = parse_qe(answer, {i: r.target for i, r in enumerate(batch, 1)})
        results: dict[str, dict[str, Any]] = {}
        for i, r in enumerate(batch, 1):
            it = got.get(i)
            if it is None:
                stats["missed"] += 1
                continue
            stats["scored"] += 1
            if it["score"] < SUSPECT_BELOW:
                stats["suspect"] += 1
                if it["reason"] is None:
                    stats["evidence_dropped"] += 1
            results[r.id] = {**it, "hash": qe_hash(r.source, r.target)}
        save(results)
        step += len(batch)
        progress(step)
    return stats


# ============================================================================================ çalıştırma

def _run_row(conn: sa.Connection, job_id: str) -> Any:
    return conn.execute(sa.select(RUNS).where(RUNS.c.job_id == job_id)).first()


def _candidates(conn: sa.Connection, job_id: str, chapter: Optional[int] = None) -> list[Any]:
    """Tahmine giren segmentler: çevrildi ya da onaylı, hedefi boş olmayan."""
    q = sa.select(T.SEGMENTS).where(T.SEGMENTS.c.job_id == job_id, T.SEGMENTS.c.status.in_(T.DONE))
    if chapter is not None:
        q = q.where(T.SEGMENTS.c.chapter == int(chapter))
    return [r for r in conn.execute(q.order_by(T.SEGMENTS.c.no)).all() if (r.target or "").strip()]


def may_run(job: Any, user: str, see_all: bool, can_manage: bool) -> bool:
    """Model harcayan başlatma: işin inceleyeni, işi açan / herkesin işini gören ya da çeviri işi yöneticisi."""
    return T._roles(job, user, see_all)["review"] or can_manage


def start_qe(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, job_id: str, body: dict[str, Any],
             chat: Optional[Callable[[list[dict[str, str]]], str]], can_manage: bool) -> dict[str, Any]:
    if chat is None:
        raise T.TranslationError("Model bağlantısı tanımlı değil.", 503)
    chapter = body.get("chapter")
    try:
        chapter = int(chapter) if chapter not in (None, "") else None
    except (TypeError, ValueError) as e:
        raise T.TranslationError("Bölüm numarası geçersiz.") from e
    redo = bool(body.get("all"))
    with engine.begin() as conn:
        job = T._job(conn, tenant, job_id, user, see_all)
        if not may_run(job, user, see_all, can_manage):
            raise T.TranslationError("ZEKİ kalite tahminini işin inceleyeni ya da çeviri işi yöneticisi başlatır.", 403)
        with _lock:
            run = _run_row(conn, job_id)
            if (run is not None and run.state == "calisiyor") or job_id in _running:
                raise T.TranslationError("Bu işte kalite tahmini zaten sürüyor.", 409)
            _running.add(job_id)
        try:
            # Kaynak yeni sürümle değiştiyse eski segmentlerin puanları artık kayıttır.
            conn.execute(sa.delete(QE).where(QE.c.job_id == job_id, QE.c.segment_id.notin_(
                sa.select(T.SEGMENTS.c.id).where(T.SEGMENTS.c.job_id == job_id))))
            rows = _candidates(conn, job_id, chapter)
            have = dict(conn.execute(sa.select(QE.c.segment_id, QE.c.target_hash).where(QE.c.job_id == job_id)).all())
            todo = rows if redo else [r for r in rows if have.get(r.id) != qe_hash(r.source, r.target)]
            if not todo:
                raise T.TranslationError(
                    "Tahmin bekleyen çevrilmiş segment yok; puanlar güncel." if rows else "Henüz çevrilmiş segment yok.", 409)
            terms = [t for t in T._terms_for(conn, tenant, job) if t.status == "onayli" and t.target_term]
            conn.execute(sa.delete(RUNS).where(RUNS.c.job_id == job_id))
            conn.execute(sa.insert(RUNS).values(job_id=job_id, state="calisiyor", note=None, done=0, total=len(todo),
                                                chapter=chapter, started_by=user.lower(), started_at=T._now(), finished_at=None))
        except BaseException:
            _running.discard(job_id)
            raise
    index = T.TermIndex(terms)

    def progress(n: int) -> None:
        with engine.begin() as c:
            c.execute(sa.update(RUNS).where(RUNS.c.job_id == job_id).values(done=n))

    saved = [0]

    def save(results: dict[str, dict[str, Any]]) -> None:
        # Her parça kendi işleminde yazılır: servis ortada yeniden başlarsa yapılan puanlama kaybolmaz.
        if not results:
            return
        now = T._now()
        with engine.begin() as c:
            c.execute(sa.delete(QE).where(QE.c.segment_id.in_(list(results))))
            c.execute(sa.insert(QE), [{"segment_id": sid, "job_id": job_id, "score": r["score"], "category": r["category"],
                                       "severity": r["severity"], "reason": r["reason"], "span": r["span"],
                                       "target_hash": r["hash"], "created_at": now} for sid, r in results.items()])
        saved[0] += len(results)

    def run() -> None:
        state, note = "bitti", None
        try:
            st = score_segments(todo, chat, index, title=job.title, src=job.source_lang, tgt=job.target_lang,
                                progress=progress, save=save)
            parts = [f"{st['scored']} segment puanlandı", f"{st['suspect']} segment {SUSPECT_BELOW} altında"]
            if st["evidence_dropped"]:
                parts.append(f"{st['evidence_dropped']} şüpheli segmentin gerekçesi çeviriden alıntıyla kanıtlanamadığı için gösterilmiyor")
            if st["missed"]:
                parts.append(f"{st['missed']} segment için cevap gelmedi, yeniden başlatılabilir")
            note = "; ".join(parts)
        except Exception as e:  # noqa: BLE001
            log.exception("translation qe failed")
            state, note = "hata", (f"{saved[0]} segment puanlandıktan sonra durdu: " + str(e))[:480]
        finally:
            _running.discard(job_id)
            with engine.begin() as c:
                c.execute(sa.update(RUNS).where(RUNS.c.job_id == job_id).values(state=state, note=note, finished_at=T._now()))

    threading.Thread(target=run, name=f"translation-qe-{job_id[:8]}", daemon=True).start()
    return {"segments": len(todo), "words": sum(int(r.words) for r in todo)}


# ============================================================================================ okuma

def items_of(rows: Iterable[Any], qe_rows: Iterable[Any]) -> list[dict[str, Any]]:
    """Segment başına tahmin. Eskime kaynak+hedef özetiyle; hedefi boşalan ya da çevrilmemişe dönen segmentin puanı
    da eskidir. Şüpheli = güncel ve puan < 85."""
    by_seg = {r.id: r for r in rows}
    out = []
    for q in qe_rows:
        s = by_seg.get(q.segment_id)
        if s is None:
            continue
        fresh = s.status in T.DONE and bool((s.target or "").strip()) and qe_hash(s.source, s.target or "") == q.target_hash
        out.append({"segmentId": s.id, "no": s.no, "chapter": s.chapter, "words": int(s.words), "status": s.status,
                    "score": int(q.score), "category": q.category, "severity": q.severity, "reason": q.reason,
                    "span": q.span, "stale": not fresh, "suspect": fresh and int(q.score) < SUSPECT_BELOW,
                    "at": T._iso(q.created_at)})
    return sorted(out, key=lambda x: x["no"])


def summarize(rows: list[Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    """Dağılım, kelimeyle ağırlıklı ortalama (yalnız güncel puanlar), bölüm bazında özet."""
    fresh = [i for i in items if not i["stale"]]
    candidates = [r for r in rows if r.status in T.DONE and (r.target or "").strip()]
    fresh_ids = {i["segmentId"] for i in fresh}
    words = sum(i["words"] for i in fresh)
    avg = round(sum(i["score"] * i["words"] for i in fresh) / words, 1) if words else None
    buckets = []
    for lo, hi, lab in BUCKETS:
        sel = [i for i in fresh if lo <= i["score"] <= hi]
        buckets.append({"from": lo, "to": hi, "label": lab, "segments": len(sel), "words": sum(i["words"] for i in sel)})
    titles = {r.chapter: r.chapter_title for r in rows}
    ch: dict[int, dict[str, Any]] = defaultdict(lambda: {"scored": 0, "suspect": 0, "w": 0, "sw": 0})
    for i in fresh:
        c = ch[i["chapter"]]
        c["scored"] += 1
        c["suspect"] += int(i["suspect"])
        c["w"] += i["words"]
        c["sw"] += i["score"] * i["words"]
    chapters = [{"no": k, "title": titles.get(k, ""), "scored": v["scored"], "suspect": v["suspect"],
                 "average": round(v["sw"] / v["w"], 1) if v["w"] else None} for k, v in sorted(ch.items())]
    return {
        "translated": len(candidates), "scored": len(fresh), "stale": sum(1 for i in items if i["stale"]),
        "missing": sum(1 for r in candidates if r.id not in fresh_ids),
        "suspect": sum(1 for i in fresh if i["suspect"]), "words": words, "average": avg,
        "buckets": buckets, "chapters": chapters,
    }


def _run_out(run: Any) -> dict[str, Any]:
    if run is None:
        return {"state": "yok", "note": None, "done": 0, "total": 0, "chapter": None, "startedBy": None,
                "startedAt": None, "finishedAt": None}
    return {"state": run.state, "note": run.note, "done": int(run.done or 0), "total": int(run.total or 0),
            "chapter": run.chapter, "startedBy": run.started_by, "startedAt": T._iso(run.started_at),
            "finishedAt": T._iso(run.finished_at)}


def job_qe(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, job_id: str, can_manage: bool) -> dict[str, Any]:
    with engine.connect() as conn:
        job = T._job(conn, tenant, job_id, user, see_all)
        rows = conn.execute(sa.select(T.SEGMENTS).where(T.SEGMENTS.c.job_id == job_id).order_by(T.SEGMENTS.c.no)).all()
        qe_rows = conn.execute(sa.select(QE).where(QE.c.job_id == job_id)).all()
        run = _run_row(conn, job_id)
    items = items_of(rows, qe_rows)
    by_seg = {r.id: r for r in rows}
    # En düşük puanlılar: güncel şüphelilerin hepsi (kesilmez), puana göre artan; kaynak/hedef metniyle.
    lowest = [{**i, "source": by_seg[i["segmentId"]].source, "target": by_seg[i["segmentId"]].target or ""}
              for i in sorted((i for i in items if i["suspect"]), key=lambda i: (i["score"], i["no"]))]
    return {"run": _run_out(run), "threshold": SUSPECT_BELOW, "items": items, "summary": summarize(rows, items),
            "lowest": lowest,
            "canRun": may_run(job, user, see_all, can_manage), "categoryLabels": T.CATEGORIES,
            "severityLabels": {k: v[0] for k, v in T.SEVERITIES.items()}}
