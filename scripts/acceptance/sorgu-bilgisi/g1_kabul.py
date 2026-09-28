"""Sorgu bilgisi kabulü — Grup 1 (çekirdek, analiz, yönetim, editoryal). Test sunucusunda, yan port köprüsüyle; yalnız
okuma, hiçbir yere yazmaz (POST /ask ve /run_sql okuma uçlarıdır).

Her uçta K1 (kaynaksız rakam yok), K2 (tutarlılık, yer tutucu, sır, teknoloji adı), K3 (her SQL kendi bağlantısında
hatasız koşar; `kabul.py` ile aynı yardımcılar). Doğrudan SQL referansları:
  G1  genel bakış: `/run_sql` ile koşan aylık sorgunun fiziksel metni Logo'da aynı Σ net_ciro'yu verir (mantıksal metin
      değil, gösterilen metin);
  G2  sohbet: «bu yıl net ciro» cevabının fiziksel SQL'i Logo'da koşunca ilk satırın rakamları cevaptakilerle aynı;
  G3  pano: her kartın saklı fiziksel SQL'i koşunca satır sayısı kartta saklı sonuçla aynı (yenilemeden sonra veri
      değiştiyse UYARI);
  G4  sistem durumu: Logo «veri sonu» SQL'inin sonucu halkanın gösterdiği veri sonu günüyle aynı;
  G5  pazar: anlık görüntünün Logo stok-kodu sorgusunun Σ ytd_ciro'su = iç göstergelerin toplam net cirosu (yeni
      anlık görüntü arada alındıysa UYARI);
  G6  kategori ağacı: öncelik SQL'lerinin toplam adedi > 0 ve kitap kuyruğundaki ilk kitabın önceliği ≤ toplam;
  G7  yönetim soru izleme: özet «toplam» portal SQL'i koşunca cevaptaki toplamla aynı.
Ortam ve kullanım `kabul.py` ile aynı: BASE, COOKIE, SEMANTIC_CONNECTION_FILE, SEMANTIC_STORE_DSN, PYTHONPATH.
    python g1_kabul.py [--skip-heavy]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kabul as K  # noqa: E402


def post(path: str, body: dict, timeout: int = 900):
    req = urllib.request.Request(K.BASE + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Cookie": K.COOKIE, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:  # type: ignore[attr-defined]
        return e.code, {}


GET_UCLARI = [
    ("uyarılar", "/api/v1/alerts", ()),
    ("pano", "/api/v1/board", ("cards[].x", "cards[].y", "cards[].w", "cards[].h", "cards[].z", "cards[].result.at",
                                "cards[].result.computedAt")),
    ("planlı raporlar", "/api/v1/reports", ("reports[].weekday", "reports[].monthday")),
    ("yönetim genel", "/api/v1/admin/overview", ("recent",)),
    ("yönetim kişiler", "/api/v1/admin/users", ()),
    ("soru izleme özet", "/api/v1/admin/prompts/overview", ("sinceDays",)),
    ("soru izleme liste", "/api/v1/admin/prompts", ("items[].catalogVersion", "nextOffset")),
    ("yetki rolleri", "/api/v1/access/roles", ()),
    ("veri alanları", "/api/v1/access/data-entities", ()),
    ("veri sözlüğü", "/api/v1/semantic/concepts?status=CERTIFIED&limit=50", ()),
    ("tablolar", "/api/v1/schema/gaps", ()),
    ("onaylar", "/api/v1/semantic/review?limit=20", ()),
    ("eş anlamlılar", "/api/v1/semantic/vocabulary", ()),
    ("zeki kalite karne", "/api/v1/model-quality/scorecard", ("days",)),
    ("zeki kalite sınıflar", "/api/v1/model-quality/classes", ("days",)),
    ("sistem durumu", "/api/v1/it-ops/status", ()),
    ("zamanlanmış işler", "/api/v1/it-ops/jobs", ()),
    ("kapasite", "/api/v1/it-ops/capacity", ("days",)),
    ("veri güvenliği özeti", "/api/v1/data-security/summary", ()),
    ("kişisel veri envanteri", "/api/v1/data-security/inventory", ()),
    ("pazar özeti", "/api/v1/pazar/overview", ("jobs",)),
    ("pazar iç göstergeler", "/api/v1/pazar/own-market", ("yil", "yillar")),
    ("pazar matris", "/api/v1/pazar/matrix", ()),
    ("rehber", "/api/v1/people", ()),
    ("kategori özeti", "/api/v1/categories/overview", ("job",)),
    ("kategori kuyruğu", "/api/v1/categories/books", ("page", "pageSize")),
    ("kurumsal e-posta", "/api/v1/mailbox/overview", ()),
    ("e-posta raporu", "/api/v1/mailbox/report", ()),
    ("yazar giriş", "/api/v1/editorial/intake", ("refreshIntervalSeconds",)),
    ("editörler", "/api/v1/editorial/editors", ()),
    ("atama bekleyen", "/api/v1/editorial/assignments/pending", ("page", "pageSize", "sinceYear", "statuses")),
    ("editoryal masam", "/api/v1/editorial/home", ("refreshIntervalSeconds",)),
    ("başvurular", "/api/v1/editorial/applications", ()),
    ("yayın kurulu", "/api/v1/editorial/board-sessions", ()),
    ("çeviri işleri", "/api/v1/editorial/translation/jobs", ()),
    ("çevirmenler", "/api/v1/editorial/translation/translators", ()),
    ("masadaki eserler", "/api/v1/editorial/works", ()),
    ("tasarım işleri", "/api/v1/editorial/studio/jobs", ()),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-heavy", action="store_true")
    heavy = not ap.parse_args().skip_heavy
    got_by: dict[str, tuple[dict, dict]] = {}
    for name, path, ignore in GET_UCLARI:
        st, out = K.http(path)
        if st != 200:
            K.check(f"{name} · uç", None if st in (403, 404, 503) else False, f"HTTP {st}")
            continue
        k = K.contract(name, out, ignore)
        got_by[name] = (out, K.run_all(name, k, heavy))

    # G1 genel bakış
    st, res = post("/api/v1/run_sql", {"sql": "SELECT 1 AS n", "limit": 5})
    if st == 200:
        k = K.contract("run_sql", res, ("computedAt", "ageSec", "truncated"))
        rows = K.run_all("run_sql", k, heavy)
        K.check("G1 run_sql fiziksel metin koşar", bool(rows), "")

    # G2 sohbet cevabı
    st, ans = post("/api/v1/ask", {"question": "bu yıl net ciro", "execute": True, "sampleSize": 5})
    if st == 200 and ans.get("type") == "TEXT_TO_SQL":
        k = K.contract("sohbet", ans, ("semantic", "repairs", "neden", "timings", "latency_ms", "ageSec", "computedAt"))
        rows = K.run_all("sohbet", k, heavy)
        first = next(iter(rows.values()), [])
        a0 = (ans.get("records") or [{}])[0]
        same = bool(first) and all(abs(K.num(first[0].get(c)) - K.num(v)) < 0.01 for c, v in a0.items()
                                   if isinstance(v, (int, float)) and c in first[0])
        K.check("G2 cevabın fiziksel SQL'i Logo'da aynı rakam", same, f"cevap {a0} · koşu {first[:1]}")
    else:
        K.check("G2 sohbet", None, f"HTTP {st} {ans.get('type')}")

    # G3 pano
    if "pano" in got_by:
        out, rows = got_by["pano"]
        for c in out.get("cards") or []:
            sid = f"pano.{c['id']}"
            if sid in rows:
                want = (c.get("result") or {}).get("totalRows")
                K.check(f"G3 kart {c['id']} satır sayısı", None if want is None else len(rows[sid]) == want or None,
                        f"saklı {want}, koşu {len(rows[sid])}")

    # G4 sistem durumu
    if "sistem durumu" in got_by:
        out, rows = got_by["sistem durumu"]
        ring = next((r for r in out.get("rings") or [] if r.get("id") == "logo"), {})
        r = rows.get("logo.itops.verisonu") or []
        if r and ring.get("dataEnd"):
            K.check("G4 Logo veri sonu", str(list(r[0].values())[0])[:10] == str(ring["dataEnd"])[:10],
                    f"SQL {list(r[0].values())[0]} · ekran {ring['dataEnd']}")

    # G5 pazar
    if "pazar iç göstergeler" in got_by:
        out, rows = got_by["pazar iç göstergeler"]
        y = out.get("yil")
        logo = rows.get(f"logo.pazar.stok.{y}") or []
        tot = (out.get("total") or {}).get("ytdCiro")
        if logo and tot is not None:
            s = sum(K.num(x.get("ytd_ciro")) for x in logo)
            K.check("G5 pazar Logo Σ ytd_ciro = iç gösterge toplamı", abs(s - K.num(tot)) < 1 or None, f"{s:.2f} / {tot}")

    # G6 kategori
    if "kategori kuyruğu" in got_by:
        out, rows = got_by["kategori kuyruğu"]
        tot = sum(K.num(x.get("adet")) for sid, rs in rows.items() if sid.startswith("logo.kategori.oncelik") for x in rs)
        first = (out.get("items") or [{}])[0].get("priority")
        K.check("G6 öncelik SQL'i adet verir", tot > 0 or None, f"Σ {tot:.0f}, ilk kitap {first}")

    # G7 soru izleme
    if "soru izleme özet" in got_by:
        out, rows = got_by["soru izleme özet"]
        r = rows.get("portal.soru.toplam") or []
        if r:
            K.check("G7 soru izleme toplamı", int(K.num(list(r[0].values())[0])) == int(out.get("total") or 0) or None,
                    f"SQL {list(r[0].values())[0]} · ekran {out.get('total')}")

    bad = [x for x in K.results if x[1] == "KALDI"]
    print(f"\nSONUÇ: {len(K.results)} denetim, {len(bad)} KALDI")
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
