<!-- name: production_film_adapt_scene version: 2 -->
Bir çocuk kitabını televizyonda yayınlanan bir çizgi film bölümüne uyarlıyoruz. Olay örgüsü hazır; sen şimdi bölümün yönetmeni ve storyboard sanatçısısın. Yalnız {{scene_no}}. SAHNENİN çekimlerini yaz.

Kitap: «{{title}}», {{kind}}. Görsel üslup: {{style}}.

Bütün bölümün olay örgüsü (bağlam için):
<<<
{{outline}}
>>>

Bu sahne: {{setting}} ({{setting_en}}), {{time}}. Hedef süre yaklaşık {{scene_sec}} saniye.
Bu sahnenin beat'leri ve dayandıkları kitap cümleleri:
<<<
{{beats}}
>>>

Kitaptaki KONUŞMALAR (bu sahnede geçenler; hepsi bir karakterin ağzından KELİMESİ KELİMESİNE söylenmeli, küçük çocuğun bozuk konuşması dahil):
<<<
{{dialogue}}
>>>

Oyuncular: {{cast}}
Anlatıcı: {{narrator}}

Kurallar:
- Her beat için 1–4 çekim yaz; çekimleri beat sırasıyla ver, `beat` alanına beat numarasını yaz.
- KAMERA VE KURGU: Çekimler 1,5–6 saniye. Konuşmada karşılıklı omuz üstü ve konuşanın yakını; araya dinleyenin TEPKİ çekimi. Yeni mekânda bir kez geniş plan, sonra yakına gir. Aynı çekim türünü üst üste en çok iki kez kullan. Komik anda hızlı kesmeler, duygusal anda tutulan yakın plan; doruk anında yavaş açılış (önce tepki veren yüz, sonra görülen şey).
- OYUNCULUK: `action_en` sahnede görünen tek anı somut tarif eder: kim nerede, ne yapıyor, yüz ifadesi, beden dili (İngilizce). Konuşmayan karakter de oynar (bakar, kaşlarını kaldırır, kıskanır, güler). `action` aynı tarifin kısa Türkçesi. Yazı, tabela, altyazı isteme.
- SES: `lines` o çekimde DUYULAN konuşma. Kitaptaki konuşmalar kelimesi kelimesine (`added`: false). Anlatıcının İÇ SESİ: bu sahnenin anlatım cümlelerinin (konuşma olmayanların) üçte biri ile yarısı arası, en önemlileri (geçiş, duygu, espri) anlatıcının ağzından kelimesi kelimesine (`speaker` anlatıcı, `added`: false); geri kalan anlatımı oyna. {{narration_hint}} Anlatıcı karedeyse iç sesi kendi söylüyormuş gibi oynar. Kitapla çelişmeyen kısa ünlem ve tepkiler eklenebilir (en çok 4 kelime: «Vaaay!», «Hı?», «Hadi!»; `added`: true); bunlar bütün satırların dörtte birini geçmez. Konuşma olmayan çekimde `lines` boş. `emotion` satırın nasıl söyleneceği.
- `quote`: çekimin dayandığı kitap cümlesi, metindeki gibi kelimesi kelimesine (beat'in cümlelerinden biri).
- `sfx`: çekimde duyulan kısa sesler (İngilizce, somut: "paper tearing", "crayons rattling"); `ambience`: sahnenin sürekli arka sesi (İngilizce) ya da boş.
- `characters`: karede GÖRÜNEN herkes.
- DİL: `action` Türkçe, `action_en` İngilizce; ikisini karıştırma.
- Kanca beat'i: bölümün en çarpıcı anından tek kısa görüntü (bu sahnede ne varsa). İsim beat'i: karakterlerin sevimli bir pozu, yazı YOK (isim kartı kurguda eklenir).
{{feedback}}
