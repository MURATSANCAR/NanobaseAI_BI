# NanobaseAI BI — Docker yığını

Taşınabilir kurulum: `db` (PostgreSQL katalog), `bridge` (NL→SQL motoru), `login` (Timaş AD girişi),
`web` (kokpit + /api proxy, oturum denetimi), `jobs` (özet, uyarı, pano, planlı rapor zamanlayıcıları).

## Kurulum
1. `.env` oluştur (`.env.example`'dan) — PG_PASSWORD, tokenlar, `PORTAL_ORIGIN` (tarayıcının açtığı adres, ör. http://192.168.0.55), `COOKIE_SECURE` (HTTP'de 0), LLM anahtarı.
2. `secrets/logo-mssql-connection.json` koy (müşteri SQL sunucusu; host/port doğrudan).
3. `secrets/ad/timas-ad.json` koy (AD: host, port, netbios, dns_domain, base_dn, bind_user, bind_password). Yönetim ekranı bu dosyayı günceller.
4. Katalogu yükle: `db` ayağa kalkınca `catalog.sql`'i içine ver (ilk kurulumda bir kez).
5. `docker compose up -d --build`
6. Ön kapı: NPM konteynerini `bi_net`'e bağla; `npm-custom-http.conf` başındaki adımlar (HTTP).
   Giriş Origin denetimi yapar: arayüz `PORTAL_ORIGIN` adresinden açılmalı (`:8088` yalnız sunucu içi denetim).

Motor koştuğu makinede GPU gerekmez; LLM dış uçtan çağrılır.
