"""Arka plan işleri (müşteri yığını): test sunucusundaki zamanlayıcıların birebir aynısı, aynı saatlerde.

Sunucuda işler systemd zamanlayıcılarıdır (`scripts/server/timas-*.timer` + `.service`). Müşteri yığınında systemd
yok; bu konteyner aynı dosyaları okur (imajda `/app/jobs/schedule/`) ve her işi dosyadaki takvimle köprüye çağırır.
Böylece iki ortamın iş düzeni tek kaynaktan gelir: sunucuya yeni zamanlayıcı eklenince VM'e ayrıca yazılmaz.

Desteklenen takvim biçimi, depodaki zamanlayıcıların kullandığı systemd alt kümesidir:
`[Gün] *-*-GG SS:DD[:ss] [Europe/Istanbul]` (gün `Mon`, `Mon..Fri`; saat/dakika `*`, sayı, `a..b`, `a/adım`,
virgül), kısa biçim `*:0/15`, ve `OnBootSec` + `OnUnitActiveSec` aralıkları. Saatler İstanbul saatidir (test
sunucusunun saat dilimi). `Persistent=true` işler konteyner kapalıyken kaçırdıkları son turu açılışta bir kez koşar;
ilk kurulumda (durum dosyası yokken) geçmiş turlar koşulmaz — 1 çekirdekli VM'e onlarca iş birden binmesin.

Bir birimde birden çok `ExecStart` varsa (Type=oneshot) hepsi dosyadaki sırayla koşar: biri hata verirse sonrakiler
koşmaz, `-` önekli satırın hatası yok sayılır (systemd kuralı); boş `ExecStart=` önceki satırları siler. Aynı birim
(ve örnek) bir turu bitirmeden yeniden tetiklenirse ikinci tur koşmaz, systemd'nin etkinleşmekte olan birime katılması gibi.

VM'de bilerek koşmayanlar `JOBS_EXCLUDE` (varsayılan: basın/web taraması — kullanıcı kararı 2026-09-25; Zeki AI
kalite kapıları — iç ölçüm, test dosyaları ister). Köprüye `curl` ya da `kopru-cagir.sh` ile gitmeyen servis (betik)
desteklenmez, günlüğe yazılır. Ana ekran özeti ayrı döngüdür (METRICS_EVERY_SEC).

Köprü çağrısı `scripts/server/kopru-cagir.sh` ile aynı kuralla (`call_bridge`): köprü hazır olana kadar beklenir; yalnız
işin başlamadığı (bağlanamadı, 502/503) ya da köprüyle birlikte öldüğü (bağlantı koptu ve köprünün pid'i değişti)
durumda yeniden denenir. Toplam bekleme JOBS_BRIDGE_WAIT_SEC (varsayılan 900 sn).
"""
from __future__ import annotations

import fnmatch
import glob
import json
import os
import re
import runpy
import threading
import time
import http.client
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Optional
from zoneinfo import ZoneInfo

BRIDGE = os.environ.get("BRIDGE", "http://bridge:8795")
TOKEN = os.environ.get("SEMANTIC_CALLER_TOKEN", "")
METRICS_EVERY = int(os.environ.get("METRICS_EVERY_SEC", "180"))
SCHEDULE_DIR = os.environ.get("SCHEDULE_DIR", "/app/jobs/schedule")
STATE_FILE = os.environ.get("JOBS_STATE", "/data/metrics/jobs-state.json")
TZ = ZoneInfo(os.environ.get("JOBS_TZ", "Europe/Istanbul"))
EXCLUDE = [p.strip() for p in os.environ.get("JOBS_EXCLUDE", "timas-web-watch,timas-model-quality-*").split(",") if p.strip()]
BRIDGE_WAIT = float(os.environ.get("JOBS_BRIDGE_WAIT_SEC", "900"))
RETRY_DELAY = float(os.environ.get("JOBS_RETRY_DELAY_SEC", "5"))

DAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


# ------------------------------------------------------------------------------------------------ takvim
def _values(expr: str, lo: int, hi: int, names: Optional[dict[str, int]] = None) -> set[int]:
    """systemd takvim alanı → izinli değerler. `*`, `5`, `8..19`, `0/15`, `8..19/2`, virgüllü liste."""
    out: set[int] = set()

    def num(s: str) -> int:
        return names[s.lower()] if names and s.lower() in names else int(s)

    for part in expr.split(","):
        step = 1
        if "/" in part:
            part, st = part.split("/", 1)
            step = int(st)
        if part == "*":
            a, b = lo, hi
        elif ".." in part:
            x, y = part.split("..", 1)
            a, b = num(x), num(y)
        else:
            a = num(part)
            b = hi if step > 1 else a
        if not (lo <= a <= hi and lo <= b <= hi):
            raise ValueError(f"aralık dışı: {expr}")
        out.update(range(a, b + 1, step))
    return out


@dataclass
class Calendar:
    text: str
    weekdays: set[int]
    months: set[int]
    days: set[int]
    hours: set[int]
    minutes: set[int]
    second: int = 0
    tz: ZoneInfo = TZ

    def _day_ok(self, day) -> bool:
        return day.month in self.months and day.day in self.days and day.weekday() in self.weekdays

    def next_after(self, t: datetime) -> datetime:
        """t'den SONRAKİ ilk tetik (takvimin saat diliminde)."""
        local = t.astimezone(self.tz)
        day = local.date()
        for _ in range(400):
            if self._day_ok(day):
                for h in sorted(self.hours):
                    for m in sorted(self.minutes):
                        cand = datetime(day.year, day.month, day.day, h, m, self.second, tzinfo=self.tz)
                        if cand > local:
                            return cand
            day += timedelta(days=1)
        raise ValueError(f"400 günde tetik yok: {self.text}")

    def prev_at_or_before(self, t: datetime) -> Optional[datetime]:
        local = t.astimezone(self.tz)
        day = local.date()
        for _ in range(400):
            if self._day_ok(day):
                for h in sorted(self.hours, reverse=True):
                    for m in sorted(self.minutes, reverse=True):
                        cand = datetime(day.year, day.month, day.day, h, m, self.second, tzinfo=self.tz)
                        if cand <= local:
                            return cand
            day -= timedelta(days=1)
        return None


def parse_calendar(text: str) -> Calendar:
    parts = text.split()
    tz = TZ
    if parts and parts[-1][0].isalpha() and "/" in parts[-1] and ":" not in parts[-1]:
        tz = ZoneInfo(parts.pop())
    weekdays = set(range(7))
    if parts and parts[0][:3].lower() in DAYS:
        weekdays = _values(parts.pop(0), 0, 6, DAYS)
    if len(parts) == 1:          # kısa biçim: yalnız saat (`*:0/15`) → her gün
        date, clock = "*-*-*", parts[0]
    elif len(parts) == 2:
        date, clock = parts
    else:
        raise ValueError(f"takvim çözülemedi: {text}")
    y, mo, d = (date.split("-") + ["*", "*"])[:3]
    if y != "*":
        raise ValueError(f"yıl sabit takvim desteklenmez: {text}")
    hms = clock.split(":")
    if len(hms) not in (2, 3):
        raise ValueError(f"saat çözülemedi: {text}")
    sec = int(hms[2]) if len(hms) == 3 and hms[2].isdigit() else 0
    return Calendar(text=text, weekdays=weekdays, months=_values(mo, 1, 12), days=_values(d, 1, 31),
                    hours=_values(hms[0], 0, 23), minutes=_values(hms[1], 0, 59), second=sec, tz=tz)


_SPAN = re.compile(r"(\d+)\s*(h|hr|hour|hours|min|m|minutes|s|sec|seconds)?", re.I)


def parse_span(text: str) -> int:
    """`15min`, `1h`, `90s`, `2min 30s` → saniye."""
    total = 0
    for n, unit in _SPAN.findall(text):
        u = (unit or "s").lower()
        total += int(n) * (3600 if u.startswith("h") else 60 if u.startswith("m") else 1)
    return total


# ------------------------------------------------------------------------------------------------ dosyalar
@dataclass
class Step:
    """Birimin tek `ExecStart` satırı."""
    path: str                      # köprü yolu (sorgu dahil)
    timeout: int
    ignore_failure: bool = False   # `ExecStart=-…`: hatası birimi düşürmez, sonraki satır koşar


@dataclass
class Job:
    name: str                      # zamanlayıcı adı (timas-stock)
    label: str                     # servis açıklaması
    path: str                      # ilk adımın köprü yolu (sorgu dahil)
    timeout: int                   # ilk adımın zaman aşımı
    calendars: list[Calendar] = field(default_factory=list)
    boot: int = 0
    every: int = 0
    persistent: bool = False
    steps: list[Step] = field(default_factory=list)   # bütün ExecStart satırları, dosyadaki sırayla
    unit: str = ""                 # birim + örnek (timas-dealers@gunluk); aynı birimin iki turu üst üste binmez

    def __post_init__(self) -> None:
        if not self.steps:
            self.steps = [Step(self.path, self.timeout)]
        if not self.unit:
            self.unit = self.name

    def describe(self) -> str:
        if self.calendars:
            return " + ".join(c.text for c in self.calendars)
        return f"{max(1, self.every // 60)} dk"

    def next_after(self, t: datetime) -> datetime:
        return min(c.next_after(t) for c in self.calendars)

    def last_due(self, t: datetime) -> Optional[datetime]:
        prev = [p for p in (c.prev_at_or_before(t) for c in self.calendars) if p]
        return max(prev) if prev else None


def _ini(path: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(("#", ";", "[")) or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out.setdefault(k.strip(), []).append(v.strip())
    return out


# Yalnız köprü (8795): başka bir servise giden çağrı VM'de köprüye yöneltilmesin.
_CURL = re.compile(r"(?:curl|kopru-cagir(?:\.sh)?)\b(?P<opts>.*?)[\"']?http://127\.0\.0\.1:8795(?P<path>/api/[^\"'\s]+)")


_PREFIX = re.compile(r"^([-@:+!]*)(.*)$", re.S)


def parse_step(line: str) -> Step:
    """ExecStart değeri → adım. Önekler systemd'deki gibi: `-` hatayı yok sayar; `@ : + !` VM'de anlamsız, atılır."""
    m = _PREFIX.match(line.strip())
    prefix, rest = (m.group(1), m.group(2)) if m else ("", line)
    path, timeout = parse_exec(rest)
    return Step(path=path, timeout=timeout, ignore_failure="-" in prefix)


def exec_lines(values: list[str]) -> list[str]:
    """Birimdeki ExecStart değerleri → koşulacak satırlar. Boş `ExecStart=` öncekileri siler (systemd kuralı)."""
    out: list[str] = []
    for v in values:
        if v:
            out.append(v)
        else:
            out.clear()
    return out


def parse_exec(line: str) -> tuple[str, int]:
    """ExecStart satırı → (köprü yolu, zaman aşımı sn). Köprüye curl değilse ValueError."""
    m = _CURL.search(line)
    if not m:
        raise ValueError("köprüye curl çağrısı değil")
    t = re.search(r"-m\s+(\d+)", m.group("opts"))
    return m.group("path"), int(t.group(1)) if t else 1700


def load_jobs(directory: str, exclude: Optional[list[str]] = None) -> tuple[list[Job], list[tuple[str, str]]]:
    """Zamanlayıcı dosyaları → işler. İkinci değer: koşulmayanlar ve nedeni."""
    exclude = EXCLUDE if exclude is None else exclude
    jobs: list[Job] = []
    skipped: list[tuple[str, str]] = []
    for tpath in sorted(glob.glob(os.path.join(directory, "timas-*.timer"))):
        name = os.path.basename(tpath)[:-6]
        if any(fnmatch.fnmatch(name, p) for p in exclude):
            skipped.append((name, "bu ortamda kapalı (JOBS_EXCLUDE)"))
            continue
        try:
            t = _ini(tpath)
            unit = (t.get("Unit") or [f"{name}.service"])[0]
            inst = ""
            m = re.match(r"^(.+@)(.+)\.service$", unit)
            if m:
                unit, inst = f"{m.group(1)}.service", m.group(2)
            s = _ini(os.path.join(directory, unit))
            execs = exec_lines(s.get("ExecStart", []))
            if not execs:
                raise ValueError(f"{unit}: ExecStart yok")
            try:
                steps = [parse_step(x.replace("%i", inst)) for x in execs]
            except ValueError as e:
                raise ValueError(f"{unit}: {e}") from None
            job = Job(name=name, label=(s.get("Description") or [name])[0], path=steps[0].path,
                      timeout=steps[0].timeout, steps=steps,
                      unit=f"{unit[:-len('@.service')]}@{inst}" if inst else unit[:-len(".service")],
                      calendars=[parse_calendar(c) for c in t.get("OnCalendar", [])],
                      boot=parse_span((t.get("OnBootSec") or ["0"])[0]),
                      every=parse_span((t.get("OnUnitActiveSec") or ["0"])[0]),
                      persistent=(t.get("Persistent") or ["false"])[0].lower() in ("true", "yes", "1"))
            if not job.calendars and not job.every:
                raise ValueError("takvim de aralık da yok")
            jobs.append(job)
        except (OSError, ValueError) as e:
            skipped.append((name, str(e)))
    return jobs, skipped


# ------------------------------------------------------------------------------------------------ çalıştırma
_state_lock = threading.Lock()


def _read_state() -> dict[str, str]:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _write_state(name: str, at: datetime) -> None:
    with _state_lock:
        s = _read_state()
        s[name] = at.isoformat()
        tmp = STATE_FILE + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(s, f)
            os.replace(tmp, STATE_FILE)
        except OSError as e:
            print(f"durum dosyası yazılamadı: {e}", flush=True)


def _post(path: str, body: dict, timeout: int):
    req = urllib.request.Request(f"{BRIDGE}{path}", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "X-Semantic-Caller": TOKEN})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.load(res)


def report(job: Job, ok: bool, detail: str = "") -> None:
    """M48: her işin sonucu Sistem durumu'nun iş tablosuna; tazelik aynı zamanda «Müşteri VM'i» kalp atışıdır."""
    try:
        _post("/api/v1/it-ops/watchdog", {"job": f"vm:{job.name}", "label": job.label, "ok": ok, "detail": detail[:500],
                                          "every": job.describe(), "source": "jobs-container"}, 30)
    except Exception as e:  # noqa: BLE001
        print(f"{job.name}: sistem durumuna bildirilemedi: {e}", flush=True)


def _bridge_pid() -> Optional[int]:
    """Köprü hazırsa süreç kimliği (bilinmiyorsa 0); hazır değilse None. Eski köprü (`boot` alanı yok): `status: ok`."""
    try:
        with urllib.request.urlopen(f"{BRIDGE}/health", timeout=5) as res:
            h = json.load(res)
    except Exception:  # noqa: BLE001 — cevap yok
        return None
    boot = h.get("boot")
    if (boot is not None and not boot.get("runtimeReady")) or (boot is None and h.get("status") != "ok"):
        return None
    try:
        return int(h.get("pid") or 0)
    except (TypeError, ValueError):
        return 0


def _wait_ready(deadline: float) -> Optional[int]:
    pause = 2.0
    while True:
        pid = _bridge_pid()
        if pid is not None:
            return pid
        if time.monotonic() >= deadline:
            return None
        time.sleep(pause)
        pause = min(pause + 2.0, 10.0)


def call_bridge(path: str, timeout: int, budget: Optional[float] = None):
    """Köprüye tur çağrısı: hazır olmasını bekle; aynı işi iki kez koşturmadan yalnız «başlamadı» hatalarında dene."""
    deadline = time.monotonic() + (BRIDGE_WAIT if budget is None else budget)
    pid = _wait_ready(deadline)
    if pid is None:
        raise ConnectionError("köprü hazır olmadı")
    delay = RETRY_DELAY
    attempt = 1
    while True:
        try:
            return _post(path, {}, timeout)
        except urllib.error.HTTPError as e:
            if e.code not in (502, 503):
                raise
            why: str = f"HTTP {e.code}"
        except urllib.error.URLError as e:
            # urllib bunu yalnız istek gönderilirken verir (bağlanamadı, ad çözülemedi — köprü kapsayıcısı yeniden
            # başlıyor): istek köprüye ulaşmadı, iş başlamadı. Cevap beklerken zaman aşımı URLError değildir, denenmez.
            why = f"bağlanamadı ({e.reason})"
        except (http.client.RemoteDisconnected, ConnectionResetError) as e:
            # Cevap gelmeden bağlantı koptu: köprü yeniden başladıysa iş onunla öldü; başlamadıysa iş sürüyor olabilir.
            now = _wait_ready(deadline)
            if now is None or now == pid:
                raise
            why = f"bağlantı koptu, köprü yeniden başladı ({type(e).__name__})"
        if time.monotonic() + delay > deadline:
            raise ConnectionError(f"köprü çağrısı bekleme süresi içinde başarılamadı: {why}")
        print(f"{path}: deneme {attempt}: {why} — {delay:.0f} sn sonra yeniden", flush=True)
        time.sleep(delay)
        new = _wait_ready(deadline)
        if new is None:
            raise ConnectionError(f"köprü hazır olmadı: {why}")
        pid = new
        delay = min(delay * 2, 60.0)
        attempt += 1


_unit_locks: dict[str, threading.Lock] = {}
_unit_locks_guard = threading.Lock()


def _unit_lock(unit: str) -> threading.Lock:
    with _unit_locks_guard:
        return _unit_locks.setdefault(unit, threading.Lock())


def run(job: Job) -> bool:
    """Birimin bütün ExecStart adımlarını sırayla koşar (Type=oneshot). Dönüş: tur başarılı mı.

    Adım hata verirse sonrakiler koşmaz; `-` önekli adımın hatası yok sayılır ve sıradaki koşar. Aynı birim hâlâ
    koşuyorsa bu tetik atlanır: iş iki kez koşmaz."""
    lock = _unit_lock(job.unit)
    if not lock.acquire(blocking=False):
        print(f"{job.name}: {job.unit} hâlâ koşuyor, bu tetik atlandı", flush=True)
        return False
    try:
        started = datetime.now(TZ)
        ok, notes = True, []
        many = len(job.steps) > 1
        for i, st in enumerate(job.steps, 1):
            tag = f"{job.name} [{i}/{len(job.steps)}] {st.path}" if many else job.name
            try:
                out = call_bridge(st.path, st.timeout)   # köprü hazır olana kadar bekler, «başlamadı» hatasında dener
                print(f"{tag}: {str(out)[:300]}", flush=True)
            except Exception as e:  # noqa: BLE001 — bir tur patlarsa bir sonraki tetikte yeniden denenir
                err = f"{type(e).__name__}: {e}"
                if st.ignore_failure:
                    print(f"{tag} başarısız (yok sayıldı, «-»): {err}", flush=True)
                    notes.append(f"{st.path} başarısız (yok sayıldı): {err}")
                    continue
                print(f"{tag} başarısız: {err}", flush=True)
                notes.append(f"{st.path} başarısız: {err}" if many else err)
                rest = [s.path for s in job.steps[i:]]
                if rest:
                    notes.append("koşmadı: " + ", ".join(rest))
                ok = False
                break
        report(job, ok, "; ".join(notes))
        _write_state(job.name, started)
        return ok
    finally:
        lock.release()


def _sleep_until(at: datetime) -> None:
    # Uzun uykuyu parçala: saat ayarı değişse de en geç bir dakikada toparlanır.
    while True:
        left = (at - datetime.now(TZ)).total_seconds()
        if left <= 0:
            return
        time.sleep(min(left, 60))


def calendar_loop(job: Job, state: dict[str, str], first_deploy: bool) -> None:
    now = datetime.now(TZ)
    if job.persistent and not first_deploy:
        due = job.last_due(now)
        last = state.get(job.name)
        if due and (last is None or datetime.fromisoformat(last) < due):
            print(f"{job.name}: kaçırılan tur ({due:%d.%m %H:%M}) şimdi koşuyor", flush=True)
            run(job)
    while True:
        _sleep_until(job.next_after(datetime.now(TZ)))
        run(job)


def interval_loop(job: Job) -> None:
    time.sleep(job.boot)
    while True:
        started = time.monotonic()
        run(job)
        time.sleep(max(5.0, job.every - (time.monotonic() - started)))


def metrics() -> None:
    while True:
        started = time.monotonic()
        try:
            runpy.run_path("/app/jobs/metrics_build.py", run_name="__main__")
        except SystemExit:
            pass
        except Exception as e:  # noqa: BLE001
            print(f"özet üretilemedi: {e}", flush=True)
        time.sleep(max(5.0, METRICS_EVERY - (time.monotonic() - started)))


def main() -> None:
    jobs, skipped = load_jobs(SCHEDULE_DIR)
    print(f"{len(jobs)} iş yüklendi ({SCHEDULE_DIR}); koşmayan {len(skipped)}:", flush=True)
    for n, why in skipped:
        print(f"  - {n}: {why}", flush=True)
    for j in jobs:
        print(f"  + {j.name}: {j.describe()} → {' → '.join(('-' if st.ignore_failure else '') + st.path for st in j.steps)}",
              flush=True)
    state = _read_state()
    first_deploy = not os.path.exists(STATE_FILE)
    if first_deploy:  # ilk kurulum: bugünkü geçmiş turları koşma; bundan sonrası takvimle
        for j in jobs:
            _write_state(j.name, datetime.now(TZ))
    time.sleep(30)   # köprü açılsın diye kısa bekleme
    targets: list[tuple[Callable, tuple]] = [(metrics, ())]
    targets += [(calendar_loop, (j, state, first_deploy)) if j.calendars else (interval_loop, (j,)) for j in jobs]
    threads = [threading.Thread(target=f, args=a, daemon=True) for f, a in targets]
    for t in threads:
        t.start()
    while all(t.is_alive() for t in threads):
        time.sleep(30)
    raise SystemExit("bir iş döngüsü durdu")  # konteyner yeniden başlar


if __name__ == "__main__":
    main()
