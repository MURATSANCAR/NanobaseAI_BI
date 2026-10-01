"""Ekrana giden finans metinlerinin son süzgeci (2026-09-25 kullanıcı kuralı: ekranda teknik ad yok).

Plan, kaynak ve denetim iletileri model ve kayıt için teknik ayrıntı taşır: Logo kolon adları (satır net tutarı yerine
kolon adı), CRM tablo/alan adları, plan alan adları (ölçü/kırılım listeleri, kaynak raporu dalları), sorgu dili ve
kullanılan altyapının adları. Bu ayrıntı sunucu günlüğünde, sorgu kaydının `error` alanında ve `semantic` durumunda kalır;
kullanıcıya giden açıklama, özet, eksik kapsam, veri notu, hesap tanımı ve kolon başlıkları buradan geçer.

İki parça:

* `public_text` — tek metin: bilinen teknik adı Türkçe iş karşılığıyla değiştirir, karşılığı olmayan teknik tanımlayıcıyı
  (alt çizgili ad, nokta ile yazılmış tablo.kolon, CRM tablo/alan adı) «ilgili alan» yapar.
* `public_response` — cevap sözlüğü: ekrana giden alanları (bölümler dahil) süzgeçten geçirir; kayıt ve sorgu alanlarına
  (`semantic`, `sql`, `physicalSql`, kayıtların değerleri) dokunmaz — kitap ya da müşteri adı bir veri değeridir, süzülmez.

Hata iletileri `public_error` ile: plan doğrulamasının iç iletisi (onarım turuna giden teknik ileti) ekrana gitmez; yerine
iş dilinde neden ve, varsa, model denetiminin karşılanmadı dediği koşullar gelir.
"""
from __future__ import annotations

import re
from typing import Any

from .contracts import METRICS

# --------------------------------------------------------------------------------------------- sözlük
#: Logo kolon/tablo adları ve sorgu dili sözcükleri (büyük harfle yazıldıklarında). Karşılığı olan Türkçe iş adıyla,
#: olmayan boşla değişir; ardından kalan noktalama temizlenir.
_LOGO = {
    "LINENET": "satır net tutarı", "NETTOTAL": "fatura genel toplamı", "GROSSTOTAL": "brüt toplam",
    "TOTALVAT": "KDV tutarı", "VAT": "KDV", "TOTALDISCOUNTS": "toplam iskonto", "DISTDISC": "dağıtılmış iskonto",
    "TRCODE": "işlem türü", "LINETYPE": "satır türü", "IOCODE": "giriş/çıkış türü", "SIGN": "borç/alacak yönü",
    "SPECODE": "özel kod", "SPECODE2": "satış kanalı kodu", "CYPHCODE": "yetki kodu", "TRADINGGRP": "ticari grup",
    "AMOUNT": "miktar", "OUTCOST": "birim maliyet", "PRICE": "birim fiyat", "TOTAL": "toplam", "PAID": "ödenen",
    "CANCELLED": "iptal durumu", "APPROVAL": "onay", "INVOICEREF": "fatura bağı", "STOCKREF": "stok kartı bağı",
    "CLIENTREF": "cari kart bağı", "LOGICALREF": "kayıt kimliği", "SOURCEINDEX": "depo", "DATE_": "tarih",
    "DEFINITION_": "ad", "FICHENO": "belge numarası", "DOCODE": "belge numarası", "PAYMENTREF": "ödeme planı bağı",
    "ITEMS": "stok kartı", "STLINE": "stok hareketi", "STFICHE": "stok fişi", "INVOICE": "fatura başlığı",
    "CLCARD": "cari kart", "CLFLINE": "cari hareket", "ORFICHE": "sipariş fişi", "ORFLINE": "sipariş satırı",
    "PAYTRANS": "ödeme hareketi", "GNTOTST": "stok toplamı", "L_CAPIPERIOD": "dönem tanımı", "L_CAPIFIRM": "firma tanımı",
    "COUNT_BIG": "sayım", "COUNT": "sayım", "SUM": "toplam", "HAVING": "sonuç süzgeci", "JOIN": "birleştirme",
    "LEFT JOIN": "birleştirme", "FULL OUTER": "", "UNION ALL": "birleştirme", "UNION": "birleştirme",
    "SELECT": "okuma", "WHERE": "koşul", "GROUP BY": "gruplama", "ORDER BY": "sıralama", "CASE WHEN": "",
    "NULL": "boş", "UUID": "kimlik", "GUID": "kimlik", "JSON": "", "ISO": "", "CTE": "",
}
#: CRM tablo/alan adları: `…Base` tablo, `new_…` özel alan, durum kodları.
_CRM = [
    (r"\b(?:new_)?\w*Base\.\w+", "CRM alanı"),
    (r"\bstatecode\s*=\s*0\b", "aktif"),
    (r"\bstatecode\s*=\s*1\b", "pasif"),
    (r"\b(?:statecode|statuscode)\b(?:\s*=\s*\d+)?", "kayıt durumu"),
    (r"\b(?:new_)?\w*Base\b", "CRM kaydı"),
    (r"\bnew_\w+", "CRM alanı"),
    (r"\b(?:CreatedOn|ModifiedOn|createdon|modifiedon)\b", "kayıt tarihi"),
    (r"\b(?:created_at|updated_at)\b", "kayıt tarihi"),
]
#: Altyapı ve ürün adları — ekranda yazmaz (model, sunucu, veritabanı motoru, dış araç).
#: Kişi/kitap adı da olabilen genel sözcükler (Claude, Gemini, Mistral…) listede yok: açıklamadaki bir yazar adı bozulmasın.
_TECH = re.compile(
    r"\b(?:Qwen[\w.-]*|vLLM|LLM|Temporal|TimesFM[\w.-]*|Ollama|OpenAI|ChatGPT|GPT-?\d[\w.-]*|Anthropic|DeepSeek[\w.-]*|"
    r"NVIDIA|H100|Real-ESRGAN|Typst|Ghostscript|Power\s*BI|PostgreSQL|Postgres|MSSQL|"
    r"SQL\s*Server|SQLAlchemy|Python|FastAPI|pyodbc|Dynamics\s*365)\b", re.IGNORECASE)
_TECH_WORD = {"power bi": "mevcut rapor", "sql server": "veritabanı", "mssql": "veritabanı", "postgresql": "veritabanı",
              "postgres": "veritabanı"}
#: Plan sözleşmesinin alan adları — modele giden JSON anahtarları, kullanıcının dili değil.
_PLAN_FIELDS = {
    "crm_report": "kaynak raporu", "logo_report": "kaynak raporu", "relational_query": "kaynak raporu",
    "population_contract": "kayıt kapsamı", "selection_intent": "seçim amacı", "output_contract": "çıktı tanımı",
    "output_fields": "sonuç kolonları", "input_filters": "süzgeçler", "group_by": "gruplama", "order_by": "sıralama",
    "sale_kind": "satış türü", "comparison.metric": "karşılaştırılan ölçü", "comparison": "dönem karşılaştırması",
    "metrics": "ölçüler", "metric": "ölçü", "dimensions": "kırılımlar", "derived": "türetilmiş hesap",
    "having": "sonuç süzgeci", "analytics": "analitik işlem", "sections": "bölümler", "gaps": "eksik kapsam",
    "coverage": "kapsam", "uncovered": "karşılanmayan", "clarification": "netleştirme", "filters": "süzgeçler",
    "parsedPeriods": "dönem", "referenceDate": "bugünün tarihi", "lookback_days": "geriye bakılan gün sayısı",
    "as_of": "itibarıyla tarihi", "top_remainder": "ilk N ve kalan", "contribution": "pay",
}
#: Sorgu dili adı: «SQL» ve «Ham SQL» kullanıcıya «sorgu» olarak görünür.
_SQL = re.compile(r"\b(?:ham\s+)?SQL\b", re.IGNORECASE)


def _labels() -> dict[str, str]:
    """Bilinen kolon/ölçü kimliklerinin Türkçe adları (sonuç kolonu başlıklarıyla aynı kaynak)."""
    from .result_metadata import LABELS
    out = {k: v for k, v in LABELS.items()}
    out.update({k: m.label for k, m in METRICS.items()})
    out.update({"author_group": "yazar grubu", "subbrand": "alt marka", "base_value": "baz dönem değeri",
                "target_value": "karşılaştırılan dönem değeri"})
    return out


#: Alt çizgili ya da noktalı tanımlayıcı (net_sales, LG_211_01_STLINE, ITEMS.CODE). İlk parça en az iki karakter: «T.C.»
#: gibi kısaltmalar tanımlayıcı sayılmaz.
_WORD = re.compile(r"\b[A-Za-z][A-Za-z0-9]+(?:[_.][A-Za-z0-9]+)+\b")


def _identifier(match: re.Match, labels: dict[str, str]) -> str:
    token = match.group(0)
    if token in _PLAN_FIELDS:
        return _PLAN_FIELDS[token]
    if token in _LOGO:
        return _LOGO[token]
    if token in labels:
        label = labels[token]
        return label if label[:2].isupper() else label[:1].lower() + label[1:]
    if token.upper() == token and token.replace("_", "").replace(".", "").isalnum():
        # LG_211_01_STLINE, L_CAPIPERIOD, ITEMS.CODE: tablo/kolon adı
        return "kaynak"
    if re.fullmatch(r"\d+(?:\.\d+)+", token):
        return token
    return "ilgili alan"


def public_text(text: Any) -> str:
    """Tek metni ekran diline çevirir. Boş/None boş metin döner; Türkçe iş cümlesi aynen kalır."""
    if text is None:
        return ""
    s = str(text)
    if not s.strip():
        return s.strip()
    labels = _labels()
    s = _TECH.sub(lambda m: _TECH_WORD.get(re.sub(r"\s+", " ", m.group(0).lower()), ""), s)
    for pattern, repl in _CRM:
        s = re.sub(pattern, repl, s)
    # Sorgu ifadesindeki tek harfli takma ad: «f.LINENET» → «LINENET».
    s = re.sub(r"\b[a-z]\.(?=[A-Z][A-Z0-9_]{2,})", "", s)
    # «TRCODE IN (7,8,9)», «TRCODE=8», «SIGN=1»: kodun değerleri de teknik ayrıntıdır.
    s = re.sub(r"\b(TRCODE|LINETYPE|IOCODE|SIGN)\s*(?:NOT\s+IN|IN|=|<>|!=)\s*(?:\([\d\s,/]*\)|\d+(?:\s*[,/]\s*\d+)*)",
               lambda m: _LOGO[m.group(1)], s)
    s = re.sub(r"\bSQL\s+sorgu\w*", "sorgu", s)
    s = _SQL.sub("sorgu", s)
    s = _WORD.sub(lambda m: _identifier(m, labels), s)
    # Önce çok sözcüklü, sonra tek sözcüklü Logo/sorgu adları (yalnız büyük harfle yazılmışsa).
    for word in sorted(_LOGO, key=len, reverse=True):
        s = re.sub(r"(?<!\w)" + re.escape(word) + r"(?!\w)(?:\s*\(\s*\*?\s*\))?", _LOGO[word], s)
    # Tek kalmış plan alanı adları (alt çizgisiz İngilizce anahtarlar).
    s = re.sub(r"\b(" + "|".join(re.escape(k) for k in _PLAN_FIELDS if re.fullmatch(r"[a-z]+", k)) + r")\b",
               lambda m: _PLAN_FIELDS[m.group(1)], s)
    # Silinen adların bıraktığı boşluk ve noktalama.
    s = re.sub(r"\(\s*[,;/*]*\s*\)", "", s)
    s = re.sub(r"\s+([,.;:)])", r"\1", s)
    s = re.sub(r"([(])\s+", r"\1", s)
    s = re.sub(r"([,;])(?:\s*[,;])+", r"\1", s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    return s.strip()


#: Ölçülerin ekrandaki hesap tanımı. Sözleşmedeki `definition` model ve kayıt içindir (işlem türü kodları, kolon adları);
#: kullanıcı aynı tanımı iş diliyle görür. Yeni ölçü eklenince burada karşılığı yazılır (test bunu ister); yazılmazsa
#: sözleşme tanımı süzgeçten geçerek gösterilir.
PUBLIC_DEFINITIONS = {
    "sales_amount": "Faturalı satış satırlarının iskonto sonrası, KDV hariç tutarı (toptan, perakende ve hizmet satışı); iadeler düşülmez.",
    "net_sales": "Faturalı satış satırlarının iskonto sonrası, KDV hariç tutarından satış iadelerinin düşülmüş hâli.",
    "sold_quantity": "Faturalı toptan ve perakende satış satırlarındaki miktar; iadeler düşülmez, hizmet satırları dahil değildir.",
    "net_quantity": "Faturalı toptan ve perakende satış miktarından satış iadesi miktarının düşülmüş hâli.",
    "return_amount": "İptal edilmemiş satış iadesi faturalarının satır tutarı; iskonto sonrası, KDV hariç, pozitif gösterilir.",
    "invoice_count": "İptal edilmemiş satış faturalarının sayısı (toptan, perakende ve hizmet); satırlar değil belgeler sayılır.",
    "invoice_amount": "İptal edilmemiş satış faturalarının genel toplamı; satır bazında net ciro değildir.",
    "collections": "Müşteri carilerindeki iptal edilmemiş alacak hareketleri: nakit, havale, çek, senet ve kredi kartı. Çek/senet "
                   "teslimi dahildir; yalnız nakit tahsilat değildir.",
    "active_books": "CRM'de aktif ve durum nedeni Aktif/Etkin olan kitap kartları; pasif kartlar hariç.",
    "active_authors": "CRM'de aktif, durum nedeni Etkin ve yazar olarak işaretli kişi kartları; ayrı bir yazar sözlüğünün sayısı değildir.",
    "active_customers": "CRM'de aktif ve durum nedeni Aktif Müşteri olan müşteri kartları; potansiyel, pasif, arşiv ve sorunlu "
                        "müşteriler hariç.",
}


def public_definition(metric_id: str) -> str:
    return PUBLIC_DEFINITIONS.get(metric_id) or public_text(METRICS[metric_id].definition)


# --------------------------------------------------------------------------------------------- hata
PLAN_REJECTED = ("Soru, doğrulanmış hesap tanımlarına güvenle dönüştürülemedi; yanlış olabilecek bir sonuç sunmak yerine "
                 "hesap durduruldu. Ölçüyü, dönemi ve kırılımı açıkça yazarak yeniden sorabilirsiniz.")
_GENERIC = {
    "PLAN_INVALID": PLAN_REJECTED,
    "SOURCE_UNAVAILABLE": "Veri kaynağına şu anda ulaşılamıyor; sonuç sunulmadı. Biraz sonra yeniden deneyebilirsiniz.",
}


def public_error(exc: Exception) -> str:
    """ContractError → ekran iletisi. İç ileti (`str(exc)`) kayıtta ve günlükte kalır."""
    code = getattr(exc, "code", None)
    unmet = [public_text(i) for i in getattr(exc, "unmet", ()) if public_text(i)]
    if code == "PLAN_INVALID":
        if unmet:
            return ("Sorudaki şu koşullar doğrulanmış hesaba güvenle taşınamadı: " + "; ".join(unmet)
                    + ". Yanlış olabilecek bir sonuç sunulmadı.")
        return PLAN_REJECTED
    if code == "UNSUPPORTED_CAPABILITY" and unmet:
        return "Bu soru için henüz doğrulanmış bir hesap tanımı yok. Cevaplanamayan kısım: " + "; ".join(unmet) + "."
    if code in _GENERIC and not str(exc).strip():
        return _GENERIC[code]
    text = public_text(str(exc))
    return text or _GENERIC.get(code, PLAN_REJECTED)


# --------------------------------------------------------------------------------------------- cevap
_TEXT_KEYS = ("explanation", "title")
_TEXT_LISTS = ("definitions",)


def _humanize_label(label: Any) -> Any:
    """Kolon başlığı bir kimlikse (model seçtiği sonuç adı «kitap_sayisi») okunur biçime çevrilir."""
    if not isinstance(label, str):
        return label
    if re.fullmatch(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+", label):
        known = _labels().get(label)
        if known:
            return known
        words = label.replace("_", " ")
        return words[:1].upper() + words[1:]
    return public_text(label)


def _columns(columns: Any) -> Any:
    if not isinstance(columns, list):
        return columns
    out = []
    for col in columns:
        if isinstance(col, dict):
            col = dict(col)
            if "label" in col:
                col["label"] = _humanize_label(col["label"])
            for key in ("definition", "formula"):
                if isinstance(col.get(key), str):
                    col[key] = public_text(col[key])
        out.append(col)
    return out


def public_response(resp: dict[str, Any]) -> dict[str, Any]:
    """Ekrana giden alanları süzer; yeni sözlük döner. Kayıtlar, sorgu ve `semantic` olduğu gibi kalır."""
    if not isinstance(resp, dict):
        return resp
    out = dict(resp)
    for key in _TEXT_KEYS:
        if isinstance(out.get(key), str):
            out[key] = public_text(out[key])
    for key in _TEXT_LISTS:
        if isinstance(out.get(key), list):
            out[key] = [public_text(x) if isinstance(x, str) else x for x in out[key]]
    if isinstance(out.get("dataNotes"), list):
        out["dataNotes"] = [{**n, "message": public_text(n.get("message"))} if isinstance(n, dict) else public_text(n)
                            for n in out["dataNotes"]]
    if isinstance(out.get("gaps"), list):
        out["gaps"] = [{**g, "reason": public_text(g.get("reason"))} if isinstance(g, dict) else public_text(g)
                       for g in out["gaps"]]
    if "columns" in out:
        out["columns"] = _columns(out["columns"])
    if isinstance(out.get("sections"), list):
        out["sections"] = [public_response(s) for s in out["sections"]]
    return out


def leaks(text: Any) -> list[str]:
    """Metinde kalan teknik adlar (test ve kabul taraması için)."""
    s = str(text or "")
    found = [m.group(0) for m in _TECH.finditer(s)]
    found += [w for w in ("TRCODE", "LINENET", "NETTOTAL", "LINETYPE", "statecode", "statuscode") if w in s]
    found += re.findall(r"\bSQL\b|\bLG_\w+|\b\w+Base\b|\bnew_\w+", s)
    found += [k for k in _PLAN_FIELDS if "_" in k or "." in k if re.search(r"(?<![\w.])" + re.escape(k) + r"(?![\w])", s)]
    found += re.findall(r"\b(?:metrics|dimensions|derived|analytics|uncovered)\b", s)
    found += re.findall(r"\b[a-z]+_[a-z0-9_]+\b", s)
    return list(dict.fromkeys(found))
