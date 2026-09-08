# Üretim açıklarının kapatılması — 9 Eylül 2026

Bu rapor önceki prod-readiness raporundaki erişim, süreç belleği, takip sorusu ve ürün satış yokluğu bulgularının son durumudur. Genel serbest soru doğruluğuna ilişkin bağımsız başarı yüzdesi değildir.

## Çalışan sunucu

- Timaş nginx basic-auth yeniden etkin; mevcut kullanıcı dosyası korundu. Dışarıdan kimliksiz ask/run_sql 401.
- Köprüye ayrı SEMANTIC_CALLER_TOKEN ve SEMANTIC_ADMIN_TOKEN tanımlandı. Nginx yalnız giriş korumasından geçen isteklerde caller anahtarını ekler. Admin anahtarı tarayıcıya enjekte edilmez. İç uçlarda anahtarsız ask/run_sql 401, yönetici anahtarsız reload 403.
- Ana API AUTH_MODE=jwt, NANOBASE_ENV=production ve rastgele güçlü JWT anahtarı ile yeniden başladı. Kimliksiz sources 401; 60 saniyelik yetkili test token'ı ile 200. Ana API istemcileri artık geçerli JWT sunmalıdır; portal oturum açma arayüzü bu çalışmada uçtan uca sınanmadı.
- Köprü tek worker. SQL sonucu, tablo, grafik ve dışa aktarım aynı sonuç kimliğine bağlı. Her başarılı test sorusunun saklanan sonucu üç kez okundu: 12/12 aynı önizleme, HTTP 200.
- Deploy betikleri tek worker ve JWT ayarlarını korur; doğrulama çağrıları kimlik doğrular. Gece worker reload çağrısı ayrı admin anahtarını kullanır.

## Sorgu davranışı

| Soru / aynı konuşmadaki takip | Canlı sonuç | Kanıt |
|---|---|---|
| 2026 kanal bazında net ciro | 17 satır | 2026 aralığı, 411 tabloları |
| Peki geçen yıl? | 17 satır | 2025 aralığı, 211 tabloları; aynı ölçü/kırılım |
| Sadece Ankara | 3 satır | 2025 korunuyor, CITYCODE=ANKARA |
| hiç satmayan ürünler | 500 satır, truncated=true | Aynı firma içinde tarihli NOT EXISTS; varsayılan 2026 |

Takipler son başarılı semantik plandan tamamlanıp yeniden çözülür. Süresi geçmiş/olmayan bağlamda tam soru istenir. Tek ve tam değer eşleşmesi INFERRED filtre olarak kaydedilir; belirsiz veya kısmi eşleşme kabul edilmez.

Ürün satış yokluğu, Logo bilgi paketindeki açık satış tanımı ve profillenmiş FK'lerle sınırlıdır. İptal satır/fatura, malzeme dışı satır, satın alma ve iade satış olayı sayılmaz. Satılıp iade edilen ürün “hiç satmayan” olmaz. Sorgu tüm geçmişi veya veri yükleme bütünlüğünü kanıtlamaz; dönem ve kapsam notu cevaba eklenir. 500 mevcut yürütme sınırıdır, gerçek toplamın 500 olduğu iddia edilmez. Tanımlanmamış yokluk ilişkileri hedefli netleştirme ister.

Denetim, bu sınırlı deterministik yokluk yolunun ürettiği AST'yi sözleşmeyle karşılaştırır. İlişki, dönem veya satış koşulu değişirse çalıştırılmaz. Genel LLM anti-join eşdeğerliği kabul edilmez.

## Doğrulama

- Kontrollü veri: hiç hareket etmeyen, yalnız satın alınan, iptal satışı olan, yalnız iade edilen, geçen yıl satılan ve satılıp iade edilen ürünler.
- Bozulmuş SQL: NOT EXISTS, tarih, korelasyon ve işlem kodu değişimleri reddediliyor. Firma karışması engelleniyor.
- Geniş test koşusu: 1982 geçti, 2 atlandı (o aşamada 382 semantik + 1600 diğer backend).
- Son semantik paket: **385 geçti**. Sabit 50ms beklemeye bağlı aralıklı kuyruk testi model başlangıç sinyaliyle senkronize edildi.
- Bash sözdizimi ve git diff --check başarılı.
- Canlı HTTP kanıtı: artifacts/prod-closure-20260909.json. Kişisel giriş parolaları/JWT anahtarları repoya alınmadı.

## Geri dönüş

Kaynak yedeği sunucuda /tmp/bi-before-closure-1788905497.tgz. Nginx giriş öncesi yedeği /etc/nginx/backups/portal-before-auth-1788905000; erişimi geri açacak eski ayarı üretimde kullanmayın. Çalışan servisler nanobase-semantic-bridge ve nanobase-bi-api aktif.
