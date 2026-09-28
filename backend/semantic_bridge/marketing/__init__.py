"""Pazarlama çekirdeği ve modülleri (M15 yeni kitap planı; M16 lansman, M17 backlist, M18 aylık plan aynı çekirdeğe
dosya ekleyerek gelir).

- `core.py`    — tablolar (`semantic_mkt_*`), plan durum makinesi, satır/takvim/materyal, geçmiş, iş kuyruğu, sözleşme.
- `sources.py` — CRM okuma (yalnız okuma); Logo rakamları M46 ve M10 önbelleğinden.
- `plans.py`   — M15: plan bekleyen yeni kitaplar, karne, bütçe/kanal önerisi, takvim, Zeki AI metinleri, CRM listesi.
- `guard.py`   — Zeki AI metin denetimi (alıntı birebir, rakam kaynaklı, kanıtsız iddia yok, teknoloji adı yok).
- `export.py`  — PDF, CSV, yayına hazır paket.
- `api.py`     — uçlar `/api/v1/marketing/*`.
- `monthly.py` — M18: aylık plan (takvim, çakışma, yeni kitap / backlist bütçe dağılımı, önceki ay özeti).
- `foy.py`, `foy_pdf.py` — M18: satış föyü (CRM alanları, fiyat/barkod uyumsuzluğu, onay, paket PDF/zip).
- `monthly_api.py` — M18 uçları (`/months/*`, `/foy*`), api.register içinden bağlanır.
- `launch*.py` — M16 lansman: paket, kontrol listesi, ilk 7/30 gün izleme, D+7/D+30 raporu (`/api/v1/marketing/launches*`).

app.py'de iki satır:
    from semantic_bridge import marketing
    app.state.marketing = marketing.register(app, rt, _require_caller, _can)
"""
from __future__ import annotations

from typing import Any, Callable


def register(app, rt: Callable[[], Any], require_caller: Callable[..., None], can: Callable[[str, str], bool]) -> dict[str, Any]:
    from semantic_bridge.marketing import api, backlist_api, launch_api

    out = api.register(app, rt, require_caller, can)
    out["launch"] = launch_api.register(app, rt, require_caller, can, out)  # M16
    # M17 Backlist (`backlist*.py`, `books.py`): /api/v1/marketing/backlist*, çekirdeğin CRM okuyucusu ve iş havuzuyla.
    out["backlist"] = backlist_api.register(app, rt, require_caller, can, out)
    return out
