# Kaynak destekli editör soru taslağı bileşeni

Yeni `frontend/src/SourceQuestionForm.tsx`, mevcut ekranlara veya dondurulmuş V15 frontend imajına bağlanmadan hazırlandı. Props: `token`, `generationId`, `onQueued(jobId): Promise<void>`.

- `GET /v1/generations/{id}/source-preview` yanıtında `ready=true` ve tam `PARTIAL_SOURCE_SUPPORTED_DRAFT` kapsamı görülmeden gönderim açılmaz. Hazır değilse Türkçe açıklama ve yeniden kontrol düğmesi gösterilir. Tanınmayan neden kodu kullanıcıya teknik metin olarak basılmaz; genel kullanılamıyor açıklaması gösterilir.
- `POST /v1/questions`, yalnız `{generation_id, question, mode:'editor_preview'}` gönderir. Kırpılmış soru 3–1000 Unicode kod noktası olmalıdır. Aynı soru için idempotency anahtarı bileşen ömrü boyunca korunur; bağlantı/yanıt hatası soruyu veya anahtarı silmez. Başarılı cevapta iş kimliği korunur; sonrasında aynı soru yeniden POST edilmez, mevcut iş açılır. Sayfa yenilemeleri arasında kalıcılık iddiası yoktur.
- POST yanıtı `job_id`, `generation_id`, `mode` açısından kontrol edilir. Gerçek durum yalnız `GET /v1/answers/{jobId}` yanıtındaki `job_status` ile gösterilir; QUEUED/RUNNING beş saniyede sorgulanır, terminal durumda sorgulama durur. POST başarısını tamamlanmış cevap gibi göstermez. Eski soru izlenirken metin değiştirilirse durumun hangi gönderilen soruya ait olduğu açık yazılır.
- Nesil veya erişim anahtarı değişiminde istekler iptal edilir ve geç cevaplar sürüm kontrolüyle yok sayılır. Parent `onQueued` asenkron işlemi de parent tarafında güncel nesle bağlanmalıdır; bileşen parent'ın başlamış callback içindeki durum değişikliğini geri alamaz.
- Mevcut `upload-book`, `hint`, `primary`, `error` stilleri kullanılır. Textarea kendi genişliğinde kalır ve yalnız dikey büyütülebilir. Sayfa taşmasını gizleyen stil yoktur.

Yayımlanmış cevap, tam kitap kabulü veya editör onayı iddiası yoktur. Gerçek endpoint/worker entegrasyonu root tarafından yapılacaktır. Yeni bileşen şu an main.tsx'e eklenmedi; mevcut frontend dosyaları değiştirilmedi.

## Kabul sınırı

Yalnız statik kod/sözleşme incelemesi yapıldı. Yerel test, build, mock, ağ simülasyonu veya deployment çalıştırılmadı. Gerçek API/DB ile soru gönderme, iş izleme, hata sonrası aynı anahtarla dönüş, nesil değişiminde geç cevap engeli ve 320/390/768/1440 px tarayıcı kabulü **DOĞRULANAMADI**. Backend'in yeni preview sözleşmesi canlı olmadan bileşen üretime hazır sayılamaz.
