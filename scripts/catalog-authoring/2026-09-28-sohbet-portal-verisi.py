"""Zeki AI sohbetine modül verisi (2026-09-28): portalın kendi modül tablolarını sohbet kataloğuna profil + onayla ekler.

Logo/CRM kataloğundan AYRI bir katalogdur (`semantic_chat_portal_catalog`); Logo/CRM sözlüğüne, kavramlarına ve
sertifikalarına dokunmaz. Alanlar `backend/semantic_bridge/chat_portal_areas.json`'da; bu betik yalnız ürünün kendi
API'sini (chat_portal.profile / save_candidates / certify) çağırır, ham SQL yazmaz.

  kuru koşu (varsayılan): her alanın tabloları, satır sayısı, kolon sınıfları (ölçü / boyut / tarih / dışarıda + nedeni),
      veriyle doğrulanan üst tablo bağları ve katalogdaki bugünkü durum basılır. Hiçbir şey yazılmaz.
  --apply            profilleri aday olarak yazar (onaylı tablonun yapısı değiştiyse yeni profil «bekliyor» olur)
  --certify A,B|all  alan ya da tablo kimliklerini onaylar (bekleyen profil varsa onaylanan odur)
  --reject T,...     tabloyu reddeder (sohbet kullanmaz, yeniden profil onu değiştirmez)
  --only A,B         yalnız bu alanlar/tablolar profillenir
  --json <dosya>     kuru koşu çıktısını dosyaya da yazar (kabul kanıtı)

Onay imzası: `operator:claude (iş teyidi bekliyor)`; iş tarafı teyit edince --certify yeniden koşulup imza değişir
(`CHAT_PORTAL_ACTOR` ortamıyla). Her yazma `semantic_audit`'e düşer (tür «chat_portal»).

Koşu (sunucuda, köprünün ortamıyla):

    sudo systemd-run --pipe --wait --collect -p User=administrator \\
      -p EnvironmentFile=/etc/nanobase/semantic-bridge.env \\
      -E PYTHONPATH=<kaynak>/backend \\
      /data/nanobaseai/bi/semantic-venv/bin/python - [--apply] [--certify all] < betik.py

Sonra köprü katalogu 60 sn içinde kendiliğinden tazeler (yeniden başlatma gerekmez). Kabul:
scripts/acceptance/sohbet-modul-verisi/calistir.sh.
"""
import argparse
import json
import os
import sys
from collections import Counter

for p in (os.environ.get("PYTHONPATH", ""), "/data/nanobaseai/bi/frontend/backend"):
    if p and p not in sys.path:
        sys.path.insert(0, p)

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import chat_portal as P  # noqa: E402
from semantic_layer.config import SemanticSettings  # noqa: E402

WHO = os.environ.get("CHAT_PORTAL_ACTOR", "operator:claude (iş teyidi bekliyor)")


def _split(v):
    return [x.strip() for x in (v or "").split(",") if x.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--certify", default="")
    ap.add_argument("--reject", default="")
    ap.add_argument("--only", default="")
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    s = SemanticSettings.from_env()
    engine = sa.create_engine(s.store_dsn)
    tenant = s.tenant_id
    profiles = P.profile(engine, tenant, only=_split(args.only) or None)
    current = {p["table"]: p for p in P.load(engine, tenant)}

    report = {"tenant": tenant, "areas": {}, "tables": []}
    for p in profiles:
        kinds = Counter(i["kind"] for i in p["columns"].values())
        out = {"table": p["table"], "area": p["area"], "topic": p["topic"], "label": p["label"], "rows": p["rows"],
               "kinds": dict(kinds),
               "measures": [c for c, i in p["columns"].items() if i["kind"] == P.MEASURE],
               "dimensions": {c: i.get("values") for c, i in p["columns"].items() if i["kind"] == P.DIMENSION},
               "times": [c for c, i in p["columns"].items() if i["kind"] == P.TIME],
               "excluded": {c: i.get("why") for c, i in p["columns"].items() if i["kind"] == P.EXCLUDED},
               "parents": p["parents"], "snapshot": p.get("snapshot"),
               "catalog": (current.get(p["table"]) or {}).get("status", "yok"),
               "fingerprintChanged": bool(current.get(p["table"])) and current[p["table"]].get("fingerprint") != p["fingerprint"]}
        report["tables"].append(out)
        report["areas"].setdefault(p["area"], []).append(p["table"])
    missing = sorted({a["id"] for a in P.areas()} - set(report["areas"]))
    report["areasWithoutTables"] = missing

    for t in report["tables"]:
        print(f"[{t['area']}] {t['table']} «{t['label']}» satır={t['rows']} katalog={t['catalog']}"
              + (" YAPI DEĞİŞTİ" if t["fingerprintChanged"] else ""))
        print(f"    ölçü: {', '.join(t['measures']) or '-'}")
        print(f"    boyut: {', '.join(f'{c}({len(v or [])})' for c, v in t['dimensions'].items()) or '-'}")
        print(f"    tarih: {', '.join(t['times']) or '-'}" + (f"  (anlık görüntü: {t['snapshot']})" if t["snapshot"] else ""))
        print(f"    dışarıda: {', '.join(f'{c}[{w}]' for c, w in t['excluded'].items()) or '-'}")
        if t["parents"]:
            print(f"    üst: {', '.join(x['column'] + '→' + x['table'] + ' %' + str(round(100 * x['coverage'], 1)) for x in t['parents'])}")
    if missing:
        print("tablosu bulunmayan alanlar (modülü bu sunucuda kurulmamış olabilir):", ", ".join(missing))

    changed = {}
    if args.apply:
        changed["saved"] = P.save_candidates(engine, tenant, profiles)
        print("yazıldı:", changed["saved"])
    if args.certify:
        changed["certified"] = P.certify(engine, tenant, _split(args.certify), WHO)
        print("onaylandı:", len(changed["certified"]), "tablo")
    if args.reject:
        changed["rejected"] = P.certify(engine, tenant, _split(args.reject), WHO, status=P.REJECTED)
        print("reddedildi:", changed["rejected"])
    if changed:
        from semantic_bridge import admin
        admin.audit(engine, WHO, "update", "chat_portal", "semantic_chat_portal_catalog",
                    "Zeki AI sohbet kataloğu: modül verisi", changed)
    report["changed"] = changed
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1, default=str)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
