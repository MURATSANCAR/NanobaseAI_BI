"""M29 İlk dağılım: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Dağılım bekleyen kitaplar, planlar, satırlar, benzer kitaplar, takip ve uyarılar portal tablolarındadır
(semantic_dist_*); gösterilen SQL uçta çalışan ifadenin kendisidir (`distribution.*_stmt`). Tabloları dolduran asıl
Logo/CRM sorguları okuma anında ÇALIŞAN metindir: liste yenilemesi `semantic_dist_meta` «logo» kaydında, öneri planın
temelinde (`basis_json.sorgular`), takip `track:<plan>` kaydında saklanır.
"""
from __future__ import annotations

import json
from typing import Any, Iterable, Optional

import sqlalchemy as sa

from semantic_bridge import distribution as D
from semantic_bridge import provenance as P

F_KITAP = ("Dağılım bekleyen kitap: son N günde Logo'da üretimden depoya gerçek girişi olan (ya da üretim kartında depo "
           "tarihi girilmiş) kitap; baskı adedi girişin ya da kartın adedi, stok = Logo stok bakiyesi (giriş − çıkış); plan "
           "adedi kitabın en son (arşivde olmayan) planının toplamı.")
F_SAYAC = ("Plan bekleyen = listede planı olmayan ya da planı taslak/onayda olan kitap; listedeki kitap = süzgeçten geçen "
           "satır; izlenen = onaydan sonraki takip haftaları içindeki onaylı planlar (ekranda sayılır).")
F_TAKIP = ("Takip: onay gününden itibaren hafta hafta cari başına Logo sevk (irsaliye), faturalanan ve iade adetleri; sevk "
           "oranı = sevk ÷ plan, iade oranı = iade ÷ faturalanan, net = faturalanan − iade. Değerlendirme günü = bugün ile "
           "Logo verisinin bittiği günden erken olanı.")
F_PLAN = ("Plan: dağıtılacak = satır adetleri toplamı; öneri = benzer kitapların ilk pencere net satışının cari payına göre "
          "dağıtım (en çok stok − rezerv; bütçe hedefi varsa ilk iki ayın hedefi); rezerv = baskı ya da stok × rezerv payı "
          "(ayar); kalan = stok − dağıtılacak − rezerv. Satış hedefi yürürlükteki bütçe planından.")
F_MATRIS = ("Bölge × kanal: satır adetlerinin bölge ve kanal kırılımında toplamı; bölge payı = bölge toplamı ÷ plan toplamı. "
            "Bölge carinin ilinden, kanal Logo satış kanalı kodundan.")
F_BENZER = ("Benzer kitap: aynı yazar/kitaplık/yayınevi adayları (Zeki AI ayıklaması açıksa benzerlik olasılığıyla); ilk N "
            "gün net = pencere satışı − iade; iade % = iade ÷ satış; müşteri = satış yapan cari sayısı; CRM dağılım "
            "siparişi = kitabın CRM'deki dağılım siparişleri.")
F_SATIR = ("Müşteri satırı: pay = carinin benzer kitaplardaki ağırlıklı net payı; benzerlerde net ve iade oranı aynı "
           "pencereden; adet = öneri (ya da elle düzeltme); takip sevk/fatura/iade onaydan sonra Logo'dan.")
F_UYARI = ("Uyarılar: plan yok (depoya girdi, plan yok), sevk edilmedi (onaydan N iş günü sonra sevk yok), hiç satmadı (N "
           "günde bölgede net satış yok), tükeniyor (faturalanan − iade ≥ sevkin payı). Sayaç = açık ve bilgi durumundaki "
           "uyarı sayısı; liste sayfalıdır (toplam ayrı).")


class _Ctx:
    def __init__(self, engine: Any, tenant: str, logo_db: Optional[str], crm_db: Optional[str]):
        self.engine, self.tenant, self.dbs = engine, tenant, {"logo": logo_db, "crm": crm_db}
        self.k = P.Kaynaklar(data_end=D.data_end(engine, tenant))

    def portal(self, sid: str, title: str, stmt: Any, desc: str, origin: Iterable[str] = ()) -> str:
        if sid in self.k.sources:
            return sid
        return self.k.portal(sid, title, stmt, self.engine, description=desc, origin=origin)

    def reads(self, prefix: str, reads: list[dict[str, Any]], desc: str, ran_at: Any = None) -> list[str]:
        ids, seen = [], set()
        for q in reads or []:
            sql = q.get("sql") or ""
            if not sql or sql in seen:
                continue
            seen.add(sql)
            conn = q.get("conn") if q.get("conn") in ("logo", "crm") else "logo"
            try:
                ids.append(self.k.sorgu(f"{prefix}.{len(ids) + 1}", f"{'Logo' if conn == 'logo' else 'CRM'} okuması "
                                        f"{len(ids) + 1}", conn, sql, database=self.dbs.get(conn), rows=q.get("rows"),
                                        ms=q.get("dbMs"), ran_at=q.get("at") or ran_at, description=desc))
            except P.ProvenanceError:
                continue
        return ids

    def books(self) -> str:
        m = D.meta_get(self.engine, self.tenant, "logo")
        origin = self.reads("dagilim.yenileme", m.get("sorgular") or [], "Liste yenilemesinde çalıştı (depo girişleri, ilk "
                                                                         "giriş, stok, veri sonu).", m.get("_at"))
        meta = self.portal("dagilim.meta", "Liste yenileme kaydı", D.meta_stmt(self.tenant, "logo"),
                           "Veri sonu, depo sonu, okunan kitap sayısı ve okuma sorguları.", origin=origin)
        return self.portal("dagilim.kitaplar", "Dağılım bekleyen kitaplar", D.books_stmt(self.tenant),
                           "Kitap başına depo girişi, baskı adedi, stok bakiyesi (yenilemede yazılır).", origin=[meta])

    def track(self, plan_ids: list[str]) -> list[str]:
        ids = []
        for pid in plan_ids:
            m = D.meta_get(self.engine, self.tenant, f"track:{pid}")
            ids += self.reads(f"dagilim.takip.{pid[:8]}", m.get("sorgular") or [], "Takip okuması (onaydan sonraki "
                                                                                     "haftalar, cari × hafta).", m.get("_at"))
        return ids

    def plan_reads(self, plan_id: str) -> list[str]:
        with self.engine.connect() as c:
            r = c.execute(D.plan_stmt(self.tenant, plan_id)).first()
        basis = json.loads(r.basis_json or "{}") if r is not None else {}
        return self.reads(f"dagilim.oneri.{plan_id[:8]}", basis.get("sorgular") or [],
                          "Öneri kurulurken çalıştı (benzer kitap satışı, cari kartları, CRM dağılım siparişleri).",
                          r.created_at if r is not None else None)


def _dbs(logo_db, crm_db):
    return logo_db, crm_db


def for_books(engine: Any, tenant: str, out: dict[str, Any], logo_db: Optional[str], crm_db: Optional[str]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, logo_db, crm_db)
    k = x.k
    books = x.books()
    plans = x.portal("dagilim.planlar", "Kitapların güncel planları", D.open_plans_stmt(tenant), "Arşivde olmayan planlar.")
    tracked = [t.get("planId") for t in out.get("izlenen") or [] if t.get("planId")]
    tr = x.portal("dagilim.takipTablosu", "Takip satırları (izlenen planlar)", D.tracking_stmt(tracked),
                  "Cari × hafta sevk, faturalanan, iade.", origin=x.track(tracked))
    lines = x.portal("dagilim.satirlarIzlenen", "İzlenen planların satırları",
                     sa.select(D.LINES).where(D.LINES.c.plan_id.in_(tracked or [""]), D.LINES.c.adet > 0),
                     "Adetli müşteri satırları (plan toplamı).")
    liste = k.hesap("liste", F_KITAP, [books, plans])
    k.alanlar({"items[]": liste, "izlenen[]": k.hesap("izlenen", F_TAKIP, [tr, lines, plans]),
               "pencereGun": k.hesap("pencere", "Liste penceresi (gün) ayardır (Yönetim).", [books]),
               "sayac.bekleyen": k.hesap("sayac", F_SAYAC, [books, plans, tr]), "sayac.liste": "hesap:sayac",
               "sayac.izlenen": "hesap:sayac"})
    return k


def for_plan(engine: Any, tenant: str, plan_id: str, out: dict[str, Any], bmt: Optional[str], logo_db: Optional[str],
             crm_db: Optional[str]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, logo_db, crm_db)
    k = x.k
    books = x.books()
    oneri = x.plan_reads(plan_id)
    plan = x.portal("dagilim.plan", "Plan kaydı", D.plan_stmt(tenant, plan_id),
                    "Toplam, öneri toplamı, rezerv, hedef ve öneri temeli.", origin=oneri)
    lines = x.portal("dagilim.satirlar", "Plan satırları" + (" (yalnız kendi carileriniz)" if bmt else ""),
                     D.lines_stmt(plan_id, bmt), "Bölge, kanal, adet, öneri.")
    comps = x.portal("dagilim.benzerler", "Benzer kitaplar", D.comps_stmt(plan_id),
                     "Pencere satışı, iade, müşteri, CRM dağılım siparişi, benzerlik.", origin=oneri)
    base = k.hesap("plan", F_PLAN, [plan, lines, books])
    fields = {key: base for key, v in out.items() if key not in ("matris", "benzerler", "kaynaklar")
              and P.numeric_paths({key: v})}
    fields.update({"matris": k.hesap("matris", F_MATRIS, [lines]), "benzerler[]": k.hesap("benzer", F_BENZER, [comps]),
                   "hedef": k.hesap("hedef", "Satış hedefi: yürürlükteki bütçe planında kitabın yıllık hedefi ve depo "
                                             "girişinden itibaren iki ayın adedi (aylık dağılımdan).", [plan]),
                   "guncelStok": k.hesap("stok", "Güncel stok: dağılım listesinin Logo stok bakiyesi; yoksa planın stoku; o da "
                                                 "yoksa baskı adedi.", [books, plan])})
    k.alanlar(fields)
    return k


def for_lines(engine: Any, tenant: str, plan_id: str, out: dict[str, Any], bmt: Optional[str], logo_db: Optional[str],
              crm_db: Optional[str]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, logo_db, crm_db)
    lines = x.portal("dagilim.satirlar", "Plan satırları (süzgeçle)", D.lines_stmt(plan_id, bmt),
                     "Müşteri satırları; süzgeç ve arama uçta, sayfa başına 100 satır (toplam ayrı).",
                     origin=x.plan_reads(plan_id))
    tr = x.portal("dagilim.takipTablosu", "Takip satırları", D.tracking_stmt([plan_id]), "Cari başına sevk, fatura, iade.",
                  origin=x.track([plan_id]))
    ref = x.k.hesap("satir", F_SATIR, [lines, tr])
    x.k.alanlar({"items[]": ref, "total": ref})
    return x.k


def for_plans(engine: Any, tenant: str, code: str) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, None, None)
    s = x.portal("dagilim.kitapPlanlari", "Kitabın planları", D.book_plans_stmt(tenant, code), "Bütün sürümler.")
    x.k.alanlar({"items[]": x.k.hesap("planlar", F_PLAN, [s])})
    return x.k


def for_tracking(engine: Any, tenant: str, out: dict[str, Any], bmt: Optional[str], logo_db: Optional[str],
                 crm_db: Optional[str]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, logo_db, crm_db)
    ids = [s.get("planId") for s in out.get("items") or [] if s.get("planId")]
    plans = x.portal("dagilim.onayli", "Onaylı planlar", D.approved_plans_stmt(tenant), "İzlenen planlar.")
    tr = x.portal("dagilim.takipTablosu", "Takip satırları", D.tracking_stmt(ids), "Cari × hafta sevk, fatura, iade.",
                  origin=x.track(ids))
    lines = x.portal("dagilim.satirlarIzlenen", "Planların satırları",
                     _lines_in(ids, bmt), "Müşteri satırları (plan adedi, bölge).")
    ref = x.k.hesap("takip", F_TAKIP + " Bölge ve müşteri tabloları aynı satırların kırılımıdır.", [plans, tr, lines])
    x.k.alanlar({"items[]": ref, "takipHafta": ref})
    return x.k


def _lines_in(ids: list[str], bmt: Optional[str]):
    return D._visible(sa.select(D.LINES).where(D.LINES.c.plan_id.in_(ids or [""])), bmt)


def for_my_region(engine: Any, tenant: str, out: dict[str, Any], user: Optional[str], logo_db: Optional[str],
                  crm_db: Optional[str]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, logo_db, crm_db)
    ids = [s.get("planId") for s in out.get("items") or [] if s.get("planId")]
    plans = x.portal("dagilim.onayli", "Onaylı planlar", D.approved_plans_stmt(tenant), "Takip penceresindeki planlar.")
    lines = x.portal("dagilim.bolgem", "Carilerinize düşen satırlar", _lines_in(ids, user), "Adetli satırlar.")
    tr = x.portal("dagilim.takipTablosu", "Takip satırları", D.tracking_stmt(ids), "Sevk, fatura, iade.", origin=x.track(ids))
    x.k.alanlar({"items[]": x.k.hesap("bolgem", "Bölgem: onaylı planlarda carilerinize düşen adet, müşteri ve sevk. "
                                                + F_TAKIP, [plans, lines, tr])})
    return x.k


def for_alerts(engine: Any, tenant: str, out: dict[str, Any], *, durum: str, tur: str, bmt: Optional[str],
               page: int) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, None, None)
    s = x.portal("dagilim.uyarilar", "Uyarılar (sayfa)", D.alerts_stmt(tenant, durum=durum, tur=tur, bmt=bmt, page=page),
                 "Uyarı kayıtları; günlük değerlendirme yazar.")
    t = x.portal("dagilim.uyariSayilari", "Açık uyarılar (tür başına sayım)", D.alerts_stmt(tenant, bmt=None),
                 "Açık ve bilgi durumundaki uyarılar.")
    ref = x.k.hesap("uyari", F_UYARI, [s, t])
    x.k.alanlar({"items[]": ref, "total": ref, "sayilar": ref})
    return x.k


NOT_RAKAM = ("page", "pageSize", "surum", "items[].surum", "items[].no", "items[].plan.surum", "baskiNo",
             "items[].baskiNo", "items[].hafta", "revisionOf")
