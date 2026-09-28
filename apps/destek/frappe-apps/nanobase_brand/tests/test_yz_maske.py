"""Destek masası: modele giden metnin kişisel veri maskesi ve model metnindeki sayı denetimi (çatısız birim testi).

Koşum (destek masası ayrı süreçtir; bu dosya çatıyı içe aktarmaz):
    python3 -m pytest apps/destek/frappe-apps/nanobase_brand/tests/test_yz_maske.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nanobase_brand.yz import sayi  # noqa: E402
from nanobase_brand.yz.maske import Maske, maskele  # noqa: E402


def test_contact_patterns_are_masked():
	t = ("Merhaba, siparişim gelmedi. E-posta: ayse.yilmaz@example.com, cep 0532 123 45 67, "
		 "TC 12345678901, IBAN TR12 0006 1005 1978 6457 8413 26, kart 4111 1111 1111 1111.")
	out = maskele(t)
	for secret in ("ayse.yilmaz@example.com", "0532 123 45 67", "12345678901", "TR12 0006", "4111 1111"):
		assert secret not in out
	for ph in ("[e-posta 1]", "[telefon 1]", "[kimlik no 1]", "[IBAN 1]", "[kart 1]"):
		assert ph in out
	assert "siparişim gelmedi" in out                 # konu kaybolmaz


def test_address_and_name_patterns():
	t = ("Sayın Ayşe Yılmaz,\nAdres: Cumhuriyet Mah. Atatürk Cad. No:12/3 Kadıköy İstanbul\n"
		 "Kargo Moda Mah. Bahariye Cad. No: 5 34710 adresine gelmedi. Mehmet Bey aradı.")
	out = maskele(t)
	assert "Ayşe Yılmaz" not in out and "Mehmet" not in out
	assert "Cumhuriyet Mah" not in out and "Bahariye" not in out
	assert "[adres 1]" in out and "[adres 2]" in out and "Adres:" in out
	assert "Bey aradı" in out and "adresine gelmedi" in out


def test_known_names_and_signature():
	m = Maske(["Deniz Kaya", "Deniz", "Kaya"])
	out = m("Deniz Kaya yazdı: deniz kenarındaki mağazadan aldım.\n\nSaygılarımla\nDeniz K.\nÖrnek Ltd")
	assert "Deniz Kaya" not in out and "Deniz K." not in out and "Örnek Ltd" not in out
	assert "deniz kenarındaki" in out                  # tek kelimelik ad küçük harfle kelimedir, maskelenmez
	assert "[ad 1]" in out and "[imza 1]" in out


def test_same_value_same_placeholder_and_restore():
	m = Maske(["Ali Veli"])
	a = m("Ali Veli ali@example.com yazdı")
	b = m("ALI@EXAMPLE.COM adresinden Ali Veli tekrar yazdı")          # harf farkı aynı değer
	assert a.count("[ad 1]") == 1 and "[ad 1]" in b and "[e-posta 1]" in a and "[e-posta 1]" in b
	draft = "Merhaba [ad 1], [e-posta 1] adresinize bilgi gönderdik."
	assert m.geri(draft) == "Merhaba Ali Veli, ali@example.com adresinize bilgi gönderdik."
	assert m.geri("[Ad 1] bey") == "Ali Veli bey"      # model harf büyüklüğünü değiştirse de dolar
	assert Maske.genel(draft) == "Merhaba [ad], [e-posta] adresinize bilgi gönderdik."
	assert m.adet >= 2


def test_order_numbers_and_plain_text_survive():
	out = maskele("Sipariş TS-240915 için 3 kitap eksik geldi, iade istiyorum.")
	assert out == "Sipariş TS-240915 için 3 kitap eksik geldi, iade istiyorum."


def test_numbers_must_come_from_facts():
	olgular = ["Açılan kayıt: 42", "Ortalama ilk yanıt: 3.5 saat", "Dönem 21.09.2026 – 28.09.2026"]
	assert sayi.olgu_disi_sayilar("Bu hafta 42 kayıt açıldı, ilk yanıt 3,5 saat.", olgular) == []
	assert sayi.olgu_disi_sayilar("28 Eylül itibarıyla durum iyi.", olgular) == []
	assert sayi.olgu_disi_sayilar("Kayıtlar %20 arttı.", olgular) == ["20"]
	assert sayi.olgu_disi_sayilar("[ad 7] üç kez yazdı.", olgular) == []   # yer tutucu numarası sayı değil


def test_weekly_comment_falls_back_to_rule_text():
	sayilar = {"Açılan kayıt": 12, "Önceki hafta açılan": 9, "SLA ihlali (bu hafta açılanlarda)": 2,
			   "Ortalama ilk yanıt": "1.5 saat"}
	dagilim = {"Tür": [("Kargo", 7), ("Fatura", 5)], "Ekip": [("(boş)", 4), ("Sipariş", 8)],
			   "Müşteri duygusu": [("Olumsuz", 3), ("Nötr", 9)]}
	olgular = sayi.haftalik_olgular(sayilar, dagilim)
	kural = sayi.haftalik_kural_yorumu(sayilar, dagilim)
	assert kural[0] == "Açılan kayıt geçen haftadan fazla: 9 → 12."
	assert "En çok kayıt açılan tür: Kargo (7)." in kural and "En çok kayıt alan ekip: Sipariş (8)." in kural
	assert any("2 tanesinde SLA" in k for k in kural) and any("kaydı: 3" in k for k in kural)
	assert sayi.olgu_disi_sayilar("\n".join(kural), olgular) == []     # kural metni de olgulardan

	ok, src, bad = sayi.yorum_sec("- Kargo kayıtları öne çıkıyor (7).\n- Fatura soruları için makale yazılmalı.", olgular, kural)
	assert src == "model" and bad == [] and ok[0].startswith("Kargo")
	lines, src, bad = sayi.yorum_sec("- Kargo şikâyetleri %40 arttı.\n- Fatura soruları azaldı.", olgular, kural)
	assert src == "kural" and bad == ["40"] and lines == kural         # yarım yorum bırakılmaz
	assert sayi.yorum_sec("", olgular, kural)[1] == "kural"
