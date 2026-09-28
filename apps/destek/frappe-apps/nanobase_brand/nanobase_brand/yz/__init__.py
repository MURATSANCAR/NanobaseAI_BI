"""NanobaseAI destek yapay zekâ özellikleri (kullanıcı isteği 2026-09-28).

- kayit.py: yeni kayıtta sınıflama (tür, öncelik, ekip, duygu), yazışma özeti, yanıt taslağı,
  çözülen kayıttan makale taslağı — temsilci ekranındaki «NanobaseAI» bölümü bunları çağırır.
- bilgi.py: bilgi bankası (yayımlanmış makaleler + çözülen kayıtlar) ve gömme modeli.
- rapor.py: SLA riski ve haftalık yönetici raporu.
- llm.py: model çağrısı; her çağrı LLM kapısından (`/destek-llm/v1`, modül `destek`) gider. `choose`: kapalı küme
  seçim + olasılık (`secim.py`, köprüdeki `QueuedLlm.choose` ile aynı yöntem).
- sinif.py: sınıflamanın kararı — konu köprüdeki M51 ile tek karar (`/destek-baglam/v1/classify`, ortak sınıf listesi),
  öncelik/ekip/duygu olasılık eşiğiyle.
"""
