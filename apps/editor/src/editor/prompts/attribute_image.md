<!-- name: attribute_image version: 1 -->
Bu görüntü bir çocuk kitabının {{page_no}}. sayfasından kırpılmış TEK bir figürdür ("{{name}}" adlı karakter olarak tanınmış). YALNIZ görüntüye bakarak figürün görünüş özelliklerini aşağıdaki kapalı kümelerden seç.

Özellik türleri ve izin verilen değerler:
{{vocabulary}}

Kurallar:
- `gorunur`: kırpımda tek ve bütün bir figür açıkça görünüyor mu (bir parça, birden çok figür, tanınmayacak kadar küçük ya da kesik çizimse false).
- Bir özellik kırpımda görünmüyorsa, kesilmişse ya da emin değilsen BELIRSIZ. Figürde o şey yoksa YOK (şapka yok, gözlük yok, saç yok, elinde bir şey yok).
- Renk için ana rengi yaz; ışık, gölge ve ton farkını abartma. Tam uymuyorsa en yakın değeri, hiç uymuyorsa DIGER; iki eşit ağırlıklı renk varsa COK_RENKLI.
- Hayvan ya da yaratık figüründe TEN_KURK_RENGI tüy/kürk/derinin ana rengidir; saçı yoksa SAC_RENGI için YOK.
- Tahmin etme: görünen dışında hiçbir bilgi kullanma.
