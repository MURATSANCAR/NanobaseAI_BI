"""Modele giden metinde kişisel veri maskesi (KVKK). Sayı denetimi `sayi.py`.

Destek masası ayrı bir süreçtir (köprüye bağlı değildir); bu yüzden köprüdeki M51 maskesinin
(`backend/semantic_bridge/support.py` `mask_personal`) genişletilmiş bir kopyası burada durur (adres, ad ve imza
kalıpları, kaydın bilinen kişi adları). Bu dosya çatıyı içe aktarmaz: saf Python, çatısız birim testiyle sınanır
(`nanobase_brand/tests/test_yz_maske.py`).

Maske geri çevrilebilir: aynı değer aynı yer tutucuyu alır (`[e-posta 1]`, `[ad 2]` …). Temsilcinin ekranına dönen
model metninde yer tutucular gerçek değerle geri doldurulur (`geri`); herkese açık olabilecek metinde (bilgi bankası
makalesi) numarasız yer tutucu kalır (`genel`). Model gerçek değeri hiç görmez.
"""

from __future__ import annotations

import re
from typing import Iterable

_IBAN = re.compile(r"\bTR\s?\d{2}(?:\s?\d{4}){5}\s?\d{2}\b", re.I)
_MAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_CARD = re.compile(r"(?<!\d)(?:\d{4}[\s\-]?){3}\d{4}(?!\d)")
_TCKN = re.compile(r"(?<!\d)[1-9]\d{10}(?!\d)")
_PHONE = re.compile(r"(?<![\w])(?:\+?90[\s\-.]?)?\(?0?[2-5]\d{2}\)?[\s\-.]?\d{3}[\s\-.]?\d{2}[\s\-.]?\d{2}(?!\d)")

_UP = "A-ZÇĞİÖŞÜ"
_LOW = "a-zçğıöşü"
_WORD = rf"[{_UP}][{_LOW}]+"
_NAME = rf"{_WORD}(?:[ \t]+{_WORD}){{0,2}}"
# «Adres: …», «Teslimat adresi: …» satırın sonuna kadar.
_ADDR_LABEL = re.compile(r"(?im)^(?P<k>[ \t]*(?:teslimat |fatura |ev |iş |is )?adres(?:im)?[ \t]*[:：])[ \t]*(?P<v>\S[^\n]*)")
# Etiketsiz adres: mahalle/cadde/sokak/bulvar + kapı numarası aynı satırda.
_ADDR_FREE = re.compile(
    rf"(?:[{_UP}0-9][\w.\-]*[ \t]+){{0,4}}(?:Mah(?:allesi|\.)?|Mh\.|Cad(?:desi|\.)?|Cd\.|Sok(?:ağı|agi|ak|\.)?|Sk\.|Bulvar(?:ı|i)?|Blv\.)"
    r"[^\n]{0,120}?\bNo\s*[:.]?\s*\d+[A-Za-z]?(?:\s*/\s*\d+)?(?:[^\n]{0,60}?\b\d{5}\b)?",
    re.U)
# Ad kalıpları: «Sayın Ayşe Yılmaz», «Adım Ayşe», «Ad Soyad: …», «Ayşe Hanım», «Mehmet Bey».
_NAME_AFTER = re.compile(
    rf"(?P<k>\b(?i:sayın|sayin|adım|adim|ismim|adı soyadı\s*:|adi soyadi\s*:|ad soyad\s*:|ad-soyad\s*:|müşteri adı\s*:))"
    rf"[ \t]*(?P<v>{_NAME})")
_NAME_BEFORE = re.compile(rf"(?P<v>\b{_WORD})(?P<k>[ \t]+(?:Hanım|Hanim|Bey)\b)")
# İmza: kapanış satırından sonraki en çok üç kısa satır (ad, unvan, şirket).
_SIGNOFF = re.compile(r"(?im)^[ \t]*(saygılarımla|saygılarımızla|iyi çalışmalar|teşekkürler|tesekkurler|sevgiler|kolay gelsin)[ \t,.!]*$")

KINDS = ("e-posta", "telefon", "IBAN", "kart", "kimlik no", "adres", "ad", "imza")
_PH = re.compile(r"\[(" + "|".join(re.escape(k) for k in KINDS) + r") (\d+)\]", re.I)
YER_TUTUCU = _PH


class Maske:
	"""Bir iş (tek kayıt, tek rapor) boyunca tutulan geri çevrilebilir maske. `bilinen`: kaydın kendi kişi adları
	(ilgili kişi, gönderen); kalıpla yakalanmayan adlar da böylece maskelenir."""

	def __init__(self, bilinen: Iterable[str] = ()):
		self._by_value: dict[tuple[str, str], str] = {}
		self._by_ph: dict[str, str] = {}
		self._count: dict[str, int] = {}
		names = {" ".join(str(n or "").split()) for n in bilinen}
		# Uzun ad önce: «Ayşe Yılmaz» «Ayşe»den önce değişsin.
		self._known = sorted((n for n in names if len(n) >= 3 and not n.isdigit()), key=len, reverse=True)

	def _ph(self, kind: str, value: str) -> str:
		key = (kind, " ".join(value.split()).casefold())
		if key not in self._by_value:
			self._count[kind] = self._count.get(kind, 0) + 1
			ph = f"[{kind} {self._count[kind]}]"
			self._by_value[key] = ph
			self._by_ph[ph.casefold()] = value.strip()
		return self._by_value[key]

	def __call__(self, text: str | None) -> str:
		s = str(text or "")
		if not s:
			return s
		s = _IBAN.sub(lambda m: self._ph("IBAN", m.group(0)), s)
		s = _MAIL.sub(lambda m: self._ph("e-posta", m.group(0)), s)
		s = _CARD.sub(lambda m: self._ph("kart", m.group(0)), s)
		s = _TCKN.sub(lambda m: self._ph("kimlik no", m.group(0)), s)
		s = _PHONE.sub(lambda m: self._ph("telefon", m.group(0)), s)
		s = _ADDR_LABEL.sub(lambda m: f"{m.group('k')} {self._ph('adres', m.group('v'))}", s)
		s = _ADDR_FREE.sub(lambda m: self._ph("adres", m.group(0)), s)
		for name in self._known:
			# Tek kelimelik ad büyük harfle yazıldığı yerde maskelenir («Deniz» ad, «deniz» kelime); tam ad harf farksız.
			flags = re.I if " " in name else 0
			for form in {name, name.upper()}:
				s = re.sub(rf"(?<![\w]){re.escape(form)}(?![\w])", lambda m: self._ph("ad", m.group(0)), s, flags=flags)
		s = _NAME_AFTER.sub(lambda m: f"{m.group('k')} {self._ph('ad', m.group('v'))}", s)
		s = _NAME_BEFORE.sub(lambda m: f"{self._ph('ad', m.group('v'))}{m.group('k')}", s)
		return _signature(s, self)

	def geri(self, text: str | None) -> str:
		"""Model metnindeki yer tutucuları gerçek değerle doldurur (yalnız o kaydı görme yetkisi olan temsilciye)."""
		return _PH.sub(lambda m: self._by_ph.get(m.group(0).casefold(), m.group(0)), str(text or ""))

	@staticmethod
	def genel(text: str | None) -> str:
		"""Numarasız yer tutucu: herkese açılabilecek metinde kimin verisi olduğu da belli olmasın."""
		return _PH.sub(lambda m: f"[{m.group(1).lower() if m.group(1) != 'IBAN' else 'IBAN'}]", str(text or ""))

	@property
	def adet(self) -> int:
		return len(self._by_ph)


def _signature(s: str, m: Maske) -> str:
	"""Kapanış satırından («Saygılarımla») sonraki en çok üç kısa satır (en çok 5 kelime, 60 karakter) imzadır."""
	lines = s.split("\n")
	out, left = [], 0
	for line in lines:
		t = line.strip()
		if left and t:
			if len(t) <= 60 and len(t.split()) <= 5 and not t.endswith("?"):
				# Adı zaten yer tutucuya dönmüş satır olduğu gibi kalır; imza sayılmaya devam eder.
				out.append(line if _PH.search(t) else m._ph("imza", t))
				left -= 1
				continue
			left = 0
		out.append(line)
		if _SIGNOFF.match(line):
			left = 3
	return "\n".join(out)


def maskele(text: str | None, bilinen: Iterable[str] = ()) -> str:
	"""Tek seferlik maske (geri çevrilmeyecek metin: arama sorgusu, rapor konuları)."""
	return Maske(bilinen)(text)
