"""Ay kolonu grupları — bir satırın 12 ay değerini 12 ayrı kolonda tutan tablolar (tam kapı 2026-09-29, sınıf K13).

Sorun: CRM satış hedefi (`new_satishedefleriBase`: new_ocak … new_aralik) gibi geniş tablolarda «ay» bir kolon değil,
kolon ADIDIR. «Hiç hedef girilmemiş aylar», «ay bazında hedef» gibi bir soruda 12 kolonun satıra açılması (unpivot)
modele kalıyordu; model her denemede başka biçimde yazdı (aynı kod ve istemle 68 / 30.334 / 154.839 / 189.649 satır).

Mekanizma (soruya özel değil):
1. **Beyan (katalog):** tablonun sertifikalı bir eşlemesinde `extra.month_columns` = {"1": kolon, …, "12": kolon} ve
   `extra.month_missing` («girilmemiş ay» okuması, veriden: `null_or_zero` ya da `null_only`). Beyanı
   `scripts/catalog-authoring/2026-09-29-ay-kolonu-gruplari.py` yazar; adaylar `detect()` ile profilden çıkar.
   Köprü açılışta beyanı profillere dağıtır (`apply`, `coverage.apply` gibi: `profile.month_columns`).
   Yan köprüde denemek için `SEMANTIC_MONTH_GROUPS_FILE` (aynı biçimde JSON) katalog beyanının üstüne bellekte eklenir.
2. **Derleyici:** model beyanlı tabloyu okurken 12 kolonu elle açmaz; tablonun takma adıyla üç SANAL kolon yazar —
   `ay` (1–12), `ay_adi` (Ocak…Aralık), `ay_degeri`. `expand()` bu kolonları gören sorguya tablonun hemen ardına
   `CROSS APPLY (VALUES (1, N'Ocak', t.[new_ocak]), …, (12, N'Aralık', t.[new_aralik])) AS nb_ay_t(ay, ay_adi, ay_degeri)`
   ekler ve başvuruları oraya çevirir: açılım her seferinde aynı, 12 ayın hepsi, doğru eşleme.
3. **Kapı:** `review()` beyanlı grubu elle açan (VALUES, UNION ya da CASE ile) ama 12 aydan azını açan ya da bir ayı
   başka bir ayın numarası/adıyla eşleyen sorguyu `block` bulgusuyla onarıma yollar. Eksiksiz ve doğru bir el açılımı
   geçer (derleyicinin yazdığıyla aynı sonuç).
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Iterable, Optional

import sqlglot
from sqlglot import exp

from semantic_layer.models import SchemaProfile
from semantic_layer.normalize import fold

log = logging.getLogger(__name__)

#: Ay adları (ASCII katlanmış) ve ekranda yazılışları; İngilizce tam ad ve üç harfli kısaltma yalnız tam kelime olarak.
MONTHS_TR = ["ocak", "subat", "mart", "nisan", "mayis", "haziran", "temmuz", "agustos", "eylul", "ekim", "kasim", "aralik"]
MONTH_LABELS = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
MONTHS_EN = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
MONTHS_EN3 = [m[:3] for m in MONTHS_EN]
_WORD_TO_MONTH: dict[str, int] = {}
for _i, _names in enumerate(zip(MONTHS_TR, MONTHS_EN, MONTHS_EN3), 1):
    for _n in _names:
        _WORD_TO_MONTH[_n] = _i
#: Sayı sonekli bir grubun önekinde dönem sözü (AY1…AY12, MONTH_1…): yoksa 1…12 bir sıra listesidir (GROUPS1…12).
_PERIOD_WORDS = {"", "ay", "aylik", "month", "mon", "m", "donem", "period", "prd"}
_NUMERIC = ("int", "bigint", "smallint", "tinyint", "decimal", "numeric", "float", "real", "money", "smallmoney", "double", "number")

#: Sanal kolonlar: modelin yazdığı ad → açılımın kolon adı.
VCOLS = ("ay", "ay_adi", "ay_degeri")
ALIAS_PREFIX = "nb_ay_"
MISSING_NULL_OR_ZERO = "null_or_zero"
MISSING_NULL_ONLY = "null_only"


# ---------------------------------------------------------------- tanıma (katalog betiği için aday)

def _tokens(name: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", fold(name)) if t]


def _month_of_token(tok: str) -> Optional[int]:
    return _WORD_TO_MONTH.get(tok)


def _is_numeric(data_type: str) -> bool:
    return str(data_type or "").lower().startswith(_NUMERIC)


def detect(p: SchemaProfile) -> tuple[list[dict], list[dict]]:
    """Bir profildeki ay kolonu grupları: (adaylar, elenenler).

    Aday: aynı ad kalıbında (ay adı kelimesi yerinde) ya da aynı önek + 1…12 sonekiyle tam 12 kolon, her ay bir kolon,
    hepsi sayısal. Sayı sonekinde önek bir dönem sözü (boş, «ay», «month» …) olmalı ve 0 ya da 13+ numaralı kardeş
    kolon bulunmamalı — yoksa bu bir sıra listesidir (DOCTYPE1…12, GROUPS1…12), ay değil."""
    by_name: dict[tuple, dict[int, list[Any]]] = {}
    numbered: dict[str, dict[int, list[Any]]] = {}
    for c in p.columns:
        toks = _tokens(c.name)
        hits = [(i, t) for i, t in enumerate(toks) if _month_of_token(t)]
        if len(hits) == 1:
            i, t = hits[0]
            key = tuple(toks[:i]) + ("#",) + tuple(toks[i + 1:])
            by_name.setdefault(key, {}).setdefault(_month_of_token(t), []).append(c)
        m = re.match(r"^(.*?)(\d{1,2})$", c.name)
        if m:
            numbered.setdefault(fold(m.group(1)).strip("_ "), {}).setdefault(int(m.group(2)), []).append(c)
    found: list[dict] = []
    dropped: list[dict] = []

    def judge(kind: str, key: str, groups: dict[int, list[Any]]) -> None:
        months = {k: v for k, v in groups.items() if 1 <= k <= 12}
        if len(months) < 10:
            return                                   # ay grubu gibi görünmüyor; elenen listesini şişirmez
        base = {"entity": p.entity, "table_name": p.table_name, "table_pattern": p.table_pattern, "kind": kind, "key": key,
                "columns": {str(k): [c.name for c in v] for k, v in sorted(groups.items())}}
        if kind == "sayı" and (set(groups) - set(range(1, 13))):
            dropped.append({**base, "why": f"1–12 dışında kardeş kolon var ({sorted(set(groups) - set(range(1, 13)))}) — sıra listesi"})
            return
        if kind == "sayı" and key.replace("_", "") not in _PERIOD_WORDS:
            dropped.append({**base, "why": f"sayı soneki, önek '{key}' dönem sözü değil — sıra listesi"})
            return
        if len(months) != 12:
            dropped.append({**base, "why": f"12 ay yok ({len(months)} ay: eksik {sorted(set(range(1, 13)) - set(months))})"})
            return
        if any(len(v) != 1 for v in months.values()):
            dropped.append({**base, "why": "bir aya birden çok kolon düşüyor"})
            return
        types = {str(v[0].data_type or "").lower() for v in months.values()}
        if not all(_is_numeric(t) for t in types):
            dropped.append({**base, "why": f"sayısal değil ({sorted(types)})"})
            return
        if any(v[0].sensitive for v in months.values()):
            dropped.append({**base, "why": "gizli kolon"})
            return
        clash = [v for v in VCOLS if p.column(v) is not None]
        if clash:
            dropped.append({**base, "why": f"tabloda sanal kolon adı zaten var ({clash})"})
            return
        found.append({**base, "month_columns": {str(k): v[0].name for k, v in sorted(months.items())},
                      "types": sorted(types)})

    for key, groups in by_name.items():
        judge("ad", "_".join(key), groups)
    for key, groups in numbered.items():
        judge("sayı", key, groups)
    return found, dropped


# ---------------------------------------------------------------- beyan (katalog → profil)

def normalize(raw: Any) -> dict[int, str]:
    """`{"1": "new_ocak", …}` → {1: "new_ocak", …}; 12 ayın hepsi ve kolon adları dolu değilse boş."""
    if not isinstance(raw, dict):
        return {}
    out: dict[int, str] = {}
    for k, v in raw.items():
        try:
            n = int(k)
        except (TypeError, ValueError):
            return {}
        if not (1 <= n <= 12) or not isinstance(v, str) or not v.strip():
            return {}
        out[n] = v.strip()
    return out if sorted(out) == list(range(1, 13)) and len({v.upper() for v in out.values()}) == 12 else {}


def declared(store, tenant_id: str, datasource_id: str) -> list[dict]:
    """Sertifikalı eşlemelerdeki ay grubu beyanları: [{entity, table_pattern, month_columns, month_missing}]."""
    out: list[dict] = []
    try:
        index = store.certified_index(tenant_id, datasource_id)
    except Exception as e:  # noqa: BLE001
        log.warning("ay grupları: katalog okunamadı: %s", e)
        return out
    seen: set[tuple] = set()
    for senses in index.values():
        for _c, maps in senses:
            for m in maps:
                cols = normalize((m.extra or {}).get("month_columns"))
                key = ((m.table_pattern or "").upper(), (m.entity or "").upper())
                if cols and key not in seen:
                    seen.add(key)
                    out.append({"entity": m.entity, "table_pattern": m.table_pattern, "month_columns": cols,
                                "month_missing": (m.extra or {}).get("month_missing") or MISSING_NULL_OR_ZERO})
    return out


def _from_file(path: str) -> list[dict]:
    """Yan köprü denemesi: katalog betiğinin `--json` çıktısı (aynı alanlar), katalog yazılmadan bellekte."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        log.warning("ay grupları dosyası okunamadı (%s): %s", path, e)
        return []
    rows = data.get("groups", data) if isinstance(data, dict) else data
    out = []
    for g in rows if isinstance(rows, list) else []:
        cols = normalize(g.get("month_columns"))
        if cols and (g.get("entity") or g.get("table_pattern")):
            out.append({"entity": g.get("entity"), "table_pattern": g.get("table_pattern"), "month_columns": cols,
                        "month_missing": g.get("month_missing") or MISSING_NULL_OR_ZERO})
    return out


def apply(profiles: Iterable[SchemaProfile], store, settings) -> int:
    """Her profile beyanını verir: `month_columns` ({ay: kolon}) ve `month_missing`. Beyansız profilde ikisi boş.
    Profilde kolonu bulunmayan beyan uygulanmaz (katalog ile profil ayrışmışsa sessiz yanlış açılım yok)."""
    groups = declared(store, settings.tenant_id, settings.datasource_id) if store is not None else []
    path = os.environ.get("SEMANTIC_MONTH_GROUPS_FILE", "").strip()
    if path:
        groups = groups + _from_file(path)
    by_pattern = {(g.get("table_pattern") or "").upper(): g for g in groups if g.get("table_pattern")}
    by_entity = {(g.get("entity") or "").upper(): g for g in groups if g.get("entity")}
    n = 0
    for p in profiles:
        g = by_pattern.get((p.table_pattern or "").upper()) or by_entity.get((p.entity or "").upper())
        cols = dict(g["month_columns"]) if g else {}
        if cols and not all(p.column(c) is not None for c in cols.values()):
            log.warning("ay grubu beyanı %s profiliyle uyuşmuyor (kolon yok): uygulanmadı", p.table_name)
            cols = {}
        if cols and any(p.column(v) is not None for v in VCOLS):
            log.warning("ay grubu beyanı %s: sanal kolon adı tabloda var, uygulanmadı", p.table_name)
            cols = {}
        p.month_columns = cols
        p.month_missing = (g.get("month_missing") if g and cols else None)
        n += bool(cols)
    if n:
        log.info("ay kolonu grubu beyanlı %d profil", n)
    return n


def of(p: Optional[SchemaProfile]) -> dict[int, str]:
    return dict(getattr(p, "month_columns", None) or {}) if p is not None else {}


# ---------------------------------------------------------------- istem

def prompt_note(p: SchemaProfile, label: str) -> str:
    """Model istemindeki tablo satırının altına: ay açılımını derleyici yazar, model sanal kolonları kullanır."""
    cols = of(p)
    if not cols:
        return ""
    missing = getattr(p, "month_missing", None) or MISSING_NULL_OR_ZERO
    empty = ("girilmemiş (boş) ay = `ISNULL(<takma ad>.ay_degeri, 0) = 0` — bu tabloda değer girilmemiş ay 0 olarak durur, "
             "NULL yalnız hiç doldurulmamış kayıtta" if missing == MISSING_NULL_OR_ZERO else
             "girilmemiş (boş) ay = `<takma ad>.ay_degeri IS NULL` — bu tabloda 0 girilmiş bir değerdir, boş değildir")
    return (f"  ↳ AY AÇILIMI ({label}): \"{cols[1]}\" … \"{cols[12]}\" bu tablonun 12 AY kolonudur (tek bir ay boyutu). "
            "Ay bazında okuma/süzme/gruplama/sayma için bu kolonları ELLE AÇMA (CROSS APPLY, VALUES, UNION ya da CASE yazma): "
            "tablonun takma adıyla SANAL kolonları kullan — <takma ad>.ay (1–12), <takma ad>.ay_adi (Ocak…Aralık), "
            "<takma ad>.ay_degeri (o ayın değeri). Derleyici her kaydı 12 ay satırına açar (12 ayın hepsi, doğru eşleme). "
            f"{empty}. Tek bir ayın ya da yıllık toplamın okunmasında kolonun kendisi kullanılabilir.")


# ---------------------------------------------------------------- derleyici: sanal kolonları açılıma çevir

def _profiles_index(profiles: list[SchemaProfile]):
    """(eleştirmenin ad dizinleri, beyanlı profillerin bütün yazılışları): istemdeki ad
    (`Timas_MSCRM_dbo_new_satishedefleriBase`), üç parçalı ad, tablo adı ve varlık adı."""
    from semantic_layer.runtime import critic
    by_table, by_entity = critic._profiles_by_name(profiles)
    spelled: dict[str, SchemaProfile] = {}
    for p in profiles:
        if not of(p):
            continue
        schema = p.schema_name or ""
        for n in (p.table_name, p.entity, f"{schema}.{p.table_name}", f"{schema.replace('.', '_')}_{p.table_name}"):
            spelled.setdefault(re.sub(r"[\[\]\"]", "", n).upper(), p)
    return by_table, by_entity, spelled


def _resolve(node: exp.Table, by_table: dict, by_entity: dict, spelled: Optional[dict] = None) -> Optional[SchemaProfile]:
    from semantic_layer.runtime import critic
    if spelled:
        parts = [x for x in (node.catalog, node.db, node.name) if x]
        for n in (".".join(parts), "_".join(parts), node.name):
            hit = spelled.get((n or "").upper())
            if hit is not None:
                return hit
    try:
        return critic._resolve(node, by_table, by_entity)
    except Exception:  # noqa: BLE001
        return None


def _split_head(sql: str) -> tuple[str, str]:
    """Baştaki `--` yorum satırları (modelin `-- yorum:` okumaları) ve gövde: gövde yeniden yazılırken yorumlar korunur."""
    lines = (sql or "").splitlines(keepends=True)
    i = 0
    while i < len(lines) and (not lines[i].strip() or lines[i].lstrip().startswith("--")):
        i += 1
    return "".join(lines[:i]), "".join(lines[i:])


def _select_sources(select: exp.Select) -> list[tuple[exp.Table, str]]:
    """Bu SELECT'in kendi FROM/JOIN listesindeki tablolar ve takma adları (alt sorgulara inmeden)."""
    out = []
    frm = select.args.get("from") or select.args.get("from_")
    items = [frm.this] if frm is not None and getattr(frm, "this", None) is not None else []
    items += [j.this for j in select.args.get("joins") or []]
    for it in items:
        if isinstance(it, exp.Table) and it.name:
            out.append((it, it.alias_or_name))
    return out


def _grouped(select: exp.Select, by_table, by_entity, spelled) -> dict[str, tuple[exp.Table, SchemaProfile]]:
    out = {}
    for node, alias in _select_sources(select):
        prof = _resolve(node, by_table, by_entity, spelled)
        if of(prof):
            out[alias.upper()] = (node, prof)
    return out


def _owner_select(col: exp.Column) -> Optional[exp.Select]:
    node = col.parent
    while node is not None and not isinstance(node, exp.Select):
        node = node.parent
    return node


def _apply_join(alias: str, table_alias: str, cols: dict[int, str], dialect: str) -> exp.Join:
    rows = ", ".join(f"({n}, N'{MONTH_LABELS[n - 1]}', {table_alias}.[{cols[n]}])" for n in range(1, 13))
    text = f"SELECT 1 FROM x CROSS APPLY (VALUES {rows}) AS {alias}({', '.join(VCOLS)})"
    return sqlglot.parse_one(text, read="tsql").args["joins"][0]


def expand(sql: str, profiles: list[SchemaProfile], dialect: str = "tsql") -> tuple[str, list[str]]:
    """Beyanlı tablonun sanal ay kolonlarını (`t.ay`, `t.ay_adi`, `t.ay_degeri`) derleyicinin açılımına çevirir.

    Sanal kolon yoksa SQL'e dokunulmaz (yeniden yazım yok). Nitelikli başvuru takma adla bağlanır; niteliksiz başvuru
    yalnız o SELECT'te tek bir beyanlı tablo varsa ona bağlanır. Açılım tablonun hemen ardına eklenir (sonraki JOIN'lerin
    ON'u ay kolonunu okuyabilir)."""
    if not sql or not any(of(p) for p in profiles):
        return sql, []
    if not re.search(r"(?i)\b(ay|ay_adi|ay_degeri)\b", sql):
        return sql, []
    head, body = _split_head(sql)
    try:
        tree = sqlglot.parse_one(body, read=dialect)
    except Exception:  # noqa: BLE001
        return sql, []
    by_table, by_entity, spelled = _profiles_index(profiles)
    taken ={a.alias_or_name.upper() for a in tree.find_all(exp.TableAlias) if a.alias_or_name}
    taken |= {t.alias_or_name.upper() for t in tree.find_all(exp.Table)}
    # (id(select), tablo takma adı) → açılımın takma adı
    made: dict[tuple[int, str], str] = {}
    notes: list[str] = []
    for col in list(tree.find_all(exp.Column)):
        name = (col.name or "").lower()
        if name not in VCOLS:
            continue
        select = _owner_select(col)
        # Kolon bir alt sorgunun içindeyse onun SELECT'i; ORDER BY / GROUP BY da aynı SELECT'e bağlıdır.
        while select is not None:
            grouped = _grouped(select, by_table, by_entity, spelled)
            if grouped:
                break
            select = _owner_select(select) if select.parent is not None else None
        if select is None:
            continue
        if col.table:
            hit = grouped.get(col.table.upper())
            if hit is None:
                continue
            key = col.table.upper()
        else:
            if len(grouped) != 1:
                continue
            key = next(iter(grouped))
            hit = grouped[key]
        node, prof = hit
        mk = (id(select), key)
        if mk not in made:
            base = re.sub(r"[^A-Za-z0-9_]", "_", ALIAS_PREFIX + node.alias_or_name)[:60]
            alias, n = base, 2
            while alias.upper() in taken:
                alias, n = f"{base}{n}", n + 1
            taken.add(alias.upper())
            join = _apply_join(alias, node.alias_or_name, of(prof), dialect)
            joins = list(select.args.get("joins") or [])
            pos = 0
            for i, j in enumerate(joins):
                if j.this is node:
                    pos = i + 1
            joins.insert(pos, join)
            select.set("joins", joins)
            made[mk] = alias
            notes.append(f"ay açılımı derleyiciden: {prof.entity} 12 ay kolonu → {alias}(ay, ay_adi, ay_degeri)")
        col.set("table", exp.to_identifier(made[mk]))
        col.set("this", exp.to_identifier(name))
    if not made:
        return sql, []
    return head + tree.sql(dialect=dialect), notes


def collapse(sql: str) -> str:
    """`expand`'in tersi — modele onarım için gösterilen SQL'de derleyicinin açılımı yerine sanal kolonlar."""
    if not sql or ALIAS_PREFIX not in sql:
        return sql
    head, body = _split_head(sql)
    try:
        tree = sqlglot.parse_one(body, read="tsql")
    except Exception:  # noqa: BLE001
        return sql
    changed = False
    for select in list(tree.find_all(exp.Select)):
        joins = list(select.args.get("joins") or [])
        keep = []
        for j in joins:
            lat = j.this
            alias = lat.args.get("alias") if isinstance(lat, exp.Lateral) else None
            name = alias.name if alias is not None else ""
            vals = lat.this.this if isinstance(lat, exp.Lateral) and isinstance(lat.this, exp.Subquery) else None
            owners = {c.table for c in vals.find_all(exp.Column)} if isinstance(vals, exp.Values) else set()
            if name.lower().startswith(ALIAS_PREFIX) and len(owners) == 1:
                owner = next(iter(owners))
                for c in select.find_all(exp.Column):
                    if (c.table or "").lower() == name.lower():
                        c.set("table", exp.to_identifier(owner))
                changed = True
                continue
            keep.append(j)
        if changed:
            select.set("joins", keep)
    return head + tree.sql(dialect="tsql") if changed else sql


# ---------------------------------------------------------------- kapı: elle ve eksik/yanlış açılım

def _label_month(node: exp.Expression) -> Optional[int]:
    """Bir satırdaki ay etiketi: 1–12 sayısı ya da ay adı dizgesi."""
    if isinstance(node, exp.National):
        node = exp.Literal.string(node.this)
    if isinstance(node, exp.Literal):
        if node.is_string:
            toks = _tokens(str(node.this))
            hits = {_month_of_token(t) for t in toks if _month_of_token(t)}
            return hits.pop() if len(hits) == 1 else None
        try:
            n = int(str(node.this))
        except ValueError:
            return None
        return n if 1 <= n <= 12 else None
    return None


def review(sql_or_tree: Any, profiles: list[SchemaProfile], dialect: str = "tsql") -> list[tuple[str, str]]:
    """Beyanlı bir ay grubunu elle açan ama eksik ya da yanlış eşleyen okumalar: [(kind, mesaj)].

    Üç el açılımı biçimi okunur: VALUES satırları, UNION kolları, CASE dalları. Bir satırda/kolda/dalda bir ay kolonu
    ve bir ay etiketi (1–12 ya da ay adı) birlikte duruyorsa eşleme; etiket kolonun ayı değilse yanlış. Aynı açılımda
    12 ayın hepsi yoksa eksik."""
    if not any(of(p) for p in profiles):
        return []
    tree = sql_or_tree
    if isinstance(sql_or_tree, str):
        try:
            tree = sqlglot.parse_one(_split_head(sql_or_tree)[1], read=dialect)
        except Exception:  # noqa: BLE001
            return []
    by_table, by_entity, spelled = _profiles_index(profiles)
    # takma ad / tablo adı → profil (bütün sorguda; açılım genellikle alt sorgu ya da CROSS APPLY içinde)
    alias_prof: dict[str, SchemaProfile] = {}
    for t in tree.find_all(exp.Table):
        prof = _resolve(t, by_table, by_entity, spelled)
        if of(prof):
            alias_prof[t.alias_or_name.upper()] = prof
            alias_prof.setdefault(t.name.upper(), prof)
    if not alias_prof:
        return []
    only = list({id(p): p for p in alias_prof.values()}.values())

    def month_col(c: exp.Column) -> Optional[tuple[SchemaProfile, int]]:
        cands = [alias_prof[c.table.upper()]] if c.table and c.table.upper() in alias_prof else ([] if c.table else only)
        for p in cands:
            for n, name in of(p).items():
                if name.upper() == (c.name or "").upper():
                    return p, n
        return None

    problems: list[tuple[str, str]] = []

    def judge(form: str, rows: list[exp.Expression]) -> None:
        per: dict[int, dict] = {}
        for row in rows:
            cols = [m for m in (month_col(c) for c in row.find_all(exp.Column)) if m]
            if len({(id(p), n) for p, n in cols}) != 1:
                continue
            prof, n = cols[0]
            st = per.setdefault(id(prof), {"prof": prof, "months": set(), "wrong": []})
            st["months"].add(n)
            labels = [m for m in (_label_month(x) for x in row.find_all(exp.Literal, exp.National)) if m]
            if labels and n not in labels:
                st["wrong"].append(f"{of(prof)[n]} → {labels[0]}")
        for st in per.values():
            if len(st["months"]) < 2:
                continue                        # tek ay okuması açılım değildir
            prof, missing = st["prof"], sorted(set(range(1, 13)) - st["months"])
            bits = []
            if missing:
                bits.append(f"{12 - len(missing)} ay açılmış, eksik: {', '.join(MONTH_LABELS[m - 1] for m in missing)}")
            if st["wrong"]:
                bits.append("yanlış eşleme: " + ", ".join(st["wrong"]))
            if bits:
                problems.append(("MONTH_UNPIVOT",
                    f"{prof.entity} tablosunun 12 ay kolonu elle ({form}) açılmış ve " + "; ".join(bits) + ". "
                    "Ay kolonlarını elle açma: tablonun takma adıyla sanal kolonları kullan — <takma ad>.ay (1–12), "
                    "<takma ad>.ay_adi, <takma ad>.ay_degeri; açılımı derleyici yazar (12 ayın hepsi, doğru eşleme)."))

    for v in tree.find_all(exp.Values):
        judge("VALUES", [t for t in v.expressions if isinstance(t, exp.Tuple)])
    for u in tree.find_all(exp.Union):
        if isinstance(u.parent, exp.Union):
            continue                            # zincirin tepesinden bir kez okunur
        branches, stack = [], [u]
        while stack:
            x = stack.pop()
            if isinstance(x, exp.Union):
                stack += [x.left, x.right]
            elif isinstance(x, exp.Select):
                branches.append(exp.Tuple(expressions=[e.copy() for e in x.expressions]))
        judge("UNION", branches)
    for case in tree.find_all(exp.Case):
        # Yalnız değeri ay kolonu olan dal (`WHEN m.ay = 3 THEN t.new_Mart`); koşulda ay kolonu olan dal
        # (`WHEN t.new_ocak > 0 THEN 1`) bir açılım değil, bir süzgeçtir — etiketi okunmaz.
        rows = []
        for i in case.args.get("ifs") or []:
            cond, val = i.args.get("this"), i.args.get("true")
            if cond is None or val is None:
                continue
            if any(month_col(c) for c in cond.find_all(exp.Column)) or not any(month_col(c) for c in val.find_all(exp.Column)):
                continue
            rows.append(exp.Tuple(expressions=[cond.copy(), val.copy()]))
        judge("CASE", rows)
    seen, out = set(), []
    for k, m in problems:
        if m not in seen:
            seen.add(m)
            out.append((k, m))
    return out


__all__ = ["detect", "declared", "apply", "of", "prompt_note", "expand", "collapse", "review", "normalize", "VCOLS",
           "MONTH_LABELS", "MISSING_NULL_OR_ZERO", "MISSING_NULL_ONLY"]
