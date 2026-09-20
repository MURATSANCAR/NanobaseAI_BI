<!-- name: check_reference version: 2 -->
Bu görüntü bir kitap sayfasından kırpıldı ve "{{name}}" adlı karakterin referans çizimi olarak kullanılmak isteniyor.
Yalnız görüntüye bakarak söyle:
- `whole_figure`: kırpımda TEK ve BÜTÜN bir figür (en azından baş ve gövde) açıkça görünüyor mu? Bir parça, bir nesne, bir yazı, birden çok figür ya da tanınmayacak kadar küçük/kesik bir çizimse false.
- `kind`: figürün türü (HUMAN_CHILD, HUMAN_ADULT, ANIMAL, ROBOT_OR_MACHINE, FANTASY_CREATURE, OTHER).
- `sex` ve `age_band`: figürün ÇİZİMİNDE görüneni yaz (saç, giysi, beden, yüz çizgileri, sakal, gözlük...). Bir robot, hayvan ya da ayırt edilemeyen bir figür için UNKNOWN. Yaş kuşakları: CHILD, TEEN, ADULT, ELDERLY (ak saç, kırışık, yaşlı çizgileri).
- `features`: bu figürü başkalarından ayıran görünür özellikler (saç, aksesuar, kıyafet, renk, biçim), kısa bir liste.
