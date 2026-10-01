"""Müşteri VM'inin GPU genel nginx'ine geldiği kaynak adresler — bütün yol betiklerinin tek listesi.

2026-09-25'te TİMAŞ'ın çıkışı 85.105.155.33'ten 212.156.126.250'ye geçti; adres o gün var olan yollara elle eklendi, ama
yol betikleri `allow 85.105.0.0/16;` satırını kendi içlerinde sabit yazdığı için sonradan kurulan 99 yol (stüdyo sayfa
düzeni, pazarlama, karakter kartı, e-kitap, kapak arşivi…) yeni adresi hiç almadı: VM'de bu ekranlar 403 alıyordu
(2026-09-29 ölçümü). Yeni adres buraya eklenir; betikler `ALLOW` ile yazar, mevcut yollar `allow-source-ip.py` ile
güncellenir.
"""
SOURCES = ("212.156.126.250/32", "85.105.0.0/16")
ALLOW = " ".join(f"allow {s};" for s in SOURCES) + " deny all;"
