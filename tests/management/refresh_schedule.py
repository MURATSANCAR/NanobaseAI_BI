"""Yönetim raporları — okuma zamanlaması: 5 dk aralık okumanın başından sayılır (DB gerektirmez).

Koşturma (fastapi kurulu ortamda):  python3 tests/management/refresh_schedule.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from semantic_bridge.management import MIN_GAP_SECONDS, REFRESH_SECONDS, _next_due, retry_text  # noqa: E402

sonuc = []


def ok(ad, kosul, gorulen=""):
    print(("GEÇTİ  " if kosul else "DÜŞTÜ  ") + ad + (f"   → {gorulen}" if gorulen else ""))
    sonuc.append(kosul)


T = 1_000_000.0
ok("varsayılan aralık 300 sn, en kısa ara 60 sn", (REFRESH_SECONDS, MIN_GAP_SECONDS) == (300, 60))
ok("hiç okunmadıysa hemen okunur", _next_due({}) is None)
ok("2 dk süren okuma: sonraki başlangıçtan 5 dk sonra (bitişten 3 dk sonra)",
   _next_due({"startedAt": T, "updatedAt": T + 120}) == T + 300)
ok("7 dk süren okuma: bitişten 1 dk sonra, üst üste binmez",
   _next_due({"startedAt": T, "updatedAt": T + 420}) == T + 480)
ok("başarısız okuma da aynı kurala uyar",
   _next_due({"startedAt": T, "failedAt": T + 30}) == T + 300)
ok("eski önbellek (startedAt yok): bitişten 5 dk sonra", _next_due({"updatedAt": T}) == T + 300)
ok("başarıdan sonraki hata: en yeni bitiş sayılır",
   _next_due({"startedAt": T + 600, "updatedAt": T, "failedAt": T + 900}) == T + 960)
ok("gecelik rapor başarılıysa 24 saat bekler",
   _next_due({"startedAt": T, "updatedAt": T + 2000}, 86400) == T + 86400)
ok("gecelik rapor hata verdiyse 30 dk sonra yeniden dener",
   _next_due({"startedAt": T, "failedAt": T + 600}, 86400) == T + 1800)
ok("gecelik rapor uzun sürüp hata verdiyse bitişten en az 1 dk sonra",
   _next_due({"startedAt": T, "failedAt": T + 2000}, 86400) == T + 2060)
ok("eski başarı + yeni hata: hata sayılır",
   _next_due({"startedAt": T + 90000, "updatedAt": T, "failedAt": T + 90100}, 86400) == T + 91800)

ok("bağımlı rapor bekleniyorsa gecelik rapor 1 dk sonra yeniden dener (30 dk değil)",
   _next_due({"startedAt": T, "failedAt": T - 500, "waitingAt": T + 2}, 86400) == T + 2 + MIN_GAP_SECONDS)
ok("bekleme sonrası başarı: normal aralığa döner",
   _next_due({"startedAt": T + 100, "updatedAt": T + 900, "waitingAt": T + 2}, 86400) == T + 100 + 86400)
ok("bekleme sonrası hata: hata aralığı (30 dk)",
   _next_due({"startedAt": T + 100, "failedAt": T + 200, "waitingAt": T + 2}, 86400) == T + 1900)
ok("hata metni 5 dk'lık raporda 'Beş dakikada bir'", retry_text(type("R", (), {})) == "Beş dakikada bir yeniden denenir.")
ok("hata metni gecelik raporda gerçek süreyi söyler (30 dk)",
   retry_text(type("R", (), {"REFRESH_SECONDS": 86400})) == "30 dakikada bir yeniden denenir.")

print("SONUÇ:", f"{sum(sonuc)}/{len(sonuc)} geçti")
raise SystemExit(0 if all(sonuc) else 1)
