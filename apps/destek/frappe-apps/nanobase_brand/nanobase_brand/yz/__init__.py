"""NanobaseAI destek yapay zekâ özellikleri (kullanıcı isteği 2026-09-28).

- kayit.py: yeni kayıtta sınıflama (tür, öncelik, ekip, duygu), yazışma özeti, yanıt taslağı,
  çözülen kayıttan makale taslağı — temsilci ekranındaki «NanobaseAI» bölümü bunları çağırır.
- bilgi.py: bilgi bankası (yayımlanmış makaleler + çözülen kayıtlar) ve gömme modeli.
- rapor.py: SLA riski ve haftalık yönetici raporu.
- llm.py: model çağrısı; her çağrı LLM kapısından (`/destek-llm/v1`, modül `destek`) gider.
"""
