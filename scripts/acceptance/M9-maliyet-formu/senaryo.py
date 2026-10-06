#!/usr/bin/env python3
"""Excel'lerde hiç kullanılmamış seçenekler için kabul senaryoları: gerçek bir basım Excel'inin (varsayılan Dirsek
Toplumu) girdi hücreleri değiştirilir, formüllere dokunulmaz. Sonuçları `pycel_referans.py` Excel formüllerinden
bağımsız hesaplar (test sunucusunda LibreOffice Calc kurulu değil); `kabul.py` sistemle karşılaştırır.

Denetim: `00-kontrol` değiştirilmemiş dosya (referans = Excel'in kendi sonucu olmalı); `01-adet` yalnız adedi değiştirir.

    python3 senaryo.py --taban Dirsek.xlsx --out /tmp/claude-<oturum>/senaryo
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from openpyxl import load_workbook

X = "X"
#: senaryo adı → değiştirilen hücreler (yalnız girdi hücreleri; formül hücresine yazılmaz).
SENARYOLAR: dict[str, dict[str, object]] = {
    "00-kontrol": {},
    "01-adet": {"F5": 4200},
    "02-sert-kapak-tablodan": {"A36": "SERT KAPAK CİLT"},
    "03-fleksi-tablodan": {"A36": "FLEKSİ KAPAK CİLT"},
    "04-amerikan-kulakli": {"A36": "AMERİKAN CİLT- (KULAKLI KAPAK)"},
    "05-iplik-kulakli": {"A36": "İPLİK+AMERİKAN CİLT - (KULAKLI KAPAK)"},
    "06-tel-dikis-ince": {"A36": "TEL DİKİŞ CİLT", "G4": 32},
    "07-tel-dikis-kalin": {"A36": "TEL DİKİŞ CİLT"},
    "08-cilt-yok": {"A36": "CİLT YOK"},
    "09-board-penceresiz": {"A36": "BOARD BOOK SIVAMA-PENCERESİZ", "G4": 16},
    "10-board-pencereli": {"A36": "BOARD BOOK SIVAMA-PENCERELİ", "G4": 16},
    "11-board-bristol": {"A36": "BOARD BOOK SIVAMA-BRİSTOL+MUKAVVA+BRİSTOL+PENCERELİ", "G4": 16},
    "12-ayrac": {"A13": "KİTAP KAĞIDI-60-70-80", "B30": 4, "I31": X},
    "13-ayrac-buyuk-baski": {"A13": "KİTAP KAĞIDI-60-70-80", "B30": 1, "F5": 12000},
    "14-mukavva-sert-kapak": {"A14": "2mm ESKA MUKAVVA", "A36": "SERT KAPAK CİLT"},
    "15-cilt-bezi": {"A15": "CİLT BEZİ-CİHAN"},
    "16-diger-tabaka": {"A16": "1,5mm ESKA MUKAVVA", "D16": 1},
    "17-kenar-boyama-vakum": {"E17": 0.5, "I29": X},
    "18-ic-selofan": {"B26": X},
    "19-ozel-kesim": {"B27": "BRİSTOL", "I26": 1},
    "20-simli-lak": {"A35": "Simli Lak-50x70", "B35": X},
    "21-dispersiyon-lak": {"A35": "DİSPERSİYON LAK", "B35": X},
    "22-dispersiyon-kaplama": {"A34": "DİSPERSİYON LAK", "B34": X},
    "23-ozel-iskonto": {"I4": 35},
    "24-kapak-bolen": {"D33": 2, "D34": 2},
    "25-somiz-buyuk-baski": {"A12": "MAT KUŞE", "B31": 1, "I28": X, "F5": 20000},
    "26-yan-kagit-buyuk-baski": {"A11": "1.HAMUR-120-140-150-170-200", "B32": 1, "F5": 14000},
    "27-kapak-adet-fiyatli": {"A10": "GELTEX K - 111 BEYAZ"},
    "28-tek-renk-kapak-buyuk": {"B33": 1, "F5": 30000},
    "29-yaldiz-gofre-gren-buyuk": {"B29": X, "B28": X, "I27": X, "F5": 8000},
    "30-matbaa-ayar-renkli": {"I1": -12, "D23": 32, "B23": 4, "B24": 2},
    "31-sert-kapak-ayarli": {"A36": "SERT KAPAK CİLT", "I1": 7},
    "32-dolayli-telif-yok": {"I41": None, "I35": None},
}

#: «TBK dijital» şablonu (taban: AŞIKLARIN HALLERİ-TBK DİJİTAL). Fiyatı boş ebat/kâğıt hücreleri senaryoya alınmadı:
#: Excel onları sessizce 0 ₺ sayar, sistem elle fiyat ister (bilinçli fark).
SENARYOLAR_DIJITAL: dict[str, dict[str, object]] = {
    "d00-kontrol": {},
    "d01-adet": {"F5": 1000},
    "d02-sayfa": {"G4": 352},
    "d03-ebat-15x21": {"G5": "15X21"},
    "d04-ebat-12x16": {"G5": "12X16,5"},
    "d05-ebat-13-5x19-5": {"G5": "13,5X19,5"},
    # Bilinçli fark: Excel E18 `VLOOKUP(G5; M3:X16; …)` yaklaşık eşleşmeyle sırasız tabloda arar; pycel 13,5X21 için
    # 12X16,5 satırını (0,165 ₺) bulur, tablodaki fiyat 0,17 ₺. Sistem ebatı birebir eşleştirir (2026-10-06: 22/23).
    "d06-ebat-13-5x21": {"G5": "13,5X21"},
    "d07-kagit-55": {"D18": " 1/1- 55gr KİTAP KAĞIDI"},
    "d08-kagit-70": {"D18": " 1/1- 70gr KİTAP KAĞIDI"},
    "d09-kapak-kuse": {"D28": "KUŞE"},
    "d10-ek-pay-15": {"G17": 15},
    "d11-ek-pay-yok": {"G17": None},
    "d12-ozel-iskonto": {"I4": 30},
    "d13-kesinlesen-fiyat": {"J3": 220},
    "d14-matbaa-ayar": {"I1": 10},
    "d15-ayrac": {"B21": X, "B22": 4},
    "d16-gofre-kulakli": {"B23": X, "B24": X},
    "d17-kapak-baski-selofan": {"B25": 4, "B26": X},
    "d18-lokal-lak": {"A27": "LOKAL LAK"},
    "d19-diger-giderler": {"J20": 500, "I21": 2, "J22": 300, "J23": 150, "J24": 400, "J28": 250},
    "d20-dolayli-telif-yok": {"I33": None, "I27": None},
    "d21-buyuk-baski-ekler": {"F5": 6000, "B21": X, "B22": 2, "B23": X, "B25": 4, "B26": X},
    "d22-yayinevi-akademi": {"A1": "TİMAŞ AKADEMİ"},
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--taban", required=True, help="temel Excel (formüller dokunulmadan kopyalanır)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--dijital", action="store_true", help="TBK dijital şablonunun senaryoları")
    a = ap.parse_args()
    senaryolar = SENARYOLAR_DIJITAL if a.dijital else SENARYOLAR
    out = Path(a.out)
    src = out / "girdi"
    shutil.rmtree(out, ignore_errors=True)
    src.mkdir(parents=True)
    for name, cells in senaryolar.items():
        wb = load_workbook(a.taban)  # formüller korunur; kayıtta önbellek değerleri düşer, LibreOffice yeniden hesaplar
        for ws in wb.worksheets:
            for ref, val in cells.items():
                if isinstance(ws[ref].value, str) and str(ws[ref].value).startswith("="):
                    raise SystemExit(f"{name}: {ref} formül hücresi, girdi değil")
                ws[ref].value = val
        wb.save(src / f"{name}.xlsx")
    print(f"{len(senaryolar)} senaryo dosyası → {src} (hesap: pycel_referans.py --senaryo)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
