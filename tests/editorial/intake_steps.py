"""Yazar giriş süreci — adım kuralları (DB gerektirmez).

Kurallar `backend/semantic_bridge/editorial_intake.py` başındaki tabloda; buradaki vakalar canlı CRM'de
2026-09-24'te görülen durumlardan (statü güncellenmeden kurulda kabul, erken açılan stok/kişi kartı…).

Koşturma (sqlalchemy kurulu ortamda):  python3 tests/editorial/intake_steps.py
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from semantic_bridge import editorial_intake as m  # noqa: E402

sonuc = []


def ok(ad, kosul, gorulen=""):
    print(("GEÇTİ  " if kosul else "DÜŞTÜ  ") + ad + (f"   → {gorulen}" if gorulen else ""))
    sonuc.append(kosul)


def proje(**kw):
    base = {"id": "a" * 8 + "-0000-0000-0000-" + "0" * 12, "name": "Deneme", "author": "Yazar", "authorCard": False,
            "editor": None, "editorAccount": None, "statusCode": 100000011, "reportCode": 1, "createdOn": "2026-09-01",
            "modifiedOn": "2026-09-01", "bookId": None, "boardOn": None, "boardCode": None, "boardCount": 0,
            "contracts": 0, "contractOn": None, "participations": 0, "participationOn": None, "productionOn": None,
            "editorOn": None, "reportOn": None}
    base.update(kw)
    return base


BUGUN = date(2026, 9, 24)


def ozet(f, marks=None):
    return m.summarize(f, marks or {}, BUGUN, 14)


x = ozet(proje())
ok("yeni başvuru, editörsüz: 2. adım, 23 gündür, gecikti", (x["step"], x["phase"], x["waitingDays"], x["late"]) == (2, 1, 23, True), x)

x = ozet(proje(editor="Zeynep", editorOn="2026-09-20"))
ok("editör atanmış: 3. adım, bekleme atamadan sayılır", (x["step"], x["waitingDays"], x["late"]) == (3, 4, False), x)

x = ozet(proje(editor="Zeynep"), {3: {"on": "2026-09-22"}})
ok("portalda rapor bitti: 4. adım, evre 2", (x["step"], x["phase"]) == (4, 2), x)

x = ozet(proje(editor="Zeynep", reportCode=3))
ok("CRM'de iç rapor tamamlandı: 4. adım", x["step"] == 4, x)

x = ozet(proje(boardCount=1, boardCode=100000002, boardOn="2026-09-22"))
ok("kurula çıktı, yeniden değerlendirme: 5. adımda, karar yazılı", (x["step"], x["line"]) == (5, "Kurul kararı: yeniden değerlendirme"), x)

steps, _ = m.steps_of(proje(boardCount=1, boardCode=100000002), {})
ok("kurul kaydı varsa 2–3 çıkarımla geçilmiş", [s["source"] for s in steps[1:4]] == ["cikarim", "cikarim", "crm"], [s["source"] for s in steps])

x = ozet(proje(statusCode=100000011, boardCount=1, boardCode=1, boardOn="2026-09-22"))
ok("statü güncellenmemiş ama kurul Kabul: 6. adım (evre 3)", (x["step"], x["phase"]) == (6, 3), x)

x = ozet(proje(authorCard=True, bookId="b", productionOn="2026-09-02", contracts=1, participations=2))
ok("onaysız projede erken açılmış kişi/stok kartı süreci ilerletmez", x["step"] == 2, x)

f = proje(statusCode=100000019, editor="Z", authorCard=True, bookId="b", contracts=1, contractOn="2026-09-10",
          participations=3, participationOn="2026-09-05", productionOn="2026-09-12")
x = ozet(f)
ok("iş planı çalışıyor + bütün kanıt: tamamlandı", (x["step"], x["complete"], x["done"]) == (None, True, 9), x)
steps, _ = m.steps_of(f, {})
ok("6. adım kanıtsız, 8/9'dan çıkarılır", steps[5]["source"] == "cikarim", steps[5])

x = ozet(proje(statusCode=100000019, authorCard=True, bookId="b", contracts=0, participations=1))
ok("onaylı, sözleşmesiz: 6. adımda bekler (yazara bilgi yok)", x["step"] == 6, x)
x = ozet(proje(statusCode=100000019, authorCard=True, bookId="b", contracts=0, participations=1), {6: {"on": "2026-09-23"}})
ok("bildirildi işaretiyle 8. adım (sözleşme eksik)", x["step"] == 8, x)

x = ozet(proje(boardCount=1, boardCode=100000000, boardOn="2026-09-22"))
ok("kurul Red: süreçten çıkar", (x["outcome"], x["line"], x["waitingDays"]) == ("red", "Kurul reddetti", None), x)
x = ozet(proje(statusCode=100000021))
ok("statü iptal: süreçten çıkar", x["outcome"] == "iptal", x)

pano = m.board({"facts": [proje(id="1", editor="Z", editorAccount="zeynep"), proje(id="2"), proje(id="3", statusCode=100000021)],
                "since": "2025-01-01"}, {}, "Zeynep", today=BUGUN, late_days=14)
ok("pano: sürenler 2, kapanan 1", (len(pano["items"]), len(pano["closed"])) == (2, 1))
ok("pano: oturumdaki editörün işi (büyük/küçük harf duyarsız)", [t["id"] for t in pano["todo"]] == ["1"], pano["todo"])
ok("pano: editör hesabı dışarı verilmez", all("editorAccount" not in x for x in pano["items"]))
ok("pano: evre sayıları", [p["count"] for p in pano["phases"]] == [2, 0, 0], pano["phases"])
ok("CRM hesabı → portal kullanıcısı", m._account("TIMAS\\MuratSancar") == "muratsancar")

try:
    m.facts_sql("Timas_MSCRM.dbo", "2025-01-01'; DROP")
    ok("başlangıç tarihi SQL'e ham girmez", False)
except m.IntakeError:
    ok("başlangıç tarihi SQL'e ham girmez", True)

print("SONUÇ:", f"{sum(sonuc)}/{len(sonuc)} geçti")
raise SystemExit(0 if all(sonuc) else 1)
