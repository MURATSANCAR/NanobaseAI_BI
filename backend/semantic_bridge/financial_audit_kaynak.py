"""Finansal denetim: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Denetim raporu arka planda Logo'dan hesaplanır ve değişmez bir çalışma kâğıdı olarak saklanır (önbellek = rapor
arşivi). Rapordaki her rakamın kaynağı, rapor hazırlanırken Logo'da ÇALIŞAN fiziksel SQL'dir (`queries`: kimlik →
başlık, SQL, satır, süre, an); burada o metin olduğu gibi gösterilir, yeniden kurulmaz. Firma kopyası raporun yılına
göredir (`firm`). Canlı ayrıntı uçları (hareket, belge, bulgu satırları) kendi çalıştırdıkları SQL'i taşır.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from semantic_bridge import provenance as P

# ------------------------------------------------------------------ formüller

F_HESAP = ("Hesap başına (dönem içi, iptal edilmemiş fiş ve satırlar): borç = Σ DEBIT, alacak = Σ CREDIT, net bakiye = "
           "borç − alacak, hareket = satır sayısı. Açılış fişi (TRCODE 1) dahildir.")
F_GENEL = ("Hareket sayısı = Σ hesap satır sayısı; toplam borç ve alacak = hesapların toplamı; veri son günü = en son "
           "hareket tarihi. Sorgu süresi raporu kuran bütün sorguların toplamıdır.")
F_ORAN = ("Oran = pay ÷ payda; pay ve payda hesap sınıflarının net bakiyelerinden (1 dönen varlık, 15 stok, 3 kısa ve 4 "
          "uzun vadeli yabancı kaynak, 5 özkaynak; kaynak sınıflarında işaret ters çevrilir). Payda sıfır/negatifse ya da "
          "kapanış uyumu doğrulanmadıysa oran hesaplanmaz. Gün cinsinden oranlar dönem hareketlerinden.")
F_KAPANIS = "Kapanış farkı = aktif (1 + 2) − kısa vadeli − uzun vadeli yabancı kaynak − özkaynak (net bakiyelerden)."
F_KAPSAM = ("Kontrol kütüphanesi: her madde hesap kapsamına (hesap kodu önekleri) ve rapordaki gözlemlere göre "
            "değerlendirilir; durum sayıları (hesaplandı, gözlem, kanıt gerekiyor, dönemi gelmedi, doğrulanamadı) madde "
            "sayısıdır, denetim başarı oranı değildir.")
F_BILESEN = ("Kontrol bileşeni: seçilen hesaplarda borç, alacak, net bakiye ve hareket toplamı; ters yönlü alt hesaplarda "
             "tutar > 0,01 TL inceleme adayıdır.")

#: Kontrol bileşeni → onu hesaplayan sorgu (rapor kurulurken `financial_audit.build_report` ile aynı eşleme).
COMPONENT_QUERY = {
    "account-scope": "hesaplar", "balance-sign": "hesaplar", "fx-profile": "profil", "voucher-counterpart": "karsiHesap",
    "multipleDocumentTypes": "belge.belgeFis", "multiplePaymentTypes": "belge.belgeFis",
    "missingNumber": "belge.belgeler", "missingDate": "belge.belgeler", "missingPayment": "belge.belgeler",
    "document-account": "belge.hesapBelge", "asset-source": "belge.sabitKiymet", "vat": "kdv",
}
#: Temel kontrol → sorgusu.
CHECK_QUERY = {"slip-balance": "fisDenge", "slip-link": "butunluk"}

#: Eski raporlarda (`queries` alanından önce) SQL listesi sırayla: temel altı sorgu, destek dört sorgu.
_LEGACY = [("hesaplar", "Hesap bakiyeleri ve hareket sayıları"), ("fisDenge", "Fiş bazında borç–alacak eşitliği"),
           ("butunluk", "Hareket–fiş bağlantısı ve iptal"), ("profil", "Hesap profili"),
           ("karsiHesap", "Fiş karşı hesap kontrolleri"), ("kdv", "KDV hesapları ay ay hareket"),
           ("belge.belgeler", "E-defter belge profili"), ("belge.belgeFis", "Fiş başına belge ve ödeme türü"),
           ("belge.hesapBelge", "Ana hesaba göre belge profili"), ("belge.sabitKiymet", "Sabit kıymet hesap cetveli")]


def _firm(report: dict[str, Any]) -> Optional[str]:
    if report.get("firm"):
        return str(report["firm"])
    m = re.search(r"\bLG_(\d{3})_", " ".join(s for s in report.get("sql") or [] if s))
    return m.group(1) if m else None


def _queries(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    q = report.get("queries")
    if q:
        return q
    out: dict[str, dict[str, Any]] = {}
    sqls = [s for s in report.get("sql") or []]
    for (qid, title), sql in zip(_LEGACY, sqls):
        if sql:
            out[qid] = {"title": title, "sql": sql}
    for c in (report.get("deepAudit") or {}).get("checks") or []:
        if c.get("sql") and c.get("detailKind"):
            out.setdefault(f"derin.{c['detailKind']}", {"title": c.get("title"), "sql": c["sql"]})
    return out


def for_report(report: dict[str, Any], logo_db: Optional[str]) -> P.Kaynaklar:
    """`GET /overview` ve `GET /runs/{id}`: raporun bütün rakamları."""
    k = P.Kaynaklar(data_end=report.get("lastDate"), as_of=report.get("computedAt"))
    year, firm = report.get("year"), _firm(report)
    ids: dict[str, str] = {}
    for qid, q in _queries(report).items():
        if not q.get("sql"):
            continue
        ids[qid] = k.sorgu(
            f"denetim.{qid}", q.get("title") or qid, "logo", q["sql"], database=logo_db, rows=q.get("rows"),
            ms=q.get("dbMs"), ran_at=q.get("at") or report.get("computedAt"),
            period=f"{year} · Logo firma {firm}" if firm else str(year),
            description="Rapor hazırlanırken Logo'da çalıştırılan fiziksel sorgu; sonucu değişmez rapor arşivinde "
                        "saklanır, ekrandaki rakam bu kayıttan okunur.")
    if not ids:
        raise P.ProvenanceError("Bu raporda kayıtlı sorgu yok.")
    base = [ids[x] for x in ("hesaplar",) if x in ids] or list(ids.values())[:1]
    prof = [ids[x] for x in ("profil",) if x in ids]
    every = list(ids.values())
    fields: dict[str, str] = {
        "accounts[]": k.hesap("hesap", F_HESAP, base),
        "lineCount": k.hesap("genel", F_GENEL, base), "debit": "hesap:genel", "credit": "hesap:genel",
        "firstDate": "hesap:genel", "lastDate": "hesap:genel",
        "dbMs": k.hesap("sure", "Toplam sorgu süresi = raporu kuran sorguların süreleri toplamı.", every),
        "queries": "hesap:sure",
        "closingGap": k.hesap("kapanis", F_KAPANIS, base),
        "ratios[]": k.hesap("oran", F_ORAN, base + prof),
    }
    if "butunluk" in ids:
        fields["sourceIntegrity"] = ids["butunluk"]
    if "profil" in ids:
        fields["profiles[]"] = ids["profil"]
    if "karsiHesap" in ids:
        fields["pairChecks"] = ids["karsiHesap"]
    if "kdv" in ids:
        fields["vatMonths[]"] = k.hesap("kdvAy", "Ay sonuna kadar birikimli 191 + 391 net bakiyesi (borç − alacak); "
                                                "190, 191, 391 ayrı gösterilir.", [ids["kdv"]])
    for r in report.get("ratios") or []:
        fields[f"ratios[]:{r.get('note')}"] = k.hesap(f"oran:{r.get('note')}", f"{r.get('title')}: {r.get('formula')}. "
                                                      + F_ORAN, base + prof)
    checks = []
    for c in report.get("checks") or []:
        src = ids.get(CHECK_QUERY.get(c["id"], "hesaplar")) or base[0]
        ref = k.hesap(f"kontrol:{c['id']}", f"{c.get('title')}: {c.get('formula')}", [src])
        fields[f"checks[]:{c['id']}"] = ref
        checks.append(ref)
    fields["checks[]"] = k.hesap("kontroller", "Temel kontroller: her kontrolün etkilenen kayıt/hesap sayısı ve tutarı "
                                               "kendi sorgusundan; durum = bulgu varsa «inceleme adayı», veri eksikse "
                                               "«doğrulanamadı», yoksa «geçti».", checks or base)
    # kontrol kütüphanesi
    cov = k.hesap("kapsam", F_KAPSAM, every)
    fields["coverage"] = cov
    comp_refs: dict[str, str] = {}
    for cid, qid in COMPONENT_QUERY.items():
        if qid in ids:
            comp_refs[cid] = k.hesap(f"bilesen:{cid}", F_BILESEN, [ids[qid]])
    comp_refs["cash-sales"] = k.hesap("bilesen:cash-sales", "Kasa bakiyesi ÷ (dönem brüt satışları ÷ takvim günü); "
                                                            "brüt satış = 60 ile başlayan hesapların dönem alacak − borcu.",
                                      base + prof)
    comp_refs["oran"] = "hesap:oran"
    for cid, ref in comp_refs.items():
        fields[f"coverage.items[].components[]:{cid}"] = ref
    fields["coverage.items[].components[]"] = cov
    # destek ve derin tarama
    ev = report.get("supportingEvidence") or {}
    ev_map = {"documentProfiles[]": "belge.belgeler", "documentVoucherProfile": "belge.belgeFis",
              "accountDocumentProfiles[]": "belge.hesapBelge", "assetProfiles[]": "belge.sabitKiymet"}
    ev_ids = [ids[q] for q in ev_map.values() if q in ids]
    if ev:
        fields["supportingEvidence"] = k.hesap("destek", "Destek verileri: e-defter belge alanları ve sabit kıymet "
                                                         "cetveli, Logo'da saklandığı gibi gruplanmış satır sayıları.",
                                               ev_ids or base)
        for path, qid in ev_map.items():
            if qid in ids:
                fields[f"supportingEvidence.{path}"] = ids[qid]
    deep = report.get("deepAudit") or {}
    if deep:
        deep_ids = [v for q, v in ids.items() if q.startswith("derin.")]
        fields["deepAudit"] = k.hesap("derin", "Logo içi karşılaştırmalar: aynı olayın iki kaynağı (fatura ↔ fiş, banka ↔ "
                                               "muhasebe, KDV ↔ muhasebe, gün sonu kasa); değerlendirilen kayıt ve bulgu "
                                               "sayıları karşılaştırma sorgusunun sonucudur.", deep_ids or base)
        fields["deepAudit.checks[]"] = "hesap:derin"
        fields["deepAudit.sources[]"] = "hesap:derin"
        for c in deep.get("checks") or []:
            qid = f"derin.{c.get('detailKind')}"
            if qid in ids:
                fields[f"deepAudit.checks[]:{c['id']}"] = k.hesap(f"derin:{c['id']}", f"{c.get('title')}: "
                                                                  f"{c.get('formula')}", [ids[qid]])
        for s in deep.get("sources") or []:
            qid = f"derin.{s.get('sourceDataset')}"
            if qid in ids:
                fields[f"deepAudit.sources[]:{s['id']}"] = ids[qid]
        for key in (deep.get("datasets") or {}):
            if f"derin.{key}" in ids:
                fields[f"deepAudit.datasets.{key}"] = ids[f"derin.{key}"]
    # ekranda sayılanlar
    fields.update({
        "ozet.bulgu": k.hesap("ozetBulgu", "İnceleme gerektiren = durumu «inceleme adayı» olan temel kontrol sayısı.",
                              [fields["checks[]"]]),
        "ozet.gecen": k.hesap("ozetGecen", "Kontrol geçti = durumu «geçti» olan temel kontrol sayısı (yalnız çalıştırılan "
                                           "kurallar içinde).", [fields["checks[]"]]),
        "ozet.oran": k.hesap("ozetOran", "Hesaplanan oran = değeri hesaplanabilen rasyo sayısı.", ["hesap:oran"]),
        "ozet.kapsam": k.hesap("ozetKapsam", "İnceleme kapsamı = kontrol kütüphanesindeki madde (kontrol ve inceleme "
                                             "başlığı) sayısı; süzgeçteki sayı ekranda sayılır.", [cov]),
        "ozet.hesapSayisi": k.hesap("ozetHesap", "Hesap sayısı = dönemde hareketi olan hesap kartı (süzgeçteki sayı "
                                                 "ekranda sayılır).", base),
    })
    k.alanlar(fields)
    return k


def for_live(out: dict[str, Any], sid: str, title: str, year: int, logo_db: Optional[str], desc: str) -> P.Kaynaklar:
    """Canlı ayrıntı uçları (hareket, belge, bulgu satırları): çalıştırdıkları fiziksel SQL'in kendisi."""
    if not out.get("sql"):
        raise P.ProvenanceError("Canlı okumanın SQL metni dönmedi.")
    firm = out.get("firm")
    k = P.Kaynaklar(as_of=out.get("readAt"))
    s = k.sorgu(sid, title, "logo", out["sql"], database=logo_db, rows=len(out.get("items") or []), ms=out.get("dbMs"),
                ran_at=out.get("readAt"), period=f"{year} · Logo firma {firm}" if firm else str(year),
                description=desc + " Canlı okuma (rapor anından ayrı); toplam = sorgunun COUNT(*) OVER() sonucu.")
    k.alanlar({"items[]": s, "total": s, "dbMs": s})
    return k


#: Rakam olmayan sayılar (kimlik, yıl, ay, sayfa, not numarası).
NOT_RAKAM = ("year", "page", "refresh", "accounts[].accountRef", "accounts[].accountType", "ratios[].note",
             "coverage.items[].note", "coverage.items[].page", "coverage.items[].endPage", "coverage.items[].accountRefs",
             "coverage.items[].components[].accountRefs", "coverage.items[].components[].note",
             "profiles[].accountRef", "vatMonths[].month", "items[].lineRef", "items[].slipRef", "items[].documentRef")
