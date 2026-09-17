# API ve worker için ayrı gerçek veritabanı seçimi

API/worker ortak bağlantısı ve eski analiz checkpoint bağlantısı, `EDITOR_DB_NAME` ortam değişkenini kullanır. Değişken verilmezse varsayılan ad `editor` olarak kalır. Amaç, çalışan analizleri kesmeden aynı PostgreSQL sunucusunda gerçek veritabanının ayrı kopyasına bağlanan kabul ortamını çalıştırabilmektir. Kitap veya analiz verisi bu değişiklikle oluşturulmaz ya da değiştirilmez.

Bu değişiklik yalnız `backend/editor/config.py` ve `backend/editor/analysis.py` bağlantılarını kapsar. Compose varsayılanı değiştirilmedi. `backend/editor/migrate.py` ile `backend/migrations/env.py` içindeki migration bağlantıları hâlâ `editor` adını kullanır; dolayısıyla tüm kurulumun müşteri tarafından seçilen veritabanı adlarını desteklediği iddia edilmez. Ayrı veritabanı kopyasına migration çalıştırılacaksa bu bağlantılar ayrıca ele alınmalıdır.

Yerel test veya uzak yapılandırma değişikliği yapılmadı. Gerçek API/worker bağlantısının doğru veritabanını kullandığı ve mevcut koşuların etkilenmediği, ayrı kabul ortamında bağımsız PostgreSQL kanıtıyla doğrulanana kadar ürün kabulü **DOĞRULANAMADI** durumundadır.
