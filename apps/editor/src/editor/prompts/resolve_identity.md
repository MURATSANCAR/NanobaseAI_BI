<!-- name: resolve_identity version: 5 -->
Bir kitabın METNİNDE geçen karakter anmalarını kimliklere birleştir. Aşağıda her anma: id, sayfa, metinde yazıldığı ad, kanıt cümlesi.
<<<
{{mentions}}
>>>
EDİTÖRÜN KİMLİK DÜZELTMELERİ (bağlayıcı):
{{corrections}}

Kurallar:
- Aynı kişiye ait anmaları tek karakterde topla; `mention_ids` listele. Farklı adlar (lakap, unvan, akrabalık adı: "dedesi", "Profesör Bulut") aynı kişiyse aynı karakterde topla ve `merge_basis` alanında hangi cümleye dayandığını söyle. Kanıtı olmayan birleştirme yapma: iki ad aynı kişi olabilir ama metin söylemiyorsa ayrı bırak.
- `canonical_name`: o karakterin anmalarında GEÇEN adlardan en tam olanı. Listede olmayan bir ad uydurma. `aliases` alanını boş bırak; diğer adları sistem anmalardan kendisi çıkarır.
- `kind`: karakterin türü, METNE göre (insan çocuk/yetişkin, hayvan, robot/makine, düşsel yaratık); metin söylemiyorsa OTHER.
- `sex` ve `age_band`: yalnız METİNDEN çıkarılabiliyorsa yaz. Akrabalık ve unvan adları ("annesi", "dedesi", "amca", "teyze", "kız kardeşi"), zamirler, "adam/kadın/çocuk/bebek" gibi sözcükler ve karakterin kendisi hakkında söylenenler kanıttır; adın kendisi kanıt DEĞİLDİR (bir ad hem kıza hem oğlana verilebilir). Metin söylemiyorsa UNKNOWN. Bu alanlar iki karakteri birbirinden ayırmak için kullanılır, yanlışı boş bırakmaktan kötüdür.
- `description`: karakterin kim olduğu ve hikâyedeki rolü, YALNIZ metindeki kanıtlara göre. Saç, kıyafet, renk gibi görünüm bilgisi YAZMA; görünüm çizimlerden ayrıca çıkarılır.
- `identity_confidence`: 0.85 ve üstü yalnız birden fazla bağımsız kanıt varsa. Tek kanıta dayanan birleştirme en fazla 0.7.
- Bir anmanın iki karaktere birden uyabildiği durumları `conflicts` içine yaz; tahminle çözme.
- Türkçe yaz.

- Her anma kimliğini TAM BİR KEZ kullan: ya tek bir karakterin mention_ids listesinde ya unresolved_mention_ids içinde. Aynı anmayı iki karaktere yazma; hiçbir anmayı atlama; yeni kimlik üretme.
- ANILAN KİŞİ alanı anmanın öznesidir. Kanıt cümlesinde adı geçen başka kişiyi bu anmanın kimliği sayma. Ebeveyn ve yavru, aynı cümlede anılsalar bile farklı kişilerdir.
- Tür ve yaş farklı kavramlardır: konuşan, bilim yapan, anne/baba/yavru olan hayvanlar ANIMAL'dır. İnsan gibi davranmak HUMAN_CHILD/HUMAN_ADULT kanıtı değildir.
- Aynı yazılan ad farklı kişilere ait olabilir. Genel ad, topluluk ve unvanı zorla tek kişiye bağlama. Bir kez görünen kişi ayrı aday olabilir; onu sırf az göründüğü için atlama.
- Açıklama ve merge_basis kısa, en fazla iki cümle olsun. İç tartışmanı veya varsayımlarını bu alanlara yazma.
