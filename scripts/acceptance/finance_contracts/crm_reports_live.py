"""Remote real-CRM/API acceptance with an independent source-row oracle.

Does not import finance_query, use its generated SQL, or read the retired catalog.
Every full PASS checks the entire stored execution: identities, all columns,
all values and result delivery. Correct partial/unsupported behavior is reported
separately and is never a full-answer/numeric PASS. No local execution is allowed.
"""
import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import signal
import sqlite3
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from uuid import UUID
from zoneinfo import ZoneInfo

from composable_live import ROOT, connect, environment, manifest, query, save, REFERENCE_CONTEXT, REFERENCE_RETRIES


def cases():
    # Oracle dates are declared independently, not copied from a generated plan.
    data = [
        ("book_quality", "CRM aktif kitaplarının ISBN, stok kodu ve yayın evi eksiklerini; aynı kitapta birden fazla eksik olmasını, kitap listesini ve yayın evi sayılarını birlikte göster.", None, None),
        ("duplicate_isbn", "CRM'de aynı güncel ISBN'yi kullanan aktif kitapları ad, baskı ve yayın eviyle karşılaştır. Kesin mükerrer deme.", None, None),
        ("duplicate_book_code", "CRM'de aynı stok koduna sahip aktif kitapları isim, ISBN, baskı ve yayın eviyle göster; aynı eser olduklarını varsayma.", None, None),
        ("duplicate_title", "CRM'de aynı başlıklı aktif kitapların yazar, ISBN, baskı ve yayın evi bilgilerini karşılaştır; kimlikleri birleştirme.", None, None),
        ("title_variants", "CRM kitap başlıklarında yalnız boşluk, noktalama ve harf farkıyla ayrı görünen kayıtları eşleşme adayı olarak göster; otomatik birleştirme yapma.", None, None),
        ("author_link_gaps", "CRM'de yazar künyesi dolu ama aktif Yazar rolündeki kişiyle bağlantısı olmayan aktif kitapları yayın evi sayılarıyla birlikte listele.", None, None),
        ("author_text_mismatch", "CRM'de aktif kişi yazar bağlantılarının adları kitap yazar künyesiyle uyuşmayan kayıtları bul; yazım farkı adaylarını belirt, kişileri birleştirme.", None, None),
        ("duplicate_authors", "CRM'de aynı adlı aktif yazar kişileri ayrı kimlikler, kayıt tarihleri ve bağlı kitaplarıyla göster.", None, None),
        ("multi_author_books", "CRM'de birden fazla benzersiz aktif kişi yazarı olan kitapları ve yayın evlerine göre kitap sayılarını göster; yazar sayısını ayrıca ver.", None, None),
        ("authors_without_books", "CRM'de aktif yazar işaretli olup hiçbir aktif kitaba Yazar rolüyle bağlanmamış kişileri kayıt açılış ve güncelleme tarihleriyle göster.", None, None),
        ("publisher_author_coverage", "CRM yayın evlerine göre aktif kitap ve benzersiz bağlı kişi yazar sayılarını, yayın evleri arasında ortak yazar kimliklerini göster.", None, None),
        ("subbrand_consistency", "CRM'de alt markası atanmış ama ana yayın evi eksik kitapları göster; iki alt marka alanını ayır ve ana yayın evi ilişkisini doğrulayamadığın kısmı açıkça belirt.", None, None),
        ("book_change_history", "1 Eylül 2026 dahil 1 Ekim 2026 hariç dönemde güncellenen CRM kitaplarında değişiklik geçmişini göster. Baskı/fiyat tarihçesini genel eski-yeni alan değişikliği gibi sunma; doğrulayamadığını belirt.", "2026-09-01", "2026-10-01"),
        ("author_contact_coverage", "CRM'de yazar işaretli aktif kişilerin telefon ve e-posta alanı doluluğunu yayın evleri bazında benzersiz kişi sayısıyla göster; gerçek ulaşılabilirlik garantisi verme.", None, None),
        ("duplicate_customer_tax", "CRM'de boş olmayan aynı vergi numarasına sahip aktif müşteri kartlarını adları ve bağlı aktif kişileriyle göster.", None, None),
        ("customers_without_contacts", "CRM'de aktif irtibat kişisi bulunmayan aktif müşterileri son güncellemesi en eski olandan başlayarak göster.", None, None),
        ("contact_multiple_customers", "CRM'de birden fazla aktif müşteriyle bağlantısı olan aktif kişileri ilişki yolu ve müşteri kimliğiyle göster; bunun hata olduğunu varsayma.", None, None),
        ("customer_geography", "CRM aktif müşterilerinin şehir yazımlarını normalleştirme adayıyla, ham kayıt sayısıyla ve bölgeyle göster; şehir-bölge uygunluğunu kanıt olmadan kesinleştirme.", None, None),
        ("publication_dates", "CRM aktif kitaplarında kayıt açılışı, ilk baskı ve son yayın tarihlerini ayrı göster; tarih sırası sinyallerini ve eksik temel alanları belirt.", None, None),
        ("catalog_additions", "1 Ekim 2025 dahil 1 Ekim 2026 hariç CRM'ye açılan aktif kitap kartlarını kayıt açılma ayı ve yayın evine göre say. Yayın tarihiyle karıştırma.", "2025-10-01", "2026-10-01"),
        ("editor_assignments", "CRM aktif kitaplarının editör, proje editörü, yayın yönetmeni ve sahip alanlarını ayrı göster; atanmayanlar dahil her rol ve kimlik için kitap sayısı ver.", None, None),
        ("work_due", "30 Eylül 2026 dahil 30 Ekim 2026 hariç aralıkta tahmini bitişi olan açık CRM kitap iş planlarını ve geçmiş terminli açık işleri göster; sorumlu ve aşama eksiklerini belirt.", "2026-09-30", "2026-10-30"),
        ("work_stage_history", "CRM'de açık kitap işlerinin aynı aşamada üç aydan uzun bekleyip beklemediğini araştır. Aşamaya giriş tarihi kanıtlanmıyorsa son güncellemeyi kullanma; mevcut işleri ve doğrulanamayan kısmı göster.", None, None),
        ("contract_expiry", "30 Eylül 2026 dahil 30 Mart 2027 hariç aralıkta kayıtlı bitiş adayı olan aktif CRM kitap sözleşmelerini kitap, taraf, hak, dil ve bölgeyle göster. Boş bitişleri ayrıca göster; revize/yenileme önceliğini veya satış yasağını varsayma.", "2026-09-30", "2027-03-30"),
        ("contract_overlap", "CRM'de aynı aktif kitabın tarih, hak, dil ve bölge kapsamı kesişen sözleşme adaylarını göster. Tarih veya kapsam eksikse kesin çakışma sayma.", None, None),
        ("contract_author_roles", "CRM'de aktif kitap sözleşmelerinin kişi ve firma taraflarını kitapla bağlı kişi yazarlardan ayrı göster; taraf rolünü ve hak kapsamını da ver, yazarın hak sahibi olduğunu varsayma.", None, None),
        ("open_author_actions", "30 Mart 2026 dahil 30 Eylül 2026 hariç dönemdeki yazar randevularına kayıt kimliğiyle bağlı ve hâlâ açık olan CRM görevlerini yazar, sorumlu ve terminle göster.", "2026-03-30", "2026-09-30"),
        ("appointments_with_actions", "30 Eylül 2026 dahil 14 Ekim 2026 hariç randevusu olan aktif yazarların önceki randevularından kimliğiyle bağlı açık görevlerini tarih sırasıyla hazırlık listesi olarak göster.", "2026-09-30", "2026-10-14"),
        ("publisher_completeness", "CRM yayın evlerine göre aktif kitap sayısını ve güncel ISBN, kişi-yazar bağı, ilk baskı, son yayın ve alt marka alanlarının doluluk yüzdelerini göster. Kitap listesindeki eksikleri de ekle.", None, None),
        ("publisher_history", "CRM aktif kitaplarının bugünkü ve önceki yayın evi alanlarını göster. Geçmiş yayın evi ilişkisinin tarih aralığı yoksa geçmiş sınıflandırmayı doğrulanmış sayma.", None, None),
        ("contract_revision_evidence", "CRM'de aktif kitaplara bağlı aktif sözleşmelerin Ana Sözleşme Id metnini göster: kendi kimliğine, başka aktif sözleşmeye ve aktif karşılığı bulunamayan kimliğe gidenleri ayır. Başlangıç, bitiş, revize, yenileme, fesih ve ek protokol tarihlerini ve ek protokol bayraklarını ayrı göster. Hukuki öncelik varsayma, PDF logunu değişiklik geçmişi sayma.", None, None),
    ]
    return [dict(id=f"CR{i:03d}",report=r,question=q,start=a,end=b) for i,(r,q,a,b) in enumerate(data,1)]


def identity(v): return str(v).strip().lower() if v is not None else None
def text(v): return str(v).strip() if v is not None and str(v).strip() else None
def normalized(v):
    folded=str(v or "").translate(str.maketrans({"I":"ı","İ":"i"})).casefold()
    return "".join(x for x in unicodedata.normalize("NFKC",folded) if x.isalnum())
def localday(v):
    if not v:return None
    d=v if isinstance(v,datetime) else datetime.fromisoformat(str(v).replace("Z","+00:00"))
    return (d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d).astimezone(ZoneInfo("Europe/Istanbul")).date()
def in_window(v,c):return bool(v) and (not c["start"] or c["start"]<=str(localday(v))<c["end"])
def pack(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,default=str)


class Oracle:
    """Fixed independently authored SQL against source DB, not application output."""
    def __init__(self,conn): self.conn=conn;self.sql=[];self.cache={}
    def get(self,key,sql):
        if key not in self.cache:
            self.sql.append(sql);self.cache[key]=query(self.conn,sql)
        return self.cache[key]
    def books(self):
        sql="""SELECT K.new_kitapId book_id,K.new_stokkodu book_code,K.new_name book_name,K.new_isbn13 isbn,
 K.new_yazartext author_text,K.new_yayineviid publisher_id,P.new_name publisher,
 K.new_yayinciid subbrand_id,S.new_name subbrand,K.new_YayneviAltMarka alternate_subbrand_id,A.new_name alternate_subbrand,
 K.new_ilkyayintarihi first_print_date,K.new_sonyayintarihi last_publication_date,K.new_baskisayisi edition_count,K.new_baskitarihi last_print_date,
 K.CreatedOn created_at,K.ModifiedOn updated_at,K.new_Editor editor_id,K.new_projeeditoru project_editor_id,
 K.new_yayinyonetmeni publishing_director_id,K.OwnerId owner_id,K.new_oncekiyayineviid previous_publisher_id,
 K.new_KitapProjesi book_project_id,K.new_projekarti project_card_id
 FROM dbo.new_kitapBase K LEFT JOIN dbo.new_markaBase P ON P.new_markaId=K.new_yayineviid AND P.statecode=0 AND P.statuscode=1
 LEFT JOIN dbo.new_markaBase S ON S.new_markaId=K.new_yayinciid AND S.statecode=0 AND S.statuscode=1
 LEFT JOIN dbo.new_yaynevialtmarkaBase A ON A.new_yaynevialtmarkaId=K.new_YayneviAltMarka AND A.statecode=0
 WHERE K.statecode=0 AND K.statuscode=1"""
        return unique(self.get("books",sql),"book_id")
    def people(self):
        return unique(self.get("people","SELECT ContactId person_id,FullName person_name,new_yazarmi is_author,EMailAddress1 email,Telephone1 phone,MobilePhone mobile,CreatedOn created_at,ModifiedOn updated_at,ParentCustomerId parent_id,ParentCustomerIdType parent_type FROM dbo.ContactBase WHERE statecode=0 AND statuscode=1"),"person_id")
    def authors(self):
        # The source's Yazar role is resolved by label, never by a guessed GUID.
        rows=self.get("authors","""SELECT DISTINCT E.new_Kitap book_id,E.new_Katilimsaglayan person_id
 FROM dbo.new_eserkatilimBase E JOIN dbo.new_katilimcitipiBase R ON R.new_katilimcitipiId=E.new_katilimciTipi AND R.statecode=0
 JOIN dbo.ContactBase C ON C.ContactId=E.new_Katilimsaglayan AND C.statecode=0 AND C.statuscode=1
 JOIN dbo.new_kitapBase B ON B.new_kitapId=E.new_Kitap AND B.statecode=0 AND B.statuscode=1
 WHERE E.statecode=0 AND R.new_name=N'Yazar'""")
        result=defaultdict(set)
        for r in rows:result[identity(r["book_id"])].add(identity(r["person_id"]))
        return result
    def customers(self):
        rows=self.get("customers","""SELECT C.AccountId customer_id,C.Name customer_name,C.new_VergiNo tax_number,
 C.TerritoryId territory_id,T.Name territory,C.PrimaryContactId primary_contact_id,C.CreatedOn created_at,C.ModifiedOn updated_at,
 A.City city,A.StateOrProvince region,A.Country country FROM dbo.AccountBase C
 LEFT JOIN dbo.CustomerAddressBase A ON A.ParentId=C.AccountId AND A.ObjectTypeCode=1 AND A.AddressNumber=1
 LEFT JOIN dbo.TerritoryBase T ON T.TerritoryId=C.TerritoryId WHERE C.statecode=0 AND C.statuscode=100000000""")
        return unique(rows,"customer_id")
    def customer_relations(self):
        return self.get("customer_relations","""SELECT C.ContactId person_id,A.AccountId customer_id,'Contact.ParentCustomerId' relationship_type
 FROM dbo.ContactBase C JOIN dbo.AccountBase A ON A.AccountId=C.ParentCustomerId AND C.ParentCustomerIdType=1
 WHERE C.statecode=0 AND C.statuscode=1 AND A.statecode=0 AND A.statuscode=100000000
 UNION SELECT C.ContactId,A.AccountId,'Account.PrimaryContactId' FROM dbo.ContactBase C JOIN dbo.AccountBase A ON A.PrimaryContactId=C.ContactId
 WHERE C.statecode=0 AND C.statuscode=1 AND A.statecode=0 AND A.statuscode=100000000
 UNION SELECT C.ContactId,A.AccountId,'new_contact_account' FROM dbo.new_contact_accountBase N
 JOIN dbo.ContactBase C ON C.ContactId=N.contactid JOIN dbo.AccountBase A ON A.AccountId=N.accountid
 WHERE C.statecode=0 AND C.statuscode=1 AND A.statecode=0 AND A.statuscode=100000000""")


def unique(rows,column):
    result={}
    for r in rows:
        k=identity(r[column])
        if k in result:raise ValueError("Independent source query multiplied identity "+column)
        result[k]=r
    return result


def expected_books(o,c,asof):
    report=c["report"];books=o.books();people=o.people();links=o.authors()
    selected=[b for b in books.values() if not c["start"] or in_window(b["created_at"],c)]
    pubs=defaultdict(list)
    for b in selected:pubs[identity(b["publisher_id"])].append(b)
    def detail(b):
        ids=sorted(links[identity(b["book_id"])]);
        return dict(b,author_count=len(ids),author_ids=pack(ids),author_names=pack([people[i]["person_name"] for i in ids]))
    def missing(b):
        names=[f for f in ("isbn","book_code","publisher","first_print_date","last_publication_date","subbrand") if not text(b[f])]
        return names+([] if links[identity(b["book_id"])] else ["author_link"])
    rows=[];boundaries=[]
    if report in {"book_quality","publisher_completeness"}:
        for pub,group in pubs.items():
            count=Counter(f for b in group for f in missing(b))
            fields=("isbn","book_code","publisher","author_link","first_print_date","last_publication_date","subbrand")
            rows.append(dict(record_type="publisher_summary",publisher_id=pub,publisher=group[0]["publisher"],book_count=len(group),multiple_core_missing_book_count=sum(len(set(missing(b)) & {"isbn","book_code","publisher"})>1 for b in group),**{"missing_"+f:count[f] for f in fields},**{"filled_pct_"+f:100*(len(group)-count[f])/len(group) for f in fields}))
        for b in selected:
            fields=missing(b);core=[f for f in fields if f in {"isbn","book_code","publisher"}]
            if fields:rows.append(dict(record_type="book_detail",**detail(b),missing_fields=pack(fields),missing_count=len(fields),missing_core_fields=pack(core),core_missing_count=len(core),record_age_days=(asof-localday(b["created_at"])).days if b["created_at"] else None))
    elif report in {"duplicate_isbn","duplicate_book_code","duplicate_title","title_variants"}:
        field={"duplicate_isbn":"isbn","duplicate_book_code":"book_code","duplicate_title":"book_name","title_variants":"book_name"}[report]
        groups=defaultdict(list)
        for b in selected:
            if text(b[field]):groups[normalized(b[field]) if report=="title_variants" else text(b[field]).casefold()].append(b)
        for key,group in groups.items():
            if len(group)<2 or report=="title_variants" and len({b[field] for b in group})<2:continue
            rows.extend(dict(record_type="candidate",**detail(b),matching_field=field,matching_value=key,candidate_count=len(group),decision="İncelenecek aday; baskı/eser/kişi kimliği otomatik birleştirilmedi") for b in group)
    elif report in {"author_link_gaps","multi_author_books","author_text_mismatch"}:
        chosen=[]
        for b in selected:
            d=detail(b);names=[people[i]["person_name"] for i in sorted(links[identity(b["book_id"])])]
            if report=="author_link_gaps":match=bool(text(b["author_text"])) and not names
            elif report=="multi_author_books":match=len(names)>1
            else:
                if not names:continue
                if len(names)==1 and text(b["author_text"])==names[0]:continue
                tokens={normalized(t) for t in re.split(r"[;,/]|\s+ve\s+",text(b["author_text"]) or "",flags=re.I) if text(t)}
                if len(names)>1 and tokens=={normalized(n) for n in names}:continue
                match=True;d["comparison"]="Yazım farkı adayı" if len(names)==1 and normalized(b["author_text"])==normalized(names[0]) else "Künye/kişi farkı; müstear veya çoklu yazarlık ayrıca incelenmeli"
            if match:chosen.append(d)
        rows.extend(dict(record_type="book_detail",**d) for d in chosen)
        tally=Counter((identity(d["publisher_id"]),d["publisher"]) for d in chosen)
        rows.extend(dict(record_type="publisher_summary",publisher_id=k[0],publisher=k[1],book_count=n) for k,n in tally.items())
    elif report in {"duplicate_authors","authors_without_books","publisher_author_coverage","author_contact_coverage"}:
        peoplebooks=defaultdict(set)
        for bid,pids in links.items():
            for pid in pids:peoplebooks[pid].add(bid)
        flagged={i:p for i,p in people.items() if p["is_author"]}
        counts=Counter((text(p["person_name"]) or "").casefold() for p in flagged.values())
        for pid,p in flagged.items():
            if report=="publisher_author_coverage":continue
            if report=="duplicate_authors" and (not text(p["person_name"]) or counts[text(p["person_name"]).casefold()]<2):continue
            if report=="authors_without_books" and peoplebooks[pid]:continue
            bids=sorted(peoplebooks[pid]);ps={identity(books[i]["publisher_id"]) for i in bids}
            rows.append(dict(record_type="person_detail",person_id=p["person_id"],person_name=p["person_name"],created_at=p["created_at"],updated_at=p["updated_at"],book_count=len(bids),books=pack([dict(book_id=i,book_name=books[i]["book_name"]) for i in bids]),publisher_ids=pack(sorted(ps,key=str)),has_email=bool(text(p["email"])),has_phone=bool(text(p["phone"]) or text(p["mobile"]))))
        if report in {"publisher_author_coverage","author_contact_coverage"}:
            sets={pub:set().union(*(links[identity(b["book_id"])] for b in group)) for pub,group in pubs.items()}
            if report=="author_contact_coverage":sets={pub:ids & set(flagged) for pub,ids in sets.items()}
            for pub,group in pubs.items():
                ids=sets[pub]
                rows.append(dict(record_type="publisher_summary",publisher_id=pub,publisher=group[0]["publisher"],book_count=len(group),author_count=len(ids),contact_field_present_count=sum(bool(text(people[i]["email"]) or text(people[i]["phone"]) or text(people[i]["mobile"])) for i in ids),shared_author_ids=pack(sorted(i for i in ids if sum(i in x for x in sets.values())>1))))
    elif report=="subbrand_consistency":
        rows=[dict(record_type="book_detail",**detail(b),finding="Alt marka atanmış, aktif ana yayıncı çözülemedi") for b in selected if (b["subbrand_id"] or b["alternate_subbrand_id"]) and not b["publisher"]]
        boundaries.append("unproven_subbrand_parent")
    elif report=="catalog_additions":
        counts=Counter((str(localday(b["created_at"]))[:7],identity(b["publisher_id"]),b["publisher"]) for b in selected if b["created_at"])
        rows=[dict(record_type="month_summary",created_month=k[0],publisher_id=k[1],publisher=k[2],book_count=n) for k,n in counts.items()]
    elif report in {"publication_dates","publisher_history"}:
        for b in selected:rows.append(dict(record_type="book_detail",**detail(b),missing_fields=pack(missing(b)),created_after_first_print=bool(b["created_at"] and b["first_print_date"] and localday(b["created_at"])>localday(b["first_print_date"])),last_publication_before_first_print=bool(b["last_publication_date"] and b["first_print_date"] and localday(b["last_publication_date"])<localday(b["first_print_date"]))))
        if report=="publisher_history":boundaries.append("unproven_publisher_validity_history")
    elif report=="editor_assignments":
        users=unique(o.get("users","SELECT SystemUserId user_id,FullName user_name,IsDisabled is_disabled FROM dbo.SystemUserBase"),"user_id");counts=Counter()
        for b in selected:
            for role in ("editor_id","project_editor_id","publishing_director_id","owner_id"):
                pid=identity(b[role]);u=users.get(pid,{})
                rows.append(dict(record_type="assignment_detail",book_id=b["book_id"],book_name=b["book_name"],role=role,person_id=pid,person_name=u.get("user_name"),user_disabled=u.get("is_disabled"),identity_status="Atanmamış" if not pid else "Kullanıcı" if u else "Takım/çözülemeyen sahip; kişi varsayılmadı"));counts[(role,pid,u.get("user_name"))]+=1
        rows.extend(dict(record_type="assignment_summary",role=k[0],person_id=k[1],person_name=k[2],book_count=n) for k,n in counts.items())
    elif report=="book_change_history":
        changed={bid:b for bid,b in books.items() if in_window(b["updated_at"],c)}
        rows=[dict(record_type="modified_book",**detail(b)) for b in changed.values()]
        history=o.get("history","SELECT new_kitapgecmisiId history_id,new_kitapid book_id,CreatedOn recorded_at,new_baskisayisi edition_count,new_kdvdahilfiyat vat_inclusive_price FROM dbo.new_kitapgecmisiBase WHERE statecode=0")
        rows.extend(dict(record_type="history_snapshot",**r) for r in history if identity(r["book_id"]) in changed and in_window(r["recorded_at"],c))
        boundaries.append("general_old_new_history_not_verified")
    else:raise ValueError("No independent book oracle for "+report)
    return rows,boundaries


def expected_customers(o,c):
    customers=o.customers();people=o.people();rels=o.customer_relations();byc=defaultdict(set);byp=defaultdict(set)
    for r in rels:byc[identity(r["customer_id"])].add(identity(r["person_id"]));byp[identity(r["person_id"])].add(identity(r["customer_id"]))
    rows=[];bounds=[]
    if c["report"]=="contact_multiple_customers":
        for r in rels:
            pid,cid=identity(r["person_id"]),identity(r["customer_id"])
            if len(byp[pid])>1:rows.append(dict(record_type="relationship",person_id=pid,person_name=people[pid]["person_name"],customer_id=cid,customer_name=customers[cid]["customer_name"],relationship_type=r["relationship_type"],customer_count=len(byp[pid]),decision="Kaynakta ilişki var; hata olduğu çıkarılmadı"))
    elif c["report"]=="customer_geography":
        groups=Counter((text(r["city"]),normalized(r["city"]),text(r["region"]),identity(r["territory_id"])) for r in customers.values());totals=Counter(normalized(r["city"]) for r in customers.values())
        rows=[dict(record_type="city_distribution",raw_city=k[0],normalized_city=k[1],region=k[2],territory_id=k[3],record_count=n,normalized_city_total=totals[k[1]]) for k,n in groups.items()];bounds.append("unproven_city_region_reference")
    else:
        tax=Counter(text(r["tax_number"]) for r in customers.values() if text(r["tax_number"]))
        for cid,r in customers.items():
            if c["report"]=="customers_without_contacts" and byc[cid]:continue
            if c["report"]=="duplicate_customer_tax" and (not text(r["tax_number"]) or tax[text(r["tax_number"])]<2):continue
            rows.append(dict(record_type="customer_detail",**r,active_contact_count=len(byc[cid]),contacts=pack([dict(person_id=pid,person_name=people[pid]["person_name"]) for pid in sorted(byc[cid])])))
    return rows,bounds


def expected_work(o,c,asof):
    books=o.books()
    works=o.get("works","""SELECT W.new_isplaniId work_id,W.new_planadi work_name,W.new_projeid project_id,W.OwnerId owner_id,
 W.new_projeasamasiid stage_id,W.new_tahminibitistarihi due_date,W.new_gercekbitistarihi actual_end,
 W.new_isEmriDurumu work_state,W.new_isplaniiptal cancelled,W.CreatedOn created_at,W.ModifiedOn updated_at,
 P.new_name project_name,S.new_name stage_name FROM dbo.new_isplaniBase W
 JOIN dbo.new_projeBase P ON P.new_projeId=W.new_projeid AND P.statecode=0
 LEFT JOIN dbo.new_projeasamalariBase S ON S.new_projeasamalariId=W.new_projeasamasiid AND S.statecode=0
 WHERE W.statecode=0 AND COALESCE(W.new_isplaniiptal,0)=0 AND (W.new_isEmriDurumu IS NULL OR W.new_isEmriDurumu<>3) AND W.new_gercekbitistarihi IS NULL""")
    br=o.get("projectbooks","""SELECT new_projeid project_id,new_kitapid book_id FROM dbo.new_new_proje_new_kitapBase
 UNION SELECT new_KitapProjesi,new_kitapId FROM dbo.new_kitapBase WHERE statecode=0 AND statuscode=1 AND new_KitapProjesi IS NOT NULL
 UNION SELECT new_projekarti,new_kitapId FROM dbo.new_kitapBase WHERE statecode=0 AND statuscode=1 AND new_projekarti IS NOT NULL""")
    byp=defaultdict(set)
    for r in br:
        if identity(r["book_id"]) in books:byp[identity(r["project_id"])].add(identity(r["book_id"]))
    # ID presence, not the human-readable label, defines whether an active stage exists.
    stages={identity(r["id"]) for r in o.get("stages","SELECT new_projeasamalariId id FROM dbo.new_projeasamalariBase WHERE statecode=0")}
    rows=[]
    for w in works:
        bids=byp[identity(w["project_id"])]
        if not bids:continue
        overdue=bool(w["due_date"] and localday(w["due_date"])<asof)
        if c["report"]=="work_due" and not (overdue or in_window(w["due_date"],c)):continue
        rows.append(dict(record_type="work_detail",**w,books=pack([dict(book_id=bid,book_name=books[bid]["book_name"]) for bid in sorted(bids)]),overdue=overdue,missing_owner=not bool(w["owner_id"]),missing_stage=identity(w["stage_id"]) not in stages))
    return rows,["stage_entry_history_not_verified"] if c["report"]=="work_stage_history" else []


def expected_activities(o,c):
    people={i:r for i,r in o.people().items() if r["is_author"]}
    ap=o.get("appointments","SELECT ActivityId activity_id,StateCode state_code,Subject subject,ScheduledStart scheduled_start,ScheduledEnd due_date,OwnerId owner_id,RegardingObjectId regarding_id,RegardingObjectTypeCode regarding_type FROM dbo.ActivityPointerBase WHERE ActivityTypeCode=4201 AND StateCode<>2")
    appointments=unique(ap,"activity_id");parties=defaultdict(set)
    for r in o.get("meetingpeople","SELECT DISTINCT ActivityId activity_id,PartyId person_id FROM dbo.ActivityPartyBase WHERE PartyObjectTypeCode=2 AND COALESCE(IsPartyDeleted,0)=0"):
        if identity(r["activity_id"]) in appointments and identity(r["person_id"]) in people:parties[identity(r["activity_id"])].add(identity(r["person_id"]))
    for aid,a in appointments.items():
        if a["regarding_type"]==2 and identity(a["regarding_id"]) in people:parties[aid].add(identity(a["regarding_id"]))
    tasks=o.get("meetingtasks","""SELECT A.ActivityId task_id,A.Subject task_subject,A.OwnerId owner_id,A.ScheduledEnd due_date,T.new_randevuid meeting_id
 FROM dbo.ActivityPointerBase A JOIN dbo.TaskBase T ON T.ActivityId=A.ActivityId
 WHERE A.ActivityTypeCode=4212 AND A.StateCode=0 AND COALESCE(T.new_iptalmi,0)=0 AND T.new_randevuid IS NOT NULL""")
    byperson=defaultdict(list)
    for t in tasks:
        mid=identity(t["meeting_id"])
        if mid in appointments:
            for pid in parties[mid]:byperson[pid].append(t)
    rows=[]
    if c["report"]=="open_author_actions":
        for pid,ts in byperson.items():
            for t in ts:
                mid=identity(t["meeting_id"]);m=appointments[mid]
                if in_window(m["scheduled_start"],c):rows.append(dict(record_type="open_action",person_id=pid,person_name=people[pid]["person_name"],meeting_id=mid,meeting_start=m["scheduled_start"],task_id=identity(t["task_id"]),task_subject=t["task_subject"],owner_id=t["owner_id"],due_date=t["due_date"],same_task_reference_count=1))
    else:
        for aid,a in appointments.items():
            if a["state_code"] not in (0,3) or not in_window(a["scheduled_start"],c):continue
            for pid in parties[aid]:
                for t in byperson[pid]:
                    mid=identity(t["meeting_id"]);m=appointments[mid]
                    if not m["scheduled_start"] or not a["scheduled_start"] or m["scheduled_start"]>=a["scheduled_start"]:continue
                    rows.append(dict(record_type="appointment_preparation",person_id=pid,person_name=people[pid]["person_name"],appointment_id=aid,appointment_start=a["scheduled_start"],appointment_subject=a["subject"],prior_meeting_id=mid,prior_meeting_start=m["scheduled_start"],task_id=identity(t["task_id"]),task_subject=t["task_subject"],owner_id=t["owner_id"],due_date=t["due_date"]))
    return rows,[]


def expected_contracts(o,c):
    books=o.books();people=o.people();authorlinks=o.authors()
    contracts=unique(o.get("contracts","SELECT new_sozlesmeId contract_id,new_name contract_number,new_SozlesmeBaslangicTarihi start_date,new_SozlesmeBitisTarihi end_date,new_revizebitistarihi revised_end_date,new_yenilemebaslangictarihi renewal_start_date,new_yenilemebitistarihi renewal_end_date,new_fesihtarihi termination_date,new_suresizsozlesme indefinite_flag FROM dbo.new_sozlesmeBase WHERE statecode=0"),"contract_id")
    revisions={}
    if c["report"]=="contract_revision_evidence":
        # SQL-side identity classification is independent of the application's
        # UUID parser/dictionary lookup. Never infer precedence from this link.
        revisions=unique(o.get("revisions","""SELECT C.new_sozlesmeId contract_id,C.new_anasozlesmeid parent_contract_text,
 C.new_ekprotokoltarihi protocol_date,C.new_ekprotokolbitist protocol_end_date,C.new_EkProtokolyeni is_addendum,C.new_ekprotokolsurelimi addendum_time_limited,
 CONVERT(varchar(36),TRY_CONVERT(uniqueidentifier,NULLIF(LTRIM(RTRIM(C.new_anasozlesmeid)),''))) parent_contract_id,
 CASE WHEN NULLIF(LTRIM(RTRIM(C.new_anasozlesmeid)),'') IS NULL THEN 'NOT_RECORDED'
 WHEN TRY_CONVERT(uniqueidentifier,C.new_anasozlesmeid) IS NULL THEN 'INVALID_UUID_TEXT'
 WHEN TRY_CONVERT(uniqueidentifier,C.new_anasozlesmeid)=C.new_sozlesmeId THEN 'SELF_REFERENCE'
 WHEN P.new_sozlesmeId IS NOT NULL THEN 'OTHER_ACTIVE_RECORD' ELSE 'ACTIVE_PARENT_NOT_FOUND' END parent_reference_status,
 P.new_name parent_contract_number FROM dbo.new_sozlesmeBase C LEFT JOIN dbo.new_sozlesmeBase P
 ON P.new_sozlesmeId=TRY_CONVERT(uniqueidentifier,C.new_anasozlesmeid) AND P.statecode=0 WHERE C.statecode=0"""),"contract_id")
        for r in revisions.values():r["parent_match_basis"]="UUID metin eşitliği; yayımlı lookup/ebeveyn önceliği değildir"
    links=o.get("contractbooks","SELECT DISTINCT L.new_sozlesmeid contract_id,L.new_kitapid book_id FROM dbo.new_new_sozlesme_new_kitapBase L JOIN dbo.new_sozlesmeBase C ON C.new_sozlesmeId=L.new_sozlesmeid AND C.statecode=0 JOIN dbo.new_kitapBase B ON B.new_kitapId=L.new_kitapid AND B.statecode=0 AND B.statuscode=1")
    bybook=defaultdict(set)
    for r in links:bybook[identity(r["book_id"])].add(identity(r["contract_id"]))
    scopes={}
    for name,relation,foreign,target,key in [("rights","new_new_hak_new_sozlesmeBase","new_hakid","new_hakBase","new_hakId"),("languages","new_new_sozlesme_new_dilBase","new_dilid","new_dilBase","new_dilId"),("regions","new_new_sozlesme_new_blgeBase","new_blgeid","new_blgeBase","new_blgeId"),("countries","new_new_sozlesme_new_ulkeBase","new_ulkeid","new_ulkeBase","new_ulkeId")]:
        rows=o.get("scope_"+name,f"SELECT DISTINCT L.new_sozlesmeid contract_id,V.{key} scope_id,V.new_name scope_name FROM dbo.{relation} L JOIN dbo.{target} V ON V.{key}=L.{foreign} AND V.statecode=0")
        scopes[name]=defaultdict(set)
        for r in rows:scopes[name][identity(r["contract_id"])].add((identity(r["scope_id"]),r["scope_name"]))
    parties=defaultdict(list)
    for r in o.get("parties","""SELECT P.new_sozlesmetarafiId party_id,P.new_sozlesmeid contract_id,P.new_kisi person_id,P.new_Firma account_id,P.new_TarafTipi party_type_id,
 C.FullName person_name,A.Name account_name,T.new_name party_type FROM dbo.new_sozlesmetarafiBase P
 LEFT JOIN dbo.ContactBase C ON C.ContactId=P.new_kisi AND C.statecode=0 AND C.statuscode=1
 LEFT JOIN dbo.AccountBase A ON A.AccountId=P.new_Firma AND A.statecode=0
 LEFT JOIN dbo.new_sozlesmetaraftipiBase T ON T.new_sozlesmetaraftipiId=P.new_TarafTipi AND T.statecode=0
 WHERE P.statecode=0 AND (P.new_kisi IS NULL OR C.ContactId IS NOT NULL) AND (P.new_Firma IS NULL OR A.AccountId IS NOT NULL)"""):
        parties[identity(r["contract_id"])].append(r)
    rows=[];bounds=["scope_interpretation_unverified"] if c["report"]=="contract_overlap" else ["contract_revision_priority_unverified"] if c["report"]=="contract_revision_evidence" else []
    for bid,ids in bybook.items():
        if c["report"]=="contract_overlap":
            ordered=sorted(ids)
            for i,cid in enumerate(ordered):
                a=contracts[cid]
                for zid in ordered[i+1:]:
                    z=contracts[zid]
                    known=all(a[f] and z[f] for f in ("start_date","end_date")) and all(scopes[n][cid] and scopes[n][zid] for n in ("rights","languages")) and bool(scopes["regions"][cid] and scopes["regions"][zid] or scopes["countries"][cid] and scopes["countries"][zid])
                    intersections={n:scopes[n][cid] & scopes[n][zid] for n in scopes}
                    overlaps=known and localday(a["start_date"])<=localday(z["end_date"]) and localday(z["start_date"])<=localday(a["end_date"])
                    if known and not (overlaps and intersections["rights"] and intersections["languages"] and (intersections["regions"] or intersections["countries"])):continue
                    rows.append(dict(record_type="contract_pair",book_id=bid,book_name=books[bid]["book_name"],contract_id=cid,other_contract_id=zid,scope_status="Tarih ve kayıtlı hak/dil/bölge kesişim adayı" if known else "DOĞRULANAMADI: tarih veya kapsam eksik",scope_intersections=pack({n:sorted(v) for n,v in intersections.items()})))
                    if not known:bounds.append("missing_contract_scope_or_dates")
        else:
            for cid in ids:
                d=contracts[cid]
                if c["report"]=="contract_expiry" and d["end_date"] and not any(in_window(d[f],c) for f in ("end_date","revised_end_date","renewal_end_date","termination_date")):continue
                data=dict(d);data.update(revisions.get(cid,{}))
                rows.append(dict(record_type="contract_detail",book_id=bid,book_name=books[bid]["book_name"],**data,**{n:pack(sorted(scopes[n][cid])) for n in scopes},parties=pack(parties[cid]),author_people=pack([dict(person_id=i,person_name=people[i]["person_name"]) for i in sorted(authorlinks[bid])]),end_date_status="Bitiş tarihi mevcut" if d["end_date"] else "Bitiş tarihi bilinmiyor; süresiz varsayılmadı"))
    relevant={identity(r.get("contract_id")) for r in rows}|{identity(r.get("other_contract_id")) for r in rows}
    if any(d["revised_end_date"] or d["renewal_end_date"] or d["termination_date"] for cid,d in contracts.items() if cid in relevant):bounds.append("unverified_contract_date_precedence")
    return rows,sorted(set(bounds))


def reference(conn,c,asof):
    oracle=Oracle(conn)
    if c["report"] in {"duplicate_customer_tax","customers_without_contacts","contact_multiple_customers","customer_geography"}:rows,bounds=expected_customers(oracle,c)
    elif c["report"].startswith("contract_"):rows,bounds=expected_contracts(oracle,c)
    elif c["report"] in {"work_due","work_stage_history"}:rows,bounds=expected_work(oracle,c,asof)
    elif c["report"] in {"open_author_actions","appointments_with_actions"}:rows,bounds=expected_activities(oracle,c)
    else:rows,bounds=expected_books(oracle,c,asof)
    if not rows:rows=[dict(record_type="summary",record_count=0,report=c["report"])]
    columns=sorted({k for r in rows for k in r})
    return dict(records=[{k:r.get(k) for k in columns} for r in rows],columns=columns,boundaries=bounds,queries=oracle.sql)


JSON_COLUMNS={"author_ids","author_names","missing_fields","missing_core_fields","books","publisher_ids","shared_author_ids","contacts","rights","languages","regions","countries","parties","author_people","scope_intersections"}
UUID_PATTERN=re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def canonical(value,column=None):
    if value is None:return None
    if isinstance(value,(datetime,date)):return value.isoformat()
    if isinstance(value,UUID):return str(value).lower()
    if isinstance(value,Decimal):return float(value)
    if isinstance(value,str) and UUID_PATTERN.fullmatch(value):return value.lower()
    if column in JSON_COLUMNS and isinstance(value,str):value=json.loads(value)
    if column in {"rights","languages","regions","countries"} and isinstance(value,list):
        # Scope pairs are positional [identity,label]; only the set of pairs is
        # unordered. Sorting within a pair would hide swapped identity/labels.
        return sorted(([canonical(part) for part in pair] for pair in value),key=lambda x:json.dumps(x,sort_keys=True,default=str))
    if isinstance(value,list):return sorted((canonical(v) for v in value),key=lambda x:json.dumps(x,sort_keys=True,default=str))
    if isinstance(value,dict):return {k:canonical(v,k) for k,v in value.items()}
    return value


def row_identity(row):
    kind=row["record_type"]
    keys={
        "publisher_summary":["publisher_id"],"book_detail":["book_id"],"candidate":["book_id"],"person_detail":["person_id"],
        "modified_book":["book_id"],"history_snapshot":["history_id"],"customer_detail":["customer_id"],
        "relationship":["person_id","customer_id","relationship_type"],"city_distribution":["raw_city","normalized_city","region","territory_id"],
        "month_summary":["created_month","publisher_id"],"assignment_detail":["book_id","role"],"assignment_summary":["role","person_id"],
        "work_detail":["work_id"],"contract_detail":["book_id","contract_id"],"contract_pair":["book_id","contract_id","other_contract_id"],
        "open_action":["person_id","task_id","meeting_id"],"appointment_preparation":["appointment_id","person_id","task_id"],"summary":["report"],
    }[kind]
    return tuple([kind]+[canonical(row.get(k),k) for k in keys])


def compare_rows(expected,actual,columns):
    problems=[]
    if len(expected)!=len(actual):problems.append(f"Row count {len(actual)} != {len(expected)}")
    def index(rows):
        out={}
        for r in rows:
            key=row_identity(r)
            if key in out:raise ValueError("Duplicate full-result row identity: "+str(key))
            out[key]=r
        return out
    try:
        wanted,received=index(expected),index(actual)
        if set(wanted)!=set(received):problems.append("Row identity set differs")
        for key in set(wanted)&set(received):
            a,b=wanted[key],received[key]
            if set(b)!=set(columns):problems.append("Record column set differs")
            for col in columns:
                left,right=canonical(a.get(col),col),canonical(b.get(col),col)
                if isinstance(left,(float,int)) and not isinstance(left,bool) and isinstance(right,(float,int)) and not isinstance(right,bool):
                    tolerance=Decimal("0.000001") if col.startswith("filled_pct_") else Decimal("0.01") if col=="vat_inclusive_price" else Decimal(0)
                    if abs(Decimal(str(left))-Decimal(str(right)))>tolerance:problems.append("Numeric mismatch: "+col)
                elif type(left) is not type(right) or left!=right:problems.append("Value mismatch: "+col)
                if len(problems)>=30:return problems
    except Exception as exc:problems.append(type(exc).__name__+": "+str(exc)[:200])
    return problems


def compare(c,answer,whole,ref,expected_hash):
    errors=[];state=answer.get("semantic",{})
    if state.get("engine")!="finance_contract_v1" or state.get("engineCodeHash")!=expected_hash:errors.append("Engine route/code hash mismatch")
    rootplan=state.get("plan",{});plan=rootplan.get("crm_report") or {};dataset=whole
    # A single report may be wrapped in the application's section container.
    # Read that same stored execution, never issue another ask to unwrap it.
    if rootplan.get("sections"):
        sections=whole.get("sections") or []
        if len(rootplan["sections"])!=1 or len(sections)!=1:
            errors.append("Unexpected extra report sections outside independently specified scope")
        else:
            plan=rootplan["sections"][0].get("crm_report") or {};dataset=sections[0]
            if answer.get("sections")!=whole.get("sections"):errors.append("Preview section datasets differ from stored execution")
            expected_section_status="PARTIAL" if ref["boundaries"] else "COMPLETE"
            if dataset.get("status")!=expected_section_status:errors.append("Section completeness status mismatch")
    if plan.get("report")!=c["report"]:errors.append("Wrong report capability")
    if plan.get("start")!=c["start"] or plan.get("end")!=c["end"] or plan.get("as_of")!=c["as_of"] or plan.get("limit") is not None:errors.append("Wrong time/limit coverage")
    expected_type="PARTIAL_ANSWER" if ref["boundaries"] else "TEXT_TO_SQL"
    if answer.get("type")!=expected_type:errors.append("Expected "+expected_type+", received "+str(answer.get("type")))
    gaps=whole.get("gaps") or answer.get("gaps") or state.get("gaps") or []
    if ref["boundaries"] and not gaps:errors.append("Required explicit gap flags missing")
    if not answer.get("resultId") or whole.get("id")!=answer["resultId"]:errors.append("Stored execution identity mismatch")
    overview=whole.get("records");rows=dataset.get("records")
    if not isinstance(rows,list) or not isinstance(overview,list):return errors+["Full stored records missing"]
    if whole.get("truncated") is not False:errors.append("Truncation flag not false")
    if whole.get("totalRows")!=len(overview) or answer.get("rowCount")!=len(overview):errors.append("Full-result row metadata mismatch")
    if dataset.get("totalRows")!=len(rows) or dataset.get("truncated") is not False:errors.append("Dataset row count/truncation mismatch")
    if dataset is not whole and overview!=[{"section":dataset.get("title"),"status":dataset.get("status"),"row_count":len(rows)}]:errors.append("Section overview differs from stored dataset")
    if {x.get("name") for x in dataset.get("columns",[])}!=set(ref["columns"]):errors.append("Column identity mismatch")
    if answer.get("records",[])!=overview[:len(answer.get("records",[]))] or answer.get("shownRows")!=len(answer.get("records",[])):errors.append("Preview differs from full stored execution")
    errors.extend(compare_rows(ref["records"],rows,ref["columns"]))
    if c["report"]=="appointments_with_actions":
        starts=[r.get("appointment_start") for r in rows if r.get("record_type")=="appointment_preparation"]
        if starts!=sorted(starts):errors.append("Requested appointment chronology not preserved")
    if c["report"]=="customers_without_contacts":
        updated=[str(r.get("updated_at") or "") for r in rows if r.get("record_type")=="customer_detail"]
        if updated!=sorted(updated):errors.append("Requested oldest-updated customer order not preserved")
    return errors[:40]


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--out",required=True);parser.add_argument("--only",default="");parser.add_argument("--base",default="http://127.0.0.1:8795");parser.add_argument("--as-of",default="2026-09-30");args=parser.parse_args()
    if sys.platform!="linux" or not ROOT.is_dir() or not Path("/proc").is_dir():raise SystemExit("Remote connected test server only; local execution prohibited")
    if not re.fullmatch(r"http://127\.0\.0\.1:\d+",args.base):raise SystemExit("Use the actual loopback test API")
    asof=date.fromisoformat(args.as_of)
    if datetime.now(ZoneInfo("Europe/Istanbul")).date()!=asof:raise SystemExit("Reference date differs from live planner date; review dates explicitly")
    os.umask(0o077);out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()):raise SystemExit("Use an empty evidence directory")
    lock=open("/tmp/finance-composable-live.lock","a")
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise SystemExit("Another finance acceptance run is active")
    selected=[c for c in cases() if not args.only or c["id"] in args.only.split(",")]
    if not selected:raise SystemExit("No selected cases")
    for c in selected:c["as_of"]=args.as_of
    before=manifest();expected_hash=hashlib.sha256(json.dumps({k.rsplit('/',1)[-1]:v for k,v in before.items() if '/finance_query/' in k},sort_keys=True).encode()).hexdigest()
    session=None;digest=None;conn=None;deleted=0;results=[];counts=Counter()
    def interrupt(signum,frame):raise KeyboardInterrupt(f"Signal {signum}")
    signal.signal(signal.SIGTERM,interrupt)
    try:
        env=environment("nanobase-semantic-bridge");login=environment("timas-login")
        session=sqlite3.connect(login.get("SESSION_DB","/var/lib/timas-login/sessions.sqlite"));token=secrets.token_urlsafe(32);digest=hashlib.sha256(token.encode()).hexdigest()
        session.execute("INSERT INTO sessions(token,username,expires) VALUES(?,?,?)",(digest,"timasai",time.time()+900));session.commit()
        headers={"Content-Type":"application/json","X-Semantic-Caller":env.get("SEMANTIC_CALLER_TOKEN",""),"Cookie":("__Secure-timas_session" if login.get("COOKIE_SECURE","1")!="0" else "timas_session")+"="+token}
        def call(path,body=None):
            req=urllib.request.Request(args.base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
            with urllib.request.urlopen(req,timeout=240) as response:return json.load(response)
        conn=connect("/data/nanobaseai/bi/secrets/crm-mssql-connection.json")
        for c in selected:
            item=dict(c,started=time.time());stop=False
            try:
                session.execute("UPDATE sessions SET expires=? WHERE token=?",(time.time()+900,digest));session.commit()
                REFERENCE_CONTEXT.clear();REFERENCE_CONTEXT.update(caseId=c["id"],source="crm",phase="before_api")
                ref=reference(conn,c,asof);item["reference"]=ref
                answer=call("/api/v1/ask",{"question":c["question"],"sampleSize":7});item["answer"]=answer
                whole=call("/api/v1/result/"+answer["resultId"]) if answer.get("resultId") else answer;item["fullResult"]=whole
                errors=compare(c,answer,whole,ref,expected_hash);item["errors"]=errors
                item["status"]="FAIL" if errors else "BOUNDARY_PASS" if ref["boundaries"] else "FULL_ANSWER_PASS"
                REFERENCE_CONTEXT["phase"]="after_api";after_ref=reference(conn,c,asof);item["referenceAfter"]=after_ref
                changed=ref["boundaries"]!=after_ref["boundaries"] or ref["columns"]!=after_ref["columns"] or bool(compare_rows(ref["records"],after_ref["records"],ref["columns"]))
                if changed:
                    item["referenceChanged"]=True
                    structural=[x for x in errors if not x.startswith(("Row count ","Row identity set differs","Numeric mismatch:","Value mismatch:"))]
                    item["status"]="FAIL" if structural else "UNVERIFIED"
            except Exception as exc:
                structural=[x for x in item.get("errors",[]) if not x.startswith(("Row count ","Row identity set differs","Numeric mismatch:","Value mismatch:"))]
                item["status"]="FAIL" if structural else "UNVERIFIED";item["error"]=type(exc).__name__+": "+str(exc)[:500]
                stop=isinstance(exc,TimeoutError) or isinstance(exc,urllib.error.URLError) and isinstance(exc.reason,TimeoutError)
            item["elapsedSeconds"]=round(time.time()-item["started"],2);save(out/(c["id"]+".json"),item)
            counts[item["status"]]+=1;results.append({k:item[k] for k in ("id","report","status","errors","error","elapsedSeconds") if k in item})
            print(json.dumps(results[-1],ensure_ascii=False),flush=True)
            if len(results)%10==0:print("BATCH",len(results),dict(counts),flush=True)
            if stop:print("STOP: request may still run; no duplicate workload",flush=True);break
    except BaseException as exc:
        counts["UNVERIFIED"]+=1;results.append(dict(id="ENVIRONMENT",status="UNVERIFIED",error=type(exc).__name__+": "+str(exc)[:400]))
    finally:
        if conn is not None:conn.close()
        if session is not None:
            try:
                if digest:deleted=session.execute("DELETE FROM sessions WHERE token=?",(digest,)).rowcount;session.commit()
            except Exception as exc:counts["UNVERIFIED"]+=1;results.append(dict(id="SESSION_CLEANUP",status="UNVERIFIED",error=str(exc)[:200]))
            finally:session.close()
        after=manifest()
        if before!=after:counts["UNVERIFIED"]+=1;results.append(dict(id="CODE_CHANGED",status="UNVERIFIED"))
        report=dict(asOf=args.as_of,api=args.base,source="connected real Timas_MSCRM",executionEnvironment="test server",planned=len(selected),completed=sum(r["id"].startswith("CR") for r in results),counts=dict(counts),results=results,sessionsDeleted=deleted,sourceWrites=0,codeBefore=before,codeAfter=after,codeStable=before==after,runnerSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),referenceRetries=REFERENCE_RETRIES,referenceRetryIsProductRecoveryEvidence=False,boundaryPassIsNumericAcceptance=False)
        save(out/"report.json",report);print("FINAL",dict(counts),"sessionsDeleted",deleted,flush=True)
        fcntl.flock(lock,fcntl.LOCK_UN);lock.close()
    return 1 if counts["FAIL"] or counts["UNVERIFIED"] or report["completed"]!=len(selected) else 0


if __name__=="__main__":raise SystemExit(main())
