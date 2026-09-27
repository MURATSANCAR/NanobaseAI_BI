"""Marka ve bölge ayarlarını siteye yazar.

after_install ve her after_migrate'te koşar; değer zaten doğruysa belgeye dokunmaz.
Alan adı sürümden sürüme değişebildiği için yalnız mevcut alanlar yazılır.
"""

import frappe

BRAND = "NanobaseAI"
MARK = "/assets/nanobase_brand/images/logo-mark.svg"
LOGO = "/assets/nanobase_brand/images/logo.svg"
FAVICON = "/assets/nanobase_brand/images/favicon.svg"

SETTINGS = {
	"System Settings": {
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
		"email_footer_address": BRAND,
	},
	"Website Settings": {
		"app_name": BRAND,
		"app_logo": MARK,
		"favicon": FAVICON,
		"splash_image": MARK,
		"brand_html": f'<img src="{LOGO}" alt="{BRAND}" style="height:28px">',
		"footer_powered": BRAND,
		"hide_footer_signup": 1,
	},
	"Navbar Settings": {
		"app_logo": MARK,
	},
	"HD Settings": {
		"brand_name": BRAND,
		"brand_logo": MARK,
		"favicon": FAVICON,
	},
}


def apply():
	for doctype, values in SETTINGS.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		_write_single(doctype, values)
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
