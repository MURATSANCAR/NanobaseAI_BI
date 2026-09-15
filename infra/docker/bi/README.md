# NanobaseAI BI — Docker yığını

Taşınabilir kurulum: `db` (PostgreSQL katalog), `bridge` (NL→SQL motoru), `login` (Timaş AD girişi),
`web` (kokpit + /api proxy, oturum denetimi), `jobs` (özet, uyarı, pano, planlı rapor zamanlayıcıları).

## Kurulum
1. `.env` oluştur (`.env.example`'dan) — PG_PASSWORD, tokenlar, `PORTAL_ORIGIN` (tarayıcının açtığı HTTPS adresi), LLM anahtarı.
2. `secrets/logo-mssql-connection.json` koy (müşteri SQL sunucusu; host/port doğrudan).
3. `secrets/ad/timas-ad.json` koy (AD: host, port, netbios, dns_domain, base_dn, bind_user, bind_password). Yönetim ekranı bu dosyayı günceller.
4. Katalogu yükle: `db` ayağa kalkınca `catalog.sql`'i içine ver (ilk kurulumda bir kez).
5. `docker compose up -d --build`
6. Ön kapı: NPM konteynerini `bi_net`'e bağla; `npm-custom-http.conf` başındaki adımlarla HTTPS aç.
   Giriş çerezi Secure'dur: HTTP'den (ör. `:8088`) giriş yapılamaz, o port yalnız sunucu içi denetim içindir.

Motor koştuğu makinede GPU gerekmez; LLM dış uçtan çağrılır.
