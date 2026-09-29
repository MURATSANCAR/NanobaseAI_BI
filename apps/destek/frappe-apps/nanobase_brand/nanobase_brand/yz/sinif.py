"""Yeni kaydın sınıflaması — tek konu kararı, olasılıklı seçim.

Önceden masa ve köprüdeki M51 aynı talebi iki ayrı yöntemle sınıflıyordu (masa: serbest JSON, olasılıksız; M51: kapalı
küme + olasılık) ve aynı talebe iki farklı konu çıkabiliyordu. Artık:

- **Konu** (masada «tür», `ticket_type`) köprüde bir kez verilir: `POST …/destek-baglam/v1/classify` → M51'in kapalı
  kümesi, olasılık eşiği, maskeli metin; karar M51'e kaydedilir (5 dk'lık tur aynı talebi yeniden sormaz). Masa türü bu
  kararın sınıf adıdır; masada o adda tür yoksa eklenir (liste ortak: M51'in sınıfları). Eşik altı ya da köprüye
  ulaşılamazsa tür boş kalır — masada ayrıca konu tahmini yapılmaz, iki çelişen sınıf oluşmaz.
- **Öncelik, ekip, duygu** masaya özgüdür; kapalı küme seçim + olasılıkla (`llm.choose`, LLM kapısından). Eşik altı alan
  doldurulmaz.

Eşikler site ayarında: `nb_sinif_min_p` (vars. 0.70), `nb_sinif_min_marj` (vars. 0.30) — M51 varsayılanlarıyla aynı.
Köprü adresi `nb_destek_baglam_url` (yoksa model adresindeki `/destek-llm/` → `/destek-baglam/`), anahtar modelinkiyle
aynı; köprüde panel anahtarı açıksa `nb_destek_panel_key`.
"""

from __future__ import annotations

import frappe
import requests

from nanobase_brand.yz import llm, secim

EKIPSIZ = "Belli bir ekibe ait değil"


def _esik() -> tuple[float, float]:
	def f(key: str, vars: float) -> float:
		try:
			return max(0.0, min(1.0, float(frappe.conf.get(key) or vars)))
		except (TypeError, ValueError):
			return vars

	return f("nb_sinif_min_p", 0.70), f("nb_sinif_min_marj", 0.30)


def baglam_adresi(model_base: str, ayar: str | None) -> str | None:
	"""Köprünün masa ucu: site ayarı, yoksa model adresinden (aynı nginx, aynı anahtar)."""
	if ayar:
		return ayar.rstrip("/")
	if "/destek-llm/" in (model_base or "") + "/":
		return (model_base.rstrip("/") + "/").replace("/destek-llm/", "/destek-baglam/").rstrip("/")
	return None


def konu(doc) -> dict | None:
	"""Köprüdeki M51 kararı (tek karar). Ulaşılamazsa None; kayıt yine açılır, M51 turu sonra sınıflar."""
	try:
		base, key, _ = llm._endpoint()
	except llm.ModelUnavailable:
		return None
	url = baglam_adresi(base, frappe.conf.get("nb_destek_baglam_url"))
	if not url:
		return None
	headers = {"Content-Type": "application/json"}
	if key:
		headers["Authorization"] = f"Bearer {key}"
	if frappe.conf.get("nb_destek_panel_key"):
		headers["X-Destek-Panel-Key"] = str(frappe.conf.get("nb_destek_panel_key"))
	body = {"ticket": doc.name, "subject": doc.subject, "description": doc.description, "raised_by": doc.raised_by,
			"opening_date": str(doc.opening_date or ""), "modified": str(doc.modified or "")}
	try:
		resp = requests.post(f"{url}/classify", json=body, headers=headers, timeout=170)
		if resp.status_code >= 400:
			frappe.log_error(title=f"NanobaseAI konu: köprü {resp.status_code} ({doc.name})", message=resp.text[:1000])
			return None
		return resp.json()
	except (requests.RequestException, ValueError):
		frappe.log_error(title=f"NanobaseAI konu: köprüye ulaşılamadı ({doc.name})")
		return None


def _fold(s: str) -> str:
	return " ".join(str(s or "").replace("İ", "i").replace("I", "ı").lower().split())


def tur_adi(etiket: str, turler: list[str]) -> str | None:
	"""M51 sınıf adının masadaki türü (büyük/küçük harf farkı gözetmeden); yoksa None."""
	hedef = _fold(etiket)
	return next((t for t in turler if _fold(t) == hedef), None)


def _tur(etiket: str, aciklama: str, turler: list[str]) -> str:
	var = tur_adi(etiket, turler)
	if var:
		return var
	d = frappe.get_doc({"doctype": "HD Ticket Type", "name": etiket, "description": aciklama or ""})
	d.flags.ignore_permissions = True
	d.insert()
	frappe.db.commit()  # kayıt kaydı geri alınsa da tür kalsın (tür bağlantısı boşa düşmesin)
	turler.append(d.name)
	return d.name


def _yuzde(r: dict) -> str:
	p = r.get("probability") if "probability" in r else r.get("p")
	return f"%{round(float(p) * 100)}" if p is not None else "olasılık yok"


# Öncelik sıralı bir ölçektir: olasılık komşu iki düzeye bölünür (2026-09-29 «acil sözleşme basmam lazım»:
# Acil %68 + Yüksek %29 — ikisi de %70 eşiğinin altında kaldı, öncelik boş kaldı). Komşu iki düzeyin toplamı
# KOMSU_TOPLAM'ı geçer ve en olası düzey KOMSU_EN_AZ'dan büyükse en olası düzey seçilir.
ONCELIK_SIRASI = ("Urgent", "High", "Medium", "Low")
KOMSU_TOPLAM = 0.9
KOMSU_EN_AZ = 0.5


def _komsu(probs: dict | None, sira: list[str]) -> str | None:
	if not probs or len(probs) < 2:
		return None
	a, b = sorted(probs, key=probs.get, reverse=True)[:2]
	if a in sira and b in sira and abs(sira.index(a) - sira.index(b)) == 1 \
			and probs[a] + probs[b] >= KOMSU_TOPLAM and probs[a] >= KOMSU_EN_AZ:
		return a
	return None


def oner(doc, text: str, types: list[str], priorities: list[str], teams: list[str], duygular) -> dict:
	"""kayit.classify'ın beklediği biçim: ticket_type, priority, agent_group, duygu, gerekce. Yalnız eşiği geçen alan
	dolar. `types` listesi eklenen türle güncellenir. Hiçbir alan sorulamadıysa `ModelUnavailable`."""
	min_p, min_m = _esik()
	out: dict = {}
	notlar: list[str] = []
	hata = 0

	k = konu(doc)
	if k and k.get("confident") and k.get("label"):
		out["ticket_type"] = _tur(k["label"], k.get("description") or "", types)
		notlar.append(f"konu: {k['label']} ({_yuzde(k)}{', temsilci düzeltmesi' if k.get('by') not in (None, 'zeki') else ''})")
	elif k:
		notlar.append("konu: emin değil" + (f" (en olası {k['guessLabel']})" if k.get("guessLabel") else ""))
	else:
		notlar.append("konu: sonra sınıflanacak")

	kayit = f"KAYIT:\n{text}"
	sorular = []
	if priorities:
		sorular.append(("priority", "öncelik", "Aşağıdaki destek kaydının önceliği hangisi olmalı?", list(priorities)))
	if teams:
		sorular.append(("agent_group", "ekip", "Aşağıdaki destek kaydına hangi ekip bakmalı?", [*teams, EKIPSIZ]))
	sorular.append(("duygu", "duygu", "Aşağıdaki destek kaydında müşterinin duygusu hangisi?", list(duygular)))
	for alan, ad, soru, secenekler in sorular:
		# Öncelik Türkçe adlarıyla sorulur («Urgent» yerine «Acil»): model Türkçe metinde Türkçe ölçeği daha net seçiyor.
		etiket = {frappe._(s): s for s in secenekler} if alan == "priority" else {s: s for s in secenekler}
		if len(etiket) != len(secenekler):
			etiket = {s: s for s in secenekler}
		try:
			r = llm.choose(f"{soru}\n\n{kayit}", list(etiket), priority=llm.BACKGROUND)
		except llm.ModelUnavailable:
			hata += 1
			continue
		secilen = etiket.get(r.get("choice")) if r.get("choice") else None
		if secim.emin(r, min_p, min_m) and secilen != EKIPSIZ:
			out[alan] = secilen
			notlar.append(f"{ad}: {r['choice']} ({_yuzde(r)})")
			continue
		if alan == "priority":
			sira = [frappe._(p) for p in ONCELIK_SIRASI if p in secenekler]
			komsu = _komsu(r.get("probs"), sira)
			if komsu:
				out[alan] = etiket[komsu]
				p = r["probs"]
				ikinci = sorted(p, key=p.get, reverse=True)[1]
				notlar.append(f"{ad}: {komsu} (%{round(p[komsu] * 100)}; {ikinci} ile birlikte %{round((p[komsu] + p[ikinci]) * 100)})")
				continue
		notlar.append(f"{ad}: emin değil")
	if hata == len(sorular) and not k:
		raise llm.ModelUnavailable("sınıflama yapılamadı")
	out["gerekce"] = "Olasılıklı seçim — " + "; ".join(notlar)
	return out
