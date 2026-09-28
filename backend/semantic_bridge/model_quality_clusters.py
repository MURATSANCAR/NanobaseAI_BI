"""M50 Zeki AI kalitesi — başarısız soru kümeleri ve sınıf önerisi (öneri 20; docs/analiz/ai-firsatlari/README.md).

Bellek `fix-classes-not-questions`: soruyu değil sınıfı düzelt. «Hata sınıfları» ekranı kurallarla sınıflıyor; kurala
uymayanlar «sınıflanamadı»da birikiyor ve tek tek okunuyordu. Bu modül:

1. **Kümeler:** pencere içindeki başarısız sorular (`sl_query_log`: SQL'li cevap almayan, hatalı, boş dönen, kullanıcının
   Kısmen/Yanlış dediği — `model_quality_sources.classified_items` ile aynı küme; insanın sınıfladığı sorular hariç)
   önce aynı metinler birleştirilerek, sonra anlam gömmesiyle (sunucudaki gömme servisi, kitap benzerliğiyle aynı)
   kümelenir. Yöntem sıralı öncü kümeleme: en sık sorudan başlanır, soru mevcut bir kümenin öncüsüne
   `MODEL_QUALITY_CLUSTER_MIN_SIM` kadar benziyorsa ona girer, yoksa yeni küme açar. Deterministik; tek soruluk küme
   gösterilmez (ekranda «tekil» sayısı yazılır). Sorular gömmeye ve modele **maskelenerek** gider (`mask_personal`).
2. **Sınıf önerisi:** her küme için `QueuedLlm.choose` (LLM kapısı, modül «zeki-kalite», düşük öncelik): etkin hata
   sınıflarının adları + «Hiçbiri (yeni sınıf gerekir)»; olasılık ve marj kaydedilir, eşik altı «emin değil» yazılır.
   Model sayı üretmez; küme boyutu ve sınıf sayıları koddan.
3. **Onay insanda:** `ozellik:zeki-kalite.karar` sahibi kümeyi bir sınıfla onaylar (öneriyi ya da kendi seçtiğini) →
   kümedeki her soruya insan sınıfı yazılır (`semantic_mq_query_classes`); sınıf panosu bu sınıfı kuralın önünde sayar.
   Reddedilen küme kaydıyla kalır. Kural tablosu değişmez; yeni kural gerekiyorsa ekran kural düzenleyicisine yönlendirir.
"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import sqlalchemy as sa

from semantic_bridge import model_quality as MQ

log = logging.getLogger("semantic_bridge.model_quality_clusters")

_md = sa.MetaData()

CLUSTERS = sa.Table(
    "semantic_mq_clusters", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("run_id", sa.String(32), nullable=False, index=True),
    sa.Column("built_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("window_days", sa.Integer, nullable=False),
    sa.Column("size", sa.Integer, nullable=False),                 # küme içindeki soru kaydı sayısı (tekrarlar dahil)
    sa.Column("distinct_texts", sa.Integer, nullable=False),
    sa.Column("samples_json", sa.Text, nullable=False),            # maskeli örnek sorular (en sık önce)
    sa.Column("rule_classes_json", sa.Text, nullable=False),       # kuralın verdiği sınıfların sayımı
    sa.Column("suggested", sa.String(40)),                         # sınıf kodu ya da None («Hiçbiri»)
    sa.Column("suggested_label", sa.String(160)),
    sa.Column("probability", sa.Float),
    sa.Column("margin", sa.Float),
    sa.Column("method", sa.String(16)),                            # logprobs | text | none | yok (model yok)
    sa.Column("confident", sa.Boolean, nullable=False, default=False),
    sa.Column("status", sa.String(12), nullable=False),            # oneri | onaylandi | reddedildi
    sa.Column("decided_klass", sa.String(40)),
    sa.Column("decided_by", sa.String(120)),
    sa.Column("decided_at", sa.DateTime(timezone=True)),
    sa.Column("note", sa.Text),
)
MEMBERS = sa.Table(
    "semantic_mq_cluster_members", _md,
    sa.Column("cluster_id", sa.String(32), primary_key=True),
    sa.Column("query_id", sa.String(64), primary_key=True),
    sa.Column("rule_klass", sa.String(40)),
)
QUERY_CLASSES = sa.Table(
    "semantic_mq_query_classes", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("query_id", sa.String(64), primary_key=True),
    sa.Column("klass", sa.String(40), nullable=False),
    sa.Column("cluster_id", sa.String(32)),
    sa.Column("decided_by", sa.String(120), nullable=False),
    sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
)

NONE_CHOICE = "Hiçbiri (yeni sınıf gerekir)"
STATUS = {"oneri": "Öneri", "onaylandi": "Onaylandı", "reddedildi": "Reddedildi"}
_ready: set[int] = set()
_lock = threading.Lock()


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _ready.add(id(engine))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def settings(conf: Callable[..., str]) -> dict[str, float]:
    def f(key: str, default: float) -> float:
        try:
            return max(0.0, min(1.0, float(str(conf(key) or default).replace(",", "."))))
        except ValueError:
            return default

    return {"minSim": f("MODEL_QUALITY_CLUSTER_MIN_SIM", 0.82), "minProb": f("MODEL_QUALITY_CLUSTER_MIN_PROB", 0.70),
            "minMargin": f("MODEL_QUALITY_CLUSTER_MIN_MARGIN", 0.30)}


# ------------------------------------------------------------------ saf hesap (sınanır)


def norm_text(q: Any) -> str:
    return " ".join(MQ.fold(q).split())


def _unit(v: list[float]) -> list[float]:
    n = sum(x * x for x in v) ** 0.5
    return [x / n for x in v] if n > 0 else list(v)


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def leader_clusters(texts: list[str], weights: list[int], vecs: list[list[float]], min_sim: float) -> list[list[int]]:
    """Sıralı öncü kümeleme: ağırlığı (tekrar sayısı) büyük metin önce; her metin öncüsüne en çok benzeyen kümeye
    `min_sim` ve üstündeyse girer, değilse yeni küme açar. Dönen: metin sıraları listesi (kümeler büyükten küçüğe)."""
    order = sorted(range(len(texts)), key=lambda i: (-weights[i], texts[i]))
    units = [_unit(list(v)) for v in vecs]
    leaders: list[int] = []
    groups: list[list[int]] = []
    for i in order:
        best, best_s = None, min_sim
        for g, lead in enumerate(leaders):
            s = _dot(units[i], units[lead])
            if s >= best_s:
                best, best_s = g, s
        if best is None:
            leaders.append(i)
            groups.append([i])
        else:
            groups[best].append(i)
    groups.sort(key=lambda g: (-sum(weights[i] for i in g), texts[g[0]]))
    return groups


def class_prompt(samples: list[str], classes: list[dict[str, Any]]) -> tuple[str, list[str]]:
    lines = [f"- {k['label']}: {k.get('help') or ''}".rstrip(": ") for k in classes]
    prompt = ("Zeki AI'ın cevaplayamadığı ya da yanlış cevapladığı soruların bir kümesi aşağıda. Kümedeki soruların ortak "
              "hata nedenine en uygun sınıf hangisi?\n\nSınıflar:\n" + "\n".join(lines)
              + f"\n- {NONE_CHOICE}: sınıfların hiçbiri uymuyor\n\nKümedeki sorular:\n" + "\n".join(f"- {s}" for s in samples))
    return prompt, [k["label"] for k in classes] + [NONE_CHOICE]


# ------------------------------------------------------------------ kurma


def build(engine: sa.engine.Engine, tenant: str, ds: str, *, days: int, embed: Callable[[list[str]], list[list[float]]],
          choose: Optional[Callable[[str, list[str]], Any]], conf: Callable[..., str],
          items: Optional[list[dict[str, Any]]] = None, sample_n: int = 8) -> dict[str, Any]:
    """Kümeleri kurar, her kümeye sınıf önerisi ister, eski «öneri» kümelerini yenileriyle değiştirir (onaylanan ve
    reddedilen kümeler kayıt olarak kalır)."""
    from semantic_bridge import model_quality_sources as src
    from semantic_bridge import zeki_text as Z

    ensure(engine)
    st = settings(conf)
    now, since = src.window(days)
    if items is None:
        items = src.classified_items(engine, tenant, ds, since)
    with engine.connect() as c:
        human = {r[0] for r in c.execute(sa.select(QUERY_CLASSES.c.query_id).where(QUERY_CLASSES.c.tenant_id == tenant))}
    todo = [i for i in items if i.get("question") and i["queryId"] not in human and i.get("klassSource", "kural") == "kural"]
    by_text: dict[str, list[dict[str, Any]]] = {}
    shown: dict[str, str] = {}
    for it in todo:
        k = norm_text(it["question"])
        if not k:
            continue
        by_text.setdefault(k, []).append(it)
        shown.setdefault(k, Z.mask_personal(it["question"])[:400])
    texts = list(by_text)
    if not texts:
        return {"clusters": 0, "questions": 0, "singletons": 0, "note": "Pencerede kümelenecek başarısız soru yok."}
    vecs: list[list[float]] = []
    for i in range(0, len(texts), 64):
        vecs.extend(embed([shown[t] for t in texts[i:i + 64]]))
    if len(vecs) != len(texts):
        raise MQ.QualityError("Gömme servisi eksik vektör döndürdü.", 502)
    weights = [len(by_text[t]) for t in texts]
    groups = leader_clusters(texts, weights, vecs, st["minSim"])
    classes = [k for k in MQ.load_classes(engine) if k.get("active", True)]
    code_of = {k["label"]: k["klass"] for k in classes}
    run_id = uuid.uuid4().hex
    rows, singletons, asked, stopped = [], 0, 0, None
    for g in groups:
        members = [it for i in g for it in by_text[texts[i]]]
        if len(members) < 2:
            singletons += 1
            continue
        samples = [shown[texts[i]] for i in g][:sample_n]
        rule = Counter(m.get("klass") or MQ.UNCLASSIFIED for m in members)
        sug = {"suggested": None, "suggested_label": None, "probability": None, "margin": None, "method": "yok", "confident": False}
        if choose is not None and classes and stopped is None:
            prompt, labels = class_prompt(samples, classes)
            try:
                ch = choose(prompt, labels)
                asked += 1
                ok = bool(ch.choice) and ch.confident(st["minProb"], st["minMargin"])
                sug = {"suggested": code_of.get(ch.choice) if ch.choice else None,
                       "suggested_label": ch.choice, "probability": ch.probability, "margin": ch.margin,
                       "method": ch.method, "confident": ok}
            except Exception as e:  # noqa: BLE001 — model kesilirse kalan kümeler önerisiz kalır, nedeni yazılır
                stopped = f"Zeki AI cevap vermedi: {str(e)[:160]}"
        rows.append((g, members, samples, rule, sug))
    with engine.begin() as c:
        old = [r[0] for r in c.execute(sa.select(CLUSTERS.c.id).where(CLUSTERS.c.tenant_id == tenant, CLUSTERS.c.status == "oneri"))]
        if old:
            c.execute(MEMBERS.delete().where(MEMBERS.c.cluster_id.in_(old)))
            c.execute(CLUSTERS.delete().where(CLUSTERS.c.id.in_(old)))
        for g, members, samples, rule, sug in rows:
            cid = uuid.uuid4().hex
            c.execute(CLUSTERS.insert().values(id=cid, tenant_id=tenant, run_id=run_id, built_at=now, window_days=days,
                                               size=len(members), distinct_texts=len(g), samples_json=json.dumps(samples, ensure_ascii=False),
                                               rule_classes_json=json.dumps(dict(rule), ensure_ascii=False), status="oneri",
                                               note=stopped, **sug))
            for m in members:
                c.execute(MEMBERS.insert().values(cluster_id=cid, query_id=m["queryId"], rule_klass=m.get("klass")))
    return {"runId": run_id, "clusters": len(rows), "questions": sum(len(r[1]) for r in rows), "singletons": singletons,
            "asked": asked, "stopped": stopped, "minSim": st["minSim"]}


# ------------------------------------------------------------------ okuma ve karar


def listing(engine: sa.engine.Engine, tenant: str, *, status: str = "oneri") -> dict[str, Any]:
    ensure(engine)
    q = sa.select(CLUSTERS).where(CLUSTERS.c.tenant_id == tenant)
    if status:
        q = q.where(CLUSTERS.c.status == status)
    with engine.connect() as c:
        rows = c.execute(q.order_by(CLUSTERS.c.size.desc(), CLUSTERS.c.id)).mappings().all()
        last = c.execute(sa.select(sa.func.max(CLUSTERS.c.built_at)).where(CLUSTERS.c.tenant_id == tenant)).scalar()
    classes = {k["klass"]: k["label"] for k in MQ.load_classes(engine, active_only=False)}
    items = []
    for r in rows:
        rule = json.loads(r["rule_classes_json"] or "{}")
        items.append({"id": r["id"], "size": r["size"], "distinctTexts": r["distinct_texts"],
                      "samples": json.loads(r["samples_json"] or "[]"),
                      "ruleClasses": [{"klass": k, "label": classes.get(k) or ("Sınıflanamadı" if k == MQ.UNCLASSIFIED else k),
                                       "count": v} for k, v in sorted(rule.items(), key=lambda kv: -kv[1])],
                      "suggested": r["suggested"], "suggestedLabel": r["suggested_label"], "probability": r["probability"],
                      "margin": r["margin"], "method": r["method"], "confident": bool(r["confident"]), "status": r["status"],
                      "statusLabel": STATUS.get(r["status"], r["status"]), "decidedKlass": r["decided_klass"],
                      "decidedLabel": classes.get(r["decided_klass"] or ""), "decidedBy": r["decided_by"],
                      "decidedAt": MQ._iso(r["decided_at"]), "builtAt": MQ._iso(r["built_at"]), "windowDays": r["window_days"],
                      "note": r["note"]})
    return {"items": items, "builtAt": MQ._iso(last), "statusLabels": STATUS,
            "method": ("Başarısız sorular anlam benzerliğiyle kümelenir; Zeki AI her kümeye sınıf önerir. Onaylanınca "
                       "kümedeki sorular o sınıfta sayılır. Kural tablosu değişmez.")}


def decide(engine: sa.engine.Engine, tenant: str, cluster_id: str, user: str, action: str,
           klass: Optional[str] = None, note: Optional[str] = None) -> dict[str, Any]:
    ensure(engine)
    if action not in ("onayla", "reddet"):
        raise MQ.QualityError("İşlem onayla ya da reddet olmalı.")
    with engine.begin() as c:
        r = c.execute(sa.select(CLUSTERS).where(CLUSTERS.c.id == cluster_id, CLUSTERS.c.tenant_id == tenant)).mappings().first()
        if r is None:
            raise MQ.QualityError("Küme bulunamadı.", 404)
        if r["status"] != "oneri":
            raise MQ.QualityError("Bu kümeye zaten karar verilmiş.", 409)
        t = _now()
        if action == "reddet":
            c.execute(CLUSTERS.update().where(CLUSTERS.c.id == cluster_id).values(
                status="reddedildi", decided_by=user, decided_at=t, note=(note or r["note"])))
            return {"id": cluster_id, "status": "reddedildi", "written": 0}
        k = (klass or r["suggested"] or "").strip()
        known = {x["klass"] for x in MQ.load_classes(engine, active_only=False)}
        if not k or k not in known:
            raise MQ.QualityError("Onay için var olan bir hata sınıfı seçin (yeni sınıf gerekiyorsa önce sınıf kuralı yazılır).")
        members = [m[0] for m in c.execute(sa.select(MEMBERS.c.query_id).where(MEMBERS.c.cluster_id == cluster_id))]
        for qid in members:
            n = c.execute(QUERY_CLASSES.update().where(QUERY_CLASSES.c.tenant_id == tenant, QUERY_CLASSES.c.query_id == qid)
                          .values(klass=k, cluster_id=cluster_id, decided_by=user, decided_at=t)).rowcount
            if not n:
                c.execute(QUERY_CLASSES.insert().values(tenant_id=tenant, query_id=qid, klass=k, cluster_id=cluster_id,
                                                        decided_by=user, decided_at=t))
        c.execute(CLUSTERS.update().where(CLUSTERS.c.id == cluster_id).values(
            status="onaylandi", decided_klass=k, decided_by=user, decided_at=t, note=(note or r["note"])))
    return {"id": cluster_id, "status": "onaylandi", "klass": k, "written": len(members)}


def human_classes(engine: sa.engine.Engine, tenant: str) -> dict[str, str]:
    """query_id → kümeden onaylanan sınıf (sınıf panosu kuraldan önce sayar)."""
    ensure(engine)
    with engine.connect() as c:
        return {q: k for q, k in c.execute(sa.select(QUERY_CLASSES.c.query_id, QUERY_CLASSES.c.klass).where(
            QUERY_CLASSES.c.tenant_id == tenant))}
