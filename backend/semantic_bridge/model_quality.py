"""M50 Zeki AI kalitesi: kapı koşuları, önce/sonra, sürüm kaydı, kullanıcı geri bildirimi, hata sınıfları, karne.

Zeki AI ince ayarlı bir model değildir; isabet katalog, kural ve eş anlamlılarla artar (bellek
`semantic-layer-v1-decision`). Bu modül o değişikliklerin etkisini ölçer ve kayda geçirir:

- **Koşu** (`semantic_mq_runs` + `semantic_mq_cases`): kapı betikleri (`tests/text2sql/resolver-gate.py`,
  `answer-gate.py`) `--report` ile bitince özet ve vaka listesini köprüye yazar. Her koşu, aynı takımın (suite +
  soru dosyası) bir önceki bitmiş koşusuyla karşılaştırılır: önceki koşuda SAĞLAM olup artık olmayan vaka
  «bozulan», tersi «düzelen». Rakamı model üretmez; hüküm betiğin referans SQL karşılaştırmasıdır.
- **Sürüm kaydı** (`semantic_mq_versions`): kod sürümü, katalog sürümü, bilgi paketi/kural özeti, dil havuzu özeti,
  model kimliği ve ayar özeti **tek satırda**. Her koşu raporunda ve her kurulumda yazılır; değişmediyse yeni satır
  açılmaz (kurulum her zaman yazar: ölçüm penceresine giren kurulum bu satırlardan görünür). M48'in kurulum kaydı
  (`semantic_itops_releases`) varsa yalnız okunur, ikinci kez yazılmaz.
- **Geri bildirim** (`semantic_mq_feedback`): cevabın altındaki Doğru / Kısmen / Yanlış + not. `sl_query_log.validated`
  da güncellenir (doğru → true, yanlış → false, kısmen → boş).
- **Hata sınıfları** (`semantic_mq_classes`): kurallar veridir (tablo satırı), kod değil. Bir kural koşulların
  listesidir; koşul verilen ölçütlerin hepsi tutarsa tutar, kural koşullarından biri tutarsa tutar; ilk tutan sınıf
  kazanır, hiçbiri tutmazsa «sınıflanamadı». İnsanın geri bildirim kuyruğunda verdiği sınıf kuralın önüne geçer.
- **Karne**: modül başına tek satır; ölçülmemiş satır «ölçülmedi» der, demo sayı yoktur.

Ekrana giden metinde teknoloji ya da model adı yazmaz (bellek `no-tech-names-on-screens`): model «Zeki AI modeli,
sürüm <ilk görüldüğü gün>» olarak gösterilir; gerçek kimlik yalnız iç kayıtta durur.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

import sqlalchemy as sa

log = logging.getLogger("semantic_bridge.model_quality")

_md = sa.MetaData()

RUNS = sa.Table(
    "semantic_mq_runs", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("suite", sa.String(24), nullable=False),          # resolver | answer | golden | regress
    sa.Column("label", sa.String(200), nullable=False, default=""),   # soru/altın dosyası (karşılaştırma anahtarı)
    sa.Column("status", sa.String(16), nullable=False),         # sirada | calisiyor | bitti | hata
    sa.Column("requested_by", sa.String(120)),
    sa.Column("requested_at", sa.DateTime(timezone=True)),
    sa.Column("started_at", sa.DateTime(timezone=True)),
    sa.Column("finished_at", sa.DateTime(timezone=True)),
    sa.Column("started_by", sa.String(120)),                    # betiğin koştuğu makine/hesap
    sa.Column("version_id", sa.Integer),
    sa.Column("code_sha", sa.String(64)),
    sa.Column("catalog_version", sa.Integer),
    sa.Column("rules_digest", sa.String(64)),
    sa.Column("model_ref", sa.String(200)),                      # iç kayıt; ekrana gitmez
    sa.Column("env", sa.String(8)),                              # test | vm
    sa.Column("metrics_json", sa.Text, nullable=False, default="{}"),
    sa.Column("baseline_run_id", sa.String(32)),
    sa.Column("total", sa.Integer, nullable=False, default=0),
    sa.Column("broken", sa.Integer, nullable=False, default=0),
    sa.Column("fixed", sa.Integer, nullable=False, default=0),
    sa.Column("installs_in_window_json", sa.Text, nullable=False, default="[]"),
    sa.Column("note", sa.Text),
    sa.Column("error", sa.Text),
    sa.Index("ix_mq_runs_suite", "tenant_id", "suite", "label", "finished_at"),
)

CASES = sa.Table(
    "semantic_mq_cases", _md,
    sa.Column("run_id", sa.String(32), primary_key=True),
    sa.Column("case_id", sa.String(80), primary_key=True),
    sa.Column("n", sa.Integer),
    sa.Column("question", sa.Text, nullable=False, default=""),
    sa.Column("status", sa.String(12), nullable=False),          # saglam | bozuk | kararsiz | veri | ret | hata | yeni
    sa.Column("klass", sa.String(40)),
    sa.Column("sql_text", sa.Text),
    sa.Column("result_digest", sa.String(64)),
    sa.Column("expected_digest", sa.String(64)),
    sa.Column("detail_json", sa.Text, nullable=False, default="[]"),   # okuma farkı satırları ya da referans farkları
    sa.Column("note", sa.Text),
)

VERSIONS = sa.Table(
    "semantic_mq_versions", _md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("at", sa.DateTime(timezone=True), nullable=False, index=True),
    sa.Column("source", sa.String(16), nullable=False),          # kosu | kurulum | elle
    sa.Column("kinds", sa.String(80), nullable=False, default=""),    # değişen parçalar: code,catalog,rules,model,prompt
    sa.Column("env", sa.String(8)),
    sa.Column("code_sha", sa.String(64)),
    sa.Column("catalog_version", sa.Integer),
    sa.Column("catalog_certified", sa.Integer),
    sa.Column("knowledge_digest", sa.String(64)),
    sa.Column("rules_digest", sa.String(64)),
    sa.Column("language_digest", sa.String(64)),
    sa.Column("prompt_digest", sa.String(64)),
    sa.Column("model_ref", sa.String(200)),                      # iç kayıt; ekrana gitmez
    sa.Column("model_digest", sa.String(64)),
    sa.Column("model_since", sa.DateTime(timezone=True)),        # bu model kimliğinin ilk görüldüğü an
    sa.Column("digest", sa.String(64), nullable=False),
    sa.Column("note", sa.Text),
    sa.Column("by", sa.String(120)),
)

FEEDBACK = sa.Table(
    "semantic_mq_feedback", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("query_id", sa.String(64), nullable=False, index=True),    # sl_query_log.id
    sa.Column("username", sa.String(120), nullable=False),
    sa.Column("verdict", sa.String(8), nullable=False),          # dogru | kismen | yanlis
    sa.Column("comment", sa.Text),
    sa.Column("at", sa.DateTime(timezone=True), nullable=False, index=True),
    sa.Column("triage_state", sa.String(12), nullable=False, default="yeni"),   # yeni | siniflandi | kapandi
    sa.Column("klass", sa.String(40)),
    sa.Column("handled_by", sa.String(120)),
    sa.Column("handled_at", sa.DateTime(timezone=True)),
    sa.Column("handle_note", sa.Text),
    sa.UniqueConstraint("tenant_id", "query_id", "username", name="uq_mq_feedback_user"),
)

CLASSES = sa.Table(
    "semantic_mq_classes", _md,
    sa.Column("klass", sa.String(40), primary_key=True),
    sa.Column("label", sa.String(120), nullable=False),
    sa.Column("help", sa.Text),
    sa.Column("sort", sa.Integer, nullable=False, default=100),
    sa.Column("counts_as_error", sa.Boolean, nullable=False, default=True),
    sa.Column("active", sa.Boolean, nullable=False, default=True),
    sa.Column("rule_json", sa.Text, nullable=False, default="{}"),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
)

STATE = sa.Table(
    "semantic_mq_state", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("key", sa.String(80), primary_key=True),
    sa.Column("value", sa.Text, nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

SUITES: dict[str, str] = {
    "resolver": "Okuma kapısı",          # soruların okunuşu kayıtlı temel çizgiyle aynı mı (modelsiz)
    "answer": "Cevap kapısı",            # doğrulanmış sorular referans rakamla aynı cevabı veriyor mu
    "golden": "Katalog kapısı",          # golden set tablo bulma (quality-gate)
    "regress": "Tam set karşılaştırması",
}
#: Ekrandan başlatılabilen takımlar ve zamanlayıcının çağıracağı varsayılan dosyalar.
STARTABLE = ("resolver", "answer")
CASE_STATUSES: dict[str, str] = {
    "saglam": "Sağlam", "bozuk": "Bozuk", "kararsiz": "Kararsız", "veri": "Veri durumu", "ret": "Ret",
    "hata": "Hata", "yeni": "Temel çizgide yok",
}
RUN_STATUSES: dict[str, str] = {"sirada": "Sırada", "calisiyor": "Çalışıyor", "bitti": "Bitti", "hata": "Hata"}
VERDICTS: dict[str, str] = {"dogru": "Doğru", "kismen": "Kısmen", "yanlis": "Yanlış"}
TRIAGE: dict[str, str] = {"yeni": "Yeni", "siniflandi": "Sınıflandı", "kapandi": "Kapandı"}
SOURCES: dict[str, str] = {"kosu": "Koşu anındaki durum", "kurulum": "Kurulum", "elle": "Elle kayıt"}
KIND_LABELS: dict[str, str] = {"code": "Kod", "catalog": "Katalog", "rules": "Bilgi paketi ve kurallar",
                               "model": "Zeki AI modeli", "prompt": "İstem", "language": "Gündelik terim havuzu"}
UNCLASSIFIED = "siniflanamadi"

#: Kullanıcının SQL'li bir cevap almadığı cevap türleri (sl_query_log.answer_type). MODULE_INTRO ölçüme girmez.
NON_ANSWER_TYPES = ("CLARIFICATION", "INCOMPLETE_ANSWER", "DATA_UNAVAILABLE", "NON_SQL_QUERY", "SQL_INVALID",
                    "DATA_SOURCE_UNAVAILABLE", "NOT_PERMITTED")
IGNORED_TYPES = ("MODULE_INTRO",)

#: Çözücünün açıklama izinde bir kavramın elendiğini söyleyen cümleler → gerekçe kodu. `tests/text2sql/resolver-gate.py`
#: ile aynı liste (betik köprüyü içe aktarmadan koşar; biri değişirse öbürü de değişmeli).
DROP_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"'(.+?)' katalogda .*? tarafında .*? olarak tanımlı; .*modele?l? o kaynakta yorumlayacak"), "OTHER_SOURCE_LEFT_TO_MODEL"),
    (re.compile(r"'(.+?)' bir belge türü olarak okundu"), "METRIC_READ_AS_DOCUMENT_NAME"),
    (re.compile(r"'(.+?)' sayım sözcüğü olarak okundu"), "MEASURE_READ_AS_COUNT_WORD"),
    (re.compile(r"'(.+?)' .*?ölçüsünün birimi olarak okundu"), "MEASURE_READ_AS_UNIT"),
    (re.compile(r"'(.+?)' sıralama sayısı olarak okundu"), "WORD_READ_AS_ROW_LIMIT"),
    (re.compile(r"varsayılan dönem geri alındı"), "DEFAULT_PERIOD_WITHDRAWN"),
    (re.compile(r"dönem belirtilmedi → varsayılan"), "DEFAULT_PERIOD_APPLIED"),
    (re.compile(r"→ o kaynak seçildi"), "SOURCE_CHOSEN_BY_TALLY"),
)

#: Kurulumda tohumlanan sınıflar (§13). Kurallar tabloya yazılır; sonradan tablodan düzeltilir, kod değişmez.
DEFAULT_CLASSES: list[dict[str, Any]] = [
    {"klass": "yetki_disi", "label": "Yetki dışı", "counts": False, "sort": 10,
     "help": "Kişinin veri alanı dışındaki soru. İsabetsizlik sayılmaz.",
     "rule": {"any": [{"answerTypes": ["NOT_PERMITTED"]}, {"textAny": ["yetkiniz yok", "veri alanı dışında"]}]}},
    {"klass": "baglanti", "label": "Veri kaynağına ulaşılamadı", "counts": False, "sort": 20,
     "help": "Logo ya da CRM o anda cevap vermedi; soru değil bağlantı. İsabetsizlik sayılmaz.",
     "rule": {"any": [{"answerTypes": ["DATA_SOURCE_UNAVAILABLE", "HTTP_ERROR"]},
                      {"textAny": ["veri kaynağı şu anda yanıt vermiyor"]}]}},
    {"klass": "netlestirme", "label": "Netleştirme istendi", "counts": False, "sort": 30,
     "help": "Zeki AI soruyu cevaplamak yerine hangi anlamın kastedildiğini sordu.",
     "rule": {"any": [{"answerTypes": ["CLARIFICATION"]}, {"textAny": ["gelen clarify"]}]}},
    {"klass": "tanimsiz_terim", "label": "Katalogda olmayan terim", "counts": True, "sort": 40,
     "help": "Sorudaki iş terimi katalogda tanımlı değil; çözüm katalog yazımı ya da eş anlamlı.",
     "rule": {"any": [{"unresolved": True}, {"textAny": ["katalogda tanımlı bir kavram değil"]}]}},
    {"klass": "kaynak_kacirma", "label": "Yanlış ya da eksik kaynak", "counts": True, "sort": 50,
     "help": "Soru yanlış tabloya/sisteme okundu ya da gereken kaynak düştü.",
     "rule": {"any": [{"dropCodes": ["OTHER_SOURCE_LEFT_TO_MODEL", "SOURCE_CHOSEN_BY_TALLY"]},
                      {"textAny": ["sources:"]},
                      {"gateKeys": ["catalogAudit"], "textAny": ["tablo", "kaynak", "varlık"]}]}},
    {"klass": "olcu_yerine_kolon", "label": "Ölçü yerine kolon", "counts": True, "sort": 60,
     "help": "Tanımlı ölçünün formülü yerine ham kolon ya da sayım okundu.",
     "rule": {"any": [{"dropCodes": ["MEASURE_READ_AS_COUNT_WORD", "METRIC_READ_AS_DOCUMENT_NAME", "MEASURE_READ_AS_UNIT"]},
                      {"gateKeys": ["catalogAudit"], "textAny": ["ölçü", "formül", "metrik"]}]}},
    {"klass": "donem_sekil", "label": "Dönem ya da cevap şekli", "counts": True, "sort": 70,
     "help": "Dönem, karşılaştırma, kırılım, sıralama ya da satır sayısı sorunun istediğinden farklı.",
     "rule": {"any": [{"dropCodes": ["DEFAULT_PERIOD_WITHDRAWN", "DEFAULT_PERIOD_APPLIED", "WORD_READ_AS_ROW_LIMIT"]},
                      {"gateKeys": ["dataCoverage"]},
                      {"gateKeys": ["unmetObligations"], "textAny": ["dönem", "yıl", "karşılaştır", "kırılım", "grup", "sıral"]},
                      {"textAny": ["temporal:", "shape:", "grain:", "groupby:", "limit:", "satır sayısı"]}]}},
    {"klass": "veri_yok", "label": "Veri yok", "counts": False, "sort": 80,
     "help": "Sorulan dönem ya da alan için veri tutulmuyor ya da sonuç boş. Dürüst ret isabetsizlik sayılmaz.",
     "rule": {"any": [{"answerTypes": ["DATA_UNAVAILABLE"]}, {"executedEmpty": True}, {"caseStatus": ["veri"]}]}},
    {"klass": "model_reddi", "label": "Zeki AI sorgu yazamadı", "counts": True, "sort": 90,
     "help": "Model SQL üretmedi, ürettiği SQL kapıdan geçmedi ya da beklenen cevap yerine ret verdi.",
     "rule": {"any": [{"answerTypes": ["NON_SQL_QUERY", "SQL_INVALID"]}, {"gateKeys": ["critic", "guardrail"]},
                      {"textAny": ["gelen deny", "gelen error"]}]}},
]
_RULE_KEYS = {"answerTypes", "gateKeys", "dropCodes", "textAny", "unresolved", "executedEmpty", "caseStatus"}

_ready: set[int] = set()
_lock = threading.Lock()


class QualityError(ValueError):
    """Kullanıcıya olduğu gibi gösterilecek düz Türkçe hata; `status` HTTP kodu."""

    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(v: Optional[datetime]) -> Optional[datetime]:
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _iso(v: Optional[datetime]) -> Optional[str]:
    v = _aware(v)
    return v.isoformat() if v else None


def _parse_dt(v: Any) -> Optional[datetime]:
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return _aware(v)
    try:
        return _aware(datetime.fromisoformat(str(v).replace("Z", "+00:00")))
    except ValueError:
        raise QualityError(f"Tarih okunamadı: {str(v)[:40]}") from None


def _loads(v: Any, default: Any) -> Any:
    if v in (None, ""):
        return default
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return default


def _dumps(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


def _new_id() -> str:
    return uuid.uuid4().hex


def digest_of(value: Any) -> str:
    """Kayıt karşılaştırması için kısa özet (sonuç satırları, referans, ayar)."""
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:32]


def fold(text: Any) -> str:
    """Türkçe harf duyarsız karşılaştırma için."""
    s = str(text or "").replace("I", "ı").replace("İ", "i").lower()
    return s.replace("̇", "")


# ------------------------------------------------------------------ kurulum


def ensure(engine: sa.engine.Engine) -> None:
    key = id(engine)
    with _lock:
        if key in _ready:
            return
        from semantic_layer.store import schema_stamp
        schema_stamp.create_all(_md, engine)
        seed_classes(engine)
        _ready.add(key)


def seed_classes(engine: sa.engine.Engine) -> int:
    """Eksik sınıfları ekler; var olanın (düzeltilmiş olabilir) kuralına dokunmaz."""
    with engine.begin() as c:
        have = {r[0] for r in c.execute(sa.select(CLASSES.c.klass))}
        added = 0
        for d in DEFAULT_CLASSES:
            if d["klass"] in have:
                continue
            c.execute(CLASSES.insert().values(klass=d["klass"], label=d["label"], help=d["help"], sort=d["sort"],
                                              counts_as_error=d["counts"], active=True, rule_json=_dumps(d["rule"]),
                                              updated_by="kurulum", updated_at=_now()))
            added += 1
    return added


# ------------------------------------------------------------------ hata sınıfı kuralları


def drop_codes(explanation: Iterable[str]) -> list[str]:
    out: list[str] = []
    for line in explanation or []:
        for pattern, code in DROP_PATTERNS:
            if pattern.search(str(line)) and code not in out:
                out.append(code)
    return out


def evidence_from_log(row: dict[str, Any]) -> dict[str, Any]:
    """Soru kaydından (sl_query_log satırı) sınıflamanın okuduğu kanıt."""
    resolved = _loads(row.get("resolved_json"), {}) or {}
    gate = _loads(row.get("gate_json"), {}) or {}
    text_parts = [row.get("answer_summary"), row.get("error")]
    for k, v in (gate.items() if isinstance(gate, dict) else []):
        text_parts.append(json.dumps(v, ensure_ascii=False, default=str) if not isinstance(v, str) else v)
    explanation = resolved.get("explanation") or []
    return {
        "answerType": row.get("answer_type") or "",
        "executed": bool(row.get("executed")),
        "rowCount": row.get("row_count"),
        "gateKeys": sorted(gate.keys()) if isinstance(gate, dict) else [],
        "dropCodes": drop_codes(explanation),
        "unresolved": list(resolved.get("unresolved") or []),
        "text": fold(" ".join(str(p) for p in text_parts if p)),
        "caseStatus": "",
    }


def evidence_from_case(case: dict[str, Any]) -> dict[str, Any]:
    """Kapı vakasından kanıt: betiğin yazdığı fark satırları ve düşen kavram kodları."""
    detail = case.get("detail") or []
    lines = [str(x) for x in detail] if isinstance(detail, list) else [str(detail)]
    codes = [c for c in (case.get("dropCodes") or []) if isinstance(c, str)]
    for line in lines:
        for _, code in DROP_PATTERNS:
            if code in line and code not in codes:
                codes.append(code)
    return {
        "answerType": str(case.get("answerType") or ""),
        "executed": False,
        "rowCount": None,
        "gateKeys": [],
        "dropCodes": codes,
        "unresolved": list(case.get("unresolved") or []),
        "text": fold(" ".join(lines + [str(case.get("note") or "")])),
        "caseStatus": str(case.get("status") or ""),
    }


def _condition_holds(cond: dict[str, Any], ev: dict[str, Any]) -> bool:
    if not cond:
        return False
    for key, want in cond.items():
        if key == "answerTypes" and ev["answerType"] not in want:
            return False
        if key == "gateKeys" and not set(want) & set(ev["gateKeys"]):
            return False
        if key == "dropCodes" and not set(want) & set(ev["dropCodes"]):
            return False
        if key == "textAny" and not any(fold(w) in ev["text"] for w in want):
            return False
        if key == "unresolved" and bool(ev["unresolved"]) != bool(want):
            return False
        if key == "executedEmpty" and bool(want) != (ev["executed"] and ev.get("rowCount") == 0):
            return False
        if key == "caseStatus" and ev["caseStatus"] not in want:
            return False
    return True


def rule_matches(rule: dict[str, Any], ev: dict[str, Any]) -> bool:
    return any(_condition_holds(c, ev) for c in (rule.get("any") or []) if isinstance(c, dict))


def validate_rule(rule: Any) -> dict[str, Any]:
    if not isinstance(rule, dict) or not isinstance(rule.get("any"), list) or not rule["any"]:
        raise QualityError("Kural {\"any\": [koşul, …]} biçiminde olmalı.")
    for cond in rule["any"]:
        if not isinstance(cond, dict) or not cond:
            raise QualityError("Her koşul boş olmayan bir nesne olmalı.")
        unknown = set(cond) - _RULE_KEYS
        if unknown:
            raise QualityError(f"Bilinmeyen ölçüt: {', '.join(sorted(unknown))}. Geçerli: {', '.join(sorted(_RULE_KEYS))}.")
        for k, v in cond.items():
            if k in ("unresolved", "executedEmpty"):
                if not isinstance(v, bool):
                    raise QualityError(f"«{k}» doğru/yanlış olmalı.")
            elif not isinstance(v, list) or not v or not all(isinstance(x, str) and x.strip() for x in v):
                raise QualityError(f"«{k}» boş olmayan metin listesi olmalı.")
    return rule


def load_classes(engine: sa.engine.Engine, *, active_only: bool = True) -> list[dict[str, Any]]:
    with engine.connect() as c:
        q = sa.select(CLASSES).order_by(CLASSES.c.sort, CLASSES.c.klass)
        if active_only:
            q = q.where(CLASSES.c.active.is_(True))
        rows = c.execute(q).mappings().all()
    return [{"klass": r["klass"], "label": r["label"], "help": r["help"], "sort": r["sort"],
             "countsAsError": bool(r["counts_as_error"]), "active": bool(r["active"]),
             "rule": _loads(r["rule_json"], {}), "updatedBy": r["updated_by"], "updatedAt": _iso(r["updated_at"])}
            for r in rows]


def classify(ev: dict[str, Any], classes: list[dict[str, Any]]) -> str:
    for k in classes:
        if k.get("active", True) and rule_matches(k.get("rule") or {}, ev):
            return k["klass"]
    return UNCLASSIFIED


def update_class(engine: sa.engine.Engine, klass: str, body: dict[str, Any], user: str) -> dict[str, Any]:
    vals: dict[str, Any] = {}
    if "label" in body:
        label = str(body.get("label") or "").strip()
        if not label:
            raise QualityError("Sınıf adı boş olamaz.")
        vals["label"] = label[:120]
    if "help" in body:
        vals["help"] = str(body.get("help") or "").strip()[:2000] or None
    if "active" in body:
        vals["active"] = bool(body["active"])
    if "countsAsError" in body:
        vals["counts_as_error"] = bool(body["countsAsError"])
    if "rule" in body:
        vals["rule_json"] = _dumps(validate_rule(body["rule"]))
    if "sort" in body:
        try:
            vals["sort"] = int(body["sort"])
        except (TypeError, ValueError):
            raise QualityError("Sıra tam sayı olmalı.") from None
    if not vals:
        raise QualityError("Değişecek alan yok.")
    vals.update(updated_by=user, updated_at=_now())
    with engine.begin() as c:
        n = c.execute(CLASSES.update().where(CLASSES.c.klass == klass).values(**vals)).rowcount
    if not n:
        raise QualityError("Sınıf bulunamadı.", 404)
    return next(k for k in load_classes(engine, active_only=False) if k["klass"] == klass)


# ------------------------------------------------------------------ sürüm kaydı

_VERSION_FIELDS = ("code_sha", "catalog_version", "catalog_certified", "knowledge_digest", "rules_digest",
                   "language_digest", "prompt_digest", "model_ref", "model_digest")
_KIND_OF = {"code_sha": "code", "catalog_version": "catalog", "catalog_certified": "catalog",
            "knowledge_digest": "rules", "rules_digest": "rules", "language_digest": "language",
            "prompt_digest": "prompt", "model_ref": "model", "model_digest": "model"}


def snapshot_digest(snap: dict[str, Any]) -> str:
    return digest_of({k: snap.get(k) for k in _VERSION_FIELDS})


def record_version(engine: sa.engine.Engine, tenant: str, snap: dict[str, Any], *, source: str, by: str,
                   env: Optional[str] = None, note: Optional[str] = None, force: bool = False,
                   at: Optional[datetime] = None) -> dict[str, Any]:
    """Anlık görüntüyü yazar. Önceki satırla aynıysa ve `force` yoksa yeni satır açmaz (öncekini döner).
    Kurulum (`source=kurulum`) her zaman yazar: ölçüm penceresindeki kurulum bu satırlardan görünür."""
    if source not in SOURCES:
        raise QualityError(f"Kaynak {', '.join(SOURCES)} olmalı.")
    snap = {k: snap.get(k) for k in _VERSION_FIELDS}
    dig = snapshot_digest(snap)
    with engine.begin() as c:
        last = c.execute(sa.select(VERSIONS).where(VERSIONS.c.tenant_id == tenant)
                         .order_by(VERSIONS.c.id.desc()).limit(1)).mappings().first()
        if last and last["digest"] == dig and not force and source != "kurulum":
            return version_view(last)
        kinds = [] if last is None else sorted({_KIND_OF[k] for k in _VERSION_FIELDS
                                                 if snap.get(k) not in (None, "") and snap.get(k) != last[k]})
        since = None
        if snap.get("model_digest"):
            first = c.execute(sa.select(sa.func.min(VERSIONS.c.at)).where(
                VERSIONS.c.tenant_id == tenant, VERSIONS.c.model_digest == snap["model_digest"])).scalar()
            since = _aware(first) if first else None
        stamp = at or _now()
        row = {"tenant_id": tenant, "at": stamp, "source": source, "kinds": ",".join(kinds) if last else "ilk",
               "env": (env or None), "digest": dig, "note": (str(note)[:2000] if note else None), "by": (by or "sistem")[:120],
               "model_since": since or stamp, **snap}
        vid = c.execute(VERSIONS.insert().values(**row)).inserted_primary_key[0]
    return version_view({**row, "id": vid})


def model_label(model_since: Any) -> str:
    d = _aware(model_since) if isinstance(model_since, datetime) else _parse_dt(model_since) if model_since else None
    return f"Zeki AI modeli, sürüm {d.date().isoformat()}" if d else "Zeki AI modeli"


def version_view(r: Any) -> dict[str, Any]:
    kinds = [k for k in str(r["kinds"] or "").split(",") if k]
    return {
        "id": r["id"], "at": _iso(r["at"]), "source": r["source"], "sourceLabel": SOURCES.get(r["source"], r["source"]),
        "kinds": kinds, "kindLabels": [KIND_LABELS.get(k, "İlk kayıt" if k == "ilk" else k) for k in kinds],
        "env": r["env"], "codeSha": r["code_sha"], "catalogVersion": r["catalog_version"],
        "catalogCertified": r["catalog_certified"], "knowledgeDigest": (r["knowledge_digest"] or "")[:12] or None,
        "rulesDigest": (r["rules_digest"] or "")[:12] or None, "languageDigest": (r["language_digest"] or "")[:12] or None,
        "promptDigest": (r["prompt_digest"] or "")[:12] or None,
        # Ekrana giden: model adı değil, «Zeki AI modeli, sürüm <ilk görüldüğü gün>» ve ayar özeti.
        "model": model_label(r["model_since"]), "modelDigest": (r["model_digest"] or "")[:12] or None,
        "digest": (r["digest"] or "")[:12], "note": r["note"], "by": r["by"],
    }


def get_version(engine: sa.engine.Engine, tenant: str, vid: Optional[int]) -> Optional[dict[str, Any]]:
    if not vid:
        return None
    with engine.connect() as c:
        r = c.execute(sa.select(VERSIONS).where(VERSIONS.c.tenant_id == tenant, VERSIONS.c.id == vid)).mappings().first()
    return version_view(r) if r else None


def list_versions(engine: sa.engine.Engine, tenant: str, *, page: int = 0, size: int = 50) -> dict[str, Any]:
    size = max(1, min(int(size or 50), 200))
    page = max(0, int(page or 0))
    with engine.connect() as c:
        total = c.execute(sa.select(sa.func.count()).select_from(VERSIONS).where(VERSIONS.c.tenant_id == tenant)).scalar() or 0
        rows = c.execute(sa.select(VERSIONS).where(VERSIONS.c.tenant_id == tenant).order_by(VERSIONS.c.id.desc())
                         .limit(size).offset(page * size)).mappings().all()
    return {"items": [version_view(r) for r in rows], "total": int(total), "page": page, "size": size}


def versions_between(engine: sa.engine.Engine, tenant: str, start: Optional[datetime], end: Optional[datetime],
                     *, sources: tuple[str, ...] = ("kurulum", "elle")) -> list[dict[str, Any]]:
    if not start or not end:
        return []
    with engine.connect() as c:
        rows = c.execute(sa.select(VERSIONS).where(
            VERSIONS.c.tenant_id == tenant, VERSIONS.c.source.in_(sources),
            VERSIONS.c.at >= start, VERSIONS.c.at <= end).order_by(VERSIONS.c.at)).mappings().all()
    return [version_view(r) for r in rows]


# ------------------------------------------------------------------ koşular


def _run_row(c, tenant: str, run_id: str) -> Any:
    r = c.execute(sa.select(RUNS).where(RUNS.c.tenant_id == tenant, RUNS.c.id == run_id)).mappings().first()
    if not r:
        raise QualityError("Koşu bulunamadı.", 404)
    return r


def request_run(engine: sa.engine.Engine, tenant: str, suite: str, user: str, *, label: str = "") -> dict[str, Any]:
    """Ekrandan koşu isteği: «sırada» satırı açılır; zamanlayıcı betiği (`model-quality-run.sh`) alır ve koşturur."""
    if suite not in STARTABLE:
        raise QualityError(f"Ekrandan yalnız {', '.join(SUITES[s] for s in STARTABLE)} başlatılır.")
    with engine.begin() as c:
        busy = c.execute(sa.select(RUNS.c.id).where(RUNS.c.tenant_id == tenant, RUNS.c.suite == suite,
                                                    RUNS.c.status.in_(("sirada", "calisiyor")))).first()
        if busy:
            raise QualityError(f"{SUITES[suite]} zaten sırada ya da çalışıyor; bitince yeniden isteyin.", 409)
        rid = _new_id()
        c.execute(RUNS.insert().values(id=rid, tenant_id=tenant, suite=suite, label=label or "", status="sirada",
                                       requested_by=user, requested_at=_now(), metrics_json="{}",
                                       installs_in_window_json="[]", total=0, broken=0, fixed=0))
        r = _run_row(c, tenant, rid)
    return run_view(r)


def claim_due(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    """Zamanlayıcı: sıradaki istekleri «çalışıyor»a alır ve döner. Aynı istek iki kez verilmez."""
    out = []
    with engine.begin() as c:
        rows = c.execute(sa.select(RUNS).where(RUNS.c.tenant_id == tenant, RUNS.c.status == "sirada")
                         .order_by(RUNS.c.requested_at)).mappings().all()
        for r in rows:
            n = c.execute(RUNS.update().where(RUNS.c.id == r["id"], RUNS.c.status == "sirada")
                          .values(status="calisiyor", started_at=_now())).rowcount
            if n:
                out.append({"id": r["id"], "suite": r["suite"], "label": r["label"], "requestedBy": r["requested_by"]})
    return out


def expire_stale(engine: sa.engine.Engine, tenant: str, hours: float) -> int:
    """Rapor getirmeyen «çalışıyor» koşusu (betik düştü) belirtilen süreden sonra «hata» olur."""
    cutoff = _now() - timedelta(hours=max(0.5, float(hours)))
    with engine.begin() as c:
        return c.execute(RUNS.update().where(RUNS.c.tenant_id == tenant, RUNS.c.status == "calisiyor",
                                             RUNS.c.started_at < cutoff)
                         .values(status="hata", finished_at=_now(),
                                 error=f"{hours:g} saat içinde rapor gelmedi; betik yarıda kalmış olabilir.")).rowcount


def fail_run(engine: sa.engine.Engine, tenant: str, run_id: str, message: str) -> dict[str, Any]:
    with engine.begin() as c:
        _run_row(c, tenant, run_id)
        c.execute(RUNS.update().where(RUNS.c.id == run_id).values(status="hata", finished_at=_now(), error=message[:2000]))
        return run_view(_run_row(c, tenant, run_id))


_OK = ("saglam", "veri")


def compare_cases(before: dict[str, str], after: dict[str, str]) -> tuple[list[str], list[str]]:
    """(bozulan, düzelen) vaka kimlikleri. Bozulan: önceki koşuda sağlamdı, şimdi sağlam/veri değil.
    Önceki koşuda olmayan vaka karşılaştırılmaz."""
    broken = sorted(k for k, s in after.items() if before.get(k) == "saglam" and s not in _OK)
    fixed = sorted(k for k, s in after.items() if k in before and before[k] not in _OK and s == "saglam")
    return broken, fixed


def _clean_case(raw: Any, i: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise QualityError(f"{i + 1}. vaka bir nesne olmalı.")
    cid = str(raw.get("id") or "").strip()[:80]
    if not cid:
        raise QualityError(f"{i + 1}. vakanın kimliği yok.")
    status = str(raw.get("status") or "").strip().lower()
    if status not in CASE_STATUSES:
        raise QualityError(f"{cid}: durum {', '.join(CASE_STATUSES)} olmalı.")
    detail = raw.get("detail") or []
    if not isinstance(detail, list):
        detail = [str(detail)]
    try:
        n = int(raw["n"]) if raw.get("n") is not None else None
    except (TypeError, ValueError):
        n = None
    return {"id": cid, "n": n, "question": str(raw.get("question") or "")[:4000], "status": status,
            "sql": (str(raw.get("sql"))[:20000] if raw.get("sql") else None),
            "resultDigest": (str(raw.get("resultDigest"))[:64] if raw.get("resultDigest") else None),
            "expectedDigest": (str(raw.get("expectedDigest"))[:64] if raw.get("expectedDigest") else None),
            "detail": [str(x)[:2000] for x in detail],
            "dropCodes": [str(x) for x in (raw.get("dropCodes") or []) if isinstance(x, str)],
            "unresolved": [str(x) for x in (raw.get("unresolved") or []) if isinstance(x, str)],
            "answerType": str(raw.get("answerType") or "")[:40],
            "note": (str(raw.get("note"))[:2000] if raw.get("note") else None)}


def ingest_report(engine: sa.engine.Engine, tenant: str, body: dict[str, Any], *, version: Optional[dict[str, Any]],
                  model_ref: Optional[str], env: Optional[str], by: str,
                  releases_between=None) -> dict[str, Any]:
    """Kapı betiğinin raporunu yazar. `version`: köprünün rapor anındaki sürüm satırı (record_version'dan).
    `releases_between(start, end)`: M48 kurulum kaydını okuyan işlev (yoksa None)."""
    suite = str(body.get("suite") or "").strip()
    if suite not in SUITES:
        raise QualityError(f"Takım {', '.join(SUITES)} olmalı.")
    label = str(body.get("label") or "").strip()[:200]
    raw_cases = body.get("cases")
    if not isinstance(raw_cases, list):
        raise QualityError("Vaka listesi (cases) gerekli.")
    cases = [_clean_case(x, i) for i, x in enumerate(raw_cases)]
    if len({c["id"] for c in cases}) != len(cases):
        raise QualityError("Aynı vaka kimliği iki kez geldi.")
    started = _parse_dt(body.get("startedAt"))
    finished = _parse_dt(body.get("finishedAt")) or _now()
    metrics = body.get("metrics") if isinstance(body.get("metrics"), dict) else {}
    state = body.get("state") if isinstance(body.get("state"), dict) else {}
    request_id = str(body.get("requestId") or "").strip() or None
    classes = load_classes(engine)
    tally: dict[str, int] = {}
    for cs in cases:
        tally[cs["status"]] = tally.get(cs["status"], 0) + 1
        cs["klass"] = None if cs["status"] == "saglam" else classify(evidence_from_case(cs), classes)
    # Okumalar yazma işleminden önce (ayrı bağlantı açan okumalar işlemin içine girmesin).
    if request_id:
        with engine.connect() as c:
            req = _run_row(c, tenant, request_id)
        if req["status"] not in ("sirada", "calisiyor"):
            raise QualityError("Bu koşu isteği zaten kapanmış.", 409)
        if req["suite"] != suite:
            raise QualityError("Rapor, istenen takımla aynı değil.", 409)
        run_id = request_id
        started = started or _aware(req["started_at"]) or _aware(req["requested_at"])
    else:
        run_id = _new_id()
    installs = versions_between(engine, tenant, started, finished)
    if releases_between is not None:
        try:
            installs += releases_between(started, finished) or []
        except Exception as e:  # noqa: BLE001
            log.warning("model_quality: kurulum kaydı okunamadı: %s", e)
    with engine.begin() as c:
        if request_id:
            # Aynı isteğe iki rapor yarışırsa ikincisi kapanmış satırı görür.
            if c.execute(sa.select(RUNS.c.status).where(RUNS.c.id == run_id)).scalar() not in ("sirada", "calisiyor"):
                raise QualityError("Bu koşu isteği zaten kapanmış.", 409)
        prev = c.execute(sa.select(RUNS).where(
            RUNS.c.tenant_id == tenant, RUNS.c.suite == suite, RUNS.c.label == label, RUNS.c.status == "bitti",
            RUNS.c.id != run_id).order_by(RUNS.c.finished_at.desc()).limit(1)).mappings().first()
        before: dict[str, str] = {}
        if prev:
            before = {r[0]: r[1] for r in c.execute(sa.select(CASES.c.case_id, CASES.c.status)
                                                    .where(CASES.c.run_id == prev["id"]))}
        after = {cs["id"]: cs["status"] for cs in cases}
        if prev:
            broken, fixed = compare_cases(before, after)
        else:
            # Önceki koşu yok: temel çizgi betiğin kendi dosyasıdır; bozuk sayılan vakalar bozulan sayılır.
            broken, fixed = sorted(k for k, s in after.items() if s == "bozuk"), []
        start_state, end_state = state.get("start") or {}, state.get("end") or {}
        moved = sorted(k for k in set(start_state) | set(end_state)
                       if start_state.get(k) not in (None, "") and start_state.get(k) != end_state.get(k))
        if moved:
            installs.append({"kind": "durum", "at": None, "label": "Koşu sırasında değişti: " + ", ".join(moved),
                             "start": {k: start_state.get(k) for k in moved}, "end": {k: end_state.get(k) for k in moved}})
        metrics = {**metrics, "tally": tally, "state": state}
        vals = dict(tenant_id=tenant, suite=suite, label=label, status="bitti", started_at=started, finished_at=finished,
                    started_by=str(body.get("host") or by)[:120], version_id=(version or {}).get("id"),
                    code_sha=(str(body.get("codeSha"))[:64] if body.get("codeSha") else (version or {}).get("codeSha")),
                    catalog_version=(version or {}).get("catalogVersion"),
                    rules_digest=(version or {}).get("rulesDigest"), model_ref=(model_ref or None), env=env,
                    metrics_json=_dumps(metrics), baseline_run_id=(prev["id"] if prev else None), total=len(cases),
                    broken=len(broken), fixed=len(fixed), installs_in_window_json=_dumps(installs),
                    note=(str(body.get("note"))[:2000] if body.get("note") else None), error=None)
        if request_id:
            c.execute(RUNS.update().where(RUNS.c.id == run_id).values(**vals))
        else:
            c.execute(RUNS.insert().values(id=run_id, requested_by=None, requested_at=None, **vals))
        c.execute(CASES.delete().where(CASES.c.run_id == run_id))
        if cases:
            c.execute(CASES.insert(), [
                {"run_id": run_id, "case_id": cs["id"], "n": cs["n"], "question": cs["question"], "status": cs["status"],
                 "klass": cs["klass"], "sql_text": cs["sql"], "result_digest": cs["resultDigest"],
                 "expected_digest": cs["expectedDigest"], "detail_json": _dumps(cs["detail"]), "note": cs["note"]}
                for cs in cases])
        r = _run_row(c, tenant, run_id)
    out = run_view(r)
    out["brokenIds"], out["fixedIds"] = broken, fixed
    return out


def run_view(r: Any) -> dict[str, Any]:
    metrics = _loads(r["metrics_json"], {})
    installs = _loads(r["installs_in_window_json"], [])
    started, finished = _aware(r["started_at"]), _aware(r["finished_at"])
    return {
        "id": r["id"], "suite": r["suite"], "suiteLabel": SUITES.get(r["suite"], r["suite"]), "label": r["label"],
        "status": r["status"], "statusLabel": RUN_STATUSES.get(r["status"], r["status"]),
        "requestedBy": r["requested_by"], "requestedAt": _iso(r["requested_at"]),
        "startedAt": _iso(started), "finishedAt": _iso(finished),
        "durationSec": (round((finished - started).total_seconds()) if started and finished else None),
        "startedBy": r["started_by"], "versionId": r["version_id"], "codeSha": r["code_sha"],
        "catalogVersion": r["catalog_version"], "env": r["env"], "metrics": metrics,
        "tally": metrics.get("tally") or {}, "baselineRunId": r["baseline_run_id"], "total": r["total"] or 0,
        "broken": r["broken"] or 0, "fixed": r["fixed"] or 0, "installsInWindow": installs,
        "polluted": bool(installs), "note": r["note"], "error": r["error"],
    }


def list_runs(engine: sa.engine.Engine, tenant: str, *, suite: str = "", page: int = 0, size: int = 50) -> dict[str, Any]:
    size = max(1, min(int(size or 50), 200))
    page = max(0, int(page or 0))
    conds = [RUNS.c.tenant_id == tenant] + ([RUNS.c.suite == suite] if suite else [])
    order = sa.func.coalesce(RUNS.c.finished_at, RUNS.c.started_at, RUNS.c.requested_at)
    with engine.connect() as c:
        total = c.execute(sa.select(sa.func.count()).select_from(RUNS).where(*conds)).scalar() or 0
        rows = c.execute(sa.select(RUNS).where(*conds).order_by(order.desc()).limit(size).offset(page * size)).mappings().all()
    return {"items": [run_view(r) for r in rows], "total": int(total), "page": page, "size": size}


def get_run(engine: sa.engine.Engine, tenant: str, run_id: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = _run_row(c, tenant, run_id)
    out = run_view(r)
    out["version"] = get_version(engine, tenant, r["version_id"])
    if r["baseline_run_id"]:
        with engine.connect() as c:
            b = c.execute(sa.select(RUNS).where(RUNS.c.id == r["baseline_run_id"])).mappings().first()
        out["baseline"] = run_view(b) if b else None
        out["baselineVersion"] = get_version(engine, tenant, b["version_id"]) if b else None
    else:
        out["baseline"], out["baselineVersion"] = None, None
    return out


def case_view(r: Any) -> dict[str, Any]:
    return {"id": r["case_id"], "n": r["n"], "question": r["question"], "status": r["status"],
            "statusLabel": CASE_STATUSES.get(r["status"], r["status"]), "klass": r["klass"], "sql": r["sql_text"],
            "resultDigest": r["result_digest"], "expectedDigest": r["expected_digest"],
            "detail": _loads(r["detail_json"], []), "note": r["note"]}


def run_cases(engine: sa.engine.Engine, tenant: str, run_id: str, *, status: str = "", change: str = "",
              page: int = 0, size: int = 100) -> dict[str, Any]:
    """Koşunun vakaları. `change=bozulan|duzelen` önceki koşuyla karşılaştırır ve her vakanın «önce» hâlini ekler."""
    size = max(1, min(int(size or 100), 500))
    page = max(0, int(page or 0))
    with engine.connect() as c:
        r = _run_row(c, tenant, run_id)
        rows = c.execute(sa.select(CASES).where(CASES.c.run_id == run_id)
                         .order_by(sa.func.coalesce(CASES.c.n, 0), CASES.c.case_id)).mappings().all()
        before_rows = {}
        if r["baseline_run_id"]:
            before_rows = {b["case_id"]: b for b in c.execute(
                sa.select(CASES).where(CASES.c.run_id == r["baseline_run_id"])).mappings().all()}
    after = {x["case_id"]: x["status"] for x in rows}
    before = {k: v["status"] for k, v in before_rows.items()}
    if r["baseline_run_id"]:
        broken, fixed = compare_cases(before, after)
    else:
        broken, fixed = [k for k, s in after.items() if s == "bozuk"], []
    counts = {"bozulan": len(broken), "duzelen": len(fixed)}
    for s in CASE_STATUSES:
        counts[s] = sum(1 for v in after.values() if v == s)
    picked = rows
    if change == "bozulan":
        picked = [x for x in rows if x["case_id"] in set(broken)]
    elif change == "duzelen":
        picked = [x for x in rows if x["case_id"] in set(fixed)]
    if status:
        picked = [x for x in picked if x["status"] == status]
    total = len(picked)
    items = []
    for x in picked[page * size:(page + 1) * size]:
        v = case_view(x)
        b = before_rows.get(x["case_id"])
        v["before"] = case_view(b) if b else None
        v["change"] = "bozulan" if x["case_id"] in broken else "duzelen" if x["case_id"] in fixed else None
        items.append(v)
    return {"items": items, "total": total, "page": page, "size": size, "counts": counts,
            "baselineRunId": r["baseline_run_id"]}


# ------------------------------------------------------------------ geri bildirim


def feedback_message(verdict: str) -> str:
    return {"dogru": "Teşekkürler, kaydedildi.",
            "kismen": "Teşekkürler; not model ekibine iletildi, incelemeye alındı.",
            "yanlis": "İncelemeye alındı; model ekibi bu cevaba bakacak."}[verdict]


def record_feedback(engine: sa.engine.Engine, tenant: str, query_row: dict[str, Any], user: str, verdict: str,
                    comment: Optional[str], *, is_admin: bool = False) -> dict[str, Any]:
    """Kişinin cevaba verdiği hüküm. Aynı kişi aynı cevaba ikinci kez basarsa hüküm güncellenir (kuyruk durumu
    yenilenir). Başkasının sorduğu cevap (yönetici dışında) işaretlenmez. `sl_query_log.validated` de güncellenir."""
    from semantic_layer.store import schema as S

    verdict = str(verdict or "").strip().lower()
    if verdict not in VERDICTS:
        raise QualityError("Hüküm Doğru, Kısmen ya da Yanlış olmalı.")
    user = (user or "").strip().lower()
    if not user:
        raise QualityError("Oturum gerekli.", 401)
    owner = str(query_row.get("username") or "").strip().lower()
    if owner and owner != user and not is_admin:
        raise QualityError("Yalnız kendi sorduğunuz cevabı işaretleyebilirsiniz.", 403)
    text = (str(comment or "").strip()[:2000] or None)
    now = _now()
    with engine.begin() as c:
        existing = c.execute(sa.select(FEEDBACK).where(
            FEEDBACK.c.tenant_id == tenant, FEEDBACK.c.query_id == query_row["id"], FEEDBACK.c.username == user)).mappings().first()
        if existing:
            fid = existing["id"]
            c.execute(FEEDBACK.update().where(FEEDBACK.c.id == fid).values(
                verdict=verdict, comment=text, at=now, triage_state="yeni" if verdict != "dogru" else existing["triage_state"]))
        else:
            fid = _new_id()
            c.execute(FEEDBACK.insert().values(id=fid, tenant_id=tenant, query_id=query_row["id"], username=user,
                                               verdict=verdict, comment=text, at=now,
                                               triage_state=("kapandi" if verdict == "dogru" else "yeni")))
        validated = {"dogru": True, "yanlis": False}.get(verdict)
        c.execute(S.sl_query_log.update().where(S.sl_query_log.c.id == query_row["id"]).values(validated=validated))
    return {"ok": True, "id": fid, "queryId": query_row["id"], "verdict": verdict, "verdictLabel": VERDICTS[verdict],
            "comment": text, "validated": validated, "message": feedback_message(verdict)}


def my_feedback(engine: sa.engine.Engine, tenant: str, query_id: str, user: str) -> Optional[dict[str, Any]]:
    with engine.connect() as c:
        r = c.execute(sa.select(FEEDBACK).where(FEEDBACK.c.tenant_id == tenant, FEEDBACK.c.query_id == query_id,
                                                FEEDBACK.c.username == (user or "").lower())).mappings().first()
    if not r:
        return None
    return {"id": r["id"], "verdict": r["verdict"], "verdictLabel": VERDICTS.get(r["verdict"]), "comment": r["comment"],
            "at": _iso(r["at"]), "triageState": r["triage_state"], "triageLabel": TRIAGE.get(r["triage_state"])}


def triage_feedback(engine: sa.engine.Engine, tenant: str, fid: str, body: dict[str, Any], user: str) -> dict[str, Any]:
    vals: dict[str, Any] = {}
    if "klass" in body:
        klass = str(body.get("klass") or "").strip()
        if klass:
            known = {k["klass"] for k in load_classes(engine, active_only=False)} | {UNCLASSIFIED}
            if klass not in known:
                raise QualityError("Bilinmeyen sınıf.")
        vals["klass"] = klass or None
    if "triageState" in body:
        st = str(body.get("triageState") or "").strip()
        if st not in TRIAGE:
            raise QualityError(f"Durum {', '.join(TRIAGE)} olmalı.")
        vals["triage_state"] = st
    elif vals.get("klass"):
        vals["triage_state"] = "siniflandi"
    if "note" in body:
        vals["handle_note"] = str(body.get("note") or "").strip()[:2000] or None
    if not vals:
        raise QualityError("Değişecek alan yok.")
    vals.update(handled_by=user, handled_at=_now())
    with engine.begin() as c:
        n = c.execute(FEEDBACK.update().where(FEEDBACK.c.tenant_id == tenant, FEEDBACK.c.id == fid).values(**vals)).rowcount
        if not n:
            raise QualityError("Geri bildirim bulunamadı.", 404)
        r = c.execute(sa.select(FEEDBACK).where(FEEDBACK.c.id == fid)).mappings().first()
    return feedback_row_view(r, None, None)


def feedback_row_view(r: Any, q: Optional[dict[str, Any]], auto_klass: Optional[str]) -> dict[str, Any]:
    out = {"id": r["id"], "queryId": r["query_id"], "username": r["username"], "verdict": r["verdict"],
           "verdictLabel": VERDICTS.get(r["verdict"]), "comment": r["comment"], "at": _iso(r["at"]),
           "triageState": r["triage_state"], "triageLabel": TRIAGE.get(r["triage_state"]),
           "klass": r["klass"], "klassSource": "insan" if r["klass"] else ("kural" if auto_klass else None),
           "effectiveKlass": r["klass"] or auto_klass, "handledBy": r["handled_by"], "handledAt": _iso(r["handled_at"]),
           "handleNote": r["handle_note"]}
    if q is not None:
        out["query"] = q
    return out


# ------------------------------------------------------------------ durum (bildirimlerin son gönderimi)


def state_get(engine: sa.engine.Engine, tenant: str, key: str) -> Optional[str]:
    with engine.connect() as c:
        return c.execute(sa.select(STATE.c.value).where(STATE.c.tenant_id == tenant, STATE.c.key == key)).scalar()


def state_set(engine: sa.engine.Engine, tenant: str, key: str, value: str) -> None:
    with engine.begin() as c:
        n = c.execute(STATE.update().where(STATE.c.tenant_id == tenant, STATE.c.key == key)
                      .values(value=value, updated_at=_now())).rowcount
        if not n:
            c.execute(STATE.insert().values(tenant_id=tenant, key=key, value=value, updated_at=_now()))


# ------------------------------------------------------------------ karne ve sınıf sayımı (saf hesap)


def week_buckets(now: datetime, weeks: int = 4) -> list[tuple[datetime, datetime]]:
    """Son `weeks` hafta, eskiden yeniye; her biri [başlangıç, bitiş)."""
    end = now
    out = []
    for i in range(weeks, 0, -1):
        out.append((end - timedelta(days=7 * i), end - timedelta(days=7 * (i - 1))))
    return out


def _bucket(buckets: list[tuple[datetime, datetime]], at: Optional[datetime]) -> Optional[int]:
    at = _aware(at)
    if at is None:
        return None
    for i, (a, b) in enumerate(buckets):
        if a <= at < b or (i == len(buckets) - 1 and at >= a):   # son hafta şimdiye kadar açık uçlu
            return i
    return None


def _ratio(n: int, d: int) -> Optional[float]:
    return round(n / d, 4) if d else None


def bi_row(log_rows: list[dict[str, Any]], feedback_rows: list[dict[str, Any]], last_runs: dict[str, Optional[dict]],
           *, now: datetime, since: datetime) -> dict[str, Any]:
    """Karnenin «Soru-cevap» satırı. `log_rows`: pencere + 4 haftalık eğilim için sl_query_log hafif satırları
    (answer_type, executed, row_count, error, latency_ms, created_at). `feedback_rows`: (verdict, at).
    `last_runs`: suite → son bitmiş koşu görünümü."""
    buckets = week_buckets(now)
    in_window = [r for r in log_rows if (_aware(r["created_at"]) or now) >= since and r.get("answer_type") not in IGNORED_TYPES]
    total = len(in_window)
    answered = sum(1 for r in in_window if r.get("answer_type") == "TEXT_TO_SQL" and r.get("executed") and not r.get("error"))
    clar = sum(1 for r in in_window if r.get("answer_type") == "CLARIFICATION")
    denied = sum(1 for r in in_window if r.get("answer_type") in NON_ANSWER_TYPES and r.get("answer_type") not in
                 ("CLARIFICATION", "NOT_PERMITTED", "DATA_SOURCE_UNAVAILABLE"))
    by_type: dict[str, int] = {}
    for r in in_window:
        k = r.get("answer_type") or "—"
        by_type[k] = by_type.get(k, 0) + 1
    lat = sorted(int(r["latency_ms"]) for r in in_window if r.get("latency_ms") is not None)
    fb_window = [f for f in feedback_rows if (_aware(f["at"]) or now) >= since]
    fb = {v: sum(1 for f in fb_window if f["verdict"] == v) for v in VERDICTS}
    trend = []
    for i, (a, b) in enumerate(buckets):
        wk = [r for r in log_rows if _bucket(buckets, r.get("created_at")) == i and r.get("answer_type") not in IGNORED_TYPES]
        ok = sum(1 for r in wk if r.get("answer_type") == "TEXT_TO_SQL" and r.get("executed") and not r.get("error"))
        wrong = sum(1 for f in feedback_rows if f["verdict"] == "yanlis" and _bucket(buckets, f.get("at")) == i)
        trend.append({"from": _iso(a), "to": _iso(b), "questions": len(wk), "answeredRate": _ratio(ok, len(wk)), "wrong": wrong})
    ans = last_runs.get("answer")
    res = last_runs.get("resolver")
    metrics = [
        {"key": "questions", "label": "Soru", "value": total},
        {"key": "answeredRate", "label": "Cevaplanan", "value": _ratio(answered, total), "kind": "ratio"},
        {"key": "denyRate", "label": "Ret", "value": _ratio(denied, total), "kind": "ratio",
         "help": "Cevap yerine ret (netleştirme, yetki ve bağlantı hariç)"},
        {"key": "clarifyRate", "label": "Netleştirme", "value": _ratio(clar, total), "kind": "ratio"},
        {"key": "wrong", "label": "«Yanlış» bildirimi", "value": fb["yanlis"]},
        {"key": "partial", "label": "«Kısmen» bildirimi", "value": fb["kismen"]},
        {"key": "correct", "label": "«Doğru» bildirimi", "value": fb["dogru"]},
        {"key": "feedbackRate", "label": "Geri bildirim oranı", "value": _ratio(len(fb_window), answered), "kind": "ratio",
         "help": "İşaretlenen cevap ÷ cevaplanan soru"},
        {"key": "latencyP50", "label": "Ortanca süre", "value": (lat[len(lat) // 2] if lat else None), "kind": "ms"},
    ]
    primary = None
    if ans:
        t = ans.get("tally") or {}
        ok = int(t.get("saglam", 0))
        denom = int(ans.get("total") or 0) - int(t.get("veri", 0))
        primary = {"label": "Doğrulanmış sorularda sağlam", "value": _ratio(ok, denom), "kind": "ratio",
                   "detail": f"{ok}/{denom}", "at": ans.get("finishedAt"), "runId": ans.get("id"),
                   "broken": ans.get("broken"), "fixed": ans.get("fixed")}
    reading = None
    if res:
        t = res.get("tally") or {}
        reading = {"label": "Okuması değişen soru", "value": int(t.get("bozuk", 0)), "total": res.get("total"),
                   "at": res.get("finishedAt"), "runId": res.get("id")}
    measured = total > 0 or ans is not None or res is not None
    stamps = [_aware(r["created_at"]) for r in in_window if r.get("created_at")]
    stamps += [_parse_dt(x.get("finishedAt")) for x in (ans, res) if x and x.get("finishedAt")]
    last = _iso(max((s for s in stamps if s), default=None))
    return {"id": "bi", "label": "Soru-cevap (Zeki AI)", "page": "genel-bakis", "measured": measured,
            "primary": primary, "reading": reading, "metrics": metrics, "byType": by_type, "trend": trend,
            "lastMeasured": last, "note": None if measured else "ölçülmedi"}


def seo_row(stats: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not stats or not (stats.get("approved") or stats.get("rejected")):
        return {"id": "seo", "label": "SEO önerileri", "page": "seo-urun", "measured": False, "metrics": [],
                "trend": [], "note": "ölçülmedi" if stats is not None else "SEO modülü bu ortamda kurulu değil"}
    ap, rj = int(stats["approved"]), int(stats["rejected"])
    un, known = int(stats.get("unedited") or 0), int(stats.get("editKnown") or 0)
    return {"id": "seo", "label": "SEO önerileri", "page": "seo-urun", "measured": True,
            "primary": {"label": "Değiştirmeden onay", "value": _ratio(un, known), "kind": "ratio",
                        "detail": f"{un}/{known}" if known else "düzenleme bilgisi bu sürümden itibaren tutuluyor"},
            "metrics": [{"key": "approveRate", "label": "Onay oranı", "value": _ratio(ap, ap + rj), "kind": "ratio"},
                        {"key": "approved", "label": "Onaylanan", "value": ap},
                        {"key": "rejected", "label": "Reddedilen", "value": rj},
                        {"key": "pending", "label": "Bekleyen", "value": int(stats.get("pending") or 0)}],
            "trend": stats.get("trend") or [], "lastMeasured": stats.get("last"), "note": None}


def translation_row(stats: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not stats or not stats.get("segments"):
        return {"id": "ceviri", "label": "Çeviri taslağı", "page": "ceviri", "measured": False, "metrics": [],
                "trend": [], "note": "ölçülmedi" if stats is not None else "Çeviri modülü bu ortamda kurulu değil"}
    seg, changed = int(stats["segments"]), int(stats.get("changed") or 0)
    return {"id": "ceviri", "label": "Çeviri taslağı", "page": "ceviri", "measured": True,
            "primary": {"label": "Taslağı düzeltilen segment", "value": _ratio(changed, seg), "kind": "ratio",
                        "detail": f"{changed}/{seg}"},
            "metrics": [{"key": "editRate", "label": "Düzeltme miktarı", "value": stats.get("editRate"), "kind": "ratio",
                         "help": "Kelime ağırlıklı karakter farkı (taslak → onaylı metin)"},
                        {"key": "mqm", "label": "Kalite puanı", "value": stats.get("mqm"), "kind": "score",
                         "help": "(1 − ceza ÷ incelenen kelime) × 100; küçük 1, büyük 5, kritik 25"},
                        {"key": "reviewedWords", "label": "İncelenen kelime", "value": stats.get("reviewedWords")}],
            "trend": [], "lastMeasured": stats.get("last"), "note": None}


def redaction_row(stats: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not stats or not (stats.get("accepted") or stats.get("rejected")):
        return {"id": "redaksiyon", "label": "Redaksiyon önerileri", "page": "redaksiyon", "measured": False,
                "metrics": [], "trend": [], "note": "ölçülmedi" if stats is not None else "Redaksiyon bu ortamda kurulu değil"}
    ac, rj, mod = int(stats["accepted"]), int(stats["rejected"]), int(stats.get("modified") or 0)
    return {"id": "redaksiyon", "label": "Redaksiyon önerileri", "page": "redaksiyon", "measured": True,
            "primary": {"label": "Kabul oranı", "value": _ratio(ac, ac + rj), "kind": "ratio", "detail": f"{ac}/{ac + rj}"},
            "metrics": [{"key": "modified", "label": "Değiştirilerek kabul", "value": _ratio(mod, ac), "kind": "ratio"},
                        {"key": "pending", "label": "Bekleyen", "value": int(stats.get("pending") or 0)}],
            "trend": [], "lastMeasured": stats.get("last"), "note": None}


def unmeasured_row(rid: str, label: str, page: Optional[str], note: str) -> dict[str, Any]:
    return {"id": rid, "label": label, "page": page, "measured": False, "metrics": [], "trend": [], "note": note}


def class_board(items: list[dict[str, Any]], classes: list[dict[str, Any]], *, now: datetime,
                gate_cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Sınıf başına soru sayısı. `items`: {klass, at, source: log|geri-bildirim}; `gate_cases`: son koşuların
    sağlam olmayan vakaları ({klass, suite}). Eğilim son 4 hafta."""
    buckets = week_buckets(now)
    names = {k["klass"]: k for k in classes}
    rows: dict[str, dict[str, Any]] = {}

    def row(klass: str) -> dict[str, Any]:
        if klass not in rows:
            k = names.get(klass) or {"label": "Sınıflanamadı" if klass == UNCLASSIFIED else klass, "help": None,
                                     "countsAsError": True, "sort": 999}
            rows[klass] = {"klass": klass, "label": k["label"], "help": k.get("help"), "countsAsError": k["countsAsError"],
                           "sort": k.get("sort", 999), "questions": 0, "fromFeedback": 0, "gateCases": 0, "trend": [0] * len(buckets)}
        return rows[klass]

    for it in items:
        r = row(it["klass"] or UNCLASSIFIED)
        r["questions"] += 1
        if it.get("source") == "geri-bildirim":
            r["fromFeedback"] += 1
        b = _bucket(buckets, it.get("at"))
        if b is not None:
            r["trend"][b] += 1
    for cs in gate_cases:
        row(cs.get("klass") or UNCLASSIFIED)["gateCases"] += 1
    for k in classes:
        row(k["klass"])
    out = sorted(rows.values(), key=lambda r: (not r["countsAsError"], -r["questions"], r["sort"]))
    errors = sum(r["questions"] for r in out if r["countsAsError"])
    return {"items": out, "errorQuestions": errors, "weeks": [{"from": _iso(a), "to": _iso(b)} for a, b in buckets]}
