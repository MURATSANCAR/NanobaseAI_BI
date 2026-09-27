#!/usr/bin/env bash
# Eksik Türkçe çevirileri doldurur; test sunucusunda arka plan birimi olarak koşar:
#   systemd-run --user --unit=destek-ceviri --collect --working-directory=$HOME/destek-ceviri \
#     bash tools/ceviri.sh <imaj>
# Klasör: tools/ (cevir.py, ceviri_hazirla.py), work/helpdesk.tr.po, work/nanobase_brand.tr.po (depodan).
# Sonuç work/*.tr.po ve ceviri-raporu.json; depoya geri kopyalanır.
set -euo pipefail
IMAGE=${1:?imaj}
ROOT=$(pwd)
mkdir -p in work lib
chmod 777 in

# 1. İmajdan şablonlar: Flow ve telephony için .pot (üretici git deposu ister), çatının tr.po'su.
docker run --rm -v "$ROOT/in:/out" --entrypoint bash "$IMAGE" -c '
  cd /home/frappe/frappe-bench
  for a in flow telephony; do
    (cd apps/$a && git init -q && git add -A && git -c user.email=x@x -c user.name=x commit -qm x) >/dev/null 2>&1
    bench generate-pot-file --app $a >/dev/null 2>&1
  done
  cp apps/flow/flow/locale/main.pot /out/flow.pot
  cp apps/telephony/telephony/locale/main.pot /out/telephony.pot
  cp apps/frappe/frappe/locale/tr.po /out/frappe.tr.po'

# 2. polib, köprünün Python'uyla aynı sürüme
[ -f lib/polib.py ] || /data/nanobaseai/bi/semantic-venv/bin/pip install -q --target lib polib
export PYTHONPATH="/data/nanobaseai/bi/frontend/backend:$ROOT/lib"
PY=/data/nanobaseai/bi/semantic-venv/bin/python

$PY tools/ceviri_hazirla.py "$ROOT"
$PY tools/cevir.py work/helpdesk.tr.po work/flow.tr.po work/nanobase_brand.tr.po \
  --sozluk work/helpdesk.tr.po --sozluk in/frappe.tr.po --rapor ceviri-raporu.json
echo BITTI
