"""İK sorgu bilgisi: ekrandaki her rakamın, o istekte portal veritabanında ÇALIŞAN sorgusu ve hesabı.

İK ekranlarının rakamları (işe alım, kayıtlar, eğitim, performans, bağlılık) portal tablolarından (`semantic_hr_*`)
Python'da hesaplanır; birkaç rakam CRM (eşitleme önizlemesi) ve Logo'dan (eğitim gideri, temsilci satışı) gelir.
Bu modül isteğin iş parçacığında çalışan her SELECT'i yakalar (`capture`): portal ifadesi değerleri yerine konmuş
biçimde derlenir (`provenance.portal_sql` — gösterilen = çalışan), dış sorgu (`record`) çalışan metniyle kaydedilir.
Uç her rakam alanını okunur bir formüle ve o formülü besleyen sorgulara bağlar (`build`).

Kişisel veri ve gizlilik (bağlayıcı):
- Sonuç satırı hiçbir kayda girmez. İK kaynaklarında satır sayısı da yazılmaz (`rows` yok): bir sorgunun satır sayısı
  çoğu zaman bir kişinin, bir ekibin ya da bir anket grubunun sayısıdır; gizlilik eşiği sayıyla sızmasın.
- Formül ve açıklama metinlerinde kişi adı, puan, aday bilgisi yoktur; yalnız kural.
- Anket ve kullanım haritasında eşik altı grubun rakamı ekranda «gizli»dir; sorgu bilgisinde de o alan «gizli (eşik
  altı)» hesabına bağlanır, sayı içermez (`hidden`).
"""
from __future__ import annotations

import re
import threading
import time
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

from semantic_bridge import provenance as P

_tl = threading.local()
_hook_lock = threading.Lock()

TABLES = {
    "semantic_hr_employees": "çalışan kaydı", "semantic_hr_units": "birimler", "semantic_hr_notices": "aydınlatma metinleri",
    "semantic_hr_consents": "rızalar", "semantic_hr_retention": "saklama süreleri", "semantic_hr_purge_runs": "imha tutanakları",
    "semantic_hr_access_log": "erişim kaydı", "semantic_hr_jobs": "arka plan işleri",
    "semantic_hr_candidates": "adaylar", "semantic_hr_positions": "pozisyonlar", "semantic_hr_stage_log": "aşama geçmişi",
    "semantic_hr_messages": "aday mesajları", "semantic_hr_candidate_evidence": "yetkinlik kanıtları",
    "semantic_hr_candidate_files": "aday dosyaları", "semantic_hr_interview_notes": "görüşme notları",
    "semantic_hr_interviews": "görüşmeler", "semantic_hr_templates": "şablonlar", "semantic_hr_recruit_reminders": "hatırlatmalar",
    "semantic_hr_courses": "eğitim kataloğu", "semantic_hr_sessions": "eğitim oturumları", "semantic_hr_enrollments": "katılımlar",
    "semantic_hr_certificates": "sertifikalar", "semantic_hr_learning_feedback": "eğitim anketi yanıtları",
    "semantic_hr_feedback_tokens": "anket davetleri (eğitim)", "semantic_hr_training_needs": "eğitim ihtiyaçları",
    "semantic_hr_training_budget": "eğitim bütçesi", "semantic_hr_page_visits": "ekran ziyaretleri",
    "semantic_hr_guides": "ekran rehberleri", "semantic_hr_guide_votes": "rehber oyları",
    "semantic_hr_goals": "hedefler", "semantic_hr_goal_checkins": "hedef ilerleme kayıtları",
    "semantic_hr_goal_revisions": "hedef değişiklikleri", "semantic_hr_review_cycles": "değerlendirme dönemleri",
    "semantic_hr_review_forms": "değerlendirme formları", "semantic_hr_reviews": "değerlendirmeler",
    "semantic_hr_work_summaries": "iş özetleri", "semantic_hr_surveys": "anketler", "semantic_hr_survey_templates": "anket şablonları",
    "semantic_hr_survey_invites": "anket davetleri", "semantic_hr_survey_paper_codes": "basılı anket kodları",
    "semantic_hr_survey_responses": "anket yanıtları", "semantic_hr_survey_results": "anket sonuç özetleri",
    "semantic_hr_survey_comments": "anket yorumları", "semantic_hr_suggestions": "öneri kutusu", "semantic_hr_actions": "aksiyonlar",
    "sl_query_log": "Zeki AI soru kaydı", "semantic_settings": "ayar kaydı", "semantic_access_grants": "yetki kaydı",
}
_TABLE_RE = re.compile(r"\b(semantic_[a-z0-9_]+|sl_[a-z0-9_]+)\b", re.I)


# ------------------------------------------------------------------ yakalama


def _stack() -> list[list[dict[str, Any]]]:
    return _tl.__dict__.setdefault("stack", [])


def _named(dialect: Any) -> Any:
    try:
        return type(dialect)(paramstyle="named")
    except Exception:  # noqa: BLE001
        from sqlalchemy.dialects import postgresql

        return postgresql.dialect(paramstyle="named")


def _render(stmt: Any, multiparams: Any, params: Any, dialect: Any) -> Optional[str]:
    """Çalışan ifade → değerleri yerinde metin. SELECT değilse None."""
    if isinstance(stmt, sa.sql.elements.TextClause):
        text = str(stmt).strip()
        if not re.match(r"(?is)^\s*(select|with)\b", text):
            return None
        bound = {}
        for v in (multiparams or ()):
            if isinstance(v, dict):
                bound.update(v)
        bound.update(params or {})
        return P.inline_params(text, bound, "portal") if bound else text
    if not getattr(stmt, "is_select", False):
        return None
    try:
        return P.portal_sql(stmt, dialect)
    except Exception:  # noqa: BLE001 — değer yazıcısı olmayan tür: adlı parametreyle derle, değeri biz yerleştiririz
        c = stmt.compile(dialect=_named(dialect), compile_kwargs={"render_postcompile": True})
        return P.inline_params(str(c).strip(), dict(c.params), "portal")


def _before(conn: Any, clauseelement: Any, multiparams: Any, params: Any, execution_options: Any) -> None:
    stack = _stack()
    if not stack:
        return
    try:
        text = _render(clauseelement, multiparams, params, conn.dialect)
    except Exception:  # noqa: BLE001 — sorgu bilgisi okumayı durdurmaz
        text = None
    if text:
        rec = {"kind": "portal", "sql": text, "at": time.time()}
        for lst in stack:
            lst.append(rec)


def _hook(engine: Any) -> None:
    """Dinleyici motor başına bir kez; yalnız yakalayıcısı açık iş parçacığında iş yapar."""
    if engine is None:
        return
    with _hook_lock:
        if not sa.event.contains(engine, "before_execute", _before):
            sa.event.listen(engine, "before_execute", _before)


class capture:
    """`with capture(engine) as got:` — bloğun iş parçacığında çalışan SELECT'ler ve `record` edilen dış sorgular."""

    def __init__(self, engine: Any):
        self.engine = engine

    def __enter__(self) -> list[dict[str, Any]]:
        _hook(self.engine)
        self.got: list[dict[str, Any]] = []
        _stack().append(self.got)
        return self.got

    def __exit__(self, *exc: Any) -> None:
        st = _stack()
        if st and st[-1] is self.got:
            st.pop()


def record(connection: str, title: str, sql: str, *, ms: Optional[int] = None, description: str = "") -> None:
    """Dış (Logo/CRM) sorgu: açık yakalayıcılara çalışan metniyle eklenir."""
    rec = {"kind": connection, "sql": sql, "title": title, "ms": ms, "at": time.time(), "description": description}
    for lst in _stack():
        lst.append(rec)


def recording(connection: str, title: str, run: Callable[[str], Any]) -> Callable[[str], Any]:
    """Çalıştırıcıyı sarar: her çalışan metin `record` edilir."""

    def wrapped(text: str) -> Any:
        t = time.monotonic()
        out = run(text)
        record(connection, title, text, ms=int((time.monotonic() - t) * 1000))
        return out

    return wrapped


# ------------------------------------------------------------------ kayıt kurma


def tables_of(sql: str) -> list[str]:
    seen: list[str] = []
    for m in _TABLE_RE.finditer(sql):
        t = m.group(1).lower()
        if t not in seen:
            seen.append(t)
    return seen


class Hk:
    """Yakalanan sorgular → `Kaynaklar`. Kimlik `ik.<önek>.<sıra>`; aynı metin bir kez."""

    def __init__(self, got: Iterable[dict[str, Any]], prefix: str, *, logo_db: Optional[str] = None,
                 crm_db: Optional[str] = None, as_of: Any = None):
        self.k = P.Kaynaklar(as_of=as_of)
        self.ids: list[tuple[str, list[str]]] = []          # (kimlik, tablolar)
        seen: dict[str, str] = {}
        n = 0
        for r in got:
            if r["sql"] in seen:
                continue
            n += 1
            sid = f"ik.{prefix}.{n}"
            if r["kind"] == "portal":
                tabs = tables_of(r["sql"])
                title = "Portal · " + ", ".join(TABLES.get(t, t) for t in tabs[:4]) if tabs else "Portal sorgusu"
                try:
                    self.k.portal(sid, title, r["sql"], None, description="Bu istekte çalışan okuma (değerleri yerinde).")
                except P.ProvenanceError:
                    continue
            else:
                tabs = [r["kind"]]
                try:
                    self.k.sorgu(sid, r["title"], r["kind"], r["sql"], database=logo_db if r["kind"] == "logo" else crm_db,
                                 ms=r.get("ms"), ran_at=r.get("at"), description=r.get("description") or "")
                except P.ProvenanceError:
                    continue
            seen[r["sql"]] = sid
            self.ids.append((sid, tabs))

    def inputs(self, tables: Optional[Iterable[str]] = None) -> list[str]:
        """Formülün girdileri: verilen tabloları (ya da «logo»/«crm») okuyan sorgular; verilmezse hepsi."""
        if tables is None:
            return [sid for sid, _ in self.ids]
        want = set(tables)
        return [sid for sid, tabs in self.ids if want & set(tabs)]

    def f(self, name: str, text: str, tables: Optional[Iterable[str]] = None) -> Optional[str]:
        ins = self.inputs(tables) or self.inputs()
        if not ins:
            return None
        return self.k.hesap(name, text, ins)

    def bind(self, mapping: dict[str, Any]) -> P.Kaynaklar:
        """`mapping`: alan yolu → (ad, formül[, tablolar]) ya da «hesap:ad» ya da None."""
        fields: dict[str, str] = {}
        for path, spec in mapping.items():
            if spec is None:
                continue
            if isinstance(spec, str):
                if spec.startswith("hesap:") and spec[6:] in self.k.formulas:
                    fields[path] = spec
                continue
            ref = self.f(*spec)
            if ref:
                fields[path] = ref
        self.k.alanlar(fields)
        return self.k


F_GIZLI = ("Gizli (eşik altı): bu grubun yanıt ya da kişi sayısı gösterim eşiğinin altında olduğu için rakam gösterilmez; "
           "sorgu bilgisi de sayı vermez. Eşik ayardadır; grup büyüdüğünde rakam görünür.")


def build(got: Iterable[dict[str, Any]], prefix: str, mapping: dict[str, Any], *, hidden: Iterable[str] = (),
          logo_db: Optional[str] = None, crm_db: Optional[str] = None, out: Optional[dict[str, Any]] = None,
          rest: Optional[tuple[str, str]] = None, ignore: Iterable[str] = ()) -> P.Kaynaklar:
    """Uçta tek çağrı: yakalananlardan kayıt kurar, alanları bağlar. `hidden`: eşik altı grupların alan yolları
    (satıra özel anahtar dahil, ör. «birimler[]:<id>») — «gizli» hesabına bağlanır, sorgu girdisi sayı taşımaz.
    `out` + `rest`: eşlemede adı geçmeyen ve rakam taşıyan üst anahtarlar (ad, formül) hesabına bağlanır — yeni bir
    alan eklenip kaynağı unutulsa da kaynaksız rakam kalmaz; `ignore` rakam olmayan sayılar."""
    hk = Hk(got, prefix, logo_db=logo_db, crm_db=crm_db)
    k = hk.bind(mapping)
    if out is not None and rest is not None:
        left = P.uncovered_numbers({**out, "kaynaklar": k.to_dict()}, ignore)
        tops = sorted({re.split(r"[.\[]", p_, 1)[0] for p_ in left})
        if tops:
            ref = hk.f(*rest)
            if ref:
                k.alanlar({t: ref for t in tops})
    hidden = list(hidden)
    if hidden and hk.ids:
        g = k.hesap("gizli", F_GIZLI, [hk.ids[0][0]])
        k.alanlar({path: g for path in hidden})
    return k


def db_names(rt: Callable[[], Any]) -> dict[str, Optional[str]]:
    """Yalnız veritabanı adları (sunucu, kullanıcı, parola okunmaz): Logo çalışma zamanı bağlantı dosyası, CRM ortamdaki."""
    import os

    try:
        logo_file = rt().settings.connection_file
    except Exception:  # noqa: BLE001
        logo_file = None
    return {"logo_db": P.connection_database(logo_file),
            "crm_db": P.connection_database(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE",
                                                           "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))}
