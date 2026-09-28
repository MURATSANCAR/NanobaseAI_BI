"""M18 hedef açığı ↔ ay planı boşluğu (AI fırsatları öneri 17b): «hedefin altında kalan kitaplara bu ay iş
planlanmamış» listesi + tek paragraf. Karar insanda (pazarlama müdürü).

**Liste kuraldır:**
- *Hedefin altında*: M46'nın açık kitap sapma uyarıları (M18'e açılmış olanlar; `monthly.open_deviations` — eşik ve
  hesap M46'nın, burada yeniden hesap yok): stok kodu → gerçekleşen/beklenen oranı, eksik ciro.
- *Bu ay iş planlı*: (a) ayın planındaki kalemlerde o stok kodu (yeni kitap, backlist, set, elle eklenen), (b) o stok kodlu
  pazarlama planlarının (M15/M17; arşiv hariç) bu aya düşen, «atlandı» olmayan işleri. İkisinden biri varsa kitap
  «planlı» sayılır.
- Liste = hedefin altında olup bu ay planlı olmayan kitaplar, eksik ciroya göre büyükten küçüğe. Sessiz tavan yok.

**Paragraf:** kural paragrafı her zaman vardır. Zeki AI paragrafı yalnız istenince (NORMAL) yazılır; olgular yalnız sayı ve
oran taşır (ciro tutarı modele gitmez: bütçe görme yetkisi olmayan da okur); `marketing.guard` denetiminden geçmeyen
cümle düşer. Paragraf `semantic_mkt_meta` içinde `month-gaps:<dönem>` anahtarında girdisiyle saklanır; liste değişince
eski paragraf «güncel değil» olur ve kural paragrafı gösterilir.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Optional

import sqlalchemy as sa

from semantic_bridge.marketing import core as C
from semantic_bridge.marketing import guard as G
from semantic_bridge.marketing import monthly as M
from semantic_bridge.marketing import plans as P

TOP_IN_TEXT = 5          # paragrafta adı geçen kitap sayısı (liste tam kalır; bu yalnız metnin uzunluğu)


def planned_tasks_stmt(tenant: str, donem: str):
    """Stok kodlu planların (arşiv hariç) bu aya düşen, atlanmamış işlerinin stok kodları."""
    first, last = M.bounds(donem)
    return (sa.select(C.PLANS.c.stok_kodu).select_from(C.TASKS.join(C.PLANS, C.PLANS.c.id == C.TASKS.c.plan_id)).where(
        C.PLANS.c.tenant_id == tenant, C.PLANS.c.durum != "arsiv", C.PLANS.c.stok_kodu.isnot(None),
        C.TASKS.c.durum != "atlandi", C.TASKS.c.tarih >= first.isoformat(), C.TASKS.c.tarih <= last.isoformat()).distinct())


def planned_codes(engine: Any, tenant: str, donem: str) -> set[str]:
    """Bu ay için işi planlı stok kodları: ay planı kalemleri + stok kodlu planların bu aya düşen işleri."""
    first, last = M.bounds(donem)
    codes: set[str] = set()
    h = M.find_plan(engine, tenant, donem)
    if h:
        codes |= {x["stokKodu"] for x in M.items_of(engine, h["id"]) if x.get("stokKodu")}
    with engine.connect() as c:
        rows = c.execute(planned_tasks_stmt(tenant, donem)).all()
    codes |= {r[0] for r in rows if r[0]}
    return codes


def gaps(engine: Any, tenant: str, donem: str, deviations: Optional[dict[str, dict[str, Any]]] = None) -> dict[str, Any]:
    donem = M.parse_donem(donem)
    y = int(donem[:4])
    devs = M.open_deviations(engine, tenant, y) if deviations is None else deviations
    planned = planned_codes(engine, tenant, donem)
    missing = [{"stokKodu": k, "ad": v.get("ad") or k, "oran": v.get("oran"), "eksik": v.get("eksik")}
               for k, v in devs.items() if k not in planned]
    missing.sort(key=lambda x: (-(x["eksik"] or 0), x["oran"] if x["oran"] is not None else 9, x["stokKodu"]))
    covered = sum(1 for k in devs if k in planned)
    out = {"donem": donem, "donemAdi": M.label(donem), "items": missing, "hedefAlti": len(devs), "planli": covered,
           "plansiz": len(missing), "kaynak": "Hedef açığı: bütçe ve hedefler modülünün açık kitap sapma uyarıları "
           "(eşik ve hesap orada). Plan: bu ayın plan kalemleri ve bu aya düşen pazarlama planı işleri."}
    out["kuralParagrafi"] = rule_paragraph(out)
    return out


def _pct(v: Optional[float]) -> str:
    return "—" if v is None else f"%{v * 100:.0f}"


def facts(g: dict[str, Any]) -> list[str]:
    f = [f"Dönem: {g['donemAdi']}", f"Hedefin altında kalan kitap: {g['hedefAlti']}",
         f"Bu ay işi planlı olan: {g['planli']}", f"Bu ay işi planlanmamış olan: {g['plansiz']}"]
    for x in g["items"][:TOP_IN_TEXT]:
        f.append(f"{x['ad']}: hedefe oranı {_pct(x['oran'])}")
    return f


def rule_paragraph(g: dict[str, Any]) -> str:
    if not g["hedefAlti"]:
        return f"{g['donemAdi']} için hedefin altında kalan kitap uyarısı yok."
    if not g["plansiz"]:
        return f"Hedefin altında kalan {g['hedefAlti']} kitabın hepsine {g['donemAdi']} için iş planlanmış."
    names = ", ".join(f"{x['ad']} ({_pct(x['oran'])})" for x in g["items"][:TOP_IN_TEXT])
    return (f"Kurala göre: hedefin altında kalan {g['hedefAlti']} kitabın {g['plansiz']} tanesine {g['donemAdi']} için iş "
            f"planlanmamış; eksik ciroya göre ilk sıradakiler {names}. Hangi kitaba iş açılacağı pazarlama müdürünün kararıdır.")


def input_hash(g: dict[str, Any]) -> str:
    return hashlib.sha1("\n".join(facts(g)).encode("utf-8")).hexdigest()


def with_paragraph(engine: Any, tenant: str, g: dict[str, Any]) -> dict[str, Any]:
    saved = C.meta_get(engine, tenant, f"month-gaps:{g['donem']}")
    fresh = bool(saved.get("metin")) and saved.get("girdi") == input_hash(g)
    return {**g, "paragraf": saved.get("metin") if fresh else g["kuralParagrafi"], "paragrafKaynak": "zeki" if fresh else "kural",
            "paragrafDusen": saved.get("dusen") if fresh else None, "paragrafZaman": saved.get("_at") if fresh else None,
            "eskiParagraf": bool(saved.get("metin")) and not fresh}


def write_paragraph(engine: Any, tenant: str, g: dict[str, Any], llm: Any, claims: list[str]) -> dict[str, Any]:
    fx = facts(g)
    prompt = ("Olgu listesi (yazabileceğin sayılar yalnız bunlar):\n" + "\n".join(f"- {x}" for x in fx)
              + "\n\nPazarlama müdürüne tek paragraf (üç dört cümle) yaz: hedefin altında kalıp bu ay için işi planlanmamış "
                "kitaplar ne durumda, neye bakmalı. Karar verme; seçimi müdüre bırak. Yeni sayı üretme.")
    raw = str(llm.chat([{"role": "system", "content": P.SYSTEM}, {"role": "user", "content": prompt}], max_tokens=500) or "")
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.S).strip()
    res = G.check(raw, [x["ad"] for x in g["items"][:TOP_IN_TEXT]], fx, claims)
    metin = " ".join(res["metin"].split()) or None
    C.meta_set(engine, tenant, f"month-gaps:{g['donem']}", {"girdi": input_hash(g), "metin": metin, "dusen": res["dusenSayisi"]})
    return {"metin": metin, "dusen": res["dusenSayisi"]}


def redact(g: dict[str, Any]) -> dict[str, Any]:
    """Bütçe görme yetkisi olmayan: eksik ciro boş (oran kalır)."""
    return {**g, "items": [{**x, "eksik": None} for x in g["items"]]}
