"""M42 D2C büyüme: timas.com.tr'nin payı, D2C'de pazar yerlerine göre oransal güçlü kitaplar, site müşterisi özeti ve
D2C'ye özel set/sadakat önerisi.

- Pay ve kitaplar Logo'dan: timas.com.tr platformuna eşlenen cari(ler) ya da kanal kodu. Eşleme yoksa sekme bunu söyler.
- «Oransal güçlü» = kitabın D2C payı (D2C net adet ÷ D2C + pazar yeri net adet) ÷ bütün kitaplardaki D2C payı ≥ eşik
  (`CHANNEL_D2C_INDEX`, 1,5) ve D2C net adedi ≥ `CHANNEL_D2C_MIN_ADET` (20). Eşikler ölçülmedi; ayardır.
- Site müşterisi (tekrar alım, müşteri başına ciro) H3'ün anahtarlanmış tablolarından (`semantic_commerce_*`) okunur;
  tablo yoksa ya da beklenen kolonlar yoksa «bağlı değil» döner. Kişisel alan okunmaz ve saklanmaz.
- Öneri (tür `d2c-set`) portal kaydıdır; hiçbir platforma gönderilmez. Gerekçe hesaptandır; Zeki AI yalnız rakamsız bir
  cümle ekler (rakam içeren satır atılır).
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Any, Optional

import sqlalchemy as sa

from semantic_bridge.channels import mapping as M
from semantic_bridge.channels import scorecard as SC
from semantic_bridge.channels import store as S

log = logging.getLogger("semantic.channels.d2c")

H3_ORDERS, H3_LINES, H3_CUSTOMERS = "semantic_commerce_orders", "semantic_commerce_order_lines", "semantic_commerce_customers"

SET_PROMPT = (
    "Bir yayınevinin kendi sitesinde (D2C) pazar yerlerine göre oransal olarak daha iyi satan kitaplar aşağıda. Bu "
    "kitaplardan yalnız sitede satılacak bir set ya da ön sipariş kampanyası için 2 cümlelik gerekçe yaz. Rakam, yüzde, "
    "fiyat yazma; kanıtsız üstünlük iddiası («en çok satan», «rekor») kullanma.\n\nKitaplar:\n{books}"
)


def _connected(engine: sa.engine.Engine) -> dict[str, Any]:
    try:
        insp = sa.inspect(engine)
        if not insp.has_table(H3_ORDERS):
            return {"bagli": False, "neden": "Site siparişleri (e-ticaret müşteri modülü) henüz bu kuruluma bağlanmadı."}
        cols = {c["name"] for c in insp.get_columns(H3_ORDERS)}
        need = {"tenant_id", "ordered_at", "total", "customer_key"}
        if not need <= cols:
            return {"bagli": False, "neden": f"Site siparişi tablosunda beklenen alanlar yok: {', '.join(sorted(need - cols))}."}
        return {"bagli": True, "lines": insp.has_table(H3_LINES), "customers": insp.has_table(H3_CUSTOMERS)}
    except Exception as e:  # noqa: BLE001
        return {"bagli": False, "neden": f"Site verisi okunamadı: {str(e)[:160]}"}


def _site(engine: sa.engine.Engine, tenant: str, p: dict[str, Any]) -> dict[str, Any]:
    info = _connected(engine)
    if not info["bagli"]:
        return info
    md = sa.MetaData()
    orders = sa.Table(H3_ORDERS, md, autoload_with=engine)
    y = p["yil"]
    # Metin karşılaştırması: «AAAA-AA-31» ayın son gününden büyük ya da eşittir, dönemin son ayını bütünüyle alır.
    start, end = f"{y}-01-01", f"{y}-{p['ay']:02d}-31"
    with engine.connect() as c:
        rows = c.execute(sa.select(orders.c.ordered_at, orders.c.total, orders.c.customer_key)
                         .where(orders.c.tenant_id == tenant)).all()
    monthly: dict[int, dict[str, float]] = defaultdict(lambda: {"siparis": 0, "ciro": 0.0})
    per_customer: dict[str, int] = defaultdict(int)
    revenue = 0.0
    n = 0
    for r in rows:
        d = str(r.ordered_at)[:10]
        if not (start <= d <= end):
            continue
        m = int(d[5:7])
        monthly[m]["siparis"] += 1
        monthly[m]["ciro"] += float(r.total or 0)
        revenue += float(r.total or 0)
        n += 1
        if r.customer_key:
            per_customer[str(r.customer_key)] += 1
    customers = len(per_customer)
    repeat = sum(1 for v in per_customer.values() if v > 1)
    return {"bagli": True, "siparis": n, "ciro": round(revenue, 2), "musteri": customers,
            "tekrarOrani": SC._ratio(repeat, customers), "musteriBasinaCiro": SC._ratio(revenue, customers),
            "sepetOrtalamasi": SC._ratio(revenue, n),
            "aylik": [{"ay": m, "siparis": int(v["siparis"]), "ciro": round(v["ciro"], 2)} for m, v in sorted(monthly.items())],
            "not": "Site siparişi tutarı sitenin kendi kaydıdır (kargo ve kupon dahil olabilir); Logo net cirosuyla aynı şey değildir."}


def overview(engine: sa.engine.Engine, tenant: str, st: dict[str, Any], yil: Optional[int] = None, ay: Optional[int] = None) -> dict[str, Any]:
    p = SC.period(engine, tenant, yil, ay)
    SC.need_read(engine, tenant, [p["yil"]])
    mp = SC.Mapping(engine, tenant)
    d2c_groups = [g for g, v in mp.amap.items() if v == M.D2C] + [f"#K:{k}" for k, v in mp.kmap.items() if v == M.D2C]
    card = SC.scorecard(engine, tenant, p["yil"], p["ay"])
    d2c = next((x for x in card["platforms"] if x["platform"] == M.D2C), None)
    out: dict[str, Any] = {"period": p, "eslendi": bool(d2c_groups), "gruplar": d2c_groups,
                           "d2c": d2c, "toplam": card["toplam"], "site": _site(engine, tenant, p),
                           "esik": {"minAdet": st["d2cMinAdet"], "indeks": st["d2cIndex"]}}
    if not d2c_groups:
        out["kitaplar"] = []
        out["not"] = "timas.com.tr henüz bir cariye ya da kanal koduna eşlenmedi (Cari eşleme ekranı)."
        return out
    out.update(strong_books(engine, tenant, p, mp, st))
    out["oneriler"] = S.suggestions(engine, tenant, platform=M.D2C)
    return out


def strong_books(engine: sa.engine.Engine, tenant: str, p: dict[str, Any], mp: SC.Mapping, st: dict[str, Any]) -> dict[str, Any]:
    w = SC._window(p, p["yil"])
    d2c: dict[str, float] = defaultdict(float)
    market: dict[str, float] = defaultdict(float)
    for r in SC._book_rows(engine, tenant, p["yil"]):
        wt = w.get(r.ay)
        if not wt:
            continue
        plat = mp.platform(r.grup)
        net = (float(r.satis_adet or 0) - float(r.iade_adet or 0)) * wt
        if plat == M.D2C:
            d2c[r.stok_kodu] += net
        elif plat not in ("degil", M.UNMAPPED):
            market[r.stok_kodu] += net
    tot_d, tot_m = sum(max(0.0, v) for v in d2c.values()), sum(max(0.0, v) for v in market.values())
    base = SC._ratio(tot_d, tot_d + tot_m)
    rows = []
    if base:
        for code, dv in d2c.items():
            if dv < st["d2cMinAdet"]:
                continue
            mv = max(0.0, market.get(code, 0.0))
            share = dv / (dv + mv) if dv + mv > 0 else None
            idx = share / base if share is not None else None
            if idx is not None and idx >= st["d2cIndex"]:
                rows.append({"stokKodu": code, "d2cAdet": round(dv, 2), "pazarYeriAdet": round(mv, 2), "d2cPay": share, "indeks": idx})
    names = S.book_names(engine, tenant, [r["stokKodu"] for r in rows])
    for r in rows:
        r["ad"] = names.get(r["stokKodu"], "")
    rows.sort(key=lambda r: (-(r["indeks"] * r["d2cAdet"]), r["stokKodu"]))
    return {"kitaplar": rows, "genelD2cPay": base, "d2cAdet": round(tot_d, 2), "pazarYeriAdet": round(tot_m, 2)}


def suggest_set(engine: sa.engine.Engine, tenant: str, user: str, st: dict[str, Any], codes: list[str], llm: Any,
                yil: Optional[int] = None, ay: Optional[int] = None) -> dict[str, Any]:
    """Seçilen güçlü kitaplardan D2C'ye özel set önerisi (taslak). Kitap listesi boşsa ilk 5 güçlü kitap."""
    p = SC.period(engine, tenant, yil, ay)
    mp = SC.Mapping(engine, tenant)
    strong = strong_books(engine, tenant, p, mp, st)["kitaplar"]
    by = {r["stokKodu"]: r for r in strong}
    pick = [by[c] for c in codes if c in by] if codes else strong[:5]
    if not pick:
        raise SC.ChannelError("Öneri için D2C'de oransal güçlü kitap yok (eşikler Yönetim ayarında).")
    reason = "Seçilen kitaplar sitede pazar yerlerine göre oransal olarak güçlü: " + "; ".join(
        f"{r['ad'] or r['stokKodu']} (D2C payı genel payın {r['indeks']:.1f} katı)".replace(".", ",") for r in pick) + "."
    model_note = None
    if llm is not None:
        try:
            text = (llm.chat([{"role": "user", "content": SET_PROMPT.format(books="\n".join(f"- {r['ad'] or r['stokKodu']}" for r in pick))}],
                             max_tokens=220, temperature=0.3) or "").strip()
            text = re.sub(r"[^\n]*\d[^\n]*\n?", "", text).strip()
            model_note = text[:1200] or None
        except Exception as e:  # noqa: BLE001 — model yoksa gerekçe yalnız hesaptan
            log.warning("channels: D2C set gerekçesi yazılamadı: %s", e)
    payload = {"kitaplar": [{k: r[k] for k in ("stokKodu", "ad", "d2cAdet", "pazarYeriAdet", "d2cPay", "indeks")} for r in pick],
               "donem": {"yil": p["yil"], "ay": p["ay"]}, "hesap": reason}
    title = f"D2C'ye özel set: {', '.join((r['ad'] or r['stokKodu'])[:40] for r in pick[:3])}" + (" …" if len(pick) > 3 else "")
    return S.suggestion_add(engine, tenant, user, M.D2C, "d2c-set", title, payload, model_note)
