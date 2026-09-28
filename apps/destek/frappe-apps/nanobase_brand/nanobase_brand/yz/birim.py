"""Talep edenin birimi (2026-09-28 kullanıcı kararı: «maili atan kişinin departmanını otomatik tespit et, ona göre»).

Kaydı açanın e-posta adresi AD'de aranır (mail, userPrincipalName, proxyAddresses; iç alan adında hesap adı);
birim AD «department» alanıdır, boşsa kişiye en yakın OU (Timaş'ta birim OU'dadır — ldap_ntlm._department).
Birim kayda yazılır (`nb_talep_birimi`). Aynı adlı (etkin) destek ekibi varsa ve kayıtta ekip seçilmemişse kayıt o
ekibe gider; bu, yapay zekânın ekip önerisinden önce gelir. Eşleşen ekip yoksa yalnız birim görünür — ekip AD birim
adıyla açıldığı gün yönlendirme kendiliğinden başlar (ekipler yöneticinin kararı; burada ekip açılmaz).
AD'de bulunmayan (şirket dışı) gönderende birim boş kalır.
"""

from __future__ import annotations

import frappe

CACHE = "nb_ad_birim::"
CACHE_SECONDS = 24 * 3600


def bul(email: str | None) -> str:
	email = (email or "").strip().lower()
	if "@" not in email:
		return ""
	cached = frappe.cache.get_value(CACHE + email)
	if cached is not None:
		return cached
	try:
		ldap = frappe.get_doc("LDAP Settings")
		if not ldap.enabled:
			return ""
		dep = _ara(ldap, email)
	except Exception:
		# AD'ye ulaşılamadı: sonuç önbelleğe yazılmaz, sonraki kayıtta yeniden denenir.
		frappe.log_error(title="NanobaseAI: talep edenin birimi AD'de aranamadı")
		return ""
	frappe.cache.set_value(CACHE + email, dep, expires_in_sec=CACHE_SECONDS)
	return dep


def _ara(ldap, email: str) -> str:
	from ldap3.utils.conv import escape_filter_chars

	from nanobase_brand.ldap_ntlm import _department

	e = escape_filter_chars(email)
	local, _sep, domain = email.partition("@")
	secenek = f"(mail={e})(userPrincipalName={e})(proxyAddresses=smtp:{e})"
	if domain and domain == (ldap.dns_domain or "").lower():
		# AD'de e-postası olmayan kişiye sistem hesap@iç-alan-adı verir (ldap_ntlm.convert_ldap_entry_to_dict).
		secenek += f"(sAMAccountName={escape_filter_chars(local)})"
	conn = ldap.connect_to_ldap(ldap.base_dn, ldap.get_password(raise_exception=False))
	try:
		conn.search(
			search_base=ldap.ldap_search_path_user,
			search_filter=f"(&(objectCategory=person)(objectClass=user)(|{secenek}))",
			attributes=["department"],
			size_limit=2,
		)
		# Birden çok kişi eşleşirse (paylaşılan adres) birim belirsizdir: yazılmaz.
		return _department(conn.entries[0]) if len(conn.entries) == 1 else ""
	finally:
		conn.unbind()


def ekip(birim: str) -> str | None:
	from nanobase_brand.ldap_ntlm import _fold

	if not birim:
		return None
	want = _fold(birim)
	return next((t for t in frappe.get_all("HD Team", filters={"disabled": 0}, pluck="name") if _fold(t) == want), None)


def uygula(doc) -> dict:
	"""Birimi ve (ekip boşsa) eşleşen ekibi belgeye koyar, kaydetmez. Değişen alanları döndürür."""
	out: dict = {}
	birim = bul(doc.raised_by)
	if not birim:
		return out
	if doc.get("nb_talep_birimi") != birim:
		doc.nb_talep_birimi = out["nb_talep_birimi"] = birim
	if not doc.agent_group and (team := ekip(birim)):
		doc.agent_group = out["agent_group"] = team
	return out
