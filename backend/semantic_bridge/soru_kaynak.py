"""Soru cevabının ve saklı soru SQL'inin sorgu bilgisi (ortak sözleşme `provenance.py`, 2026-09-28).

Sohbet cevabı (`/ask`, `/ask/stream`), `/run_sql` (genel bakış kartları, pano kartı, planlı rapor, uyarı değeri) aynı
kalıptan geçer: köprü mantıksal SQL'i (katalog adları, dönem çözülmemiş) fiziksel SQL'e çevirip Logo'da ya da CRM'de
koşturur (`Runtime._physical`: yıl kopyası birleşimi, firma öneki, veri kapsamı süzgeci). Kullanıcıya gösterilen ve
kopyalanan metin **fiziksel** SQL'dir — SSMS'te aynı veritabanında koşturulunca ekrandaki rakamı verir. Mantıksal metin
yalnız açıklamada adıyla anılır, SQL olarak verilmez.

İki sunuculu cevapta (Logo + CRM) her parça kendi sunucusunda ayrı koşar ve köprü sonuçları ortak anahtarla birleştirir:
her parça ayrı sorgu, birleştirme «hesap» olarak yazılır.
"""
from __future__ import annotations

import os
from typing import Any, Iterable, Mapping, Optional

from semantic_bridge import provenance as P

CRM_FILE_DEFAULT = "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"

#: Soru cevabında rakam olmayan sayılar: iç ölçümler (kapı kararları, onarım sayısı, iç süre kırılımı).
CEVAP_NOT_RAKAM = ("semantic", "repairs", "neden", "timings", "latency_ms", "ageSec", "computedAt", "queryId")


def databases(logo_connection_file: Optional[str] = None) -> tuple[Optional[str], Optional[str]]:
    """(Logo veritabanı adı, CRM veritabanı adı) — bağlantı dosyasından YALNIZ veritabanı adı okunur."""
    logo = P.connection_database(logo_connection_file or os.environ.get("SEMANTIC_CONNECTION_FILE"))
    crm = P.connection_database(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", CRM_FILE_DEFAULT))
    return logo, crm


def connection_of(sql: str) -> str:
    """Köprünün bağlantı seçimiyle aynı kural (`Runtime._conn_for`): CRM şeması geçen SQL CRM'de koşar."""
    return "crm" if "timas_mscrm" in (sql or "").lower() else "logo"


def calisan(k: P.Kaynaklar, id: str, title: str, *, physical_sql: Optional[str], logo_db: Optional[str],
            crm_db: Optional[str], rows: Optional[int] = None, ms: Optional[int] = None, ran_at: Any = None,
            parts: Optional[Iterable[Mapping[str, Any]]] = None, description: str = "", period: Optional[str] = None,
            data_end: Any = None, connection: Optional[str] = None) -> str:
    """Köprünün gerçekten koşturduğu SQL'i kaydeder, alanlara verilecek kimliği döndürür.

    `parts` (iki sunuculu cevap): her biri {name, source: logo|crm, ms, sql}; her parça ayrı sorgu, birleştirme hesap.
    `physical_sql` yoksa (soru hiç koşmadıysa) kayıt açılmaz: `ProvenanceError` — `P.bagla` nedeni ekrana yazar."""
    plist = [p for p in (parts or []) if (p.get("sql") or "").strip()]
    if plist:
        ids = []
        for i, p in enumerate(plist, 1):
            src = "crm" if str(p.get("source") or "").lower() == "crm" else "logo"
            ids.append(k.sorgu(f"{id}.parca{i}", f"{title} · {p.get('name') or f'parça {i}'}", src, p["sql"],
                               database=crm_db if src == "crm" else logo_db, ms=p.get("ms"), ran_at=ran_at,
                               period=period, data_end=data_end,
                               description="İki sunuculu cevabın bu sunucuda koşan parçası."))
        return k.hesap(f"{id}.birlesim",
                       "Cevap iki sunucudan okunur: her parça kendi sunucusunda ayrı koşar, sonuçlar ortak anahtarla "
                       "birleştirilip toplanır. Aşağıdaki parçaların her biri kendi veritabanında kopyala-çalıştır.",
                       ids)
    if not (physical_sql or "").strip():
        raise P.ProvenanceError("Bu cevap için çalışan SQL yok (soru koşturulmadı).")
    conn = connection or connection_of(physical_sql)
    return k.sorgu(id, title, conn, physical_sql, database=crm_db if conn == "crm" else logo_db, rows=rows, ms=ms,
                   ran_at=ran_at, period=period, data_end=data_end,
                   description=description or "Köprünün veritabanında koşturduğu metin (dönem ve yıl kopyaları çözülmüş, "
                                              "veri kapsamı süzgeci eklenmiş); aynı veritabanında aynı sonucu verir.")


def for_answer(ans: Mapping[str, Any], logo_db: Optional[str], crm_db: Optional[str], *,
               title: str = "Sorunun cevabı") -> Optional[P.Kaynaklar]:
    """Soru cevabı (`Runtime.ask`) için kaynak kaydı. Yalnız SQL'li cevapta (TEXT_TO_SQL) kurulur; diğer cevap
    tiplerinde (metin, yetki reddi, veri yok) rakam yoktur → None."""
    if (ans or {}).get("type") != "TEXT_TO_SQL":
        return None
    phys = ans.get("physicalSql")
    parts = ans.get("dbParts") if ans.get("federated") else None
    if ans.get("federated") and not any((p or {}).get("sql") for p in (parts or [])):
        phys = None  # iki sunuculu planın metni SQL değil, parçalar ayrı koşar
    k = P.Kaynaklar(data_end=ans.get("dataEnd") if isinstance(ans.get("dataEnd"), str) else None,
                    as_of=ans.get("computedAt"))
    executed = ans.get("executed", True) is not False
    ref = calisan(k, "soru", title, physical_sql=phys, logo_db=logo_db, crm_db=crm_db,
                  rows=ans.get("totalRows") if executed else None, ms=ans.get("dbMs") if executed else None,
                  ran_at=ans.get("computedAt") if executed else None, parts=parts,
                  description=None if executed else "Soru çözüldü ama koşturulmadı; metin koşturulacak SQL'dir.")
    # Cevaptaki her rakam bu sorgudan (ya da iki sunuculu birleşimden) gelir: tablo, özet cümlesi, grafik, sayaçlar.
    k.alanlar({key: ref for key in ("records", "summary", "rowCount", "totalRows", "shownRows", "dbMs", "dbParts",
                                    "presentation", "widget", "comparison", "dataCoverage", "dataNotes", "columns",
                                    "dataEnd")})
    return k


def for_run(result: Mapping[str, Any], logo_db: Optional[str], crm_db: Optional[str], *,
            title: str = "Çalıştırılan sorgu") -> P.Kaynaklar:
    """`/run_sql` sonucu: köprünün koşturduğu fiziksel metin (önbellekten geldiyse ilk koşunun zamanı ve süresi)."""
    k = P.Kaynaklar(as_of=result.get("computedAt"))
    ref = calisan(k, "sorgu", title, physical_sql=result.get("physicalSql"), logo_db=logo_db, crm_db=crm_db,
                  rows=result.get("totalRows"), ms=result.get("dbMs"), ran_at=result.get("computedAt"),
                  description=("Önbellekten verildi; süre ve zaman ilk koşunundur. " if result.get("cached") else "")
                  + "Köprünün veritabanında koşturduğu metin (dönem ve yıl kopyaları çözülmüş).")
    k.alanlar({key: ref for key in ("records", "totalRows", "dbMs", "widget", "columns")})
    return k


#: `/run_sql` cevabında rakam olmayan sayılar.
RUN_NOT_RAKAM = ("computedAt", "ageSec", "truncated")
