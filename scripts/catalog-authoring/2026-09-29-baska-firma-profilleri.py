"""Başka şirketlerin Logo kopyalarını katalogdan çıkarır (2026-09-29).

Canlı Logo (192.168.0.25) muhasebe bürosunun bütün şirketlerini tek veritabanında tutar; eski .155 kopyasından
taranan katalogda da TİMAŞ dışı firmaların nesneleri kalmıştı (ör. `LG_XT1015_172`, `EOS_DAGITIM_MALIYET_019`,
`L_TABLELAYS_413`). Aynı ad kalıbında TİMAŞ kopyası da varsa çalışma zamanı bunları «bir yıl daha» sanıp birleştirir.
Gece taraması yalnız değişeni okuduğu için bunları kendiliğinden silmez; bu betik bir kez siler.

Hangi nesnenin yabancı olduğu `semantic_layer.firm_scope.foreign_tables` ile, katalogdaki adların kendisinden
okunur (elle liste yok): `LG_<firma>_…` ya da TİMAŞ firmasıyla da var olan bir ad kalıbındaki başka firma numarası.
Hesap kodu (`…_320`, `…_710`) ya da kısa yıl (`…_021`) taşıyan rapor tabloları dokunulmadan kalır.

  kuru koşu (varsayılan): silinecek profil sayısı, ad kalıpları, tutulan «sayılı» nesneler basılır; yazma yok.
  --apply           profilleri ve kapsam beyanlarını siler (`CatalogStore.delete_profiles`), `semantic_audit`'e yazar.
  --json <dosya>    listeyi dosyaya da yazar (kanıt).

Koşu (sunucuda, köprünün ortamıyla):

    sudo systemd-run --pipe --wait --collect -p User=administrator \\
      -p EnvironmentFile=/etc/nanobase/semantic-bridge.env \\
      -E PYTHONPATH=<kaynak>/backend \\
      /data/nanobaseai/bi/semantic-venv/bin/python - [--apply] < betik.py

Sonra köprü katalogu 60 sn içinde kendiliğinden tazeler (yeniden başlatma gerekmez).
"""
import argparse
import json
import os
import sys
from collections import Counter

for p in ("/data/nanobaseai/bi/frontend/backend", os.environ.get("PYTHONPATH", "")):   # PYTHONPATH önde kalır
    if p and p not in sys.path:
        sys.path.insert(0, p)

from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.firm_scope import foreign_tables, included_firms  # noqa: E402
from semantic_layer.naming import logical_table  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--json")
    a = ap.parse_args()
    if included_firms() is None:
        print("SEMANTIC_FIRMS boş — hangi firmaların şirketin olduğu bilinmeden silinmez.")
        return 2
    s = SemanticSettings.from_env() if hasattr(SemanticSettings, "from_env") else SemanticSettings()
    st = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False)
    profs = st.list_profiles(s.datasource_id)
    names = [p.table_name for p in profs]
    theirs = sorted(foreign_tables(names))
    numbered = [n for n in names if n not in theirs and (logical_table(n).context.get("n0", "").isdigit()
                                                          and len(logical_table(n).context.get("n0", "")) == 3
                                                          and int(logical_table(n).context["n0"]) not in included_firms())]
    pats = Counter(logical_table(n).table_pattern for n in theirs)
    print(f"katalog profili: {len(profs)} · silinecek (başka firma): {len(theirs)} · ad kalıbı: {len(pats)}")
    print("en çok:", pats.most_common(12))
    print(f"tutulan sayılı nesne (hesap kodu / kısa yıl): {len(numbered)} · ör. {numbered[:8]}")
    if a.json:
        with open(a.json, "w") as f:
            json.dump({"delete": theirs, "kept_numbered": numbered}, f, ensure_ascii=False, indent=1)
    if not a.apply:
        print("kuru koşu — yazılmadı (--apply ile siler)")
        return 0
    removed = st.delete_profiles(s.datasource_id, theirs)
    print(f"silindi: {removed} profil (kapsam beyanlarıyla)")
    try:
        from semantic_bridge import admin

        admin.audit(st.engine, "operator:claude", "delete", "catalog_profile", s.datasource_id,
                    f"başka firma kopyaları katalogdan çıkarıldı ({removed})",
                    {"tables": theirs, "rule": "firm_scope.foreign_tables", "firms": sorted(included_firms())})
    except Exception as e:  # noqa: BLE001
        print("UYARI: değişiklik kaydı yazılamadı:", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
