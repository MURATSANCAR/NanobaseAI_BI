"""SELECT-only compiler for the validated, metadata-bound CRM relational AST."""
from datetime import date, datetime
from decimal import Decimal
import re
from uuid import UUID

from .contracts import ContractError
from .relational_contracts import ENTITY_REGISTRY, RELATION_REGISTRY
from .relational_plan import alias_entities, validate_relational_query

MAX_RESULT_ROWS = 50000

def _identifier(value):
    if not isinstance(value,str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*",value):
        raise ContractError("Kaynak tanımındaki SQL kimliği güvenli değil.",code="SOURCE_CONTRACT_VIOLATION")
    return "["+value+"]"

def _table(entity):
    if entity.get("schema","dbo")!="dbo":
        raise ContractError("CRM şema kapsamı doğrulanmamış.",code="SOURCE_CONTRACT_VIOLATION")
    return "[Timas_MSCRM].[dbo]."+_identifier(entity["table"])

def _column(ref,aliases):
    field=ENTITY_REGISTRY[aliases[ref["alias"]]]["fields"][ref["field"]]
    return _identifier(ref["alias"])+"."+_identifier(field["column"])

def _active(entity,alias):
    # Only the source registry owns this template; no model text enters it.
    return entity["active_predicate"].format(alias=_identifier(alias))

def _text(value):
    return "N'"+value.replace("'","''")+"'"

def _literal(value):
    if value["type"]=="number": return value["value"]
    if value["type"]=="bool": return "1" if value["value"]=="true" else "0"
    if value["type"]=="date":
        # Validation normalized offsets to UTC; CRM physical datetime has no offset.
        stamp=datetime.fromisoformat(value["value"]).replace(tzinfo=None)
        return "CONVERT(datetime2,"+_text(stamp.isoformat(timespec="microseconds"))+",126)"
    if value["type"]=="identity": return "CONVERT(uniqueidentifier,"+_text(value["value"])+")"
    return _text(value["value"])

def compile_relational_query(plan, active=None):
    """Caller passes validate_relational_query output. No user SQL fragments accepted.
    active(entity, alias) adds the runtime passive-record rule to each registry predicate."""
    active=active or _active
    plan=validate_relational_query(plan,"",date.today())
    aliases=alias_entities(plan);root=ENTITY_REGISTRY[plan["root"]]
    root_pk=_column({"alias":"root","field":root["primary_key"]},aliases)
    select=[];numeric=[];types={}
    for item in plan["select"]:
        op=item["op"]
        value=_column(item["field"],aliases) if item["field"] is not None else root_pk
        if op=="count_records": expression="COUNT_BIG(DISTINCT "+root_pk+")"
        elif op=="count_distinct": expression="COUNT_BIG(DISTINCT "+value+")"
        elif op=="sum": expression="SUM("+value+")"
        elif op=="normalized_text": expression="NULLIF(LTRIM(RTRIM("+value+")),N'')"
        elif op=="missing_flag":
            spec=ENTITY_REGISTRY[aliases[item["field"]["alias"]]]["fields"][item["field"]["field"]]
            condition=value+" IS NULL"
            if spec["type"]=="text": condition+=" OR LTRIM(RTRIM("+value+"))=N''"
            expression="CAST(CASE WHEN "+condition+" THEN 1 ELSE 0 END AS bit)"
        else: expression=value
        select.append(expression+" AS "+_identifier(item["id"]))
        fieldtype=ENTITY_REGISTRY[aliases[item["field"]["alias"]]]["fields"][item["field"]["field"]]["type"] if item["field"] else "number"
        types[item["id"]]="bool" if op=="missing_flag" else "number" if op in {"count_records","count_distinct","sum"} else fieldtype
        if types[item["id"]]=="number": numeric.append(item["id"])
    explicit=plan["limit"]
    top=explicit if explicit is not None else MAX_RESULT_ROWS+1
    sql="SELECT "+("DISTINCT " if plan["distinct"] else "")+"TOP ("+str(top)+") "+", ".join(select)+" FROM "+_table(root)+" AS [root]"
    for join in plan["joins"]:
        relation=RELATION_REGISTRY[join["relation"]];entity=ENTITY_REGISTRY[relation["right_entity"]]
        left=_column({"alias":join["left_alias"],"field":relation["left_field"]},aliases)
        right=_column({"alias":join["alias"],"field":relation["right_field"]},aliases)
        sql+=(" LEFT JOIN " if join["kind"]=="left" else " INNER JOIN ")+_table(entity)+" AS "+_identifier(join["alias"])
        sql+=" ON "+left+"="+right+" AND ("+active(entity,join["alias"])+")"
    predicates=["("+active(root,"root")+")"]
    for predicate in plan["filters"]:
        col=_column(predicate["field"],aliases);op=predicate["op"];values=predicate["values"]
        if op in {"is_missing","not_missing"}:
            spec=ENTITY_REGISTRY[aliases[predicate["field"]["alias"]]]["fields"][predicate["field"]["field"]]
            target="NULLIF(LTRIM(RTRIM("+col+")),N'')" if spec["type"]=="text" else col
            term=target+(" IS NULL" if op=="is_missing" else " IS NOT NULL")
        elif op in {"is_null","not_null"}: term=col+(" IS NULL" if op=="is_null" else " IS NOT NULL")
        elif op=="contains":
            pattern=values[0]["value"].replace("~","~~").replace("%","~%").replace("_","~_").replace("[","~[")
            term=col+" LIKE "+_text("%"+pattern+"%")+" ESCAPE N'~'"
        elif op=="in": term=col+" IN ("+",".join(_literal(v) for v in values)+")"
        elif op=="range": term=col+">="+_literal(values[0])+" AND "+col+"<"+_literal(values[1])
        else: term=col+("=" if op=="eq" else "<>")+_literal(values[0])
        predicates.append("("+term+")")
    sql+=" WHERE "+" AND ".join(predicates)
    if plan["group_by"]: sql+=" GROUP BY "+",".join(_column(r,aliases) for r in plan["group_by"])
    aggregate=any(item["op"] in {"count_records","count_distinct","sum"} for item in plan["select"])
    order=[_identifier(item["column"])+(" DESC" if item["descending"] else " ASC") for item in plan["order_by"]]
    ordered={item["column"] for item in plan["order_by"]}
    if aggregate:
        # Selected group fields are all present by validation; add them for stable ties.
        order.extend(_identifier(item["id"])+" ASC" for item in plan["select"] if item["op"]=="field" and item["id"] not in ordered)
    elif plan["distinct"]:
        order.extend(_identifier(item["id"])+" ASC" for item in plan["select"] if item["id"] not in ordered)
    else: order.append(root_pk+" ASC")
    if order: sql+=" ORDER BY "+",".join(order)
    return sql, list(types), numeric

def execute_relational_query(executor, plan):
    plan=validate_relational_query(plan,"",date.today())
    aliases=alias_entities(plan)
    entities={entity_id:ENTITY_REGISTRY[entity_id] for entity_id in aliases.values()}
    def active(entity,alias):
        # Registry template (reviewed definition) AND the shared passive-record rule, LEFT targets included.
        rule=executor.crm_active(entity["table"],_identifier(alias))
        return _active(entity,alias) if rule=="1=1" else "("+_active(entity,alias)+") AND ("+rule+")"
    required={}
    for entity in entities.values():
        columns={field["column"] for field in entity["fields"].values()}
        columns.update(re.findall(r"\]\.\[?([A-Za-z_][A-Za-z0-9_]*)",active(entity,"r")))
        required.setdefault(entity["table"],set()).update(columns)
    actual=executor.verify_schema(required,"crm")
    allowed={"text":{"varchar","nvarchar","char","nchar","text","ntext"},
             "number":{"int","bigint","smallint","tinyint","decimal","numeric","float","real","money","smallmoney"},
             "date":{"date","datetime","datetime2","smalldatetime","datetimeoffset"},
             "identity":{"uniqueidentifier"},"bool":{"bit"}}
    for entity in entities.values():
        for field in entity["fields"].values():
            physical=actual.get((entity["table"].lower(),field["column"].lower()))
            if physical not in allowed[field["type"]]:
                raise ContractError("CRM alan türü kayıtlı sözleşmeyle uyuşmuyor.",code="SOURCE_CONTRACT_VIOLATION")
        pk=_identifier(entity["fields"][entity["primary_key"]]["column"])
        check="SELECT TOP (1) r."+pk+" AS invalid_key FROM "+_table(entity)+" AS r WHERE ("+active(entity,"r")+")"
        check+=" GROUP BY r."+pk+" HAVING COUNT_BIG(*)>1 OR r."+pk+" IS NULL"
        if executor.read(check,source="crm"):
            raise ContractError("CRM anahtar tekilliği bozulmuş; çoğaltan ilişki yürütülmedi.",code="SOURCE_CONTRACT_VIOLATION")
    sql,fields,numeric=compile_relational_query(plan,active)
    rows=executor.read(sql,source="crm")
    if len(rows)>MAX_RESULT_ROWS:
        raise ContractError("İlişkisel sonuç teknik sınırı aştı; kesilmiş sonuç sunulmadı.",code="SOURCE_CONTRACT_VIOLATION")
    def scalar(value):
        if isinstance(value,(UUID,date,datetime)): return value.isoformat() if isinstance(value,(date,datetime)) else str(value)
        if isinstance(value,Decimal): return float(value)
        return value
    records=[{k:scalar(v) for k,v in row.items()} for row in rows]
    notes=["CRM ilişkisel sonuç güncel aktif kaynakları kullanır; tarihçe veya kesin kimlik birleştirmesi iddiası içermez.",
           "Yalnız doğrulanmış çocuk-üst kayıt ilişkileri kullanılır; kaynaklar tekil anahtarlarla kontrol edilir. LEFT JOIN aktiflik koşulu ON içinde uygulanır.",
           "Süzgeçler AND; range başlangıç dahil/bitiş hariçtir. is_null boş metni kapsamaz. Tarih-only süzgeç değeri İstanbul gece yarısından UTCye dönüştürülür."]
    if plan["limit"] is not None: notes.append("Kullanıcı planındaki sonuç sınırı: "+str(plan["limit"])+"; teknik kesilme değil.")
    return {"records":records,"output_fields":fields,"numeric_fields":numeric,"notes":notes,"gaps":[]}
