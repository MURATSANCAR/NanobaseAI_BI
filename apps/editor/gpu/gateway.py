"""Istek gelince OCR konteynerini baslatan, bosta kalinca durduran kucuk kapi.

Yalniz standart kutuphane. Docker ile /var/run/docker.sock uzerinden konusur.
GET /gateway/status konteyneri BASLATMADAN durumu dondurur; diger her istek
konteyneri (gerekirse) baslatir, saglik ucunu bekler ve istegi aynen iletir.
"""
import http.client, json, os, socket, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TARGET = os.environ.get("TARGET", "paddleocr-vl")
UP_HOST = os.environ.get("UP_HOST", "paddleocr-vl")
UP_PORT = int(os.environ.get("UP_PORT", "8000"))
IDLE_SECONDS = int(os.environ.get("IDLE_SECONDS", "600"))
START_TIMEOUT = int(os.environ.get("START_TIMEOUT", "600"))
STOP_GRACE = int(os.environ.get("STOP_GRACE", "30"))
MAX_BODY_BYTES = int(os.environ.get("MAX_BODY_BYTES", str(32 * 1024 * 1024)))
VERSION = "editor-ocr-gateway-v2"

class _Docker(http.client.HTTPConnection):
    def __init__(self):
        super().__init__("docker", timeout=STOP_GRACE + 30)
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect("/var/run/docker.sock")

def docker(method, path):
    c = _Docker()
    try:
        c.request(method, path)
        r = c.getresponse()
        return r.status, r.read()
    finally:
        c.close()

def running():
    st, body = docker("GET", f"/containers/{TARGET}/json")
    return st == 200 and json.loads(body)["State"]["Running"]

def healthy():
    try:
        c = http.client.HTTPConnection(UP_HOST, UP_PORT, timeout=3)
        c.request("GET", "/health")
        ok = c.getresponse().status == 200
        c.close()
        return ok
    except OSError:
        return False

_start_lock = threading.Lock()
_state_lock = threading.Lock()
_active = 0
_last_used = time.monotonic()
_starts = 0
_stops = 0

def ensure_up():
    global _starts
    if healthy():
        return True, 0.0
    with _start_lock:
        t0 = time.monotonic()
        if not running():
            st, body = docker("POST", f"/containers/{TARGET}/start")
            if st not in (204, 304):
                return False, body.decode("utf-8", "replace")[:300]
            _starts += 1
        while time.monotonic() - t0 < START_TIMEOUT:
            if healthy():
                return True, time.monotonic() - t0
            if time.monotonic() - t0 > 15 and not running():
                return False, "konteyner acilista durdu (docker logs ile bakin)"
            time.sleep(2)
        return False, "acilis zaman asimi"

def reaper():
    global _stops
    while True:
        time.sleep(20)
        try:
            # The idle check and stop must be atomic with request admission.
            # Otherwise an arriving request can see a healthy model immediately
            # before a stale idle decision stops that model during inference.
            if not _start_lock.acquire(blocking=False):
                continue
            try:
                with _state_lock:
                    if _active == 0 and time.monotonic() - _last_used > IDLE_SECONDS and running():
                        status, _ = docker("POST", f"/containers/{TARGET}/stop?t={STOP_GRACE}")
                        if status in (204, 304):
                            _stops += 1
            finally:
                _start_lock.release()
        except Exception as e:  # kapi hic dusmemeli
            print("reaper:", e, flush=True)

class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, fmt, *a):
        print(self.address_string(), fmt % a, flush=True)
    def _send(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def _handle(self):
        global _active, _last_used
        if self.path.startswith("/gateway/status"):
            with _state_lock:
                idle = time.monotonic() - _last_used; busy = _active
            return self._send(200, {"target": TARGET, "running": running(), "healthy": healthy(),
                                    "active_requests": busy, "idle_seconds": round(idle),
                                    "idle_limit_seconds": IDLE_SECONDS, "starts": _starts, "stops": _stops,
                                    "version": VERSION})
        if self.headers.get("Transfer-Encoding"):
            self.close_connection = True
            return self._send(400, {"error": "TRANSFER_ENCODING_NOT_SUPPORTED"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self.close_connection = True
            return self._send(400, {"error": "INVALID_CONTENT_LENGTH"})
        if n < 0 or n > MAX_BODY_BYTES:
            self.close_connection = True
            return self._send(413, {"error": "REQUEST_BODY_LIMIT"})
        self.connection.settimeout(60)
        body = self.rfile.read(n) if n else None
        if n and len(body) != n:
            self.close_connection = True
            return self._send(400, {"error": "INCOMPLETE_REQUEST_BODY"})
        with _state_lock:
            _active += 1; _last_used = time.monotonic()
        c = None
        response_started = False
        try:
            ok, info = ensure_up()
            if not ok:
                return self._send(503, {"error": "OCR servisi baslatilamadi", "detail": info})
            c = http.client.HTTPConnection(UP_HOST, UP_PORT, timeout=900)
            hdrs = {k: v for k, v in self.headers.items() if k.lower() not in ("host", "connection", "content-length")}
            c.request(self.command, self.path, body=body, headers=hdrs)
            r = c.getresponse(); data = r.read()
            response_started = True
            self.send_response(r.status)
            for k, v in r.getheaders():
                if k.lower() not in ("transfer-encoding", "connection", "content-length"):
                    self.send_header(k, v)
            if isinstance(info, float) and info > 0:
                self.send_header("X-Cold-Start-Seconds", f"{info:.1f}")
            self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
        except (OSError, http.client.HTTPException) as error:
            self.close_connection = True
            if not response_started:
                self._send(502, {"error": "OCR_UPSTREAM_UNAVAILABLE", "kind": type(error).__name__})
        finally:
            if c is not None:
                c.close()
            with _state_lock:
                _active -= 1; _last_used = time.monotonic()
    do_GET = do_POST = do_PUT = do_DELETE = _handle

if __name__ == "__main__":
    threading.Thread(target=reaper, daemon=True).start()
    print(f"kapi hazir: hedef={TARGET} bosta_sinir={IDLE_SECONDS}s", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8080), H).serve_forever()
