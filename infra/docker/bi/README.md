# NanobaseAI BI — Docker yığını

Taşınabilir kurulum: `db` (PostgreSQL katalog), `bridge` (NL→SQL motoru), `web` (kokpit + /api proxy).

## Kurulum
1. `.env` oluştur (`.env.example`'dan) — PG_PASSWORD, tokenlar; LLM uç boş bırakılabilir.
2. `secrets/logo-mssql-connection.json` koy (müşteri SQL sunucusu; host/port doğrudan).
3. Katalogu yükle: `db` ayağa kalkınca `catalog.sql`'i içine ver (ilk kurulumda bir kez).
4. `docker compose up -d --build`
5. Ön kapı: NPM konteynerini `bi_net`'e bağla, `web:80`'e proxy host.

Motor koştuğu makinede GPU gerekmez; LLM dış uçtan (müşteri) çağrılır.
