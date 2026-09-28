"""Yönetim raporları (liste + Baskı Öneri): ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Rapor 5 dakikada bir Logo ve CRM'den okunur ve önbellek dosyasına yazılır; ekrandaki rakam o dosyadandır. Burada
gösterilen SQL, son okumada ÇALIŞAN metnin kendisidir (`sourceStats[].sql`: yıl görünümleri ve stok kodu listesi
yerine konmuş). Kolon başına kaynak düğmesi (SourcesSheet) aynı metni gösterir; bu kayıt sayaçlara, sekme
rozetlerine ve toplam satırına bağlanır. Eski önbellekte (yer tutucu kalmış metin) sorgu yeniden okunana dek
kayda alınmaz — şablon gösterilmez.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from semantic_bridge import provenance as P

#: Rapor SQL dosyalarının yer tutucuları ({satis:2024}, {satis:yil}, {stok_kodlari}); dize ve açıklama dışında kalırsa
#: metin çalışan metin değil şablondur ve gösterilmez.
_TEMPLATE = re.compile(r"\{[A-Za-z_]\w*(?::[^}]*)?\}")


def is_template(sql: Optional[str]) -> bool:
    bare = P._STRING_OR_COMMENT.sub(" ", sql or "")
    return bool(_TEMPLATE.search(bare) or P.placeholders_left(sql or ""))

F_GORUNUM = ("Sekmedeki kitap sayısı = son okumadaki satır sayısı; öneri düzeyi sayaçları = Öneri kolonunda o düzeyde "
             "olan satır sayısı. Arama ve süzgeçler ekranda uygulanır; «N kitap» süzgeçten geçen satırlardır.")
F_TOPLAM = ("Toplam satırı: toplamı olan kolonlarda süzgeçten geçen satırların toplamı (ekranda). Tükenme Süresi "
            "toplamı Power BI ölçüsüyle Σ stok adedi ÷ Σ ortalama satış hızı; toplamı olmayan kolon boş kalır.")
F_LISTE = ("Rapor kartı: sekme başına satır sayısı son okumadan; «N sorgu» raporun kaynak sorgu sayısıdır; yenileme "
           "aralığı ayardır (dakika).")


def _register(k: P.Kaynaklar, rid: str, sources: list, stats: dict[str, Any], dbs: dict[str, Optional[str]],
              ran_at: Any) -> dict[str, str]:
    ids: dict[str, str] = {}
    for sid, conn, title, desc, *_ in sources:
        st = stats.get(sid) or {}
        if not st.get("sql") or is_template(st["sql"]):
            continue  # eski önbellek: yer tutuculu metin gösterilmez; bir sonraki okumada gelir
        note = f" {st['warning']}" if st.get("warning") else ""
        try:
            ids[sid] = k.sorgu(f"yonetim.{rid}.{sid}", title, conn, st["sql"], database=dbs.get(conn),
                               rows=st.get("rows"), ms=st.get("dbMs"), ran_at=ran_at,
                               description=f"{desc} Son okumada çalışan metin; sonuç rapor önbelleğine yazılır.{note}")
        except P.ProvenanceError:
            continue  # eski önbellek: yer tutuculu metin gösterilmez; bir sonraki okumada gelir
    return ids


def for_report(report: Any, snap: dict[str, Any], dbs: dict[str, Optional[str]]) -> Optional[P.Kaynaklar]:
    """`GET /reports/{id}`: sekme sayaçları, öneri düzeyi sayaçları, toplam satırı, hücreler."""
    data = snap.get("data")
    if not data:
        return None
    k = P.Kaynaklar(data_end=data.get("asOf"), as_of=snap.get("updatedAt"))
    rid = report.REPORT_ID
    ids = _register(k, rid, list(report.SOURCES), data.get("sourceStats") or {}, dbs, snap.get("updatedAt"))
    every = list(ids.values())
    if not every:
        raise P.ProvenanceError("Raporun son okumasında kayıtlı sorgu yok; bir sonraki okumada görünür.")
    formulas: dict[str, str] = {}
    for name, text in getattr(report, "FORMULAS", []):
        formulas[name] = k.hesap(f"{rid}:{name}", text, every)
    fields: dict[str, str] = {"data.sourceStats": k.hesap(f"{rid}:okuma", "Kaynak başına satır ve süre son okumadan.",
                                                          every),
                              "durationMs": f"hesap:{rid}:okuma"}
    all_views = []
    for v in data.get("views") or []:
        ins: list[str] = []
        for c in v.get("columns") or []:
            src = str(c.get("source") or "")
            if src.startswith("hesap:") and src[6:] in formulas:
                ins.append(formulas[src[6:]])
            elif src in ids:
                ins.append(ids[src])
        # model sekmesi (ör. tahmin): açıklamasındaki çalışan sorgular
        for e in (v.get("explain") or {}).get("sql") or []:
            if is_template(e.get("sql")):
                continue
            try:
                ins.append(k.sorgu(f"yonetim.{rid}.{v['id']}.{e['id']}", e.get("title") or e["id"],
                                   "crm" if str(e["id"]).startswith("crm") else "logo", e["sql"],
                                   database=dbs.get("crm" if str(e["id"]).startswith("crm") else "logo"),
                                   description=e.get("description") or ""))
            except P.ProvenanceError:
                continue
        ins = list(dict.fromkeys(ins)) or every
        ref = k.hesap(f"{rid}:gorunum:{v['id']}", F_GORUNUM, ins)
        fields[f"data.views[]:{v['id']}"] = ref
        fields[f"toplam:{v['id']}"] = k.hesap(f"{rid}:toplam:{v['id']}", F_TOPLAM, [ref])
        all_views.append(ref)
    fields["data.views[]"] = k.hesap(f"{rid}:gorunumler", F_GORUNUM, all_views or every)
    fields["toplam"] = k.hesap(f"{rid}:toplam", F_TOPLAM, [fields["data.views[]"]])
    k.alanlar(fields)
    return k


def for_list(items: list[dict[str, Any]], reports: dict[str, Any], snaps: dict[str, dict[str, Any]],
             dbs: dict[str, Optional[str]]) -> P.Kaynaklar:
    """`GET /reports`: kart başına sekme satır sayıları ve sorgu sayısı."""
    k = P.Kaynaklar()
    fields: dict[str, str] = {}
    every: list[str] = []
    for it in items:
        rid = it["id"]
        snap = snaps.get(rid) or {}
        ids = _register(k, rid, list(reports[rid].SOURCES), (snap.get("data") or {}).get("sourceStats") or {}, dbs,
                        snap.get("updatedAt"))
        if ids:
            fields[f"reports[]:{rid}"] = k.hesap(f"liste:{rid}", F_LISTE, list(ids.values()))
            every += list(ids.values())
    if not every:
        raise P.ProvenanceError("Raporlar henüz okunmadı; ilk okumadan sonra sorgu bilgisi görünür.")
    fields["reports[]"] = k.hesap("liste", F_LISTE, every)
    k.alanlar(fields)
    return k


#: Rakam olmayan sayılar: zaman damgaları ve ayarlar.
NOT_RAKAM = ("serverTime", "updatedAt", "startedAt", "failedAt", "waitingAt", "nextRefreshAt", "refreshStartedAt",
             "refreshIntervalSeconds", "reports[].updatedAt", "reports[].refreshIntervalSeconds")
