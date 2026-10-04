<!-- name: production_film_script version: 1 -->
Bir kitaptan {{format}} çekeceğiz. Sen senaristsin ve yönetmensin: çekim listesini yaz.

Kitap: «{{title}}», {{kind}}.
Biçim: {{format}}, toplam {{min_sec}}–{{max_sec}} saniye. Görsel üslup: {{style}}.
{{hook}}

Kitabın bölüm bölüm özeti:
<<<
{{summary}}
>>>

Kitaptan birebir alıntılar (çekimleri bunlara bağla):
<<<
{{quotes}}
>>>

Bilinen karakterler (bu adları aynen kullan; listede olmayan karakter gerekiyorsa `cast`a ekle):
{{known}}

Kurallar:
- `cast`: filmde görünen ya da konuşan her karakter. `look_en` İngilizce görünüş tarifi (yaş, beden, saç, yüz, kıyafet; kitapta yazanla çelişme). `age` ve `gender` sesi seçmek içindir.
- Film çekimlerden oluşur; her çekim {{min_shot}}–{{max_shot}} saniye. Uzun sahne art arda çekimdir. Çekim türlerini değiştir: genel plan, yakın plan, omuz üstü; kamerayı anlamlı oynat.
- `action_en`: çekimde GÖRÜNEN şeyin İngilizce, somut tarifi (kim nerede ne yapıyor, ifadesi, ışık). Tek an, tek hareket; birden fazla olay sığdırma. Yazı, tabela, altyazı isteme.
- `action`: aynı tarifin kısa Türkçesi (editör okur).
- `quote`: çekimin dayandığı cümle; yukarıdaki alıntılardan ya da özetteki olaydan KELİMESİ KELİMESİNE kitaptan bir cümle. Uydurma.
- `lines`: çekimdeki replikler. Konuşan `cast`taki bir ad ya da «anlatıcı». Replik kısa ve doğal Türkçe olsun; bir saniyede en çok iki kelime sığar, çekim süresini buna göre seç. Kitaptaki konuşmayı kullanabiliyorsan kullan. `emotion` replik nasıl söylenir.
- `sfx`: çekimde duyulan kısa sesler, Türkçe («kapı gıcırtısı», «kılıç çarpışması»). `ambience`: arka plandaki sürekli ses («orman, kuş sesleri»), yoksa boş.
- Hikâye kitabın hikâyesi olsun: sırası, karakterleri ve sonu kitaptaki gibi. Kitapta olmayan olay ekleme.
{{feedback}}
