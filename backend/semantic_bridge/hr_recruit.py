"""M55 İşe alım: pozisyon, aday, özgeçmiş, kanıtlı özet, mülakat, şablon ve yazışma kayıtları; iş kuralları.

Analiz: docs/analiz/kullanici-ihtiyaclari/M55-ise-alim-yetkinlik.md §14.2. Ortak temel `hr_core` (İK-0).

Kurallar:
- **Karar insandadır.** Zeki AI hiçbir adayı elemez, puanlamaz, sıralamaz (KVKK md. 11/1-g); her aşama değişikliği bir
  kişinin kaydıdır (`semantic_hr_stage_log`). Kanıtlı özet yalnız «yetkinlik → özgeçmişteki satır» listesidir.
- **Gönderim yok.** Mektuplar şablondan taslak olur; teklif mektubu gönderilmeden önce `ik.teklif-onay` ile onaylanır
  (hazırlayan onaylayamaz). Gönderimi insan kendi e-postasından yapar, portal yalnız «gönderildi» kaydını tutar.
- **Görünürlük:** `ik.aday-hepsi` bütün adayları ve özgün özgeçmişi görür; `ik.aday-gor` yalnız işe alan yöneticisi ya da
  görüşmecisi olduğu pozisyonların (ve görüşmeci olduğu mülakatların) adaylarını, özgeçmişi maskeli metin olarak görür.
  E-posta ve telefon yalnız `ik.aday-hepsi`'de. Her aday görüntülemesi erişim kaydına yazılır.
- **Mülakat notu:** görüşmeci, kendi notunu teslim edene kadar aynı mülakattaki başkalarının notunu görmez.
- **Saklama:** sonuçlanan (ret / aday çekildi) adayın süresi sonuç tarihinden sayılır: havuz rızası varsa `aday_havuz`,
  yoksa `aday_ret` süresi. Süre girilmemişse imha yapılmaz, ekran uyarır. Havuz rızası geri çekilince aday hemen imha
  kuyruğuna girer. İşe alınan adayın kaydı çalışan kaydına bağlanır, aday imhasına girmez (İş Kanunu md. 75).
- **İmha** kişisel veriyi siler (dosya, metin, kanıt, not, yazışma, iletişim bilgisi, ad), aday satırı istatistik için
  `purged_at` ile kalır; tutanak `semantic_hr_purge_runs`.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import weakref
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

import sqlalchemy as sa

from semantic_bridge import hr_core as H
from semantic_bridge import hr_recruit_text as X
from semantic_bridge.hr_core import HrError, clean, dump, iso, load, new_id, now

log = logging.getLogger("semantic_bridge.hr.recruit")

_md = sa.MetaData()


def _ts(name: str, **kw: Any) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), **kw)


POSITIONS = sa.Table(
    "semantic_hr_positions", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("title", sa.String(200), nullable=False),
    sa.Column("unit_id", sa.String(40)),
    sa.Column("hiring_manager", sa.String(120)),                 # AD hesap adı (küçük harf)
    sa.Column("team_json", sa.Text),                             # görüşmeci hesap adları
    sa.Column("competencies_json", sa.Text),
    sa.Column("note", sa.Text),
    sa.Column("posting_text", sa.Text),
    sa.Column("posting_warnings_json", sa.Text),
    sa.Column("interview_kit_json", sa.Text),
    sa.Column("state", sa.String(16), nullable=False),
    sa.Column("submitted_by", sa.String(120)),
    _ts("submitted_at"),
    sa.Column("approved_by", sa.String(120)),
    _ts("approved_at"),
    sa.Column("review_note", sa.Text),
    _ts("opened_at"),
    _ts("closed_at"),
    sa.Column("created_by", sa.String(120)),
    _ts("created_at", nullable=False),
    _ts("updated_at", nullable=False),
)

CANDIDATES = sa.Table(
    "semantic_hr_candidates", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("position_id", sa.String(40), index=True),
    sa.Column("full_name", sa.String(200), nullable=False),
    sa.Column("email", sa.String(254)),
    sa.Column("phone", sa.String(40)),
    sa.Column("source", sa.String(16), nullable=False),
    sa.Column("source_ref", sa.String(64), index=True),         # e-posta ileti kimliğinin özeti (tekrar aktarımı önler)
    sa.Column("stage", sa.String(16), nullable=False),
    sa.Column("outcome", sa.String(16)),
    _ts("stage_since", nullable=False),
    _ts("outcome_at"),
    sa.Column("retention_class", sa.String(40)),
    _ts("retention_until"),
    _ts("retention_forced"),                                     # rıza geri çekildi: bu andan sonra imha
    _ts("purged_at"),
    sa.Column("employee_id", sa.String(40)),
    sa.Column("created_by", sa.String(120)),
    _ts("created_at", nullable=False),
    _ts("updated_at", nullable=False),
)

FILES = sa.Table(
    "semantic_hr_candidate_files", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("candidate_id", sa.String(40), nullable=False, index=True),
    sa.Column("filename", sa.String(255), nullable=False),
    sa.Column("mime", sa.String(120)),
    sa.Column("size", sa.Integer, nullable=False, default=0),
    sa.Column("blob", sa.LargeBinary),
    sa.Column("extracted_text", sa.Text),
    sa.Column("masked_text", sa.Text),
    sa.Column("mask_json", sa.Text),
    sa.Column("model_checked", sa.Boolean, nullable=False, default=False),
    sa.Column("created_by", sa.String(120)),
    _ts("created_at", nullable=False),
)

EVIDENCE = sa.Table(
    "semantic_hr_candidate_evidence", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("candidate_id", sa.String(40), nullable=False, index=True),
    sa.Column("competency", sa.String(300), nullable=False),
    sa.Column("line_no", sa.Integer),
    sa.Column("quote", sa.Text),
    sa.Column("verdict", sa.String(16), nullable=False),        # kanit_var | kanit_yok
    sa.Column("model_run_id", sa.String(40)),
    _ts("created_at", nullable=False),
)

INTERVIEWS = sa.Table(
    "semantic_hr_interviews", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("candidate_id", sa.String(40), nullable=False, index=True),
    _ts("starts_at", nullable=False),
    sa.Column("location", sa.String(300)),
    sa.Column("room_booking_id", sa.String(80)),
    sa.Column("interviewers_json", sa.Text),
    sa.Column("created_by", sa.String(120)),
    _ts("created_at", nullable=False),
)

NOTES = sa.Table(
    "semantic_hr_interview_notes", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("interview_id", sa.String(40), nullable=False, index=True),
    sa.Column("candidate_id", sa.String(40), nullable=False, index=True),
    sa.Column("author", sa.String(120), nullable=False),
    sa.Column("scores_json", sa.Text),                           # yetkinlik → 1..5 (görüşmecinin puanı; model değil)
    sa.Column("note", sa.Text),
    _ts("submitted_at"),
    _ts("updated_at", nullable=False),
    sa.UniqueConstraint("interview_id", "author", name="uq_hr_note_author"),
)

TEMPLATES = sa.Table(
    "semantic_hr_templates", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("kind", sa.String(16), nullable=False),
    sa.Column("name", sa.String(200), nullable=False),
    sa.Column("body", sa.Text, nullable=False),
    sa.Column("version", sa.Integer, nullable=False, default=1),
    sa.Column("state", sa.String(16), nullable=False),           # taslak | yururlukte | arsiv
    sa.Column("updated_by", sa.String(120)),
    _ts("updated_at", nullable=False),
)

MESSAGES = sa.Table(
    "semantic_hr_messages", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("candidate_id", sa.String(40), nullable=False, index=True),
    sa.Column("kind", sa.String(16), nullable=False),
    sa.Column("template_id", sa.String(40)),
    sa.Column("template_version", sa.Integer),
    sa.Column("body", sa.Text, nullable=False),
    sa.Column("status", sa.String(16), nullable=False),          # taslak | onayda | onaylandi | gonderildi | iptal
    sa.Column("created_by", sa.String(120)),
    _ts("created_at", nullable=False),
    sa.Column("approved_by", sa.String(120)),
    _ts("approved_at"),
    sa.Column("sent_by", sa.String(120)),
    _ts("sent_at"),
    sa.Column("channel", sa.String(40)),
    sa.Column("note", sa.Text),
)

STAGE_LOG = sa.Table(
    "semantic_hr_stage_log", _md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("candidate_id", sa.String(40), nullable=False, index=True),
    _ts("at", nullable=False),
    sa.Column("actor", sa.String(120), nullable=False),
    sa.Column("from_stage", sa.String(16)),
    sa.Column("to_stage", sa.String(16), nullable=False),
    sa.Column("outcome", sa.String(16)),
    sa.Column("reason", sa.Text),
)

REMINDERS = sa.Table(
    "semantic_hr_recruit_reminders", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("candidate_id", sa.String(40), primary_key=True),
    sa.Column("stage_since", sa.String(40), primary_key=True),   # aynı aşamada bir kez hatırlatılır
    _ts("sent_at", nullable=False),
)

STAGES = {"basvurdu": "Başvurdu", "on_eleme": "Ön eleme", "mulakat": "Mülakat", "teklif": "Teklif", "sonuc": "Sonuç"}
OUTCOMES = {"ise_alindi": "İşe alındı", "ret": "Ret", "cekildi": "Aday çekildi"}
SOURCES = {"eposta": "E-posta", "elle": "Elle", "ilan_sitesi": "İlan sitesi", "ic_basvuru": "İç başvuru"}
POSITION_STATES = {"taslak": "Taslak", "onayda": "Onayda", "acik": "Açık", "beklemede": "Beklemede", "kapandi": "Kapandı"}
TEMPLATE_STATES = {"taslak": "Taslak", "yururlukte": "Yürürlükte", "arsiv": "Arşiv"}
MESSAGE_STATES = {"taslak": "Taslak", "onayda": "Onayda", "onaylandi": "Onaylandı", "gonderildi": "Gönderildi", "iptal": "İptal"}
SEND_CHANNELS = {"eposta": "E-posta", "telefon": "Telefon", "elden": "Elden"}

F_ALL = "ozellik:ik.aday-hepsi"
F_SEE = "ozellik:ik.aday-gor"
F_DECIDE = "ozellik:ik.aday-karar"
F_POS_OPEN = "ozellik:ik.pozisyon-ac"
F_POS_APPROVE = "ozellik:ik.pozisyon-onay"
F_LETTERS = "ozellik:ik.yazisma-gonder"
F_OFFER_APPROVE = "ozellik:ik.teklif-onay"
F_TEMPLATES = "ozellik:ik.sablon"
F_EXPORT = "ozellik:ik.disa-aktar"
F_KVKK = "ozellik:ik.kvkk-yonet"

_ready: "weakref.WeakSet[sa.engine.Engine]" = weakref.WeakSet()


def ensure(engine: sa.engine.Engine) -> None:
    H.ensure(engine)
    if engine in _ready:
        return
    _md.create_all(engine, checkfirst=True)
    _ready.add(engine)


def _days(since: Any, t: datetime) -> Optional[int]:
    s = H.aware(since)
    return None if s is None else max(0, (t - s).days)


def _usernames(v: Any) -> list[str]:
    raw = v if isinstance(v, list) else str(v or "").replace(";", ",").split(",")
    out: list[str] = []
    for x in raw:
        u = clean(x, 120).lower()
        if u and u not in out:
            out.append(u)
    return out


def _competencies(v: Any) -> list[str]:
    raw = v if isinstance(v, list) else str(v or "").split("\n")
    out: list[str] = []
    for x in raw:
        c = clean(x, 300)
        if c and c not in out:
            out.append(c)
    return out


# ------------------------------------------------------------------ görünürlük


def own_position_ids(c: Any, tenant: str, user: str) -> set[str]:
    rows = c.execute(sa.select(POSITIONS.c.id, POSITIONS.c.hiring_manager, POSITIONS.c.team_json)
                     .where(POSITIONS.c.tenant_id == tenant)).all()
    return {r.id for r in rows if r.hiring_manager == user or user in (load(r.team_json, []) or [])}


def _interviewer_candidate_ids(c: Any, tenant: str, user: str) -> set[str]:
    rows = c.execute(sa.select(INTERVIEWS.c.candidate_id, INTERVIEWS.c.interviewers_json)
                     .where(INTERVIEWS.c.tenant_id == tenant)).all()
    return {r.candidate_id for r in rows if user in (load(r.interviewers_json, []) or [])}


def candidate_filter(c: Any, tenant: str, who: H.Who) -> Optional[sa.ColumnElement]:
    """Kişinin görebileceği adaylar için süzgeç; None = hepsi. Yetkisi yoksa hiçbir aday."""
    if who.can(F_ALL):
        return None
    if not who.can(F_SEE):
        return sa.false()
    pos = own_position_ids(c, tenant, who.user)
    ids = _interviewer_candidate_ids(c, tenant, who.user)
    conds = []
    if pos:
        conds.append(CANDIDATES.c.position_id.in_(sorted(pos)))
    if ids:
        conds.append(CANDIDATES.c.id.in_(sorted(ids)))
    return sa.or_(*conds) if conds else sa.false()


def _load_candidate(c: Any, tenant: str, who: H.Who, cid: str, *, allow_purged: bool = False) -> Any:
    q = sa.select(CANDIDATES).where(CANDIDATES.c.id == cid, CANDIDATES.c.tenant_id == tenant)
    flt = candidate_filter(c, tenant, who)
    if flt is not None:
        q = q.where(flt)
    r = c.execute(q).first()
    if r is None or (r.purged_at is not None and not allow_purged):
        raise HrError("Aday bulunamadı ya da bu adayı görme yetkiniz yok.", 404)
    return r


def can_decide(c: Any, tenant: str, who: H.Who, cand: Any) -> bool:
    if not who.can(F_DECIDE):
        return False
    if who.can(F_ALL):
        return True
    return bool(cand.position_id) and cand.position_id in own_position_ids(c, tenant, who.user)


def candidate_exists(engine: sa.engine.Engine, tenant: str, cid: str) -> bool:
    with engine.connect() as c:
        return c.execute(sa.select(CANDIDATES.c.id).where(CANDIDATES.c.id == cid, CANDIDATES.c.tenant_id == tenant,
                                                          CANDIDATES.c.purged_at.is_(None))).first() is not None


# ------------------------------------------------------------------ pozisyonlar


def _pos_out(r: Any, units: dict[str, str], counts: Optional[dict[str, int]] = None) -> dict[str, Any]:
    return {"id": r.id, "title": r.title, "unitId": r.unit_id, "unitName": units.get(r.unit_id or "", ""),
            "hiringManager": r.hiring_manager, "team": load(r.team_json, []) or [],
            "competencies": load(r.competencies_json, []) or [], "note": r.note or "", "postingText": r.posting_text or "",
            "postingWarnings": load(r.posting_warnings_json, []) or [], "interviewKit": load(r.interview_kit_json, []) or [],
            "state": r.state, "stateLabel": POSITION_STATES.get(r.state, r.state),
            "submittedBy": r.submitted_by, "submittedAt": iso(r.submitted_at), "approvedBy": r.approved_by,
            "approvedAt": iso(r.approved_at), "reviewNote": r.review_note or "", "openedAt": iso(r.opened_at),
            "closedAt": iso(r.closed_at), "createdBy": r.created_by, "createdAt": iso(r.created_at),
            "updatedAt": iso(r.updated_at), "counts": counts or {}}


def _units(c: Any, tenant: str) -> dict[str, str]:
    return dict(c.execute(sa.select(H.UNITS.c.id, H.UNITS.c.name).where(H.UNITS.c.tenant_id == tenant)).all())


def list_positions(engine: sa.engine.Engine, tenant: str, who: H.Who, state: str = "") -> list[dict[str, Any]]:
    ensure(engine)
    with engine.connect() as c:
        q = sa.select(POSITIONS).where(POSITIONS.c.tenant_id == tenant)
        if state in POSITION_STATES:
            q = q.where(POSITIONS.c.state == state)
        rows = c.execute(q.order_by(POSITIONS.c.created_at.desc())).all()
        if not who.can(F_ALL, F_POS_OPEN, F_POS_APPROVE):
            mine = own_position_ids(c, tenant, who.user)
            rows = [r for r in rows if r.id in mine]
        counts: dict[str, dict[str, int]] = {}
        flt = candidate_filter(c, tenant, who)
        cq = sa.select(CANDIDATES.c.position_id, CANDIDATES.c.stage, sa.func.count()).where(
            CANDIDATES.c.tenant_id == tenant, CANDIDATES.c.purged_at.is_(None))
        if flt is not None:
            cq = cq.where(flt)
        for pid, stage, n in c.execute(cq.group_by(CANDIDATES.c.position_id, CANDIDATES.c.stage)).all():
            counts.setdefault(pid or "", {})[stage] = int(n)
        units = _units(c, tenant)
    return [_pos_out(r, units, counts.get(r.id, {})) for r in rows]


def get_position(engine: sa.engine.Engine, tenant: str, who: H.Who, pid: str) -> dict[str, Any]:
    ensure(engine)
    with engine.connect() as c:
        r = c.execute(sa.select(POSITIONS).where(POSITIONS.c.id == pid, POSITIONS.c.tenant_id == tenant)).first()
        if r is None or (not who.can(F_ALL, F_POS_OPEN, F_POS_APPROVE) and pid not in own_position_ids(c, tenant, who.user)):
            raise HrError("Pozisyon bulunamadı.", 404)
        return _pos_out(r, _units(c, tenant))


def save_position(engine: sa.engine.Engine, tenant: str, actor: str, body: dict[str, Any],
                  pid: Optional[str] = None) -> tuple[dict[str, Any], dict[str, Any]]:
    ensure(engine)
    t = now()
    with engine.begin() as c:
        before = None
        if pid:
            before = c.execute(sa.select(POSITIONS).where(POSITIONS.c.id == pid, POSITIONS.c.tenant_id == tenant)).first()
            if before is None:
                raise HrError("Pozisyon bulunamadı.", 404)
            if before.state == "kapandi":
                raise HrError("Kapanmış pozisyon düzenlenemez.", 409)
            if before.state == "onayda":
                raise HrError("Onaydaki pozisyon düzenlenemez; önce geri çekin ya da onay sonucunu bekleyin.", 409)
        vals: dict[str, Any] = {}
        if "title" in body or before is None:
            title = clean(body.get("title"), 200)
            if not title:
                raise HrError("Pozisyon adı boş olamaz.")
            vals["title"] = title
        if "unitId" in body:
            uid = body.get("unitId") or None
            if uid and not c.execute(sa.select(H.UNITS.c.id).where(H.UNITS.c.id == uid, H.UNITS.c.tenant_id == tenant)).first():
                raise HrError("Birim bulunamadı.")
            vals["unit_id"] = uid
        if "hiringManager" in body:
            vals["hiring_manager"] = clean(body.get("hiringManager"), 120).lower() or None
        if "team" in body:
            vals["team_json"] = dump(_usernames(body.get("team")))
        if "competencies" in body:
            vals["competencies_json"] = dump(_competencies(body.get("competencies")))
        if "note" in body:
            vals["note"] = str(body.get("note") or "").strip()[:4000] or None
        if "postingText" in body:
            text = str(body.get("postingText") or "").strip()[:20000]
            vals["posting_text"] = text or None
            vals["posting_warnings_json"] = dump(X.discrimination_rules(text))
        vals["updated_at"] = t
        if before is None:
            pid = new_id("poz")
            c.execute(POSITIONS.insert().values(id=pid, tenant_id=tenant, state="taslak", created_by=actor, created_at=t, **vals))
            diff = {"yeni": vals["title"]}
        else:
            diff = {k: {"once": getattr(before, k), "sonra": v} for k, v in vals.items()
                    if k != "updated_at" and getattr(before, k) != v and k not in ("posting_text", "posting_warnings_json")}
            if "posting_text" in vals and before.posting_text != vals["posting_text"]:
                diff["ilanMetni"] = "değişti"
            c.execute(POSITIONS.update().where(POSITIONS.c.id == pid).values(**vals))
        r = c.execute(sa.select(POSITIONS).where(POSITIONS.c.id == pid)).first()
        return _pos_out(r, _units(c, tenant)), diff


def position_transition(engine: sa.engine.Engine, tenant: str, who: H.Who, pid: str, action: str,
                        note: str = "") -> dict[str, Any]:
    """submit (taslak → onayda), withdraw (onayda → taslak), approve (onayda → acik; gönderen onaylayamaz),
    reject (onayda → taslak, gerekçe şart), hold (acik → beklemede), resume (beklemede → acik), close (→ kapandi)."""
    ensure(engine)
    t = now()
    with engine.begin() as c:
        r = c.execute(sa.select(POSITIONS).where(POSITIONS.c.id == pid, POSITIONS.c.tenant_id == tenant)).first()
        if r is None:
            raise HrError("Pozisyon bulunamadı.", 404)
        vals: dict[str, Any] = {"updated_at": t}
        if action in ("approve", "reject"):
            if not who.can(F_POS_APPROVE):
                raise HrError("Pozisyon onayı rolünüzde yok.", 403)
            if r.state != "onayda":
                raise HrError("Pozisyon onayda değil.", 409)
            if r.submitted_by == who.user:
                raise HrError("Onaya gönderdiğiniz pozisyonu siz onaylayamazsınız; başka bir onaycı gerekir.", 409)
            if action == "approve":
                vals.update(state="acik", approved_by=who.user, approved_at=t, opened_at=t, review_note=note or None)
            else:
                if not note.strip():
                    raise HrError("Geri gönderme gerekçesini yazın.")
                vals.update(state="taslak", review_note=note.strip()[:2000])
        else:
            if not who.can(F_POS_OPEN):
                raise HrError("Pozisyon açma rolünüzde yok.", 403)
            allowed = {"submit": ("taslak", "onayda"), "withdraw": ("onayda", "taslak"), "hold": ("acik", "beklemede"),
                       "resume": ("beklemede", "acik")}
            if action == "close":
                if r.state == "kapandi":
                    raise HrError("Pozisyon zaten kapalı.", 409)
                vals.update(state="kapandi", closed_at=t)
            elif action in allowed:
                src, dst = allowed[action]
                if r.state != src:
                    raise HrError(f"Bu işlem yalnız «{POSITION_STATES[src]}» durumunda yapılır.", 409)
                if action == "submit":
                    if not _competencies(load(r.competencies_json, [])):
                        raise HrError("Onaya göndermeden önce yetkinlikleri yazın.")
                    vals.update(submitted_by=who.user, submitted_at=t, review_note=None)
                vals["state"] = dst
            else:
                raise HrError("Bilinmeyen işlem.", 400)
        c.execute(POSITIONS.update().where(POSITIONS.c.id == pid).values(**vals))
        return _pos_out(c.execute(sa.select(POSITIONS).where(POSITIONS.c.id == pid)).first(), _units(c, tenant))


def set_interview_kit(engine: sa.engine.Engine, tenant: str, pid: str, kit: list[dict[str, Any]]) -> None:
    with engine.begin() as c:
        c.execute(POSITIONS.update().where(POSITIONS.c.id == pid, POSITIONS.c.tenant_id == tenant)
                  .values(interview_kit_json=dump(kit), updated_at=now()))


# ------------------------------------------------------------------ adaylar


def _clean_email(v: Any) -> Optional[str]:
    s = clean(v, 254).lower()
    if not s:
        return None
    if "@" not in s or " " in s or "." not in s.split("@")[-1]:
        raise HrError("E-posta adresi geçersiz.")
    return s


def create_candidate(engine: sa.engine.Engine, tenant: str, actor: str, body: dict[str, Any], *,
                     source: str = "elle", source_ref: Optional[str] = None) -> str:
    ensure(engine)
    name = clean(body.get("fullName"), 200)
    if not name:
        raise HrError("Adayın adını yazın.")
    src = str(body.get("source") or source)
    if src not in SOURCES:
        raise HrError("Başvuru kaynağı geçersiz.")
    pid = body.get("positionId") or None
    t = now()
    with engine.begin() as c:
        if pid:
            p = c.execute(sa.select(POSITIONS.c.state).where(POSITIONS.c.id == pid, POSITIONS.c.tenant_id == tenant)).first()
            if p is None:
                raise HrError("Pozisyon bulunamadı.")
        cid = new_id("aday")
        c.execute(CANDIDATES.insert().values(
            id=cid, tenant_id=tenant, position_id=pid, full_name=name, email=_clean_email(body.get("email")),
            phone=clean(body.get("phone"), 40) or None, source=src, source_ref=source_ref, stage="basvurdu",
            stage_since=t, created_by=actor, created_at=t, updated_at=t))
        c.execute(STAGE_LOG.insert().values(tenant_id=tenant, candidate_id=cid, at=t, actor=actor, from_stage=None,
                                            to_stage="basvurdu", reason=None))
    return cid


def update_candidate(engine: sa.engine.Engine, tenant: str, who: H.Who, cid: str, body: dict[str, Any]) -> dict[str, Any]:
    """Ad, iletişim, pozisyon ve kaynak düzeltmesi (yalnız `ik.aday-hepsi`). Dönen: değişen alan adları (değer yok)."""
    if not who.can(F_ALL):
        raise HrError("Aday kaydını düzenleme rolünüzde yok.", 403)
    with engine.begin() as c:
        r = _load_candidate(c, tenant, who, cid)
        vals: dict[str, Any] = {}
        if "fullName" in body:
            name = clean(body.get("fullName"), 200)
            if not name:
                raise HrError("Adayın adı boş olamaz.")
            vals["full_name"] = name
        if "email" in body:
            vals["email"] = _clean_email(body.get("email"))
        if "phone" in body:
            vals["phone"] = clean(body.get("phone"), 40) or None
        if "positionId" in body:
            pid = body.get("positionId") or None
            if pid and not c.execute(sa.select(POSITIONS.c.id).where(POSITIONS.c.id == pid, POSITIONS.c.tenant_id == tenant)).first():
                raise HrError("Pozisyon bulunamadı.")
            vals["position_id"] = pid
        if "source" in body:
            if body.get("source") not in SOURCES:
                raise HrError("Başvuru kaynağı geçersiz.")
            vals["source"] = body["source"]
        changed = sorted(k for k, v in vals.items() if getattr(r, k) != v)
        if changed:
            c.execute(CANDIDATES.update().where(CANDIDATES.c.id == cid).values(**vals, updated_at=now()))
    return {"changed": changed}


def change_stage(engine: sa.engine.Engine, tenant: str, who: H.Who, cid: str, body: dict[str, Any]) -> dict[str, Any]:
    """Aşama değişikliği: her zaman bir kişinin kaydı. Sonuç aşaması `outcome` ister; işe alınan aday çalışan kaydına
    bağlanır. Dönen: {from, to, outcome, employeeId}."""
    ensure(engine)
    to = str(body.get("stage") or "")
    if to not in STAGES:
        raise HrError("Aşama geçersiz.")
    outcome = body.get("outcome") or None
    if to == "sonuc" and outcome not in OUTCOMES:
        raise HrError("Sonuç aşamasında sonucu seçin (işe alındı, ret, aday çekildi).")
    if to != "sonuc":
        outcome = None
    reason = str(body.get("reason") or "").strip()[:2000] or None
    t = now()
    employee_id = None
    with engine.begin() as c:
        r = _load_candidate(c, tenant, who, cid)
        if not can_decide(c, tenant, who, r):
            raise HrError("Bu adayın aşamasını değiştirme rolünüzde yok.", 403)
        if r.stage == to and (r.outcome or None) == outcome:
            raise HrError("Aday zaten bu aşamada.", 409)
        if r.outcome == "ise_alindi" and r.employee_id:
            raise HrError("İşe alınan adayın kaydı çalışan kaydına geçti; aşaması değiştirilemez.", 409)
        vals: dict[str, Any] = {"stage": to, "outcome": outcome, "stage_since": t, "updated_at": t,
                                "outcome_at": t if outcome else None}
        if outcome == "ise_alindi":
            pos = c.execute(sa.select(POSITIONS).where(POSITIONS.c.id == r.position_id)).first() if r.position_id else None
            employee_id = new_id("clsn")
            c.execute(H.EMPLOYEES.insert().values(
                id=employee_id, tenant_id=tenant, display_name=r.full_name, unit_id=pos.unit_id if pos else None,
                title=pos.title if pos else None, start_date=H.parse_date(body.get("startDate"), "İşe giriş"),
                status="aktif", source_json=dump({"display_name": "ik", "unit_id": "ik", "title": "ik"}),
                updated_by=who.user, updated_at=t))
            vals.update(employee_id=employee_id, retention_class="calisan", retention_until=None)
        elif not outcome:
            vals.update(retention_class=None, retention_until=None, retention_forced=None)
        c.execute(CANDIDATES.update().where(CANDIDATES.c.id == cid).values(**vals))
        c.execute(STAGE_LOG.insert().values(tenant_id=tenant, candidate_id=cid, at=t, actor=who.user, from_stage=r.stage,
                                            to_stage=to, outcome=outcome, reason=reason))
    if outcome in ("ret", "cekildi"):
        refresh_retention(engine, tenant, [cid])
    return {"from": r.stage, "to": to, "outcome": outcome, "employeeId": employee_id}


# ------------------------------------------------------------------ saklama


def refresh_retention(engine: sa.engine.Engine, tenant: str, ids: Optional[list[str]] = None) -> int:
    """Sonuçlanmış (ret / çekildi) adayların saklama sınıfı ve bitiş tarihi. Süre ayarı değişince hepsi yeniden hesaplanır."""
    ensure(engine)
    days = {k: H.keep_days(engine, tenant, k) for k in ("aday_ret", "aday_havuz")}
    changed = 0
    with engine.begin() as c:
        q = sa.select(CANDIDATES).where(CANDIDATES.c.tenant_id == tenant, CANDIDATES.c.purged_at.is_(None),
                                        CANDIDATES.c.outcome.in_(("ret", "cekildi")))
        if ids is not None:
            q = q.where(CANDIDATES.c.id.in_(ids or [""]))
        rows = c.execute(q).all()
        pool = {sid for (sid,) in c.execute(sa.select(H.CONSENTS.c.subject_id).where(
            H.CONSENTS.c.tenant_id == tenant, H.CONSENTS.c.subject_type == "aday", H.CONSENTS.c.purpose == "aday_havuzu",
            H.CONSENTS.c.withdrawn_at.is_(None))).all()}
        for r in rows:
            cls = "aday_havuz" if r.id in pool else "aday_ret"
            base = H.aware(r.outcome_at) or H.aware(r.stage_since)
            until = base + timedelta(days=days[cls]) if days[cls] else None
            forced = H.aware(r.retention_forced)
            if forced is not None and cls == "aday_ret":
                until = forced if until is None else min(until, forced)
            if r.retention_class != cls or H.aware(r.retention_until) != until:
                c.execute(CANDIDATES.update().where(CANDIDATES.c.id == r.id).values(retention_class=cls, retention_until=until))
                changed += 1
    return changed


def on_consent_withdrawn(engine: sa.engine.Engine, tenant: str, subject_type: str, subject_id: str, purpose: str) -> None:
    """Havuz rızası geri çekildi: sonuçlanmış aday hemen imha kuyruğuna girer (süreç sürüyorsa değerlendirme sürer)."""
    if subject_type != "aday" or purpose != "aday_havuzu":
        return
    with engine.begin() as c:
        c.execute(CANDIDATES.update().where(CANDIDATES.c.id == subject_id, CANDIDATES.c.tenant_id == tenant,
                                            CANDIDATES.c.outcome.in_(("ret", "cekildi")))
                  .values(retention_forced=now()))
    refresh_retention(engine, tenant, [subject_id])


def due_candidates(engine: sa.engine.Engine, tenant: str, t: datetime) -> list[str]:
    refresh_retention(engine, tenant)
    with engine.connect() as c:
        return [r[0] for r in c.execute(sa.select(CANDIDATES.c.id).where(
            CANDIDATES.c.tenant_id == tenant, CANDIDATES.c.purged_at.is_(None), CANDIDATES.c.retention_until.isnot(None),
            CANDIDATES.c.retention_until <= t, CANDIDATES.c.outcome.in_(("ret", "cekildi")))).all()]


def purge_candidates(engine: sa.engine.Engine, tenant: str, ids: list[str], t: datetime) -> int:
    """Kişisel veriyi siler; aday satırı istatistik için kimliği, aşaması ve tarihleriyle kalır."""
    if not ids:
        return 0
    with engine.begin() as c:
        c.execute(FILES.delete().where(FILES.c.tenant_id == tenant, FILES.c.candidate_id.in_(ids)))
        c.execute(EVIDENCE.delete().where(EVIDENCE.c.tenant_id == tenant, EVIDENCE.c.candidate_id.in_(ids)))
        c.execute(NOTES.delete().where(NOTES.c.tenant_id == tenant, NOTES.c.candidate_id.in_(ids)))
        c.execute(INTERVIEWS.delete().where(INTERVIEWS.c.tenant_id == tenant, INTERVIEWS.c.candidate_id.in_(ids)))
        c.execute(MESSAGES.delete().where(MESSAGES.c.tenant_id == tenant, MESSAGES.c.candidate_id.in_(ids)))
        c.execute(STAGE_LOG.update().where(STAGE_LOG.c.tenant_id == tenant, STAGE_LOG.c.candidate_id.in_(ids)).values(reason=None))
        c.execute(REMINDERS.delete().where(REMINDERS.c.tenant_id == tenant, REMINDERS.c.candidate_id.in_(ids)))
        n = c.execute(CANDIDATES.update().where(CANDIDATES.c.tenant_id == tenant, CANDIDATES.c.id.in_(ids),
                                                CANDIDATES.c.purged_at.is_(None))
                      .values(full_name="(imha edildi)", email=None, phone=None, source_ref=None, purged_at=t, updated_at=t)).rowcount
    return int(n or 0)


def due_notes(engine: sa.engine.Engine, tenant: str, t: datetime) -> list[str]:
    days = H.keep_days(engine, tenant, "mulakat_notu")
    if not days:
        return []
    limit = t - timedelta(days=days)
    with engine.connect() as c:
        return [r[0] for r in c.execute(sa.select(NOTES.c.id).where(
            NOTES.c.tenant_id == tenant, sa.func.coalesce(NOTES.c.submitted_at, NOTES.c.updated_at) < limit)).all()]


def purge_notes(engine: sa.engine.Engine, tenant: str, ids: list[str], t: datetime) -> int:
    with engine.begin() as c:
        return int(c.execute(NOTES.delete().where(NOTES.c.tenant_id == tenant, NOTES.c.id.in_(ids))).rowcount or 0)


def register_hooks() -> None:
    """İK-0 bağları: imha, rıza geri çekme, rıza kaydının ait olduğu aday."""
    H.register_purger(H.Purger("aday", "Aday verisi (ret / aday çekildi)", due_candidates, purge_candidates))
    H.register_purger(H.Purger("mulakat_notu", "Mülakat notları", due_notes, purge_notes))
    H.register_withdraw_hook(on_consent_withdrawn)
    H.register_subject_check("aday", candidate_exists)


def delete_on_request(engine: sa.engine.Engine, tenant: str, who: H.Who, cid: str, reason: str) -> int:
    """İlgili kişi talebiyle imha (KVKK md. 7/11); tutanak «talep» sınıfıyla yazılır."""
    if not who.can(F_KVKK):
        raise HrError("Talep üzerine imha KVKK yönetimi yetkisi ister.", 403)
    if not reason.strip():
        raise HrError("Talebin kaydını (tarih, kanal) yazın.")
    with engine.connect() as c:
        r = _load_candidate(c, tenant, who, cid)
        if r.outcome == "ise_alindi":
            raise HrError("İşe alınan adayın kaydı özlük dosyasına geçti; buradan silinemez.", 409)
    t = now()
    n = purge_candidates(engine, tenant, [cid], t)
    H.record_purge(engine, tenant, "talep", n, {"ids": [cid], "gerekce": reason.strip()[:500]}, None, who.user, t)
    return n


# ------------------------------------------------------------------ pano


def pipeline(engine: sa.engine.Engine, tenant: str, who: H.Who, position_id: str = "", sla_days: Optional[int] = None) -> dict[str, Any]:
    """Aşama sütunları (bütün görünür adaylar; sayı tavanı yok) ve dört sayaç."""
    ensure(engine)
    t = now()
    with engine.connect() as c:
        q = sa.select(CANDIDATES).where(CANDIDATES.c.tenant_id == tenant, CANDIDATES.c.purged_at.is_(None))
        flt = candidate_filter(c, tenant, who)
        if flt is not None:
            q = q.where(flt)
        if position_id == "-":
            q = q.where(CANDIDATES.c.position_id.is_(None))
        elif position_id:
            q = q.where(CANDIDATES.c.position_id == position_id)
        rows = c.execute(q.order_by(CANDIDATES.c.stage_since)).all()
        titles = dict(c.execute(sa.select(POSITIONS.c.id, POSITIONS.c.title).where(POSITIONS.c.tenant_id == tenant)).all())
        ids = [r.id for r in rows]
        sent = {(m.candidate_id, m.kind) for m in c.execute(sa.select(MESSAGES.c.candidate_id, MESSAGES.c.kind).where(
            MESSAGES.c.tenant_id == tenant, MESSAGES.c.status == "gonderildi", MESSAGES.c.candidate_id.in_(ids or [""]))).all()}
        has_ev = {x for (x,) in c.execute(sa.select(EVIDENCE.c.candidate_id).where(
            EVIDENCE.c.tenant_id == tenant, EVIDENCE.c.candidate_id.in_(ids or [""])).distinct()).all()}
        open_positions = c.execute(sa.select(sa.func.count()).select_from(POSITIONS).where(
            POSITIONS.c.tenant_id == tenant, POSITIONS.c.state == "acik")).scalar() or 0
    show_name = who.can(F_ALL, F_SEE)
    columns: dict[str, list[dict[str, Any]]] = {k: [] for k in STAGES}
    over, waiting_reply, stale30, week = 0, 0, 0, 0
    for r in rows:
        days = _days(r.stage_since, t)
        is_over = sla_days is not None and r.stage != "sonuc" and days is not None and days > sla_days
        needs_reply = r.stage == "sonuc" and r.outcome in ("ret", "ise_alindi") and \
            (r.id, "ret" if r.outcome == "ret" else "teklif") not in sent
        over += int(is_over)
        waiting_reply += int(needs_reply)
        stale30 += int(r.stage != "sonuc" and (_days(r.created_at, t) or 0) > 30)
        week += int(H.aware(r.created_at) >= t - timedelta(days=7))
        columns[r.stage].append({
            "id": r.id, "name": r.full_name if show_name else "", "positionId": r.position_id,
            "positionTitle": titles.get(r.position_id or "", ""), "source": r.source, "stage": r.stage,
            "outcome": r.outcome, "outcomeLabel": OUTCOMES.get(r.outcome or "", ""), "daysInStage": days,
            "overSla": is_over, "needsReply": needs_reply, "hasEvidence": r.id in has_ev, "createdAt": iso(r.created_at)})
    return {
        "stages": STAGES, "outcomes": OUTCOMES, "columns": columns,
        "counters": {"openPositions": int(open_positions), "thisWeek": week, "overSla": over if sla_days is not None else None,
                     "slaDays": sla_days, "waitingReply": waiting_reply, "unanswered30": stale30},
        "total": len(rows),
    }


# ------------------------------------------------------------------ dosyalar


def add_file(engine: sa.engine.Engine, tenant: str, who: H.Who, cid: str, filename: str, data: bytes,
             max_mb: int) -> dict[str, Any]:
    if not who.can(F_ALL):
        raise HrError("Özgeçmiş yükleme bütün adayları görme yetkisi ister.", 403)
    if len(data) > max_mb * 1024 * 1024:
        raise HrError(f"Dosya {max_mb} MB sınırını aşıyor.", 413)
    name = clean(filename, 255).replace("/", "_").replace("\\", "_") or "ozgecmis"
    text = X.extract_text(name, data)
    masked, counts = X.rule_mask(text)
    with engine.connect() as c:
        _load_candidate(c, tenant, who, cid)
    return _store_file(engine, tenant, who.user, cid, name, data, text, masked, counts)


def _store_file(engine: sa.engine.Engine, tenant: str, actor: str, cid: str, name: str, data: bytes, text: str,
                masked: str, counts: dict[str, int]) -> dict[str, Any]:
    fid = new_id("dsy")
    t = now()
    with engine.begin() as c:
        c.execute(FILES.insert().values(id=fid, tenant_id=tenant, candidate_id=cid, filename=name,
                                        mime=X.EXTENSIONS.get(X.ext_of(name), "application/octet-stream"), size=len(data),
                                        blob=data, extracted_text=text, masked_text=masked, mask_json=dump(counts),
                                        model_checked=False, created_by=actor, created_at=t))
        c.execute(CANDIDATES.update().where(CANDIDATES.c.id == cid).values(updated_at=t))
    return {"id": fid, "filename": name, "size": len(data), "maskCounts": counts}


def file_blob(engine: sa.engine.Engine, tenant: str, who: H.Who, cid: str, fid: str) -> tuple[bytes, str, str]:
    if not who.can(F_ALL):
        raise HrError("Özgün dosya yalnız bütün adayları görme yetkisiyle indirilir; maskeli metin aday kartında.", 403)
    with engine.connect() as c:
        _load_candidate(c, tenant, who, cid)
        r = c.execute(sa.select(FILES).where(FILES.c.id == fid, FILES.c.candidate_id == cid, FILES.c.tenant_id == tenant)).first()
    if r is None or r.blob is None:
        raise HrError("Dosya bulunamadı.", 404)
    return bytes(r.blob), r.filename, r.mime or "application/octet-stream"


def delete_file(engine: sa.engine.Engine, tenant: str, who: H.Who, cid: str, fid: str) -> None:
    if not who.can(F_ALL):
        raise HrError("Dosya silme bütün adayları görme yetkisi ister.", 403)
    with engine.begin() as c:
        _load_candidate(c, tenant, who, cid)
        n = c.execute(FILES.delete().where(FILES.c.id == fid, FILES.c.candidate_id == cid, FILES.c.tenant_id == tenant)).rowcount
    if not n:
        raise HrError("Dosya bulunamadı.", 404)


# ------------------------------------------------------------------ kanıtlı özet


def evidence_input(engine: sa.engine.Engine, tenant: str, who: H.Who, cid: str) -> dict[str, Any]:
    """Kanıt işi için pozisyon ve dosyalar. Kanıt işini başlatmak aşama kararı ya da bütün aday yetkisi ister."""
    with engine.connect() as c:
        r = _load_candidate(c, tenant, who, cid)
        if not (who.can(F_ALL) or can_decide(c, tenant, who, r)):
            raise HrError("Kanıtlı özet çıkarma rolünüzde yok.", 403)
        if not r.position_id:
            raise HrError("Adayın pozisyonu yok; kanıtlı özet pozisyonun yetkinliklerine göre çıkar.")
        p = c.execute(sa.select(POSITIONS).where(POSITIONS.c.id == r.position_id)).first()
        files = c.execute(sa.select(FILES.c.id, FILES.c.masked_text, FILES.c.model_checked).where(
            FILES.c.candidate_id == cid, FILES.c.tenant_id == tenant).order_by(FILES.c.created_at)).all()
    if not files:
        raise HrError("Önce özgeçmiş yükleyin.")
    return {"title": p.title, "competencies": load(p.competencies_json, []) or [],
            "files": [{"id": f.id, "masked": f.masked_text or "", "checked": bool(f.model_checked)} for f in files]}


def run_evidence(engine: sa.engine.Engine, tenant: str, cid: str, inp: dict[str, Any],
                 chat: Callable[[list[dict[str, str]]], str], progress: Callable[[int, int], None]) -> dict[str, Any]:
    """Önce modelle özel nitelikli satır maskesi (her dosya bir kez), sonra kanıt. Sonuç tabloya; özet döner."""
    model_masked = 0
    total_steps = len(inp["files"]) + 1
    for i, f in enumerate(inp["files"], 1):
        if not f["checked"]:
            text, n = X.model_mask(f["masked"], chat)
            model_masked += n
            f["masked"] = text
            with engine.begin() as c:
                c.execute(FILES.update().where(FILES.c.id == f["id"]).values(masked_text=text, model_checked=True))
        progress(i, total_steps)
    joined = "\n".join(f["masked"] for f in inp["files"])
    rows = X.evidence(inp["title"], inp["competencies"], joined, chat)
    run_id = new_id("kanit")
    t = now()
    with engine.begin() as c:
        c.execute(EVIDENCE.delete().where(EVIDENCE.c.candidate_id == cid, EVIDENCE.c.tenant_id == tenant))
        for r in rows:
            quotes = r["quotes"] or [None]
            for q in quotes:
                c.execute(EVIDENCE.insert().values(id=new_id("kn"), tenant_id=tenant, candidate_id=cid, competency=r["competency"][:300],
                                                   line_no=q["line"] if q else None, quote=q["text"] if q else None,
                                                   verdict=r["verdict"], model_run_id=run_id, created_at=t))
    progress(total_steps, total_steps)
    return {"competencies": len(rows), "withEvidence": sum(1 for r in rows if r["verdict"] == "kanit_var"),
            "modelMaskedLines": model_masked, "runId": run_id}


# ------------------------------------------------------------------ mülakat ve notlar


def create_interview(engine: sa.engine.Engine, tenant: str, who: H.Who, body: dict[str, Any]) -> dict[str, Any]:
    cid = str(body.get("candidateId") or "")
    starts = H.aware(body.get("startsAt")) if body.get("startsAt") else None
    if starts is None:
        raise HrError("Mülakat tarih ve saatini seçin.")
    interviewers = _usernames(body.get("interviewers"))
    if not interviewers:
        raise HrError("En az bir görüşmeci seçin.")
    iid = new_id("mlk")
    with engine.begin() as c:
        r = _load_candidate(c, tenant, who, cid)
        if not can_decide(c, tenant, who, r):
            raise HrError("Mülakat planlama aşama kararı yetkisi ister.", 403)
        c.execute(INTERVIEWS.insert().values(id=iid, tenant_id=tenant, candidate_id=cid, starts_at=starts,
                                             location=clean(body.get("location"), 300) or None,
                                             room_booking_id=clean(body.get("roomBookingId"), 80) or None,
                                             interviewers_json=dump(interviewers), created_by=who.user, created_at=now()))
    return {"id": iid, "candidateId": cid, "startsAt": iso(starts), "interviewers": interviewers}


def save_note(engine: sa.engine.Engine, tenant: str, who: H.Who, iid: str, body: dict[str, Any]) -> dict[str, Any]:
    """Görüşmecinin notu ve 1–5 puanları. Teslim edilen not değiştirilemez."""
    scores_in = body.get("scores") or {}
    if not isinstance(scores_in, dict):
        raise HrError("Puanlar yetkinlik → 1..5 biçiminde olmalı.")
    scores: dict[str, int] = {}
    for k, v in scores_in.items():
        if v in (None, ""):
            continue
        try:
            n = int(v)
        except (TypeError, ValueError):
            raise HrError("Puan 1 ile 5 arasında olmalı.") from None
        if not 1 <= n <= 5:
            raise HrError("Puan 1 ile 5 arasında olmalı.")
        scores[clean(k, 300)] = n
    text = str(body.get("note") or "").strip()[:8000]
    submit = bool(body.get("submit"))
    t = now()
    with engine.begin() as c:
        iv = c.execute(sa.select(INTERVIEWS).where(INTERVIEWS.c.id == iid, INTERVIEWS.c.tenant_id == tenant)).first()
        if iv is None:
            raise HrError("Mülakat bulunamadı.", 404)
        if who.user not in (load(iv.interviewers_json, []) or []):
            raise HrError("Yalnız bu mülakatın görüşmecileri not girer.", 403)
        old = c.execute(sa.select(NOTES).where(NOTES.c.interview_id == iid, NOTES.c.author == who.user)).first()
        if old is not None and old.submitted_at is not None:
            raise HrError("Teslim ettiğiniz not değiştirilemez.", 409)
        vals = dict(scores_json=dump(scores), note=text or None, submitted_at=t if submit else None, updated_at=t)
        if old is None:
            nid = new_id("not")
            c.execute(NOTES.insert().values(id=nid, tenant_id=tenant, interview_id=iid, candidate_id=iv.candidate_id,
                                            author=who.user, **vals))
        else:
            nid = old.id
            c.execute(NOTES.update().where(NOTES.c.id == nid).values(**vals))
    return {"id": nid, "submitted": submit}


# ------------------------------------------------------------------ aday kartı


def detail(engine: sa.engine.Engine, tenant: str, who: H.Who, cid: str, sla_days: Optional[int]) -> dict[str, Any]:
    ensure(engine)
    full = who.can(F_ALL)
    t = now()
    with engine.connect() as c:
        r = _load_candidate(c, tenant, who, cid)
        pos = c.execute(sa.select(POSITIONS).where(POSITIONS.c.id == r.position_id)).first() if r.position_id else None
        files = c.execute(sa.select(FILES.c.id, FILES.c.filename, FILES.c.size, FILES.c.created_at, FILES.c.mask_json,
                                    FILES.c.model_checked, FILES.c.masked_text, FILES.c.extracted_text)
                          .where(FILES.c.candidate_id == cid, FILES.c.tenant_id == tenant).order_by(FILES.c.created_at)).all()
        ev = c.execute(sa.select(EVIDENCE).where(EVIDENCE.c.candidate_id == cid, EVIDENCE.c.tenant_id == tenant)
                       .order_by(EVIDENCE.c.competency, EVIDENCE.c.line_no)).all()
        ivs = c.execute(sa.select(INTERVIEWS).where(INTERVIEWS.c.candidate_id == cid, INTERVIEWS.c.tenant_id == tenant)
                        .order_by(INTERVIEWS.c.starts_at)).all()
        notes = c.execute(sa.select(NOTES).where(NOTES.c.candidate_id == cid, NOTES.c.tenant_id == tenant)).all()
        msgs = c.execute(sa.select(MESSAGES).where(MESSAGES.c.candidate_id == cid, MESSAGES.c.tenant_id == tenant)
                         .order_by(MESSAGES.c.created_at)).all()
        log_rows = c.execute(sa.select(STAGE_LOG).where(STAGE_LOG.c.candidate_id == cid, STAGE_LOG.c.tenant_id == tenant)
                             .order_by(STAGE_LOG.c.id)).all()
        decide = can_decide(c, tenant, who, r)
    comps: dict[str, dict[str, Any]] = {}
    order = load(pos.competencies_json, []) if pos else []
    for e in ev:
        item = comps.setdefault(e.competency, {"competency": e.competency, "verdict": e.verdict, "quotes": []})
        if e.quote:
            item["quotes"].append({"line": e.line_no, "text": e.quote})
    evidence_rows = sorted(comps.values(), key=lambda x: order.index(x["competency"]) if x["competency"] in order else 999)
    interviews = []
    for iv in ivs:
        ivers = load(iv.interviewers_json, []) or []
        mine = next((n for n in notes if n.interview_id == iv.id and n.author == who.user), None)
        hide_others = who.user in ivers and (mine is None or mine.submitted_at is None)
        shown = []
        for n in notes:
            if n.interview_id != iv.id:
                continue
            if n.author != who.user and (hide_others or (n.submitted_at is None) or not (full or who.user in ivers or decide)):
                continue
            shown.append({"id": n.id, "author": n.author, "scores": load(n.scores_json, {}) or {}, "note": n.note or "",
                          "submittedAt": iso(n.submitted_at), "mine": n.author == who.user})
        interviews.append({"id": iv.id, "startsAt": iso(iv.starts_at), "location": iv.location or "",
                           "roomBookingId": iv.room_booking_id, "interviewers": ivers, "notes": shown,
                           "hiddenOthers": hide_others and any(n.interview_id == iv.id and n.author != who.user for n in notes),
                           "iAmInterviewer": who.user in ivers})
    days = _days(r.stage_since, t)
    return {
        "id": r.id, "fullName": r.full_name, "email": r.email if full else None, "phone": r.phone if full else None,
        "source": r.source, "sourceLabel": SOURCES.get(r.source, r.source), "stage": r.stage, "stageLabel": STAGES[r.stage],
        "outcome": r.outcome, "outcomeLabel": OUTCOMES.get(r.outcome or "", ""), "stageSince": iso(r.stage_since),
        "daysInStage": days, "overSla": sla_days is not None and r.stage != "sonuc" and (days or 0) > sla_days,
        "createdAt": iso(r.created_at), "employeeId": r.employee_id,
        "position": ({"id": pos.id, "title": pos.title, "competencies": order, "interviewKit": load(pos.interview_kit_json, []) or []}
                     if pos else None),
        "retention": {"class": r.retention_class, "label": (H.DATA_CLASSES.get(r.retention_class or "", {}) or {}).get("label")
                      or ("Çalışan kaydı" if r.retention_class == "calisan" else None),
                      "until": iso(r.retention_until), "forced": iso(r.retention_forced)},
        "files": [{"id": f.id, "filename": f.filename, "size": f.size, "createdAt": iso(f.created_at),
                   "maskCounts": load(f.mask_json, {}) or {}, "modelChecked": bool(f.model_checked),
                   "maskedText": f.masked_text or "", "originalText": (f.extracted_text or "") if full else None} for f in files],
        "evidence": evidence_rows,
        "evidenceAt": iso(max((e.created_at for e in ev), default=None)) if ev else None,
        "interviews": interviews,
        "messages": [_msg_out(m) for m in msgs] if (full or who.can(F_LETTERS)) else [],
        "stageLog": [{"at": iso(x.at), "actor": x.actor, "from": x.from_stage, "to": x.to_stage, "outcome": x.outcome,
                      "reason": x.reason or ""} for x in log_rows],
        "can": {"decide": decide, "edit": full, "files": full, "downloadOriginal": full,
                "letters": who.can(F_LETTERS) and (full or decide), "approveOffer": who.can(F_OFFER_APPROVE),
                "export": who.can(F_EXPORT) and full, "delete": who.can(F_KVKK) and full, "consents": full},
    }


# ------------------------------------------------------------------ şablonlar


def _tpl_out(r: Any) -> dict[str, Any]:
    return {"id": r.id, "kind": r.kind, "kindLabel": X.TEMPLATE_KINDS.get(r.kind, r.kind), "name": r.name, "body": r.body,
            "version": r.version, "state": r.state, "stateLabel": TEMPLATE_STATES.get(r.state, r.state),
            "placeholders": X.placeholders(r.body), "unknown": [p for p in X.placeholders(r.body) if p not in X.FIELDS],
            "updatedBy": r.updated_by, "updatedAt": iso(r.updated_at)}


def list_templates(engine: sa.engine.Engine, tenant: str, kind: str = "") -> list[dict[str, Any]]:
    ensure(engine)
    q = sa.select(TEMPLATES).where(TEMPLATES.c.tenant_id == tenant)
    if kind:
        q = q.where(TEMPLATES.c.kind == kind)
    with engine.connect() as c:
        return [_tpl_out(r) for r in c.execute(q.order_by(TEMPLATES.c.kind, TEMPLATES.c.name)).all()]


def save_template(engine: sa.engine.Engine, tenant: str, actor: str, body: dict[str, Any],
                  tid: Optional[str] = None) -> tuple[dict[str, Any], dict[str, Any]]:
    ensure(engine)
    t = now()
    with engine.begin() as c:
        before = None
        if tid:
            before = c.execute(sa.select(TEMPLATES).where(TEMPLATES.c.id == tid, TEMPLATES.c.tenant_id == tenant)).first()
            if before is None:
                raise HrError("Şablon bulunamadı.", 404)
        kind = str(body.get("kind") or (before.kind if before is not None else ""))
        if kind not in X.TEMPLATE_KINDS:
            raise HrError("Şablon türü geçersiz.")
        name = clean(body.get("name"), 200) if "name" in body or before is None else before.name
        if not name:
            raise HrError("Şablonun adını yazın.")
        text = str(body.get("body")).strip() if "body" in body else (before.body if before is not None else "")
        if not text:
            raise HrError("Şablon metni boş olamaz.")
        state = str(body.get("state") or (before.state if before is not None else "taslak"))
        if state not in TEMPLATE_STATES:
            raise HrError("Şablon durumu geçersiz.")
        if kind == "ilan" and X.discrimination_rules(text) and state == "yururlukte":
            raise HrError("Şablonda ayrımcı koşul olabilecek bir ifade var; düzeltmeden yürürlüğe alınamaz.")
        if before is None:
            tid = new_id("sbl")
            c.execute(TEMPLATES.insert().values(id=tid, tenant_id=tenant, kind=kind, name=name, body=text[:40000], version=1,
                                                state=state, updated_by=actor, updated_at=t))
            diff = {"yeni": name, "tur": kind}
        else:
            version = before.version + (1 if text != before.body else 0)
            c.execute(TEMPLATES.update().where(TEMPLATES.c.id == tid).values(kind=kind, name=name, body=text[:40000],
                                                                             version=version, state=state, updated_by=actor, updated_at=t))
            diff = {k: v for k, v in (("ad", name != before.name), ("metin", text != before.body), ("durum", state != before.state),
                                      ("tur", kind != before.kind)) if v}
        return _tpl_out(c.execute(sa.select(TEMPLATES).where(TEMPLATES.c.id == tid)).first()), diff


def active_template(c: Any, tenant: str, kind: str, tid: Optional[str] = None) -> Any:
    q = sa.select(TEMPLATES).where(TEMPLATES.c.tenant_id == tenant, TEMPLATES.c.kind == kind)
    if tid:
        q = q.where(TEMPLATES.c.id == tid)
    else:
        q = q.where(TEMPLATES.c.state == "yururlukte")
    return c.execute(q.order_by(TEMPLATES.c.updated_at.desc()).limit(1)).first()


# ------------------------------------------------------------------ yazışma


def _msg_out(m: Any) -> dict[str, Any]:
    return {"id": m.id, "kind": m.kind, "kindLabel": X.TEMPLATE_KINDS.get(m.kind, m.kind), "templateId": m.template_id,
            "templateVersion": m.template_version, "body": m.body, "status": m.status,
            "statusLabel": MESSAGE_STATES.get(m.status, m.status), "createdBy": m.created_by, "createdAt": iso(m.created_at),
            "approvedBy": m.approved_by, "approvedAt": iso(m.approved_at), "sentBy": m.sent_by, "sentAt": iso(m.sent_at),
            "channel": m.channel, "note": m.note or ""}


def letter_values(c: Any, tenant: str, cand: Any, company: str, extra: dict[str, Any], signer: str,
                  notice: Optional[dict[str, Any]]) -> dict[str, str]:
    pos = c.execute(sa.select(POSITIONS).where(POSITIONS.c.id == cand.position_id)).first() if cand.position_id else None
    unit = ""
    if pos is not None and pos.unit_id:
        unit = c.execute(sa.select(H.UNITS.c.name).where(H.UNITS.c.id == pos.unit_id)).scalar() or ""
    vals = {"aday_adi": cand.full_name, "pozisyon": pos.title if pos is not None else "", "birim": unit, "sirket": company,
            "tarih": now().astimezone().strftime("%d.%m.%Y"), "imza": signer,
            "aydinlatma_metni": f"{notice['title']} (sürüm {notice['version']})" if notice else ""}
    for k in ("gorusme_tarihi", "gorusme_yeri"):
        if extra.get(k):
            vals[k] = clean(extra[k], 300)
    return {k: v for k, v in vals.items() if v}


def draft_letter(engine: sa.engine.Engine, tenant: str, who: H.Who, cid: str, kind: str, body: dict[str, Any],
                 company: str, soften: Optional[Callable[[str, list[str]], tuple[str, Optional[str]]]] = None) -> dict[str, Any]:
    if kind not in ("alindi", "davet", "teklif", "ret"):
        raise HrError("Mektup türü geçersiz.")
    if not who.can(F_LETTERS):
        raise HrError("Adaya yazışma rolünüzde yok.", 403)
    notice = H.current_notice(engine, tenant, "aday")
    with engine.connect() as c:
        r = _load_candidate(c, tenant, who, cid)
        if not (who.can(F_ALL) or can_decide(c, tenant, who, r)):
            raise HrError("Bu adaya yazışma rolünüzde yok.", 403)
        tpl = active_template(c, tenant, kind, body.get("templateId") or None)
        if tpl is None:
            raise HrError(f"«{X.TEMPLATE_KINDS[kind]}» için yürürlükte şablon yok; İK belgelerinden ekleyin.", 409)
        vals = letter_values(c, tenant, r, company, body.get("fields") or {}, who.display, notice)
    text, missing = X.fill(tpl.body, vals)
    note = None
    if body.get("soften") and soften is not None:
        text, note = soften(text, list(vals.values()))
    mid = new_id("msj")
    with engine.begin() as c:
        c.execute(MESSAGES.insert().values(id=mid, tenant_id=tenant, candidate_id=cid, kind=kind, template_id=tpl.id,
                                           template_version=tpl.version, body=text, status="taslak", created_by=who.user,
                                           created_at=now()))
        m = c.execute(sa.select(MESSAGES).where(MESSAGES.c.id == mid)).first()
    return {**_msg_out(m), "missing": missing, "softenNote": note}


def queue_ack(engine: sa.engine.Engine, tenant: str, cid: str, company: str) -> Optional[str]:
    """«Başvurunuz alındı» taslağı (yürürlükte şablon varsa). Gönderilmez; İK gönderip «gönderildi» der."""
    notice = H.current_notice(engine, tenant, "aday")
    with engine.connect() as c:
        tpl = active_template(c, tenant, "alindi")
        if tpl is None:
            return None
        r = c.execute(sa.select(CANDIDATES).where(CANDIDATES.c.id == cid)).first()
        vals = letter_values(c, tenant, r, company, {}, f"{company} İnsan Kaynakları", notice)
    text, _ = X.fill(tpl.body, vals)
    mid = new_id("msj")
    with engine.begin() as c:
        c.execute(MESSAGES.insert().values(id=mid, tenant_id=tenant, candidate_id=cid, kind="alindi", template_id=tpl.id,
                                           template_version=tpl.version, body=text, status="taslak", created_by="sistem",
                                           created_at=now()))
    return mid


def _msg_for(c: Any, tenant: str, who: H.Who, mid: str) -> tuple[Any, Any]:
    m = c.execute(sa.select(MESSAGES).where(MESSAGES.c.id == mid, MESSAGES.c.tenant_id == tenant)).first()
    if m is None:
        raise HrError("Yazışma bulunamadı.", 404)
    cand = _load_candidate(c, tenant, who, m.candidate_id)
    return m, cand


def message_action(engine: sa.engine.Engine, tenant: str, who: H.Who, mid: str, action: str,
                   body: dict[str, Any]) -> dict[str, Any]:
    """edit (taslak), submit (teklif: taslak → onayda), approve / reject (onayda; hazırlayan onaylayamaz),
    sent (insan gönderdi: kanal + tarih; teklif için onay şart), cancel."""
    t = now()
    with engine.begin() as c:
        m, cand = _msg_for(c, tenant, who, mid)
        vals: dict[str, Any] = {}
        if action in ("approve", "reject"):
            if not who.can(F_OFFER_APPROVE):
                raise HrError("Teklif onayı rolünüzde yok.", 403)
            if m.status != "onayda":
                raise HrError("Yazışma onayda değil.", 409)
            if m.created_by == who.user:
                raise HrError("Hazırladığınız teklifi siz onaylayamazsınız.", 409)
            if action == "approve":
                vals.update(status="onaylandi", approved_by=who.user, approved_at=t)
            else:
                note = str(body.get("note") or "").strip()
                if not note:
                    raise HrError("Geri gönderme gerekçesini yazın.")
                vals.update(status="taslak", note=note[:2000])
        else:
            if not who.can(F_LETTERS) or not (who.can(F_ALL) or can_decide(c, tenant, who, cand)):
                raise HrError("Bu adaya yazışma rolünüzde yok.", 403)
            if action == "edit":
                if m.status != "taslak":
                    raise HrError("Yalnız taslak düzenlenir.", 409)
                text = str(body.get("body") or "").strip()
                if not text:
                    raise HrError("Mektup metni boş olamaz.")
                vals["body"] = text[:40000]
            elif action == "submit":
                if m.kind != "teklif":
                    raise HrError("Yalnız teklif mektubu onaya gönderilir.", 409)
                if m.status != "taslak":
                    raise HrError("Yalnız taslak onaya gönderilir.", 409)
                vals.update(status="onayda", note=None)
            elif action == "sent":
                if m.status in ("gonderildi", "iptal"):
                    raise HrError("Bu yazışma kapanmış.", 409)
                if m.kind == "teklif" and m.status != "onaylandi":
                    raise HrError("Teklif mektubu gönderilmeden önce onaylanmalı.", 409)
                if m.kind != "teklif" and m.status != "taslak":
                    raise HrError("Yazışma taslak değil.", 409)
                channel = str(body.get("channel") or "eposta")
                if channel not in SEND_CHANNELS:
                    raise HrError("Gönderim kanalı geçersiz.")
                sent_at = H.aware(body.get("sentAt")) if body.get("sentAt") else t
                if sent_at > t + timedelta(minutes=5):
                    raise HrError("Gönderim tarihi gelecekte olamaz.")
                vals.update(status="gonderildi", sent_by=who.user, sent_at=sent_at, channel=channel)
            elif action == "cancel":
                if m.status in ("gonderildi", "iptal"):
                    raise HrError("Bu yazışma kapanmış.", 409)
                vals["status"] = "iptal"
            else:
                raise HrError("Bilinmeyen işlem.", 400)
        c.execute(MESSAGES.update().where(MESSAGES.c.id == mid).values(**vals))
        return _msg_out(c.execute(sa.select(MESSAGES).where(MESSAGES.c.id == mid)).first())


def message_document(engine: sa.engine.Engine, tenant: str, who: H.Who, mid: str) -> tuple[bytes, str]:
    from semantic_bridge.contracts_docs import docx_from_text

    with engine.connect() as c:
        m, _ = _msg_for(c, tenant, who, mid)
    if not (who.can(F_LETTERS) or who.can(F_ALL)):
        raise HrError("Yazışma belgesi rolünüzde yok.", 403)
    title = X.TEMPLATE_KINDS.get(m.kind, "Mektup")
    return docx_from_text(m.body, title), f"{m.kind}-{m.id[-6:]}.docx"


# ------------------------------------------------------------------ e-postadan başvuru (H4 → M55)


def intake(engine: sa.engine.Engine, tenant: str, body: dict[str, Any], company: str, max_mb: int) -> dict[str, Any]:
    """Kurumsal e-posta modülünün «iş başvurusu» iletisini aday kaydına çevirir. Aynı ileti iki kez aktarılmaz.

    Gövde: {messageId, from: {name, email}, subject, body, receivedAt?, positionId?, attachments: [{filename, contentBase64}]}.
    Pozisyon: `positionId` verilmişse o; yoksa konu satırı açık pozisyonlardan tam olarak birinin adını içeriyorsa o; yoksa boş
    (İK panoda atar). Ekler PDF/Word/ODT/metin ise özgeçmiş olarak işlenir; öteki ekler alınmaz ve cevapta sayılır."""
    ensure(engine)
    frm = body.get("from") or {}
    email = _clean_email(frm.get("email")) if isinstance(frm, dict) else None
    if not email:
        raise HrError("Gönderenin e-posta adresi yok.")
    msg_id = str(body.get("messageId") or "").strip()
    if not msg_id:
        raise HrError("İleti kimliği (messageId) yok; tekrar aktarımı önlemek için gerekli.")
    ref = hashlib.sha256(msg_id.encode("utf-8")).hexdigest()[:64]
    with engine.connect() as c:
        dup = c.execute(sa.select(CANDIDATES.c.id).where(CANDIDATES.c.tenant_id == tenant, CANDIDATES.c.source_ref == ref)).first()
        if dup is not None:
            return {"id": dup.id, "created": False, "files": 0, "skipped": []}
        pid = body.get("positionId") or None
        if pid and not c.execute(sa.select(POSITIONS.c.id).where(POSITIONS.c.id == pid, POSITIONS.c.tenant_id == tenant)).first():
            pid = None
        if not pid:
            subject = X._fold(str(body.get("subject") or ""))
            hits = [r.id for r in c.execute(sa.select(POSITIONS.c.id, POSITIONS.c.title).where(
                POSITIONS.c.tenant_id == tenant, POSITIONS.c.state == "acik")).all() if X._fold(r.title) in subject]
            pid = hits[0] if len(hits) == 1 else None
    name = clean(frm.get("name"), 200) or email.split("@")[0]
    cid = create_candidate(engine, tenant, "eposta", {"fullName": name, "email": email, "positionId": pid},
                           source="eposta", source_ref=ref)
    files, skipped = 0, []
    text = str(body.get("body") or "").strip()
    if text:
        masked, counts = X.rule_mask(text)
        _store_file(engine, tenant, "eposta", cid, "eposta-govdesi.txt", text.encode("utf-8"), text, masked, counts)
        files += 1
    for a in body.get("attachments") or []:
        fname = clean((a or {}).get("filename"), 255) or "ek"
        try:
            data = base64.b64decode(str((a or {}).get("contentBase64") or ""), validate=True)
            if len(data) > max_mb * 1024 * 1024:
                raise HrError(f"{max_mb} MB sınırını aşıyor")
            extracted = X.extract_text(fname, data)
        except (HrError, ValueError) as e:
            skipped.append({"filename": fname, "reason": str(e)[:200]})
            continue
        masked, counts = X.rule_mask(extracted)
        _store_file(engine, tenant, "eposta", cid, fname, data, extracted, masked, counts)
        files += 1
    ack = queue_ack(engine, tenant, cid, company)
    return {"id": cid, "created": True, "positionId": pid, "files": files, "skipped": skipped, "ackDraft": ack}


# ------------------------------------------------------------------ KVKK ilgili kişi talebi


def export_candidate(engine: sa.engine.Engine, tenant: str, who: H.Who, cid: str) -> dict[str, Any]:
    """Adayın portalda tutulan bütün verisi (dosya içerikleri hariç; dosya listesi ve çıkarılan metin dahil)."""
    if not (who.can(F_EXPORT) and who.can(F_ALL)):
        raise HrError("İK verisini dışa aktarma rolünüzde yok.", 403)
    d = detail(engine, tenant, who, cid, None)
    with engine.connect() as c:
        r = _load_candidate(c, tenant, who, cid)
    d.pop("can", None)
    d["email"], d["phone"] = r.email, r.phone
    d["consents"] = H.list_consents(engine, tenant, "aday", cid)
    d["accessLog"] = []
    before = None
    while True:
        page = H.access_log(engine, tenant, subject_id=cid, before=before, limit=1000)
        d["accessLog"].extend(page["items"])
        if not page["hasMore"]:
            break
        before = page["next"]
    d["exportedAt"] = iso(now())
    d["exportedBy"] = who.user
    return d


# ------------------------------------------------------------------ hatırlatma (aşama süresi)


def due_reminders(engine: sa.engine.Engine, tenant: str, sla_days: Optional[int]) -> list[dict[str, Any]]:
    """Aşamasında eşik günden uzun bekleyen, bu aşamada henüz hatırlatılmamış adaylar. Eşik yoksa boş."""
    if not sla_days:
        return []
    ensure(engine)
    t = now()
    limit = t - timedelta(days=sla_days)
    with engine.connect() as c:
        rows = c.execute(sa.select(CANDIDATES.c.id, CANDIDATES.c.position_id, CANDIDATES.c.stage, CANDIDATES.c.stage_since).where(
            CANDIDATES.c.tenant_id == tenant, CANDIDATES.c.purged_at.is_(None), CANDIDATES.c.stage != "sonuc",
            CANDIDATES.c.stage_since < limit)).all()
        done = {(r.candidate_id, r.stage_since) for r in c.execute(sa.select(REMINDERS).where(REMINDERS.c.tenant_id == tenant)).all()}
        titles = dict(c.execute(sa.select(POSITIONS.c.id, POSITIONS.c.title).where(POSITIONS.c.tenant_id == tenant)).all())
    out = []
    for r in rows:
        key = iso(r.stage_since) or ""
        if (r.id, key) in done:
            continue
        out.append({"candidateId": r.id, "stageSince": key, "stage": r.stage, "stageLabel": STAGES[r.stage],
                    "positionTitle": titles.get(r.position_id or "", "Pozisyonsuz başvuru"), "days": _days(r.stage_since, t)})
    return out


def reminder_text(items: list[dict[str, Any]], sla_days: int, link: str) -> str:
    """E-posta metni: aday adı ve özgeçmiş YOK; yalnız pozisyon/aşama sayıları ve bağlantı."""
    groups: dict[tuple[str, str], int] = {}
    for it in items:
        k = (it["positionTitle"], it["stageLabel"])
        groups[k] = groups.get(k, 0) + 1
    lines = [f"İşe alım: {len(items)} aday aşamasında {sla_days} günden uzun bekliyor.", ""]
    lines += [f"- {pos} · {stage}: {n} aday" for (pos, stage), n in sorted(groups.items())]
    if link:
        lines += ["", f"Pano: {link}"]
    lines += ["", "Bu e-posta aday bilgisi içermez; ayrıntı yalnız portalda, yetkinizle görünür."]
    return "\n".join(lines)


def mark_reminded(engine: sa.engine.Engine, tenant: str, items: list[dict[str, Any]]) -> None:
    t = now()
    with engine.begin() as c:
        for it in items:
            c.execute(REMINDERS.insert().values(tenant_id=tenant, candidate_id=it["candidateId"], stage_since=it["stageSince"], sent_at=t))
