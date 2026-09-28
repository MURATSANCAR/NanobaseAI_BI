"""M27 Fuar, etkinlik ve ödül — gerçek API ↔ doğrudan SQL kabulü (test sunucusunda, yan port köprüsü, salt okunur kaynaklar).

Uçların kullanıcıya verdiği sonuç, köprü kodu kullanılmadan yazılmış doğrudan Logo/CRM sorgularıyla karşılaştırılır
(`referans.sql` R1–R8). Pencere ve cari sabit değildir: varsayılan pencere Logo veri sonuna biten 9 gün, cari o
pencerede fuar kanalında en çok satan cari (ikisi de her koşuda veriden okunur; `--bas/--bit/--cariler` ile verilebilir).

Salt okunur kontroller: R4 (tip eşlemesinde «fuar» kararı varsa), R5, R6, R7 (uç), R8. `--write` ile bir deneme fuar
kartı açılır (kimliği `--out` dosyasına yazılır), sonucu hesaplatılır (R1, R2, R3, R7), yetki denemeleri yapılır ve kart
API'den silinir; kalan değişiklik kaydı satırlarını `cleanup.py` siler.

Ortam: BASE (ör. http://127.0.0.1:8798), COOKIE (timasai'nin 15 dk'lık oturum çerezi), KISI (oturumun AD hesabı;
varsayılan timasai), SEMANTIC_CONNECTION_FILE (Logo), SEMANTIC_CRM_CONNECTION_FILE, PYTHONPATH=<aday ağaç>/backend.
Kullanım: python kabul.py [--write] [--firma 411] [--bas 2026-08-09 --bit 2026-08-17 --cariler 120.FUAR.01]
          --out /tmp/claude-m27/kabul-kimlikler.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

from semantic_layer.profiler.connectors import connector_from_file

BASE = os.environ.get("BASE", "http://127.0.0.1:8798").rstrip("/")
COOKIE = os.environ.get("COOKIE", "")
KISI = os.environ.get("KISI", "timasai").lower()
P = BASE + "/api/v1/events"
S = os.environ.get("CRM_SCHEMA", "Timas_MSCRM.dbo")
results: list[tuple[str, str, str]] = []


def http(method: str, url: str, body=None, timeout=900, cookie=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Cookie": cookie if cookie is not None else COOKIE, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = r.read()
            return r.status, (json.loads(payload) if payload[:1] in (b"{", b"[") else payload)
    except urllib.error.HTTPError as e:
        payload = e.read()
        try:
            return e.code, json.loads(payload)
        except ValueError:
            return e.code, payload


def check(name: str, ok, detail: str = "") -> None:
    st = "GEÇTİ" if ok is True else ("KALDI" if ok is False else "DOĞRULANAMADI")
    results.append((name, st, detail))
    print(f"[{st}] {name}" + (f" — {detail}" if detail else ""), flush=True)
    if len(results) % 10 == 0:
        print(f"-- ara durum: {sum(1 for r in results if r[1] == 'GEÇTİ')} geçti, "
              f"{sum(1 for r in results if r[1] == 'KALDI')} kaldı, {sum(1 for r in results if r[1] == 'DOĞRULANAMADI')} doğrulanamadı", flush=True)


def runner(path: str):
    conn = connector_from_file(path)
    conn.query_timeout = 1800

    def run(sql: str) -> list[dict]:
        _, rows, trunc = conn.execute(sql, 5_000_000)
        assert not trunc, "referans sorgusu kesildi"
        return [{str(k).lower(): v for k, v in r.items()} for r in rows]
    return run


def q(v) -> str:
    return "N'" + str(v).replace("'", "''") + "'"


def tr(day: str) -> str:
    """İstanbul günü → UTC sınırı (SQL Server'ın kendi saat dilimi çevirisiyle; köprü kodu kullanılmaz)."""
    return f"CAST(CAST('{day}' AS datetime2) AT TIME ZONE 'Turkey Standard Time' AT TIME ZONE 'UTC' AS datetime)"


def day_of(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return str(v)[:10]


def close(a: float, b: float, tol: float = 0.01) -> bool:
    return abs(float(a or 0) - float(b or 0)) <= tol


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--firma", default="411")
    ap.add_argument("--bas", default="")
    ap.add_argument("--bit", default="")
    ap.add_argument("--cariler", default="")
    a = ap.parse_args()
    logo = runner(os.environ["SEMANTIC_CONNECTION_FILE"])
    crm = runner(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))
    F = a.firma
    created: dict[str, list[str]] = {"fairs": [], "tasks": [], "costs": [], "authors": []}
    t0 = time.time()

    s, meta = http("GET", P + "/meta")
    if s != 200:
        print(f"meta {s}: oturum geçersiz ya da sayfa yetkisi yok — {meta}")
        return 2
    print(f"meta {round(time.time() - t0, 1)} sn; kanal {meta['settings']['channel']}, ajanda {meta['settings']['agendaDays']} gün")
    channel = meta["settings"]["channel"]

    # R7 · veri sonu
    ref_end = day_of(logo(f"SELECT MAX(DATE_) AS son FROM dbo.LG_{F}_01_INVOICE WHERE CANCELLED = 0")[0]["son"])
    print(f"Logo veri sonu (R7): {ref_end}")

    # R8 · tip sayısı
    n_types = int(crm(f"SELECT COUNT(*) AS n FROM {S}.new_etkinliktipiBase")[0]["n"])
    s, tm = http("GET", P + "/type-map", timeout=1800)
    check("R8 etkinlik tipi sayısı", s == 200 and tm["counts"]["total"] == n_types,
          f"ekran {tm['counts']['total'] if s == 200 else s} / SQL {n_types}; karar {tm['counts']['decided'] if s == 200 else '—'}")

    # R4 · takvim: «fuar» kararı verilen tiplerde, en yoğun ayın sayısı
    fuar_types = [r["id"] for r in tm["items"] if r["class"] == "fuar"] if s == 200 else []
    if not fuar_types:
        check("R4 takvim fuar sayısı", None, "tip eşlemesinde henüz «fuar» kararı yok; eşleme yapılınca yeniden koşun")
    else:
        ids = ", ".join(f"'{t}'" for t in fuar_types)
        yr = int((ref_end or str(date.today()))[:4])
        busiest = crm(f"SELECT TOP 1 MONTH(DATEADD(hour, 3, e.new_BalangTarihi)) AS ay, COUNT(*) AS n FROM {S}.new_etkinlikBase e "
                      f"WHERE e.statecode = 0 AND e.new_etkinliktipiid IN ({ids}) AND e.new_BalangTarihi >= {tr(f'{yr}-01-01')} "
                      f"AND e.new_BalangTarihi < {tr(f'{yr + 1}-01-01')} GROUP BY MONTH(DATEADD(hour, 3, e.new_BalangTarihi)) ORDER BY COUNT(*) DESC")
        if not busiest:
            check("R4 takvim fuar sayısı", None, f"{yr} yılında fuar tipli CRM kaydı yok")
        else:
            mo = int(busiest[0]["ay"])
            m1 = date(yr, mo, 1)
            m2 = date(yr + (mo == 12), mo % 12 + 1, 1)
            ref = int(crm(f"SELECT COUNT(*) AS n FROM {S}.new_etkinlikBase e WHERE e.statecode = 0 AND e.new_etkinliktipiid IN ({ids}) "
                          f"AND e.new_BalangTarihi >= {tr(m1.isoformat())} AND e.new_BalangTarihi < {tr(m2.isoformat())}")[0]["n"])
            s, lst = http("GET", P + f"/crm-events?frm={m1}&to={m2 - timedelta(days=1)}&cls=fuar", timeout=1800)
            s2, cal = http("GET", P + f"/calendar?year={yr}&classes=fuar", timeout=1800)
            cal_n = cal["months"][mo - 1]["counts"].get("fuar") if s2 == 200 else None
            check("R4 takvim fuar sayısı (liste + ay kutusu)", s == 200 and lst["total"] == ref and cal_n == ref,
                  f"{m1:%Y-%m}: liste {lst.get('total') if s == 200 else s} / takvim {cal_n} / SQL {ref}")

    # R5 · yazar etkinlik sayısı: bu yıl en çok etkinliği olan yazar (veriden)
    yr = date.today().year
    top = crm(f"SELECT TOP 1 ec.contactid AS id, COUNT(DISTINCT ec.new_etkinlikid) AS n FROM {S}.new_new_etkinlik_contactBase ec "
              f"JOIN {S}.new_etkinlikBase e ON e.new_etkinlikId = ec.new_etkinlikid WHERE e.statuscode <> 100000000 "
              f"AND e.new_BalangTarihi >= {tr(f'{yr}-01-01')} AND e.new_BalangTarihi < {tr(f'{yr + 1}-01-01')} "
              f"GROUP BY ec.contactid ORDER BY COUNT(DISTINCT ec.new_etkinlikid) DESC")
    if not top:
        check("R5 yazar etkinlik sayısı", None, f"{yr} yılında yazar bağlı etkinlik yok")
    else:
        cid = str(top[0]["id"]).lower()
        s, ae = http("GET", P + f"/authors/{cid}/events?year={yr}")
        check("R5 yazar etkinlik sayısı", s == 200 and ae["total"] == int(top[0]["n"]), f"ekran {ae.get('total') if s == 200 else s} / SQL {top[0]['n']}")

    # R6 · Kampüs ajandası (CRM payı)
    s, ag = http("GET", P + "/me/agenda")
    if s != 200:
        check("R6 Kampüs ajandası", False, f"uç {s}")
    else:
        days = int(meta["settings"]["agendaDays"])
        today = date.fromisoformat(ag["today"])
        like_dom, like_mail, exact = q("%" + chr(92) + KISI), q(KISI + "@%"), q(KISI)
        rows = crm(f"SELECT e.new_etkinlikId AS id FROM {S}.new_etkinlikBase e JOIN {S}.SystemUserBase u ON u.SystemUserId = e.new_sorumlusu "
                   f"WHERE e.statecode = 0 AND e.statuscode <> 100000000 AND (u.DomainName LIKE {like_dom} OR u.DomainName LIKE {like_mail} "
                   f"OR u.DomainName = {exact}) AND e.new_BalangTarihi >= {tr(today.isoformat())} "
                   f"AND e.new_BalangTarihi < {tr((today + timedelta(days=days + 1)).isoformat())}")
        ref = {str(r["id"]).lower() for r in rows}
        got = {i["id"] for i in ag["items"] if i["kind"] == "crm"}
        check("R6 Kampüs ajandası CRM kayıtları birebir", ref == got, f"ekran {len(got)} / SQL {len(ref)}; fark {sorted(ref ^ got)[:5]}")
        foreign = [i for i in ag["items"] if i["kind"] == "fuar"]
        print(f"   ajandada {len(foreign)} portal kartı, {sum(1 for i in ag['items'] if i['kind'] == 'gorev')} görev")

    s, _ = http("GET", P + "/me/agenda", cookie="")
    check("oturumsuz ajanda 401", s == 401, str(s))

    if not a.write:
        return finish(a.out, created)

    # --write · deneme kartı: pencere ve cari veriden
    bit = a.bit or ref_end
    bas = a.bas or (date.fromisoformat(bit) - timedelta(days=8)).isoformat()
    bit1 = (date.fromisoformat(bit) + timedelta(days=1)).isoformat()
    if a.cariler:
        cariler = [c for c in a.cariler.split(",") if c]
    else:
        topc = logo(f"SELECT TOP 1 c.CODE AS kod, SUM(CASE WHEN s.TRCODE IN (7,8,9) THEN s.LINENET ELSE -s.LINENET END) AS ciro "
                    f"FROM dbo.LG_{F}_01_STLINE s JOIN dbo.LG_{F}_CLCARD c ON c.LOGICALREF = s.CLIENTREF "
                    f"WHERE s.LINETYPE = 0 AND s.CANCELLED = 0 AND s.INVOICEREF <> 0 AND s.TRCODE IN (2,3,7,8,9) AND c.SPECODE2 = {q(channel)} "
                    f"AND s.DATE_ >= '{bas}' AND s.DATE_ < '{bit1}' GROUP BY c.CODE ORDER BY ciro DESC")
        cariler = [topc[0]["kod"]] if topc else []
    print(f"deneme penceresi {bas} – {bit}; cariler {cariler or 'yok (kanalın tamamı)'}")

    s, bad = http("POST", P + "/fairs", {})
    check("boş gövdeyle kart 422", s == 422, str(s))
    s, card = http("POST", P + "/fairs", {"name": f"M27 kabul denemesi {datetime.now():%Y%m%d-%H%M}", "kind": "stant",
                                          "startsOn": bas, "endsOn": bit, "logoClientCodes": cariler})
    check("kart açıldı (201)", s == 201, str(s) if s != 201 else card["id"])
    if s != 201:
        return finish(a.out, created)
    fid = card["id"]
    created["fairs"].append(fid)
    created["tasks"] += [t["id"] for t in card["tasks"]]
    try:
        s, ap_ = http("POST", P + f"/fairs/{fid}/approve", {})
        check("kartı açan onaylayamaz (403)", s == 403, str(s))

        t1 = time.time()
        s, res = http("GET", P + f"/fairs/{fid}/result?yenile=1", timeout=3600)
        check("sonuç hesaplandı", s == 200 and res["result"].get("complete"), f"{s} · {round(time.time() - t1, 1)} sn")
        if s == 200:
            r = res["result"]
            cond = f" AND c.CODE IN ({', '.join(q(c) for c in cariler)})" if cariler else ""
            ref1 = logo(f"SELECT SUM(CASE WHEN s.TRCODE IN (7,8,9) THEN s.LINENET WHEN s.TRCODE IN (2,3) THEN -s.LINENET END) AS ciro, "
                        f"SUM(CASE WHEN s.TRCODE IN (7,8,9) THEN s.AMOUNT WHEN s.TRCODE IN (2,3) THEN -s.AMOUNT END) AS adet "
                        f"FROM dbo.LG_{F}_01_STLINE s JOIN dbo.LG_{F}_CLCARD c ON c.LOGICALREF = s.CLIENTREF "
                        f"WHERE s.LINETYPE = 0 AND s.CANCELLED = 0 AND s.INVOICEREF <> 0 AND s.TRCODE IN (2,3,7,8,9) "
                        f"AND c.SPECODE2 = {q(channel)} AND s.DATE_ >= '{bas}' AND s.DATE_ < '{bit1}'{cond}")[0]
            check("R1 fuar kanalı net satışı birebir (kuruş)", close(r["netCiro"], ref1["ciro"]) and close(r["netAdet"], ref1["adet"]),
                  f"ekran {r['netCiro']:.2f} / {r['netAdet']} · SQL {float(ref1['ciro'] or 0):.2f} / {ref1['adet']}")
            ref2 = logo(f"SELECT TOP 20 i.CODE AS kod, SUM(CASE WHEN s.TRCODE IN (7,8,9) THEN s.AMOUNT ELSE -s.AMOUNT END) AS adet, "
                        f"SUM(CASE WHEN s.TRCODE IN (7,8,9) THEN s.LINENET ELSE -s.LINENET END) AS ciro "
                        f"FROM dbo.LG_{F}_01_STLINE s JOIN dbo.LG_{F}_CLCARD c ON c.LOGICALREF = s.CLIENTREF "
                        f"JOIN dbo.LG_{F}_ITEMS i ON i.LOGICALREF = s.STOCKREF WHERE s.LINETYPE = 0 AND s.CANCELLED = 0 AND s.INVOICEREF <> 0 "
                        f"AND s.TRCODE IN (2,3,7,8,9) AND c.SPECODE2 = {q(channel)} AND s.DATE_ >= '{bas}' AND s.DATE_ < '{bit1}'{cond} "
                        f"GROUP BY i.CODE ORDER BY ciro DESC")
            api = {b["stokKodu"].upper(): b for b in r["books"]}
            diff = [(x["kod"], float(x["adet"]), api.get(str(x["kod"]).upper(), {}).get("adet")) for x in ref2
                    if not close(x["adet"], api.get(str(x["kod"]).upper(), {}).get("adet", -1), 0.001)
                    or not close(x["ciro"], api.get(str(x["kod"]).upper(), {}).get("ciro", -1))]
            order_ok = [b["stokKodu"].upper() for b in r["books"][:len(ref2)]] == [str(x["kod"]).upper() for x in ref2]
            check("R2 kitap bazında ilk 20 (adet, ciro, sıra)", not diff and order_ok, f"{len(ref2)} kitap; fark {diff[:5]}; sıra {'aynı' if order_ok else 'farklı'}")
            ref3 = crm(f"SELECT COUNT(*) AS n, SUM(new_toplamsatistutari) AS t FROM {S}.new_siparisBase WHERE statecode = 0 "
                       f"AND new_siparistipi IN ({', '.join(str(x) for x in meta['settings']['orderTypes'])}) "
                       f"AND statuscode NOT IN (100000001,100000003) AND new_siparistarihi >= {tr(bas)} AND new_siparistarihi < {tr(bit1)}")[0]
            check("R3 CRM fuar/etkinlik/imza siparişleri birebir", r["orderCount"] == int(ref3["n"]) and close(r["orderTotal"], ref3["t"]),
                  f"ekran {r['orderCount']} / {r['orderTotal']:.2f} · SQL {ref3['n']} / {float(ref3['t'] or 0):.2f}")
            check("R7 rapordaki veri sonu", r["dataEnd"] == ref_end, f"ekran {r['dataEnd']} / SQL {ref_end}")

        # öneri: temel pencerenin (364 gün önce) kanal satışı ile satır sayısı
        s, sug = http("POST", P + f"/fairs/{fid}/suggest-books", timeout=3600)
        if s == 200:
            b0, b1 = sug["basis"]["from"], (date.fromisoformat(sug["basis"]["to"]) + timedelta(days=1)).isoformat()
            fb = date.fromisoformat(b0).year
            fF = "211" if fb <= 2025 else F
            cond = f" AND c.CODE IN ({', '.join(q(c) for c in cariler)})" if cariler else ""
            n_ref = int(logo(f"SELECT COUNT(*) AS n FROM (SELECT i.CODE FROM dbo.LG_{fF}_01_STLINE s JOIN dbo.LG_{fF}_CLCARD c ON c.LOGICALREF = s.CLIENTREF "
                             f"JOIN dbo.LG_{fF}_ITEMS i ON i.LOGICALREF = s.STOCKREF WHERE s.LINETYPE = 0 AND s.CANCELLED = 0 AND s.INVOICEREF <> 0 "
                             f"AND s.TRCODE IN (2,3,7,8,9) AND c.SPECODE2 = {q(channel)} AND s.DATE_ >= '{b0}' AND s.DATE_ < '{b1}'{cond} "
                             f"GROUP BY i.CODE HAVING SUM(CASE WHEN s.TRCODE IN (7,8,9) THEN s.AMOUNT ELSE -s.AMOUNT END) > 0) x")[0]["n"])
            got = sum(1 for b in sug["detail"]["bookList"] if b["basisQty"] is not None)
            check("öneri: temelde satan kitap sayısı birebir", got == n_ref, f"ekran {got} / SQL {n_ref} ({b0} – {sug['basis']['to']}, firma {fF})")
        else:
            check("öneri ucu", False, str(s))
    finally:
        s, _ = http("DELETE", P + f"/fairs/{fid}")
        check("deneme kartı silindi", s == 200, str(s))
    return finish(a.out, created)


def finish(out_path: str, created: dict) -> int:
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w") as fh:
        json.dump(created, fh)
    ok = sum(1 for r in results if r[1] == "GEÇTİ")
    bad = sum(1 for r in results if r[1] == "KALDI")
    unk = sum(1 for r in results if r[1] == "DOĞRULANAMADI")
    print(f"== SONUÇ: {ok} geçti, {bad} kaldı, {unk} doğrulanamadı; kimlikler {out_path} (cleanup.py ile silin)")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
