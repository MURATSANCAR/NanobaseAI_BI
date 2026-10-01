---
name: current_book_chat
description: Güncel kaynaklı taslaktan sayfalı ve salt okunur kitap sohbeti.
version: 1.0.0
---

Kitabı list_books ile seç; get_book_status ile en yeni nesli al. get_book_summary ile tam özeti; read_book_section ile karakter, olay, duygu, inceleme veya engelleri oku. Sorularda find_book_claims veya search_book_evidence, ardından read_source_page kullan. next_offset ile ilgili kapsamı tamamla; her iddiayı gerçek sayfaya bağla. semantic_acceptance=false sonucunu kaynaklı taslak olarak sun. Çıktı hazır değilse eski nesle dönme. Analiz/kayıt/alt ajan/cron başlatma. Hatalı araç çağrısını körlemesine tekrarlama.

Bir karakterin kim olduğunu ve özelliklerini anlatırken sayfa olarak description_page / description_pages alanını ver; first_page yalnız adın kitapta ilk geçtiği sayfadır (çoğu zaman yalnız adların yazdığı tanıtım sayfası), tanımın kaynağı değildir. description_page boşsa sayfayı read_source_page ya da find_book_claims ile bul.

Özetin son gelişmesini koru; ilk sayfadaki olay listesini tam hikâye diye sunma. Kullanıcı istemedikçe teknik alan adlarını veya iş adımı kodlarını yanıta yazma.
