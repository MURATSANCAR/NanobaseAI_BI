# Gerçek üretim koşusu — 2026-09-09 09:05 TRT

Ana sonuçlar sunucuda /data/nanobaseai/bi/backups/enduser-real-10000-20260909/results.jsonl. Ana koşu 58 benzersiz soruda duraklatıldı: 47 PASS (8 önizleme sınırlı), 9 LIVE_FAIL, 2 LIVE_RESPONSE_UNVERIFIED (NON_SQL_QUERY; cevap veremedi). Ana milestone bildirimi notified.json=50. 31–40:5 PASS/5 FAIL;41–50:6 PASS/4 FAIL.

İlk hatalar: P00017 ve P00048 bilgisini sözcüğü; P00026–P00034 net satışta iadelerin kaybolması. retry-v1 ayrı dizinde 11 tekrar:8 PASS/3 FAIL (P00029–31); bildirildi. Perakende net sorguları sadece TRCODE7 ile yanlış filtreye rağmen Ocak2022 verisinde tesadüfen eşleşti: SQL kapsamı ayrıca düzeltilmiştir; salt aynı sonuç genelleme kanıtı değildir.

Düzeltmeler üretimde:
- resolver: composed ölçüden sonra generic bilgi baş ismi, aradaki ölçü sözcükleri üzerinden bağlanır. Standalone bilgi korunur.
- question_facts: n_max parametresi; resolver n_max değerini sertifikalı katalog terimlerinin en uzununa göre hesaplar. Önceden dört kelimeli terimler bölünüyordu.
- register_enduser_net_sales.py: mevcut CERTIFIED net ciro INVOICE/STLINE tanımlarından 6 tam metrik: net satış tutarı, toptan net satış tutarı (3,8), perakende net satış tutarı (2,7). Eski tanımlar korunur.
- register_enduser_line_sales.py: mevcut sertifikalı net ciro STLINE.LINENET temelinin pozitif satış karşılığı, satış tutarı satır düzeyli anlamı. Toplam fatura NETTOTAL, ürün kırılımı LINENET; mevcut net ciro grain politikasıyla tutarlı. İşlem verisine yazım yok.
- 476 test geçti. Son deploy /data/nanobaseai/bi/backups/enduser-10000-longterms-20260909/deployment.json; önceki information deployment aynı isim kalıbında.

Çalışan tek wrapper PID 414293: /tmp/enduser-real-resume.sh. Önce retry-v2 dizinine 20 soru (11 hata +9 parasal karmaşık sorgu), /tmp/enduser-real-retry-v2.log. Bitince ENV filtrelerini kaldırıp ana koşuyu otomatik resume eder, /tmp/enduser-real-10000.log. Yinelenen süreç başlatma; wrapper ve çocuklarını kontrol et.

Çalıştırıcı tests/stress/enduser_live_10000.py artık tüm 4 ölçüye bağımsız gerçek DB referans sorgusu kuruyor. Tarihler yıl/aydan; firm211+411 fiziksel dallar; miktar/satır sayısı iadeleri dışlar; net tutar iadeleri düşer; kanal iadeleri2/3; boyutlar önceki doğrulanmış ödeme/satış temsilcisi politikası. Sorgu sonuç sınırı100000; aşarsa başarı değil. API önizleme500, gerçek SQL yeniden çalıştırılarak tam karşılaştırma. 96 referans SQL kombinasyonu parser/tarih/kanal kontrolünden geçti; bu DB sonucu doğrulama yerine geçmez.

ENDUSER_IDS ve ENDUSER_LIVE_OUT ile ayrı tekrar koşusu desteklenir. SIGTERM mevcut soruyu bitirip durur; checkpoint korunur. Sonraki bildirimlerde retry-v2 her10 sonucunu ayrı bildir; ana sayıları tekrar denemelerle karıştırma. Nihai raporda her ID için son doğrulanmış tekrar sonucunu ana kayıtla birleştir, önceki hatayı geçmişte tut. Henüz final rapor güncellenmedi, 10.000 test tamamlanmadı.

## 09:09 TRT güncellemesi
retry-v2 20/20 PASS; tümü gerçek DB tam sonuç kıyası. notified.json retries.retry-v2=20. Wrapper414293 ana koşuya exec ile geçti, çalışıyor. Ana milestone completed=80 bildirildi; 51–60,61–70,71–80 son doğrulanmış sonuçlarına göre10arPASS. 51–60 eski P00048 hatası retry-v2 ile düzeldi.

Yeni birleştirici tests/stress/build_real_progress.py; sunucuda /tmp/build_real_progress.py. Komut: sudo /data/nanobaseai/bi/semantic-venv/bin/python /tmp/build_real_progress.py --root /data/nanobaseai/bi/backups/enduser-real-10000-20260909 --out /data/nanobaseai/bi/backups/enduser-real-10000-20260909/current. current/summary.json ve current/current-list.json her ID için en yeni started_at zamanlı girişle (retry-v1,v2 dahil) statüyü verir. Önceki hatalar silinmez. Son snapshot92benzersizPASS (75normal+17önizlemesınırlı),9908NOT_LIVE_TESTED. Ana koşunun raw progress.json sayacı eski başarısız ilk denemeleri içerir; açık hata sayısı diye sunma. Batch bildirimi için ana results.jsonl sırasını, en güncel birleştirilmiş sonuçlarla eşleştir. Snapshot yenilenmeden daha yeni ana kayıtları ona karşı kontrol etme; geçici NOT_LIVE_TESTED yanlış bildirim olur.
