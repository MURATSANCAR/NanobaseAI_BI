"""Closed CRM relational plan; field names and joins come only from proven metadata."""
from __future__ import annotations
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import re
from uuid import UUID
from zoneinfo import ZoneInfo

from .language import fold, normalize_numbers, asked_limit
from .contracts import ContractError
from .relational_contracts import ENTITY_REGISTRY, RELATION_REGISTRY

ALIASES = ["root", *[f"j{i}" for i in range(1, 9)]]
FIELD_IDS = sorted({field for entity in ENTITY_REGISTRY.values() for field in entity["fields"]})

def _object(fields):
    return {"type":"object", "properties":fields, "required":list(fields), "additionalProperties":False}

FIELD_REF = _object({"alias":{"type":"string","enum":ALIASES}, "field":{"type":"string","enum":FIELD_IDS}})
RELATIONAL_SCHEMA = _object({
    "root":{"type":"string","enum":list(ENTITY_REGISTRY)},
    "distinct":{"type":"boolean"},
    "joins":{"type":"array","maxItems":8,"items":_object({
        "relation":{"type":"string","enum":list(RELATION_REGISTRY)},
        "left_alias":{"type":"string","enum":ALIASES}, "alias":{"type":"string","enum":ALIASES[1:]},
        "kind":{"type":"string","enum":["left","inner"]}})},
    # "field" is optional: after "op":"count_records" the model closes the object; a required field there made it
    # loop on blank lines until max_tokens (2026-10-05, vLLM 0.27.1, «Bu yıl kaç sipariş iptal edildi?» 6/6).
    "select":{"type":"array","minItems":1,"maxItems":32,"items":{**_object({
        "id":{"type":"string","pattern":"^[a-z][a-z0-9_]{0,63}$"},
        "op":{"type":"string","enum":["field","label","normalized_text","missing_flag","count_records","count_distinct","sum"]},
        "field":{"anyOf":[{"type":"null"},FIELD_REF]}}), "required":["id","op"]}},
    "filters":{"type":"array","maxItems":24,"items":_object({
        "field":FIELD_REF, "op":{"type":"string","enum":["eq","ne","contains","in","range","is_null","not_null","is_missing","not_missing"]},
        # Plain strings: a value object ({type,value}) made the model loop on blank lines under constrained decoding
        # (2026-10-04, vLLM 0.27.1, reproduced 3/3); the field type is known from the registry anyway.
        "values":{"type":"array","maxItems":100,"items":{"type":"string"}}})},
    "group_by":{"type":"array","maxItems":16,"items":FIELD_REF},
    "order_by":{"type":"array","maxItems":8,"items":_object({
        "column":{"type":"string","pattern":"^[a-z][a-z0-9_]{0,63}$"}, "descending":{"type":"boolean"}})},
    "limit":{"anyOf":[{"type":"null"},{"type":"integer","minimum":1,"maximum":50000}]},
})

def _invalid(message):
    raise ContractError(message, code="PLAN_INVALID")

def _keys(value, keys):
    if not isinstance(value,dict) or set(value)!=set(keys):
        _invalid("İlişkisel plan nesnesinin alanları geçersiz.")

def alias_entities(plan):
    aliases = {"root":plan["root"]}
    for join in plan["joins"]:
        aliases[join["alias"]] = RELATION_REGISTRY[join["relation"]]["right_entity"]
    return aliases

def _field(ref, aliases):
    _keys(ref, ["alias","field"])
    if not isinstance(ref["alias"],str) or ref["alias"] not in aliases:
        _invalid("Alan başvurusu henüz bağlı olmayan kaynağı kullanıyor.")
    entity = ENTITY_REGISTRY[aliases[ref["alias"]]]
    if not isinstance(ref["field"],str) or ref["field"] not in entity["fields"]:
        _invalid("Alan seçilen kaynak varlığında doğrulanmamış.")
    return entity["fields"][ref["field"]]

def _value(value, field_type):
    if isinstance(value,str):
        value={"type":field_type,"value":value}
    _keys(value,["type","value"])
    if value["type"]!=field_type or not isinstance(value["value"],str) or len(value["value"])>2000:
        _invalid("Süzgeç değeri kaynak alan türüyle uyuşmuyor.")
    text = value["value"]
    try:
        if field_type=="number":
            number=Decimal(text)
            if (not number.is_finite() or len(text)>80 or abs(number.as_tuple().exponent)>38
                    or number.adjusted()>37 or len(number.as_tuple().digits)>38): raise ValueError()
            text=format(number,"f")
            if len(text)>100: raise ValueError()
        elif field_type=="bool":
            if text not in {"true","false"}: raise ValueError()
        elif field_type=="identity": text=str(UUID(text))
        elif field_type=="date":
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}",text):
                # CRM timestamps are UTC; date-only input denotes Istanbul midnight.
                stamp=datetime.combine(date.fromisoformat(text),datetime.min.time(),ZoneInfo("Europe/Istanbul"))
            else:
                stamp=datetime.fromisoformat(text.replace("Z","+00:00"))
                if stamp.tzinfo is None: raise ValueError()
            text=stamp.astimezone(timezone.utc).isoformat()
        elif field_type!="text": raise ValueError()
    except (ValueError,InvalidOperation,OverflowError):
        _invalid("Süzgeç değeri geçerli sonlu sayı/kimlik/tarih değil.")
    return {"type":field_type,"value":text}

def ROOT_PK(data, aliases):
    return {"alias":"root","field":ENTITY_REGISTRY[aliases["root"]]["primary_key"]}

def validate_relational_query(data, question, reference_date):
    """Structure/type/grain checks only; caller must review original intent separately."""
    _keys(data,RELATIONAL_SCHEMA["properties"])
    if not isinstance(data["root"],str) or data["root"] not in ENTITY_REGISTRY:
        _invalid("Kök CRM varlığı doğrulanmış kayıtta yok.")
    bounds={"joins":(0,8),"select":(1,32),"filters":(0,24),"group_by":(0,16),"order_by":(0,8)}
    for key,(lo,hi) in bounds.items():
        if not isinstance(data[key],list) or not lo<=len(data[key])<=hi: _invalid("İlişkisel plan işlem sınırı aşıldı.")
    if type(data["distinct"]) is not bool: _invalid("Tekilleştirme seçimi boolean olmalı.")
    aliases={"root":data["root"]}
    for join in data["joins"]:
        _keys(join,["relation","left_alias","alias","kind"])
        if (not isinstance(join["relation"],str) or join["relation"] not in RELATION_REGISTRY
                or not isinstance(join["left_alias"],str) or join["left_alias"] not in aliases
                or not isinstance(join["alias"],str) or not isinstance(join["kind"],str)
                or join["alias"] not in ALIASES[1:] or join["alias"] in aliases or join["kind"] not in {"left","inner"}):
            _invalid("İlişki/bağlantı sırası veya takma ad geçersiz.")
        relation=RELATION_REGISTRY[join["relation"]]
        if relation["left_entity"]!=aliases[join["left_alias"]] or relation["cardinality"]!="many_to_one" or relation.get("target_unique") is not True:
            _invalid("İlişki yönü veya çoğaltmama kanıtı uygun değil.")
        target=ENTITY_REGISTRY[relation["right_entity"]]
        if relation["right_field"]!=target["primary_key"]:
            _invalid("İlişki hedefi doğrulanmış tekil anahtar değil.")
        aliases[join["alias"]]=relation["right_entity"]
        _field({"alias":join["left_alias"],"field":relation["left_field"]},aliases)
        _field({"alias":join["alias"],"field":relation["right_field"]},aliases)
    groups=[]
    for ref in data["group_by"]:
        _field(ref,aliases)
        key=(ref["alias"],ref["field"])
        if key in groups: _invalid("Tekrarlanan grup alanı.")
        groups.append(key)
    ids=set(); plain=[]; aggregates=False; selects=[]
    for selected in data["select"]:
        if isinstance(selected,dict) and "field" not in selected:
            selected={**selected,"field":None}
        _keys(selected,["id","op","field"])
        if (not isinstance(selected["id"],str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}",selected["id"])
                or selected["id"] in ids or not isinstance(selected["op"],str) or selected["op"] not in {"field","label","normalized_text","missing_flag","count_records","count_distinct","sum"}):
            _invalid("Projeksiyon kimliği veya işlemi geçersiz.")
        ids.add(selected["id"])
        if selected["op"]=="count_records":
            if selected["field"]==ROOT_PK(data, aliases):
                selected={**selected,"field":None}           # kök kimliğini açıkça yazmak aynı sayımdır
            if selected["field"] is not None: _invalid("Kayıt sayımı kök kimliğini kullanır, başka alan alamaz.")
        else:
            field=_field(selected["field"],aliases)
            if selected["op"]=="normalized_text" and field["type"]!="text":
                _invalid("Metin normalleştirme yalnız metin alanında geçerli.")
            if selected["op"]=="sum" and (field["type"]!="number" or field.get("sum_allowed") is not True):
                _invalid("Bu alanın toplamsal ölçü olduğu doğrulanmamış.")
            if selected["op"]=="sum" and selected["field"]["alias"]!="root":
                # Joins go child → parent only: a parent's amount repeats on every child row of the root.
                _invalid("Toplam yalnız kök kaydın kendi alanında alınır; bağlanan üst kaydın tutarı her alt satırda tekrarlanır.")
            if selected["op"]=="label" and not field.get("values"):
                _invalid("Etiket yalnız kod listesi olan alanda gösterilir.")
        selects.append(selected)
        if selected["op"] in {"field","label","normalized_text","missing_flag"}: plain.append((selected["field"]["alias"],selected["field"]["field"]))
        else: aggregates=True
    if aggregates and (data["distinct"] or any(item["op"] in {"missing_flag","normalized_text"} for item in selects)):
        _invalid("Toplulaştırmaya ek DISTINCT, düz eksiklik bayrağı veya normalleştirilmiş metin henüz desteklenmiyor.")
    if (aggregates and set(plain)!=set(groups)) or (groups and not aggregates):
        _invalid("Grup anahtarları ile seçilen düz alanlar aynı olmalı; salt listeye gizli tekilleştirme uygulanamaz.")
    filters=[]
    for predicate in data["filters"]:
        _keys(predicate,["field","op","values"])
        field=_field(predicate["field"],aliases); op=predicate["op"]; values=predicate["values"]
        arity={"eq":(1,1),"ne":(1,1),"contains":(1,1),"in":(1,100),"range":(2,2),"is_null":(0,0),"not_null":(0,0),"is_missing":(0,0),"not_missing":(0,0)}
        if not isinstance(op,str) or op not in arity or not isinstance(values,list) or not arity[op][0]<=len(values)<=arity[op][1]:
            _invalid("Süzgeç işlemi veya değer sayısı geçersiz.")
        if op=="contains" and field["type"]!="text": _invalid("İçerme işlemi yalnız metinde geçerli.")
        if op=="range" and field["type"] not in {"number","date"}: _invalid("Aralık yalnız sayı veya tarihte geçerli.")
        normalized=[_value(v,field["type"]) for v in values]
        if question and field["type"] in {"text","identity"}:
            for value in normalized:
                if fold(value["value"]) not in fold(question):
                    _invalid("Süzgeç metni/kimliği özgün kullanıcı sorusunda bulunamadı.")
        if op=="range":
            pair=[Decimal(v["value"]) if field["type"]=="number" else datetime.fromisoformat(v["value"]) for v in normalized]
            if pair[0]>=pair[1]: _invalid("Aralık başlangıcı bitişinden önce olmalı.")
        filters.append({"field":dict(predicate["field"]),"op":op,"values":normalized})
    ordered=set()
    for order in data["order_by"]:
        _keys(order,["column","descending"])
        if not isinstance(order["column"],str) or order["column"] not in ids or order["column"] in ordered or type(order["descending"]) is not bool:
            _invalid("Sıralama yalnız tekil seçilmiş kolon kimliğiyle yapılır.")
        ordered.add(order["column"])
    if data["limit"] is not None and (type(data["limit"]) is not int or not 1<=data["limit"]<=50000):
        _invalid("İlişkisel sonuç sınırı geçersiz.")
    if question and data["limit"] is not None and not asked_limit(data["limit"],question):
        _invalid("Sonuç sınırı özgün kullanıcı sorusunda bulunamadı.")
    return {**data,"select":selects,"filters":filters}


RELATIONAL_CAPABILITIES = {
    "source":"CRM current active records; relations and fields must be in this registry",
    "entities":{key:{"primary_key":entity["primary_key"],"grain":entity.get("grain","physical record"), "semantic_notes":entity.get("semantic_notes",[]),
        **({"label_tr":entity["label_tr"]} if entity.get("label_tr") else {}),
        "fields":{field:{"type":spec["type"],"semantics":spec.get("semantics",""),"sum_allowed":spec.get("sum_allowed",False),
                         **({"label_tr":spec["label_tr"]} if spec.get("label_tr") else {}),
                         **({"codes":spec["values"]} if spec.get("values") else {})}
                  for field,spec in entity["fields"].items()}}
        for key,entity in ENTITY_REGISTRY.items()},
    "relations":{key:{field:relation[field] for field in
        ("left_entity","right_entity","left_field","right_field","cardinality")}
        for key,relation in RELATION_REGISTRY.items()},
    "operations":{
        "joins":"root alias is root; new aliases j1..j8. Only forward child FK -> unique parent PK. LEFT preserves missing/inactive parents with NULL; INNER excludes those roots. Reverse parent -> children is not supported.",
        "projection":"field (raw), label (code-list field shown as its CRM label; filter such fields by the numeric code from codes), normalized_text (text-only trim spaces and blank to NULL), missing_flag (text NULL/trimmed empty; other fields NULL), distinct true means unique whole selected row, count_records (distinct root PK), count_distinct (nonNULL field), sum only when sum_allowed and only on a root field (a joined parent's amount repeats per child row). Raw numeric field is not necessarily additive.",
        "filters":"AND of eq/ne/contains/in/range/is_null/not_null/is_missing/not_missing. eq/ne/contains need exactly one value, in at least one, range two; a filter without its value is invalid — omit the filter instead. A code-list field (codes) is filtered with the numeric code whose label matches the question. Active/passive record rules are applied automatically; never add a state filter for them. is_missing/not_missing use NULL or trimmed blank for text, NULL for other types. range inclusive lower/exclusive upper. NULL tests do not test blank strings. ne does not retain NULL. Fields cannot be compared to other fields.",
        "literal":"filter values are plain strings in the field's type; number finite decimal, identity UUID, bool true/false; date ISO date means Istanbul midnight or timestamp must include UTC offset.",
        "grouping":"When aggregates selected, group_by must equal all plain selected field references. DISTINCT projection requires explicit distinct=true and cannot combine with aggregates. Missing flags and normalized_text are detail-only; no derived arithmetic, HAVING or conditional counters.",
        "ordering":"Only selected output IDs, descending boolean. Technical tie-breaker is root PK for detail or group fields for aggregate.",
        "limit":"Explicit user limit only; null means whole result up to technical 50000 cap, fail closed beyond cap.",
    },
    "non_claims":["No historical state reconstruction", "No fuzzy identity merge or name-based join",
                  "No legal contract priority inference", "No reverse fanout or arbitrary SQL"],
}


def describe_relational_output(plan):
    """Exact executable population and output shape for the independent intent gate."""
    plan=validate_relational_query(plan,"",date.today())
    aliases=alias_entities(plan)
    root=ENTITY_REGISTRY[plan["root"]]
    def reference(ref):
        entity=aliases[ref["alias"]];spec=ENTITY_REGISTRY[entity]["fields"][ref["field"]]
        out={"alias":ref["alias"],"entity":entity,"field":ref["field"],"type":spec["type"],"semantics":spec.get("semantics","")}
        if spec.get("label_tr"): out["label_tr"]=spec["label_tr"]
        return out
    def meaning(predicate):
        # Denetçi kodu değil anlamını görür: yil=100000000 → «2026»; kod listesi olmayan değer olduğu gibi kalır.
        spec=ENTITY_REGISTRY[aliases[predicate["field"]["alias"]]]["fields"][predicate["field"]["field"]]
        codes=spec.get("values") or {}
        return [codes.get(str(v["value"]).split(".")[0], v["value"]) if codes else v["value"] for v in predicate["values"]]
    columns={}
    for item in plan["select"]:
        if item["op"]=="count_records":
            columns[item["id"]]={"operation":"count_records","meaning":"Distinct root identities in the filtered population",
                "root_entity":plan["root"],"root_key":root["primary_key"],"type":"number"}
        else:
            columns[item["id"]]={"operation":item["op"],"source":reference(item["field"]),
                "type":"bool" if item["op"]=="missing_flag" else "number" if item["op"] in {"count_records","count_distinct","sum"} else reference(item["field"])["type"],
                "null_semantics":"True for NULL or trimmed empty text; otherwise false" if item["op"]=="missing_flag" else "Leading/trailing spaces removed; blank becomes NULL" if item["op"]=="normalized_text" else "NULL excluded from aggregate" if item["op"]!="field" else "NULL preserved"}
    aggregate=any(item["op"] in {"count_records","count_distinct","sum"} for item in plan["select"])
    return {
        "columns":columns,
        "entity_semantics":{alias:ENTITY_REGISTRY[entity].get("semantic_notes",[]) for alias,entity in aliases.items()},
        "grain":{"root_entity":plan["root"],"root_key":root["primary_key"],
            "result":"one row per selected group" if plan["group_by"] else "one aggregate row" if aggregate else "one row per distinct selected projection" if plan["distinct"] else "one row per surviving root identity",
            "group_by":[reference(ref) for ref in plan["group_by"]],
            "duplicate_projection_rows":"deduplicated by all selected values" if plan["distinct"] else "preserved in detail; two different root IDs may display same selected values"},
        "population_contract":{
            "root_entity":plan["root"],"active_only":True,
            "active_predicates":{alias:ENTITY_REGISTRY[entity]["active_predicate"] for alias,entity in aliases.items()},
            "passive_rule":"Additionally every table with statecode: statecode=0 and no status reason labelled Pasif/Inactive (root WHERE, joined targets in ON).",
            "joins":[{**join,"relationship":RELATIONAL_CAPABILITIES["relations"][join["relation"]]} for join in plan["joins"]],
            "filters_AND":[{**predicate,"field":reference(predicate["field"]),"values_meaning":meaning(predicate)} for predicate in plan["filters"]],
            "filter_stage":"Before projection, optional DISTINCT, aggregation and ordering; explicit limit last",
            "missing_flags_filter_population":False, "projection_distinct":plan["distinct"],
            "left_join_missing_parent":"Root remains with NULL joined fields unless explicit WHERE filters reject NULL",
            "inner_join_missing_parent":"Root excluded",
            "active_state_meaning":"Current active records, not historical active snapshots",
        },
        "order_by":plan["order_by"],"limit":plan["limit"],
        "date_semantics":"Normalized date literals are UTC. Date-only inputs use Istanbul midnight. range is start inclusive/end exclusive; timestamps are source field values, not inferred business-event dates.",
        "non_claims":RELATIONAL_CAPABILITIES["non_claims"],
        "unsupported_requested_operations":["Reverse parent-to-child joins", "Field-to-field comparison", "Conditional aggregate", "HAVING", "Identity verdict", "Unknown registry field or relation"],
        "gaps":"No built-in runtime business gap; unsupported requested calculation must be handled by intent gate with explicit scoped permission, never silently omitted.",
    }
