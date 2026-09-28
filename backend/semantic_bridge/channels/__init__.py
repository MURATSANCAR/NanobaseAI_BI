"""Platform ve kanal paketi: M42 (diğer pazar yerleri ve D2C) ile kuruldu; M40 Trendyol ve M41 Amazon aynı pakete
dosya ekleyerek gelir.

- `sql/*.sql`     — Logo/CRM okumaları (M34 pazar yeri sell-in aynı `logo_eticaret_cari.sql`'i kullanır).
- `sources.py`    — okuma; Logo yıl/firma bulma M46 `budget_sources` ile.
- `store.py`      — tablolar (`semantic_channel_*`), ayar, önbellek, eşleme ve öneri kayıtları.
- `mapping.py`    — cari ↔ platform, kanal kodu ↔ platform, CRM hedef bölgesi ↔ platform (aday + kullanıcı onayı).
- `refresh.py`    — arka plan okuması ve kapsam.
- `scorecard.py`  — karne, kanal detayı, kitap × kanal matrisi, hedef ↔ gerçekleşen, iskonto simülasyonu.
- `d2c.py`        — timas.com.tr payı, D2C'de oransal güçlü kitaplar, site müşterisi özeti (H3 tabloları), set önerisi.
- `imports.py`    — panel dışa aktarımı (Excel/CSV) yükleme; kişisel kolon içeri alınmaz.
- `platforms.py`  — satıcı API istemcileri için salt okunur taban sınıf (M40/M41).
- `report.py`     — haftalık uyarı, aylık karne e-postası, Excel.
- `api.py`        — uçlar `/api/v1/channels/*`.

app.py'de iki satır:
    from semantic_bridge import channels
    app.state.channels = channels.register(app, rt, _require_caller, _can)
"""
from __future__ import annotations

from typing import Any, Callable


def register(app, rt: Callable[[], Any], require_caller: Callable[..., None], can: Callable[[str, str], bool]) -> dict[str, Any]:
    from semantic_bridge.channels import api

    return api.register(app, rt, require_caller, can)
