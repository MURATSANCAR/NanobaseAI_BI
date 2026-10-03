#!/usr/bin/env python3
"""Merkezi denetim kaydının kenar katmanı: portal nginx'i her isteği kişisiyle JSON satırı olarak yazar (idempotent).

- `/etc/nginx/conf.d/nb-audit-log.conf`: `log_format nb_audit` (zaman, IP, kişi, yöntem, yol, kod, boy, süre, Referer,
  tarayıcı, sunucu:port, nginx istek kimliği).
- Kişi: giriş servisinin `/check` cevabındaki `X-Timas-User` başlığı → `auth_request_set $timas_user` (sunucu bloğu
  düzeyinde; `auth_request` olan her konum kalıtır). Oturumsuz istekte boş.
- Portal (443/80), Destek kapısı (8446) ve analiz (8443) sunucu bloklarına ikinci bir `access_log` eklenir; mevcut log
  yerinde kalır. Kendi `access_log`'u olan konumlar (ör. sunucudan sunucuya `destek-baglam`) bu loga yazmaz.
- Log `/var/log/nanobase-audit/edge.log` (dizin root:administrator 0750 — köprü okur), logrotate günlük, `.1` sıkıştırılmaz
  (köprü yarım kalan dosyayı oradan tamamlar). Köprü (`audit_trail.ship_edge`) 30 sn'de bir okur ve merkeze yazar.

`nginx -t` geçmezse dosyalar eski içeriğine döner.  Test sunucusunda:  sudo python3 add-audit-edge-log.py
"""
import os
import pwd
import subprocess
import sys

LOG_DIR = "/var/log/nanobase-audit"
CONF = "/etc/nginx/conf.d/nb-audit-log.conf"
ROTATE = "/etc/logrotate.d/nanobase-audit"
SITES = ["/etc/nginx/sites-enabled/portal.nanobase.ai", "/etc/nginx/sites-enabled/destek-8446.conf",
         "/etc/nginx/sites-enabled/portal-analytics-8443.conf"]
READER = os.environ.get("AUDIT_READER", "administrator")

FORMAT = r"""# Merkezi denetim kaydı — kenar katmanı (deploy/nanobase-direct/add-audit-edge-log.py)
log_format nb_audit escape=json '{"t":"$time_iso8601","ip":"$remote_addr","u":"$timas_user","m":"$request_method",'
    '"p":"$request_uri","s":$status,"b":$body_bytes_sent,"rt":"$request_time","ref":"$http_referer",'
    '"ua":"$http_user_agent","h":"$server_name:$server_port","rid":"$request_id"}';
"""

ROTATE_CONF = f"""{LOG_DIR}/edge.log {{
    daily
    rotate 30
    missingok
    notifempty
    compress
    delaycompress
    create 0640 root {READER}
    sharedscripts
    postrotate
        [ -s /run/nginx.pid ] && kill -USR1 $(cat /run/nginx.pid)
    endscript
}}
"""

LINES = ("    # Denetim kaydı (kenar): kişi giriş servisinden, satır merkeze akar.\n"
         "    auth_request_set $timas_user $upstream_http_x_timas_user;\n"
         f"    access_log {LOG_DIR}/edge.log nb_audit;\n")
MARK = "nb_audit;"


def patch_site(text: str) -> str:
    """Her `server {` bloğunun `server_name` satırının ardına ekler. Blokta sunucu düzeyinde access_log yoksa, eski
    davranış (http düzeyindeki ana log) kaybolmasın diye o da yazılır."""
    if MARK in text:
        return text
    out, i = [], 0
    lines = text.splitlines(keepends=True)
    depth = 0
    in_server = False
    server_has_log = False
    pending = None
    for ln in lines:
        stripped = ln.strip()
        if stripped.startswith("server {") or stripped == "server{":
            in_server, server_has_log, pending = True, False, None
            depth = 0
        if in_server:
            depth += ln.count("{") - ln.count("}")
            if depth == 1 and stripped.startswith("access_log"):
                server_has_log = True
        out.append(ln)
        if in_server and depth == 1 and stripped.startswith("server_name"):
            pending = len(out)
        if in_server and depth == 0 and pending is not None:
            extra = LINES if server_has_log else LINES + "    access_log /var/log/nginx/access.log;\n"
            out.insert(pending, extra)
            in_server, pending = False, None
        elif in_server and depth == 0:
            in_server = False
    return "".join(out)


def main() -> int:
    uid = 0
    try:
        gid = pwd.getpwnam(READER).pw_gid
    except KeyError:
        print(f"okuyucu kullanıcı yok: {READER}")
        return 1
    os.makedirs(LOG_DIR, exist_ok=True)
    os.chown(LOG_DIR, uid, gid)
    os.chmod(LOG_DIR, 0o750)
    saved = {}
    for p in [CONF, *SITES]:
        rp = os.path.realpath(p)
        saved[rp] = open(rp, encoding="utf-8").read() if os.path.exists(rp) else None
    open(CONF, "w", encoding="utf-8").write(FORMAT)
    for p in SITES:
        rp = os.path.realpath(p)
        if saved.get(rp) is None:
            continue
        new = patch_site(saved[rp])
        if new != saved[rp]:
            open(rp, "w", encoding="utf-8").write(new)
    t = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
    if t.returncode != 0:
        for rp, old in saved.items():
            if old is None:
                os.path.exists(rp) and os.remove(rp)
            else:
                open(rp, "w", encoding="utf-8").write(old)
        print("nginx -t DÜŞTÜ, dosyalar eski hâline döndü:\n", t.stderr)
        return 1
    open(ROTATE, "w", encoding="utf-8").write(ROTATE_CONF)
    subprocess.run(["systemctl", "reload", "nginx"], check=True)
    log = os.path.join(LOG_DIR, "edge.log")
    if os.path.exists(log):
        os.chown(log, uid, gid)
        os.chmod(log, 0o640)
    print("kenar logu kuruldu:", log)
    return 0


if __name__ == "__main__":
    sys.exit(main())
