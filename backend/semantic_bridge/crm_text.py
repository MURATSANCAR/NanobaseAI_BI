"""CRM zengin metin alanları → ekranda gösterilecek düz metin (ZEKI-23).

CRM'in zengin metin alanları (kişi özgeçmişi `new_ozgecmis` / `new_kisaozgecmis`, kitap arka kapağı `new_ozet`,
tanıtım metinleri, kurul notları…) çoğu zaman Word'den yapıştırılmış HTML tutar:
`<p class="MsoNormal"><span style="…">1948&rsquo;de Isparta, &Scedil;arkikaraa&gbreve;a…`. Ekran bunu React ile
metin olarak basınca kod görünüyordu; modüllerin kendi küçük sökücüleri de yalnız `&nbsp;`/`&amp;` çözdüğü için
`&rsquo;`, `&Scedil;`, `&gbreve;` gibi adlandırılmış varlıklar ekranda kalıyordu.

Burada tek kural var, her modül bunu kullanır:

- Güvenlik: çıktı her zaman DÜZ METİNDİR; ekran onu metin düğümü olarak basar, HTML olarak işlenmez (XSS yolu yok).
  `<script>`, `<style>`, Word'ün `<xml>` / koşullu yorum blokları içerikleriyle birlikte atılır.
- Paragraf: `<p>`, `<div>`, `<li>`, `<h1-6>`, `<tr>`, `<blockquote>` kapanışı ve `<br>` satır sonu olur; liste maddesi
  «• » ile başlar. Boş satırlar atılır (her paragraf bir satır); satır içi boşluklar teke iner.
- Varlıklar: HTML5'in bütün adlandırılmış ve sayısal varlıkları çözülür (`html.unescape`). İki kez kaçışlanmış metin
  (`&lt;p&gt;…`) de çözülür: çözülen metin yeniden etiket içeriyorsa işlem bir tur daha yapılır (en çok üç tur;
  sonuç değişmeyince durur — veri kesilmez, yalnız döngü sınırlanır).
- Düz metin bozulmaz: yalnız etiket adıyla başlayan `<…>` sökülür; «3 < 5 > 2» gibi metin olduğu gibi kalır.
- Uzunluk sınırı yoktur; çağıran kendi (var olan) sınırını ayrıca uygular.
"""
from __future__ import annotations

import html
import re
from typing import Any, Optional

# İçeriğiyle birlikte atılan bloklar (Word yapıştırması <style>, <xml>, <!--[if gte mso 9]>… taşır).
_DROP = re.compile(r"(?is)<!--.*?-->|<(script|style|xml|head|title)\b[^>]*>.*?</\1\s*>|<!\[[^\]]*\]>|<\?[^>]*>")
_BR = re.compile(r"(?i)<br\s*/?>")
_LI = re.compile(r"(?i)<li\b[^>]*>")
_BLOCK_END = re.compile(r"(?i)</(p|div|li|h[1-6]|tr|blockquote|pre|table|ul|ol|section|article|header|footer)\s*>")
_BLOCK_START = re.compile(r"(?i)<(p|div|h[1-6]|tr|blockquote|pre|table|ul|ol|section|article|header|footer)\b[^>]*>")
_CELL_END = re.compile(r"(?i)</t[dh]\s*>")
# HTML kaynağındaki satır sonu boşluktur, paragraf değil (Word kaynağı uzun satırları kaydırır).
_SOURCE_NL = re.compile(r"[ \t]*\n[ \t\n]*")
# Yalnız gerçek etiket biçimi: harfle başlayan ad (isteğe bağlı ad alanı, `o:p` gibi) ya da kapanış/doctype.
_TAG = re.compile(r"</?[A-Za-z][A-Za-z0-9:_-]*(?:\s[^<>]*)?/?>|<![A-Za-z][^<>]*>")
_ENTITY = re.compile(r"&(#\d+|#[xX][0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]{1,31});")
_SPACES = re.compile("[ \t\f\v\u00a0\u2007\u202f\u200b]+")
_ROUNDS = 3


def looks_rich(v: Any) -> bool:
    """Metin HTML etiketi ya da HTML varlığı içeriyor mu (sökmeye gerek var mı)."""
    t = str(v or "")
    return bool(_TAG.search(t) or _ENTITY.search(t) or "<!--" in t)


def _one_pass(t: str) -> str:
    if _TAG.search(t):
        t = _SOURCE_NL.sub(" ", t)
    t = _DROP.sub("", t)
    t = _BR.sub("\n", t)
    t = _LI.sub("\n• ", t)
    t = _BLOCK_END.sub("\n", t)
    t = _BLOCK_START.sub("\n", t)
    t = _CELL_END.sub(" ", t)
    t = _TAG.sub("", t)
    return html.unescape(t)


def rich_text(v: Any, *, keep_blank: bool = False) -> Optional[str]:
    """Zengin metin → paragrafları korunmuş düz metin.

    Her paragraf bir satırdır, satırlar `\\n` ile ayrılır; ekran `white-space: pre-line` ile basar. Boş satırlar
    atılır; `keep_blank=True` ise art arda boş satırlar tek boş satıra iner (paragraf arası boşluğu korunan metinler)."""
    if v is None:
        return None
    t = str(v).replace("\r\n", "\n").replace("\r", "\n")
    for _ in range(_ROUNDS):
        if not looks_rich(t):
            break
        nxt = _one_pass(t)
        if nxt == t:
            break
        t = nxt
    lines = [_SPACES.sub(" ", ln).strip() for ln in t.split("\n")]
    if keep_blank:
        out = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip("\n")
    else:
        out = "\n".join(ln for ln in lines if ln)
    return out or None


def rich_line(v: Any) -> Optional[str]:
    """Zengin metin → tek satır düz metin (liste satırı, özet kutusu, arama metni için)."""
    t = rich_text(v)
    if t is None:
        return None
    return " ".join(t.replace("• ", "").split()) or None
