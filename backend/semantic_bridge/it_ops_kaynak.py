"""Sistem durumu: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Halka, olay, iş ve kapasite sayıları portal tablolarından (semantic_itops_*, sl_llm_job, sl_query_log) okunur; uç
çalışırken koşan okumalar `sorgu_izi` ile yakalanır. Logo ve CRM «Veri sonu» denetim turunun o bağlantıda koşturduğu
SQL'den gelir; metin denetim kaydında saklanır (`semantic_itops_checks.sql_text`). Sunucu zamanlayıcıları ve disk
ölçümünün SQL'i yoktur; kaynağın adıyla yazılır.
"""
from __future__ import annotations

from typing import Any, Optional

import sqlalchemy as sa

from semantic_bridge import it_ops as I
from semantic_bridge import provenance as P
from semantic_bridge import sorgu_izi as IZ

F_DURUM = ("Halka durumu: son denetim, son başarılı denetim ve gecikme (ms) denetim kayıtlarından; «N dk'dır kopuk» açık "
           "kopma olayının açılışından bu yana geçen süre; özet bandı halkaların durumundan; sekme rozetleri açık olay ve "
           "son koşusu hatalı zamanlanmış iş sayısı.")
F_VERI_SONU = ("Veri sonu: denetim turunun bu bağlantıda koşturduğu SQL'in döndürdüğü son kayıt anı (Logo: iptal "
               "edilmemiş son fatura günü; CRM: kitap kartının son değişikliği). Tur 5 dakikada bir koşar.")
F_OLAY = ("Olaylar: son 30 günde halka başına kesinti süresi = kopma olaylarının açılış–kapanış sürelerinin toplamı (açık "
          "olay için şimdiye kadar); kopma sayısı = olay sayısı; olay ayrıntısında denetimlerin gecikmesi (ms).")
F_IS = ("Zamanlanmış işler: sonuç ve hatalı sayısı işin son koşularından; kayıt sayısı işin kendi tablosundaki satırlar "
        "(planlı rapor, uyarı, pano kartı…); son ve sıradaki koşu sunucu zamanlayıcısından.")
F_SURUM = "Kurulumlar: kurulum betiğinin yazdığı kayıt; Mac artığı = kurulan ağaçtaki ._* dosya sayısı."
F_KAPASITE = ("Kapasite: modül başına iş sayısı, sırada bekleme ve model süresi medyanı (p50) model işi kayıtlarından; soru "
              "sayısı, hata ve gecikme medyanı soru kayıtlarından; disk kullanımı sunucunun anlık ölçümü.")
F_BANNER = "Kesinti şeridi: açık kopma olaylarının halkası ve açılış anı; dakika = şimdi − açılış."

SUNUCU_DIS = "Sunucu zamanlayıcıları ve disk ölçümü (anlık okuma)"


def last_sql_stmt(tenant: str, ring: str) -> Any:
    """Halkanın veri sonunu okuyan son SQL (denetim kaydında saklı)."""
    C = I.CHECKS
    return (sa.select(C.c.sql_text, C.c.at, C.c.latency_ms, C.c.data_end)
            .where(C.c.tenant_id == tenant, C.c.ring == ring, C.c.sql_text.isnot(None))
            .order_by(C.c.at.desc(), C.c.id.desc()).limit(1))


def _data_end_sources(k: P.Kaynaklar, engine: Any, tenant: str, logo_db: Optional[str],
                      crm_db: Optional[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    with engine.connect() as c:
        for ring, conn, db in (("logo", "logo", logo_db), ("crm", "crm", crm_db)):
            row = c.execute(last_sql_stmt(tenant, ring)).mappings().first()
            if row and row["sql_text"]:
                out[ring] = k.sorgu(f"{conn}.itops.verisonu", f"{'Logo' if conn == 'logo' else 'CRM'} veri sonu",
                                    conn, row["sql_text"], database=db, ms=row["latency_ms"], ran_at=row["at"],
                                    data_end=row["data_end"],
                                    description="Denetim turunun bu bağlantıda son koşturduğu metin.")
    return out


def for_status(engine: Any, tenant: str, ran: list, out: dict[str, Any], logo_db: Optional[str],
               crm_db: Optional[str]) -> P.Kaynaklar:
    ends: dict[str, str] = {}

    def extra(k: P.Kaynaklar) -> list[str]:
        ends.update(_data_end_sources(k, engine, tenant, logo_db, crm_db))
        return [k.hesap("sunucu", "Zamanlayıcı son/sıradaki koşu zamanları sunucudan okunur.", dis=SUNUCU_DIS)]

    def fields(k: P.Kaynaklar, ref: str) -> dict[str, str]:
        f = {}
        for ring in ("logo", "crm"):
            base = [i for i in k.sources if i.startswith("portal.itops")]
            ins = base + ([ends[ring]] if ring in ends else [])
            text = F_VERI_SONU + ("" if ring in ends else " Bu halkanın SQL'i bir sonraki denetim turunda yazılır.")
            f[f"rings[]:{ring}"] = k.hesap(f"verisonu.{ring}", text, ins)
        f["rings"] = ref
        return f

    return IZ.kaynak(engine, ran, out, prefix="portal.itops.durum", title="Sistem durumu", text=F_DURUM, extra=extra,
                     fields=fields)


def simple(engine: Any, ran: list, out: dict[str, Any], *, prefix: str, title: str, text: str, skip: tuple = (),
           dis: bool = False) -> P.Kaynaklar:
    extra = (lambda k: [k.hesap("sunucu", "Anlık sunucu ölçümü.", dis=SUNUCU_DIS)]) if dis else None
    return IZ.kaynak(engine, ran, out, prefix=prefix, title=title, text=text, skip=skip, extra=extra)
