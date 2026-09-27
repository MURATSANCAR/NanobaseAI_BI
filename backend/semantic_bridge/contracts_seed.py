"""M6 Sözleşmeler: kütüphane boşken açılan başlangıç şablonları.

Bunlar iskelettir: hukuk biriminin kendi metniyle (ya da Word dosyasıyla) değiştirmesi için vardır. Her şablonun
açıklamasında bu yazılıdır; şablon kütüphanesinden düzenlenir, arşivlenir ya da Word dosyası yüklenir.
"""
from __future__ import annotations

NOTE = "Başlangıç iskeleti. Timaş hukuk birimi kendi metnini yazmadan ya da Word şablonunu yüklemeden imzaya gönderilmemeli."

TELIF_ALIS = """# TELİF HAKKI DEVİR SÖZLEŞMESİ

Sözleşme No: {{sozlesme_no}}

## Madde 1 — Taraflar
Bu sözleşme, bir tarafta {{yayinevi}} (bundan sonra «YAYINEVİ» olarak anılacaktır) ile diğer tarafta {{taraflar}} (bundan sonra «HAK SAHİBİ» olarak anılacaktır) arasında aşağıdaki şartlarla yapılmıştır.

## Madde 2 — Konu
Sözleşmenin konusu, HAK SAHİBİ'ne ait «{{kitaplar}}» adlı eser(ler) üzerindeki mali hakların 5846 sayılı Fikir ve Sanat Eserleri Kanunu hükümleri çerçevesinde, aşağıda sayılan kapsamda YAYINEVİ'ne devridir.

## Madde 3 — Devredilen haklar
HAK SAHİBİ aşağıdaki mali hakları YAYINEVİ'ne devreder:
{{haklar}}

Bölge: {{bolge}} · Dil: {{dil}}

## Madde 4 — Süre
Sözleşme {{baslangic}} tarihinde başlar ve {{bitis}} tarihinde sona erer (süre: {{sure_yil}} yıl).

## Madde 5 — Telif ücreti
Ödeme şekli: {{odeme_sekli}}. Telif, {{telif_esasi}} hesaplanır.
Telif oranları:
{{telif_oranlari}}

Kademeli oranlar (varsa): {{kademeler}}
Telif hesaplama iskontosu: {{iskonto}}

## Madde 6 — Avans
YAYINEVİ, HAK SAHİBİ'ne {{avans}} ({{avans_yazi}}) avans öder. Avans, doğacak telif hakedişlerinden mahsup edilir.

## Madde 7 — Hakediş ve ödeme
Telif hakedişi {{hakedis_donemi}} aylık dönemler hâlinde hesaplanır ve dönem sonunu izleyen {{odeme_vadesi}} gün içinde ödenir. Yasal kesintiler (stopaj: {{stopaj}}) ödemeden düşülür.

## Madde 8 — Baskı
Eserin ilk baskısı {{ilk_baski}} adet olarak planlanmıştır.

## Madde 9 — Özel hükümler
{{notlar}}

## Madde 10 — Uyuşmazlık
Bu sözleşmeden doğacak uyuşmazlıklarda İstanbul mahkemeleri ve icra daireleri yetkilidir.

İşbu sözleşme {{bugun}} tarihinde iki nüsha olarak düzenlenmiş ve taraflarca imzalanmıştır.

YAYINEVİ: {{yayinevi}}

HAK SAHİBİ: {{hak_sahibi}}
"""

TELIF_SATIS = """# TELİF HAKKI LİSANS SÖZLEŞMESİ (YURTDIŞI / ÜÇÜNCÜ TARAF)

Sözleşme No: {{sozlesme_no}}

## Madde 1 — Taraflar
Lisans veren: {{yayinevi}}. Lisans alan: {{taraflar}}.

## Madde 2 — Konu
«{{kitaplar}}» adlı eser(ler)in {{dil}} dilinde, {{bolge}} bölgesinde yayımlanma hakkının lisanslanması.

## Madde 3 — Süre
{{baslangic}} – {{bitis}}.

## Madde 4 — Bedel
Avans: {{avans}} ({{avans_yazi}}). Telif oranları:
{{telif_oranlari}}
Hakediş bildirimi {{hakedis_donemi}} ayda bir yapılır; ödeme {{odeme_vadesi}} gün içinde.

## Madde 5 — Özel hükümler
{{notlar}}

{{bugun}}

Lisans veren: {{yayinevi}}

Lisans alan: {{hak_sahibi}}
"""

ZEYILNAME = """# ZEYİLNAME (EK PROTOKOL)

Zeyilname No: {{zeyilname_no}} · Ana sözleşme: {{sozlesme_no}}

## Madde 1 — Taraflar
{{yayinevi}} ile {{taraflar}} arasında imzalanan {{sozlesme_no}} numaralı sözleşmeye (bundan sonra «Ana Sözleşme») ektir.

## Madde 2 — Konu
{{zeyilname_konusu}}

## Madde 3 — Değişiklikler
Ana Sözleşme'nin aşağıdaki hükümleri {{zeyilname_tarihi}} tarihinden itibaren şu şekilde değiştirilmiştir:
{{zeyilname_degisiklikler}}

## Madde 4 — Gerekçe
{{zeyilname_gerekcesi}}

## Madde 5 — Diğer hükümler
Ana Sözleşme'nin bu zeyilnameyle değiştirilmeyen hükümleri aynen geçerlidir.

{{bugun}}

YAYINEVİ: {{yayinevi}}

HAK SAHİBİ: {{hak_sahibi}}
"""

HAKEDIS = """# TELİF HAKEDİŞ BİLDİRİMİ

Sözleşme: {{sozlesme_no}} — {{sozlesme_adi}}
Hak sahibi: {{taraflar}}
Dönem: {{hakedis_donem}}

## Hesap
Ödeme şekli: {{odeme_sekli}} · Telif esası: {{telif_esasi}}
Dönem adedi: {{hakedis_adet}}
Telif matrahı: {{hakedis_matrah}}
Brüt telif: {{hakedis_brut}}
Avanstan düşülen: {{hakedis_avans_mahsup}}
Stopaj: {{hakedis_stopaj}}
Ödenecek net tutar: {{hakedis_net}} ({{hakedis_net_yazi}})

## Kitap ve taraf ayrıntısı
{{hakedis_satirlar}}

Bu bildirim {{bugun}} tarihinde düzenlenmiştir.

{{yayinevi}}
"""

SEED = [
    {"name": "Telif hakkı devir sözleşmesi (başlangıç)", "target": "sozlesme", "kind": "telif-alis", "description": NOTE, "body": TELIF_ALIS},
    {"name": "Telif lisans sözleşmesi (başlangıç)", "target": "sozlesme", "kind": "telif-satis", "description": NOTE, "body": TELIF_SATIS},
    {"name": "Zeyilname (başlangıç)", "target": "zeyilname", "kind": None, "description": NOTE, "body": ZEYILNAME},
    {"name": "Hakediş bildirimi", "target": "hakedis", "kind": None,
     "description": "Hak sahibine gönderilen dönem hesabı. Alanlar hakedişten doldurulur.", "body": HAKEDIS},
]
