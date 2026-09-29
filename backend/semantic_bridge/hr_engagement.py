"""M58 Çalışan deneyimi ve bağlılık: anonim anket (bağlılık, nabız, oryantasyon), sonuç (eNPS, endeks, madde), küçük grup
eşiği, açık uç tema özeti, öneri kutusu ve aksiyon planı. Ortak temel `hr_core` (İK-0).

Analiz: docs/analiz/kullanici-ihtiyaclari/M58-calisan-deneyimi-baglilik.md §14.

**Anonimlik tasarımı (teknik garanti, sözle değil):**
- Anket açılınca hedef kitledeki her hesap sahibi çalışana bir davet satırı açılır (`semantic_hr_survey_invites`: anket,
  çalışan, jetonun özeti, cevapladı mı). Ham jeton hiçbir yerde saklanmaz; kişi «Anketlerim»den bağlantıyı aldığında jeton
  yenilenir ve yalnız özeti yazılır.
- Cevap gelince önce davet «cevapladı» yapılır (tek cevap), cevap ayrı işlemde, rastgele kısa gecikmeyle
  `semantic_hr_survey_responses`'a yazılır: **çalışan kimliği, jeton ve saat yok**; satır kimliği rastgele, tarih güne
  yuvarlı. Açık uçlu cevaplar maskelenip ayrı tabloya (`semantic_hr_survey_comments`) ayrı gecikmeyle yazılır; cevap
  satırıyla bağı yoktur. Birim yalnız anket «birim kırılımlı» açıldıysa (ve gösterim eşiği girilmişse) yazılır.
- Anket kapanınca davet ve basılı kod satırları silinir, yalnız toplam sayılar ankette kalır: kimin katılıp katılmadığının
  izi kalmaz. Açıkken de «kim katılmadı» listesini veren uç yoktur.
- Bilgisayarsız çalışan için İK kişiye bağlı olmayan tek kullanımlık basılı kod üretir.

**Gösterim eşiği (min_group):** bir gizlilik kuralıdır, sayı tavanı değildir; kendiliğinden konmaz — İK anket başına girer.
Girilmemişse hiçbir sonuç gösterilmez (ekranda nedeni yazar); girilmişse yanıt sayısı eşiğin altındaki kapsam gösterilmez,
«üst birimle birlikte» notu düşer. Fark saldırısına karşı bir üst birimde gösterilen alt birimlerin dışında kalan yanıt sayısı
0 ya da eşik ve üstü olmalıdır; değilse en küçük gösterilen alt birim de gizlenir. Eşik bir kez girildikten sonra yalnız
yükseltilebilir. Sonuçlar anket kapanmadan gösterilmez (açıkken tek tek değişimi izleyerek kişiyi bulmak engellenir).

**Kimse cevabı kişiye bağlayamaz**, portal yöneticisi dahil: şema buna izin vermez. Açık uç metinleri yalnız
`ik.anket-yorum` (duyarlı) ile, maskeli ve karışık sırada görülür; yöneticiye yalnız tema ve sayı gider.

**Öneri kutusu:** adsız öneride yazar hiçbir tabloda tutulmaz (takip için yalnız kodun özeti); değişiklik kaydında yazan
«anonim» görünür. «Bir çalışanla ilgili şikâyet» birime yönlendirilmez, İK'da kalır.
"""
from __future__ import annotations

import hashlib
import logging
import random
import secrets
import threading
import uuid
import weakref
from datetime import date, datetime, timedelta
from typing import Any, Callable, Optional

import sqlalchemy as sa

from semantic_bridge import hr_core as H
from semantic_bridge import hr_engagement_text as T
from semantic_bridge.hr_core import HrError, clean, dump, iso, load, new_id, now

log = logging.getLogger("semantic_bridge.hr.engagement")

F_SURVEY_ADMIN = "ozellik:ik.anket-yonet"
F_UNIT_RESULT = "ozellik:ik.birim-sonuc"
F_COMMENTS = "ozellik:ik.anket-yorum"
F_SUGG_ADMIN = "ozellik:ik.oneri-yonet"
F_SUGG_ANSWER = "ozellik:ik.oneri-cevapla"
F_ACTION = "ozellik:ik.aksiyon"
F_EXPORT = "ozellik:ik.disa-aktar"
PAGE_DASHBOARD = "sayfa:ik-baglilik"

DC_COMMENTS = "anket_yorum"
DC_SUGGESTIONS = "oneri"

_md = sa.MetaData()


def _ts(name: str, **kw: Any) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), **kw)


TEMPLATES = sa.Table(
    "semantic_hr_survey_templates", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("kind", sa.String(20), nullable=False),              # baglilik | nabiz | oryantasyon_30 | oryantasyon_90 | modul
    sa.Column("title", sa.String(200), nullable=False),
    sa.Column("questions_json", sa.Text, nullable=False),
    sa.Column("version", sa.Integer, nullable=False),
    sa.Column("state", sa.String(12), nullable=False),             # taslak | onayda | yururlukte | arsiv
    sa.Column("submitted_by", sa.String(120)),
    sa.Column("approved_by", sa.String(120)),
    _ts("approved_at"),
    sa.Column("created_by", sa.String(120)),
    sa.Column("updated_by", sa.String(120)),
    _ts("updated_at", nullable=False),
)

SURVEYS = sa.Table(
    "semantic_hr_surveys", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("template_id", sa.String(40)),
    sa.Column("template_version", sa.Integer),
    sa.Column("kind", sa.String(20), nullable=False),
    sa.Column("title", sa.String(200), nullable=False),
    sa.Column("questions_json", sa.Text, nullable=False),          # açılışta şablondan donmuş kopya
    sa.Column("opens_at", sa.Date, nullable=False),
    sa.Column("closes_at", sa.Date, nullable=False),
    sa.Column("audience_json", sa.Text),                           # {"units": [...]} ya da {} (herkes)
    sa.Column("unit_breakdown", sa.Boolean, nullable=False, default=False),
    sa.Column("min_group", sa.Integer),                            # None: gösterim eşiği girilmedi → sonuç gösterilmez
    sa.Column("state", sa.String(10), nullable=False),             # taslak | planli | acik | kapandi
    sa.Column("invited_count", sa.Integer, nullable=False, default=0),
    sa.Column("responded_count", sa.Integer, nullable=False, default=0),
    sa.Column("paper_issued", sa.Integer, nullable=False, default=0),
    sa.Column("paper_used", sa.Integer, nullable=False, default=0),
    _ts("results_shared_at"),
    sa.Column("created_by", sa.String(120)),
    _ts("created_at", nullable=False),
    sa.Column("updated_by", sa.String(120)),
    _ts("updated_at", nullable=False),
    _ts("opened_at"),
    _ts("closed_at"),
)

INVITES = sa.Table(
    "semantic_hr_survey_invites", _md,
    sa.Column("survey_id", sa.String(40), primary_key=True),
    sa.Column("employee_id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("token_hash", sa.String(64), index=True),
    sa.Column("responded", sa.Boolean, nullable=False, default=False),
    _ts("reminded_at"),
)

PAPER = sa.Table(
    "semantic_hr_survey_paper_codes", _md,
    sa.Column("survey_id", sa.String(40), primary_key=True),
    sa.Column("code_hash", sa.String(64), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("unit_id", sa.String(40)),                           # yalnız birim kırılımlı ankette
    sa.Column("used", sa.Boolean, nullable=False, default=False),
)

#: Cevap: çalışan kimliği, jeton, saat YOK. Kimlik rastgele; tarih güne yuvarlı.
RESPONSES = sa.Table(
    "semantic_hr_survey_responses", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("survey_id", sa.String(40), nullable=False, index=True),
    sa.Column("submitted_day", sa.Date, nullable=False),
    sa.Column("unit_id", sa.String(40)),
    sa.Column("answers_json", sa.Text, nullable=False),
)

#: Açık uç: cevap satırıyla bağı yok; tarih bile yok.
COMMENTS = sa.Table(
    "semantic_hr_survey_comments", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("survey_id", sa.String(40), nullable=False, index=True),
    sa.Column("question_key", sa.String(40), nullable=False),
    sa.Column("masked_text", sa.Text, nullable=False),
    sa.Column("theme", sa.String(80)),
    sa.Column("theme_prob", sa.Float),
)

RESULTS = sa.Table(
    "semantic_hr_survey_results", _md,
    sa.Column("survey_id", sa.String(40), primary_key=True),
    sa.Column("scope", sa.String(40), primary_key=True),           # sirket | birim kimliği
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    _ts("computed_at", nullable=False),
    sa.Column("n", sa.Integer, nullable=False),
    sa.Column("enps", sa.Float),
    sa.Column("idx", sa.Float),
    sa.Column("items_json", sa.Text),
    sa.Column("themes_json", sa.Text),
    sa.Column("suppressed", sa.Boolean, nullable=False, default=False),
)

SUGGESTIONS = sa.Table(
    "semantic_hr_suggestions", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("created_day", sa.Date, nullable=False),
    sa.Column("author_employee_id", sa.String(40), index=True),    # adsızda None
    sa.Column("follow_hash", sa.String(64), index=True),           # adsız öneride takip kodunun özeti
    sa.Column("text", sa.Text, nullable=False),
    sa.Column("topic", sa.String(80)),
    sa.Column("topic_prob", sa.Float),
    sa.Column("topic_source", sa.String(8)),                       # zeki | ik
    sa.Column("personal", sa.Boolean, nullable=False, default=False),
    sa.Column("routed_unit_id", sa.String(40), index=True),
    sa.Column("routed_by", sa.String(120)),
    _ts("routed_at"),
    sa.Column("state", sa.String(14), nullable=False),             # yeni | yonlendirildi | cevaplandi | kapandi
    sa.Column("answer", sa.Text),
    sa.Column("answered_by", sa.String(120)),
    _ts("answered_at"),
    _ts("closed_at"),
)

ACTIONS = sa.Table(
    "semantic_hr_actions", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("survey_id", sa.String(40), index=True),
    sa.Column("unit_id", sa.String(40), index=True),
    sa.Column("question_key", sa.String(40)),
    sa.Column("title", sa.String(300), nullable=False),
    sa.Column("owner_employee_id", sa.String(40)),
    sa.Column("due_on", sa.Date),
    sa.Column("state", sa.String(10), nullable=False),             # acik | devam | tamam | iptal
    sa.Column("note", sa.Text),
    sa.Column("created_by", sa.String(120)),
    _ts("created_at", nullable=False),
    sa.Column("updated_by", sa.String(120)),
    _ts("updated_at", nullable=False),
    _ts("closed_at"),
)

_ready: "weakref.WeakSet[sa.engine.Engine]" = weakref.WeakSet()

KINDS = {"baglilik": "Çeyreklik bağlılık", "nabiz": "Nabız", "oryantasyon_30": "Yeni çalışan — 30. gün",
         "oryantasyon_90": "Yeni çalışan — 90. gün", "modul": "Portal modülü memnuniyeti"}
ORIENTATION_DAYS = {"oryantasyon_30": 30, "oryantasyon_90": 90}
QTYPES = {"enps": "Tavsiye (0–10)", "likert5": "Katılım (1–5)", "secim": "Seçenekli", "acik": "Açık uçlu"}
TEMPLATE_STATES = {"taslak": "Taslak", "onayda": "Onayda", "yururlukte": "Yürürlükte", "arsiv": "Arşiv"}
SURVEY_STATES = {"taslak": "Taslak", "planli": "Açılış bekliyor", "acik": "Açık", "kapandi": "Kapandı"}
SUGG_STATES = {"yeni": "Yeni", "yonlendirildi": "Yönlendirildi", "cevaplandi": "Cevaplandı", "kapandi": "Kapandı"}
ACTION_STATES = {"acik": "Açık", "devam": "Sürüyor", "tamam": "Tamamlandı", "iptal": "İptal"}
ANONYMITY_TEXT = ("Cevaplarınız adınızla saklanmaz: cevap tablosunda adınız, hesabınız, bağlantınız ve cevap saatiniz yoktur; "
                  "yalnız «cevapladı» bilgisi ayrı tutulur ve anket kapanınca o da silinir. Sonuçlar ancak yeterli sayıda "
                  "yanıt varsa toplu olarak gösterilir. Açık uçlu yorumlarda adlar ve iletişim bilgileri otomatik gizlenir.")
_PAPER_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def ensure(engine: sa.engine.Engine) -> None:
    H.ensure(engine)
    with H._lock:
        if engine in _ready:
            return
        from semantic_layer.store import schema_stamp
        schema_stamp.create_all(_md, engine)
        _ready.add(engine)


def register_hooks() -> None:
    H.register_data_class(DC_COMMENTS, "Anket açık uç yorumu",
                          "Maskeli yorum metinleri; süre anketin kapanışından sayılır. Sayısal sonuçlar anonimdir, silinmez")
    H.register_data_class(DC_SUGGESTIONS, "Çalışan önerisi",
                          "Öneri metni, cevabı ve adlı öneride yazarı; süre önerinin kapanışından sayılır")
    H.register_purger(H.Purger(DC_COMMENTS, "Anket yorumları", due_comments, purge_comments))
    H.register_purger(H.Purger(DC_SUGGESTIONS, "Çalışan önerileri", due_suggestions, purge_suggestions))


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _norm_code(code: str) -> str:
    return "".join(ch for ch in (code or "").upper() if ch.isalnum())


def settings(conf: Callable[[str], str]) -> dict[str, Any]:
    raw = (conf("HR_SURVEY_SHUFFLE_MAX_SEC") or "").strip()
    try:
        delay = max(0, min(int(raw), 600)) if raw else 20
    except ValueError:
        delay = 20
    return {"shuffleMaxSec": delay, "themes": T.configured(conf("HR_SURVEY_THEMES") or "", T.DEFAULT_THEMES),
            "topics": _with_personal(T.configured(conf("HR_SUGGESTION_TOPICS") or "", T.DEFAULT_TOPICS))}


def _with_personal(topics: list[str]) -> list[str]:
    """«Bir çalışanla ilgili şikâyet» konusu listeden çıkarılamaz (o öneri birime gitmez, İK'da kalır)."""
    return topics if T.PERSONAL_TOPIC in topics else topics[:-1] + [T.PERSONAL_TOPIC] + topics[-1:] if topics else [T.PERSONAL_TOPIC]


def _defer(fn: Callable[[], None], max_delay: int) -> None:
    """Cevap ve yorum yazımı ayrı ayrı, rastgele gecikmeyle: davetin «cevapladı» anıyla cevap satırının eklenme sırası/anı
    eşlenemesin. `max_delay` 0 ise hemen (test)."""
    if max_delay <= 0:
        fn()
        return

    def run() -> None:
        try:
            fn()
        except Exception:  # noqa: BLE001
            log.exception("hr: gecikmeli anket yazımı başarısız")

    t = threading.Timer(random.uniform(1.0, float(max_delay)), run)
    t.daemon = False                 # süreç kapanırken bekleyen yazım yarıda bırakılmasın
    t.start()


# ------------------------------------------------------------------ birim ağacı


class Org:
    def __init__(self, engine: sa.engine.Engine, tenant: str):
        with engine.connect() as c:
            self.units = {u.id: u for u in c.execute(sa.select(H.UNITS).where(H.UNITS.c.tenant_id == tenant)).all()}
            self.emp = {e.id: e for e in c.execute(sa.select(H.EMPLOYEES).where(H.EMPLOYEES.c.tenant_id == tenant)).all()}
        self.kids: dict[Optional[str], list[str]] = {}
        for u in self.units.values():
            p = u.parent_id if u.parent_id in self.units else None
            self.kids.setdefault(p, []).append(u.id)

    def subtree(self, uid: str) -> set[str]:
        out, stack = set(), [uid]
        while stack:
            x = stack.pop()
            if x in out:
                continue
            out.add(x)
            stack.extend(self.kids.get(x, []))
        return out

    def name(self, uid: Optional[str]) -> Optional[str]:
        u = self.units.get(uid or "")
        return u.name if u else None

    def me(self, username: str) -> Optional[Any]:
        u = (username or "").strip().lower()
        rows = sorted((e for e in self.emp.values() if (e.username or "") == u), key=lambda e: e.status != "aktif")
        return rows[0] if rows else None

    def managed(self, username: str) -> set[str]:
        me = self.me(username)
        if not me:
            return set()
        out: set[str] = set()
        for u in self.units.values():
            if u.manager_employee_id == me.id:
                out |= self.subtree(u.id)
        return out

    def audience(self, audience: dict[str, Any]) -> list[Any]:
        units = [u for u in (audience or {}).get("units") or [] if u in self.units]
        allowed: Optional[set[str]] = None
        if units:
            allowed = set()
            for u in units:
                allowed |= self.subtree(u)
        return [e for e in self.emp.values() if e.status == "aktif" and (allowed is None or e.unit_id in allowed)]


# ------------------------------------------------------------------ şablonlar


def _clean_questions(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise HrError("Ankette en az bir soru olmalı.")
    out: list[dict[str, Any]] = []
    for i, q in enumerate(raw, 1):
        if not isinstance(q, dict):
            continue
        text = clean(q.get("text"), 400)
        typ = str(q.get("type") or "")
        if not text:
            raise HrError(f"{i}. sorunun metni boş.")
        if typ not in QTYPES:
            raise HrError(f"{i}. sorunun türü geçersiz.")
        key = "".join(ch for ch in str(q.get("key") or f"s{i}").lower() if ch.isalnum() or ch == "_")[:40] or f"s{i}"
        item: dict[str, Any] = {"key": key, "text": text, "type": typ}
        if typ == "secim":
            opts = [clean(o, 120) for o in (q.get("options") or []) if clean(o, 120)]
            if len(opts) < 2:
                raise HrError(f"«{text}» seçenekli soru en az iki seçenek ister.")
            item["options"] = opts
        out.append(item)
    keys = [q["key"] for q in out]
    if len(keys) != len(set(keys)):
        raise HrError("Soru anahtarları tekrar ediyor.")
    if sum(1 for q in out if q["type"] == "enps") > 1:
        raise HrError("Ankette en çok bir tavsiye (eNPS) sorusu olur.")
    return out


def _tpl_out(r: Any) -> dict[str, Any]:
    return {"id": r.id, "kind": r.kind, "kindLabel": KINDS.get(r.kind, r.kind), "title": r.title,
            "questions": load(r.questions_json, []), "version": r.version, "state": r.state,
            "stateLabel": TEMPLATE_STATES.get(r.state, r.state), "submittedBy": r.submitted_by, "approvedBy": r.approved_by,
            "approvedAt": iso(r.approved_at), "updatedBy": r.updated_by, "updatedAt": iso(r.updated_at)}


def list_templates(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    ensure(engine)
    with engine.connect() as c:
        return [_tpl_out(r) for r in c.execute(sa.select(TEMPLATES).where(TEMPLATES.c.tenant_id == tenant)
                                               .order_by(TEMPLATES.c.kind, TEMPLATES.c.title)).all()]


def save_template(engine: sa.engine.Engine, tenant: str, actor: str, body: dict[str, Any], tid: Optional[str] = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Taslak şablon. Onaydaki ya da yürürlükteki şablon düzenlenirse taslağa döner ve sürüm artar (yeniden onay gerekir)."""
    ensure(engine)
    with engine.begin() as c:
        before = c.execute(sa.select(TEMPLATES).where(TEMPLATES.c.id == tid, TEMPLATES.c.tenant_id == tenant)).first() if tid else None
        if tid and before is None:
            raise HrError("Şablon bulunamadı.", 404)
        kind = str(body.get("kind") or (before.kind if before is not None else ""))
        if kind not in KINDS:
            raise HrError("Anket türünü seçin.")
        title = clean(body.get("title", before.title if before is not None else ""), 200)
        if not title:
            raise HrError("Şablonun adı boş olamaz.")
        qs = _clean_questions(body["questions"]) if "questions" in body or before is None else load(before.questions_json, [])
        t = now()
        if before is None:
            tid = new_id("sabl")
            c.execute(TEMPLATES.insert().values(id=tid, tenant_id=tenant, kind=kind, title=title, questions_json=dump(qs), version=1,
                                                state="taslak", created_by=actor, updated_by=actor, updated_at=t))
            diff = {"yeni": title}
        else:
            changed = dump(qs) != before.questions_json or kind != before.kind
            vals = dict(kind=kind, title=title, questions_json=dump(qs), updated_by=actor, updated_at=t)
            if changed:
                vals.update(version=before.version + 1, state="taslak", approved_by=None, approved_at=None, submitted_by=None)
            c.execute(TEMPLATES.update().where(TEMPLATES.c.id == tid).values(**vals))
            diff = {k: v for k, v in (("ad", title != before.title), ("sorular", changed)) if v}
        r = c.execute(sa.select(TEMPLATES).where(TEMPLATES.c.id == tid)).first()
    return _tpl_out(r), diff


def template_transition(engine: sa.engine.Engine, tenant: str, who: H.Who, tid: str, action: str) -> dict[str, Any]:
    """submit (taslak→onayda) · approve (onayda→yürürlük; gönderen onaylayamaz) · reject · archive."""
    ensure(engine)
    with engine.begin() as c:
        r = c.execute(sa.select(TEMPLATES).where(TEMPLATES.c.id == tid, TEMPLATES.c.tenant_id == tenant)).first()
        if r is None:
            raise HrError("Şablon bulunamadı.", 404)
        t = now()
        if action == "submit" and r.state == "taslak":
            vals: dict[str, Any] = dict(state="onayda", submitted_by=who.user)
        elif action in ("approve", "reject") and r.state == "onayda":
            if r.submitted_by == who.user:
                raise HrError("Şablonu onaya gönderen onaylayamaz; ikinci bir kişi onaylar.", 403)
            vals = dict(state="yururlukte", approved_by=who.user, approved_at=t) if action == "approve" else dict(state="taslak")
        elif action == "archive" and r.state != "arsiv":
            vals = dict(state="arsiv")
        else:
            raise HrError(f"Şablonda «{action}» şu durumda ({TEMPLATE_STATES.get(r.state, r.state)}) yapılamaz.", 409)
        c.execute(TEMPLATES.update().where(TEMPLATES.c.id == tid).values(updated_by=who.user, updated_at=t, **vals))
        return _tpl_out(c.execute(sa.select(TEMPLATES).where(TEMPLATES.c.id == tid)).first())


# ------------------------------------------------------------------ anketler


def _survey_out(r: Any, org: Optional[Org] = None) -> dict[str, Any]:
    aud = load(r.audience_json, {}) or {}
    return {"id": r.id, "templateId": r.template_id, "templateVersion": r.template_version, "kind": r.kind,
            "kindLabel": KINDS.get(r.kind, r.kind), "title": r.title, "questions": load(r.questions_json, []),
            "opensAt": iso(r.opens_at), "closesAt": iso(r.closes_at), "audience": aud,
            "audienceNames": [org.name(u) or u for u in aud.get("units") or []] if org else None,
            "unitBreakdown": bool(r.unit_breakdown), "minGroup": r.min_group, "state": r.state,
            "stateLabel": SURVEY_STATES.get(r.state, r.state), "invited": r.invited_count, "responded": r.responded_count,
            "paperIssued": r.paper_issued, "paperUsed": r.paper_used, "resultsSharedAt": iso(r.results_shared_at),
            "createdBy": r.created_by, "openedAt": iso(r.opened_at), "closedAt": iso(r.closed_at), "updatedAt": iso(r.updated_at)}


def _survey_row(c: Any, tenant: str, sid: str) -> Any:
    r = c.execute(sa.select(SURVEYS).where(SURVEYS.c.id == sid, SURVEYS.c.tenant_id == tenant)).first()
    if r is None:
        raise HrError("Anket bulunamadı.", 404)
    return r


def list_surveys(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    ensure(engine)
    org = Org(engine, tenant)
    with engine.connect() as c:
        return [_survey_out(r, org) for r in c.execute(sa.select(SURVEYS).where(SURVEYS.c.tenant_id == tenant)
                                                       .order_by(SURVEYS.c.opens_at.desc())).all()]


def get_survey(engine: sa.engine.Engine, tenant: str, sid: str) -> dict[str, Any]:
    ensure(engine)
    with engine.connect() as c:
        return _survey_out(_survey_row(c, tenant, sid), Org(engine, tenant))


def _min_group(v: Any, old: Optional[int]) -> Optional[int]:
    if v in (None, ""):
        if old is not None:
            raise HrError("Girilmiş gösterim eşiği kaldırılamaz.")
        return None
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise HrError("Gösterim eşiği tam sayı olmalı.") from None
    if n < 2:
        raise HrError("Gösterim eşiği en az 2 olmalı (tek yanıt kişiyi gösterir).")
    if old is not None and n < old:
        raise HrError(f"Gösterim eşiği yalnız yükseltilebilir (şu an {old}).")
    return n


def save_survey(engine: sa.engine.Engine, tenant: str, actor: str, body: dict[str, Any], sid: Optional[str] = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Anket taslağı. Açıldıktan sonra yalnız kapanış tarihi (uzatma) ve gösterim eşiği (yükseltme) değişir."""
    ensure(engine)
    with engine.begin() as c:
        before = _survey_row(c, tenant, sid) if sid else None
        if before is not None and before.state == "kapandi" and set(body) - {"minGroup"}:
            raise HrError("Kapanmış ankette yalnız gösterim eşiği girilebilir.", 409)
        t = now()
        if before is not None and before.state != "taslak":
            vals: dict[str, Any] = {}
            if "closesAt" in body and before.state != "kapandi":
                ca = H.parse_date(body["closesAt"], "Kapanış")
                if ca is None or ca < before.closes_at:
                    raise HrError("Açılmış anketin kapanışı yalnız ileri alınabilir.")
                vals["closes_at"] = ca
            if "minGroup" in body:
                vals["min_group"] = _min_group(body.get("minGroup"), before.min_group)
            extra = set(body) - {"closesAt", "minGroup"}
            if extra:
                raise HrError("Açılmış ankette sorular, hedef kitle ve birim kırılımı değişmez.", 409)
            if not vals:
                raise HrError("Değişecek bir şey yok.")
            c.execute(SURVEYS.update().where(SURVEYS.c.id == sid).values(updated_by=actor, updated_at=t, **vals))
            diff = {k: {"once": iso(getattr(before, k)) if isinstance(getattr(before, k), date) else getattr(before, k),
                        "sonra": iso(v) if isinstance(v, date) else v} for k, v in vals.items()}
        else:
            tid = body.get("templateId", before.template_id if before is not None else None)
            tpl = c.execute(sa.select(TEMPLATES).where(TEMPLATES.c.id == (tid or ""), TEMPLATES.c.tenant_id == tenant)).first()
            if tpl is None:
                raise HrError("Anket bir şablondan açılır; şablon seçin.")
            if tpl.state != "yururlukte":
                raise HrError("Yalnız onaylanmış (yürürlükteki) şablon kullanılır.")
            oa = H.parse_date(body["opensAt"], "Açılış") if "opensAt" in body else (before.opens_at if before is not None else None)
            ca = H.parse_date(body["closesAt"], "Kapanış") if "closesAt" in body else (before.closes_at if before is not None else None)
            if not oa or not ca:
                raise HrError("Açılış ve kapanış tarihlerini girin.")
            if ca < oa:
                raise HrError("Kapanış açılıştan önce olamaz.")
            units = body.get("units") if "units" in body else ((load(before.audience_json, {}) or {}).get("units") if before is not None else [])
            units = [u for u in (units or []) if isinstance(u, str)]
            mg = _min_group(body.get("minGroup"), None) if "minGroup" in body else (before.min_group if before is not None else None)
            breakdown = bool(body.get("unitBreakdown", before.unit_breakdown if before is not None else False))
            if breakdown and mg is None:
                raise HrError("Birim kırılımı yalnız gösterim eşiği girilmiş ankette açılır.")
            vals = dict(template_id=tpl.id, template_version=tpl.version, kind=tpl.kind,
                        title=clean(body.get("title"), 200) or (before.title if before is not None else tpl.title),
                        questions_json=tpl.questions_json, opens_at=oa, closes_at=ca, audience_json=dump({"units": units} if units else {}),
                        unit_breakdown=breakdown, min_group=mg, updated_by=actor, updated_at=t)
            if before is None:
                sid = new_id("ankt")
                c.execute(SURVEYS.insert().values(id=sid, tenant_id=tenant, state="taslak", created_by=actor, created_at=t, **vals))
                diff = {"yeni": vals["title"], "tur": tpl.kind}
            else:
                c.execute(SURVEYS.update().where(SURVEYS.c.id == sid).values(**vals))
                diff = {"guncellendi": True}
    if before is not None and before.state == "kapandi":
        snapshot(engine, tenant, sid)                  # eşik sonradan girildi: eğilim satırı yeniden
    return get_survey(engine, tenant, sid), diff


def _open_now(c: Any, tenant: str, s: Any, org: Org) -> int:
    """Davet satırlarını açar: hedef kitlede hesabı olan aktif çalışanlar (oryantasyon anketinde davet run-due'da)."""
    if s.kind in ORIENTATION_DAYS:
        return 0
    n = 0
    have = {r[0] for r in c.execute(sa.select(INVITES.c.employee_id).where(INVITES.c.survey_id == s.id)).all()}
    for e in org.audience(load(s.audience_json, {}) or {}):
        if not e.username or e.id in have:
            continue
        c.execute(INVITES.insert().values(survey_id=s.id, employee_id=e.id, tenant_id=tenant, token_hash=None, responded=False))
        n += 1
    return n


def open_survey(engine: sa.engine.Engine, tenant: str, actor: str, sid: str, today: Optional[date] = None) -> dict[str, Any]:
    ensure(engine)
    today = today or date.today()
    org = Org(engine, tenant)
    with engine.begin() as c:
        s = _survey_row(c, tenant, sid)
        if s.state != "taslak":
            raise HrError("Yalnız taslak anket açılır.", 409)
        if s.closes_at < today:
            raise HrError("Kapanış tarihi geçmiş; tarihi düzeltin.")
        if s.opens_at > today:
            c.execute(SURVEYS.update().where(SURVEYS.c.id == sid).values(state="planli", updated_by=actor, updated_at=now()))
        else:
            n = _open_now(c, tenant, s, org)
            c.execute(SURVEYS.update().where(SURVEYS.c.id == sid).values(state="acik", opened_at=now(), invited_count=n,
                                                                         updated_by=actor, updated_at=now()))
    return get_survey(engine, tenant, sid)


def close_survey(engine: sa.engine.Engine, tenant: str, actor: str, sid: str) -> dict[str, Any]:
    """Kapanış: sonuç anlık görüntüsü yazılır, davet ve basılı kod satırları silinir (katılım izi kalmaz), sayılar ankette kalır."""
    ensure(engine)
    with engine.begin() as c:
        s = _survey_row(c, tenant, sid)
        if s.state not in ("acik", "planli"):
            raise HrError("Yalnız açık anket kapatılır.", 409)
        inv = c.execute(sa.select(sa.func.count(), sa.func.sum(sa.case((INVITES.c.responded.is_(True), 1), else_=0)))
                        .where(INVITES.c.survey_id == sid)).first()
        pap = c.execute(sa.select(sa.func.count(), sa.func.sum(sa.case((PAPER.c.used.is_(True), 1), else_=0)))
                        .where(PAPER.c.survey_id == sid)).first()
        c.execute(SURVEYS.update().where(SURVEYS.c.id == sid).values(
            state="kapandi", closed_at=now(), invited_count=int(inv[0] or 0), responded_count=int(inv[1] or 0),
            paper_issued=int(pap[0] or 0), paper_used=int(pap[1] or 0), updated_by=actor, updated_at=now()))
        c.execute(INVITES.delete().where(INVITES.c.survey_id == sid))
        c.execute(PAPER.delete().where(PAPER.c.survey_id == sid))
    snapshot(engine, tenant, sid)
    return get_survey(engine, tenant, sid)


def paper_codes(engine: sa.engine.Engine, tenant: str, sid: str, n: int, unit_id: Optional[str] = None) -> list[str]:
    """Kişiye bağlı olmayan tek kullanımlık kodlar. Kodun kendisi yalnız bu cevapta döner (basılıp dağıtılır), özeti saklanır."""
    ensure(engine)
    if not 1 <= n <= 5000:
        raise HrError("Kod sayısı 1–5000 arası olmalı.")
    with engine.begin() as c:
        s = _survey_row(c, tenant, sid)
        if s.state not in ("acik", "planli"):
            raise HrError("Basılı kod yalnız açık ya da açılış bekleyen ankete üretilir.", 409)
        if unit_id and not s.unit_breakdown:
            raise HrError("Bu anket birim kırılımlı değil; kodlar birimsiz üretilir.")
        codes = []
        for _ in range(n):
            raw = "".join(secrets.choice(_PAPER_ALPHABET) for _ in range(10))
            codes.append(f"{raw[:5]}-{raw[5:]}")
            c.execute(PAPER.insert().values(survey_id=sid, code_hash=_hash(_norm_code(raw)), tenant_id=tenant, unit_id=unit_id or None, used=False))
    return codes


def progress(engine: sa.engine.Engine, tenant: str, sid: str) -> dict[str, Any]:
    """Yalnız toplamlar: davet, cevaplayan, basılı kod; hiç kimsenin adı yok."""
    ensure(engine)
    org = Org(engine, tenant)
    with engine.connect() as c:
        s = _survey_row(c, tenant, sid)
        responses = int(c.execute(sa.select(sa.func.count()).where(RESPONSES.c.survey_id == sid)).scalar() or 0)
        if s.state == "kapandi":
            invited, responded, issued, used = s.invited_count, s.responded_count, s.paper_issued, s.paper_used
        else:
            inv = c.execute(sa.select(sa.func.count(), sa.func.sum(sa.case((INVITES.c.responded.is_(True), 1), else_=0)))
                            .where(INVITES.c.survey_id == sid)).first()
            pap = c.execute(sa.select(sa.func.count(), sa.func.sum(sa.case((PAPER.c.used.is_(True), 1), else_=0)))
                            .where(PAPER.c.survey_id == sid)).first()
            invited, responded, issued, used = int(inv[0] or 0), int(inv[1] or 0), int(pap[0] or 0), int(pap[1] or 0)
    audience = org.audience(load(s.audience_json, {}) or {})
    reach = invited + issued
    return {"state": s.state, "invited": invited, "responded": responded, "paperIssued": issued, "paperUsed": used,
            "responses": responses, "rate": ((responded + used) / reach) if reach else None,
            "audienceActive": len(audience), "noAccount": sum(1 for e in audience if not e.username),
            "note": "Cevaplar birkaç saniye gecikmeyle kaydedilir; «yanıt» sayısı «cevaplayan» sayısını kısa süre geriden izleyebilir."}


# ------------------------------------------------------------------ çalışanın anketleri ve oturumsuz form


def my_surveys(engine: sa.engine.Engine, tenant: str, username: str) -> list[dict[str, Any]]:
    ensure(engine)
    me = Org(engine, tenant).me(username)
    if not me:
        return []
    with engine.connect() as c:
        rows = c.execute(sa.select(SURVEYS, INVITES.c.responded).join(INVITES, INVITES.c.survey_id == SURVEYS.c.id)
                         .where(INVITES.c.employee_id == me.id, SURVEYS.c.state == "acik", SURVEYS.c.tenant_id == tenant)
                         .order_by(SURVEYS.c.closes_at)).all()
    return [{"id": r.id, "title": r.title, "kindLabel": KINDS.get(r.kind, r.kind), "closesAt": iso(r.closes_at),
             "questions": len(load(r.questions_json, [])), "responded": bool(r.responded)} for r in rows]


def issue_link(engine: sa.engine.Engine, tenant: str, username: str, sid: str) -> str:
    """Kişinin davet jetonunu yeniler ve ham jetonu bir kez döndürür (yalnız özeti saklanır)."""
    ensure(engine)
    me = Org(engine, tenant).me(username)
    if not me:
        raise HrError("Çalışan kaydınız yok; İK ile görüşün.", 404)
    token = secrets.token_urlsafe(24)
    with engine.begin() as c:
        s = _survey_row(c, tenant, sid)
        if s.state != "acik":
            raise HrError("Anket açık değil.", 409)
        inv = c.execute(sa.select(INVITES).where(INVITES.c.survey_id == sid, INVITES.c.employee_id == me.id)).first()
        if inv is None:
            raise HrError("Bu ankete davetli değilsiniz.", 404)
        if inv.responded:
            raise HrError("Bu anketi cevapladınız; teşekkürler.", 409)
        c.execute(INVITES.update().where(INVITES.c.survey_id == sid, INVITES.c.employee_id == me.id).values(token_hash=_hash(token)))
    return token


def _lookup(c: Any, token: str) -> tuple[Any, Optional[Any], Optional[Any]]:
    """(anket, davet, basılı kod). Jeton davet jetonu ya da basılı kod olabilir."""
    h = _hash(token or "")
    inv = c.execute(sa.select(INVITES).where(INVITES.c.token_hash == h)).first()
    if inv is not None:
        s = c.execute(sa.select(SURVEYS).where(SURVEYS.c.id == inv.survey_id)).first()
        return s, inv, None
    code = _norm_code(token)
    if len(code) == 10:
        pap = c.execute(sa.select(PAPER).where(PAPER.c.code_hash == _hash(code))).first()
        if pap is not None:
            return c.execute(sa.select(SURVEYS).where(SURVEYS.c.id == pap.survey_id)).first(), None, pap
    raise HrError("Bağlantı ya da kod geçersiz veya süresi dolmuş.", 404)


def public_form(engine: sa.engine.Engine, token: str, today: Optional[date] = None) -> dict[str, Any]:
    ensure(engine)
    today = today or date.today()
    with engine.connect() as c:
        s, inv, pap = _lookup(c, token)
    used = bool(inv.responded) if inv is not None else bool(pap.used)
    open_ = s.state == "acik" and s.opens_at <= today <= s.closes_at
    return {"title": s.title, "kindLabel": KINDS.get(s.kind, s.kind), "closesAt": iso(s.closes_at), "open": open_,
            "alreadyResponded": used, "questions": load(s.questions_json, []), "anonymity": ANONYMITY_TEXT}


def _validate_answers(questions: list[dict[str, Any]], raw: Any) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    raw = raw if isinstance(raw, dict) else {}
    answers: dict[str, Any] = {}
    texts: list[tuple[str, str]] = []
    for q in questions:
        v = raw.get(q["key"])
        if v in (None, ""):
            continue                                   # her soru isteğe bağlı: cevaplamamak da bir cevaptır
        if q["type"] in ("enps", "likert5"):
            lo, hi = (0, 10) if q["type"] == "enps" else (1, 5)
            try:
                v = int(v)
            except (TypeError, ValueError):
                raise HrError(f"«{q['text']}» için {lo}–{hi} arası bir değer seçin.") from None
            if not lo <= v <= hi:
                raise HrError(f"«{q['text']}» için {lo}–{hi} arası bir değer seçin.")
            answers[q["key"]] = v
        elif q["type"] == "secim":
            if v not in q.get("options", []):
                raise HrError(f"«{q['text']}» için listeden seçin.")
            answers[q["key"]] = v
        else:
            txt = str(v).strip()[:3000]
            if txt:
                texts.append((q["key"], txt))
    if not answers and not texts:
        raise HrError("Hiçbir soruyu cevaplamadınız.")
    return answers, texts


def submit_public(engine: sa.engine.Engine, token: str, body: dict[str, Any], *, delay_max: int = 20,
                  today: Optional[date] = None) -> dict[str, Any]:
    """Cevap: (1) davet/kod «kullanıldı» — tek cevap; (2) gecikmeli, kimliksiz cevap satırı; (3) ayrı gecikmeyle maskeli yorumlar."""
    ensure(engine)
    today = today or date.today()
    with engine.connect() as c:
        s, inv, pap = _lookup(c, token)
    if not (s.state == "acik" and s.opens_at <= today <= s.closes_at):
        raise HrError("Anket şu an cevaba açık değil.", 409)
    answers, texts = _validate_answers(load(s.questions_json, []), body.get("answers"))
    org = Org(engine, s.tenant_id)
    unit_id = None
    with engine.begin() as c:
        if inv is not None:
            n = c.execute(INVITES.update().where(INVITES.c.survey_id == inv.survey_id, INVITES.c.employee_id == inv.employee_id,
                                                 INVITES.c.responded.is_(False)).values(responded=True)).rowcount
            if s.unit_breakdown and s.min_group:
                e = org.emp.get(inv.employee_id)
                unit_id = e.unit_id if e else None
        else:
            n = c.execute(PAPER.update().where(PAPER.c.survey_id == pap.survey_id, PAPER.c.code_hash == pap.code_hash,
                                               PAPER.c.used.is_(False)).values(used=True)).rowcount
            if s.unit_breakdown and s.min_group:
                unit_id = pap.unit_id
        if not n:
            raise HrError("Bu anket bu bağlantıyla zaten cevaplandı.", 409)
    tenant, sid = s.tenant_id, s.id
    names = [e.display_name for e in org.emp.values()]

    def write_response() -> None:
        with engine.begin() as c:
            c.execute(RESPONSES.insert().values(id=uuid.uuid4().hex, tenant_id=tenant, survey_id=sid, submitted_day=today,
                                                unit_id=unit_id, answers_json=dump(answers)))

    def write_comments() -> None:
        rows = []
        for key, txt in texts:
            masked, _ = T.mask_text(txt, names)
            if masked.strip():
                rows.append({"id": uuid.uuid4().hex, "tenant_id": tenant, "survey_id": sid, "question_key": key, "masked_text": masked})
        if rows:
            random.shuffle(rows)
            with engine.begin() as c:
                c.execute(COMMENTS.insert(), rows)

    _defer(write_response, delay_max)
    if texts:
        _defer(write_comments, delay_max)
    return {"ok": True, "message": "Teşekkürler; cevabınız adınız olmadan kaydedildi."}


# ------------------------------------------------------------------ sonuç hesabı


def aggregate(questions: list[dict[str, Any]], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Rakamlar yalnız buradan (SQL satırlarından); kabul betiği aynı tanımı doğrudan SQL ile sınar:
    eNPS = 100 × (9–10 verenler − 0–6 verenler) / eNPS sorusunu cevaplayan; madde ortalaması = AVG; endeks = Likert madde
    ortalamalarının (ortalama − 1) / 4 × 100 ortalaması."""
    items = []
    enps = None
    likert_means = []
    for q in questions:
        vals = [r[q["key"]] for r in rows if q["key"] in r]
        if q["type"] == "enps":
            if vals:
                pro = sum(1 for v in vals if v >= 9)
                det = sum(1 for v in vals if v <= 6)
                enps = round(100.0 * (pro - det) / len(vals), 1)
            items.append({"key": q["key"], "text": q["text"], "type": "enps", "n": len(vals), "enps": enps,
                          "dist": [sum(1 for v in vals if v == i) for i in range(11)]})
        elif q["type"] == "likert5":
            mean = round(sum(vals) / len(vals), 2) if vals else None
            if mean is not None:
                likert_means.append(mean)
            items.append({"key": q["key"], "text": q["text"], "type": "likert5", "n": len(vals), "mean": mean,
                          "favorable": round(100.0 * sum(1 for v in vals if v >= 4) / len(vals), 1) if vals else None,
                          "dist": [sum(1 for v in vals if v == i) for i in range(1, 6)]})
        elif q["type"] == "secim":
            items.append({"key": q["key"], "text": q["text"], "type": "secim", "n": len(vals),
                          "counts": {o: sum(1 for v in vals if v == o) for o in q.get("options", [])}})
    idx = round(sum((m - 1) / 4 * 100 for m in likert_means) / len(likert_means), 1) if likert_means else None
    return {"n": len(rows), "enps": enps, "index": idx, "items": items}


def _responses(engine: sa.engine.Engine, sid: str) -> list[tuple[Optional[str], dict[str, Any]]]:
    with engine.connect() as c:
        return [(r.unit_id, load(r.answers_json, {}) or {}) for r in c.execute(
            sa.select(RESPONSES.c.unit_id, RESPONSES.c.answers_json).where(RESPONSES.c.survey_id == sid)).all()]


def breakdown(org: Org, units_n: dict[str, int], total: int, m: int) -> dict[str, dict[str, Any]]:
    """Birim → {n, shown, mergedInto}. Kural: n ≥ m ve bir üst düzeydeki gösterilmeyen artık 0 ya da ≥ m (fark saldırısı)."""
    sub_n = {u: sum(units_n.get(x, 0) for x in org.subtree(u)) for u in org.units}
    out: dict[str, dict[str, Any]] = {}

    def visit(parent: Optional[str], parent_n: int, parent_name: str) -> None:
        kids = [k for k in org.kids.get(parent, []) if sub_n.get(k, 0) > 0]
        shown = sorted((k for k in kids if sub_n[k] >= m), key=lambda k: sub_n[k])
        residual = parent_n - sum(sub_n[k] for k in shown)
        while shown and 0 < residual < m:
            k = shown.pop(0)
            residual += sub_n[k]
        for k in kids:
            out[k] = {"n": sub_n[k], "shown": k in shown, "mergedInto": None if k in shown else parent_name}
            if k in shown:
                visit(k, sub_n[k], org.name(k) or k)
            else:
                for x in org.subtree(k) - {k}:
                    if sub_n.get(x, 0) > 0:
                        out[x] = {"n": sub_n[x], "shown": False, "mergedInto": parent_name}

    visit(None, total, "Şirket geneli")
    return out


def results(engine: sa.engine.Engine, tenant: str, sid: str, scope: str = "sirket", *, allowed_units: Optional[set[str]] = None) -> dict[str, Any]:
    """Sonuç. Anket kapanmadan ya da gösterim eşiği girilmeden hiçbir sonuç yok; eşik altı kapsam gizli ve nedeniyle."""
    ensure(engine)
    s = get_survey(engine, tenant, sid)
    base = {"survey": s, "scope": scope}
    if s["state"] != "kapandi":
        return {**base, "suppressed": True, "reason": "acik", "message": "Sonuçlar anket kapanınca gösterilir (açıkken tek tek değişim izlenemesin diye)."}
    m = s["minGroup"]
    if not m:
        return {**base, "suppressed": True, "reason": "esik_yok",
                "message": "Gösterim eşiği girilmedi; en az kaç yanıt olmadan sonuç gösterilmeyeceğine İK karar verip girince sonuçlar görünür."}
    rows = _responses(engine, sid)
    org = Org(engine, tenant)
    if scope == "sirket":
        if len(rows) < m:
            return {**base, "suppressed": True, "reason": "esik_alti", "n": None,
                    "message": f"Bu ankette {m}'den az yanıt var; sonuç gösterilmiyor."}
        agg = aggregate(s["questions"], [a for _, a in rows])
        units = None
        if s["unitBreakdown"]:
            un: dict[str, int] = {}
            for u, _ in rows:
                if u:
                    un[u] = un.get(u, 0) + 1
            bd = breakdown(org, un, len(rows), m)
            units = [{"unitId": u, "unitName": org.name(u), **v, "n": v["n"] if v["shown"] else None} for u, v in bd.items()
                     if allowed_units is None or u in allowed_units]
            units.sort(key=lambda x: (x["unitName"] or "").casefold())
        return {**base, "suppressed": False, **agg, "units": units, "minGroup": m}
    if not s["unitBreakdown"]:
        return {**base, "suppressed": True, "reason": "kirilim_kapali", "message": "Bu anket birim kırılımı kapalı açıldı; birim sonucu yok."}
    if scope not in org.units:
        raise HrError("Birim bulunamadı.", 404)
    if allowed_units is not None and scope not in allowed_units:
        raise HrError("Bu birimin sonucu kapsamınızda değil.", 403)
    un = {}
    for u, _ in rows:
        if u:
            un[u] = un.get(u, 0) + 1
    bd = breakdown(org, un, len(rows), m) if len(rows) >= m else {}
    info = bd.get(scope)
    if not info or not info["shown"]:
        merged = (info or {}).get("mergedInto") or "Şirket geneli"
        return {**base, "suppressed": True, "reason": "esik_alti", "unitName": org.name(scope), "mergedInto": merged,
                "message": f"Bu birimde gösterim eşiğinin ({m}) altında yanıt var ya da ayrı gösterilmesi başka bir birimi ele verir; "
                           f"sonuç «{merged}» ile birlikte gösteriliyor."}
    sub = org.subtree(scope)
    agg = aggregate(s["questions"], [a for u, a in rows if u in sub])
    return {**base, "suppressed": False, "unitName": org.name(scope), **agg, "minGroup": m}


def snapshot(engine: sa.engine.Engine, tenant: str, sid: str) -> None:
    """Kapanışta şirket ve gösterilen birim sonuçları eğilim için saklanır (eşik yoksa gizli olarak)."""
    res = results(engine, tenant, sid)
    t = now()
    with engine.begin() as c:
        c.execute(RESULTS.delete().where(RESULTS.c.survey_id == sid))
        c.execute(RESULTS.insert().values(survey_id=sid, scope="sirket", tenant_id=tenant, computed_at=t,
                                          n=res.get("n") or 0 if not res["suppressed"] else 0, enps=res.get("enps"), idx=res.get("index"),
                                          items_json=dump(res.get("items") or []), suppressed=bool(res["suppressed"])))
        for u in res.get("units") or []:
            if not u["shown"]:
                continue
            ur = results(engine, tenant, sid, u["unitId"])
            c.execute(RESULTS.insert().values(survey_id=sid, scope=u["unitId"][:40], tenant_id=tenant, computed_at=t, n=ur.get("n") or 0,
                                              enps=ur.get("enps"), idx=ur.get("index"), items_json=dump(ur.get("items") or []),
                                              suppressed=bool(ur["suppressed"])))


def trend(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    ensure(engine)
    with engine.connect() as c:
        rows = c.execute(sa.select(SURVEYS, RESULTS.c.n, RESULTS.c.enps, RESULTS.c.idx, RESULTS.c.suppressed)
                         .join(RESULTS, sa.and_(RESULTS.c.survey_id == SURVEYS.c.id, RESULTS.c.scope == "sirket"))
                         .where(SURVEYS.c.tenant_id == tenant, SURVEYS.c.state == "kapandi").order_by(SURVEYS.c.closes_at)).all()
    return [{"surveyId": r.id, "title": r.title, "kind": r.kind, "closesAt": iso(r.closes_at),
             "n": None if r.suppressed else r.n, "enps": None if r.suppressed else r.enps, "index": None if r.suppressed else r.idx,
             "suppressed": bool(r.suppressed), "rate": ((r.responded_count + r.paper_used) / (r.invited_count + r.paper_issued))
             if (r.invited_count + r.paper_issued) else None} for r in rows]


def themes(engine: sa.engine.Engine, tenant: str, sid: str, *, raw: bool = False) -> dict[str, Any]:
    """Tema sayıları ve özetleri (kapanmış ankette, eşik girilmişse). `raw` yalnız `ik.anket-yorum`: maskeli metin, karışık sıra."""
    s = get_survey(engine, tenant, sid)
    if s["state"] != "kapandi" or not s["minGroup"]:
        return {"suppressed": True, "message": "Temalar anket kapanıp gösterim eşiği girilince görünür.", "themes": [], "comments": None}
    with engine.connect() as c:
        rows = c.execute(sa.select(COMMENTS).where(COMMENTS.c.survey_id == sid)).all()
        snap = c.execute(sa.select(RESULTS.c.themes_json).where(RESULTS.c.survey_id == sid, RESULTS.c.scope == "sirket")).scalar()
    summaries = load(snap, {}) or {}
    counts: dict[str, int] = {}
    for r in rows:
        counts[r.theme or "Sınıflanmadı"] = counts.get(r.theme or "Sınıflanmadı", 0) + 1
    m = s["minGroup"]
    out = [{"theme": k, "count": v, "summary": summaries.get(k) if v >= m else None,
            "note": None if v >= m else f"{m}'den az yorum: özet yazılmadı"} for k, v in sorted(counts.items(), key=lambda x: -x[1])]
    comments = None
    if raw:
        comments = [{"questionKey": r.question_key, "text": r.masked_text, "theme": r.theme, "probability": r.theme_prob} for r in rows]
        random.shuffle(comments)
    return {"suppressed": False, "total": len(rows), "themes": out, "comments": comments, "unclassified": counts.get("Sınıflanmadı", 0)}


def classify_comments(engine: sa.engine.Engine, tenant: str, choose: Callable[[str, list[str]], Any], theme_list: list[str]) -> int:
    """Sınıflanmamış yorumlar kapalı tema listesine (tek token + olasılık). Olasılık saklanır; eşik uygulanmaz, ekranda yazar."""
    ensure(engine)
    with engine.connect() as c:
        rows = c.execute(sa.select(COMMENTS.c.id, COMMENTS.c.masked_text).where(COMMENTS.c.tenant_id == tenant, COMMENTS.c.theme.is_(None))).all()
    done = 0
    for r in rows:
        prompt, labels = T.theme_prompt(r.masked_text, theme_list)
        ch = choose(prompt, labels)
        if getattr(ch, "choice", None) not in labels:
            continue
        theme = theme_list[labels.index(ch.choice)]
        p = (ch.probs or {}).get(ch.choice) if getattr(ch, "probs", None) else None
        with engine.begin() as c:
            c.execute(COMMENTS.update().where(COMMENTS.c.id == r.id).values(theme=theme, theme_prob=p))
        done += 1
    return done


def summarize_themes(engine: sa.engine.Engine, tenant: str, sid: str, chat: Callable[[list[dict[str, str]]], str]) -> dict[str, str]:
    """Eşik ve üstü yorumlu her tema için alıntısız özet; şirket sonucu satırına yazılır."""
    s = get_survey(engine, tenant, sid)
    if s["state"] != "kapandi" or not s["minGroup"]:
        raise HrError("Tema özeti anket kapanıp gösterim eşiği girilince yazılır.", 409)
    with engine.connect() as c:
        rows = c.execute(sa.select(COMMENTS.c.theme, COMMENTS.c.masked_text).where(COMMENTS.c.survey_id == sid, COMMENTS.c.theme.isnot(None))).all()
    by: dict[str, list[str]] = {}
    for r in rows:
        by.setdefault(r.theme, []).append(r.masked_text)
    out: dict[str, str] = {}
    for theme, texts in by.items():
        if len(texts) < s["minGroup"]:
            continue
        random.shuffle(texts)
        out[theme] = (chat(T.theme_summary_messages(theme, texts)) or "").strip()[:1500]
    with engine.begin() as c:
        c.execute(RESULTS.update().where(RESULTS.c.survey_id == sid, RESULTS.c.scope == "sirket").values(themes_json=dump(out)))
    return out


def share_results(engine: sa.engine.Engine, tenant: str, actor: str, sid: str) -> dict[str, Any]:
    with engine.begin() as c:
        s = _survey_row(c, tenant, sid)
        if s.state != "kapandi" or not s.unit_breakdown or not s.min_group:
            raise HrError("Birim sonucu yalnız kapanmış, birim kırılımlı ve eşiği girilmiş ankette paylaşılır.", 409)
        c.execute(SURVEYS.update().where(SURVEYS.c.id == sid).values(results_shared_at=now(), updated_by=actor, updated_at=now()))
    return get_survey(engine, tenant, sid)


def my_unit_results(engine: sa.engine.Engine, tenant: str, username: str) -> dict[str, Any]:
    """Birim yöneticisi: yöneticisi olduğu birimler (ve altları) için paylaşılmış anket sonuçları; eşik kuralı aynen."""
    ensure(engine)
    org = Org(engine, tenant)
    managed = org.managed(username)
    roots = [u for u in managed if (org.units[u].parent_id not in managed)]
    with engine.connect() as c:
        surveys = c.execute(sa.select(SURVEYS.c.id).where(SURVEYS.c.tenant_id == tenant, SURVEYS.c.results_shared_at.isnot(None))
                            .order_by(SURVEYS.c.closes_at.desc())).all()
    out = []
    for (sid,) in surveys:
        for u in sorted(roots, key=lambda x: (org.name(x) or "").casefold()):
            out.append(results(engine, tenant, sid, u, allowed_units=managed))
    return {"units": [{"id": u, "name": org.name(u)} for u in roots], "results": out}


# ------------------------------------------------------------------ öneri kutusu


def _sugg_out(r: Any, org: Org, *, show_author: bool) -> dict[str, Any]:
    return {"id": r.id, "createdDay": iso(r.created_day), "anonymous": r.author_employee_id is None,
            "author": (org.emp[r.author_employee_id].display_name if show_author and r.author_employee_id in org.emp else None),
            "text": r.text, "topic": r.topic, "topicProb": r.topic_prob, "topicSource": r.topic_source, "personal": bool(r.personal),
            "routedUnitId": r.routed_unit_id, "routedUnitName": org.name(r.routed_unit_id), "routedAt": iso(r.routed_at),
            "state": r.state, "stateLabel": SUGG_STATES.get(r.state, r.state), "answer": r.answer or "",
            "answeredBy": r.answered_by, "answeredAt": iso(r.answered_at)}


def create_suggestion(engine: sa.engine.Engine, tenant: str, username: str, body: dict[str, Any]) -> dict[str, Any]:
    ensure(engine)
    text = str(body.get("text") or "").strip()[:4000]
    if len(text) < 5:
        raise HrError("Önerinizi yazın.")
    anonymous = bool(body.get("anonymous"))
    author = None
    code = None
    if not anonymous:
        me = Org(engine, tenant).me(username)
        if not me:
            raise HrError("Adlı öneri için çalışan kaydınız yok; adsız gönderebilirsiniz.")
        author = me.id
    else:
        raw = "".join(secrets.choice(_PAPER_ALPHABET) for _ in range(10))
        code = f"{raw[:5]}-{raw[5:]}"
    sid = new_id("oneri")
    with engine.begin() as c:
        c.execute(SUGGESTIONS.insert().values(id=sid, tenant_id=tenant, created_day=date.today(), author_employee_id=author,
                                              follow_hash=_hash(_norm_code(code)) if code else None, text=text, personal=False,
                                              state="yeni"))
    return {"id": sid, "anonymous": anonymous, "followCode": code}


def list_suggestions(engine: sa.engine.Engine, tenant: str, who: H.Who, *, state: str = "") -> list[dict[str, Any]]:
    ensure(engine)
    org = Org(engine, tenant)
    stmt = sa.select(SUGGESTIONS).where(SUGGESTIONS.c.tenant_id == tenant)
    if state in SUGG_STATES:
        stmt = stmt.where(SUGGESTIONS.c.state == state)
    admin = who.can(F_SUGG_ADMIN)
    managed = org.managed(who.user) if who.can(F_SUGG_ANSWER) else set()
    if not admin and not managed:
        raise HrError("Öneri kutusu yönetimi rolünüzde yok.", 403)
    with engine.connect() as c:
        rows = c.execute(stmt.order_by(SUGGESTIONS.c.created_day.desc(), SUGGESTIONS.c.id)).all()
    return [_sugg_out(r, org, show_author=True) for r in rows
            if admin or (r.routed_unit_id in managed and not r.personal)]


def my_suggestions(engine: sa.engine.Engine, tenant: str, username: str) -> list[dict[str, Any]]:
    ensure(engine)
    org = Org(engine, tenant)
    me = org.me(username)
    if not me:
        return []
    with engine.connect() as c:
        rows = c.execute(sa.select(SUGGESTIONS).where(SUGGESTIONS.c.tenant_id == tenant, SUGGESTIONS.c.author_employee_id == me.id)
                         .order_by(SUGGESTIONS.c.created_day.desc())).all()
    return [_sugg_out(r, org, show_author=False) for r in rows]


def track_suggestion(engine: sa.engine.Engine, tenant: str, code: str) -> dict[str, Any]:
    ensure(engine)
    with engine.connect() as c:
        r = c.execute(sa.select(SUGGESTIONS).where(SUGGESTIONS.c.tenant_id == tenant, SUGGESTIONS.c.follow_hash == _hash(_norm_code(code)))).first()
    if r is None:
        raise HrError("Takip kodu bulunamadı.", 404)
    return _sugg_out(r, Org(engine, tenant), show_author=False)


def suggestion_action(engine: sa.engine.Engine, tenant: str, who: H.Who, sid: str, action: str, body: dict[str, Any],
                      topics: list[str]) -> dict[str, Any]:
    """route (İK: birime; kişiyle ilgili şikâyet yönlendirilmez) · topic (İK konu düzeltir) · answer · close."""
    ensure(engine)
    org = Org(engine, tenant)
    with engine.begin() as c:
        r = c.execute(sa.select(SUGGESTIONS).where(SUGGESTIONS.c.id == sid, SUGGESTIONS.c.tenant_id == tenant)).first()
        if r is None:
            raise HrError("Öneri bulunamadı.", 404)
        admin = who.can(F_SUGG_ADMIN)
        t = now()
        if action == "topic":
            if not admin:
                raise HrError("Konu düzeltme İK'nındır.", 403)
            topic = str(body.get("topic") or "")
            if topic not in topics:
                raise HrError("Listeden bir konu seçin.")
            vals: dict[str, Any] = dict(topic=topic, topic_source="ik", topic_prob=None, personal=topic == T.PERSONAL_TOPIC or bool(body.get("personal")))
            if vals["personal"] and r.routed_unit_id:
                vals.update(routed_unit_id=None, state="yeni")
        elif action == "route":
            if not admin:
                raise HrError("Yönlendirme İK'nındır.", 403)
            if r.personal or r.topic == T.PERSONAL_TOPIC:
                raise HrError("Bir çalışanla ilgili şikâyet birime yönlendirilmez; İK'da kalır.", 409)
            uid = body.get("unitId")
            if uid not in org.units:
                raise HrError("Birim seçin.")
            if r.state in ("cevaplandi", "kapandi"):
                raise HrError("Cevaplanmış öneri yeniden yönlendirilmez.", 409)
            vals = dict(routed_unit_id=uid, routed_by=who.user, routed_at=t, state="yonlendirildi")
        elif action == "answer":
            can = admin or (who.can(F_SUGG_ANSWER) and r.routed_unit_id in org.managed(who.user) and not r.personal)
            if not can:
                raise HrError("Bu öneriyi cevaplama yetkiniz yok (yalnız İK ya da yönlendirilen birimin yöneticisi).", 403)
            ans = str(body.get("answer") or "").strip()[:4000]
            if not ans:
                raise HrError("Cevabı yazın.")
            vals = dict(answer=ans, answered_by=who.user, answered_at=t, state="cevaplandi")
        elif action == "close":
            if not admin:
                raise HrError("Kapatma İK'nındır.", 403)
            vals = dict(state="kapandi", closed_at=t)
        else:
            raise HrError("Bilinmeyen işlem.", 404)
        c.execute(SUGGESTIONS.update().where(SUGGESTIONS.c.id == sid).values(**vals))
        row = c.execute(sa.select(SUGGESTIONS).where(SUGGESTIONS.c.id == sid)).first()
    return _sugg_out(row, org, show_author=True)


def suggest_topics(engine: sa.engine.Engine, tenant: str, choose: Callable[[str, list[str]], Any], topics: list[str]) -> int:
    """Yeni önerilere Zeki AI konu önerisi (K2); İK düzeltir. «Kişiyle ilgili şikâyet» işareti öneriyi İK'da tutar."""
    ensure(engine)
    with engine.connect() as c:
        rows = c.execute(sa.select(SUGGESTIONS.c.id, SUGGESTIONS.c.text).where(SUGGESTIONS.c.tenant_id == tenant, SUGGESTIONS.c.topic.is_(None))).all()
    names = [e.display_name for e in Org(engine, tenant).emp.values()] if rows else []
    done = 0
    for r in rows:
        masked, _ = T.mask_text(r.text, names)
        prompt, labels = T.topic_prompt(masked, topics)
        ch = choose(prompt, labels)
        if getattr(ch, "choice", None) not in labels:
            continue
        topic = topics[labels.index(ch.choice)]
        p = (ch.probs or {}).get(ch.choice) if getattr(ch, "probs", None) else None
        with engine.begin() as c:
            c.execute(SUGGESTIONS.update().where(SUGGESTIONS.c.id == r.id).values(topic=topic, topic_prob=p, topic_source="zeki",
                                                                                  personal=topic == T.PERSONAL_TOPIC))
        done += 1
    return done


def suggestion_stats(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    ensure(engine)
    with engine.connect() as c:
        rows = c.execute(sa.select(SUGGESTIONS.c.state, SUGGESTIONS.c.created_day, SUGGESTIONS.c.answered_at).where(SUGGESTIONS.c.tenant_id == tenant)).all()
    answered = [r for r in rows if r.answered_at is not None]
    days = [(H.aware(r.answered_at).date() - r.created_day).days for r in answered]
    return {"total": len(rows), "answered": len(answered), "open": sum(1 for r in rows if r.state in ("yeni", "yonlendirildi")),
            "avgDays": round(sum(days) / len(days), 1) if days else None}


# ------------------------------------------------------------------ aksiyon planı


def _action_out(r: Any, org: Org) -> dict[str, Any]:
    return {"id": r.id, "surveyId": r.survey_id, "unitId": r.unit_id, "unitName": org.name(r.unit_id), "questionKey": r.question_key,
            "title": r.title, "ownerEmployeeId": r.owner_employee_id,
            "ownerName": org.emp[r.owner_employee_id].display_name if r.owner_employee_id in org.emp else None,
            "dueOn": iso(r.due_on), "state": r.state, "stateLabel": ACTION_STATES.get(r.state, r.state), "note": r.note or "",
            "createdBy": r.created_by, "updatedAt": iso(r.updated_at), "closedAt": iso(r.closed_at)}


def list_actions(engine: sa.engine.Engine, tenant: str, who: H.Who, survey_id: str = "") -> dict[str, Any]:
    ensure(engine)
    org = Org(engine, tenant)
    admin = who.can(F_ACTION)
    managed = org.managed(who.user)
    stmt = sa.select(ACTIONS).where(ACTIONS.c.tenant_id == tenant)
    if survey_id:
        stmt = stmt.where(ACTIONS.c.survey_id == survey_id)
    with engine.connect() as c:
        rows = c.execute(stmt.order_by(ACTIONS.c.due_on.is_(None), ACTIONS.c.due_on)).all()
    items = [_action_out(r, org) for r in rows if admin or (r.unit_id in managed)]
    for it in items:
        it["canEdit"] = admin or it["unitId"] in managed
    return {"items": items, "canCreate": admin}


def save_action(engine: sa.engine.Engine, tenant: str, who: H.Who, body: dict[str, Any], aid: Optional[str] = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """İK (`ik.aksiyon`) ekler ve her alanı düzeltir; birim yöneticisi kendi biriminin aksiyonunda durum ve not yazar."""
    ensure(engine)
    org = Org(engine, tenant)
    admin = who.can(F_ACTION)
    with engine.begin() as c:
        before = c.execute(sa.select(ACTIONS).where(ACTIONS.c.id == aid, ACTIONS.c.tenant_id == tenant)).first() if aid else None
        if aid and before is None:
            raise HrError("Aksiyon bulunamadı.", 404)
        if before is None and not admin:
            raise HrError("Aksiyon eklemek rolünüzde yok.", 403)
        if before is not None and not admin and before.unit_id not in org.managed(who.user):
            raise HrError("Bu aksiyon biriminizin değil.", 403)
        vals: dict[str, Any] = {}
        if admin:
            if "title" in body or before is None:
                vals["title"] = clean(body.get("title"), 300)
                if not vals["title"]:
                    raise HrError("Aksiyonun adı boş olamaz.")
            for key, col in (("surveyId", "survey_id"), ("unitId", "unit_id"), ("questionKey", "question_key"), ("ownerEmployeeId", "owner_employee_id")):
                if key in body:
                    vals[col] = body.get(key) or None
            if vals.get("unit_id") and vals["unit_id"] not in org.units:
                raise HrError("Birim bulunamadı.")
            if vals.get("owner_employee_id") and vals["owner_employee_id"] not in org.emp:
                raise HrError("Sorumlu çalışan kaydında yok.")
            if "dueOn" in body:
                vals["due_on"] = H.parse_date(body.get("dueOn"), "Son")
        elif set(body) - {"state", "note"}:
            raise HrError("Birim yöneticisi yalnız durum ve not yazar.", 403)
        if "state" in body:
            st = str(body.get("state"))
            if st not in ACTION_STATES:
                raise HrError("Durum geçersiz.")
            vals["state"] = st
            vals["closed_at"] = now() if st in ("tamam", "iptal") else None
        if "note" in body:
            vals["note"] = str(body.get("note") or "").strip()[:4000] or None
        t = now()
        if before is None:
            aid = new_id("aks")
            vals.setdefault("state", "acik")
            c.execute(ACTIONS.insert().values(id=aid, tenant_id=tenant, created_by=who.user, created_at=t, updated_by=who.user, updated_at=t, **vals))
            diff = {"yeni": vals["title"]}
        else:
            diff = {k: {"once": iso(getattr(before, k)) if isinstance(getattr(before, k), (date, datetime)) else getattr(before, k),
                        "sonra": iso(v) if isinstance(v, (date, datetime)) else v}
                    for k, v in vals.items() if k != "closed_at" and getattr(before, k) != v}
            c.execute(ACTIONS.update().where(ACTIONS.c.id == aid).values(updated_by=who.user, updated_at=t, **vals))
        row = c.execute(sa.select(ACTIONS).where(ACTIONS.c.id == aid)).first()
    return _action_out(row, org), diff


# ------------------------------------------------------------------ zamanlayıcı


def run_due(engine: sa.engine.Engine, tenant: str, *, today: Optional[date] = None,
            choose: Optional[Callable[[str, list[str]], Any]] = None, chat: Optional[Callable[[list[dict[str, str]]], str]] = None,
            st: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Açılış (planlı), kapanış (tarihi geçen), oryantasyon davetleri, tema sınıflama, tema özeti, öneri konusu. Her adım ayrı;
    birinin hatası diğerini durdurmaz."""
    ensure(engine)
    today = today or date.today()
    st = st or {"themes": T.DEFAULT_THEMES, "topics": T.DEFAULT_TOPICS}
    out: dict[str, Any] = {"opened": 0, "closed": [], "orientationInvites": 0, "classified": 0, "summarized": 0, "topics": 0, "errors": []}
    org = Org(engine, tenant)

    def step(name: str, fn: Callable[[], None]) -> None:
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            log.exception("hr: bağlılık run-due adımı %s", name)
            out["errors"].append(f"{name}: {type(e).__name__}")

    def open_planned() -> None:
        with engine.begin() as c:
            for s in c.execute(sa.select(SURVEYS).where(SURVEYS.c.tenant_id == tenant, SURVEYS.c.state == "planli",
                                                        SURVEYS.c.opens_at <= today)).all():
                n = _open_now(c, tenant, s, org)
                c.execute(SURVEYS.update().where(SURVEYS.c.id == s.id).values(state="acik", opened_at=now(), invited_count=n, updated_at=now()))
                out["opened"] += 1

    def close_due() -> None:
        with engine.connect() as c:
            due = [r.id for r in c.execute(sa.select(SURVEYS.c.id).where(SURVEYS.c.tenant_id == tenant, SURVEYS.c.state == "acik",
                                                                          SURVEYS.c.closes_at < today)).all()]
        for sid in due:
            close_survey(engine, tenant, "sistem", sid)
            out["closed"].append(sid)

    def orientation() -> None:
        with engine.begin() as c:
            for s in c.execute(sa.select(SURVEYS).where(SURVEYS.c.tenant_id == tenant, SURVEYS.c.state == "acik",
                                                        SURVEYS.c.kind.in_(tuple(ORIENTATION_DAYS)))).all():
                days = ORIENTATION_DAYS[s.kind]
                have = {r[0] for r in c.execute(sa.select(INVITES.c.employee_id).where(INVITES.c.survey_id == s.id)).all()}
                added = 0
                for e in org.audience(load(s.audience_json, {}) or {}):
                    if not e.username or not e.start_date or e.id in have:
                        continue
                    milestone = e.start_date + timedelta(days=days)
                    if s.opens_at <= milestone <= today:
                        c.execute(INVITES.insert().values(survey_id=s.id, employee_id=e.id, tenant_id=tenant, responded=False))
                        added += 1
                if added:
                    c.execute(SURVEYS.update().where(SURVEYS.c.id == s.id).values(invited_count=SURVEYS.c.invited_count + added))
                out["orientationInvites"] += added

    step("açılış", open_planned)
    step("kapanış", close_due)
    step("oryantasyon", orientation)
    if choose is not None:
        step("tema", lambda: out.__setitem__("classified", classify_comments(engine, tenant, choose, st["themes"])))
        step("konu", lambda: out.__setitem__("topics", suggest_topics(engine, tenant, choose, st["topics"])))
    if chat is not None:
        def summaries() -> None:
            with engine.connect() as c:
                sids = [r.survey_id for r in c.execute(sa.select(RESULTS.c.survey_id).where(
                    RESULTS.c.tenant_id == tenant, RESULTS.c.scope == "sirket", RESULTS.c.themes_json.is_(None))).all()]
                ready = {r.id for r in c.execute(sa.select(SURVEYS.c.id).where(SURVEYS.c.id.in_(sids or [""]), SURVEYS.c.min_group.isnot(None))).all()}
                pending = {r.survey_id for r in c.execute(sa.select(COMMENTS.c.survey_id).where(
                    COMMENTS.c.survey_id.in_(sids or [""]), COMMENTS.c.theme.is_(None))).all()}
            for sid in sorted(ready - pending):
                summarize_themes(engine, tenant, sid, chat)
                out["summarized"] += 1
        step("özet", summaries)
    return out


# ------------------------------------------------------------------ saklama ve imha


def due_comments(engine: sa.engine.Engine, tenant: str, at: datetime) -> list[str]:
    days = H.keep_days(engine, tenant, DC_COMMENTS)
    if not days:
        return []
    ensure(engine)
    with engine.connect() as c:
        sids = [r[0] for r in c.execute(sa.select(SURVEYS.c.id).where(SURVEYS.c.tenant_id == tenant, SURVEYS.c.state == "kapandi",
                                                                       SURVEYS.c.closed_at < at - timedelta(days=days))).all()]
        return sorted({r[0] for r in c.execute(sa.select(COMMENTS.c.survey_id).where(COMMENTS.c.survey_id.in_(sids or [""]))).all()})


def purge_comments(engine: sa.engine.Engine, tenant: str, ids: list[str], at: datetime) -> int:
    with engine.begin() as c:
        return c.execute(COMMENTS.delete().where(COMMENTS.c.tenant_id == tenant, COMMENTS.c.survey_id.in_(ids))).rowcount or 0


def due_suggestions(engine: sa.engine.Engine, tenant: str, at: datetime) -> list[str]:
    days = H.keep_days(engine, tenant, DC_SUGGESTIONS)
    if not days:
        return []
    ensure(engine)
    limit = at - timedelta(days=days)
    with engine.connect() as c:
        return [r[0] for r in c.execute(sa.select(SUGGESTIONS.c.id).where(
            SUGGESTIONS.c.tenant_id == tenant, SUGGESTIONS.c.state == "kapandi", SUGGESTIONS.c.closed_at < limit)).all()]


def purge_suggestions(engine: sa.engine.Engine, tenant: str, ids: list[str], at: datetime) -> int:
    with engine.begin() as c:
        return c.execute(SUGGESTIONS.delete().where(SUGGESTIONS.c.tenant_id == tenant, SUGGESTIONS.c.id.in_(ids))).rowcount or 0


def export_rows(engine: sa.engine.Engine, tenant: str, sid: str) -> list[list[Any]]:
    """Yalnız toplu sonuç (madde ortalamaları); tek tek cevap ya da yorum yok."""
    res = results(engine, tenant, sid)
    if res["suppressed"]:
        raise HrError(res["message"], 409)
    rows = [["Madde", "Tür", "Yanıt", "Ortalama", "Olumlu %", "eNPS"]]
    for it in res["items"]:
        rows.append([it["text"], QTYPES.get(it["type"], it["type"]), it["n"], it.get("mean") or "", it.get("favorable") or "", it.get("enps") or ""])
    rows.append(["Toplam yanıt", "", res["n"], "", "", res.get("enps") or ""])
    rows.append(["Bağlılık endeksi (0–100)", "", "", res.get("index") or "", "", ""])
    return rows
