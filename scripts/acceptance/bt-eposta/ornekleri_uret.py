#!/usr/bin/env python3
"""Bilgi İşlem e-posta örnekleri: beş bildirimin (ve düzelme/günlük eşlerinin) HTML ve düz metin çıktısı.

Veritabanına, CRM'e ya da posta sunucusuna gitmez: bildirimler, uygulamanın kullandığı aynı kurucu işlevlerle örnek
satırlardan kurulur (`it_ops.down_notice` … `crm_unassigned.notice`), yalnız şablon çıktısı dosyaya yazılır.

    cd backend && python3 ../scripts/acceptance/bt-eposta/ornekleri_uret.py            # docs/analiz/bt-eposta-ornekleri/
    cd backend && python3 ../scripts/acceptance/bt-eposta/ornekleri_uret.py --out /tmp/x

Gerçek verili sürüm test sunucusunda `kabul.py` ile (canlı tablolardan kurulur, referans SQL ile karşılaştırılır).
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

from semantic_bridge import crm_unassigned as CU  # noqa: E402
from semantic_bridge import data_security as D  # noqa: E402
from semantic_bridge import ic_bildirim as IB  # noqa: E402
from semantic_bridge import it_ops as I  # noqa: E402
from semantic_bridge import mailbox as M  # noqa: E402

LOCAL = timezone(timedelta(hours=3))
LINK = "https://portal.timas.com.tr/timas/uyarilar"
ST = {"logoStaleDays": 3, "crmStaleHours": 24}


def t(day: int, hh: int, mm: int, month: int = 9) -> datetime:
    return datetime(2026, month, day, hh, mm, tzinfo=LOCAL)


def inc(ring: str, opened: datetime, closed: datetime | None = None, err: str = "", kind: str = "kopma") -> dict:
    return {"id": f"{ring}-{kind}", "ring": ring, "kind": kind, "opened_at": opened, "closed_at": closed,
            "first_error": err, "last_error": err}


def samples() -> dict[str, tuple[IB.Notice, list]]:
    out: dict[str, tuple[IB.Notice, list]] = {}
    # 1) ITOPS_RECIPIENTS — kopma ve düzelme
    logo = inc("logo", t(29, 9, 42), err="Bağlantı zaman aşımına uğradı (sunucu 60 sn içinde yanıt vermedi).")
    out["1a-kesinti-logo"] = (I.down_notice(None, "timas", [logo], t(29, 9, 52), LINK, fail_counts={"logo": 3}), [])
    out["1b-duzeldi-logo"] = (I.fixed_notice([dict(logo, closed_at=t(29, 10, 27))], t(29, 10, 27), LINK), [])
    stale = inc("logo", t(29, 8, 5), kind="tazelik", err="Logo veri sonu 17.08.2026")
    out["1c-uyari-logo-verisi-eski"] = (I.stale_notice(None, "timas", [stale], ST, t(29, 8, 5), LINK,
                                                       data_ends={"logo": t(17, 21, 0, month=8)}), [])
    # 2) ITOPS_WEEKLY_TO — haftalık sağlık özeti
    dt = {r["id"]: {"count": 0, "minutes": 0} for r in I.RINGS}
    dt["logo"] = {"count": 1, "minutes": 45}
    dt["vpn"] = {"count": 2, "minutes": 18}
    jobs = [{"label": "Birlikte alınan yazarlar", "lastAt": t(28, 3, 0).isoformat(),
             "lastError": "Son koşu başarısız (zaman aşımı)."}]
    out["2-haftalik-sistem-sagligi"] = (I.weekly_notice(None, "timas", t(29, 8, 0), jobs, LINK, dt=dt, still=[stale]), [])
    # 3) SECURITY_ALERT_RECIPIENTS — güvenlik uyarısı ve günlük erişim özeti
    alert = {"id": 1, "rule": "hatali_giris", "username": "ahmet.yilmaz", "severity": "kritik",
             "summary": "«ahmet.yilmaz» hesabına 29.09.2026 09:31–29.09.2026 09:38 arasında 7 hatalı giriş denendi "
                        "(eşik: 10 dakikada 5); kaynak adres: 10.0.4.27."}
    out["3a-guvenlik-uyarisi"] = (D.alert_notice([alert], IB.portal_link(LINK, "veri-guvenligi"), t(29, 9, 40)), [])
    counts = {"ayse.demir": {"forbidden": 6, "not_permitted": 1}, "mehmet.kaya": {"forbidden": 2, "not_permitted": 0},
              "zeynep.ak": {"forbidden": 0, "not_permitted": 3}}
    out["3b-guvenlik-gunluk-ozet"] = (D.digest_notice_from(counts, t(29, 8, 0), IB.portal_link(LINK, "veri-guvenligi")), [])
    # 4) MAIL_CONNECTION_ALERT_TO — kurumsal e-posta kutusu bağlantısı
    out["4a-kesinti-eposta-kutusu"] = (M.connection_down_notice("timas@timas.com.tr", t(29, 9, 12), t(29, 9, 45),
                                                                "Kutuya erişim reddedildi: hizmet hesabının yetkisi yok.",
                                                                LINK), [])
    out["4b-duzeldi-eposta-kutusu"] = (M.connection_fixed_notice("timas@timas.com.tr", t(29, 9, 12), t(29, 11, 17),
                                                                 t(29, 11, 20), LINK), [])
    # 5) CRM_UNASSIGNED_TO — departmansız CRM kullanıcıları (Excel ekli)
    rows = [{"name": "Ali Kaya", "account": "ali.kaya", "adUnit": "Satış", "email": "", "created": "2025-01-02",
             "mainRoles": ["07-Temel Rol"], "roles": ["07-Temel Rol"], "crmUnit": "Timaş"},
            {"name": "Elif Şahin", "account": "elif.sahin", "adUnit": "Satış", "email": "", "created": "2025-06-11",
             "mainRoles": [], "roles": [], "crmUnit": "Timaş"},
            {"name": "Eski Hesap", "account": "eski.hesap", "adUnit": CU.NO_AD, "email": "", "created": "2019-03-04",
             "mainRoles": [], "roles": [], "crmUnit": "Timaş"},
            {"name": "Can Yıldız", "account": "can.yildiz", "adUnit": "Editörlük", "email": "", "created": "2024-11-20",
             "mainRoles": ["Editör"], "roles": ["Editör"], "crmUnit": "Timaş"}]
    now = datetime(2026, 9, 29, 7, 0)
    out["5-crm-departmansiz-kullanicilar"] = (CU.notice(rows, now, LINK), [
        (f"CRM-departmansiz-kullanicilar-{now:%Y-%m-%d-%H%M}.xlsx", CU.xlsx(rows, now, minimal=True), CU.XLSX_MIME)])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs" / "analiz" / "bt-eposta-ornekleri"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    index = []
    for name, (n, att) in samples().items():
        bad = IB.tech_words(IB.render_html(n) + IB.render_text(n))
        if bad:
            raise SystemExit(f"{name}: teknoloji adı kaldı: {bad}")
        (out / f"{name}.html").write_text(IB.render_html(n), encoding="utf-8")
        (out / f"{name}.txt").write_text(IB.render_text(n), encoding="utf-8")
        index.append((name, n.subject, [a[0] for a in att]))
    lines = ["# Bilgi İşlem e-posta örnekleri", "",
             "`scripts/acceptance/bt-eposta/ornekleri_uret.py` üretir (örnek satırlar, gerçek veri değil). Her bildirim "
             "iki biçimde gider: `.html` (e-posta istemcisi) ve `.txt` (düz metin karşılığı).", "",
             "| Dosya | Konu satırı | Ek |", "| --- | --- | --- |"]
    lines += [f"| `{name}.html` | {subj} | {', '.join(a) or '—'} |" for name, subj, a in index]
    (out / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for name, subj, _ in index:
        print(f"{name}: {subj}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
