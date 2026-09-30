#!/usr/bin/env python3
"""M9 eski kitap fiyat karşılaştırması — test sunucusunda gerçek M9 görüntüsü, gerçek portal DB'si ve CRM ile kabul.

Fiyatlama uçları gerçek kodla (`semantic_bridge.pricing.register`) bir FastAPI uygulamasına bağlanır ve HTTP ile
çağrılır; yalnız oturum çözümü (AD girişi) atlanır, değişiklik kaydı yazılmaz. Görüntünün kopyası geçici klasörde
açılır (canlı görüntüye yazılmaz, Logo'ya yenileme sorgusu gitmez). Analiz, teklif, pazar fiyatı açmaz.

    cd <kaynak>/backend && sudo systemd-run --uid=administrator --pipe --wait -p EnvironmentFile=/etc/nanobase/semantic-bridge.env \\
        /data/nanobaseai/bi/semantic-venv/bin/python ../scripts/acceptance/M9-eski-kitap/kabul.py --out /tmp/claude-<oturum>/kabul.json

Kontroller (OK / FARK / DOĞRULANAMADI):
- K1  `/compare` hesabı biter; fiyatı olan her kitap listede (hesaplanamayan nedeniyle); durum sayıları toplamı tutar.
- K2  Durum başına --ornek kitap + en çok satan --ornek kitap: ekranın «Kitap hesabı» zinciri (`/books`, `/form/setup`,
      `/form/calc`, `/overview`, `/calc`; `CalcPane.tsx`'in `fromSuggested` + maliyet formu aktarımı satır satır)
      ile aynı önerilen fiyat, birim maliyet, adet ve marj — kuruşu kuruşuna.
- K3  Aynı kitapların güncel fiyatı = CRM'de şu an `new_kitapBase.new_kdvdahilfiyat` (bağımsız SQL). Görüntü CRM'den
      eskiyse fark görüntü tarihiyle birlikte yazılır.
- K4  Süzgeçler: arama, en az satış, yeni kitap, durum sekmesi, sayfalama ve CSV satır sayısı.
- K5  Kur: fiyat listesinde «elle» seçilince form ve karşılaştırma elle kuru kullanır, «logo»da Logo kuru; sonunda
      fiyat listesi eski hâline döner (fiyat listesi varsayılandaysa satır silinir, değilse kayıt geri yazılır).
- K6  Teklif ucu boş seçimi reddeder (400); kayıt açılmaz.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

LIVE_DIR = Path(os.environ.get("PRICING_DATA_DIR", "/data/nanobaseai/bi/var/pricing"))
WORK = Path(tempfile.mkdtemp(prefix="m9-eski-kitap-"))
shutil.copy2(LIVE_DIR / "snapshot.json", WORK / "snapshot.json")
(WORK / "status.json").write_text(json.dumps({"updatedAt": time.time(), "error": None}))
os.environ["PRICING_DATA_DIR"] = str(WORK)
os.environ["PRICING_REFRESH_SECONDS"] = str(10 ** 9)

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from semantic_bridge import pricing as PR  # noqa: E402
from semantic_bridge.pricing import karsilastir as KS  # noqa: E402
from semantic_bridge.pricing import store as S  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

RESULTS: list[dict] = []


def record(name: str, status: str, **detail) -> None:
    RESULTS.append({"kontrol": name, "durum": status, **detail})
    print(f"[{status:>13}] {name}  {json.dumps(detail, ensure_ascii=False, default=str)[:600]}", flush=True)


def same(a, b, tol=0.005) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= tol


# ------------------------------------------------------------------ ekranın zinciri (CalcPane.tsx, satır satır)

def binding_of(tur):
    t = (tur or "").upper()
    for key, val in (("SERT", "Sert Kapak"), ("FLEKS", "Flexi Kapak Cilt"), ("TEL", "Tel Dikiş"), ("AMER", "Amerikan Cilt")):
        if key in t:
            return val
    return None


def nn(*vals):
    """JS `a ?? b ?? c`."""
    for v in vals:
        if v is not None:
            return v
    return None


def ui_chain(c: TestClient, code: str, ov: dict) -> dict:
    """Kitap seçilince ekranın yaptığı: kitap + form kurulumu → maliyet formu → fiyat hesabı. Hata olursa ekranda ne
    görünürse o (hesap yok)."""
    b = c.get(f"/api/v1/pricing/books/{code}").json()
    setup = c.get("/api/v1/pricing/form/setup", params={"kitap": code}).json()
    d = ov["defaults"]
    s, fl = b["suggested"], b["freelance"]["byKey"]
    form = {  # fromSuggested
        "printService": s.get("printService"), "paperPerCopy": (s.get("paper") or {}).get("perCopy"),
        "printSetup": nn(s.get("printSetup"), 0), "overheadRate": d["overheadRate"],
        "fixed": {"avans": nn(s.get("advance"), 0), "ceviri": nn(fl.get("ceviri"), 0), "grafik": nn(fl.get("grafik"), 0),
                  "redaksiyon": nn(fl.get("redaksiyon"), 0), "pazarlama": 0, "diger": nn(fl.get("diger"), 0)},
        "royaltyRate": nn(s.get("royaltyRate"), 0), "royaltyBase": "kapak", "royaltyOn": "baski", "vat": s.get("vat"),
        "discount": nn(s.get("discount"), 0), "variableRate": nn(s.get("variableRate"), d["variableRate"]),
        "sellThrough": d["sellThrough"], "targetMargin": d["targetMargin"], "qtys": d["qtys"],
        "chosenQty": d["qtys"][len(d["qtys"]) // 2] if d["qtys"] else None, "price": None,
    }
    spec = dict(b["spec"])
    cost = setup["inputs"]
    fc = c.post("/api/v1/pricing/form/calc", json={"inputs": cost})
    mapped = fc.json().get("analysis") if fc.status_code == 200 else None
    if mapped:  # maliyet formunun sonucu fiyat hesabına (sync, elle baskı bedeli yok)
        q = mapped["chosenQty"]
        form.update({"printService": mapped["printService"], "paperPerCopy": mapped["paperPerCopy"], "printSetup": mapped["printSetup"],
                     "overheadRate": mapped["overheadRate"], "royaltyRate": mapped["royaltyRate"],
                     "qtys": sorted(set(form["qtys"]) | {q}), "chosenQty": q, "price": nn(mapped.get("price"), form["price"]),
                     "fixed": {**form["fixed"], "grafik": mapped["fixed"]["grafik"], "diger": mapped["fixed"]["diger"]}})
        spec.update({"pages": nn(cost.get("sayfa"), spec.get("pages")), "trim": nn(cost.get("ebat"), spec.get("trim")),
                     "gsm": nn((cost.get("ic") or {}).get("gr"), spec.get("gsm")),
                     "binding": nn(binding_of((cost.get("cilt") or {}).get("tur")), spec.get("binding")), "form": cost})
    ppc = (form["printService"] or 0) + (form["paperPerCopy"] or 0)
    inputs = {**form, "printPerCopy": ppc or None}
    out = {"price": b["book"].get("price"), "formError": None if mapped else (fc.json().get("detail") or {}).get("message")}
    if not (inputs["printPerCopy"] or 0) > 0:  # ekran hesabı çağırmaz
        return {**out, "ours": None}
    r = c.post("/api/v1/pricing/calc", json={"inputs": inputs, "spec": spec, "marketPrices": [m["price"] for m in b.get("market") or []]})
    if r.status_code != 200:
        return {**out, "ours": None, "calcError": r.text[:200]}
    j = r.json()
    return {**out, "ours": j["recommendation"]["price"], "unitCost": j["summary"]["unitCost"], "qty": j["summary"]["qty"],
            "margin": j["summary"]["margin"], "floor": j["recommendation"]["floor"], "median": j["recommendation"]["median"]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="m9-eski-kitap-kabul.json")
    ap.add_argument("--ornek", type=int, default=10, help="durum başına kitap sayısı")
    args = ap.parse_args()

    engine = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False).engine
    tenant = os.environ.get("SEMANTIC_TENANT_ID", "default")
    S.ensure(engine)
    app = FastAPI()
    runtime = SimpleNamespace(settings=SimpleNamespace(connection_file=os.environ["SEMANTIC_CONNECTION_FILE"]))
    PR.register(app, lambda: runtime, {"session": lambda req: (engine, tenant, "ZEKİ AI", "ZEKİ AI"),
                                        "can": lambda user, key: True, "audit": lambda *a, **k: None,
                                        "is_admin": lambda user: False})
    c = TestClient(app)
    snap = json.loads((WORK / "snapshot.json").read_text())
    record("Görüntü", "OK", dataEnd=snap.get("dataEnd"), asOf=snap.get("asOf"), kitap=len(snap.get("books") or {}))

    # K1
    t0 = time.time()
    while True:
        cm = c.get("/api/v1/pricing/compare", params={"new": "true", "limit": 100000}).json()
        if cm.get("ready") or time.time() - t0 > 300:
            break
        time.sleep(2)
    if not cm.get("ready"):
        record("K1 karşılaştırma hesabı", "DOĞRULANAMADI", neden="5 dakikada bitmedi", cevap=cm.get("error"))
        return finish(args.out)
    rows = cm["rows"]
    priced = {code for code, b in (snap.get("books") or {}).items() if b.get("price") and b["price"] > 0}
    got = {r["code"] for r in rows}
    ok = got == priced and cm["total"] == len(rows) == sum(cm["counts"].values())
    record("K1 karşılaştırma hesabı", "OK" if ok else "FARK", sure_sn=round(time.time() - t0, 1), hesap_sn=cm.get("seconds"),
           fiyatli=len(priced), listede=len(got), eksik=sorted(priced - got)[:10], fazla=sorted(got - priced)[:10],
           sayilar=cm["counts"], ortalama_fark=cm.get("avgDiffPct"), kur=cm.get("kur"), kurKaynak=cm.get("kurKaynak"))

    # K2 + K3: örnek kitaplar
    ov = c.get("/api/v1/pricing/overview").json()
    by = {r["code"]: r for r in rows}

    def pick(xs, n):
        return sorted(xs, key=lambda r: hashlib.sha256(r["code"].encode()).hexdigest())[:n]

    sample = []
    for st in KS.STATUS:
        sample += pick([r for r in rows if r["status"] == st], args.ornek)
    sample += sorted([r for r in rows if r not in sample], key=lambda r: -(r.get("sold2y") or 0))[:args.ornek]
    fails = 0
    for r in sample:
        u = ui_chain(c, r["code"], ov)
        fields = {"ours": (r.get("ours"), u.get("ours")), "unitCost": (r.get("unitCost"), u.get("unitCost")),
                  "qty": (r.get("qty"), u.get("qty")), "margin": (r.get("margin"), u.get("margin")),
                  "price": (r["price"], u["price"])}
        bad = {k: v for k, v in fields.items() if not same(*v)}
        if r["status"] == "hesaplanamadi" and u.get("ours") is None and not bad.get("price"):
            bad = {}
        fails += bool(bad)
        record(f"K2 {r['code']} ({r['status']})", "FARK" if bad else "OK", kitap=r["name"][:40], liste=r.get("ours"),
               ekran=u.get("ours"), guncel=r["price"], adet=r.get("qty"), neden=r.get("reason") or u.get("formError"), farklar=bad)
    record("K2 ekranın zinciriyle aynı rakam", "OK" if not fails else "FARK", ornek=len(sample), fark=fails)

    crm_file = os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json")
    try:
        from semantic_layer.profiler.connectors import connector_from_file
        crm = connector_from_file(crm_file)
        codes = [r["code"] for r in sample]
        sql = ("SELECT k.new_StokKodu AS kod, k.new_kdvdahilfiyat AS fiyat, k.modifiedon AS degisti FROM new_kitapBase k "
               "WHERE k.statecode = 0 AND k.new_StokKodu IN (" + ", ".join("'" + x.replace("'", "''") + "'" for x in codes) + ")")
        _, crm_rows, _ = crm.execute(sql, 10000)
        live = {}
        for x in crm_rows:
            live.setdefault(x["kod"], []).append(x)
        diffs = []
        for r in sample:
            xs = live.get(r["code"]) or []
            prices = sorted({float(x["fiyat"]) for x in xs if x["fiyat"] is not None})
            if len(prices) != 1 or not same(prices[0], r["price"], 0.01):
                diffs.append({"kod": r["code"], "liste": r["price"], "crm": prices,
                              "crm_degisti": max((str(x["degisti"]) for x in xs), default=None)})
        record("K3 güncel fiyat = CRM (şu an)", "OK" if not diffs else "FARK", ornek=len(sample), fark=len(diffs),
               goruntu=snap.get("asOf"), ayrinti=diffs[:10])
    except Exception as e:  # noqa: BLE001
        record("K3 güncel fiyat = CRM (şu an)", "DOĞRULANAMADI", neden=f"{type(e).__name__}: {e}"[:300])

    # K4 süzgeçler
    old = c.get("/api/v1/pricing/compare", params={"limit": 100000}).json()
    new_n = sum(1 for r in rows if r["new"])
    k4 = [("yeni hariç", old["total"] == len(rows) - new_n and old["newHidden"] == new_n)]
    zam = c.get("/api/v1/pricing/compare", params={"status": "zam", "limit": 100000}).json()
    k4.append(("zam sekmesi", zam["count"] == old["counts"]["zam"] and all(r["status"] == "zam" and r["diff"] > 0 for r in zam["rows"])))
    ms = c.get("/api/v1/pricing/compare", params={"minSold": 100, "limit": 100000}).json()
    k4.append(("en az satış 100", ms["total"] == sum(1 for r in rows if not r["new"] and (r["sold2y"] or 0) >= 100)))
    one = next(r for r in rows if r["status"] != "hesaplanamadi" and not r["new"])
    sr = c.get("/api/v1/pricing/compare", params={"q": one["code"]}).json()
    k4.append(("stok koduyla arama", [r["code"] for r in sr["rows"]] == [one["code"]]))
    p1 = c.get("/api/v1/pricing/compare", params={"limit": 100}).json()
    k4.append(("sayfalama", len(p1["rows"]) == min(100, p1["count"]) and p1["count"] == old["count"]))
    csv = c.get("/api/v1/pricing/compare.csv")
    lines = [ln for ln in csv.text.lstrip("﻿").splitlines() if ln.strip()]
    k4.append(("CSV satır sayısı", csv.status_code == 200 and len(lines) - 1 == old["count"]))
    record("K4 süzgeçler", "OK" if all(v for _, v in k4) else "FARK", **{k: v for k, v in k4})

    # K5 kur
    before = S.get_form_tariff(engine, tenant)
    try:
        r = c.put("/api/v1/pricing/form/tariff", json={"kurKaynak": "elle", "kur": {"USD": 60.0, "EUR": 70.0}})
        s1 = c.get("/api/v1/pricing/form/setup", params={"kitap": one["code"]}).json()
        t0 = time.time()
        while True:
            e = c.get("/api/v1/pricing/compare", params={"q": one["code"]}).json()
            if e.get("ready") or time.time() - t0 > 300:
                break
            time.sleep(2)
        elle_ok = (r.status_code == 200 and r.json()["kurKaynak"] == "elle" and s1["inputs"].get("kur") is None
                   and e.get("kurKaynak") == "elle" and e.get("kur") == {"USD": 60.0, "EUR": 70.0})
        fc = c.post("/api/v1/pricing/form/calc", json={"inputs": s1["inputs"]}).json()
        record("K5 kur elle", "OK" if elle_ok and fc.get("kur") == {"USD": 60.0, "EUR": 70.0} else "FARK",
               put=r.status_code, form_kur=fc.get("kur"), liste_kur=e.get("kur"), liste_hazir=e.get("ready"))
        bad = c.put("/api/v1/pricing/form/tariff", json={"kurKaynak": "banka"})
        record("K5 geçersiz kur kaynağı reddedilir", "OK" if bad.status_code == 400 else "FARK", durum=bad.status_code)
        c.put("/api/v1/pricing/form/tariff", json={"kurKaynak": "logo"})
        s2 = c.get("/api/v1/pricing/form/setup", params={"kitap": one["code"]}).json()
        lk = {k: v["rate"] for k, v in (snap.get("kur") or {}).items() if v.get("rate")}
        record("K5 kur Logo", "OK" if (s2["inputs"].get("kur") or {}) == lk else "FARK", form_kur=s2["inputs"].get("kur"), logo=lk)
    finally:
        if before["isDefault"]:
            c.put("/api/v1/pricing/form/tariff", json={"reset": True})
        else:
            keep = {k: before[k] for k in ("kur", "kurKaynak", "vade", "papers", "prices", "fire", "dolayli", "kapakBolen", "publishers")}
            S.save_form_tariff(engine, tenant, before["updatedBy"] or "ZEKİ AI", keep)
        after = S.get_form_tariff(engine, tenant)
        strip = lambda t: {k: v for k, v in t.items() if k not in ("updatedAt", "updatedBy")}  # noqa: E731
        record("K5 fiyat listesi eski hâlinde", "OK" if strip(after) == strip(before) else "FARK",
               varsayilan=after["isDefault"], once_varsayilan=before["isDefault"])

    # K6
    r = c.post("/api/v1/pricing/proposals", json={"title": "", "codes": []})
    record("K6 boş teklif reddedilir", "OK" if r.status_code == 400 else "FARK", durum=r.status_code)
    return finish(args.out)


def finish(out: str) -> int:
    Path(out).write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1, default=str))
    shutil.rmtree(WORK, ignore_errors=True)
    bad = [r for r in RESULTS if r["durum"] != "OK"]
    print(f"\nSONUÇ: {len(RESULTS) - len(bad)} OK, {len(bad)} değil → {out}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
