# CRM tarihçe ve revizyon kanıtı — 30 Eylül 2026

Gerçek Timas_MSCRM üzerinde test sunucusundan kontrollü salt SELECT yürütüldü. İş kayıtlarında statecode=0 kullanıldı; kaynak yazma ve ürün kabul koşusu yok. API eski/yeni değer kabulü **DOĞRULANAMADI**.

## Kanıt

- Sunucu `/tmp/codex-crm-history-20260930/discovery.json`, SHA256 `902953ce6b955686f8f6644c69487ef97f5ed4266660fb3034b73f16f2788b38`.
- Sunucu `/tmp/codex-crm-history-20260930/discovery2.json`, SHA256 `81e2c23fc81d3c9351f891d20ca310f070a2ff18ade021c874577303b9539040`.
- Metadata `/tmp/codex-crm-full-inventory-20260930-r2.json`.

Audit organizasyon, new_kitap ve new_sozlesme düzeyinde açık. sys.partitions yaklaşık satır sayısı 55.702.897; tam audit taraması/sayımı yapılmadı. ObjectTypeCode+CreatedOn ve ObjectId+ObjectTypeCode+CreatedOn indeksleri var. Eylül 2026 aralığında aktif kayıtlara bağlı TOP20 kitap ve TOP20 sözleşme audit örneği okundu; sorgu zaman aşımı 25 saniye. Bir kitap update maskesinde yayıncı alanının ColumnNumber343 değeri var. Bu, alanın audit olayına girdiği kanıtıdır; eski/yeni değerin doğru çözülmesi veya bütün geçmişin mevcut olması kanıtı değildir.

Kitabın bugünkü new_yayineviid alanı Marka, new_oncekiyayineviid alanı Account varlığına bağlı. Aktif 13.614 kitabın 331'inde önceki yayıncı dolu. Ad üzerinden kimlik birleştirilemez. new_kitapgecmisiBase baskı adedi, KDV dahil fiyat ve kapak alanları içerir; yayıncı geçerlilik dönemi veya genel old/new alanı bulunmadı.

Aktif sözleşme 14.869. Revize bitiş dolu 0; yenileme başlangıç/bitişinden en az biri dolu 389; fesih tarihi dolu 843; ek protokol tarihi dolu 24. Sıfır revize bitiş, geçmişte hiç revizyon olmadığını göstermez.

new_anasozlesmeid lookup değil nvarchar(100). Dolu 8.814 kaydın tamamı UUID olarak dönüştürülebiliyor: 1.383 kendine, 7.401 başka aktif sözleşmeye, 30 aktif kümede bulunmayan kimliğe işaret ediyor. Aday ana-sözleşme bağı olarak gösterilebilir; kronolojik revizyon zinciri veya üstün sözleşme seçimi kanıtlanmadı. new_OdemeDonemi gerçek sözleşme self-lookup olsa da etiketi Ödeme Dönemi; revizyon parent alanı sayılamaz.

new_sozlesmelogBase.new_sozlesmeid → new_sozlesmeId ilişkisi doğrulandı. Aktif sözleşmelere bağlı aktif 8.555 log: Create 7.535, Update 6, Delete 1.014. Bunların 8.539'unda new_name .pdf ile bitiyor; son 10 örnek PDF dosya yolu. Belge işlem günlüğü adayıdır; sözleşme alanı old/new geçmişi olduğu kanıtlanmadı. Etiketler StringMapBase ile doğrulandı.

## Güvenli rapor alanları

| Çıktı | Kaynak |
|---|---|
| contract_id | new_sozlesmeId |
| parent_id_text / parsed_parent_id | new_anasozlesmeid / doğrulanan UUID dönüşümü |
| parent_link_status | self / active_parent / unavailable_active_parent / invalid / missing |
| start_date / end_date | new_SozlesmeBaslangicTarihi / new_SozlesmeBitisTarihi |
| revised_end_date | new_revizebitistarihi |
| renewal_start_date / renewal_end_date | new_yenilemebaslangictarihi / new_yenilemebitistarihi |
| termination_date / indefinite_flag | new_fesihtarihi / new_suresizsozlesme |
| protocol_date / protocol_end_date | new_ekprotokoltarihi / new_ekprotokolbitist |
| protocol_flag / protocol_fixed_term | new_EkProtokolyeni / new_ekprotokolsurelimi |
| document_event_id / type / time | new_sozlesmelogId / new_logtipi / CreatedOn |

**new_ekprotokol kullanılmamalı:** metadata etiketi “Ek Protokol (hatalı)”; yeni flag ayrı alandır. Logdaki dosya yolları erişilebilir indirme bağlantısı olarak sunulmamalı.

effective_end_date, governing_contract veya sales_forbidden sonucu üretilmemeli. Alan önceliği, fesih/yenileme etkisi, ek protokol ana sözleşme ilişkisi ve ülke+bölge kapsamının AND/OR anlamı kanıtlanmadı. Bölge veya ülke kümelerinden yalnız birinin kesişmesi kesin hak çatışması değildir; scope_interpretation_unverified gap gerekir.

## Eski/yeni değer kabul kapısı

Microsoft desteklenen RetrieveAuditDetails, RetrieveRecordChangeHistory ve RetrieveAttributeChangeHistory mesajlarını önerir; tipli AttributeAuditDetail OldValue/NewValue kullanılmalıdır. AttributeMask/ChangeData için özel ayraç tahminiyle üretim decoder yazılmamalı. Kaynaklar: [Dynamics on-prem audit geçmişi](https://learn.microsoft.com/en-us/dynamics365/customerengagement/on-premises/developer/retrieve-and-delete-the-history-of-audited-data-changes?view=op-9-1), [Microsoft audit verisi alma](https://learn.microsoft.com/en-us/power-apps/developer/data-platform/auditing/retrieve-audit-data).

Sonraki kapı: mevcut saltokunur SDK/API kimliği ve audit-read yetkisiyle bilinen auditId için tipli eski/yeni lookup GUIDleri alınır; gerçek portalın aynı yürütmedeki tam çıktısı bu bağımsız yanıtla karşılaştırılır. Sayfalama, boş değere değişim, çok alanlı olay, eşzamanlı olaylar, silinmiş referans ve tarihçe başlangıcı/kayıp aralıkları doğrulanır. SQL erişimi desteklenen SDK audit mesajlarına erişim kanıtı değildir. Bugün auditin açık olması tüm geçmişin saklandığını göstermez. Güncel yayıncıyı geçmiş satışa uygulamak bu doğrulama yerine geçmez.
