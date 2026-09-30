"""BT talep kategorileri (2026-09-29 kullanıcı: «tüm sistemi analiz et, BT tarafına gidecek kategorileri oluştur»).

Kategoriler Timaş'ın kullandığı sistemlerden ve birimlerden çıkarıldı: Active Directory hesapları, Google e-posta ve
Drive, Logo (muhasebe, stok, fatura), CRM (kitap, yazar, proje kartları), Zeki AI portalı, e-ticaret sitesi ve pazar
yerleri, VPN ile uzaktan erişim, yazıcı ve telefon (dahili hat), toplantı odaları, ortak klasörler. Kayıt türü
(HD Ticket Type) olarak açılır; açıklama hem yöneticiye hem sınıflamaya (modele giden soruya) gider.

Şirket içinden gelen talep (AD'de birimi bulunan kişi) bu listeden sınıflanır; dışarıdan gelen müşteri talebi
müşteri hizmetleri konu listesiyle (sinif.konu, köprü) sınıflanır.
"""

from __future__ import annotations

import frappe

KATEGORILER: list[tuple[str, str]] = [
	("Hesap ve Şifre", "Bilgisayara ya da Windows'a giriş yapamama, şifre unutma veya sıfırlama, hesap kilitlenmesi, "
					   "iki adımlı doğrulama, e-posta hesabına girememe."),
	("Yetki ve Erişim", "Klasöre, uygulamaya, rapora ya da sisteme erişim veya yetki talebi, yetki kaldırma, yeni "
						"çalışan için hesap açılışı, ayrılan çalışanın hesabının kapatılması."),
	("E-posta ve Takvim", "E-posta gönderememe ya da alamama, paylaşılan posta kutusu, imza, takvim ve toplantı daveti, "
						  "Google Drive dosya ve klasör paylaşımı."),
	("Bilgisayar ve Donanım", "Bilgisayar açılmıyor, donuyor veya yavaş; monitör, klavye, fare, pil, şarj, bağlantı "
							  "noktası arızası; yeni cihaz ya da parça talebi; el terminali ve barkod okuyucu."),
	("Yazıcı ve Tarayıcı", "Çıktı alamama, kuyrukta bekleyen yazdırma işi, kâğıt sıkışması, toner, tarama ve "
						   "fotokopi sorunu, yazıcı ekleme."),
	("Ağ, İnternet ve VPN", "İnternet yok ya da yavaş, kablosuz ağ, ağ kablosu, uzaktan bağlantı (VPN), şirket "
							"sunucusuna veya ortak sürücüye erişememe."),
	("Telefon ve Dahili Hat", "Masa telefonu, dahili numara, yönlendirme, şirket cep hattı ve telefonu."),
	("Yazılım Kurulumu ve Lisans", "Program kurulumu, güncellemesi veya kaldırılması, lisans ve etkinleştirme, ofis "
								   "programları, genel uygulama hatası."),
	("Logo (Muhasebe ve Stok)", "Logo'da fatura, irsaliye, cari hesap, stok kartı, muhasebe fişi, rapor ya da ekran "
								"hatası; Logo'ya giriş sorunu."),
	("CRM", "CRM'de kitap, yazar, proje veya sözleşme kaydı, ekran ve rapor hatası, CRM'e giriş ya da yetki sorunu."),
	("Zeki AI Portalı", "Portal girişi, raporlar, panolar, planlı raporlar, uyarılar, Zeki AI sohbeti, ekranda "
						"yanlış ya da eksik görünen veri."),
	("E-ticaret ve Web Sitesi", "Web sitesi, e-ticaret yönetim paneli, pazar yeri entegrasyonları, ürün, fiyat ve "
								"stok aktarımı, sipariş aktarım hatası."),
	("Dosya Paylaşımı ve Yedek", "Ortak klasör, silinen ya da kaybolan dosya, yedekten geri yükleme, depolama alanı "
								 "dolması."),
	("Bilgi Güvenliği", "Virüs veya kötü amaçlı yazılım şüphesi, şüpheli e-posta ve oltalama, hesabın başkası "
						"tarafından kullanılması, veri sızıntısı şüphesi."),
	("Toplantı Odası ve Sunum", "Projeksiyon, ekran paylaşımı, video konferans, toplantı odası ekranı ve ses "
								"donanımı."),
	("Diğer", "Yukarıdaki kategorilerin hiçbirine uymayan talepler."),
]
# Kurulumla gelen İngilizce örnek türler: hiçbir kayıt kullanmıyorsa kaldırılır (talep formunda karışıklık olmasın).
ORNEK_TURLER = ("Incident", "Bug", "Question")


def ensure() -> None:
	if not frappe.db.exists("DocType", "HD Ticket Type"):
		return
	for ad, aciklama in KATEGORILER:
		if frappe.db.exists("HD Ticket Type", ad):
			if frappe.db.get_value("HD Ticket Type", ad, "description") != aciklama:
				frappe.db.set_value("HD Ticket Type", ad, "description", aciklama)
		else:
			frappe.get_doc({"doctype": "HD Ticket Type", "name": ad, "description": aciklama}).insert(
				ignore_permissions=True)
	varsayilan = frappe.db.get_single_value("HD Settings", "default_ticket_type")
	for ad in ORNEK_TURLER:
		if frappe.db.exists("HD Ticket Type", ad) and ad != varsayilan \
				and not frappe.db.exists("HD Ticket", {"ticket_type": ad}):
			try:
				frappe.delete_doc("HD Ticket Type", ad, ignore_permissions=True)
			except (frappe.LinkExistsError, frappe.ValidationError):
				pass
	frappe.db.commit()


def adlar() -> list[str]:
	return [ad for ad, _ in KATEGORILER if frappe.db.exists("HD Ticket Type", ad)]


def soru_metni() -> str:
	return "\n".join(f"- {ad}: {aciklama}" for ad, aciklama in KATEGORILER)
