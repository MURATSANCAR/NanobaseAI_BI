"""CRM kitap kümesi × Logo satışı.

CRM süreçtir, satış Logo'dadır: «7-9 yaş kitaplarının satışı», «masal kategorisi», «sözleşmesi bu yıl biten
kitaplar», «hedefini tutturan kitaplar» sorularında kitaplar CRM'de kayıtlı ilişki sözlüğüyle (relational_query)
seçilir, satış Logo'dan aynı ölçüyle hesaplanır. Bağ yalnız stok kodudur (Logo ITEMS.CODE = CRM stok kodu); ad
benzerliği kullanılmaz. Soruya özel hiçbir kalıp yok: küme, kırılım ve CRM sayısı modelin kurduğu kapalı ilişkisel
plandan gelir, aynı doğrulayıcılardan geçer.

Kümenin üç kullanımı:
- süzgeç: yalnız kümedeki kitapların satışı;
- kırılım (crm_attribute): kümenin stok kodu dışındaki düz kolonları (yaş grubu, kategori…); bir kitap birden çok
  değerdeyse satışı her değerde ayrı sayılır, değerlerin toplamı genel toplam değildir (not yazılır);
- CRM sayısı (crm_value, crm_value_2): stok kodu başına toplanmış CRM değeri (hedef, bekleyen adet…); satış
  satırının yanına konur, oran/fark/eşik hesabına girer. Satışı olmayan kümedeki kitap 0 satışla korunur.
"""
from decimal import Decimal

from .contracts import ContractError

#: CRM'de Logo stok kodunu taşıyan alanlar (varlık, alan). Hepsi canlı veriyle ITEMS.CODE ile ölçüldü; ürün kodu
#: (ProductNumber) 2026-10-05: bekleyen ürünlerin 8.260 kodundan 8.257'si Logo stok kartında.
CODE_FIELDS = {("book", "book_code"), ("sales_target", "stok_kodu"), ("crm_product", "urun_kimligi")}
#: CRM sayılarının birimi (varlık → sayı alanlarının birimi). Satış hedefi ve bekleyen ürün adettir: TL ölçüsüyle
#: oranlanmaz, farkı alınmaz (2026-10-05: «hedefin neresindeyiz» hedef adedini satış TL'sine bölmüştü).
UNITS = {"sales_target": "adet", "pending_item": "adet", "crm_order_line": "adet"}
#: CRM sayı kolonlarının sabit kimlikleri: model şemasında hesap operandı olarak sayılabilsinler diye.
VALUE_IDS = ("crm_value", "crm_value_2")
PLAIN = {"field", "label", "normalized_text"}
AGGREGATE = {"sum", "count_records", "count_distinct"}

CAPABILITY = (
    "crm_books: Logo satış ölçüsünü CRM'de seçilen kitaplarla sınırlar/kırar. relational_query ile aynı kapalı "
    "biçimdir (relationalCapabilities). select içinde id=book_code olan, op=field ve CRM stok kodu alanını "
    "(book.book_code, sales_target.stok_kodu ya da crm_product.urun_kimligi) gösteren bir kolon ZORUNLU. Kökü bağ tablosundan seç ve ileri "
    "ilişkilerle kitaba git (ör. yaş: root book_age_link → j1 book, j2 age_group; kategori: book_category_link; "
    "sözleşme: contract_book → book ve contract). Stok kodu dışındaki düz kolonlar (yaş grubu, kategori adı) "
    "dimensions içinde crm_attribute ile kırılım olur; kırılım istenmiyorsa yalnız book_code seç. Kitap başına CRM "
    "sayısı (hedef, bekleyen adet) için sum/count kolonunun id'si crm_value (ikincisi crm_value_2) olur ve group_by "
    "yalnız stok kodu alanıdır; bu sayı derived/having/order_by içinde ölçü gibi kullanılır (ör. satış/hedef oranı, "
    "satış−hedef farkı ≥ 0); crm_value metrics'e yazılmaz. Satış hedefi ve bekleyen ürün ADETtir: sold_quantity/net_quantity "
    "ile karşılaştırılır, TL ölçüsüyle oranlanmaz. Yeni çıkan/yeni yayımlanan kitap book.first_print_date (ilk baskı "
    "tarihi) aralığıdır. Ortak yazarlı kitap: participation→participation_role.name=Yazar süzgeciyle kişi sayısı "
    "katılımın kendi alanından sayılır (root participation.person_id, count_distinct; kişi kartına JOIN yok — pasif kişi kartı "
    "yazarlığı silmez) ve crm_value olur, having crm_value gte 2. Sayısız kümede group_by boş bırakılır. CRM sayısı varken kırılım yalnız book olabilir ya da hiç olmaz. Yalnız satış ailesi "
    "ölçüleri. Logo satışı kendi dönemiyle hesaplanır; CRM tarihleri (sözleşme bitişi, ilk baskı) CRM süzgecidir.")


def _ref_entity(ref, aliases):
    return aliases[ref["alias"]], ref["field"]


def validate(spec, question, today):
    """Kapalı ilişkisel planı doğrular ve kümenin kolon rollerini döndürür."""
    from .relational_plan import validate_relational_query, alias_entities
    if isinstance(spec, dict) and isinstance(spec.get("select"), list) and not any(
            isinstance(s, dict) and s.get("op") in AGGREGATE for s in spec["select"]):
        # Sayısız küme bir kitap kümesidir: model onu «stok koduna göre grupla» diye de yazar; aynı anlam tekilleştirmedir.
        spec = {**spec, "group_by": [], "distinct": True}
    elif isinstance(spec, dict) and isinstance(spec.get("select"), list):
        # Sayılı küme kitap başına toplanır: grup anahtarı her zaman seçilen stok kodu alanıdır.
        code = next((s.get("field") for s in spec["select"] if isinstance(s, dict) and s.get("id") == "book_code"), None)
        if isinstance(code, dict):
            spec = {**spec, "group_by": [code], "distinct": False}
    plan = validate_relational_query(spec, question, today)
    aliases = alias_entities(plan)
    codes = [s for s in plan["select"] if s["id"] == "book_code"]
    if len(codes) != 1 or codes[0]["op"] != "field" or _ref_entity(codes[0]["field"], aliases) not in CODE_FIELDS:
        raise ContractError("CRM kitap kümesi stok kodunu (book_code) taşıyan bir kolon seçmeli; kitaplar Logo'ya yalnız stok koduyla bağlanır.",
                            code="PLAN_INVALID")
    code_ref = codes[0]["field"]
    attributes = [s["id"] for s in plan["select"] if s["op"] in PLAIN and s["id"] not in ("book_code", "book_name")]
    values = [s["id"] for s in plan["select"] if s["op"] in AGGREGATE]
    if any(s["op"] == "missing_flag" for s in plan["select"]):
        raise ContractError("CRM kitap kümesinde eksiklik bayrağı satış satırına taşınmaz.", code="PLAN_INVALID")
    if values:
        if set(values) - set(VALUE_IDS):
            raise ContractError("CRM sayı kolonunun kimliği crm_value veya crm_value_2 olmalı.", code="PLAN_INVALID")
        if attributes or plan["group_by"] != [code_ref]:
            raise ContractError("Kitap başına CRM sayısı yalnız stok koduna göre toplanır; ek kırılım kolonu taşımaz.", code="PLAN_INVALID")
    names = [s for s in plan["select"] if s["id"] == "book_name"]
    if names and _ref_entity(names[0]["field"], aliases) != ("book", "book_name"):
        raise ContractError("book_name yalnız CRM kitap adı olabilir.", code="PLAN_INVALID")
    return {"plan": plan, "attributes": attributes, "values": values}


def check_plan(scope, metrics, dims, families, comparison):
    if families != {"sales"}:
        raise ContractError("CRM kitap kümesi yalnız satış satırı ölçüleriyle birleşir; fatura/tahsilat kitaba dağıtılamaz.")
    if "crm_attribute" in dims and not scope["attributes"]:
        raise ContractError("crm_attribute kırılımı için CRM kümesinde stok kodu dışında bir kolon seçilmeli.", code="PLAN_INVALID")
    if scope["attributes"] and "crm_attribute" not in dims:
        raise ContractError("CRM kümesindeki ek kolon kırılım istenmeden seçilmiş; kırılım yoksa yalnız book_code seçin.", code="PLAN_INVALID")
    if scope["values"]:
        if set(dims) - {"book"}:
            raise ContractError("Kitap başına CRM sayısı yalnız kitap kırılımıyla ya da toplam olarak verilir.")
        if comparison is not None:
            raise ContractError("CRM sayısı ile dönem karşılaştırması aynı hesapta yapılmaz.")


def redundant(spec, dims):
    """Hiçbir kitabı elemeyen, sayı taşımayan ve kırılımı istenmeyen küme cevaba bir şey katmaz: yok sayılır
    (2026-10-06: «yayınevine göre ciro» künye kırılımının yanına süzgeçsiz bir CRM kümesi de yazılmıştı)."""
    select = spec.get("select") if isinstance(spec, dict) else None
    return (isinstance(select, list) and not spec.get("filters")
            and not any(isinstance(s, dict) and s.get("op") in AGGREGATE for s in select)
            and "crm_attribute" not in dims and not any(j.get("kind") == "inner" for j in spec.get("joins") or [] if isinstance(j, dict)))


def describe(scope):
    from .relational_plan import describe_relational_output
    out = describe_relational_output(scope["plan"])
    return {"anlam": "Logo satışı yalnız bu CRM sorgusunun döndürdüğü stok kodlarındaki kitaplar için hesaplanır",
            "crm_sorgusu": out, "kırılım_kolonları": scope["attributes"], "crm_sayı_kolonları": scope["values"],
            "çoklu_değer": "Bir kitap birden çok kırılım değerindeyse satışı her değerde ayrı sayılır" if scope["attributes"] else None,
            "crm_sayı_koşulu": "having içinde crm_value/crm_value_2 koşulu her kitabın kendi CRM sayısına uygulanır ve kitap seçer; toplam satıra uygulanmaz" if scope["values"] else None,
            "satışsız_kitap": "Kümedeki satışı olmayan kitap 0 satışla korunur" if scope["values"] else
                              "Kümedeki satışı olmayan kitap satıra çıkmaz"}


def column_labels(scope):
    """CRM kolonlarının ekrandaki adı: kayıtlı alanın Türkçe etiketi, «CRM» ön ekiyle (Logo ölçüsünden ayrılsın)."""
    from .relational_plan import alias_entities
    from .relational_contracts import ENTITY_REGISTRY
    if not scope:
        return {}
    plan = scope["plan"]
    aliases = alias_entities(plan)
    labels = {}
    for item in plan["select"]:
        if item["id"] not in (*scope["attributes"], *scope["values"]):
            continue
        if item["op"] == "count_records":
            labels[item["id"]] = {"label": "CRM kayıt sayısı", "unit": "adet"}
            continue
        ref = item["field"]
        spec = ENTITY_REGISTRY[aliases[ref["alias"]]]["fields"][ref["field"]]
        name = spec.get("label_tr") or ref["field"].replace("_", " ")
        labels[item["id"]] = {"label": "CRM " + name, **({"unit": "adet"} if item["op"] == "count_distinct" else {})}
    return labels


def unit(scope, column):
    """CRM sayı kolonunun birimi; bilinmiyorsa None."""
    from .relational_plan import alias_entities
    if not scope or column not in scope["values"]:
        return None
    plan = scope["plan"]
    item = next(s for s in plan["select"] if s["id"] == column)
    if item["op"] != "sum":
        return None
    return UNITS.get(alias_entities(plan)[item["field"]["alias"]])


def key(code):
    return str(code or "").strip().casefold()


def run(executor, scope):
    """CRM kümesini okur: stok kodu → {kod, ad, kırılım değerleri, CRM sayıları}."""
    from .relational_executor import execute_relational_query
    result = execute_relational_query(executor, scope["plan"])
    books = {}
    for row in result["records"]:
        k = key(row.get("book_code"))
        if not k:
            continue
        item = books.setdefault(k, {"code": str(row["book_code"]).strip(), "name": row.get("book_name"),
                                    "attributes": set(), "values": {}})
        if scope["attributes"]:
            item["attributes"].add(tuple(row.get(a) for a in scope["attributes"]))
        for v in scope["values"]:
            if v in item["values"]:
                raise ContractError("CRM sayısı aynı stok kodunda birden çok satıra dağıldı.", code="SOURCE_CONTRACT_VIOLATION")
            item["values"][v] = Decimal(str(row[v])) if row.get(v) is not None else None
    executor.notes.extend(n for n in result["notes"] if n not in executor.notes)
    return books


def select(books, predicates):
    """Kitap başına CRM sayısı koşulunu her kitaba uygular (eksik sayı koşulu sağlamaz)."""
    from .operations import decimal
    ops = {"gt": lambda a, b: a > b, "gte": lambda a, b: a >= b, "lt": lambda a, b: a < b,
           "lte": lambda a, b: a <= b, "eq": lambda a, b: a == b, "neq": lambda a, b: a != b}
    return {k: b for k, b in books.items()
            if all(b["values"].get(p.metric) is not None and ops[p.op](decimal(b["values"][p.metric]), decimal(p.value))
                   for p in predicates)}


def coverage_note(books, sold):
    """Kümedeki kitapların kaçının dönemde satışı var: «0» sessiz kalmasın."""
    total = len(books)
    with_sales = len(set(books) & sold)
    return (f"CRM koşuluna uyan {total:,} kitap bulundu; {with_sales:,} tanesinin bu dönemde Logo'da satışı var. "
            "Kitaplar Logo'ya stok koduyla bağlandı.").replace(",", ".")
