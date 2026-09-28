"""Sorgu bilgisi kabulü — finansal denetim ve yönetim raporları (test sunucusunda, yan port köprüsü; yalnız okuma).

K1–K3 her uçta (kabul.py ile aynı), ve doğrudan SQL referansları:
  D1  denetim: raporun firma kopyası = Logo `L_CAPIPERIOD`'da raporun yılını tutan firma (sabit 411 değil);
  D2  denetim: «hesaplar» sorgusunun Σ satır sayısı = raporun «N hareket» rakamı;
  D3  denetim hareket ayrıntısı: uçtaki toplam = sorgunun COUNT(*) OVER() sonucu;
  Y1  Baskı Öneri: her kaynak SQL'inde yer tutucu yok ve Logo/CRM'de hatasız koşar; satır sayısı son okumayla aynı
      (okumadan sonra veri girdiyse fark UYARI).
Ortam ve kullanım kabul.py ile aynı: python kabul_denetim_yonetim.py [--skip-heavy]
"""
from __future__ import annotations

import argparse

from kabul import check, connector, contract, http, num, results, run_all


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-heavy", action="store_true")
    heavy = not ap.parse_args().skip_heavy

    from semantic_bridge import financial_audit_kaynak as FK

    st, rep = http("/api/v1/financial-audit/overview", 1800)
    if st != 200:
        check("denetim /overview", None, f"HTTP {st} (rapor hazır değil ya da yetki yok)")
    else:
        k = contract("denetim /overview", rep, FK.NOT_RAKAM)
        got = run_all("denetim /overview", k, heavy)
        periods = connector("logo").execute("SELECT FIRMNR, BEGDATE, ENDDATE FROM L_CAPIPERIOD WHERE ACTIVE = 1", 1000)[1]
        want = [f"{int(r['FIRMNR']):03d}" for r in periods if str(r["BEGDATE"])[:4] <= str(rep["year"]) <= str(r["ENDDATE"])[:4]]
        check("D1 denetim: firma kopyası yılın firması", rep.get("firm") in want, f"rapor {rep.get('firm')} · Logo {want}")
        h = got.get("denetim.hesaplar")
        if h is not None:
            total = sum(num(r.get("lineCount")) for r in h)
            check("D2 denetim: hesaplar Σ satır = «N hareket»", abs(total - num(rep.get("lineCount"))) < 0.5,
                  f"sorgu {total:,.0f} · rapor {rep.get('lineCount')}")
        acc = next((a for a in rep.get("accounts") or [] if a.get("lineCount")), None)
        if acc:
            st, lines = http(f"/api/v1/financial-audit/lines?year={rep['year']}&account={acc['accountRef']}&page=0", 900)
            if st == 200:
                k = contract("denetim /lines", lines, FK.NOT_RAKAM)
                got = run_all("denetim /lines", k, heavy)
                rows = got.get("denetim.hareket") or []
                check("D3 denetim: hareket toplamı = COUNT(*) OVER()", not rows or num(rows[0].get("totalRows")) == num(lines.get("total")),
                      f"uç {lines.get('total')} · sorgu {rows[0].get('totalRows') if rows else '—'}")
            else:
                check("denetim /lines", None, f"HTTP {st} (denetim.detay yetkisi yok olabilir)")

    from semantic_bridge.management import kaynak as MK

    st, lst = http("/api/v1/management/reports")
    contract("yönetim /reports", lst, MK.NOT_RAKAM)
    st, bo = http("/api/v1/management/reports/baski-oneri", 900)
    if not bo.get("data"):
        check("yönetim /baski-oneri", None, "rapor henüz okunmadı")
    else:
        k = contract("yönetim /baski-oneri", bo, MK.NOT_RAKAM)
        got = run_all("yönetim /baski-oneri", k, heavy)
        stats = bo["data"].get("sourceStats") or {}
        for sid, s in (k.get("sources") or {}).items():
            short = sid.rsplit(".", 1)[-1]
            if sid in got and short in stats and stats[short].get("rows") is not None:
                have, want = len(got[sid]), stats[short]["rows"]
                check(f"Y1 {short}: satır = son okuma", True if have == want else None, f"son okuma {want} · bugün {have}")

    ok = sum(1 for _, s, _ in results if s == "GEÇTİ")
    bad = sum(1 for _, s, _ in results if s == "KALDI")
    print(f"== {ok} geçti, {bad} kaldı, {sum(1 for _, s, _ in results if s == 'UYARI')} uyarı")
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
