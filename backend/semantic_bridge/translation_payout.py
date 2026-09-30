"""M4 çeviri işi → M8 serbest çalışan işi ve hakediş.

Dışarıdan çalışan çevirmenin emeği M8'de ödenecek iş olur; hakediş hesabı M8'de kalır, burada tekrarlanmaz.

- **Bağ:** çeviri işi bir M8 kişisine (çeviri rolü), kelime başına ücrete ve hakediş esasına bağlanır: onaylanan
  kelime (inceleyenin onayladığı segmentler, varsayılan) ya da çevrilen kelime (çevrildi + onaylandı). Bağ kendi
  tablosunda (`semantic_translation_links`); M4 ve M8 tablolarına sütun eklenmez.
- **İş paketi:** M8'de kitaba bir çeviri paketi ve kişiye atanmış tek görev açılır: miktar = kaynağın kelimesi
  (aktarılmış kelime düşülür), birim «kelime», termin = işin teslim tarihi. Tahmini süre sayfa başına M8 çeviri
  saatinden hesaplanır (bir sayfa `WORDS_PER_PAGE` kelime); M8 kapasitesi ve takvimi işi böyle görür. Yeniden
  basılırsa yeni paket açılmaz, açık görevin miktarı/ücreti/terminine eşitlenir.
- **Hakedişe aktarım:** esas kelimeden daha önce aktarılan düşülür; yalnız yeni kelime gider. Açık görev bölünür:
  aktarılan kelime ayrı görev olarak açılır, kişiye atanır, teslim tutanağıyla teslim alınır ve kabul edilir
  (M8 `add_tasks` → `assign` → `add_delivery` → `decide_delivery`); kalan kelime asıl görevde kalır. Aktarılacak
  kelime asıl görevin tamamını karşılıyorsa asıl görevin kendisi kabul edilir. Kabul edilen görev M8'de ödenecek
  işlere düşer, hakediş belgesi oradan hazırlanır.
- Aynı aktarım iki kez gitmez: aktarılan kelime önce ayrılır (koşullu güncelleme), M8 adımları başarısız olursa
  ayrılan kelime ve açılan görev geri alınır. Her aktarım `semantic_translation_payout_moves`'ta iz bırakır.
- CRM'e ve Logo'ya yazılmaz; tutarlar M8'deki gibi brüt, KDV hariç, TL.
"""
from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from functools import wraps
from typing import Any, Optional

import sqlalchemy as sa
# Uç imzaları dizge olarak çözülür (`from __future__ import annotations`): Request modül düzeyinde olmalı.
from fastapi import HTTPException, Request

from semantic_bridge import editorial_translation as tr
from semantic_bridge import freelance as fl
from semantic_bridge import sorgu_izi as _IZ  # noqa: E402 — sorgu bilgisi
from semantic_bridge.soru_kaynak import databases as _sk_dbs  # noqa: E402

log = logging.getLogger("semantic.translation_payout")
_md = sa.MetaData()

#: M8 çeviri rolü ve bu bağda kullanılan birim.
ROLE = "ceviri"
UNIT = "kelime"
#: Tahmini süre için bir sayfanın kelimesi (M8 çeviri rolünün saati sayfa başınadır).
WORDS_PER_PAGE = 250
BASES = {"onaylanan": "Onaylanan kelime", "cevrilen": "Çevrilen kelime"}
#: M8'de hâlâ elde olan (kabul edilmemiş, iptal olmamış) görev durumları.
OPEN_TASK = ("atanmadi", "atandi", "calisiyor", "revizyon", "teslim")

LINKS = sa.Table(
    "semantic_translation_links", _md,
    sa.Column("job_id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("person_id", sa.String(32), nullable=False),
    sa.Column("package_id", sa.String(32)),
    sa.Column("task_id", sa.String(32)),
    sa.Column("rate", sa.Numeric(14, 2), nullable=False),
    sa.Column("basis", sa.String(12), nullable=False, default="onaylanan"),
    sa.Column("transferred", sa.Integer, nullable=False, default=0),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
)
MOVES = sa.Table(
    "semantic_translation_payout_moves", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("job_id", sa.String(32), nullable=False, index=True),
    sa.Column("task_id", sa.String(32), nullable=False),
    sa.Column("words", sa.Integer, nullable=False),
    sa.Column("basis", sa.String(12), nullable=False),
    sa.Column("rate", sa.Numeric(14, 2), nullable=False),
    sa.Column("amount", sa.Numeric(14, 2), nullable=False),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

_ready: set[int] = set()
_lock = threading.Lock()
#: Aynı işin iki aktarımı aynı anda koşmasın (köprü tek süreç; çok süreçte koşullu güncelleme korur).
_moving = threading.Lock()


class PayoutError(ValueError):
    """Kişiye gösterilecek düz Türkçe hata."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _plain(fn):
    """M4 ve M8'in kendi hataları da aynı düz cümleyle döner."""
    @wraps(fn)
    def run(*a, **kw):
        try:
            return fn(*a, **kw)
        except (tr.TranslationError, fl.FreelanceError) as e:
            raise PayoutError(str(e), e.status) from e
    return run


def ensure(engine: sa.engine.Engine) -> None:
    tr.ensure(engine)
    fl.ensure(engine)
    with _lock:
        if id(engine) in _ready:
            return
        from semantic_layer.store import schema_stamp
        schema_stamp.create_all(_md, engine)
        _ready.add(id(engine))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()
    return v.isoformat()


def _hours(words: int) -> float:
    """Tahmini saat: M8 çeviri rolünün sayfa başına saati × sayfa. M8 sıfır saati kabul etmez."""
    return max(0.01, round(words / WORDS_PER_PAGE * fl.ROLES[ROLE][2], 2))


def _amount(words: int, rate: Decimal) -> Decimal:
    return (Decimal(words) * Decimal(rate)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------------------------- okuma

def _managed_job(conn: sa.Connection, tenant: str, job_id: str, user: str, see_all: bool) -> Any:
    job = tr._job(conn, tenant, job_id, user, see_all)
    if not tr._roles(job, user, see_all)["manage"]:
        raise PayoutError("Çevirmen ücreti ve hakedişi yalnız işi açan kişi ya da yetkili yönetici yönetir.", 403)
    return job


def _words(conn: sa.Connection, job_id: str) -> dict[str, int]:
    rows = conn.execute(sa.select(tr.SEGMENTS.c.status, sa.func.sum(tr.SEGMENTS.c.words))
                        .where(tr.SEGMENTS.c.job_id == job_id).group_by(tr.SEGMENTS.c.status)).all()
    by = {st: int(w or 0) for st, w in rows}
    return {"total": sum(by.values()), "approved": by.get("onaylandi", 0),
            "translated": by.get("cevrildi", 0) + by.get("onaylandi", 0)}


def _basis_words(words: dict[str, int], basis: str) -> int:
    return words["approved"] if basis == "onaylanan" else words["translated"]


def _link(conn: sa.Connection, tenant: str, job_id: str) -> Any:
    return conn.execute(sa.select(LINKS).where(LINKS.c.job_id == job_id, LINKS.c.tenant_id == tenant)).first()


def _task(conn: sa.Connection, tenant: str, task_id: Optional[str]) -> Any:
    if not task_id:
        return None
    return conn.execute(sa.select(fl.TASKS).where(fl.TASKS.c.id == task_id, fl.TASKS.c.tenant_id == tenant)).first()


def _people(conn: sa.Connection, tenant: str) -> list[dict[str, Any]]:
    """M8'de çeviri rolü olan aktif kişiler; kelime başına ücreti kartında yazılıysa o da gelir."""
    rows = conn.execute(sa.select(fl.PEOPLE).where(fl.PEOPLE.c.tenant_id == tenant, fl.PEOPLE.c.status == "aktif")
                        .order_by(fl.PEOPLE.c.name)).all()
    out = []
    for r in rows:
        if ROLE not in fl._loads(r.roles_json, []):
            continue
        rates = [x for x in fl._loads(r.rates_json, []) if x.get("role") == ROLE and x.get("unit") == UNIT]
        out.append({"id": r.id, "name": r.name, "city": r.city, "email": r.email,
                    "rate": rates[0]["price"] if rates else None})
    return out


@_plain
def status(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, job_id: str) -> dict[str, Any]:
    with engine.connect() as conn:
        job = _managed_job(conn, tenant, job_id, user, see_all)
        words = _words(conn, job_id)
        link = _link(conn, tenant, job_id)
        people = _people(conn, tenant)
        out: dict[str, Any] = {
            "jobId": job_id, "words": words, "bases": BASES, "unit": UNIT, "wordsPerPage": WORDS_PER_PAGE,
            "people": people, "link": None, "task": None, "package": None, "moves": [],
        }
        if link is None:
            return out
        person = conn.execute(sa.select(fl.PEOPLE.c.id, fl.PEOPLE.c.name, fl.PEOPLE.c.status)
                              .where(fl.PEOPLE.c.id == link.person_id)).first()
        task = _task(conn, tenant, link.task_id)
        pkg = conn.execute(sa.select(fl.PACKAGES.c.id, fl.PACKAGES.c.title, fl.PACKAGES.c.status)
                           .where(fl.PACKAGES.c.id == link.package_id)).first() if link.package_id else None
        moves = conn.execute(sa.select(MOVES).where(MOVES.c.job_id == job_id).order_by(MOVES.c.created_at.desc())).all()
        # Her aktarımın görevi hakedişe girdi mi, ödendi mi: M8'deki durumundan.
        move_tasks = {t.id: t for t in conn.execute(sa.select(fl.TASKS.c.id, fl.TASKS.c.payout_id)
                                                    .where(fl.TASKS.c.id.in_([m.task_id for m in moves] or [""])))}
        payouts = {p.id: p for p in conn.execute(sa.select(fl.PAYOUTS.c.id, fl.PAYOUTS.c.no, fl.PAYOUTS.c.status).where(
            fl.PAYOUTS.c.id.in_([t.payout_id for t in move_tasks.values() if t.payout_id] or [""])))}
    basis_words = _basis_words(words, link.basis)
    rate = Decimal(link.rate)
    pending = max(0, basis_words - int(link.transferred or 0))
    out["link"] = {
        "personId": link.person_id, "personName": person.name if person else None,
        "personActive": bool(person and person.status == "aktif"), "rate": float(rate), "basis": link.basis,
        "basisWords": basis_words, "transferred": int(link.transferred or 0), "pending": pending,
        "pendingAmount": float(_amount(pending, rate)), "transferredAmount": float(_amount(int(link.transferred or 0), rate)),
        # Esas kelime aktarılandan azsa (yeni kaynak sürümü onayları düşürdü) fark burada görünür; geri alınmaz.
        "ahead": max(0, int(link.transferred or 0) - basis_words),
        "updatedBy": link.updated_by or link.created_by, "updatedAt": _iso(link.updated_at or link.created_at),
    }
    if task is not None:
        out["task"] = {"id": task.id, "title": task.title, "status": task.status, "units": float(task.units),
                       "unitPrice": float(task.unit_price), "due": _iso(task.due), "open": task.status in OPEN_TASK}
    if pkg is not None:
        out["package"] = {"id": pkg.id, "title": pkg.title, "status": pkg.status}
    out["moves"] = []
    for m in moves:
        t = move_tasks.get(m.task_id)
        p = payouts.get(t.payout_id) if t is not None and t.payout_id else None
        out["moves"].append({"id": m.id, "taskId": m.task_id, "words": m.words, "basis": m.basis, "rate": float(m.rate),
                             "amount": float(m.amount), "by": m.created_by, "at": _iso(m.created_at),
                             "payout": {"id": p.id, "no": p.no, "status": p.status} if p is not None else None})
    return out


# ---------------------------------------------------------------------------------------------- bağ

def _rate(v: Any) -> Decimal:
    d = fl._money(v, "Kelime ücreti")
    if d <= 0:
        raise PayoutError("Kelime ücreti sıfırdan büyük olmalı.")
    return d


@_plain
def set_link(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, job_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Kişi, kelime ücreti ve esas. M8'de açık görev varsa kişi/ücret oraya da yansır (hakedişe girmemişse)."""
    person_id = str(body.get("personId") or "").strip()
    basis = str(body.get("basis") or "onaylanan")
    if basis not in BASES:
        raise PayoutError("Hakediş esası onaylanan ya da çevrilen kelime olmalı.")
    rate = _rate(body.get("rate"))
    now = _now()
    with engine.begin() as conn:
        job = _managed_job(conn, tenant, job_id, user, see_all)
        if not person_id:
            raise PayoutError("Serbest çalışan seçilmeli.")
        person = fl._person_row(conn, tenant, person_id)
        if ROLE not in fl._loads(person.roles_json, []):
            raise PayoutError(f"{person.name} M8'de çeviri rolünde kayıtlı değil.", 409)
        old = _link(conn, tenant, job_id)
        task = _task(conn, tenant, old.task_id) if old is not None else None
        if task is not None and (task.status not in OPEN_TASK or task.payout_id is not None):
            task = None                                    # kapanmış görev bağa eşitlenmez
        if person.status != "aktif" and (old is None or old.person_id != person_id):
            raise PayoutError(f"{person.name} pasif; iş bağlanamaz.", 409)
        if task is not None and task.person_id != person_id and task.status not in ("atanmadi", "atandi", "calisiyor"):
            raise PayoutError("M8'deki görev teslim aşamasında; kişisi değiştirilemez. Önce teslimi karara bağlayın.", 409)
        if old is None:
            conn.execute(sa.insert(LINKS).values(job_id=job_id, tenant_id=tenant, person_id=person_id, package_id=None,
                                                 task_id=None, rate=rate, basis=basis, transferred=0,
                                                 created_by=user, created_at=now))
        else:
            if old.person_id != person_id and int(old.transferred or 0) > 0:
                # Aktarılmış kelimeler eski kişinin hakedişinde; kişi değişirse kalan kelime yeni kişiye gider.
                log.info("çeviri işi %s: kişi %s → %s (aktarılmış %s kelime eski kişide kalır)",
                         job_id, old.person_id, person_id, old.transferred)
            conn.execute(sa.update(LINKS).where(LINKS.c.job_id == job_id).values(
                person_id=person_id, rate=rate, basis=basis, updated_by=user, updated_at=now))
    # Açık M8 görevini bağa eşitle (M8'in kendi kurallarıyla: teslimdeki görevin kişisi değişmez, hakedişteki tutar değişmez).
    if task is not None:
        if Decimal(task.unit_price) != rate:
            fl.update_task(engine, tenant, user, task.id, {"unitPrice": str(rate)})
        if task.person_id != person_id:
            fl.assign(engine, tenant, user, [{"taskId": task.id, "personId": person_id}])
    return {"personId": person_id, "personName": person.name, "rate": float(rate), "basis": basis, "title": job.title}


# ---------------------------------------------------------------------------------------------- iş paketi

@_plain
def open_package(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, job_id: str) -> dict[str, Any]:
    """M8'de iş paketi + kişiye atanmış görev. Bağın açık görevi varsa yenisi açılmaz, miktar/ücret/termin eşitlenir."""
    with engine.connect() as conn:
        job = _managed_job(conn, tenant, job_id, user, see_all)
        link = _link(conn, tenant, job_id)
        if link is None:
            raise PayoutError("Önce serbest çalışanı ve kelime ücretini kaydedin.", 409)
        words = _words(conn, job_id)
        person = fl._person_row(conn, tenant, link.person_id)
        task = _task(conn, tenant, link.task_id)
        pkg = conn.execute(sa.select(fl.PACKAGES).where(fl.PACKAGES.c.id == link.package_id)).first() if link.package_id else None
    if not words["total"]:
        raise PayoutError("Kaynak metin yüklenmeden iş paketi açılmaz; miktar kaynağın kelimesidir.", 409)
    remaining = words["total"] - int(link.transferred or 0)
    due = job.due_date.isoformat() if job.due_date else None
    if task is not None and task.status in OPEN_TASK:
        # Aynı iş için ikinci görev açılmaz; kaynak değiştiyse miktar, ücret ve termin güncellenir.
        change: dict[str, Any] = {}
        if task.payout_id is None:
            if remaining > 0 and Decimal(task.units) != Decimal(remaining):
                change.update(units=str(remaining), effortHours=_hours(remaining))
            if Decimal(task.unit_price) != Decimal(link.rate):
                change["unitPrice"] = str(link.rate)
        if due and (task.due is None or task.due.isoformat() != due) and (task.start is None or task.start.isoformat() <= due):
            change["due"] = due
        if change:
            fl.update_task(engine, tenant, user, task.id, change)
        return {"packageId": task.package_id, "taskId": task.id, "created": False, "units": remaining}
    if remaining <= 0:
        raise PayoutError("Bu işin bütün kelimeleri hakedişe aktarıldı; açılacak iş kalmadı.", 409)
    if person.status != "aktif":
        raise PayoutError(f"{person.name} pasif; iş atanamaz.", 409)
    title = f"{job.title} çevirisi ({tr.LANGS.get(job.source_lang, job.source_lang)} → {tr.LANGS.get(job.target_lang, job.target_lang)})"
    spec = {"title": title[:300], "role": ROLE, "units": str(remaining), "unit": UNIT, "unitPrice": str(link.rate),
            "effortHours": _hours(remaining), "due": due}
    created = False
    if pkg is not None and pkg.status == "acik":
        package_id = pkg.id
        fl.add_tasks(engine, tenant, user, package_id, [spec])
    else:
        brief = (f"Çeviri işi «{job.title}»: {words['total']:,} kelime".replace(",", ".")
                 + ". Hakediş çeviri ekranından aktarılan kelimeyle oluşur.")
        package_id = fl.create_package(engine, tenant, user, {
            "title": f"Çeviri · {job.title}"[:300], "role": ROLE, "bookTitle": job.title, "due": due, "brief": brief,
            "tasks": [spec]})["id"]
        created = True
    task_id = _new_task_id(engine, tenant, package_id, spec["title"])
    fl.assign(engine, tenant, user, [{"taskId": task_id, "personId": link.person_id}])
    with engine.begin() as conn:
        conn.execute(sa.update(LINKS).where(LINKS.c.job_id == job_id).values(
            package_id=package_id, task_id=task_id, updated_by=user, updated_at=_now()))
    return {"packageId": package_id, "taskId": task_id, "created": created, "units": remaining}


def _new_task_id(engine: sa.engine.Engine, tenant: str, package_id: str, title: str) -> str:
    """M8 `add_tasks`/`create_package` görev kimliği döndürmez: paketteki bu adlı en yeni atanmamış görev."""
    with engine.connect() as conn:
        tid = conn.execute(sa.select(fl.TASKS.c.id).where(
            fl.TASKS.c.tenant_id == tenant, fl.TASKS.c.package_id == package_id, fl.TASKS.c.title == title,
            fl.TASKS.c.status == "atanmadi").order_by(fl.TASKS.c.created_at.desc()).limit(1)).scalar()
    if not tid:
        raise PayoutError("M8'de açılan görev bulunamadı; sayfayı yenileyip yeniden deneyin.", 500)
    return tid


# ---------------------------------------------------------------------------------------------- hakedişe aktarım

def _receipt(job: Any, words: int, basis: str, total: int, rate: Decimal, user: str) -> bytes:
    lines = [
        "Çeviri hakedişi teslim tutanağı",
        f"Eser: {job.title}",
        f"Dil: {tr.LANGS.get(job.source_lang, job.source_lang)} → {tr.LANGS.get(job.target_lang, job.target_lang)}",
        f"Esas: {BASES[basis]}",
        f"Bu aktarım: {words} kelime × {rate} ₺ = {_amount(words, rate)} ₺ (brüt, KDV hariç)",
        f"Toplam aktarılan: {total} kelime",
        f"Aktaran: {user}",
        f"Tarih: {(_now() + timedelta(hours=3)).strftime('%Y-%m-%d %H:%M')}",
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _accept(engine: sa.engine.Engine, tenant: str, user: str, task_id: str, receipt: bytes, name: str, note: str) -> None:
    """Görevi M8'in teslim + kabul yoluyla ödenecek işe düşürür. Bekleyen bir teslim varsa o kabul edilir."""
    with engine.connect() as conn:
        t = _task(conn, tenant, task_id)
        pending = conn.execute(sa.select(fl.DELIVERIES.c.id).where(fl.DELIVERIES.c.task_id == task_id,
                                                                   fl.DELIVERIES.c.decision == "bekliyor")
                               .order_by(fl.DELIVERIES.c.version.desc()).limit(1)).scalar() if t.status == "teslim" else None
    delivery_id = pending or fl.add_delivery(engine, tenant, user, task_id, filename=name, data=receipt, note=note)["id"]
    fl.decide_delivery(engine, tenant, user, delivery_id, {"decision": "kabul", "note": note})


@_plain
def transfer(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, job_id: str) -> dict[str, Any]:
    """Esas kelimeden daha önce aktarılanı düşer, yalnız yeni kelimeyi M8'de kabul edilmiş işe çevirir.
    Yeni kelime yoksa hiçbir şey yapmaz (`moved` 0) — aynı istek iki kez gelirse ikinci tutar üretmez."""
    with _moving:
        with engine.connect() as conn:
            job = _managed_job(conn, tenant, job_id, user, see_all)
            link = _link(conn, tenant, job_id)
            if link is None or not link.task_id:
                raise PayoutError("Önce M8'de iş paketini açın.", 409)
            words = _words(conn, job_id)
            task = _task(conn, tenant, link.task_id)
            person = fl._person_row(conn, tenant, link.person_id)
            pkg = conn.execute(sa.select(fl.PACKAGES).where(fl.PACKAGES.c.id == link.package_id)).first()
        old = int(link.transferred or 0)
        n = _basis_words(words, link.basis) - old
        if n <= 0:
            return {"moved": 0, "transferred": old, "amount": 0.0, "taskId": None}
        rate = Decimal(link.rate)
        is_open = task is not None and task.status in OPEN_TASK and task.payout_id is None
        whole = is_open and Decimal(n) >= Decimal(task.units)
        # Değişiklikten önce denetle: yarım kalan M8 adımı bırakmayalım.
        if person.status != "aktif" and not (whole and task.person_id == person.id):
            raise PayoutError(f"{person.name} pasif; M8'de iş atanamaz. Kişiyi aktif yapın ya da başka kişi seçin.", 409)
        if not whole and (pkg is None or pkg.status != "acik"):
            raise PayoutError("M8'deki iş paketi kapalı; hakedişe aktarmak için paketi yeniden açın.", 409)
        if is_open and task.status == "teslim" and not whole:
            raise PayoutError("M8'de bu görevin teslimi inceleme bekliyor; önce orada karara bağlayın.", 409)
        # Kelimeyi ayır: aynı anda gelen ikinci istek aynı kelimeyi göremez.
        with engine.begin() as conn:
            got = conn.execute(sa.update(LINKS).where(LINKS.c.job_id == job_id, LINKS.c.transferred == old).values(
                transferred=old + n, updated_by=user, updated_at=_now())).rowcount
        if not got:
            raise PayoutError("Bu iş için başka bir aktarım yapıldı; sayfayı yenileyin.", 409)
        receipt = _receipt(job, n, link.basis, old + n, rate, user)
        name = f"ceviri-hakedis-{old + n}-kelime.txt"
        note = f"Çeviri ekranından aktarıldı: {n} kelime ({BASES[link.basis].lower()})."
        undo: list[tuple[str, str, dict[str, Any]]] = []
        try:
            if whole:
                target = task.id
                change: dict[str, Any] = {}
                if Decimal(task.units) != Decimal(n):
                    change.update(units=str(n), effortHours=_hours(n))
                if Decimal(task.unit_price) != rate:
                    change["unitPrice"] = str(rate)
                if change:
                    fl.update_task(engine, tenant, user, task.id, change)
                    undo.append(("update", task.id, {"units": str(task.units), "unitPrice": str(task.unit_price),
                                                     "effortHours": task.effort_hours}))
                if task.person_id != link.person_id and task.status in ("atanmadi", "atandi", "calisiyor"):
                    fl.assign(engine, tenant, user, [{"taskId": task.id, "personId": link.person_id}])
                elif task.person_id is None:
                    raise PayoutError("M8'deki görevin kişisi yok; önce kişi atayın.", 409)
            else:
                if is_open:
                    # Asıl görev kalan kelimeyle sürer (kapasite kalan işi görür).
                    left = Decimal(task.units) - Decimal(n)
                    fl.update_task(engine, tenant, user, task.id, {
                        "units": str(left), "effortHours": max(0.01, round(float(task.effort_hours) * float(left / Decimal(task.units)), 2))})
                    undo.append(("update", task.id, {"units": str(task.units), "effortHours": task.effort_hours}))
                title = f"{job.title} çevirisi · hakediş {old + 1}–{old + n}. kelime"[:300]
                fl.add_tasks(engine, tenant, user, pkg.id, [{
                    "title": title, "role": ROLE, "units": str(n), "unit": UNIT, "unitPrice": str(rate),
                    "effortHours": _hours(n), "start": task.start.isoformat() if task is not None and task.start else None,
                    "due": task.due.isoformat() if task is not None and task.due else (job.due_date.isoformat() if job.due_date else None)}])
                target = _new_task_id(engine, tenant, pkg.id, title)
                undo.append(("cancel", target, {}))
                fl.assign(engine, tenant, user, [{"taskId": target, "personId": link.person_id}])
            _accept(engine, tenant, user, target, receipt, name, note)
        except Exception:
            _rollback(engine, tenant, user, job_id, old, n, undo)
            raise
        amount = _amount(n, rate)
        with engine.begin() as conn:
            conn.execute(sa.insert(MOVES).values(id=uuid.uuid4().hex, job_id=job_id, task_id=target, words=n,
                                                 basis=link.basis, rate=rate, amount=amount, created_by=user,
                                                 created_at=_now()))
    return {"moved": n, "transferred": old + n, "amount": float(amount), "taskId": target, "packageId": link.package_id}


def _rollback(engine: sa.engine.Engine, tenant: str, user: str, job_id: str, old: int, n: int,
              undo: list[tuple[str, str, dict[str, Any]]]) -> None:
    """M8 adımı yarıda kaldıysa: açılan görev iptal, bölünen görev eski miktarına, ayrılan kelime geri."""
    for kind, task_id, vals in reversed(undo):
        try:
            with engine.connect() as conn:
                t = _task(conn, tenant, task_id)
            if t is None or t.status == "onaylandi":
                continue
            if kind == "cancel":
                if t.status == "atanmadi":
                    fl.delete_task(engine, tenant, user, task_id)
                elif t.status in ("atandi", "calisiyor", "revizyon"):
                    fl.update_task(engine, tenant, user, task_id, {"status": "iptal"})
            else:
                fl.update_task(engine, tenant, user, task_id, vals)
        except Exception as e:  # noqa: BLE001 — geri alma en iyi çabadır; iz günlükte
            log.error("çeviri hakedişi geri alınamadı (iş %s, görev %s): %s", job_id, task_id, e)
    with engine.begin() as conn:
        conn.execute(sa.update(LINKS).where(LINKS.c.job_id == job_id, LINKS.c.transferred == old + n)
                     .values(transferred=old))


# ---------------------------------------------------------------------------------------------- köprü uçları

def register(app: Any, deps: dict[str, Any]) -> None:
    """Uçlar `/api/v1/editorial/translation/jobs/{iş}/payout[...]`. `deps["auth"]`: app.py'deki `_tr(request)` →
    (engine, tenant, user, see_all); `deps["audit"]`: `admin_mod.audit`. Sayfa kuralı çeviri sayfalarınındır;
    okuma `serbest.yonet`, yazma `ceviri.yonet` + `serbest.yonet` ister (access.py FEATURE_RULES)."""
    auth = deps["auth"]
    audit = deps["audit"]
    base = "/api/v1/editorial/translation/jobs/{job_id}/payout"

    def call(request: Request, fn, *a):
        engine, tenant, user, see_all = auth(request)
        ensure(engine)
        try:
            return engine, user, fn(engine, tenant, user, see_all, *a)
        except PayoutError as e:
            code = "FORBIDDEN" if e.status == 403 else "TRANSLATION"
            raise HTTPException(status_code=e.status, detail={"code": code, "message": str(e)}) from e

    @app.get(base)
    @_IZ.izlenir('portal.ceviri.hakedis', 'Hakediş', 'Hakediş: esas kelime = işin onaylı (ya da seçilen esasa göre çevrilen) kelimesi; aktarılan = daha önce hakedişe taşınan kelime; bekleyen = esas − aktarılan; tutar = kelime × kelime ücreti (ondalık hesap); iş paketi kelime sayısı ve taşıma geçmişi taşıma kayıtlarından.', engine=None, dbs=_sk_dbs)
    def tr_payout(job_id: str, request: Request) -> dict[str, Any]:
        return call(request, status, job_id)[2]

    @app.put(base)
    def tr_payout_link(job_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, user, out = call(request, set_link, job_id, body)
        audit(engine, user, "update", "translation_payout", job_id, out["title"],
              {k: out[k] for k in ("personId", "personName", "rate", "basis")})
        return out

    @app.post(base + "/package")
    def tr_payout_package(job_id: str, request: Request) -> dict[str, Any]:
        engine, user, out = call(request, open_package, job_id)
        audit(engine, user, "create" if out["created"] else "update", "translation_payout", job_id, None, out)
        return out

    @app.post(base + "/transfer")
    def tr_payout_transfer(job_id: str, request: Request) -> dict[str, Any]:
        engine, user, out = call(request, transfer, job_id)
        if out["moved"]:
            audit(engine, user, "create", "translation_payout_move", job_id, None, out)
        return out
