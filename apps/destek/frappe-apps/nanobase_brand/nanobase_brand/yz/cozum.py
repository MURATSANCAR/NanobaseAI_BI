"""Otomatik çözüm önerisi ve BT'ye yönlendirme (2026-09-29 kullanıcı kararı).

Akış:
1. Yeni kayıt (sınıflamadan hemen sonra, `yeni_kayit`): geçmişte çözülmüş benzer kayıtlarda BT'nin uyguladığı
   çözümler bulunur (kayit._candidates + _applied: çözüm notu, BT yanıtları, iç notlar). Model önce olasılıkla karar
   verir: «bu çözüm bu talebe uyar ve kullanıcı adımları kendisi uygulayabilir mi?» (Evet olasılığı ≥ eşik). Geçerse
   YALNIZ o geçmiş çözümlere dayanan numaralı adımlar talep edene e-postayla gider, kayıt «yanıt bekleniyor» olur ve
   temsilciye iç not düşülür (kaynak kayıtlar, güven). Geçmezse ya da geçmiş çözüm yoksa kayıt BT ekibine atanır.
2. Talep edenin yanıtı (`yanit`): «çözüldü» → kayıt çözülür (çözüm notu: önerilen adımlar); «çözülmedi» ya da
   belirsiz → BT'ye atanır.
3. Yanıt gelmezse (`zaman_asimi`, saatlik): `nb_oneri_bekleme_saat` (vars. 4) saat sonra BT'ye atanır.
4. BT kaydı çözdüğünde çözüm notu boşsa (`ozet`): BT'nin yanıtlarından ve iç notlarından numaralı çözüm özeti
   çıkarılır; sonraki önerilerin kaynağı budur (temsilci ekranında ayrı bir çözüm alanı yok).

Uydurma yok: geçmiş çözüm yoksa öneri gitmez. Öneri e-postası `nb-otomatik-oneri` işaretini taşır; «BT'nin geçmiş
çözümü» toplanırken bu e-posta sayılmaz (kendi önerisinden öğrenmesin).
Ayarlar (site_config): nb_bt_ekibi (vars. «BT»), nb_oneri_min_p (0.80), nb_oneri_bekleme_saat (4),
nb_otomatik_oneri_kapali (1 → öneri gönderilmez, kayıt doğrudan BT'ye).
"""

from __future__ import annotations

import frappe
from frappe.utils import add_to_date, cint, escape_html, flt, now_datetime

from nanobase_brand.yz import kayit, llm

ISARET = "nb-otomatik-oneri"
GONDERILDI, COZULDU, COZULMEDI, BT = "Öneri gönderildi", "Öneriyle çözüldü", "Öneriyle çözülmedi", "BT'ye atandı"
DURUMLAR = ("", GONDERILDI, COZULDU, COZULMEDI, BT)

SISTEM = (
	"Sen NanobaseAI'sin, şirketin BT destek masasının asistanısın. Kendinden ve altyapıdan bahsetme, model ya da ürün "
	"adı verme. Yalnız verilen geçmiş çözümlere dayan; orada olmayan hiçbir adımı ekleme."
)


def _ayar(key: str, vars):
	return frappe.conf.get(key) if frappe.conf.get(key) not in (None, "") else vars


def bt_ekibi() -> str | None:
	"""BT ekibi (site ayarı `nb_bt_ekibi`); yoksa açılır. Üyeleri AD eşitlemesi ekler (yz/temsilci.py)."""
	ad = str(_ayar("nb_bt_ekibi", "BT"))
	if not frappe.db.exists("DocType", "HD Team"):
		return None
	if not frappe.db.exists("HD Team", ad):
		frappe.get_doc({"doctype": "HD Team", "team_name": ad}).insert(ignore_permissions=True)
	return ad


def _yorum(ticket: str, metin: str) -> None:
	try:
		frappe.get_doc({"doctype": "HD Ticket Comment", "reference_ticket": ticket, "commented_by": "Administrator",
						"content": f"<p>{escape_html(metin).replace(chr(10), '<br>')}</p>"}).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(title=f"NanobaseAI iç not yazılamadı: {ticket}")


def bt_ata(ticket: str, neden: str) -> None:
	"""Kaydı BT ekibine verir (ekibin atama kuralı bir temsilciye atar) ve nedenini iç not olarak yazar."""
	ekip = bt_ekibi()
	doc = frappe.get_doc("HD Ticket", ticket)
	doc.flags.ignore_permissions = True
	if ekip:
		doc.agent_group = ekip
	doc.nb_oneri_durumu = BT
	if doc.status in ("Replied", "Paused"):
		doc.status = "Open"
	try:
		doc.save()
	except Exception:
		# Atama kuralı çalışamazsa (ekipte temsilci yok) alanlar kancasız yazılır; kayıt yine ekibin kuyruğundadır.
		frappe.db.rollback()
		frappe.log_error(title=f"NanobaseAI BT ataması: atama kuralı çalışmadı ({ticket})")
		frappe.db.set_value("HD Ticket", ticket, {"agent_group": ekip, "nb_oneri_durumu": BT}, update_modified=False)
	_yorum(ticket, f"NanobaseAI: kayıt BT ekibine atandı — {neden}")
	frappe.db.commit()


def yeni_kayit(ticket: str) -> None:
	"""Yeni kaydın tek işi: sınıflama, sonra otomatik öneri ya da BT ataması. Hata kaydı BT'siz bırakmaz."""
	try:
		kayit.classify(ticket)
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title=f"NanobaseAI sınıflama: {ticket}")
	try:
		baslat(ticket)
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title=f"NanobaseAI otomatik öneri: {ticket}")
		bt_ata(ticket, "otomatik öneri hazırlanamadı")


def _kaynaklar(doc, limit: int = 8) -> list[dict]:
	"""Geçmiş çözülmüş benzer kayıtlar ve uygulanan çözüm (öneri e-postaları hariç)."""
	names, _how = kayit._candidates(doc, limit)
	out = []
	for name in names:
		yapilan = kayit._applied(name)
		if yapilan:
			out.append({"ad": str(name), "konu": frappe.db.get_value("HD Ticket", name, "subject") or "",
						"yapilan": yapilan})
	return out


def baslat(ticket: str) -> str:
	"""Öneri gönderir ya da BT'ye atar; ne yapıldığını döndürür."""
	doc = frappe.get_doc("HD Ticket", ticket)
	if doc.get("nb_oneri_durumu"):
		return "zaten işlendi"
	if cint(_ayar("nb_otomatik_oneri_kapali", 0)):
		bt_ata(ticket, "otomatik öneri kapalı")
		return "bt"
	kaynak = _kaynaklar(doc)
	if not kaynak:
		bt_ata(ticket, "benzer geçmiş çözüm bulunamadı")
		return "bt"

	m = kayit._maske(doc)
	talep = m(f"Konu: {doc.subject}\n\n{kayit._text(doc.description, 2500)}")
	gecmis = "\n\n".join(f"GEÇMİŞ KAYIT #{k['ad']} — {m(k['konu'])}\n{m(k['yapilan'])}" for k in kaynak)
	soru = (
		"Aşağıda yeni bir BT talebi ve BT'nin geçmişte benzer kayıtlarda uyguladığı çözümler var.\n"
		"Geçmiş çözümlerden biri bu yeni talebe GERÇEKTEN uyuyor mu ve talep eden kişi o çözümün adımlarını KENDİSİ "
		"uygulayabilir mi? (BT'nin sunucuda ya da yönetici hesabıyla yaptığı işler kullanıcıya uygulanamaz.)\n\n"
		f"YENİ TALEP:\n{talep}\n\n{gecmis}"
	)
	try:
		r = llm.choose(soru, ["Evet", "Hayır"], system=SISTEM, priority=llm.BACKGROUND)
	except llm.ModelUnavailable:
		bt_ata(ticket, "yapay zekâ şu an yanıt vermiyor")
		return "bt"
	p_evet = flt((r.get("probs") or {}).get("Evet"))
	esik = flt(_ayar("nb_oneri_min_p", 0.80))
	if r.get("choice") != "Evet" or p_evet < esik:
		bt_ata(ticket, f"geçmiş çözümler kullanıcının uygulayabileceği bir yol göstermiyor (uyma olasılığı %{round(p_evet * 100)}; "
					   f"eşik %{round(esik * 100)}; bakılan kayıtlar: {', '.join('#' + k['ad'] for k in kaynak)})")
		return "bt"

	istek = (
		"Talep edene gönderilecek adımları yaz.\n"
		"- YALNIZ geçmiş kayıtlardaki çözümlerde geçen, kullanıcının kendi yapabileceği adımlar; başka adım ekleme.\n"
		"- Numaralı, kısa, Türkçe; en çok 6 adım. Selamlama ve imza yazma.\n"
		"- Hangi geçmiş kayıtlara dayandığını da ver.\n"
		'Yalnız şu JSON\'u döndür: {"adimlar": ["...", "..."], "kaynak": ["<kayıt no>"]}\n\n'
		f"YENİ TALEP:\n{talep}\n\n{gecmis}"
	)
	try:
		out = llm.chat_json([{"role": "system", "content": SISTEM}, {"role": "user", "content": istek}],
							max_tokens=700, temperature=0.1, priority=llm.BACKGROUND)
	except (llm.ModelUnavailable, ValueError):
		out = None
	adimlar = [m.geri(str(a)).strip() for a in ((out or {}).get("adimlar") or []) if str(a).strip()][:6]
	kaynak_no = [str(x).lstrip("#") for x in ((out or {}).get("kaynak") or [])]
	gecerli = {k["ad"] for k in kaynak}
	kaynak_no = [k for k in kaynak_no if k in gecerli] or [kaynak[0]["ad"]]
	if not adimlar:
		bt_ata(ticket, "öneri adımları yazılamadı")
		return "bt"

	saat = cint(_ayar("nb_oneri_bekleme_saat", 4))
	liste = "".join(f"<li>{escape_html(a)}</li>" for a in adimlar)
	mesaj = (
		f'<div class="{ISARET}"><p>Merhaba,</p>'
		f"<p>Talebinizi aldık (#{escape_html(str(ticket))}). Benzer durumlarda BT ekibimiz sorunu şu adımlarla çözdü:</p>"
		f"<ol>{liste}</ol>"
		"<p>Bu adımlar sorunu çözdüyse bu e-postayı <b>«Çözüldü»</b> diye yanıtlamanız yeterli. Çözülmediyse "
		"<b>«Çözülmedi»</b> yazın; talebiniz hemen BT ekibine atanır. "
		f"{saat} saat içinde yanıt gelmezse de talebiniz BT ekibine iletilir.</p>"
		"<p>NanobaseAI Destek</p></div>"
	)
	yazar = frappe.session.user
	try:
		frappe.set_user("Administrator")
		frappe.get_doc("HD Ticket", ticket).reply_via_agent(message=mesaj, to=doc.raised_by)
	finally:
		frappe.set_user(yazar)
	# Kaydederek: «Replied» yanıt bekleyen durumdur, SLA çözüm süresi duraklar (doğrudan yazım SLA'yı atlardı).
	son = frappe.get_doc("HD Ticket", ticket)
	son.flags.ignore_permissions = True
	son.status = "Replied"
	son.nb_oneri_durumu = GONDERILDI
	son.nb_oneri_zamani = now_datetime()
	son.nb_oneri_not = f"Güven %{round(p_evet * 100)} · kaynak: {', '.join('#' + k for k in kaynak_no)}"
	son.save()
	_yorum(ticket, f"NanobaseAI talep edene çözüm önerisi gönderdi (güven %{round(p_evet * 100)}; kaynak kayıtlar: "
				   f"{', '.join('#' + k for k in kaynak_no)}). Yanıt «çözülmedi» olursa ya da {saat} saat içinde yanıt "
				   "gelmezse kayıt BT ekibine atanır.\n\nGönderilen adımlar:\n"
				   + "\n".join(f"{i + 1}. {a}" for i, a in enumerate(adimlar)))
	frappe.db.commit()
	return "öneri"


def yanit(ticket: str) -> str:
	"""Öneriden sonra gelen yanıt: çözüldüyse kapat, değilse BT'ye ata."""
	durum = frappe.db.get_value("HD Ticket", ticket, "nb_oneri_durumu")
	if durum != GONDERILDI:
		return "öneri beklenmiyor"
	son = frappe.get_all("Communication", filters={"reference_doctype": "HD Ticket", "reference_name": ticket,
												   "sent_or_received": "Received"},
						 fields=["content"], order_by="creation desc", limit=1)
	metin = _yeni_kisim(kayit._text(son[0].content, 3000)) if son else ""
	doc = frappe.get_doc("HD Ticket", ticket)
	m = kayit._maske(doc)
	try:
		r = llm.choose(
			"Kullanıcıya sorunu için adım adım bir çözüm önerisi gönderildi. Aşağıdaki yanıtına göre sorun çözüldü mü?\n\n"
			f"KULLANICININ YANITI:\n{m(metin)[:1500]}",
			["Çözüldü", "Çözülmedi", "Belirsiz"], system=SISTEM, priority=llm.BACKGROUND)
	except llm.ModelUnavailable:
		r = {}
	p = flt((r.get("probs") or {}).get("Çözüldü"))
	if r.get("choice") == "Çözüldü" and p >= flt(_ayar("nb_oneri_min_p", 0.80)):
		adim = frappe.db.get_value("HD Ticket Comment", {"reference_ticket": ticket, "content": ["like", "%çözüm önerisi gönderdi%"]},
								   "content", order_by="creation desc") or ""
		doc.flags.ignore_permissions = True
		doc.status = "Resolved"
		doc.nb_oneri_durumu = COZULDU
		if not doc.resolution_details:
			doc.resolution_details = "<p>Talep eden, NanobaseAI'nin geçmiş BT çözümlerinden önerdiği adımlarla sorunu çözdü.</p>" + adim
		doc.save()
		_yorum(ticket, f"NanobaseAI: talep eden sorunun önerilen adımlarla çözüldüğünü bildirdi (%{round(p * 100)}); kayıt çözüldü.")
		frappe.db.commit()
		return "çözüldü"
	bt_ata(ticket, "talep eden önerilen adımların sorunu çözmediğini bildirdi" if r.get("choice") == "Çözülmedi"
		   else "talep edenin yanıtından sorunun çözüldüğü anlaşılamadı")
	return "bt"


def _yeni_kisim(metin: str) -> str:
	"""E-posta yanıtında alıntılanan eski metni atar (> satırları, «... yazdı:» sonrası)."""
	satirlar = []
	for s in metin.splitlines():
		t = s.strip()
		if t.startswith(">") or t.endswith(("yazdı:", "wrote:")) or t.startswith(("From:", "Kimden:", "-----Original")):
			break
		satirlar.append(s)
	return "\n".join(satirlar).strip() or metin[:500]


def zaman_asimi() -> int:
	"""Saatlik: öneriye süresinde yanıt gelmeyen kayıtlar BT'ye."""
	saat = cint(_ayar("nb_oneri_bekleme_saat", 4))
	sinir = add_to_date(now_datetime(), hours=-saat)
	adlar = frappe.get_all("HD Ticket", filters={"nb_oneri_durumu": GONDERILDI, "nb_oneri_zamani": ["<", sinir]}, pluck="name")
	for ad in adlar:
		try:
			bt_ata(ad, f"öneriye {saat} saat içinde yanıt gelmedi")
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"NanobaseAI zaman aşımı ataması: {ad}")
	return len(adlar)


def ozet(ticket: str) -> str:
	"""BT kaydı çözdü, çözüm notu boş: BT'nin yanıtlarından ve iç notlarından numaralı çözüm özeti yazılır."""
	doc = frappe.get_doc("HD Ticket", ticket)
	if doc.resolution_details or doc.status not in ("Resolved", "Closed"):
		return "gerek yok"
	parcalar = []
	for c in frappe.get_all("Communication", filters={"reference_doctype": "HD Ticket", "reference_name": ticket},
							fields=["sent_or_received", "content"], order_by="creation"):
		if ISARET in (c.content or ""):
			continue
		kim = "BT" if c.sent_or_received == "Sent" else "Talep eden"
		parcalar.append(f"[{kim}] {kayit._text(c.content, 1200)}")
	for c in frappe.get_all("HD Ticket Comment", filters={"reference_ticket": ticket}, fields=["content", "commented_by"],
							order_by="creation"):
		if c.commented_by != "Administrator":
			parcalar.append(f"[BT iç not] {kayit._text(c.content, 600)}")
	if not any(p.startswith("[BT") for p in parcalar):
		return "BT yazışması yok"
	m = kayit._maske(doc)
	istek = (
		"Aşağıdaki çözülmüş BT kaydında sorunun NASIL çözüldüğünü, benzer talepte tekrar uygulanabilecek numaralı "
		"adımlar olarak yaz. Yalnız yazışmada geçenlere dayan; BT'nin sunucuda/yönetici hesabıyla yaptığını "
		"«(BT yaptı)» diye belirt. Türkçe, en çok 8 adım, başka açıklama yazma.\n\n"
		f"KONU: {m(doc.subject)}\n\n" + m("\n".join(parcalar))[:6000]
	)
	try:
		metin = m.geri(llm.chat([{"role": "system", "content": SISTEM}, {"role": "user", "content": istek}],
							   max_tokens=600, temperature=0.1, priority=llm.BACKGROUND)).strip()
	except llm.ModelUnavailable:
		return "model yok"
	if not metin:
		return "boş"
	frappe.db.set_value("HD Ticket", ticket, "resolution_details",
						"".join(f"<p>{escape_html(s)}</p>" for s in metin.splitlines() if s.strip()),
						update_modified=False)
	frappe.db.commit()
	try:
		from nanobase_brand.yz.bilgi import source_name

		kaynak = source_name("Çözülen kayıtlar")
		if kaynak:
			frappe.enqueue("flow.knowledge.ingest.ingest_source", source=kaynak, queue="long",
						   job_id="nb-bilgi-cozulen-kayitlar", deduplicate=True)
	except Exception:
		pass
	return "özet yazıldı"
