"""Read-only contract executor. Physical source selection never uses sampled date ranges.

No SQL provided by the model reaches this module. Source periods are disjoint, each
aggregate has a declared grain, and cross-source enrichment is many-to-one or fails.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
import hashlib
import json
import os
import random
import re
import time

import sqlglot
from sqlglot import exp
from .contracts import METRICS, ContractError

MAX_ROWS = 250_000
CRM = "[Timas_MSCRM].[dbo]"


def literal(value):
    return "N'" + str(value).replace("'", "''") + "'"


def number(value):
    return Decimal(str(value or 0))


class Executor:
    def __init__(self, runtime):
        self.rt = runtime
        self.runs = []
        self.notes = []
        self.source_periods = []
        self.read_retries = []
        self._crm_status = {}

    def read(self, sql, *, metadata=False, source="logo"):
        statements = sqlglot.parse(sql, read="tsql")
        if len(statements) != 1 or not isinstance(statements[0], exp.Select) or any(
            node.key in {"insert", "update", "delete", "merge", "create", "drop", "alter", "into", "command"}
            for node in statements[0].walk()
        ):
            raise ContractError("Sözleşme sorgusu salt okuma denetimini geçemedi.")
        if not metadata:
            # Existing authorization is an integration boundary, not an input to the new planner.
            self.rt._check_data_scope(sql)
        conn = self.rt.crm_connector if source == "crm" else self.rt.connector
        if conn is None:
            raise ContractError("İstenen veri kaynağının bağlantısı tanımlı değil.")
        if source == "crm":
            # Keep the transport pool and its concurrency gate, not the legacy SQL rewriter.
            # Every business CRM read below explicitly applies this engine's positive status contract.
            conn = getattr(conn, "inner", conn)
        t = time.monotonic()
        for attempt in range(3):
            try:
                cols, rows, truncated = conn.execute(sql, MAX_ROWS)
                break
            except Exception as exc:
                args = getattr(exc, "args", ())
                # SQL Server explicitly rolled back a deadlock victim. Only
                # this known transient error may repeat this read-only SELECT.
                if not args or args[0] not in ("40001", "42000") or "(1205)" not in str(exc):
                    raise
                delay = (0.25 * (2 ** attempt) + random.uniform(0, 0.15)) if attempt < 2 else None
                self.read_retries.append({"source": source, "sqlSha256": hashlib.sha256(sql.encode()).hexdigest(),
                                          "failedAttempt": attempt + 1, "errorCode": 1205,
                                          "retryAfterMs": round(delay * 1000) if delay is not None else None})
                if delay is None:
                    raise
                time.sleep(delay)
        ms = round((time.monotonic() - t) * 1000)
        if truncated:
            raise ContractError("Tam sonuç okuma sınırını aştı; eksik sonuç cevap olarak sunulmadı.")
        if not metadata:
            self.runs.append({"source": source, "sql": sql, "rows": len(rows), "dbMs": ms, "attempts": attempt + 1})
        return rows

    def partitions(self, start, end):
        included = {int(x) for x in os.environ.get("SEMANTIC_FIRMS", "").split(",") if x.strip().isdigit()}
        excluded = {int(x) for x in os.environ.get("SEMANTIC_EXCLUDE_CONTEXT", "").split(",") if x.strip().isdigit()}
        if not included:
            raise ContractError("Bu şirketin Logo kaynak kapsamı tanımlanmamış; teknik koddan şirket tahmini yapılmaz.")
        rows = self.read("SELECT FIRMNR, NR, BEGDATE, ENDDATE FROM L_CAPIPERIOD WHERE ACTIVE=1", metadata=True)
        selected = []
        for r in rows:
            if int(r["FIRMNR"]) not in included - excluded:
                continue
            a, b = date.fromisoformat(str(r["BEGDATE"])[:10]), date.fromisoformat(str(r["ENDDATE"])[:10]) + timedelta(days=1)
            if a < end and start < b:
                selected.append((max(a, start), min(b, end), f"{int(r['FIRMNR']):03d}", f"{int(r['NR']):02d}"))
        selected = sorted(set(selected))
        cursor = start
        for a, b, firm, period in selected:
            if a != cursor:
                raise ContractError("Logo dönem kaynakları örtüşüyor veya arada boşluk var; esas kaynak doğrulanmadan toplanamaz.")
            cursor = b
        if cursor != end:
            raise ContractError("İstenen dönemin tamamı için doğrulanmış Logo kaynağı bulunamadı.")
        self.source_periods.extend({"start": str(a), "end": str(b), "sourceCode": f, "periodCode": p} for a, b, f, p in selected)
        return selected

    def verify_schema(self, tables, source):
        """Check actual columns, rather than accepting a stale profile's invented name."""
        wanted = ",".join(literal(t) for t in tables)
        prefix = "[Timas_MSCRM]." if source == "crm" else ""
        rows = self.read(f"SELECT TABLE_NAME,COLUMN_NAME,DATA_TYPE FROM {prefix}INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME IN ({wanted})", metadata=True, source=source)
        found = {(r["TABLE_NAME"].lower(), r["COLUMN_NAME"].lower()): r["DATA_TYPE"] for r in rows}
        missing = [f"{t}.{c}" for t, cols in tables.items() for c in cols if (t.lower(), c.lower()) not in found]
        if missing:
            raise ContractError("Kaynak şema sözleşmeyle uyuşmuyor: " + ", ".join(missing))
        return found

    def crm_status(self, table, alias):
        from .language import fold
        if table not in self._crm_status:
            entity = {"new_kitapBase": "new_kitap", "ContactBase": "contact",
                      "AccountBase": "account", "new_markaBase": "new_marka"}[table]
            rows = self.read("SELECT DISTINCT M.AttributeValue AS code,M.Value AS label FROM "
                "[Timas_MSCRM].dbo.StringMapBase M JOIN [Timas_MSCRM].MetadataSchema.Entity E "
                "ON E.ObjectTypeCode=M.ObjectTypeCode AND E.ComponentState=0 "
                "WHERE M.AttributeName='statuscode' AND M.LangId=1055 AND E.LogicalName=" + literal(entity),
                metadata=True, source="crm")
            accepted = {"aktif musteri"} if table == "AccountBase" else {"aktif", "etkin"}
            codes = sorted({int(r["code"]) for r in rows if fold(r["label"]).strip() in accepted})
            if not codes:
                raise ContractError("CRM'nin yayımlanmış durum açıklamalarında istenen aktif kayıt tanımı bulunamadı.")
            self._crm_status[table] = codes
        return f"{alias}.statecode=0 AND {alias}.statuscode IN (" + ",".join(map(str,self._crm_status[table])) + ")"

    def crm_books(self):
        self.verify_schema({"new_kitapBase": ["new_stokkodu", "new_name", "new_yazartext", "new_yayineviid", "statecode", "statuscode"],
                            "new_markaBase": ["new_markaId", "new_name", "statecode", "statuscode"]}, "crm")
        book_active = self.crm_status("new_kitapBase", "k")
        publisher_active = self.crm_status("new_markaBase", "m")
        rows = self.read(f"SELECT LTRIM(RTRIM(k.new_stokkodu)) AS book_code, k.new_name AS book_name, "
                         f"NULLIF(LTRIM(RTRIM(k.new_yazartext)), '') AS author, m.new_name AS publisher "
                         f"FROM {CRM}.new_kitapBase k LEFT JOIN {CRM}.new_markaBase m "
                         f"ON m.new_markaId=k.new_yayineviid AND {publisher_active} "
                         f"WHERE {book_active} AND NULLIF(LTRIM(RTRIM(k.new_stokkodu)), '') IS NOT NULL", source="crm")
        books = {}
        for row in rows:
            key = str(row["book_code"]).strip().casefold()
            if key in books:
                raise ContractError("Aktif CRM kitaplarında stok kodu tekil değil; satışları çoğaltmamak için birleştirme durduruldu.")
            books[key] = row
        return books

    def execute(self, plan):
        family = METRICS[plan.metrics[0]].family
        if family.startswith("crm_"):
            table = {"crm_books": "new_kitapBase", "crm_authors": "ContactBase", "crm_customers": "AccountBase"}[family]
            self.verify_schema({table: ["statecode", "statuscode"] + (["new_yazarmi"] if family == "crm_authors" else [])}, "crm")
            where = self.crm_status(table, "r") + (" AND r.new_yazarmi=1" if family == "crm_authors" else "")
            rows = self.read(f"SELECT COUNT_BIG(*) AS [{plan.metrics[0]}] FROM {CRM}.[{table}] r WHERE {where}", source="crm")
            return rows
        enrichment = bool((set(plan.dimensions) | {d for d, _, _ in plan.filters}) & {"author", "publisher"})
        books = self.crm_books() if enrichment else {}
        answer = []
        for start, end in plan.periods:
            partials = []
            for a, b, firm, period in self.partitions(date.fromisoformat(start), date.fromisoformat(end)):
                partials.extend(self.aggregate(plan, family, a, b, firm, period, enrichment))
            before = {m: sum((number(r[m]) for r in partials), Decimal(0)) for m in plan.metrics}
            missing = 0
            empty_fields = {field: 0 for field in ("author", "publisher") if field in plan.dimensions}
            for row in partials:
                if enrichment:
                    card = books.get(str(row.get("book_code") or "").strip().casefold())
                    if card is None:
                        missing += 1
                    for field in ("author", "publisher"):
                        row[field] = card.get(field) if card else None
                        if field in empty_fields and not row[field]:
                            empty_fields[field] += 1
            after = {m: sum((number(r[m]) for r in partials), Decimal(0)) for m in plan.metrics}
            if before != after:
                raise ContractError("Kaynaklar birleştirildiğinde ölçü toplamları değişti; cevap engellendi.")
            if missing:
                self.notes.append(f"{missing} satış kırılımında aktif CRM kitap eşleşmesi yok; künye alanları boş bırakıldı, satışlar korunuyor.")
            for field, count in empty_fields.items():
                if count:
                    label = "yazar künyesi" if field == "author" else "yayınevi"
                    self.notes.append(f"{count} satış kırılımında {label} bilgisi bulunamadı; değer tahmin edilmedi.")
            # Enrichment filters explicitly narrow the population, after conservation was checked.
            selected = [r for r in partials if all(self.matches(r.get(d), op, value) for d, op, value in plan.filters if d in ("author", "publisher"))]
            group_fields = []
            for d in plan.dimensions:
                group_fields.extend(["book_code", "book_name"] if d == "book" else ["customer_code", "customer_name"] if d == "customer" else [d])
            totals = {}
            for r in selected:
                key = tuple(r.get(d) for d in group_fields)
                item = totals.setdefault(key, {**dict(zip(group_fields, key)), **{m: Decimal(0) for m in plan.metrics}})
                for m in plan.metrics:
                    item[m] += number(r[m])
            if not totals and not group_fields:
                totals[()] = {m: Decimal(0) for m in plan.metrics}
            rows = list(totals.values())
            rows.sort(key=lambda r: (number(r[plan.order_by]), str(tuple(r.get(k) for k in group_fields))), reverse=plan.descending)
            if plan.limit:
                rows = rows[:plan.limit]
            if len(plan.periods) > 1:
                rows = [{"period_start": start, "period_end_exclusive": end, **r} for r in rows]
            answer.extend(rows)
        return [{k: float(v) if isinstance(v, Decimal) else v for k, v in r.items()} for r in answer]

    @staticmethod
    def matches(value, op, wanted):
        from .language import fold
        a, b = fold(str(value or "")), fold(wanted)
        return a == b if op == "eq" else b in a

    def aggregate(self, plan, family, start, end, firm, period, enrichment):
        suffix = {"sales": "STLINE", "invoice": "INVOICE", "collection": "CLFLINE"}[family]
        table = f"LG_{firm}_{period}_{suffix}"
        item_table, client_table = f"LG_{firm}_ITEMS", f"LG_{firm}_CLCARD"
        dims = set(plan.dimensions) | {d for d, _, _ in plan.filters}
        book = "book" in dims or enrichment
        client = bool(dims & {"channel", "customer"}) or family == "collection"
        needed = {table: ["CANCELLED", "DATE_", "TRCODE"]}
        needed[table] += {"sales": ["LINETYPE", "INVOICEREF", "STOCKREF", "CLIENTREF", "LINENET", "AMOUNT"],
                          "invoice": ["LOGICALREF", "NETTOTAL", "CLIENTREF"],
                          "collection": ["CLIENTREF", "AMOUNT", "SIGN"]}[family]
        quantities = set(plan.metrics) & {"sold_quantity", "net_quantity"}
        if quantities:
            needed[table] += ["UINFO1", "UINFO2"]
        if book:
            needed[item_table] = ["LOGICALREF", "CODE", "NAME"]
        if client:
            needed[client_table] = ["LOGICALREF", "CODE", "DEFINITION_", "SPECODE2"]
        types = self.verify_schema(needed, "logo")
        measures = {"sales": ["AMOUNT", "LINENET"], "invoice": ["NETTOTAL"], "collection": ["AMOUNT"]}[family]
        for col in measures:
            if types[table.lower(), col.lower()] not in {"decimal", "numeric", "float", "real", "money", "smallmoney", "int", "bigint"}:
                raise ContractError("Finansal değer alanının veri türü sözleşmeyle uyuşmuyor.")
        labels = {}
        if book:
            labels.update(book_code="LTRIM(RTRIM(i.CODE))", book_name="i.NAME")
        if "channel" in dims:
            labels["channel"] = "c.SPECODE2"
        if "customer" in dims:
            labels.update(customer_code="c.CODE", customer_name="c.DEFINITION_")
        for d, expression in {"day": "CONVERT(varchar(10),f.DATE_,23)", "month": "CONVERT(varchar(7),f.DATE_,23)", "year": "YEAR(f.DATE_)"}.items():
            if d in plan.dimensions:
                labels[d] = expression
        select = [f"{expr} AS [{name}]" for name, expr in labels.items()]
        select += [f"COALESCE({METRICS[m].expression},0) AS [{m}]" for m in plan.metrics]
        if quantities:
            unit_codes = "2,3,7,8" if "net_quantity" in quantities else "7,8"
            select.append("COALESCE(SUM(CASE WHEN f.TRCODE IN (" + unit_codes + ") AND "
                          "(f.UINFO1 IS NULL OR f.UINFO2 IS NULL OR f.UINFO1<=0 OR f.UINFO1<>f.UINFO2) "
                          "THEN 1 ELSE 0 END),0) AS [_unverified_quantity_units]")
        sql = "SELECT " + ", ".join(select) + f" FROM dbo.[{table}] f"
        if book:
            sql += f" LEFT JOIN dbo.[{item_table}] i ON i.LOGICALREF=f.STOCKREF"
        if client:
            sql += f" LEFT JOIN dbo.[{client_table}] c ON c.LOGICALREF=f.CLIENTREF"
        conditions = ["f.CANCELLED=0", f"f.DATE_>='{start}'", f"f.DATE_<'{end}'"]
        if family == "sales":
            codes_by_metric = {"sold_quantity": {7,8}, "net_quantity": {2,3,7,8},
                               "sales_amount": {7,8,9}, "net_sales": {2,3,7,8,9}, "return_amount": {2,3}}
            transaction_codes = sorted(set().union(*(codes_by_metric[m] for m in plan.metrics)))
            conditions += ["f.LINETYPE=0", "f.INVOICEREF<>0", "f.TRCODE IN (" + ",".join(map(str,transaction_codes)) + ")"]
        elif family == "invoice":
            conditions += ["f.TRCODE IN (7,8,9)"]
        else:
            conditions += ["f.SIGN=1", "f.TRCODE IN (1,20,61,62,70)", "c.CODE LIKE '120%'"]
        if plan.sale_kind != "all":
            # Retail returns are 2, wholesale returns 3; do not silently discard returns from net metrics.
            codes = "(8,3)" if plan.sale_kind == "wholesale" and family == "sales" else "(7,2)" if family == "sales" else "(8)" if plan.sale_kind == "wholesale" else "(7)"
            conditions.append("f.TRCODE IN " + codes)
        for dim, op, value in plan.filters:
            if dim in ("author", "publisher"):
                continue
            exprs = {"book": ["i.CODE", "i.NAME"], "customer": ["c.CODE", "c.DEFINITION_"], "channel": ["c.SPECODE2"]}[dim]
            if op == "contains":
                escaped = value.replace("~", "~~").replace("%", "~%").replace("_", "~_").replace("[", "~[")
                pred = [f"{expr} LIKE {literal('%' + escaped + '%')} ESCAPE '~'" for expr in exprs]
            else:
                pred = [f"{expr}={literal(value)}" for expr in exprs]
            conditions.append("(" + " OR ".join(pred) + ")")
        sql += " WHERE " + " AND ".join(conditions)
        if labels:
            sql += " GROUP BY " + ", ".join(labels.values())
        rows = self.read(sql)
        if quantities:
            if any(number(row.get("_unverified_quantity_units")) for row in rows):
                raise ContractError("Satış miktarlarında farklı veya eksik birim dönüşümü var; işlem miktarı kitap adedi gibi sunulamaz. Birim sözleşmesi doğrulanmalıdır.")
            for row in rows:
                row.pop("_unverified_quantity_units", None)
        return rows
