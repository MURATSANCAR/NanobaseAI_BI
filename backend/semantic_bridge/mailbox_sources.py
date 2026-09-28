"""H4 Kurumsal e-posta: posta kutusu bağdaştırıcıları ve CRM gönderen tanıma (yalnız okuma).

**Kutu (kullanıcı kararı 2026-09-28): timas@timas.com.tr Google Workspace'tedir; birincil ve varsayılan bağdaştırıcı
Gmail API'dir.** Yetki yalnız iki kapsamdır:

- `https://www.googleapis.com/auth/gmail.readonly` — ileti ve konu zinciri okuma,
- `https://www.googleapis.com/auth/gmail.labels` — etiket tanımlarını okuma/oluşturma.

Gönderme kapsamı (`gmail.send`, `gmail.compose`) ve değiştirme kapsamı (`gmail.modify`) **istenmez**: portal Timaş
adına hiçbir ileti göndermez, kutudan hiçbir şey silmez, taşımaz. Not: `gmail.labels` etiket *tanımını* yönetir; bir
iletiye etiket *takmak* `gmail.modify` ister. Bu sürüm iletiye etiket takmaz — tür, sorumlu ve durum portalda tutulur,
kutu olduğu gibi kalır.

İki bağlantı yolu (Yönetim → Kurumsal e-posta):

1. **Hizmet hesabı + alan geneli yetki devri** (önerilen, `MAIL_GMAIL_AUTH=hizmet-hesabi`): Google Cloud'da bir hizmet
   hesabı açılır, JSON anahtarı `MAIL_GOOGLE_SERVICE_ACCOUNT_JSON`'a yapıştırılır; Workspace yöneticisi Yönetici
   Konsolu → Güvenlik → API denetimleri → Alan genelinde yetki devri'nde hesabın istemci kimliğine YALNIZ yukarıdaki iki
   kapsamı verir. Belirteç `sub = MAIL_ADDRESS` ile alınır; hizmet hesabı yalnız o kutuyu okur.
2. **OAuth** (`MAIL_GMAIL_AUTH=oauth`): kutunun kendi hesabıyla bir kez onay verilir, çıkan yenileme belirteci
   (`MAIL_OAUTH_REFRESH_TOKEN`) ve OAuth istemcisi (`MAIL_OAUTH_CLIENT_ID/SECRET`) girilir. Workspace yöneticisi alan
   geneli yetki devri vermek istemezse bu yol kullanılır.

JWT imzası SEO modülündeki servis hesabı deseniyle aynıdır (`seo_geo.connections._sign`: sunucudaki openssl, anahtar
yalnız imza süresince 0600 geçici dosyada); yeni bağımlılık yok.

**Artımlı okuma:** `messages.list` sorgusu `after:<epoch> -in:sent -in:drafts -in:chats`, çöp ve spam dahil. Epoch son
okunan iletinin tarihinden `MAIL_READ_OVERLAP_MIN` dakika geridir; aynı ileti ikinci kez gelirse (sağlayıcı kimliği
tekil) yazılmaz. Geçmiş kimliği (historyId) yerine sorgu kullanılır: geçmiş kimliği bir hafta sonra geçersizleşir ve
kesintide ileti kaçırılır; sorguda kaçırma olmaz. Sayfa tavanı yok: `nextPageToken` bitene kadar okunur.

**Yanıt tespiti:** kutudan gönderilen yanıt konu zincirinde `SENT` etiketiyle durur; ilk yanıtın zamanı zincirden
okunur (`threads.get`, yalnız başlık). Portal ile kutu iki ayrı gerçek olmaz.

Microsoft 365 (Graph) ve IMAP için yalnız arayüz vardır; bu kurulumda kullanılmaz.

**CRM** (`Timas_MSCRM`, .28) yalnız okunur: `ContactBase.EMailAddress1`, `AccountBase.EMailAddress1`,
`LeadBase.EMailAddress1` tam eşleşme (küçük harf, kırpılmış), etkin kayıt (`StateCode = 0`).
"""
from __future__ import annotations

import base64
import html
import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import getaddresses, parseaddr
from typing import Any, Callable, Iterable, Optional
from urllib.parse import quote

import httpx

log = logging.getLogger("semantic.mailbox.sources")

GMAIL_SCOPES = ("https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.labels")
GMAIL = "https://gmail.googleapis.com/gmail/v1/users"
TOKEN_URI = "https://oauth2.googleapis.com/token"
PROVIDERS = {"gmail": "Google Workspace (Gmail)", "graph": "Microsoft 365", "imap": "IMAP"}
AUTH_MODES = {"hizmet-hesabi": "Hizmet hesabı + alan geneli yetki devri", "oauth": "OAuth (kutunun kendi onayı)"}
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+'\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


class SourceError(RuntimeError):
    """Kullanıcıya olduğu gibi gösterilecek Türkçe hata."""


class NotConnected(SourceError):
    """Kutu bağlı değil (ayar eksik). Ekran «kutu bağlı değil» der; sahte ileti yoktur."""


@dataclass
class Attachment:
    name: str
    size: int
    mime: str
    ref: str = ""                        # sağlayıcının ek kimliği (anlık; saklanmaz)

    def public(self) -> dict[str, Any]:
        return {"name": self.name, "size": self.size, "mime": self.mime}


@dataclass
class MailItem:
    provider_id: str
    thread_id: str
    received_at: datetime
    from_addr: str
    from_name: str
    to: list[str]
    subject: str
    labels: list[str]
    attachments: list[Attachment] = field(default_factory=list)
    text: str = ""                       # gövde (düz metin); SAKLANMAZ, yalnız sınıflama ve ekran için bellekte


# ------------------------------------------------------------------------------------------------ yardımcılar


def norm_addr(addr: str) -> str:
    return (addr or "").strip().strip("<>").lower()


def valid_addr(addr: str) -> bool:
    return bool(EMAIL_RE.match(addr or ""))


def html_to_text(raw: str) -> str:
    s = re.sub(r"(?is)<(script|style|head)[^>]*>.*?</\1>", " ", raw or "")
    s = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</tr>", "\n", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n\n", s).strip()


def _b64d(data: str) -> bytes:
    data = data or ""
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _walk(part: dict[str, Any]) -> Iterable[dict[str, Any]]:
    yield part
    for p in part.get("parts") or []:
        yield from _walk(p)


def _header(payload: dict[str, Any], name: str) -> str:
    for h in payload.get("headers") or []:
        if str(h.get("name", "")).lower() == name.lower():
            return str(h.get("value") or "")
    return ""


def parse_gmail(msg: dict[str, Any]) -> MailItem:
    """Gmail `messages.get?format=full` cevabı → MailItem. Gövde düz metin tercih edilir, yoksa HTML sadeleştirilir."""
    payload = msg.get("payload") or {}
    name, addr = parseaddr(_header(payload, "From"))
    to = [norm_addr(a) for _, a in getaddresses([_header(payload, "To"), _header(payload, "Cc")]) if a]
    plain, htm, atts = [], [], []
    for p in _walk(payload):
        mime = str(p.get("mimeType") or "").lower()
        body = p.get("body") or {}
        fname = p.get("filename") or ""
        if fname:
            atts.append(Attachment(name=fname[:300], size=int(body.get("size") or 0), mime=mime[:120],
                                   ref=str(body.get("attachmentId") or "")))
            continue
        if not body.get("data"):
            continue
        try:
            txt = _b64d(body["data"]).decode("utf-8", errors="replace")
        except (ValueError, TypeError):
            continue
        if mime == "text/plain":
            plain.append(txt)
        elif mime == "text/html":
            htm.append(txt)
    text = "\n".join(plain).strip() or html_to_text("\n".join(htm))
    try:
        received = datetime.fromtimestamp(int(msg.get("internalDate") or 0) / 1000, timezone.utc)
    except (TypeError, ValueError):
        received = datetime.now(timezone.utc)
    return MailItem(provider_id=str(msg.get("id")), thread_id=str(msg.get("threadId") or msg.get("id")),
                    received_at=received, from_addr=norm_addr(addr), from_name=(name or "").strip()[:200],
                    to=to, subject=_header(payload, "Subject").strip()[:500], labels=list(msg.get("labelIds") or []),
                    attachments=atts, text=text)


# ------------------------------------------------------------------------------------------------ arayüz


class MailSource:
    """Posta kutusu bağdaştırıcısı: yalnız okuma. Gönderme, silme, taşıma yöntemi YOKTUR (bilinçli)."""

    kind = "?"

    def mailbox(self) -> str:
        raise NotImplementedError

    def test(self) -> tuple[bool, str]:
        raise NotImplementedError

    def list_since(self, since: datetime) -> list[str]:
        """`since`'ten sonra gelen (gönderilmemiş, taslak olmayan) iletilerin sağlayıcı kimlikleri; bütün sayfalar."""
        raise NotImplementedError

    def fetch(self, provider_id: str) -> MailItem:
        """Tek ileti: başlık + gövde + ek adları. Gövde bellekte kalır, yazılmaz."""
        raise NotImplementedError

    def first_reply(self, thread_id: str, after: datetime) -> Optional[datetime]:
        """Konu zincirinde kutudan `after`'dan sonra gönderilen ilk iletinin zamanı; yoksa None."""
        raise NotImplementedError

    def attachment(self, provider_id: str, att: Attachment) -> bytes:
        """Ekin içeriği, anlık (yazar giriş sürecine aktarım için). Portal eki saklamaz."""
        raise NotImplementedError

    def web_link(self, provider_id: str, thread_id: str) -> Optional[str]:
        """«Kutuda aç» bağlantısı (yanıt kutunun kendi arayüzünden gönderilir)."""
        return None


class GmailSource(MailSource):
    kind = "gmail"

    def __init__(self, conf: Callable[[str, str], str]):
        self._conf = conf
        self._lock = threading.Lock()
        self._token: Optional[str] = None
        self._exp = 0.0
        self._key = ""

    # -------------------------------------------------------------- kimlik

    def mailbox(self) -> str:
        return norm_addr(self._conf("MAIL_ADDRESS", ""))

    def _mode(self) -> str:
        m = (self._conf("MAIL_GMAIL_AUTH", "hizmet-hesabi") or "hizmet-hesabi").strip().lower()
        return m if m in AUTH_MODES else "hizmet-hesabi"

    def _service_account(self) -> dict[str, Any]:
        # Kutunun kendi anahtarı yoksa SEO'nun Google servis hesabı kullanılır: tek anahtar, iki iş (2026-09-28). Yetki
        # yine Workspace'in alan geneli devriyle sınırlı; devir verilmemişse Google belirteci reddeder, ekranda yazar.
        raw = (self._conf("MAIL_GOOGLE_SERVICE_ACCOUNT_JSON", "") or self._conf("GOOGLE_SERVICE_ACCOUNT_JSON", "") or "").strip()
        if not raw:
            raise NotConnected("Hizmet hesabı anahtarı girilmemiş (Yönetim → Kurumsal e-posta ya da SEO & GEO → Google servis hesabı).")
        try:
            info = json.loads(raw)
        except ValueError:
            raise NotConnected("Hizmet hesabı anahtarı JSON olarak okunamadı; dosyanın içeriğini olduğu gibi yapıştırın.") from None
        if info.get("type") != "service_account" or not info.get("private_key") or not info.get("client_email"):
            raise NotConnected("Bu bir hizmet hesabı anahtarı değil (type=service_account, private_key, client_email gerekli).")
        return info

    def identity(self) -> Optional[str]:
        """Ekranda gösterilecek kimlik: hizmet hesabının adresi ya da «OAuth»."""
        try:
            return self._service_account()["client_email"] if self._mode() == "hizmet-hesabi" else "OAuth"
        except NotConnected:
            return None

    def _token_sa(self) -> tuple[str, float]:
        from semantic_bridge.seo_geo.connections import ConnectionError_, _b64, _sign

        info = self._service_account()
        now = int(time.time())
        head = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
        claims = _b64(json.dumps({"iss": info["client_email"], "sub": self.mailbox(), "scope": " ".join(GMAIL_SCOPES),
                                  "aud": info.get("token_uri") or TOKEN_URI, "iat": now, "exp": now + 3600}).encode())
        unsigned = f"{head}.{claims}".encode()
        try:
            jwt = unsigned.decode() + "." + _b64(_sign(info["private_key"], unsigned))
        except ConnectionError_ as e:
            raise SourceError(str(e)) from None
        with httpx.Client(timeout=30) as c:
            resp = c.post(info.get("token_uri") or TOKEN_URI,
                          data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": jwt})
        if resp.status_code != 200:
            text = resp.text[:300]
            if "unauthorized_client" in text:
                raise SourceError("Google belirteç vermedi: alan geneli yetki devri bu hizmet hesabına verilmemiş ya da "
                                  "kapsamlar eksik (gmail.readonly ve gmail.labels). Workspace yöneticisine iletin.")
            raise SourceError(f"Google belirteci alınamadı: {text}")
        body = resp.json()
        return body["access_token"], time.time() + int(body.get("expires_in", 3600))

    def _token_oauth(self) -> tuple[str, float]:
        cid = (self._conf("MAIL_OAUTH_CLIENT_ID", "") or "").strip()
        secret = (self._conf("MAIL_OAUTH_CLIENT_SECRET", "") or "").strip()
        refresh = (self._conf("MAIL_OAUTH_REFRESH_TOKEN", "") or "").strip()
        if not (cid and secret and refresh):
            raise NotConnected("OAuth istemcisi ya da yenileme belirteci girilmemiş (Yönetim → Kurumsal e-posta).")
        with httpx.Client(timeout=30) as c:
            resp = c.post(TOKEN_URI, data={"grant_type": "refresh_token", "refresh_token": refresh,
                                           "client_id": cid, "client_secret": secret})
        if resp.status_code != 200:
            raise SourceError(f"Google belirteci yenilenemedi (onay geri alınmış olabilir): {resp.text[:200]}")
        body = resp.json()
        granted = set(str(body.get("scope") or "").split())
        extra = granted - set(GMAIL_SCOPES) - {"openid", "email", "profile",
                                                "https://www.googleapis.com/auth/userinfo.email"}
        if extra:
            # Fazla yetki (ör. gönderme) verilmişse kullanılmaz; yine de yöneticinin bilmesi gerekir.
            log.warning("posta: OAuth onayı gereğinden geniş kapsam taşıyor: %s", " ".join(sorted(extra)))
        return body["access_token"], time.time() + int(body.get("expires_in", 3600))

    def token(self) -> str:
        if not self.mailbox():
            raise NotConnected("Kutu adresi girilmemiş (Yönetim → Kurumsal e-posta).")
        key = f"{self._mode()}|{self.mailbox()}|{self.identity()}"
        with self._lock:
            if self._token and self._key == key and self._exp - 60 > time.time():
                return self._token
            tok, exp = self._token_sa() if self._mode() == "hizmet-hesabi" else self._token_oauth()
            self._token, self._exp, self._key = tok, exp, key
            return tok

    def _get(self, path: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        url = f"{GMAIL}/{quote(self.mailbox(), safe='@')}/{path}"
        for attempt in range(4):
            with httpx.Client(timeout=60) as c:
                resp = c.get(url, params=params, headers={"Authorization": f"Bearer {self.token()}"})
            if resp.status_code in (429, 500, 502, 503) and attempt < 3:
                time.sleep(2 ** attempt)
                continue
            break
        if resp.status_code == 401:
            with self._lock:
                self._token = None
            raise SourceError("Google oturumu reddetti; bağlantı ayarını denetleyin.")
        if resp.status_code == 403:
            raise SourceError("Google erişimi reddetti: kapsam (gmail.readonly) verilmemiş ya da kutu adresi hizmet "
                              "hesabının yetkisi dışında.")
        if resp.status_code == 404:
            raise SourceError("İleti kutuda bulunamadı (silinmiş olabilir).")
        if resp.status_code >= 400:
            try:
                msg = resp.json().get("error", {}).get("message")
            except ValueError:
                msg = None
            raise SourceError(f"Google {resp.status_code}: {msg or resp.text[:200]}")
        return resp.json()

    # -------------------------------------------------------------- okuma

    def test(self) -> tuple[bool, str]:
        p = self._get("profile")
        labels = self._get("labels")
        n = int(p.get("messagesTotal") or 0)
        return True, (f"{p.get('emailAddress')} okundu: {n:,} ileti, {len(labels.get('labels') or [])} etiket"
                      .replace(",", ".") + f" · {AUTH_MODES[self._mode()]}.")

    def list_since(self, since: datetime) -> list[str]:
        q = f"after:{int(since.timestamp())} -in:sent -in:drafts -in:chats"
        out: list[str] = []
        token: Optional[str] = None
        while True:
            params: dict[str, Any] = {"q": q, "includeSpamTrash": "true", "maxResults": 500}
            if token:
                params["pageToken"] = token
            page = self._get("messages", params)
            out.extend(str(m["id"]) for m in page.get("messages") or [])
            token = page.get("nextPageToken")
            if not token:
                return out

    def fetch(self, provider_id: str) -> MailItem:
        return parse_gmail(self._get(f"messages/{quote(provider_id, safe='')}", {"format": "full"}))

    def first_reply(self, thread_id: str, after: datetime) -> Optional[datetime]:
        t = self._get(f"threads/{quote(thread_id, safe='')}", {"format": "metadata", "metadataHeaders": "Date"})
        cutoff = after.timestamp() * 1000
        sent = [int(m.get("internalDate") or 0) for m in t.get("messages") or []
                if "SENT" in (m.get("labelIds") or []) and int(m.get("internalDate") or 0) > cutoff]
        return datetime.fromtimestamp(min(sent) / 1000, timezone.utc) if sent else None

    def attachment(self, provider_id: str, att: Attachment) -> bytes:
        if not att.ref:
            raise SourceError(f"«{att.name}» ekinin kimliği okunamadı.")
        d = self._get(f"messages/{quote(provider_id, safe='')}/attachments/{quote(att.ref, safe='')}")
        return _b64d(str(d.get("data") or ""))

    def web_link(self, provider_id: str, thread_id: str) -> Optional[str]:
        box = self.mailbox()
        return f"https://mail.google.com/mail/u/{quote(box, safe='@')}/#all/{quote(thread_id or provider_id, safe='')}" if box else None


class _NotBuilt(MailSource):
    """Microsoft 365 / IMAP: yalnız arayüz. Kutu Gmail'de olduğu için bu kurulumda kurulmadı."""

    def __init__(self, kind: str):
        self.kind = kind

    def mailbox(self) -> str:
        return ""

    def _no(self) -> Any:
        raise NotConnected(f"{PROVIDERS.get(self.kind, self.kind)} bağdaştırıcısı bu sürümde kurulmadı; kutu Google "
                           "Workspace'te (Gmail).")

    def test(self) -> tuple[bool, str]:
        return self._no()

    def list_since(self, since: datetime) -> list[str]:
        return self._no()

    def fetch(self, provider_id: str) -> MailItem:
        return self._no()

    def first_reply(self, thread_id: str, after: datetime) -> Optional[datetime]:
        return self._no()


_GMAIL: dict[str, GmailSource] = {}


def source(conf: Callable[[str, str], str]) -> MailSource:
    """Ayardaki sağlayıcı. Varsayılan Gmail. Belirteç önbelleği süreç boyunca tek nesnede tutulur."""
    kind = (conf("MAIL_PROVIDER", "gmail") or "gmail").strip().lower()
    if kind in ("", "gmail", "google"):
        if "g" not in _GMAIL:
            _GMAIL["g"] = GmailSource(conf)
        return _GMAIL["g"]
    return _NotBuilt(kind)


def connection_state(conf: Callable[[str, str], str]) -> dict[str, Any]:
    """Ayarın tamlığı (ağa çıkmadan). `connected=False` ise ekran «kutu bağlı değil» der."""
    src = source(conf)
    out: dict[str, Any] = {"provider": src.kind, "providerLabel": PROVIDERS.get(src.kind, src.kind),
                           "mailbox": src.mailbox() or None, "connected": False, "reason": None, "identity": None,
                           "scopes": list(GMAIL_SCOPES) if src.kind == "gmail" else []}
    if isinstance(src, GmailSource):
        out["authMode"] = src._mode()
        out["authLabel"] = AUTH_MODES[src._mode()]
        if not src.mailbox():
            out["reason"] = "Kutu adresi girilmemiş."
            return out
        try:
            if src._mode() == "hizmet-hesabi":
                out["identity"] = src._service_account()["client_email"]
            elif not all((conf(k, "") or "").strip() for k in ("MAIL_OAUTH_CLIENT_ID", "MAIL_OAUTH_CLIENT_SECRET",
                                                                 "MAIL_OAUTH_REFRESH_TOKEN")):
                raise NotConnected("OAuth istemcisi ya da yenileme belirteci girilmemiş.")
            else:
                out["identity"] = "OAuth"
        except NotConnected as e:
            out["reason"] = str(e)
            return out
        out["connected"] = True
        return out
    out["reason"] = f"{PROVIDERS.get(src.kind, src.kind)} bağdaştırıcısı bu sürümde kurulmadı."
    return out


# ------------------------------------------------------------------------------------------------ CRM


def _sql_str(v: str) -> str:
    return "N'" + v.replace("'", "''") + "'"


def recognize_sql(prefix: str, addrs: list[str]) -> str:
    """Gönderen tanıma: etkin kişi / firma / aday kaydı, tam eşleşme. Kişinin olası yazar olduğu proje sayısı da okunur
    (`new_projeBase.new_olasyazaryazar`). Adresler önceden `valid_addr` ile süzülür."""
    inlist = ", ".join(_sql_str(a) for a in addrs)
    return (
        "SELECT 'kisi' AS tur, LOWER(LTRIM(RTRIM(c.EMailAddress1))) AS adres, CAST(c.ContactId AS nvarchar(40)) AS id, "
        "c.FullName AS ad, (SELECT COUNT(*) FROM " + prefix + "new_projeBase p WHERE p.new_olasyazaryazar = c.ContactId) AS proje "
        f"FROM {prefix}ContactBase c WHERE c.StateCode = 0 AND LOWER(LTRIM(RTRIM(c.EMailAddress1))) IN ({inlist}) "
        "UNION ALL "
        "SELECT 'firma', LOWER(LTRIM(RTRIM(a.EMailAddress1))), CAST(a.AccountId AS nvarchar(40)), a.Name, 0 "
        f"FROM {prefix}AccountBase a WHERE a.StateCode = 0 AND LOWER(LTRIM(RTRIM(a.EMailAddress1))) IN ({inlist}) "
        "UNION ALL "
        "SELECT 'aday', LOWER(LTRIM(RTRIM(l.EMailAddress1))), CAST(l.LeadId AS nvarchar(40)), l.FullName, 0 "
        f"FROM {prefix}LeadBase l WHERE l.StateCode = 0 AND LOWER(LTRIM(RTRIM(l.EMailAddress1))) IN ({inlist})"
    )


def recognize(run: Callable[[str], list[dict[str, Any]]], prefix: str, addrs: Iterable[str]) -> dict[str, dict[str, Any]]:
    """adres → {kisi: {id, ad, proje}, firma: {...}, aday: {...}}. Birden çok eşleşmede ilk kayıt (id sırası) alınır ve
    `coklu` işaretlenir; hangisinin doğru olduğu insan kararıdır. 500'lük parçalarla, hepsi okunur."""
    clean = sorted({norm_addr(a) for a in addrs if valid_addr(norm_addr(a))})
    out: dict[str, dict[str, Any]] = {}
    for i in range(0, len(clean), 500):
        chunk = clean[i:i + 500]
        for r in sorted(run(recognize_sql(prefix, chunk)), key=lambda x: str(x.get("id") or "")):
            addr, kind = str(r.get("adres") or ""), str(r.get("tur") or "")
            if not addr or kind not in ("kisi", "firma", "aday"):
                continue
            slot = out.setdefault(addr, {})
            if kind in slot:
                slot[kind]["coklu"] = True
                continue
            slot[kind] = {"id": str(r.get("id") or "").strip("{}").lower(), "ad": (str(r.get("ad") or "").strip() or None),
                          "proje": int(r.get("proje") or 0)}
    return out
