#!/usr/bin/env python3
"""Köprü açılış süresi ölçümü (hız 2. tur, 2026-09-29). Test sunucusunda koşulur; Mac'te değil.

İki kip:

  ic    Süreç içinde, adım adım: içe aktarmalar (üçüncü parti, katalog katmanı, create_app'in modülleri tek tek),
        create_app (modüller yüklüyken, satır satır), çalışma ortamı (katalog deposu, model sırası, bilgi paketi),
        katalog (profil okuma → dil havuzu, adım adım), tablo kurulumları (`ensure`, damgalı/damgasız), hazır cevap
        önbelleğinin kod özeti ve disk yüklemesi. Canlı köprüye dokunmaz; ayrı bir süreçte aynı ortamla kurar.

      cd /data/nanobaseai/bi/frontend/backend
      set -a; . /etc/nanobase/semantic-bridge.env; set +a
      /data/nanobaseai/bi/semantic-venv/bin/python ../scripts/perf/acilis.py ic [--ensure] [--json /tmp/acilis.json]

      --katalogsuz      katalog yüklemesini atla (bellek: katalog ~ canlı köprü kadar yer tutar)
      --ensure          bütün modüllerin tablo kurulumunu (ensure) koştur ve süresini say (eksik tablo/kolon varsa
                        köprünün ilk istekte yapacağını yapar: kurar)
      --damgasiz        tablo kurulumunu damgasız ölç (SCHEMA_STAMP=0; eski davranış)
      --onbellek-dizini DIR   hazır cevap önbelleğini bu dizinden yükleme süresini ölç (köprü gibi 3 günden eski
                        kayıtları siler; verilmezse boş geçici dizin kullanılır)

  izle  Çalışan servisi dışarıdan izler: port ne zaman cevap verdi, `ready` ne zaman oldu, systemd ne zaman `active`
        dedi, verilen uçlar ne zaman 200 döndü.

      python3 scripts/perf/acilis.py izle --yeniden-baslat [--port 8795] [--sure 300] [--uc /api/v1/engine ...]

      --yeniden-baslat  önce `sudo systemctl restart nanobase-semantic-bridge` (paylaşılan sunucu: bilerek kullanın)
      --baslik "Ad: değer"   uçlara gidecek başlık (ör. X-Semantic-Caller); SEMANTIC_CALLER_TOKEN varsa kendiliğinden

Çıktı Türkçe tablo; --json ile makine okunur kopya.
"""

from __future__ import annotations

import argparse
import ast
import importlib
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
APP_FILE = BACKEND / "semantic_bridge" / "app.py"


def _fmt(sec: float) -> str:
    return f"{sec * 1000:8.0f} ms" if sec < 10 else f"{sec:8.1f} sn"


def _print_table(title: str, rows: list[tuple[str, float]], top: int | None = None) -> None:
    print(f"\n== {title}")
    shown = sorted(rows, key=lambda r: -r[1])[:top] if top else rows
    for name, sec in shown:
        print(f"  {_fmt(sec)}  {name}")
    if top and len(rows) > top:
        rest = sum(s for _, s in sorted(rows, key=lambda r: -r[1])[top:])
        print(f"  {_fmt(rest)}  (kalan {len(rows) - top} kalem)")
    print(f"  {_fmt(sum(s for _, s in rows))}  TOPLAM")


# ---------------------------------------------------------------------------------------------- ic
def _app_imports() -> tuple[list[str], list[str]]:
    """app.py'nin üst düzey içe aktarmaları ve create_app içindekiler (sırasıyla, tekrarsız)."""
    tree = ast.parse(APP_FILE.read_text(encoding="utf-8"))

    def mods(nodes) -> list[str]:
        out: list[str] = []
        for n in nodes:
            if isinstance(n, ast.Import):
                out += [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
                out.append(n.module)
                # `from semantic_bridge import x` → x bir alt modül olabilir
                out += [f"{n.module}.{a.name}" for a in n.names]
        return out

    def direct(node):
        """create_app gövdesinde koşan içe aktarmalar; uçların (iç fonksiyonların) içindekiler açılışta koşmaz."""
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                continue
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                yield child
            else:
                yield from direct(child)

    top = mods(n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom)))
    ca = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "create_app")
    inner = mods(direct(ca))
    seen: set[str] = set()
    return ([m for m in top if not (m in seen or seen.add(m))], [m for m in inner if not (m in seen or seen.add(m))])


def _import_timed(names: list[str]) -> list[tuple[str, float]]:
    rows = []
    for name in names:
        if name in sys.modules:
            continue
        t = time.perf_counter()
        try:
            importlib.import_module(name)
        except ModuleNotFoundError:
            continue                    # `from paket import ad`: ad modül değil, değişken
        except Exception as e:  # noqa: BLE001
            print(f"  ! {name}: {type(e).__name__}: {e}")
            continue
        rows.append((name, time.perf_counter() - t))
    return rows


def _trace_create_app(create_app) -> tuple[float, list[tuple[str, float]], str]:
    """create_app'i satır satır zamanla. 3.12+: yalnız create_app'in kodu olay üretir (sys.monitoring, ek yük yok);
    daha eskisinde sys.settrace (her çağrıda küçük ek yük — toplam ayrıca izsiz ölçülür)."""
    code = create_app.__code__
    lines = APP_FILE.read_text(encoding="utf-8").splitlines()
    spent: dict[int, float] = {}
    state = {"line": None, "at": 0.0}

    def on_line(lineno: int) -> None:
        now = time.perf_counter()
        if state["line"] is not None:
            spent[state["line"]] = spent.get(state["line"], 0.0) + (now - state["at"])
        state["line"], state["at"] = lineno, time.perf_counter()

    how = ""
    started = time.perf_counter()
    if sys.version_info >= (3, 12):
        mon = sys.monitoring
        tool = mon.PROFILER_ID
        mon.use_tool_id(tool, "acilis")
        mon.register_callback(tool, mon.events.LINE, lambda c, n: on_line(n) if c is code else None)
        mon.set_local_events(tool, code, mon.events.LINE)
        try:
            create_app()
        finally:
            mon.set_local_events(tool, code, 0)
            mon.register_callback(tool, mon.events.LINE, None)
            mon.free_tool_id(tool)
        how = "sys.monitoring (ek yük yok)"
    else:
        def local(frame, event, arg):
            if event == "line":
                on_line(frame.f_lineno)
            return local

        def glob(frame, event, arg):
            return local if frame.f_code is code else None

        sys.settrace(glob)
        try:
            create_app()
        finally:
            sys.settrace(None)
        how = "sys.settrace (her çağrıda ek yük: satır süreleri toplamı izsiz süreden büyük olabilir)"
    on_line(-1)
    total = time.perf_counter() - started
    rows = [(f"app.py:{n}  {lines[n - 1].strip()[:110]}", s) for n, s in spent.items() if n > 0]
    return total, rows, how


def cmd_ic(args: argparse.Namespace) -> dict:
    sys.path.insert(0, str(BACKEND))
    os.environ.setdefault("SCHOOLS_WARM", "0")           # ayrı süreçte okul ısıtması koşmasın
    tmp_cache = tempfile.mkdtemp(prefix="acilis-onbellek-")
    os.environ["RESPONSE_CACHE_DIR"] = tmp_cache         # canlı önbelleğe dokunulmaz
    if args.damgasiz:
        os.environ["SCHEMA_STAMP"] = "0"
    report: dict = {"python": sys.version.split()[0], "cwd": os.getcwd()}
    t_all = time.perf_counter()

    third = ["fastapi", "starlette", "pydantic", "sqlalchemy", "sqlglot", "httpx", "yaml", "anyio", "uvicorn",
             "pyodbc", "psycopg2", "openpyxl", "ldap3", "fpdf"]
    rows_third = _import_timed(third)
    top, inner = _app_imports()
    rows_top = _import_timed(top)
    rows_inner = _import_timed(inner)
    _print_table("İçe aktarma: üçüncü parti", rows_third)
    _print_table("İçe aktarma: app.py üst düzey (katalog katmanı)", rows_top, top=15)
    _print_table("İçe aktarma: create_app içindeki modüller (bağımlılıklarıyla, ilk yükleyen öder)", rows_inner, top=25)

    # app.py modül düzeyinde `app = create_app()` koşar: modüller yüklü olduğu için bu süre yalnız kayıt işidir.
    t = time.perf_counter()
    import semantic_bridge.app as app_mod  # noqa: E402
    t_module = time.perf_counter() - t
    t = time.perf_counter()
    app_mod.create_app()
    t_plain = time.perf_counter() - t
    t_traced, rows_lines, how = _trace_create_app(app_mod.create_app)
    routes = len(app_mod.app.routes)
    _print_table(f"create_app satır satır ({how}; izli toplam {t_traced:.2f} sn)", rows_lines, top=25)
    print(f"\n  semantic_bridge.app modülü (create_app dahil): {_fmt(t_module)}")
    print(f"  create_app ikinci kez, izsiz:                   {_fmt(t_plain)}   ({routes} rota)")

    from semantic_bridge import response_cache as rc  # noqa: E402
    t = time.perf_counter()
    rc._code_version()
    t_code = time.perf_counter() - t
    print(f"  hazır cevap kod özeti (_code_version):          {_fmt(t_code)}")
    t_rc = None
    if args.onbellek_dizini:
        t = time.perf_counter()
        cache = rc.ResponseCache(args.onbellek_dizini)
        t_rc = time.perf_counter() - t
        print(f"  hazır cevap diskten yükleme ({cache.stats.get('loaded')} kayıt): {_fmt(t_rc)}")

    report.update(imports={"third": rows_third, "top": rows_top, "inner": rows_inner},
                  app_module_sec=t_module, create_app_sec=t_plain, create_app_traced_sec=t_traced,
                  create_app_lines=sorted(rows_lines, key=lambda r: -r[1])[:60], routes=routes,
                  code_version_sec=t_code, response_cache_load_sec=t_rc)

    # Çalışma ortamı (katalogsuz) — köprünün istek kabul etmesi için gereken kısım.
    t = time.perf_counter()
    rt = app_mod.build_runtime(defer_catalog=True)
    t_rt = time.perf_counter() - t
    _print_table(f"Çalışma ortamı (katalogsuz): {t_rt:.2f} sn", [(k, v) for k, v in rt.boot_timings.items()])
    report.update(runtime_sec=t_rt, runtime_steps=dict(rt.boot_timings))

    if not args.katalogsuz:
        t = time.perf_counter()
        rt.load_catalog()
        t_cat = time.perf_counter() - t
        steps = [(k, v) for k, v in rt.boot_timings.items() if k.startswith("katalog.")]
        _print_table(f"Katalog: {t_cat:.2f} sn ({len(rt.profiles)} profil; profiller hazır: "
                     f"{rt.boot_timings.get('profiller-hazir', '?')} sn)", steps)
        report.update(catalog_sec=t_cat, catalog_steps=dict(steps), profiles=len(rt.profiles))

    if args.ensure:
        report["ensure"] = _ensure_all(rt.store.engine, rt.settings.tenant_id)

    from semantic_layer.store import schema_stamp  # noqa: E402
    try:
        import sqlalchemy as sa
        with rt.store.engine.connect() as c:
            n = c.execute(sa.text("SELECT count(*) FROM sl_schema_stamp")).scalar()
        print(f"\n  sl_schema_stamp satırı: {n}  (damga {'kapalı' if not schema_stamp.enabled(rt.store.engine) else 'açık'})")
        report["stamps"] = n
    except Exception as e:  # noqa: BLE001
        print(f"\n  sl_schema_stamp okunamadı: {e}")

    report["total_sec"] = time.perf_counter() - t_all
    print(f"\nÖZET  içe aktarma+create_app ≈ {t_module + sum(s for _, s in rows_third + rows_top + rows_inner):.1f} sn "
          f"(port bundan sonra açılır) · çalışma ortamı {t_rt:.1f} sn (ekran uçları bundan sonra) · "
          f"katalog {report.get('catalog_sec', 0):.1f} sn (soru uçları bundan sonra)")
    return report


def _ensure_all(engine, tenant: str) -> list[tuple[str, float]]:
    """Köprü modüllerinin `ensure(engine)` işlevleri — köprünün yeniden başladıktan sonra her modülün ilk isteğinde
    ödediği tablo denetimi. Aynı süreçte ikinci kez koşmaz (modüllerin kendi `_ready` kümesi)."""
    import inspect
    import pkgutil

    import semantic_bridge

    rows = []
    for info in pkgutil.walk_packages(semantic_bridge.__path__, "semantic_bridge."):
        if ".tests" in info.name:
            continue
        try:
            mod = importlib.import_module(info.name)
        except Exception:  # noqa: BLE001
            continue
        for fname in ("ensure", "ensure_tables", "ensure_table"):
            fn = getattr(mod, fname, None)
            if not callable(fn) or getattr(fn, "__module__", "") != mod.__name__:
                continue
            params = list(inspect.signature(fn).parameters)
            try:
                t = time.perf_counter()
                fn(engine, tenant) if len(params) == 2 else fn(engine) if len(params) == 1 else None
                rows.append((f"{info.name}.{fname}", time.perf_counter() - t))
            except Exception as e:  # noqa: BLE001
                print(f"  ! {info.name}.{fname}: {type(e).__name__}: {str(e)[:160]}")
    _print_table("Tablo kurulumu (ensure), modül başına", rows, top=20)
    return rows


# ---------------------------------------------------------------------------------------------- izle
def _get(url: str, headers: dict[str, str], timeout: float = 5.0) -> tuple[int, str]:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 — bağlantı yok / zaman aşımı
        return 0, ""


def cmd_izle(args: argparse.Namespace) -> dict:
    base = f"http://127.0.0.1:{args.port}"
    headers = {}
    token = os.environ.get("SEMANTIC_CALLER_TOKEN", "")
    if token:
        headers["X-Semantic-Caller"] = token
    for h in args.baslik or []:
        k, _, v = h.partition(":")
        headers[k.strip()] = v.strip()
    t0 = time.monotonic()
    if args.yeniden_baslat:
        print(f"yeniden başlatılıyor: {args.unit}")
        subprocess.run(["sudo", "systemctl", "restart", "--no-block", args.unit], check=True)
        t0 = time.monotonic()
    marks: dict[str, float] = {}
    pending = list(args.uc or ["/api/v1/llm/queue", "/api/v1/engine"])
    last_phase = None
    while time.monotonic() - t0 < args.sure:
        now = time.monotonic() - t0
        if "systemd-active" not in marks:
            st = subprocess.run(["systemctl", "is-active", args.unit], capture_output=True, text=True).stdout.strip()
            if st == "active":
                marks["systemd-active"] = now
        code, body = _get(base + "/health", headers, 2.0)
        if code and "port" not in marks:
            marks["port"] = now
            print(f"  {now:6.1f} sn  port cevap verdi (/health {code})")
        if code == 200:
            try:
                h = json.loads(body)
            except ValueError:
                h = {}
            phase = (h.get("boot") or {}).get("phase")
            if phase != last_phase:
                print(f"  {now:6.1f} sn  açılış aşaması: {phase}")
                last_phase = phase
            if (h.get("boot") or {}).get("runtimeReady") and "calisma-ortami" not in marks:
                marks["calisma-ortami"] = now
            if h.get("ready") and "ready" not in marks:
                marks["ready"] = now
                print(f"  {now:6.1f} sn  hazır (profil {h.get('profiles')}); adımlar: {(h.get('boot') or {}).get('steps')}")
        if "port" in marks:
            for path in list(pending):
                c, _ = _get(base + path, headers, 60.0)
                if c == 200:
                    marks[path] = time.monotonic() - t0
                    pending.remove(path)
                    print(f"  {marks[path]:6.1f} sn  {path} → 200")
        if "ready" in marks and "systemd-active" in marks and not pending:
            break
        time.sleep(0.25)
    print("\nÖZET")
    for k in ("systemd-active", "port", "calisma-ortami", "ready", *(args.uc or ["/api/v1/llm/queue", "/api/v1/engine"])):
        print(f"  {k:<28} {marks[k]:6.1f} sn" if k in marks else f"  {k:<28}   —  (süre içinde olmadı)")
    return {"marks": marks}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="kip", required=True)
    a = sub.add_parser("ic")
    a.add_argument("--katalogsuz", action="store_true")
    a.add_argument("--ensure", action="store_true")
    a.add_argument("--damgasiz", action="store_true")
    a.add_argument("--onbellek-dizini")
    a.add_argument("--json")
    b = sub.add_parser("izle")
    b.add_argument("--port", type=int, default=int(os.environ.get("SEMANTIC_BRIDGE_PORT", "8795")))
    b.add_argument("--unit", default="nanobase-semantic-bridge")
    b.add_argument("--yeniden-baslat", action="store_true")
    b.add_argument("--sure", type=float, default=300.0)
    b.add_argument("--uc", action="append")
    b.add_argument("--baslik", action="append")
    b.add_argument("--json")
    args = ap.parse_args()
    report = cmd_ic(args) if args.kip == "ic" else cmd_izle(args)
    if args.json:
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"\nJSON: {args.json}")
    os._exit(0)                       # modüllerin arka plan iş parçacıklarını beklemeden çık


if __name__ == "__main__":
    main()
