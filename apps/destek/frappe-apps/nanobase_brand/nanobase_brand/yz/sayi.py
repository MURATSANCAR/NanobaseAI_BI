"""Model metnindeki sayıların olgularla denetimi ve tutmayan metnin yerine geçen kural metni.

İlke: rakamı model üretmez. Modelin yazdığı metinde geçen her sayı, modele verilen olgularda (veritabanından sayılmış
değerler, kayıt konuları) geçmelidir; geçmeyen bir sayı varsa metin atılır, yerine olgulardan kuralla yazılan metin
kullanılır. Köprüdeki `backend/semantic_bridge/marketing/guard.py` kuralının destek masasındaki küçük kopyası (masa
ayrı süreçtir). Saf Python; çatısız birim testi `nanobase_brand/tests/test_yz_maske.py`.
"""

from __future__ import annotations

import re
from typing import Iterable

from nanobase_brand.yz.maske import YER_TUTUCU

_NUM = re.compile(r"\d+(?:[.,]\d+)*")
_RUN = re.compile(r"\d+")


def _norm(n: str) -> str:
	n = re.sub(r"[.,]", "", n)
	return n.lstrip("0") or "0"


def izinli_sayilar(olgular: Iterable[str]) -> set[str]:
	"""Olgularda geçen sayılar: «1.250» ve «1250» aynı; «28.09.2026» hem bütün hem de 28, 9, 2026 olarak."""
	out: set[str] = set()
	for f in olgular:
		f = str(f or "")
		out |= {_norm(x) for x in _NUM.findall(f)}
		out |= {_norm(x) for x in _RUN.findall(f)}
	return out


def olgu_disi_sayilar(metin: str | None, olgular: Iterable[str]) -> list[str]:
	"""Model metninde geçip olgularda olmayan sayılar (boş liste = metin geçer). Madde numarası da sayıdır: model
	metni olgudan başka rakam taşımaz. Maskenin yer tutucusundaki numara («[ad 1]») sayılmaz."""
	izin = izinli_sayilar(olgular)
	metin = YER_TUTUCU.sub(" ", str(metin or ""))
	return sorted({n for n in _NUM.findall(metin) if _norm(n) not in izin})


def maddeler(metin: str | None) -> list[str]:
	"""«- …» satırları → madde listesi (işaret atılır, boş satır düşer)."""
	return [ln.strip().lstrip("-•*").strip() for ln in str(metin or "").splitlines() if ln.strip().lstrip("-•*").strip()]


def haftalik_olgular(sayilar: dict[str, object], dagilim: dict[str, list[tuple[str, int]]]) -> list[str]:
	"""Haftalık raporun modele verilen olgu satırları (hepsi veritabanından sayılmış)."""
	out = [f"{k}: {v}" for k, v in sayilar.items() if v not in (None, "")]
	for ad, rows in dagilim.items():
		if rows:
			out.append(f"{ad}: " + ", ".join(f"{k} {v}" for k, v in rows))
	return out


def haftalik_kural_yorumu(sayilar: dict[str, object], dagilim: dict[str, list[tuple[str, int]]]) -> list[str]:
	"""Model yoksa ya da metni olgularla tutmazsa: aynı olgulardan kuralla yazılan en çok 5 madde."""
	out: list[str] = []
	acilan, onceki = sayilar.get("Açılan kayıt"), sayilar.get("Önceki hafta açılan")
	if isinstance(acilan, int) and isinstance(onceki, int):
		if acilan > onceki:
			out.append(f"Açılan kayıt geçen haftadan fazla: {onceki} → {acilan}.")
		elif acilan < onceki:
			out.append(f"Açılan kayıt geçen haftadan az: {onceki} → {acilan}.")
		else:
			out.append(f"Açılan kayıt geçen haftayla aynı: {acilan}.")
	for ad, etiket in (("Tür", "En çok kayıt açılan tür"), ("Ekip", "En çok kayıt alan ekip")):
		rows = [r for r in dagilim.get(ad) or [] if r[0] and not str(r[0]).startswith("(")]
		if rows:
			out.append(f"{etiket}: {rows[0][0]} ({rows[0][1]}).")
	ihlal = sayilar.get("SLA ihlali (bu hafta açılanlarda)")
	if isinstance(ihlal, int) and ihlal:
		out.append(f"Bu hafta açılan kayıtlardan {ihlal} tanesinde SLA ihlal edildi.")
	olumsuz = sum(v for k, v in dagilim.get("Müşteri duygusu") or [] if k in ("Olumsuz", "Öfkeli"))
	if olumsuz:
		out.append(f"Olumsuz ya da öfkeli yazan müşteri kaydı: {olumsuz}.")
	return out[:5]


def yorum_sec(model_metni: str | None, olgular: Iterable[str], kural: list[str]) -> tuple[list[str], str, list[str]]:
	"""(maddeler, kaynak, olgu dışı sayılar). kaynak: «model» ya da «kural». Model metni boşsa ya da tek bir olgu
	dışı sayı taşıyorsa bütünüyle atılır (yarım yorum bırakılmaz)."""
	olgular = list(olgular)
	lines = maddeler(model_metni)[:5]
	if not lines:
		return kural, "kural", []
	disari = olgu_disi_sayilar("\n".join(lines), olgular)
	if disari:
		return kural, "kural", disari
	return lines, "model", []
