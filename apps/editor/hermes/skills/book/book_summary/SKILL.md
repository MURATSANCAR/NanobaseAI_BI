---
name: book_summary
description: En yeni neslin güncel, kaynaklı özet taslağını gösterir; hazır değilse gerçek iş durumunu bildirir.
version: 2.0.0
metadata:
  hermes: {category: book, tags: [book, summary]}
---
# book_summary

`list_books` → `latest_generation` → `get_report` okuma araçlarını kullan. Rapor `available=true` ise `content.book_summary` ve `content.chapters` içindeki cümleleri sayfa atıflarıyla göster. Her cümlenin `pages` alanını koru. Bu okuma yeni üretim veya yazma başlatmaz.

`available=false` ise eski nesle dönme. `latest_generation.job_id` ile `get_job_status` oku ve güncel çıktının hazır olmadığını söyle. Çalışan/bekleyen işi yeniden başlatmayı önerme.

`semantic_acceptance=false` veya `complete_book=false` sonucu tam kitap analitik kabulü değildir; kaynaklı taslak olduğunu belirt. Mühürlenme ve teknik başarı kabul yerine geçmez. Desteklenmeyen cümle veya belirsiz kimlikten kesin sonuç üretme. Kullanıcıya iç kimlik/alan adları yerine anlaşılır Türkçe ile durumu anlat.
