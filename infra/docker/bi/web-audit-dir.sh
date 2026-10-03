#!/bin/sh
# Denetim kaydı (kenar): bi_audit diski köke ait bağlanır; nginx işçisi günlük dosyayı (edge-YYYYAAGG.log) kendisi açar.
set -e
mkdir -p /var/log/nanobase-audit
chown nginx:nginx /var/log/nanobase-audit
chmod 0755 /var/log/nanobase-audit
