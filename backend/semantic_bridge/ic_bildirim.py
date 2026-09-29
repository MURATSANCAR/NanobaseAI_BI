"""İç bildirim e-postası şablonu: Bilgi İşlem'e giden sistem, güvenlik ve liste e-postalarının ortak biçimi.

Her bildirim bir `Notice`'tır: durum (rozet rengi), konu, tek cümlelik özet, «Ne oldu», «Etkisi», «Ne yapmalı»,
gerekirse kısa ayrıntı tablosu ve portal bağlantısı. Aynı içerik iki biçimde gider (`multipart/alternative`):

- HTML: tablo tabanlı, satır içi stil (e-posta istemcileri harici CSS okumaz), en çok 640 px, telefonda tek sütun.
- Düz metin: HTML göstermeyen istemci ve arama için aynı bölümler.

Konu satırı önce durumu söyler: «[Kesinti] Logo bağlantısı 09:42'den beri yanıt vermiyor», «[Düzeldi] …»,
«[Haftalık] Sistem sağlığı · 22–28 Eylül». Metne giren her parça `plain()` süzgecinden geçer: teknoloji ve ürün adı
(bellek no-tech-names-on-screens) işlev adına çevrilir, hata sınıfı adları atılır. Parola ve anahtar hiçbir bildirime
konmaz; bildirimi kuran modül yalnız işin gerektirdiği alanı verir.

Gönderim `send()`: SMTP ayarı Yönetim → E-posta'dan (`alerts.smtp_settings`); dönen durum modüllerin var olan
kodlarıyla aynıdır: sent | no_recipient | no_smtp | failed.
"""

from __future__ import annotations

import html
import logging
import re
import smtplib
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any, Iterable, Optional, Sequence

log = logging.getLogger("semantic_bridge.ic_bildirim")

LOCAL = timezone(timedelta(hours=3))
FOOTER = "Bu e-posta TİMAŞ Zeki AI tarafından otomatik gönderildi."

#: Durum → rozet. Kırmızı: kesinti ve güvenlik; yeşil: düzelme; sarı: dikkat (veri eski, iş hatası); mavi: bilgi.
TONES: dict[str, dict[str, str]] = {
    "kesinti": {"tag": "Kesinti", "fg": "#B42318", "bg": "#FEF3F2", "line": "#FECDCA", "bar": "#D92D20"},
    "guvenlik": {"tag": "Güvenlik", "fg": "#B42318", "bg": "#FEF3F2", "line": "#FECDCA", "bar": "#D92D20"},
    "duzeldi": {"tag": "Düzeldi", "fg": "#067647", "bg": "#ECFDF3", "line": "#ABEFC6", "bar": "#17B26A"},
    "uyari": {"tag": "Uyarı", "fg": "#B54708", "bg": "#FFFAEB", "line": "#FEDF89", "bar": "#F79009"},
    "bilgi": {"tag": "Bilgi", "fg": "#175CD3", "bg": "#EFF8FF", "line": "#B2DDFF", "bar": "#2E90FA"},
}

#: Ekrana ve e-postaya giden metinde geçmeyecek teknoloji/ürün adları → sade karşılığı. `it_ops.screen_text` de bunu
#: kullanır; iç günlükte ham metin kalır.
TECH: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bsystemd\b|\bsystemctl\b|\bjournalctl\b", re.I), "servis yöneticisi"),
    (re.compile(r"\bdocker\b|\bcontainerd?\b|\bkubernetes\b|\bk8s\b", re.I), "kapsayıcı"),
    (re.compile(r"\bnginx\b|\bapache2?\b|\bcaddy\b", re.I), "web sunucusu"),
    (re.compile(r"\buvicorn\b|\bgunicorn\b|\bfastapi\b|\bstarlette\b", re.I), "portal sunucusu"),
    (re.compile(r"\bv?llm\b|\bvllm\b|\bqwen[\w.-]*|\bopenai\b|\bollama\b|\bllama[\w.-]*", re.I), "Zeki AI modeli"),
    (re.compile(r"\btimesfm[\w.-]*", re.I), "Zeki AI tahmin modeli"),
    (re.compile(r"\breal-?esrgan\b|\btypst\b|\bghostscript\b", re.I), "belge ve görsel üretici"),
    (re.compile(r"\btemporal\b", re.I), "iş sırası"),
    (re.compile(r"\bopenvpn\b|\bsocat\b|\bwireguard\b", re.I), "şirket ağı bağlantısı"),
    (re.compile(r"\bpy?odbc\b|\bfreetds\b|\bpymssql\b|\bsqlalchemy\b|\bpsycopg2?\b|\basyncpg\b", re.I), "veritabanı sürücüsü"),
    (re.compile(r"\bpostgre(?:s|sql)?\b|\bsqlite3?\b|\bmssql\b|\bsql server\b|\bredis\b|\bqdrant\b", re.I), "veritabanı"),
    (re.compile(r"\bldap3?\b", re.I), "dizin"),
    # Sunucu adı («smtp.gmail.com») bozulmasın: noktayla devam eden ad dokunulmaz.
    (re.compile(r"\bsmtplib\b|\bsmtp\w*\b(?![.\w])", re.I), "posta sunucusu"),
    (re.compile(r"\bgmail\b(?![.\w])|\bgoogle workspace\b", re.I), "kurumsal e-posta"),
    (re.compile(r"\bpython\d?(?:\.\d+)*\b", re.I), "uygulama"),
]
#: «OperationalError: …», «ConnectionRefusedError …» gibi hata sınıfı adları okura bir şey söylemez.
_EXC = re.compile(r"\b(?:[A-Z][A-Za-z]*\.)*[A-Z][A-Za-z]*(?:Error|Exception|Timeout)\b:?\s*")

_MONTHS = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
_DAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
_ONES = ["sıfır", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"]
_TENS = ["", "on", "yirmi", "otuz", "kırk", "elli"]


# ------------------------------------------------------------------ metin


def tech_words(text: str) -> list[str]:
    """Metinde kalan teknoloji/ürün adları (testler ve kabul betiği denetler)."""
    return sorted({m.group(0) for rx, _ in TECH for m in rx.finditer(str(text or ""))})


def plain(s: Any, limit: Optional[int] = None) -> str:
    """Bildirime giden her parça: teknoloji adı sade karşılığıyla, hata sınıfı adı atılmış, boşluk tek."""
    t = " ".join(str(s if s is not None else "").split())
    t = _EXC.sub("", t)
    for rx, rep in TECH:
        t = rx.sub(rep, t)
    t = t.strip(" :;-")
    if limit and len(t) > limit:
        t = t[: limit - 1].rstrip() + "…"
    return t


def _last_vowel(word: str) -> str:
    for ch in reversed(word.lower()):
        if ch in "aıoueiöü":
            return ch
    return "e"


def suffix(word: str, kind: str = "den") -> str:
    """Türkçe ayrılma («-den») ya da bulunma («-de») eki, kesme işaretsiz: ünlü uyumu ve sert ünsüz benzeşmesi.
    «Ağustos» → «tan», «Eylül» → «den», «kırk» → «tan»."""
    w = word.strip().lower()
    back = _last_vowel(w) in "aıou"
    hard = bool(w) and w[-1] in "çfhkpsşt"
    head = "t" if hard else "d"
    if kind == "den":
        return head + ("an" if back else "en")
    return head + ("a" if back else "e")


def _spoken_last(n: int) -> str:
    """Sayının okunuşundaki son kelime (0–59): ekin uyumu buna göre."""
    if n == 0:
        return _ONES[0]
    return _ONES[n % 10] if n % 10 else _TENS[n // 10]


def local(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(LOCAL)


def hm(dt: Optional[datetime]) -> str:
    d = local(dt)
    return d.strftime("%H:%M") if d else "—"


def hm_suffix(dt: Optional[datetime], kind: str = "den") -> str:
    """«09:42'den», «10:40'tan», «12:00'de»."""
    d = local(dt)
    if not d:
        return "—"
    word = _spoken_last(d.minute or d.hour)
    return f"{d:%H:%M}'{suffix(word, kind)}"


def day_month(dt: Optional[datetime]) -> str:
    d = local(dt)
    return f"{d.day} {_MONTHS[d.month - 1]}" if d else "—"


def long_dt(dt: Optional[datetime]) -> str:
    """«29 Eylül 2026 Salı, 09:42»."""
    d = local(dt)
    return f"{d.day} {_MONTHS[d.month - 1]} {d.year} {_DAYS[d.weekday()]}, {d:%H:%M}" if d else "—"


def long_date(dt: Optional[datetime]) -> str:
    """«17 Ağustos 2026»."""
    d = local(dt)
    return f"{d.day} {_MONTHS[d.month - 1]} {d.year}" if d else "—"


def short_dt(dt: Optional[datetime]) -> str:
    """«29 Eylül 09:42» (bugün de olsa tarih yazılır: e-posta geç okunabilir)."""
    d = local(dt)
    return f"{d.day} {_MONTHS[d.month - 1]} {d:%H:%M}" if d else "—"


def day_range(a: datetime, b: datetime) -> str:
    """«22–28 Eylül», ay değişirse «29 Eylül – 5 Ekim», yıl değişirse yıllarıyla."""
    x, y = local(a), local(b)
    if x.year != y.year:
        return f"{x.day} {_MONTHS[x.month - 1]} {x.year} – {y.day} {_MONTHS[y.month - 1]} {y.year}"
    if x.month != y.month:
        return f"{x.day} {_MONTHS[x.month - 1]} – {y.day} {_MONTHS[y.month - 1]}"
    if x.day == y.day:
        return f"{x.day} {_MONTHS[x.month - 1]}"
    return f"{x.day}–{y.day} {_MONTHS[x.month - 1]}"


def minutes_text(m: Optional[int]) -> str:
    if m is None:
        return "—"
    m = max(0, int(m))
    if m < 60:
        return f"{m} dk"
    h, mm = divmod(m, 60)
    if h < 48:
        return f"{h} sa {mm} dk" if mm else f"{h} sa"
    d, hh = divmod(h, 24)
    return f"{d} gün {hh} sa" if hh else f"{d} gün"


def tr_upper(s: str) -> str:
    return s.replace("i", "İ").replace("ı", "I").upper()


def portal_link(base: str, path: str = "") -> str:
    """`ALERT_LINK` uyarılar sayfasını da gösterebilir («…/timas/uyarilar»); ekran adresi kökten kurulur."""
    root = (base or "").strip().split("/uyarilar")[0].rstrip("/")
    if not root:
        return ""
    return f"{root}/{path.lstrip('/')}" if path else root


# ------------------------------------------------------------------ bildirim


@dataclass
class Table:
    columns: list[str]
    rows: list[list[Any]]
    title: str = ""
    #: Sayı kolonları sağa yaslanır (kolon sırası).
    numeric: tuple[int, ...] = ()


@dataclass
class Notice:
    tone: str                      # kesinti | guvenlik | duzeldi | uyari | bilgi
    subject: str                   # «[Kesinti] …» hazır konu (bkz. `subject()`)
    headline: str                  # üstteki tek cümle
    what: list[str] = field(default_factory=list)     # Ne oldu
    impact: list[str] = field(default_factory=list)   # Etkisi
    actions: list[str] = field(default_factory=list)  # Ne yapmalı (sıralı adım)
    tables: list[Table] = field(default_factory=list)
    link: str = ""
    link_label: str = "Portalda aç"
    at: Optional[datetime] = None
    #: Neden bu adrese geldi (ayar adı), altta küçük yazı.
    why: str = ""
    tag: str = ""                  # rozet yazısı; boşsa durumun adı
    #: «Ne yapmalı»dan sonra, alıcının yapacağı iş olmayan bilgi (ör. uygulama ekibinin ilgilendiği hatalar).
    info: list[str] = field(default_factory=list)
    info_title: str = "Bilgi için"

    @property
    def badge(self) -> str:
        return self.tag or TONES.get(self.tone, TONES["bilgi"])["tag"]


def subject(tag: str, text: str) -> str:
    """«[Kesinti] Logo bağlantısı 09:42'den beri yanıt vermiyor». Konu 200 karakteri geçmez."""
    s = f"[{tag}] {plain(text)}"
    return s if len(s) <= 200 else s[:199].rstrip() + "…"


def split_steps(text: str) -> list[str]:
    """Paragraf hâlindeki tarifi cümle cümle adıma böler (büyük harf ya da «» ile başlayan cümle)."""
    parts = re.split(r"(?<=[.!?])\s+(?=[A-ZÇĞİÖŞÜ«])", " ".join(str(text or "").split()))
    return [p for p in (x.strip() for x in parts) if p]


# ------------------------------------------------------------------ düz metin


def render_text(n: Notice) -> str:
    out = [n.subject, "", plain(n.headline), ""]

    def section(title: str, items: Sequence[str], numbered: bool = False) -> None:
        items = [plain(x) for x in items if plain(x)]
        if not items:
            return
        out.append(title)
        for i, x in enumerate(items, 1):
            out.append(f"{i}. {x}" if numbered else (x if len(items) == 1 else f"- {x}"))
        out.append("")

    section("NE OLDU", n.what)
    section("ETKİSİ", n.impact)
    section("NE YAPMALI", n.actions, numbered=True)
    section(tr_upper(n.info_title), n.info)
    for t in n.tables:
        if not t.rows:
            continue
        out.append(tr_upper(plain(t.title) or "Ayrıntı"))
        if len(t.columns) == 2:
            for r in t.rows:
                out.append(f"{plain(r[0])}: {plain(r[1])}")
        else:
            out.append(" · ".join(plain(c) for c in t.columns))
            for r in t.rows:
                out.append("- " + " · ".join(plain(c) for c in r))
        out.append("")
    if n.link:
        out += [f"{n.link_label}: {n.link}", ""]
    out.append("--")
    out.append(FOOTER + (f" Gönderim: {long_dt(n.at)}." if n.at else ""))
    if n.why:
        out.append(plain(n.why))
    return "\n".join(out).rstrip() + "\n"


# ------------------------------------------------------------------ HTML

_FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
_INK = "#101828"
_BODY = "#344054"
_MUTED = "#667085"
_RULE = "#EAECF0"


def _e(s: Any) -> str:
    return html.escape(plain(s), quote=True)


def _section(title: str, inner: str) -> str:
    return (f'<tr><td class="px" style="padding:20px 32px 0 32px;">'
            f'<p style="margin:0 0 6px 0;font-family:{_FONT};font-size:13px;line-height:18px;font-weight:600;'
            f'color:{_MUTED};">{html.escape(title)}</p>{inner}</td></tr>')


def _paras(items: Iterable[str]) -> str:
    items = [x for x in items if plain(x)]
    if len(items) == 1:
        return (f'<p style="margin:0;font-family:{_FONT};font-size:15px;line-height:23px;color:{_BODY};">'
                f'{_e(items[0])}</p>')
    rows = "".join(
        f'<tr><td valign="top" style="width:16px;padding:0 0 6px 0;font-family:{_FONT};font-size:15px;line-height:23px;'
        f'color:{_MUTED};">•</td><td style="padding:0 0 6px 0;font-family:{_FONT};font-size:15px;line-height:23px;'
        f'color:{_BODY};">{_e(x)}</td></tr>' for x in items)
    return f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">{rows}</table>'


def _steps(items: Iterable[str], tone: dict[str, str]) -> str:
    items = [x for x in items if plain(x)]
    rows = "".join(
        f'<tr><td valign="top" style="width:30px;padding:0 0 10px 0;">'
        f'<span style="display:inline-block;width:22px;height:22px;border-radius:11px;background:{tone["bg"]};'
        f'border:1px solid {tone["line"]};color:{tone["fg"]};font-family:{_FONT};font-size:12px;line-height:22px;'
        f'font-weight:600;text-align:center;">{i}</span></td>'
        f'<td style="padding:1px 0 10px 0;font-family:{_FONT};font-size:15px;line-height:23px;color:{_BODY};">{_e(x)}</td></tr>'
        for i, x in enumerate(items, 1))
    return f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">{rows}</table>'


def _table(t: Table) -> str:
    if not t.rows:
        return ""
    cell = f"font-family:{_FONT};font-size:14px;line-height:20px;color:{_BODY};padding:9px 12px;"
    head = f"font-family:{_FONT};font-size:12px;line-height:16px;color:{_MUTED};font-weight:600;padding:8px 12px;background:#F9FAFB;"
    two = len(t.columns) == 2 and not t.numeric
    if two:
        # İki kolonlu tablo «alan: değer» listesidir; başlık satırı gerekmez, alan adı soluk.
        body = "".join(
            f'<tr><td valign="top" style="{cell}color:{_MUTED};width:38%;border-top:{"0" if i == 0 else "1px solid " + _RULE};">'
            f'{_e(r[0])}</td><td valign="top" style="{cell}color:{_INK};border-top:{"0" if i == 0 else "1px solid " + _RULE};'
            f'word-break:break-word;">{_e(r[1])}</td></tr>' for i, r in enumerate(t.rows))
        return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
                f'style="border:1px solid {_RULE};border-radius:8px;border-collapse:separate;">{body}</table>')
    align = lambda j: "right" if j in t.numeric else "left"  # noqa: E731
    hdr = "".join(f'<th align="{align(j)}" style="{head}text-align:{align(j)};">{_e(c)}</th>' for j, c in enumerate(t.columns))
    body = "".join(
        "<tr>" + "".join(
            f'<td valign="top" align="{align(j)}" style="{cell}text-align:{align(j)};border-top:1px solid {_RULE};'
            f'word-break:break-word;{"white-space:nowrap;" if j in t.numeric else ""}">{_e(v)}</td>'
            for j, v in enumerate(r)) + "</tr>" for r in t.rows)
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
            f'style="border:1px solid {_RULE};border-radius:8px;border-collapse:separate;">'
            f'<tr>{hdr}</tr>{body}</table>')


def render_html(n: Notice) -> str:
    tone = TONES.get(n.tone, TONES["bilgi"])
    headline = _e(n.headline)
    parts = []
    if n.what:
        parts.append(_section("Ne oldu", _paras(n.what)))
    if n.impact:
        parts.append(_section("Etkisi", _paras(n.impact)))
    if n.actions:
        parts.append(_section("Ne yapmalı", _steps(n.actions, tone)))
    if n.info:
        parts.append(_section(n.info_title, _paras(n.info)))
    for t in n.tables:
        if t.rows:
            parts.append(_section(plain(t.title) or "Ayrıntı", _table(t)))
    if n.link:
        href = html.escape(n.link, quote=True)
        parts.append(
            f'<tr><td class="px" style="padding:24px 32px 0 32px;">'
            f'<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>'
            f'<td style="border-radius:8px;background:{_INK};">'
            f'<a href="{href}" style="display:inline-block;padding:12px 20px;font-family:{_FONT};font-size:15px;'
            f'line-height:20px;font-weight:600;color:#FFFFFF;text-decoration:none;border-radius:8px;">'
            f'{html.escape(n.link_label)} &rarr;</a></td></tr></table>'
            f'<p style="margin:10px 0 0 0;font-family:{_FONT};font-size:12px;line-height:18px;color:{_MUTED};'
            f'word-break:break-all;">{href}</p></td></tr>')
    when = f" Gönderim: {html.escape(long_dt(n.at))}." if n.at else ""
    why = (f'<br>{_e(n.why)}' if n.why else "")
    return f"""<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<meta name="supported-color-schemes" content="light">
<title>{html.escape(n.subject)}</title>
<style>
@media only screen and (max-width: 480px) {{
  .px {{ padding-left: 20px !important; padding-right: 20px !important; }}
  .h1 {{ font-size: 19px !important; line-height: 26px !important; }}
}}
</style>
</head>
<body style="margin:0;padding:0;background:#F2F4F7;-webkit-text-size-adjust:100%;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:#F2F4F7;">{headline}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#F2F4F7;">
<tr><td align="center" style="padding:24px 12px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:640px;background:#FFFFFF;border:1px solid #E4E7EC;border-radius:12px;border-collapse:separate;">
<tr><td style="height:4px;line-height:4px;font-size:0;background:{tone['bar']};border-radius:12px 12px 0 0;">&nbsp;</td></tr>
<tr><td class="px" style="padding:24px 32px 0 32px;">
<p style="margin:0 0 14px 0;font-family:{_FONT};font-size:12px;line-height:16px;color:{_MUTED};letter-spacing:0.02em;">TİMAŞ · Zeki AI</p>
<span style="display:inline-block;padding:3px 10px;border-radius:999px;background:{tone['bg']};border:1px solid {tone['line']};font-family:{_FONT};font-size:12px;line-height:18px;font-weight:600;color:{tone['fg']};">&#9679;&nbsp;{html.escape(n.badge)}</span>
<h1 class="h1" style="margin:12px 0 0 0;font-family:{_FONT};font-size:21px;line-height:29px;font-weight:600;color:{_INK};">{headline}</h1>
</td></tr>
{''.join(parts)}
<tr><td class="px" style="padding:28px 32px 24px 32px;">
<p style="margin:0;padding-top:16px;border-top:1px solid {_RULE};font-family:{_FONT};font-size:12px;line-height:18px;color:{_MUTED};">{html.escape(FOOTER)}{when}{why}</p>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>
"""


# ------------------------------------------------------------------ ileti ve gönderim


Attachment = tuple[str, bytes, str]   # (dosya adı, içerik, MIME türü)


def message(n: Notice, sender: str, to: Sequence[str], attachments: Optional[Sequence[Attachment]] = None) -> EmailMessage:
    """Düz metin + HTML (`multipart/alternative`); ek varsa ikisi birlikte `multipart/mixed` içinde."""
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = n.subject, sender, ", ".join(to)
    msg.set_content(render_text(n))
    msg.add_alternative(render_html(n), subtype="html")
    for name, data, mime in attachments or []:
        main, _, sub = mime.partition("/")
        msg.add_attachment(data, maintype=main, subtype=sub or "octet-stream", filename=name)
    return msg


def send(n: Notice, to: Sequence[str], attachments: Optional[Sequence[Attachment]] = None) -> str:
    from semantic_bridge.alerts import smtp_settings

    to = [a for a in to if a]
    if not to:
        return "no_recipient"
    cfg = smtp_settings()
    if not cfg:
        return "no_smtp"
    try:
        msg = message(n, cfg["sender"], to, attachments)
        ctx = ssl.create_default_context()
        server = (smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=20, context=ctx) if cfg["ssl"]
                  else smtplib.SMTP(cfg["host"], cfg["port"], timeout=20))
        with server as s:
            if not cfg["ssl"] and cfg["starttls"]:
                s.starttls(context=ctx)
            if cfg["user"]:
                s.login(cfg["user"], cfg["password"])
            s.send_message(msg)
        return "sent"
    except Exception as e:  # noqa: BLE001
        log.warning("iç bildirim gönderilemedi (%s): %s", n.subject[:80], e)
        return "failed"
