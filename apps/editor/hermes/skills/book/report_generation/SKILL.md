---
name: report_generation
description: En yeni neslin güncel atıflı rapor taslağını okur; revizyona bağlı üretimi sohbetten atlamaz.
version: 2.0.0
metadata:
  hermes: {category: book, tags: [book, report]}
---
# report_generation

`latest_generation` → `get_report` kullan. `available=true` ise güncel raporu ve açık kabul kontrollerini göster. `available=false` ise `job_id` ile `get_job_status` oku; rapor hazır olmadığını söyle. Kullanıcı rapor okumak istedi diye regresyon/yeni analiz/yazma başlatma.

Eski `create_analysis_report` yolu güncel TRACKED nesiller için kullanılamaz. Desteklenmeyen rapor türünü ANALYSIS raporuyla tamamlanmış gibi gösterme; o değerlendirme henüz üretilmemiştir. Eski rapor veya nesle dönme.

`semantic_acceptance=false` ise analitik kabul tamamlanmamıştır. Teknik SUCCEEDED veya mühürlenme bu sonucu değiştirmez. Kanıt sayfalarını koru, açık incelemeleri açıkça belirt; aday bulguyu kesin hata sayma.
