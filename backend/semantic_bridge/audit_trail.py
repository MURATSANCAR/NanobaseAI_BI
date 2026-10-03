"""Denetim izi: portalda kim, ne zaman, nereden, hangi ekranda, ne yazdı, neyi değiştirdi, neyi sildi.

Dört katman, tek zaman çizelgesi (Yönetim → Denetim kaydı):

1. **Ekran olayı** (`semantic_audit_ui`): açılan sayfa, basılan düğme/menü/sekme, seçilen seçenek. Tarayıcıdaki
   `src/canvas/auditTrail.ts` toplar, `POST /api/v1/audit/ui` ile gelir. Yazılan serbest metin buraya alınmaz;
   gönderilen her metin (promt, form) zaten istek kaydında durur.
2. **İstek** (`semantic_audit_requests`): köprüye gelen her istek — kişi, IP, tarayıcı, hangi ekrandan (Referer),
   hangi modül, gönderilen gövde (promt ve form içeriği dahil; parola/anahtar/jeton maskeli), yüklenen dosyaların adı
   ve boyu, sonuç kodu, süre. İstek kimliği (`rid`) cevapta `X-Request-Id` başlığıyla döner.
3. **Satır değişikliği** (`semantic_audit_rows`): veritabanında değişen her satır, eski ve yeni hâliyle. Postgres
   tetikleyicisi (`nb_audit_row`) bütün tablolara kurulur; modül kodu bir şey yazmasa da yakalanır. Silinen satırın
   tamamı, güncellenen satırın yalnız değişen alanları (önce → sonra) ve kimliği saklanır. Yalnız kişinin yazma
   isteği (POST/PUT/PATCH/DELETE) içinde açılan işlemlerde çalışır: gece eşitlemesi ve önbellek yazması kişinin işi
   değildir, kendi koşu kayıtları vardır.
4. **İşlem kaydı** (`semantic_audit`, admin.py): modülün kendi cümlesiyle «X kitabının fiyatını onayladı». Artık
   aynı istek kimliğini, IP'yi ve ekranı taşır.

Bütünlük: dört tablonun her satırı yazıldıktan sonra mühürlenir (`seal` = sha256(önceki mühür + satır),
`seal_seq` sıra). Silinen satır sırada boşluk, değiştirilen satır mühür uyuşmazlığı olarak görünür. Ayrıca
tetikleyici (`nb_audit_guard`) bu tablolarda UPDATE/DELETE/TRUNCATE'i reddeder; yalnız saklama süresi işi
(`nanobase.audit_purge`) silebilir ve mühürleyici (`nanobase.audit_seal`) boş mührü doldurabilir.

Kayıt asıl işi durdurmaz: yazılamazsa diske (`var/audit-spool`) düşer, veritabanı dönünce oradan aktarılır.
Sayı tavanı yoktur: gövde, satır, sayfa boyu kesilmez.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import queue
import re
import threading
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import parse_qsl

import sqlalchemy as sa

log = logging.getLogger("semantic_bridge.audit_trail")

_md = sa.MetaData()


def _seal_cols() -> list[sa.Column]:
    return [sa.Column("seal_seq", sa.BigInteger), sa.Column("seal", sa.String(64))]


REQUESTS = sa.Table(
    "semantic_audit_requests", _md,
    sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
    sa.Column("at", sa.DateTime(timezone=True), nullable=False, index=True),
    sa.Column("rid", sa.String(32), nullable=False, index=True),
    sa.Column("actor", sa.String(120), index=True),
    sa.Column("session", sa.String(16)),            # oturum çerezinin özeti: aynı oturumun isteklerini bağlar
    sa.Column("ip", sa.String(64)),
    sa.Column("ua", sa.Text),
    sa.Column("method", sa.String(8), nullable=False),
    sa.Column("path", sa.Text, nullable=False),
    sa.Column("query", sa.Text),
    sa.Column("page", sa.Text),                     # isteğin yapıldığı ekran (Referer yolu + sorgusu)
    sa.Column("module", sa.Text),                   # yolun sayfa yetkisi (sayfa:…), okunur ad ekranda
    sa.Column("kind", sa.String(12), nullable=False, index=True),   # read | write | denied | error | system | public
    sa.Column("status", sa.Integer),
    sa.Column("ms", sa.Integer),
    sa.Column("req_bytes", sa.BigInteger),
    sa.Column("resp_bytes", sa.BigInteger),
    sa.Column("content_type", sa.String(200)),
    sa.Column("body", sa.Text),                     # gönderilen gövde (maskeli JSON/form/metin)
    sa.Column("files", sa.Text),                    # çok parçalı yüklemede alan + dosya adları (JSON)
    *_seal_cols(),
    sa.Index("ix_semantic_audit_requests_unsealed", "id", postgresql_where=sa.text("seal IS NULL")),
)

ROWS = sa.Table(
    "semantic_audit_rows", _md,
    sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
    sa.Column("at", sa.DateTime(timezone=True), nullable=False, index=True),
    sa.Column("rid", sa.String(32), index=True),
    sa.Column("actor", sa.String(120), index=True),
    sa.Column("tbl", sa.String(120), nullable=False, index=True),
    sa.Column("op", sa.String(8), nullable=False),  # INSERT | UPDATE | DELETE
    sa.Column("pk", sa.Text),                       # {kolon: değer} — kaydın kimliği
    sa.Column("changed", sa.Text),                  # güncellemede değişen alanlar (JSON liste)
    sa.Column("old_row", sa.Text),                  # silmede bütün satır, güncellemede değişen alanların eski değeri
    sa.Column("new_row", sa.Text),                  # eklemede bütün satır, güncellemede değişen alanların yeni değeri
    sa.Column("txid", sa.BigInteger),
    *_seal_cols(),
    sa.Index("ix_semantic_audit_rows_record", "tbl", "pk"),
    sa.Index("ix_semantic_audit_rows_unsealed", "id", postgresql_where=sa.text("seal IS NULL")),
)

UI = sa.Table(
    "semantic_audit_ui", _md,
    sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
    sa.Column("at", sa.DateTime(timezone=True), nullable=False, index=True),
    sa.Column("client_at", sa.DateTime(timezone=True)),
    sa.Column("actor", sa.String(120), nullable=False, index=True),
    sa.Column("session", sa.String(16)),
    sa.Column("ip", sa.String(64)),
    sa.Column("ua", sa.Text),
    sa.Column("page", sa.Text),
    sa.Column("event", sa.String(16), nullable=False),   # view | click | change | leave
    sa.Column("label", sa.Text),
    sa.Column("detail", sa.Text),
    *_seal_cols(),
    sa.Index("ix_semantic_audit_ui_unsealed", "id", postgresql_where=sa.text("seal IS NULL")),
)

SEALS = sa.Table(
    "semantic_audit_seal", _md,
    sa.Column("tbl", sa.String(64), primary_key=True),
    sa.Column("last_seq", sa.BigInteger, nullable=False, default=0),
    sa.Column("last_hash", sa.String(64), nullable=False, default=""),
    sa.Column("anchor_seq", sa.BigInteger, nullable=False, default=0),     # saklama süresiyle silinen son sıra
    sa.Column("anchor_hash", sa.String(64), nullable=False, default=""),
    sa.Column("verified_at", sa.DateTime(timezone=True)),
    sa.Column("verify_json", sa.Text),
)

#: Mühürlenen tablolar (işlem kaydı admin.py'de).
SEALED = ("semantic_audit", "semantic_audit_requests", "semantic_audit_rows", "semantic_audit_ui")

#: Satır tetikleyicisi kurulmayan tablolar: denetim/güvenlik kayıtlarının kendisi ve kendisi zaten kayıt olan
#: sıra/iz tabloları (soru kaydı promt izleyicide, model sırası kendi ekranında).
_NO_ROW_TRIGGER = frozenset({
    *SEALED, "semantic_audit_seal",
    "sl_query_log", "sl_llm_queue", "sl_llm_job", "sl_llm_gate", "sl_schema_stamp",
    "alembic_version", "nanobase_alembic_version",
    "semantic_security_logins", "semantic_security_access", "semantic_security_state", "semantic_security_retention_runs",
    "semantic_admin_group", "semantic_hr_page_visits", "semantic_hr_access_log",
})

#: Değeri hiçbir kayda açık yazılmayan alan adları (gövde, satır). Değişip değişmediği özetle görünür.
SECRET_RX = re.compile(r"(pass(word|wd)?|parola|sifre|şifre|secret|token|api_?key|apikey|credential|private_?key|"
                       r"cookie|authorization|client_secret|smtp_pass)", re.I)
#: Değeri bir satırın başka alanına bağlı gizli olan tablolar: (anahtar kolonu, değer kolonu).
_KEYED_SECRETS = {"semantic_settings": ("key", "value")}

CTX: ContextVar[Optional[dict]] = ContextVar("audit_ctx", default=None)

_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_TEXT_TYPES = ("application/json", "application/x-www-form-urlencoded", "text/", "application/xml",
               "application/graphql", "+json")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def new_rid() -> str:
    return uuid.uuid4().hex


def current() -> Optional[dict]:
    return CTX.get()


# ------------------------------------------------------------------ maskeleme


def mask(value: Any, key: str = "") -> Any:
    """Gövdedeki gizli alanları maskeler (iç içe). Değer yerine «gizli · özet»: değiştiği görünür, kendisi görünmez."""
    if key and SECRET_RX.search(key) and value not in (None, "", [], {}):
        return hidden(value)
    if isinstance(value, dict):
        return {k: mask(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [mask(v, key) for v in value]
    return value


def hidden(value: Any) -> str:
    raw = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return "«gizli · " + hashlib.md5(raw.encode("utf-8")).hexdigest()[:8] + "»"  # noqa: S324 — kimlik değil, iz


def mask_body(raw: bytes, content_type: str) -> Optional[str]:
    if not raw:
        return None
    ct = (content_type or "").lower()
    text = raw.decode("utf-8", errors="replace")
    if "json" in ct:
        try:
            return json.dumps(mask(json.loads(text)), ensure_ascii=False)
        except ValueError:
            return text
    if "x-www-form-urlencoded" in ct:
        pairs = parse_qsl(text, keep_blank_values=True)
        return json.dumps({k: (hidden(v) if SECRET_RX.search(k) and v else v) for k, v in pairs}, ensure_ascii=False)
    return text


_PART_RX = re.compile(rb'content-disposition:\s*form-data;\s*name="([^"]*)"(?:;\s*filename\*?="?([^"\r\n]*)"?)?', re.I)


# ------------------------------------------------------------------ istek ara katmanı


class Middleware:
    """Saf ASGI ara katmanı: gövdeyi akarken kopyalar (bekletmez), cevabın kodunu ve boyunu sayar, isteği kuyruğa atar.

    `resolve(cookie) -> Optional[str]`: oturumun kişisi (giriş servisi; sayfa kapısıyla aynı 10 sn önbellek).
    `module_of(path) -> Optional[str]`: yolun sayfa yetkisi anahtarları."""

    def __init__(self, app: Any, resolve: Callable[[str], Optional[str]], module_of: Callable[[str], Optional[str]],
                 system_name: str) -> None:
        self.app = app
        self.resolve = resolve
        self.module_of = module_of
        self.system_name = system_name

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope.get("type") != "http" or scope.get("path") in ("/health", "/api/v1/audit/ui"):
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers") or []}
        cookie = headers.get("cookie", "")
        if "timas_session=swr." in cookie:      # köprünün kendi hazır cevap tazelemesi: kişinin isteği değil
            await self.app(scope, receive, send)
            return
        from starlette.concurrency import run_in_threadpool

        method = scope.get("method", "GET").upper()
        path = scope.get("path", "")
        ip = headers.get("x-real-ip") or (headers.get("x-forwarded-for", "").split(",")[0].strip() or None) \
            or ((scope.get("client") or [None])[0])
        via_proxy = bool(headers.get("x-real-ip") or headers.get("x-forwarded-for"))
        session = session_key(cookie)
        actor: Optional[str] = None
        if session:
            try:
                actor = await run_in_threadpool(self.resolve, cookie)
            except Exception:  # noqa: BLE001 — oturum çözülemedi: kayıt yine yazılır
                actor = None
        if actor:
            kind = "write" if method in _WRITE_METHODS else "read"
        elif not via_proxy:
            actor, kind = self.system_name, "system"          # zamanlayıcı / betik (sunucunun içinden)
        else:
            kind = "public"                                   # oturumsuz dış istek (anket bağlantısı, giriş öncesi)
        rid = new_rid()
        page = _page_of(headers.get("referer", ""))
        ctx = {"rid": rid, "actor": actor, "ip": ip, "ua": headers.get("user-agent"), "page": page,
               "method": method, "path": path, "write": method in _WRITE_METHODS, "session": session}
        ct = headers.get("content-type", "")
        text_body = any(t in ct.lower() for t in _TEXT_TYPES)
        multipart = "multipart/" in ct.lower()
        chunks: list[bytes] = []
        parts: list[dict[str, str]] = []
        tail = b""
        size = 0

        async def rec() -> dict:
            nonlocal size, tail
            msg = await receive()
            if msg.get("type") == "http.request":
                body = msg.get("body") or b""
                size += len(body)
                if text_body:
                    chunks.append(body)
                elif multipart and body:
                    # Parça başlıkları parça sınırında bölünebilir: önceki parçanın sonu ile birlikte aranır.
                    buf = tail + body
                    for m in _PART_RX.finditer(buf):
                        p = {"name": m.group(1).decode("utf-8", "replace")}
                        if m.group(2):
                            p["filename"] = m.group(2).decode("utf-8", "replace")
                        if p not in parts:
                            parts.append(p)
                    tail = buf[-400:]
            return msg

        status = {"code": None, "bytes": 0}

        async def snd(msg: dict) -> None:
            if msg.get("type") == "http.response.start":
                status["code"] = msg.get("status")
                msg = dict(msg)
                msg["headers"] = list(msg.get("headers") or []) + [(b"x-request-id", rid.encode())]
            elif msg.get("type") == "http.response.body":
                status["bytes"] += len(msg.get("body") or b"")
            await send(msg)

        t0 = time.monotonic()
        token = CTX.set(ctx)
        try:
            await self.app(scope, rec, snd)
        except Exception:
            status["code"] = status["code"] or 500
            raise
        finally:
            CTX.reset(token)
            code = status["code"]
            k = kind
            if code in (401, 403):
                k = "denied"
            elif code is not None and code >= 500:
                k = "error"
            try:
                module = self.module_of(path)
            except Exception:  # noqa: BLE001
                module = None
            enqueue("request", {
                "at": _now(), "rid": rid, "actor": actor, "session": session, "ip": ip, "ua": ctx["ua"],
                "method": method, "path": path, "query": scope.get("query_string", b"").decode("latin-1") or None,
                "page": page, "module": module, "kind": k, "status": code, "ms": int((time.monotonic() - t0) * 1000),
                "req_bytes": size or int(headers.get("content-length") or 0) or None, "resp_bytes": status["bytes"],
                "content_type": ct[:200] or None,
                "body": mask_body(b"".join(chunks), ct) if text_body else None,
                "files": json.dumps(parts, ensure_ascii=False) if parts else None,
            })


def session_key(cookie: str) -> Optional[str]:
    # Giriş servisi HTTPS'te `__Secure-timas_session`, düz HTTP'de `timas_session` yazar.
    m = re.search(r"(?:^|;\s*)(?:__Secure-)?timas_session=([^;]+)", cookie or "")
    return hashlib.sha256(m.group(1).encode()).hexdigest()[:16] if m else None


def _page_of(referer: str) -> Optional[str]:
    if not referer:
        return None
    m = re.match(r"^[a-z]+://[^/]+(/.*)?$", referer, re.I)
    return (m.group(1) or "/") if m else referer


# ------------------------------------------------------------------ satır bağlamı (Postgres)

_bound: set[int] = set()


def bind_engine(engine: sa.engine.Engine) -> None:
    """Kişinin yazma isteğinde açılan her işlemin başına `nanobase.audit` bağlamını koyar; satır tetikleyicisi oradan
    kişiyi ve istek kimliğini okur. Bağlam yoksa (arka plan işi) hiçbir şey yapılmaz, tetikleyici de çalışmaz."""
    if engine.dialect.name != "postgresql" or id(engine) in _bound:
        return
    _bound.add(id(engine))
    flag = "nb_audit_rid"

    @sa.event.listens_for(engine, "before_cursor_execute")
    def _stamp(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        c = CTX.get()
        if not c or not c.get("write") or not c.get("actor"):
            return
        if conn.info.get(flag) == c["rid"] or not conn.in_transaction():
            return
        cursor.execute("SELECT set_config('nanobase.audit', %s, true)",
                       (json.dumps({"rid": c["rid"], "actor": c["actor"]}, ensure_ascii=False),))
        conn.info[flag] = c["rid"]

    def _clear(conn, *_a):  # noqa: ANN001
        conn.info.pop(flag, None)

    sa.event.listen(engine, "commit", _clear)
    sa.event.listen(engine, "rollback", _clear)

    @sa.event.listens_for(engine.pool, "reset")
    def _reset(dbapi_conn, record, reset_state):  # noqa: ANN001
        record.info.pop(flag, None)

    @sa.event.listens_for(engine.pool, "checkin")
    def _checkin(dbapi_conn, record):  # noqa: ANN001
        if record is not None:
            record.info.pop(flag, None)


_ROW_FN = r"""
CREATE OR REPLACE FUNCTION nb_audit_hidden(v jsonb, how text) RETURNS jsonb LANGUAGE sql IMMUTABLE AS $f$
  SELECT CASE WHEN v IS NULL OR v = 'null'::jsonb THEN v
              WHEN how = 'b' THEN to_jsonb('«ikili veri · ' || greatest((length(v #>> '{}') - 2) / 2, 0)
                                           || ' bayt · ' || left(md5(v #>> '{}'), 8) || '»')
              ELSE to_jsonb('«gizli · ' || left(md5(v #>> '{}'), 8) || '»') END
$f$;

CREATE OR REPLACE FUNCTION nb_audit_row() RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE
  ctx jsonb;
  o jsonb; n jsonb; ch text[]; k text; parts text[]; pk jsonb := '{}'::jsonb;
  pkcols text[] := string_to_array(NULLIF(TG_ARGV[0], ''), ',');
  masks text[] := string_to_array(NULLIF(TG_ARGV[1], ''), ',');
  keyed text[] := string_to_array(NULLIF(TG_ARGV[2], ''), ',');
BEGIN
  ctx := NULLIF(current_setting('nanobase.audit', true), '')::jsonb;
  IF ctx IS NULL THEN RETURN NULL; END IF;
  IF TG_OP <> 'INSERT' THEN o := to_jsonb(OLD); END IF;
  IF TG_OP <> 'DELETE' THEN n := to_jsonb(NEW); END IF;
  IF TG_OP = 'UPDATE' THEN
    SELECT array_agg(e.key ORDER BY e.key) INTO ch FROM jsonb_each(n) e WHERE e.value IS DISTINCT FROM o -> e.key;
    IF ch IS NULL THEN RETURN NULL; END IF;
  END IF;
  IF pkcols IS NOT NULL THEN
    FOREACH k IN ARRAY pkcols LOOP pk := pk || jsonb_build_object(k, coalesce(n, o) -> k); END LOOP;
    IF TG_OP = 'UPDATE' THEN
      o := (SELECT jsonb_object_agg(key, value) FROM jsonb_each(o) WHERE key = ANY(ch));
      n := (SELECT jsonb_object_agg(key, value) FROM jsonb_each(n) WHERE key = ANY(ch));
    END IF;
  END IF;
  IF masks IS NOT NULL THEN
    FOREACH k IN ARRAY masks LOOP
      parts := string_to_array(k, ':');
      IF o ? parts[1] THEN o := jsonb_set(o, ARRAY[parts[1]], nb_audit_hidden(o -> parts[1], parts[2])); END IF;
      IF n ? parts[1] THEN n := jsonb_set(n, ARRAY[parts[1]], nb_audit_hidden(n -> parts[1], parts[2])); END IF;
    END LOOP;
  END IF;
  IF keyed IS NOT NULL AND (coalesce(to_jsonb(NEW), to_jsonb(OLD)) ->> keyed[1]) ~* $re$__SECRET_RX__$re$ THEN
    IF o ? keyed[2] THEN o := jsonb_set(o, ARRAY[keyed[2]], nb_audit_hidden(o -> keyed[2], 's')); END IF;
    IF n ? keyed[2] THEN n := jsonb_set(n, ARRAY[keyed[2]], nb_audit_hidden(n -> keyed[2], 's')); END IF;
  END IF;
  INSERT INTO semantic_audit_rows(at, rid, actor, tbl, op, pk, changed, old_row, new_row, txid)
  VALUES (clock_timestamp(), ctx ->> 'rid', ctx ->> 'actor', TG_TABLE_NAME, TG_OP,
          CASE WHEN pk = '{}'::jsonb THEN NULL ELSE pk::text END, to_jsonb(ch)::text, o::text, n::text, txid_current());
  RETURN NULL;
END $f$;

CREATE OR REPLACE FUNCTION nb_audit_guard() RETURNS trigger LANGUAGE plpgsql AS $f$
BEGIN
  IF current_setting('nanobase.audit_purge', true) = '1' THEN
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
  END IF;
  IF TG_OP = 'UPDATE' AND current_setting('nanobase.audit_seal', true) = '1' THEN
    IF OLD.seal IS NULL AND (to_jsonb(NEW) - 'seal' - 'seal_seq') = (to_jsonb(OLD) - 'seal' - 'seal_seq') THEN
      RETURN NEW;
    END IF;
  END IF;
  RAISE EXCEPTION 'Denetim kaydı değiştirilemez ve silinemez (%: %).', TG_TABLE_NAME, TG_OP;
END $f$;
""".replace("__SECRET_RX__", SECRET_RX.pattern.replace("(?i)", ""))


_ensure_lock = threading.Lock()


def ensure(engine: sa.engine.Engine) -> None:
    """Tablolar, işlem kaydının yeni kolonları, tetikleyici işlevleri ve koruma tetikleyicileri (bir kez, damgalı).
    Kilitli: açılışta yazıcı ve ilk istekler aynı anda kurmaya kalkınca CREATE TABLE yarışı olmasın."""
    with _ensure_lock:
        _ensure(engine)


def _ensure(engine: sa.engine.Engine) -> None:
    from semantic_layer.store import schema_stamp

    def install() -> None:
        _md.create_all(engine, checkfirst=True)
        if engine.dialect.name != "postgresql":
            return
        with engine.begin() as c:
            for col, typ in (("rid", "varchar(32)"), ("ip", "varchar(64)"), ("ua", "text"), ("page", "text"),
                             ("seal_seq", "bigint"), ("seal", "varchar(64)")):
                c.exec_driver_sql(f"ALTER TABLE semantic_audit ADD COLUMN IF NOT EXISTS {col} {typ}")
            c.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_semantic_audit_rid ON semantic_audit (rid)")
            c.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_semantic_audit_unsealed ON semantic_audit (id) WHERE seal IS NULL")
            c.exec_driver_sql(_ROW_FN.replace("%", "%%"))  # psycopg2 parametresiz de % biçimler
            for t in SEALED:
                c.exec_driver_sql(f"DROP TRIGGER IF EXISTS nb_audit_guard ON {t}")
                c.exec_driver_sql(f"CREATE TRIGGER nb_audit_guard BEFORE UPDATE OR DELETE ON {t} "
                                  "FOR EACH ROW EXECUTE FUNCTION nb_audit_guard()")
                c.exec_driver_sql(f"DROP TRIGGER IF EXISTS nb_audit_guard_trunc ON {t}")
                c.exec_driver_sql(f"CREATE TRIGGER nb_audit_guard_trunc BEFORE TRUNCATE ON {t} "
                                  "FOR EACH STATEMENT EXECUTE FUNCTION nb_audit_guard()")

    # semantic_audit admin.py'de tanımlı; bu kurulum onu (yoksa) açar ve üstüne kolon ekler.
    from semantic_bridge import admin as admin_mod

    def install_all() -> None:
        admin_mod.AUDIT.create(engine, checkfirst=True)
        install()

    schema_stamp.run(engine, list(_md.sorted_tables), install_all, name="audit_trail", extra="v1:" + _ROW_FN)


_TRIGGER_SQL = """
SELECT c.relname,
       coalesce((SELECT string_agg(a.attname, ',' ORDER BY array_position(i.indkey::int2[], a.attnum))
                 FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                 WHERE i.indrelid = c.oid AND i.indisprimary), '') AS pk,
       coalesce((SELECT string_agg(a.attname || ':' || CASE WHEN t.typname = 'bytea' THEN 'b' ELSE 's' END, ',' ORDER BY a.attnum)
                 FROM pg_attribute a JOIN pg_type t ON t.oid = a.atttypid
                 WHERE a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
                   AND (t.typname = 'bytea' OR a.attname ~* %(rx)s)), '') AS masks,
       (SELECT encode(tg.tgargs, 'escape') FROM pg_trigger tg WHERE tg.tgrelid = c.oid AND tg.tgname = 'nb_audit_row') AS have
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p') AND n.nspname = current_schema() AND NOT c.relispartition
"""


def install_row_triggers(engine: sa.engine.Engine) -> dict[str, Any]:
    """Satır tetikleyicisini tetikleyicisi olmayan ya da kolon yapısı değişen her tabloya kurar. Kilit
    alınamayan tablo atlanır, sonraki turda yeniden denenir (modüller tablolarını ilk istekte kurar)."""
    if engine.dialect.name != "postgresql":
        return {"installed": 0, "skipped": 0}
    done, failed = 0, []
    with engine.connect() as c:
        rows = c.exec_driver_sql(_TRIGGER_SQL, {"rx": SECRET_RX.pattern}).all()
    for name, pk, masks, have in rows:
        if name in _NO_ROW_TRIGGER or name.endswith("_log") or not re.match(r"^[a-z0-9_]+$", name):
            continue
        keyed = ",".join(_KEYED_SECRETS.get(name, ()))
        want = f"{pk}\\000{masks}\\000{keyed}\\000"
        if have == want:
            continue
        try:
            with engine.begin() as c:
                c.exec_driver_sql("SET LOCAL lock_timeout = '3s'")
                c.exec_driver_sql(f'DROP TRIGGER IF EXISTS nb_audit_row ON "{name}"')
                c.exec_driver_sql(
                    f'CREATE TRIGGER nb_audit_row AFTER INSERT OR UPDATE OR DELETE ON "{name}" FOR EACH ROW '
                    "WHEN (coalesce(current_setting('nanobase.audit', true), '') <> '') "
                    "EXECUTE FUNCTION nb_audit_row(%(a)s, %(b)s, %(c)s)".replace("%(a)s", _lit(pk))
                    .replace("%(b)s", _lit(masks)).replace("%(c)s", _lit(keyed)))
            done += 1
        except Exception as e:  # noqa: BLE001
            failed.append(name)
            log.warning("denetim: %s tablosuna satır tetikleyicisi kurulamadı: %s", name, e)
    if done or failed:
        log.info("denetim: satır tetikleyicisi %d tabloya kuruldu, %d tablo sonraki tura kaldı", done, len(failed))
    return {"installed": done, "skipped": len(failed)}


def _lit(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


# ------------------------------------------------------------------ yazıcı (kuyruk → veritabanı, olmazsa disk)

_q: "queue.Queue[tuple[str, dict]]" = queue.Queue()
_engine_fn: Optional[Callable[[], Optional[sa.engine.Engine]]] = None
_thread: Optional[threading.Thread] = None
_maint: Optional[threading.Thread] = None
_stop = threading.Event()
_TABLES = {"request": REQUESTS, "ui": UI}


def enqueue(kind: str, row: dict) -> None:
    _q.put((kind, row))


def spool_dir() -> Path:
    base = os.environ.get("AUDIT_SPOOL_DIR") or os.path.join(os.environ.get("SEMANTIC_VAR_DIR", "/data/nanobaseai/bi/var"),
                                                              "audit-spool")
    return Path(base)


def spool(kind: str, row: dict) -> None:
    """Veritabanına yazılamayan kayıt: diske, sonra aktarılır. Disk de yoksa son çare sunucu günlüğü."""
    try:
        d = spool_dir()
        d.mkdir(parents=True, exist_ok=True)
        with open(d / f"{_now():%Y%m%d}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"kind": kind, "row": row}, ensure_ascii=False, default=_jdefault) + "\n")
    except Exception as e:  # noqa: BLE001
        log.error("denetim: kayıt ne veritabanına ne diske yazılabildi (%s): %s %s", e, kind,
                  json.dumps(row, ensure_ascii=False, default=str))


def _jdefault(v: Any) -> Any:
    if isinstance(v, datetime):
        return {"__dt": v.isoformat()}
    return str(v)


def _jload(row: dict) -> dict:
    return {k: (datetime.fromisoformat(v["__dt"]) if isinstance(v, dict) and "__dt" in v else v) for k, v in row.items()}


def _write(engine: sa.engine.Engine, batch: list[tuple[str, dict]]) -> None:
    from semantic_bridge import admin as admin_mod

    groups: dict[str, list[dict]] = {}
    for kind, row in batch:
        groups.setdefault(kind, []).append(row)
    with engine.begin() as c:
        for kind, rows in groups.items():
            t = admin_mod.AUDIT if kind == "action" else _TABLES[kind]
            c.execute(t.insert(), rows)


def _replay_spool(engine: sa.engine.Engine) -> None:
    d = spool_dir()
    if not d.is_dir():
        return
    for f in sorted(d.glob("*.jsonl")):
        try:
            items = [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines() if line.strip()]
            _write(engine, [(i["kind"], _jload(i["row"])) for i in items])
            f.unlink()
            log.info("denetim: diskte bekleyen %d kayıt veritabanına aktarıldı (%s)", len(items), f.name)
        except Exception as e:  # noqa: BLE001
            log.warning("denetim: diskteki kayıt aktarılamadı (%s): %s", f.name, e)
            return


def start(engine_fn: Callable[[], Optional[sa.engine.Engine]]) -> None:
    """Yazıcı + mühürleyici + tetikleyici kurucu tek iş parçacığında. Çalışma ortamı hazır değilken kuyruk bekler."""
    global _engine_fn, _thread, _maint
    _engine_fn = engine_fn
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    # Yazıcı ayrı, bakım (tetikleyici kurulumu, mühür, doğrulama) ayrı: uzun bakım turu kaydı bekletmesin.
    _thread = threading.Thread(target=_loop, name="audit-trail", daemon=True)
    _thread.start()
    _maint = threading.Thread(target=_maintenance, name="audit-trail-maint", daemon=True)
    _maint.start()


def stop() -> None:
    _stop.set()
    for t in (_thread, _maint):
        if t:
            t.join(timeout=5)
    _drain(final=True)


def _engine() -> Optional[sa.engine.Engine]:
    try:
        return _engine_fn() if _engine_fn else None
    except Exception:  # noqa: BLE001
        return None


def _drain(final: bool = False) -> None:
    batch: list[tuple[str, dict]] = []
    while True:
        try:
            batch.append(_q.get_nowait())
        except queue.Empty:
            break
    if not batch:
        return
    eng = _engine()
    if eng is None:
        if final:
            for kind, row in batch:
                spool(kind, row)
        else:
            for item in batch:          # çalışma ortamı kuruluyor: geri koy
                _q.put(item)
        return
    try:
        ensure(eng)
        _write(eng, batch)
    except Exception as e:  # noqa: BLE001
        log.warning("denetim: %d kayıt veritabanına yazılamadı, diske alındı: %s", len(batch), e)
        for kind, row in batch:
            spool(kind, row)


def _loop() -> None:
    ready = False
    while not _stop.is_set():
        _stop.wait(1.0)
        try:
            eng = _engine()
            if eng is not None and not ready:
                ensure(eng)
                bind_engine(eng)
                _replay_spool(eng)
                ready = True
            _drain()
        except Exception as e:  # noqa: BLE001
            log.warning("denetim: yazıcı turu hata verdi: %s", e)


def _maintenance() -> None:
    last_seal = last_trig = last_replay = 0.0
    last_verify: Optional[float] = None
    while not _stop.is_set():
        _stop.wait(5.0)
        eng = _engine()
        if eng is None:
            continue
        now = time.monotonic()
        try:
            ensure(eng)
            if now - last_trig > 300:
                last_trig = now
                with _advisory(eng, 72110) as got:
                    if got:
                        install_row_triggers(eng)
            if now - last_replay > 300:
                last_replay = now
                _replay_spool(eng)
            if now - last_seal > 60:
                last_seal = now
                with _advisory(eng, 72111) as got:
                    if got:
                        seal_all(eng)
            # İlk doğrulama açılıştan 10 dk sonra, sonra günde bir.
            if last_verify is None:
                last_verify = now - 86400 + 600
            if now - last_verify > 86400:
                last_verify = now
                with _advisory(eng, 72112) as got:
                    if got:
                        verify_all(eng)
        except Exception as e:  # noqa: BLE001
            log.warning("denetim: bakım turu hata verdi: %s", e)


class _advisory:
    """Postgres oturum kilidi: aynı veritabanında iki süreç aynı bakım işini birlikte yapmasın."""

    def __init__(self, engine: sa.engine.Engine, key: int) -> None:
        self.engine, self.key, self.conn = engine, key, None

    def __enter__(self) -> bool:
        if self.engine.dialect.name != "postgresql":
            return True
        self.conn = self.engine.connect()
        got = bool(self.conn.exec_driver_sql(f"SELECT pg_try_advisory_lock({self.key})").scalar())
        self.conn.commit()
        if not got:
            self.conn.close()
            self.conn = None
        return got

    def __exit__(self, *_a: Any) -> None:
        if self.conn is not None:
            self.conn.exec_driver_sql(f"SELECT pg_advisory_unlock({self.key})")
            self.conn.commit()
            self.conn.close()


# ------------------------------------------------------------------ mühür

_SEAL_BATCH = 2000          # parti boyu tavan değildir: mühürlenmemiş satır kalmayana kadar döner
_SEAL_DELAY = timedelta(seconds=30)


def _canon(row: dict) -> str:
    out = {}
    for k, v in row.items():
        if k in ("seal", "seal_seq"):
            continue
        if isinstance(v, datetime):
            v = (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()
        out[k] = v
    return json.dumps(out, ensure_ascii=False, sort_keys=True, default=str)


def _digest(prev: str, row: dict) -> str:
    return hashlib.sha256((prev + "\n" + _canon(row)).encode("utf-8")).hexdigest()


def _table(engine: sa.engine.Engine, name: str) -> sa.Table:
    from semantic_bridge import admin as admin_mod

    return {"semantic_audit": admin_mod.AUDIT, "semantic_audit_requests": REQUESTS, "semantic_audit_rows": ROWS,
            "semantic_audit_ui": UI}[name]


def _reflect(engine: sa.engine.Engine, name: str) -> sa.Table:
    """Mühür tablodaki bütün kolonları kapsar (kodda tanımlı olmayan sonradan eklenen kolon dahil)."""
    return sa.Table(name, sa.MetaData(), autoload_with=engine)


def seal_all(engine: sa.engine.Engine) -> dict[str, int]:
    out = {}
    for name in SEALED:
        out[name] = seal_table(engine, name)
    return out


def seal_table(engine: sa.engine.Engine, name: str) -> int:
    T = _reflect(engine, name)
    done = 0
    while True:
        with engine.begin() as c:
            if engine.dialect.name == "postgresql":
                c.exec_driver_sql("SELECT set_config('nanobase.audit_seal', '1', true)")
            st = c.execute(sa.select(SEALS).where(SEALS.c.tbl == name).with_for_update()).mappings().first()
            if st is None:
                c.execute(SEALS.insert().values(tbl=name, last_seq=0, last_hash="", anchor_seq=0, anchor_hash=""))
                seq, prev = 0, ""
            else:
                seq, prev = int(st["last_seq"]), st["last_hash"]
            rows = c.execute(sa.select(T).where(T.c.seal.is_(None), T.c.at < _now() - _SEAL_DELAY)
                             .order_by(T.c.id).limit(_SEAL_BATCH)).mappings().all()
            if not rows:
                return done
            for r in rows:
                seq += 1
                prev = _digest(prev, dict(r))
                c.execute(T.update().where(T.c.id == r["id"]).values(seal_seq=seq, seal=prev))
            c.execute(SEALS.update().where(SEALS.c.tbl == name).values(last_seq=seq, last_hash=prev))
            done += len(rows)


def verify_table(engine: sa.engine.Engine, name: str) -> dict[str, Any]:
    """Zinciri baştan yürür: her mührü yeniden hesaplar, sıradaki boşlukları ve uyuşmazlıkları sayar."""
    T = _reflect(engine, name)
    with engine.connect() as c:
        st = c.execute(sa.select(SEALS).where(SEALS.c.tbl == name)).mappings().first()
    anchor_seq = int(st["anchor_seq"]) if st else 0
    prev = st["anchor_hash"] if st else ""
    expect = anchor_seq + 1
    checked, broken, gaps, first_bad = 0, 0, 0, None
    last = 0
    while True:
        with engine.connect() as c:
            rows = c.execute(sa.select(T).where(T.c.seal_seq.isnot(None), T.c.seal_seq > last)
                             .order_by(T.c.seal_seq).limit(_SEAL_BATCH)).mappings().all()
        if not rows:
            break
        for r in rows:
            s = int(r["seal_seq"])
            if s != expect:
                gaps += s - expect
                first_bad = first_bad or {"seq": expect, "why": f"{s - expect} kayıt eksik (sıra {expect}–{s - 1})"}
                prev = None                      # boşluktan sonra zincir bu satırın kendi mührüyle sürer
            h = _digest(prev, dict(r)) if prev is not None else r["seal"]
            if h != r["seal"]:
                broken += 1
                first_bad = first_bad or {"seq": s, "id": r["id"], "why": "satır mühürlendikten sonra değişmiş"}
            prev, expect, last = r["seal"], s + 1, s
            checked += 1
    with engine.connect() as c:
        unsealed = c.execute(sa.select(sa.func.count()).select_from(T).where(T.c.seal.is_(None))).scalar() or 0
        total = c.execute(sa.select(sa.func.count()).select_from(T)).scalar() or 0
    last_seq = int(st["last_seq"]) if st else 0
    missing_tail = max(0, last_seq - last) if last_seq else 0
    if missing_tail:
        gaps += missing_tail
        first_bad = first_bad or {"seq": last + 1, "why": f"zincirin sonundan {missing_tail} kayıt eksik"}
    return {"table": name, "checked": checked, "broken": broken, "missing": gaps, "unsealed": int(unsealed),
            "total": int(total), "ok": broken == 0 and gaps == 0, "firstProblem": first_bad, "anchorSeq": anchor_seq}


def verify_all(engine: sa.engine.Engine) -> dict[str, Any]:
    t0 = time.monotonic()
    results = [verify_table(engine, n) for n in SEALED]
    out = {"at": _now().isoformat(), "ok": all(r["ok"] for r in results), "tables": results,
           "seconds": round(time.monotonic() - t0, 1)}
    with engine.begin() as c:
        for r in results:
            c.execute(SEALS.update().where(SEALS.c.tbl == r["table"]).values(
                verified_at=_now(), verify_json=json.dumps(out, ensure_ascii=False)))
    if not out["ok"]:
        log.error("denetim: mühür doğrulaması BOZUK: %s", json.dumps(results, ensure_ascii=False))
    return out


def seal_state(engine: sa.engine.Engine) -> dict[str, Any]:
    with engine.connect() as c:
        rows = c.execute(sa.select(SEALS)).mappings().all()
    last = None
    for r in rows:
        if r["verify_json"]:
            last = json.loads(r["verify_json"])
            break
    return {"tables": [{"table": r["tbl"], "lastSeq": r["last_seq"], "anchorSeq": r["anchor_seq"],
                        "verifiedAt": r["verified_at"].isoformat() if r["verified_at"] else None} for r in rows],
            "lastVerify": last}


def note_purge(conn: sa.engine.Connection, name: str, ids: list[int]) -> None:
    """Saklama süresi işi silmeden önce: silinen en büyük mühür sırasını çapa yapar (doğrulama oradan başlar)."""
    if name not in SEALED or not ids:
        return
    if conn.dialect.name == "postgresql":
        conn.exec_driver_sql("SELECT set_config('nanobase.audit_purge', '1', true)")
    T = _reflect(conn.engine, name)
    top = conn.execute(sa.select(T.c.seal_seq, T.c.seal).where(T.c.id.in_(ids), T.c.seal_seq.isnot(None))
                       .order_by(T.c.seal_seq.desc()).limit(1)).first()
    if top is not None:
        conn.execute(SEALS.update().where(SEALS.c.tbl == name, SEALS.c.anchor_seq < top[0])
                     .values(anchor_seq=top[0], anchor_hash=top[1]))


# ------------------------------------------------------------------ ekran olayları


_UI_EVENTS = frozenset({"view", "click", "change", "leave", "submit"})


def ui_events(user: str, cookie: str, ip: Optional[str], ua: Optional[str], body: Any) -> int:
    items = body.get("events") if isinstance(body, dict) else None
    if not isinstance(items, list):
        return 0
    session = session_key(cookie)
    now = _now()
    n = 0
    for e in items:
        if not isinstance(e, dict) or e.get("type") not in _UI_EVENTS:
            continue
        client_at = None
        try:
            client_at = datetime.fromtimestamp(float(e.get("t")) / 1000, tz=timezone.utc)
        except (TypeError, ValueError, OverflowError, OSError):
            pass
        detail = {k: v for k, v in e.items() if k not in ("type", "t", "page", "label")}
        enqueue("ui", {"at": now, "client_at": client_at, "actor": user, "session": session, "ip": ip, "ua": ua,
                       "page": str(e.get("page") or "") or None, "event": e["type"],
                       "label": str(e.get("label") or "") or None,
                       "detail": json.dumps(mask(detail), ensure_ascii=False) if detail else None})
        n += 1
    return n


# ------------------------------------------------------------------ okuma (Yönetim → Denetim kaydı)

TYPES = ("ui", "request", "row", "action")


def _parse_dt(v: Optional[str]) -> Optional[datetime]:
    if not v:
        return None
    try:
        d = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _iso(v: Optional[datetime]) -> Optional[str]:
    if v is None:
        return None
    return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()


def _jl(v: Optional[str]) -> Any:
    if v is None:
        return None
    try:
        return json.loads(v)
    except ValueError:
        return v


def _selects(types: list[str], actor: Optional[str], since: Optional[datetime], until: Optional[datetime],
             q: Optional[str], reads: Any, tbl: Optional[str], module: Optional[str]) -> list[Any]:
    """`reads`: False = okuma istekleri yok, True = hepsi, "only" = yalnız okuma."""
    from semantic_bridge import admin as admin_mod

    A = admin_mod.AUDIT
    like = f"%{q.strip()}%" if q and q.strip() else None
    parts = []

    def common(T: sa.Table, stmt: Any, text_cols: list[Any]) -> Any:
        if actor:
            stmt = stmt.where(T.c.actor == actor)
        if since:
            stmt = stmt.where(T.c.at >= since)
        if until:
            stmt = stmt.where(T.c.at < until)
        if like:
            stmt = stmt.where(sa.or_(*[col.ilike(like) for col in text_cols]))
        return stmt

    null = sa.null()
    if "ui" in types and not tbl and not module:
        s = sa.select(sa.literal("ui").label("type"), UI.c.id, UI.c.at, UI.c.actor, sa.cast(null, sa.String).label("rid"),
                      UI.c.event.label("a"), UI.c.label.label("b"), UI.c.page.label("c"),
                      sa.cast(null, sa.Integer).label("n"), UI.c.ip)
        parts.append(common(UI, s, [UI.c.label, UI.c.page]))
    if "request" in types and not tbl:
        s = sa.select(sa.literal("request").label("type"), REQUESTS.c.id, REQUESTS.c.at, REQUESTS.c.actor, REQUESTS.c.rid,
                      REQUESTS.c.method.label("a"), REQUESTS.c.path.label("b"), REQUESTS.c.page.label("c"),
                      REQUESTS.c.status.label("n"), REQUESTS.c.ip)
        if reads == "only":
            s = s.where(REQUESTS.c.kind == "read")
        elif not reads:
            s = s.where(REQUESTS.c.kind != "read")
        if module:
            s = s.where(REQUESTS.c.module.ilike(f"%{module}%"))
        parts.append(common(REQUESTS, s, [REQUESTS.c.path, REQUESTS.c.body, REQUESTS.c.page, REQUESTS.c.query]))
    if "row" in types and not module:
        s = sa.select(sa.literal("row").label("type"), ROWS.c.id, ROWS.c.at, ROWS.c.actor, ROWS.c.rid,
                      ROWS.c.op.label("a"), ROWS.c.tbl.label("b"), ROWS.c.pk.label("c"),
                      sa.cast(null, sa.Integer).label("n"), sa.cast(null, sa.String).label("ip"))
        if tbl:
            s = s.where(ROWS.c.tbl == tbl)
        parts.append(common(ROWS, s, [ROWS.c.tbl, ROWS.c.pk, ROWS.c.old_row, ROWS.c.new_row]))
    if "action" in types and not tbl and not module:
        s = sa.select(sa.literal("action").label("type"), sa.cast(A.c.id, sa.BigInteger).label("id"), A.c.at, A.c.actor,
                      A.c.rid, A.c.action.label("a"), A.c.title.label("b"), A.c.kind.label("c"),
                      sa.cast(null, sa.Integer).label("n"), A.c.ip)
        parts.append(common(A, s, [A.c.title, A.c.object_id, A.c.detail]))
    return parts


def _cursor(v: Optional[str]) -> Optional[tuple[datetime, str, int]]:
    """Sayfa imleci «ISO an|tür|kimlik»: aynı anda yazılmış kayıtlar sayfa sınırında ne kaybolur ne iki kez gelir."""
    if not v:
        return None
    try:
        at, typ, i = v.rsplit("|", 2)
        d = _parse_dt(at)
        return (d, typ, int(i)) if d else None
    except ValueError:
        return None


def timeline(engine: sa.engine.Engine, *, types: Optional[list[str]] = None, actor: Optional[str] = None,
             since: Optional[str] = None, until: Optional[str] = None, q: Optional[str] = None, reads: Any = False,
             tbl: Optional[str] = None, module: Optional[str] = None, before: Optional[str] = None,
             limit: int = 100) -> dict[str, Any]:
    """Dört katman tek akışta, yeniden eskiye. `before` = önceki sayfanın `next` imleci. `limit` sayfa boyudur."""
    from semantic_bridge import admin as admin_mod

    ensure(engine)
    types = [t for t in (types or TYPES) if t in TYPES]
    limit = max(1, int(limit or 100))
    cur = _cursor(before)
    top = _parse_dt(until)
    parts = _selects(types, actor, _parse_dt(since), top, q, reads, tbl, module)
    if not parts:
        return {"items": [], "next": None}
    u = sa.union_all(*parts).subquery()
    stmt = sa.select(u)
    if cur:
        at, typ, i = cur
        stmt = stmt.where(sa.or_(u.c.at < at, sa.and_(u.c.at == at, sa.or_(u.c.type < typ, sa.and_(u.c.type == typ, u.c.id < i)))))
    stmt = stmt.order_by(u.c.at.desc(), u.c.type.desc(), u.c.id.desc()).limit(limit + 1)
    with engine.connect() as c:
        rows = c.execute(stmt).mappings().all()
    items = []
    for r in rows[:limit]:
        item = {"type": r["type"], "id": r["id"], "at": _iso(r["at"]), "actor": admin_mod.system_actor(r["actor"]) if r["actor"] else None,
                "rid": r["rid"], "ip": r["ip"]}
        if r["type"] == "ui":
            item.update(event=r["a"], label=r["b"], page=r["c"])
        elif r["type"] == "request":
            item.update(method=r["a"], path=r["b"], page=r["c"], status=r["n"])
        elif r["type"] == "row":
            item.update(op=r["a"], table=r["b"], pk=_jl(r["c"]))
        else:
            item.update(action=r["a"], title=r["b"], kind=r["c"], kindLabel=admin_mod.KIND_LABEL.get(r["c"], r["c"]))
        items.append(item)
    nxt = None
    if len(rows) > limit:
        last = rows[limit - 1]
        nxt = f"{_iso(last['at'])}|{last['type']}|{last['id']}"
    return {"items": items, "next": nxt}


def request_detail(engine: sa.engine.Engine, rid: str) -> Optional[dict[str, Any]]:
    """Bir isteğin bütün izi: istek (gövde dahil), değiştirdiği satırlar, yazdığı işlem kaydı, aynı oturumun
    o andaki ekran olayları."""
    from semantic_bridge import admin as admin_mod

    ensure(engine)
    A = admin_mod.AUDIT
    with engine.connect() as c:
        req = c.execute(sa.select(REQUESTS).where(REQUESTS.c.rid == rid)).mappings().first()
        rows = c.execute(sa.select(ROWS).where(ROWS.c.rid == rid).order_by(ROWS.c.id)).mappings().all()
        acts = c.execute(sa.select(A).where(A.c.rid == rid).order_by(A.c.id)).mappings().all()
        ui = []
        if req is not None and req["session"]:
            ui = c.execute(sa.select(UI).where(UI.c.session == req["session"],
                                               UI.c.at.between(req["at"] - timedelta(seconds=30), req["at"] + timedelta(seconds=5)))
                           .order_by(UI.c.at)).mappings().all()
    if req is None and not rows and not acts:
        return None
    return {
        "request": request_dict(req) if req is not None else None,
        "rows": [row_dict(r) for r in rows],
        "actions": [{"id": a["id"], "at": _iso(a["at"]), "actor": admin_mod.system_actor(a["actor"]), "action": a["action"],
                     "kind": a["kind"], "kindLabel": admin_mod.KIND_LABEL.get(a["kind"], a["kind"]),
                     "objectId": a["object_id"], "title": a["title"], "detail": _jl(a["detail"])} for a in acts],
        "ui": [ui_dict(u) for u in ui],
    }


def request_dict(r: Any) -> dict[str, Any]:
    from semantic_bridge import admin as admin_mod

    return {"id": r["id"], "at": _iso(r["at"]), "rid": r["rid"], "actor": admin_mod.system_actor(r["actor"]) if r["actor"] else None,
            "ip": r["ip"], "ua": r["ua"], "method": r["method"], "path": r["path"], "query": r["query"], "page": r["page"],
            "module": r["module"], "kind": r["kind"], "status": r["status"], "ms": r["ms"], "reqBytes": r["req_bytes"],
            "respBytes": r["resp_bytes"], "contentType": r["content_type"], "body": _jl(r["body"]), "files": _jl(r["files"]),
            "sealed": bool(r["seal"])}


def row_dict(r: Any) -> dict[str, Any]:
    return {"id": r["id"], "at": _iso(r["at"]), "rid": r["rid"], "actor": r["actor"], "table": r["tbl"], "op": r["op"],
            "pk": _jl(r["pk"]), "changed": _jl(r["changed"]), "old": _jl(r["old_row"]), "new": _jl(r["new_row"]),
            "sealed": bool(r["seal"])}


def ui_dict(u: Any) -> dict[str, Any]:
    return {"id": u["id"], "at": _iso(u["at"]), "clientAt": _iso(u["client_at"]), "actor": u["actor"], "ip": u["ip"],
            "ua": u["ua"], "page": u["page"], "event": u["event"], "label": u["label"], "detail": _jl(u["detail"]),
            "sealed": bool(u["seal"])}


def item_detail(engine: sa.engine.Engine, typ: str, item_id: int) -> Optional[dict[str, Any]]:
    from semantic_bridge import admin as admin_mod

    ensure(engine)
    T = {"ui": UI, "request": REQUESTS, "row": ROWS, "action": admin_mod.AUDIT}.get(typ)
    if T is None:
        return None
    with engine.connect() as c:
        r = c.execute(sa.select(T).where(T.c.id == item_id)).mappings().first()
    if r is None:
        return None
    if typ == "ui":
        return {"ui": ui_dict(r)}
    if typ == "row":
        return {"row": row_dict(r)}
    if typ == "request":
        return request_detail(engine, r["rid"])
    if r["rid"]:
        return request_detail(engine, r["rid"])
    return {"actions": [{"id": r["id"], "at": _iso(r["at"]), "actor": admin_mod.system_actor(r["actor"]), "action": r["action"],
                         "kind": r["kind"], "kindLabel": admin_mod.KIND_LABEL.get(r["kind"], r["kind"]),
                         "objectId": r["object_id"], "title": r["title"], "detail": _jl(r["detail"])}],
            "rows": [], "ui": [], "request": None}


def record_history(engine: sa.engine.Engine, tbl: str, pk: str) -> list[dict[str, Any]]:
    """Bir kaydın ilk eklenişinden son hâline kadar bütün değişiklikleri (eskiden yeniye)."""
    ensure(engine)
    with engine.connect() as c:
        rows = c.execute(sa.select(ROWS).where(ROWS.c.tbl == tbl, ROWS.c.pk == pk).order_by(ROWS.c.id)).mappings().all()
    return [row_dict(r) for r in rows]


def actors(engine: sa.engine.Engine) -> list[dict[str, Any]]:
    """Kayıtta adı geçen herkes, son görülme anıyla (kişi seçicisi)."""
    from semantic_bridge import admin as admin_mod

    ensure(engine)
    A = admin_mod.AUDIT
    parts = [sa.select(T.c.actor, sa.func.max(T.c.at).label("last"), sa.func.count().label("n"))
             .where(T.c.actor.isnot(None)).group_by(T.c.actor) for T in (UI, REQUESTS, A)]
    u = sa.union_all(*parts).subquery()
    stmt = sa.select(u.c.actor, sa.func.max(u.c.last).label("last"), sa.func.sum(u.c.n).label("n")) \
        .group_by(u.c.actor).order_by(sa.func.max(u.c.last).desc())
    with engine.connect() as c:
        rows = c.execute(stmt).all()
    merged: dict[str, dict[str, Any]] = {}
    for a, last, n in rows:
        name = admin_mod.system_actor(a)
        m = merged.setdefault(name, {"actor": name, "last": None, "count": 0})
        m["count"] += int(n or 0)
        if last and (m["last"] is None or _iso(last) > m["last"]):
            m["last"] = _iso(last)
    return sorted(merged.values(), key=lambda m: m["last"] or "", reverse=True)


def stats(engine: sa.engine.Engine) -> dict[str, Any]:
    from semantic_bridge import admin as admin_mod

    ensure(engine)
    out = {}
    with engine.connect() as c:
        for key, T in (("ui", UI), ("request", REQUESTS), ("row", ROWS), ("action", admin_mod.AUDIT)):
            n, lo = c.execute(sa.select(sa.func.count(), sa.func.min(T.c.at)).select_from(T)).one()
            out[key] = {"count": int(n or 0), "since": _iso(lo)}
        if engine.dialect.name == "postgresql":
            out["tablesWatched"] = int(c.exec_driver_sql(
                "SELECT count(*) FROM pg_trigger WHERE tgname = 'nb_audit_row'").scalar() or 0)
    d = spool_dir()
    out["spooled"] = sum(1 for f in d.glob("*.jsonl") for _ in open(f, encoding="utf-8")) if d.is_dir() else 0
    out["queued"] = _q.qsize()
    return out


def export_rows(engine: sa.engine.Engine, **filters: Any):  # noqa: ANN201
    """CSV için bütün sayfalar (tavan yok): zaman çizelgesi sayfa sayfa yürünür."""
    before = None
    while True:
        page = timeline(engine, before=before, limit=1000, **filters)
        yield from page["items"]
        if not page["next"]:
            return
        before = page["next"]
