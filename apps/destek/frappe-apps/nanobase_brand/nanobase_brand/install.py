"""Marka ve bölge ayarlarını siteye yazar.

after_install ve her after_migrate'te koşar; değer zaten doğruysa belgeye dokunmaz.
Alan adı sürümden sürüme değişebildiği için yalnız mevcut alanlar yazılır.
"""

import frappe

BRAND = "NanobaseAI"
MARK = "/assets/nanobase_brand/images/logo-mark.svg"
LOGO = "/assets/nanobase_brand/images/logo.svg"
FAVICON = "/assets/nanobase_brand/images/favicon.svg"

SETTINGS = [
	("System Settings", {
		"app_name": BRAND,
		"country": "Turkey",
		"language": "tr",
		"time_zone": "Europe/Istanbul",
		"date_format": "dd.mm.yyyy",
		"number_format": "#.###,##",
		"first_day_of_the_week": "Monday",
		"currency": "TRY",
		# Kullanım verisi dışarı gitmez.
		"enable_telemetry": 0,
		"disable_standard_email_footer": 1,
		# Giriş sayfası dışarıya açık ve AD şifresi soruyor: 5 yanlışta 15 dk kilit (nginx'te IP sınırı da var).
		"allow_consecutive_login_attempts": 5,
		"allow_login_after_fail": 900,
		"email_footer_address": BRAND,
	}),
	# Ayrı adım: seçenek listesi çalışma anında dolar; tutmazsa öteki ayarları düşürmesin.
	# Girişten sonra doğrudan destek ekranı açılır.
	("System Settings", {"default_app": "helpdesk"}),
	("Website Settings", {
		"app_name": BRAND,
		"app_logo": MARK,
		"favicon": FAVICON,
		"splash_image": MARK,
		"brand_html": f'<img src="{LOGO}" alt="{BRAND}" style="height:28px">',
		"footer_powered": BRAND,
		"hide_footer_signup": 1,
	}),
	("Navbar Settings", {
		"app_logo": MARK,
	}),
	("HD Settings", {
		# Dışarıya otomatik e-posta yok: kayıt açılınca alındı, çözülünce memnuniyet e-postası gitmez.
		"send_acknowledgement_email": 0,
		"enable_email_ticket_feedback": 0,
		"brand_name": BRAND,
		"brand_logo": MARK,
		"favicon": FAVICON,
	}),
]


CUSTOM_FIELDS = {
	"HD Ticket": [
		{"fieldname": "nb_yz_section", "fieldtype": "Section Break", "label": "NanobaseAI", "collapsible": 1},
		{"fieldname": "nb_duygu", "fieldtype": "Select", "label": "Müşteri duygusu",
		 "options": "\nOlumlu\nNötr\nOlumsuz\nÖfkeli", "read_only": 1, "insert_after": "nb_yz_section"},
		{"fieldname": "nb_yz_not", "fieldtype": "Small Text", "label": "Sınıflama gerekçesi", "read_only": 1,
		 "insert_after": "nb_duygu"},
		{"fieldname": "nb_yz_ozet", "fieldtype": "Small Text", "label": "Yazışma özeti", "read_only": 1,
		 "insert_after": "nb_yz_not"},
		{"fieldname": "nb_yz_ozet_zamani", "fieldtype": "Datetime", "label": "Özet zamanı", "read_only": 1,
		 "insert_after": "nb_yz_ozet"},
	],
	"HD Article": [
		{"fieldname": "nb_kaynak_kayit", "fieldtype": "Link", "options": "HD Ticket", "label": "Kaynak kayıt",
		 "read_only": 1},
	],
}


# Bağlantı alanında adı görünen sabit listeler: masaüstü ekranı değeri çeviriyle gösterir («Open» → «Açık»).
TRANSLATED_DOCTYPES = ("HD Ticket Status", "HD Ticket Type", "HD Ticket Priority")


def apply():
	_custom_fields()
	_translated_doctypes()
	_help_menu()
	for doctype, values in SETTINGS:
		if not frappe.db.exists("DocType", doctype):
			continue
		# Bir ayarın doğrulaması göçü düşürmesin: hata kaydedilir, diğer ayarlar yazılır.
		try:
			_write_single(doctype, values)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"NanobaseAI marka ayarı yazılamadı: {doctype}")
			frappe.db.commit()


def _write_single(doctype, values):
	meta = frappe.get_meta(doctype)
	doc = frappe.get_single(doctype)
	changed = False
	for field, value in values.items():
		if not meta.has_field(field):
			continue
		if field in ("country", "language", "currency") and not _exists_for_link(meta, field, value):
			continue
		if doc.get(field) != value:
			doc.set(field, value)
			changed = True
	if not changed:
		return
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.save()


def _exists_for_link(meta, field, value):
	target = meta.get_field(field).options
	return not target or bool(frappe.db.exists(target, value))


def _help_menu():
	"""Yardım menüsünde dışarıya giden standart bağlantılar gizlenir.

	Satır silinmez: her göçte standart öğeler eksikse yeniden eklenir, gizli satır olduğu gibi kalır.
	"""
	if not frappe.db.exists("DocType", "Navbar Settings"):
		return
	try:
		doc = frappe.get_single("Navbar Settings")
		changed = False
		for row in doc.get("help_dropdown") or []:
			if (row.route or "").startswith(("http://", "https://")) and not row.hidden:
				row.hidden = 1
				changed = True
		if changed:
			doc.flags.ignore_permissions = True
			doc.save()
			frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="NanobaseAI yardım menüsü ayarlanamadı")


def _translated_doctypes():
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	for doctype in TRANSLATED_DOCTYPES:
		if not frappe.db.exists("DocType", doctype) or frappe.get_meta(doctype).translated_doctype:
			continue
		try:
			make_property_setter(doctype, None, "translated_doctype", 1, "Check", for_doctype=True)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"NanobaseAI çeviri ayarı yazılamadı: {doctype}")


def _custom_fields():
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	present = {dt: fields for dt, fields in CUSTOM_FIELDS.items() if frappe.db.exists("DocType", dt)}
	if present:
		create_custom_fields(present, ignore_validate=True, update=True)
		frappe.db.commit()
	# Bilgi bankası model tanımlıysa kurulur; ilk kurulumda model sonradan gelir (ai.ensure_model çağırır).
	try:
		from nanobase_brand.yz import bilgi

		bilgi.ensure()
	except Exception:
		frappe.log_error(title="NanobaseAI bilgi bankası kurulamadı")
