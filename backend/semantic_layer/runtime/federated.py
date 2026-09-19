"""Questions that need two databases at once.

Since 2026-09-16 the ERP (Logo) and the CRM live on different SQL servers, and no single statement can
read both. A question like "siparişlerin kaçının faturası kesilmemiş" is still one question, so the
model writes a *plan* instead of a statement:

    {"parts": [{"name": "crm_siparis", "source": "TIMAS_MSCRM", "sql": "SELECT ..."},
               {"name": "logo_fatura", "source": "", "sql": "SELECT ..."}],
     "links": [{"left": "crm_siparis.fatura_no", "right": "logo_fatura.fatura_no",
                "via": "NEW_SEVKIYATBASE.NEW_FATURANUMARASI=INVOICE.FICHENO"}],
     "final": "SELECT ... FROM crm_siparis s LEFT JOIN logo_fatura f ON f.fatura_no = s.fatura_no ..."}

Each part runs on its own server and reads only that server's tables. Their rows are loaded into an
in-memory database, and `final` — written for that database — combines them: a match, an absence, a
difference, a breakdown of one side by the other. One mechanism covers every shape of combined
question, and nothing is joined across the wire.

What keeps it honest is checked before anything runs (`check_plan`):
  * every part reads one source, and only catalog tables of that source;
  * `final` reads only the parts, and uses every one of them;
  * every link names two part columns that `final` actually joins on, and a relationship the catalog
    holds with its measured evidence (`cross_source` relationships written by link discovery). A
    join the catalog has not measured is refused: two key columns that merely look alike is how a
    combined answer goes silently wrong.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional

import sqlglot
from sqlglot import exp

from semantic_layer.runtime.guardrails import allowed_tables, validate_sql

_NAME = re.compile(r"^[a-z][a-z0-9_]{0,40}$")
_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.S | re.I)
_READING = re.compile(r"(?im)^\s*--\s*yorum\s*:\s*(.+?)\s*$")


@dataclass
class Part:
    name: str
    source: str
    sql: str


@dataclass
class Plan:
    parts: list[Part]
    final: str
    links: list[dict[str, str]] = field(default_factory=list)
    readings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"parts": [dict(p.__dict__) for p in self.parts], "final": self.final,
                "links": list(self.links), "readings": list(self.readings)}

    def text(self) -> str:
        """Everything the plan says, as one reviewable document (what the person is shown as SQL)."""
        lines = [f"-- yorum: {r}" for r in self.readings]
        for p in self.parts:
            lines += [f"-- parça {p.name} · kaynak {p.source or 'LOGO'}", p.sql.strip() + ";"]
        lines += ["-- birleştirme (bellekte)", self.final.strip() + ";"]
        return "\n".join(lines)


def source_of_schema(schema: Optional[str]) -> str:
    """The database a table lives in, as the catalog spells its schema: "Timas_MSCRM.dbo" → TIMAS_MSCRM;
    a schema with no database part belongs to the connection's own database (empty string)."""
    schema = schema or ""
    return schema.split(".")[0].upper() if "." in schema else ""


def parse_plan(text: str) -> Optional[Plan]:
    """The model's plan, or None when the answer is not a plan."""
    m = _JSON_BLOCK.search(text or "")
    raw = m.group(1) if m else None
    if raw is None:
        stripped = (text or "").strip()
        raw = stripped if stripped.startswith("{") else None
    if raw is None:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("parts"), list) or not isinstance(data.get("final"), str):
        return None
    parts = []
    for item in data["parts"]:
        if not isinstance(item, dict):
            return None
        source = str(item.get("source", "") or "").strip().upper()
        parts.append(Part(name=str(item.get("name", "")).strip().lower(),
                          source="" if source in ("LOGO", "DBO", "ERP") else source,
                          sql=str(item.get("sql", "")).strip().rstrip(";")))
    links = [{k: str(v) for k, v in link.items()} for link in data.get("links") or [] if isinstance(link, dict)]
    readings = [str(r) for r in data.get("readings") or [] if str(r).strip()]
    readings += [r for r in _READING.findall(text or "") if r not in readings]
    return Plan(parts=parts, final=data["final"].strip().rstrip(";"), links=links, readings=readings)


def cross_links(profiles: Iterable[Any]) -> set[tuple[str, str, str, str]]:
    """(entity, column, ref entity, ref column), both directions, for every measured cross-source link."""
    out: set[tuple[str, str, str, str]] = set()
    for p in profiles:
        for r in getattr(p, "relationships", None) or []:
            if not isinstance(r, dict) or not r.get("cross_source"):
                continue
            a = (str(p.entity).upper(), str(r.get("column", "")).upper())
            b = (str(r.get("ref_entity", "")).upper(), str(r.get("ref_column", "")).upper())
            out.add(a + b)
            out.add(b + a)
    return out


def _tables(sql: str, dialect: Optional[str]) -> list[exp.Table]:
    tree = sqlglot.parse_one(sql, read=dialect)
    ctes = {c.alias.upper() for c in tree.find_all(exp.CTE) if c.alias}
    return [t for t in tree.find_all(exp.Table) if t.name and t.name.upper() not in ctes]


def check_plan(plan: Plan, profiles: list[Any], context: dict[str, str], dialect: str = "tsql") -> list[str]:
    """Why this plan must not run; empty when it may."""
    problems: list[str] = []
    by_source: dict[str, list[Any]] = {}
    for p in profiles:
        by_source.setdefault(source_of_schema(p.schema_name), []).append(p)
    names = [p.name for p in plan.parts]
    if len(plan.parts) < 2:
        problems.append("birleşik plan en az iki parça ister; tek kaynaklı soru tek SQL ile yazılmalı")
    if len(set(names)) != len(names) or not all(_NAME.match(n) for n in names):
        problems.append("parça adları küçük harf, benzersiz ve yalnız harf/rakam/alt çizgi olmalı")
    if len({p.source for p in plan.parts}) < 2:
        problems.append("parçaların hepsi aynı kaynakta; iki sunucuya gerek yok, tek SQL yazılmalı")
    for part in plan.parts:
        if part.source not in by_source:
            problems.append(f"'{part.name}' bilinmeyen kaynak: {part.source or '(varsayılan)'}")
            continue
        ok, why = validate_sql(part.sql)
        if not ok:
            problems.append(f"'{part.name}' geçersiz: {why}")
            continue
        ok, why = allowed_tables(part.sql, by_source[part.source], context, dialect)
        if not ok:
            problems.append(f"'{part.name}' yalnız kendi kaynağının tablolarını okuyabilir: {why}")
    ok, why = validate_sql(plan.final)
    if not ok:
        problems.append(f"birleştirme sorgusu geçersiz: {why}")
    else:
        try:
            used = {t.name.lower() for t in _tables(plan.final, "sqlite")}
        except Exception as e:  # noqa: BLE001
            problems.append(f"birleştirme sorgusu okunamadı: {str(e)[:120]}")
            used = set(names)
        foreign = used - set(names)
        if foreign:
            problems.append("birleştirme sorgusu yalnız parçaları okuyabilir: " + ", ".join(sorted(foreign)))
        missing = set(names) - used
        if missing:
            problems.append("kullanılmayan parça: " + ", ".join(sorted(missing)))
    problems += _check_links(plan, profiles)
    return problems


def _check_links(plan: Plan, profiles: list[Any]) -> list[str]:
    measured = cross_links(profiles)
    if not plan.links:
        return ["parçaların hangi ölçülmüş bağla birleştiği yazılmadı (links)"]
    problems = []
    try:
        tree = sqlglot.parse_one(plan.final, read="sqlite")
    except Exception:  # noqa: BLE001
        return problems                      # reported by check_plan already
    aliases: dict[str, str] = {}
    for t in tree.find_all(exp.Table):
        aliases[(t.alias_or_name or t.name).lower()] = t.name.lower()
    joined: set[frozenset] = set()
    for eq in tree.find_all(exp.EQ):
        left, right = _key_column(eq.left), _key_column(eq.right)
        if left is not None and right is not None:
            a = (aliases.get(left.table.lower(), left.table.lower()), left.name.lower())
            b = (aliases.get(right.table.lower(), right.table.lower()), right.name.lower())
            joined.add(frozenset((a, b)))
    for link in plan.links:
        left = tuple(link.get("left", "").lower().split(".", 1))
        right = tuple(link.get("right", "").lower().split(".", 1))
        if len(left) != 2 or len(right) != 2 or frozenset((left, right)) not in joined:
            problems.append(f"bağ birleştirme sorgusunda eşitlik olarak kullanılmıyor: {link.get('left')} = {link.get('right')}")
        via = link.get("via", "").upper().replace(" ", "")
        m = re.fullmatch(r"([A-Z0-9_]+)\.([A-Z0-9_]+)=([A-Z0-9_]+)\.([A-Z0-9_]+)", via)
        if not m or (m.group(1), m.group(2), m.group(3), m.group(4)) not in measured:
            problems.append(f"bağ katalogda ölçülmüş bir kaynaklar arası ilişki değil: {link.get('via') or '(boş)'}")
    return problems


def _key_column(node: exp.Expression) -> Optional[exp.Column]:
    """The column under a key comparison, looking through the normalisation people wrap it in
    (TRIM, UPPER, CAST)."""
    while isinstance(node, (exp.Trim, exp.Upper, exp.Lower, exp.Cast, exp.Paren, exp.Anonymous)):
        inner = node.this if not isinstance(node, exp.Anonymous) else (node.expressions[0] if node.expressions else None)
        if inner is None:
            return None
        node = inner
    return node if isinstance(node, exp.Column) and node.table else None


def _value(v: Any) -> Any:
    if v is None or isinstance(v, (int, float, bytes)):
        return v
    if isinstance(v, str):
        return v.strip()
    return str(v)


def execute(plan: Plan, fetch: Callable[[Part], Iterable[tuple[list[dict], list[dict]]]]) -> tuple[list[dict], list[dict]]:
    """Run each part through `fetch` (batches of (columns, rows)), combine in memory, return
    (columns, rows) of `final`. Nothing is truncated: a part is read whole or the question fails."""
    db = sqlite3.connect(":memory:")
    try:
        for part in plan.parts:
            columns: list[str] = []
            created = False
            for cols, rows in fetch(part):
                if not created:
                    columns = [c["name"] for c in cols]
                    if len({c.lower() for c in columns}) != len(columns):
                        raise ValueError(f"'{part.name}' parçasında aynı adlı iki kolon var; farklı takma ad verin")
                    quoted = ", ".join('"' + c.replace('"', '') + '"' for c in columns)
                    db.execute(f'CREATE TABLE "{part.name}" ({quoted})')
                    created = True
                if rows:
                    marks = ", ".join("?" for _ in columns)
                    db.executemany(f'INSERT INTO "{part.name}" VALUES ({marks})',
                                   [[_value(r.get(c)) for c in columns] for r in rows])
            if not created:
                raise ValueError(f"'{part.name}' parçası kolon döndürmedi")
        try:
            cur = db.execute(plan.final)
        except sqlite3.OperationalError as first:
            # Every other statement in the conversation is T-SQL, and the model carries its habits
            # into the one statement that is not: ISNULL(a, b), TOP n, LEN(). The combining step
            # reads in-memory tables only, so its dialect carries no meaning of its own — the same
            # statement is translated and tried once before the question is failed over spelling.
            try:
                import sqlglot
                translated = sqlglot.transpile(plan.final, read="tsql", write="sqlite")[0]
            except Exception:
                raise first
            if translated.strip() == plan.final.strip():
                raise
            cur = db.execute(translated)
        names = [d[0] for d in cur.description or []]
        rows = [dict(zip(names, row)) for row in cur.fetchall()]
        return [{"name": n, "type": ""} for n in names], rows
    finally:
        db.close()


FORMAT = """## İKİ AYRI SUNUCU — BİRLEŞİK PLAN YAZ
Bu soru iki veritabanını birlikte istiyor: Logo ERP (kaynak "LOGO") ve CRM (kaynak "TIMAS_MSCRM"). Bunlar
ayrı sunuculardadır; TEK SQL YAZMA. Yalnız şu JSON'u ```json bloğunda döndür:
{"readings": ["'<kelime>' → <koşul>"],
 "parts": [{"name": "<küçük_harf_ad>", "source": "LOGO|TIMAS_MSCRM", "sql": "<o kaynağın T-SQL'i>"}],
 "links": [{"left": "<parça>.<kolon>", "right": "<parça>.<kolon>", "via": "<TABLO.KOLON>=<TABLO.KOLON>"}],
 "final": "<parçaları okuyan SQLite SELECT'i>"}
Kurallar:
- Her parça yalnız kendi kaynağının tablolarını okur (şemadaki [kaynak: ...] etiketine bak). O kaynağın
  koşullarını (dönem, iptal, filtre) parçada uygula; mümkünse parçayı birleştirme anahtarı düzeyinde topla.
- Birleştirme anahtarını iki parçada da aynı tipe ve biçime çevir: LTRIM(RTRIM(CAST(<kolon> AS NVARCHAR(100)))) AS <ad>.
- "links" yalnız ÖLÇÜLMÜŞ BAĞLAR listesinden seçilir ve "via" o satırı birebir yazar. Uygun bağ yoksa JSON yerine
  NO_SQL yaz ve hangi bağın eksik olduğunu söyle.
- "final" SQLite sözdizimidir; tablo adı olarak yalnız parça adlarını kullanır; her link bir eşitlik
  (ON a.x = b.y) olarak geçer. Yokluk için LEFT JOIN … IS NULL ya da NOT EXISTS kullan.
- Modele bırakılan niteleyiciler varsa her biri için "readings" satırı yaz ve koşulu bir parçada ya da final'de uygula.
"""


def links_block(profiles: Iterable[Any]) -> str:
    rows = sorted({f"{a}.{b}={c}.{d}" for a, b, c, d in cross_links(profiles)})
    return "## ÖLÇÜLMÜŞ BAĞLAR (kaynaklar arası)\n" + ("\n".join(f"- {r}" for r in rows) if rows else "(yok)")


def required_bridges_block(profiles: list[Any], placed: set[str]) -> str:
    """Stage 1 of moving two-source join *construction* off the model: of all measured cross-source
    links, the ones that touch a table the question actually placed are the join the plan MUST use.
    Spelled out here as a mandatory recipe — which key each part exposes and how `final` joins on it —
    the model is kept from matching parts by book/product *name* (the barcode↔barcode bridge is the
    only measured way to tie a CRM sales target to a Logo item). Empty when no measured bridge reaches
    the placed tables; then the ordinary links list stands. This does not yet *assemble* the plan (that
    is stage 2 — the compiler emitting the parts and `final` itself); it dictates the one decision the
    gate most often refuses the model for."""
    def bare(n: str) -> str:
        return re.sub(r"^LG_", "", str(n or "").upper())
    src_of: dict[str, str] = {}
    known: dict[str, str] = {}
    for p in profiles:
        src_of[bare(p.entity)] = source_of_schema(getattr(p, "schema_name", ""))
        known.setdefault(bare(p.entity), str(p.entity))
    placed_bare = {bare(e) for e in placed}
    lines: list[str] = []
    seen: set[frozenset] = set()
    for a, col, b, ref in sorted(cross_links(profiles)):
        ba, bb = bare(a), bare(b)
        if src_of.get(ba, "") == src_of.get(bb, ""):
            continue                                   # not a cross-source link
        if ba not in placed_bare and bb not in placed_bare:
            continue                                   # the question never named either end
        key = frozenset(((ba, col.upper()), (bb, ref.upper())))
        if key in seen:
            continue
        seen.add(key)
        na, nb = known.get(ba, a), known.get(bb, b)
        sa, sb = src_of.get(ba, "") or "LOGO", src_of.get(bb, "") or "LOGO"
        lines.append(f"- {na} (kaynak {sa}) .{col}  ↔  {nb} (kaynak {sb}) .{ref}")
    if not lines:
        return ""
    return ("## ZORUNLU KAYNAK BAĞI (bu soru için ölçülmüş — parçaları AD ile değil bu anahtarla birleştir)\n"
            + "\n".join(lines)
            + "\nHer iki parça bağ kolonunu LTRIM(RTRIM(CAST(<kolon> AS NVARCHAR(100)))) AS <ortak_ad> olarak yansıtsın; "
              "links.via bu satırı birebir yazsın; final ON a.<ortak_ad> = b.<ortak_ad> ile birleşsin. Kırılım "
              "kolonlarını (ör. kitap/ürün adı) bağın kaynağındaki tabloya kendi ilişki zinciri üzerinden o parçanın "
              "İÇİNDE bağla; kırılımı parçalar arası bağ anahtarı yapma.")


__all__ = ["Part", "Plan", "parse_plan", "check_plan", "execute", "cross_links", "source_of_schema",
           "FORMAT", "links_block", "required_bridges_block"]
