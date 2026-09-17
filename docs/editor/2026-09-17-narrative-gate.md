# Sayfa rolü kapısı — gerçek aday ölçümü

## V8 gerçek entegrasyon kabulü — 14:22 UTC

`narrative-coverage-v8-20260917`, stage API 18810, nesil `7e7db466-3576-4c23-85b2-73483ab4508e`: genel `verify-narrative-coverage.py` ile öncelik listesindeki gerçek 2/13/29. sayfalar API/PostgreSQL ve kullanılan V7 ebeveyn ham kaynaklarıyla karşılaştırıldı. Üç sayfa kontrolü geçti. Sayfa 2 `FRONT_MATTER`: önceki dört eşleşen adayın tamamı artık bloke, MATCH 0. Sayfa 13 `NARRATIVE`: dört adaydan mevcut ikisi MATCH, ikisi bloke. Sayfa 29 `UNKNOWN`: aday 0. Ham metin, bbox, diğer okuyucu çıktıları ve yeniden okumalar aynı; manuel inceleme 0, doğrulayıcı veri yazımı 0.

Görsel kapsam atlama sayıları aynı sayfa sırasıyla 5/1/0; sayfa/figür kimliği kabulü kapalı. Kanıt: stage kökünde `evidence/narrative-coverage-integration-20260917T142236Z.json`. Bu, yayımlanan V8'in üç gerçek öncelik sayfasında entegrasyon kabulüdür; tüm kitap uçtan uca anlamsal kabulü değildir. Aşağıdaki aday ölçümleri önceki sürümlerin tarihçesidir.

17 Eylül: `source_pipeline.narrative_gate` aday genel düzeltmesi gerçek API/PostgreSQL kayıtlarında salt okunur ölçüldü. Üretime kurulmadı; eski kayıtlar yeniden yazılmadı. Promptta hikâye dışı sayfalarda boş aday istenmesi, yeniden kullanılan veya kurala uymayan model adaylarını tek başına engellemiyordu. Önceki kapı yalnız `EVENT` türünü engelliyordu; künye/etkinlik içindeki `STATEMENT` adayları `MATCH` kalabiliyordu.

Yeni kapı aday türünden bağımsızdır: `ACTIVITY`, `FRONT_MATTER`, `APPENDIX`, `UNKNOWN` için `NON_NARRATIVE_CLAIM_BLOCKED`; tanınmayan rol için `INVALID_PAGE_ROLE`. `NARRATIVE` ve `MIXED` mevcut kaynak kararını aynen korur. Rol sınıflandırmasının kendisinin doğruluğu bu ölçümle kabul edilmiş değildir.

## Gerçek sonuçlar

| Ortam | Tamamlanmış sayfa | Aday | Kapalı rollerde aday | Yeni bloke edilen eski MATCH | NARRATIVE/MIXED değişmeden |
|---|---:|---:|---:|---:|---:|
| Ana V5, API 8810 | 48 | 149 | 25 | 15 | 124 |
| Aktif V7, stage API 18810 | 8 | 19 | 11 | 4 | 8 |

V5 yeni engellenen 15 eşlik: künye 7, etkinlik 7, rolü bilinmeyen 1. Kalan 10 kapalı-rol adayı zaten başka sebeple engelliydi; bunları yeni kazanım saymıyoruz. V5'te 120 NARRATIVE ve 4 MIXED adayın kapısı değişmedi. APPENDIX veya geçersiz rol örneği bu gerçek kayıtlarda yok; o dalların gerçek senaryo kabulü verilmedi.

V7 ölçümü yalnız o anda tamamlanmış 1, 2, 3, 4, 5, 6, 13, 29. sayfaları kapsar. Künye içindeki dört `MATCH` adayı artık aday hesapta engelleniyor. Bu tamamlanmamış nesli 48 sayfa kabul edilmiş gibi raporlamıyoruz.

## Yöntem ve kanıt

`apps/editor/scripts/verify-narrative-gate-candidate.py` genel çevre değişkenleriyle çalışır: `EDITOR_VERIFY_ROOT`, `EDITOR_VERIFY_RUN_FILE`, `EDITOR_VERIFY_BASE_URL`, `EDITOR_VERIFY_CANDIDATE_CODE`. Tamamlanmış `page_checks` sınırı sabitlenir; her sayfanın gerçek `page_claims` HTTP çıktısı bağımsız PostgreSQL JSON kaydıyla karşılaştırılır. Aday dosyadan yalnız `narrative_gate` AST fonksiyonu çalıştırılır; bağımsız rol izin listesiyle her karar karşılaştırılır. Sonunda bütün ölçülen sayfa kayıtları yeniden okunup değişmezliği doğrulanır. Yerel test, mock, sentetik kitap, inference veya kaynak/inceleme yazımı yok.

- V5 nesli: `14a79646-79c6-4cdb-8714-00adf5698770`; kayıt snapshot SHA `7abf826dbb47c9f3e5ee6a3f9787088a961a57191c54433402589c17bc65c4a3`.
- V7 nesli: `ab85c397-25f9-4cd9-8291-fc6ffed8e61b`; kayıt snapshot SHA `24990b88fd95d0b95693724a73f743a3b3ca3dc13026c8feba0a6a3cffb8732f`.
- Ölçülen aday fonksiyon SHA: `9cb7b71a9e9f0611811389a0566ac1ce022802efdf7b6fff72c4f09bcde38fdb`.
- Ana kanıt: `/data/nanobaseai/editor/evidence/narrative-gate-candidate-20260917T141801994575Z.json`.
- Stage kanıtı: `/data/nanobaseai/editor-qualifications/source-boundaries-v4-r2-20260917/99881d8f/installation/evidence/narrative-gate-candidate-20260917T141741737153Z.json`.

JSON dosyalarında gerçek sayfa kayıt kimliği, aday liste adı/indeksi, eski ve yeni kapı bulunur; kitap cevabı modele verilmez. **Bu aday fonksiyonun gerçek kayıt ölçümüdür. Yeni yayın/nesilde uçtan uca ürün kabulü henüz DOĞRULANAMADI.**
