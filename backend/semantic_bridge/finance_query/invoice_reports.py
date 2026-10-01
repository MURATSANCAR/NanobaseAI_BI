"""Document-level Logo evidence. No guessed allocation or automatic duplicate verdict."""
from collections import defaultdict
from datetime import date
from decimal import Decimal
import hashlib
import json
from statistics import median

from .contracts import ContractError, RETURN_INVOICE_CODES, SALES_INVOICE_CODES, codes_sql
from .result_metadata import format_count, return_invoice_note

INVOICE_REPORTS = {
    "invoice_reconciliation": "Fatura NETTOTAL-TOTALVAT ile malzeme satırı LINENET toplamını belge kimliğinde karşılaştır; ham masraf/indirim alanlarını göster. Farkın nedeni veya yuvarlama olduğu tahmin edilmez.",
    "invoice_duplicates": "Aynı kaynakta aynı müşteri/gün/NETTOTAL fatura adayları; stok, miktar, birim oranı ve satır net tutarından bağımsız içerik izi. Benzerlik şüphesi, kesin mükerrer hükmü değildir.",
    "orphan_invoice_lines": "Malzeme satırı olmayan satış faturaları ve fatura referansı boş/bulunamayan malzeme hareketleri. Faturasız sevkiyat tek başına hata değildir.",
    "invoice_statistics": "Dönemde müşteri başına satış fatura başlığı sayısı (iade faturaları dahil değil), NETTOTAL toplamı, aritmetik ortalama ve ortanca. Satır adedi değildir; iadeler düşülmemiş fatura toplamıdır. Dönemdeki iade faturası sayısı ayrıca ölçülüp notta verilir; iadeler istenirse ayrı iade sayısı ve iadeler dahil sayı kolonları eklenir, ortalama/ortanca satış faturalarında kalır.",
}
SALES = codes_sql(SALES_INVOICE_CODES)
RETURNS = codes_sql(RETURN_INVOICE_CODES)


def _d(value):
    return Decimal(str(value or 0))


def execute(executor, spec):
    mode = spec.get("mode", spec.get("report"))
    if mode not in INVOICE_REPORTS:
        raise ContractError("Fatura raporu tanımlı değil.")
    if not spec.get("start") or not spec.get("end"):
        raise ContractError("Fatura raporu için tarih aralığı gereklidir.", code="NEEDS_CLARIFICATION")
    output, notes, gaps = [], [INVOICE_REPORTS[mode]], []
    fields = []
    returns = defaultdict(int)
    include_returns = mode == "invoice_statistics" and spec.get("include_returns")
    for a,b,firm,period in executor.partitions(date.fromisoformat(spec["start"]),date.fromisoformat(spec["end"])):
        invoice, line, client = f"LG_{firm}_{period}_INVOICE", f"LG_{firm}_{period}_STLINE", f"LG_{firm}_CLCARD"
        required = {invoice:["LOGICALREF","FICHENO","DATE_","CLIENTREF","CANCELLED","TRCODE","NETTOTAL"],
                    client:["LOGICALREF","CODE","DEFINITION_"]}
        if mode != "invoice_statistics":
            required[line] = ["LOGICALREF","INVOICEREF","LINETYPE","CANCELLED","TRCODE","DATE_","STOCKREF","AMOUNT","LINENET"]
        if mode == "invoice_reconciliation":
            required[invoice] += ["TOTALVAT","TOTALEXPENSES","TOTALDISCOUNTS","ADDDISCOUNTS","ADDEXPENSES"]
        if mode == "invoice_duplicates":
            required[line] += ["UINFO1","UINFO2"]
        executor.verify_schema(required,"logo")
        head = f"i.CANCELLED=0 AND i.TRCODE IN {SALES} AND i.DATE_>='{a}' AND i.DATE_<'{b}'"
        base = f" FROM dbo.[{invoice}] i LEFT JOIN dbo.[{client}] c ON c.LOGICALREF=i.CLIENTREF "
        identities = "i.LOGICALREF invoice_id,i.FICHENO invoice_number,CONVERT(varchar(10),i.DATE_,23) invoice_date,c.CODE customer_code,c.DEFINITION_ customer_name"
        if mode == "invoice_statistics":
            rows = executor.read("SELECT " + identities + ",i.NETTOTAL invoice_total"+base+" WHERE "+head)
            # Same period and source, return invoices only: never mixed into the sales statistics.
            for row in executor.read("SELECT c.CODE customer_code,c.DEFINITION_ customer_name,COUNT_BIG(*) return_invoice_count"+base+
                                     f" WHERE i.CANCELLED=0 AND i.TRCODE IN {RETURNS} AND i.DATE_>='{a}' AND i.DATE_<'{b}' GROUP BY c.CODE,c.DEFINITION_"):
                returns[(row["customer_code"], row["customer_name"])] += int(row["return_invoice_count"])
        elif mode == "invoice_reconciliation":
            # No date filter in the child aggregate: all rows belonging to a selected invoice count.
            sql = "SELECT "+identities+",i.NETTOTAL invoice_total,i.TOTALVAT invoice_vat,i.NETTOTAL-i.TOTALVAT header_excluding_vat," \
                "i.TOTALEXPENSES header_expenses,i.TOTALDISCOUNTS header_discounts,i.ADDDISCOUNTS header_additional_discounts,i.ADDEXPENSES header_additional_expenses," \
                "COALESCE(l.material_lines,0) material_lines,COALESCE(l.material_net,0) material_line_net," \
                "COALESCE(l.other_lines,0) other_lines,COALESCE(l.other_net,0) other_line_net," \
                "i.NETTOTAL-i.TOTALVAT-COALESCE(l.material_net,0) difference_from_material_net" +base+ \
                f" OUTER APPLY (SELECT SUM(CASE WHEN s.LINETYPE=0 THEN 1 ELSE 0 END) material_lines," \
                "SUM(CASE WHEN s.LINETYPE=0 THEN s.LINENET ELSE 0 END) material_net," \
                "SUM(CASE WHEN s.LINETYPE<>0 THEN 1 ELSE 0 END) other_lines," \
                f"SUM(CASE WHEN s.LINETYPE<>0 THEN s.LINENET ELSE 0 END) other_net FROM dbo.[{line}] s WHERE s.INVOICEREF=i.LOGICALREF AND s.CANCELLED=0) l WHERE "+head
            rows=executor.read(sql)
            rows=[r for r in rows if abs(_d(r["difference_from_material_net"]))>Decimal("0.01")]
            gaps.append({"status":"UNVERIFIED_DEFINITION","reason":"Masraf, iskonto, hizmet ve diğer vergi dağıtımının farkı hangi sırayla açıkladığı doğrulanmadan bakiye farkı yuvarlama veya hata diye sınıflandırılmadı."})
        elif mode == "invoice_duplicates":
            rows=executor.read("SELECT "+identities+",i.NETTOTAL invoice_total"+base+" WHERE "+head+
                f" AND EXISTS (SELECT 1 FROM dbo.[{invoice}] j WHERE j.CANCELLED=0 AND j.TRCODE IN {SALES} AND j.CLIENTREF=i.CLIENTREF AND j.NETTOTAL=i.NETTOTAL AND CONVERT(date,j.DATE_)=CONVERT(date,i.DATE_) AND j.LOGICALREF<>i.LOGICALREF)")
            by_invoice=defaultdict(list)
            ids=[int(r["invoice_id"]) for r in rows]
            for start in range(0,len(ids),500):
                batch=",".join(map(str,ids[start:start+500]))
                parts=executor.read(f"SELECT INVOICEREF invoice_id,STOCKREF stock_id,UINFO1 unit_numerator,UINFO2 unit_denominator,SUM(AMOUNT) quantity,SUM(LINENET) line_net FROM dbo.[{line}] WHERE CANCELLED=0 AND LINETYPE=0 AND INVOICEREF IN ({batch}) GROUP BY INVOICEREF,STOCKREF,UINFO1,UINFO2")
                for row in parts:
                    by_invoice[int(row.pop("invoice_id"))].append(row)
            groups=defaultdict(list)
            for row in rows:
                contents=sorted(by_invoice[int(row["invoice_id"])],key=lambda r:json.dumps(r,sort_keys=True,default=str))
                # Money rounds only for candidate fingerprinting; source records stay unchanged.
                normalized=[{k:str(_d(v).quantize(Decimal("0.000001"))) if isinstance(v,(int,float,Decimal)) else v for k,v in r.items()} for r in contents]
                row["line_fingerprint"]=hashlib.sha256(json.dumps(normalized,sort_keys=True,default=str).encode()).hexdigest()
                row["material_groups"]=len(contents)
                groups[(row["customer_code"],row["invoice_date"],str(_d(row["invoice_total"])))].append(row)
            for members in groups.values():
                for row in members:
                    row["same_content_candidates"]=sum(r["line_fingerprint"]==row["line_fingerprint"] and r["invoice_id"]!=row["invoice_id"] for r in members) if row["material_groups"] else None
                    row["finding"]="same_header_and_material_content_candidate" if row["same_content_candidates"] else "same_header_review_required"
        else:
            sql="SELECT "+identities+",i.NETTOTAL amount,'invoice_without_material_line' finding"+base+" WHERE "+head+f" AND NOT EXISTS (SELECT 1 FROM dbo.[{line}] s WHERE s.INVOICEREF=i.LOGICALREF AND s.CANCELLED=0 AND s.LINETYPE=0)"
            rows=executor.read(sql)
            for r in rows:r["line_id"]=None
            orphan=executor.read(f"SELECT s.LOGICALREF line_id,s.INVOICEREF invoice_id,CONVERT(varchar(10),s.DATE_,23) movement_date,s.LINENET amount,CASE WHEN s.INVOICEREF=0 THEN 'movement_without_invoice_reference' ELSE 'movement_invoice_not_found' END finding FROM dbo.[{line}] s LEFT JOIN dbo.[{invoice}] i ON i.LOGICALREF=s.INVOICEREF WHERE s.CANCELLED=0 AND s.LINETYPE=0 AND s.TRCODE IN (2,3,7,8,9) AND s.DATE_>='{a}' AND s.DATE_<'{b}' AND (s.INVOICEREF=0 OR i.LOGICALREF IS NULL)")
            for r in rows:r["movement_date"]=None
            for r in orphan:r.update(invoice_number=None,invoice_date=None,customer_code=None,customer_name=None)
            rows.extend(orphan)
            notes.append("Fatura referansı olmayan malzeme hareketleri faturalı satış ölçüsüne girmez. Referansı olup hedef faturası bulunamayan hareket mevcut satır ölçüsüne girebilir; kaynak kaydı incelenmelidir.")
        for row in rows:row["source_code"]=firm+"_"+period
        output.extend(rows)
    if mode=="invoice_statistics":
        groups=defaultdict(list)
        for row in output:groups[(row["customer_code"],row["customer_name"])].append(_d(row["invoice_total"]))
        if include_returns:
            # Customers with only return invoices are real rows of the requested union.
            for key in returns: groups.setdefault(key, [])
        output=[{"customer_code":k[0],"customer_name":k[1],"invoice_count":len(v),"invoice_total":sum(v,Decimal(0)),
                 "invoice_mean":sum(v)/len(v) if v else None,"invoice_median":median(v) if v else None,
                 **({"return_invoice_count":returns.get(k,0),"invoice_count_with_returns":len(v)+returns.get(k,0)} if include_returns else {})}
                for k,v in groups.items()]
        output.sort(key=lambda r:(r["invoice_total"],str(r["customer_code"])),reverse=True)
        total=sum(returns.values())
        if include_returns:
            notes.append(f"İade faturaları istendiği için ayrı kolonda sayıldı ve iadeler dahil fatura sayısına eklendi; dönemde toplam {format_count(total)} iade faturası var. Ortalama ve ortanca yalnız satış faturalarıdır.")
        else:
            notes.append(return_invoice_note([(spec["start"],spec["end"],total)]))
    fields = list(output[0]) if output else {
        "invoice_statistics":["customer_code","customer_name","invoice_count","invoice_total","invoice_mean","invoice_median"]+(["return_invoice_count","invoice_count_with_returns"] if include_returns else []),
        "invoice_duplicates":["invoice_id","invoice_number","invoice_date","customer_code","customer_name","invoice_total","line_fingerprint","material_groups","same_content_candidates","finding","source_code"],
        "invoice_reconciliation":["invoice_id","invoice_number","invoice_date","customer_code","customer_name","invoice_total","invoice_vat","header_excluding_vat","header_expenses","header_discounts","header_additional_discounts","header_additional_expenses","material_lines","material_line_net","other_lines","other_line_net","difference_from_material_net","source_code"],
        "orphan_invoice_lines":["invoice_id","invoice_number","invoice_date","customer_code","customer_name","amount","finding","line_id","movement_date","source_code"]}[mode]
    numeric=set(fields)&{"invoice_id","invoice_total","invoice_vat","header_excluding_vat","header_expenses","header_discounts","header_additional_discounts","header_additional_expenses","material_lines","material_line_net","other_lines","other_line_net","difference_from_material_net","material_groups","same_content_candidates","amount","line_id","invoice_count","invoice_mean","invoice_median","return_invoice_count","invoice_count_with_returns"}
    if spec.get("limit"):
        output=output[:spec["limit"]]
    counts=[{"start":spec["start"],"end":spec["end"],"returnInvoiceCount":sum(returns.values())}] if mode=="invoice_statistics" and not include_returns else []
    return {"records":[{k:float(v) if isinstance(v,Decimal) else v for k,v in row.items()} for row in output],"output_fields":fields,"numeric_fields":numeric,"notes":notes,"gaps":gaps,"return_invoice_counts":counts}
