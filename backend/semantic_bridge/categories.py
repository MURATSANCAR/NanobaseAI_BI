"""H1 Kategori ağacı: tek onaylı kategori ağacı, kitap profili (öneri → editör onayı), tutarsızlık kuralları ve
«CRM'e işlenecek fark» listesi.

**Neden:** CRM'de bir kitap yedi ayrı, birbirine bağlı olmayan sınıflamada durur (Kitaplık, ürün kategorisi ağacı,
raf kategorisi, sergilenecek kategori, tür, web kategorisi metni, tema) ve T-soft'un site ağacı ayrıdır. Bu modül
bunları tek bir onaylı ağaca bağlar ve eksikleri kitap kitap, satış önceliğiyle kapattırır.

**Yazma yok:** CRM'e, T-soft'a ve Logo'ya hiçbir şey yazılmaz. Onaylanan profil köprünün kendi tablolarında durur;
ekran CRM'deki bugünkü değerle onaylı değer arasındaki farkı «CRM'e işlenecek fark» diye listeler, CRM'e insan işler.

**Ağaç (K3):** sürümlüdür. Taslak → onaya gönder → onay (açıkça verilen `ozellik:kategori.agac-onay`; gönderen
onaylayamaz) → yürürlükte; önceki yürürlükteki sürüm arşive geçer. Düğüm kimliği sürümler arasında sabittir (taslak
yürürlükteki ağacın kopyasıyla başlar), böylece profillerdeki kategori değeri sürüm değişince kaybolmaz; yeni sürümde
kaldırılan düğüme bağlı onaylı profil etki önizlemesinde görünür. Düğüm düzeyleri: yayinevi → ana → alt → altalt.
Her düğümün dış sistem eşlemeleri vardır (CRM Kitaplık, ürün kategorisi, raf, sergilenecek, web kategorisi, hedef
kitle, marka, T-soft kategorisi, uluslararası konu kodu); kitap bu eşlemelerle ağaca **deterministik** yerleşir
(`resolve`), model yalnız yerleşemeyen ya da birden çok düğüme düşen kitapta seçer.

**Profil (K2):** alanlar kategori (ağaç düğümü), tür, hedef kitle, yaş aralığı, tema, etiket. Her alanın mevcut
(CRM) değeri, önerisi (kaynağı, olasılığı, kanıtı) ve kararı (kabul / düzeltme / ret, kim, ne zaman) ayrı tutulur;
kısmi onay serbesttir. Kategori değeri her zaman yürürlükteki ağacın düğümüdür (uydurma kategori yazılamaz). Her
öneri ve karar `semantic_book_profile_events`'e düşer (ölçüm ve değerlendirme verisi budur); her yazma
`semantic_audit`'e.

**Tutarsızlık kuralları (K1):** deterministik, veriden; ekrandan açılıp kapanır, parametreleri ekrandadır. Yalnız
liste üretir, hiçbir şeyi değiştirmez.

**M2 bağlantı noktası:** editör atamasının kategori kuralı (Kitaplık / marka) yeniden yazılmadı; `m2_node_for()`
bir CRM Kitaplık ya da markanın yürürlükteki ağaçtaki düğümünü verir, M2 kural tablosu ağaca geçerken bunu okur.
"""
from __future__ import annotations

import io
import json
import logging
import threading
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

log = logging.getLogger("semantic.categories")
_md = sa.MetaData()

TREES = sa.Table(
    "semantic_category_trees", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("version", sa.Integer, nullable=False),
    sa.Column("status", sa.String(16), nullable=False),       # taslak | onay-bekliyor | yururlukte | arsiv
    sa.Column("note", sa.Text),
    sa.Column("based_on", sa.String(32)),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
    sa.Column("submitted_by", sa.String(120)),
    sa.Column("submitted_at", sa.DateTime(timezone=True)),
    sa.Column("approved_by", sa.String(120)),
    sa.Column("approved_at", sa.DateTime(timezone=True)),
    sa.Column("decision_note", sa.Text),
)
NODES = sa.Table(
    "semantic_category_nodes", _md,
    sa.Column("tree_id", sa.String(32), primary_key=True),
    sa.Column("id", sa.String(32), primary_key=True),          # sürümler arasında sabit
    sa.Column("parent_id", sa.String(32)),
    sa.Column("level", sa.String(10), nullable=False),         # yayinevi | ana | alt | altalt
    sa.Column("name", sa.String(200), nullable=False),
    sa.Column("code", sa.String(60)),
    sa.Column("sort", sa.Integer, nullable=False, default=0),
    sa.Column("status", sa.String(10), nullable=False, default="aktif"),  # aktif | pasif
)
MAPPINGS = sa.Table(
    "semantic_category_mappings", _md,
    sa.Column("tree_id", sa.String(32), primary_key=True),
    sa.Column("node_id", sa.String(32), primary_key=True),
    sa.Column("system", sa.String(24), primary_key=True),
    sa.Column("external_id", sa.String(300), primary_key=True),
    sa.Column("external_name", sa.String(300)),
    sa.Column("source", sa.String(10), nullable=False, default="elle"),   # oneri | elle
    sa.Column("approved_by", sa.String(120)),
    sa.Column("approved_at", sa.DateTime(timezone=True)),
)
PROFILES = sa.Table(
    "semantic_book_profiles", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("book_id", sa.String(40), primary_key=True),     # CRM new_kitapId
    sa.Column("stock_code", sa.String(60), index=True),
    sa.Column("isbn", sa.String(40)),
    sa.Column("ean", sa.String(20)),
    sa.Column("name", sa.String(400)),
    sa.Column("author", sa.String(400)),
    sa.Column("brand_id", sa.String(40)),
    sa.Column("brand_name", sa.String(200)),
    sa.Column("kitaplik_id", sa.String(40)),
    sa.Column("kitaplik_name", sa.String(200)),
    sa.Column("editor_id", sa.String(40)),
    sa.Column("director_id", sa.String(40)),
    sa.Column("active", sa.Boolean, nullable=False, default=True),
    sa.Column("status", sa.String(10), nullable=False),        # yok | taslak | kismi | onayli | red
    sa.Column("fields_json", sa.Text, nullable=False),
    sa.Column("crm_snapshot_json", sa.Text, nullable=False),
    sa.Column("priority_score", sa.Float, nullable=False, default=0.0),   # son N ay net adet (Logo)
    sa.Column("node_id", sa.String(32)),                       # onaylı kategori düğümü
    sa.Column("resolved_node_id", sa.String(32)),              # CRM eşlemesinden türeyen düğüm (yürürlükteki ağaç)
    sa.Column("findings", sa.Integer, nullable=False, default=0),
    sa.Column("model_call_ids", sa.Text),
    sa.Column("crm_created_at", sa.String(25)),
    sa.Column("synced_at", sa.DateTime(timezone=True)),
    sa.Column("proposed_at", sa.DateTime(timezone=True)),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
    sa.Index("ix_semantic_book_profiles_queue", "tenant_id", "active", "status"),
)
EVENTS = sa.Table(
    "semantic_book_profile_events", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("book_id", sa.String(40), nullable=False, index=True),
    sa.Column("field", sa.String(24), nullable=False),
    sa.Column("old", sa.Text),
    sa.Column("new", sa.Text),
    sa.Column("action", sa.String(12), nullable=False),        # oneri | kabul | duzeltme | ret | sifirla
    sa.Column("user", sa.String(120), nullable=False),
    sa.Column("at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("detail_json", sa.Text),
)
FINDINGS = sa.Table(
    "semantic_category_findings", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("book_id", sa.String(40), nullable=False),
    sa.Column("rule_key", sa.String(40), nullable=False),
    sa.Column("detail_json", sa.Text, nullable=False),
    sa.Column("status", sa.String(12), nullable=False),        # acik | duzeltildi | yoksay
    sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
    sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
    sa.Column("closed_at", sa.DateTime(timezone=True)),
    sa.Column("decided_by", sa.String(120)),
    sa.Column("note", sa.String(500)),
    sa.UniqueConstraint("tenant_id", "book_id", "rule_key", name="uq_semantic_category_findings"),
    sa.Index("ix_semantic_category_findings_open", "tenant_id", "status", "rule_key"),
)
RULES = sa.Table(
    "semantic_category_rules", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("rule_key", sa.String(40), primary_key=True),
    sa.Column("label", sa.String(200), nullable=False),
    sa.Column("enabled", sa.Boolean, nullable=False, default=True),
    sa.Column("params_json", sa.Text, nullable=False),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
)
TAGS = sa.Table(
    "semantic_tag_vocabulary", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("tag", sa.String(200), primary_key=True),
    sa.Column("source", sa.String(20), nullable=False),        # crm_anahtarkelime | onayli | oneri
    sa.Column("status", sa.String(10), nullable=False),        # aktif | oneri | red | birlesti
    sa.Column("merged_into", sa.String(200)),
    sa.Column("crm_id", sa.String(40)),
    sa.Column("books", sa.Integer, nullable=False, default=0),
    sa.Column("created_by", sa.String(120)),
    sa.Column("created_at", sa.DateTime(timezone=True)),
    sa.Column("decided_by", sa.String(120)),
    sa.Column("decided_at", sa.DateTime(timezone=True)),
)
META = sa.Table(
    "semantic_category_meta", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("key", sa.String(60), primary_key=True),
    sa.Column("value_json", sa.Text, nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

LEVELS = {"yayinevi": "Yayınevi", "ana": "Ana kategori", "alt": "Alt kategori", "altalt": "Alt alt kategori"}
LEVEL_ORDER = list(LEVELS)
TREE_STATUS = {"taslak": "Taslak", "onay-bekliyor": "Onay bekliyor", "yururlukte": "Yürürlükte", "arsiv": "Arşiv"}
#: Düğüm eşlemesinin dış sistemleri. Kitabın ağaca deterministik yerleşmesinde ağırlığı olanlar `SYSTEM_WEIGHT`'te;
#: marka ve hedef kitle ata düğümlerde **tutarlılık koşuludur** (kitabın markası atadaki markayla çelişirse düğüm aday
#: olamaz). Ağırlıklar kitaptan bağımsız, sabit bir önceliktir: CRM Kitaplık editoryal işbölümünün fiilî kategorisidir
#: (M2), ürün kategorisi ve web kategorisi site sınıflamasıdır, raf/sergilenecek/T-soft zayıf ipucudur.
SYSTEMS = {
    "crm_kitaplik": "CRM Kitaplık", "crm_urunkategorisi": "CRM ürün kategorisi", "crm_raf": "CRM raf kategorisi",
    "crm_sergilenecek": "CRM sergilenecek kategori", "crm_webkategori": "CRM web kategorisi",
    "marka": "Yayınevi (marka)", "hedef_kitle": "Hedef kitle", "tsoft": "T-soft site kategorisi",
    "konu_standardi": "Uluslararası konu kodu",
}
SYSTEM_WEIGHT = {"crm_kitaplik": 3, "crm_urunkategorisi": 2, "crm_webkategori": 2, "crm_raf": 1,
                 "crm_sergilenecek": 1, "tsoft": 1}
CONSTRAINT_SYSTEMS = ("marka", "hedef_kitle")
PROFILE_STATUS = {"yok": "Profil yok", "taslak": "Taslak", "kismi": "Kısmi onay", "onayli": "Onaylı", "red": "Reddedildi"}
FIELDS: dict[str, dict[str, str]] = {
    "kategori": {"label": "Kategori", "kind": "node"},
    "tur": {"label": "Tür", "kind": "many"},
    "hedef_kitle": {"label": "Hedef kitle", "kind": "one"},
    "yas": {"label": "Yaş aralığı", "kind": "one"},
    "tema": {"label": "Tema", "kind": "many"},
    "etiket": {"label": "Etiket", "kind": "many"},
}
DECIDED = ("kabul", "duzeltme", "ret")

#: Deterministik tutarsızlık kuralları. `field`: bulgunun ilgili olduğu profil alanı («Öneriyi uygula» o alanın
#: bekleyen, emin önerisini kabul eder).
RULE_DEFS: dict[str, dict[str, Any]] = {
    "hedef_kitle_web": {"label": "Hedef kitle ile web kategorisi çelişiyor", "field": "hedef_kitle", "params": {},
                        "help": "Web kategorisi metninin ilk parçası bir hedef kitle adıysa (Çocuk/Genç/Yetişkin — "
                                "CRM'in hedef kitle etiketleri) ve kartın hedef kitlesinden farklıysa."},
    "yas_hedef_kitle": {"label": "Yaş aralığı hedef kitleyle uyuşmuyor", "field": "yas", "params": {"yetiskin_yas": 18},
                        "help": "Başlangıç yaşı bitişten büyük; ya da yetişkin kitabın bitiş yaşı eşiğin altında, "
                                "çocuk kitabının başlangıç yaşı eşiğin üstünde."},
    "kitaplik_bos": {"label": "Kitaplık boş", "field": "kategori", "params": {},
                     "help": "Editör atamasının (M2) kategorisi olan Kitaplık alanı doldurulmamış."},
    "tur_bos": {"label": "Tür girilmemiş", "field": "tur", "params": {},
                "help": "Ne tür bağı ne de tür metni var."},
    "ozet_bos": {"label": "Arka kapak metni yok", "field": None, "params": {},
                 "help": "Kategori ve etiket önerisinin ana kanıtı olan arka kapak metni boş."},
    "urun_kategorisi_yok": {"label": "Ürün kategorisi bağı yok", "field": "kategori", "params": {},
                            "help": "Kitap CRM ürün kategorisi ağacında hiçbir kategoriye bağlı değil."},
    "agacta_karsiligi_yok": {"label": "Ağaçta yeri yok", "field": "kategori", "params": {},
                             "help": "Kitabın CRM sınıflamaları yürürlükteki ağacın hiçbir düğümüne eşlenmiyor "
                                     "(ya da birden çok düğüme eşit düşüyor). Yalnız yürürlükte ağaç varken."},
    "tsoft_kategori": {"label": "Sitede farklı kategoride", "field": "kategori", "params": {},
                       "help": "T-soft'taki varsayılan kategorisi, kitabın düğümüne eşlenen T-soft kategorilerinden "
                               "biri değil. Yalnız düğümün T-soft eşlemesi varken; T-soft'a yazılmaz."},
}

_ready: set[int] = set()
_lock = threading.Lock()


class CategoryError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _ready.add(id(engine))


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(v: Optional[datetime]) -> Optional[str]:
    if v is None:
        return None
    if v.tzinfo is None:
        v = v.replace(tzinfo=timezone.utc)
    return v.isoformat()


def loads(raw: Optional[str], default: Any) -> Any:
    try:
        return json.loads(raw) if raw else default
    except ValueError:
        return default


def dumps(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


def new_id(n: int = 32) -> str:
    return uuid.uuid4().hex[:n]


def fold(s: Any) -> str:
    """Türkçe harf farkı gözetmeyen karşılaştırma anahtarı."""
    t = str(s or "").replace("İ", "i").replace("I", "ı").lower()
    return " ".join(t.split())


def setting(key: str, default: str) -> str:
    try:
        from semantic_bridge import admin as admin_mod

        v = admin_mod.conf(key, default)
    except Exception:  # noqa: BLE001 — ayar okunamazsa varsayılan
        v = default
    return str(v if v not in (None, "") else default)


def fsetting(key: str, default: float) -> float:
    try:
        return float(setting(key, str(default)).replace(",", "."))
    except ValueError:
        return default


def thresholds() -> dict[str, float]:
    """Öneri eşikleri (`docs/analiz/llm-choose.md` başlangıç önerisi; golden set ile ölçülecek)."""
    return {"minProb": fsetting("CATEGORY_SUGGEST_MIN_PROB", 0.70),
            "minMargin": fsetting("CATEGORY_SUGGEST_MIN_MARGIN", 0.30),
            "treeMinBooks": fsetting("CATEGORY_TREE_MIN_BOOKS", 3),
            "mapMinShare": fsetting("CATEGORY_MAP_MIN_SHARE", 0.5),
            "coShare": fsetting("CATEGORY_COOCCUR_SHARE", 0.25),
            "staleDays": fsetting("CATEGORY_DIFF_STALE_DAYS", 7),
            "priorityMonths": fsetting("CATEGORY_PRIORITY_MONTHS", 24)}


# ================================================================================ meta


def meta_get(engine: sa.engine.Engine, tenant: str, key: str, default: Any = None) -> Any:
    with engine.connect() as c:
        r = c.execute(sa.select(META.c.value_json).where(META.c.tenant_id == tenant, META.c.key == key)).first()
    return loads(r[0], default) if r else default


def meta_set(engine: sa.engine.Engine, tenant: str, key: str, value: Any, conn: Any = None) -> None:
    def run(c: Any) -> None:
        c.execute(META.delete().where(META.c.tenant_id == tenant, META.c.key == key))
        c.execute(META.insert().values(tenant_id=tenant, key=key, value_json=dumps(value), updated_at=now()))

    if conn is not None:
        run(conn)
    else:
        with engine.begin() as c:
            run(c)


# ================================================================================ ağaç


def _tree_row(r: Any) -> dict[str, Any]:
    m = dict(r._mapping)
    return {"id": m["id"], "version": m["version"], "status": m["status"], "statusLabel": TREE_STATUS.get(m["status"], m["status"]),
            "note": m["note"], "basedOn": m["based_on"], "createdBy": m["created_by"], "createdAt": iso(m["created_at"]),
            "updatedBy": m["updated_by"], "updatedAt": iso(m["updated_at"]), "submittedBy": m["submitted_by"],
            "submittedAt": iso(m["submitted_at"]), "approvedBy": m["approved_by"], "approvedAt": iso(m["approved_at"]),
            "decisionNote": m["decision_note"]}


def tree_versions(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(sa.select(TREES).where(TREES.c.tenant_id == tenant).order_by(TREES.c.version.desc())).fetchall()
    return [_tree_row(r) for r in rows]


def _tree_by_status(engine: sa.engine.Engine, tenant: str, statuses: Iterable[str]) -> Optional[dict[str, Any]]:
    with engine.connect() as c:
        r = c.execute(sa.select(TREES).where(TREES.c.tenant_id == tenant, TREES.c.status.in_(list(statuses)))
                      .order_by(TREES.c.version.desc())).first()
    return _tree_row(r) if r else None


def in_force(engine: sa.engine.Engine, tenant: str) -> Optional[dict[str, Any]]:
    return _tree_by_status(engine, tenant, ("yururlukte",))


def draft(engine: sa.engine.Engine, tenant: str) -> Optional[dict[str, Any]]:
    return _tree_by_status(engine, tenant, ("taslak", "onay-bekliyor"))


def nodes_of(engine: sa.engine.Engine, tree_id: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(sa.select(NODES).where(NODES.c.tree_id == tree_id).order_by(NODES.c.sort, NODES.c.name)).mappings().all()
    return [{"id": r["id"], "parentId": r["parent_id"], "level": r["level"], "name": r["name"], "code": r["code"],
             "sort": r["sort"], "status": r["status"]} for r in rows]


def mappings_of(engine: sa.engine.Engine, tree_id: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(sa.select(MAPPINGS).where(MAPPINGS.c.tree_id == tree_id)).mappings().all()
    return [{"nodeId": r["node_id"], "system": r["system"], "externalId": r["external_id"], "externalName": r["external_name"],
             "source": r["source"], "approvedBy": r["approved_by"], "approvedAt": iso(r["approved_at"])} for r in rows]


class TreeCtx:
    """Bir ağaç sürümünün bellekteki hâli: düğümler, çocuklar, yol adları, eşlemeler."""

    def __init__(self, tree: Optional[dict[str, Any]], nodes: list[dict[str, Any]], maps: list[dict[str, Any]]):
        self.tree = tree
        self.nodes = {n["id"]: n for n in nodes}
        self.children: dict[Optional[str], list[str]] = defaultdict(list)
        for n in sorted(nodes, key=lambda x: (x.get("sort") or 0, fold(x["name"]))):
            if n.get("status", "aktif") == "aktif":
                self.children[n.get("parentId")].append(n["id"])
        self.by_ext: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        self.node_maps: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
        for m in maps:
            if m["nodeId"] not in self.nodes:
                continue
            self.by_ext[m["system"]][str(m["externalId"])].append(m["nodeId"])
            self.node_maps[m["nodeId"]][m["system"]].append(m)

    @property
    def empty(self) -> bool:
        return not self.nodes

    def active(self, node_id: Optional[str]) -> bool:
        n = self.nodes.get(node_id or "")
        return bool(n) and n.get("status", "aktif") == "aktif" and all(
            self.nodes.get(a, {}).get("status", "aktif") == "aktif" for a in self.ancestors(node_id))

    def ancestors(self, node_id: Optional[str]) -> list[str]:
        out, seen = [], set()
        cur = self.nodes.get(node_id or "", {}).get("parentId")
        while cur and cur in self.nodes and cur not in seen:
            out.append(cur)
            seen.add(cur)
            cur = self.nodes[cur].get("parentId")
        return out

    def path(self, node_id: Optional[str]) -> Optional[str]:
        if not node_id or node_id not in self.nodes:
            return None
        chain = [node_id, *self.ancestors(node_id)]
        return " > ".join(self.nodes[x]["name"] for x in reversed(chain))

    def depth(self, node_id: str) -> int:
        return len(self.ancestors(node_id))

    def descendants(self, node_id: str) -> list[str]:
        out, stack = [], list(self.children.get(node_id, []))
        while stack:
            x = stack.pop()
            out.append(x)
            stack.extend(self.children.get(x, []))
        return out

    def ext_of(self, node_id: str, system: str) -> list[str]:
        return [str(m["externalId"]) for m in self.node_maps.get(node_id, {}).get(system, [])]

    def constraint_ok(self, node_id: str, book: dict[str, Any]) -> bool:
        """Düğüm ve atalarındaki marka / hedef kitle eşlemesi kitabınkiyle çelişmiyor mu."""
        chain = [node_id, *self.ancestors(node_id)]
        values = {"marka": ((book.get("marka") or {}).get("id")),
                  "hedef_kitle": (str((book.get("hedefKitle") or {}).get("code")) if (book.get("hedefKitle") or {}).get("code") is not None else None)}
        for system in CONSTRAINT_SYSTEMS:
            for n in chain:
                exts = self.ext_of(n, system)
                if exts and values[system] is not None and values[system] not in exts:
                    return False
        return True

    def start_nodes(self, book: dict[str, Any]) -> list[str]:
        """Modelin seçime başlayacağı düğümler: kitabın markasına eşlenen düğüm(ler)in çocukları; yoksa kökler."""
        marka = (book.get("marka") or {}).get("id")
        hits = [n for n in self.by_ext.get("marka", {}).get(marka or "", []) if self.active(n)] if marka else []
        return hits

    def flat(self) -> list[dict[str, Any]]:
        out = []
        for nid, n in self.nodes.items():
            out.append({**n, "path": self.path(nid), "depth": self.depth(nid),
                        "mappings": {s: [{"id": m["externalId"], "name": m["externalName"]} for m in ms]
                                     for s, ms in self.node_maps.get(nid, {}).items()}})
        out.sort(key=lambda x: fold(x["path"]))
        return out


def tree_ctx(engine: sa.engine.Engine, tree: Optional[dict[str, Any]]) -> TreeCtx:
    if not tree:
        return TreeCtx(None, [], [])
    return TreeCtx(tree, nodes_of(engine, tree["id"]), mappings_of(engine, tree["id"]))


def book_ext(book: dict[str, Any]) -> dict[str, list[str]]:
    """Kitabın dış sistemlerdeki değerleri (eşleme anahtarları)."""
    out: dict[str, list[str]] = {
        "crm_kitaplik": [book["kitaplik"]["id"]] if book.get("kitaplik") else [],
        "crm_urunkategorisi": [x["id"] for x in book.get("urunkategorisi") or []],
        "crm_raf": [x["id"] for x in book.get("raf") or []],
        "crm_sergilenecek": [x["id"] for x in book.get("sergilenecek") or []],
        "crm_webkategori": [x for x in (book.get("webSub"), book.get("web")) if x],
        "tsoft": [x for x in ([(book.get("tsoft") or {}).get("categoryId")] + list((book.get("tsoft") or {}).get("categories") or [])) if x],
    }
    return out


def resolve(ctx: TreeCtx, book: dict[str, Any]) -> dict[str, Any]:
    """Kitabın CRM/T-soft sınıflamalarından yürürlükteki ağaçtaki yeri. Model yok.

    Her eşleşen (sistem, dış değer) → düğüm, sistemin ağırlığı kadar puan alır; marka / hedef kitle çelişen düğüm
    elenir. En yüksek puan kazanır; eşitlikte biri ötekinin atasıysa daha derindeki. Eşit ve ilgisizse «belirsiz»:
    adaylar modele gider. Dönüş: {nodeId, candidates, reason, hits}."""
    if ctx.empty:
        return {"nodeId": None, "candidates": [], "reason": "Yürürlükte ağaç yok.", "hits": []}
    score: dict[str, float] = defaultdict(float)
    hits: list[dict[str, Any]] = []
    for system, values in book_ext(book).items():
        w = SYSTEM_WEIGHT.get(system, 0)
        for v in values:
            for nid in ctx.by_ext.get(system, {}).get(str(v), []):
                if not ctx.active(nid) or not ctx.constraint_ok(nid, book):
                    continue
                score[nid] += w
                hits.append({"system": system, "systemLabel": SYSTEMS[system], "value": v, "nodeId": nid})
    if not score:
        return {"nodeId": None, "candidates": [], "reason": "CRM sınıflamalarının hiçbiri ağaçta bir düğüme eşlenmiyor.",
                "hits": []}
    # Ata düğümün puanı torununa da geçer (Kitaplık ata, web kategorisi torun eşlenmişse torun kazanır).
    total = {n: s + sum(score.get(a, 0) for a in ctx.ancestors(n)) for n, s in score.items()}
    best = max(total.values())
    top = [n for n, s in total.items() if s == best]
    top = [n for n in top if not any(n in ctx.ancestors(o) for o in top if o != n)]
    if len(top) == 1:
        nid = top[0]
        why = ", ".join(sorted({f"{h['systemLabel']}: {h['value']}" if h["system"] == "crm_webkategori" else h["systemLabel"]
                                for h in hits if h["nodeId"] in (nid, *ctx.ancestors(nid))}))
        return {"nodeId": nid, "candidates": [nid], "reason": f"CRM beyanı ({why})", "hits": hits}
    return {"nodeId": None, "candidates": sorted(top, key=lambda n: fold(ctx.path(n))),
            "reason": "CRM sınıflamaları ağaçta birden çok düğüme eşit düşüyor.", "hits": hits}


# ---------------------------------------------------------------- ağaç yazma


def _clean_nodes(nodes: Any) -> list[dict[str, Any]]:
    if not isinstance(nodes, list):
        raise CategoryError("Düğüm listesi bekleniyordu.")
    out: list[dict[str, Any]] = []
    ids: set[str] = set()
    for i, n in enumerate(nodes, 1):
        if not isinstance(n, dict):
            raise CategoryError(f"{i}. düğüm geçerli değil.")
        nid = str(n.get("id") or "").strip()[:32] or new_id(12)
        if nid in ids:
            raise CategoryError(f"«{n.get('name')}» düğümünün kimliği iki kez yazılmış.")
        ids.add(nid)
        name = " ".join(str(n.get("name") or "").split())[:200]
        if not name:
            raise CategoryError(f"{i}. düğümün adı boş.")
        level = str(n.get("level") or "")
        if level not in LEVELS:
            raise CategoryError(f"«{name}» düğümünün düzeyi geçerli değil.")
        status = str(n.get("status") or "aktif")
        if status not in ("aktif", "pasif"):
            raise CategoryError(f"«{name}» düğümünün durumu geçerli değil.")
        out.append({"id": nid, "parentId": (str(n.get("parentId") or "").strip() or None), "level": level, "name": name,
                    "code": (str(n.get("code") or "").strip()[:60] or None), "sort": int(n.get("sort") or 0), "status": status})
    by = {n["id"]: n for n in out}
    siblings: dict[tuple[Optional[str], str], str] = {}
    for n in out:
        p = n["parentId"]
        if p is not None and p not in by:
            raise CategoryError(f"«{n['name']}» düğümünün üst düğümü listede yok.")
        if p is not None and LEVEL_ORDER.index(by[p]["level"]) >= LEVEL_ORDER.index(n["level"]):
            raise CategoryError(f"«{n['name']}» düzeyi üst düğümünün ({by[p]['name']}) altında olmalı.")
        key = (p, fold(n["name"]))
        if key in siblings:
            raise CategoryError(f"Aynı üst düğümün altında iki «{n['name']}» var; kardeş düğümlerin adı farklı olmalı.")
        siblings[key] = n["id"]
        seen, cur = {n["id"]}, p
        while cur:
            if cur in seen:
                raise CategoryError(f"«{n['name']}» düğümünde döngü var.")
            seen.add(cur)
            cur = by[cur]["parentId"]
    return out


def _clean_maps(maps: Any, node_ids: set[str]) -> list[dict[str, Any]]:
    if maps is None:
        return []
    if not isinstance(maps, list):
        raise CategoryError("Eşleme listesi bekleniyordu.")
    out, seen = [], set()
    for m in maps:
        if not isinstance(m, dict):
            continue
        nid, system, ext = str(m.get("nodeId") or ""), str(m.get("system") or ""), str(m.get("externalId") or "").strip()[:300]
        if system not in SYSTEMS:
            raise CategoryError(f"Bilinmeyen eşleme sistemi: {system}")
        if nid not in node_ids or not ext:
            continue
        key = (nid, system, ext)
        if key in seen:
            continue
        seen.add(key)
        out.append({"nodeId": nid, "system": system, "externalId": ext,
                    "externalName": (str(m.get("externalName") or "").strip()[:300] or None),
                    "source": "oneri" if m.get("source") == "oneri" else "elle"})
    return out


def _write_tree(c: Any, tree_id: str, nodes: list[dict[str, Any]], maps: list[dict[str, Any]]) -> None:
    c.execute(NODES.delete().where(NODES.c.tree_id == tree_id))
    c.execute(MAPPINGS.delete().where(MAPPINGS.c.tree_id == tree_id))
    if nodes:
        c.execute(NODES.insert(), [{"tree_id": tree_id, "id": n["id"], "parent_id": n["parentId"], "level": n["level"],
                                    "name": n["name"], "code": n["code"], "sort": n["sort"], "status": n["status"]} for n in nodes])
    if maps:
        c.execute(MAPPINGS.insert(), [{"tree_id": tree_id, "node_id": m["nodeId"], "system": m["system"],
                                       "external_id": m["externalId"], "external_name": m["externalName"],
                                       "source": m.get("source") or "elle"} for m in maps])


def save_draft(engine: sa.engine.Engine, tenant: str, actor: str, body: dict[str, Any]) -> dict[str, Any]:
    """Taslağı yazar (yoksa yürürlükteki ağacın üstüne açar). `mappings` verilmezse taslağın eşlemeleri korunur
    (silinen düğümünkiler düşer)."""
    nodes = _clean_nodes(body.get("nodes"))
    ids = {n["id"] for n in nodes}
    cur = draft(engine, tenant)
    if cur and cur["status"] == "onay-bekliyor":
        raise CategoryError("Taslak onay bekliyor; değiştirmek için önce onaydan geri alın.", 409)
    if cur and body.get("version") is not None and int(body["version"]) != int(cur["version"]):
        raise CategoryError("Taslak siz düzenlerken değişti; sayfayı yenileyip yeniden deneyin.", 409)
    maps = (_clean_maps(body.get("mappings"), ids) if "mappings" in body
            else [m for m in (mappings_of(engine, cur["id"]) if cur else []) if m["nodeId"] in ids])
    with engine.begin() as c:
        if cur:
            tid = cur["id"]
            c.execute(TREES.update().where(TREES.c.id == tid).values(
                note=(str(body.get("note") or "")[:2000] or cur["note"]), updated_by=actor[:120], updated_at=now()))
        else:
            base = in_force(engine, tenant)
            top = c.execute(sa.select(sa.func.max(TREES.c.version)).where(TREES.c.tenant_id == tenant)).scalar() or 0
            tid = new_id()
            c.execute(TREES.insert().values(id=tid, tenant_id=tenant, version=int(top) + 1, status="taslak",
                                            note=(str(body.get("note") or "")[:2000] or None),
                                            based_on=base["id"] if base else None, created_by=actor[:120], created_at=now()))
        _write_tree(c, tid, nodes, maps)
    return tree_state(engine, tenant)


def open_draft(engine: sa.engine.Engine, tenant: str, actor: str) -> dict[str, Any]:
    """Yürürlükteki ağacın kopyasıyla taslak açar (düğüm kimlikleri aynı kalır)."""
    if draft(engine, tenant):
        raise CategoryError("Zaten bir taslak var.", 409)
    base = in_force(engine, tenant)
    if not base:
        raise CategoryError("Yürürlükte ağaç yok; «Veriden taslak» ile ya da boş taslakla başlayın.", 404)
    return save_draft(engine, tenant, actor, {"nodes": nodes_of(engine, base["id"]), "mappings": mappings_of(engine, base["id"]),
                                              "note": None})


def discard_draft(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    cur = draft(engine, tenant)
    if not cur:
        raise CategoryError("Silinecek taslak yok.", 404)
    if cur["status"] != "taslak":
        raise CategoryError("Onay bekleyen taslak silinemez; önce geri alın.", 409)
    with engine.begin() as c:
        c.execute(NODES.delete().where(NODES.c.tree_id == cur["id"]))
        c.execute(MAPPINGS.delete().where(MAPPINGS.c.tree_id == cur["id"]))
        c.execute(TREES.delete().where(TREES.c.id == cur["id"]))
    return tree_state(engine, tenant)


def set_mappings(engine: sa.engine.Engine, tenant: str, actor: str, node_id: str, system: str,
                 items: Any) -> dict[str, Any]:
    """Taslakta bir düğümün bir sistemdeki eşlemelerini baştan yazar."""
    cur = draft(engine, tenant)
    if not cur or cur["status"] != "taslak":
        raise CategoryError("Eşleme yalnız taslakta değişir; önce taslak açın.", 409)
    if system not in SYSTEMS:
        raise CategoryError("Bilinmeyen eşleme sistemi.")
    nodes = {n["id"] for n in nodes_of(engine, cur["id"])}
    if node_id not in nodes:
        raise CategoryError("Düğüm taslakta yok.", 404)
    maps = _clean_maps([{**x, "nodeId": node_id, "system": system} for x in (items or []) if isinstance(x, dict)], nodes)
    with engine.begin() as c:
        c.execute(MAPPINGS.delete().where(MAPPINGS.c.tree_id == cur["id"], MAPPINGS.c.node_id == node_id,
                                          MAPPINGS.c.system == system))
        if maps:
            c.execute(MAPPINGS.insert(), [{"tree_id": cur["id"], "node_id": node_id, "system": system,
                                           "external_id": m["externalId"], "external_name": m["externalName"],
                                           "source": "elle"} for m in maps])
        c.execute(TREES.update().where(TREES.c.id == cur["id"]).values(updated_by=actor[:120], updated_at=now()))
    return {"nodeId": node_id, "system": system, "items": maps}


def submit(engine: sa.engine.Engine, tenant: str, actor: str) -> dict[str, Any]:
    cur = draft(engine, tenant)
    if not cur or cur["status"] != "taslak":
        raise CategoryError("Onaya gönderilecek taslak yok.", 404)
    if not nodes_of(engine, cur["id"]):
        raise CategoryError("Boş ağaç onaya gönderilemez.")
    with engine.begin() as c:
        c.execute(TREES.update().where(TREES.c.id == cur["id"]).values(status="onay-bekliyor", submitted_by=actor[:120],
                                                                       submitted_at=now(), decision_note=None))
    return tree_state(engine, tenant)


def withdraw(engine: sa.engine.Engine, tenant: str, actor: str) -> dict[str, Any]:
    cur = draft(engine, tenant)
    if not cur or cur["status"] != "onay-bekliyor":
        raise CategoryError("Onay bekleyen taslak yok.", 404)
    with engine.begin() as c:
        c.execute(TREES.update().where(TREES.c.id == cur["id"]).values(status="taslak", updated_by=actor[:120],
                                                                       updated_at=now()))
    return tree_state(engine, tenant)


def decide_tree(engine: sa.engine.Engine, tenant: str, actor: str, approve: bool, version: Any,
                note: Optional[str]) -> dict[str, Any]:
    """Onay/ret. Gönderen onaylayamaz (iki göz). `version` onaylayanın gördüğü taslak sürümüdür."""
    cur = draft(engine, tenant)
    if not cur or cur["status"] != "onay-bekliyor":
        raise CategoryError("Onay bekleyen taslak yok.", 404)
    if version is not None and int(version) != int(cur["version"]):
        raise CategoryError("Taslak siz bakarken değişti; yeniden açıp kontrol edin.", 409)
    if (cur["submittedBy"] or "").lower() == actor.lower():
        raise CategoryError("Taslağı onaya gönderen kişi onaylayamaz ya da geri gönderemez.", 403)
    if not approve and not (note or "").strip():
        raise CategoryError("Geri gönderirken gerekçe yazın.")
    with engine.begin() as c:
        if approve:
            c.execute(TREES.update().where(TREES.c.tenant_id == tenant, TREES.c.status == "yururlukte").values(status="arsiv"))
            c.execute(TREES.update().where(TREES.c.id == cur["id"]).values(
                status="yururlukte", approved_by=actor[:120], approved_at=now(), decision_note=(note or None)))
            c.execute(MAPPINGS.update().where(MAPPINGS.c.tree_id == cur["id"]).values(approved_by=actor[:120], approved_at=now()))
        else:
            c.execute(TREES.update().where(TREES.c.id == cur["id"]).values(status="taslak", decision_note=note.strip()[:2000]))
    return tree_state(engine, tenant)


def tree_state(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    """Ekranın ağaç görünümü: yürürlükteki ağaç + taslak (düğümler, yol, eşlemeler, düğüm başına kitap/satış)."""
    live, dr = in_force(engine, tenant), draft(engine, tenant)
    counts = node_counts(engine, tenant)

    def pack(t: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if not t:
            return None
        ctx = tree_ctx(engine, t)
        items = ctx.flat()
        for n in items:
            k = counts.get(n["id"], {})
            n["books"] = k.get("books", 0)
            n["approved"] = k.get("approved", 0)
            n["sales"] = k.get("sales", 0.0)
        return {**t, "nodes": items}

    return {"inForce": pack(live), "draft": pack(dr), "versions": tree_versions(engine, tenant),
            "levels": LEVELS, "systems": SYSTEMS}


def node_counts(engine: sa.engine.Engine, tenant: str) -> dict[str, dict[str, Any]]:
    """Düğüm (ve ataları) başına aktif kitap sayısı, onaylı profil sayısı ve öncelik (son N ay net adet) toplamı.
    Kitabın düğümü: onaylı kategori, yoksa CRM eşlemesinden türeyen."""
    ctx = tree_ctx(engine, in_force(engine, tenant))
    out: dict[str, dict[str, Any]] = defaultdict(lambda: {"books": 0, "approved": 0, "sales": 0.0})
    with engine.connect() as c:
        rows = c.execute(sa.select(PROFILES.c.node_id, PROFILES.c.resolved_node_id, PROFILES.c.priority_score)
                         .where(PROFILES.c.tenant_id == tenant, PROFILES.c.active.is_(True))).all()
    for node_id, resolved, score in rows:
        nid = node_id or resolved
        if not nid:
            continue
        for x in [nid, *ctx.ancestors(nid)]:
            out[x]["books"] += 1
            out[x]["sales"] += float(score or 0)
            if node_id:
                out[x]["approved"] += 1
    return out


#: «Veriden taslak ağaç»ın ekrandaki ve kayıttaki adı. Model kullanmaz; «Zeki AI» adını taşımaz.
SUGGEST_LABEL = "Veriden taslak"


def suggest_draft(engine: sa.engine.Engine, tenant: str, actor: str, replace: bool = False) -> dict[str, Any]:
    """Veriden taslak ağaç (model yok): marka → hedef kitle → Kitaplık (yoksa web alt kategorisi) → web alt kategorisi.
    Bir düğüm en az `CATEGORY_TREE_MIN_BOOKS` aktif kitapla açılır (eşik ekranda; kesme değil, gürültü süzgeci:
    kalan kitaplar profil önerisiyle yerleşir ve rapora yazılır). Alt düğümlere ürün kategorisi ve T-soft eşlemesi,
    kitaplarının en az `CATEGORY_MAP_MIN_SHARE` payında ortaksa «öneri» olarak eklenir."""
    cur = draft(engine, tenant)
    if cur and not replace and nodes_of(engine, cur["id"]):
        raise CategoryError("Taslakta düğüm var; üzerine yazmak için «taslağı değiştir» seçeneğini işaretleyin.", 409)
    if cur and cur["status"] != "taslak":
        raise CategoryError("Taslak onay bekliyor; önce geri alın.", 409)
    books = [b for b in all_snapshots(engine, tenant)]
    if not books:
        raise CategoryError("CRM kitap kartları henüz okunmadı; önce «Kaynakları yenile».", 409)
    th = thresholds()
    min_books, min_share = max(1, int(th["treeMinBooks"])), th["mapMinShare"]
    groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    skipped = Counter()
    for b in books:
        marka, hedef = b.get("marka"), b.get("hedefKitle")
        if not marka:
            skipped["marka"] += 1
            continue
        if not hedef or not hedef.get("label"):
            skipped["hedef"] += 1
            continue
        if b.get("kitaplik"):
            alt = ("kitaplik", b["kitaplik"]["id"], b["kitaplik"]["name"])
        elif b.get("webSub"):
            alt = ("web", b["webSub"], b["webSub"])
        else:
            skipped["alt"] += 1
            continue
        groups[(marka["id"], marka["name"], str(hedef["code"]), hedef["label"], alt)].append(b)

    nodes: list[dict[str, Any]] = []
    maps: list[dict[str, Any]] = []
    made: dict[tuple, str] = {}

    def node(key: tuple, parent: Optional[str], level: str, name: str) -> str:
        if key in made:
            return made[key]
        taken = {fold(n["name"]) for n in nodes if n["parentId"] == parent}
        nm, i = name, 2
        while fold(nm) in taken:
            nm, i = f"{name} ({i})", i + 1
        nid = new_id(12)
        nodes.append({"id": nid, "parentId": parent, "level": level, "name": nm[:200], "code": None,
                      "sort": 0, "status": "aktif"})
        made[key] = nid
        return nid

    def common(items: list[str]) -> Optional[tuple[str, int]]:
        if not items:
            return None
        v, n = Counter(items).most_common(1)[0]
        return (v, n)

    by_marka: dict[tuple, int] = Counter()
    by_hedef: dict[tuple, int] = Counter()
    for (mid, mname, hcode, hlabel, alt), bs in groups.items():
        by_marka[(mid, mname)] += len(bs)
        by_hedef[(mid, hcode, hlabel)] += len(bs)
    placed = 0
    for (mid, mname, hcode, hlabel, alt), bs in sorted(groups.items(), key=lambda kv: (fold(kv[0][1]), kv[0][2], fold(kv[0][4][2]))):
        if len(bs) < min_books:
            skipped["az"] += len(bs)
            continue
        m_id = node(("m", mid), None, "yayinevi", mname)
        if not any(x["nodeId"] == m_id and x["system"] == "marka" for x in maps):
            maps.append({"nodeId": m_id, "system": "marka", "externalId": mid, "externalName": mname, "source": "oneri"})
        h_id = node(("h", mid, hcode), m_id, "ana", hlabel)
        if not any(x["nodeId"] == h_id and x["system"] == "hedef_kitle" for x in maps):
            maps.append({"nodeId": h_id, "system": "hedef_kitle", "externalId": hcode, "externalName": hlabel, "source": "oneri"})
        a_id = node(("a", mid, hcode, alt[0], alt[1]), h_id, "alt", alt[2])
        system = "crm_kitaplik" if alt[0] == "kitaplik" else "crm_webkategori"
        maps.append({"nodeId": a_id, "system": system, "externalId": alt[1], "externalName": alt[2], "source": "oneri"})
        placed += len(bs)
        n = len(bs)
        uk = common([x["id"] for b in bs for x in (b.get("urunkategorisi") or [])])
        if uk and uk[1] / n >= min_share:
            name = next((x["name"] for b in bs for x in (b.get("urunkategorisi") or []) if x["id"] == uk[0]), uk[0])
            maps.append({"nodeId": a_id, "system": "crm_urunkategorisi", "externalId": uk[0], "externalName": name, "source": "oneri"})
        ts = common([(b.get("tsoft") or {}).get("categoryId") for b in bs if (b.get("tsoft") or {}).get("categoryId")])
        if ts and ts[1] / n >= min_share:
            name = next(((b.get("tsoft") or {}).get("categoryName") for b in bs if (b.get("tsoft") or {}).get("categoryId") == ts[0]), ts[0])
            maps.append({"nodeId": a_id, "system": "tsoft", "externalId": ts[0], "externalName": name, "source": "oneri"})
        if alt[0] == "kitaplik":
            subs = Counter(b["webSub"] for b in bs if b.get("webSub"))
            for sub, k in sorted(subs.items(), key=lambda kv: fold(kv[0])):
                if k >= min_books and len(subs) > 1:
                    s_id = node(("s", mid, hcode, alt[1], sub), a_id, "altalt", sub)
                    maps.append({"nodeId": s_id, "system": "crm_webkategori", "externalId": sub, "externalName": sub, "source": "oneri"})
    if not nodes:
        raise CategoryError("Veriden ağaç kurulamadı: eşiği geçen kitap grubu yok.", 409)
    # Model yok: ad «veriden taslak»; «Zeki AI» adı yalnız modelin çalıştığı yerde (profil önerisi) kullanılır.
    note = (f"{SUGGEST_LABEL} (kurala göre): {len(books)} aktif kitabın {placed}'i yerleşti; marka boş {skipped['marka']}, "
            f"hedef kitle boş {skipped['hedef']}, Kitaplık ve web kategorisi boş {skipped['alt']}, "
            f"{min_books} kitaptan az gruplarda {skipped['az']} kitap — bunlar profil önerisiyle yerleşir.")
    body = {"nodes": nodes, "mappings": maps, "note": note}
    if cur:
        body["version"] = cur["version"]
    out = save_draft(engine, tenant, actor, body)
    out["suggestion"] = {"books": len(books), "placed": placed, "skipped": dict(skipped), "nodes": len(nodes),
                         "mappings": len(maps), "minBooks": min_books}
    return out


def impact(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    """Taslağın yürürlükteki ağaca göre etkisi: düğüm farkları, yeri değişecek kitaplar, kaldırılan düğüme bağlı onaylı
    profiller, etkilenen M2 kategori–editör kuralları, T-soft karşılığı olmayan alt düğümler."""
    dr = draft(engine, tenant)
    if not dr:
        raise CategoryError("Taslak yok.", 404)
    live = in_force(engine, tenant)
    a, b = tree_ctx(engine, live), tree_ctx(engine, dr)
    added = [n for n in b.nodes if n not in a.nodes]
    removed = [n for n in a.nodes if n not in b.nodes or not b.active(n)]
    renamed = [n for n in b.nodes if n in a.nodes and a.nodes[n]["name"] != b.nodes[n]["name"]]
    moved = [n for n in b.nodes if n in a.nodes and a.nodes[n].get("parentId") != b.nodes[n].get("parentId")]
    map_changed = []
    for n in set(a.nodes) | set(b.nodes):
        sa_ = {(m["system"], str(m["externalId"])) for ms in a.node_maps.get(n, {}).values() for m in ms}
        sb_ = {(m["system"], str(m["externalId"])) for ms in b.node_maps.get(n, {}).values() for m in ms}
        if sa_ != sb_ and n in b.nodes:
            map_changed.append({"nodeId": n, "path": b.path(n), "added": sorted(sb_ - sa_), "removed": sorted(sa_ - sb_)})
    moves: Counter = Counter()
    orphaned: list[dict[str, Any]] = []
    newly_placed = lost = 0
    with engine.connect() as c:
        rows = c.execute(sa.select(PROFILES.c.book_id, PROFILES.c.name, PROFILES.c.node_id, PROFILES.c.crm_snapshot_json,
                                   PROFILES.c.priority_score)
                         .where(PROFILES.c.tenant_id == tenant, PROFILES.c.active.is_(True))).mappings().all()
    for r in rows:
        snap = loads(r["crm_snapshot_json"], {})
        ra, rb = resolve(a, snap)["nodeId"], resolve(b, snap)["nodeId"]
        if ra != rb:
            moves[(ra, rb)] += 1
            if ra is None:
                newly_placed += 1
            if rb is None:
                lost += 1
        if r["node_id"] and (r["node_id"] not in b.nodes or not b.active(r["node_id"])):
            orphaned.append({"bookId": r["book_id"], "name": r["name"], "nodeId": r["node_id"], "path": a.path(r["node_id"]),
                             "priority": r["priority_score"]})
    orphaned.sort(key=lambda x: -(x["priority"] or 0))
    move_list = [{"from": f, "fromPath": a.path(f) if f else None, "to": t, "toPath": b.path(t) if t else None, "books": k}
                 for (f, t), k in moves.most_common()]
    m2 = _m2_effect(engine, tenant, a, b)
    no_tsoft = [{"nodeId": n, "path": b.path(n)} for n in b.nodes
                if b.active(n) and b.nodes[n]["level"] in ("alt", "altalt") and not b.ext_of(n, "tsoft")]
    return {"draft": dr, "inForce": live, "added": [{"nodeId": n, "path": b.path(n)} for n in added],
            "removed": [{"nodeId": n, "path": a.path(n)} for n in removed],
            "renamed": [{"nodeId": n, "from": a.nodes[n]["name"], "to": b.nodes[n]["name"]} for n in renamed],
            "moved": [{"nodeId": n, "fromPath": a.path(n), "toPath": b.path(n)} for n in moved],
            "mappingChanges": map_changed, "bookMoves": move_list,
            "books": {"total": len(rows), "moved": sum(moves.values()), "newlyPlaced": newly_placed, "lost": lost},
            "orphanedApproved": orphaned, "m2": m2, "withoutTsoft": no_tsoft}


def _m2_effect(engine: sa.engine.Engine, tenant: str, a: TreeCtx, b: TreeCtx) -> list[dict[str, Any]]:
    """M2 kural tablosunda (yürürlükte) Kitaplık/marka kuralı olup ağaçtaki yeri değişen kategoriler."""
    try:
        from semantic_bridge import editorial_assign as M2

        M2.ensure(engine)
        active = (M2.rule_versions(engine, tenant).get("active") or {}).get("rules") or []
    except Exception as e:  # noqa: BLE001
        log.info("kategori etkisi: M2 kuralları okunamadı: %s", e)
        return []
    out = []
    for r in active:
        system = "crm_kitaplik" if r.get("kind") == "kitaplik" else "marka"
        ext = str(r.get("id") or "").upper()
        pa = sorted(a.path(n) or "" for n in a.by_ext.get(system, {}).get(ext, []))
        pb = sorted(b.path(n) or "" for n in b.by_ext.get(system, {}).get(ext, []) if b.active(n))
        if pa != pb:
            out.append({"kind": r.get("kind"), "id": ext, "name": r.get("name"), "primary": r.get("primary"),
                        "before": pa, "after": pb})
    return out


def m2_node_for(engine: sa.engine.Engine, tenant: str, *, kitaplik_id: Optional[str] = None,
                marka_id: Optional[str] = None) -> Optional[dict[str, Any]]:
    """M2 bağlantı noktası: CRM Kitaplık (yoksa marka) → yürürlükteki ağaçtaki düğüm {id, path}. Birden çok düğüme
    eşlenmişse marka ile daraltılır; yine birden çoksa None (M2 bugünkü Kitaplık/marka kuralında kalır)."""
    ctx = tree_ctx(engine, in_force(engine, tenant))
    if ctx.empty:
        return None
    book = {"kitaplik": {"id": kitaplik_id.upper()} if kitaplik_id else None,
            "marka": {"id": marka_id.upper()} if marka_id else None}
    r = resolve(ctx, book)
    if r["nodeId"] is None and not kitaplik_id and marka_id:
        hits = ctx.start_nodes(book)
        if len(hits) == 1:
            return {"id": hits[0], "path": ctx.path(hits[0])}
        return None
    return {"id": r["nodeId"], "path": ctx.path(r["nodeId"])} if r["nodeId"] else None


# ================================================================================ kurallar


def rules(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = {r["rule_key"]: r for r in c.execute(sa.select(RULES).where(RULES.c.tenant_id == tenant)).mappings()}
    out = []
    for key, d in RULE_DEFS.items():
        r = rows.get(key)
        out.append({"key": key, "label": d["label"], "help": d["help"], "field": d["field"],
                    "enabled": bool(r["enabled"]) if r else True,
                    "params": {**d["params"], **(loads(r["params_json"], {}) if r else {})},
                    "updatedBy": r["updated_by"] if r else None, "updatedAt": iso(r["updated_at"]) if r else None})
    return out


def update_rule(engine: sa.engine.Engine, tenant: str, actor: str, key: str, body: dict[str, Any]) -> dict[str, Any]:
    if key not in RULE_DEFS:
        raise CategoryError("Bilinmeyen kural.", 404)
    cur = next(r for r in rules(engine, tenant) if r["key"] == key)
    params = dict(cur["params"])
    for k, v in (body.get("params") or {}).items():
        if k not in RULE_DEFS[key]["params"]:
            raise CategoryError(f"«{k}» bu kuralın parametresi değil.")
        try:
            params[k] = type(RULE_DEFS[key]["params"][k])(v)
        except (TypeError, ValueError):
            raise CategoryError(f"«{k}» için geçerli bir değer yazın.") from None
    enabled = bool(body["enabled"]) if "enabled" in body else cur["enabled"]
    with engine.begin() as c:
        c.execute(RULES.delete().where(RULES.c.tenant_id == tenant, RULES.c.rule_key == key))
        c.execute(RULES.insert().values(tenant_id=tenant, rule_key=key, label=RULE_DEFS[key]["label"], enabled=enabled,
                                        params_json=dumps(params), updated_by=actor[:120], updated_at=now()))
    return next(r for r in rules(engine, tenant) if r["key"] == key)


def evaluate(book: dict[str, Any], cfg: dict[str, dict[str, Any]], ctx: TreeCtx, audience: dict[str, str],
             resolved: Optional[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    """Bir kitabın açık bulguları: [(kural, ayrıntı)]. Yalnız açık kurallar."""
    out: list[tuple[str, dict[str, Any]]] = []

    def on(k: str) -> bool:
        return cfg.get(k, {}).get("enabled", True)

    hk = book.get("hedefKitle") or {}
    labels = {fold(v): v for v in audience.values()}
    root = book.get("webRoot")
    if on("hedef_kitle_web") and root and fold(root) in labels and hk.get("label") and fold(root) != fold(hk["label"]):
        out.append(("hedef_kitle_web", {"hedefKitle": hk["label"], "webKategori": book.get("web"), "webRoot": root}))
    if on("yas_hedef_kitle"):
        age = book.get("yas") or {}
        lim = int(cfg.get("yas_hedef_kitle", {}).get("params", {}).get("yetiskin_yas", 18))
        a, b = age.get("bas"), age.get("bit")
        adult = labels.get(fold("Yetişkin"))
        why = None
        if a is not None and b is not None and a > b:
            why = f"Başlangıç yaşı ({a}) bitişten ({b}) büyük."
        elif hk.get("label") and adult and fold(hk["label"]) == fold(adult) and b is not None and b < lim:
            why = f"Yetişkin kitabın bitiş yaşı {b} (< {lim})."
        elif hk.get("label") and adult and fold(hk["label"]) != fold(adult) and a is not None and a >= lim:
            why = f"{hk['label']} kitabının başlangıç yaşı {a} (≥ {lim})."
        if why:
            out.append(("yas_hedef_kitle", {"yas": age, "hedefKitle": hk.get("label"), "neden": why}))
    if on("kitaplik_bos") and not book.get("kitaplik"):
        out.append(("kitaplik_bos", {}))
    if on("tur_bos") and not book.get("tur") and not book.get("turMetni"):
        out.append(("tur_bos", {}))
    if on("ozet_bos") and not book.get("ozetVar"):
        out.append(("ozet_bos", {}))
    if on("urun_kategorisi_yok") and not book.get("urunkategorisi"):
        out.append(("urun_kategorisi_yok", {}))
    if not ctx.empty and resolved is not None:
        if on("agacta_karsiligi_yok") and resolved["nodeId"] is None:
            out.append(("agacta_karsiligi_yok", {"neden": resolved["reason"],
                                                 "adaylar": [ctx.path(n) for n in resolved["candidates"]]}))
        nid = resolved["nodeId"]
        ts = (book.get("tsoft") or {}).get("categoryId")
        if on("tsoft_kategori") and nid and ts:
            allowed = {x for n in (nid, *ctx.ancestors(nid)) for x in ctx.ext_of(n, "tsoft")}
            if allowed and ts not in allowed:
                out.append(("tsoft_kategori", {"tsoft": ts, "tsoftAd": (book.get("tsoft") or {}).get("categoryName"),
                                               "beklenen": sorted(allowed), "dugum": ctx.path(nid)}))
    return out


# ================================================================================ eşitleme (kaynaklar → profiller)


def all_snapshots(engine: sa.engine.Engine, tenant: str, active_only: bool = True) -> list[dict[str, Any]]:
    q = sa.select(PROFILES.c.crm_snapshot_json).where(PROFILES.c.tenant_id == tenant)
    if active_only:
        q = q.where(PROFILES.c.active.is_(True))
    with engine.connect() as c:
        return [loads(r[0], {}) for r in c.execute(q)]


def current_values(book: dict[str, Any], resolved: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Profil alanlarının CRM'deki bugünkü değeri."""
    age = book.get("yas") or {}
    yas = None
    if age.get("bas") is not None or age.get("bit") is not None:
        yas = f"{age.get('bas') if age.get('bas') is not None else ''}-{age.get('bit') if age.get('bit') is not None else ''}"
    tur = [x["name"] for x in book.get("tur") or []]
    if not tur and book.get("turMetni"):
        from semantic_bridge.categories_sources import split_text

        tur = split_text(book["turMetni"])
    return {"kategori": (resolved or {}).get("nodeId"), "tur": tur,
            "hedef_kitle": (book.get("hedefKitle") or {}).get("label"), "yas": yas,
            "tema": [x["name"] for x in book.get("tema") or []], "etiket": [x["name"] for x in book.get("anahtarkelime") or []]}


def apply_sync(engine: sa.engine.Engine, tenant: str, crm: dict[str, Any], priority: Optional[dict[str, Any]],
               tsoft: Optional[dict[str, Any]], actor: str = "sistem") -> dict[str, Any]:
    """Kaynak okumasını profillere yazar: her aktif kitabın `crm_snapshot_json`'u, öncelik puanı, türeyen düğümü,
    alanların mevcut değeri; artık aktif olmayan kitap `active=false`. Sonra tutarsızlık kuralları yeniden koşar.
    Onaylanmış ya da önerilmiş değerlere dokunulmaz."""
    ensure(engine)
    books: dict[str, dict[str, Any]] = crm["books"]
    by_code = (priority or {}).get("byCode") or {}
    tprod = (tsoft or {}).get("products") or {}
    ctx = tree_ctx(engine, in_force(engine, tenant))
    cfg = {r["key"]: r for r in rules(engine, tenant)}
    audience = (crm.get("labels") or {}).get("hedefKitle") or {}
    ts = now()
    with engine.connect() as c:
        existing = {r["book_id"]: dict(r) for r in c.execute(
            sa.select(PROFILES.c.book_id, PROFILES.c.fields_json, PROFILES.c.status, PROFILES.c.priority_score)
            .where(PROFILES.c.tenant_id == tenant)).mappings()}
    inserts, updates, findings = [], [], {}
    placed = 0
    for bid, b in books.items():
        b["tsoft"] = tprod.get(b.get("ean") or "") if b.get("ean") else None
        res = resolve(ctx, b)
        placed += int(res["nodeId"] is not None)
        cur = current_values(b, res)
        prev = existing.get(bid)
        fields = loads(prev["fields_json"], {}) if prev else {}
        for f in FIELDS:
            fields.setdefault(f, {"state": "yok"})
            fields[f]["current"] = cur[f]
        score = float(by_code.get(b.get("stok") or "", 0.0)) if priority is not None else float((prev or {}).get("priority_score") or 0)
        found = evaluate(b, cfg, ctx, audience, res)
        findings[bid] = found
        row = {"stock_code": (b.get("stok") or "")[:60] or None, "isbn": (b.get("isbn") or "")[:40] or None,
               "ean": (b.get("ean") or "")[:20] or None, "name": (b.get("ad") or "")[:400] or None,
               "author": (b.get("yazar") or "")[:400] or None,
               "brand_id": (b.get("marka") or {}).get("id"), "brand_name": ((b.get("marka") or {}).get("name") or "")[:200] or None,
               "kitaplik_id": (b.get("kitaplik") or {}).get("id"),
               "kitaplik_name": ((b.get("kitaplik") or {}).get("name") or "")[:200] or None,
               "editor_id": (b.get("editor") or {}).get("id"), "director_id": (b.get("yonetmen") or {}).get("id"),
               "active": True, "fields_json": dumps(fields), "crm_snapshot_json": dumps(b), "priority_score": score,
               "resolved_node_id": res["nodeId"], "findings": len(found), "crm_created_at": (b.get("olusturma") or "")[:25] or None,
               "synced_at": ts}
        if prev:
            updates.append({"b_id": bid, **row})
        else:
            inserts.append({"tenant_id": tenant, "book_id": bid, "status": "yok", **row})
    gone = [b for b in existing if b not in books]
    with engine.begin() as c:
        if inserts:
            for i in range(0, len(inserts), 500):
                c.execute(PROFILES.insert(), inserts[i:i + 500])
        if updates:
            stmt = PROFILES.update().where(PROFILES.c.tenant_id == tenant, PROFILES.c.book_id == sa.bindparam("b_id"))
            for i in range(0, len(updates), 500):
                c.execute(stmt, updates[i:i + 500])
        for i in range(0, len(gone), 500):
            c.execute(PROFILES.update().where(PROFILES.c.tenant_id == tenant, PROFILES.c.book_id.in_(gone[i:i + 500]))
                      .values(active=False, synced_at=ts))
        meta_set(engine, tenant, "vocab", crm.get("vocab") or {}, conn=c)
        meta_set(engine, tenant, "labels", crm.get("labels") or {}, conn=c)
        if tsoft is not None:
            meta_set(engine, tenant, "tsoft", {"categories": tsoft.get("categories") or {}, "syncedAt": tsoft.get("syncedAt"),
                                               "products": len(tprod)}, conn=c)
        if priority is not None:
            meta_set(engine, tenant, "priority", {k: v for k, v in priority.items() if k != "byCode"} | {"codes": len(by_code)}, conn=c)
    fstat = _write_findings(engine, tenant, findings, gone)
    _sync_tags(engine, tenant, crm)
    return {"books": len(books), "new": len(inserts), "updated": len(updates), "inactive": len(gone),
            "findings": fstat, "placed": placed, "at": iso(ts)}


def _write_findings(engine: sa.engine.Engine, tenant: str, found: dict[str, list[tuple[str, dict[str, Any]]]],
                    gone: list[str]) -> dict[str, int]:
    """Açık bulguyu tazeler; artık görülmeyen açık bulgu «düzeltildi» olur, «yoksay» kararı korunur. Aktif olmayan
    kitabın açık bulgusu da kapanır."""
    ts = now()
    with engine.connect() as c:
        prev = {(r["book_id"], r["rule_key"]): dict(r) for r in c.execute(
            sa.select(FINDINGS.c.id, FINDINGS.c.book_id, FINDINGS.c.rule_key, FINDINGS.c.status)
            .where(FINDINGS.c.tenant_id == tenant)).mappings()}
    seen: set[tuple[str, str]] = set()
    ins, upd = [], []
    for bid, items in found.items():
        for key, detail in items:
            k = (bid, key)
            seen.add(k)
            p = prev.get(k)
            if p is None:
                ins.append({"id": new_id(), "tenant_id": tenant, "book_id": bid, "rule_key": key, "detail_json": dumps(detail),
                            "status": "acik", "first_seen": ts, "last_seen": ts})
            else:
                upd.append({"f_id": p["id"], "detail_json": dumps(detail), "last_seen": ts,
                            "status": "yoksay" if p["status"] == "yoksay" else "acik",
                            "closed_at": None})
    closed = [p["id"] for k, p in prev.items() if k not in seen and p["status"] == "acik"]
    with engine.begin() as c:
        for i in range(0, len(ins), 500):
            c.execute(FINDINGS.insert(), ins[i:i + 500])
        if upd:
            stmt = FINDINGS.update().where(FINDINGS.c.id == sa.bindparam("f_id"))
            for i in range(0, len(upd), 500):
                c.execute(stmt, upd[i:i + 500])
        for i in range(0, len(closed), 500):
            c.execute(FINDINGS.update().where(FINDINGS.c.id.in_(closed[i:i + 500])).values(status="duzeltildi", closed_at=ts))
    return {"new": len(ins), "open": len(ins) + sum(1 for u in upd if u["status"] == "acik"), "closed": len(closed)}


def _sync_tags(engine: sa.engine.Engine, tenant: str, crm: dict[str, Any]) -> None:
    """CRM anahtar kelime sözlüğü → etiket sözlüğü (kaynak `crm_anahtarkelime`). Elle onaylanan / önerilen etiketlere
    dokunulmaz."""
    vocab = (crm.get("vocab") or {}).get("anahtarkelime") or {}
    uses: Counter = Counter()
    for b in crm["books"].values():
        for x in b.get("anahtarkelime") or []:
            uses[x["id"]] += 1
    with engine.connect() as c:
        have = {r["tag"]: r for r in c.execute(sa.select(TAGS.c.tag, TAGS.c.source, TAGS.c.status)
                                              .where(TAGS.c.tenant_id == tenant)).mappings()}
    ins, upd = [], []
    seen: set[str] = set()
    for vid, v in vocab.items():
        tag = (v.get("name") or "").strip()[:200]
        if not tag or tag == "—" or fold(tag) in seen:
            continue
        seen.add(fold(tag))
        if tag in have:
            if have[tag]["source"] == "crm_anahtarkelime":
                upd.append({"t_tag": tag, "books": uses.get(vid, 0), "crm_id": vid,
                            "status": "aktif" if v.get("active") else "pasif"})
        else:
            ins.append({"tenant_id": tenant, "tag": tag, "source": "crm_anahtarkelime",
                        "status": "aktif" if v.get("active") else "pasif", "crm_id": vid, "books": uses.get(vid, 0),
                        "created_by": "sistem", "created_at": now()})
    with engine.begin() as c:
        for i in range(0, len(ins), 500):
            c.execute(TAGS.insert(), ins[i:i + 500])
        if upd:
            stmt = TAGS.update().where(TAGS.c.tenant_id == tenant, TAGS.c.tag == sa.bindparam("t_tag"))
            for i in range(0, len(upd), 500):
                c.execute(stmt, upd[i:i + 500])


def reresolve(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    """Ağaç yürürlüğe girince: kaynak okumadan, kayıtlı anlık görüntülerle düğüm çözümü ve kuralları yeniden koşar."""
    ctx = tree_ctx(engine, in_force(engine, tenant))
    cfg = {r["key"]: r for r in rules(engine, tenant)}
    audience = (meta_get(engine, tenant, "labels", {}) or {}).get("hedefKitle") or {}
    with engine.connect() as c:
        rows = c.execute(sa.select(PROFILES.c.book_id, PROFILES.c.crm_snapshot_json, PROFILES.c.fields_json)
                         .where(PROFILES.c.tenant_id == tenant, PROFILES.c.active.is_(True))).mappings().all()
    found, upd = {}, []
    for r in rows:
        b = loads(r["crm_snapshot_json"], {})
        res = resolve(ctx, b)
        fields = loads(r["fields_json"], {})
        fields.setdefault("kategori", {"state": "yok"})["current"] = res["nodeId"]
        f = evaluate(b, cfg, ctx, audience, res)
        found[r["book_id"]] = f
        upd.append({"b_id": r["book_id"], "resolved_node_id": res["nodeId"], "findings": len(f), "fields_json": dumps(fields)})
    with engine.begin() as c:
        if upd:
            stmt = PROFILES.update().where(PROFILES.c.tenant_id == tenant, PROFILES.c.book_id == sa.bindparam("b_id"))
            for i in range(0, len(upd), 500):
                c.execute(stmt, upd[i:i + 500])
    return {"books": len(rows), "findings": _write_findings(engine, tenant, found, [])}


# ================================================================================ profiller


def _status_of(fields: dict[str, Any]) -> str:
    proposed = {f: v for f, v in fields.items() if v.get("state") not in (None, "yok")}
    if not proposed:
        return "yok"
    decided = {f: v for f, v in proposed.items() if v.get("state") in DECIDED}
    if not decided:
        return "taslak"
    if len(decided) < len(proposed):
        return "kismi"
    k = fields.get("kategori") or {}
    if k.get("state") in ("kabul", "duzeltme"):
        return "onayli"
    if all(v.get("state") == "ret" for v in decided.values()):
        return "red"
    return "kismi"


def _row_out(r: dict[str, Any], ctx: Optional[TreeCtx] = None) -> dict[str, Any]:
    fields = loads(r.get("fields_json"), {})
    out = {"bookId": r["book_id"], "stockCode": r["stock_code"], "isbn": r.get("isbn"), "name": r["name"],
           "author": r.get("author"), "brand": r.get("brand_name"), "kitaplik": r.get("kitaplik_name"),
           "status": r["status"], "statusLabel": PROFILE_STATUS.get(r["status"], r["status"]),
           "priority": r.get("priority_score") or 0, "findings": r.get("findings") or 0, "nodeId": r.get("node_id"),
           "resolvedNodeId": r.get("resolved_node_id"), "proposedAt": iso(r.get("proposed_at")),
           "updatedAt": iso(r.get("updated_at")), "updatedBy": r.get("updated_by"),
           "pending": sum(1 for v in fields.values() if v.get("state") == "oneri"),
           "lowConfidence": sum(1 for v in fields.values() if v.get("state") == "oneri" and v.get("confident") is False)}
    if ctx is not None:
        out["nodePath"] = ctx.path(r.get("node_id") or r.get("resolved_node_id"))
        k = fields.get("kategori") or {}
        out["proposedPath"] = ctx.path(k.get("proposed")) if k.get("state") == "oneri" else None
    return out


def owner_ids(me: Optional[dict[str, Any]]) -> Optional[str]:
    return (me or {}).get("id")


def list_books(engine: sa.engine.Engine, tenant: str, *, q: str = "", owner: Optional[str] = None,
               status: str = "", brand: str = "", kitaplik: str = "", selling: str = "", finding: str = "",
               node: str = "", order: str = "priority", page: int = 0, page_size: int = 50) -> dict[str, Any]:
    """Onay kuyruğu. Bütün katalog; önceliklendirme sıralamayla (son N ay net adet), kesme yok — sayfalama yalnız
    görüntü içindir, toplam her zaman yazılır."""
    P = PROFILES.c
    stmt = sa.select(PROFILES).where(P.tenant_id == tenant, P.active.is_(True))
    if owner:
        stmt = stmt.where(sa.or_(P.editor_id == owner, P.director_id == owner))
    if status:
        stmt = stmt.where(P.status.in_(status.split(",")))
    if brand:
        stmt = stmt.where(P.brand_id == brand.upper())
    if kitaplik == "bos":
        stmt = stmt.where(P.kitaplik_id.is_(None))
    elif kitaplik:
        stmt = stmt.where(P.kitaplik_id == kitaplik.upper())
    if selling == "1":
        stmt = stmt.where(P.priority_score > 0)
    elif selling == "0":
        stmt = stmt.where(P.priority_score <= 0)
    if finding:
        sub = sa.select(FINDINGS.c.book_id).where(FINDINGS.c.tenant_id == tenant, FINDINGS.c.status == "acik")
        if finding != "*":
            sub = sub.where(FINDINGS.c.rule_key == finding)
        stmt = stmt.where(P.book_id.in_(sub))
    if node:
        ctx = tree_ctx(engine, in_force(engine, tenant))
        ids = [node, *ctx.descendants(node)]
        stmt = stmt.where(sa.or_(P.node_id.in_(ids), sa.and_(P.node_id.is_(None), P.resolved_node_id.in_(ids))))
    text = (q or "").strip()
    if text:
        like = f"%{text.replace('%', '').replace('_', '')[:80]}%"
        stmt = stmt.where(sa.or_(P.name.ilike(like), P.stock_code.ilike(like), P.isbn.ilike(like), P.author.ilike(like)))
    order_by = {"name": [P.name.asc()], "updated": [P.updated_at.desc().nullslast(), P.name.asc()],
                "findings": [P.findings.desc(), P.priority_score.desc()]}.get(order, [P.priority_score.desc(), P.name.asc()])
    with engine.connect() as c:
        total = c.execute(sa.select(sa.func.count()).select_from(stmt.subquery())).scalar() or 0
        rows = c.execute(stmt.order_by(*order_by).offset(max(0, page) * page_size).limit(page_size)).mappings().all()
    ctx = tree_ctx(engine, in_force(engine, tenant))
    return {"items": [_row_out(dict(r), ctx) for r in rows], "total": total, "page": page, "pageSize": page_size}


def get_profile(engine: sa.engine.Engine, tenant: str, book_id: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = c.execute(sa.select(PROFILES).where(PROFILES.c.tenant_id == tenant, PROFILES.c.book_id == book_id.upper())).mappings().first()
    if not r:
        raise CategoryError("Kitap bulunamadı ya da CRM kartları henüz okunmadı.", 404)
    return dict(r)


def book_detail(engine: sa.engine.Engine, tenant: str, book_id: str) -> dict[str, Any]:
    r = get_profile(engine, tenant, book_id)
    ctx = tree_ctx(engine, in_force(engine, tenant))
    snap = loads(r["crm_snapshot_json"], {})
    fields = loads(r["fields_json"], {})
    res = resolve(ctx, snap)
    for f, v in fields.items():
        if FIELDS.get(f, {}).get("kind") == "node":
            for k in ("current", "proposed", "value"):
                if v.get(k):
                    v[k + "Path"] = ctx.path(v[k])
            for alt in v.get("alternatives") or []:
                alt["path"] = ctx.path(alt.get("nodeId"))
    with engine.connect() as c:
        events = [{"field": e["field"], "old": loads(e["old"], e["old"]), "new": loads(e["new"], e["new"]),
                   "action": e["action"], "user": e["user"], "at": iso(e["at"]), "detail": loads(e["detail_json"], None)}
                  for e in c.execute(sa.select(EVENTS).where(EVENTS.c.tenant_id == tenant, EVENTS.c.book_id == r["book_id"])
                                     .order_by(EVENTS.c.at.desc())).mappings()]
        finds = [_finding_out(dict(f)) for f in c.execute(sa.select(FINDINGS).where(
            FINDINGS.c.tenant_id == tenant, FINDINGS.c.book_id == r["book_id"]).order_by(FINDINGS.c.status)).mappings()]
    return {**_row_out(r, ctx), "fields": fields, "fieldDefs": FIELDS, "crm": snap, "resolution": {
        **res, "path": ctx.path(res["nodeId"]), "candidatePaths": [ctx.path(n) for n in res["candidates"]]},
        "events": events, "findingsList": finds, "tree": ctx.tree,
        # Öncelik puanının hesaplandığı Logo penceresi (son eşitlemedeki; ayar sonradan değişse de puan bununla).
        "priorityWindow": {k: (meta_get(engine, tenant, "priority", {}) or {}).get(k) for k in ("start", "end", "months")}}


def _log(c: Any, tenant: str, book_id: str, field: str, old: Any, new: Any, action: str, user: str,
         detail: Any = None) -> None:
    c.execute(EVENTS.insert().values(id=new_id(), tenant_id=tenant, book_id=book_id, field=field, old=dumps(old),
                                     new=dumps(new), action=action, user=(user or "sistem")[:120], at=now(),
                                     detail_json=dumps(detail) if detail is not None else None))


def store_proposal(engine: sa.engine.Engine, tenant: str, book_id: str, proposals: dict[str, dict[str, Any]],
                   actor: str, *, reset: bool = False, call_ids: Optional[list[str]] = None) -> dict[str, Any]:
    """Önerileri yazar. Karar verilmiş alan (kabul/düzeltme/ret) `reset` olmadıkça değişmez."""
    r = get_profile(engine, tenant, book_id)
    fields = loads(r["fields_json"], {})
    ts = now()
    with engine.begin() as c:
        for f, p in proposals.items():
            if f not in FIELDS:
                continue
            cur = fields.get(f) or {"state": "yok"}
            if cur.get("state") in DECIDED and not reset:
                continue
            if cur.get("state") in DECIDED and reset:
                _log(c, tenant, r["book_id"], f, cur.get("value"), None, "sifirla", actor)
            entry = {"current": cur.get("current"), **{k: v for k, v in p.items() if k != "current"}, "state": "oneri",
                     "proposedAt": iso(ts), "proposedBy": actor}
            fields[f] = entry
            _log(c, tenant, r["book_id"], f, cur.get("current"), p.get("proposed"), "oneri", actor,
                 {"kaynak": p.get("source"), "olasilik": p.get("probability"), "emin": p.get("confident"),
                  "yontem": p.get("method")})
        status = _status_of(fields)
        c.execute(PROFILES.update().where(PROFILES.c.tenant_id == tenant, PROFILES.c.book_id == r["book_id"]).values(
            fields_json=dumps(fields), status=status, proposed_at=ts,
            model_call_ids=dumps(loads(r.get("model_call_ids"), []) + call_ids) if call_ids else r.get("model_call_ids")))
    return book_detail(engine, tenant, r["book_id"])


def can_decide(row: dict[str, Any], me_crm_id: Optional[str], everyone: bool) -> bool:
    """Editör kendi kitabını (kartın editörü ya da yayın yönetmeni), `herkesinki` yetkisi olan herkesinkini onaylar."""
    if everyone:
        return True
    return bool(me_crm_id) and me_crm_id.upper() in {(row.get("editor_id") or "").upper(), (row.get("director_id") or "").upper()}


def _valid_value(engine: sa.engine.Engine, tenant: str, field: str, value: Any, ctx: TreeCtx) -> Any:
    kind = FIELDS[field]["kind"]
    if kind == "node":
        if not isinstance(value, str) or not ctx.active(value):
            raise CategoryError("Kategori yürürlükteki ağacın etkin bir düğümü olmalı.")
        return value
    if kind == "many":
        if not isinstance(value, list):
            raise CategoryError(f"{FIELDS[field]['label']} için liste bekleniyordu.")
        vals = [" ".join(str(x).split())[:200] for x in value if str(x).strip()]
        allowed = vocabulary(engine, tenant, field)
        if allowed:
            by = {fold(a): a for a in allowed}
            unknown = [v for v in vals if fold(v) not in by]
            if unknown and field != "etiket":
                raise CategoryError(f"{FIELDS[field]['label']} sözlükte yok: {', '.join(unknown)}")
            vals = [by.get(fold(v), v) for v in vals]
        return list(dict.fromkeys(vals))
    s = " ".join(str(value or "").split())[:200]
    if field == "hedef_kitle":
        labels = list(((meta_get(engine, tenant, "labels", {}) or {}).get("hedefKitle") or {}).values())
        if labels and fold(s) not in {fold(x) for x in labels}:
            raise CategoryError("Hedef kitle CRM'in seçeneklerinden biri olmalı.")
    if field == "yas" and s:
        import re as _re

        m = _re.match(r"^(\d{1,2})?\s*-\s*(\d{1,2})?$", s)
        if not m or not (m.group(1) or m.group(2)):
            raise CategoryError("Yaş aralığı «6-10» biçiminde olmalı.")
    return s or None


def vocabulary(engine: sa.engine.Engine, tenant: str, field: str) -> Optional[list[str]]:
    """Kontrollü sözlük: tür ve tema CRM sözlüğünden, etiket etiket sözlüğünden (aktif + onaylı)."""
    if field in ("tur", "tema"):
        v = (meta_get(engine, tenant, "vocab", {}) or {}).get(field) or {}
        return sorted({x["name"] for x in v.values() if x.get("active") and x.get("name") and x["name"] != "—"}, key=fold)
    if field == "etiket":
        with engine.connect() as c:
            return [r[0] for r in c.execute(sa.select(TAGS.c.tag).where(TAGS.c.tenant_id == tenant,
                                                                        TAGS.c.status == "aktif").order_by(TAGS.c.tag))]
    return None


def decide(engine: sa.engine.Engine, tenant: str, actor: str, book_id: str, body: dict[str, Any], *,
           me_crm_id: Optional[str], everyone: bool) -> dict[str, Any]:
    """Alan alan karar. body: {fields: {alan: {action: kabul|duzeltme|ret, value?}}, all?: "kabul"}.
    `all: "kabul"` bekleyen bütün önerileri olduğu gibi kabul eder (emin olunmayanlar dahil değil)."""
    r = get_profile(engine, tenant, book_id)
    if not can_decide(r, me_crm_id, everyone):
        raise CategoryError("Bu kitabın editörü ya da yayın yönetmeni değilsiniz; başkalarının kitabı için "
                            "«herkesin kitabı» yetkisi gerekir.", 403)
    fields = loads(r["fields_json"], {})
    ctx = tree_ctx(engine, in_force(engine, tenant))
    todo: dict[str, dict[str, Any]] = {}
    for f, d in (body.get("fields") or {}).items():
        if f not in FIELDS or not isinstance(d, dict):
            raise CategoryError(f"Bilinmeyen alan: {f}")
        todo[f] = d
    if body.get("all") == "kabul":
        for f, v in fields.items():
            if f not in todo and v.get("state") == "oneri" and v.get("proposed") not in (None, [], "") and v.get("confident") is not False:
                todo[f] = {"action": "kabul"}
    if not todo:
        raise CategoryError("Karar verilecek alan yok.")
    ts = now()
    changed: dict[str, Any] = {}
    new_tags: list[str] = []
    with engine.begin() as c:
        for f, d in todo.items():
            action = str(d.get("action") or "")
            if action not in DECIDED:
                raise CategoryError(f"{FIELDS[f]['label']}: karar kabul, düzeltme ya da ret olmalı.")
            cur = fields.get(f) or {"state": "yok"}
            if action == "kabul":
                if cur.get("proposed") in (None, [], ""):
                    raise CategoryError(f"{FIELDS[f]['label']}: kabul edilecek öneri yok.")
                value = _valid_value(engine, tenant, f, cur["proposed"], ctx)
            elif action == "duzeltme":
                value = _valid_value(engine, tenant, f, d.get("value"), ctx)
                if value in (None, [], ""):
                    raise CategoryError(f"{FIELDS[f]['label']}: düzeltilen değer boş olamaz; öneriyi reddedin.")
            else:
                value = None
            if f == "etiket" and value:
                known = {fold(x) for x in (vocabulary(engine, tenant, "etiket") or [])}
                new_tags += [x for x in value if fold(x) not in known]
            old = cur.get("value") if cur.get("state") in DECIDED else cur.get("current")
            cur.update({"state": action, "value": value, "by": actor, "at": iso(ts), "note": (str(d.get("note") or "")[:500] or None)})
            fields[f] = cur
            changed[f] = {"karar": action, "deger": value}
            _log(c, tenant, r["book_id"], f, old, value, action, actor, {"oneri": cur.get("proposed")})
        status = _status_of(fields)
        k = fields.get("kategori") or {}
        node_id = k.get("value") if k.get("state") in ("kabul", "duzeltme") else None
        c.execute(PROFILES.update().where(PROFILES.c.tenant_id == tenant, PROFILES.c.book_id == r["book_id"]).values(
            fields_json=dumps(fields), status=status, node_id=node_id, updated_by=actor[:120], updated_at=ts))
        for t in dict.fromkeys(new_tags):
            if not c.execute(sa.select(TAGS.c.tag).where(TAGS.c.tenant_id == tenant, TAGS.c.tag == t[:200])).first():
                c.execute(TAGS.insert().values(tenant_id=tenant, tag=t[:200], source="oneri", status="oneri", books=1,
                                               created_by=actor[:120], created_at=ts))
    out = book_detail(engine, tenant, r["book_id"])
    out["changed"] = changed
    out["newTags"] = list(dict.fromkeys(new_tags))
    return out


def my_pending(engine: sa.engine.Engine, tenant: str, me_crm_id: Optional[str]) -> dict[str, Any]:
    """Kişinin (editör / yayın yönetmeni olduğu) kitaplarında kararını bekleyen öneri sayısı — Kampüs zili."""
    if not me_crm_id:
        return {"pending": 0, "books": 0}
    P = PROFILES.c
    with engine.connect() as c:
        n = c.execute(sa.select(sa.func.count()).where(
            P.tenant_id == tenant, P.active.is_(True), P.status.in_(("taslak", "kismi")),
            sa.or_(P.editor_id == me_crm_id.upper(), P.director_id == me_crm_id.upper()))).scalar() or 0
    return {"pending": n, "books": n}


# ================================================================================ bulgular


def _finding_out(r: dict[str, Any]) -> dict[str, Any]:
    d = RULE_DEFS.get(r["rule_key"], {})
    return {"id": r["id"], "bookId": r["book_id"], "rule": r["rule_key"], "ruleLabel": d.get("label", r["rule_key"]),
            "field": d.get("field"), "detail": loads(r["detail_json"], {}), "status": r["status"],
            "firstSeen": iso(r["first_seen"]), "lastSeen": iso(r["last_seen"]), "closedAt": iso(r.get("closed_at")),
            "decidedBy": r.get("decided_by"), "note": r.get("note")}


def list_findings(engine: sa.engine.Engine, tenant: str, *, rule: str = "", status: str = "acik", owner: Optional[str] = None,
                  q: str = "", page: int = 0, page_size: int = 50) -> dict[str, Any]:
    F, P = FINDINGS.c, PROFILES.c
    stmt = (sa.select(FINDINGS, P.name, P.stock_code, P.brand_name, P.kitaplik_name, P.priority_score, P.status.label("pstatus"))
            .select_from(FINDINGS.join(PROFILES, sa.and_(P.tenant_id == F.tenant_id, P.book_id == F.book_id)))
            .where(F.tenant_id == tenant, P.active.is_(True)))
    if rule:
        stmt = stmt.where(F.rule_key == rule)
    if status:
        stmt = stmt.where(F.status == status)
    if owner:
        stmt = stmt.where(sa.or_(P.editor_id == owner, P.director_id == owner))
    if q.strip():
        like = f"%{q.strip().replace('%', '')[:80]}%"
        stmt = stmt.where(sa.or_(P.name.ilike(like), P.stock_code.ilike(like)))
    with engine.connect() as c:
        total = c.execute(sa.select(sa.func.count()).select_from(stmt.subquery())).scalar() or 0
        rows = c.execute(stmt.order_by(P.priority_score.desc(), P.name).offset(max(0, page) * page_size).limit(page_size)).mappings().all()
        counts = {k: n for k, n in c.execute(sa.select(F.rule_key, sa.func.count()).select_from(
            FINDINGS.join(PROFILES, sa.and_(P.tenant_id == F.tenant_id, P.book_id == F.book_id)))
            .where(F.tenant_id == tenant, F.status == "acik", P.active.is_(True)).group_by(F.rule_key))}
    items = []
    for r in rows:
        m = dict(r)
        items.append({**_finding_out(m), "name": m["name"], "stockCode": m["stock_code"], "brand": m["brand_name"],
                      "kitaplik": m["kitaplik_name"], "priority": m["priority_score"] or 0, "profileStatus": m["pstatus"]})
    return {"items": items, "total": total, "page": page, "pageSize": page_size, "openByRule": counts,
            "rules": rules(engine, tenant)}


def set_finding_status(engine: sa.engine.Engine, tenant: str, actor: str, finding_id: str, status: str,
                       note: Optional[str]) -> dict[str, Any]:
    if status not in ("acik", "yoksay"):
        raise CategoryError("Durum «açık» ya da «yoksay» olabilir; düzeltilen bulgu kaynağı düzelince kendiliğinden kapanır.")
    with engine.begin() as c:
        r = c.execute(sa.select(FINDINGS).where(FINDINGS.c.tenant_id == tenant, FINDINGS.c.id == finding_id)).mappings().first()
        if not r:
            raise CategoryError("Bulgu bulunamadı.", 404)
        if r["status"] == "duzeltildi":
            raise CategoryError("Bu bulgu kaynağında düzelmiş; yeniden açılmaz.", 409)
        c.execute(FINDINGS.update().where(FINDINGS.c.id == finding_id).values(
            status=status, decided_by=actor[:120], note=(note or "")[:500] or None,
            closed_at=now() if status == "yoksay" else None))
        r = c.execute(sa.select(FINDINGS).where(FINDINGS.c.id == finding_id)).mappings().first()
    return _finding_out(dict(r))


def apply_findings(engine: sa.engine.Engine, tenant: str, actor: str, ids: list[str], *, me_crm_id: Optional[str],
                   everyone: bool) -> dict[str, Any]:
    """«Öneriyi uygula»: seçili bulguların kitabında, kuralın ilgili olduğu alanın bekleyen ve emin önerisini kabul
    eder. Önerisi olmayan, emin olunmayan ya da yetki dışındaki kitap atlanır ve nedeni döner."""
    with engine.connect() as c:
        rows = c.execute(sa.select(FINDINGS).where(FINDINGS.c.tenant_id == tenant, FINDINGS.c.id.in_(ids[:100000]))).mappings().all()
    applied, skipped = [], []
    for r in rows:
        field = RULE_DEFS.get(r["rule_key"], {}).get("field")
        if not field:
            skipped.append({"id": r["id"], "reason": "Bu kuralın profil alanı yok."})
            continue
        try:
            prof = get_profile(engine, tenant, r["book_id"])
        except CategoryError as e:
            skipped.append({"id": r["id"], "reason": str(e)})
            continue
        fv = loads(prof["fields_json"], {}).get(field) or {}
        if fv.get("state") != "oneri" or fv.get("proposed") in (None, [], ""):
            skipped.append({"id": r["id"], "reason": "Bekleyen Zeki AI önerisi yok; önce öneri üretin."})
            continue
        if fv.get("confident") is False:
            skipped.append({"id": r["id"], "reason": "Zeki AI bu öneriden emin değil; profil ekranında karar verin."})
            continue
        if not can_decide(prof, me_crm_id, everyone):
            skipped.append({"id": r["id"], "reason": "Kitap sizin değil."})
            continue
        try:
            decide(engine, tenant, actor, r["book_id"], {"fields": {field: {"action": "kabul"}}}, me_crm_id=me_crm_id,
                   everyone=everyone)
            applied.append({"id": r["id"], "bookId": r["book_id"], "field": field})
        except CategoryError as e:
            skipped.append({"id": r["id"], "reason": str(e)})
    return {"applied": applied, "skipped": skipped}


# ================================================================================ CRM'e işlenecek fark


def crm_diff(engine: sa.engine.Engine, tenant: str, *, owner: Optional[str] = None, q: str = "") -> dict[str, Any]:
    """Onaylı (kabul/düzeltme) alanlarla CRM'in bugünkü değeri arasındaki fark. CRM sonraki okumada aynı değeri
    gösterince satır kendiliğinden düşer. Kategori farkı, düğümün CRM eşlemeleri üzerinden yazılır (Kitaplık, ürün
    kategorisi, raf, sergilenecek); düğümün CRM karşılığı yoksa «ağaç düğümü» satırı olarak kalır."""
    P = PROFILES.c
    stmt = sa.select(PROFILES).where(P.tenant_id == tenant, P.active.is_(True), P.status.in_(("kismi", "onayli", "red")))
    if owner:
        stmt = stmt.where(sa.or_(P.editor_id == owner, P.director_id == owner))
    if q.strip():
        like = f"%{q.strip().replace('%', '')[:80]}%"
        stmt = stmt.where(sa.or_(P.name.ilike(like), P.stock_code.ilike(like)))
    ctx = tree_ctx(engine, in_force(engine, tenant))
    stale = thresholds()["staleDays"]
    ts = now()
    rows_out: list[dict[str, Any]] = []
    with engine.connect() as c:
        rows = c.execute(stmt.order_by(P.priority_score.desc(), P.name)).mappings().all()
    for r in rows:
        snap = loads(r["crm_snapshot_json"], {})
        fields = loads(r["fields_json"], {})
        base = {"bookId": r["book_id"], "stockCode": r["stock_code"], "name": r["name"], "brand": r["brand_name"],
                "priority": r["priority_score"] or 0}
        for f, v in fields.items():
            if v.get("state") not in ("kabul", "duzeltme"):
                continue
            at = v.get("at")
            try:
                age = (ts - datetime.fromisoformat(at)).days if at else None
            except ValueError:
                age = None
            meta = {"approvedBy": v.get("by"), "approvedAt": at, "ageDays": age, "stale": age is not None and age > stale}
            for d in _field_diff(f, v.get("value"), snap, ctx):
                rows_out.append({**base, **meta, "field": f, "fieldLabel": FIELDS[f]["label"], **d})
    by_field = Counter(x["field"] for x in rows_out)
    return {"items": rows_out, "total": len(rows_out), "books": len({x["bookId"] for x in rows_out}),
            "stale": sum(1 for x in rows_out if x["stale"]), "staleDays": stale, "byField": dict(by_field)}


def _field_diff(f: str, value: Any, snap: dict[str, Any], ctx: TreeCtx) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if f == "kategori":
        if not value or value not in ctx.nodes:
            return out
        chain = [value, *ctx.ancestors(value)]
        wrote = False
        crm_single = {"crm_kitaplik": ("Kitaplık", [snap["kitaplik"]] if snap.get("kitaplik") else []),
                      "crm_urunkategorisi": ("Ürün kategorisi", snap.get("urunkategorisi") or []),
                      "crm_raf": ("Raf kategorisi", snap.get("raf") or []),
                      "crm_sergilenecek": ("Sergilenecek kategori", snap.get("sergilenecek") or [])}
        for system, (label, have) in crm_single.items():
            want = next((ctx.node_maps.get(n, {}).get(system) for n in chain if ctx.node_maps.get(n, {}).get(system)), None)
            if not want:
                continue
            wrote = True
            have_ids = {x["id"] for x in have}
            want_ids = {str(m["externalId"]) for m in want}
            if system == "crm_kitaplik":
                if not have_ids & want_ids:
                    out.append({"crmField": label, "crmValue": ", ".join(x["name"] for x in have) or None,
                                "portalValue": " / ".join(m["externalName"] or m["externalId"] for m in want),
                                "action": "degistir", "note": ctx.path(value)})
            elif not have_ids & want_ids:
                out.append({"crmField": label, "crmValue": ", ".join(x["name"] for x in have) or None,
                            "portalValue": " / ".join(m["externalName"] or m["externalId"] for m in want),
                            "action": "ekle", "note": ctx.path(value)})
        if not wrote:
            out.append({"crmField": "Kategori (ağaç düğümü)", "crmValue": None, "portalValue": ctx.path(value),
                        "action": "bilgi", "note": "Düğümün CRM karşılığı eşlenmemiş; ağaçta eşleme ekleyin."})
        return out
    if f == "hedef_kitle":
        have = (snap.get("hedefKitle") or {}).get("label")
        if fold(have) != fold(value):
            out.append({"crmField": "Hedef kitle", "crmValue": have, "portalValue": value, "action": "degistir"})
        return out
    if f == "yas":
        age = snap.get("yas") or {}
        have = None if not age else f"{age.get('bas') if age.get('bas') is not None else ''}-{age.get('bit') if age.get('bit') is not None else ''}"
        if (have or "") != (value or ""):
            out.append({"crmField": "Hedef kitle yaş başlangıç / bitiş", "crmValue": have, "portalValue": value, "action": "degistir"})
        return out
    src = {"tur": ("Tür", "tur"), "tema": ("Tema", "tema"), "etiket": ("Anahtar kelime", "anahtarkelime")}.get(f)
    if src:
        have = [x["name"] for x in snap.get(src[1]) or []]
        if f == "tur" and not have and snap.get("turMetni"):
            from semantic_bridge.categories_sources import split_text

            have = split_text(snap["turMetni"])
        hf = {fold(x) for x in have}
        vf = {fold(x) for x in (value or [])}
        add = [x for x in (value or []) if fold(x) not in hf]
        rem = [x for x in have if fold(x) not in vf]
        if add:
            out.append({"crmField": src[0], "crmValue": ", ".join(have) or None, "portalValue": ", ".join(add), "action": "ekle"})
        if rem:
            out.append({"crmField": src[0], "crmValue": ", ".join(have) or None, "portalValue": ", ".join(rem), "action": "cikar"})
    return out


ACTION_LABEL = {"ekle": "Ekle", "cikar": "Çıkar", "degistir": "Değiştir", "bilgi": "Bilgi"}


def crm_diff_xlsx(diff: dict[str, Any], user: str) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.table import Table, TableStyleInfo

    wb = Workbook()
    ws = wb.active
    ws.title = "CRM'e işlenecek fark"
    ws["A1"] = "CRM'e işlenecek fark — Kategori ağacı"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = f"{datetime.now().strftime('%d.%m.%Y %H:%M')} · {user} · {diff['total']} satır, {diff['books']} kitap. Portal CRM'e yazmaz; bu liste CRM'de elle işlenir."
    head = ["Stok kodu", "Kitap", "Yayınevi", "Alan", "CRM alanı", "İşlem", "CRM'deki değer", "Onaylı değer", "Not",
            "Onaylayan", "Onay tarihi", "Gün"]
    ws.append([])
    ws.append(head)
    for x in diff["items"]:
        ws.append([x.get("stockCode"), x.get("name"), x.get("brand"), x.get("fieldLabel"), x.get("crmField"),
                   ACTION_LABEL.get(x.get("action"), x.get("action")), x.get("crmValue"), x.get("portalValue"), x.get("note"),
                   x.get("approvedBy"), (x.get("approvedAt") or "")[:10], x.get("ageDays")])
    last = ws.max_row
    if last > 4:
        ref = f"A4:{get_column_letter(len(head))}{last}"
        t = Table(displayName="CrmFark", ref=ref)
        t.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
        ws.add_table(t)
    for i, w in enumerate((16, 44, 22, 14, 22, 10, 36, 36, 36, 16, 12, 6), 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ================================================================================ etiket sözlüğü


def list_tags(engine: sa.engine.Engine, tenant: str, status: str = "oneri", q: str = "", page: int = 0,
              page_size: int = 100) -> dict[str, Any]:
    stmt = sa.select(TAGS).where(TAGS.c.tenant_id == tenant)
    if status:
        stmt = stmt.where(TAGS.c.status == status)
    if q.strip():
        stmt = stmt.where(TAGS.c.tag.ilike(f"%{q.strip()[:80]}%"))
    with engine.connect() as c:
        total = c.execute(sa.select(sa.func.count()).select_from(stmt.subquery())).scalar() or 0
        rows = c.execute(stmt.order_by(TAGS.c.books.desc(), TAGS.c.tag).offset(page * page_size).limit(page_size)).mappings().all()
        counts = dict(c.execute(sa.select(TAGS.c.status, sa.func.count()).where(TAGS.c.tenant_id == tenant).group_by(TAGS.c.status)).all())
    return {"items": [{"tag": r["tag"], "source": r["source"], "status": r["status"], "mergedInto": r["merged_into"],
                       "books": r["books"], "createdBy": r["created_by"], "createdAt": iso(r["created_at"]),
                       "decidedBy": r["decided_by"], "decidedAt": iso(r["decided_at"])} for r in rows],
            "total": total, "page": page, "pageSize": page_size, "counts": counts}


def decide_tag(engine: sa.engine.Engine, tenant: str, actor: str, tag: str, status: str,
               merged_into: Optional[str]) -> dict[str, Any]:
    if status not in ("aktif", "red", "birlesti"):
        raise CategoryError("Karar aktif, red ya da birleşti olmalı.")
    with engine.begin() as c:
        r = c.execute(sa.select(TAGS).where(TAGS.c.tenant_id == tenant, TAGS.c.tag == tag)).mappings().first()
        if not r:
            raise CategoryError("Etiket bulunamadı.", 404)
        if r["source"] == "crm_anahtarkelime":
            raise CategoryError("CRM sözlüğündeki etiket CRM'de yönetilir.", 409)
        if status == "birlesti":
            target = c.execute(sa.select(TAGS.c.tag).where(TAGS.c.tenant_id == tenant, TAGS.c.tag == (merged_into or ""),
                                                           TAGS.c.status == "aktif")).first()
            if not target:
                raise CategoryError("Birleştirilecek etiket sözlükte etkin değil.")
        c.execute(TAGS.update().where(TAGS.c.tenant_id == tenant, TAGS.c.tag == tag).values(
            status=status, source="onayli" if status == "aktif" else r["source"],
            merged_into=merged_into if status == "birlesti" else None, decided_by=actor[:120], decided_at=now()))
    return {"tag": tag, "status": status, "mergedInto": merged_into}


# ================================================================================ özet


def overview(engine: sa.engine.Engine, tenant: str, me_crm_id: Optional[str]) -> dict[str, Any]:
    """Özet ekranı: herkes için aynı kısım (`overview_ortak`) + kişinin onayını bekleyenler (`my_pending`)."""
    out = overview_ortak(engine, tenant)
    out["mine"] = my_pending(engine, tenant, me_crm_id)
    return out


def overview_ortak(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    """Özetin kişiye bağlı olmayan kısmı: bütün etkin profillerin CRM kopyası okunup sayılır (ağır kısım). `mine`
    yeri boş bırakılır (anahtar sırası `overview` ile aynı kalsın); kişiye özel sayı `my_pending` ile doldurulur.
    Köprü bunu süreç belleğinde tutar ve profil/ağaç/kural yazan her uçta düşürür (`categories_api`)."""
    P = PROFILES.c
    with engine.connect() as c:
        rows = c.execute(sa.select(PROFILES.c.status, PROFILES.c.crm_snapshot_json, PROFILES.c.priority_score,
                                   PROFILES.c.node_id, PROFILES.c.resolved_node_id)
                         .where(P.tenant_id == tenant, P.active.is_(True))).all()
        open_by_rule = dict(c.execute(sa.select(FINDINGS.c.rule_key, sa.func.count()).select_from(
            FINDINGS.join(PROFILES, sa.and_(P.tenant_id == FINDINGS.c.tenant_id, P.book_id == FINDINGS.c.book_id)))
            .where(FINDINGS.c.tenant_id == tenant, FINDINGS.c.status == "acik", P.active.is_(True))
            .group_by(FINDINGS.c.rule_key)).all())
    status = Counter()
    fill = Counter()
    selling = selling_approved = placed = 0
    links: Counter = Counter()
    for st, raw, score, node_id, resolved in rows:
        status[st] += 1
        b = loads(raw, {})
        checks = {"kitaplik": bool(b.get("kitaplik")), "tur": bool(b.get("tur") or b.get("turMetni")),
                  "web": bool(b.get("web")), "hedefKitle": bool(b.get("hedefKitle")), "yas": bool(b.get("yas")),
                  "tema": bool(b.get("tema")), "ozet": bool(b.get("ozetVar")), "urunkategorisi": bool(b.get("urunkategorisi")),
                  "anahtarkelime": bool(b.get("anahtarkelime"))}
        for k, v in checks.items():
            fill[k] += int(v)
        for k in ("tema", "urunkategorisi", "raf", "sergilenecek", "anahtarkelime", "tur"):
            links[k] += len(b.get(k) or [])
        if (score or 0) > 0:
            selling += 1
            if node_id:
                selling_approved += 1
        if node_id or resolved:
            placed += 1
    n = len(rows)
    live = in_force(engine, tenant)
    dr = draft(engine, tenant)
    sync = meta_get(engine, tenant, "sync", {}) or {}
    pr = meta_get(engine, tenant, "priority", {}) or {}
    ts = meta_get(engine, tenant, "tsoft", {}) or {}
    labels = {"kitaplik": "Kitaplık", "tur": "Tür", "web": "Web kategorisi", "hedefKitle": "Hedef kitle",
              "yas": "Yaş aralığı", "tema": "Tema", "ozet": "Arka kapak metni", "urunkategorisi": "Ürün kategorisi",
              "anahtarkelime": "Anahtar kelime"}
    diff = crm_diff(engine, tenant) if status.get("onayli") or status.get("kismi") or status.get("red") else {"total": 0, "stale": 0, "books": 0}
    return {
        "activeBooks": n, "status": {k: status.get(k, 0) for k in PROFILE_STATUS}, "statusLabels": PROFILE_STATUS,
        "fill": [{"key": k, "label": lab, "filled": fill.get(k, 0), "total": n} for k, lab in labels.items()],
        "links": dict(links), "selling": selling, "sellingApproved": selling_approved, "placed": placed,
        "findings": {"open": sum(open_by_rule.values()), "byRule": open_by_rule,
                     "labels": {k: d["label"] for k, d in RULE_DEFS.items()}},
        "tree": {"inForce": live, "draft": dr}, "sync": sync, "priority": pr,
        "tsoft": {"syncedAt": ts.get("syncedAt"), "products": ts.get("products"), "categories": len(ts.get("categories") or {})},
        "mine": None, "crmDiff": {"rows": diff["total"], "stale": diff["stale"], "books": diff["books"]},
        "thresholds": thresholds(),
    }


# ================================================================================ sözleşme (diğer modüller)


def profile_by_stock(engine: sa.engine.Engine, tenant: str, stock_code: str) -> dict[str, Any]:
    """Diğer modüllerin okuduğu profil: onaylı değerler öncelikli, yoksa CRM'den türeyen; her alanın kaynağı yazılır."""
    with engine.connect() as c:
        r = c.execute(sa.select(PROFILES).where(PROFILES.c.tenant_id == tenant, PROFILES.c.stock_code == stock_code.strip())
                      .order_by(PROFILES.c.active.desc())).mappings().first()
    if not r:
        raise CategoryError("Bu stok koduyla kitap profili yok.", 404)
    ctx = tree_ctx(engine, in_force(engine, tenant))
    fields = loads(r["fields_json"], {})
    out: dict[str, Any] = {}
    for f in FIELDS:
        v = fields.get(f) or {}
        if v.get("state") in ("kabul", "duzeltme"):
            out[f] = {"value": v.get("value"), "source": "onayli", "approvedBy": v.get("by"), "approvedAt": v.get("at")}
        else:
            out[f] = {"value": v.get("current"), "source": "crm"}
        if f == "kategori":
            out[f]["path"] = ctx.path(out[f]["value"])
    return {"bookId": r["book_id"], "stockCode": r["stock_code"], "name": r["name"], "status": r["status"],
            "active": bool(r["active"]), "priority": r["priority_score"], "fields": out,
            "tree": {"id": ctx.tree["id"], "version": ctx.tree["version"]} if ctx.tree else None}


def nodes_flat(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    ctx = tree_ctx(engine, in_force(engine, tenant))
    counts = node_counts(engine, tenant)
    items = [{**n, **counts.get(n["id"], {"books": 0, "approved": 0, "sales": 0.0})} for n in ctx.flat() if ctx.active(n["id"])]
    return {"tree": ctx.tree, "items": items}


def node_books(engine: sa.engine.Engine, tenant: str, node_id: str, *, page: int = 0, page_size: int = 100,
               include_resolved: bool = True) -> dict[str, Any]:
    ctx = tree_ctx(engine, in_force(engine, tenant))
    if node_id not in ctx.nodes:
        raise CategoryError("Düğüm yürürlükteki ağaçta yok.", 404)
    ids = [node_id, *ctx.descendants(node_id)]
    P = PROFILES.c
    cond = P.node_id.in_(ids)
    if include_resolved:
        cond = sa.or_(cond, sa.and_(P.node_id.is_(None), P.resolved_node_id.in_(ids)))
    stmt = sa.select(P.book_id, P.stock_code, P.name, P.author, P.brand_name, P.priority_score, P.node_id,
                     P.resolved_node_id, P.status).where(P.tenant_id == tenant, P.active.is_(True), cond)
    with engine.connect() as c:
        total = c.execute(sa.select(sa.func.count()).select_from(stmt.subquery())).scalar() or 0
        rows = c.execute(stmt.order_by(P.priority_score.desc(), P.name).offset(page * page_size).limit(page_size)).mappings().all()
    return {"node": {"id": node_id, "path": ctx.path(node_id)}, "total": total, "page": page, "pageSize": page_size,
            "items": [{"bookId": r["book_id"], "stockCode": r["stock_code"], "name": r["name"], "author": r["author"],
                       "brand": r["brand_name"], "priority": r["priority_score"], "status": r["status"],
                       "source": "onayli" if r["node_id"] else "crm", "nodeId": r["node_id"] or r["resolved_node_id"],
                       "path": ctx.path(r["node_id"] or r["resolved_node_id"])} for r in rows]}


def batch_candidates(engine: sa.engine.Engine, tenant: str) -> list[str]:
    """Gece önerisinin sırası: önce son okumadan beri açılan kartlar (en yeni önce), sonra öncelik puanı (son N ay net
    adet) büyükten küçüğe. Sessiz tavan yok; iş bütçesi (süre) bitince kalan sonraki geceye kalır."""
    P = PROFILES.c
    last = ((meta_get(engine, tenant, "sync", {}) or {}).get("previousAt") or "")[:19]
    with engine.connect() as c:
        rows = c.execute(sa.select(P.book_id, P.crm_created_at, P.priority_score).where(
            P.tenant_id == tenant, P.active.is_(True), P.status == "yok")).all()
    fresh = sorted((r for r in rows if last and (r.crm_created_at or "") >= last), key=lambda r: r.crm_created_at or "",
                   reverse=True)
    ids = {r.book_id for r in fresh}
    rest = sorted((r for r in rows if r.book_id not in ids), key=lambda r: -(r.priority_score or 0))
    return [r.book_id for r in fresh] + [r.book_id for r in rest]
