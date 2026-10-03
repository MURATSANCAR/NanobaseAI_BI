"""Yönetim: sistem ayarları, herkesin tanımları ve değişiklik kaydı.

Ayar önceliği: yönetim ekranında kaydedilen değer > servis ortam dosyası (`/etc/nanobase/semantic-bridge.env`)
> varsayılan. Böylece SMTP gibi ayarlar sunucuya girmeden ekrandan verilir; ekrandan silinen ayar ortam
dosyasındaki değere döner. Gizli değerler (parola) hiçbir uçtan geri dönmez, kayıtta da yalnız "değişti" yazar.

Değişiklik kaydı (`semantic_audit`) kim, ne zaman, neyi oluşturdu/güncelledi/sildi/çalıştırdı sorusunun
cevabıdır. Kayıt yazılamazsa asıl işlem durmaz; kayıt bir yan üründür, kapı değil.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import smtplib
import ssl
import threading
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any, Callable, Optional

import sqlalchemy as sa

log = logging.getLogger(__name__)

_md = sa.MetaData()

SETTINGS = sa.Table(
    "semantic_settings", _md,
    sa.Column("key", sa.String(80), primary_key=True),
    sa.Column("value", sa.Text, nullable=False),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

AUDIT = sa.Table(
    "semantic_audit", _md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("at", sa.DateTime(timezone=True), nullable=False, index=True),
    sa.Column("actor", sa.String(120), nullable=False, index=True),
    sa.Column("action", sa.String(16), nullable=False),
    sa.Column("kind", sa.String(24), nullable=False, index=True),
    sa.Column("object_id", sa.String(120)),
    sa.Column("title", sa.String(300)),
    sa.Column("detail", sa.Text),
    # Denetim izi (audit_trail.py): aynı isteğin kimliği, IP'si, tarayıcısı ve ekranı; mühür. Kolonlar sonradan
    # eklendi (ALTER … IF NOT EXISTS, audit_trail.ensure).
    sa.Column("rid", sa.String(32), index=True),
    sa.Column("ip", sa.String(64)),
    sa.Column("ua", sa.Text),
    sa.Column("page", sa.Text),
    sa.Column("seal_seq", sa.BigInteger),
    sa.Column("seal", sa.String(64)),
    sa.Column("source", sa.String(24)),             # boş = portal; sohbet, destek, editor (merkezi denetim kaydı)
    sa.Column("ext_id", sa.String(120)),
)

#: Yönetici AD grubunun üyelerinin kalıcı anlık görüntüsü. Yetki kontrolü (is_admin) bunu okur;
#: canlı AD her istekte okunmaz. 15 dk'lık timer `refresh_admin_group` ile tazelenir.
GROUP_CACHE = sa.Table(
    "semantic_admin_group", _md,
    sa.Column("group_name", sa.String(200), primary_key=True),
    sa.Column("members", sa.Text, nullable=False),   # JSON: küçük harf sAMAccountName listesi
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("error", sa.Text),                      # son tazeleme hatası (varsa); üyeler korunur
)

#: Ekrandan yönetilen ayarlar. `env` servis dosyasındaki adıdır; ekran değeri yoksa oradan okunur.
SPEC: list[dict[str, Any]] = [
    # E-posta
    {"key": "ALERT_SMTP_HOST", "group": "email", "label": "SMTP sunucusu", "type": "text", "default": "",
     "help": "Örn. smtp.office365.com ya da mail.timas.com.tr"},
    {"key": "ALERT_SMTP_PORT", "group": "email", "label": "Port", "type": "int", "default": "587",
     "help": "587 (STARTTLS) ya da 465 (SSL)"},
    {"key": "ALERT_SMTP_USER", "group": "email", "label": "Kullanıcı adı", "type": "text", "default": "",
     "help": "Gönderici hesabın oturum adı; sunucu kimlik istemiyorsa boş"},
    {"key": "ALERT_SMTP_PASSWORD", "group": "email", "label": "Parola", "type": "secret", "default": "",
     "help": "Kaydedilen parola ekranda bir daha gösterilmez"},
    {"key": "ALERT_SMTP_FROM", "group": "email", "label": "Gönderen adresi", "type": "email", "default": "",
     "help": "Boşsa kullanıcı adı kullanılır"},
    {"key": "ALERT_SMTP_SSL", "group": "email", "label": "Doğrudan SSL (465)", "type": "bool", "default": "0", "help": ""},
    {"key": "ALERT_SMTP_STARTTLS", "group": "email", "label": "STARTTLS", "type": "bool", "default": "1",
     "help": "SSL kapalıyken bağlantıyı şifreler"},
    {"key": "ALERT_RECIPIENT_DOMAINS", "group": "email", "label": "İzinli alıcı alan adları", "type": "text", "default": "",
     "help": "Virgülle, örn. timas.com.tr. Boşsa her adrese gönderilir"},
    # Bildirim ve raporlar
    {"key": "ALERT_LINK", "group": "delivery", "label": "E-postadaki bağlantı", "type": "text",
     "default": "", "help": "Uyarı ve rapor e-postalarının sonuna eklenen adres"},
    {"key": "CRM_UNASSIGNED_TO", "group": "delivery", "label": "Departmansız CRM kullanıcıları listesi alıcıları",
     "type": "text", "default": "",
     "help": "Virgülle e-posta adresleri. CRM'de departmana atanmamış kullanıcıların Excel listesi her gün 07:00 ve 12:00'de gider; boşsa gönderilmez"},
    {"key": "ALERT_REMIND_HOURS", "group": "delivery", "label": "Uyarı hatırlatma (saat)", "type": "int", "default": "24",
     "help": "Eşik aşılmaya devam ederse kaç saat sonra yeniden bildirilir"},
    {"key": "REPORT_KEEP_FILES", "group": "delivery", "label": "Rapor başına saklanan dosya", "type": "int", "default": "10",
     "help": "Eski dosyalar bu sayıdan sonra silinir"},
    {"key": "REPORT_CHANGE_NOTE", "group": "delivery", "label": "Rapor e-postasında «ne değişti» yorumu", "type": "bool", "default": "1",
     "help": "Önceki rapora göre fark kodla bulunur; açıksa Zeki AI madde madde anlatır (sayı denetimli), kapalıysa kural maddeleri yazılır"},
    {"key": "ALERT_RANGE_K", "group": "delivery", "label": "Beklenen aralık genişliği (k)", "type": "text", "default": "2",
     "help": "Uyarılarda beklenen aralık = medyan ± k × yayılım (1,4826 × MAD). Büyük k daha az uyarı"},
    {"key": "BUDGET_ALERT_RECIPIENTS", "group": "delivery", "label": "Bütçe uyarısı alıcıları", "type": "text", "default": "",
     "help": "Virgülle e-posta adresleri. Satış hedefinin eşik altına düşmesi ve departman bütçesi aşımı özetle gider"},
    {"key": "FINANCE_SUMMARY_RECIPIENTS", "group": "delivery", "label": "Finansal sabah özeti alıcıları", "type": "text", "default": "",
     "help": "Virgülle e-posta adresleri (mali işler, genel müdür). İş günü 08:30'dan sonra özet kartlar ve «bu ay dikkat» listesi; ek dosya yok"},
    {"key": "FINANCE_TAX_RECIPIENTS", "group": "delivery", "label": "Vergi takvimi hatırlatması alıcıları", "type": "text", "default": "",
     "help": "Virgülle muhasebe e-posta adresleri. Beyanın son gününe 7 ve 2 gün kala hatırlatma"},
    {"key": "DIST_ALERT_RECIPIENTS", "group": "delivery", "label": "İlk dağılım uyarısı alıcıları", "type": "text", "default": "",
     "help": "Virgülle iç ekip e-posta adresleri (satış, lojistik). Plansız kitap, sevk gecikmesi, hiç satmayan bölge özetle gider; müşteriye gönderim yok"},
    {"key": "TENDER_ALERT_RECIPIENTS", "group": "delivery", "label": "İhale hatırlatması alıcıları", "type": "text", "default": "",
     "help": "Virgülle iç ekip e-posta adresleri (ihale sorumlusu, finans). Son teklif tarihi, belge geçerliliği, teminat iadesi ve onay bekleyen karar her sabah tek özetle gider; kuruma gönderim yok"},
    {"key": "SUPPLY_ALERT_RECIPIENTS", "group": "delivery", "label": "Baskı yükü uyarısı alıcıları", "type": "text", "default": "",
     "help": "Virgülle iç ekip e-posta adresleri (prodüksiyon). Ay × matbaa eşik aşımı ve yeni yük dengeleme önerisi gece özetle gider; matbaaya gönderim yok"},
    {"key": "SUPPLY_PAYMENT_RECIPIENTS", "group": "delivery", "label": "Matbaa/kağıtçı ödeme listesi alıcıları", "type": "text", "default": "",
     "help": "Virgülle iç ekip e-posta adresleri (finans). Her pazartesi 08:00 önümüzdeki 30 günün ödemeleri (FIFO yaklaşımı) gider"},
    {"key": "TENDER_WATCH_ENABLED", "group": "delivery", "label": "İhale ilanı içe alma", "type": "bool", "default": "0",
     "help": "Resmî kaynaktan ilan içe alma (ikinci sürüm). Kapalıyken ilanlar elle ya da dosyayla girilir; müşteri ortamında kullanıcı kararı olmadan açılmaz"},
    {"key": "TENDER_PRICE_SOURCE", "group": "delivery", "label": "İhale teklifinde liste fiyatı", "type": "text", "default": "crm",
     "help": "crm = CRM KDV dahil liste fiyatı, logo = Logo geçerli satış fiyat listesi. Hangisi kullanıldığı teklif tablosunda yazar"},
    {"key": "TENDER_DEFAULT_VAT", "group": "delivery", "label": "İhale: varsayılan KDV oranı", "type": "text", "default": "0",
     "help": "CRM kitap kartında KDV oranı yoksa kullanılır; oran olarak (0,10 = %10)"},
    # Serbest not sinyali (öneri 16): M30/M59/M38 notları + CRM ziyaret açıklaması; yalnız bilgi, skora girmez
    {"key": "NOT_SINYALI_MIN_OLASILIK", "group": "crm", "label": "Not sinyali: en düşük olasılık", "type": "text", "default": "0.60",
     "help": "Zeki AI'ın not etiketi bu olasılığın altındaysa etiket boş kalır («belirsiz»)"},
    {"key": "NOT_SINYALI_MIN_FARK", "group": "crm", "label": "Not sinyali: en düşük fark", "type": "text", "default": "0.20",
     "help": "Seçilen etiketle ikinci en olası etiket arasındaki en düşük olasılık farkı"},
    {"key": "NOT_SINYALI_GUN", "group": "crm", "label": "Not sinyali sayım penceresi (gün)", "type": "int", "default": "90",
     "help": "Cari ekranındaki etiket sayıları bu kadar günlük notlardan"},
    {"key": "NOT_SINYALI_CRM_GUN", "group": "crm", "label": "Not sinyali: CRM ziyaret geçmişi (gün)", "type": "int", "default": "365",
     "help": "CRM ziyaret açıklamaları bu kadar gün geriye okunur (CRM ziyaret–cari kolonu tanımlıysa)"},
    {"key": "NOT_SINYALI_MODEL_SURE_SN", "group": "crm", "label": "Not sinyali gece model süresi (sn)", "type": "int",
     "default": "1200", "help": "Gece turunda özet yazımına ayrılan süre; kalan cariler sonraki gece yazılır"},
    {"key": "BUGUN_SLA_SAAT", "group": "mailbox", "label": "Kampüs «Bugün»: yaklaşan yanıt süresi (saat)", "type": "text",
     "default": "4", "help": "Bana atanmış e-postanın ilk yanıt süresi bu kadar saat içinde doluyorsa «Bugün» özetinde öne çıkar"},
    {"key": "DEALERS_MORNING_RECIPIENTS", "group": "delivery", "label": "Bayi riski sabah özeti alıcıları", "type": "text", "default": "",
     "help": "Virgülle iç ekip e-posta adresleri (satış müdürü, finans). Her sabah segmenti düşen bayiler, vadesi geçmiş ve onay bekleyen limit önerileri; bayiye gönderim yok"},
    {"key": "RISK_ALERT_RECIPIENTS", "group": "delivery", "label": "Risk ve uyum özeti alıcıları", "type": "text", "default": "",
     "help": "Virgülle risk ve uyum koordinatörünün adresleri. Kırmızıya dönen gösterge, aksiyon termini, gözden geçirme, uyum son günü ve poliçe bitişi her sabah tek özetle gider"},
    {"key": "RISK_CRITICAL_RECIPIENTS", "group": "delivery", "label": "Kritik risk alıcıları", "type": "text", "default": "",
     "help": "Virgülle adresler (genel müdür). Etkisi kritik (5) bir riske bağlı gösterge kırmızıya dönünce aynı gün gider"},
    # Toplantı odaları
    {"key": "ROOM_DAY_START", "group": "rooms", "label": "Takvim başlangıcı", "type": "time", "default": "08:00",
     "help": "Oda takviminin ilk saati, SS:DD"},
    {"key": "ROOM_DAY_END", "group": "rooms", "label": "Takvim bitişi", "type": "time", "default": "20:00",
     "help": "Oda takviminin son saati, SS:DD (24:00 gece yarısı)"},
    {"key": "ROOM_SLOT_MINUTES", "group": "rooms", "label": "Saat adımı (dakika)", "type": "int", "default": "30",
     "help": "Takvimdeki en küçük aralık: 15, 30 ya da 60"},
    # Active Directory (giriş). Değerler giriş servisinin dosyasında tutulur (`file`), veritabanında değil;
    # timas-login her girişte dosyayı yeniden okur, kaydedilen değer hemen geçerli olur.
    {"key": "AD_HOST", "group": "directory", "label": "Etki alanı denetleyicisi", "type": "text", "default": "",
     "help": "Sunucu adı ya da IP, örn. 192.168.0.20", "file": "host"},
    {"key": "AD_PORT", "group": "directory", "label": "Port", "type": "int", "default": "389",
     "help": "389 (LDAP, NTLM ile)", "file": "port"},
    {"key": "AD_NETBIOS", "group": "directory", "label": "NetBIOS alan adı", "type": "text", "default": "",
     "help": "Örn. TIMAS; giriş TIMAS\\kullanici biçiminde yapılır", "file": "netbios"},
    {"key": "AD_DNS_DOMAIN", "group": "directory", "label": "DNS alan adı", "type": "text", "default": "",
     "help": "Örn. timas.local; kullanici@timas.local biçimi de kabul edilir", "file": "dns_domain"},
    {"key": "AD_BASE_DN", "group": "directory", "label": "Arama kökü (Base DN)", "type": "text", "default": "",
     "help": "Örn. DC=timas,DC=local", "file": "base_dn"},
    {"key": "AD_BIND_USER", "group": "directory", "label": "Servis hesabı", "type": "text", "default": "",
     "help": "Kullanıcıları arayan hesap, alan adı olmadan", "file": "bind_user"},
    {"key": "AD_BIND_PASSWORD", "group": "directory", "label": "Servis hesabı parolası", "type": "secret", "default": "",
     "help": "Kaydedilen parola ekranda bir daha gösterilmez", "file": "bind_password"},
    # Logo veritabanı. Değerler köprünün bağlantı dosyasında (`SEMANTIC_CONNECTION_FILE`) tutulur;
    # kaydedilince bağlantı yeniden kurulur, servis yeniden başlatılmaz.
    {"key": "DB_HOST", "group": "database", "label": "Sunucu", "type": "text", "default": "",
     "help": "SQL Server adresi, ağın içindeki gerçek adres (örn. 192.168.0.25)", "file": "host", "store": "db"},
    {"key": "DB_PORT", "group": "database", "label": "Port", "type": "int", "default": "1433",
     "help": "SQL Server portu, genellikle 1433", "file": "port", "store": "db"},
    {"key": "DB_NAME", "group": "database", "label": "Veritabanı", "type": "text", "default": "",
     "help": "Logo veritabanı, örn. LOGO_DB", "file": "database", "store": "db"},
    {"key": "DB_USER", "group": "database", "label": "Kullanıcı", "type": "text", "default": "",
     "help": "Salt okunur hesap. Etki alanı hesabı ise ALAN\\kullanici", "file": "user", "store": "db"},
    {"key": "DB_PASSWORD", "group": "database", "label": "Parola", "type": "secret", "default": "",
     "help": "Kaydedilen parola ekranda bir daha gösterilmez", "file": "password", "store": "db"},
    {"key": "DB_DRIVER", "group": "database", "label": "ODBC sürücüsü", "type": "text", "default": "FreeTDS",
     "help": "Sunucuda kayıtlı sürücü adı (odbcinst -q -d)", "file": "driver", "store": "db"},
    {"key": "DB_TDS_VERSION", "group": "database", "label": "TDS sürümü", "type": "text", "default": "7.4",
     "help": "FreeTDS için; SQL Server 2012+ ile 7.4", "file": "tds_version", "store": "db"},
    # CRM: artık ayrı bir sunucu (.28 prod). Tabloları şemalarında veritabanı adını taşır
    # (Timas_MSCRM.dbo); katalog bu adla tutar, köprü _conn_for ile .28 connectorune yönlendirir.
    {"key": "CRM_SCHEMA", "group": "crm", "label": "CRM şeması", "type": "text", "default": "Timas_MSCRM.dbo",
     "help": "veritabanı.şema biçiminde, örn. Timas_MSCRM.dbo. Boşsa CRM okunmaz"},
    # Yazar giriş süreci (editoryal): hangi projeler izlenir, ne zaman gecikmiş sayılır.
    {"key": "EDITORIAL_INTAKE_SINCE", "group": "crm", "label": "Yazar giriş süreci başlangıcı", "type": "text", "default": "2025-01-01",
     "help": "Bu tarihten sonra CRM'de açılan yeni ve yenileme projeleri süreç panosunda izlenir (YYYY-AA-GG)"},
    {"key": "RESPONSE_CACHE_ENABLED", "group": "performance", "label": "Yavaş ekranlarda hazır cevap", "type": "bool", "default": "1",
     "help": "Açıkken kaynağı 1,5 sn'den uzun bekleten ekran verisi hazır tutulur: ekran anında açılır, veri 5 dakikada bir ve «Yenile» ile tazelenir; bir modülde kayıt yapılınca o modülün hazır cevapları düşer"},
    {"key": "LOGO_MAX_CONCURRENT", "group": "performance", "label": "Logo'ya aynı anda giden sorgu", "type": "int", "default": "4",
     "help": "Ekranlar, Zeki AI ve arka planda tazelenen ekran verisi Logo sunucusuna aynı anda en çok bu kadar sorgu gönderir (en az 1). Dolunca yeni sorgu geliş sırasıyla bekler, düşürülmez. Logo canlı sistemdir: artırmadan önce sunucu yükü ölçülmeli"},
    {"key": "CRM_MAX_CONCURRENT", "group": "performance", "label": "CRM'e aynı anda giden sorgu", "type": "int", "default": "4",
     "help": "Ekranlar, Zeki AI ve arka planda tazelenen ekran verisi CRM sunucusuna aynı anda en çok bu kadar sorgu gönderir (en az 1). Dolunca yeni sorgu geliş sırasıyla bekler, düşürülmez"},
    {"key": "AUTHOR_REMINDERS_ENABLED", "group": "crm", "label": "Yazar ilişkileri sabah özeti", "type": "bool", "default": "1",
     "help": "Açıkken kişiye her sabah bugün/yarınki randevular, notu girilmemiş randevular ve geciken adımlar e-postayla gider (yalnız yayınevi içi; kişi kendi ekranından kapatabilir)"},
    {"key": "AUTHOR_REMINDER_TIME", "group": "crm", "label": "Sabah özeti saati", "type": "text", "default": "08:15",
     "help": "Özet günün bu saatinden sonraki ilk turda gider (SS:DD, İstanbul saati); kişi başına günde bir kez"},
    {"key": "AUTHOR_POOL_SINCE", "group": "crm", "label": "Aday havuzu başlangıcı", "type": "text", "default": "2024-01-01",
     "help": "Bu tarihten sonra CRM'de açılan projelerin olası yazarları (henüz yazar rolüyle eseri yoksa) aday havuzunda listelenir (YYYY-AA-GG)"},
    {"key": "WEB_WATCH_ENABLED", "group": "crm", "label": "Basın ve web taraması", "type": "bool", "default": "0",
     "help": "Açıkken yazarlar ve kitapları haber akışlarında, sözlükte ve açık bilgi tabanında her gece taranır. Müşteri ortamında kapalı (2026-09-24 kararı)"},
    # ZEKI-26 (kullanıcı kararı 2026-09-30): yükleme akışlıdır ama PDF okunurken bellek dosya boyuyla büyür (test sunucusu:
    # 300 MB → ~0,6 GB, 1 GB → ~2,7 GB); müşteri VM'inde 7 GB bellek var. Sınır büyük ama VM'i zorlamayan bir değer.
    {"key": "EDITORIAL_UPLOAD_MAX_MB", "group": "crm", "label": "Kitap/belge yükleme üst sınırı (MB)", "type": "int", "default": "300",
     "help": "Redaksiyon, Son Okuma ve Çeviri'ye yüklenen tek dosyanın en büyük boyutu. Büyük PDF okunurken sunucu belleği dosya "
             "boyutuyla artar; sunucunun belleğine göre ayarlayın. 0 = sınır yok"},
    {"key": "EDITORIAL_INTAKE_LATE_DAYS", "group": "crm", "label": "Gecikme sınırı (gün)", "type": "int", "default": "14",
     "help": "Bir adım bu kadar günden uzun beklerse panoda gecikti olarak işaretlenir"},
    # Yayın kurulu: toplam karar skoru (misyon, yayıncılık, ticari puanların ortalaması) → skor önerisi.
    {"key": "BASVURU_FORM_SHEETS", "group": "basvuru_form", "label": "Yazar başvuru formu yanıt tabloları",
     "type": "text",
     # 2026-09-29: TİMAŞ'ın üç yaş grubu formu (Çocuk 0-9, Genç 11-14, İlk Gençlik 9-11), sahibi basvuru@timas.com.tr.
     "default": "1wME0i1A8aVoMHfP_w-qnn6nwssM7i0CbSbD67m5uvEM 1yAvMQXw9_U5ZwMABMUJ1OYndM4Avh9V_xV4GdDQ3cQ0 "
                "1Berv8Cy09X3r7WlSQtoD5oKlXE6tHPs-Cy62-VGFgqA",
     "help": "Google E-Tablo bağlantıları ya da kimlikleri, boşluk ya da satırla ayrılmış. Her tablo "
             "zeki-seo servis hesabıyla Görüntüleyici olarak paylaşılmalı. Yanıtlar 15 dakikada bir okunur, her yanıt bir "
             "kez Başvurular'a düşer; tablolara hiçbir şey yazılmaz."},
    {"key": "EDITORIAL_BOARD_ACCEPT_SCORE", "group": "crm", "label": "Kurul: kabul skoru", "type": "int", "default": "70",
     "help": "Üyelerin ortalama toplam karar skoru bu değer ve üstündeyse skor önerisi «Kabul» olur (0–100)"},
    {"key": "EDITORIAL_BOARD_REVISE_SCORE", "group": "crm", "label": "Kurul: revizyon skoru", "type": "int", "default": "50",
     "help": "Kabul skorunun altında, bu değer ve üstündeyse öneri «Revizyon», altındaysa «Red» olur (0–100)"},
    # H1 Kategori ağacı: öneri eşikleri (golden set ile ölçülecek), taslak ağaç ve öncelik ayarları.
    {"key": "CATEGORY_SUGGEST_MIN_PROB", "group": "crm", "label": "Kategori önerisi: en düşük olasılık", "type": "text",
     "default": "0.70", "help": "Zeki AI önerisi bu olasılığın altındaysa «emin değil» işaretlenir, toplu onayla kabul edilmez (0–1)"},
    {"key": "CATEGORY_SUGGEST_MIN_MARGIN", "group": "crm", "label": "Kategori önerisi: en düşük fark", "type": "text",
     "default": "0.30", "help": "Seçilen ile ikinci seçenek arasındaki olasılık farkı bunun altındaysa «emin değil» (0–1)"},
    {"key": "CATEGORY_TREE_MIN_BOOKS", "group": "crm", "label": "Taslak ağaçta düğüm için en az kitap", "type": "int",
     "default": "3", "help": "Veriden taslak ağaç önerisinde bir düğüm en az bu kadar aktif kitapla açılır; kalanlar profil önerisiyle yerleşir"},
    {"key": "CATEGORY_MAP_MIN_SHARE", "group": "crm", "label": "Eşleme önerisi için ortaklık payı", "type": "text",
     "default": "0.5", "help": "Düğümün kitaplarının en az bu payında ortak olan ürün kategorisi / T-soft kategorisi eşleme olarak önerilir (0–1)"},
    {"key": "CATEGORY_COOCCUR_SHARE", "group": "crm", "label": "Tema/etiket adayı için kategori payı", "type": "text",
     "default": "0.25", "help": "Aynı kategorideki kitapların en az bu payında kullanılan tema ve etiket kitaba aday olarak sorulur (0–1)"},
    {"key": "CATEGORY_PRIORITY_MONTHS", "group": "crm", "label": "Öncelik puanı dönemi (ay)", "type": "int",
     "default": "24", "help": "Onay kuyruğu Logo'daki son bu kadar ayın net satış adedine göre sıralanır"},
    {"key": "CATEGORY_DIFF_STALE_DAYS", "group": "crm", "label": "CRM farkı hatırlatma (gün)", "type": "int",
     "default": "7", "help": "Onaylanıp bu kadar gündür CRM'e işlenmemiş fark «bekliyor» diye işaretlenir"},
    {"key": "CATEGORY_BATCH_SECONDS", "group": "crm", "label": "Gece önerisi süresi (saniye)", "type": "int",
     "default": "3600", "help": "Gece turunda profili olmayan kitaplara öneri üretmek için ayrılan süre; biten iş sonraki geceye kalır"},
    # Kişi rehberi
    {"key": "PEOPLE_MAX_IDLE_DAYS", "group": "people", "label": "Son giriş süresi (gün)", "type": "int", "default": "365",
     "help": "Rehbere yalnız bu kadar gün içinde etki alanına giriş yapmış kişiler girer; ortak ve kullanılmayan "
             "hesaplar böyle ayrılır. 0: süreye bakılmaz"},
    # Yapay zekâ modeli
    {"key": "OPENAI_API_BASE", "group": "llm", "label": "Model adresi", "type": "text",
     "default": "http://127.0.0.1:18881/v1",
     "help": "Model servisinin adresi, sonunda /v1"},
    {"key": "LLM_MODEL_NAME", "group": "llm", "label": "Model", "type": "text",
     "default": "nanobaseAI", "help": "Sağlayıcının model adı"},
    {"key": "OPENAI_API_KEY", "group": "llm", "label": "API anahtarı", "type": "secret", "default": "",
     "help": "Kaydedilen anahtar ekranda bir daha gösterilmez"},
    {"key": "LLM_TIMEOUT_SEC", "group": "llm", "label": "Zaman aşımı (sn)", "type": "int", "default": "240",
     "help": "Bir soru için modelin cevabı beklenecek en uzun süre"},
    # SEO & GEO: T-soft mağazası ve Google. Parola ve anahtarlar ekranda bir daha gösterilmez.
    {"key": "TSOFT_BASE", "group": "seo", "label": "T-soft REST adresi", "type": "text",
     "default": "https://satinal.timas.com.tr/rest1", "help": "Mağazanın REST1 kökü, sonunda /rest1"},
    {"key": "TSOFT_USER", "group": "seo", "label": "T-soft web servis kullanıcısı", "type": "text", "default": "zekiai",
     "help": "T-soft panelindeki web servis kullanıcısı (yalnız okuma için kullanılır); IP kısıtı varsa bu sunucunun IP'si izinli olmalı"},
    {"key": "TSOFT_PASSWORD", "group": "seo", "label": "T-soft şifresi", "type": "secret", "default": "",
     "help": "Kaydedilen şifre ekranda bir daha gösterilmez"},
    {"key": "SEO_SITE_URL", "group": "seo", "label": "Mağaza adresi", "type": "text", "default": "https://timas.com.tr",
     "help": "Ürün sayfası bağlantıları ve arama önizlemesi bu adresle kurulur"},
    {"key": "SEO_APPROVERS", "group": "seo", "label": "Onay verebilenler", "type": "text", "default": "",
     "help": "AD hesap adları, virgülle. SEO önerilerini bunlar onaylar (onay kayıt altına alınır; T-soft'a gönderim yok). Boşsa yöneticiler onaylar"},
    {"key": "SEO_TITLE_MIN", "group": "seo", "label": "SEO başlığı en kısa (karakter)", "type": "int", "default": "30", "help": ""},
    {"key": "SEO_TITLE_MAX", "group": "seo", "label": "SEO başlığı en uzun (karakter)", "type": "int", "default": "65",
     "help": "Google başlığı yaklaşık 60–65 karakterden sonra keser"},
    {"key": "SEO_META_MIN", "group": "seo", "label": "Meta açıklama en kısa (karakter)", "type": "int", "default": "120", "help": ""},
    {"key": "SEO_META_MAX", "group": "seo", "label": "Meta açıklama en uzun (karakter)", "type": "int", "default": "160", "help": ""},
    {"key": "SEO_DESC_MIN_WORDS", "group": "seo", "label": "Ürün açıklaması en az (kelime)", "type": "int", "default": "150",
     "help": "Bundan kısa açıklama hem arama hem yapay zekâ cevapları için zayıf sayılır"},
    {"key": "GSC_SITE", "group": "seo", "label": "Search Console mülkü", "type": "text", "default": "sc-domain:timas.com.tr",
     "help": "Alan adı mülkü sc-domain:… ya da https://… biçiminde"},
    {"key": "GOOGLE_SERVICE_ACCOUNT_JSON", "group": "seo", "label": "Google servis hesabı (JSON)", "type": "secret", "default": "",
     "help": "Cloud'da indirilen anahtar dosyasının içeriği. Servis hesabı Search Console'a kullanıcı, GA4'e Görüntüleyici olarak eklenmiş olmalı"},
    {"key": "GA4_PROPERTY_ID", "group": "seo", "label": "GA4 mülk kimliği", "type": "text", "default": "347043165",
     "help": "Yönetici → Mülk ayrıntıları'ndaki sayı"},
    {"key": "MERCHANT_ACCOUNT_ID", "group": "seo", "label": "Merchant Center kimliği", "type": "text", "default": "5411495322", "help": ""},
    {"key": "GOOGLE_API_KEY", "group": "seo", "label": "Google API anahtarı", "type": "secret", "default": "",
     "help": "PageSpeed ve CrUX için; yalnız bu iki API ile kısıtlı olmalı"},
    {"key": "BING_WEBMASTER_API_KEY", "group": "seo", "label": "Bing Webmaster API anahtarı", "type": "secret", "default": "",
     "help": "bing.com/webmasters → Ayarlar → API erişimi. ChatGPT'nin web araması büyük ölçüde Bing dizinine dayanır; "
             "Bing'deki sorgu, tıklama ve tarama sorunları buradan okunur. Yalnız okuma"},
    {"key": "YANDEX_WEBMASTER_TOKEN", "group": "seo", "label": "Yandex Webmaster jetonu", "type": "secret", "default": "",
     "help": "oauth.yandex.com'da «webmaster:hostinfo» izinli bir uygulama açılır, jeton Yandex Webmaster'a yetkili "
             "hesapla alınır. Yandex'teki sorgu, dizin, site teşhisi ve dış bağlantılar buradan okunur. Yalnız okuma"},
    {"key": "INDEXNOW_KEY", "group": "seo", "label": "IndexNow anahtarı", "type": "secret", "default": "",
     "help": "8–128 harf/rakam. Aynı adla bir metin dosyası sitenin köküne konmalı (https://timas.com.tr/<anahtar>.txt, "
             "içinde yalnız anahtar); dosyayı site yöneticisi koyar. Dosya doğrulanınca değişen sayfalar Bing ve "
             "Yandex'e bildirilir. T-soft'a yazılmaz"},
    {"key": "SERPAPI_KEY", "group": "seo", "label": "Google arama sonucu anahtarı (rakip sırası)", "type": "secret", "default": "",
     "help": "Anahtar serpapi.com hesabından alınır; ücretsiz katman ayda 250 arama. Boşsa rakip karşılaştırması yapılmaz"},
    {"key": "SEO_SERP_MONTHLY", "group": "seo", "label": "Rakip araması aylık sınır", "type": "int", "default": "240",
     "help": "Ücretsiz kota aşılmasın diye bir ayda en çok bu kadar Google araması yapılır"},
    {"key": "SEO_INSPECT_DAILY", "group": "seo", "label": "Google URL denetimi günlük sınır", "type": "int", "default": "1800",
     "help": "Search Console URL Denetimi günde 2.000 adresle sınırlı; Googlebot'un sayfayı en son ne zaman taradığı ve "
             "dizinde olup olmadığı her gece bu kadar adres için sorulur, kalan ertesi güne kalır"},
    {"key": "CLOUDFLARE_API_TOKEN", "group": "seo", "label": "Cloudflare API anahtarı (yalnız okuma)", "type": "secret",
     "default": "", "help": "timas.com.tr Cloudflare arkasında. «Analytics: Read» yetkili anahtarla Googlebot ve yapay zekâ "
                            "botlarının istekleri, taradığı sayfalar ve aldığı hata kodları okunur (sunucu günlüğü yerine). Boşsa bu bölüm kapalı"},
    {"key": "CLOUDFLARE_ZONE_ID", "group": "seo", "label": "Cloudflare bölge kimliği (Zone ID)", "type": "text", "default": "",
     "help": "Cloudflare panelinde timas.com.tr → Genel bakış sağ altta"},
    {"key": "SEO_ALERT_RECIPIENTS", "group": "seo", "label": "SEO uyarı alıcıları", "type": "text", "default": "",
     "help": "E-posta adresleri, virgülle. Tıklama düşüşü, 404 artışı, robots.txt/sitemap değişikliği, yapay zekâ "
             "cevaplarından düşme gibi olaylarda gider. E-posta sunucusu Uyarılar ayarlarındaki ile aynı"},
    {"key": "SEO_WEEKLY_REPORT_TO", "group": "seo", "label": "Haftalık SEO/GEO raporu alıcıları", "type": "text", "default": "",
     "help": "E-posta adresleri, virgülle. Boşsa haftalık rapor yalnız ekranda durur"},
    {"key": "SEO_WEEKLY_REPORT_DAY", "group": "seo", "label": "Haftalık rapor günü (1=Pazartesi … 7=Pazar)", "type": "int",
     "default": "1", "help": "Rapor o günün gece işinde hazırlanır ve gönderilir"},
    {"key": "YOUTUBE_API_KEY", "group": "seo", "label": "YouTube Data API anahtarı", "type": "secret", "default": "",
     "help": "Google Cloud → YouTube Data API v3 anahtarı (ücretsiz günlük kota). Tanıtım videolarının başlık, açıklama, "
             "izlenme ve açıklamada timas.com.tr bağlantısı olup olmadığı okunur; YouTube'a hiçbir şey yazılmaz"},
    {"key": "SEO_MONTHLY_REPORT_TO", "group": "seo", "label": "Aylık SEO/GEO yönetim raporu alıcıları", "type": "text",
     "default": "", "help": "E-posta adresleri, virgülle. Her ayın ilk gecesi önceki ayın PDF raporu hazırlanır; boşsa yalnız ekranda durur"},
    {"key": "SEO_GUIDE_BOOKS", "group": "seo", "label": "Rehber taslağında önceden seçili kitap", "type": "int", "default": "10",
     "help": "Rehber içerik taslağı üretilirken en uygun bu kadar kitap işaretli gelir; kullanıcı ekler, çıkarır"},
    {"key": "SEO_GUIDE_MIN_BOOKS", "group": "seo", "label": "Rehber için en az kitap", "type": "int", "default": "3",
     "help": "Gece ön üretiminde bundan az uygun kitabı olan konu için taslak yazılmaz"},
    {"key": "SEO_GUIDES_BUDGET", "group": "seo", "label": "Gece rehber üretimi süresi (sn)", "type": "int", "default": "1800",
     "help": "Gece işinde rehber taslağı yazmaya ayrılan en uzun süre; dolunca kalan konular ertesi geceye kalır"},
    {"key": "SEO_COMPETITORS", "group": "seo", "label": "Rakip siteler", "type": "text",
     "default": "dr.com.tr,kitapyurdu.com,idefix.com,amazon.com.tr,bkmkitap.com,hepsiburada.com,trendyol.com",
     "help": "Virgülle. Aynı kitap aramasında bu sitelerin Google sırası timas.com.tr ile karşılaştırılır"},
    # Kitap Tasarım Stüdyosu
    {"key": "STUDIO_UPLOAD_MB", "group": "studio", "label": "Fotoğraf yükleme sınırı (MB)", "type": "int", "default": "60",
     "help": "Sayfa düzeninde tek fotoğrafın en büyük boyutu; ekranda yükleme alanında yazılır. Giriş kapısı ve portal "
             "web sunucusunun gövde sınırı da bu değere göre ayarlanmalıdır"},
    {"key": "STUDIO_CHARACTER_RETRIES", "group": "studio", "label": "Karakter kartına uymayan resmi yeniden üretme sayısı",
     "type": "int", "default": "3",
     "help": "Dizinin karakter kartına uymayan resim en çok bu kadar kez yeniden çizilir; sonra en yakın sürüm "
             "«karakter kartına uymuyor» uyarısıyla editöre gelir. 0: yeniden çizme, yalnız işaretle. Kaydedilince "
             "stüdyoya hemen iletilir"},
    {"key": "STUDIO_READER_PASSES", "group": "studio", "label": "Okur okuması: sayfa başına okuma sayısı", "type": "int",
     "default": "3",
     "help": "«Çocuk gözüyle okuma»da ZEKİ AI her sayfayı bu kadar kez birbirinden bağımsız okur; yalnız okumaların "
             "yarısından fazlasında geçen işaret gösterilir. Sayı arttıkça sonuç tutarlılaşır, süre uzar"},
    # Yapay zekâ görünürlüğü (GEO): izlenen sorular bu motorlara resmî API'leriyle sorulur. Anahtarsız motor ölçülmez.
    {"key": "GEMINI_API_KEY", "group": "geo", "label": "Gemini API anahtarı (ücretsiz)", "type": "secret", "default": "",
     "help": "aistudio.google.com → Get API key. Google aramalı cevap ücretsiz katmanda günde ~500 istek"},
    {"key": "GEO_GEMINI_DAILY", "group": "geo", "label": "Gemini günlük soru sınırı", "type": "int", "default": "450",
     "help": "Ücretsiz kota aşılmasın diye; bir günde en çok bu kadar soru sorulur, kalan ertesi güne kalır"},
    {"key": "GEO_GEMINI_MODEL", "group": "geo", "label": "Gemini modeli", "type": "text", "default": "gemini-2.5-flash",
     "help": "Aramalı cevabı ücretsiz katmanda olan model"},
    {"key": "GEO_OPENAI_API_KEY", "group": "geo", "label": "ChatGPT (OpenAI) API anahtarı — ücretli", "type": "secret",
     "default": "", "help": "Web aramalı cevap ücretlidir (1.000 arama ~10 $ + kullanım). Boşsa ChatGPT ölçülmez"},
    {"key": "GEO_OPENAI_DAILY", "group": "geo", "label": "ChatGPT günlük soru sınırı", "type": "int", "default": "100", "help": ""},
    {"key": "GEO_OPENAI_MODEL", "group": "geo", "label": "ChatGPT modeli", "type": "text", "default": "gpt-5-mini", "help": ""},
    {"key": "PERPLEXITY_API_KEY", "group": "geo", "label": "Perplexity API anahtarı — ücretli", "type": "secret",
     "default": "", "help": "Boşsa Perplexity ölçülmez"},
    {"key": "GEO_PERPLEXITY_DAILY", "group": "geo", "label": "Perplexity günlük soru sınırı", "type": "int", "default": "100", "help": ""},
    {"key": "GEO_PERPLEXITY_MODEL", "group": "geo", "label": "Perplexity modeli", "type": "text", "default": "sonar", "help": ""},
    {"key": "GEO_ANTHROPIC_API_KEY", "group": "geo", "label": "Claude (Anthropic) API anahtarı — ücretli", "type": "secret",
     "default": "", "help": "Boşsa Claude ölçülmez"},
    {"key": "GEO_CLAUDE_DAILY", "group": "geo", "label": "Claude günlük soru sınırı", "type": "int", "default": "100", "help": ""},
    {"key": "GEO_CLAUDE_MODEL", "group": "geo", "label": "Claude modeli", "type": "text", "default": "claude-sonnet-5", "help": ""},
    {"key": "GEO_EVERY_DAYS", "group": "geo", "label": "Aynı soru kaç günde bir sorulur", "type": "int", "default": "7",
     "help": "Bir soru bir motorda bu kadar gün geçmeden yeniden sorulmaz"},
    # Zeki AI sohbeti (chat_scope.py, chat_topics.json)
    {"key": "CHAT_CONNECTED_TOPICS", "group": "chat", "label": "Verisi bağlı sohbet konuları", "type": "text",
     "default": "",
     "help": "Virgülle konu kimlikleri, örn. finans,satis,stok,yayin,telif,tedarik,lojistik,basin,kurumsal,ik. "
             "Boşsa Logo ve CRM kataloğunda verisi olan konular bağlı sayılır. Bağlı olmayan konudaki soruya "
             "Zeki AI tahmin yerine «henüz veri bağlı değil» der"},
    # Sohbete modül verisi (chat_portal.py, chat_portal_areas.json)
    {"key": "CHAT_PORTAL_REQUIRE_CERTIFIED", "group": "chat", "label": "Modül verisinde yalnız onaylı tablolar", "type": "bool",
     "default": "1",
     "help": "Açıkken sohbet, modül tablolarından yalnız sohbet kataloğunda onaylananları kullanır. Kapatmak adayları da açar; "
             "yalnız deneme için"},
    {"key": "CHAT_PORTAL_MIN_PROB", "group": "chat", "label": "Modül verisi: seçim eşiği (olasılık)", "type": "text",
     "default": "0.5",
     "help": "Tablo, ölçü, kırılım ve tarih seçiminde en az bu olasılık istenir; altında soru netleştirilir. Kabulde ölçülür"},
    {"key": "CHAT_PORTAL_MIN_MARGIN", "group": "chat", "label": "Modül verisi: seçim eşiği (marj)", "type": "text",
     "default": "0.15",
     "help": "Seçilen seçenek ile ikinci arasındaki en az olasılık farkı. Kabulde ölçülür"},
    {"key": "CHAT_PORTAL_TIMEOUT_MS", "group": "chat", "label": "Modül verisi: sorgu süre sınırı (ms)", "type": "int",
     "default": "20000", "help": "Portal tablosuna giden tek sorgunun en uzun süresi"},
    # M32 Kurumsal satış ve B2B
    {"key": "CORP_CHANNEL", "group": "corporate", "label": "Kurum kanalı (Logo özel kod 2)", "type": "text", "default": "KURUM",
     "help": "Kurum carileri Logo'da bu özel kod 2 değeriyle ayrılır; alım geçmişi ve hacim indirimi geçmişi bu kanaldan okunur"},
    {"key": "CORP_DEALER_CHANNELS", "group": "corporate", "label": "Bayi kanalları", "type": "text", "default": "BAYI,KITAPCI",
     "help": "Virgülle, Logo özel kod 2 değerleri. Bayi paneli (sipariş vermeyen bayi, öne çıkarılacak kitaplar) bu kanallardan okunur"},
    {"key": "CORP_DISCOUNT_APPROVAL_PCT", "group": "corporate", "label": "Teklif onay eşiği: indirim (%)", "type": "text", "default": "30",
     "help": "Bir kalemin indirimi bunu aşarsa teklif satış müdürü onayına düşer. Boş: indirim onay istemez"},
    {"key": "CORP_MARGIN_MIN_PCT", "group": "corporate", "label": "Teklif onay eşiği: en düşük marj (%)", "type": "text", "default": "0",
     "help": "Maliyet biliniyorsa teklif marjı bunun altındaysa onaya düşer (0 = maliyetin altında satış). Boş: marj onay istemez"},
    {"key": "CORP_VOLUME_TIERS", "group": "corporate", "label": "Hacim indirimi kademeleri", "type": "text", "default": "",
     "help": "Örn. 100:10;300:15;1000:20 (adet:indirim %). Boşsa son 12 ayın kurum faturalarında aynı adet aralığında "
             "gerçekleşen iskontonun medyanı önerilir"},
    {"key": "CORP_COST_SOURCE", "group": "corporate", "label": "Teklif marjı için birim maliyet", "type": "text", "default": "m9",
     "help": "m9: birim maliyet modülü (bağlanana kadar maliyet «bilinmiyor»); logo: Logo'da kitabın son maliyetli satış satırı "
             "(tahmini); yok: marj hesaplanmaz"},
    {"key": "CORP_THEMES", "group": "corporate", "label": "Kurumsal paket temaları", "type": "text",
     "default": "Liderlik ve yönetim;Kişisel gelişim;İş hayatı;Yeni çalışan;Çocuk kütüphanesi;Aile;Değerler eğitimi",
     "help": "Noktalı virgülle. CRM'deki temalara eklenir; ZEKİ AI kitaplara yalnız bu listeden tema önerir, onaylanan tema paket önerisine girer"},
    {"key": "CORP_REMINDER_LEAD_DAYS", "group": "corporate", "label": "Dönemsel hatırlatma kaç gün önce", "type": "int", "default": "45",
     "help": "Geçen yıl aynı ayda alım yapan kurumlar, o ayın başından bu kadar gün önce hatırlatma listesine girer"},
    {"key": "CORP_DEALER_SILENT_DAYS", "group": "corporate", "label": "Sipariş vermeyen bayi (gün)", "type": "int", "default": "60",
     "help": "Son satış faturası bu kadar günden eski (Logo verisinin bittiği güne göre) ve önceki 12 ayda alımı olan bayi"},
    {"key": "CORP_APPROVAL_RECIPIENTS", "group": "corporate", "label": "Onay bekleyen teklif bildirimi", "type": "text", "default": "",
     "help": "Virgülle iç e-posta adresleri (satış müdürü). Boşsa bildirim gitmez; kuyruk ekranda durur. Kuruma hiçbir e-posta gitmez"},
    {"key": "CORP_B2B_REPORT_TO", "group": "corporate", "label": "Haftalık bayi özeti alıcıları", "type": "text", "default": "",
     "help": "Virgülle iç e-posta adresleri. Pazartesi sabahı sipariş vermeyen bayi listesi ekiyle gider; boşsa gitmez"},
    # M28 Kurumsal ilişkiler
    {"key": "REL_CONTACT_DAYS", "group": "relations", "label": "Temas aralığı (gün)", "type": "int", "default": "180",
     "help": "Normal öncelikli kişiyle son temastan bu kadar gün geçince «temas zamanı gelen» listesine girer"},
    {"key": "REL_CRITICAL_DAYS", "group": "relations", "label": "Kritik kişi temas aralığı (gün)", "type": "int", "default": "90",
     "help": "Kritik işaretli kişi için aynı sınır; hiç temas yazılmamış kritik kişi de listeye girer"},
    {"key": "REL_GIFT_GAP_DAYS", "group": "relations", "label": "Hediye aralığı (gün)", "type": "int", "default": "90",
     "help": "Son hediyesi bundan yeni olan kişi hediye önerisinde geriye düşer (gerekçede yazar)"},
    {"key": "REL_ORDER_TYPES", "group": "relations", "label": "Sayılan CRM sipariş tipleri", "type": "text", "default": "12,15,10,11",
     "help": "Rapordaki tanıtım/bağış toplamı: 12 Pazarlama (Tanıtım Gönderimi), 15 Deprem Bağış, 10 Okul Örneği, 11 Öğretmen Örneği"},
    {"key": "REL_ORDER_EXCLUDED_STATUS", "group": "relations", "label": "Sayılmayan sipariş durumları", "type": "text",
     "default": "100000001,100000003",
     "help": "CRM sipariş durum kodları (virgülle): 100000001 İptal Edildi, 100000003 Birleştirildi (satırları yeni siparişte de durur)"},
    {"key": "REL_SHIPPED_STATUS", "group": "relations", "label": "Sevk sayılan sipariş durumu", "type": "text", "default": "100000000",
     "help": "Hediye satırına yazılan CRM siparişi bu durumdaysa (ya da sevk tarihi doluysa) hediye «sevk edildi» olur"},
    {"key": "REL_BANNED_TERMS", "group": "relations", "label": "Ek yasaklı alan sözcükleri", "type": "text", "default": "",
     "help": "Virgülle. Alan listesine ve ilgi alanlarına yazılamaz. İnanç, mezhep, cemaat, siyasi görüş, parti, etnik köken, "
             "sendika gibi sözcükler zaten yasak; bu liste yalnız genişletir"},
    {"key": "REL_ALERT_RECIPIENTS", "group": "relations", "label": "Haftalık özet alıcıları", "type": "text", "default": "",
     "help": "Virgülle iç e-posta adresleri. Pazartesi sabahı temas zamanı gelen kişiler, geciken proje adımları ve onay bekleyen "
             "hediyeler gider; boşsa gitmez. Kişilere ve kurumlara hiçbir e-posta gitmez"},
    {"key": "REL_LLM_MIN_PROB", "group": "relations", "label": "Alan önerisi: en düşük olasılık", "type": "text", "default": "0.70",
     "help": "Zeki AI'ın alan önerisi bu olasılığın altındaysa «emin değil» denir, alanı kullanıcı seçer"},
    {"key": "REL_LLM_MIN_MARGIN", "group": "relations", "label": "Alan önerisi: en düşük marj", "type": "text", "default": "0.30",
     "help": "Seçilen alanla ikinci aday arasındaki olasılık farkı bunun altındaysa öneri gösterilmez"},
    # Pazarlama (M15 yeni kitap planı; M16–M18 aynı grubu kullanır)
    {"key": "MARKETING_ALERT_RECIPIENTS", "group": "marketing", "label": "Pazarlama bildirim alıcıları", "type": "text",
     "default": "", "help": "Virgülle e-posta adresleri (pazarlama müdürü, onaycılar). Onaya gönderilen plan ve günlük özet "
                            "(yayına 60/30/14 gün kala planı onaysız kitaplar, eksik materyal, hedefi değişen planlar) buraya gider. "
                            "Boşsa bildirim gönderilmez, plan geçmişinde «alıcı yok» yazar"},
    {"key": "MARKETING_UPPER_APPROVAL_THRESHOLD", "group": "marketing", "label": "Üst onay eşiği (TL)", "type": "text",
     "default": "", "help": "Plan bütçesi bu tutarı aşarsa pazarlama onayına ek olarak üst onay (genel müdür) gerekir. "
                            "Boş bırakılırsa ikinci onay istenmez"},
    {"key": "MARKETING_BUDGET_RATE", "group": "marketing", "label": "Kitap bütçesi oranı (%)", "type": "text", "default": "",
     "help": "CRM proje kartında pazarlama bütçesi yoksa önerilen çerçeve = kitabın onaylı hedef cirosu × bu oran. Boşsa oran "
             "veriden hesaplanır: son tam yılda pazarlama masraf merkezlerinin Logo gideri ÷ şirket net cirosu"},
    {"key": "MARKETING_DEPT_CENTERS", "group": "marketing", "label": "Pazarlama masraf merkezleri", "type": "text", "default": "",
     "help": "Oran veriden hesaplanırken sayılacak Logo masraf merkezi kodları (virgülle). Boşsa adında «Pazarlama» geçen merkezler"},
    {"key": "MARKETING_BUDGET_ACCOUNTS", "group": "marketing", "label": "Sayılacak gider hesapları", "type": "text", "default": "",
     "help": "Oran hesabında yalnız bu hesap kodlarıyla başlayan giderler (ör. 760). Boşsa merkezin bütün 7'li giderleri "
             "(personel dahil; oran yüksek çıkabilir)"},
    {"key": "MARKETING_CHANNEL_LOOKBACK_YEARS", "group": "marketing", "label": "Kanal payı geçmişi (yıl)", "type": "int", "default": "3",
     "help": "Emsal kitapların CRM pazarlama harcaması yoksa kanal payı şirketin bu kadar yıllık harcamasından hesaplanır"},
    {"key": "MARKETING_PUBLISH_DATE_ORDER", "group": "marketing", "label": "Yayın günü önceliği", "type": "text",
     "default": "crm-kitap,crm-proje,uretim",
     "help": "Yayın günü CRM'de üç yerde: crm-kitap (kitap kartı ilk baskı tarihi), crm-proje (proje kartı yayın tarihi), "
             "uretim (ilk baskının depo girişi, yoksa dağılım planı). İlk dolu olan esas alınır"},
    {"key": "MARKETING_HORIZON_DAYS", "group": "marketing", "label": "Liste penceresi (gün)", "type": "int", "default": "120",
     "help": "Yeni kitap listesinin varsayılan aralığı: bugünden bu kadar gün sonrasına kadar yayımlanacaklar. Ekranda değiştirilir"},
    {"key": "MARKETING_NO_PLAN_DAYS", "group": "marketing", "label": "«Planı yok» uyarısı (gün)", "type": "int", "default": "60",
     "help": "Yayına bu kadar gün ya da daha az kalıp planı olmayan kitaplar üstteki kartta sayılır"},
    {"key": "MARKETING_REMIND_DAYS", "group": "marketing", "label": "Hatırlatma günleri", "type": "text", "default": "60,30,14",
     "help": "Yayına bu günler kala planı onaylı olmayan kitaplar günlük özete girer"},
    {"key": "MARKETING_MATERIAL_DAYS", "group": "marketing", "label": "Materyal hatırlatması (gün)", "type": "int", "default": "21",
     "help": "Yayına bu kadar gün kala onaylı materyali eksik plan özete girer"},
    {"key": "MARKETING_REQUIRED_MATERIALS", "group": "marketing", "label": "Zorunlu materyaller", "type": "text",
     "default": "foy,basin-bulteni,sosyal",
     "help": "Yayından önce onaylı olması beklenen materyal türleri: foy, arka-kapak, basin-bulteni, sosyal, e-bulten-konu, "
             "video-senaryo, kapak-brief, influencer-brief"},
    {"key": "MARKETING_BANNED_CLAIMS", "group": "marketing", "label": "Ek yasaklı ifadeler", "type": "text", "default": "",
     "help": "Zeki AI taslağında geçerse cümlenin düşeceği ek ifadeler (virgülle). «En çok satan», «bir numara», «rekor» gibi "
             "kanıtsız üstünlük iddiaları zaten yasak"},
    {"key": "MARKETING_TASK_TEMPLATE", "group": "marketing", "label": "Takvim şablonu (JSON)", "type": "text", "default": "",
     "help": "Boşsa varsayılan şablon. Biçim: [[gün, \"iş\", \"kanal\", \"materyal\"], …] — gün yayın gününe göre (−60 … +30)"},
    # M43 Depo ve stok
    {"key": "STOCK_BULLETIN_RECIPIENTS", "group": "stock", "label": "Sabah stok bülteni alıcıları", "type": "text", "default": "",
     "help": "Virgülle iç ekip adresleri (depo, üretim planlama). Bitecekler, aktarım hataları ve Logo–CRM farkı her sabah tek e-postayla"},
    {"key": "STOCK_RUNOUT_DAYS", "group": "stock", "label": "Bitecekler: gün", "type": "int", "default": "30",
     "help": "Yeterliliği bu günün altındaki kitap «bitecek» sayılır (ekranda değiştirilebilir)"},
    {"key": "STOCK_SAFETY_DAYS", "group": "stock", "label": "Varsayılan güvenlik günü", "type": "int", "default": "15",
     "help": "Kitabın onaylı güvenlik stoku yoksa kullanılır. Kritik = yeterlilik ≤ baskı süresi + güvenlik günü"},
    {"key": "STOCK_LEAD_DAYS", "group": "stock", "label": "Baskı süresi (gün)", "type": "text", "default": "",
     "help": "Boş: üretim kartlarında ölçülen süre (matbaa belirleme → depo girişi); ölçüm yoksa 45"},
    {"key": "STOCK_EXCESS_DAYS", "group": "stock", "label": "Fazla stok: yeterlilik (gün)", "type": "int", "default": "730",
     "help": "Stoğu bu günden uzun yeten kitap fazla stok listesine girer"},
    {"key": "STOCK_DEAD_DAYS", "group": "stock", "label": "Hareketsiz stok penceresi (gün)", "type": "int", "default": "365",
     "help": "Bu pencerede hiç hareketi olmayan stoklu kitap hareketsiz sayılır (açılış devri hareket değildir)"},
    {"key": "STOCK_EXCLUDE_PLANNED", "group": "stock", "label": "Planlanan üretim girişi bakiyeye girmesin", "type": "bool",
     "default": "1", "help": "Logo'daki planlanan (ileri tarihli) üretimden giriş fişi fiziksel stok değildir; ilk dağılımla aynı karar"},
    {"key": "STOCK_EXCLUDE_PREFIXES", "group": "stock", "label": "Listeye girmeyen kod önekleri", "type": "text", "default": "157",
     "help": "Virgülle; 157 = ticari ürün (mevcut baskı öneri raporundaki süzgeçle aynı)"},
    {"key": "STOCK_MODEL", "group": "stock", "label": "Zeki AI önerileri", "type": "bool", "default": "1",
     "help": "Aktarım hata mesajı sınıflaması, fazla stok eritme yönü ve bülten metni. Kapalıyken kural metni yazılır"},
    {"key": "STOCK_MODEL_BUDGET_SEC", "group": "stock", "label": "Gece işinde Zeki AI süresi (sn)", "type": "int", "default": "1200",
     "help": "Bitmeyen sınıflama ve öneriler sonraki geceye kalır; hiçbiri atlanmaz"},
    # M53 Set, hediye ve promosyon
    {"key": "SETS_COMPONENT_SOURCE", "group": "sets", "label": "Set bileşeni kaynağı", "type": "text", "default": "auto",
     "help": "crm: setin en son CRM «Set Yapma» işlemi; logo: Logo ürün reçetesi; auto: CRM, işlem yoksa Logo reçetesi"},
    {"key": "SETS_SALES_LINETYPES", "group": "sets", "label": "Satış satırı türleri (Logo)", "type": "text", "default": "0",
     "help": "Virgülle STLINE satır türü. 0 = malzeme satırı (bütçe ve kokpitle aynı). Set satışı yalnız set koduyla okunur; "
             "bileşen satışıyla toplanmaz"},
    {"key": "SETS_LIST_PRICE_SOURCE", "group": "sets", "label": "Liste fiyatı kaynağı", "type": "text", "default": "crm",
     "help": "crm: kitap kartının KDV dahil fiyatı; logo: Logo'da bugün geçerli satış fiyat listesi. Diğeri ekranda ayrıca görünür"},
    {"key": "SETS_COST_SOURCE", "group": "sets", "label": "Marj için birim maliyet", "type": "text", "default": "m9",
     "help": "m9: birim maliyet modülü (bağlanana kadar maliyet «bilinmiyor»); logo: Logo'da kitabın son maliyetli satış satırı "
             "(tahmini); yok: marj hesaplanmaz"},
    {"key": "SETS_MARGIN_MIN_PCT", "group": "sets", "label": "Set marjı alt sınırı (%)", "type": "text", "default": "",
     "help": "Onaya gönderilen setin marjı bunun altındaysa onaycıya işaretli gelir. Boş: uyarı yok"},
    {"key": "SETS_PROMO_PREFIX", "group": "sets", "label": "Ticari ürün kodu öneki", "type": "text", "default": "157",
     "help": "Logo'da bu önekle başlayan kodlar promosyon/yan ürün listesine girer (satış raporlarındaki 157 ayrımıyla aynı)"},
    {"key": "SETS_BASKET_MONTHS", "group": "sets", "label": "Birlikte alım penceresi (ay)", "type": "int", "default": "24",
     "help": "Yalnız B2C (tüketici) siparişleri; bayi siparişi sepet sayılmaz"},
    {"key": "SETS_BASKET_MIN_ORDERS", "group": "sets", "label": "Birlikte alım: en az sipariş", "type": "int", "default": "2",
     "help": "Bir kitap çifti en az bu kadar siparişte birlikte geçtiyse listeye ve öneriye girer (ekranda yazılır)"},
    {"key": "SETS_B2C_ORDER_TYPES", "group": "sets", "label": "B2C sipariş tipleri (CRM)", "type": "text", "default": "8",
     "help": "Virgülle CRM sipariş tipi kodları; adı «B2C» ile başlayan siparişler de B2C sayılır"},
    {"key": "SETS_SUGGEST_SIZE", "group": "sets", "label": "Yazar/dizi önerisinde kitap sayısı", "type": "int", "default": "3", "help": ""},
    {"key": "SETS_GIFT_OPTIONS", "group": "sets", "label": "Kurumsal hediye: seçenek sayısı", "type": "int", "default": "5",
     "help": "Teklife konan seçenek sayısı (bütçeye en yakın olanlar); satış seçimi daraltır"},
    {"key": "SETS_GIFT_TIERS", "group": "sets", "label": "Kurumsal hediye adet kademeleri", "type": "text", "default": "",
     "help": "Örn. 100:5;300:10;1000:15 (adet:indirim %). Boşsa kademe teklifte elle girilir"},
    {"key": "SETS_SEASON_LEAD_WEEKS", "group": "sets", "label": "Özel gün uyarısı kaç hafta önce", "type": "int", "default": "8",
     "help": "Özel güne bu kadar kala o sezonun seti CRM'de açılmamışsa uyarı"},
    {"key": "SETS_ALERT_RECIPIENTS", "group": "sets", "label": "Uyarı özeti alıcıları", "type": "text", "default": "",
     "help": "Virgülle iç e-posta adresleri (set sorumlusu, depo, satın alma). Boşsa e-posta gitmez; uyarılar ekranda durur"},
    # M34 E-ticaret ve platform yönetimi (eticaret.py; yalnız ortamdan: ECOM_DIFF_KINDS, ECOM_HAK_RIGHTS, ECOM_SNOOZE_DAYS,
    # ECOM_SALES_MONTHS, ECOM_FUNNEL_*, ECOM_REASON_MIN_*, ECOM_LLM_BUDGET_SEC, ECOM_DEFAULT_OWNERS, ECOM_NAME_CHECK, ECOM_WEEKLY_DAY)
    {"key": "ECOM_CHANNELS", "group": "eticaret", "label": "Pazar yeri kanalı (Logo özel kod 2)", "type": "text", "default": "E-TICARET",
     "help": "Virgülle. Pazar yeri carileri Logo'da bu özel kod 2 değeriyle ayrılır; sell-in panosu bu carilerden okunur"},
    {"key": "ECOM_PRICE_REFERENCE", "group": "eticaret", "label": "Fiyat farkında esas fiyat", "type": "text", "default": "crm",
     "help": "crm: kitap kartının KDV dahil fiyatı; logo: Logo'da bugün geçerli satış fiyat listesi. Sitedeki fiyat bununla karşılaştırılır"},
    {"key": "ECOM_PRICE_TOLERANCE", "group": "eticaret", "label": "Fiyat farkı eşiği (₺)", "type": "text", "default": "0.01",
     "help": "Sitedeki fiyat esas fiyattan bundan fazla saparsa fark açılır"},
    {"key": "ECOM_STOCK_MIN", "group": "eticaret", "label": "Stok farkı eşiği (adet)", "type": "text", "default": "0",
     "help": "Sitede satışta olup Logo stoğu bu sayı ve altında olan kitap fark sayılır (kesim tarihiyle gösterilir)"},
    {"key": "ECOM_REQUIRED_FIELDS", "group": "eticaret", "label": "Ürün kartında zorunlu alanlar", "type": "text",
     "default": "gorsel,arka_kapak,yazar,kategori,site_gorsel",
     "help": "Virgülle: gorsel, arka_kapak, spot, yazar, kategori, anahtar_kelime, foy, site_gorsel. Boş olan «eksik kart» farkı açar"},
    {"key": "ECOM_ALERT_KINDS", "group": "eticaret", "label": "E-posta gönderilen fark türleri", "type": "text", "default": "hak,fiyat,stok",
     "help": "Virgülle: hak, fiyat, perakende (D&R fiyat farkı), stok, aktiflik, barkod, ad, eksik_kart. Fark ilk kez görüldüğünde bir kez bildirilir"},
    {"key": "ECOM_ALERT_RECIPIENTS", "group": "eticaret", "label": "Fark bildirimi alıcıları", "type": "text", "default": "",
     "help": "Virgülle iç e-posta adresleri (site sorumlusu). Boşsa e-posta gitmez; farklar ekranda durur"},
    {"key": "ECOM_WEEKLY_TO", "group": "eticaret", "label": "Haftalık özet alıcıları", "type": "text", "default": "",
     "help": "Virgülle (müdür, pazar yeri sorumlusu). Pazartesi sabahı: açık farklar, kapanma hızı, pazar yeri carileri, tükenme riski"},
    {"key": "ECOM_STOCKOUT_DAYS", "group": "eticaret", "label": "Tükenme riski (gün)", "type": "int", "default": "30",
     "help": "Logo stoğu son 12 ayın satış hızıyla bu kadar günden az yetecekse pazar yeri listesinde işaretlenir"},
    # M36 Dijital yayın ve e-kitap
    {"key": "DIJITAL_OPP_MIN_QTY", "group": "dijital", "label": "E-kitap fırsatı: son 12 ay en az basılı satış", "type": "int",
     "default": "1000",
     "help": "Hakkı olup e-kitabı olmayan kitap, son 12 ayda (Logo faturalı net adet) en az bu kadar sattıysa fırsat listesine girer"},
    {"key": "DIJITAL_AUDIO_MIN_QTY", "group": "dijital", "label": "Sesli kitap adayı: son 12 ay en az basılı satış", "type": "int",
     "default": "1000", "help": "Sesli kitap hakkı olup sesli sürümü olmayan kitaplar için aynı eşik"},
    {"key": "DIJITAL_AUDIO_GENRES", "group": "dijital", "label": "Sesli kitap adayı: türler", "type": "text", "default": "",
     "help": "Virgülle tür ya da hedef kitle kelimeleri (örn. roman, kişisel gelişim, masal, çocuk). Boşsa bütün türler"},
    {"key": "DIJITAL_BOOK_TYPES", "group": "dijital", "label": "Kitap sayılan CRM tipleri", "type": "text", "default": "1",
     "help": "Virgülle CRM kitap kartı «Tip» kodları (1 = Kitap). Fırsat ve katalog göstergeleri bu tiplerden"},
    {"key": "DIJITAL_AUDIO_TYPES", "group": "dijital", "label": "Sesli kitap CRM tipleri", "type": "text", "default": "9",
     "help": "Virgülle CRM «Tip» kodları (9 = SesliKitap). Aynı adlı basılı kitabın sesli sürümü var sayılır"},
    {"key": "DIJITAL_MATCH_MIN_PROB", "group": "dijital", "label": "Rapor eşleme: güçlü öneri olasılığı", "type": "text",
     "default": "0.6",
     "help": "Zeki AI önerisinin «güçlü» sayılacağı olasılık (0–1). Güçlü öneriler tek düğmeyle onaylanabilir; hiçbiri kendiliğinden onaylanmaz"},
    {"key": "DIJITAL_MATCH_CANDIDATES", "group": "dijital", "label": "Rapor eşleme: aday kitap sayısı", "type": "int", "default": "8",
     "help": "Eşleşmeyen satır için ad/yazar benzerliğiyle Zeki AI'a sunulan aday sayısı"},
    {"key": "DIJITAL_EDITION_DAYS", "group": "dijital", "label": "Yeni baskı / kapak değişikliği penceresi (gün)", "type": "int",
     "default": "90", "help": "Dijital sürümü olan kitapta bu süre içindeki yeni baskı ya da kapak değişikliği işaretlenir"},
    {"key": "DIJITAL_WEEKLY_DAY", "group": "dijital", "label": "Haftalık yeni baskı e-postası günü", "type": "int", "default": "1",
     "help": "1 Pazartesi … 7 Pazar"},
    {"key": "DIJITAL_NOTE_BUDGET_SEC", "group": "dijital", "label": "Hak notu ön okuması: gece süre bütçesi (sn)", "type": "int",
     "default": "1800", "help": "Bitmeyen notlar sonraki geceye kalır; kalan sayı gece raporunda yazılır"},
    {"key": "DIJITAL_RIGHTS_RECIPIENTS", "group": "dijital", "label": "Hak riski e-postası alıcıları (telif)", "type": "text",
     "default": "", "help": "Virgülle. Hak riski listesine yeni kitap girdiğinde. Boşsa e-posta gitmez, liste ekranda durur"},
    {"key": "DIJITAL_ALERT_RECIPIENTS", "group": "dijital", "label": "Yeni baskı e-postası alıcıları (dijital yayın)", "type": "text",
     "default": "", "help": "Virgülle. Dijital sürümü olan kitapta yeni baskı ya da kapak değişikliği (haftalık)"},
    {"key": "DIJITAL_FINANCE_RECIPIENTS", "group": "dijital", "label": "Rapor hatırlatması alıcıları (finans)", "type": "text",
     "default": "", "help": "Virgülle. Platformun aylık satış raporu beklenen günde yüklenmediyse"},
    {"key": "DIJITAL_IMPORT_MAX_MB", "group": "dijital", "label": "Satış raporu dosya sınırı (MB)", "type": "int", "default": "40",
     "help": "Yüklenen Excel/CSV dosyasının en büyük boyutu"},
    # M35 E-ticaret kampanya yönetimi
    {"key": "KAMPANYA_LIST_PRICE_SOURCE", "group": "kampanya", "label": "Liste fiyatı kaynağı", "type": "text", "default": "crm",
     "help": "crm: kitap kartının KDV dahil fiyatı; logo: Logo'da bugün geçerli satış fiyat listesi. Seçilen boşsa diğeri kullanılır "
             "ve satırda yazılır"},
    {"key": "KAMPANYA_COST_SOURCE", "group": "kampanya", "label": "Marj için birim maliyet", "type": "text", "default": "m9+logo",
     "help": "m9: birim maliyet modülü (onaylı analiz, M9'un Logo gerçekleşeni); m9+logo: o yoksa bu modülün okuduğu güncel yıl "
             "Logo maliyeti; logo: yalnız Logo; yok: marj hesaplanmaz. Maliyet bulunamayan kitapta marj «hesaplanamaz» yazar"},
    {"key": "KAMPANYA_MARJ_MIN_PCT", "group": "kampanya", "label": "Kampanyalı marj alt sınırı (%)", "type": "text", "default": "",
     "help": "Kampanya fiyatındaki marj bunun altındaysa kitap sarı işaretlenir (zarar her zaman kırmızı). Boş: uyarı yok"},
    {"key": "KAMPANYA_KANAL_CARI", "group": "kampanya", "label": "Kanalın Logo cari kodları", "type": "text", "default": "",
     "help": "Sonuç satışını kanala göre ayırmak için, örn. site:120.01.001;pazar_yeri:120.05.010,120.05.011. Boşsa sonuç bütün "
             "kanalların satışıdır ve ekranda öyle yazar"},
    {"key": "KAMPANYA_ADAY_HIZ_AY", "group": "kampanya", "label": "Satış hızı penceresi (ay)", "type": "int", "default": "3",
     "help": "Aday süzgecinde ve tükenme tahmininde son bu kadar ayın satışı; yavaşlama bir önceki eşit pencereyle karşılaştırılır"},
    {"key": "KAMPANYA_ADAY_STOK_AY", "group": "kampanya", "label": "Aday: stok kaç ay yetiyorsa «fazla»", "type": "text",
     "default": "12", "help": "Stok ÷ aylık satış bu sayıdan büyükse kitap stok fazlası sayılır"},
    {"key": "KAMPANYA_ADAY_DUSUS_PCT", "group": "kampanya", "label": "Aday: satış düşüşü (%)", "type": "text", "default": "30",
     "help": "Son pencere önceki pencereye göre en az bu kadar düştüyse kitap «satışı yavaşlamış» sayılır"},
    {"key": "KAMPANYA_ADAY_MARJ_MIN_PCT", "group": "kampanya", "label": "Aday: kampanya indiriminde en düşük marj (%)",
     "type": "text", "default": "", "help": "«Marjı indirimi kaldırıyor» kuralı seçildiğinde. Boş: marj sıfırın üstünde olmalı"},
    {"key": "KAMPANYA_SEZON_ONCESI_GUN", "group": "kampanya", "label": "Sezon bağı: özel günden kaç gün önce", "type": "int",
     "default": "21", "help": "Kampanya bitişinden bu kadar gün sonrasına kadar düşen özel güne bağlı kitaplar «sezona bağlı» sayılır"},
    {"key": "KAMPANYA_SONRA_GUN", "group": "kampanya", "label": "Sonuç: kampanya sonrası izleme (gün)", "type": "int",
     "default": "14", "help": "İade ve satış düşüşü için kampanya bitişinden sonra bu kadar gün okunur"},
    {"key": "KAMPANYA_FIYAT_GUN", "group": "kampanya", "label": "En düşük fiyat kuralı (gün)", "type": "int", "default": "30",
     "help": "İndirim öncesi fiyat son bu kadar gündeki en düşük site fiyatı olmalı (hukuk birimi teyit etmeli). Site fiyatı her gece "
             "kaydedilir; kayıt bu süreden kısaysa ekranda yazılır"},
    {"key": "KAMPANYA_TAKVIM_GUN", "group": "kampanya", "label": "Takvim şeridi (gün)", "type": "int", "default": "60",
     "help": "Kampanyalar ekranının üstündeki takvimde bugünden bu kadar gün ileri"},
    {"key": "KAMPANYA_LEARN_MIN_N", "group": "kampanya", "label": "Beklenen artış: en az öğrenim kaydı", "type": "int",
     "default": "3", "help": "Kampanyada artış girilmediyse aynı kanaldaki öğrenim kayıtlarının ortancası kullanılır; bu kadar kayıt "
                             "yoksa artış varsayılmaz (1 kat)"},
    {"key": "KAMPANYA_ONAY_ALICILARI", "group": "kampanya", "label": "Onay bildirimi alıcıları", "type": "text", "default": "",
     "help": "Virgülle iç e-posta adresleri (pazarlama müdürü, finans). Kampanya onaya gönderilince bildirim gider; boşsa gitmez"},
    {"key": "KAMPANYA_DEPO_ALICILARI", "group": "kampanya", "label": "Stok uyarısı alıcıları", "type": "text", "default": "",
     "help": "Yürüyen kampanyada stok bitişten önce tükenecek görünürse hazırlayana ve bu adreslere gider"},
    {"key": "KAMPANYA_LLM_BUDGET_SEC", "group": "kampanya", "label": "Gece Zeki AI süresi (sn)", "type": "int", "default": "900",
     "help": "Biten kampanyaların özeti ve CRM bayi kampanyası türü için gece ayrılan süre; biten iş sonraki geceye kalır"},
    {"key": "KAMPANYA_LLM_MIN_PROB", "group": "kampanya", "label": "Tür seçimi: en düşük olasılık", "type": "text",
     "default": "0.70", "help": "Zeki AI bayi kampanyasının türünü bu olasılığın altında seçerse «belirsiz» yazılır"},
    {"key": "KAMPANYA_LLM_MIN_MARGIN", "group": "kampanya", "label": "Tür seçimi: en düşük fark", "type": "text",
     "default": "0.30", "help": "İki seçenek arasındaki olasılık farkı bundan küçükse «belirsiz» yazılır"},
    # H3 E-ticaret müşteri yönetimi (RFM eşikleri ve kontrol payı modülün kendi ekranında)
    {"key": "COMMERCE_ENABLED", "group": "commerce", "label": "Gece okuması açık", "type": "bool", "default": "1",
     "help": "Kapalıyken zamanlayıcı T-soft'u okumaz ve özet göndermez; ekran son okumayı gösterir"},
    {"key": "COMMERCE_TSOFT_ORDER_PATH", "group": "commerce", "label": "T-soft sipariş yöntemi", "type": "text",
     "default": "order/get", "help": "Yalnız okuma yöntemi (…/get…). Ölçülecek: alanlar ve tarih süzgeci"},
    {"key": "COMMERCE_TSOFT_ORDER_PARAMS", "group": "commerce", "label": "Sipariş yöntemine ek parametre (JSON)", "type": "text",
     "default": "", "help": "Örn. {\"FetchProductData\": true}. Satırlar gelmiyorsa T-soft konsolundaki ad buraya yazılır"},
    {"key": "COMMERCE_TSOFT_DATE_PARAM", "group": "commerce", "label": "Sipariş tarih süzgeci parametresi", "type": "text",
     "default": "OrderDateTimeStart", "help": "Gece artımlı okumada «bu tarihten sonra» parametresi. Boşsa her gece bütün "
                                              "siparişler okunur. Süzgeç yok sayılırsa okuma yine doğru, yalnız uzun sürer"},
    {"key": "COMMERCE_TSOFT_DATE_FORMAT", "group": "commerce", "label": "Tarih süzgeci biçimi", "type": "text",
     "default": "%Y-%m-%d", "help": "Python strftime biçimi (örn. %d.%m.%Y)"},
    {"key": "COMMERCE_TSOFT_ORDER_ID_PARAM", "group": "commerce", "label": "Tek sipariş parametresi", "type": "text",
     "default": "OrderCode", "help": "Misafir müşterinin adresi dışa aktarımda bu parametreyle siparişten okunur"},
    {"key": "COMMERCE_TSOFT_MEMBER_PATH", "group": "commerce", "label": "T-soft üye yöntemi", "type": "text",
     "default": "customer/get", "help": "Üye izni ve üyelik tarihi için. «-» yazılırsa üyeler okunmaz"},
    {"key": "COMMERCE_TSOFT_MEMBER_ID_PARAM", "group": "commerce", "label": "Tek üye parametresi", "type": "text",
     "default": "CustomerId", "help": "Yetkili ekranda ve dışa aktarımda kişi bilgisi bu parametreyle anlık okunur"},
    {"key": "COMMERCE_TSOFT_FIELDS", "group": "commerce", "label": "T-soft alan adları (JSON)", "type": "text", "default": "",
     "help": "Boşsa varsayılan adaylar. Biçim: {\"rol\": [\"AlanAdı\", …]}; roller ve bulunan alanlar ekrandaki «Veri» "
             "bölümünde yazar"},
    {"key": "COMMERCE_CANCEL_STATUSES", "group": "commerce", "label": "İptal/iade sayılan durumlar", "type": "text",
     "default": "", "help": "Virgülle durum adı ya da numarası. Boşsa adında iptal/iade/red geçen durumlar"},
    {"key": "COMMERCE_TSOFT_FALSE_IS_RET", "group": "commerce", "label": "Sitede izin kapalıysa ret say", "type": "bool",
     "default": "1", "help": "Açıkken T-soft üyesinin e-posta/SMS izni kapalıysa o kanalda ret kanıtı yazılır (ret kazanır)"},
    {"key": "COMMERCE_RESYNC_DAYS", "group": "commerce", "label": "Gece yeniden okunan gün", "type": "int", "default": "7",
     "help": "Son bu kadar günün siparişi her gece yeniden yazılır (durum değişikliği); pazar günleri tam tur"},
    {"key": "COMMERCE_STALE_HOURS", "group": "commerce", "label": "Veri eski sayılır (saat)", "type": "int", "default": "30",
     "help": ""},
    {"key": "COMMERCE_SUMMARY_RECIPIENTS", "group": "commerce", "label": "Sabah özeti alıcıları", "type": "text", "default": "",
     "help": "Virgülle iç ekip adresleri (e-ticaret müdürü, yönetim). Dünün sipariş/ciro/müşteri özeti ve düşüş uyarısı"},
    {"key": "COMMERCE_ADMIN_RECIPIENTS", "group": "commerce", "label": "Okuma sorunu alıcıları", "type": "text", "default": "",
     "help": "Virgülle. T-soft okuması başarısız olunca"},
    # M19 Pazarlama görsel ve metin
    {"key": "MKT_CREATIVE_COVER_BASE_URL", "group": "creative", "label": "CRM kapak adresi kökü", "type": "text",
     "default": "",
     "help": "CRM kitap kartındaki kapak adresi (new_resimurl) göreli yol; önüne bu kök eklenerek indirilir. Boşsa bu "
             "yol denenmez, kapak yüklenen dosyadan ya da e-ticaret ürün görselinden gelir"},
    {"key": "MKT_CREATIVE_COVER_MIN_PX", "group": "creative", "label": "Kapak için en küçük kısa kenar (px)", "type": "int",
     "default": "800", "help": "Bundan küçük kapakta ekran «düşük çözünürlük» uyarır"},
    {"key": "MKT_CREATIVE_DIGEST_TO", "group": "creative", "label": "Günlük özet alıcıları", "type": "text", "default": "",
     "help": "Virgülle e-posta adresleri (grafik ve pazarlama ekibi). Her iş günü 08:30'dan sonra tek özet; boşsa gönderilmez"},
    {"key": "MKT_CREATIVE_CLAIM_MIN_P", "group": "creative", "label": "Kanıtsız iddia uyarısı: en düşük olasılık",
     "type": "text", "default": "0.70", "help": "Zeki AI «iddia var» dediğinde bu olasılığın altındaysa uyarı verilmez"},
    {"key": "MKT_CREATIVE_CLAIM_MIN_MARGIN", "group": "creative", "label": "Kanıtsız iddia uyarısı: en düşük fark",
     "type": "text", "default": "0.30", "help": "İki seçenek arasındaki olasılık farkı bundan küçükse uyarı verilmez"},
    {"key": "MKT_CREATIVE_LIMITS_JSON", "group": "creative", "label": "Platform karakter sınırları (JSON)", "type": "text",
     "default": "",
     "help": "Kodda platformların yayımladığı sınırlar var; farklıysa buraya {\"platform\": {\"tür\": [sınır, önerilen]}} "
             "biçiminde yazılır (ör. {\"meta-ads\": {\"baslik\": [40, 27]}})"},
    # M18 Aylık plan ve satış föyü
    {"key": "MARKETING_MONTH_DRAFT_DAY", "group": "marketing", "label": "Ay taslağı günü", "type": "int", "default": "15",
     "help": "Her ayın bu gününde gelecek ayın taslak planı kendiliğinden kurulur ve bildirim alıcılarına haber gider. "
             "Ekran da bu günden sonra gelecek ayı açar"},
    {"key": "MARKETING_MONTHLY_BUDGET", "group": "marketing", "label": "Aylık pazarlama bütçesi (TL)", "type": "text", "default": "",
     "help": "Ay planının bütçe çerçevesi. Boşsa çerçeve = ayın onaylı satış hedefi cirosu × kitap bütçesi oranı (oran boşsa "
             "veriden). Müdür ay planında elle de girebilir"},
    {"key": "MARKETING_CONFLICT_KEYS", "group": "marketing", "label": "Çakışma kuralı", "type": "text", "default": "kitaplik",
     "help": "Aynı hafta birden çok lansman hangi alanda çakışma sayılır: kitaplik, hedef-kitle (virgülle ikisi)"},
    {"key": "MARKETING_B2B_CAMPAIGN_TYPES", "group": "marketing", "label": "Takvime girecek CRM kampanya tipleri", "type": "text",
     "default": "", "help": "CRM kampanya tipi: 1 Kampanya, 2 Anlaşma. Boşsa ikisi de takvime girer"},
    {"key": "MARKETING_MONTH_SUMMARY_WORKDAY", "group": "marketing", "label": "Ay özeti iş günü", "type": "int", "default": "3",
     "help": "Önceki ayın özeti (hedef/gerçekleşen, yapılan iş) ayın bu iş gününde gönderilir (resmî tatiller sayılmaz)"},
    {"key": "MARKETING_FOY_REMIND_DAY", "group": "marketing", "label": "Föy hatırlatma günü", "type": "int", "default": "20",
     "help": "Bu gün gelecek ayın föyü eksik ya da onaysız kitapları bildirim ve föy dağıtım listesine gider"},
    {"key": "MARKETING_FOY_RECIPIENTS", "group": "marketing", "label": "Föy dağıtım listesi", "type": "text", "default": "",
     "help": "Onaylı föy paketi «Gönder» ile yalnız bu iç adreslere gider (satış müdürü, saha ekibi). Boşsa gönderilmez; paket indirilir"},
    {"key": "MARKETING_FOY_REQUIRED", "group": "marketing", "label": "Föyde zorunlu alanlar", "type": "text",
     "default": "ad,yazar,hedefKitle,fiyat,barkod,tanitim,argumanlar",
     "help": "Boşsa föy onaylanmaz. Alanlar: ad, yazar, yayinevi, kitaplik, dizi, hedefKitle, fiyat, barkod, isbn, sayfa, ebat, "
             "cilt, yayinTarihi, tanitim, argumanlar, ozet, kapak"},
    {"key": "MARKETING_FOY_LOGO_PRICE", "group": "marketing", "label": "Föy fiyatı hangi Logo fiyatıyla karşılaştırılır", "type": "text",
     "default": "satis", "help": "satis: B2B/CRM siparişli satış satırındaki güncel fiyat (Baskı Öneri tanımı) · liste: Logo satış "
                                 "fiyat listesi · yok: karşılaştırma yapılmaz"},
    {"key": "MARKETING_FOY_PRICE_TOLERANCE", "group": "marketing", "label": "Fiyat farkı toleransı (TL)", "type": "text", "default": "0.01",
     "help": "CRM ile Logo fiyatı arasındaki fark bunu aşarsa föyde uyumsuzluk uyarısı çıkar"},
    {"key": "MARKETING_COVER_BASE_URL", "group": "marketing", "label": "Kapak görseli adresi", "type": "text", "default": "",
     "help": "CRM kapak yolunun (göreli) önüne eklenen adres, ör. https://www.timas.com.tr. Boşsa föyde kapak yerine boş kutu çıkar"},
    # H4 Kurumsal e-posta (timas@ genel kutusu). Kutu yalnız okunur; portal dışarıya ileti göndermez.
    {"key": "MAIL_PROVIDER", "group": "mailbox", "label": "Kutunun sistemi", "type": "text", "default": "gmail",
     "help": "gmail: Google Workspace (bu kurulum). Microsoft 365 ve IMAP bağdaştırıcıları bu sürümde kurulmadı"},
    {"key": "MAIL_ADDRESS", "group": "mailbox", "label": "Kutu adresi", "type": "text", "default": "timas@timas.com.tr",
     "help": "Okunacak genel kutu. Boşsa ekran «kutu bağlı değil» der"},
    {"key": "MAIL_GMAIL_AUTH", "group": "mailbox", "label": "Bağlantı yolu", "type": "text", "default": "hizmet-hesabi",
     "help": "hizmet-hesabi (önerilen): Google Cloud'da hizmet hesabı + Workspace Yönetici Konsolu → Güvenlik → API denetimleri → "
             "Alan genelinde yetki devri'nde hesabın istemci kimliğine YALNIZ şu iki kapsam: "
             "https://www.googleapis.com/auth/gmail.readonly ve https://www.googleapis.com/auth/gmail.labels. "
             "oauth: kutunun kendi hesabıyla bir kez onay verilir (alan geneli yetki istenmiyorsa). Gönderme kapsamı verilmez"},
    {"key": "MAIL_GOOGLE_SERVICE_ACCOUNT_JSON", "group": "mailbox", "label": "Hizmet hesabı anahtarı (JSON)", "type": "secret",
     "default": "",
     "help": "BT'den istenecek: (1) Gmail API açık bir Google Cloud projesinde hizmet hesabı ve JSON anahtarı, (2) hesabın "
             "istemci kimliğine (sayı) alan geneli yetki devri, yalnız gmail.readonly + gmail.labels, (3) kutu adresi. "
             "SEO'nun servis hesabından ayrı tutun; bu anahtar yalnız kutuyu okur"},
    {"key": "MAIL_OAUTH_CLIENT_ID", "group": "mailbox", "label": "OAuth istemci kimliği", "type": "text", "default": "",
     "help": "Yalnız bağlantı yolu oauth ise. Google Cloud → API'ler → Kimlik bilgileri → OAuth istemcisi (Masaüstü)"},
    {"key": "MAIL_OAUTH_CLIENT_SECRET", "group": "mailbox", "label": "OAuth istemci sırrı", "type": "secret", "default": "", "help": ""},
    {"key": "MAIL_OAUTH_REFRESH_TOKEN", "group": "mailbox", "label": "OAuth yenileme belirteci", "type": "secret", "default": "",
     "help": "Kutunun hesabıyla gmail.readonly + gmail.labels kapsamlarına onay verilerek alınır. Onay geri alınırsa okuma durur "
             "ve bağlantı uyarısı gider"},
    {"key": "MAIL_START_DATE", "group": "mailbox", "label": "Canlı işleme başlangıcı", "type": "text", "default": "",
     "help": "YYYY-AA-GG. Bu tarihten önce gelen iletiler «geçmiş»tir: listeye, SLA'ya, bildirime girmez; yalnız etiketleme "
             "ekranında görünür. Boşsa ilk okumanın anı"},
    {"key": "MAIL_HISTORY_FROM", "group": "mailbox", "label": "Geçmiş iletiler şu tarihten", "type": "text", "default": "",
     "help": "YYYY-AA-GG. İlk okumada bu tarihten sonraki geçmiş iletiler de okunur (doğruluk ölçümü için etiketlenir). Boşsa okunmaz"},
    {"key": "MAIL_BUSINESS_HOURS", "group": "mailbox", "label": "İş saatleri", "type": "text", "default": "1-5 09:00-18:00",
     "help": "Hafta günü (1 = pazartesi) ve saat; birden çok satır noktalı virgülle, örn. 1-5 09:00-18:00; 6 10:00-14:00. SLA bu saatlerle sayılır"},
    {"key": "MAIL_HOLIDAYS", "group": "mailbox", "label": "Resmî tatiller", "type": "text", "default": "",
     "help": "Virgülle YYYY-AA-GG. Bu günler SLA'da sayılmaz"},
    {"key": "MAIL_SLA_REMIND_H", "group": "mailbox", "label": "Hatırlatma (iş saati)", "type": "int", "default": "24",
     "help": "Tür için kuralda SLA yazılmamışsa: bu kadar iş saati yanıtsız kalan ileti için atanan kişiye hatırlatma"},
    {"key": "MAIL_SLA_ESCALATE_H", "group": "mailbox", "label": "Eskalasyon (iş saati)", "type": "int", "default": "48",
     "help": "Birim yöneticisine (yönlendirme tablosunda) bildirim"},
    {"key": "MAIL_SLA_TOP_H", "group": "mailbox", "label": "Üst yönetici (iş saati)", "type": "int", "default": "72", "help": ""},
    {"key": "MAIL_INBOX_OWNERS", "group": "mailbox", "label": "Genel kutu sorumluları", "type": "users", "default": "",
     "help": "Atanmamış iletinin hatırlatması ve birim yöneticisi yazılmamış eskalasyon bunlara gider"},
    {"key": "MAIL_TOP_MANAGERS", "group": "mailbox", "label": "Üst yöneticiler", "type": "users", "default": "",
     "help": "Üst yönetici eşiğini aşan iletilerin bildirimi"},
    {"key": "MAIL_NOTIFY_EMAIL", "group": "mailbox", "label": "SLA bildirimini e-postayla gönder", "type": "bool", "default": "1",
     "help": "İç e-posta (portalın bildirim hesabından, çalışanlara). Kapalıyken bildirim yalnız ileti geçmişine yazılır"},
    {"key": "MAIL_SUGGEST_MIN_PROB", "group": "mailbox", "label": "Öneri eşiği: olasılık", "type": "text", "default": "0.70",
     "help": "Zeki AI'ın tür olasılığı bunun altındaysa ileti «Emin olunmayan» sekmesine düşer"},
    {"key": "MAIL_SUGGEST_MIN_MARGIN", "group": "mailbox", "label": "Öneri eşiği: fark", "type": "text", "default": "0.30",
     "help": "Seçilen tür ile en yakın ikinci tür arasındaki olasılık farkı"},
    {"key": "MAIL_AUTO_MIN_PROB", "group": "mailbox", "label": "Otomatik işlem eşiği: olasılık", "type": "text", "default": "0.90",
     "help": "Tanıtım/spam arşivi ve açılmış türlerde otomatik atama yalnız bu olasılığın üstünde"},
    {"key": "MAIL_AUTO_MIN_MARGIN", "group": "mailbox", "label": "Otomatik işlem eşiği: fark", "type": "text", "default": "0.50", "help": ""},
    {"key": "MAIL_AUTO_ASSIGN_CATEGORIES", "group": "mailbox", "label": "Otomatik atanan türler", "type": "text", "default": "",
     "help": "Virgülle tür anahtarları. Boş (varsayılan): hiçbir tür kendiliğinden atanmaz. Etiketlenmiş geçmişte o türün "
             "doğruluğu %90'ı geçmeden açmayın"},
    {"key": "MAIL_SPAM_SENDERS", "group": "mailbox", "label": "Doğrudan arşivlenen gönderenler", "type": "text", "default": "",
     "help": "Virgülle adres ya da alan adı (örn. bulten.ornek.com). Kutunun kendi spam işaretine ek; arşiv geri alınabilir"},
    {"key": "MAIL_ORDER_PATTERN", "group": "mailbox", "label": "Sipariş numarası deseni", "type": "text",
     "default": r"(?:sipari[şs]|order)\s*(?:no|numaras[ıi]|#)?\s*[:#]?\s*([A-Z0-9][A-Z0-9\-]{4,19})",
     "help": "İleti metnindeki sipariş numarasını bulan düzenli ifade (ilk grup numara). Boşsa aranmaz"},
    {"key": "MAIL_MODEL_BODY_CHARS", "group": "mailbox", "label": "Zeki AI'a giden metin (karakter)", "type": "int", "default": "6000",
     "help": "Uzun iletide modelin bağlam penceresine sığacak kısım. Ekranda ileti kutudan tam okunur"},
    {"key": "MAIL_LLM_BUDGET_SEC", "group": "mailbox", "label": "Okuma turu süresi (sn)", "type": "int", "default": "200",
     "help": "5 dakikalık turda sınıflamaya ayrılan süre; bitmeyen iletiler sonraki tura kalır"},
    {"key": "MAIL_READ_OVERLAP_MIN", "group": "mailbox", "label": "Okuma örtüşmesi (dk)", "type": "int", "default": "60",
     "help": "Her okuma son iletiden bu kadar geriden başlar; aynı ileti iki kez yazılmaz"},
    {"key": "MAIL_REPLY_CHECK_MIN", "group": "mailbox", "label": "Yanıt denetimi aralığı (dk)", "type": "int", "default": "15",
     "help": "Açık iletinin konu zincirinde kutudan gönderilmiş yanıt bu aralıkla aranır"},
    {"key": "MAIL_CONNECTION_ALERT_MIN", "group": "mailbox", "label": "Bağlantı uyarısı (dk)", "type": "int", "default": "30",
     "help": "Kutu bu kadar dakikadır okunamadıysa aşağıdaki adreslere bir kez uyarı gider"},
    {"key": "MAIL_CONNECTION_ALERT_TO", "group": "mailbox", "label": "Bağlantı uyarısı alıcıları", "type": "text", "default": "",
     "help": "Virgülle iç e-posta adresleri (portal yöneticisi / BT)"},
    # Zeki AI sesli not (M30/M31 ziyaret notu mikrofonu). Servis adresi ve anahtarı yalnız ortamda (VOICE_NOTE_URL,
    # VOICE_NOTE_TOKEN, VOICE_NOTE_EXTRA_HEADER, VOICE_NOTE_CA_FILE).
    {"key": "VOICE_NOTE_ENABLED", "group": "voice", "label": "Sesli not açık", "type": "bool", "default": "0",
     "help": "Açıkken saha ve okul ziyaret notunda mikrofon düğmesi görünür. Servis bağlantısı tanımlı değilse düğme yine görünmez"},
    {"key": "VOICE_NOTE_MAX_SECONDS", "group": "voice", "label": "En uzun kayıt (saniye)", "type": "int", "default": "300",
     "help": "Telefonda kayıt bu sürede kendiliğinden durur; daha uzun ses kabul edilmez"},
    {"key": "VOICE_NOTE_MAX_MB", "group": "voice", "label": "En büyük ses (MB)", "type": "int", "default": "20",
     "help": "Portal kaydı 16 kHz WAV'a çevirir: 5 dakika ≈ 9,6 MB"},
    {"key": "VOICE_NOTE_AI_FIX", "group": "voice", "label": "Zeki AI düzeltmesi", "type": "bool", "default": "1",
     "help": "Noktalama, büyük harf ve özel adları düzeltir. Sayıları ya da anlamı değiştiren düzeltme kullanılmaz; o zaman konuşmanın kendi metni gelir"},
    {"key": "VOICE_NOTE_SLOTS", "group": "voice", "label": "Aynı anda servise giden kayıt", "type": "int", "default": "2",
     "help": "Fazlası geliş sırasıyla bekler. Servis kendi içinde de tek sıra tutar"},
    {"key": "VOICE_NOTE_WAIT_SEC", "group": "voice", "label": "Sırada en uzun bekleme (saniye)", "type": "int", "default": "180",
     "help": "Aşılırsa kişiye «yoğun, yeniden deneyin» denir; kayıt telefonda durur, yeniden gönderilebilir"},
    {"key": "VOICE_NOTE_CONTEXT", "group": "voice", "label": "Ad ipucu gönder", "type": "bool", "default": "0",
     "help": "Müşteri/okul adı ve aşağıdaki sözlük yazıya dökme sırasında ipucu olarak verilir. Etkisi sahada ölçülene kadar kapalı"},
    {"key": "VOICE_NOTE_VOCABULARY", "group": "voice", "label": "Sözlük ipucu", "type": "text", "default": "",
     "help": "Virgülle sık geçen terimler ve adlar (ör. iskonto, vade, sevk, irsaliye). Yalnız «Ad ipucu gönder» açıkken kullanılır"},
    # M48 Sistem durumu (halka denetimleri, olaylar). Bu grup Sistem durumu ekranından da `ozellik:sistem.ayar` ile düzenlenir.
    {"key": "ITOPS_RECIPIENTS", "group": "itops", "label": "Kopma ve düzelme bildirimi alıcıları", "type": "text", "default": "",
     "help": "Virgülle BT ve işletim ekibinin e-posta adresleri. Yalnız aşağıdaki iç alan adlarındaki adreslere gönderilir"},
    {"key": "ITOPS_INTERNAL_DOMAINS", "group": "itops", "label": "İç alan adları", "type": "text", "default": "timas.com.tr",
     "help": "Virgülle. Sistem durumu e-postası yalnız bu alan adlarına gider; boşsa izinli alıcı alan adları kullanılır"},
    {"key": "ITOPS_WEEKLY_TO", "group": "itops", "label": "Haftalık sağlık özeti alıcıları", "type": "text", "default": "",
     "help": "Virgülle; boşsa bildirim alıcılarına gider. Kesinti dakikası ve en çok bozulan halka"},
    {"key": "ITOPS_WEEKLY_DAY", "group": "itops", "label": "Haftalık özet günü (1=Pazartesi … 7=Pazar)", "type": "int", "default": "1", "help": ""},
    {"key": "ITOPS_REPORT_HOUR", "group": "itops", "label": "Özet saati", "type": "int", "default": "8",
     "help": "Haftalık özet ve günlük «hata veren zamanlanmış işler» e-postası bu saatten sonraki ilk turda gider (0–23)"},
    {"key": "ITOPS_FAILS_TO_OPEN", "group": "itops", "label": "Olay açmak için art arda başarısız deneme", "type": "int", "default": "2",
     "help": "Tek başarısız deneme olay açmaz (yanlış alarm); kesinti ayrıca aşağıdaki en kısa süre kadar sürmeli"},
    {"key": "ITOPS_OUTAGE_MIN", "group": "itops", "label": "Kesinti sayılması için en kısa süre (dk)", "type": "int", "default": "10",
     "help": "Bağlantı bu kadar dakika art arda yanıt vermezse olay açılır ve bir kez e-posta gider; daha kısa kesinti olay "
             "sayılmaz. 5 dk'lık turda 10 = üç ardışık başarısız deneme. 0: yalnız deneme sayısına bakılır"},
    {"key": "ITOPS_RESTART_GRACE_MIN", "group": "itops", "label": "Yeniden başlatma payı (dk)", "type": "int", "default": "5",
     "help": "Zeki AI hizmeti yeniden başlatıldığında, açılışın bu kadar dakika öncesi ve sonrasındaki başarısız denemeler "
             "sayılmaz (planlı yeniden başlatma olay değildir). Açılış zamanı hizmetin kendi açılış kaydından okunur. 0: kapalı"},
    {"key": "ITOPS_RESOLVE_MIN", "group": "itops", "label": "«Düzeldi» için kesintisiz çalışma (dk)", "type": "int",
     "default": "15",
     "help": "Olay ancak bağlantı bu kadar dakika kesintisiz çalışınca, kendi verisi okununca ve onu kullanan sık çalışan "
             "bir zamanlanmış iş (varsa) başarıyla koşunca kapanır; «Düzeldi» e-postası o zaman gider. Kurumsal e-posta "
             "kutusu da aynı kurala uyar"},
    {"key": "ITOPS_REMIND_HOURS", "group": "itops", "label": "Kopma hatırlatması (saat)", "type": "int", "default": "0",
     "help": "0: aynı olay için ikinci e-posta gitmez, düzelince tek «Düzeldi» e-postası gider. Sürerken hatırlatma "
             "isteniyorsa kaç saatte bir gideceğini girin"},
    {"key": "ITOPS_LOGO_STALE_DAYS", "group": "itops", "label": "Logo verisi eski sayılır (gün)", "type": "int", "default": "3",
     "help": "Son fatura bu kadar günden eskiyse «veri eski» olayı açılır. 0: bakılmaz. Hafta sonu yanlış alarm vermesin diye 3"},
    {"key": "ITOPS_CRM_STALE_HOURS", "group": "itops", "label": "CRM verisi eski sayılır (saat)", "type": "int", "default": "24",
     "help": "Kitap kartlarında son değişiklik bu kadar saatten eskiyse «veri eski» olayı açılır. 0: bakılmaz"},
    {"key": "ITOPS_CRM_FRESH_TABLE", "group": "itops", "label": "CRM tazelik tablosu", "type": "text", "default": "new_kitapBase",
     "help": "Son değişiklik zamanına bakılan CRM tablosu"},
    {"key": "ITOPS_STALE_REMIND_HOURS", "group": "itops", "label": "«Veri eski» hatırlatması (saat)", "type": "int", "default": "0",
     "help": "0: «veri eski» olayı için tek e-posta gider, veri güncellenince tek «Düzeldi». Sürerken hatırlatma isteniyorsa saat girin"},
    # DYK Kurul (göstergeler, toplantı, paket). Eşik ve sahip gösterge kataloğunda (Kurul ekranı) tutulur.
    {"key": "KURUL_COMPANY", "group": "kurul", "label": "Paketteki şirket adı", "type": "text", "default": "Timaş Yayınları",
     "help": "Kurul paketinin ve PDF'in üst bilgisinde yazar"},
    {"key": "KURUL_STALE_HOURS", "group": "kurul", "label": "Gösterge ölçümü eski sayılır (saat)", "type": "int", "default": "24",
     "help": "Panel açılınca son ölçüm bundan eskiyse göstergeler arka planda yeniden okunur (hazır raporlardan; ağır sorgu yok)"},
    {"key": "KURUL_ACTION_WARN_DAYS", "group": "kurul", "label": "Aksiyon hatırlatması (termine gün)", "type": "int", "default": "7",
     "help": "Kurul aksiyonunun terminine bu kadar gün kala ve termin geçince sahibine bir kez iç e-posta"},
    {"key": "KURUL_COMMENT_REMIND_DAYS", "group": "kurul", "label": "Yorum hatırlatması (toplantıya iş günü)", "type": "int", "default": "5",
     "help": "Sıradaki toplantıya bu kadar iş günü kala, yorumu olmayan sarı/kırmızı göstergenin sahibine bir kez"},
    {"key": "KURUL_HISTORY_MONTHS", "group": "kurul", "label": "Gösterge seyri (ay)", "type": "int", "default": "12",
     "help": "Gösterge ayrıntısındaki geçmiş dönem sayısı"},
    {"key": "ITOPS_VPN_IFACE", "group": "itops", "label": "Şirket ağı bağlantı arayüzü", "type": "text", "default": "tun0",
     "help": "Test sunucusunda şirket ağı bağlantısının arayüz adı. Müşteri VM'inde bakılmaz"},
    {"key": "ITOPS_VPN_PROBE", "group": "itops", "label": "Şirket ağında denenecek adres", "type": "text", "default": "",
     "help": "sunucu:port, örn. 192.168.0.25:1433. Yerel tünel ağzı değil, ağın içindeki gerçek adres"},
    {"key": "ITOPS_VM_URL", "group": "itops", "label": "Müşteri VM'i adresi", "type": "text", "default": "",
     "help": "Test sunucusundan denenecek portal adresi, örn. http://192.168.0.55/timas/. Boşsa bu halka ölçülmez"},
    {"key": "ITOPS_VM_HEARTBEAT_SEC", "group": "itops", "label": "VM iş bildirimi beklenen en uzun süre (sn)", "type": "int",
     "default": "1200", "help": "Müşteri VM'inde zamanlanmış işlerden bu süre bildirim gelmezse halka kopuk sayılır"},
    {"key": "ITOPS_MODEL_TIMEOUT_SEC", "group": "itops", "label": "Zeki AI deneme süresi (sn)", "type": "int", "default": "240",
     "help": "Sırada bekleyip cevap alamayan deneme kopma sayılmaz, «meşgul» yazar"},
    {"key": "ITOPS_RING_TIMEOUT_SEC", "group": "itops", "label": "Bağlantı denemesi süresi (sn)", "type": "int", "default": "90", "help": ""},
    {"key": "ITOPS_QUERY_TIMEOUT_SEC", "group": "itops", "label": "Veri sonu sorgusu süresi (sn)", "type": "int", "default": "60", "help": ""},
    {"key": "ITOPS_DISK_PATHS", "group": "itops", "label": "İzlenen disk klasörleri", "type": "text", "default": "",
     "help": "Virgülle; boşsa uygulama veri klasörü"},
    # Veri güvenliği (M49)
    {"key": "SECURITY_ALERT_RECIPIENTS", "group": "security", "label": "Güvenlik uyarısı alıcıları", "type": "text", "default": "",
     "help": "Virgülle e-posta adresleri (bilgi güvenliği sorumlusu, yönetici). Kritik uyarı anında, 403 özeti günde bir gider; boşsa e-posta gitmez, uyarı ekranda kalır"},
    {"key": "SECURITY_FAIL_THRESHOLD", "group": "security", "label": "Hatalı giriş eşiği (deneme)", "type": "int", "default": "5",
     "help": "Aynı hesaba aşağıdaki süre içinde bu kadar hatalı giriş denenirse kritik uyarı açılır"},
    {"key": "SECURITY_FAIL_WINDOW_MIN", "group": "security", "label": "Hatalı giriş penceresi (dakika)", "type": "int", "default": "10", "help": ""},
    {"key": "SECURITY_WORK_HOURS", "group": "security", "label": "Mesai saatleri", "type": "text", "default": "08:00-19:00",
     "help": "SS:DD-SS:DD. Bunun dışında yapılan dışa aktarmalar «mesai dışı» sayılır"},
    {"key": "SECURITY_WORK_DAYS", "group": "security", "label": "Mesai günleri", "type": "text", "default": "1-5",
     "help": "1 = Pazartesi … 7 = Pazar; «1-5» ya da «1,2,3,4,5,6»"},
    {"key": "SECURITY_OFFHOURS_EXPORT_MIN", "group": "security", "label": "Mesai dışı toplu dışa aktarma (bir saatte)", "type": "int", "default": "3",
     "help": "Bir kişi mesai dışında bir saat içinde bu kadar dışa aktarma yaparsa kritik uyarı açılır"},
    {"key": "SECURITY_IDLE_DAYS", "group": "security", "label": "Uzun süredir girmeyen hesap (gün)", "type": "int", "default": "90",
     "help": "Hesap hijyeni raporunda: portal izi olan ama bu kadar gündür giriş yapmamış hesaplar. 0 = bakılmaz"},
    {"key": "SECURITY_TEST_ACCOUNT_PATTERN", "group": "security", "label": "Test hesabı ad kalıbı", "type": "text",
     "default": "^(test|deneme|demo|qa[-_.]|claude)",
     "help": "Bu kalıba uyan hesaplar hesap hijyeni raporunda «test/deneme adı» diye çıkar (düzenli ifade)"},
    {"key": "SECURITY_DAILY_AT", "group": "security", "label": "Günlük iş saati", "type": "time", "default": "03:40",
     "help": "Saklama süresi işi ve günlük erişim özeti bu saatten sonraki ilk koşuda, günde bir kez çalışır"},
    {"key": "SECURITY_RETENTION_APPLY", "group": "security", "label": "Saklama süresini uygula", "type": "bool", "default": "0",
     "help": "Kapalıyken hiçbir kayıt silinmez; gece işi yalnız «kaç satır etkilenecek» önizlemesini yazar. Açmak yönetici "
             "kararıdır (Veri güvenliği → Saklama süreleri, önizlemeyle)"},
    {"key": "SECURITY_RETENTION_QUERY_RESULT_DAYS", "group": "security", "label": "Soru sonucu saklama (gün)", "type": "int", "default": "90",
     "help": "Soru kaydındaki tam sonuç tablosu bu süreden sonra boşaltılır; soru ve SQL kalır. 0 = süresiz"},
    {"key": "SECURITY_RETENTION_LLM_TEXT_DAYS", "group": "security", "label": "Model sırası metni saklama (gün)", "type": "int", "default": "30",
     "help": "Model sırasındaki ve model işindeki mesaj/cevap metni boşaltılır; süre ve sayılar kalır. 0 = süresiz"},
    {"key": "SECURITY_RETENTION_LOGIN_DAYS", "group": "security", "label": "Giriş kaydı saklama (gün)", "type": "int", "default": "365",
     "help": "0 = süresiz"},
    {"key": "SECURITY_RETENTION_ACCESS_DAYS", "group": "security", "label": "Erişim kaydı saklama (gün)", "type": "int", "default": "365",
     "help": "Yetkisiz erişim ve dışa aktarma satırları. 0 = süresiz"},
    {"key": "SECURITY_RETENTION_ALERT_DAYS", "group": "security", "label": "Kapanmış uyarı saklama (gün)", "type": "int", "default": "730",
     "help": "Açık uyarı silinmez. 0 = süresiz"},
    {"key": "SECURITY_RETENTION_AUDIT_DAYS", "group": "security", "label": "Değişiklik kaydı saklama (gün)", "type": "int", "default": "0",
     "help": "0 = süresiz (yetki değişikliklerinin kanıtı)"},
    # M51 Müşteri hizmetleri: destek masası (NanobaseAI Destek) salt okuma bağlantısı ve Zeki AI eşikleri.
    {"key": "DESTEK_API_BASE", "group": "support", "label": "Destek masası adresi", "type": "text", "default": "",
     "help": "Masanın köprüden erişilen adresi, örn. http://127.0.0.1:8447. Masaya yalnız okuma çağrısı yapılır"},
    {"key": "DESTEK_API_KEY", "group": "support", "label": "Masa okuma anahtarı", "type": "secret", "default": "",
     "help": "Masada açılan salt okuma API kullanıcısının anahtarı (API Key)"},
    {"key": "DESTEK_API_SECRET", "group": "support", "label": "Masa okuma parolası", "type": "secret", "default": "",
     "help": "Aynı kullanıcının API Secret değeri"},
    {"key": "DESTEK_PUBLIC_URL", "group": "support", "label": "Masanın kullanıcı adresi", "type": "text", "default": "",
     "help": "Ekrandaki «Masada aç» bağlantıları için, örn. https://portal.nanobase.ai:8446"},
    {"key": "DESTEK_API_VERIFY_TLS", "group": "support", "label": "Masa sertifikasını doğrula", "type": "bool", "default": "1",
     "help": "Masa adresi https ve iç sertifikalıysa kapatılabilir"},
    {"key": "DESTEK_PANEL_TOKEN", "group": "support", "label": "Masa paneli anahtarı", "type": "secret", "default": "",
     "help": "Doluysa masa panelinin bağlam isteği X-Destek-Panel-Key başlığında bu değeri taşımalı (nginx anahtarına ek)"},
    {"key": "SUPPORT_CLASSIFY_MIN_PROB", "group": "support", "label": "Konu sınıflaması: en düşük olasılık", "type": "text",
     "default": "0.70", "help": "Zeki AI bu olasılığın altında kalırsa talep «sınıflanamadı» olur, temsilci seçer (0–1)"},
    {"key": "SUPPORT_CLASSIFY_MIN_MARGIN", "group": "support", "label": "Konu sınıflaması: en düşük fark", "type": "text",
     "default": "0.30", "help": "Seçilen konu ile ikinci konu arasındaki olasılık farkı bunun altındaysa «sınıflanamadı» (0–1)"},
    {"key": "SUPPORT_ORDER_DAYS", "group": "support", "label": "Bağlamda sipariş penceresi (gün)", "type": "int", "default": "365",
     "help": "Müşteri bağlamında bu kadar günlük sipariş gösterilir; açık (bekleyen) siparişler tarihten bağımsız hep gelir"},
    {"key": "SUPPORT_LOGO_MONTHS", "group": "support", "label": "Bağlamda fatura penceresi (ay)", "type": "int", "default": "12",
     "help": "Logo'dan son bu kadar ayın satış ve iade faturaları (veri sonu tarihiyle)"},
    {"key": "SUPPORT_CARGO_MATCH", "group": "support", "label": "Kargo kaydı eşleme yolu", "type": "text", "default": "takip,irsaliye",
     "help": "Kargo firmasının gönderi kaydını siparişe bağlayan alan: takip (takip numarası), irsaliye (müşteri irsaliye no) ya da ikisi"},
    {"key": "SUPPORT_SLA_WARN_RATIO", "group": "support", "label": "SLA uyarı payı", "type": "text", "default": "0.80",
     "help": "Sürenin bu payı dolan açık talep «yaklaşıyor» sayılır (0–1)"},
    {"key": "SUPPORT_REPEAT_DAYS", "group": "support", "label": "Tekrarlayan talep penceresi (gün)", "type": "int", "default": "7",
     "help": "Aynı kişiden aynı konuda bu kadar gün içinde ikinci talep «tekrar» sayılır"},
    {"key": "SUPPORT_GAP_DAYS", "group": "support", "label": "SSS açığı penceresi (gün)", "type": "int", "default": "30",
     "help": "SSS eşleşmesi bulunamayan talepler bu kadar günlük pencerede konuya göre sayılır"},
    {"key": "SUPPORT_GAP_MIN_TICKETS", "group": "support", "label": "SSS açığı için en az talep", "type": "int", "default": "3",
     "help": "Bir konu en az bu kadar eşleşmesiz talepte SSS adayı olur"},
    {"key": "SUPPORT_DEALER_CHANNELS", "group": "support", "label": "Bayi aramasında kanal", "type": "text", "default": "",
     "help": "Boşsa bütün etkin cariler aranır; doluysa CRM firma kanalı kodları (virgülle, örn. 100000008 bayi, 100000001 kitapçı)"},
    {"key": "SUPPORT_DRAFT_SIGNATURE", "group": "support", "label": "Taslak imzası", "type": "text",
     "default": "Timaş Yayınları Müşteri Hizmetleri", "help": "Cevap taslağının sonuna eklenen satır"},
    # M50 Zeki AI kalitesi
    {"key": "MODEL_QUALITY_RECIPIENTS", "group": "model_quality", "label": "Bildirim alıcıları", "type": "text", "default": "",
     "help": "Virgülle; yalnız iç adresler (izinli alan adı süzgeci geçerli). Koşuda bozulan soru, aynı soruya tekrarlanan "
             "«Yanlış» ve günlük geri bildirim özeti buraya gider. Boşsa e-posta gitmez, ekranda görünür"},
    {"key": "MODEL_QUALITY_WINDOW_DAYS", "group": "model_quality", "label": "Karne penceresi (gün)", "type": "int",
     "default": "30", "help": "Karne ve hata sınıfı sayımının varsayılan süresi; ekrandan değiştirilebilir"},
    {"key": "MODEL_QUALITY_REPEAT_WRONG", "group": "model_quality", "label": "Tekrarlanan «Yanlış» eşiği", "type": "int",
     "default": "3", "help": "Aynı soruya pencere içinde bu kadar «Yanlış» gelirse ekibe anında bir kez yazılır"},
    {"key": "MODEL_QUALITY_QUEUE_STALE_DAYS", "group": "model_quality", "label": "Bekleyen bildirim uyarısı (gün)",
     "type": "int", "default": "7", "help": "Bu süreden eski, sınıflanmamış bildirimler günlük özette ayrıca yazılır"},
    {"key": "MODEL_QUALITY_STALE_HOURS", "group": "model_quality", "label": "Yarıda kalan koşu (saat)", "type": "int",
     "default": "6", "help": "Rapor getirmeyen koşu bu süreden sonra «hata» olur"},
    {"key": "MODEL_QUALITY_ENV", "group": "model_quality", "label": "Ortam", "type": "text", "default": "",
     "help": "test ya da vm; sürüm kaydında ve koşularda ortam adı olarak yazılır"},
    {"key": "MODEL_QUALITY_CODE_SHA", "group": "model_quality", "label": "Kod sürümü (elle)", "type": "text", "default": "",
     "help": "Boş bırakın: kurulum betiğinin bildirdiği sürüm kullanılır. Yalnız kurulum bildirim yapamıyorsa doldurun"},
    {"key": "MODEL_QUALITY_RULES_PATHS", "group": "model_quality", "label": "Kural dosyaları", "type": "text", "default": "",
     "help": "Sürüm kaydına özeti girecek ek kural klasörleri/dosyaları, virgülle (bilgi paketi zaten sayılır)"},
    {"key": "MODEL_QUALITY_PROMPT_PATHS", "group": "model_quality", "label": "İstem dosyaları", "type": "text", "default": "",
     "help": "Sürüm kaydına özeti girecek istem dosyaları, virgülle. Boşsa istem kodla birlikte sürümlenir"},
    {"key": "MODEL_QUALITY_CLUSTER_MIN_SIM", "group": "model_quality", "label": "Soru kümesi: benzerlik eşiği", "type": "text",
     "default": "0.82", "help": "Başarısız sorular anlam benzerliği bu değerin üstündeyse aynı kümeye girer (0–1)"},
    {"key": "MODEL_QUALITY_CLUSTER_MIN_PROB", "group": "model_quality", "label": "Küme sınıf önerisi: en düşük olasılık",
     "type": "text", "default": "0.70", "help": "Zeki AI'ın küme için önerdiği sınıf bu olasılığın altındaysa «emin değil» yazılır (0–1)"},
    {"key": "MODEL_QUALITY_CLUSTER_MIN_MARGIN", "group": "model_quality", "label": "Küme sınıf önerisi: en düşük fark",
     "type": "text", "default": "0.30", "help": "Önerilen sınıf ile ikinci sınıf arasındaki olasılık farkı bunun altındaysa «emin değil» (0–1)"},
    # Zeki AI ortak araçlar (belge okuma, kitap benzerliği)
    {"key": "DOC_READ_OCR", "group": "zeki_ortak", "label": "Taranmış sayfaları oku (OCR)", "type": "bool", "default": "1",
     "help": "Açıkken metin katmanı olmayan PDF sayfası ve görüntü dosyası GPU sunucusundaki okuyucuyla okunur. Kapalıyken "
             "bu sayfalar «okunamadı» diye işaretlenir"},
    {"key": "DOC_READ_TIMEOUT_SEC", "group": "zeki_ortak", "label": "Belge okuma süresi (sn)", "type": "int", "default": "900",
     "help": "Taranmış belgenin okunması için beklenecek en uzun süre; model açılırken beklenen süre de buna dahil"},
    {"key": "DOC_READ_MIN_PAGE_CHARS", "group": "zeki_ortak", "label": "Metin sayılacak en az harf", "type": "int",
     "default": "20", "help": "PDF sayfasının metin katmanında bundan az harf varsa sayfa taranmış sayılır ve OCR'a gider"},
    {"key": "DOC_READ_LOW_CONFIDENCE", "group": "zeki_ortak", "label": "OCR düşük güven eşiği", "type": "text",
     "default": "0.80", "help": "Bu güvenin altında okunan sayfa ekranda «düşük güven» diye işaretlenir; metin atılmaz (0–1)"},
    {"key": "BOOK_SIMILAR_TEXT_CHARS", "group": "zeki_ortak", "label": "Kitap benzerliği: özet uzunluğu", "type": "int",
     "default": "3000", "help": "Kitabın benzerlik dizinine girecek arka kapak/özet metninin karakter sayısı (HTML temizlenmiş)"},
    {"key": "BOOK_SIMILAR_BATCH", "group": "zeki_ortak", "label": "Kitap benzerliği: parti", "type": "int", "default": "32",
     "help": "Dizin kurulurken gömme servisine bir istekte gönderilen kitap sayısı"},
    {"key": "DOC_EXTRACT_WINDOW_CHARS", "group": "zeki_ortak", "label": "Belgeden alan çıkarma: bölüm uzunluğu",
     "type": "int", "default": "24000",
     "help": "Uzun belge (başvuru dosyası, sözleşme) Zeki AI'a bu kadar karakterlik bölümlerle gider; sayfa bölünmez, "
             "bütün bölümler okunur"},
    {"key": "DOC_EXTRACT_OVERLAP_PAGES", "group": "zeki_ortak", "label": "Belgeden alan çıkarma: örtüşen sayfa",
     "type": "int", "default": "1", "help": "Ardışık iki bölümün ortak sayfa (parça) sayısı (0–5)"},
    {"key": "BASVURU_ILKE_KATEGORILERI", "group": "zeki_ortak", "label": "Başvuru ön okuması: ilke kategorileri",
     "type": "text", "default": "",
     "help": "Yayın ilkelerine aykırılık işaretlerinin kategorileri, JSON: {\"anahtar\": \"ad\"}. Boşsa varsayılan "
             "kategoriler (şiddet, müstehcenlik, nefret söylemi, inanç, madde, kendine zarar, siyasi propaganda, hukuki "
             "risk, yaşa uygunluk)"},
    {"key": "BASVURU_ONOKUMA_BENZER", "group": "zeki_ortak", "label": "Başvuru ön okuması: benzer kitap sayısı",
     "type": "int", "default": "5", "help": "Ön okuma taslağındaki «katalogda konusu yakın kitaplar» listesinin uzunluğu"},
    {"key": "BASVURU_ONOKUMA_MIN_OLASILIK", "group": "zeki_ortak", "label": "Başvuru ön okuması: en düşük olasılık",
     "type": "text", "default": "0.70",
     "help": "Tür ve hedef kitle seçiminin olasılığı bunun altındaysa alan boş kalır, «emin değil» yazılır (0–1)"},
    {"key": "BASVURU_ONOKUMA_MIN_FARK", "group": "zeki_ortak", "label": "Başvuru ön okuması: en düşük fark",
     "type": "text", "default": "0.30",
     "help": "Seçilen değer ile ikinci değer arasındaki olasılık farkı bunun altındaysa «emin değil» (0–1)"},
    # M54 Telif dönemi
    {"key": "ROYALTY_CRM_STATUSES", "group": "royalty", "label": "Kapsamdaki CRM durum kodları", "type": "text",
     "default": "100000000,100000007",
     "help": "Dönem koşusuna giren Telif Alış sözleşmelerinin CRM durum kodları (100000000 Aktif-Sözleşme, 100000007 "
             "Aktif-Yenileme, 100000006 Aktif (Proje))"},
    {"key": "ROYALTY_CRM_PAYMENT_TYPES", "group": "royalty", "label": "Kapsamdaki ödeme şekilleri", "type": "text", "default": "2,7",
     "help": "CRM ödeme şekli kodları: 2 Satıştan, 7 Satıştan kademeli. Baskıdan ödemeli sözleşmeler (baskı adedi elle) "
             "sözleşme sayfasında hesaplanır"},
    {"key": "ROYALTY_PERIOD_MONTHS", "group": "royalty", "label": "Telif dönemi (ay)", "type": "int", "default": "6",
     "help": "Yeni koşunun önerilen dönem uzunluğu ve «koşu açılmadı» hatırlatmasının takvimi (6: Ocak–Haziran, Temmuz–Aralık)"},
    {"key": "ROYALTY_WITHHOLDING_PCT", "group": "royalty", "label": "Varsayılan stopaj oranı (%)", "type": "text", "default": "",
     "help": "Sözleşmesinde stopaj oranı olmayan ve bütün tarafları kişi olan sözleşmelere uygulanır. Boşsa stopaj "
             "yalnız sözleşmede oran varsa hesaplanır; oranı muhasebe belirler"},
    {"key": "ROYALTY_RENEWAL_DAYS", "group": "royalty", "label": "Yenileme hatırlatma günleri", "type": "text", "default": "90,60,30",
     "help": "Bitişine bu kadar gün kalan, kararı girilmemiş sözleşmeler günlük özete girer"},
    {"key": "ROYALTY_ADVANCE_RISK_YEARS", "group": "royalty", "label": "Avans geri dönüş eşiği (yıl)", "type": "text",
     "default": "3", "help": "Kalan avans bugünkü telif hızıyla bu kadar yılda kapanmıyorsa «geri dönmesi zor» işaretlenir"},
    {"key": "ROYALTY_RUN_REMIND_WORKDAYS", "group": "royalty", "label": "«Koşu açılmadı» hatırlatması (iş günü)", "type": "int",
     "default": "5", "help": "Dönem bitiminden bu kadar iş günü sonra koşu yoksa özete girer"},
    {"key": "ROYALTY_ALERT_RECIPIENTS", "group": "royalty", "label": "Telif bildirim alıcıları", "type": "text", "default": "",
     "help": "Virgülle iç ekip e-posta adresleri (telif birimi, muhasebe). Koşu hatırlatması, yenileme özeti ve «ödeme listesi "
             "hazır» gider; yazara gönderim yok"},
    # Sözleşme karşılaştırma (emsal kıyası; model yok)
    {"key": "CONTRACT_COMPARE_MIN_PEERS", "group": "contract_compare", "label": "En az emsal sayısı", "type": "int",
     "default": "20", "help": "Kıyas grubu bundan küçükse ölçütler sırayla gevşetilir (dönem, bölüm, para birimi, ödeme türü); "
                             "bir maddede bundan az dolu değer varsa o madde için karar verilmez (3–1000)"},
    {"key": "CONTRACT_COMPARE_RARE_PCT", "group": "contract_compare", "label": "Sapma eşiği (%)", "type": "text",
     "default": "5", "help": "Emsallerin bu yüzdesinden azında görülen değer «emsalden yüksek/düşük» ya da «nadir» "
                             "işaretlenir; emsallerin (100 − eşik) yüzdesinde olan madde bu sözleşmede yoksa «eksik» (1–40)"},
    {"key": "CONTRACT_COMPARE_YEARS", "group": "contract_compare", "label": "Emsal dönemi (yıl)", "type": "int",
     "default": "5", "help": "Başlangıcı sözleşmenin başlangıç yılı ile bu kadar önceki yıl arasındaki sözleşmeler emsal "
                            "olur; ekrandan da değişir (0–60)"},
    {"key": "CONTRACT_COMPARE_TEXT_SIMILAR", "group": "contract_compare", "label": "Serbest metin benzerlik eşiği",
     "type": "text", "default": "0.80", "help": "İki notun ortak kelimelerinin bütün kelimelerine oranı bunun üstündeyse "
                                               "aynı madde sayılır (0,5–1)"},
    {"key": "CONTRACT_COMPARE_TEMPLATE_MIN", "group": "contract_compare", "label": "Kalıp metin eşiği (sözleşme)", "type": "int",
     "default": "5", "help": "Bir not bu kadar ya da daha çok başka sözleşmede de varsa «kalıp metin» sayılır (2–1000)"},
    {"key": "CONTRACT_COMPARE_EXTRA_DIMS", "group": "contract_compare", "label": "Varsayılan ek kıyas ölçütleri", "type": "text",
     "default": "", "help": "Virgülle: ajans (ajans üzerinden), satis (hak sahibinin satış dilimi), hedef (hedef kitle), tur (tür), "
                           "dil (yerli/çeviri). Boşsa yalnız tip, ödeme türü, para birimi, bölüm ve dönem; ekrandan değişir"},
    {"key": "CONTRACT_COMPARE_UPLOAD_DAYS", "group": "contract_compare", "label": "Yüklenen belgenin saklama süresi (gün)",
     "type": "int", "default": "0", "help": "Karşılaştırma için yüklenen belge bu kadar gün sonra dosyasıyla silinir (değişiklik "
                                            "kaydına yazılır). 0 = süresiz; CRM ekleri ve şablonlar silinmez"},
    {"key": "CONTRACT_COMPARE_REFRESH_HOURS", "group": "contract_compare", "label": "CRM görüntüsünün yenilenmesi (saat)",
     "type": "text", "default": "12", "help": "CRM sözleşme görüntüsü bundan eskiyse ilk açılışta arka planda yeniden okunur; "
                                             "ekrandaki «Yenile» hemen okur"},
    # H2 Okur veri tabanı
    {"key": "READERS_EXPORT_ENABLED", "group": "readers", "label": "Liste dışa aktarımı açık", "type": "bool", "default": "0",
     "help": "Rıza metni ve çocuk kayıtları için hukuk teyidi gelince açılır. Kapalıyken segmentler sayılır, liste alınamaz"},
    {"key": "READERS_REQUIRE_KVKK", "group": "readers", "label": "Listede KVKK açık rızası şart", "type": "bool", "default": "1",
     "help": "Açıkken İYS izni olsa da KVKK açık rızası CRM'de işaretli olmayan okur listeye girmez"},
    {"key": "READERS_MINOR_EXPORT", "group": "readers", "label": "18 yaş altı listeye girebilir", "type": "bool", "default": "0",
     "help": "Ebeveyn rızası CRM'de ayrı tutulmuyor; hukuk teyidi olmadan açılmaz"},
    {"key": "READERS_MINOR_AGE", "group": "readers", "label": "Çocuk yaş sınırı", "type": "int", "default": "18", "help": ""},
    {"key": "READERS_IMPORT_RETENTION_DAYS", "group": "readers", "label": "Yükleme satırlarının saklama süresi (gün)",
     "type": "int", "default": "30", "help": "Etkinlik dosyasındaki kişi satırları bu süre sonunda silinir; sayılar kalır"},
    {"key": "READERS_ALERT_RECIPIENTS", "group": "readers", "label": "Okur uyarısı alıcıları", "type": "text", "default": "",
     "help": "Virgülle. Kaynak okunamadı / eskidi ya da birleştirme kuyruğu eşiği aştığında gece özeti"},
    {"key": "READERS_KVKK_RECIPIENTS", "group": "readers", "label": "KVKK irtibat alıcıları", "type": "text", "default": "",
     "help": "Virgülle. Son 24 saatte dışa aktarılan okur listelerinin günlük özeti"},
    {"key": "READERS_CRM_FLAG_RULES", "group": "readers", "label": "CRM izin bayraklarının anlamı (JSON)", "type": "text",
     "default": "", "help": "Boşsa varsayılan: DoNot* = 1 ret, new_kvkkonayi = 1 KVKK onayı, adayda obs_donotkvkk = 1 KVKK ret. "
                           "Biçim: [{\"source\": \"crm_contact\", \"field\": …, \"value\": 1, \"channel\": email|sms|call|kvkk, "
                           "\"status\": ret|izinli}]"},
    {"key": "READERS_IYS_FIELD_CHANNELS", "group": "readers", "label": "İYS alanı → kanal (JSON)", "type": "text", "default": "",
     "help": "Boşsa alan adından (E-POSTA / MESAJ / ARAMA). Biçim: {\"alan kimliği\": \"email|sms|call\"}"},
    {"key": "READERS_CANDIDATE_GROUP_MAX", "group": "readers", "label": "Aynı ad + il grubunda en çok okur", "type": "int",
     "default": "5", "help": "Daha kalabalık gruplar (yaygın ad) birleştirme adayı üretmez; sayısı özet ekranında yazılır"},
    # M37 Okur topluluğu
    {"key": "OKUR_ALERT_RECIPIENTS", "group": "marketing", "label": "Okur topluluğu özeti alıcıları", "type": "text", "default": "",
     "help": "Virgülle iç ekip e-posta adresleri (KVKK sorumlusu, topluluk sorumlusu). Onay bekleyen segment, izin çelişkisi "
             "artışı, yeni cevapsız yorum ve yaklaşan program her gece tek özetle gider; okura hiçbir ileti gitmez"},
    {"key": "OKUR_HASSAS_SEGMENT_ACIK", "group": "marketing", "label": "Özel nitelikli ilgi alanıyla segment", "type": "bool",
     "default": "0",
     "help": "Kapalıyken din/inanç gibi özel nitelikli çağrışım taşıyan ilgi alanları segmentte kullanılamaz (KVKK md. 6). "
             "Yalnız hukuk birimi yazılı karar verirse açılır; açıkken de ayrı açık rıza gerekir"},
    # Okur sesi sınıflayıcı (öneri 15): site yorumu + Trendyol soru/yorum/iade, konu kapalı küme
    {"key": "OKUR_SESI_MIN_OLASILIK", "group": "marketing", "label": "Okur sesi: en düşük olasılık", "type": "text", "default": "0.60",
     "help": "Zeki AI'ın konu seçimi bu olasılığın altındaysa konu boş kalır («belirsiz»). Kör etiketleme örneğiyle ayarlanacak"},
    {"key": "OKUR_SESI_MIN_FARK", "group": "marketing", "label": "Okur sesi: en düşük fark", "type": "text", "default": "0.20",
     "help": "Seçilen konuyla ikinci en olası konu arasındaki en düşük olasılık farkı"},
    {"key": "OKUR_SESI_BASKI_GUN", "group": "marketing", "label": "Baskı hatası kümesi penceresi (gün)", "type": "int", "default": "90",
     "help": "Aynı kitapta bu kadar gün içindeki «baskı / cilt hatası» okur metinleri sayılır"},
    {"key": "OKUR_SESI_BASKI_ESIK", "group": "marketing", "label": "Baskı hatası kümesi eşiği (kayıt)", "type": "int", "default": "3",
     "help": "Pencerede aynı kitap için bu kadar ve üstü baskı/cilt hatası metni üretime iç uyarı açar"},
    {"key": "OKUR_SESI_URETIM_ALICI", "group": "marketing", "label": "Baskı hatası uyarısı alıcıları (üretim)", "type": "text",
     "default": "", "help": "Virgülle iç e-posta adresleri (üretim/baskı sorumlusu). Boşsa uyarı yalnız ekranda (okur sesi paneli, "
                           "Kampüs «Bugün» özeti) görünür; okura ya da matbaaya hiçbir şey gitmez"},
    {"key": "OKUR_SESI_OZET_GUN", "group": "marketing", "label": "Okur sesi özet penceresi (gün)", "type": "int", "default": "90",
     "help": "Kaynak × konu sayıları bu kadar günlük kayıttan"},
    {"key": "OKUR_SESI_MODEL_SURE_SN", "group": "marketing", "label": "Okur sesi gece model süresi (sn)", "type": "int",
     "default": "900", "help": "Gece turunda Zeki AI sınıflamasına ayrılan süre; biten iş sonraki geceye kalır (kayıp yok)"},
    # M16 Lansman
    {"key": "MARKETING_LAUNCH_OPEN_DAYS", "group": "marketing", "label": "Lansmanın açılması (gün)", "type": "int", "default": "14",
     "help": "Onaylı pazarlama planı olan kitabın lansman paketi yayına bu kadar gün kala kendiliğinden açılır (elle her zaman açılır)"},
    {"key": "MARKETING_LAUNCH_PRE_DAYS", "group": "marketing", "label": "Lansman izlemesi yayından önce (gün)", "type": "int",
     "default": "14", "help": "İzleme grafiği ve ön sipariş sayımı yayın gününden bu kadar gün önce başlar"},
    {"key": "MARKETING_LAUNCH_ALERT_RATIO", "group": "marketing", "label": "Lansman hedef eşiği (%)", "type": "int", "default": "80",
     "help": "İlk günlerde satış (Logo verisi yoksa sipariş) hedefin o güne düşen payının bu oranının altındaysa lansman kırmızı "
             "olur ve sahibine günlük özette yazılır (bütçe modülünün sapma kuralıyla aynı varsayılan)"},
    {"key": "MARKETING_LAUNCH_ORDER_EXCLUDE", "group": "marketing", "label": "Sayılmayan sipariş durumları", "type": "text",
     "default": "1,100000001", "help": "CRM sipariş durum kodları (virgülle): 1 Taslak, 100000001 İptal Edildi. Birleştirilen "
                                       "siparişler (100000003) çift sayılıyorsa buraya eklenir"},
    {"key": "MARKETING_LAUNCH_STOCK_RECIPIENTS", "group": "marketing", "label": "Stok uyarısı alıcıları (satış)", "type": "text",
     "default": "", "help": "Açık sipariş depo stokunu aşınca ya da yayından sonra dağılım siparişi yoksa anında giden e-postanın "
                            "alıcıları (virgülle); lansman sahibine de gider. Kitap başına günde en çok bir kez"},
    {"key": "MARKETING_LAUNCH_EMSAL_RATIO", "group": "marketing", "label": "Lansman risk: emsal eşiği (%)", "type": "int",
     "default": "70", "help": "Aynı gün sayısında birikmiş satış (Logo yoksa sipariş) emsallerin ortalama eğrisinin bu oranının "
                             "altındaysa lansman risk bayrağına «emsal sapması» nedeni düşer"},
    {"key": "MARKETING_LAUNCH_ORDER_DAYS", "group": "marketing", "label": "Lansman risk: siparişsiz gün", "type": "int",
     "default": "3", "help": "Yayından bu kadar gün sonra CRM'de hiç sipariş yoksa risk bayrağına «sipariş yok» nedeni düşer"},
    {"key": "MARKETING_LAUNCH_DAILY_HOUR", "group": "marketing", "label": "Lansman günlük okuma saati", "type": "int", "default": "7",
     "help": "Logo satış ve depo okuması, D+7/D+30 raporu ve günlük özet bu saatten sonraki ilk koşuda yapılır; sipariş saatte bir okunur"},
    {"key": "MARKETING_LAUNCH_TASKS", "group": "marketing", "label": "Lansman kontrol listesi (JSON)", "type": "text", "default": "",
     "help": "Planın takvimine eklenen lansman maddeleri. Boşsa varsayılan. Biçim: [[gün, \"iş\", \"kanal\", \"materyal\"], …]"},
    # M17 Backlist (backlist kümesi M46'nın backlist segmentidir; aşağıdaki yaş eşiği yalnız o yıl onaylı bütçe planı yoksa)
    {"key": "MARKETING_BACKLIST_MIN_MONTHS", "group": "marketing", "label": "Backlist yaşı (ay)", "type": "int", "default": "12",
     "help": "Onaylı bütçe planı olmayan yılda backlist: ilk yayını veri sonundan en az bu kadar ay önce olan kitaplar"},
    {"key": "MARKETING_BACKLIST_AGENDA_WEEKS", "group": "marketing", "label": "Backlist gündem penceresi (hafta)", "type": "int",
     "default": "8", "help": "Gündem sekmesi ve fırsat listesindeki «yakın özel gün» süzgeci"},
    {"key": "MARKETING_BACKLIST_REMIND_WEEKS", "group": "marketing", "label": "Özel gün hatırlatması (hafta)", "type": "int",
     "default": "6", "help": "Özel güne bu kadar hafta kala bağlı, stoklu ve aktivasyonu olmayan kitaplar e-postayla bildirilir"},
    {"key": "MARKETING_BACKLIST_DIGEST_MIN", "group": "marketing", "label": "Aylık özet endeks eşiği", "type": "int", "default": "70",
     "help": "Ayın ilk iş günü özetinde sayılan kitapların en düşük uyku endeksi (0–100)"},
    # M20 Basın ilişkileri (aynı grup)
    {"key": "PR_ALERT_RECIPIENTS", "group": "marketing", "label": "Basın ilişkileri bildirim alıcıları", "type": "text",
     "default": "", "help": "Virgülle iç e-posta adresleri (pazarlama müdürü, basın sorumlusu). Onaya gönderilen basın dosyası ve "
                            "takip günü geçen cevapsız gönderimler buraya gider (dosya sahibine ayrıca). Gazeteciye hiçbir şey "
                            "kendiliğinden gitmez"},
    {"key": "PR_REPORT_RECIPIENTS", "group": "marketing", "label": "Haftalık yansıma özeti alıcıları", "type": "text",
     "default": "", "help": "Virgülle iç e-posta adresleri. Boşsa bildirim alıcılarına gider; ikisi de boşsa özet gönderilmez"},
    {"key": "PR_REPORT_WEEKDAY", "group": "marketing", "label": "Haftalık yansıma özeti günü", "type": "int", "default": "1",
     "help": "1 = pazartesi … 7 = pazar. O günün sabah turunda bir önceki haftanın (pazartesi–pazar) özeti gider"},
    {"key": "PR_FOLLOW_UP_DAYS", "group": "marketing", "label": "Basın gönderimi takip süresi (gün)", "type": "int", "default": "5",
     "help": "Gönderimden bu kadar gün sonra cevap yoksa satır «takip günü geçti» olur ve hatırlatmaya girer"},
    {"key": "PR_CRM_MEDIA_ROLES", "group": "marketing", "label": "CRM'de gazeteci kişi rolleri", "type": "text", "default": "",
     "help": "CRM «Kişi Rolü» adları (virgülle; ör. Gazeteci). Bu rollere bağlı kişiler de medya kişisi sayılır. Boşsa yalnız "
             "«Basın medya Mecrası» dolu kişiler ve CRM haber kayıtlarında haberi yapan/görüşülen kişiler gelir"},
    {"key": "PR_TONE_MIN_PROB", "group": "marketing", "label": "Yansıma tonu: en düşük olasılık", "type": "text", "default": "0.6",
     "help": "Zeki AI yansımanın tonunu bu olasılığın altında önermez; ton boş kalır, kullanıcı seçer"},
    # M21 Dijital pazarlama ve reklam. Eşiği boş bırakılan öneri kuralı çalışmaz.
    {"key": "ADS_ALERT_RECIPIENTS", "group": "ads", "label": "Reklam bildirim alıcıları", "type": "text", "default": "",
     "help": "Virgülle e-posta adresleri. Günlük işte çıkan yeni öneri ve uyarılar (stok, satıştan kalkan kitap, veri gelmedi, "
             "bütçe aşımı, durdurma/kaydırma) buraya gider. Boşsa e-posta gitmez; öneriler ekranda durur"},
    {"key": "ADS_ECOM_CHANNELS", "group": "ads", "label": "E-ticaret kanal kodları", "type": "text", "default": "E-TICARET",
     "help": "Logo cari kartındaki özel kod 2 (satış kanalı) değerleri, virgülle. Pazarlama verimi bu kanalların net cirosuyla "
             "hesaplanır. İnternet satışı başka bir kodla da tutuluyorsa ekleyin (ör. E-TICARET,INTERNET)"},
    {"key": "ADS_STOCK_DAYS", "group": "ads", "label": "Stok uyarısı (gün)", "type": "text", "default": "14",
     "help": "Reklamı süren kitabın stoğu bu kadar günlük satışı karşılamıyorsa (ya da bakiye sıfırsa) uyarı. Boşsa yalnız "
             "stoğu biten kitap için uyarı"},
    {"key": "ADS_VELOCITY_DAYS", "group": "ads", "label": "Satış hızı penceresi (gün)", "type": "int", "default": "60",
     "help": "Günlük satış hızı = Logo verisinin bittiği güne kadar bu kadar günün bütün kanallardaki net adedi ÷ gün"},
    {"key": "ADS_ACTIVE_DAYS", "group": "ads", "label": "«Reklam sürüyor» penceresi (gün)", "type": "int", "default": "3",
     "help": "Son bu kadar günde harcaması olan kampanya açık sayılır (stok ve satış dışı uyarıları için)"},
    {"key": "ADS_NO_DATA_DAYS", "group": "ads", "label": "«Veri gelmedi» uyarısı (gün)", "type": "int", "default": "2",
     "help": "Hesabın son harcama günü bundan eskiyse uyarı (son 30 günde verisi olan hesaplar)"},
    {"key": "ADS_OFF_SALE_STATUS", "group": "ads", "label": "Satış dışı yayın durumları", "type": "text",
     "default": "YS01,YS05,YS06,YS11,YS12",
     "help": "CRM yayıncılık durumu kodları (etiketin başındaki YS kodu). Bu durumdaki kitaba reklam sürüyorsa uyarı"},
    {"key": "ADS_OVERSPEND_PCT", "group": "ads", "label": "Bütçe aşımı payı (%)", "type": "text", "default": "0",
     "help": "Ayın harcaması ay sonuna taşındığında kanal planını bu yüzdeden fazla aşarsa uyarı. Plan girilmemiş kanal için "
             "uyarı çıkmaz"},
    {"key": "ADS_PERF_WINDOW_DAYS", "group": "ads", "label": "Performans penceresi (gün)", "type": "int", "default": "14",
     "help": "Durdurma ve kaydırma önerileri son bu kadar günün harcaması ve dönüşümüyle hesaplanır"},
    {"key": "ADS_STOP_MIN_SPEND", "group": "ads", "label": "Durdurma önerisi: en az harcama (TL)", "type": "text", "default": "",
     "help": "Pencerede bu tutardan fazla harcayıp hiç dönüşümü olmayan kampanya için durdurma önerisi. Boşsa kural kapalı"},
    {"key": "ADS_STOP_MAX_ROAS", "group": "ads", "label": "Durdurma önerisi: platform ROAS altı", "type": "text", "default": "",
     "help": "Doluysa platform ROAS'ı bunun altında kalan kampanya da durdurma önerisine girer (harcama eşiği aşılmışsa)"},
    {"key": "ADS_SHIFT_MIN_SPEND", "group": "ads", "label": "Kaydırma önerisi: en az harcama (TL)", "type": "text", "default": "",
     "help": "Aynı kanalda pencerede bu tutardan fazla harcayan kampanyalar karşılaştırılır. Boşsa kural kapalı"},
    {"key": "ADS_SHIFT_ROAS_RATIO", "group": "ads", "label": "Kaydırma önerisi: ROAS oranı", "type": "text", "default": "2",
     "help": "En yüksek platform ROAS'ı en düşüğün bu katıysa kaydırma önerilir"},
    {"key": "ADS_SHIFT_SHARE", "group": "ads", "label": "Kaydırma önerisi: pay (%)", "type": "text", "default": "20",
     "help": "Önerilen tutar = düşük kampanyanın pencere harcaması × bu pay"},
    {"key": "ADS_M15_CHANNEL_MAP", "group": "ads", "label": "M15 plan kanalı eşlemesi", "type": "text",
     "default": "google=dijital,meta=sosyal-medya,tiktok=sosyal-medya,pazaryeri=dijital,diger=dijital",
     "help": "Reklam kanalı = yeni kitap pazarlama planındaki kanal. Bütçe ekranı onaylı planların bu kanallardaki satırlarını gösterir"},
    {"key": "ADS_LOOKBACK_DAYS", "group": "ads", "label": "Satış önbelleği penceresi (gün)", "type": "int", "default": "400",
     "help": "Logo e-ticaret cirosu ve kitap satışı veri sonundan bu kadar gün geri okunur; ilk reklam günü daha eskiyse ondan"},
    {"key": "ADS_DATE_ORDER", "group": "ads", "label": "Dosyada tarih sırası", "type": "text", "default": "gun-ay",
     "help": "01/09/2026 gibi eğik çizgili tarihlerde: gun-ay (Türkçe) ya da ay-gun (İngilizce dışa aktarım)"},
    {"key": "ADS_IMPORT_MAX_MB", "group": "ads", "label": "Yükleme dosyası sınırı (MB)", "type": "text", "default": "50",
     "help": "Bundan büyük dosya reddedilir ve ekranda söylenir"},
    {"key": "ADS_LINK_MIN_PROB", "group": "ads", "label": "Kitap önerisi en az olasılık", "type": "text", "default": "0.70",
     "help": "Zeki AI kampanya adından kitap önerirken bu olasılığın altındaysa öneri yazılmaz; aday listesi elle seçilir"},
    {"key": "ADS_LINK_MIN_MARGIN", "group": "ads", "label": "Kitap önerisi en az fark", "type": "text", "default": "0.30",
     "help": "Seçilen kitabın olasılığı ikinci adaydan en az bu kadar yüksek olmalı"},
    # Sosyal medya (M22). Otomatik yayın yok; platformlara hiçbir istek gitmez.
    {"key": "SOCIAL_ALERT_RECIPIENTS", "group": "social", "label": "Sosyal medya bildirim alıcıları", "type": "text", "default": "",
     "help": "Virgülle iç e-posta adresleri (pazarlama müdürü, onaycılar). Onaya gönderilen gönderi ve her sabah 07:00 özeti "
             "(yarın hazır olmayan gönderi, yaklaşan özel gün, onay bekleyen) buraya gider. Boşsa gönderilmez"},
    {"key": "SOCIAL_OPPORTUNITY_DAYS", "group": "social", "label": "Fırsat penceresi (gün)", "type": "int", "default": "30",
     "help": "«Fırsatlar» ekranı bugünden bu kadar gün ilerideki özel günleri ve yeni çıkan kitapları gösterir (ekranda değişir)"},
    {"key": "SOCIAL_OCCASION_LEAD_DAYS", "group": "social", "label": "Özel gün uyarısı (gün)", "type": "int", "default": "14",
     "help": "Özel güne bu kadar gün ya da daha az kalmışken bağlı kitaplardan hiçbiri takvimde değilse uyarı verilir"},
    {"key": "SOCIAL_BACKLIST_MIN_AGE_DAYS", "group": "social", "label": "Backlist sayılma (gün)", "type": "int", "default": "365",
     "help": "İlk yayını bu kadar günden eski kitap backlist sayılır"},
    {"key": "SOCIAL_BACKLIST_QUIET_DAYS", "group": "social", "label": "Uzun süredir paylaşılmayan (gün)", "type": "int",
     "default": "90", "help": "Son 12 ayda çok satan backlist kitaplardan bu kadar gündür takvimde gönderisi olmayanlar önerilir"},
    {"key": "SOCIAL_BACKLIST_EXCLUDE_STATUS", "group": "social", "label": "Önerilmeyecek kitap statüleri", "type": "text",
     "default": "", "help": "Virgülle CRM kitap statüleri (ör. baskısı tükenmiş). Bu statüdeki kitaplar backlist önerisine girmez"},
    {"key": "SOCIAL_PLATFORM_LIMITS", "group": "social", "label": "Platform sınırları (JSON)", "type": "text", "default": "",
     "help": "Boşsa: Instagram 2200, Facebook 63206, X 280, LinkedIn 3000, TikTok 2200, YouTube 5000 karakter; Instagram 30 "
             "etiket. Değiştirmek için ör. {\"x\": 280, \"instagram:etiket\": 30}"},
    {"key": "SOCIAL_DEFAULT_HOUR", "group": "social", "label": "Varsayılan paylaşım saati", "type": "time", "default": "10:00",
     "help": "Yalnız gün seçilen gönderinin saati (SS:DD)"},
    {"key": "SOCIAL_BANNED_CLAIMS", "group": "social", "label": "Ek yasaklı ifadeler", "type": "text", "default": "",
     "help": "Zeki AI taslağında geçerse cümlenin düşeceği ek ifadeler (virgülle). Kanıtsız üstünlük iddiaları zaten yasak"},
    # İşbirlikleri (M23: içerik üreticisi kayıt defteri, işbirliği panosu, ödeme listesi)
    {"key": "INFLUENCER_ALERT_RECIPIENTS", "group": "influencer", "label": "Hatırlatma alıcıları", "type": "text", "default": "",
     "help": "Virgülle iç ekip e-posta adresleri (işbirliği sorumlusu). Yayın tarihi yaklaşan, bağlantısı girilmemiş, içerik onayı "
             "bekleyen işler ve takipçi sıçraması her sabah tek özetle gider; içerik üreticisine hiçbir e-posta gitmez"},
    {"key": "INFLUENCER_APPROVAL_RECIPIENTS", "group": "influencer", "label": "Onay bildirimi alıcıları", "type": "text", "default": "",
     "help": "Virgülle (pazarlama müdürü). Onay bekleyen teklif ve aylık bütçe uyarısı. Boşsa hatırlatma alıcılarına gider"},
    {"key": "INFLUENCER_PAYOUT_RECIPIENTS", "group": "influencer", "label": "Ödeme listesi alıcıları", "type": "text", "default": "",
     "help": "Virgülle (muhasebe). Ödeme günü geldiğinde onay/ödeme bekleyen satır varsa bildirim"},
    {"key": "INFLUENCER_PAYOUT_DAY", "group": "influencer", "label": "Ödeme listesi günü", "type": "int", "default": "25",
     "help": "Ayın bu gününden itibaren bekleyen ödeme satırı varsa muhasebeye bir kez bildirim gider (1–28)"},
    {"key": "INFLUENCER_MONTHLY_BUDGET", "group": "influencer", "label": "Aylık işbirliği bütçesi (₺)", "type": "text", "default": "",
     "help": "Boşsa bütçe uyarısı yok. Onaylı işbirliklerinin o aya düşen ücret toplamı eşiği geçince müdüre uyarı"},
    {"key": "INFLUENCER_BUDGET_WARN_PCT", "group": "influencer", "label": "Bütçe uyarı eşiği (%)", "type": "text", "default": "90",
     "help": "Aylık bütçenin bu yüzdesine ulaşılınca uyarı"},
    {"key": "INFLUENCER_COOLDOWN_DAYS", "group": "influencer", "label": "İki işbirliği arası (gün)", "type": "int", "default": "60",
     "help": "Son işbirliği bundan yeni olan kişi aday sırasında «tazelik» puanı almaz"},
    {"key": "INFLUENCER_RANK_WEIGHTS", "group": "influencer", "label": "Aday puanı ağırlıkları (JSON)", "type": "text", "default": "",
     "help": "Boşsa {\"konu\":35,\"yas\":15,\"performans\":20,\"iliski\":10,\"tazelik\":10,\"butce\":10}. Puan bu ağırlıklarla 0–100"},
    {"key": "INFLUENCER_TOPIC_WORDS", "group": "influencer", "label": "Konu kelimeleri (JSON)", "type": "text", "default": "",
     "help": "Kitabın CRM tür/raf/hedef kitle metninden konu çıkaran kelimelere ek: {\"tarih\": [\"savaş\"], …}"},
    {"key": "INFLUENCER_TOPIC_MIN_PROB", "group": "influencer", "label": "Zeki AI konu eşiği", "type": "text", "default": "0.70",
     "help": "Konu önerisinin kabul edileceği en düşük olasılık"},
    {"key": "INFLUENCER_JUMP_PCT", "group": "influencer", "label": "Takipçi sıçraması (%)", "type": "text", "default": "30",
     "help": "Kendi iki ölçümümüz arasında (en çok 45 gün) takipçi bu yüzdeden fazla artarsa uyarı. Sahte takipçi puanı değildir"},
    {"key": "INFLUENCER_CONTENT_WAIT_DAYS", "group": "influencer", "label": "İçerik onayı bekleme (gün)", "type": "int", "default": "3",
     "help": "İçerik taslağı bu kadar gündür «onayda» ise hatırlatma"},
    {"key": "INFLUENCER_LINK_GRACE_DAYS", "group": "influencer", "label": "Bağlantı gecikmesi (gün)", "type": "int", "default": "2",
     "help": "Planlanan yayın tarihinden bu kadar gün sonra paylaşım bağlantısı yoksa hatırlatma"},
    {"key": "INFLUENCER_DISCLOSURE_KINDS", "group": "influencer", "label": "Yasal etiket zorunlu türler", "type": "text",
     "default": "hediye,ucretli,karsilikli",
     "help": "Bu türlerde «yasal etiket var» işaretlenmeden rapora geçilmez (hediye, ucretli, karsilikli). Hukuka doğrulatılacak"},
    {"key": "INFLUENCER_GIFT_NEEDS_APPROVAL", "group": "influencer", "label": "Hediye kitap da onaylı", "type": "bool", "default": "1",
     "help": "Açıkken hediye kitap gönderimi de müdür onayı olmadan ilerlemez; ücretli ve karşılıklı her zaman onaylı"},
    {"key": "INFLUENCER_API_ENABLED", "group": "influencer", "label": "Resmî API ile hesap sayıları", "type": "bool", "default": "0",
     "help": "İkinci sürüm. Kapalıyken sayılar elle ya da dosyayla girilir; müşteri ortamında kullanıcı kararı olmadan açılmaz"},
    # Katalog ve bülten (M24)
    {"key": "CATALOG_PRICE_SOURCE", "group": "catalog", "label": "Katalog fiyatı kaynağı", "type": "text", "default": "crm",
     "help": "crm = CRM kitap kartı KDV dahil fiyat (varsayılan; kayıtlı liste fiyatı, ihale tablosuyla aynı alan), crm-perakende "
             "= CRM perakende birim fiyat, crm-uzeri = kitabın üzerindeki fiyat (Baskı önerisi raporu), logo = son B2B/CRM satış "
             "faturasının birim fiyatı, tsoft = web sitesi satış fiyatı. Yeni katalog bunu alır; katalog başına değiştirilir"},
    {"key": "CATALOG_STOCK_SOURCE", "group": "catalog", "label": "Stok kaynağı", "type": "text", "default": "crm",
     "help": "crm = CRM stok adedi (Baskı önerisi «Tükenme süresi» ile aynı), logo = Logo depo stoku. Stok ay sayısı = stok ÷ "
             "ağırlıklı aylık satış hızı"},
    {"key": "CATALOG_BOOK_TYPES", "group": "catalog", "label": "Katalog havuzundaki ürün tipleri", "type": "text", "default": "1,4",
     "help": "CRM kitap kartı tipi, virgülle: 1 Kitap, 4 Set, 5 Dergi, 8 E-kitap, 9 Sesli kitap"},
    {"key": "CATALOG_CRITICAL_STOCK_MONTHS", "group": "catalog", "label": "Kritik stok (ay)", "type": "text", "default": "1",
     "help": "Katalogdaki kitabın stoku bu kadar aydan az yetiyorsa kritik uyarı"},
    {"key": "CATALOG_TARGET_STOCK_MONTHS", "group": "catalog", "label": "Öneride yeterli stok (ay)", "type": "text", "default": "6",
     "help": "Öneri puanında stok parçası bu aya ulaşınca tam puan alır"},
    {"key": "CATALOG_NEW_MONTHS", "group": "catalog", "label": "Yeni kitap penceresi (ay)", "type": "int", "default": "12",
     "help": "İlk baskısı bu kadar ay içinde olan kitap «yeni» sayılır ve yenilik puanı alır"},
    {"key": "CATALOG_SCORE_WEIGHTS", "group": "catalog", "label": "Öneri puanı ağırlıkları (JSON)", "type": "text", "default": "",
     "help": "Boşsa {\"hiz\": 40, \"stok\": 20, \"yenilik\": 20, \"ozelgun\": 20}. Ölçülemeyen parça dışarıda kalır"},
    {"key": "CATALOG_TEXT_WORDS", "group": "catalog", "label": "Katalog metni (kelime)", "type": "int", "default": "60",
     "help": "Zeki AI tanıtım metnini en çok bu kadar kelimeye kısaltır"},
    {"key": "CATALOG_PDF_PER_PAGE", "group": "catalog", "label": "PDF önizlemede sayfa başına kitap", "type": "int", "default": "6",
     "help": "1–12; ekranda indirirken değiştirilir"},
    {"key": "CATALOG_ALERT_RECIPIENTS", "group": "catalog", "label": "Katalog uyarısı alıcıları", "type": "text", "default": "",
     "help": "Virgülle iç e-posta adresleri (katalog sorumlusu, pazarlama müdürü). Kritik fiyat/stok uyarısı ve onay bekleyen "
             "katalog/bülten her sabah tek özetle gider; okura ya da bayiye hiçbir gönderim yok"},
    {"key": "NEWSLETTER_REQUIRE_KVKK", "group": "catalog", "label": "Segmentte KVKK onayı şart", "type": "bool", "default": "0",
     "help": "Açıksa segment sayısına yalnız KVKK onayı da olan kişi girer. İYS onayı, e-posta izni ve toplu e-posta izni her "
             "durumda şarttır"},
    {"key": "NEWSLETTER_SUBJECT_OPTIONS", "group": "catalog", "label": "Konu satırı seçeneği", "type": "int", "default": "5",
     "help": "Zeki AI'ın bülten için önereceği konu satırı sayısı"},
    {"key": "NEWSLETTER_INTEREST_KEYWORDS", "group": "catalog", "label": "İlgi alanı → kitap türü sözcükleri (JSON)", "type": "text",
     "default": "", "help": "Kişi kartındaki ilgi bayrağının kitabın tür/Kitaplık/web kategorisinde aranan sözcükleri, örn. "
                            "{\"new_tarihveakademi\": [\"tarih\", \"akademi\"]}. Boşsa varsayılan eşleme"},
    # İnsan kaynakları (İK-0 + M55)
    {"key": "HR_RECRUIT_SLA_DAYS", "group": "hr", "label": "Aşamada bekleme eşiği (gün)", "type": "text", "default": "",
     "help": "Aday bir aşamada bundan uzun kalırsa panoda sayılır ve İK alıcılarına aday bilgisi içermeyen özet gider. Boş: eşik yok"},
    {"key": "HR_ALERT_RECIPIENTS", "group": "hr", "label": "İK bildirim alıcıları", "type": "text", "default": "",
     "help": "Virgülle iç e-posta adresleri. Adaya hiçbir e-posta gönderilmez; mektupları İK kendisi gönderir"},
    {"key": "HR_ADMIN_SEES_PERSONAL", "group": "hr", "label": "Yönetici aday verisini rolsüz görsün", "type": "bool", "default": "0",
     "help": "Kapalıyken (önerilen) portal yöneticisi aday kişisel verisini, KVKK yönetimini ve İK erişim kaydını ancak kendine "
             "rol bağlarsa görür; bağ değişiklik kaydına düşer"},
    {"key": "HR_FILE_MAX_MB", "group": "hr", "label": "Özgeçmiş dosyası üst boyutu (MB)", "type": "int", "default": "20",
     "help": "Bozuk ya da kötü niyetli yüklemeye karşı; aşan dosya reddedilir ve nedeni yazılır"},
    {"key": "HR_COMPANY_NAME", "group": "hr", "label": "Mektuplarda şirket adı", "type": "text", "default": "Timaş Yayınları",
     "help": "Şablonlardaki {{sirket}} alanı"},
    {"key": "HR_CRM_UNIT_MANAGER_COLUMN", "group": "hr", "label": "CRM birim yöneticisi kolonu", "type": "text",
     "default": "new_departmanyoneticisiid",
     "help": "BusinessUnitBase'te departman yöneticisini tutan kolon. Okunamazsa eşitleme yöneticisiz sürer ve not düşer"},
    # M57 Eğitim ve gelişim
    {"key": "HR_LEARNING_ALERT_DAYS", "group": "hr", "label": "Zorunlu eğitim uyarısı (gün önce)", "type": "text", "default": "",
     "help": "Sertifika geçerliliği bitmeden kaç gün önce «dolacak» sayılsın ve sabah özetine girsin. Boş: yalnız süresi dolmuş olanlar"},
    {"key": "HR_PRIVACY_MIN_GROUP", "group": "hr", "label": "Gizlilik eşiği (kişi)", "type": "text", "default": "",
     "help": "Kullanım haritasında bu sayıdan az çalışanı olan birimler birleştirilir; anket sonucu bu sayıdan az yanıtta "
             "gösterilmez. Boş: 5 kişi. 0: birleştirme bilerek kapalı"},
    {"key": "HR_TRAINING_ACCOUNTS", "group": "hr", "label": "Eğitim gider hesapları (Logo)", "type": "text", "default": "",
     "help": "Virgülle 7'li gider hesap kodları; alt hesaplar dahil sayılır. Adayları Eğitim → Gider ekranı listeler (Mali İşler seçer)"},
    # İnsan kaynakları — M56 performans, M58 bağlılık
    {"key": "HR_PERF_LOGO_SALES", "group": "hr", "label": "Hedefte Logo satış ölçüsü", "type": "bool", "default": "0",
     "help": "Açıksa satış hedefinin ilerlemesi Logo'daki temsilci bazında faturalı net satıştan okunur. Satış faturalarında "
             "temsilci alanı doluluğu ölçülmeden açmayın (Değerlendirme dönemi ekranındaki ölçüm)"},
    {"key": "HR_PERF_REMIND_DAYS", "group": "hr", "label": "Değerlendirme hatırlatması (gün kala)", "type": "text", "default": "",
     "help": "Açık dönemde son tarihe bu kadar gün kala İK alıcılarına eksik sayılarıyla tek özet (kişi adı yok). Boş: gönderim yok"},
    {"key": "HR_SURVEY_SHUFFLE_MAX_SEC", "group": "hr", "label": "Anket cevabı yazım gecikmesi (sn, en çok)", "type": "int", "default": "20",
     "help": "Cevap ve yorum, «cevapladı» işaretinden ayrı ve rastgele gecikmeyle yazılır ki sıra/zaman eşlemesi yapılamasın"},
    {"key": "HR_SURVEY_THEMES", "group": "hr", "label": "Anket yorum temaları", "type": "text", "default": "",
     "help": "Virgülle kapalı tema listesi; Zeki AI açık uçlu yorumları bu listeye sınıflar. Boşsa varsayılan liste"},
    {"key": "HR_SUGGESTION_TOPICS", "group": "hr", "label": "Öneri kutusu konuları", "type": "text", "default": "",
     "help": "Virgülle konu listesi; «Bir çalışanla ilgili şikâyet» her zaman İK'da kalır. Boşsa varsayılan liste"},
    # Platform ve kanallar (M42; M40/M41 bağlantı anahtarlarını aynı gruba ekler)
    {"key": "CHANNEL_SPECODES", "group": "channels", "label": "E-ticaret kanal kodları", "type": "text", "default": "E-TICARET",
     "help": "Logo cari kartındaki özel kod 2 değerleri (virgülle). Bu kodlu cariler eşleme listesine ve kanal karnesine girer"},
    {"key": "CHANNEL_YEARS", "group": "channels", "label": "Okunan yıl sayısı", "type": "int", "default": "2",
     "help": "Verinin son yılı ve öncesi; geçen yılla kıyas için en az 2"},
    {"key": "CHANNEL_RETURN_THRESHOLD", "group": "channels", "label": "İade oranı uyarı eşiği", "type": "text", "default": "0.10",
     "help": "Oran (0,10 = %10). Platformun yıl içi iade oranı bunu aşarsa pazartesi uyarısı. Ölçülmemiş başlangıç değeridir"},
    {"key": "CHANNEL_DISCOUNT_RISE_PTS", "group": "channels", "label": "İskonto artışı uyarısı (puan)", "type": "text", "default": "2",
     "help": "İskonto oranı geçen yılın aynı dönemine göre bu kadar puandan çok artarsa uyarı"},
    {"key": "CHANNEL_REPORT_RECIPIENTS", "group": "channels", "label": "Kanal karnesi ve uyarı alıcıları", "type": "text", "default": "",
     "help": "Virgülle iç e-posta adresleri. Ayın 2'si aylık karne, pazartesi uyarı özeti. Boşsa e-posta gitmez, uyarı ekranda kalır"},
    {"key": "CHANNEL_MAP_MIN_PROB", "group": "channels", "label": "Eşleme adayı en düşük olasılık", "type": "text", "default": "0.70",
     "help": "Zeki AI'ın cari için seçtiği platform bu olasılığın altındaysa aday gösterilmez («emin değil»)"},
    {"key": "CHANNEL_MAP_MIN_MARGIN", "group": "channels", "label": "Eşleme adayı en düşük fark", "type": "text", "default": "0.30",
     "help": "Seçilen platformla ikinci en olası seçenek arasındaki en düşük olasılık farkı"},
    {"key": "CHANNEL_PLATFORM_HINTS", "group": "channels", "label": "Platform işletmeci unvanları (JSON)", "type": "text", "default": "",
     "help": "Boşsa varsayılan. Biçim: {\"hepsiburada\": [\"D-MARKET\"], \"dr\": [\"TURKUVAZ\"]}. Unvanda geçerse aday olur; onay yine gerekir"},
    {"key": "CHANNEL_ORDER_DAYS", "group": "channels", "label": "CRM sipariş sayımı (gün)", "type": "int", "default": "180",
     "help": "Kanal detayındaki CRM sipariş tipi sayıları (Pazaryeri, Amazon Konsinye, B2C) bu kadar günlük pencereden"},
    {"key": "CHANNEL_D2C_MIN_ADET", "group": "channels", "label": "D2C güçlü kitap: en az adet", "type": "text", "default": "20",
     "help": "Sitede bu kadar net adetten az satan kitap «D2C'de güçlü» listesine girmez"},
    {"key": "CHANNEL_D2C_INDEX", "group": "channels", "label": "D2C güçlü kitap: pay katı", "type": "text", "default": "1.5",
     "help": "Kitabın D2C payı, bütün kitaplardaki D2C payının en az bu katıysa listeye girer"},
    {"key": "CHANNEL_TARGET_YEAR_CODES", "group": "channels", "label": "CRM hedef yılı kodları", "type": "text", "default": "",
     "help": "Boşsa CRM seçim listesinden okunur. Elle: 2025:3,2026:100000000"},
    # M39 Pazar araştırması ve rekabet
    {"key": "PAZAR_ALERT_RECIPIENTS", "group": "pazar", "label": "Bildirim alıcıları", "type": "text", "default": "",
     "help": "Virgülle iç e-posta adresleri (pazarlama müdürü, yönetim): özet taslağı hazır, onay bekliyor, onaylandı ve "
             "rakip verisi eski uyarısı. Boşsa e-posta gitmez"},
    {"key": "PAZAR_STALE_DAYS", "group": "pazar", "label": "Rakip verisi eski sayılır (gün)", "type": "int", "default": "180",
     "help": "CRM rakip kitap kayıtlarının son eklenme/değişme tarihinden bu yana geçen gün bu sayıyı aşınca ekranda "
             "uyarı ve haftalık e-posta. Ekipçe belirlenecek"},
    {"key": "PAZAR_NEW_DAYS", "group": "pazar", "label": "«Yeni kayıt» penceresi (gün)", "type": "int", "default": "365",
     "help": "Matristeki yeni kayıt sayısı: CRM'e bu kadar gün içinde eklenen rakip kitap"},
    {"key": "PAZAR_CATEGORY_SOURCE", "group": "pazar", "label": "TİMAŞ kategori listesi", "type": "text", "default": "auto",
     "help": "auto: yürürlükte kategori ağacı varsa ağaç, yoksa CRM Kitaplık; agac; kitaplik. Değişince onaylı eşlemelerin "
             "karşılığı kalmayanlar yeniden öneriye düşer"},
    {"key": "PAZAR_CATEGORY_LEVELS", "group": "pazar", "label": "Ağaçtan alınan düzeyler", "type": "text", "default": "ana,alt",
     "help": "Virgülle: yayinevi, ana, alt, altalt. Rakip kategorisi bu düzeylerdeki düğümlere eşlenir"},
    {"key": "PAZAR_MAP_MIN_PROB", "group": "pazar", "label": "Eşleme önerisi: en düşük olasılık", "type": "text", "default": "0.70",
     "help": "Zeki AI bunun altında emin olduğunda öneri «emin değil» olarak gelir; karar her durumda insanda"},
    {"key": "PAZAR_MAP_MIN_MARGIN", "group": "pazar", "label": "Eşleme önerisi: en düşük fark", "type": "text", "default": "0.30",
     "help": "Seçilen kategori ile ikinci aday arasındaki olasılık farkı"},
    {"key": "PAZAR_BATCH_SECONDS", "group": "pazar", "label": "Eşleme önerisi süresi (saniye)", "type": "int", "default": "1800",
     "help": "Bir turda öneriye ayrılan süre; biten süre sonraki tura kalır (kuyruk kalıcı)"},
    {"key": "PAZAR_BLURB_CHARS", "group": "pazar", "label": "Tanıtım metninden alınan karakter", "type": "int", "default": "280",
     "help": "Rakip tanıtım metni ve TİMAŞ arka kapak metninin yalnız başı alınır (emsal benzerliği için); toplu kopyalanmaz"},
    {"key": "PAZAR_COMP_PAGE_TOL", "group": "pazar", "label": "Emsal: sayfa farkı payı", "type": "text", "default": "0.25",
     "help": "0.25 = ±%25. Sayfa sayısı girildiyse bu payın dışındaki aday elenir"},
    {"key": "PAZAR_COMP_PRICE_TOL", "group": "pazar", "label": "Emsal: fiyat farkı payı", "type": "text", "default": "0.30",
     "help": "0.30 = ±%30. Fiyat girildiyse bu payın dışındaki aday elenir"},
    {"key": "PAZAR_COMP_MODEL_CANDIDATES", "group": "pazar", "label": "Emsal: Zeki AI'ın okuduğu aday", "type": "int",
     "default": "20", "help": "Ortak sözcük puanı en yüksek bu kadar aday Zeki AI'ya sorulur; kalanlar puan sırasıyla listelenir "
                             "ve ekranda yazılır"},
    {"key": "PAZAR_COMP_EMBED_CANDIDATES", "group": "pazar", "label": "Emsal: anlam benzerliğiyle eklenen aday", "type": "int",
     "default": "30", "help": "Kitap benzerliği dizininden özeti anlamca en yakın bu kadar TİMAŞ kitabı (ortak sözcüğü olmasa da) "
                             "aday kümesine eklenir; kurallı süzgeç yine uygulanır. 0: kapalı"},
    {"key": "PAZAR_OWN_YEARS", "group": "pazar", "label": "İç göstergelerde yıl sayısı", "type": "int", "default": "3",
     "help": "Logo'dan okunan yıl sayısı (veri sonunun yılı dahil)"},
    {"key": "PAZAR_BRIEF_MAX_SOURCES", "group": "pazar", "label": "Özet taslağı: en çok kaynak", "type": "int", "default": "60",
     "help": "Taslağa verilen kaynak sayısı; dışarıda kalan sayısı özette yazılır"},
    {"key": "PAZAR_BRIEF_TWO_EYES", "group": "pazar", "label": "Özeti yazan onaylayamaz", "type": "bool", "default": "1", "help": ""},
    {"key": "PAZAR_FILE_MAX_MB", "group": "pazar", "label": "Rapor dosyası üst sınırı (MB)", "type": "int", "default": "50", "help": ""},
    {"key": "PAZAR_EXTRACT_PAGE_CHARS", "group": "pazar", "label": "Rakam çıkarımında parça boyu (karakter)", "type": "int",
     "default": "12000", "help": "Uzun sayfa bu boyda parçalara bölünür; hiçbir parça atlanmaz"},
    # M44 Lojistik ve kargo
    {"key": "SHIPPING_SHIPPED_STATUSES", "group": "shipping", "label": "Sevk edilmiş sayılan sipariş durumları", "type": "text",
     "default": "100000000,100000015", "help": "Virgülle CRM sipariş durum kodları (100000000 Sevk edildi, 100000015 Tamamlandı)"},
    {"key": "SHIPPING_UNTRACKED_STATUSES", "group": "shipping", "label": "Takip no'suz sevk: durumlar", "type": "text",
     "default": "100000000", "help": "Bu durumdaki siparişte takip numarası boşsa «takip numarasız sevk» listesine girer"},
    {"key": "SHIPPING_UNTRACKED_EXCLUDE_TYPES", "group": "shipping", "label": "Takip no'suz sevk: hariç sipariş tipleri",
     "type": "text", "default": "", "help": "Kargoyla gitmeyen sipariş tipleri (virgülle CRM kodu, ör. 16 İmza siparişi). Ölçülecek"},
    {"key": "SHIPPING_INTEGRATION_OK_VALUES", "group": "shipping", "label": "Entegrasyon sonucunda «başarılı» değerleri",
     "type": "text", "default": "başarılı,basarili,success,successful,ok,true,1,evet",
     "help": "Aras/UPS/MNG/Akademi sonuç alanında bu değerler hata sayılmaz (harf büyüklüğü fark etmez). Değer kümesi ölçülecek"},
    {"key": "SHIPPING_WINDOW_DAYS", "group": "shipping", "label": "Günlük hat penceresi (gün)", "type": "int", "default": "30",
     "help": "Entegrasyon hatası, takip numarasız sevk ve sipariş listesinin kaç gün geriye baktığı (ekranda yazılır)"},
    {"key": "SHIPPING_CARGO_DATE_FORMATS", "group": "shipping", "label": "Kargo kaydı tarih biçimleri", "type": "text",
     "default": "%d.%m.%Y,%d.%m.%Y %H:%M:%S,%d.%m.%Y %H:%M,%d/%m/%Y,%Y-%m-%d,%Y-%m-%d %H:%M:%S,%Y%m%d",
     "help": "Kargo bilgisi tablosunda tarihler metin; sırayla denenir, okunamayan kayıt ekranda sayılır. Ölçülecek"},
    {"key": "SHIPPING_RETURN_NO_VALUES", "group": "shipping", "label": "İade durumu: «iade değil» değerleri", "type": "text",
     "default": "hayır,hayir,yok,0,false,-,normal,iade değil", "help": "Kargo kaydının iade durumu alanında bu değerler iade sayılmaz. Ölçülecek"},
    {"key": "SHIPPING_COD_NO_VALUES", "group": "shipping", "label": "Tahsilatlı kargo: «hayır» değerleri", "type": "text",
     "default": "hayır,hayir,yok,0,false,-", "help": "Tahsilatlı kargo alanında bu değerler tahsilatsız sayılır. Ölçülecek"},
    {"key": "SHIPPING_LOGO_CARRIER_CODES", "group": "shipping", "label": "Kargo firması → Logo cari kodları", "type": "text",
     "default": "", "help": "Mutabakat ve kargo maliyeti için. Biçim: ARAS KARGO=320.01.001,320.01.002;MNG KARGO=320.01.003 "
                            "(firma adı kargo kaydındaki ya da CRM kargo firmasındaki gibi; kargo maliyeti ekranı irsaliyedeki "
                            "taşıyıcı kodunu da kabul eder). Mutabakat ekranındaki «Aday cariler» listesinden seçilir"},
    {"key": "SHIPPING_COST_SERVICE_CODES", "group": "shipping", "label": "Kargo gideri hizmet kodları", "type": "text",
     "default": "760.34.341,760.34.342,770.34.341",
     "help": "Kargo maliyeti ekranı için. Virgülle Logo hizmet kartı kodları; alınan hizmet faturalarında bu kodlu satırların "
             "tutarı (KDV hariç) kargo ve nakliye gideri sayılır. Varsayılan: posta ve kargo, satış nakliye, genel yönetim "
             "posta ve kargo"},
    {"key": "SHIPPING_LOGO_CARRIER_HINTS", "group": "shipping", "label": "Aday cari ipuçları", "type": "text",
     "default": "KARGO,KURYE,LOJİSTİK,EXPRESS", "help": "Logo'da ünvanında bu sözcükler geçen hizmet faturası carileri aday olarak listelenir"},
    {"key": "SHIPPING_STALE_DAYS", "group": "shipping", "label": "Kargo kaydı eskime uyarısı (gün)", "type": "int", "default": "3",
     "help": "Son kargo kaydı bundan eskiyse ekranlar «teslim bilgisi eksik olabilir» uyarır"},
    {"key": "SHIPPING_SNAPSHOT_MAX_MIN", "group": "shipping", "label": "Kargo anlık görüntüsü en çok kaç dakikalık", "type": "int",
     "default": "45", "help": "Zamanlayıcı ağır CRM okumalarını 15 dakikada bir okuyup saklar; ekran bundan tazeyse beklemeden "
                             "buradan okur, eskiyse CRM'e gider. 0 kapatır (her açılış CRM'i bekler)"},
    {"key": "SHIPPING_WAITING_DAYS", "group": "shipping", "label": "Teslim bekleyen eşiği (gün, varsayılan)", "type": "int",
     "default": "5", "help": "Depo müdürü ekranda değiştirebilir (kargo.karar yetkisiyle); bu değer ilk varsayılandır"},
    {"key": "SHIPPING_BOXED_DAYS", "group": "shipping", "label": "Kutulandı bekleyen eşiği (gün, varsayılan)", "type": "int",
     "default": "2", "help": "Kutulanıp bu kadar gün sevk edilmeyen sipariş sabah listesine girer"},
    {"key": "SHIPPING_DAILY_AT", "group": "shipping", "label": "Günlük özet saati", "type": "time", "default": "06:45",
     "help": "Hata sınıflaması ve iç özet e-postası bu saatten sonraki ilk turda, günde bir kez"},
    {"key": "SHIPPING_DAILY_TO", "group": "shipping", "label": "Günlük özet alıcıları", "type": "text", "default": "",
     "help": "Virgülle iç e-posta adresleri (sevkiyat sorumlusu). Boşsa e-posta gitmez"},
    {"key": "SHIPPING_WEEKLY_AT", "group": "shipping", "label": "Haftalık karne saati (pazartesi)", "type": "time", "default": "08:00",
     "help": "Haftalık firma karnesi pazartesi bu saatten sonra"},
    {"key": "SHIPPING_WEEKLY_TO", "group": "shipping", "label": "Haftalık karne alıcıları", "type": "text", "default": "",
     "help": "Virgülle iç e-posta adresleri (depo müdürü, yönetim). Karnede maliyet de vardır. Boşsa gitmez"},
    {"key": "SHIPPING_MONTHLY_TO", "group": "shipping", "label": "Aylık mutabakat alıcıları", "type": "text", "default": "",
     "help": "Ayın 3'ünde önceki ayın kargo mutabakatı özeti (finans). Boşsa gitmez"},
    {"key": "SHIPPING_CLASSIFY_MIN_PROB", "group": "shipping", "label": "Hata sınıflaması: en düşük olasılık", "type": "text",
     "default": "0.70", "help": "Zeki AI bu olasılığın altında kalırsa sınıf «Belirsiz» yazılır"},
    {"key": "SHIPPING_CLASSIFY_MIN_MARGIN", "group": "shipping", "label": "Hata sınıflaması: en düşük fark", "type": "text",
     "default": "0.30", "help": "İlk iki sınıfın olasılık farkı bundan küçükse «Belirsiz»"},
    {"key": "SHIPPING_CLASSIFY_BUDGET_SEC", "group": "shipping", "label": "Hata sınıflaması süre bütçesi (sn)", "type": "int",
     "default": "600", "help": "Günlük turda sınıflamaya ayrılan en uzun süre; kalan mesajlar ertesi tura kalır (kayıp yok)"},
    # M40 Trendyol (panel dosyası; API'ye bağlanılmaz) — varsayılanlar ölçülmemiş başlangıç değeridir
    {"key": "TRENDYOL_CARI_ADLARI", "group": "channels", "label": "Trendyol: cari unvanında aranan adlar", "type": "text",
     "default": "TRENDYOL,DSM GRUP", "help": "Virgülle. Logo'da unvanında bunlar geçen cariler Trendyol ekranında eşleme adayı olarak listelenir"},
    {"key": "TRENDYOL_MIN_DEPO_STOK", "group": "channels", "label": "Trendyol: «depoda var, kapalı» en az depo stoğu", "type": "text",
     "default": "1", "help": "Depo stoğu en az bu kadarken Trendyol'da kapalı ya da stoksuz olan ürün kaçan satış sayılır"},
    {"key": "TRENDYOL_MAX_INDIRIM", "group": "channels", "label": "Trendyol: liste fiyatına göre en çok indirim", "type": "text",
     "default": "0.35", "help": "Oran (0,35 = %35). Trendyol fiyatı liste fiyatının bundan fazla altındaysa «eşik altı» işaretlenir"},
    {"key": "TRENDYOL_LISTE_KDV", "group": "channels", "label": "Trendyol: KDV hariç liste fiyatını brütleme oranı", "type": "text",
     "default": "0", "help": "Logo liste fiyatı KDV hariçse kıyas için bu oranla brütlenir (0 = brütlenmez; ekranda yazar). Kitap KDV'si ölçülecek"},
    {"key": "TRENDYOL_VITRIN_MIN_STOK", "group": "channels", "label": "Trendyol vitrin: en az depo stoğu", "type": "text",
     "default": "50", "help": "Vitrin adayı olmak için depo stoğu en az bu kadar olmalı"},
    {"key": "TRENDYOL_VITRIN_GUN", "group": "channels", "label": "Trendyol vitrin: satış hızı penceresi (gün)", "type": "int",
     "default": "30", "help": "Satış hızı yüklenen sipariş dosyasındaki son siparişten geriye bu kadar gün"},
    {"key": "TRENDYOL_SORU_SAAT", "group": "channels", "label": "Trendyol: cevapsız soru eşiği (saat)", "type": "text",
     "default": "24", "help": "Bundan uzun süredir cevapsız soru «geciken» sayılır"},
    {"key": "TRENDYOL_SINIF_MIN_OLASILIK", "group": "channels", "label": "Trendyol iade sınıfı: en düşük olasılık", "type": "text",
     "default": "0.60", "help": "Zeki AI'ın iade nedeni seçimi bu olasılığın altındaysa sınıf boş kalır («emin değil»)"},
    {"key": "TRENDYOL_SINIF_MIN_FARK", "group": "channels", "label": "Trendyol iade sınıfı: en düşük fark", "type": "text",
     "default": "0.20", "help": "Seçilen sınıfla ikinci en olası sınıf arasındaki en düşük olasılık farkı"},
    # M41 Amazon ve yurtdışı (Logo + CRM; Amazon'a bağlanılmaz)
    {"key": "AMAZON_CARI_ADLARI", "group": "channels", "label": "Amazon: cari unvanında aranan adlar", "type": "text",
     "default": "AMAZON", "help": "Virgülle. Logo'da unvanında bunlar geçen cariler Amazon ekranında eşleme adayı olarak listelenir"},
    {"key": "AMAZON_YURTDISI_KODLARI", "group": "channels", "label": "Yurtdışı kanal kodları", "type": "text",
     "default": "YURTDIŞI,YURTDISI", "help": "Logo cari özel kod 2 değerleri (virgülle). Yazım ölçülecek: SELECT DISTINCT SPECODE2"},
    {"key": "AMAZON_YIL_SAYISI", "group": "channels", "label": "Yurtdışı: okunan yıl sayısı", "type": "int", "default": "2",
     "help": "Verinin son yılı ve öncesi"},
    {"key": "AMAZON_KONSINYE_YIL", "group": "channels", "label": "Konsinye: açık irsaliye yılı sayısı", "type": "int", "default": "1",
     "help": "Faturalanmamış irsaliye kaç yıl geriye aranır (1 = verinin son yılı). Yıl devrinde taşınıp taşınmadığı ölçülecek"},
    {"key": "AMAZON_CRM_KONSINYE_TIPI", "group": "channels", "label": "CRM Amazon Konsinye sipariş tipi", "type": "int", "default": "14",
     "help": "new_siparisBase.new_siparistipi değeri"},
    {"key": "AMAZON_ULKE_TABLOSU", "group": "channels", "label": "CRM ülke varlığı", "type": "text", "default": "new_ulke",
     "help": "Telif Satış sözleşmesindeki «Telif Satılan Ülke» aramasının varlık adı (Base eki ve Id kolonu eklenir). Ölçülecek"},
    # Trendyol/Amazon satış modeli (Aşama 0) ve mutabakat (Aşama 1) — başlangıç değerleri ölçülmemiştir
    {"key": "PAZARYERI_MODEL_YIL", "group": "channels", "label": "Satış modeli: okunan yıl sayısı", "type": "int", "default": "2",
     "help": "Satış modeli tespiti Logo'nun son verisinden geriye bu kadar yılı okur"},
    {"key": "PAZARYERI_KONSINYE_GUN", "group": "channels", "label": "Satış modeli: konsinye günü", "type": "int", "default": "30",
     "help": "Bu günden eski faturalanmamış sevk ya da sevkten bu kadar günden geç faturalanan sevk «konsinye izi» sayılır"},
    {"key": "PAZARYERI_GUCLU_AY", "group": "channels", "label": "Satış modeli: güçlü kanıt için ay sayısı", "type": "int",
     "default": "3", "help": "Modelin izi en az bu kadar farklı ayda görülürse kanıt «güçlü», azsa «zayıf» yazar"},
    {"key": "PAZARYERI_BASKIN_PAY", "group": "channels", "label": "Satış modeli: baskın satış payı", "type": "text",
     "default": "0.9", "help": "Kendi mağaza ile toptan/konsinye izi birlikteyse satış tutarının bu payından fazlası olan model "
     "geçerli sayılır, öteki «yan iz» yazar (0,5–1)"},
    {"key": "MUTABAKAT_TOLERANS_GUN", "group": "channels", "label": "Mutabakat: tarih toleransı (gün)", "type": "int",
     "default": "15", "help": "Logo faturası panel tarihinden en çok bu kadar gün önce ya da sonra aranır"},
    {"key": "MUTABAKAT_TUTAR_TOLERANS", "group": "channels", "label": "Mutabakat: tutar toleransı (₺)", "type": "text",
     "default": "1", "help": "Panel tutarı ile Logo fatura tutarı (KDV dahil) arasındaki fark bundan küçükse «eşleşti»"},
    # Yetki
    {"key": "TIMAS_ADMIN_USERS", "group": "access", "label": "Yöneticiler", "type": "users",
     "default": "zekiai,timasai,muratsancar",
     "help": "AD hesap adları, virgülle. Bu ekranı bunlar açar. zekiai her zaman yönetici AD grubunda; "
             "burada da tutulur ki AD bir an okunamasa bile yetkisi düşmesin"},
    {"key": "TIMAS_ADMIN_GROUP", "group": "access", "label": "Yönetici AD grubu", "type": "text",
     "default": "Administrators",
     "help": "Bu Active Directory grubunun üyeleri de yönetici sayılır (iç içe gruplar dahil). "
             "Boş bırakılırsa yalnız yukarıdaki liste geçerli olur"},
    {"key": "TIMAS_EDITOR_GROUP", "group": "access", "label": "Editör AD grubu", "type": "text",
     "default": "",
     "help": "Bu Active Directory grubunun üyeleri (iç içe gruplar dahil) menüde Editoryal'i Kampüs'ün hemen "
             "altında, «Çalışma alanım» olarak görür; öbür modüller menü sırasında gelir. Yetki vermez, yalnız "
             "menü düzenidir. Boş bırakılırsa herkes aynı menüyü görür"},
]
_BY_KEY = {s["key"]: s for s in SPEC}
#: Ayar gruplarının kategorileri: Yönetim › Ayarlar ekranında ikinci düzey gezinme. Her grup tam bir kategoride
#: (`GROUPS[*]["category"]`); kategorisi yazılmamış ya da bilinmeyen grup ekranda «Diğer» altında görünür, kaybolmaz.
CATEGORIES = [
    {"id": "baglanti", "label": "Bağlantılar ve giriş"},
    {"id": "zeki", "label": "Zeki AI"},
    {"id": "eposta", "label": "E-posta ve bildirimler"},
    {"id": "pazarlama", "label": "Pazarlama"},
    {"id": "seo", "label": "SEO ve GEO"},
    {"id": "satis", "label": "Satış, dijital ve platform"},
    {"id": "lojistik", "label": "Lojistik"},
    {"id": "finans", "label": "Finans ve risk"},
    {"id": "ik", "label": "İnsan kaynakları"},
    {"id": "sistem", "label": "Sistem"},
]
GROUPS = [
    {"id": "email", "category": "eposta", "label": "E-posta (SMTP)", "help": "Uyarı ve planlı rapor e-postaları bu hesapla gider."},
    {"id": "performance", "category": "sistem", "label": "Hız ve veri tazeliği",
     "help": "Yavaş ekranların verisi hazır tutulur ve 5 dakikada bir tazelenir; «Yenile» beklemeden kaynaktan okur."},
    {"id": "delivery", "category": "eposta", "label": "Bildirim ve raporlar", "help": "Gönderim davranışı."},
    {"id": "rooms", "category": "ik", "label": "Toplantı odaları", "help": "Rezervasyon takviminin saatleri."},
    {"id": "directory", "category": "baglanti", "label": "Active Directory (giriş)",
     "help": "Portal girişi bu dizinle doğrulanır. Kaydedilen değer giriş servisinin dosyasına yazılır ve hemen geçerli olur."},
    {"id": "database", "category": "baglanti", "label": "Logo veritabanı (SQL Server)",
     "help": "Soruların cevabı bu bağlantıdan okunur. Kaydedilen değer bağlantı dosyasına yazılır ve bağlantı yeniden kurulur."},
    {"id": "basvuru_form", "category": "baglanti", "label": "Yazar başvuru formları (Google)",
     "help": "Yazar başvuru formlarının yanıt tabloları servis hesabıyla yalnız okunur; her yanıt Başvurular'da yeni başvuru olur."},
    {"id": "crm", "category": "baglanti", "label": "CRM (Dynamics)", "help": "CRM prod sunucusu 192.168.0.28 (CRMDATBASE); kendi bağlantısıyla okunur."},
    {"id": "people", "category": "baglanti", "label": "Kişi rehberi",
     "help": "Rehber CRM'deki etkin kullanıcılardan gelir, Active Directory ile kesiştirilir: AD'de devre dışı olanlar ve "
             "süre içinde giriş yapmamış hesaplar girmez."},
    {"id": "llm", "category": "zeki", "label": "Yapay zekâ modeli (LLM)",
     "help": "Soruyu SQL'e çeviren model. Kaydedilen değer hemen geçerli olur, servis yeniden başlatılmaz."},
    {"id": "chat", "category": "zeki", "label": "Zeki AI sohbeti",
     "help": "Sohbet şirketin bütün modüllerinin sorularını cevaplar; kimlik ve şirket dışı sorulara kısa tanıtım "
             "verir. Burada hangi konuların verisinin sohbete bağlı olduğu seçilir."},
    {"id": "seo", "category": "seo", "label": "SEO & GEO (T-soft, Google)",
     "help": "Ürünler T-soft'tan yalnız okunur; T-soft'a hiçbir şey yazılmaz. Onaylanan öneriler kayıt altında "
             "durur (hedef CRM). Google verisi servis hesabıyla okunur."},
    {"id": "corporate", "category": "satis", "label": "Kurumsal satış ve B2B",
     "help": "Teklif onay eşikleri, hacim indirimi, tema listesi ve bayi paneli. B2B sitesine, CRM'e ve Logo'ya hiçbir şey yazılmaz."},
    {"id": "sets", "category": "pazarlama", "label": "Set, hediye ve promosyon",
     "help": "Set bileşeni, satış ve fiyat kaynağı, marj alt sınırı, birlikte alım ve kurumsal hediye kademeleri. CRM'e, Logo'ya "
             "ve T-soft'a hiçbir şey yazılmaz; onaylanan set için açılacak kart listesi verilir."},
    {"id": "mailbox", "category": "eposta", "label": "Kurumsal e-posta",
     "help": "timas@ genel kutusu yalnız okunur (Gmail: gmail.readonly + gmail.labels). Portal dışarıya ileti göndermez, kutudan "
             "silmez, taşımaz; yanıtı kişi kutunun kendi arayüzünden gönderir. İleti gövdesi portalda saklanmaz."},
    {"id": "relations", "category": "pazarlama", "label": "Kurumsal ilişkiler",
     "help": "Kanaat önderi ve kurum ilişkileri, hediye kitap programı, kamu projeleri. CRM'e hiçbir şey yazılmaz; kişilere ve "
             "kurumlara e-posta gitmez."},
    {"id": "eticaret", "category": "satis", "label": "E-ticaret ve pazar yerleri",
     "help": "Site, CRM ve Logo arasındaki fark kuralları, bildirim alıcıları ve pazar yeri kanalı. T-soft'a, CRM'e, Logo'ya ve "
             "pazar yerlerine hiçbir şey yazılmaz; düzeltmeyi kişi yapar."},
    {"id": "dijital", "category": "satis", "label": "Dijital yayın ve e-kitap",
     "help": "Fırsat eşikleri, rapor eşleme ve iç uyarı alıcıları. Platformlara, CRM'e, Logo'ya ve T-soft'a hiçbir şey gönderilmez."},
    {"id": "kampanya", "category": "satis", "label": "E-ticaret kampanyaları",
     "help": "Fiyat ve maliyet kaynağı, aday süzgeci eşikleri, sonuç penceresi ve bildirim alıcıları. Kampanya hiçbir platforma, "
             "T-soft'a ya da CRM'e gönderilmez; onaydan sonra ekip elle kurar."},
    {"id": "stock", "category": "lojistik", "label": "Depo ve stok",
     "help": "Bitecek, fazla ve hareketsiz stok kuralları, baskı süresi ve sabah bülteni. Logo'ya ve CRM'e hiçbir şey yazılmaz; "
             "onaylanan güvenlik stoku portalda durur."},
    {"id": "commerce", "category": "satis", "label": "E-ticaret müşterileri",
     "help": "Site siparişi ve üyesi T-soft'tan yalnız okunur; kişisel alan portalda yalnız tuzlu özet olarak durur. RFM "
             "eşikleri modülün kendi ekranındadır. T-soft'a, CRM'e ve Logo'ya hiçbir şey yazılmaz; portal ileti göndermez."},
    {"id": "studio", "category": "zeki", "label": "Kitap Tasarım Stüdyosu", "help": "Sayfa düzeni, karakter kartı ve okur araçları ayarları."},
    {"id": "creative", "category": "pazarlama", "label": "Pazarlama görsel ve metin",
     "help": "Kapak kaynağı, günlük özet alıcıları ve metin denetimi eşikleri. Dış kanala hiçbir şey gönderilmez."},
    {"id": "geo", "category": "seo", "label": "Yapay zekâ görünürlüğü (GEO)",
     "help": "İzlenen sorular bu motorlara resmî API'leriyle sorulur; Timaş'ın anılıp anılmadığı kaydedilir. Gemini ücretsiz "
             "katmanla çalışır; diğerleri ücretlidir ve anahtar girilmezse ölçülmez. Tüketici siteleri kazınmaz."},
    {"id": "marketing", "category": "pazarlama", "label": "Pazarlama planları",
     "help": "Yeni kitap ve aylık pazarlama planının bildirimleri, onay eşiği, öneri kuralları ve satış föyü. CRM'e ve dış "
             "kanallara hiçbir şey kendiliğinden gönderilmez; planlar ve föyler portalda onaylanır."},
    {"id": "kurul", "category": "finans", "label": "Kurul (danışma ve yönetim)",
     "help": "Kurul göstergeleri diğer modüllerin onaylı çıktılarından okunur. Portal kurul paketini kimseye göndermez; "
             "hatırlatmalar yalnız iç adreslere gider."},
    {"id": "itops", "category": "sistem", "label": "Sistem durumu",
     "help": "Halka denetimleri 5 dk'da bir koşar; kopma ve düzelme yalnız iç alıcılara e-postayla bildirilir. Denetimler "
             "yalnız okur, hiçbir servisi yeniden başlatmaz."},
    {"id": "voice", "category": "zeki", "label": "Zeki AI sesli not",
     "help": "Saha ve okul ziyaret notunu konuşarak yazdırma. Ses hiçbir yerde saklanmaz; metin not alanına düşer, kişi "
             "düzeltip kendisi kaydeder."},
    {"id": "security", "category": "sistem", "label": "Veri güvenliği",
     "help": "Güvenlik uyarı kuralları, hesap hijyeni ve saklama süreleri. Saklama süresi yalnız «uygula» açıkken siler; "
             "önizleme ve kanıt Veri güvenliği ekranındadır."},
    {"id": "support", "category": "sistem", "label": "Müşteri hizmetleri",
     "help": "Destek masası yalnız okunur; masaya, CRM'e ve Logo'ya hiçbir şey yazılmaz. Zeki AI taslağı müşteriye gitmez, "
             "temsilci düzeltip masadan kendisi gönderir."},
    {"id": "model_quality", "category": "zeki", "label": "Zeki AI kalitesi",
     "help": "Kapı koşularının bildirimleri, karne penceresi ve sürüm kaydının ek dosyaları. Bildirimler yalnız iç ekibe gider."},
    {"id": "zeki_ortak", "category": "zeki", "label": "Zeki AI ortak araçlar",
     "help": "Belge okuma (taranmış sayfa dahil) ve kitap benzerliği araması. Belgeler yalnız kendi GPU sunucumuzda okunur, "
             "okunan metin modele gitmeden önce maskelenir; benzerlik yalnız sıralama içindir, rakamlar SQL'den gelir."},
    {"id": "contract_compare", "category": "finans", "label": "Sözleşme karşılaştırma",
     "help": "Sözleşmenin maddeleri geçmiş sözleşmelerle kıyaslanır: kıyas grubu, sapma eşiği ve serbest metin eşikleri. "
             "Model kullanılmaz; CRM'e yazılmaz."},
    {"id": "royalty", "category": "finans", "label": "Telif dönemi",
     "help": "Dönem koşusunun kapsamı, stopaj varsayılanı ve hatırlatmalar. CRM'e, Logo'ya ve bankaya hiçbir şey yazılmaz; "
             "beyannameyi yazara insan gönderir."},
    {"id": "readers", "category": "satis", "label": "Okur veri tabanı",
     "help": "Tekil okur, izin ve segment kuralları. CRM'e yazılmaz, portal ileti göndermez; liste dışa aktarımı izin "
             "denetimli ve kayıt altındadır."},
    {"id": "ads", "category": "pazarlama", "label": "Dijital pazarlama ve reklam",
     "help": "Reklam harcaması platformun dışa aktarım dosyasıyla gelir; platformlara hiçbir şey gönderilmez (bütçe, teklif, "
             "durdurma yok). Eşiği boş bırakılan öneri kuralı çalışmaz."},
    {"id": "social", "category": "pazarlama", "label": "Sosyal medya",
     "help": "Takvim uyarıları, fırsat kuralları ve platform sınırları. Portal hiçbir sosyal medya hesabına paylaşım yapmaz; "
             "onaylı gönderi yayına hazır paket olarak iner."},
    {"id": "influencer", "category": "pazarlama", "label": "İşbirlikleri",
     "help": "İçerik üreticisi işbirliklerinin hatırlatmaları, onay ve ödeme bildirimleri, aday puanı. İçerik üreticisine "
             "portaldan e-posta gitmez; hesap sayıları kazınmaz."},
    {"id": "catalog", "category": "pazarlama", "label": "Katalog ve bülten",
     "help": "Katalog fiyat ve stok kaynağı, uyarı eşikleri, öneri ağırlıkları ve bülten segment kuralı. Portal toplu e-posta "
             "göndermez, kişi listesi dışarı vermez; CRM'e ve T-soft'a hiçbir şey yazılmaz."},
    {"id": "hr", "category": "ik", "label": "İnsan kaynakları",
     "help": "İşe alım bildirimleri ve aday verisine yönetici erişimi. Saklama süreleri ve aydınlatma metni İK ekranındadır "
             "(Çalışan ve KVKK kayıtları). CRM'e yazılmaz; adaya portal e-posta göndermez."},
    {"id": "channels", "category": "satis", "label": "Platform ve kanallar",
     "help": "Kanal karnesi, eşleme ve uyarı ayarları. Pazar yerlerine, T-soft'a, CRM'e ve Logo'ya hiçbir şey yazılmaz; "
             "öneriler portalda onaylanır, gönderimi insan yapar."},
    {"id": "pazar", "category": "satis", "label": "Pazar araştırması ve rekabet",
     "help": "Rakip verisi CRM'den okunur, pazar rakamları yalnız yüklenen ve onaylanan rapordan gelir; dış kaynak taraması "
             "yok. CRM'e ve Logo'ya hiçbir şey yazılmaz."},
    {"id": "shipping", "category": "lojistik", "label": "Lojistik ve kargo",
     "help": "Kargo günlük hattı, firma karnesi ve mutabakat. CRM, Logo ve kargo firmaları yalnız okunur; kargo firmasına, "
             "CRM'e ve müşteriye hiçbir şey gönderilmez. Alıcılar yalnız iç e-posta adresleridir."},
    {"id": "access", "category": "baglanti", "label": "Yetki",
     "help": "Yönetim ekranına kimlerin gireceği: aşağıdaki liste ya da seçilen AD grubunun üyeleri. "
             "Editör grubu yalnız menünün düzenini belirler."},
]
#: Dosyada tutulan ayarlar: anahtar → (dosya, dosyadaki alan adı). Veritabanı yerine dosya, çünkü
#: bu değerleri okuyan başka bir süreç var (giriş servisi, bağlantıyı kuran sürücü).
_FILE_KEYS = {s["key"]: (s.get("store", "ad"), s["file"]) for s in SPEC if s.get("file")}
#: Giriş servisiyle aynı dosya (scripts/server/portal-login/server.py → AD_CONFIG_FILE).
AD_FILE = os.environ.get("AD_CONFIG_FILE", "/etc/nanobase/timas-ad.json")
#: Köprünün veritabanı bağlantı dosyası (SemanticSettings.connection_file ile aynı).
DB_FILE = os.environ.get("SEMANTIC_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/logo-mssql-connection.json")


def _store_path(store: str) -> str:
    return AD_FILE if store == "ad" else DB_FILE


def store_keys(store: str) -> list[str]:
    """O dosyada tutulan ayar anahtarları."""
    return [k for k, (s, _) in _FILE_KEYS.items() if s == store]


#: Ayarı kaydedilince neyin yeniden kurulacağı; köprü (app.py) bu listelere bakar.
LLM_KEYS = ("OPENAI_API_BASE", "LLM_MODEL_NAME", "OPENAI_API_KEY", "LLM_TIMEOUT_SEC")
#: Modelin ürün içindeki adı. Hangi sağlayıcının hangi modeli olduğu bir kurulum ayrıntısıdır ve
#: yerine başkası konabilir; ekranda ürünün kendi adı yazar (sohbetteki "ZEKİ AI" kimliğiyle aynı
#: kural). Teknik ad, düzeltilecek yerde — «Model» ayarının kendisinde — duruyor.
LLM_DISPLAY = os.environ.get("LLM_DISPLAY_NAME", "ZEKİ AI")

KIND_LABEL = {"audit_verify": "Denetim kaydı doğrulaması", "audit_export": "Denetim kaydı aktarımı", "report": "Planlı rapor", "alert": "Uyarı", "board": "Pano kartı", "setting": "Ayar",
              "term": "Sözlük terimi", "annotation": "Kolon açıklaması", "session": "Oturum",
              "room": "Toplantı odası", "booking": "Oda rezervasyonu", "access": "Yetki",
              "marketing_plan": "Pazarlama planı", "marketing_material": "Pazarlama materyali",
              "marketing_foy": "Satış föyü",
              "itops_incident": "Sistem olayı", "itops_check": "Bağlantı denemesi", "itops_release": "Sürüm kaydı",
              "security_alert": "Güvenlik uyarısı",
              "support_context": "Müşteri bağlamı", "support_dealer": "Bayi görünümü", "support_draft": "Cevap taslağı",
              "support_class": "Talep sınıfı", "support_class_def": "Destek sınıfı", "support_faq": "SSS maddesi",
              "ads_account": "Reklam hesabı", "ads_import": "Reklam dosyası", "ads_campaign": "Reklam kampanyası",
              "ads_budget": "Reklam bütçesi", "ads_suggestion": "Reklam önerisi", "ads_brief": "Reklam brief'i",
              "ads_report": "Reklam raporu", "ads_refresh": "Reklam satış verisi", "ads_run_due": "Reklam günlük işi",
              "social_post": "Sosyal medya gönderisi", "social_account": "Sosyal medya hesabı",
              "social_import": "Sosyal medya içe aktarma", "social_metric": "Sosyal medya içgörüsü",
              "social_report": "Sosyal medya raporu",
              "catalog": "Katalog", "catalog_item": "Katalog kitabı", "newsletter": "E-bülten",
              "dijital_listing": "Dijital platform durumu", "dijital_rights": "Dijital hak kararı",
              "dijital_price": "Dijital fiyat kararı", "dijital_platform": "Dijital platform",
              "dijital_import": "Dijital satış raporu"}

_ready: set[int] = set()
_lock = threading.Lock()
_engine: Optional[sa.engine.Engine] = None
_cache: dict[str, Any] = {"at": 0.0, "values": {}}
_TTL = 5.0


class AdminError(ValueError):
    """Kullanıcıya olduğu gibi gösterilecek düz Türkçe hata."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v: Optional[datetime]) -> Optional[str]:
    if v is None:
        return None
    return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()


def ensure(engine: sa.engine.Engine) -> None:
    """Tabloları kurar ve ayar okuyucusunu bu veritabanına bağlar."""
    global _engine
    with _lock:
        if id(engine) not in _ready:
            from semantic_layer.store import schema_stamp
            schema_stamp.create_all(_md, engine)
            from semantic_bridge import audit_trail
            try:
                audit_trail.ensure(engine)
            except Exception as e:  # noqa: BLE001 — denetim kurulumu yönetim/ayar okumasını durdurmaz; sonra yeniden denenir
                log.warning("admin: denetim kaydı kurulumu bu sefer olmadı: %s", e)
            _ready.add(id(engine))
        _engine = engine


# ------------------------------------------------------------------ ayarlar


def settings_stmt() -> Any:
    """Ayar kaydı okuması (sorgu bilgisi aynı ifadeyi gösterir: `kaynak_ayar.py`)."""
    return sa.select(SETTINGS.c.key, SETTINGS.c.value)


def _stored() -> dict[str, str]:
    if _engine is None:
        return {}
    if time.monotonic() - _cache["at"] < _TTL:
        return _cache["values"]
    try:
        with _engine.connect() as c:
            rows = c.execute(settings_stmt()).all()
        _cache.update(at=time.monotonic(), values={k: v for k, v in rows})
    except Exception as e:  # noqa: BLE001
        log.warning("admin: ayarlar okunamadı, ortam değerleri kullanılıyor: %s", e)
        return {}
    return _cache["values"]


def _file(store: str) -> dict[str, Any]:
    try:
        with open(_store_path(store), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _file_write(store: str, values: dict[str, Any]) -> None:
    """Dosyayı yanına yazıp adını değiştirir: okuyan yarım dosya görmesin.

    Sahibi ve izni korunmak zorunda: giriş ayarı root'a ait ve giriş servisinin grubuna okunur.
    Yeni dosyayı aynı sahiple yazamıyorsak (chown yalnız root'un işi) ad değiştirmek, dosyayı
    okuyan servisin erişimini elinden alır — giriş çalışmaz olur. O durumda dosyanın kendisine,
    aynı düğüme yazılır: sahip, grup ve izin olduğu gibi kalır.
    """
    path = _store_path(store)
    body = json.dumps(values, ensure_ascii=False, indent=2) + "\n"
    tmp = f"{path}.tmp"
    st = None
    try:
        st = os.stat(path)
    except OSError:
        pass
    if st is not None and (st.st_uid != os.geteuid() or st.st_gid not in os.getgroups()):
        with open(path, "r+", encoding="utf-8") as f:
            f.write(body)
            f.truncate()
            f.flush()
            os.fsync(f.fileno())
        return
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(body)
    if st is not None:
        os.chmod(tmp, st.st_mode & 0o777)
        try:
            os.chown(tmp, st.st_uid, st.st_gid)
        except OSError:
            pass
    else:
        os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _ad_file() -> dict[str, Any]:
    return _file("ad")


def conf(key: str, default: str = "") -> str:
    """Ayarın geçerli değeri: ekran > ortam > varsayılan. Dosyada tutulanlar yalnız kendi dosyasından."""
    if key in _FILE_KEYS:
        store, field = _FILE_KEYS[key]
        v = _file(store).get(field)
        if v is None or v == "":
            spec = _BY_KEY[key]
            return spec["default"] if default == "" else default
        return str(v)
    stored = _stored()
    if key in stored:
        return stored[key]
    if key in os.environ:
        return os.environ[key]
    spec = _BY_KEY.get(key)
    return spec["default"] if spec and default == "" else default


def admins() -> list[str]:
    return [u.strip().lower() for u in conf("TIMAS_ADMIN_USERS").split(",") if u.strip()]


#: DB'deki grup anlık görüntüsünü her is_admin çağrısında sorgulamamak için kısa bellek önbelleği.
#: Bu AD'yi DEĞİL, yalnız DB kaydını önbelleğe alır; canlı AD okuması 15 dk'lık timer'da yapılır.
_grp_mem: dict[str, Any] = {"at": 0.0, "group": "", "members": frozenset()}
_GRP_MEM_TTL = 30.0


def admin_group_members() -> frozenset[str]:
    """Yönetici AD grubunun (iç içe dahil) üyeleri — DB'deki en son anlık görüntüden okunur.
    Canlı AD burada OKUNMAZ; görüntüyü `refresh_admin_group` (15 dk'lık timer) tazeler. Grup adı
    boşsa ya da görüntü yoksa boş küme döner; o zaman yalnız `TIMAS_ADMIN_USERS` listesi geçerlidir.
    """
    return _snapshot_members(_grp_mem, conf("TIMAS_ADMIN_GROUP").strip().lower())


#: Editör AD grubunun bellek önbelleği (yönetici grubununkiyle aynı düzen, ayrı kayıt).
_ed_mem: dict[str, Any] = {"at": 0.0, "group": "", "members": frozenset()}


def editor_group_members() -> frozenset[str]:
    """Editör AD grubunun (`TIMAS_EDITOR_GROUP`) üyeleri — yönetici grubu gibi DB anlık görüntüsünden
    okunur, canlı AD istek yolunda okunmaz. Grup tanımlı değilse boş küme."""
    return _snapshot_members(_ed_mem, conf("TIMAS_EDITOR_GROUP").strip().lower())


def _snapshot_members(mem: dict[str, Any], group: str) -> frozenset[str]:
    now = time.time()
    if mem["group"] == group and now - mem["at"] < _GRP_MEM_TTL:
        return mem["members"]  # type: ignore[no-any-return]
    members = _load_group_snapshot(group)
    mem.update(at=now, group=group, members=members)
    return members


def _load_group_snapshot(group_lower: str) -> frozenset[str]:
    if not group_lower or _engine is None:
        return frozenset()
    try:
        with _engine.connect() as c:
            row = c.execute(sa.select(GROUP_CACHE.c.members)
                            .where(sa.func.lower(GROUP_CACHE.c.group_name) == group_lower)).first()
        if not row:
            return frozenset()
        data = json.loads(row[0]) or []
        return frozenset(str(x).strip().lower() for x in data if str(x).strip())
    except Exception as e:  # noqa: BLE001
        log.warning("admin: grup anlık görüntüsü okunamadı: %s", e)
        return frozenset()


def group_snapshot() -> dict[str, Any]:
    """Ekranda göstermek için: kayıtlı üyeler, en son tazeleme zamanı ve varsa hata."""
    group = conf("TIMAS_ADMIN_GROUP").strip()
    out: dict[str, Any] = {"group": group, "members": [], "updatedAt": None, "error": None, "count": 0}
    if not group or _engine is None:
        return out
    try:
        with _engine.connect() as c:
            row = c.execute(sa.select(GROUP_CACHE.c.members, GROUP_CACHE.c.updated_at, GROUP_CACHE.c.error)
                            .where(sa.func.lower(GROUP_CACHE.c.group_name) == group.lower())).first()
        if row:
            members = sorted(str(x).strip().lower() for x in (json.loads(row[0]) or []) if str(x).strip())
            out.update(members=members, count=len(members), updatedAt=_iso(row[1]), error=row[2])
    except Exception as e:  # noqa: BLE001
        out["error"] = f"görüntü okunamadı: {e}"[:400]
    return out


def refresh_admin_group(engine: Optional[sa.engine.Engine] = None) -> dict[str, Any]:
    """Yönetici AD grubunu (ve tanımlıysa editör AD grubunu) canlı okuyup DB'ye yazar. 15 dk'lık timer bunu
    çağırır (istek yolunda değil). Dönen cevap yönetici grubununkidir; editör grubunun sonucu `editor`
    alanındadır. Tazeleme başarısız olursa eldeki üye görüntüsü SİLİNMEZ; yalnız hata kaydedilir."""
    out = _refresh_group(engine, "TIMAS_ADMIN_GROUP")
    if conf("TIMAS_EDITOR_GROUP").strip():
        ed = _refresh_group(engine, "TIMAS_EDITOR_GROUP")
        ed.pop("members", None)
        out["editor"] = ed
    return out


def _refresh_group(engine: Optional[sa.engine.Engine], key: str) -> dict[str, Any]:
    eng = engine or _engine
    group = conf(key).strip()
    if eng is None:
        return {"ok": False, "error": "veritabanı bağlı değil"}
    ensure(eng)
    if not group:
        return {"ok": True, "group": "", "count": 0, "note": "grup tanımlı değil"}
    cfg = {k: conf(k) for k in store_keys("ad")}
    missing = [k for k in ("AD_HOST", "AD_NETBIOS", "AD_BASE_DN", "AD_BIND_USER", "AD_BIND_PASSWORD") if not cfg.get(k)]
    if missing:
        return {"ok": False, "group": group, "error": "AD ayarı eksik: " + ", ".join(missing)}
    now = _now()
    try:
        members = sorted(_read_group_members(cfg, group))
    except Exception as e:  # noqa: BLE001
        log.warning("admin: %s tazelenemedi, eski görüntü korunuyor: %s", key, e)
        try:
            with eng.begin() as c:
                c.execute(GROUP_CACHE.update().where(GROUP_CACHE.c.group_name == group)
                          .values(updated_at=now, error=f"{type(e).__name__}: {e}"[:400]))
        except Exception:  # noqa: BLE001
            pass
        return {"ok": False, "group": group, "error": f"{type(e).__name__}: {e}"[:400]}
    body = json.dumps(members, ensure_ascii=False)
    with eng.begin() as c:
        c.execute(GROUP_CACHE.delete().where(GROUP_CACHE.c.group_name == group))
        c.execute(GROUP_CACHE.insert().values(group_name=group, members=body, updated_at=now, error=None))
    _grp_mem.update(at=0.0)   # bellek önbelleklerini geçersiz kıl: sonraki okuma yeni görüntüyü alsın
    _ed_mem.update(at=0.0)
    log.info("admin: %s tazelendi (%s): %d üye", key, group, len(members))
    return {"ok": True, "group": group, "count": len(members), "at": _iso(now), "members": members}


def _read_group_members(cfg: dict[str, str], group: str) -> frozenset[str]:
    from ldap3 import NONE, NTLM, SUBTREE, Connection, Server  # type: ignore[import-not-found]

    _ensure_md4()
    server = Server(cfg["AD_HOST"], port=int(cfg.get("AD_PORT") or 389), get_info=NONE, connect_timeout=5)
    conn = Connection(server, user=f'{cfg["AD_NETBIOS"]}\\{cfg["AD_BIND_USER"]}', password=cfg["AD_BIND_PASSWORD"],
                      authentication=NTLM, receive_timeout=15)
    if not conn.bind():
        raise RuntimeError(f"servis hesabı reddedildi: {conn.result.get('description')}")
    try:
        if group.lower().startswith(("cn=", "ou=")) and "dc=" in group.lower():
            group_dn = group                       # tam DN girilmişse doğrudan kullan
        else:
            esc = _ldap_escape(group)
            conn.search(cfg["AD_BASE_DN"], f"(&(objectClass=group)(|(sAMAccountName={esc})(cn={esc})))",
                        SUBTREE, attributes=["distinguishedName"], size_limit=2)
            if not conn.entries:
                raise RuntimeError(f"«{group}» grubu bulunamadı")
            group_dn = conn.entries[0].entry_dn
        # 1.2.840.113556.1.4.1941 = LDAP_MATCHING_RULE_IN_CHAIN: iç içe grupların üyeleri de gelir.
        # userAccountControl bit 2 (ACCOUNTDISABLE) olanlar dışlanır.
        flt = (f"(&(objectCategory=person)(objectClass=user)"
               f"(memberOf:1.2.840.113556.1.4.1941:={_ldap_escape(group_dn)})"
               f"(!(userAccountControl:1.2.840.113556.1.4.803:=2)))")
        found = conn.extend.standard.paged_search(cfg["AD_BASE_DN"], flt, SUBTREE,
                                                  attributes=["sAMAccountName"], paged_size=500, generator=True)
        out = set()
        for e in found:
            if e.get("type") != "searchResEntry":
                continue
            # Ham öznitelik değeri liste gelir (['ahmetbozkurt']); ilk elemanı al.
            v = (e.get("attributes") or {}).get("sAMAccountName")
            if isinstance(v, (list, tuple)):
                v = v[0] if v else ""
            out.add(str(v or "").strip().lower())
        return frozenset(a for a in out if a)
    finally:
        conn.unbind()


def _ldap_escape(v: str) -> str:
    """RFC 4515 filtre kaçışı: girilen grup adı filtreyi bozmasın."""
    return v.replace("\\", "\\5c").replace("*", "\\2a").replace("(", "\\28").replace(")", "\\29").replace("\x00", "\\00")


def is_editor(user: Optional[str]) -> bool:
    """Editör AD grubunun üyesi mi (menü düzeni için; yetki vermez). Grup tanımlı değilse herkes için False."""
    if not user or not conf("TIMAS_EDITOR_GROUP").strip():
        return False
    return user.strip().lower() in editor_group_members()


def is_admin(user: Optional[str]) -> bool:
    if not user:
        return False
    u = user.strip().lower()
    if u in admins():
        return True
    return u in admin_group_members()


def _validate(spec: dict[str, Any], raw: Any) -> str:
    t = spec["type"]
    v = "" if raw is None else str(raw).strip()
    if spec["key"] == "SEO_SITE_URL" and v and ("/rest" in v.lower() or not v.lower().startswith(("http://", "https://"))):
        # 2026-09-25: T-soft REST adresi bu kutuya girilmiş, şema taraması ve bağlantılar API adresine gitmişti.
        raise AdminError("«Mağaza adresi» sitenin adresi olmalı (örn. https://timas.com.tr); T-soft REST adresi üstteki kutuya girilir.")
    if spec["key"] == "MARKETING_FOY_LOGO_PRICE" and v and v not in ("satis", "liste", "yok"):
        raise AdminError("«Föy fiyatı …» satis, liste ya da yok olmalı.")
    if spec["key"] == "MARKETING_CONFLICT_KEYS" and v and any(x.strip() not in ("kitaplik", "hedef-kitle") for x in v.split(",")):
        raise AdminError("«Çakışma kuralı» kitaplik ve/veya hedef-kitle olmalı.")
    if spec["key"] in ("MARKETING_MONTH_DRAFT_DAY", "MARKETING_FOY_REMIND_DAY") and v and not (v.isdigit() and 1 <= int(v) <= 28):
        raise AdminError(f"«{spec['label']}» 1 ile 28 arasında bir gün olmalı.")
    if spec["key"] in ("MARKETING_MONTHLY_BUDGET", "MARKETING_FOY_PRICE_TOLERANCE") and v:
        raw = v.replace(".", "").replace(",", ".") if "," in v else v
        try:
            n = float(raw)
        except ValueError:
            raise AdminError(f"«{spec['label']}» bir sayı olmalı.") from None
        if n < 0:
            raise AdminError(f"«{spec['label']}» eksi olamaz.")
        return raw
    if spec["key"] in ("MARKETING_UPPER_APPROVAL_THRESHOLD", "MARKETING_BUDGET_RATE") and v:
        try:
            n = float(v.replace(",", "."))
        except ValueError:
            raise AdminError(f"«{spec['label']}» bir sayı olmalı.") from None
        if n < 0 or (spec["key"] == "MARKETING_BUDGET_RATE" and n > 100):
            raise AdminError(f"«{spec['label']}» eksi olamaz" + (" ve 100'ü geçemez." if spec["key"] == "MARKETING_BUDGET_RATE" else "."))
        return v.replace(",", ".")
    if spec["key"] == "MARKETING_TASK_TEMPLATE" and v:
        try:
            rows = json.loads(v)
            ok = isinstance(rows, list) and all(isinstance(r, list) and len(r) >= 4 and isinstance(r[0], int) and str(r[1]).strip()
                                                for r in rows)
        except ValueError:
            ok = False
        if not ok:
            raise AdminError("«Takvim şablonu» [[gün, \"iş\", \"kanal\", \"materyal\"], …] biçiminde JSON olmalı.")
        return v
    if spec["key"] == "SOCIAL_PLATFORM_LIMITS" and v:
        try:
            lim = json.loads(v)
            ok = isinstance(lim, dict) and all(isinstance(n, int) and n > 0 for n in lim.values())
        except ValueError:
            ok = False
        if not ok:
            raise AdminError("«Platform sınırları» {\"x\": 280, \"instagram:etiket\": 30} biçiminde JSON olmalı.")
    if spec["key"] in ("CATALOG_PRICE_SOURCE", "CATALOG_STOCK_SOURCE") and v:
        allowed = (("crm", "crm-perakende", "crm-uzeri", "logo", "tsoft") if spec["key"] == "CATALOG_PRICE_SOURCE" else ("crm", "logo"))
        if v.lower() not in allowed:
            raise AdminError(f"«{spec['label']}» şunlardan biri olmalı: {', '.join(allowed)}.")
        return v.lower()
    if spec["key"] in ("CATALOG_SCORE_WEIGHTS", "NEWSLETTER_INTEREST_KEYWORDS") and v:
        try:
            obj = json.loads(v)
        except ValueError:
            obj = None
        if not isinstance(obj, dict):
            raise AdminError(f"«{spec['label']}» JSON nesnesi olmalı.")
        return v
    if t == "bool":
        return "1" if v in ("1", "true", "True", "on", "evet") else "0"
    if t == "int":
        try:
            n = int(v)
        except ValueError:
            raise AdminError(f"«{spec['label']}» bir tam sayı olmalı.") from None
        if n < 0:
            raise AdminError(f"«{spec['label']}» eksi olamaz.")
        return str(n)
    if t == "time":
        import re as _re
        m = _re.match(r"^([01]\d|2[0-4]):([0-5]\d)$", v)
        if not m or (m.group(1) == "24" and m.group(2) != "00"):
            raise AdminError(f"«{spec['label']}» SS:DD biçiminde olmalı, örn. 08:30.")
        return v
    if t == "email" and v and ("@" not in v or " " in v):
        raise AdminError(f"«{spec['label']}» geçerli bir e-posta adresi değil.")
    if t == "users":
        users = [u.strip().lower() for u in v.split(",") if u.strip()]
        if not users:
            raise AdminError("En az bir yönetici kalmalı.")
        return ",".join(dict.fromkeys(users))
    if t == "secret":
        return str(raw or "")
    return v


def settings_view() -> dict[str, Any]:
    stored = _stored()
    rows = {}
    if _engine is not None:
        with _engine.connect() as c:
            rows = {r["key"]: r for r in c.execute(sa.select(SETTINGS)).mappings().all()}
    items = []
    for s in SPEC:
        k = s["key"]
        source = "file" if k in _FILE_KEYS else "screen" if k in stored else "env" if k in os.environ else "default"
        value = conf(k)
        item = {k2: s[k2] for k2 in ("key", "group", "label", "type", "help")}
        item.update(source=source, updatedBy=rows[k]["updated_by"] if k in rows else None,
                    updatedAt=_iso(rows[k]["updated_at"]) if k in rows else None)
        if s["type"] == "secret":
            item.update(value=None, hasValue=bool(value))
        else:
            item.update(value=value, hasValue=bool(value))
        items.append(item)
    return {"groups": GROUPS, "categories": CATEGORIES, "items": items}


def save_settings(engine: sa.engine.Engine, actor: str, values: dict[str, Any]) -> dict[str, Any]:
    changed: list[dict[str, Any]] = []
    now = _now()
    clean: dict[str, str] = {}
    for k, raw in values.items():
        spec = _BY_KEY.get(k)
        if not spec:
            raise AdminError(f"Bilinmeyen ayar: {k}")
        # Boş gönderilen parola "değiştirme" demektir; silmek için ayrı uç var.
        if spec["type"] == "secret" and (raw is None or str(raw) == ""):
            continue
        clean[k] = _validate(spec, raw)
    if ("TIMAS_ADMIN_USERS" in clean and actor.lower() not in clean["TIMAS_ADMIN_USERS"].split(",")
            and actor.lower() not in admin_group_members()):
        raise AdminError("Kendinizi yöneticilerden çıkaramazsınız; önce başka bir yönetici bunu yapmalı.")
    for store in ("ad", "db"):
        file_part = {k: v for k, v in clean.items() if _FILE_KEYS.get(k, ("", ""))[0] == store}
        if not file_part:
            continue
        current = _file(store)
        merged = dict(current)
        touched = False
        for k, v in file_part.items():
            field = _FILE_KEYS[k][1]
            old = "" if current.get(field) is None else str(current.get(field))
            if old == v:
                continue
            # Dosyadaki yazımı koru: port bir kurulumda sayı, ötekinde metin yazılmış.
            merged[field] = v if isinstance(current.get(field), str) or _BY_KEY[k]["type"] != "int" else int(v)
            touched = True
            secret = _BY_KEY[k]["type"] == "secret"
            changed.append({"key": k, "label": _BY_KEY[k]["label"],
                            "from": None if secret else old, "to": None if secret else v})
        if touched:
            if store == "db" and not merged.get("datasource"):
                merged["datasource"] = "mssql"
            try:
                _file_write(store, merged)
            except OSError as e:
                raise AdminError(f"Ayar dosyası yazılamadı ({_store_path(store)}): {e}") from e
    with engine.begin() as c:
        for k, v in clean.items():
            if k in _FILE_KEYS:
                continue
            old = conf(k)
            if old == v and k in _stored():
                continue
            c.execute(SETTINGS.delete().where(SETTINGS.c.key == k))
            c.execute(SETTINGS.insert().values(key=k, value=v, updated_by=actor, updated_at=now))
            secret = _BY_KEY[k]["type"] == "secret"
            changed.append({"key": k, "label": _BY_KEY[k]["label"],
                            "from": None if secret else old, "to": None if secret else v})
    _cache["at"] = 0.0
    for ch in changed:
        audit(engine, actor, "update", "setting", ch["key"], ch["label"],
              {"from": ch["from"], "to": ch["to"]} if ch["from"] is not None or ch["to"] is not None else {"secret": True})
    return {"changed": [c["key"] for c in changed], **settings_view()}


def reset_setting(engine: sa.engine.Engine, actor: str, key: str) -> dict[str, Any]:
    spec = _BY_KEY.get(key)
    if not spec:
        raise AdminError(f"Bilinmeyen ayar: {key}")
    if key == "TIMAS_ADMIN_USERS":
        raise AdminError("Yönetici listesi sıfırlanamaz; düzenleyerek değiştirin.")
    if key in _FILE_KEYS:
        raise AdminError("Bu ayar kendi dosyasında tutulur; sunucu değeri yoktur, düzenleyerek değiştirin.")
    with engine.begin() as c:
        n = c.execute(SETTINGS.delete().where(SETTINGS.c.key == key)).rowcount
    _cache["at"] = 0.0
    if n:
        audit(engine, actor, "delete", "setting", key, spec["label"], {"to": "ortam dosyası / varsayılan"})
    return settings_view()


def smtp_test(to: str) -> tuple[bool, str]:
    """Geçerli ayarla bir deneme e-postası gönderir; hata metnini olduğu gibi döndürür."""
    from semantic_bridge import alerts as alerts_mod

    cfg = alerts_mod.smtp_settings()
    if not cfg:
        return False, "SMTP sunucusu ya da gönderen adresi girilmemiş."
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = "ZEKİ deneme e-postası", cfg["sender"], to
    msg.set_content("Bu e-posta ZEKİ yönetim ekranından gönderilen denemedir. Uyarı ve planlı rapor e-postaları bu ayarla gidecek.")
    try:
        ctx = ssl.create_default_context()
        server = (smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=20, context=ctx) if cfg["ssl"]
                  else smtplib.SMTP(cfg["host"], cfg["port"], timeout=20))
        with server as s:
            if not cfg["ssl"] and cfg["starttls"]:
                s.starttls(context=ctx)
            if cfg["user"]:
                s.login(cfg["user"], cfg["password"])
            s.send_message(msg)
        return True, f"{to} adresine gönderildi."
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"[:400]


def _ensure_md4() -> None:
    """NTLM MD4 ister; OpenSSL 3 kaldırdı, pycryptodome'da var. Giriş servisindeki şimle aynı."""
    try:
        hashlib.new("md4", b"")
        return
    except ValueError:
        pass
    from Crypto.Hash import MD4  # type: ignore[import-not-found]

    builtin = hashlib.new

    class _Md4:
        def __init__(self, data: bytes = b"") -> None:
            self.h = MD4.new(data)

        def update(self, data: bytes) -> None:
            self.h.update(data)

        def digest(self) -> bytes:
            return self.h.digest()

    hashlib.new = lambda name, data=b"", **kw: _Md4(data) if name.lower() == "md4" else builtin(name, data, **kw)  # type: ignore[assignment]


def directory_test(username: str = "") -> tuple[bool, str]:
    """Servis hesabıyla dizine bağlanır; ad verilmişse o kullanıcıyı da arar. Giriş servisiyle aynı yol: NTLM, düz bağlama yok."""
    cfg = {k: conf(k) for k in store_keys("ad")}
    missing = [_BY_KEY[k]["label"] for k in ("AD_HOST", "AD_NETBIOS", "AD_BASE_DN", "AD_BIND_USER", "AD_BIND_PASSWORD") if not cfg[k]]
    if missing:
        return False, "Eksik: " + ", ".join(missing) + "."
    try:
        from ldap3 import NONE, NTLM, SUBTREE, Connection, Server  # type: ignore[import-not-found]
        from ldap3.core.exceptions import LDAPException  # type: ignore[import-not-found]
        _ensure_md4()
    except ImportError as e:
        return False, f"Sunucuda ldap3 kurulu değil: {e}"
    t0 = time.monotonic()
    try:
        server = Server(cfg["AD_HOST"], port=int(cfg["AD_PORT"] or 389), get_info=NONE, connect_timeout=5)
        conn = Connection(server, user=f'{cfg["AD_NETBIOS"]}\\{cfg["AD_BIND_USER"]}', password=cfg["AD_BIND_PASSWORD"],
                          authentication=NTLM, receive_timeout=10)
        if not conn.bind():
            return False, f"Servis hesabı reddedildi: {conn.result.get('description') or conn.result}"
        try:
            name = "".join(ch for ch in username.strip().split("\\")[-1].split("@")[0] if ch.isalnum() or ch in "._-") or cfg["AD_BIND_USER"]
            conn.search(cfg["AD_BASE_DN"], f"(&(objectClass=user)(sAMAccountName={name}))", SUBTREE,
                        attributes=["sAMAccountName", "displayName", "userAccountControl"], size_limit=2)
            ms = int((time.monotonic() - t0) * 1000)
            if len(conn.entries) != 1:
                return False, f"Bağlantı kuruldu ({ms} ms) ama «{name}» hesabı bulunamadı."
            e = conn.entries[0]
            uac = int(e.userAccountControl.value or 0)
            disabled = bool(uac & 2)
            return (not disabled,
                    f"Bağlandı ({ms} ms). {e.displayName.value or name} ({e.sAMAccountName.value})"
                    + (" — hesap devre dışı." if disabled else " — hesap etkin."))
        finally:
            conn.unbind()
    except LDAPException as e:
        return False, f"{type(e).__name__}: {e}"[:400]
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"[:400]


# ------------------------------------------------------------------ bağlantı denemeleri
# Her deneme kaydedilmiş ayarla, gerçek bağlantıyı kurarak yapılır: "ayar dolu mu" diye bakmak
# bağlantının çalıştığını söylemez. Hata metni olduğu gibi döner, çünkü düzeltecek kişi onu okur.


def _thousands(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _test_connector(extra: Optional[dict[str, Any]] = None):
    """Bağlantı dosyasındaki tanımla yeni bir bağlantı. Canlı bağlantıya dokunulmaz: deneme
    yanlış ayarla asılı kalırsa kullanıcının sorusu bundan etkilenmesin."""
    from semantic_layer.profiler.connectors import connector_from_config

    cfg = dict(_file("db"))
    cfg.update(extra or {})
    cfg.setdefault("datasource", "mssql")
    cfg.setdefault("login_timeout", int(os.environ.get("ADMIN_TEST_LOGIN_TIMEOUT", "10")))
    return connector_from_config(cfg), str(cfg.get("datasource", "")).lower()


def _db_missing() -> list[str]:
    return [_BY_KEY[k]["label"] for k in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD") if not conf(k)]


def database_test() -> tuple[bool, str]:
    """Logo veritabanına bağlanır ve hangi veritabanına, hangi hesapla bağlandığını söyler."""
    if missing := _db_missing():
        return False, "Eksik: " + ", ".join(missing) + "."
    t0 = time.monotonic()
    conn = None
    try:
        conn, ds = _test_connector()
        if ds in ("mssql", "sqlserver"):
            sql = ("SELECT DB_NAME() AS db, SUSER_SNAME() AS hesap, "
                   "(SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES) AS tablolar, "
                   "CAST(SERVERPROPERTY('ProductVersion') AS nvarchar(40)) AS surum")
        else:
            sql = "SELECT 1 AS db"
        _, rows, _ = conn.execute(sql, 1)
        ms = int((time.monotonic() - t0) * 1000)
        r = rows[0] if rows else {}
        if "hesap" not in r:
            return True, f"Bağlandı ({ms} ms)."
        return True, (f"Bağlandı ({ms} ms). {r.get('db')} · {r.get('hesap')} · "
                      f"{_thousands(int(r.get('tablolar') or 0))} tablo · sürüm {r.get('surum')}")
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"[:400]
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


def crm_test() -> tuple[bool, str]:
    """CRM artık ayrı bir sunucuda (.28 prod, CRMDATBASE). Deneme, CRM bağlantısının
    (crm-mssql-connection.json) Timas_MSCRM veritabanını okuyup okuyamadığına bakar."""
    schema = conf("CRM_SCHEMA").strip()
    if not schema:
        return False, "CRM şeması girilmemiş."
    _crm_file = os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json")
    if not os.path.exists(_crm_file):
        return False, "CRM bağlantı dosyası bulunamadı: " + _crm_file
    db, _, sch = schema.rpartition(".")
    if not db:
        db, sch = "", schema
    for part in (db, sch):
        if part and not all(ch.isalnum() or ch in "_-$" for ch in part):
            return False, f"«{schema}» geçerli bir ad değil; veritabanı.şema bekleniyor."
    t0 = time.monotonic()
    conn = None
    try:
        from semantic_layer.profiler.connectors import connector_from_file
        conn = connector_from_file(_crm_file)
        qual = f"[{db}]." if db else ""
        _, rows, _ = conn.execute(
            f"SELECT COUNT(*) AS tablolar FROM {qual}INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = '{sch}'", 1)
        n = int((rows[0].get("tablolar") if rows else 0) or 0)
        ms = int((time.monotonic() - t0) * 1000)
        if not n:
            return False, f"Bağlandı ({ms} ms) ama «{schema}» altında tablo görünmüyor; ad ya da okuma izni yanlış olabilir."
        return True, f"Bağlandı ({ms} ms). {schema} · {_thousands(n)} tablo okunabiliyor."
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"[:400]
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


#: Model denemesinin LLM kapısı: app.py bağlar (`set_llm_gate`). İmza: fn(base, model, key, timeout) → kapıdan geçen
#: istemci (`QueuedLlm`; `chat`, `last_wait_ms`) ya da None. Deneme de öteki modüllerle aynı sıradan ve slottan geçer:
#: `LlmClient` burada doğrudan kurulmaz (docs/LLM-KAPISI.md).
_llm_gate: Optional[Callable[[str, str, str, float], Any]] = None


def set_llm_gate(fn: Optional[Callable[[str, str, str, float], Any]]) -> None:
    global _llm_gate
    _llm_gate = fn


def llm_test() -> tuple[bool, str]:
    """Modele tek kelimelik bir soru sorar; cevabın içeriği değil, geldiği önemli. Kaydedilmiş ayarla, LLM kapısından
    (sıra + slot) gider; sırada beklenen süre ayrıca yazılır."""
    base, model, key = conf("OPENAI_API_BASE"), conf("LLM_MODEL_NAME"), conf("OPENAI_API_KEY")
    if not base or not model:
        return False, "Model adresi ya da model adı girilmemiş."
    if _llm_gate is None:
        return False, "Model kapısı bu süreçte bağlı değil; deneme yapılamadı."
    timeout = float(os.environ.get("ADMIN_LLM_TEST_TIMEOUT", "60"))
    t0 = time.monotonic()
    try:
        llm = _llm_gate(base, model, key, timeout)
        if llm is None:
            return False, "Model kapısı bu ayarla istemci kuramadı."
        out = llm.chat([{"role": "user", "content": "Yalnızca TAMAM yaz."}], max_tokens=8)
        ms = int((time.monotonic() - t0) * 1000)
        wait = int(getattr(llm, "last_wait_ms", 0) or 0)
        queued = f"; {wait} ms sırada bekledi" if wait else ""
        text = " ".join(re.sub(r"<think>.*?</think>", "", out or "", flags=re.S).split())[:60]
        if not text:
            return False, f"Model bağlandı ({ms} ms{queued}) ama boş cevap verdi."
        return True, f"Cevap geldi ({ms} ms{queued}). {LLM_DISPLAY} → «{text}»"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"[:400]


def store_test() -> tuple[bool, str]:
    """Ayarların, kayıtların, panoların ve raporların tutulduğu meta veritabanı."""
    if _engine is None:
        return False, "Meta veritabanı bağlantısı kurulmamış."
    t0 = time.monotonic()
    try:
        with _engine.connect() as c:
            n = c.execute(sa.select(sa.func.count()).select_from(SETTINGS)).scalar() or 0
            audits = c.execute(sa.select(sa.func.count()).select_from(AUDIT)).scalar() or 0
        ms = int((time.monotonic() - t0) * 1000)
        return True, f"Bağlandı ({ms} ms). {n} kayıtlı ayar, {_thousands(int(audits))} değişiklik kaydı."
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"[:400]


def email_config_test() -> tuple[bool, str]:
    """E-posta için bağlantı kurmadan bakılabilecek tek şey ayarın tamlığı; gerçek deneme
    bir adrese posta gönderir ve onu kullanıcı ister (`smtp_test`)."""
    from semantic_bridge import alerts as alerts_mod

    cfg = alerts_mod.smtp_settings()
    if not cfg:
        return False, "SMTP sunucusu ya da gönderen adresi girilmemiş."
    return True, f"Ayarlı: {cfg['host']}:{cfg['port']} · gönderen {cfg['sender']}. Gerçek deneme için bir adrese gönderin."


def _seo_check() -> tuple[bool, str, list[dict[str, Any]]]:
    """T-soft ve girilmiş her Google/Bing/Cloudflare anahtarı ayrı satırda (yalnız okuma)."""
    from semantic_bridge.seo_geo import checks

    parts = checks.seo_parts()
    return (*checks.summarize(parts), parts)


def _geo_check() -> tuple[bool, str, list[dict[str, Any]]]:
    """Yapay zekâ arama motorlarının anahtarları; soru sorulmaz, kota harcanmaz."""
    from semantic_bridge.seo_geo import checks

    parts = checks.geo_parts()
    return (*checks.summarize(parts), parts)


def mailbox_test() -> tuple[bool, str]:
    """Kurumsal e-posta kutusu: ayar tamsa kutunun profilini ve etiket listesini okur (yalnız okuma)."""
    from semantic_bridge import mailbox_sources as ms

    state = ms.connection_state(conf)
    if not state["connected"]:
        return False, f"Kutu bağlı değil: {state['reason']}"
    return ms.source(conf).test()


#: Tek tuşla çalışan denemeler. E-posta burada yalnız ayar bütünlüğüne bakar: bir denemenin
#: kimseye posta göndermemesi gerekir.
CHECKS: list[dict[str, Any]] = [
    {"id": "database", "group": "database", "label": "Logo veritabanı", "run": database_test},
    {"id": "crm", "group": "crm", "label": "CRM veritabanı", "run": crm_test},
    {"id": "llm", "group": "llm", "label": "Yapay zekâ modeli", "run": llm_test},
    {"id": "directory", "group": "directory", "label": "Active Directory", "run": lambda: directory_test("")},
    {"id": "email", "group": "email", "label": "E-posta ayarı", "run": email_config_test},
    {"id": "seo", "group": "seo", "label": "T-soft ve Google", "run": lambda: _seo_check()},
    {"id": "geo", "group": "geo", "label": "Yapay zekâ arama motorları", "run": lambda: _geo_check()},
    {"id": "mailbox", "group": "mailbox", "label": "Kurumsal e-posta kutusu", "run": mailbox_test},
    {"id": "store", "group": None, "label": "Meta veritabanı", "run": store_test},
]
_CHECK_BY_ID = {c["id"]: c for c in CHECKS}


def run_check(check_id: str) -> dict[str, Any]:
    c = _CHECK_BY_ID.get(check_id)
    if not c:
        raise AdminError(f"Bilinmeyen deneme: {check_id}")
    t0 = time.monotonic()
    parts: Optional[list[dict[str, Any]]] = None
    try:
        out = c["run"]()
        ok, message = out[0], out[1]
        if len(out) > 2:
            parts = out[2]
    except Exception as e:  # noqa: BLE001
        ok, message = False, f"{type(e).__name__}: {e}"[:400]
    res = {"id": c["id"], "group": c["group"], "label": c["label"], "ok": ok, "message": message,
           "ms": int((time.monotonic() - t0) * 1000), "at": _iso(_now())}
    if parts is not None:
        res["parts"] = parts
    return res


def run_checks() -> dict[str, Any]:
    """Hepsi sırayla: tek bağlantı üstünde koşan denemeler birbirini beklesin."""
    items = [run_check(c["id"]) for c in CHECKS]
    return {"items": items, "ok": all(i["ok"] for i in items), "at": _iso(_now())}


def system_info() -> dict[str, Any]:
    """Ekrandan değiştirilmeyen, servisin açılışta okuduğu tanımlar. Görünür olmaları gerekir:
    bir ayarın neden beklendiği gibi davranmadığı çoğu zaman burada yazar."""
    def mask(dsn: str) -> str:
        import re as _re
        return _re.sub(r"//([^:/@]+):[^@]*@", r"//\1:***@", dsn or "")

    return {"items": [
        {"label": "Bağlantı dosyası", "value": DB_FILE},
        {"label": "Giriş servisi dosyası", "value": AD_FILE},
        {"label": "Meta veritabanı", "value": mask(os.environ.get("SEMANTIC_STORE_DSN") or os.environ.get("NANOBASE_META_DSN", ""))},
        {"label": "Katalog kapsamı (şema)", "value": os.environ.get("SEMANTIC_SCHEMA", "dbo")},
        {"label": "Katalog kapsamı (tablo deseni)", "value": os.environ.get("SEMANTIC_TABLE_LIKE", "") or "tümü"},
        {"label": "Bilgi klasörü", "value": os.environ.get("SEMANTIC_KNOWLEDGE_DIR", "")},
        {"label": "Rapor klasörü", "value": os.environ.get("REPORT_DIR", "")},
        {"label": "Servis ortam dosyası", "value": "/etc/nanobase/semantic-bridge.env"},
    ]}


# ------------------------------------------------------------------ değişiklik kaydı


#: Kişi olmayan yapan (zamanlayıcı, gece işi, otomatik kural): kayıtta ürünün adıyla görünür, «sistem» değil.
_SYSTEM_ACTORS = frozenset({"sistem", "system", "zamanlayıcı", "scheduler"})


def system_actor(actor: Optional[str]) -> str:
    a = (actor or "").strip()
    return LLM_DISPLAY if not a or a.lower() in _SYSTEM_ACTORS else a


def audit(engine: Optional[sa.engine.Engine], actor: Optional[str], action: str, kind: str,
          object_id: Optional[str], title: Optional[str], detail: Any = None) -> None:
    """İşlem kaydı. İstek içinden çağrıldıysa isteğin kimliği, IP'si, tarayıcısı ve ekranı da yazılır (denetim izi
    aynı isteğin değiştirdiği satırları buradan bağlar). Veritabanına yazılamazsa diske düşer, sonra aktarılır."""
    from semantic_bridge import audit_trail

    ctx = audit_trail.current() or {}
    row = dict(at=_now(), actor=system_actor(actor)[:120], action=action[:16], kind=kind[:24],
               object_id=(str(object_id)[:120] if object_id else None), title=(str(title)[:300] if title else None),
               detail=json.dumps(detail, ensure_ascii=False, default=str) if detail is not None else None,
               rid=ctx.get("rid"), ip=ctx.get("ip"), ua=ctx.get("ua"), page=ctx.get("page"))
    eng = engine or _engine
    if eng is None:
        audit_trail.spool("action", row)
        return
    try:
        ensure(eng)
        with eng.begin() as c:
            c.execute(AUDIT.insert().values(**row))
    except Exception as e:  # noqa: BLE001
        log.warning("admin: değişiklik kaydı yazılamadı, diske alındı (%s %s): %s", action, kind, e)
        audit_trail.spool("action", row)


def audit_list(engine: sa.engine.Engine, *, kind: Optional[str] = None, actor: Optional[str] = None,
               action: Optional[str] = None, q: Optional[str] = None, before: Optional[int] = None,
               limit: int = 100) -> dict[str, Any]:
    stmt = sa.select(AUDIT)
    if kind:
        stmt = stmt.where(AUDIT.c.kind == kind)
    if actor:
        # Eski kayıtlarda kişi olmayan yapan «sistem» yazılıydı; ürün adıyla süzünce onlar da gelir.
        names = [actor] + (sorted(_SYSTEM_ACTORS) if system_actor(actor) == LLM_DISPLAY else [])
        stmt = stmt.where(AUDIT.c.actor.in_(names))
    if action:
        stmt = stmt.where(AUDIT.c.action == action)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(sa.or_(AUDIT.c.title.ilike(like), AUDIT.c.object_id.ilike(like), AUDIT.c.actor.ilike(like)))
    if before:
        stmt = stmt.where(AUDIT.c.id < before)
    limit = max(1, min(int(limit or 100), 500))
    with engine.connect() as c:
        rows = c.execute(stmt.order_by(AUDIT.c.id.desc()).limit(limit + 1)).mappings().all()
    items = [{
        "id": r["id"], "at": _iso(r["at"]), "actor": system_actor(r["actor"]), "action": r["action"], "kind": r["kind"],
        "kindLabel": KIND_LABEL.get(r["kind"], r["kind"]), "objectId": r["object_id"], "title": r["title"],
        "detail": json.loads(r["detail"]) if r["detail"] else None,
    } for r in rows[:limit]]
    return {"items": items, "next": items[-1]["id"] if len(rows) > limit else None}


def changes(before: dict[str, Any], after: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    """İki kaydın kayda değer alanlarındaki farkı: {alan: {from, to}}."""
    out = {}
    for k in keys:
        if before.get(k) != after.get(k):
            out[k] = {"from": before.get(k), "to": after.get(k)}
    return out


# ------------------------------------------------------------------ herkesin tanımları


def all_reports(engine: sa.engine.Engine, tenant: str, ds: str) -> list[dict[str, Any]]:
    from semantic_bridge import reports as rm

    rm.ensure(engine)
    with engine.connect() as c:
        rows = c.execute(rm.list_stmt(tenant, ds, None)).mappings().all()
    return [{**rm.to_dict(r), "owner": r["username"]} for r in rows]


def all_cards_stmt(tenant: str, ds: str) -> Any:
    """Bütün pano kartları (yönetim listesi ve genel durum sayacı; sorgu bilgisi aynı ifadeyi gösterir)."""
    from semantic_bridge import board as bm

    C = bm.CARDS
    cols = [C.c.id, C.c.username, C.c.title, C.c.question, C.c.chart, C.c.refresh, C.c.refresh_at,
            C.c.created_at, C.c.updated_at, C.c.result_at, C.c.last_auto_at, C.c.last_error]
    return sa.select(*cols).where(C.c.tenant_id == tenant, C.c.datasource_id == ds).order_by(C.c.username, C.c.position)


def all_cards(engine: sa.engine.Engine, tenant: str, ds: str) -> list[dict[str, Any]]:
    from semantic_bridge import board as bm

    bm.ensure(engine)
    with engine.connect() as c:
        rows = c.execute(all_cards_stmt(tenant, ds)).mappings().all()
    return [{"id": r["id"], "owner": r["username"], "title": r["title"], "question": r["question"] or "",
             "chart": r["chart"], "refresh": r["refresh"], "refreshAt": r["refresh_at"],
             "createdAt": _iso(r["created_at"]), "updatedAt": _iso(r["updated_at"]),
             "resultAt": _iso(r["result_at"]), "lastAutoAt": _iso(r["last_auto_at"]), "lastError": r["last_error"]}
            for r in rows]


def delete_card(engine: sa.engine.Engine, tenant: str, ds: str, card_id: str) -> Optional[dict[str, Any]]:
    from semantic_bridge import board as bm

    C = bm.CARDS
    with engine.begin() as c:
        row = c.execute(sa.select(C.c.id, C.c.username, C.c.title).where(
            C.c.id == card_id, C.c.tenant_id == tenant, C.c.datasource_id == ds)).mappings().first()
        if not row:
            return None
        c.execute(C.delete().where(C.c.id == card_id))
    return dict(row)


def users_stmts(tenant: str, ds: str) -> dict[str, Any]:
    """Kişi başına kart, plan ve kayıtlı işlem sayımı (sorgu bilgisi aynı ifadeleri gösterir)."""
    from semantic_bridge import board as bm
    from semantic_bridge import reports as rm

    return {
        "cards": sa.select(bm.CARDS.c.username, sa.func.count(), sa.func.max(bm.CARDS.c.updated_at))
        .where(bm.CARDS.c.tenant_id == tenant, bm.CARDS.c.datasource_id == ds).group_by(bm.CARDS.c.username),
        "reports": sa.select(rm.REPORTS.c.username, sa.func.count(), sa.func.max(rm.REPORTS.c.updated_at))
        .where(*rm._scope(tenant, ds, None)).group_by(rm.REPORTS.c.username),
        "actions": sa.select(AUDIT.c.actor, sa.func.count(), sa.func.max(AUDIT.c.at))
        .where(AUDIT.c.actor.notin_(sorted(_SYSTEM_ACTORS | {LLM_DISPLAY}))).group_by(AUDIT.c.actor),
    }


def users(engine: sa.engine.Engine, tenant: str, ds: str) -> list[dict[str, Any]]:
    """Sistemi kullanan kişiler: tanımı ya da kaydı olan her hesap, son hareketiyle."""
    from semantic_bridge import board as bm
    from semantic_bridge import reports as rm

    people: dict[str, dict[str, Any]] = {}

    def person(u: str) -> dict[str, Any]:
        key = (u or "").lower()
        return people.setdefault(key, {"username": u, "cards": 0, "reports": 0, "actions": 0, "lastSeen": None,
                                       "admin": is_admin(u)})

    def seen(p: dict[str, Any], at: Optional[datetime]) -> None:
        s = _iso(at)
        if s and (p["lastSeen"] is None or s > p["lastSeen"]):
            p["lastSeen"] = s

    st = users_stmts(tenant, ds)
    with engine.connect() as c:
        for u, n, last in c.execute(st["cards"]).all():
            p = person(u); p["cards"] = n; seen(p, last)
        for u, n, last in c.execute(st["reports"]).all():
            p = person(u); p["reports"] = n; seen(p, last)
        for u, n, last in c.execute(st["actions"]).all():
            p = person(u); p["actions"] = n; seen(p, last)
    for a in admins():
        person(a)["admin"] = True
    return sorted(people.values(), key=lambda p: (p["lastSeen"] or ""), reverse=True)


# ------------------------------------------------------------------ sistem durumu


def _unit(name: str) -> dict[str, Any]:
    """systemd birimini okur (yetki gerektirmez). systemctl yoksa bilinmiyor döner."""
    import subprocess

    props = "ActiveState,SubState,LastTriggerUSec,NextElapseUSecRealtime,Result"
    try:
        out = subprocess.run(["systemctl", "show", name, "-p", props], capture_output=True, text=True, timeout=5).stdout
    except Exception:  # noqa: BLE001
        return {"unit": name, "state": "unknown"}
    kv = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    return {"unit": name, "state": kv.get("ActiveState") or "unknown", "sub": kv.get("SubState"),
            "last": kv.get("LastTriggerUSec") or None, "next": kv.get("NextElapseUSecRealtime") or None,
            "result": kv.get("Result")}


TIMERS = [
    {"unit": "timas-alerts.timer", "label": "Uyarı kontrolü", "every": "15 dk"},
    {"unit": "timas-reports.timer", "label": "Planlı raporlar", "every": "her dakika"},
    {"unit": "timas-board.timer", "label": "Pano kartı tazeleme", "every": "15 dk"},
    {"unit": "timas-seo.timer", "label": "SEO & GEO eşitlemesi", "every": "gece 03:00"},
    {"unit": "nanobase-semantic-worker.timer", "label": "Gece katalog taraması", "every": "gece"},
    {"unit": "nanobase-semantic-watchdog.timer", "label": "Köprü sağlık denetimi", "every": "5 dk"},
]
SERVICES = [
    {"unit": "nanobase-semantic-bridge.service", "label": "Sorgu motoru (köprü)"},
    {"unit": "timas-login.service", "label": "Giriş servisi (Active Directory)"},
    {"unit": "timas-vpn-mfa.service", "label": "TİMAŞ VPN"},
]


_STAMP = r"\w{3} \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \S+"


def _timer_times() -> dict[str, tuple[Optional[str], Optional[str]]]:
    """Göreli (OnUnitActiveSec) zamanlayıcılarda `systemctl show` sıradaki anı boş verir; list-timers verir.
    Satır biçimi: NEXT LEFT LAST PASSED UNIT ACTIVATES — sıradaki yoksa satır "-" ile başlar."""
    import re
    import subprocess

    try:
        out = subprocess.run(["systemctl", "list-timers", "--all", "--no-legend", "--no-pager"],
                             capture_output=True, text=True, timeout=5).stdout
    except Exception:  # noqa: BLE001
        return {}
    times: dict[str, tuple[Optional[str], Optional[str]]] = {}
    for line in out.splitlines():
        unit = next((w for w in line.split() if w.endswith(".timer")), None)
        if not unit:
            continue
        stamps = re.findall(_STAMP, line)
        if line.lstrip().startswith("-"):
            times[unit] = (None, stamps[0] if stamps else None)
        else:
            times[unit] = (stamps[0] if stamps else None, stamps[1] if len(stamps) > 1 else None)
    return times


_UNIT_PROPS = "Id,ActiveState,SubState,LastTriggerUSec,NextElapseUSecRealtime,Result"


def _units(names: list[str]) -> dict[str, dict[str, Any]]:
    """Birimlerin hepsi tek `systemctl show` çağrısıyla (yetki gerektirmez). Çıktı birim başına boş satırla ayrılmış
    blok; blok `Id` ile eşlenir, eşlenemeyen birim tek başına okunur (`_unit`). Sonuç `_unit` ile birebir aynı biçim."""
    import subprocess

    try:
        out = subprocess.run(["systemctl", "show", *names, "-p", _UNIT_PROPS], capture_output=True, text=True,
                             timeout=5).stdout
    except Exception:  # noqa: BLE001 — systemctl yok: hepsi bilinmiyor (tek tek okumada da öyle)
        return {n: {"unit": n, "state": "unknown"} for n in names}
    found: dict[str, dict[str, Any]] = {}
    for block in out.split("\n\n"):
        kv = dict(line.split("=", 1) for line in block.splitlines() if "=" in line)
        name = kv.get("Id")
        if name in names and name not in found:
            found[name] = {"unit": name, "state": kv.get("ActiveState") or "unknown", "sub": kv.get("SubState"),
                           "last": kv.get("LastTriggerUSec") or None, "next": kv.get("NextElapseUSecRealtime") or None,
                           "result": kv.get("Result")}
    return {n: found.get(n) or _unit(n) for n in names}


#: Sistem durumu kısa bellekte (2026-09-29): yönetim ekranı açılışında 9 birim tek tek + zamanlayıcı listesi = 10
#: `systemctl` süreci ~5 sn sürüyordu. Şimdi iki süreç, aynı anda; sonuç 15 sn taze, 2 dk'ya kadar hemen dönüp arkada
#: yenilenir (birim durumu canlı bilgidir, rakam değildir).
_status_mem: Optional[Any] = None


def _read_system_status() -> dict[str, Any]:
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="systemctl") as ex:
        times_f = ex.submit(_timer_times)
        units_f = ex.submit(_units, [t["unit"] for t in TIMERS] + [s["unit"] for s in SERVICES])
        times, units = times_f.result(), units_f.result()
    timers = []
    for t in TIMERS:
        u = {**t, **units[t["unit"]]}
        nxt, last = times.get(t["unit"], (None, None))
        u["next"] = nxt or u.get("next")
        u["last"] = last or u.get("last")
        timers.append(u)
    return {"services": [{**s, **units[s["unit"]]} for s in SERVICES], "timers": timers}


def system_status(fresh: bool = False) -> dict[str, Any]:
    """`fresh`: beklenerek şimdi okunur («Verileri yenile», arka plan toplayıcıları)."""
    global _status_mem
    if _status_mem is None:
        from semantic_bridge.hizli_bellek import Bellek

        _status_mem = Bellek("yonetim.sistem-durumu", taze=15, bayat=120, en_cok=1)
    return _status_mem.al("sistem", _read_system_status, zorla=fresh)
