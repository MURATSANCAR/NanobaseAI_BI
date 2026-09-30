"""Cross-source identity evidence without name matching or fan-out allocation."""
from collections import defaultdict
from datetime import date
from decimal import Decimal
import json

from .contracts import ContractError
from .crm_reports import Sources

CROSS_REPORTS = {
    "cross_book_sales_quality": "Logo kitap kodu ile aktif CRM stok kodunu eşleştir; tek/eksik/çoğul eşleşme, ISBN/kişi-yazar/yayıncı boşlukları, ad farkı ve dönem net satış/iade/miktarı. Çoğul CRM kartlarına satış dağıtılmaz. no_sales yalnız Logo kimliği eşleşmiş, belirtilen dönemde satış7/8/9 hareketi olmayan aktif CRM kartıdır; iadesi olabilir, eşleşmeyen satışsız sayılmaz. Çok yazarlı kitaba tek satış tutarı verilir, kişi başına bölünmez; çoğul kitap eşleşmesinde yazar ataması yapılmaz. Tarihsel yayıncı değil bugünkü sınıflamadır.",
    "cross_customer_sales_quality": "Logo TAXNR ile CRM Vergi No alanını boş olmayan birebir metin olarak eşleştir; ad benzerliği veya TC kimlik dönüşümü yok. Her vergi grubunun satışını bir kez tut; çoklu CRM/Logo kartlarını kimlik listesinde göster. Ülke/kimlik türü kanıtlanmadan kesin aynı tüzel kişi hükmü yok. no_sales yalnız Logo kodu eşleşmiş dönemde satışsız CRM vergi grubudur.",
}


def _num(value): return Decimal(str(value or 0))
def _key(value): return str(value).strip().casefold() if value is not None and str(value).strip() else None
def _json(value): return json.dumps(value,ensure_ascii=False,default=str)


def execute(executor, spec):
    from .executor import literal
    mode=spec["mode"]
    if mode not in CROSS_REPORTS: raise ContractError("Çapraz kaynak raporu tanımlı değil.")
    if not spec.get("start") or not spec.get("end"): raise ContractError("Çapraz kaynak raporunun dönemi belirtilmeli.",code="NEEDS_CLARIFICATION")
    book=mode=="cross_book_sales_quality"
    source=Sources(executor)
    crm=list(source.books().values()) if book else list(source.customers().values())
    by_key=defaultdict(list)
    for row in crm:
        k=_key(row.get("book_code") if book else row.get("tax_number"))
        if k: by_key[k].append(row)
    links=source.author_links() if book else {}
    people=source.people() if book else {}
    identity=defaultdict(set);names=defaultdict(set);sales={};selected_keys=set();sale_activity=set()
    wanted=spec.get("book_code") if book else spec.get("customer_code")
    for a,b,firm,period in executor.partitions(date.fromisoformat(spec["start"]),date.fromisoformat(spec["end"])):
        line=f"LG_{firm}_{period}_STLINE"; card=f"LG_{firm}_ITEMS" if book else f"LG_{firm}_CLCARD"
        extra=[] if book else ["TAXNR"]
        executor.verify_schema({line:["STOCKREF","CLIENTREF","DATE_","CANCELLED","LINETYPE","INVOICEREF","TRCODE","LINENET","AMOUNT","UINFO1","UINFO2"],card:["LOGICALREF","CODE","NAME" if book else "DEFINITION_",*extra]},"logo")
        title="NAME" if book else "DEFINITION_"
        all_cards=executor.read(f"SELECT LOGICALREF card_id,LTRIM(RTRIM(CODE)) card_code,{title} card_name"+("" if book else ",TAXNR tax_number")+f" FROM dbo.[{card}]")
        cards={int(row["card_id"]):row for row in all_cards}
        for r in all_cards:
            if wanted and _key(r["card_code"])!=_key(wanted):continue
            k=_key(r["card_code"] if book else r.get("tax_number"))
            if k:
                identity[k].add(str(r["card_code"]))
                names[k].add(str(r["card_name"] or ""))
                if not wanted or _key(r["card_code"])==_key(wanted):selected_keys.add(k)
        ref="STOCKREF" if book else "CLIENTREF"
        conditions=f"S.CANCELLED=0 AND S.LINETYPE=0 AND S.INVOICEREF<>0 AND S.TRCODE IN (2,3,7,8,9) AND S.DATE_>='{a}' AND S.DATE_<'{b}'"
        if wanted:conditions+=f" AND I.CODE={literal(wanted)}"
        rows=executor.read(f"SELECT S.{ref} card_id,SUM(CASE WHEN S.TRCODE IN (2,3) THEN -S.LINENET ELSE S.LINENET END) net_sales,SUM(CASE WHEN S.TRCODE IN (2,3) THEN S.LINENET ELSE 0 END) return_amount,SUM(CASE WHEN S.TRCODE IN (7,8) THEN S.AMOUNT ELSE 0 END) sold_quantity,SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN 1 ELSE 0 END) sale_activity_count,SUM(CASE WHEN S.TRCODE IN (7,8) AND (S.UINFO1 IS NULL OR S.UINFO2 IS NULL OR S.UINFO1<=0 OR S.UINFO1<>S.UINFO2) THEN 1 ELSE 0 END) unverified_units FROM dbo.[{line}] S LEFT JOIN dbo.[{card}] I ON I.LOGICALREF=S.{ref} WHERE {conditions} GROUP BY S.{ref}")
        for r in rows:
            c=cards.get(int(r["card_id"]),{})
            k=_key(c.get("card_code") if book else c.get("tax_number")) or f"__unresolved:{firm}:{r['card_id']}"
            if r["sale_activity_count"]:sale_activity.add(k)
            target=sales.setdefault(k,dict(net_sales=Decimal(0),return_amount=Decimal(0),sold_quantity=Decimal(0),unverified_units=0))
            for m in target:target[m]+=_num(r[m])
            identity[k].add(str(c.get("card_code") or f"{firm}:{r['card_id']}"));names[k].add(str(c.get("card_name") or ""))
    scope=spec.get("match_status","all")
    keys=set(sales)
    if scope=="no_sales":keys=(set(by_key)&selected_keys)-sale_activity
    output=[];unverified_units=0
    for k in sorted(keys):
        matches=by_key.get(k,[]);known=k in identity
        if scope=="no_sales" and not known:continue
        status="unmatched" if not matches else "matched" if len(matches)==1 else "ambiguous"
        amounts=sales.get(k,dict(net_sales=Decimal(0),return_amount=Decimal(0),sold_quantity=Decimal(0),unverified_units=0))
        core={"match_status":status,"logo_codes":_json(sorted(identity.get(k,()))),"logo_names":_json(sorted(names.get(k,()))),
              "net_sales":amounts["net_sales"],"return_amount":amounts["return_amount"],"sold_quantity":None if amounts["unverified_units"] else amounts["sold_quantity"]}
        if book:
            people_ids=links.get(str(matches[0]["book_id"]).lower(),set()) if len(matches)==1 else set()
            missing=[]
            for field in ("isbn","publisher"):
                if not matches or any(not _key(r.get(field)) for r in matches):missing.append(field)
            if not matches or any(not links.get(str(r["book_id"]).lower(),set()) for r in matches):missing.append("author_link")
            if len(matches)>1:missing.append("author_attribution_ambiguous")
            crm_names={str(r.get("book_name") or "") for r in matches}
            different=bool(matches) and {_key(v) for v in crm_names}!={_key(v) for v in names[k]}
            core.update(book_code=None if k.startswith("__unresolved:") else k,
                        crm_book_ids=_json([str(r["book_id"]) for r in matches]),crm_book_names=_json(sorted(crm_names)),
                        publisher=matches[0].get("publisher") if len(matches)==1 else None,
                        author_ids=_json(sorted(people_ids)),author_names=_json(sorted({str(people.get(pid,{}).get("person_name") or pid) for pid in people_ids})),
                        shared_authors=None if len(matches)>1 else len(people_ids)>1,missing_fields=_json(missing),name_difference=different)
        else:
            missing=[]
            for field in ("city","region"):
                if not matches or any(not _key(r.get(field)) for r in matches):missing.append(field)
            crm_names={str(r.get("customer_name") or "") for r in matches}
            different=bool(matches) and {_key(v) for v in crm_names}!={_key(v) for v in names[k]}
            core.update(tax_number=None if k.startswith("__unresolved:") else k,
                        crm_customer_ids=_json([str(r["customer_id"]) for r in matches]),crm_customer_names=_json(sorted(crm_names)),
                        crm_address_regions=_json(sorted({str(r.get("region")) for r in matches if r.get("region")})),
                        crm_sales_territories=_json(sorted({str(r.get("territory")) for r in matches if r.get("territory")})),
                        crm_countries=_json(sorted({str(r.get("country")) for r in matches if r.get("country")})),
                        missing_fields=_json(missing),name_difference=different)
        if scope in ("matched","unmatched","ambiguous") and status!=scope:continue
        if scope=="missing_fields" and not missing:continue
        if scope=="name_difference" and not different:continue
        unverified_units+=bool(amounts["unverified_units"])
        output.append(core)
    # Conservation is checked before any explicit display limit for the complete sales population.
    if scope=="all":
        for metric in ("net_sales","return_amount"):
            if sum((r[metric] for r in output),Decimal(0))!=sum((r[metric] for r in sales.values()),Decimal(0)):
                raise ContractError("Kaynaklar arası ölçü korunumu bozuldu.",code="SOURCE_CONTRACT_VIOLATION")
    fields=list(output[0]) if output else ["match_status","logo_codes","logo_names","net_sales","return_amount","sold_quantity"]+(["book_code","crm_book_ids","crm_book_names","publisher","author_ids","author_names","shared_authors","missing_fields","name_difference"] if book else ["tax_number","crm_customer_ids","crm_customer_names","crm_address_regions","crm_sales_territories","crm_countries","missing_fields","name_difference"])
    order=spec.get("order_by") or "net_sales"
    if order not in fields:raise ContractError("Rapor sıralama alanı çıktı sözleşmesinde yok.")
    present=[r for r in output if r.get(order) is not None]
    missing=[r for r in output if r.get(order) is None]
    output=sorted(present,key=lambda r:(r[order],r["logo_codes"]),reverse=spec.get("descending",True))+missing
    if spec.get("limit"):output=output[:spec["limit"]]
    gaps=[]
    if unverified_units:gaps.append({"status":"UNVERIFIED_DEFINITION","reason":f"{unverified_units} kaynak grubunda kitap adedi birimi doğrulanamadı; tutarlar korunup miktar boş bırakıldı."})
    if not book:gaps.append({"status":"UNVERIFIED_DEFINITION","reason":"Vergi numarası alanları metin olarak eşleştirildi; ülke ve vergi kimliği türü teyidi olmadan kartların kesin aynı tüzel kişi olduğu sonucuna varılmaz."})
    notes=[CROSS_REPORTS[mode],"Eşleşmeyen ve çoğul eşleşen kaynak tutarları korunur; çoğul CRM kartlarına dağıtılmaz. Sınıflama rapor anındaki aktif CRM bilgileridir."]
    if wanted:notes.append("Kaynak kimlikleri ve hareketler yalnız istenen Logo kodu kapsamındadır; aynı vergi numarasındaki başka Logo kartlarının toplamı değildir.")
    return {"records":[{k:float(v) if isinstance(v,Decimal) else v for k,v in row.items()} for row in output],"output_fields":fields,"numeric_fields":["net_sales","return_amount","sold_quantity"],"notes":notes,"gaps":gaps}
