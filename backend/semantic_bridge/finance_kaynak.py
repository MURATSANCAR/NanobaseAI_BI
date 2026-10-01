"""M45 Finansal raporlar: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Rakamların çoğu gece/saatlik okumanın yazdığı portal tablolarından (semantic_finance_*) gelir; gösterilen portal SQL'i
uçta çalıştırılan ifadenin kendisidir (`finance.*_stmt`), tabloyu dolduran asıl Logo/CRM sorgusu `origin`'dir (hangi
firma kopyası, ne zaman okundu). Fiş satırları (`/entries`) canlı okumadır; çalışan SQL aynen verilir.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

from semantic_bridge import finance as F
from semantic_bridge import finance_sources as src
from semantic_bridge import provenance as P

F_NET = ("Net satış = Σ VATMATRAH (satış: TRCODE 7, 8, 9) − Σ VATMATRAH (iade: TRCODE 2, 3); yalnız faturalı "
         "(INVOICEREF ≠ 0) malzeme satırları (LINETYPE 0), iptaller hariç; dönem fatura tarihi. İskonto öncesi = "
         "Σ TOTAL.")
F_BRUT = ("Brüt kâr = maliyeti işlenmiş satırların net satışı − Σ AMOUNT × OUTCOST (OUTCOST ≠ 0); oran = brüt kâr ÷ "
          "maliyetli net satış. Maliyeti işlenmemiş satış marja katılmaz; payı kartın notunda.")
F_DEGISIM = "Değişim = (bu yıl − geçen yılın aynı dönemi) ÷ geçen yılın aynı dönemi."
F_MUHASEBE = ("Gelir tablosu satırı = eşlenen hesapların Σ (alacak − borç) kâr etkisi; yalnız «dahil» kuralındaki "
              "muhasebe satırları (yansıtma ve kapanış fişleri ayrı sayılır, dışarıda kalan tutar ayrıca yazılır). "
              "Hesap → satır eşlemesi onaylı eşleme, yoksa öneri, yoksa hesap planı kuralı; ara toplamlar formülle.")
F_FAALIYET = ("Faaliyet giderleri = Ar-Ge + pazarlama-satış-dağıtım + genel yönetim satırları (7 ile başlayan "
              "hesaplar, eşlemeyle), yıl başından veri sonuna kadar; işareti ekranda artı gösterilir.")
F_POZISYON = ("Kasa ve banka = 100 + 102 hesap gruplarının Σ borç − Σ alacak bakiyesi (yıl açılış fişi dahil) veri "
              "son gününe kadar.")
F_VADESI = ("Vadesi geçmiş alacak = müşteri (120) açık kalemlerinin vadesi veri son gününden önce olanların toplamı. "
            "Logo'da ödeme kapama kullanılmadığı için carinin net bakiyesi en yeni vade satırlarından geriye dağıtılır "
            "(FIFO yaklaşımı).")
F_NAKIT = ("13 haftalık nakit: açılış = kasa + banka bakiyesi; her kalem vadesine göre haftasına yazılır (alacak ve "
           "satıcı borcu FIFO yaklaşımı, çek/senet vade, CRM'de onay bekleyen tahsilat, sözleşme ödeme takvimi, vergi "
           "takvimi; bütçe temposu isteğe bağlı). Hafta neti = giriş − çıkış; kapanış = açılış + net; eksi kapanış açık.")
F_NAKIT_GECMIS = ("Geçmiş tahmin ↔ gerçekleşen: tahminin haftalık neti ile o haftanın kasa + banka (100, 102) giriş − "
                  "çıkışı (açılış fişi hariç); sapma = gerçekleşen − tahmin; ortalama mutlak sapma.")
F_MIZAN = "Mizan denkliği: seçili ayların bütün hesaplarında |Σ borç − Σ alacak| < 0,01 ₺ ise denk."
F_MUTABAKAT = ("Mutabakat farkı = muhasebedeki net satış (600–612, eşlemeyle) − fatura satırlarından net satış "
               "(VATMATRAH kuralı).")
F_KAPSAM = ("Maliyet kapsamı: maliyetli pay = (net − maliyeti işlenmemiş net) ÷ net; maliyetsiz satır sayısı ve tutarı "
            "ayrıca.")
F_KURAL = "Kural dışı tutarlar: yansıtma ve kapanış kuralına düşen muhasebe satırlarının hesap sayısı, borç ve alacağı."
F_ESLEME = ("Eşleme durumu: onaysız tutar = eşlemesi onaylanmamış hesapların kâr etkisi (mutlak); eşlenmemiş = hiçbir "
            "satıra eşlenmemiş hesap sayısı ve tutarı.")
F_KARLILIK = ("Kârlılık: net = Σ VATMATRAH; iskonto = iskonto öncesi (Σ TOTAL) − net; kesin katkı = maliyetli net − Logo "
              "maliyeti (Σ AMOUNT × OUTCOST); yaklaşık katkı = (net − maliyeti bilinmeyen net) − Logo maliyeti − "
              "fiyatlamanın birim maliyetiyle doldurulan maliyet − telif (yaklaşık, yürürlükteki sözleşme oranıyla); "
              "marj = katkı ÷ ilgili net; kapsam = maliyeti bilinen net ÷ net.")
F_BUTCE = ("Bütçe sütunu: yürürlükteki planın net satış hedefi × seçili ayların taban dönemi payı; departman gider "
           "bütçesi seçili ayların toplamı, hesap eşlemesiyle gelir tablosu satırına (gider eksi).")
F_VERGI = "Vergi takvimi elle girilir (beyan, dönem, son gün, tahmini tutar); kalan gün = son gün − bugün."
F_DIKKAT = ("«Bu ay dikkat»: açık bütçe sapmaları (en büyük 3), nakit açığı olan ilk hafta, geciken ve 14 gün içindeki "
            "vergi beyanları.")


class _Ctx:
    """Bir cevap için ortak kaynak kurucusu: yıl başına Logo kaynakları bir kez eklenir."""

    def __init__(self, engine: Any, tenant: str, logo_db: Optional[str], crm_db: Optional[str] = None):
        self.engine, self.tenant, self.logo_db, self.crm_db = engine, tenant, logo_db, crm_db
        self.k = P.Kaynaklar(data_end=F.data_end(engine))

    def firm(self, y: int) -> Optional[str]:
        return (F.meta_get(self.engine, f"ledger:{y}").get("firm") or F.meta_get(self.engine, f"trial:{y}").get("firm"))

    def _logo(self, sid: str, title: str, sql: str, y: int, firm: str, desc: str, **kw: Any) -> str:
        if sid in self.k.sources:
            return sid
        led = F.meta_get(self.engine, f"ledger:{y}")
        return self.k.sorgu(sid, title, "logo", sql, database=self.logo_db, ran_at=led.get("_at"),
                            period=f"{y} · Logo firma {firm}", description=desc, **kw)

    def logo_year(self, y: int, what: str) -> Optional[str]:
        firm = self.firm(y)
        if not firm:
            return None
        led = F.meta_get(self.engine, f"ledger:{y}")
        if what == "muhasebe":
            return self._logo(f"logo.fin.muhasebe.{y}", f"Logo muhasebe satırları · {y}", src.account_actuals_sql(firm, y), y,
                              firm, "Hesap × masraf merkezi × ay borç/alacak ve kuralı (dahil / yansıtma / kapanış); "
                                    "semantic_finance_account_actuals tablosuna yazılır.", ms=led.get("muhasebeMs"))
        if what == "mizan":
            return self._logo(f"logo.fin.mizan.{y}", f"Logo mizan · {y}", src.trial_sql(firm, y), y, firm,
                              "Ay başına bütün hesapların borç ve alacak toplamı (mizan denkliği).")
        if what == "satis":
            return self._logo(f"logo.fin.satis.{y}", f"Logo satış satırları · {y}", src.sales_month_sql(firm, y), y, firm,
                              "Ay başına net satış, iskonto öncesi, maliyet, maliyetsiz satırlar; "
                              "semantic_finance_sales_month tablosuna yazılır.", rows=led.get("satisAy"))
        if what == "kitapKanal":
            return self._logo(f"logo.fin.kitapKanal.{y}", f"Logo kitap × kanal satışları · {y}", src.profit_items_sql(firm, y),
                              y, firm, "Kitap × kanal × ay ölçüleri; semantic_finance_profit_items tablosuna yazılır.")
        if what == "cari":
            a = self._logo(f"logo.fin.cari.{y}", f"Logo cari × kanal satışları · {y}", src.profit_clients_sql(firm, y), y,
                           firm, "Cari × kanal × ay ölçüleri; semantic_finance_profit_clients tablosuna yazılır.")
            self._logo(f"logo.fin.cariMaliyetsiz.{y}", f"Logo maliyetsiz cari satırları · {y}",
                       src.client_uncosted_sql(firm, y), y, firm,
                       "Maliyeti işlenmemiş cari satırları; birim maliyet fiyatlamadan doldurulur (yaklaşık).")
            return a
        if what == "banka":
            return self._logo(f"logo.fin.banka.{y}", f"Logo kasa ve banka hareketleri · {y}", src.bank_daily_sql(firm, y),
                              y, firm, "Kasa + banka (100, 102) gün gün giriş ve çıkış, açılış fişi hariç.")
        if what == "pozisyon":
            pos = F.meta_get(self.engine, f"position:{y}")
            if not pos.get("asof"):
                return None
            return self._logo(f"logo.fin.pozisyon.{y}", f"Logo hesap grubu bakiyeleri · {pos['asof']}",
                              src.position_sql(firm, y, date.fromisoformat(pos["asof"])), y, firm,
                              "Kasa, banka, çek, alacak, borç gruplarının bakiyesi (yıl açılış fişi dahil).")
        raise ValueError(what)

    def logo_years(self, years: Iterable[int], what: str) -> list[str]:
        return [x for x in (self.logo_year(y, what) for y in sorted(set(years))) if x]

    def portal(self, sid: str, title: str, stmt: Any, desc: str, origin: Iterable[str] = ()) -> str:
        if sid in self.k.sources:
            return sid
        return self.k.portal(sid, title, stmt, self.engine, description=desc, origin=origin)

    def esleme(self) -> list[str]:
        return [
            self.portal("portal.fin.satirlar", "Gelir tablosu satırları",
                        sa.select(F.LINES).where(F.LINES.c.tenant_id == self.tenant).order_by(F.LINES.c.sira),
                        "Satır kodu, adı, sırası, işareti ve ara toplam formülleri (semantic_finance_lines)."),
            self.portal("portal.fin.esleme", "Hesap → satır eşlemesi",
                        sa.select(F.ACCOUNT_MAP).where(F.ACCOUNT_MAP.c.tenant_id == self.tenant),
                        "Onaylı, dışlanan ve önerilen eşlemeler (semantic_finance_account_map)."),
        ]

    def ledger(self, sid: str, months: list[tuple[int, int]], kural: str = "dahil", label: str = "") -> str:
        years = {y for y, _ in months}
        return self.portal(sid, f"Muhasebe toplamları{(' · ' + label) if label else ''} ({kural})",
                           F.account_totals_stmt(months, kural),
                           f"Hesap başına borç, alacak ve satır sayısı; {F.period_label(months)}.",
                           origin=self.logo_years(years, "muhasebe"))

    def sales(self, sid: str, months: list[tuple[int, int]], label: str = "") -> str:
        years = {y for y, _ in months}
        return self.portal(sid, f"Satış toplamları{(' · ' + label) if label else ''}", F.sales_totals_stmt(months),
                           f"Net, iskonto öncesi, maliyet, maliyetsiz satırlar; {F.period_label(months)}.",
                           origin=self.logo_years(years, "satis"))

    def prev_sales(self, y: int) -> Optional[str]:
        prev = F.meta_get(self.engine, f"sales_prev:{y}")
        end = F.data_end(self.engine)
        firm = prev.get("firm") or self.firm(y - 1)
        if not prev or not end or not firm:
            return None
        start, stop = date(y - 1, 1, 1), F._same_day_last_year(end) + timedelta(days=1)
        return self._logo(f"logo.fin.oncekiYil.{y}", f"Logo satış · geçen yılın aynı dönemi", src.sales_period_sql(firm, start, stop),
                          y - 1, firm, "Geçen yıl 1 Ocak'tan veri son gününün geçen yılki karşılığına kadar satış ölçüleri.")

    def cash_sources(self, run: Optional[dict[str, Any]]) -> dict[str, str]:
        """Nakit tablosunu kuran okumalar (kalem → kaynak)."""
        out: dict[str, str] = {}
        cr = F.meta_get(self.engine, "cash_run")
        asof = date.fromisoformat(cr["asof"]) if cr.get("asof") else F.data_end(self.engine)
        if asof is None:
            return out
        firm = self.firm(asof.year)
        if firm:
            desc = "Nakit tablosu kurulurken okundu; sonuç semantic_finance_cash_lines tablosunda."
            kw = {"period": f"{asof.isoformat()} · Logo firma {firm}", "ran_at": cr.get("_at")}
            out["pozisyon"] = self.k.sorgu("logo.nakit.pozisyon", "Açılış: hesap grubu bakiyeleri", "logo",
                                           src.position_sql(firm, asof.year, asof), database=self.logo_db,
                                           description=desc, **kw)
            out["alacak"] = self.k.sorgu("logo.nakit.alacak", "Müşteri alacakları (FIFO vade)", "logo",
                                         src.fifo_due_sql(firm, asof.year, asof, payable=False), database=self.logo_db,
                                         description=desc, **kw)
            out["satici"] = self.k.sorgu("logo.nakit.satici", "Satıcı borçları (FIFO vade)", "logo",
                                         src.fifo_due_sql(firm, asof.year, asof, payable=True), database=self.logo_db,
                                         description=desc, **kw)
            out["cek-giris"] = out["cek-cikis"] = self.k.sorgu(
                "logo.nakit.cek", "Çek ve senet kartları", "logo", src.cheques_sql(firm), database=self.logo_db,
                description=desc + " Giriş/çıkış ayrımı belge türü ve durum koduyla (ayar).", **kw)
        out["crm-tahsilat"] = self.k.sorgu("crm.nakit.tahsilat", "CRM'de onay bekleyen tahsilat", "crm",
                                           src.crm_pending_collections_sql(), database=self.crm_db,
                                           ran_at=cr.get("_at"), description="Logo'ya henüz düşmemiş tahsilat kayıtları.")
        try:
            from semantic_bridge import contracts as C

            out["telif"] = self.portal(
                "portal.nakit.telif", "Sözleşme ödeme takvimi",
                (sa.select(C.PAYMENTS, C.RECORDS.c.no, C.RECORDS.c.terms, C.RECORDS.c.crm_id)
                 .join(C.RECORDS, C.RECORDS.c.id == C.PAYMENTS.c.contract_id)
                 .where(C.PAYMENTS.c.tenant_id == self.tenant, C.PAYMENTS.c.status == "planlandi")
                 .order_by(sa.func.coalesce(C.PAYMENTS.c.due_on, "9999"), C.PAYMENTS.c.created_at)),
                "Planlanmış telif, avans ve hakediş ödemeleri (sözleşmeler modülü).")
        except Exception:  # noqa: BLE001 — sözleşme modülü yoksa kalem de yoktur
            pass
        out["vergi"] = self.portal("portal.nakit.vergi", "Vergi takvimi", F.tax_stmt(self.tenant),
                                   "Elle girilen beyanlar; verilmemiş olanların tahmini tutarı.")
        try:
            from semantic_bridge import budget as B

            ids = []
            for y in (asof.year, asof.year + 1):
                ids.append(self.portal(f"portal.nakit.butcePlan.{y}", f"Yürürlükteki bütçe planı · {y}",
                                       B.approved_stmt(self.tenant, y), "Onaylı plan (varsa)."))
            with self.engine.connect() as c:
                rows = [B._approved(c, self.tenant, y) for y in (asof.year, asof.year + 1)]
            for r in rows:
                if r is not None:
                    ids.append(self.portal(f"portal.nakit.butce.{r.year}", f"Departman bütçesi · {r.year}",
                                           B.depts_stmt(r.id), "Aylık gider bütçesi; ayın ilk gününe yazılır."))
            out["butce"] = ids[-1]
        except Exception:  # noqa: BLE001
            pass
        out["run"] = self.portal("portal.nakit.tablo", "Son nakit tablosu", F.cash_run_stmt(self.tenant),
                                 "En son kurulan tablo ve parametreleri (açılış, pozisyon, vadesi geçmiş).",
                                 origin=[v for key, v in out.items() if key != "run"])
        if run and run.get("id"):
            out["lines"] = self.portal("portal.nakit.kalemler", "Nakit tablosu kalemleri", F.cash_lines_stmt(run["id"]),
                                       "Kalem × hafta tutarları.", origin=[out["run"]])
        return out


# ------------------------------------------------------------------ uçlar


def for_summary(engine: Any, tenant: str, out: dict[str, Any], logo_db: Optional[str], crm_db: Optional[str]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, logo_db, crm_db)
    k = x.k
    end = F.data_end(engine)
    fields: dict[str, str] = {}
    if end:
        y = end.year
        ytd = [(y, m) for m in range(1, end.month + 1)]
        sales = x.sales("portal.fin.satisYbd", ytd, "yıl başından")
        prev = x.prev_sales(y)
        every: list[str] = [sales]
        for card in out.get("cards") or []:
            cid = card.get("id")
            if cid == "net-satis":
                ref = k.hesap("kart:net-satis", F_NET + " " + F_DEGISIM, [sales] + ([prev] if prev else []))
            elif cid == "brut-kar":
                ref = k.hesap("kart:brut-kar", F_BRUT, [sales])
            elif cid == "faaliyet":
                led = x.ledger("portal.fin.muhasebeYbd", ytd, label="yıl başından")
                ref = k.hesap("kart:faaliyet", F_FAALIYET + " " + F_MUHASEBE, [led] + x.esleme())
                every.append(led)
            elif cid == "nakit":
                pos = x.logo_year(y, "pozisyon")
                if not pos:
                    continue
                ref = k.hesap("kart:nakit", F_POZISYON, [pos])
                every.append(pos)
            elif cid == "vadesi-gecmis":
                cs = x.cash_sources(None)
                ref = k.hesap("kart:vadesi-gecmis", F_VADESI, [s for s in (cs.get("alacak"), cs.get("run")) if s])
                every.append(cs["run"])
            elif cid == "butce":
                from semantic_bridge import budget_kaynak as BK
                from semantic_bridge import budget as B

                with engine.connect() as c:
                    row = B._approved(c, tenant, y)
                if row is None:
                    plan = x.portal("portal.butce.onayli", f"Yürürlükteki bütçe planı · {y}", B.approved_stmt(tenant, y),
                                    "Bu yıl için onaylı plan yok.")
                    ref = k.hesap("kart:butce", "Bu yıl için yürürlükte bütçe planı yok.", [plan])
                else:
                    bf = BK.tracking_fields(k, engine, tenant, row.id, y, logo_db)
                    ref = k.hesap("kart:butce", "Satış hedefine göre = şirket satışının gerçekleşen ÷ bugüne beklenen "
                                                "oranı (M46 bütçe izlemesiyle aynı). Not: gider bütçesi kullanımı.",
                                  [bf["sirket"], bf["gider"]])
            else:
                continue
            fields[f"cards[]:{cid}"] = ref
            every.append(ref)
        fields["cards[]"] = k.hesap("kartlar", "Özet kartları; her kartın kendi kaynağı kartın «i» düğmesinde.", every)
        dik: list[str] = []
        try:
            from semantic_bridge import budget as B

            dik.append(x.portal("portal.butce.uyarilar", "Açık bütçe uyarıları", B.deviations_stmt(tenant, y, status="acik"),
                                "Saatlik denetimin yazdığı sapmalar."))
        except Exception:  # noqa: BLE001
            pass
        dik.append(x.portal("portal.fin.vergi", "Vergi takvimi", F.tax_stmt(tenant), "Elle girilen beyanlar."))
        fields["dikkat[]"] = k.hesap("dikkat", F_DIKKAT, dik)
    k.alanlar(fields)
    return k


def _period_cols(year: int, month: int, grain: str) -> dict[str, Optional[list[tuple[int, int]]]]:
    months = F.period_months(int(year), int(month), grain)
    return {"donem": months, "onceki": F.previous_period(int(year), int(month), grain),
            "gecenYil": [(y - 1, m) for y, m in months]}


def for_pnl(engine: Any, tenant: str, out: dict[str, Any], logo_db: Optional[str]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, logo_db)
    k = x.k
    cols = _period_cols(out["year"], out["month"], out["grain"])
    months = cols["donem"] or []
    es = x.esleme()
    fields: dict[str, str] = {}
    labels = {"donem": "Dönem", "onceki": "Önceki dönem", "gecenYil": "Geçen yıl"}
    for key in ("donem", "onceki", "gecenYil"):
        ms = cols.get(key)
        if key in (out.get("columns") or {}) and ms:
            led = x.ledger(f"portal.fin.muhasebe.{key}", ms, label=labels[key])
            fields[f"rows[].values.{key}"] = k.hesap(f"gelir.{key}", F_MUHASEBE, [led] + es)
    if "butce" in (out.get("columns") or {}):
        try:
            from semantic_bridge import budget as B

            plan_src = x.portal("portal.butce.onayli", f"Yürürlükteki bütçe planı · {out['year']}",
                                B.approved_stmt(tenant, int(out["year"])), "Onaylı plan, taban dağılımı.")
            ins = [plan_src] + es
            with engine.connect() as c:
                row = B._approved(c, tenant, int(out["year"]))
            if row is not None:
                st = B.totals_stmts(row.id)
                ins.append(x.portal("portal.butce.toplam", "Plan toplamı (kitap hedefleri)", st["segment"],
                                    "Net satış hedefi = kitap hedefleri + program."))
                ins.append(x.portal("portal.butce.program", "Plan toplamı (program)", st["program"], "Yeni kitap programı."))
                ins.append(x.portal("portal.butce.departman", "Departman bütçesi", B.depts_stmt(row.id),
                                    "Aylık gider bütçesi."))
            fields["rows[].values.butce"] = k.hesap("gelir.butce", F_BUTCE, ins)
            if "rows[].values.donem" in fields:
                # «Bütçeden fark» kolonu ekranda çıkarılır; kaynağı bu iki kolonun kaynağıdır.
                fields["rows[].values.fark"] = k.hesap(
                    "gelir.fark", "Bütçeden fark = bu dönem − bütçe (satır başına; olumlu değer kâra olumlu katkı).",
                    [fields["rows[].values.donem"], fields["rows[].values.butce"]])
        except Exception:  # noqa: BLE001
            pass
    main_led = x.ledger("portal.fin.muhasebe.donem", months, label="Dönem") if months else None
    gelir = fields.get("rows[].values.donem") or k.hesap("gelir.donem", F_MUHASEBE, [main_led] + es)
    fields["rows[].values"] = k.hesap("gelir", F_MUHASEBE, [v for v in fields.values()])
    fields["rows[].onaysiz"] = k.hesap("gelir.onaysiz", F_ESLEME, [gelir])
    fields["rows[].hesap"] = k.hesap("gelir.hesapSayisi", "Satıra eşlenen, dönemde hareketi olan hesap sayısı "
                                                          "(ara toplamda alt satırların toplamı).", [gelir])
    rules = [x.ledger(f"portal.fin.muhasebe.{r}", months, r, "Dönem") for r in ("yansitma", "kapanis")] if months else []
    fields["dislanan"] = k.hesap("dislanan", "Dışlanan = «dışlandı» eşlemeli hesapların kâr etkisi (ör. stoka giden "
                                             "üretim gideri); rapora girmez, burada yazılır.", [gelir])
    fields["kurallar"] = k.hesap("kurallar", F_KURAL, rules or [gelir])
    fields["esleme"] = k.hesap("esleme", F_ESLEME, [gelir])
    sales = x.sales("portal.fin.satis.donem", months, "Dönem") if months else None
    if sales:
        fields["maliyet"] = k.hesap("maliyetKapsam", F_NET + " " + F_KAPSAM, [sales])
        fields["faturaNetSatis"] = k.hesap("faturaNet", F_NET, [sales])
        fields["mutabakatFarki"] = k.hesap("mutabakat", F_MUTABAKAT, [gelir, sales])
    mz = [s for s in (x.logo_year(y, "mizan") for y in sorted({y for y, _ in months})) if s]
    fields["mizan"] = k.hesap("mizan", F_MIZAN, mz or [gelir])
    k.alanlar(fields)
    return k


def for_line_accounts(engine: Any, tenant: str, out: dict[str, Any], year: int, month: int, grain: str,
                      logo_db: Optional[str]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, logo_db)
    months = F.period_months(int(year), int(month), grain)
    led = x.ledger("portal.fin.muhasebe.donem", months, label="Dönem")
    ref = x.k.hesap("hesaplar", "Satırın hesapları: hesap başına borç, alacak, kâr etkisi (alacak − borç) ve satır "
                                "sayısı; toplam = Σ kâr etkisi. " + F_MUHASEBE, [led] + x.esleme())
    x.k.alanlar({"items[]": ref, "toplam": ref})
    return x.k


def for_entries(engine: Any, out: dict[str, Any], sql: str, logo_db: Optional[str], year: int) -> P.Kaynaklar:
    k = P.Kaynaklar(data_end=F.data_end(engine))
    firm = (F.meta_get(engine, f"ledger:{year}").get("firm") or "")
    sid = k.sorgu("logo.fin.fisler", f"Logo fiş satırları · {out.get('hesap')}", "logo", sql, database=logo_db,
                  rows=len(out.get("items") or []), period=f"{out.get('donem')} · Logo firma {firm}".strip(),
                  description="Canlı okuma (sayfalı); her satırın rapordaki kuralı (dahil / yansıtma / kapanış) yazılır.")
    k.alanlar({"items[]": sid, "total": sid})
    return k


def for_reconciliation(engine: Any, tenant: str, out: dict[str, Any], year: int, month: int, grain: str,
                       logo_db: Optional[str]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, logo_db)
    months = F.period_months(int(year), int(month), grain)
    led = x.ledger("portal.fin.muhasebe.donem", months, label="Dönem")
    sales = x.sales("portal.fin.satis.donem", months, "Dönem")
    m = x.k.hesap("muhasebeNet", "Muhasebe: brüt satış (600–602), satış indirimleri (610–612), net satış satırları; "
                                 + F_MUHASEBE, [led] + x.esleme())
    f = x.k.hesap("faturaNet", F_NET + " Satış ve iade ayrı; iskonto = iskonto öncesi − net.", [sales])
    x.k.alanlar({"muhasebe": m, "fatura": f, "fark": x.k.hesap("mutabakat", F_MUTABAKAT, [m, f])})
    return x.k


def for_account_map(engine: Any, tenant: str, out: dict[str, Any], logo_db: Optional[str]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, logo_db)
    y = int(out["year"])
    led = x.ledger("portal.fin.muhasebe.yil", [(y, m) for m in range(1, 13)], label=str(y))
    names = x.portal("portal.fin.hesaplar", "Hesap planı (6/7)", sa.select(F.ACCOUNTS),
                     "Logo hesap planından okunan 6 ve 7 ile başlayan hesaplar (semantic_finance_accounts).")
    etki = x.k.hesap("etki", "Hesabın bu yılki kâr etkisi = Σ alacak − Σ borç («dahil» satırlar).", [led, names])
    say = x.k.hesap("eslemeSayim", "Eşleme durumu sayıları: yalnız hareketi olan hesaplar; tutar = |kâr etkisi|.",
                    [led] + x.esleme())
    meta = x.portal("portal.fin.oneriIsi", "Eşleme öneri işi durumu",
                    sa.select(F.META).where(F.META.c.key == f"suggest:{tenant}"),
                    "Son öneri işinin sayıları (hesap, öneri, belirsiz, hata).")
    esl = x.k.hesap("eslemeKaydi", "Eşleme kaydı: onaylı ya da önerilen satır, öneri olasılığı ve kaynağı (onay, kural, "
                                   "hesap planı); portal tablosunda saklanır.", x.esleme())
    x.k.hesap("gruplar", "Grup = hesap kodunun ilk rakamı (6 gelir tablosu, 7 maliyet hesapları); grup başlığındaki sayı "
                         "o gruptaki, süzgeçten geçen hesap sayısıdır (ekranda sayılır).", [led, names])
    x.k.alanlar({"gruplar": "hesap:gruplar", "items[].esleme": esl, "items[].kayit": esl,
                 "items[].etki": etki, "counts": say, "amounts": say, "suggest": x.k.hesap("oneriIsi",
                 "Öneri işi: sınıflanan hesap sayısı, eşik üstü öneri, belirsiz, hatalı.", [meta])})
    return x.k


def for_profitability(engine: Any, tenant: str, out: dict[str, Any], logo_db: Optional[str],
                      snapshot: Optional[dict[str, Any]] = None) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, logo_db)
    y, frm, to = int(out["year"]), int(out.get("from") or 1), int(out.get("to") or 12)
    months = [(y, m) for m in range(frm, to + 1)]
    by = out.get("by") or "kitap"
    origin = x.logo_years([y], "cari" if by == "cari" else "kitapKanal")
    prof = x.portal("portal.fin.karlilik", f"Kârlılık satırları · {out.get('donem')}", F.profit_stmt(by, months),
                    "Kırılım anahtarı × ay ölçüleri.", origin=origin)
    ins = [prof]
    if by in ("kitap", "seri", "yayinevi"):
        from semantic_bridge import budget as B

        ins.append(x.portal("portal.fin.kitapKarti", "Kitap kartı (ad, seri, yayınevi)", sa.select(B.BOOKINFO),
                            "CRM kitap kartı önbelleği (bütçe modülünün gece okuması): ad, yayınevi, kitaplık; "
                            "seri ve yayınevi kırılımının anahtarı."))
    from semantic_bridge.pricing import kaynak as PK

    snap_ids = PK.snap_sources(x.k, snapshot, ("logo_satis", "crm_kitap", "crm_baski"), logo_db)
    ref = x.k.hesap("karlilik", F_KARLILIK, ins + snap_ids)
    x.k.alanlar({"items[]": ref, "toplam": ref,
                 "telif": x.k.hesap("telifSayim", "Telif: yürürlükteki sözleşmesi bulunan / bulunmayan kitap sayısı.",
                                    ins + [s for s in snap_ids if "crm_kitap" in s])})
    return x.k


def for_cash(engine: Any, tenant: str, out: dict[str, Any], logo_db: Optional[str], crm_db: Optional[str]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, logo_db, crm_db)
    k = x.k
    cs = x.cash_sources(out.get("run"))
    lines = cs.get("lines") or cs.get("run")
    fields: dict[str, str] = {}
    every = []
    for item in out.get("kalemler") or []:
        kalem = item.get("kalem")
        src_id = cs.get(kalem)
        ref = k.hesap(f"kalem:{kalem}", f"{item.get('kaynak') or kalem}: vadesine göre haftasına yazılır.",
                      [s for s in (src_id, lines) if s])
        fields[f"kalemler[]:{kalem}"] = ref
        every.append(ref)
    table = k.hesap("nakit", F_NAKIT, [s for s in (cs.get("run"), lines) if s] + every)
    fields.update({"kalemler[]": table, "haftalar[]": table, "acikHafta": table,
                   "acilisBakiye": k.hesap("acilis", F_POZISYON, [s for s in (cs.get("pozisyon"), cs.get("run")) if s]),
                   "pozisyon": "hesap:acilis",
                   "vadesiGecmis": k.hesap("vadesiGecmis", F_VADESI, [s for s in (cs.get("alacak"), cs.get("satici"),
                                                                                  cs.get("run")) if s]),
                   "dovizTelif": k.hesap("dovizTelif", "Döviz cinsinden telif ödemeleri (çevrilmeden, para birimi başına).",
                                         [s for s in (cs.get("telif"), cs.get("run")) if s])})
    bant = out.get("bant") or {}
    if bant:
        reads = []
        for r in bant.get("sorgular") or []:
            reads.append(k.sorgu(
                f"logo.nakit.bant.{r['year']}", f"Geçmiş günlük tahsilat ve ödeme · {r['year']}", "logo",
                src.cash_flows_daily_sql(r["firm"], date.fromisoformat(r["from"]), date.fromisoformat(r["to"])),
                database=x.logo_db, rows=r.get("rows"), ms=r.get("dbMs"), ran_at=r.get("at"),
                period=f"{r['from']} – {r['to']} · Logo firma {r['firm']}",
                description="Bandın geçmişi: kasa + banka gün gün müşteri tahsilatı ve satıcı ödemesi; haftalara toplanır."))
        fields["bant"] = k.hesap(
            "bant", "Olasılıklı bant: vadesi belli kalemler (çek/senet, sözleşme ödemesi, vergi) tablodaki kuraldan; "
                    "müşteri tahsilatı ve satıcı ödemesi yerine geçmiş haftalık gerçekleşen serilerin Zeki AI tahmini "
                    "(p10/p50/p90, tahmin servisi) konur. En kötü %10 = açılış + Σ (kesin + tahsilat p10 − ödeme p90); "
                    "beklenen p50 ile, en iyi %10 tahsilat p90 − ödeme p10 ile. Tahmin yoksa bant gösterilmez."
                    + ("" if reads else " Bu tablo geçmiş okuması kaydedilmeden kuruldu; yeniden kurunca sorgular görünür."),
            [s for s in [cs.get("run"), lines] + reads if s] + [table])
    k.alanlar(fields)
    return k


def for_cash_history(engine: Any, tenant: str, logo_db: Optional[str]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, logo_db)
    runs = x.portal("portal.nakit.tablolar", "Geçmiş nakit tabloları", F.cash_run_stmt(tenant),
                    "Her tablonun haftalık tahmini (parametrelerde).")
    bank = x.logo_years(F._loaded_years(engine), "banka")
    ref = x.k.hesap("nakitGecmis", F_NAKIT_GECMIS, [runs] + bank)
    x.k.alanlar({"items[]": ref, "ortalamaMutlakSapma": ref})
    return x.k


def for_budget(engine: Any, tenant: str, out: dict[str, Any], logo_db: Optional[str]) -> P.Kaynaklar:
    from semantic_bridge import budget as B
    from semantic_bridge import budget_kaynak as BK

    k = P.Kaynaklar(data_end=F.data_end(engine))
    plan = out.get("plan")
    y = int(out["year"])
    if not plan:
        s = k.portal("portal.butce.onayli", f"Yürürlükteki bütçe planı · {y}", B.approved_stmt(tenant, y), engine,
                     description="Bu yıl için onaylı plan yok.")
        k.alanlar({"plan": s})
        return k
    bf = BK.tracking_fields(k, engine, tenant, plan["id"], y, logo_db)
    dev = k.portal("portal.butce.uyarilar", "Açık bütçe uyarıları", B.deviations_stmt(tenant, y, status="acik"), engine,
                   description="Saatlik denetimin yazdığı sapmalar.")
    k.alanlar({"sirket": bf["sirket"], "gider": bf["gider"], "aylar[]": bf["aylar[]"], "esik": bf["esik"],
               "departmanlar[]": k.hesap("departmanlar", BK.F_GIDER + " " + BK.F_DEPT + " Sapma = gerçekleşen − dönem "
                                                                                      "bütçesi.", [bf["gider"]]),
               "sapmalar[]": k.hesap("sapmalar", BK.F_UYARI, [dev]), "sapmaToplam": "hesap:sapmalar"})
    return k


def for_tax(engine: Any, tenant: str, year: Optional[int]) -> P.Kaynaklar:
    k = P.Kaynaklar(data_end=F.data_end(engine))
    s = k.portal("portal.fin.vergi", "Vergi takvimi", F.tax_stmt(tenant, year), engine,
                 description="Elle girilen beyanlar (semantic_finance_tax_calendar).")
    ref = k.hesap("vergi", F_VERGI, [s])
    gun = k.hesap("vergiGun", "Kalan gün = son gün − bugün (takvim günü); eksi ise «N gün geçti». Geciken = durumu «verildi» "
                              "olmayan ve son günü bugünden önce olan beyanlar; sayı bu listenin uzunluğudur.", [s])
    k.alanlar({"items[]": ref, "yaklasan[]": ref, "geciken[]": gun, "items[].kalanGun": gun, "gecikenSayi": gun})
    return k


#: Rakam olmayan sayılar (yıl, ay, sayfa, satır sırası, işaret, sürüm): kapsam denetiminde atlanır.
NOT_RAKAM = ("year", "month", "months", "from", "to", "page", "pageSize", "columns", "kapanis", "lines", "rows[].sira",
             "rows[].isaret", "items[].sira", "hazir", "plan.version", "total", "status")
