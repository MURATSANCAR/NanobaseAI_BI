# Modül yol haritası (2026-09-28)

Kaynak: kullanıcıyla «Yol haritamız» oturumu. Ayrıntı: bu klasördeki analiz belgeleri ve [README.md](README.md).

## Sıra

1. **Yarım kalanlar** — M2, M4, M6, M7, M8, SEO & GEO, Yetki A/B/C: `main`de; test sunucusu kabulü ve müşteri VM'ine toplu kurulum bekliyor.
2. **Editoryal zincirin kapanışı** — M1 (başvuru, yayın kurulu; dalda, test edilmedi), M6 (bitti).
3. **B bloku** — M9 (dalda, test edilmedi), M10 ve M12 (`main`de).
4. **M46 Bütçe & hedefler** — `main`de; M15, M17, M18, M29, M30 ve DYK hedefleri buradan okur.
5. **Kalan 47 modül** — analiz tamam; kodlama en fazla 5 eşzamanlı ajanla, öncelik sırası:
   - Ortak: Zeki AI seçim çağrısı (`QueuedLlm.choose`), Zeki AI sohbet kapsamının genişletilmesi, pazarlama çekirdeği, sayfa düzeyinde açık yetki (İK için).
   - Satış ve saha: M29, M30, M31, M32, M33.
   - Pazarlama: M15 (+çekirdek), M19, M53, M18, M17, M16, sonra M20–M24, M27, M28.
   - Hazırlık: H1 kategori ağacı, H4 kurumsal e-posta, H2 okur veri tabanı, H3 e-ticaret müşteri.
   - Altyapı ve destek: M48, M49, M50, M51.
   - Finans ve risk: M59, M54, M45, M47.
   - Dijital ve müşteri: M38, M37, M34, M35, M36, M39.
   - Platform ve lojistik: M42, M40, M41, M43, M44, M52.
   - Yönetim: DYK (bütün modüllerin göstergeleri; en son).
   - İK: M57, M55, M56, M58; personel portalı (2026-09-29); sonra M60 izin yönetimi + İK e-posta bildirimleri (F1: bildirim kuyruğu + evrak talebi bildirimi + izin talep/onay/bakiye; F2: ekip takvimi, hakediş gece işi, bordro listesi).

## Sonraya bırakılanlar (açık notlar)

### Trendyol ve Amazon satış modeli (M40, M41, M42)
- TİMAŞ'ın Trendyol'da kendi mağazası var mı, yoksa ürünler bir bayi/dağıtıcı üzerinden mi satılıyor? CRM'de yalnız 2020 tarihli bir test kaydı var.
- Amazon ilişkisi konsinye mi (Amazon'a mal gönderilip satıldıkça faturalanıyor), yoksa Seller Central satıcı hesabı mı?
- Satıcı API (Trendyol Partner API, Amazon SP-API) erişimi ve okuma yetkisi kimde; verilebilir mi?
- Pazar yeri carileri Logo'da hangi kodlarla duruyor; hangi carinin hangi platform olduğu kullanıcı onayıyla eşlenecek.
- Karar gelene kadar: M40–M42 Logo cari satışı + panelden indirilen Excel yüklemesiyle çalışır; mağazaya hiçbir yazma yapılmaz.
- 2026-09-29: kullanıcı işi başlattı; kodlama öncesi analiz ve karar soruları [../trendyol-amazon-satis-modeli.md](../trendyol-amazon-satis-modeli.md).

### Diğer açık konular
- CRM `new_kargofirmasi` tablosunda kargo firması kullanıcı adı/parola/token/client secret alanları var — BT'ye iletilecek.
- Genel e-posta kutusu (timas@) Google mı Microsoft mu, hangi yetkiyle okunur (H4).
- Site analitiği (GA4) okuma yetkisi (H3, M21, M34).
- T-soft siparişlerinin Logo'daki cari kodu (H3, M34).
- Bülten/SMS platformu (H2, M24).
- Kurul (YK) CRM sözleşme akışında yönetim kurulu mu yayın kurulu mu (M54, DYK).
- Logo .155 kopyası 17.08.2026'da donmuş; canlı Logo (.25) erişimi.
