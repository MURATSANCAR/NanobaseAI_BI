"""Read-only contract executor. Physical source selection never uses sampled date ranges.

No SQL provided by the model reaches this module. Source periods are disjoint, each
aggregate has a declared grain, and cross-source enrichment is many-to-one or fails.
"""
from __future__ import annotations
from collections import defaultdict
from dataclasses import replace
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
from semantic_layer.runtime import crm_active as active_rule
from .contracts import METRICS, SALES_INVOICE_CODES, TRANSACTION_CODES, ContractError, codes_sql
from . import operations
from .result_metadata import describe_columns, calculation_definitions, return_invoice_note

MAX_ROWS = 250_000
CRM_DB = "Timas_MSCRM"
CRM = f"[{CRM_DB}].[dbo]"


def literal(value):
    return "N'" + str(value).replace("'", "''") + "'"


#: Türkçe çekim ekleri (uzundan kısaya): «kitapyurduna», «D&R'dan», «Timaş Çocuk'un» gibi adlar ana kayıtta eksiz geçer.
_SUFFIXES = sorted({"nın", "nin", "nun", "nün", "ın", "in", "un", "ün", "ndan", "nden", "dan", "den", "tan", "ten",
                    "nda", "nde", "da", "de", "ta", "te", "na", "ne", "ya", "ye", "yla", "yle", "la", "le", "a", "e",
                    "ı", "i", "u", "ü", "lar", "ler", "ları", "leri", "larına", "lerine", "lara", "lere"}, key=len, reverse=True)


def name_stems(value):
    """Adın ek atılmış kökleri, uzundan kısaya; kesme işaretinden önceki kısım ilk aday (en az 3 harf)."""
    text = str(value or "").strip()
    out = []
    for sep in ("'", "’", "`"):
        if sep in text:
            out.append(text.split(sep)[0].strip())
    frontier = [text]
    for _ in range(2):
        nxt = []
        for word in frontier:
            low = word.lower()
            for suf in _SUFFIXES:
                if low.endswith(suf) and len(word) - len(suf) >= 3:
                    nxt.append(word[:-len(suf)])
        out.extend(nxt)
        frontier = nxt
    seen, stems = set(), []
    for stem in out:
        if stem and stem.lower() != text.lower() and stem.lower() not in seen:
            seen.add(stem.lower()); stems.append(stem)
    return stems


def number(value):
    return Decimal(str(value or 0))


# Logo stores an unentered date as NULL, 1899-12-30 (Delphi zero) or 1900-01-01
# (SQL Server zero). None of them is a business date: a due date of 1900-01-01
# would otherwise be ~46.000 days overdue. Every Logo vade/gecikme/as-of use goes
# through these two helpers; the boundary matches the golden references.
LOGO_FIRST_REAL_DATE = date(1901, 1, 1)


def logo_date_entered(column):
    """SQL predicate: the Logo date column holds a real, user-entered date."""
    return f"{column}>='{LOGO_FIRST_REAL_DATE:%Y%m%d}'"


def logo_date_text(column):
    """ISO day text of a Logo date column, NULL when the date was not entered."""
    return f"CASE WHEN {logo_date_entered(column)} THEN CONVERT(varchar(10),{column},23) END"


def logo_entered_date(value):
    """Python twin for values read back from Logo: a date, or None when not entered."""
    if value is None or value == "":
        return None
    day = value.date() if hasattr(value, "date") and callable(value.date) else value
    day = day if isinstance(day, date) else date.fromisoformat(str(day)[:10])
    return day if day >= LOGO_FIRST_REAL_DATE else None


class Executor:
    def __init__(self, runtime):
        self.rt = runtime
        self.runs = []
        self.notes = []
        self.source_periods = []
        self.read_retries = []
        self._crm_status = {}
        self._crm_policy = None
        self.output_fields = []
        self.coverage_complete = True
        self.section_results = []
        self.gaps = []
        # Return invoices measured beside an invoice count: [{start, end, returnInvoiceCount}].
        self.return_invoice_counts = []

    def read(self, sql, *, metadata=False, source="logo", passive_count=False):
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
            raise ContractError("İstenen veri kaynağının bağlantısı tanımlı değil.", code="SOURCE_UNAVAILABLE")
        if source == "crm":
            # Keep the transport pool and its concurrency gate, not the legacy SQL rewriter: evidence SQL
            # must be the executed SQL, and the rewriter passes unparsable SQL unfiltered. The same
            # passive-record rule is written into every query (crm_active) and verified here, fail closed.
            conn = getattr(conn, "inner", conn)
            if passive_count and not self.single_count(statements[0]):
                raise ContractError("Pasif kayıt sayımı yalnız tek bir sayı döndürebilir.", code="SOURCE_CONTRACT_VIOLATION")
            if not metadata and not passive_count:
                eligible, passive = self.crm_policy()
                missing = active_rule.missing(sql, eligible, passive)
                if missing:
                    raise ContractError("CRM okumasında pasif kayıt kuralı uygulanmamış: " + ", ".join(missing),
                                        code="SOURCE_CONTRACT_VIOLATION")
        t = time.monotonic()
        evidence = {"source": source, "sql": sql, "sqlSha256": hashlib.sha256(sql.encode()).hexdigest(),
                    "startedAt": time.time(), "status": "running", "rows": 0, "dbMs": 0}
        if not metadata:
            self.runs.append(evidence)
        for attempt in range(3):
            try:
                cols, rows, truncated = conn.execute(sql, MAX_ROWS)
                break
            except Exception as exc:
                evidence.update(status="failed", attempts=attempt+1, dbMs=round((time.monotonic()-t)*1000))
                args = getattr(exc, "args", ())
                # SQL Server explicitly rolled back a deadlock victim. Only
                # this known transient error may repeat this read-only SELECT.
                if not args or args[0] not in ("40001", "42000") or "(1205)" not in str(exc):
                    raise
                delay = (0.25 * (2 ** attempt) + random.uniform(0, 0.15)) if attempt < 2 else None
                self.read_retries.append({"source": source, "sqlSha256": hashlib.sha256(sql.encode()).hexdigest(),
                                          "failedAttempt": attempt + 1, "errorCode": 1205,
                                          "occurredAt": time.time(), "sqlState": args[0],
                                          "retryAfterMs": round(delay * 1000) if delay is not None else None})
                if delay is None:
                    raise
                time.sleep(delay)
        ms = round((time.monotonic() - t) * 1000)
        if truncated:
            raise ContractError("Tam sonuç okuma sınırını aştı; eksik sonuç cevap olarak sunulmadı.")
        evidence.update(status="complete", rows=len(rows), dbMs=ms, attempts=attempt+1)
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
            raise ContractError("Kaynak şema sözleşmeyle uyuşmuyor: " + ", ".join(missing), code="SOURCE_CONTRACT_VIOLATION")
        return found

    def crm_policy(self):
        """Tables with statecode and their 'Pasif…/Inactive…' status reasons, from live CRM metadata."""
        if self._crm_policy is None:
            wrapper = self.rt.crm_connector
            eligible, passive = frozenset(), {}
            if isinstance(wrapper, active_rule.ActiveOnly):
                eligible, passive = wrapper.eligible(), dict(wrapper._passive)
            if not eligible or not passive:
                # The wrapper degrades silently on metadata errors; this engine re-reads and fails closed.
                eligible = frozenset(str(r["name"]).lower() for r in self.read(active_rule.tables_sql(CRM_DB), metadata=True, source="crm") if r.get("name"))
                passive = {k: v for k, v in active_rule.passive_codes(self.read(active_rule.passive_sql(CRM_DB), metadata=True, source="crm")).items() if k in eligible}
            if not eligible:
                raise ContractError("CRM pasif kayıt kuralının tablo listesi okunamadı.", code="SOURCE_UNAVAILABLE")
            self._crm_policy = (eligible, passive)
        return self._crm_policy

    @staticmethod
    def single_count(select):
        """Pasif sayımının tek izinli biçimi: tek tablo, tek COUNT ifadesi, gruplama ve birleşim yok (kayıt dönmez)."""
        exprs = select.expressions
        return (len(exprs) == 1 and isinstance(exprs[0].unalias(), exp.Count) and not select.args.get("group")
                and not select.args.get("joins") and len(list(select.find_all(exp.Table))) == 1)

    #: Pasif sayımının kayıt türleri → CRM tablosu, ekran adı, türe özgü sabit koşul.
    PASSIVE_KINDS = {"customer": ("AccountBase", "müşteri", ""), "book": ("new_kitapBase", "kitap", ""),
                     "author": ("ContactBase", "yazar", " AND r.new_yazarmi=1"), "contract": ("new_sozlesmeBase", "sözleşme", "")}

    def passive_count(self, kind):
        """Kurum kuralı: pasif CRM kaydı listelenmez; açık istekte yalnız sayısı. Pasif = aktif kuralının tersi
        (statecode≠0 ya da «Pasif…/Inactive…» durum nedeni), okuma kapısındaki tanımın aynısı."""
        if kind not in self.PASSIVE_KINDS:
            raise ContractError("Pasif sayımı bu kayıt türü için tanımlı değil.")
        table, label, extra = self.PASSIVE_KINDS[kind]
        self.verify_schema({table: ["statecode", "statuscode"] + (["new_yazarmi"] if kind == "author" else [])}, "crm")
        eligible, passive = self.crm_policy()
        if table.lower() not in eligible:
            raise ContractError("Bu kayıt türünde aktif/pasif durumu tutulmuyor.")
        where = f"NOT ({active_rule.predicate(table, 'r', passive)}){extra}"
        rows = self.read(f"SELECT COUNT_BIG(*) AS [passive_records] FROM {CRM}.[{table}] r WHERE {where}",
                         source="crm", passive_count=True)
        self.output_fields, self.numeric_fields = ["passive_records"], {"passive_records"}
        self.notes.append(f"Pasif {label} kayıtları kurum kuralı gereği listelenmez; yalnız sayısı verilir. "
                          "Sayı kayıtların bugünkü durumudur, pasife alınma tarihi sorgulanmaz.")
        return [{"passive_records": int(rows[0]["passive_records"] or 0) if rows else 0}]

    def crm_active(self, table, alias):
        """User rule: no passive CRM record anywhere (LEFT targets too). '1=1' for tables without statecode."""
        eligible, passive = self.crm_policy()
        return active_rule.predicate(table, alias, passive) if table.lower() in eligible else "1=1"

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

    def crm_dimension_books(self, plan):
        requested = set(plan.dimensions) | {d for d, _, _ in plan.filters}
        if not requested & {"subbrand", "author_group"}:
            return self.crm_books()
        from .crm_reports import Sources
        import json
        sources = Sources(self)
        cards = sources.books()
        links = sources.author_links() if "author_group" in requested else {}
        people = sources.people() if "author_group" in requested else {}
        incomplete_authors = set()
        if "author_group" in requested:
            broken = self.read("SELECT DISTINCT L.new_Kitap AS book_id FROM " + CRM + ".new_eserkatilimBase L JOIN " + CRM + ".new_katilimcitipiBase R ON R.new_katilimcitipiId=L.new_katilimciTipi AND " + self.crm_active("new_katilimcitipiBase", "R") + " AND LTRIM(RTRIM(R.new_name))=N'Yazar' LEFT JOIN " + CRM + ".ContactBase C ON C.ContactId=L.new_Katilimsaglayan AND " + self.crm_status("ContactBase", "C") + " WHERE " + self.crm_active("new_eserkatilimBase", "L") + " AND C.ContactId IS NULL", source="crm")
            incomplete_authors = {str(r["book_id"]).strip().lower() for r in broken if r["book_id"]} & set(cards)
            if incomplete_authors:
                self.coverage_complete = False
                self.gaps.append({"status": "INCOMPLETE_SOURCE_COVERAGE", "reason": f"{len(incomplete_authors)} aktif kitapta Yazar katılımının aktif kişi kimliği çözülemedi; kısmi kişi kümesi tam grup sayılmadı, satış boş yazar grubunda korundu."})
        books, ambiguous = {}, set()
        for bid, card in cards.items():
            code = str(card.get("book_code") or "").strip().casefold()
            if not code:
                continue
            if code in books or code in ambiguous:
                books.pop(code, None)
                ambiguous.add(code)
                continue
            ids = sorted(links.get(bid, ())) if bid not in incomplete_authors else []
            books[code] = {**card, "author":card.get("author_text"),
                "subbrand_id": str(card["subbrand_id"]).lower() if card.get("subbrand") and card.get("subbrand_id") else None,
                "author_group_ids": json.dumps(ids, ensure_ascii=False) if ids else None,
                "author_group_names": json.dumps([people[pid].get("person_name") for pid in ids], ensure_ascii=False) if ids else None}
        if ambiguous:
            self.coverage_complete = False
            self.gaps.append({"status": "AMBIGUOUS_SOURCE_IDENTITY", "reason": f"{len(ambiguous)} stok kodu birden çok aktif CRM kitabına bağlı; bu kodların satışları korunur, CRM kırılımları boş bırakılır."})
        self.notes.append("Alt marka ve yazar kişi grubu güncel CRM ilişkileridir; geçmiş dönem ilişki tarihçesi olarak yorumlanmaz. Ortak yazarlı kitap satışı kişi grubunda bir kez sayılır.")
        return books

    def execute(self, plan):
        self.gaps.extend(getattr(plan, "gaps", ()))
        if self.gaps:
            self.coverage_complete = False
        if getattr(plan, "sections", ()):
            overview = []
            for index, leaf in enumerate(plan.sections):
                child = Executor(self.rt)
                title = leaf.section_title or f"Bölüm {index+1}"
                section = {"title": title, "index": index, "status": "COMPLETE", "columns": [], "records": [], "totalRows": 0, "truncated": False}
                try:
                    records = child.execute(leaf)
                    if sum(s["totalRows"] for s in self.section_results) + len(records) > MAX_ROWS:
                        raise ContractError("Rapor bölümleri tam sonuç sınırını aşıyor; dönem veya kapsam daraltılmalı.")
                    fields = list(records[0]) if records else child.output_fields
                    numeric = set(getattr(child, "numeric_fields", ())) | set(leaf.metrics)
                    if leaf.comparison:
                        numeric -= set(leaf.metrics)
                    if any(set(row) != set(fields) for row in records) or not numeric <= set(fields):
                        raise ContractError("Rapor bölümünün kolonları hesap sözleşmesini sağlamıyor.", code="SOURCE_CONTRACT_VIOLATION")
                    section.update(records=records, totalRows=len(records), columns=describe_columns(leaf, fields, numeric))
                    if child.gaps or not child.coverage_complete:
                        section["status"] = "PARTIAL"
                        section["gaps"] = child.gaps
                        self.gaps.extend({**gap, "reason": title + ": " + gap["reason"]} for gap in child.gaps)
                        if not child.gaps:
                            self.gaps.append({"status": "INCOMPLETE_SOURCE_COVERAGE", "reason": title + ": kaynak eşleşmelerinin bir kısmı eksik; bölümün veri notlarına bakın."})
                except ContractError as exc:
                    section.update(status=exc.code, explanation=str(exc))
                    self.gaps.append({"status": exc.code, "reason": title + ": " + str(exc)})
                finally:
                    self.runs.extend(child.runs)
                    self.read_retries.extend(child.read_retries)
                    self.source_periods.extend(child.source_periods)
                    self.return_invoice_counts.extend(child.return_invoice_counts)
                    self.notes.extend(title + ": " + n for n in child.notes)
                    self.coverage_complete &= child.coverage_complete
                section["sourceExecutions"] = child.runs
                section["sourceComplete"] = child.coverage_complete and not section.get("explanation")
                section["dataNotes"] = [{"message": n, "severity": "info" if child.coverage_complete else "warn"} for n in dict.fromkeys(child.notes)]
                section["dataCoverage"] = child.source_periods
                section["definitions"] = calculation_definitions(leaf)
                self.section_results.append(section)
                overview.append({"section": title, "status": section["status"], "row_count": section["totalRows"]})
            if self.gaps:
                self.coverage_complete = False
            self.output_fields = ["section", "status", "row_count"]
            self.numeric_fields = {"row_count"}
            return overview
        if getattr(plan, "passive_count", None):
            return self.passive_count(plan.passive_count)
        if getattr(plan, "relational_query", None):
            from .relational_executor import execute_relational_query
            return self.report_result(execute_relational_query(self, plan.relational_query))
        if getattr(plan, "crm_report", None):
            from .crm_reports import execute_crm_report
            return self.report_result(execute_crm_report(self, plan.crm_report))
        if getattr(plan, "logo_report", None):
            from .logo_reports import execute_logo_report
            return self.report_result(execute_logo_report(self, plan.logo_report))
        if getattr(plan, "crm", None):
            from .crm_query import execute_crm_plan
            return execute_crm_plan(self, plan.crm)
        family = METRICS[plan.metrics[0]].family
        if family.startswith("crm_"):
            table = {"crm_books": "new_kitapBase", "crm_authors": "ContactBase", "crm_customers": "AccountBase"}[family]
            self.verify_schema({table: ["statecode", "statuscode"] + (["new_yazarmi"] if family == "crm_authors" else [])}, "crm")
            where = self.crm_status(table, "r") + (" AND r.new_yazarmi=1" if family == "crm_authors" else "")
            rows = self.read(f"SELECT COUNT_BIG(*) AS [{plan.metrics[0]}] FROM {CRM}.[{table}] r WHERE {where}", source="crm")
            return rows
        enrichment = bool((set(plan.dimensions) | {d for d, _, _ in plan.filters}) & {"author", "publisher", "subbrand", "author_group"})
        books = self.crm_dimension_books(plan) if enrichment else {}
        if enrichment and any(d in ("author", "publisher", "subbrand") for d, _, _ in plan.filters):
            plan = replace(plan, filters=tuple(self.resolve_card_filter(books, f) for f in plan.filters))
        from . import crm_book_scope
        crm_scope = getattr(plan, "crm_books", None)
        scope_books = crm_book_scope.run(self, crm_scope) if crm_scope else None
        scope_values = list(crm_scope["values"]) if crm_scope else []
        if scope_books is not None and any(h.metric in scope_values for h in plan.having):
            # Kitap başına CRM sayısına konan koşul («yazar sayısı ≥ 2», «hedefi 1000 üstü») kitap seçer: toplamın değil
            # her kitabın sayısına uygulanır, satış yalnız seçilen kitaplarda toplanır.
            scope_books = crm_book_scope.select(scope_books, [h for h in plan.having if h.metric in scope_values])
            plan = replace(plan, having=tuple(h for h in plan.having if h.metric not in scope_values))
        scope_sold = set()
        answer = []
        period_rows = []
        group_fields = []
        for d in plan.dimensions:
            group_fields.extend(["book_code", "book_name"] if d == "book" else ["customer_code", "customer_name"] if d == "customer" else ["subbrand_id", "subbrand"] if d == "subbrand" else ["author_group_ids", "author_group_names"] if d == "author_group" else
                                list(crm_scope["attributes"]) if d == "crm_attribute" else [d])
        returns_probe = self.returns_probe(plan)
        return_counts = []
        for start, end in plan.periods:
            partials = []
            returns = Decimal(0)
            for a, b, firm, period in self.partitions(date.fromisoformat(start), date.fromisoformat(end)):
                partials.extend(self.aggregate_families(plan, a, b, firm, period, enrichment or scope_books is not None))
                if returns_probe:
                    returns += sum((number(r["return_invoice_count"]) for r in self.aggregate(returns_probe, "invoice", a, b, firm, period, False)), Decimal(0))
            if returns_probe:
                return_counts.append((start, end, int(returns)))
            before = {m: sum((number(r[m]) for r in partials), Decimal(0)) for m in plan.metrics}
            missing = 0
            empty_fields = {field: 0 for field in ("author", "publisher", "subbrand", "author_group_ids") if field in group_fields}
            # A matched card whose author text is empty has no author in the source (teacher guides,
            # badges, magazines, compiled works: measured 2026-10-01). That is a fact about the product,
            # not a coverage gap; a missing or non-active card stays a gap.
            authorless = 0
            missing_codes, missing_amount = set(), Decimal(0)
            for row in partials:
                if enrichment:
                    card = books.get(str(row.get("book_code") or "").strip().casefold())
                    if card is None:
                        missing += 1
                        missing_codes.add(str(row.get("book_code") or "").strip())
                        missing_amount += number(row.get(plan.metrics[0]))
                    for field in ("author", "publisher", "subbrand_id", "subbrand", "author_group_ids", "author_group_names"):
                        row[field] = card.get(field) if card else None
                        if field in empty_fields and not row[field]:
                            if field == "author" and card is not None:
                                authorless += 1
                            else:
                                empty_fields[field] += 1
            after = {m: sum((number(r[m]) for r in partials), Decimal(0)) for m in plan.metrics}
            if before != after:
                raise ContractError("Kaynaklar birleştirildiğinde ölçü toplamları değişti; cevap engellendi.")
            if missing:
                self.coverage_complete = False
                total = before[plan.metrics[0]]
                share = f" (%{missing_amount / total * 100:.1f})".replace(".", ",") if total else ""
                amount = f"{missing_amount:,.2f}".replace(",", "~").replace(".", ",").replace("~", ".")
                self.notes.append(f"{len(missing_codes)} kitabın CRM'de aktif kartı yok (kart pasif ya da hiç açılmamış); bu kitapların "
                                  f"{METRICS[plan.metrics[0]].label.lower()} {amount}{share} yazar/yayınevine bağlanamadı ve «bilinmiyor» "
                                  "satırında gösterildi. Toplam etkilenmez.")
            if authorless:
                self.notes.append(f"{authorless} satış kırılımında kitap kartı var ama kaynakta yazar alanı boş (kılavuz, dergi, derleme gibi yazarsız ürün); yazar boş gösterildi.")
            for field, count in empty_fields.items():
                if count:
                    self.coverage_complete = False
                    label = {"author":"yazar künyesi", "publisher":"yayınevi", "subbrand":"alt marka", "author_group_ids":"gerçek yazar kişi grubu"}[field]
                    self.notes.append(f"{count} satış kırılımında {label} bilgisi bulunamadı; değer tahmin edilmedi.")
            # Enrichment filters explicitly narrow the population, after conservation was checked.
            selected = [r for r in partials if all(self.matches(r.get(d), op, value) for d, op, value in plan.filters if d in ("author", "publisher", "subbrand"))]
            if scope_books is not None:
                selected = self.apply_crm_book_scope(selected, scope_books, crm_scope, plan, scope_sold)
            totals = {}
            for r in selected:
                key = tuple(r.get(d) for d in group_fields)
                item = totals.setdefault(key, {**dict(zip(group_fields, key)), **{m: Decimal(0) for m in plan.metrics}})
                for m in plan.metrics:
                    item[m] += number(r[m])
                if scope_values:
                    item.setdefault("_books", set()).add(crm_book_scope.key(r.get("book_code")))
            if not totals and not group_fields:
                totals[()] = {m: Decimal(0) for m in plan.metrics}
            for item in totals.values():
                if scope_values:
                    # Kitap başına CRM sayısı grubun kitaplarında bir kez toplanır; satış satırı sayısı onu çoğaltmaz.
                    codes = item.pop("_books", set())
                    for v in scope_values:
                        found = [scope_books[c]["values"].get(v) for c in codes if c in scope_books]
                        item[v] = sum((x for x in found if x is not None), Decimal(0)) if any(x is not None for x in found) else None
            rows = operations.derived(list(totals.values()), plan.derived)
            rows = operations.analytics(rows, getattr(plan, "analytics", ()), plan.metrics, group_fields)
            period_rows.append(rows)
            if plan.comparison:
                continue
            rows = operations.finish(rows, plan, group_fields)
            if len(plan.periods) > 1:
                rows = [{"period_start": start, "period_end_exclusive": end, **r} for r in rows]
            answer.extend(rows)
        if plan.comparison:
            answer = operations.finish(operations.compare(period_rows, plan, group_fields), plan, group_fields)
            self.output_fields = [*group_fields, "base_period_start", "base_period_end_exclusive",
                                  "target_period_start", "target_period_end_exclusive", "base_value", "target_value", plan.comparison.id]
        else:
            self.output_fields = (["period_start", "period_end_exclusive"] if len(plan.periods)>1 else []) + group_fields + list(plan.metrics) + scope_values + [d.id for d in plan.derived]
            for spec in getattr(plan, "analytics", ()):
                self.output_fields += [spec["id"]+suffix for suffix in ("_group_total", "_share_pct", "_cumulative_pct")] if spec["op"] == "contribution" else ["row_kind"]
        from .logo_codes import CODED
        from .logo_fields import FIELDS
        # Fiyat farkı notu yalnız müşteri/kanal süzgecini taşır; kart kolonu süzgecinde (il, temsilci…) not yanlış tutar verirdi.
        if family == "sales" and set(plan.metrics) & {"net_sales", "sales_amount"} and not any(d in CODED or d in FIELDS for d, _, _ in plan.filters):
            self.price_difference_note(plan)
        if family in ("sales", "invoice"):
            self.cancelled_coded_note(plan)
        if plan.derived or plan.comparison:
            self.notes.append("Oran veya yüzde değişim hesabında sıfır/eksik payda boş gösterilir; dönemde bulunmayan kırılım sıfır varsayılmaz.")
        if returns_probe:
            self.return_invoice_counts = [{"start": a, "end": b, "returnInvoiceCount": n} for a, b, n in return_counts]
            self.notes.append(return_invoice_note(return_counts, bool(plan.filters) or plan.sale_kind != "all"))
        if scope_books is not None:
            self.notes.append(crm_book_scope.coverage_note(scope_books, scope_sold))
        self.numeric_fields = {k for k in self.output_fields if k in plan.metrics or k in scope_values or k in {d.id for d in plan.derived}}
        if plan.comparison:
            self.numeric_fields.update(("base_value", "target_value", plan.comparison.id))
        for spec in getattr(plan, "analytics", ()):
            if spec["op"] == "contribution":
                self.numeric_fields.update(spec["id"]+suffix for suffix in ("_group_total", "_share_pct", "_cumulative_pct"))
        return [{k: float(v) if isinstance(v, Decimal) else v for k, v in r.items()} for r in answer]

    def resolve_card_filter(self, books, item):
        """Yazar/yayınevi süzgeci CRM kartındaki adla birebir tutmazsa («Metin Özdamar» ↔ «Metin Özdamarlar») içerme, sonra
        eki atılmış kök denenir; hiçbir kart yoksa «0» değil «bulunamadı» (Logo ad süzgeciyle aynı kural)."""
        dim, op, value = item
        if dim not in ("author", "publisher", "subbrand"):
            return item
        names = {str(card.get(dim) or "") for card in books.values() if card.get(dim)}
        for o, v in [(op, value)] + ([("contains", value)] if op == "eq" else []) + [("contains", stem) for stem in name_stems(value)]:
            found = sorted(n for n in names if self.matches(n, o, v))
            if found:
                if (o, v) != (op, value):
                    label = {"author": "yazar", "publisher": "yayınevi", "subbrand": "alt marka"}[dim]
                    self.notes.append(f"«{value}» {label} adı CRM'de " + ", ".join(f"«{n}»" for n in found[:5])
                                      + (" …" if len(found) > 5 else "") + " olarak bulundu.")
                return (dim, o, v)
        label = {"author": "yazar", "publisher": "yayınevi", "subbrand": "alt marka"}[dim]
        raise ContractError(f"«{value}» adını taşıyan {label} CRM'deki aktif kitap kartlarında bulunamadı; adı kontrol edip yeniden sorun.",
                            code="NEEDS_CLARIFICATION")

    def apply_crm_book_scope(self, rows, scope_books, scope, plan, sold):
        """Satış satırlarını CRM kümesine indirger; kırılım değerlerine açar; CRM sayısı varken satışsız kitabı 0 ile korur."""
        from . import crm_book_scope
        sold.update(k for k in (crm_book_scope.key(r.get("book_code")) for r in rows) if k in scope_books)
        kept = [r for r in rows if crm_book_scope.key(r.get("book_code")) in scope_books]
        attributes = scope["attributes"]
        if attributes and "crm_attribute" in plan.dimensions:
            spread = []
            for r in kept:
                values = sorted(scope_books[crm_book_scope.key(r.get("book_code"))]["attributes"], key=str)
                spread.extend({**r, **dict(zip(attributes, value))} for value in values)
            if any(len(b["attributes"]) > 1 for b in scope_books.values()):
                note = ("Bazı kitaplar CRM'de birden çok değere bağlı; bu kitapların satışı her değerde ayrı sayıldı, "
                        "değerlerin toplamı genel toplam değildir.")
                if note not in self.notes:
                    self.notes.append(note)
            kept = spread
        if scope["values"]:
            present = {crm_book_scope.key(r.get("book_code")) for r in kept}
            for k, book in scope_books.items():
                if k not in present:
                    kept.append({"book_code": book["code"], "book_name": book["name"], **{m: Decimal(0) for m in plan.metrics}})
        return kept

    def report_result(self, result):
        if isinstance(result, list):
            return result
        self.output_fields = result.get("output_fields", [])
        self.numeric_fields = set(result.get("numeric_fields", []))
        self.notes.extend(result.get("notes", []))
        self.gaps.extend(result.get("gaps", []))
        self.return_invoice_counts.extend(result.get("return_invoice_counts", []))
        if self.gaps:
            self.coverage_complete = False
        return result["records"]

    @staticmethod
    def returns_probe(plan):
        """Invoice counts exclude returns (user decision 2026-10-01). The same run also
        counts return invoices for the identical period, filters and sale kind, so the
        answer can say how many were left out. One total, not per breakdown row."""
        counted = set(plan.metrics) | ({plan.comparison.metric} if plan.comparison else set())
        if "invoice_count" not in counted or counted & {"return_invoice_count", "invoice_count_with_returns"}:
            return None
        return replace(plan, metrics=("return_invoice_count",), dimensions=(), derived=(), having=(),
                       comparison=None, analytics=(), limit=None, order_by=None)

    @staticmethod
    def matches(value, op, wanted):
        from .language import fold
        a, b = fold(str(value or "")), fold(wanted)
        return a == b if op == "eq" else b in a

    def aggregate_families(self, plan, start, end, firm, period, enrichment):
        families = {}
        for metric in plan.metrics:
            families.setdefault(METRICS[metric].family, []).append(metric)
        if len(families) == 1:
            return self.aggregate(plan, next(iter(families)), start, end, firm, period, enrichment)
        if not set(families) <= {"sales", "invoice", "collection"}:
            raise ContractError("Bu kaynak aileleri aynı kayıt düzeyinde birleştirilemiyor.")
        dims = set(plan.dimensions) | {d for d, _, _ in plan.filters}
        if enrichment or dims - {"customer", "channel", "day", "month", "year"}:
            raise ContractError("Fatura ve tahsilat tutarı kitap satırlarına dağıtılamaz; ortak müşteri veya dönem kırılımı gerekir.")
        joined = {}
        keys = None
        for family, metrics in families.items():
            partial = replace(plan, metrics=tuple(metrics))
            rows = self.aggregate(partial, family, start, end, firm, period, False)
            for row in rows:
                row_keys = tuple(k for k in row if k not in metrics)
                if keys is None:
                    keys = row_keys
                if row_keys != keys:
                    raise ContractError("Hesap ailelerinin ortak kırılım kolonları uyuşmuyor.", code="SOURCE_CONTRACT_VIOLATION")
                key = tuple(row[k] for k in keys)
                target = joined.setdefault(key, {**{k:row[k] for k in keys}, **{m:Decimal(0) for m in plan.metrics}})
                for metric in metrics:
                    target[metric] += number(row[metric])
        self.notes.append("Satış satırı, fatura başlığı ve ödeme hareketleri ayrı hesaplandı; ortak kırılımda birleştirildi. Dönemde hareketi olmayan ölçü 0 gösterilir.")
        return list(joined.values())

    def cancelled_coded_note(self, plan):
        """Kodlu fatura süzgeci (e-belge durumu, belge türü, senaryo, cari işareti) iptal edilmemiş faturaları sayar.
        Reddedilen e-fatura çoğu zaman iptal edilir (2026: 2 ret, ikisi iptal); aynı dönem ve süzgeçle iptal edilmiş
        satış faturası sayısı not olarak söylenir ki «0» sessiz bir kapsam kararı olmasın."""
        from .logo_codes import CODED
        coded = [(d, op, v) for d, op, v in plan.filters if d in CODED and CODED[d].level in ("invoice", "client")]
        if not coded:
            return
        total = 0
        coverage = list(self.source_periods)    # aynı dönemler cevabın kapsamında zaten yazılı
        for start, end in plan.periods:
            for a, b, firm, period in self.partitions(date.fromisoformat(start), date.fromisoformat(end)):
                header, client = f"LG_{firm}_{period}_INVOICE", f"LG_{firm}_CLCARD"
                needed = {header: ["LOGICALREF", "DATE_", "CANCELLED", "TRCODE", "CLIENTREF"]}
                for d, _, _ in coded:
                    t = client if CODED[d].level == "client" else header
                    needed.setdefault(t, ["LOGICALREF"]).append(CODED[d].column)
                self.verify_schema(needed, "logo")
                where = ["f.CANCELLED=1", f"f.DATE_>='{a}'", f"f.DATE_<'{b}'", "f.TRCODE IN " + codes_sql(SALES_INVOICE_CODES)]
                where += [CODED[d].predicate("c" if CODED[d].level == "client" else "f", op, v) for d, op, v in coded]
                rows = self.read(f"SELECT COUNT_BIG(*) AS [n] FROM dbo.[{header}] f LEFT JOIN dbo.[{client}] c ON c.LOGICALREF=f.CLIENTREF"
                                 " WHERE " + " AND ".join(where))
                total += sum(int(number(r.get("n"))) for r in rows)
        self.source_periods = coverage
        if total:
            self.notes.append(f"Aynı dönem ve koşullarda {total:,} satış faturası iptal edilmiş; iptal edilen faturalar hesaba girmez.".replace(",", "."))

    def price_difference_note(self, plan):
        """Müşteriye ayrı faturayla verilen iskonto fiyat farkı (hizmet kartı 611…): muhasebede satış indirimi, kitap
        satırına bağlı değil. Satış tutarı bunu içermez; aynı dönem ve müşteri/kanal süzgeciyle tutarı nota yazılır
        (karar 2026-10-01). İade faturasında indirim (+), satış faturasında geri alım (−)."""
        total = Decimal(0)
        coverage = list(self.source_periods)    # aynı dönemler cevabın kapsamında zaten yazılı
        for start, end in plan.periods:
            for a, b, firm, period in self.partitions(date.fromisoformat(start), date.fromisoformat(end)):
                line, header = f"LG_{firm}_{period}_STLINE", f"LG_{firm}_{period}_INVOICE"
                srv, client = f"LG_{firm}_SRVCARD", f"LG_{firm}_CLCARD"
                self.verify_schema({line: ["LINETYPE", "INVOICEREF", "STOCKREF", "CLIENTREF", "VATMATRAH", "TRCODE", "CANCELLED"],
                                    header: ["LOGICALREF", "DATE_", "CANCELLED"], srv: ["LOGICALREF", "CODE"],
                                    client: ["LOGICALREF", "CODE", "DEFINITION_", "SPECODE2"]}, "logo")
                conditions = ["f.CANCELLED=0", "h.CANCELLED=0", "f.LINETYPE=4", "f.INVOICEREF<>0", "f.TRCODE IN (2,3,7,8,9)",
                              f"h.DATE_>='{a}'", f"h.DATE_<'{b}'", "s.CODE LIKE '611%'"]
                if plan.sale_kind != "all":
                    conditions.append("f.TRCODE IN " + ("(8,3)" if plan.sale_kind == "wholesale" else "(7,2)"))
                for dim, op, value in plan.filters:
                    if dim not in ("customer", "channel"):
                        continue
                    conditions.append(self.name_predicate(dim, op, value, firm, "c"))
                rows = self.read("SELECT ISNULL(SUM(CASE WHEN f.TRCODE IN (2,3) THEN f.VATMATRAH ELSE -f.VATMATRAH END),0) AS [discount]"
                                 f" FROM dbo.[{line}] f JOIN dbo.[{header}] h ON h.LOGICALREF=f.INVOICEREF"
                                 f" JOIN dbo.[{srv}] s ON s.LOGICALREF=f.STOCKREF LEFT JOIN dbo.[{client}] c ON c.LOGICALREF=f.CLIENTREF"
                                 " WHERE " + " AND ".join(conditions))
                total += sum((number(r.get("discount")) for r in rows), Decimal(0))
        self.source_periods = coverage
        if abs(total) >= 1:
            amount = f"{total:,.2f}".replace(",", "~").replace(".", ",").replace("~", ".")
            where = "kitap satırına bağlı olmadığı için kitap kırılımına dağıtılamaz" if ("book" in plan.dimensions or any(d == "book" for d, _, _ in plan.filters)) else "müşteri bazında ayrı faturayla kesilir"
            self.notes.append(f"Bu dönemde ayrı faturayla verilen iskonto fiyat farkı {amount} TL (muhasebede satış indirimi) bu satış "
                              f"tutarına dahil değildir; {where}. Muhasebe net satışı bu farkları içerir.")

    #: Ad süzgecinin ana kaydı: kırılım → (tablo soneki, kolonlar, ekranda ad).
    NAME_MASTERS = {"book": ("ITEMS", ("CODE", "NAME"), "kitap"), "customer": ("CLCARD", ("CODE", "DEFINITION_"), "müşteri"),
                    "channel": ("CLCARD", ("SPECODE2",), "satış kanalı")}

    def name_predicate(self, dim, op, value, firm, alias):
        """Ad süzgecini ana kayıtta çözer: soruda geçtiği gibi bulunmazsa eki atılmış kökü dener; hiçbiri yoksa «0» değil
        «bulunamadı» der. Latin1_General_CI_AI: Logo kodları Türkçe harfsiz yazılı (E-TICARET, KITAPCI, YURTDISI); Türkçe
        karşılaştırmada «i» ile «I» ayrı harftir ve «e-ticaret» hiçbir kartı bulmaz (2026-10-05 ölçüldü: 0 / 21.402)."""
        key = (dim, op, value, firm, alias)
        cache = self.__dict__.setdefault("_name_cache", {})
        if key in cache:
            return cache[key]
        table, cols, label = self.NAME_MASTERS[dim]

        def pred(a, o, v):
            if o == "contains":
                esc = v.replace("~", "~~").replace("%", "~%").replace("_", "~_").replace("[", "~[")
                return "(" + " OR ".join(f"{a}.{c} COLLATE Latin1_General_CI_AI LIKE {literal('%' + esc + '%')} ESCAPE '~'" for c in cols) + ")"
            return "(" + " OR ".join(f"{a}.{c} COLLATE Latin1_General_CI_AI={literal(v)}" for c in cols) + ")"

        tries = [(op, value)] + ([("contains", value)] if op == "eq" else []) + [("contains", stem) for stem in name_stems(value)]
        for o, v in tries:
            rows = self.read(f"SELECT COUNT_BIG(*) AS n FROM dbo.[LG_{firm}_{table}] m WHERE " + pred("m", o, v))
            n = int(number(rows[0].get("n"))) if rows else 0
            if n:
                if (o, v) != (op, value):
                    self.notes.append(f"«{value}» {label} kayıtlarında «{v}» içeren ad olarak arandı ({n} kayıt).")
                cache[key] = pred(alias, o, v)
                return cache[key]
        if dim == "channel":
            # Kanal ve müşteri aynı cari kartta: «kitapyurduna» bir müşteridir, kanal değil. Kanal adında yoksa müşteri
            # adında aranır; bulunursa müşteri süzgeci olarak uygulanır ve söylenir.
            try:
                found = self.name_predicate("customer", op, value, firm, alias)
            except ContractError:
                pass
            else:
                self.notes.append(f"«{value}» bir satış kanalı adı değil; müşteri kartı adı olarak bulundu ve müşteri süzgeci uygulandı.")
                cache[key] = found
                return found
        raise ContractError(f"«{value}» adını taşıyan {label} kaydı bulunamadı; adı kontrol edip yeniden sorun.", code="NEEDS_CLARIFICATION")

    def field_predicate(self, field, op, value, family, firm, period):
        """Kart kolonu süzgeci (il, temsilci, ödeme planı…): değer kartta bulunmazsa «0» değil «bulunamadı». Türkçe ek
        kökleri de denenir («Ankara'daki» → «Ankara»). Kodlu alanda değer koda çevrilir."""
        alias = field.alias(family)
        if field.kind == "coded":
            return field.predicate(alias, op, value)
        key = ("field", field.id, op, value, firm, period)
        cache = self.__dict__.setdefault("_name_cache", {})
        if key in cache:
            return cache[key]
        table = field.physical(firm, period)
        tries = [(op, value)] + ([("contains", value)] if op == "eq" else []) + [("contains", stem) for stem in name_stems(value)]
        for o, v in tries:
            rows = self.read(f"SELECT COUNT_BIG(*) AS n FROM dbo.[{table}] m WHERE " + field.predicate("m", o, v))
            n = int(number(rows[0].get("n"))) if rows else 0
            if n:
                if (o, v) != (op, value):
                    self.notes.append(f"«{value}» {field.label} alanında «{v}» içeren değer olarak arandı.")
                cache[key] = field.predicate(alias, o, v)
                return cache[key]
        raise ContractError(f"«{value}» değeri {field.label} alanında bulunamadı; yazımı kontrol edip yeniden sorun.", code="NEEDS_CLARIFICATION")

    def aggregate_ledger(self, plan, start, end, firm, period):
        """Muhasebe net satışı: fiş satırında 600–602 ve 610–612 alacak − borç. Kapanış ve yansıtma hesabı içeren fişler
        M45 gelir tablosuyla aynı kuralla dışarıda (finance_sources); dönem fiş satırı tarihi."""
        from semantic_bridge.finance_sources import close_accounts, yansitma_accounts
        line, fiche, acc = f"LG_{firm}_{period}_EMFLINE", f"LG_{firm}_{period}_EMFICHE", f"LG_{firm}_EMUHACC"
        types = self.verify_schema({line: ["ACCFICHEREF", "ACCOUNTREF", "DEBIT", "CREDIT", "DATE_", "CANCELLED"],
                                    fiche: ["LOGICALREF", "CANCELLED"], acc: ["LOGICALREF", "CODE"]}, "logo")
        for col in ("DEBIT", "CREDIT"):
            if types[line.lower(), col.lower()] not in {"decimal", "numeric", "float", "real", "money", "smallmoney"}:
                raise ContractError("Muhasebe tutar alanının veri türü sözleşmeyle uyuşmuyor.")
        labels = {d: e for d, e in {"day": "CONVERT(varchar(10),f.DATE_,23)", "month": "CONVERT(varchar(7),f.DATE_,23)",
                                    "year": "YEAR(f.DATE_)"}.items() if d in plan.dimensions}
        excluded = close_accounts()[:-1] + "," + yansitma_accounts()[1:]
        select = [f"{e} AS [{d}]" for d, e in labels.items()]
        select.append("ISNULL(SUM(f.CREDIT-f.DEBIT),0) AS [accounting_net_sales]")
        sql = ("SELECT " + ", ".join(select) + f" FROM dbo.[{line}] f JOIN dbo.[{fiche}] h ON h.LOGICALREF=f.ACCFICHEREF"
               f" JOIN dbo.[{acc}] a ON a.LOGICALREF=f.ACCOUNTREF"
               f" WHERE f.CANCELLED=0 AND h.CANCELLED=0 AND f.DATE_>='{start}' AND f.DATE_<'{end}'"
               " AND LEFT(a.CODE,3) IN ('600','601','602','610','611','612')"
               f" AND NOT EXISTS (SELECT 1 FROM dbo.[{line}] k JOIN dbo.[{acc}] ka ON ka.LOGICALREF=k.ACCOUNTREF"
               f" WHERE k.ACCFICHEREF=f.ACCFICHEREF AND k.CANCELLED=0 AND LEFT(ka.CODE,3) IN {excluded})")
        if labels:
            sql += " GROUP BY " + ", ".join(labels.values())
        return self.read(sql)

    def aggregate(self, plan, family, start, end, firm, period, enrichment):
        if family == "ledger":
            return self.aggregate_ledger(plan, start, end, firm, period)
        suffix = {"sales": "STLINE", "invoice": "INVOICE", "collection": "CLFLINE"}[family]
        table = f"LG_{firm}_{period}_{suffix}"
        item_table, client_table = f"LG_{firm}_ITEMS", f"LG_{firm}_CLCARD"
        dims = set(plan.dimensions) | {d for d, _, _ in plan.filters}
        book = "book" in dims or enrichment
        from .logo_codes import CODED, columns as coded_columns, sql_alias as coded_alias
        coded = [d for d in CODED if d in dims]
        from . import logo_fields
        fields = [logo_fields.FIELDS[d] for d in sorted(dims) if d in logo_fields.FIELDS]
        for f in fields:
            f.alias(family)                               # okunamayan düzeyde açık hata
        client = (bool(dims & {"channel", "customer"}) or family == "collection" or any(CODED[d].level == "client" for d in coded)
                  or any(f.level == "client" for f in fields))
        items = book or any(f.level == "item" for f in fields)
        needed = {table: ["CANCELLED", "DATE_", "TRCODE"]}
        needed[table] += {"sales": ["LINETYPE", "INVOICEREF", "STOCKREF", "CLIENTREF", "VATMATRAH", "AMOUNT"],
                          "invoice": ["LOGICALREF", "NETTOTAL", "CLIENTREF"],
                          "collection": ["CLIENTREF", "AMOUNT", "SIGN"]}[family]
        quantities = set(plan.metrics) & {"sold_quantity", "net_quantity"}
        if quantities:
            needed[table] += ["UINFO1", "UINFO2"]
        # A sales line belongs to the period of its invoice (user decision 2026-10-01).
        header_table = f"LG_{firm}_{period}_INVOICE"
        if family == "sales":
            needed[header_table] = ["LOGICALREF", "DATE_", "CANCELLED"]
        date_col = "h.DATE_" if family == "sales" else "f.DATE_"
        if items:
            needed[item_table] = ["LOGICALREF", "CODE", "NAME"]
        if client:
            needed[client_table] = ["LOGICALREF", "CODE", "DEFINITION_", "SPECODE2"]
        for d in coded:
            coded_alias(d, family)                        # okunamayan düzeyde açık hata
            t, col = coded_columns(d, family, firm, period)
            needed.setdefault(t, []).append(col)
        for t, cols in logo_fields.schema_needs(fields, family, firm, period).items():
            needed.setdefault(t, []).extend(cols)
        types = self.verify_schema(needed, "logo")
        measures = {"sales": ["AMOUNT", "VATMATRAH"], "invoice": ["NETTOTAL"], "collection": ["AMOUNT"]}[family]
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
        for d in coded:
            if d in plan.dimensions:
                labels[d] = CODED[d].expression(coded_alias(d, family))
        for f in fields:
            if f.id in plan.dimensions:
                labels[f.id] = f.expression(f.alias(family))
        for d, expression in {"day": f"CONVERT(varchar(10),{date_col},23)", "month": f"CONVERT(varchar(7),{date_col},23)", "year": f"YEAR({date_col})"}.items():
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
        if family == "sales":
            sql += f" JOIN dbo.[{header_table}] h ON h.LOGICALREF=f.INVOICEREF"
        if items:
            sql += f" LEFT JOIN dbo.[{item_table}] i ON i.LOGICALREF=f.STOCKREF"
        if client:
            sql += f" LEFT JOIN dbo.[{client_table}] c ON c.LOGICALREF=f.CLIENTREF"
        sql += "".join(logo_fields.joins(fields, family, firm, period))
        conditions = ["f.CANCELLED=0", f"{date_col}>='{start}'", f"{date_col}<'{end}'"]
        if family == "sales":
            conditions.append("h.CANCELLED=0")
        if family in ("sales", "invoice"):
            transaction_codes = codes_sql(set().union(*(TRANSACTION_CODES[m] for m in plan.metrics)))
            if family == "sales":
                conditions += ["f.LINETYPE=0", "f.INVOICEREF<>0"]
            conditions.append("f.TRCODE IN " + transaction_codes)
        else:
            conditions += ["f.SIGN=1", "f.TRCODE IN (1,20,61,62,70)", "c.CODE LIKE '120%'"]
        if plan.sale_kind != "all":
            # Retail returns are 2, wholesale returns 3; do not silently discard returns from
            # net metrics or return counts. Service sales 9 are neither retail nor wholesale.
            conditions.append("f.TRCODE IN " + ("(8,3)" if plan.sale_kind == "wholesale" else "(7,2)"))
        for dim, op, value in plan.filters:
            if dim in ("author", "publisher", "subbrand"):
                continue
            if dim in CODED:
                conditions.append(CODED[dim].predicate(coded_alias(dim, family), op, value))
                continue
            if dim in logo_fields.FIELDS:
                conditions.append(self.field_predicate(logo_fields.FIELDS[dim], op, value, family, firm, period))
                continue
            conditions.append(self.name_predicate(dim, op, value, firm, "i" if dim == "book" else "c"))
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
