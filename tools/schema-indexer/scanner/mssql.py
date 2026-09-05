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

import re
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


def _logo_base(table_name: str) -> str:
    m = _LOGO_NAME.match(table_name.upper())
    return m.group("base") if m else table_name.upper()


def _table_desc(table_name: str) -> str:
    base = _logo_base(table_name)
    if base in _LOGO_TABLE_DESC:
        return _LOGO_TABLE_DESC[base]
    if table_name.upper().startswith("L_CAPI"):
        return _LOGO_TABLE_DESC.get(table_name.upper()[2:], "")
    return ""


def _col_desc(column: str) -> str:
    return _LOGO_COLUMN_DESC.get(column.upper(), "")


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
        cur.execute(
            f"SELECT TOP {int(cfg.max_tables)} TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE "
            f"FROM INFORMATION_SCHEMA.TABLES WHERE {' AND '.join(where)} ORDER BY TABLE_SCHEMA, TABLE_NAME",
            tuple(params),
        )
        raw_tables = list(cur.fetchall())

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
            # ERP databases rarely declare FKs; derive the well-known *REF links from naming.
            if not fks:
                base = _logo_base(name)
                prefix = name[: len(name) - len(base)] if name.upper().endswith(base) else ""
                firm_prefix = re.sub(r"(\d+_)$", "", prefix) if re.search(r"LG_\d+_\d+_$", prefix) else prefix
                link_targets = {"CLIENTREF": "CLCARD", "STOCKREF": "ITEMS", "INVOICEREF": "INVOICE", "STFICHEREF": "STFICHE", "ORDFICHEREF": "ORFICHE", "SALESMANREF": "SLSMAN", "ACCOUNTREF": "EMUHACC"}
                names_in_scan = {(r["TABLE_SCHEMA"], r["TABLE_NAME"]) for r in raw_tables}
                for c in cols_raw:
                    cname = c["COLUMN_NAME"].upper()
                    if cname in link_targets:
                        tgt_base = link_targets[cname]
                        candidates = [f"{prefix}{tgt_base}", f"{firm_prefix}{tgt_base}"]
                        for cand in candidates:
                            if (schema, cand) in names_in_scan:
                                relationships.append(
                                    RelationshipMeta(from_schema=schema, from_table=name, from_column=c["COLUMN_NAME"], to_schema=schema, to_table=cand, to_column="LOGICALREF")
                                )
                                fks.append(ForeignKey(column=c["COLUMN_NAME"], target_schema=schema, target_table=cand, target_column="LOGICALREF"))
                                break

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
                        description=descs.get((schema, name, cname)) or _col_desc(cname),
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
