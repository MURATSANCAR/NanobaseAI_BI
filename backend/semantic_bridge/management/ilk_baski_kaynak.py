"""M10 İlk baskı ve satış tahmini: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Tahmin günde bir kez hazırlanan rapor önbelleğinden kurulur (CRM kitap kartları, emsaller, baskı adetleri; Logo'dan
2015'ten bu yana yıl yıl kitap × ay × kanal satışı). Gösterilen SQL son okumada ÇALIŞAN metindir (yıl görünümü yerine
konmuş); Logo satışı yıl başına ayrı kayıttır. Kitap ekranındaki anlık tahmin aynı veri kümesinden bellekte hesaplanır;
kaynağı yine bu okumalardır. Rakamı model üretmez: tahmin emsal satışlarından kuraldır, gerekçesi formüldedir.
"""
from __future__ import annotations

from typing import Any, Optional

from semantic_bridge import provenance as P
from semantic_bridge.management import ilk_baski as IB
from semantic_bridge.management.kaynak import is_template

F = dict(IB.FORMULAS)
F_YENI = " ".join(F[x] for x in ("Baz tahmin", "Senaryolar", "İlk baskı önerisi", "Ciro"))
F_TAKIP = ("Beklenen (bugüne) = baz tahmin × emsallerin aynı aya kadarki satış payı; sapma = gerçekleşen ÷ beklenen − 1; "
           "kötümser senaryonun aynı aya kadarki değerinin altında kalan kitap uyarıdır. " + F["Revize tahmin"])
F_SINAMA = ("Geçmiş sınama: 2024 başından çıkan her kitap için lansmandan 2 ay önceki veriyle tahmin kurulur ve ilk 6 / 12 "
            "ayın gerçekleşeniyle karşılaştırılır. Tipik sapma = |tahmin ÷ gerçekleşen − 1| ortancası; ±%25 / ±%50 içinde "
            "kalan pay; 2 kat dışı; toplam adette sapma; yön. Karşılaştırma: CRM emsali ve son 12 ay ortancası aynı ölçüyle. "
            "«Bu kadar basılsaydı»: önerilen baskıda 6 / 12 ayda tükenen pay ve 12. ay elde kalan.")
F_SAYIM = "Kitap kartı, lansmanı (Logo'da ilk net satış ayı) olan kitap ve CRM'de emsali girilmiş kitap sayıları."
F_KANAL = "Kanal payı = emsallerin ilk aylarındaki kanal dağılımı (puan ağırlıklı); adet = baz × pay."
F_EMSAL = F["Emsal puanı"] + " Emsal başına ilk 6 / 12 ay satışı Logo'dan (net adet)."


def sources(k: P.Kaynaklar, data: dict[str, Any], dbs: dict[str, Optional[str]], ran_at: Any) -> dict[str, list[str]]:
    """Raporun son okumasındaki çalışan sorgular: kaynak → kayıt kimlikleri (Logo satışı yıl başına ayrı)."""
    stats = data.get("sourceStats") or {}
    out: dict[str, list[str]] = {}
    for sid, conn, title, desc in IB.SOURCES:
        st = stats.get(sid) or {}
        texts = st.get("sqlByYear") or ({"": st["sql"]} if st.get("sql") else {})
        for y, sql in sorted(texts.items()):
            if is_template(sql):
                continue  # yer tutucu kalmış eski metin gösterilmez
            rid = f"ilkbaski.{sid}" + (f".{y}" if y else "")
            try:
                out.setdefault(sid, []).append(k.sorgu(
                    rid, f"{title}{f' · {y}' if y else ''}", conn, sql, database=dbs.get(conn),
                    rows=(st.get("rowsByYear") or {}).get(y, st.get("rows") if not y else None),
                    ms=(st.get("msByYear") or {}).get(y, st.get("dbMs") if not y else None), ran_at=ran_at,
                    period=f"{y}" if y else None,
                    description=desc + (" Son okumada yalnız son yılın metni saklanmıştı; yeniden okumada her yıl ayrı "
                                        "görünür." if sid == "logo_aylik_kanal" and not st.get("sqlByYear") else "")))
            except P.ProvenanceError:
                continue  # yer tutucu kalmış eski metin gösterilmez
    return out


def _all(src: dict[str, list[str]]) -> list[str]:
    return [x for ids in src.values() for x in ids]


def for_summary(out: dict[str, Any], data: dict[str, Any], dbs: dict[str, Optional[str]], ran_at: Any) -> Optional[P.Kaynaklar]:
    if not data:
        return None
    k = P.Kaynaklar(data_end=data.get("dataEnd"), as_of=ran_at)
    src = sources(k, data, dbs, ran_at)
    every = _all(src)
    if not every:
        raise P.ProvenanceError("Tahminin son okumasında kayıtlı sorgu yok.")
    sales = src.get("logo_aylik_kanal", []) + src.get("logo_son_fatura", [])
    crm = src.get("crm_kitaplar", []) + src.get("crm_emsal", []) + src.get("crm_baski", [])
    yeni = k.hesap("yeni", F_YENI, every)
    takip = k.hesap("takip", F_TAKIP, (sales + crm) or every)
    sinama = k.hesap("sinama", F_SINAMA, every)
    k.alanlar({
        "upcoming[]": yeni, "tracking[]": takip, "backtest": sinama,
        "meta.counts": k.hesap("sayim", F_SAYIM, every),
        "sources[]": k.hesap("okuma", "Kaynak başına satır sayısı son okumadan (Logo satışı yılların toplamı).", every),
        "status.durationMs": "hesap:okuma",
        "kpi.yayimlanacak": k.hesap("kpiYeni", "Yayımlanacak kitap = CRM'de ilk yayın tarihi verinin son tam ayından "
                                               "sonra olan, satışı olmayan, kapanmamış kitap sayısı.", crm or every),
        "kpi.takip": k.hesap("kpiTakip", "İlk satış takibinde = son 6 ayda lansmanı olan kitap sayısı.", sales or every),
        "kpi.kotumser": k.hesap("kpiKotumser", "Kötümserin altında = takipteki kitaplardan gerçekleşeni kötümser "
                                               "senaryonun bugüne düşen değerinin altında kalanların sayısı.", [takip]),
        "kpi.sapma": k.hesap("kpiSapma", "Tipik sapma (6 ay) = geçmiş sınamada ilk 6 ay tahmini ile gerçekleşen "
                                         "arasındaki mutlak oransal farkın ortancası.", [sinama]),
    })
    return k


def for_forecast(out: dict[str, Any], data: dict[str, Any], dbs: dict[str, Optional[str]], ran_at: Any,
                 free: bool = False) -> P.Kaynaklar:
    """`GET /forecast/{kod}` ve `POST /forecast` (serbest giriş): anlık tahmin, aynı veri kümesinden."""
    k = P.Kaynaklar(data_end=data.get("dataEnd"), as_of=ran_at)
    src = sources(k, data, dbs, ran_at)
    every = _all(src)
    if not every:
        raise P.ProvenanceError("Tahminin son okumasında kayıtlı sorgu yok.")
    sales = src.get("logo_aylik_kanal", []) or every
    crm_book = src.get("crm_kitaplar", []) or every
    fields: dict[str, str] = {
        "book": k.hesap("kitapElle", "Kitap özellikleri ekranda elle girildi (sayfa, fiyat); emsal havuzu CRM kitap "
                                     "kartlarından.", crm_book) if free else crm_book[0],
        "horizons": k.hesap("tahmin", F_YENI, every),
        "recommendation": k.hesap("oneri", F["İlk baskı önerisi"] + " Seçenekler: kural başına baskı adedi; geçmişte "
                                           "bu kuralla 6 ayda tükenen ve 12. ay elde kalan pay (geçmiş sınamadan).",
                                  every),
    }
    for h in (out.get("horizons") or {}):
        fields[f"horizons.{h}.channels[]"] = k.hesap("kanal", F_KANAL, sales)
        fields[f"horizons.{h}.analogs"] = k.hesap("emsal", F_EMSAL, every)
        fields[f"horizons.{h}.curve[]"] = k.hesap("egri", "Birikimli eğri = emsallerin ay ay satış payı × senaryo "
                                                          "değeri (kötümser, baz, iyimser, %10–%90 bant).", every)
        fields[f"horizons.{h}.scenarios[]"] = "hesap:tahmin"
    if out.get("author"):
        fields["author"] = k.hesap("yazar", F["Yazar geçmişi"] + " Kitap başına ilk 6 / 12 ay satışı Logo'dan (net adet).",
                                   sales)
    if out.get("actual"):
        fields["actual[]"] = k.hesap("gerceklesen", "Gerçekleşen = Logo'daki ay ay net satış adedi ve birikimli toplam.",
                                     sales)
    if out.get("revised"):
        fields["revised"] = k.hesap("revize", F["Revize tahmin"], every)
    k.alanlar(fields)
    return k


def for_decisions(engine: Any, stmt: Any) -> P.Kaynaklar:
    k = P.Kaynaklar()
    s = k.portal("ilkbaski.kararlar", "İlk baskı kararları", stmt, engine,
                 description="Önerilen ve karar verilen baskı adetleri, onaylar (semantic_first_print_decisions; ekrandan "
                             "girilir). Tahmin anının değerleri kararla birlikte saklanır.")
    k.alanlar({"items[]": s})
    return k


#: Rakam olmayan sayılar: zaman damgaları, ay dizinleri.
NOT_RAKAM = ("status.updatedAt", "status.nextRefreshAt", "status.refreshStartedAt", "cutoff", "launch")
