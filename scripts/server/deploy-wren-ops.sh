#!/usr/bin/env bash
# İşletme katmanı: watchdog timer, log rotasyonu, journald sınırı, gece regresyon testi, günlük yedek. Idempotent.
set -euo pipefail
export SYSTEMD_BUS_TIMEOUT="${SYSTEMD_BUS_TIMEOUT:-300}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VENV="${WREN_VENV:-/data/nanobaseai/bi/wren-venv}"
PROJECT="${WREN_PROJECT:-/data/nanobaseai/bi/wren-project/logo_timas}"
LOGDIR=/data/nanobaseai/bi/logs
BACKUP=/data/nanobaseai/bi/backups
log() { printf '[deploy-wren-ops] %s\n' "$*"; }
mkdir -p "$LOGDIR" "$BACKUP" /data/logs
install -m 755 "${ROOT}/scripts/server/wren-watchdog.sh" /data/nanobaseai/bi/wren-watchdog.sh

# 1) watchdog (2 dk)
sudo -E tee /etc/systemd/system/nanobase-wren-watchdog.service >/dev/null <<UNIT
[Unit]
Description=NanobaseAI WrenAI hattı sağlık bekçisi (tek atış)
[Service]
Type=oneshot
User=administrator
EnvironmentFile=-/etc/nanobaseai/wren-watchdog.env
ExecStart=/data/nanobaseai/bi/wren-watchdog.sh
UNIT
sudo -E tee /etc/systemd/system/nanobase-wren-watchdog.timer >/dev/null <<UNIT
[Unit]
Description=WrenAI watchdog her 2 dakikada
[Timer]
OnBootSec=3min
OnUnitActiveSec=2min
[Install]
WantedBy=timers.target
UNIT

# 2) gece regresyon testi (03:30) + günlük yedek (03:00)
sudo -E tee /etc/systemd/system/nanobase-wren-eval.service >/dev/null <<UNIT
[Unit]
Description=Timaş Copilot gece regresyon testi (korpus → köprü → ham DB gerçeğiyle karşılaştır)
[Service]
Type=oneshot
User=administrator
WorkingDirectory=${ROOT}
ExecStart=/usr/bin/python3 ${ROOT}/tests/text2sql/timas-copilot-eval.py --bridge http://127.0.0.1:8794 --corpus ${ROOT}/tests/text2sql/timas-copilot-complex.json --truth ${ROOT}/artifacts/timas/complex-truth.json --out ${LOGDIR}/copilot-eval-%%Y%%m%%d.json
UNIT
# %%Y yok: systemd özel belirteç desteklemez → sarmalayıcı ile tarih
sudo -E tee /data/nanobaseai/bi/run-copilot-eval.sh >/dev/null <<SH
#!/usr/bin/env bash
set -o pipefail
OUT=${LOGDIR}/copilot-eval-\$(date +%Y%m%d).json
/usr/bin/python3 ${ROOT}/tests/text2sql/timas-copilot-eval.py --bridge http://127.0.0.1:8794 \\
  --corpus ${ROOT}/tests/text2sql/timas-copilot-complex.json --truth ${ROOT}/artifacts/timas/complex-truth.json --out "\$OUT" 2>&1 | tee -a ${LOGDIR}/copilot-eval.log
rc=\${PIPESTATUS[0]}
[[ \$rc -ne 0 ]] && logger -t wren-eval "REGRESYON HATASI: \$OUT" 
exit \$rc
SH
sudo chmod 755 /data/nanobaseai/bi/run-copilot-eval.sh
sudo -E sed -i "s#^ExecStart=.*#ExecStart=/data/nanobaseai/bi/run-copilot-eval.sh#" /etc/systemd/system/nanobase-wren-eval.service
sudo -E tee /etc/systemd/system/nanobase-wren-eval.timer >/dev/null <<UNIT
[Unit]
Description=Timaş Copilot regresyon testi her gece 03:30
[Timer]
OnCalendar=*-*-* 03:30:00
Persistent=true
[Install]
WantedBy=timers.target
UNIT
sudo -E tee /data/nanobaseai/bi/backup-wren-project.sh >/dev/null <<SH
#!/usr/bin/env bash
set -euo pipefail
ts=\$(date +%Y%m%d)
tar -czf ${BACKUP}/wren-project-\${ts}.tgz -C "$(dirname "${PROJECT}")" "$(basename "${PROJECT}")" --exclude='.wren' --exclude='target'
cp -f /data/nanobaseai/bi/secrets/wren-logo-connection.json ${BACKUP}/wren-logo-connection-\${ts}.json.enc 2>/dev/null || true
find ${BACKUP} -name 'wren-project-*.tgz' -mtime +14 -delete
find ${BACKUP} -name 'wren-logo-connection-*' -mtime +14 -delete
ls -la ${BACKUP} | tail -3
SH
sudo chmod 755 /data/nanobaseai/bi/backup-wren-project.sh
sudo -E tee /etc/systemd/system/nanobase-wren-backup.service >/dev/null <<UNIT
[Unit]
Description=Wren projesi (MDL + knowledge) günlük yedek
[Service]
Type=oneshot
User=administrator
ExecStart=/data/nanobaseai/bi/backup-wren-project.sh
UNIT
sudo -E tee /etc/systemd/system/nanobase-wren-backup.timer >/dev/null <<UNIT
[Unit]
Description=Wren projesi yedeği her gece 03:00
[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true
[Install]
WantedBy=timers.target
UNIT

# 3) log rotasyonu + journald sınırı
sudo -E tee /etc/logrotate.d/nanobase-wren >/dev/null <<LR
${LOGDIR}/*.log /data/logs/wren-watchdog.log {
    weekly
    rotate 8
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
LR
if ! grep -qE '^SystemMaxUse=' /etc/systemd/journald.conf; then
  echo 'SystemMaxUse=2G' | sudo -E tee -a /etc/systemd/journald.conf >/dev/null
  sudo -E systemctl restart systemd-journald || true
fi

sudo -E systemctl daemon-reload || log "WARN daemon-reload zaman aşımı"
for t in nanobase-wren-watchdog nanobase-wren-eval nanobase-wren-backup; do
  sudo -E systemctl enable --now "${t}.timer" >/dev/null 2>&1 || sudo -E systemctl start "${t}.timer"
done
log "ilk watchdog koşusu"; sudo -E systemctl start nanobase-wren-watchdog.service; cat /data/logs/wren-watchdog.state
log "ilk yedek"; sudo -E systemctl start nanobase-wren-backup.service; ls "$BACKUP" | tail -2
systemctl list-timers --no-pager 2>/dev/null | grep -E "wren" | cut -c1-120
log "hazır"
