"""Merkezi denetim kaydı — Destek tarafı.

Portalın denetim kaydı (BI köprüsü, Yönetim → Denetim kaydı) her sistemi tek yerde toplar. Destek'te:

- **Kayıt değişikliği** (`doc_events "*"`): her belge türünde ekleme (tam belge), güncelleme (değişen alanların
  önce → sonra değeri; alt tablolar dahil), silme (silinen belgenin tamamı), gönderme/iptal. Parola türündeki ve adı
  gizli anahtara benzeyen alanlar maskeli.
- **Oturum**: Activity Log satırları (giriş, çıkış, başarısız giriş) işlem olarak.
- **İstek** (`after_request`): kişi, IP, tarayıcı, yöntem, yol, gönderilen form/gövde (maskeli), sonuç kodu, süre.

Olay önce bu sitenin kendi veritabanındaki `nb_audit_outbox` tablosuna yazılır — belge değişikliğiyle **aynı işlemde**:
değişiklik geri alınırsa olay da gider, kalıcı olursa olay da kalır. Zamanlayıcının her turunda (Frappe varsayılanı 4 dk) `gonder()` kutuyu merkeze yollar
(`<destek-baglam>/audit-ingest`, model anahtarıyla aynı masa anahtarı) ve yalnız merkez yazdığını söyledikten sonra siler.
Merkez kapalıysa olaylar kutuda bekler; sayı tavanı yoktur.
"""

import json
import re
import time
import uuid

import frappe

OUTBOX = "nb_audit_outbox"

#: Kendisi kayıt/iz olan ya da makinenin kendi işletim satırı olan türler: ikinci kez kaydedilmez.
SKIP = frozenset({
	"Version", "Deleted Document", "Access Log", "Error Log", "Scheduled Job Log", "Route History", "Email Queue",
	"Email Queue Recipient", "RQ Job", "Integration Request", "Webhook Request Log", "Submission Queue",
	"Prepared Report", "Data Import Log", "Transaction Log", "Console Log", "View Log", "Energy Point Log",
	"Notification Log", "Session Default Settings", "Scheduled Job Type", "Unhandled Email", "SMS Log",
})
#: İstek kaydına girmeyen yollar: derleme dosyaları, canlı bağlantı, durum yoklaması.
SKIP_PATH = re.compile(r"^/(?:assets|files|socket\.io|private/files)/|\.(?:js|css|map|png|jpe?g|gif|svg|webp|ico|woff2?)$"
                       r"|^/api/method/(?:frappe\.realtime\.|frappe\.client\.get_count|ping)")
SECRET = re.compile(r"(pass(word|wd)?|pwd|parola|sifre|şifre|secret|token|api_?key|apikey|credential|private_?key|cookie|"
                    r"authorization|client_secret|smtp_pass)", re.I)
_SYSTEM_FIELDS = {"modified", "modified_by", "idx", "_liked_by", "_comments", "_seen", "_assign", "_user_tags"}


def ensure_table():
	frappe.db.sql_ddl(
		f"""CREATE TABLE IF NOT EXISTS `{OUTBOX}` (
			`id` bigint NOT NULL AUTO_INCREMENT PRIMARY KEY,
			`at` datetime(6) NOT NULL,
			`body` longtext NOT NULL
		) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"""
	)


def _now():
	return time.time()


def _mask(value, key=""):
	if key and SECRET.search(str(key)) and value not in (None, "", [], {}):
		return "«gizli»"
	if isinstance(value, dict):
		return {k: _mask(v, k) for k, v in value.items()}
	if isinstance(value, list):
		return [_mask(v, key) for v in value]
	return value


_users = {}


def _actor(user=None):
	"""Belgeyi değiştiren kişinin AD hesap adı (Destek kullanıcısının `username`'i), yoksa e-posta/kimlik."""
	user = user or getattr(frappe.session, "user", None) or "Guest"
	if user == "Guest":
		return None
	if user == "Administrator":
		# İstek içinde: yerel yönetici hesabıyla giren kişi. İstek dışında (zamanlayıcı, kuyruk): makinenin işi.
		return "Administrator" if getattr(frappe.local, "nb_audit_t0", None) else "ZEKİ AI"
	if user not in _users:
		try:
			_users[user] = frappe.db.get_value("User", user, "username") or user
		except Exception:
			_users[user] = user
	return _users[user]


def _put(event, commit=False):
	try:
		frappe.db.sql(f"INSERT INTO `{OUTBOX}` (`at`, `body`) VALUES (NOW(6), %s)",
					  (json.dumps(event, ensure_ascii=False, default=str),))
		if commit:
			frappe.db.commit()
	except Exception:
		# Kutu yoksa (ilk göçten önce) kurulur ve bir kez daha denenir; kayıt asıl işi hiçbir zaman durdurmaz.
		try:
			ensure_table()
			frappe.db.sql(f"INSERT INTO `{OUTBOX}` (`at`, `body`) VALUES (NOW(6), %s)",
						  (json.dumps(event, ensure_ascii=False, default=str),))
			if commit:
				frappe.db.commit()
		except Exception:
			frappe.logger("denetim").error("denetim olayı yazılamadı", exc_info=True)


def _rid():
	r = getattr(frappe.local, "nb_audit_rid", None)
	if not r:
		r = uuid.uuid4().hex
		frappe.local.nb_audit_rid = r
	return r


def _plain(doc):
	"""Belgenin JSON'a çevrilebilir tam hâli (alt tablolar dahil); parola alanları maskeli."""
	d = doc.as_dict(convert_dates_to_str=True, no_nulls=False)
	try:
		for f in doc.meta.get("fields", {"fieldtype": "Password"}):
			if d.get(f.fieldname):
				d[f.fieldname] = "«gizli»"
	except Exception:
		pass
	return _mask(d)


def _pk(doc):
	return {"doctype": doc.doctype, "name": doc.name}


def _row(doc, op, old=None, new=None, changed=None):
	if doc.doctype in SKIP or getattr(doc.flags, "nb_audit_skip", False):
		return
	_put({"type": "row", "id": uuid.uuid4().hex, "at": _now(), "actor": _actor(), "rid": _rid(), "table": doc.doctype,
		  "op": op, "pk": _pk(doc), "changed": changed, "old": old, "new": new})


# ------------------------------------------------------------------ belge olayları (hooks.doc_events "*")


def after_insert(doc, method=None):
	if doc.doctype == "Activity Log":
		return _activity(doc)
	_row(doc, "INSERT", new=_plain(doc))


def on_update(doc, method=None):
	before = doc.get_doc_before_save()
	if before is None:              # ekleme: after_insert yazdı
		return
	old, new = _plain(before), _plain(doc)
	changed = sorted(k for k in set(old) | set(new) if k not in _SYSTEM_FIELDS and old.get(k) != new.get(k))
	if not changed:
		return
	_row(doc, "UPDATE", old={k: old.get(k) for k in changed}, new={k: new.get(k) for k in changed}, changed=changed)


def on_trash(doc, method=None):
	_row(doc, "DELETE", old=_plain(doc))


def on_submit(doc, method=None):
	_action("submit", doc)


def on_cancel(doc, method=None):
	_action("cancel", doc)


def _action(action, doc):
	if doc.doctype in SKIP:
		return
	_put({"type": "action", "id": uuid.uuid4().hex, "at": _now(), "actor": _actor(), "rid": _rid(), "action": action,
		  "kind": "destek", "objectId": f"{doc.doctype}:{doc.name}", "title": f"{doc.doctype} · {doc.get_title() or doc.name}"})


def _activity(doc):
	"""Giriş/çıkış/başarısız giriş: Frappe'nin Activity Log'u."""
	op = (doc.get("operation") or doc.get("subject") or "").strip()
	status = (doc.get("status") or "").strip()
	action = "login" if op.lower() == "login" else "logout" if op.lower() == "logout" else (op.lower()[:16] or "run")
	if status and status.lower() != "success":
		action = "login_failed" if action == "login" else action
	_put({"type": "action", "id": f"act:{doc.name}", "at": _now(), "actor": _actor(doc.get("user")),
		  "action": action[:16], "kind": "oturum", "objectId": doc.get("user"),
		  "title": doc.get("subject") or op, "ip": doc.get("ip_address"),
		  "detail": {"status": status, "operation": op, "reference": doc.get("reference_name")}})


# ------------------------------------------------------------------ istek (hooks.after_request)


def istek(response=None, request=None):
	"""Her isteğin satırı. Asıl işlem bu noktada kaydedilmiş/geri alınmış olur; olay kendi başına kaydedilir."""
	try:
		req = request or getattr(frappe, "request", None)
		if req is None or SKIP_PATH.search(req.path or ""):
			return
		started = getattr(frappe.local, "nb_audit_t0", None)
		body = None
		ct = (req.headers.get("Content-Type") or "").lower()
		if req.method not in ("GET", "HEAD", "OPTIONS"):
			if "json" in ct:
				try:
					body = _mask(json.loads(req.get_data(as_text=True) or "null"))
				except Exception:
					body = req.get_data(as_text=True)
			elif "multipart" in ct:
				body = {"alanlar": _mask(dict(req.form)), "dosyalar": [f.filename for f in req.files.values()]}
			else:
				body = _mask(dict(req.form)) if req.form else (req.get_data(as_text=True) or None)
		ip = req.headers.get("X-Real-IP") or (req.headers.get("X-Forwarded-For") or "").split(",")[0].strip() or req.remote_addr
		status = getattr(response, "status_code", None)
		actor = _actor()
		_put({"type": "request", "id": _rid(), "rid": _rid(), "at": _now(), "actor": actor, "ip": ip,
			  "ua": req.headers.get("User-Agent"), "method": req.method, "path": req.path,
			  "query": req.query_string.decode("latin-1") if req.query_string else None,
			  "page": req.headers.get("Referer"), "status": status,
			  "ms": int((time.monotonic() - started) * 1000) if started else None,
			  "contentType": ct or None, "body": body,
			  "kind": ("denied" if status in (401, 403) else "error" if (status or 0) >= 500 else
					   ("read" if req.method in ("GET", "HEAD") else "write") if actor else "public")},
			 commit=True)
	except Exception:
		frappe.logger("denetim").error("istek kaydı yazılamadı", exc_info=True)


def istek_basi():
	"""before_request: süre ölçümü ve isteğin kimliği (aynı istekteki belge değişiklikleri bu kimliği taşır)."""
	frappe.local.nb_audit_t0 = time.monotonic()
	frappe.local.nb_audit_rid = uuid.uuid4().hex


# ------------------------------------------------------------------ merkeze gönderim (zamanlayıcı turu, 4 dk)

_BATCH_BYTES = 700_000       # nginx konumu 1 MB gövde kabul eder; parti boyudur, tavan değil (kutu boşalana kadar döner)


def ayarla():
	"""Kurulum: merkez adresi ve anahtar standart girişten (komut satırında görünmesin) site ayarına."""
	import sys

	from frappe.installer import update_site_config

	data = json.loads(sys.stdin.read())
	update_site_config("nb_audit_url", data["url"])
	update_site_config("nb_audit_key", data["key"])
	ensure_table()
	frappe.db.commit()
	print("denetim gönderimi ayarlandı")


def gonder():
	import requests

	url, key = frappe.conf.get("nb_audit_url"), frappe.conf.get("nb_audit_key")
	if not url or not key:
		return
	ensure_table()
	while True:
		rows = frappe.db.sql(f"SELECT `id`, `body` FROM `{OUTBOX}` ORDER BY `id` LIMIT 2000", as_dict=True)
		if not rows:
			return
		batch, size = [], 0
		for r in rows:
			if batch and size + len(r.body) > _BATCH_BYTES:
				break
			batch.append(r)
			size += len(r.body)
		events = []
		for r in batch:
			try:
				events.append(json.loads(r.body))
			except ValueError:
				events.append({"type": "action", "id": f"bozuk:{r.id}", "action": "run", "kind": "destek",
							   "title": "Okunamayan denetim olayı", "detail": {"ham": r.body[:4000]}})
		resp = requests.post(f"{url.rstrip('/')}/audit-ingest", json={"events": events},
							 headers={"Authorization": f"Bearer {key}"}, timeout=60)
		if resp.status_code != 200:
			frappe.logger("denetim").warning(f"merkez kabul etmedi: {resp.status_code} {resp.text[:300]}")
			return
		ids = [r.id for r in batch]
		frappe.db.sql(f"DELETE FROM `{OUTBOX}` WHERE `id` IN %(ids)s", {"ids": ids})
		frappe.db.commit()
