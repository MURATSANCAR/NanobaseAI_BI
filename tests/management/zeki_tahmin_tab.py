"""ZEKI AI Tahminleme — tahmin raporu ve sekme (veritabanı ve model gerektirmez).

Koşturma (fastapi kurulu ortamda):  python3 tests/management/zeki_tahmin_tab.py
"""
import copy
import importlib.util
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from semantic_bridge.management import baski_oneri as bo  # noqa: E402
from semantic_bridge.management import zeki_tahmin as zt  # noqa: E402

sonuc = []


def ok(ad, kosul, gorulen=""):
    print(("GEÇTİ  " if kosul else "DÜŞTÜ  ") + ad + (f"   → {gorulen}" if gorulen else ""))
    sonuc.append(bool(kosul))


# ---- son tam ay
ok("son fatura 17.08 → son tam ay Temmuz", zt.last_full_month(date(2026, 8, 17), date(2026, 9, 24)) == zt._mi(2026, 7))
ok("son fatura ay sonu → o ay tam", zt.last_full_month(date(2026, 8, 31), date(2026, 9, 24)) == zt._mi(2026, 8))
ok("içinde bulunulan ay hiçbir zaman tam değil", zt.last_full_month(date(2026, 9, 30), date(2026, 9, 30)) == zt._mi(2026, 8))

# ---- tahmin raporu: Logo satırları → servis isteği → tahmin
inputs = {"baski-oneri": {"views": [
    {"id": "tekrar", "columns": [{"key": "stok_kodu"}], "rows": [["A"], ["B"]]},
    {"id": "yeni", "columns": [{"key": "stok_kodu"}], "rows": [["N"]]},
]}}
DATA = {
    "logo_son_fatura": [{"son_fatura": "2026-08-17T00:00:00"}],
    "logo_aylik_gecmis": [{"stok_kodu": "A", "yil": 2025, "ay": m, "miktar": 10.0} for m in range(1, 13)]
                         + [{"stok_kodu": "A", "yil": 2026, "ay": m, "miktar": 20.0} for m in range(1, 9)]
                         + [{"stok_kodu": "B", "yil": 2026, "ay": m, "miktar": 5.0} for m in (5, 6, 7)]
                         + [{"stok_kodu": "N", "yil": 2025, "ay": m, "miktar": 3.0} for m in range(3, 13)]
                         + [{"stok_kodu": "X", "yil": 2025, "ay": m, "miktar": 100.0} for m in range(1, 13)],  # havuz dışı
}
calls = {}
years = []


def run(sid, params=None):
    calls[sid] = params
    recs = DATA[sid]
    if sid == "logo_aylik_gecmis":
        years.append(params["yil"]); recs = [r for r in recs if r["yil"] == params["yil"]]
    return {"records": recs, "columns": [], "dbMs": 1, "sql": f"-- {sid}"}


sent = {}


def post(payload):
    sent.update(payload)
    return {"engine": "timesfm-3.0", "engine_version": "3.0", "checkpoint_sha": "abc", "latency_ms": 5,
            "results": [{"id": x["id"], "start": "2026-08", "quantiles": [[1, 2, 3, 4, 10, 6, 7, 30, 40]] * 12}
                        for x in payload["series"]]}


fc = zt.build(run, today=date(2026, 9, 24), inputs=inputs, post=post, ready=lambda: None)


def servis_yok():
    raise RuntimeError("yok")


calls.clear()
try:
    zt.build(run, today=date(2026, 9, 24), inputs=inputs, post=post, ready=servis_yok)
    ok("tahmin servisi yoksa Logo okunmadan durur", False)
except RuntimeError:
    ok("tahmin servisi yoksa Logo okunmadan durur", calls == {}, str(list(calls)))
calls.clear(); years.clear()
fc = zt.build(run, today=date(2026, 9, 24), inputs=inputs, post=post, ready=lambda: None)
ids = [x["id"] for x in sent["series"]]
ok("havuz Baskı Tekrar + Yeni Kitap; 6 aydan kısa geçmiş (B) gönderilmez", ids == ["A", "N"] and fc["shortHistory"] == ["B"], str(ids))
a = next(x for x in sent["series"] if x["id"] == "A")
ok("A: ilk satış ayından son tam aya (Temmuz 2026), Ağustos yarım ay dahil değil",
   a["start"] == "2025-01" and len(a["values"]) == 19 and a["values"][-1] == 20.0, f"{a['start']} {len(a['values'])}")
sp = sent["shared_past"]
ok("takvim + okul zirvesi (9, 10) + portföy = bütün kodlar (havuz dışı X dahil), TimesFM 3.0",
   sent["calendar"] and sent["calendar_peak_months"] == [9, 10] and sp["start"] == "2025-01"
   and len(sp["values"]) == 19 and sp["values"][2] == 10.0 + 3.0 + 100.0 and sp["values"][-1] == 20.0 + 5.0
   and sent["engine"] == "timesfm3", f"{sp['start']} {len(sp['values'])} {sp['values'][2]} {sp['values'][-1]}")
ok("geçmiş yıl yıl okunur: 2015 … 2026", years == list(range(2015, 2027)), str(years[:2] + years[-1:]))
ok("havuz dışı kod tahmine gönderilmez", "X" not in ids and fc["sourceStats"]["logo_aylik_gecmis"]["rows"] == 45)
ok("tahmin başlangıcı Ağustos 2026, p50/p80 saklanır",
   fc["forecastStart"] == "2026-08" and fc["forecasts"]["A"]["p50"][0] == 10 and fc["forecasts"]["A"]["p80"][0] == 30)
ok("son 12 tam ay satışı (Ağu 2025 – Tem 2026)", fc["last12"]["A"] == 5 * 10.0 + 7 * 20.0, str(fc["last12"]["A"]))

# ---- sekme: bugünden itibaren tükenme, baskı ihtiyacı, öneri
today = date(2026, 9, 24)
left = zt._left_fraction(today)
ok("Eylül'ün kalanı 7/30", abs(left - 7 / 30) < 1e-9)
tekrar = [{"stok_kodu": "A", "urun_adi": "Kitap A", "yayinevi": "Timaş", "stok_adedi": 25.0, "oneri": "Takip Et",
           "ort_satis_hizi": 12.0, "tukenme_suresi": 2.08},
          {"stok_kodu": "Z", "urun_adi": "Tahminsiz", "yayinevi": "Timaş", "stok_adedi": 5.0, "oneri": "Kritik",
           "ort_satis_hizi": 3.0, "tukenme_suresi": "∞"}]
yeni = [{"stok_kodu": "N", "urun_adi": "Yeni", "yayinevi": "Timaş", "stok_adedi": 0.0, "oneri": "Risk/Acil"}]
before = copy.deepcopy((tekrar, yeni))
t = zt.tab(tekrar, yeni, {"A": 5.0}, fc, today, [{"id": "x", "title": "x", "description": "", "sql": "SELECT 1"}])
rows = {r["stok_kodu"]: r for r in t["rows"]}
A = rows["A"]
# p50 yolu bugünden: Eylül kalan 10*7/30=2,33, Ekim 10, Kasım 10 … → 25 stok: 2,33+10+10=22,33 < 25 → Aralık'ta biter
ok("Power BI satırları değişmez (sekme yalnız okur)", before == (tekrar, yeni))
ok("A: tükenme Aralık 2026, gerçek ay ≈ 2,5", A["ai_tukenme"] == "Aralık 2026" and abs(A["ai_tukenme_ay"] - 2.5) < 0.05,
   f"{A['ai_tukenme']} {A['ai_tukenme_ay']}")
ok("A: öneri ZEKI eşiğiyle (2,5 ay → Takip Et)", A["oneri"] == "Takip Et", A["oneri"])
ok("A: tahmin ufku bugünden Temmuz 2027'ye 11 ay: 2,33 + 10×10", A["ai_tahmin"] == round(10 * 7 / 30 + 100), str(A["ai_tahmin"]))
ok("A: baskı ihtiyacı = tahmin + bekleyen − stok", A["ai_baski"] == A["ai_tahmin"] + 5 - 25, str(A["ai_baski"]))
ok("A: temkinli (p80) daha erken biter", A["ai_tukenme_temkinli"] == "Ekim 2026", A["ai_tukenme_temkinli"])
ok("stoksuz yeni kitap: hemen Risk/Acil", rows["N"]["oneri"] == "Risk/Acil" and rows["N"]["liste"] == "Yeni Kitap")
ok("tahmini olmayan kitap: 'Tahmin yok', öneri boş", rows["Z"]["guven"] == "Tahmin yok" and rows["Z"].get("oneri") is None)
mk = [c for c in t["columns"] if c["key"].startswith("ai_m")]
ok("aylık tahmin kolonları bugünden ufkun sonuna (Eyl 26 … Tem 27)", len(mk) == 11 and mk[0]["label"] == "Eyl 26" and mk[-1]["label"] == "Tem 27",
   f"{len(mk)} {mk[0]['label']}…{mk[-1]['label']}")
ok("açıklama: başlık, bölümler, sınama tablosu, SQL",
   t["explain"]["title"] and len(t["explain"]["sections"]) == 3 and len(t["explain"]["table"]["rows"]) == 5
   and t["explain"]["sql"][0]["sql"] == "SELECT 1" and "Temmuz 2026" in " ".join(t["explain"]["notes"]))
empty = zt.tab(tekrar, yeni, {}, None, today, [])
ok("tahmin yokken sekme boş ve 'hazırlanıyor' der", empty["rows"] == [] and "hazırlanıyor" in empty["emptyText"])

# ---- Baskı Öneri raporu: üçüncü sekme eklenir, Power BI sekmeleri aynı kalır
spec = importlib.util.spec_from_file_location("parity", ROOT / "tests/management/baski_oneri_parity.py")
src = (ROOT / "tests/management/baski_oneri_parity.py").read_text(encoding="utf-8")
ns: dict = {"__file__": str(ROOT / "tests/management/baski_oneri_parity.py"), "__name__": "parity"}
exec(src.split("out = m.build(run, today=TODAY)")[0], ns)  # parity testinin yapay verisi
without = bo.build(ns["run"], today=ns["TODAY"])
with_fc = bo.build(ns["run"], today=ns["TODAY"], inputs={zt.REPORT_ID: fc})
ok("üç sekme: Baskı Tekrar, Yeni Kitap, ZEKI AI Tahminleme",
   [v["title"] for v in with_fc["views"]] == ["Baskı Tekrar", "Yeni Kitap", "ZEKI AI Tahminleme"])
ok("Power BI sekmeleri tahminle ve tahminsiz birebir aynı", with_fc["views"][:2] == without["views"][:2])
ok("tahminsiz kurulumda üçüncü sekme boş", without["views"][2]["rows"] == [] and without["views"][2]["emptyText"])

print("SONUÇ:", f"{sum(sonuc)}/{len(sonuc)} geçti")
raise SystemExit(0 if all(sonuc) else 1)
