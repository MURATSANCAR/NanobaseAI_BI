"""Closed CRM read plans, independent of the retired semantic catalog.

Field meanings and the publisher relationship were checked against published
Dynamics metadata on 2026-09-30. This is current active-card reporting, not a
historical reconstruction of record state or a royalty-owner relationship.
"""
from datetime import datetime
import re
from uuid import UUID

from .contracts import ContractError


FIELDS = {
    "book_id": ("book", "r.new_kitapId", "id", "Kitap kayıt kimliği"),
    "book_code": ("book", "r.new_stokkodu", "text", "Stok kodu"),
    "book_name": ("book", "r.new_name", "text", "Kitabın ekran adı"),
    "author": ("book", "r.new_yazartext", "text", "Yazar künye metni; kişi/telif sahibi kimliği değildir"),
    "isbn": ("book", "r.new_isbn13", "text", "Güncel ISBN / ISSN; eski ISBN veya e-kitap ISBN değildir"),
    "publisher_id": ("book", "m.new_markaId", "id", "Aktif yayıncı kayıt kimliği"),
    "publisher": ("book", "m.new_name", "text", "Aktif yayıncı adı"),
    "person_id": ("author", "r.ContactId", "id", "Aktif yazar kişi kimliği"),
    "person_name": ("author", "r.FullName", "text", "Aktif yazar kişinin tam adı"),
    "customer_id": ("customer", "r.AccountId", "id", "Aktif müşteri kayıt kimliği"),
    "customer_name": ("customer", "r.Name", "text", "Aktif müşteri adı"),
    "created_at": ("all", "r.CreatedOn", "datetime", "Kayıt oluşturma zamanı; yayın/ilk satış tarihi değildir, kaynak UTC"),
    "updated_at": ("all", "r.ModifiedOn", "datetime", "Kayıt değiştirme zamanı; iş olayının tarihi değildir, kaynak UTC"),
}
TABLES = {"book": "new_kitapBase", "author": "ContactBase", "customer": "AccountBase"}
CRM_CAPABILITIES = {
    "entities": {"book": "Aktif kitap kartları", "author": "Aktif Contact yazar kişiler (new_yazarmi=1)",
                 "customer": "Aktif müşteri durumundaki Account kayıtları"},
    "fields": {k: {"entity": v[0], "type": v[2], "meaning": v[3]} for k, v in FIELDS.items()},
    "modes": {"list": "fields kolonlarını listele", "count": "group_by kırılımında record_count; kırılım boşsa tek sayı. fields boş olmalıdır; group_by zaten sonuç kolonlarını içerir",
              "quality": "fields içindeki metin alanları için NULL/boş sayıları: missing_<field>, ayrıca record_count"},
    "rules": ["Yalnız mevcut aktif kayıtlar; tarihsel aktiflik, silinmiş/pasif kayıt, satış, randevu veya sözleşme kapsamı yok.",
              "Yazar künye metni ile Contact kişiler arasında bağlantı yok; kitabın kişi kimliği veya telif ilişkisi uydurulmaz.",
              "Yayınevi kırılımı publisher_id ve publisher birlikte kullanır; aynı adlı farklı yayıncılar birleşmez.",
              "Mükerrer stok kodu: count, group_by=[book_code], having_min_count=2; boş kod istenmiyorsa present süzgeci.",
              "quality yalnız eksik/boş alan sayar; ISBN doğruluğunu, kayıt tutarlılığını veya yazar eşleşmesini doğrulamaz.",
              "filters mantıksal AND; OR, tarihsel anlık görüntü, dönem kıyası, satışsız kitap desteklenmez.",
              "created_at/updated_at değerleri UTC; tarihler yalnız açık kayıt oluşturma/değiştirme anlamında kullanılır.",
              "limit yalnız kullanıcı açıkça ilk/en çok/en az N isterse; listeye keyfi sınır koyma."],
}


def _object(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


CRM_PLAN_SCHEMA = _object({
    "kind": {"type": "string", "enum": ["crm"]},
    "entity": {"type": "string", "enum": list(TABLES)},
    "mode": {"type": "string", "enum": ["list", "count", "quality"]},
    "fields": {"type": "array", "items": {"type": "string", "enum": list(FIELDS)}},
    "group_by": {"type": "array", "items": {"type": "string", "enum": list(FIELDS)}},
    "filters": {"type": "array", "items": _object({
        "field": {"type": "string", "enum": list(FIELDS)},
        "op": {"type": "string", "enum": ["eq", "contains", "missing", "present", "gte", "lt"]},
        "value": {"type": "string"},
    })},
    "having_min_count": {"anyOf": [{"type": "null"}, {"type": "integer", "minimum": 1}]},
    "order_by": {"anyOf": [{"type": "null"}, {"type": "string", "enum": list(FIELDS) + ["record_count"] + ["missing_" + f for f in FIELDS]}]},
    "descending": {"type": "boolean"},
    "limit": {"anyOf": [{"type": "null"}, {"type": "integer", "minimum": 1, "maximum": 1000}]},
})


def validate_crm_plan(raw):
    if not isinstance(raw, dict) or set(raw) != set(CRM_PLAN_SCHEMA["properties"]):
        raise ContractError("CRM planının alanları sözleşmeyle uyuşmuyor.")
    p = dict(raw)
    if p["kind"] != "crm" or p["entity"] not in TABLES or p["mode"] not in ("list", "count", "quality"):
        raise ContractError("CRM varlığı veya işlem türü tanımlı değil.")
    for slot in ("fields", "group_by"):
        names = p[slot]
        if not isinstance(names, list) or any(not isinstance(f, str) for f in names) or len(names) != len(set(names)):
            raise ContractError("CRM kolon listesi geçersiz.")
        if any(f not in FIELDS or FIELDS[f][0] not in (p["entity"], "all") for f in names):
            raise ContractError("İstenen CRM alanı bu varlıkta tanımlı değil.")
    if p["mode"] == "list" and (not p["fields"] or p["group_by"]):
        raise ContractError("CRM liste planında kolonlar gerekli; gruplama kullanılamaz.")
    if p["mode"] == "count" and p["fields"]:
        # A grouping column is already projected by the count plan. Accept its
        # redundant listing without changing either grain or output columns;
        # never drop an additional requested field that is not grouped.
        if not set(p["fields"]).issubset(p["group_by"]):
            raise ContractError("CRM sayımında liste kolonları yerine kırılım kullanılmalıdır.")
        p["fields"] = []
    if p["mode"] == "quality" and (not p["fields"] or any(FIELDS[f][2] != "text" for f in p["fields"])):
        raise ContractError("Eksik alan sayımı yalnız açıkça seçilen metin alanları için tanımlıdır.")
    if "publisher" in p["group_by"] and "publisher_id" not in p["group_by"]:
        raise ContractError("Aynı adlı yayıncılar karışmamalı; yayıncı kimliği kırılıma eklenmelidir.")
    minimum = p["having_min_count"]
    if minimum is not None and (type(minimum) is not int or minimum < 1 or p["mode"] != "count" or not p["group_by"]):
        raise ContractError("Kayıt sayısı alt sınırı yalnız kırılımlı sayımda kullanılabilir.")
    if not isinstance(p["filters"], list) or len(p["filters"]) > 30:
        raise ContractError("CRM süzgeç listesi geçersiz.")
    for f in p["filters"]:
        if not isinstance(f, dict) or set(f) != {"field", "op", "value"}:
            raise ContractError("CRM süzgeç biçimi geçersiz.")
        field, op, value = f["field"], f["op"], f["value"]
        if not isinstance(field, str) or field not in FIELDS or FIELDS[field][0] not in (p["entity"], "all"):
            raise ContractError("CRM süzgeç alanı varlıkta tanımlı değil.")
        if op not in ("eq", "contains", "missing", "present", "gte", "lt") or not isinstance(value, str) or len(value) > 200:
            raise ContractError("CRM süzgeç değeri/işlemi geçersiz.")
        kind = FIELDS[field][2]
        if op in ("missing", "present"):
            if value:
                raise ContractError("Boş/dolu alan süzgeci ayrıca bir değer içeremez.")
        elif not value.strip():
            raise ContractError("CRM süzgeci için boş olmayan değer gerekli.")
        elif kind == "datetime":
            if op not in ("eq", "gte", "lt") or not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2})?", value):
                raise ContractError("CRM kayıt zamanı süzgeci ISO UTC tarih gerektirir.")
            try:
                datetime.fromisoformat(value)
            except ValueError as exc:
                raise ContractError("CRM kayıt zamanı geçersiz.") from exc
        elif kind == "id":
            if op != "eq":
                raise ContractError("CRM kayıt kimliğinde yalnız eşitlik kullanılabilir.")
            try:
                UUID(value)
            except ValueError as exc:
                raise ContractError("CRM kayıt kimliği UUID olmalıdır.") from exc
        elif op not in ("eq", "contains"):
            raise ContractError("Metin alanında sayısal/tarihsel karşılaştırma tanımlı değil.")
    columns = output_columns(p)
    if p["order_by"] is not None and p["order_by"] not in columns:
        raise ContractError("CRM sıralaması sonuç kolonlarından biri olmalı.")
    if type(p["descending"]) is not bool:
        raise ContractError("CRM sıralama yönü geçersiz.")
    if p["limit"] is not None and (type(p["limit"]) is not int or not 1 <= p["limit"] <= 1000):
        raise ContractError("CRM liste sınırı geçersiz.")
    return p


def output_columns(plan):
    if plan["mode"] == "list":
        return list(plan["fields"])
    return list(plan["group_by"]) + ["record_count"] + (["missing_" + f for f in plan["fields"]] if plan["mode"] == "quality" else [])


def execute_crm_plan(executor, raw):
    from .executor import CRM, literal
    p = validate_crm_plan(raw)
    executor.output_fields = output_columns(p)
    executor.numeric_fields = {f for f in executor.output_fields if f == "record_count" or f.startswith("missing_")}
    used = set(p["fields"] + p["group_by"] + [f["field"] for f in p["filters"]])
    table = TABLES[p["entity"]]
    needed = {table: ["statecode", "statuscode"]}
    for field in used:
        expression = FIELDS[field][1]
        target = "new_markaBase" if expression.startswith("m.") else table
        needed.setdefault(target, []).append(expression.split(".")[1])
    publisher = bool(used & {"publisher", "publisher_id"})
    if p["entity"] == "author":
        needed[table].append("new_yazarmi")
    if publisher:
        needed[table].append("new_yayineviid")
        needed["new_markaBase"] = list(set(needed.get("new_markaBase", []) + ["new_markaId", "statecode", "statuscode"]))
    executor.verify_schema(needed, "crm")
    base = f" FROM {CRM}.[{table}] r"
    if publisher:
        active = executor.crm_status("new_markaBase", "m")
        duplicates = executor.read(f"SELECT TOP (1) m.new_markaId FROM {CRM}.new_markaBase m WHERE {active} GROUP BY m.new_markaId HAVING COUNT_BIG(*)>1", source="crm")
        if duplicates:
            raise ContractError("Aktif yayıncı anahtarı tekil değil; kitap sayısını çoğaltacak birleştirme engellendi.", code="SOURCE_CONTRACT_VIOLATION")
        base += f" LEFT JOIN {CRM}.new_markaBase m ON m.new_markaId=r.new_yayineviid AND {active}"
    conditions = [executor.crm_status(table, "r")]
    if p["entity"] == "author":
        conditions.append("r.new_yazarmi=1")
    def expression(field):
        raw_expr = FIELDS[field][1]
        return f"NULLIF(LTRIM(RTRIM({raw_expr})),N'')" if FIELDS[field][2] == "text" else raw_expr
    for f in p["filters"]:
        expr, op, val = expression(f["field"]), f["op"], f["value"]
        if op in ("missing", "present"):
            conditions.append(expr + (" IS NULL" if op == "missing" else " IS NOT NULL"))
        elif op == "contains":
            escaped = val.replace("~", "~~").replace("%", "~%").replace("_", "~_").replace("[", "~[")
            conditions.append(f"{expr} LIKE {literal('%' + escaped + '%')} ESCAPE '~'")
        else:
            conditions.append(expr + {"eq": "=", "gte": ">=", "lt": "<"}[op] + literal(val))
    base += " WHERE " + " AND ".join(conditions)
    dims = p["fields"] if p["mode"] == "list" else p["group_by"]
    select = [f"{expression(f)} AS [{f}]" for f in dims]
    if p["mode"] != "list":
        select.append("COUNT_BIG(*) AS [record_count]")
    if p["mode"] == "quality":
        select += [f"COALESCE(SUM(CAST(CASE WHEN {expression(f)} IS NULL THEN 1 ELSE 0 END AS bigint)),0) AS [missing_{f}]" for f in p["fields"]]
    if p["mode"] != "list" and dims:
        base += " GROUP BY " + ",".join(expression(f) for f in dims)
    if p["having_min_count"] is not None:
        base += f" HAVING COUNT_BIG(*)>={p['having_min_count']}"
    # Stable tie ordering makes an explicit TOP request reproducible.
    order = p["order_by"] or output_columns(p)[0]
    sort = [f"[{order}] " + ("DESC" if p["descending"] else "ASC")]
    sort += [f"[{f}] ASC" for f in output_columns(p) if f != order]
    top = f"TOP ({p['limit']}) " if p["limit"] is not None else ""
    sql = "SELECT " + top + ",".join(select) + base + " ORDER BY " + ",".join(sort)
    executor.notes.append("CRM sonucu güncel aktif kayıtları kapsar; kitap yazar alanı kişi kimliği değil künye metnidir.")
    if publisher:
        executor.notes.append("Pasif veya bulunamayan yayıncılar boş gösterilir; aktif kitap kayıtları korunur.")
    rows = executor.read(sql, source="crm")
    return [{k: (str(v) if isinstance(v, UUID) else v.isoformat() if isinstance(v, datetime) else v)
             for k, v in row.items()} for row in rows]
