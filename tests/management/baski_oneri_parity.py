"""Yeni Baskı Öneri raporu — Power BI şablonuyla davranış eşliği (yapay veri, veritabanı gerekmez).

Şablondan (`docs/analiz/pbit-yeni-baski-oneri/`) okunan kurallar burada sabittir: ağırlıklı hız,
tükenme/marj eşikleri, açılış dilimleyicileri, satışı olmayan kitabın havuzda kalması ve DAX'ın
bölen-yok davranışı. Koşturma:  python3 tests/management/baski_oneri_parity.py
"""
import importlib.util
from datetime import date
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "baski_oneri", Path(__file__).resolve().parents[2] / "backend/semantic_bridge/management/baski_oneri.py")
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)

TODAY = date(2026, 9, 23)
ESKI = "2024-01-15"          # baskı tarihi eşiğinin altında → Baskı Tekrar havuzunda
YENI_BASKI = "2026-09-01"    # eşiğin üstünde → havuza girmez

def kitap(kod, *, stok, yayinevi="Timaş", statu="YS04 Aktif", durum="Depo Girişi Yapıldı", baski=ESKI):
    return {"stok_kodu": kod, "urun_adi": f"Kitap {kod}", "statu": statu, "yazar": "Y", "yayinevi": yayinevi,
            "kitaplik": "K", "dizi_tur": "D", "sayfa_sayisi": 100, "uzeri_fiyat": 10, "baski_tarihi": baski,
            "stok_adedi": stok, "baski_durum": durum, "son_baski_tarihi": baski, "baski_adet": 1000}

def hiz(kod, ceyrek1=0.0):
    z = {c: 0.0 for c, _ in m.WEIGHTS}
    z["ceyrek1_ort"] = ceyrek1
    return {"stok_kodu": kod, "yillik_toplam": ceyrek1 * 3, **z}

DATA = {
    "crm_kitap": [
        kitap("A", stok=300),                                  # canlı satış, stok 6 aylık
        kitap("H", stok=60),                                   # canlı satış, stok 1,2 aylık
        kitap("I", stok=80),                                   # iadesi satışından fazla: hız eksi
        kitap("B", stok=500),                                  # son 12 ayda satış yok, stok var
        kitap("C", stok=0),                                    # satış yok, stok da yok
        kitap("D", stok=100, statu="YS02 Pasif"),              # açılış süzgeci dışı statü
        kitap("E", stok=100, durum="Baskıda"),                 # açılış süzgeci dışı baskı durumu
        kitap("F", stok=100, yayinevi="Sincap Kitap"),         # yayınevi hariç
        kitap("G", stok=100, baski=YENI_BASKI),                # baskı tarihi eşiğin üstünde
        kitap("N1", stok=400, baski=ESKI),                     # yeni kitap kartı
        kitap("N2", stok=0, baski=ESKI),
    ],
    # B ve C: 2024'te satmış, son 12 ayda sıfır → yeni havuzda satır var, dönemleri 0
    "logo_satis_hizi": [hiz("A", 100.0), hiz("H", 100.0), hiz("I", -20.0), hiz("B"), hiz("C"), hiz("D"), hiz("E"), hiz("F"), hiz("G")],
    "logo_aylik_satis": [{"stok_kodu": "A", "ay": 9, "miktar": 120}],
    "logo_fiyat": [{"stok_kodu": "A", "son_fiyat_degisikligi": "2026-01-01"}],
    "logo_depo_stok": [{"stok_kodu": "A", "depo_stok": 280}],
    "crm_bekleyen_siparis": [{"stok_kodu": "A", "bekleyen_siparis": 40}],
    "crm_baski_onerisi": [{"stok_kodu": "A", "oneri_adet": 3000}],
    # N1: bu ay yayımlandı (satış süresi 0). N2: bu ay yayımlandı, stok yok.
    "crm_yeni_kitap": [{"stok_kodu": "N1", "ilk_yayin_tarihi": "2026-09-05"},
                       {"stok_kodu": "N2", "ilk_yayin_tarihi": "2026-09-05"}],
    "logo_yeni_kitap_satis": [{"stok_kodu": "N1", "gun": "2026-09-10", "miktar": 50},
                              {"stok_kodu": "N2", "gun": "2026-09-10", "miktar": 10}],
}

def run(source_id, params=None):
    return {"records": DATA[source_id], "columns": [], "dbMs": 1}

out = m.build(run, today=TODAY)
views = {v["id"]: v for v in out["views"]}

def satirlar(v):
    ix = {c["key"]: i for i, c in enumerate(v["columns"])}
    return {r[ix["stok_kodu"]]: {k: r[i] for k, i in ix.items()} for r in v["rows"]}

t = satirlar(views["tekrar"])
y = satirlar(views["yeni"])

def ok(ad, kosul, gorulen=""):
    print(("GEÇTİ  " if kosul else "DÜŞTÜ  ") + ad + (f"   → {gorulen}" if gorulen else ""))
    return kosul

hepsi = []
print("== Baskı Tekrar havuzu:", sorted(t))
hepsi.append(ok("A: ağırlıklı hız 50, tükenme 6 ay, marj 5, öneri Yeterli Stok",
                t["A"]["ort_satis_hizi"] == 50.0 and t["A"]["tukenme_suresi"] == 6.0
                and t["A"]["marj"] == 5.0 and t["A"]["oneri"] == "Yeterli Stok", t["A"]["oneri"]))
hepsi.append(ok("H: tükenme 1,2 ay, marj 0,2, öneri Kritik",
                t["H"]["tukenme_suresi"] == 1.2 and t["H"]["marj"] == 0.2
                and t["H"]["oneri"] == "Kritik", t["H"]["oneri"]))
hepsi.append(ok("I: eksi hız → tükenme eksi (Power BI gibi), öneri Risk/Acil",
                t["I"]["ort_satis_hizi"] == -10.0 and t["I"]["tukenme_suresi"] == -8.0
                and t["I"]["oneri"] == "Risk/Acil", f"{t['I']['tukenme_suresi']} {t['I']['oneri']}"))
hepsi.append(ok("B satışsız + stoklu: havuzda, hız 0, öneri Yeterli Stok",
                "B" in t and t["B"]["ort_satis_hizi"] == 0 and t["B"]["tukenme_suresi"] is None
                and t["B"]["oneri"] == "Yeterli Stok", t.get("B", {}).get("oneri")))
hepsi.append(ok("C satışsız + stoksuz: marj -1, öneri Risk/Acil",
                t["C"]["marj"] == -1.0 and t["C"]["oneri"] == "Risk/Acil", t["C"]["oneri"]))
hepsi.append(ok("F yayınevi hariç tutuldu", "F" not in t))
hepsi.append(ok("G baskı tarihi eşiğin üstünde, havuzda değil", "G" not in t))
hepsi.append(ok("D pasif statü satırı havuzda (süzgeç ekranda)", "D" in t))
hepsi.append(ok("E farklı baskı durumu havuzda (süzgeç ekranda)", "E" in t))
sira = [r[0] for r in views["tekrar"]["rows"]]
hepsi.append(ok("sıralama: en önce tükenen üstte, satışsızlar en sonda",
                sira[:3] == ["I", "H", "A"] and all(t[k]["tukenme_suresi"] is None for k in sira[3:]),
                " ".join(sira)))

df = {d["key"]: d["values"] for d in views["tekrar"]["defaultFilters"]}
hepsi.append(ok("açılış süzgeci: statü 3 değer, boş dahil",
                df.get("statu") == [None, "YS04 Aktif", "YS10A Ürün Fazlası - Stok Eritilecek Ürün (Yeniden Basılabilir)"]))
hepsi.append(ok("açılış süzgeci: baskı durumu 2 değer, boş dahil",
                df.get("baski_durum") == [None, "Depo Girişi Yapıldı"]))
hepsi.append(ok("açılış süzgeci D ve E'yi gizler",
                all(any((v or "") == (t[k]["statu"] if key == "statu" else t[k]["baski_durum"]) or False
                        for v in vals) is False or True for key, vals in df.items() for k in ("D", "E"))
                and t["D"]["statu"] not in [v or "" for v in df["statu"]]
                and t["E"]["baski_durum"] not in [v or "" for v in df["baski_durum"]]))
hepsi.append(ok("Yeni Kitap görünümünde açılış süzgeci yok", views["yeni"]["defaultFilters"] == []))

print("== Yeni Kitap havuzu:", sorted(y))
hepsi.append(ok("N1 bu ay yayımlandı, stoklu: satış süresi 0, öneri Yeterli Stok",
                y["N1"]["satis_suresi"] == 0 and y["N1"]["son_bir_yil_ort"] is None
                and y["N1"]["oneri"] == "Yeterli Stok", y["N1"]["oneri"]))
hepsi.append(ok("N2 bu ay yayımlandı, stoksuz: marj -1, öneri Risk/Acil",
                y["N2"]["marj"] == -1.0 and y["N2"]["oneri"] == "Risk/Acil", y["N2"]["oneri"]))
hepsi.append(ok("N1 dağılım satışı ilk yayın ayından", y["N1"]["dagilim_satis"] == 50))

print("\nNOT sayısı:", len(m.NOTES), "| FORMÜL sayısı:", len(m.FORMULAS), "| KAYNAK sayısı:", len(m.SOURCES))
print("SONUÇ:", f"{sum(hepsi)}/{len(hepsi)} geçti")
raise SystemExit(0 if all(hepsi) else 1)
