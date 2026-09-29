"""Canlı kaynak bağlantıları: havuz, sunucu başına eşzamanlılık sınırı, tek uçuş.

Neden (2026-09-29 ölçümü): köprü bütün canlı Logo ve CRM okumalarını tek bağlantı ve tek kilit
(`Runtime._engine_lock`) üstünden yapıyordu. Kilit bağlantı nesnesini koruyordu — pyodbc/FreeTDS
bağlantısı iş parçacıkları arasında paylaşılamaz — ama bunun bedeli, iki ekranın birbirinden
bağımsız iki sorgusunun sıraya girmesiydi: sözleşme ekranı beş dakikada bir koşan tazeleme turlarının
arkasında bekledi. Burada o kilidin yerine üç parça var:

``ServerGate``
    Bir sunucuya (host:port) aynı anda giden sorgu sayısı. Logo müşterinin canlı sistemidir; sınır
    ayarla verilir (varsayılan 4). Bu bir sessiz tavan değil, eşzamanlılık sınırıdır: sınır dolunca
    yeni sorgu geliş sırasıyla bekler ve sırası gelince koşar, hiçbir sorgu düşürülmez ya da kesilmez.
    Kapı sunucu adresine bağlıdır, bağlantı nesnesine değil: köprünün ortak havuzu ve aynı sunucuya
    kendi bağlantısıyla giden değer yoklaması aynı kapıdan geçer. Modüllerin kendi açtığı
    `connector_from_file` bağlantıları (yönetim raporları, sözleşme hakedişi, etiket sözlüğü …) bu
    kapıdan geçmez — eskiden de ortak kilide girmiyorlardı; uzun süren rapor sorguları ekranların
    yerini tutmasın diye bilerek dışarıda bırakıldı (`gate_of(conn).slot()` ile tek satırda katılabilirler).
    Aynı iş parçacığı içinde iç içe okuma (parti parti okurken ikinci sorgu) ikinci yer istemez; istese,
    sınır kadar iç içe okuyucu birbirini sonsuza kadar beklerdi.

``ConnectorPool``
    Bir bağlayıcının çoğaltılmış kopyaları. Her çağrı boşta bir kopya alır (yoksa açar), işi bitince
    geri bırakır: her iş parçacığı kendi bağlantısını kullanır. Kopyalanamayan bağlayıcı (testlerdeki
    bellek içi SQLite, sahte bağlayıcılar) tek kopyalı havuzdur ve eskisi gibi sırayla kullanılır.

``SingleFlight``
    Aynı SQL aynı anda ikinci kez gelirse kaynağa ikinci kez inilmez: ikinci istek birincinin
    sonucunu bekler ve aynı satırları alır.
"""

from __future__ import annotations

import inspect
import logging
import threading
import time
from collections import deque
from contextlib import contextmanager
from typing import Any, Callable, Iterator, Optional

log = logging.getLogger(__name__)

#: Ayar okunamazsa kullanılan sınır (ayar: LOGO_MAX_CONCURRENT / CRM_MAX_CONCURRENT).
DEFAULT_LIMIT = 4


# ---------------------------------------------------------------------------------------------- bekleme ölçümü

_meters = threading.local()


@contextmanager
def queue_wait() -> Iterator[list]:
    """Bu blok içinde, bu iş parçacığında kapı önünde geçen süre (saniye) `box[0]`'da birikir.

    Veritabanı süresi (dbMs) sırada beklenen süreyi içermez; ekran «veritabanında … sürede geldi»
    derken sıra beklemesini veritabanına yazmasın diye ölçen taraf bunu düşer."""
    box = [0.0]
    stack = getattr(_meters, "boxes", None)
    if stack is None:
        stack = _meters.boxes = []
    stack.append(box)
    try:
        yield box
    finally:
        for i, b in enumerate(stack):
            if b is box:
                del stack[i]
                break


def _note_wait(seconds: float) -> None:
    for box in getattr(_meters, "boxes", None) or ():
        box[0] += seconds


# ---------------------------------------------------------------------------------------------- sunucu kapısı


class _Hold:
    __slots__ = ("active", "nested")

    def __init__(self, nested: bool = False):
        self.active = not nested
        self.nested = nested


class ServerGate:
    """Bir sunucuya aynı anda giden sorgu sayısı; sınır dolunca geliş sırasıyla bekletir."""

    def __init__(self, name: str, limit: Callable[[], int]):
        self.name = name
        self._limits: dict[str, Callable[[], int]] = {name: limit}
        self._lock = threading.Lock()
        self._busy = 0
        self._queue: "deque[threading.Event]" = deque()
        self._local = threading.local()
        self._runs = 0
        self._waited = 0
        self._wait_total = 0.0
        self._wait_max = 0.0
        self._peak = 0

    def add_limit(self, name: str, limit: Callable[[], int]) -> None:
        """Aynı ad yeniden gelirse (bağlantı ayarı değişti) sınırı yenilenir; başka ad aynı sunucuyu
        paylaşıyorsa (Logo ve CRM tek makinede) ikisinin küçüğü geçerlidir."""
        self._limits = {**self._limits, name: limit}
        self.name = "+".join(sorted(self._limits))

    def limit(self) -> int:
        values = []
        for name, fn in list(self._limits.items()):
            try:
                values.append(int(fn()))
            except Exception as e:  # noqa: BLE001 — okunamayan ayar kaynağı kapatmaz; varsayılan geçerli
                log.warning("eşzamanlılık ayarı okunamadı (%s), %d kullanılıyor: %s", name, DEFAULT_LIMIT, e)
                values.append(DEFAULT_LIMIT)
        return max(1, min(values))

    def _held_here(self) -> bool:
        holds = getattr(self._local, "holds", None)
        if not holds:
            return False
        live = [h for h in holds if h.active]
        self._local.holds = live
        return bool(live)

    def acquire(self, timeout: Optional[float] = None) -> Optional[_Hold]:
        """Yer alır; `timeout` dolarsa None. Dönen tutamaç `release` ile bırakılır."""
        if self._held_here():
            return _Hold(nested=True)
        limit = self.limit()
        started = time.monotonic()
        ticket: Optional[threading.Event] = None
        with self._lock:
            if not self._queue and self._busy < limit:
                self._busy += 1
                self._peak = max(self._peak, self._busy)
            else:
                ticket = threading.Event()
                self._queue.append(ticket)
                self._grant(limit)          # sınır büyütüldüyse boşalan yer hemen verilir
        if ticket is not None and not ticket.wait(timeout):
            with self._lock:
                if not ticket.is_set():
                    self._queue.remove(ticket)
                    return None
        waited = time.monotonic() - started
        hold = _Hold()
        holds = getattr(self._local, "holds", None)
        if holds is None:
            holds = self._local.holds = []
        holds.append(hold)
        with self._lock:
            self._runs += 1
            if ticket is not None:
                self._waited += 1
                self._wait_total += waited
                self._wait_max = max(self._wait_max, waited)
        if ticket is not None:
            _note_wait(waited)
        return hold

    def release(self, hold: Optional[_Hold]) -> None:
        # Başka iş parçacığından da bırakılabilir (parti parti okuyan üreteç orada kapanırsa); tutamaç
        # etkinliğini kaybeder, sahibi olan iş parçacığı bir sonraki alışında bunu görür.
        if hold is None or hold.nested or not hold.active:
            return
        hold.active = False
        limit = self.limit()
        with self._lock:
            self._busy -= 1
            self._grant(limit)

    def _grant(self, limit: int) -> None:
        while self._queue and self._busy < limit:
            self._busy += 1
            self._peak = max(self._peak, self._busy)
            self._queue.popleft().set()

    @contextmanager
    def slot(self, timeout: Optional[float] = None) -> Iterator[bool]:
        hold = self.acquire(timeout)
        try:
            yield hold is not None
        finally:
            self.release(hold)

    def waiting(self) -> int:
        return len(self._queue)

    def stats(self) -> dict[str, Any]:
        limit = self.limit()
        with self._lock:
            return {"name": self.name, "limit": limit, "running": self._busy, "waiting": len(self._queue),
                    "peak": self._peak, "runs": self._runs, "waitedRuns": self._waited,
                    "waitMsTotal": int(round(self._wait_total * 1000)), "waitMsMax": int(round(self._wait_max * 1000))}


_GATES: dict[str, ServerGate] = {}
_GATES_LOCK = threading.Lock()


def server_key(cfg: Any, default_port: int = 1433) -> Optional[str]:
    """Kapının anahtarı: sunucu adresi. Aynı sunucuya giden her bağlantı aynı kapıdan geçer."""
    if not isinstance(cfg, dict) or not cfg.get("host"):
        return None
    return f"{str(cfg['host']).strip().lower()}:{cfg.get('port') or default_port}"


def register_gate(key: Optional[str], name: str, limit: Callable[[], int]) -> Optional[ServerGate]:
    """Bu sunucu için sınır koyar. Aynı ad yeniden kaydolursa (bağlantı ayarı değişti) sınır yenilenir;
    iki ayrı kaynak aynı sunucudaysa (Logo ve CRM tek makinede) kapı birdir ve küçük sınır geçerlidir."""
    if not key:
        return None
    with _GATES_LOCK:
        gate = _GATES.get(key)
        if gate is None:
            gate = _GATES[key] = ServerGate(name, limit)
        else:
            gate.add_limit(name, limit)
        return gate


def gate_for(key: Optional[str]) -> Optional[ServerGate]:
    if not key:
        return None
    return _GATES.get(key)


def gate_of(connector: Any) -> Optional[ServerGate]:
    """Bağlayıcının sunucusunun kapısı; sınır konmamışsa None (o zaman bekleme yok)."""
    key_fn = getattr(connector, "_gate_key", None)
    if not callable(key_fn):
        return None
    try:
        return gate_for(key_fn())
    except Exception:  # noqa: BLE001
        return None


def gates() -> list[ServerGate]:
    with _GATES_LOCK:
        return list(_GATES.values())


# ---------------------------------------------------------------------------------------------- havuz

#: Alt çizgili olup yine de veritabanına inen yöntemler: bunlar da bir kopya alarak çalışır.
_LEASED_PRIVATE = frozenset({"_rows"})


class ConnectorPool:
    """Bağlayıcı kopyalarından oluşan havuz; dışarıdan tek bağlayıcı gibi kullanılır.

    Açık (alt çizgisiz) her yöntem çağrısı (ve `_rows`) boşta bir kopya alır, çağrı bitince bırakır. `batches` gibi
    üreteç yöntemlerde kopya, üreteç tükenene ya da kapanana kadar tutulur. Değer nitelikleri
    (`dialect`, `cfg`, `query_timeout` …) ilk kopyadan okunur; yazılan açık nitelik her kopyaya
    (sonradan açılanlara da) uygulanır.
    """

    def __init__(self, prototype: Any, name: str = "db"):
        object.__setattr__(self, "_proto", prototype)
        object.__setattr__(self, "_name", name)
        # Yalnız sınıfında `clone` tanımlı bağlayıcı çoğaltılır (MSSQL, Postgres); sahte/dinamik nesneler tek kopya.
        clone = prototype.clone if callable(getattr(type(prototype), "clone", None)) else None
        object.__setattr__(self, "_clone", clone)
        object.__setattr__(self, "_cond", threading.Condition())
        object.__setattr__(self, "_idle", [prototype])
        object.__setattr__(self, "_members", [prototype])
        object.__setattr__(self, "_overrides", {})
        object.__setattr__(self, "_closed", False)
        object.__setattr__(self, "_owner", None)          # tek kopyalı havuzda kopyayı tutan iş parçacığı
        object.__setattr__(self, "_depth", 0)
        object.__setattr__(self, "_single_waiting", 0)

    # ---- dışarıya açık yardımcılar (bağlayıcı yöntemleriyle çakışmasın diye havuza özgü adlar)
    @property
    def prototype(self) -> Any:
        return self._proto

    @property
    def gate(self) -> Optional[ServerGate]:
        return gate_of(self._proto) if self._clone is not None else None

    def pool_waiting(self) -> int:
        gate = self.gate
        return (gate.waiting() if gate is not None else 0) + self._single_waiting

    def pool_stats(self) -> dict[str, Any]:
        with self._cond:
            out = {"name": self._name, "connections": len(self._members), "idle": len(self._idle),
                   "shared": self._clone is None}
        gate = self.gate
        if gate is not None:
            out["gate"] = gate.stats()
        return out

    @contextmanager
    def lease(self) -> Iterator[Any]:
        """Boşta bir kopya; sunucunun kapısı varsa önce oradan yer alınır (açık bağlantı sayısı sınırı aşmaz)."""
        if self._clone is None:
            member = self._take_single()
            try:
                yield member
            finally:
                self._give_single(member)
            return
        gate = self.gate
        hold = gate.acquire() if gate is not None else None
        try:
            member = self._take()
            try:
                yield member
            finally:
                self._give(member)
        finally:
            if gate is not None:
                gate.release(hold)

    def close(self) -> None:
        """Boştaki bağlantıları kapatır; kullanımdaki kopya işi bitince kapanır. Kopyalar bir sonraki
        kullanımda (varsa) yeniden bağlanır — geç kalan bir çağrı hata almaz."""
        with self._cond:
            object.__setattr__(self, "_closed", True)
            idle = list(self._idle)
        for m in idle:
            _close_quietly(m)

    # ---- kopyalar
    def _take(self) -> Any:
        with self._cond:
            if self._idle:
                return self._idle.pop()
        member = self._clone()
        for k, v in self._overrides.items():
            setattr(member, k, v)
        with self._cond:
            self._members.append(member)
        return member

    def _give(self, member: Any) -> None:
        with self._cond:
            self._idle.append(member)
            closed = self._closed
        if closed:
            _close_quietly(member)

    def _take_single(self) -> Any:
        # Tek kopya: aynı iş parçacığı zaten tutuyorsa onu kullanır (iç içe çağrı kilitlenmez).
        me = threading.get_ident()
        with self._cond:
            if self._owner == me:
                object.__setattr__(self, "_depth", self._depth + 1)
                return self._proto
            if not self._idle:
                object.__setattr__(self, "_single_waiting", self._single_waiting + 1)
                started = time.monotonic()
                try:
                    while not self._idle:
                        self._cond.wait()
                finally:
                    object.__setattr__(self, "_single_waiting", self._single_waiting - 1)
                    _note_wait(time.monotonic() - started)
            member = self._idle.pop()
            object.__setattr__(self, "_owner", me)
            object.__setattr__(self, "_depth", 1)
        return member

    def _give_single(self, member: Any) -> None:
        with self._cond:
            if self._depth > 1:
                object.__setattr__(self, "_depth", self._depth - 1)
                return
            object.__setattr__(self, "_owner", None)
            object.__setattr__(self, "_depth", 0)
            self._idle.append(member)
            self._cond.notify()

    # ---- bağlayıcı gibi davranmak
    def __getattr__(self, item: str) -> Any:
        if item.startswith("__"):
            raise AttributeError(item)
        try:
            proto = object.__getattribute__(self, "_proto")
        except AttributeError:
            raise AttributeError(item) from None
        attr = getattr(proto, item)
        if (item.startswith("_") and item not in _LEASED_PRIVATE) or not callable(attr):
            return attr
        if item == "batches" or inspect.isgeneratorfunction(getattr(type(proto), item, None)):
            def leased_gen(*a: Any, **kw: Any):
                with self.lease() as member:
                    yield from getattr(member, item)(*a, **kw)
            return leased_gen

        def leased(*a: Any, **kw: Any) -> Any:
            with self.lease() as member:
                return getattr(member, item)(*a, **kw)
        return leased

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return
        with self._cond:
            self._overrides[name] = value
            members = list(self._members)
        for m in members:
            setattr(m, name, value)

    def __repr__(self) -> str:
        return f"<ConnectorPool {self._name} of {type(self._proto).__name__} ×{len(self._members)}>"


def _close_quietly(member: Any) -> None:
    try:
        member.close()
    except Exception as e:  # noqa: BLE001
        log.debug("havuz kopyası kapatılamadı: %s", e)


def pooled(connector: Any, name: str, limit: Optional[Callable[[], int]] = None) -> Any:
    """Bağlayıcıyı havuza alır ve sunucusuna `limit` sınırını koyar.

    CRM'in etkin kayıt süzgeci (`ActiveOnly`) en dışta kalır: sorgu metni bir kez yeniden yazılır,
    havuz onun içindeki asıl bağlayıcıyı çoğaltır."""
    if connector is None:
        return None
    if isinstance(connector, ConnectorPool):
        if limit is not None and connector._clone is not None:
            key_fn = getattr(connector.prototype, "_gate_key", None)
            register_gate(key_fn() if callable(key_fn) else None, name, limit)
        return connector
    from semantic_layer.runtime.crm_active import ActiveOnly

    if isinstance(connector, ActiveOnly):
        connector._inner = pooled(connector._inner, name, limit)
        return connector
    pool = ConnectorPool(connector, name)
    if limit is not None and pool._clone is not None:
        key_fn = getattr(connector, "_gate_key", None)
        register_gate(key_fn() if callable(key_fn) else None, name, limit)
    return pool


# ---------------------------------------------------------------------------------------------- tek uçuş


class _Call:
    __slots__ = ("done", "value", "error", "followers")

    def __init__(self) -> None:
        self.done = threading.Event()
        self.value: Any = None
        self.error: Optional[BaseException] = None
        self.followers = 0


class SingleFlight:
    """Aynı anahtarla aynı anda gelen çağrılardan yalnız ilki koşar; ötekiler onun sonucunu alır.

    Sonuç saklanmaz: ilk çağrı bitince anahtar düşer, sonraki çağrı yeniden koşar (önbellek ayrı iştir)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._calls: dict[Any, _Call] = {}
        self.joined = 0

    def do(self, key: Any, fn: Callable[[], Any]) -> Any:
        with self._lock:
            call = self._calls.get(key)
            leader = call is None
            if leader:
                call = self._calls[key] = _Call()
            else:
                call.followers += 1
                self.joined += 1
        if not leader:
            call.done.wait()
            if call.error is not None:
                raise call.error
            return call.value
        try:
            call.value = fn()
        except BaseException as e:
            call.error = e
            raise
        finally:
            with self._lock:
                self._calls.pop(key, None)
            call.done.set()
        return call.value

    def in_flight(self) -> int:
        with self._lock:
            return len(self._calls)
