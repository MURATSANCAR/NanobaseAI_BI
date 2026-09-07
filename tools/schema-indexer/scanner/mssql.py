"""Microsoft SQL Server metadata scanner + profiler (pymssql, read-only).

Mirrors scanner/metadata.py for INFORMATION_SCHEMA + sys.* catalog views and
returns the same TableMeta/RelationshipMeta models, so normalize → embed →
upsert is untouched. Table selection is driven by `table_patterns` (T-SQL LIKE)
from the datasource map — ERP databases carry thousands of firm/period tables,
and the retrieval index must only hold the ones the customer actually uses.

Domain descriptions for well-known ERP table families (Logo Tiger/Go naming:
LG_<firm>_<period>_<TABLE>) are attached when the physical name matches, so
retrieval text carries business meaning instead of bare identifiers.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from config import IndexerConfig
from models import ColumnMeta, ForeignKey, RelationshipMeta, TableMeta

# --- ERP (Logo) domain descriptions ------------------------------------------

_LOGO_TABLE_DESC: dict[str, str] = {
    "INVOICE": "Fatura başlıkları (satış ve alış faturaları). TRCODE 7=perakende satış, 8=toptan satış, 9=verilen hizmet, 1=satınalma, 4=alınan hizmet, 3=alış iade, 6=satış iade. CANCELLED=0 geçerli, 1 iptal. NETTOTAL vergiler dahil net tutar, GROSSTOTAL brüt, TOTALVAT KDV, TOTALDISCOUNTS iskonto. DATE_ fatura tarihi. CLIENTREF → CLCARD.LOGICALREF (cari).",
    "STLINE": "Fatura/irsaliye satırları (malzeme hareketleri). STOCKREF → ITEMS.LOGICALREF (malzeme), INVOICEREF → INVOICE.LOGICALREF, CLIENTREF → CLCARD.LOGICALREF. AMOUNT miktar, PRICE birim fiyat, TOTAL satır tutarı, VATAMNT KDV. LINETYPE 0=malzeme satırı, 1=promosyon, 2=indirim, 3=masraf, 4=hizmet. TRCODE fatura türü (7/8 satış, 1 alış). IOCODE 1-2 giriş, 3-4 çıkış. DATE_ hareket tarihi. CANCELLED=0.",
    "CLCARD": "Cari hesap kartları (müşteri/tedarikçi). CODE cari kodu, DEFINITION_ unvan, CARDTYPE 1=alıcı 2=satıcı 3=alıcı+satıcı, CITY şehir, TOWN ilçe, COUNTRY ülke, SPECODE özel kod, CYPHCODE yetki kodu, ACTIVE 0=aktif.",
    "ITEMS": "Malzeme (stok) kartları. CODE malzeme kodu, NAME malzeme adı, CARDTYPE 1=ticari mal 2=karma koli 3=depozitolu 4=sabit kıymet 10=hammadde 11=yarı mamul 12=mamul 20=tüketim malı, SPECODE özel kod, STGRPCODE grup kodu, UNITSETREF birim seti, ACTIVE 0=aktif.",
    "STFICHE": "Malzeme fişleri başlıkları (irsaliye, sayım, ambar fişleri). TRCODE 1=satınalma irsaliyesi 8=toptan satış irsaliyesi 7=perakende satış irsaliyesi 13=üretim çıkış 11-12 ambar fişi. FICHENO fiş no, DATE_ tarih, NETTOTAL net tutar, INVOICEREF ilişkili fatura, CANCELLED=0.",
    "ORFICHE": "Sipariş fişleri başlıkları. TRCODE 1=satınalma siparişi, 2=satış siparişi. DATE_ sipariş tarihi, NETTOTAL net tutar, CLIENTREF cari, STATUS 1=öneri 4=onaylı, CANCELLED=0.",
    "ORFLINE": "Sipariş satırları. STOCKREF malzeme, ORDFICHEREF → ORFICHE.LOGICALREF, AMOUNT sipariş miktarı, SHIPPEDAMOUNT sevk edilen, PRICE fiyat, TOTAL tutar, CLOSED 1=kapalı, DATE_ tarih.",
    "CLFLINE": "Cari hesap hareketleri (fişler). TRCODE hareket türü (1 nakit tahsilat, 2 nakit ödeme, 31-38 fatura kaynaklı, 70 devir). AMOUNT tutar, SIGN 0=borç 1=alacak, DATE_ tarih, CLIENTREF cari, CANCELLED=0.",
    "PAYTRANS": "Ödeme/vade hareketleri (fatura vadeleri, tahsilat planı). DATE_ vade tarihi, TOTAL tutar, PAID ödenen, CARDREF cari, EARLYINTEREST/LATEINTEREST vade farkı oranları.",
    "EMFLINE": "Muhasebe fişi satırları. ACCOUNTREF → EMUHACC.LOGICALREF (hesap), DEBIT borç, CREDIT alacak, DATE_ tarih, SIGN 0=borç 1=alacak.",
    "EMFICHE": "Muhasebe fişi başlıkları. TRCODE fiş türü, DATE_ tarih, FICHENO fiş no, CANCELLED=0.",
    "EMUHACC": "Muhasebe hesap planı. CODE hesap kodu, DEFINITION_ hesap adı, ACCOUNTTYPE hesap türü.",
    "PRCLIST": "Fiyat listeleri (alış/satış fiyat kartları). CARDREF malzeme, PRICE fiyat, PTYPE 1=alış 2=satış, BEGDATE/ENDDATE geçerlilik.",
    "UNITSETF": "Birim setleri başlıkları. CODE birim seti kodu, NAME adı.",
    "UNITSETL": "Birim seti satırları (adet, kg, koli...). CODE birim kodu, UNITSETREF birim seti.",
    "SPECODES": "Özel kod tanımları (cari/malzeme özel kodları, yetki kodları). SPECODE kod, SPECODETYPE tür, DEFINITION_ açıklama.",
    "CAPIBLOCK": "Depo/ambar ve genel parametre blokları.",
    "STINVTOT": "Malzeme ambar toplamları (stok miktarları). STOCKREF malzeme, INVENNO ambar no, ONHAND eldeki miktar, DATE_ tarih.",
    "PAYPLANS": "Ödeme planları. CODE plan kodu, DEFINITION_ açıklama.",
    "BANKACC": "Banka hesapları. CODE hesap kodu, DEFINITION_ açıklama.",
    "BNFLINE": "Banka hareketleri. AMOUNT tutar, SIGN 0=borç 1=alacak, DATE_ tarih.",
    "KSLINES": "Kasa hareketleri. AMOUNT tutar, SIGN 0=borç 1=alacak, DATE_ tarih.",
    "CSCARD": "Çek/senet kartları. AMOUNT tutar, DUEDATE vade, DOC 1=çek 2=senet.",
    "SLSMAN": "Satış temsilcileri. CODE kod, DEFINITION_ ad.",
    "CAPIFIRM": "Firma tanımları (NR firma numarası, NAME firma adı).",
    "CAPIPERIOD": "Firma dönemleri (FIRMNR firma, NR dönem, BEGDATE/ENDDATE).",
}

_LOGO_COLUMN_DESC: dict[str, str] = {
    "LOGICALREF": "Tekil kayıt anahtarı (birincil anahtar; diğer tablolar *REF kolonlarıyla buna bağlanır)",
    "DATE_": "Belge/hareket tarihi (DATETIME)",
    "TRCODE": "İşlem/belge türü kodu",
    "CANCELLED": "İptal bayrağı: 0=geçerli, 1=iptal — sorgularda CANCELLED=0 filtreleyin",
    "NETTOTAL": "Net tutar (KDV dahil, iskonto düşülmüş)",
    "GROSSTOTAL": "Brüt tutar",
    "TOTALVAT": "Toplam KDV",
    "TOTALDISCOUNTS": "Toplam iskonto",
    "CLIENTREF": "Cari hesap referansı → CLCARD.LOGICALREF",
    "STOCKREF": "Malzeme referansı → ITEMS.LOGICALREF",
    "INVOICEREF": "Fatura referansı → INVOICE.LOGICALREF",
    "STFICHEREF": "Malzeme fişi referansı → STFICHE.LOGICALREF",
    "ORDFICHEREF": "Sipariş fişi referansı → ORFICHE.LOGICALREF",
    "AMOUNT": "Miktar (satırlarda) veya tutar (cari/banka hareketlerinde)",
    "PRICE": "Birim fiyat",
    "TOTAL": "Satır tutarı",
    "VATAMNT": "Satır KDV tutarı",
    "LINETYPE": "Satır türü: 0=malzeme, 1=promosyon, 2=indirim, 3=masraf, 4=hizmet",
    "IOCODE": "Giriş/çıkış: 1-2 giriş, 3-4 çıkış",
    "FICHENO": "Belge/fiş numarası",
    "CODE": "Kod",
    "NAME": "Ad",
    "DEFINITION_": "Açıklama / unvan",
    "SPECODE": "Özel kod",
    "CYPHCODE": "Yetki kodu",
    "ACTIVE": "Aktiflik: 0=aktif, 1=pasif",
    "SIGN": "Yön: 0=borç, 1=alacak",
    "CARDTYPE": "Kart türü",
    "CITY": "Şehir",
    "TOWN": "İlçe",
    "COUNTRY": "Ülke",
    "SALESMANREF": "Satış temsilcisi referansı → SLSMAN.LOGICALREF",
    "SOURCEINDEX": "Kaynak ambar numarası",
    "INVENNO": "Ambar numarası",
    "ONHAND": "Eldeki miktar",
    "PAID": "Ödenen tutar",
    "DUEDATE": "Vade tarihi",
    "DEBIT": "Borç tutarı",
    "CREDIT": "Alacak tutarı",
    "ACCOUNTREF": "Muhasebe hesabı referansı → EMUHACC.LOGICALREF",
}

_LOGO_NAME = re.compile(r"^(?:LG_\d+_(?:\d+_)?)?(?P<base>[A-Z][A-Z0-9]*)$")
# The three shapes a Logo table name takes: L_X once per database, LG_<firm>_X once per firm, and
# LG_<firm>_<period>_X once per firm-period. Splitting a physical name into (prefix, base) is what
# lets a dictionary entry written once be applied to every copy of that table.
_LOGO_PREFIX = re.compile(r"^(?P<prefix>L_|LG_(?P<firm>\d+)_(?:(?P<period>\d+)_)?)(?P<base>[A-Z][A-Z0-9_]*)$")


def _logo_base(table_name: str) -> str:
    m = _LOGO_NAME.match(table_name.upper())
    if m:
        return m.group("base")
    m = _LOGO_PREFIX.match(table_name.upper())
    return m.group("base") if m else table_name.upper()


def _logo_parts(table_name: str) -> tuple[str, str | None, str | None]:
    """(base, firm, period) for a physical Logo name; (name, None, None) for anything else."""
    m = _LOGO_PREFIX.match(table_name.upper())
    if not m:
        return table_name.upper(), None, None
    return m.group("base"), m.group("firm"), m.group("period")


# --- vendor data dictionary (LDDS) ----------------------------------------------


def _ldds_path() -> Path:
    env = os.environ.get("LOGO_LDDS_PATH")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3] / "configs" / "schemas" / "logo-ldds.json"


@lru_cache(maxsize=1)
def _ldds() -> dict[str, Any]:
    """Logo's own dictionary: 310 tables, 8.900 columns, the code sets and the join graph.

    Logo declares no foreign keys and writes no extended properties, so without this a scan sees
    nothing but identifiers. Absent file → empty dict: a source that is not Logo, or a deployment
    that has not imported the workbook, keeps working exactly as before.
    """
    path = _ldds_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"[schema-indexer] Logo data dictionary not loaded ({path}): {e}")
        return {}
    tables = data.get("tables") or {}
    print(
        f"[schema-indexer] Logo data dictionary: {len(tables)} tables, "
        f"{sum(len(t.get('columns') or {}) for t in tables.values())} columns, "
        f"{sum(len(t.get('relations') or []) for t in tables.values())} relations"
    )
    return data


def _ldds_table(table_name: str) -> dict[str, Any]:
    return (_ldds().get("tables") or {}).get(_logo_base(table_name)) or {}


def _bilingual(tr: str, en: str) -> str:
    """The vendor documents in both languages and neither one alone is enough.

    Questions arrive in Turkish, so "Cari hesap kartları" is what a question about cari hesap can
    match. The English is what the column names themselves were built from, and dropping it would
    lose the only text that reads like `CLCARD`. Where both exist they are kept together.
    """
    tr, en = tr.strip(), en.strip()
    if tr and en and tr.casefold() != en.casefold():
        return f"{tr} ({en})"
    return tr or en


def _table_desc(table_name: str) -> str:
    """What this table is. The hand-written Turkish entries stay first — they carry the filters and
    transaction codes that answering a question actually needs — and the dictionary covers the
    several hundred tables nobody has written about."""
    base = _logo_base(table_name)
    if base in _LOGO_TABLE_DESC:
        return _LOGO_TABLE_DESC[base]
    if table_name.upper().startswith("L_CAPI"):
        written = _LOGO_TABLE_DESC.get(table_name.upper()[2:], "")
        if written:
            return written
    entry = _ldds_table(table_name)
    return _bilingual(str(entry.get("description_tr") or ""), str(entry.get("description") or ""))


def _col_desc(column: str, table_name: str = "") -> str:
    """What this column holds, and — when the vendor documented them — what its codes mean.

    A coded column is the one case where the dictionary beats anything written by hand: `CARDTYPE`
    described as "kart türü" cannot be filtered on, while `1=Ticari Mal, 12=Mamul` can.
    """
    col = column.upper()
    entry = (_ldds_table(table_name).get("columns") or {}).get(col) if table_name else None
    # Turkish labels first where the vendor wrote them: a question asking for indirim satırları has
    # to match "İndirim", not "Discount".
    values = (entry.get("values_tr") or entry.get("values")) if entry else None
    if values:
        # With a code set the codes are the point, so the head stays short: one language, not two.
        head = entry.get("description_tr") or entry.get("description") or _LOGO_COLUMN_DESC.get(col) or col
        codes = ", ".join(f"{k}={v}" for k, v in sorted(values.items(), key=lambda kv: int(kv[0])))
        return f"{head} ({codes})"
    if col in _LOGO_COLUMN_DESC:
        return _LOGO_COLUMN_DESC[col]
    if not entry:
        return ""
    return _bilingual(str(entry.get("description_tr") or ""), str(entry.get("description") or ""))


# --- connection -----------------------------------------------------------------


def connect_mssql(cfg: IndexerConfig):
    import pymssql

    c = cfg.mssql_connect_cfg()
    return pymssql.connect(
        server=c["host"],
        port=int(c.get("port") or 1433),
        user=c["user"],
        password=c["password"],
        database=c["database"],
        login_timeout=20,
        timeout=120,
        tds_version=str(c.get("tds_version") or "7.4"),
        charset="UTF-8",
        as_dict=True,
        appname="nanobaseai-bi-schema-indexer",
    )


def _type_display(dt: str, max_len: Any, precision: Any, scale: Any) -> str:
    d = (dt or "").lower()
    if d in ("varchar", "nvarchar", "char", "nchar", "varbinary") and max_len:
        return f"{d}({'max' if int(max_len) < 0 else max_len})"
    if d in ("decimal", "numeric") and precision is not None:
        return f"{d}({precision},{scale or 0})"
    return d


def _patterns(cfg: IndexerConfig) -> list[str]:
    pats = [str(p) for p in (cfg.mssql_connect_cfg().get("table_patterns") or []) if str(p).strip()]
    return pats


# --- scan -------------------------------------------------------------------------


def _row_count_map(cur) -> dict[tuple[str, str], int]:
    """(schema, table) → row count, from the partition stats DMV. Empty when the read-only account
    lacks VIEW DATABASE STATE — the caller then keeps whatever order it already had."""
    try:
        cur.execute(
            """
            SELECT s.name AS sch, o.name AS tbl, SUM(p.row_count) AS n
            FROM sys.dm_db_partition_stats p
            JOIN sys.objects o ON o.object_id = p.object_id
            JOIN sys.schemas s ON s.schema_id = o.schema_id
            WHERE p.index_id IN (0, 1) AND o.type = 'U'
            GROUP BY s.name, o.name
            """
        )
        return {(r["sch"], r["tbl"]): int(r["n"] or 0) for r in cur.fetchall()}
    except Exception:
        return {}


def _dictionary_key(table_name: str, columns: list[str]) -> list[str]:
    """The primary key a Logo database does not declare.

    Logo enforces uniqueness in the application, not in SQL Server: `sys.key_constraints` is empty
    for every table, so a scan reports a schema in which no row is identifiable. The dictionary's
    index listing says which columns are unique, and the one that matters is the same everywhere —
    `LOGICALREF`, the reference every `*REF` column in the database points at. Without it a join is
    written between two columns the planner has no reason to believe are one-to-many.
    """
    present = {c.upper() for c in columns}
    unique = [ix for ix in (_ldds_table(table_name).get("indexes") or [])
              if ix.get("unique") and ix.get("columns") and present.issuperset(ix["columns"])]
    if not unique:
        return []
    # Shortest first — a single-column key over a composite that also happens to be unique — and the
    # vendor's own order among equals, which puts the row reference first.
    unique.sort(key=lambda ix: len(ix["columns"]))
    return list(unique[0]["columns"])


def _dictionary_links(table_name: str, columns: list[str], present: set[str]) -> list[dict[str, str]]:
    """The dictionary's joins for this table, resolved to table names this scan actually contains.

    A relation is written once against `STLINE`; the database holds it as
    `LG_411_01_STLINE → LG_411_ITEMS`, crossing from a period table to a firm one. The target's own
    level decides which prefix it takes, and a target that is not in the scan is skipped rather than
    invented — a join to a table nobody catalogued is worse than no join.
    """
    entry = _ldds_table(table_name)
    relations = entry.get("relations") or []
    if not relations:
        return []
    _, firm, period = _logo_parts(table_name)
    if firm is None:
        return []
    tables = _ldds().get("tables") or {}
    have = {c.upper() for c in columns}
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for rel in relations:
        column, target = rel.get("column", ""), rel.get("to", "")
        if column not in have or column in seen or not target:
            continue
        # Try the shape the dictionary says this table takes first, then the others: the workbook's
        # own scope is right almost always, and where it is not (a table listed as global that
        # actually ships per firm) the scan set settles it.
        scope = (tables.get(target) or {}).get("scope", "firm")
        forms = {
            "period": f"LG_{firm}_{period}_{target}" if period else "",
            "firm": f"LG_{firm}_{target}",
            "database": f"L_{target}",
        }
        order = [scope] + [k for k in ("period", "firm", "database") if k != scope]
        candidates = [forms[k] for k in order if forms[k]]
        for cand in candidates:
            if cand in present:
                seen.add(column)
                out.append({"column": column, "table": cand, "to_column": rel.get("to_column") or "LOGICALREF"})
                break
    return out


def select_tables(cfg: IndexerConfig, discovered: list[dict], row_counts) -> list[dict]:
    """Which of the matched tables this run will catalogue, and a record of what it left out.

    Kept separate from the scan so the decision can be reasoned about (and tested) without a database:
    it is the decision that made a customer's schema look half-empty.
    """
    cfg.discovered_tables = len(discovered)
    cfg.truncated_tables = []
    if not int(cfg.max_tables) or len(discovered) <= int(cfg.max_tables):
        return discovered
    # If a cap has to bite, it must drop the least-carrying tables, not the ones whose name happens
    # to sort last. Row counts come from the partition stats DMV; an account without VIEW DATABASE
    # STATE simply gets the alphabetical order it had before — but now the run says what it dropped.
    try:
        counts = row_counts() or {}
    except Exception:
        # No permission to read the stats DMV. Ranking degrades to the name order; losing the ranking
        # must never cost the customer the scan itself.
        counts = {}
    ordered = sorted(
        discovered,
        key=lambda t: (-counts.get((t["TABLE_SCHEMA"], t["TABLE_NAME"]), 0), t["TABLE_SCHEMA"], t["TABLE_NAME"]),
    )
    cap = int(cfg.max_tables)
    cfg.truncated_tables = [f'{t["TABLE_SCHEMA"]}.{t["TABLE_NAME"]}' for t in ordered[cap:]]
    print(
        f"[schema-indexer] WARNING: scope matched {len(discovered)} tables, cap is {cap} — "
        f"cataloguing the {cap} largest, {len(cfg.truncated_tables)} left out "
        f"(raise BI_SCHEMA_MAX_TABLES or narrow table_patterns)"
    )
    return ordered[:cap]


def scan_metadata_mssql(cfg: IndexerConfig) -> tuple[list[TableMeta], list[RelationshipMeta]]:
    conn = connect_mssql(cfg)
    tables: list[TableMeta] = []
    relationships: list[RelationshipMeta] = []
    try:
        cur = conn.cursor()
        schemas = [s for s in cfg.schemas if s.lower() != "public"] or ["dbo"]
        patterns = _patterns(cfg)
        where = ["TABLE_SCHEMA IN (" + ",".join("%s" for _ in schemas) + ")", "TABLE_TYPE IN ('BASE TABLE','VIEW')"]
        params: list[Any] = list(schemas)
        if patterns:
            where.append("(" + " OR ".join("TABLE_NAME LIKE %s" for _ in patterns) + ")")
            params.extend(patterns)
        # Every table the scope matches, with no TOP. `TOP n ... ORDER BY TABLE_NAME` cut a Logo
        # database off mid-alphabet — the scan stopped inside LG_<firm>_<period>_C% and ITEMS, STLINE
        # and STFICHE were never seen — and the report said nothing, so the catalogue silently
        # disagreed with the database.
        cur.execute(
            f"SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE "
            f"FROM INFORMATION_SCHEMA.TABLES WHERE {' AND '.join(where)} ORDER BY TABLE_SCHEMA, TABLE_NAME",
            tuple(params),
        )
        raw_tables = select_tables(cfg, list(cur.fetchall()), lambda: _row_count_map(cur))

        # Extended properties (MS_Description) if the customer documented anything.
        descs: dict[tuple[str, str, str], str] = {}
        try:
            cur.execute(
                """
                SELECT s.name AS sch, o.name AS tbl, ISNULL(c.name, '') AS col, CAST(ep.value AS NVARCHAR(4000)) AS val
                FROM sys.extended_properties ep
                JOIN sys.objects o ON o.object_id = ep.major_id
                JOIN sys.schemas s ON s.schema_id = o.schema_id
                LEFT JOIN sys.columns c ON c.object_id = ep.major_id AND c.column_id = ep.minor_id
                WHERE ep.name = 'MS_Description'
                """
            )
            for r in cur.fetchall():
                descs[(r["sch"], r["tbl"], r["col"])] = str(r["val"] or "")
        except Exception:
            descs = {}

        for t in raw_tables:
            schema, name, ttype = t["TABLE_SCHEMA"], t["TABLE_NAME"], t["TABLE_TYPE"]
            cur.execute(
                """
                SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, ORDINAL_POSITION,
                       CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION, NUMERIC_SCALE
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION
                """,
                (schema, name),
            )
            cols_raw = list(cur.fetchall())
            cur.execute(
                """
                SELECT kcu.COLUMN_NAME
                FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
                  ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME AND tc.TABLE_SCHEMA = kcu.TABLE_SCHEMA
                WHERE tc.TABLE_SCHEMA=%s AND tc.TABLE_NAME=%s AND tc.CONSTRAINT_TYPE='PRIMARY KEY'
                ORDER BY kcu.ORDINAL_POSITION
                """,
                (schema, name),
            )
            pks = [r["COLUMN_NAME"] for r in cur.fetchall()]
            cur.execute(
                """
                SELECT pc.name AS column_name, rs.name AS foreign_table_schema, rt.name AS foreign_table_name, rc.name AS foreign_column_name
                FROM sys.foreign_key_columns fkc
                JOIN sys.objects pt ON pt.object_id = fkc.parent_object_id
                JOIN sys.schemas ps ON ps.schema_id = pt.schema_id
                JOIN sys.columns pc ON pc.object_id = fkc.parent_object_id AND pc.column_id = fkc.parent_column_id
                JOIN sys.objects rt ON rt.object_id = fkc.referenced_object_id
                JOIN sys.schemas rs ON rs.schema_id = rt.schema_id
                JOIN sys.columns rc ON rc.object_id = fkc.referenced_object_id AND rc.column_id = fkc.referenced_column_id
                WHERE ps.name=%s AND pt.name=%s
                """,
                (schema, name),
            )
            fks: list[ForeignKey] = []
            for r in cur.fetchall():
                fk = ForeignKey(
                    column=r["column_name"],
                    target_schema=r["foreign_table_schema"],
                    target_table=r["foreign_table_name"],
                    target_column=r["foreign_column_name"],
                )
                fks.append(fk)
                relationships.append(
                    RelationshipMeta(
                        from_schema=schema, from_table=name, from_column=fk.column,
                        to_schema=fk.target_schema, to_table=fk.target_table, to_column=fk.target_column,
                    )
                )
            # Logo enforces its keys in the application, so the constraint query above returns
            # nothing for every table it owns. The dictionary's unique indexes name the key instead.
            if not pks:
                pks = _dictionary_key(name, [c["COLUMN_NAME"] for c in cols_raw])

            # Logo declares no foreign keys, so an honest FK query returns nothing and the join graph
            # is empty. The vendor dictionary carries the whole graph — every *REF column and what it
            # points at — which is the difference between joining two tables and joining the schema.
            if not fks:
                present = {r["TABLE_NAME"].upper() for r in raw_tables if r["TABLE_SCHEMA"] == schema}
                for link in _dictionary_links(name, [c["COLUMN_NAME"] for c in cols_raw], present):
                    relationships.append(
                        RelationshipMeta(
                            from_schema=schema, from_table=name, from_column=link["column"],
                            to_schema=schema, to_table=link["table"], to_column=link["to_column"],
                        )
                    )
                    fks.append(ForeignKey(column=link["column"], target_schema=schema, target_table=link["table"], target_column=link["to_column"]))

            columns: list[ColumnMeta] = []
            for c in cols_raw:
                cname = c["COLUMN_NAME"]
                columns.append(
                    ColumnMeta(
                        schema_name=schema,
                        table_name=name,
                        column_name=cname,
                        data_type=str(c["DATA_TYPE"]),
                        nullable=str(c["IS_NULLABLE"]).upper() == "YES",
                        ordinal=int(c["ORDINAL_POSITION"]),
                        is_pk=cname in pks,
                        description=descs.get((schema, name, cname)) or _col_desc(cname, name),
                        udt_name=str(c["DATA_TYPE"]),
                        max_length=c.get("CHARACTER_MAXIMUM_LENGTH"),
                        precision=c.get("NUMERIC_PRECISION"),
                        scale=c.get("NUMERIC_SCALE"),
                        type_display=_type_display(str(c["DATA_TYPE"]), c.get("CHARACTER_MAXIMUM_LENGTH"), c.get("NUMERIC_PRECISION"), c.get("NUMERIC_SCALE")),
                    )
                )
            tables.append(
                TableMeta(
                    schema_name=schema,
                    table_name=name,
                    table_type=ttype,
                    description=descs.get((schema, name, "")) or _table_desc(name),
                    primary_key=pks,
                    foreign_keys=fks,
                    columns=columns,
                )
            )
    finally:
        conn.close()
    return tables, relationships


def profile_mssql(cfg: IndexerConfig, tables: list[TableMeta]) -> list[TableMeta]:
    """Row counts from partition stats (cheap) + MIN/MAX of the first DATETIME column."""
    if cfg.skip_profile:
        return tables
    conn = connect_mssql(cfg)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT s.name AS sch, o.name AS tbl, SUM(ps.row_count) AS cnt
            FROM sys.dm_db_partition_stats ps
            JOIN sys.objects o ON o.object_id = ps.object_id
            JOIN sys.schemas s ON s.schema_id = o.schema_id
            WHERE ps.index_id IN (0, 1)
            GROUP BY s.name, o.name
            """
        )
        counts = {(r["sch"], r["tbl"]): int(r["cnt"] or 0) for r in cur.fetchall()}
        for t in tables:
            if t.table_type != "BASE TABLE":
                continue
            t.row_count = counts.get((t.schema_name, t.table_name))
            date_cols = [c.column_name for c in t.columns if c.data_type.lower() in ("date", "datetime", "datetime2", "smalldatetime")]
            if date_cols and (t.row_count or 0) > 0:
                col = date_cols[0]
                try:
                    cur.execute(f"SELECT CONVERT(varchar(10), MIN([{col}]), 120) AS mn, CONVERT(varchar(10), MAX([{col}]), 120) AS mx FROM [{t.schema_name}].[{t.table_name}] WHERE [{col}] > '1900-01-02'")
                    r = cur.fetchone()
                    if r:
                        t.date_min, t.date_max = r["mn"], r["mx"]
                except Exception:
                    pass
    finally:
        conn.close()
    return tables
