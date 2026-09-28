#!/bin/bash
# M49 Veri güvenliği — test sunucusunda kabul (yerelde koşulmaz). Sıra:
#   1. Aday ağaç `git archive main` ile $W/src'ye açılır (._* sayısı 0 olmalı).
#   2. Giriş servisi aday server.py ile yeniden kurulur (sudo; kullanıcı çalıştırır): /opt/timas-login/server.py,
#      /etc/nanobase/timas-login.env içinde LOGIN_ADMIN_TOKEN (en az 24 karakter; köprü ortam dosyasındakiyle aynı),
#      timas-login.service'e EnvironmentFile satırı, nginx /timas/auth/ konumuna `proxy_set_header X-Real-IP $remote_addr;`.
#   3. Bu betik: pytest (M49 + yetki + giriş servisi), tsc, vitest, derleme.
#   4. Yan port köprüsü aday ağaçla (gerçek meta DB, CRM, AD; LOGIN_ADMIN_TOKEN ile) başlatılır; timasai'nin 15 dk'lık
#      oturumu açılır (varsa yetkisiz ikinci oturum COOKIE2).
#   5. kabul.py, sonra cleanup.py (önce --dry) ve giriş servisindeki test satırlarının silinmesi (aşağıda), oturum
#      satırları silinir; Yönetim → Kişiler'de gerçek olmayan hesap kalmadığına bakılır.
#   6. timas-security.service bir kez elle (?zorla=gunluk) koşturulur, sonra timas-security.timer etkinleştirilir.
#      SECURITY_RETENTION_APPLY kapalı kalır (açmak yönetici kararı, ekrandan önizlemeyle).
# Kullanım: W=/tmp/claude-m49 ./check.sh
set -u
W=${W:-/tmp/claude-m49}
cd $W/src || exit 1
echo "== ._ sayısı: $(find $W/src -name '._*' -type f -not -path '*/node_modules/*' | wc -l)"
cd $W/src/backend
echo "== pytest (M49 + yetki)"
/data/nanobaseai/bi/semantic-venv/bin/python -m pytest -q -p no:cacheprovider semantic_layer/tests/test_data_security.py \
  semantic_layer/tests/test_access.py 2>&1 | tail -25
echo "== giriş servisi birim testleri"
cd $W/src/scripts/server/portal-login && /opt/timas-login/venv/bin/python -m unittest -q test_server 2>&1 | tail -8
cd $W/src
ln -sfn /data/nanobaseai/bi/frontend/node_modules node_modules
echo "== tsc"
timeout 900 npx tsc -b 2>&1 | tail -30; echo "tsc çıkış=${PIPESTATUS[0]}"
echo "== vitest"
timeout 900 npx vitest run 2>&1 | tail -12
echo "== build"
VITE_BASE=/timas/ VITE_ENGINE_BASE=/timas timeout 1200 npx vite build --outDir $W/dist 2>&1 | tail -6
echo "== ekran metninde teknoloji adı"
grep -rniE '\b(systemd|docker|nginx|vllm|openvpn|qwen|sqlite|postgres)\b' $W/src/src/canvas/data-security || echo "yok"
cat <<'EOF'
== kabul (elle):
  LOGIN_DB=$W/login-copy.sqlite LOGIN_DB_SOURCE=/var/lib/timas-login/sessions.sqlite BASE=http://127.0.0.1:8798 COOKIE=... [COOKIE2=...] python kabul.py --out $W/kabul.json
  python cleanup.py --out $W/kabul.json --dry && python cleanup.py --out $W/kabul.json
  T0=$(python -c "import json,datetime;print(datetime.datetime.fromisoformat(json.load(open('$W/kabul.json'))['t0']).timestamp())")
  sudo sqlite3 /var/lib/timas-login/sessions.sqlite "DELETE FROM login_events WHERE username = 'timasai' AND at > $T0; DELETE FROM sessions WHERE username = 'timasai' AND created > $T0;"
  rm -f $W/login-copy.sqlite
EOF
